# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ form controls carry the site idiom, measured in Chromium.

Owner report 2026-09-18: the year range "from / to" selects rendered in the
browser default beside themed chips. This asserts the repair on the served
page, in both themes at desk and phone width, and pins the two numbers the
repair rests on: the select boundary clears 3:1 and the page declares its
color-scheme so the browser's own widget parts follow the theme. A control
that reverts to the user-agent default fails here.
"""
from __future__ import annotations

import re

import pytest

from conftest import serve_site

ROUTES = ["mlbstats/#section=starters", "mlbstats/#section=war", "mlbstats/#section=defense"]
SIZES = [(1440, 900), (390, 844)]
THEMES = ["dark", "light"]
SITE_FACE = "PixelMplus12"

_READ = r"""
() => {
  const lum = (rgb) => {
    const m = rgb.match(/\d+(\.\d+)?/g); if (!m) return null;
    const c = m.slice(0, 3).map(v => { v = Number(v) / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); if (x == null || y == null) return null;
    const hi = Math.max(x, y), lo = Math.min(x, y); return (hi + 0.05) / (lo + 0.05); };
  const tok = (name) => { const d = document.createElement('div'); d.style.cssText = 'position:absolute;left:-9999px;background:var(' + name + ')';
    document.body.appendChild(d); const v = getComputedStyle(d).backgroundColor; d.remove(); return v; };
  const out = [];
  for (const el of document.querySelectorAll('select, input, textarea')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue;
    const bg = cs.backgroundColor;
    out.push({ tag: el.tagName, type: (el.type || '').toLowerCase(),
      range: !!el.dataset.mlbrangesel, inBar: !!el.closest('.mlbstats-bar'),
      id: el.id || '', font: cs.fontFamily, appearance: cs.appearance, accent: cs.accentColor,
      bg, border: cs.borderTopColor, boundary: ratio(cs.borderTopColor, bg) });
  }
  const cap = document.querySelector('.mlbstats-range-fromto .mlbstats-ctl');
  return { colorScheme: getComputedStyle(document.documentElement).colorScheme,
           tokenBg: tok('--bg-secondary'), tokenAccent: tok('--accent-cyan'),
           captionPx: cap ? getComputedStyle(cap).fontSize : null,
           overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
           controls: out };
}
"""


@pytest.fixture(scope="module")
def swept():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    seen = {}
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip("chromium unavailable: %s" % e)
        for (w, h) in SIZES:
            for theme in THEMES:
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
                ctx.route(re.compile(r"^(?!http://127\.0\.0\.1:).*"), lambda route: route.abort())
                ctx.add_init_script("try{localStorage.setItem('prospect-tracker.theme',%r);}catch(e){}" % theme)
                page = ctx.new_page()
                for path in ROUTES:
                    page.goto("about:blank")
                    page.goto(base + path, wait_until="load", timeout=60_000)
                    page.evaluate("t => document.documentElement.setAttribute('data-theme', t)", theme)
                    page.wait_for_selector("select[data-mlbrangesel]", timeout=30_000)
                    page.wait_for_timeout(400)
                    seen[(path, theme, w)] = page.evaluate(_READ)
                ctx.close()
        browser.close()
    assert seen
    return seen


def _each(swept):
    for (path, theme, w), d in sorted(swept.items()):
        yield path, theme, w, d


def test_the_page_declares_the_color_scheme_it_is_on(swept):
    for path, theme, w, d in _each(swept):
        assert d["colorScheme"] == theme, (path, theme, w, d["colorScheme"])


def test_the_year_range_selects_carry_the_site_idiom(swept):
    for path, theme, w, d in _each(swept):
        rng = [c for c in d["controls"] if c["range"]]
        assert len(rng) >= 2, (path, theme, w, "no year range selects rendered")
        for c in rng:
            assert SITE_FACE in c["font"], (path, theme, w, c["font"])
            assert c["appearance"] == "none", (path, theme, w, c["appearance"])
            assert c["bg"] == d["tokenBg"], (path, theme, w, c["bg"], d["tokenBg"])


def test_the_select_boundary_clears_three_to_one_in_both_themes(swept):
    """The measured answer to the review that the themed border was worse
    than the browser's white box: --border reads about 1.1:1 dark / 1.6:1
    light on --bg-secondary; the shipped border clears the 3:1 floor."""
    for path, theme, w, d in _each(swept):
        for c in d["controls"]:
            if c["tag"] == "SELECT" and (c["range"] or c["inBar"]):
                assert c["boundary"] is not None and c["boundary"] >= 3.0, (path, theme, w, c["id"] or "range", c["boundary"])


def test_every_checkbox_takes_the_site_accent(swept):
    """Presence is asserted over the WHOLE sweep, not per state: the Defense
    board keeps its qualified box behind the Filters fold at phone width, so
    one section at 390 legitimately renders none."""
    seen_any = False
    for path, theme, w, d in _each(swept):
        for c in [c for c in d["controls"] if c["type"] == "checkbox"]:
            seen_any = True
            assert c["accent"] == d["tokenAccent"], (path, theme, w, c["id"], c["accent"], d["tokenAccent"])
    assert seen_any, "no checkbox rendered on any route at any width"


def test_the_caption_words_take_the_bar_dialect(swept):
    for path, theme, w, d in _each(swept):
        assert d["captionPx"] == "11px", (path, theme, w, d["captionPx"])


def test_no_sideways_scroll_at_either_width(swept):
    for path, theme, w, d in _each(swept):
        assert d["overflow"] <= 0, (path, theme, w, d["overflow"])
