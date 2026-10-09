# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Club links on the served pages (owner ask 9; the skeleton Q9_05 leaves for
the surface tasks that follow it, links_efv_display.md Part A, A.2 to A.4).

Two kinds of check, per route, at 1280 and 390 px:

  ALWAYS, on every route below: every a.club-link carries an href of the two
  shapes the one resolver builds (/franchise/#team=CODE or
  /prospx/#farm-org=CODE over the 30 canonical codes), a data-club equal to
  that code, and no interactive ancestor (a, button, [role=button], summary,
  label, select). Every [data-club-nolink] names an allowed reason.

  SWEPT routes only (a surface task adds its route to SWEPT when it lands):
  every MLB logo image and every [data-club] sits inside a.club-link[href] or
  carries data-club-nolink with an allowed reason, and one sampled link lands
  on a Franchises page naming that club.

THE SWEEP (Q9_09): every route SITE_MAP.md lists (read from the file, so a
new route joins on its own) and the generated pages are SWEPT routes, checked
at 1280 and 390 px in the light and the dark theme; the alias routes
/franchise/#team=CWS and /prospx/#farm-org=OAK land on their clubs.

Off-loopback requests are aborted, except the ESPN logo images, which are
answered with a local 1 px image so a logo stays in the page to be checked
(an aborted logo removes itself). The page must raise no console error.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

from conftest import serve_site

CODES = ("ARI|ATH|ATL|BAL|BOS|CHC|CHW|CIN|CLE|COL|DET|HOU|KCR|LAA|LAD|MIA|MIL|MIN|"
         "NYM|NYY|PHI|PIT|SDP|SEA|SFG|STL|TBR|TEX|TOR|WSN")
HREF_RE = re.compile(r"^(/franchise/#team=|(/prospx/)?#farm-org=)(" + CODES + r")$")
NOLINK_REASONS = {"row-anchor", "unresolved", "defunct", "self"}

# Every route a club link may appear on. The ALWAYS checks run on each.
ROUTES = [
    "franchise/#team=CHW",
    "management/",
    "projections/",
]
# Q9_06 (MLB modules, part A): MLB Stats player boards, the five team views
# and the four depth charts; Sports Betting; Club Ledger; Arbitration; the
# In-Game Management club view.
MLB_A = [
    "mlbstats/",
    "mlbstats/#section=hitters",
    "mlbstats/#section=starters",
    "mlbstats/#section=bullpen",
    "mlbstats/#section=leverage",
    "mlbstats/#section=hitters&hview=teams",
    "mlbstats/#section=starters&sview=teams",
    "mlbstats/#section=bullpen&view=teams",
    "mlbstats/#section=war&wview=teams",
    "mlbstats/#section=defense&dview=teams",
    "mlbstats/#section=hitters&hview=charts",
    "mlbstats/#section=starters&sview=charts",
    "mlbstats/#section=bullpen&view=depth",
    "mlbstats/#section=defense&dview=charts",
    "betting/#section=teams",
    "betting/#section=futures",
    "betting/#section=props",
    "ledger/",
    "ledger/#section=club&team=CHW",
    "arbitration/",
    "arbitration/#teams",
    "management/#section=clubs&team=CHW",
]
ROUTES += MLB_A
# Q9_07 (MLB modules, part B): Trade Machine (board rows, the farm page for a
# prospect row), Projections (board, prospects, Team Outlook, compare, player
# page), Free Agency (board and rails, Team Fits, archive, player card),
# Fantasy (Dynasty board, Call-up Watch, Keeper, Fantasy Rank, Redraft
# rest-of-season and closers; the empty off-season DFS slate has no club) and
# the Alchemy Lab. The Hall of Fame Franchises section opens by a click, so it
# has its own test below.
MLB_B = [
    "trademachine/",
    "projections/",
    "projections/#src=prospect",
    "projections/#view=teams",
    "projections/#cmp=shohei_ohtani,juan_soto",
    "projections/#player=shohei_ohtani",
    "fa/",
    "fa/#view=fits&team=LAD",
    "fa/#view=archive",
    "fa/#player=tarik_skubal",
    "fantasy/#section=dynasty",
    "fantasy/#section=callups",
    "fantasy/#section=keeper",
    "fantasy/#section=fantasy_rank",
    "fantasy/#section=ros_hitter",
    "fantasy/#section=closers",
    "pal/",
    "pal/#rp2sp",
    "pal/#history",
    "pal/#pitchadd",
    "pal/#platoon",
    "pal/#prospects",
    "pal/#posfit=board",
]
ROUTES += [r for r in MLB_B if r not in ROUTES]
# Q9_08 (PROSPX, A17 to A24): the board-family rows (board, Spotlights,
# Transactions, Injured, Leaderboards, Debuted) and their context rails, the
# Farm Systems list (table and cards), the farm page header and rail, the
# player card (header, origin line, rail title, career table), the draft
# (cards, results, signing trends, order, overperformers), the IFA board, an
# overseas league page (a signed pro's MLB club opens Franchises) and the Time
# Machine (logos inside player row anchors are marked row-anchor). Every other
# PROSPX mention opens the club's farm page.
PROSPX = [
    "prospx/",
    "prospx/#tab=spotlights",
    "prospx/#tab=traded",
    "prospx/#tab=injured",
    "prospx/#tab=leaderboards",
    "prospx/#tab=debuts",
    "prospx/#tab=farm",
    "prospx/#tab=farm&farmview=cards",
    "prospx/#farm-org=CHW",
    "prospx/#player=jesus_made",
    "prospx/#player=jesus_made&ptab=stats",
    "prospx/#tab=draft&dyear=2026",
    "prospx/#tab=draft&dyear=2026&dview=results",
    "prospx/#tab=draft&dyear=2026&dview=signing-trends",
    "prospx/#tab=draft&dyear=2026&dview=order",
    "prospx/#tab=draft&dyear=2026&dview=overperformers",
    "prospx/#tab=ifa",
    "prospx/#league=NPB",
    "prospx/#tab=timemachine",
]
ROUTES += PROSPX
# Q9_09 (A14 to A16 and the sweep): the generated home page, the news wire and
# /history/ (whole-row player links keep one target and mark their logos
# row-anchor, owner answer Q-L1; a logo outside a row link links its club),
# the Scores / Standings day, bracket and game views, and every route
# SITE_MAP.md lists.
ROOT = Path(__file__).parent
GENERATED = ["", "news/", "history/", "scores/", "scores/#bracket=2026"]


def _site_map_routes() -> list[str]:
    """Every page route of SITE_MAP.md's surface tables, as a path under the
    site root (robots.txt and sitemap.xml are no pages; /articles/<slug>/ is
    the first article on disk)."""
    out = []
    text = (ROOT / "SITE_MAP.md").read_text(encoding="utf-8")
    for path in re.findall(r"^\| `(/[^`]*)` \|", text, re.M):
        if path.endswith((".txt", ".xml")):
            continue
        if "<slug>" in path:
            slugs = sorted(p.parent.name for p in (ROOT / "articles").glob("*/index.html"))
            if not slugs:
                continue
            path = path.replace("<slug>", slugs[0])
        if path.lstrip("/") not in out:
            out.append(path.lstrip("/"))
    return out


SITE_MAP_ROUTES = _site_map_routes()
ROUTES += [r for r in dict.fromkeys(GENERATED + SITE_MAP_ROUTES) if r not in ROUTES]
# Routes whose club mentions have been converted (the SWEPT checks run on each).
# Each surface task appends its own routes.
SWEPT: list[str] = list(dict.fromkeys(["franchise/#team=CHW"] + MLB_A + MLB_B + PROSPX
                                      + GENERATED + SITE_MAP_ROUTES))
# The sweep routes run in both themes; the rest in the default (light) theme.
THEMED = set(GENERATED + SITE_MAP_ROUTES)
CASES = [pytest.param(r, w, t, id=f"{r or 'home'}-{w}-{t}")
         for r in ROUTES for w in (1280, 390) for t in (("light", "dark") if r in THEMED else ("light",))]
# A 1 px PNG served for every ESPN logo request.
_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

_READ = """() => {
  const bad = 'a, button, [role=button], summary, label, select';
  const links = [...document.querySelectorAll('a.club-link')].map(a => ({
    href: a.getAttribute('href') || '', club: a.getAttribute('data-club') || '',
    nested: !!(a.parentElement && a.parentElement.closest(bad))}));
  const nolink = [...document.querySelectorAll('[data-club-nolink]')].map(e => e.getAttribute('data-club-nolink'));
  const loose = [...document.querySelectorAll('img[src*="teamlogos/mlb"], [data-club]')]
    .filter(e => !e.closest('a.club-link[href]') && !e.closest('[data-club-nolink]'))
    .map(e => e.outerHTML.slice(0, 160));
  const first = document.querySelector('a.club-link[href]');
  const sample = first ? {href: first.getAttribute('href'), club: first.getAttribute('data-club'),
                          name: (first.getAttribute('title') || '').split(':')[0]} : null;
  return {links, nolink, loose, sample};
}"""


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def base():
    with serve_site() as url:
        yield url


def _offsite(r):
    if "teamlogos/mlb" in r.request.url:
        r.fulfill(status=200, content_type="image/png", body=_PNG)
    else:
        r.abort()


def _open(browser, base, route, width, theme=None):
    pg = browser.new_page(viewport={"width": width, "height": 900})
    if theme:
        pg.add_init_script("try{localStorage.setItem('prospect-tracker.theme',%r);}catch(e){}" % theme)
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), _offsite)
    pg.goto(base + route)
    pg.wait_for_load_state("networkidle")
    return pg, errors


