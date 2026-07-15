# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""E-AGE (2026-07-14) -- absolute age as an eFV feature. NO-SHIP ledger.

Motivation (the Nathan Hickey case): the lean sets carry only age_rel_level,
which under-prices the outcome clock at old-skewing levels -- a 26.6yo AAA bat
reads as just "+2 vs level" while absolute age dominates a 6-year WAR window.
Feature tested: milb.age (age at the production read; emitted by efv_model._vec
since 2026-07-14, mean-imputed at 22.5) +/- an age_missing indicator.

Gate pre-registered in docs/efv-2026-07-14/GATES.md (E-AGE), BEFORE any run:
ship iff blended pooled rho >= baseline + 0.0046 (2x the 0.0023 identity-refit
noise floor) AND within-tier wm >= baseline - noise AND t45 >= baseline - noise.

Result on the standard forward-chained OOS protocol (tools/efv_ml_lab.py):
  hit + age(+ind): pooled sub-bar, wm/t45 positive
  hit + age only : pooled +0.0043 (0.0003 short of the bar), wm/t45 positive
  pit + age(+ind): pooled -0.0224, t45 -0.2235 -- the sparse age_missing
                   indicator DESTABILIZES pitchers (same class as the reverted
                   col_x_k sparse-column boosts)
  pit + age only : pooled +0.0019 (SUB-BAR), wm +0.0114, t45 +0.0117
Mechanical verdict: no variant clears the pre-registered pooled auto-ship bar.

SHIPPED ANYWAY (age-only, both sides) as an OWNER-DIRECTED decision
(2026-07-14, explicit ask: 26-27yo org arms like Andrew Moore must not rank
top-100): every measured metric moves >= -noise (a non-loss), and the
debuted-only OOS pool is structurally BLIND to the never-debut risk absolute
age targets - the 27yo-AA-dominator class busts out of the eval's sample
frame entirely. The indicator variant stays rejected.

The baselines below are pinned to the PRE-SHIP lean sets (explicit lists)
so the recorded deltas keep meaning after the ship (the module-level 'lean'
now includes age).

Writes data/xfv_age_feature_eval.json (fresh rerun of all four variants).
Run: python tools/efv_age_feature_lab.py
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

import efv_ml_lab as LABX

NOISE = 0.0023
BAR = 2 * NOISE

_LEAN_HIT = ["fv", "obp_rel", "k_rel", "peak_k_rel", "age_rel_level", "n_milb_seasons",
             "tool_hit", "tool_speed", "milb_missing", "is_ifa", "is_college", "ops_rel"]
_LEAN_PIT = ["fv", "peak_k_rel", "k_rel", "bb_rel", "age_rel_level", "x_era_k", "tool_fb"]

VARIANTS = [
    {"id": "hit_age", "side": "hit", "model": "ridge", "features": _LEAN_HIT + ["age", "age_missing"],
     "target": "censored", "blend": "war"},
    {"id": "hit_age_only", "side": "hit", "model": "ridge", "features": _LEAN_HIT + ["age"],
     "target": "censored", "blend": "war"},
    {"id": "pit_age", "side": "pit", "model": "ridge", "features": _LEAN_PIT + ["age", "age_missing"],
     "target": "censored", "blend": "war"},
    {"id": "pit_age_only", "side": "pit", "model": "ridge", "features": _LEAN_PIT + ["age"],
     "target": "censored", "blend": "war"},
]

OUT_PATH = ROOT / "data" / "xfv_age_feature_eval.json"


def main():
    # baselines = the PRE-SHIP lean sets (explicit), NOT feature_keys('lean')
    # which is age-inclusive after the ship
    base = {
        "hit": LABX.run_variant({"id": "base_hit", "side": "hit", "model": "ridge",
                                 "features": _LEAN_HIT, "target": "censored", "blend": "war"}),
        "pit": LABX.run_variant({"id": "base_pit", "side": "pit", "model": "ridge",
                                 "features": _LEAN_PIT, "target": "censored", "blend": "war"}),
    }
    results = [LABX.run_variant(v) for v in VARIANTS]
    verdicts = {}
    for r in results:
        side = "hit" if r["id"].startswith("hit") else "pit"
        b = base[side]
        d_pooled = (r.get("spearman") or 0.0) - (b.get("spearman") or 0.0)
        d_wm = (r.get("within_tier_wm") or 0.0) - (b.get("within_tier_wm") or 0.0)
        d_t45 = (r.get("t45") or 0.0) - (b.get("t45") or 0.0)
        verdicts[r["id"]] = {
            "d_pooled": round(d_pooled, 4), "d_wm": round(d_wm, 4), "d_t45": round(d_t45, 4),
            "pass_pooled_bar": d_pooled >= BAR,
            "pass_wm": d_wm >= -NOISE, "pass_t45": d_t45 >= -NOISE,
            "ship": d_pooled >= BAR and d_wm >= -NOISE and d_t45 >= -NOISE,
        }
    artifact = {
        "experiment": "xfv_age_feature",
        "generated_at": date.today().isoformat(),
        "gates_doc": "docs/efv-2026-07-14/GATES.md (E-AGE)",
        "noise_floor": NOISE, "pooled_bar": BAR,
        "baselines": {s: {k: base[s].get(k) for k in
                          ("spearman", "spearman_pure", "within_tier_wm", "t45", "era")}
                      for s in ("hit", "pit")},
        "variants": results,
        "verdicts": verdicts,
        "ship_decision": {
            "mechanical_ship": any(v["ship"] for v in verdicts.values()),
            "ship": True,
            "shipped_variant": "age-only, both sides (no indicator)",
            "summary": "OWNER-DIRECTED SHIP (2026-07-14): no variant clears the "
                       "pre-registered pooled auto-ship bar (best +0.0043, 0.0003 "
                       "short), but every metric moves >= -noise on the age-only "
                       "variants and the debuted-only eval pool cannot see the "
                       "never-debut org-arm risk the feature targets (the explicit "
                       "owner ask). The pit age_missing indicator variant stays "
                       "rejected (sparse-column instability).",
        },
    }
    OUT_PATH.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
    for rid, v in verdicts.items():
        print(f"{rid:14s} d_pooled={v['d_pooled']:+.4f} d_wm={v['d_wm']:+.4f} "
              f"d_t45={v['d_t45']:+.4f} ship={v['ship']}")
    print(f"wrote {OUT_PATH.name}")


if __name__ == "__main__":
    main()
