# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer smoke test for assets/mlbstats.js (Bullpen Leaderboards).

Stubs the DOM plus a synchronous fetch so the app's init() actually drives a
render, then asserts each view (Relievers / Team Bullpens / Depth Charts)
produces real content - not just "no crash". Skips when py_mini_racer is
unavailable so it never blocks a machine without it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
# The value ruler is a separate module and every colour cut lives in it, so the
# harness has to evaluate it before the board file, exactly as the page does
# (build_site.py puts its tag in the shared head block right after the nav
# script, and deferred scripts run in document order).
TIERS_JS = (ROOT / "assets" / "eephus-tiers.js").read_text(encoding="utf-8")
JS = TIERS_JS + (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")

# A small, real-shaped sample matching the bullpen_export.py contract.
SAMPLE = """{
 "generated_at":"2026-06-30","season":2026,"as_of":"2026-06-29",
 "coverage":{"games":1200,"expected":2430},"verdict":"provisional",
 "relievers":[
  {"key":"a","name":"Closer Alpha","team":"NYY","rem_plus":138,"rem_plus_3yr":128,"rem_plus_3yr_pct":95,"rem_plus_3yr_tag":"established","riv_plus":132,"qualified":true,"ip":42.1,"g":45,"tbf":170,"k_pct":0.34,"bb_pct":0.06,"k_bb_pct":0.28,"fip":2.40,"swstr_pct":0.16,"era":2.10,"gmli":1.85,"gmli_3yr":1.81,"gmli_3yr_pct":98,"gmli_3yr_tag":"established","wpa":2.6,"wpa_li":1.7,"sd":24,"md":4,"role":"Closer","saves":20},
  {"key":"b","name":"Middle Beta","team":"NYY","rem_plus":96,"rem_plus_3yr":99,"rem_plus_3yr_pct":42,"rem_plus_3yr_tag":"provisional","riv_plus":97,"qualified":true,"ip":38.0,"g":40,"tbf":160,"k_pct":0.22,"bb_pct":0.09,"k_bb_pct":0.13,"fip":4.20,"swstr_pct":0.10,"era":4.00,"gmli":0.95,"gmli_3yr":0.88,"gmli_3yr_pct":31,"gmli_3yr_tag":"provisional","wpa":-0.2,"wpa_li":0.1,"sd":12,"md":11,"role":"Middle"},
  {"key":"c","name":"Prov Gamma","team":"BOS","rem_plus":110,"riv_plus":104,"qualified":false,"ip":12.0,"g":13,"tbf":50,"k_pct":0.28,"bb_pct":0.08,"k_bb_pct":0.20,"fip":3.30,"swstr_pct":0.13,"era":3.10,"gmli":1.20,"wpa":0.4,"wpa_li":0.3,"sd":6,"md":3,"role":"Setup"}
 ],
 "teams":[
  {"team":"NYY","bullpen_plus":118,"leverage_deploy_plus":121,"n_above_avg":5,"n_relievers":8,"high_lev_core_rem":130,"relief_ip":410.0,"team_wpa":5.4,"sd":120,"md":70,
   "depth":[{"role":"Closer","name":"Closer Alpha","rem_plus":138,"gmli":1.85},{"role":"Middle","name":"Middle Beta","rem_plus":96,"gmli":0.95}]},
  {"team":"BOS","bullpen_plus":92,"leverage_deploy_plus":90,"n_above_avg":2,"n_relievers":7,"high_lev_core_rem":104,"relief_ip":395.0,"team_wpa":-1.1,"sd":95,"md":98,"depth":[]}
 ]
}"""


def _prelude(hash_: str) -> str:
    # THE BULLPEN BOARD IS NO LONGER WHAT A BARE URL OPENS. Overall is the
    # landing section since 2026-09-17 and every section is lazy, including
    # that one, so a harness that wants the bullpen root has to name its
    # section - which is what the starter, hitter, leverage and defense
    # preludes below have always done. A hash that already names a section is
    # untouched, so #view=teams still reaches the Team Bullpens view.
    if "section=" not in hash_:
        rest = hash_.lstrip("#")
        hash_ = "#section=bullpen" + ("&" + rest if rest else "")
    return f"""
    var __html={{}};
    function __el(id){{return new Proxy(function(){{return __el(id);}},{{
      get:function(t,k){{ if(k==='innerHTML')return __html[id]||'';
        if(k==='classList')return {{add:function(){{}},remove:function(){{}},toggle:function(){{}},contains:function(){{return false;}}}};
        if(k==='querySelectorAll')return function(){{return [];}};
        if(k==='getAttribute')return function(){{return null;}};
        if(k==='setAttribute'||k==='addEventListener'||k==='removeEventListener'||k==='focus'||k==='setSelectionRange')return function(){{}};
        if(k==='querySelector'||k==='closest')return function(){{return __el(id+'q');}};
        if(k==='value'||k==='textContent')return ''; if(k==='checked')return true; if(k==='selectionStart')return 0;
        return __el(id);}},
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
      EEPHUS_GL:{{wire:function(){{}}}},EEPHUS_HUB:null,addEventListener:function(){{}},setTimeout:function(){{}}}};
    var navigator={{userAgent:'smoke'}};
    """


def _render(hash_: str) -> str:
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_) + JS)
    return ctx.eval("__html['mlbstats-app-root'] || ''")


def test_relievers_view_renders():
    html = _render("")
    assert "mlbstats-table" in html
    assert "Closer Alpha" in html and "Middle Beta" in html
    # REM+ 138 is `great`, not `elite`: the run family (REM+ / SEM+ / RIV+) adds a
    # 140 step ABOVE the locked 120 because the served board runs to REM+ 200, so
    # one ladder could not separate a 200 from a 121 on the board whose whole job
    # is separating relievers. 120 is still a boundary and both steps are bold
    # teal. This is the ONE tier name the value ruler moves for a served value.
    assert "vt-great" in html         # REM+ 138 on the run ladder
    assert "vt-elite" not in html.split(">138<")[0][-120:]
    assert "xREM+" in html            # deserved run-prevention companion column
    assert "Prov Gamma" not in html   # qualified-only filter (default) drops it
    assert ">138<" in html


def test_provisional_shown_when_filter_off_via_data():
    # With qualifiedOnly default on, the provisional arm is hidden; this asserts
    # the row exists in the data path by checking the teams view (no filter).
    html = _render("#view=teams")
    assert "Bullpen+" in html
    assert "NYY" in html and "BOS" in html
    assert ">118<" in html            # NYY Bullpen+


def test_depth_view_renders():
    html = _render("#view=depth")
    assert "bp-depth-card" in html
    assert "Closer Alpha" in html
    assert "bp-slot" in html


# ---------------------------------------------------------------------------
# F-02: fetch failure must paint a visible error state (not a blank page or a
# misleading "being computed" message), with a retry affordance.
# ---------------------------------------------------------------------------

_ERR_FETCH = ("var fetch=function(){return {then:function(){return this;},"
              "catch:function(cb){cb(new Error('network down'));return this;}};};")


def test_fetch_failure_renders_error_state():
    ctx = MiniRacer()
    ctx.eval(_prelude("") + _ERR_FETCH + JS)
    html = ctx.eval("__html['mlbstats-app-root'] || ''")
    assert "Data failed to load" in html
    assert "nightly build is mid-run" in html
    assert "mlbstats-retry" in html          # the retry affordance exists
    assert 'role="alert"' in html


def test_null_payload_still_reads_as_not_exported():
    # ok fetch that yields a null payload = "not exported yet", NOT an error.
    ctx = MiniRacer()
    ok_null = ("var fetch=function(){return FT({ok:true,"
               "json:function(){return FT(null);}});};")
    ctx.eval(_prelude("") + ok_null + JS)
    html = ctx.eval("__html['mlbstats-app-root'] || ''")
    assert "being computed" in html
    assert "Data failed to load" not in html


