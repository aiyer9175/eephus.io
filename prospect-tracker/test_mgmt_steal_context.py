# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The steal context columns (mgmt_steal_context.py, W11 stage 1), pinned.

  - each runner percentile equals its source row: the Savant sprint speed row of
    that runner and season, ranked inside that season's leaderboard;
  - the catcher is read off the steal's own event, or the last event of a plate
    appearance the steal ended;
  - a row without a source carries the blank-with-note form, in Python and on the
    page, with the same words;
  - DV and the execution residual are untouched: the build never writes a shard,
    the payload carries no decision value, and the page prints the same DV / ER
    line with or without the context file.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import mgmt_shards  # noqa: E402
import mgmt_steal_context as msc  # noqa: E402
import savant_sprint  # noqa: E402

SERVED = ROOT / "data" / "management_steal_context.json"

SPRINT_CSV = (
    '"last_name, first_name","player_id","team_id","team","position","age","competitive_runs",'
    '"bolts","hp_to_1b","sprint_speed"\n'
    '"Fast, Al",101,1,"KC","SS",24,"200","90","4.10","30.5"\n'
    '"Mid, Bo",102,1,"KC","CF",25,"150","10","4.30","27.0"\n'
    '"Tie, Cy",103,1,"KC","2B",26,"120","5","4.35","27.0"\n'
    '"Slow, Di",104,1,"KC","C",30,"40","0","","24.0"\n'
)
# the fixture season's steal rows, as the shards name them
ROWS = [
    {"game_pk": 9001, "ab": 3, "in_id": 101, "season": 2024},   # listed runner, catcher with pop
    {"game_pk": 9001, "ab": 7, "in_id": 102, "season": 2024},   # tied runner, catcher with no pop
    {"game_pk": 9002, "ab": 1, "in_id": 555, "season": 2024},   # runner not listed, no catcher
]
POP = ({"201": [1.95, 40, "Ed Catch"], "202": [None, 3, "Fay Backup"]}, "2026-10-03T00:00:00")
ATT = {"9001:3": 201, "9001:7": 202}


def _block(**kw):
    rows = savant_sprint.parse_rows(SPRINT_CSV, 2024)
    return msc.season_block(2024, ROWS, sprint=(rows, "2026-10-03T00:00:00"),
                            pop=kw.get("pop", POP), att=kw.get("att", ATT), prev=kw.get("prev"))


# --------------------------------------------------------------------------
# the runner percentile equals the source row
# --------------------------------------------------------------------------

def test_each_percentile_equals_its_source_row_on_a_fixture():
    blk = _block()
    src = {r["mlbam"]: r for r in savant_sprint.parse_rows(SPRINT_CSV, 2024)}
    # 30.5 is above three of four: (3 + 0.5) / 4; 27.0 twice: (1 + 0.5 * 2) / 4
    assert blk["runners"]["101"] == [88, src[101]["ft_s"], src[101]["runs"]]
    assert blk["runners"]["102"] == [50, src[102]["ft_s"], src[102]["runs"]]
    # only runners on a steal row ship; the leaderboard size rides beside them
    assert set(blk["runners"]) == {"101", "102"}
    assert blk["sprint"]["n_runners"] == 4
    assert msc.percentiles({"a": 30.5, "b": 27.0, "c": 27.0, "d": 24.0}) == {
        "a": 88, "b": 50, "c": 50, "d": 13}


def test_the_served_percentiles_equal_the_cached_leaderboard_rows():
    if not SERVED.exists():
        pytest.skip("management_steal_context.json not built")
    d = json.loads(SERVED.read_text(encoding="utf-8"))
    checked = 0
    for season, blk in d["seasons"].items():
        p = savant_sprint._cache_path(int(season))
        if not p.exists() or "carried_from_previous_build" in blk:
            continue
        rows = savant_sprint.parse_rows(p.read_text(encoding="utf-8-sig"), int(season))
        if len(rows) != blk["sprint"]["n_runners"]:
            continue   # the cache moved since the build (the open season's refetch)
        src = {str(r["mlbam"]): r for r in rows}
        pct = msc.percentiles({k: r["ft_s"] for k, r in src.items()})
        for rid, rec in blk["runners"].items():
            assert rec == [pct[rid], round(src[rid]["ft_s"], 1), src[rid].get("runs")], (season, rid)
            checked += 1
    assert checked > 1000


# --------------------------------------------------------------------------
# the catcher on the attempt
# --------------------------------------------------------------------------

