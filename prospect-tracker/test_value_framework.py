# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Unit tests for value_framework v2 -- the career-path mixture model.

Covers the four overhaul validation requirements plus the supporting machinery:
  * Tiered $/WAR (per-season, convex) + present value
  * P(bucket|FV): smooth, monotone (stochastic dominance), sums to 1
  * RECONCILIATION: P(bucket|FV)-weighted six-year avg WAR matches the
    fv_to_6yr_avg_war anchor within tolerance (50->2.0, 55->2.5, 60->3.0; non-grid)
  * CONTINUITY & MONOTONICITY: expected SV continuous in FV (no jumps at grade
    boundaries) and non-decreasing
  * OLD-vs-NEW (Jensen): per-bucket decomposition; the mixture beats the
    collapsed point estimate where outcomes span the convex tier region; the
    star bucket has the highest surplus-per-WAR
  * WORKED EXAMPLE: re-trace the audit's non-grid FV (58.33) through every step
  * Preserved back-compat API (dollars_per_war, career_war_value_mm, ...)
  * Snapshot emitters round-trip
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import value_framework as vf

_TOL = float(vf._config()["fit"]["reconcile_tol"])
_GRID = [round(20.0 + 0.5 * i, 1) for i in range(int((80 - 20) / 0.5) + 1)]


# =============================================================================
# Tiered $/WAR + present value
# =============================================================================
def test_tiered_war_value_classifies_each_season_by_own_war() -> None:
    rates = vf._config()["dollars_per_war"]["tiered"]["rates"]
    assert vf.tiered_war_value_usd(0.5) == pytest.approx(0.5 * rates["lt_1"])
    assert vf.tiered_war_value_usd(1.5) == pytest.approx(1.5 * rates["1_to_2"])
    assert vf.tiered_war_value_usd(3.0) == pytest.approx(3.0 * rates["2plus"])
    assert vf.tiered_war_value_usd(0.0) == 0.0
    assert vf.tiered_war_value_usd(-1.0) == 0.0


def test_tiered_is_convex_star_costs_more_per_win() -> None:
    """A 3-WAR season values ABOVE 3x the flat rate (convex); a 0.5-WAR season
    below 0.5x flat. This is why a flat rate underprices stars."""
    flat = vf._flat_rate_usd()
    assert vf.tiered_war_value_usd(3.0) > 3.0 * flat
    assert vf.tiered_war_value_usd(0.5) < 0.5 * flat


def test_present_value_discounts_future_years() -> None:
    r = vf._config()["discount_rate"]
    assert vf.present_value(100.0, 0) == pytest.approx(100.0)
    assert vf.present_value(100.0, 1) == pytest.approx(100.0 / (1 + r))
    assert vf.present_value(100.0, 5) == pytest.approx(100.0 / (1 + r) ** 5)


# =============================================================================
# P(bucket|FV): valid distribution, smooth, monotone (stochastic dominance)
# =============================================================================
@pytest.mark.parametrize("is_pit", [False, True])
def test_p_bucket_sums_to_one_everywhere(is_pit: bool) -> None:
    for fv in _GRID:
        probs = vf.p_bucket_given_fv(fv, is_pit)
        assert len(probs) == 5
        assert all(p >= 0 for p in probs)
        assert sum(probs) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("is_pit", [False, True])
def test_p_bucket_stochastically_increasing_in_fv(is_pit: bool) -> None:
    """Higher FV must shift probability mass toward better outcomes: the
    cumulative P(Y > k) is non-decreasing in FV for every threshold k."""
    fvs = [40, 45, 50, 55, 60, 65]
    cdfs = []
    for fv in fvs:
        p = vf.p_bucket_given_fv(fv, is_pit)
        # survival P(Y>k) for k=0..3
        cdfs.append([sum(p[k + 1:]) for k in range(4)])
    for k in range(4):
        col = [c[k] for c in cdfs]
        assert col == sorted(col), f"P(Y>{k}) not non-decreasing in FV: {col}"


