# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The 5 validation criteria for the WAG rebuild (engine FV-projection core).

Guards the properties the rebuild promised:
  1. continuity at zero exposure (WAG 0, standardized neutral),
  2. an on-trajectory player reads ~0 at every exposure (above -> +, below -> -),
     and the SAME WAR surplus is a smaller standardized signal at larger exposure,
  3. a cohort drawn ON their grades has ~uniform standardized percentiles (the PIT
     is calibrated -- ties to the backtest's PIT/coverage check),
  4. WAG sign + sample-weight match the Prompt-D bucket-posterior shift (shared
     reliability regression),
  5. rate vs counting WAG diverge by exposure (injured-but-good vs
     healthy-but-mediocre).
"""

from __future__ import annotations

import random

import numpy as np

import value_framework as vf


def test_continuity_zero_exposure():
    z = vf.wag(55, False, 0.0, position="SS", service_years=0.0, age=22)
    assert z["counting_wag"] == 0.0
    assert z["rate_wag"] == 0.0
    assert abs(z["percentile"] - 0.5) < 1e-9
    assert z["z"] == 0.0


def test_on_trajectory_and_direction():
    prev_above_pct = None
    for yrs in (1.0, 2.0, 3.0, 4.0):
        ew = vf.expected_war(55, False, "SS", service_years=yrs, age=22 + yrs)
        on = vf.wag(55, False, ew["mean"], position="SS", service_years=yrs, age=22 + yrs)
        assert abs(on["counting_wag"]) < 1e-6            # exactly on grade -> 0
        above = vf.wag(55, False, ew["mean"] + 2.0, position="SS", service_years=yrs, age=22 + yrs)
        below = vf.wag(55, False, max(0.0, ew["mean"] - 2.0), position="SS", service_years=yrs, age=22 + yrs)
        assert above["counting_wag"] > 0 and below["counting_wag"] < 0
        # same +2 WAR surplus -> a SMALLER standardized signal at larger exposure
        if prev_above_pct is not None:
            assert above["percentile"] <= prev_above_pct + 1e-9
        prev_above_pct = above["percentile"]


def test_cohort_on_grade_uniform_percentiles():
    rng = random.Random(7)
    np.random.seed(7)
    pits = []
    for _ in range(2500):
        fv = rng.uniform(45, 65)
        isp = rng.random() < 0.45
        yrs = rng.choice([2.0, 3.0, 4.0])
        ew = vf.expected_war(fv, isp, None, service_years=yrs, age=24)
        r = rng.random(); acc = 0.0; pick = ew["components"][-1]
        for w, cum, sd in ew["components"]:
            acc += w
            if r <= acc:
                pick = (w, cum, sd); break
        obs = float(np.random.normal(pick[1], max(1e-6, pick[2])))   # draw from the predicted mixture
        w = vf.wag(fv, isp, obs, service_years=yrs, age=24)
        if w and not w["below_meaningful_exposure"]:
            pits.append(w["percentile"])
    pits = np.array(pits)
    bins = np.histogram(pits, bins=10, range=(0, 1))[0]
    maxdev = float(np.max(np.abs(bins - len(pits) / 10)) / (len(pits) / 10))
    assert abs(pits.mean() - 0.5) < 0.05, f"mean={pits.mean():.3f}"
    assert maxdev < 0.30, f"bins={bins.tolist()} maxdev={maxdev:.2f}"


def _up_mass(dv):
    p, pr = dv["posterior"], dv["prior"]
    return (p["good"] + p["star"]) - (pr["good"] + pr["star"])


def test_wag_sign_and_weight_match_posterior():
    over = vf.debuted_player_value(55, False, "SS", observed_war=12.0, observed_pa=1800,
                                   service_time=3.0, age=25,
                                   consumed_seasons=vf.realized_consumed_seasons({2023: 4, 2024: 4, 2025: 4}))
    under = vf.debuted_player_value(55, False, "SS", observed_war=1.0, observed_pa=1800,
                                    service_time=3.0, age=25,
                                    consumed_seasons=vf.realized_consumed_seasons({2023: 0.3, 2024: 0.3, 2025: 0.4}))
    w_over = vf.wag(55, False, 12.0, position="SS", exposure_pa=1800, age=25)
    w_under = vf.wag(55, False, 1.0, position="SS", exposure_pa=1800, age=25)
    # sign: WAG and the posterior up-mass shift agree
    assert w_over["regressed_wag"] > 0 and _up_mass(over) > 0
    assert w_under["regressed_wag"] < 0 and _up_mass(under) < 0
    # sample weight: more exposure (same strong rate) -> bigger posterior shift
    small = vf.debuted_player_value(55, False, "SS", observed_war=4.0, observed_pa=600, service_time=1.0,
                                    age=23, consumed_seasons=vf.realized_consumed_seasons({2025: 4.0}))
    big = vf.debuted_player_value(55, False, "SS", observed_war=16.0, observed_pa=2400, service_time=4.0,
                                  age=26, consumed_seasons=vf.realized_consumed_seasons({2022: 4, 2023: 4, 2024: 4, 2025: 4}))
    assert abs(_up_mass(big)) > abs(_up_mass(small))


def test_rate_vs_counting_divergence():
    injured = vf.wag(55, False, 3.0, position="SS", exposure_pa=300, age=24)    # strong rate, ~half season
    healthy = vf.wag(55, False, 4.0, position="SS", exposure_pa=2400, age=27)   # meh rate, 4 full seasons
    assert injured["rate_wag"] > healthy["rate_wag"]                            # rate ranks injured ahead
    assert abs(injured["counting_wag"]) < abs(injured["rate_wag"])              # sub-season: counting < rate
    assert abs(healthy["counting_wag"]) > abs(healthy["rate_wag"])             # multi-season: counting > rate
