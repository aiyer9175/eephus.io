# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Consensus FV sort actually sorts the PROSPX board by consensus FV.

WHY THIS EXISTS (census M01-01, 2026-09-24, four verifiers CONFIRMED). The "Consensus
FV" sort option and the Rank-by Consensus toggle both write state.sort = "fv", and
getFilteredActives had no branch for it, so the pool kept its raw payload order: the
baked board order with the provisional rows appended. The consensus badges printed out
of order (Lackey 55 above Gillen 57, Sirota 54 above Cholowsky 57; 888 adjacent
inversions of the printed badge over 4,678 graded pairs) and Seth Hernandez, tied
second on consensus at 59, sat at row 78. With the reverse flag set, every
no-consensus provisional row floated to the top.

Contract pinned here:
  * the printed consensus integer (fv_close) never rises down the real-consensus block;
  * placeholder rows (no source published an FV; the 35 is a fixed anchor) sit below
    every real grade, and rows with no consensus sit below those, in both directions;
  * the toggle and the dropdown give the same order.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
DATA = ROOT / "data"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


# ---------------------------------------------------------------------------
# 1. Wiring
# ---------------------------------------------------------------------------

def test_the_sort_chain_has_a_consensus_branch():
    fn = _function_source(_src(), "getFilteredActives")
    m = re.search(r'else if \(state\.sort === "fv"\) \{(.*?)\n  \} else if', fn, re.S)
    assert m, ("getFilteredActives has no state.sort === \"fv\" branch, so the Consensus "
               "FV sort and the Rank-by Consensus toggle leave the pool unsorted")
    assert "consensusSortCmp(a, b, _rev)" in m.group(1)


def test_fv_handles_its_own_direction():
    m = re.search(r"const _INTERNAL_DIR_MAIN_SORTS = new Set\(\[(.*?)\]\);", _src(), re.S)
    assert m and '"fv"' in m.group(1), (
        "fv must be in _INTERNAL_DIR_MAIN_SORTS: its comparator flips only the real-consensus "
        "term, and a blanket reverse would float every no-consensus row to the top")


# ---------------------------------------------------------------------------
# 2. The comparator in V8
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    ctx = mr.MiniRacer()
    # getEfv and fvCmpDesc are stubbed: the eFV tie order is fvCmpDesc's own contract,
    # pinned elsewhere. Here it is eFV descending, then key.
    ctx.eval("function getEfv(p) { return p ? (p._x || null) : null; }"
             " function fvCmpDesc(a, b) { return ((b.efv || 0) - (a.efv || 0))"
             " || String(a.player_key).localeCompare(String(b.player_key)); }")
    ctx.eval(_function_source(src, "consensusSortTier"))
    ctx.eval(_function_source(src, "consensusSortCmp"))
    return ctx


_ROWS = """[
  {player_key: "prov_hi", _is_provisional: true, efv: 60},
  {player_key: "ph_hi", fv_close: 35, fv_close_raw: 35, efv: 55, _x: {consensus_is_placeholder: true}},
  {player_key: "ph_lo", fv_close: 35, fv_close_raw: 35, efv: 30, _x: {consensus_is_placeholder: true}},
  {player_key: "real34", fv_close: 34, fv_close_raw: 33.6, efv: 20, _x: {}},
  {player_key: "g57b", fv_close: 57, fv_close_raw: 56.25, efv: 58, _x: {}},
  {player_key: "g55", fv_close: 55, fv_close_raw: 54.79, efv: 61, _x: {}},
  {player_key: "g57a", fv_close: 57, fv_close_raw: 56.45, efv: 50, _x: {}},
  {player_key: "g57c", fv_close: 57, fv_close_raw: 56.45, efv: 52, _x: {}},
  {player_key: "prov_lo", _is_provisional: true, efv: 21}
]"""


