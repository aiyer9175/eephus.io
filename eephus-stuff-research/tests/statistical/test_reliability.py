from __future__ import annotations

import numpy as np
import pandas as pd

from eephus_research.statistics.reliability import (
    empirical_bayes_shrinkage,
    split_half_reliability,
    stabilization_curve,
)


def _stable_signal_df(n_ids=60, n_per_id=40, seed=1) -> pd.DataFrame:
    """Each id has a true underlying mean; value = true_mean + noise, so split-half reliability should be high."""
    rng = np.random.default_rng(seed)
    true_means = rng.normal(0, 1, n_ids)
    ids = np.repeat(np.arange(n_ids), n_per_id)
    noise = rng.normal(0, 0.3, n_ids * n_per_id)
    values = true_means[ids] + noise
    return pd.DataFrame({"id": ids, "value": values})


def _pure_noise_df(n_ids=60, n_per_id=40, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ids = np.repeat(np.arange(n_ids), n_per_id)
    values = rng.normal(0, 1, n_ids * n_per_id)
    return pd.DataFrame({"id": ids, "value": values})


def test_split_half_reliability_high_for_stable_signal():
    df = _stable_signal_df()
    r = split_half_reliability(df, "id", "value", seed=1)
    assert r > 0.8


def test_split_half_reliability_low_for_pure_noise():
    df = _pure_noise_df()
    r = split_half_reliability(df, "id", "value", seed=1)
    assert r < 0.5


def test_stabilization_curve_improves_with_more_exposure():
    df = _stable_signal_df(n_per_id=100)
    curve = stabilization_curve(df, "id", "value", seed=1, sample_size_bins=[5, 20, 80])
    reliabilities = curve.sort_values("max_n_per_id")["reliability"].to_numpy()
    assert reliabilities[-1] >= reliabilities[0]  # more exposure should not make reliability worse


def test_empirical_bayes_shrinkage_pulls_low_count_groups_toward_league_mean():
    group_means = pd.Series({"a": 10.0, "b": 0.0}, name="mean")
    group_counts = pd.Series({"a": 1000, "b": 1}, name="count")
    league_mean = 5.0
    shrunk = empirical_bayes_shrinkage(group_means, group_counts, league_mean)
    # group 'a' has huge sample size -> barely shrunk toward league mean
    assert abs(shrunk["a"] - group_means["a"]) < abs(shrunk["b"] - group_means["b"])
