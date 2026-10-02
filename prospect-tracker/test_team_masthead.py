# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Masthead, the Franchises rename and the attribution move (owner
decisions TEAM-1 to TEAM-7, 2026-10-02).

Pins: data/team.json is the one roster (structure, unique keys, the explicit
order of the Developers group, exactly one owner); every badge key resolves to
a sprite symbol and every rendered card's badges equal its data entry; exactly
one card wears the owner's foil and the founder plate; the Writers and
Analysts group shows its honest empty state and invents no names; no served
page carries a 'Created by' byline; /franchises/ is a canonical noindex
redirect that ships; the nav says Franchises and Masthead. The browser test
checks the same on the served page in headless Chromium (optional: it skips
when Playwright is unavailable)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent
TEAM = json.loads((ROOT / "data" / "team.json").read_text(encoding="utf-8"))
DEV_ORDER = ["noah-j-dengler", "will-cahoon", "michael-behrens",
             "joseph-gillis", "anirudh-iyer", "charlie-mortellite"]
WRITERS_EMPTY = ("Scouting reports and articles are by the eephus.io writers; "
                 "bylines appear with each piece.")


@pytest.fixture(scope="module")
def team_html() -> str:
    return B.build_team()


def _sprite_symbols() -> set[str]:
    svg = (ROOT / "assets" / "eephus-icons.svg").read_text(encoding="utf-8")
    return set(re.findall(r'<symbol id="i-([\w-]+)"', svg))


# ------------------------------------------------------------ data/team.json

def test_team_json_structure():
    assert TEAM["set"] == "eephus.io Masthead 2026"
    groups = {g["key"]: g for g in TEAM["groups"]}
    assert [g["label"] for g in sorted(TEAM["groups"], key=lambda g: g["order"])] == \
        ["Developers", "Writers and Analysts"]
    assert groups["writers"]["empty"] == WRITERS_EMPTY
    keys = [m["key"] for m in TEAM["members"]]
    assert len(keys) == len(set(keys))
    for m in TEAM["members"]:
        for f in ("key", "name", "group", "order", "role", "photo", "watermark", "front", "badges", "back"):
            assert f in m, (m.get("key"), f)
        assert m["key"] == B._member_slug(m["name"]), m["key"]
        assert m["group"] in groups
        assert isinstance(m["order"], int) and m["order"] >= 1
        assert isinstance(m["front"], dict) and isinstance(m["back"], list)
        assert all(isinstance(ln, str) and ln.strip() and "**" not in ln and "`" not in ln for ln in m["back"])
        assert m["badges"], m["key"]
        for b in m["badges"]:
            assert b["key"] in TEAM["badges"], (m["key"], b)
            assert b["credit"] in TEAM["credits"], (m["key"], b)
        assert len({b["key"] for b in m["badges"]}) == len(m["badges"]), m["key"]
        if m["photo"]:
            assert m["photo"].startswith("/assets/team/") and (ROOT / m["photo"].lstrip("/")).exists()
    for g in groups:
        orders = [m["order"] for m in TEAM["members"] if m["group"] == g]
        assert len(orders) == len(set(orders)), g


def test_exactly_one_owner_and_it_is_the_founder():
    owners = [m for m in TEAM["members"] if m.get("owner")]
    assert [m["key"] for m in owners] == ["noah-j-dengler"]
    assert owners[0]["role"] == "Owner and founder"
    assert all(m.get("owner") in (None, False) for m in TEAM["members"] if m is not owners[0])


def test_developers_are_ordered_by_role_weight():
    devs = sorted((m for m in TEAM["members"] if m["group"] == "developers"), key=lambda m: m["order"])
    assert [m["key"] for m in devs] == DEV_ORDER
    assert [m["order"] for m in devs] == list(range(1, len(devs) + 1))


def test_the_owner_photo_is_the_processed_square_jpeg():
    from PIL import Image
    for m in TEAM["members"]:
        if not m["photo"]:
            continue
        with Image.open(ROOT / m["photo"].lstrip("/")) as im:
            assert im.format == "JPEG" and im.mode == "RGB" and im.size == (600, 600), m["key"]


def test_every_badge_key_resolves_to_a_sprite_symbol():
    syms = _sprite_symbols()
    table = json.loads((ROOT / "assets" / "eephus-icons.json").read_text(encoding="utf-8"))
    for key, b in TEAM["badges"].items():
        assert b["label"].strip(), key
        assert b["icon"] in syms and b["icon"] in table, (key, b["icon"])
    for g in TEAM["groups"]:
        assert g["icon"] in syms, g["key"]
    assert {"b-founder", "b-flip"} <= syms


# ------------------------------------------------------------ the page

def test_page_is_the_masthead(team_html):
    assert "<title>Masthead - eephus.io</title>" in team_html
    assert re.search(r"<h1>.*Masthead</h1>", team_html)
    assert "who builds, runs and writes the site" in team_html
    assert "Created by" not in team_html and "Developers - eephus.io" not in team_html


def test_every_card_renders_its_data_badges_in_order(team_html):
    cards = dict(re.findall(r'<article class="tc-card[^"]*" id="member-([\w-]+)"[^>]*data-badges="([^"]*)"', team_html))
    assert set(cards) == {m["key"] for m in TEAM["members"]}
    for m in TEAM["members"]:
        assert cards[m["key"]].split(",") == [b["key"] for b in m["badges"]], m["key"]
        art = team_html[team_html.index(f'id="member-{m["key"]}"'):]
        art = art[:art.index("</article>")]
        back = art[art.index('class="tc-face tc-back"'):]
        assert re.findall(r'<tr data-badge="([\w-]+)"', back) == [b["key"] for b in m["badges"]], m["key"]
        # each badge carries a text label for screen readers
        front = art[:art.index('class="tc-face tc-back"')]
        for key in re.findall(r'<li class="tc-badge" data-badge="([\w-]+)"', front):
            assert TEAM["badges"][key]["label"] in front


