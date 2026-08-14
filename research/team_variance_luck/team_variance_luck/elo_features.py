"""Build a safe, schema-only table for downstream ELO consumers."""

from __future__ import annotations

import pandas as pd

from .schema import (
    FORBIDDEN_ELO_EXPORT_COLUMNS,
    REQUIRED_ELO_COLUMNS,
    validate_elo_features,
)


def select_elo_feature_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Reject forbidden detail, then select and validate ELO-facing columns."""
    forbidden = sorted(set(df.columns) & FORBIDDEN_ELO_EXPORT_COLUMNS)
    if forbidden:
        raise ValueError(f"Forbidden ELO export columns present: {forbidden}")

    missing = [column for column in REQUIRED_ELO_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required ELO columns: {missing}")

    return validate_elo_features(df.loc[:, REQUIRED_ELO_COLUMNS])
