# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR uncertainty band read's registration pins
(docs/ewar-v3/EWAR_UNCERTAINTY_BAND_GATE.md, task EWAR_UNCERTAINTY_BAND, owner EW3-50).

The registration is committed ALONE, before any number of its estimands exists. Every
clause that binds the read is pinned by the sentence that makes it bind. Prose
assertions run against a whitespace-flattened copy of the document, so re-wrapping a
paragraph is not a test failure.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ewar-v3" / "EWAR_UNCERTAINTY_BAND_GATE.md"


def _flat() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


def test_document_names_itself_and_this_test():
    text = _flat()
    assert text.startswith("# eWAR uncertainty band: a spread for every player-season, coverage-checked "
                           "(pre-registration, 2026-10-22)")
    assert "This document is committed ALONE, before any number of its estimands is computed" in text
    assert "`test_ewar_uncertainty_band_gate.py`" in text
    assert "## 13. Results" in text
    assert "`data/_labs/ewar_uncertainty_band/record.json`" in text


def test_band_form_and_terms():
    text = _flat()
    for clause in ("sigma(p, s, x) = sqrt(sigma_samp^2 + sigma_src^2)",
                   "band(p, s, x) = eWAR_x(p, s) +/- z80 * sigma(p, s, x), z80 = 1.2816",
                   "k_c = sum over rows of (x_A - x_B)^2 / sum over rows of (1 / e_A + 1 / e_B)",
                   "`k_src = sum d^2 / (2 * sum e)`",
                   "Odd against even `game_pk` within a season"):
        assert clause in text, clause
    for term in ("| k_bat | batting runs | PA |", "| k_ebr | baserunning runs | PA |",
                 "| k_fip | pitching runs, FIP basis | IP |", "| k_ra | pitching runs, runs-allowed basis | IP |",
                 "| k_src,bat | method disagreement, hitting | PA |",
                 "| k_src,pit | method disagreement, pitching | IP |"):
        assert term in text, term
    assert "their sampling noise is not measured" in text


def test_frame_split_floors_and_bands():
    text = _flat()
    assert ("Each other season is FIT when `s mod 3 = 0`, CAL when `s mod 3 = 1` and TEST when "
            "`s mod 3 = 2`") in text
    assert "| C2-fip, C2-ra (sampling) | 2019, 2022, 2025 | 2023 | 2018, 2021, 2024 |" in text
    assert "Hitting side (PA): floor 20; bands [20, 100), [100, 300), [300, 500), [500, up)." in text
    assert "Pitching side (IP): floor 5; bands [5, 20), [20, 60), [60, 120), [120, up)." in text
    assert "every cell of part 7 carries at least 100 TEST rows and 50 CAL rows" in text


def test_multipliers_fixed_before_test():
    text = _flat()
    assert "if c_b is outside [0.77, 0.83]:" in text
    assert "The multipliers are fixed from CAL before any TEST row is read and are never refitted on TEST." in text


def test_checks_comparators_bootstraps_planted():
    text = _flat()
    assert "| C1-bat, C1-pit | `fWAR_side - bWAR_side` | `sqrt(2 * k_src * e)` |" in text
    assert "`IS = 2 h + (2 / 0.2) * max(0, |D| - h)`" in text
    assert "**N0, the exposure-blind null.**" in text and "**N1, the no-change null.**" in text
    assert "Two, B = 4,000 each, seed 20261023" in text
    assert "player-clustered" in text and "club-clustered" in text
    assert "**PLANTED PASS** when the truth candidate reads PASS (part 7) in at least 16 of 20 replicates" in text
    assert "a Student t with 5 degrees of freedom scaled to unit variance" in text


def test_pass_rule():
    text = _flat()
    assert ("in every one of the 24 cells, the 5th to 95th percentile interval of TEST coverage lies "
            "inside [0.75, 0.85] under both bootstraps") in text
    assert ("`lo > 0` under both bootstraps for d(N0) in all six families and for d(N1) in the four C2 "
            "families") in text
    assert "**PASS** when CALIBRATED, SHARPER THAN THE NULLS and the planted check read PLANTED PASS." in text
    assert "A read whose planted check failed cannot PASS" in text


def test_licence_bans_and_owner_question():
    text = _flat()
    assert "**A PASS builds the band dark and raises one owner question,** EWUB-Q1" in text
    assert "(c) record only, nothing served" in text
    assert "that the band is a confidence interval for talent" in text
    assert "`docs/PROSPECT_ANCHOR_GATE.md`" in text
    assert "`backtest.run_backtest`" in text
    assert "A second `--read` refuses while the record exists." in text
    assert "it uses eBR's priced events only as the baserunning component's noise proxy" in text
