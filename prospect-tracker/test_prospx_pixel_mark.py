# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PB-05 / BR-05 (owner ask 2, 2026-09-30): the PROSPX mark as pixel art.

Pins the committed fragment assets/brand/prospx-mark.svg (the 22 x 22 drawing
from tools/pixel_brand.py at 2x, token classes only, integer, hidden), the
P/X floor (never below 40 px, whole multiples of 22 only), prospx_ball_logo()
under either PIXEL_BRAND state, and the hand-page sync that PIXEL_BRAND runs
on prospx/index.html: the vector badge and its monogram font stack go, the
pixel mark keeps the click-to-board handler, the title sits on the grid at
36 px with no tracking over a banded 3 px rule, the sync is idempotent and
moves nothing else, and the PROSPX style block gains no hex.
"""
from __future__ import annotations

import difflib
import inspect
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import build_site as B  # noqa: E402
import pixel_brand as PB  # noqa: E402

FRAGMENT = ROOT / "assets" / "brand" / "prospx-mark.svg"
PAGE = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
FONT_STACK = ("Old English Text MT", "UnifrakturCook", "Cloister Black")


def _style_block(text: str) -> str:
    return re.search(r"<style>(.*?)</style>", text, re.S).group(1)


def _grid(svg_text: str) -> list[str]:
    """The fragment's paths painted back onto a 22 x 22 grid of class keys."""
    root = ET.fromstring(svg_text)
    n = int(root.get("viewBox").split()[2])
    key = {v: k for k, v in PB.PXMARK_CLASS.items() if k not in "ms"}
    g = [["."] * n for _ in range(n)]
    for el in root.iter():
        if not el.tag.endswith("path"):
            continue
        for x, y, w, h in re.findall(r"M(\d+) (\d+)h(\d+)v(\d+)h-\d+z", el.get("d")):
            for yy in range(int(y), int(y) + int(h)):
                for xx in range(int(x), int(x) + int(w)):
                    assert g[yy][xx] == ".", "overlapping paths"
                    g[yy][xx] = key[el.get("class")]
    return ["".join(r) for r in g]


@pytest.fixture(scope="module")
def synced() -> str:
    return B.pixel_brand_hand_prospx(PAGE)


# ------------------------------------------------------------- the fragment
def test_fragment_is_the_generator_output():
    assert FRAGMENT.read_text(encoding="utf-8") == PB.pxmark_svg()


def test_fragment_is_token_only_integer_hidden_and_2x():
    text = FRAGMENT.read_text(encoding="utf-8")
    assert len(text.encode("utf-8")) <= 6 * 1024
    assert not HEX.search(text) and "rgb(" not in text
    root = ET.fromstring(text)
    assert (root.get("width"), root.get("height"), root.get("viewBox")) == ("44", "44", "0 0 22 22")
    assert root.get("aria-hidden") == "true" and root.get("class") == "wm-px px-mark"
    for el in root.iter():
        assert el.get("fill") is None
        if el.tag.endswith("path"):
            assert el.get("class") in set(PB.PXMARK_CLASS.values())
            assert all(re.fullmatch(r"-?\d+", n) for n in re.findall(r"-?[\d.]+", el.get("d")))
            style = el.get("style")
            assert style is None or style == "fill:var(--bg-secondary)"
            assert (style is not None) == (el.get("class") == "px-face")
    assert "<text" not in text and "font" not in text


def test_fragment_draws_the_generator_rows():
    rows = PB.pxmark()
    want = ["".join({"m": "k", "s": "k"}.get(c, c) for c in r) for r in rows]
    assert _grid(FRAGMENT.read_text(encoding="utf-8")) == want


def test_face_rim_and_letters_follow_the_served_inversion():
    # Face --bg-secondary, rim, stitches and P/X --text-primary (.wm-k), both themes.
    assert PB.PXMARK_CLASS["C"] == "px-face"
    assert {PB.PXMARK_CLASS[k] for k in "kms"} == {"wm-k"}
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    assert ".wm-px .wm-k { fill: var(--text-primary); }" in css
    for i, k in enumerate("abde", 1):
        assert f".wm-px .wm-{k} {{ fill: var(--seam-{i}); }}" in css


# ------------------------------------------------------------- the 40 px floor
@pytest.mark.parametrize("px", [16, 22, 40, 45])
def test_no_p_x_below_40_px_and_whole_scales_only(px):
    with pytest.raises(ValueError):
        B.pixel_prospx_mark(px)


