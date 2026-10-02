# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PROSPX MiLB board cuts nothing off and splits no item, 390 to 1920px, both themes.

Owner answer M29-2 (2026-09-30): the width PLUS% freed goes to spacing. Measured on
page 1 (50 rows) before the change, on 2026-10-02: the MiLB cell cut text off at its
right edge on 48 rows at 1024 and 1100, 37 at 1280 and 40 at 1500 (Caden Bodine's
"wRC+ 105" printed as "wRC+ 10", a different number), the Player cell clipped top and
bottom on 50 rows at 1024, the meta line split "SS / 2B / 3B" mid-list, and the phone
row's columns sat up to 16px off the header's. Width alone did not cure it: the row
buttons sat in the identity row, the slash line repeated the pill's wRC+, and the
detail line was one text run. Every fix is a width or wrap fix; no font size moved.

Pinned at every width in WIDTHS, in both themes, over the first 50 rows:
  * the Player and MiLB cells hold their content (no clip at the right edge, top or
    bottom), and the page never scrolls sideways;
  * a position list, a MiLB stat and a Surplus sub-line item each sit on one line;
  * no slash line repeats the wRC+ its pill already prints;
  * the age-vs-level line under ETA prints a signed one-decimal number and stays in
    its cell, and the in-org rank under the diamond is the live getEfvOrgRank;
  * at 390 the name stack keeps real width (it was 0px before SPR03 and 124px after).

`content-visibility: visible` is injected for the measurement only: off-screen rows
otherwise skip layout and would pass any geometry check vacuously.

