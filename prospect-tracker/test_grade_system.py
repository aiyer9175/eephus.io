# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""v6 farm-grade overhaul — covers:

  * Harsher letter scale: F at the bottom, D- in the 93-97% band, A
    reserved for the top 7% (was 10%).
  * Composite stretch: `_stretch_composite` magnifies distance from the
    league mean, monotonic + clamped to [0, 100].
  * 6y window: `FARM_TRAJECTORY_WINDOWS` carries "6y" (not "5y"); the
    blended `trajectory_score` weights 60% 6y / 30% 3y / 10% 1y.
  * 6y per-tool DvM+ window: `_compute_tool_deltas` honors a 6-year
    lookback by default and drops snapshots older than that.
  * 6y Conviction recency window: `_CONVICTION_RECENCY_YEARS == 6`.
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from storage import (
    FARM_TOOL_DELTA_LOOKBACK_DAYS,
    FARM_TRAJECTORY_WINDOWS,
    _CONVICTION_RECENCY_YEARS,
    _compute_tool_deltas,
    _letter_grade,
    _stretch_composite,
)


# ---------------------------------------------------------------------------
# Letter scale — v6 harsher curve with F + D-
# ---------------------------------------------------------------------------

class TestLetterGradeV6(unittest.TestCase):
    """Pin the v6 distribution boundaries on a canonical 30-org pool."""

    N = 30  # canonical MLB-org-count pool

    def test_rank_1_is_a_plus(self):
        self.assertEqual(_letter_grade(1, self.N), "A+")

    def test_rank_2_is_a(self):
        # pct = (2-1)/(30-1) = 0.034 → "A" (< 0.07)
        self.assertEqual(_letter_grade(2, self.N), "A")

    def test_a_minus_starts_at_pct_07(self):
        # rank 4: pct = 3/29 ≈ 0.103 → A-; rank 3: pct = 2/29 ≈ 0.069 → A
        self.assertEqual(_letter_grade(3, self.N), "A")
        self.assertEqual(_letter_grade(4, self.N), "A-")

    def test_b_plus_band(self):
        # 14% cutoff: rank 5/30 → pct 4/29 = 0.138 → A-, rank 6 → B+
        self.assertEqual(_letter_grade(5, self.N), "A-")
        self.assertEqual(_letter_grade(6, self.N), "B+")

    def test_middle_is_b_minus(self):
        # rank 15: pct = 14/29 ≈ 0.483 → B- (< 0.50 cutoff)
        self.assertEqual(_letter_grade(15, self.N), "B-")

    def test_c_minus_band_visible(self):
        # rank 23: pct = 22/29 ≈ 0.759 → C- (≥ 0.74 cutoff)
        # rank 22: pct = 21/29 ≈ 0.724 → C (< 0.74 cutoff)
        self.assertEqual(_letter_grade(22, self.N), "C")
        self.assertEqual(_letter_grade(23, self.N), "C-")

    def test_d_band(self):
        # rank 26: pct = 25/29 ≈ 0.862 → D; rank 25: ≈ 0.828 → C-
        self.assertEqual(_letter_grade(25, self.N), "C-")
        self.assertEqual(_letter_grade(26, self.N), "D")

    def test_d_minus_appears_above_f(self):
        # rank 29: pct = 28/29 ≈ 0.966 → D- (< 0.97 cutoff)
        self.assertEqual(_letter_grade(29, self.N), "D-")

    def test_f_is_bottom_rank(self):
        # rank 30: pct = 29/29 = 1.0 → F
        self.assertEqual(_letter_grade(30, self.N), "F")

    def test_n_one_pool_is_a_plus(self):
        # Single-org pool — trivially top.
        self.assertEqual(_letter_grade(1, 1), "A+")

    def test_zero_n_safe(self):
        self.assertEqual(_letter_grade(1, 0), "—")

    def test_none_rank_safe(self):
        self.assertEqual(_letter_grade(None, 30), "—")

    def test_no_f_in_small_pool(self):
        # 3-org pool: rank 3 → pct = 1.0 → F (the scale still applies
        # uniformly). This is intentional — small pools that need
        # softer treatment should sit on a different mechanism.
        self.assertEqual(_letter_grade(3, 3), "F")


# ---------------------------------------------------------------------------
# Composite stretch — magnifies distance from the mean, monotonic + clamped
# ---------------------------------------------------------------------------

