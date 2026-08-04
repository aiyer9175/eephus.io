# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Launch smoke test for the unified Glossary & Methodology module
(/glossary/ + assets/glossary.js + assets/eephus-gl.js + data/glossary.json).

Mirrors test_index_html_loads.py: boots the page in headless Chromium and
asserts the JS actually runs — term cards render from the unified data
layer, all four views (Terms / How to Read / Methodology / Source
Comparison) reach a defined state, #g= deep links land on their card, the
site-wide ⌘K palette opens and finds terms, and the retired PROSPX
#tab=glossary deep links redirect here with term + sub-view intact.

Playwright is an OPTIONAL dependency; tests skip cleanly without it."""
from __future__ import annotations

import json
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
def browser():
    """One chromium per module (was: one launch per test, ~5 per run).
    browser.new_page() gives each test a fresh isolated context, so test
    isolation matches the old fresh-browser-per-test behavior."""
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


def test_glossary_data_layer_is_valid():
    """The canonical layer parses, has no duplicate slugs, and every entry
    carries the fields the runtime renders from."""
    d = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    entries = d["entries"]
    assert len(entries) >= 190, f"expected the full unified layer, got {len(entries)}"
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "duplicate slugs in glossary.json"
    idset = set(ids)
    for e in entries:
        assert e.get("term") and e.get("definition") and e.get("category"), \
            f"{e.get('id')}: missing term/definition/category"
        for ref in e.get("seeAlso", []):
            assert ref in idset, f"{e['id']}: dangling seeAlso → {ref}"
    # Permalink-stable legacy slugs must survive every rebuild (#g= URLs).
    for legacy in ("pwr_plus", "tvi", "sur_plus", "farm_report_card"):
        assert legacy in idset, f"legacy permalink slug missing: {legacy}"


def test_terms_view_renders_from_data_layer(server, browser):
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
        n_cards = page.evaluate("document.querySelectorAll('.gl-app .glossary-card').length")
        n_chips = page.evaluate("document.querySelectorAll('#gl-cats .chip').length")
    finally:
        page.close()

    assert not page_errors, "JS errors on load:\n  " + "\n  ".join(page_errors)
    assert n_cards >= 190, f"terms view rendered only {n_cards} cards"
    assert n_chips >= 8, f"group chips missing ({n_chips})"


def test_all_four_views_render(server, browser):
    page_errors: list[str] = []
    results: dict[str, int] = {}
    # Per-view readiness signals: the static views are ready when populated;
    # models + source-comparison lazy-fetch their JSON, so wait for the same
    # rendered markers the assertions below check. These condition waits
    # replace a fixed 900ms sleep per view; timeouts are swallowed so the
    # assertions do the failing.
    ready = {
        "models": " && el.innerHTML.indexOf('gl-verdict') !== -1",
        "source-comparison": (
            " && (el.innerHTML.indexOf('The full head-to-head') !== -1"
            " || el.innerHTML.indexOf('A different kind of Future Value') !== -1"
            " || el.innerHTML.indexOf('no resolved cohorts') !== -1)"),
    }
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
        for view, body_id in [("guide", "guide-body"),
                              ("methodology", "methodology-body"),
                              ("models", "models-body"),
                              ("source-comparison", "source-comparison-body")]:
            page.click(f'[data-glossary-view="{view}"]')
            try:
                page.wait_for_function(
                    "id => { const el = document.getElementById(id);"
                    " return !!el && el.innerHTML.length >= 200"
                    + ready.get(view, "") + "; }",
                    arg=body_id, timeout=10_000)
            except Exception:
                pass
            results[view] = page.evaluate(
                f"document.getElementById('{body_id}').innerHTML.length")
        # The backtest must actually RENDER, not strand its loading state
        # (the missed-port _RATER_META bug hung here while passing a
        # length-only assertion - never again).
        sc_html = page.evaluate(
            "document.getElementById('source-comparison-body').innerHTML")
        # Models & Proofs must render the registry-driven accountability cards,
        # not strand on loading (same lesson).
        models_html = page.evaluate(
            "document.getElementById('models-body').innerHTML")
    finally:
        page.close()

    assert not page_errors, "JS errors during view walk:\n  " + "\n  ".join(page_errors)
    empty = [v for v, n in results.items() if n < 200]
    assert not empty, f"views rendered (near-)empty: {empty} — {results}"
    assert "Loading backtest" not in sc_html, "source comparison stranded on its loading state"
    # 2026-07-06: the data-state header is "The full head-to-head", led by the hero
    # verdict banner ("A different kind of Future Value"); the empty-state text is unchanged.
    assert ("The full head-to-head" in sc_html
            or "A different kind of Future Value" in sc_html
            or "no resolved cohorts" in sc_html), "source comparison rendered neither data nor empty-state"
    assert "gl-verdict" in models_html, "Models & Proofs stranded (no verdict badges rendered)"
    assert "Predicts" in models_html, "Models & Proofs cards missing the Predicts row"


def test_deep_link_expands_and_highlights_term(server, browser):
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html#g=wag", wait_until="load",
                  timeout=15_000)
        page.wait_for_selector("#g-wag.is-highlighted", timeout=10_000)
        opened = page.evaluate(
            "!!document.querySelector('#g-wag details[open]')")
    finally:
        page.close()

    assert not page_errors, "JS errors on deep link:\n  " + "\n  ".join(page_errors)
    assert opened, "#g=wag arrived collapsed — direct anchors must open the full read"


def test_quick_search_palette_finds_terms(server, browser):
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.goto(server + "glossary/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
        page.keyboard.press("Control+k")
        page.wait_for_selector("#qk-overlay.is-open", timeout=5_000)
        page.fill("#qk-input", "wag")
        page.wait_for_selector(".qk-row", timeout=5_000)
        first = page.evaluate(
            "document.querySelector('.qk-row .qk-row-name').textContent")
        # Ctrl+K must NOT fire while typing in an input (the focus guard the
        # legacy duplicate handler lacked) — overlay stays open, no toggle.
        page.keyboard.press("Control+k")
        still_open = page.evaluate(
            "document.getElementById('qk-overlay').classList.contains('is-open')")
    finally:
        page.close()

    assert not page_errors, "JS errors in palette:\n  " + "\n  ".join(page_errors)
    assert first.strip().upper() == "WAG", f"top palette hit for 'wag' was {first!r}"
    assert still_open, "Ctrl+K stole focus mid-typing — input guard regressed"


def test_legacy_prospx_deep_link_redirects(server, browser):
    page_errors: list[str] = []
    page = _browser_page(browser, page_errors)
    try:
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}"
            "catch(e){}"
        )
        page.goto(server + "prospx/index.html#tab=glossary&g=wag&gview=methodology",
                  wait_until="load", timeout=15_000)
        page.wait_for_url("**/glossary/**", timeout=10_000)
        url = page.url
    finally:
        page.close()

    assert "/glossary/" in url, f"legacy #tab=glossary did not redirect: {url}"
    assert "g=wag" in url, f"redirect dropped the term param: {url}"
    assert "view=methodology" in url, f"redirect dropped the sub-view: {url}"
