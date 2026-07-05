# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Phase 3 -- salary path & discounting: single net discount (no double
inflation), a deterministic golden career, arb-salary monotonicity, and the
clemens_2026 4-step prior-season arbitration schedule."""
import copy
import re
from pathlib import Path

import pytest

import value_framework as vf

_SRC = Path(vf.__file__).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# No second inflation / discount anywhere on the path
# --------------------------------------------------------------------------
def test_present_value_helper_is_never_called():
    """present_value() exists but must have NO call site -- a second PV pass on the
    already-netted surplus would double-count. Only its definition may reference it."""
    calls = [ln for ln in _SRC.splitlines()
             if "present_value(" in ln
             and not ln.lstrip().startswith("def present_value(")
             and not ln.lstrip().startswith("#")           # skip explanatory comments
             and '"""' not in ln]                          # skip docstrings
    assert calls == [], f"present_value() is called (double-discount risk): {calls}"


def test_single_net_discount_factor():
    with vf.valuation_set("clemens_2026"):
        net = 1.0 / 1.07   # net 7% flat (infl=0, discount_rate=0.07)
        v0 = vf._service_path_surplus_usd([2.0, 2.0, 2.0], False, 0.0)
        v1 = vf._service_path_surplus_usd([2.0, 2.0, 2.0], False, 1.0)
        # Shifting debut out one year multiplies EVERY season by net exactly once.
        assert v1 == pytest.approx(v0 * net, rel=1e-9)


def test_t0_season_is_undiscounted_and_uninflated():
    with vf.valuation_set("clemens_2026"):
        # One pre-arb season at t=0, eta=0: value == market(today) - league_min,
        # with net**0 = 1 (no discount) and today's $/WAR (no inflation grow-up).
        market = vf.tiered_war_value_usd(2.0)
        lm = float(vf._config()["service_time"]["league_min_usd"])
        v = vf._service_path_surplus_usd([2.0], False, 0.0)
        assert v == pytest.approx(market - lm, rel=1e-9)


# --------------------------------------------------------------------------
# Deterministic golden career (controlled config -> hand-computed)
# --------------------------------------------------------------------------
def test_golden_six_year_career():
    cfg = vf._config()
    snap = copy.deepcopy({k: cfg[k] for k in
                          ("dollars_per_war", "service_time", "discount_rate",
                           "dollars_per_war_inflation")})
    try:
        cfg["dollars_per_war"]["tiered"] = {"breakpoints": [1.0, 2.0],
                                            "rates": {"lt_1": 5e6, "1_to_2": 8e6, "2plus": 12e6}}
        cfg["dollars_per_war"]["kernel_mode"] = "bucket_step"
        cfg["service_time"] = {"control_years": 6, "league_min_usd": 0.5e6, "pre_arb_years": 3,
                               "arb_model": {"fractions_of_fa_value": [0.4, 0.6, 0.8],
                                             "super_two_first_fraction": 0.25},
                               "super_two": {"enabled": True, "fraction": 0.22}}
        cfg["discount_rate"] = 0.10
        cfg["dollars_per_war_inflation"] = 0.0
        val = vf._service_path_surplus_usd([2.0] * 6, False, 0.0)
        m = 2.0 * 12e6          # each season priced at the 2plus rate (bucket_step)
        net = 1.0 / 1.1
        sal = [0.5e6, 0.5e6, 0.5e6, 0.4 * m, 0.6 * m, 0.8 * m]   # current-season arb
        exp = sum((m - sal[t]) * net ** t for t in range(6))
        assert val == pytest.approx(exp, rel=1e-9)
    finally:
        vf._reset_caches()   # drop the mutated cached config


# --------------------------------------------------------------------------
# clemens_2026 arbitration: 4-step, prior-season basis, league-min floor
# --------------------------------------------------------------------------
def test_clemens_schedule_shape():
    with vf.valuation_set("clemens_2026"):
        st = vf._config()["service_time"]
        assert int(st["control_years"]) == 7
        assert int(st["pre_arb_years"]) == 3
        assert list(st["arb_model"]["fractions_of_fa_value"]) == [0.15, 0.35, 0.50, 0.75]
        lm = float(st["league_min_usd"])
        wars = [1.0, 1.5, 2.0, 2.5, 2.5, 2.0, 1.5]
        markets = [vf.tiered_war_value_usd(w) for w in wars]
        sal = vf._service_path_salaries(wars, markets, False)
        assert len(sal) == 7
        # 3 pre-arb at league min, then 4 arb years >= league min.
        assert sal[0] == sal[1] == sal[2] == pytest.approx(lm)
        assert all(s >= lm for s in sal[3:])


def test_arb_salary_monotone_in_prior_season_war():
    with vf.valuation_set("clemens_2026"):
        base = [1.0] * 7
        hi = [1.0] * 7
        hi[2] = 3.0   # raise the season PRIOR to the first arb year (t=3)
        s_base = vf._service_path_salaries(base, [vf.tiered_war_value_usd(w) for w in base], False)
        s_hi = vf._service_path_salaries(hi, [vf.tiered_war_value_usd(w) for w in hi], False)
        # Higher prior-season WAR never lowers the next arb salary; here strictly up.
        assert s_hi[3] >= s_base[3]
        assert s_hi[3] > s_base[3]


def test_prior_vs_current_basis_differ_on_rising_path():
    wars = [1.0, 1.0, 1.0, 3.0, 3.0, 3.0, 3.0]   # jump up at the first arb year
    with vf.valuation_set("clemens_2026"):   # prior_season basis
        markets = [vf.tiered_war_value_usd(w) for w in wars]
        prior = vf._service_path_salaries(wars, markets, False)
    # Under the current-season basis (the legacy prospx_current set), the first arb
    # salary tracks the CURRENT (3.0) season; under clemens prior-season it tracks
    # the prior (1.0), so prior-season pays less at the jump. clemens is now the
    # default, so pin the current-season comparison to the prospx_current context.
    with vf.valuation_set("prospx_current"):   # current_season basis
        markets_d = [vf.tiered_war_value_usd(w) for w in wars]
        current = vf._service_path_salaries(wars, markets_d, False)
    assert prior[3] < current[3]
