# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""I3, the constant-path identity, and I5's neutral companion legs, on a
SYNTHETIC series: under carry_const, V(w, s) d(s) = K(w)(P(B)/F)((1+g)/(1+R))^(s-B)
for every forward season (s = N included), which at the default R is today's
net-7 pricing at level P(B) exactly; under any other R the general form."""

from __future__ import annotations

import random

import pytest

import dpw_testkit as kit
import value_framework as vf


def _paths(n=200, seed=20260925):
    rng = random.Random(seed)
    return [[rng.uniform(-0.5, 6.0) for _ in range(rng.randint(1, 12))] for _ in range(n)]


@pytest.mark.parametrize("R", [0.113763, 0.10])
def test_the_constant_path_identity_over_200_random_paths(tmp_path, R):
    with kit.unified(tmp_path, R=R):
        b, f = vf.pricing_base_season(), vf._flat_rate_usd()
        pb, g = vf.price_level(b), vf.g_ref()
        for path in _paths():
            for s0 in (b - 1, b, b + 3):
                lhs = sum(vf.season_value_usd(w, s0 + t) * vf.season_discount(s0 + t)
                          for t, w in enumerate(path))
                rhs = sum(vf.tiered_war_value_usd(w) * (pb / f) * ((1 + g) / (1 + R)) ** (s0 + t - b)
                          for t, w in enumerate(path))
                assert lhs == pytest.approx(rhs, rel=1e-12, abs=1e-6)
                if R == 0.113763:
                    net7 = sum(vf.tiered_war_value_usd(w) * (pb / f) / 1.07 ** (s0 + t - b)
                               for t, w in enumerate(path))
                    assert lhs == pytest.approx(net7, rel=1e-12, abs=1e-6)


def test_neutral_companion_legs_are_pv_neutral_after_s_t(tmp_path):
    with kit.unified(tmp_path):
        si = vf._require_block()["salary_index"]
        s_t = int(si["s_T"])
        base = vf.league_min_for(s_t) * vf.season_discount(s_t)
        ratio = (1.0409 / 1.113763)
        for k in range(1, 12):
            s = s_t + k
            assert vf.league_min_for(s) * vf.season_discount(s) == pytest.approx(base * ratio ** k, rel=1e-12)
            assert vf.arb_index_scale(s) == pytest.approx(vf.price_level(s) / vf.price_level(s_t), rel=1e-12)
