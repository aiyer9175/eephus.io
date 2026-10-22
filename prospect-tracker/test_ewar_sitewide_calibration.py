# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR site-wide calibration's registration pins
(docs/ewar-2026-10-22/EWAR_SITEWIDE_CALIBRATION.md, task EWAR_SITEWIDE_CALIBRATION).

The registration is committed ALONE, before any number of its estimands exists. Every
clause is pinned by the sentence that makes it bind. Prose assertions run against a
whitespace-flattened copy of the document, so re-wrapping a paragraph is not a test
failure.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ewar-2026-10-22" / "EWAR_SITEWIDE_CALIBRATION.md"


def _flat() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


def test_document_names_itself_and_this_test():
    text = _flat()
    assert text.startswith("# eWAR site-wide calibration: which WAR each consumer reads "
                           "(pre-registration, 2026-10-22)")
    assert "This document is committed ALONE, before any number of its estimands is computed" in text
    assert "`test_ewar_sitewide_calibration.py`" in text


def test_basis_decision_never_claims_accuracy():
    text = _flat()
    assert "**Each switch below is an owner basis decision (EW3-20) with a registered accounting check" in text
    assert "copy may never say a number improved because its WAR basis changed" in text
    assert "groups a realized number by FV, eFV or consensus band" in text


def test_wag_reads_the_headline_by_literal_provider():
    text = _flat()
    assert 'observed_new(R) = war_source.row_on_provider(R, "ewar_v3").career_war' in text
    assert "The provider id is named literally, `\"ewar_v3\"`, never `DISPLAY_PROVIDER`" in text
    assert "`storage.WAG_EWAR_HEADLINE` (default False at the build commit)" in text
    assert "Debuted value, surplus and trade value keep reading `R.career_war`" in text


def test_wag_check_and_pass_rule():
    text = _flat()
    for clause in ("C-1: no WAG-bearing player whose row has no 2026 season",
                   "C-2: for every player whose observed leg moves",
                   "C-3: the debuted value block",
                   "PASS when C-1, C-2 and C-3 all hold."):
        assert clause in text


def test_awards_deserved_band_and_verdict():
    text = _flat()
    assert "k_x = sum of d^2 / (2 * sum of e)" in text
    assert "player-seasons 2015 to 2025, 2020 excluded" in text
    assert "band(p, S) = realized(p, S) +/- 1.645 * sigma(p, S)" in text
    assert "realized(L) - realized(i) < 1.645 * sqrt(sigma(L)^2 + sigma(i)^2)" in text
    assert "`DESERVED_N = 5`" in text
    assert "`awards_core.AWARDS_DESERVED_LIVE` (default False at the build commit)" in text
    for clause in ("D-1:", "D-2:", "D-3:", "D-4:"):
        assert clause in text
    assert "no rate, count or test over seasons is computed from these comparisons" in text


def test_deferred_consumers_and_owner_questions():
    text = _flat()
    assert "`hof_data.WAR_PROVIDER = \"bwar\"` is FROZEN" in text
    assert "SWC-Q1 (Hall of Fame basis): (a) keep the HoF rule on bWAR" in text
    assert "SWC-Q2 (Franchise club WAR history): (a) keep bWAR from 1969" in text
