from __future__ import annotations

import numpy as np
import pytest

from eephus_research.diagnostics.splits import (
    SplitIntegrityError,
    assert_no_group_overlap,
    game_grouped_split,
    pitcher_grouped_split,
    pitcher_grouped_temporal_split,
    random_row_split,
    temporal_split,
)


def test_random_row_split_produces_disjoint_rows(clustered_df):
    train_mask, test_mask = random_row_split(clustered_df, test_frac=0.3, seed=1)
    assert not (train_mask & test_mask).any()
    assert (train_mask | test_mask).all()


def test_pitcher_grouped_split_never_splits_a_pitcher_across_sets(clustered_df):
    train_mask, test_mask = pitcher_grouped_split(clustered_df, "pitcher_id", test_frac=0.3, seed=1)
    assert_no_group_overlap(clustered_df, "pitcher_id", train_mask, test_mask)  # must not raise


def test_game_grouped_split_never_splits_a_game_across_sets(clustered_df):
    train_mask, test_mask = game_grouped_split(clustered_df, "game_id", test_frac=0.3, seed=1)
    assert_no_group_overlap(clustered_df, "game_id", train_mask, test_mask)


def test_assert_no_group_overlap_actually_detects_a_real_violation(clustered_df):
    # deliberately construct a bad "split" where one pitcher is in both sets
    n = len(clustered_df)
    train_mask = np.ones(n, dtype=bool)  # everyone in train
    test_mask = np.ones(n, dtype=bool)   # everyone in test too -- total overlap
    with pytest.raises(SplitIntegrityError):
        assert_no_group_overlap(clustered_df, "pitcher_id", train_mask, test_mask)


def test_temporal_split_test_set_is_strictly_later(clustered_df):
    train_mask, test_mask = temporal_split(clustered_df, "date", test_frac=0.2)
    if test_mask.any() and train_mask.any():
        assert clustered_df.loc[test_mask, "date"].min() >= clustered_df.loc[train_mask, "date"].max()


def test_pitcher_grouped_temporal_split_is_both_grouped_and_temporal(clustered_df):
    train_mask, test_mask = pitcher_grouped_temporal_split(
        clustered_df, pitcher_id_col="pitcher_id", date_col="date", test_frac=0.2
    )
    assert_no_group_overlap(clustered_df, "pitcher_id", train_mask, test_mask)
    if test_mask.any() and train_mask.any():
        train_pitchers_first_date = clustered_df.loc[train_mask].groupby("pitcher_id")["date"].min()
        test_pitchers_first_date = clustered_df.loc[test_mask].groupby("pitcher_id")["date"].min()
        assert test_pitchers_first_date.min() >= train_pitchers_first_date.max()


def test_splits_are_deterministic_given_same_seed(clustered_df):
    a = pitcher_grouped_split(clustered_df, "pitcher_id", test_frac=0.3, seed=99)
    b = pitcher_grouped_split(clustered_df, "pitcher_id", test_frac=0.3, seed=99)
    assert (a[0] == b[0]).all() and (a[1] == b[1]).all()
