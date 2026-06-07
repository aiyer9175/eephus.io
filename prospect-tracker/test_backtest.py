# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the backtest & calibration harness (Prompt F).

Validates the harness MACHINERY (the repo has no real completed-window data):
  * Step-1 reconstruction hand-checked against a manual control-window calc
  * structural NO LOOK-AHEAD (prediction path cannot see realized data)
  * continuity: a never-debuted player reconstructs to realized SV = 0
  * held-out-only cross-validated correction; bias collapses out-of-sample
  * the harness RECOVERS an injected shrinkage (overshoot; monotone in shrink)
  * the production calibration config stays IDENTITY (no real fit committed)
"""

from __future__ import annotations

import numpy as np
import pytest

import backtest as bt
import value_framework as vf

_R = float(vf._config()["discount_rate"])
_INFL = float(vf._config()["dollars_per_war_inflation"])
# The synthetic self-test values realized with the model's own convention
# (tiered $/WAR + inflation), so the only injected difference is the WAR-shrink.
_SYNTH = {"tiered": True, "inflation": _INFL}


# =============================================================================
# Step 1 -- realized reconstruction hand-check
# =============================================================================
def test_realized_reconstruction_matches_manual_calc() -> None:
    """Hand-checked: a 3-pre-arb + 3-arb control window, valued at a flat
    $10M/WAR, league-min $0.75M pre-arb, actual salaries in arb, discounted 9%
    from the listing year (debut = listing+1)."""
    dpw = {y: {"overall": 10.0} for y in range(2014, 2025)}
    seasons = tuple(
        bt.RealizedSeason(year=2015 + k, fwar=2.0,
                          salary_mm=(0.75 if k < 3 else [4.0, 6.0, 8.0][k - 3]),
                          service_days=172.0)
        for k in range(6)
    )
    rec = bt.RealizedRecord("p", debut_year=2015, seasons=seasons)
    got = bt.realized_sv_pv(rec, listing_year=2014, discount_rate=0.09, dpw_by_year=dpw)
    # Manual: each season value = 2.0*10 - salary = 20 - salary; discounted by
    # 1.09**(year-2014), year-2014 = 1..6.
    manual = 0.0
    sal = [0.75, 0.75, 0.75, 4.0, 6.0, 8.0]
    for k in range(6):
        manual += (2.0 * 10.0 - sal[k]) / (1.09 ** (2015 + k - 2014))
    assert got == pytest.approx(manual, abs=1e-6)


def test_never_debuted_reconstructs_to_zero() -> None:
    rec = bt.RealizedRecord("p", debut_year=None, seasons=())
    assert bt.realized_sv_pv(rec, 2014, discount_rate=_R, dpw_by_year={}) == 0.0


def test_realized_negative_not_floored() -> None:
    """A player paid against ~0 WAR has genuinely negative realized SV (no floor)."""
    dpw = {y: {"overall": 10.0} for y in range(2014, 2025)}
    seasons = tuple(bt.RealizedSeason(2015 + k, 0.0, 0.75, 172.0) for k in range(6))
    rec = bt.RealizedRecord("p", 2015, seasons)
    assert bt.realized_sv_pv(rec, 2014, discount_rate=0.09, dpw_by_year=dpw) < 0


def test_release_ends_control_window() -> None:
    dpw = {y: {"overall": 10.0} for y in range(2014, 2025)}
    seasons = tuple(bt.RealizedSeason(2015 + k, 2.0, 0.75, 172.0) for k in range(6))
    full = bt.realized_sv_pv(bt.RealizedRecord("p", 2015, seasons), 2014, discount_rate=0.09, dpw_by_year=dpw)
    rel = bt.realized_sv_pv(bt.RealizedRecord("p", 2015, seasons, released_year=2017), 2014,
                            discount_rate=0.09, dpw_by_year=dpw)
    assert rel < full                                  # later years drop out


def test_service_time_caps_window_at_six_years() -> None:
    """Only 6 service years count; a 7th season contributes nothing."""
    dpw = {y: {"overall": 10.0} for y in range(2014, 2026)}
    seasons = tuple(bt.RealizedSeason(2015 + k, 2.0, 0.75, 172.0) for k in range(7))
    six = bt.realized_sv_pv(bt.RealizedRecord("p", 2015, seasons[:6]), 2014, discount_rate=0.09, dpw_by_year=dpw)
    seven = bt.realized_sv_pv(bt.RealizedRecord("p", 2015, seasons), 2014, discount_rate=0.09, dpw_by_year=dpw)
    assert seven == pytest.approx(six, abs=1e-9)       # 7th year excluded (FA)


# =============================================================================
# Step 2 -- structural no look-ahead
# =============================================================================
def test_no_lookahead_structural() -> None:
    bt.assert_no_lookahead(bt.predict_listing)         # raises if violated


def test_listing_view_has_no_realized_fields() -> None:
    from dataclasses import fields
    lv = {f.name for f in fields(bt.ListingView)}
    rv = {f.name for f in fields(bt.RealizedRecord)} | {f.name for f in fields(bt.RealizedSeason)}
    assert (lv & rv) <= {"player_id"}                  # only the join key may overlap
    for leak in ("fwar", "salary_mm", "debut_year", "seasons", "service_days"):
        assert leak not in lv


def test_prediction_uses_only_listing_inputs() -> None:
    """predict_listing on a ListingView returns a finite prediction without any
    realized object in scope."""
    lv = bt.ListingView("x", "x", 2015, 55.0, False, "SS", 22.0, 1.5, True)
    out = bt.predict_listing(lv, draws=500)
    assert out["pred_mm"] > 0 and np.isfinite(out["pred_mm"])
    assert out["draws_mm"].shape[0] == 500


# =============================================================================
# Step 3/4 -- metrics + correction on a synthetic cohort with KNOWN shrinkage
# =============================================================================
@pytest.fixture(scope="module")
def synth():
    # inject_shrink 0.6 (a clear 40%-optimistic model). Raw mean-PIT detection of
    # optimism is skew-fragile: prospect surplus is heavily right-skewed (large bust
    # mass at $0 + a long upside tail), so a MILD shrink can leave a shrunk-realized
    # value above the predicted median -> PIT ~ 0.5. A clearer shrink keeps the
    # validation robust to that skew (the CV-bias tests are the primary detectors).
    recs, dpw = bt.make_synthetic_cohort(seed=7, inject_shrink=0.6, n_per_year=160)
    pre = [x for x in recs if x.listing.pre_debut]
    preds = [bt.predict_listing(x.listing, draws=1500) for x in pre]
    realized = np.array([bt.realized_sv_pv(x.realized, x.listing.listing_year,
                                           discount_rate=_R, dpw_by_year=dpw, **_SYNTH) for x in pre])
    pred = np.array([p["pred_mm"] for p in preds])
    return {"recs": pre, "preds": preds, "realized": realized, "pred": pred, "dpw": dpw}


def test_self_test_is_fair_at_zero_shrink() -> None:
    """With NO injected shrink, the harness must NOT fabricate a correction:
    realized and predicted share the model's pricing convention, so cohort bias
    ≈ 0 (any residual is tier-convexity/noise, not a $/WAR-convention artifact)."""
    recs, dpw = bt.make_synthetic_cohort(seed=7, inject_shrink=1.0, high_fv_extra_shrink=0.0, n_per_year=200)
    pre = [x for x in recs if x.listing.pre_debut]
    pred = np.array([bt.predict_listing(x.listing, draws=600)["pred_mm"] for x in pre])
    real = np.array([bt.realized_sv_pv(x.realized, x.listing.listing_year,
                                       discount_rate=_R, dpw_by_year=dpw, **_SYNTH) for x in pre])
    bias = float((real - pred).mean())
    assert abs(bias) < 6.0, f"no-shrink bias {bias:.1f}M should be ~0 (fair self-test)"


def test_harness_recovers_overshoot(synth) -> None:
    """The raw model overshoots realized: binned slope < 1 and bias < 0."""
    binned = bt.binned_calibration(synth["pred"], synth["realized"])
    assert binned["slope"] < 1.0
    assert synth["realized"].mean() < synth["pred"].mean()       # overshoot


def test_recovered_shrinkage_monotone_in_injected_shrink() -> None:
    """Stronger injected shrink => lower recovered calibration slope and more
    negative bias -- the harness tracks the ground-truth correction."""
    slopes, biases = [], []
    for s in (0.5, 0.7, 0.9):
        recs, dpw = bt.make_synthetic_cohort(seed=7, inject_shrink=s, n_per_year=160)
        pre = [x for x in recs if x.listing.pre_debut]
        pred = np.array([bt.predict_listing(x.listing, draws=400)["pred_mm"] for x in pre])
        real = np.array([bt.realized_sv_pv(x.realized, x.listing.listing_year,
                                           discount_rate=_R, dpw_by_year=dpw, **_SYNTH) for x in pre])
        slopes.append(bt.binned_calibration(pred, real)["slope"])
        biases.append(float((real - pred).mean()))
    assert slopes[0] < slopes[1] < slopes[2]                     # 0.5 < 0.7 < 0.9
    assert biases[0] < biases[1] < biases[2]                     # more shrink -> more negative bias


def test_cross_validated_correction_removes_bias(synth) -> None:
    """The leave-one-year-out correction is fit on held-out years and collapses
    the bias toward 0 out-of-sample (isotonic, the conditional-mean map)."""
    cv = bt.leave_one_year_out_cv(synth["recs"], synth["preds"],
                                  discount_rate=_R, dpw_by_year=synth["dpw"], method="isotonic", **_SYNTH)
    assert abs(cv["held_out_bias"]) < 5.0                        # raw bias was strongly negative
    assert cv["n_held_out"] > 100
    # The affine-recalibrated held-out PIT is no longer degenerate (coverage was
    # 1.00 with a location-only shift); it lands in a sane band near ~0.80.
    cov = cv["held_out_pit"]["coverage_p10_p90"]
    assert 0.5 <= cov <= 0.95


def test_cv_metrics_are_held_out_only(synth) -> None:
    """The CV fits exclude the evaluated year (years list present; held-out n < total)."""
    cv = bt.leave_one_year_out_cv(synth["recs"], synth["preds"],
                                  discount_rate=_R, dpw_by_year=synth["dpw"], method="linear", **_SYNTH)
    assert len(cv["years"]) >= 2
    assert cv["n_held_out"] <= len(synth["recs"])


def test_pit_in_unit_interval_and_coverage(synth) -> None:
    pits = np.array([bt.pit_value(p["draws_mm"], rv)
                     for p, rv in zip(synth["preds"], synth["realized"])])
    assert (pits >= 0).all() and (pits <= 1).all()
    # Raw (uncorrected) PITs should pile LOW (model optimistic -> realized below predicted).
    assert pits.mean() < 0.5


def test_isotonic_correction_is_monotone_and_rank_preserving() -> None:
    pred = np.array([10.0, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    realized = np.array([8.0, 14, 19, 22, 28, 30, 33, 35, 36, 38])    # overshoot, monotone
    corr = bt.fit_isotonic_correction(pred, realized)
    mapped = [bt.apply_correction(corr, x) for x in pred]
    assert mapped == sorted(mapped)                              # monotone -> rank preserved


def test_linear_fit_recovers_known_slope() -> None:
    """Unit check of the fit on clean (low-noise) data: recovers the slope."""
    rng = np.random.RandomState(0)
    pred = np.linspace(10, 200, 400)
    realized = 0.6 * pred + 5 + rng.normal(0, 3, pred.size)
    corr = bt.fit_linear_correction(pred, realized)
    assert corr["slope"] == pytest.approx(0.6, abs=0.05)
    assert corr["intercept_mm"] == pytest.approx(5.0, abs=3.0)


def test_sensitivity_dominated_by_dpw_and_discount() -> None:
    rows = bt.sensitivity_table()
    top2 = {r["param"] for r in rows[:2]}
    assert top2 & {"dpw_2plus", "dpw_1_to_2", "dpw_lt_1", "discount_rate"}, top2


# =============================================================================
# Production config stays identity (no real-data correction committed)
# =============================================================================
def test_calibration_config_is_identity() -> None:
    cal = vf._config()["calibration"]
    assert cal["enabled"] is False
    assert vf.apply_calibration(123.4) == 123.4         # identity passthrough


def test_apply_calibration_linear_when_enabled() -> None:
    cfg = vf._config()
    saved = dict(cfg["calibration"])
    try:
        cfg["calibration"] = {"enabled": True, "method": "linear",
                              "linear": {"slope": 0.5, "intercept_mm": 2.0}}
        assert vf.apply_calibration(100.0) == pytest.approx(52.0)
    finally:
        cfg["calibration"] = saved
