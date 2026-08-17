"""Simulation harness (docs/VALIDATION_STANDARD.md, Part AD).

Generates data with a KNOWN data-generating process, so an estimator can be
checked against ground truth before being trusted on observational data.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SimulationConfig:
    n_clusters: int = 200
    obs_per_cluster: int = 30
    true_effect: float = 0.0
    noise_sd: float = 1.0
    cluster_heterogeneity_sd: float = 0.5
    missingness_frac: float = 0.0
    feature_correlation: float = 0.0
    seed: int = 20260816


def simulate_clustered_data(config: SimulationConfig) -> pd.DataFrame:
    """Simulate a clustered dataset (e.g. pitchers = clusters, pitches = observations).

    y = true_effect * x + cluster_effect + noise

    cluster_effect ~ N(0, cluster_heterogeneity_sd^2), one draw per cluster,
    shared by every observation in that cluster (this is the "pitcher
    heterogeneity" knob). x is optionally correlated with a second feature
    x2 by feature_correlation, so a leakage/collinearity check has something
    real to catch. missingness_frac of y values are set to NaN, uniformly at
    random, to exercise missing-data handling.
    """
    rng = np.random.default_rng(config.seed)
    n = config.n_clusters * config.obs_per_cluster

    cluster_ids = np.repeat(np.arange(config.n_clusters), config.obs_per_cluster)
    cluster_effects = rng.normal(0, config.cluster_heterogeneity_sd, size=config.n_clusters)
    cluster_effect_per_row = cluster_effects[cluster_ids]

    mean = [0, 0]
    cov = [[1, config.feature_correlation], [config.feature_correlation, 1]]
    x, x2 = rng.multivariate_normal(mean, cov, size=n).T

    noise = rng.normal(0, config.noise_sd, size=n)
    y = config.true_effect * x + cluster_effect_per_row + noise

    if config.missingness_frac > 0:
        missing_idx = rng.choice(n, size=int(round(n * config.missingness_frac)), replace=False)
        y[missing_idx] = np.nan

    return pd.DataFrame(
        {
            "cluster_id": cluster_ids,
            "x": x,
            "x2": x2,
            "y": y,
            "row_order_seed": np.arange(n),
        }
    )


def recovers_true_effect(
    estimated_effect: float, true_effect: float, tolerance: float
) -> bool:
    return abs(estimated_effect - true_effect) <= tolerance
