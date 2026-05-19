"""Tests for the farm-system grading helpers introduced in the
report-card overhaul that replaced the 60/30/10 composite + 90-day form.
The trajectory window was later widened from 90 days to 1 year and the
fv_history series was made graduation-neutral."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage import (
    FV_POINTS,
    FARM_WEIGHT_TOP_END,
    FARM_WEIGHT_DEPTH,
    FARM_WEIGHT_TRAJECTORY,
    FARM_WEIGHT_GRAD,
    FARM_TRAJECTORY_LOOKBACK_DAYS,
    FARM_TRAJECTORY_SMOOTH_WINDOW,
    FARM_GRAD_PIPELINE_MONTHS,
    _fv_to_points,
    _top_end_points,
    _depth_points,
    _trajectory_score,
    _grad_pipeline_score,
    _rank_percentile,
    _normalize_to_100,
    _rank_descending,
    _letter_grade,
    _build_org_fv_history,
)
from types import SimpleNamespace


def _iso_days_ago(n: int, ref: date) -> str:
    return (ref - timedelta(days=n)).isoformat()


# ---------------------------------------------------------------------------
# FV_POINTS curve + interpolation
# ---------------------------------------------------------------------------

class TestFvToPoints:
    def test_table_anchors_match(self):
        # Spot-check a few tiers — these anchor the curve and tests below.
        assert _fv_to_points(80) == 100.0
        assert _fv_to_points(70) == 50.0
        assert _fv_to_points(60) == 18.0
        assert _fv_to_points(50) == 5.0
        assert _fv_to_points(40) == 1.0

    def test_interpolates_between_tiers(self):
        # 57.5 sits halfway between FV 55 (10.0) and FV 60 (18.0).
        # Expected: 10 + 0.5 * (18 - 10) = 14.0
        assert _fv_to_points(57.5) == 14.0

    def test_plus_grades_via_half_step(self):
        # "55+" semantically is a 57.5 — the existing CSV stores rounded
        # consensus_fv_raw floats, so we test the float path that the
        # pipeline actually uses. Half-step interpolation gives 14.0.
        assert _fv_to_points(57.5) == 14.0

    def test_geometric_top_is_dominant(self):
        # The whole point of the tiered curve: top-tier prospects swamp
        # org-filler. An 80 should be worth far more than 50 filler 40s.
        # (Exact ratio per the table: 80 = 100, 40 = 1, so 80 ≈ 100 × 40.)
        assert _fv_to_points(80) > 50 * _fv_to_points(40)

    def test_none_and_garbage_safe(self):
        assert _fv_to_points(None) == 0.0
        assert _fv_to_points("not a number") == 0.0
        assert _fv_to_points(15) == 0.0   # sub-floor returns 0

    def test_clamps_above_80(self):
        # Future-proofing: if a source ever emits 85 it shouldn't crash
        # or return a nonsense value.
        assert _fv_to_points(85) == FV_POINTS[80]


# ---------------------------------------------------------------------------
# Top-end + depth slices of the prospect list
# ---------------------------------------------------------------------------

class TestTopEndAndDepth:
    def _make_prospects(self, fvs):
        return [{"name": f"P{i}", "fv_raw": fv} for i, fv in enumerate(fvs)]

    def test_top_end_sums_top_five(self):
        # Star-heavy roster — the top 5 dominate.
        ps = self._make_prospects([70, 65, 60, 55, 50, 45, 45, 40])
        expected = (_fv_to_points(70) + _fv_to_points(65) + _fv_to_points(60)
                    + _fv_to_points(55) + _fv_to_points(50))
        assert _top_end_points(ps) == round(expected, 2)

    def test_top_end_short_roster(self):
        # Org with only 2 graded prospects still gets a clean number — no
        # IndexError, just sums what's there.
        ps = self._make_prospects([70, 50])
        assert _top_end_points(ps) == round(_fv_to_points(70) + _fv_to_points(50), 2)

    def test_depth_skips_top_five(self):
        # Depth must exclude the top 5 — otherwise top-end is double-counted.
        ps = self._make_prospects([70, 65, 60, 55, 50, 45, 45, 40, 40])
        depth_only = (_fv_to_points(45) + _fv_to_points(45)
                      + _fv_to_points(40) + _fv_to_points(40))
        assert _depth_points(ps) == round(depth_only, 2)

    def test_depth_zero_when_no_secondary_prospects(self):
        ps = self._make_prospects([60, 55, 50])   # < 5 prospects total
        assert _depth_points(ps) == 0.0


# ---------------------------------------------------------------------------
# Smoothed trajectory — the user's main complaint was the old 90-day delta
# being whipsawed by single source updates. The window was widened to 1 year
# so the form chart and trajectory score reflect a fuller arc.
# ---------------------------------------------------------------------------

class TestTrajectoryScore:
    def test_empty_and_single_point_return_zero(self):
        today = date(2026, 5, 19)
        assert _trajectory_score([], as_of=today) == 0.0
        assert _trajectory_score(
            [{"date": today.isoformat(), "total_fv": 100.0}], as_of=today,
        ) == 0.0

    def test_smoothing_dilutes_single_outlier(self):
        """A single big spike from one source should NOT dominate the
        trajectory — that was the headline complaint about the old delta."""
        today = date(2026, 5, 19)
        # 3 calm points outside the 1-year cutoff (averaging 180) and 3 recent
        # points where the LAST one is a wild +60 spike (the other two calm
        # at 180). Mean of recent = (180+180+240)/3 = 200. Mean of baseline
        # = 180. Smoothed trajectory = 200 - 180 = 20. An unsmoothed
        # (latest - one-baseline) would have reported +60 — 3x the magnitude.
        series = [
            {"date": _iso_days_ago(400, today), "total_fv": 180.0},
            {"date": _iso_days_ago(380, today), "total_fv": 180.0},
            {"date": _iso_days_ago(370, today), "total_fv": 180.0},
            {"date": _iso_days_ago( 30, today), "total_fv": 180.0},
            {"date": _iso_days_ago( 15, today), "total_fv": 180.0},
            {"date": today.isoformat(),         "total_fv": 240.0},  # outlier spike
        ]
        traj = _trajectory_score(series, as_of=today)
        assert traj == 20.0

    def test_negative_trajectory_for_bleeding_farm(self):
        today = date(2026, 5, 19)
        series = [
            {"date": _iso_days_ago(420, today), "total_fv": 300.0},
            {"date": _iso_days_ago(400, today), "total_fv": 290.0},
            {"date": _iso_days_ago(380, today), "total_fv": 280.0},
            {"date": _iso_days_ago( 20, today), "total_fv": 240.0},
            {"date": _iso_days_ago( 10, today), "total_fv": 235.0},
            {"date": today.isoformat(),         "total_fv": 230.0},
        ]
        # Recent mean = (240 + 235 + 230) / 3 = 235
        # Baseline mean = (300 + 290 + 280) / 3 = 290
        # Trajectory = 235 - 290 = -55
        assert _trajectory_score(series, as_of=today) == -55.0

    def test_short_history_falls_back_to_earliest(self):
        """When the entire history is inside the lookback window, baseline
        against the earliest points so the sign of the change is still
        meaningful."""
        today = date(2026, 5, 19)
        series = [
            {"date": _iso_days_ago(40, today), "total_fv": 100.0},
            {"date": _iso_days_ago(20, today), "total_fv": 120.0},
            {"date": today.isoformat(),        "total_fv": 140.0},
        ]
        # No point falls on/before today-365 → baseline = mean of first 3
        # (which is just the whole series): (100+120+140)/3 = 120.
        # Recent mean is also (100+120+140)/3 = 120. Result = 0.
        # This is the documented degenerate case — the test pins behavior.
        assert _trajectory_score(series, as_of=today) == 0.0

    def test_constants_pinned(self):
        # The defaults are referenced directly in the front-end tooltip
        # text — flag loud breakage if someone retunes.
        assert FARM_TRAJECTORY_LOOKBACK_DAYS == 365
        assert FARM_TRAJECTORY_SMOOTH_WINDOW == 3


# ---------------------------------------------------------------------------
# Grad pipeline — FV-weighted, not a count
# ---------------------------------------------------------------------------

class TestGradPipelineScore:
    def test_fv_weighting_dominates_count(self):
        """One 60 FV grad should be worth more than four 40 FV grads —
        that's the whole point of switching from count to FV-weighted."""
        today = date(2026, 5, 19)
        one_60 = [{"kind": "graduation", "fv": 60.0,
                   "date": _iso_days_ago(30, today)}]
        four_40 = [
            {"kind": "graduation", "fv": 40.0, "date": _iso_days_ago(10, today)},
            {"kind": "graduation", "fv": 40.0, "date": _iso_days_ago(20, today)},
            {"kind": "graduation", "fv": 40.0, "date": _iso_days_ago(30, today)},
            {"kind": "graduation", "fv": 40.0, "date": _iso_days_ago(40, today)},
        ]
        assert _grad_pipeline_score(one_60, as_of=today) > _grad_pipeline_score(four_40, as_of=today)

    def test_only_counts_window(self):
        today = date(2026, 5, 19)
        events = [
            {"kind": "graduation", "fv": 55, "date": _iso_days_ago(400, today)},  # outside
            {"kind": "graduation", "fv": 50, "date": _iso_days_ago(100, today)},  # inside
        ]
        # Only the 100-days-ago grad counts — score = points(50) = 5.0.
        assert _grad_pipeline_score(events, as_of=today) == 5.0

    def test_ignores_non_graduation_events(self):
        today = date(2026, 5, 19)
        events = [
            {"kind": "trade",      "fv": 60, "date": _iso_days_ago(20, today)},
            {"kind": "graduation", "fv": 45, "date": _iso_days_ago(30, today)},
        ]
        # Only the graduation contributes — points(45) = 2.5.
        assert _grad_pipeline_score(events, as_of=today) == 2.5

    def test_empty_returns_zero(self):
        assert _grad_pipeline_score([], as_of=date(2026, 5, 19)) == 0.0

    def test_constants_pinned(self):
        assert FARM_GRAD_PIPELINE_MONTHS == 12


