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
  never a summed multi-year quantile total (F-01 stays quarantined);
- the player page layout (2026-09-11): tab sets by role, the active tab kept in
  #ptab= through an async fill, async fills landing in their own slots, the
  scale family each index is banded on, and the Defense and Game context
  blocks. Sections are isolated by their data-mlbp-section hook, never by
  markup a styling change would move.
- the Players table: one row per player, keyboard-sortable column headers,
  the F-01 total band never rendered

Skips when py_mini_racer is unavailable so it never blocks a machine without it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
# The value ruler is a separate module now and every cut lives in it, so any
# harness that evaluates a board file has to evaluate this one first. In the
# browser the same ordering is a head tag placed immediately after the nav
# script (build_site.py), not luck: deferred scripts run in document order.
TIERS_JS = (ROOT / "assets" / "eephus-tiers.js").read_text(encoding="utf-8")

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
   "warTotal":13.0,"warTotalP10Comon":5.0,"warTotalP90Comon":22.0,
   "thru":2028,"aav":25000000,"surNpv":40000000}
 ],
 "prospects":[
  {"key":"efv_kid","name":"Efv Kid","pos":"SS","age":20.1,"team":"BOS","src":"prospect",
   "fv":50.4,"consensus_fv":50,"fv_source":"xfv","eta":2026,
   "war":[1.0,1.5,2.0,2.5,3.0],"warP10":[0,0.2,0.4,0.6,0.8],"warP90":[3,4,5,5.5,6],
   "warTotal":10.0,"warTotalP10Comon":2.0,"warTotalP90Comon":23.5,
   "warPTH":[2.0,2.6,3.2,3.8,4.4],"warTotalPTH":16.0,"warPeak":4.4,
   "bucketLo":"bust","bucketHi":"star","pBust":0.3,"surNpv":30000000},
  {"key":"cons_kid","name":"Cons Kid","pos":"OF","age":19.5,"team":"SEA","src":"prospect",
   "fv":45.2,"consensus_fv":45.2,"fv_source":"consensus","eta":2027,
   "war":[0.8,1.2,1.6,2.0],"warP10":[0,0,0.2,0.4],"warP90":[2.5,3.5,4.5,5],
   "warTotal":5.6,"warTotalP10Comon":0.6,"warTotalP90Comon":15.5,
   "bucketLo":"bust","bucketHi":"solid","pBust":0.45,"surNpv":12000000}
 ],
 "team_outlook":[]
}"""

# Player detail payload (data/mlb_player_detail.json contract). Every banded
# index a test reads sits at 113, and 113 is the value that separates the two
# rulers: `good` on the ratio ladder (130 / 120 / 112 / 100 / 88) and `great` on
# the z ladder (120 / 113 / 107 / 100 / 93). The family class in the markup
# (vt-fam-ratio against vt-fam-z) says which one drew it, which is the evidence
# the old rem-* class names could not carry.
DETAIL = json.dumps({"players": {
    "vet_guy": {
        "key": "vet_guy", "name": "Vet Guy", "pos": "SS", "age": 29.4, "team": "NYY",
        "mlbam": 545361, "isPit": False,
        "proj": {"war": [3.0, 2.8, 2.6, 2.4, 2.2], "warP10": [1.2, 1.1, 1.0, 0.9, 0.8],
                 "warP90": [4.8, 4.6, 4.4, 4.2, 4.0], "warTotal": 13.0, "warTotalP10Comon": 5.0,
                 "warTotalP90Comon": 22.0, "surNpv": 40000000, "thru": 2028, "aav": 25000000},
        "career": [{"y": 2025, "pa": 600, "avg": ".300", "obp": ".380", "slg": ".500",
                    "ops": ".880", "hr": 30, "sb": 10, "bbPct": 11, "kPct": 18, "iso": 0.2,
                    "war": 5.1}],
        "sc": {"season": 2025, "metrics": [
            {"label": "xwOBA", "value": ".390", "pct": 95},
            {"label": "Luck (xwOBA-wOBA)", "value": "+0.031", "pct": 99}]},
        "skills": {
            "hem": {"season": 2026, "hemPlus": 113, "xhemPlus": 108,
                    "wrcPlus": 121, "qualified": True, "pa": 610, "warPaPlus": 113,
                    "warPaPlusPct": 90},
            "lev": {"kind": "bat", "season": 2026, "wpa": 1.234, "wpaLi": 0.8, "pli": 1.02,
                    "clutch": -0.31},
            "def": {"season": 2026, "pos": "SS", "inn": 1030.3, "posInn": {"SS": 1030.3},
                    "qualified": True, "demPlus": 113, "demPlusPct": 88, "demPlusPosPct": 81,
                    "fldTotal": 6.4, "posRuns": 5.9, "defRuns": 12.3}}},
    "ace_arm": {
        "key": "ace_arm", "name": "Ace Arm", "pos": "SP", "age": 28.0, "team": "DET",
        "mlbam": 669373, "isPit": True,
        "proj": {"war": [4.0, 3.8, 3.5, 3.1, 2.8], "warP10": [2.0, 1.8, 1.5, 1.2, 1.0],
                 "warP90": [6.0, 5.8, 5.5, 5.1, 4.8], "warTotal": 17.2, "surNpv": 90000000},
        "career": [{"y": 2025, "ip": "195.1", "era": 2.21, "kPct": 32.2, "bbPct": 4.6,
                    "war": 6.1, "war_bwar": 6.6, "war_fwar": 6.4}],
        "sc": {"season": 2025, "metrics": [{"label": "xwOBA Against", "value": ".260", "pct": 97}]},
        # Savant pitch-arsenal-stats for a pitcher: positive rv100 = runs saved.
        "arsenal": [{"pitch": "4-Seam Fastball", "usage": 35.1, "rv100": 1.2, "whiff": 24.0,
                     "ba": 0.21},
                    {"pitch": "Changeup", "usage": 12.0, "rv100": -1.6, "whiff": 18.0,
                     "ba": 0.29}],
        "skills": {
            "pitch": {"kind": "sp", "season": 2026, "role": "SP", "ip": 180.1,
                      "qualified": True, "semPlus": 113, "xsemPlus": 110, "warIpPlus": 113,
                      "warIpPlusPct": 91, "gs": 30, "ipPerGs": 6.01},
            "lev": {"kind": "sp", "season": 2026, "wpa": 2.5, "wpaLi": 1.1,
                    "wpaPerStart": 0.083}}},
    "backstop": {
        "key": "backstop", "name": "Back Stop", "pos": "C", "age": 26.0, "team": "DET",
        "mlbam": 693307, "isPit": False,
        "career": [{"y": 2025, "pa": 400, "avg": ".250", "obp": ".310", "slg": ".400",
                    "ops": ".710", "hr": 12, "sb": 1, "war": 2.0}],
        "skills": {"def": {"season": 2026, "pos": "C", "inn": 908.7, "posInn": {"C": 908.7},
                           "qualified": True, "demPlus": 133, "demPlusPct": 100,
                           "demPlusPosPct": 99, "fldTotal": 14.4, "frmRuns": 8.2,
                           "posRuns": 4.8, "posRunsFg": 3.1, "defRuns": 19.1}}},
    "two_way": {
        "key": "two_way", "name": "Two Way", "pos": "DH/SP", "age": 31.0, "team": "LAD",
        "mlbam": 660271, "isPit": False, "twoWay": True,
        "proj": {"war": [9.2, 7.9], "warP10": [5.0, 4.0], "warP90": [12.0, 11.0],
                 "warTotal": 17.1, "warHit": [6.0, 5.3], "warPit": [3.2, 2.6]},
        "career": [{"y": 2025, "pa": 700, "avg": ".280", "obp": ".390", "slg": ".600",
                    "ops": ".990", "hr": 50, "sb": 20, "war": 7.0}],
        "careerPit": [{"y": 2025, "ip": "47.0", "era": 3.10, "kPct": 30.0, "bbPct": 6.0,
                       "war": 1.2}],
        "sc": {"season": 2025, "metrics": [{"label": "Exit Velo", "value": "95.0", "pct": 99}]},
        "scPit": {"season": 2025, "metrics": [{"label": "EV Against", "value": "86.0", "pct": 90}]},
        "skills": {"hem": {"hemPlus": 170, "qualified": True}}},
}})

# The nightly games-by-position file: keyed by MLBAM id, rows [g, gs, inn],
# stamped with the fielding feed's own date (as_of). The "vet_guy" slug row is a
# decoy: the strip joins on the card's mlbam, so a slug join would print its P.
FIELDING = json.dumps({"season": 2026, "as_of": "2026-09-23", "generated_at": "2026-09-24",
                       "players": {"545361": {"SS": [120, 118, 1030.3]},
                                   "vet_guy": {"P": [18, 0, 20.0]}}})


def _prelude(hash_: str, fail_fetch: bool = False) -> str:
    fetch_js = (
        # every fetch fails: exercises the F-02 error path
        "var fetch=function(){return {then:function(){return this;},"
        "catch:function(cb){cb(new Error('network down'));return this;}};};"
        if fail_fetch else
        "var __payloads={'/data/mlb_projections.json':BOARD,"
        "'/data/mlb_player_detail.json':DETAIL,"
        "'/data/mlb_position_games.json':FIELDING};"
        # The per-player shards mlb_player_export writes (QMLP01): one card plus
        # the board's first_season and horizon, as the page fetches them.
        "for(var __k in DETAIL.players){__payloads['/data/mlb_player_detail/'+encodeURIComponent(__k)+'.json']="
        "{generated_at:'2026-06-30',first_season:BOARD.first_season,horizon:BOARD.horizon,"
        "key:__k,player:DETAIL.players[__k]};}"
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
    return _render_all(hash_, fail_fetch).get("proj-rows", "")


def _render_all(hash_: str, fail_fetch: bool = False) -> dict:
    """Every element's innerHTML by id. The stub's fetch is synchronous, so each
    async fill has already landed by the time this returns; a fill that patches
    its slot shows up under the slot's own id, not inside proj-rows."""
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_, fail_fetch) + TIERS_JS + JS)
    return json.loads(ctx.eval("JSON.stringify(__html)"))


