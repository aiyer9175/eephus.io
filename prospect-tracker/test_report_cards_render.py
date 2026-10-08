"""Playwright guard for the report cards on the one model ledger (/models/).

Since LIBRARY_7 (owner answer LB-Q2, 2026-10-08) the report-card bars, the
family grouping and the per-row History links live on /models/, server-rendered
by build_site.build_models; the Library's old #view=models address forwards
there. This drives the served page: the bars are in the open rows, the Family
control moves every row into its family group and back, a filter still cuts
across the families, and the old address lands on the ledger. Skips cleanly
where playwright/chromium is absent.
"""
import os

import pytest
from conftest import make_static_server

import model_registry as mr

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def _serve():
    """Shared harness (conftest.make_static_server): HTTP/1.1 + threaded.

    Was a single-threaded TCPServer on the stdlib HTTP/1.0 default. Both
    were wrong: HTTP/1.0 signals end-of-body by closing the socket, which
    on Windows races the send buffer and truncates a large asset
    (assets/site.css, 211KB) so page.goto hangs to timeout; and once
    HTTP/1.1 keep-alive is on, a single-threaded server deadlocks on the
    browser's parallel connections. See conftest._QuietHTTP."""
    return make_static_server(ROOT)


_STATE = """() => {
  const vis = el => !!el && el.offsetParent !== null;
  const rows = [...document.querySelectorAll('.acct-row')];
  const fams = [...document.querySelectorAll('.acct-fam')];
  return {
    rows: rows.length,
    inFam: rows.filter(r => r.parentElement.classList.contains('acct-fam')).length,
    shownRows: rows.filter(vis).length,
    shownFams: fams.filter(vis).map(f => f.dataset.acctFam),
    shownGroups: [...document.querySelectorAll('.acct-group')].filter(vis).length,
    cards: document.querySelectorAll('.acct-row .acct-card').length,
    history: document.querySelectorAll('.acct-row a[href^="/models/updates/#model="]').length,
    pressed: document.querySelector('[data-acct-groupby="family"]').getAttribute('aria-pressed'),
    hash: location.hash,
    scrollW: document.documentElement.scrollWidth, innerW: innerWidth };
}"""


def test_the_ledger_carries_cards_families_and_history():
    reg = mr.load()["models"]
    n_rows = len(reg)
    n_cards = sum(1 for m in reg if m.get("card"))
    n_dep = sum(1 for m in reg if m.get("verdict") == "deprecated")
    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch()
            except Exception as e:  # noqa: BLE001
                pytest.skip(f"chromium unavailable: {e}")
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            base = f"http://127.0.0.1:{port}"

            page.goto(base + "/models/index.html", wait_until="load")
            page.wait_for_selector(".acct-row", timeout=15000)
            first = page.evaluate(_STATE)
            # an open carded row shows its bars
            page.locator(".acct-row:has(.acct-card) > summary").first.click()
            bar_w = page.evaluate(
                "document.querySelector('.acct-row[open] .acct-card-track').getBoundingClientRect().width")

            page.click('[data-acct-groupby="family"]')
            fam = page.evaluate(_STATE)
            page.click('[data-acct-filter="deprecated"]')
            fam_dep = page.evaluate(_STATE)
            page.click('[data-acct-groupby="verdict"]')
            back = page.evaluate(_STATE)

            # the Library's old address lands on the ledger
            page.goto(base + "/glossary/index.html#view=models", wait_until="load")
            page.wait_for_selector(".acct-app .acct-row", timeout=15000)
            landed = page.evaluate("location.pathname")
            page.goto(base + "/glossary/index.html#view=models&family=betting", wait_until="load")
            page.wait_for_selector(".acct-app .acct-row", timeout=15000)
            deep = page.evaluate(_STATE)
            browser.close()

        assert first["rows"] == n_rows and first["inFam"] == 0
        assert first["cards"] == n_cards >= 8, first["cards"]
        assert first["history"] == n_rows
        assert first["shownFams"] == [] and first["pressed"] == "false"
        assert bar_w > 40, f"the report-card track is {bar_w}px wide at 390"
        assert fam["inFam"] == n_rows and fam["shownRows"] == n_rows
        assert fam["shownGroups"] == 0 and len(fam["shownFams"]) >= 8
        assert fam["pressed"] == "true" and fam["hash"] == "#group=family"
        assert fam_dep["shownRows"] == n_dep
        assert fam_dep["hash"] == "#group=family&verdict=deprecated"
        assert back["inFam"] == 0 and back["shownGroups"] == 1
        assert back["hash"] == "#verdict=deprecated"
        assert landed == "/models/"
        assert deep["inFam"] == n_rows and "betting" in deep["shownFams"]
        assert deep["hash"] == "#family=betting"
        for st in (first, fam, back, deep):
            assert st["scrollW"] == st["innerW"], st
        assert not errors, f"page errors: {errors}"
    finally:
        httpd.shutdown()
