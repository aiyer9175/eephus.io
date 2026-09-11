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

# Player detail payload (data/mlb_player_detail.json contract). Every banded
# index a test reads sits at 113: that is above the HEM+ 88/112 cut and inside
# the z family's 80/120 neutral zone, so the class says which ruler drew it.
DETAIL = json.dumps({"players": {
    "vet_guy": {
        "key": "vet_guy", "name": "Vet Guy", "pos": "SS", "age": 29.4, "team": "NYY",
        "mlbam": 545361, "isPit": False,
        "proj": {"war": [3.0, 2.8, 2.6, 2.4, 2.2], "warP10": [1.2, 1.1, 1.0, 0.9, 0.8],
                 "warP90": [4.8, 4.6, 4.4, 4.2, 4.0], "warTotal": 13.0, "warTotalP10": 5.0,
                 "warTotalP90": 22.0, "surNpv": 40000000, "thru": 2028, "aav": 25000000},
        "career": [{"y": 2025, "pa": 600, "avg": ".300", "obp": ".380", "slg": ".500",
                    "ops": ".880", "hr": 30, "sb": 10, "bbPct": 11, "kPct": 18, "iso": 0.2,
                    "war": 5.1}],
        "sc": {"season": 2025, "metrics": [
            {"label": "xwOBA", "value": ".390", "pct": 95},
            {"label": "Luck (wOBA-xwOBA)", "value": "+0.031", "pct": 99}]},
        "skills": {
            "hem": {"season": 2026, "hemPlus": 113, "xhemPlus": 108, "luckGap": 5,
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
                    "war": 6.1, "war_bwar": 6.6}],
        "sc": {"season": 2025, "metrics": [{"label": "xwOBA Against", "value": ".260", "pct": 97}]},
        "arsenal": [{"pitch": "4-Seam Fastball", "usage": 35.1, "rv100": -1.2, "whiff": 24.0,
                     "ba": 0.21}],
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
                           "posRuns": 4.8, "defRuns": 19.1}}},
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

FIELDING = json.dumps({"season": 2026, "generated_at": "2026-06-22T21:29:00Z", "players": {
    "vet_guy": {"positions": {"SS": {"games": 120, "games_started": 118, "innings": 1030.3}}}}})


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
    return _render_all(hash_, fail_fetch).get("proj-rows", "")


def _render_all(hash_: str, fail_fetch: bool = False) -> dict:
    """Every element's innerHTML by id. The stub's fetch is synchronous, so each
    async fill has already landed by the time this returns; a fill that patches
    its slot shows up under the slot's own id, not inside proj-rows."""
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_, fail_fetch) + JS)
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
    assert "Projected eWAR" in html               # fan chart section (eWAR epoch 2026-09-03)
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
    assert "as of 2026-06-22" in usage             # the file's own vintage, stamped
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
    """113 is above the HEM+ 88/112 cut and inside the 100 + 10z neutral zone.
    DEM+ and WAR/PA+ must read neutral on the z ruler; HEM+ reads good on its
    own ruler. DEM+ on the HEM+ bands would paint an average glove green."""
    html = _render("#player=vet_guy")
    dem = _tile_classes(html, "dem_plus")
    assert len(dem) == 2, dem                     # hero slot 4 + the Defense tab
    for cls in dem:
        assert "mlbp-scale-z" in cls and "proj-pos" not in cls, cls
    for cls in _tile_classes(html, "war_pa_plus"):
        assert "mlbp-scale-z" in cls and "proj-pos" not in cls, cls
    hem = _tile_classes(html, "hem_plus")
    assert hem and all("mlbp-scale-ratio" in c and "proj-pos" in c for c in hem), hem


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
    """luck_gap is xHEM+ minus HEM+ (hitter_export.py), so +5 means results
    BELOW the contact. The retired hero tooltip said the reverse."""
    idx = _section(_render("#player=vet_guy"), "hitting-index")
    assert "+5 vs HEM+" in idx
    assert "HEM+ minus xHEM+" not in JS


def test_luck_leaves_the_percentile_colour_scale():
    sc = _section(_render("#player=vet_guy"), "hitting-statcast")
    assert "mlbp-luck" in sc and "+0.031" in sc
    # the Luck row is not drawn as a percentile slider
    assert sc.count('class="mlbp-slider"') == 1


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
