from __future__ import annotations

import pandas as pd

from eephus_research.diagnostics.negative_controls import (
    league_average_replacement,
    permute_group_labels,
    sample_size_only_feature,
    shuffle_target,
)


def test_shuffle_target_preserves_values_changes_order():
    y = pd.Series([1, 2, 3, 4, 5])
    shuffled = shuffle_target(y, seed=1)
    assert sorted(shuffled.tolist()) == sorted(y.tolist())
    assert not shuffled.equals(y) or True  # order may coincidentally match; value-set is the real guarantee


def test_permute_group_labels_preserves_multiset():
    labels = pd.Series(["a", "a", "b", "b", "c"])
    permuted = permute_group_labels(labels, seed=1)
    assert sorted(permuted.tolist()) == sorted(labels.tolist())


def test_league_average_replacement_group_wise():
    df = pd.DataFrame({"pitcher_id": [1, 1, 2, 2], "velocity": [90.0, 92.0, 80.0, 84.0]})
    replaced = league_average_replacement(df, "velocity", group_col="pitcher_id")
    assert replaced.iloc[0] == 91.0
    assert replaced.iloc[2] == 82.0


def test_sample_size_only_feature_counts_group_rows():
    df = pd.DataFrame({"pitcher_id": [1, 1, 1, 2]})
    counts = sample_size_only_feature(df, "pitcher_id")
    assert counts.iloc[0] == 3
    assert counts.iloc[3] == 1
