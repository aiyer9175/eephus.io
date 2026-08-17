"""Reusable leakage checker (docs/STATISTICAL_GOVERNANCE.md, Part AE).

Returns explicit findings. Never silently passes -- an empty findings list
IS the pass signal, and callers should check for that rather than assuming
"no exception raised" means "no leakage found."
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class LeakageReport:
    findings: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return len(self.findings) == 0

    def add(self, message: str) -> None:
        self.findings.append(message)


def check_duplicate_keys(df: pd.DataFrame, key_cols: list[str]) -> LeakageReport:
    report = LeakageReport()
    dup_count = int(df.duplicated(subset=key_cols).sum())
    if dup_count > 0:
        report.add(f"{dup_count} duplicate row(s) on key {key_cols}")
    return report


def check_train_test_row_overlap(
    train_df: pd.DataFrame, test_df: pd.DataFrame, key_cols: list[str]
) -> LeakageReport:
    report = LeakageReport()
    train_keys = set(map(tuple, train_df[key_cols].to_numpy()))
    test_keys = set(map(tuple, test_df[key_cols].to_numpy()))
    overlap = train_keys & test_keys
    if overlap:
        report.add(
            f"{len(overlap)} row(s), identified by key {key_cols}, appear in "
            f"both train and test"
        )
    return report


def check_group_overlap(
    train_df: pd.DataFrame, test_df: pd.DataFrame, group_col: str
) -> LeakageReport:
    report = LeakageReport()
    overlap = set(train_df[group_col].unique()) & set(test_df[group_col].unique())
    if overlap:
        report.add(
            f"{len(overlap)} value(s) of '{group_col}' appear in both train "
            f"and test"
        )
    return report


def check_exact_target_leakage(
    df: pd.DataFrame, feature_cols: list[str], target_col: str
) -> LeakageReport:
    """A feature that's just the target (or an affine transform of it) is exact leakage."""
    report = LeakageReport()
    target = df[target_col].to_numpy(dtype=float)
    for col in feature_cols:
        if col == target_col:
            continue
        try:
            feature = df[col].to_numpy(dtype=float)
        except (TypeError, ValueError):
            continue
        if np.array_equal(feature, target):
            report.add(f"feature '{col}' is identical to target '{target_col}'")
            continue
        if np.std(feature) > 0 and np.std(target) > 0:
            corr = float(np.corrcoef(feature, target)[0, 1])
            if abs(corr) > 0.999:
                report.add(
                    f"feature '{col}' correlates {corr:.6f} with target "
                    f"'{target_col}' -- check for a near-affine leak"
                )
    return report


def check_normalization_fit_scope(
    fit_row_count: int, expected_train_row_count: int
) -> LeakageReport:
    """Guards against a scaler/encoder fit on the full dataset instead of the training split."""
    report = LeakageReport()
    if fit_row_count != expected_train_row_count:
        report.add(
            f"transformation was fit on {fit_row_count} rows but the "
            f"training split has {expected_train_row_count} rows -- likely "
            f"fit on data outside the training split"
        )
    return report


def combine(*reports: LeakageReport) -> LeakageReport:
    combined = LeakageReport()
    for r in reports:
        combined.findings.extend(r.findings)
    return combined
