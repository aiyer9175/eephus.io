# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /fantasy/ display pass (surface-quality audit 2026-10-02, DISPLAY_fantasy).

One pin per finding the pass fixed:

  QREA08  the player card is a real modal: the page's header, main and footer
          are inert while it is open, Tab and Shift+Tab wrap inside the panel,
          and Escape hands focus back to the opener with nothing left inert.
  QREA09  a sort chip is ONE Tab stop: its glossary hook rides the chip, no
          focusable element sits inside it, and at 390 px it is a 44 px target.
  QREA10  the board's small labels and the module tab subtitles take a token
          colour, not opacity, and read at 4.5:1 or better in both themes.
  QREC03  the Dynasty "Star" column printed the star BUCKET share under the
          Star Odds name and link; it is labelled and linked as the bucket.

The source guards always run; the rendered half needs playwright.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import serve_site

ROOT = Path(__file__).parent
CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")


def _src(name: str) -> str:
    return (ROOT / "assets" / name).read_text(encoding="utf-8")


def _sort_btn(name: str) -> str:
    return _src(name).split("function sortBtn(")[1].split("\n  function ")[0]


# ---- QREA09 -----------------------------------------------------------------
@pytest.mark.parametrize("name", ["redraft.js", "dynasty.js"])
def test_sort_chip_carries_the_glossary_hook_itself(name):
    body = _sort_btn(name)
    # the term rides the chip; the label span inside it has no data-gl and so
    # never gets wire()'s tabindex
    assert "' data-gl=\"' + esc(c.term)" in body, name
    assert "glossLbl(c)" not in body.split("var on = st.key")[1], name
    assert '<span class="g-term">' in body, name


def test_phone_sort_chips_are_44px_targets():
    m = re.search(r"@media \(max-width: 640px\) \{\s*\.ff-sortbar \[role=\"button\"\],\s*"
                  r"\.ff-card-head \[role=\"button\"\] \{([^}]*)\}", CSS)
    assert m, "the /fantasy/ phone chip rule moved; re-point this guard"
    assert "min-height: 44px" in m.group(1) and "min-width: 44px" in m.group(1)


# ---- QREA10 -----------------------------------------------------------------
@pytest.mark.parametrize("sel", [r"\.mlb-metric-label", r"\.mlb-chip b"])
def test_board_labels_use_a_token_colour_not_opacity(sel):
    m = re.search(r"(?m)^" + sel + r" \{([^}]*)\}", CSS)
    assert m, sel
    assert "opacity" not in m.group(1) and "color: var(--text-secondary)" in m.group(1), m.group(1)


def test_module_tab_subtitle_uses_a_token_colour_not_opacity():
    hub = _src("fantasy-hub.js")
    rule = hub.split(".fantasy-modbtn .fh-modsub{display:block")[1].split("}")[0]
    assert "opacity" not in rule and "color:var(--text-secondary)" in rule, rule
    assert ".fantasy-modbtn.active .fh-modsub{color:inherit}" in hub


# ---- QREA08 -----------------------------------------------------------------
def test_card_source_holds_the_page_and_wraps_tab():
    src = _src("fantasy-card.js")
    assert 'querySelectorAll("body > header, body > main, body > footer")' in src
    assert "holdPage(true)" in src and "holdPage(false)" in src
    assert 'e.key === "Tab" && S.id != null) trapTab(e)' in src
    # close() releases the page BEFORE it hands focus back to the opener
    close = src.split("function close() {")[1].split("\n  }")[0]
    assert close.index("holdPage(false)") < close.index("S.lastFocus.focus()")


# ---- QREC03 -----------------------------------------------------------------
# The column prints xfv p_bucket["star"] (fantasy_export, star = p_bucket star),
# the share of the five-bucket star outcome. star_odds defines the published
# Star Odds tier value, a different number, so the label, the tooltip and the
# glossary link name the bucket.
def test_star_column_names_the_bucket_it_prints():
    dyn, card = _src("dynasty.js"), _src("fantasy-card.js")
    for name, src in (("dynasty.js", dyn), ("fantasy-card.js", card)):
        assert '"star_odds"' not in src, name
        assert "P(star outcome)" not in src, name
    col = dyn.split('{ key: "star",')[1].split("} },")[0]
    assert 'label: "Star bucket"' in col and 'term: "bust_prob"' in col, col
    assert 'title: "Share of the star (Elite) outcome bucket"' in col, col
    assert "return d.star;" in col          # the served number is unchanged
    assert 'gl("Star bucket", "bust_prob")' in card
    assert "star (Elite) bucket share" in dyn
    assert "Sorted by star odds" not in dyn


# ---- rendered ---------------------------------------------------------------
@pytest.fixture(scope="module")
def server():
    with serve_site() as base:
        yield base