# ---------------------------------------------------------------------------
# F-08: on-page explainers for the headline metrics, wired to the glossary
# tooltip system (data-gl) plus a deep link into the unified glossary.
# ---------------------------------------------------------------------------

def test_rem_plus_explainer_on_relievers_view():
    html = _render("")
    assert "mlbstats-explainer" in html
    assert 'data-gl="rem_plus"' in html
    assert "/glossary/#g=rem_plus" in html
    assert "100 is an average reliever" in html


def test_bullpen_plus_explainer_on_teams_view():
    html = _render("#view=teams")
    assert "mlbstats-explainer" in html
    assert 'data-gl="bullpen_plus"' in html
    assert "/glossary/#g=bullpen_plus" in html


# ---------------------------------------------------------------------------
# The eWAR build stamp (war_source.ewar_vintage, served since 2026-09-10) and
# the 3-year WAR-rate basis (audit F10-01, closed 2026-09-11: the 3-year
# column now shares the 1-year eWAR series). data/ewar.json is hand-built, so
# this season's eWAR numerator can trail the IP beside it.
# ---------------------------------------------------------------------------

def _render_payload(payload: dict, hash_: str = "") -> str:
    ctx = MiniRacer()
    ctx.eval(_prelude(hash_).replace(f"var SAMPLE={SAMPLE};",
                                     f"var SAMPLE={json.dumps(payload)};") + JS)
    return ctx.eval("__html['mlbstats-app-root'] || ''")


def test_a_stale_ewar_build_is_disclosed_and_a_fresh_one_is_not():
    d = json.loads(SAMPLE)
    d["ewar_vintage"] = {"artifact_generated_at": "2026-09-03T12:35:09", "stale": True,
                         "rebuilds_on_a_schedule": False}
    html = _render_payload(d)
    assert "eWAR built 2026-09-03" in html, "the stale eWAR build is not disclosed"
    d["ewar_vintage"]["stale"] = False
    assert "eWAR built" not in _render_payload(d), "a fresh build must not raise the note"
    d.pop("ewar_vintage")
    assert "eWAR built" not in _render_payload(d), "an absent stamp must not invent one"


def test_the_pitcher_3yr_war_rate_column_shares_the_1yr_basis():
    """F10-01 closed 2026-09-11: the lab re-pointed to the served provider, so
    the typed "bWAR basis ... not on one scale" sentence is false and gone."""
    head = _render("").split("<thead>")[1].split("</thead>")[0]
    th = head.split('data-col="war_ip_plus_3yr"')[0].rsplit("<th ", 1)[1]
    assert "bWAR" not in th and "not on one scale" not in th, th
    assert "same eWAR series" in th, th


# ---------------------------------------------------------------------------
# X-D1 wiring: the gmLI 3yr deployment-context column (gate-validated;
# joined by bullpen_export from data/leverage_consistency_eval.json).
# ---------------------------------------------------------------------------

def test_gmli_3yr_column_renders():
    html = _render("")
    assert "gmLI 3yr" in html                 # header present
    assert "1.81" in html                     # established arm's value
    assert "p98" in html                      # pool percentile, dimmed
    # provisional arm carries the marker with its explanatory title
    assert "0.88" in html and "p31" in html
    assert "Provisional: under 2 seasons or 60 relief entries" in html


def test_gmli_3yr_blank_when_absent():
    # Prov Gamma has no gmli_3yr fields; via teams view its depth row renders
    # without the column exploding. Relievers view: strip row c's absence by
    # asserting no 'undefined' leaks anywhere in the rendered table.
    html = _render("")
    assert "undefined" not in html


# ---------------------------------------------------------------------------
# Wave B1: RIV+ (realized-impact) + REM+ 3yr (stable-skill) columns, and the
# yearly-history season pills on the Relievers view.
# ---------------------------------------------------------------------------

def test_riv_plus_and_rem3yr_columns_render():
    html = _render("")
    assert "RIV+" in html                      # RIV+ header present
    assert "REM+ 3yr" in html                  # REM+ 3yr header present
    assert ">132<" in html                     # Closer Alpha RIV+ value
    assert ">128<" in html or "128" in html    # Closer Alpha REM+ 3yr value
    assert "p95" in html                        # REM+ 3yr percentile, dimmed
    # provisional REM+ 3yr arm carries its explanatory marker
    assert "Provisional: under 2 seasons or 40 IP" in html
    assert "undefined" not in html


def test_riv_plus_glossary_wired():
    html = _render("")
    # the header tooltip + the note both reach the riv_plus glossary entry
    assert 'data-gl="riv_plus"' in html


def test_season_history_pills_render():
    html = _render("")
    assert "mlbstats-seasons" in html          # the season tablist
    assert "Current" in html                    # the live-season pill
    # DATA.season is 2026, so the five prior seasons seed the pills before load
    assert ">2025<" in html and ">2021<" in html
    assert 'aria-selected="true"' in html       # Current is selected by default


# ---------------------------------------------------------------------------
# Wave 2: Starter section Rotation Charts (SEM+ viz + rotation ladders) and
# clickable leaderboard names (mlbam -> merged /projections/ card via links()).
# ---------------------------------------------------------------------------

