# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The salary path strip fits, and it does not break the table it lives in
(ask C, 2026-09-16).

The strip renders inside the existing `.proj-dt` container of an OPEN row, so
the thing that could break is the pinned detail-row invariant: the visible
colspan sum has to equal the visible header column count, and opening the line
must not move the columns (a colspan past the painted columns adds phantom
columns to a fixed-layout table and crushes the Player column).

This file reuses `_DETAIL` from test_projections_table_fit.py VERBATIM rather
than re-deriving it. The design prototype for this strip measured
`detailCells 7` against `headCells 14` and called that the invariant; it is
neither half of one, and the claim was withdrawn. Importing the real probe is
how it stays withdrawn.

It also pins the two colour facts the first shape of this design got wrong:
NO opacity anywhere on a strip cell (opacity .62 on --text-tertiary composites
to 2.36:1 light and 2.58:1 dark and fails the house rule), and a struck-through
salary at full opacity instead, which measures 4.68:1 light / 4.94:1 dark.
"""
from __future__ import annotations

import pytest

from test_projections_table_fit import _DETAIL, _board_page, server  # noqa: F401

VIEWPORTS = [(1280, 800), (390, 844)]

# Open the first row that actually carries a salary path, measure the detail
# row's height BEFORE and AFTER the strip paints, and read every strip cell.
_STRIP = """async () => {
  const vis = el => getComputedStyle(el).display !== 'none';
  const cs = el => getComputedStyle(el);
  const t = document.querySelector('table.proj-board-table');
  const rows = [...t.querySelectorAll('tbody tr[data-key]')].slice(0, 40);
  // `DATA` is module-scoped in projections.js, so the probe finds its row the
  // way a reader would: open rows until one paints a strip, then close the
  // ones that did not, so the table is left as it was found.
  let tr = null, d = null, hBefore = null;
  for (const r of rows) {
    const before = r.nextElementSibling ? 0 : 0;
    r.querySelector('.proj-xp-btn').click();
    await new Promise(x => setTimeout(x, 40));
    const det = r.nextElementSibling;
    if (det && det.classList.contains('proj-detail') && det.querySelector('.proj-sp')) {
      tr = r; d = det; hBefore = det.getBoundingClientRect().height; break;
    }
    r.querySelector('.proj-xp-btn').click();
    await new Promise(x => setTimeout(x, 10));
  }
  if (!tr) return {noRow: true};
  const strip = d.querySelector('.proj-sp');
  const cells = [...strip.querySelectorAll('.proj-sp-c')];
  // Detail height WITHOUT the strip, measured on the same open row by hiding
  // it, so the delta the strip costs is a measurement and not a memory.
  strip.style.display = 'none';
  const hNoStrip = d.getBoundingClientRect().height;
  strip.style.display = '';
  return {
    key: tr.getAttribute('data-key'),
    hasStrip: true,
    nCells: cells.length,
    detailH: hBefore,
    detailHWithoutStrip: hNoStrip,
    minOpacity: cells.length ? Math.min(...cells.map(c => parseFloat(cs(c).opacity))) : 1,
    estDashed: cells.filter(c => c.classList.contains('is-est'))
                    .every(c => cs(c).borderTopStyle === 'dashed'),
    nEst: cells.filter(c => c.classList.contains('is-est')).length,
    overflow: cells.filter(c => c.scrollWidth > c.clientWidth + 1).length,
    pageScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    cutStruck: cells.filter(c => c.classList.contains('is-cut'))
      .every(c => {
        const s = c.querySelector('.sp-s');
        return s && cs(s).textDecorationLine.indexOf('line-through') >= 0;
      }),
  };
}"""

# A row carrying salTrunc must render is-unk and NEVER is-fa: "2029 FA / not
# controlled" is a served falsehood for a grid that never established a control
# end, and 266 veterans are in exactly that state.
_TRUNC = """async () => {
  const t = document.querySelector('table.proj-board-table');
  const rows = [...t.querySelectorAll('tbody tr[data-key]')].slice(0, 80);
  for (const r of rows) {
    r.querySelector('.proj-xp-btn').click();
    await new Promise(x => setTimeout(x, 30));
    const d = r.nextElementSibling;
    const unk = d ? d.querySelectorAll('.proj-sp-c.is-unk').length : 0;
    if (unk) return {key: r.getAttribute('data-key'), unk: unk,
                     fa: d.querySelectorAll('.proj-sp-c.is-fa').length};
    r.querySelector('.proj-xp-btn').click();
    await new Promise(x => setTimeout(x, 10));
  }
  return {noRow: true};
}"""


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_the_strip_does_not_break_the_detail_row(server, w, h):
    """The REAL pinned invariant, reused verbatim from
    test_projections_table_fit.py:116-118."""
    with _board_page(server, w, h) as page:
        d = page.evaluate(_DETAIL)
        assert d["isDetail"] and d["expanded"] == "true"
        assert d["span"] == d["cols"], f"{w}px: detail spans {d['span']} of {d['cols']} columns"
        assert d["same"], f"{w}px: opening a detail line moved the columns"
        assert d["pageScroll"] <= 0


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_the_strip_fits_and_carries_no_opacity(server, w, h):
    with _board_page(server, w, h) as page:
        s = page.evaluate(_STRIP)
        if s.get("noRow"):
            pytest.skip("no served row carries a salary path yet (mode off, or pre-regen)")
        assert s["hasStrip"] and s["nCells"] >= 1, s
        assert s["pageScroll"] <= 0, f"{w}px: the strip made the page scroll sideways"
        assert s["overflow"] == 0, f"{w}px: {s['overflow']} strip cells overflow their box"
        # R4: the cut cell carries NO opacity. The struck salary says the same
        # thing at full contrast.
        assert s["minOpacity"] == 1, f"{w}px: a strip cell is at opacity {s['minOpacity']}"
        if s["nEst"]:
            assert s["estDashed"], f"{w}px: an estimated season is not drawn dashed"
        assert s["cutStruck"], f"{w}px: a not-tendered salary is not struck through"
        # concern 12b: the design's "106 -> 125" was two POST-injection numbers
        # at different widths and was withdrawn. This is the real delta, at one
        # width, published in the test output.
        print(f"salary strip {w}px: {s['nCells']} cells, detail row "
              f"{s['detailHWithoutStrip']:.0f}px -> {s['detailH']:.0f}px "
              f"(+{s['detailH'] - s['detailHWithoutStrip']:.0f}px)")


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_a_row_with_no_established_window_never_claims_a_free_agent_year(server, w, h):
    with _board_page(server, w, h) as page:
        s = page.evaluate(_TRUNC)
        if s.get("noRow"):
            pytest.skip("no served row carries salTrunc yet")
        assert s["unk"] == 1, f"{s['key']}: expected one is-unk cell, got {s['unk']}"
        assert s["fa"] == 0, f"{s['key']}: rendered a free-agent year it cannot know"
