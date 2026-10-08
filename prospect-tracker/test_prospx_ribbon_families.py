# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX "Prospect news" ribbon speaks the MLB News family system (HOME_8).

LANE_HOME 1 H05(b) and H15: the ribbon coloured its chips through its own map
(trade and debut in the violet the homepage uses for free agency) and printed
unicode arrows and a star. Contract pinned here:
  * every ribbon event kind maps to a type code of EEPHUS_HUB.wireType;
  * each chip carries data-fam and data-type from that registry, the 12 px
    sprite pictogram of the type and the hidden family prefix, and no up,
    down, star or right-arrow glyph;
  * the Transactions method pill reads the same registry.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest

from test_wire_type_system import _js_object

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
GLYPHS = ("↑", "↓", "★", "→")
KIND_TO_CODE = {
    "promotion": "promo", "demotion": "demo", "debuted": "debut", "trade": "trade", "il": "il_place",
    "waivers": "claim", "release": "release", "dfa": "dfa", "rule_5": "rule5",
}


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src.replace("\r\n", "\n"), re.S | re.M)
    assert m, name
    return m.group(0)


def _const_source(src: str, name: str) -> str:
    m = re.search(r"^const %s = \{.*?\n\};\n" % re.escape(name), src.replace("\r\n", "\n"), re.S | re.M)
    assert m, name
    return m.group(0)


def test_every_kind_maps_to_a_registry_code():
    src = _src()
    hub = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
    types = _js_object(hub, "wireType")
    body = _const_source(src, "RIBBON_WIRE_CODE")
    got = dict(re.findall(r"(\w+): \"(\w+)\"", body))
    assert got == KIND_TO_CODE
    assert all(code in types for code in got.values())
    fn = _function_source(src, "renderWhatsNew")
    assert "colorMap" not in fn and "neon-violet" not in fn
    acq = _const_source(src, "ACQ_LABELS")
    codes = re.findall(r'wire: "(\w+)"', acq)
    assert codes and all(c in types for c in codes) and "color:" not in acq


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    hub = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")
    import json
    ctx = mr.MiniRacer()
    ctx.eval("""var DATA = {}; var _ROOT = {innerHTML: ''};
      var document = {getElementById: function(){ return _ROOT; },
                      querySelector: function(){ return null; }};
      var window = {EEPHUS_HUB: {wireType: %s, wireFamily: %s}};
      function escapeHtml(s){ return String(s); }
      function efvCompactBadge(){ return ''; }
      function marqueeifyTicker(){}""" % (
        json.dumps(_js_object(hub, "wireType")), json.dumps(_js_object(hub, "wireFamily"))))
    src = _src()
    for name in ("pxIcoHTML", "pxWireType", "renderWhatsNew"):
        ctx.eval(_function_source(src, name))
    ctx.eval(_const_source(src, "RIBBON_WIRE_CODE"))
    return ctx


def test_ribbon_chips_carry_family_and_pictogram(js):
    js.eval("""var d = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      DATA.players = [
        {player_key:'a', player_name:'A', trades:[{trade_date:d, from_org:'BAL', to_org:'WSH'}]},
        {player_key:'b', player_name:'B', transactions:[{date:d, kind:'promotion', to_level:'AAA'},
                                                        {date:d, kind:'dfa'}]},
        {player_key:'c', player_name:'C', transactions:[{date:d, kind:'demotion', to_level:'A'}],
         il_status:{is_on_il:true, since:d, type:'60-day', description:'elbow'}},
        {player_key:'e', player_name:'E', transactions:[{date:d, kind:'waivers'}, {date:d, kind:'release'},
                                                        {date:d, kind:'rule_5'}]}];
      DATA.debuts = [{player_key:'f', player_name:'F', status:'debuted', debut_date:d}];
      renderWhatsNew('x');""")
    html = js.eval("_ROOT.innerHTML")
    chips = re.findall(r'<button class="chip".*?</button>', html, re.S)
    assert len(chips) == 9
    seen = set()
    for chip in chips:
        m = re.search(r'data-fam="(\w+)" data-type="(\w+)"', chip)
        assert m, chip
        seen.add(m.group(2))
        assert re.search(r'<span class="wire-ico"><svg class="ico" width="12" height="12"[^>]*>'
                         r'<use href="/assets/eephus-icons\.svg#i-[\w-]+"', chip), chip
        assert '<span class="visually-hidden">' in chip
        assert not any(g in chip for g in GLYPHS), chip
    assert seen == set(KIND_TO_CODE.values())
    assert "Prospect news" in html
    assert 'data-fam="trd" data-type="trade"' in html and "#i-ev-trade" in html
    assert "traded BAL to WSH" in html and "promoted to AAA" in html and "MLB DEBUT" in html
