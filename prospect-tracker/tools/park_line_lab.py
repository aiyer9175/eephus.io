# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""W2 PARK-LINE gate lab (pre-registered: docs/wills-2026-07-23/GATES.md, W2).

REGISTERED THRESHOLDS (frozen a priori, hard-coded here, never retuned):
  SEED           = 20260723   bootstrap seed (player-clustered, 2000 reps)
  BOOT_REPS      = 2000
  M bar          : Spearman delta (neutralized vs raw current-season rate,
                   predicting next-season RAW rate) bootstrap lo95 > 0, per side
  Clause 1       : flag OFF byte-identical to committed behavior; flag ON
                   byte-identical for every uncovered row (0 violations)
  Clause 2 bar   : pooled OOS blend Spearman delta >= -0.003 per side
                   (evals.debuted_km.pooled_oos.blend.spearman)
  Clause 3       : run PF clamped [0.90, 1.10], HR PF clamped [0.80, 1.25]
                   at application time (verified against efv_park_line code)
  K_G            = 70         EB shrink prior (home games) toward PF 1.0
  DOMINANT_SHARE = 0.70       (numTeams==1 rows carry share 1.00)
  EXPOSURE       : hit >= 100 PA, pit >= 40 IP, both seasons of an M pair
  SPORTS/SEASONS : 11/12/13/14/16, 2021-2026 (venue window = seasons <= t,
                   3-season lookback)
  STOP-D         : either data sub-phase failing cheaply, or run-PF coverage
                   under 0.90 of observed team-seasons

Frozen neutralization formulas (GATES.md W2, implemented in efv_park_line):
  applied_run_pf = (venue_run_pf + 1) / 2
  hitters:  obp/slg/ops/iso each / sqrt(applied_run_pf)  (avg scaled by the
            same sqrt factor so derived iso = slg - avg lands exactly)
  pitchers: era / applied_run_pf

Phases (subcommands; every fetch cache-first and resumable):
  fetch    Phase A schedules -> .cache/milb_schedules/
           Phase B player team-split season stats + team home/away HR splits
           -> .cache/milb_team_stats/
  factors  build data/milb_park_factors.json (+ STOP-D check)
  clausem  measurement-validity study (per side)
  gate     clauses 1-3 (matrix invariance + no-harm eval + clamps), write
           data/xfv_park_line_eval.json, restore matrices to the
           module-default (OFF) state
  all      fetch + factors + clausem + gate

