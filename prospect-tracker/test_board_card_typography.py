# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Typography regression tests for the MLB board cards and the font stacks.

Two defects are pinned here, both found 2026-08-05.

1. THE NAME CLIP (owner-reported: every player name on /projections/ rendered
   with its top sliced off). `.mlb-name` carries `overflow: hidden` for its
   ellipsis, which makes it a grid item whose automatic minimum size is 0, so it
   can be compressed BELOW its own line box without any visible overflow
   anywhere else on the card. It was measured at a 17.66px box around a 22px
   line box: a silent 4px clip, identical in both themes at DPR 1.0 and 1.25.
   The guard is deliberately `scrollHeight <= clientHeight` on the name itself
   rather than a pixel assertion on the card, because the failure mode is the
   element clipping its OWN content - a card-height assertion would keep passing
   while a future font-metric or chip change re-ate the text.

2. THE MIRRORED FONT TOKENS. `--font-retro` / `--font-retro-mono` are defined
   twice on purpose (assets/site.css and prospx/index.html's own :root, which
   wins the cascade inside the PROSPX app). If only one copy gains a family,
   Apple renders PROSPX and the editorial pages in two different faces. Both
   files' comments say "mirrors the other"; this asserts it.

3. THE LOGO STACK AND ITS FOUR UNRESOLVABLE COPIES (added 2026-08-07 with the
   DotGothic16 -> PixelMplus12 swap). A canvas 2d context and a serialized
   standalone SVG cannot resolve `var(--font-logo)`, so the logo stack is
   repeated as a LITERAL in eephus-gfx.js, eephus-hub.js and eephus-export.js,
   and the fonts.load warmups name the family a fifth and sixth time. Nothing
   links those copies to the token: a stale one does not throw, it silently
   rasterises the wordmark in the next family down. prospx's _GFX_SVG_MONO is
   the proof this happens - three copies had already drifted apart before one
   constant replaced them.

