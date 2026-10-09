# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX-derived grades on pages outside PROSPX print eFV, and a consensus grade only
where it is named.

Owner ask 5 (2026-09-30) and owner answer Q-E4 ("Yes, everywhere": every page prints eFV
rounded to nearest and labels any consensus grade; the Team Outlook top-prospect value
changes after step Z). The Part 8 lane links_efv_display (Part B, PROSPX-derived FV
outside PROSPX) and wiring_ideas 6.2 list the spots; plan 8.D rows 9 and 10.

Pinned here, one block per surface:
  * home Top Movers and the spotlight cards: the grade-history line names its basis
    (consensus until storage.EFV_DISPLAY_SWAPS flips, then the eFV series where one
    exists); a consensus-basis move reads "Consensus FV", never a bare "FV"; the pill
    for a player with no eFV is named consensus and rounds up;
  * the wire: a consensus-basis grade move reads "+N Consensus FV";
  * /pal/ Prospect Watch (W0 item G06): eFV first, to nearest, then "Consensus FV",
    rounded up;
  * /projections/ Team Outlook: the top prospect's grade names its basis; the exporter
    serves the eFV grade (nearest) only with the flag on; the prospect fallback tag
    says "Consensus FV";
  * Trade Machine: the board column is eFV, its consensus fallback carries a C mark
    and rounds up; the sub-lines say "Consensus FV"; the GRPO panel names its
    consensus grades;
  * Call-up Watch: the consensus fallback under the eFV header carries a C mark;
  * the MLB player page origin line prints eFV at debut and no consensus arc (wiring
    W06 already landed it; test_graduate_bridge pins the line).
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"


