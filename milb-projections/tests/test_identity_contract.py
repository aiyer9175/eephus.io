"""Contract tests for the identity export adapter.

Covers the charter's Phase 6 requirements: unique authoritative key,
no unexplained many-to-many mapping, and confirmation that redaction
actually removes the full birthdate rather than merely hiding it.
"""
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

ADAPTERS_DIR = Path(__file__).resolve().parent.parent / "adapters"
sys.path.insert(0, str(ADAPTERS_DIR))
import export_identity as adapter  # noqa: E402

SOURCE_PATH = adapter.source_path()


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="career_outcome_plus checkout not available in this environment")
def test_mlbam_id_is_unique_authoritative_key(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    rc = adapter.main()
    assert rc == 0
    df = pd.read_parquet(tmp_path / "identity" / "eephus_identity_redacted.parquet")
    assert not df["mlbam_id"].duplicated().any(), "mlbam_id must be unique -- unexplained many-to-many mapping"


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="career_outcome_plus checkout not available in this environment")
def test_dob_is_fully_removed_not_just_hidden(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    adapter.main()
    df = pd.read_parquet(tmp_path / "identity" / "eephus_identity_redacted.parquet")
    assert "dob" not in df.columns
    assert "birth_year" in df.columns


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="career_outcome_plus checkout not available in this environment")
def test_birth_year_is_derived_not_fabricated(tmp_path, monkeypatch):
    """birth_year must be null wherever the source dob was null/uncovered --
    never backfilled with a guessed value."""
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    adapter.main()
    exported = pd.read_parquet(tmp_path / "identity" / "eephus_identity_redacted.parquet")
    source = pd.read_parquet(SOURCE_PATH)
    uncovered = source.loc[~source["dob_coverage"], "mlbam_id"]
    merged = exported.set_index("mlbam_id").loc[uncovered.values, "birth_year"]
    assert merged.isna().all(), "birth_year must stay null where dob was never covered upstream"


@pytest.mark.skipif(not SOURCE_PATH.exists(), reason="career_outcome_plus checkout not available in this environment")
def test_adapter_does_not_modify_authoritative_source(tmp_path, monkeypatch):
    import hashlib

    before = hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    adapter.main()
    after = hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()
    assert before == after


def test_adapter_never_joins_team_affiliate_mapping():
    """Guards against silently introducing the disjoint team/affiliate/park
    system as an undocumented join -- that system is classified NOT_NEEDED
    (reconstructable from the public MLB Stats API)."""
    source = (ADAPTERS_DIR / "export_identity.py").read_text()
    assert "milb_affiliate_mapping" not in source
    assert "milb_park_mapping" not in source
