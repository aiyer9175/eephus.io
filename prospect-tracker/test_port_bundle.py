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
    # the live store (PORT_SCORES_PR11): the scores job's files, carried as of the build
    (root / "data" / "scores" / "games").mkdir(parents=True)
    (root / "data" / "scores" / "latest.json").write_text('{"schema": 1}', encoding="utf-8")
    (root / "data" / "scores" / "games" / "7.json").write_text('{"pk": 7}', encoding="utf-8")
    return root


_SERVED = ["assets/site.css", "data/a.json", "data/b.js", "data/pitch_plots/1.json",
           "data/scores/games/7.json", "data/scores/latest.json",
           "fa/index.html", "index.html", "prospx/index.html"]


def _no_strip(site):
    return {}


def test_served_set_is_the_nightly_rsync_set_plus_the_live_store_minus_the_heartbeat(tmp_path):
    root = _site_tree(tmp_path)
    assert pb.served_files(root) == _SERVED
    rsync = set(pe.page_files(root)) | set(pe.payload_files(root))
    live = set(pe.live_files(root))
    assert live == {"data/scores/games/7.json", "data/scores/latest.json"}
    assert not (live & rsync), "the nightly rsync never ships the scores store"
    assert set(_SERVED) == (rsync | live) - {"data/build_info.json"}


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


# --------------------------------------------------------------------------- #
# Bundle slimming (docs/port/PORT_BUNDLE.md section 9)
# --------------------------------------------------------------------------- #
import pytest  # noqa: E402


def test_slim_list_never_names_a_sidecar_file_and_only_depth_one_payloads():
    assert not set(pb.SLIM_EXCLUDE) & pb.SIDECAR_FILES
    for rel, why in pb.SLIM_EXCLUDE.items():
        assert rel.startswith("data/") and rel.count("/") == 1 and rel.endswith(".json"), rel
        assert why and why in (pb._INPUT, pb._LAB, pb._LEDGER, pb._RENDERED, pb._STRAY)
        assert not rel.startswith(pb.SIDECAR_DIRS)
        assert rel not in (pb.BUNDLE_INFO, pb.RECEIPT) and rel not in pb.PUBLISHER_FILES


def _slim_tree(tmp_path, monkeypatch):
    root = _site_tree(tmp_path)
    (root / "data" / "old_lab.json").write_text('{"lab": 1}', encoding="utf-8")
    (root / "data" / "awards_2021.json").write_text('{"y": 2021}', encoding="utf-8")
    monkeypatch.setattr(pb, "SLIM_EXCLUDE", {"data/old_lab.json": pb._LAB,
                                             "data/awards_2021.json": pb._LAB,
                                             "data/not_in_this_tree.json": pb._LAB})
    return root


def test_slimmed_set_is_the_rsync_set_minus_the_list(tmp_path, monkeypatch):
    root = _slim_tree(tmp_path, monkeypatch)
    full = pb.served_files(root)
    assert "data/old_lab.json" in full and "data/awards_2021.json" in full
    assert pb.served_files(root, slim=True) == sorted(
        set(full) - {"data/old_lab.json", "data/awards_2021.json"})
    plan = pb.plan_served(root)
    assert plan["slimmed"]["files"] == 2 and plan["files"] == len(full) - 2
    assert pb.plan_served(root, slim=False)["files"] == len(full)


def test_a_slimmed_build_leaves_the_list_out_and_still_verifies(tmp_path, monkeypatch):
    root = _slim_tree(tmp_path, monkeypatch)
    info = pb.build_served(root, tmp_path / "out", strip=False, now=_T0, strips=_no_strip)
    bundle = Path(info["path"])
    assert info["slim"] and info["slimmed"] == ["data/awards_2021.json", "data/old_lab.json"]
    assert not (bundle / "site" / "data" / "old_lab.json").exists()
    assert pb.verify_served(bundle)["ok"]
    full = pb.build_served(root, tmp_path / "full", strip=False, now=_T0, strips=_no_strip,
                           slim=False)
    assert full["slimmed"] == [] and full["files"] == info["files"] + 2


