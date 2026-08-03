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


def _chip_consts() -> dict[str, float]:
    """The layout constants, now module-level in prospx (they were locals inside
    _gfxChipColumns until the column search was rewritten)."""
    want = {
        "PAD": r"_GFX_CHIP_PAD\s*=\s*(\d+)",
        "GAP": r"_GFX_CHIP_GAP\s*=\s*(\d+)",
        "MIN_CHIP_W": r"_GFX_CHIP_MIN_W\s*=\s*(\d+)",
        "MIN_CELL_H": r"_GFX_CHIP_MIN_CELL_H\s*=\s*(\d+)",
        "CHROME": r"_GFX_CHIP_CHROME\s*=\s*(\d+)",
        "MAX_ASPECT": r"_GFX_CHIP_MAX_PHOTO_ASPECT\s*=\s*([\d.]+)",
        "MIN_ASPECT": r"_GFX_CHIP_MIN_PHOTO_ASPECT\s*=\s*([\d.]+)",
    }
    out: dict[str, float] = {}
    for key, pat in want.items():
        m = re.search(pat, SRC)
        assert m, f"{key} constant missing from prospx chip layout"
        out[key] = float(m.group(1))
    return out


def _text_h(chip_w: int) -> int:
    name = 14 if chip_w >= 130 else (12 if chip_w >= 100 else 11)
    return name + 11 + 22


def _geo_for(cap: int, w: int, h: int, cols: int, k):
    """Mirror of _gfxChipGeoFor. Returns None when the candidate is infeasible."""
    rows = math.ceil(cap / cols)
    chip_w = (w - int(k["PAD"]) * 2 - (cols - 1) * int(k["GAP"])) // cols
    if chip_w < k["MIN_CHIP_W"]:
        return None
    avail = (h - int(k["CHROME"]) - (rows - 1) * int(k["GAP"])) // rows
    if avail < k["MIN_CELL_H"]:
        return None
    text_h = _text_h(chip_w)
    photo = max(52, min(avail - text_h, round(chip_w * k["MAX_ASPECT"])))
    cell_h = max(int(k["MIN_CELL_H"]), photo + text_h)
    return dict(cols=cols, rows=rows, chip_w=chip_w, cell_h=cell_h, photo=photo,
                letterboxed=photo < chip_w * k["MIN_ASPECT"],
                area=chip_w * photo, empty=cols * rows - cap)


def _columns(cap: int, w: int, h: int, k) -> int:
    """Mirror of _gfxChipColumns: maximise photo area, break ties toward a full
    last row, reject letterboxed wells unless nothing else fits."""
    hi = max(1, min((w - int(k["PAD"]) * 2 + int(k["GAP"])) // (int(k["MIN_CHIP_W"]) + int(k["GAP"])),
                    max(1, cap)))

    def better(g, b):
        return (not b or g["area"] > b["area"] * 1.02
                or (g["area"] > b["area"] * 0.98 and g["empty"] < b["empty"]))

    best = boxed = None
    for c in range(1, hi + 1):
        g = _geo_for(cap, w, h, c, k)
        if not g:
            continue
        if g["letterboxed"]:
            if better(g, boxed):
                boxed = g
        elif better(g, best):
            best = g
    best = best or boxed
    return best["cols"] if best else hi


def _geometry(cap: int, fmt_key: str):
    w, h = _formats()[fmt_key]
    k = _chip_consts()
    cols = _columns(cap, w, h, k)
    g = _geo_for(cap, w, h, cols, k) or _geo_for(cap, w, h, 1, k)
    total = g["rows"] * g["cell_h"] + (g["rows"] - 1) * int(k["GAP"]) + int(k["CHROME"])
    name = 14 if g["chip_w"] >= 130 else (12 if g["chip_w"] >= 100 else 11)
    return dict(name=name, meta=11, total=total, w=w, h=h, **g)


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


