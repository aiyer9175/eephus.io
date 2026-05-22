"""Tests for the draft polish: sequential consensus_pick + integer FV
+ lottery odds plumbing."""

from __future__ import annotations

import unittest

from draft_export import _projected_round, build_draft_export


class ProjectedRound(unittest.TestCase):
    def test_round_buckets(self):
        self.assertEqual(_projected_round(1), 1)
        self.assertEqual(_projected_round(30), 1)
        self.assertEqual(_projected_round(31), 2)
        self.assertEqual(_projected_round(60), 2)
        self.assertEqual(_projected_round(150), 5)

    def test_none_safe(self):
        self.assertIsNone(_projected_round(None))
        self.assertIsNone(_projected_round(0))


class SequentialRanking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.export = build_draft_export()

    def test_picks_are_sequential_no_dupes(self):
        for klass in self.export["classes"]:
            ranked = [p for p in klass["prospects"]
                      if p.get("consensus_pick") is not None]
            if not ranked:
                continue
            picks = sorted(p["consensus_pick"] for p in ranked)
            self.assertEqual(picks, list(range(1, len(ranked) + 1)),
                             f"class {klass['year']} has non-sequential picks")
            self.assertEqual(len(picks), len(set(picks)),
                             f"class {klass['year']} has duplicate picks")

    def test_picks_track_consensus_rank_order(self):
        """Lower averaged rank → lower pick number."""
        for klass in self.export["classes"]:
            ranked = sorted(
                (p for p in klass["prospects"] if p.get("consensus_pick") is not None),
                key=lambda p: p["consensus_pick"]
            )
            for prev, cur in zip(ranked, ranked[1:]):
                self.assertLessEqual(
                    prev["consensus_rank"], cur["consensus_rank"] + 1e-6,
                    f"pick {prev['consensus_pick']} has higher raw rank "
                    f"than pick {cur['consensus_pick']} in {klass['year']}"
                )


class IntegerFV(unittest.TestCase):
    def test_consensus_fv_is_integer(self):
        export = build_draft_export()
        for klass in export["classes"]:
            for p in klass["prospects"]:
                fv = p.get("consensus_fv")
                if fv is None:
                    continue
                self.assertIsInstance(fv, int, f"{p['player_name']} FV is not int")

    def test_consensus_fv_raw_preserved(self):
        """The raw average stays alongside for tooltips."""
        export = build_draft_export()
        for klass in export["classes"]:
            for p in klass["prospects"]:
                if p.get("consensus_fv") is None:
                    continue
                self.assertIn("consensus_fv_raw", p,
                              f"{p['player_name']} missing consensus_fv_raw")


class LotteryPlumbing(unittest.TestCase):
    def test_lottery_odds_field_present(self):
        export = build_draft_export()
        for klass in export["classes"]:
            self.assertIn("lottery_odds", klass)
            self.assertIsInstance(klass["lottery_odds"], list)

    def test_lottery_odds_sorted_descending(self):
        export = build_draft_export()
        for klass in export["classes"]:
            odds = klass["lottery_odds"]
            if len(odds) < 2:
                continue
            vals = [o["odds_pct"] for o in odds]
            self.assertEqual(vals, sorted(vals, reverse=True),
                             f"lottery odds for {klass['year']} not sorted")


if __name__ == "__main__":
    unittest.main()
