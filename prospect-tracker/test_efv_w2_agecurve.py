# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The age-curve columns (EFV4_AGE_CURVE): shapes and the as-of rule, on fixtures."""
import efv_w2_agecurve as A
import efv_w2_milb as M

AGES = sorted([20.0] * 5 + [22.0] * 20 + [24.0] * 40 + [26.0] * 25 + [28.0] * 10)


def test_youngest_scores_highest_and_oldest_lowest():
    young, old = A.position(20.0, AGES), A.position(28.0, AGES)
    for c in A.CURVES:
        assert A.curve_value(c, *young, "AA") > 0 > A.curve_value(c, *old, "AA")


def test_graded_curve_moves_the_tails_most():
    mid, edge = A.position(24.0, AGES), A.position(20.0, AGES)
    step_mid = abs(A.curve_value("c2_graded", *mid, "AA"))
    step_edge = abs(A.curve_value("c2_graded", *edge, "AA"))
    assert step_edge > 3 * step_mid
    assert abs(A.curve_value("c2_graded", 10.0, 1.0, "AA")) <= A.CLIP


def test_tails_curve_is_zero_in_the_middle():
    assert A.curve_value("c3_tails", 0.0, 0.5, "A") == 0.0


def test_level_weight_scales_the_graded_curve():
    z, p = A.position(20.0, AGES)
    g = A.curve_value("c2_graded", z, p, "A")
    assert A.curve_value("c4_graded_level", z, p, "AAA") == g * A.LEVEL_WEIGHT["AAA"]


def test_thin_distribution_gives_no_value():
    assert A.position(22.0, [22.0] * (M.NORM_MIN_LINES - 1)) is None


def test_profile_reads_nothing_after_the_cutoff(monkeypatch):
    seen = []

    def lines(season, side):
        seen.append(season)
        return {}
    monkeypatch.setattr(M, "season_lines", lines)
    A.profile(123, 2018, "2017-06-01", "hit", 2005)
    assert max(seen) <= 2016