class TestStretchComposite(unittest.TestCase):
    """Stretch defaults to mean=100 (the DvM+-style anchor used by
    the farm-tree composite). Above-mean lifts further, below-mean
    drops further, and rank order is preserved."""

    def test_mean_unchanged(self):
        # 100 sits at the mean — stretched back to 100.
        self.assertAlmostEqual(_stretch_composite(100.0), 100.0, places=1)

    def test_above_mean_pulled_higher(self):
        # 120 (20 above mean=100) should stretch further above.
        s = _stretch_composite(120.0)
        self.assertGreater(s, 120.0)

    def test_below_mean_pulled_lower(self):
        # 80 (20 below mean=100) should stretch further below.
        s = _stretch_composite(80.0)
        self.assertLess(s, 80.0)

    def test_symmetric_around_mean(self):
        # Distance preserved in shape — above and below stretch by the
        # same magnitude.
        above = _stretch_composite(120.0) - 100.0
        below = 100.0 - _stretch_composite(80.0)
        self.assertAlmostEqual(above, below, places=1)

    def test_factor_1_35_widens_by_35pct(self):
        # 110 → 100 + 10*1.35 = 113.5
        self.assertAlmostEqual(_stretch_composite(110.0), 113.5, places=1)
        # 90 → 100 - 10*1.35 = 86.5
        self.assertAlmostEqual(_stretch_composite(90.0), 86.5, places=1)

    def test_monotonic(self):
        # Larger inputs → larger outputs across the realistic composite
        # range (75 – 130).
        prev = -1.0
        for v in [75, 85, 90, 95, 100, 105, 110, 115, 125]:
            s = _stretch_composite(float(v))
            self.assertGreater(s, prev)
            prev = s

    def test_clamps_below_0(self):
        # Defensive — a negative input shouldn't slip through.
        self.assertEqual(_stretch_composite(-5.0), 0.0)

    def test_unbounded_above(self):
        # Upper end isn't clamped — composite can exceed 100 since each
        # branch is DvM+-style (mean=100, sigma=10).
        s = _stretch_composite(130.0)
        self.assertGreater(s, 130.0)  # 100 + 30*1.35 = 140.5

    def test_explicit_mean_50_works_for_legacy_callers(self):
        # The function accepts an explicit mean override (for any
        # caller using the legacy 0-100 scale).
        self.assertAlmostEqual(_stretch_composite(70.0, mean=50.0), 77.0, places=1)
        self.assertAlmostEqual(_stretch_composite(30.0, mean=50.0), 23.0, places=1)

    def test_none_passes_through(self):
        # Defensive — `None` in, `None` out (callers may pass missing).
        self.assertIsNone(_stretch_composite(None))


# ---------------------------------------------------------------------------
# 6y window — DvM+ trajectory dict + Conviction recency
# ---------------------------------------------------------------------------

class TestSixYearWindow(unittest.TestCase):
    def test_trajectory_windows_carry_6y(self):
        self.assertIn("6y", FARM_TRAJECTORY_WINDOWS)
        self.assertEqual(FARM_TRAJECTORY_WINDOWS["6y"], 365 * 6)

    def test_trajectory_windows_no_5y(self):
        # 5y was renamed wholesale to 6y in v6.
        self.assertNotIn("5y", FARM_TRAJECTORY_WINDOWS)

    def test_trajectory_windows_keeps_1y_3y(self):
        # The shorter windows still exist for the blended trajectory.
        self.assertIn("1y", FARM_TRAJECTORY_WINDOWS)
        self.assertIn("3y", FARM_TRAJECTORY_WINDOWS)

    def test_conviction_recency_is_6_years(self):
        self.assertEqual(_CONVICTION_RECENCY_YEARS, 6)

    def test_tool_delta_lookback_constant_is_6_years(self):
        self.assertEqual(FARM_TOOL_DELTA_LOOKBACK_DAYS, 365 * 6)


# ---------------------------------------------------------------------------
# `_compute_tool_deltas` 6y window — drops older snapshots
# ---------------------------------------------------------------------------