4. THREE LAYOUT DEFECTS ADDED 2026-08-07, all of them silent by construction -
   nothing throws, nothing overflows a viewport, and the page keeps rendering.

   4a. NAV STRIP FIT. The primary link strip is right-aligned by margin-left:auto
       inside `overflow-x: auto`, so when it stops fitting it does not push the
       bar wider or wrap: it just scrolls, and the tail links leave the screen
       with no visible affordance above the <=640px hamburger. Measured
       2026-08-07 at 1440: 799px of links in 904px of available track, i.e.
       105px of real headroom - enough for exactly ONE more ~97px item, and the
       second one clips. (The earlier reading of "799 in 799, zero slack" was
       reading a content-sized flex item's own width back at itself.) The strip
       stops overflowing at 1190px viewport, so 641-1189 is the band with no
       affordance. The guard asserts the fit, so the next nav addition fails
       here instead of silently amputating "Developers".

   4b. THE PHONE SUBTITLE. `.section-head .section-sub` clamps to 2 lines at
       <=640px. The mitigation used to be a `title` attribute, which is a HOVER
       tooltip - absent on the exact device class the clamp fires on. Measured
       at 390px: 5 of 7 lines hidden on /cards/, and the hidden run is the
       "Treat this as a screen, not a forecast" disclaimer. The guard asserts a
       real tap target exists wherever the clamp actually hides text.

   4c. THE PROSPX COLUMN BOUNDARIES. Header and rows are INDEPENDENT grids that
       agree only because they are handed the same track list; anything that
       changes one side's gap, border or padding silently walks the header off
       the data. It had: `body.density-compact .player-header { gap: 8px }`
       named a class that occurs nowhere else in the file, so rows ran at 8px
       and the header stayed at 14px, and the 1px row card border took another
       2px out of the row's content box. Worst boundary drift 10.14px. The guard
       compares USED track geometry, header against every row.

Playwright/chromium are OPTIONAL; the browser tests skip cleanly when
unavailable (mirrors test_index_html_loads.py). The stack tests are pure text
and always run."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
SITE_CSS = ROOT / "assets" / "site.css"
PROSPX = ROOT / "prospx" / "index.html"

# The faces that must lead every copy stack, in order: the self-hosted face first
# (owner decision 2026-09-03: one letterform on every platform, Windows included;
# until then the Windows system faces led so a Windows reader never downloaded a
# copy webfont), then the Windows system faces as the swap-in fallback.
_EXPECTED_HEAD = ["PixelMplus12", "MS UI Gothic", "MS Gothic"]

# Every file that repeats the logo stack somewhere a var() cannot reach.
_LOGO_COPIES = [
    ROOT / "assets" / "eephus-gfx.js",
    ROOT / "assets" / "eephus-hub.js",
    ROOT / "assets" / "eephus-export.js",
    ROOT / "prospx" / "index.html",
]

# DotGothic16 named as a FACE rather than in prose: quoted inside a family list
# ("DotGothic16") or trailing a canvas / fonts.load shorthand ("26px DotGothic16").
# Deliberately not a bare-substring search - the comments that record WHY the
# face was retired have to keep naming it, and losing that history is how the
# omnibus-2 record and the shipped CSS ended up contradicting each other.
_RETIRED_AS_A_FACE = re.compile(r"""["']DotGothic16["']|\d\s*px\s+DotGothic16""")

# The head of a canvas font stack: the self-hosted face, then the Windows system
# face behind it (what a reader sees while the webfont is still swapping in).
_CANVAS_LOGO_HEAD = re.compile(r"""["']PixelMplus12["']\s*,\s*["']MS Gothic["']""")


def _token(text: str, name: str) -> str:
    """Return the raw value of a CSS custom property (may span lines)."""
    m = re.search(re.escape(name) + r"\s*:\s*(.*?);", text, re.S)
    assert m, f"{name} not found"
    return " ".join(m.group(1).split())


def _families(value: str) -> list[str]:
    return [f.strip().strip('"\'') for f in value.split(",")]


# ---------------------------------------------------------------- font stacks

def test_font_face_files_exist():
    """A @font-face src that 404s degrades silently to the next family, which is
    exactly the bug this face was added to fix."""
    css = SITE_CSS.read_text(encoding="utf-8")
    for url in re.findall(r'url\("(/assets/fonts/[^"]+)"\)', css):
        assert (ROOT / url.lstrip("/")).is_file(), f"@font-face src missing: {url}"


def test_pixelmplus_declared_with_both_weights():
    """`font-synthesis: none` is set on body, so a face without a real 700 makes
    every bold on the site render regular for anyone off Windows."""
    css = SITE_CSS.read_text(encoding="utf-8")
    blocks = re.findall(r"@font-face\s*\{[^}]*\}", css, re.S)
    pixel = [b for b in blocks if "PixelMplus12" in b]
    weights = {re.search(r"font-weight:\s*(\d+)", b).group(1) for b in pixel}
    assert weights == {"400", "700"}, f"expected 400+700, got {weights or 'none'}"


@pytest.mark.parametrize("token", ["--font-retro", "--font-retro-mono"])
def test_copy_stacks_lead_with_the_selfhosted_face_then_windows(token):
    css = _families(_token(SITE_CSS.read_text(encoding="utf-8"), token))
    head = css[: len(_EXPECTED_HEAD)]
    assert head[0] == "PixelMplus12", f"{token} must lead with PixelMplus12, got {head}"
    if token == "--font-retro-mono":
        # the mono token keeps MS Gothic before MS UI Gothic behind the face
        assert head[1] == "MS Gothic" and head[2] == "MS UI Gothic"
    else:
        assert head[1] == "MS UI Gothic" and head[2] == "MS Gothic"
    assert "monospace" in css[-1], "the monospace ladder must remain as last resort"


def test_logo_token_leads_with_the_selfhosted_face():
    """--font-logo is the ONE token that must not lead with the Windows system
    faces the copy tokens lead with. The wordmark has to be the same letterform
    on every platform, which means every platform downloads PixelMplus12."""
    fams = _families(_token(SITE_CSS.read_text(encoding="utf-8"), "--font-logo"))
    assert fams[0] == "PixelMplus12", f"--font-logo must lead PixelMplus12, got {fams}"
    assert "monospace" in fams[-1], "the monospace ladder must remain as last resort"


@pytest.mark.parametrize("path", _LOGO_COPIES + [SITE_CSS], ids=lambda p: p.name)
def test_no_file_still_names_the_retired_logo_face(path):
    """A stale copy does not throw - it rasterises the wordmark in the next family
    down, which stays invisible until someone compares two exports side by side."""
    stale = _RETIRED_AS_A_FACE.findall(path.read_text(encoding="utf-8"))
    assert not stale, f"{path.name} still names the retired logo face: {stale[:3]}"


@pytest.mark.parametrize("path", _LOGO_COPIES[:3], ids=lambda p: p.name)
def test_canvas_logo_literals_lead_with_the_same_face(path):
    """These three carry the logo stack as a literal because a canvas 2d context
    cannot read var(--font-logo). Nothing but this test links them to the token."""
    assert _CANVAS_LOGO_HEAD.search(path.read_text(encoding="utf-8")), (
        f"{path.name} has no PixelMplus12-led canvas font stack")


def test_prospx_export_warms_the_logo_face():
    """prospx awaits document.fonts.load before an html2canvas capture. If the
    warmup names a face the page no longer uses, the wait resolves against
    nothing and a cold first export captures the fallback."""
    text = PROSPX.read_text(encoding="utf-8")
    assert re.search(r"\d\s*px\s+PixelMplus12", text), "prospx warms no logo weight"


def test_font_face_does_not_declare_a_retired_family():
    css = SITE_CSS.read_text(encoding="utf-8")
    for block in re.findall(r"@font-face\s*\{[^}]*\}", css, re.S):
        fam = re.search(r"font-family:\s*\"([^\"]+)\"", block)
        assert fam and fam.group(1) == "PixelMplus12", f"unexpected @font-face: {block[:80]}"


@pytest.mark.parametrize("token", ["--font-retro", "--font-retro-mono"])
def test_prospx_token_mirrors_site_css(token):
    """PROSPX's own :root wins inside the app, so a one-sided edit splits the
    site's type identity in half without any test failing elsewhere."""
    a = _families(_token(SITE_CSS.read_text(encoding="utf-8"), token))
    b = _families(_token(PROSPX.read_text(encoding="utf-8"), token))
    assert a == b, f"{token} drifted:\n  site.css: {a}\n  prospx:   {b}"


# ------------------------------------------------------------- the name clip

@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


@pytest.mark.parametrize("route,card", [
    ("projections/", ".proj-board-table tbody tr[data-key]"),
    ("fa/", ".fa-card"),
])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_board_card_names_are_not_self_clipped(server, route, card, theme):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1226, "height": 900})
            page.add_init_script(
                "localStorage.setItem('prospect-tracker.theme', %r)" % theme)
            page.goto(server + route, wait_until="networkidle", timeout=60_000)
            page.wait_for_selector(card, timeout=30_000)
            page.wait_for_timeout(1200)
            clipped = page.evaluate(
                """(sel) => [...document.querySelectorAll(sel)].slice(0, 25)
                     .map(c => c.querySelector('.mlb-name'))
                     .filter(Boolean)
                     .map(n => ({t: (n.textContent || '').trim().slice(0, 24),
                                 clip: n.scrollHeight - n.clientHeight}))
                     .filter(x => x.clip > 0)""",
                card,
            )
            assert not clipped, (
                f"{route} ({theme}): {len(clipped)} name(s) clip their own line box "
                f"- the identity block does not fit row 1. First: {clipped[:3]}"
            )
        finally:
            browser.close()


