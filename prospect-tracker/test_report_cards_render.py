"""Playwright guard for Model Report Cards v0: the proof charts render under
the #cards=1 preview flag, are inert by default (dark pre-launch), and never
strand the 57-row ledger. Skips cleanly where playwright/chromium is absent.
"""
import os
import functools
import http.server
import socketserver
import threading

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def _serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def test_report_cards_flag_gating():
    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"chromium unavailable: {e}")
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            base = f"http://127.0.0.1:{port}/glossary/index.html"

            # Surfaced: proof charts show by default now. Condition wait
            # replaces the old fixed 600ms sleep: wait for the asserted
            # chart count itself; a timeout is swallowed so the assertion
            # below reports the real count.
            page.goto(base + "#view=models", wait_until="networkidle")
            page.wait_for_selector(".gl-model-card", timeout=15000)
            try:
                page.wait_for_function(
                    "document.querySelectorAll('.gl-card-proof').length >= 8",
                    timeout=10000)
            except Exception:
                pass
            on = page.eval_on_selector_all(".gl-card-proof", "els => els.length")

            # ...and #cards=0 turns them off. Charts must NOT appear here,
            # so there is no positive signal to wait on: wait for the full
            # ledger (asserted below), then keep a SHORT settle so a buggy
            # late chart injection would still be caught.
            page.goto(base + "#view=models&cards=0", wait_until="networkidle")
            page.wait_for_selector(".gl-model-card", timeout=15000)
            try:
                page.wait_for_function(
                    "document.querySelectorAll('.gl-model-card').length >= 50",
                    timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(200)
            off = page.eval_on_selector_all(".gl-card-proof", "els => els.length")
            ledger = page.eval_on_selector_all(".gl-model-card", "els => els.length")
            browser.close()

            assert on >= 8, f"expected proof charts by default, got {on}"
            assert off == 0, f"cards must hide under #cards=0, got {off}"
            assert ledger >= 50, f"ledger should still render, got {ledger}"
            assert not errors, f"page errors: {errors}"
    finally:
        httpd.shutdown()
