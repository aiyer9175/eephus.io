# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Nav-drift guard for the hand-maintained CollegeSavant pages.

Every editorial page gets its top nav from `build_site._nav()`, but the two
CollegeSavant pages (`collegesavant/index.html`, `pitcher_index.html`) are
hand-authored and hardcode the same nav bar. Nothing forced them to stay in
sync, so adding/removing/renaming a `NAV_ITEMS` entry would silently leave
CollegeSavant pointing at a stale set of links.

This test asserts the `<nav class="eephus-links">` block on each CollegeSavant
page carries exactly the canonical `NAV_ITEMS` set (same hrefs, same labels,
same count) — catching drift in either direction at test time instead of in
production.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from build_site import NAV_ITEMS

ROOT = Path(__file__).parent

CS_PAGES = [
    ROOT / "collegesavant" / "index.html",
    ROOT / "collegesavant" / "pitcher_index.html",
]

# Grab the first <nav class="eephus-links"> ... </nav> block (the top bar).
_NAV_RE = re.compile(
    r'<nav\s+class="eephus-links">(.*?)</nav>', re.DOTALL | re.IGNORECASE
)
_LINK_RE = re.compile(r"<a\b", re.IGNORECASE)


@pytest.mark.parametrize("page", CS_PAGES, ids=lambda p: p.name)
def test_collegesavant_nav_matches_build_site(page: Path):
    assert page.exists(), f"missing CollegeSavant page: {page}"
    html = page.read_text(encoding="utf-8")

    m = _NAV_RE.search(html)
    assert m, f'{page.name}: no <nav class="eephus-links"> block found'
    nav = m.group(1)

    # Every canonical item must be present as a link (href + visible label).
    missing = []
    for _key, label, href in NAV_ITEMS:
        has_href = f'href="{href}"' in nav
        has_label = f">{label}<" in nav
        if not (has_href and has_label):
            missing.append(f'{label} ({href})')
    assert not missing, (
        f"{page.name}: nav out of sync with build_site.NAV_ITEMS — "
        f"missing/renamed: {missing}"
    )

    # And no extras: the link count must match exactly, so a removed
    # NAV_ITEMS entry left behind on the page is also caught.
    link_count = len(_LINK_RE.findall(nav))
    assert link_count == len(NAV_ITEMS), (
        f"{page.name}: nav has {link_count} links but NAV_ITEMS has "
        f"{len(NAV_ITEMS)} — a stale/extra link drifted in."
    )
