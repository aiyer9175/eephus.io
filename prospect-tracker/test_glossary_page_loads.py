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

import http.server
import json
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


def _browser_page(p, page_errors):
    try:
        browser = p.chromium.launch(headless=True)
    except Exception as exc:
        pytest.skip(f"chromium not installed for playwright: {exc}")
    page = browser.new_page()
    page.on("pageerror", lambda err: page_errors.append(err.message))
    return browser, page


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


def test_terms_view_renders_from_data_layer(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    page_errors: list[str] = []
    with sync_playwright() as p:
        browser, page = _browser_page(p, page_errors)
        page.goto(server + "glossary/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
        n_cards = page.evaluate("document.querySelectorAll('.gl-app .glossary-card').length")
        n_chips = page.evaluate("document.querySelectorAll('#gl-cats .chip').length")
        browser.close()

    assert not page_errors, "JS errors on load:\n  " + "\n  ".join(page_errors)
    assert n_cards >= 190, f"terms view rendered only {n_cards} cards"
    assert n_chips >= 8, f"group chips missing ({n_chips})"


def test_all_four_views_render(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    page_errors: list[str] = []
    results: dict[str, int] = {}
    with sync_playwright() as p:
        browser, page = _browser_page(p, page_errors)
        page.goto(server + "glossary/index.html", wait_until="load", timeout=15_000)
        page.wait_for_selector(".gl-app .glossary-card", timeout=10_000)
        for view, body_id in [("guide", "guide-body"),
                              ("methodology", "methodology-body"),
                              ("models", "models-body"),
                              ("source-comparison", "source-comparison-body")]:
            page.click(f'[data-glossary-view="{view}"]')
            # source-comparison + models lazy-fetch their JSON.
            page.wait_for_timeout(900)
            results[view] = page.evaluate(
                f"document.getElementById('{body_id}').innerHTML.length")
        # The backtest must actually RENDER, not strand its loading state
        # (the missed-port _RATER_META bug hung here while passing a
        # length-only assertion — never again).
        sc_html = page.evaluate(
            "document.getElementById('source-comparison-body').innerHTML")
        # Models & Proofs must render the registry-driven accountability cards,
        # not strand on loading (same lesson).
        models_html = page.evaluate(
            "document.getElementById('models-body').innerHTML")
        browser.close()

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


def test_deep_link_expands_and_highlights_term(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    page_errors: list[str] = []
    with sync_playwright() as p:
        browser, page = _browser_page(p, page_errors)
        page.goto(server + "glossary/index.html#g=wag", wait_until="load",
                  timeout=15_000)
        page.wait_for_selector("#g-wag.is-highlighted", timeout=10_000)
        opened = page.evaluate(
            "!!document.querySelector('#g-wag details[open]')")
        browser.close()

    assert not page_errors, "JS errors on deep link:\n  " + "\n  ".join(page_errors)
    assert opened, "#g=wag arrived collapsed — direct anchors must open the full read"


def test_quick_search_palette_finds_terms(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    page_errors: list[str] = []
    with sync_playwright() as p:
        browser, page = _browser_page(p, page_errors)
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
        browser.close()

    assert not page_errors, "JS errors in palette:\n  " + "\n  ".join(page_errors)
    assert first.strip().upper() == "WAG", f"top palette hit for 'wag' was {first!r}"
    assert still_open, "Ctrl+K stole focus mid-typing — input guard regressed"


def test_legacy_prospx_deep_link_redirects(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    page_errors: list[str] = []
    with sync_playwright() as p:
        browser, page = _browser_page(p, page_errors)
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}"
            "catch(e){}"
        )
        page.goto(server + "prospx/index.html#tab=glossary&g=wag&gview=methodology",
                  wait_until="load", timeout=15_000)
        page.wait_for_url("**/glossary/**", timeout=10_000)
        url = page.url
        browser.close()

    assert "/glossary/" in url, f"legacy #tab=glossary did not redirect: {url}"
    assert "g=wag" in url, f"redirect dropped the term param: {url}"
    assert "view=methodology" in url, f"redirect dropped the sub-view: {url}"
