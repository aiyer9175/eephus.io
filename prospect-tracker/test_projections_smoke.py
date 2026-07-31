# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer smoke test for assets/projections.js (/projections/).

Stubs the DOM, URLSearchParams, and a synchronous fetch keyed by URL so boot()
actually drives a render, then asserts the surfaces this app owns:

- F-02: a failed payload fetch paints a visible error state with a retry
  affordance (never a silent blank page);
- eFV-primary prospect grade language: prospects whose payload row carries
  fv_source="xfv" lead with "eFV" (round-to-NEAREST), consensus-FV fallbacks
  keep the "FV" + CEILING (fvCeil) idiom - on the board and in #cmp;
- the player detail card's explicit Upside element: per-year P90 values only,
  never a summed multi-year quantile total (F-01 stays quarantined).

Skips when py_mini_racer is unavailable so it never blocks a machine without it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")

# Board payload (data/mlb_projections.json contract, proj_export.py): one vet,
# one eFV-graded prospect (fv_source="xfv", fv carries the eFV grade), one
# consensus-fallback prospect. fv=50.4 distinguishes the rounding rules:
# round-to-NEAREST -> 50, ceiling -> 51.
BOARD = """{
 "generated_at":"2026-06-30","first_season":2026,"horizon":5,
 "n_vets":1,"n_prospects":2,"dpw_usd":9500000,"dpw_infl":0.05,
 "vets":[
  {"key":"vet_guy","name":"Vet Guy","pos":"SS","age":29.4,"team":"NYY","src":"vet",
   "war":[3.0,2.8,2.6,2.4,2.2],"warP10":[1.2,1.1,1.0,0.9,0.8],"warP90":[4.8,4.6,4.4,4.2,4.0],
   "warTotal":13.0,"warTotalP10":5.0,"warTotalP90":22.0,
   "thru":2028,"aav":25000000,"surNpv":40000000}
 ],
 "prospects":[
  {"key":"efv_kid","name":"Efv Kid","pos":"SS","age":20.1,"team":"BOS","src":"prospect",
   "fv":50.4,"consensus_fv":50,"fv_source":"xfv","eta":2026,
   "war":[1.0,1.5,2.0,2.5,3.0],"warP10":[0,0.2,0.4,0.6,0.8],"warP90":[3,4,5,5.5,6],
   "warTotal":10.0,"warTotalP10":2.0,"warTotalP90":23.5,
   "bucketLo":"bust","bucketHi":"star","pBust":0.3,"surNpv":30000000},
  {"key":"cons_kid","name":"Cons Kid","pos":"OF","age":19.5,"team":"SEA","src":"prospect",
   "fv":45.2,"consensus_fv":45.2,"fv_source":"consensus","eta":2027,
   "war":[0.8,1.2,1.6,2.0],"warP10":[0,0,0.2,0.4],"warP90":[2.5,3.5,4.5,5],
   "warTotal":5.6,"warTotalP10":0.6,"warTotalP90":15.5,
   "bucketLo":"bust","bucketHi":"solid","pBust":0.45,"surNpv":12000000}
 ],
 "team_outlook":[]
}"""

# Player detail payload (data/mlb_player_detail.json contract).
DETAIL = """{
 "players":{
  "vet_guy":{"key":"vet_guy","name":"Vet Guy","pos":"SS","age":29.4,"team":"NYY","mlbam":545361,
   "proj":{"war":[3.0,2.8,2.6,2.4,2.2],"warP10":[1.2,1.1,1.0,0.9,0.8],"warP90":[4.8,4.6,4.4,4.2,4.0],
     "warTotal":13.0,"warTotalP10":5.0,"warTotalP90":22.0,"surNpv":40000000,"thru":2028,"aav":25000000},
   "career":[{"y":2025,"pa":600,"avg":".300","obp":".380","slg":".500","ops":".880","hr":30,"sb":10,
     "bbPct":11,"kPct":18,"iso":0.2,"war":5.1}],
   "sc":{"season":2025,"metrics":[{"label":"xwOBA","value":".390","pct":95}]}}
 }
}"""

FIELDING = '{"season":2026,"players":{}}'


