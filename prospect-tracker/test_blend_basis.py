# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eval blend and the served blend are two objects. Keep them apart, on purpose.

    _run_eval    (1-lam) * max(0, ols(fv)) + lam * _predict(ridge, feats)
    oos_grades   (1-lam) * max(0, ols(fv)) + lam * max(-2, a + b*_predict(ridge, feats))

`a, b` come from _fit_linear_calibration on that fold's TRAIN rows. So the eval scores the
RAW ridge inside the blend and the served path scores the CALIBRATED, CLAMPED ridge inside
it. The eval's comment claimed they were the same object; measured on debuted_km, 0 of 761
hitter rows and 0 of 900 pitcher rows carry the same blend value.

A linear calibration is monotone and cannot reorder the ridge on its own. What it does is
re-scale the model leg RELATIVE to the consensus leg it is blended against, which is why
the BLEND reorders when the ridge does not.

WHAT IT COSTS IS A MEASURED NULL, paired on identical rows, fold-clustered bootstrap
B=2000: hit +0.0044 CI95 [-0.0026, +0.0117], pit -0.0003 CI95 [-0.0072, +0.0065]. Both
contain zero, the sides point opposite ways. So nothing published is wrong by a measurable
amount and the difference must NOT be "fixed" by quietly aligning the two: that would move
every published eFV number for no measured gain. See docs/efv-2026-09-06/SERVED_LEG_BASIS.md.

This file pins the shapes and the corrected comment, not the rho values, which move with
the frame.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import efv_model as em

HERE = Path(__file__).parent
DOC = HERE / "docs" / "efv-2026-09-06" / "SERVED_LEG_BASIS.md"


def test_the_eval_blend_is_the_raw_ridge():
    src = inspect.getsource(em._run_eval)
    m = re.search(r'yp\["blend"\]\.append\(\((.*?), t\)\)', src, re.S)
    assert m, "the blend leg is no longer built where this test can read it"
    leg = m.group(1)
    assert "_predict(ridge" in leg
    assert "_fit_linear_calibration" not in leg and re.search(r"\ba\s*\+\s*b\s*\*", leg) is None, (
        "the EVAL blend now calibrates its model leg. That is the served basis. "
        "If this is deliberate, every published pooled_oos.blend moves and the "
        "reproduction in docs/efv-2026-09-06/SERVED_LEG_BASIS.md has to be re-taken"
    )


def test_the_served_blend_calibrates_and_clamps_its_model_leg():
    src = inspect.getsource(em.oos_grades)
    assert "_fit_linear_calibration" in src, (
        "oos_grades no longer calibrates the model leg, so the served object has "
        "silently changed basis to the eval's")
    assert re.search(r"max\(\s*-2\.0\s*,", src), "the served leg lost its clamp"
    assert re.search(r"\(1 - lam\) \* cons_war \+ lam \* model_war", src)


def test_the_eval_no_longer_claims_to_score_the_shipped_rank():
    src = Path(em.__file__).read_text(encoding="utf-8")
    assert "blend == the SHIPPED headline rank" not in src, (
        "the eval claims its blend IS the shipped headline rank again. It is not: "
        "the shipped rank blends the calibrated, clamped leg, and 0 of 1,661 rows "
        "agree between the two bases"
    )
    assert "THE BLEND SCORED HERE IS NOT THE SHIPPED HEADLINE RANK" in src, (
        "the correction is gone, so the next reader inherits the wrong claim")


def test_the_served_grade_maps_from_the_model_leg_not_the_blend():
    """A second, separate basis split, recorded so it is not conflated with the first.

    `xfv_grade = vf.outcome_implied_fv(xfv_war, ...)` maps from the MODEL leg, while
    `rank_war` (the board's sort) is the blend. So the board's GRADE and its ORDER
    already come from two different quantities, and that is by design. This test
    exists so a future reader does not "fix" it by pointing the grade at rank_war
    while thinking they are closing the eval-vs-served gap above, which is a
    different seam entirely.
    """
    src = (HERE / "efv_score.py").read_text(encoding="utf-8")
    assert "outcome_implied_fv(xfv_war" in src, (
        "the served grade no longer maps from the model leg; if that is deliberate "
        "every published grade moves and the epoch has to say so")
    assert re.search(r"rank_war = \(1 - lam\) \* cons_war \+ lam \* ", src)


def test_the_measurement_is_on_disk():
    assert DOC.exists(), (
        "SERVED_LEG_BASIS.md is gone. It carries the paired measurement, the "
        "stale-artifact reason S0 could not run, and the argument for NOT "
        "refactoring the five call sites; without it the next reader re-derives "
        "all three or, worse, aligns the two bases on the assumption it is a bug"
    )
    doc = DOC.read_text(encoding="utf-8")
    for token in ("+0.0044", "-0.0003", "0 of 761", "0 of 900"):
        assert token in doc, f"the measurement lost {token}"
