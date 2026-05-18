"""
Tests for the v3 consensus engine.

Run: python -m pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from scrapers import Snapshot, _parse_fv
from consensus import (
    WHOLE_FV_GRADES, PLUS_GRADES, snap_to_grade,
    implied_fv_from_rank, compute_consensus_point, build_timeseries,
    stock_movement, SourceWeight, DEFAULT_WEIGHTS,
)


def _snap(source, name, *, rank=None, fv=None, date_="2026-02-16",
          label="2026 Report", status="active"):
    return Snapshot(
        source=source, snapshot_date=date_, interval_label=label,
        player_key=name.lower().replace(" ", "_"), player_name=name,
        position="SS", org="PIT", rank=rank, fv=fv, status=status,
    )


# ---------------------------------------------------------------------------
# FV parsing (covers TJStats PV/FV format)
# ---------------------------------------------------------------------------

class TestParseFV:
    def test_simple_whole(self):
        assert _parse_fv("60") == 60.0

    def test_plus_grade(self):
        assert _parse_fv("55+") == 57.5

    def test_pvfv_format(self):
        # TJStats uses "PV/FV" format like "45/55"
        assert _parse_fv("45/55") == 55.0

    def test_pvfv_with_plus(self):
        assert _parse_fv("45/55+") == 57.5

    def test_empty(self):
        assert _parse_fv("") is None
        assert _parse_fv("   ") is None


# ---------------------------------------------------------------------------
# Grade grid
# ---------------------------------------------------------------------------

class TestSnapToGrade:
    def test_whole_grades_exact(self):
        for g in [20, 30, 40, 45, 50, 55, 60, 65, 70, 80]:
            fv, label = snap_to_grade(float(g))
            assert label == str(g)

    def test_plus_grade_emitted(self):
        fv, label = snap_to_grade(57.5)
        assert label == "55+"

    def test_75_never_emitted(self):
        for raw in [73.0, 74.0, 75.0, 76.0, 77.0]:
            fv, label = snap_to_grade(raw)
            assert label != "75"

    def test_clamps(self):
        assert snap_to_grade(15.0)[0] == 20.0
        assert snap_to_grade(95.0)[0] == 80.0


# ---------------------------------------------------------------------------
# 7-source consensus
# ---------------------------------------------------------------------------

class TestSevenSourceConsensus:
    def test_all_four_fv_graders_agree(self):
        """
        FG, ESPN, JB, TJ all explicit 65. Rank-only sources rank #2
        (implied 60 from the rank tier mapping).

        The four FV-graders pull toward 65 (combined weight 9.5), but the
        three rank-only sources at 60 pull down. Result: ~63.3 raw, which
        snaps to 60+ — exactly the correct outcome ("60 with upside to 65").
        """
        snaps = [
            _snap("fangraphs",        "X", rank=2, fv=65.0),
            _snap("espn",             "X", rank=2, fv=65.0),
            _snap("just_baseball",    "X", rank=2, fv=65.0),
            _snap("tjstats",          "X", rank=2, fv=65.0),
            _snap("baseball_america", "X", rank=2),
            _snap("mlb_pipeline",     "X", rank=2),
            _snap("the_athletic",     "X", rank=2),
        ]
        pt = compute_consensus_point(snaps)
        assert pt.consensus_fv_label == "60+"
        assert pt.avg_fv == 65.0
        assert pt.avg_rank == 2.0
        # All seven sources contributed
        assert len(pt.sources_contributing) == 7

    def test_fv_graders_split(self):
        """
        FG 65, ESPN 60, JB 60, TJ 60. Rank-only all #3 (implied 60).
        Weighted avg: FG dominates with weight 3.0 but pulled by 60s.
        Expected to snap to 60 or 60+.
        """
        snaps = [
            _snap("fangraphs",        "X", rank=3, fv=65.0),
            _snap("espn",             "X", rank=3, fv=60.0),
            _snap("just_baseball",    "X", rank=3, fv=60.0),
            _snap("tjstats",          "X", rank=3, fv=60.0),
            _snap("baseball_america", "X", rank=3),
            _snap("mlb_pipeline",     "X", rank=3),
            _snap("the_athletic",     "X", rank=3),
        ]
        pt = compute_consensus_point(snaps)
        assert pt.consensus_fv_label in ("60", "60+")
        assert pt.avg_fv > 60.0  # 4-grader mean is 61.25

    def test_rank_only_sources(self):
        """Only rank-only sources. Consensus comes purely from rank-implied."""
        snaps = [
            _snap("baseball_america", "X", rank=1),
            _snap("mlb_pipeline",     "X", rank=1),
            _snap("the_athletic",     "X", rank=1),
        ]
        pt = compute_consensus_point(snaps)
        assert pt.avg_fv is None
        assert pt.avg_rank == 1.0
        assert pt.consensus_fv == 70.0

    def test_missing_sources_dont_break_consensus(self):
        """Only 2 of 7 sources have this player. Consensus still computes."""
        snaps = [
            _snap("fangraphs",     "Newcomer", rank=None, fv=45.0),
            _snap("baseball_america", "Newcomer", rank=85),
        ]
        pt = compute_consensus_point(snaps)
        assert pt is not None
        # FG 45 weight 3.0, BA rank 85 -> implied 50, weight 1.0
        # raw = (45*3 + 50*1) / 4 = 46.25
        # 46.25 is within 1.25 of 47.5 (the 45+ midpoint) -> snaps to "45+"
        assert pt.consensus_fv_label == "45+"


# ---------------------------------------------------------------------------
# Source weighting
# ---------------------------------------------------------------------------

class TestSourceWeighting:
    def test_fangraphs_dominates_other_fv_graders(self):
        """
        FG 70 (w=3.0) vs three other FV-graders at 55 (w 2.5 + 2.0 + 2.0).
        Total: 70*3 + 55*6.5 = 210 + 357.5 = 567.5 / 9.5 = 59.7 -> 60
        """
        snaps = [
            _snap("fangraphs",     "X", fv=70.0),
            _snap("espn",          "X", fv=55.0),
            _snap("just_baseball", "X", fv=55.0),
            _snap("tjstats",       "X", fv=55.0),
        ]
        pt = compute_consensus_point(snaps)
        assert pt.consensus_fv == 60.0

    def test_custom_weights(self):
        """Override weights to bias toward TJStats."""
        custom = dict(DEFAULT_WEIGHTS)
        custom["tjstats"] = SourceWeight("tjstats", rank_weight=1.0, fv_weight=10.0)
        snaps = [
            _snap("fangraphs", "X", fv=50.0),
            _snap("tjstats",   "X", fv=70.0),
        ]
        pt = compute_consensus_point(snaps, weights=custom)
        # TJ weight 10 dominates FG weight 3
        assert pt.consensus_fv >= 65.0


# ---------------------------------------------------------------------------
# Candlestick fields
# ---------------------------------------------------------------------------

class TestCandlestick:
    def _player(self, history):
        """history = [(date, fv)]"""
        snaps = [_snap("fangraphs", "X", date_=d, fv=fv, label=f"upd-{d}")
                 for d, fv in history]
        return build_timeseries(snaps)[0]

    def test_high_low_basic(self):
        p = self._player([
            ("2025-02-15", 55.0),
            ("2025-07-29", 65.0),
            ("2026-02-16", 60.0),
        ])
        assert p.fv_high == 65.0
        assert p.fv_high_date == "2025-07-29"
        assert p.fv_low == 55.0
        assert p.fv_low_date == "2025-02-15"
        assert p.fv_open == 55.0
        assert p.fv_close == 60.0

    def test_single_point(self):
        p = self._player([("2026-02-16", 50.0)])
        assert p.fv_high == p.fv_low == p.fv_open == p.fv_close == 50.0

    def test_walcott_pattern(self):
        """High at peak summer 2025, then back down post-TJ"""
        p = self._player([
            ("2025-02-15", 60.0),
            ("2025-07-29", 65.0),  # peak
            ("2026-02-16", 60.0),  # post-TJ
            ("2026-05-13", 60.0),
        ])
        assert p.fv_high == 65.0
        assert p.fv_low == 60.0  # all the 60s are equal-low
        # Open is the first observation, close is the most recent
        assert p.fv_open == 60.0
        assert p.fv_close == 60.0


# ---------------------------------------------------------------------------
# Last-update stock movement
# ---------------------------------------------------------------------------

class TestStockMovement:
    def _player_from_points(self, points_data):
        snaps = [_snap("fangraphs", "X", date_=d, fv=fv, label=f"upd-{d}")
                 for d, fv in points_data]
        return build_timeseries(snaps)[0]

    def test_uses_last_two_points_only(self):
        """
        First→last delta would be +15 (huge up); but the most recent
        delta is -5 (down). Stock should be down.
        """
        p = self._player_from_points([
            ("2025-02-15", 50.0),
            ("2025-07-29", 60.0),
            ("2026-02-16", 65.0),
            ("2026-05-13", 60.0),  # latest update: drop from 65 to 60
        ])
        m = stock_movement(p)
        assert m["direction"] == "down_strong"
        assert m["from_label"] == "65"
        assert m["to_label"] == "60"

    def test_flat_when_no_recent_change(self):
        p = self._player_from_points([
            ("2025-02-15", 55.0),
            ("2026-02-16", 55.0),
        ])
        m = stock_movement(p)
        assert m["direction"] == "flat"
        assert m["delta"] == 0.0

    def test_single_point_is_flat(self):
        p = self._player_from_points([("2026-02-16", 55.0)])
        m = stock_movement(p)
        assert m["direction"] == "flat"

    def test_graduated_overrides(self):
        # Even one FG graduates-page entry flips the status, regardless of
        # what other sources say.
        snaps = [
            _snap("fangraphs", "X", fv=60.0, date_="2025-02-15", label="FG 2025 Report"),
            # Other sources still rank the player (stale):
            _snap("baseball_america", "X", rank=15, date_="2026-05-13", label="BA May"),
            # FG graduates page picks them up:
            _snap("fangraphs", "X", fv=65.0, date_="2026-05-14", label="FG 2026 Graduates", status="graduated"),
        ]
        p = build_timeseries(snaps)[0]
        assert p.status == "graduated"
        assert p.graduation_date == "2026-05-14"
        assert stock_movement(p)["direction"] == "graduated"


class TestExportSplit:
    """Verifies the active/graduate split and top-N trimming in storage.export."""

    def test_split_and_top_n(self, tmp_path):
        import json
        from storage import export_timeseries_json

        # Build 5 actives + 2 graduates
        snaps = []
        for i, fv in enumerate([70.0, 65.0, 60.0, 55.0, 50.0]):
            snaps.append(_snap("fangraphs", f"Active {i}",
                              fv=fv, date_="2026-02-16",
                              label="FG 2026 Report"))
        # Two graduates
        snaps.append(_snap("fangraphs", "Grad A",
                          fv=60.0, date_="2025-10-15",
                          label="FG 2025 Graduates", status="graduated"))
        snaps.append(_snap("fangraphs", "Grad B",
                          fv=65.0, date_="2026-05-14",
                          label="FG 2026 Graduates", status="graduated"))

        ts = build_timeseries(snaps)
        out = tmp_path / "out.json"
        export_timeseries_json(ts, out, top_n_active=3)
        payload = json.loads(out.read_text())

        # Active list trimmed to top 3 by consensus FV
        assert payload["active_count"] == 3
        assert len(payload["players"]) == 3
        names = [p["player_name"] for p in payload["players"]]
        assert names == ["Active 0", "Active 1", "Active 2"]  # 70, 65, 60

        # Graduates list separate, sorted by graduation_date desc
        assert payload["graduate_count"] == 2
        grad_names = [p["player_name"] for p in payload["graduates"]]
        assert grad_names == ["Grad B", "Grad A"]  # 2026 before 2025
        assert all(p["status"] == "graduated" for p in payload["graduates"])
