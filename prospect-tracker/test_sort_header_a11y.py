# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Sortable table heads announce their sort state (census X06-06, 2026-09-25).

ARIA reads aria-sort only on a columnheader or rowheader. The table boards put
role="button" on the <th>, which replaced its columnheader role, so the
attribute was there and no screen reader heard it (MLB Stats, PAL, Parks, the
Trade Board, Betting); the Ledger league table and the Hall of Fame board had
no aria-sort at all; DFS put it on the span inside the head. The head is now a
<th scope=col tabindex=0 aria-sort> with the module's existing key binder, the
/fa/ and /projections/ contract.

The card boards whose "heads" are <div> sort bars (PROSPX, the fantasy
Redraft, Dynasty and Rest of season cards) are not tables and are not judged
here; they are listed as NEXT in the lane report.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import serve_site

ROOT = Path(__file__).parent
FILES = ("mlbstats.js", "pal.js", "parks.js", "trademachine.js", "betting.js", "hof.js",
         "ledger.js", "dfs.js")


def test_no_table_head_source_pairs_role_button_with_aria_sort():
    for name in FILES:
        src = (ROOT / "assets" / name).read_text(encoding="utf-8")
        assert not re.search(r'role="button" aria-sort', src), name
        assert 'th.setAttribute("role", "button")' not in src, name
        assert "scope" in src and "aria-sort" in src, name


ROUTES = [
    ("mlbstats/", None),
    ("pal/", None),
    ("parks/", None),
    ("hof/", None),
    ("ledger/", None),
    ("trademachine/", "() => { const b = document.querySelector('#proj-view-trademachine [data-collapse-target]');"
                      " if (b && b.getAttribute('aria-expanded') !== 'true') b.click(); }"),
]

_READ = """() => {
  const ths = [...document.querySelectorAll('th[aria-sort], th[tabindex]')]
    .filter(t => t.getBoundingClientRect().width > 0);
  return {
    n: ths.length,
    roleButton: ths.filter(t => t.getAttribute('role') === 'button').length,
    noAria: ths.filter(t => !t.hasAttribute('aria-sort')).length,
    noScope: ths.filter(t => t.getAttribute('scope') !== 'col').length,
    active: ths.filter(t => /ascending|descending/.test(t.getAttribute('aria-sort') || '')).length,
    innerAria: document.querySelectorAll('th [aria-sort]').length};
}"""


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@pytest.mark.parametrize("route,pre", ROUTES, ids=[r[0] for r in ROUTES])
def test_rendered_sort_heads_are_columnheaders_with_aria_sort(server, route, pre):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(server + route, wait_until="networkidle", timeout=90_000)
            if pre:
                page.evaluate(pre)
            try:
                page.wait_for_function("() => document.querySelectorAll('th[aria-sort]').length > 0",
                                       timeout=30_000)
            except Exception:  # noqa: BLE001
                pytest.skip(route + " painted no sortable table on this machine's data")
            got = page.evaluate(_READ)
        finally:
            browser.close()
    assert got["n"] > 0, got
    assert got["roleButton"] == 0, got
    assert got["noAria"] == 0, got
    assert got["noScope"] == 0, got
    assert got["active"] >= 1, got
    assert got["innerAria"] == 0, got
