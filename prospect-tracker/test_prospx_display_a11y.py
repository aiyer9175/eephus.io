# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX accessibility pass (DISPLAY_prospx, quality audit 2026-10-02 QPRA03 to QPRA13).

Measured on the served page before the pass: the GFX dialog took 0 of 40 Tabs
and the compare panel 0 of 12, Escape left the compare panel open, row Enter and
a detail-tab Enter dropped focus to <body>, 7 filter selects had no name, 0 of 44
chips carried aria-pressed, no tab marked its active state, the page had one
heading and no <main>, the sort-header ring was navy on the navy band (1.00:1),
light FV 20 badges read 3.68:1, dark FV 45 badges 3.74:1, the tool history legend
1.23:1 to 2.72:1, and 288 text nodes on board page 1 (1280, light) failed AA.

The static checks pin each repair in the page source; the browser checks walk the
keyboard paths the audit walked.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import serve_site

ROOT = Path(__file__).parent
PAGE = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")


def _lum(h: str) -> float:
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _blocks():
    """(light, dark) token blocks of the page's own :root."""
    i_dark = PAGE.index("DARK MODE = Topps Chrome")
    return PAGE[:i_dark], PAGE[i_dark:i_dark + 30000]


def _tok(block: str, name: str) -> str:
    m = re.search(re.escape(name) + r":\s*(#[0-9A-Fa-f]{6})", block)
    assert m, name
    return m.group(1)


# ---------------------------------------------------------------- static pins

def test_qpra03_dialogs_are_modal_and_rows_link_their_name():
    assert 'id="gfx-overlay" role="dialog" aria-modal="true"' in PAGE
    assert 'id="compare-panel" role="dialog" aria-modal="true"' in PAGE
    fn = PAGE[PAGE.index("function _pxWireA11y()"):]
    fn = fn[:fn.index("\nif (document.readyState")]
    assert 'e.key === "Escape"' in fn and 'e.key !== "Tab"' in fn
    assert "o.focus()" in fn, "focus goes back to the opener on close"
    deco = PAGE[PAGE.index("function decorateA11yRows()"):]
    assert deco.index("_pxRowNameLink(row)") < deco.index('setAttribute("role", "button")')
    link = PAGE[PAGE.index("function _pxRowNameLink("):]
    assert 'a.href = "#player=" + encodeURIComponent(row.dataset.key)' in link[:900]
    go = PAGE[PAGE.index("function goToPlayer(key)"):][:220]
    assert "_pxFocusSoon(" in go and "player-display-name" in go


def test_qpra04_filter_groups_selects_chips_and_org_picker():
    assert 'id="filter-toggle" type="button" aria-expanded="false" aria-controls="filter-bar"' in PAGE
    sync = PAGE[PAGE.index("function _pxA11ySync()"):][:3200]
    assert 'g.setAttribute("role", "group")' in sync
    assert 's.setAttribute("aria-labelledby", lab.id)' in sync
    assert 'b.setAttribute("aria-pressed"' in sync
    picker = PAGE[PAGE.index("function mountOrgPicker("):][:4200]
    assert 'panel.addEventListener("keydown"' in picker
    assert '"ArrowDown"' in picker and '"ArrowUp"' in picker and '"Escape"' in picker


def test_qpra05_tabs_state_and_section_menu_escape():
    sync = PAGE[PAGE.index("function _pxA11ySync()"):][:3200]
    assert 'setAttribute("aria-current", "page")' in sync
    assert 'role="tab" aria-selected=' in PAGE, "the scouting source strip's buttons are tabs"
    assert 'sectionTabsBar.addEventListener("keydown"' in PAGE


def test_qpra06_main_landmark_heading_name_and_card_headings():
    assert '<main id="content">' in PAGE and "</main>" in PAGE
    assert '<h1 aria-label="PROSPX">' in PAGE
    # The vector badge, or the pixel mark PB-05 writes under PIXEL_BRAND: hidden
    # either way, the h1's aria-label names it.
    assert re.search(r'<svg class="h1-logo(?: wm-px px-mark)?" [^>]*\baria-hidden="true"', PAGE)
    sync = PAGE[PAGE.index("function _pxA11ySync()"):][:3200]
    assert 'h.setAttribute("aria-level", "2")' in sync and 'h.setAttribute("aria-level", "3")' in sync
    assert "document.title = name ?" in sync


def test_qpra07_sort_header_ring_contrasts_with_the_header_band():
    assert re.search(r"\.col-header \.sort-header:focus-visible,[^{]*\{ outline-color: var\(--col-header-fg\); \}", PAGE)
    light, _ = _blocks()
    assert _ratio(_tok(PAGE, "--col-header-fg"), "#0E2B4D") >= 3.0


def test_qpra08_qpra12_reading_inks_clear_aa_on_the_row_ground():
    light, dark = _blocks()
    row_ground = "#ECE6D6"
    for name in ("--age-young-ink", "--eta-near-ink", "--eta-far-ink", "--up", "--neon-green"):
        assert _ratio(_tok(light, name), row_ground) >= 4.5, name
    fn = PAGE[PAGE.index("function _ageHeatColor("):][:500]
    assert not re.search(r'"#[0-9a-fA-F]{3,6}"', fn), "age tint is a token, not a raw hex"
    assert ".eta-near     { color: var(--eta-near-ink); }" in PAGE


