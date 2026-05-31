# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for source-disagreement uncertainty (Prompt I).

The consensus FV is a mean over several scouting sources; how much they DISAGREE
is a free uncertainty signal. We propagate it as FV sampling noise through the
SAME bucket model and re-center, so:

  * Two prospects with IDENTICAL consensus FV but different source spread share
    the SAME mean SV but the contested one has a WIDER distribution (the spec's
    headline validation).
  * Widening is monotone in dispersion and degrades gracefully: dispersion 0,
    disabled, or below `min_sources` reproduces the plain Prompt-E distribution.
  * The reported mean is ALWAYS the deterministic consensus SV (mean-preserving).
"""

from __future__ import annotations

import contextlib

import numpy as np
import pytest

import value_framework as vf

_DRAWS = 40000
_SEED = 20260531


@contextlib.contextmanager
def _cfg_override(**kv):
    """Temporarily patch keys of the live source_disagreement config block."""
    block = vf._config().setdefault("source_disagreement", {})
    saved = {k: block.get(k) for k in kv}
    block.update(kv)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                block.pop(k, None)
            else:
                block[k] = v


def _spread(d):
    return d["percentiles"]["p95"] - d["percentiles"]["p5"]


# =============================================================================
# THE spec validation: same mean, wider distribution for the contested prospect
# =============================================================================
def test_same_mean_wider_distribution_for_contested() -> None:
    tight = vf.sv_distribution(50, False, "SS", source_fvs={"a": 49, "b": 50, "c": 51},
                               draws=_DRAWS, seed=_SEED)
    wide = vf.sv_distribution(50, False, "SS", source_fvs={"a": 40, "b": 50, "c": 60},
                              draws=_DRAWS, seed=_SEED)
    assert tight["mean"] == wide["mean"]                 # identical consensus -> identical mean
    assert wide["std"] > tight["std"]                    # contested is wider
    assert _spread(wide) > _spread(tight)                # ... in the percentile spread too
    assert wide["fv_dispersion"] > tight["fv_dispersion"]


def test_same_mean_wider_for_pitcher() -> None:
    tight = vf.sv_distribution(55, True, "SP", fv_dispersion=1.0, n_sources=4, draws=_DRAWS, seed=_SEED)
    wide = vf.sv_distribution(55, True, "SP", fv_dispersion=7.0, n_sources=4, draws=_DRAWS, seed=_SEED)
    assert tight["mean"] == wide["mean"]
    assert wide["std"] > tight["std"]


# =============================================================================
# Mean is exactly preserved, regardless of dispersion
# =============================================================================
@pytest.mark.parametrize("fv,is_pit,pos", [(50, False, "SS"), (55, True, "SP"), (45, False, "OF"), (62, True, None)])
def test_mean_exactly_preserved(fv, is_pit, pos) -> None:
    point = vf.surplus_value_mm(fv, is_pit, pos)
    for disp in (0.0, 2.0, 5.0, 9.0):
        d = vf.sv_distribution(fv, is_pit, pos, fv_dispersion=disp, n_sources=4, draws=_DRAWS, seed=_SEED)
        assert d["mean"] == pytest.approx(point, abs=0.05)
        assert d["mc_mean"] == pytest.approx(d["mean"], abs=0.05)   # re-centered exactly


# =============================================================================
# Graceful degradation: no widening when there's no usable disagreement signal
# =============================================================================
def test_no_dispersion_reproduces_plain_distribution() -> None:
    plain = vf.sv_distribution(55, False, "SS", draws=_DRAWS, seed=_SEED)
    none_d = vf.sv_distribution(55, False, "SS", fv_dispersion=None, draws=_DRAWS, seed=_SEED)
    zero_d = vf.sv_distribution(55, False, "SS", fv_dispersion=0.0, draws=_DRAWS, seed=_SEED)
    assert plain["fv_sd"] == 0.0
    assert none_d["std"] == plain["std"] and zero_d["std"] == plain["std"]
    assert none_d["percentiles"] == plain["percentiles"]


def test_below_min_sources_no_widening() -> None:
    base = vf.sv_distribution(55, False, "SS", draws=_DRAWS, seed=_SEED)
    d = vf.sv_distribution(55, False, "SS", fv_dispersion=8.0, n_sources=1, draws=_DRAWS, seed=_SEED)
    assert d["fv_sd"] == 0.0
    assert d["std"] == base["std"]


def test_disabled_config_no_widening() -> None:
    base = vf.sv_distribution(55, False, "SS", draws=_DRAWS, seed=_SEED)
    with _cfg_override(enabled=False):
        d = vf.sv_distribution(55, False, "SS", fv_dispersion=8.0, n_sources=4, draws=_DRAWS, seed=_SEED)
    assert d["fv_sd"] == 0.0
    assert d["std"] == base["std"]


def test_single_source_dispersion_is_zero() -> None:
    d = vf.sv_distribution(55, False, "SS", source_fvs={"only": 55}, draws=_DRAWS, seed=_SEED)
    assert d["fv_sd"] == 0.0          # one source -> zero spread -> no widening


# =============================================================================
# Monotone widening in dispersion
# =============================================================================
def test_widening_monotone_in_dispersion() -> None:
    stds = [vf.sv_distribution(55, True, "SP", fv_dispersion=disp, n_sources=4,
                               draws=_DRAWS, seed=_SEED)["std"]
            for disp in (0.0, 2.0, 4.0, 6.0, 8.0)]
    assert stds == sorted(stds), stds
    assert stds[-1] > stds[0] * 1.05          # a clear, not-just-noise widening


def test_dispersion_cap_binds() -> None:
    """The disagreement magnitude is capped at max_fv_sd, so beyond the cap more
    raw dispersion does not keep widening."""
    with _cfg_override(max_fv_sd=4.0):
        a = vf.sv_distribution(55, True, "SP", fv_dispersion=4.0, n_sources=4, draws=_DRAWS, seed=_SEED)
        b = vf.sv_distribution(55, True, "SP", fv_dispersion=12.0, n_sources=4, draws=_DRAWS, seed=_SEED)
    assert a["fv_sd"] == 4.0 and b["fv_sd"] == 4.0
    assert a["std"] == b["std"]


def test_widening_monotone_at_low_fv_both_roles() -> None:
    """REGRESSION (review HIGH): widening must be MONOTONE at EVERY FV, including
    the steep low-tier 41-44 region where the prior FV-jitter+re-center mechanism
    INVERTED (more dispersion -> narrower). The within-bucket variance inflation
    is monotone by construction at all FV; the mean stays pinned."""
    for is_pit in (False, True):
        pos = "SP" if is_pit else "SS"
        for fv in (41, 42, 43, 44):
            stds = [vf.sv_distribution(fv, is_pit, pos, fv_dispersion=disp, n_sources=4,
                                       draws=60000, seed=_SEED)["std"]
                    for disp in (0.0, 2.0, 4.0, 6.0)]
            assert stds == sorted(stds), f"FV{fv} {pos}: non-monotone {stds}"
            assert stds[-1] > stds[0]            # strict widening, not just flat
            wide = vf.sv_distribution(fv, is_pit, pos, fv_dispersion=6.0, n_sources=4, draws=60000, seed=_SEED)
            plain = vf.sv_distribution(fv, is_pit, pos, draws=60000, seed=_SEED)
            assert wide["mean"] == pytest.approx(plain["mean"], abs=0.05)   # mean still pinned


# =============================================================================
# Contested is riskier: bucket probs (hence p_bust) UNCHANGED, but the outcome
# distribution is wider and the downside worse where bust mass < the CVaR quantile
# =============================================================================
def test_contested_keeps_pbust_but_widens() -> None:
    """The mechanism inflates within-bucket spread, NOT bucket probabilities, so a
    contested and a converged prospect at the same consensus FV share p_bust (and
    mean) exactly, while the contested one is wider."""
    tight = vf.sv_distribution(50, False, "SS", fv_dispersion=1.0, n_sources=4, draws=_DRAWS, seed=_SEED)
    wide = vf.sv_distribution(50, False, "SS", fv_dispersion=8.0, n_sources=4, draws=_DRAWS, seed=_SEED)
    assert wide["p_bust"] == pytest.approx(tight["p_bust"], abs=1e-9)
    assert wide["mean"] == tight["mean"]
    assert wide["std"] > tight["std"]
    assert _spread(wide) > _spread(tight)


def test_contested_has_worse_downside_when_bust_light() -> None:
    """At an FV whose bust mass is below the CVaR quantile (so the worst quartile
    sits in the non-bust region), disagreement worsens the downside metric and
    fattens the upper tail."""
    tight = vf.sv_distribution(62, True, "SP", fv_dispersion=1.0, n_sources=4, draws=_DRAWS, seed=_SEED)
    wide = vf.sv_distribution(62, True, "SP", fv_dispersion=8.0, n_sources=4, draws=_DRAWS, seed=_SEED)
    assert tight["p_bust"] < 0.25                       # worst quartile is non-bust
    assert wide["downside_metric"] < tight["downside_metric"]   # worse downside
    assert wide["percentiles"]["p90"] > tight["percentiles"]["p90"]   # fatter upside too


# =============================================================================
# aggregate_source_fvs: consensus + dispersion, normalization, weighting
# =============================================================================
def test_aggregate_source_fvs_basic() -> None:
    agg = vf.aggregate_source_fvs({"a": 40, "b": 50, "c": 60})
    assert agg["consensus"] == pytest.approx(50.0)
    assert agg["dispersion"] == pytest.approx(np.std([40, 50, 60]))   # population SD
    assert agg["n"] == 3


def test_aggregate_source_fvs_list_and_bad_values() -> None:
    agg = vf.aggregate_source_fvs([45, 55, None, float("nan"), "x"])
    assert agg["n"] == 2 and agg["consensus"] == pytest.approx(50.0)
    assert vf.aggregate_source_fvs([]) is None
    assert vf.aggregate_source_fvs([None, "x"]) is None


def test_aggregate_source_fvs_scale_offsets_and_weights() -> None:
    # mlb grades +2 hot: subtracting the offset converges the consensus/spread.
    raw = vf.aggregate_source_fvs({"fg": 50, "mlb": 54})
    norm = vf.aggregate_source_fvs({"fg": 50, "mlb": 54}, scale_offsets={"mlb": 4.0})
    assert norm["dispersion"] < raw["dispersion"]
    # zero-weight a source -> it drops out entirely.
    w = vf.aggregate_source_fvs({"a": 40, "b": 50, "c": 60}, weights={"c": 0.0})
    assert w["n"] == 2 and w["consensus"] == pytest.approx(45.0)


def test_aggregate_returns_spread() -> None:
    agg = vf.aggregate_source_fvs({"a": 40, "b": 50, "c": 60})
    assert agg["spread"] == pytest.approx(20.0)        # max - min


def test_aggregate_non_finite_offset_is_dropped() -> None:
    """REGRESSION (review LOW): a non-finite scale_offset must DROP the source, not
    poison the consensus with NaN/inf."""
    agg = vf.aggregate_source_fvs({"a": 50, "b": 50}, scale_offsets={"a": float("nan")})
    assert agg["n"] == 1 and agg["consensus"] == pytest.approx(50.0)
    agg2 = vf.aggregate_source_fvs({"a": 50, "b": 50}, scale_offsets={"a": float("inf")})
    assert agg2["n"] == 1 and np.isfinite(agg2["consensus"])


def test_spread_mode_uses_max_min_through_source_fvs() -> None:
    """REGRESSION (review LOW): in dispersion_stat='spread' mode the source_fvs path
    must drive off the max-min SPREAD (not the stddev). [40,60] -> spread 20 ->
    magnitude 0.5*20 = 10 (capped to max_fv_sd)."""
    with _cfg_override(dispersion_stat="spread", spread_to_sd=0.5, max_fv_sd=99.0):
        fv_sd, disp, n = vf._resolve_fv_sd(None, [40, 60], None)
        assert disp == pytest.approx(20.0)             # the max-min spread, not stddev 10
        assert fv_sd == pytest.approx(10.0)


# =============================================================================
# _source_fv_sd mapping knobs
# =============================================================================
def test_source_fv_sd_stddev_and_spread_modes() -> None:
    with _cfg_override(dispersion_stat="stddev", fv_sd_per_stddev=1.5, max_fv_sd=99):
        assert vf._source_fv_sd(4.0, 4) == pytest.approx(6.0)
    with _cfg_override(dispersion_stat="spread", spread_to_sd=0.5, max_fv_sd=99):
        assert vf._source_fv_sd(20.0, 4) == pytest.approx(10.0)   # spread 20 -> SD 10


def test_source_fv_sd_guards() -> None:
    assert vf._source_fv_sd(None) == 0.0
    assert vf._source_fv_sd(float("nan")) == 0.0
    assert vf._source_fv_sd(-1.0) == 0.0
    assert vf._source_fv_sd(0.0) == 0.0


# =============================================================================
# Robustness: extreme dispersion stays finite and valid; output bookkeeping
# =============================================================================
def test_extreme_dispersion_stays_valid() -> None:
    draws = vf.sv_draws(50, False, "SS", fv_dispersion=50.0, n_sources=4, draws=20000, seed=_SEED)
    assert draws is not None
    assert np.isfinite(draws).all()
    assert (draws >= 0).all()


def test_output_carries_dispersion_bookkeeping() -> None:
    d = vf.sv_distribution(50, False, "SS", source_fvs={"a": 42, "b": 50, "c": 58},
                           draws=_DRAWS, seed=_SEED)
    assert d["fv_sd"] > 0
    assert d["fv_dispersion"] == pytest.approx(np.std([42, 50, 58]), abs=1e-2)
    assert d["n_sources"] == 3


def test_sv_draws_widens_with_dispersion() -> None:
    base = vf.sv_draws(55, True, "SP", draws=_DRAWS, seed=_SEED)
    wide = vf.sv_draws(55, True, "SP", fv_dispersion=8.0, n_sources=4, draws=_DRAWS, seed=_SEED)
    assert wide.std() > base.std()
    assert wide.mean() == pytest.approx(base.mean(), abs=1.0)   # mean ~ preserved
