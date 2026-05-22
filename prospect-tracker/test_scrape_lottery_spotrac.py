"""Smoke tests for the Spotrac draft-order and Tankathon lottery scrapers.

Both use cached HTML from .cache/ so the tests run offline. We only
check shape + sane counts — the upstream pages are authoritative."""

from __future__ import annotations

import unittest
from pathlib import Path

from scrapers import scrape_spotrac_draft_order, scrape_tankathon_lottery

CACHE = Path(__file__).parent / ".cache"


class SpotracSmoke(unittest.TestCase):
    def setUp(self):
        if not (CACHE / "spotrac_draft_2026.html").exists():
            self.skipTest("no cached Spotrac 2026 page")

    def test_returns_picks(self):
        rows = scrape_spotrac_draft_order(2026)
        self.assertGreater(len(rows), 500, "expected ~613 picks in 2026 draft")
        # Spot-check pick 1 — CHW had the worst record in 2025
        p1 = next(r for r in rows if r["pick_overall"] == 1)
        self.assertEqual(p1["team"], "CHW")
        self.assertEqual(p1["round_label"], "1")
        self.assertEqual(p1["pick_in_round"], 1)
        self.assertGreater(p1["slot_usd"] or 0, 10_000_000)
        self.assertEqual(p1["source"], "spotrac")

    def test_round_1_has_30_picks(self):
        rows = scrape_spotrac_draft_order(2026)
        r1 = [r for r in rows if r.get("round_label") == "1"]
        # 30 regular R1 picks + comp / PPI / CBA picks. Allow some slack.
        self.assertGreaterEqual(len(r1), 30)
        self.assertLessEqual(len(r1), 50)


class TankathonSmoke(unittest.TestCase):
    def setUp(self):
        if not (CACHE / "tankathon_mlb.html").exists():
            self.skipTest("no cached Tankathon page")

    def test_returns_top_6_odds(self):
        rows = scrape_tankathon_lottery(2027)
        self.assertGreaterEqual(len(rows), 5)
        self.assertLessEqual(len(rows), 6)
        for r in rows:
            self.assertEqual(r["draft_year"], 2027)
            self.assertEqual(r["pick_pos"], 1)
            self.assertEqual(r["source"], "tankathon")
            # Bottom-6 teams typically have 6-19% odds at #1
            self.assertGreater(r["odds_pct"], 1.0)
            self.assertLess(r["odds_pct"], 25.0)

    def test_odds_sum_under_100(self):
        """The 18 lottery-eligible teams (top 6 we capture + rest)
        sum to 100% on Tankathon. We capture only top 6, which is
        roughly 65-75% of the total odds."""
        rows = scrape_tankathon_lottery(2027)
        total = sum(r["odds_pct"] for r in rows)
        self.assertGreater(total, 60.0)
        self.assertLess(total, 100.0)


if __name__ == "__main__":
    unittest.main()