def _read(browser, base, route, width, theme=None):
    pg, errors = _open(browser, base, route, width, theme)
    out = pg.evaluate(_READ)
    out["theme"] = pg.evaluate("() => document.documentElement.getAttribute('data-theme')")
    pg.close()
    # aborted off-loopback requests surface as net::ERR_FAILED console lines
    out["errors"] = [e for e in errors if "ERR_FAILED" not in e and "Failed to load resource" not in e]
    return out


def test_skeleton_lists_are_well_formed():
    assert len(set(ROUTES)) == len(ROUTES)
    assert set(SWEPT) <= set(ROUTES), "a swept route is also an ALWAYS route"
    # the sweep reads SITE_MAP.md: its home, wire, history, scores, PROSPX and
    # Franchises rows are all there, and no crawler file is taken for a page
    for r in ("", "news/", "history/", "scores/", "prospx/", "franchise/", "collegesavant/pitcher_index.html"):
        assert r in SITE_MAP_ROUTES, r
    assert not [r for r in SITE_MAP_ROUTES if r.endswith((".txt", ".xml")) or "<" in r]


@pytest.mark.parametrize("route,width,theme", CASES)
def test_every_club_link_is_well_formed(browser, base, route, width, theme):
    r = _read(browser, base, route, width, theme)
    if route in THEMED and r["theme"] is not None:
        assert r["theme"] == theme, (route, r["theme"])
    for link in r["links"]:
        m = HREF_RE.match(link["href"])
        assert m, (route, link)
        assert link["club"] == m.group(3), (route, link)
        assert not link["nested"], (route, link)
    assert set(r["nolink"]) <= NOLINK_REASONS, (route, r["nolink"])
    assert not r["errors"], (route, r["errors"][:3])
    if route in SWEPT:
        assert not r["loose"], (route, r["loose"][:5])


