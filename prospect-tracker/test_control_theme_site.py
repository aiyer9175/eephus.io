# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every control the site serves is a piece of the site, not a piece of the
browser. Measured in headless Chromium against every built route, in both
themes, at desk and phone width.

Owner ask 2026-09-18, confirmed 2026-09-23: "ensure that no elements like
this exist on the site that are off theme". The MLB Stats module landed first
(test_mlbstats_control_theme.py pins that repair and is unchanged); this is
the site-wide sibling. The sweep behind the ask enumerated 1,459 interactive
elements over 26 routes and 392 page states and found 108 rendering off theme
in four classes, none of them visible to any test in this suite, because
every control RULE in the sheet was correct and the defect was the controls
no rule reached. A stylesheet audit cannot see that; only the served page
can, so this file measures the served page and fails when any control
reverts to the user-agent default.

THE CLASSES, which are the cases below:

  1. THE UA WIDGET PARTS. A page that never declares `color-scheme` computes
     `normal`, and the browser paints every part it owns (the option list
     that drops out of a themed select, the spinners, the range track) in
     LIGHT mode on both themes. CSS cannot style those parts; color-scheme is
     the only control over them, so it is asserted rather than eyeballed.
  2. THE UA DISCLOSURE ARROW. `appearance: auto` on a themed select draws
     the browser's chevron in the browser's colour inside a pixel-font box.
     The repair REPLACES the arrow with a currentColor chevron rather than
     removing it, so both halves are asserted: appearance none AND a caret
     image present (a select with no caret reads as a text box).
  3. THE UA FILL, FONT AND BOUNDARY. A select the sheet does not reach is a
     white Arial box on the phosphor field. Its fill must be one of the page's
     own surfaces, its face the site's, and its boundary must clear 3:1
     against its own fill (WCAG 1.4.11) in BOTH themes: the sheet's `--border`
     token measures about 1.1:1 dark / 1.6:1 light on a control fill, so a
     select that quietly falls back to it fails here. The text fields the
     layer lifted (the ones that share a bar with a lifted select) are held
     to the same 3:1 by name.
  4. THE OS ACCENT. A checkbox, radio or slider with `accent-color: auto`
     paints the OS blue, a colour in neither palette, identically in both
     themes.
  5. THE FONT LEAK. A button and a form control do not inherit font-family,
     so a control whose rule set colour, fill and border but no face renders
     its text in the UA default beside PixelMplus12 copy. A control that
     renders no text of its own (an SVG glyph, a CSS triangle) has no font to
     leak and is not judged.
  6. THE KEYBOARD RING. Focusing every select and text field and reading the
     computed outline: the site's ring is 2px solid, and it must clear 3:1
     against the surface behind the control in both themes. A module that
     ends its control with `outline: none` fails here.
  7. NO SIDEWAYS SCROLL. The caret reserves room on the right of every
     select; the page must still fit its viewport at 1440 and 390.
  8. THE COARSE POINTER. iOS zooms the page when a focused field computes
     under 16px, and a touch target must not shrink: the fields the layer
     lifts by name are read on a touch context at 390, with the two heights
     the layer pins (the Hall of Fame search at 44px, the Trade Board search
     at 34px).
  9. THE SURFACES BUILT ON OPEN. The PROSPX splits builder, the PROSPX GFX
     modal, the Time Machine compare pickers and the eephus-gfx modal on MLB
     Stats do not exist in the DOM until a hand opens them, so the route
     sweep cannot see them; the first site-wide draft was caught by exactly
     that (the splits builder's selects lost their arrow to a PROSPX rule
     the class could not beat). A bounded probe opens each one and holds it
     to the same select invariants.

COVERAGE. Every route in SITE_MAP.md that is built here, in its default
state, every hash deep link the nav advertises, and every section or tab
reachable by clicking the site's own tab hooks (bounded per route). A route
whose shell is not built on this machine is skipped by name, not silently.
The /forums/ account forms are inert without eephus-config.js and are not
reached.