Run: python -m tools.park_line_lab all        (from prospect-tracker/)
"""
from __future__ import annotations

import json
import os
import random
import statistics
import sys
import time
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

SEED = 20260723
BOOT_REPS = 2000
POOL_BAR = -0.003
RUN_PF_LO, RUN_PF_HI = 0.90, 1.10
HR_PF_LO, HR_PF_HI = 0.80, 1.25
K_G = 70
MIN_LEAGUE_TEAMS = 4          # league-season centering small-sample guard (a priori)
DOMINANT_SHARE = 0.70
HIT_PA_FLOOR = 100
PIT_IP_FLOOR = 40.0
SPORTS = (11, 12, 13, 14, 16)
SEASONS = tuple(range(2021, 2027))
STOPD_COVERAGE_BAR = 0.90

SCHED_DIR = _ROOT / ".cache" / "milb_schedules"
TSTAT_DIR = _ROOT / ".cache" / "milb_team_stats"
CKPT_DIR = _ROOT / ".cache" / "park_line_lab"
PF_PATH = _ROOT / "data" / "milb_park_factors.json"
EVAL_PATH = _ROOT / "data" / "xfv_park_line_eval.json"

_UA = {"User-Agent": "Mozilla/5.0"}
SPORT_LEVEL = {11: "AAA", 12: "AA", 13: "A+", 14: "A"}   # 16 splits DSL/CPX by league


def _fetch_json(url: str, tries: int = 3) -> dict:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.loads(r.read())
            time.sleep(0.25)            # polite pacing
            return out
        except Exception as e:          # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"fetch failed after {tries} tries: {url}: {last!r}")


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _ip_float(v):
    """StatsAPI innings notation: '62.1' = 62 and 1/3."""
    if v is None:
        return None
    s = str(v)
    try:
        if "." in s:
            whole, frac = s.split(".", 1)
            return int(whole) + {"0": 0.0, "1": 1 / 3, "2": 2 / 3}.get(frac, 0.0)
        return float(s)
    except ValueError:
        return None


def _level16(league: str) -> str:
    """Mirror milb_history._level16: DSL/VSL are their own environment."""
    return "DSL" if (league or "").strip().upper() in ("DSL", "VSL") else "CPX"


def _spearman(xs, ys):
    from prospect_path import _spearman as sp
    return sp(xs, ys)


# ---------------------------------------------------------------------------
# fetch: phase A (schedules) + phase B (player team splits, team h/a splits)
# ---------------------------------------------------------------------------

def fetch_schedules() -> dict:
    SCHED_DIR.mkdir(parents=True, exist_ok=True)
    acct = {}
    for sport in SPORTS:
        for season in SEASONS:
            path = SCHED_DIR / f"schedule_{sport}_{season}.json"
            if path.exists() and path.stat().st_size > 2:
                acct[f"{sport}_{season}"] = "cached"
                continue
            d = _fetch_json("https://statsapi.mlb.com/api/v1/schedule"
                            f"?sportId={sport}&season={season}&gameTypes=R")
            lean = []
            for day in d.get("dates") or []:
                for g in day.get("games") or []:
                    v = g.get("venue") or {}
                    th = (g.get("teams") or {}).get("home") or {}
                    ta = (g.get("teams") or {}).get("away") or {}
                    lean.append({
                        "d": g.get("officialDate"),
                        "v": v.get("id"), "vn": v.get("name"),
                        "h": (th.get("team") or {}).get("id"),
                        "hn": (th.get("team") or {}).get("name"),
                        "a": (ta.get("team") or {}).get("id"),
                        "hs": th.get("score"), "as": ta.get("score"),
                        "st": (g.get("status") or {}).get("codedGameState"),
                    })
            path.write_text(json.dumps(lean, separators=(",", ":")),
                            encoding="utf-8")
            acct[f"{sport}_{season}"] = len(lean)
            print(f"  schedule {sport}/{season}: {len(lean)} games", flush=True)
    return acct


def fetch_team_stats() -> dict:
    TSTAT_DIR.mkdir(parents=True, exist_ok=True)
    acct = {}
    for group in ("hitting", "pitching"):
        for sport in SPORTS:
            for season in SEASONS:
                path = TSTAT_DIR / f"{group}_{sport}_{season}.json"
                if path.exists() and path.stat().st_size > 2:
                    acct[f"{group}_{sport}_{season}"] = "cached"
                    continue
                lean, offset = [], 0
                while True:
                    d = _fetch_json(
                        "https://statsapi.mlb.com/api/v1/stats?stats=season"
                        f"&group={group}&sportId={sport}&season={season}"
                        f"&playerPool=ALL&limit=2000&offset={offset}")
                    block = (d.get("stats") or [{}])[0]
                    page = block.get("splits") or []
                    for s in page:
                        st = s.get("stat") or {}
                        league = (s.get("league") or {}).get("name") or ""
                        level = _level16(league) if sport == 16 else SPORT_LEVEL[sport]
                        row = {"mlbam": (s.get("player") or {}).get("id"),
                               "name": (s.get("player") or {}).get("fullName"),
                               "team_id": (s.get("team") or {}).get("id"),
                               "team_name": (s.get("team") or {}).get("name"),
                               "league": league, "level": level,
                               "num_teams": s.get("numTeams") or 1}
                        if group == "hitting":
                            row.update({"pa": st.get("plateAppearances"),
                                        "ab": st.get("atBats"),
                                        "so": st.get("strikeOuts"),
                                        "bb": st.get("baseOnBalls"),
                                        "hr": st.get("homeRuns"),
                                        "avg": st.get("avg"), "obp": st.get("obp"),
                                        "slg": st.get("slg"), "ops": st.get("ops")})
                        else:
                            row.update({"ip": st.get("inningsPitched"),
                                        "bf": st.get("battersFaced"),
                                        "era": st.get("era"),
                                        "so": st.get("strikeOuts"),
                                        "bb": st.get("baseOnBalls"),
                                        "hr": st.get("homeRuns"),
                                        "g": st.get("gamesPlayed"),
                                        "gs": st.get("gamesStarted")})
                        lean.append(row)
                    total = block.get("totalSplits") or len(lean)
                    offset += len(page)
                    if not page or offset >= total:
                        break
                path.write_text(json.dumps(lean, separators=(",", ":")),
                                encoding="utf-8")
                acct[f"{group}_{sport}_{season}"] = len(lean)
                print(f"  team_stats {group}/{sport}/{season}: {len(lean)} rows",
                      flush=True)
    return acct


def fetch_team_splits() -> dict:
    """Team-level home/away splits (HR + runs) for hr_pf: one call per
    (sport, season, group, sitCode)."""
    TSTAT_DIR.mkdir(parents=True, exist_ok=True)
    acct = {}
    for group in ("hitting", "pitching"):
        for sport in SPORTS:
            for season in SEASONS:
                for sc in ("h", "a"):
                    path = TSTAT_DIR / f"teamsplit_{group}_{sport}_{season}_{sc}.json"
                    if path.exists() and path.stat().st_size > 2:
                        acct[f"{group}_{sport}_{season}_{sc}"] = "cached"
                        continue
                    d = _fetch_json(
                        "https://statsapi.mlb.com/api/v1/teams/stats"
                        f"?sportId={sport}&season={season}&group={group}"
                        f"&stats=statSplits&sitCodes={sc}")
                    lean = []
                    for s in (d.get("stats") or [{}])[0].get("splits") or []:
                        if s.get("gameType") not in (None, "R"):
                            continue
                        st = s.get("stat") or {}
                        lean.append({"team_id": (s.get("team") or {}).get("id"),
                                     "team_name": (s.get("team") or {}).get("name"),
                                     "g": st.get("gamesPlayed"),
                                     "hr": st.get("homeRuns"),
                                     "r": st.get("runs")})
                    path.write_text(json.dumps(lean, separators=(",", ":")),
                                    encoding="utf-8")
                    acct[f"{group}_{sport}_{season}_{sc}"] = len(lean)
                    print(f"  teamsplit {group}/{sport}/{season}/{sc}: "
                          f"{len(lean)} teams", flush=True)
    return acct


# ---------------------------------------------------------------------------
# factors: team-season + venue run/HR park factors -> data/milb_park_factors.json
# ---------------------------------------------------------------------------

def _load_sched(sport, season):
    path = SCHED_DIR / f"schedule_{sport}_{season}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _load_tsplit(group, sport, season, sc):
    path = TSTAT_DIR / f"teamsplit_{group}_{sport}_{season}_{sc}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def build_factors() -> dict:
    team_rows, venues = [], {}
    observed = covered_run = covered_hr = 0
    # per-season league + a team name per team from phase-B player rows (league
    # names realign across seasons, so the centering group must be season-true)
    team_league_season, team_league_any, team_names = {}, {}, {}
    for sport in SPORTS:
        for season in SEASONS:
            path = TSTAT_DIR / f"hitting_{sport}_{season}.json"
            try:
                for r in json.loads(path.read_text(encoding="utf-8")):
                    if r.get("team_id"):
                        tid = int(r["team_id"])
                        if r.get("league"):
                            team_league_season.setdefault((tid, season),
                                                          r.get("league"))
                        team_league_any.setdefault(tid, r.get("league"))
                        team_names.setdefault(tid, r.get("team_name"))
            except (OSError, ValueError):
                pass

    def _tleague(tid, season):
        return team_league_season.get((tid, season)) or team_league_any.get(tid)

    def _league_means(rmap, season):
        """Registered centering: league-season mean ratio. Fallback to the
        sport-season pooled mean when a league is unlabeled or has under
        MIN_LEAGUE_TEAMS rated teams (a-priori small-sample guard)."""
        pooled = statistics.mean(rmap.values()) if rmap else None
        by = {}
        for tid, val in rmap.items():
            by.setdefault(_tleague(tid, season), []).append(val)
        means = {lg: (statistics.mean(vs) if lg is not None
                      and len(vs) >= MIN_LEAGUE_TEAMS else pooled)
                 for lg, vs in by.items()}
        return means, pooled

    for sport in SPORTS:
        for season in SEASONS:
            games = [g for g in _load_sched(sport, season)
                     if g.get("st") in ("F", "O") and g.get("v") and g.get("h")
                     and g.get("a") and g.get("hs") is not None
                     and g.get("as") is not None]
            agg = {}
            vnames = {}
            for g in games:
                r_total = (g["hs"] or 0) + (g["as"] or 0)
                h = agg.setdefault(int(g["h"]), {"gh": 0, "rh": 0.0, "gr": 0,
                                                 "rr": 0.0, "ven": Counter()})
                h["gh"] += 1
                h["rh"] += r_total
                h["ven"][int(g["v"])] += 1
                vnames.setdefault(int(g["v"]), g.get("vn"))
                a = agg.setdefault(int(g["a"]), {"gh": 0, "rh": 0.0, "gr": 0,
                                                 "rr": 0.0, "ven": Counter()})
                a["gr"] += 1
                a["rr"] += r_total
            # HR home/away from the team split fetch (hitting HR + pitching HR
            # allowed = all HR hit at the team's venue)
            hr_h, hr_a = {}, {}
            for grp in ("hitting", "pitching"):
                for sc, sink in (("h", hr_h), ("a", hr_a)):
                    for row in _load_tsplit(grp, sport, season, sc):
                        if row.get("team_id") is None:
                            continue
                        d = sink.setdefault(int(row["team_id"]), {"g": 0, "hr": 0})
                        d["g"] = max(d["g"], int(row.get("g") or 0))
                        d["hr"] += int(row.get("hr") or 0)

            ratios, hr_ratios = {}, {}
            for tid, t in agg.items():
                observed += 1
                if t["gh"] > 0 and t["gr"] > 0 and t["rr"] > 0:
                    ratios[tid] = (t["rh"] / t["gh"]) / (t["rr"] / t["gr"])
                hh, ha = hr_h.get(tid), hr_a.get(tid)
                if hh and ha and hh["g"] > 0 and ha["g"] > 0 and ha["hr"] > 0:
                    hr_ratios[tid] = (hh["hr"] / hh["g"]) / (ha["hr"] / ha["g"])
            means_r, pooled_r = _league_means(ratios, season)
            means_h, pooled_h = _league_means(hr_ratios, season)
            for tid, t in agg.items():
                ven, vshare = None, None
                if t["ven"]:
                    ven, vcount = t["ven"].most_common(1)[0]
                    vshare = round(vcount / t["gh"], 3) if t["gh"] else None
                run_pf = hr_pf = None
                mean_r = means_r.get(_tleague(tid, season)) or pooled_r
                mean_h = means_h.get(_tleague(tid, season)) or pooled_h
                if tid in ratios and mean_r:
                    w = t["gh"] / (t["gh"] + K_G)
                    run_pf = round(1.0 + (ratios[tid] / mean_r - 1.0) * w, 4)
                    covered_run += 1
                if tid in hr_ratios and mean_h:
                    gh_s = hr_h[tid]["g"]
                    w = gh_s / (gh_s + K_G)
                    hr_pf = round(1.0 + (hr_ratios[tid] / mean_h - 1.0) * w, 4)
                    covered_hr += 1
                if ven is None or run_pf is None:
                    continue
                team_rows.append({
                    "season": season, "sport": sport,
                    "level": _level16(_tleague(tid, season) or "") if sport == 16
                             else SPORT_LEVEL[sport],
                    "team_id": tid, "team_name": team_names.get(tid),
                    "league": _tleague(tid, season),
                    "venue_id": ven, "venue_name": vnames.get(ven),
                    "venue_share": vshare,
                    "g_home": t["gh"], "g_road": t["gr"],
                    "rpg_home": round(t["rh"] / t["gh"], 3),
                    "rpg_road": round(t["rr"] / t["gr"], 3),
                    "run_pf": run_pf, "hr_pf": hr_pf})
                v = venues.setdefault(ven, {"venue_id": ven,
                                            "venue_name": vnames.get(ven),
                                            "seasons": {}})
                s = v["seasons"].setdefault(str(season),
                                            {"run_pf_w": 0.0, "hr_pf_w": 0.0,
                                             "hr_g": 0, "g_home": 0})
                s["run_pf_w"] += run_pf * t["gh"]
                s["g_home"] += t["gh"]
                if hr_pf is not None:
                    s["hr_pf_w"] += hr_pf * t["gh"]
                    s["hr_g"] += t["gh"]

    for v in venues.values():
        seas = {}
        for yr, s in v["seasons"].items():
            seas[yr] = {"run_pf": round(s["run_pf_w"] / s["g_home"], 4),
                        "g_home": s["g_home"],
                        "hr_pf": round(s["hr_pf_w"] / s["hr_g"], 4)
                                 if s["hr_g"] else None}
        v["seasons"] = seas
        v["window_run_pf"], v["window_hr_pf"] = {}, {}
        for t in SEASONS:                     # 3-season window, seasons <= t only
            rw = rg = hw = hg = 0.0
            for s in range(t - 2, t + 1):
                d = seas.get(str(s))
                if not d:
                    continue
                rw += d["run_pf"] * d["g_home"]
                rg += d["g_home"]
                if d["hr_pf"] is not None:
                    hw += d["hr_pf"] * d["g_home"]
                    hg += d["g_home"]
            if rg:
                v["window_run_pf"][str(t)] = round(rw / rg, 4)
            if hg:
                v["window_hr_pf"][str(t)] = round(hw / hg, 4)

    coverage = round(covered_run / observed, 4) if observed else 0.0
    stopd = {"observed_team_seasons": observed,
             "covered_run_pf": covered_run, "covered_hr_pf": covered_hr,
             "coverage_run_pf": coverage, "bar": STOPD_COVERAGE_BAR,
             "pass": coverage >= STOPD_COVERAGE_BAR}
    doc = {
        "generated_at": "2026-07-23",
        "experiment": "W2 PARK-LINE (docs/wills-2026-07-23/GATES.md section W2)",
        "tool": "tools/park_line_lab.py",
        "method": {
            "run_pf": ("team-season (home RS+RA per game) / (road RS+RA per game) "
                       "from StatsAPI schedule final scores, regular season only; "
                       "centered on the unweighted LEAGUE-season mean ratio "
                       "(registered centering; sport-season pooled fallback when "
                       f"a league is unlabeled or has under {MIN_LEAGUE_TEAMS} "
                       "rated teams); "
                       f"EB-shrunk toward 1.0 with K_G={K_G} home games; venue = "
                       "modal home venue; venue-season = home-game-weighted mean; "
                       "3-season venue window uses only seasons <= t (vintage-safe)"),
            "hr_pf": ("team home/away HR per game from the league-wide team "
                      "statSplits fetch (hitting HR + pitching HR allowed = all HR "
                      "at the venue), same centering/shrink/window. hr_pf feeds NO "
                      "frozen eFV formula (iso/slg neutralize via run_pf); it is "
                      "carried for display/audit and clamped [0.80, 1.25] on read"),
            "application_clamps": {"run_pf": [RUN_PF_LO, RUN_PF_HI],
                                   "hr_pf": [HR_PF_LO, HR_PF_HI]},
            "sports": list(SPORTS), "seasons": [SEASONS[0], SEASONS[-1]],
            "note_2026": "2026 is in season; its factors use partial schedules "
                         "plus the 2024-2025 window legs",
        },
        "stop_d": stopd,
        "team_seasons": team_rows,
        "venues": sorted(venues.values(), key=lambda v: v["venue_id"]),
    }
    PF_PATH.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {PF_PATH} team_seasons={len(team_rows)} venues={len(venues)} "
          f"coverage={coverage} stopd_pass={stopd['pass']}", flush=True)
    return stopd


# ---------------------------------------------------------------------------
# clause M: park-neutralized current-season rate predicts next-season raw rate
# ---------------------------------------------------------------------------

def _primary_rows(group: str, season: int) -> dict:
    """{mlbam: row} = each player's maximum-exposure line for the season.
    The player-season qualifies only when that primary line is numTeams==1
    (single dominant affiliate, share 1.00 >= 0.70) and clears the exposure
    floor (hit >= 100 PA, pit >= 40 IP)."""
    best = {}
    for sport in SPORTS:
        path = TSTAT_DIR / f"{group}_{sport}_{season}.json"
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows:
            mid = r.get("mlbam")
            if not mid:
                continue
            exp = (_f(r.get("pa")) if group == "hitting" else _f(r.get("bf"))) or 0.0
            cur = best.get(int(mid))
            if cur is None or exp > cur[0]:
                best[int(mid)] = (exp, r)
    out = {}
    for mid, (exp, r) in best.items():
        if (r.get("num_teams") or 1) > 1 or not r.get("team_id"):
            continue
        if group == "hitting":
            if (_f(r.get("pa")) or 0) < HIT_PA_FLOOR:
                continue
            rate = _f(r.get("ops"))
        else:
            if (_ip_float(r.get("ip")) or 0) < PIT_IP_FLOOR:
                continue
            rate = _f(r.get("era"))
        if rate is None:
            continue
        out[mid] = {"team_id": int(r["team_id"]), "rate": rate,
                    "level": r.get("level")}
    return out


def clause_m() -> dict:
    import efv_park_line as pl
    pl._pf_maps.cache_clear()
    results = {}
    for side, group in (("hit", "hitting"), ("pit", "pitching")):
        pairs = []                    # (mlbam, neut_t, raw_t, raw_next)
        excluded_no_pf = 0
        season_rows = {s: _primary_rows(group, s) for s in SEASONS}
        for t in SEASONS[:-1]:
            cur, nxt = season_rows[t], season_rows[t + 1]
            for mid, c in cur.items():
                n = nxt.get(mid)
                if n is None:
                    continue
                pf = pl.venue_run_pf(c["team_id"], t)
                if pf is None:
                    excluded_no_pf += 1
                    continue
                applied = (pf + 1.0) / 2.0
                neut = (c["rate"] / (applied ** 0.5) if side == "hit"
                        else c["rate"] / applied)
                pairs.append((mid, neut, c["rate"], n["rate"]))
        n_pairs = len(pairs)
        players = sorted({p[0] for p in pairs})
        by_player = {}
        for i, p in enumerate(pairs):
            by_player.setdefault(p[0], []).append(i)
        rho_neut = _spearman([p[1] for p in pairs], [p[3] for p in pairs])
        rho_raw = _spearman([p[2] for p in pairs], [p[3] for p in pairs])
        delta = (round(rho_neut - rho_raw, 4)
                 if rho_neut is not None and rho_raw is not None else None)
        rng = random.Random(SEED)
        deltas = []
        for _ in range(BOOT_REPS):
            idx = []
            for _ in range(len(players)):
                idx.extend(by_player[players[rng.randrange(len(players))]])
            rn = _spearman([pairs[i][1] for i in idx], [pairs[i][3] for i in idx])
            rr = _spearman([pairs[i][2] for i in idx], [pairs[i][3] for i in idx])
            if rn is not None and rr is not None:
                deltas.append(rn - rr)
        deltas.sort()
        lo95 = deltas[int(0.025 * len(deltas))] if deltas else None
        hi95 = deltas[int(0.975 * len(deltas)) - 1] if deltas else None
        p_gt0 = (sum(1 for d in deltas if d > 0) / len(deltas)) if deltas else None
        results[side] = {
            "metric": "OPS" if side == "hit" else "ERA",
            "n_pairs": n_pairs, "n_players": len(players),
            "excluded_no_pf": excluded_no_pf,
            "rho_raw": rho_raw, "rho_neut": rho_neut, "delta": delta,
            "boot": {"reps": BOOT_REPS, "seed": SEED,
                     "clustering": "player (mlbam)",
                     "lo95": round(lo95, 4) if lo95 is not None else None,
                     "hi95": round(hi95, 4) if hi95 is not None else None,
                     "p_gt0": round(p_gt0, 4) if p_gt0 is not None else None},
            "bar": "delta lo95 > 0",
            "pass": lo95 is not None and lo95 > 0,
        }
        print(f"  clause M {side}: n={n_pairs} rho_raw={rho_raw} "
              f"rho_neut={rho_neut} delta={delta} lo95={results[side]['boot']['lo95']} "
              f"-> {'PASS' if results[side]['pass'] else 'FAIL'}", flush=True)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    (CKPT_DIR / "clause_m.json").write_text(json.dumps(results, indent=1),
                                            encoding="utf-8")
    return results


# ---------------------------------------------------------------------------
# gate: clauses 1-3 on the actual training matrices
# ---------------------------------------------------------------------------

def _flag_env(side: str, val: str | None):
    key = "EEPHUS_PARKLINE_PIT" if side == "pit" else "EEPHUS_PARKLINE_HIT"
    if val is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = val


def _build_matrix(side: str):
    import efv_dataset
    import efv_park_line
    efv_park_line._pf_maps.cache_clear()
    efv_park_line._affiliate_index.cache_clear()
    efv_dataset.run(True, side)
    return json.loads(efv_dataset.matrix_path(side).read_text(encoding="utf-8"))


def _pooled(ev):
    block = (ev.get("evals") or ev).get("debuted_km") or {}
    try:
        return float(block["pooled_oos"]["blend"]["spearman"])
    except (KeyError, TypeError, ValueError):
        return None


def _covered_mlbams(group: str) -> set:
    """mlbam ids with at least one (season 2021+, level) line resolving to a
    dominant affiliate with a mapped venue factor."""
    import efv_park_line as pl
    out = set()
    for season in SEASONS:
        for (mid, _lv), team in pl._affiliate_index(season, group).items():
            if pl.venue_run_pf(team, season) is not None:
                out.add(mid)
    return out


# fields the neutralization may legitimately move (everything else must be
# byte-identical even on covered rows)
_ALLOWED_HIT = {"iso_rel", "obp_rel", "ops_rel", "peak_iso_rel", "peak_obp_rel",
                "peak_ops_rel", "prod_trend"}
_ALLOWED_PIT = {"era_rel"}


def _eval_side(side: str) -> dict:
    import efv_model
    baseline_matrix = CKPT_DIR / f"baseline_{side}_matrix.json"

    _flag_env(side, "0")
    off_rows = _build_matrix(side)
    import efv_dataset
    off_bytes = efv_dataset.matrix_path(side).read_bytes()
    committed_identical = None
    if baseline_matrix.exists():
        committed_identical = off_bytes == baseline_matrix.read_bytes()
    off_rho = _pooled(efv_model.run(persist=False, side=side))

    _flag_env(side, "1")
    on_rows = _build_matrix(side)
    on_rho = _pooled(efv_model.run(persist=False, side=side))
    _flag_env(side, None)

    group = "pitching" if side == "pit" else "hitting"
    covered = _covered_mlbams(group)
    allowed = _ALLOWED_PIT if side == "pit" else _ALLOWED_HIT
    off_by = {r.get("player_key"): r for r in off_rows}
    on_by = {r.get("player_key"): r for r in on_rows}
    violations, changed, max_pull = 0, [], {}
    for pk, a in off_by.items():
        b = on_by.get(pk)
        if b is None:
            violations += 1
            continue
        if json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True):
            continue
        ma, mb = (a.get("milb") or {}), (b.get("milb") or {})
        diff_keys = {k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k)}
        top_a = {k: v for k, v in a.items() if k != "milb"}
        top_b = {k: v for k, v in b.items() if k != "milb"}
        mid = a.get("mlbam_id")
        ok = (top_a == top_b and diff_keys <= allowed
              and mid is not None and int(mid) in covered)
        if not ok:
            violations += 1
            continue
        deltas = {k: round((mb.get(k) or 0.0) - (ma.get(k) or 0.0), 5)
                  for k in sorted(diff_keys)}
        for k, v in deltas.items():
            max_pull[k] = max(max_pull.get(k, 0.0), abs(v))
        changed.append({"player_key": pk, "kind": a.get("kind"),
                        "milb_season": ma.get("milb_season"),
                        "deltas": deltas})
    extra_on = set(on_by) - set(off_by)
    violations += len(extra_on)

    clause1_pass = violations == 0 and committed_identical is not False
    delta2 = (round(on_rho - off_rho, 4)
              if on_rho is not None and off_rho is not None else None)
    clause2_pass = delta2 is not None and delta2 >= POOL_BAR

    import efv_park_line as pl
    clamps_ok = (pl.RUN_PF_LO == RUN_PF_LO and pl.RUN_PF_HI == RUN_PF_HI
                 and pl.HR_PF_LO == HR_PF_LO and pl.HR_PF_HI == HR_PF_HI)
    # a-priori worst-case pulls implied by the clamps (documentation values)
    era_ratio_bounds = [round(1 / 1.05, 4), round(1 / 0.95, 4)]
    hit_ratio_bounds = [round(1 / (1.05 ** 0.5), 4), round(1 / (0.95 ** 0.5), 4)]

    return {
        "side": side,
        "clause_1_invariance": {
            "off_byte_identical_to_committed": committed_identical,
            "uncovered_row_violations": violations,
            "n_changed_rows": len(changed),
            "n_rows": len(off_rows),
            "pass": clause1_pass},
        "clause_2_no_harm": {
            "off_pooled_rho": off_rho, "on_pooled_rho": on_rho,
            "delta": delta2, "bar": POOL_BAR, "pass": clause2_pass},
        "clause_3_bounded_pull": {
            "clamps_in_code": {"run_pf": [pl.RUN_PF_LO, pl.RUN_PF_HI],
                               "hr_pf": [pl.HR_PF_LO, pl.HR_PF_HI]},
            "registered": {"run_pf": [RUN_PF_LO, RUN_PF_HI],
                           "hr_pf": [HR_PF_LO, HR_PF_HI]},
            "clamps_match": clamps_ok,
            "era_ratio_bounds_implied": era_ratio_bounds,
            "hit_rate_ratio_bounds_implied": hit_ratio_bounds,
            "max_abs_feature_delta": {k: round(v, 5)
                                      for k, v in sorted(max_pull.items())},
            "pass": clamps_ok},
        "changed_rows_sample": changed[:12],
    }


def gate() -> dict:
    try:
        clause_m_res = json.loads((CKPT_DIR / "clause_m.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        clause_m_res = clause_m()
    try:
        stopd = (json.loads(PF_PATH.read_text(encoding="utf-8"))
                 .get("stop_d") or {})
    except (OSError, ValueError):
        stopd = {}

    sides = {}
    for side in ("hit", "pit"):
        print(f"=== W2 gate: {side} ===", flush=True)
        sides[side] = _eval_side(side)
        s = sides[side]
        print(f"  c1 pass={s['clause_1_invariance']['pass']} "
              f"(committed_identical={s['clause_1_invariance']['off_byte_identical_to_committed']}, "
              f"violations={s['clause_1_invariance']['uncovered_row_violations']}, "
              f"changed={s['clause_1_invariance']['n_changed_rows']}) "
              f"c2 delta={s['clause_2_no_harm']['delta']} "
              f"pass={s['clause_2_no_harm']['pass']} "
              f"c3 pass={s['clause_3_bounded_pull']['pass']}", flush=True)

    factors_clean = bool(stopd.get("pass"))
    verdicts = {}
    for side in ("hit", "pit"):
        m_ok = clause_m_res.get(side, {}).get("pass")
        all_ok = (m_ok and sides[side]["clause_1_invariance"]["pass"]
                  and sides[side]["clause_2_no_harm"]["pass"]
                  and sides[side]["clause_3_bounded_pull"]["pass"])
        if all_ok:
            verdicts[side] = "PASS"
        elif not m_ok and factors_clean:
            # registered fallback class: factors built cleanly, measurement
            # clause missed -> factor table ships display-only, layer stays OFF
            verdicts[side] = "M-FAIL-DISPLAY-CANDIDATE"
        else:
            verdicts[side] = "FAIL"
    if not stopd.get("pass", True):
        verdicts = {"hit": "STOP-D", "pit": "STOP-D"}
    results = {
        "generated_at": "2026-07-23",
        "experiment": {
            "name": "W2 PARK-LINE: in-house MiLB park factors + measurement "
                    "blend into eFV rates",
            "registration": "docs/wills-2026-07-23/GATES.md section W2",
            "tool": "tools/park_line_lab.py",
            "seed": SEED, "bootstrap_reps": BOOT_REPS,
            "flags": {"EEPHUS_PARKLINE_HIT": "default OFF",
                      "EEPHUS_PARKLINE_PIT": "default OFF"},
            "factor_artifact": "data/milb_park_factors.json",
        },
        "stop_d": {"bar": f"run-PF coverage >= {STOPD_COVERAGE_BAR} of observed "
                          "team-seasons; endpoint sub-phases must not fail",
                   "measured": stopd},
        "clause_m_measurement": clause_m_res,
        "sides": sides,
        "verdict": verdicts,
    }
    if any(v != "PASS" for v in verdicts.values()):
        results["loss_ledger"] = {
            "mechanism_story": (
                "The in-house factor table itself built cleanly (coverage "
                f"{stopd.get('coverage_run_pf')}) - the failure mode, where "
                "present, is the measurement clause: a half-weighted, "
                "sqrt-damped one-park correction on a single MiLB season is "
                "small relative to season-to-season rate noise, promotion "
                "level changes, and league re-centering, which the eFV "
                "pipeline already handles via contemporaneous level norms. "
                "Neutralizing the current-season rate must ADD forward signal "
                "on top of that machinery to clear the bar."),
            "display_only_ship": (
                "Registered fallback (GATES.md W2): on M FAIL with a clean "
                "factor build, data/milb_park_factors.json ships DISPLAY-ONLY "
                "as a product option (changes no served model number)."
                if factors_clean else None),
        }
    else:
        results["reading"] = {
            "mechanism_story": (
                "Park-neutralized current-season rates carry more forward "
                "signal than raw rates for the covered pool, and the "
                "measurement layer moves training features only inside the "
                "registered clamps with no OOS harm - the S-XLINE pattern "
                "extended one environment layer deeper (venue instead of "
                "expected-stat gap)."),
        }
    EVAL_PATH.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {EVAL_PATH} verdict={verdicts}", flush=True)

    # restore matrices to the module-default (OFF) state (the S-XLINE lab
    # hygiene: never leave ON-state matrices on disk)
    for side in ("hit", "pit"):
        _build_matrix(side)
    print("matrices restored to module-default (OFF) state", flush=True)
    return results


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("fetch", "all"):
        print("=== fetch: schedules ===", flush=True)
        fetch_schedules()
        print("=== fetch: player team stats ===", flush=True)
        fetch_team_stats()
        print("=== fetch: team h/a splits ===", flush=True)
        fetch_team_splits()
    if cmd in ("factors", "all"):
        print("=== factors ===", flush=True)
        build_factors()
    if cmd in ("clausem", "all"):
        print("=== clause M ===", flush=True)
        clause_m()
    if cmd in ("gate", "all"):
        gate()


if __name__ == "__main__":
    main()
