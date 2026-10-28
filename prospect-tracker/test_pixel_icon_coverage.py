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

import html
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
    # The type codes of the MLB News registry (HOME_2) that the wire emits today.
    assert _wire_types() == {"grade_up", "grade_down", "promo", "demo", "il_place", "debut", "trade",
                             "fa_sign", "minor_deal", "opt_declined", "opt_exercised", "qo"}
    assert _wire_types() <= set(B._WIRE_TYPES)


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


# ------------------------------------------- rail, cards, mastheads, team

@pytest.fixture(scope="module")
def home() -> str:
    return B.build_home([], {})


def test_band_links_and_band_marks_draw_their_pixel_icons(home):
    # HOME_4: the homepage's module list is the shared header's (its icons are
    # pinned with the header above); the PROSPX sub-nav is the Prospects
    # band's link row, every section still one click away.
    sub = re.search(r'<nav class="band-links"[^>]*>(.*?)</nav>', home, re.S).group(1)
    subs = re.findall(r'<a href="([^"]+)">(.*?)</a>', sub, re.S)
    assert len(subs) == len(B.PROSPX_SUBNAV)
    for href, inner in subs:
        assert _icons(inner) == [(12, _sym(B._prospx_subnav_section(href)))], href
        assert "›" not in inner
    lead = sub.split('<span class="band-links-lab">PROSPX</span>', 1)[0]
    assert _icons(lead) == [(12, "prospx")]
    for band in B.HOME_BAND_ORDER:
        mark = re.search(rf'id="band-{band}".*?<span class="band-mark">(.*?)</span>', home, re.S).group(1)
        # HOME_7 (PA3): the family's key mark first; the Prospects band adds
        # i-collegesavant beside i-prospx.
        assert _icons(mark) == [(32, _sym(m)) for m in B._HOME_BANDS[band][3]], band
        assert B._HOME_BANDS[band][3][0] == B._WIRE_FAMILIES[band]["mark"]
    assert 'class="px-ball"' not in home


def test_cross_module_card_titles_carry_one_16px_icon():
    strip = B._xmod_cards_html()
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
    "glossary": B.build_glossary, "team": B.build_team, "scores": B.build_scores,
    # /scouting/ (TL_22) is built dark; its masthead icon arrives with the flip
    # (TL_23 draws i-scouting), so the two masthead tests bind once the flag is on.
    "scouting": B.build_scouting_page,
}


def _dark_without_icon(key: str) -> None:
    if key == "scouting" and not B.SCOUTING_PAGE_LIVE:
        pytest.skip("/scouting/ is dark (SCOUTING_PAGE_LIVE False); TL_23 adds its icon")


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
    _dark_without_icon(key)
    out = MASTHEADS[key]()
    icons32 = [s for w, s in _icons(out) if w == 32]
    assert icons32 == [_sym(key)], icons32
    # The plain h1, or PB-06's grid masthead under the committed PIXEL_BRAND.
    h1 = re.search(r'<h1(?: class="mh-px")?>(.*?)</h1>', out, re.S).group(1)
    assert h1.startswith('<svg class="ico" width="32"'), h1[:80]
    if key in B.MODULE_STAGE:
        assert B._stage_chip(key) in h1, "the stage chip is untouched"


# PB-06 / BR-06 (owner ask 2): under build_site.PIXEL_BRAND the masthead title
# sits on the 12 px grid over a 1 u rule in the ramp bands. Off, nothing moves.
_MH_RE = re.compile(r'<h1 class="mh-px">(<svg class="ico" width="32"[^>]*>.*?</svg>)'
                    r'<span class="mh-title">([^<]*)</span>(.*?)</h1>', re.S)


def _unwrap_masthead(out: str) -> str:
    """The flag-on page with the PB-06 wrapper taken off again."""
    return _MH_RE.sub(lambda m: f"<h1>{m.group(1)}{m.group(2)}{m.group(3)}</h1>", out, count=1)