def _section(html: str, sid: str) -> str:
    """One data-mlbp-section, sliced to the next section, panel or page foot.
    Asserts the slice both starts and terminates, so it can never go vacuous
    by running to the end of the page."""
    hook = f'data-mlbp-section="{sid}"'
    assert html.count("data-mlbp-section=") >= 2, "section hooks missing"
    assert hook in html, f"no {sid} section"
    rest = html.split(hook, 1)[1]
    part = re.split(r"data-mlbp-section=|data-mlbp-panel=|mlbp-page-foot", rest, maxsplit=1)[0]
    assert len(part) < len(rest), f"the {sid} slice never terminated"
    return part


def _tabs(html: str) -> list[tuple[str, str]]:
    return re.findall(r'data-mlbp-tab="([a-z]+)"[^>]*aria-selected="(true|false)"', html)


def _visible_panels(html: str) -> list[str]:
    return [pid for pid, attrs in re.findall(r'data-mlbp-panel="([a-z]+)"([^>]*)>', html)
            if "hidden" not in attrs]


def _tile_classes(html: str, gl: str) -> list[str]:
    """The value classes of every tile whose label is the glossary term `gl`."""
    return re.findall(
        rf'<span class="mlbp-tile-label"><span data-gl="{gl}">[^<]*</span></span>'
        r'<span class="mlbp-tile-val ([^"]*)">', html)


# ---------------------------------------------------------------------------
# F-02: fetch failure paints a visible error state with a retry affordance
# ---------------------------------------------------------------------------

def test_fetch_failure_renders_error_state():
    html = _render("", fail_fetch=True)
    assert "Projections did not load" in html
    assert "nightly build may be writing it" in html
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
    # isolate the upside section by its hook (to the next section, panel or the
    # page foot); _section asserts the slice is non-vacuous
    up = _section(html, "upside")
    assert "P90 outcome per season" in up
    for v in ("4.8", "4.6", "4.4", "4.2", "4.0"):
        assert v in up, f"per-year P90 {v} missing from the upside strip"
    assert "2026" in up and "2030" in up          # season labels
    # the summed multi-year P90 (22.0) must NOT appear inside the upside element
    assert "22.0" not in up


def test_player_detail_renders_hero_and_fan():
    html = _render("#player=vet_guy")
    assert "Vet Guy" in html
    assert "Projected WAR" in html                # fan chart section (fWAR label epoch 2026-10-03: a model basis)
    assert "bWAR (Baseball-Reference)" not in html  # the pre-epoch basis label
    assert "Statcast Percentiles" in html


# ---------------------------------------------------------------------------
# Player page layout (2026-09-11): tabs by role, tab state, slots, rulers
# ---------------------------------------------------------------------------

def test_tab_sets_by_role_and_one_visible_panel():
    expect = {
        "vet_guy": ["overview", "hitting", "defense", "value", "projection"],
        "ace_arm": ["overview", "pitching", "value", "projection"],
        "two_way": ["overview", "hitting", "pitching", "value", "projection"],
    }
    for key, ids in expect.items():
        html = _render(f"#player={key}")
        tabs = _tabs(html)
        assert [t for t, _ in tabs] == ids, (key, tabs)
        assert html.count("data-mlbp-panel=") == len(tabs), key
        visible = _visible_panels(html)
        assert visible == [t for t, sel in tabs if sel == "true"] == ["overview"], (key, visible)


def test_pitcher_has_no_defense_tab():
    html = _render("#player=ace_arm")
    assert 'data-mlbp-tab="defense"' not in html
    assert 'data-mlbp-panel="defense"' not in html
    assert 'data-mlbp-tab="hitting"' not in html
    # a #ptab= naming a tab the card does not have falls back to the first tab
    html = _render("#player=ace_arm&ptab=defense")
    assert _visible_panels(html) == ["overview"]


def test_ptab_deep_link_keeps_its_panel_after_the_async_fill():
    out = _render_all("#player=vet_guy&ptab=defense")
    html = out["proj-rows"]
    # the fielding fixture landed (synchronous stub fetch) ...
    usage = out.get("mlbp-slot-usage", "")
    assert "position-usage-chip" in usage and "SS" in usage, "usage fill never landed"
    assert "as of 2026-09-23" in usage             # the feed's own vintage, stamped
    assert "<span>P</span>" not in usage           # joined on mlbam, never the slug
    # ... into its slot, without re-rendering the page back to the first tab
    assert _visible_panels(html) == ["defense"]
    assert [t for t, sel in _tabs(html) if sel == "true"] == ["defense"]
    # without #ptab= the page opens on Overview
    assert _visible_panels(_render("#player=vet_guy")) == ["overview"]


def test_async_slots_are_always_emitted():
    html = _render("#player=vet_guy")
    for slot in ("hub", "usage", "batspeed"):
        assert f'data-mlbp-slot="{slot}"' in html, slot
    assert 'data-mlbp-slot="pitchlb"' in _render("#player=ace_arm")


def test_dem_plus_tile_is_on_the_z_ruler_not_the_hem_cut():
    """Same intent as before the value ruler, with stronger evidence. 113 is
    `great` on the z ladder and `good` on the ratio ladder, and the FAMILY class
    proves which ruler drew it rather than leaving it to a shared class name.
    HEM+ used to carry proj-pos here, i.e. a SIGN pair with no elite step; it
    carries a real tier now."""
    html = _render("#player=vet_guy")
    dem = _tile_classes(html, "dem_plus")
    assert len(dem) == 2, dem                     # hero slot 4 + the Defense tab
    for cls in dem:
        assert "mlbp-scale-z" in cls and "vt-fam-z vt-great" in cls, cls
        assert "proj-pos" not in cls and "vt-fam-ratio" not in cls, cls
    for cls in _tile_classes(html, "war_pa_plus"):
        assert "mlbp-scale-z" in cls and "vt-fam-z vt-great" in cls, cls
    hem = _tile_classes(html, "hem_plus")
    assert hem and all("mlbp-scale-ratio" in c and "vt-fam-ratio vt-good" in c
                       for c in hem), hem
    assert all("proj-pos" not in c for c in hem), hem


def test_the_z_family_bands_exactly_as_the_mlbstats_board_does():
    """Owner decision 25 (2026-09-11): one colour ruler, 93/107/120, for DEM+,
    WAR/PA+ and WAR/IP+ on both surfaces. This used to read two banding
    functions by regex and compare the pair, which could only ever prove the two
    COPIES agreed. There is one ladder now, in one file, so the assertion is
    strictly stronger: the locked cuts are still boundaries, they still carry the
    tier names they carried before, and NEITHER board file contains a cut."""
    cuts = re.search(r"z:\s*\{ cuts: \[([^\]]+)\]", TIERS_JS).group(1)
    cuts = [float(x) for x in cuts.split(",")]
    assert cuts == [120, 113, 107, 100, 93], cuts
    assert {120, 107, 93} <= set(cuts)
    ctx = MiniRacer()
    ctx.eval("var window = {};" + TIERS_JS)
    for v, tier in ((120, "elite"), (107, "good"), (93, "avg")):
        got = ctx.eval('EephusTiers.tier(%d, "z")' % v)
        assert got == tier, (v, got)
    ms = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    for f in (ms, JS):
        assert "rem-elite" not in f and "rem-good" not in f
        assert not re.search(r'>=\s*\d+\) return "rem-', f)