def _asset(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    """The source of `function name(...) { ... }` at any indent, brace-matched."""
    m = re.search(r"^\s*function %s\(" % re.escape(name), src, re.M)
    assert m, f"{name} not found"
    i = src.index("{", src.index(")", m.end()))
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _ctx():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    return mr.MiniRacer()


def _ev(ctx, expr):
    return json.loads(ctx.eval("JSON.stringify(%s)" % expr))


# ---------------------------------------------------------------------------
# Home Top Movers, spotlight cards and the wire (build_site.py)
# ---------------------------------------------------------------------------

def test_mover_unit_names_a_consensus_step():
    import build_site as B
    assert B._mover_unit({"stock": {"basis": "xfv"}}) == "eFV"
    assert B._mover_unit({"stock": {"basis": "same_source"}}) == "Consensus FV"
    assert B._mover_unit({}) == "Consensus FV"


def test_pill_without_efv_is_named_consensus_and_rounds_up():
    import build_site as B
    p = {"player_key": "zz_nobody_q9_14", "fv_close": 45.2}
    pill = B._fv_pill(p)
    assert '<span class="visually-hidden">Consensus FV </span>' in pill
    assert 'data-grade-basis="consensus"' in pill and "fv-prod" in pill
    assert 'title="Consensus FV 46: no eFV for this player"' in pill
    assert ">46</span>" in pill                      # ceil(45.2), never 45


def test_pill_with_efv_rounds_to_nearest(monkeypatch):
    import build_site as B
    monkeypatch.setitem(B._EFV_GRADES, "zz_efv_q9_14", 54.4)
    pill = B._fv_pill({"player_key": "zz_efv_q9_14", "fv_close": 51.1})
    assert '<span class="visually-hidden">eFV </span>' in pill
    assert ">54</span>" in pill and "Consensus" not in pill


_PTS = [{"consensus_fv_raw": v} for v in (45, 45, 50, 50)]


def test_mover_spark_flag_off_draws_the_named_consensus_line(monkeypatch):
    import build_site as B
    import storage
    monkeypatch.setattr(storage, "EFV_DISPLAY_SWAPS", False)
    monkeypatch.setattr(B, "_EFV_SERIES_CACHE", {"k1": [{"x": 50.0}, {"x": 55.0}]})
    svg, basis = B._mover_spark({"player_key": "k1", "points": _PTS}, "var(--accent-green)", 56, 20)
    assert basis == "consensus"
    assert 'data-grade-basis="consensus"><title>Consensus FV history</title>' in svg
    # the same pixels as the plain consensus line, plus the name
    plain = B._fv_sparkline(_PTS, "var(--accent-green)", w=56, h=20)
    assert svg.replace(' data-grade-basis="consensus"><title>Consensus FV history</title>', ">") == plain


def test_mover_spark_flag_on_draws_the_efv_series_where_one_exists(monkeypatch):
    import build_site as B
    import storage
    monkeypatch.setattr(storage, "EFV_DISPLAY_SWAPS", True)
    monkeypatch.setattr(B, "_EFV_SERIES_CACHE", {"k1": [{"x": 50.0}, {"x": 61.5}]})
    svg, basis = B._mover_spark({"player_key": "k1", "points": _PTS}, "var(--accent-green)", 56, 20)
    assert basis == "efv" and "<title>eFV history</title>" in svg
    efv_line = B._fv_sparkline([{"consensus_fv_raw": 50.0}, {"consensus_fv_raw": 61.5}],
                               "var(--accent-green)", w=56, h=20)
    assert svg.replace(' data-grade-basis="efv"><title>eFV history</title>', ">") == efv_line
    # no eFV series: the consensus line, named
    svg2, basis2 = B._mover_spark({"player_key": "k2", "points": _PTS}, "var(--accent-red)", 56, 20)
    assert basis2 == "consensus" and "<title>Consensus FV history</title>" in svg2


def test_mover_row_and_spotlight_card_carry_the_named_line(monkeypatch):
    import build_site as B
    import storage
    monkeypatch.setattr(storage, "EFV_DISPLAY_SWAPS", False)
    p = {"player_key": "zz_row_q9_14", "player_name": "A B", "org": "NYM",
         "position": "SS", "points": _PTS, "stock": {"basis": "xfv"}}
    row = B._row_mover(p, 5)
    assert '<span class="row-spark"><svg' in row and "<title>Consensus FV history</title>" in row
    assert '<span class="visually-hidden">eFV change </span>' in row
    card = B._spotlight_card("Spotlight - Top Riser", p, "", "var(--accent-green)")
    assert "<title>Consensus FV history</title>" in card


def test_wire_names_a_consensus_grade_move(tmp_path, monkeypatch):
    import build_site as B
    from datetime import date
    monkeypatch.setattr(B, "_WIRE_FV_LEDGER", tmp_path / "ledger.json")
    today = date.today().isoformat()
    cons = {"player_key": "c_q9_14", "player_name": "Cons Mover", "org": "NYM",
            "stock": {"basis": "same_source", "delta": 3.0, "direction": "up",
                      "confidence": "high", "to_label": "50", "to_date": today}}
    efv = {"player_key": "e_q9_14", "player_name": "Efv Mover", "org": "NYM",
           "stock": {"basis": "xfv", "delta": 4.0, "direction": "up",
                     "confidence": "high", "to_label": "eFV 55.4", "to_date": today}}
    ev = B._collect_events([cons, efv], [], [])
    vals = {e[6]: e[7] for e in ev if e[1] == "grade_up"}
    assert vals == {"Cons Mover": "+3 Consensus FV", "Efv Mover": "+4 eFV"}


# ---------------------------------------------------------------------------
# /pal/ Prospect Watch (assets/pal.js gradeText; W0 item G06)
# ---------------------------------------------------------------------------

@pytest.fixture()
def pal_js():
    src = _asset("pal.js")
    ctx = _ctx()
    ctx.eval('function esc(s) { return String(s == null ? "" : s); }')
    for f in ("num", "fCeil", "gloss"):
        ctx.eval(_fn(src, f))
    ctx.eval(re.search(r"var FLOOR_TIP = [^;]*;", src, re.S).group(0))
    ctx.eval(_fn(src, "gradeText"))
    return ctx


def test_pal_prospect_watch_prints_efv_first_then_named_consensus(pal_js):
    out = _ev(pal_js, "gradeText({fv: 40.2, fvE: 39.6})")
    assert out == ('<span class="g-term" data-gl="xfv">eFV</span> 40'
                   " &middot; Consensus FV 41")            # eFV nearest, consensus up
    assert _ev(pal_js, "gradeText({fv: 40.2, fvE: null})") == "Consensus FV 41"
    floor = _ev(pal_js, "gradeText({fv: 41, fvE: 20, fvE_is_floor: true})")
    assert floor.startswith('<span class="g-term" data-gl="xfv">eFV</span> 20 <span')
    assert "scale floor" in floor and floor.endswith(" &middot; Consensus FV 41")
    assert '"FV " + fCeil' not in _asset("pal.js")
    assert "clear the consensus FV floor" in _asset("pal.js")


# ---------------------------------------------------------------------------
# /projections/ Team Outlook top prospect (proj_export.py, assets/projections.js)
# ---------------------------------------------------------------------------

_TOP = {"name": "A B", "player_key": "a_b", "fv_label": "53", "fv_raw": 52.3, "xfv_grade": 56.5}


def test_team_outlook_top_prospect_flag_off_is_the_named_consensus_label(monkeypatch):
    import proj_export as pe
    import storage
    monkeypatch.setattr(storage, "EFV_DISPLAY_SWAPS", False)
    assert pe._top_prospect_cell(_TOP) == {"name": "A B", "key": "a_b", "fv": "53",
                                           "fvBasis": "consensus"}


def test_team_outlook_top_prospect_flag_on_is_efv_to_nearest(monkeypatch):
    import proj_export as pe
    import storage
    monkeypatch.setattr(storage, "EFV_DISPLAY_SWAPS", True)
    assert pe._top_prospect_cell(_TOP)["fv"] == 57            # 56.5 half-up, never 56
    assert pe._top_prospect_cell(dict(_TOP, xfv_grade=52.3))["fv"] == 52
    assert pe._top_prospect_cell(_TOP)["fvBasis"] == "efv"
    # eFV abstains: the consensus label, named
    assert pe._top_prospect_cell(dict(_TOP, xfv_grade=None)) == {
        "name": "A B", "key": "a_b", "fv": "53", "fvBasis": "consensus"}


def test_proj_export_reads_the_one_flag():
    src = (ROOT / "proj_export.py").read_text(encoding="utf-8")
    body = src[src.index("def _top_prospect_cell"):src.index("def _org_farm_blocks")]
    assert "storage.EFV_DISPLAY_SWAPS" in body
    assert '"topProspect": (_top_prospect_cell(top)' in src


def test_team_outlook_cell_and_prospect_tag_name_their_basis():
    js = _asset("projections.js")
    assert 'const topBasisEfv = f.topProspect && f.topProspect.fvBasis === "efv";' in js
    assert '${topBasisEfv ? "eFV" : "Consensus FV"} ${esc(String(f.topProspect.fv || "?"))}' in js
    assert '<span class="fa-sub">FV ${esc(String(f.topProspect.fv' not in js
    grade = _fn(js, "prospectGrade")
    assert "`eFV ${Math.round(m.fv)}`" in grade
    assert "`Consensus FV ${EEPHUS_HUB.fvCeil(m.fv)}`" in grade


# ---------------------------------------------------------------------------
# Trade Machine (assets/trademachine.js)
# ---------------------------------------------------------------------------

@pytest.fixture()
def tm_js():
    src = _asset("trademachine.js")
    ctx = _ctx()
    for f in ("_tmFvNum", "_tmFvText", "_tmFvCell", "_tmFvSortNum"):
        ctx.eval(_fn(src, f))
    return ctx


def test_trade_board_column_is_efv_and_its_fallback_is_marked(tm_js):
    assert _ev(tm_js, "_tmFvCell(60.5, 58.2)") == "61"         # eFV nearest
    cell = _ev(tm_js, "_tmFvCell(null, 58.2)")
    assert cell == ('<span data-grade-basis="consensus" title="Consensus FV 59 '
                    '(no eFV for this player)">C 59</span>')   # consensus up, marked
    assert _ev(tm_js, "_tmFvText(60.5, 58.2)") == "eFV 61"
    assert _ev(tm_js, "_tmFvText(null, 58.2)") == "Consensus FV 59"
    # the column sorts on the grade it prints
    assert _ev(tm_js, "_tmFvSortNum({xfv_grade: 60.5, fv: 40})") == 60.5
    assert _ev(tm_js, "_tmFvSortNum({xfv_grade: null, fv: 58.2})") == 58.2


def test_trade_board_header_and_grpo_panel_name_their_grades():
    js = _asset("trademachine.js")
    assert '${_tbTh("eFV", "fv", "tm-num", "Prospects only: eFV, rounded to nearest.' in js
    assert '_tbTh("FV", "fv"' not in js
    assert 'if (col === "fv")  return { n: _tmFvSortNum(p) };' in js
    assert "const fv    = !isProspect ? \"\" : _tmFvCell(p.xfv_grade, p.fv);" in js
    assert ">Consensus FV</th>" in js
    assert '">Consensus FV ${c.fv != null ? String(Math.ceil(Number(c.fv)))' in js


# ---------------------------------------------------------------------------
# Call-up Watch (assets/dynasty.js renderCallups) and the FA arc tooltip
# ---------------------------------------------------------------------------

def test_callup_watch_marks_its_consensus_fallback():
    body = _fn(_asset("dynasty.js"), "renderCallups")
    assert "(c.fvE != null) ? String(Math.round(c.fvE))" in body
    assert ('\'<span data-grade-basis="consensus" title="Consensus FV \' + Math.ceil(c.fv)'
            in body)
    assert "' (no eFV for this player)\">C ' + Math.ceil(c.fv)" in body
    assert "Consensus FV (rounded up, marked C) where eFV is missing." in body


def test_fa_card_arc_tooltip_names_consensus():
    js = _asset("fa.js")
    assert "&middot; Consensus FV ${Math.ceil(p[1])}</title>" in js
    assert "&middot; FV ${Math.ceil(p[1])}</title>" not in js


# ---------------------------------------------------------------------------
# MLB player page origin line (already eFV at debut, wiring W06)
# ---------------------------------------------------------------------------

def test_origin_line_prints_no_consensus_arc():
    js = _asset("projections.js")
    i = js.index("const originLine")
    line = js[i:js.index("\n", js.index('      : "";', i))]
    assert "at debut ${Math.round(org.efvDebut)}" in line
    assert "fvOpen" not in line and "fvClose" not in line