# ------------------------------------------------- 4a. the nav link-strip fit

# Widths at which the whole strip must fit without scrolling. 1440 is the
# .eephus-nav max-width and the width at which the nav-control text labels come
# back (below it they are hidden, which is what buys the strip its room), so it
# is the tightest of the three. 1190px was the measured first-fit width on
# 2026-08-07; the widths below it are a horizontal-scroll band by design.
_NAV_FIT_WIDTHS = [1440, 1366, 1280]

# One generated page and one hand-authored page: build_site.py emits the nav for
# the former and prospx/index.html carries its own copy, and they have drifted
# apart before.
_NAV_PAGES = ["models/", "prospx/"]


@pytest.mark.parametrize("width", _NAV_FIT_WIDTHS)
@pytest.mark.parametrize("route", _NAV_PAGES)
def test_nav_link_strip_fits_without_scrolling(server, route, width):
    """The strip must not overflow its track at desktop widths.

    Deliberately `scrollWidth <= clientWidth` on .eephus-links rather than a
    px budget: the strip is content-sized, so its own width tells you nothing
    (that is the reading that produced a phantom "zero slack" finding). Only
    the overflow comparison distinguishes "fits" from "silently scrolls".
    """
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(server + route, wait_until="load", timeout=60_000)
            page.wait_for_selector("header.eephus-nav .eephus-links", timeout=30_000)
            page.wait_for_timeout(500)
            m = page.evaluate(
                """() => {
                     const l = document.querySelector(
                       'header.eephus-nav .eephus-links');
                     return {scrollW: l.scrollWidth, clientW: l.clientWidth,
                             items: l.children.length,
                             last: (l.lastElementChild || {}).textContent || ''};
                   }"""
            )
            assert m["scrollW"] <= m["clientW"], (
                f"{route} at {width}px: the nav link strip needs {m['scrollW']}px "
                f"but has {m['clientW']}px, so {m['scrollW'] - m['clientW']}px of "
                f"links ({m['items']} items, last is "
                f"{m['last'].strip()[:24]!r}) scroll off with no affordance above "
                "the 640px hamburger. Shorten a label or move an item into the "
                "MLB Modules / Diamond dropdown."
            )
        finally:
            browser.close()