# =============================================================================
# VALIDATION 1 -- RECONCILIATION
# =============================================================================
@pytest.mark.parametrize("is_pit", [False, True])
@pytest.mark.parametrize("fv", [50, 55, 60])
def test_reconciliation_named_targets(is_pit: bool, fv: int) -> None:
    target = vf.fv_to_6yr_avg_war(fv)   # v47: config anchor (empirically recalibrated), not hardcoded
    got = vf.expected_six_year_avg_war(fv, is_pit)
    assert got == pytest.approx(target, abs=_TOL), \
        f"FV {fv} {'pit' if is_pit else 'hit'}: weighted avg WAR {got:.3f} != {target} (+-{_TOL})"


@pytest.mark.parametrize("is_pit", [False, True])
def test_reconciliation_non_grid_interpolated(is_pit: bool) -> None:
    """Non-grid FV 57 should land near the smoothly-interpolated anchor (~2.7)."""
    target = vf.fv_to_6yr_avg_war(57)
    got = vf.expected_six_year_avg_war(57, is_pit)
    assert got == pytest.approx(target, abs=_TOL + 0.1)


# =============================================================================
# VALIDATION 2 -- CONTINUITY & MONOTONICITY
# =============================================================================
@pytest.mark.parametrize("is_pit", [False, True])
def test_expected_sv_monotonic_in_fv(is_pit: bool) -> None:
    svs = [vf.surplus_value_mm(fv, is_pit, None) for fv in _GRID]
    for i in range(len(svs) - 1):
        assert svs[i] <= svs[i + 1] + 1e-6, \
            f"SV decreased {_GRID[i]}->{_GRID[i+1]}: {svs[i]} -> {svs[i+1]}"


@pytest.mark.parametrize("is_pit", [False, True])
def test_expected_sv_continuous_no_grade_jumps(is_pit: bool) -> None:
    """No discontinuous jump at grade boundaries. Across the fitted region the
    half-point steps are smooth and comparable in size (no kink/jump at 55, 60)."""
    fine = [round(45 + 0.5 * i, 1) for i in range(int((70 - 45) / 0.5) + 1)]
    diffs = []
    for i in range(len(fine) - 1):
        a = vf.expected_surplus_usd(fine[i], is_pit, None) / 1e6
        b = vf.expected_surplus_usd(fine[i + 1], is_pit, None) / 1e6
        diffs.append(b - a)
    # Every half-point step is a small, positive increment (continuous + monotone).
    assert max(diffs) < 6.0, f"jump too large in fitted region: max step {max(diffs):.2f}M"
    assert min(diffs) >= -1e-6


@pytest.mark.parametrize("is_pit", [False, True])
@pytest.mark.parametrize("c", [55, 60])
def test_no_jump_across_specific_grade_boundary(is_pit: bool, c: int) -> None:
    """54->55->56 (and 59->60->61): increments are gradual, not a step."""
    s = {d: vf.expected_surplus_usd(c + d, is_pit, None) / 1e6 for d in (-1, 0, 1)}
    inc_lo = s[0] - s[-1]
    inc_hi = s[1] - s[0]
    assert inc_lo >= -1e-6 and inc_hi >= -1e-6
    # The slope on either side of the boundary is comparable (no kink/jump).
    assert abs(inc_hi - inc_lo) < 3.0


# =============================================================================
# VALIDATION 3 -- OLD (collapsed) vs NEW (mixture): the Jensen gap
# =============================================================================
def test_per_bucket_decomposition_sums_to_expected() -> None:
    fv, is_pit, pos = 52.0, False, "CF"
    probs = vf.p_bucket_given_fv(fv, is_pit)
    svs = vf.bucket_surplus_usd(is_pit, pos, fv=fv)
    decomp = sum(p * svs[b] for p, b in zip(probs, vf._BUCKETS))
    # expected_surplus is the pipeline (no low-tail anchor at FV 52).
    assert decomp == pytest.approx(vf.expected_surplus_usd(fv, is_pit, pos), rel=1e-6)


