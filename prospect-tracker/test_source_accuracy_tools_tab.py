# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Source Accuracy "Tools" tab (TL_14, Class 2, built dark).

Off (build_site.SOURCE_ACCURACY_TOOLS_TAB False, the served state) the shell
carries no data-sacc-tools-src, the tab list is the six tabs it always had and
Source Comparison carries no link line. On, through a local override of the
shell, the tab renders the look W display copy: the weight verdict per tool,
the three source metrics per tool with thin and not-computable cells shown as
n only, the survivorship sentence beside every headline, and an empty state
when the payload is absent. Playwright is optional; the browser tests skip
without it."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import serve_site

import build_site as B

ROOT = Path(__file__).parent
ATTR = ' data-sacc-tools-src="/data/tool_source_accuracy.json"'
SIX = ["read-first", "side", "archetype", "cuts", "precision", "coverage"]
SURV = "Accuracy among players who reached the majors."

# A fixture payload in the display copy's shape, with one void primary, one
# pool under the minimum and one thin board-year cell.
FIXTURE = {
    "look": "W", "display_copy": True, "served": False,
    "frame": {"board_years": [2017, 2018], "max_debut_year": 2024, "last_outcome_season": 2026},
    "tools": {
        "hit": {"stat": "k_pct", "role": "primary", "verdict": "NULL", "n": 300, "d_rho": -0.001,
                "equal": {"spearman": 0.4, "auc": 0.7}, "weighted": {"spearman": 0.399, "auc": 0.7},
                "holm": {"p": 0.8, "step": 2, "rejected": False, "m": 2, "threshold": 0.05}},
        "speed": {"stat": "sprint", "role": "primary", "verdict": "VOID", "n": 400, "d_rho": 0.004,
                  "equal": {"spearman": 0.7, "auc": 0.8}, "weighted": {"spearman": 0.704, "auc": 0.8},
                  "holm": {"p": 0.05, "step": 1, "rejected": False, "m": 2, "threshold": 0.025}},
        "game_pwr": {"tool": "game_pwr", "stat": "iso", "role": "secondary",
                     "verdict": "secondary: no verdict", "ba2": "NO SHIP", "n": 250, "d_rho": 0.003},
    },
    "tag": {
        "game_pwr": {"stat": "iso", "n_frame": 260, "k_m": 177.5, "regressed": True, "by_source": {
            "fangraphs": {"n": 250, "computable": True, "ordering": 0.52, "bias_regressed": -0.012,
                          "bias_pit": -0.03, "error_abs_regressed": 0.026, "note": None,
                          "per_year": {"2017": {"n": 12, "thin": True, "range_gap": [-0.05, 0.04]},
                                       "2018": {"n": 238, "ordering_rho": 0.51}}},
            "baseballamerica": {"n": 61, "computable": False, "ordering": 0.39, "bias_regressed": 0.01,
                                "bias_pit": 0.03, "error_abs_regressed": 0.02,
                                "note": "NOT COMPUTABLE: pool under 100 players"}}},
    },
    "survivorship": "Accuracy AMONG DEBUTS: only players who reached the majors have a realized MLB quantity.",
}


def test_flag_defaults_off_and_shell_differs_only_by_the_attribute(monkeypatch):
    assert B.SOURCE_ACCURACY_TOOLS_TAB is False
    off = B.build_glossary()
    assert "data-sacc-tools-src" not in off
    monkeypatch.setattr(B, "SOURCE_ACCURACY_TOOLS_TAB", True)
    on = B.build_glossary()
    assert on.count(ATTR) == 1
    assert on.replace(ATTR, "") == off


def test_served_shell_is_dark():
    page = (ROOT / "glossary" / "index.html").read_text(encoding="utf-8")
    assert "data-sacc-tools-src" not in page


def test_no_glossary_terms_written_in_the_dark_build():
    terms = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))["entries"]
    names = {(e.get("term") or "").lower() for e in terms} | {e["id"] for e in terms}
    assert "tool above grade (tag)" not in names and "tool_above_grade" not in names


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        yield b
        b.close()


