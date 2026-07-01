# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A11y regression test for the PROSPX sort headers + flagship scatter.

Boots index.html in headless Chromium and asserts the keyboard-accessibility
contract added for the deferred viz/a11y pass:
  - every .sort-header is a keyboard-reachable button (role=button, tabindex=0)
    - stamped by the scoped MutationObserver, so this also covers farm/draft
      headers whose renderers don't call syncSortHeaderActive.
  - aria-sort reflects the live sort state (one active header ascending/
    descending, the rest none).
  - pressing Enter on a focused header actually re-sorts (the delegated keydown
    handler routes through the same click path).
  - the #chart-svg flagship scatter carries role=img + a dynamic aria-label that
    names its axes and sample.

Playwright/chromium are OPTIONAL; the test skips cleanly when unavailable
(mirrors test_index_html_loads.py)."""
from __future__ import annotations

import http.server
import socketserver
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
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
def booted_page(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}"
            "catch(e){}"
        )
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        page.goto(server + "prospx/index.html", wait_until="load", timeout=15_000)
        page.wait_for_timeout(3000)
        yield page, errs
        browser.close()


def test_sort_headers_are_keyboard_buttons(booted_page):
    page, errs = booted_page
    # Every sort-header the observer has seen should be an operable button.
    info = page.evaluate("""() => {
        const hs = [...document.querySelectorAll('.sort-header')];
        return {
            total: hs.length,
            roled: hs.filter(h => h.getAttribute('role') === 'button').length,
            focusable: hs.filter(h => h.getAttribute('tabindex') === '0').length,
        };
    }""")
    assert info["total"] > 0, "no .sort-header spans rendered"
    assert info["roled"] == info["total"], (
        f"{info['total'] - info['roled']} sort-headers missing role=button")
    assert info["focusable"] == info["total"], (
        f"{info['total'] - info['focusable']} sort-headers not focusable")
    assert not errs, "JS errors on load:\n  " + "\n  ".join(errs)


def test_aria_sort_reflects_state_and_enter_resorts(booted_page):
    page, errs = booted_page
    # The main actives board has data-sort-key headers; exactly one column is
    # the active sort at a time (aria-sort ascending|descending), the rest none.
    def aria_states():
        return page.evaluate("""() => [...document.querySelectorAll(
            '#active-section .sort-header[data-sort-key]')]
            .map(h => ({key: h.dataset.sortKey,
                        sort: h.getAttribute('aria-sort'),
                        active: h.classList.contains('is-active')}))""")

    before = aria_states()
    assert before, "no actives sort headers found"
    assert any(s["sort"] in ("ascending", "descending") for s in before), \
        "no header advertises an active aria-sort"
    assert all(s["sort"] in ("ascending", "descending", "none") for s in before), \
        "aria-sort carries an invalid value"

    # Focus an inactive header and press Enter — it must become the active sort.
    target = next((s for s in before if not s["active"]), None)
    assert target, "expected at least one inactive sortable header"
    page.eval_on_selector(
        f'#active-section .sort-header[data-sort-key="{target["key"]}"]',
        "el => el.focus()")
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    after = {s["key"]: s for s in aria_states()}
    assert after[target["key"]]["active"], (
        f"Enter on header '{target['key']}' did not activate its sort")
    assert after[target["key"]]["sort"] in ("ascending", "descending"), (
        "activated header did not advertise a directional aria-sort")
    assert not errs, "JS errors during keyboard sort:\n  " + "\n  ".join(errs)


def test_scatter_has_role_img_and_dynamic_label(booted_page):
    page, errs = booted_page
    page.click('.section-tab[data-section="charts"]')
    page.wait_for_timeout(1500)
    svg = page.evaluate("""() => {
        const s = document.getElementById('chart-svg');
        return s ? {role: s.getAttribute('role'),
                    label: s.getAttribute('aria-label') || ''} : null;
    }""")
    assert svg, "#chart-svg not found"
    assert svg["role"] == "img", "flagship scatter missing role=img"
    # Dynamic label should name the axes / sample, not the bare placeholder.
    assert svg["label"] and svg["label"] != "Scatterplot", (
        f"scatter aria-label not updated dynamically: {svg['label']!r}")
    assert ("plotted" in svg["label"] or "x-axis" in svg["label"]), (
        f"scatter aria-label lacks axis/sample detail: {svg['label']!r}")
    assert not errs, "JS errors on charts section:\n  " + "\n  ".join(errs)
