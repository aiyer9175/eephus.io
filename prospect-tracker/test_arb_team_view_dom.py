# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/arbitration/#teams, read in a browser (2026-09-24, M08-08).

The Team View counted every board row as "Arb-eligible" (WSN 39, of which 9
carry an arbitration class) and summed PRE-ARB rungs at the league minimum into
"arbitration cost" (38% of the league total). The Franchise chip that links
here said "9 arb of 39 rows". Now the count is the class 1-4 count the
Franchise hub publishes, and every dollar column is split by the rung token.
"""
from __future__ import annotations

import pytest

from conftest import load_data_doc, serve_site


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def _expected():
    board = load_data_doc("arbitration.json")
    if not board or not board.get("rows"):
        pytest.skip("data/arbitration.json not built")
    by = {}
    for r in board["rows"]:
        if not r.get("t"):
            continue
        t = by.setdefault(r["t"], {"n": 0, "cls": 0, "arb": 0, "pre": 0})
        t["n"] += 1
        t["cls"] += 1 if int(r.get("c") or 0) >= 1 else 0
        for s in r.get("l") or []:
            t["pre" if s[4] == "PRE-ARB" else "arb"] += s[1] or 0
    # the split is exhaustive: the two remaining columns add back to tot
    for code, t in by.items():
        own = sum(r.get("tot") or 0 for r in board["rows"] if r.get("t") == code)
        assert t["arb"] + t["pre"] == own, code
    order = sorted(by, key=lambda k: (-by[k]["arb"], -by[k]["pre"]))
    return by, order


_READ = """() => {
  const root = document.getElementById('arb-panel-teams');
  const heads = [...root.querySelectorAll('thead th')].map(t => (t.textContent || '').trim());
  const rows = [...root.querySelectorAll('tbody tr')].map(tr =>
    [...tr.querySelectorAll('td')].map(td => (td.textContent || '').trim()));
  return {heads, rows, note: (root.querySelector('.arb-note') || {}).textContent || ''};
}"""


def test_team_view_counts_classes_and_splits_pre_arb_dollars(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    by, order = _expected()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(server + "arbitration/#teams", wait_until="networkidle", timeout=60_000)
            page.wait_for_selector("#arb-panel-teams tbody tr", timeout=30_000)
            got = page.evaluate(_READ)
        finally:
            browser.close()
    heads = got["heads"]
    assert "Arb-eligible" not in heads
    assert "Arb class 1-4" in heads and "Players" in heads
    assert any(h.endswith("pre-arb min.") for h in heads)
    assert "upper bound" not in got["note"].lower()
    clubs = [r[1] for r in got["rows"]]
    assert len(clubs) == len(order) == 30
    # sorted by remaining arbitration dollars, pre-arb minimums excluded
    assert all(c in r[1] for c, r in zip(order, got["rows"])), (clubs[:5], order[:5])
    for r in got["rows"]:
        code = next(c for c in by if c in r[1])
        assert int(r[2]) == by[code]["n"], code
        assert int(r[3]) == by[code]["cls"], code
