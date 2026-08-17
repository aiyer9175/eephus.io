"""Train/validation split regimes (docs/STATISTICAL_GOVERNANCE.md, Part AF).

Every function returns (train_mask, test_mask) as boolean numpy arrays
aligned to the input dataframe's row order, so callers can do
df[train_mask] / df[test_mask] regardless of which regime was used.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class SplitIntegrityError(AssertionError):
    """Raised when a split violates the grouping/temporal guarantee it claims to provide."""


def random_row_split(
    df: pd.DataFrame, test_frac: float, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n = len(df)
    test_idx = rng.choice(n, size=int(round(n * test_frac)), replace=False)
    test_mask = np.zeros(n, dtype=bool)
    test_mask[test_idx] = True
    return ~test_mask, test_mask


def _grouped_split(
    df: pd.DataFrame, group_col: str, test_frac: float, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    groups = df[group_col].unique()
    rng = np.random.default_rng(seed)
    rng.shuffle(groups)
    n_test_groups = max(1, int(round(len(groups) * test_frac))) if len(groups) > 1 else 0
    test_groups = set(groups[:n_test_groups])
    test_mask = df[group_col].isin(test_groups).to_numpy()
    return ~test_mask, test_mask


def game_grouped_split(
    df: pd.DataFrame, game_id_col: str, test_frac: float, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    return _grouped_split(df, game_id_col, test_frac, seed)


def pitcher_grouped_split(
    df: pd.DataFrame, pitcher_id_col: str, test_frac: float, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    return _grouped_split(df, pitcher_id_col, test_frac, seed)


def temporal_split(
    df: pd.DataFrame, date_col: str, test_frac: float
) -> tuple[np.ndarray, np.ndarray]:
    """Test set is the most-recent test_frac of rows by date_col. No shuffling -- order matters."""
    order = df[date_col].to_numpy().argsort(kind="stable")
    n = len(df)
    n_test = int(round(n * test_frac))
    test_positions = order[n - n_test :] if n_test > 0 else np.array([], dtype=int)
    test_mask = np.zeros(n, dtype=bool)
    test_mask[test_positions] = True
    return ~test_mask, test_mask


def pitcher_grouped_temporal_split(
    df: pd.DataFrame, pitcher_id_col: str, date_col: str, test_frac: float
) -> tuple[np.ndarray, np.ndarray]:
    """Test set: the most-recent test_frac of PITCHERS by their first appearance, entirely held out.

    Combines the pitcher-grouped guarantee (a pitcher never appears in both
    splits) with the temporal guarantee (test pitchers debut later than
    train pitchers) -- the strictest of the five regimes.
    """
    first_seen = df.groupby(pitcher_id_col)[date_col].min().sort_values()
    n_pitchers = len(first_seen)
    n_test = max(1, int(round(n_pitchers * test_frac))) if n_pitchers > 1 else 0
    test_pitchers = set(first_seen.index[n_pitchers - n_test :]) if n_test > 0 else set()
    test_mask = df[pitcher_id_col].isin(test_pitchers).to_numpy()
    return ~test_mask, test_mask


def assert_no_group_overlap(
    df: pd.DataFrame, group_col: str, train_mask: np.ndarray, test_mask: np.ndarray
) -> None:
    train_groups = set(df.loc[train_mask, group_col].unique())
    test_groups = set(df.loc[test_mask, group_col].unique())
    overlap = train_groups & test_groups
    if overlap:
        raise SplitIntegrityError(
            f"{len(overlap)} value(s) of '{group_col}' appear in both train "
            f"and test: {sorted(overlap)[:10]}{'...' if len(overlap) > 10 else ''}"
        )