def _order(js, rev: bool) -> list[str]:
    return json.loads(js.eval(
        "JSON.stringify(%s.sort((a, b) => consensusSortCmp(a, b, %s)).map(p => p.player_key))"
        % (_ROWS, "true" if rev else "false")))


def test_forward_order_is_printed_grade_then_decimal_then_tiers(js):
    assert _order(js, False) == [
        "g57c", "g57a",         # 57 on 56.45, tie broken by eFV
        "g57b",                 # 57 on 56.25
        "g55", "real34",        # real grades, highest first
        "ph_hi", "ph_lo",       # placeholder 35 below a real 34, eFV order inside
        "prov_hi", "prov_lo",   # no consensus at all, eFV order inside
    ]


def test_reverse_flips_only_the_real_block(js):
    assert _order(js, True) == [
        "real34", "g55", "g57b", "g57c", "g57a",
        "ph_hi", "ph_lo", "prov_hi", "prov_lo",
    ]


# ---------------------------------------------------------------------------
# 3. The served artifacts through the real comparator
# ---------------------------------------------------------------------------

def test_served_board_prints_consensus_badges_in_order(js, timeseries_doc):
    xpath = DATA / "xfv.json"
    if not xpath.exists():
        pytest.skip("data/xfv.json not built")
    by = json.loads(xpath.read_text(encoding="utf-8")).get("by_player") or {}
    rows = []
    for p in timeseries_doc.get("players") or []:
        if not p or not p.get("player_key"):
            continue
        x = by.get(p["player_key"]) or {}
        rows.append({"player_key": p["player_key"], "fv_close": p.get("fv_close"),
                     "fv_close_raw": p.get("fv_close_raw"), "efv": x.get("xfv_grade"),
                     "_x": {"consensus_is_placeholder": bool(x.get("consensus_is_placeholder"))}})
    upath = DATA / "xfv_ungraded.json"
    if upath.exists():
        ung = json.loads(upath.read_text(encoding="utf-8")).get("by_player") or {}
        graded = {r["player_key"] for r in rows}
        rows += [{"player_key": k, "_is_provisional": True, "efv": (e or {}).get("xfv_grade")}
                 for k, e in ung.items() if k not in graded]
    out = json.loads(js.eval(
        "JSON.stringify(%s.sort((a, b) => consensusSortCmp(a, b, false))"
        ".map(p => [consensusSortTier(p), p.fv_close == null ? null : Number(p.fv_close)]))"
        % json.dumps(rows)))
    tiers = [t for t, _ in out]
    assert tiers == sorted(tiers), "a placeholder or no-consensus row sits above a real grade"
    real = [v for t, v in out if t == 0]
    assert real, "no real consensus grades on the served board; this check proved nothing"
    bad = [(i, real[i - 1], real[i]) for i in range(1, len(real)) if real[i] > real[i - 1]]
    assert not bad, f"printed consensus badge rises down the list at {bad[:5]}"


# ---------------------------------------------------------------------------
# 4. The rendered board
# ---------------------------------------------------------------------------

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
        # The filter bar opens closed (site pass REDESIGN_prospx); a stored choice
        # opens it so the Rank-by toggle inside it is clickable.
        page.add_init_script(
            "try{localStorage.setItem('prospect-tracker.gate-unlocked','1');"
            "localStorage.setItem('prospect-tracker.filters.filter-bar','open')}catch(e){}")
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
            pass
        yield page, errs
        browser.close()


_MEASURE = """() => {
  const f = getFilteredActives();
  const tier = p => consensusSortTier(p);
  let rise = 0, tierUp = 0;
  for (let i = 1; i < f.length; i++) {
    if (tier(f[i]) < tier(f[i - 1])) tierUp++;
    if (tier(f[i]) === 0 && tier(f[i - 1]) === 0
        && Number(f[i].fv_close) > Number(f[i - 1].fv_close)) rise++;
  }
  return {sort: state.sort, rise, tierUp, n0: f.filter(p => tier(p) === 0).length,
          keys: f.slice(0, 200).map(p => p.player_key)};
}"""


