# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/arbitration/#history renders every settled season it serves (2026-09-25).

The History table printed rows.slice(0, 400) of a season-descending list with
no count and no season control. On the 2026-09-23 artifact that hid 372 of 772
rows: all 236 from 2023, the 136 lowest-paid of 2024, and 254 of the 282 MLBTR
figures the Model tab's Swartz tile rests on. Now every row is reachable under
a season filter, and a count line says how many rows show and how many carry an
MLBTR projection. Since 2026-10-03 the table paints 100 rows at a time like the
board; Show all reaches the rest.
"""
from __future__ import annotations

import pytest

from conftest import load_data_doc, serve_site


_READ = """() => {
  const root = document.getElementById('arb-panel-history');
  const rows = [...root.querySelectorAll('tbody tr')].map(tr =>
    [...tr.querySelectorAll('td')].map(td => (td.textContent || '').trim()));
  const chips = [...root.querySelectorAll('[data-hseason]')].map(b => b.getAttribute('data-hseason'));
  return {rows, chips, count: (root.querySelector('.arb-histcount') || {}).textContent || ''};
}"""


def test_history_renders_every_row_and_filters_by_season():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    hist = load_data_doc("arb_history.json")
    if not hist or not hist.get("rows"):
        pytest.skip("data/arb_history.json not built")
    rows = hist["rows"]
    seasons = sorted({str(r[0]) for r in rows}, reverse=True)
    n_sw = sum(1 for r in rows if r[7] is not None)
    oldest = seasons[-1]
    n_old = sum(1 for r in rows if str(r[0]) == oldest)
    with serve_site() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "arbitration/#history", wait_until="networkidle", timeout=60_000)
            page.wait_for_selector("#arb-panel-history tbody tr", timeout=30_000)
            first = page.evaluate(_READ)
            page.eval_on_selector('[data-hmore="all"]', "b => b.click()")
            page.wait_for_timeout(200)
            full = page.evaluate(_READ)
            page.eval_on_selector(f'[data-hseason="{oldest}"]', "b => b.click()")
            page.wait_for_timeout(200)
            one_first = page.evaluate(_READ)
            if n_old > 100:
                page.eval_on_selector('[data-hmore="all"]', "b => b.click()")
                page.wait_for_timeout(200)
            one = page.evaluate(_READ)
        finally:
            browser.close()
    assert not errors, errors
    assert len(first["rows"]) == min(100, len(rows))
    assert f"Showing {min(100, len(rows))} of {len(rows)}" in first["count"], first["count"]
    assert len(one_first["rows"]) == min(100, n_old)
    assert len(full["rows"]) == len(rows), (len(full["rows"]), len(rows))
    assert full["chips"] == ["all"] + seasons
    assert f"Showing {len(rows)} of {len(rows)}" in full["count"], full["count"]
    assert f"{n_sw} of them carry an MLBTR projection" in full["count"], full["count"]
    # the oldest season is reachable, which the 400-row cut made impossible
    assert len(one["rows"]) == n_old
    assert all(r[1] == oldest for r in one["rows"])
    assert f"Showing {n_old} of {len(rows)}" in one["count"], one["count"]
