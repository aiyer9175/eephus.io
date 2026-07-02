# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer smoke test for assets/pal.js (Pitcher Alchemy Lab).

Stubs the DOM + a synchronous fetch so init() renders each section, then asserts
real content (candidate tables, the need-gated SP->RP verdict, the backtest
scorecard, the pitch-add recommendation). Skips when py_mini_racer is absent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "pal.js").read_text(encoding="utf-8")

SAMPLE = """{
 "season":2026,"n_conversions":95,"verdict":"provisional",
 "rp2sp":[{"mlbam":1,"name":"Deep Reliever","team":"NYY","fit":85.2,"n_pitches":4,"ip":50,"k_pct":0.28,
   "bb_pct":0.05,"fb_velo":94,"proj_velo":93,"fb_pct":0.5,"platoon_split":0.05,
   "components":{"arsenal_depth":100,"command":90,"fb_reliance_inv":80,"stuff_quality":70,"platoon_neutrality":88,"survivability":60},
   "flags":[],"arsenal":[{"pitch":"FF","usage":0.3,"whiff":0.15,"est_woba":0.30},{"pitch":"SL","usage":0.25,"whiff":0.30,"est_woba":0.28}],
   "pitch_add":{"add":"Changeup","target":"RHB","reason":"no offspeed pitch","priority":"medium"}}],
 "sp2rp":[{"mlbam":2,"name":"Power Starter","team":"SD","fit":78.0,"relief_upside":85,"starter_era":5.10,"n_pitches":2,
   "best_whiff":0.40,"proj_velo":100,"fb_velo":98,"proj_relief_rem_plus":150,
   "components":{"stuff_upside":80,"putaway":90,"velo_leverage":70,"tto_leakage":75,"conversion_need":82},
   "flags":[{"key":"putaway","label":"late-inning weapon"},{"key":"struggling_sp","label":"struggling as a starter"}]}],
 "history":[{"mlbam":3,"name":"Converted Guy","team":"KC","direction":"RP->SP","year":2023,
   "pre":{"g":60,"gs":0,"ip":65,"k_pct":0.28,"era":3.5},"post":{"g":30,"gs":28,"ip":160,"k_pct":0.24,"era":3.8},
   "held":true,"pre_fit":80.5,"success":true}],
 "pitch_mix_changes":[{"mlbam":3,"name":"Converted Guy","team":"KC","direction":"RP->SP","year":2023,
   "before":[{"pitch":"FF","usage":0.6}],"after":[{"pitch":"FF","usage":0.4},{"pitch":"CH","usage":0.2}]}],
 "pitch_add":[{"mlbam":1,"name":"Deep Reliever","team":"NYY","fit":85.2,"n_pitches":4,
   "arsenal":[{"pitch":"FF","usage":0.3}],"platoon_split":0.05,
   "rec":{"add":"Changeup","target":"RHB","reason":"no offspeed pitch","priority":"medium"}}],
 "reverse_platoon":[{"mlbam":9,"name":"Reverse Guy","team":"TB","role":"RP","p_throws":"R",
   "own_ops":0.720,"opp_ops":0.560,"split":0.160,"reverse_index":0.160,"reverse":true,"extreme":true,
   "weak_hand":"RHB","min_tbf":120}],
 "prospect_watch":[{"name":"Thin Starter Prospect","org":"LAD","position":"SP","fv":50,
   "tools":{"fb":60,"sl":55,"cmd":40},"starter_shape":27.0,"arsenal_depth":2,"role":"SP","lean":"RP","mismatch":true}],
 "n_prospects":1960,
 "backtest":{"n_labeled":44,"spearman_prefit_vs_held":0.223,"relief_k_bump_measured":0.022,
   "converter_median_fit_pool_pctile":72,"disclaimer":"A screen, not a success-probability model."}
}"""


