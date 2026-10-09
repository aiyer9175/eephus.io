# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""CollegeSavant boards flag the translation legs their own backtest flags.

Final-pass finding M03-05 (2026-09-24), the part 62745d82 left open. The
"How accurate is this" tables flag a leg below the low-signal line (hitter
BB% and OPS, pitcher K%, which tie the predict-the-Single-A-mean baseline in
college_translation_eval.json), but the Projected Single-A boards and the
Draft Prospects board beside them printed every leg's expected value with no
flag. A flagged leg now carries its flag in the board header and its cells
are muted (data-muted, read in --text-secondary since QREA12; an opacity
dropped them to 3.81:1); the flag is read from CS_TRANSLATION.eval, never
hardcoded.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

CS = Path(__file__).parent / "collegesavant"

EVAL = ('{"hit_k":{"r2":0.17,"n":217},"hit_bb":{"r2":0.02,"n":217},'
        '"hit_ops":{"r2":0.007,"n":217},"pit_k":{"r2":0.033,"n":232},'
        '"pit_bb":{"r2":0.112,"n":232},"box_k":{"r2":0.257,"n":86},'
        '"box_bb":{"r2":0.076,"n":86}}')

HIT = ('[{"hitter_name":"Condon, Charlie","team":"GEO_BUL","year":2024,"k_pct":14.8,"pa":280,'
       '"bb_pct":18.6,"xwoba":0.45,"average_exit_velocity":98.5,'
       '"90th_percentile_exit_velocity":112.0,"max_exit_velocity":118.0,"swing_pct":38,'
       '"chase_pct":21,"whiff_pct":20,"zone_swing_pct":68,"zone_contact_pct":89,'
       '"o_contact_pct":62,"sweet_spot_pct":49,"barrel_pct":17,"hard_hit_pct":69}]')
PIT = ('[{"pitcher_id":"1","pitcher_name":"Arm, Alpha","team":"TEX_LON","year":2024,'
       '"pitch_count":300,"stuff_plus":120,"avg_fastball_velo":94,"avg_ivb":18,'
       '"avg_extension":6.2,"avg_release_height":6.0,"xwoba_against":0.28,'
       '"average_exit_velocity":86,"barrel_pct":5,"hard_hit_pct":35,"k_pct":28,"bb_pct":7,'
       '"chase_pct":30,"z_contact_pct":80,"swinging_strike_pct":13}]')

TRANS = ('{"condon-charlie":{"side":"hit","single_a":{"k_pct":{"exp":23.5,"lo":15.2,"hi":31.9},'
         '"bb_pct":{"exp":14.1,"lo":8.1,"hi":20.0},"ops":{"exp":0.84,"lo":0.63,"hi":1.05}}},'
         '"arm-alpha":{"side":"pit","single_a":{"k_pct":{"exp":25,"lo":18,"hi":32},'
         '"bb_pct":{"exp":9,"lo":4,"hi":14}}}}')

PROSPECTS = ('{"hitters":[{"name":"Charlie Condon","year":2024,"school":"Georgia","pos":"3B",'
             '"fv":55,"proj":{"k_pct":{"exp":21.0},"bb_pct":{"exp":10.5}}}]}')

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
var location={hash:'#/'};
var localStorage={getItem:function(){return null;},setItem:function(){},removeItem:function(){}};
var document={querySelector:function(s){return __el(s==='#app'?'app':s);},querySelectorAll:function(){return [];},getElementById:function(id){return __el(id);},createElement:function(){return __el('t');},addEventListener:function(){},body:__el('b'),documentElement:__el('h'),head:__el('h')};
var window={__DATA__, CS_TRANSLATION:{translations:__T__, eval:__E__, low_signal_r2:0.10},
  CS_DRAFT_PROSPECTS:__P__,
  B1G_TEAMS:{}, B1G_TEAMS_PITCHERS:{}, location:location, localStorage:localStorage, document:document, addEventListener:function(){}, removeEventListener:function(){}, matchMedia:function(){return {matches:false,addEventListener:function(){},addListener:function(){}};}, requestAnimationFrame:function(){}, setTimeout:function(){}, clearTimeout:function(){}, devicePixelRatio:1, innerWidth:1200, scrollTo:function(){}, EEPHUS_GL:null, EEPHUS_HUB:null,
  PITCHER_PITCH_DATA:[], PITCHER_PITCH_DATA_2024:[], PITCHER_PITCH_DATA_2025:[], PITCHER_PITCH_DATA_2026:[], PITCH_SHAPES_2024:{}, PITCH_SHAPES_2025:{},
  HITTER_BIP:{}, HITTER_BIP_2024:{}, HITTER_BIP_2025:{}};
var console={log:function(){},warn:function(){},error:function(){}};
var navigator={userAgent:'verify'};
"""


def _render(app: str, data: str, route: str) -> str:
    ctx = MiniRacer()
    ctx.eval(CAP.replace("__DATA__", data).replace("__T__", TRANS)
             .replace("__E__", EVAL).replace("__P__", PROSPECTS))
    ctx.eval((CS / "team_names.js").read_text(encoding="utf-8"))
    ctx.eval((CS / app).read_text(encoding="utf-8"))
    ctx.eval(f"location.hash='{route}';window.location.hash=location.hash;render();")
    return ctx.eval("__html['app']||''")


def _board_head(html: str, marker: str) -> str:
    i = html.index(marker)
    return html[i:html.index("</thead>", i)]


def test_hitter_projection_board_flags_bb_and_ops():
    html = _render("app.js", "HITTER_DATA:" + HIT, "#/projections")
    head = _board_head(html, "Projected Single-A board")
    assert re.search(r"Proj A K%</th>", head), head
    assert re.search(r"Proj A BB% <span class=\"trans-flag\">not predictive</span>", head), head
    assert re.search(r"Proj A OPS <span class=\"trans-flag\">not predictive</span>", head), head
    assert html.count("data-muted>") >= 2
    assert "opacity" not in html


def test_pitcher_projection_board_flags_k_not_bb():
    html = _render("pitcher_app.js", "PITCHER_DATA:" + PIT, "#/projections")
    head = _board_head(html, "Projected Single-A board")
    assert 'Proj A K% <span class="trans-flag">low signal</span>' in head, head
    assert "Proj A BB%</th>" in head, head


def test_draft_prospects_board_flags_box_bb():
    html = _render("app.js", "HITTER_DATA:" + HIT, "#/prospects")
    assert 'Proj A BB% <span class="trans-flag">low signal</span>' in html
    assert re.search(r"Proj A K%(?! <span)", html)
