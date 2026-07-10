# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Nav-drift guard for the hand-maintained static pages.

Every generated editorial page gets its top nav from `build_site._nav()`, but
three pages are hand-authored and hardcode the same nav bar: `prospx/index.html`
and the two CollegeSavant pages (`collegesavant/index.html`,
`pitcher_index.html`). Nothing forces them to stay in sync, so adding, removing,
or renaming a `NAV_ITEMS` entry would silently leave these pages pointing at a
stale set of links.

The nav now carries a grouped "MLB Modules" dropdown (Free Agency / Projections /
MLB Stats live under it via a <details>), so the canonical link set is the
FLATTENED leaf list `build_site.nav_leaves()`, not the top-level `NAV_ITEMS`.
This test asserts the `<nav class="eephus-links">` block on each hand-kept page
carries exactly that leaf set (same hrefs, same labels, same count) plus the
group label, catching drift in either direction at test time.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from build_site import NAV_ITEMS, nav_leaves

ROOT = Path(__file__).parent

STATIC_NAV_PAGES = [
    ROOT / "prospx" / "index.html",
    ROOT / "collegesavant" / "index.html",
    ROOT / "collegesavant" / "pitcher_index.html",
]

# Grab the first <nav class="eephus-links"> ... </nav> block (the top bar).
_NAV_RE = re.compile(
    r'<nav\s+class="eephus-links">(.*?)</nav>', re.DOTALL | re.IGNORECASE
)
_LINK_RE = re.compile(r"<a\b", re.IGNORECASE)


@pytest.mark.parametrize("page", STATIC_NAV_PAGES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_static_nav_matches_build_site(page: Path):
    assert page.exists(), f"missing hand-kept nav page: {page}"
    html = page.read_text(encoding="utf-8")

    m = _NAV_RE.search(html)
    assert m, f'{page.name}: no <nav class="eephus-links"> block found'
    nav = m.group(1)

    leaves = nav_leaves()

    # Every canonical leaf must be present as a link (href + visible label).
    missing = []
    for _key, label, href in leaves:
        has_href = f'href="{href}"' in nav
        has_label = f">{label}<" in nav
        if not (has_href and has_label):
            missing.append(f'{label} ({href})')
    assert not missing, (
        f"{page.name}: nav out of sync with build_site.nav_leaves() - "
        f"missing/renamed: {missing}"
    )

    # Each grouped node's label must render as a dropdown summary.
    for item in NAV_ITEMS:
        if isinstance(item, dict):
            assert f'>{item["group"]}<' in nav, (
                f'{page.name}: missing "{item["group"]}" group dropdown summary'
            )

    # And no extras: the <a> count must match the leaf count exactly, so a
    # removed entry left behind on the page is also caught. (The group's
    # <summary> is not an <a>, so it does not inflate the count.)
    link_count = len(_LINK_RE.findall(nav))
    assert link_count == len(leaves), (
        f"{page.name}: nav has {link_count} links but nav_leaves() has "
        f"{len(leaves)} - a stale/extra link drifted in."
    )