def test_qpra09_fv_tier_badges_and_tool_codes():
    light, dark = _blocks()
    for t in ("20", "25"):
        assert _ratio(_tok(light, f"--fv-{t}-fg"), _tok(light, f"--fv-{t}-bg")) >= 4.5, t
    assert _ratio(_tok(dark, "--fv-45-fg"), _tok(dark, "--fv-45-bg")) >= 4.5
    rule = PAGE[PAGE.index(".tool-grade-pill .tg-code {"):][:120]
    assert "opacity" not in rule.split("}")[0]


def test_qpra10_tool_history_series_are_theme_tokens():
    fn = PAGE[PAGE.index("function _toolHistoryChart("):]
    fn = fn[:fn.index("\nfunction ")]
    assert not re.search(r"#[0-9A-Fa-f]{6}", fn), "no raw hex in the tool history chart"
    light, _ = _blocks()
    for i in range(1, 8):
        assert _ratio(_tok(light, f"--tool-s{i}"), "#FBF8F0") >= 4.5, i
    assert 'color:var(--text-primary);font-weight:700;">${escapeHtml(lbl)}' in fn


def test_qpra11_phone_targets():
    block = PAGE[PAGE.index("QPRA11: chips, sort headers"):][:900]
    for sel in ("button.chip { min-width: 44px; }", ".col-header .sort-header, .debut-header .sort-header { min-height: 44px;", ".org-picker-trigger",
                ".debut-row .compare-add-btn.is-compact", ".back-link"):
        assert sel in block, sel


def test_qpra13_live_region_and_named_glyphs():
    assert '<div id="px-live" class="visually-hidden" role="status" aria-live="polite"></div>' in PAGE
    assert '<span class="health-glyph is-${tier}" role="img"' in PAGE
    assert '<span class="visually-hidden">thinly sourced</span>' in PAGE
    assert '<div class="fa-note" aria-live="polite"' in PAGE


def test_qprp02_boot_holds_the_viewport():
    assert "#content { min-height: 100vh; }" in PAGE


# ---------------------------------------------------------------- browser walk

@pytest.fixture(scope="module")
def page_and_base():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"chromium not installed for playwright: {exc}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        page.goto(base + "prospx/index.html", wait_until="load", timeout=30_000)
        try:
            page.wait_for_selector("#rows .player-row a.row-name-link", timeout=60_000)
        except Exception:
            pass
        yield page, base, errs
        browser.close()


_AE = "() => { const e = document.activeElement; return e && e !== document.body ? (e.id || e.className || e.tagName) : 'BODY'; }"


def test_browser_board_semantics(page_and_base):
    page, _, errs = page_and_base
    info = page.evaluate("""() => {
      const r = document.querySelector('#rows .player-row');
      const chips = [...document.querySelectorAll('#filter-bar button.chip[data-filter-level]')];
      const sels = [...document.querySelectorAll('#filter-bar select')];
      return { rowRole: r && r.getAttribute('role'), link: !!(r && r.querySelector('a.row-name-link')),
               pressed: chips.filter(c => c.hasAttribute('aria-pressed')).length, chips: chips.length,
               unnamed: sels.filter(s => !s.getAttribute('aria-label') && !s.getAttribute('aria-labelledby')).length,
               current: document.querySelectorAll('.section-tab[aria-current="page"]').length,
               skip: !!document.querySelector('a.skip-link'), main: !!document.querySelector('main#content'),
               live: document.getElementById('px-live').textContent };
    }""")
    assert info["link"] and info["rowRole"] is None
    assert info["chips"] and info["pressed"] == info["chips"]
    assert info["unnamed"] == 0
    assert info["current"] == 1
    assert info["skip"] and info["main"]
    assert info["live"].startswith("Showing")
    assert not errs, errs


def test_browser_gfx_dialog_traps_and_returns_focus(page_and_base):
    page, _, _ = page_and_base
    page.focus(".gfx-list-btn")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    assert page.evaluate(_AE) == "gfx-close"
    inside = 0
    for _ in range(25):
        page.keyboard.press("Tab")
        inside += page.evaluate("document.getElementById('gfx-overlay').contains(document.activeElement)")
    assert inside == 25
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert not page.evaluate("document.getElementById('gfx-overlay').classList.contains('is-open')")
    assert "gfx-list-btn" in page.evaluate(_AE)


def test_browser_row_link_opens_card_with_focus_on_the_name(page_and_base):
    page, _, _ = page_and_base
    page.focus("#rows .player-row a.row-name-link")
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.activeElement && document.activeElement.classList.contains('player-display-name')",
                           timeout=10_000)
    assert page.evaluate("document.title").endswith(" - PROSPX - eephus.io")
    page.wait_for_function("() => document.activeElement.getAttribute('role') === 'heading'", timeout=5_000)
    page.focus(".detail-tab:nth-child(2)")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1500)
    assert page.evaluate("document.activeElement.classList.contains('detail-tab')")
    assert page.evaluate("document.activeElement.getAttribute('aria-current')") == "page"
