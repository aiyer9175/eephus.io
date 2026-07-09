"""Schema and validation for the stable ELO feature-table contract."""

from __future__ import annotations

import pandas as pd

REQUIRED_ELO_COLUMNS = [
    "team_id",
    "team_abbr",
    "season",
    "game_date",
    "game_id",
    "luck_runs",
    "variance_runs",
    "injury_context_index",
    "roster_health_index",
    "schedule_variance_index",
    "expected_win_delta",
    "confidence",
    "model_version",
]

ELO_COLUMN_DTYPES = {
    "team_id": "string",
    "team_abbr": "string",
    "season": "Int64",
    "game_date": "datetime64[ns]",
    "game_id": "string",
    "luck_runs": "Float64",
    "variance_runs": "Float64",
    "injury_context_index": "Float64",
    "roster_health_index": "Float64",
    "schedule_variance_index": "Float64",
    "expected_win_delta": "Float64",
    "confidence": "Float64",
    "model_version": "string",
}

FORBIDDEN_ELO_EXPORT_COLUMNS = {
    "player_id",
    "player_name",
    "injury_type",
    "body_part",
    "diagnosis",
    "il_reason",
    "medical_note",
    "health_label",
}

_STRING_COLUMNS = ("team_id", "team_abbr", "game_id", "model_version")
_NUMERIC_COLUMNS = (
    "luck_runs",
    "variance_runs",
    "injury_context_index",
    "roster_health_index",
    "schedule_variance_index",
    "expected_win_delta",
    "confidence",
)


def validate_elo_features(df: pd.DataFrame) -> pd.DataFrame:
    """Validate, coerce, and return an ELO table in canonical column order."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("ELO features must be provided as a pandas DataFrame")

    forbidden = sorted(set(df.columns) & FORBIDDEN_ELO_EXPORT_COLUMNS)
    if forbidden:
        raise ValueError(f"Forbidden ELO export columns present: {forbidden}")

    missing = [column for column in REQUIRED_ELO_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required ELO columns: {missing}")

    result = df.loc[:, REQUIRED_ELO_COLUMNS].copy()

    for column in _STRING_COLUMNS:
        result[column] = result[column].astype("string")

    result["game_date"] = pd.to_datetime(result["game_date"], errors="raise")

    season = pd.to_numeric(result["season"], errors="raise")
    if season.isna().any() or (season % 1 != 0).any():
        raise ValueError("season must contain non-null, integer-like values")
    result["season"] = season.astype("Int64")

    for column in _NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="raise").astype("Float64")

    confidence = result["confidence"]
    if confidence.isna().any() or not confidence.between(0, 1, inclusive="both").all():
        raise ValueError("confidence must contain non-null values between 0 and 1")

    return result
