# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""CollegeSavant display and copy pass (DISPLAY_collegesavant, 2026-10-08).

Pins the surface-quality findings QREA12 and QREA13 (2026-10-02) and the copy
trim:
  - QREA12: a translation leg the backtest flags is muted by a data-muted
    attribute read in --text-secondary, never by opacity (opacity .55 and .5
    put 368 hitter and 77 pitcher cells at 3.81:1 and 10 at 3.27:1 on the
    light paper), and the positive CS+ pill reads in --text-green (accent
    green measured 4.32:1 on the chip). Both inks clear 4.5:1 on every paper
    the boards use, in both themes.
  - QREA13: every view renders exactly one h1, the active view tab carries
    aria-current="page", the board CS+ pills name a visible note through
    aria-describedby instead of a title, and a board player link is a 44 px
    target under 720 px.
  - Copy: the boards lead (the projections board sits above its accuracy
    table and the folded method), the hub cards and the UI narration are
    gone, and the unsupported "pro profile" / "travel to pro ball" phrasing
    is deleted (the registry calls CS+ descriptive).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
CS = ROOT / "collegesavant"
APP_JS = (CS / "app.js").read_text(encoding="utf-8")
PIT_JS = (CS / "pitcher_app.js").read_text(encoding="utf-8")
CS_CSS = (CS / "styles.css").read_text(encoding="utf-8")
SITE_CSS = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")

SOURCES = [("app.js", APP_JS), ("pitcher_app.js", PIT_JS)]


# --------------------------------------------------------------------------
# QREA12: muted cells and the positive pill read at AA
# --------------------------------------------------------------------------

def _tokens(name: str) -> list[str]:
    return re.findall(r"--%s:\s*([^;]+);" % re.escape(name), SITE_CSS)


def _hex(name: str, theme: int) -> str:
    v = _tokens(name)[theme].strip()
    m = re.match(r"var\(--([\w-]+)\)", v)
    return _hex(m.group(1), theme) if m else v


def _lum(h: str) -> float:
    h = h.lstrip("#")
    def ch(x: int) -> float:
        c = x / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _ratio(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@pytest.mark.parametrize("theme", [0, 1], ids=["light", "dark"])
@pytest.mark.parametrize("ink", ["text-secondary", "text-green"])
def test_muted_and_positive_inks_clear_aa_on_every_board_paper(ink, theme):
    for paper in ("bg-primary", "bg-secondary", "bg-tertiary"):
        r = _ratio(_hex(ink, theme), _hex(paper, theme))
        assert r >= 4.5, (ink, paper, theme, round(r, 2))


def test_muted_rule_and_pill_ink():
    assert re.search(r"\[data-muted\] \{ color: var\(--text-secondary", CS_CSS)
    assert re.search(r"\.tt-table td\[data-muted\] \{ color: var\(--text-secondary", CS_CSS)
    pill = re.search(r"\.cs-plus-pill\.is-pos \{([^}]*)\}", CS_CSS).group(1)
    assert "color: var(--text-green" in pill and "border-color: var(--green)" in pill
    assert ".tt-pos { color: var(--text-green" in CS_CSS


@pytest.mark.parametrize("name,src", SOURCES, ids=["app", "pitcher_app"])
def test_no_inline_opacity_in_the_apps(name, src):
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("//"))
    assert "opacity" not in code, name


# --------------------------------------------------------------------------
# QREA13 and the copy trim, on the rendered views
# --------------------------------------------------------------------------

br = pytest.importorskip("test_collegesavant_board_flags")

HIT_ROUTES = ["#/", "#/leaders/cs_plus/2024", "#/teams", "#/prospects", "#/projections"]
PIT_ROUTES = ["#/", "#/leaders/stuff_plus/2024", "#/teams", "#/prospects", "#/projections"]


def _hit(route: str) -> str:
    return br._render("app.js", "HITTER_DATA:" + br.HIT, route)


def _pit(route: str) -> str:
    return br._render("pitcher_app.js", "PITCHER_DATA:" + br.PIT, route)


@pytest.mark.parametrize("route", HIT_ROUTES)
def test_every_hitter_view_has_one_h1(route):
    html = _hit(route)
    assert html.count("<h1") == 1, (route, html[:400])


@pytest.mark.parametrize("route", PIT_ROUTES)
def test_every_pitcher_view_has_one_h1(route):
    html = _pit(route)
    assert html.count("<h1") == 1, (route, html[:400])


@pytest.mark.parametrize("name,src", SOURCES, ids=["app", "pitcher_app"])
def test_active_tab_carries_aria_current(name, src):
    nav = src.split("function updateNav(hash)")[1].split("\n}\n")[0]
    assert 'link.setAttribute("aria-current", "page")' in nav
    assert 'link.removeAttribute("aria-current")' in nav


def test_board_pills_name_a_visible_note():
    assert 'plusPill(x.cs, "CS+", "cs-plus-note")' in PIT_JS
    assert '${csPlusNote("cs-plus-note")}' in PIT_JS
    html = _hit("#/projections")
    pills = re.findall(r'<span class="cs-plus-pill[^"]*"[^>]*>', html)
    assert pills, html[:600]
    for p in pills:
        assert 'aria-describedby="cs-plus-note"' in p and "title=" not in p, p
    assert html.count('id="cs-plus-note"') == 1
    assert "tracked-skill index: 100 = the 2024 pool average" in html


def test_board_player_links_are_44px_targets_on_a_phone():
    block = CS_CSS.split("@media (max-width: 720px) {\n  .tt-table a.proj-name")[1].split("}")[0]
    assert "min-height: 44px" in block


def test_app_body_has_a_side_gutter():
    assert re.search(r"\.app-shell \{ padding: 12px 16px 32px; \}", CS_CSS)


@pytest.mark.parametrize("render,acc", [(_hit, "Proj Single-A OPS"), (_pit, "Proj Single-A BB%")], ids=["hitters", "pitchers"])
def test_projection_board_leads_and_the_method_folds(render, acc):
    html = render("#/projections")
    board = html.index("Projected Single-A board")
    table = html.index("How accurate is this")
    how = html.index('<details class="cs-how"><summary>How this works</summary>')
    assert board < table < how
    assert acc in html[table:how]
    # The trust sentence (the backtest verdict) stays on the page, folded.
    assert "What to trust." in html[how:]
    assert "read them as context, not a forecast" in html[how:] or "read it as context, not a forecast" in html[how:]


def test_hitter_prospects_keep_the_trust_sentence_folded():
    html = _hit("#/prospects")
    how = html.index('<details class="cs-how"><summary>How accurate is this</summary>')
    assert "Box BB%" in html[how:] and "FV is the consensus board grade, rounded up." in html[:how]


@pytest.mark.parametrize("name,src", SOURCES, ids=["app", "pitcher_app"])
def test_copy_trim(name, src):
    src = "\n".join(l for l in src.splitlines() if not l.strip().startswith("//"))
    for gone in ("pro profile", "travel to pro ball", "Click any column", "click a column",
                 "hub-card", "HOME_SECTIONS"):
        assert gone not in src, (name, gone)