def test_star_bucket_has_highest_surplus_per_war() -> None:
    """The convex tiered $/WAR + fixed pre-arb cost amortization mean the star
    outcome earns the most surplus PER WAR -- the mixture 'raises the star most'."""
    for is_pit in (False, True):
        svs = vf.bucket_surplus_usd(is_pit, None)
        mids = vf._calibrated_midpoints(vf._role_key(is_pit))
        per_war = [svs[b] / mids[i] for i, b in enumerate(vf._BUCKETS) if mids[i] > 0]
        assert per_war == sorted(per_war), f"surplus-per-WAR not rising to star: {per_war}"


def test_mixture_beats_collapsed_point_estimate_midfv() -> None:
    """Where outcomes span the convex tier region, E[f(X)] > f(E[X]): valuing the
    upside buckets at their OWN high WAR beats collapsing to one averaged WAR."""
    for fv, is_pit, pos in [(48, True, "SP"), (50, True, "SP"), (49, False, "OF")]:
        new = vf.expected_surplus_usd(fv, is_pit, pos)
        collapsed = vf.point_estimate_surplus_usd(fv, is_pit, pos)
        assert new > collapsed, f"FV {fv} pit={is_pit}: new {new} !> collapsed {collapsed}"


def test_new_model_raises_audit_worked_example_vs_v1() -> None:
    """v47 EMPIRICAL RECALIBRATION: the FV 58.33 SS prospect was $107.8M (v1) and
    ~$125M (pre-recal); it now reflects realized 2017-20 cohort outcomes blended
    with the public Edwards scale (~$45M at 58 FV) -- deliberately DE-inflated to a
    defensible, empirically-grounded magnitude rather than the prior 2-3x overshoot.
    v3 (surplus re-anchor): the $/WAR LEVEL now tracks the FA signings-implied
    series (open-market price of a win, ~1.34x the curated league-wide table),
    lifting the band proportionally — WAR-side calibration unchanged."""
    new = vf.surplus_value_mm(58.33, is_pitcher=False, position="SS")
    scale = (vf._config()["dollars_per_war"].get("_fa_reanchor") or {}).get("scale", 1.0)
    assert 25.0 * scale < new < 60.0 * scale


# =============================================================================
# VALIDATION 4 -- WORKED EXAMPLE (re-trace the audit's non-grid FV)
# =============================================================================
def test_worked_example_full_trace_58_33_ss() -> None:
    fv, is_pit, pos = 58.33, False, "SS"
    probs = vf.p_bucket_given_fv(fv, is_pit)
    svs = vf.bucket_surplus_usd(is_pit, pos, fv=fv)
    _ws = vf._war_scale_for(fv, vf._role_key(is_pit))
    mids = [m * _ws for m in vf._calibrated_midpoints(vf._role_key(is_pit))]

    # (a) probability vector is a valid distribution
    assert sum(probs) == pytest.approx(1.0, abs=1e-9)
    # (b) bucket surplus is ordered bust < bench < regular < good < star
    ordered = [svs[b] for b in vf._BUCKETS]
    assert ordered == sorted(ordered)
    assert svs["bust"] == 0.0
    # (c) every intermediate present and finite
    contribs = {b: probs[i] * svs[b] for i, b in enumerate(vf._BUCKETS)}
    total_usd = sum(contribs.values())
    # (d) weighted six-year avg WAR reconciles near the interpolated anchor (~2.83)
    wavg = sum(p * m for p, m in zip(probs, mids))
    assert wavg == pytest.approx(vf.fv_to_6yr_avg_war(fv), abs=_TOL + 0.1)
    # (e) the assembled expected surplus matches the public API to the cent
    assert total_usd == pytest.approx(vf.expected_surplus_usd(fv, is_pit, pos), rel=1e-9)
    assert round(total_usd / 1e6, 1) == vf.surplus_value_mm(fv, is_pit, pos)
    # sanity: this premium prospect lands in a defensible band (v47 WAR-side
    # calibration; v3 scales the band by the FA-implied $/WAR re-anchor)
    scale = (vf._config()["dollars_per_war"].get("_fa_reanchor") or {}).get("scale", 1.0)
    assert 25.0 * scale < vf.surplus_value_mm(fv, is_pit, pos) < 60.0 * scale


