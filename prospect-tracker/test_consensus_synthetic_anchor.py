# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A fabricated constant must not vote in the consensus FV (2026-07-31).

storage.upsert_unranked_active_player stamps a FLAT FV 35.0 on every
auto-discovered player (`source='performance_ingest'`; measured on the live
DB: 2,808 rows, DISTINCT fv == {35.0}). The consensus vote is equal-weight
(data/source_weights.json ships weights={}, and absent sources vote at 1.0),
so for the 32 players who have BOTH a real published grade and that stamp, a
fabricated 35 was averaged in at FanGraphs' weight - dragging a published 40
down to a served 36. Same defect class as the fabricated BA-statcast FV-40
removed on 2026-07-30.

The constant still has to cover the ~2,776 players NO outlet has ever graded:
their performance_ingest rows carry rank = NULL, so there is no rank-implied
fallback and dropping the vote outright would delete them from the board.
Hence: LAST RESORT, never a co-vote.

Pure unit tests over compute_consensus_point / build_timeseries. No DB, no
network, no data/ artifacts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import consensus
from consensus import (CONSTANT_ANCHOR_SOURCES, build_timeseries,
                       compute_consensus_point)
from scrapers import Snapshot

SYNTH_FV = 35.0


def _s(source, fv, *, key="p", date="2026-06-01", rank=None, label=None):
    return Snapshot(source=source, snapshot_date=date,
                    interval_label=label or f"{source} list",
                    player_key=key, player_name="Player One", position="SS",
                    org="NYY", rank=rank, fv=fv, status="active", tools=None)


class ConstantAnchorSet(unittest.TestCase):
    def test_contains_the_two_constant_sources(self):
        self.assertIn("performance_ingest", CONSTANT_ANCHOR_SOURCES)
        self.assertIn("auto_detect", CONSTANT_ANCHOR_SOURCES)

    def test_draft_signing_still_votes(self):
        """draft_signing is flagged synthetic in grade_normalization only so
        the quantile map passes its SCALE through raw. Its VALUE is a real
        published draft-board FV (138 rows, varying), so it keeps its vote."""
        self.assertNotIn("draft_signing", CONSTANT_ANCHOR_SOURCES)


class ExcludedWhenARealGradeExists(unittest.TestCase):
    def test_single_real_grade_is_not_averaged_with_the_constant(self):
        pt = compute_consensus_point(
            [_s("fangraphs", 45.0), _s("performance_ingest", SYNTH_FV)],
            total_fv_instances=2)
        self.assertEqual(pt.avg_fv, 45.0)
        self.assertEqual(pt.avg_fv_n, 1)
        self.assertNotIn("performance_ingest", pt.sources_contributing)

    def test_the_old_behaviour_would_have_averaged_to_40(self):
        """Documents the exact defect: (45 + 35) / 2 = 40, a full grade below
        the only real opinion on file."""
        self.assertEqual((45.0 + SYNTH_FV) / 2, 40.0)
        pt = compute_consensus_point(
            [_s("fangraphs", 45.0), _s("performance_ingest", SYNTH_FV)],
            total_fv_instances=2)
        self.assertNotEqual(pt.avg_fv, 40.0)

    def test_multi_source_consensus_ignores_the_constant(self):
        pt = compute_consensus_point(
            [_s("fangraphs", 50.0), _s("mlb_pipeline", 60.0),
             _s("performance_ingest", SYNTH_FV)],
            total_fv_instances=3)
        self.assertEqual(pt.avg_fv, 55.0)
        self.assertEqual(pt.avg_fv_n, 2)
        self.assertEqual(pt.sources_contributing, ["fangraphs", "mlb_pipeline"])

    def test_per_source_still_shows_the_stamp(self):
        """Excluded from the VOTE, not hidden. The per-source breakdown is the
        audit trail for why a player is on the board at all."""
        pt = compute_consensus_point(
            [_s("fangraphs", 45.0), _s("performance_ingest", SYNTH_FV)],
            total_fv_instances=2)
        self.assertIn("performance_ingest", pt.per_source)
        self.assertEqual(pt.per_source["performance_ingest"]["fv_published"],
                         SYNTH_FV)

    def test_a_real_35_is_still_a_real_vote(self):
        """An outlet that genuinely publishes FV 35 must be unaffected - the
        exclusion keys on the SOURCE, never on the value."""
        pt = compute_consensus_point([_s("fangraphs", 35.0)],
                                     total_fv_instances=1)
        self.assertEqual(pt.avg_fv_n, 1)
        self.assertIn("fangraphs", pt.sources_contributing)


