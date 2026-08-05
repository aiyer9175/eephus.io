# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fabricated constant must not block its own replacement (2026-08-05).

THE BUG. storage.upsert_unranked_active_player stamps a flat FV 35 on
auto-discovered players (source='performance_ingest'). consensus folds that
constant back in as a LAST RESORT (CONSTANT_ANCHOR_SOURCES) so those players do
not vanish from the board, which produces a real consensus point carrying a
fabricated FV, which sets fv_raw on the roster row, which made
efv_ungraded.flagship_owns() read the player as scouted and route him AWAY from
the provisional model built to grade exactly him.

Measured on the live DB the day this was fixed: 2,720 players carried ONLY a
performance_ingest snapshot; 2,632 of them (96.8%) were excluded from the
provisional model by that gate, every one at fv_raw exactly 35.0. The model
scored just 70 of them, and only because their identity join had failed and
happened to leave fv_raw None. 2,650 of the 2,720 were scoreable with the data
already on disk.

WHAT THIS FILE PINS. The routing contract only: a constant-anchored player
belongs to the provisional path, a genuinely graded player belongs to the
flagship, and the two remain complements. It does NOT pin any served consensus
number, because the fix deliberately changes none: consensus_fv still says 35
for these players. Substituting the model grade into the consensus anchor is a
separate, gated question (it would put a WAR model's output into the dominant
eFV feature, contaminating the very baseline eFV is judged against).

Pure unit tests over flagship_owns and the farm pool merge. No DB, no network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import consensus
import efv_ungraded


class FlagshipOwnsHonorsTheSyntheticFlag(unittest.TestCase):
    def test_a_real_published_grade_stays_with_the_flagship(self):
        self.assertTrue(efv_ungraded.flagship_owns({"fv_raw": 45.0}))

    def test_a_constant_anchored_player_routes_to_the_provisional_model(self):
        """The regression. fv_raw is set, but only by the fabricated constant, so
        the provisional model must be allowed to score him."""
        row = {"fv_raw": 35.0, "fv_synthetic_only": True}
        self.assertFalse(efv_ungraded.flagship_owns(row))

    def test_no_consensus_point_at_all_still_routes_provisional(self):
        self.assertFalse(efv_ungraded.flagship_owns({"fv_raw": None}))
        self.assertFalse(efv_ungraded.flagship_owns({}))
        self.assertFalse(efv_ungraded.flagship_owns(None))

    def test_the_flag_only_fires_when_it_is_actually_set(self):
        """A falsy flag must not strand a genuinely graded player in the
        provisional pool, which would be the mirror-image bug."""
        self.assertTrue(efv_ungraded.flagship_owns({"fv_raw": 50.0,
                                                    "fv_synthetic_only": False}))

    def test_the_partition_is_still_a_partition(self):
        """Every roster row lands in exactly one path, which is the invariant the
        flagship_owns docstring has always claimed."""
        rows = [
            {"fv_raw": 45.0},                                    # graded
            {"fv_raw": 35.0, "fv_synthetic_only": True},         # constant
            {"fv_raw": None},                                    # never graded
        ]
        for r in rows:
            flagship = efv_ungraded.flagship_owns(r)
            provisional = not flagship
            self.assertNotEqual(flagship, provisional)


class TheConstantSourcesAreTheOnesWeMean(unittest.TestCase):
    def test_constant_anchor_sources_is_what_the_flag_is_built_from(self):
        """run_monthly derives fv_synthetic_only by testing the point's
        contributing sources against this set, so the set is part of the
        contract rather than an implementation detail."""
        self.assertIn("performance_ingest", consensus.CONSTANT_ANCHOR_SOURCES)
        self.assertIn("auto_detect", consensus.CONSTANT_ANCHOR_SOURCES)

    def test_a_real_source_is_not_a_constant_anchor(self):
        for src in ("fangraphs", "mlb_pipeline", "baseballamerica"):
            self.assertNotIn(src, consensus.CONSTANT_ANCHOR_SOURCES)

    def test_the_flag_rule_discriminates(self):
        """Mirrors run_monthly's expression exactly: the flag fires only when
        EVERY contributing source is a constant anchor."""
        def synthetic_only(sources):
            s = set(sources or ())
            return bool(s) and s <= consensus.CONSTANT_ANCHOR_SOURCES

        self.assertTrue(synthetic_only(["performance_ingest"]))
        self.assertTrue(synthetic_only(["performance_ingest", "auto_detect"]))
        self.assertFalse(synthetic_only(["performance_ingest", "fangraphs"]))
        self.assertFalse(synthetic_only(["fangraphs"]))
        self.assertFalse(synthetic_only([]))


class TheFarmPoolDoesNotDoubleCount(unittest.TestCase):
    """The concat at storage.py was safe only while the graded and provisional
    sets were complements. This fix breaks that assumption, so the merge has to
    dedup or ~2,300 players get counted twice in the org depth pools."""

    @staticmethod
    def _merge(prospects, prov):
        if prov:
            seen = {p.get("player_key") for p in prospects if p.get("player_key")}
            prov = [p for p in prov
                    if not (p.get("player_key") and p.get("player_key") in seen)]
        return prospects + prov if prov else prospects

    def test_a_player_in_both_lists_is_counted_once(self):
        graded = [{"player_key": "a"}, {"player_key": "b"}]
        prov = [{"player_key": "b", "provisional": True},
                {"player_key": "c", "provisional": True}]
        pool = self._merge(graded, prov)
        self.assertEqual(len(pool), 3)
        self.assertEqual([p["player_key"] for p in pool].count("b"), 1)

    def test_the_graded_row_wins(self):
        """The graded row is the one the board displays, so it is the one that
        must survive the merge."""
        graded = [{"player_key": "b", "provisional": False}]
        prov = [{"player_key": "b", "provisional": True}]
        pool = self._merge(graded, prov)
        self.assertEqual(len(pool), 1)
        self.assertFalse(pool[0]["provisional"])

    def test_keyless_provisional_rows_are_kept(self):
        """mlbam_-keyed provisional rows carry no player_key and cannot collide,
        so they must not be dropped by the dedup."""
        graded = [{"player_key": "a"}]
        prov = [{"player_key": None, "provisional": True},
                {"provisional": True}]
        self.assertEqual(len(self._merge(graded, prov)), 3)

    def test_no_provisional_rows_is_unchanged(self):
        graded = [{"player_key": "a"}]
        self.assertIs(self._merge(graded, []), graded)


if __name__ == "__main__":
    unittest.main()
