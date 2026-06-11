# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ETA backtest (model-audit Phase 4b, WS-8) — the heuristic's FIRST-EVER
scoring against actual debut dates.

The ETA model (eta.estimate_eta, heuristic v38) has shipped on every
PROSPX prospect since v1 with zero validation; the registry has carried
it `unvalidated` since Phase 0 precisely so this backtest couldn't be
skipped. Protocol mirrors surplus_backtest_real.py's vintage discipline:

  COHORT     per (player, vintage year Y in 2018-2023): players with an
             FV snapshot in year Y who had NOT debuted before that
             snapshot. FV = median of each source's earliest same-year
             snapshot (the platform's standard vintage consensus).
  INPUTS AT  level   = highest level reached through season Y-1 (the
  VINTAGE              vintage snapshot is almost always preseason, so
                       season-Y stats don't exist yet). Debuted players
                       resolve through milb_history (StatsAPI ladder,
                       mlbam from debuts.json) — career_stats payloads
                       only reach back to graduation and reconstruct
                       almost nothing (measured: 654/2,332 for 2018-20
                       vintages). Non-debuted players keep the
                       career_stats fallback; they only drive the
                       censoring accounting, never the MAE.
             stats   = the player's season-(Y-1) line at that level
                       (ops for hitters / era for pitchers).
             age     = decimal age at the snapshot date.
             norms   = the STATIC fallback tables (empirical level
                       norms are computed from a rolling 2-season
                       window at export time and cannot be
                       reconstructed per vintage — documented).
             NOT reconstructable (documented, unscored): Statcast+,
             health/IL state, org promotion tendencies. The backtest
             scores the core level+perf+age+FV heuristic.
  PREDICTED  vintage year + the model's years-to-debut (estimate_eta
             anchors at today; predicted years = eta_year − this year).
  ACTUAL     debut year from debuts.json (tracked debut_date), falling
             back to the first career_war / career_stats MLB season.
  OUTCOMES   debuted      → scored (error in calendar years)
             active, not debuted → censored; counted OVERDUE when the
                            predicted year has already passed (lower-
                            bound miss, excluded from MAE)
             washed out   → no pro activity since 2024 and never
                            debuted; ETA has no "never" state, so these
                            are counted, never scored in years
  BASELINE   the naive level→years table (eta.BASE_YEARS, unadjusted,
             rounded) — "level only, no model".
  CHALLENGER empirical per-level years table fitted FORWARD-CHAINED
             (per vintage Y: median realized years-to-debut by level
             over debuted cohort members from vintages < Y). This is
             the recalibration candidate the plan calls for; it ships
             into the live path only if it beats the heuristic here.

Selection caveat (stated, not hidden): debuted-only MAE conditions on
players who DID debut — predictions for busts are unscoreable in
calendar years. Champion, baseline and challenger all share the
selection, so the comparison is fair even though the absolute MAE reads
optimistic. Overdue + washed-out rates carry the unconditional signal.

Artifact: data/eta_eval.json. Reruns monthly (cheap, cache-only).
Run: python eta_backtest.py
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path

import milb_history as mh
import storage
from eta import BASE_YEARS, estimate_eta

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "eta_eval.json"
DEBUTS_PATH = DATA_DIR / "debuts.json"

VINTAGE_YEARS = (2018, 2019, 2020, 2021, 2022, 2023)
# The hand-set v38 base table FROZEN at audit time (2026-06-11) — the
# permanent comparator. eta.BASE_YEARS itself moved to the KM-fitted v39
# values when this backtest's ship decision landed, so monthly reruns
# score the LIVE table as champion and this frozen copy as the legacy
# reference (otherwise the ship would erase its own before/after).
V38_BASE_YEARS = {"MLB": 0.0, "AAA": 0.5, "AA": 2.0, "A+": 3.5,
                  "A": 5.0, "CPX": 6.5, "DSL": 7.5}
# Last season whose debuts are fully known (2026 is in progress); a
# prediction that has "come due" is only judged overdue against this.
LAST_FULL_SEASON = 2025
# No professional activity in/after this season + never debuted = washed
# out (same convention as surplus_backtest_real).
WASHED_BEFORE = 2024

_LEVEL_ORDER = ["DSL", "FRk", "Rk", "ROK", "CPX", "A-", "A", "A+", "AA", "AAA"]
# Levels the ETA model knows; historical short-season/rookie labels fold in.
_LEVEL_MAP = {"A-": "A", "Rk": "CPX", "ROK": "CPX", "FRk": "CPX"}


def _age_at(birth_date: str | None, asof: str) -> float | None:
    if not birth_date:
        return None
    try:
        b = date.fromisoformat(birth_date[:10])
        a = date.fromisoformat(asof[:10])
    except ValueError:
        return None
    return round((a - b).days / 365.25, 1)


def _load_inputs() -> tuple[dict, dict, dict, dict]:
    """(listings, career_levels, bio, debut_year_by_key).
    listings: {(player_key, Y): {fv, date, n_sources}} — median of each
    source's earliest same-year FV snapshot, the platform convention."""
    with storage.connect() as con:
        rows = con.execute("""
            SELECT player_key, source, substr(snapshot_date,1,4) AS y,
                   MIN(snapshot_date) AS d
            FROM snapshots WHERE fv IS NOT NULL
              AND substr(snapshot_date,1,4) IN ({})
            GROUP BY player_key, source, y""".format(
            ",".join(f"'{y}'" for y in VINTAGE_YEARS))).fetchall()
        fv_at: dict[tuple, list] = {}
        for r in rows:
            fv = con.execute(
                "SELECT fv FROM snapshots WHERE player_key=? AND source=? AND snapshot_date=?",
                (r["player_key"], r["source"], r["d"])).fetchone()
            if fv and fv[0] is not None:
                fv_at.setdefault((r["player_key"], int(r["y"])), []).append(
                    (float(fv[0]), r["d"]))
        listings = {}
        for key, vals in fv_at.items():
            listings[key] = {"fv": statistics.median(v for v, _ in vals),
                             "date": min(d for _, d in vals),
                             "n_sources": len(vals)}
        cs = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_stats"):
            try:
                cs[r["player_key"]] = json.loads(r["payload_json"])
            except ValueError:
                continue
        bio = {r["player_key"]: dict(r) for r in con.execute(
            "SELECT player_key, position, is_pitcher, birth_date FROM players")}
        cw_first: dict[str, int] = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            if seasons:
                cw_first[r["player_key"]] = min(int(y) for y in seasons)
    debut_year: dict[str, int] = {}
    ident: dict[str, dict] = {}
    try:
        for d in json.loads(DEBUTS_PATH.read_text(encoding="utf-8")):
            dd = d.get("debut_date")
            if d.get("player_key") and dd:
                debut_year[d["player_key"]] = int(dd[:4])
                ident[d["player_key"]] = {"mlbam": d.get("mlbam_id"),
                                          "position": d.get("position"),
                                          "debut_date": dd}
    except (OSError, ValueError):
        log.warning("eta_backtest: debuts.json unavailable")
    # career_war first season / career_stats MLB rows fill gaps
    for k, y in cw_first.items():
        debut_year.setdefault(k, y)
    for k, rows_ in cs.items():
        mlb = [int(r["season"]) for r in (rows_ or [])
               if r.get("level") == "MLB" and r.get("season")]
        if mlb:
            debut_year[k] = min(debut_year.get(k, 9999), min(mlb))
    return listings, cs, bio, debut_year, ident


def _highest_level_through(rows: list[dict], year: int) -> str | None:
    best = None
    for r in rows or []:
        if not r.get("season") or int(r["season"]) > year or r.get("level") == "MLB":
            continue
        lv = r.get("level")
        if lv in _LEVEL_ORDER:
            if best is None or _LEVEL_ORDER.index(lv) > _LEVEL_ORDER.index(best):
                best = lv
    return best


def _season_stats(rows: list[dict], season: int, level: str | None) -> dict | None:
    """The season row at the player's then-highest level (raw label)."""
    cands = [r for r in rows or []
             if r.get("season") and int(r["season"]) == season
             and r.get("level") == level]
    return cands[0] if cands else None


def _last_activity(rows: list[dict]) -> int | None:
    seasons = [int(r["season"]) for r in (rows or []) if r.get("season")]
    return max(seasons) if seasons else None


def _is_pitcher_pos(position: str | None) -> bool:
    return (position or "").upper() in ("P", "SP", "RP", "LHP", "RHP", "TWP")


def _vintage_inputs_statsapi(mlbam: int, position: str | None,
                             vy: int) -> tuple[str | None, dict | None, bool]:
    """(level, stats, is_pitcher) at the vintage from the StatsAPI
    ladder: season-(Y-1) highest MiLB level + that line; when the player
    didn't play in Y-1, the most recent earlier season's level, no stats
    (mirrors live semantics: 'current level' preseason = last season's)."""
    groups = ("pitching", "hitting") if _is_pitcher_pos(position) else ("hitting", "pitching")
    for group in groups:
        for season in range(vy - 1, 2013, -1):
            rows = [r for r in (mh.player_index(season, group).get(mlbam) or [])
                    if r.get("level") != "MLB"]
            if not rows:
                continue
            level = mh.highest_level(rows)
            srow = mh.level_row(rows, level, group) if season == vy - 1 else None
            return level, srow, group == "pitching"
    return None, None, _is_pitcher_pos(position)


def build_cohort() -> tuple[list[dict], dict]:
    """One row per scoreable (player, vintage) + honest accounting."""
    listings, cs, bio, debut_year, ident = _load_inputs()
    today_year = date.today().year
    rows: list[dict] = []
    acct = {"listed": 0, "excluded_post_debut": 0, "excluded_no_bio": 0,
            "no_level_age_fallback": 0, "level_from_statsapi": 0,
            "level_from_career_stats": 0,
            "debuted": 0, "censored_active": 0, "washed_out": 0,
            "overdue": 0}
    for (key, vy), li in sorted(listings.items()):
        acct["listed"] += 1
        b = bio.get(key)
        if not b:
            acct["excluded_no_bio"] += 1
            continue
        actual = debut_year.get(key)
        info = ident.get(key) or {}
        # pre-debut at the vintage snapshot only (debut DATE when known)
        dd = info.get("debut_date")
        if actual is not None and (actual < vy or (dd or "") < li["date"] and dd):
            acct["excluded_post_debut"] += 1
            continue
        stats_rows = cs.get(key) or []
        level = srow = None
        is_pitcher = bool(b.get("is_pitcher"))
        if info.get("mlbam"):
            level, srow, is_pitcher = _vintage_inputs_statsapi(
                int(info["mlbam"]), info.get("position") or b.get("position"), vy)
            if level is not None:
                acct["level_from_statsapi"] += 1
        if level is None:
            raw_level = _highest_level_through(stats_rows, vy - 1)
            level = _LEVEL_MAP.get(raw_level or "", raw_level)
            srow = _season_stats(stats_rows, vy - 1, raw_level)
            if srow:
                is_pitcher = bool(srow.get("is_pitcher"))
            if level is not None:
                acct["level_from_career_stats"] += 1
        age = _age_at(b.get("birth_date"), li["date"])
        if level is None:
            acct["no_level_age_fallback"] += 1
        res = estimate_eta(
            current_level=level, age=age, is_pitcher=is_pitcher,
            fv=li["fv"], stats=srow, snapshot_date=li["date"])
        if res.eta_year is None:
            continue
        pred = vy + (res.eta_year - today_year)
        naive = (vy + round(V38_BASE_YEARS[level])) if level in V38_BASE_YEARS else None
        row = {"player_key": key, "vintage": vy, "fv": li["fv"],
               "level": level, "age": age, "is_pitcher": is_pitcher,
               "pred": pred, "naive": naive, "actual": actual,
               "srow": srow, "date": li["date"]}
        if actual is not None:
            acct["debuted"] += 1
            row["outcome"] = "debuted"
        else:
            last = _last_activity(stats_rows)
            if last is not None and last >= WASHED_BEFORE:
                acct["censored_active"] += 1
                row["outcome"] = "censored_active"
                if pred <= LAST_FULL_SEASON:
                    acct["overdue"] += 1
                    row["overdue"] = True
            else:
                acct["washed_out"] += 1
                row["outcome"] = "washed_out"
        rows.append(row)
    return rows, acct


def _score(pairs: list[tuple[int, int]]) -> dict:
    """MAE / bias / within-1 over (predicted, actual) debut years."""
    if not pairs:
        return {"n": 0}
    errs = [p - a for p, a in pairs]
    return {"n": len(pairs),
            "mae": round(sum(abs(e) for e in errs) / len(errs), 3),
            "bias": round(sum(errs) / len(errs), 3),
            "within_1y": round(sum(1 for e in errs if abs(e) <= 1) / len(errs), 3),
            "exact": round(sum(1 for e in errs if e == 0) / len(errs), 3)}


def _empirical_table(train: list[dict]) -> dict[str, float]:
    """Median realized years-to-debut by vintage level (debuted only) —
    the SURVIVOR-BIASED table, scored for reference, never shipped."""
    by_level: dict[str, list[int]] = {}
    for r in train:
        if r["outcome"] == "debuted" and r["level"]:
            by_level.setdefault(r["level"], []).append(r["actual"] - r["vintage"])
    return {lv: statistics.median(v) for lv, v in by_level.items() if len(v) >= 10}


def _km_median(pool: list[dict], max_t: int = 12) -> float | None:
    """Kaplan-Meier median years-to-debut with cure handling: debuts are
    events; still-active non-debuted players censor at their observed
    follow-up; WASHED-OUT players never leave the risk set (they are
    known never-debuts, the 'cure' mass that keeps a survivor table from
    lying about busts). Fractional via within-year linear interpolation;
    None when the curve never crosses 0.5 (cure fraction too large)."""
    if not pool:
        return None
    events: dict[int, int] = {}
    censor: dict[int, int] = {}
    for r in pool:
        if r["outcome"] == "debuted":
            t = max(0, r["actual"] - r["vintage"])
            events[t] = events.get(t, 0) + 1
        elif r["outcome"] == "censored_active":
            t = max(0, date.today().year - r["vintage"])
            censor[t] = censor.get(t, 0) + 1
        # washed_out: permanent risk-set member
    s_prev, at_risk = 1.0, len(pool)
    for t in range(0, max_t + 1):
        d = events.get(t, 0)
        s = s_prev * (1 - d / at_risk) if at_risk > 0 else s_prev
        if s <= 0.5 < s_prev:
            frac = (s_prev - 0.5) / (s_prev - s) if s_prev > s else 0.0
            return round(t + frac, 2)
        at_risk -= d + censor.get(t, 0)
        s_prev = s
    return None


def _km_table(train: list[dict], min_n: int = 50) -> dict[str, float]:
    """Censoring-aware base-years candidates by level, rounded to 0.25
    (the heuristic's adjustment granularity). Levels that never cross
    50% debut probability (DSL) or are too thin keep no entry — the
    incumbent base survives there."""
    out = {}
    for lv in BASE_YEARS:
        pool = [r for r in train if r["level"] == lv]
        if len(pool) < min_n:
            continue
        m = _km_median(pool)
        if m is not None:
            out[lv] = round(m * 4) / 4
    return out


def _heuristic_rescore(rows: list[dict], base_tables: dict[int, dict],
                       today_year: int) -> dict[int, dict[str, int]]:
    """Re-run estimate_eta per row with the vintage's candidate base
    table (forward-chained). {id(row): pred} keyed by row index."""
    preds: dict[int, int] = {}
    for i, r in enumerate(rows):
        table = base_tables.get(r["vintage"])
        if not table or r["level"] not in table:
            continue
        merged = dict(BASE_YEARS) | table
        res = estimate_eta(current_level=r["level"], age=r["age"],
                           is_pitcher=r["is_pitcher"], fv=r["fv"],
                           stats=r.get("srow"), snapshot_date=r.get("date"),
                           base_years=merged)
        if res.eta_year is not None:
            preds[i] = r["vintage"] + (res.eta_year - today_year)
    return preds


def run(persist: bool = True) -> dict:
    rows, acct = build_cohort()
    deb = [r for r in rows if r["outcome"] == "debuted"]

    champion = _score([(r["pred"], r["actual"]) for r in deb])
    naive_rows = [r for r in deb if r["naive"] is not None]
    baseline = _score([(r["naive"], r["actual"]) for r in naive_rows])
    champion_on_naive_rows = _score([(r["pred"], r["actual"]) for r in naive_rows])

    # forward-chained challengers. C1 = survivor-median table (reference
    # only — fitted on debuted players, biased fast, never shippable).
    # C2 = the heuristic with KM-recalibrated bases (the candidate): the
    # full live code path, only BASE_YEARS swapped per vintage for the
    # censoring-aware Kaplan-Meier medians fitted on vintages < Y.
    chall_pairs = []
    tables_by_vintage = {}
    km_by_vintage: dict[int, dict] = {}
    for vy in VINTAGE_YEARS:
        train = [r for r in rows if r["vintage"] < vy]
        table = _empirical_table(train)
        if table:
            tables_by_vintage[vy] = table
        km = _km_table(train)
        if km:
            km_by_vintage[vy] = km
        for r in deb:
            if r["vintage"] == vy and r["level"] in table:
                chall_pairs.append((vy + round(table[r["level"]]), r["actual"]))
    challenger = _score(chall_pairs)

    today_year = date.today().year
    # frozen v38 comparator (the pre-ship hand-set bases) on all rows
    v38_tables = {vy: V38_BASE_YEARS for vy in VINTAGE_YEARS}
    v38_preds = _heuristic_rescore(rows, v38_tables, today_year)

    km_preds = _heuristic_rescore(rows, km_by_vintage, today_year)
    idx_deb = [i for i, r in enumerate(rows)
               if r["outcome"] == "debuted" and i in km_preds and i in v38_preds]
    km_chall = _score([(km_preds[i], rows[i]["actual"]) for i in idx_deb])
    v38_on_km_rows = _score([(v38_preds[i], rows[i]["actual"])
                             for i in idx_deb])

    # the SHIPPABLE table: full-window KM fit (what goes live if C2 wins)
    km_final = _km_table(rows)
    final_tables = {vy: km_final for vy in VINTAGE_YEARS}
    final_preds = _heuristic_rescore(rows, final_tables, today_year)
    overdue_after = sum(
        1 for i, r in enumerate(rows)
        if r["outcome"] == "censored_active"
        and final_preds.get(i, r["pred"]) <= LAST_FULL_SEASON)
    overdue_v38 = sum(
        1 for i, r in enumerate(rows)
        if r["outcome"] == "censored_active"
        and v38_preds.get(i, r["pred"]) <= LAST_FULL_SEASON)

    by_level = {lv: _score([(r["pred"], r["actual"]) for r in deb if r["level"] == lv])
                for lv in sorted({r["level"] for r in deb if r["level"]},
                                 key=lambda l: _LEVEL_ORDER.index(l) if l in _LEVEL_ORDER else 99)}
    by_vintage = {vy: _score([(r["pred"], r["actual"]) for r in deb if r["vintage"] == vy])
                  for vy in VINTAGE_YEARS}
    # full-pool per-level residuals — the recalibration diagnostic
    resid_by_level = {}
    for lv in by_level:
        errs = [r["pred"] - r["actual"] for r in deb if r["level"] == lv]
        resid_by_level[lv] = {"n": len(errs),
                              "mean": round(statistics.mean(errs), 3),
                              "median": statistics.median(errs)}

    censored = [r for r in rows if r["outcome"] == "censored_active"]
    washed = [r for r in rows if r["outcome"] == "washed_out"]
    out = {
        "generated_at": date.today().isoformat(),
        "vintage_years": list(VINTAGE_YEARS),
        "accounting": acct,
        "conventions": {
            "vintage_fv": "median of each source's earliest same-year snapshot",
            "inputs": "level/stats = season Y-1 at then-highest level (A- -> A, Rk/ROK/FRk -> CPX); age at snapshot date; STATIC norm tables",
            "unscored_live_signals": "statcast_plus, health/IL, org promotion tendencies (not reconstructable per vintage)",
            "actual": "debuts.json debut_date, else first career_war / career_stats MLB season",
            "selection": "MAE conditions on debuted players (shared by champion/baseline/challenger); overdue + washed-out rates carry the unconditional signal",
        },
        "champion_heuristic": champion,
        "baseline_naive_level_table": baseline,
        "champion_on_baseline_rows": champion_on_naive_rows,
        "challenger_empirical_table_forward_chained": challenger,
        "challenger_km_recalibrated_heuristic": km_chall,
        "v38_frozen_on_km_rows": v38_on_km_rows,
        "km_base_years_full_window": km_final,
        "live_base_years": {k: v for k, v in BASE_YEARS.items() if k != "MLB"},
        "v38_frozen_base_years": {k: v for k, v in V38_BASE_YEARS.items()
                                  if k != "MLB"},
        "overdue_v38_vs_km": {
            "v38": overdue_v38,
            "km_recalibrated": overdue_after,
            "censored_n": acct["censored_active"],
        },
        "ship_decision": {
            "date": "2026-06-11",
            "decision": "SHIP — eta.BASE_YEARS recalibrated to the "
                        "censoring-aware KM medians (v39); DSL keeps the "
                        "hand-set 7.5 (curve never crosses 50% debut "
                        "probability — cure fraction dominates)",
            "criteria": "forward-chained debuted MAE and within-1y must "
                        "beat the v38 bases on identical rows; overdue "
                        "shift disclosed (conditional-accuracy trade, "
                        "accepted: KM is censoring-aware, not a survivor "
                        "median)",
            "measured_2026_06_11": {
                "km_recalibrated": {"mae": 1.448, "within_1y": 0.571},
                "v38_incumbent": {"mae": 1.993, "within_1y": 0.405},
                "rows": 2778,
                "overdue": {"v38": 803, "km": 904, "censored_n": 2345},
            },
        },
        "by_level": by_level,
        "by_vintage": {str(k): v for k, v in by_vintage.items()},
        "residual_by_level": resid_by_level,
        "censoring": {
            "censored_active": len(censored),
            "overdue_rate": round(sum(1 for r in censored if r.get("overdue")) /
                                  len(censored), 3) if censored else None,
            "washed_out": len(washed),
            "washed_out_share_of_listed": round(len(washed) / max(1, len(rows)), 3),
        },
        "empirical_tables_by_vintage": {str(k): v for k, v in tables_by_vintage.items()},
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print(f"cohort: {rep['accounting']}")
    for k in ("champion_heuristic", "baseline_naive_level_table",
              "champion_on_baseline_rows",
              "challenger_empirical_table_forward_chained",
              "challenger_km_recalibrated_heuristic", "v38_frozen_on_km_rows"):
        print(f"{k}: {rep[k]}")
    print("km table:", rep["km_base_years_full_window"],
          "vs v38:", rep["v38_frozen_base_years"])
    print("overdue:", rep["overdue_v38_vs_km"])
    print("by_level:", {k: v.get('mae') for k, v in rep['by_level'].items()})
    print("residuals:", rep['residual_by_level'])
    print("censoring:", rep['censoring'])
