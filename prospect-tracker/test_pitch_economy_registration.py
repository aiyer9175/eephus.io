# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pitch-economy registration pins (task EWAR_T1_PITCH_ECON, owner answer EW3-19).

Two documents are committed ALONE, before any number of their estimands exists:

  1. docs/ebr-2026-09-30/EBR_GATE.md part 11.3, the eWAR v3 candidate parts PE-P
     (pitchers) and PE-H (hitters): their formulas, targets, bases, cells, guards,
     admission, assembly and copy, and the constants they freeze before the look.
  2. docs/ewar/PITCH_ECONOMY_LAB.md, the descriptive lab, the same-season
     decomposition, the fit of those constants, and the trigger for the owner's
     question about pitch counts inside HEM+, SEM+ and REM+.

Every clause is pinned by the sentence that makes it bind. Prose assertions run on a
whitespace-flattened copy so that re-wrapping a paragraph is not a failure. A result
pin never lives here: the lab's results go in part 10 of its own document and the
skill look's in part 12.2 of the gate.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GATE = ROOT / "docs" / "ebr-2026-09-30" / "EBR_GATE.md"
LAB = ROOT / "docs" / "ewar" / "PITCH_ECONOMY_LAB.md"

AMEND_HEAD = ("### 11.3 2026-10-15: the pitch-economy candidate parts PE-P and PE-H (clause (i), "
              "owner decisions EW3-19 and EW3-23)")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _amendment() -> str:
    doc = GATE.read_text(encoding="utf-8")
    return doc[doc.index("### 11.3 2026-10-15"):doc.index("## 12. Results")]


def _lab() -> str:
    return LAB.read_text(encoding="utf-8")


# 1. The amendment sits in part 11, after 11.2 and before the results -------------


def test_amendment_is_placed_after_11_2_and_before_part_12():
    doc = GATE.read_text(encoding="utf-8")
    assert doc.count(AMEND_HEAD) == 1
    assert doc.index("### 11.2 2026-10-15") < doc.index(AMEND_HEAD) < doc.index("## 12. Results")


def test_amendment_records_the_owner_answer_and_its_footing():
    flat = _flat(_amendment())
    assert "\"pitch economy = register BOTH a hitter and a pitcher part for the v3 skill look\"" in flat
    assert "| EW3-19 (pitch economy) | Whether pitch economy is a candidate part of eWAR v3 |" in flat
    assert "is recorded as an owner-decided addition (EW3-19) on the footing of 11.2" in flat
    assert "Nothing registered for candidate parts 1 to 6 changes" in flat
    assert "Pinned by** `test_pitch_economy_registration.py`" in flat


def test_neither_part_adds_a_pitch_count_to_war():
    flat = _flat(_amendment())
    assert "A pitch count added on top would count twice." in flat
    assert "Neither part is a raw P/PA, P/BF, P/IP or PAR term." in flat
    assert "a skill arm minus an actual arm through the same function" in flat


# 2. PE-P ---------------------------------------------------------------------------


def test_pe_p_formula_lines():
    flat = _flat(_amendment())
    for line in (
        "ppo~_j,r = (P_j,r + K_o * L_ppo,s,r) / (O_j,r + K_o) K_o = 120 outs",
        "b~_j,r = (P_j,r + k_b * L_pa,s,r) / (n_j,r + k_b) k_b = 2 appearances",
        "X~_j,r = n_j,r * min(27, b~_j,r / ppo~_j,r)",
        "G_j,r = X~_j,r - O_j,r",
        "T9_s = 27 * pi_s * delta_TTO",
        "c_j,SP = (F_RP,s - F~_j - T9_s) / 27",
        "c_j,RP = (F_RP,s - F~_j) / 27",
        "Delta_PE,j = sum over r of ( g_j,r - O_j,r * (sum_k g_k,r) / (sum_k O_k,r) ) zero-sum per season and role",
        "test value = B0_j + Delta_PE,j / RPW_s",
    ):
        assert line in flat, line
    assert "The lineup ratio r_L is 1 here" in flat
    assert "carries Delta_PE = 0, outside the re-centring" in flat


# 3. PE-H ---------------------------------------------------------------------------


def test_pe_h_formula_lines():
    flat = _flat(_amendment())
    for line in (
        "CLres_i = sum over a of (CL_a - CLbar_s,e(a))",
        "Pres_i = sum over a faced against the opposing starter of (p_a - pbar_s,e(a))",
        "w_s = (F_RP,s - F_SP,s - T9_s) / (27 * L_ppo,s,SP)",
        "g_PEH,i = CLres_i * n_i / (n_i + K_CL) + w_s * Pres_i * m_i / (m_i + K_P)",
        "d_PEH,i = g_PEH,i - PA_i * (sum_k g_PEH,k) / (sum_k PA_k) zero-sum per season, MLB-wide per PA",
        "test value = B0_i + d_PEH,i",
    ):
        assert line in flat, line
    assert "The starter is the first pitcher of each fielding half" in flat


# 4. Targets, cells, guards (11.2.7) -------------------------------------------------


