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

    # --- R4: slow-monotonic-slide origin walk -----------------------------

    def test_slow_monotonic_climb_reports_full_magnitude(self):
        # Rank drifts 30 -> 2 in 2-spot steps over 15 runs. Each step is a
        # genuine one-off move (farm plateau is exact-match), so the OLD engine
        # broke at the first prior point and reported only the last 2-spot step,
        # calling a 28-spot climb barely "up". The origin now walks the whole
        # monotonic slide and reports its full magnitude.
        ranks = list(range(30, 1, -2))              # 30,28,...,2  (15 points)
        hist = [h(f"2026-01-{i + 1:02d}", r) for i, r in enumerate(ranks)]
        m = movement.compute_farm_movement(hist)
        self.assertEqual(m["direction"], "up_strong")
        self.assertEqual(m["delta"], 28)            # 30 -> 2
        self.assertEqual(m["from_rank"], 30)
        self.assertEqual(m["to_rank"], 2)
        self.assertEqual(m["from_date"], "2026-01-01")

    def test_slow_monotonic_drop_reports_full_magnitude(self):
        ranks = list(range(2, 31, 2))               # 2,4,...,30
        hist = [h(f"2026-01-{i + 1:02d}", r) for i, r in enumerate(ranks)]
        m = movement.compute_farm_movement(hist)
        self.assertEqual(m["direction"], "down_strong")
        self.assertEqual(m["delta"], -28)           # 2 -> 30
        self.assertEqual(m["from_rank"], 2)

    def test_sawtooth_wobble_stays_flat(self):
        # Oscillation around #10 with no net move must NOT be amplified into a
        # slide: the origin walk stops at the first reversal toward the anchor.
        m = movement.compute_farm_movement([
            h("2026-01-01", 10), h("2026-01-02", 12), h("2026-01-03", 9),
            h("2026-01-04", 11), h("2026-01-05", 10)])
        self.assertEqual(m["direction"], "flat")

    def test_monotonic_run_stops_at_reversal(self):
        # 20 -> 16, reverses to 18, then settles at 15. The origin walks the
        # 18 -> 15 leg but stops at the 16 -> 18 reversal, so the move reported
        # is 18 -> 15 (not the whole noisy 20 -> 15 history).
        m = movement.compute_farm_movement([
            h("2026-01-01", 20), h("2026-01-02", 16),
            h("2026-01-03", 18), h("2026-01-04", 15)])
        self.assertEqual(m["from_rank"], 18)
        self.assertEqual(m["to_rank"], 15)
        self.assertEqual(m["delta"], 3)
        self.assertEqual(m["direction"], "up")

    def test_held_level_then_jump_uses_durable_origin(self):
        # Real-data regression (MIN farm): the org held ~#14 for most of the
        # window - with a one-day #15 blip - then jumped to #6 on the last run.
        # The origin walk must report the DURABLE #14 level, not the stray #15
        # blip beyond it. (The unbounded walk adopted #15 -> delta 9; the origin
        # is #14 -> delta 8.)
        m = movement.compute_farm_movement([
            h("2026-06-19", 14), h("2026-06-20", 14), h("2026-06-21", 13),
            h("2026-06-22", 10), h("2026-06-23", 14), h("2026-06-24", 14),
            h("2026-06-25", 14), h("2026-06-26", 15), h("2026-06-29", 14),
            h("2026-06-30", 6)])
        self.assertEqual(m["from_rank"], 14)   # the durable level, not the 15 blip
        self.assertEqual(m["to_rank"], 6)
        self.assertEqual(m["delta"], 8)
        self.assertEqual(m["direction"], "up_strong")
        self.assertEqual(m["from_date"], "2026-06-29")  # brackets the real jump


if __name__ == "__main__":
    unittest.main()
