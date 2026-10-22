# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR core label epoch registration pins
(docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md, task EFV_LABEL_EPOCH_EWAR).

The registration is committed ALONE, before any number of its estimands exists.
Every clause is pinned by the sentence that makes it bind. Prose assertions run
against a whitespace-flattened copy of the document, so re-wrapping a paragraph is
not a test failure. A result pin never lives here: once part 11 records a result,
the emptiness assertion below is replaced by a pointer to the result pin.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "efv-2026-10-22" / "EWAR_CORE_LABEL_EPOCH_GATE.md"


def _flat() -> str:
    return re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))


def test_document_names_itself_and_this_test():
    text = _flat()
    assert text.startswith("# eWAR core label epoch: eFV's label moves from published fWAR to core "
                           "eWAR (pre-registration, 2026-10-22)")
    assert "Task EFV_LABEL_EPOCH_EWAR (owner decisions EW3-17, EW3-19 and EW3-20" in text
    assert "This document is committed ALONE, before any number of its estimands is computed" in text
    assert "`test_ewar_core_label_epoch_registration.py`" in text


def test_basis_decision_and_its_one_condition():
    text = _flat()
    assert ("**The label basis is an OWNER BASIS DECISION, and one registered condition stands in "
            "front of it: the circularity guard of part 4.**") in text
    assert "Evaluating a model on a label you also produce is circular" in text


def test_label_definition_is_core_with_realized_sensitivity():
    text = _flat()
    assert "core_i = war_i - (B_i + Fr_i)" in text
    assert "core_j = war_j" in text
    assert ("**The label is CORE: published fWAR built only from the parts present in every season "
            "2000 to 2026**") in text
    assert "**The realized-core sensitivity** is the label plus the realized pitching departure R2" in text
    assert "It is a sensitivity: it trains nothing and anchors nothing." in text
    assert "**The transform contract is the fwar transform's.**" in text


def test_history_gate_relation_is_stated():
    text = _flat()
    assert "This registration does not read `data/ewar_history.json`" in text
    assert "CORE is still never displayed, never a column and never a sort key on any served surface" in text


def test_frozen_vintage_and_provider_contract():
    text = _flat()
    assert "`data/ewar_core_label.json`, written ONCE by `python tools/build_ewar_core_label.py --write`" in text
    assert "`ewar-core-<fWAR vintage id>-<first 12 hex of content_sha256>`" in text
    assert "The builder refuses to overwrite a file whose content differs" in text
    assert "`war_source.LABEL_EWAR_CORE` defaults to False" in text
    assert "The flag flips at step D + U of the epoch run (part 8), never in this task." in text
    assert "`DISPLAY_PROVIDER` is unchanged." in text
    assert "`ewar_core@<vintage id>`" in text
    assert "listed in `deploy/data_exclude.txt`" in text


def test_guard_legs_rules_and_seeds():
    text = _flat()
    assert "predictor seasons Y in 2011 to 2018 and 2021 to 2024" in text
    assert "300 or more plate appearances in Y and in Y + 1" in text
    assert "**Gap = S(a) - S(b).**" in text
    assert "B 2,000, seed 20261022" in text
    assert "**Rule. NON-INFERIOR when lower > -0.02.**" in text
    assert "`numpy.random.default_rng(20261022)`" in text
    assert "seed 20261024" in text
    assert ("**NON-INFERIOR when dT - 1.645 sd > -0.02 under both bootstraps for every carried "
            "outcome.**") in text
    assert "**THE GUARD HOLDS when G-1 and G-2 are both NON-INFERIOR.**" in text
    assert "**Otherwise the flip does not happen.**" in text
    assert "no default is taken" in text


def test_secondary_legs_decide_nothing():
    text = _flat()
    assert "### 4.3 Secondary legs (descriptive: each decides nothing)" in text
    for leg in ("G-1 on the rate", "G-1 at a 200 PA floor", "The realized-core sensitivity on pitchers",
                "absolute framing term above 0.05 runs"):
        assert leg in text


def test_blast_radius_is_label_only():
    text = _flat()
    assert "no grade, no consensus FV, no model output and no FV cell is read" in text
    assert "The reserved vintages 2020 and 2021 and the 2025 and later debut cohorts are never read" in text


def test_reads_carry_the_cross_label_disclosure():
    text = _flat()
    assert "on the incumbent fWAR label (the cross-label disclosure part 0 requires)" in text
    assert "Development rows adjudicate NOTHING" in text
    assert "CORROBORATION ONLY" in text


def test_clause_l_is_carried_and_one_factor():
    text = _flat()
    assert "**(l) copy may never claim an accuracy gain from a basis change**, absolute" in text
    assert "The basis is the only factor of this epoch" in text
    assert "`RESOLVED_THROUGH` stays 2026." in text


def test_epoch_runs_in_the_main_tree():
    text = _flat()
    assert "**It runs in the main tree, with every lane stopped, as task EWAR_CORE_EPOCH_RUN.**" in text
    assert "This task builds, guards and measures; it does not flip." in text
    assert "`../_pre_epoch_ewar_core_2026-10/`" in text
    for site in ("awards_export.py", "storage.py", "efv_v2_dev_read.py", "prospect_anchor_gate.py"):
        assert site in text


def test_owner_questions():
    text = _flat()
    assert "**EWLE-Q1 (recorded, not blocking; the default is applied).**" in text
    assert "**EWLE-Q2 (asked only if the guard of part 4 does not hold; blocking, no default).**" in text


def test_results_part_points_to_the_result_pin():
    """Part 11 recorded the guard read on 2026-10-22; its numbers are pinned by
    test_ewar_core_label_epoch_result.py. Nothing above part 11 may change."""
    text = DOC.read_text(encoding="utf-8")
    head, tail = text.split("## 11. Results", 1)
    assert "**EMPTY AT REGISTRATION.**" in tail
    assert "### 2026-10-22: the circularity guard does NOT hold" in tail
    assert (ROOT / "test_ewar_core_label_epoch_result.py").exists()


def test_no_dashes():
    text = DOC.read_text(encoding="utf-8")
    assert "\u2014" not in text and "\u2013" not in text