# --------------------------------------------- 4b. the clamped phone subtitle

# Every surface that emits a .section-head .section-sub. The retired /cards/ screen
# was the one that mattered most (its hidden text WAS the disclaimer) but the guard
# is the rule, not the instance, so it sweeps the lot.
_SUB_PAGES = ["mlbstats/", "pal/", "betting/", "models/",
              "trademachine/", "projections/", "fa/", "glossary/"]


@pytest.mark.parametrize("route", _SUB_PAGES)
def test_phone_clamped_subtitle_has_a_tap_target(server, route):
    """Wherever the phone clamp hides text, a tap must reveal it.

    Three separate things have to hold and each has its own failure mode:
    the control has to EXIST, it has to be VISIBLE (a `display:none` button is
    the same as no button), and tapping it has to actually unhide the text.
    A `title` attribute satisfies none of them on a touch device, which is how
    the /cards/ disclaimer came to be unreadable on a phone.
    """
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    read = """() => [...document.querySelectorAll('.section-head .section-sub')]
                 .map(el => {
                   const b = el.nextElementSibling;
                   const isBtn = !!(b && b.classList &&
                                    b.classList.contains('section-sub-toggle'));
                   const r = isBtn ? b.getBoundingClientRect() : null;
                   return {hidden: el.scrollHeight - el.clientHeight,
                           text: (el.textContent || '').trim().slice(0, 40),
                           btn: isBtn,
                           shown: isBtn &&
                                  getComputedStyle(b).display !== 'none',
                           h: r ? Math.round(r.height) : 0};
                 })"""

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(server + route, wait_until="load", timeout=60_000)
            page.wait_for_selector(".section-head .section-sub", timeout=30_000)
            page.wait_for_timeout(600)

            subs = page.evaluate(read)
            assert subs, f"{route}: no .section-sub found - guard is mis-wired"

            for i, s in enumerate(subs):
                if s["hidden"] <= 0:
                    continue
                assert s["btn"] and s["shown"], (
                    f"{route} subtitle {i} ({s['text']!r}...) hides "
                    f"{s['hidden']}px of text at 390px with no visible control. "
                    "A title attribute does not count: it is a hover tooltip."
                )
                assert s["h"] >= 44, (
                    f"{route} subtitle {i}: expand control is {s['h']}px tall, "
                    "below the 44px touch target the rest of the site uses."
                )

            # ...and the tap has to work, not just exist.
            first = next((i for i, s in enumerate(subs) if s["hidden"] > 0), None)
            if first is not None:
                page.evaluate(
                    """(i) => document.querySelectorAll(
                         '.section-head .section-sub-toggle')[i].click()""",
                    first,
                )
                page.wait_for_timeout(200)
                after = page.evaluate(read)[first]
                assert after["hidden"] == 0, (
                    f"{route}: tapping the control left {after['hidden']}px of "
                    "the subtitle still hidden."
                )
        finally:
            browser.close()


# ------------------------------------------ 4c. the prospx column boundaries

# Column boundaries are derived from the USED (px-resolved) grid-template-columns
# plus column-gap, padding-left and border-left. That is the rendered geometry,
# not a proxy for it: it was checked against measured cell rects on 2026-08-07
# (header cell 1 at 18+235.219+14 = 267.22 measured, row cell 1 at 19+244.359+8
# = 271.36 measured). Comparing the geometry rather than the rects is what lets
# the guard ignore a row's extra absolutely-positioned children, which is
# exactly the false positive that made the farm list look 185px out of line
# when its tracks were within 1px.
_BOUNDS_JS = """(sel) => {
  const bounds = (el) => {
    const cs = getComputedStyle(el);
    const tracks = cs.gridTemplateColumns.split(' ').map(parseFloat);
    const gap = parseFloat(cs.columnGap) || 0;
    let x = parseFloat(cs.borderLeftWidth) + parseFloat(cs.paddingLeft);
    const out = [];
    tracks.forEach((t) => { out.push(x); x += t; out.push(x); x += gap; });
    return out;
  };
  let rows = [...document.querySelectorAll(sel[1])]
      .filter(r => r.getBoundingClientRect().width > 200);
  if (!rows.length) return {err: 'no rows for ' + sel[1]};
  const par = rows[0].parentElement;
  rows = rows.filter(r => r.parentElement === par);
  const h = par.querySelector(':scope > ' + sel[0]) ||
            document.querySelector(sel[0]);
  if (!h) return {err: 'no header for ' + sel[0]};
  const hb = bounds(h);
  let worst = 0, idx = -1;
  rows.forEach((r) => {
    const rb = bounds(r);
    for (let i = 0; i < Math.min(hb.length, rb.length); i++) {
      const d = Math.abs(rb[i] - hb[i]);
      if (d > worst) { worst = d; idx = i; }
    }
  });
  return {n: rows.length, worst: Math.round(worst * 1000) / 1000, idx: idx,
          hdrGap: getComputedStyle(h).columnGap,
          rowGap: getComputedStyle(rows[0]).columnGap};
}"""