@pytest.mark.parametrize("key", sorted(MASTHEADS))
def test_masthead_is_one_icon_one_grid_title_one_rule_under_the_flag(key, monkeypatch):
    _dark_without_icon(key)
    monkeypatch.setattr(B, "PIXEL_BRAND", False)
    off = MASTHEADS[key]()
    assert 'class="mh-title"' not in off and 'class="mh-px"' not in off
    monkeypatch.setattr(B, "PIXEL_BRAND", True)
    on = MASTHEADS[key]()
    assert len(_MH_RE.findall(on)) == 1, "one masthead h1"
    assert on.count('class="mh-title"') == 1, "one rule per page (it draws under .mh-title)"
    assert [s for w, s in _icons(on) if w == 32] == [_sym(key)], "one masthead icon"
    icon, words, rest = _MH_RE.search(on).groups()
    assert words.strip() == words and words, f"live text, no padding: {words!r}"
    if key in B.MODULE_STAGE:
        assert rest == " " + B._stage_chip(key), "the stage chip follows, untouched"
    # Nothing else on the page moves: unwrapping the title gives the flag-off
    # page's main back (head and footer carry the flag's favicon, card and mark).
    main = lambda s: s.split("<main", 1)[1].split("</main>", 1)[0]  # noqa: E731
    assert main(_unwrap_masthead(on)) == main(off)


@pytest.mark.parametrize("active", ["awards", "hof"])
def test_awards_hof_head_is_one_masthead_site(active, monkeypatch):
    """_hof_module_head serves /awards/ and /hof/; with AWARDS_LIVE on its title
    reads 'Awards / HoF' and the strip sits under it, with the grid title."""
    import awards_core
    monkeypatch.setattr(awards_core, "AWARDS_LIVE", True)
    monkeypatch.setattr(B, "PIXEL_BRAND", True)
    head = B.pixel_masthead(B._hof_module_head(active, live=True))
    m = _MH_RE.search(head)
    assert m and m.group(2) == html.escape(awards_core.MODULE_LABEL)
    assert head.count('class="mh-title"') == 1