def _prelude(hash_: str) -> str:
    return f"""
    var __html={{}};
    function __el(id){{return new Proxy(function(){{return __el(id);}},{{
      get:function(t,k){{ if(k==='innerHTML')return __html[id]||'';
        if(k==='classList')return {{add:function(){{}},remove:function(){{}},toggle:function(){{}},contains:function(){{return false;}}}};
        if(k==='querySelectorAll')return function(){{return [];}};
        if(k==='getAttribute')return function(){{return null;}};
        if(k==='setAttribute'||k==='addEventListener'||k==='removeEventListener')return function(){{}};
        if(k==='querySelector'||k==='closest')return function(){{return __el(id+'q');}};
        if(k==='value'||k==='textContent')return ''; return __el(id);}},
      set:function(t,k,v){{if(k==='innerHTML')__html[id]=v;return true;}}, apply:function(){{return __el(id);}}}});}}
    function FT(val){{return {{then:function(cb){{var r=cb(val);return (r&&r.then)?r:FT(r);}},catch:function(cb){{return FT(val);}}}};}}
    var SAMPLE={SAMPLE};
    var fetch=function(){{return FT({{ok:true,json:function(){{return FT(SAMPLE);}}}});}};
    var history={{replaceState:function(){{}}}};
    var location={{hash:'{hash_}'}};
    var document={{readyState:'complete',getElementById:function(id){{return __el(id);}},
      querySelector:function(){{return __el('q');}},querySelectorAll:function(){{return [];}},
      createElement:function(){{return __el('c');}},addEventListener:function(){{}},
      body:__el('body'),documentElement:__el('de'),head:__el('head')}};
    var window={{location:location,document:document,history:history,fetch:fetch,
      EEPHUS_GL:{{wire:function(){{}}}},EEPHUS_HUB:{{teamLogo:function(){{return '<img>';}}}},
      addEventListener:function(){{}},setTimeout:function(){{}}}};
    var navigator={{userAgent:'smoke'}};
    """


def _render(hash_: str) -> str:
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_) + JS)
    return ctx.eval("__html['pal-app-root'] || ''")


def test_rp2sp_view():
    html = _render("")
    assert "mlbstats-table" in html and "Deep Reliever" in html
    assert "pal-fit" in html and ">85.2<" in html


def test_sp2rp_need_gated_view():
    html = _render("#sp2rp")
    assert "Power Starter" in html
    assert "struggling as a starter" in html          # the need flag renders
    assert "5.10" in html                             # SP ERA column


def test_history_scorecard_view():
    html = _render("#history")
    assert "pal-scorecard" in html
    assert "0.223" in html and "Converted Guy" in html
    assert "Hit" in html                              # held-role label


def test_pitchadd_view():
    html = _render("#pitchadd")
    assert "Deep Reliever" in html
    assert "ADD Changeup" in html


def test_platoon_radar_view():
    html = _render("#platoon")
    assert "Reverse Guy" in html
    assert "reverse" in html.lower()


def test_prospect_watch_view():
    html = _render("#prospects")
    assert "Thin Starter Prospect" in html
    assert "profiles as a reliever" in html


# ---------------------------------------------------------------------------
# F-02: fetch failure must paint a visible error state (not the misleading
# "being computed" message), with a retry affordance.
# ---------------------------------------------------------------------------

def test_fetch_failure_renders_error_state():
    ctx = MiniRacer()
    err_fetch = ("var fetch=function(){return {then:function(){return this;},"
                 "catch:function(cb){cb(new Error('network down'));return this;}};};")
    ctx.eval(_prelude("") + err_fetch + JS)
    html = ctx.eval("__html['pal-app-root'] || ''")
    assert "Data failed to load" in html
    assert "nightly build is mid-run" in html
    assert "pal-retry" in html               # the retry affordance exists
    assert 'role="alert"' in html


def test_null_payload_still_reads_as_not_exported():
    ctx = MiniRacer()
    ok_null = ("var fetch=function(){return FT({ok:true,"
               "json:function(){return FT(null);}});};")
    ctx.eval(_prelude("") + ok_null + JS)
    html = ctx.eval("__html['pal-app-root'] || ''")
    assert "being computed" in html
    assert "Data failed to load" not in html
