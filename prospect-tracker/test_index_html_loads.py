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

from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent


@pytest.fixture(scope="module")
def server():
    """Shared harness (conftest.serve_site): HTTP/1.1 + threaded.

    Both settings are load-bearing and the reason this is no longer
    re-typed per module; see conftest._QuietHTTP for the measured
    HTTP/1.0 large-file truncation this fixes."""
    with serve_site() as base:
        yield base


def _wait_for_boot(page):
    """Condition wait replacing the old fixed 2.5-3s sleeps: boot is done
    once the loading placeholder has left #content. Generous ceiling; a
    timeout is swallowed so the assertions below report the real failure
    state (JS error list + placeholder text) instead of a TimeoutError."""
    try:
        page.wait_for_function(
            "() => { const c = document.getElementById('content');"
            " return !!c && c.innerHTML.indexOf('Loading prospect data') === -1; }",
            timeout=30_000)
    except Exception:
        pass


@pytest.fixture(scope="module")
def booted_page(server):
    """One booted app page shared by the module (the pattern from
    test_prospx_sort_a11y.py): one chromium launch + one boot of the large
    payload instead of one per test."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        # Pre-unlock the welcome gate so its full-screen overlay doesn't sit
        # on top of #content or intercept the .section-tab clicks. Runs
        # before any page script on every navigation.
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}"
            "catch(e){}"
        )
        page_errors: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(err.message))
        page.goto(server + "prospx/index.html", wait_until="load", timeout=15_000)
        _wait_for_boot(page)
        yield page, page_errors
        browser.close()


def test_page_boots_without_js_errors(booted_page):
    page, page_errors = booted_page
    content_html = page.evaluate(
        "document.getElementById('content').innerHTML"
    )

    assert not page_errors, (
        "JS errors thrown on load:\n  " + "\n  ".join(page_errors)
    )
    assert "Loading prospect data" not in content_html, (
        "Boot IIFE never finished - #content still shows the placeholder. "
        "Likely a JS error before the fetch."
    )


# Every list/scan section reachable from the tabs strip (+ watchlist via
# the global control). Each must render without JS errors AND either show
# content or a `.state-message` empty-state placeholder. Catches the
# regression where a section silently renders blank because a render fn
# threw mid-build. (Glossary left for /glossary/ 2026-06-10 — its redirect
# is covered in test_glossary_page_loads.py.)
SECTION_TABS = [
    "active",
    "spotlights",
    "traded",
    "injured",
    "debuts",
    "farm",
    "leaderboards",
    "watchlist",
]


def test_every_section_renders(booted_page):
    page, page_errors = booted_page
    section_results: dict[str, dict] = {}

    for section in SECTION_TABS:
        # Click the section-tab button - same path as a real user.
        # Watchlist no longer has a section tab; it's reached via the
        # persistent top-right global control. Exercising that button
        # here also guards the regression where it called an undefined
        # renderSection() and silently failed to navigate.
        if section == "watchlist":
            page.click("#global-watchlist")
        else:
            page.click(f'.section-tab[data-section="{section}"]')
        # Slice-gated sections (graduates, injured) fire one extra
        # render once the lazy sidecar arrives - give it room. (KEPT as
        # a fixed settle wait: the re-render has no DOM completion
        # signal to condition-wait on.)
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
                '.player-row, .debut-row, .grad-row, .farm-row, .spotlight-row');
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


# test_welcome_gate_locks_unlocks_and_persists removed 2026-06-09: the alpha
# welcome gate/letter itself was removed in 5e60c6b ("Beta v1.0: remove alpha
# gate/letter") — the walk-through outlived the feature it tested and failed
# on every run since.
