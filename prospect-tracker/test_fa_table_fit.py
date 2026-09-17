# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /fa/ Class Board table fits the screen (owner ask B, 2026-09-16).

The MiniRacer smoke test pins the markup but has no CSS, so it cannot see the
column tiers (@container faboard in site.css). This drives the served page in
headless Chromium at a laptop and a phone and pins what the table promises: no
sideways page scroll, a header that sticks, the predicted deal (verdict, AAV,
term, guarantee) on every width, the status and the age still readable once
their columns fold, 24px sort targets, and a detail line that paints exactly as
many cells as the header (a colspan past the painted columns adds phantom
columns to a fixed-layout table and crushes the Player column).

Four more cases guard decisions the card board did not have to make: the sort
control is the ONLY route to downside WAR, star odds and prior AAV, which have
no column at any width, so it can never be hidden, and it sits on its own row
above the filter bar because the bar measured 43px with it outside and 73px
with it inside at 1440, 1280, 1100 and 1024; the gold option marker has to
follow the first cell that actually paints, which stops being the rank cell
once the 891px tier hides it; .fa-sort left the shared
coarse-pointer overlay list in the same commit, because an 11px outset overlay
on a button that fills its own header cell would overlap its neighbours by 16px
and reach into row 1; and the Status cell leads with a word rather than a price
and a percentage, whose meaning depended on the type pill 300px away.
"""
from __future__ import annotations

import contextlib

import pytest

from conftest import serve_site

VIEWPORTS = [(1280, 800), (390, 844)]


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@contextlib.contextmanager
def _board_page(server, w, h, hash_="", coarse=False):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            if coarse:
                # A touch device: this is what turns on the (pointer: coarse)
                # block, which is where the 36px sort target and the 16px field
                # size live.
                ctx = browser.new_context(viewport={"width": w, "height": h},
                                          is_mobile=True, has_touch=True)
                page = ctx.new_page()
            else:
                page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(server + "fa/" + hash_, wait_until="networkidle", timeout=60_000)
            page.wait_for_selector("table.fa-board-table tbody tr[data-key]", timeout=30_000)
            page.wait_for_timeout(400)
            yield page
        finally:
            browser.close()


_FIT = """() => {
  const de = document.documentElement, vis = el => el && getComputedStyle(el).display !== 'none';
  const t = document.querySelector('table.fa-board-table');
  const wrap = document.querySelector('.fa-board-wrap');
  const heads = [...t.querySelectorAll('thead th')].filter(vis);
  const cls = heads.map(th => th.className.split(' ')[0]);
  const row = t.querySelector('tbody tr[data-key]');
  return {
    pageScroll: de.scrollWidth - de.clientWidth,
    over: t.getBoundingClientRect().width - wrap.getBoundingClientRect().width,
    deal: ['fc-vd', 'fc-aav', 'fc-yrs', 'fc-guar'].filter(c => cls.includes(c)).length,
    minSortH: Math.min(...heads.map(th => th.querySelector('button').getBoundingClientRect().height)),
    ageCol: cls.includes('fc-age'), subAge: vis(row.querySelector('.fa-sub-age')),
    stCol: cls.includes('fc-st'), subSt: vis(row.querySelector('.fa-sub-st')),
    clipped: [...row.children].filter(c => vis(c) && !c.classList.contains('fc-player')
                                         && c.scrollWidth > c.clientWidth + 1).length,
    bands: row.querySelectorAll('[data-band][tabindex="0"]').length,
  };
}"""

_STICK = """() => {
  const th = document.querySelector('table.fa-board-table thead th.fc-guar');
  window.scrollTo(0, th.getBoundingClientRect().top + scrollY + 900);
  const top = th.getBoundingClientRect().top;
  window.scrollTo(0, 0);
  return top;
}"""

_DETAIL = """async () => {
  const vis = el => getComputedStyle(el).display !== 'none';
  const t = document.querySelector('table.fa-board-table');
  const widths = () => [...t.querySelectorAll('thead th')].filter(vis).map(th => Math.round(th.getBoundingClientRect().width));
  const before = widths();
  const tr = t.querySelector('tbody tr[data-key]');
  tr.querySelector('.fa-xp-btn').click();
  await new Promise(r => setTimeout(r, 60));
  const d = tr.nextElementSibling;
  return {isDetail: !!d && d.classList.contains('fa-detail'),
          span: [...d.children].filter(vis).reduce((a, c) => a + c.colSpan, 0),
          cols: before.length, same: JSON.stringify(before) === JSON.stringify(widths()),
          expanded: tr.querySelector('.fa-xp-btn').getAttribute('aria-expanded'),
          text: d.innerText,
          pageScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}"""

_SORTCTL = """() => {
  const box = el => { const r = el && el.getBoundingClientRect(); return r ? [Math.round(r.width), Math.round(r.height)] : [0, 0]; };
  const sel = document.getElementById('fa-sort-sel');
  const dir = document.getElementById('fa-sort-dir');
  return {
    sel: box(sel), dir: box(dir),
    inBoard: !!(sel && sel.closest('.fa-board-tmain')),
    gated: !!(sel && getComputedStyle(sel.closest('.fa-board-tools') || sel).display === 'none'),
    opts: sel ? [...sel.options].map(o => o.value) : [],
  };
}"""

_COARSE = """() => {
  const vis = el => getComputedStyle(el).display !== 'none';
  const t = document.querySelector('table.fa-board-table');
  const heads = [...t.querySelectorAll('thead th')].filter(vis);
  const btns = heads.map(th => th.querySelector('button'));
  let overlap = 0;
  const r = heads.map(th => th.getBoundingClientRect());
  for (let i = 1; i < r.length; i++) if (r[i].left < r[i - 1].right - 0.5) overlap++;
  return {
    after: getComputedStyle(btns[0], '::after').content,
    minH: Math.min(...btns.map(b => b.getBoundingClientRect().height)),
    overlap: overlap,
    fields: [...document.querySelectorAll('.fa-select')].map(
      s => parseFloat(getComputedStyle(s).fontSize)),
  };
}"""

_STRIPE = """() => {
  const vis = el => getComputedStyle(el).display !== 'none';
  const t = document.querySelector('table.fa-board-table');
  const rows = [...t.querySelectorAll('tbody tr.fa-row-opt')];
  if (!rows.length) return null;
  const first = [...rows[0].children].filter(vis)[0];
  return {n: rows.length, cls: first.className.split(' ')[0],
          shadow: getComputedStyle(first).boxShadow};
}"""

_HEADCOL = """() => {
  const vis = el => getComputedStyle(el).display !== 'none';
  const ths = [...document.querySelectorAll('table.fa-board-table thead th')].filter(vis);
  const out = {active: [], idle: []};
  ths.forEach(th => {
    const cs = getComputedStyle(th);
    const rec = [th.className.split(' ')[0], cs.color, cs.borderBottomColor];
    (th.getAttribute('aria-sort') === 'none' ? out.idle : out.active).push(rec);
  });
  return out;
}"""

_STATUS = """() => {
  const vis = el => getComputedStyle(el).display !== 'none';
  const out = [];
  document.querySelectorAll('table.fa-board-table tbody tr[data-key] td.fc-st').forEach(td => {
    if (!vis(td)) return;
    const s = td.querySelector('.fa-st');
    if (!s || !s.classList.contains('fa-st-opt')) return;
    out.push({text: (td.innerText || '').trim(),
              clipped: td.scrollWidth > td.clientWidth + 1,
              tip: s.getAttribute('title') || ''});
  });
  return out;
}"""


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_fa_table_fits_without_sideways_scroll(server, w, h):
    with _board_page(server, w, h) as page:
        fit = page.evaluate(_FIT)
        assert fit["pageScroll"] <= 0, f"{w}px: the page scrolls sideways by {fit['pageScroll']}px"
        assert fit["over"] <= 0.5, f"{w}px: the table is wider than its box"
        assert fit["deal"] == 4, f"{w}px: {fit['deal']} of 4 predicted-deal columns painted"
        assert fit["minSortH"] >= 24, f"{w}px: a sort target is {fit['minSortH']}px tall"
        assert fit["clipped"] == 0, f"{w}px: a number is clipped in row 1"
        # Age and Status are columns at a laptop and sub-line facts on a phone;
        # never neither.
        assert fit["ageCol"] != fit["subAge"], fit
        assert fit["stCol"] != fit["subSt"], fit
        # The tap-to-open P10-P90 bands (2026-08-07) survive the table.
        assert fit["bands"] == 3, fit
        assert abs(page.evaluate(_STICK)) < 1, f"{w}px: the header does not stick"


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_detail_line_paints_exactly_the_header_columns(server, w, h):
    with _board_page(server, w, h) as page:
        d = page.evaluate(_DETAIL)
        assert d["isDetail"] and d["expanded"] == "true"
        assert d["span"] == d["cols"], f"{w}px: detail spans {d['span']} of {d['cols']} columns"
        assert d["same"], f"{w}px: opening a detail line moved the columns"
        assert d["pageScroll"] <= 0
        # the facts no column carries, at every width (the labels are
        # uppercased by CSS, and innerText reports the rendered text)
        for fact in ("P10-P90", "DEAL+", "EWAR"):
            assert fact in d["text"].upper(), f"{w}px: the detail line dropped {fact}"


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_the_sort_control_is_visible_at_every_width(server, w, h):
    """Downside WAR, star odds and prior AAV have NO column at any width, so a
    picker revealed only once a column folded would leave them reachable by
    hand-typing #sort= and nothing else. It lives on its own .fa-board-tools row
    above the filter bar: measured with the picker inside the bar, the bar went
    from 43px to 73px at 1440, 1280, 1100 AND 1024, so the pre-registered
    fallback in the spec fired."""
    with _board_page(server, w, h) as page:
        s = page.evaluate(_SORTCTL)
        assert s["sel"][0] > 0 and s["sel"][1] > 0, f"{w}px: the sort picker is not painted"
        assert s["dir"][0] > 0 and s["dir"][1] > 0, f"{w}px: the reverse button is not painted"
        assert s["inBoard"], f"{w}px: the sort control is not in the board column"
        assert not s["gated"], f"{w}px: the sort control sits behind a display gate"
        for key in ("warCvar10", "pAnyStar", "prevAav"):
            assert key in s["opts"], f"{w}px: {key} is not offered by the picker"


def test_coarse_pointer_targets_and_field_sizes(server):
    """.fa-sort left the shared coarse-pointer overlay list in the same commit:
    inline-block plus an inset -11px -8px overlay is right for a chip and wrong
    for a button that fills its own header cell, where it would overlap the
    neighbouring header by 16px and reach 11px into row 1. And iOS zooms the
    whole page when a focused field is under 16px."""
    with _board_page(server, 390, 844, coarse=True) as page:
        c = page.evaluate(_COARSE)
        assert c["after"] == "none", f"a header button still carries the overlay ({c['after']})"
        assert c["minH"] >= 36, f"a coarse sort target is {c['minH']}px tall"
        assert c["overlap"] == 0, f"{c['overlap']} header pairs overlap"
        assert c["fields"] and min(c["fields"]) >= 16, f"a field is {c['fields']} px"


def test_status_cell_says_a_word(server):
    """The cell printed a price and a percentage under a header that says
    Status, so its meaning depended on the type pill 300px away in the Player
    cell. It leads with the word now, and P(enter) moved to the title."""
    with _board_page(server, 1280, 800) as page:
        rows = page.evaluate(_STATUS)
        assert len(rows) >= 10, f"only {len(rows)} option rows to read"
        import re
        for r in rows:
            assert re.match(r"^(CLUB|PLYR|MUT|COND|OPT)", r["text"]), r
            assert not r["clipped"], f"the Status cell clips {r['text']!r}"
            assert "P(enter)" in r["tip"], r


@pytest.mark.parametrize("w,h", VIEWPORTS)
def test_the_option_row_keeps_its_gold_marker(server, w, h):
    """71 of 236 rows are an option rather than a plain expiring contract, and
    the gold left marker is how the board says so at a glance. The rule paints
    the row's first cell, and :first-child is STRUCTURAL: it keeps naming
    td.fc-rank after the 891px tier sets it to display: none, so every folded
    width painted the marker on a cell that is not there. The assertion reads
    the first cell that actually paints."""
    with _board_page(server, w, h) as page:
        s = page.evaluate(_STRIPE)
        assert s and s["n"] >= 10, f"{w}px: {s} option rows to read"
        assert s["shadow"] and s["shadow"] != "none",             f"{w}px: the option marker is not painted on {s['cls']}, the first painted cell"
        assert "inset" in s["shadow"], f"{w}px: {s['shadow']}"


def test_only_the_active_header_reads_as_sorted(server):
    """The active header is the one with --text-primary and the gold rule. A
    per-column emphasis rule on the bare class (.fc-guar rather than td.fc-guar)
    is (0,3,0) and outranks the (0,2,2) thead rule, so the Guar HEADER painted
    the active colour at all times while aria-sort said none: two columns
    looking sorted, one of them lying."""
    with _board_page(server, 1280, 800, hash_="#sort=name&dir=asc") as page:
        h = page.evaluate(_HEADCOL)
        assert len(h["active"]) == 1, h["active"]
        assert h["idle"], h
        colours = {c for _n, c, _b in h["idle"]}
        assert len(colours) == 1, f"idle headers paint {colours}: one of them reads as sorted"
        assert h["active"][0][1] not in colours, "the active header paints as an idle one"
