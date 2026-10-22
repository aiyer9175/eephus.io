# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR headline label check's registration pins
(docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md, task EFV_LABEL_HEADLINE_EWAR_CHECK).

The registration is committed ALONE, before any number of its estimands exists. Every
clause is pinned by the sentence that makes it bind. Prose assertions run against a
whitespace-flattened copy of the document, so re-wrapping a paragraph is not a test
failure. Once part 9 records a result, the emptiness assertion is replaced by a pointer
to the result pin.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "efv-2026-10-22" / "EWAR_HEADLINE_LABEL_GATE.md"


def _flat() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


def test_document_names_itself_and_this_test():
    text = _flat()
    assert text.startswith("# eWAR headline label check: eFV's label from published fWAR to the "
                           "headline eWAR (pre-registration, 2026-10-22)")
    assert "Task EFV_LABEL_HEADLINE_EWAR_CHECK (owner answer EWLE-Q2 \"Headline eWAR, after a check\"" in text
    assert "This document is committed ALONE, before any number of its estimands is computed" in text
    assert "`test_ewar_headline_label_registration.py`" in text


def test_basis_decision_and_clause_l():
    text = _flat()
    assert ("**The label basis is an OWNER BASIS DECISION, and one registered condition stands in front "
            "of it: the circularity guard of part 4, the core gate's guard re-read on the headline "
            "label.**") in text
    assert "copy may never claim an accuracy gain from a basis change" in text


def test_label_is_headline_with_realized_sensitivity():
    text = _flat()
    assert "label(p, s) = war_hit(p, s) + dh_bat(p, s) + war_pit(p, s) + dh_pit(p, s)" in text
    assert "**The label is the HEADLINE eWAR: published fWAR plus the eABS part from 2026.**" in text
    assert "It trains nothing and anchors nothing" in text
    assert "**The transform contract is the eWAR v3 transform's.**" in text


def test_structural_count_is_stated_before_the_look():
    text = _flat()
    assert "40ea0196102beb793e2aeae1d6503d160acbec92c6eebf6e583fae8bcc81fe69" in text
    assert ("lists headline departures on 1,470 player-seasons, every one of them in 2026 (662 hitting "
            "cells and 868 pitching cells), and none in 2000 to 2025") in text


def test_frozen_vintage_and_switch_contract():
    text = _flat()
    assert ("`data/ewar_headline_label.json`, written ONCE by `python tools/build_ewar_headline_label.py "
            "--write`") in text
    assert "`ewar-headline-<fWAR vintage id>-<first 12 hex of content_sha256>`" in text
    assert "The builder refuses to overwrite a file whose content differs" in text
    assert "(4) no headline departure falls in a season before 2026" in text
    assert "`war_source.EFV_LABEL_EWAR_HEADLINE` defaults to False" in text
    assert "**Scope: eFV's label, and only eFV's label.**" in text
    assert "The career_war table is NOT rebased and `war_source.DEFAULT_PROVIDER` stays `\"fwar\"`" in text
    assert "`ewar_headline@<vintage id>`" in text
    assert "listed in `deploy/data_exclude.txt`" in text
    assert "the flip commit carries only the flag, the registry, the glossary, copy and tests" in text


def test_guard_is_the_core_guard_with_the_series_changed():
    text = _flat()
    assert "Y in 2011 to 2018 and 2021 to 2024" in text
    assert "300 or more plate appearances in Y and in Y + 1" in text
    assert "**Gap = S(a) - S(b).**" in text
    assert "Player-clustered bootstrap, B 2,000, seed 20261022" in text
    assert "**Rule. NON-INFERIOR when lower > -0.02.**" in text
    assert "**The random-change comparator (the permuted twin).**" in text
    assert ("**NON-INFERIOR when dT - 1.645 sd > -0.02 under both bootstraps for every carried "
            "outcome**") in text
    assert "seed 20261024" in text


def test_decision_and_stop_rules():
    text = _flat()
    assert "**THE GUARD HOLDS when G-1 and G-2 are both NON-INFERIOR.**" in text
    assert "**Otherwise the switch does not flip.** eFV keeps published fWAR" in text
    assert "On any exception after scoring began: STOP, no re-run, `OWNER_QUESTION.md`." in text
    assert "`docs/efv-2026-10-22/ewar_headline_label_guard.json`" in text


def test_identity_disclosure_and_the_eabs_read():
    text = _flat()
    assert "**It is an identity check, by construction.**" in text
    assert "It says nothing about the eABS part, the one part of the label the site produces" in text
    assert ("If the look reads anything other than a G-1 gap of exactly 0, a twin gap of exactly 0, "
            "`n_pairs_departing` 0 and a G-2 dT of exactly 0 on every outcome") in text
    assert "(EWHL-R1)" in text
    assert "The data does not exist today, so this read cannot run now." in text


def test_owner_question_and_exclusions():
    text = _flat()
    assert "**EWHL-Q1 (recorded after the look, not blocking; the default is applied).**" in text
    assert "`war_source.LABEL_EWAR_CORE` stays False" in text
    assert "`docs/PROSPECT_ANCHOR_GATE.md`" in text


def test_results_part_is_pinned_by_the_result_test():
    # part 9 was empty at registration (072861de); its 2026-10-22 entry is pinned by
    # test_ewar_headline_label_result.py
    text = _flat()
    assert "## 9. Results **EMPTY AT REGISTRATION.**" in text
    assert "### 2026-10-22: the guard HOLDS, by identity, as part 4.5 stated" in text


def test_amendment_9_1_identity_3_tolerance():
    text = _flat()
    assert ("### Amendment 9.1 (2026-10-22, before the vintage is frozen and before any guard statistic): "
            "identity 3's tolerance") in text
    assert ("(a) the artifact's own pre-rounding sum `checks[s].sum_departure_wins.dh_<side>` is within "
            "1e-9 wins of zero, and (b) the stored 6-decimal departures sum to zero within the rounding "
            "bound n x 0.5e-6 wins") in text
