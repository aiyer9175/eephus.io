# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The flagship board must actually paint players, not just its chrome.

WHY THIS EXISTS. On 2026-08-06 a hand check of /prospx/ reported zero rows after
25 seconds, with every JSON fetched 200 and no JS errors. It looked like the
flagship board was serving nothing. It was not: the board is a CARD GRID that
fills `#rows`, and the probe was counting `tbody tr`. The real count was 53
elements under `#rows`, reading "Showing 1-50 of 10569".

That was the FOURTH false "dead section" alarm in one session, every one of them
the same mistake: a probe that assumes a table. One of the earlier three nearly
caused a working module to be reverted.

The gap that let it keep happening is that nothing asserted rows. test_prospx_sort_a11y
drives this same page but only checks headers, which are chrome and render with or
without data, so a genuinely empty board would pass it.

So this test asserts the thing a reader cares about: players are on the page. It
is deliberately written against SEVERAL possible unit selectors and a text
signature, so a layout change makes it fail loudly rather than pass vacuously on
a selector that no longer matches anything.
"""
from __future__ import annotations

import re

import pytest
from conftest import serve_site


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def test_the_board_paints_player_rows(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        errs: list[str] = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        try:
            page.goto(server + "prospx/index.html", wait_until="load", timeout=60_000)
            # The board loads a 74MB timeseries; be generous, and wait on the
            # CONDITION rather than a fixed sleep.
            try:
                page.wait_for_function(
                    "() => { const r = document.getElementById('rows');"
                    " return !!r && r.children.length > 3; }",
                    timeout=60_000)
            except Exception:
                pass          # let the assertions below report the real state

            container = page.query_selector("#rows")
            assert container is not None, (
                "#rows is missing entirely; the board's row container has been "
                "renamed and this test needs updating with the new one")

            n = page.eval_on_selector_all("#rows > *", "els => els.length")
            text = page.inner_text("#rows")

            assert n > 3, (
                f"#rows holds {n} children, so the flagship board is painting "
                "chrome and no players. Every JSON can fetch 200 and the page "
                "can be error-free while this is true, which is exactly how it "
                "would ship unnoticed.")

            # A count alone can be satisfied by pagination furniture, so require
            # the page to say how many players it is showing.
            m = re.search(r"Showing\s+[\d,]+\s*-\s*[\d,]+\s+of\s+([\d,]+)", text)
            assert m, (
                "the board renders rows but no 'Showing X-Y of N' line; either "
                "the pager changed or those children are furniture rather than "
                f"players. First 200 chars: {text[:200]!r}")
            total = int(m.group(1).replace(",", ""))
            assert total > 1000, (
                f"the board reports only {total} tracked players, which is far "
                "below the expected board size; a join has probably collapsed")

            assert not errs, "JS errors while painting the board:\n  " + "\n  ".join(errs)
        finally:
            browser.close()
