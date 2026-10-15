# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The runs-per-win gate registration pins (docs/ewar/RPW_GATE.md, task EWAR_RPW_FIT).

The registration is committed ALONE, before any number of its estimand exists, so
that nothing is tuned after the first build. Every clause is pinned by the sentence
that makes it bind, not by its heading. Prose assertions run against a
whitespace-flattened copy of the document, so re-wrapping a paragraph is not a
test failure. A result pin never lives here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ewar" / "RPW_GATE.md"


def _flat() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


def test_document_names_itself_and_this_test():
    text = _flat()
    assert text.startswith("# Runs per win fitted from team outcomes (rpw_fit_v1)")
    assert "Task EWAR_RPW_FIT (owner decision EW3-24, 2026-10-15" in text
    assert "committed ALONE, before any number of its estimand is computed" in text
    assert "test_rpw_gate_registration.py" in text


def test_incumbent_and_scope():
    text = _flat()
    assert "9 x (R / IP) x 1.5 + 3" in text
    assert "It is the INCUMBENT." in text
    assert "Only eWAR v3 can change." in text
    assert "Nothing served moves." in text
    assert "`measurement_only`, until a candidate is admitted" in text


def test_frame_and_2020():
    text = _flat()
    assert ("Seasons 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026: ten seasons, "
            "30 clubs each, 300 team-seasons.") in text
    assert "2020 is excluded from the primary frame" in text
    assert "it decides nothing" in text


def test_five_candidates_and_references():
    text = _flat()
    for head in ("**(a) The FanGraphs closed form, the incumbent.**",
                 "**(b) Pythagenpat with a fitted exponent.**",
                 "**(c) The linear slope of wins on run differential.**",
                 "**(d) A run-environment model.**",
                 "**(e) Baseball-Reference's recovered values.**",
                 "**Reference rows (deciding nothing).**"):
        assert head in text
    assert "a grid over 0.1000 to 0.5000 in steps of 0.0005 (a tie takes the smaller z)" in text
    assert "RPW_i = 1 / (b0 + b1 (L_s - 9) + b2 (T_i - L_s) + b3 (PF_i - 1))" in text
    assert "is VOID: it is reported and cannot pass" in text


def test_estimand_bootstrap_and_pass_rule():
    text = _flat()
    assert "**Leave one season out.**" in text
    assert "MAE (the mean absolute error, deciding) and RMSE (reported), in wins" in text
    assert "dMAE_c = MAE(a) - MAE(c)" in text
    assert ".integers(0, 300, size=(2000, 300))`, drawn once, B = 2000, seed 20261025" in text
    assert "the fits are not redone inside the bootstrap" in text
    assert "**PRIMARY PASS** when lo95 of dMAE_c is above 0." in text
    assert "The candidate with the largest point dMAE is the one carried forward" in text


def test_team_guard_is_deferred_to_its_own_record():
    text = _flat()
    assert "NON-INFERIOR on the team guard of `EBR_GATE.md` 11.2.4" in text
    assert "This task does not compute it." in text
    assert "PRIMARY PASS, GUARD PENDING" in text
    assert "INCUMBENT HOLDS" in text


def test_pitcher_leg():
    text = _flat()
    assert "dRPW_p = (((18 - ipg_p) * lg_ra9_s + 9 * RA_p / G_p) / 18 + 2) * 1.5" in text
    assert "It equals candidate (a) identically (refusing beyond 1e-9 wins)." in text
    assert '"beats" when lo95 is above 0, "does worse" when hi95 is below 0' in text
    assert "It changes no conversion by itself." in text


def test_refusals_and_output():
    text = _flat()
    assert "## 6. Refusals (nothing is written)" in text
    assert "do not sum exactly to the standings' runs allowed" in text
    assert "`data/rpw_fit.json`: `rpw_fit_version` (`rpw_fit_v1`)" in text
    assert "## 12. Results" in text


def test_no_dashes():
    raw = DOC.read_text(encoding="utf-8")
    assert "—" not in raw and "–" not in raw
