# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Hitter-metric lab: HEM+ forward validation (the offensive analog of the SEM+
lab), HARNESS v2 (T1-7 2026-07-15; see tools/plus_lab_harness.py). One
pre-registered experiment:

  X-H1  HEM+ skill validation. HEM+ = hitter-pool EB-shrunk wOBA. GATE (ship):
        forward Spearman vs wOBA(Y+1) BEATS the naive AVG baseline (bootstrap gap
        lo95 > 0) AND is NOT WORSE than its raw-wOBA parent (gap lo95 >= -0.01).
        The shrinkage earns its place if it holds even/ahead of raw wOBA while
        beating the simpler rate stats. -> data/hem_plus_eval.json

HARNESS v2 fixes a real defect here: the lab previously read the ROUNDED int
hem_plus (hem_plus.py hem_plus(): hi.hem_plus = int(round(raw))) plus 3-decimal
display-rounded ops/avg/woba fields out of hitter_row(). The lab now scores the
Hitter objects directly and reads hem_plus_raw + unrounded rates. Shipped
display rounding is untouched. Both target conventions (v1 raw / v2 within-
outcome-season z of wOBA(Y+1)) + both bootstrap designs are emitted side by
side; gates stay declared on v1 this cycle. Outcome seasons must be complete
(no-op for the current SEASONS list, enforced anyway).

Uses the CACHED StatsAPI hitting statlines (fa_sources), so it runs offline. All
stochastic steps seeded.
Run: python tools/hem_plus_lab.py [--no-write] [--seasons 2015,2016,...]
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import hem_plus  # noqa: E402
import hitter_export as he  # noqa: E402
import plus_lab_harness as plh  # noqa: E402
from rem_plus_backtest import _spearman  # noqa: E402

DATA = ROOT / "data"
HEM_EVAL = DATA / "hem_plus_eval.json"
MULTI_EVAL = DATA / "hem_plus_multiyear_eval.json"

# Predictor seasons (cached hitting 2000-2026). Recent, ex-2020 (COVID 60-game).
SEASONS = [2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024]
MIN_PA_Y = 150.0                   # a usable predictor-year sample
MIN_PA_NEXT = 150.0                # a real outcome-year sample
BOOT = 2000
SEED = 20260705
TAG_MIN_SEASONS = 2                # 3yr "established" bar
TAG_MIN_PA = 600.0                 # ... and total PA over the window

TARGET_V1 = "wOBA in year Y+1 (raw, pooled across seasons)"
TARGET_V2 = "wOBA in year Y+1"


def _r4(v):
    return None if v is None else round(v, 4)


def load_season(y: int) -> dict:
    """MLBAM -> per-hitter record for season Y, carrying HEM+ (UNROUNDED
    hem_plus_raw for the eval + rounded display int for proposed_values), raw
    wOBA, OPS, AVG (all unrounded) and PA. Scores the Hitter objects directly
    instead of consuming hitter_row() display dicts (whose hem_plus is
    int(round()) and whose rates are 3-decimal display-rounded - the v1 lab
    defect). The next-year wOBA is joined at pair time."""
    rows = he.load_season_hitting(y)
    if not rows:
        return {}
    hitters = he.build_hitters(rows)
    pool_input = [h for h in hitters if hem_plus._woba_denom(h) > 0]
    for h in pool_input:
        hem_plus.derive_rates(h)
    pool = hem_plus.build_pool(pool_input)
    out = {}
    for h in pool_input:
        hem_plus.hem_plus(h, pool)
        if h.hem_plus_raw is None or h.woba_raw is None:
            continue
        out[h.mlbam] = {
            "name": h.name,
            "hem_plus": h.hem_plus,               # rounded display (proposed_values)
            "hem_plus_raw": h.hem_plus_raw,       # v2: unrounded eval predictor
            "woba_raw": h.woba_raw,               # unrounded (was 3dp via hitter_row)
            "ops": h.rates.get("ops"), "avg": h.rates.get("avg"),
            "pa": h.pa,
        }
    print(f"  {y}: {len(out)} hitters scored")
    return out