STARTER_SAMPLE = """{
 "generated_at":"2026-06-30","season":2026,"as_of":"2026-06-29","verdict":"provisional",
 "backtest":{"rho_sem_plus":0.39,"rho_fip":0.26,"rho_era":0.09,"n_pairs":120,"seasons":"2021-2025","disclaimer":"forward-chained OOS"},
 "starters":[
  {"key":"111","name":"Ace One","team":"NYY","mlbam":111,"sem_plus":135,"sem_plus_3yr":130,"qualified":true,"ip":110.0,"gs":18,"ip_per_gs":6.1,"k_pct":0.31,"bb_pct":0.05,"k_bb_pct":0.26,"gb_pct":0.45,"fip":2.90,"era":2.70,"hr9":0.8},
  {"key":"222","name":"Mid Two","team":"NYY","mlbam":222,"sem_plus":98,"sem_plus_3yr":101,"qualified":true,"ip":95.0,"gs":17,"ip_per_gs":5.6,"k_pct":0.22,"bb_pct":0.08,"k_bb_pct":0.14,"gb_pct":0.42,"fip":4.10,"era":4.20,"hr9":1.2},
  {"key":"333","name":"Back Three","team":"BOS","mlbam":333,"sem_plus":88,"sem_plus_3yr":90,"qualified":true,"ip":90.0,"gs":16,"ip_per_gs":5.5,"k_pct":0.19,"bb_pct":0.09,"k_bb_pct":0.10,"gb_pct":0.40,"fip":4.80,"era":4.90,"hr9":1.4},
  {"key":"401","name":"Arm 4","team":"NYY","mlbam":401,"sem_plus":122,"qualified":true,"ip":100.0,"gs":17,"ip_per_gs":5.9,"k_pct":0.27,"bb_pct":0.06,"k_bb_pct":0.21,"gb_pct":0.44,"fip":3.30,"era":3.20,"hr9":0.9},
  {"key":"402","name":"Arm 5","team":"BOS","mlbam":402,"sem_plus":115,"qualified":true,"ip":98.0,"gs":16,"ip_per_gs":6.0,"k_pct":0.25,"bb_pct":0.06,"k_bb_pct":0.19,"gb_pct":0.43,"fip":3.60,"era":3.40,"hr9":1.0},
  {"key":"403","name":"Arm 6","team":"NYY","mlbam":403,"sem_plus":108,"qualified":true,"ip":92.0,"gs":16,"ip_per_gs":5.7,"k_pct":0.24,"bb_pct":0.07,"k_bb_pct":0.17,"gb_pct":0.41,"fip":3.90,"era":3.80,"hr9":1.1},
  {"key":"404","name":"Arm 7","team":"BOS","mlbam":404,"sem_plus":103,"qualified":true,"ip":90.0,"gs":15,"ip_per_gs":6.0,"k_pct":0.23,"bb_pct":0.07,"k_bb_pct":0.16,"gb_pct":0.42,"fip":4.00,"era":3.90,"hr9":1.1},
  {"key":"405","name":"Arm 8","team":"NYY","mlbam":405,"sem_plus":99,"qualified":true,"ip":88.0,"gs":15,"ip_per_gs":5.9,"k_pct":0.22,"bb_pct":0.08,"k_bb_pct":0.14,"gb_pct":0.40,"fip":4.20,"era":4.10,"hr9":1.2},
  {"key":"406","name":"Arm 9","team":"BOS","mlbam":406,"sem_plus":94,"qualified":true,"ip":85.0,"gs":15,"ip_per_gs":5.7,"k_pct":0.21,"bb_pct":0.08,"k_bb_pct":0.13,"gb_pct":0.39,"fip":4.40,"era":4.30,"hr9":1.3},
  {"key":"407","name":"Arm 10","team":"NYY","mlbam":407,"sem_plus":90,"qualified":true,"ip":82.0,"gs":14,"ip_per_gs":5.9,"k_pct":0.20,"bb_pct":0.09,"k_bb_pct":0.11,"gb_pct":0.41,"fip":4.60,"era":4.50,"hr9":1.3},
  {"key":"408","name":"Arm 11","team":"BOS","mlbam":408,"sem_plus":86,"qualified":true,"ip":80.0,"gs":14,"ip_per_gs":5.7,"k_pct":0.19,"bb_pct":0.09,"k_bb_pct":0.10,"gb_pct":0.38,"fip":4.80,"era":4.70,"hr9":1.4},
  {"key":"409","name":"Arm 12","team":"NYY","mlbam":409,"sem_plus":112,"qualified":true,"ip":96.0,"gs":16,"ip_per_gs":6.0,"k_pct":0.26,"bb_pct":0.06,"k_bb_pct":0.20,"gb_pct":0.44,"fip":3.70,"era":3.50,"hr9":1.0}
 ],
 "teams":[
  {"team":"NYY","rotation_plus":118,"front_sem":130,"n_above_avg":3,"n_starters":5,"starter_ip":520.0,"total_gs":86},
  {"team":"BOS","rotation_plus":94,"front_sem":100,"n_above_avg":2,"n_starters":5,"starter_ip":505.0,"total_gs":85}
 ]
}"""


def _starter_prelude(hash_: str) -> str:
    # Override the base prelude's fetch (route by URL to the starter sample) and
    # EEPHUS_HUB (chart proxies + a links() map for clickable names).
    override = f"""
    var STARTER_SAMPLE={STARTER_SAMPLE};
    fetch=function(url){{
      var body = (String(url).indexOf('starter')>=0) ? STARTER_SAMPLE : SAMPLE;
      return FT({{ok:true,json:function(){{return FT(body);}}}});
    }};
    var EEPHUS_HUB={{
      teamLogo:function(){{return '';}},
      histogram:function(){{return '<svg class="hub-hist"></svg>';}},
      scatter:function(){{return '<svg class="hub-scatter"></svg>';}},
      stripHTML:function(){{return '';}},
      links:function(){{return FT({{byMlbam:{{"111":{{"key":"ace_one","mlbam":111,"name":"Ace One"}}}}}});}}
    }};
    window.EEPHUS_HUB=EEPHUS_HUB;
    """
    return _prelude(hash_) + override


def _render_starters(hash_: str) -> str:
    ctx = MiniRacer()
    ctx.eval(_starter_prelude(hash_) + JS)
    return ctx.eval("__html['mlbstats-starters-root'] || ''")


def test_starter_board_renders_via_section_hash():
    html = _render_starters("#section=starters")
    assert "mlbstats-table" in html
    assert "SEM+" in html and "Ace One" in html
    assert "xSEM+" in html and "Luck" in html   # deserved run-prevention companion columns
    # clickable name: mlbam 111 resolves through the links() map
    assert 'class="mlbstats-name-link"' in html
    assert "/projections/#player=ace_one" in html
    # a starter with no links match still renders (plain text, no crash)
    assert "Mid Two" in html and "undefined" not in html


def test_rotation_charts_view_renders():
    html = _render_starters("#section=starters&sview=charts")
    # SVG viz (histogram + scatter) from the stubbed EEPHUS_HUB
    assert "hub-hist" in html
    assert "hub-scatter" in html
    # per-team rotation depth ladders (clone of the bullpen depth cards)
    assert "bp-depth-card" in html
    assert "Rotation+" in html
    assert "SP1" in html and "Ace One" in html
    assert "undefined" not in html


# ---------------------------------------------------------------------------
# Wave 2: Hitter Leaderboards section (HEM+), Team Lineups, Lineup Charts, and
# clickable names -- driven via the #section=hitters deep-link.
# ---------------------------------------------------------------------------

def _hrow(mlbam, name, team, hem, pa, hr=20, sb=5, qualified=True):
    return ('{"key":"%d","name":"%s","team":"%s","mlbam":%d,"hem_plus":%d,"hem_plus_3yr":%d,'
            '"hem_plus_3yr_pct":88,"hem_plus_3yr_tag":"established","xhem_plus":%d,"luck_gap":%.3f,'
            '"xwoba":0.375,"qualified":%s,'
            '"tier":"Above-avg","pa":%d,"ab":%d,"hr":%d,"bb":50,"sb":%d,"woba":0.360,'
            '"woba_raw":0.365,"avg":0.280,"obp":0.360,"slg":0.480,"ops":0.840,"iso":0.200,'
            '"bb_pct":0.09,"k_pct":0.20,"babip":0.300}'
            % (mlbam, name, team, mlbam, hem, hem - 3, hem + 4, 0.015, "true" if qualified else "false",
               pa, pa - 70, hr, sb))

_HIT_ROWS = ",".join(
    [_hrow(111, "Star Bat", "NYY", 145, 640)]
    + [_hrow(500 + i, "Bat %d" % i, "NYY" if i % 2 else "BOS", 130 - i * 3, 600 - i * 20)
       for i in range(13)]
)

HITTER_SAMPLE = ('{"generated_at":"2026-06-30","season":2026,"as_of":"2026-06-29","verdict":"validated",'
                 '"backtest":{"rho_hem_plus":0.4123,"rho_woba":0.4089,"rho_ops":0.411,"rho_avg":0.2348,'
                 '"n_pairs":3372,"seasons":"2012-2024","disclaimer":"forward-chained OOS"},'
                 '"hitters":[' + _HIT_ROWS + '],'
                 '"teams":[{"team":"NYY","offense_plus":112,"heart_hem":135,"n_above_avg":5,"n_hitters":9,'
                 '"team_pa":6000,"lineup":[{"name":"Star Bat","hem_plus":145,"pa":640},'
                 '{"name":"Bat 1","hem_plus":127,"pa":580}]},'
                 '{"team":"BOS","offense_plus":98,"heart_hem":110,"n_above_avg":3,"n_hitters":9,'
                 '"team_pa":5900,"lineup":[{"name":"Bat 2","hem_plus":124,"pa":560}]}]}')


