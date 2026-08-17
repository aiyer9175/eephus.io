from __future__ import annotations

import numpy as np

from eephus_research.statistics.clustering import (
    cluster_bootstrap,
    cluster_robust_se_of_mean,
    effective_sample_size,
)


def test_effective_sample_size_reports_both_grains(clustered_df):
    result = effective_sample_size(clustered_df, "pitcher_id")
    assert result["n_rows"] == len(clustered_df)
    assert result["n_clusters"] == clustered_df["pitcher_id"].nunique()
    assert result["n_clusters"] < result["n_rows"]  # the whole point: clusters != rows


def test_cluster_bootstrap_returns_n_boot_values(clustered_df):
    results = cluster_bootstrap(
        clustered_df, "pitcher_id", lambda df: df["velocity"].mean(), n_boot=50, seed=1
    )
    assert len(results) == 50
    assert np.isfinite(results).all()


def test_cluster_bootstrap_deterministic_given_seed(clustered_df):
    a = cluster_bootstrap(clustered_df, "pitcher_id", lambda df: df["velocity"].mean(), n_boot=20, seed=5)
    b = cluster_bootstrap(clustered_df, "pitcher_id", lambda df: df["velocity"].mean(), n_boot=20, seed=5)
    assert np.allclose(a, b)


def test_cluster_bootstrap_ci_contains_true_mean(clustered_df):
    results = cluster_bootstrap(
        clustered_df, "pitcher_id", lambda df: df["velocity"].mean(), n_boot=500, seed=1
    )
    lo, hi = np.percentile(results, [2.5, 97.5])
    assert lo <= clustered_df["velocity"].mean() <= hi


def test_cluster_robust_se_is_positive(clustered_df):
    se = cluster_robust_se_of_mean(clustered_df, "pitcher_id", "velocity")
    assert se > 0
