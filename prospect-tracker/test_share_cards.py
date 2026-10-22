# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PB-07 / BR-07 (owner ask 2, 2026-09-30): the pixel share cards.

tools/pixel_brand.py writes a lowercase default card (assets/brand/
share-default.png: the s 10 lockup with its one ball, 'sabermetrics' at s 4, the
URL at s 2, no module list) and one card per module (assets/og/<key>.png: the s 4
lockup, the module icon at 8x, the title at s 6 or s 5, a 1 u banded rule, one
line, the URL). Pinned here:

  - the page-to-card map: with build_site.PIXEL_BRAND on, every module page
    names its own card in og:image and twitter:image, every other page the
    pixel default, and the three hand-kept pages their module's card
    (pixel_brand_hand_og, run by restamp), with nothing else on them moving;
  - with the flag off every page names assets/share-default.png, which since
    PB-10's flip holds the same pixels as the pixel default card;
  - the card keys are the generator's module list, every card file exists at
    1200 x 630, and each card's title is the page's own masthead title;
  - the copy on the cards: each line is cut from its page's own meta
    description, with no em or en dash, no banned or forecast word and no
    number or grade (the one figure is the betting page's 21+ age notice).
The generator's --check (every card pixel for pixel) is test_pixel_brand.py's
test_check_reproduces_every_output.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

import build_site as B

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import copy_lint  # noqa: E402
import pixel_brand_src as SRC  # noqa: E402

OG_RE = re.compile(r'<meta (?:property="og:image"|name="twitter:image") content="([^"]+)"')
DESC_RE = re.compile(r'<meta name="description" content="([^"]*)"')
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.S)
KEYS = tuple(k for k, _, _, _ in SRC.MODULES)
HAND_KEYS = {"prospx", "collegesavant"}
GENERATED = tuple(k for k in KEYS if k not in HAND_KEYS)
OTHER_PAGES = ("404", "parks", "models", "glossary", "sources")
FORECAST = re.compile(r"\b(luck|due|regress\w*|trending|will|clutch|sleeper)\b", re.I)


def _built(name: str, flag: bool) -> str:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(B, "PIXEL_BRAND", flag)
        return getattr(B, f"build_{name}")()


@pytest.fixture(scope="module")
def pages_on():
    return {k: _built(k, True) for k in GENERATED + OTHER_PAGES}


@pytest.fixture(scope="module")
def pages_off():
    return {k: _built(k, False) for k in GENERATED + OTHER_PAGES}


def _url(rel: str) -> str:
    return f"{B.SITE_ORIGIN}/{rel}"


def _file(url: str) -> Path:
    assert url.startswith(B.SITE_ORIGIN + "/"), url
    return ROOT / url[len(B.SITE_ORIGIN) + 1:]


def test_the_committed_flag_is_on():
    # PB-10 flipped it after the fWAR epoch's step Z.
    assert B.PIXEL_BRAND is True


def test_the_old_default_card_path_serves_the_pixel_card():
    # PB-10 copied the pixel default card over the vector-era file, so a link
    # unfurled before the flip (or a page that still names it) shows the new art.
    old = Image.open(ROOT / "assets" / "share-default.png").convert("RGBA")
    new = Image.open(ROOT / "assets" / "brand" / "share-default.png").convert("RGBA")
    assert old.size == new.size and old.tobytes() == new.tobytes()


def test_card_keys_are_the_generator_modules():
    assert B.OG_CARD_KEYS == KEYS
    assert set(B.HAND_OG_CARD) == set(B.HAND_AUTHORED_PAGES)
    assert set(B.HAND_OG_CARD.values()) == HAND_KEYS
    for key in GENERATED:
        assert callable(getattr(B, f"build_{key}", None)), key


@pytest.mark.parametrize("rel", ["assets/brand/share-default.png"] + [f"assets/og/{k}.png" for k in KEYS])
def test_every_card_file_is_1200_by_630(rel):
    im = Image.open(ROOT / rel)
    assert im.size == (SRC.CARD_W, SRC.CARD_H) == (1200, 630), rel


def test_the_card_scales_are_the_brand_table():
    # Default card: lockup s 10; module cards: lockup s 4 (plan section 3.3).
    assert SRC.STRIKES["og"] == 10 and SRC.STRIKES["og_small"] == 4
    assert SRC.DEFAULT_CARD_TAG == "sabermetrics"


@pytest.mark.parametrize("key", GENERATED)
def test_flag_on_every_module_page_names_its_own_card(pages_on, key):
    urls = OG_RE.findall(pages_on[key])
    card = _url(f"assets/og/{key}.png")
    assert urls == [card, card], (key, urls)
    assert _file(card).exists(), card


