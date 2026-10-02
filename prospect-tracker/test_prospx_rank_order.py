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

Census M01-04 (display half). storage bakes overall_rank over graded rows only; the live
board also ranks the provisional pool, so the baked rank differed from the chip on 4,493
of 4,679 graded rows and the "Last board #N" pill (detail header, GFX card) read as a fall
that never happened. The pill is retired, and the leaderboard rank caps and the scatter
rank axis read the rank the chip prints (boardRankOf). Re-basing the baked rank itself is
an owner question (canonical pool) and is not pinned here.

PV-07 (owner answers PG-Q1 / PG-Q2, 2026-09-25) answered it: rows no label source has
graded leave the shared rank for the section "Not yet graded by any source", which sorts
after every graded row. The live rank and the baked overall_rank now count the same pool,
the graded rows, so a printed #N is the row's position among graded rows; a section row
prints no rank (its chance of a first grade instead) and holds its place in the section.
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
                 ".filter(p => !inProvSection(p)).sort(boardCmp);",   # org-rank map (PV-07)
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
  let mis = 0, ge10 = 0, maxAbs = 0, first = null, secMis = 0, nSec = 0;
  const nGraded = f.filter(p => !inProvSection(p)).length;
  for (let i = 0; i < f.length; i++) {
    if (inProvSection(f[i])) {
      nSec++;
      const sp = provSectionPos(f[i]);
      if (getEfvRank(f[i]) != null || !sp || sp.pos !== i + 1 - nGraded) secMis++;
      continue;
    }
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
    const pool = oneRowOrgPool(o).filter(p => p && p.player_key && !inProvSection(p))
      .sort((a, b) => efvRankValue(b) - efvRankValue(a) || fvCmpDesc(a, b));
    pool.forEach((p, i) => {
      orgRows++;
      const r = getEfvOrgRank(p);
      if (!r || r.rank !== i + 1) orgMis++;
    });
  }
  return {sort: state.sort, n: f.length, nProv: f.filter(p => p._is_provisional).length,
          mis, ge10, maxAbs, first, orgMis, orgRows, secMis, nSec, nGraded};
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
    assert m["secMis"] == 0, (
        f"{m['secMis']} of {m['nSec']} section rows carry a board rank or a section place "
        "that is not their position below the graded rows")
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
        const rows = Array.from(document.querySelectorAll('#rows .player-row'));
        rows.forEach((row, i) => {
          const el = row.querySelector('.rank-num-inner');
          if (!el) return;
          const t = el.textContent;
          seen++;
          if (row.querySelector('.rank-num-prov')) {          // PV-07 section row: no rank
            if (t.includes('#')) { bad++; if (firstBad == null) firstBad = [pg, i, t]; }
            return;
          }
          const c = Number(t.replace(/[^0-9]/g, ''));
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


def test_last_board_pill_is_retired():
    src = _src()
    assert 'rankPill("Last board"' not in src
    assert "`Last board #" not in src


def test_rank_caps_read_the_printed_rank():
    src = _src()
    assert "Number(p.overall_rank) <= rankCap" not in src
    assert "Number(p.overall_rank) <= _rankCap" not in src
    assert src.count("boardRankOf(p) <= rankCap") == 1
    assert src.count("boardRankOf(p) <= _rankCap") == 1


def test_detail_header_prints_one_overall_rank(booted_page):
    page, errs = booted_page
    key = page.evaluate("""() => {
      const f = getFilteredActives();
      const g = f.find(p => !p._is_provisional && p.overall_rank != null
                        && getEfvRank(p) != null && getEfvRank(p) - p.overall_rank >= 10);
      return g ? g.player_key : null;
    }""")
    if not key:
        pytest.skip("no graded row whose baked and live ranks differ; the pill could not fire")
    page.evaluate(f"() => {{ location.hash = 'player={key}'; }}")
    page.wait_for_function(
        "() => { const b = document.getElementById('player-detail-body');"
        " return b && /Overall eFV/i.test(b.innerText); }", timeout=30_000)
    txt = page.evaluate("() => document.getElementById('player-detail-body').innerText")
    live = page.evaluate(f"() => getEfvRank(DATA.players.find(p => p.player_key === '{key}'))")
    page.evaluate("() => { location.hash = ''; }")
    assert not re.search(r"Last board", txt, re.I), (
        f"{key}: the detail header still prints a Last board pill beside #{live}")
    assert f"#{live}" in txt
    assert not errs, "JS errors: " + " | ".join(errs)


def test_cold_deep_link_prints_the_board_rank(booted_page):
    """A shared player link never loaded the provisional pool, so its header printed a
    graded-only rank (Andrew Bolivar #2511 on the link, #3728 on the board). Since PV-07
    the board ranks graded rows only too, so the cold link, the board and the baked rank
    print one number."""
    import json
    board, _ = booted_page
    ts = ROOT / "data" / "timeseries.json"
    if not ts.exists():
        pytest.skip("data/timeseries.json not built")
    players = json.loads(ts.read_text(encoding="utf-8")).get("players") or []
    deep = [p for p in players if p.get("player_key") and (p.get("overall_rank") or 0) > 1500
            and p.get("status") != "debuted"]
    if not deep:
        pytest.skip("no graded row deep enough to sit below provisional rows")
    key = deep[0]["player_key"]
    base = board.url.split("#")[0]
    page = board.context.browser.new_page()   # fresh page, nothing loaded: a shared link
    page.add_init_script(
        "try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
    try:
        page.goto(base + "#player=" + key, wait_until="load", timeout=60_000)
        page.wait_for_function(
            "() => typeof provPlayers === 'function' && provPlayers().length > 0",
            timeout=60_000)
        page.wait_for_function(
            "(k) => { const b = document.getElementById('player-detail-body');"
            " const p = DATA.players.find(q => q.player_key === k);"
            " return b && p && b.innerText.includes('#' + getEfvRank(p)); }",
            arg=key, timeout=30_000)
        live, baked = page.evaluate(
            "(k) => { const p = DATA.players.find(q => q.player_key === k);"
            " return [getEfvRank(p), p.overall_rank]; }", key)
    finally:
        page.close()
    assert live == baked, (
        f"{key}: the cold link prints #{live} and the baked board rank is #{baked}; since "
        "PV-07 both count the graded pool, so they must agree")
