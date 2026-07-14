# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Smoke tests for the Spotrac draft-order and Tankathon lottery scrapers.

Both use cached HTML from .cache/ so the tests run offline. We only
check shape + sane counts — the upstream pages are authoritative."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import storage
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
        # Summing ~18 percentages each rounded to 2 decimals can drift a few
        # hundredths past 100 (the live page sums to ~100.02), so allow slack.
        self.assertLessEqual(total, 100.5)

    def test_comp_picks_parsed(self):
        """Round 1A + Round 1B comp picks live outside the main
        projected-order table — verify the scraper picks them up and
        labels them correctly WHEN the page lists them. The count is
        seasonal, not a scraper property: Tankathon wipes the comp-pick
        sections right after each draft (observed 2026-07-14, the day
        after the 2026 draft) and repopulates them during the season, so
        a hard count here is a time bomb that reddens the deploy gate."""
        rows = scrape_tankathon_lottery(2027)
        comp = [r for r in rows if r["round_label"] in ("1A", "1B")]
        if not comp:
            self.skipTest("cached Tankathon page lists no comp picks "
                          "(post-draft reset; they reappear in-season)")
        for r in comp:
            self.assertIsNone(r["odds_pct"])
            self.assertGreaterEqual(r["pick_pos"], 31)


# ---------------------------------------------------------------------------
# Storage load path: latest_only must collapse a multi-snapshot lottery to the
# single newest scrape, even when teams move between projected slots. (pytest
# style so it gets an isolated per-test DB, mirroring test_storage_export.py.)
# ---------------------------------------------------------------------------

def _seed_two_snapshots(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    storage.init_db()
    # Old scrape: COL at pick 1. New scrape: COL slid to pick 2, BOS now at #1.
    old = "2026-06-01"
    new = "2026-06-08"
    rows = [
        # old snapshot (3 picks)
        dict(draft_year=2027, team="COL", pick_pos=1, odds_pct=17.95, round_label="1", snapshot_date=old, source="tankathon"),
        dict(draft_year=2027, team="BOS", pick_pos=2, odds_pct=14.36, round_label="1", snapshot_date=old, source="tankathon"),
        dict(draft_year=2027, team="LAA", pick_pos=3, odds_pct=10.88, round_label="1", snapshot_date=old, source="tankathon"),
        # new snapshot (3 picks) - team at pick_pos 1 CHANGES (COL -> BOS)
        dict(draft_year=2027, team="BOS", pick_pos=1, odds_pct=17.95, round_label="1", snapshot_date=new, source="tankathon"),
        dict(draft_year=2027, team="COL", pick_pos=2, odds_pct=14.36, round_label="1", snapshot_date=new, source="tankathon"),
        dict(draft_year=2027, team="LAA", pick_pos=3, odds_pct=10.88, round_label="1", snapshot_date=new, source="tankathon"),
    ]
    storage.upsert_draft_lottery_odds(rows)
    return new


def test_latest_only_collapses_to_newest_snapshot(tmp_path, monkeypatch):
    new = _seed_two_snapshots(monkeypatch, tmp_path)
    got = storage.load_draft_lottery_odds(2027, latest_only=True)
    # Exactly one row per (pick_pos, round_label), all from the newest scrape.
    assert len(got) == 3, f"expected 3 latest rows, got {len(got)}: {got}"
    assert all(r["snapshot_date"] == new for r in got)
    seen = {(r["pick_pos"], r["round_label"]) for r in got}
    assert len(seen) == 3
    # The team at pick 1 must be the NEW one (BOS), not the stale COL.
    p1 = next(r for r in got if r["pick_pos"] == 1)
    assert p1["team"] == "BOS"


def test_latest_only_false_returns_all_snapshots(tmp_path, monkeypatch):
    _seed_two_snapshots(monkeypatch, tmp_path)
    got = storage.load_draft_lottery_odds(2027, latest_only=False)
    assert len(got) == 6  # both snapshots, full history retained


if __name__ == "__main__":
    unittest.main()
