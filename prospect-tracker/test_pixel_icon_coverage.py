# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""T2 (final-pass plan 5.7.4): every place a reader scans a list of modules
draws the module's pixel icon, and the top bar stays text.

Pins: every nav_leaves() key, every PROSPX data-section, the four footer
routes and every _collect_events wire type have a drawing; _nav() puts one
12 px icon on each dropdown leaf and shows none on a top-bar leaf (a top-level
leaf's icon lives in .nav-drawer-ico, which site.css shows only in the open
phone drawer); the three control glyphs are pixel icons (owner answer PX-Q2);
the rail, the PROSPX sub-nav, the cross-module cards, the module mastheads and
the /team/ badges draw from the one sprite; the unicode sidebar_icons map is
gone; and the three hand-kept static navs carry the icon ICON_FOR gives each
link's key (PX-10).
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent
STATIC_NAV_PAGES = ("prospx/index.html", "collegesavant/index.html", "collegesavant/pitcher_index.html")
_ICO = re.compile(r'<svg class="ico" width="(\d+)" height="\d+"[^>]*><use href="[^"#]*#i-([\w-]+)"[^>]*/></svg>')
_NAV_RE = re.compile(r'<nav\s+class="eephus-links">(.*?)</nav>', re.S)
_MENU_RE = re.compile(r'<div class="eephus-nav-menu" role="menu">(.*?)</div>', re.S)


def _sym(key: str) -> str:
    return B.ICON_FOR.get(key, key)


def _icons(html: str) -> list[tuple[int, str]]:
    return [(int(w), s) for w, s in _ICO.findall(html)]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _prospx_sections() -> list[str]:
    return re.findall(r'<button class="section-tab(?: active)?" data-section="([\w-]+)"', _src("prospx/index.html"))


def _wire_types() -> set[str]:
    body = inspect.getsource(B._collect_events)
    types: set[str] = set()
    for m in re.finditer(r'\badd\(\s*[^,]+,\s*"(\w+)"(?:\s+if\s+\w+\s+else\s+"(\w+)")?', body):
        types.update(t for t in m.groups() if t)
    return types


# ------------------------------------------------------------ coverage

def test_every_vocabulary_key_has_a_drawing():
    keys = [k for k, _l, _h in B.nav_leaves()]
    keys += ["models", "parks", "news", "history", "watchlist"]
    keys += _prospx_sections()
    keys += sorted(_wire_types())
    missing = [k for k in keys if _sym(k) not in B.ICON_KEYS]
    assert not missing, missing


def test_the_vocabularies_are_the_ones_the_site_uses():
    assert len(_prospx_sections()) == 12
    assert _wire_types() == {"up", "down", "promo", "demo", "il", "debut", "trade", "signing"}


def test_the_unicode_sidebar_glyph_map_is_gone():
    assert "sidebar_icons" not in _src("build_site.py")


# ---------------------------------------------------------- the top bar

def test_nav_gives_each_dropdown_leaf_one_12px_icon():
    out = B._nav("ledger")
    groups = [i for i in B.NAV_ITEMS if B._nav_is_group(i)]
    menus = _MENU_RE.findall(out)
    assert len(menus) == len(groups)
    for grp, menu in zip(groups, menus):
        leaves = re.findall(r"<a\b[^>]*>(.*?)</a>", menu, re.S)
        assert len(leaves) == len(grp["children"])
        for (k, label, _h), inner in zip(grp["children"], leaves):
            assert _icons(inner) == [(12, _sym(k))], (k, inner[:160])
            assert inner.endswith(f"</svg>{label}"), "the label follows the icon unchanged"


def test_top_bar_leaves_stay_text():
    nav = _NAV_RE.search(B._nav("ledger")).group(1)
    nav = re.sub(r"<details\b.*?</details>", "", nav, flags=re.S)
    tops = [i for i in B.NAV_ITEMS if not B._nav_is_group(i)]
    links = re.findall(r"<a\b[^>]*>(.*?)</a>", nav, re.S)
    assert len(links) == len(tops)
    for (k, _l, _h), inner in zip(tops, links):
        # the only icon on a top-level leaf is the drawer one, which the
        # one-line bar never shows
        assert inner.startswith('<span class="nav-drawer-ico">'), (k, inner[:120])
        assert _icons(inner) == [(12, _sym(k))]
        assert "<svg" not in re.sub(r'<span class="nav-drawer-ico">.*?</span>', "", inner, flags=re.S)
    css = _src("assets/site.css")
    assert ".eephus-nav .nav-drawer-ico { display: none; }" in css
    shown = [ln for ln in css.splitlines() if ".nav-drawer-ico" in ln and "display: block" in ln]
    assert shown and all("[data-nav-open]" in ln for ln in shown), shown