def test_every_z_band_renders_on_the_card():
    """One value per TIER through the real tiles, all six the z ladder can
    reach: 133 elite (the backstop's DEM+), 113 great (WAR/IP+), and the rest off
    fixture copies. The z family never reaches vt-poor - red is below zero and
    an index cannot go there."""
    assert all("vt-elite" in c for c in _tile_classes(_render("#player=backstop"), "dem_plus"))
    for cls in _tile_classes(_render("#player=ace_arm"), "war_ip_plus_sp"):
        assert "mlbp-scale-z" in cls and "vt-great" in cls, cls
    global DETAIL
    base = DETAIL
    try:
        for v, band in ((125, "vt-elite"), (116, "vt-great"), (110, "vt-good"),
                        (103, "vt-above"), (97, "vt-avg"), (88, "vt-below"),
                        (93, "vt-avg"), (92, "vt-below"), (107, "vt-good"),
                        (120, "vt-elite")):
            d = json.loads(base)
            d["players"]["vet_guy"]["skills"]["def"]["demPlus"] = v
            DETAIL = json.dumps(d)
            cls = _tile_classes(_render("#player=vet_guy"), "dem_plus")
            assert cls and all(band in c and "vt-poor" not in c for c in cls), (v, cls)
    finally:
        DETAIL = base


def test_the_defense_lens_paints_the_z_band_on_an_inner_span():
    """.mlbp-lens-num sets colour AND weight 800 at one class and is declared
    after the ruler block, so a one-class .vt-* rule loses to it on source order
    and EVERY tiered lens rides an inner span. The ratio lens used to sit on a
    sign pair (proj-pos) that could not win that fight either, which is the F4
    drift this test is the record of: it carries a real tier now."""
    html = _render("#player=vet_guy")
    lens = html.split('data-mlbp-goto="defense"', 1)[1].split('class="mlbp-lens"', 1)[0]
    assert ('<span class="mlbp-lens-num"><span class="mlbp-scale-z vt-fam-z vt-great">'
            '113</span></span>') in lens
    hit = html.split('data-mlbp-goto="hitting"', 1)[1].split('class="mlbp-lens"', 1)[0]
    assert ('<span class="mlbp-lens-num"><span class="mlbp-scale-ratio vt-fam-ratio '
            'vt-good">113</span></span>') in hit
    assert "proj-pos" not in hit.split("mlbp-lens-val", 1)[1][:200]


def test_arsenal_run_value_is_coloured_from_the_pitchers_side():
    """M05-03: Savant's pitcher arsenal run value is positive when the pitch
    saves runs, so a positive RV/100 is the good (green) cell and a negative
    one the bad (red) cell, and the header says which way the sign runs."""
    ars = _section(_render("#player=ace_arm&ptab=pitching"), "pitching-arsenal")
    assert '<td class="proj-pos">1.2</td>' in ars
    assert '<td class="proj-neg">-1.6</td>' in ars
    assert "positive = runs saved" in ars


def _horizon_row(row):
    """A nine-figure deal that runs past the five priced seasons: the salary
    path stops at 2031, the guarantee (and so the control end) runs to 2039."""
    row = dict(row)
    row.update({"salPath": [[s, 51000000, 51000000, 51000000, "signed", "contract", 0]
                            for s in range(2027, 2032)],
                "salThru": 2031, "salSrc": "contract", "thru": 2039, "ctrlThru": 2039,
                "ctrlWhy": "horizon", "aav": 51000000, "surNpv": 232000000,
                "surTotal": 234000000, "surRos": 2000000})
    return row


def test_a_deal_past_the_horizon_never_calls_its_surplus_the_control_window():
    """M05-01: surplus prices 2027-2031 only. On a guarantee through 2039 the
    card must name the seasons it covers and the eight it leaves unpriced,
    never label the number as the whole club control window."""
    global DETAIL, BOARD
    base_d, base_b = DETAIL, BOARD
    try:
        d = json.loads(base_d)
        d["players"]["vet_guy"]["proj"] = _horizon_row(d["players"]["vet_guy"]["proj"])
        DETAIL = json.dumps(d)
        html = _render("#player=vet_guy&ptab=projection")
        assert "Surplus (2027-2031)" in html
        assert "Surplus (club control window)" not in html
        assert "8 guaranteed seasons after 2031 not priced" in html
        foot = html.split("data-proj-horizon-tail", 1)[1][:300]
        assert "Surplus prices 2027-2031 only." in foot
        assert "The 8 guaranteed seasons 2032-2039" in foot and "$408M" in foot
        bd = json.loads(base_b)
        bd["first_season"] = 2027
        bd["vets"][0] = _horizon_row(bd["vets"][0])
        BOARD = json.dumps(bd)
        board = _render("")
        assert "over 2027-2031 only, not the whole club control window" in board
    finally:
        DETAIL, BOARD = base_d, base_b


def test_the_fa_block_names_the_path_it_prices_on():
    """M05-06: the Projection tab prints the proj_lgbm_v1 path and, below it,
    FA values priced on the Marcel champion. The block must name that path,
    its seasons and Deal WAR, and compare the two sums on shared seasons."""
    global DETAIL, BOARD
    base_d, base_b = DETAIL, BOARD
    try:
        d = json.loads(base_d)
        d["players"]["vet_guy"]["fa"] = {
            "status": "FA 2027", "projYears": 7, "projGuar": 150000000,
            "projAav": 21000000, "rational": 180000000, "surplus": 30000000,
            "dealPlus": 120, "verdict": "fair",
            "warPath": [4.25, 3.75, 3.25, 2.71, 2.08, 1.36, 0.74], "warTotal": 18.1}
        DETAIL = json.dumps(d)
        bd = json.loads(base_b)
        bd["first_season"] = 2027
        BOARD = json.dumps(bd)
        blk = _section(_render("#player=vet_guy&ptab=projection"), "contract-fa")
        note = blk.split("data-fa-pricing-path", 1)[1][:900]
        assert "Marcel champion path" in note
        assert "4.3 / 3.8 / 3.3 / 2.7 / 2.1 / 1.4 / 0.7 (2027-2033)" in note
        assert "Deal WAR 18.1" in note
        # shared seasons 2027-2031: FA 16.0 against the card's 13.0
        assert "Over 2027-2031 the FA path sums 16.0 against 13.0" in note
    finally:
        DETAIL, BOARD = base_d, base_b


def test_season_lines_carry_the_ewar_column_again():
    """Owner decision 20 (2026-09-11): the eWAR column is back in the season
    lines, and the Value tab keeps its bars. A two-way card shows each side's
    own eWAR in that side's table."""
    vet = _render("#player=vet_guy")
    lines = _section(vet, "hitting-lines")
    assert '<th><span data-gl="ewar">eWAR</span></th>' in lines
    assert "<td>5.1</td>" in lines
    assert 'data-mlbp-section="value-war"' in vet and "mlbp-warbars" in vet
    ace = _section(_render("#player=ace_arm"), "pitching-lines")
    assert '<span data-gl="ewar">eWAR</span>' in ace and "<td>6.1</td>" in ace
    two = _render("#player=two_way")
    assert "<td>7.0</td>" in _section(two, "hitting-lines")
    assert "<td>1.2</td>" in _section(two, "pitching-lines")
    # a season with no WAR on file prints the null marker, not a blank or 0.0
    global DETAIL
    base = DETAIL
    try:
        d = json.loads(base)
        d["players"]["vet_guy"]["career"][0]["war"] = None
        DETAIL = json.dumps(d)
        lines = _section(_render("#player=vet_guy"), "hitting-lines")
        assert lines.count("<td> - </td>") == 1 and "<td>0.0</td>" not in lines
    finally:
        DETAIL = base


FG_WAR_TIP = ("FanGraphs' published WAR, as MLB's StatsAPI publishes it. "
              "A reference only: the site's WAR is eWAR.")


def test_ewar_v3_cards_carry_realized_v2_and_bwar_beside_ewar():
    """EBR_GATE.md 11.10.5 (owner answers EW3-19 and EW3-20): once the displayed
    eWAR is eWAR v3 the season lines print eWAR, eWAR realized, then eWAR v2,
    FanGraphs WAR and bWAR as references; a card without war_real prints none of
    the new columns."""
    global DETAIL
    base = DETAIL
    try:
        d = json.loads(base)
        for r in d["players"]["ace_arm"]["career"]:
            r["war_real"] = 5.8
            r["war_ewar2"] = 6.3
        DETAIL = json.dumps(d)
        lines = _section(_render("#player=ace_arm"), "pitching-lines")
        order = [lines.index(s) for s in ('<span data-gl="ewar">eWAR</span>', "eWAR realized</",
                                          ">eWAR v2</th>", ">FanGraphs WAR</th>", ">bWAR</th>")]
        assert order == sorted(order), order
        assert '<td>6.1</td><td class="mlbp-realwar">5.8</td><td class="mlbp-fgwar">6.3</td>' in lines
    finally:
        DETAIL = base
    plain = _section(_render("#player=ace_arm"), "pitching-lines")
    assert "eWAR realized" not in plain and ">bWAR</th>" not in plain and ">eWAR v2</th>" not in plain