class TestToolDeltasSixYearWindow(unittest.TestCase):
    def _today(self) -> date:
        return date.today()

    def _iso(self, d: date) -> str:
        return d.isoformat()

    def test_in_window_snapshots_pair_normally(self):
        # Both observations inside the 6y window → delta computed.
        today = self._today()
        recent = self._iso(today - timedelta(days=400))
        very_recent = self._iso(today - timedelta(days=30))
        out = _compute_tool_deltas([
            {"snapshot_date": recent,      "tools_consensus": {"hit": 50.0}},
            {"snapshot_date": very_recent, "tools_consensus": {"hit": 55.0}},
        ])
        self.assertIn("hit", out)
        self.assertEqual(out["hit"]["delta"], 5.0)
        self.assertEqual(out["hit"]["first"], 50.0)
        self.assertEqual(out["hit"]["last"], 55.0)

    def test_out_of_window_snapshots_dropped(self):
        # The 7-year-old observation falls outside the 6y window and
        # is ignored → only 1 in-window observation → no delta.
        today = self._today()
        too_old = self._iso(today - timedelta(days=365 * 7))
        in_window = self._iso(today - timedelta(days=30))
        out = _compute_tool_deltas([
            {"snapshot_date": too_old,    "tools_consensus": {"hit": 40.0}},
            {"snapshot_date": in_window,  "tools_consensus": {"hit": 55.0}},
        ])
        # Only 1 in-window observation → skipped (no delta).
        self.assertNotIn("hit", out)

    def test_first_in_window_obs_is_the_anchor(self):
        # The earliest in-window snapshot becomes "first" — pre-window
        # observations don't anchor the delta even though they exist.
        today = self._today()
        pre_window = self._iso(today - timedelta(days=365 * 8))  # dropped
        oldest_in = self._iso(today - timedelta(days=365 * 5))   # kept
        recent    = self._iso(today - timedelta(days=30))         # kept
        out = _compute_tool_deltas([
            {"snapshot_date": pre_window, "tools_consensus": {"power": 35.0}},
            {"snapshot_date": oldest_in,  "tools_consensus": {"power": 45.0}},
            {"snapshot_date": recent,     "tools_consensus": {"power": 55.0}},
        ])
        # First in-window = 45, last = 55, delta = +10 (NOT +20 vs the
        # pre-window 35).
        self.assertEqual(out["power"]["first"], 45.0)
        self.assertEqual(out["power"]["last"], 55.0)
        self.assertEqual(out["power"]["delta"], 10.0)

    def test_lookback_override_opts_out(self):
        # Passing a huge lookback turns the helper back into a lifetime
        # delta — for callers that legitimately want lifetime numbers.
        today = self._today()
        ancient = self._iso(today - timedelta(days=365 * 12))
        recent  = self._iso(today - timedelta(days=30))
        out = _compute_tool_deltas([
            {"snapshot_date": ancient, "tools_consensus": {"hit": 40.0}},
            {"snapshot_date": recent,  "tools_consensus": {"hit": 60.0}},
        ], lookback_days=365 * 20)
        self.assertEqual(out["hit"]["delta"], 20.0)

    def test_explicit_as_of_anchors_window(self):
        # Walk back a fixed anchor so the test is deterministic.
        # Snapshots at T-365 + T-1 inside 6y of T → delta visible.
        anchor = date(2024, 6, 15)
        in1 = "2023-06-15"   # 1 year before anchor → in-window
        in2 = "2024-06-14"   # 1 day before anchor  → in-window
        out_of = "2017-01-01"  # 7+ years before anchor → out
        out = _compute_tool_deltas([
            {"snapshot_date": out_of, "tools_consensus": {"hit": 40.0}},
            {"snapshot_date": in1,    "tools_consensus": {"hit": 50.0}},
            {"snapshot_date": in2,    "tools_consensus": {"hit": 55.0}},
        ], as_of=anchor.isoformat())
        self.assertEqual(out["hit"]["first"], 50.0)
        self.assertEqual(out["hit"]["last"], 55.0)


# ---------------------------------------------------------------------------
# Stretch + letter-grade integration — ensures order is preserved
# ---------------------------------------------------------------------------

class TestStretchPreservesRankOrder(unittest.TestCase):
    """A monotonic remap must preserve the rank order, otherwise the
    letter-grading downstream would be inconsistent with the displayed
    composite."""

    def test_rank_order_preserved(self):
        # Realistic composite distribution: roughly centered on 100,
        # range [75, 130].
        raw = [128.0, 118.0, 110.0, 105.0, 100.0, 95.0, 88.0, 78.0]
        stretched = [_stretch_composite(v) for v in raw]
        # Ranks should be identical: higher in → higher out.
        for i in range(len(raw) - 1):
            self.assertGreater(stretched[i], stretched[i + 1])


if __name__ == "__main__":
    unittest.main()
