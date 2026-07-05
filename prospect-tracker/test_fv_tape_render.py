"""FV Tape render guard: the candlestick tape appears on a player page when the
tape flag is set (via ?tape=1, captured to localStorage before the SPA router
rewrites the hash), and is dark by default in a clean context. Skips where
playwright/chromium is unavailable.
"""
import functools
import http.server
import socketserver
import threading
import os

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
PLAYER = "emmanuel_rodriguez"  # 49 consensus points, well over the candle gate


def _serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def test_fv_tape_flag_gating():
    httpd, port = _serve()
    base = f"http://127.0.0.1:{port}/prospx/index.html"
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"chromium unavailable: {e}")

            # Surfaced: on by default in a clean context.
            ctx_on = browser.new_context()
            p1 = ctx_on.new_page()
            errs = []
            p1.on("pageerror", lambda e: errs.append(str(e)))
            p1.goto(f"{base}#player={PLAYER}", wait_until="networkidle", timeout=45000)
            p1.wait_for_timeout(2500)
            on = p1.eval_on_selector_all(".fv-tape", "e => e.length")
            ctx_on.close()

            # ...and ?tape=0 turns it off (fresh context).
            ctx_off = browser.new_context()
            p2 = ctx_off.new_page()
            p2.goto(f"{base}?tape=0#player={PLAYER}", wait_until="networkidle", timeout=45000)
            p2.wait_for_timeout(2500)
            off = p2.eval_on_selector_all(".fv-tape", "e => e.length")
            ctx_off.close()
            browser.close()

            assert on >= 1, "FV Tape should render by default"
            assert off == 0, "FV Tape must hide under ?tape=0"
            assert not errs, f"page errors: {errs[:3]}"
    finally:
        httpd.shutdown()
