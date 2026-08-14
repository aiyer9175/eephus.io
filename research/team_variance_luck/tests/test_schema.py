from __future__ import annotations

import pandas as pd
import pytest

from team_variance_luck.schema import REQUIRED_ELO_COLUMNS, validate_elo_features


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "team_id": ["COL"],
            "team_abbr": ["COL"],
            "season": [2026],
            "game_date": ["2026-04-01"],
            "game_id": ["2026-001"],
            "luck_runs": [0.2],
            "variance_runs": [-0.1],
            "injury_context_index": [0.4],
            "roster_health_index": [0.9],
            "schedule_variance_index": [0.2],
            "expected_win_delta": [0.01],
            "confidence": [0.8],
            "model_version": ["test-v1"],
        }
    )


def test_valid_minimal_dataframe_passes() -> None:
    result = validate_elo_features(valid_frame())
    assert len(result) == 1
    assert pd.api.types.is_datetime64_any_dtype(result["game_date"])


def test_missing_required_column_fails() -> None:
    with pytest.raises(ValueError, match="Missing required"):
        validate_elo_features(valid_frame().drop(columns="game_id"))


def test_forbidden_column_fails() -> None:
    frame = valid_frame().assign(player_name="Private Detail")
    with pytest.raises(ValueError, match="Forbidden"):
        validate_elo_features(frame)


def test_confidence_outside_range_fails() -> None:
    with pytest.raises(ValueError, match="confidence"):
        validate_elo_features(valid_frame().assign(confidence=1.1))


def test_output_column_order_is_canonical() -> None:
    frame = valid_frame()[list(reversed(REQUIRED_ELO_COLUMNS))]
    assert list(validate_elo_features(frame).columns) == REQUIRED_ELO_COLUMNS
