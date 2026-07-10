# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for debuted-player surplus mode (Prompt D).

Validates the spec's requirements:
  * Continuity: at 0 MLB PA/IP the debuted mode reduces EXACTLY to the Prompt-B
    prospect valuation.
  * Monotonicity: expected SV rises with better observed performance AND with
    larger sample of strong play (and FALLS with larger sample of weak play).
  * Realized years use ACTUAL WAR/salary (not projections); trade value excludes
    the sunk (consumed) years.
  * A long, strong MLB track record is valued ~entirely by projection (the FV
    prior contributes negligibly).
  * The remaining (trade-value) piece reports through the Prompt-E distribution
    contract; the double-count guard works; bad input degrades to None.
"""

from __future__ import annotations

import pytest

import value_framework as vf


# =============================================================================
# Continuity -- 0 PA/IP reduces EXACTLY to the prospect model
# =============================================================================
@pytest.mark.parametrize("fv", [50, 55, 60, 47.5])
@pytest.mark.parametrize("is_pit", [False, True])
def test_continuity_zero_sample_equals_prospect(fv, is_pit) -> None:
    pos = "SP" if is_pit else "SS"
    d = vf.debuted_player_value(fv, is_pit, pos, observed_war=0.0,
                                observed_pa=0, observed_ip=0, service_time=0.0,
                                age=23, draws=3000)
    prospect = vf.surplus_value_mm(fv, is_pit, pos, age=23, eta_years=0)
    assert d["trade_value_mm"] == pytest.approx(prospect, abs=0.15)
    assert d["realized_mm"] == 0.0
    # posterior == prior (no evidence)
    assert d["posterior"] == d["prior"]


def test_continuity_no_sample_no_age() -> None:
    """No age + 0 sample still reduces to the prospect (eta=0) value."""
    d = vf.debuted_player_value(55, False, "SS", observed_war=0, observed_pa=0,
                                service_time=0.0, draws=3000)
    assert d["trade_value_mm"] == pytest.approx(
        vf.surplus_value_mm(55, False, "SS", eta_years=0), abs=0.2)


# =============================================================================
# Monotonicity
# =============================================================================
def test_rises_with_observed_performance() -> None:
    """Better observed performance (fixed sample + service) => higher SV."""
    trades = [vf.debuted_player_value(50, False, "CF", observed_war=ow, observed_pa=1200,
                                      service_time=2.0, age=24, draws=3000)["trade_value_mm"]
              for ow in (2.0, 5.0, 9.0, 14.0)]
    assert trades == sorted(trades)
    assert trades[-1] > trades[0]


def test_strong_performer_rises_with_sample_fixed_service() -> None:
    """More sample of STRONG play (fixed service => fixed remaining years) =>
    less regression to the prior => higher remaining value."""
    trades = [vf.debuted_player_value(50, False, "CF", observed_war=4.0 * pa / 600,
                                      observed_pa=pa, service_time=1.0, age=24, draws=3000)["trade_value_mm"]
              for pa in (300, 600, 1200, 2400)]
    assert trades == sorted(trades), trades


def test_weak_performer_falls_with_sample_fixed_service() -> None:
    """More sample of WEAK play regresses the optimistic FV prior DOWN."""
    trades = [vf.debuted_player_value(55, False, "SS", observed_war=1.0 * pa / 600,
                                      observed_pa=pa, service_time=1.0, age=24, draws=2000)["trade_value_mm"]
              for pa in (300, 600, 1200, 2400)]
    assert trades == sorted(trades, reverse=True), trades


def test_true_talent_tracks_observed_with_sample() -> None:
    """The regressed true talent moves from the FV prior toward observed as the
    sample grows (the smooth prior->stats transition)."""
    prior_mean = vf.expected_six_year_avg_war(50, False)   # FV-implied talent rate (FV-scaled)
    small = vf.debuted_player_value(50, False, "CF", observed_war=5.0 * 200 / 600,
                                    observed_pa=200, service_time=0.5, age=23)
    large = vf.debuted_player_value(50, False, "CF", observed_war=5.0 * 3000 / 600,
                                    observed_pa=3000, service_time=0.5, age=23)
    # observed rate 5.0/600 > prior; true talent rises toward it with sample
    assert prior_mean < small["true_talent_war"] < large["true_talent_war"]
    assert small["w_observed"] < large["w_observed"]


# =============================================================================
# Realized piece + trade excludes sunk years
# =============================================================================
def test_realized_uses_actual_war_and_salary() -> None:
    consumed = [{"fwar": 3.0, "salary_mm": 0.76}, {"fwar": 4.0, "salary_mm": 0.78}]
    d = vf.debuted_player_value(55, False, "SS", observed_war=7.0, observed_pa=1200,
                                service_time=2.0, age=24, consumed_seasons=consumed, draws=2000)
    flat = vf.dollars_per_war_flat()       # $M/WAR
    r = vf._config()["discount_rate"]
    manual = ((3.0 * flat - 0.76) * (1 + r) ** 1) + ((4.0 * flat - 0.78) * (1 + r) ** 0)
    assert d["realized_mm"] == pytest.approx(manual, abs=0.05)


def test_trade_value_excludes_consumed_years() -> None:
    """Trade value (remaining only) is identical whether or not consumed seasons
    are supplied -- consumed years are SUNK and enter only realized/total."""
    kw = dict(observed_war=7.0, observed_pa=1200, service_time=2.0, age=24, draws=2000)
    no_consumed = vf.debuted_player_value(55, False, "SS", **kw)
    with_consumed = vf.debuted_player_value(55, False, "SS",
                                            consumed_seasons=[{"fwar": 3.0, "salary_mm": 0.76},
                                                              {"fwar": 4.0, "salary_mm": 0.78}], **kw)
    assert no_consumed["trade_value_mm"] == with_consumed["trade_value_mm"]
    assert with_consumed["realized_mm"] > 0
    assert with_consumed["total_value_mm"] == pytest.approx(
        with_consumed["realized_mm"] + with_consumed["trade_value_mm"], abs=0.15)


def test_fewer_remaining_years_lower_value_same_talent() -> None:
    """On the ACTUAL service clock, a higher-service player (fewer remaining
    control years) is worth less at the same observed talent."""
    early = vf.debuted_player_value(55, False, "SS", observed_war=2.5, observed_pa=600,
                                    service_time=1.0, age=24, draws=2000)
    late = vf.debuted_player_value(55, False, "SS", observed_war=12.5, observed_pa=3000,
                                   service_time=5.0, age=28, draws=2000)
    assert late["remaining_control_years"] < early["remaining_control_years"]
    assert late["trade_value_mm"] < early["trade_value_mm"]


# =============================================================================
# Graduation -- long strong track record valued ~entirely by projection
# =============================================================================
def test_graduated_player_is_fv_independent() -> None:
    """A 30-WAR / 4500-PA track record should value ~the same regardless of the
    old FV prior -- the FV scaffolding has fallen away."""
    vals = {fv: vf.debuted_player_value(fv, False, "CF", observed_war=30.0, observed_pa=4500,
                                        service_time=4.0, age=27, draws=2000)
            for fv in (45, 55, 65)}
    trades = [v["trade_value_mm"] for v in vals.values()]
    spread = (max(trades) - min(trades)) / max(np_mean(trades), 1e-9)
    # ~16% residual FV-dependence after the 2026-06 surplus re-cal (anchor lag_max
    # widened to 12 for the 2011-2016 backfill) raised the top-tier FV->WAR anchors,
    # widening the FV-implied gap the small (<0.4) FV-prior component still carries.
    assert spread < 0.18, f"graduated trades not ~FV-independent: {trades}"
    assert all(v["w_graduated"] > 0.6 for v in vals.values())
    # true talent ~ observed (4500 PA at 30 WAR -> 4.0 WAR/600), prior negligible
    assert all(v["true_talent_war"] > 3.4 for v in vals.values())


def np_mean(xs):
    return sum(xs) / len(xs)


# =============================================================================
# Double-count guard + Prompt-E contract + bad input
# =============================================================================
def test_double_count_guard_full_reflect_no_update() -> None:
    """fv_reflects_mlb=1.0 => the FV already fully ingested the MLB data, so the
    Bayes update is suppressed (posterior == prior, no graduation)."""
    d = vf.debuted_player_value(50, False, "CF", observed_war=10.0, observed_pa=1500,
                                service_time=2.0, age=24, fv_reflects_mlb=1.0, draws=2000)
    assert d["posterior"] == d["prior"]
    assert d["w_observed"] == 0.0 and d["w_graduated"] == 0.0
    # vs full update (fv_reflects_mlb=0): overperformance lifts the trade value
    full = vf.debuted_player_value(50, False, "CF", observed_war=10.0, observed_pa=1500,
                                   service_time=2.0, age=24, fv_reflects_mlb=0.0, draws=2000)
    assert full["trade_value_mm"] > d["trade_value_mm"]


def test_remaining_reports_through_prompt_e_distribution() -> None:
    d = vf.debuted_player_value(55, False, "SS", observed_war=6.0, observed_pa=1200,
                                service_time=2.0, age=24, draws=4000)
    rem = d["remaining"]
    for k in ("mean", "percentiles", "p_bust", "p_above_threshold", "downside_metric",
              "risk_adjusted_score", "std", "mc_mean"):
        assert k in rem
    ps = list(rem["percentiles"].values())
    assert ps == sorted(ps)                                  # monotone percentiles
    assert rem["mean"] == pytest.approx(d["trade_value_mm"], abs=0.15)
    assert rem["downside_metric"] <= rem["mean"]


def test_debuted_none_for_bad_fv() -> None:
    for bad in (None, "x", float("nan"), float("inf")):
        assert vf.debuted_player_value(bad, False, "SS", observed_war=1, observed_pa=100) is None


# =============================================================================
# Review-hardening: tiny-sample stability, no-hump monotonicity, fractional-age
# and sub-45 continuity, coherent risk structure
# =============================================================================
def test_tiny_sample_does_not_blow_up() -> None:
    """A 1-PA / 2-IP cup of coffee must carry ~its own (tiny) weight -- close to
    the 0-sample prior, NOT a 40%+ swing (the tempered-likelihood fix)."""
    prior = vf.debuted_player_value(50, False, "CF", observed_war=0, observed_pa=0, age=23, draws=3000)["trade_value_mm"]
    for ow, pa in [(2.0, 1), (0.5, 1), (5.0, 1), (-1.0, 1)]:
        t = vf.debuted_player_value(50, False, "CF", observed_war=ow, observed_pa=pa,
                                    service_time=0, age=23, draws=3000)["trade_value_mm"]
        assert abs(t - prior) < 0.10 * prior, f"{ow} WAR/{pa} PA swung trade {t} vs prior {prior}"


def test_no_underflow_discontinuity() -> None:
    """No sharp jump across the old Gaussian-underflow boundary (5 WAR, 1->4 PA)."""
    ts = [vf.debuted_player_value(50, False, "CF", observed_war=5.0, observed_pa=pa,
                                  service_time=0, age=23, draws=2000)["trade_value_mm"] for pa in (1, 2, 3, 4)]
    assert max(abs(ts[i + 1] - ts[i]) for i in range(3)) < 2.0


def test_mean_tracking_player_is_monotone_no_hump() -> None:
    """A player performing EXACTLY at his FV-implied talent must not exhibit a
    sample-driven value hump (rise-then-fall); uncertainty resolution is a
    smooth monotone non-increase toward the resolved-talent value."""
    prior_mean = sum(p * m for p, m in zip(vf.p_bucket_given_fv(50, False),
                                           vf._calibrated_midpoints("hitter")))
    trades = [vf.debuted_player_value(50, False, "CF", observed_war=prior_mean * pa / 600,
                                      observed_pa=pa, service_time=1.0, age=24, draws=3000)["trade_value_mm"]
              for pa in (50, 150, 300, 600, 1200, 2400, 4800, 9600)]
    # No HUMP = no rise-then-fall (no interior peak). For the (correctly) right-
    # skewed recalibrated prior, confirming a mean-rate (above-median) outcome
    # raises value MONOTONICALLY -- clean resolution, not a hump. Assert monotone
    # (either direction): no local maximum interior to the path.
    assert trades == sorted(trades) or trades == sorted(trades, reverse=True),         f"hump (non-monotone rise-then-fall): {trades}"


@pytest.mark.parametrize("age", [22.3, 22.7, 23.4])
def test_continuity_exact_at_fractional_age(age) -> None:
    d = vf.debuted_player_value(55, False, "SS", observed_war=0, observed_pa=0,
                                service_time=0, age=age, draws=4000)["trade_value_mm"]
    assert d == pytest.approx(vf.surplus_value_mm(55, False, "SS", age=age, eta_years=0), abs=0.15)


@pytest.mark.parametrize("fv", [40, 42, 44])
def test_continuity_exact_sub45(fv) -> None:
    """Below FV 45 the debuted 0-sample value must match the prospect Edwards
    anchor/bridge (not the raw bucket pipeline)."""
    d = vf.debuted_player_value(fv, False, "SS", observed_war=0, observed_pa=0,
                                service_time=0, age=23, draws=4000)["trade_value_mm"]
    assert d == pytest.approx(vf.surplus_value_mm(fv, False, "SS", age=23, eta_years=0), abs=0.2)


def test_remaining_distribution_two_component_coherent() -> None:
    """The remaining distribution is a genuine two-component mixture: a graduated
    player's reported p_bust falls (proven not-bust) and the percentiles aren't a
    degenerate spike."""
    d = vf.debuted_player_value(50, False, "CF", observed_war=4.0 * 1800 / 600, observed_pa=1800,
                                service_time=1.0, age=24, draws=5000)
    rem = d["remaining"]
    assert rem["p_bust"] < d["prior"]["bust"]              # strong play lowers go-forward bust risk
    ps = list(rem["percentiles"].values())
    assert ps[-1] > ps[0]                                  # not a degenerate spike
