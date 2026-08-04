"""FV Tape render guard: the candlestick tape appears on a player page when the
tape flag is set (via ?tape=1, captured to localStorage before the SPA router
rewrites the hash), and is dark by default in a clean context. Skips where
playwright/chromium is unavailable.
"""
import os

import pytest
from conftest import make_static_server

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
PLAYER = "emmanuel_rodriguez"  # 49 consensus points, well over the candle gate


def _serve():
    """Shared harness (conftest.make_static_server): HTTP/1.1 + threaded.

    Was a single-threaded TCPServer on the stdlib HTTP/1.0 default. Both
    were wrong: HTTP/1.0 signals end-of-body by closing the socket, which
    on Windows races the send buffer and truncates a large asset
    (assets/site.css, 211KB) so page.goto hangs to timeout; and once
    HTTP/1.1 keep-alive is on, a single-threaded server deadlocks on the
    browser's parallel connections. See conftest._QuietHTTP."""
    return make_static_server(ROOT)


def test_fv_tape_flag_gating():
    httpd, port = _serve()
    base = f"http://127.0.0.1:{port}/prospx/index.html"
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"chromium unavailable: {e}")

            # The tape renders inside the same template string as the player
            # page's "FV history" .detail-title (see makeFvTape's call site
            # in prospx/index.html), so once any .detail-title exists the
            # .fv-tape count is final - a deterministic signal for BOTH the
            # on and off cases, replacing the old fixed 2.5s sleeps.
            # Timeouts are swallowed so the assertions report the failure.
            def _wait_player_rendered(pg):
                try:
                    pg.wait_for_selector(".detail-title", timeout=30000)
                except Exception:
                    pass

            # Surfaced: on by default in a clean context.
            ctx_on = browser.new_context()
            p1 = ctx_on.new_page()
            errs = []
            p1.on("pageerror", lambda e: errs.append(str(e)))
            p1.goto(f"{base}#player={PLAYER}", wait_until="networkidle", timeout=45000)
            _wait_player_rendered(p1)
            on = p1.eval_on_selector_all(".fv-tape", "e => e.length")
            ctx_on.close()

            # ...and ?tape=0 turns it off (fresh context).
            ctx_off = browser.new_context()
            p2 = ctx_off.new_page()
            p2.goto(f"{base}?tape=0#player={PLAYER}", wait_until="networkidle", timeout=45000)
            _wait_player_rendered(p2)
            off = p2.eval_on_selector_all(".fv-tape", "e => e.length")
            ctx_off.close()
            browser.close()

            assert on >= 1, "FV Tape should render by default"
            assert off == 0, "FV Tape must hide under ?tape=0"
            assert not errs, f"page errors: {errs[:3]}"
    finally:
        httpd.shutdown()