def _landing_name(browser, base, href):
    """The club a link lands on: the Franchises masthead, or for a farm link
    the PROSPX farm system header."""
    pg, _ = _open(browser, base, href.lstrip("/"), 1280)
    sel = "#farm-detail-body .player-display-name" if "farm-org=" in href else ".fr-mast-name"
    pg.wait_for_selector(sel, timeout=60000)
    name = pg.inner_text(sel).strip()
    pg.close()
    return name


@pytest.mark.parametrize("route", SWEPT)
def test_a_sampled_club_link_lands_on_its_club(browser, base, route):
    r = _read(browser, base, route, 1280)
    if r["sample"] is None:
        pytest.skip(f"{route}: no club link on the served data today")
    href = r["sample"]["href"]
    assert href.startswith(("/franchise/#team=", "/prospx/#farm-org=")), (route, href)
    assert _landing_name(browser, base, href) == r["sample"]["name"], (route, r["sample"])


@pytest.mark.parametrize("href,name", [("/franchise/#team=CWS", "Chicago White Sox"),
                                       ("/prospx/#farm-org=OAK", "Athletics")])
def test_alias_routes_land_on_their_club(browser, base, href, name):
    """A payload spelling (CWS, OAK) opens its own club, never Arizona or an
    unknown organization (the trap links_efv_display.md A.0 measured)."""
    assert _landing_name(browser, base, href) == name


