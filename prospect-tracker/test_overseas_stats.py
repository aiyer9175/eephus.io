"""Tests for overseas_stats.py — FG player-page parser.

Uses the cached Yamashita page from .cache/ so the parser is exercised
offline. Verifies the header-cleaning and per-season extraction stay
stable when FG ships a glyph-duplicated header like 'WW - Wins'.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from overseas_stats import (
    _clean_header,
    _to_num,
    scrape_fg_player_stats,
)

CACHE = Path(__file__).parent / ".cache"


class HeaderClean(unittest.TestCase):
    def test_strips_tooltip_suffix(self):
        self.assertEqual(_clean_header("WW - Wins"), "W")
        self.assertEqual(_clean_header("K/9K/9 - Strikeouts per 9 Innings"), "K/9")
        self.assertEqual(_clean_header("ERAERA - Earned Run Average"), "ERA")

    def test_passes_through_clean_header(self):
        self.assertEqual(_clean_header("Season"), "Season")
        self.assertEqual(_clean_header("Team"), "Team")

    def test_empty(self):
        self.assertEqual(_clean_header(""), "")


class NumCoerce(unittest.TestCase):
    def test_percent(self):
        self.assertAlmostEqual(_to_num("82.2%"), 0.822)
        self.assertAlmostEqual(_to_num("18.5%"), 0.185)

    def test_int(self):
        self.assertEqual(_to_num("95"), 95)

    def test_float(self):
        self.assertAlmostEqual(_to_num("1.61"), 1.61)
        self.assertAlmostEqual(_to_num(".280"), 0.28)

    def test_blank(self):
        self.assertIsNone(_to_num(""))
        self.assertIsNone(_to_num(None))
        self.assertIsNone(_to_num("—"))

    def test_string_passthrough(self):
        # Team / Level column values fall through as strings.
        self.assertEqual(_to_num("ORX"), "ORX")
        self.assertEqual(_to_num("NPB"), "NPB")


class ScraperRoundTrip(unittest.TestCase):
    """Round-trip a cached FG player page. Skips when the cache miss."""

    CACHE_FILE = CACHE / "fg_player_sa3063816.html"

    def setUp(self):
        if not self.CACHE_FILE.exists():
            self.skipTest("no cached Yamashita FG page — "
                          "run scrape_fg_player_stats('sa3063816') once first")

    def test_returns_npb_seasons(self):
        rows = scrape_fg_player_stats("sa3063816")
        self.assertGreaterEqual(len(rows), 3)
        # All rows should be NPB level with valid season + ERA
        npb_rows = [r for r in rows if r.get("level") == "NPB"]
        self.assertGreaterEqual(len(npb_rows), 3)
        for r in npb_rows[:3]:
            self.assertGreaterEqual(r.get("season"), 2020)
            self.assertGreater(r.get("ip") or 0, 0)
            self.assertGreater(r.get("era") or 0, 0)

    def test_pitcher_keys_recognized(self):
        rows = scrape_fg_player_stats("sa3063816")
        if not rows:
            self.skipTest("scraper returned no rows")
        r = rows[0]
        self.assertIn("ip", r)
        self.assertIn("era", r)
        self.assertIn("k_per_9", r)
        self.assertTrue(r.get("_is_pitcher"))


if __name__ == "__main__":
    unittest.main()