def test_ewar_parts_table_names_each_part_with_its_delta():
    """Owner answer SWAR-Q4 (EBR_3_EWAR_V3): the Value tab names eWAR's parts per
    season with their delta in wins (war_parts); a column only for a part some
    row carries; a two-way card adds a Side column; no war_parts, no section."""
    global DETAIL
    base = DETAIL
    try:
        d = json.loads(base)
        d["players"]["ace_arm"]["career"][-1]["war_parts"] = {"eabs": -0.09, "r2": 2.11}
        d["players"]["two_way"]["career"][-1]["war_parts"] = {"eabs": 0.12}
        DETAIL = json.dumps(d)
        parts = _section(_render("#player=ace_arm"), "value-ewar-parts")
        assert ">eABS (ABS challenges)</th>" in parts and ">Realized pitching</th>" in parts
        assert parts.index("eABS (ABS challenges)") < parts.index("Realized pitching")
        assert "<td>-0.09</td><td>+2.11</td>" in parts
        assert "wins beyond FanGraphs WAR" in parts and "also takes realized pitching" in parts
        assert "regressed" not in parts and "validated" not in parts
        two = _section(_render("#player=two_way"), "value-ewar-parts")
        assert "<th>Side</th>" in two and "<td>hitting</td><td>+0.12</td>" in two
        assert "Realized pitching" not in two
    finally:
        DETAIL = base
    assert 'data-mlbp-section="value-ewar-parts"' not in _render("#player=ace_arm")


def test_the_xhem_part_column_carries_the_owner_sentence():
    """EBR_GATE.md 11.11 (owner EW3-51): a hitting row that carries the xHEM+ part gets
    its column, the owner's sentence in the column's tooltip, a sub-line saying eWAR adds
    half of xHEM+ while eWAR realized keeps FanGraphs' batting, and the realized column's
    tooltip says the same; a card without the part prints none of it."""
    import ewar_v3
    global DETAIL
    base = DETAIL
    try:
        d = json.loads(base)
        for r in d["players"]["two_way"]["career"]:
            r["war_real"] = 1.0
        d["players"]["two_way"]["career"][-1]["war_parts"] = {"eabs": 0.12, "xhem": -0.31}
        DETAIL = json.dumps(d)
        html = _render("#player=two_way")
        parts = _section(html, "value-ewar-parts")
        assert ">xHEM+ (half weight)</th>" in parts and "<td>+0.12</td><td>-0.31</td>" in parts
        assert ewar_v3.xhem_copy() in parts
        assert "+ half of xHEM+" in parts
        assert "keeps FanGraphs&#39; batting" in parts or "keeps FanGraphs' batting" in parts
        assert "override" not in parts.lower()
        assert "without the xHEM+ part eWAR carries" in html
    finally:
        DETAIL = base
    plain = _render("#player=two_way")
    assert "xHEM+ (half weight)" not in plain and "without the xHEM+ part eWAR carries" not in plain


def test_ewar_parts_labels_are_the_assembler_card_labels():
    """The card's part labels are ewar_v3.PART_LABELS verbatim (EBR_GATE.md
    11.10.2 and 11.10.3), so the card and the artifact name each part alike."""
    import ewar_v3
    block = JS.split("const EWAR_PARTS = [", 1)[1].split("];", 1)[0]
    found = dict(re.findall(r'\{ id: "([a-z0-9]+)", label: "([^"]+)"', block))
    assert found == ewar_v3.PART_LABELS


def test_fangraphs_war_rides_as_a_reference_column_beside_ewar():
    """Owner answer EPOCH-Q4 (task EPOCH_FWAR_REFERENCE_COLUMN): war_fwar is a
    REFERENCE column after eWAR, labelled FanGraphs WAR with its tooltip; the
    eWAR cell is unchanged, and a table whose rows carry no war_fwar gets no
    column at all."""
    ace = _render("#player=ace_arm")
    lines = _section(ace, "pitching-lines")
    th = f'<th class="mlbp-fgwar" title="{FG_WAR_TIP}">FanGraphs WAR</th>'
    assert th in lines
    # eWAR first, then the reference; the eWAR cell is the served 6.1
    assert lines.index('<span data-gl="ewar">eWAR</span>') < lines.index("FanGraphs WAR")
    assert '<td>6.1</td><td class="mlbp-fgwar">6.4</td>' in lines
    # the Value tab's bar keeps eWAR as its value and names the reference in its tooltip
    war = _section(ace, "value-war")
    assert "2025: 6.1 eWAR, bWAR 6.6, FanGraphs WAR 6.4 (reference)" in war
    assert ">6.1</text>" in war
    # no war_fwar on the card: no column, no tooltip mention
    vet = _render("#player=vet_guy")
    assert "FanGraphs WAR" not in _section(vet, "hitting-lines")
    assert "FanGraphs WAR" not in _section(vet, "value-war")
    # a row without a published value prints the null marker in the column
    global DETAIL
    base = DETAIL
    try:
        d = json.loads(base)
        d["players"]["ace_arm"]["career"].insert(0, {
            "y": 2024, "ip": "120.0", "era": 3.50, "kPct": 25.0, "bbPct": 7.0, "war": 2.0})
        DETAIL = json.dumps(d)
        lines = _section(_render("#player=ace_arm"), "pitching-lines")
        assert '<td>2.0</td><td class="mlbp-fgwar"> - </td>' in lines
        war = _section(_render("#player=ace_arm"), "value-war")
        assert "2024: 2.0 eWAR</title>" in war       # no published value: no reference in the tip
    finally:
        DETAIL = base


def test_hero_is_four_tiles_at_most_and_symmetric_by_role():
    for key in ("vet_guy", "ace_arm", "two_way", "backstop"):
        html = _render(f"#player={key}")
        hero = html.split('class="mlbp-hero"', 1)[1].split("data-mlbp-tab=", 1)[0]
        assert hero.count('class="mlbp-tile"') <= 4, key
    # two-way slot 1 carries both sides of the window
    assert "hit 11.3 / pit 5.8" in _render("#player=two_way")


def test_defense_panel_labels_published_runs_and_links_the_glossary():
    html = _render("#player=backstop")
    runs = _section(html, "defense-runs")
    assert "FanGraphs published" in runs
    # owner decision 18: the positional term in Def is ours, FanGraphs' beside it
    assert "our ladder" in runs and "Positional (ours)" in runs and "Positional (FG)" in runs
    assert "+4.8" in runs and "+3.1" in runs
    for gl in ("fielding_runs", "framing_runs", "positional_adjustment"):
        assert f'data-gl="{gl}"' in runs, gl
    assert "+14.4" in runs and "+8.2" in runs and "+19.1" in runs
    dem = _section(html, "defense-dem")
    assert 'data-gl="dem_plus"' in dem
    assert "/mlbstats/#section=defense" in dem
    assert "<span>C</span>:908.7" in _section(html, "defense-positions")
    # nothing on the Defense tab speaks of a prospect grade
    tab = html.split('data-mlbp-panel="defense"', 1)[1].split("data-mlbp-panel=", 1)[0]
    assert "eFV" not in tab


def test_game_context_renders_the_baked_leverage_block():
    hit = _section(_render("#player=vet_guy"), "hitting-context")
    assert "+1.23" in hit and "-0.31" in hit and 'data-gl="pli"' in hit
    pit = _section(_render("#player=ace_arm"), "pitching-context")
    assert "WPA/start" in pit and "+0.083" in pit


def test_two_way_keeps_both_sides():
    html = _render("#player=two_way")
    hitting = html.split('data-mlbp-panel="hitting"', 1)[1].split("data-mlbp-panel=", 1)[0]
    pitching = html.split('data-mlbp-panel="pitching"', 1)[1].split("data-mlbp-panel=", 1)[0]
    assert "As a hitter" in hitting and "As a pitcher" in pitching
    assert "MLB · hitting" in hitting and "MLB · pitching" in pitching


def test_luck_gap_is_said_as_the_difference_it_is():
    """The xHEM+ tile note is the plain difference of the two dots, computed
    client-side (xHEM+ 108 minus HEM+ 113). The card no longer reads a baked
    luckGap: the board's luck_gap is xwOBA minus wOBA in wOBA points since
    2026-09-24. The retired hero tooltip said the reverse sign."""
    idx = _section(_render("#player=vet_guy"), "hitting-index")
    assert "-5 vs HEM+" in idx
    assert "luckGap" not in JS
    assert "HEM+ minus xHEM+" not in JS


