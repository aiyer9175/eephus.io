from __future__ import annotations

import pytest

from eephus_research.provenance.manifest import (
    ProductionPathError,
    assert_not_production_path,
    build_manifest_entry,
    config_hash,
    diff_against_baseline,
    load_manifest,
    sha256_file,
    write_manifest,
)


def test_sha256_file_deterministic(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    assert sha256_file(f) == sha256_file(f)


def test_sha256_file_changes_with_content(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello")
    h1 = sha256_file(f)
    f.write_text("hello world")
    h2 = sha256_file(f)
    assert h1 != h2


def test_config_hash_order_independent():
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})


def test_config_hash_sensitive_to_values():
    assert config_hash({"a": 1}) != config_hash({"a": 2})


def test_build_manifest_entry_roundtrip(tmp_path):
    f = tmp_path / "artifact.csv"
    f.write_text("x,y\n1,2\n")
    entry = build_manifest_entry(f, producer="test_manifest", producer_version="0.1.0")
    out = tmp_path / "manifest.json"
    write_manifest([entry], out)
    loaded = load_manifest(out)
    assert loaded[0]["sha256"] == entry.sha256
    assert loaded[0]["producer"] == "test_manifest"


def test_build_manifest_entry_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_manifest_entry(tmp_path / "nope.csv", producer="x", producer_version="1")


def test_diff_against_baseline_byte_identical(tmp_path):
    f = tmp_path / "artifact.csv"
    f.write_text("x,y\n1,2\n")
    entry = build_manifest_entry(f, producer="p", producer_version="1").to_dict()
    result = diff_against_baseline(current=entry, baseline=entry)
    assert result["byte_identical"] is True
    assert result["changed_fields"] == {}


def test_diff_against_baseline_detects_change(tmp_path):
    f = tmp_path / "artifact.csv"
    f.write_text("x,y\n1,2\n")
    baseline = build_manifest_entry(f, producer="p", producer_version="1").to_dict()
    f.write_text("x,y\n1,3\n")  # content changed
    current = build_manifest_entry(f, producer="p", producer_version="1").to_dict()
    result = diff_against_baseline(current=current, baseline=baseline)
    assert result["byte_identical"] is False
    assert "sha256" in result["changed_fields"]


@pytest.mark.parametrize(
    "path",
    [
        "../defense-plus/model.pkl",
        "../swing-plus/output.csv",
        "../milb-projections/adapters/export_identity.py",
        "../xwoba_model.pkl",
    ],
)
def test_assert_not_production_path_blocks_known_production_dirs(path):
    with pytest.raises(ProductionPathError):
        assert_not_production_path(path)


def test_assert_not_production_path_allows_research_dir(tmp_path):
    assert_not_production_path(tmp_path / "eephus-stuff-research" / "data" / "raw" / "x.csv")
