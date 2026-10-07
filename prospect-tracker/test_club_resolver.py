# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The one club resolver (owner ask 9, 2026-09-30; task Q9_05, census M13-07).

Every link to a club's Franchises page or PROSPX farm page is built by ONE
resolver: EEPHUS_HUB.club / clubHref / clubLinkHTML in assets/eephus-hub.js on
the client, and build_site._club_code / _club_href / _club_link on the server,
which reads the same table out of eephus-hub.js. Measured before this task on
the served path: /franchise/#team=CWS, #team=KC and #team=OAK all rendered the
Arizona Diamondbacks page, /prospx/#farm-org=CWS and #farm-org=OAK rendered
"Unknown organization", and club("constructor") returned Object off the
prototype.

These tests hold:
  - every one of the 30 codes, the nine aliases, the 30 full names, the six
    former names and the 30 MLBAM ids resolve to the canonical code and href,
    in the hub evaluated in a headless page AND in the Python mirror;
  - prose, MiLB clubs, leagues, levels and prototype keys resolve to "";
  - the two sides read one table and print the same markup;
  - the alias routes land on their own club on the served pages.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import build_site as B
from conftest import serve_site

ROOT = Path(__file__).parent
HUB = (ROOT / "assets" / "eephus-hub.js").read_text(encoding="utf-8")

CODES = ["ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL",
         "DET", "HOU", "KCR", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY",
         "PHI", "PIT", "SDP", "SEA", "SFG", "STL", "TBR", "TEX", "TOR", "WSN"]
ALIASES = {"AZ": "ARI", "CWS": "CHW", "KC": "KCR", "SD": "SDP", "SF": "SFG",
           "TB": "TBR", "WSH": "WSN", "OAK": "ATH", "FLA": "MIA"}
NAMES = {
    "Arizona Diamondbacks": "ARI", "Athletics": "ATH", "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS", "Chicago Cubs": "CHC",
    "Chicago White Sox": "CHW", "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL", "Detroit Tigers": "DET", "Houston Astros": "HOU",
    "Kansas City Royals": "KCR", "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN",
    "New York Mets": "NYM", "New York Yankees": "NYY", "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT", "San Diego Padres": "SDP", "Seattle Mariners": "SEA",
    "San Francisco Giants": "SFG", "St. Louis Cardinals": "STL", "Tampa Bay Rays": "TBR",
    "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR", "Washington Nationals": "WSN",
}
FORMER = {"Oakland Athletics": "ATH", "Florida Marlins": "MIA", "Cleveland Indians": "CLE",
          "Tampa Bay Devil Rays": "TBR", "Anaheim Angels": "LAA",
          "Los Angeles Angels of Anaheim": "LAA"}
IDS = {109: "ARI", 133: "ATH", 144: "ATL", 110: "BAL", 111: "BOS", 112: "CHC", 145: "CHW",
       113: "CIN", 114: "CLE", 115: "COL", 116: "DET", 117: "HOU", 118: "KCR", 108: "LAA",
       119: "LAD", 146: "MIA", 158: "MIL", 142: "MIN", 121: "NYM", 147: "NYY", 143: "PHI",
       134: "PIT", 135: "SDP", 136: "SEA", 137: "SFG", 138: "STL", 139: "TBR", 140: "TEX",
       141: "TOR", 120: "WSN"}
# Not one of the 30: prose, a state, a college, MiLB and complex-league clubs,
# a league, a level, free agency, prototype keys, empty input.
NEGATIVES = ["Texas", "Arizona State", "Worcester Red Sox", "ACL D-backs", "DSL NYY Bombers",
             "Arizona Complex League", "constructor", "", None, "FA", "AAA",
             "__proto__", "toString", "hasOwnProperty", "White Sox", "Sox", "NY", "0", 999]


def _positives():
    out = {}
    for c in CODES:
        out[c] = c
        out[c.lower()] = c
    out.update(ALIASES)
    out.update(NAMES)
    out.update({n.upper(): c for n, c in NAMES.items()})
    out.update(FORMER)
    return out


