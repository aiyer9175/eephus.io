# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Two served /mlbstats/ defects, measured on the served page in Chromium
(final pass Part 8, league_team_stats lane section 1.7).

1. The row number. site.css numbers the board rows with a CSS counter that
   steps on every tbody tr, and the Overall caret inserts a tr.mlbx-seasonrow
   under the player it opens. Before the fix, opening the first player's
   season line made the second player print 3. The counter is generated
   content, so the test reads what CSS reads: each row's computed
   counter-increment, summed in document order.
2. The chart labels. EEPHUS_HUB.histogram and scatter draw on a viewBox that
   the SVG scales to its cell, and every /mlbstats/ chart used the default
   640-unit box, so at 390 (a 306px cell) a 9-unit label drew 5px tall.
   mlbstats.js now hands each chart a viewBox as wide as its cell. Every
   chart on every Charts panel at 390 must draw its first label 8px or taller.

Every request off loopback is aborted. Playwright and chromium are OPTIONAL;
the tests skip when they are missing, and when the boards are not built here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
WAR_FILE = "war_leaderboards.json"
BOARD_FILES = ["bullpen_leaderboards.json", "starter_leaderboards.json", "hitter_leaderboards.json",
               "leverage_leaderboards.json", "defense_leaderboards.json"]
# (label, hash, collapse key of its Charts panel): every surface that draws a hub chart.
CHART_PAGES = [
    ("bullpen", "section=bullpen", "relievers-viz"),
    ("starters", "section=starters&sview=charts", "starters-viz"),
    ("hitters", "section=hitters&hview=charts", "hitters-viz"),
    ("leverage batters", "section=leverage", "leverage-viz"),
    ("leverage starters", "section=leverage&lview=starters", "leverage-viz"),
    ("defense", "section=defense&dview=charts", "defense-viz"),
]
MIN_LABEL_PX = 8

# The rank each of the first rows prints: a row adds its counter-increment to
# the running count, and a player row (it carries td.mlbstats-name) prints the
# count, which is how the CSS counter on td.mlbstats-name::before resolves.
_RANKS = r"""
() => {
  const tb = document.querySelector('#mlbstats-section-war .mlbstats-table tbody');
  let n = 0; const out = [];
  Array.from(tb.querySelectorAll(':scope > tr')).slice(0, 6).forEach(tr => {
    const inc = getComputedStyle(tr).counterIncrement;
    const m = /mlbx-rank\s+(-?\d+)/.exec(inc || '');
    n += m ? Number(m[1]) : 0;
    const name = tr.querySelector('td.mlbstats-name');
    out.push({season: tr.classList.contains('mlbx-seasonrow'), inc: inc,
              rank: name ? n : null});
  });
  return out;
}
"""


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
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


def _context(browser, w, h, init=""):
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
    ctx.route(re.compile(r"^(?!http://127\.0\.0\.1:).*"), lambda route: route.abort())
    ctx.add_init_script("try { localStorage.clear(); %s } catch (e) {}" % init)
    return ctx


def test_the_season_rule_takes_no_rank_in_site_css():
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    assert ".mlbx .mlbstats-table tbody tr.mlbx-seasonrow { counter-increment: none; }" in css


def test_opening_the_overall_caret_keeps_the_next_player_at_rank_2(browser, server):
    if not (ROOT / "data" / WAR_FILE).exists():
        pytest.skip("data/%s is not built on this machine" % WAR_FILE)
    ctx = _context(browser, 1280, 800)
    try:
        page = ctx.new_page()
        page.goto(server + "mlbstats/", wait_until="load", timeout=60_000)
        page.wait_for_selector(".mlbx-caret", timeout=30_000)
        closed = page.evaluate(_RANKS)
        assert [r["rank"] for r in closed[:3]] == [1, 2, 3], closed
        page.locator(".mlbx-caret").first.click()
        page.wait_for_selector("tr.mlbx-seasonrow", timeout=10_000)
        opened = page.evaluate(_RANKS)
        assert opened[1]["season"], opened
        assert opened[1]["inc"] == "none", (
            "the season line steps the rank counter: %s" % opened[1]["inc"])
        ranks = [r["rank"] for r in opened if r["rank"] is not None]
        assert ranks[:4] == [1, 2, 3, 4], (
            "with the first player's season line open the board prints %s" % ranks[:4])
    finally:
        ctx.close()


def _drawer_live() -> bool:
    """The served shell names the drawer script (MLBSTATS_DRAWER_LIVE) and the
    drawer's trend file is on disk."""
    shell = (ROOT / "mlbstats" / "index.html").read_text(encoding="utf-8")
    return "data-drawer-src=" in shell and (ROOT / "data" / "mlbstats_trends.json").exists()


