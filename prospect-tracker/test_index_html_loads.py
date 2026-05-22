"""Launch smoke test — boots `index.html` in headless Chromium and
asserts the boot IIFE actually runs (no JS parse errors, the loading
placeholder gets replaced with rendered content).

The previous QA round shipped a JS `SyntaxError` (stray `\\'` inside a
single-quoted glossary tooltip) that none of the existing tests caught —
they validated the data layer and HTML well-formedness but never
actually executed the JS. This test closes that gap.

Playwright is an OPTIONAL dependency; the test skips cleanly when it
or its chromium browser is not installed."""
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
    httpd = socketserver.TCPServer(("127.0.0.1", 0), _QuietHandler,
                                   bind_and_activate=False)
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


def test_page_boots_without_js_errors(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    page_errors: list[str] = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        page.on("pageerror", lambda err: page_errors.append(err.message))
        page.goto(server, wait_until="load", timeout=15_000)
        page.wait_for_timeout(2500)  # let async boot IIFE finish
        content_html = page.evaluate(
            "document.getElementById('content').innerHTML"
        )
        browser.close()

    assert not page_errors, (
        "JS errors thrown on load:\n  " + "\n  ".join(page_errors)
    )
    assert "Loading prospect data" not in content_html, (
        "Boot IIFE never finished — #content still shows the placeholder. "
        "Likely a JS error before the fetch."
    )