def test_generated_rows_keep_one_target_and_free_logos_link_their_club():
    """Owner answer Q-L1 on the generated pages (build_site, the server mirror):
    a logo inside a whole-row player link stays unlinked and says row-anchor;
    a logo outside any row link is a logo-only club link through the resolver
    (alt the full club name); a team name no club owns never links."""
    import build_site as B
    row = B._feed_item_html("debut", "", "", "jesus_made", "CWS", "Jesus Made", "debut")
    assert row.count("<a ") == 1 and 'data-club-nolink="row-anchor"' in row and "club-link" not in row
    assert 'data-club-nolink="row-anchor"' in B._row_logo("NYM")
    free = B._club_logo_link("CWS")
    assert free.startswith('<a class="club-link club-link--logo-only" href="/franchise/#team=CHW" data-club="CHW"')
    assert 'alt="Chicago White Sox"' in free
    assert B._club_logo_link("Seattle Mariners").count('href="/franchise/#team=SEA"') == 1
    for name in ("Worcester Red Sox", "ACL D-backs", "Texas"):
        got = B._club_logo_link(name)
        assert "href=" not in got and 'data-club-nolink="unresolved"' in got, name
    assert B._row_farm({"org": "CHW", "count": 1}, 1).startswith('<a class="row-link" href="/prospx/#farm-org=CHW">')


def test_hall_of_fame_franchises_link_current_clubs_and_mark_defunct_ones(browser, base):
    """The /hof/ Franchises section (owner rule 2026-09-25) names 30 current
    franchises and one defunct bucket: each current name links to its
    Franchises page through the resolver, and every defunct club (the bucket
    row and the Club column of its list) is marked, since no page exists."""
    for width in (1280, 390):
        pg, errors = _open(browser, base, "hof/", width)
        pg.click("[data-hofsection=franchises]")
        pg.wait_for_selector(".hof-fr-table", timeout=15000)
        r = pg.evaluate(_READ)
        names = pg.evaluate("""() => [...document.querySelectorAll('.hof-fr-table a.club-link')]
          .map(a => [a.textContent.trim(), (a.getAttribute('title') || '').split(':')[0]])""")
        pg.close()
        errors = [e for e in errors if "ERR_FAILED" not in e and "Failed to load resource" not in e]
        assert not errors, errors[:3]
        if not names:
            pytest.skip("the Franchises section is not live on the served data")
        assert len(names) == 30, len(names)
        assert all(text == full for text, full in names), names
        for link in r["links"]:
            m = HREF_RE.match(link["href"])
            assert m and m.group(1) == "/franchise/#team=" and link["club"] == m.group(3), link
            assert not link["nested"], link
        assert r["nolink"] and set(r["nolink"]) == {"defunct"}, r["nolink"]
        assert not r["loose"], r["loose"][:5]


