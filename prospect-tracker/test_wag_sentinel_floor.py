# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FV-0 sentinel must not be measured as a grade (audit L15-F2).

152 graduate rows carry an FV of 0, which is a sentinel for "no grade", not a
grade. survivor_expected_war extrapolates FV 0 to 11.84 WAR per year for a hitter,
so every one of those players was measured against an expectation no real player
meets, and 136 of them were served the label 'bust'. The scale runs 20 to 80 and
the board serves 20.0 as its floor, so nothing below 20 is a real grade.
"""
from __future__ import annotations

import pytest

import storage


@pytest.mark.parametrize("fv", [0, 0.0, 5, 19.99, -1])
def test_below_the_scale_floor_has_no_expectation(fv):
    assert storage._fv_to_expected_war_per_yr(fv, is_pitcher=False) is None
    assert storage._fv_to_expected_war_per_yr(fv, is_pitcher=True) is None


@pytest.mark.parametrize("fv", [20, 30, 45, 60, 80])
def test_real_grades_still_price(fv):
    assert storage._fv_to_expected_war_per_yr(fv, is_pitcher=False) is not None


def test_the_sentinel_tail_was_absurd_which_is_why_it_is_refused():
    """The number the guard exists to keep out, measured on the engine itself.
    If the engine ever stops extrapolating this far the guard is still correct,
    but this records why it was needed."""
    import value_framework as vf
    raw = vf.survivor_expected_war(0.0, False)
    assert raw is None or raw > 5.0, (
        "FV 0 used to extrapolate to about 11.8 WAR per year; a sentinel must never "
        "be compared against that")


def test_a_graduate_with_no_grade_reads_unsettled_not_bust():
    """End to end through the labeller: no expectation means no WAG, which the
    boom/bust labeller already reads as 'unsettled', the honest answer."""
    payload = {"fv_close": 0.0, "is_pitcher": False,
               "career_war": {"total": 0.4, "seasons": {"2024": 0.4}},
               "career_stats": [{"level": "MLB", "season": 2024, "pa": 300}]}
    assert storage._grad_wag(payload) is None
    assert storage._compute_boom_bust(payload) == "unsettled"
