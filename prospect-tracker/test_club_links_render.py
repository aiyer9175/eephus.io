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

Off-loopback requests are aborted, except the ESPN logo images, which are
answered with a local 1 px image so a logo stays in the page to be checked
(an aborted logo removes itself). The page must raise no console error.
"""
from __future__ import annotations

import base64
import re

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
# Routes whose club mentions have been converted (the SWEPT checks run on each).
# Each surface task appends its own routes.
SWEPT: list[str] = ["franchise/#team=CHW"] + MLB_A + MLB_B
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


def _open(browser, base, route, width):
    pg = browser.new_page(viewport={"width": width, "height": 900})
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), _offsite)
    pg.goto(base + route)
    pg.wait_for_load_state("networkidle")
    return pg, errors


def _read(browser, base, route, width):
    pg, errors = _open(browser, base, route, width)
    out = pg.evaluate(_READ)
    pg.close()
    # aborted off-loopback requests surface as net::ERR_FAILED console lines
    out["errors"] = [e for e in errors if "ERR_FAILED" not in e and "Failed to load resource" not in e]
    return out


def test_skeleton_lists_are_well_formed():
    assert len(set(ROUTES)) == len(ROUTES)
    assert set(SWEPT) <= set(ROUTES), "a swept route is also an ALWAYS route"


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("route", ROUTES)
def test_every_club_link_is_well_formed(browser, base, route, width):
    r = _read(browser, base, route, width)
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