def _hitter_prelude(hash_: str, sample: str | None = None) -> str:
    override = f"""
    var HITTER_SAMPLE={sample or HITTER_SAMPLE};
    fetch=function(url){{
      var body = (String(url).indexOf('hitter')>=0) ? HITTER_SAMPLE : SAMPLE;
      return FT({{ok:true,json:function(){{return FT(body);}}}});
    }};
    var EEPHUS_HUB={{
      teamLogo:function(){{return '';}},
      histogram:function(){{return '<svg class="hub-hist"></svg>';}},
      scatter:function(){{return '<svg class="hub-scatter"></svg>';}},
      stripHTML:function(){{return '';}},
      links:function(){{return FT({{byMlbam:{{"111":{{"key":"star_bat","mlbam":111,"name":"Star Bat"}}}}}});}}
    }};
    window.EEPHUS_HUB=EEPHUS_HUB;
    """
    return _prelude(hash_) + override


def _render_hitters(hash_: str) -> str:
    ctx = MiniRacer()
    ctx.eval(_hitter_prelude(hash_) + JS)
    return ctx.eval("__html['mlbstats-hitters-root'] || ''")


def test_hitter_board_renders_via_section_hash():
    html = _render_hitters("#section=hitters")
    assert "mlbstats-table" in html
    assert "HEM+" in html and "Star Bat" in html
    assert "HEM+ 3yr" in html                     # the validated 3yr companion column
    assert "xHEM+" in html and "Luck" in html     # the validated Savant deserved-offense columns
    assert 'data-gl="hem_plus"' in html          # the HEM+ explainer is wired
    # clickable name: mlbam 111 resolves to the merged card
    assert 'class="mlbstats-name-link"' in html
    assert "/projections/#player=star_bat" in html
    assert "undefined" not in html


def test_hitter_team_lineups_render():
    html = _render_hitters("#section=hitters")
    # switch to the teams tab is event-driven; assert the Team Lineups tab exists
    assert "Team Lineups" in html
    assert "Lineup Charts" in html


def test_lineup_charts_render():
    html = _render_hitters("#section=hitters&hview=charts")
    assert "hub-hist" in html and "hub-scatter" in html     # HEM+ distribution + scatter
    assert "bp-depth-card" in html                          # per-team lineup ladders
    assert "Offense+" in html
    assert "Star Bat" in html and "undefined" not in html


# ---------------------------------------------------------------------------
# Bench-aware, platoon-aware lineup cards (owner ask 2026-09-11). The card
# shows the served per-hand HEM+ on every slot and bench row, the served
# platoon options, and the served regulars_out. The renderer computes none of
# it, so these tests count rendered rows against served rows.
# ---------------------------------------------------------------------------

def _slot(slot, key, name, bats, hem, pa, sv, spa, adv):
    return {"slot": slot, "key": key, "name": name, "bats": bats, "hem_plus": hem,
            "pa": pa, "platoon_adv": adv, "hem_plus_split": sv, "split_pa": spa}


def _lineup_team(team, off, keys, *, bench, opts=None, out=None, applied=True):
    names = {k: ("Star Bat" if k == "111" else "Reg %s" % k) for k in keys}
    bats = {k: ("L" if i % 2 else "R") for i, k in enumerate(keys)}
    vr = [_slot(i + 1, k, names[k], bats[k], 120 - i * 3, 600 - i * 20,
                (125 if bats[k] == "L" else 110) - i * 3, 400, bats[k] == "L")
          for i, k in enumerate(keys)]
    vl = [_slot(i + 1, k, names[k], bats[k], 120 - i * 3, 600 - i * 20,
                (80 if bats[k] == "L" else 118) - i, 150, bats[k] == "R")
          for i, k in enumerate(reversed(keys))]
    t = {"team": team, "offense_plus": off, "heart_hem": 120, "n_above_avg": 5,
         "n_hitters": 14, "team_pa": 6000, "platoon_applied": applied,
         "lineup": [{"key": k, "name": names[k], "hem_plus": 100, "pa": 300} for k in keys],
         "orders": {"vr": vr, "vl": vl},
         "slot_meta": {k: {"mlbam": int(k), "pos": ["LF" if i % 2 else "SS"]}
                       for i, k in enumerate(keys)},
         "bench": bench,
         "platoon_options": opts or {"vl": [], "vr": [], "n_withheld": {"vl": 0, "vr": 0}},
         "regulars_out": out or []}
    if not applied:
        t["order_no_platoon"] = [dict(s, platoon_adv=None) for s in vr]
    return t


_NYY_KEYS = ["111", "501", "502", "503", "504", "505", "506", "507", "508"]
_NYY_BENCH = [
    # holds the edge vs LHP on a real 150-PA line: the marker pair
    {"key": "601", "name": "Plat Bat", "bats": "R", "hem_plus": 110, "pa": 300, "mlbam": 601,
     "pos": ["LF", "1B"], "hem_plus_split": {"L": 131, "R": 100}, "split_pa": {"L": 150, "R": 150}},
    # the sub-floor shape: 107 on 4 PA vs LHP, never a marker, rendered thin
    {"key": "602", "name": "Thin Bat", "bats": "R", "hem_plus": 106, "pa": 11, "mlbam": 602,
     "pos": ["C"], "hem_plus_split": {"L": 107, "R": 98}, "split_pa": {"L": 4, "R": 7}},
    # no vs-LHP line at all: the season fallback
    {"key": "603", "name": "No Lefty Line", "bats": "L", "hem_plus": 95, "pa": 60, "mlbam": 603,
     "pos": ["2B"], "hem_plus_split": {"L": None, "R": 97}, "split_pa": {"L": None, "R": 58}},
]
# 501 bats L and plays LF (odd index), and on vs-LHP he reads 80 - 7 = 73 on 150 PA
_NYY_OPTS = {"vl": [{"starter_key": "501", "bench_key": "601", "pos": "LF",
                     "starter_split": 73, "starter_split_pa": 150, "starter_bats": "L",
                     "bench_split": 131, "bench_split_pa": 150, "bench_bats": "R", "delta": 58}],
             "vr": [], "n_withheld": {"vl": 1, "vr": 0}}
_NYY_OUT = [{"key": "701", "mlbam": 701, "name": "Hurt Regular", "bats": "L", "hem_plus": 118,
             "pa": 420, "status_code": "D10", "status_label": "IL-10"}]
_BOS_KEYS = ["801", "802", "803", "804", "805", "806", "807", "808", "809"]
_BOS_BENCH = [{"key": "901", "name": "Bos Bench", "bats": "S", "hem_plus": 99, "pa": 120,
               "mlbam": 901, "pos": ["CF"], "hem_plus_split": {"L": 101, "R": 98},
               "split_pa": {"L": 110, "R": 130}}]


def _lineup_sample(applied=True):
    d = json.loads(HITTER_SAMPLE)
    d["teams"] = [
        _lineup_team("NYY", 112, _NYY_KEYS, bench=_NYY_BENCH, opts=_NYY_OPTS, out=_NYY_OUT,
                     applied=applied),
        _lineup_team("BOS", 98, _BOS_KEYS, bench=_BOS_BENCH, applied=applied)]
    d["lineup_cards"] = {"constants": {"min_split_pa": 100, "margin": 15, "min_pos_innings": 30.0}}
    return json.dumps(d)


def _render_lineups(sample: str, split: str = "vr", links: str = "") -> str:
    """The Lineup Charts view for one opposing hand. The toggle is event-driven
    and the stub DOM carries no events, so the hand is set at the source."""
    js = JS.replace('var hitterSplit = "vr";', 'var hitterSplit = "%s";' % split, 1)
    assert split == "vr" or js != JS, "the hitterSplit declaration moved"
    ctx = MiniRacer()
    ctx.eval(_hitter_prelude("#section=hitters&hview=charts", sample) + links + js)
    return ctx.eval("__html['mlbstats-hitters-root'] || ''")


