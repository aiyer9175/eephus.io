"""Deterministic unit tests for the de-noised farm-system rank movement engine
(movement.compute_farm_movement).

Synthetic history only — no live data, so these never rot. They pin the
behaviours the engine exists to guarantee: singletons can't move, a held rank
is flat, a multi-spot shift registers with the right direction/delta and brackets
the transition with from/to dates, a single-spot wobble is rejected by the
dead-band, and big leaps hit the strong tier.
"""

import unittest

import movement


def h(snapshot_date, rank, score=None):
    """One farm_rank_history row for a single org."""
    return {"org": "X", "snapshot_date": snapshot_date,
            "farm_rank": rank, "farm_score": score}


class FarmMovementTests(unittest.TestCase):

    def test_empty_is_insufficient(self):
        m = movement.compute_farm_movement([])
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "insufficient")
        self.assertIsNone(m["delta"])

    def test_singleton_is_insufficient(self):
        m = movement.compute_farm_movement([h("2026-01-01", 10)])
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "insufficient")

    def test_held_rank_is_flat(self):
        m = movement.compute_farm_movement([
            h("2026-01-01", 12), h("2026-02-01", 12), h("2026-03-01", 12)])
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "held")
        self.assertEqual(m["delta"], 0)

    def test_climb_registers_up(self):
        m = movement.compute_farm_movement([
            h("2026-01-01", 18, 100.0), h("2026-02-01", 15, 110.0)])
        self.assertEqual(m["direction"], "up")
        self.assertEqual(m["delta"], 3)            # 18 -> 15 = climbed 3 spots
        self.assertEqual(m["basis"], "rank_step")
        self.assertEqual(m["from_rank"], 18)
        self.assertEqual(m["to_rank"], 15)
        self.assertEqual(m["from_date"], "2026-01-01")
        self.assertEqual(m["to_date"], "2026-02-01")
        self.assertEqual(m["score_delta"], 10.0)

    def test_drop_registers_down(self):
        m = movement.compute_farm_movement([
            h("2026-01-01", 8), h("2026-02-01", 12)])
        self.assertEqual(m["direction"], "down")
        self.assertEqual(m["delta"], -4)

    def test_single_spot_wobble_is_flat(self):
        # A step exists, but a one-spot move is relative churn — the dead-band
        # reports it flat.
        m = movement.compute_farm_movement([
            h("2026-01-01", 10), h("2026-02-01", 9)])
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "rank_step")
        self.assertEqual(m["delta"], 1)

    def test_strong_leaps(self):
        up = movement.compute_farm_movement([
            h("2026-01-01", 20), h("2026-02-01", 12)])
        self.assertEqual(up["direction"], "up_strong")
        self.assertEqual(up["delta"], 8)
        down = movement.compute_farm_movement([
            h("2026-01-01", 5), h("2026-02-01", 14)])
        self.assertEqual(down["direction"], "down_strong")
        self.assertEqual(down["delta"], -9)

    def test_plateau_then_step_brackets_transition(self):
        # 18 -> 15, then holds at 15 for two more months. The reported move is
        # the 18->15 step: from_date = the pre-step point, to_date = the first
        # month at the current level.
        m = movement.compute_farm_movement([
            h("2025-12-01", 18), h("2026-01-01", 15),
            h("2026-02-01", 15), h("2026-03-01", 15)])
        self.assertEqual(m["direction"], "up")
        self.assertEqual(m["delta"], 3)
        self.assertEqual(m["from_rank"], 18)
        self.assertEqual(m["to_rank"], 15)
        self.assertEqual(m["from_date"], "2025-12-01")
        self.assertEqual(m["to_date"], "2026-01-01")
        self.assertEqual(m["confidence"], "high")   # >=3 points backs the call

    def test_out_of_order_and_dupe_dates_tolerated(self):
        m = movement.compute_farm_movement([
            h("2026-02-01", 15),            # anchor, out of order
            h("2026-01-01", 18),
            h("2026-02-01", 15)])           # duplicate date (same-day re-run)
        self.assertEqual(m["delta"], 3)
        self.assertEqual(m["direction"], "up")
        self.assertEqual(m["n_points"], 2)          # dedup collapsed the dupe

    def test_two_point_call_is_medium_confidence(self):
        m = movement.compute_farm_movement([
            h("2026-01-01", 18), h("2026-02-01", 13)])
        self.assertEqual(m["confidence"], "medium")


if __name__ == "__main__":
    unittest.main()