Playwright/chromium are OPTIONAL; the test skips cleanly when unavailable.
"""
from __future__ import annotations

import pytest
from conftest import serve_site

WIDTHS = [390, 768, 1024, 1100, 1280, 1366, 1440, 1500, 1600, 1920]

WAIT_ROWS = ("() => { const r = document.getElementById('rows');"
             " return !!r && r.querySelectorAll('.player-row[data-key]').length > 10"
             " && !!r.querySelector('.col-header'); }")

PROBE = r"""() => {
  const rows = [...document.querySelectorAll('#rows .player-row[data-key]')].slice(0, 50);
  const shown = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).display !== 'none';
  const lines = el => {
    const rg = document.createRange(); rg.selectNodeContents(el);
    const tops = [];
    for (const r of rg.getClientRects()) {
      if (r.width <= 0.5 || r.height <= 0) continue;
      const t = Math.round(r.top);
      if (!tops.some(x => Math.abs(x - t) <= 3)) tops.push(t);
    }
    return tops.length;
  };
  const by = {};
  try { for (const q of getFilteredActives()) by[q.player_key] = q; } catch (e) {}
  const bad = [];
  const who = row => (row.querySelector('.player-name') || {}).textContent || row.dataset.key;
  for (const row of rows) {
    const name = who(row).trim().slice(0, 30);
    for (const sel of [':scope > .player-row-col1', ':scope > .milb-cell']) {
      const c = row.querySelector(sel);
      if (!shown(c)) continue;
      if (c.scrollWidth > c.clientWidth + 1) bad.push(`${name}: ${sel} cut at the right edge (${c.scrollWidth} > ${c.clientWidth})`);
      if (c.scrollHeight > c.clientHeight + 1) bad.push(`${name}: ${sel} cut top/bottom (${c.scrollHeight} > ${c.clientHeight})`);
    }
    for (const el of row.querySelectorAll('.pos-cluster, .milb-seg, .sv-botline > span')) {
      if (shown(el) && lines(el) > 1) bad.push(`${name}: "${el.textContent.trim()}" splits across lines`);
    }
    const pill = [...row.querySelectorAll('.milb-pill-row .stat-pill')].map(s => s.textContent.trim()).find(t => /^wRC\+ -?\d+$/.test(t));
    const slash = row.querySelector('.milb-slash');
    if (pill && slash && new RegExp(pill.replace('+', '\\+') + '$').test(slash.textContent.trim())) {
      bad.push(`${name}: the slash line repeats "${pill}"`);
    }
    for (const k of row.querySelectorAll('.milb-pill-row .stat-pill')) {
      const t = k.textContent.trim();
      if (/^KRP\+/.test(t) && !/^KRP\+ -?\d+$/.test(t)) bad.push(`${name}: KRP+ pill is not an integer (${t})`);
    }
    const eta = row.querySelector(':scope > .eta-cell');
    if (shown(eta)) {
      const er = eta.getBoundingClientRect();
      for (const e of eta.querySelectorAll('*')) {
        const r = e.getBoundingClientRect();
        if (r.width > 0 && (r.right > er.right + 1 || r.left < er.left - 1 || r.bottom > er.bottom + 1)) {
          bad.push(`${name}: ETA cell content escapes its cell`); break;
        }
      }
      const a = eta.querySelector('.eta-avl');
      if (a && !/^[+-]?\d+\.\dy$/.test(a.textContent.trim())) bad.push(`${name}: age vs level reads "${a.textContent.trim()}"`);
    }
    const rk = row.querySelector(':scope > .rank-cell-stack');
    const org = rk && rk.querySelector('.rank-org');
    const p = by[row.dataset.key];
    if (p && !inProvSection(p)) {
      const o = getEfvOrgRank(p);
      const want = o ? `${p.org} #${o.rank}` : null;
      const got = org ? org.textContent.trim() : null;
      if (want !== got) bad.push(`${name}: org rank line "${got}", expected "${want}"`);
    }
    if (shown(org)) {
      const rr = rk.getBoundingClientRect(), r = org.getBoundingClientRect();
      if (r.right > rr.right + 1 || r.left < rr.left - 1) bad.push(`${name}: org rank line escapes the rank cell`);
    }
    if (window.innerWidth <= 640) {
      const ns = row.querySelector('.player-name-stack');
      if (ns && ns.getBoundingClientRect().width <= 100) bad.push(`${name}: name stack only ${ns.getBoundingClientRect().width}px wide`);
    }
  }
  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + 1) bad.push(`page scrolls sideways (${de.scrollWidth} > ${de.clientWidth})`);
  return { n: rows.length, bad };
}"""


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_board_cuts_nothing_off_at_any_width(server, theme):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme=theme)
            ctx.add_init_script("try { localStorage.setItem('prospect-tracker.theme', %r); } catch (e) {}" % theme)
            page = ctx.new_page()
            errs: list[str] = []
            page.on("pageerror", lambda e: errs.append(str(e)[:200]))
            page.goto(server + "prospx/index.html", wait_until="load", timeout=120_000)
            page.wait_for_function(WAIT_ROWS, timeout=120_000)
            page.wait_for_timeout(2500)
            assert page.evaluate("() => document.documentElement.getAttribute('data-theme')") == theme
            page.add_style_tag(content="#rows .player-row { content-visibility: visible !important; }")
            failures = {}
            for w in WIDTHS:
                page.set_viewport_size({"width": w, "height": 900})
                page.evaluate("() => renderActives()")
                page.wait_for_timeout(600)
                m = page.evaluate(PROBE)
                assert m["n"] >= 50, f"{w}px: only {m['n']} rows painted"
                if m["bad"]:
                    failures[w] = m["bad"][:6] + ([f"... {len(m['bad']) - 6} more"] if len(m["bad"]) > 6 else [])
            assert not failures, f"{theme}: " + "; ".join(f"{w}px: {v}" for w, v in failures.items())
            assert not errs, errs
        finally:
            browser.close()


def test_age_vs_level_line_is_blank_on_provisional_rows(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(server + "prospx/index.html", wait_until="load", timeout=120_000)
            page.wait_for_function("() => typeof etaAgeVsLevelHTML === 'function'", timeout=60_000)
            m = page.evaluate("""() => {
              const base = { age_vs_level: { diff: -3.46, tier: 'very-young' }, statline: { level: 'AAA' },
                             level_changes: [{ to_level: 'AA', date: '2025-06-02' }, { to_level: 'AAA', date: '2025-08-25' }] };
              const prov = etaAgeVsLevelHTML(Object.assign({ _is_provisional: true }, base));
              const d = document.createElement('div'); d.innerHTML = etaAgeVsLevelHTML(base);
              const off = Object.assign({}, base, { level_changes: [{ to_level: 'AA', date: '2026-05-01' }] });
              const d2 = document.createElement('div'); d2.innerHTML = etaAgeVsLevelHTML(off);
              return { prov, num: d.querySelector('.eta-avl').textContent, reached: (d.querySelector('.eta-reached') || {}).textContent,
                       title: d.firstElementChild.getAttribute('title'), offDate: !!d2.querySelector('.eta-reached'),
                       none: etaAgeVsLevelHTML({ statline: { level: 'A' } }) };
            }""")
            assert m["prov"] == "" and m["none"] == "", m
            assert m["num"] == "-3.5y", m
            assert m["reached"] == "AAA 2025", m
            assert "3.5 years younger than the median player at AAA" in m["title"], m
            assert "Reached AAA on Aug 25, 2025." in m["title"], m
            assert m["offDate"] is False, "the date prints only when the last move lands on the level"
        finally:
            browser.close()