# =============================================================================
# Position: NO double-count (WAR already contains the positional adjustment)
# =============================================================================
def test_position_does_not_apply_dollar_multiplier_by_default() -> None:
    """SS and 1B at the same FV/role value EQUALLY -- the old AAV-derived
    positional $ multiplier (which double-counted WAR's positional adjustment)
    is gone (docs/sv-audit.md FLAG 7)."""
    assert vf.surplus_value_mm(55, False, "SS") == vf.surplus_value_mm(55, False, "1B")
    assert vf.position_multiplier("SS") == 1.0
    assert vf.position_multiplier("1B") == 1.0


def test_reliever_war_haircut_lowers_value_vs_starter() -> None:
    """Relievers value BELOW starters at the same FV -- via the role-outcome
    layer's bullpen WAR normalization/ceiling (a WAR-INPUT correction), NOT a
    position $ multiplier. (See test_pitcher_roles.py for the full layer.)"""
    sp = vf.surplus_value_mm(55, True, "SP")
    rp = vf.surplus_value_mm(55, True, "RP")
    assert rp < sp


# =============================================================================
# FV <= 40 dollar anchor (Edwards)
# =============================================================================
def test_fv40_position_player_matches_edwards_anchor() -> None:
    anchor_mm = vf._config()["lowtier_anchor"]["anchor_usd_40fv_position"] / 1e6
    assert vf.surplus_value_mm(40, False, "OF") == pytest.approx(anchor_mm, abs=0.2)


def test_low_fv_is_small_and_floored_nonnegative() -> None:
    for g in (20, 25, 30, 35, 40):
        s = vf.surplus_value_mm(g, False, "OF")
        assert s is not None and s >= 0.0
        assert s <= 5.0


# =============================================================================
# Preserved back-compat API
# =============================================================================
def test_surplus_returns_none_for_missing_fv() -> None:
    assert vf.surplus_value_mm(None, False, None) is None
    assert vf.dollars_per_fv(None, False, None) is None


def test_non_finite_and_bad_inputs_degrade_to_none() -> None:
    """Every public FV API degrades to None (never NaN/inf or a raised
    exception) on missing / unparseable / non-finite FV -- a uniform contract
    across the dollar APIs AND p_bucket_given_fv / expected_six_year_avg_war."""
    bad = [None, "garbage", [], {}, float("nan"), float("inf"), float("-inf")]
    for b in bad:
        assert vf.surplus_value_mm(b, False, "SS") is None
        assert vf.expected_surplus_usd(b, False, "SS") is None
        assert vf.point_estimate_surplus_usd(b, False, None) is None
        assert vf.dollars_per_fv(b, False, None) is None
        assert vf.fv_to_6yr_avg_war(b) is None
        assert vf.p_bucket_given_fv(b, False) is None
        assert vf.expected_six_year_avg_war(b, False) is None


# =============================================================================
# SV DISTRIBUTION (Monte Carlo) -- the standard output contract
# =============================================================================
@pytest.mark.parametrize("fv,is_pit,pos", [
    (58.33, False, "SS"), (47, True, "SP"), (52, False, "CF"),
    (63, False, None), (42, False, "OF"), (55, True, "RP"),
])
def test_distribution_mean_equals_point_estimate(fv, is_pit, pos) -> None:
    """The distribution's reported mean equals the prior point-estimate SV
    exactly, and the Monte Carlo sample mean tracks it (mean-preserving Gamma)."""
    out = vf.sv_distribution(fv, is_pit, pos)
    assert out is not None
    # surplus_value_mm rounds to 1 dp, the distribution mean to 2 dp -> allow the
    # half-cent rounding gap.
    assert out["mean"] == pytest.approx(vf.surplus_value_mm(fv, is_pit, pos), abs=0.06)
    assert out["mc_mean"] == pytest.approx(out["mean"], rel=0.03, abs=0.5)


