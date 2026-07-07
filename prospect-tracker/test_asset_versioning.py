# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Stale-asset cache guard for the hand-authored pages (WS-F4).

The generated editorial pages stamp every local CSS/JS reference with a
content hash via `build_site._asset_ver()`, and their render tests cover
them. The three hand-authored pages below are NOT written by build_site.py;
they hand-bump a single shared `?v=` date stamp. That is exactly where a
stale-asset regression slips in: the production nginx once served /assets/
with a 7-day max-age on the assumption every asset fetch was `?v=`-stamped,
so an unstamped site.css / eephus-*.js reference could run up to a week
stale after a deploy (WS-F4).

This test asserts that every LOCAL stylesheet-link href and script src on
those pages carries a `?v=` cache-buster. Out of scope by design:
  - external URLs (http[s]:// or protocol-relative //) - not ours to stamp
  - /data/ payloads (value_framework.js, collegesavant_*.js) - fetched and
    stamped at runtime, long-cached on purpose
  - icon / manifest / canonical / preconnect links - not CSS or JS, they do
    not break rendering when momentarily stale
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
        "cache-buster and can serve stale after a deploy. Add a ?v=<stamp> "
        "(hand-bump the shared date):\n  " + "\n  ".join(unstamped)
    )
