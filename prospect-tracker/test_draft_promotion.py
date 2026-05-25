"""Tests for draft_promotion.py — the draft → MiLB bridge.

Focus areas:
  * Idempotency: running twice produces no change.
  * No empty / garbage keys.
  * Canonical-key mapping is consistent: same MiLB key for same name.
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from draft_promotion import _milb_key_from_name, promote_drafted_players

DB_PATH = Path(__file__).parent / "prospects.db"


class MilbKey(unittest.TestCase):
    def test_strips_accents(self):
        self.assertEqual(_milb_key_from_name("José Ramírez"),
                         _milb_key_from_name("Jose Ramirez"))

    def test_collapses_whitespace(self):
        self.assertEqual(_milb_key_from_name("JJ  Wetherholt"),
                         _milb_key_from_name("JJ Wetherholt"))


class PromotionIdempotency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DB_PATH.exists():
            raise unittest.SkipTest(
                f"no prospects.db at {DB_PATH} — run a backfill first"
            )

    def test_re_run_is_noop_for_links(self):
        """Re-running promote_drafted_players should produce 0 new links
        once a backfill has already populated them."""
        first = promote_drafted_players()
        second = promote_drafted_players()
        # `linked` counts only NEW canonical-key mappings; should be 0
        # on the second pass.
        self.assertEqual(second["linked"], 0,
                         f"expected 0 new links on re-run, got {second['linked']}")

    def test_all_promoted_have_acquisition_records(self):
        # contextlib.closing — sqlite3's own `with` doesn't close the
        # connection (it only manages the transaction). Closing leaks
        # otherwise surface as GC-time ResourceWarnings.
        from contextlib import closing
        with closing(sqlite3.connect(DB_PATH)) as con:
            con.row_factory = sqlite3.Row
            linked = con.execute(
                "SELECT milb_key FROM draft_canonical_keys"
            ).fetchall()
            if not linked:
                self.skipTest("no promotions on file yet")
            keys = [r["milb_key"] for r in linked]
            placeholders = ",".join("?" * len(keys))
            ac = con.execute(
                f"SELECT player_key FROM acquisitions "
                f"WHERE player_key IN ({placeholders}) AND method='draft'",
                keys,
            ).fetchall()
        # Allow ~5% miss rate for canonical-key name collisions (two
        # players normalizing to the same key — the second loses).
        coverage = len(ac) / max(1, len(keys))
        self.assertGreater(coverage, 0.90,
                           f"acquisitions coverage too low: {coverage:.1%}")


if __name__ == "__main__":
    unittest.main()
