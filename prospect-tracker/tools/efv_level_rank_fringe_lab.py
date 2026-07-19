# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""LR-FRINGE -- FV-45 fringe level_rank feature re-gate (ONE attempt).

The xfv_feature_arms_2026_07 ledger (data/xfv_feature_arms_eval.json) recorded
hit_level_rank showing the ops_rel FRINGE signature (t45 +0.0200, pooled flat)
but refused post-hoc fringe-gating as gate-shopping, keeping the arm alive for
a PRE-REGISTERED fringe re-run at the 2024-fold vintage. This is that run:
gate registered in docs/efv-2026-07-15/GATES.md section LR-FRINGE (the M5
ops_rel template verbatim) BEFORE this lab first executed.

Adds level_rank to the hitter lean set (additive) and scores it on the shipped
forward-chained eFV blend eval (efv_lab_runner). SHIP iff ALL of:
  1. t45 tier Spearman >= +0.015.
  2. Pooled >= -0.003.
  3. Within-tier weighted-mean >= -0.003.
  4. Per-era cells: no drop > 0.01.
ONE attempt; on failure, ledger and stop (the arm closes for good).

Writes data/xfv_level_rank_fringe_eval.json. Touches no production code.

Run:  python tools/efv_level_rank_fringe_lab.py
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

import efv_lab_runner as LAB

# gate thresholds (LR-FRINGE, the M5 template verbatim)
G_T45 = 0.015
G_POOLED = -0.003
G_WM = -0.003
G_ERA_DROP = 0.01

LEVEL_RANK_SPEC = {"name": "level_rank", "expr": "g(f,'level_rank')"}
OUT_PATH = ROOT / "data" / "xfv_level_rank_fringe_eval.json"


def _run(target):
    base = LAB.run_variant({"id": f"BASE:hit:{target}", "side": "hit", "target": target})
    treat = LAB.run_variant({"id": f"levelrank:hit:{target}", "side": "hit", "target": target,
                             "features": [LEVEL_RANK_SPEC]})
    era_delta = {e: round((treat["era"].get(e) or 0) - (base["era"].get(e) or 0), 4)
                 for e in set(base["era"]) | set(treat["era"])}
    return {
        "baseline": {"spearman": base["spearman"], "within_tier_wm": base["within_tier_wm"],
                     "t45": base["t45"], "era": base["era"], "n": base["n"]},
        "treatment": {"spearman": treat["spearman"], "within_tier_wm": treat["within_tier_wm"],
                      "t45": treat["t45"], "era": treat["era"], "n": treat["n"]},
        "delta": {
            "spearman": round((treat["spearman"] or 0) - (base["spearman"] or 0), 4),
            "within_tier_wm": round((treat["within_tier_wm"] or 0) - (base["within_tier_wm"] or 0), 4),
            "t45": (round((treat["t45"] or 0) - (base["t45"] or 0), 4)
                    if (treat["t45"] is not None and base["t45"] is not None) else None),
            "era": era_delta,
        },
    }


def main():
    res = {t: _run(t) for t in ("censored", "resolved")}
    prim = res["censored"]["delta"]

    c1 = {"t45_delta": prim["t45"], "threshold": G_T45,
          "pass": prim["t45"] is not None and prim["t45"] >= G_T45}
    c2 = {"pooled_delta": prim["spearman"], "threshold": G_POOLED, "pass": prim["spearman"] >= G_POOLED}
    c3 = {"within_tier_wm_delta": prim["within_tier_wm"], "threshold": G_WM,
          "pass": prim["within_tier_wm"] >= G_WM}
    era_fail = {e: dv for e, dv in prim["era"].items() if dv < -G_ERA_DROP}
    c4 = {"era_failures": era_fail, "pass": not era_fail}
    passed = all(c["pass"] for c in (c1, c2, c3, c4))

    artifact = {
        "generated_at": date.today().isoformat(),
        "experiment": "LR-FRINGE: FV-45 fringe level_rank feature re-gate at the 2024-fold vintage (one attempt)",
        "spec": "gate pre-registered in docs/efv-2026-07-15/GATES.md section LR-FRINGE (M5 template verbatim)",
        "method": {
            "change": "add level_rank to the hitter lean set (additive), shipped forward-chained "
                      "eFV blend eval (efv_lab_runner), blend at the live lambda",
            "vintage": "DEBUT_YEARS 2011-2024 unlocked matrices + terminal-transaction label fix",
            "primary_target": "censored (resolved reported as sensitivity)",
            "one_attempt": True,
            "declared_before_first_run": True,
        },
        "gate_thresholds": {"t45_at_least": G_T45, "pooled_floor": G_POOLED,
                            "within_tier_floor": G_WM, "era_drop_no_more_than": G_ERA_DROP},
        "results_by_target": res,
        "gate": {"condition_1_t45": c1, "condition_2_pooled": c2, "condition_3_within_tier": c3,
                 "condition_4_era": c4, "pass": passed},
        "verdict": "SHIP" if passed else "NO SHIP",
    }
    if not passed:
        artifact["loss_ledger"] = {
            "verdict": "NO SHIP",
            "failed_conditions": [k for k in ("condition_1_t45", "condition_2_pooled",
                                              "condition_3_within_tier", "condition_4_era")
                                  if not artifact["gate"][k]["pass"]],
            "summary": "level_rank did not clear the pre-registered fringe re-gate at the "
                       "2024-fold vintage. The hitter lean set is unchanged (byte-neutral). "
                       "The one pre-registered attempt is spent; the arm is closed for good.",
        }

    OUT_PATH.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
    print(f"LR-FRINGE level_rank gate: {'PASS -> SHIP' if passed else 'FAIL -> NO SHIP'}")
    for t in ("censored", "resolved"):
        d = res[t]["delta"]
        print(f"  {t}: t45 d={d['t45']} pooled d={d['spearman']} wm d={d['within_tier_wm']} era d={d['era']}")
    for k in ("condition_1_t45", "condition_2_pooled", "condition_3_within_tier", "condition_4_era"):
        print(f"  {k}: {'PASS' if artifact['gate'][k]['pass'] else 'FAIL'}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
