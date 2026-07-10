# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""WAG (WAR Above Grade) -- Prompt M rebuild on the FV-projection core.

Locks the rebuild's contract + the prompt's validations:
  * shared expected_war / _talent_regression core (no separate FV->WAR lookup)
  * exposure-matched (rookie-ramp) baseline -> counting + rate forms
  * standardized percentile (PIT) + z headline, distribution-aware
  * reliability-regressed true-talent WAG + band; sub-exposure flag
  * consistency with the Prompt-D posterior (same sign + sample weighting)
  * reliever-normalization safety; aggregates (leaderboard, mean-by-source)
"""

from __future__ import annotations

import numpy as np
import pytest

import value_framework as vf


# =============================================================================
# Continuity + on-trajectory
# =============================================================================
def test_zero_exposure_is_neutral() -> None:
    w = vf.wag(55, False, 0.0, position="SS", exposure_pa=0, age=23)
    assert w["counting_wag"] == 0.0 and w["rate_wag"] == 0.0
    assert w["percentile"] == 0.5 and w["z"] == 0.0
    assert w["regressed_wag"] == 0.0 and w["w_obs"] == 0.0
    assert w["below_meaningful_exposure"] is True


@pytest.mark.parametrize("pa,age", [(150, 22), (350, 23), (600, 24), (1800, 26)])
def test_on_trajectory_is_zero_at_every_exposure(pa, age) -> None:
    ew = vf.expected_war(50, False, "SS", exposure_pa=pa, age=age)
    w = vf.wag(50, False, ew["mean"], position="SS", exposure_pa=pa, age=age)
    assert w["counting_wag"] == pytest.approx(0.0, abs=1e-6)
    assert w["rate_wag"] == pytest.approx(0.0, abs=1e-6)
    assert w["z"] == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("pa", [150, 350, 600, 1800])
def test_above_positive_below_negative(pa) -> None:
    ew = vf.expected_war(50, False, "SS", exposure_pa=pa, age=24)
    up = vf.wag(50, False, ew["mean"] + 2.0, position="SS", exposure_pa=pa, age=24)
    dn = vf.wag(50, False, ew["mean"] - 2.0, position="SS", exposure_pa=pa, age=24)
    assert up["counting_wag"] > 0 and up["percentile"] > 0.5 and up["z"] > 0
    assert dn["counting_wag"] < 0 and dn["percentile"] < 0.5 and dn["z"] < 0


def test_percentile_scales_with_exposure() -> None:
    # The SAME +2 WAR over-performance is more extreme on a small sample (narrow
    # predicted distribution) than on a large one -> percentile decreases with exposure.
    small = vf.wag(50, False, vf.expected_war(50, False, "SS", exposure_pa=200, age=23)["mean"] + 2.0,
                   position="SS", exposure_pa=200, age=23)
    big = vf.wag(50, False, vf.expected_war(50, False, "SS", exposure_pa=1800, age=27)["mean"] + 2.0,
                 position="SS", exposure_pa=1800, age=27)
    assert small["percentile"] > big["percentile"]


# =============================================================================
# The headline rookie-ramp fix (Prompt M req 2)
# =============================================================================
def test_fifty_fv_one_year_two_war_reads_ahead() -> None:
    w = vf.wag(50, False, 2.0, position="SS", exposure_pa=600, age=24)
    assert w["counting_wag"] > 0          # ahead of the exposure-matched expectation
    assert w["percentile"] > 0.5
    # ... and the exposure-matched expectation is BELOW the 6-yr talent level (ramp).
    assert w["expected_war"] < 2.0


def test_full_exposure_rate_converges_to_talent_level() -> None:
    ew6 = vf.expected_war(55, False, "SS", service_years=6, age=27)
    tr = vf._talent_regression(55, False, 0.0, None, None, 0.0)
    assert ew6["mean_rate"] == pytest.approx(tr["prior_mean_rate"], abs=0.02)


# =============================================================================
# Standardized WAG is a valid PIT (ties to Prompt F)
# =============================================================================
def test_uniform_pit_for_cohort_following_grades() -> None:
    rng = np.random.RandomState(7)
    ew = vf.expected_war(52, False, "SS", exposure_pa=600, age=24)
    probs = np.array(ew["probs"]) / sum(ew["probs"])
    pits = []
    for _ in range(4000):
        _, cum_b, sw = ew["components"][rng.choice(5, p=probs)]
        obs = rng.normal(cum_b, sw)
        pits.append(vf.wag(52, False, obs, position="SS", exposure_pa=600, age=24)["percentile"])
    pits = np.array(pits)
    assert pits.mean() == pytest.approx(0.5, abs=0.03)
    deciles = np.histogram(pits, bins=10, range=(0, 1))[0] / len(pits)
    assert deciles.max() < 0.14 and deciles.min() > 0.06     # ~uniform (each ~0.10)


# =============================================================================
# Regression / small-sample (req 5) + shared core / D-consistency (req 1, 6)
# =============================================================================
def test_regressed_wag_shrinks_toward_zero_for_small_samples() -> None:
    # Same above-grade RATE, growing exposure -> regressed WAG grows from ~0.
    small = vf.wag(55, False, 3.4 * 100 / 600, position="SS", exposure_pa=100, age=24)
    big = vf.wag(55, False, 3.4 * 1800 / 600, position="SS", exposure_pa=1800, age=26)
    assert abs(small["regressed_wag"]) < abs(big["regressed_wag"])
    assert 0.0 <= small["w_obs"] < big["w_obs"]


def test_regressed_band_widens_for_thin_samples() -> None:
    small = vf.wag(55, False, 2.0, position="SS", exposure_pa=120, age=24)
    big = vf.wag(55, False, 6.0, position="SS", exposure_pa=1800, age=26)
    small_band = small["regressed_hi"] - small["regressed_lo"]
    big_band = big["regressed_hi"] - big["regressed_lo"]
    assert small_band > big_band


def test_meaningful_exposure_flag() -> None:
    me = vf._config()["wag"]["meaningful_exposure"]
    below = vf.wag(55, False, 1.0, position="SS", exposure_pa=int(me["hitter_pa"]) - 50, age=23)
    above = vf.wag(55, False, 3.0, position="SS", exposure_pa=int(me["hitter_pa"]) + 200, age=24)
    assert below["below_meaningful_exposure"] is True
    assert above["below_meaningful_exposure"] is False


def test_wag_true_talent_matches_debuted_same_core() -> None:
    # req 1/6: WAG and the debuted update call the SAME regression core, so the
    # regressed true-talent rate is identical for matched inputs.
    w = vf.wag(55, False, 3.5, position="SS", exposure_pa=900, age=25)
    d = vf.debuted_player_value(55, False, "SS", observed_war=3.5, observed_pa=900,
                                service_time=1.5, age=25)
    assert w["true_talent_war"] == pytest.approx(d["true_talent_war"], abs=1e-6)
    assert w["w_obs"] == pytest.approx(d["w_observed"], abs=1e-6)


@pytest.mark.parametrize("pa", [200, 600, 1500])
def test_regressed_wag_sign_and_weight_track_debuted_posterior(pa) -> None:
    mids = vf._calibrated_midpoints("hitter")
    obs = 3.5 * pa / 600                          # above-grade rate
    w = vf.wag(55, False, obs, position="SS", exposure_pa=pa, age=25)
    d = vf.debuted_player_value(55, False, "SS", observed_war=obs, observed_pa=pa,
                                service_time=pa / 600, age=25)
    prior_mean = sum(d["prior"][b] * mids[i] for i, b in enumerate(vf._BUCKETS))
    post_mean = sum(d["posterior"][b] * mids[i] for i, b in enumerate(vf._BUCKETS))
    assert (w["regressed_wag"] > 0) == (post_mean - prior_mean > 0)        # same sign
    assert w["w_obs"] > 0


def test_regressed_wag_monotone_in_sample() -> None:
    obs_rate_excess = lambda pa: vf.wag(55, False, 3.5 * pa / 600, position="SS",
                                        exposure_pa=pa, age=25)["regressed_wag"]
    vals = [obs_rate_excess(pa) for pa in (200, 600, 1200, 2400)]
    assert all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))        # grows with sample


# =============================================================================
# Rate vs counting divergence (req 3) + pitchers (req 7)
# =============================================================================
def test_rate_vs_counting_rank_injured_good_vs_healthy_compiler() -> None:
    injured_good = vf.wag(55, True, 2.6, position="SP", exposure_ip=80, age=25)     # elite rate, ~0.4 seas
    healthy_comp = vf.wag(55, True, 13.0, position="SP", exposure_ip=800, age=27)   # modest rate, big volume
    # Per-inning quality favors the injured-but-good arm:
    assert injured_good["rate_wag"] > healthy_comp["rate_wag"]
    # Total contribution favors the healthy compiler:
    assert healthy_comp["counting_wag"] > injured_good["counting_wag"]


def test_reliever_not_deflated_below_grade() -> None:
    # 1.4 WAR over 65 IP is a strong reliever; band-scale rate must read ABOVE a
    # 50-FV grade (the role haircut is a $-only effect, never applied to the grade).
    rp = vf.wag(50, True, 1.4, position="RP", exposure_ip=65, age=26)
    assert rp["rate_wag"] > 0 and rp["percentile"] > 0.5
    assert rp["observed_rate"] > rp["expected_rate"]


def test_bad_fv_returns_none() -> None:
    for bad in (None, "x", float("nan"), float("inf")):
        assert vf.wag(bad, False, 2.0, exposure_pa=600, age=24) is None
        assert vf.expected_war(bad, False, exposure_pa=600, age=24) is None


# =============================================================================
# Aggregates (req 8)
# =============================================================================
def _cohort():
    return [
        {"id": "a", "fv": 55, "is_pitcher": False, "position": "SS", "age": 25, "pa": 900, "observed_war": 5.0, "source": "FG"},
        {"id": "b", "fv": 50, "is_pitcher": False, "position": "OF", "age": 26, "pa": 1200, "observed_war": 2.0, "source": "FG"},
        {"id": "c", "fv": 60, "is_pitcher": True, "position": "SP", "age": 25, "ip": 400, "observed_war": 9.0, "source": "BA"},
        {"id": "d", "fv": 45, "is_pitcher": False, "position": "2B", "age": 24, "pa": 700, "observed_war": 0.5, "source": "BA"},
        {"id": "e", "fv": 55, "is_pitcher": False, "position": "CF", "age": 23, "pa": 60, "observed_war": 1.0, "source": "FG"},  # sub-exposure
    ]


def test_wag_leaderboard_risers_and_fallers() -> None:
    lb = vf.wag_leaderboard(_cohort(), n=2, by="percentile")
    assert lb["risers"] and lb["fallers"]
    assert lb["risers"][0]["wag"]["percentile"] >= lb["risers"][-1]["wag"]["percentile"]
    assert lb["fallers"][0]["wag"]["percentile"] <= lb["risers"][0]["wag"]["percentile"]
    # The sub-meaningful-exposure player is excluded by default.
    assert all(r["id"] != "e" for r in lb["risers"] + lb["fallers"])


def test_wag_mean_by_source_is_the_bias_signal() -> None:
    agg = vf.wag_mean_by(_cohort(), group_by="source", metric="regressed_wag")
    assert set(agg) == {"FG", "BA"}
    for g in agg:
        assert agg[g]["n"] >= 1 and "mean" in agg[g] and "mean_percentile" in agg[g]
    # 'e' (sub-exposure) excluded -> FG has 2 graded, not 3.
    assert agg["FG"]["n"] == 2
