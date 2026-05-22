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


# All 11 list/scan sections + the 2 detail entry points. Each must
# render without JS errors AND either show content or a `.state-message`
# empty-state placeholder. Catches the regression where a section
# silently renders blank because a render fn threw mid-build.
SECTION_TABS = [
    "active",
    "spotlights",
    "traded",
    "injured",
    "graduates",
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
        page.on("pageerror", lambda err: page_errors.append(err.message))
        page.goto(server, wait_until="load", timeout=15_000)
        page.wait_for_timeout(3000)  # let boot + initial render settle

        for section in SECTION_TABS:
            # Click the section-tab button — same path as a real user.
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
                const hasRows = !!sec.querySelector(
                    '.player-row, .grad-row, .farm-row, .spotlight-row, .glossary-card');
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


def test_graduates_page_shows_fg_writeup_pills(server):
    """Once the scout-reports sidecar is loaded, graduates with a FG
    grad-year writeup should display the `.grad-writeup-pill` indicator.
    Guards the Stage 3a UI surfacing — silently swallowed if the data
    isn't ingested (sidecar-empty → pill rightfully absent)."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    import json
    from pathlib import Path

    # Cheap pre-check: does the local scout_reports.json carry any
    # fangraphs entry with a "graduat" label? If not, skip — there's
    # nothing for the pill to flag.
    sr_path = Path(__file__).parent / "data" / "scout_reports.json"
    if not sr_path.exists():
        pytest.skip("scout_reports.json not present — no data to test against")
    sidecar = json.loads(sr_path.read_text(encoding="utf-8"))
    # Multi-cycle shape (2026-05): sidecar[key]["fangraphs"] is a list
    # of {date, label, text, hash} entries newest-first. Iterate every
    # cycle to find one with a "graduat"-labeled label.
    def _has_grad_label(entries):
        if isinstance(entries, dict):     # legacy single-entry shape
            return "graduat" in (entries.get("label") or "").lower()
        if isinstance(entries, list):
            return any("graduat" in (e.get("label") or "").lower() for e in entries)
        return False
    eligible_keys = {
        k for k, by_src in sidecar.items()
        if "fangraphs" in by_src
        and _has_grad_label(by_src["fangraphs"])
    }
    if not eligible_keys:
        pytest.skip("no FG grad-year writeups in sidecar — nothing to flag")

    page_errors: list[str] = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        page.on("pageerror", lambda err: page_errors.append(err.message))
        page.goto(server, wait_until="load", timeout=15_000)
        page.wait_for_timeout(3000)
        # Navigate to Graduates + wait for the slice + sidecar to settle.
        page.click('.section-tab[data-section="graduates"]')
        page.wait_for_timeout(2500)
        n_pills = page.evaluate(
            "document.querySelectorAll('.grad-writeup-pill').length"
        )
        browser.close()

    assert not page_errors, (
        "JS errors during graduates render:\n  " + "\n  ".join(page_errors)
    )
    assert n_pills >= 1, (
        f"expected ≥1 .grad-writeup-pill in the graduates list (sidecar "
        f"has {len(eligible_keys)} eligible graduates), got {n_pills}"
    )