def _cards(html: str) -> dict:
    out = {}
    for chunk in html.split('<div class="bp-depth-card">')[1:]:
        team = chunk.split('class="bp-depth-team">', 1)[1].split("<", 1)[0]
        out[team] = chunk
    return out


def _row(card: str, name: str, kind: str) -> str:
    """The one rendered row of `kind` (order | bench | out) naming `name`. Rows
    hold no nested divs, so each row is the text up to the next <div."""
    rows = [c for c in card.split('<div class="bp-slot')[1:]
            if 'data-slot="%s"' % kind in c and name in c]
    assert len(rows) == 1, (name, kind, len(rows))
    return rows[0]


def test_the_bench_renders_the_hand_specific_value_and_the_marker():
    html = _render_lineups(_lineup_sample(), "vl")
    nyy = _cards(html)["NYY"]
    # the bench row leads with its vs-LHP number (131), not the season 110
    row = _row(nyy, "Plat Bat", "bench")
    assert 'data-kind="split"' in row and ">131<" in row
    assert " 150 PA" in row and " 300 PA" not in row   # the vs-LHP sample, not the season
    # the marker renders once, under the starter, with both split PAs on it
    assert nyy.count('data-opt="1"') == 1
    assert 'data-spa="150"' in nyy and 'data-bpa="150"' in nyy
    assert 'data-gl="platoon_option"' in nyy
    assert nyy.count('data-optb="1"') == 1          # the chip on the bench row
    assert 'data-gl="hem_plus_vs_hand"' in html
    assert "undefined" not in html and "NaN" not in html


def test_rendered_rows_equal_served_rows_per_card_and_hand():
    """T2 on the fixture. Mutation: rows dropped, duplicated or sliced."""
    served = {t["team"]: t for t in json.loads(_lineup_sample())["teams"]}
    for split in ("vl", "vr"):
        for team, card in _cards(_render_lineups(_lineup_sample(), split)).items():
            t = served[team]
            assert card.count('data-slot="order"') == 9
            assert card.count('data-slot="bench"') == len(t["bench"])
            assert card.count('data-slot="out"') == len(t["regulars_out"])
            assert card.count('data-opt="1"') == len(t["platoon_options"][split])


def test_a_thin_line_is_dimmed_and_never_marked():
    """T5. The Thin Bat reads 107 on 4 PA vs LHP, above the starter he could
    replace, and the served options leave him out: the page must not add him."""
    nyy = _cards(_render_lineups(_lineup_sample(), "vl"))["NYY"]
    row = _row(nyy, "Thin Bat", "bench")
    assert 'data-kind="thin"' in row and ">107<" in row
    assert "4 PA vs LHP, under 100" in nyy
    assert "data-optb" not in row
    import re
    for spa, bpa in re.findall(r'data-opt="1" data-spa="(\d+)" data-bpa="(\d+)"', nyy):
        assert int(spa) >= 100 and int(bpa) >= 100


def test_a_missing_hand_renders_the_season_fallback_visibly():
    """T6. Mutation: a silent fallback that reads like a split."""
    html = _render_lineups(_lineup_sample(), "vl")
    served_nulls = sum(1 for t in json.loads(_lineup_sample())["teams"]
                       for b in t["bench"] if b["hem_plus_split"]["L"] is None)
    assert html.count('data-kind="fallback"') == served_nulls == 1
    assert "No vs LHP line; season HEM+ shown" in html
    assert ">95<sup>s</sup>" in html


def test_the_out_block_shows_the_status_and_the_bench_sorts_by_the_hand():
    nyy = _cards(_render_lineups(_lineup_sample(), "vl"))["NYY"]
    assert "Hurt Regular" in nyy and ">IL-10<" in nyy
    # vs LHP: the 150-PA line leads, the thin and fallback rows follow
    bench = nyy.split('<div class="bp-bench-head">Bench</div>')[1]
    assert bench.index("Plat Bat") < bench.index("Thin Bat") < bench.index("No Lefty Line")


def test_card_names_link_to_the_player_card_when_mapped():
    """T12. Slot, bench and out names all link when the mlbam maps."""
    links = ("EEPHUS_HUB.links=function(){return FT({byMlbam:{"
             '"111":{"key":"star_bat"},"601":{"key":"plat_bat"},"701":{"key":"hurt_reg"}}});};')
    nyy = _cards(_render_lineups(_lineup_sample(), "vl", links))["NYY"]
    for key in ("star_bat", "plat_bat", "hurt_reg"):
        assert "/projections/#player=" + key in nyy, key
    assert ">Thin Bat<" in nyy or "Thin Bat<span" in nyy      # unmapped: plain text


def test_no_dashes_in_the_rendered_cards():
    """T10: the bench role column used to print &mdash; on every row."""
    for split in ("vl", "vr"):
        html = _render_lineups(_lineup_sample(), split)
        for bad in ("&mdash;", "&ndash;", "\u2014", "\u2013"):
            assert bad not in html, (split, bad)


def test_one_lineup_and_no_hand_column_when_the_split_was_not_applied():
    """T11: platoon_applied=false means no toggle, no hand column, no markers."""
    html = _render_lineups(_lineup_sample(applied=False), "vl")
    assert "data-hittersplit" not in html
    assert "data-kind=" not in html and 'data-opt="1"' not in html
    assert "Handedness split unavailable" in html
    assert html.count('data-slot="order"') == 18
    assert "undefined" not in html


def _hand_means(card: str) -> dict:
    """The header's vs-hand means, unrounded, off the card head only."""
    import re
    head = card.split('<div class="bp-slot', 1)[0]
    return {h: float(v) for h, v in re.findall(r'data-hand-mean="([LR])" data-raw="([^"]+)"', head)}


def _half_up(v: float) -> int:
    import math
    return int(math.floor(v + 0.5))


def test_the_card_header_shows_the_nines_vs_hand_mean_as_the_capture_computes_it():
    """Owner decision 21 (2026-09-11). The header number is the capture's own
    reduction (leaderboard_vintages.off_splits_from_hitter_team): PA-weighted,
    per-hand value first. It does not follow the toggle. Mutation: a flat mean,
    the season number used on both hands, or the two hands swapped."""
    import leaderboard_vintages as lv
    served = {t["team"]: t for t in json.loads(_lineup_sample())["teams"]}
    for split in ("vl", "vr"):
        cards = _cards(_render_lineups(_lineup_sample(), split))
        for team, card in cards.items():
            vl, vr = lv.off_splits_from_hitter_team(served[team])
            got = _hand_means(card)
            assert got == pytest.approx({"L": vl, "R": vr}, abs=0.0011), (team, split)
            assert got["L"] != got["R"], "the fixture's two hands differ; the header must too"
            assert "vs LHP %d<" % _half_up(vl) in card and "vs RHP %d<" % _half_up(vr) in card
            assert 'data-gl="hem_plus_vs_hand"' in card.split('<div class="bp-slot', 1)[0]


def test_the_header_mean_skips_a_hole_and_falls_back_like_the_capture():
    """A slot with no PA is skipped, never a zero; a slot with no per-hand value
    reads its season HEM+. Both are the capture's rules, so the numbers match."""
    import leaderboard_vintages as lv
    d = json.loads(_lineup_sample())
    nyy = d["teams"][0]
    nyy["orders"]["vl"][0]["hem_plus_split"] = None      # season fallback
    nyy["orders"]["vl"][1]["pa"] = None                  # skipped
    nyy["orders"]["vr"][2]["pa"] = 0                     # skipped
    blob = json.dumps(d)
    card = _cards(_render_lineups(blob, "vr"))["NYY"]
    vl, vr = lv.off_splits_from_hitter_team(nyy)
    assert _hand_means(card) == pytest.approx({"L": vl, "R": vr}, abs=0.0011)