def _css_rule(css: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def test_masthead_grid_rules_are_tokens_only():
    css = _src("assets/site.css")
    h1 = _css_rule(css, ".section-head h1.mh-px")
    assert "font-size: 24px" in h1 and "letter-spacing: 0" in h1 and "line-height: 36px" in h1
    rule = _css_rule(css, ".section-head h1.mh-px > .mh-title")
    assert "var(--iridescent-steps)" in rule and "100% 2px" in rule and "no-repeat" in rule
    for body in (h1, rule):
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", body), "colours through tokens only"
        assert "animation" not in body and "transition" not in body, "the rule does not move"


# The CollegeSavant bar (PB-06): the 12 px icon crop and a 12 px grid title.
CS_PAGES = ("collegesavant/index.html", "collegesavant/pitcher_index.html")


@pytest.mark.parametrize("rel", CS_PAGES)
def test_cs_bar_title_takes_the_12px_icon_under_the_flag(rel):
    page = _src(rel)
    if not B.PIXEL_BRAND:
        assert 'class="cs-bar-title cs-bar-title--px"' not in page, "flag off: the bar is untouched"
    synced = B.pixel_brand_hand_cs_bar(page)
    assert B.pixel_brand_hand_cs_bar(synced) == synced, "idempotent"
    bar = re.search(r'<span class="cs-bar-title cs-bar-title--px">(.*?)</span></span>', synced, re.S).group(1)
    assert _icons(bar) == [(12, "collegesavant")] and 'viewBox="2 2 12 12"' in bar
    assert re.sub(r"<svg\b.*?</svg>", "", bar) == "CollegeSavant "
    if B.PIXEL_BRAND:
        # PB-10 flipped the flag: restamp has already synced the committed page.
        assert synced == page, "flag on: the committed bar is the synced bar"
        return
    # one hunk: the title line, nothing else on the page
    a, b = page.splitlines(), synced.splitlines()
    assert len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1


def test_cs_bar_grid_rules():
    rule = _css_rule(_src("collegesavant/styles.css"), ".cs-bar-title--px")
    assert "font-size: 12px" in rule and "letter-spacing: 0" in rule
    src = inspect.getsource(B.restamp_hand_authored_pages)
    assert src.index("pixel_brand_hand_cs_bar(stamped)") > src.index("if PIXEL_BRAND:")


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
    # The glossary module reads "Library" and draws i-library (owner ask 2026-10-02).
    assert _icons(gl) == [(12, _sym("glossary"))] == [(12, "library")]
    assert "section-tab-glyph" not in text


def test_prospx_theme_toggle_swaps_glyphs_not_text():
    text = _src("prospx/index.html")
    assert 'icon.textContent = theme === "dark"' not in text
    assert '.theme-icon [data-theme-glyph]' in text
    assert 'data-theme-glyph="light"' in text and 'data-theme-glyph="dark" hidden' in text


# ------------------------------------------------ the wire pictograms (PX-17)

_KNOWN_WIRE = tuple(B._WIRE_TYPES)


@pytest.mark.parametrize("typ", _KNOWN_WIRE)
def test_wire_rows_draw_the_event_pictogram(typ):
    """The sidebar feed, the /news/ row and the WIRE ticker draw the type's 12 px
    icon at the row lead (HOME_2: the family colour reads it from data-fam)
    instead of a text glyph."""
    feed = B._feed_item_html(typ, "GLYPH", "t", "k", None, "Name", "val")
    news = B._news_item_html(typ, "GLYPH", "t", "k", None, "Name", "val", "", {})
    tick = B._ticker_html([("2026-10-01", typ, "GLYPH", "text", "k", None, "Name", "val")])
    want = (12, _sym(B._WIRE_ICON[typ]))
    fam = B._WIRE_TYPES[typ]["fam"]
    for html in (feed, news):
        assert f'data-fam="{fam}" data-type="{typ}"><span class="wire-ico"><svg class="ico"' in html
        assert _icons(html) == [want]
        assert "GLYPH" not in html
    assert f'data-fam="{fam}" data-type="{typ}"><span class="wire-ico"><svg class="ico"' in tick
    assert _icons(tick) == [want, want] and "GLYPH" not in tick  # the track loops twice


def test_an_unknown_wire_type_keeps_its_text_glyph():
    html = B._feed_item_html("other", "◆", "t", "k", None, "Name", "val")
    assert _icons(html) == [] and "◆val" in html and "data-fam" not in html


def test_the_untyped_ticker_glyph_keeps_the_panel_ink_and_no_family_is_gold():
    """An item outside the registry keeps the panel's own ink; the trade family
    takes its own colour (the 2026-10-02 ask, SP-Q1, superseding PX-Q3), and
    gold on the dark panel still means elite FV only."""
    css = _src("assets/site.css")
    m = re.search(re.escape(".home-ticker .ticker-track .glyph") + r"\s*\{([^}]*)\}", css)
    assert m and "color: inherit" in m.group(1)
    fam_rules = re.findall(r"\[data-fam=\"\w+\"\][^{]*\{([^}]*)\}", css)
    assert fam_rules and not any("gold" in r for r in fam_rules)

# PX_SYSTEM_SWEEP (docs/pixel/PX_SWEEP_2026-10.md): the MLB news family
# pictograms of the site-pass plan 3.3 (HOME_7 swaps them into _WIRE_TYPES)
# and the controls that drew a unicode glyph or emoji before the sweep.
SWEEP_WIRE_KEYS = ("ev-mlb", "ev-callup", "ev-dfa", "ev-claim", "ev-release", "ev-retire",
                   "ev-suspend", "ev-award", "ev-option", "ev-qo", "ev-il-off")
SWEEP_UI_KEYS = ("gfx", "export", "link", "account", "close", "reset", "menu", "watch-off",
                 "compare", "hourglass", "lock", "warn", "web", "mail")


@pytest.mark.parametrize("key", SWEEP_WIRE_KEYS + SWEEP_UI_KEYS)
def test_every_sweep_key_is_drawn_and_served(key):
    sprite = _src("assets/eephus-icons.svg")
    assert key in B.ICON_KEYS, key
    assert f'<symbol id="i-{key}"' in sprite, key
    for size in (12, 16, 24, 32):
        assert _icons(B._ico(key, size)) == [(size, key)]


def test_the_draft_and_intl_aliases_resolve_to_their_tab_drawings():
    assert B.ICON_FOR["ev-draft"] == "px-draft" and B.ICON_FOR["ev-intl"] == "px-intl"
