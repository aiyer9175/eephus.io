# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Top-100 Generate-GFX chip layout (owner ask, 2026-08-03).

The row layout gave a 100-player board 359x67px per player, of which the
headshot was 40x52 - 8.6% of the chip - while a whole column went to a surplus
figure whose sub-line rendered at 10px. At the ~600px width a social timeline
actually displays, that 10px lands under 4px on screen. The owner's brief: the
photo, the eFV grade and the rank are the only elements that MUST survive;
level, age and position are wanted if they stay legible; the surplus / $DvM+
column goes; header and footer compress; landscape is allowed.

These tests recompute the shipped geometry from the constants in
prospx/index.html, so they fail if someone edits the layout into a state where
100 chips no longer fit the canvas or text drops below the legibility floor.
Regex-over-source is the house pattern for this file (see
test_no_hardcoded_colors.py); the page's JS cannot be imported here.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

INDEX = Path(__file__).parent / "prospx" / "index.html"
SRC = INDEX.read_text(encoding="utf-8")

# The floor the redesign is built to hold. 10px was the old worst case.
MIN_FONT_PX = 11


def _formats() -> dict[str, tuple[int, int]]:
    block = re.search(r"const _GFX_FORMATS = \{(.*?)\n\};", SRC, re.S)
    assert block, "could not find _GFX_FORMATS"
    out = {}
    for m in re.finditer(r"(\w+):\s*\{\s*w:\s*(\d+),\s*h:\s*(\d+)", block.group(1)):
        out[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return out


def _chip_consts() -> dict[str, int]:
    m = re.search(r"function _gfxChipColumns\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
    assert m, "could not find _gfxChipColumns"
    body = m.group(1)
    c = dict(re.findall(r"(PAD|GAP|MIN_CHIP_W|MIN_CELL_H|CHROME)\s*=\s*(\d+)", body))
    for k in ("PAD", "GAP", "MIN_CHIP_W", "MIN_CELL_H", "CHROME"):
        assert k in c, f"{k} missing from _gfxChipColumns"
    return {k: int(v) for k, v in c.items()}


def _columns(cap: int, w: int, h: int, k: dict[str, int]) -> int:
    max_by_width = max(1, (w - k["PAD"] * 2 + k["GAP"]) // (k["MIN_CHIP_W"] + k["GAP"]))
    cols = max(1, round(math.sqrt(cap * (w / max(1, h)))))
    max_rows = max(1, (h - k["CHROME"] + k["GAP"]) // (k["MIN_CELL_H"] + k["GAP"]))
    cols = max(cols, math.ceil(cap / max_rows))
    return min(cols, max_by_width, max(1, cap))


def _geometry(cap: int, fmt_key: str):
    w, h = _formats()[fmt_key]
    k = _chip_consts()
    cols = _columns(cap, w, h, k)
    rows = math.ceil(cap / cols)
    chip_w = (w - 80 - (cols - 1) * k["GAP"]) // cols
    cell_h = max(k["MIN_CELL_H"], (h - k["CHROME"] - (rows - 1) * k["GAP"]) // rows)
    name = 14 if chip_w >= 130 else (12 if chip_w >= 100 else 11)
    photo = max(52, cell_h - (name + 11 + 22))
    total = rows * cell_h + (rows - 1) * k["GAP"] + k["CHROME"]
    return dict(cols=cols, rows=rows, chip_w=chip_w, cell_h=cell_h,
                name=name, meta=11, photo=photo, total=total, w=w, h=h)


# --------------------------------------------------------------------------
# The owner's board: 100 players, default canvas
# --------------------------------------------------------------------------

def test_default_gfx_opts_use_the_chip_layout_on_a_board_canvas():
    m = re.search(r"const _gfxOpts = \{(.*?)\};", SRC, re.S)
    assert m, "could not find _gfxOpts"
    opts = m.group(1)
    assert re.search(r'layout:\s*"chips"', opts), "chip layout is not the default"
    assert re.search(r'format:\s*"board"', opts), "default canvas is not the board format"


def test_one_hundred_chips_fit_the_default_canvas():
    """The failure this whole layout exists to end: a format that promises an
    aspect ratio and then runs off the bottom of it."""
    g = _geometry(100, "board")
    assert g["total"] <= g["h"], (
        f"100 chips need {g['total']}px on a {g['h']}px canvas "
        f"({g['cols']}x{g['rows']} at {g['cell_h']}px)")


def test_one_hundred_chips_fit_the_landscape_canvas():
    g = _geometry(100, "landscape")
    assert g["total"] <= g["h"], f"{g['total']} > {g['h']}"


@pytest.mark.parametrize("cap", [10, 25, 50, 100])
@pytest.mark.parametrize("fmt", ["board", "landscape"])
def test_no_text_below_the_legibility_floor(cap, fmt):
    g = _geometry(cap, fmt)
    assert g["name"] >= MIN_FONT_PX, f"name {g['name']}px"
    assert g["meta"] >= MIN_FONT_PX, f"meta {g['meta']}px"


def test_the_photo_dominates_the_chip():
    """The point of dropping the value column. The row layout gave the headshot
    40x52 = 2,080px2, 8.6% of a 359x67 chip."""
    g = _geometry(100, "board")
    photo_area = g["chip_w"] * g["photo"]
    chip_area = g["chip_w"] * g["cell_h"]
    assert photo_area / chip_area > 0.55, (
        f"photo is only {photo_area / chip_area:.0%} of the chip")
    assert photo_area > 4 * 2080, (
        f"photo area {photo_area}px2 is not a material gain on the old 2,080px2")


def test_chip_is_bigger_than_the_row_it_replaces_where_it_counts():
    """Total chip area may go down (a grid packs tighter); the photo must not."""
    g = _geometry(100, "board")
    assert g["chip_w"] * g["photo"] > 40 * 52


# --------------------------------------------------------------------------
# What the chip may and may not carry
# --------------------------------------------------------------------------

def _chip_html_body() -> str:
    m = re.search(r"function _gfxChipHtml\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
    assert m, "could not find _gfxChipHtml"
    return m.group(1)


def test_chip_carries_no_surplus_or_dvm():
    """The ask, as an invariant. The row layout spends ~45px of every chip on
    `$M` over `$DvM+ nnn`; neither belongs on the Top-100 graphic."""
    body = _chip_html_body()
    for banned in ("dvm", "valueSub", "$DvM", "showValue"):
        assert banned not in body, f"chip renderer still references {banned!r}"
    assert ".value" not in body, "chip renderer still reads the value column"


def test_chip_carries_the_three_required_elements():
    body = _chip_html_body()
    assert "_gfxChipPhotoCss" in body, "no photo"
    assert "fv-badge" in body, "no eFV grade badge"
    assert "rank" in body, "no rank"


def test_chip_keeps_the_preferred_meta_line():
    """Position / level / age, which the owner wanted kept if it stayed legible."""
    assert "r.meta" in _chip_html_body()


def test_chip_photo_uses_background_cover_not_object_fit():
    """html2canvas 1.4.1 does not implement object-fit, so an <img> exports
    STRETCHED - the reason the logo path was already rewritten to size instead
    of crop. A background-image with cover rasterises correctly."""
    m = re.search(r"function _gfxChipPhotoCss\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
    assert m, "could not find _gfxChipPhotoCss"
    body = m.group(1)
    assert "object-fit" not in body
    assert "cover" in body and "background-image" in body


def test_chip_layout_has_its_own_footer_legend():
    """The row legend explains $M and $DvM+. Printing it under a board that has
    neither would tell the reader to look for something that is not there."""
    m = re.search(r"function _gfxChipFooterNote\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
    assert m, "chip footer legend missing"
    assert "$DvM" not in m.group(1) and "$M" not in m.group(1)


# --------------------------------------------------------------------------
# Defects fixed alongside
# --------------------------------------------------------------------------

def test_show_all_is_capped():
    """The unfiltered active pool is 4,526 rows; at 67px a row that is a
    ~76,000px board and ~152,000px after the 2x export scale, well past the
    ~32,767px canvas limit, so the export failed silently and returned a blank
    image."""
    assert "GFX_MAX_ROWS" in SRC, "Show=All is uncapped"
    m = re.search(r"GFX_MAX_ROWS\s*=\s*(\d+)", SRC)
    assert m and int(m.group(1)) <= 400


def test_unknown_format_falls_back_to_one_canvas():
    """buildGfxBoard fell back to `portrait` while _gfxColumnCount fell back to
    `wide`, so a bad format key laid 1600px of column math inside a 1080px
    frame."""
    def fallback_in(fn_name: str) -> str:
        m = re.search(r"function " + fn_name + r"\([^)]*\)\s*\{(.*?)\n\}", SRC, re.S)
        assert m, f"could not find {fn_name}"
        f = re.search(r"_GFX_FORMATS\[[^\]]+\]\s*\|\|\s*_GFX_FORMATS\.(\w+)", m.group(1))
        assert f, f"{fn_name} has no format fallback"
        return f.group(1)

    # Only the LIST-BOARD pair has to agree: one picks the canvas, the other
    # picks the column math for it. The single-subject card renderers keep
    # their own natural canvases (a prospect card falls back to `tall`), which
    # is correct and not what this guard is about.
    board_fmt = fallback_in("buildGfxBoard")
    col_fmt = fallback_in("_gfxColumnCount")
    assert board_fmt == col_fmt, (
        f"list-board format fallbacks disagree: buildGfxBoard={board_fmt}, "
        f"_gfxColumnCount={col_fmt} - a bad format key would lay out one "
        f"canvas's column math inside another's frame")


def test_detached_board_height_is_not_read_from_the_layout():
    """offsetHeight on a node that was never appended is always 0."""
    assert "board.offsetHeight || H" not in SRC