def test_the_guard_refuses_a_build_once_something_served_names_an_excluded_file(
        tmp_path, monkeypatch):
    root = _slim_tree(tmp_path, monkeypatch)
    assert pb.slim_violations(root) == {}
    plants = {
        "file name": ("fa/index.html", '<script>fetch("/data/old_lab.json")</script>'),
        "quoted stem": ("assets/site.css", "/* 'old_lab' */"),
        "numbered prefix": ("prospx/index.html", "<script>fetch(`/data/awards_${y}.json`)</script>"),
        "another payload": ("data/a.json", '{"src": "data/old_lab.json"}'),
    }
    for how, (rel, text) in plants.items():
        before = (root / rel).read_text(encoding="utf-8")
        (root / rel).write_text(before + text, encoding="utf-8")
        bad = pb.slim_violations(root)
        assert bad, how
        assert set(bad.values()) <= {rel, rel + " (numbered prefix)"}, (how, bad)
        with pytest.raises(pb.SlimError):
            pb.build_served(root, tmp_path / f"out-{len(how)}", strip=False, now=_T0,
                            strips=_no_strip)
        assert not (tmp_path / f"out-{len(how)}").exists() or not any(
            (tmp_path / f"out-{len(how)}").iterdir()), "a refused build wrote a bundle"
        (root / rel).write_text(before, encoding="utf-8")
    # A file's own name inside itself is not a reference.
    (root / "data" / "old_lab.json").write_text('{"self": "data/old_lab.json"}', encoding="utf-8")
    assert pb.slim_violations(root) == {}
    # The CLI reports the refusal and exits 1; --no-slim still builds.
    (root / "fa" / "index.html").write_text('<a href="/data/old_lab.json">x</a>', encoding="utf-8")
    assert pb.main(["--root", str(root), "--served-bundle", str(tmp_path / "cli"),
                    "--no-strip"]) == 1
    assert pb.main(["--root", str(root), "--served-bundle", str(tmp_path / "cli"),
                    "--no-strip", "--no-slim"]) == 0


def test_the_live_store_travels_whole_and_is_never_slimmed(tmp_path, monkeypatch):
    """PORT_SCORES_PR11 (owner PORT-Q-SCORES, 2026-10-27): data/scores/ ships in
    the bundle as of the build, every file, slim or not, and BUNDLE.json counts it."""
    root = _slim_tree(tmp_path, monkeypatch)
    assert [r for r in pb.served_files(root, slim=True) if r.startswith("data/scores/")] == [
        "data/scores/games/7.json", "data/scores/latest.json"]
    info = pb.build_served(root, tmp_path / "out", strip=False, now=_T0, strips=_no_strip)
    bundle = Path(info["path"])
    assert info["live"] == {"data/scores": 2} and info["files_by_top"]["data/scores"] == 2
    assert info["live_vanished"] == []
    assert (bundle / "site" / "data" / "scores" / "latest.json").read_text(encoding="utf-8") == '{"schema": 1}'
    assert (bundle / "site" / "data" / "scores" / "games" / "7.json").is_file()
    rows = (bundle / "MANIFEST.tsv").read_text(encoding="utf-8").splitlines()
    assert [r.split("\t")[0] for r in rows if r.startswith("data/scores/")] == [
        "data/scores/games/7.json", "data/scores/latest.json"]
    assert pb.verify_served(bundle)["ok"]
    assert pb.plan_served(root)["by_top"]["data/scores"] == {"files": 2, "bytes": 13 + 9}
    # a live file the job removed between the listing and the copy is left out, not an error
    import shutil
    real_copy = shutil.copy2

    def copy_minus_one(src, dst, *a, **k):
        if str(src).replace("\\", "/").endswith("data/scores/games/7.json"):
            raise FileNotFoundError(src)
        return real_copy(src, dst, *a, **k)
    monkeypatch.setattr(pb.shutil, "copy2", copy_minus_one)
    info = pb.build_served(root, tmp_path / "out1", strip=False, now=_T0, strips=_no_strip)
    assert info["live"] == {"data/scores": 1} and info["live_vanished"] == ["data/scores/games/7.json"]
    assert pb.verify_served(Path(info["path"]))["ok"]
    monkeypatch.setattr(pb.shutil, "copy2", real_copy)
    # a tree without the store builds without it, and says so
    shutil.rmtree(root / "data" / "scores")
    info = pb.build_served(root, tmp_path / "out2", strip=False, now=_T0, strips=_no_strip)
    assert info["live"] == {"data/scores": 0}
    assert not any(r.startswith("data/scores/") for r in pb.served_files(root))


def test_the_real_tree_carries_its_whole_scores_store():
    """Every file under data/scores/ (latest, the index, the dates, games/,
    standings/) is in the served set, and none is in the nightly rsync's."""
    store = ROOT / "data" / "scores"
    if not (store / "latest.json").is_file():
        pytest.skip("no scores store in this checkout")
    files = sorted(p.relative_to(ROOT).as_posix() for p in store.rglob("*") if p.is_file())
    served = set(pb.served_files(ROOT, slim=True))
    assert set(files) <= served and "data/scores/latest.json" in served
    assert not any(r.startswith("data/scores/") for r in pe.payload_files(ROOT))


def test_the_real_tree_names_no_excluded_file():
    """The committed list against the real page set and payloads: the guard a
    nightly build runs. Skips on a checkout without the gitignored payloads."""
    if not any((ROOT / r).is_file() for r in pb.SLIM_EXCLUDE):
        pytest.skip("no served payloads in this checkout")
    assert pb.slim_violations(ROOT) == {}
