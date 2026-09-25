# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Standout Performances ribbon reads single games again.

WHY THIS EXISTS (census M02-06, 2026-09-25, two verifiers CONFIRMED). The v33 payload
diet moved statcast_metrics.standout_games into the per-player shards, so 0 of 4,679
boot rows carried a game and the ribbon on Spotlights and Leaderboards always drew its
fallback, captioned "season aggregate (refresh pending)", a refresh that never came.
Opening a card merged one shard back, so the ticker then showed only the reader's own
clicks.

Contract pinned here:
  * export_timeseries_json keeps a top-level `standouts` list of the active board's
    games, taken before the shard harvest;
  * the ribbon reads DATA.standouts, anchors its 14-day window to the newest game on
    file, and no copy says "refresh pending";
  * on the served payload, every standout belongs to a boot player.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def test_source_reads_the_top_level_list():
    src = _src()
    assert "refresh pending" not in src and "Awaiting per-game gameLog refresh" not in src
    fn = _function_source(src, "renderStandoutPerformances")
    assert "DATA.standouts" in fn
    storage_src = (ROOT / "storage.py").read_text(encoding="utf-8")
    harvest = storage_src.index('"standouts":  standouts')
    assert storage_src.index("standouts: list[dict] = []") < storage_src.index(
        "for p in active_payload:\n        _harvest_player_detail(p)".replace("\n", "\r\n")
        if "\r\n" in storage_src else "for p in active_payload:\n        _harvest_player_detail(p)") < harvest


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    ctx = mr.MiniRacer()
    ctx.eval("""var DATA = {}; var _ROOT = {innerHTML: ''};
      var document = {getElementById: function(){ return _ROOT; }};
      function escapeHtml(s){ return String(s); }
      function getEfv(p){ return null; }
      function efvGradeDisplay(x){ return null; }
      function efvCompactBadge(){ return ''; }
      function marqueeifyTicker(){}
      function _renderStandoutPerformancesFallback(root){ root.innerHTML = 'FALLBACK'; }""")
    ctx.eval(_function_source(_src(), "renderStandoutPerformances"))
    return ctx


def test_ribbon_renders_games_anchored_to_the_newest_date(js):
    # Games from last season's end: a Date.now() window would drop them all.
    js.eval("""DATA.players = [{player_key:'a', player_name:'A', fv_close:55},
                               {player_key:'b', player_name:'B', fv_close:45}];
      DATA.standouts = [
        {player_key:'a', date:'2025-09-20', level:'AA', line:'3-4, 2 HR', score:9},
        {player_key:'b', date:'2025-09-10', level:'A', line:'2-3', score:5},
        {player_key:'b', date:'2025-08-01', level:'A', line:'old', score:12},
        {player_key:'zz', date:'2025-09-21', level:'A', line:'not on board', score:12}];
      renderStandoutPerformances('x');""")
    html = js.eval("_ROOT.innerHTML")
    assert "FALLBACK" not in html
    assert "2 games" in html and "through 09-20" in html
    assert "not on board" not in html and ">old<" not in html


def test_served_standouts_belong_to_the_board():
    from conftest import load_data_doc
    doc = load_data_doc("timeseries.json")
    if not doc or "standouts" not in doc:
        pytest.skip("timeseries.json predates the standouts list")
    keys = {p["player_key"] for p in doc.get("players") or []}
    assert isinstance(doc["standouts"], list) and doc["standouts"]
    assert all(r["player_key"] in keys and r["date"] and r["line"] for r in doc["standouts"])
