# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the run_monthly output-diff harness (tools/pipeline_artifact_diff).

The harness must fingerprint pipeline artifacts so a runtime optimization can be
proven output-neutral: identical CONTENT must hash the same even when volatile
metadata (generated_at etc.) differs, and any real content change must be
detected.
"""
import json

import tools.pipeline_artifact_diff as pad


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_identical_content_same_fingerprint(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write(a, {"players": [{"k": "v", "n": 1}], "generated_at": "2026-07-01"})
    _write(b, {"players": [{"k": "v", "n": 1}], "generated_at": "2026-07-01"})
    assert pad.fingerprint_file(a) == pad.fingerprint_file(b)


def test_volatile_fields_ignored(tmp_path):
    # Only generated_at / run differ -> same content fingerprint.
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write(a, {"players": [1, 2, 3], "generated_at": "2026-07-01", "run": {"id": 7}})
    _write(b, {"players": [1, 2, 3], "generated_at": "2026-09-09", "run": {"id": 42}})
    assert pad.fingerprint_file(a)["sha256"] == pad.fingerprint_file(b)["sha256"]


def test_content_change_detected(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write(a, {"players": [{"score": 0.5}]})
    _write(b, {"players": [{"score": 0.6}]})   # a real change
    assert pad.fingerprint_file(a)["sha256"] != pad.fingerprint_file(b)["sha256"]


def test_content_key_narrows_hash(tmp_path):
    # With content_key="players", an outer-metadata-only change is invisible...
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _write(a, {"players": [1, 2], "scored_count": 2})
    _write(b, {"players": [1, 2], "scored_count": 999})
    assert pad.fingerprint_file(a, "players")["sha256"] == pad.fingerprint_file(b, "players")["sha256"]
    # ...but a change inside the keyed sub-document is caught.
    _write(b, {"players": [1, 3], "scored_count": 2})
    assert pad.fingerprint_file(a, "players")["sha256"] != pad.fingerprint_file(b, "players")["sha256"]


def test_missing_file_returns_none(tmp_path):
    assert pad.fingerprint_file(tmp_path / "nope.json") is None


def test_snapshot_and_diff_roundtrip(tmp_path, monkeypatch):
    # Point the harness at a temp data dir + temp snapshot dir, write two
    # artifacts that differ only in a volatile field, and confirm diff() reports
    # them identical (exit 0).
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write(data_dir / "grpo_scores.json",
           {"all_scores": {"p1": {"breakout_score": 0.4}}, "generated_at": "2026-07-01"})
    monkeypatch.setattr(pad, "SNAP_DIR", tmp_path / "snaps")
    monkeypatch.setattr(pad, "ARTIFACTS", [{"file": "grpo_scores.json", "content_key": "all_scores"}])

    pad.snapshot("before", data_dir=data_dir)
    # Rewrite with a new timestamp but identical content.
    _write(data_dir / "grpo_scores.json",
           {"all_scores": {"p1": {"breakout_score": 0.4}}, "generated_at": "2026-12-31"})
    pad.snapshot("after", data_dir=data_dir)
    assert pad.diff("before", "after") == 0    # output-neutral

    # A real score change must be flagged (exit 1).
    _write(data_dir / "grpo_scores.json",
           {"all_scores": {"p1": {"breakout_score": 0.9}}, "generated_at": "2026-12-31"})
    pad.snapshot("after2", data_dir=data_dir)
    assert pad.diff("before", "after2") == 1
