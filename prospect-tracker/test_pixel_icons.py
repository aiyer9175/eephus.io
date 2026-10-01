# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""T1 (final-pass plan 5.7.4): the pixel icon sprite assets/eephus-icons.svg.

Pins what the 2026-09-24 judges found broken in the three prototype sets:
a symbol with no fill paints black through an external <use> (invisible on
dark), a double hyphen in a comment makes the file malformed so nothing
renders, and anything other than whole-pixel rectangles inside the 12 px core
softens or loses pixels at the menu crop. Also pins that the committed sprite
and bitmap table are exactly what tools/pixel_icons.py writes, so the drawing
has one source.
"""
from __future__ import annotations

import importlib.util
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
SPRITE = ROOT / "assets" / "eephus-icons.svg"
BITMAPS = ROOT / "assets" / "eephus-icons.json"
NS = "{http://www.w3.org/2000/svg}"
ACCENT = "fill:var(--ico-accent,currentColor)"


def _gen():
    spec = importlib.util.spec_from_file_location("pixel_icons", ROOT / "tools" / "pixel_icons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def text() -> str:
    return SPRITE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def symbols(text):
    root = ET.fromstring(text)
    syms = root.findall(f"{NS}symbol")
    assert syms, "the sprite carries no <symbol>"
    return syms


def test_sprite_within_byte_budget():
    assert SPRITE.stat().st_size <= 40_960, SPRITE.stat().st_size


def test_sprite_parses_and_has_no_comments(text):
    ET.fromstring(text)
    assert "<!--" not in text
    assert "--" not in text.replace("--ico-accent", "")


def test_every_symbol_carries_its_own_paint(symbols):
    for s in symbols:
        sid = s.get("id")
        assert sid and sid.startswith("i-"), sid
        assert s.get("viewBox") == "0 0 16 16", sid
        assert s.get("fill") == "currentColor", sid
        assert s.get("shape-rendering") == "crispEdges", sid


def test_no_raw_colour_or_soft_shape(text):
    no_refs = re.sub(r'href="#i-[^"]*"', "", text)
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", no_refs)
    for banned in ("gradient", "rx=", "<circle", "opacity", "stroke"):
        assert banned not in text, banned


def test_paths_are_whole_pixels_inside_the_core(symbols):
    for s in symbols:
        sid = s.get("id")
        paths = s.findall(f"{NS}path")
        uses = s.findall(f"{NS}use")
        assert paths or uses, sid
        assert len(paths) <= 2, sid
        for i, p in enumerate(paths):
            style = p.get("style")
            if i == 1:
                assert style == ACCENT, (sid, style)
            elif style is not None:
                assert style == ACCENT and len(paths) == 1, (sid, style)
            d = p.get("d")
            # Rectangles only: absolute M x y, then relative h/v runs, closed.
            assert re.fullmatch(r"(M-?\d+ -?\d+h\d+v\d+h-\d+z)+", d), (sid, d)
            for m in re.finditer(r"M(\d+) (\d+)h(\d+)v(\d+)h-(\d+)z", d):
                x, y, w, h, back = map(int, m.groups())
                assert w == back, (sid, m.group(0))
                assert 2 <= x and x + w <= 14, (sid, m.group(0))
                assert 2 <= y and y + h <= 14, (sid, m.group(0))
        for u in uses:
            ref = u.get("href")
            assert ref and ref.startswith("#i-"), (sid, ref)
            assert s.find(f"{NS}path") is None, sid


def test_aliases_point_at_a_drawn_symbol(symbols):
    drawn = {s.get("id") for s in symbols if s.find(f"{NS}path") is not None}
    for s in symbols:
        for u in s.findall(f"{NS}use"):
            assert u.get("href")[1:] in drawn, (s.get("id"), u.get("href"))


def test_bitmap_table_matches_the_sprite(symbols):
    bits = json.loads(BITMAPS.read_text(encoding="utf-8"))
    assert {"i-" + k for k in bits} == {s.get("id") for s in symbols}
    for k, b in bits.items():
        if "alias" in b:
            assert b["alias"] in bits and "alias" not in bits[b["alias"]], k
            continue
        assert len(b["rows"]) == 12 and all(len(r) == 12 for r in b["rows"]), k
        assert set("".join(b["rows"])) <= set("#+."), k


def test_regenerating_is_byte_identical():
    gen = _gen()
    svg, js, _ = gen.build()
    assert SPRITE.read_bytes() == svg.encode("utf-8"), (
        "assets/eephus-icons.svg is not what tools/pixel_icons.py builds; run it and commit")
    assert BITMAPS.read_bytes() == js.encode("utf-8"), (
        "assets/eephus-icons.json is not what tools/pixel_icons.py builds; run it and commit")
    assert gen.stale() == []