def test_developer_cards_render_in_order(team_html):
    dev = team_html[team_html.index('data-group="developers"'):team_html.index('data-group="writers"')]
    assert re.findall(r'id="member-([\w-]+)"', dev) == DEV_ORDER
    assert re.findall(r'data-no="(\d+)"', dev) == [f"{i:02d}" for i in range(1, 7)]


def test_exactly_one_card_carries_the_owner_foil_and_plate(team_html):
    owners = re.findall(r'<article class="tc-card is-owner" id="member-([\w-]+)"', team_html)
    assert owners == ["noah-j-dengler"]
    assert team_html.count("is-owner") == 1
    assert team_html.count('class="tc-plate"') == 1 and "Owner and founder</span></span>" in team_html
    css = (ROOT / "assets" / "team.css").read_text(encoding="utf-8")
    assert ".tc-card.is-owner .tc-inner" in css and "@keyframes tc-holo" in css
    assert "prefers-reduced-motion" in css
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), "team.css draws only through tokens"


def test_writers_group_shows_its_empty_state_and_no_names(team_html):
    w = team_html[team_html.index('data-group="writers"'):]
    w = w[:w.index("</section>")]
    assert 'class="px-state' in w and WRITERS_EMPTY.replace("'", "&#x27;") in w
    assert "To be named" in w and 'id="member-' not in w


def test_no_served_page_carries_a_created_by_byline():
    pages = [p for p in ROOT.rglob("*.html")
             if not any(part in {"docs", "node_modules", "vendor", ".cache", "data"} or part.startswith(("_", "."))
                        for part in p.relative_to(ROOT).parts)]
    assert len(pages) > 20
    bad = [p.relative_to(ROOT).as_posix() for p in pages
           if re.search(r"Created by|build-banner", p.read_text(encoding="utf-8", errors="replace"))]
    assert not bad, bad
    assert not hasattr(B, "CREATED_BY_BANNER")
    for rel in ("assets/site.css", "prospx/index.html"):
        assert ".build-banner" not in (ROOT / rel).read_text(encoding="utf-8"), rel


# ------------------------------------------------------------ rename + redirect

def test_nav_says_franchises_and_masthead():
    leaves = {h: label for _k, label, h in B.nav_leaves()}
    assert leaves["/franchise/"] == "Franchises"
    assert leaves["/team/"] == "Masthead"


def test_franchises_redirect_is_canonical_noindex_and_ships():
    out = B.build_franchises_redirect()
    assert '<meta http-equiv="refresh" content="0; url=/franchise/">' in out
    assert '<meta name="robots" content="noindex">' in out
    assert f'<link rel="canonical" href="{B.SITE_ORIGIN}/franchise/">' in out
    assert '<a href="/franchise/">/franchise/</a>' in out
    assert (ROOT / "franchises" / "index.html").read_text(encoding="utf-8") == out
    ships = (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").split()
    assert "franchises" in ships and "franchise" in ships
    assert "/franchises/" not in B.build_sitemap([])


# ------------------------------------------------------------ in the browser

@pytest.fixture(scope="module")
def rendered():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from conftest import serve_site

    out: dict = {}
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        for theme, motion in (("light", "no-preference"), ("dark", "reduce")):
            ctx = browser.new_context(viewport={"width": 390, "height": 900}, reduced_motion=motion)
            ctx.add_init_script(
                "try{localStorage.setItem('prospect-tracker.gate-unlocked','1');"
                f"localStorage.setItem('prospect-tracker.theme','{theme}')}}catch(e){{}}")
            page = ctx.new_page()
            page.goto(base + "team/", wait_until="load", timeout=30_000)
            res = page.evaluate("""() => {
              const cs = (el) => getComputedStyle(el);
              const owner = [...document.querySelectorAll('.tc-card')].filter(
                (c) => cs(c.querySelector('.tc-inner')).borderTopWidth === '4px');
              const w = document.querySelector('.tc-group[data-group=writers]');
              const o = document.querySelector('.tc-card.is-owner .tc-inner');
              return {
                foil: owner.map((c) => c.id),
                anim: cs(o).animationName,
                writers_state: !!(w && w.querySelector('.px-state')),
                writers_text: w ? w.textContent : '',
                width: document.querySelector('.tc-card').getBoundingClientRect().width,
                hscroll: document.documentElement.scrollWidth > innerWidth,
              };
            }""")
            page.focus("#member-will-cahoon .tc-front .tc-flipbtn")
            page.keyboard.press("Enter")
            page.wait_for_timeout(400)
            res["flipped"] = page.evaluate(
                "document.getElementById('member-will-cahoon').classList.contains('is-flipped')")
            res["back_visible"] = page.evaluate(
                "getComputedStyle(document.querySelector('#member-will-cahoon .tc-back')).visibility")
            out[theme] = res
            ctx.close()
        browser.close()
    return out


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_rendered_masthead(rendered, theme):
    r = rendered[theme]
    assert r["foil"] == ["member-noah-j-dengler"], r["foil"]
    assert r["anim"] == ("tc-holo" if theme == "dark" else "none"), r["anim"]
    assert r["writers_state"] and "bylines appear with each piece" in r["writers_text"]
    assert r["width"] == 300 and not r["hscroll"]
    assert r["flipped"] and r["back_visible"] == "visible"