@pytest.mark.parametrize("section,header,row", [
    ("active", ".col-header", ".player-row"),
    ("injured", ".col-header", ".player-row"),
    ("spotlights", ".spotlight-header", ".spotlight-row"),
])
def test_prospx_header_shares_the_row_column_boundaries(server, section, header, row):
    """Every column boundary in the header must land on the row's boundary.

    1.0px of tolerance, not 0: it absorbs sub-pixel fr distribution, and the
    defect this pins was an order of magnitude past it (10.14px).
    """
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.goto(server + "prospx/", wait_until="load", timeout=120_000)
            page.wait_for_selector(".player-row", timeout=90_000)
            page.wait_for_timeout(2500)
            page.click(f'[data-section="{section}"]', timeout=30_000)
            page.wait_for_timeout(3000)

            m = page.evaluate(_BOUNDS_JS, [header, row])
            assert not m.get("err"), f"{section}: {m.get('err')}"
            assert m["worst"] <= 1.0, (
                f"prospx {section}: {header} and {row} disagree by "
                f"{m['worst']}px at column boundary {m['idx']} across {m['n']} "
                f"rows (header column-gap {m['hdrGap']}, row {m['rowGap']}). "
                "They are independent grids - a gap, border or padding change "
                "on one side walks every later column off the data."
            )
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# The phone sparkline deliberately paints outside its own cell. This pins the
# clearance it has left, which is the part nobody measured.
# ---------------------------------------------------------------------------
_CHART_SPILL_JS = """() => {
  const rows = [...document.querySelectorAll('.player-row')];
  let worstSpill = 0, minClear = 1e9, charts = 0;
  rows.forEach((row, i) => {
    const svg = row.querySelector('.line-chart-cell svg');
    if (!svg) return;
    charts++;
    const cell = row.querySelector('.line-chart-cell');
    const sr = svg.getBoundingClientRect();
    worstSpill = Math.max(worstSpill, sr.bottom - cell.getBoundingClientRect().bottom);
    const next = rows[i + 1];
    if (next) minClear = Math.min(minClear, next.getBoundingClientRect().top - sr.bottom);
  });
  return {charts, worstSpill: Math.round(worstSpill),
          minClear: minClear === 1e9 ? null : Math.round(minClear)};
}"""


def test_phone_sparkline_spills_its_cell_but_clears_the_next_row(server):
    """The <=900px board gives .line-chart-cell a 42px box and lets a ~60px
    sparkline paint out of it on purpose, so the chart reads in full. That is
    fine right up until the spill reaches the row underneath, and the margin
    was never measured: it is ONE pixel.

    Measured 2026-08-07 at 390px: the chart clears its cell by 9px and the next
    row by 1px. This asserts the clearance, not the spill, because the spill is
    the intended behaviour and the collision is the bug. A row-gap change, a
    taller chart or a density tweak turns 1 into -3 with nothing else failing.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 900})
            page.goto(server + "prospx/", wait_until="load", timeout=120_000)
            page.wait_for_selector(".player-row", timeout=90_000)
            page.wait_for_timeout(2500)
            m = page.evaluate(_CHART_SPILL_JS)
            if not m["charts"]:
                pytest.skip("no sparklines rendered on the first board page")
            assert m["minClear"] is None or m["minClear"] >= 0, (
                f"the phone sparkline overlaps the next board row by "
                f"{-m['minClear']}px (it clears its own cell by {m['worstSpill']}px, "
                "which is intended). Either shorten the chart or widen the row gap."
            )
        finally:
            browser.close()
