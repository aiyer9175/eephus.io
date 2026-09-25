# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX IFA tab prints an eFV floor as a floor, not a resolved grade.

Final-pass finding M03-12 (2026-09-24). An eFV of 20.0 with
xfv_grade_is_floor is the outcome map's first knot, returned for every
non-positive projection: the bottom of the scale, not a level. The Signings
list read "Gregory Pio 35 -> 20 SEA $3.00M" and the Efficiency view divided
bonus dollars by those 20 points. ifa_export now carries fv_is_floor; the page
prints the row as a floor with no movement arrow and keeps it out of $/FV and
the country FV means. The eFV scale and floor mechanics are untouched.
"""
from __future__ import annotations

import pytest
from conftest import load_data_doc, serve_site

PROSPX = "prospx/index.html"


def _floor_rows():
    doc = load_data_doc("ifa_timeseries.json")
    if not doc:
        pytest.skip("data/ifa_timeseries.json not built")
    rows = [s for c in doc.get("classes") or [] for s in c.get("signings") or []
            if s.get("fv_is_floor")]
    if not rows:
        pytest.skip("no eFV floor rows in the IFA artifact")
    return rows


@pytest.fixture(scope="module")
def page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        pg = browser.new_page(viewport={"width": 1400, "height": 1000})
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"{base}{PROSPX}#tab=ifa", wait_until="load", timeout=90_000)
        try:
            pg.wait_for_function(
                "() => typeof DATA !== 'undefined' && DATA && DATA.ifa && DATA.ifa.classes",
                timeout=180_000)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"IFA data did not load: {exc}")
        pg._errs = errs
        try:
            yield pg
        finally:
            browser.close()


def test_floor_cell_has_no_arrow_and_says_floor(page):
    keys = [s["player_key"] for s in _floor_rows()]
    out = page.evaluate(
        """(keys) => {
          const want = new Set(keys);
          const rows = DATA.ifa.classes.flatMap(c => c.signings || []).filter(s => want.has(s.player_key));
          return rows.map(s => ({ k: s.player_key, html: _ifaFvProgHTML(s), lbl: _ifaCurLabel(s) }));
        }""", keys)
    assert out
    for r in out:
        assert "floor" in r["html"], r
        for arrow in ("→", "↗", "↘"):
            assert arrow not in r["html"], r
        assert r["lbl"] != "20", r
    assert not page._errs, page._errs


def test_efficiency_excludes_floor_rows(page):
    rows = _floor_rows()
    org = max({s["org"] for s in rows if s.get("org")},
              key=lambda o: sum(1 for s in rows if s["org"] == o))
    graded = page.evaluate(
        """(org) => {
          state.ifaYear = 'all'; state.ifaView = 'efficiency'; renderIFA();
          const tr = [...document.querySelectorAll('.draft-table tbody tr')]
            .find(r => r.children[1] && r.children[1].innerText.trim() === org);
          return tr ? tr.children[5].innerText.trim() : null;
        }""", org)
    if graded is None:
        pytest.skip(f"{org} not ranked on efficiency")
    doc = load_data_doc("ifa_timeseries.json")
    sig = [s for c in doc["classes"] for s in c["signings"] if s.get("org") == org]
    n_graded = sum(1 for s in sig if s.get("is_tracked") and s.get("fv") is not None
                   and not s.get("fv_is_floor"))
    assert graded == f"{n_graded}/{len(sig)}"