def _ev(et, catcher, pitch=False):
    return {"details": {"eventType": et}, "isPitch": pitch,
            "defense": {"catcher": {"id": catcher}} if catcher else {}}


def test_the_catcher_is_read_off_the_steal_event_or_the_last_event():
    plays = [
        {"atBatIndex": 3, "playEvents": [_ev(None, 201, True), _ev("stolen_base_2b", 202),
                                         _ev(None, 203, True)]},
        # a steal that ended the plate appearance is no playEvent
        {"atBatIndex": 4, "result": {"eventType": "caught_stealing_2b"},
         "playEvents": [_ev(None, 301, True), _ev(None, 302, True)]},
        {"atBatIndex": 5, "playEvents": [_ev(None, None, True)]},
    ]
    assert msc.catcher_of(plays, 3) == 202
    assert msc.catcher_of(plays, 4) == 302
    assert msc.catcher_of(plays, 5) is None
    assert msc.catcher_of(plays, 9) is None


def test_attempt_catchers_reads_only_what_the_seed_lacks(tmp_path, monkeypatch):
    monkeypatch.setattr(msc, "CACHE_DIR", tmp_path / "c")
    asked = []

    def loader(g):
        asked.append(g)
        return [{"atBatIndex": 1, "playEvents": [_ev("stolen_base_2b", 777)]}]

    got = msc.attempt_catchers(2024, ROWS, seed={"9001:3": 201, "9001:7": 202}, loader=loader)
    assert got == {"9001:3": 201, "9001:7": 202, "9002:1": 777}
    assert asked == [9002]


# --------------------------------------------------------------------------
# blank with a note
# --------------------------------------------------------------------------

def test_rows_without_a_source_carry_the_blank_with_note_form():
    blk = _block(att={"9001:3": 201, "9001:7": 202})
    a, b, c = (msc.context_for(r, blk) for r in ROWS)
    assert (a["sp_pct"], a["sp_note"], a["pop"], a["pop_note"], a["c_name"]) == (88, None, 1.95, None, "Ed Catch")
    assert b["pop"] is None and b["pop_note"] == (
        "no pop time for this catcher on the 2024 Savant catcher throwing leaderboard")
    assert c["sp_pct"] is None and c["sp_note"] == (
        "not on the 2024 Savant sprint speed leaderboard, which lists runners with 10 or "
        "more competitive runs")
    assert c["c_id"] is None and c["pop_note"] == "the MLB feed names no catcher on this attempt"
    none = msc.context_for({"season": 2017, "in_id": 1}, None)
    assert none["sp_note"] == "no Savant sprint speed leaderboard on file for 2017"
    assert none["pop_note"] == "no catcher context on file for 2017"
    assert blk["coverage"] == {"attempts": 3, "runner_pct": 2, "catcher_id": 2, "pop": 1}
    # every value is None exactly when its note is set
    for cx in (a, b, c, none):
        assert (cx["sp_pct"] is None) == bool(cx["sp_note"])
        assert (cx["pop"] is None) == bool(cx["pop_note"])


def test_an_empty_source_keeps_the_previous_block_and_says_so():
    prev = _block()
    blk = msc.season_block(2024, ROWS, sprint=([], None), pop=({}, None), att=ATT, prev=prev)
    assert blk["runners"] == prev["runners"] and blk["catchers"] == prev["catchers"]
    assert blk["carried_from_previous_build"] == ["sprint", "pop"]


# --------------------------------------------------------------------------
# DV and ER untouched
# --------------------------------------------------------------------------

def _steal(game_pk, ab, runner, dv, er):
    return {"date": "2024-05-01", "game_pk": game_pk, "ab": ab, "idx": -1, "opp": "NYY", "home": True,
            "season": 2024, "club": "MIA", "half": "bottom", "inning": 3, "outs": 0, "base": 1,
            "score_diff": 0, "li": 1.1, "family": "steal", "kind": "2B", "in_id": runner,
            "mwpa": dv + er, "dv": dv, "er": er, "realized_delta": dv + er, "breakeven_p": 0.72,
            "success": True}


