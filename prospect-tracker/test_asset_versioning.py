# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Stale-asset cache guard for the hand-authored pages (WS-F4).

The generated editorial pages stamp every local CSS/JS reference with a
content hash via `build_site._asset_ver()`, and their render tests cover
them. The three hand-authored pages below are NOT written by build_site.py;
they used to hand-bump a single shared `?v=` date stamp. That is exactly
where a stale-asset regression slips in: the production nginx once served
/assets/ with a 7-day max-age on the assumption every asset fetch was
`?v=`-stamped, so an unstamped site.css / eephus-*.js reference could run up
to a week stale after a deploy (WS-F4).

PRESENCE WAS NOT ENOUGH (2026-08-03). This guard only asserted that a `?v=`
existed, which a date stamp satisfies forever - so it stayed green while
site.css had changed on 07-31 and all three pages still advertised
`?v=20260730` (pitcher_index `?v=20260709`). A stamp that never changes is a
stamp that never busts. `build_site.restamp_hand_authored_pages()` now
rewrites these from the same content hash the generated pages use, and the
freshness test below fails if a build has not been run since the last asset
edit.

The tests assert that every LOCAL stylesheet-link href and script src on
those pages (a) carries a `?v=` cache-buster and (b) that the stamp equals
the referenced asset's CURRENT content hash. Out of scope by design:
  - external URLs (http[s]:// or protocol-relative //) - not ours to stamp
  - /data/ payloads (value_framework.js, collegesavant_*.js) - fetched and
    stamped at runtime, long-cached on purpose
  - icon / manifest / canonical / preconnect links - not CSS or JS, they do
    not break rendering when momentarily stale
  - refs whose asset is absent from the tree - there is no content to hash
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent

# Hand-authored surfaces (see SITE_MAP.md "Hand-maintained" table). The
# generated pages are covered by build_site._asset_ver() + their own tests.
HAND_AUTHORED_PAGES = [
    "prospx/index.html",
    "collegesavant/index.html",
    "collegesavant/pitcher_index.html",
]

# `[^>]` matches newlines too, so multi-line <link> tags (the webfont link
# in prospx spans two lines) are captured whole.
_STYLESHEET_LINK = re.compile(r"<link\b[^>]*\brel=[\"']stylesheet[\"'][^>]*>", re.I)
_HREF = re.compile(r"\bhref=[\"']([^\"']+)[\"']", re.I)
_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"'][^>]*>", re.I)


def _local_asset_refs(html: str) -> list[str]:
    """Stylesheet-link hrefs and script srcs that point at a LOCAL asset we
    control (so they must carry a ?v= cache-buster). External URLs and
    /data/ payloads are filtered out here."""
    refs: list[str] = []
    for tag in _STYLESHEET_LINK.findall(html):
        m = _HREF.search(tag)
        if m:
            refs.append(m.group(1))
    refs.extend(_SCRIPT_SRC.findall(html))

    local: list[str] = []
    for url in refs:
        u = url.strip()
        if u.startswith(("http://", "https://", "//")):
            continue  # external - not ours
        path = u.split("?", 1)[0]
        if path.startswith("/data/"):
            continue  # runtime-stamped payload, long-cached on purpose
        local.append(u)
    return local


@pytest.mark.parametrize("page", HAND_AUTHORED_PAGES)
def test_local_assets_are_version_stamped(page):
    path = ROOT / page
    assert path.exists(), f"missing hand-authored page: {page}"
    html = path.read_text(encoding="utf-8")

    refs = _local_asset_refs(html)
    # Sanity: the sweep must find refs, else a markup/regex change has
    # silently disabled the guard.
    assert refs, (
        f"{page}: found no local stylesheet/script refs to check - the "
        "guard may be mis-wired against the current markup."
    )

    unstamped = [u for u in refs if "?v=" not in u]
    assert not unstamped, (
        f"{page}: {len(unstamped)} local asset ref(s) carry no ?v= "
        "cache-buster and can serve stale after a deploy. Run "
        "`python build_site.py` to stamp them:\n  " + "\n  ".join(unstamped)
    )


@pytest.mark.parametrize("page", HAND_AUTHORED_PAGES)
def test_local_asset_stamps_match_current_content(page):
    """The stamp must be the asset's CURRENT content hash.

    This is the half the presence check could not see: a date stamp is
    present forever and busts nothing, so an edit to site.css shipped
    invisibly to prospx and collegesavant for as long as the CDN held it.
    """
    import build_site

    html = (ROOT / page).read_text(encoding="utf-8")

    stale = []
    for url in _local_asset_refs(html):
        path, _, query = url.partition("?")
        rel = path.lstrip("/")
        if not (ROOT / rel).exists():
            continue  # nothing on disk to hash
        want = build_site._asset_ver(rel)
        got = query[2:] if query.startswith("v=") else query
        if got != want:
            stale.append(f"{path}: stamped ?v={got}, content hash is {want}")

    assert not stale, (
        f"{page}: {len(stale)} asset stamp(s) do not match current content, so "
        "the CDN can serve the old asset alongside the new page. Run "
        "`python build_site.py` (it re-stamps these pages):\n  "
        + "\n  ".join(stale)
    )