Playwright and chromium are OPTIONAL: the module skips when either is
missing. MUTATIONS, executed 2026-09-23 in a sandbox copy: removing `#hof-ind`
from the layer's caret list fails test_no_select_leaves_the_browser_to_draw_
its_arrow and the boundary case on /hof/; removing the `body select.chip`
block fails the arrow case on the PROSPX #acq-filter; removing `body
.split-custom select` from the caret list fails test_the_surfaces_built_on_
open_hold_the_same_line on the splits builder; removing the hamburger from
the font list fails the font case on every module route at 390.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import serve_site

ROOT = Path(__file__).parent

# (label, shell that must exist, url paths to visit). Deep links are the ones
# the nav and the section pickers advertise; the tab hooks below reach the
# rest by clicking.
ROUTES = [
    ("home", "index.html", [""]),
    ("prospx", "prospx/index.html", ["prospx/", "prospx/#tab=farm", "prospx/#tab=leaderboards", "prospx/#tab=traded",
                                     "prospx/#tab=injured", "prospx/#tab=spotlights", "prospx/#tab=debuts",
                                     "prospx/#tab=draft", "prospx/#tab=ifa", "prospx/#tab=overseas",
                                     "prospx/#tab=timemachine", "prospx/#tab=charts"]),
    ("projections", "projections/index.html", ["projections/"]),
    ("mlbstats", "mlbstats/index.html", ["mlbstats/", "mlbstats/#section=bullpen", "mlbstats/#section=starters",
                                         "mlbstats/#section=hitters", "mlbstats/#section=leverage",
                                         "mlbstats/#section=defense", "mlbstats/#section=war"]),
    ("fa", "fa/index.html", ["fa/", "fa/#view=dpw"]),
    ("trademachine", "trademachine/index.html", ["trademachine/"]),
    ("arbitration", "arbitration/index.html", ["arbitration/"]),
    ("betting", "betting/index.html", ["betting/"]),
    ("diamond", "diamond/index.html", ["diamond/"]),
    ("pal", "pal/index.html", ["pal/"]),
    ("parks", "parks/index.html", ["parks/"]),
    ("collegesavant", "collegesavant/index.html", ["collegesavant/"]),
    ("collegesavant-pitchers", "collegesavant/pitcher_index.html", ["collegesavant/pitcher_index.html"]),
    ("fantasy", "fantasy/index.html", ["fantasy/"]),
    ("glossary", "glossary/index.html", ["glossary/", "glossary/#view=calculators"]),
    ("hof", "hof/index.html", ["hof/"]),
    ("management", "management/index.html", ["management/"]),
    ("models", "models/index.html", ["models/"]),
    ("sources", "sources/index.html", ["sources/"]),
    ("team", "team/index.html", ["team/"]),
    ("history", "history/index.html", ["history/"]),
    ("news", "news/index.html", ["news/"]),
    ("report", "report/index.html", ["report/"]),
    ("articles", "articles/index.html", ["articles/"]),
    ("forums", "forums/index.html", ["forums/"]),
    ("404", "404.html", ["404.html"]),
]
# 1440 is the desk. 390 is the only width where the phone hamburger exists at
# all (display:none above 900px), and it was one of the font leaks.
SIZES = [(1440, 900), (390, 844)]
THEMES = ["dark", "light"]
SITE_FACE = "PixelMplus12"
MAX_CLICKS_PER_ROUTE = 14

# The text fields the layer lifts to the select boundary (section 7 of the
# native-control layer): each shares a bar with a lifted select, or had its
# typed text in the browser font. Held to 3:1 wherever one is visible.
TEXT_FIELDS = ("#hof-q", "#proj-q", "#dfs-f-q", "#dyn-f-q", "#rd-f-q",
               "#tb-search", "#chart-highlight", "input[search].search-box")

# The fields section 11 lifts to 16px on a coarse pointer, and the two touch
# heights it pins, read on the routes that render them.
COARSE_ROUTES = [
    ("hof", "hof/"), ("trademachine", "trademachine/"), ("management", "management/"),
    ("fantasy", "fantasy/"), ("betting", "betting/"), ("arbitration", "arbitration/"),
    ("glossary", "glossary/#view=calculators"),
]
COARSE_16 = ("#hof-ind", "#hof-pos", "#hof-q", "#mgmt-season", "#mgmt-cseason", "#mgmt-bseason", "#mgmt-club",
             "#mgmt-family", "#mgmt-spark", "#dfs-f-team", "#dfs-tpl", "#dyn-f-org",
             "#dyn-f-tier", "#rd-f-team", "#bt-legsel", "#arb-team", "#gx-surplus-side", "#tb-search")
COARSE_HEIGHT = {"#hof-q": 44, "#tb-search": 34}

# The site's own tab hooks, as the audit sweep used them.
TABSEL = ("[data-mlbsection],[data-bettingsection],[data-palsection],[data-mgmtsection],[data-arbsection],"
          "[data-parksection],[data-hofsection],[data-fantasysection],[data-fa-tab],[data-glossary-view],"
          "[data-fantasymodule],[data-mlbp-tab],[data-mlbp-section],[data-acct-filter],[role='tab'],"
          ".proj-viewbtn,[data-histview],[data-warview],[data-teamview],[data-starterview],[data-view],[data-tab]")

_READ = r"""
() => {
  const lum = (rgb) => {
    const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?/.exec(rgb || '');
    if (!m) return null;
    if (m[4] !== undefined && parseFloat(m[4]) === 0) return null;
    const f = v => { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(+m[1]) + 0.7152 * f(+m[2]) + 0.0722 * f(+m[3]);
  };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); if (x == null || y == null) return null;
    const hi = Math.max(x, y), lo = Math.min(x, y); return (hi + 0.05) / (lo + 0.05); };
  const opaque = (c) => lum(c) != null;
  const behind = (el) => { let p = el.parentElement;
    while (p) { const b = getComputedStyle(p).backgroundColor; if (opaque(b)) return b; p = p.parentElement; }
    return getComputedStyle(document.body).backgroundColor; };
  const tok = (name) => { const d = document.createElement('div'); d.style.cssText = 'position:absolute;left:-9999px;background:var(' + name + ')';
    document.body.appendChild(d); const v = getComputedStyle(d).backgroundColor; d.remove(); return v; };
  const fills = ['--bg-primary', '--bg-secondary', '--bg-tertiary'].map(tok);
  const accent = tok('--accent-cyan');
  const bodyFont = getComputedStyle(document.body).fontFamily;
  const out = [];
  const seen = {};
  for (const el of document.querySelectorAll('select, input, textarea, button')) {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || r.width < 1 || r.height < 1) continue;
    const type = (el.type || '').toLowerCase();
    const cls = (el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean)[0] || '';
    let key = el.id ? '#' + el.id : el.tagName.toLowerCase() + (type ? '[' + type + ']' : '') + (cls ? '.' + cls : '');
    if (el.dataset.mlbrangesel) key += '[' + el.dataset.mlbrangesel + ']';
    if (seen[key]) continue; seen[key] = 1;
    const typed = el.tagName === 'TEXTAREA' || el.tagName === 'SELECT'
      || (el.tagName === 'INPUT' && !['checkbox','radio','range','button','submit','reset','image','color','file','hidden'].includes(type));
    const rendersText = typed || (el.textContent || '').trim().length > 0;
    const fill = opaque(cs.backgroundColor) ? cs.backgroundColor : behind(el);
    out.push({ key, tag: el.tagName, type, rendersText, h: r.height, size: parseFloat(cs.fontSize),
      font: cs.fontFamily, appearance: cs.appearance, accent: cs.accentColor,
      bg: cs.backgroundColor, caret: cs.backgroundImage.indexOf('linear-gradient') >= 0,
      disabled: !!el.disabled, opacity: parseFloat(cs.opacity),
      boundary: ratio(cs.borderTopColor, fill) });
  }
  // The keyboard ring: focus each select and text field in turn and read the
  // computed outline. A control that cannot take focus (behind a fold) is
  // skipped by name and counted, so the case cannot go quietly vacuous.
  const focus = [];
  const fseen = {};
  for (const el of document.querySelectorAll('select, input[type=search], input[type=text], input[type=number], input[type=date], textarea')) {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || r.width < 1 || r.height < 1) continue;
    const key = el.id ? '#' + el.id : el.tagName.toLowerCase() + '.' + ((el.getAttribute('class') || '').trim().split(/\s+/)[0] || '');
    if (fseen[key]) continue; fseen[key] = 1;
    try { el.focus({preventScroll: true}); } catch (e) {}
    if (document.activeElement !== el) continue;
    const fs = getComputedStyle(el);
    focus.push({ key, style: fs.outlineStyle, width: parseFloat(fs.outlineWidth) || 0,
      color: fs.outlineColor, ring: ratio(fs.outlineColor, behind(el)) });
    el.blur();
  }
  return { colorScheme: getComputedStyle(document.documentElement).colorScheme,
           bodyFont, fills, accent, controls: out, focus,
           overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
}
"""

_CLICK = r"""
([s, i]) => {
  const els = document.querySelectorAll(s);
  if (i >= els.length) return null;
  const el = els[i];
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return null;
  const lbl = (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 30);
  el.click();
  return lbl || ('idx' + i);
}
"""

# The surfaces built on open: (label, route, what opens it). Each opener is
# the site's own hook, run in the page; a hook that is absent returns null
# and the surface is recorded as unreached by name.
_OPEN_SPLITS = r"""
() => {
  const row = document.querySelector('.player-row[data-key], [data-key]');
  return row ? row.getAttribute('data-key') : null;
}
"""
_OPEN_SPLITS_2 = r"""
(key) => {
  for (const b of document.querySelectorAll('.detail-tab')) { if (/Stats/.test(b.textContent)) { b.click(); break; } }
  return key;
}
"""
_OPEN_SPLITS_3 = r"""
(key) => {
  if (typeof splitSetView !== 'function' || !document.getElementById('splits-body')) return null;
  splitSetView(key, 'custom');
  return !!document.querySelector('.split-custom select');
}
"""
_OPEN_GFX = r"""
() => { if (typeof openGfxModal !== 'function') return null; openGfxModal(); return !!document.querySelector('.gfx-select'); }
"""
_OPEN_TM_DIFF = r"""
() => { const b = document.querySelectorAll('.tm-mode-btn'); if (b.length < 2) return null; b[1].click(); return true; }
"""
_OPEN_EGFX = r"""
() => { const c = document.querySelector('.egfx-chip'); if (!c) return null; c.click(); return true; }
"""


def _built():
    return [(label, paths) for label, shell, paths in ROUTES if (ROOT / shell).exists()]


def _launch(p):
    try:
        return p.chromium.launch()
    except Exception as e:  # noqa: BLE001
        pytest.skip("chromium unavailable: %s" % e)


def _context(browser, w, h, theme, coarse=False):
    kw = {"viewport": {"width": w, "height": h}, "device_scale_factor": 1}
    if coarse:
        kw.update({"has_touch": True, "is_mobile": True})
    ctx = browser.new_context(**kw)
    ctx.route(re.compile(r"^(?!http://127\.0\.0\.1:).*"), lambda route: route.abort())
    ctx.add_init_script("try{localStorage.setItem('prospect-tracker.theme',%r);}catch(e){}" % theme)
    page = ctx.new_page()
    page.set_default_timeout(30_000)
    return ctx, page


def _load(page, url, theme, settle=1000):
    page.goto("about:blank")
    page.goto(url, wait_until="load", timeout=60_000)
    page.wait_for_timeout(settle)
    page.evaluate("t => document.documentElement.setAttribute('data-theme', t)", theme)
    page.wait_for_timeout(150)


@pytest.fixture(scope="module")
def swept():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    routes = _built()
    assert routes, "no route shells built"
    seen = {}
    with serve_site() as base, sync_playwright() as p:
        browser = _launch(p)
        for (w, h) in SIZES:
            for theme in THEMES:
                ctx, page = _context(browser, w, h, theme)
                for label, paths in routes:
                    for i, path in enumerate(paths):
                        url = base + path
                        _load(page, url, theme)
                        seen[(label, path or "/", theme, w)] = page.evaluate(_READ)
                        if i:
                            continue
                        # the default state only: click through the route's own tab hooks
                        n = page.evaluate("s => document.querySelectorAll(s).length", TABSEL)
                        for k in range(min(n, MAX_CLICKS_PER_ROUTE)):
                            try:
                                hit = page.evaluate(_CLICK, [TABSEL, k])
                            except Exception:  # noqa: BLE001
                                hit = None
                            if not hit:
                                continue
                            page.wait_for_timeout(500)
                            if page.url.split("#")[0].rstrip("/") != url.split("#")[0].rstrip("/"):
                                page.goto(url, wait_until="load")
                                page.wait_for_timeout(1000)
                                continue
                            seen[(label, (path or "/") + " > " + hit, theme, w)] = page.evaluate(_READ)
                ctx.close()
        browser.close()
    assert seen
    return seen


@pytest.fixture(scope="module")
def coarse():
    """A touch context at 390 (has_touch + is_mobile, so `(pointer: coarse)`
    matches), both themes, on the routes that render the lifted fields."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    built = {label for label, _ in _built()}
    seen = {}
    with serve_site() as base, sync_playwright() as p:
        browser = _launch(p)
        for theme in THEMES:
            ctx, page = _context(browser, 390, 844, theme, coarse=True)
            for label, path in COARSE_ROUTES:
                if label not in built:
                    continue
                _load(page, base + path, theme)
                seen[(label, path, theme)] = page.evaluate(_READ)
                # the fantasy filters live behind the module tabs, and the
                # glossary calculator (#gx-surplus-side) behind a glossary view
                if label in ("fantasy", "glossary"):
                    n = page.evaluate("s => document.querySelectorAll(s).length", TABSEL)
                    for k in range(min(n, MAX_CLICKS_PER_ROUTE)):
                        try:
                            hit = page.evaluate(_CLICK, [TABSEL, k])
                        except Exception:  # noqa: BLE001
                            hit = None
                        if not hit:
                            continue
                        page.wait_for_timeout(500)
                        seen[(label, path + " > " + hit, theme)] = page.evaluate(_READ)
            ctx.close()
        browser.close()
    assert seen
    return seen


@pytest.fixture(scope="module")
def opened():
    """The surfaces built on open, both themes, at 1440 and 390."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    built = {label for label, _ in _built()}
    seen = {}
    with serve_site() as base, sync_playwright() as p:
        browser = _launch(p)
        for (w, h) in SIZES:
            for theme in THEMES:
                ctx, page = _context(browser, w, h, theme)
                if "prospx" in built:
                    _load(page, base + "prospx/", theme, settle=2500)
                    key = page.evaluate(_OPEN_SPLITS)
                    if key:
                        _load(page, base + "prospx/#player=" + key, theme, settle=3000)
                        page.evaluate(_OPEN_SPLITS_2, key)
                        page.wait_for_timeout(2500)
                        ok = page.evaluate(_OPEN_SPLITS_3, key)
                        page.wait_for_timeout(1200)
                        seen[("prospx splits builder", theme, w)] = (ok, page.evaluate(_READ))
                    _load(page, base + "prospx/", theme, settle=2500)
                    ok = page.evaluate(_OPEN_GFX)
                    page.wait_for_timeout(800)
                    seen[("prospx gfx modal", theme, w)] = (ok, page.evaluate(_READ))
                    _load(page, base + "prospx/#tab=timemachine", theme, settle=2500)
                    ok = page.evaluate(_OPEN_TM_DIFF)
                    page.wait_for_timeout(1500)
                    seen[("prospx time machine compare", theme, w)] = (ok, page.evaluate(_READ))
                if "mlbstats" in built:
                    _load(page, base + "mlbstats/#section=starters", theme, settle=2500)
                    ok = page.evaluate(_OPEN_EGFX)
                    page.wait_for_timeout(1200)
                    seen[("mlbstats egfx modal", theme, w)] = (ok, page.evaluate(_READ))
                ctx.close()
        browser.close()
    assert seen
    return seen


def _each(swept):
    for (label, state, theme, w), d in sorted(swept.items()):
        yield label, state, theme, w, d


def _site_face(font, body_font):
    first = (font or "").split(",")[0].replace('"', "").replace("'", "").strip()
    body_first = (body_font or "").split(",")[0].replace('"', "").replace("'", "").strip()
    return SITE_FACE in (font or "") or first == body_first


def _select_holds_the_line(where, c, d):
    """The four select invariants, shared by the sweep and the probe."""
    assert c["appearance"] == "none", (where, c["key"], c["appearance"])
    assert c["caret"], (where, c["key"], "appearance none with no caret drawn")
    assert c["bg"] in d["fills"], (where, c["key"], c["bg"], d["fills"])
    assert _site_face(c["font"], d["bodyFont"]), (where, c["key"], c["font"])
    assert c["boundary"] is not None and c["boundary"] >= 3.0, (where, c["key"], c["boundary"])


def test_every_page_declares_the_color_scheme_it_is_on(swept):
    for label, state, theme, w, d in _each(swept):
        assert d["colorScheme"] == theme, (label, state, theme, w, d["colorScheme"])


def test_no_select_leaves_the_browser_to_draw_its_arrow(swept):
    """Replaced, never removed: appearance none AND a caret image present."""
    n = 0
    for label, state, theme, w, d in _each(swept):
        for c in d["controls"]:
            if c["tag"] != "SELECT":
                continue
            n += 1
            assert c["appearance"] == "none", (label, state, theme, w, c["key"], c["appearance"])
            assert c["caret"], (label, state, theme, w, c["key"], "appearance none with no caret drawn")
    assert n, "no select rendered on any route"


def test_no_select_renders_the_browser_fill_or_face(swept):
    for label, state, theme, w, d in _each(swept):
        for c in d["controls"]:
            if c["tag"] != "SELECT":
                continue
            assert c["bg"] in d["fills"], (label, state, theme, w, c["key"], c["bg"], d["fills"])
            assert _site_face(c["font"], d["bodyFont"]), (label, state, theme, w, c["key"], c["font"])


def test_every_select_boundary_clears_three_to_one_in_both_themes(swept):
    for label, state, theme, w, d in _each(swept):
        for c in d["controls"]:
            if c["tag"] != "SELECT":
                continue
            assert c["boundary"] is not None and c["boundary"] >= 3.0, (label, state, theme, w, c["key"], c["boundary"])


def test_the_lifted_text_fields_clear_the_same_boundary(swept):
    """The text fields the layer names (section 7) share a bar with a lifted
    select; the bar carries one boundary, so they are held to the same 3:1."""
    seen = set()
    for label, state, theme, w, d in _each(swept):
        for c in d["controls"]:
            if c["key"] not in TEXT_FIELDS:
                continue
            seen.add(c["key"])
            assert c["boundary"] is not None and c["boundary"] >= 3.0, (label, state, theme, w, c["key"], c["boundary"])
    # the sweep must actually reach the bars: the Hall of Fame, projections and
    # Trade Board searches render in a route's default state. The DFS filter
    # (#dfs-f-q) lives in a fantasy module that is lazy-loaded behind its tab
    # (data-src on the module button); the tab-click sweep does not wait for
    # that script, so it is measured whenever it appears and never required.
    for key in ("#hof-q", "#proj-q", "#tb-search"):
        assert key in seen, (key, "never rendered on any route: the guard is mis-wired")


def test_every_checkbox_radio_and_range_takes_the_site_accent(swept):
    seen_any = False
    for label, state, theme, w, d in _each(swept):
        for c in d["controls"]:
            if c["type"] not in ("checkbox", "radio", "range"):
                continue
            seen_any = True
            assert c["accent"] == d["accent"], (label, state, theme, w, c["key"], c["accent"], d["accent"])
    assert seen_any, "no checkbox, radio or range rendered on any route"


def test_no_control_renders_its_text_in_the_browser_font(swept):
    for label, state, theme, w, d in _each(swept):
        for c in d["controls"]:
            if not c["rendersText"]:
                continue
            assert _site_face(c["font"], d["bodyFont"]), (label, state, theme, w, c["key"], c["font"])


def test_every_focused_select_and_field_shows_the_site_ring(swept):
    probed = 0
    for label, state, theme, w, d in _each(swept):
        for f in d["focus"]:
            probed += 1
            assert f["style"] == "solid" and f["width"] >= 2, (label, state, theme, w, f["key"], f["style"], f["width"])
            assert f["ring"] is not None and f["ring"] >= 3.0, (label, state, theme, w, f["key"], f["color"], f["ring"])
    assert probed, "no control took focus on any route"


# Pre-existing page overflow, measured on the UNTOUCHED tree on 2026-09-23
# and identical after this lane: the PROSPX Time Machine board at phone width
# (span.tm-h-stat / span.tm-fv inside .tm-board) runs 515px in a 390px
# viewport, and its compare mode (two dates) runs 1499px at 1440 and 423px at
# 390. Board layouts, not controls, in PROSPX's own sheet. Bounded here at
# their measured sizes so they cannot grow unseen, and named so they cannot
# hide a second one.
KNOWN_OVERFLOW = {("prospx", "prospx/#tab=timemachine", 390): 125}
KNOWN_OVERFLOW_OPENED = {("prospx time machine compare", 1440): 60, ("prospx time machine compare", 390): 35}


def test_no_sideways_scroll_at_either_width(swept):
    for label, state, theme, w, d in _each(swept):
        allowed = KNOWN_OVERFLOW.get((label, state, w), 0)
        assert d["overflow"] <= allowed, (label, state, theme, w, d["overflow"], allowed)


def test_the_lifted_fields_do_not_zoom_or_shrink_on_a_touch_screen(coarse):
    seen = {}
    for (label, state, theme), d in sorted(coarse.items()):
        assert d["overflow"] <= 0, (label, state, theme, d["overflow"])
        for c in d["controls"]:
            if c["key"] in COARSE_16:
                seen[c["key"]] = c["size"]
                assert c["size"] >= 16, (label, state, theme, c["key"], c["size"])
            if c["key"] in COARSE_HEIGHT:
                assert c["h"] >= COARSE_HEIGHT[c["key"]], (label, state, theme, c["key"], c["h"], COARSE_HEIGHT[c["key"]])
    # #mgmt-cseason is the League tab's season select, the management page's
    # default tab since Wave A; #mgmt-season sits on the Running Game tab, which
    # only the fine-pointer tab sweep reaches.
    for key in ("#hof-ind", "#hof-q", "#tb-search", "#mgmt-cseason", "#arb-team", "#gx-surplus-side"):
        assert key in seen, (key, "never rendered on a coarse pointer: the guard is mis-wired")


def test_the_surfaces_built_on_open_hold_the_same_line(opened):
    reached = set()
    for (surface, theme, w), (ok, d) in sorted(opened.items()):
        assert ok is not None, (surface, theme, w, "the site's own opener hook is gone")
        reached.add(surface)
        allowed = KNOWN_OVERFLOW_OPENED.get((surface, w), 0)
        assert d["overflow"] <= allowed, (surface, theme, w, d["overflow"], allowed)
        n = 0
        for c in d["controls"]:
            if c["tag"] == "SELECT":
                n += 1
                _select_holds_the_line((surface, theme, w), c, d)
                if c["disabled"]:
                    assert c["opacity"] < 1, (surface, theme, w, c["key"], "a disabled select paints like an enabled one")
            elif c["rendersText"]:
                assert _site_face(c["font"], d["bodyFont"]), (surface, theme, w, c["key"], c["font"])
        assert n, (surface, theme, w, "opened, but no select rendered")
    for surface in ("prospx splits builder", "prospx gfx modal", "prospx time machine compare", "mlbstats egfx modal"):
        assert surface in reached, (surface, "never opened")