def test_luck_leaves_the_percentile_colour_scale():
    sc = _section(_render("#player=vet_guy"), "hitting-statcast")
    assert "mlbp-luck" in sc and "+0.031" in sc
    # the Luck row is not drawn as a percentile slider
    assert sc.count('class="mlbp-slider"') == 1


def test_statcast_bars_take_the_percentile_gradient_and_keep_the_fallback_step():
    """Owner ask 2026-10-01: each bar and its chip carry one colour from the
    shared percentile gradient (EephusTiers.pctColor) as an inline --pct, and
    both keep their pctClass step, which is what site.css paints where
    color-mix is unsupported. The Luck chip stays neutral: no --pct, no step."""
    sc = _section(_render("#player=vet_guy&ptab=hitting"), "hitting-statcast")
    mix = "color-mix(in oklab, var(--vt-great) 50%, var(--vt-elite))"  # p = 95
    assert f'class="mlbp-slider-fill is-elite" style="--pct:{mix};width:95%;"' in sc
    assert f'class="mlbp-slider-pct is-elite" style="--pct:{mix};left:94%;">95<' in sc
    luck = sc.split('class="mlbp-luck"', 1)[1]
    assert "--pct" not in luck and "is-elite" not in luck
    pit = _section(_render("#player=ace_arm&ptab=pitching"), "pitching-statcast")
    mix = "color-mix(in oklab, var(--vt-great) 30%, var(--vt-elite))"  # p = 97
    assert f'class="mlbp-slider-fill is-elite" style="--pct:{mix};width:97%;"' in pit


def test_the_slider_css_paints_from_pct_and_falls_back_to_the_steps():
    """The five steps stay the base rule: the PROSPX Statcast card draws the
    same classes with no --pct and must keep them, and so must a browser with
    no color-mix. The gradient is one opt-in rule behind @supports that only a
    row carrying --pct matches, at a specificity above the steps."""
    css = re.sub(r"/\*.*?\*/", "", (ROOT / "assets" / "site.css").read_text(encoding="utf-8"), flags=re.S)
    m = re.search(r"@supports \(color: color-mix\(in oklch, red, blue\)\) \{(.*?)\n\}", css, re.S)
    assert m, "no color-mix gated gradient block"
    block, rest = m.group(1), css.replace(m.group(0), "")
    assert re.search(r'\.mlbp-slider-track \.mlbp-slider-fill\[style\*="--pct:"\]\s*\{\s*background: var\(--pct\);', block)
    assert re.search(r'\.mlbp-slider-track \.mlbp-slider-pct\[style\*="--pct:"\]\s*\{\s*color: var\(--pct\); border-color: var\(--pct\);', block)
    for step in ("is-elite", "is-good", "is-avg", "is-low", "is-poor"):
        assert re.search(r"\.mlbp-slider-fill\.%s\s*\{\s*background:" % step, rest), step
    assert "--pct" not in rest, "outside the gated block nothing reads --pct"
    chip = re.search(r"\.mlbp-slider-pct\s*\{([^}]*)\}", rest).group(1)
    assert "background: var(--bg-primary)" in chip, "the chip keeps its solid ground"
    track = re.search(r"\.mlbp-slider-track\s*\{([^}]*)\}", rest).group(1)
    assert "var(--bg-tertiary)" in track, "the track stays neutral"


# ---------------------------------------------------------------------------
# Players TABLE (owner ask 2026-09-11: a table, not cards). The fixture's
# first_season is 2026: vet_guy thru 2028, aav $25.0M.
# ---------------------------------------------------------------------------


def _board(html):
    """The Players table, from its opening tag to its close. Asserts both ends
    so the slice can never go vacuous."""
    assert 'class="proj-board-table' in html, "board did not render its table"
    part = html.split('class="proj-board-table', 1)[1]
    assert "</table>" in part, "the board table never closed"
    return part.split("</table>", 1)[0]


def _head(html):
    return _board(html).split("<thead>", 1)[1].split("</thead>", 1)[0]


def _body(html):
    return _board(html).split("<tbody>", 1)[1].split("</tbody>", 1)[0]


def _row_keys(html):
    return re.findall(r'<tr data-key="([^"]+)"', _body(html))


def test_board_renders_one_table_row_per_player():
    """One <tr> per player in one <tbody> under one <thead>; the card
    primitives are gone from the board, and no detail line is open on load."""
    html = _render("")
    board = _board(html)
    assert "<thead>" in board and "<tbody>" in board
    assert _row_keys(html) == ["vet_guy", "efv_kid", "cons_kid"]
    for card_bit in ("mlb-card", "mlb-tape", "mlb-chip", "mlb-sortbar", "data-card-href"):
        assert card_bit not in html, f"{card_bit} is still emitted on the board"
    assert "proj-detail" not in _body(html)
    assert "data-export" in html.split('class="proj-board-table', 1)[1][:200]


def test_every_board_header_is_a_keyboard_sortable_columnheader():
    """aria-sort on a <th scope=col> (a columnheader, where ARIA exposes it)
    around a native <button> (Enter and Space for free). Every key a share
    link has carried keeps a header or a picker entry; exactly one is active."""
    html = _render("")
    head = _head(html)
    ths = [t for t in re.findall(r"<th\b[^>]*>.*?</th>", head, flags=re.S)
           if not re.match(r"<th\b[^>]*\bhidden\b", t)]      # export-only Pos, Team
    assert len(ths) >= 12
    for th in ths:
        assert 'scope="col"' in th and "aria-sort=" in th and "data-export-text=" in th
        assert re.search(r'<button type="button" class="proj-sort" data-psort="', th), th[:120]
        assert "data-gl" not in th, "a glossary hook inside a sort button is a nested tab stop"
    keys = re.findall(r'data-psort="([^"]+)"', head)
    # `ctrl` replaced `thru` on 2026-09-17: the column prints the last season the
    # club CONTROLS him, not the last season a contract guarantees him. A share
    # link carrying the old key still resolves (syncFromURL aliases it), which is
    # what test_unknown_sort_key_falls_back_and_dir_round_trips has to keep true.
    for key in ("rank", "name", "warTotal", "sur", "y0", "y1", "y2", "y3", "y4", "age", "aav", "ctrl"):
        assert key in keys, f"{key} lost its header"
    assert "thru" not in keys, "the guarantee year is the sub-line now, not the column"
    active = re.findall(r'aria-sort="(ascending|descending)"[^>]*>\s*<button[^>]*data-psort="([^"]+)"', head)
    assert active == [("descending", "warTotal")], active
    assert 'role="button"' not in head and "tabindex" not in head


def test_rows_reach_their_player_through_a_real_link():
    """The name link is the only navigation on a row: vets open the in-module
    card, prospects PROSPX. The row header is the player cell, so a screen
    reader names every number in the row."""
    body = _body(_render(""))
    assert 'role="button"' not in body
    assert 'href="#player=vet_guy"' in body
    assert 'href="/prospx/#player=efv_kid"' in body and 'href="/prospx/#player=cons_kid"' in body
    assert body.count('<th scope="row"') == 3


def test_rows_carry_compare_and_a_collapsed_detail_toggle():
    body = _body(_render(""))
    assert body.count('class="proj-cmp-btn') == 3 and body.count('aria-pressed="false"') == 3
    assert body.count('class="proj-xp-btn"') == 3 and body.count('aria-expanded="false"') == 3
    assert "aria-controls" not in body, "aria-controls points at a row that does not exist yet"


def test_season_headers_keep_the_full_year_for_assistive_tech_and_the_csv():
    """Phones show 26..30; the '20' is visually hidden, not removed, and the
    CSV header is the full year plus the cell unit.

    The 5y total header carries ONE unit line of its own in WAR mode, and it
    is not a unit: it is the column's ANCHOR, "expected", stated on screen
    rather than only in a tooltip (2026-09-18b). The season headers still
    carry no unit line until the cells swap to a rate."""
    head = _head(_render(""))
    assert '<span class="proj-sr-sm">20</span>26' in head
    assert 'data-export-text="2026 WAR"' in head
    assert 'data-export-text="5y WAR (expected)"' in head
    assert head.count("proj-th-unit") == 1 and ">expected</span>" in head
    head = _head(_render("#cells=wrc"))
    assert 'data-export-text="2026 wRC+"' in head
    # five season units plus the 5y anchor line, which does not move.
    assert head.count("proj-th-unit") == 6 and ">expected</span>" in head


