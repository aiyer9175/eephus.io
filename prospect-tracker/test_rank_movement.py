"""Deterministic unit tests for the de-noised board-RANK movement engine
(movement.compute_rank_movement) - the per-prospect overall-board climb/fall
twin of the farm engine.

Synthetic history only, so these never rot. They pin the behaviours the engine
guarantees: singletons can't move, a held rank is flat, day-to-day churn inside
the plateau band is flat, a genuine leap hits the right tier, and - the deferred
R4 fix - a slow monotonic slide that stays inside the plateau band of the fixed
anchor still reports its full accumulated magnitude instead of reading flat.
"""

import unittest

import movement


def r(snapshot_date, rank):
    """One board-rank history point for a single prospect."""
    return {"snapshot_date": snapshot_date, "rank": rank}


class RankMovementTests(unittest.TestCase):

    def test_singleton_is_insufficient(self):
        m = movement.compute_rank_movement([r("2026-01-01", 40)])
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "insufficient")
        self.assertIsNone(m["delta"])

    def test_held_rank_is_flat(self):
        m = movement.compute_rank_movement([
            r("2026-01-01", 40), r("2026-02-01", 40), r("2026-03-01", 40)])
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "held")
        self.assertEqual(m["delta"], 0)

    def test_churn_within_plateau_is_flat(self):
        # Neighbour re-grades jostle the number a few spots each way but there is
        # no net move: everything sits within _RANK_PLATEAU of the anchor.
        m = movement.compute_rank_movement([
            r("2026-01-01", 45), r("2026-02-01", 52),
            r("2026-03-01", 48), r("2026-04-01", 50)])
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "held")

    def test_small_step_below_deadband_is_flat(self):
        # A real step exists (outside the plateau band) but it is under the
        # 25-spot dead-band, so it reads flat.
        m = movement.compute_rank_movement([
            r("2026-01-01", 30), r("2026-02-01", 50)])
        self.assertEqual(m["basis"], "rank_step")
        self.assertEqual(m["delta"], -20)
        self.assertEqual(m["direction"], "flat")

    def test_marquee_leap_hits_strong(self):
        up = movement.compute_rank_movement([
            r("2026-01-01", 130), r("2026-02-01", 30)])
        self.assertEqual(up["direction"], "up_strong")
        self.assertEqual(up["delta"], 100)
        down = movement.compute_rank_movement([
            r("2026-01-01", 20), r("2026-02-01", 130)])
        self.assertEqual(down["direction"], "down_strong")
        self.assertEqual(down["delta"], -110)

    # --- R4: slow-monotonic-slide origin walk -----------------------------

    def test_slow_board_slide_reports_full_magnitude(self):
        # Rank drifts 10 -> 50 in 2-spot steps. The OLD engine treated the whole
        # 40..50 tail as the anchor's plateau, found the step at rank 38, and
        # reported delta -12 -> flat. The origin now walks the full slide.
        ranks = list(range(10, 51, 2))              # 10,12,...,50  (21 points)
        hist = [r(f"2026-01-{i + 1:02d}", rank) for i, rank in enumerate(ranks)]
        m = movement.compute_rank_movement(hist)
        self.assertEqual(m["direction"], "down")    # fell 40 spots (>= dead-band)
        self.assertEqual(m["delta"], -40)           # 10 -> 50
        self.assertEqual(m["from_rank"], 10)
        self.assertEqual(m["to_rank"], 50)
        self.assertEqual(m["from_date"], "2026-01-01")

    def test_slow_board_climb_reports_full_magnitude(self):
        ranks = list(range(50, 9, -2))              # 50,48,...,10
        hist = [r(f"2026-01-{i + 1:02d}", rank) for i, rank in enumerate(ranks)]
        m = movement.compute_rank_movement(hist)
        self.assertEqual(m["direction"], "up")
        self.assertEqual(m["delta"], 40)            # 50 -> 10
        self.assertEqual(m["from_rank"], 50)

    def test_sawtooth_does_not_amplify(self):
        # Wobble that repeatedly returns toward the anchor: the origin walk stops
        # at the first reversal, so no phantom slide is reported.
        m = movement.compute_rank_movement([
            r("2026-01-01", 40), r("2026-01-02", 55), r("2026-01-03", 42),
            r("2026-01-04", 53), r("2026-01-05", 45)])
        self.assertEqual(m["direction"], "flat")

    def test_held_level_then_jump_uses_durable_origin(self):
        # A board player held ~#130 (with a one-run #135 blip) then leapt to
        # #100. The origin must be the durable #130 level, not the #135 blip
        # beyond it, and the old #200 era must NOT be merged into the move.
        m = movement.compute_rank_movement([
            r("2026-01-01", 200), r("2026-01-02", 130), r("2026-01-03", 130),
            r("2026-01-04", 135), r("2026-01-05", 130), r("2026-01-06", 100)])
        self.assertEqual(m["from_rank"], 130)   # durable level, not 135 blip / 200
        self.assertEqual(m["to_rank"], 100)
        self.assertEqual(m["delta"], 30)        # 130 -> 100, a genuine 30-spot climb
        self.assertEqual(m["direction"], "up")

    def test_out_of_order_and_dupe_dates_tolerated(self):
        m = movement.compute_rank_movement([
            r("2026-02-01", 30), r("2026-01-01", 130), r("2026-02-01", 30)])
        self.assertEqual(m["delta"], 100)
        self.assertEqual(m["direction"], "up_strong")
        self.assertEqual(m["n_points"], 2)


if __name__ == "__main__":
    unittest.main()
