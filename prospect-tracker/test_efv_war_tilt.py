# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Regression pins for efv_score._apply_war_tilt (sign-aware live-overlay
tilt, audit fix 2026-07-14).

The bug being pinned: for a NEGATIVE WAR projection, war * factor INVERTS the
intended direction - a penalty factor (<1) moved the projection TOWARD zero
(up), so an injured fringe arm leapfrogged his healthy peers while his factor
chip read "penalty". The fix divides for war < 0 (symmetric and monotone
across the sign boundary, floored at the model floor -2.0). Nothing else in
the suite asserts the sign invariant, so a revert to war * factor would pass
without these tests.
"""

import pytest

from efv_score import _apply_war_tilt


class TestPenaltyDirection:
    def test_penalty_lowers_negative_war(self):
        # factor 0.9 on war -1.0 must move the projection DOWN (below -1.0).
        # The reverted (war * factor) form returns -0.9, i.e. a raise.
        assert _apply_war_tilt(-1.0, 0.9) < -1.0
        assert _apply_war_tilt(-1.0, 0.9) == pytest.approx(-1.0 / 0.9)

    def test_penalty_lowers_positive_war(self):
        assert _apply_war_tilt(2.0, 0.9) == pytest.approx(1.8)

    def test_boost_raises_negative_war(self):
        # factor 1.1 on war -1.0 moves it toward zero (up), never further down.
        out = _apply_war_tilt(-1.0, 1.1)
        assert -1.0 < out < 0.0
        assert out == pytest.approx(-1.0 / 1.1)

    def test_boost_raises_positive_war(self):
        assert _apply_war_tilt(1.0, 1.1) == pytest.approx(1.1)


class TestMonotoneAcrossSign:
    def test_penalty_preserves_ordering_through_zero(self):
        """A fixed penalty factor must keep the WAR ordering intact across
        the sign boundary - no leapfrogging at war = 0."""
        wars = [-1.5, -0.5, -0.1, 0.0, 0.1, 0.5, 1.5]
        tilted = [_apply_war_tilt(w, 0.85) for w in wars]
        assert tilted == sorted(tilted), (
            f"penalty inverted ordering across the sign boundary: {tilted}")

    def test_boost_preserves_ordering_through_zero(self):
        wars = [-1.5, -0.5, -0.1, 0.0, 0.1, 0.5, 1.5]
        tilted = [_apply_war_tilt(w, 1.15) for w in wars]
        assert tilted == sorted(tilted)


class TestEdges:
    def test_floor_at_model_floor(self):
        # Dividing a deep negative by a strong penalty is floored at -2.0.
        assert _apply_war_tilt(-1.9, 0.7) == -2.0

    def test_neutral_factor_is_noop(self):
        assert _apply_war_tilt(-1.23, 1.0) == -1.23
        assert _apply_war_tilt(0.0, 1.0) == 0.0

    def test_none_war_passthrough(self):
        assert _apply_war_tilt(None, 1.0) is None

    def test_zero_war_unmoved_by_any_factor(self):
        assert _apply_war_tilt(0.0, 0.7) == 0.0
        assert _apply_war_tilt(0.0, 1.18) == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