def test_the_build_never_writes_a_shard_and_carries_no_decision_value(tmp_path, monkeypatch):
    monkeypatch.setattr(msc, "CACHE_DIR", tmp_path / "c")
    shard = mgmt_shards.compact_season([_steal(9001, 3, 101, 0.004, 0.02),
                                        _steal(9001, 7, 102, -0.001, -0.05)],
                                       2024, "MIA", "2026-10-01T00:00:00+00:00")
    p = tmp_path / "2024-MIA.json"
    p.write_text(json.dumps(shard), encoding="utf-8")
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    art = msc.build(shard_dir=tmp_path, prev={}, open_season=2026,
                    sprint_fn=lambda y: (savant_sprint.parse_rows(SPRINT_CSV, y), None),
                    pop_fn=lambda y: POP,
                    catcher_loader=lambda g: [{"atBatIndex": a, "playEvents": [_ev("stolen_base_2b", c)]}
                                              for a, c in ((3, 201), (7, 202))])
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before
    assert art["seasons"]["2024"]["coverage"] == {"attempts": 2, "runner_pct": 2, "catcher_id": 2, "pop": 1}
    flat = json.dumps(art)
    for k in ('"dv"', '"er"', '"realized_delta"', '"breakeven_p"', '"mwpa"'):
        assert k not in flat


# --------------------------------------------------------------------------
# the page: the twin of context_for, and the DV / ER line unchanged
# --------------------------------------------------------------------------

MiniRacer = None
try:
    from py_mini_racer import MiniRacer  # noqa: F811
except Exception:                       # noqa: BLE001
    pass

JS = (ROOT / "assets" / "management.js").read_text(encoding="utf-8")


def _render(hash_, board, shards, ctx):
    if MiniRacer is None:
        pytest.skip("py_mini_racer unavailable")
    prelude = """
    var __html={};
    function __el(id){return new Proxy(function(){return __el(id);},{
      get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
        if(k==='querySelectorAll')return function(){return [];};
        if(k==='addEventListener'||k==='setAttribute'||k==='getAttribute')return function(){return null;};
        return __el(id);},
      set:function(t,k,v){if(k==='innerHTML')__html[id]=v;return true;}});}
    function FT(v){return {then:function(cb){var r=cb(v);return (r&&r.then)?r:FT(r);},catch:function(){return FT(v);}};}
    var P=%s; var SH=%s; var CX=%s;
    function NF(){return FT({ok:false,status:404,json:function(){return FT({});}});}
    var fetch=function(url){ var u=String(url);
      if(u.indexOf('management_steal_context')>=0) return CX ? FT({ok:true,json:function(){return FT(CX);}}) : NF();
      if(u.indexOf('mgmt_decisions')>=0){ var s=SH[u]; if(!s) return NF();
        return FT({ok:true,json:function(){return FT(s);}}); }
      return FT({ok:true,json:function(){return FT(P);}});};
    var location={hash:%s};
    var history={replaceState:function(a,b,h){location.hash=h;}};
    var document={readyState:'complete',getElementById:function(id){return __el(id);},
      querySelector:function(){return {};},querySelectorAll:function(){return [];},addEventListener:function(){}};
    var window={document:document,EEPHUS_GL:{wire:function(){}}};
    """ % (json.dumps(board), json.dumps(shards), json.dumps(ctx), json.dumps(hash_))
    c = MiniRacer()
    c.eval(prelude + JS)
    return c.eval("__html['mgmt-app-root'] || ''")


def _served(season=2024, club="NYY"):
    board = ROOT / "data" / "management_board.json"
    shard = ROOT / "data" / "mgmt_decisions" / f"{season}-{club}.json"
    if not (board.exists() and shard.exists() and SERVED.exists()):
        pytest.skip("served management board, shard or steal context not built")
    return (json.loads(board.read_text(encoding="utf-8")),
            json.loads(shard.read_text(encoding="utf-8")),
            json.loads(SERVED.read_text(encoding="utf-8")))


def _unesc(s):
    return (s.replace("&quot;", '"').replace("&#39;", "'").replace("&lt;", "<")
            .replace("&gt;", ">").replace("&amp;", "&"))


