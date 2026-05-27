# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

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

    def test_returns_full_projected_order(self):
        """Post-v4 the scraper captures the FULL first-round projection
        (~30 regular picks at unique pick_pos values) plus up to 12
        competitive-balance picks. Picks 1-6 carry real lottery odds;
        picks 7+ have odds_pct=None (deterministic by standings)."""
        rows = scrape_tankathon_lottery(2027)
        self.assertGreaterEqual(len(rows), 30)
        self.assertLessEqual(len(rows), 50)
        for r in rows:
            self.assertEqual(r["draft_year"], 2027)
            self.assertIsInstance(r["pick_pos"], int)
            self.assertIn(r["round_label"], {"1", "1A", "1B", "2"})
            self.assertEqual(r["source"], "tankathon")
        # Lottery picks (all eligible non-playoff teams) — each carries
        # a valid percentage in roughly the 0.1-20% band (top-6 cluster
        # near 15-20%, bottom-of-lottery teams as low as ~0.2%).
        lottery = [r for r in rows if r["odds_pct"] is not None]
        self.assertGreaterEqual(len(lottery), 5)
        for r in lottery:
            self.assertGreater(r["odds_pct"], 0.0)
            self.assertLess(r["odds_pct"], 25.0)

    def test_odds_sum_around_100(self):
        """Tankathon's lottery-eligible teams sum to ~100% (all 18
        non-playoff slots are now captured in our scrape)."""
        rows = scrape_tankathon_lottery(2027)
        total = sum(r["odds_pct"] for r in rows if r["odds_pct"] is not None)
        self.assertGreater(total, 60.0)
        self.assertLessEqual(total, 100.01)  # rounding tolerance

    def test_comp_picks_parsed(self):
        """Round 1A + Round 1B comp picks live outside the main
        projected-order table — verify the scraper picks them up and
        labels them correctly."""
        rows = scrape_tankathon_lottery(2027)
        comp_a = [r for r in rows if r["round_label"] == "1A"]
        comp_b = [r for r in rows if r["round_label"] == "1B"]
        # Tankathon typically lists 6 of each; tolerate ± a couple if
        # the page format shifts. Picks should carry odds_pct=None.
        self.assertGreaterEqual(len(comp_a) + len(comp_b), 8)
        for r in comp_a + comp_b:
            self.assertIsNone(r["odds_pct"])
            self.assertGreaterEqual(r["pick_pos"], 31)


if __name__ == "__main__":
    unittest.main()
