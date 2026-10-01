# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A11y regression test for the PROSPX sort headers + flagship scatter.

Boots index.html in headless Chromium and asserts the keyboard-accessibility
contract added for the deferred viz/a11y pass:
  - every .sort-header is keyboard-reachable (tabindex=0), and every div-grid
    <span> header is a button (role=button) - stamped by the scoped
    MutationObserver, so this also covers farm/draft headers whose renderers
    don't call syncSortHeaderActive. A <th class="sort-header"> keeps its
    columnheader role (role=button would replace it).
  - census M24-4 (owner answer 2026-09-25): aria-sort is read only on a
    columnheader or rowheader, so no element outside a <th> carries it. The
    div headers carry aria-pressed instead, and the active one holds its sort
    state as .visually-hidden text.
  - pressing Enter on a focused header actually re-sorts (the delegated keydown
    handler routes through the same click path).
  - the #chart-svg flagship scatter carries role=img + a dynamic aria-label that
    names its axes and sample.

Playwright/chromium are OPTIONAL; the test skips cleanly when unavailable
(mirrors test_index_html_loads.py)."""
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
        # Condition wait replaces the old fixed 3s sleep: boot is done once
        # the loading placeholder has left #content. Generous ceiling; a
        # timeout is swallowed so each test's assertions report the real
        # failure state instead of a TimeoutError.
        # The placeholder leaving #content is NOT sufficient: it clears before the
        # board is interactive, so a keypress could land on a header that exists in
        # the markup but is not wired yet. That is what made this test flaky, and it
        # got worse as the shared CSS and JS grew: measured 2026-07-31, a failing run
        # took 13.0s against 3.2s for a passing one, i.e. the downstream 10s re-sort
        # wait was timing out rather than any assertion being wrong.
        #
        # Wait for what the tests actually need: real sort headers, carrying the
        # role/tabindex the boot code stamps on them. Same generous ceiling, and a
        # timeout is still swallowed so each test reports its own failure state
        # instead of a TimeoutError from the fixture.
        try:
            page.wait_for_function(
                "() => { const c = document.getElementById('content');"
                " if (!c || c.innerHTML.indexOf('Loading prospect data') !== -1) return false;"
                " const hs = [...document.querySelectorAll('.sort-header')];"
                " return hs.length > 0 && hs.every(h => h.getAttribute('role') === 'button'"
                "   && h.getAttribute('tabindex') === '0'); }",
                timeout=30_000)
        except Exception:
            pass
        yield page, errs
        browser.close()


def test_sort_headers_are_keyboard_buttons(booted_page):
    page, errs = booted_page
    # Every span sort-header the observer has seen should be an operable button;
    # a <th> one stays a columnheader.
    info = page.evaluate("""() => {
        const hs = [...document.querySelectorAll('.sort-header')];
        const spans = hs.filter(h => h.tagName !== 'TH');
        return {
            total: hs.length,
            spans: spans.length,
            roled: spans.filter(h => h.getAttribute('role') === 'button').length,
            thButton: hs.filter(h => h.tagName === 'TH' && h.hasAttribute('role')).length,
            focusable: hs.filter(h => h.getAttribute('tabindex') === '0').length,
        };
    }""")
    assert info["total"] > 0, "no .sort-header spans rendered"
    assert info["roled"] == info["spans"], (
        f"{info['spans'] - info['roled']} span sort-headers missing role=button")
    assert info["thButton"] == 0, "a <th> sort-header lost its columnheader role"
    assert info["focusable"] == info["total"], (
        f"{info['total'] - info['focusable']} sort-headers not focusable")
    assert not errs, "JS errors on load:\n  " + "\n  ".join(errs)


SORT_TEXT = (", sorted ascending", ", sorted descending")


def test_no_aria_sort_outside_a_table_header(booted_page):
    page, errs = booted_page
    bad = page.evaluate("""() => [...document.querySelectorAll('[aria-sort]')]
        .filter(e => e.tagName !== 'TH' || e.hasAttribute('role'))
        .map(e => e.tagName + '.' + e.className)""")
    assert not bad, f"aria-sort outside a columnheader: {bad[:5]}"


def test_aria_sort_reflects_state_and_enter_resorts(booted_page):
    page, errs = booted_page
    # The main actives board has data-sort-key headers. The active column (two
    # headers share the xfv key, so it can be two cells) is aria-pressed=true
    # and holds hidden sort text; the rest are aria-pressed=false with none.
    # No span carries aria-sort (census M24-4).
    def aria_states():
        return page.evaluate("""() => [...document.querySelectorAll(
            '#active-section .sort-header[data-sort-key]')]
            .map(h => { const sr = h.querySelector('.visually-hidden');
                        return {key: h.dataset.sortKey,
                        sort: h.getAttribute('aria-sort'),
                        pressed: h.getAttribute('aria-pressed'),
                        sr: sr ? sr.textContent : null,
                        srPos: sr ? getComputedStyle(sr).position : null,
                        srW: sr ? sr.getBoundingClientRect().width : null,
                        active: h.classList.contains('is-active')}; })""")

    before = aria_states()
    assert before, "no actives sort headers found"
    assert all(s["sort"] is None for s in before), "a div header carries aria-sort"
    assert all(s["pressed"] in ("true", "false") for s in before), \
        "aria-pressed missing or invalid"
    pressed = [s for s in before if s["pressed"] == "true"]
    assert pressed and all(s["active"] for s in pressed), \
        "no header is aria-pressed=true, or a pressed header is not the active one"
    assert all(s["sr"] in SORT_TEXT for s in pressed), \
        f"active header lacks its hidden sort text: {pressed}"
    assert all(s["srPos"] == "absolute" and s["srW"] <= 1 for s in pressed), \
        f"the sort text is not visually hidden: {pressed}"
    assert all(s["sr"] is None for s in before if s["pressed"] != "true"), \
        "an inactive header still holds hidden sort text"

    # Focus an inactive header and press Enter — it must become the active sort.
    target = next((s for s in before if not s["active"]), None)
    assert target, "expected at least one inactive sortable header"
    sel = f'#active-section .sort-header[data-sort-key="{target["key"]}"]'
    page.eval_on_selector(sel, "el => el.focus()")

    # PROVE FOCUS LANDED BEFORE PRESSING. Under full-suite load this test failed
    # with "Enter did not activate its sort" while passing in isolation, and the
    # message pointed at the sort handler when the real suspect is the step
    # before it: a keypress sent at an element that does not have focus yet goes
    # nowhere, and then the 10s wait below times out on a press that was never
    # delivered. Asserting focus separately means a future failure names which
    # of the two actually broke.
    # RE-APPLY focus inside the wait. The board re-renders after load and
    # REPLACES the header node, so a focus() called once lands on an element
    # that is then thrown away, and document.activeElement falls back to body.
    # Polling with a re-focus survives that; asserting once does not. Diagnosed
    # from a full-suite failure where this wait timed out while the same test
    # passed in isolation.
    page.wait_for_function(
        "key => { const h = document.querySelector("
        "`#active-section .sort-header[data-sort-key=\"${key}\"]`);"
        " if (!h) return false;"
        " if (document.activeElement !== h) { h.focus(); return false; }"
        " return true; }",
        arg=target["key"], timeout=15_000)

    page.keyboard.press("Enter")
    # Condition wait replaces the old fixed 400ms sleep: the re-sort is done
    # once the pressed header advertises the active sort. Timeout swallowed
    # so the assertions below do the failing.
    try:
        page.wait_for_function(
            "key => { const h = document.querySelector("
            "`#active-section .sort-header[data-sort-key=\"${key}\"]`);"
            " return !!h && h.classList.contains('is-active'); }",
            arg=target["key"], timeout=10_000)
    except Exception:
        pass
    after = {s["key"]: s for s in aria_states()}
    assert after[target["key"]]["active"], (
        f"Enter on header '{target['key']}' did not activate its sort")
    assert after[target["key"]]["pressed"] == "true", (
        "activated header did not advertise aria-pressed=true")
    assert after[target["key"]]["sr"] in SORT_TEXT, (
        "activated header did not take the hidden sort text")
    assert after[target["key"]]["sort"] is None, "activated header carries aria-sort"
    assert not errs, "JS errors during keyboard sort:\n  " + "\n  ".join(errs)


def test_scatter_has_role_img_and_dynamic_label(booted_page):
    page, errs = booted_page
    page.click('.section-tab[data-section="charts"]')
    # Condition wait replaces the old fixed 1.5s sleep: the scatter is ready
    # once #chart-svg carries a dynamic (non-placeholder) aria-label - the
    # same facts asserted below. Timeout swallowed so the assertions report
    # the failure.
    try:
        page.wait_for_function(
            "() => { const s = document.getElementById('chart-svg');"
            " const l = s && s.getAttribute('aria-label');"
            " return !!l && l !== 'Scatterplot'; }",
            timeout=10_000)
    except Exception:
        pass
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
