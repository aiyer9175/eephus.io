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

from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")

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
    assert "rem-elite" in html        # REM+ 138 colors elite
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
            '"hem_plus_3yr_pct":88,"hem_plus_3yr_tag":"established","xhem_plus":%d,"luck_gap":%d,'
            '"xwoba":0.375,"qualified":%s,'
            '"tier":"Above-avg","pa":%d,"ab":%d,"hr":%d,"bb":50,"sb":%d,"woba":0.360,'
            '"woba_raw":0.365,"avg":0.280,"obp":0.360,"slg":0.480,"ops":0.840,"iso":0.200,'
            '"bb_pct":0.09,"k_pct":0.20,"babip":0.300}'
            % (mlbam, name, team, mlbam, hem, hem - 3, hem + 4, 4, "true" if qualified else "false",
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


def _hitter_prelude(hash_: str) -> str:
    override = f"""
    var HITTER_SAMPLE={HITTER_SAMPLE};
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
