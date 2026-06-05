# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

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
    # ThreadingTCPServer (not the single-threaded TCPServer): the boot path
    # kicks off a large async fetch of data/timeseries.json (~58MB) which, on a
    # single-threaded server, blocks the remaining load-blocking resources and
    # pushes page.goto(wait_until="load") past its timeout. A threaded server
    # serves resources concurrently — like real static hosting — so the page
    # loads promptly regardless of payload size. (Assertions are unchanged.)
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
        # shutdown() stops serve_forever; server_close() releases the
        # listening socket. Without the latter, the socket lingers until
        # GC and surfaces as a ResourceWarning on Python 3.13+.
        httpd.shutdown()
        httpd.server_close()


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
        # Pre-unlock the welcome gate so its full-screen overlay doesn't sit
        # on top of #content. Runs before any page script on every navigation.
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}"
            "catch(e){}"
        )
        page.on("pageerror", lambda err: page_errors.append(err.message))
        page.goto(server + "prospx/index.html", wait_until="load", timeout=15_000)
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


# All 11 list/scan sections + the 2 detail entry points. Each must
# render without JS errors AND either show content or a `.state-message`
# empty-state placeholder. Catches the regression where a section
# silently renders blank because a render fn threw mid-build.
SECTION_TABS = [
    "active",
    "spotlights",
    "traded",
    "injured",
    "debuts",
    "farm",
    "leaderboards",
    "glossary",
    "watchlist",
]


def test_every_section_renders(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    page_errors: list[str] = []
    section_results: dict[str, dict] = {}

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        # Pre-unlock the welcome gate — otherwise its overlay intercepts the
        # .section-tab clicks below.
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}"
            "catch(e){}"
        )
        page.on("pageerror", lambda err: page_errors.append(err.message))
        page.goto(server + "prospx/index.html", wait_until="load", timeout=15_000)
        page.wait_for_timeout(3000)  # let boot + initial render settle

        for section in SECTION_TABS:
            # Click the section-tab button — same path as a real user.
            # Watchlist no longer has a section tab; it's reached via the
            # persistent top-right global control. Exercising that button
            # here also guards the regression where it called an undefined
            # renderSection() and silently failed to navigate.
            if section == "watchlist":
                page.click("#global-watchlist")
            else:
                page.click(f'.section-tab[data-section="{section}"]')
            # Slice-gated sections (graduates, injured) fire one extra
            # render once the lazy sidecar arrives — give it room.
            page.wait_for_timeout(800)
            result = page.evaluate(f"""() => {{
                const sec = document.getElementById('{section}-section');
                if (!sec) return {{found: false}};
                const visible = sec.style.display !== 'none';
                const html = sec.innerHTML;
                // Has content if there's either a populated row container
                // OR an explicit empty-state placeholder.
                // `.debut-row` is the debuts/graduates list row class
                // (renamed when the Graduates section became Debuted).
                const hasRows = !!sec.querySelector(
                    '.player-row, .debut-row, .grad-row, .farm-row, .spotlight-row, .glossary-card');
                const hasStateMsg = !!sec.querySelector('.state-message');
                return {{
                    found: true,
                    visible,
                    hasRows,
                    hasStateMsg,
                    htmlLen: html.length,
                }};
            }}""")
            section_results[section] = result

        browser.close()

    assert not page_errors, (
        f"JS errors during section walk:\n  " + "\n  ".join(page_errors)
    )

    # Every section must (a) exist and (b) be in a defined state — either
    # rows rendered OR an explicit empty-state placeholder. A section that
    # shows neither is silently broken.
    failed = []
    for section, res in section_results.items():
        if not res.get("found"):
            failed.append(f"{section}: section div not found in DOM")
            continue
        if not (res.get("hasRows") or res.get("hasStateMsg")):
            failed.append(
                f"{section}: rendered no rows AND no .state-message — "
                f"silent empty render (htmlLen={res.get('htmlLen')})"
            )
    assert not failed, "Section render gaps:\n  " + "\n  ".join(failed)


# test_graduates_page_shows_fg_writeup_pills removed 2026-05-26:
# The `.debut-writeup-pill` CSS class + this test were a stale Stage-3a
# stub that never had a JS render path wired up after the
# Graduates -> Debuted rename. CSS deleted alongside this test.


def test_welcome_gate_locks_unlocks_and_persists(server):
    """The first-visit welcome gate covers the page, rejects a wrong
    password, accepts "baseball", and stays dismissed on reload (the
    unlock persists to localStorage)."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    page_errors: list[str] = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        # Fresh context => empty localStorage => first-visit (locked) state.
        page = browser.new_page()
        page.on("pageerror", lambda err: page_errors.append(err.message))
        page.goto(server + "prospx/index.html", wait_until="load", timeout=15_000)
        page.wait_for_timeout(500)

        gate = page.locator("#welcome-gate")
        # Gate is visible and the password row (gate mode) is showing.
        assert gate.is_visible(), "gate should be up on a first visit"
        assert page.locator("#wg-input").is_visible(), (
            "password input should show in gate mode"
        )

        # Wrong password keeps the gate up and surfaces an error.
        page.fill("#wg-input", "wrongword")
        page.click(".wg-submit")
        page.wait_for_timeout(200)
        assert gate.is_visible(), "wrong password must not dismiss the gate"
        assert page.locator("#wg-error").inner_text().strip() != "", (
            "wrong password should show an error message"
        )

        # Correct password (case-insensitive) drops the gate.
        page.fill("#wg-input", "BASEBALL")
        page.click(".wg-submit")
        page.wait_for_timeout(300)
        assert not gate.is_visible(), "correct password should dismiss the gate"
        unlocked = page.evaluate(
            "localStorage.getItem('prospect-tracker.gate-unlocked')"
        )
        assert unlocked == "1", "unlock should persist to localStorage"

        # Reload — the gate stays down (no re-prompt on this device).
        page.reload(wait_until="load", timeout=15_000)
        page.wait_for_timeout(500)
        assert not page.locator("#welcome-gate").is_visible(), (
            "gate must not re-appear after a previous unlock"
        )

        # The masthead link re-opens it read-only (no password field).
        page.click("#open-welcome-letter")
        page.wait_for_timeout(300)
        assert page.locator("#welcome-gate").is_visible(), (
            "masthead link should re-open the letter"
        )
        assert page.locator("#wg-close").is_visible(), (
            "read mode should show the Close button"
        )
        assert not page.locator("#wg-input").is_visible(), (
            "read mode must not show the password field"
        )
        # Esc closes the read-only letter.
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        assert not page.locator("#welcome-gate").is_visible(), (
            "Esc should close the read-only letter"
        )

        browser.close()

    assert not page_errors, (
        "JS errors during welcome-gate walk:\n  " + "\n  ".join(page_errors)
    )
