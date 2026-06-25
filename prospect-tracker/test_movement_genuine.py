"""Deterministic unit tests for the de-noised movement engine (movement.py).

Synthetic points only — no live data, so these never rot. They pin the
behaviours the engine exists to guarantee: same-source moves drive direction,
panel-composition shifts and lone outliers do NOT, performance is the backup,
and thin samples are gated off the board.
"""

import unittest
from unittest.mock import patch

import movement


def pt(snapshot_date, label, srcs, *, contributing=None, spread=None,
       shrink=1.0, dropped=()):
    """Build a serialized consensus point. `srcs` maps source -> fv_published
    (None for a rank-only source)."""
    per_source = {s: {"fv_published": fv, "dropped_off": s in dropped}
                  for s, fv in srcs.items()}
    return {
        "snapshot_date": snapshot_date,
        "consensus_fv_label": label,
        "per_source": per_source,
        "sources_contributing": (contributing if contributing is not None
                                 else sorted(srcs.keys())),
        "fv_spread": spread,
        "shrinkage_weight": shrink,
    }


def player(points, *, status="active", fv_total_instances=10, statline=None):
    return {"status": status, "points": points,
            "fv_total_instances": fv_total_instances, "statline": statline or {}}


_VALID_DIRECTIONS = {"up_strong", "up", "flat", "down", "down_strong", "debuted"}


