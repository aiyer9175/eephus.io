"""Compatibility tests for the MiLB park-context export adapter.

These tests exist to satisfy the charter's compatibility requirement: the
handoff export must not alter, recompute, or drift from the authoritative
MiLB park-factor source, and must not touch any existing consumer.

Run with: pytest milb_pitch_quality_handoff/tests/test_park_context_compatibility.py
Requires pandas and a readable ~/milb_park_rebuild checkout (skips otherwise).
"""
import hashlib
import os
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

ADAPTERS_DIR = Path(__file__).resolve().parent.parent / "adapters"
sys.path.insert(0, str(ADAPTERS_DIR))
import export_park_context as adapter  # noqa: E402

SOURCE_PATH = adapter.source_path()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="milb_park_rebuild checkout not available in this environment")
def test_export_matches_authoritative_source_row_for_row(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    rc = adapter.main()
    assert rc == 0

    exported = pd.read_parquet(tmp_path / "park_context" / "milb_park_factors_v2.parquet")
    authoritative = pd.read_parquet(SOURCE_PATH)

    pd.testing.assert_frame_equal(
        exported.sort_values(["season", "team_id"]).reset_index(drop=True),
        authoritative.sort_values(["season", "team_id"]).reset_index(drop=True),
    )


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="milb_park_rebuild checkout not available in this environment")
def test_export_stamps_same_model_version_as_source(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    adapter.main()
    exported = pd.read_parquet(tmp_path / "park_context" / "milb_park_factors_v2.parquet")
    authoritative = pd.read_parquet(SOURCE_PATH)
    assert set(exported["model_version"].unique()) == set(authoritative["model_version"].unique())


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="milb_park_rebuild checkout not available in this environment")
def test_adapter_does_not_modify_authoritative_source(tmp_path, monkeypatch):
    before_hash = _sha256(SOURCE_PATH)
    before_mtime = SOURCE_PATH.stat().st_mtime
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    adapter.main()
    after_hash = _sha256(SOURCE_PATH)
    after_mtime = SOURCE_PATH.stat().st_mtime
    assert before_hash == after_hash, "adapter must never modify the authoritative source file"
    assert before_mtime == after_mtime


def test_adapter_never_reads_the_deprecated_engine_artifact():
    """Guards against ever substituting the deprecated air-density index
    for the v2 empirical park factors inside this handoff package."""
    source = (ADAPTERS_DIR / "export_park_context.py").read_text()
    assert "environment_engine" not in source
    assert "milb_park_factors.parquet" not in source or "milb_park_factors_v2.parquet" in source


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="milb_park_rebuild checkout not available in this environment")
def test_no_duplicate_season_team_id(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    adapter.main()
    exported = pd.read_parquet(tmp_path / "park_context" / "milb_park_factors_v2.parquet")
    assert not exported.duplicated(subset=["season", "team_id"]).any()


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="milb_park_rebuild checkout not available in this environment")
def test_coverage_and_weather_invariants_hold(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    adapter.main()
    exported = pd.read_parquet(tmp_path / "park_context" / "milb_park_factors_v2.parquet")
    assert (exported["coverage_share"] == 1.0).all()
    assert not exported["weather_required"].any()