_CONTRAST = """sel => {
  const cv = document.createElement('canvas'); cv.width = cv.height = 1;
  const cx = cv.getContext('2d', {willReadFrequently: true});
  const parse = c => { const m = /rgba?\\(([^)]+)\\)/.exec(c);
    if (m) { const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; }
    cx.clearRect(0, 0, 1, 1); cx.fillStyle = c; cx.fillRect(0, 0, 1, 1);
    const d = cx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const bgOf = el => { const st = []; for (let p = el; p; p = p.parentElement) {
      const c = parse(getComputedStyle(p).backgroundColor); if (c[3] > 0) { st.push(c); if (c[3] >= 1) break; } }
    let base = [255, 255, 255]; if (st.length && st[st.length - 1][3] >= 1) base = st.pop().slice(0, 3);
    for (let i = st.length - 1; i >= 0; i--) { const a = st[i][3]; base = base.map((v, k) => Math.round(st[i][k] * a + v * (1 - a))); }
    return base; };
  const op = el => { let o = 1; for (let p = el; p; p = p.parentElement) o *= Number(getComputedStyle(p).opacity); return o; };
  return [...document.querySelectorAll(sel)].filter(e => e.getBoundingClientRect().width > 0).slice(0, 40).map(e => {
    const bg = bgOf(e), c = parse(getComputedStyle(e).color), a = c[3] * op(e);
    const fg = c.slice(0, 3).map((v, k) => Math.round(v * a + bg[k] * (1 - a)));
    const L1 = lum(fg), L2 = lum(bg);
    return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); });
}"""


def _browser(p):
    try:
        return p.chromium.launch()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"chromium not installed for playwright: {exc}")


def _dynasty(page, server):
    page.goto(server + "fantasy/#m=dynasty&section=dynasty", wait_until="load", timeout=90_000)
    try:
        page.wait_for_function(
            "() => document.querySelectorAll('#dynasty-app-root .ff-sortbar [data-dynsort]').length > 2",
            timeout=60_000)
    except Exception:  # noqa: BLE001
        pytest.skip("the Dynasty board painted no cards on this machine's data")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_rendered_labels_and_subtitles_clear_4_5(server, theme):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _browser(p)
        try:
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme=theme)
            ctx.add_init_script(
                "try{localStorage.setItem('prospect-tracker.theme','" + theme + "')}catch(e){}")
            page = ctx.new_page()
            _dynasty(page, server)
            for sel in (".mlb-chip b", ".mlb-metric-label", ".fh-modsub"):
                ratios = page.evaluate(_CONTRAST, sel)
                assert ratios, sel
                assert min(ratios) >= 4.5, (theme, sel, min(ratios))
        finally:
            browser.close()


def test_rendered_sort_chips_are_one_tab_stop_and_44px_on_a_phone(server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = _browser(p)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            _dynasty(page, server)
            chips = page.evaluate(
                "() => [...document.querySelectorAll('#dynasty-app-root [data-dynsort]')].map(c => ({"
                " inner: c.querySelectorAll('[tabindex],a[href],button,[data-gl]').length,"
                " h: c.getBoundingClientRect().height, w: c.getBoundingClientRect().width,"
                " desc: c.getAttribute('aria-describedby'), gl: c.getAttribute('data-gl') }))")
            assert chips
            assert all(c["inner"] == 0 for c in chips), chips
            assert all(c["h"] >= 44 and c["w"] >= 40 for c in chips), chips
            # every chip that names a term is described by that term's definition
            termed = [c for c in chips if c["gl"]]
            assert termed and all(c["desc"] == "gl-def-" + c["gl"] for c in termed), termed
        finally:
            browser.close()


@pytest.mark.parametrize("width,theme", [(1280, "light"), (390, "dark")])
def test_rendered_card_is_modal(server, width, theme):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    inside = ("() => { const d = document.querySelector('.fc-panel[role=dialog]');"
              " return !!(d && d.contains(document.activeElement)); }")
    with sync_playwright() as p:
        browser = _browser(p)
        try:
            ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=theme)
            page = ctx.new_page()
            _dynasty(page, server)
            page.evaluate("() => document.querySelector('#dynasty-app-root a.dyn-name-link[href*=\"player=\"]')"
                          ".setAttribute('data-qa-open', '1')")
            page.focus("[data-qa-open='1']")
            page.keyboard.press("Enter")
            page.wait_for_function(inside, timeout=30_000)
            held = page.evaluate("() => ['header', 'main', 'footer'].map(t => {"
                                 " const e = document.querySelector('body > ' + t); return !!(e && e.inert); })")
            assert held == [True, True, True], held
            for key in ("Tab", "Shift+Tab"):
                for _ in range(40):
                    page.keyboard.press(key)
                    assert page.evaluate(inside), key + " left the card"
            page.keyboard.press("Escape")
            page.wait_for_function("() => document.querySelector('.fc-wrap').hasAttribute('hidden')")
            assert page.evaluate("() => document.activeElement.getAttribute('data-qa-open')") == "1"
            assert page.evaluate("() => document.querySelectorAll('[inert]').length") == 0
        finally:
            browser.close()
