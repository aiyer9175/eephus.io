# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A season's Projected Single-A board never shows another season's line unlabelled.

Reconciliation finding RML05 (2026-10-01). college_translation.py builds ONE
projection per player from one college season (the latest for hitters, the
most-pitched season that carries K% / BB% for pitchers; the 2026 pitcher rows
carry neither), and the CollegeSavant boards and player pages looked it up by
slug under whatever season was on screen, so the default 2026 pitcher board
listed 77 arms whose projections all came from a 2024 or 2025 line, labelled
2026. Each translation entry now carries source_season and every row whose
source season is not the board's season prints it.

These tests read the SERVED artifacts (data/collegesavant_translation.js and
the vendored collegesavant/*.js files) and render the real boards.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import college_translation as ct

ROOT = Path(__file__).parent
CS = ROOT / "collegesavant"
SIDECAR = ROOT / "data" / "collegesavant_translation.js"


def _sidecar() -> dict:
    text = SIDECAR.read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):text.rstrip().rstrip(";").rindex("}") + 1])


def _hitter_rows():
    return ct._first_array(CS / "hitter_year_data.js", "window.HITTER_DATA")


def _pitcher_rows():
    return ct._first_array(CS / "pitcher_data.js", "window.PITCHER_DATA")


def _hit_slug(r):
    return ct.slugify_cs(r["hitter_name"])


def _pit_slug(r):
    return ct.slugify_cs("{}-{}".format(r["pitcher_name"], r["pitcher_id"]))


def test_every_served_entry_carries_its_source_season():
    T = _sidecar()["translations"]
    assert T
    missing = [s for s, e in T.items() if not isinstance(e.get("source_season"), int)]
    assert not missing, f"{len(missing)} entries carry no source_season, e.g. {missing[:5]}"


def test_source_season_is_the_line_the_projection_was_built_from():
    """Recomputed from the build's own loaders: the hitter's latest season, the
    pitcher's most-pitched season among those with K% / BB%."""
    T = _sidecar()["translations"]
    want = {}
    for v in ct.load_cs_hitters().values():
        want.setdefault(ct.slugify_cs(v["name"]), v["year"])
    for v in ct.load_cs_pitchers().values():
        want.setdefault(ct.slugify_cs("{}-{}".format(v["name"], v.get("pitcher_id"))), v["year"])
    bad = [s for s, e in T.items() if s in want and e["source_season"] != want[s]]
    assert not bad, bad[:5]
    # No 2026 pitcher row carries a rate, so no translation can name 2026.
    assert not any(r.get("k_pct") is not None for r in _pitcher_rows() if r.get("year") == 2026)
    assert not any(e["source_season"] == 2026 for e in T.values() if e.get("side") == "pit")


# --------------------------------------------------------------------------- #
# Render the served boards in a JS engine
# --------------------------------------------------------------------------- #
MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

CAP = r"""
var __html={};
function __el(id){return new Proxy(function(){return __el(id);},{
  get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
    if(k==='classList')return {add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
    if(k==='querySelectorAll')return function(){return [];};
    if(k==='getAttribute')return function(){return null;};
    if(k==='addEventListener'||k==='setAttribute'||k==='focus'||k==='setSelectionRange'||k==='removeEventListener')return function(){};
    if(k==='querySelector'||k==='closest')return function(){return __el(id+'c');};
    if(k==='dataset')return {};
    if(k==='style')return {};
    if(k==='value'||k==='textContent')return ''; if(k==='selectionStart')return 0; return __el(id);},
  set:function(t,k,v){if(k==='innerHTML')__html[id]=v;return true;}, apply:function(){return __el(id);}});}
var location={hash:'#/projections'};
var localStorage={getItem:function(){return null;},setItem:function(){},removeItem:function(){}};
var document={querySelector:function(s){return __el(s==='#app'?'app':s);},querySelectorAll:function(){return [];},getElementById:function(id){return __el(id);},createElement:function(){return __el('t');},addEventListener:function(){},body:__el('b'),documentElement:__el('h'),head:__el('h')};
var window={B1G_TEAMS:{}, B1G_TEAMS_PITCHERS:{}, location:location, localStorage:localStorage, document:document, addEventListener:function(){}, removeEventListener:function(){}, matchMedia:function(){return {matches:false,addEventListener:function(){},addListener:function(){}};}, requestAnimationFrame:function(){}, setTimeout:function(){}, clearTimeout:function(){}, devicePixelRatio:1, innerWidth:1200, scrollTo:function(){}, EEPHUS_GL:null, EEPHUS_HUB:null,
  PITCHER_PITCH_DATA:[], PITCHER_PITCH_DATA_2024:[], PITCHER_PITCH_DATA_2025:[], PITCHER_PITCH_DATA_2026:[], PITCH_SHAPES_2024:{}, PITCH_SHAPES_2025:{},
  HITTER_BIP:{}, HITTER_BIP_2024:{}, HITTER_BIP_2025:{}, CS_DRAFT_PROSPECTS:{hitters:[],pitchers:[]}};
var console={log:function(){},warn:function(){},error:function(){}};
var navigator={userAgent:'verify'};
"""


def _ctx(app: str, data_files: list[str]):
    ctx = MiniRacer()
    ctx.eval(CAP)
    for f in data_files:
        ctx.eval((CS / f).read_text(encoding="utf-8"))
    ctx.eval(SIDECAR.read_text(encoding="utf-8"))
    ctx.eval((CS / "team_names.js").read_text(encoding="utf-8"))
    ctx.eval((CS / app).read_text(encoding="utf-8"))
    return ctx


def _board(ctx, year: int) -> str:
    ctx.eval(f"setActiveYear({year});renderProjections();")
    return ctx.eval("__html['app']||''")


_ROW = re.compile(r'<a class="proj-name" href="#/player/(\d{4})/([^"]+)">.*?</td>', re.S)
_NOTE = re.compile(r"([\d,]+) of ([\d,]+) (?:hitters|pitchers) with a projection listed, (\d{4})")
_OFF = re.compile(r"([\d,]+) of the ([\d,]+) listed (?:hitters|pitchers) project from another season")


def _num(s):
    return int(s.replace(",", ""))


def _expected(rows, slug_of, year, T, default_year, qual):
    """Independent recount of a season's board: projected rows, rows listed by
    the pool-median qualifier, and listed rows from another season."""
    pool = [r for r in rows if (r.get("year") or default_year) == year]
    proj = [r for r in pool if T.get(slug_of(r), {}).get("single_a")]
    med = qual(pool)
    if med is None:
        listed = proj
    elif qual.__name__ == "_pa_median":
        listed = [r for r in proj if r.get("pa") is None or r["pa"] >= med]
    else:
        listed = [r for r in proj if (r.get("pitch_count") or 0) >= med]
    off = sum(1 for r in listed if T[slug_of(r)]["source_season"] != year)
    return len(proj), len(listed), off, med


def _pa_median(pool):
    pa = sorted(float(r["pa"]) for r in pool if r.get("pa") not in (None, ""))
    return pa[len(pa) // 2] if pa else None


def _pitch_median(pool):
    pc = sorted(float(r.get("pitch_count") or 0) for r in pool)
    return pc[len(pc) // 2] if pc else None


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_every_board_row_has_its_season_or_prints_its_source(side):
    T = _sidecar()["translations"]
    if side == "hit":
        ctx = _ctx("app.js", ["data.js", "hitter_year_data.js"])
        rows, slug_of, dflt, qual = _hitter_rows(), _hit_slug, 2025, _pa_median
    else:
        ctx = _ctx("pitcher_app.js", ["pitcher_data.js"])
        rows, slug_of, dflt, qual = _pitcher_rows(), _pit_slug, 2026, _pitch_median
    years = sorted({r.get("year") or dflt for r in rows})
    tagged_total = 0
    for y in years:
        html = _board(ctx, y)
        board = html[html.index("Projected Single-A board"):]
        found = _ROW.findall(board)
        cells = [m.group(0) for m in _ROW.finditer(board)]
        assert found, (side, y)
        for (yy, slug), cell in zip(found, cells):
            assert int(yy) == y
            src = T[slug]["source_season"]
            tag = re.search(r"from (\d{4}) line", cell)
            if src == y:
                assert not tag, (side, y, slug, cell)
            else:
                assert tag and int(tag.group(1)) == src, (side, y, slug, cell)
                tagged_total += 1
        # The label is additive: the qualifier and the listed counts are the
        # independent recount, so no row was dropped or added by it.
        n_proj, n_listed, n_off, med = _expected(rows, slug_of, y, T, dflt, qual)
        note = _NOTE.search(board)
        assert note and (_num(note.group(1)), _num(note.group(2)), int(note.group(3))) == (n_listed, n_proj, y)
        assert len(found) == min(n_listed, 300)
        off = _OFF.search(board)
        if n_off:
            assert off and (_num(off.group(1)), _num(off.group(2))) == (n_off, n_listed), board[:600]
        else:
            assert not off
        if med is not None:
            assert f"{med:g}+ " in board
    assert tagged_total > 0


def test_default_2026_pitcher_board_marks_every_row():
    """The audited case: every arm on the 2026 board projects from 2024 or 2025."""
    ctx = _ctx("pitcher_app.js", ["pitcher_data.js"])
    html = _board(ctx, 2026)
    board = html[html.index("Projected Single-A board"):]
    rows = [m.group(0) for m in _ROW.finditer(board)]
    assert rows
    assert all(re.search(r"from 202[45] line", r) for r in rows)
    assert "(the 2026 file carries neither)" in board


def test_player_page_names_its_source_season():
    T = _sidecar()["translations"]
    p = next(r for r in _pitcher_rows() if r.get("year") == 2026 and T.get(_pit_slug(r), {}).get("single_a"))
    slug = _pit_slug(p)
    src = T[slug]["source_season"]
    ctx = _ctx("pitcher_app.js", ["pitcher_data.js"])
    ctx.eval(f"setActiveYear(2026);renderPitcher(state.pitchers.find(function(x){{return x.slug==='{slug}';}}));")
    html = ctx.eval("__html['app']||''")
    panel = html[html.index("trans-panel"):]
    assert f"from the {src} line" in panel
    assert f"from {src} line</span> Not this 2026 line" in panel
