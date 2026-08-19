# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pins for the ETA backtest gate outcomes.

2026-08-19 empirical-table gate (docs/eta-2026-08-19/ETA_EMPIRICAL_TABLE_GATE.md):
NO SHIP. C1/C2/C3/C5 passed but C4 (overdue guardrail, the survivor-bias
check) failed +453 vs the +110 limit. These pins hold three facts:

  1. the loss block is on the record in data/eta_eval.json,
  2. eta.py still serves v39 (KM bases; the empirical table did NOT ship),
  3. the frozen comparators (v38 hand-set bases) and the live-caller layers
     (LEVEL_BIAS_ADJ, hazard-lite hook) are unchanged.

NOTE: eta_backtest.run() rebuilds data/eta_eval.json from scratch on the
monthly rerun and does not yet carry empirical_table_gate_2026_08_19
forward (ship_decision is hardcoded in its output dict; the gate block is
not). Until that carry-forward lands, a monthly regen will turn
test_gate_block_exists red; that is the signal to add the carry-forward,
not to delete the pin.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import eta
from eta_backtest import V38_BASE_YEARS

DATA = Path(__file__).parent / "data"
GATE_DOC = (Path(__file__).parent / "docs" / "eta-2026-08-19"
            / "ETA_EMPIRICAL_TABLE_GATE.md")

# v39 KM-recalibrated bases, shipped 2026-06-11, HELD 2026-08-04, and held
# again by the 2026-08-19 empirical-table gate. This dict IS the shape pin:
# any edit to eta.BASE_YEARS must come through a passed gate.
V39_BASE_YEARS = {
    "MLB": 0.0,
    "AAA": 0.75,
    "AA":  1.5,
    "A+":  3.0,
    "A":   3.75,
    "CPX": 4.25,
    "DSL": 7.5,
}


class EmpiricalTableGate20260819(unittest.TestCase):
    """The 2026-08-19 gate ran, lost on C4, and the loss is recorded."""

    @classmethod
    def setUpClass(cls):
        cls.art = json.loads((DATA / "eta_eval.json").read_text(encoding="utf-8"))

    def test_gate_block_exists(self):
        self.assertIn("empirical_table_gate_2026_08_19", self.art)

    def test_gate_decision_is_no_ship(self):
        block = self.art["empirical_table_gate_2026_08_19"]
        self.assertEqual(block["decision"], "NO_SHIP")
        self.assertEqual(block["clauses"]["C4"], "FAIL")
        for c in ("C1", "C2", "C3", "C5"):
            self.assertEqual(block["clauses"][c], "PASS")

    def test_gate_overdue_guardrail_numbers(self):
        og = self.art["empirical_table_gate_2026_08_19"]["overdue_guardrail"]
        self.assertEqual(og["limit"], 110)
        self.assertGreater(og["delta"], og["limit"])
        self.assertEqual(og["delta"],
                         og["shipped_system"] - og["champion"])

    def test_v39_ship_decision_untouched(self):
        # NO SHIP means the standing ship_decision stays the v39 record.
        self.assertEqual(self.art["ship_decision"]["date"], "2026-06-11")

    def test_gate_doc_records_the_loss(self):
        text = GATE_DOC.read_text(encoding="utf-8")
        self.assertIn("NO SHIP", text)
        self.assertIn("C4", text)


class V39StillServes(unittest.TestCase):
    """eta.py is untouched by the 2026-08-19 gate: v39 serves."""

    def test_base_years_pinned_to_v39(self):
        self.assertEqual(eta.BASE_YEARS, V39_BASE_YEARS)

    def test_v38_frozen_comparator_unchanged(self):
        self.assertEqual(V38_BASE_YEARS,
                         {"MLB": 0.0, "AAA": 0.5, "AA": 2.0, "A+": 3.5,
                          "A": 5.0, "CPX": 6.5, "DSL": 7.5})

    def test_level_bias_adj_unchanged(self):
        self.assertEqual(eta.LEVEL_BIAS_ADJ,
                         {"AAA": 0.5, "AA": 0.5, "A+": 0.5, "A": 0.5,
                          "CPX": 0.5, "DSL": 0.5})

    def test_hazard_lite_table_unchanged(self):
        self.assertEqual(eta.FORTYMAN_ADJ,
                         {"AAA": 0.0, "AA": 0.97, "A+": 1.0, "A": 1.0})

    def test_hazard_lite_default_off(self):
        # fortyman_adj=None (the default) must apply nothing.
        r = eta.estimate_eta(current_level="AA", age=22.0, is_pitcher=False,
                             fv=50.0, stats=None)
        self.assertEqual(r.fortyman_adj_applied, 0.0)

    def test_age_adj_continuous_still_off(self):
        self.assertFalse(eta.AGE_ADJ_CONTINUOUS)


if __name__ == "__main__":
    unittest.main()