def _cases():
    pos = [(k, v) for k, v in _positives().items()]
    pos += [(i, c) for i, c in IDS.items()] + [(str(i), c) for i, c in IDS.items()]
    return pos


# ---- the headless page -------------------------------------------------------
@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def page(browser):
    pg = browser.new_page()
    pg.set_content("<!doctype html><html><body></body></html>")
    pg.add_script_tag(content=HUB)
    assert pg.evaluate("typeof window.EEPHUS_HUB.clubHref") == "function"
    yield pg
    pg.close()


def _js(page, fn, args):
    return page.evaluate("([fn, args]) => args.map(a => { const H = window.EEPHUS_HUB;"
                         " const r = fn === 'code' ? (H.club(a[0]) || {}).code || '' : H[fn].apply(null, a);"
                         " return r == null ? '' : r; })", [fn, args])


# ---- Python mirror -----------------------------------------------------------
def test_python_resolves_every_code_alias_name_former_name_and_id():
    for x, code in _cases():
        assert B._club_code(x) == code, x
        assert B._club_href(x) == "/franchise/#team=" + code, x
        assert B._club_href(x, "farm") == "/prospx/#farm-org=" + code, x
    assert len({c for _, c in _cases()}) == 30


def test_python_never_guesses():
    for x in NEGATIVES:
        assert B._club_code(x) is None, x
        assert B._club_href(x) == "" and B._club_href(x, "farm") == "", x
    assert B._club_code(True) is None and B._club_code(145.5) is None


def test_python_ids_go_through_canonical_org_from_id():
    trades = pytest.importorskip("trades")
    for i, code in IDS.items():
        assert trades.canonical_org_from_id(i) == code == B._club_code(i)


def test_one_table_and_the_logo_slugs_agree():
    t = B._club_table()
    assert [r["code"] for r in t["rows"]] == CODES
    assert {a: r["code"] for r in t["rows"] for a in r["aliases"]} == ALIASES
    assert {r["name"]: r["code"] for r in t["rows"]} == NAMES
    assert {r["id"]: r["code"] for r in t["rows"]} == IDS
    assert {r["code"]: r["slug"] for r in t["rows"]} == B.ESPN_SLUGS


def test_the_server_never_reaches_for_the_token_matchers():
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    body = src[src.index("def _club_code("):src.index("def _club_href(")]
    assert "canonical_org_from_id" in body
    assert "canonical_org(" not in body and "_org_from_team_name" not in body


# ---- the hub in a headless page ------------------------------------------------
def test_hub_resolves_every_code_alias_name_former_name_and_id(page):
    cases = _cases()
    args = [[x] for x, _ in cases]
    assert _js(page, "code", args) == [c for _, c in cases]
    assert _js(page, "clubHref", args) == ["/franchise/#team=" + c for _, c in cases]
    assert _js(page, "clubHref", [[x, "farm"] for x, _ in cases]) == ["/prospx/#farm-org=" + c for _, c in cases]


def test_hub_never_guesses_and_is_off_the_prototype(page):
    args = [[x] for x in NEGATIVES]
    assert _js(page, "code", args) == [""] * len(NEGATIVES)
    assert _js(page, "clubHref", args) == [""] * len(NEGATIVES)
    assert page.evaluate("window.EEPHUS_HUB.club('constructor')") is None
    assert page.evaluate("window.EEPHUS_HUB.club(NaN)") is None


def test_js_and_python_tables_are_identical(page):
    js = page.evaluate("window.EEPHUS_HUB.clubs().map(c => ({code: c.code, slug: c.slug, name: c.name,"
                       " id: c.id, aliases: c.aliases, logo: c.logo}))")
    assert js == B._club_table()["rows"]
    for n, code in FORMER.items():
        assert page.evaluate("n => window.EEPHUS_HUB.club(n).code", n) == code == B._club_code(n)


