# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX's shared grade helpers print eFV, and a consensus grade only where it is named.

Owner ask 5 (2026-09-30): "Make sure eFV is being used as the only displayed FV source
across PROSPX". The Part 8 lane links_efv_display (B.1, the shared helpers B-S1 to B-S8)
found the chokepoints most surfaces inherit: the gradeBlock and efvBadgeHTML fallbacks
printed a consensus grade as a bare number, fvBadgeTooltip called it "FV" and rounded it
to nearest, the compare cart's eFV badge carried the consensus tooltip, and the Rank-by
toggle swapped every badge on the board to consensus.

Pinned here:
  * EFV_DISPLAY_SWAPS is one constant in storage.py, assigned nowhere else, served as
    flags.efv_display_swaps on the boot payload, and the page reads it only from there;
  * flag off (today): a consensus fallback wears a C mark, a dashed border and the
    tooltip "Consensus FV (no eFV for this player)", and rounds UP; fvBadgeTooltip says
    "Consensus FV" and rounds up;
  * flag on (owner answer Q-E1): the toggle orders only, the printed grade stays eFV with
    a labelled consensus chip beside it, a grade waiting on the eFV file is a neutral
    placeholder or "eFV unavailable", the FV-history tooltip and the ring read eFV.
"""
from __future__ import annotations

import json
import os
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def js_function(src: str, name: str) -> str:
    """The source of a top-level `function name(...) { ... }`, brace-matched."""
    m = re.search(r"^function %s\(" % re.escape(name), src, re.M)
    assert m, f"{name} not found in prospx/index.html"
    i = src.index("{", src.index(")", m.end()))
    depth = 0
    for j in range(i, len(src)):
        c = src[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def js_const(src: str, name: str) -> str:
    m = re.search(r"^const %s = .*?;$" % re.escape(name), src, re.M)
    assert m, f"const {name} not found in prospx/index.html"
    return m.group(0)


_STUBS = r"""
var DATA = {flags: {}};
var state = {gradePrimary: "xfv", sort: "xfv", debutGrade: "xfv"};
let _EFV_LOAD = "ready";
function getEfv(p) { return p ? (p._x || null) : null; }
function efvGradeDisplay(x) { return (x && x.xfv_grade != null) ? Math.round(x.xfv_grade) : null; }
function inProvSection(p) { return false; }
function provBadgeHTML(p) { return "PROV"; }
function fvClass(v) { return "fv-x"; }
function fvBadgeChainClasses(p) { return ""; }
function fvBadgeChainMarks(p) { return ""; }
function escapeHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;"); }
function efvTooltip(x) { return "EFVTIP"; }
var FV_TO_WAR = {};
function playerSurplusMM(p) { return null; }
function fvToWarPeak(v, isPit) { return null; }
var _HIST = {};
function getEfvHistory(p) { return _HIST[p.player_key] || null; }
function rarityFvOf(p) { return p._x ? Math.round(p._x.xfv_grade) : p.fv_close; }
"""

_FUNCS = ["fvCeil", "efvDisplaySwaps", "efvLoadState", "gradeMarkHTML", "gradeDashCSS",
          "efvWaitingBadgeHTML", "consensusChipHTML", "gradeBlock", "_gradePrimary",
          "_debutGradePrimary", "efvBadgeHTML", "efvCompactBadge", "fvBadgeTooltip",
          "_ohlcTooltip", "_ringFv"]


def make_js_ctx():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    ctx = mr.MiniRacer()
    ctx.eval(_STUBS)
    ctx.eval(js_const(src, "CONS_FALLBACK_TIP"))
    ctx.eval(js_const(src, "GRADE_C_MARK"))
    for f in _FUNCS:
        ctx.eval(js_function(src, f))
    return ctx


@pytest.fixture()
def js():
    return make_js_ctx()


def _flag(js, on: bool, load: str = "ready"):
    js.eval("DATA.flags = {efv_display_swaps: %s}; _EFV_LOAD = %s;" % (
        "true" if on else "false", json.dumps(load)))


def _ev(js, expr):
    return json.loads(js.eval("JSON.stringify(%s)" % expr))


# A consensus-only row: no eFV entry, the latest point carries the ceil-snapped label.
_CONS_ROW = '{player_key: "c1", fv_close: 55, points: [{consensus_fv_label: "55"}]}'
# A consensus-only row with an unsnapped close and no points: gradeBlock ceils it.
_RAW_ROW = '{player_key: "c2", fv_close: 54.2}'
_EFV_ROW = ('{player_key: "e1", fv_close: 55, points: [{consensus_fv_label: "55"}], '
            '_x: {xfv_grade: 57.4, consensus_fv: 55}}')


# ---------------------------------------------------------------------------
# 1. The flag: one constant, one payload key, one reader
# ---------------------------------------------------------------------------

def test_the_flag_is_one_constant_in_storage_and_off():
    import storage
    assert isinstance(storage.EFV_DISPLAY_SWAPS, bool)
    # Default off until Q9_15 flips it in its own commit.
    assert storage.EFV_DISPLAY_SWAPS is False


def test_the_flag_is_assigned_nowhere_else():
    pat = re.compile(r"^\s*(?:[\w.]+\.)?EFV_DISPLAY_SWAPS\s*(?::[^=\n]*)?=(?!=)", re.M)
    skip = {".cache", "data", "node_modules", "__pycache__", ".git", "_labs", ".venv", "venv"}
    hits = []
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in skip]
        for fn in fns:
            if not fn.endswith((".py", ".js", ".html")):
                continue
            path = Path(dp) / fn
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "EFV_DISPLAY_SWAPS" not in text:
                continue
            for m in pat.finditer(text):
                hits.append(str(path.relative_to(ROOT)))
    assert hits == ["storage.py"], f"EFV_DISPLAY_SWAPS assigned outside storage.py: {hits}"


def test_the_boot_payload_serves_the_flag():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    assert '"flags": {"efv_display_swaps": bool(EFV_DISPLAY_SWAPS)}' in src


def test_the_page_reads_the_flag_only_from_the_payload():
    src = _src()
    uses = [m.start() for m in re.finditer(r"efv_display_swaps", src)]
    assert uses, "prospx never reads flags.efv_display_swaps"
    for i in uses:
        assert src[i - len("DATA.flags."):i] == "DATA.flags.", (
            "prospx reads efv_display_swaps from somewhere other than DATA.flags: "
            + src[i - 60:i + 30])
    assert "EFV_DISPLAY_SWAPS =" not in src


# ---------------------------------------------------------------------------
# 2. Flag off: the fallbacks are labelled and round up
# ---------------------------------------------------------------------------

def test_gradeblock_fallback_is_labelled_consensus_and_rounds_up(js):
    _flag(js, False)
    gb = _ev(js, "gradeBlock(%s)" % _RAW_ROW)
    assert gb["basis"] == "consensus"
    assert gb["label"] == "55" and gb["value"] == 55          # 54.2 rounds UP
    assert gb["consTip"] == "Consensus FV (no eFV for this player)"
    mark = js.eval("gradeMarkHTML(gradeBlock(%s))" % _RAW_ROW)
    assert ">C</sup>" in mark
    assert js.eval("gradeDashCSS(gradeBlock(%s))" % _RAW_ROW) == "border-style:dashed;"
    eg = _ev(js, "gradeBlock(%s)" % _EFV_ROW)
    assert eg["basis"] == "efv" and eg["label"] == "57"        # eFV rounds to nearest
    assert js.eval("gradeMarkHTML(gradeBlock(%s))" % _EFV_ROW) == ""


def test_efv_badge_consensus_fallback_is_labelled(js):
    _flag(js, False)
    html = js.eval("efvBadgeHTML(%s)" % _CONS_ROW)
    assert 'data-grade-basis="consensus"' in html
    assert "border-style:dashed" in html
    assert ">C</sup>" in html
    assert "Consensus FV (no eFV for this player)" in html
    assert ">55<" in html


def test_efv_badge_leads_with_efv_and_carries_no_mark(js):
    _flag(js, False)
    html = js.eval("efvBadgeHTML(%s)" % _EFV_ROW)
    assert ">57<" in html and "grade-c-mark" not in html and "fv-cons-chip" not in html


def test_the_flag_off_consensus_toggle_marks_every_consensus_badge(js):
    _flag(js, False)
    js.eval('state.gradePrimary = "fv"; state.sort = "fv";')
    html = js.eval("efvBadgeHTML(%s)" % _EFV_ROW)
    js.eval('state.gradePrimary = "xfv"; state.sort = "xfv";')
    assert ">55<" in html and ">C</sup>" in html and 'data-grade-basis="consensus"' in html
    assert "the board is set to lead with consensus; eFV 57" in html


def test_compact_badge_fallback_is_labelled_and_rounds_up(js):
    _flag(js, False)
    html = js.eval('efvCompactBadge({player_key: "c3"}, {fallback: 54.2})')
    assert ">55<" in html and ">C</sup>" in html and "border-style:dashed" in html
    assert "Consensus FV 55 (no eFV for this player)" in html


def test_fv_badge_tooltip_says_consensus_and_rounds_up(js):
    tip = js.eval('fvBadgeTooltip({fv_close: 54.2, fv_close_raw: 54.2})')
    assert tip.startswith("Consensus FV 55"), tip
    assert not re.search(r"(^|\n)FV \d", tip)


def test_ohlc_tooltip_names_consensus_when_off(js):
    _flag(js, False)
    js.eval('_HIST = {h1: [{d: "2025-01-01", x: 40.4}, {d: "2026-01-01", x: 51.6}]};')
    assert js.eval('_ohlcTooltip({player_key: "h1", fv_high: 51, fv_low: 42})') == \
        "Consensus FV history · High 51 · Low 42"


def test_ring_keys_on_consensus_when_off(js):
    _flag(js, False)
    assert js.eval("_ringFv(%s)" % '{fv_close: 49, _x: {xfv_grade: 61.6}}') == 49


def test_the_compare_cart_badge_uses_the_efv_tooltip():
    src = _src()
    body = js_function(src, "makeCompareSideBySide")
    m = re.search(r'<span class="fv-badge \$\{fvClass\(String\(fvLabel\)\)\} size-sm"[^\n]*', body)
    assert m, "compare cart grade badge not found"
    line = m.group(0)
    assert "efvTooltip(gbHead.x)" in line
    assert "gradeMarkHTML(gbHead)" in line


# ---------------------------------------------------------------------------
# 3. Flag on (owner answer Q-E1 and B-S5 to B-S8)
# ---------------------------------------------------------------------------

def test_flag_on_the_toggle_orders_only_and_the_grade_stays_efv(js):
    _flag(js, True)
    js.eval('state.gradePrimary = "fv"; state.sort = "fv";')
    assert js.eval("_gradePrimary()") == "xfv"
    html = js.eval("efvBadgeHTML(%s)" % _EFV_ROW)
    js.eval('state.gradePrimary = "xfv"; state.sort = "xfv";')
    assert ">57<" in html, "the printed grade must stay eFV"
    assert 'class="fv-cons-chip"' in html and ">C 55<" in html
    # a placeholder consensus is not a source grade: no chip
    js.eval('state.sort = "fv";')
    ph = js.eval('efvBadgeHTML({player_key: "e2", fv_close: 35, points: [{consensus_fv_label: "35"}],'
                 ' _x: {xfv_grade: 41.2, consensus_fv: 35, consensus_is_placeholder: true}})')
    js.eval('state.sort = "xfv";')
    assert "fv-cons-chip" not in ph


def test_flag_on_debuted_lead_stays_efv(js):
    _flag(js, True)
    js.eval('state.debutGrade = "fv";')
    assert js.eval("_debutGradePrimary()") == "xfv"
    _flag(js, False)
    assert js.eval("_debutGradePrimary()") == "fv"
    js.eval('state.debutGrade = "xfv";')


def test_flag_on_first_paint_is_a_placeholder_never_bare_consensus(js):
    _flag(js, True, "loading")
    html = js.eval("efvBadgeHTML(%s)" % _CONS_ROW)
    assert 'data-grade-basis="pending"' in html and ">55<" not in html
    assert _ev(js, "gradeBlock(%s).label" % _CONS_ROW) is None
    _flag(js, True, "failed")
    html = js.eval("efvBadgeHTML(%s)" % _CONS_ROW)
    assert "eFV unavailable" in html and ">55<" not in html
    compact = js.eval('efvCompactBadge({player_key: "c3"}, {fallback: 54.2})')
    assert "eFV unavailable" in compact
    # once the file is in, the fallback is the labelled consensus grade again
    _flag(js, True, "ready")
    assert ">C</sup>" in js.eval("efvBadgeHTML(%s)" % _CONS_ROW)


def test_flag_on_ohlc_tooltip_reads_the_efv_series(js):
    _flag(js, True)
    js.eval('_HIST = {h1: [{d: "2025-01-01", x: 40.4}, {d: "2026-01-01", x: 51.6}]};')
    assert js.eval('_ohlcTooltip({player_key: "h1", fv_high: 51, fv_low: 42})') == \
        "eFV history · High 52 · Low 40"
    assert js.eval('_ohlcTooltip({player_key: "nohist", fv_high: 51, fv_low: 42})') == \
        "Consensus FV history · High 51 · Low 42"


def test_flag_on_ring_keys_on_the_efv_rarity_grade(js):
    _flag(js, True)
    assert js.eval("_ringFv(%s)" % '{fv_close: 49, _x: {xfv_grade: 61.6}}') == 62


def test_sparkline_chips_follow_the_flag():
    """makeLineChart reads the eFV series for the H/L chips only behind the flag, and the
    consensus chips it keeps with the flag off are titled as consensus."""
    body = js_function(_src(), "makeLineChart")
    assert "const _swapHL = efvDisplaySwaps();" in body
    assert "<title>eFV high · " in body and "<title>eFV low · " in body
    assert "<title>Consensus FV high · " in body and "<title>Consensus FV low · " in body
    assert "no eFV history" in body
    assert ">Consensus FV</text>" in body
