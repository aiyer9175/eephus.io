"""Schema contracts for tabular artifacts (docs/DATA_GOVERNANCE.md).

Validation fails loudly. It never silently coerces a structurally
incompatible column -- that is the entire point of this module existing
instead of just calling `df.astype(...)` inline wherever data is loaded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


class SchemaValidationError(ValueError):
    """Raised when a dataframe does not satisfy a SchemaContract. Carries all findings, not just the first."""

    def __init__(self, findings: list[str]):
        self.findings = findings
        super().__init__("; ".join(findings))


@dataclass
class ColumnContract:
    name: str
    dtype: str  # one of: "int", "float", "string", "bool", "datetime"
    nullable: bool = False
    unit: str | None = None
    valid_range: tuple[float, float] | None = None
    semantic_meaning: str = ""
    is_key: bool = False


@dataclass
class SchemaContract:
    name: str
    version: str
    columns: list[ColumnContract] = field(default_factory=list)

    @property
    def key_columns(self) -> list[str]:
        return [c.name for c in self.columns if c.is_key]

    def validate(self, df: pd.DataFrame) -> None:
        findings: list[str] = []

        declared = {c.name for c in self.columns}
        present = set(df.columns)
        missing = declared - present
        if missing:
            findings.append(f"missing required columns: {sorted(missing)}")

        for col in self.columns:
            if col.name not in df.columns:
                continue  # already reported above
            series = df[col.name]

            if not col.nullable and series.isna().any():
                n = int(series.isna().sum())
                findings.append(
                    f"column '{col.name}' is declared non-nullable but has {n} null value(s)"
                )

            dtype_ok = _dtype_matches(series, col.dtype)
            if not dtype_ok:
                findings.append(
                    f"column '{col.name}' has dtype {series.dtype}, expected "
                    f"'{col.dtype}' (declared unit: {col.unit or 'n/a'})"
                )

            if col.valid_range is not None and pd.api.types.is_numeric_dtype(series):
                lo, hi = col.valid_range
                out_of_range = series.dropna()
                out_of_range = out_of_range[(out_of_range < lo) | (out_of_range > hi)]
                if len(out_of_range) > 0:
                    findings.append(
                        f"column '{col.name}' has {len(out_of_range)} value(s) "
                        f"outside declared valid range [{lo}, {hi}]"
                    )

        key_cols = self.key_columns
        if key_cols and set(key_cols).issubset(present):
            dup_count = int(df.duplicated(subset=key_cols).sum())
            if dup_count > 0:
                findings.append(
                    f"declared unique key {key_cols} has {dup_count} duplicate row(s)"
                )

        if findings:
            raise SchemaValidationError(findings)


def _dtype_matches(series: pd.Series, expected: str) -> bool:
    checks = {
        "int": pd.api.types.is_integer_dtype,
        "float": lambda s: pd.api.types.is_float_dtype(s) or pd.api.types.is_integer_dtype(s),
        "string": lambda s: pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s),
        "bool": pd.api.types.is_bool_dtype,
        "datetime": pd.api.types.is_datetime64_any_dtype,
    }
    check = checks.get(expected)
    if check is None:
        raise ValueError(f"Unknown contract dtype '{expected}'")
    return bool(check(series))