def test_the_five_year_column_carries_one_anchor_for_every_row():
    """THE HOUSE RULE, on the column the owner reads first. Both row
    populations print the EXPECTED path in the 5y cell and in every season
    cell: one anchor, one sort, one ruler per pool. A prospect also has a
    prime-anchored total, and it is never the number in this cell.

    05a25ce1 moved this column from the if-healthy path to the expected value,
    which was right for a veteran (the if-healthy series ran 37.9 percent high
    league-wide). Putting the PROSPECT rows back on their prime anchor here
    would rank a 62-eFV teenager 17th on the served board instead of 113th, so
    the prime total is published beside the column, never inside it."""
    body = _body(_render(""))
    row = [r for r in body.split("<tr ") if 'data-key="efv_kid"' in r][0]
    tot = row.split('class="pc-tot"', 1)[1].split("</td>", 1)[0]
    printed = re.sub(r'\stitle="[^"]*"', "", tot)
    assert ">10.0</span>" in printed, printed   # warTotal, the expected path
    assert "16.0" not in printed, printed       # warTotalPTH is NOT printed here
    assert "proj-ct-sub" not in tot, tot        # and not as a sub-line either
    # The tooltip may name the other anchor -- it must not be the ONLY place
    # the page says so, and the header and the row tag both carry it too.
    assert "Prime 16.0" in tot, tot


def test_a_prospect_row_publishes_its_prime_total_once_and_says_so():
    """The talent number the owner was missing, in the row sub line, labelled
    in TEXT and not only in a tooltip, exactly once per row. A prospect whose
    payload carries no prime series gets no tag and no crash; a veteran never
    gets one, because the veteran warPTH field is a DIFFERENT series (the
    if-healthy path) and reading it here would re-make 05a25ce1's mistake in
    the other direction."""
    body = _body(_render(""))
    rows = {k: r for k, r in
            ((r.split('data-key="', 1)[1].split('"', 1)[0], r)
             for r in body.split("<tr ")[1:])}
    assert rows["efv_kid"].count("prime 16.0") == 1, rows["efv_kid"]
    assert "proj-tag-prospect" in rows["efv_kid"]
    assert "prime " not in rows["cons_kid"]      # no warPTH on the payload row
    assert "prime " not in rows["vet_guy"]       # never a veteran


def test_the_prime_total_is_sortable_and_sorts_no_veteran_up():
    """It is a published value, so a reader can rank the prospect pool by
    talent, and the key survives in a share link. A veteran has no prime path
    on this anchor at all, so he sorts with the missing values rather than
    borrowing a number that means something else."""
    keys = _row_keys(_render("#sort=warPrime"))
    assert keys[0] == "efv_kid", keys
    # Everything with no prime path lands behind it, in the board's own WAR
    # order (the documented tie-break), never interleaved with it.
    assert set(keys[1:]) == {"vet_guy", "cons_kid"}, keys


def test_contract_cell_is_the_year_and_aav_needs_a_live_deal():
    """The CONTROL cell (2026-09-17). For a man whose club controls him exactly
    as long as his contract guarantees him, the cell is his guarantee year, it
    is solid, and it keeps the guarantee word - which belongs to `thru` and is
    never attached to `ctrlThru`. The sub-line under it says which fact it is."""
    body = _body(_render(""))
    vet = body.split('<tr data-key="vet_guy"', 1)[1].split("</tr>", 1)[0]
    assert '<span class="proj-ct proj-ct-signed"' in vet and ">2028</span>" in vet
    assert "$25.0M" in vet
    assert '<span class="proj-ct-sub"' in vet and ">guaranteed</span>" in vet
    assert "guaranteed 2028" in vet                # the sub-line form for narrow widths
    assert "Guaranteed through 2028" in vet        # and the tip names the contract
    ctcell = vet.split('<td class="pc-ct"', 1)[1].split("</td>", 1)[0]
    assert "club control" not in ctcell.lower(), "control words on a contract-only cell"
    # The export column a tooltip cannot carry: the visible year, not the sub.
    assert 'data-export-text="2028"' in vet
    kid = body.split('<tr data-key="efv_kid"', 1)[1].split("</tr>", 1)[0]
    assert "proj-ct-prospect" in kid and ">Prospect<" in kid


def test_prospect_view_shows_grade_eta_and_bust_as_columns():
    """#src=prospect (or #contract=prospect) swaps the contract tail for the
    prospect facts. eFV rounds to NEAREST (50.4 -> 50), consensus FV to
    CEILING (45.2 -> 46)."""
    for h in ("#src=prospect", "#contract=prospect"):
        html = _render(h)
        head = _head(html)
        for key in ("fv", "eta", "warPeak", "pBust"):
            assert f'data-psort="{key}"' in head, (h, key)
        assert 'data-psort="aav"' not in head and 'data-psort="thru"' not in head
        body = _body(html)
        assert ">50</span>" in body and "FV 46" in body and "FV 51" not in html
        assert "30%" in body                       # efv_kid pBust 0.3
        assert 'data-gl="xfv"' in html and 'data-gl="bust_prob"' in html   # eyebrow hooks


def test_total_band_stays_withdrawn():
    """F-01: the summed P10-P90 total band is miscalibrated and never rendered.
    The fixture's warTotalP10Comon/P90Comon (22.0, 23.5, 15.5) are numbers nothing else
    on the board produces."""
    for h in ("", "#src=prospect"):
        board = _board(_render(h))
        for v in ("22.0", "23.5", "15.5"):
            assert v not in board, (h, v)


def test_unknown_sort_key_falls_back_and_dir_round_trips():
    head = _head(_render("#sort=bogus"))
    assert re.search(r'aria-sort="descending"[^>]*>\s*<button[^>]*data-psort="warTotal"', head)
    head = _head(_render("#sort=age&dir=desc"))
    assert re.search(r'aria-sort="descending"[^>]*>\s*<button[^>]*data-psort="age"', head)
    head = _head(_render("#sort=name"))            # natural first direction A-Z
    assert re.search(r'aria-sort="ascending"[^>]*>\s*<button[^>]*data-psort="name"', head)


def test_missing_values_sort_last_in_both_directions():
    """Only vet_guy carries an AAV. Ascending used to open on the dash rows."""
    assert _row_keys(_render("#sort=aav&dir=asc"))[0] == "vet_guy"
    assert _row_keys(_render("#sort=aav"))[0] == "vet_guy"
    assert _row_keys(_render("#sort=name")) == ["cons_kid", "efv_kid", "vet_guy"]


def test_eyebrow_names_the_active_sort():
    """The only on-screen cue when the sorted column has folded at this width."""
    assert "sorted by 5y WAR ▾" in _render("")
    assert "sorted by AAV ▴" in _render("#sort=aav&dir=asc")
    assert "sorted by 2027 FIP" in _render("#cells=fip&sort=y1")


def test_position_strip_reads_the_nightly_mlbam_keyed_file():
    """The strip used to read a June snapshot keyed by name slug that nothing
    refreshed; owner decision 24 (2026-09-11) repointed /dfs/ and /redraft/ off
    it and /projections/ was missed. Neither player page may fetch it again."""
    src = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    assert "mlb_fielding_positions.json" not in src
    assert '"/data/mlb_position_games.json"' in src
    prospx = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "mlb_fielding_positions.json" not in prospx
    assert '"mlb_position_games.json"' in prospx


def _tail_row(row):
    """The same nine-figure deal with the contract tail on: the salary path
    runs to 2039 and the eight seasons after 2031 carry a price."""
    row = _horizon_row(row)
    row.update({"salPath": [[s, 51000000, 51000000, 51000000, "signed", "contract", 0]
                            for s in range(2027, 2040)],
                "salThru": 2039, "ctrlWhy": "contract_only",
                "sur": [47.3, 51.3, 39.6, 58.7, 40.6, -29.2, -35.4, -41.9, -46.7, -50.8, -51.0, -51.0, -51.0],
                "warTail": [1.65, 1.26, 0.84, 0.42, 0.02, 0.0, 0.0, 0.0],
                "surNpv": 8600000, "surTotal": 10600000})
    return row


def test_a_guarantee_priced_past_the_horizon_names_its_whole_span():
    """Owner answer 2026-09-25 (M05-01 step 2): a guarantee through 2039 is
    priced through 2039, the seasons after 2031 on the champion aging curve
    chained from the 2031 WAR (owner answer VAL2-Q1). The
    card and the board label the surplus with the whole span and say which path
    the later seasons price on; nothing calls them unpriced."""
    global DETAIL, BOARD
    base_d, base_b = DETAIL, BOARD
    try:
        bd = json.loads(base_b)
        bd["first_season"] = 2027
        BOARD = json.dumps(bd)
        d = json.loads(base_d)
        d["players"]["vet_guy"]["proj"] = _tail_row(d["players"]["vet_guy"]["proj"])
        DETAIL = json.dumps(d)
        html = _render("#player=vet_guy&ptab=projection")
        assert "Surplus (2027-2039)" in html
        assert "2032-2039 on the champion aging curve" in html
        assert "not priced" not in html and "carry no price" not in html
        foot = html.split("data-proj-contract-tail", 1)[1][:400]
        assert "Surplus prices the whole guarantee, 2027-2039." in foot
        assert ("The 8 guaranteed seasons 2032-2039 price on the champion (Marcel) aging curve "
                "chained from the 2031 WAR") in foot
        bd["vets"][0] = _tail_row(bd["vets"][0])
        BOARD = json.dumps(bd)
        board = _render("")
        assert "over the whole guarantee, 2027-2039" in board
        assert "only, not the whole club control window" not in board
    finally:
        DETAIL, BOARD = base_d, base_b