def test_no_header_mean_when_the_split_was_not_applied():
    html = _render_lineups(_lineup_sample(applied=False), "vl")
    assert "data-hand-mean" not in html


def test_the_live_board_header_means_equal_the_capture():
    """On the served artifact: every club's header equals off_vs_lhp and
    off_vs_rhp as the vintage capture reduces them. Skips when not built."""
    import leaderboard_vintages as lv
    p = ROOT / "data" / "hitter_leaderboards.json"
    if not p.exists():
        pytest.skip("hitter leaderboards not built")
    blob = p.read_text(encoding="utf-8")
    served = {t["team"]: t for t in json.loads(blob)["teams"]}
    cards = _cards(_render_lineups(blob, "vr"))
    n = 0
    for team, card in cards.items():
        t = served[team]
        if t.get("platoon_applied") is False:
            assert not _hand_means(card), team
            continue
        vl, vr = lv.off_splits_from_hitter_team(t)
        want = {k: v for k, v in (("L", vl), ("R", vr)) if v is not None}
        assert _hand_means(card) == pytest.approx(want, abs=0.0011), team
        n += 1
    assert n or not cards


def test_the_live_board_renders_every_served_row_on_both_hands():
    """T2 on the served artifact. Skips when the board is not built."""
    p = ROOT / "data" / "hitter_leaderboards.json"
    if not p.exists():
        pytest.skip("hitter leaderboards not built")
    blob = p.read_text(encoding="utf-8")
    served = {t["team"]: t for t in json.loads(blob)["teams"]}
    for split in ("vl", "vr"):
        cards = _cards(_render_lineups(blob, split))
        assert len(cards) == len(served)
        for team, card in cards.items():
            t = served[team]
            applied = t.get("platoon_applied") is not False
            order = (t.get("orders") or {}).get(split) if applied else t.get("order_no_platoon")
            if order:
                assert card.count('data-slot="order"') == len(order), team
            assert card.count('data-slot="bench"') == len(t.get("bench") or []), team
            assert card.count('data-slot="out"') == len(t.get("regulars_out") or []), team
            want = len(((t.get("platoon_options") or {}).get(split)) or []) if applied else 0
            assert card.count('data-opt="1"') == want, team
            assert "&mdash;" not in card and "undefined" not in card, team


# ---------------------------------------------------------------------------
# S-1: Leverage Leaderboards section (realized WPA impact) -- Batters (WPA /
# pLI / Clutch / WPA-LI) and Starters (per-start WPA), driven via the
# #section=leverage deep-link, with clickable names + the WPA/pLI explainer.
# ---------------------------------------------------------------------------

LEVERAGE_SAMPLE = ('{"generated_at":"2026-06-30","season":2026,"as_of":"2026-06-29",'
                   '"coverage":{"games":1346,"games_total":1356},'
                   '"batters":['
                   '{"mlbam":111,"name":"Clutch Cody","team":"NYY","pa":600,"wpa":3.4,"pli":1.05,'
                   '"clutch":1.20,"wpa_li":2.9,"qualified":true},'
                   '{"mlbam":222,"name":"Quiet Quinn","team":"BOS","pa":540,"wpa":-0.8,"pli":0.97,'
                   '"clutch":-0.60,"wpa_li":-0.4,"qualified":true},'
                   '{"mlbam":333,"name":"Thin Sample","team":"BOS","pa":120,"wpa":0.5,"pli":1.10,'
                   '"clutch":0.10,"wpa_li":0.4,"qualified":false}],'
                   '"starters":['
                   '{"mlbam":911,"name":"Ace Adams","team":"NYY","starts":18,"wpa":2.6,'
                   '"wpa_per_start":0.144,"wpa_li":1.9,"gs":18,"qualified":true},'
                   '{"mlbam":922,"name":"Mid Miller","team":"BOS","starts":16,"wpa":-0.5,'
                   '"wpa_per_start":-0.031,"wpa_li":-0.2,"gs":16,"qualified":true}]}')


def _leverage_prelude(hash_: str) -> str:
    override = f"""
    var LEVERAGE_SAMPLE={LEVERAGE_SAMPLE};
    fetch=function(url){{
      var body = (String(url).indexOf('leverage')>=0) ? LEVERAGE_SAMPLE : SAMPLE;
      return FT({{ok:true,json:function(){{return FT(body);}}}});
    }};
    var EEPHUS_HUB={{
      teamLogo:function(){{return '';}},
      histogram:function(){{return '<svg class="hub-hist"></svg>';}},
      scatter:function(){{return '<svg class="hub-scatter"></svg>';}},
      stripHTML:function(){{return '';}},
      links:function(){{return FT({{byMlbam:{{"111":{{"key":"clutch_cody","mlbam":111,"name":"Clutch Cody"}}}}}});}}
    }};
    window.EEPHUS_HUB=EEPHUS_HUB;
    """
    return _prelude(hash_) + override


def _render_leverage(hash_: str) -> str:
    ctx = MiniRacer()
    ctx.eval(_leverage_prelude(hash_) + JS)
    return ctx.eval("__html['mlbstats-leverage-root'] || ''")


def test_leverage_batter_board_renders_via_section_hash():
    html = _render_leverage("#section=leverage")
    assert "mlbstats-table" in html
    assert "WPA" in html and "Clutch Cody" in html
    assert "pLI" in html and "Clutch" in html          # leverage-context columns
    assert 'data-gl="wpa"' in html                      # the WPA/pLI/Clutch explainer is wired
    # clickable name: mlbam 111 resolves to the merged card
    assert 'class="mlbstats-name-link"' in html
    assert "/projections/#player=clutch_cody" in html
    # qualified-only default drops the thin-sample bat
    assert "Thin Sample" not in html
    assert "undefined" not in html


def test_leverage_starter_board_renders_via_view_hash():
    html = _render_leverage("#section=leverage&lview=starters")
    assert "mlbstats-table" in html
    assert "WPA/start" in html                           # the starter-only column
    assert "Ace Adams" in html and "Mid Miller" in html
    assert "GS" in html
    assert "undefined" not in html


def test_leverage_board_has_a_years_control():
    # The season pills are one control now (2026-09-17): Current, the windows
    # the lab built for this board, and a from/to whose option list seeds from
    # the live season before the history file loads, so every year the pills
    # reached is still one click away.
    html = _render_leverage("#section=leverage")
    assert "mlbstats-seasons" in html and "mlbstats-range" in html
    assert 'data-mlbrange="leverage:current"' in html
    assert 'data-mlbrangesel="leverage:lo"' in html and 'data-mlbrangesel="leverage:hi"' in html
    assert '<option value="2025"' in html
    assert "undefined" not in html


# A full-pool sample (>=10 qualified batters) so the charts clear their threshold.
_VIZ_BATTERS = [
    {"mlbam": 500 + i, "name": "Bat %02d" % i, "team": "NYY",
     "pa": 400, "wpa": round(3.0 - i * 0.35, 2), "pli": round(1.30 - i * 0.03, 2),
     "clutch": round(0.8 - i * 0.15, 2), "wpa_li": round(2.6 - i * 0.30, 2),
     "qualified": True}
    for i in range(12)
]
LEVERAGE_VIZ_SAMPLE = json.dumps({
    "generated_at": "2026-06-30", "season": 2026, "as_of": "2026-06-29",
    "coverage": {"games": 1346, "games_total": 1356},
    "batters": _VIZ_BATTERS, "starters": [],
})


