# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX sections other than Leaderboards, redesigned (site pass REDESIGN_prospx).

WHY THIS EXISTS (2026-10-08). Every PROSPX filter bar opened by default on desktop,
so at 1280 the first data row sat at 782 px on the board, 749 on Draft and 743 on
Farm; the Farm list fell back to 30 cards of about 280 px below 1300 px of window
width (an 8,694 px page at 1280); the Injured List printed 267 rows on one page
(25,735 px) and International Amateurs 364 (17,100 px); and the Standout ribbon
took three lines all winter.

Contract pinned here:
  * every collapsible filter bar renders closed without a stored choice, and a
    stored per-viewer choice still wins; Draft and Overseas print their active
    filters as removable chips beside the toggle, as the board, IL and Farm do;
  * Farm defaults to Table at every width (Cards only when picked), its columns
    stepping down by width with the header on the rows' boundaries, and the
    Tendencies chips are one select with a count;
  * the Injured List and International Amateurs page at 50 rows;
  * in the browser at 1280 the first row of the board, Debuted, Draft and Farm
    sits above y 600 with the filters closed, and outside the regular season the
    Standout ribbon is one line.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

from conftest import serve_site

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _fn(src: str, name: str, indent: str = "") -> str:
    m = re.search(r"^%s(?:async )?function %s\([^)]*\)\s*\{.*?\n%s\}\n" % (indent, re.escape(name), indent),
                  src, re.S | re.M)
    assert m, f"{name} not found"
    return m.group(0)


@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    ctx = mr.MiniRacer()
    ctx.eval("""var STORE = {}; var window = {innerWidth: 1280};
      var localStorage = {getItem: function (k) { return k in STORE ? STORE[k] : null; },
                          setItem: function (k, v) { STORE[k] = String(v); }};
      function Bar(id) { this.id = id; this.cls = {};
        var self = this; this.classList = {toggle: function (c, on) { self.cls[c] = !!on; },
                                           contains: function (c) { return !!self.cls[c]; }}; }
      function Btn() { this.attrs = {}; this.setAttribute = function (k, v) { this.attrs[k] = v; }; }
      const FILTER_LS_PREFIX = "prospect-tracker.filters.";""")
    src = _src()
    ctx.eval(_fn(src, "filterBarStored", "  "))
    ctx.eval(_fn(src, "applyFilterBarDefault", "  "))
    return ctx


# ------------------------------------------------------------- filter bars

@pytest.mark.parametrize("width", [390, 720, 1280, 1920])
def test_filter_bars_render_closed_without_a_stored_choice(js, width):
    js.eval("STORE = {}; window.innerWidth = %d;" % width)
    js.eval("var b = new Bar('draft-filter-bar'), t = new Btn(); applyFilterBarDefault(b, t);")
    assert js.eval("b.classList.contains('is-open')") is False
    assert js.eval("t.attrs['aria-expanded']") == "false"


@pytest.mark.parametrize("stored,is_open", [("open", True), ("collapsed", False)])
def test_a_stored_choice_still_wins(js, stored, is_open):
    js.eval("STORE = {'prospect-tracker.filters.filter-bar': %s};" % json.dumps(stored))
    js.eval("var b = new Bar('filter-bar'), t = new Btn(); applyFilterBarDefault(b, t);")
    assert js.eval("b.classList.contains('is-open')") is is_open
    assert js.eval("t.attrs['aria-expanded']") == ("true" if is_open else "false")


def test_every_collapsible_bar_has_a_chip_strip_or_no_filters():
    src = _src()
    # The bars that hold filters print them beside the toggle.
    for strip in ("active-filters-strip", "injured-active-filters", "farm-active-filters",
                  "draft-active-filters-strip", "overseas-active-filters-strip"):
        assert f'id="{strip}"' in src
    assert '_pxRenderBarChips("draft");' in _fn(src, "renderDraft")
    assert '_pxRenderBarChips("overseas");' in _fn(src, "renderOverseas")
    # the old width rule is gone
    assert "FILTER_MOBILE_BP" not in src


