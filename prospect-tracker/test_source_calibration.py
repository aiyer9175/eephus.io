# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Source-calibration loop (Prompt N): de-bias + reliability-weight the consensus FV.

Validates the rebuild against the prompt's checks, reusing Prompt F's realized-
outcome reconstruction (backtest._realized_control_war) and the Prompt-M/F FV core:
  * recovery of an injected per-source bias; weight scales inversely with noise var
  * a pure-noise source -> ~0 weight
  * redundancy: two highly-correlated sources together ~ one independent source
  * de-biasing reduces error on HELD-OUT cohorts (leave-one-cohort-year-out CV)
  * continuity: a single source -> that source de-biased
  * thin-history sources shrink toward 0 bias / equal weight
  * the consensus FV feeds the FV-projection core + Prompt I uncertainty
"""

from __future__ import annotations

import numpy as np
import pytest

import value_framework as vf
import backtest as bt           # Prompt F -- reused for the realized reconstruction


def _synth(rng, n, sources, *, year_span=(2015, 2021), fv_lo=44.0, fv_hi=65.0):
    """Synthetic graded-player -> outcome cohort.

    A true FV maps to a realized control-window WAR via the FV core; that WAR is
    reconstructed through Prompt F's _realized_control_war (genuine reuse). Each
    source observes true_fv + bias + (shared cluster noise) + independent noise, so
    cluster members are CORRELATED. `sources`: {name: {bias, noise, cluster,
    cluster_sd, only_first}} (only_first N -> source grades only the first N players).
    """
    recs = []
    for i in range(n):
        true_fv = float(rng.uniform(fv_lo, fv_hi))
        is_pit = bool(rng.rand() < 0.5)
        rw = vf.expected_war(true_fv, is_pit, service_years=6)["mean"]
        rr = bt.RealizedRecord(player_id=f"p{i}", debut_year=2018,
                               seasons=(bt.RealizedSeason(2018, rw, 1.0, 172.0),))
        realized = bt._realized_control_war(rr)
        common: dict = {}
        sf = {}
        for s, spec in sources.items():
            if spec.get("only_first") is not None and i >= spec["only_first"]:
                continue
            cl = spec.get("cluster")
            if cl is not None and cl not in common:
                common[cl] = rng.normal(0.0, spec.get("cluster_sd", 0.0))
            shared = common.get(cl, 0.0) if cl is not None else 0.0
            sf[s] = true_fv + spec.get("bias", 0.0) + shared + rng.normal(0.0, spec.get("noise", 1.0))
        recs.append({"source_fvs": sf, "is_pitcher": is_pit, "realized_war": realized,
                     "exposure_seasons": 6, "cohort_year": int(rng.randint(*year_span))})
    return recs


# =============================================================================
# (1)(2) Recovery: injected bias + skill-based weighting
# =============================================================================
def test_recovers_injected_bias_and_inverse_noise_weight() -> None:
    rng = np.random.RandomState(11)
    recs = _synth(rng, 800, {
        "A": {"bias": 0.0, "noise": 1.0},      # unbiased, precise
        "B": {"bias": 5.0, "noise": 2.0},      # +5 too high, noisier
        "C": {"bias": -3.0, "noise": 1.5},     # -3 too low
    })
    cal = vf.fit_source_calibration(recs)
    ps = cal["per_source"]
    assert ps["A"]["bias"] == pytest.approx(0.0, abs=0.4)
    assert ps["B"]["bias"] == pytest.approx(5.0, abs=0.8)        # de-bias DOWN (grades high)
    assert ps["C"]["bias"] == pytest.approx(-3.0, abs=0.8)       # de-bias UP (grades low)
    # error variance tracks injected noise^2 (1 / 4 / 2.25):
    assert ps["A"]["var"] < ps["C"]["var"] < ps["B"]["var"]
    # reliability weight scales inversely with noise variance:
    con = vf.calibrated_consensus_fv({"A": 55, "B": 55, "C": 55}, cal)
    w = con["weights"]
    assert w["A"] > w["C"] > w["B"]


def test_pure_noise_source_gets_near_zero_weight() -> None:
    rng = np.random.RandomState(3)
    recs = _synth(rng, 700, {"A": {"bias": 0.0, "noise": 1.0},
                             "Noise": {"bias": 0.0, "noise": 14.0}})
    cal = vf.fit_source_calibration(recs)
    con = vf.calibrated_consensus_fv({"A": 55, "Noise": 55}, cal)
    assert con["weights"]["Noise"] < 0.05
    assert con["weights"]["A"] > 0.95


# =============================================================================
# (4) Correlated / redundant sources share weight
# =============================================================================
def test_correlated_sources_share_one_sources_weight() -> None:
    rng = np.random.RandomState(5)
    # A1,A2 copy each other (shared cluster noise sd=2) + small independent noise;
    # B is independent with a comparable TOTAL noise. So all three have ~equal
    # marginal variance, but A1,A2 are ~0.9 correlated.
    recs = _synth(rng, 1500, {
        "A1": {"bias": 0.0, "noise": 0.6, "cluster": "K", "cluster_sd": 2.0},
        "A2": {"bias": 0.0, "noise": 0.6, "cluster": "K", "cluster_sd": 2.0},
        "B":  {"bias": 0.0, "noise": 2.09},
    })
    cal = vf.fit_source_calibration(recs)
    w = vf.calibrated_consensus_fv({"A1": 55, "A2": 55, "B": 55}, cal)["weights"]
    # The redundant pair TOGETHER gets ~the weight of the single independent source,
    # not double -- and each pair member individually gets less than B.
    assert w["A1"] < w["B"] and w["A2"] < w["B"]
    assert abs((w["A1"] + w["A2"]) - w["B"]) < 0.18


# =============================================================================
# (5)(6) Consensus rebuild, continuity, loop wiring, uncertainty -> Prompt I
# =============================================================================
def test_single_source_consensus_is_that_source_debiased() -> None:
    rng = np.random.RandomState(7)
    recs = _synth(rng, 600, {"A": {"bias": 4.0, "noise": 1.0}})
    cal = vf.fit_source_calibration(recs)
    con = vf.calibrated_consensus_fv({"A": 60}, cal)
    assert con["n_sources"] == 1
    # Continuity: the consensus IS the single source, de-biased (by its conditional
    # role/FV-tier cell bias), and pulled DOWN since the source grades high (+4).
    assert con["consensus_fv"] == pytest.approx(con["debiased"]["A"], abs=1e-9)
    assert con["consensus_fv"] < 60
    assert con["weights"] == {"A": 1.0}


def test_consensus_feeds_core_and_prompt_i_uncertainty() -> None:
    rng = np.random.RandomState(9)
    recs = _synth(rng, 600, {"A": {"bias": 0.0, "noise": 1.0}, "B": {"bias": 3.0, "noise": 2.0}})
    cal = vf.fit_source_calibration(recs)
    con = vf.calibrated_consensus_fv({"A": 56, "B": 59}, cal, is_pitcher=False, position="SS")
    # (6) the de-biased consensus FV flows into the FV-projection core:
    assert vf.surplus_value_mm(con["consensus_fv"], False, "SS") is not None
    assert vf.wag(con["consensus_fv"], False, 3.0, position="SS", exposure_pa=600, age=24) is not None
    # (5d) skill uncertainty combines with the Prompt-I disagreement spread:
    combined = vf.combined_fv_uncertainty(2.0, con["fv_sd"])
    assert combined == pytest.approx((4.0 + con["fv_sd"] ** 2) ** 0.5)
    wide = vf.sv_distribution(con["consensus_fv"], False, "SS", fv_dispersion=combined, n_sources=2, seed=1)
    tight = vf.sv_distribution(con["consensus_fv"], False, "SS", seed=1)
    assert wide["std"] >= tight["std"]


# =============================================================================
# (3) Thin-history shrinkage
# =============================================================================
def test_thin_history_source_shrinks_to_no_bias() -> None:
    rng = np.random.RandomState(13)
    recs = _synth(rng, 400, {
        "Big": {"bias": 0.0, "noise": 1.0},
        "Thin": {"bias": 6.0, "noise": 1.0, "only_first": 3},   # only 3 graded players
    })
    cal = vf.fit_source_calibration(recs)
    assert cal["per_source"]["Thin"]["thin"] is True
    assert cal["per_source"]["Thin"]["bias"] == 0.0             # shrunk to no-bias
    assert cal["per_source"]["Big"]["thin"] is False


# =============================================================================
# (7) Out-of-sample: de-biasing reduces error on HELD-OUT cohorts
# =============================================================================
def test_oos_cv_debiasing_reduces_error_on_holdout() -> None:
    rng = np.random.RandomState(17)
    recs = _synth(rng, 900, {
        "A": {"bias": 4.0, "noise": 1.5},
        "B": {"bias": -3.0, "noise": 1.5},
    }, year_span=(2014, 2020))
    cv = vf.source_calibration_cv(recs)
    assert cv["pooled"]["mae_after"] < cv["pooled"]["mae_before"]   # de-bias helps out-of-sample
    # and it helps in (most) individual held-out years too:
    improved = sum(1 for y in cv["per_year"].values() if y["mae_after"] < y["mae_before"])
    assert improved >= max(1, len(cv["per_year"]) - 1)


# =============================================================================
# Plumbing / edge cases
# =============================================================================
def test_realized_implied_fv_inverts_the_core() -> None:
    for fv, isp in [(50, False), (55, True), (60, False)]:
        rw = vf.expected_war(fv, isp, service_years=6)["mean"]
        assert vf.realized_implied_fv(rw, isp, exposure_seasons=6) == pytest.approx(fv, abs=0.2)


def test_unknown_source_gets_no_bias_default_weight() -> None:
    rng = np.random.RandomState(19)
    cal = vf.fit_source_calibration(_synth(rng, 300, {"A": {"bias": 5.0, "noise": 1.0}}))
    con = vf.calibrated_consensus_fv({"A": 60, "NeverSeen": 50}, cal)
    assert con["debiased"]["NeverSeen"] == 50.0                 # unknown -> ungraded, no bias
    info = cal["per_source"]["A"]
    cellbias = info["cells"].get(("hitter", vf._fv_tier_index(60, cal["tiers"])), info["bias"])
    assert con["debiased"]["A"] == pytest.approx(60 - cellbias, abs=2e-3)   # de-biased (conditional; 3dp rounded)


def test_empty_inputs_degrade_gracefully() -> None:
    assert vf.calibrated_consensus_fv({}, {}) is None
    assert vf.fit_source_calibration([])["sources"] == []
    assert vf.realized_implied_fv(None, False) is None
