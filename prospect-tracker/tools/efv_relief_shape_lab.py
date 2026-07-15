# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""RELIEF-SHAPE -- PAL prospect-watch relief risk as a pitcher feature (one
attempt per arm).

Owner ask: wire the PAL Prospect Watch shape signal (pal_conversion.
prospect_role_fit) into eFV as a relief risk for pitchers; only ship on a
gain. Gate registered in docs/efv-2026-07-15/GATES.md section RELIEF-SHAPE
BEFORE this lab first executed.

The feature computation lives in efv_model._vec (None-aware on raw grades,
observed-train-mean neutral for zero-graded rows), so this lab scores the
exact production code path via the shipped forward-chained eFV blend eval
(efv_lab_runner). Three arms, additive to the pit lean set, live lambda:

  RS-1 starter_shape  PAL composite (arsenal depth + command), 0-100
  RS-2 arsenal_depth  observed count of pitch grades >= 55, 0-4
  RS-3 relief_flag    1.0 if observed starter_shape < 40 (PAL RP lean)

SHIP an arm iff ALL of (deltas vs SAME-RUN BASE, censored primary):
  1. pooled Spearman delta >= +0.0046
  2. within-tier wm delta  >= -0.0023
  3. t45 delta             >= -0.0023
  4. no per-era cell drop  > 0.01
  5. per_tier 45 and 50 rho drop no more than 0.01 (pit weakest cells)
Marginal counts as fail. Multiple passers -> ship ONLY the highest pooled
delta. Pooled-fail arms with t45 >= +0.015 and pooled/wm >= -0.0011 are
recorded as fringe-signature keep-alives (future pre-registered re-gate
only; no same-session re-gate).

Writes data/xfv_relief_shape_eval.json. Touches no production behavior
(the _vec keys are inert until added to _FEATURES_PIT).

Run:  python tools/efv_relief_shape_lab.py
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

# gate thresholds (RELIEF-SHAPE registration, the MC-PIT additive bar +
# the weakest-cells clause)
G_POOLED = 0.0046
G_WM = -0.0023
G_T45 = -0.0023
G_ERA_DROP = 0.01
G_TIER_DROP = 0.01
# fringe-signature record thresholds (level_rank precedent)
F_T45 = 0.015
F_FLOOR = -0.0011

ARMS = [
    {"key": "RS-1", "name": "starter_shape", "expr": "g(f,'starter_shape')"},
    {"key": "RS-2", "name": "arsenal_depth", "expr": "g(f,'arsenal_depth')"},
    {"key": "RS-3", "name": "relief_flag", "expr": "g(f,'relief_flag')"},
]
OUT_PATH = ROOT / "data" / "xfv_relief_shape_eval.json"


def _delta(treat, base):
    # UNROUNDED deltas: "marginal counts as fail" means the gate must compare
    # full-precision values (a true wm -0.00234 must NOT round up to a
    # passing -0.0023). Rounding happens only at artifact-write time.
    era = {e: (treat["era"].get(e) or 0) - (base["era"].get(e) or 0)
           for e in set(base["era"]) | set(treat["era"])}
    tier = {}
    for tk in (45, 50):
        b = (base["per_tier"].get(tk) or {}).get("rho")
        t = (treat["per_tier"].get(tk) or {}).get("rho")
        tier[tk] = (t - b) if (b is not None and t is not None) else None
    return {
        "spearman": (treat["spearman"] or 0) - (base["spearman"] or 0),
        "within_tier_wm": (treat["within_tier_wm"] or 0) - (base["within_tier_wm"] or 0),
        "t45": ((treat["t45"] or 0) - (base["t45"] or 0)
                if (treat["t45"] is not None and base["t45"] is not None) else None),
        "era": era,
        "per_tier": tier,
    }


def _round_delta(d):
    return {
        "spearman": round(d["spearman"], 4),
        "within_tier_wm": round(d["within_tier_wm"], 4),
        "t45": round(d["t45"], 4) if d["t45"] is not None else None,
        "era": {e: round(v, 4) for e, v in d["era"].items()},
        "per_tier": {tk: (round(v, 4) if v is not None else None)
                     for tk, v in d["per_tier"].items()},
    }


def _gate(d):
    # comparisons on UNROUNDED deltas; stored values rounded for readability
    c1 = {"pooled_delta": round(d["spearman"], 4), "threshold": G_POOLED,
          "pass": d["spearman"] >= G_POOLED}
    c2 = {"within_tier_wm_delta": round(d["within_tier_wm"], 4), "threshold": G_WM,
          "pass": d["within_tier_wm"] >= G_WM}
    c3 = {"t45_delta": round(d["t45"], 4) if d["t45"] is not None else None, "threshold": G_T45,
          "pass": d["t45"] is not None and d["t45"] >= G_T45}
    era_fail = {e: round(dv, 4) for e, dv in d["era"].items() if dv < -G_ERA_DROP}
    c4 = {"era_failures": era_fail, "pass": not era_fail}
    tier_fail = {tk: round(dv, 4) for tk, dv in d["per_tier"].items()
                 if dv is not None and dv < -G_TIER_DROP}
    c5 = {"tier_failures": tier_fail, "pass": not tier_fail}
    gate = {"condition_1_pooled": c1, "condition_2_within_tier": c2, "condition_3_t45": c3,
            "condition_4_era": c4, "condition_5_weakest_tiers": c5}
    gate["pass"] = all(gate[k]["pass"] for k in
                       ("condition_1_pooled", "condition_2_within_tier", "condition_3_t45",
                        "condition_4_era", "condition_5_weakest_tiers"))
    # The registered fringe rule keys on failing the POOLED bar specifically
    # ("an arm that FAILS the pooled bar..."), not on overall gate failure.
    gate["fringe_signature"] = (not c1["pass"]
                                and d["t45"] is not None and d["t45"] >= F_T45
                                and d["spearman"] >= F_FLOOR
                                and d["within_tier_wm"] >= F_FLOOR)
    return gate


