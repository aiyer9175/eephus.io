# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Smoke test for the expanded Prospect News page (/news/) and the homepage
entry points into it.

Mirrors test_glossary_page_loads.py: boots the built static pages in headless
Chromium and asserts the page renders day-grouped feed rows, the type-filter
chips actually hide non-matching rows (and empty day blocks), and the homepage
"Prospect News" section header links to /news/.

The pages under test are the committed build artifacts (news/index.html,
index.html). Playwright is an OPTIONAL dependency; tests skip cleanly without
it."""
from __future__ import annotations

import http.server
import socketserver
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 (matches stdlib sig)
        pass


@pytest.fixture(scope="module")
def server():
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _QuietHandler,
                                            bind_and_activate=False)
    httpd.daemon_threads = True
    httpd.allow_reuse_address = True
    httpd.server_bind()
    httpd.server_activate()
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture(scope="module")
def browser():
    """One chromium per module (was: one launch per test). browser.new_page()
    gives each test a fresh isolated context, so test isolation matches the
    old fresh-browser-per-test behavior."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        yield b
        b.close()


def _browser_page(browser, page_errors):
    page = browser.new_page()
    page.on("pageerror", lambda err: page_errors.append(err.message))
    return page


def test_news_page_renders_and_filters(server, browser):
    if not (ROOT / "news" / "index.html").exists():
        pytest.skip("news/index.html not built")

    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "news/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector("#news-feed .feed-item", timeout=10_000)

        total = page.evaluate("document.querySelectorAll('#news-feed .feed-item').length")
        n_chips = page.evaluate("document.querySelectorAll('[data-news-filter]').length")

        # Click the Trades filter; only trade rows should remain visible, and
        # day blocks with no visible rows must hide. (The 150ms settle stays
        # a fixed wait: hiding rows has no positive DOM signal to
        # condition-wait on without assuming non-trade rows exist.)
        page.click('[data-news-filter="trade"]')
        page.wait_for_timeout(150)
        vis = page.evaluate("""() => {
            const items = [...document.querySelectorAll('#news-feed .feed-item')];
            const visible = items.filter(it => it.style.display !== 'none');
            const days = [...document.querySelectorAll('#news-feed .news-day')];
            return {
                visibleCount: visible.length,
                allTrade: visible.every(it => it.getAttribute('data-cat') === 'trade'),
                visibleDayWithNoRows: days.some(d => d.style.display !== 'none'
                    && [...d.querySelectorAll('.feed-item')].every(it => it.style.display === 'none')),
            };
        }""")
    finally:
        page.close()

    assert not page_errors, "JS errors on /news/:\n  " + "\n  ".join(page_errors)
    assert total >= 20, f"news feed rendered only {total} rows"
    assert n_chips == 7, f"expected 7 filter chips, got {n_chips}"
    assert vis["allTrade"], "Trades filter left non-trade rows visible"
    assert not vis["visibleDayWithNoRows"], "a day block stayed visible with no visible rows"


def test_homepage_news_header_links_to_news(server, browser):
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server, wait_until="load", timeout=15_000)
        href = page.get_attribute('.sb-feed .feed-head a', "href")
        page.click('.sb-feed .feed-head a')
        page.wait_for_url("**/news/**", timeout=10_000)
        url = page.url
    finally:
        page.close()

    assert not page_errors, "JS errors on homepage:\n  " + "\n  ".join(page_errors)
    assert href == "/news/", f"sidebar Prospect News header href was {href!r}"
    assert "/news/" in url, f"clicking the header did not navigate to /news/: {url}"
