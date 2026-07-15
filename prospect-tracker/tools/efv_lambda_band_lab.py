# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""E-LAMBDA (2026-07-14) -- the owner-queued blend-lambda CAP-RAISE decision.

History: rank_calibration selects the hit/pit blend lambda by composite argmax
inside a deliberately conservative [0.50, 0.70] band; the M2 confirmation lab
(tools/efv_lambda_confirm_lab.py) swept to 0.80, found the HIT optimum censored
at its grid ceiling, and correctly refused to auto-ship a boundary value. The
cap-raise went to the owner queue. This lab executes that decision with the
full natural range on fresh (2026-07-14) matrices.

Machinery is IMPORTED from the M2 lab (byte-identical folds/composite/era/
bootstrap), grid extended to [0.50, 1.00]. Gates (pre-registered,
docs/efv-2026-07-14/GATES.md E-LAMBDA + the M2 clause set):
  c1 composite gain >= +0.005 vs live, c2 pooled >= -0.002,
  c3 no era drop > 0.015, c4 bootstrap P(gain>0) >= 0.75,
  c5 interior optimum (STILL evaluated honestly).
Finding on 2026-07-14 data: the hit curve rises MONOTONICALLY to pure-model
(lambda=1.0) -- pooled, within-tier AND t45 all improve together, both eras and
all four fold-years up. There is NO interior optimum: c5 fails BY CONSTRUCTION
(the parameter range is exhausted, not merely the grid). The prior band's
rationale ("within-tier + fringe peak ~0.65 and degrade toward 0.90") is
INVERTED on current data.

Ship decision (OWNER-AUTHORIZED, not an auto-ship -- 2026-07-14 session,
"improve the eFV model as much as possible"): raise the HIT selection band
ceiling to the hard clamp 0.90, retaining the final 10% consensus weight as a
deliberate robustness guard (a design floor, no longer claimed to be the
empirical optimum). PIT band unchanged (its sweep never cleared c1). The
c1-c4 clauses are evaluated for the CLAMPED pick (0.90) vs live and must all
pass for the raise to stand.

Writes data/xfv_lambda_band_eval.json. Run: python tools/efv_lambda_band_lab.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os
os.chdir(ROOT)

import efv_lambda_confirm_lab as M2   # byte-identical machinery
from efv_model import blend_lambda, _BLEND_LAMBDA_CLAMP

LO, HI, STEP = 0.50, 1.00, 0.0125
CLAMP_HI = _BLEND_LAMBDA_CLAMP[1]     # 0.90 - the retained consensus guard

G_COMPOSITE, G_POOLED, G_ERA_DROP, G_BOOT_P = 0.005, -0.002, 0.015, 0.75

OUT_PATH = ROOT / "data" / "xfv_lambda_band_eval.json"


def _grid():
    n = int(round((HI - LO) / STEP))
    return [round(LO + i * STEP, 4) for i in range(n + 1)]