@pytest.mark.parametrize("fv,is_pit", [(58.33, False), (47, True), (63, False), (50, True)])
def test_distribution_percentiles_monotone(fv, is_pit) -> None:
    out = vf.sv_distribution(fv, is_pit, None)
    ps = list(out["percentiles"].values())
    assert ps == sorted(ps), f"percentiles not monotone: {out['percentiles']}"


def test_distribution_probabilities_and_downside() -> None:
    out = vf.sv_distribution(55, False, "SS")
    assert 0.0 <= out["p_bust"] <= 1.0
    assert 0.0 <= out["p_above_threshold"] <= 1.0
    # CVaR of the worst quartile must sit at or below the mean.
    assert out["downside_metric"] <= out["mean"]
    # p_bust is the analytic bucket-0 probability (reported rounded to 4 dp).
    assert out["p_bust"] == pytest.approx(vf.p_bucket_given_fv(55, False)[0], abs=1e-4)
    # Higher-FV prospect has lower bust probability (stochastic dominance).
    assert vf.sv_distribution(60, False, None)["p_bust"] < vf.sv_distribution(48, False, None)["p_bust"]


def test_distribution_none_for_bad_fv() -> None:
    for b in (None, "x", float("nan"), float("inf")):
        assert vf.sv_distribution(b, False, None) is None


def test_risk_lambda_zero_reproduces_mean_ranking() -> None:
    """lambda = 0 => the risk-adjusted score IS the mean, so ranking by score
    is identical to ranking by mean."""
    fvs = [45, 48, 50, 55, 60, 65]
    means = [vf.sv_distribution(fv, False, None)["mean"] for fv in fvs]
    scores = [vf.sv_distribution(fv, False, None, risk_lambda=0.0)["risk_adjusted_score"] for fv in fvs]
    assert scores == means
    order_score = sorted(range(len(fvs)), key=lambda i: scores[i])
    order_mean = sorted(range(len(fvs)), key=lambda i: means[i])
    assert order_score == order_mean


def test_equal_mean_different_risk_ranks_differently() -> None:
    """Two prospects with EQUAL mean but different downside: identical score at
    lambda = 0, but the riskier (lower-CVaR) one ranks below once lambda > 0."""
    m = 100.0
    # lambda = 0 -> identical
    assert vf.risk_adjusted_score(m, 80.0, 0.0) == vf.risk_adjusted_score(m, 40.0, 0.0) == m
    # lambda > 0 -> the one with worse downside (CVaR 40 < 80) scores lower
    safe = vf.risk_adjusted_score(m, 80.0, 0.5)
    risky = vf.risk_adjusted_score(m, 40.0, 0.5)
    assert risky < safe
    # monotone in lambda for a prospect with real downside
    d = vf.sv_distribution(60, False, "SS")
    s0 = vf.risk_adjusted_score(d["mean"], d["downside_metric"], 0.0)
    s1 = vf.risk_adjusted_score(d["mean"], d["downside_metric"], 0.5)
    assert s0 == d["mean"] and s1 <= s0


def test_equal_mean_different_risk_reorders_through_distribution() -> None:
    """End-to-end (not just the scalar score fn): two prospects with the SAME
    consensus FV -> EXACTLY equal mean, but different source spread (Prompt I)
    -> different downside. They tie on risk_adjusted_score at lambda=0 and the
    contested (wider, worse-CVaR) one ranks strictly below once lambda>0."""
    tight = lambda lam: vf.sv_distribution(52, False, "SS", source_fvs={"a": 51, "b": 52, "c": 53},
                                           risk_lambda=lam, seed=5)
    wide = lambda lam: vf.sv_distribution(52, False, "SS", source_fvs={"a": 44, "b": 52, "c": 60},
                                          risk_lambda=lam, seed=5)
    t0, w0 = tight(0.0), wide(0.0)
    assert t0["mean"] == pytest.approx(w0["mean"], abs=1e-9)          # identical consensus mean
    assert w0["downside_metric"] <= t0["downside_metric"]             # contested has worse downside
    assert t0["risk_adjusted_score"] == pytest.approx(w0["risk_adjusted_score"], abs=1e-9)  # tie at 0
    t5, w5 = tight(0.5), wide(0.5)
    assert t5["risk_adjusted_score"] > w5["risk_adjusted_score"]      # reorder once lambda>0


