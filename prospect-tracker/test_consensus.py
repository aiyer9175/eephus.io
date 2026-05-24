"""
Tests for the v3 consensus engine.

Run: python -m pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from scrapers import Snapshot, _parse_fv, _parse_espn_tools, _parse_pipeline_tools
from consensus import (
    snap_to_grade,
    implied_fv_from_rank, compute_consensus_point, build_timeseries,
    stock_movement, apply_shrinkage, compute_prior_mean_fv,
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


class TestParseEspnTools:
    def test_pv_fv_format_takes_rightmost(self):
        # ESPN's preseason block — left=present, right=future. We take FV.
        commentary = (
            "Konnor Griffin, SS, Pittsburgh Pirates\n"
            "Age: 19 | Bats: Right | Throws: Right\n"
            "Hit: 45/50\nGame Power: 50/65\nRaw Power: 60/70\n"
            "Speed: 70/70\nFielding: 45/55\nThrowing: 65/65\n"
        )
        tools = _parse_espn_tools(commentary)
        assert tools["hit"] == 50.0
        assert tools["game_pwr"] == 65.0
        assert tools["raw_pwr"] == 70.0
        assert tools["speed"] == 70.0
        assert tools["field"] == 55.0
        assert tools["throw"] == 65.0

    def test_single_value_fallback(self):
        # If ESPN ever drops the PV/FV format and ships a single grade,
        # use it as-is.
        tools = _parse_espn_tools("Hit: 55\nPower: 60\n")
        assert tools["hit"] == 55.0
        assert tools["game_pwr"] == 60.0

    def test_out_of_range_dropped(self):
        # 12 and 99 are not on the 20-80 scale; both silently skipped.
        tools = _parse_espn_tools("Hit: 12/99\nSpeed: 50/55\n")
        assert "hit" not in (tools or {})
        assert tools["speed"] == 55.0

    def test_empty_returns_none(self):
        assert _parse_espn_tools("") is None
        assert _parse_espn_tools("No tools here") is None


class TestParsePipelineTools:
    def test_single_value_format(self):
        # Current Pipeline format — single integer per tool.
        bio = "Scouting grades: Hit: 55 | Power: 60 | Run: 45 | Arm: 50 | Field: 55 | Overall: 55"
        tools = _parse_pipeline_tools(bio)
        assert tools["hit"] == 55.0
        assert tools["game_pwr"] == 60.0
        assert tools["speed"] == 45.0
        assert tools["throw"] == 50.0
        assert tools["field"] == 55.0

    def test_pv_fv_format_safety(self):
        # If Pipeline starts shipping PV/FV pairs, take the rightmost.
        bio = "Scouting grades: Hit: 50/60 | Power: 55/65"
        tools = _parse_pipeline_tools(bio)
        assert tools["hit"] == 60.0
        assert tools["game_pwr"] == 65.0

    def test_mixed_formats(self):
        # Mix of single-value and PV/FV in the same bio.
        bio = "Scouting grades: Hit: 50/60 | Power: 55 | Run: 40/50"
        tools = _parse_pipeline_tools(bio)
        assert tools["hit"] == 60.0
        assert tools["game_pwr"] == 55.0
        assert tools["speed"] == 50.0


# ---------------------------------------------------------------------------
# Grade grid
# ---------------------------------------------------------------------------

class TestSnapToGrade:
    def test_whole_grades_exact(self):
        for g in [20, 30, 40, 45, 50, 55, 60, 65, 70, 80]:
            fv, label = snap_to_grade(float(g))
            assert label == str(g)

    def test_rounds_to_nearest_int(self):
        assert snap_to_grade(57.5)[1] == "58"
        assert snap_to_grade(57.4)[1] == "57"
        assert snap_to_grade(46.25)[1] == "46"
        assert snap_to_grade(63.3)[1] == "63"

    def test_clamps(self):
        assert snap_to_grade(15.0)[0] == 20.0
        assert snap_to_grade(95.0)[0] == 80.0


# ---------------------------------------------------------------------------
# 7-source consensus
# ---------------------------------------------------------------------------

class TestUnweightedConsensus:
    def test_all_five_fv_graders_agree(self):
        """
        All five FV-grading sources (FG, ESPN, JB, TJ, MLB Pipeline) explicit
        at 65; the two rank-only sources (BA, The Athletic) rank #2.
        Unweighted FV mean = 65. Rank-implied (#2 → 60) does NOT pull the
        consensus down — it's a fallback only used when no source publishes FV.
        """
        snaps = [
            _snap("fangraphs",        "X", rank=2, fv=65.0),
            _snap("espn",             "X", rank=2, fv=65.0),
            _snap("just_baseball",    "X", rank=2, fv=65.0),
            _snap("tjstats",          "X", rank=2, fv=65.0),
            _snap("mlb_pipeline",     "X", rank=2, fv=65.0),
            _snap("baseball_america", "X", rank=2),
            _snap("the_athletic",     "X", rank=2),
        ]
        pt = compute_consensus_point(snaps)
        assert pt.consensus_fv_label == "65"
        assert pt.avg_fv == 65.0
        assert pt.avg_rank == 2.0
        # All seven sources contributed something (FV or rank)
        assert len(pt.sources_contributing) == 7

    def test_fv_graders_split(self):
        """
        FG 65, ESPN 60, JB 60, TJ 60, Pipeline 60. Unweighted mean of FVs:
        (65 + 60 + 60 + 60 + 60) / 5 = 61.0 → snaps to "61".
        """
        snaps = [
            _snap("fangraphs",        "X", rank=3, fv=65.0),
            _snap("espn",             "X", rank=3, fv=60.0),
            _snap("just_baseball",    "X", rank=3, fv=60.0),
            _snap("tjstats",          "X", rank=3, fv=60.0),
            _snap("mlb_pipeline",     "X", rank=3, fv=60.0),
            _snap("baseball_america", "X", rank=3),
            _snap("the_athletic",     "X", rank=3),
        ]
        pt = compute_consensus_point(snaps)
        assert pt.consensus_fv_label == "61"
        assert pt.avg_fv == 61.0

    def test_mlb_pipeline_fv_counts(self):
        """
        Regression test: MLB Pipeline used to be hard-coded as rank-only
        (fv_weight=0). With the unweighted engine it contributes its FV
        like any other grader. With `single_source_k=0` (test override
        to disable the single-source pull), Pipeline at 60 alone yields
        consensus 60. (The pull-down path is tested separately in
        TestConsensusIsSourceMean.)
        """
        snaps = [_snap("mlb_pipeline", "X", rank=1, fv=60.0)]
        pt = compute_consensus_point(snaps, single_source_k=0)
        assert pt.consensus_fv_label == "60"
        assert pt.avg_fv == 60.0

    def test_rank_only_sources(self):
        """
        Only rank-only sources have this player. No explicit FV, so we fall
        back to rank-implied. All three rank #1 → implied 70.
        """
        snaps = [
            _snap("baseball_america", "X", rank=1),
            _snap("the_athletic",     "X", rank=1),
        ]
        pt = compute_consensus_point(snaps)
        assert pt.avg_fv is None
        assert pt.avg_rank == 1.0
        assert pt.consensus_fv == 70.0

    def test_explicit_fv_overrides_rank_implied(self):
        """
        FG publishes 45, BA only ranks (#85 → implied 50). Unweighted FV mean
        is just 45 (BA has no FV). Rank-implied does NOT pull it up. With
        `single_source_k=0` we also disable the new single-source pull-down
        so this test still asserts the "consensus = FG's 45" contract;
        the pull-down path itself is covered in TestConsensusIsSourceMean.
        """
        snaps = [
            _snap("fangraphs",        "Newcomer", rank=None, fv=45.0),
            _snap("baseball_america", "Newcomer", rank=85),
        ]
        pt = compute_consensus_point(snaps, single_source_k=0)
        assert pt is not None
        assert pt.consensus_fv_label == "45"
        assert pt.avg_rank == 85.0  # BA's rank still surfaces for display

    def test_all_sources_contribute_equally(self):
        """
        FG 70, three other graders at 55. Unweighted: (70+55+55+55)/4 = 58.75
        → snaps to "59". (Under the old weighted scheme this returned 60.)
        """
        snaps = [
            _snap("fangraphs",     "X", fv=70.0),
            _snap("espn",          "X", fv=55.0),
            _snap("just_baseball", "X", fv=55.0),
            _snap("tjstats",       "X", fv=55.0),
        ]
        pt = compute_consensus_point(snaps)
        assert pt.consensus_fv == 59.0
        assert pt.avg_fv == 58.75


# ---------------------------------------------------------------------------
# Candlestick fields
# ---------------------------------------------------------------------------

class TestCandlestick:
    def _player(self, history):
        """history = [(date, fv)]. Shrinkage disabled (both the legacy
        `shrinkage_k` post-pass and the new `single_source_k` pull-down)
        so the asserted high/low/open/close numbers reflect the raw FV
        grid the test is checking — TestConsensusIsSourceMean covers the
        shrinkage paths separately."""
        snaps = [_snap("fangraphs", "X", date_=d, fv=fv, label=f"upd-{d}")
                 for d, fv in history]
        return build_timeseries(snaps, shrinkage_k=0, single_source_k=0)[0]

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
        # Same rationale as TestCandlestick: stock direction thresholds are
        # tested against the raw FV grid, not the shrinkage-adjusted one.
        # Single-source pull also disabled so a 1-FG history doesn't get
        # quietly shrunk before the stock-direction comparison runs.
        return build_timeseries(snaps, shrinkage_k=0, single_source_k=0)[0]

    def test_uses_one_year_window(self):
        """v12 — stock_movement is now anchored to the trailing 1y
        window (not the prior single point). For this fixture the
        latest is 2026-05-13; cutoff = 2025-05-13. Anchor prior is the
        snap nearest to (but ≤) that cutoff — 2025-02-15 (50.0).
        Delta = 60 - 50 = +10 → up_strong.
        """
        p = self._player_from_points([
            ("2025-02-15", 50.0),
            ("2025-07-29", 60.0),
            ("2026-02-16", 65.0),
            ("2026-05-13", 60.0),  # latest update
        ])
        m = stock_movement(p)
        assert m["direction"] == "up_strong"
        assert m["from_label"] == "50"
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
        assert p.debut_date == "2026-05-14"
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
        from storage import load_export_unified as _leu; payload = _leu(out)

        # Active list trimmed to top 3 by consensus FV
        assert payload["active_count"] == 3
        assert len(payload["players"]) == 3
        names = [p["player_name"] for p in payload["players"]]
        assert names == ["Active 0", "Active 1", "Active 2"]  # 70, 65, 60

        # Graduates list separate, sorted by debut_date desc
        assert payload["debut_count"] == 2
        grad_names = [p["player_name"] for p in payload["debuts"]]
        assert grad_names == ["Grad B", "Grad A"]  # 2026 before 2025
        assert all(p["status"] == "graduated" for p in payload["debuts"])
        grad_a = next(p for p in payload["debuts"] if p["player_name"] == "Grad A")
        assert grad_a["debut_date"] == "2025-07-01"

    def test_graduate_org_uses_post_graduation_trade(self, tmp_path):
        import json
        from storage import export_timeseries_json

        snaps = [
            Snapshot("fangraphs", "2025-02-15", "FG 2025 Report",
                     "richard_fitts", "Richard Fitts", "SP", "BOS",
                     74, 50.0, "active"),
            Snapshot("fangraphs", "2025-10-15", "FG 2025 Graduates",
                     "richard_fitts", "Richard Fitts", "SP", "BOS",
                     74, 50.0, "graduated"),
        ]
        ts = build_timeseries(snaps)
        out = tmp_path / "out.json"
        export_timeseries_json(
            ts, out,
            trades_by_player={
                "richard_fitts": [{
                    "player_key": "richard_fitts",
                    "trade_date": "2025-11-25",
                    "date_range_start": "2025-11-25",
                    "date_range_end": "2025-11-25",
                    "from_org": "Boston Red Sox",
                    "to_org": "St. Louis Cardinals",
                    "source": "mlb_api",
                    "description": (
                        "St. Louis Cardinals traded RHP Sonny Gray and cash "
                        "to Boston Red Sox for RHP Richard Fitts."
                    ),
                }]
            },
        )

        from storage import load_export_unified as _leu; payload = _leu(out)
        fitts = payload["debuts"][0]
        assert fitts["org"] == "STL"

    def test_active_no_org_uses_roster_org(self, tmp_path):
        import json
        from storage import export_timeseries_json

        snaps = [Snapshot(
            "mlb_pipeline_international", "2026-05-19",
            "MLB Pipeline 2026 International",
            "luis_hernandez", "Luis Hernandez", "SS", None,
            1, None, "active",
        )]
        ts = build_timeseries(snaps)
        out = tmp_path / "out.json"
        export_timeseries_json(
            ts, out,
            rosters_by_org={
                "SFG": {
                    "CPX": [{
                        "player_key": "luis_hernandez",
                        "fullName": "Luis Hernandez",
                        "fv_label": None,
                        "fv_raw": None,
                    }]
                }
            },
        )

        from storage import load_export_unified as _leu; payload = _leu(out)
        luis = payload["players"][0]
        assert luis["org"] == "SFG"
        assert luis["org_rank"] == 1


# ---------------------------------------------------------------------------
# Forward-fill across dates
# ---------------------------------------------------------------------------

class TestForwardFill:
    """Sources publish on different days; each ConsensusPoint should still
    average every source that has ever graded the player up to that date."""

    def test_two_sources_different_dates_average_at_latest(self):
        """
        The Wandy Asigen case. FG snaps 47.5 on 2026-05-17; Pipeline
        International snaps 65 on 2026-05-19. Before forward-fill, the
        latest point only saw Pipeline. Now it averages both.

        Note on Pipeline source aliasing: when the Top 100 row is
        absent (as here), `mlb_pipeline_international` gets relabeled
        to canonical `mlb_pipeline` inside the consensus engine so the
        outlet counts as one source rather than two. The averaged FV
        and avg_fv_n are unchanged from the original test intent —
        only the source-name spelling shifts.
        """
        snaps = [
            _snap("fangraphs", "Wandy", date_="2026-05-17",
                  label="FG 2026 Report", fv=47.5),
            _snap("mlb_pipeline_international", "Wandy", date_="2026-05-19",
                  label="MLB Pipeline 2026 International", rank=2, fv=65.0),
        ]
        # Disable shrinkage so we isolate the forward-fill effect.
        p = build_timeseries(snaps, shrinkage_k=0)[0]
        latest = p.points[-1]
        assert latest.avg_fv_n == 2
        assert latest.avg_fv == pytest.approx((47.5 + 65.0) / 2)
        assert set(latest.sources_contributing) == {
            "fangraphs", "mlb_pipeline"
        }
        # And the candle close reflects the averaged value, not 65 alone.
        assert p.fv_close == 56.0  # 56.25 → snaps to 56

    def test_later_snapshot_from_same_source_overwrites_earlier(self):
        """A second FG snapshot at a later date replaces the first — the
        latest point uses FG=70 (not avg of 60 and 70)."""
        snaps = [
            _snap("fangraphs", "X", date_="2025-02-15", label="FG 2025", fv=60.0),
            _snap("fangraphs", "X", date_="2026-02-16", label="FG 2026", fv=70.0),
        ]
        p = build_timeseries(snaps, shrinkage_k=0)[0]
        latest = p.points[-1]
        assert latest.avg_fv == 70.0
        assert latest.avg_fv_n == 1

    def test_historical_point_only_sees_earlier_sources(self):
        """At an early date, sources that haven't graded yet don't
        contribute (forward-fill, not backward-fill)."""
        snaps = [
            _snap("fangraphs", "X", date_="2025-02-15", label="FG 2025", fv=60.0),
            _snap("espn",      "X", date_="2026-01-27", label="ESPN 2026", fv=50.0),
        ]
        p = build_timeseries(snaps, shrinkage_k=0)[0]
        # Two event dates → two points.
        assert len(p.points) == 2
        # 2025 point: only FG is known.
        assert p.points[0].avg_fv == 60.0
        assert p.points[0].avg_fv_n == 1
        # 2026 point: FG carries forward + ESPN joins.
        assert p.points[1].avg_fv == pytest.approx(55.0)
        assert p.points[1].avg_fv_n == 2


# ---------------------------------------------------------------------------
# Bayesian shrinkage
# ---------------------------------------------------------------------------

class TestConsensusIsSourceMean:
    """Bayesian shrinkage is OFF for multi-source consensus (≥2 sources
    with explicit FVs) — that path stays a pure mean. The 2026 IFA class
    surfaced a need to discount single-source grades, so a targeted pull
    toward FV 35 (k=0.5) is re-enabled when exactly one source published
    an explicit FV. Each test below documents one branch of that policy."""

    def test_single_source_consensus_pulled_toward_prior(self):
        # 1-source prospect at FV 70 is pulled toward the FV-35 prior:
        #   adjusted = (2/3 · 70) + (1/3 · 35) = 58.33 → snaps to FV 58.
        # The pre-shrinkage value is preserved on the point so the UI
        # can show "raw 70" in tooltips.
        snaps = [_snap("fangraphs", "X", fv=70.0)]
        p = build_timeseries(snaps)[0]
        pt = p.points[-1]
        assert pt.consensus_fv_pre_shrinkage == 70.0
        assert pt.consensus_fv == 58.0
        assert abs(pt.consensus_fv_raw - 58.33) < 0.05
        assert abs(pt.shrinkage_weight - (2.0 / 3.0)) < 1e-9
        assert pt.avg_fv_n == 1

    def test_multi_source_consensus_not_shrunken(self):
        # 2 sources at 50 + 60 → consensus mean 55, no shrinkage applied.
        snaps = [
            _snap("fangraphs",    "X", fv=50.0),
            _snap("mlb_pipeline", "X", fv=60.0),
        ]
        p = build_timeseries(snaps)[0]
        pt = p.points[-1]
        assert pt.consensus_fv_pre_shrinkage == 55.0
        assert pt.consensus_fv == 55.0
        assert pt.consensus_fv_raw == 55.0
        assert pt.shrinkage_weight == 1.0
        assert pt.avg_fv_n == 2

    def test_single_source_rank_only_no_shrinkage(self):
        # 1 source publishing only a rank (no explicit FV) — explicit_fvs
        # is empty, so the shrinkage branch (len(explicit_fvs) == 1) does
        # NOT fire. The consensus uses the rank-implied fallback and
        # stays at weight 1.0.
        snaps = [_snap("baseball_america", "X", rank=1)]
        p = build_timeseries(snaps)[0]
        pt = p.points[-1]
        assert pt.shrinkage_weight == 1.0
        assert pt.avg_fv_n == 0
        # Rank 1 implies FV 70 in the rank→FV table.
        assert pt.consensus_fv == 70.0

    def test_full_coverage_consensus_equals_mean(self):
        # 4 sources all at 70 → mean 70.
        snaps = [
            _snap("fangraphs",        "X", fv=70.0),
            _snap("espn",             "X", fv=70.0),
            _snap("just_baseball",    "X", fv=70.0),
            _snap("tjstats",          "X", fv=70.0),
        ]
        p = build_timeseries(snaps)[0]
        pt = p.points[-1]
        assert pt.shrinkage_weight == 1.0
        assert pt.consensus_fv_raw == 70.0
        assert pt.consensus_fv == 70.0

    def test_jesus_made_case_no_more_drift(self):
        # 4 explicit grades averaging 62.5 + 1 rank-only source.
        # snap_to_grade(62.5) → 62 (banker's rounding). The motivating
        # regression: with shrinkage, this collapsed below 61; now the
        # consensus exactly matches the raw arithmetic mean.
        snaps = [
            _snap("fangraphs",     "Made", fv=65.0),
            _snap("mlb_pipeline",  "Made", fv=65.0),
            _snap("tjstats",       "Made", fv=60.0),
            _snap("espn",          "Made", fv=60.0),
            _snap("just_baseball", "Made", rank=4),
        ]
        p = build_timeseries(snaps)[0]
        pt = p.points[-1]
        assert pt.consensus_fv_pre_shrinkage == 62.5
        assert pt.consensus_fv == 62.0
        assert pt.shrinkage_weight == 1.0

    def test_partial_coverage_no_pull(self):
        # 3 sources at 60 → mean 60. Used to drift to 58 under shrinkage.
        snaps = [
            _snap("fangraphs",     "X", fv=60.0),
            _snap("espn",          "X", fv=60.0),
            _snap("just_baseball", "X", fv=60.0),
        ]
        p = build_timeseries(snaps)[0]
        pt = p.points[-1]
        assert pt.consensus_fv == 60.0
        assert pt.consensus_fv_raw == 60.0
        assert pt.shrinkage_weight == 1.0

    def test_rank_only_consensus_is_rank_implied_mean(self):
        # 2 rank-only sources both implying FV 60 (rank 2 → 60 in the
        # rank→FV table). Consensus is exactly 60, no shrinkage drift.
        snaps = [
            _snap("baseball_america", "X", rank=2),
            _snap("the_athletic",     "X", rank=2),
        ]
        p = build_timeseries(snaps)[0]
        pt = p.points[-1]
        assert pt.avg_fv is None
        assert pt.consensus_fv_pre_shrinkage == 60.0
        assert pt.consensus_fv == 60.0
        assert pt.consensus_fv_raw == 60.0
        assert pt.shrinkage_weight == 1.0

    def test_multi_point_single_source_not_pulled(self):
        # Same source publishing across 3 snapshots — the player has 3
        # FV instances even though only 1 source contributed. Under the
        # single-INSTANCE semantics, this player is well-observed and
        # escapes the FV-35 pull. Each point's consensus equals the raw
        # published value at that snapshot.
        snaps = [
            _snap("fangraphs", "Smith", fv=60.0, date_="2024-02-15"),
            _snap("fangraphs", "Smith", fv=60.0, date_="2025-02-15"),
            _snap("fangraphs", "Smith", fv=60.0, date_="2026-02-15"),
        ]
        p = build_timeseries(snaps)[0]
        assert p.fv_total_instances == 3
        for pt in p.points:
            assert pt.consensus_fv == 60.0
            assert pt.consensus_fv_raw == 60.0
            assert pt.shrinkage_weight == 1.0

    def test_pool_doesnt_drag_individual_consensus(self):
        # The old "prior_mean_fv pulled from pool average" path is gone.
        # Three single-source prospects keep their published grades
        # regardless of how the pool looks. (single_source_k=0 isolates
        # this test from the new FV-35 pull-down — the policy under test
        # here is pool-prior absence, not single-source shrinkage.)
        snaps = [
            _snap("fangraphs", "A", fv=70.0),
            _snap("fangraphs", "B", fv=50.0),
            _snap("fangraphs", "C", fv=60.0),
        ]
        ts = build_timeseries(snaps, single_source_k=0)
        by_name = {p.player_name: p for p in ts}
        assert by_name["A"].points[-1].consensus_fv == 70.0
        assert by_name["B"].points[-1].consensus_fv == 50.0
        assert by_name["C"].points[-1].consensus_fv == 60.0

    def test_shrinkage_kwargs_are_inert(self):
        # The old shrinkage_k / shrinkage_n_full / prior_mean_fv kwargs
        # remain on build_timeseries for back-compat but are now no-ops.
        # Passing absurd values shouldn't change the consensus. We use
        # single_source_k=0 here to factor out the new FV-35 pull-down
        # so the assertion focuses on the legacy-kwargs no-op contract.
        snaps = [_snap("fangraphs", "X", fv=70.0)]
        p_default = build_timeseries(snaps, single_source_k=0)[0]
        p_extreme = build_timeseries(snaps, shrinkage_k=10.0,
                                     shrinkage_n_full=99, prior_mean_fv=20.0,
                                     single_source_k=0)[0]
        assert p_default.points[-1].consensus_fv == p_extreme.points[-1].consensus_fv == 70.0


# ---------------------------------------------------------------------------
# Just Baseball table parser (Step 1 of broadening-consensus integration)
# ---------------------------------------------------------------------------

class TestParseJbToolTable:
    def test_hitter_table(self):
        from scrapers import _parse_jb_tool_table
        html_block = """
        <table class="has-fixed-layout"><tbody>
          <tr>
            <td><strong>HIT</strong></td>
            <td><strong>Plate Disc.</strong></td>
            <td><strong>GAME POWER</strong></td>
            <td><strong>RUN</strong></td>
            <td><strong>FIELD</strong></td>
            <td><strong>FV</strong></td>
          </tr>
          <tr>
            <td>50/60</td><td>50/60</td><td>55/70</td>
            <td>70/70</td><td>55/65</td><td>70</td>
          </tr>
        </tbody></table>
        """
        tools, fv = _parse_jb_tool_table(html_block)
        assert fv == 70.0
        assert tools["hit"] == 60.0
        assert tools["pitch_sel"] == 60.0   # Plate Disc → pitch_sel
        assert tools["game_pwr"] == 70.0
        assert tools["speed"] == 70.0       # RUN → speed
        assert tools["field"] == 65.0

    def test_pitcher_table_with_sweeper_and_splitter(self):
        from scrapers import _parse_jb_tool_table
        html_block = """
        <table><tbody>
          <tr>
            <td><strong>FASTBALL</strong></td>
            <td><strong>Sweeper</strong></td>
            <td><strong>Slider</strong></td>
            <td><strong>CURVEBALL</strong></td>
            <td><strong>Splitter</strong></td>
            <td><strong>COMMAND</strong></td>
            <td><strong>FV</strong></td>
          </tr>
          <tr>
            <td>70/70</td><td>60/60</td><td>50/50</td>
            <td>55/60</td><td>50/55</td><td>45/50</td><td>65</td>
          </tr>
        </tbody></table>
        """
        tools, fv = _parse_jb_tool_table(html_block)
        assert fv == 65.0
        assert tools["fb"] == 70.0
        # Both sweeper + slider map to sl; the later (slider) value
        # overwrites the earlier (sweeper) — both are real publications.
        assert tools["sl"] == 50.0
        assert tools["cb"] == 60.0
        # Both splitter + nothing maps to ch — splitter rides the changeup slot.
        assert tools["ch"] == 55.0
        assert tools["cmd"] == 50.0

    def test_no_table_returns_none(self):
        from scrapers import _parse_jb_tool_table
        tools, fv = _parse_jb_tool_table("<p>No table here</p>")
        assert tools is None
        assert fv is None

    def test_out_of_range_dropped(self):
        from scrapers import _parse_jb_tool_table
        html_block = """
        <table><tr><td>HIT</td><td>RUN</td><td>FV</td></tr>
        <tr><td>15/99</td><td>50/55</td><td>60</td></tr></table>
        """
        tools, fv = _parse_jb_tool_table(html_block)
        assert fv == 60.0
        assert "hit" not in (tools or {})  # 99 fails 20-80 gate
        assert tools["speed"] == 55.0


# ---------------------------------------------------------------------------
# ESPN prose parser (Step 3) — exercises the fallback that handles
# ESPN's 2025+ articles where structured "Hit: 45/50" lines were
# replaced with descriptive prose.
# ---------------------------------------------------------------------------

class TestParseEspnProseTools:
    def test_plus_runner_to_speed_60(self):
        from scrapers import _parse_espn_prose_tools
        tools = _parse_espn_prose_tools(
            "Bazzana is a plus runner who will steal some bags and play decent defense."
        )
        assert tools["speed"] == 60.0

    def test_numeric_grade_pattern(self):
        from scrapers import _parse_espn_prose_tools
        tools = _parse_espn_prose_tools(
            "Griffin has a 70 raw power, plus speed, and an above-average hit tool."
        )
        assert tools["raw_pwr"] == 70.0
        assert tools["speed"] == 60.0
        assert tools["hit"] == 55.0  # above-average → 55

    def test_velocity_to_fb_grade(self):
        from scrapers import _parse_espn_prose_tools
        # 94-98 mph fastball that peaks at 99 → fb=65 (anchor sits_max=98)
        tools = _parse_espn_prose_tools(
            "His 94-98 mph fastball peaks at 99 mph."
        )
        assert tools["fb"] == 65.0

    def test_raw_vs_game_power_disambiguation(self):
        from scrapers import _parse_espn_prose_tools
        # When both "raw power" and "game power" appear, longer match wins.
        tools = _parse_espn_prose_tools("He has plus raw power and average game power.")
        assert tools.get("raw_pwr") == 60.0
        assert tools.get("game_pwr") == 50.0

    def test_plus_plus_glove(self):
        from scrapers import _parse_espn_prose_tools
        tools = _parse_espn_prose_tools("Elite defender with a plus-plus glove.")
        # "elite defender" or "plus-plus glove" — at least one maps field to 70.
        assert tools.get("field") in (60.0, 70.0)

    def test_empty_returns_none(self):
        from scrapers import _parse_espn_prose_tools
        assert _parse_espn_prose_tools("") is None
        assert _parse_espn_prose_tools("No tools described here at all.") is None

    def test_full_parser_falls_through_to_prose_when_no_structured(self):
        """_parse_espn_tools must fall through to _parse_espn_prose_tools
        when no structured 'Label: 45/50' blocks are present."""
        from scrapers import _parse_espn_tools
        tools = _parse_espn_tools("He's a plus runner with an above-average hit tool.")
        assert tools is not None
        assert tools.get("speed") == 60.0
        assert tools.get("hit") == 55.0


# ---------------------------------------------------------------------------
# Pipeline org-page URL list (Step 2) — smoke-check the catalog so that
# accidental removal/typo is caught at test time, not at scrape time.
# ---------------------------------------------------------------------------

class TestPipelineOrgIntervals:
    def test_thirty_orgs_per_year(self):
        from scrapers import MLB_PIPELINE_ORG_INTERVALS, MLB_PIPELINE_ORG_SLUGS, MLB_PIPELINE_ORG_YEARS
        assert len(MLB_PIPELINE_ORG_SLUGS) == 30
        assert len(MLB_PIPELINE_ORG_INTERVALS) == 30 * len(MLB_PIPELINE_ORG_YEARS)

    def test_url_pattern(self):
        from scrapers import MLB_PIPELINE_ORG_INTERVALS
        url, label, snap, year, cache_key = MLB_PIPELINE_ORG_INTERVALS[0]
        assert url.startswith("https://www.mlb.com/prospects/")
        assert cache_key.startswith("mlb_pipeline_")
        assert "org_" in cache_key

    def test_cache_keys_unique(self):
        from scrapers import MLB_PIPELINE_ORG_INTERVALS
        keys = [interval[4] for interval in MLB_PIPELINE_ORG_INTERVALS]
        assert len(set(keys)) == len(keys)


# ---------------------------------------------------------------------------
# Cutter as canonical pitcher key (Step 1a)
# ---------------------------------------------------------------------------

class TestCutterCanonical:
    def test_ct_in_pitcher_keys(self):
        from scrapers import PITCHER_TOOL_KEYS, ALL_TOOL_KEYS
        assert "ct" in PITCHER_TOOL_KEYS
        assert "ct" in ALL_TOOL_KEYS


# ---------------------------------------------------------------------------
# Forward-fill verification — the Tool composite uses each source's
# MOST RECENT publication. This is the latest-only rule the UI source-
# history dropdown discloses.
# ---------------------------------------------------------------------------

class TestConsensusForwardFill:
    def test_uses_latest_per_source(self):
        """When the same source publishes tools on two different dates,
        the final consensus point must use the LATER value only — not
        the mean of both. Forward-fill picks the latest per source."""
        older = Snapshot(
            source="fangraphs", snapshot_date="2024-02-14",
            interval_label="2024report",
            player_key="x", player_name="X",
            position="SS", org="PIT", rank=None, fv=50.0, status="active",
            tools={"hit": 50.0},
        )
        newer = Snapshot(
            source="fangraphs", snapshot_date="2025-07-31",
            interval_label="2025updated",
            player_key="x", player_name="X",
            position="SS", org="PIT", rank=None, fv=60.0, status="active",
            tools={"hit": 60.0},
        )
        ts = build_timeseries([older, newer], single_source_k=0)
        assert len(ts) == 1
        latest_point = ts[0].points[-1]
        # The final consensus uses the newer publication only —
        # forward-fill drops the older snapshot once a newer one exists.
        assert latest_point.tools_consensus["hit"] == 60.0, \
            f"expected 60 (latest), got {latest_point.tools_consensus['hit']} (mean would be 55)"

    def test_two_sources_consensus_uses_each_latest(self):
        """When two sources publish, the consensus is the mean of EACH
        source's latest value — not a mean across all snapshots."""
        fg_old = Snapshot(
            source="fangraphs", snapshot_date="2024-02-14",
            interval_label="2024report",
            player_key="x", player_name="X", position="SS", org="PIT",
            rank=None, fv=50.0, status="active", tools={"hit": 50.0},
        )
        fg_new = Snapshot(
            source="fangraphs", snapshot_date="2025-07-31",
            interval_label="2025updated",
            player_key="x", player_name="X", position="SS", org="PIT",
            rank=None, fv=60.0, status="active", tools={"hit": 60.0},
        )
        pipe_new = Snapshot(
            source="mlb_pipeline", snapshot_date="2025-08-01",
            interval_label="MLB Pipeline 2025 Top 100",
            player_key="x", player_name="X", position="SS", org="PIT",
            rank=None, fv=55.0, status="active", tools={"hit": 50.0},
        )
        ts = build_timeseries([fg_old, fg_new, pipe_new], single_source_k=0)
        latest_point = ts[0].points[-1]
        # FG latest = 60, Pipeline latest = 50, mean = 55.
        # The 50 from fg_old must NOT participate.
        assert latest_point.tools_consensus["hit"] == 55.0