def _prelude(hash_: str, fail_fetch: bool = False) -> str:
    fetch_js = (
        # every fetch fails: exercises the F-02 error path
        "var fetch=function(){return {then:function(){return this;},"
        "catch:function(cb){cb(new Error('network down'));return this;}};};"
        if fail_fetch else
        "var __payloads={'/data/mlb_projections.json':BOARD,"
        "'/data/mlb_player_detail.json':DETAIL,"
        "'/data/mlb_fielding_positions.json':FIELDING};"
        "var fetch=function(url){var p=__payloads[url];"
        "if(p===undefined)return {then:function(){return this;},"
        "catch:function(cb){cb(new Error('HTTP 404'));return this;}};"
        "return FT({ok:true,json:function(){return FT(p);}});};"
    )
    return f"""
    var __html={{}};
    function __el(id){{return new Proxy(function(){{return __el(id);}},{{
      get:function(t,k){{ if(k==='innerHTML')return __html[id]||'';
        if(k==='classList')return {{add:function(){{}},remove:function(){{}},toggle:function(){{}},contains:function(){{return false;}}}};
        if(k==='querySelectorAll')return function(){{return [];}};
        if(k==='getAttribute')return function(){{return null;}};
        if(k==='setAttribute'||k==='addEventListener'||k==='removeEventListener'||k==='focus'||k==='setSelectionRange'||k==='appendChild')return function(){{}};
        if(k==='querySelector'||k==='closest')return function(){{return __el(id+'q');}};
        if(k==='value'||k==='textContent')return ''; if(k==='checked')return true; if(k==='selectionStart')return 0;
        if(k==='dataset')return {{}};
        return __el(id);}},
      set:function(t,k,v){{if(k==='innerHTML')__html[id]=v;return true;}}, apply:function(){{return __el(id);}}}});}}
    function FT(val){{return {{then:function(cb){{var r=cb(val);return (r&&r.then)?r:FT(r);}},catch:function(cb){{return FT(val);}}}};}}
    function URLSearchParams(s){{ this._m={{}}; s=String(s==null?'':s);
      if(s.charAt(0)==='?'||s.charAt(0)==='#')s=s.slice(1);
      var self=this; s.split('&').forEach(function(kv){{ if(!kv)return;
        var i=kv.indexOf('='); var k=i<0?kv:kv.slice(0,i); var v=i<0?'':kv.slice(i+1);
        self._m[decodeURIComponent(k)]=decodeURIComponent(v.replace(/\\+/g,' ')); }}); }}
    URLSearchParams.prototype.get=function(k){{ return (k in this._m)?this._m[k]:null; }};
    URLSearchParams.prototype.has=function(k){{ return (k in this._m); }};
    URLSearchParams.prototype.set=function(k,v){{ this._m[k]=String(v); }};
    URLSearchParams.prototype.toString=function(){{ var out=[];
      for(var k in this._m) out.push(encodeURIComponent(k)+'='+encodeURIComponent(this._m[k]));
      return out.join('&'); }};
    var BOARD={BOARD};
    var DETAIL={DETAIL};
    var FIELDING={FIELDING};
    {fetch_js}
    var history={{replaceState:function(){{}}}};
    var location={{hash:'{hash_}',pathname:'/projections/'}};
    var document={{readyState:'complete',getElementById:function(id){{return __el(id);}},
      querySelector:function(){{return __el('q');}},querySelectorAll:function(){{return [];}},
      createElement:function(){{return __el('c');}},addEventListener:function(){{}},
      body:__el('body'),documentElement:__el('de'),head:__el('head')}};
    var EEPHUS_HUB={{fvCeil:function(v){{return Math.ceil(Number(v));}},
      teamLogo:function(){{return '';}},
      links:function(){{return {{then:function(){{}}}};}}}};
    var window={{location:location,document:document,history:history,fetch:fetch,
      EEPHUS_GL:{{wire:function(){{}}}},EEPHUS_HUB:EEPHUS_HUB,
      addEventListener:function(){{}},setTimeout:function(){{}}}};
    var navigator={{userAgent:'smoke'}};
    """


def _render(hash_: str, fail_fetch: bool = False) -> str:
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_, fail_fetch) + JS)
    return ctx.eval("__html['proj-rows'] || ''")