# ---------------------------------------------------------------------------
# Normalization + ranking + letter grades
# ---------------------------------------------------------------------------

class TestNormalizeTo100:
    def test_min_max_anchor_when_small_n(self):
        # With only 3 values, the 5th/95th percentile collapse to first/last.
        vals = [10.0, 20.0, 30.0]
        out = _normalize_to_100(vals)
        assert out[0] == 0.0
        assert out[2] == 100.0

    def test_all_equal_returns_50(self):
        # Avoid divide-by-zero; everyone gets a middling 50.
        assert _normalize_to_100([7.5, 7.5, 7.5]) == [50.0, 50.0, 50.0]

    def test_empty_returns_empty(self):
        assert _normalize_to_100([]) == []

    def test_single_value_returns_100(self):
        assert _normalize_to_100([42.0]) == [100.0]

    def test_outlier_does_not_squash_distribution(self):
        """One huge outlier shouldn't flatten the rest of the orgs into a
        narrow band — percentile anchoring guards against that. Uses n=30
        because that's the actual farm-pool size (the 5/95 percentile
        trim needs enough orgs to bite — for n<20 it degenerates to
        min/max anchoring)."""
        vals = list(range(10, 310, 10)) + [10000]   # 30 normal values + 1 outlier
        out = _normalize_to_100(vals)
        # A median value (160 = position 15/30) should land somewhere
        # meaningful, not pinned near zero by the outlier dominating the max.
        mid_idx = vals.index(160)
        assert 30 <= out[mid_idx] <= 70, f"mid score collapsed to {out[mid_idx]}"