def test_risk_lambda_can_reverse_mean_ranking() -> None:
    """The knob can FLIP the order: a higher-mean but heavily contested prospect A
    leads by mean (lambda=0) yet falls below a safer, slightly lower-mean prospect
    B once downside is penalized (lambda>0)."""
    A = lambda lam: vf.sv_distribution(61, False, "SS", source_fvs={"x": 50, "y": 61, "z": 72},
                                       risk_lambda=lam, seed=2)
    B = lambda lam: vf.sv_distribution(59, False, "SS", source_fvs={"x": 58, "y": 59, "z": 60},
                                       risk_lambda=lam, seed=2)
    a0, b0 = A(0.0), B(0.0)
    assert a0["mean"] > b0["mean"]                                    # A wins on mean
    assert a0["risk_adjusted_score"] > b0["risk_adjusted_score"]      # ... and at lambda=0
    a6, b6 = A(1.5), B(1.5)   # v47: recalibration moved the crossover to ~1.0
    assert b6["risk_adjusted_score"] > a6["risk_adjusted_score"]      # safer B overtakes at lambda>0


# =============================================================================
# TIMING -- ETA / age / $/WAR inflation
# =============================================================================
def test_later_debut_lowers_present_value() -> None:
    """Two identical-FV prospects with different ETAs/ages produce MATERIALLY
    different PVs; the more distant debut (longer ETA) is worth less."""
    near = vf.surplus_value_mm(55, False, "SS", age=24, eta_years=1)   # AAA, debuts soon
    far = vf.surplus_value_mm(55, False, "SS", age=19, eta_years=4)    # A-ball, distant
    assert far < near
    assert far < 0.95 * near                                          # material, not rounding


def test_pv_monotone_decreasing_in_eta() -> None:
    """At fixed age, more years to debut => more discounting => lower PV."""
    vals = [vf.surplus_value_mm(55, False, "SS", age=22, eta_years=e) for e in (0, 1, 2, 3, 4)]
    for i in range(len(vals) - 1):
        assert vals[i + 1] <= vals[i] + 1e-9, f"PV rose with ETA: {vals}"
    assert vals[-1] < vals[0]


def test_inflation_raises_value_vs_no_inflation() -> None:
    """Projecting $/WAR forward (net against the discount rate) lifts PV vs
    applying today's rate flat -- inflation lowers the effective discount."""
    cfg = vf._config()
    saved = cfg["dollars_per_war_inflation"]
    try:
        cfg["dollars_per_war_inflation"] = 0.0
        vf._bucket_sv_usd.cache_clear()
        off = vf.surplus_value_mm(60, False, "SS")
        cfg["dollars_per_war_inflation"] = 0.05
        vf._bucket_sv_usd.cache_clear()
        on = vf.surplus_value_mm(60, False, "SS")
    finally:
        cfg["dollars_per_war_inflation"] = saved
        vf._bucket_sv_usd.cache_clear()
    assert on > off


