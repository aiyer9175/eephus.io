"""Schema, cardinality, temporal, and versioning tests for the pitcher-eWAR
and contact-translation export adapters (charter Phase 13).
"""
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

ADAPTERS_DIR = Path(__file__).resolve().parent.parent / "adapters"
sys.path.insert(0, str(ADAPTERS_DIR))
import export_pitcher_ewar_mlb as mlb_adapter  # noqa: E402
import export_pitcher_ewar_milb as milb_adapter  # noqa: E402
import export_contact_translation as contact_adapter  # noqa: E402

MLB_SRC = mlb_adapter._source_dir() / "data" / "pitcher_ewar.parquet"
MILB_SRC_DIR = milb_adapter._source_dir()
CONTACT_SRC_DIR = contact_adapter._source_dir()


# --- MLB pitcher eWAR ---

@pytest.mark.skipif(not MLB_SRC.exists(), reason="pitcher_ewar checkout not available")
def test_mlb_pitcher_ewar_no_duplicate_player_season(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    assert mlb_adapter.main() == 0
    df = pd.read_parquet(tmp_path / "pitcher_ewar_mlb" / "pitcher_ewar.parquet")
    assert not df.duplicated(subset=["player_id", "season"]).any()


@pytest.mark.skipif(not MLB_SRC.exists(), reason="pitcher_ewar checkout not available")
def test_mlb_pitcher_ewar_model_version_never_null(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    mlb_adapter.main()
    df = pd.read_parquet(tmp_path / "pitcher_ewar_mlb" / "pitcher_ewar.parquet")
    assert df["model_version"].notna().all()
    assert df["as_of_date"].notna().all()


@pytest.mark.skipif(not MLB_SRC.exists(), reason="pitcher_ewar checkout not available")
def test_mlb_pitcher_ewar_adapter_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path / "run1"))
    mlb_adapter.main()
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path / "run2"))
    mlb_adapter.main()
    df1 = pd.read_parquet(tmp_path / "run1" / "pitcher_ewar_mlb" / "pitcher_ewar.parquet")
    df2 = pd.read_parquet(tmp_path / "run2" / "pitcher_ewar_mlb" / "pitcher_ewar.parquet")
    pd.testing.assert_frame_equal(df1, df2)


# --- MiLB pitcher eWAR ---

@pytest.mark.skipif(not (MILB_SRC_DIR / "data" / "aaa_pitcher_ewar.parquet").exists(), reason="milb_pitcher_ewar checkout not available")
def test_milb_pitcher_ewar_never_exports_lowa(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    milb_adapter.main()
    out_dir = tmp_path / "pitcher_ewar_milb"
    exported_files = {p.name for p in out_dir.glob("*.parquet")}
    assert not any("lowa" in name for name in exported_files), "Low-A is INTERNAL_ONLY and must never be exported"


@pytest.mark.skipif(not (MILB_SRC_DIR / "data" / "aaa_pitcher_ewar.parquet").exists(), reason="milb_pitcher_ewar checkout not available")
def test_milb_pitcher_ewar_no_duplicate_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    milb_adapter.main()
    for level_file in ["aaa_pitcher_ewar.parquet", "aa_pitcher_ewar.parquet", "higha_pitcher_ewar.parquet"]:
        df = pd.read_parquet(tmp_path / "pitcher_ewar_milb" / level_file)
        assert not df.duplicated(subset=["player_id", "level", "league", "season"]).any(), level_file


@pytest.mark.skipif(not (MILB_SRC_DIR / "data" / "aa_pitcher_ewar.parquet").exists(), reason="milb_pitcher_ewar checkout not available")
def test_aa_higha_have_no_contact_columns_by_design(tmp_path, monkeypatch):
    """This isn't a bug -- SEM_CORE levels never had a contact component.
    A future consumer must not expect these columns to appear."""
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    milb_adapter.main()
    df = pd.read_parquet(tmp_path / "pitcher_ewar_milb" / "aa_pitcher_ewar.parquet")
    assert "contact_runs_above_average" not in df.columns
    assert "hr_opportunity_runs" not in df.columns


# --- Contact translation ---

@pytest.mark.skipif(not (CONTACT_SRC_DIR / "data" / "latent_rate_talent.parquet").exists(), reason="career_outcome_plus checkout not available")
def test_latent_rate_talent_no_duplicate_batter_season(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    contact_adapter.main()
    df = pd.read_parquet(tmp_path / "contact_translation" / "latent_rate_talent.parquet")
    assert not df.duplicated(subset=["batter", "season"]).any()


@pytest.mark.skipif(not (CONTACT_SRC_DIR / "data" / "milb_xwar_projection.parquet").exists(), reason="career_outcome_plus checkout not available")
def test_milb_xwar_projection_no_duplicate_batter_season_level(tmp_path, monkeypatch):
    monkeypatch.setenv("EEPHUS_HANDOFF_PRIVATE_OUT", str(tmp_path))
    contact_adapter.main()
    df = pd.read_parquet(tmp_path / "contact_translation" / "milb_xwar_projection.parquet")
    assert not df.duplicated(subset=["batter", "season", "level"]).any()


# --- Reproducibility / portability ---

def test_no_adapter_hardcodes_a_username_path():
    import re
    for path in ADAPTERS_DIR.glob("*.py"):
        source = path.read_text()
        # flags e.g. /Users/willcahoon or /home/someuser as a literal default
        assert not re.search(r"/Users/\w+/(?!eephus_handoff_private_exports)", source) or "os.environ.get" in source, (
            f"{path.name} appears to hardcode a user-specific path outside an env-var default"
        )
        assert "willcahoon" not in source or 'os.environ.get("EEPHUS' in source


def test_all_adapters_read_config_from_environment_not_argv_only():
    for path in ADAPTERS_DIR.glob("export_*.py"):
        source = path.read_text()
        assert "os.environ.get(" in source, f"{path.name} must read its source/output paths from env vars with documented defaults"
