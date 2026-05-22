"""Smoke tests for scrape_mlb_draft_tracker — the MLB Stats API
draft-results scraper. Uses cached JSON from .cache/ so the tests
run offline."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scrapers import scrape_mlb_draft_tracker

CACHE = Path(__file__).parent / ".cache"


class DraftTrackerSmoke(unittest.TestCase):
    """Round-trip a real cached draft response and confirm the parser
    produces the expected shape. We only check shape + sane counts —
    the API itself is authoritative."""

    def test_2024_picks_have_expected_fields(self):
        cache_file = CACHE / "mlb_draft_api_2024.json"
        if not cache_file.exists():
            self.skipTest("no cached 2024 draft response — "
                          "run scrape_mlb_draft_tracker(2024) once first")
        rows = scrape_mlb_draft_tracker(2024)
        self.assertGreater(len(rows), 500, "expected ~615 picks in 2024 draft")
        # Spot-check the #1 pick
        p1 = next(r for r in rows if r["pick_overall"] == 1)
        self.assertEqual(p1["team"], "CLE")
        self.assertEqual(p1["player_name"], "Travis Bazzana")
        self.assertEqual(p1["player_key"], "draft_2024_travis_bazzana")
        self.assertGreater(p1["bonus_usd"] or 0, 8_000_000)
        self.assertEqual(p1["signed"], 1)
        self.assertEqual(p1["source"], "mlb_stats_api")

    def test_payload_shape_is_upserter_compatible(self):
        """Every emitted dict must have the columns upsert_draft_results expects."""
        required = {
            "draft_year", "pick_overall", "team", "player_name", "signed",
        }
        cache_file = CACHE / "mlb_draft_api_2024.json"
        if not cache_file.exists():
            self.skipTest("no cached 2024 draft response")
        rows = scrape_mlb_draft_tracker(2024)
        for r in rows[:50]:
            self.assertTrue(required.issubset(r.keys()),
                            f"missing required cols: {required - set(r.keys())}")
            self.assertIsInstance(r["pick_overall"], int)
            self.assertIsInstance(r["draft_year"], int)


if __name__ == "__main__":
    unittest.main()
