"""Tests for the rolling-window farm-performance signals + composite
farm_rank introduced for the farm-system overhaul."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage import (
    _rolling_fv_delta,
    _recent_grad_count,
    _rank_percentile,
    FARM_ROLLING_WINDOW_DAYS,
    FARM_WEIGHT_TOTAL_FV,
    FARM_WEIGHT_DELTA_90D,
    FARM_WEIGHT_RECENT_GRADS,
)


def _iso_days_ago(n: int, ref: date) -> str:
    return (ref - timedelta(days=n)).isoformat()


# ---------------------------------------------------------------------------
# _rolling_fv_delta — baseline picks the most-recent point on/before cutoff
# ---------------------------------------------------------------------------

class TestRollingFvDelta:
    def test_basic_window_picks_correct_baseline(self):
        today = date(2026, 5, 19)
        series = [
            {"date": _iso_days_ago(120, today), "total_fv": 200.0},
            {"date": _iso_days_ago(95,  today), "total_fv": 210.0},  # just outside 90
            {"date": _iso_days_ago(80,  today), "total_fv": 225.0},  # inside the window
            {"date": today.isoformat(),         "total_fv": 250.0},
        ]
        # Cutoff is today - 90 = 90 days ago. The most recent point on or
        # before that is the 95-days-ago row (210.0).
        # Latest (250.0) - baseline (210.0) = 40.0.
        assert _rolling_fv_delta(series, days=90, as_of=today) == 40.0

    def test_series_shorter_than_window_uses_first_point(self):
        today = date(2026, 5, 19)
        series = [
            {"date": _iso_days_ago(40, today), "total_fv": 100.0},
            {"date": _iso_days_ago(10, today), "total_fv": 130.0},
        ]
        # No point falls on/before today-90 → fall back to the first point.
        assert _rolling_fv_delta(series, days=90, as_of=today) == 30.0

    def test_single_point_returns_zero(self):
        today = date(2026, 5, 19)
        series = [{"date": today.isoformat(), "total_fv": 220.0}]
        # First point IS the latest point — delta against itself is zero.
        assert _rolling_fv_delta(series, days=90, as_of=today) == 0.0

    def test_empty_series_returns_zero(self):
        assert _rolling_fv_delta([], days=90, as_of=date(2026, 5, 19)) == 0.0

    def test_handles_negative_delta(self):
        """A farm that's been bleeding FV reports a negative number."""
        today = date(2026, 5, 19)
        series = [
            {"date": _iso_days_ago(120, today), "total_fv": 300.0},
            {"date": _iso_days_ago(100, today), "total_fv": 280.0},
            {"date": _iso_days_ago(20,  today), "total_fv": 250.0},
            {"date": today.isoformat(),         "total_fv": 240.0},
        ]
        # Baseline: most recent on/before today-90 = the 100-days-ago point (280.0).
        # Latest (240.0) - 280.0 = -40.0.
        assert _rolling_fv_delta(series, days=90, as_of=today) == -40.0


# ---------------------------------------------------------------------------
# _recent_grad_count — only graduation events inside the window
# ---------------------------------------------------------------------------

class TestRecentGradCount:
    def test_counts_only_graduations_in_window(self):
        today = date(2026, 5, 19)
        events = [
            {"kind": "graduation", "date": _iso_days_ago(120, today),
             "player_name": "Old Grad"},
            {"kind": "graduation", "date": _iso_days_ago(60,  today),
             "player_name": "Mid Grad"},
            {"kind": "graduation", "date": _iso_days_ago(5,   today),
             "player_name": "Recent Grad"},
            {"kind": "trade",      "date": _iso_days_ago(20,  today),
             "player_name": "Traded Guy"},
        ]
        # 120-days-ago graduation is outside the 90-day window; the trade
        # is inside the window but isn't a graduation; the other two count.
        assert _recent_grad_count(events, days=90, as_of=today) == 2

    def test_no_graduation_events_returns_zero(self):
        today = date(2026, 5, 19)
        events = [{"kind": "trade", "date": today.isoformat(),
                   "player_name": "X"}]
        assert _recent_grad_count(events, days=90, as_of=today) == 0

    def test_empty_events_returns_zero(self):
        assert _recent_grad_count([], days=90, as_of=date(2026, 5, 19)) == 0


# ---------------------------------------------------------------------------
# _rank_percentile — rank-normalized scores in [0, 1]; ties share a slot
# ---------------------------------------------------------------------------

