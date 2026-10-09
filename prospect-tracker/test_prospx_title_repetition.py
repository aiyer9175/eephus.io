# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Copy lint rule L11 on the rendered PROSPX board and Debuted tab (COPY_3_PROSPX).

A definition belongs once: in the column header and the Library entry. A row's
tooltip carries that row's numbers. Before COPY_3 the eFV V2 method sentence sat on
1,996 graded badge tooltips and the V1 'Reads a 6-yr WAR outcome mix' tail on 7,519,
and the first rendered page carried 101 copies of the Star Odds definition and 150
of the eFV tail on Debuted.

The check, at 1280 px in light: split every title attribute into sentences (on
. ! ? followed by space, on ' · ' and on newlines), replace digit runs with 0 as
tools/copy_lint.normalise does, keep sentences of 12 or more words under
copy_lint.WORDS, and fail when one of them appears in more than 20 titles.
"""
from __future__ import annotations

import pytest
from conftest import serve_site

MAX_REPEAT = 20
MIN_WORDS = 12

_COUNT_JS = r"""
([minWords, maxRepeat]) => {
  const cnt = new Map();
  for (const el of document.querySelectorAll('[title]')) {
    const seen = new Set();
    for (let s of (el.getAttribute('title') || '').split(/(?<=[.!?])\s+|\s·\s|\n/)) {
      s = s.trim().replace(/\d+/g, '0');
      if ((s.match(/[A-Za-z][A-Za-z'+%-]*/g) || []).length < minWords || seen.has(s)) continue;
      seen.add(s);
      cnt.set(s, (cnt.get(s) || 0) + 1);
    }
  }
  return [...cnt.entries()].filter(e => e[1] > maxRepeat).sort((a, b) => b[1] - a[1]);
}
"""


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@pytest.mark.parametrize("route,row", [
    ("prospx/", ".player-row[data-key]"),
    ("prospx/#tab=debuts", ".debut-row[data-key]"),
])
def test_no_long_sentence_repeats_across_row_tooltips(server, route, row):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.add_init_script("localStorage.setItem('prospect-tracker.theme', 'light')")
            page.goto(server + route, wait_until="networkidle", timeout=120_000)
            page.wait_for_selector(row, timeout=60_000)
            page.wait_for_timeout(2500)
            n_rows = page.evaluate("(sel) => document.querySelectorAll(sel).length", row)
            assert n_rows >= 20, f"{route}: only {n_rows} rows rendered, too few to test"
            hits = page.evaluate(_COUNT_JS, [MIN_WORDS, MAX_REPEAT])
            assert not hits, (
                f"{route}: {len(hits)} sentence(s) of {MIN_WORDS}+ words repeat in more than "
                f"{MAX_REPEAT} title attributes; move the definition to the column header. "
                f"Top: {hits[:3]}")
        finally:
            browser.close()
