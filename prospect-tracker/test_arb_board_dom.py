# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/arbitration/ Projections board, read in a browser (census X06-04, X06-05).

The board was the least interactive large table on the site: pinned to total
remaining, no column sort, no name search across 853 rows, and every name was
dead text although all 853 MLBAM ids resolve through player_links. Now the
heads are <th scope=col aria-sort> around native buttons, a name search narrows
the table without dropping focus, the sort rides the hash, and each name opens
the player's projections page (or his PROSPX card when he has no projections
page).

Since 2026-10-03 (QCLP04) the exporter writes each row's link token, so the
page no longer fetches the 1.9 MB player_links map, and the board paints 100
rows at a time with Show more and Show all.
"""
from __future__ import annotations

import unicodedata

import pytest

from conftest import load_data_doc, serve_site


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


PAGE = 100


def _board():
    board = load_data_doc("arbitration.json")
    links = load_data_doc("player_links.json")
    if not board or not board.get("rows") or not links:
        pytest.skip("arbitration.json or player_links.json not built")
    return board, links


def _fold(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _expected_hrefs(board, links):
    """The identity map's answer for each name, the rule the page applied to
    player_links before the exporter took it over; the row's token must agree."""
    by = links.get("byMlbam") or {}
    out = {}
    for r in board["rows"]:
        e = by.get(str(r.get("m")))
        if not e:
            continue
        proj = bool(e.get("key")) if e.get("proj") is None else e.get("proj")
        if proj and e.get("key"):
            out[r["n"]] = "/projections/#player=" + e["key"]
        elif e.get("prospx"):
            out[r["n"]] = "/prospx/#player=" + e["prospx"]
    return out


def _token_href(tok):
    tok = tok or ""
    if tok.startswith("p:"):
        return "/projections/#player=" + tok[2:]
    if tok.startswith("x:"):
        return "/prospx/#player=" + tok[2:]
    return None


_READ = """() => {
  const t = document.querySelector('#arb-panel-projections table.arb-table');
  const heads = [...t.querySelectorAll('thead th')].map(th => ({
    sort: th.getAttribute('aria-sort'), scope: th.getAttribute('scope'),
    role: th.getAttribute('role'), btn: !!th.querySelector('button[data-asort]'),
    key: th.querySelector('button[data-asort]') ? th.querySelector('button[data-asort]').getAttribute('data-asort') : null}));
  const rows = [...t.querySelectorAll('tbody tr')].map(tr => {
    const td = tr.querySelectorAll('td'); const a = td[1].querySelector('a');
    return {name: td[1].textContent.trim(), href: a ? a.getAttribute('href') : null,
            club: td[2].textContent.trim(), tot: td[6].textContent.trim()};
  });
  return {heads, rows, count: (document.getElementById('arb-count') || {}).textContent || '',
          hash: location.hash, active: document.activeElement && document.activeElement.id};
}"""


def _open(p, url, fetched=None):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    if fetched is not None:
        page.on("request", lambda r: fetched.append(r.url))
    page.goto(url, wait_until="networkidle", timeout=60_000)
    page.wait_for_selector("#arb-panel-projections tbody tr", timeout=30_000)
    page.wait_for_function("() => document.querySelector('#arb-panel-projections tbody td a') !== null",
                           timeout=30_000)
    return browser, page


def test_names_link_and_heads_carry_aria_sort(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    board, links = _board()
    want = _expected_hrefs(board, links)
    n = len(board["rows"])
    # the exporter's token agrees with the identity map on every row
    assert {r["n"]: _token_href(r.get("h")) for r in board["rows"] if r.get("h")} == want
    fetched = []
    with sync_playwright() as p:
        browser, page = _open(p, server + "arbitration/", fetched)
        try:
            first = page.evaluate(_READ)
            page.click('[data-amore="all"]')
            got = page.evaluate(_READ)
        finally:
            browser.close()
    assert not [u for u in fetched if "player_links" in u], "the board fetched the identity map"
    assert len(first["rows"]) == min(PAGE, n)
    assert first["count"] == "Showing %d of %d players." % (min(PAGE, n), n)
    rows = got["rows"]
    assert len(rows) == n
    linked = {r["name"]: r["href"] for r in rows if r["href"]}
    assert len(linked) == len(want) and len(want) >= 800, (len(linked), len(want))
    for name, href in want.items():
        assert linked.get(name) == href, name
    sortable = [h for h in got["heads"] if h["btn"]]
    assert [h["key"] for h in sortable] == ["n", "t", "c", "yl", "next", "tot"]
    for h in got["heads"]:
        assert h["scope"] == "col" and h["role"] is None
    for h in sortable:
        assert h["sort"] in ("ascending", "descending", "none")
    assert [h["sort"] for h in sortable if h["sort"] != "none"] == ["descending"]
    assert sortable[-1]["sort"] == "descending"  # total remaining, the default
    assert got["count"] == "Showing %d of %d players." % (n, n)


def test_keyboard_sort_flips_aria_sort_and_reorders(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    board, _ = _board()
    names = sorted((r["n"] for r in board["rows"]), key=_fold)
    with sync_playwright() as p:
        browser, page = _open(p, server + "arbitration/")
        try:
            page.focus('[data-asort="n"]')
            page.keyboard.press("Enter")
            asc = page.evaluate(_READ)
            focused = page.evaluate("() => document.activeElement.getAttribute('data-asort')")
            page.keyboard.press("Enter")
            desc = page.evaluate(_READ)
        finally:
            browser.close()
    assert focused == "n"
    head = {h["key"]: h["sort"] for h in asc["heads"] if h["key"]}
    assert head["n"] == "ascending" and head["tot"] == "none"
    assert [_fold(r["name"]) for r in asc["rows"][:25]] == [_fold(n) for n in names[:25]]
    assert asc["hash"] == "#projections&sort=n.a"
    head = {h["key"]: h["sort"] for h in desc["heads"] if h["key"]}
    assert head["n"] == "descending"
    assert _fold(desc["rows"][0]["name"]) == _fold(names[-1])
    assert desc["hash"] == "#projections&sort=n.d"


def test_sort_hash_restores_and_search_narrows(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    board, _ = _board()
    target = next(r for r in board["rows"] if r["n"] == "Paul Skenes")
    with sync_playwright() as p:
        browser, page = _open(p, server + "arbitration/#projections&sort=t.a")
        try:
            restored = page.evaluate(_READ)
            page.click("#arb-q")
            page.keyboard.type("skenes", delay=20)
            page.wait_for_timeout(200)
            found = page.evaluate(_READ)
            page.fill("#arb-q", "zzzz-no-such-player")
            page.wait_for_timeout(200)
            empty = page.evaluate("() => !!document.getElementById('arb-clear')")
            page.click("#arb-clear")
            page.wait_for_timeout(200)
            cleared = page.evaluate(_READ)
        finally:
            browser.close()
    head = {h["key"]: h["sort"] for h in restored["heads"] if h["key"]}
    assert head["t"] == "ascending"
    clubs = [r["club"] for r in restored["rows"] if r["club"] not in ("", "-")]
    assert clubs == sorted(clubs)
    assert [r["name"] for r in found["rows"]] == [target["n"]]
    assert found["active"] == "arb-q"
    assert found["count"] == "Showing 1 of %d players." % len(board["rows"])
    assert empty
    assert len(cleared["rows"]) == min(PAGE, len(board["rows"]))
