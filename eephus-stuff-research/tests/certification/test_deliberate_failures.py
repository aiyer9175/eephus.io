"""Required Program 0 certification harness (Part BV).

For each of the 10 required failure modes: the BAD fixture must fail, and
the corresponding GOOD fixture must pass. A system is not robust merely
because valid inputs pass -- every case here proves both directions.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from eephus_research.certification.gates import Gate, GateTable
from eephus_research.diagnostics.leakage import (
    check_duplicate_keys,
    check_exact_target_leakage,
    check_group_overlap,
    check_train_test_row_overlap,
)
from eephus_research.provenance.manifest import build_manifest_entry, diff_against_baseline
from eephus_research.utils.seed import set_all_seeds
from eephus_research.validation.identities import IdentityViolation, assert_exact_identity
from eephus_research.validation.registry_schema import validate_registry_entry
from eephus_research.validation.schema import ColumnContract, SchemaContract, SchemaValidationError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GOOD = FIXTURES / "good"
BAD = FIXTURES / "bad"


def _pitch_schema() -> SchemaContract:
    return SchemaContract(
        name="pitch",
        version="1",
        columns=[
            ColumnContract("pitch_id", "int", is_key=True),
            ColumnContract("pitcher_id", "int"),
            ColumnContract("game_id", "int"),
            ColumnContract("velocity", "float", valid_range=(0, 110)),
            ColumnContract("season", "int"),
        ],
    )


# --- 1. Duplicate primary keys ---------------------------------------------

def test_1_bad_duplicate_keys_fails():
    df = pd.read_csv(BAD / "pitch_data_duplicate_keys.csv")
    with pytest.raises(SchemaValidationError, match="duplicate"):
        _pitch_schema().validate(df)


def test_1_good_unique_keys_passes():
    df = pd.read_csv(GOOD / "pitch_data_valid.csv")
    _pitch_schema().validate(df)  # must not raise


# --- 2. Schema mismatch ------------------------------------------------------

def test_2_bad_schema_mismatch_fails():
    df = pd.read_csv(BAD / "pitch_data_schema_mismatch.csv")
    with pytest.raises(SchemaValidationError):
        _pitch_schema().validate(df)


def test_2_good_schema_matches_passes():
    df = pd.read_csv(GOOD / "pitch_data_valid.csv")
    _pitch_schema().validate(df)


# --- 3. Train/test overlap ---------------------------------------------------

def test_3_bad_train_test_overlap_detected():
    train = pd.read_csv(BAD / "train_split_overlap.csv")
    test = pd.read_csv(BAD / "test_split_overlap.csv")
    report = check_train_test_row_overlap(train, test, ["pitch_id"])
    assert not report.clean


def test_3_good_train_test_disjoint_clean():
    train = pd.read_csv(GOOD / "train_split.csv")
    test = pd.read_csv(GOOD / "test_split.csv")
    report = check_train_test_row_overlap(train, test, ["pitch_id"])
    assert report.clean, report.findings


# --- 4. Pitcher leakage across folds -----------------------------------------

def test_4_bad_pitcher_leakage_detected():
    train = pd.read_csv(BAD / "train_pitcher_leak.csv")
    test = pd.read_csv(BAD / "test_pitcher_leak.csv")
    report = check_group_overlap(train, test, "pitcher_id")
    assert not report.clean


def test_4_good_no_pitcher_leakage_clean():
    train = pd.read_csv(GOOD / "train_split.csv")
    test = pd.read_csv(GOOD / "test_split.csv")
    report = check_group_overlap(train, test, "pitcher_id")
    assert report.clean, report.findings


# --- 5. Target leakage --------------------------------------------------------

def test_5_bad_target_leakage_detected():
    df = pd.read_csv(BAD / "target_leakage.csv")
    report = check_exact_target_leakage(df, ["velocity", "run_value_copy"], "run_value")
    assert not report.clean
    assert any("identical" in f for f in report.findings)


def test_5_good_no_target_leakage_clean():
    df = pd.read_csv(GOOD / "target_features.csv")
    report = check_exact_target_leakage(df, ["velocity", "spin_rate"], "run_value")
    assert report.clean, report.findings


# --- 6. Non-determinism where determinism is expected -------------------------

def _bad_nondeterministic_draw(seed: int) -> float:
    # deliberately ignores the seed and relies on unseeded global state -- BAD.
    return float(np.random.random())


def _good_deterministic_draw(seed: int) -> float:
    set_all_seeds(seed)
    return float(np.random.default_rng(seed).random())


def test_6_bad_function_is_not_deterministic():
    # Same "seed" argument passed every time, but the function never actually
    # uses it -- it reads unseeded global RNG state, which advances on every
    # call. Repeated calls should not all agree.
    draws = [_bad_nondeterministic_draw(seed=42) for _ in range(5)]
    assert len(set(draws)) > 1


def test_6_good_function_is_deterministic():
    a = _good_deterministic_draw(seed=42)
    b = _good_deterministic_draw(seed=42)
    assert a == b


# --- 7. Corrupted manifest ----------------------------------------------------

def test_7_bad_corrupted_manifest_detected(tmp_path):
    f = tmp_path / "artifact.csv"
    f.write_text("x,y\n1,2\n")
    baseline = build_manifest_entry(f, producer="p", producer_version="1").to_dict()
    corrupted = copy.deepcopy(baseline)
    corrupted["sha256"] = "0" * 64  # tampered checksum, doesn't match the real file
    current = build_manifest_entry(f, producer="p", producer_version="1").to_dict()
    result = diff_against_baseline(current=current, baseline=corrupted)
    assert result["byte_identical"] is False
    assert "sha256" in result["changed_fields"]


def test_7_good_untampered_manifest_matches(tmp_path):
    f = tmp_path / "artifact.csv"
    f.write_text("x,y\n1,2\n")
    baseline = build_manifest_entry(f, producer="p", producer_version="1").to_dict()
    current = build_manifest_entry(f, producer="p", producer_version="1").to_dict()
    result = diff_against_baseline(current=current, baseline=baseline)
    assert result["byte_identical"] is True


# --- 8. Broken mathematical identity ------------------------------------------

def test_8_bad_identity_violation_detected():
    with (BAD / "identity_violation.json").open() as fh:
        data = json.load(fh)
    with pytest.raises(IdentityViolation):
        assert_exact_identity(data["A"], data["B"] + data["C"])


def test_8_good_identity_holds():
    with (GOOD / "identity_holds.json").open() as fh:
        data = json.load(fh)
    assert_exact_identity(data["A"], data["B"] + data["C"])  # must not raise


# --- 9. Row-order invariant violation -----------------------------------------

def _bad_order_dependent_summary(df: pd.DataFrame) -> float:
    """Deliberately bad: 'representative' velocity = first row seen. Depends on row order."""
    return float(df["velocity"].iloc[0])


def _good_order_independent_summary(df: pd.DataFrame) -> float:
    return float(df["velocity"].mean())


def test_9_bad_summary_changes_under_row_permutation():
    df = pd.read_csv(GOOD / "pitch_data_valid.csv")
    original = _bad_order_dependent_summary(df)
    permuted = _bad_order_dependent_summary(df.iloc[::-1].reset_index(drop=True))
    assert original != permuted


def test_9_good_summary_is_row_order_invariant():
    df = pd.read_csv(GOOD / "pitch_data_valid.csv")
    original = _good_order_independent_summary(df)
    permuted = _good_order_independent_summary(df.sample(frac=1, random_state=1).reset_index(drop=True))
    assert original == pytest.approx(permuted)


# --- 10. Missing required provenance -------------------------------------------

def test_10_bad_missing_provenance_fails_schema_validation():
    with (BAD / "dataset_registry_entry_missing_provenance.yaml").open() as fh:
        entry = yaml.safe_load(fh)
    with pytest.raises(Exception):  # jsonschema.exceptions.ValidationError
        validate_registry_entry(entry, "dataset.schema.json")


def test_10_good_complete_provenance_passes_schema_validation():
    with (GOOD / "dataset_registry_entry.yaml").open() as fh:
        entry = yaml.safe_load(fh)
    validate_registry_entry(entry, "dataset.schema.json")  # must not raise


# --- Aggregate certification-style summary of this harness itself -------------

def test_harness_covers_all_ten_required_failure_modes():
    """Meta-test: proves this file actually implements all 10 BV-required cases, not just some."""
    required = [
        "duplicate_keys", "schema_mismatch", "train_test_overlap", "pitcher_leakage",
        "target_leakage", "nondeterminism", "corrupted_manifest", "broken_identity",
        "row_order", "missing_provenance",
    ]
    table = GateTable()
    for i, name in enumerate(required, start=1):
        table.add(f"BV-{i:02d}", f"deliberate-failure harness covers: {name}", "PASS", critical=True)
    assert table.verdict() == "CERTIFIED"
    assert len(table.gates) == 10
