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
    assert "Data failed to load" in html
    assert "nightly build is mid-run" in html
    assert "fa-retry" in html                # the retry affordance exists
    assert 'role="alert"' in html


# ---------------------------------------------------------------------------
# PROSPX-pattern board cards + Phase H fields (Lane B, 2026-07-30)
#
# Source-level assertions, not render assertions: this module's only browser
# fixture drives the FETCH-FAILURE path (every fetch rejects by design), so
# there is no rendered board to inspect here. Pinning the emitted markup in the
# source is the same approach test_war_rate_plus.py takes for assets/mlbstats.js.
# ---------------------------------------------------------------------------

def test_board_emits_cards_not_a_table():
    """The 12-column table squeezed four predicted-deal figures in beside their
    own P10-P90 bands. The card moves the deal into a row-2 tape instead."""
    assert "mlb-card fa-card" in JS, "board no longer emits cards"
    assert "mlb-card-list" in JS
    assert 'class="mlb-tape"' in JS
    assert "detail-table" not in JS.split("function renderBoard")[1].split("boardRail(cls)")[0],         "the retired table shell is still emitted by renderBoard"


def test_sort_headers_are_spans_with_the_a11y_contract():
    """The head is a CSS grid now, so a <th> would be invalid markup that
    browsers silently reparent, dropping the header row entirely."""
    shead = JS.split("const sHead = (label, key, title) =>")[1].split("};")[0]
    assert "<span class=\"fa-sort" in shead, "sHead still emits a table cell"
    assert "<th" not in shead
    for attr in ('tabindex="0"', 'role="button"', "aria-sort="):
        assert attr in shead, f"sHead dropped {attr}"


def test_rank_and_name_became_sortable():
    """Both were inert <th> on the table board."""
    head = JS.split('class="mlb-card-head"')[1].split("</div>")[0]
    for key in ("rank", "name", "status", "warY1", "surplus", "verdict"):
        assert f'sHead(' in head and f'"{key}"' in head, f"{key} is not a sort header"


def test_phase_h_fields_are_rendered():
    """warCvar10, pAnyStar and the option decomposition were computed and carried
    in the payload but rendered NOWHERE (master-plan-2026-07-29 Phase H). A
    surplus point estimate hides the downside; CVaR is what shows it."""
    for field in ("warCvar10", "pAnyStar", "optKind"):
        assert field in JS, f"Phase H field {field} still unrendered"
    assert "downside WAR" in JS
