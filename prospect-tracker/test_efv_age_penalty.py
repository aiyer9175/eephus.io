# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Owner-directed live prospect-age penalty (2026-07-14, the Andrew Moore
directive). Mirrors the injury-penalty overlay: LIVE board only, multiplicative
on the model WAR term, surfaced as a "Prospect age penalty" factor chip.

2026-07-30: the hard gate at exactly 25.0 became a continuous ramp with the ONSET as
an owner policy dial, and the owner then moved the onset to 23.0. These tests were
written against the 25.0 gate and asserted its arithmetic directly, so they are now
expressed RELATIVE TO THE DIAL. The behaviour they exist to protect - young prospects
untouched, a monotone ramp past the onset, a hard floor, a safe fallback when age is
missing - is unchanged and is what is asserted here. The literal 25.0 constants moved
to test_efv_age_pipeline.py, which owns the dial's mechanism and its decided value.
"""

from __future__ import annotations

import efv_score as es
from efv_score import _age_factor

ONSET = es._AGE_PENALTY_ONSET
PER_YR = es._AGE_PENALTY_PER_YR
FLOOR = es._AGE_PENALTY_FLOOR
FLOOR_AGE = ONSET + (1.0 - FLOOR) / PER_YR      # age at which the floor is reached


def test_young_prospects_untouched():
    """Anything at or below the onset pays nothing. This is the clause that makes the
    penalty a penalty on being OLD for a prospect rather than a tax on everyone."""
    assert _age_factor({"age_now": 19.4}) == 1.0
    assert _age_factor({"age_now": ONSET - 3.0}) == 1.0
    assert _age_factor({"age_now": ONSET - 0.1}) == 1.0
    assert _age_factor({"age_now": ONSET}) == 1.0


def test_ramp_and_floor():
    """Monotone, linear at PER_YR past the onset, floored at FLOOR."""
    assert abs(_age_factor({"age_now": ONSET + 1.0}) - (1.0 - PER_YR)) < 1e-9
    assert abs(_age_factor({"age_now": ONSET + 1.9}) - (1.0 - 1.9 * PER_YR)) < 1e-9
    assert abs(_age_factor({"age_now": FLOOR_AGE}) - FLOOR) < 1e-9
    assert _age_factor({"age_now": FLOOR_AGE + 4.0}) == FLOOR      # floored
    # THE ANDREW MOORE CASE, the directive that created this overlay: a 26.9-year-old
    # prospect. Under the retired 25.0 gate he read 0.81; under the owner's 23.0 onset
    # he is at the floor. The case still pays, which is the point of the directive.
    assert _age_factor({"age_now": 26.9}) == FLOOR


def test_fallback_to_milb_age_and_missing_safe():
    """milb.age is the fallback when the decimal age is absent, and a missing age must
    never fabricate a penalty."""
    assert abs(_age_factor({"milb": {"age": ONSET + 2.0}})
               - max(FLOOR, 1.0 - 2.0 * PER_YR)) < 1e-9
    assert _age_factor({}) == 1.0
    assert _age_factor({"age_now": None, "milb": {}}) == 1.0


def test_wired_into_live_scoring_only():
    """The overlay must ride adj_factor in run_live (tilting the MODEL term,
    like the injury penalty) and must NOT appear in the resolved scoring path
    (resolved outcomes already embed age)."""
    from pathlib import Path
    src = (Path(__file__).parent / "efv_score.py").read_text(encoding="utf-8")
    assert "adj_factor = inj * sc * agef" in src
    assert '"Prospect age penalty"' in src