def test_disabling_timing_reproduces_flat_behavior() -> None:
    """Disabling inflation + debut-based discounting + aging makes surplus
    INVARIANT to age/ETA (the prior timing-flat behavior) and reproduces the
    recalibrated flat value (FV 60 SS = 48.5)."""
    cfg = vf._config()
    saved = (cfg["dollars_per_war_inflation"], cfg["discount_from"], cfg["aging"]["enabled"])
    try:
        cfg["dollars_per_war_inflation"] = 0.0
        cfg["discount_from"] = "now"
        cfg["aging"]["enabled"] = False
        vf._bucket_sv_usd.cache_clear()
        v_noargs = vf.surplus_value_mm(60, False, "SS")
        v_young = vf.surplus_value_mm(60, False, "SS", age=19, eta_years=4)
        v_old = vf.surplus_value_mm(60, False, "SS", age=30, eta_years=0)
        assert v_noargs == v_young == v_old                    # timing has NO effect (flat)
        # The flat value tracks the (hierarchical-MAP) point estimate. v44 lifted
        # the $/WAR tiers to the trailing 3-yr average (2024-26), so the 60-FV
        # flat surplus rose ~6% (the 2plus tier firmed up) to ~140 from the old
        # ~132.5; range widened to absorb future annual re-averages + G pooling.
        # v3 (re-anchor): the band scales by the FA-implied level shift.
        scale = (cfg["dollars_per_war"].get("_fa_reanchor") or {}).get("scale", 1.0)
        assert 44.0 * scale <= v_noargs <= 54.0 * scale   # v47 recalibration (~48.5 pre-anchor)
    finally:
        (cfg["dollars_per_war_inflation"], cfg["discount_from"], cfg["aging"]["enabled"]) = saved
        vf._bucket_sv_usd.cache_clear()


def test_distribution_threads_timing() -> None:
    """The distribution contract honors timing: a distant prospect's mean is
    lower and still equals its (timing-adjusted) point estimate."""
    near = vf.sv_distribution(55, False, "SS", age=24, eta_years=1)
    far = vf.sv_distribution(55, False, "SS", age=19, eta_years=4)
    assert far["mean"] < near["mean"]
    assert far["mean"] == pytest.approx(
        vf.surplus_value_mm(55, False, "SS", age=19, eta_years=4), abs=0.2)


def test_aging_shape_preserves_six_year_average_war() -> None:
    """Aging only REDISTRIBUTES WAR across the control window: the six-year
    average still equals the calibrated bucket midpoint for ANY debut age (the
    shape is renormalized to mean 1.0), so anchor reconciliation is timing-
    invariant even as the per-season trajectory tilts up (young) or down (old)."""
    ny = int(vf._config()["service_time"]["control_years"])
    for role in ("hitter", "pitcher"):
        mids = vf._calibrated_midpoints(role)
        for b in range(vf._N_BUCKETS):
            for da in (None, 19, 23, 27, 31, 34):
                wars = vf._bucket_season_wars(role, b, False, da)
                assert sum(wars) / ny == pytest.approx(mids[b], abs=1e-9)


def test_aging_shape_moves_pv_at_constant_eta() -> None:
    """REQ: with FV and ETA held FIXED, age-at-debut still moves PV -- the aging
    curve places the six control years differently on the WAR trajectory (and on
    the convex $/WAR tiers). A young, still-climbing debut back-loads WAR into
    more-discounted seasons -> lower PV than an older, front-loaded (declining)
    debut. This isolates the aging-SHAPE effect from the ETA-gap discount."""
    young = vf.surplus_value_mm(55, False, "SS", age=19, eta_years=0)
    older = vf.surplus_value_mm(55, False, "SS", age=31, eta_years=0)
    assert young != older
    assert older > young


def test_jensen_gap_direction_is_fv_dependent() -> None:
    """Honest direction check (the v1 'uniform positive, star-driven' claim was
    wrong): the mixture beats the collapsed point estimate in the mid-FV band
    where outcomes straddle the convex $/WAR tiers, and the advantage fades at
    high FV where all mass sits in the flat 2+ tier."""
    mid = (vf.expected_surplus_usd(48, True, "SP")
           - vf.point_estimate_surplus_usd(48, True, "SP"))
    assert mid > 0, "mid-FV Jensen gap should be positive"
    # At high FV the gap is small in magnitude relative to the value (no large
    # uniform star premium); just assert it's bounded, not that it's positive.
    hi_new = vf.expected_surplus_usd(65, False, None)
    hi_old = vf.point_estimate_surplus_usd(65, False, None)
    assert abs(hi_new - hi_old) < 0.1 * hi_new