def test_nav_controls_are_pixel_icons_with_the_same_labels():
    out = B._nav("ledger")
    ctrl = out[out.index('<div class="eephus-nav-controls">'):]
    assert [s for _w, s in _icons(ctrl)] == ["search", "watchlist", "theme-dark", "theme-light"]
    for glyph in ("⌘K</span>", "★", "☾", "☀"):
        assert glyph not in ctrl, glyph
    for aria in ('aria-label="Quick search (Ctrl+K)"', 'aria-label="Watchlist"', 'aria-label="Toggle dark mode"'):
        assert aria in ctrl
    assert "☾" not in B.THEME_BTN and "☀" not in B.THEME_BTN
    assert [s for _w, s in _icons(B.THEME_BTN)] == ["theme-dark", "theme-light"]


# ------------------------------------------- rail, cards, mastheads, team

@pytest.fixture(scope="module")
def home() -> str:
    return B.build_home([], {})


def test_rail_draws_16px_module_icons_and_12px_tab_icons(home):
    nav = re.search(r'<nav class="sb-nav">(.*?)</nav>', home, re.S).group(1)
    links = re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', nav, re.S)
    by_href = {h: k for k, _l, h in B.nav_leaves()}
    assert len(links) == len(by_href)
    for href, inner in links:
        assert _icons(inner) == [(16, _sym(by_href[href]))], href
    sub = re.search(r'<nav class="sb-subnav">(.*?)</nav>', home, re.S).group(1)
    subs = re.findall(r'<a href="([^"]+)">(.*?)</a>', sub, re.S)
    assert len(subs) == len(B.PROSPX_SUBNAV)
    for href, inner in subs:
        assert _icons(inner) == [(12, _sym(B._prospx_subnav_section(href)))], href
        assert "›" not in inner
    lockup = re.search(r'sb-group-label--lockup">(.*?)PROSPX</div>', home, re.S).group(1)
    assert _icons(lockup) == [(12, "prospx")]
    assert 'class="px-ball"' not in home


def test_cross_module_card_titles_carry_one_16px_icon():
    strip = B._cross_module_strip()
    titles = re.findall(r'<span class="xmod-title">(.*?)</span>', strip, re.S)
    assert titles
    for t in titles:
        icons = _icons(t)
        assert len(icons) == 1 and icons[0][0] == 16, t[:120]
        text = re.sub(r"<svg\b.*?</svg>", "", t, flags=re.S)
        assert text[:1].isascii() and text[:1].isalpha(), f"a glyph is left in {text!r}"


MASTHEADS = {
    "news": lambda: B.build_news({}), "history": lambda: B.build_this_day({}),
    "articles": lambda: B.build_articles_index([]), "forums": B.build_forums_index,
    "fa": B.build_fa, "projections": B.build_projections, "arbitration": B.build_arbitration,
    "trademachine": B.build_trademachine, "mlbstats": B.build_mlbstats, "pal": B.build_pal,
    "fantasy": B.build_fantasy, "betting": B.build_betting, "diamond": B.build_diamond,
    "parks": B.build_parks, "management": B.build_management, "ledger": B.build_ledger,
    "franchise": B.build_franchise, "hof": B.build_hof, "models": B.build_models,
    "glossary": B.build_glossary, "team": B.build_team,
}


def test_every_module_page_key_has_a_masthead_case():
    """Every page() `active` key that names a module masthead is listed above,
    so a new module page cannot ship without its masthead icon. /history/
    passes no nav key (nothing in the top bar lights for it) and is listed by
    its footer route."""
    src = _src("build_site.py")
    keys = set(re.findall(r'return page\([^,]+,\s*"(\w+)"', src))
    assert keys | {"history"} == set(MASTHEADS), sorted((keys | {"history"}) ^ set(MASTHEADS))


@pytest.mark.parametrize("key", sorted(MASTHEADS))
def test_masthead_draws_one_32px_icon_first_in_the_h1(key):
    out = MASTHEADS[key]()
    icons32 = [s for w, s in _icons(out) if w == 32]
    assert icons32 == [_sym(key)], icons32
    h1 = re.search(r"<h1>(.*?)</h1>", out, re.S).group(1)
    assert h1.startswith('<svg class="ico" width="32"'), h1[:80]
    if key in B.MODULE_STAGE:
        assert B._stage_chip(key) in h1, "the stage chip is untouched"


def test_team_badges_are_sprite_symbols():
    """The Masthead's attribution badges (TEAM_1, 2026-10-02): one 16 px symbol
    per credit on a card front, one 12 px symbol per row of the back's table,
    every one drawn from the sprite; nothing on the page is gold."""
    out = B.build_team()
    front = re.findall(r'<li class="tc-badge"[^>]*>(.*?)</li>', out, re.S)
    rows = re.findall(r'<tr data-badge="[\w-]+"><td>(.*?)</td>', out, re.S)
    assert front and rows
    for m in front:
        assert [w for w, _s in _icons(m)] == [16], m[:120]
    for m in rows:
        assert [w for w, _s in _icons(m)] == [12], m[:120]
    assert "accent-gold" not in out