def test_targets_bases_and_cells():
    flat = _flat(_amendment())
    assert "| PE-P | pitching: innings and bullpen cost, outside the four components of 11.2.1 |" in flat
    assert "| PE-H | batting plus starter wear | wRAA_i(Y), the batting B0 of 11.2.1 |" in flat
    assert "RSB_j(Y+1) = (O_j(Y+1) / 27) * (lgRA9*_RP,Y+1 - RA9*_j(Y+1))" in flat
    assert "W_i(Y+1) = w_Y+1 * Pres_i(Y+1)" in flat
    assert "{PE-P rate, PE-P total}, k = 2; {PE-H rate, PE-H total}, k = 2" in flat
    assert "B = 2,000 and seed 20261008" in flat
    assert "PE-H on the 2018 to 2019 pair, the only corpus pair before the frame" in flat


def test_guards_and_admission():
    flat = _flat(_amendment())
    assert "**Era transport (PE-P):** the rate cell's point gap against B0 is positive in BOTH" in flat
    assert ("The rate cell's gap on wRAA_i(Y+1) alone, W left out, must not be LOSS") in flat
    assert "**The team guard of 11.2.4,** unchanged" in flat
    assert "**The secondary estimand of 11.2.5,** unchanged" in flat
    assert "its team guard is NON-INFERIOR and, for PE-H, the sensitivity guard is not LOSS" in flat
    assert "their combination with each other or with candidate parts 1 to 6 is never scored" in flat
    assert "\"eWAR realized\" (11.2.8) carries no pitch-economy term" in flat
    assert "\"eWAR skill: pitch economy (pitching)\" and \"eWAR skill: pitch economy (batting)\"" in flat


def test_constants_and_disclosure():
    flat = _flat(_amendment())
    assert "on the 2018 and 2019 corpus seasons only (outside the frame's predictor and outcome seasons)" in flat
    assert "never re-chosen. The skill look reads the frozen values and refits nothing." in flat
    assert "None relates a pitch rate or a pitch-economy delta to a next-season quantity on this frame's pairs." in flat
    assert "It computes no year-to-year, forward or split-half statistic of Delta_PE or d_PEH" in flat
    assert "Nothing in 11.3.2 to 11.3.5 changes after the lab" in flat


def test_before_the_skill_look_with_a_null_comparator_and_planted_recovery():
    flat = _flat(_amendment())
    assert "The skill look (part 7.3) does not run until `tools/swar_lab.py` implements this amendment" in flat
    assert "an all-zero delta never reads WIN, and the planted delta's twin fails" in flat
    assert "Committed alone, docs and their pin test only, before the skill look" in flat


# 5. The lab document ----------------------------------------------------------------


def test_lab_document_registers_before_any_number():
    flat = _flat(_lab())
    assert flat.startswith("# Pitch economy: the descriptive lab and the decomposition (pitch_economy_lab_v1)")
    assert "Its pin test is `test_pitch_economy_registration.py`." in flat
    assert "STATUS: REGISTERED, RESULTS EMPTY." in flat
    assert "The lab decides nothing about eWAR" in flat


def test_lab_frames_and_statistics():
    flat = _flat(_lab())
    assert "(Y, Y+1) for Y in 2016, 2017, 2018, 2021, 2022, 2023, 2024; 2020 out on both sides" in flat
    assert "hitters with 300 or more PA in both seasons" in flat
    assert "pitchers with 50 or more IP in both seasons" in flat
    assert "B = 2,000, seed 20261015" in flat
    assert "**2026 never enters.**" in flat
    assert "Part D reads no Y+1 quantity of any kind." in flat


def test_lab_constant_fit_and_trigger():
    flat = _flat(_lab())
    assert "rho_full = 2 * rho_half / (1 + rho_half); K = nbar * (1 - rho_full) / rho_full" in flat
    assert "K clamped to 50 to 20,000; rho_half at or below 0 sets K to infinity" in flat
    assert "**Residual value is shown** when any of these 95 percent intervals, pooled, excludes 0" in flat
    for item in ("(h) part A2", "(s) part C2, starters", "(r) part C2, relievers"):
        assert item in flat, item
    assert "never on HEM+" in flat
    assert "the answer to the owner's question is no, on this lab's numbers" in flat


def test_lab_never_list():
    flat = _flat(_lab())
    assert "It computes no year-to-year, forward or split-half statistic of Delta_PE or d_PEH" in flat
    assert "no betting artifact, dark column, price, market capture or game result, and no 2026 row" in flat
    assert "(`docs/PROSPECT_ANCHOR_GATE.md`)" in flat


RESULT_PATTERNS = (
    r"\[\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\]",
    r"\bp\s*=\s*-?0?\.\d",
    r"\brho(_[A-Z])?\s*=\s*-?\d",
    r"\bgap\s*=\s*[-+]?\d",
    r"\bverdict\s*:\s*\w",
    r"\btriggered\s*:\s*(true|false|yes|no)\b",
)


def test_no_result_is_recorded_in_the_lab_document_before_its_run():
    text = _lab()
    head, results = text.split("## 10. Results", 1)
    for pattern in RESULT_PATTERNS:
        m = re.search(pattern, head, re.I)
        assert m is None, f"a result above part 10: {m.group(0) if m else ''!r}"
    if not (ROOT / "data" / "_labs" / "pitch_economy_partials.json").exists():
        assert _flat(results).strip() == "EMPTY AT REGISTRATION."
