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

# --------------------------------------------------------------------------- #
# The served bundle (port Strategy D, docs/port/PORT_BUNDLE.md)
# --------------------------------------------------------------------------- #
import datetime as _dt  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402

import port_equivalence as pe  # noqa: E402

_T0 = _dt.datetime(2026, 10, 22, 7, 0, 0, tzinfo=_dt.timezone.utc)


def _site_tree(tmp_path: Path) -> Path:
    root = tmp_path / "site_mod"
    (root / "deploy").mkdir(parents=True)
    (root / "deploy" / "publish_paths.txt").write_text(
        "# pages\nindex.html\nfa\nassets\nprospx\n", encoding="utf-8")
    (root / "deploy" / "data_exclude.txt").write_text("# x\nsecret.json\n", encoding="utf-8")
    (root / "index.html").write_text("<p>home</p>", encoding="utf-8")
    (root / "fa").mkdir()
    (root / "fa" / "index.html").write_text("<p>fa</p>", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "site.css").write_text("/* note */\na{color:red}\n", encoding="utf-8")
    (root / "prospx").mkdir()
    (root / "prospx" / "index.html").write_text(
        "<html><body>\n<!-- dev note -->\n<p>x</p>\n</body></html>\n", encoding="utf-8")
    (root / "data" / "pitch_plots").mkdir(parents=True)
    (root / "data" / "_labs").mkdir()
    (root / "data" / "a.json").write_text('{"x": 1}', encoding="utf-8")
    (root / "data" / "b.js").write_text("var b=1;", encoding="utf-8")
    (root / "data" / "secret.json").write_text("{}", encoding="utf-8")
    (root / "data" / "build_info.json").write_text('{"mode": "daily"}', encoding="utf-8")
    (root / "data" / "notes.txt").write_text("not served", encoding="utf-8")
    (root / "data" / "_labs" / "lab.json").write_text("{}", encoding="utf-8")
    (root / "data" / "pitch_plots" / "1.json").write_text('{"v": [1]}', encoding="utf-8")
    return root


_SERVED = ["assets/site.css", "data/a.json", "data/b.js", "data/pitch_plots/1.json",
           "fa/index.html", "index.html", "prospx/index.html"]


def _no_strip(site):
    return {}


def test_served_set_is_the_nightly_rsync_set_minus_the_publisher_heartbeat(tmp_path):
    root = _site_tree(tmp_path)
    assert pb.served_files(root) == _SERVED
    both = set(pe.page_files(root)) | set(pe.payload_files(root))
    assert set(_SERVED) == both - {"data/build_info.json"}


