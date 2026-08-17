# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""fantasy_closer_lab.py - the measurement behind the pre-registered closer
save-share gate (docs/fantasy-closer-gate-2026-08-16.md).

Every clause it implements (weights, windows, pool, metrics, ship bar, the
data-blocked floor) is stated in that document, which was written and dated
BEFORE this file existed. This script computes and reports; it decides
nothing the document did not already decide.

Data, all of it predating the gate:
  * saves: official save decisions off the StatsAPI season schedule
    (hydrate=decisions), one fetch, cached under .cache/closer_lab/;
  * gmLI and relief appearances: the committed .cache/win_prob per-game cache
    (entry leverage index per appearance, entry_inning > 1 = relief, the same
    rule mlb_leverage._merge_reliever ships);
  * club per appearance: the play's half-inning side joined to the schedule's
    home and away orgs; club per save: the winning side of the game, because
    a save pitcher pitches for the winner by definition.

Run:  python tools/fantasy_closer_lab.py
      python tools/fantasy_closer_lab.py --rebuild     (re-extract appearances)
      python tools/fantasy_closer_lab.py --refresh     (re-fetch the schedule)

Writes .cache/closer_lab/fantasy_closer_gate_eval.json and prints the summary
block the gate doc transcribes verbatim.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# The clauses, transcribed from the gate doc. Changing any of these without
# re-registering the gate voids the measurement.
# ---------------------------------------------------------------------------
SEASON = 2026
W_SV, W_GMLI = 0.65, 0.35        # fixed stated weights, no fitting
TRAIL_DAYS = 30                  # trailing feature window
HORIZON_DAYS = 14                # forward label window
BASE_START = date(2026, 4, 24)   # first start with a full trailing window
GROUP_OFFSETS = (0, 5, 10)       # org index mod 3 staggers the start dates
SPACING_DAYS = 14                # per-team spacing = non-overlapping labels
MIN_APPS_POOL = 2                # relief appearances to enter a team's pool
MIN_POOL_SPEARMAN = 3            # arms needed for a within-team rank corr
SHIP_CONSISTENCY = 0.70          # share of window starts champion must win
MIN_WINPROB_COVERAGE = 0.90      # data-blocked floor
MIN_WINDOW_STARTS = 15           # data-blocked floor

CACHE = ROOT / ".cache" / "closer_lab"
SCHEDULE_CACHE = CACHE / f"schedule_{SEASON}_decisions.json"
APPEARANCES_CACHE = CACHE / f"appearances_{SEASON}.jsonl"
EVAL_PATH = CACHE / "fantasy_closer_gate_eval.json"
WIN_PROB_DIR = ROOT / ".cache" / "win_prob"

SCHEDULE_API = "https://statsapi.mlb.com/api/v1/schedule"


