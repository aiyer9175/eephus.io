# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PB-03 / BR-03 (owner ask 2, 2026-09-30): the wordmark swap stays in sync.

Every eephus.io wordmark serves the committed pixel lockup
(assets/brand/wordmark-s{2,4,6}.svg, written by tools/pixel_brand.py) since the
owner's 2026-10-02 ask (PX_LOGO_ANIMATION), whatever build_site.PIXEL_BRAND says
(the flag still governs the favicon links and the footer mark). Pinned here:

  - the nav and the sidebar serve the s 2 fragment byte for byte, wrapped as
    <tag class="nameplate eephus-wordmark-px">{svg}<span
    class="wm-txt">eephus.io</span></tag>; the hero serves s 6 then its s 4
    phone twin, and the homepage h1 stays an h1;
  - the three hand-kept navs (prospx/index.html, collegesavant/index.html,
    collegesavant/pitcher_index.html) carry the same s 2 lockup byte for byte
    (pixel_brand_hand_nav, run by restamp), and nothing else on those pages
    moves;
  - no generated or hand-kept page carries the retired vector mark, and the
    committed flag is off.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import build_site as B

ROOT = Path(__file__).parent
BRAND = ROOT / "assets" / "brand"
HAND_PAGES = [ROOT / rel for rel in B.HAND_AUTHORED_PAGES]
_BRAND_LINK_RE = re.compile(
    r'<a class="eephus-wordmark" href="/" aria-label="eephus\.io home">(.*?)</a></span>')


def _fragment(s: int) -> str:
    return (BRAND / f"wordmark-s{s}.svg").read_bytes().decode("utf-8").strip()


def _wrapped(svgs: str, tag: str) -> str:
    return (f'<{tag} class="nameplate eephus-wordmark-px">{svgs}'
            f'<span class="wm-txt">eephus.io</span></{tag}>')


@pytest.fixture(params=[False, True], ids=["flag_off", "flag_on"])
def either_flag(request, monkeypatch):
    monkeypatch.setattr(B, "PIXEL_BRAND", request.param)
    yield


def test_the_committed_flag_is_off():
    # The rest of the swap (the favicon links, the footer mark) flips in its
    # own commit (PB-10); a build commit never carries the flag on.
    assert B.PIXEL_BRAND is False


def test_nav_and_sidebar_serve_the_s2_fragment_byte_for_byte(either_flag):
    s2 = _fragment(2)
    assert B.pixel_wordmark_fragment(2) == s2
    assert B.eephus_merged_wordmark("nav", tag="span") == _wrapped(s2, "span")
    assert B.eephus_merged_wordmark("sb", tag="span") == _wrapped(s2, "span")
    nav = B._nav("ledger")
    m = _BRAND_LINK_RE.search(nav)
    assert m and m.group(1) == _wrapped(s2, "span")


def test_hero_serves_s6_then_its_s4_twin_and_stays_an_h1(either_flag):
    hero = B.eephus_merged_wordmark("mast")
    assert hero == _wrapped(_fragment(6) + _fragment(4), "h1")
    lockup = B.eephus_logo_lockup()
    assert '<h1 class="nameplate eephus-wordmark-px">' in lockup
    assert lockup.count("<h1") == 1
    # The words stay on the page for assistive tech; the art is aria-hidden.
    assert '<span class="wm-txt">eephus.io</span>' in hero
    assert hero.count('aria-hidden="true"') == 2


@pytest.mark.parametrize("page", HAND_PAGES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_hand_nav_takes_the_s2_lockup_and_nothing_else_moves(page):
    text = page.read_text(encoding="utf-8")
    synced = B.pixel_brand_hand_nav(text)
    m = _BRAND_LINK_RE.search(synced)
    assert m, f"{page.name}: no nav brand link"
    assert m.group(1) == _wrapped(_fragment(2), "span"), f"{page.name}: nav lockup is not the s 2 fragment"
    # Only the lockup moved: cut it from both texts and the rest is identical.
    before = _BRAND_LINK_RE.search(text)
    assert before
    assert text[:before.start(1)] == synced[:m.start(1)]
    assert text[before.end(1):] == synced[m.end(1):]
    # Idempotent: a second sync (a regenerated fragment, a second build) is a no-op.
    assert B.pixel_brand_hand_nav(synced) == synced


@pytest.mark.parametrize("page", HAND_PAGES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_hand_nav_on_disk_is_the_s2_lockup(page):
    m = _BRAND_LINK_RE.search(page.read_text(encoding="utf-8"))
    assert m, f"{page.name}: no nav brand link"
    assert m.group(1) == _wrapped(_fragment(2), "span")


def test_generated_pages_on_disk_serve_the_pixel_lockup():
    s2 = _wrapped(_fragment(2), "span")
    for rel in ("index.html", "ledger/index.html", "404.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "eephus-wordmark-merged" not in text, rel
        assert s2 in text, rel
    home = (ROOT / "index.html").read_text(encoding="utf-8")
    assert _wrapped(_fragment(6) + _fragment(4), "h1") in home
