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
  carries data-club-nolink with an allowed reason.

Off-loopback requests are aborted; the page must raise no console error.
"""
from __future__ import annotations

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
# Routes whose club mentions have been converted (the SWEPT checks run on each).
# Empty until the first surface task lands; each task appends its own routes.
SWEPT: list[str] = []

_READ = """() => {
  const bad = 'a, button, [role=button], summary, label, select';
  const links = [...document.querySelectorAll('a.club-link')].map(a => ({
    href: a.getAttribute('href') || '', club: a.getAttribute('data-club') || '',
    nested: !!(a.parentElement && a.parentElement.closest(bad))}));
  const nolink = [...document.querySelectorAll('[data-club-nolink]')].map(e => e.getAttribute('data-club-nolink'));
  const loose = [...document.querySelectorAll('img[src*="teamlogos/mlb"], [data-club]')]
    .filter(e => !e.closest('a.club-link[href]') && !e.closest('[data-club-nolink]'))
    .map(e => e.outerHTML.slice(0, 160));
  return {links, nolink, loose};
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


def _read(browser, base, route, width):
    pg = browser.new_page(viewport={"width": width, "height": 900})
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.abort())
    pg.goto(base + route)
    pg.wait_for_load_state("networkidle")
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