class LastResortFallback(unittest.TestCase):
    def test_ungraded_player_keeps_a_consensus_point(self):
        """The ~2,776 auto-tracked players with no published grade anywhere
        must NOT lose their point (their rows carry rank = NULL, so there is
        no rank-implied fallback to catch them)."""
        pt = compute_consensus_point([_s("performance_ingest", SYNTH_FV)],
                                     total_fv_instances=0)
        self.assertIsNotNone(pt)
        self.assertEqual(pt.consensus_fv, SYNTH_FV)
        self.assertEqual(pt.sources_contributing, ["performance_ingest"])

    def test_fallback_value_is_unchanged_by_the_shrinkage(self):
        """Pulling 35 toward a prior of 35 is a no-op, so the ungraded cohort
        serves exactly what it served before this change."""
        pt = compute_consensus_point([_s("performance_ingest", SYNTH_FV)],
                                     total_fv_instances=0)
        self.assertEqual(pt.consensus_fv_raw, SYNTH_FV)

    def test_no_fv_anywhere_still_returns_none(self):
        self.assertIsNone(compute_consensus_point(
            [_s("fangraphs", None)], total_fv_instances=0))


class InstanceCounting(unittest.TestCase):
    """The single-instance uncertainty pull fires when a player has <= 1
    published-FV observation ever. A fabricated stamp is not an observation,
    so it must not buy a lone real grade an escape from the pull."""

    def _latest(self, ts):
        p = ts[0]
        return max(p.points, key=lambda q: q.snapshot_date)

    def test_constant_does_not_count_as_corroboration(self):
        snaps = [_s("fangraphs", 45.0, date="2026-06-01"),
                 _s("performance_ingest", SYNTH_FV, date="2026-06-02")]
        pt = self._latest(build_timeseries(snaps))
        # 1 real instance -> the pull fires: 45 * 2/3 + 35 * 1/3 = 41.67
        self.assertLess(pt.shrinkage_weight, 1.0)
        self.assertAlmostEqual(pt.consensus_fv_raw, 41.67, places=1)

    def test_two_real_instances_still_escape_the_pull(self):
        snaps = [_s("fangraphs", 45.0, date="2026-05-01"),
                 _s("fangraphs", 45.0, date="2026-06-01", label="fg later"),
                 _s("performance_ingest", SYNTH_FV, date="2026-06-02")]
        pt = self._latest(build_timeseries(snaps))
        self.assertEqual(pt.shrinkage_weight, 1.0)
        self.assertEqual(pt.consensus_fv_raw, 45.0)

    def test_synthetic_only_player_survives_the_zero_count(self):
        ts = build_timeseries([_s("performance_ingest", SYNTH_FV)])
        self.assertEqual(len(ts), 1)
        pt = self._latest(ts)
        self.assertEqual(pt.consensus_fv, SYNTH_FV)


class NoCollateral(unittest.TestCase):
    def test_players_with_no_synthetic_row_are_untouched(self):
        """Control cohort. Measured on the live DB across 600 sampled
        no-synthetic players: zero moved."""
        snaps = [_s("fangraphs", 50.0), _s("mlb_pipeline", 55.0)]
        before = compute_consensus_point(snaps, total_fv_instances=2)
        self.assertEqual(before.avg_fv, 52.5)
        self.assertEqual(before.avg_fv_n, 2)

    def test_rank_only_sources_still_reach_the_rank_implied_fallback(self):
        pt = compute_consensus_point(
            [_s("baseball_america", None, rank=25, label="BA Top 100")],
            total_fv_instances=0)
        self.assertIsNotNone(pt)
        self.assertIsNone(pt.avg_fv)
        self.assertIsNotNone(pt.rank_implied_fv)


if __name__ == "__main__":
    unittest.main()
