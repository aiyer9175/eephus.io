# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV-minus-consensus chip is the subtraction of the two PRINTED integers.

Audit finding F43, owner decision 2026-09-04 (docs/efv-2026-09-03/
EWAR_LABEL_EPOCH_GATE.md, Appendix A, "Delta chip computed on displayed values",
NOW / display only / no served number): both display rules stay as they are -
consensus rounds UP (fvCeil, the owner rule), eFV rounds to NEAREST - and the
chip differences what the reader can see, so the three numbers on a card
reconcile. Franklin Arias is the recorded case: consensus 58.1, eFV 60.3, printed
as 58 and 60, and a raw chip of +2.2 there claims 58 + 2.2 = 60.3 next to a badge
reading 60.

The raw delta is NOT retired: efvMinusConsensus keeps one decimal and is what the
xfv_delta and conviction sorts rank on, and what any magnitude filter reads. Only
the printed chip is display arithmetic.

The test drives the real board in a browser rather than reading the source,
because this defect class is invisible in source: every helper here is correct in
isolation and the bug is which one a call site reached for.
"""
from __future__ import annotations

import re

import pytest
from conftest import serve_site

PROSPX = "prospx/index.html"

# Chips we insist on seeing before the assertions mean anything. The live board
# published 1,098 comparisons on 2026-09-04 (8,075 filtered actives, 6,977
# suppressed or unrated); 20 is the floor the lane was written against.
MIN_CHIPS = 20


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@pytest.fixture(scope="module")
def board(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:                              # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page()
        errs: list[str] = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        try:
            page.goto(server + PROSPX, wait_until="load", timeout=90_000)
            try:
                page.wait_for_function(
                    "() => { const r = document.getElementById('rows');"
                    " return !!r && r.children.length > 3; }",
                    timeout=180_000)
            except Exception as exc:                          # noqa: BLE001
                pytest.skip(f"board did not paint rows (data not built?): {exc}")
            yield page, errs
        finally:
            browser.close()


def _scan(page):
    """Every published chip on the filtered pool, with its two display inputs."""
    return page.evaluate(r"""
    () => {
      const pool = getFilteredActives();
      let chips = 0, suppressed = 0, mismatch = 0, sharpened = 0;
      const bad = [];
      for (const p of pool) {
        const x = getEfv(p);
        if (!x || x.xfv_grade == null) continue;
        const d = efvMinusConsensusDisplay(x);
        if (d == null) { suppressed++; continue; }
        chips++;
        const g = efvGradeDisplay(x), c = efvConsensusDisplay(x);
        if (d !== g - c) { mismatch++; if (bad.length < 5) bad.push({k: p.player_key, d, g, c}); }
        // rows where the raw delta would have printed a different number
        const raw = efvMinusConsensus(x);
        if (raw != null && Math.round(Number(raw)) !== d) sharpened++;
      }
      return {pool: pool.length, chips, suppressed, mismatch, sharpened, bad};
    }
    """)


def test_every_chip_is_the_difference_of_the_two_printed_integers(board):
    page, errs = board
    r = _scan(page)
    assert not errs, f"page errors: {errs[:3]}"
    assert r["chips"] >= MIN_CHIPS, f"only {r['chips']} chips on the board: {r}"
    assert r["mismatch"] == 0, f"{r['mismatch']} chips off the printed pair: {r['bad']}"
    # Not vacuous: on a real board the raw value and the printed pair disagree on
    # a substantial minority of rows, which is the whole finding.
    assert r["sharpened"] > 0, (
        "no row where the raw delta rounds to something other than the printed "
        f"difference - the fixture cannot detect a regression: {r}")


def test_suppressed_rows_still_render_no_chip(board):
    """C-6 ratchet. The two withheld cohorts (consensus_is_placeholder, the
    fabricated FV 35 anchor; xfv_grade_is_floor, the outcome map's first knot)
    must stay chipless: this change must not resurrect a comparison C-6 silenced."""
    page, _ = board
    r = page.evaluate(r"""
    () => {
      const pool = getFilteredActives();
      let marked = 0, marked_with_chip = 0;
      for (const p of pool) {
        const x = getEfv(p);
        if (!x || x.xfv_grade == null) continue;
        if (!(x.consensus_is_placeholder || x.xfv_grade_is_floor)) continue;
        marked++;
        if (efvMinusConsensusDisplay(x) != null) marked_with_chip++;
      }
      return {marked, marked_with_chip};
    }
    """)
    assert r["marked"] > 0, "no suppressed rows on the board: fixture is vacuous"
    assert r["marked_with_chip"] == 0, r


def test_the_rendered_badge_and_its_tooltip_reconcile(board):
    """DOM check, not a function check: the number in the badge, the consensus in
    the badge's own tooltip and the chip in it must satisfy badge - consensus = chip."""
    page, _ = board
    pairs = page.evaluate(r"""
    () => Array.from(document.querySelectorAll('#rows .fv-badge'))
      .map(el => ({txt: el.textContent.trim(), title: el.getAttribute('title') || ''}))
    """)
    pat = re.compile(r"Consensus FV (\d+) \(([+-]?\d+)\)")
    checked = 0
    for cell in pairs:
        m = pat.search(cell["title"])
        if not m:
            continue
        grade = re.match(r"^(\d+)", cell["txt"])
        if not grade:
            continue
        cons, chip = int(m.group(1)), int(m.group(2))
        assert int(grade.group(1)) - cons == chip, cell
        checked += 1
    assert checked >= MIN_CHIPS, f"only {checked} rendered chips found on page one"


def test_the_raw_delta_is_still_what_the_gap_sorts_read(board):
    """The owner decision changed the printed chip only. A sort that ranks on the
    rounded chip would flatten the board into integer tie blocks."""
    page, _ = board
    src_uses_raw = page.evaluate(
        "() => typeof efvMinusConsensus === 'function' "
        "&& efvMinusConsensus({xfv_grade: 60.3, consensus_fv: 58.1}) === 2.2")
    assert src_uses_raw, "efvMinusConsensus no longer carries the raw one-decimal delta"


def test_no_raw_basis_delta_chip_renderer_survives_in_the_file():
    """efvDeltaMark printed Math.abs(Math.round(rawDelta)) with a one-decimal raw
    tooltip and had no call sites. It is removed; nothing may re-introduce a chip
    renderer that takes the raw value."""
    from pathlib import Path
    src = (Path(__file__).parent / PROSPX).read_text(encoding="utf-8")
    assert "function efvDeltaMark" not in src
    assert "function efvConsensusDisplay(x)" in src
    i = src.index("function efvMinusConsensusDisplay(x) {")
    body = src[i:i + 400]
    assert "efvGradeDisplay(x)" in body and "efvConsensusDisplay(x)" in body, body