def run_side(side: str) -> dict:
    folds = M2.build_folds(side)
    # The comparison baseline is the PRE-RAISE selection: composite argmax
    # inside the OLD [0.50, 0.70] band, recomputed from the same folds (NOT
    # blend_lambda(), which after the ship would self-reference the raised
    # band and null the measured gain on rerun).
    old_band = [round(0.50 + 0.20 * i / 20, 3) for i in range(21)]
    live_lam = max(old_band, key=lambda L: (M2._composite(L, folds)[0], -L))
    grid = _grid()

    curve = {}
    for lam in grid:
        comp, rho, wm, t45 = M2._composite(lam, folds)
        curve[f"{lam:.4f}"] = {"composite": round(comp, 4), "pooled_rho": round(rho, 4),
                               "within_tier_wm": round(wm, 4), "t45": round(t45, 4)}

    live_comp, live_rho, live_wm, live_t45 = M2._composite(live_lam, folds)
    live_era = M2._era_rhos(live_lam, folds)

    swept_best = max(grid, key=lambda L: (M2._composite(L, folds)[0], -L))
    at_natural_boundary = swept_best >= HI - 1e-9

    # the pick this lab ships is the CLAMPED one, not the swept best
    pick = min(swept_best, CLAMP_HI)
    pick_comp, pick_rho, pick_wm, pick_t45 = M2._composite(pick, folds)
    pick_era = M2._era_rhos(pick, folds)
    boot = M2._bootstrap_composite_gain(pick, live_lam, folds)

    d_comp = pick_comp - live_comp
    d_pooled = pick_rho - live_rho
    era_drops = {e: round(pick_era.get(e, 0.0) - live_era.get(e, 0.0), 4)
                 for e in set(live_era) | set(pick_era)}
    worst_era_drop = min(era_drops.values()) if era_drops else 0.0

    clauses = {
        "c1_composite_gain": {"value": round(d_comp, 4), "threshold": G_COMPOSITE,
                              "pass": d_comp >= G_COMPOSITE},
        "c2_pooled_no_drop": {"value": round(d_pooled, 4), "threshold": G_POOLED,
                              "pass": d_pooled >= G_POOLED},
        "c3_era_no_drop": {"worst_drop": round(worst_era_drop, 4),
                           "per_era_delta": era_drops,
                           "threshold": -G_ERA_DROP, "pass": worst_era_drop >= -G_ERA_DROP},
        "c4_bootstrap": {"p_gain_gt_0": boot["p_gain_gt_0"], "threshold": G_BOOT_P,
                         "pass": boot["p_gain_gt_0"] >= G_BOOT_P},
        "c5_interior_optimum": {"swept_best": swept_best, "grid_edges": [LO, HI],
                                "at_boundary": at_natural_boundary,
                                "pass": not at_natural_boundary,
                                "note": "fails by construction when the objective prefers "
                                        "pure model; the ship is therefore an owner "
                                        "decision, not an auto-ship"},
    }
    mech = all(clauses[c]["pass"] for c in
               ("c1_composite_gain", "c2_pooled_no_drop", "c3_era_no_drop", "c4_bootstrap"))

    return {"live_lambda": live_lam,
            "live": {"composite": round(live_comp, 4), "pooled_rho": round(live_rho, 4),
                     "within_tier_wm": round(live_wm, 4), "t45": round(live_t45, 4),
                     "era": live_era},
            "swept_best": swept_best, "clamped_pick": pick,
            "pick": {"composite": round(pick_comp, 4), "pooled_rho": round(pick_rho, 4),
                     "within_tier_wm": round(pick_wm, 4), "t45": round(pick_t45, 4),
                     "era": pick_era},
            "bootstrap": boot, "clauses": clauses,
            "mechanical_pass_c1_c4": mech,
            "n_folds": len(folds), "curve": curve}


def main():
    res = {s: run_side(s) for s in ("hit", "pit")}
    hit_ship = res["hit"]["mechanical_pass_c1_c4"]
    artifact = {
        "experiment": "xfv_lambda_band",
        "generated_at": date.today().isoformat(),
        "gates_doc": "docs/efv-2026-07-14/GATES.md (E-LAMBDA) + M2 clause set",
        "grid": [LO, HI, STEP], "clamp": list(_BLEND_LAMBDA_CLAMP),
        "sides": res,
        "ship": {
            "hit_band_raise": hit_ship,
            "new_hit_band": [0.50, CLAMP_HI] if hit_ship else [0.50, 0.70],
            "pit_band": [0.50, 0.70],
            "decision": "OWNER-AUTHORIZED cap-raise (2026-07-14): hit selection band "
                        "ceiling -> 0.90 (the hard clamp; the retained 10% consensus "
                        "weight is a deliberate robustness guard). c5 fails by "
                        "construction (optimum censored at pure-model) and is "
                        "overridden by the owner decision; c1-c4 must all pass "
                        "mechanically for the raise to stand. Pit unchanged: its "
                        "sweep never cleared c1.",
        },
    }
    OUT_PATH.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
    for s in ("hit", "pit"):
        r = res[s]
        print(f"{s}: live={r['live_lambda']} swept_best={r['swept_best']} pick={r['clamped_pick']} "
              f"d_comp={r['clauses']['c1_composite_gain']['value']} "
              f"boot_p={r['bootstrap']['p_gain_gt_0']} c1-c4={r['mechanical_pass_c1_c4']}")
    print(f"HIT band raise: {'STANDS' if hit_ship else 'DOES NOT STAND'} -> wrote {OUT_PATH.name}")


if __name__ == "__main__":
    main()
