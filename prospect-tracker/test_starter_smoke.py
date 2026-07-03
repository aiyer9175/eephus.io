# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""py_mini_racer smoke test for the /mlbstats/ Starter Leaderboards section
(assets/mlbstats.js, Wave B2). Stubs a DOM concrete enough to (1) run the app
init, (2) fire a click on the Starter Leaderboards section tab, and (3) read the
HTML rendered into #mlbstats-starters-root, so it asserts a real SEM+ board, not
just "no crash". Fetch is routed by URL to small real-shaped samples. Skips when
py_mini_racer is unavailable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")

STARTERS = """{
 "generated_at":"2026-07-03","season":2026,"verdict":"validated",
 "backtest":{"status":"validated","n_pairs":702,"seasons":7,"rho_sem_plus":0.3923,"rho_fip":0.358,"rho_era":0.2612,"disclaimer":"SEM+ predicts next-year run prevention out of sample."},
 "pool":{"n":175,"pool_era":4.17,"mean_fip":4.15,"n_qualified":140,"n_provisional":70},
 "starters":[
  {"key":"m","name":"Ace Misi","team":"MIL","sem_plus":163,"sem_plus_3yr":143,"sem_plus_3yr_pct":98,"sem_plus_3yr_tag":"established","qualified":true,"ip":104.0,"g":17,"gs":17,"tbf":420,"cg":0,"k_pct":0.33,"bb_pct":0.08,"k_bb_pct":0.25,"gb_pct":0.45,"ip_per_gs":6.12,"fip":2.54,"era":1.47,"hr9":0.6,"role":"Ace"},
  {"key":"b","name":"Back Ender","team":"MIL","sem_plus":92,"sem_plus_3yr":95,"sem_plus_3yr_pct":38,"sem_plus_3yr_tag":"provisional","qualified":true,"ip":88.0,"g":16,"gs":16,"tbf":390,"cg":0,"k_pct":0.19,"bb_pct":0.09,"k_bb_pct":0.10,"gb_pct":0.41,"ip_per_gs":5.5,"fip":4.6,"era":4.8,"hr9":1.4,"role":"Back-end"},
  {"key":"p","name":"Prov Arm","team":"BOS","sem_plus":108,"qualified":false,"ip":22.0,"g":4,"gs":4,"tbf":95,"cg":0,"k_pct":0.26,"bb_pct":0.07,"k_bb_pct":0.19,"gb_pct":0.47,"ip_per_gs":5.5,"fip":3.4,"era":3.1,"hr9":0.9,"role":"Mid-rotation"}
 ],
 "teams":[
  {"team":"MIL","rotation_plus":123,"front_sem":140,"n_above_avg":3,"n_starters":5,"starter_ip":410.0,"total_gs":80,
   "rotation":[{"role":"Ace","name":"Ace Misi","sem_plus":163,"ip":104.0,"gs":17}]},
  {"team":"BOS","rotation_plus":96,"front_sem":108,"n_above_avg":2,"n_starters":5,"starter_ip":395.0,"total_gs":78,"rotation":[]}
 ]
}"""

HISTORY = """{
 "generated_at":"2026-07-03","seasons":[2024,2025],
 "history":{
  "2024":{"season":2024,"n_qualified":2,"starters":[
    {"mlbam":1,"name":"Past Ace","team":"NYY","sem_plus":150,"role":"Ace","ip":190.0,"g":31,"gs":31,"tbf":760,"cg":1,"era":2.6,"fip":2.9,"k_pct":0.30,"bb_pct":0.06,"k_bb_pct":0.24,"gb_pct":0.46,"ip_per_gs":6.1,"hr9":0.8,"qualified":true},
    {"mlbam":2,"name":"Past Mid","team":"NYY","sem_plus":101,"role":"Mid-rotation","ip":170.0,"g":30,"gs":30,"tbf":720,"cg":0,"era":4.0,"fip":4.1,"k_pct":0.22,"bb_pct":0.08,"k_bb_pct":0.14,"gb_pct":0.43,"ip_per_gs":5.7,"hr9":1.1,"qualified":true}
  ]}
 }
}"""

BULLPEN = """{
 "generated_at":"2026-07-03","season":2026,"as_of":"2026-07-03",
 "coverage":{"games":1200,"expected":2430},"verdict":"validated",
 "relievers":[{"key":"a","name":"Closer A","team":"NYY","rem_plus":138,"riv_plus":130,"qualified":true,"ip":42.1,"g":45,"tbf":170,"k_pct":0.34,"bb_pct":0.06,"k_bb_pct":0.28,"fip":2.4,"swstr_pct":0.16,"era":2.1,"gmli":1.85,"wpa":2.6,"wpa_li":1.7,"sd":24,"md":4,"role":"Closer","saves":20}],
 "teams":[]
}"""