# ---------------------------------------------------------------------------
# PJ_7 (dark): the component table on the Projection tab and the PA/IP cell.
# proj.comp reaches a card only through the shard once proj_export's
# PROJ_COMPONENTS_LIVE flips; the board says so with components_live. Both
# fixtures below are the block shape proj_export._component_lines writes.
# ---------------------------------------------------------------------------

_N4 = [None, None, None, None]
COMP_HIT = {
    "mlbam": 545361, "frame": "FanGraphs frame", "base": 2026, "twoWay": False, "pit": None,
    "hit": {"pa": [600, 560, 520, 480, 440], "k": [0.181] + _N4, "bb": [0.112] + _N4,
            "iso": [0.201] + _N4, "babip": [0.305] + _N4,
            "woba": [0.371, 0.365, 0.358, 0.351, 0.344], "wrc": [131.4, 127.0, 122.6, 118.2, 113.8],
            "bat": [20.1, 17.2, 14.4, 11.6, 9.0], "bsr": [1.4, None, 0.9, 0.6, 0.4],
            "fld": [3.2, 2.6, 2.0, 1.4, 0.9], "pos": [4.8, 4.5, 4.2, 3.9, 3.6],
            "lg": [1.9, 1.8, 1.6, 1.5, 1.4], "rep": [20.2, 18.8, 17.5, 16.1, 14.8],
            "warComp": [5.1, None, 4.1, 3.5, 2.9],
            "p10": {"pa": [380, 250, 140, -10, -60], "bat": [7.7, 5.5, 3.4, 1.2, -0.5],
                    "bsr": [-1.2, -1.4, -1.6, -1.8, -1.9], "fldPos": [-1.5, -2.1, -2.8, -3.4, -3.9],
                    "lg": [1.1, 0.9, 0.8, 0.6, 0.5], "rep": [12.6, 9.8, 7.4, 5.0, 3.1]},
            "p90": {"pa": [700, 690, 670, 650, 620], "bat": [33.4, 29.8, 26.1, 22.7, 19.6],
                    "bsr": [3.9, 3.6, 3.3, 3.0, 2.7], "fldPos": [13.9, 12.8, 11.6, 10.4, 9.2],
                    "lg": [2.7, 2.6, 2.5, 2.4, 2.3], "rep": [24.0, 23.4, 22.6, 21.8, 20.6]},
            "tier": "hit:hi", "notProjected": []},
    "warComp": [5.1, None, 4.1, 3.5, 2.9],
    "gap": [-2.1, None, -1.5, -1.1, -0.7],
}
COMP_PIT = {
    "mlbam": 669373, "frame": "FanGraphs frame", "base": 2026, "twoWay": False, "hit": None,
    "pit": {"ip": [180.4, 170.2, 160.0, 150.3, 140.6], "k": [0.302] + _N4, "bb": [0.051] + _N4,
            "hr9": [0.92] + _N4, "fip": [2.95, 3.10, 3.25, 3.40, 3.55],
            "warFip": [4.6, 4.1, 3.6, 3.1, 2.6], "warRa9": [4.8, 4.3, 3.8, 3.2, 2.7],
            "gmli": None, "ra9Gap": [1.9, 1.6, 1.4, 1.2, 1.0], "gmliRelief": [None] * 5,
            "p10": {"ip": [110.0, 90.0, 70.0, 50.0, 30.0], "ra9Gap": [-8.0, -7.1, -6.4, -5.8, -5.2],
                    "gmliRelief": [None] * 5},
            "p90": {"ip": [210.0, 205.0, 198.0, 190.0, 180.0], "ra9Gap": [11.2, 10.0, 9.1, 8.2, 7.3],
                    "gmliRelief": [None] * 5},
            "tier": "pit:hi", "notProjected": []},
    "warComp": [4.6, 4.1, 3.6, 3.1, 2.6],
    "gap": [-0.6, -0.3, -0.1, 0.0, 0.2],
}


def _with_comp(players=None, live=True):
    """(DETAIL, BOARD) JSON with proj.comp on the named cards and, when live,
    the board's components_live plus the year-1 pa scalar on its veteran."""
    d = json.loads(DETAIL)
    for key, blk in (players or {}).items():
        d["players"][key]["proj"]["comp"] = blk
    b = json.loads(BOARD)
    if live:
        b["components_live"] = True
        b["vets"][0]["pa"] = 600
    return json.dumps(d), json.dumps(b)


def _render_fixture(hash_, detail, board, all_=False):
    global DETAIL, BOARD
    base_d, base_b = DETAIL, BOARD
    try:
        DETAIL, BOARD = detail, board
        return _render_all(hash_) if all_ else _render(hash_)
    finally:
        DETAIL, BOARD = base_d, base_b


def _comp_rows(sec):
    return re.findall(r'data-proj-comp-row="([a-z0-9-]+)"', sec)


def _comp_row(sec, rid):
    return sec.split(f'data-proj-comp-row="{rid}"', 1)[1].split("</tr>", 1)[0]


def test_component_table_renders_five_seasons_and_the_gap_row():
    d, b = _with_comp({"vet_guy": COMP_HIT})
    html = _render_fixture("#player=vet_guy&ptab=projection", d, b)
    sec = _section(html, "projection-components")
    head = sec.split("<thead>", 1)[1].split("</thead>", 1)[0]
    assert re.findall(r'<th scope="col">([0-9]{4})</th>', head) == ["2026", "2027", "2028", "2029", "2030"]
    assert _comp_rows(sec) == ["pa", "k", "bb", "iso", "babip", "woba", "wrc", "bat", "bsr", "fld",
                               "pos", "lg", "rep", "war-comp", "gap", "war"]
    assert "Components on FanGraphs' WAR frame; the season history on the Hitting tab shows" in sec
    # formats: PA integer, K% one decimal, wOBA / ISO / BABIP three, runs and WAR one
    assert ">600<" in sec and ">18.1%<" in sec and ">.371<" in sec and ">.201<" in sec
    assert ">131<" in sec and ">+20.1<" in sec and ">5.1<" in sec and ">-2.1<" in sec
    # each range rides in the title AND the aria-label; PA floors at zero
    assert 'title="80% range +7.7 to +33.4 runs"' in sec
    assert 'aria-label="2026 Batting runs: +20.1, 80% range +7.7 to +33.4 runs"' in sec
    assert "80% range 0 to 650 PA" in sec and "-10 to" not in sec
    assert "80% range of fielding plus positional runs together" in _comp_row(sec, "pos")
    # the served WAR row keeps the WAR head's own P10 / P90
    war_row = _comp_row(sec, "war")
    assert 'title="80% range 1.2 to 4.8 WAR"' in war_row and ">3.0<" in war_row
    # the gap row is the served WAR minus the component WAR, and no range rides on it
    gap_row = _comp_row(sec, "gap")
    assert ">-2.1<" in gap_row and "80% range" not in gap_row
    # a null component prints "not projected", a run of them once across its seasons
    k_row = _comp_row(sec, "k")
    assert 'colspan="4"' in k_row and k_row.count("not projected") == 2  # text and aria-label
    bsr_row = _comp_row(sec, "bsr")
    assert 'aria-label="2027 Baserunning runs: not projected"' in bsr_row
    # no accuracy claim on the block (owner answer PJ-Q2)
    assert "accura" not in sec.lower()
    # tab order: the WAR path, then the components, then the contract
    panel = html.split('data-mlbp-panel="projection"', 1)[1]
    assert panel.index('data-mlbp-section="projection-fan"') < panel.index(
        'data-mlbp-section="projection-components"') < panel.index('data-mlbp-section="contract-ctrl"')


def test_component_table_pitcher_carries_fip_then_ra9_war():
    d, b = _with_comp({"ace_arm": COMP_PIT})
    sec = _section(_render_fixture("#player=ace_arm&ptab=projection", d, b), "projection-components")
    assert _comp_rows(sec) == ["ip", "k-pit", "bb-pit", "hr9", "fip", "war-fip", "war-ra9",
                               "war-comp", "gap", "war"]
    assert ">180<" in sec and ">30.2%<" in sec and ">0.92<" in sec and ">2.95<" in sec
    assert "RA9 adjustment +1.9 runs; its 80% range -8.0 to +11.2 runs" in _comp_row(sec, "war-ra9")
    assert "the season history on the Pitching tab shows" in sec


