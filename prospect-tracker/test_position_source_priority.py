"""FanGraphs-priority position resolution (v6).

`_latest_meta` previously picked whichever source happened to publish
last. v6 prefers FanGraphs as the position authority because FG forward-
projects positions (including SP / SIRP / MIRP role tagging), while
other sources tend to mirror the current MiLB roster designation.
"""

from __future__ import annotations

import unittest

from scrapers import Snapshot
from consensus import _latest_meta


def _snap(source, date_, position, org="PIT"):
    return Snapshot(
        source=source, snapshot_date=date_, interval_label="2026 Report",
        player_key="paul_skenes", player_name="Paul Skenes",
        position=position, org=org, rank=1, fv=70.0, status="active",
    )


class TestFangraphsPositionPriority(unittest.TestCase):
    def test_fg_wins_over_more_recent_other_source(self):
        # MLB Pipeline snapshot is newer (2026-04) but FG snapshot
        # (2026-02) carries the role-tagged "SIRP" position. FG should
        # win the position field.
        snaps = [
            _snap("fangraphs",    "2026-02-15", position="SIRP"),
            _snap("mlb_pipeline", "2026-04-01", position="RHP"),
        ]
        name, pos, org = _latest_meta(snaps)
        self.assertEqual(name, "Paul Skenes")
        self.assertEqual(pos, "SIRP")

    def test_fg_with_null_position_falls_back(self):
        # FG snapshot exists but has no position → fall back to another
        # source's position rather than returning None.
        snaps = [
            _snap("fangraphs",    "2026-04-01", position=None),
            _snap("mlb_pipeline", "2026-03-01", position="SP"),
        ]
        _, pos, _ = _latest_meta(snaps)
        self.assertEqual(pos, "SP")

    def test_no_fg_snapshot_falls_back_to_latest(self):
        # When FG hasn't graded this prospect at all, latest-non-null
        # from any source wins (preserves the old behavior).
        snaps = [
            _snap("mlb_pipeline", "2026-04-01", position="MIRP"),
            _snap("baseball_america", "2026-01-01", position="SP"),
        ]
        _, pos, _ = _latest_meta(snaps)
        self.assertEqual(pos, "MIRP")

    def test_org_still_uses_latest_non_null(self):
        # Position priority is FG-only; org resolution stays on the
        # latest-non-null heuristic.
        snaps = [
            _snap("fangraphs",    "2026-02-15", position="SS", org="PIT"),
            _snap("mlb_pipeline", "2026-04-01", position=None, org="SDP"),
        ]
        _, pos, org = _latest_meta(snaps)
        self.assertEqual(pos, "SS")    # FG won
        self.assertEqual(org, "SDP")    # latest-non-null won


if __name__ == "__main__":
    unittest.main()