def _render_leverage_viz(hash_: str) -> str:
    ctx = MiniRacer()
    override = f"""
    var LEVERAGE_SAMPLE={LEVERAGE_VIZ_SAMPLE};
    fetch=function(url){{
      var body=(String(url).indexOf('leverage')>=0)?LEVERAGE_SAMPLE:SAMPLE;
      return FT({{ok:true,json:function(){{return FT(body);}}}});
    }};
    var EEPHUS_HUB={{teamLogo:function(){{return '';}},
      histogram:function(){{return '<svg class="hub-hist"></svg>';}},
      scatter:function(){{return '<svg class="hub-scatter"></svg>';}},
      stripHTML:function(){{return '';}},
      links:function(){{return FT({{byMlbam:{{}}}});}}}};
    window.EEPHUS_HUB=EEPHUS_HUB;
    """
    ctx.eval(_prelude(hash_) + override + JS)
    return ctx.eval("__html['mlbstats-leverage-root'] || ''")


def test_leverage_charts_render_for_a_full_pool():
    # 12 qualified batters clears the viz threshold -> the Charts collapsible with
    # the WPA histogram + the production-vs-leverage scatter.
    html = _render_leverage_viz("#section=leverage")
    assert 'data-collapse="leverage-viz"' in html
    assert 'class="hub-hist"' in html and 'class="hub-scatter"' in html
    assert "undefined" not in html


# ---------------------------------------------------------------------------
# Defense Leaderboards section (DEM+), Team Defense, Defense Charts and the
# season history, driven via the #section=defense deep-link. Row shapes follow
# data/defense_leaderboards.json and data/defense_history.json as served.
# ---------------------------------------------------------------------------

_DEF_POS = ["CF", "SS", "2B", "3B", "RF", "LF", "1B", "CF", "SS", "2B", "3B", "RF"]


def _drow(mlbam, name, team, pos, dem, inn, hem, qualified=True, **extra):
    row = {"key": str(mlbam), "mlbam": mlbam, "name": name, "team": team, "pos": pos,
           "pos_inn": {pos: inn}, "inn": inn, "qualified": qualified,
           "tier": "Average", "dem_plus": dem, "dem_plus_raw": dem + 0.2,
           "dem_plus_pct": 50, "dem_plus_pos_pct": 55, "rel": 0.6,
           "rate_1000": 2.5, "rate_1000_shrunk": 1.4, "fld_runs": 3.1, "fld_total": 3.1,
           "fld_pct": 0.981, "pos_runs": -1.2, "pos_runs_fg": -3.4, "def_runs": 1.9,
           "hem_plus": hem}
    row.update(extra)
    return row


_DEF_ROWS = (
    [_drow(111, "Glove Star", "NYY", "CF", 125, 1100.0, 104,
           pos_inn={"CF": 1000.0, "RF": 100.0}, dem_plus_pct=99, dem_plus_3yr=121,
           dem_plus_3yr_pct=97, dem_plus_3yr_tag="established"),
     _drow(222, "Frame Catcher", "BOS", "C", 113, 800.0, 91,
           fld_runs=2.0, frm_runs=6.4, fld_total=8.4, def_runs=14.0, pos_runs=5.6,
           dem_plus_3yr=109, dem_plus_3yr_pct=80, dem_plus_3yr_tag="provisional"),
     _drow(333, "Thin Glove", "BOS", "SS", 104, 150.0, 97, qualified=False)]
    + [_drow(500 + i, "Glove %02d" % i, "NYY" if i % 2 else "BOS", _DEF_POS[i],
             101 - i * 3, 900.0 - i * 20, 99 - i)
       for i in range(12)]
)
_DEF_ALIGN = [{"pos": p, "key": str(m), "mlbam": m, "name": n, "inn_at_pos": inn, "dem_plus": d}
              for p, m, n, inn, d in (("C", 222, "Frame Catcher", 800.0, 113),
                                      ("CF", 111, "Glove Star", 1000.0, 125),
                                      ("SS", 501, "Glove 01", 880.0, 98))]
_DEF_ALIGN[0]["frm_runs"] = 6.4     # the club framing rollup is on: the slot carries it
DEFENSE_SAMPLE = json.dumps({
    "generated_at": "2026-09-11", "season": 2026, "as_of": "2026-09-11",
    "verdict": "validated",
    "backtest": {"status": "validated", "n_pairs": 1255, "seasons": 4, "rho_dem_plus": 0.46,
                 "rho_raw_rate": 0.45, "rho_fld_pct": 0.01, "rho_innings": 0.09,
                 "disclaimer": "DEM+ is scored against next season's published fielding rate."},
    "multiyear": {"source": "dem_plus_multiyear_eval.json", "available": True,
                  "generated_at": "2026-09-11", "window": [2024, 2025, 2026], "n_stamped": 2},
    "team_rollup_framing": {"included": True, "note": "Team DEM+ includes catchers and their framing."},
    "positional": {"basis": "our_ladder", "available": True, "inn_per_650pa": 1277.7,
                   "dh_excluded": True, "fg_column": "pos_runs_fg"},
    "team_basis": {"basis": "current_roster", "scope": "current", "n_rows": 15,
                   "n_moved_to_current_club": 1, "note": "Team is the current club."},
    "fielders": _DEF_ROWS,
    "teams": [
        {"team": "NYY", "team_dem_plus": 106, "team_dem_plus_raw": 106.2, "n_fielders": 8,
         "n_above_avg": 5, "team_inn": 9800.0, "team_fld_runs": 20.5, "team_fld_total": 26.9,
         "team_frm_runs": 6.4, "team_pos_runs": -4.0, "team_pos_runs_fg": -9.1,
         "rollup_includes_catchers": True,
         "alignment": _DEF_ALIGN, "n_off_roster_dropped": 2},
        {"team": "BOS", "team_dem_plus": 94, "team_dem_plus_raw": 94.1, "n_fielders": 9,
         "n_above_avg": 3, "team_inn": 9700.0, "team_fld_runs": -8.0, "team_fld_total": -8.0,
         "team_frm_runs": None, "team_pos_runs": 2.0, "team_pos_runs_fg": 0.5,
         "rollup_includes_catchers": True,
         "alignment": _DEF_ALIGN[:1], "n_off_roster_dropped": 0},
    ],
})
DEFENSE_HISTORY_SAMPLE = json.dumps({
    "generated_at": "2026-09-11", "seasons": [2024, 2025],
    "team_basis": {"basis": "current_roster", "scope": "history", "n_rows": 2,
                   "n_moved_to_current_club": 1,
                   "note": "These are CLOSED seasons; team is the club today."},
    "history": {"2025": {"season": 2025, "n_qualified": 2, "fielders": [
        {"mlbam": 111, "name": "Past Glove", "team": "NYY", "pos": "CF", "inn": 1200.0,
         "dem_plus": 131, "tier": "Elite", "fld_runs": 15.0, "fld_total": 15.0, "pos_runs": 2.0,
         "def_runs": 17.0, "rate_1000": 12.5, "fld_pct": 0.99, "qualified": True},
        {"mlbam": 222, "name": "Past Catcher", "team": "BOS", "pos": "C", "inn": 900.0,
         "dem_plus": 97, "tier": "Average", "fld_runs": 1.0, "frm_runs": -2.0, "fld_total": -1.0,
         "pos_runs": 6.0, "def_runs": 5.0, "rate_1000": -1.1, "fld_pct": 0.995, "qualified": True},
    ]}},
})


