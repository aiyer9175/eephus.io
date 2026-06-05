# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the system / portfolio rollup (Prompt K).

A farm system is NOT a sum of point estimates. Two effects bend the rollup:
  * OUTCOME CORRELATION (shared org/development) -- a single-factor Gaussian
    copula reorders each prospect's own draws to a shared rho, preserving every
    marginal exactly (so the system mean is the sum of means) while widening the
    spread for rho > 0.
  * ROSTER-REALIZATION / LOGJAM -- only so many roster spots per position, so a
    system stacked at one position realizes the blocked excess at a trade
    discount.

Headline validation: rho = 0 AND cap disabled reduces EXACTLY to the sum of
individual mean SVs.
"""

from __future__ import annotations

import contextlib

import pytest

import value_framework as vf

_DRAWS = 40000
_SEED = 20260531


@contextlib.contextmanager
def _portfolio_override(**kv):
    block = vf._config().setdefault("portfolio", {})
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


def _sys(extra=None):
    base = [
        {"fv": 60, "is_pitcher": False, "position": "SS"},
        {"fv": 55, "is_pitcher": False, "position": "CF"},
        {"fv": 50, "is_pitcher": True, "position": "SP"},
        {"fv": 45, "is_pitcher": True, "position": "RP"},
        {"fv": 50, "is_pitcher": False, "position": "3B"},
    ]
    return base + (extra or [])


def _sum_of_means(system):
    return sum(vf.surplus_value_mm(p["fv"], p["is_pitcher"], p["position"]) for p in system)


# =============================================================================
# THE headline validation: rho=0 + cap off == sum of individual mean SVs
# =============================================================================
def test_continuity_rho0_capoff_equals_sum_of_means() -> None:
    system = _sys()
    d = vf.system_surplus_distribution(system, correlation=0.0, apply_cap=False,
                                       draws=_DRAWS, seed=_SEED)
    assert d["mean"] == pytest.approx(d["sum_of_means"], abs=0.05)
    assert d["sum_of_means"] == pytest.approx(_sum_of_means(system), abs=0.2)
    assert d["realization_discount"] == pytest.approx(0.0, abs=1e-3)
    assert d["cap_applied"] is False and d["correlation"] == 0.0


def test_mean_is_sum_of_means_at_any_correlation_capoff() -> None:
    """Correlation reorders marginals -> mean unchanged at every rho (cap off)."""
    system = _sys()
    means = [vf.system_surplus_distribution(system, correlation=r, apply_cap=False,
                                            draws=_DRAWS, seed=_SEED)["mean"]
             for r in (0.0, 0.1, 0.3, 0.6, 0.9)]
    assert all(m == pytest.approx(means[0], abs=0.1) for m in means)


# =============================================================================
# Correlation widens the system spread (correct portfolio risk)
# =============================================================================
def test_correlation_widens_spread() -> None:
    system = _sys()
    stds = [vf.system_surplus_distribution(system, correlation=r, apply_cap=False,
                                           draws=_DRAWS, seed=_SEED)["std"]
            for r in (0.0, 0.1, 0.3, 0.6, 0.9)]
    assert stds == sorted(stds)
    assert stds[-1] > stds[0]
    # rho=0 spread ~ independent (sqrt-of-sum-of-variances) < perfectly-summed std.
    indep = vf.system_surplus_distribution(system, correlation=0.0, apply_cap=False, draws=_DRAWS, seed=_SEED)
    per = [vf.sv_distribution(p["fv"], p["is_pitcher"], p["position"], draws=_DRAWS, seed=_SEED)["std"]
           for p in system]
    assert indep["std"] < sum(per)                       # diversification (independent) < comonotone


# =============================================================================
# Roster-realization / logjam discount
# =============================================================================
def test_logjam_cap_discounts_stacked_position() -> None:
    """Three SS (one full-value slot) -> the cap discounts the blocked two."""
    stacked = _sys([{"fv": 55, "is_pitcher": False, "position": "SS"},
                    {"fv": 50, "is_pitcher": False, "position": "SS"}])
    off = vf.system_surplus_distribution(stacked, correlation=0.1, apply_cap=False, draws=_DRAWS, seed=_SEED)
    on = vf.system_surplus_distribution(stacked, correlation=0.1, apply_cap=True, draws=_DRAWS, seed=_SEED)
    assert on["realization_discount"] > 0.02             # logjam bites
    assert on["mean"] < off["mean"]                      # realized value below the naive sum
    assert off["realization_discount"] == pytest.approx(0.0, abs=1e-3)


def test_cap_no_logjam_no_discount() -> None:
    """A balanced system (no position over its slot count) sees ~no discount even
    with the cap on -- so cap-on reduces to the sum of means when nothing is
    blocked."""
    system = _sys()   # SS1, CF(OF) 1, SP 1, RP 1, 3B 1 -- all within slots
    on = vf.system_surplus_distribution(system, correlation=0.0, apply_cap=True, draws=_DRAWS, seed=_SEED)
    assert on["realization_discount"] == pytest.approx(0.0, abs=1e-3)
    assert on["mean"] == pytest.approx(on["sum_of_means"], abs=0.1)


def test_trade_recovery_bounds_the_discount() -> None:
    """trade_recovery=1.0 -> blocked excess fully realized (no discount);
    trade_recovery=0.0 -> excess fully blocked (max discount)."""
    stacked = _sys([{"fv": 55, "is_pitcher": False, "position": "SS"},
                    {"fv": 52, "is_pitcher": False, "position": "SS"}])
    with _portfolio_override(trade_recovery=1.0):
        full = vf.system_surplus_distribution(stacked, apply_cap=True, correlation=0.1, draws=_DRAWS, seed=_SEED)
    with _portfolio_override(trade_recovery=0.0):
        none = vf.system_surplus_distribution(stacked, apply_cap=True, correlation=0.1, draws=_DRAWS, seed=_SEED)
    assert full["realization_discount"] == pytest.approx(0.0, abs=1e-3)
    assert none["realization_discount"] > full["realization_discount"]


def test_cap_keeps_the_best_in_the_slot() -> None:
    """Within a logjam group the TOP-SV prospects fill the slots; the discount
    falls on the weaker excess. So a system with the elite SS plus two weak SS
    loses less than one with three equal mid SS (same prospect count)."""
    elite = [{"fv": 65, "is_pitcher": False, "position": "SS"},
             {"fv": 40, "is_pitcher": False, "position": "SS"},
             {"fv": 40, "is_pitcher": False, "position": "SS"}]
    flat = [{"fv": 50, "is_pitcher": False, "position": "SS"},
            {"fv": 50, "is_pitcher": False, "position": "SS"},
            {"fv": 50, "is_pitcher": False, "position": "SS"}]
    e = vf.system_surplus_distribution(elite, apply_cap=True, correlation=0.1, draws=_DRAWS, seed=_SEED)
    f = vf.system_surplus_distribution(flat, apply_cap=True, correlation=0.1, draws=_DRAWS, seed=_SEED)
    assert e["realization_discount"] < f["realization_discount"]


# =============================================================================
# Output contract, robustness, determinism
# =============================================================================
def test_percentiles_present_and_monotone() -> None:
    d = vf.system_surplus_distribution(_sys(), draws=_DRAWS, seed=_SEED)
    p = d["percentiles"]
    assert p["p10"] <= p["p50"] <= p["p90"]
    for key in ("mean", "std", "sum_of_means", "realization_discount", "n_prospects",
                "correlation", "cap_applied", "downside_metric"):
        assert key in d
    assert "p_bust" not in d                              # not meaningful for an aggregate
    assert d["n_prospects"] == 5


def test_single_prospect_matches_its_own_distribution() -> None:
    one = [{"fv": 55, "is_pitcher": False, "position": "SS"}]
    sysd = vf.system_surplus_distribution(one, correlation=0.5, apply_cap=True, draws=_DRAWS, seed=_SEED)
    solo = vf.sv_distribution(55, False, "SS", draws=_DRAWS, seed=_SEED)
    assert sysd["mean"] == pytest.approx(solo["mean"], abs=0.1)
    assert sysd["std"] == pytest.approx(solo["std"], abs=0.5)    # rho irrelevant with one prospect


def test_empty_and_all_invalid_return_none() -> None:
    assert vf.system_surplus_distribution([]) is None
    assert vf.system_surplus_distribution([{"fv": None, "is_pitcher": False, "position": "SS"}]) is None
    assert vf.system_surplus_distribution([{"fv": float("nan"), "is_pitcher": True, "position": "SP"}]) is None


def test_invalid_prospects_are_skipped() -> None:
    mixed = [{"fv": 55, "is_pitcher": False, "position": "SS"},
             {"fv": None, "is_pitcher": False, "position": "CF"},
             {"fv": 50, "is_pitcher": True, "position": "SP"}]
    d = vf.system_surplus_distribution(mixed, draws=_DRAWS, seed=_SEED)
    assert d["n_prospects"] == 2


def test_correlation_clamped_no_crash() -> None:
    system = _sys()
    hi = vf.system_surplus_distribution(system, correlation=5.0, apply_cap=False, draws=10000, seed=_SEED)
    lo = vf.system_surplus_distribution(system, correlation=-1.0, apply_cap=False, draws=10000, seed=_SEED)
    assert hi["correlation"] == 0.999 and lo["correlation"] == 0.0
    assert hi["mean"] == pytest.approx(lo["mean"], abs=0.5)


def test_determinism() -> None:
    system = _sys()
    a = vf.system_surplus_distribution(system, correlation=0.2, apply_cap=True, draws=20000, seed=123)
    b = vf.system_surplus_distribution(system, correlation=0.2, apply_cap=True, draws=20000, seed=123)
    c = vf.system_surplus_distribution(system, correlation=0.2, apply_cap=True, draws=20000, seed=999)
    assert a["std"] == b["std"] and a["percentiles"] == b["percentiles"]
    assert a["std"] != c["std"]


def test_discount_is_clean_zero_not_negative_zero() -> None:
    """REGRESSION (review LOW): the exact-continuity case must report a clean 0.0
    realization_discount, not a float-noise -0.0 that serializes as '-0.0000'."""
    import json
    d = vf.system_surplus_distribution(_sys(), correlation=0.0, apply_cap=False, draws=_DRAWS, seed=_SEED)
    assert d["realization_discount"] == 0.0
    assert "%.4f" % d["realization_discount"] == "0.0000"        # not '-0.0000'
    assert "-0.0" not in json.dumps(d["realization_discount"])


def test_trade_recovery_above_one_clamped_no_premium() -> None:
    """REGRESSION (review LOW): a misconfigured trade_recovery > 1 must NOT create
    a negative discount (a logjam can never be a premium); it clamps to 1.0."""
    stacked = _sys([{"fv": 55, "is_pitcher": False, "position": "SS"},
                    {"fv": 50, "is_pitcher": False, "position": "SS"}])
    with _portfolio_override(trade_recovery=1.5):
        d = vf.system_surplus_distribution(stacked, apply_cap=True, correlation=0.1, draws=_DRAWS, seed=_SEED)
    assert d["realization_discount"] >= 0.0                       # clamped: no premium
    assert d["realization_discount"] == pytest.approx(0.0, abs=1e-3)   # t->1 => ~no discount


def test_roster_group_mapping() -> None:
    assert vf._roster_group("CF") == "OF"
    assert vf._roster_group("LF") == "OF"
    assert vf._roster_group("RHP", True) == "SP"
    assert vf._roster_group("SP") == "SP"
    assert vf._roster_group("RP") == "RP"
    assert vf._roster_group("CL") == "RP"
    assert vf._roster_group("SS") == "SS"
    assert vf._roster_group(None, True) == "SP"          # untagged pitcher
    assert vf._roster_group(None, False) == "UTIL"
