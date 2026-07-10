# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Regression tests for the pre-Beta model-audit correctness fixes.

Each test locks one confirmed defect so it cannot silently return:
  M8  draft_export._stock_plus collapsed fractional consensus ranks via int()
  M10 proj_ml.age_from_history offset was anchored to the wrong history row
  R1  proj_ml._implied_mean weights (docstring lock, not a trapezoid)
"""
from __future__ import annotations

import draft_export
import proj_ml


def test_stock_plus_keeps_fractional_ranks_distinct():
    # Two prospects at 4.4 and 4.6 must NOT collapse to the same DS+ (the old
    # int() truncation made both rank "4"). A dense top of board stays separable.
    class_ranks = [1.0, 2.0, 3.0, 4.4, 4.6, 6.0, 7.0, 8.0, 9.0, 10.0]
    a = draft_export._stock_plus(4.4, class_ranks)
    b = draft_export._stock_plus(4.6, class_ranks)
    assert a is not None and b is not None
    assert a > b                                    # lower rank = higher stock
    # exact ties still share a value
    assert draft_export._stock_plus(4.4, class_ranks) == a


def test_age_from_history_anchors_to_age_row():
    # hist is most-recent-first. The most recent row (base-1) has WAR but a null
    # age; the older row carries the age. Age at base=2025 must be 27+(2025-2023)
    # = 29, NOT 27+(2025-2024)=28 (the old hist[0]-anchored bug).
    hist = [{"season": 2024, "age": None}, {"season": 2023, "age": 27}]
    assert proj_ml.age_from_history(hist, 2025) == 29
    # normal case: most recent row has the age
    assert proj_ml.age_from_history([{"season": 2024, "age": 26}], 2025) == 27
    # no age anywhere -> None
    assert proj_ml.age_from_history([{"season": 2024, "age": None}], 2025) is None


def test_implied_mean_weights_locked():
    # (1,2,2,2,1)/8 quantile-mass weighting - deliberately NOT a trapezoid.
    assert proj_ml._implied_mean(0, 1, 2, 3, 4) == 2.0
    assert proj_ml._implied_mean(0, 0, 0, 0, 10) == 1.25
