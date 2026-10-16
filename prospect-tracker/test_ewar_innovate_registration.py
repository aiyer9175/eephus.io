# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Registration pins for task EWAR_INNOVATE_LEDGER (owner decisions EW3-16 to EW3-23).

Four documents, each committed ALONE before any number of its estimands exists:

  docs/ewar/PITCH_LEDGER_GATE.md      (a) the pitch-level run value attribution ledger
  docs/ewar/SWING_DECISION_GATE.md    (b) swing-decision value and its two tests
  docs/ewar/CATCHER_VALUE_2_GATE.md   (c) catcher value 2.0 and its two validations
  docs/ewar/TALENT_EWAR_GATE.md       (d) talent eWAR, its band and its reads

Each clause is pinned by the sentence that makes it bind, on a whitespace-flattened copy so a
re-wrapped paragraph is not a failure. Results live in each document's last part, never here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
DOCS = {
    "ledger": ROOT / "docs" / "ewar" / "PITCH_LEDGER_GATE.md",
    "swing": ROOT / "docs" / "ewar" / "SWING_DECISION_GATE.md",
    "catcher": ROOT / "docs" / "ewar" / "CATCHER_VALUE_2_GATE.md",
    "talent": ROOT / "docs" / "ewar" / "TALENT_EWAR_GATE.md",
}


def _flat(key: str) -> str:
    return re.sub(r"\s+", " ", DOCS[key].read_text(encoding="utf-8"))


@pytest.mark.parametrize("key", sorted(DOCS))
def test_each_document_is_registered_before_numbers(key):
    flat = _flat(key)
    assert "is committed ALONE" in flat
    assert "before any number of its estimands is computed" in flat
    assert "STATUS: REGISTERED" in flat
    assert chr(0x2014) not in DOCS[key].read_text(encoding="utf-8")
    assert chr(0x2013) not in DOCS[key].read_text(encoding="utf-8")


@pytest.mark.parametrize("key", ["swing", "catcher", "talent"])
def test_development_frames_never_read_the_skill_look_frame(key):
    flat = _flat(key)
    assert "never read" in flat
    assert "2021 to 2024" in flat


# (a) the ledger -----------------------------------------------------------------------


def test_ledger_components_sum_to_the_step():
    flat = _flat("ledger")
    for line in (
        "x_duel = V(z) - V(before)",
        "x_frm = - d_c * v",
        "x_ump = - (s0 - z - d_c - d_p - d_b) * v",
        "x_ch = V(s1) - V(s0)",
        "x_oth = dRE - (V(s1) - V(before))",
    ):
        assert line in flat, line
    assert "On every step, the batting side's credits sum to the step's run value" in flat
    assert "the components sum to dRE within 1e-9 runs" in flat


def test_ledger_framing_is_net_of_challenge_exposure_and_sigma_is_frozen_on_2018():
    flat = _flat("ledger")
    assert "fitted on that season's called pitches (on s1, the call that stood" in flat
    assert "The four sigma_g are chosen ONCE on the 2018 season" in flat
    assert "then frozen in `pitch_ledger.py` for every season and never re-chosen" in flat


def test_ledger_planted_recovery_and_null_comparator():
    flat = _flat("ledger")
    assert "I5, the planted recovery and the null comparator" in flat
    assert "the planted catcher's fitted effect lies between 0.20 and 0.40" in flat
    assert "below one third of their sd in the planted run" in flat


def test_ledger_measures_only():
    flat = _flat("ledger")
    assert "It forecasts nothing, admits nothing and serves nothing." in flat
    assert "no year-to-year, split-half or forward statistic of any ledger total is computed" in flat


# (b) swing decisions ------------------------------------------------------------------


def test_swing_decision_credits_the_choice_not_the_contact():
    flat = _flat("swing")
    assert "It credits the choice, never the contact" in flat
    assert "with a ball in play valued at the ledger's x_x" in flat
    assert "DV = (VT - VS) if the batter took, (VS - VT) if he swung." in flat


def test_swing_decision_test_x_arms_and_rule():
    flat = _flat("swing")
    assert "N, the null comparator: the unmodified xHEM+." in flat
    assert "P, the permuted twin:" in flat
    assert "Pass rule (DEV PASS):** V - N has lo95 above 0, and the twin fails" in flat
    assert "The registered expectation is NOT VALIDATED" in flat


def test_swing_decision_test_e_waits_for_resolved_labels():
    flat = _flat("swing")
    assert "Runs only when at least two AAA seasons have a resolved label." in flat
    assert "never a cell by FV level" in flat


# (c) catcher value 2.0 ----------------------------------------------------------------


def test_catcher_value_parts_and_eabs_kept_beside():
    flat = _flat("catcher")
    assert "CV2 = FRM + BLK + THR" in flat
    assert "CV2 therefore never carries eABS under this document" in flat


def test_catcher_value_validations():
    flat = _flat("catcher")
    assert "3.1 V-P, self-persistence." in flat
    assert "3.2 V-S, catcher switches and the team's runs allowed (same season, held out)." in flat
    assert "so the measure never sees the games it is scored on" in flat
    assert "DEV PASS when V-P and V-S both pass" in flat


# (d) talent eWAR ----------------------------------------------------------------------


def test_talent_ewar_target_and_dispositions():
    flat = _flat("talent")
    assert "The deciding target is next-season realized runs" in flat
    assert "WIN (components)** needs lo95 above 0 against R and against B1" in flat
    assert "DEV PASS, per side:** T1's rate cell WIN (components), its total cell not LOSS, and T2's band passes." in flat


def test_talent_ewar_constants_are_fitted_before_the_read():
    flat = _flat("talent")
    assert "K_c = hm (1 - r_c) / r_c" in flat
    assert "Frozen in `talent_ewar.py` with their log before any read of part 3." in flat
    assert "The band passes for a side when every part's coverage lies between 0.75 and 0.85." in flat