# ---------------------------------------------------------------------------
# F-02: fetch failure paints a visible error state with a retry affordance
# ---------------------------------------------------------------------------

def test_fetch_failure_renders_error_state():
    html = _render("", fail_fetch=True)
    assert "Data failed to load" in html
    assert "nightly build is mid-run" in html
    assert "proj-retry" in html
    assert 'role="alert"' in html


# ---------------------------------------------------------------------------
# eFV-primary prospect grade language (board rows + #cmp)
# ---------------------------------------------------------------------------

def test_board_prospect_tag_leads_with_efv_round_nearest():
    html = _render("")
    # eFV rounds to NEAREST: 50.4 -> 50 (a ceiling display would say 51)
    assert "eFV 50" in html
    assert "FV 51" not in html
    # consensus fallback keeps the FV + CEILING idiom: 45.2 -> 46
    assert "FV 46" in html
    # the tag title discloses the grade source + the consensus read
    assert "Graded on eFV" in html
    assert "consensus FV 50" in html


def test_compare_heads_lead_with_efv():
    html = _render("#cmp=efv_kid,cons_kid")
    assert "Head-to-Head" in html
    assert "eFV 50" in html          # xfv-graded prospect leads with eFV
    assert "FV 46" in html           # consensus fallback keeps fvCeil display
    assert "FV 51" not in html


# ---------------------------------------------------------------------------
# Player detail: explicit Upside element = per-year P90 only, never a summed
# multi-year quantile total (the F-01 pattern is not extended)
# ---------------------------------------------------------------------------

def test_player_detail_upside_is_per_year_p90():
    html = _render("#player=vet_guy")
    assert "Upside" in html
    assert "P90 outcome per season" in html
    assert "do not add up to a multi-year total" in html
    # isolate the upside section: from its title to the next section div
    up = html.split("P90 outcome per season")[1].split('<div class="mlbp-section">')[0]
    for v in ("4.8", "4.6", "4.4", "4.2", "4.0"):
        assert v in up, f"per-year P90 {v} missing from the upside strip"
    assert "2026" in up and "2030" in up          # season labels
    # the summed multi-year P90 (22.0) must NOT appear inside the upside element
    assert "22.0" not in up


def test_player_detail_renders_hero_and_fan():
    html = _render("#player=vet_guy")
    assert "Vet Guy" in html
    assert "Projected bWAR" in html               # fan chart section
    assert "Statcast Percentiles" in html


# ---------------------------------------------------------------------------
# PROSPX-pattern board cards (Lane B, 2026-07-30)
# ---------------------------------------------------------------------------

def test_board_renders_cards_not_a_table():
    """The board moved off <table> onto the PROSPX two-row card. The old markup
    packed six elements into one ellipsized 320px cell, which is what made it
    feel cramped; widening a table would not have fixed that."""
    html = _render("")
    assert "mlb-card proj-card" in html, "board did not render cards"
    assert "mlb-card-list" in html
    # the season projection is the row-2 tape, so it must be inside one
    assert "mlb-tape" in html and "mlb-chip" in html
    assert "proj-table" not in html, "the retired table shell is still being emitted"


def test_every_board_header_is_a_keyboard_sortable_button():
    """Projections was the ONE module below the a11y contract that fa.js,
    mlbstats.js and prospx all already met: its sort headers were plain <th>
    with a click handler, so a keyboard user could not sort at all, and rank
    and name were not sortable by any means."""
    html = _render("")
    head = html.split('class="mlb-card-head"')[1].split("</div>")[0]
    for key in ("rank", "name", "warTotal", "sur"):
        assert f'data-psort="{key}"' in head, f"{key} is not a sort header"
    # every header advertises itself to assistive tech and is reachable by tab
    assert head.count('role="button"') >= 4
    assert head.count('tabindex="0"') >= 4
    assert 'aria-sort=' in head


def test_cards_are_focusable_and_carry_their_own_destination():
    """Whole-card activation, matching the PROSPX row. The href rides the card
    so keyboard and mouse open the same place without a lookup table."""
    html = _render("")
    card = html.split('class="mlb-card proj-card"')[1][:400]
    assert 'tabindex="0"' in card and 'role="button"' in card
    assert "data-card-href=" in card