def _prelude() -> str:
    # A concrete-enough DOM: elements are objects with innerHTML + a listener
    # registry; querySelectorAll('[data-mlbsection]') yields the two real section
    # tabs so a click can drive showSection(). fetch routes by URL.
    return """
    var STARTERS=%s, HISTORY=%s, BULLPEN=%s;
    function FT(v){return {then:function(cb){var r=cb(v);return (r&&r.then)?r:FT(r);},catch:function(){return FT(v);}};}
    var REG={};
    function mkEl(id, attrs){
      return {id:id, innerHTML:"", _l:{}, _a:attrs||{},
        classList:{add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}},
        getAttribute:function(k){return this._a[k]!=null?this._a[k]:null;},
        setAttribute:function(k,v){this._a[k]=v;}, removeAttribute:function(k){delete this._a[k];},
        addEventListener:function(t,cb){(this._l[t]=this._l[t]||[]).push(cb);},
        removeEventListener:function(){}, focus:function(){}, setSelectionRange:function(){},
        querySelector:function(){return mkEl('q');},
        querySelectorAll:function(sel){return findAll(sel);},
        closest:function(){return mkEl('q');}, fire:function(t){(this._l[t]||[]).forEach(function(f){f({});});}};
    }
    function el(id){ if(!REG[id]) REG[id]=mkEl(id, {}); return REG[id]; }
    var SEC_BP=mkEl('secbp',{'data-mlbsection':'bullpen'});
    var SEC_ST=mkEl('secst',{'data-mlbsection':'starters'});
    function findAll(sel){
      if(sel && sel.indexOf('data-mlbsection')>=0) return [SEC_BP, SEC_ST];
      return [];
    }
    var EMPTY_HIST={seasons:[],history:{}};
    var fetch=function(url){
      var body = (url.indexOf('starter_history')>=0)?HISTORY
               : (url.indexOf('starter_leaderboards')>=0)?STARTERS
               : (url.indexOf('bullpen_history')>=0)?EMPTY_HIST
               : BULLPEN;
      return FT({ok:true,json:function(){return FT(body);}});
    };
    var history={replaceState:function(){}};
    var location={hash:''};
    var document={readyState:'complete',
      getElementById:function(id){return el(id);},
      querySelector:function(){return mkEl('q');},
      querySelectorAll:function(sel){return findAll(sel);},
      createElement:function(){return mkEl('c');},addEventListener:function(){},
      body:el('body'),documentElement:el('de'),head:el('head')};
    var window={location:location,document:document,history:history,fetch:fetch,
      EEPHUS_GL:{wire:function(){}},EEPHUS_HUB:null,addEventListener:function(){},setTimeout:function(f){f();}};
    var navigator={userAgent:'smoke'};
    var localStorage={getItem:function(){return null;},setItem:function(){}};
    """ % (STARTERS, HISTORY, BULLPEN)


def _run() -> dict:
    ctx = MiniRacer()
    ctx.eval(_prelude() + JS)
    # fire a click on the Starter Leaderboards section tab, then read the root
    ctx.eval("SEC_ST.fire('click');")
    return {
        "starters_root": ctx.eval("(REG['mlbstats-starters-root']||{}).innerHTML || ''"),
        "bullpen_root": ctx.eval("(REG['mlbstats-app-root']||{}).innerHTML || ''"),
    }


def test_starters_section_renders_sem_board():
    out = _run()
    html = out["starters_root"]
    assert "mlbstats-table" in html, html[:400]
    assert "SEM+" in html                 # header
    assert "SEM+ 3yr" in html             # 3yr companion column
    assert "Ace Misi" in html             # top starter row
    assert ">163<" in html                # SEM+ value renders
    assert "undefined" not in html


def test_starters_section_has_pills_and_explainer():
    html = _run()["starters_root"]
    assert "mlbstats-seasons" in html          # yearly history pills
    assert 'data-gl="sem_plus"' in html        # explainer wired to glossary
    assert "/glossary/#g=sem_plus" in html     # deep link
    assert "0.3923" in html                     # accountability scorecard rho


def test_bullpen_section_unaffected():
    # the bullpen board still renders into its own root after the starters init
    html = _run()["bullpen_root"]
    assert "mlbstats-table" in html
    assert "Closer A" in html
    assert "undefined" not in html
