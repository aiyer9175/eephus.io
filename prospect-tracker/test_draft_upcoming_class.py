# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX names ONE upcoming draft class, the earliest undrafted class.

Final-pass finding M03-07 (2026-09-24). draft_export marks every undrafted
class is_current, and once Baseball America publishes an early list for the
draft after next, two classes hold prospects (2027 and 2028). The page took
the FIRST is_current class in the export's newest-first order, so the college
pages called 2028 the current class and filed the 2027 prospects under "Draft
history" beside drafted alumni, the colleges board's Current column counted
2028, and both class chips carried the upcoming-draft hourglass.

The upcoming class is min(year) over is_current classes with prospects;
later scouted classes are a future class with an early list.
"""
from __future__ import annotations

import re

import pytest
from conftest import load_data_doc, serve_site

PROSPX = "prospx/index.html"


def _classes():
    doc = load_data_doc("draft_timeseries.json")
    if not doc:
        pytest.skip("data/draft_timeseries.json not built")
    return doc.get("classes") or []


def _upcoming(classes):
    cur = [c for c in classes if c.get("is_current") and (c.get("n_prospects") or 0) > 0]
    if not cur:
        pytest.skip("no undrafted class with prospects in the export")
    return min(c["year"] for c in cur)


def test_source_has_no_first_is_current_pick():
    """The newest-first `classes.find(c => c.is_current ...)` pick is gone."""
    src = open(PROSPX, encoding="utf-8").read()
    assert not re.search(r"classes\.find\(c => c\.is_current", src)
    assert "const PREFERRED_DRAFT_YEAR = 2026;" not in src


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
        pg._base = base
        pg._errs = errs
        try:
            yield pg
        finally:
            browser.close()


def _open_draft(pg, year):
    pg.goto(f"{pg._base}{PROSPX}#tab=draft&dyear={year}&dview=rankings",
            wait_until="load", timeout=90_000)
    try:
        pg.wait_for_selector("[data-draft-year]", timeout=180_000)
    except Exception as exc:                                  # noqa: BLE001
        pytest.skip(f"draft chips did not paint: {exc}")


def test_only_the_upcoming_chip_has_the_hourglass(page):
    classes = _classes()
    up = _upcoming(classes)
    _open_draft(page, up)
    chips = page.eval_on_selector_all(
        "[data-draft-year]",
        "els => els.map(e => [e.dataset.draftYear, e.textContent.trim(), e.title])")
    marked = [y for y, txt, _ in chips if "⏳" in txt]
    assert marked == [str(up)], chips
    for y, _, title in chips:
        if y == "overall":
            continue
        c = next(c for c in classes if str(c["year"]) == y)
        if c.get("is_current") and (c.get("n_prospects") or 0) > 0 and c["year"] != up:
            assert "future class" in title, (y, title)
    assert not page._errs, page._errs


def test_college_page_current_block_is_the_upcoming_class(page):
    classes = _classes()
    up = _upcoming(classes)
    # A college with a prospect in the upcoming class, resolved by the page's
    # own college key so the test follows the page's canon.
    _open_draft(page, up)
    name = page.evaluate(
        """(up) => {
          const cls = DATA.draft.classes.find(c => c.year === up);
          for (const p of cls.prospects || []) { const k = _collegeKeyOf(p); if (k) return k; }
          return null;
        }""", up)
    if not name:
        pytest.skip("no college prospect in the upcoming class")
    page.goto(f"{page._base}{PROSPX}#college={name}", wait_until="load", timeout=90_000)
    page.wait_for_selector("#college-detail-body .detail-title", timeout=180_000)
    titles = page.eval_on_selector_all(
        "#college-detail-body .detail-title", "els => els.map(e => e.textContent.trim())")
    assert f"Current draft prospects ({up})" in titles, titles
    # No upcoming-class row is filed under Draft history.
    hist_years = page.evaluate(
        """() => {
          const t = [...document.querySelectorAll('#college-detail-body .detail-title')]
            .find(e => e.textContent.startsWith('Draft history'));
          if (!t) return [];
          const tbl = t.nextElementSibling;
          return [...tbl.querySelectorAll('tbody tr')].map(r => r.children[1].textContent.trim());
        }""")
    undrafted = {str(c["year"]) for c in classes if c.get("is_current")}
    assert not (set(hist_years) & undrafted), hist_years
    assert not page._errs, page._errs