def test_the_steal_view_prints_the_twin_of_context_for_on_a_served_shard():
    board, shard, ctx = _served()
    rows = [r for r in mgmt_shards.expand(shard) if r["family"] == "steal"]
    html = _render("#section=decisions&team=NYY&season=2024&family=steal", board,
                   {"/data/mgmt_decisions/2024-NYY.json": shard}, ctx)
    # every header cell, the unsortable Flags one included, so indexes match the cells
    head = re.findall(r"<th([^>]*)>", html.split("<thead>")[1].split("</thead>")[0])
    i_sp = next(i for i, a in enumerate(head) if 'data-dsort="ctx_sp"' in a)
    i_pop = next(i for i, a in enumerate(head) if 'data-dsort="ctx_pop"' in a)
    assert "Savant sprint speed" in head[i_sp] and "catcher throwing" in head[i_pop]
    body = html.split("<tbody>")[1].split("</tbody>")[0]
    trs = re.findall(r'<tr data-mrow="([^"]+)"[^>]*>(.*?)</tr>', body)
    assert len(trs) == len(rows) > 0
    blk = ctx["seasons"]["2024"]
    n_sp = n_pop = 0
    for (rid, tr), r in zip(trs, rows):
        assert rid == "%d:%d:%d" % (r["game_pk"], r["ab"], r["idx"])
        cells = re.findall(r"<td([^>]*)>(.*?)</td>", tr)
        cx = msc.context_for(dict(r, season=2024), blk)
        sp_attr, sp_txt = cells[i_sp]
        pop_attr, pop_txt = cells[i_pop]
        if cx["sp_pct"] is None:
            assert sp_txt == "not on file" and _unesc(sp_attr).endswith('title="%s"' % cx["sp_note"])
        else:
            assert sp_txt == str(cx["sp_pct"]) and "2024" in sp_attr and "Savant sprint speed" in sp_attr
            n_sp += 1
        if cx["pop"] is None:
            assert pop_txt == "not on file" and _unesc(pop_attr).endswith('title="%s"' % cx["pop_note"])
        else:
            assert pop_txt == "%.2f" % cx["pop"] and "2024" in pop_attr and "catcher throwing" in pop_attr
            n_pop += 1
    assert n_sp > 0 and n_pop > 0
    assert "Runner sprint pct and C pop are context only" in html


def test_the_dv_and_er_line_is_the_same_with_and_without_the_context():
    board, shard, ctx = _served()
    r = next(r for r in mgmt_shards.expand(shard) if r["family"] == "steal")
    h = "#section=decisions&team=NYY&season=2024&family=steal&game=%d&ab=%d" % (r["game_pk"], r["ab"])
    sh = {"/data/mgmt_decisions/2024-NYY.json": shard}

    def dv_line(html):
        card = html.split('id="mgmt-detail"')[1].split("</table>")[0]
        return re.search(r"realized \(model\)</[^>]+>.*?</tr>", card, re.S).group(0)

    with_ctx, without = _render(h, board, sh, ctx), _render(h, board, sh, None)
    assert dv_line(with_ctx) == dv_line(without)
    want = "%+.4f / %+.4f / %+.4f" % (r["dv"], r["er"], r["realized_delta"])
    assert want in dv_line(with_ctx)
    assert "Runner sprint speed (context)" in with_ctx and "Runner sprint speed (context)" not in without
    # without the file the steal view keeps its rows and leaves the context cells empty
    assert "not on file" not in without.split("<tbody>")[1]


def test_the_other_family_views_draw_no_context_column():
    board, shard, ctx = _served()
    html = _render("#section=decisions&team=NYY&season=2024", board,
                   {"/data/mgmt_decisions/2024-NYY.json": shard}, ctx)
    assert 'data-dsort="ctx_sp"' not in html and 'data-dsort="ctx_pop"' not in html


# --------------------------------------------------------------------------
# the wiring
# --------------------------------------------------------------------------

def test_the_step_runs_nightly_after_the_shard_writer_with_a_heartbeat():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    daily = src[src.index("def run_daily("):src.index("\ndef ", src.index("def run_daily(") + 10)]
    step = daily.index('_step("9e-pre0f. Steal context (management_steal_context.json)')
    assert daily.index('_step("9e-pre0e. In-Game Management nightly') < step
    for s in ('_hb.record("mgmt_steal_context", ok=True', '_hb.record("mgmt_steal_context", ok=False',
              '_record_ingest("mgmt_steal_context", _sc["status"] == "built"',
              '_record_ingest("mgmt_steal_context", False'):
        assert s in daily
    i = src.index("SCHEDULED_EXPORTS = (")
    assert '"mgmt_steal_context"' in src[i:src.index("\n)\n", i)]


def test_the_served_file_states_it_is_context_and_counts_its_coverage():
    if not SERVED.exists():
        pytest.skip("management_steal_context.json not built")
    d = json.loads(SERVED.read_text(encoding="utf-8"))
    assert d["produced_by"] == "mgmt_steal_context.py" and d["status"] == "built"
    assert "league-average runner" in d["use"]
    tot = {k: sum(b["coverage"][k] for b in d["seasons"].values()) for k in d["coverage"]}
    assert tot == d["coverage"]
    for b in d["seasons"].values():
        c = b["coverage"]
        assert c["attempts"] >= c["catcher_id"] >= c["pop"] and c["attempts"] >= c["runner_pct"]
