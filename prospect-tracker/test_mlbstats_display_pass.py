# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ display pass (DISPLAY_mlbstats, 2026-10-07), one pin per
finding where a test can hold it.

The rendered cases use the py_mini_racer smoke harness. The served cases drive
Chromium over loopback with every off-site request aborted, and skip when
Playwright, Chromium or the Overall board is missing.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import test_mlbstats_views as views
from conftest import serve_site

ROOT = Path(__file__).parent
MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    if not (ROOT / "data" / "war_leaderboards.json").exists():
        pytest.skip("the Overall board is not built on this machine")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001 - no chromium on this machine
            pytest.skip("chromium unavailable: %s" % e)
        try:
            yield b
        finally:
            b.close()


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


# Counts each time a board table lands in the Overall root.
_INIT = """
window.__ins = 0;
document.addEventListener('DOMContentLoaded', () => {
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => {
    if (n.nodeType === 1 && n.closest && n.closest('#mlbstats-war-root')
        && (n.matches('table.mlbstats-table') || n.querySelector('table.mlbstats-table'))) window.__ins++;
  }))).observe(document.body, {childList: true, subtree: true});
});
"""
R = "#mlbstats-war-root "


def _context(browser, w, h, **kw):
    ctx = browser.new_context(viewport={"width": w, "height": h}, accept_downloads=True, **kw)
    ctx.route(re.compile(r"^(?!http://127\.0\.0\.1:).*"), lambda route: route.abort())
    ctx.add_init_script("try { localStorage.clear(); } catch (e) {}")
    ctx.add_init_script(_INIT)
    return ctx


def _open(page, server, hash_=""):
    page.goto(server + "mlbstats/" + hash_, wait_until="networkidle")
    page.wait_for_selector(R + "table.mlbstats-table", timeout=20000)
    page.wait_for_timeout(600)


# ---------------------------------------------------------------- QMLA05 / QMLA08 / QMLA17
def test_every_header_is_a_column_header_and_the_table_has_a_name():
    """QMLA17: Pos and Also on had no scope, and no board table had a name."""
    html = views._render_war()
    heads = re.findall(r"<th [^>]*>", views._table(html))
    assert heads and all('scope="col"' in h for h in heads), heads
    assert '<caption class="visually-hidden">Overall eWAR leaderboard</caption>' in html
    team = views._render_war("#section=war&wview=teams")
    assert '<caption class="visually-hidden">Team eWAR</caption>' in team


def test_a_header_that_does_not_sort_promises_no_click(browser, server):
    """QMLA17: th.mlbstats-col-pos showed a pointer and did nothing."""
    ctx = _context(browser, 1280, 900)
    try:
        page = ctx.new_page()
        _open(page, server)
        bad = page.evaluate("[...document.querySelectorAll('%sth[data-col]:not([tabindex])')]"
                            ".filter(h => getComputedStyle(h).cursor === 'pointer').map(h => h.textContent)" % R)
        assert bad == [], bad
    finally:
        ctx.close()


def test_enter_on_a_season_caret_keeps_focus_on_it(browser, server):
    """QMLA05: the render after Enter dropped focus to <body>, and the next Tab
    went to Download CSV above the board."""
    ctx = _context(browser, 1280, 900)
    try:
        page = ctx.new_page()
        _open(page, server)
        caret = page.evaluate("document.querySelector('%s.mlbx-caret').getAttribute('data-mlbexpand')" % R)
        page.focus("%s.mlbx-caret[data-mlbexpand='%s']" % (R, caret))
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        assert page.evaluate("document.activeElement.getAttribute('data-mlbexpand')") == caret
        assert page.evaluate("document.activeElement.getAttribute('aria-expanded')") == "true"
        page.keyboard.press("Tab")
        assert "eph-csv-btn" not in page.evaluate("document.activeElement.className")
    finally:
        ctx.close()


def test_the_caret_takes_a_44px_tap_under_a_finger(browser, server):
    """QMLA08: the caret was a 9 x 13 px target on every row."""
    ctx = _context(browser, 390, 844, is_mobile=True, has_touch=True)
    try:
        page = ctx.new_page()
        _open(page, server)
        eff = page.evaluate("""() => {
          const el = document.querySelector('.mlbx-caret'); const r = el.getBoundingClientRect();
          const cs = getComputedStyle(el, '::after');
          if (cs.position !== 'absolute') return [r.width, r.height];
          return [r.width - parseFloat(cs.left) - parseFloat(cs.right),
                  r.height - parseFloat(cs.top) - parseFloat(cs.bottom)];
        }""")
        assert eff[0] >= 44 and eff[1] >= 44, eff
    finally:
        ctx.close()