READY = ("() => { const el = document.getElementById('source-accuracy-body');"
         " return !!el && el.innerHTML.indexOf('sacc-tabs') !== -1"
         " && el.innerHTML.indexOf('Loading the cohort') === -1; }")
TABS = "[...document.querySelectorAll('[data-sacc-tab]')].map(b => b.dataset.saccTab)"


def _open(browser, server, shell=None, payload=None):
    errs: list[str] = []
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.on("pageerror", lambda e: errs.append(e.message))
    if shell is not None:
        page.route("**/glossary/index.html*", lambda r: r.fulfill(
            status=200, body=shell, headers={"content-type": "text/html; charset=utf-8"}))
        if payload is None:
            page.route("**/data/tool_source_accuracy.json*", lambda r: r.fulfill(status=404, body="nf"))
        else:
            page.route("**/data/tool_source_accuracy.json*", lambda r: r.fulfill(
                status=200, body=json.dumps(payload), headers={"content-type": "application/json"}))
    page.goto(server + "glossary/index.html#view=source-accuracy", wait_until="load", timeout=15_000)
    page.wait_for_function(READY, timeout=15_000)
    return page, errs


def _on_shell(monkeypatch):
    monkeypatch.setattr(B, "SOURCE_ACCURACY_TOOLS_TAB", True)
    return B.build_glossary()


def test_off_tab_list_unchanged(server, browser):
    page, errs = _open(browser, server)
    try:
        assert page.evaluate(TABS) == SIX
        assert "sacc-tools" not in page.evaluate("document.getElementById('source-accuracy-body').innerHTML")
        page.evaluate("location.hash = '#view=source-comparison'")
        page.wait_for_timeout(1500)
        assert "data-sacc-goto" not in page.evaluate(
            "document.getElementById('source-comparison-body').innerHTML")
    finally:
        page.close()
    assert not errs, errs


def test_on_populated(server, browser, monkeypatch):
    page, errs = _open(browser, server, _on_shell(monkeypatch), FIXTURE)
    try:
        assert page.evaluate(TABS) == SIX + ["tools"]
        page.click('[data-sacc-tab="tools"]')
        page.wait_for_function("() => document.getElementById('source-accuracy-body')"
                               ".innerHTML.indexOf('Loading the tool accuracy') === -1", timeout=10_000)
        html = page.evaluate("document.getElementById('source-accuracy-body').innerHTML")
    finally:
        page.close()
    assert not errs, errs
    assert "The look is void" in html
    assert "equal weight retains" in html
    assert "runs hot by 0.012 ISO" in html
    assert "2017: n 12, thin, range -0.050 to +0.040 ISO" in html
    assert "NOT COMPUTABLE: pool under 100 players" in html and "0.390" not in html
    assert "approx. 95% interval" in html
    assert "2026-08-08" in html and "sacc-tools-framework" in html
    # beside every headline: the tiles, the status line, each table title
    assert html.count(SURV) >= 2 + 1 + 2 + 1 + 1
    assert "—" not in html and "–" not in html


def test_on_empty_state(server, browser, monkeypatch):
    page, errs = _open(browser, server, _on_shell(monkeypatch), None)
    try:
        page.click('[data-sacc-tab="tools"]')
        page.wait_for_function("() => document.getElementById('source-accuracy-body')"
                               ".innerHTML.indexOf('not published yet') !== -1", timeout=10_000)
        assert page.query_selector("#gl-sacct-retry") is not None
    finally:
        page.close()
    assert not errs, errs


def test_on_source_comparison_link(server, browser, monkeypatch):
    page, errs = _open(browser, server, _on_shell(monkeypatch), FIXTURE)
    try:
        page.evaluate("location.hash = '#view=source-comparison'")
        page.wait_for_selector("[data-sacc-goto]", timeout=15_000)
        page.click("[data-sacc-goto]")
        page.wait_for_function("() => { const b = document.querySelector('[data-sacc-tab=\"tools\"]');"
                               " return !!b && b.getAttribute('aria-pressed') === 'true'; }", timeout=10_000)
    finally:
        page.close()
    assert not errs, errs
