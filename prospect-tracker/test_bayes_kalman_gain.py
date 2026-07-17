# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Regression pins for the § KALMAN precision-consistent gain in
bayes_trade_value (audit fix; bayes_trade_value.py ~L3288).

The bug being pinned: the old gain K = prior_prec / (prior_prec + obs_n)
INVERTED the prior's role - a TIGHTER prior (higher pedigree / age-for-level /
source-count precision) moved MORE on a noisy sample, the exact opposite of
_prior_precision's documented contract ("higher precision -> observation moves
the posterior less"). The fixed form is K = 1 / (1 + prior_prec * obs_n), so
prior precision now SHRINKS the gain. Nothing else in the suite touches
kalman_gain / _prior_precision / _obs_noise, so a revert would pass silently
without these tests.

Fixture note: n_sources is the cleanest precision dial - it feeds
_prior_precision directly (per-source weight, capped) while every other input
stays byte-identical between calls. The small 80-PA sample keeps observation
noise high enough that the gain sits BELOW the 0.22 prospect cap on both the
fixed and the reverted formula path for the low-precision call; under the
reverted formula both calls saturate the cap and the strict inequality fails.
"""

import pytest

from bayes_trade_value import (
    bayesian_trade_value,
    _obs_noise,
    _prior_precision,
)

LEVEL_NORMS = {
    "AA": {"perf": {"k_pct": 22.0, "bb_pct": 8.5, "woba": 0.320,
                    "avg_ev": 87.0, "barrel_pct": 6.0}},
}


def _prospect(**overrides):
    """Active AA hitter with a real (but small, 80 PA) performance sample so
    the § KALMAN update actually fires (signal is not None, sample > 10)."""
    p = {
        "player_key": "kalman_test_prospect",
        "player_name": "Kalman Test",
        "org": "TST",
        "status": "active",
        "position": "SS",
        "is_pitcher": False,
        "fv_close": 50.0,
        "age": 21.5,
        "current_level": "AA",
        "eta_years": 1.5,
        "statline": {"pa": 80, "k_pct": 18.0, "bb_pct": 12.0, "woba": 0.360},
        "acquisition": {},
        "tools": {},
    }
    p.update(overrides)
    return p


def test_tighter_prior_shrinks_the_gain():
    """THE contract: with the observation fixed, kalman_gain must be
    non-increasing in prior precision (here dialed via n_sources). The
    reverted prior_prec/(prior_prec+obs_n) form makes it INCREASE."""
    gains = []
    for n_sources in (1, 4, 8):
        out = bayesian_trade_value(_prospect(), LEVEL_NORMS, n_sources=n_sources)
        assert out["kalman_gain"] > 0.0, "fixture must trigger the Kalman update"
        gains.append(out["kalman_gain"])
    assert gains[0] > gains[1] >= gains[2], (
        f"tighter prior must shrink the gain; got {gains} for n_sources 1/4/8")


def test_gain_matches_precision_consistent_form():
    """Pin the exact production formula K = 1/(1 + prior_prec * obs_n)
    (uncapped region), built from the module's own helpers."""
    player = _prospect()
    out = bayesian_trade_value(player, LEVEL_NORMS, n_sources=1)
    prior_prec = _prior_precision(player, 1)
    obs_n = _obs_noise(80, False)
    expected = 1.0 / (1.0 + max(1e-6, prior_prec) * obs_n)
    assert expected < 0.22, "fixture drifted into the cap; shrink the sample"
    assert out["kalman_gain"] == pytest.approx(round(expected, 3), abs=1e-9)


def test_gain_cap_holds():
    """A huge, low-noise sample saturates the prospect gain cap at 0.22 -
    outlier rate stats still cannot override the FV hierarchy."""
    big = _prospect(statline={"pa": 6000, "k_pct": 18.0, "bb_pct": 12.0,
                              "woba": 0.360})
    out = bayesian_trade_value(big, LEVEL_NORMS, n_sources=1)
    assert out["kalman_gain"] == 0.22


def test_no_signal_means_zero_gain():
    """No usable statline -> prior only, gain 0 (the documented else-path)."""
    bare = _prospect(statline={})
    out = bayesian_trade_value(bare, LEVEL_NORMS, n_sources=3)
    assert out["kalman_gain"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
