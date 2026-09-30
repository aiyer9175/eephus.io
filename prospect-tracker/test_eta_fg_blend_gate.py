# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the ETA FanGraphs-blend gate lab (tools/eta_fg_blend_gate.py).

The gate (docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md) was committed alone before any
read of its 2024 frame. These tests hold the lab to the frozen text without
reading any frame: the reserved 2020/2021 lists never pass the guard, the look
cannot run before 2026-09-28 or twice, the constants match the doc, Holm and the
decision rule behave as written, and eta_eval.json carries the blocks forward.
"""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

import eta_backtest
from tools import eta_fg_blend_gate as G

HERE = Path(__file__).resolve().parent


class Guards(unittest.TestCase):
    def test_reserved_lists_never_pass(self):
        for v in (2020, 2021):
            for kw in ({}, {"allow_dev": True}, {"allow_shadow": True}):
                with self.assertRaises(AssertionError):
                    G.assert_frame_vintages((v,), **kw)
        with self.assertRaises(AssertionError):
            G.assert_frame_vintages((2019, 2020), allow_dev=True)

    def test_modes_accept_only_their_vintages(self):
        G.assert_frame_vintages((2024,))
        G.assert_frame_vintages(G.DEV_V, allow_dev=True)
        G.assert_frame_vintages((2026,), allow_shadow=True)
        for bad in ((2023,), (2025,), (2026,)):
            with self.assertRaises(AssertionError):
                G.assert_frame_vintages(bad)
        with self.assertRaises(AssertionError):
            G.assert_frame_vintages(())

    def test_dev_vintages_exclude_the_frame_and_the_reserved_lists(self):
        self.assertNotIn(G.FRAME_V, G.DEV_V)
        self.assertFalse(set(G.DEV_V) & G.RESERVED_LV)

    def test_look_date_and_once(self):
        ok, why = G.look_allowed(date(2026, 9, 27), {})
        self.assertFalse(ok)
        self.assertIn("2026-09-28", why)
        self.assertTrue(G.look_allowed(date(2026, 9, 28), {})[0])
        self.assertFalse(G.look_allowed(date(2026, 10, 1), {G.BLOCK: {"look": "2026-09-28"}})[0])


class FrozenConstants(unittest.TestCase):
    def test_constants_match_the_gate_doc(self):
        self.assertEqual(G.LOOK_NOT_BEFORE, date(2026, 9, 28))
        self.assertEqual(G.FRAME_V, 2024)
        self.assertEqual(G.OUTCOME_CUTOFF, "2026-09-27")
        self.assertEqual(G.LAST_SEASON, 2026)
        self.assertEqual(G.ACTIVE_FROM, 2025)
        self.assertEqual(G.OVERDUE_LIMIT, 110)
        self.assertEqual((G.SEED, G.B), (20260928, 2000))
        self.assertEqual(G.ORG_EXCLUDED_SEASONS, frozenset({2020, 2021}))
        doc = (HERE / G.GATE_DOC).read_text(encoding="utf-8")
        for s in ("seed 20260928", "B = 2000", "2026-09-27", "+110", "2026-09-28"):
            self.assertIn(s, doc)

    def test_eta_eval_carries_the_new_blocks_forward(self):
        for k in (G.BLOCK, G.ORG_BLOCK, "empirical_table_gate_2026_08_19"):
            self.assertTrue(k.startswith(eta_backtest.GATE_BLOCK_PREFIXES), k)


class Scoring(unittest.TestCase):
    def test_holm_step_down(self):
        self.assertEqual(G.holm({"A": 0.01, "B": 0.04}), {"A": True, "B": True})
        self.assertEqual(G.holm({"A": 0.03, "B": 0.04}), {"A": False, "B": False})
        self.assertEqual(G.holm({"A": 0.001, "B": 0.06}), {"A": True, "B": False})

    def test_decision_rule(self):
        passed = {k: True for k in ("C1", "C2", "C3", "C4", "C5")}
        failed = dict(passed, C4=False)
        d = G.decide({"A": passed, "B": passed}, {"pass": False})
        self.assertEqual(d["recommended_arm"], "A")
        d = G.decide({"A": passed, "B": passed}, {"pass": True})
        self.assertEqual(d["recommended_arm"], "B")
        d = G.decide({"A": failed, "B": passed}, {"pass": False})
        self.assertEqual(d["recommended_arm"], "B")
        d = G.decide({"A": failed, "B": failed}, {"pass": True})
        self.assertIsNone(d["recommended_arm"])
        self.assertEqual(d["verdict"], "NO SHIP")

    def test_paired_boot_sign_convention(self):
        rows = [{"player_key": f"p{i}", "actual": 2026, "cmp": 2028, "arm": 2026 + (i % 2)}
                for i in range(40)]
        bt = G.paired_boot(rows, lambda r: r["cmp"], lambda r: r["arm"], b=200)
        self.assertGreater(bt["dMAE"], 0)          # the arm is closer: positive
        self.assertGreater(bt["dW1"], 0)
        self.assertEqual(bt["n"], 40)

    def test_c5_leak_rule(self):
        base = {"fg": 2026, "fg_date": "2024-02-01"}
        self.assertTrue(G.c5_clean(dict(base, outcome="censored_active")))
        self.assertTrue(G.c5_clean(dict(base, outcome="debuted", debut_date="2024-06-01", actual=2024)))
        self.assertFalse(G.c5_clean(dict(base, outcome="debuted", debut_date="2024-01-20", actual=2024)))
        self.assertTrue(G.c5_clean(dict(base, outcome="debuted", debut_date=None, actual=2025)))
        self.assertFalse(G.c5_clean(dict(base, outcome="debuted", debut_date=None, actual=2024)))
        self.assertFalse(G.c5_clean({"fg": None, "outcome": "debuted"}))

    def test_by_level_table_takes_a_row_with_no_level(self):
        # The first look (2026-09-30) crashed here: a C5-clean debuted row with level None
        # could not be sorted against the named levels. None now sorts last.
        rows = []
        for i, lv in enumerate(("AA", "A+", "AAA", None) * 3):
            rows.append({"player_key": f"p{i}", "vintage": 2024, "level": lv, "on40": i % 2,
                         "ch40": 2027, "fg": 2025, "fg_date": "2024-02-01",
                         "outcome": "debuted", "debut_date": "2025-06-01", "actual": 2025})
        rows.append({"player_key": "c0", "vintage": 2024, "level": None, "on40": 0,
                     "ch40": 2028, "fg": None, "fg_date": None, "outcome": "censored_active",
                     "actual": None})
        out = G.run_blend_gate(rows, lambda s: None)
        self.assertEqual(list(out["by_level"]), ["A+", "AA", "AAA", None])
        self.assertEqual(out["by_level"][None]["CH40"]["n"], 3)
        self.assertIn("verdict", out["decision"])

    def test_arm_rows_without_a_clean_fg_year_keep_the_champion(self):
        r = {"ch40": 2028, "fg": 2025, "vintage": 2024, "on40": 1, "c5_ok": False}
        self.assertEqual(G.arm_year(r, "A"), 2028)
        self.assertEqual(G.arm_year(r, "B"), 2028)
        r["c5_ok"] = True
        self.assertEqual(G.arm_year(r, "A"), 2027)   # 2026.5 rounds up
        self.assertEqual(G.arm_year(r, "B"), 2026)


if __name__ == "__main__":
    unittest.main()