def test_trade_board_prospect_rows_open_the_farm_and_mlb_rows_the_franchise(browser, base):
    """Owner ask 9 in its own words: a prospect's club opens his farm system,
    an MLB player's club its Franchises page. The board row is clickable, so
    the club link stops propagation and the row handler skips links."""
    pg, errors = _open(browser, base, "trademachine/", 1280)
    rows = pg.evaluate("""() => [...document.querySelectorAll('.tm-board-table tr.prospect-row')].map(tr => {
      const a = tr.querySelector('a.club-link');
      const st = tr.querySelector('.tm-signals span');
      return a ? [st ? st.textContent.trim() : '', a.getAttribute('href'),
                  a.getAttribute('onclick') || '', tr.getAttribute('onclick') || ''] : null; }).filter(Boolean)""")
    assert rows, "no linked board row"
    for kind, href, link_click, row_click in rows:
        want = "/prospx/#farm-org=" if kind == "MiLB" else "/franchise/#team="
        assert href.startswith(want), (kind, href)
        assert "stopPropagation" in link_click, link_click
        assert "closest('a,button')" in row_click, row_click
    # a click on the club link is not swallowed by the row: it opens the club
    first = pg.query_selector(".tm-board-table tr.prospect-row a.club-link")
    href = first.get_attribute("href")
    first.click()
    pg.wait_for_function("h => location.pathname + location.hash === h", arg=href, timeout=15000)
    pg.close()
    assert not [e for e in errors if "ERR_FAILED" not in e and "Failed to load resource" not in e]


def test_logo_only_club_links_carry_the_full_club_name(browser, base):
    """Owner answer Q-L3: a logo standing alone in a dense row links to the
    club with the full club name as its alt text; a mark beside its own linked
    code is the code link's mouse twin (out of the tab order)."""
    for route in ("fantasy/#section=keeper", "fa/", "fantasy/#section=dynasty"):
        pg, _ = _open(browser, base, route, 1280)
        got = pg.evaluate("""() => [...document.querySelectorAll('a.club-link')].map(a => {
          const img = a.querySelector('img'), txt = a.textContent.trim();
          return {mark: a.classList.contains('club-link--mark'), tab: a.getAttribute('tabindex'),
                  hidden: a.getAttribute('aria-hidden'), alt: img ? img.getAttribute('alt') : null,
                  txt, name: (a.getAttribute('title') || '').split(':')[0]}; })""")
        pg.close()
        if not got:
            continue
        for g in got:
            if g["mark"]:
                assert g["tab"] == "-1" and g["hidden"] == "true", (route, g)
            elif g["alt"] is not None and not g["txt"]:
                assert g["alt"] == g["name"], (route, g)


def test_fantasy_cards_are_not_buttons_around_links(browser, base):
    """A card that holds the player link and the club links is not a
    role=button (no link inside a button); the name link is the keyboard path."""
    pg, _ = _open(browser, base, "fantasy/#section=dynasty", 1280)
    n = pg.evaluate("""() => [document.querySelectorAll('.mlb-card a.club-link').length,
      document.querySelectorAll('.mlb-card[role=button]').length,
      document.querySelectorAll('.mlb-card[data-dynhref] a.dyn-name-link').length]""")
    pg.close()
    if not n[0]:
        pytest.skip("no Dynasty card on the served data")
    assert n[1] == 0 and n[2] > 0, n


def test_lineup_charts_white_sox_lands_on_the_white_sox(browser, base):
    """The owner's example: Lineup Charts print the StatsAPI code CWS; the link
    resolves to CHW and opens the Chicago White Sox page, not Arizona."""
    pg, _ = _open(browser, base, "mlbstats/#section=hitters&hview=charts", 1280)
    got = pg.evaluate("""() => [...document.querySelectorAll('.bp-depth-team a.club-link')]
      .filter(a => a.textContent.trim() === 'CWS')
      .map(a => [a.getAttribute('href'), a.getAttribute('data-club')])""")
    pg.close()
    if not got:
        pytest.skip("no CWS lineup card on the served data")
    assert got == [["/franchise/#team=CHW", "CHW"]], got
    assert _landing_name(browser, base, got[0][0]) == "Chicago White Sox"


def _prospx_errors(errors):
    return [e for e in errors if "ERR_FAILED" not in e and "Failed to load resource" not in e]


