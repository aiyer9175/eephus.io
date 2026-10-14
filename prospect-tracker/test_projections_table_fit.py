# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /projections/ Players table fits the screen (owner ask 2026-09-11).

The MiniRacer smoke test pins the markup but has no CSS, so it cannot see the
column tiers (@container projboard in site.css). This drives the served page
in headless Chromium at a laptop and a phone and pins what the table promises:
no sideways page scroll, a header that sticks, all five seasons on a phone,
Age still readable once its column folds, 24px sort targets, and a detail
line that paints exactly as many cells as the header (a colspan past the
painted columns adds phantom columns to a fixed-layout table and crushes the
Player column).

Extended 2026-09-16 with the value ruler's legend chip, which is the one new
block above the table: it has to sit inside the board column and stay on one
line at 390px, because a wrapping chip pushes the table down and a chip wider
than its column is the first thing that would scroll the page sideways.
"""
from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest

from conftest import serve_site

VIEWPORTS = [(1280, 800), (390, 844)]


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def _new_page(browser, w, h):
    return browser.new_page(viewport={"width": w, "height": h})


@contextlib.contextmanager
def _board_page(server, w, h, hash_=""):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = _new_page(browser, w, h)
            page.goto(server + "projections/" + hash_, wait_until="networkidle", timeout=60_000)
            page.wait_for_selector("table.proj-board-table tbody tr[data-key]", timeout=30_000)
            page.wait_for_timeout(400)
            yield page
        finally:
            browser.close()


_FIT = """() => {
  const de = document.documentElement, vis = el => getComputedStyle(el).display !== 'none';
  const t = document.querySelector('table.proj-board-table');
  const wrap = document.querySelector('.proj-board-wrap');
  const heads = [...t.querySelectorAll('thead th')].filter(vis);
  const row = t.querySelector('tbody tr[data-key]');
  const key = document.querySelector('.proj-board-main .tier-key');
  const main = document.querySelector('.proj-board-main');
  const kr = key && key.getBoundingClientRect();
  return {
    keyPresent: !!key,
    keyGl: !!(key && key.querySelector('[data-gl="value_ruler"]')),
    keySteps: key ? key.querySelectorAll('span[class^="tk-"]').length : 0,
    keyOver: kr ? kr.width - main.getBoundingClientRect().width : 0,
    keyH: kr ? Math.round(kr.height) : 0,
    keyControls: key ? key.querySelectorAll('a,button,input,select,textarea').length : 0,
    keyStops: key ? key.querySelectorAll('[tabindex]:not([tabindex="-1"])').length : 0,
    pageScroll: de.scrollWidth - de.clientWidth,
    over: t.getBoundingClientRect().width - wrap.getBoundingClientRect().width,
    seasons: heads.filter(th => th.classList.contains('pc-y')).length,
    minSortH: Math.min(...heads.map(th => th.querySelector('button').getBoundingClientRect().height)),
    ageCol: heads.some(th => th.classList.contains('pc-age')),
    subAge: vis(row.querySelector('.proj-sub-age')),
    clipped: [...row.children].filter(c => vis(c) && !c.classList.contains('pc-player')
                                         && c.scrollWidth > c.clientWidth + 1).length,
  };
}"""

_STICK = """() => {
  const th = document.querySelector('table.proj-board-table thead th.pc-tot');
  window.scrollTo(0, th.getBoundingClientRect().top + scrollY + 900);
  const top = th.getBoundingClientRect().top;
  window.scrollTo(0, 0);
  return top;
}"""

_DETAIL = """async () => {
  const vis = el => getComputedStyle(el).display !== 'none';
  const t = document.querySelector('table.proj-board-table');
  const widths = () => [...t.querySelectorAll('thead th')].filter(vis).map(th => Math.round(th.getBoundingClientRect().width));
  const before = widths();
  const tr = t.querySelector('tbody tr[data-key]');
  tr.querySelector('.proj-xp-btn').click();
  await new Promise(r => setTimeout(r, 50));
  const d = tr.nextElementSibling;
  return {isDetail: !!d && d.classList.contains('proj-detail'),
          span: [...d.children].filter(vis).reduce((a, c) => a + c.colSpan, 0),
          cols: before.length, same: JSON.stringify(before) === JSON.stringify(widths()),
          expanded: tr.querySelector('.proj-xp-btn').getAttribute('aria-expanded'),
          pageScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_projections_table_fits_without_sideways_scroll(server, w, h):
    with _board_page(server, w, h) as page:
        fit = page.evaluate(_FIT)
        assert fit["pageScroll"] <= 0, f"{w}px: the page scrolls sideways by {fit['pageScroll']}px"
        assert fit["over"] <= 0.5, f"{w}px: the table is wider than its box"
        assert fit["seasons"] == 5, f"{w}px: {fit['seasons']} of 5 season columns painted"
        assert fit["minSortH"] >= 24, f"{w}px: a sort target is {fit['minSortH']}px tall"
        assert fit["clipped"] == 0, f"{w}px: a number is clipped in row 1"
        # The legend chip: present, readable through the glossary hook, six
        # steps, inside its column, one line (measured 15px).
        assert fit["keyPresent"] and fit["keyGl"], f"{w}px: no legend chip"
        assert fit["keySteps"] == 6, f"{w}px: {fit['keySteps']} legend steps"
        assert fit["keyOver"] <= 0.5, f"{w}px: the legend chip is wider than its column"
        assert fit["keyH"] <= 20, f"{w}px: the legend chip wraps ({fit['keyH']}px tall)"
        # It carries no control of its own. Its ONE tab stop is the glossary
        # term, which eephus-gl.js gives tabindex=0 to every [data-gl] on the
        # site so a keyboard reader can open the definition: the chip is a
        # glossary term like any other, not a new widget.
        assert fit["keyControls"] == 0, f"{w}px: the legend chip carries a control"
        assert fit["keyStops"] == 1, f"{w}px: {fit['keyStops']} tab stops in the chip"
        # Age is a column at a laptop and a sub-line fact on a phone; never neither.
        assert fit["ageCol"] != fit["subAge"], fit
        assert abs(page.evaluate(_STICK)) < 1, f"{w}px: the header does not stick"


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_detail_line_paints_exactly_the_header_columns(server, w, h):
    with _board_page(server, w, h) as page:
        d = page.evaluate(_DETAIL)
        assert d["isDetail"] and d["expanded"] == "true"
        assert d["span"] == d["cols"], f"{w}px: detail spans {d['span']} of {d['cols']} columns"
        assert d["same"], f"{w}px: opening a detail line moved the columns"
        assert d["pageScroll"] <= 0


# ---------------------------------------------------------------------------
# Team Outlook (#view=teams): the T3 runs columns and the T7 drill-down
# (TM_7, dark) must not add a sideways scroll. The served rows are read as
# they are, then the same rows carry a runs block (the side TM-C passed) and
# a drill-down, served through a route so no file under data/ moves.
# ---------------------------------------------------------------------------

_TEAMS_FIT = """() => {
  const de = document.documentElement, vis = el => el && getComputedStyle(el).display !== 'none';
  const t = document.querySelector('#proj-rows table.proj-table');
  const drill = document.querySelector('tr.proj-drill');
  const inner = document.querySelector('.proj-drill-inner');
  const ir = inner && inner.getBoundingClientRect();
  return {pageScroll: de.scrollWidth - de.clientWidth, tableScroll: t.scrollWidth,
          heads: t.querySelectorAll(':scope > thead th').length,
          span: drill ? [...drill.children].reduce((a, c) => a + c.colSpan, 0) : null,
          innerLeft: ir ? ir.left : null, innerRight: ir ? ir.right : null, vw: de.clientWidth,
          runCells: [...t.querySelectorAll('td.proj-tm-run')].filter(vis).length,
          btnH: drill ? drill.previousElementSibling.querySelector('.proj-drill-btn').getBoundingClientRect().height : null};
}"""


def _teams_fixture_body():
    doc = json.loads((Path(__file__).parent / "data" / "mlb_projections.json").read_text(encoding="utf-8"))
    rows = doc.get("team_outlook") or []
    if not rows:
        pytest.skip("no Team Outlook rows in the served payload")
    for r in rows:
        r["runs"] = {"ra": 700.0, "pf": 1.0}
        r["drill"] = {"season": doc.get("first_season"), "frame": "FanGraphs frame",
                      "players": [{"key": "a", "name": "Long Hyphenated-Surname Player", "pos": "SS",
                                   "side": "two", "pa": None, "ip": None, "bat": 12.4, "bsr": 1.1,
                                   "fld": -2.0, "posRuns": 6.8, "pitRuns": 24.8, "warComp": 3.4,
                                   "gap": -0.4, "war": 3.0, "warChamp": 3.2}],
                      "foot": {"nPlayers": 1, "warComp": 3.4, "gap": -0.4, "warNoComp": 0, "nNoComp": 0,
                               "warServed": 3.0, "champMinusServed": 0.2, "prospects": 0.0,
                               "nProspects": 0, "rosterWar": r.get("war"), "residual": 0.0}}
    return json.dumps(doc), rows[0]["team"]


@contextlib.contextmanager
def _teams_page(server, w, h, hash_, body=None):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = _new_page(browser, w, h)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            if body is not None:
                page.route("**/data/mlb_projections.json*", lambda r: r.fulfill(
                    status=200, content_type="application/json", body=body))
            page.goto(server + "projections/" + hash_, wait_until="networkidle", timeout=60_000)
            page.wait_for_selector("#proj-rows table.proj-table tbody tr", timeout=30_000)
            page.wait_for_timeout(400)
            yield page, errors
        finally:
            browser.close()


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_team_outlook_blocks_add_no_sideways_scroll(server, w, h):
    body, club = _teams_fixture_body()
    with _teams_page(server, w, h, "#view=teams") as (page, errors):
        base = page.evaluate(_TEAMS_FIT)
        assert not errors, errors
    with _teams_page(server, w, h, f"#view=teams&club={club}", body) as (page, errors):
        fit = page.evaluate(_TEAMS_FIT)
        assert not errors, errors
    assert fit["pageScroll"] <= 0, f"{w}px: the page scrolls sideways by {fit['pageScroll']}px"
    # the table's own scroll (marked on a phone) grows by nothing
    assert fit["tableScroll"] <= base["tableScroll"] + 0.5, (w, base["tableScroll"], fit["tableScroll"])
    assert fit["heads"] == base["heads"] + 1, "the RA column joins the header"
    assert fit["span"] == fit["heads"], f"{w}px: the drill-down spans {fit['span']} of {fit['heads']}"
    # the open panel sits inside the visible box, and its toggle is a 24px target
    assert fit["innerLeft"] >= 0 and fit["innerRight"] <= fit["vw"] + 0.5, fit
    assert fit["btnH"] >= 24, fit
    # on a phone the run columns leave (the drill-down prints the same line)
    assert (fit["runCells"] == 0) == (w < 640), fit
