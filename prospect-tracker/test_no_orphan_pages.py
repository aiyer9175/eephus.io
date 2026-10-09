# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A page nobody can click is not shipped, however finished it is.

MEASURED 2026-09-07. /hof/ and /management/ were built, generated nightly,
registered in sitemap.xml, and linked from NOWHERE on the site: not the top nav,
not the homepage module cards, not the footer. Both pages already passed their own
key to `page()` as the nav `active` marker, so they were authored EXPECTING an
entry in NAV_ITEMS that was never added. A reader could reach either module only
by typing its URL, and the first sign of it was the owner saying the new modules
were not on the site.

Being in the sitemap is what makes this sharp: the site was telling crawlers about
two pages it would not tell a person about.

The invariant is NOT "everything is in the top nav" - /history/, /models/, /news/,
/parks/, /report/ and /sources/ are legitimately reached from the homepage or the
footer instead. It is that a page we advertise is reachable by following a link
from some page we build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
SITE_ORIGIN = "https://eephus.io"

# Redirect stubs carry meta robots=noindex and are deliberately absent from the
# sitemap; they are not orphans, they are forwarding addresses.
_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")


def _sitemap_paths() -> set[str]:
    p = ROOT / "sitemap.xml"
    if not p.exists():
        pytest.skip("sitemap.xml not built on this machine")
    out = set()
    for m in _LOC_RE.finditer(p.read_text(encoding="utf-8")):
        u = m.group(1).strip()
        if u.startswith(SITE_ORIGIN):
            u = u[len(SITE_ORIGIN):]
        out.add(u or "/")
    return out


def _all_hrefs() -> set[str]:
    """Every internal href appearing on any built page."""
    hrefs: set[str] = set()
    for page in ROOT.glob("*/index.html"):
        hrefs |= set(re.findall(r'href="(/[^"#?]*)', page.read_text(
            encoding="utf-8", errors="ignore")))
    idx = ROOT / "index.html"
    if idx.exists():
        hrefs |= set(re.findall(r'href="(/[^"#?]*)', idx.read_text(
            encoding="utf-8", errors="ignore")))
    return hrefs


def test_every_advertised_page_is_reachable_by_a_link():
    sm = _sitemap_paths()
    hrefs = _all_hrefs()
    orphans = sorted(u for u in sm if u not in hrefs)
    assert not orphans, (
        f"{len(orphans)} page(s) are in sitemap.xml and linked from NO built page, "
        f"so the site advertises them to crawlers and hides them from readers: "
        f"{orphans}. Add each to build_site.NAV_ITEMS (and the three hand-kept nav "
        f"mirrors), or to the homepage module cards, or drop it from the sitemap."
    )


def test_the_two_modules_that_shipped_orphaned_are_in_the_nav():
    """The specific regression, pinned by name.

    Both were finished, correct and invisible. This is cheap insurance that the
    next nav edit does not quietly drop them again.
    """
    from build_site import nav_leaves
    hrefs = {h for _k, _l, h in nav_leaves()}
    # Since AWARDS_11 (2026-10-09) the Hall of Fame slot's leaf reads "Awards / HoF" and
    # points at /awards/; /hof/ is the "Hall of Fame" link on the module strip both
    # pages of the module draw, so it stays one click from the nav.
    for u in ("/awards/", "/management/"):
        assert u in hrefs, f"{u} fell out of NAV_ITEMS again"
    awards = ROOT / "awards" / "index.html"
    if not awards.exists():
        pytest.skip("awards/index.html not built on this machine")
    strip = re.search(r'<nav class="mlbstats-sectionnav hof-modstrip"[^>]*>(.*?)</nav>',
                      awards.read_text(encoding="utf-8"), re.S)
    assert strip and 'href="/hof/"' in strip.group(1), "/hof/ fell off the Awards / HoF strip"


def test_every_nav_link_has_a_page_behind_it():
    """The reverse orphan: a nav link pointing at nothing.

    Deliberately NOT the mirror test "every page(key) has a nav entry". That one
    was tried and it flags /models/, /news/ and /parks/, which pass their key to
    page() and are reached from the homepage rather than the top bar. Passing a
    key the nav cannot highlight is untidy, not broken, and a guard that cries
    about three long-standing intentional pages is a guard someone deletes.

    A nav link to a missing page IS broken, every time.
    """
    from build_site import nav_leaves
    missing = []
    for key, label, href in nav_leaves():
        if not href.startswith("/") or href == "/":
            continue
        if not (ROOT / href.strip("/") / "index.html").exists():
            missing.append((key, label, href))
    assert not missing, f"nav links with no built page behind them: {missing}"