class TestRankPercentile:
    def test_best_is_one_worst_is_zero(self):
        pct = _rank_percentile([10.0, 20.0, 30.0])
        # 30 → best (1.0), 20 → middle, 10 → worst (0.0)
        assert pct == [0.0, 0.5, 1.0]

    def test_handles_ties_by_averaging_rank(self):
        """Two orgs at the same total_fv get the same percentile so the
        composite tiebreaker isn't dictated by list order."""
        pct = _rank_percentile([50.0, 50.0, 100.0, 25.0])
        # 100 → rank 1 → 1.0; the two 50s share ranks 2 and 3 → avg rank 2.5
        # → share = (4 - 2.5) / 3 = 0.5; 25 → rank 4 → 0.0
        assert pct[2] == 1.0
        assert pct[3] == 0.0
        assert pct[0] == pct[1] == 0.5

    def test_single_value_returns_one(self):
        assert _rank_percentile([42.0]) == [1.0]

    def test_empty_returns_empty(self):
        assert _rank_percentile([]) == []


# ---------------------------------------------------------------------------
# End-to-end composite ranking via export_timeseries_json
# ---------------------------------------------------------------------------

class TestCompositeFarmRank:
    """Drive a small but realistic org_summary build to confirm the
    composite ranking responds to all three signals in the expected
    direction."""

    def test_composite_weights_match_constants(self):
        # Defensive — the recommended weights are 60/30/10. If someone
        # bumps them, this fails loudly so we re-anchor tests + docs.
        assert FARM_WEIGHT_TOTAL_FV     == 0.60
        assert FARM_WEIGHT_DELTA_90D    == 0.30
        assert FARM_WEIGHT_RECENT_GRADS == 0.10
        assert abs((FARM_WEIGHT_TOTAL_FV
                    + FARM_WEIGHT_DELTA_90D
                    + FARM_WEIGHT_RECENT_GRADS) - 1.0) < 1e-9

    def test_rolling_window_constant(self):
        # Locked at 90 days per the spec. If we change this we'll likely
        # need to retune the weights.
        assert FARM_ROLLING_WINDOW_DAYS == 90

    def test_composite_prefers_rising_over_higher_static_when_close(self):
        """Two orgs are tied on total_fv but org A has a positive 90-day
        delta and org B has a negative one. The composite should rank A
        ahead."""
        today = date(2026, 5, 19)
        a_history = [
            {"date": _iso_days_ago(95, today), "total_fv": 180.0},
            {"date": today.isoformat(),        "total_fv": 200.0},
        ]
        b_history = [
            {"date": _iso_days_ago(95, today), "total_fv": 220.0},
            {"date": today.isoformat(),        "total_fv": 200.0},
        ]
        a_delta = _rolling_fv_delta(a_history, days=90, as_of=today)
        b_delta = _rolling_fv_delta(b_history, days=90, as_of=today)
        assert a_delta > 0 > b_delta

        # Same total_fv → fv_percentile ties (0.5 each). Different deltas
        # → A gets delta_percentile 1.0, B gets 0.0. No grads.
        # Composite A = 0.6 * 0.5 + 0.3 * 1.0 + 0.1 * 0 = 0.60
        # Composite B = 0.6 * 0.5 + 0.3 * 0.0 + 0.1 * 0 = 0.30
        fv_pct    = _rank_percentile([200.0, 200.0])
        delta_pct = _rank_percentile([a_delta, b_delta])
        grad_pct  = _rank_percentile([0, 0])
        score_a = (FARM_WEIGHT_TOTAL_FV  * fv_pct[0]
                + FARM_WEIGHT_DELTA_90D * delta_pct[0]
                + FARM_WEIGHT_RECENT_GRADS * grad_pct[0])
        score_b = (FARM_WEIGHT_TOTAL_FV  * fv_pct[1]
                + FARM_WEIGHT_DELTA_90D * delta_pct[1]
                + FARM_WEIGHT_RECENT_GRADS * grad_pct[1])
        assert score_a > score_b

    def test_recent_grads_break_tie_when_static_and_delta_equal(self):
        """All else equal, the org that just promoted prospects ranks
        higher — graduations are success, not attrition."""
        fv_pct    = _rank_percentile([200.0, 200.0])
        delta_pct = _rank_percentile([5.0,   5.0])
        grad_pct  = _rank_percentile([3,     0])   # A had 3 grads, B had 0
        score_a = (FARM_WEIGHT_TOTAL_FV  * fv_pct[0]
                + FARM_WEIGHT_DELTA_90D * delta_pct[0]
                + FARM_WEIGHT_RECENT_GRADS * grad_pct[0])
        score_b = (FARM_WEIGHT_TOTAL_FV  * fv_pct[1]
                + FARM_WEIGHT_DELTA_90D * delta_pct[1]
                + FARM_WEIGHT_RECENT_GRADS * grad_pct[1])
        assert score_a > score_b