class MovementGenuineTests(unittest.TestCase):

    def setUp(self):
        # Default: no on-field performance signal, so classification is driven
        # purely by the same-source consensus unless a test opts in.
        self._perf = patch.object(movement, "_perf_delta", return_value=(None, None))
        self._skills = patch.object(movement, "_skills_delta", return_value=(None, []))
        self._perf.start()
        self._skills.start()
        self.addCleanup(self._perf.stop)
        self.addCleanup(self._skills.stop)

    def test_a_stable_panel_is_flat(self):
        p = player([
            pt("2025-01-01", "55", {"fangraphs": 55, "espn": 55, "mlb_pipeline": 55}),
            pt("2025-06-01", "55", {"fangraphs": 55, "espn": 55, "mlb_pipeline": 55}),
            pt("2026-01-01", "55", {"fangraphs": 55, "espn": 55, "mlb_pipeline": 55}),
        ])
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "insufficient")
        self.assertIn(m["direction"], _VALID_DIRECTIONS)

    def test_b_two_sources_raise_is_up_and_names_both(self):
        p = player([
            pt("2025-06-01", "55", {"fangraphs": 60, "mlb_pipeline": 60, "espn": 60}),
            pt("2026-01-01", "58", {"fangraphs": 65, "mlb_pipeline": 65, "espn": 60}),
        ])
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "up")
        self.assertEqual(m["basis"], "same_source")
        self.assertEqual(m["n_sources_up"], 2)
        labels = " | ".join(d["label"] for d in m["drivers"])
        self.assertIn("FanGraphs", labels)
        self.assertIn("MLB Pipeline", labels)

    def test_b2_two_sources_big_jump_is_up_strong(self):
        p = player([
            pt("2025-06-01", "50", {"fangraphs": 55, "mlb_pipeline": 55, "espn": 60}),
            pt("2026-01-01", "58", {"fangraphs": 65, "mlb_pipeline": 65, "espn": 60}),
        ])
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "up_strong")
        self.assertEqual(m["basis"], "same_source")

    def test_c_composition_only_change_is_panel_update(self):
        p = player([
            pt("2025-06-01", "55", {"fangraphs": 55}, contributing=["fangraphs"]),
            pt("2026-01-01", "57", {"fangraphs": 55, "espn": 60},
               contributing=["fangraphs", "espn"]),
        ])
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "panel_update")

    def test_d_single_outlier_without_perf_is_flat(self):
        p = player([
            pt("2025-06-01", "55", {"fangraphs": 60, "espn": 60, "mlb_pipeline": 60}),
            pt("2026-01-01", "57", {"fangraphs": 70, "espn": 60, "mlb_pipeline": 60}),
        ])
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["n_sources_up"], 1)

    def test_e_single_outlier_with_perf_is_up(self):
        p = player([
            pt("2025-06-01", "55", {"fangraphs": 60, "espn": 60, "mlb_pipeline": 60}),
            pt("2026-01-01", "57", {"fangraphs": 70, "espn": 60, "mlb_pipeline": 60}),
        ], statline={"is_pitcher": False})
        with patch.object(movement, "_perf_delta", return_value=(0.200, "OPS +0.200 vs prior")):
            m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "up")
        self.assertEqual(m["basis"], "same_source")

    def test_f_no_overlapping_sources_is_insufficient(self):
        # Disjoint panels with no consensus move: nothing to measure, no panel
        # story either -> insufficient, never a fabricated delta.
        p = player([
            pt("2025-06-01", "55", {"fangraphs": 55}),
            pt("2026-01-01", "55", {"espn": 55}),
        ], fv_total_instances=2)
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["basis"], "insufficient")
        self.assertEqual(m["direction"], "flat")
        self.assertIsNone(m["delta"])

    def test_f2_panel_swap_with_label_move_is_panel_update(self):
        # Disjoint panels AND the consensus label moved -> the move is purely
        # composition-driven. Classified panel_update, still flat.
        p = player([
            pt("2025-06-01", "55", {"fangraphs": 55}, contributing=["fangraphs"]),
            pt("2026-01-01", "60", {"espn": 60}, contributing=["espn"]),
        ], fv_total_instances=2)
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["basis"], "panel_update")

    def test_g_singleton_is_gated_flat_low(self):
        p = player([
            pt("2025-06-01", "55", {"fangraphs": 60}),
            pt("2026-01-01", "58", {"fangraphs": 65}),
        ], fv_total_instances=1)
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "flat")
        self.assertEqual(m["confidence"], "low")

    def test_h_rank_only_source_excluded(self):
        anchor = pt("2026-01-01", "55", {"fangraphs": 65, "baseballamerica": None})
        prior = pt("2025-06-01", "53", {"fangraphs": 60, "baseballamerica": None})
        res = movement.same_source_change_anchor([prior, anchor])
        self.assertIn("fangraphs", res["common"])
        self.assertNotIn("baseballamerica", res["common"])

    def test_i_debuted_short_circuits(self):
        p = player([
            pt("2025-06-01", "55", {"fangraphs": 60, "espn": 60}),
            pt("2026-01-01", "60", {"fangraphs": 65, "espn": 65}),
        ], status="debuted")
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "debuted")
        self.assertEqual(m["basis"], "debuted")

    def test_j_two_sources_cut_is_down(self):
        p = player([
            pt("2025-06-01", "60", {"fangraphs": 65, "mlb_pipeline": 65, "espn": 55}),
            pt("2026-01-01", "57", {"fangraphs": 60, "mlb_pipeline": 60, "espn": 55}),
        ])
        m = movement.compute_genuine_movement(p)
        self.assertEqual(m["direction"], "down")
        self.assertEqual(m["n_sources_down"], 2)

    def test_output_shape_is_superset(self):
        p = player([
            pt("2025-06-01", "55", {"fangraphs": 60, "espn": 60}),
            pt("2026-01-01", "58", {"fangraphs": 65, "espn": 65}),
        ])
        m = movement.compute_genuine_movement(p)
        for k in ("direction", "delta", "basis", "strength", "confidence",
                  "from_label", "to_label", "from_date", "to_date",
                  "perf_delta", "skills_delta", "n_sources_up", "n_sources_down",
                  "drivers"):
            self.assertIn(k, m)
        self.assertIn(m["direction"], _VALID_DIRECTIONS)


if __name__ == "__main__":
    unittest.main()
