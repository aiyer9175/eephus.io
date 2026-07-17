# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""xHEM+ validation lab, HARNESS v2 (T1-7 2026-07-15; see
tools/plus_lab_harness.py): does Statcast expected wOBA (xwOBA) forward-predict
a hitter's NEXT-year wOBA better than his ACTUAL wOBA?

  X-H3  xHEM+ = the HEM+ ratio scale applied to Savant est_woba (xwOBA) instead of
        actual wOBA. GATE (ship the xwOBA-based companion): forward Spearman of
        xwOBA(Y) vs wOBA(Y+1) BEATS actual wOBA(Y) (seeded bootstrap gap lo95 > 0).
        xwOBA strips BABIP/sequencing luck, so it is the more stable talent signal.
        -> data/xhem_plus_eval.json

  X-H5  fwdHEM+ blend (T1-3, pre-registered 2026-07-15): 0.7 * z(est_woba) +
        0.3 * z(unrounded HEM+ core, hem_plus_raw), z-scored WITHIN the predictor
        season over the joined pair set. The intuition: xwOBA carries the contact-
        quality signal but is blind to the sample-shrunk walk/steal-of-first
        discipline the HEM+ core keeps; a light 30% HEM leg recovers it. GATE
        (ship the blend as the forward column): blend forward-beats xwOBA-alone
        on the SAME pair set (seeded 2000-rep paired bootstrap gap lo95 > 0,
        seed 20260706, convention v1; pass_under_v2 reported alongside).
        Ships as the fwdhem_plus column (hitter_export._join_fwdhem_plus).
        -> x_h5_blend block of data/xhem_plus_eval.json

HARNESS v2: predictors are the Savant floats (already unrounded); outcome
seasons must be complete (past Nov 15 - enforced, currently a no-op because the
Savant loader never joins a season that is not in SEASONS); both target
conventions (v1 raw / v2 within-outcome-season z of wOBA(Y+1)) and both
bootstrap designs (legacy iid / player-clustered season-stratified) are emitted
side by side. The gate stays declared on v1 this cycle.

Uses the Savant expected-statistics leaderboard (mlb_player_export._savant, cached
per season under .cache/savant_mlb/). Savant is MLB-only + min-BBE gated, so xHEM+
is a COMPANION for tracked hitters, not population-complete like HEM+.
Run: python tools/xhem_plus_lab.py [--no-write]
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

import mlb_player_export as mpe  # noqa: E402
import plus_lab_harness as plh  # noqa: E402
from rem_plus_backtest import _spearman  # noqa: E402

DATA = ROOT / "data"
XHEM_EVAL = DATA / "xhem_plus_eval.json"

SEASONS = [2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]   # ex-2020
MIN_PA = 200.0
BOOT = 2000
SEED = 20260705
BLEND_SEED = 20260706          # X-H5 pre-registered seed (T1-3)
BLEND_W_XWOBA = 0.7            # X-H5 pre-registered weights
BLEND_W_HEM = 0.3

TARGET_V1 = "actual wOBA in Y+1 (raw, pooled across seasons)"
TARGET_V2 = "actual wOBA in Y+1"


def _r4(v):
    return None if v is None else round(v, 4)


def load_savant_woba(year: int) -> dict:
    """mlbam -> (woba, xwoba, pa) from the Savant expected-statistics leaderboard."""
    out = {}
    for r in mpe._savant("expected", year, "batter"):
        try:
            out[int(r["player_id"])] = (float(r["woba"]), float(r["est_woba"]), float(r["pa"]))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def load_hem_core(year: int) -> dict:
    """mlbam -> UNROUNDED hem_plus_raw for season `year`, scored from the cached
    StatsAPI hitting statlines (offline). Same scoring path as the HEM+ lab:
    Hitter objects scored directly, display rounding never enters the eval."""
    import hem_plus  # noqa: PLC0415 - local so X-H3 alone stays import-light
    import hitter_export as he  # noqa: PLC0415

    rows = he.load_season_hitting(year)
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
        if h.hem_plus_raw is not None and h.mlbam is not None:
            out[int(h.mlbam)] = h.hem_plus_raw
    return out