@pytest.mark.parametrize("width", [1280, 390])
def test_prospx_board_rows_split_the_player_link_and_the_club_link(browser, base, width):
    """Owner answer Q-L1 (split row links): a board row is no button; its
    player name is the row's link and its org cluster is a separate club link
    that sits above the row (position relative, z-index 1), comes after the
    player link in the tab order, and opens the farm page, not the player."""
    pg, errors = _open(browser, base, "prospx/", width)
    pg.wait_for_selector(".player-row[data-key] .org-cluster a.club-link", state="attached", timeout=60000)
    rows = pg.evaluate("""() => [...document.querySelectorAll('#content .player-row[data-key]')].slice(0, 20).map(r => {
      const name = r.querySelector('a.row-name-link'), club = r.querySelector('.org-cluster a.club-link');
      const cs = club ? getComputedStyle(club) : null;
      return {role: r.getAttribute('role'), name: !!name, club: club ? club.getAttribute('href') : null,
              after: !!(name && club && (name.compareDocumentPosition(club) & Node.DOCUMENT_POSITION_FOLLOWING)),
              z: cs ? cs.zIndex : null, pos: cs ? cs.position : null,
              stop: club ? (club.getAttribute('onclick') || '') : ''}; })""")
    bad = pg.evaluate("""() => document.querySelectorAll('#content [role=button] a, #content [role=button] button').length""")
    assert rows and bad == 0, (len(rows), bad)
    for r in rows:
        assert r["role"] is None and r["name"] and r["after"], r
        assert r["club"] and r["club"].startswith("/prospx/#farm-org="), r
        assert r["z"] == "1" and r["pos"] == "relative" and "_pxClubClick" in r["stop"], r
    # Tab from the player link reaches the club link of the same row.
    first = pg.query_selector("#content .player-row[data-key]")
    key = first.get_attribute("data-key")
    first.query_selector("a.row-name-link").focus()
    reached = False
    for _ in range(12):
        pg.keyboard.press("Tab")
        on = pg.evaluate("""() => { const a = document.activeElement;
          const row = a && a.closest('.player-row[data-key]');
          return [row ? row.getAttribute('data-key') : null, !!(a && a.matches('a.club-link'))]; }""")
        if on[0] != key:
            break
        if on[1]:
            reached = True
            break
    assert reached, "Tab from the player link never reached the row's club link"
    # A click on the club link opens the farm page and never the player card.
    link = first.query_selector(".org-cluster a.club-link")
    href = link.get_attribute("href")
    link.click()
    # the farm page adds its own view keys after the org (for example &ftree=)
    pg.wait_for_function("h => (location.pathname + location.hash + '&').startsWith(h + '&')", arg=href, timeout=15000)
    pg.wait_for_selector("#farm-detail-body .player-display-name", timeout=60000)
    pg.close()
    assert not _prospx_errors(errors), errors[:3]


def test_prospx_farm_rows_name_their_farm_and_are_not_buttons(browser, base):
    """A18: the Farm Systems org name is a real link to the farm page, so the
    row is no role=button around its watch, compare and glossary controls."""
    for route in ("prospx/#tab=farm", "prospx/#tab=farm&farmview=cards"):
        pg, errors = _open(browser, base, route, 1280)
        pg.wait_for_selector(".farm-row[data-org] a.club-link", state="attached", timeout=60000)
        got = pg.evaluate("""() => [...document.querySelectorAll('#content .farm-row[data-org]')].map(r => {
          const a = [...r.querySelectorAll('a.club-link:not(.club-link--mark)')].find(x => x.getClientRects().length);
          return [r.getAttribute('data-org'), r.getAttribute('role'), a ? a.getAttribute('href') : null,
                  a ? a.textContent.trim() : null]; })""")
        nested = pg.evaluate("""() => document.querySelectorAll('#content [role=button] a, #content [role=button] button').length""")
        pg.close()
        assert len(got) == 30 and nested == 0, (route, len(got), nested)
        for org, role, href, text in got:
            assert role is None and href == "/prospx/#farm-org=" + org and text, (route, org, role, href, text)
        assert not _prospx_errors(errors), errors[:3]


