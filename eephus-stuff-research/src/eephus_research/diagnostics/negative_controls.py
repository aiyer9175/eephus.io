"""Negative-control construction (docs/VALIDATION_STANDARD.md, Part AJ).

A model should beat these controls by a documented, non-trivial margin.
This module builds the control datasets/labels; it does not judge whether a
given model beat them -- that comparison belongs to the experiment that
uses these.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def shuffle_target(y: pd.Series, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    shuffled = rng.permutation(y.to_numpy())
    return pd.Series(shuffled, index=y.index, name=y.name)


def permute_group_labels(labels: pd.Series, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    permuted = rng.permutation(labels.to_numpy())
    return pd.Series(permuted, index=labels.index, name=labels.name)


def league_average_replacement(
    df: pd.DataFrame, value_col: str, group_col: str | None = None
) -> pd.Series:
    """Replace every value with the (optionally group-wise) mean.

    E.g. league_average_replacement(df, "velocity") answers: how much
    apparent signal survives if every pitcher's velocity is replaced by the
    league mean? A large drop in apparent model performance under this
    control is evidence velocity (or whatever column) was actually
    contributing something real.
    """
    if group_col is None:
        return pd.Series(
            np.full(len(df), df[value_col].mean()), index=df.index, name=value_col
        )
    return df.groupby(group_col)[value_col].transform("mean")


def sample_size_only_feature(df: pd.DataFrame, group_col: str) -> pd.Series:
    """Raw observation count per group, as a feature. If THIS alone predicts the outcome well,
    that's a survivorship/opportunity-bias red flag, not a skill signal."""
    return df.groupby(group_col)[group_col].transform("count").rename("n_observations")
