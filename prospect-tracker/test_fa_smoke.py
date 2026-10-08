# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer smoke test for assets/fa.js (F-02 error state).

fa.js already had a visible error branch; this pins the standardized copy and
the retry affordance so a fetch failure can never regress to a blank board.
Uses REAL rejected Promises (fa.js render() is async/await + Promise.all);
py_mini_racer drains the microtask queue inside eval, so the catch branch has
painted by the time the first eval returns. Skips without py_mini_racer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "fa.js").read_text(encoding="utf-8")

PRELUDE = r"""
var __html={};
function __el(id){return new Proxy(function(){return __el(id);},{
  get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
    if(k==='classList')return {add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
    if(k==='querySelectorAll')return function(){return [];};
    if(k==='getAttribute')return function(){return null;};
    if(k==='setAttribute'||k==='addEventListener'||k==='removeEventListener'||k==='appendChild'||k==='focus')return function(){};
    if(k==='querySelector'||k==='closest')return function(){return __el(id+'q');};
    if(k==='value'||k==='textContent')return ''; if(k==='dataset')return {};
    return __el(id);},
  set:function(t,k,v){if(k==='innerHTML')__html[id]=v;return true;}, apply:function(){return __el(id);}});}
function URLSearchParams(s){ this._m={}; s=String(s==null?'':s);
  if(s.charAt(0)==='?'||s.charAt(0)==='#')s=s.slice(1);
  var self=this; s.split('&').forEach(function(kv){ if(!kv)return;
    var i=kv.indexOf('='); var k=i<0?kv:kv.slice(0,i); var v=i<0?'':kv.slice(i+1);
    self._m[decodeURIComponent(k)]=decodeURIComponent(v.replace(/\+/g,' ')); }); }
URLSearchParams.prototype.get=function(k){ return (k in this._m)?this._m[k]:null; };
URLSearchParams.prototype.has=function(k){ return (k in this._m); };
URLSearchParams.prototype.set=function(k,v){ this._m[k]=String(v); };
URLSearchParams.prototype.toString=function(){ var out=[];
  for(var k in this._m) out.push(encodeURIComponent(k)+'='+encodeURIComponent(this._m[k]));
  return out.join('&'); };
// every sidecar fetch fails -> render()'s catch must paint the error state
var fetch=function(){ return Promise.reject(new Error('network down')); };
var history={replaceState:function(){}};
var location={hash:'',pathname:'/fa/',replace:function(){}};
var document={readyState:'complete',getElementById:function(id){return __el(id);},
  querySelector:function(){return __el('q');},querySelectorAll:function(){return [];},
  createElement:function(id){return __el('created');},addEventListener:function(){},
  body:__el('body'),documentElement:__el('de'),head:__el('head')};
var window={location:location,document:document,history:history,fetch:fetch,
  EEPHUS_GL:{wire:function(){}},EEPHUS_HUB:null,
  addEventListener:function(){},setTimeout:function(){}};
var navigator={userAgent:'smoke'};
"""


def test_fetch_failure_renders_error_state():
    ctx = MiniRacer()
    ctx.eval(PRELUDE + JS)
    html = ctx.eval("__html['fa-rows'] || ''")
    assert "Free-agent board did not load" in html
    assert "nightly build may be writing it" in html
    assert "fa-retry" in html                # the retry affordance exists
    assert 'role="alert"' in html


# ---------------------------------------------------------------------------
# The Class Board is ONE TABLE (owner ask B, 2026-09-16)
#
# Source-level assertions, not render assertions: this module's only browser
# fixture drives the FETCH-FAILURE path (every fetch rejects by design), so
# there is no rendered board to inspect here. Pinning the emitted markup in the
# source is the same approach test_war_rate_plus.py takes for assets/mlbstats.js,
# and test_fa_table_fit.py drives the built page for everything CSS decides.
#
# Every slice below asserts BOTH ends, so none of them can quietly go vacuous
# when the source moves.
# ---------------------------------------------------------------------------

def _board(js):
    """renderBoard's source, from its opening line to the next top-level
    function. Both ends are asserted, so the slice cannot go vacuous."""
    assert "function renderBoard(rows, cls)" in js
    part = js.split("function renderBoard(rows, cls)", 1)[1]
    assert "function faValueMap(members)" in part
    return part.split("function faValueMap(members)", 1)[0]


def _board_all(js):
    """Everything the board emits: the row, the detail line and renderBoard."""
    assert "// ---- Class Board: ONE TABLE" in js
    part = js.split("// ---- Class Board: ONE TABLE", 1)[1]
    assert "function faValueMap(members)" in part
    return part.split("function faValueMap(members)", 1)[0]