def main():
    res = {}
    raw = {}  # target -> arm key -> unrounded deltas (gating precision)
    for target in ("censored", "resolved"):
        base = LAB.run_variant({"id": f"BASE:pit:{target}", "side": "pit", "target": target})
        arms = {}
        raw[target] = {}
        for a in ARMS:
            treat = LAB.run_variant({"id": f"{a['key']}:{a['name']}:pit:{target}", "side": "pit",
                                     "target": target,
                                     "features": [{"name": a["name"], "expr": a["expr"]}]})
            d = _delta(treat, base)
            raw[target][a["key"]] = d
            arms[a["key"]] = {
                "name": a["name"],
                "treatment": {"spearman": treat["spearman"], "within_tier_wm": treat["within_tier_wm"],
                              "t45": treat["t45"], "era": treat["era"],
                              "per_tier": treat["per_tier"], "n": treat["n"]},
                "delta": _round_delta(d),
            }
        res[target] = {
            "baseline": {"spearman": base["spearman"], "within_tier_wm": base["within_tier_wm"],
                         "t45": base["t45"], "era": base["era"],
                         "per_tier": base["per_tier"], "n": base["n"]},
            "arms": arms,
        }

    gates = {k: _gate(raw["censored"][k]) for k in raw["censored"]}
    passers = [k for k, gv in gates.items() if gv["pass"]]
    # registered selection rule: multiple passers -> highest pooled delta only
    ship = (max(passers, key=lambda k: raw["censored"][k]["spearman"])
            if passers else None)
    fringe = [k for k, gv in gates.items() if gv["fringe_signature"]]

    artifact = {
        "generated_at": date.today().isoformat(),
        "experiment": "RELIEF-SHAPE: PAL prospect-watch relief risk (starter_shape / "
                      "arsenal_depth / relief_flag) as additive pit features (one attempt per arm)",
        "spec": "gate pre-registered in docs/efv-2026-07-15/GATES.md section RELIEF-SHAPE",
        "method": {
            "change": "PAL-faithful shape composite computed None-aware in efv_model._vec "
                      "(production code path), added to the pit lean set additively; shipped "
                      "forward-chained eFV blend eval (efv_lab_runner), blend at the live lambda",
            "vintage": "DEBUT_YEARS 2011-2024 unlocked matrices + terminal-transaction label fix",
            "primary_target": "censored (resolved reported as sensitivity)",
            "pal_divergence": "tool_ct absent at the pre-debut anchor; composite is fb/sl/cb/ch + cmd",
            "survivorship_caveat": "debuted-only eval pool cannot see never-debut RP-shape washouts; "
                                   "this gate can under-credit the feature but not over-credit it",
            "one_attempt_per_arm": True,
            "declared_before_first_run": True,
        },
        "gate_thresholds": {"pooled_at_least": G_POOLED, "within_tier_floor": G_WM,
                            "t45_floor": G_T45, "era_drop_no_more_than": G_ERA_DROP,
                            "weakest_tier_drop_no_more_than": G_TIER_DROP,
                            "fringe_signature": {"t45_at_least": F_T45, "pooled_wm_floor": F_FLOOR}},
        "results_by_target": res,
        "gates": gates,
        "ship_arm": ship,
        "fringe_keepalives": fringe,
        "verdict": f"SHIP {ship}" if ship else "NO SHIP",
    }
    if not ship:
        artifact["loss_ledger"] = {
            "verdict": "NO SHIP",
            "summary": "No RELIEF-SHAPE arm cleared the pre-registered pit additive bar. The pit "
                       "lean set is unchanged (the _vec keys stay inert). One attempt per arm is "
                       "spent; fringe-signature arms (if any) hold a keep-alive for a FUTURE "
                       "pre-registered fringe re-gate only.",
            "fringe_keepalives": fringe,
        }

    OUT_PATH.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
    print(f"RELIEF-SHAPE gate: {'PASS -> SHIP ' + ship if ship else 'FAIL -> NO SHIP'}")
    for k in ("RS-1", "RS-2", "RS-3"):
        d = res["censored"]["arms"][k]["delta"]
        g = gates[k]
        print(f"  {k} {res['censored']['arms'][k]['name']}: pooled d={d['spearman']} "
              f"wm d={d['within_tier_wm']} t45 d={d['t45']} tier d={d['per_tier']} "
              f"era d={d['era']} -> {'PASS' if g['pass'] else 'FAIL'}"
              f"{' (fringe signature)' if g['fringe_signature'] else ''}")
        dr = res["resolved"]["arms"][k]["delta"]
        print(f"       resolved sensitivity: pooled d={dr['spearman']} wm d={dr['within_tier_wm']} "
              f"t45 d={dr['t45']}")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
