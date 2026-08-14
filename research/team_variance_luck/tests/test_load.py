from __future__ import annotations

import importlib.util

import pytest

from team_variance_luck.load import load_elo_features
from test_schema import valid_frame


def test_load_csv(tmp_path) -> None:
    path = tmp_path / "features.csv"
    valid_frame().to_csv(path, index=False)
    assert len(load_elo_features(path)) == 1


@pytest.mark.skipif(
    importlib.util.find_spec("pyarrow") is None,
    reason="pyarrow is an optional dependency",
)
def test_load_parquet(tmp_path) -> None:
    path = tmp_path / "features.parquet"
    valid_frame().to_parquet(path, index=False)
    assert len(load_elo_features(path)) == 1
