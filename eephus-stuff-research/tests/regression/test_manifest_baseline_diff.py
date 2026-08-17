"""Regression test: frozen-baseline comparison (Part AY) must not rely on modification time alone."""
from __future__ import annotations

import time

from eephus_research.provenance.manifest import build_manifest_entry, diff_against_baseline


def test_touching_a_file_without_changing_content_is_still_byte_identical(tmp_path):
    f = tmp_path / "artifact.csv"
    f.write_text("x,y\n1,2\n")
    baseline = build_manifest_entry(f, producer="p", producer_version="1").to_dict()

    time.sleep(0.01)
    f.write_text("x,y\n1,2\n")  # rewritten with IDENTICAL content -> mtime changes, content doesn't
    current = build_manifest_entry(f, producer="p", producer_version="1").to_dict()

    result = diff_against_baseline(current=current, baseline=baseline)
    assert result["byte_identical"] is True, (
        "modification_time changed but sha256 did not -- byte_identical must "
        "be computed from the hash, not from mtime"
    )


def test_same_mtime_different_content_is_not_byte_identical(tmp_path, monkeypatch):
    f = tmp_path / "artifact.csv"
    f.write_text("x,y\n1,2\n")
    baseline = build_manifest_entry(f, producer="p", producer_version="1").to_dict()

    f.write_text("x,y\n1,999\n")
    current = build_manifest_entry(f, producer="p", producer_version="1").to_dict()

    result = diff_against_baseline(current=current, baseline=baseline)
    assert result["byte_identical"] is False
