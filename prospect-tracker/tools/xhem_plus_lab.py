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
                               "pass_v1": passed, "pass_v2": passed_v2}}, indent=1))
    if write:
        tmp = XHEM_EVAL.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        tmp.replace(XHEM_EVAL)
        print(f"wrote {XHEM_EVAL.relative_to(ROOT)}")
    return {XHEM_EVAL: payload}


if __name__ == "__main__":
    run(write="--no-write" not in sys.argv[1:])
