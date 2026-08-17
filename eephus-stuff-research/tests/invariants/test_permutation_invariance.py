"""Property-based tests (Part AC): row order must not affect a permutation-invariant aggregate."""
from __future__ import annotations

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st


@st.composite
def small_numeric_series(draw):
    values = draw(st.lists(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False), min_size=1, max_size=50))
    return pd.Series(values)


@given(series=small_numeric_series(), seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=50)
def test_sum_is_row_order_invariant(series, seed):
    permuted = series.sample(frac=1, random_state=seed).reset_index(drop=True)
    assert np.isclose(series.sum(), permuted.sum(), rtol=1e-9, atol=1e-9)


@given(series=small_numeric_series(), seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=50)
def test_mean_is_row_order_invariant(series, seed):
    permuted = series.sample(frac=1, random_state=seed).reset_index(drop=True)
    assert np.isclose(series.mean(), permuted.mean(), rtol=1e-9, atol=1e-9, equal_nan=True)


@given(
    a=st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=30),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
@settings(max_examples=30)
def test_irrelevant_column_does_not_change_an_unrelated_aggregate(a, seed):
    df = pd.DataFrame({"value": a})
    baseline_mean = df["value"].mean()
    df_with_extra_col = df.copy()
    rng = np.random.default_rng(seed)
    df_with_extra_col["irrelevant"] = rng.random(len(df))
    assert np.isclose(df_with_extra_col["value"].mean(), baseline_mean)


def test_split_and_recombine_preserves_additive_total():
    df = pd.DataFrame({"value": np.arange(1, 101)})
    part_a = df.iloc[:37]
    part_b = df.iloc[37:]
    assert np.isclose(part_a["value"].sum() + part_b["value"].sum(), df["value"].sum())
