# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""M07-03 (final pass 2026-09-25): one venue count and one stability read.

The glossary entry milb_park_factor typed a split-half of 0.735 runs / 0.760 HR,
201 venues and "venue 401 'TBD' is excluded". Those came from
park_factors_export.py, deleted on 2026-08-05 (8fecb2f5) with its 201-venue
sidecar. /parks/ reads the raw lab artifact (202 rows, TBD among them) and its
Method tab computes the split-half live under a different rule (0.64 / 0.66).
A reader following the glossary link from the Method tab met two numbers under
one label. Policy now: the pooled no-venue row stays on the board flagged
"pooled", is counted apart from the venues, stays out of the stability reads,
and the glossary types no stability figure and no venue count.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
PAYLOAD = ROOT / "data" / "milb_park_factors.json"


def _entry(eid: str) -> dict:
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    return next(e for e in g["entries"] if e["id"] == eid)


def _pooled(v: dict) -> bool:
    return not v.get("venue_name") or v.get("venue_name") == "TBD"


def test_glossary_types_no_stability_figure_and_no_venue_count():
    e = _entry("milb_park_factor")
    text = e["definition"] + "\n" + e["methodology"]
    window = next(p for p in e["methodology"].split("\n\n") if p.startswith("Window, not season"))
    # the 0.50 bar is the registration's threshold, not a measurement
    assert not re.search(r"\b0\.\d{2,3}\b", window.replace("0.50 bar", "")), window
    assert "/parks/" in window
    assert not re.search(r"\b\d{3} (minor-league )?venues\b", text)
    assert "is excluded" not in text
    assert "pooled" in e["methodology"]


def test_registry_notes_stop_citing_the_deleted_display_build():
    r = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(m for m in r["models"] if m["model_id"] == "milb_park_factors")
    notes = row["notes"]
    assert "DISPLAY BUILD (park_factors_export.py)" not in notes
    assert "Single-season factors are deliberately absent" not in notes
    assert "201 display venues" not in notes
    assert "is retired" in notes


def _render_method(payload: str) -> str:
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    js = (ROOT / "assets" / "parks.js").read_text(encoding="utf-8")
    prelude = """
    var __html={};
    function __el(id){return new Proxy(function(){return __el(id);},{
      get:function(t,k){ if(k==='innerHTML')return __html[id]||'';
        if(k==='classList')return {add:function(){},remove:function(){},toggle:function(){return false;},contains:function(){return false;}};
        if(k==='querySelectorAll')return function(){return [];};
        if(k==='querySelector')return function(){return null;};
        if(k==='getAttribute')return function(){return null;};
        if(k==='setAttribute'||k==='addEventListener'||k==='removeEventListener')return function(){};
        if(k==='value'||k==='textContent')return ''; return __el(id);},
      set:function(t,k,v){if(k==='innerHTML')__html[id]=v;return true;}, apply:function(){return __el(id);}});}
    function FT(val){return {then:function(cb){var r=cb(val);return (r&&r.then)?r:FT(r);},catch:function(cb){return FT(val);}};}
    var SAMPLE=%s;
    var fetch=function(){return FT({ok:true,json:function(){return FT(SAMPLE);}});};
    var history={replaceState:function(){}};
    var location={hash:'#method'};
    var document={readyState:'complete',getElementById:function(id){return __el(id);},
      querySelector:function(){return null;},querySelectorAll:function(){return [];},
      createElement:function(){return __el('c');},addEventListener:function(){},
      body:__el('body'),documentElement:__el('de'),head:__el('head')};
    var window={location:location,document:document,history:history,fetch:fetch,
      EEPHUS_GL:{wire:function(){}},addEventListener:function(){},setTimeout:function(){}};
    """ % payload
    ctx = MiniRacer()
    ctx.eval(prelude + js)
    return ctx.eval("__html['parks-app-root'] || ''")


def test_method_tab_counts_the_pooled_row_apart_and_keeps_it_out_of_stability():
    if not PAYLOAD.exists():
        pytest.skip("milb_park_factors.json not in this tree")
    d = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    n_pooled = sum(1 for v in d["venues"] if _pooled(v))
    n_named = len(d["venues"]) - n_pooled
    html = _render_method(json.dumps(d))
    assert "What backs it" in html, html[:400]
    want = f"{n_named} venues"
    if n_pooled:
        want += f" plus {n_pooled} pooled row"
    assert want in html
    # the split-half n counts parks only: every named venue with a season in
    # each half, never the pooled bucket
    named = [v for v in d["venues"] if not _pooled(v)]

    def n_half(key):
        n = 0
        for v in named:
            odd = even = False
            for k, e in (v.get("seasons") or {}).items():
                if e.get(key) is None or not e.get("g_home"):
                    continue
                if int(k) % 2:
                    odd = True
                else:
                    even = True
            n += odd and even
        return n

    assert f"on runs ({n_half('run_pf')} venues)" in html
    assert f"on home runs ({n_half('hr_pf')})" in html
