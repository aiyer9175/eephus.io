# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ boards fit the screen: the served page, measured in Chromium.

Owner ask 2026-09-11: "make it so that the chart fits on one screen without a
need for horizontal scrolling". Before the column views the reliever and hitter
boards ran 1,424 to 1,900px wide against a 1,352px container and scrolled
sideways at every desktop width. The views (Standard, Skill, Value, Leverage,
Batting, Runs) carry 9 to 13 columns each; All carries every column.

THE BUDGET RULE, asserted on the SERVED page and the served data:
  * the page itself never scrolls sideways, at any width, on any board;
  * every named view (every view but All), qualified filter on and off, fits
    its own table box at 768px and wider, and its phone subset fits at 390px;
  * All fits at 1263px (a 1280 window with a classic 17px scrollbar) and wider;
    narrower, All may scroll inside its own box, never the page;
  * every eWAR column a board carries is visible on its Standard view;
  * a fitted board has no scroll box, so after a long scroll its header sits at
    the top of the viewport (390 and 1440).
A future column that breaks the budget fails here rather than shipping a
sideways scroll. Views are read from the page's own Columns strip, so a view
added later is measured without editing this file.

Every request off loopback is aborted: logos and fonts never load, which the
layout does not depend on (the logo box is sized in CSS and hidden below 1024).
Playwright and chromium are OPTIONAL; the tests skip when they are missing, and
when the boards are not built on this machine.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
BOARD_FILES = ["bullpen_leaderboards.json", "starter_leaderboards.json", "hitter_leaderboards.json",
               "leverage_leaderboards.json", "defense_leaderboards.json"]

# (label, section, hash, qualified-only checkbox id or None)
PAGES = [
    ("relievers", "bullpen", "section=bullpen", "mlbstats-qual"),
    ("starters", "starters", "section=starters", "mlbstats-starter-qual"),
    ("hitters", "hitters", "section=hitters", "mlbstats-hitter-qual"),
    ("defense", "defense", "section=defense", "mlbstats-defense-qual"),
    ("leverage batters", "leverage", "section=leverage", "mlbstats-leverage-qual"),
    ("leverage starters", "leverage", "section=leverage&lview=starters", "mlbstats-leverage-qual"),
    ("team bullpens", "bullpen", "section=bullpen&view=teams", None),
    ("team rotations", "starters", "section=starters&sview=teams", None),
    ("team lineups", "hitters", "section=hitters&hview=teams", None),
    ("team defense", "defense", "section=defense&dview=teams", None),
    ("relievers 2025", "bullpen", "section=bullpen&rseason=2025", None),
    ("starters 2025", "starters", "section=starters&sseason=2025", None),
    ("hitters 2025", "hitters", "section=hitters&hseason=2025", None),
    ("defense 2025", "defense", "section=defense&dseason=2025", None),
]
SIZES = [(390, 844), (768, 1024), (1024, 768), (1280, 800), (1440, 900)]
ALL_FITS_FROM = 1263

_MEASURE = r"""
(sec) => {
  const root = document.getElementById('mlbstats-section-' + sec);
  const sc = root && root.querySelector('.mlbstats-scroll:has(> table.mlbstats-table)');
  if (!sc) return null;
  const t = sc.querySelector('table');
  const shown = (th) => th && getComputedStyle(th).display !== 'none';
  const war = ['war', 'team_war'].map(k => t.querySelector('thead th[data-col="' + k + '"]'))
                                 .filter(Boolean);
  return {
    all: t.classList.contains('mlbstats-cv-all'),
    page_overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    sc_sw: sc.scrollWidth, sc_cw: sc.clientWidth, table_w: t.offsetWidth,
    fit: sc.classList.contains('is-fit'),
    war_hidden: war.filter(th => !shown(th)).map(th => th.getAttribute('data-col')),
    n_visible: Array.from(t.querySelectorAll('thead th')).filter(shown).length,
  };
}
"""
_VIEWS = r"""(sec) => Array.from(document.querySelectorAll('#mlbstats-section-' + sec + ' [data-colview]'))
                          .map(b => b.getAttribute('data-colview'))"""
_STICKY = r"""
(sec) => {
  const root = document.getElementById('mlbstats-section-' + sec);
  const sc = root.querySelector('.mlbstats-scroll:has(> table.mlbstats-table)');
  const th = sc.querySelector('thead th');
  const top = sc.getBoundingClientRect().top + window.scrollY;
  window.scrollTo(0, top + 1500);
  return {fit: sc.classList.contains('is-fit'), th_top: th.getBoundingClientRect().top,
          scrolled: window.scrollY};
}
"""


def _boards_built() -> bool:
    return all((ROOT / "data" / f).exists() for f in BOARD_FILES)


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    if not _boards_built():
        pytest.skip("the /mlbstats/ boards are not built on this machine")
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