def _dual(primary, baselines: dict, tgt_raw, players, pred_seasons, out_seasons,
          seed=SEED):
    """One primary-vs-baselines comparison under BOTH conventions."""
    tgt_v2 = plh.zscore_within(out_seasons, tgt_raw)
    rp1 = _spearman(primary, tgt_raw)
    rb1 = {k: _spearman(s, tgt_raw) for k, s in baselines.items()}
    rp2 = _spearman(primary, tgt_v2)
    rb2 = {k: _spearman(s, tgt_v2) for k, s in baselines.items()}
    return {
        "v1": {"rho_primary": _r4(rp1),
               "rho_baselines": {k: _r4(v) for k, v in rb1.items()},
               "rho_primary_full": rp1, "rho_baselines_full": rb1,
               "gap_ci": plh.iid_boot_gaps(primary, baselines, tgt_raw, BOOT, seed)},
        "v2": {"rho_primary": _r4(rp2),
               "rho_baselines": {k: _r4(v) for k, v in rb2.items()},
               "rho_primary_full": rp2, "rho_baselines_full": rb2,
               "gap_ci": plh.cluster_boot_gaps(primary, baselines, tgt_v2, players,
                                               pred_seasons, BOOT, seed),
               "cluster": plh.cluster_summary(players, pred_seasons)},
    }


def _hem3(by_season, mid, y):
    """PA-weighted trailing-3-season HEM+ (y-2..y) for a player, seasons used, PA.
    Uses the UNROUNDED hem_plus_raw (harness v2)."""
    num = den = 0.0
    su = 0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if rec and rec.get("hem_plus_raw") is not None and rec.get("pa"):
            num += rec["hem_plus_raw"] * rec["pa"]; den += rec["pa"]; su += 1
    return (num / den if den else None), su, den


def _multiyear_proposed(by_season: dict, cur_season: int) -> dict:
    """3yr HEM+ for the CURRENT qualified pool -> proposed_values joined into
    hitter_leaderboards.json by MLBAM (like sem_plus_3yr). DISPLAY values keep
    the shipped rounding convention (rounded per-season HEM+ in, int out)."""
    cur = by_season.get(cur_season) or {}
    players, vals = {}, []
    for mid, row in cur.items():
        if row.get("hem_plus") is None or (row.get("pa") or 0) < 200:
            continue
        # shipped display convention: rounded per-season hem_plus
        num = den = 0.0
        su = 0
        for yy in (cur_season - 2, cur_season - 1, cur_season):
            rec = (by_season.get(yy) or {}).get(mid)
            if rec and rec.get("hem_plus") is not None and rec.get("pa"):
                num += rec["hem_plus"] * rec["pa"]; den += rec["pa"]; su += 1
        if not den:
            continue
        h3, pa3 = num / den, den
        tag = ("established" if su >= TAG_MIN_SEASONS and pa3 >= TAG_MIN_PA else "provisional")
        players[str(mid)] = {"name": row.get("name"), "hem_plus_now": row.get("hem_plus"),
                             "hem_plus_3yr": int(round(h3)), "seasons_used": su,
                             "pa_total": int(pa3), "tag": tag}
        vals.append((str(mid), h3))
    n = len(vals)
    svals = sorted(v for _, v in vals)
    for mid, v in vals:
        lo = sum(1 for s in svals if s < v)
        eq = sum(1 for s in svals if s == v)
        players[mid]["pct"] = int(round(100.0 * (lo + (eq + 1) / 2.0 - 0.5) / n)) if n else None
    return {"season": cur_season, "window": [cur_season - 2, cur_season - 1, cur_season],
            "metric": "hem_plus_3yr", "display_name": "HEM+ (3yr)",
            "definition": (f"PA-weighted mean HEM+ over the trailing 3 seasons. A steadier "
                           f"offense read than one season. tag is 'established' with "
                           f"{TAG_MIN_SEASONS}+ seasons and {int(TAG_MIN_PA)}+ PA."),
            "n_with_value": len(players), "players": players}


