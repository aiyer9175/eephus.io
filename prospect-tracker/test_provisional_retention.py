# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PV-02: the served provisional grade is retained nightly (provisional_history.py).

Pinned: a retained snapshot reloads to exactly the served rows; a re-run on the same
build adds nothing; a snapshot file is never rewritten; and a digest row written one
night survives the deploy box's `git checkout -- .` before the next night, replayed
here against a real scratch repository. Also: the tracked digest is not ignored, the
snapshot store is, and neither ships to the webroot.

Every write goes to tmp_path; nothing here touches data/ or .cache/.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import provisional_history as PH

ROOT = Path(__file__).resolve().parent


def _artifact(path: Path, date: str, grades: dict[str, float]) -> Path:
    doc = {"meta": {"generated_at": date},
           "by_player": {k: {"mlbam_id": 100 + i, "side": "H" if i % 2 else "P",
                             "level": "DSL", "age": 18.5, "xfv_grade": g, "p_bust": 0.9,
                             "factors": [{"k": "ignored"}]}
                         for i, (k, g) in enumerate(sorted(grades.items()))}}
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_snapshot_reloads_to_the_served_rows(tmp_path):
    src = _artifact(tmp_path / "xfv_ungraded.json", "2026-10-01", {"a": 31.2, "b": 24.0, "c": 40.1})
    res = PH.retain(src, cache_dir=tmp_path / "cache", digest_path=tmp_path / "dig" / "digest.json",
                    now_iso="2026-10-01T09:00:00+00:00")
    assert res["status"] == "ok" and res["appended"] == 1 and res["n_rows"] == 3
    rows = PH.load_digest(tmp_path / "dig" / "digest.json", tmp_path / "cache")
    head, snap = PH.load_snapshot(tmp_path / "cache" / rows[0]["snapshot"])
    assert head["date"] == "2026-10-01"
    want = PH.rows_from_artifact(json.loads(src.read_text(encoding="utf-8")))
    assert snap == want
    assert {r["key"]: r["grade"] for r in snap} == {"a": 31.2, "b": 24.0, "c": 40.1}
    assert set(snap[0]) == set(PH.COLUMNS)


def test_rerun_on_the_same_build_adds_nothing_and_never_rewrites(tmp_path):
    src = _artifact(tmp_path / "x.json", "2026-10-01", {"a": 30.0})
    kw = dict(cache_dir=tmp_path / "cache", digest_path=tmp_path / "digest.json")
    PH.retain(src, now_iso="2026-10-01T09:00:00+00:00", **kw)
    snap = tmp_path / "cache" / "2026" / "2026-10-01.json.gz"
    before = snap.read_bytes()
    res = PH.retain(src, now_iso="2026-10-01T10:00:00+00:00", **kw)
    assert res["appended"] == 0 and res["n_digest_rows"] == 1
    assert snap.read_bytes() == before
    # Same date, different served rows: a second file, the first untouched.
    _artifact(src, "2026-10-01", {"a": 33.0})
    res = PH.retain(src, now_iso="2026-10-01T11:00:00+00:00", **kw)
    assert res["appended"] == 1 and res["n_digest_rows"] == 2
    assert snap.read_bytes() == before
    assert len(list((tmp_path / "cache" / "2026").glob("*.json.gz"))) == 2
    assert len((tmp_path / "cache" / "digest.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_a_tampered_snapshot_is_refused(tmp_path):
    import gzip
    src = _artifact(tmp_path / "x.json", "2026-10-01", {"a": 30.0, "b": 21.0})
    PH.retain(src, cache_dir=tmp_path / "c", digest_path=tmp_path / "d.json")
    p = tmp_path / "c" / "2026" / "2026-10-01.json.gz"
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        body = json.load(fh)
    body["rows"][0][5] = 45.0
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(body, fh)
    with pytest.raises(ValueError):
        PH.load_snapshot(p)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_digest_survives_the_nightly_git_checkout(tmp_path):
    """Night 1 retains and writes the tracked digest; the box then runs
    `git checkout -- .`, which restores the committed (empty) digest; night 2
    must still carry night 1's row, from the untracked durable copy."""
    repo = tmp_path / "box"
    (repo / "data" / "provisional_history").mkdir(parents=True)
    (repo / ".gitignore").write_text(".cache/\ndata/xfv_ungraded.json\n", encoding="utf-8")
    dig = repo / "data" / "provisional_history" / "digest.json"
    dig.write_text(json.dumps({"schema": 1, "rows": []}), encoding="utf-8")

    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    git("init", "-q")
    git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "seed")

    src = repo / "data" / "xfv_ungraded.json"
    kw = dict(cache_dir=repo / ".cache" / "provisional_history", digest_path=dig)
    _artifact(src, "2026-10-01", {"a": 30.0, "b": 25.5})
    PH.retain(src, now_iso="2026-10-01T09:00:00+00:00", **kw)
    assert [r["date"] for r in json.loads(dig.read_text(encoding="utf-8"))["rows"]] == ["2026-10-01"]

    git("checkout", "--", ".")                      # the box, before the next pull
    assert json.loads(dig.read_text(encoding="utf-8"))["rows"] == []

    _artifact(src, "2026-10-02", {"a": 30.4, "b": 25.5})
    res = PH.retain(src, now_iso="2026-10-02T09:00:00+00:00", **kw)
    rows = json.loads(dig.read_text(encoding="utf-8"))["rows"]
    assert [r["date"] for r in rows] == ["2026-10-01", "2026-10-02"], res
    head, snap = PH.load_snapshot(repo / ".cache" / "provisional_history" / rows[0]["snapshot"])
    assert {r["key"]: r["grade"] for r in snap} == {"a": 30.0, "b": 25.5}


def test_the_store_is_untracked_the_digest_tracked_and_neither_ships():
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")

    def ignored(rel):
        return subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", rel]).returncode == 0
    assert ignored(".cache/provisional_history/2026/2026-10-01.json.gz")
    assert not ignored("data/provisional_history/digest.json")
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert "provisional_history" not in nightly
    assert "provisional_history" not in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    # data/ depth two (the conftest mirror redirects the constant, so read the source).
    src = (ROOT / "provisional_history.py").read_text(encoding="utf-8")
    assert 'DIGEST_PATH = DATA_DIR / "provisional_history" / "digest.json"' in src


def test_the_committed_digest_names_only_served_fields():
    p = ROOT / "data" / "provisional_history" / "digest.json"
    if not p.exists():
        pytest.skip("no committed digest yet")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["columns"] == list(PH.COLUMNS)
    assert not any("war" in c for c in doc["columns"])
    for r in doc["rows"]:
        assert r["n_rows"] > 0 and len(r["sha256_rows"]) == 64