def test_draft_and_overseas_chips_name_each_non_default_filter():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    ctx = mr.MiniRacer()
    ctx.eval("""function escapeHtml(s){ return String(s); }
      var state = {draftPool: 'HS', draftSide: 'all', draftPos: 'SS', draftStatus: 'all',
                   draftFvIndicators: new Set(['upside']),
                   overseasSide: 'all', overseasPos: 'all', overseasStatus: 'all',
                   overseasFvIndicators: new Set()};""")
    src = _src()
    m = re.search(r"^const _PX_BAR_CHIPS = \{.*?\n\};\n", src, re.S | re.M)
    assert m
    ctx.eval(m.group(0))
    ctx.eval(_fn(src, "_pxBarChipsHTML"))
    html = ctx.eval("_pxBarChipsHTML('draft')")
    keys = re.findall(r'data-clear-filter="([^"]+)"', html)
    assert keys == ["bar:draft:draftPool", "bar:draft:draftPos", "bar:draft:draftFvIndicators:upside"]
    assert html.count("<button") == 3
    assert ctx.eval("_pxBarChipsHTML('overseas')") == ""
    # the shared clear handler understands the bar keys
    assert 'case key.startsWith("bar:"):' in src


# ------------------------------------------------------------- farm

def test_farm_defaults_to_table_at_every_width():
    src = _src()
    assert 'farmViewMode: "table",' in src
    fn = _fn(src, "farmViewEffective")
    assert "innerWidth" not in fn and "cards" not in fn
    for gone in ("FARM_TABLE_MIN_PX", "farmTableFitsViewport", "farmViewPinned"):
        assert gone not in src, gone
    assert 'class="chip active" data-farm-view="table"' in src


def test_farm_tendencies_are_one_select_with_a_count():
    src = _src()
    assert '<select id="farm-tendency-select"' in src
    fn = _fn(src, "renderFarmTendencyChips")
    assert "ALL_TENDENCY_BADGES.length" in fn
    # picked tendencies only print as chips, not one chip per tendency
    assert "filter(({ kind }) => sel.has(kind))" in fn


# ------------------------------------------------------------- paging

def test_injured_list_and_international_amateurs_page_at_50():
    src = _src()
    assert re.search(r"pageSizes: \{[^}]*injured: 50, ifa: 50,", src, re.S)
    assert '"injured","ifa"]' in src  # _PG_KEYS
    il = _fn(src, "renderInjured")
    assert 'renderPaginationStrip(_ilPage, filtered.length, _ilSize, "injured")' in il
    assert "pageSlice(filtered, _ilPage, _ilSize)" in il
    ifa = _fn(src, "renderIFA")
    assert 'renderPaginationStrip(_ifaPage, shown.length, _ifaSize, "ifa")' in ifa
    assert "pageSlice(shown, _ifaPage, _ifaSize)" in ifa
    for k in ('p.set("ilpage"', 'p.set("ifapage"', '_readPage("ilpage"', '_readPage("ifapage"'):
        assert k in src
    # the empty and failed states that remain go through the pixel state box
    assert 'class="state-message"' not in il
    head = ifa.split("const t = cls.trends")[0]
    assert not re.search(r'class="state-message[ "]', head)
    assert head.count("_pxStateHTML(") == 4


# ------------------------------------------------------------- the browser

@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


_FIRST = {
    "active": ("", "#rows [data-key]"),
    "debuts": ("#tab=debuts", "#debut-rows [data-key]"),
    "draft": ("#tab=draft", "#draft-rows .draft-card"),
    "farm": ("#tab=farm", "#farm-rows .farm-row"),
}


def _page(p, server, width, suffix, sel):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.goto(server + "prospx/" + suffix, wait_until="load", timeout=120_000)
    page.wait_for_selector(sel, timeout=90_000)
    page.wait_for_timeout(1500)
    return browser, page


