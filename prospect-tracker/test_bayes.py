# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the hierarchical Bayesian P(bucket|FV) model (Prompt G).

Validates:
  * partial pooling -- hitter/pitcher slopes shrink toward each other (the thin
    pitcher cells borrow strength from the hitters);
  * posterior median ~ the point-estimate fit where samples are large;
  * credible intervals WIDEN where cells are thin (pitcher vs hitter) and in
    EXTRAPOLATION (FV > 60, FV < 45);
  * the P(bucket|FV) posterior propagates to an epistemic credible interval on SV;
  * posterior draws are valid distributions; intervals are well-ordered.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import value_framework as vf

_FIT = json.loads((Path(__file__).resolve().parent / "data" / "value_framework_fitted.json").read_text())


def _ci_width(fv, is_pit, bucket, cred=0.90):
    c = vf.p_bucket_credible(fv, is_pit, cred=cred)
    return c[bucket]["hi"] - c[bucket]["lo"]


def test_bayes_posterior_committed() -> None:
    assert "bayes" in _FIT
    for k in ("theta_map", "cov", "data_fv_range", "map_params"):
        assert k in _FIT["bayes"]
    assert len(_FIT["bayes"]["theta_map"]) == 10                  # 2 slopes + 2*(base+3 incs)


def test_partial_pooling_shrinks_slopes_together() -> None:
    """The joint hierarchical MAP pulls the hitter and pitcher slopes toward each
    other relative to the independent MLEs (borrowing strength across roles)."""
    b = _FIT["bayes"]
    h_map, p_map = b["map_params"]["hitter"]["slope"], b["map_params"]["pitcher"]["slope"]
    h_mle, p_mle = b["indep_mle"]["hitter"]["slope"], b["indep_mle"]["pitcher"]["slope"]
    assert h_mle > p_mle                                          # hitter slope steeper than pitcher
    assert p_mle < p_map <= h_map < h_mle                         # both pulled inward
    assert abs(h_map - p_map) < abs(h_mle - p_mle)                # gap narrowed


def test_posterior_median_near_point_at_large_n() -> None:
    """Where the cell is well-sampled, the posterior median ~ the point estimate
    (the fit p_bucket_given_fv), per the validation requirement."""
    for fv in (50, 55):
        cred = vf.p_bucket_credible(fv, False, cred=0.90)
        point = vf.p_bucket_given_fv(fv, False)
        for i, bname in enumerate(vf._BUCKETS):
            assert cred[bname]["median"] == pytest.approx(point[i], abs=0.02)


def test_intervals_widen_for_thin_cells() -> None:
    """Pitcher cells are thinner (esp. n=12 at FV60) than hitter cells, so the
    credible intervals are wider for pitchers."""
    for fv in (55, 60):
        assert _ci_width(fv, True, "good") > _ci_width(fv, False, "good")


def test_intervals_widen_in_extrapolation() -> None:
    """Beyond the [45,60] data range the intervals widen (honest extrapolation)."""
    star = [_ci_width(fv, False, "star") for fv in (55, 60, 65, 70)]
    assert star == sorted(star) and star[-1] > 2 * star[0]
    bust = [_ci_width(fv, False, "bust") for fv in (45, 42, 38)]
    assert bust == sorted(bust)


def test_p_bucket_credible_well_ordered_and_valid() -> None:
    c = vf.p_bucket_credible(57, False, cred=0.90)
    med_sum = 0.0
    for bname in vf._BUCKETS:
        ci = c[bname]
        assert ci["lo"] <= ci["median"] <= ci["hi"]
        assert 0.0 <= ci["lo"] and ci["hi"] <= 1.0
        med_sum += ci["median"]
    assert med_sum == pytest.approx(1.0, abs=0.05)               # medians ~ sum to 1


def test_posterior_draws_are_valid_distributions() -> None:
    d = vf.p_bucket_posterior_draws(52.5, True, draws=1000)
    assert d.shape == (1000, 5)
    assert np.allclose(d.sum(axis=1), 1.0)
    assert (d >= 0).all()


def test_sv_credible_interval_brackets_point_and_widens() -> None:
    """The epistemic SV interval brackets the point estimate (positive width),
    and widens in extrapolation (FV70 wider than FV55)."""
    near = vf.sv_credible_interval(55, False, "SS", cred=0.90, age=22, eta_years=1)
    far = vf.sv_credible_interval(70, False, "SS", cred=0.90, age=22, eta_years=1)
    assert near["lo_mm"] < near["median_mm"] < near["hi_mm"]
    assert near["median_mm"] == pytest.approx(near["point_mm"], abs=2.0)
    near_w = near["hi_mm"] - near["lo_mm"]
    far_w = far["hi_mm"] - far["lo_mm"]
    assert far_w > near_w                                         # extrapolation -> wider


def test_sv_credible_interval_none_for_bad_fv() -> None:
    ci = vf.sv_credible_interval(None, False, "SS")
    assert ci["point_mm"] is None


def test_sv_credible_point_inside_interval_all_regimes() -> None:
    """The point estimate must lie inside its own credible interval at EVERY FV,
    including the Edwards anchor/bridge region (the interval mirrors the same
    anchor/bridge regime as the point), with a regime flag."""
    expected = {40: "anchor", 42: "bridge", 44: "bridge", 45: "pipeline", 55: "pipeline", 70: "pipeline"}
    for fv, reg in expected.items():
        ci = vf.sv_credible_interval(fv, False, "SS", cred=0.90, age=22, eta_years=1)
        assert ci["lo_mm"] <= ci["point_mm"] <= ci["hi_mm"], f"FV{fv}: point {ci['point_mm']} outside {ci}"
        assert ci["regime"] == reg
    # anchor region: degenerate interval (no parameter uncertainty in a fixed $ anchor)
    a = vf.sv_credible_interval(40, False, "SS", age=22, eta_years=1)
    assert a["lo_mm"] == a["hi_mm"] == a["point_mm"]


def test_means_still_reconcile_after_bayes() -> None:
    """The hierarchical-MAP point estimate still reconciles the weighted six-year
    avg WAR to the anchor at 50/55/60 (the Prompt-B calibration survives)."""
    tol = float(vf._config()["fit"]["reconcile_tol"])
    for fv in (50, 55, 60):
        target = vf.fv_to_6yr_avg_war(fv)   # v47 config anchor, not hardcoded
        for is_pit in (False, True):
            assert vf.expected_six_year_avg_war(fv, is_pit) == pytest.approx(target, abs=tol)