def test_dollars_per_war_rate_tiers_in_mm() -> None:
    rates = vf._config()["dollars_per_war"]["tiered"]["rates"]
    assert vf.dollars_per_war(0.5) == pytest.approx(rates["lt_1"] / 1e6)
    assert vf.dollars_per_war(1.5) == pytest.approx(rates["1_to_2"] / 1e6)
    assert vf.dollars_per_war(3.0) == pytest.approx(rates["2plus"] / 1e6)
    assert vf.dollars_per_war(None) == pytest.approx(rates["lt_1"] / 1e6)


def test_dollars_per_war_flat_and_career_value() -> None:
    flat_mm = vf._flat_rate_usd() / 1e6
    assert vf.dollars_per_war_flat() == pytest.approx(flat_mm)
    assert vf.career_war_value_mm(10.0) == pytest.approx(10.0 * flat_mm, abs=0.05)
    assert vf.career_war_value_mm(0.0) is None
    assert vf.career_war_value_mm(None) is None
    assert vf.career_war_value_mm(-3.0) is None


def test_is_pitcher_and_reliever_position() -> None:
    for p in ("SP", "RP", "RHP", "LHP", "MIRP", "SIRP", "P"):
        assert vf.is_pitcher_position(p) is True
    for p in ("SS", "C", "1B", "OF", "DH", None, ""):
        assert vf.is_pitcher_position(p) is False
    assert vf.is_pitcher_position("RHP/SP") is True
    assert vf.is_reliever_position("RP") is True
    assert vf.is_reliever_position("SP") is False


def test_dollars_per_fv_distinct_for_non_grid() -> None:
    d47 = vf.dollars_per_fv(47, False, None)
    d50 = vf.dollars_per_fv(50, False, None)
    assert d47 is not None and d50 is not None
    assert abs(d47 - d50) > 0.01


# =============================================================================
# Snapshot emitters
# =============================================================================
def test_build_snapshot_has_required_keys() -> None:
    snap = vf.build_snapshot()
    for k in ("version", "model", "sources", "dollars_per_war", "discount_rate",
              "buckets", "bucket_midpoints", "bucket_surplus_mm", "fv_to_6yr_avg_war",
              "sv_curve", "position", "service_time", "fit"):
        assert k in snap, f"snapshot missing {k}"
    assert snap["model"] == "career-path-mixture"
    assert len(snap["sv_curve"]["hitter"]) == len(snap["sv_curve"]["pitcher"])
    assert "reliever" in snap["sv_curve"]


def test_sv_curve_matches_engine() -> None:
    """The dense precomputed curve the frontend reads must equal the engine."""
    snap = vf.build_snapshot()
    c = snap["sv_curve"]
    for i, sv in enumerate(c["hitter"]):
        fv = c["fv_min"] + i * c["step"]
        assert sv == pytest.approx(round((vf.expected_surplus_usd(fv, False, None) or 0) / 1e6, 4))


def test_emit_snapshots_roundtrip(tmp_path: Path) -> None:
    jp, jsp = vf.emit_snapshots(out_dir=tmp_path)
    assert jp.exists() and jsp.exists()
    snap = json.loads(jp.read_text(encoding="utf-8"))
    assert snap["version"] == vf.FRAMEWORK_VERSION
    js = jsp.read_text(encoding="utf-8")
    assert "window.VALUE_FRAMEWORK = " in js
    body = js.split("window.VALUE_FRAMEWORK = ", 1)[1].rstrip().rstrip(";")
    assert json.loads(body) == snap


def test_parallel_lines_diagnostic_recorded() -> None:
    snap = vf.build_snapshot()
    diag = snap["fit"]["parallel_lines_diagnostic"]
    for role in ("hitter", "pitcher"):
        assert "passed" in diag[role]
        assert "spread" in diag[role]