def test_the_owners_board_has_no_ragged_last_row():
    """`round(sqrt(cap * w/h))` returned 9 columns for 100 players on the board
    canvas: 9x12 = 108 cells, so the bottom row held one chip and eight blanks -
    a ~1,360x137px hole, which is the empty space the owner reported. The
    module comment above _gfxChipColumns had specified ten columns all along."""
    g = _geometry(100, "board")
    assert g["cols"] == 10 and g["rows"] == 10, (
        f"expected a 10x10 grid for 100 chips, got {g['cols']}x{g['rows']}")
    assert g["empty"] == 0, f"{g['empty']} empty cells in the Top-100 board"


@pytest.mark.parametrize("cap", [10, 25, 50, 100])
@pytest.mark.parametrize("fmt", ["board", "landscape"])
def test_grid_wastes_at_most_one_partial_row(cap, fmt):
    """A few holes are unavoidable when cap is prime-ish; a whole empty row is
    not."""
    g = _geometry(cap, fmt)
    assert g["empty"] < g["cols"], (
        f"{fmt} n={cap}: {g['empty']} empty cells across {g['cols']} columns "
        "is a full blank row")


def test_the_photo_well_is_not_a_letterbox_on_the_default_board():
    """A headshot is cropped `cover` from `top center`, so a well wider than it
    is tall shows a strip across the eyes instead of a face. The old 100-chip
    board was 158x93, an 0.59 well."""
    g = _geometry(100, "board")
    aspect = g["photo"] / g["chip_w"]
    k = _chip_consts()
    assert aspect >= k["MIN_ASPECT"], (
        f"photo well is {g['chip_w']}x{g['photo']} (aspect {aspect:.2f}), a "
        "letterbox for a portrait headshot")
    assert aspect <= k["MAX_ASPECT"] + 0.01, (
        f"photo well aspect {aspect:.2f} is taller than the cap; a short list "
        "should leave margin rather than stretch the chip")


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


# --------------------------------------------------------------------------
# The caller/callee contract. Everything above asserts what the RENDERER reads;
# none of it could see that the CALLER was handing over a different object.
# --------------------------------------------------------------------------

def _chips_block() -> str:
    """The `if (useChips) { ... }` body that builds the grid."""
    start = SRC.index("if (useChips) {")
    return SRC[start:SRC.index("} else {", start)]


def test_chip_grid_normalizes_items_through_gfxrow():
    """THE REGRESSION (2026-08-03).

    The chip layout shipped calling `_gfxChipHtml(it, ...)` on the raw snapshot
    item, while the row layout it replaced called
    `_gfxRow(item, snap.kind, snap.meta)` first. The raw prospect object carries
    player_name / fv_close / mlbam_id; the chip renderer reads name / fv / mlbam.
    Every lookup missed, so the Top-100 board rendered a grid of team logos with
    a bare array index and no name, no eFV badge, no headshot and no meta line.

    Nothing threw - escapeHtml returns "" for null and the FV badge is
    null-guarded - which is exactly why it laid out perfectly while showing
    nothing, and why every source-grep test above stayed green.
    """
    block = _chips_block()
    assert "_gfxChipHtml(" in block, "chip grid no longer builds chips"
    assert re.search(r"_gfxChipHtml\(\s*_gfxRow\(", block), (
        "the chip grid must pass each item through _gfxRow before rendering; "
        "handing _gfxChipHtml a raw snapshot item silently blanks every field")


def test_every_field_the_chip_reads_is_a_field_gfxrow_returns():
    """Pin the shape contract itself, so a future rename cannot re-open the gap
    from the other side."""
    m = re.search(r"function _gfxRow\(([^)]*)\)\s*\{", SRC)
    assert m, "could not find _gfxRow"
    start = m.start()
    body = SRC[start:start + 12000]
    reads = set(re.findall(r"\br\.(\w+)", _chip_html_body()))
    assert reads, "chip renderer reads no row fields at all"
    for field in sorted(reads):
        assert re.search(rf"\b{field}\b\s*[:,=]", body), (
            f"_gfxChipHtml reads r.{field}, which _gfxRow does not appear to "
            "produce - the two shapes have drifted apart again")


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
