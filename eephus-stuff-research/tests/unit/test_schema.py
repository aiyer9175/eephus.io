from __future__ import annotations

import pandas as pd
import pytest

from eephus_research.validation.schema import (
    ColumnContract,
    SchemaContract,
    SchemaValidationError,
)


def _pitch_schema() -> SchemaContract:
    return SchemaContract(
        name="pitch",
        version="1",
        columns=[
            ColumnContract("pitch_id", "int", nullable=False, is_key=True),
            ColumnContract("velocity", "float", nullable=False, unit="mph", valid_range=(0, 110)),
            ColumnContract("season", "int", nullable=False),
        ],
    )


def test_valid_dataframe_passes():
    df = pd.DataFrame({"pitch_id": [1, 2, 3], "velocity": [92.1, 95.4, 88.0], "season": [2026, 2026, 2026]})
    _pitch_schema().validate(df)  # should not raise


def test_missing_column_fails():
    df = pd.DataFrame({"pitch_id": [1, 2], "velocity": [92.1, 95.4]})
    with pytest.raises(SchemaValidationError, match="missing required columns"):
        _pitch_schema().validate(df)


def test_duplicate_key_fails():
    df = pd.DataFrame({"pitch_id": [1, 1, 2], "velocity": [92.1, 95.4, 88.0], "season": [2026, 2026, 2026]})
    with pytest.raises(SchemaValidationError, match="duplicate"):
        _pitch_schema().validate(df)


def test_nullable_violation_fails():
    df = pd.DataFrame({"pitch_id": [1, 2, None], "velocity": [92.1, 95.4, 88.0], "season": [2026, 2026, 2026]})
    with pytest.raises(SchemaValidationError, match="non-nullable"):
        _pitch_schema().validate(df)


def test_out_of_range_fails():
    df = pd.DataFrame({"pitch_id": [1, 2], "velocity": [92.1, 250.0], "season": [2026, 2026]})
    with pytest.raises(SchemaValidationError, match="valid range"):
        _pitch_schema().validate(df)


def test_dtype_mismatch_fails_season_as_string():
    df = pd.DataFrame(
        {"pitch_id": [1, 2, 3], "velocity": [92.1, 95.4, 88.0], "season": ["2026", "2026", "unknown"]}
    )
    with pytest.raises(SchemaValidationError, match="dtype"):
        _pitch_schema().validate(df)


def test_findings_are_collected_not_short_circuited():
    df = pd.DataFrame({"pitch_id": [1, 1], "velocity": [500.0, -5.0], "season": [2026, 2026]})
    with pytest.raises(SchemaValidationError) as excinfo:
        _pitch_schema().validate(df)
    assert len(excinfo.value.findings) >= 2