# ------------------------------------------------- the hand-kept pages

@pytest.mark.parametrize("rel", STATIC_NAV_PAGES)
def test_static_nav_links_carry_the_icon_icon_for_gives_their_key(rel):
    nav = _NAV_RE.search(_src(rel)).group(1)
    by_href = {h: k for k, _l, h in B.nav_leaves()}
    links = re.findall(r'<a href="([^"]+)"([^>]*)>(.*?)</a>', nav, re.S)
    assert len(links) == len(by_href)
    for href, attrs, inner in links:
        key = by_href[href]
        assert _icons(inner) == [(12, _sym(key))], (rel, href, inner[:120])
        if 'role="menuitem"' not in attrs:
            assert inner.startswith('<span class="nav-drawer-ico">'), (rel, href)


@pytest.mark.parametrize("rel", STATIC_NAV_PAGES)
def test_static_nav_controls_are_pixel_icons(rel):
    text = _src(rel)
    ctrl = text[text.index('<div class="eephus-nav-controls">'):]
    ctrl = ctrl[:ctrl.index("</header>")]
    syms = [s for _w, s in _icons(ctrl)]
    want = ["watchlist", "theme-dark", "theme-light"] if rel.startswith("prospx") else \
        ["search", "watchlist", "theme-dark", "theme-light"]
    assert syms == want, syms
    for glyph in ("&#8984;", "&#9733;", "&#9790;", "&#9728;", "★", "☾", "☀"):
        assert glyph not in ctrl, glyph


def test_prospx_section_tabs_and_glossary_tab_carry_their_icons():
    text = _src("prospx/index.html")
    tabs = re.findall(r'<button class="section-tab(?: active)?" data-section="([\w-]+)"[^>]*>(.*?)</button>', text, re.S)
    assert len(tabs) == 12
    for sec, inner in tabs:
        assert _icons(inner) == [(12, _sym(sec))], sec
    gl = re.search(r'<a class="section-tab section-tab-link" href="/glossary/"[^>]*>(.*?)</a>', text, re.S).group(1)
    assert _icons(gl) == [(12, "glossary")]
    assert "section-tab-glyph" not in text


def test_prospx_theme_toggle_swaps_glyphs_not_text():
    text = _src("prospx/index.html")
    assert 'icon.textContent = theme === "dark"' not in text
    assert '.theme-icon [data-theme-glyph]' in text
    assert 'data-theme-glyph="light"' in text and 'data-theme-glyph="dark" hidden' in text


# ------------------------------------------------ the wire pictograms (PX-17)

_KNOWN_WIRE = ("up", "down", "promo", "demo", "il", "debut", "trade", "signing")


@pytest.mark.parametrize("typ", _KNOWN_WIRE)
def test_wire_rows_draw_the_event_pictogram(typ):
    """The sidebar feed, the /news/ row and the WIRE ticker draw the type's 12 px
    icon inside the type's own coloured span instead of a text glyph."""
    feed = B._feed_item_html(typ, "GLYPH", "t", "k", None, "Name", "val")
    news = B._news_item_html(typ, "GLYPH", "t", "k", None, "Name", "val", "", {})
    tick = B._ticker_html([("2026-10-01", typ, "GLYPH", "text", "k", None, "Name", "val")])
    want = (12, _sym(typ))
    for html in (feed, news):
        assert f'<span class="feed-val {typ}"><svg class="ico"' in html
        assert _icons(html) == [want]
        assert "GLYPH" not in html
    assert f'<span class="{typ}"><svg class="ico"' in tick
    assert _icons(tick) == [want, want] and "GLYPH" not in tick  # the track loops twice


def test_an_unknown_wire_type_keeps_its_text_glyph():
    html = B._feed_item_html("other", "◆", "t", "k", None, "Name", "val")
    assert _icons(html) == [] and "◆val" in html


def test_trade_on_the_wire_panel_is_panel_ink_not_gold():
    """Owner answer PX-Q3: the trade pictogram (and the untyped ticker glyph)
    take the panel's own ink; gold on the dark panel means elite FV only."""
    css = _src("assets/site.css")
    for sel in (".home-ticker .ticker-track .trade", ".home-ticker .ticker-track .glyph",
                ".feed-item .g.trade, .feed-item .feed-val.trade"):
        m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", css)
        assert m, sel
        assert "color: inherit" in m.group(1) and "gold" not in m.group(1), sel
