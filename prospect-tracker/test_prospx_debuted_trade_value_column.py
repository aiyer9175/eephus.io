# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX Debuted list carries a Trade value column with its sort.

Owner answer B4BS-1 (b), 2026-10-01: the Debuted list prints the trade value the
debuted card leads with (B4_BOARD_SURPLUS, one rule: _dtvRow), on desktop and on
the phone row. A row with no contract-projection trade row prints a dash; the
prospect valuation is the second line; the number is spelled as the card spells
it ($X.XM through _taMM). The column reads the slim trade-value sidecar lazily,
once, when the tab opens, and the full board only when the sidecar cannot be read.
"""

from __future__ import annotations

import re
import warnings
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest
from conftest import load_data_doc, serve_site

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
SRC = PROSPX.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), SRC, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def _render_debuts() -> str:
    return _function_source("renderDebuts")


def _media_block_with(marker: str) -> str:
    i = SRC.index(marker)
    j = SRC.rindex("@media", 0, i)
    return SRC[j:i + len(marker) + 1200]


# ---------------------------------------------------------------------------
# 1. The column, desktop and phone
# ---------------------------------------------------------------------------

def test_the_header_and_the_row_carry_a_trade_value_cell_after_fv():
    body = _render_debuts()
    i_fv = body.index('data-debut-sort="fv_close"')
    i_tv = body.index('data-debut-sort="trade_value"')
    i_wag = body.index('data-debut-sort="vs_fv_proj"')
    assert i_fv < i_tv < i_wag
    head = body[body.rindex("<span", 0, i_tv):body.index("</span>", i_tv)]
    assert ">Trade value" in head and "sort-header" in head
    # The phone row keeps the column: neither the header span nor the cell is desktop-only.
    assert "desktop-only" not in head
    # Q9_10: the badge's lead reads _debutGradePrimary() (the list's own toggle, or eFV
    # whenever storage.EFV_DISPLAY_SWAPS is on).
    i_badge = body.index("${efvBadgeHTML(g, { primary: _debutGradePrimary(),")
    i_cell = body.index("${_debutTvCellHTML(g)}")
    i_chart = body.index('<div class="desktop-only" style="padding-right:6px;">${chartHtml}</div>')
    assert i_badge < i_cell < i_chart
    assert "desktop-only" not in _function_source("_debutTvCellHTML")


def test_the_grids_have_a_track_for_it_on_desktop_and_on_the_phone():
    desk = re.search(r"\.debut-header, \.debut-row \{\s*display: grid;\s*grid-template-columns: ([^;]+);", SRC)
    assert desk, "desktop debut grid not found"
    assert len(desk.group(1).split()) == 9, desk.group(1)
    narrow = _media_block_with("grid-template-columns: 28px 1.2fr 0.5fr 0.75fr;")
    # #, player, FV, Trade value on line one; MLB stats spans line two.
    assert ".debut-header > span:last-child,\n      .debut-row > .milb-cell:last-child { grid-column: 2 / -1; }" in narrow
    assert ".debut-row .desktop-only," in narrow
    assert ".debut-header .debut-date-cell, .debut-header .debut-level-cell { display: none; }" in narrow


def test_the_cell_prints_the_cards_number_and_a_dash_otherwise():
    cell = _function_source("_debutTvCellHTML")
    assert "debutedTradeValueMM(g)" in cell, "one rule: the card's debutedTradeValueMM / _dtvRow"
    assert "${_taMM(mm)}</div>" in cell, "the card's $X.XM spelling"
    assert '<div class="debut-tv-lead is-none">-</div>' in cell
    assert "_debutTvSecondary(g)" in cell and "fmtSvMM(sec.mm)" in cell
    # The colour bands are the card's (_tvLeadFill).
    band = 'mm >= 50 ? "var(--up)" : mm >= 10 ? "var(--neon-cyan)" : mm < 0 ? "var(--down)" : "var(--text-primary)"'
    assert band in cell and band in _function_source("_tvLeadFill")
    sec = _function_source("_debutTvSecondary")
    assert '"eFV prospect"' in sec and "_debutGradePrimary()" in sec


# ---------------------------------------------------------------------------
# 2. The sort
# ---------------------------------------------------------------------------

def test_the_sort_ranks_priced_rows_and_keeps_dashes_at_the_bottom():
    body = _render_debuts()
    i = body.index('} else if (sortMode === "trade_value") {')
    branch = body[i:body.index("} else if", i + 10)]
    assert "_debutTvSortValue(g)" in branch
    assert "priced.sort((a, b) => _tv.get(b) - _tv.get(a));" in branch
    assert "if (state.sortRev && state.sortRev.debutSort) priced.reverse();" in branch
    assert "orderedGrads = priced.concat(unpriced);" in branch
    # The blanket reverse would float every dash to the top.
    assert 'if (orderedGrads && sortMode !== "trade_value") _applySortDir(orderedGrads, "debutSort");' in body
    assert '<button class="chip" data-debut-sort="trade_value"' in SRC
    assert 'trade_value: "by trade value"' in SRC


# ---------------------------------------------------------------------------
# 3. The slim read, lazily, once; the full board only as the fallback
# ---------------------------------------------------------------------------

def test_the_column_reads_through_the_shared_loader_once():
    kick = _function_source("_debutTvKick")
    assert "if (_debutTvKicked || _TA_TV.idx) return;" in kick
    assert "_debutTvKicked = true;" in kick
    assert "_taTradeValuesLoad()" in kick
    assert "trade_values" not in kick
    assert "try { _debutTvKick(); }" in _render_debuts()
    loader = _function_source("_taTradeValuesLoad")
    i_slim, i_full = loader.find('get("trade_values_slim.json")'), loader.find('get("trade_values.json")')
    assert 0 <= i_slim < i_full
    assert ".then(j => ((j && j.players) ? j : get(\"trade_values.json\")))" in loader
    # Before the board lands the cell is pending and does not kick a second load.
    cell = _function_source("_debutTvCellHTML")
    assert cell.index("if (!_TA_TV.idx)") < cell.index("debutedTradeValueMM(g)")
    assert "return _TA_TV.idx ? debutedTradeValueMM(g) : null;" in _function_source("_debutTvSortValue")


# ---------------------------------------------------------------------------
# 4. The cell in V8, against a small board
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    ctx = mr.MiniRacer()
    ctx.eval("""
      if (!String.prototype.normalize) String.prototype.normalize = function () { return String(this); };
      var state = { section: "debuts", view: null, debutGrade: "xfv", sortRev: {} };
      var DATA = { flags: {} };
      var _TA_TV = { idx: null, loading: null };
      var KICKS = 0;
      function _dtvKick() { KICKS++; }
      function escapeHtml(s) { return String(s); }
      function getEfv(p) { return (p && p.efv) || null; }
    """)
    for fn in ("efvDisplaySwaps", "_debutGradePrimary",
               "_taFold", "_taBuildIndex", "_taMM", "fmtSvMM", "_dtvRow",
               "debutedTradeValueMM", "_debutTvSortValue", "_debutTvSecondary", "_debutTvCellHTML"):
        ctx.eval(_function_source(fn))
    ctx.eval("""
      var BOARD = { generated_at: "2026-10-02", players: [
        { player_key: "a", mlbam_id: 1, player_name: "A", surplus_source: "projection", trade_value_mm: 345.46 },
        { player_key: "b", mlbam_id: 2, player_name: "B", surplus_source: "efv", trade_value_mm: 40.0 },
        { player_key: "c", mlbam_id: 99, player_name: "C", surplus_source: "projection", trade_value_mm: 12.0 },
        { player_key: "d", mlbam_id: 4, player_name: "D", surplus_source: "projection", trade_value_mm: -3.25 } ] };
      var ROWS = {
        a: { player_key: "a", mlbam_id: 1, status: "debuted", efv: { surplus_mm: 147.2 }, surplus: { value_mm: 20.4 } },
        b: { player_key: "b", mlbam_id: 2, status: "debuted", efv: { surplus_mm: 9.5 } },
        c: { player_key: "c", mlbam_id: 3, status: "debuted" },
        d: { player_key: "d", mlbam_id: 4, status: "debuted" },
        z: { player_key: "zz", mlbam_id: 5, status: "debuted" } };
      function cell(k) { return _debutTvCellHTML(ROWS[k]); }
    """)
    return ctx


def _lead(html: str) -> str:
    m = re.search(r'<div class="debut-tv-lead[^"]*"[^>]*>([^<]*)</div>', html)
    return m.group(1) if m else None


def _sub(html: str) -> str | None:
    m = re.search(r'<div class="debut-tv-sub">([^<]*)</div>', html)
    return m.group(1) if m else None


def test_pending_before_the_board_lands(js):
    js.eval("_TA_TV.idx = null; KICKS = 0;")
    html = js.eval('cell("a")')
    assert _lead(html) == "..." and "is-pending" in html
    assert js.eval('_debutTvSortValue(ROWS.a)') is None
    assert js.eval("KICKS") == 0, "the pending cell does not start a second load"


def test_the_lead_is_the_projection_row_for_the_same_human(js):
    js.eval("_TA_TV.idx = _taBuildIndex(BOARD); state.debutGrade = 'xfv';")
    a = js.eval('cell("a")')
    assert _lead(a) == "$345.5M" and _sub(a) == "eFV prospect $147M"
    assert js.eval("_debutTvSortValue(ROWS.a)") == pytest.approx(345.46)
    # toFixed breaks an exact tie upward (3.25 -> 3.3), as /trademachine/ does.
    assert _lead(js.eval('cell("d")')) == "-$3.3M"
    # Not on the projection basis, another mlbam, or no row at all: a dash, no sort value.
    for k in ("b", "c", "z"):
        assert _lead(js.eval(f'cell("{k}")')) == "-", k
        assert js.eval(f"_debutTvSortValue(ROWS.{k})") is None, k
    assert _sub(js.eval('cell("b")')) == "eFV prospect $9.5M"
    assert _sub(js.eval('cell("c")')) is None


def test_the_second_line_follows_the_lists_lead_grade(js):
    js.eval("_TA_TV.idx = _taBuildIndex(BOARD); state.debutGrade = 'fv';")
    try:
        assert _sub(js.eval('cell("a")')) == "FV prospect $20M"
        # Owner answer Q-E1 behind storage.EFV_DISPLAY_SWAPS: the toggle orders the list
        # only, so the second line stays on eFV.
        js.eval("DATA.flags = { efv_display_swaps: true };")
        assert _sub(js.eval('cell("a")')) == "eFV prospect $147M"
    finally:
        js.eval("state.debutGrade = 'xfv'; DATA.flags = {};")


def test_a_board_that_could_not_be_read_prints_dashes(js):
    js.eval("_TA_TV.idx = _taBuildIndex(null);")
    html = js.eval('cell("a")')
    assert _lead(html) == "-" and "could not be read" in html


# ---------------------------------------------------------------------------
# 5. Served: the Debuted tab reads the sidecar, and falls back to the board
# ---------------------------------------------------------------------------

_LEADS = """() => Array.from(document.querySelectorAll('#debut-rows .debut-row')).map(r => {
  const e = r.querySelector('.debut-tv-lead'); return [r.dataset.key, e ? e.textContent.trim() : null]; })"""


def _expected() -> dict:
    tv = load_data_doc("trade_values.json")
    deb = load_data_doc("debuts.json")
    if not tv or not tv.get("players") or not deb:
        pytest.skip("data/trade_values.json or data/debuts.json not built")
    board = {r["player_key"]: r for r in tv["players"]}
    rows = deb if isinstance(deb, list) else deb.get("players", [])
    out = {}
    for r in rows:
        t = board.get(r.get("player_key"))
        if (r.get("status") != "debuted" or not t or t.get("surplus_source") != "projection"
                or t.get("trade_value_mm") is None):
            continue
        if r.get("mlbam_id") and t.get("mlbam_id") is not None and int(t["mlbam_id"]) != int(r["mlbam_id"]):
            continue
        out[r["player_key"]] = float(t["trade_value_mm"])
    return out


def _ta_mm(v: float) -> str:
    """_taMM in Python: Number.prototype.toFixed(1) on the exact binary value,
    an exact tie going up (Python's format would round it to even)."""
    q = Decimal(abs(v)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{'-' if v < 0 else ''}${q}M"


def _open_sorted(block_slim: bool):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.add_init_script("try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        fetched: list[str] = []
        page.on("request", lambda r: fetched.append(r.url.split("?")[0].rsplit("/", 1)[-1]))
        if block_slim:
            page.route("**/trade_values_slim.json*", lambda route: route.abort())
        page.goto(base + "prospx/index.html#tab=debuts&gsort=trade_value", wait_until="load", timeout=120_000)
        page.wait_for_function(
            "() => document.querySelector('#debut-rows .debut-tv-lead')"
            " && !document.querySelector('#debut-rows .debut-tv-lead.is-pending')", timeout=180_000)
        leads = page.evaluate(_LEADS)
        browser.close()
    return errs, fetched, leads


def _check_sorted(leads, expected):
    assert len(leads) >= 100
    priced = [(k, t) for k, t in leads if t != "-"]
    assert len(priced) >= 100, "the first page of the trade value sort is all priced"
    want = sorted(expected.items(), key=lambda kv: -kv[1])
    for k, t in priced[:50]:
        assert t == _ta_mm(expected[k]), (k, t)
    vals = [expected[k] for k, _ in priced]
    assert vals == sorted(vals, reverse=True), "highest trade value first"
    assert priced[0][0] == want[0][0]


def test_served_the_debuted_tab_reads_the_sidecar_once_and_sorts():
    expected = _expected()
    errs, fetched, leads = _open_sorted(block_slim=False)
    assert not errs, errs[:3]
    if (ROOT / "data" / "trade_values_slim.json").exists():
        assert fetched.count("trade_values_slim.json") == 1, "read once"
        assert "trade_values.json" not in fetched, "the Debuted view never loads the 5 MB board"
    _check_sorted(leads, expected)


def test_served_without_the_sidecar_the_column_falls_back_to_the_full_board():
    expected = _expected()
    errs, fetched, leads = _open_sorted(block_slim=True)
    assert not errs, errs[:3]
    assert "trade_values.json" in fetched
    _check_sorted(leads, expected)