_DRAWER = r"""
() => {
  const tb = document.querySelector('#mlbstats-section-hitters .mlbstats-table tbody');
  const dr = tb.querySelector('tr.mlbx-drawer');
  if (!dr) return null;
  let n = 0, before = null, after = null;
  for (const tr of Array.from(tb.rows).filter(r => !r.hidden)) {
    const m = /mlbx-rank\s+(-?\d+)/.exec(getComputedStyle(tr).counterIncrement || '');
    n += m ? Number(m[1]) : 0;
    if (tr === dr.previousElementSibling) before = n;
    else if (before != null && tr !== dr && tr.querySelector('td.mlbstats-name')) { after = n; break; }
  }
  const hs = [];
  dr.querySelectorAll('svg.eephus-chart text').forEach(t => { const h = t.getBoundingClientRect().height; if (h) hs.push(h); });
  return {inc: getComputedStyle(dr).counterIncrement, before: before, after: after,
          hl: dr.previousElementSibling.classList.contains('mlbx-hl'), drawers: document.querySelectorAll('tr.mlbx-drawer').length,
          hash: location.hash, min_label: hs.length ? Math.min.apply(null, hs) : null,
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}
"""


def test_the_drawer_row_takes_no_rank_in_site_css():
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    assert ".mlbx .mlbstats-table tbody tr.mlbx-drawer { counter-increment: none; }" in css


@pytest.mark.parametrize("size", [(390, 844), (1280, 800)], ids=["390", "1280"])
def test_a_deep_linked_drawer_opens_highlights_its_row_and_takes_no_rank(browser, server, size):
    """#player= opens the board, pages to the row, highlights it and opens
    ONE drawer under it; the drawer row is not a player, so the next player
    keeps the next rank. Skipped, never failed, while the drawer is dark."""
    if not _drawer_live():
        pytest.skip("the player drawer is dark in this build")
    ctx = _context(browser, *size)
    try:
        page = ctx.new_page()
        page.goto(server + "mlbstats/#section=hitters&player=665742", wait_until="load", timeout=60_000)
        page.wait_for_selector("#mlbstats-section-hitters tr.mlbx-drawer svg.eephus-chart", timeout=30_000)
        m = page.evaluate(_DRAWER)
    finally:
        ctx.close()
    assert m and m["inc"] == "none", m
    assert m["after"] == m["before"] + 1, m
    assert m["hl"] and m["drawers"] == 1 and "player=665742" in m["hash"], m
    assert m["overflow"] <= 0, m
    assert m["min_label"] is None or m["min_label"] >= MIN_LABEL_PX, m


_LABELS = r"""
() => Array.from(document.querySelectorAll('.mlbx svg.eephus-chart'))
  .filter(s => s.getBoundingClientRect().width > 0)
  .map(s => {
    const t = s.querySelector('text');
    return {aria: s.getAttribute('aria-label'), css_w: s.getBoundingClientRect().width,
            viewbox: s.getAttribute('viewBox'),
            first_label_px: t ? t.getBoundingClientRect().height : null};
  })
"""


def test_every_chart_at_390_draws_its_first_label_8px_or_taller(browser, server):
    if not all((ROOT / "data" / f).exists() for f in BOARD_FILES):
        pytest.skip("the /mlbstats/ boards are not built on this machine")
    opened = "".join("localStorage.setItem('mlbstats.collapse.%s', '0');" % k
                     for k in sorted({c for _, _, c in CHART_PAGES}))
    ctx = _context(browser, 390, 844, opened)
    problems, measured = [], 0
    try:
        for label, hash_, _ in CHART_PAGES:
            page = ctx.new_page()
            page.goto(server + "mlbstats/#" + hash_, wait_until="load", timeout=60_000)
            page.wait_for_selector(".mlbx svg.eephus-chart", timeout=30_000)
            charts = page.evaluate(_LABELS)
            if not charts:
                problems.append("%s: no chart drawn" % label)
            for c in charts:
                measured += 1
                px = c["first_label_px"]
                if px is None or px < MIN_LABEL_PX:
                    problems.append("%s / %s: first label %s px in a %.0f px chart (viewBox %s)"
                                    % (label, c["aria"], px, c["css_w"], c["viewbox"]))
            page.close()
    finally:
        ctx.close()
    assert measured >= len(CHART_PAGES), measured
    assert not problems, "\n".join(problems)
