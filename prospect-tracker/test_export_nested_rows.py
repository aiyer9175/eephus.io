# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EephusExport.scrape writes a table's own rows only (PORT_RED_TESTS_CLEAR, 2026-10-26).

The /mlbstats/ Overall caret opens a season line whose cell holds the player drawer,
and the drawer draws a small table of its own. scrapeTable walked every tr under the
first tbody it found, so the drawer's rows reached the file: the hitters CSV held 929
lines for a 928-row board while the Download CSV bar (eephus-csv.js dataRowCount, which
reads tbody.rows) said 928. The scrape now reads table.tBodies[0].rows, the rule the
counter uses, so the file and the bar agree.

Playwright/chromium are optional; the test skips cleanly when unavailable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parent

_PAGE = """<!doctype html><html><body>
<table id="t"><thead><tr><th>Player</th><th>WAR</th></tr></thead>
<tbody>
<tr><td>A</td><td>1.0</td></tr>
<tr class="open" data-export-skip><td colspan="2" data-export-skip>
  <table><tbody><tr><td>2026</td><td>2.6</td></tr><tr><td>2025</td><td>0.4</td></tr></tbody></table>
</td></tr>
<tr><td>B</td><td>2.0</td></tr>
</tbody></table>
<table id="n"><tr><th>Player</th><th>WAR</th></tr><tr><td>C</td><td>3.0</td></tr></table>
</body></html>"""


def test_a_nested_table_never_adds_rows_to_the_file():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip("chromium unavailable: %s" % e)
        try:
            page = browser.new_page()
            page.set_content(_PAGE)
            page.add_script_tag(path=str(ROOT / "assets" / "eephus-export.js"))
            got = page.evaluate("""() => {
              const m = window.EephusExport.scrape(document.getElementById('t'));
              const n = window.EephusExport.scrape(document.getElementById('n'));
              return {headers: m.headers, rows: m.rows, nrows: n.rows};
            }""")
        finally:
            browser.close()
    assert got["headers"] == ["Player", "WAR"]
    # the skipped season line stays out, and so do the rows of the table inside it
    assert got["rows"] == [["A", "1.0"], ["B", "2.0"]]
    assert got["nrows"] == [["C", "3.0"]]