def _head(js):
    part = js.split("const head = `<thead><tr>`", 1)
    assert len(part) == 2, "the board head is not one <thead> template"
    return part[1].split("</tr></thead>", 1)[0]


def test_board_emits_one_table_not_cards():
    """Owner ask B (2026-09-16): the class board is a table. The card grid put
    2 rows above the fold at 1440 and 0 on a phone."""
    board = _board(JS)
    assert 'class="fa-board-table"' in board
    assert "<thead>" in board and "<tbody>" in board
    assert '<tr data-key="' in JS
    for card_bit in ("mlb-card fa-card", "mlb-card-list", 'class="mlb-tape"',
                     "mlb-sortbar", "data-card-href", "FA_TRACKS"):
        assert card_bit not in JS, f"{card_bit} is still emitted on the board"
    # the in-module table dialect stays with the other five views
    assert "detail-table" not in board
    assert "data-export" in board.split('class="fa-board-table"', 1)[1][:200]


def test_every_board_header_is_a_keyboard_sortable_columnheader():
    """aria-sort on a <th scope=col> (a columnheader, where ARIA exposes it)
    around a native <button>: Enter and Space with no keydown shim, one tab
    stop, and no glossary hook nested inside a control."""
    import re
    head = _head(JS)
    ths = [t for t in re.findall(r"\+ th\(\"[^\"]+\"", head)]
    assert len(ths) == 13, f"{len(ths)} sortable headers, not 13"
    th_src = JS.split("const th = (key, label, cname, title, exportText) =>", 1)[1].split("};", 1)[0]
    assert 'scope="col"' in th_src and "aria-sort=" in th_src and "data-export-text=" in th_src
    assert '<button type="button" class="fa-sort" data-fsort=' in th_src
    assert 'role="button"' not in th_src and "tabindex" not in th_src
    assert "data-gl" not in head, "a glossary hook inside a sort button is a nested tab stop"
    keys = re.findall(r'th\("([A-Za-z0-9]+)"', head)
    for key in ("rank", "name", "status", "verdict", "projAav", "projYears", "projGuar",
                "surplus", "dealPlus", "rational", "warY1", "warTotal", "age"):
        assert key in keys, f"{key} lost its header"


def test_every_sort_key_is_reachable_and_whitelisted():
    """A key with no column must be reachable through the picker, and an unknown
    #sort= must fall back rather than sort every row as a tie. warCvar10 and
    pAnyStar have no column at any width, so the picker is their only path."""
    import re
    keys = set(re.findall(r'"([A-Za-z0-9]+)"', JS.split("const FA_SORT_KEYS = [", 1)[1].split("];", 1)[0]))
    assert keys == {"rank", "name", "status", "verdict", "projAav", "projYears", "projGuar",
                    "surplus", "dealPlus", "rational", "warY1", "warTotal", "warCvar10",
                    "pAnyStar", "age", "prevAav"}
    # the picker offers every key except rank, which has its own column
    assert 'const FA_PICK_KEYS = FA_SORT_KEYS.filter(k => k !== "rank");' in JS
    assert "FA_PICK_KEYS.map(" in JS, "the picker is not built from FA_PICK_KEYS"
    head_keys = set(re.findall(r'th\("([A-Za-z0-9]+)"', _head(JS)))
    assert keys - head_keys - {"prevAav", "warCvar10", "pAnyStar"} == set(), \
        "a key has neither a header nor a documented picker-only route"
    assert 'FA_SORT_KEYS.indexOf(p.get("sort")) >= 0 ? p.get("sort") : "projGuar"' in JS
    labels = JS.split("const FA_SORT_LBL = {", 1)[1].split("};", 1)[0]
    for key in keys:
        assert f"{key}:" in labels, f"{key} has no picker label"


def test_default_sort_key_has_a_header():
    """boardState.sort defaulted to projGuar while NO header carried that key,
    so first paint showed no active-sort indicator and the default ordering was
    unreachable after a single click."""
    default = JS.split("const boardState")[1].split("sort:")[1].split(",")[0].strip().strip("\"' ")
    assert f'th("{default}"' in _head(JS), f"default sort {default!r} has no header"


def test_missing_values_sort_last_in_both_directions():
    """The card comparator used -1e15, so every ascending sort opened on the
    four unprojected rows. The null branch must return 1 / -1 BEFORE dir is
    applied, which is the only shape that keeps a missing value last in both
    directions. Asserted on the CODE, not on its comment: a "missing values
    last" disjunct is satisfied by the comment on that very line, so a mutant
    that flips the branch to dir * (a.v == null ? -1 : 1) would keep the comment
    and survive the pin."""
    src = JS.split("function faSortRows(list)", 1)[1].split("\n  }", 1)[0]
    assert "-1e15" not in JS, "the -1e15 null sentinel is back"
    assert "return a.v == null ? 1 : -1;" in src, "nulls no longer sort last in both directions"
    assert "localeCompare" in src, "no deterministic tiebreak"


