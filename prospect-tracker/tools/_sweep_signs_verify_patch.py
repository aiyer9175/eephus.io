"""Verify the PROPOSED declaration patch makes the sign guard pass, WITHOUT editing
the files this lane may not touch (efv_model.py / efv_ungraded.py). Monkeypatches the
declaration tables to the proposed values, then runs efv_sign_audit + the guard tests.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import efv_model as M
import efv_ungraded as U
import efv_sign_audit as sa

PATCHED_HIT = [
    ("fv", +1), ("obp_rel", +1), ("k_rel", 0), ("peak_k_rel", -1),
    ("age_rel_level", -1), ("n_milb_seasons", 0), ("tool_hit", +1),
    ("tool_speed", +1), ("milb_missing", 0), ("is_ifa", 0), ("is_college", 0),
    ("ops_rel", +1), ("age", -1), ("level_rank", +1),
]
PATCHED_PIT = [
    ("fv", +1), ("peak_k_rel", +1), ("k_rel", +1), ("bb_rel", -1),
    ("age_rel_level", -1), ("x_era_k", +1), ("tool_fb", +1), ("age", 0),
]
PATCHED_NOFV_MONO = {
    "obp_rel": +1, "ops_rel": +1, "peak_obp_rel": +1, "iso_rel": +1,
    "k_rel": None, "peak_k_rel": None,          # side-dependent, inherit the flagship
    "bb_rel": -1, "era_rel": -1, "x_era_k": +1,
    "age_rel_level": -1, "level_rank": +1, "n_milb_seasons": 0,
}

M._FEATURES_HIT[:] = PATCHED_HIT
M._FEATURES_PIT[:] = PATCHED_PIT
U._NOFV_MONO = {k: v for k, v in PATCHED_NOFV_MONO.items() if v is not None}

ok = True
for side in ("hit", "pit"):
    c = sa.contradictions(side)
    print("flagship", side, "contradictions:", c or "NONE")
    ok &= not c
for side in ("hit", "pit"):
    rows = sa.audit_provisional(side)
    bad = {k: v for k, v in rows.items() if v["contradiction"]}
    und = [k for k, v in rows.items() if v["declared"] is None]
    print("provisional", side, "contradictions:", bad or "NONE", "| undeclared:", und or "NONE")
    ok &= not bad and not und
print("PATCH CLEAN:", ok)
