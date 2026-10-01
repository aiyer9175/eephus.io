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
