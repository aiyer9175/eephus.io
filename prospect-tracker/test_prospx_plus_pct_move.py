# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PLUS% left the PROSPX board for the player page (owner answer M29-1, 2026-09-30).

PLUS% (surplus.opt_pct) is a lookup on the consensus FV tier and role: 11 distinct
values over 4,686 board rows, a dash on every provisional row, and a tier cliff that
reads as a real gap between two neighbours (a hitter at consensus 47.4 printed 60%,
one at 47.5 printed -6%). It is now a line on the player page's eFV card, under Star
Odds, where the tooltip names the tier it is read at. The board CSV keeps plus_pct.

Pinned here:
  1. the board carries no PLUS% track, header, cell, flag or sort key, while the
     formatter and the CSV column stay;
  2. the board header has 8 grid children and the rows resolve the same tracks;
  3. a saved #sort=opt_pct&srev=sort link lands on the default eFV order, not on an
     unsorted pool (the sort lives only in the hash, and an unknown key used to
     leave the board in merge order with no active header);
  4. the player page prints the PLUS% line with the value fmtOptPct gives;
  5. #starodds=0 survives boot. It did not: syncToURL rebuilt the hash before the
     board settled and dropped the key, so the column painted anyway.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when unavailable.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
PAGE = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")

WAIT_ROWS = ("() => { const r = document.getElementById('rows');"
             " return !!r && r.querySelectorAll('.player-row[data-key]').length > 10"
             " && !!r.querySelector('.col-header'); }")


# ------------------------------------------------------------------ static

def test_board_carries_no_plus_pct_column():
    for gone in ("has-opt-pct", 'data-sort-key="opt_pct"', "makeOptPctCell(",
                 "_optPctShow(", "_optPctUiOn(", "OPT_PCT_DEFAULT"):
        assert gone not in PAGE, f"prospx/index.html still carries {gone!r}"
    assert "function fmtOptPct" in PAGE, "the PLUS% formatter must stay for the player page"
    assert "function optPctColor" in PAGE


def test_opt_pct_left_the_internal_direction_sorts():
    m = re.search(r"const _INTERNAL_DIR_MAIN_SORTS = new Set\(\[(.*?)\]\);", PAGE, re.S)
    assert m, "_INTERNAL_DIR_MAIN_SORTS not found"
    keys = set(re.findall(r'"([a-z_]+)"', m.group(1)))
    assert "opt_pct" not in keys
    assert "fv" in keys and "star_odds" in keys
    assert 'state.sort === "opt_pct") {\n    // OPT%' not in PAGE


def test_board_csv_keeps_plus_pct():
    m = re.search(r"BOARD_CSV_HEADERS\s*=\s*\[(.*?)\];", PAGE, re.S)
    assert m, "BOARD_CSV_HEADERS not found"
    assert '"plus_pct"' in m.group(1)
    assert "num(s.opt_pct, 4)" in PAGE


def test_saved_sort_link_is_migrated_in_the_url_reader():
    body = PAGE[PAGE.index("function _syncFromURLBody()"):]
    body = body[:body.index("\nfunction ")]
    srev = body.index('if (p.has("srev"))')
    mig = body.index('if (state.sort === "opt_pct") { state.sort = "xfv"; delete state.sortRev.sort; }')
    assert mig > srev, "the migration must run after the srev restore, or the flag survives it"


def test_star_odds_flag_is_latched_at_boot():
    assert "const _STAR_ODDS_BOOT = (() => {" in PAGE
    fn = PAGE[PAGE.index("function _starOddsUiOn()"):]
    fn = fn[:fn.index("\n}") + 2]
    assert "return _STAR_ODDS_BOOT;" in fn


# ----------------------------------------------------------------- browser

@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def _open(p, server, url, width=1440, height=1000):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": height})
    errs: list[str] = []
    page.on("pageerror", lambda e: errs.append(str(e)[:200]))
    page.goto(server + url, wait_until="load", timeout=120_000)
    return browser, page, errs