def test_rank_by_consensus_sorts_the_rendered_board(booted_page):
    page, errs = booted_page
    page.click("[data-grade-toggle='fv']")
    page.wait_for_timeout(1500)
    tog = page.evaluate(_MEASURE)
    assert tog["sort"] == "fv"
    assert tog["n0"] > 0
    assert tog["rise"] == 0, f"{tog['rise']} printed consensus badges rise down the board"
    assert tog["tierUp"] == 0, "a placeholder or no-consensus row sits above a real grade"

    page.click("[data-grade-toggle='xfv']")
    page.wait_for_timeout(800)
    page.select_option("#sort-select", "fv")
    page.wait_for_timeout(1500)
    drop = page.evaluate(_MEASURE)
    assert drop["keys"] == tog["keys"], "the dropdown and the toggle give different orders"

    page.evaluate("() => { state.sortRev = state.sortRev || {}; state.sortRev.sort = true; }")
    rev = page.evaluate(_MEASURE)
    page.evaluate("() => { state.sortRev.sort = false; }")
    assert rev["tierUp"] == 0, (
        "reversing the consensus sort floated placeholder or no-consensus rows to the top")
    assert not errs, "JS errors:\n  " + "\n  ".join(errs)


# ---------------------------------------------------------------------------
# 5. PV-07: the default eFV order keeps the not-yet-graded section last
# ---------------------------------------------------------------------------
# Owner answers PG-Q1 / PG-Q2 (2026-09-25): rows no label source has graded leave the
# shared eFV rank for the "Not yet graded by any source" section. In the consensus sort
# they already sank (no consensus grade); in the default eFV order they now sit below
# every graded row, in both directions, under one section header, with no "#" rank.

_MEASURE_XFV = """() => {
  const f = getFilteredActives();
  const flags = f.map(p => inProvSection(p));
  const first = flags.indexOf(true), lastGraded = flags.lastIndexOf(false);
  const rankedSec = f.filter(p => inProvSection(p) && boardRankOf(p) != null).length;
  return {sort: state.sort, on: provSectionOn(), n: f.length, nsec: flags.filter(Boolean).length,
          first, lastGraded, rankedSec};
}"""


def test_default_order_puts_the_section_after_every_graded_row(booted_page):
    page, errs = booted_page
    page.click("[data-grade-toggle='xfv']")
    page.select_option("#sort-select", "xfv")
    page.wait_for_timeout(1500)
    m = page.evaluate(_MEASURE_XFV)
    if not m["on"]:
        pytest.skip("served payload carries no prov_section block (exported before PV-07)")
    assert m["nsec"] > 0
    assert m["first"] == m["lastGraded"] + 1, f"a section row sits above a graded row: {m}"
    assert m["rankedSec"] == 0, "a section row carries a board rank"
    page.evaluate("() => { state.sortRev = state.sortRev || {}; state.sortRev.sort = true; }")
    rev = page.evaluate(_MEASURE_XFV)
    page.evaluate("() => { state.sortRev.sort = false; }")
    assert rev["first"] == rev["lastGraded"] + 1, "reversing the eFV order floated the section up"
    # the section header renders once, on the page where the section starts
    pg = page.evaluate("""() => { const n = state.pageSizes.actives || 50;
      const f = getFilteredActives(); return Math.floor(f.findIndex(p => inProvSection(p)) / n) + 1; }""")
    page.evaluate("(pg) => { state.pages.actives = pg; render(); }", pg)
    page.wait_for_timeout(800)
    heads = page.evaluate("() => document.querySelectorAll('#rows .prov-section-head:not(.is-continued)').length")
    assert heads == 1
    page.evaluate("() => { state.pages.actives = 1; render(); }")
    assert not errs, "JS errors:\n  " + "\n  ".join(errs)
