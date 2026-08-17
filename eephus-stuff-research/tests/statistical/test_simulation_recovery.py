"""A method that can't recover a known simulated truth should not be trusted on real data (Part AD)."""
from __future__ import annotations

import numpy as np
import pytest

from eephus_research.statistics.simulation import (
    SimulationConfig,
    recovers_true_effect,
    simulate_clustered_data,
)


def _ols_slope(df) -> float:
    x = df["x"].to_numpy()
    y = df["y"].to_numpy()
    design = np.column_stack([np.ones_like(x), x])
    coeffs, *_ = np.linalg.lstsq(design, y, rcond=None)
    return float(coeffs[1])


@pytest.mark.parametrize("true_effect", [0.0, 0.8, -0.8])
def test_ols_recovers_true_effect_with_low_noise(true_effect):
    config = SimulationConfig(
        n_clusters=100, obs_per_cluster=40, true_effect=true_effect,
        noise_sd=0.5, cluster_heterogeneity_sd=0.1, seed=1,
    )
    df = simulate_clustered_data(config)
    estimated = _ols_slope(df)
    assert recovers_true_effect(estimated, true_effect, tolerance=0.15)


def test_simulation_is_deterministic_given_seed():
    config = SimulationConfig(seed=123)
    df1 = simulate_clustered_data(config)
    df2 = simulate_clustered_data(config)
    assert df1.equals(df2)


def test_higher_noise_widens_estimate_dispersion_across_seeds():
    low_noise_estimates = []
    high_noise_estimates = []
    for seed in range(10):
        low = simulate_clustered_data(SimulationConfig(true_effect=0.5, noise_sd=0.2, seed=seed))
        high = simulate_clustered_data(SimulationConfig(true_effect=0.5, noise_sd=5.0, seed=seed))
        low_noise_estimates.append(_ols_slope(low))
        high_noise_estimates.append(_ols_slope(high))
    assert np.std(high_noise_estimates) > np.std(low_noise_estimates)


def test_missingness_produces_expected_nan_fraction():
    config = SimulationConfig(n_clusters=50, obs_per_cluster=20, missingness_frac=0.3, seed=1)
    df = simulate_clustered_data(config)
    observed_frac = df["y"].isna().mean()
    assert abs(observed_frac - 0.3) < 0.05