def fetch_schedule(refresh: bool = False) -> dict:
    """The season schedule with decisions and scores, cached on disk. One
    network call per season per box unless --refresh asks again."""
    if SCHEDULE_CACHE.exists() and not refresh:
        try:
            return json.loads(SCHEDULE_CACHE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    import feed_cache
    resp = feed_cache.SESSION.get(SCHEDULE_API, params={
        "sportId": 1, "season": SEASON, "gameType": "R",
        "hydrate": "decisions",
        "fields": ("dates,date,games,gamePk,officialDate,status,"
                   "abstractGameState,teams,home,away,team,id,name,score,"
                   "decisions,save,id,fullName"),
    }, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    CACHE.mkdir(parents=True, exist_ok=True)
    SCHEDULE_CACHE.write_text(json.dumps(data), encoding="utf-8")
    return data


def _org(name: str | None) -> str | None:
    try:
        from trades import canonical_org
        return canonical_org(name) or name
    except Exception:
        return name


def parse_games(raw: dict, today: date) -> list[dict]:
    """Final regular-season games through `today`, with orgs, scores and the
    save decision. A stray future-dated 'final' is excluded by the date test."""
    out: list[dict] = []
    org_cache: dict = {}

    def org_of(name):
        if name not in org_cache:
            org_cache[name] = _org(name)
        return org_cache[name]

    for d in raw.get("dates", []):
        for g in d.get("games", []):
            if ((g.get("status") or {}).get("abstractGameState")) != "Final":
                continue
            day = g.get("officialDate") or d.get("date")
            try:
                gd = date.fromisoformat(day)
            except (TypeError, ValueError):
                continue
            if gd > today:
                continue
            teams = g.get("teams") or {}
            home, away = teams.get("home") or {}, teams.get("away") or {}
            hs, as_ = home.get("score"), away.get("score")
            row = {
                "pk": int(g["gamePk"]), "date": day,
                "home_org": org_of((home.get("team") or {}).get("name")),
                "away_org": org_of((away.get("team") or {}).get("name")),
                "home_score": hs, "away_score": as_,
                "save_pid": ((g.get("decisions") or {}).get("save") or {}).get("id"),
            }
            if row["home_org"] and row["away_org"]:
                out.append(row)
    return out


def _extract_game_pitchers(plays: list) -> dict:
    """{pid: {entry_li, entry_inning, is_home}} for one game's play stream.
    The same walk as mlb_leverage._game_pitcher_dict plus the SIDE, which the
    shipped fold does not need but the club join here does."""
    gp: dict = {}
    for play in plays:
        p = (play.get("matchup") or {}).get("pitcher") or {}
        pid = p.get("id")
        if not pid:
            continue
        ab = play.get("about") or {}
        half = ab.get("halfInning")
        is_home = (half == "top") if half else bool(ab.get("isTopInning"))
        li = play.get("leverageIndex")
        inning = ab.get("inning")
        d = gp.get(pid)
        if d is None:
            gp[pid] = {"entry_li": li, "entry_inning": inning, "is_home": is_home}
        elif d["entry_li"] is None and li is not None:
            d["entry_li"] = li
            if d["entry_inning"] is None:
                d["entry_inning"] = inning
    return gp


def build_appearances(games: list[dict], rebuild: bool = False) -> tuple[list, dict]:
    """All RELIEF appearances (entry_inning > 1) with club and entry LI, plus
    coverage counts. Extracted once from the win_prob cache and memoized as
    jsonl; the extraction pass reads ~1,900 cached play files and the memo
    makes every rerun free."""
    if APPEARANCES_CACHE.exists() and not rebuild:
        try:
            lines = APPEARANCES_CACHE.read_text(encoding="utf-8").splitlines()
            memo = [json.loads(l) for l in lines if l.strip()]
            if memo and isinstance(memo[0], dict) and memo[0].get("kind") == "meta":
                return memo[1:], memo[0]["coverage"]
        except (json.JSONDecodeError, OSError):
            pass
    import mlb_leverage
    rows: list = []
    n_have = n_miss = 0
    for g in games:
        path = WIN_PROB_DIR / f"{g['pk']}.json"
        if not path.exists():
            n_miss += 1
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            n_miss += 1
            continue
        n_have += 1
        plays = mlb_leverage._plays_of(payload)
        for pid, d in _extract_game_pitchers(plays).items():
            if d.get("entry_inning") == 1:
                continue            # a start or an opener, not relief
            rows.append({"pid": int(pid), "date": g["date"], "pk": g["pk"],
                         "org": g["home_org"] if d["is_home"] else g["away_org"],
                         "entry_li": d.get("entry_li")})
    coverage = {"games_final": len(games), "games_with_win_prob": n_have,
                "games_missing_win_prob": n_miss}
    CACHE.mkdir(parents=True, exist_ok=True)
    with APPEARANCES_CACHE.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": "meta", "coverage": coverage}) + "\n")
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    return rows, coverage


def save_events(games: list[dict]) -> list[dict]:
    """One row per official save: pitcher, date, club (the winning side)."""
    out = []
    for g in games:
        pid = g.get("save_pid")
        if not pid:
            continue
        hs, as_ = g.get("home_score"), g.get("away_score")
        if hs is None or as_ is None or hs == as_:
            continue
        out.append({"pid": int(pid), "date": g["date"], "pk": g["pk"],
                    "org": g["home_org"] if hs > as_ else g["away_org"]})
    return out


def _spearman(a: list, b: list):
    try:
        from scipy.stats import spearmanr
        rho = spearmanr(a, b).statistic
        return None if rho != rho else float(rho)   # NaN guard
    except Exception:
        return None


def _share_predictions(pool: list, sv30: dict, gmli30: dict, team_sv30: float,
                       w_sv: float, w_gmli: float) -> dict:
    """The champion's share allocation over one pool, with the degenerate
    cases the gate doc decided in advance."""
    gm = {p: max(gmli30.get(p) or 0.0, 0.0) for p in pool}
    gm_sum = sum(gm.values())
    shares: dict = {}
    for p in pool:
        sv_term = (sv30.get(p, 0) / team_sv30) if team_sv30 > 0 else None
        gm_term = (gm[p] / gm_sum) if gm_sum > 0 else None
        if sv_term is None and gm_term is None:
            shares[p] = 1.0 / len(pool)
        elif sv_term is None:
            shares[p] = gm_term
        elif gm_term is None:
            shares[p] = sv_term
        else:
            shares[p] = w_sv * sv_term + w_gmli * gm_term
    team_hat = team_sv30 * (HORIZON_DAYS / TRAIL_DAYS)
    return {p: shares[p] * team_hat for p in pool}


def run_lab(args) -> int:
    today = date.today()
    raw = fetch_schedule(refresh=args.refresh)
    games = parse_games(raw, today)
    if not games:
        print("DATA_BLOCKED: the season schedule returned no resolved final "
              "games. Searched: StatsAPI /schedule season=%d hydrate=decisions."
              % SEASON)
        return 2
    data_end = max(date.fromisoformat(g["date"]) for g in games)
    season_start = min(date.fromisoformat(g["date"]) for g in games)

    saves = save_events(games)
    if not saves:
        print("DATA_BLOCKED: no official save decisions on the season schedule "
              "(hydrate=decisions returned none). The gate cannot run without "
              "a saves series and nothing is substituted for one.")
        return 2

    apps, coverage = build_appearances(games, rebuild=args.rebuild)
    cov = (coverage["games_with_win_prob"] / coverage["games_final"]
           if coverage["games_final"] else 0.0)
    if cov < MIN_WINPROB_COVERAGE:
        print(f"DATA_BLOCKED: the win_prob cache covers {cov:.1%} of final "
              f"{SEASON} games, under the {MIN_WINPROB_COVERAGE:.0%} floor the "
              "gate doc set. Searched: .cache/win_prob/{game_pk}.json for "
              f"{coverage['games_final']} final games "
              f"({coverage['games_missing_win_prob']} missing).")
        return 2

    # Indexes. Dates stay ISO strings; the comparisons are lexicographic.
    apps_by_org: dict = defaultdict(list)
    for r in apps:
        if r["org"]:
            apps_by_org[r["org"]].append(r)
    saves_by_org: dict = defaultdict(list)
    saves_by_pid: dict = defaultdict(list)
    for s in saves:
        if s["org"]:
            saves_by_org[s["org"]].append(s)
        saves_by_pid[s["pid"]].append(s)

    orgs = sorted(set(apps_by_org))
    starts_by_org: dict = {}
    all_starts: set = set()
    for i, org in enumerate(orgs):
        t = BASE_START + timedelta(days=GROUP_OFFSETS[i % len(GROUP_OFFSETS)])
        lst = []
        while t + timedelta(days=HORIZON_DAYS - 1) <= data_end:
            lst.append(t)
            all_starts.add(t)
            t += timedelta(days=SPACING_DAYS)
        starts_by_org[org] = lst
    if len(all_starts) < MIN_WINDOW_STARTS:
        print(f"DATA_BLOCKED: only {len(all_starts)} window starts fit between "
              f"{BASE_START} and {data_end}, under the {MIN_WINDOW_STARTS} "
              "floor the gate doc set.")
        return 2

    # ---- replay -----------------------------------------------------------
    rows: list = []            # one per (org, T, pid)
    cells: list = []           # one per (org, T) with a valid rank corr
    n_cells_skipped = 0
    for org in orgs:
        oapps = apps_by_org[org]
        osaves = saves_by_org[org]
        for t in starts_by_org[org]:
            lo = (t - timedelta(days=TRAIL_DAYS)).isoformat()
            hi = (t - timedelta(days=1)).isoformat()
            f_lo, f_hi = t.isoformat(), (t + timedelta(days=HORIZON_DAYS - 1)).isoformat()
            trail = [a for a in oapps if lo <= a["date"] <= hi]
            n_apps: dict = defaultdict(int)
            li_vals: dict = defaultdict(list)
            for a in trail:
                n_apps[a["pid"]] += 1
                if a["entry_li"] is not None:
                    li_vals[a["pid"]].append(a["entry_li"])
            pool = sorted(p for p, n in n_apps.items() if n >= MIN_APPS_POOL)
            if not pool:
                continue
            gmli30 = {p: statistics.fmean(li_vals[p]) for p in pool if li_vals[p]}
            sv30 = defaultdict(int)
            for s in osaves:
                if lo <= s["date"] <= hi:
                    sv30[s["pid"]] += 1
            team_sv30 = float(sum(sv30[p] for p in pool))
            pred_c = _share_predictions(pool, sv30, gmli30, team_sv30, W_SV, W_GMLI)
            pred_ref = _share_predictions(pool, sv30, gmli30, team_sv30, 1.0, 0.0)
            days_elapsed = max(1, (t - season_start).days)
            actual = defaultdict(int)
            for s in osaves:
                if f_lo <= s["date"] <= f_hi:
                    actual[s["pid"]] += 1
            pred_b: dict = {}
            for p in pool:
                sv_std = sum(1 for s in saves_by_pid.get(p, []) if s["date"] <= hi)
                pred_b[p] = sv_std * HORIZON_DAYS / days_elapsed
            for p in pool:
                rows.append({"org": org, "start": t.isoformat(), "pid": p,
                             "pred_champion": round(pred_c[p], 4),
                             "pred_baseline": round(pred_b[p], 4),
                             "pred_sv_only": round(pred_ref[p], 4),
                             "actual": actual.get(p, 0)})
            # rank cell, per the doc: pool >= 3 and no constant vector
            act_v = [actual.get(p, 0) for p in pool]
            c_v = [pred_c[p] for p in pool]
            b_v = [pred_b[p] for p in pool]
            r_v = [pred_ref[p] for p in pool]
            if (len(pool) >= MIN_POOL_SPEARMAN
                    and len(set(act_v)) > 1 and len(set(c_v)) > 1
                    and len(set(b_v)) > 1):
                rho_c = _spearman(c_v, act_v)
                rho_b = _spearman(b_v, act_v)
                rho_r = _spearman(r_v, act_v) if len(set(r_v)) > 1 else None
                if rho_c is not None and rho_b is not None:
                    cells.append({"org": org, "start": t.isoformat(),
                                  "n_pool": len(pool),
                                  "rho_champion": round(rho_c, 4),
                                  "rho_baseline": round(rho_b, 4),
                                  "rho_sv_only": (round(rho_r, 4)
                                                  if rho_r is not None else None)})
                else:
                    n_cells_skipped += 1
            else:
                n_cells_skipped += 1

    # ---- aggregate --------------------------------------------------------
    def mae(key: str, sub=None) -> float:
        rs = sub if sub is not None else rows
        return statistics.fmean(abs(r[key] - r["actual"]) for r in rs)

    per_start = []
    for t in sorted(all_starts):
        ts = t.isoformat()
        srows = [r for r in rows if r["start"] == ts]
        scells = [c for c in cells if c["start"] == ts]
        if not srows:
            continue
        e = {"start": ts, "n_rows": len(srows), "n_cells": len(scells),
             "mae_champion": round(mae("pred_champion", srows), 4),
             "mae_baseline": round(mae("pred_baseline", srows), 4),
             "rho_champion": (round(statistics.fmean(
                 c["rho_champion"] for c in scells), 4) if scells else None),
             "rho_baseline": (round(statistics.fmean(
                 c["rho_baseline"] for c in scells), 4) if scells else None)}
        e["champion_wins_both"] = bool(
            e["mae_champion"] < e["mae_baseline"]
            and e["rho_champion"] is not None
            and e["rho_baseline"] is not None
            and e["rho_champion"] > e["rho_baseline"])
        per_start.append(e)

    pooled = {
        "mae_champion": round(mae("pred_champion"), 4),
        "mae_baseline": round(mae("pred_baseline"), 4),
        "mae_sv_only": round(mae("pred_sv_only"), 4),
        "rho_champion": round(statistics.fmean(
            c["rho_champion"] for c in cells), 4) if cells else None,
        "rho_baseline": round(statistics.fmean(
            c["rho_baseline"] for c in cells), 4) if cells else None,
        "rho_sv_only": (round(statistics.fmean(
            c["rho_sv_only"] for c in cells if c["rho_sv_only"] is not None), 4)
            if any(c["rho_sv_only"] is not None for c in cells) else None),
    }
    n_wins = sum(1 for e in per_start if e["champion_wins_both"])
    win_share = n_wins / len(per_start) if per_start else 0.0
    cond1 = pooled["mae_champion"] < pooled["mae_baseline"]
    cond2 = (pooled["rho_champion"] is not None
             and pooled["rho_baseline"] is not None
             and pooled["rho_champion"] > pooled["rho_baseline"])
    cond3 = win_share >= SHIP_CONSISTENCY
    verdict = "SHIP" if (cond1 and cond2 and cond3) else "RED"

    result = {
        "gate_doc": "docs/fantasy-closer-gate-2026-08-16.md",
        "computed_at": today.isoformat(),
        "config": {"season": SEASON, "w_sv": W_SV, "w_gmli": W_GMLI,
                   "trail_days": TRAIL_DAYS, "horizon_days": HORIZON_DAYS,
                   "base_start": BASE_START.isoformat(),
                   "group_offsets": list(GROUP_OFFSETS),
                   "spacing_days": SPACING_DAYS,
                   "min_apps_pool": MIN_APPS_POOL,
                   "ship_consistency": SHIP_CONSISTENCY},
        "frame": {"season_start": season_start.isoformat(),
                  "data_end": data_end.isoformat(),
                  "coverage": coverage,
                  "n_save_decisions": len(saves),
                  "n_orgs": len(orgs),
                  "n_window_starts": len(per_start),
                  "n_team_windows": len({(r['org'], r['start']) for r in rows}),
                  "n_rp_rows": len(rows),
                  "n_rank_cells": len(cells),
                  "n_rank_cells_skipped": n_cells_skipped},
        "pooled": pooled,
        "per_start": per_start,
        "conditions": {"1_pooled_mae": cond1, "2_mean_rho": cond2,
                       "3_consistency": cond3,
                       "wins_both": n_wins, "win_share": round(win_share, 3)},
        "verdict": verdict,
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    EVAL_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")

    print(f"frame:    {SEASON} regular season {season_start}..{data_end}")
    print(f"          {coverage['games_final']} final games; win_prob cached for "
          f"{coverage['games_with_win_prob']} ({cov:.1%}); "
          f"{len(saves)} official save decisions")
    print(f"          {len(per_start)} window starts, "
          f"{result['frame']['n_team_windows']} team-windows, "
          f"{len(rows)} RP rows, {len(cells)} rank cells "
          f"({n_cells_skipped} skipped)")
    d_mae = pooled["mae_champion"] - pooled["mae_baseline"]
    print(f"pooled MAE   champion {pooled['mae_champion']:.4f}   "
          f"baseline {pooled['mae_baseline']:.4f}   delta {d_mae:+.4f} "
          f"({d_mae / pooled['mae_baseline']:+.1%})")
    if pooled["rho_champion"] is not None:
        d_rho = pooled["rho_champion"] - pooled["rho_baseline"]
        print(f"mean rho     champion {pooled['rho_champion']:.4f}   "
              f"baseline {pooled['rho_baseline']:.4f}   delta {d_rho:+.4f}")
    print(f"per-start    champion wins BOTH metrics in {n_wins} of "
          f"{len(per_start)} starts ({win_share:.1%}; bar {SHIP_CONSISTENCY:.0%})")
    print(f"sv-only ref  (w_sv=1.0)  MAE {pooled['mae_sv_only']:.4f}  "
          f"rho {pooled['rho_sv_only'] if pooled['rho_sv_only'] is not None else 'n/a'}")
    print(f"VERDICT: {verdict}")
    print(f"eval artifact: {EVAL_PATH}")
    return 0 if verdict == "SHIP" else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Closer save-share gate lab "
                                             "(pre-registered 2026-08-16).")
    ap.add_argument("--rebuild", action="store_true",
                    help="re-extract relief appearances from the win_prob cache")
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch the season schedule (decisions hydration)")
    sys.exit(run_lab(ap.parse_args()))