def test_prospx_ifa_org_links_are_anchors_through_the_resolver(browser, base):
    """A21: the IFA org mark was a span with an onclick and no href; it is a
    keyboard-reachable link built through the resolver, so a payload's OAK
    opens the Athletics farm page, and a name no club owns stays text."""
    pg, errors = _open(browser, base, "prospx/#tab=ifa", 1280)
    pg.wait_for_selector(".ifa-org-link", timeout=60000)
    tags = pg.evaluate("""() => [...document.querySelectorAll('.ifa-org-link')].map(e => [e.tagName, e.getAttribute('href') || ''])""")
    oak = pg.evaluate("() => _ifaOrgLink('OAK')")
    off = pg.evaluate("() => _ifaOrgLink('Texas')")
    pg.close()
    assert tags and all(tag == "A" and HREF_RE.match(h) for tag, h in tags), tags[:3]
    assert 'href="/prospx/#farm-org=ATH"' in oak and 'data-club="ATH"' in oak, oak
    assert 'data-club-nolink="unresolved"' in off and "href=" not in off, off
    assert not _prospx_errors(errors), errors[:3]


def test_prospx_clickable_rows_skip_their_club_links(browser, base):
    """Binding rule: inside a clickable row the club link stops propagation and
    the row handler skips a,button targets (the draft card guard pattern)."""
    for route in ("prospx/#tab=draft&dyear=2026", "prospx/#tab=draft&dyear=2026&dview=results",
                  "prospx/#tab=draft&dyear=2026&dview=overperformers"):
        pg, _ = _open(browser, base, route, 1280)
        pg.wait_for_selector("#content a.club-link", timeout=60000)
        got = pg.evaluate("""() => [...document.querySelectorAll('#content a.club-link')].map(a => {
          const row = a.parentElement.closest('[onclick]');
          return [a.getAttribute('onclick') || '', row ? (row.getAttribute('onclick') || '') : null]; })""")
        pg.close()
        assert got, route
        for link_click, row_click in got:
            assert "_pxClubClick" in link_click, (route, link_click)
            if row_click is not None:
                assert "closest('a,button')" in row_click, (route, row_click)


def test_prospx_farm_page_header_opens_the_franchise_and_the_rail_farms(browser, base):
    """A24: on a farm page the club's own name opens its Franchises page; the
    comparable farms in the rail open their farm pages. An alias route (CWS)
    lands on the same club and builds the same canonical links."""
    for route in ("prospx/#farm-org=CHW", "prospx/#farm-org=CWS"):
        pg, _ = _open(browser, base, route, 1280)
        pg.wait_for_selector("#farm-detail-body .detail-page-header a.club-link", timeout=60000)
        head = pg.evaluate("""() => [...document.querySelectorAll('#farm-detail-body .detail-page-header a.club-link')]
          .map(a => a.getAttribute('href'))""")
        rail = pg.evaluate("""() => [...document.querySelectorAll('#content .farm-side-card [data-org] a.club-link')]
          .map(a => [a.closest('[data-org]').getAttribute('data-org'), a.getAttribute('href')])""")
        pg.close()
        assert head and set(head) == {"/franchise/#team=CHW"}, (route, head)
        assert all(h == "/prospx/#farm-org=" + o for o, h in rail), (route, rail)


def test_prospx_overseas_signed_clubs_open_their_franchise(browser, base):
    """A22: a signed overseas pro's MLB club opens its Franchises page."""
    r = _read(browser, base, "prospx/#league=NPB", 1280)
    if not r["links"]:
        pytest.skip("no signed NPB alumni on the served data")
    assert all(link["href"].startswith("/franchise/#team=") for link in r["links"]), r["links"][:3]


def test_prospx_time_machine_logos_are_marked_row_anchor(browser, base):
    """A23: a Time Machine row is one player link, so the logo inside it stays
    unlinked and says why."""
    pg, _ = _open(browser, base, "prospx/#tab=timemachine", 1280)
    pg.wait_for_selector("a.tm-row", timeout=60000)
    got = pg.evaluate("""() => [...document.querySelectorAll('a.tm-row img[src*="teamlogos/mlb"]')]
      .map(i => i.getAttribute('data-club-nolink'))""")
    pg.close()
    if not got:
        pytest.skip("no Time Machine row on the served data")
    assert set(got) == {"row-anchor"}, set(got)

