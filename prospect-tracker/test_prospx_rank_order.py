# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The printed eFV rank equals the row's position on the default PROSPX board.

WHY THIS EXISTS (census M01-03, 2026-09-24, two verifiers CONFIRMED). The board sort
ordered every pair by efvRankValue then fvCmpDesc, but the rank maps (current and
previous), the org-rank map, the farm top-3 strip and the watchlist top prospect
returned 0 for any tie that involved a provisional row, and the farm roster and
provOrgRank sorted on efvRankValue alone. Stable sort then left tied provisional rows in
payload key order, grouped by org. 3,201 of 8,071 rank chips printed a number that was
not their position (1,687 off by 10 or more, the worst by 677); page 16 ended
"#798, #801, #799" and page 17 opened with "#800".

Contract pinned here:
  * one comparator, boardCmp, and no site returns 0 for a provisional tie;
  * on the rendered default board, getEfvRank(row i) == i + 1 for every row;
  * getEfvOrgRank equals the row's index in its org pool under the roster's sort;
  * every printed rank chip, page by page, reads its row position.
"""
from __future__ import annotations

import re

import pytest
from conftest import serve_site

from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def test_no_sort_site_zeroes_a_provisional_tie():
    src = _src()
    assert not re.search(r"_is_provisional\s*\|\|\s*b\._is_provisional\)\s*\?\s*0", src), (
        "a comparator still returns 0 for ties involving a provisional row, so tied "
        "provisional rows keep payload order and their rank chips disagree with the board")


def test_one_comparator_serves_every_board_order_site():
    src = _src()
    m = re.search(r"^function boardCmp\(a, b\) \{\n(.*?)\n\}\n", src, re.S | re.M)
    assert m, "boardCmp is missing from prospx/index.html"
    assert "efvRankValue(b) - efvRankValue(a) || fvCmpDesc(a, b)" in m.group(1)
    for site in ("pool.sort(boardCmp);",            # board branch, rank map, provOrgRank
                 "byOrg[o].sort(boardCmp);",        # org-rank map
                 "_wlPool.sort(boardCmp);",         # watchlist top prospect
                 "_orgPool.sort(boardCmp);",        # farm top 3
                 "return boardCmp(a, b);",          # farm roster default sort
                 ".sort(boardCmp)"):                # farm GFX top 5
        assert site in src, f"{site} not found: that surface can order ties differently"
    # The roster must not fall back to a bare efvRankValue difference with no tiebreak.
    assert not re.search(r"fv: \(a, b\) => \{[^}]*return efvRankValue\(b\) - efvRankValue\(a\);",
                         src, re.S)


@pytest.fixture(scope="module")
def booted_page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        page.goto(base + "prospx/index.html", wait_until="load", timeout=60_000)
        page.wait_for_function(
            "() => document.querySelectorAll('#rows .player-row').length > 5", timeout=120_000)
        try:
            page.wait_for_function(
                "() => typeof provPlayers === 'function' && provPlayers().length > 0",
                timeout=60_000)
        except Exception:
            pytest.skip("the provisional pool never loaded; the tie blocks are not on the board")
        page.wait_for_timeout(800)
        yield page, errs
        browser.close()


_MEASURE = """() => {
  buildEfvRankMap();
  _EFV_ORG_RANK = null;
  const f = getFilteredActives();
  let mis = 0, ge10 = 0, maxAbs = 0, first = null;
  for (let i = 0; i < f.length; i++) {
    const r = getEfvRank(f[i]);
    if (r !== i + 1) {
      mis++;
      const d = Math.abs((r || 0) - (i + 1));
      if (d >= 10) ge10++;
      if (d > maxAbs) maxAbs = d;
      if (first == null) first = i + 1;
    }
  }
  const orgs = {};
  for (const p of f) if (p && p.org) orgs[p.org] = 1;
  let orgMis = 0, orgRows = 0;
  for (const o of Object.keys(orgs)) {
    const pool = oneRowOrgPool(o).filter(p => p && p.player_key)
      .sort((a, b) => efvRankValue(b) - efvRankValue(a) || fvCmpDesc(a, b));
    pool.forEach((p, i) => {
      orgRows++;
      const r = getEfvOrgRank(p);
      if (!r || r.rank !== i + 1) orgMis++;
    });
  }
  return {sort: state.sort, n: f.length, nProv: f.filter(p => p._is_provisional).length,
          mis, ge10, maxAbs, first, orgMis, orgRows};
}"""


def test_rank_chip_equals_board_position(booted_page):
    page, errs = booted_page
    m = page.evaluate(_MEASURE)
    assert m["sort"] == "xfv", "the default board sort is not eFV; this check proved nothing"
    assert m["nProv"] > 0, "no provisional rows on the board; the tie blocks were not tested"
    assert m["mis"] == 0, (
        f"{m['mis']} of {m['n']} rows print a rank that is not their position "
        f"({m['ge10']} off by 10 or more, worst {m['maxAbs']}, first at #{m['first']})")
    assert m["orgRows"] > 0
    assert m["orgMis"] == 0, (
        f"{m['orgMis']} of {m['orgRows']} org ranks differ from the roster's order")
    assert not errs, "JS errors:\n  " + "\n  ".join(errs)


def test_printed_chips_read_in_order_on_every_page(booted_page):
    page, _ = booted_page
    out = page.evaluate("""() => {
      const size = state.pageSizes.actives || 50;
      const pages = Math.ceil(getFilteredActives().length / size);
      let bad = 0, seen = 0, firstBad = null;
      for (let pg = 1; pg <= pages; pg++) {
        state.pages.actives = pg;
        render();
        const chips = Array.from(document.querySelectorAll('#rows .player-row .rank-num-inner'))
          .map(e => Number(e.textContent.replace(/[^0-9]/g, '')));
        chips.forEach((c, i) => {
          seen++;
          if (c !== (pg - 1) * size + i + 1) { bad++; if (firstBad == null) firstBad = [pg, i, c]; }
        });
      }
      state.pages.actives = 1;
      render();
      return {bad, seen, pages, firstBad};
    }""")
    assert out["seen"] > 1000, f"only {out['seen']} rank chips painted over {out['pages']} pages"
    assert out["bad"] == 0, (
        f"{out['bad']} of {out['seen']} printed rank chips differ from their row position; "
        f"first at page/row/chip {out['firstBad']}")
