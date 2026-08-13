# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""P-0 pins: the label-window invariant, which is also the pitcher stuff clock.

`DEBUT_YEARS` stops one year short of `RESOLVED_THROUGH` so that every admitted
debut cohort has at least TWO observed seasons. A cohort admitted in the same
year as RESOLVED_THROUGH would carry exactly one, and `_label_6yr` would project
a six-season target off that single season at weight 1/6, which is the regime the
censoring work already measured as materially biased.

The same bound decides when a pitcher stuff feature can first be trained. AAA
tracking starts in 2023, so strict pre-decision coverage is zero for every cohort
through 2023 and first appears at 2024. A feature reaches the model only through
TRAINING rows, and training for test year Y is decision_year < Y, so the first
fold able to train on covered rows is test year 2025 - a fold that does not exist
while this bound excludes the 2025 cohort.

These tests exist so the invariant cannot be broken by editing one of the two
constants, and so the coupling is discoverable from the test suite rather than
only from a comment.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import efv_dataset as D
import efv_model as E

DATA = Path(__file__).parent / "data"


def test_debut_years_stops_one_short_of_resolved_through():
    """The invariant. Both constants may move; the RELATIONSHIP may not."""
    assert D.DEBUT_YEARS[-1] == D.RESOLVED_THROUGH - 1, (
        f"DEBUT_YEARS ends {D.DEBUT_YEARS[-1]} against RESOLVED_THROUGH "
        f"{D.RESOLVED_THROUGH}. Admitting a cohort in the RESOLVED_THROUGH year "
        f"gives it one observed season and a six-season label projected off it.")
    assert D.DEBUT_YEARS == tuple(range(D.DEBUT_YEARS[0], D.RESOLVED_THROUGH))


def test_every_admitted_cohort_has_at_least_two_observed_seasons():
    """States the bound in the units that matter, so it survives a refactor."""
    for dy in D.DEBUT_YEARS:
        observed = [y for y in range(dy, dy + D.TARGET_SEASONS)
                    if y <= D.RESOLVED_THROUGH]
        assert len(observed) >= 2, (
            f"debut cohort {dy} would carry {len(observed)} observed season(s)")


def test_the_last_scored_fold_is_covered_by_the_label_window():
    """efv_model may not score a fold the dataset cannot admit rows for."""
    assert max(E.SCORED_YEARS) <= D.DEBUT_YEARS[-1], (
        f"SCORED_YEARS reaches {max(E.SCORED_YEARS)} but DEBUT_YEARS stops at "
        f"{D.DEBUT_YEARS[-1]}, so the last fold has no debuted rows to test on")


def test_the_stuff_gate_records_why_it_is_untrainable():
    """The registered gate must keep saying it failed for lack of TRAINING rows.

    Its three ship conditions all read delta 0.0, and a reader who does not see
    `trainable` alongside them could easily record 'stuff does not help' as a
    measured result. It is not one: with zero covered training rows every arm is
    identical to the baseline by construction.
    """
    p = DATA / "xfv_pitcher_stuff_eval.json"
    if not p.exists():
        pytest.skip("stuff eval not built on this tree")
    d = json.loads(p.read_text(encoding="utf-8"))
    gate = d.get("registered_gate") or {}
    tc = gate.get("trainable_coverage") or {}
    if tc.get("trainable") is False:
        assert tc.get("train_covered_rows_all_folds") == 0, (
            "the gate reports untrainable but non-zero training coverage; the "
            "verdict and its stated reason disagree")
        assert gate.get("verdict") == "FAIL"