@pytest.mark.parametrize("section", list(_FIRST))
def test_first_row_sits_in_the_first_viewport_at_1280(server, section):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    suffix, sel = _FIRST[section]
    with sync_playwright() as p:
        browser, page = _page(p, server, 1280, suffix, sel)
        try:
            m = page.evaluate("""(sel) => ({
              y: document.querySelector(sel).getBoundingClientRect().top + scrollY,
              open: [...document.querySelectorAll('.collapsible-filter-bar, #filter-bar')]
                      .filter(b => b.classList.contains('is-open')).map(b => b.id)})""", sel)
        finally:
            browser.close()
    assert m["open"] == [], f"{section}: bars open by default: {m['open']}"
    assert m["y"] < 600, f"{section}: first row at y {m['y']:.0f} at 1280"


@pytest.mark.parametrize("width", [1600, 1280, 1100, 900, 390])
def test_farm_table_fits_and_keeps_the_header_on_the_rows(server, width):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = _page(p, server, width, "#tab=farm", "#farm-rows .farm-row")
        try:
            m = page.evaluate("""() => {
              const vis = el => [...el.children].filter(c => getComputedStyle(c).display !== 'none')
                .map(c => [(c.className.match(/fc-[a-z]+/) || [''])[0], Math.round(c.getBoundingClientRect().left)]);
              const rows = [...document.querySelectorAll('#farm-rows .farm-row')];
              return {cards: document.getElementById('farm-section').classList.contains('farm-rows-cards'),
                      n: rows.length, head: vis(document.querySelector('#farm-rows .farm-header')),
                      row: vis(rows[0]), overflow: document.documentElement.scrollWidth - innerWidth,
                      rowOverflow: Math.max(...rows.map(r => r.scrollWidth - r.clientWidth))};
            }""")
        finally:
            browser.close()
    assert not m["cards"], "Farm fell back to cards"
    assert m["n"] == 30
    assert m["overflow"] <= 0 and m["rowOverflow"] <= 1, m
    assert [c for c, _ in m["head"]] == [c for c, _ in m["row"]]
    for (c, hx), (_, rx) in zip(m["head"], m["row"]):
        assert abs(hx - rx) <= 1, f"{width}px: {c} header at {hx}, row at {rx}"


@pytest.mark.parametrize("suffix,rows", [
    ("#tab=injured", "#injured-rows [data-key]"),
    ("#tab=ifa", "#ifa-rows .ifa-main tbody tr"),
])
def test_long_lists_print_50_rows_and_a_pager(server, suffix, rows):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = _page(p, server, 1280, suffix, rows)
        try:
            m = page.evaluate("""(sel) => ({n: document.querySelectorAll(sel).length,
              pager: (document.querySelector(sel.split(' ')[0] + ' .pg-count') || {}).textContent || ''})""", rows)
        finally:
            browser.close()
    assert m["n"] <= 50
    total = re.search(r"of (\d+)", m["pager"])
    if total and int(total.group(1)) > 50:
        assert m["n"] == 50 and m["pager"].startswith("Showing 1-50 of")


def test_standout_ribbon_is_one_line_outside_the_regular_season(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = _page(p, server, 1280, "#tab=spotlights", "#whats-standout-spotlights .news-ticker")
        try:
            m = page.evaluate("""() => {
              const t = document.querySelector('#whats-standout-spotlights .news-ticker');
              const h = t.querySelector('.news-ticker-headline');
              return {phase: window.EephusSeason ? window.EephusSeason.phase() : null,
                      oneline: t.classList.contains('ntk-oneline'),
                      lines: h.querySelectorAll('.ntk-subline').length,
                      headH: h.getBoundingClientRect().height};
            }""")
        finally:
            browser.close()
    if m["phase"] in (None, "regular"):
        assert not m["oneline"]
    else:
        assert m["oneline"] and m["lines"] == 1 and m["headH"] < 30, m