def _defense_prelude(hash_: str, sample: str | None = None) -> str:
    override = f"""
    var DEFENSE_SAMPLE={sample or DEFENSE_SAMPLE};
    var DEFENSE_HISTORY_SAMPLE={DEFENSE_HISTORY_SAMPLE};
    fetch=function(url){{
      var u=String(url);
      var body = (u.indexOf('defense_history')>=0) ? DEFENSE_HISTORY_SAMPLE
               : (u.indexOf('defense')>=0) ? DEFENSE_SAMPLE : SAMPLE;
      return FT({{ok:true,json:function(){{return FT(body);}}}});
    }};
    var EEPHUS_HUB={{
      teamLogo:function(){{return '';}},
      histogram:function(){{return '<svg class="hub-hist"></svg>';}},
      scatter:function(){{return '<svg class="hub-scatter"></svg>';}},
      stripHTML:function(){{return '';}},
      links:function(){{return FT({{byMlbam:{{"111":{{"key":"glove_star","mlbam":111,"name":"Glove Star"}}}}}});}}
    }};
    window.EEPHUS_HUB=EEPHUS_HUB;
    """
    return _prelude(hash_) + override


def _render_defense(hash_: str, sample: str | None = None) -> str:
    ctx = MiniRacer()
    ctx.eval(_defense_prelude(hash_, sample) + JS)
    return ctx.eval("__html['mlbstats-defense-root'] || ''")


def _rollup_off_sample() -> str:
    """The same board as a build with dem_plus.TEAM_ROLLUP_FRAMING off writes it:
    no club framing, no framing on any slot."""
    d = json.loads(DEFENSE_SAMPLE)
    d["team_rollup_framing"] = {"included": False, "note": "catchers roll up separately"}
    for t in d["teams"]:
        t["rollup_includes_catchers"] = False
        t.pop("team_frm_runs", None)
        for s in t["alignment"]:
            s.pop("frm_runs", None)
    return json.dumps(d)


def test_defense_board_renders_via_section_hash():
    html = _render_defense("#section=defense")
    assert "mlbstats-table" in html
    assert "DEM+" in html and "Glove Star" in html and "Frame Catcher" in html
    assert "DEM+ 3yr" in html and "p97" in html          # frozen 3yr column + percentile
    assert 'data-gl="dem_plus"' in html                   # header + explainer reach the glossary
    assert "/glossary/#g=dem_plus" in html
    assert 'data-gl="fielding_runs"' in html and 'data-gl="framing_runs"' in html
    assert 'data-gl="positional_adjustment"' in html
    assert "published" in html                            # the one-line run-column note
    # owner decision 18: Def carries OUR ladder, FanGraphs' positional rides beside it,
    # and the column titles say which is which
    assert "Pos (ours)" in html and "Pos (FG)" in html
    assert 'title="OUR LADDER.' in html and "not in Def" in html
    assert "-3.4" in html                                 # FanGraphs' positional, shown
    # clickable name: mlbam 111 resolves to the merged card
    assert 'class="mlbstats-name-link"' in html
    assert "/projections/#player=glove_star" in html
    assert "Thin Glove" not in html                       # qualified-only default
    assert "+6.4" in html                                 # catcher framing runs, signed
    assert "undefined" not in html


def test_dem_plus_bands_on_the_rem_ruler_not_the_hem_ruler():
    """DEM+ is 100 + 10z (SD exactly 10), so it bands on the z ladder
    (120 / 113 / 107 / 100 / 93). The ratio ladder would call 113 `above` and 125
    merely `elite`-adjacent on a wider spread; the family class says which ruler
    drew the number."""
    html = _render_defense("#section=defense")
    assert 'class="rem-plus vt vt-fam-z vt-great">113<' in html
    assert 'class="rem-plus vt vt-fam-z vt-elite">125<' in html
    assert 'vt-fam-ratio">113<' not in html
    assert 'class="rem-plus vt vt-fam-z vt-great">125<' not in html


def test_defense_team_and_chart_tabs_exist():
    html = _render_defense("#section=defense")
    assert "Team Defense" in html and "Defense Charts" in html
    assert 'data-mlbpos="CF"' in html and 'data-mlbpos="C"' in html   # position chips


def test_team_defense_view_renders():
    html = _render_defense("#section=defense&dview=teams")
    assert "Team DEM+" in html and 'data-gl="team_dem_plus"' in html
    assert ">106<" in html and ">94<" in html
    assert "catchers are included, framing too" in html   # owner decision 17: rollup on
    assert "catchers are excluded" not in html
    assert "+6.4" in html and "-9.1" in html              # club Frm and Pos (FG) columns
    assert "Pos (ours)" in html and "Pos (FG)" in html
    assert "undefined" not in html


def test_team_defense_with_the_rollup_off_says_so():
    html = _render_defense("#section=defense&dview=teams", _rollup_off_sample())
    assert "catchers are excluded" in html
    charts = _render_defense("#section=defense&dview=charts", _rollup_off_sample())
    assert "Frm +6.4" in charts                           # the slot falls back to the board row


def test_the_catcher_slot_reads_its_own_framing_first():
    d = json.loads(DEFENSE_SAMPLE)
    d["teams"][0]["alignment"][0]["frm_runs"] = 7.0       # differs from the board row's 6.4
    html = _render_defense("#section=defense&dview=charts", json.dumps(d))
    assert "Frm +7.0" in html


def test_defense_charts_render():
    html = _render_defense("#section=defense&dview=charts")
    assert 'data-collapse="defense-viz"' in html
    assert "hub-hist" in html and "hub-scatter" in html
    assert "bp-depth-card" in html and "bp-slot" in html
    assert "Team DEM+ 106" in html
    assert "Frm +6.4" in html                             # catcher slot reads his framing
    assert "undefined" not in html


def test_defense_years_control_and_history_board():
    html = _render_defense("#section=defense")
    assert 'data-mlbrange="defense:current"' in html
    assert 'data-mlbrangesel="defense:lo"' in html
    assert '<option value="2025"' in html
    hist = _render_defense("#section=defense&dseason=2025")
    assert "Past Glove" in hist and "Past Catcher" in hist
    assert "2025 season, 2 qualified fielders" in hist
    assert "DEM+ 3yr" not in hist                         # frozen join is live-board only
    assert "CLOSED seasons" in hist                       # the history file's own team note
    assert "undefined" not in hist


def test_defense_sort_deep_link_is_honoured():
    html = _render_defense("#section=defense&dsort=inn.a")
    body = html.split("<tbody>")[1]
    assert body.index("Glove 11") < body.index("Glove Star")


# --------------------------------------------------------------------------
# The Team column means "today", and the page has to say so
# --------------------------------------------------------------------------

def test_the_team_basis_disclosure_is_actually_rendered():
    """THE DEFECT. The exporters have written a full team_basis block since the
    convention was introduced, and NOTHING on this page read it: a grep for
    team_basis in assets/mlbstats.js returned zero.

    So `team` pointed at the club that employs the player TODAY, on the history
    boards as well as the current one, and a reader had no way to learn that
    existed. A past season carries the player's present club.
    """
    js = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    assert "team_basis" in js, (
        "the page still does not read the team_basis block the exporters write")
    assert "function teamBasisNote" in js
    assert "teamBasisNote(DATA)" in js, "the note is defined but never mounted"


def test_the_note_is_derived_from_the_payload_and_not_typed():
    """The payload carries the sentence. A hand-written copy of it would go
    stale the day the basis changes."""
    js = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    i = js.index("function teamBasisNote")
    body = js[i:i + 900]
    assert "tb.note" in body, "the note text is not read from the payload"
    assert "n_moved_to_current_club" in body


def test_the_exporters_still_write_the_block_the_page_now_reads():
    import json
    p = ROOT / "data" / "bullpen_leaderboards.json"
    if not p.exists():
        pytest.skip("bullpen leaderboards not built")
    tb = json.loads(p.read_text(encoding="utf-8")).get("team_basis") or {}
    assert tb.get("note"), "the disclosure block lost its note"
    assert tb.get("basis") in ("current_roster", "stats_earned")
    assert tb.get("n_rows")