_LINK_OPTS = [
    {}, {"ctx": "farm"}, {"text": "name"}, {"text": "Chi White Sox"}, {"logo": True},
    {"logo": True, "text": ""}, {"stop": True, "ctx": "farm", "logo": True, "text": "name"},
    {"text": 'A "quoted" <b>&'},
]


def test_js_and_python_print_the_same_link_markup(page):
    inputs = ["CWS", "OAK", "Kansas City Royals", 145, "Texas", "Worcester Red Sox", "", None, "constructor"]
    py_key = {"ctx": "ctx", "text": "text", "logo": "logo", "stop": "stop"}
    for x in inputs:
        for o in _LINK_OPTS:
            js = page.evaluate("([x, o]) => window.EEPHUS_HUB.clubLinkHTML(x, o)", [x, o])
            kw = {py_key[k]: v for k, v in o.items()}
            assert js == B._club_link(x, **kw), (x, o)


def test_link_shape_and_unresolved_marking(page):
    a = page.evaluate("window.EEPHUS_HUB.clubLinkHTML('CWS', {logo: true, stop: true})")
    assert a.startswith('<a class="club-link" href="/franchise/#team=CHW" data-club="CHW" '
                        'title="Chicago White Sox: franchise overview" onclick="event.stopPropagation()">')
    assert 'alt=""' in a and a.endswith("<span>CHW</span></a>")
    only = page.evaluate("window.EEPHUS_HUB.clubLinkHTML('OAK', {logo: true, text: '', ctx: 'farm'})")
    assert 'class="club-link club-link--logo-only" href="/prospx/#farm-org=ATH"' in only and 'alt="Athletics"' in only
    assert "<span>" not in only.split("onerror")[0]
    u = page.evaluate("window.EEPHUS_HUB.clubLinkHTML('Worcester Red Sox', {text: 'name'})")
    assert u == '<span data-club-nolink="unresolved">Worcester Red Sox</span>'
    assert page.evaluate("window.EEPHUS_HUB.clubLinkHTML(null)") == ""


def test_club_link_style_is_tokened_with_a_focus_ring():
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    block = css[css.index(".club-link {"):css.index(".club-link--logo-only .club-link-logo")]
    assert ".club-link:focus-visible { outline: 2px solid var(--accent-cyan);" in block
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", block)
    assert "min-width: 24px; min-height: 24px;" in block


# ---- the alias routes on the served pages ------------------------------------------
def test_franchise_alias_route_renders_its_own_club(browser):
    if not (ROOT / "data" / "franchise_board.json").exists():
        pytest.skip("data/franchise_board.json not built")
    with serve_site() as base:
        for hash_, code, name in (("#team=CWS", "CHW", "Chicago White Sox"), ("#team=KC", "KCR", "Kansas City Royals"),
                                  ("#team=OAK", "ATH", "Athletics"), ("#view=club&team=CWS", "CHW", "Chicago White Sox")):
            pg = browser.new_page()
            pg.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.abort())
            pg.goto(base + "franchise/" + hash_)
            pg.wait_for_selector(".fr-mast-name", timeout=30000)
            assert pg.inner_text(".fr-mast-name").strip() == name, hash_
            assert "team=" + code in pg.evaluate("location.hash"), hash_
            pg.close()


def test_prospx_alias_route_renders_its_own_farm(browser):
    ts = ROOT / "data" / "timeseries.json"
    if not ts.exists():
        pytest.skip("data/timeseries.json not built")
    with serve_site() as base:
        for alias, name in (("OAK", "Athletics"), ("CWS", "Chicago White Sox")):
            pg = browser.new_page()
            pg.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.abort())
            pg.goto(base + "prospx/#farm-org=" + alias)
            pg.wait_for_selector("#farm-detail-body .player-display-name", timeout=60000)
            assert pg.inner_text("#farm-detail-body .player-display-name").strip() == name, alias
            assert "Unknown organization" not in pg.inner_text("#farm-detail-body")
            pg.close()
