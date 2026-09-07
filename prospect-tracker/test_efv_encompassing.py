# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A-CLAIM-6 asks whether the model leg adds to consensus, and answered UNDECIDED.

    y = a + b1*cons_war + b2*model_war + fold fixed effects,  out of fold, debuted_km

    hit   b2 +0.2203  CI95 [-0.0987, +0.5952]   UNDECIDED
    pit   b2 +0.1301  CI95 [-0.1509, +0.4191]   UNDECIDED

The verdict rule was fixed before the run: a player-clustered CI95 covering zero
prints UNDECIDED. The hitter permutation null gives p = 0.048, which would read as
significant at the usual bar, and the CI still covers zero. **The CI is what was
pre-specified.** These tests pin that rule into the code, because the temptation to
quote the nicer of two disagreeing nulls is exactly what it exists to stop.

They also pin the two structural guards the number depends on:
  * the regressors are cons_war and the model leg, NEVER the blend beside its own
    components (blend = (1-lam)*cons + lam*model is an exact linear combination, so
    adding it is perfect collinearity dressed as a third opinion);
  * the zero-information twin must return ~0, or the estimator is manufacturing a
    coefficient out of the fixed-effect structure and the real number means nothing.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

HERE = Path(__file__).parent
ART = HERE / "data" / "xfv_encompassing_eval.json"

efv_enc = pytest.importorskip("tools.efv_encompassing")


def _art():
    if not ART.exists():
        pytest.skip("data/xfv_encompassing_eval.json not built on this machine")
    return json.loads(ART.read_text(encoding="utf-8"))


def test_a_ci_covering_zero_prints_undecided():
    """The rule, applied to the artifact's own numbers rather than trusted."""
    d = _art()
    for side, blk in d["sides"].items():
        lo, hi = blk["ci95"]
        covers = lo <= 0.0 <= hi
        if covers:
            assert blk["verdict"] == "UNDECIDED", (
                f"{side}: CI95 [{lo}, {hi}] covers zero but the artifact claims "
                f"{blk['verdict']!r}")
        else:
            assert blk["verdict"] in ("ADDS", "SUBTRACTS")


def test_the_permutation_p_cannot_override_the_interval():
    """The hitter side is the live case: p = 0.048 next to a CI that covers zero."""
    d = _art()
    for side, blk in d["sides"].items():
        p = (blk.get("null_permuted_model_residual") or {}).get("p_two_sided")
        lo, hi = blk["ci95"]
        if p is not None and p < 0.05 and lo <= 0.0 <= hi:
            assert blk["verdict"] == "UNDECIDED", (
                f"{side}: the permutation p ({p}) was allowed to override an "
                f"interval covering zero. That is the substitution the "
                f"pre-registered rule exists to prevent")
    assert "covering zero prints UNDECIDED" in d["verdict_rule"]


def test_the_zero_information_twin_returns_nothing():
    """If a covariate that knows nothing scores, the harness is broken."""
    d = _art()
    for side, blk in d["sides"].items():
        twin = blk["null_zero_information_twin"]
        assert abs(twin["mean"]) < 0.05, (
            f"{side}: a zero-information covariate scores {twin['mean']}, so the "
            f"estimator is manufacturing a coefficient and b2 means nothing")
        lo, hi = twin["band95"]
        assert lo <= 0.0 <= hi


def test_the_blend_is_not_a_regressor_beside_its_own_components():
    src = Path(efv_enc.__file__).read_text(encoding="utf-8")
    assert "rank_war" not in src, (
        "the blend is being used as a regressor. blend = (1-lam)*cons + lam*model "
        "is an exact linear combination of the other two, so it is collinearity, "
        "not a third opinion")
    assert '"model"' in src and '"cons"' in src


def test_the_estimator_recovers_a_planted_coefficient():
    """A harness that cannot find a real effect cannot report its absence."""
    rng = random.Random(11)
    rows = []
    for i in range(400):
        cons = rng.gauss(2.0, 1.0)
        model = rng.gauss(0.0, 1.0)
        rows.append({"cons": cons, "model": model, "fold": 2019 + (i % 4),
                     "pk": f"p{i}", "w": 1.0,
                     "y": 0.5 * cons + 0.8 * model + rng.gauss(0, 0.2)})
    b1, b2 = efv_enc.fit_b2(rows)
    assert abs(b1 - 0.5) < 0.05, b1
    assert abs(b2 - 0.8) < 0.05, b2


def test_the_estimator_returns_zero_when_the_model_is_noise():
    rng = random.Random(12)
    rows = []
    for i in range(400):
        cons = rng.gauss(2.0, 1.0)
        rows.append({"cons": cons, "model": rng.gauss(0.0, 1.0),
                     "fold": 2019 + (i % 4), "pk": f"p{i}", "w": 1.0,
                     "y": 0.5 * cons + rng.gauss(0, 0.2)})
    _b1, b2 = efv_enc.fit_b2(rows)
    assert abs(b2) < 0.05, b2


def test_fold_fixed_effects_absorb_a_cohort_level_shift():
    """A regressor whose only agreement with y is the cohort trend must not score.

    Both `model` and `y` carry the same large per-cohort level move, and their
    WITHIN-fold variation is independent noise. Pooled, they would correlate
    strongly and b2 would be large; with the fold effects absorbing the level,
    the only thing left to explain is noise, so b2 must be ~0. That is what stops
    a model from being credited for tracking a cohort trend the consensus anchor
    misses.

    The regressor keeps real within-fold variance ON PURPOSE. A model that is
    PURELY the fold level sits in the column space of the dummies, so its
    coefficient is not identified at all and lstsq splits it arbitrarily between
    them; a first version of this test asserted on that arbitrary split and was
    measuring the solver, not the design.
    """
    rng = random.Random(13)
    rows = []
    for i in range(400):
        fold = 2019 + (i % 4)
        shift = (fold - 2019) * 3.0            # a big per-cohort level move
        rows.append({"cons": rng.gauss(2.0, 1.0),
                     "model": shift + rng.gauss(0, 1.0),   # informative-looking, isn't
                     "fold": fold, "pk": f"p{i}", "w": 1.0,
                     "y": shift + rng.gauss(0, 1.0)})
    got = efv_enc.fit_b2(rows)
    assert got is not None
    _b1, b2 = got
    assert abs(b2) < 0.15, (
        f"b2 = {b2}: a regressor whose only agreement with y is the cohort level "
        f"is scoring, so the fold fixed effects are not absorbing the shift")
