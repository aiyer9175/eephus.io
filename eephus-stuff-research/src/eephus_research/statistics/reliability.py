"""Reliability-as-a-function-of-exposure infrastructure (Part AM).

No specific reliability estimator or sample-size cutoff is endorsed here --
infrastructure only, per the mega-spec's Part AM. A future program decides
which of these to actually rely on for a given metric.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def split_half_reliability(
    df: pd.DataFrame, id_col: str, value_col: str, seed: int
) -> float:
    """Correlation between two random halves of each id's observations, averaged per id then Pearson'd.

    Concretely: for each id, randomly split its rows into two halves,
    take the mean of value_col in each half, then correlate the two
    resulting per-id series across all ids. This is the classic split-half
    reliability construction -- NOT a claim about what threshold counts as
    "reliable enough" (that's a research decision, not an infrastructure
    default).
    """
    rng = np.random.default_rng(seed)
    half_a_means = []
    half_b_means = []
    for _, group in df.groupby(id_col):
        vals = group[value_col].to_numpy()
        if len(vals) < 2:
            continue
        idx = rng.permutation(len(vals))
        mid = len(vals) // 2
        half_a_means.append(vals[idx[:mid]].mean())
        half_b_means.append(vals[idx[mid:]].mean())
    if len(half_a_means) < 2:
        return float("nan")
    return float(np.corrcoef(half_a_means, half_b_means)[0, 1])


def stabilization_curve(
    df: pd.DataFrame, id_col: str, value_col: str, seed: int, sample_size_bins: list[int]
) -> pd.DataFrame:
    """Split-half reliability computed separately within subsets capped at each bin size.

    For each n in sample_size_bins, keep only the first n rows per id (after
    a seeded shuffle) and recompute split-half reliability on that subset --
    producing an empirical reliability-vs-exposure curve rather than
    assuming one from a rule of thumb.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for n in sample_size_bins:
        capped_parts = [
            group.sample(frac=1, random_state=int(rng.integers(0, 2**31))).head(n)
            for _, group in df.groupby(id_col)
        ]
        capped = pd.concat(capped_parts, ignore_index=True)
        reliability = split_half_reliability(capped, id_col, value_col, seed)
        rows.append({"max_n_per_id": n, "reliability": reliability, "n_ids": capped[id_col].nunique()})
    return pd.DataFrame(rows)


def empirical_bayes_shrinkage(
    group_means: pd.Series, group_counts: pd.Series, league_mean: float
) -> pd.Series:
    """Simple (Morrissey-style) shrinkage: shrink each group's mean toward league_mean
    in proportion to its count relative to the between-group variance of group_means.

    shrunk = league_mean + reliability_i * (group_mean_i - league_mean)
    where reliability_i = n_i / (n_i + k), k estimated from the variance of
    group_means (a coarse method-of-moments estimate, not a full
    empirical-Bayes fit -- documented as such rather than dressed up as one).
    """
    var_between = float(group_means.var(ddof=1))
    if var_between <= 0 or len(group_means) < 2:
        return pd.Series(league_mean, index=group_means.index)
    # crude k: median count, so median-exposure groups get ~50% shrinkage
    k = float(group_counts.median())
    reliability = group_counts / (group_counts + k)
    return league_mean + reliability * (group_means - league_mean)
