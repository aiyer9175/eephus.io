"""Tests for the graduate Statcast zone classifier + swing-rate aggregator.

These exercise the pure helpers in graduate_savant.py with synthetic
fixture data — no network access required. The CSV fetch path itself is
not exercised; integration with Savant is verified at runtime via the
single-graduate smoke-test in the plan.

Run: python -m pytest test_graduate_savant.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from graduate_savant import (
    ZONE_HALF_WIDTH_FT,
    _classify_zone,
    compute_swing_zone_heat,
    build_graduate_swing_zone_heat,
)


# Default synthetic strike-zone bounds: 3.4 ft top, 1.6 ft bottom (a
# fairly typical pitcher-eye-level zone for an avg-height MLB hitter).
SZ_TOP = 3.4
SZ_BOT = 1.6
ZONE_HEIGHT = SZ_TOP - SZ_BOT  # 1.8 ft


class TestClassifyZoneInnerGrid:
    """Inner 3x3 zone — 9 pitches, one per cell, should map to 0-8."""

    def test_center_of_each_cell(self):
        # Column anchors. Half-width / 3 ≈ 0.236 ft.
        third = ZONE_HALF_WIDTH_FT / 3
        col_centers = [-2 * third, 0, 2 * third]  # left, mid, right
        # Row anchors. Top row uses pz > sz_top - h/3 -> use top-third
        # midpoint; ditto middle and bottom.
        row_centers = [
            SZ_TOP - ZONE_HEIGHT / 6,            # top
            (SZ_TOP + SZ_BOT) / 2,                # middle
            SZ_BOT + ZONE_HEIGHT / 6,            # bottom
        ]
        for r, pz in enumerate(row_centers):
            for c, px in enumerate(col_centers):
                z = _classify_zone(px, pz, SZ_TOP, SZ_BOT)
                assert z == r * 3 + c, f"({px=}, {pz=}) -> {z}, want {r*3+c}"


class TestClassifyZoneChaseWedges:
    def test_above_zone(self):
        assert _classify_zone(0, SZ_TOP + 0.2, SZ_TOP, SZ_BOT) == 9

    def test_below_zone(self):
        assert _classify_zone(0, SZ_BOT - 0.2, SZ_TOP, SZ_BOT) == 10

    def test_left_of_zone(self):
        # Way outside on the left at mid-height.
        px = -(ZONE_HALF_WIDTH_FT + 0.2)
        pz = (SZ_TOP + SZ_BOT) / 2
        assert _classify_zone(px, pz, SZ_TOP, SZ_BOT) == 11

    def test_right_of_zone(self):
        px = ZONE_HALF_WIDTH_FT + 0.2
        pz = (SZ_TOP + SZ_BOT) / 2
        assert _classify_zone(px, pz, SZ_TOP, SZ_BOT) == 12


class TestClassifyZoneBoundary:
    def test_exact_top_boundary_inside(self):
        # pz == sz_top should still be inside the zone (≤, not <).
        z = _classify_zone(0, SZ_TOP, SZ_TOP, SZ_BOT)
        assert z in {0, 1, 2}  # row 0 (top row)

    def test_exact_bottom_boundary_inside(self):
        z = _classify_zone(0, SZ_BOT, SZ_TOP, SZ_BOT)
        assert z in {6, 7, 8}  # row 2 (bottom row)

    def test_exact_side_boundary_inside(self):
        # |px| == half-width -> inside.
        z = _classify_zone(ZONE_HALF_WIDTH_FT, (SZ_TOP + SZ_BOT) / 2,
                           SZ_TOP, SZ_BOT)
        assert z is not None and z < 9


class TestClassifyZoneMissingData:
    def test_none_coords(self):
        assert _classify_zone(None, 2.5, SZ_TOP, SZ_BOT) is None
        assert _classify_zone(0, None, SZ_TOP, SZ_BOT) is None
        assert _classify_zone(0, 2.5, None, SZ_BOT) is None
        assert _classify_zone(0, 2.5, SZ_TOP, None) is None

    def test_inverted_zone_bounds(self):
        # sz_top <= sz_bot is a corrupt row, must reject.
        assert _classify_zone(0, 2.5, SZ_BOT, SZ_TOP) is None
        assert _classify_zone(0, 2.5, 2.0, 2.0) is None


# ---------------------------------------------------------------------------
# compute_swing_zone_heat
# ---------------------------------------------------------------------------

def _make_pitch(px, pz, desc="ball"):
    return {
        "plate_x": px, "plate_z": pz,
        "sz_top": SZ_TOP, "sz_bot": SZ_BOT,
        "description": desc,
    }


class TestComputeSwingZoneHeat:
    def test_basic_heart_swing_rate(self):
        # 20 pitches at dead center, 15 swings -> swing rate 0.75 in zone 4.
        pitches = []
        for _ in range(15):
            pitches.append(_make_pitch(0, (SZ_TOP + SZ_BOT) / 2, "hit_into_play"))
        for _ in range(5):
            pitches.append(_make_pitch(0, (SZ_TOP + SZ_BOT) / 2, "ball"))
        heat = compute_swing_zone_heat(pitches)
        assert heat[4] == 0.75
        # All other zones should be None (insufficient sample).
        for i, v in enumerate(heat):
            if i != 4:
                assert v is None

    def test_sample_gate_returns_none(self):
        # 9 pitches in a zone — below the default 10-pitch floor.
        pitches = [_make_pitch(0, (SZ_TOP + SZ_BOT) / 2, "swinging_strike")
                   for _ in range(9)]
        heat = compute_swing_zone_heat(pitches)
        assert heat[4] is None
        # 10 pitches — at the floor — should now read.
        pitches.append(_make_pitch(0, (SZ_TOP + SZ_BOT) / 2, "swinging_strike"))
        heat = compute_swing_zone_heat(pitches)
        assert heat[4] == 1.0

    def test_chase_wedge_aggregation(self):
        # 12 pitches above the zone, 4 swings -> swing rate 0.333 in zone 9.
        pitches = []
        for _ in range(4):
            pitches.append(_make_pitch(0, SZ_TOP + 0.3, "foul"))
        for _ in range(8):
            pitches.append(_make_pitch(0, SZ_TOP + 0.3, "ball"))
        heat = compute_swing_zone_heat(pitches)
        assert heat[9] == 0.333

    def test_only_recognized_swing_descriptions_count(self):
        # ball / called_strike / blocked_ball don't count as swings.
        # 10 zone-center pitches, all called strikes -> 0% swing rate.
        pitches = [_make_pitch(0, (SZ_TOP + SZ_BOT) / 2, "called_strike")
                   for _ in range(10)]
        heat = compute_swing_zone_heat(pitches)
        assert heat[4] == 0.0

    def test_skips_pitches_with_missing_coords(self):
        # Mix of valid + invalid; only the valid ones aggregate.
        pitches = [_make_pitch(None, None, "swinging_strike")
                   for _ in range(20)]
        pitches.extend([_make_pitch(0, (SZ_TOP + SZ_BOT) / 2, "swinging_strike")
                        for _ in range(10)])
        heat = compute_swing_zone_heat(pitches)
        assert heat[4] == 1.0  # only the 10 valid pitches counted


class TestBuildOrchestrator:
    def test_skips_graduates_without_mlbam_or_seasons(self):
        # Direct call exercises the early-return paths without hitting
        # the network. Graduate with no mlbam_id, no career_war, etc.
        graduates = [
            {"player_key": "no_mlbam", "career_war": {"seasons": {"2024": {}}}},
            {"player_key": "no_seasons", "mlbam_id": 12345,
             "career_war": {"seasons": {}}},
            {"player_key": "no_key", "mlbam_id": 67890,
             "career_war": {"seasons": {"2024": {}}}},
        ]
        out = build_graduate_swing_zone_heat(graduates)
        assert out == {}
