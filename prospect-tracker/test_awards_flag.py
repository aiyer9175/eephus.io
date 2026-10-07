# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""awards_core.AWARDS_LIVE, the export part (AWARDS_3_EXPORTER; AWARDS_PLAN 6 'Invariants
and tests' row I13 and 3 'The flag').

While the flag is False: the exporter writes nothing under data/ except exactly
data/_labs/awards/frozen_<S>.json and data/_labs/awards/freeze_log.json, both by --freeze;
every other file lands under .cache/awards/preview/; deploy/publish_paths.txt,
data/glossary.json and data/model_registry.json carry no awards entry; and run_monthly's
watched tuple holds no awards_export row. The page part (no awards/index.html, /hof/
byte-identical except stamps) lands with AWARDS_7. The fixture world is
test_fixtures/awards/export/ (see test_awards_export.py); no test touches the network.
"""
from __future__ import annotations

import json
import shutil
import socket
from pathlib import Path

import pytest

import awards_core as A
import awards_export as E

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "awards" / "export"
SEASON = 2026
PROV = "ewar_v2"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("an awards_flag test opened a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A fixture tree laid out like the repository: data/, data/_labs/awards/, .cache/,
    model/, so the flag's rule can be stated on the real paths."""
    data = tmp_path / "data"
    shutil.copytree(FIX / "data", data)
    shutil.copytree(FIX / "labs", data / "_labs" / "awards")
    shutil.copytree(FIX / "cache", tmp_path / ".cache")
    shutil.copytree(FIX / "model", tmp_path / "model")
    monkeypatch.setattr(E, "_display_provider", lambda: PROV)
    E.reset_frames()
    E.inject_frames(json.loads((FIX / "stints.json").read_text(encoding="utf-8")), PROV)
    yield tmp_path
    E.reset_frames()


def _files(root: Path) -> set:
    return {str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*") if p.is_file()}


def _kw(tree: Path) -> dict:
    return dict(data_dir=tree / "data", cache_dir=tree / ".cache", labs_dir=tree / "data" / "_labs" / "awards",
                model_dir=tree / "model", log=lambda *_a, **_k: None)


def test_the_flag_is_false_at_head():
    assert A.AWARDS_LIVE is False
    assert E.PREVIEW == E.CACHE / "awards" / "preview"
    assert E.LABS == E.DATA / "_labs" / "awards"


def test_with_the_flag_false_the_export_writes_only_under_the_preview(tree):
    assert A.AWARDS_LIVE is False
    before = _files(tree)
    preview = tree / ".cache" / "awards" / "preview"
    res = E.export(out_dir=tree / "data", preview_dir=preview, **_kw(tree))
    assert res["ok"], res
    after = _files(tree)
    new = after - before
    assert new, "the export wrote nothing"
    assert all(n.startswith(".cache/awards/preview/") for n in new), sorted(new)
    assert not any(n.startswith("data/") for n in new)
    assert Path(res["out_dir"]) == preview
    assert {n.rsplit("/", 1)[1] for n in new} == set(res["files"])
    assert "awards.json" in res["files"] and f"awards_candidates_{SEASON}.json" in res["files"]


def test_the_freeze_writes_exactly_the_two_labs_files_and_nothing_else(tree):
    assert A.AWARDS_LIVE is False
    before = _files(tree)
    res = E.freeze(SEASON, **_kw(tree))
    assert res["ok"], res
    new = _files(tree) - before
    assert new == {f"data/_labs/awards/frozen_{SEASON}.json", "data/_labs/awards/freeze_log.json"}
    assert not (tree / ".cache" / "awards").exists()
    log = json.loads((tree / "data" / "_labs" / "awards" / "freeze_log.json").read_text(encoding="utf-8"))
    assert [e["season"] for e in log["entries"]] == [SEASON]
    again = E.freeze(SEASON, **_kw(tree))
    assert again["ok"] is False and _files(tree) - before == new


def test_the_main_entry_points_route_freeze_and_export(tree, monkeypatch):
    calls = []
    monkeypatch.setattr(E, "freeze", lambda s, **k: calls.append(("freeze", s)) or {"ok": True})
    monkeypatch.setattr(E, "export", lambda **k: calls.append(("export", k.get("season"))) or {"ok": False})
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    assert E.main(["--freeze", "2026"]) == 0
    assert E.main([]) == 1
    assert E.main(["--season", "2025"]) == 1
    assert calls == [("freeze", 2026), ("export", None), ("export", 2025)]


def test_publish_paths_glossary_and_registry_carry_no_awards_entry_while_the_flag_is_false():
    if A.AWARDS_LIVE:
        pytest.skip("the flip commit adds them")
    paths = [ln.strip() for ln in (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    assert "awards" not in paths and "hof" in paths
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    entries = gl if isinstance(gl, list) else (gl.get("entries") or gl.get("terms") or [])
    ids = {e.get("id") or e.get("slug") for e in entries if isinstance(e, dict)}
    for new_id in ("eephus_selection", "awards_rule_mvp", "rookie_proxy", "bbwaa_ballot", "my_ballot",
                   "rule_and_vote", "sl_next_season_change"):
        assert new_id not in ids, new_id
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    assert A.SELECTION_REGISTRY not in {m.get("model_id") for m in reg["models"]}
    assert not any(p.name.startswith("awards") for p in (ROOT / "data").glob("awards*.json")), \
        "a served awards file exists under data/ while the flag is False"


def test_the_watched_tuple_gains_awards_export_only_inside_the_flag_branch():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index("SCHEDULED_EXPORTS = (")
    j = src.index("\n)\n", i)
    assert '"awards_export"' not in src[i:j]
    assert '"statsapi_standings"' in src[i:j]
    k = src.index('SCHEDULED_EXPORTS = SCHEDULED_EXPORTS + ("awards_export",)')
    assert k > j
    assert "if _AWARDS_LIVE:" in src[j:k]
    assert "from awards_core import AWARDS_LIVE as _AWARDS_LIVE" in src[j:k]
    # the window scan test_mgmt_export relies on
    assert '"mgmt_export"' in src[i:i + 3200]