@pytest.mark.parametrize("name", OTHER_PAGES)
def test_flag_on_other_pages_take_the_pixel_default(pages_on, name):
    urls = OG_RE.findall(pages_on[name])
    assert urls == [B.DEFAULT_SHARE_IMAGE_PIXEL] * 2, (name, urls)
    assert _file(B.DEFAULT_SHARE_IMAGE_PIXEL).exists()


@pytest.mark.parametrize("name", GENERATED + OTHER_PAGES)
def test_flag_off_every_page_keeps_todays_card(pages_off, name):
    assert OG_RE.findall(pages_off[name]) == [B.DEFAULT_SHARE_IMAGE] * 2, name
    assert B.DEFAULT_SHARE_IMAGE == _url("assets/share-default.png")


@pytest.mark.parametrize("flag", [False, True])
def test_an_article_card_wins_under_either_flag(monkeypatch, flag):
    monkeypatch.setattr(B, "PIXEL_BRAND", flag)
    own = _url("assets/articles/x/share-card.png")
    assert OG_RE.findall(B._social_meta("t", "d", image=own)) == [own, own]


@pytest.mark.parametrize("rel", B.HAND_AUTHORED_PAGES)
def test_hand_page_takes_its_module_card_and_nothing_else_moves(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    # Start from the default card's lines (the page on disk carries its own
    # card since PB-10's flip), so the sync's one move is measured either way.
    text = B._HAND_OG_IMAGE_RE.sub(lambda m: m.group(1) + B.DEFAULT_SHARE_IMAGE + m.group(2), text)
    synced = B.pixel_brand_hand_og(text, rel)
    card = _url(f"assets/og/{B.HAND_OG_CARD[rel]}.png")
    assert OG_RE.findall(synced) == [card, card], rel
    before, after = text.splitlines(), synced.splitlines()
    assert len(before) == len(after)
    moved = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(moved) == 2 and all(OG_RE.search(after[i]) for i in moved), rel
    assert B.pixel_brand_hand_og(synced, rel) == synced


@pytest.mark.parametrize("rel", B.HAND_AUTHORED_PAGES)
def test_hand_page_on_disk_matches_the_flag(rel):
    urls = OG_RE.findall((ROOT / rel).read_text(encoding="utf-8"))
    want = _url(f"assets/og/{B.HAND_OG_CARD[rel]}.png") if B.PIXEL_BRAND else B.DEFAULT_SHARE_IMAGE
    assert urls == [want, want], rel


def _desc(text: str) -> str:
    return html.unescape(DESC_RE.search(text).group(1))


def _words(text: str) -> list[str]:
    return [w.strip(".,:;'") for w in re.findall(r"[a-z0-9+.'-]+", text.lower())]


def test_each_card_line_is_cut_from_its_pages_meta_description(pages_off):
    for key, _, _, line in SRC.MODULES:
        if key in HAND_KEYS:
            rels = [r for r, k in B.HAND_OG_CARD.items() if k == key]
            meta = " ".join(_desc((ROOT / r).read_text(encoding="utf-8")) for r in rels)
        else:
            meta = _desc(pages_off[key])
        allowed = set(_words(meta)) | {"and"}
        missing = [w for w in _words(line) if w not in allowed]
        assert not missing, (key, missing)


def test_each_card_title_is_the_pages_masthead_title(pages_off):
    for key, title, _, _ in SRC.MODULES:
        if key in HAND_KEYS or key == "hof":
            # the hof card names the shelf page (AWARDS_10) while the masthead
            # reads the module name "Awards / HoF" since the AWARDS_11 flip
            continue
        h1 = H1_RE.search(pages_off[key])
        assert h1, key
        text = html.unescape(re.sub(r"<[^>]+>", " ", h1.group(1)))
        assert title == " ".join(text.split()[:len(title.split())]), (key, title, text)


def test_card_copy_follows_the_copy_rules():
    lines = [SRC.DEFAULT_CARD_TAG, "eephus.io"]
    for key, title, route, line in SRC.MODULES:
        lines += [title, line, "eephus.io" + route]
    for text in lines:
        assert chr(0x2014) not in text and chr(0x2013) not in text, text
        assert not copy_lint.BAN_RE.search(text), text
        assert not FORECAST.search(text), text
        # No numbers or grades on any card (a digit inside a stat name, WAR7,
        # is a name); the one figure is the betting page's age notice.
        assert not re.search(r"(?<![A-Za-z])\d", text.replace("21+", "")), text
