# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/hof/ keyboard, screen-reader and contrast contract (audit 2026-10-02).

QCLA14. The band switcher carried role=tablist over three plain buttons, so
the accessibility tree held a tablist with no tabs and the active band was a
class only. A keyboard sort (Enter on a header) dropped focus on <body>. The
header focus ring was gold, 2.2:1 on the cream header. The count line changed
on every search with no live region.

QCLA15. Text on the leaderboard was dimmed with opacity or set in accent ink
on its own tint, under 4.5:1 in light: rank 3.8, the writers chip 3.9, the
route-unverified chip 4.2, the JAWS ladder labels 4.45, the count line 4.4,
and the blank-value dot 1.9 (2.4 in dark).

Each test below drives the served page in headless Chromium over loopback.
"""
from __future__ import annotations

import pytest

from conftest import serve_site

_LUM = """
function parse(c){const q=c.match(/color\\(srgb ([^)]+)\\)/);
  if(q){const v=q[1].split(/[ \\/]+/).filter(Boolean).map(Number); return [v[0]*255,v[1]*255,v[2]*255,v.length>3?v[3]:1];}
  const m=c.match(/rgba?\\(([^)]+)\\)/); if(!m) return [0,0,0,0];
  const p=m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return [p[0],p[1],p[2],p.length>3?p[3]:1];}
function over(a,b){const al=a[3]; return [a[0]*al+b[0]*(1-al),a[1]*al+b[1]*(1-al),a[2]*al+b[2]*(1-al),1];}
function lum(c){const f=v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4)};
  return 0.2126*f(c[0])+0.7152*f(c[1])+0.0722*f(c[2]);}
function ratio(a,b){const x=lum(a),y=lum(b);return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05);}
function bgOf(el){const chain=[];let e=el;while(e&&e.nodeType===1){chain.push(e);e=e.parentElement;}
  let bg=[255,255,255,1]; for(let i=chain.length-1;i>=0;i--){const c=parse(getComputedStyle(chain[i]).backgroundColor);
  if(c[3]>0) bg=over(c,bg);} return bg;}
function opac(el){let o=1,e=el;while(e&&e.nodeType===1){o*=parseFloat(getComputedStyle(e).opacity);e=e.parentElement;}return o;}
function textRatio(el){const fg=parse(getComputedStyle(el).color); const bg=bgOf(el);
  return ratio(over([fg[0],fg[1],fg[2],fg[3]*opac(el)],bg),bg);}
"""


@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


def _open(p, server, theme="light", width=1280):
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=theme)
    ctx.add_init_script(
        "try{localStorage.setItem('prospect-tracker.theme','" + theme + "')}catch(e){}")
    page = ctx.new_page()
    page.goto(server + "hof/", wait_until="networkidle", timeout=90_000)
    try:
        page.wait_for_selector(".hof-table tbody tr", timeout=30_000)
    except Exception:  # noqa: BLE001
        browser.close()
        pytest.skip("hof_board.json painted no board on this machine")
    return browser, page


def test_the_band_switcher_is_a_tablist_of_tabs(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = _open(p, server)
        try:
            got = page.evaluate("""() => {
              const l = document.querySelector('.hof-bands');
              const kids = [...l.children];
              const panel = document.getElementById('hof-band-panel');
              return {role: l.getAttribute('role'), label: l.getAttribute('aria-label'),
                n: kids.length, tabs: kids.filter(b => b.getAttribute('role') === 'tab').length,
                selected: kids.filter(b => b.getAttribute('aria-selected') === 'true').map(b => b.dataset.band),
                controls: kids.filter(b => b.getAttribute('aria-controls') === 'hof-band-panel').length,
                panelRole: panel && panel.getAttribute('role')};
            }""")
            assert got["role"] == "tablist" and got["label"], got
            assert got["n"] == 3 and got["tabs"] == 3 and got["controls"] == 3, got
            assert got["selected"] == ["leaderboard"], got
            assert got["panelRole"] == "tabpanel", got
            # The arrow key moves the selection and keeps focus on the new tab.
            page.focus("#hof-band-leaderboard")
            page.keyboard.press("ArrowRight")
            after = page.evaluate("""() => ({
              focus: document.activeElement.id,
              selected: [...document.querySelectorAll('.hof-bandbtn')]
                .filter(b => b.getAttribute('aria-selected') === 'true').map(b => b.dataset.band)})""")
            assert after == {"focus": "hof-band-watch", "selected": ["watch"]}, after
        finally:
            browser.close()


def test_a_keyboard_sort_keeps_focus_on_its_header_with_a_cyan_ring(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = _open(p, server)
        try:
            page.focus('th[data-sort="war"]')
            page.keyboard.press("Enter")
            got = page.evaluate("() => {" + _LUM + """
              const a = document.activeElement; const cs = getComputedStyle(a);
              const ring = parse(cs.outlineColor);
              return {sort: a.getAttribute('data-sort'), aria: a.getAttribute('aria-sort'),
                style: cs.outlineStyle, ring: ratio(over(ring, bgOf(a)), bgOf(a))};
            }""")
            assert got["sort"] == "war" and got["aria"] in ("ascending", "descending"), got
            assert got["style"] != "none" and got["ring"] >= 3.0, got
        finally:
            browser.close()


def test_the_count_line_is_one_status_node_that_survives_a_search(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = _open(p, server)
        try:
            page.evaluate("() => { window.__hofCount = document.querySelector('.hof-count'); }")
            before = page.evaluate("() => document.querySelector('.hof-count').textContent")
            page.fill("#hof-q", "ruth")
            got = page.evaluate("""() => {
              const c = document.querySelector('.hof-count');
              return {same: c === window.__hofCount, role: c.getAttribute('role'),
                text: c.textContent, focus: document.activeElement.id};
            }""")
            assert got["same"] and got["role"] == "status", got
            assert got["text"] != before, (before, got)
            assert got["focus"] == "hof-q", got
        finally:
            browser.close()


# Selector -> the least contrast each must clear. The blank dot is a marker
# with an accessible name, so it is held to the 3:1 of a non-text mark.
_CONTRAST = {
    "td.hof-c-rank": 4.5,
    "th.hof-c-rank": 4.5,
    ".hof-ind--player_bbwaa": 4.5,
    ".hof-ind--route_unverified": 4.5,
    ".hof-ladder-q": 4.5,
    ".hof-count": 4.5,
    ".hof-blank": 3.0,
}


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_leaderboard_text_clears_its_contrast_floor(server, theme):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = _open(p, server, theme)
        try:
            got = page.evaluate("(sels) => {" + _LUM + """
              const out = {};
              for (const s of sels) {
                const els = [...document.querySelectorAll('#hof-app-root ' + s)]
                  .filter(e => e.getBoundingClientRect().width > 0);
                out[s] = els.length ? Math.min(...els.map(textRatio)) : null;
              }
              return out;
            }""", list(_CONTRAST))
        finally:
            browser.close()
    missing = [s for s, v in got.items() if v is None]
    assert not missing, ("nothing painted for", missing)
    low = {s: round(v, 2) for s, v in got.items() if v < _CONTRAST[s]}
    assert not low, (theme, low)