def test_component_table_two_way_carries_both_sides():
    two = dict(COMP_HIT, pit=COMP_PIT["pit"], twoWay=True, warComp=[9.7, None], gap=[-0.5, None])
    d, b = _with_comp({"two_way": two})
    sec = _section(_render_fixture("#player=two_way&ptab=projection", d, b), "projection-components")
    rows = _comp_rows(sec)
    assert rows.index("rep") < rows.index("war-hit") < rows.index("ip") < rows.index("war-ra9") < rows.index("war-comp")
    assert "WAR, both sides" in sec
    assert "the Hitting and Pitching tabs" in sec


def test_without_comp_the_projection_tab_is_unchanged():
    base = _render_all("#player=vet_guy&ptab=projection")
    d, b = _with_comp({}, live=False)
    assert _render_fixture("#player=vet_guy&ptab=projection", d, b, all_=True) == base
    for key in ("vet_guy", "ace_arm", "two_way", "backstop"):
        html = _render(f"#player={key}&ptab=projection")
        assert "data-proj-comp" not in html and "projection-components" not in html


def test_pa_ip_chip_only_when_components_live():
    dark = _render_all("")
    assert "PA/IP" not in dark.get("proj-filters", "") and "PA/IP" not in dark.get("proj-rows", "")
    # a #cells=pa link on a dark board falls back to WAR
    fallback = _head(_render("#cells=pa"))
    assert "PA/IP" not in fallback and 'data-export-text="2026 WAR"' in fallback
    d, b = _with_comp({})
    live = _render_fixture("#cells=pa", d, b, all_=True)
    assert 'data-pf="cells:pa"' in live.get("proj-filters", "")
    vet = _body(live["proj-rows"]).split('data-key="vet_guy"', 1)[1].split("</tr>", 1)[0]
    assert "600 PA projected" in vet
    assert "PA/IP" in _head(live["proj-rows"])
    # playing time has no ruler family: no tier key on the board
    assert 'class="tier-key"' not in live["proj-rows"]


# ---------------------------------------------------------------------------
# Team Outlook: the T3 runs columns and the T7 drill-down (TM_7, dark). Each
# block renders only when its payload keys exist; the exporter writes them
# only under TEAM_RUNS_LIVE / TEAM_DRILLDOWN_LIVE, so the served page is
# unchanged until a flip.
# ---------------------------------------------------------------------------

_TEAM_ROW = {"team": "NYY", "war": 40.1, "wins": 90.2, "losses": 71.8, "winsRaw": 88.0,
             "depthWar": 1.0, "n": 20, "byYear": [], "farm": None,
             "top": [{"key": "vet_guy", "name": "Vet Guy", "war": 3.0}]}

_DRILL = {"season": 2026, "frame": "FanGraphs frame",
          "players": [
              {"key": "vet_guy", "name": "Vet Guy", "pos": "SS", "side": "hit", "pa": None, "ip": None,
               "bat": 12.4, "bsr": 1.1, "fld": -2.0, "posRuns": 6.8, "pitRuns": None,
               "warComp": 3.4, "gap": -0.4, "war": 3.0, "warChamp": 3.2},
              {"key": "ace_arm", "name": "Ace Arm", "pos": "SP", "side": "pit", "pa": None, "ip": None,
               "bat": None, "bsr": None, "fld": None, "posRuns": None, "pitRuns": 41.0,
               "warComp": 4.1, "gap": -0.1, "war": 4.0, "warChamp": 3.9},
              {"key": "two_way", "name": "Two Way", "pos": "DH/SP", "side": "two", "pa": None, "ip": None,
               "bat": 30.0, "bsr": None, "fld": 0.0, "posRuns": -14.2, "pitRuns": 24.8,
               "warComp": None, "gap": None, "war": 9.2, "warChamp": 9.0}],
          "foot": {"nPlayers": 3, "warComp": 7.5, "gap": -0.5, "warNoComp": 9.2, "nNoComp": 1,
                   "warServed": 16.2, "champMinusServed": -0.1, "prospects": 1.0, "nProspects": 1,
                   "rosterWar": 17.1, "residual": 0.0}}


def _teams_board(**extra):
    b = json.loads(BOARD)
    rows = [dict(_TEAM_ROW), dict(_TEAM_ROW, team="BOS", war=30.0, wins=80.0, losses=82.0)]
    for k, v in extra.items():
        if k == "frame":
            b["team_outlook_frame"] = v
            continue
        for r in rows:
            r[k] = json.loads(json.dumps(v))
    b["team_outlook"] = rows
    return json.dumps(b)


def _team_head(html):
    return html.split("<thead>", 1)[1].split("</thead>", 1)[0]


def test_team_outlook_blocks_are_absent_without_their_keys():
    for h in ("#view=teams", "#view=teams&club=NYY"):
        html = _render_fixture(h, DETAIL, _teams_board())
        assert "<strong>90-72</strong>" in html
        for needle in ("proj-drill", "data-drill", "proj-tm-run", "proj-runs-frame", ">RA<",
                       ">RS<", "Pythag W", "player by player"):
            assert needle not in html, (h, needle)


def test_team_runs_columns_print_only_the_sides_on_the_rows():
    # TM-C passed RA only: the exporter carries ra and the park factor
    html = _render_fixture("#view=teams", DETAIL, _teams_board(runs={"ra": 690.4, "pf": 1.0}))
    head = _team_head(html)
    assert 'data-team-sort="ra"' in head and ">RA<" in head
    for k in ("rs", "runDiff", "pythW"):
        assert f'data-team-sort="{k}"' not in head, k
    assert html.count('<td class="proj-tm-run proj-cell-mono">690</td>') == 2
    assert "RA: 2026, pre-free-agency frame; component runs on FanGraphs' frame." in html
    # both sides: four columns, a signed differential, and the as-of-signings label
    both = {"rs": 731.0, "ra": 690.4, "runDiff": 40.6, "pythW": 85.3, "pythL": 76.7, "pf": 1.0}
    html2 = _render_fixture("#view=teams", DETAIL, _teams_board(runs=both, frame={"pool": []}))
    head2 = _team_head(html2)
    assert [k for k in ("rs", "ra", "runDiff", "pythW") if f'data-team-sort="{k}"' in head2] ==         ["rs", "ra", "runDiff", "pythW"]
    assert ">+41</td>" in html2 and ">85</td>" in html2
    assert "as-of-signings frame" in html2 and "pre-free-agency frame" not in html2


def test_team_drilldown_opens_one_club_and_reconciles_to_roster_war():
    board = _teams_board(drill=_DRILL)
    closed = _render_fixture("#view=teams", DETAIL, board)
    assert closed.count('class="proj-drill-btn"') == 2 and 'aria-expanded="false"' in closed
    assert "proj-drill-inner" not in closed
    html = _render_fixture("#view=teams&club=NYY", DETAIL, board)
    assert html.count('data-drill-for="NYY"') == 1 and 'data-drill-for="BOS"' not in html
    assert 'data-drill="NYY" aria-expanded="true"' in html
    # the drill row spans exactly the header's columns
    n_head = len(re.findall(r"<th[\s>]", _team_head(html)))
    assert f'data-drill-for="NYY"><td colspan="{n_head}">' in html
    drill = html.split('data-drill-for="NYY"', 1)[1]
    for name in ("Vet Guy", "Ace Arm", "Two Way"):
        assert name in drill, name
    # component runs by side, served WAR in bold, the gap line; a missing
    # component prints "not projected"
    assert "+12.4" in drill and "41.0" in drill and "<strong>9.2</strong>" in drill
    assert "not projected" in drill
    # no exposure head served: the PA / IP column leaves and the note says why
    assert "PA / IP" not in drill and "PA and IP are not projected" in drill
    foot = drill.split("data-proj-drill-foot", 1)[1]
    for label, v in (("Roster WAR", "17.1"), ("Arrived prospects, 1 at their ETA", "1.0"),
                     ("Served WAR, 3 listed players", "16.2")):
        assert re.search(re.escape(label) + r"</th><td>" + re.escape(v) + "<", foot), label
    # the club's Franchise page is one click away
    assert '<a href="/franchise/#team=NYY">franchise page</a>' in drill
    # an exposure head that serves brings the column back
    with_pt = json.loads(json.dumps(_DRILL))
    with_pt["players"][0]["pa"] = 612.0
    html_pt = _render_fixture("#view=teams&club=NYY", DETAIL, _teams_board(drill=with_pt))
    assert "PA / IP" in html_pt and "612 PA" in html_pt
    assert "PA and IP are not projected" not in html_pt