class TestRankDescending:
    def test_basic_ordering(self):
        # Highest value → rank 1
        assert _rank_descending([10, 30, 20]) == [3, 1, 2]

    def test_ties_share_rank(self):
        # Both 50s tie for #1; 25 is #3.
        assert _rank_descending([50, 50, 25]) == [1, 1, 3]

    def test_empty(self):
        assert _rank_descending([]) == []


class TestLetterGrade:
    def test_rank_one_is_a_plus(self):
        assert _letter_grade(1, 30) == "A+"

    def test_last_is_d(self):
        assert _letter_grade(30, 30) == "D"

    def test_middle_is_b_or_b_minus(self):
        # Rank 15 / 30 = pct 0.483 → "B-" per the bucket table.
        assert _letter_grade(15, 30) == "B-"

    def test_single_org_pool_is_a_plus(self):
        assert _letter_grade(1, 1) == "A+"

    def test_zero_pool_safe(self):
        assert _letter_grade(1, 0) == "—"


# ---------------------------------------------------------------------------
# Composite weights — keep the report card balanced
# ---------------------------------------------------------------------------

class TestCompositeWeights:
    def test_weights_sum_to_one(self):
        total = (FARM_WEIGHT_TOP_END + FARM_WEIGHT_DEPTH
                 + FARM_WEIGHT_TRAJECTORY + FARM_WEIGHT_GRAD)
        assert abs(total - 1.0) < 1e-9

    def test_top_end_is_the_dominant_signal(self):
        # The whole rationale of the overhaul — stars matter more than
        # depth or trajectory. If someone re-tunes and breaks this
        # invariant the test fails loud.
        assert FARM_WEIGHT_TOP_END > FARM_WEIGHT_DEPTH
        assert FARM_WEIGHT_TOP_END > FARM_WEIGHT_TRAJECTORY
        assert FARM_WEIGHT_TOP_END > FARM_WEIGHT_GRAD

    def test_inventory_dominates_movement(self):
        # Inventory (top_end + depth) should outweigh movement (trajectory
        # + grad). Otherwise a flatlined-but-stacked farm can rank below
        # a churning-but-empty one — which is what the overhaul kills.
        inventory = FARM_WEIGHT_TOP_END + FARM_WEIGHT_DEPTH
        movement  = FARM_WEIGHT_TRAJECTORY + FARM_WEIGHT_GRAD
        assert inventory > movement