def run(write: bool = True) -> dict:
    t0 = time.time()
    data = {}
    for y in SEASONS:
        d = load_savant_woba(y)
        if d:
            data[y] = d
        print(f"  {y}: {len(d)} tracked batters")

    woba, xwoba, tgt = [], [], []
    mids, pys, oys = [], [], []
    dropped_partial = 0
    for y in SEASONS:
        cur, nxt = data.get(y), data.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, (w, x, pa) in cur.items():
            nn = nxt.get(mid)
            if nn and pa >= MIN_PA and nn[2] >= MIN_PA:
                if not plh.season_complete(y + 1):
                    dropped_partial += 1
                    continue
                woba.append(w); xwoba.append(x); tgt.append(nn[0])
                mids.append(mid); pys.append(y); oys.append(y + 1)
    n = len(woba)
    print(f"  X-H3 pairs: {n} (dropped {dropped_partial} partial-outcome pairs)")

    tgt_v2 = plh.zscore_within(oys, tgt)
    rho_woba = _spearman(woba, tgt)
    rho_xwoba = _spearman(xwoba, tgt)
    rho_woba_v2 = _spearman(woba, tgt_v2)
    rho_xwoba_v2 = _spearman(xwoba, tgt_v2)

    gap_v1 = plh.iid_boot_gaps(xwoba, {"vs_actual_woba": woba}, tgt, BOOT, SEED)["vs_actual_woba"]
    gap_v2 = plh.cluster_boot_gaps(xwoba, {"vs_actual_woba": woba}, tgt_v2,
                                   mids, pys, BOOT, SEED)["vs_actual_woba"]
    passed = bool(rho_xwoba is not None and gap_v1 and gap_v1["lo95"] > 0)
    passed_v2 = bool(rho_xwoba_v2 is not None and gap_v2 and gap_v2["lo95"] > 0)

    # ---- X-H5: fwdHEM+ blend (0.7 z(xwOBA) + 0.3 z(HEM core), within season) --- #
    # Same pair set as X-H3, with the UNROUNDED hem_plus_raw joined per predictor
    # season from cached StatsAPI (StatsAPI is population-complete over MLB, so the
    # join should keep every pair; any unmatched pair is dropped and counted).
    hem_by_year = {y: load_hem_core(y) for y in sorted(set(pys))}
    keep = [i for i in range(n) if hem_by_year.get(pys[i], {}).get(mids[i]) is not None]
    dropped_no_hem = n - len(keep)
    xw5 = [xwoba[i] for i in keep]
    hem5 = [hem_by_year[pys[i]][mids[i]] for i in keep]
    tgt5 = [tgt[i] for i in keep]
    mids5 = [mids[i] for i in keep]
    pys5 = [pys[i] for i in keep]
    oys5 = [oys[i] for i in keep]
    n5 = len(keep)
    print(f"  X-H5 pairs: {n5} (dropped {dropped_no_hem} pairs with no HEM core)")

    zx5 = plh.zscore_within(pys5, xw5)          # within-PREDICTOR-season z
    zh5 = plh.zscore_within(pys5, hem5)
    blend5 = [BLEND_W_XWOBA * a + BLEND_W_HEM * b for a, b in zip(zx5, zh5)]
    tgt5_v2 = plh.zscore_within(oys5, tgt5)

    rho_blend = _spearman(blend5, tgt5)
    rho_xw5 = _spearman(xw5, tgt5)
    rho_hem5 = _spearman(hem5, tgt5)
    rho_blend_v2 = _spearman(blend5, tgt5_v2)
    rho_xw5_v2 = _spearman(xw5, tgt5_v2)
    rho_hem5_v2 = _spearman(hem5, tgt5_v2)

    bl_base = {"vs_xwoba_alone": xw5, "vs_hem_core_alone": hem5}
    bl_gap_v1 = plh.iid_boot_gaps(blend5, bl_base, tgt5, BOOT, BLEND_SEED)
    bl_gap_v2 = plh.cluster_boot_gaps(blend5, bl_base, tgt5_v2, mids5, pys5,
                                      BOOT, BLEND_SEED)
    bl_pass = bool(rho_blend is not None and bl_gap_v1["vs_xwoba_alone"]
                   and bl_gap_v1["vs_xwoba_alone"]["lo95"] > 0)
    bl_pass_v2 = bool(rho_blend_v2 is not None and bl_gap_v2["vs_xwoba_alone"]
                      and bl_gap_v2["vs_xwoba_alone"]["lo95"] > 0)

    x_h5_blend = {
        "experiment": "X-H5", "model": "fwdhem_plus", "seed": BLEND_SEED,
        "weights": {"xwoba_z": BLEND_W_XWOBA, "hem_core_z": BLEND_W_HEM},
        "conventions": {
            "predictor": ("0.7 * z(Savant est_woba) + 0.3 * z(unrounded HEM+ core "
                          "hem_plus_raw), z-scored WITHIN the predictor season over "
                          "the joined pair set"),
            "hem_core_source": "cached StatsAPI hitting statlines scored via hem_plus (unrounded)",
            "pair_set": "the X-H3 pair set (Savant PA>=200 both years) with HEM core joined",
            "n_pairs_dropped_no_hem_core": dropped_no_hem},
        "n_forward_pairs": n5,
        "forward_spearman_vs_wOBA_next": {
            "blend": _r4(rho_blend), "xwoba_alone": _r4(rho_xw5),
            "hem_core_alone": _r4(rho_hem5)},
        "gap_ci_blend_minus_xwoba": bl_gap_v1["vs_xwoba_alone"],
        "results_by_convention": {
            "v1": {"rho_primary": _r4(rho_blend),
                   "rho_baselines": {"vs_xwoba_alone": _r4(rho_xw5),
                                     "vs_hem_core_alone": _r4(rho_hem5)},
                   "gap_ci": bl_gap_v1},
            "v2": {"rho_primary": _r4(rho_blend_v2),
                   "rho_baselines": {"vs_xwoba_alone": _r4(rho_xw5_v2),
                                     "vs_hem_core_alone": _r4(rho_hem5_v2)},
                   "gap_ci": bl_gap_v2,
                   "cluster": plh.cluster_summary(mids5, pys5)},
        },
        "gate": {"bar": ("blend forward-beats xwOBA-alone on the same pair set "
                         "(paired bootstrap gap lo95 > 0, seed 20260706)"),
                 "convention": "v1", "pass": bl_pass, "pass_under_v2": bl_pass_v2},
        "verdict": {
            "status": "validated" if bl_pass else "provisional",
            "summary": (
                f"Forward-chained OOS on the X-H3 pair set ({n5} pairs): the 0.7/0.3 "
                f"xwOBA+HEM-core blend predicts next-year wOBA at rho {_r4(rho_blend)} "
                f"vs xwOBA-alone {_r4(rho_xw5)} (HEM core alone {_r4(rho_hem5)}); "
                f"paired bootstrap gap CI {bl_gap_v1['vs_xwoba_alone']}. "
                + ("Shipped VALIDATED as the fwdhem_plus forward column: the light HEM "
                   "leg recovers the shrunk-discipline signal xwOBA is blind to. The "
                   "competing decayed-multiyear candidate (X-H4) failed its gate, so "
                   "this single-season blend is the declared incumbent."
                   if bl_pass else "Gate FAILED; not shipped, ledger stands."))},
    }

    results_by_convention = {
        "v1": {"rho_primary": _r4(rho_xwoba),
               "rho_baselines": {"vs_actual_woba": _r4(rho_woba)},
               "gap_ci": {"vs_actual_woba": gap_v1}},
        "v2": {"rho_primary": _r4(rho_xwoba_v2),
               "rho_baselines": {"vs_actual_woba": _r4(rho_woba_v2)},
               "gap_ci": {"vs_actual_woba": gap_v2},
               "cluster": plh.cluster_summary(mids, pys)},
    }

    payload = {
        "generated_at": date.today().isoformat(), "seasons": SEASONS, "seed": SEED,
        "experiment": "X-H3", "model": "xhem_plus",
        "conventions": {"predictor_year": f"Savant Y (PA>={int(MIN_PA)})",
                        "target": f"actual wOBA in Y+1 (PA>={int(MIN_PA)})", "excluded": "2020",
                        "n_partial_outcome_pairs_dropped": dropped_partial},
        "harness": plh.convention_meta(TARGET_V1, TARGET_V2),
        "n_forward_pairs": n,
        "forward_spearman_vs_wOBA_next": {"xwoba": _r4(rho_xwoba), "actual_woba": _r4(rho_woba)},
        "gap_ci_xwoba_minus_woba": gap_v1,
        "results_by_convention": results_by_convention,
        "gate": {"bar": "xwOBA forward-beats actual wOBA (gap lo95 > 0)",
                 "convention": "v1", "pass": passed, "pass_under_v2": passed_v2},
        "x_h5_blend": x_h5_blend,
        "runtime_seconds": round(time.time() - t0, 1),
        "verdict": {"status": "validated" if passed else "provisional",
                    "summary": (
                        f"Forward-chained OOS over {len([y for y in SEASONS if (y+1) in data])} "
                        f"year-pairs ({n} pairs): Savant xwOBA predicts next-year wOBA at rho "
                        f"{_r4(rho_xwoba)} vs actual wOBA {_r4(rho_woba)}; bootstrap gap CI "
                        f"{gap_v1}. "
                        + ("Shipped VALIDATED: xwOBA is the more forward-stable talent signal "
                           "(it strips BABIP/sequencing luck), so xHEM+ (the HEM+ ratio scale on "
                           "xwOBA) is a genuine deserved-offense companion. MLB-only + min-BBE "
                           "gated, so it is a companion column, not population-complete."
                           if passed else "Shipped provisional with the r published."))}}

    print(json.dumps({"X-H3": {"n": n, "xwoba": _r4(rho_xwoba), "woba": _r4(rho_woba),
                               "xwoba_v2": _r4(rho_xwoba_v2), "woba_v2": _r4(rho_woba_v2),
                               "gap_v1": gap_v1, "gap_v2": gap_v2,
                               "pass_v1": passed, "pass_v2": passed_v2},
                      "X-H5": {"n": n5, "blend": _r4(rho_blend), "xwoba": _r4(rho_xw5),
                               "hem": _r4(rho_hem5),
                               "gap_v1": bl_gap_v1["vs_xwoba_alone"],
                               "gap_v2": bl_gap_v2["vs_xwoba_alone"],
                               "pass_v1": bl_pass, "pass_v2": bl_pass_v2}}, indent=1))
    if write:
        tmp = XHEM_EVAL.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        tmp.replace(XHEM_EVAL)
        print(f"wrote {XHEM_EVAL.relative_to(ROOT)}")
    return {XHEM_EVAL: payload}


if __name__ == "__main__":
    run(write="--no-write" not in sys.argv[1:])
