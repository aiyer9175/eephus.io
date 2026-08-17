"""Integration test: schema validation -> split -> leakage audit, as a pipeline (Part AA)."""
from __future__ import annotations

import pytest

from eephus_research.diagnostics.leakage import (
    check_duplicate_keys,
    check_group_overlap,
    combine,
)
from eephus_research.diagnostics.splits import (
    assert_no_group_overlap,
    pitcher_grouped_split,
)
from eephus_research.validation.schema import ColumnContract, SchemaContract


def _clustered_schema() -> SchemaContract:
    return SchemaContract(
        name="clustered_pitch",
        version="1",
        columns=[
            ColumnContract("pitch_id", "int", is_key=True),
            ColumnContract("pitcher_id", "int"),
            ColumnContract("game_id", "int"),
            ColumnContract("velocity", "float"),
            ColumnContract("outcome", "float"),
        ],
    )


def test_full_pipeline_on_clean_data_produces_no_findings(clustered_df):
    _clustered_schema().validate(clustered_df)

    train_mask, test_mask = pitcher_grouped_split(
        clustered_df, pitcher_id_col="pitcher_id", test_frac=0.25, seed=7
    )
    assert_no_group_overlap(clustered_df, "pitcher_id", train_mask, test_mask)

    train_df = clustered_df.loc[train_mask]
    test_df = clustered_df.loc[test_mask]

    report = combine(
        check_duplicate_keys(clustered_df, ["pitch_id"]),
        check_group_overlap(train_df, test_df, "pitcher_id"),
    )
    assert report.clean, report.findings
    assert len(train_df) > 0 and len(test_df) > 0


def test_pipeline_surfaces_duplicate_key_before_split_is_even_attempted(clustered_df):
    corrupted = clustered_df.copy()
    corrupted.loc[1, "pitch_id"] = corrupted.loc[0, "pitch_id"]  # introduce a duplicate key

    with pytest.raises(Exception):
        _clustered_schema().validate(corrupted)  # SchemaValidationError, caught generically here

    # even if a caller pressed on anyway, the leakage checker independently catches it:
    report = check_duplicate_keys(corrupted, ["pitch_id"])
    assert not report.clean