# ---------------------------------------------------------------------------
# rank_percentile — kept from the old system, still used internally
# ---------------------------------------------------------------------------

class TestRankPercentile:
    def test_best_is_one_worst_is_zero(self):
        pct = _rank_percentile([10.0, 20.0, 30.0])
        assert pct == [0.0, 0.5, 1.0]

    def test_handles_ties_by_averaging_rank(self):
        pct = _rank_percentile([50.0, 50.0, 100.0, 25.0])
        assert pct[2] == 1.0
        assert pct[3] == 0.0
        assert pct[0] == pct[1] == 0.5

    def test_single_value_returns_one(self):
        assert _rank_percentile([42.0]) == [1.0]

    def test_empty_returns_empty(self):
        assert _rank_percentile([]) == []


# ---------------------------------------------------------------------------
# Org FV history — graduations are neutral. A farm that promotes a 60 FV
# prospect to the majors should not see its cumulative line drop on the
# graduation date, because that's success, not lost value.
# ---------------------------------------------------------------------------

def _mk_player(key, name, org, points, status="active", graduation_date=None):
    """Build a minimal PlayerTimeseries stand-in. `_build_org_fv_history`
    only reads .points, .player_key, .player_name, .org, .status, and
    .graduation_date — SimpleNamespace covers all of that without forcing
    us to populate the candlestick/shrinkage fields."""
    return SimpleNamespace(
        player_key=key, player_name=name, org=org, status=status,
        graduation_date=graduation_date,
        points=[SimpleNamespace(snapshot_date=d, consensus_fv_raw=fv) for d, fv in points],
    )


class TestBuildOrgFvHistoryGraduations:
    def test_graduation_does_not_drop_cumulative(self):
        # One player rated 60 FV all season, then graduates. Cumulative line
        # should hit 60 on the snapshot date and stay there — NOT drop to 0
        # on the graduation date.
        player = _mk_player(
            "p1", "Prospect One", "ATL",
            [("2025-04-01", 60.0)],
            status="graduated", graduation_date="2025-08-15",
        )
        out = _build_org_fv_history([player], lambda trades: [], {})
        series = out["ATL"]["series"]
        assert series == [{"date": "2025-04-01", "total_fv": 60.0}]
        # The graduation event is still recorded so grad_pipeline_score and
        # chart annotations can use it.
        events = out["ATL"]["events"]
        assert any(e["kind"] == "graduation" and e["fv"] == 60.0 for e in events)

    def test_trajectory_neutral_through_graduation(self):
        # Org builds up to 60 FV early, prospect graduates mid-window, no
        # other movement. Trajectory should be ~0, not strongly negative.
        player = _mk_player(
            "p1", "Prospect One", "ATL",
            [("2025-01-15", 60.0)],
            status="graduated", graduation_date="2025-09-01",
        )
        out = _build_org_fv_history([player], lambda trades: [], {})
        series = out["ATL"]["series"]
        traj = _trajectory_score(series, as_of=date(2026, 5, 19))
        assert traj == 0.0
