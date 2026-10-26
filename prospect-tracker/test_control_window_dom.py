# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The two control-window claims that only exist once a browser has run
(owner report 2026-09-17).

  1. /arbitration/ renders NO free-agency step and says "free agent" in no
     aria-label. The board was publishing "FA '29" and "free agent after 2028"
     for a player every other module controls through 2030, invented from
     whatever season Spotrac's grid happened to stop at. Pinned so a future
     "nice touch" cannot put the bookend back.
  2. The /projections/ CSV carries the control window as DATA. A tooltip cannot
     travel in a CSV, and the export was pairing a surplus priced through 2030
     with "Thru 2026" and no control column at all.
"""
from __future__ import annotations

import contextlib

import pytest

from conftest import serve_site


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@contextlib.contextmanager
def _page(server, path, wait_for, w=1280, h=900):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(server + path, wait_until="networkidle", timeout=60_000)
            page.wait_for_selector(wait_for, timeout=30_000)
            page.wait_for_timeout(400)
            yield page
        finally:
            browser.close()


_ARB = """() => {
  const ladders = [...document.querySelectorAll('.arb-ladder')];
  const aria = ladders.map(l => l.getAttribute('aria-label') || '');
  return {
    n: ladders.length,
    faSteps: document.querySelectorAll('.arb-step--fa').length,
    faWords: aria.filter(a => /free agent/i.test(a)).length,
    faGlyph: ladders.filter(l => /(^|\\W)FA(\\W|$)/.test(l.innerText || '')).length,
    ladderYrs: [...document.querySelectorAll('th')].some(t => (t.textContent || '').trim() === 'Ladder yrs'),
    totTitle: [...document.querySelectorAll('th')].some(t => /not of the club control window/.test(t.getAttribute('title') || '')),
    caveat: (document.querySelector('.arb-caveatbar') || {}).textContent || '',
    sample: aria[0] || '',
  };
}"""


def test_the_arbitration_ladder_makes_no_free_agency_claim(server):
    with _page(server, "arbitration/", ".arb-ladder") as page:
        r = page.evaluate(_ARB)
        assert r["n"] > 0, "no ladder rendered"
        assert r["faSteps"] == 0, f"{r['faSteps']} free-agency steps still render"
        assert r["faWords"] == 0, f"{r['faWords']} aria-labels still say 'free agent'"
        assert r["faGlyph"] == 0, f"{r['faGlyph']} ladders still print an FA token"
        assert r["ladderYrs"], "the Yrs column is still called Yrs"
        assert r["totTitle"], "Total remaining does not say it is not the control window"
        assert "club control ends" in r["caveat"], (
            "the caveat bar does not say the ladder is not a control-end statement")
        print("arbitration aria sample:", r["sample"][:160])


_CSV = """(name) => {
  const t = document.querySelector('table.proj-board-table');
  const X = window.EephusExport;
  const model = X && X.scrape ? X.scrape(t) : null;
  if (!model) return {noExport: true};
  const idx = k => model.headers.indexOf(k);
  const rows = {};
  model.rows.forEach(r => { rows[r[idx('Player')]] = r; });
  return {headers: model.headers, iGuar: idx('Guaranteed thru'),
          iCtrl: idx('Control thru'), iBasis: idx('Control basis'),
          caminero: rows[name] || null,
          nRows: model.rows.length,
          widthOk: model.rows.every(r => r.length === model.headers.length)};
}"""


# The player the export is read on: the first served row whose guarantee ends
# before his club control does (basis contract+arb). The owner's report named Junior
# Caminero (2026-09-17), whose 2026 guarantee ran out with the season, so the row is
# taken from the payload rather than pinned by name.
_PICK = """async () => {
  const d = await (await fetch('/data/mlb_projections.json')).json();
  const m = (d.vets || []).find(v => v.salSrc === 'contract+arb' && v.thru && v.ctrlThru > v.thru);
  return m ? m.name : null;
}"""


def test_the_csv_carries_the_control_window(server):
    with _page(server, "projections/", "table.proj-board-table tbody tr[data-key]") as page:
        name = page.evaluate(_PICK)
        if name is None:
            pytest.skip("no served row has a guarantee that ends before his club control")
        page.fill("#proj-q", name)
        page.wait_for_timeout(600)
        r = page.evaluate(_CSV, name)
        if r.get("noExport"):
            pytest.skip("eephus-export.js not loaded on this build")
        for h in ("Guaranteed thru", "Control thru", "Control basis"):
            assert h in r["headers"], f"{h} missing from the export: {r['headers']}"
        assert r["widthOk"], "an exported row does not paint the header's columns"
        cam = r["caminero"]
        assert cam is not None, f"{name} is not in the export after searching for him"
        guar, ctrl, basis = cam[r["iGuar"]], cam[r["iCtrl"]], cam[r["iBasis"]]
        assert ctrl and ctrl != guar, f"control {ctrl!r} vs guarantee {guar!r}"
        assert int(str(ctrl).rstrip("+")) > int(guar)
        assert basis == "contract+arb", basis
        print(f"csv {name}: guaranteed {guar}, control {ctrl}, basis {basis}")


_CELL = """() => {
  const t = document.querySelector('table.proj-board-table');
  const out = {open: null, est: null, signed: null, none: null, nCells: 0, fa: 0};
  [...t.querySelectorAll('tbody tr[data-key] td.pc-ct')].forEach(td => {
    const pill = td.querySelector('.proj-ct');
    if (!pill) return;
    out.nCells++;
    const txt = (pill.innerText || '').trim();
    const sub = (td.querySelector('.proj-ct-sub') || {}).innerText || '';
    const tip = pill.getAttribute('title') || '';
    if (/free agent/i.test(tip) || /free agent/i.test(sub)) out.fa++;
    const rec = {txt: txt, sub: sub.trim(), tip: tip,
                 cls: pill.getAttribute('class'),
                 dashed: getComputedStyle(pill).borderTopStyle};
    if (pill.classList.contains('proj-ct-open')) out.open = out.open || rec;
    else if (pill.classList.contains('proj-ct-est')) out.est = out.est || rec;
    else if (pill.classList.contains('proj-ct-signed')) out.signed = out.signed || rec;
    else if (pill.classList.contains('proj-ct-none')) out.none = out.none || rec;
  });
  return out;
}"""


_CTRL_BUCKET = """() => {
  const rows = [...document.querySelectorAll('table.proj-board-table tbody tr[data-key]')];
  const bad = [];
  rows.forEach(tr => {
    const td = tr.querySelector('td.pc-ct');
    const pill = td && td.querySelector('.proj-ct');
    if (!pill) return;
    if (pill.classList.contains('proj-ct-signed')) {
      const sub = td.querySelector('.proj-ct-sub');
      bad.push(tr.getAttribute('data-key') + ' -> ' + (pill.innerText || '').trim()
               + ' / ' + (sub ? (sub.innerText || '').trim() : ''));
    }
  });
  return {n: rows.length, bad: bad.slice(0, 8)};
}"""


def test_the_club_control_filter_holds_only_club_controlled_players(server):
    """THE BUCKET AND THE CELL ARE ONE CLAIM, and for one revision of this
    change they disagreed on 347 rows. The filter read `thru` alone, so 226
    upcoming free agents whose guarantee ended in the season in progress were
    chipped, coloured and legended "Club control" - and rendered, four columns
    away, as a solid `2026 / guaranteed` cell. The mirror half put 121
    genuinely controlled players in "Expiring" under a tip promising free
    agency.

    One assertion catches both, and the second defect too: inside
    `#contract=ctrl` no cell may be the SIGNED cell. A row in this bucket is
    controlled past its guarantee or its window is open, and either way its
    cell is dashed or carries a `+`. A solid "guaranteed" cell here is either a
    free agent who does not belong in the bucket or an open window rendering
    the contract-only branch."""
    with _page(server, "projections/#contract=ctrl",
               "table.proj-board-table tbody tr[data-key]") as page:
        r = page.evaluate(_CTRL_BUCKET)
        assert r["n"] > 0, "the Club control filter rendered no rows"
        assert not r["bad"], (
            f"{len(r['bad'])}+ rows inside the Club control bucket render the "
            f"guaranteed cell: {r['bad']}")
        print(f"club control bucket: {r['n']} rows, 0 guaranteed cells")


def test_the_control_cell_says_what_it_means(server):
    """Every bucket the design enumerates, read off the rendered page: the
    projected span is dashed, the open span ends in `+` and says "at least",
    the contract-only span is solid and keeps the guarantee word, and no cell
    anywhere says "free agent" - that word lives only in the salary path
    strip's own bookend."""
    with _page(server, "projections/", "table.proj-board-table tbody tr[data-key]") as page:
        r = page.evaluate(_CELL)
        assert r["nCells"] > 0
        assert r["fa"] == 0, "a Control cell claims a free agency year"
        if r["est"]:
            e = r["est"]
            assert e["dashed"] == "dashed", e
            assert "Club control through" in e["tip"], e["tip"]
            assert "at least" not in e["tip"], e["tip"]
            assert e["sub"].startswith("guar.") or e["sub"] == "no deal on file", e
            print("est cell:", e["txt"], "|", e["sub"], "|", e["tip"][:110])
        if r["open"]:
            o = r["open"]
            assert o["txt"].endswith("+"), o
            assert "through at least" in o["tip"], o["tip"]
            assert "guaranteed" not in o["tip"].lower() or "Guaranteed through" in o["tip"], o
            assert "proj-ct-signed" not in (o["cls"] or ""), o
            print("open cell:", o["txt"], "|", o["sub"], "|", o["tip"][:110])
        if r["signed"]:
            s = r["signed"]
            assert s["dashed"] != "dashed", s
            assert "Guaranteed through" in s["tip"], s["tip"]
            assert s["sub"] == "guaranteed", s
        if r["none"]:
            assert r["none"]["txt"] == "none", r["none"]
