# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""tools/port_bundle.py: the port's state-transfer bundle (docs/port/PORT_RUNBOOK.md).

Pins the cache rule of PORT_SPEC.md 1.4.1 (carry everything under .cache/ that is
not inside a prune_cache.SAFE_CACHES directory, the tuple imported and not
transcribed), the import/served split of gitignored data/ files, and a verify
pass that is shown to catch a changed file (positive control)."""

import sqlite3
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import port_bundle as pb  # noqa: E402
import prune_cache  # noqa: E402


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "mod"
    cache = root / ".cache"
    (cache / prune_cache.SAFE_CACHES[0]).mkdir(parents=True)
    (cache / prune_cache.SAFE_CACHES[0] / "feed.json").write_text("{}", encoding="utf-8")
    (cache / "leaderboard_vintages").mkdir()
    (cache / "leaderboard_vintages" / "2026-10-01.json").write_text("[1]", encoding="utf-8")
    (cache / "win_prob_hist").mkdir()
    (cache / "win_prob_hist" / "1.json").write_text("[2]", encoding="utf-8")
    (cache / "fg_player_x.html").write_text("<p>fg</p>", encoding="utf-8")
    (cache / "proj_ml_pit_v1.joblib").write_bytes(b"\x00\x01")
    (root / "data" / "fangraphs_imports").mkdir(parents=True)
    (root / "data" / "fangraphs_imports" / "a.csv").write_text("x,y\n", encoding="utf-8")
    (root / "data" / "timeseries.json").write_text("{}", encoding="utf-8")
    (root / "data" / "prospects.db").write_bytes(b"")
    con = sqlite3.connect(str(root / "prospects.db"))
    con.execute("CREATE TABLE t (a INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()
    return root


def _ignored(monkeypatch):
    monkeypatch.setattr(pb, "_git_ignored_under_data", lambda root: [
        "data/fangraphs_imports/a.csv", "data/prospects.db", "data/timeseries.json"])


def test_safe_caches_is_the_imported_tuple():
    assert pb.SAFE_CACHES is prune_cache.SAFE_CACHES


def test_also_carry_names_safe_dirs_with_pinned_inputs():
    assert set(pb.LEAVE_BEHIND) <= set(prune_cache.SAFE_CACHES)
    assert set(pb.ALSO_CARRY) | set(pb.LEAVE_BEHIND) == set(prune_cache.SAFE_CACHES)
    assert "savant_mlb" in pb.ALSO_CARRY       # prospect_statline pins expected_*.csv
    assert "milb_stats" in pb.ALSO_CARRY       # efv_surrogate pins 2005 to 2013 seasons


def test_also_carry_dir_travels(tmp_path):
    root = _tree(tmp_path)
    (root / ".cache" / "savant_mlb").mkdir()
    (root / ".cache" / "savant_mlb" / "expected_batter_2020.csv").write_text("a\n", encoding="utf-8")
    rels = [p.relative_to(root / ".cache").as_posix()
            for p in pb.cache_carry_files(root / ".cache")]
    assert "savant_mlb/expected_batter_2020.csv" in rels


def test_carry_rule_skips_safe_dirs_only(tmp_path):
    root = _tree(tmp_path)
    rels = sorted(p.relative_to(root / ".cache").as_posix()
                  for p in pb.cache_carry_files(root / ".cache"))
    assert rels == ["fg_player_x.html", "leaderboard_vintages/2026-10-01.json",
                    "proj_ml_pit_v1.joblib", "win_prob_hist/1.json"]
    rels = sorted(p.relative_to(root / ".cache").as_posix()
                  for p in pb.cache_carry_files(root / ".cache", ("win_prob_hist",)))
    assert "win_prob_hist/1.json" not in rels and len(rels) == 3


def test_data_split_keeps_imports_apart_and_drops_strays(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    _ignored(monkeypatch)
    imports, served = pb.split_data_files(root)
    assert imports == ["data/fangraphs_imports/a.csv"]
    assert served == ["data/timeseries.json"]


def test_ignored_files_in_page_dirs_travel_with_the_imports(tmp_path, monkeypatch):
    """collegesavant/logos/ is gitignored and served: a clean clone had none."""
    root = _tree(tmp_path)
    _ignored(monkeypatch)
    monkeypatch.setattr(pb, "_git_ignored_in_page_dirs",
                        lambda r: ["collegesavant/logos/IU.png"])
    imports, _ = pb.split_data_files(root)
    assert imports == ["collegesavant/logos/IU.png", "data/fangraphs_imports/a.csv"]


def test_real_tree_carries_the_collegesavant_logos():
    logos = ROOT / "collegesavant" / "logos"
    if not any(logos.glob("*.png")):
        import pytest
        pytest.skip("no local logos in this checkout")
    assert any(r.startswith("collegesavant/logos/") for r in pb._git_ignored_in_page_dirs(ROOT))


def test_build_then_verify_and_positive_control(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    _ignored(monkeypatch)
    out = tmp_path / "bundle"
    info = pb.build(root, out, served_data=True, with_db=True)
    assert info["parts"]["cache-carry.tar"]["files"] == 4
    assert info["parts"]["data-imports.tar"]["files"] == 1
    assert info["parts"]["served-data.tar"]["files"] == 1
    assert info["parts"]["prospects.seed.db"]["integrity_check"] == "ok"
    sums = (out / "SHA256SUMS.txt").read_text(encoding="utf-8")
    for name in ("cache-carry.tar", "data-imports.tar", "served-data.tar",
                 "prospects.seed.db", "MANIFEST.tsv"):
        assert name in sums
    target = tmp_path / "target"
    target.mkdir()
    for name in ("cache-carry.tar", "data-imports.tar", "served-data.tar"):
        with tarfile.open(out / name) as tf:
            tf.extractall(target, filter="data")
    res = pb.verify(out / "MANIFEST.tsv", target)
    assert res == {**res, "checked": 6, "ok": True}
    (target / ".cache" / "proj_ml_pit_v1.joblib").write_bytes(b"\x00\x02")
    (target / "data" / "timeseries.json").unlink()
    res = pb.verify(out / "MANIFEST.tsv", target)
    assert not res["ok"]
    assert res["mismatched_sample"] == [".cache/proj_ml_pit_v1.joblib"]
    assert res["missing_sample"] == ["data/timeseries.json"]