def test_the_served_shell_carries_the_mlbx_scope():
    """The fit rules only reach the page through the .mlbx root class, which
    build_site writes into mlbstats/index.html. A stale shell (site.css edited,
    build_site not rerun) serves an unfitted page."""
    shell = (ROOT / "mlbstats" / "index.html").read_text(encoding="utf-8")
    assert 'class="fa-app mlbstats-app mlbx"' in shell, (
        "mlbstats/index.html predates the .mlbx scope: rerun build_site.py")


def _context(browser, w, h):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
    ctx.route(re.compile(r"^(?!http://127\.0\.0\.1:).*"), lambda route: route.abort())
    ctx.add_init_script("try { localStorage.clear(); } catch (e) {}")
    return ctx


def _open(page, server, sec, hash_):
    page.goto("about:blank")
    page.goto(server + "mlbstats/#" + hash_, wait_until="load", timeout=60_000)
    page.wait_for_selector("#mlbstats-section-%s .mlbstats-table" % sec, timeout=30_000)
    page.wait_for_timeout(200)


def _check(m, w, where, problems, all_only=False):
    if m is None:
        problems.append("%s: no board table rendered" % where)
        return
    if m["page_overflow"] > 0:
        problems.append("%s: the PAGE scrolls sideways by %dpx" % (where, m["page_overflow"]))
    fits = m["sc_sw"] <= m["sc_cw"] and m["table_w"] <= m["sc_cw"]
    must_fit = (w >= ALL_FITS_FROM) if m["all"] else (not all_only)
    if must_fit and not fits:
        problems.append("%s: table %dpx does not fit its %dpx box" % (where, m["table_w"], m["sc_cw"]))
    if fits and not m["fit"]:
        problems.append("%s: fits but markFit did not mark it" % where)


@pytest.mark.parametrize("size", SIZES, ids=["%dx%d" % s for s in SIZES])
def test_every_board_and_view_fits_and_the_page_never_scrolls_sideways(browser, server, size):
    w, h = size
    ctx = _context(browser, w, h)
    page = ctx.new_page()
    problems, measured = [], 0
    try:
        for label, sec, hash_, qual in PAGES:
            if "season=" in hash_ and not (ROOT / "data" / (
                    {"bullpen": "bullpen", "starters": "starter", "hitters": "hitter",
                     "defense": "defense"}[sec] + "_history.json")).exists():
                continue
            _open(page, server, sec, hash_)
            views = page.evaluate(_VIEWS, sec) or [None]
            for v in views:
                if v:
                    page.evaluate("(v) => document.querySelector('[data-colview=\"' + v + '\"]').click()", v)
                where = "%dpx %s %s" % (w, label, v.split(":")[1] if v else "(one view)")
                m = page.evaluate(_MEASURE, sec)
                _check(m, w, where, problems)
                measured += 1
                if m and (v is None or v.endswith(":standard")) and m["war_hidden"]:
                    problems.append("%s: eWAR column hidden on the Standard view: %s" % (where, m["war_hidden"]))
                if qual and m and not m["all"]:
                    page.evaluate("(id) => document.getElementById(id).click()", qual)
                    _check(page.evaluate(_MEASURE, sec), w, where + " qualified off", problems)
                    page.evaluate("(id) => document.getElementById(id).click()", qual)
                    measured += 1
    finally:
        ctx.close()
    assert measured >= 30, measured
    assert not problems, "\n".join(problems)


def test_the_all_view_fits_a_1280_window_with_a_classic_scrollbar(browser, server):
    ctx = _context(browser, ALL_FITS_FROM, 800)
    page = ctx.new_page()
    problems = []
    try:
        for label, sec, hash_, _qual in PAGES[:4]:
            _open(page, server, sec, hash_)
            alls = [v for v in page.evaluate(_VIEWS, sec) if v.endswith(":all")]
            assert alls, label
            page.evaluate("(v) => document.querySelector('[data-colview=\"' + v + '\"]').click()", alls[0])
            m = page.evaluate(_MEASURE, sec)
            assert m and m["all"], label
            _check(m, ALL_FITS_FROM, "%dpx %s all" % (ALL_FITS_FROM, label), problems, all_only=True)
    finally:
        ctx.close()
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("size", [(390, 844), (1440, 900)], ids=["390x844", "1440x900"])
def test_a_fitted_board_keeps_its_header_at_the_top_after_a_long_scroll(browser, server, size):
    ctx = _context(browser, *size)
    page = ctx.new_page()
    try:
        for sec in ("bullpen", "hitters"):
            _open(page, server, sec, "section=" + sec)
            r = page.evaluate(_STICKY, sec)
            assert r["fit"], (size, sec, "the Standard board should fit and lose its scroll box")
            assert r["scrolled"] > 0, (size, sec)
            assert abs(r["th_top"]) <= 1, (size, sec, r)
    finally:
        ctx.close()