def test_phase_h_fields_are_rendered():
    """warCvar10, pAnyStar and the option decomposition were computed and
    carried in the payload but rendered NOWHERE before Phase H; the table keeps
    them on the detail line, with prevAav, the unprojected reason, the comps and
    the fits, none of which the row has ever shown."""
    for field in ("warCvar10", "pAnyStar", "optKind"):
        assert field in JS, f"Phase H field {field} still unrendered"
    assert "downside WAR" in JS
    detail = JS.split("function faDetailRow(m, cls)", 1)[1].split("\n  }", 1)[0]
    for field in ("warCvar10", "pAnyStar", "optKind", "prevAav", "thinPlatform",
                  "unprojected_reason_text", "comps", "fits"):
        assert field in detail, f"{field} is not on the detail line"


def test_the_band_disclosure_travels_with_the_number():
    """The aavWild sentence is composed once, at the band; the surplus sentence
    is composed once in surplusBandText, which the cell and the detail line both
    read; and openBand still prints the cell's own aria-label."""
    bands = JS.split("function faBands(m)", 1)[1].split("\n  }", 1)[0]
    assert "flat ratio, not a per-tier fit" in bands
    assert "surplus: surplusBandText(m.surplus, m.surplusP10, m.surplusP90)" in bands
    assert JS.count("P10 to P90 of simulated contract value") == 1, "the surplus sentence is composed twice"
    assert "const band = surplusBandText(usd, p10, p90);" in JS
    # One FORMATTER too: the board block must not turn a surplus field into a
    # string of its own, and no caller may invent a zero for a missing end.
    assert _board_all(JS).count('"surplusM"') == 0, "the board formats a surplus of its own"
    assert "?? 0) / 1e6" not in JS, "a missing band end is printed as a zero"
    assert "const sp = surplusBandParts(m.surplus, m.surplusP10, m.surplusP90);" in JS
    assert 'aria-label="${esc(label)}"' in JS and "data-band" in JS
    assert 'const text = cell.getAttribute("aria-label");' in JS


def test_the_total_band_stays_withdrawn():
    """F-01: summing per-year quantiles is not the total's quantile."""
    board = _board_all(JS)
    for f in ("warTotalP10", "warTotalP90", "warTotalP10Comon", "warTotalP90Comon"):
        assert f not in board, f"{f} is back on the board"


def test_the_board_carries_its_state_in_the_hash():
    """A sorted or filtered class board was unshareable: boardState never
    reached the URL. And dir must be read only when the hash carries dir or
    sort, or coming back from a player card would silently flip the order."""
    to = JS.split("function syncToURL()", 1)[1].split("\n  }", 1)[0]
    assert 'p.set("sort", boardState.sort)' in to
    assert 'p.set("dir"' in to
    assert '"type", "pos", "verdict", "hand"' in to
    frm = JS.split("function syncFromURL()", 1)[1].split("\n  }", 1)[0]
    assert 'p.has("sort")' in frm and '"asc"' in frm
    assert 'if (p.has("dir") || p.has("sort")) {' in frm, "dir is reapplied on every hash read"
    assert '"type", "pos", "verdict", "hand"' in frm


def test_deal_plus_is_not_banded_on_the_house_thresholds():
    """Deal+ is a RATIO index, so its cuts are the served per-group terciles in
    fa_meta.gate2.verdict_edges, never the 93/107/120 ruler that belongs to the
    100 + 10z family. The column carries no colour at all."""
    tip = JS.split("function faDealPlusTip(m)", 1)[1].split("\n  }", 1)[0]
    assert "_faVerdictBand(m.pos)" in tip, "the tooltip does not read the served edges"
    cell = JS.split("const dp = m.dealPlus != null", 1)[1].split(";", 1)[0]
    for literal in ("93", "107", "120"):
        assert literal not in tip, f"a house threshold {literal} is hardcoded in the Deal+ tooltip"
        assert literal not in cell, f"a house threshold {literal} is hardcoded in the Deal+ cell"
    assert "vt-" not in cell and "class=" not in cell, "the Deal+ cell carries a band class"


def test_in_module_links_keep_the_class():
    """The retired whole-card handler built #player= WITHOUT faHash(), so a
    click on a future-class row dropped class= and re-read the current class."""
    import re
    board = _board_all(JS)
    hrefs = re.findall(r'href="#([^"]*)"', board)
    assert hrefs, "the board emits no links"
    for h in hrefs:
        assert h.startswith("${faHash()}"), f'href="#{h}" drops the class'