@pytest.mark.parametrize("px", [44, 66, 88])
def test_whole_scales_from_44_px(px):
    root = ET.fromstring(B.pixel_prospx_mark(px, cls="px-ball"))
    assert root.get("width") == root.get("height") == str(px)
    assert root.get("class") == "px-ball wm-px px-mark"


def test_prospx_ball_logo_follows_the_flag(monkeypatch):
    monkeypatch.setattr(B, "PIXEL_BRAND", False)
    legacy = B.prospx_ball_logo("t", 44)
    assert legacy.startswith('<svg class="px-ball" width="44" height="44" viewBox="0 0 44 44"')
    monkeypatch.setattr(B, "PIXEL_BRAND", True)
    assert B.prospx_ball_logo("t", 44) == B.pixel_prospx_mark(44, cls="px-ball")
    with pytest.raises(ValueError):
        B.prospx_ball_logo("t", 16)


# ------------------------------------------------------------- the hand page
def test_the_committed_page_is_untouched_while_the_flag_is_off():
    if B.PIXEL_BRAND:
        pytest.skip("PIXEL_BRAND is on: the page carries the pixel mark")
    assert '<svg class="h1-logo" viewBox="0 0 44 44"' in PAGE
    assert "pixel-prospx-mark:begin" not in PAGE


def test_restamp_syncs_the_mark_only_under_the_flag():
    src = inspect.getsource(B.restamp_hand_authored_pages)
    flag_at = src.index("if PIXEL_BRAND:")
    assert src.index("pixel_brand_hand_prospx(stamped)") > flag_at


def test_sync_swaps_the_mark_and_keeps_the_handler(synced):
    marks = re.findall(r'<svg class="h1-logo[^"]*"[^>]*>', synced)
    assert marks == [marks[0]] and 'class="h1-logo wm-px px-mark"' in marks[0]
    for attr in ('onclick="goToProspectsBoard()"', 'style="cursor:pointer;"',
                 'title="Back to MiLB Prospects"', 'aria-hidden="true"', 'width="44" height="44"'):
        assert attr in marks[0], attr
    assert B.pixel_prospx_mark(44, cls="h1-logo").split(">", 1)[1] in synced
    assert '<h1 aria-label="PROSPX beta">' in synced
    assert "ball-seam-gradient" not in synced and "mono-letter" not in synced


def test_sync_deletes_the_monogram_font_stack(synced):
    for face in FONT_STACK:
        # Under the committed PIXEL_BRAND (PB-10) the page on disk is the synced one.
        assert (B.PIXEL_BRAND or face in PAGE) and face not in synced, face


def test_sync_puts_the_title_and_rule_on_the_grid(synced):
    style = _style_block(synced)
    block = style[style.index("pixel-prospx-mark:begin"):style.index("pixel-prospx-mark:end")]
    assert "h1 .h1-title { font-size: 36px; letter-spacing: 0; }" in block
    assert ("h1 .h1-title .h1-rule { width: 72px; height: 3px; "
            "background: var(--iridescent-steps); border-radius: 0; }") in block
    assert "@media (max-width: 900px) { h1 .h1-title { font-size: 24px; } }" in block
    assert "filter" not in block.split("*/", 1)[1]


def test_sync_adds_no_hex_to_the_prospx_style(synced):
    def count(text):
        no_tokens = re.sub(r"^\s*--[\w-]+\s*:\s*[^;]+;", "", _style_block(text), flags=re.M)
        return len(HEX.findall(no_tokens))
    assert count(synced) <= count(PAGE)


def test_sync_is_idempotent_and_moves_nothing_else(synced):
    assert B.pixel_brand_hand_prospx(synced) == synced
    if B.PIXEL_BRAND:
        # PB-10 flipped the flag: restamp has already synced the committed page.
        assert synced == PAGE
        return
    hunks = [ln for ln in difflib.unified_diff(PAGE.splitlines(), synced.splitlines(), lineterm="", n=0)
             if ln.startswith("@@")]
    assert len(hunks) == 2, hunks


def test_sync_copy_rules(synced):
    added = "\n".join(ln[1:] for ln in difflib.unified_diff(PAGE.splitlines(), synced.splitlines(), lineterm="", n=0)
                      if ln.startswith("+") and not ln.startswith("+++"))
    assert chr(0x2014) not in added and chr(0x2013) not in added
    assert not re.search(r"\b(seamless|robust|delve|comprehensive|crucial|essential|powerful|showcase|"
                         r"utilize|unlock|elevate|leverag\w*|will)\b", added, re.I)