def test_served_bundle_layout_and_verify(tmp_path):
    root = _site_tree(tmp_path)
    info = pb.build_served(root, tmp_path / "out", strip=False, now=_T0, strips=_no_strip)
    bundle = Path(info["path"])
    assert pb.BUNDLE_ID_RE.match(info["bundle_id"])
    assert info["bundle_id"].startswith("20261022T070000Z-")
    assert bundle.name == info["bundle_id"]
    assert info["files"] == len(_SERVED) + 1 and info["withheld"] == ["secret.json"]
    rows = (bundle / "MANIFEST.tsv").read_text(encoding="utf-8").splitlines()
    assert rows[0] == "relpath\tbytes\tsha256"
    assert [r.split("\t")[0] for r in rows[1:]] == sorted(_SERVED + [pb.BUNDLE_INFO])
    for line in (bundle / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        assert hashlib.sha256((bundle / rel).read_bytes()).hexdigest() == digest
    bi = json.loads((bundle / "site" / pb.BUNDLE_INFO).read_text(encoding="utf-8"))
    assert bi["bundle_id"] == info["bundle_id"] and bi["built_at"] == "2026-10-22T07:00:00Z"
    ready = (bundle / "READY").read_text(encoding="utf-8").strip().split("\t")
    assert ready == [info["bundle_id"], info["manifest_sha256"]]
    assert not (bundle / "site" / "data" / "secret.json").exists()
    assert not (bundle / "site" / "data" / "build_info.json").exists()
    assert not (bundle / "site" / "data" / "_labs").exists()
    res = pb.verify_served(bundle)
    assert res["ok"] and res["checked"] == len(_SERVED) + 1, res


def test_verify_served_positive_controls(tmp_path):
    root = _site_tree(tmp_path)
    bundle = Path(pb.build_served(root, tmp_path / "out", strip=False, now=_T0,
                                  strips=_no_strip)["path"])
    site = bundle / "site"
    (site / pb.RECEIPT).write_text('{"received_at": "2026-10-22T08:00:00Z"}', encoding="utf-8")
    assert pb.verify_served(bundle)["ok"], "the receipt is the one allowed extra file"
    (site / "data" / "a.json").write_text('{"x": 2}', encoding="utf-8")
    (site / "data" / "stray.json").write_text("{}", encoding="utf-8")
    (site / "data" / "secret.json").write_text("{}", encoding="utf-8")
    (site / "fa" / "index.html").unlink()
    res = pb.verify_served(bundle)
    assert not res["ok"]
    assert res["mismatched_sample"] == ["data/a.json"]
    assert res["missing_sample"] == ["fa/index.html"]
    assert res["extra_sample"] == ["data/secret.json", "data/stray.json"]
    assert res["withheld_present"] == ["data/secret.json"]


def test_verify_served_catches_a_tampered_manifest_or_no_ready(tmp_path):
    root = _site_tree(tmp_path)
    bundle = Path(pb.build_served(root, tmp_path / "out", strip=False, now=_T0,
                                  strips=_no_strip)["path"])
    man = bundle / "MANIFEST.tsv"
    assert pb.verify_served(bundle)["ok"]
    rows = man.read_bytes().split(b"\n")
    man.write_bytes(b"\n".join(rows[:-2]) + b"\n")   # drop the last row, keep LF
    res = pb.verify_served(bundle)
    assert not res["ok"] and any("manifest" in p for p in res["problems"])
    (bundle / "READY").unlink()
    res = pb.verify_served(bundle)
    assert not res["ok"] and res["problems"] == ["READY is missing"]


def test_same_bytes_share_the_content_suffix_and_prune_keeps_the_newest(tmp_path):
    root = _site_tree(tmp_path)
    out = tmp_path / "out"
    ids = [pb.build_served(root, out, strip=False, now=_T0 + _dt.timedelta(days=d),
                           strips=_no_strip)["bundle_id"] for d in range(3)]
    assert len({i.split("-")[1] for i in ids}) == 1
    (out / ".building-1").mkdir()
    (out / "keep_me").mkdir()
    gone = pb.prune_served(out, keep=2)
    assert sorted(gone) == sorted([ids[0], ".building-1"])
    assert sorted(p.name for p in out.iterdir()) == sorted(ids[1:] + ["keep_me"])


def test_strips_run_on_the_bundle_copy_never_the_source(tmp_path):
    root = _site_tree(tmp_path)
    before = {r: (root / r).read_bytes() for r in _SERVED}
    info = pb.build_served(root, tmp_path / "out", strip=True, now=_T0)
    bundle = Path(info["path"])
    assert info["strips"]["prospx/index.html"] == "stripped"
    assert info["strips"]["assets/site.css"].startswith("stripped")
    assert b"dev note" not in (bundle / "site" / "prospx" / "index.html").read_bytes()
    assert b"note" not in (bundle / "site" / "assets" / "site.css").read_bytes()
    assert {r: (root / r).read_bytes() for r in _SERVED} == before
    assert pb.verify_served(bundle)["ok"]


def test_served_bundle_cli_builds_verifies_and_prunes(tmp_path, capsys):
    root = _site_tree(tmp_path)
    rc = pb.main(["--root", str(root), "--served-bundle", str(tmp_path / "out"),
                  "--no-strip", "--keep", "1"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["verify"]["ok"] and out["pruned"] == []
    assert pb.main(["--verify-served", out["path"]]) == 0
