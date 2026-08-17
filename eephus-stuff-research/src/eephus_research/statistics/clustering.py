"""Cluster-aware uncertainty (docs/STATISTICAL_GOVERNANCE.md, Part Y).

Do not mechanically bootstrap individual rows when the scientific unit of
variation is a cluster (e.g. pitcher) -- these helpers resample clusters,
not rows, on purpose.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd


def cluster_bootstrap(
    df: pd.DataFrame,
    cluster_col: str,
    statistic_fn: Callable[[pd.DataFrame], float],
    n_boot: int,
    seed: int,
) -> np.ndarray:
    """Resample whole clusters with replacement, recompute statistic_fn each time.

    Returns an array of n_boot bootstrap statistic values. Use
    np.percentile(result, [2.5, 97.5]) for a cluster-robust 95% CI, rather
    than a naive per-row bootstrap CI.
    """
    rng = np.random.default_rng(seed)
    clusters = df[cluster_col].unique()
    n_clusters = len(clusters)
    grouped = {c: idx for c, idx in df.groupby(cluster_col).groups.items()}

    results = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        sampled_clusters = rng.choice(clusters, size=n_clusters, replace=True)
        idx = np.concatenate([np.asarray(grouped[c]) for c in sampled_clusters])
        results[b] = statistic_fn(df.loc[idx])
    return results


def cluster_robust_se_of_mean(df: pd.DataFrame, cluster_col: str, value_col: str) -> float:
    """Cluster-robust standard error of a simple mean, via cluster-mean aggregation.

    Treats each cluster's mean as one observation -- a quick, defensible
    approximation when a full bootstrap isn't warranted. Prefer
    cluster_bootstrap for anything consequential.
    """
    cluster_means = df.groupby(cluster_col)[value_col].mean()
    n_clusters = len(cluster_means)
    if n_clusters < 2:
        return float("nan")
    return float(cluster_means.std(ddof=1) / np.sqrt(n_clusters))


def effective_sample_size(df: pd.DataFrame, cluster_col: str) -> dict[str, float]:
    """Report raw row count vs. cluster count -- the gap between the two is the point (Part W)."""
    return {
        "n_rows": float(len(df)),
        "n_clusters": float(df[cluster_col].nunique()),
        "mean_rows_per_cluster": float(len(df) / max(df[cluster_col].nunique(), 1)),
    }