def run(write: bool = True) -> dict:
    t0 = time.time()
    by_season = {}
    # Backtest pairs run over SEASONS (all complete Y->Y+1). Load two extra seasons
    # beyond the last predictor (the last complete target + the CURRENT season) so
    # the proposed-values 3yr window matches the live board's season, not a year
    # behind. The current (incomplete) season is NOT used as a backtest target.
    for y in SEASONS + [max(SEASONS) + 1, max(SEASONS) + 2]:
        s = load_season(y)
        if s:
            by_season[y] = s
    print(f"  loaded {len(by_season)} seasons in {round(time.time()-t0,1)}s")

    hem, woba, ops, avg, tgt = [], [], [], [], []
    mids1, pys1, oys1 = [], [], []
    dropped_partial = 0
    for y in SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["pa"] or 0) < MIN_PA_Y or (b["pa"] or 0) < MIN_PA_NEXT:
                continue
            if a["ops"] is None or a["avg"] is None or b["woba_raw"] is None:
                continue
            if not plh.season_complete(y + 1):
                dropped_partial += 1
                continue
            hem.append(a["hem_plus_raw"]); woba.append(a["woba_raw"])
            ops.append(a["ops"]); avg.append(a["avg"]); tgt.append(b["woba_raw"])
            mids1.append(mid); pys1.append(y); oys1.append(y + 1)
    n = len(hem)
    print(f"  X-H1 pairs: {n} (dropped {dropped_partial} partial-outcome pairs)")

    xh1 = _dual(hem, {"vs_avg": avg, "vs_ops": ops, "vs_raw_woba": woba}, tgt,
                mids1, pys1, oys1)
    rho_hem = xh1["v1"]["rho_primary"]
    rho_woba = xh1["v1"]["rho_baselines"]["vs_raw_woba"]
    rho_ops = xh1["v1"]["rho_baselines"]["vs_ops"]
    rho_avg = xh1["v1"]["rho_baselines"]["vs_avg"]
    gap_vs_avg = xh1["v1"]["gap_ci"]["vs_avg"]
    gap_vs_ops = xh1["v1"]["gap_ci"]["vs_ops"]
    gap_vs_woba = xh1["v1"]["gap_ci"]["vs_raw_woba"]
    passed = bool(rho_hem is not None and gap_vs_avg and gap_vs_avg["lo95"] > 0
                  and gap_vs_woba and gap_vs_woba["lo95"] >= -0.01)
    passed_v2 = bool(xh1["v2"]["rho_primary"] is not None
                     and xh1["v2"]["gap_ci"]["vs_avg"]
                     and xh1["v2"]["gap_ci"]["vs_avg"]["lo95"] > 0
                     and xh1["v2"]["gap_ci"]["vs_raw_woba"]
                     and xh1["v2"]["gap_ci"]["vs_raw_woba"]["lo95"] >= -0.01)

    # ---- X-H2: 3yr HEM+ forward pairs (3yr vs 1yr on the SAME set) ---- #
    one3, three3, tgt3 = [], [], []
    mids3, pys3, oys3 = [], [], []
    for y in SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["pa"] or 0) < MIN_PA_Y or (b["pa"] or 0) < MIN_PA_NEXT or b["woba_raw"] is None:
                continue
            if not plh.season_complete(y + 1):
                continue
            h3, su, pa3 = _hem3(by_season, mid, y)
            if h3 is None or su < TAG_MIN_SEASONS or pa3 < TAG_MIN_PA:
                continue
            one3.append(a["hem_plus_raw"]); three3.append(h3); tgt3.append(b["woba_raw"])
            mids3.append(mid); pys3.append(y); oys3.append(y + 1)
    n3 = len(one3)
    xh2 = (_dual(three3, {"vs_1yr": one3}, tgt3, mids3, pys3, oys3)
           if n3 >= 30 else None)
    rho_1yr = xh2["v1"]["rho_baselines"]["vs_1yr"] if xh2 else None
    rho_3yr = xh2["v1"]["rho_primary"] if xh2 else None
    gap3 = xh2["v1"]["gap_ci"]["vs_1yr"] if xh2 else None
    passed3 = bool(xh2 and xh2["v1"]["rho_primary_full"] is not None
                   and xh2["v1"]["rho_baselines_full"]["vs_1yr"] is not None
                   and xh2["v1"]["rho_primary_full"] > xh2["v1"]["rho_baselines_full"]["vs_1yr"]
                   and gap3 and gap3["lo95"] >= 0)
    gap3_v2 = xh2["v2"]["gap_ci"]["vs_1yr"] if xh2 else None
    passed3_v2 = bool(xh2 and xh2["v2"]["rho_primary_full"] is not None
                      and xh2["v2"]["rho_baselines_full"]["vs_1yr"] is not None
                      and xh2["v2"]["rho_primary_full"] > xh2["v2"]["rho_baselines_full"]["vs_1yr"]
                      and gap3_v2 and gap3_v2["lo95"] >= 0)

    dur = round(time.time() - t0, 1)
    payload = {
        "generated_at": date.today().isoformat(), "seasons": SEASONS, "seed": SEED,
        "experiment": "X-H1", "model": "hem_plus",
        "conventions": {"predictor_year": f"year Y (PA>={int(MIN_PA_Y)})",
                        "target": f"wOBA in year Y+1 (PA>={int(MIN_PA_NEXT)})",
                        "excluded": "2020 (60-game COVID season)",
                        "n_partial_outcome_pairs_dropped": dropped_partial},
        "harness": plh.convention_meta(TARGET_V1, TARGET_V2),
        "lab_defect_fixed": ("previous runs read the ROUNDED int hem_plus + 3-decimal "
                             "display-rounded ops/avg/woba out of hitter_row(); harness "
                             "v2 scores Hitter objects directly (hem_plus_raw, unrounded "
                             "rates). Shipped display rounding untouched."),
        "n_forward_pairs": n,
        "forward_spearman_vs_wOBA_next": {
            "hem_plus": rho_hem, "raw_woba": rho_woba,
            "ops": rho_ops, "avg": rho_avg},
        "gap_ci_vs_avg": gap_vs_avg, "gap_ci_vs_ops": gap_vs_ops,
        "gap_ci_vs_raw_woba": gap_vs_woba,
        "results_by_convention": xh1,
        "gate": {"bar": "beats AVG forward (gap lo95 > 0) AND not worse than raw wOBA (lo95 >= -0.01)",
                 "convention": "v1", "pass": passed, "pass_under_v2": passed_v2},
        "runtime_seconds": dur,
        "verdict": {"status": "validated" if passed else "provisional",
                    "summary": (
                        f"Forward-chained OOS over {len(SEASONS)} seasons ({n} Y->Y+1 pairs): "
                        f"HEM+ predicts next-year wOBA at rho {rho_hem} vs raw wOBA "
                        f"{rho_woba}, OPS {rho_ops}, AVG {rho_avg}. CI on the rho "
                        f"gap vs AVG {gap_vs_avg}, vs raw wOBA {gap_vs_woba}. "
                        + ("Shipped VALIDATED: HEM+ beats the naive rate baselines and holds "
                           "even-or-ahead of its raw-wOBA parent out of sample, so the "
                           "component empirical-Bayes shrinkage + hitter-pool anchoring earn "
                           "their place. Volume/baserunning ride separate context columns."
                           if passed else
                           "Shipped provisional with the r published."))}}

    cur_season = max(by_season)
    multi_payload = {
        "generated_at": date.today().isoformat(), "seasons": SEASONS, "seed": SEED,
        "experiment": "X-H2", "model": "hem_plus_3yr", "n_forward_pairs": n3,
        "conventions": {"predictor_year": f"trailing 3yr through Y (PA>={int(MIN_PA_Y)} in Y)",
                        "target": f"wOBA in year Y+1 (PA>={int(MIN_PA_NEXT)})", "excluded": "2020"},
        "harness": plh.convention_meta(TARGET_V1, TARGET_V2),
        "hem_1yr_forward_rho_on_3yr_set": rho_1yr,
        "hem_3yr_forward_rho": rho_3yr, "gap_ci_3yr_minus_1yr": gap3,
        "results_by_convention": xh2,
        "gate": {"bar": "3yr rho > 1yr rho on the same set AND bootstrap gap lo95 >= 0",
                 "convention": "v1", "pass": passed3, "pass_under_v2": passed3_v2},
        "verdict": ("PASS: 3-year HEM+ forward-predicts next-year offense better than one "
                    "season; ship hem_plus_3yr as a companion column."
                    if passed3 else
                    "MARGINAL: 3-year HEM+ does not clear the strict same-set gate; ship "
                    "provisional with the r published (more sample is a steadier read)."),
        "runtime_seconds": dur,
        "proposed_values": _multiyear_proposed(by_season, cur_season)}

    print(json.dumps({"X-H1": {"n": n, "hem": rho_hem, "woba": rho_woba,
                               "ops": rho_ops, "avg": rho_avg,
                               "vs_avg_v1": gap_vs_avg, "vs_woba_v1": gap_vs_woba,
                               "vs_avg_v2": xh1["v2"]["gap_ci"]["vs_avg"],
                               "vs_woba_v2": xh1["v2"]["gap_ci"]["vs_raw_woba"],
                               "pass_v1": passed, "pass_v2": passed_v2},
                      "X-H2": {"n": n3, "one": rho_1yr, "three": rho_3yr,
                               "gap_v1": gap3, "gap_v2": gap3_v2,
                               "pass_v1": passed3, "pass_v2": passed3_v2}}, indent=1))
    if write:
        for path, pl in ((HEM_EVAL, payload), (MULTI_EVAL, multi_payload)):
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(pl, indent=1) + "\n", encoding="utf-8")
            tmp.replace(path)
            print(f"wrote {path.relative_to(ROOT)}")
    return {HEM_EVAL: payload, MULTI_EVAL: multi_payload}


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--seasons" in argv:
        i = argv.index("--seasons")
        SEASONS = [int(x) for x in argv[i + 1].split(",")]
    run(write="--no-write" not in argv)