def test_board_header_has_eight_children_and_no_plus_pct(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page, errs = _open(p, server, "prospx/")
        try:
            page.wait_for_function(WAIT_ROWS, timeout=120_000)
            page.wait_for_timeout(2000)
            m = page.evaluate("""() => {
              const h = document.querySelector('#rows .col-header');
              const rows = [...document.querySelectorAll('#rows .player-row[data-key]')];
              const n = el => getComputedStyle(el).gridTemplateColumns.split(' ').length;
              return { kids: h.children.length, text: h.textContent, cls: h.className,
                       hdrTracks: n(h), rowTracks: [...new Set(rows.map(n))] };
            }""")
            assert m["kids"] == 8, f"board header has {m['kids']} children: {m['text'][:200]!r}"
            assert "PLUS%" not in m["text"]
            assert "has-opt-pct" not in m["cls"]
            assert m["rowTracks"] == [m["hdrTracks"]] == [8], m
            assert not errs, errs
        finally:
            browser.close()


def test_saved_plus_pct_sort_link_lands_on_the_efv_order(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page, errs = _open(p, server, "prospx/#sort=opt_pct&srev=sort")
        try:
            page.wait_for_function(WAIT_ROWS, timeout=120_000)
            page.wait_for_timeout(2500)
            m = page.evaluate("""() => {
              const h = document.querySelector('#rows .col-header [data-sort-key="xfv"]');
              const r = document.querySelector('#rows .player-row[data-key] .rank-num-inner');
              const sr = h && h.querySelector('.sort-header-sr');
              return { sort: state.sort, rev: !!(state.sortRev && state.sortRev.sort),
                       hash: location.hash, active: !!(h && h.classList.contains('is-active')),
                       pressed: h && h.getAttribute('aria-pressed'), sr: sr ? sr.textContent : null,
                       first: r ? r.textContent.trim() : null };
            }""")
            assert not errs, errs
            assert m["sort"] == "xfv" and m["rev"] is False, m
            assert "opt_pct" not in m["hash"] and "srev" not in m["hash"], m
            assert m["active"] and m["pressed"] == "true", m
            assert m["sr"] == ", sorted descending", m
            assert m["first"] == "#1", m
        finally:
            browser.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_player_page_prints_the_plus_pct_line(server, theme):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 1200})
            page.add_init_script("localStorage.setItem('prospect-tracker.theme', %r)" % theme)
            errs: list[str] = []
            page.on("pageerror", lambda e: errs.append(str(e)[:200]))
            page.goto(server + "prospx/", wait_until="load", timeout=120_000)
            page.wait_for_function(WAIT_ROWS, timeout=120_000)
            page.wait_for_timeout(2500)
            # The first board row whose player carries both an eFV record (the card
            # renders only then) and surplus.opt_pct.
            key = page.evaluate("""() => {
              const ks = [...document.querySelectorAll('#rows .player-row[data-key]')].map(r => r.dataset.key);
              const by = Object.fromEntries((DATA.players || []).map(q => [q.player_key, q]));
              const ok = q => q && q.surplus && q.surplus.opt_pct != null
                && getEfv(q) && getEfv(q).xfv_grade != null;
              return ks.find(k => ok(by[k])) || null;
            }""")
            assert key, "no first-page board row carries surplus.opt_pct"
            # A fresh load of the deep link, the way a reader opens a shared player URL.
            page.goto(server + "prospx/index.html#player=" + key, wait_until="load", timeout=120_000)
            page.wait_for_selector(".efv-plus-line", state="attached", timeout=90_000)
            m = page.evaluate("""(k) => {
              const l = document.querySelector('.efv-plus-line');
              const p = DATA.players.find(q => q.player_key === k);
              const card = l.closest('.detail-card');
              return { val: l.querySelector('.efv-plus-val').textContent.trim(),
                       want: fmtOptPct(p.surplus.opt_pct), text: l.textContent,
                       title: l.getAttribute('title') || '',
                       inEfvCard: !!(card && /eFV/.test(card.querySelector('.detail-title').textContent)) };
            }""", key)
            assert m["val"] == m["want"], m
            assert "PLUS%" in m["text"] and m["inEfvCard"], m
            assert "consensus FV tier" in m["title"], m
            assert not errs, errs
        finally:
            browser.close()


@pytest.mark.parametrize("url", ["prospx/#starodds=0", "prospx/?starodds=0"])
def test_star_odds_off_switch_survives_boot(server, url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser, page, errs = _open(p, server, url)
        try:
            page.wait_for_function(WAIT_ROWS, timeout=120_000)
            page.wait_for_timeout(4000)
            page.evaluate("() => renderActives()")
            page.wait_for_timeout(500)
            m = page.evaluate("""() => { const h = document.querySelector('#rows .col-header');
              return { cls: h.className, star: /Star Odds/.test(h.textContent), hash: location.hash }; }""")
            assert not m["star"] and "has-star-odds" not in m["cls"], (
                f"{url}: the Star Odds column painted after boot ({m})")
            assert not errs, errs
        finally:
            browser.close()
