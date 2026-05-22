"""Assertions on the three-bucket spotlights export shape."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

TS_PATH = Path(__file__).parent / "data" / "timeseries.json"


class ThreeBuckets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TS_PATH.exists():
            raise unittest.SkipTest("data/timeseries.json missing")
        cls.payload = json.loads(TS_PATH.read_text(encoding="utf-8"))
        cls.sp = cls.payload.get("spotlights") or {}

    def test_three_named_buckets_present(self):
        for k in ("risers", "rebounders", "fallers"):
            self.assertIn(k, self.sp, f"spotlights missing bucket {k!r}")
            self.assertIsInstance(self.sp[k], list)

    def test_legacy_hot_alias_present(self):
        """Back-compat: `hot` should still appear (aliased to `risers`)
        so a stale frontend or cached payload still renders."""
        self.assertIn("hot", self.sp)
        self.assertEqual(len(self.sp["hot"]), len(self.sp["risers"]))

    def test_no_player_in_two_buckets(self):
        """Same player should not appear in both Risers and Fallers (a
        Riser-and-Faller would be a logic bug). Rebounders + Risers
        overlap is intentional (the classifier picks one but the test
        is conservative and only enforces Risers ⊥ Fallers)."""
        riser_keys = {e["player_key"] for e in self.sp.get("risers") or []}
        faller_keys = {e["player_key"] for e in self.sp.get("fallers") or []}
        overlap = riser_keys & faller_keys
        self.assertFalse(overlap,
                         f"players in both Risers AND Fallers: {sorted(overlap)[:5]}")

    def test_risers_sorted_desc(self):
        scores = [e["score"] for e in self.sp.get("risers") or []]
        self.assertEqual(scores, sorted(scores, reverse=True),
                         "Risers not sorted by score DESC")

    def test_fallers_sorted_asc(self):
        scores = [e["score"] for e in self.sp.get("fallers") or []]
        self.assertEqual(scores, sorted(scores),
                         "Fallers not sorted by score ASC (most-negative first)")

    def test_each_bucket_has_drivers(self):
        for k in ("risers", "rebounders", "fallers"):
            for e in self.sp.get(k) or []:
                self.assertTrue(e.get("drivers"),
                    f"{k}: {e.get('player_name')} has empty drivers list")


class StockSignalShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TS_PATH.exists():
            raise unittest.SkipTest("data/timeseries.json missing")
        cls.payload = json.loads(TS_PATH.read_text(encoding="utf-8"))

    def test_stock_carries_new_fields(self):
        required = {"direction", "delta", "from_label", "to_label",
                    "from_date", "to_date", "perf_delta", "skills_delta",
                    "drivers"}
        for p in (self.payload.get("players") or [])[:50]:
            s = p.get("stock") or {}
            missing = required - set(s.keys())
            self.assertFalse(missing,
                f"{p['player_name']} stock missing fields: {missing}")


if __name__ == "__main__":
    unittest.main()
