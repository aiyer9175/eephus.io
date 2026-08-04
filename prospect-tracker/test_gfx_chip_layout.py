# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Generate-GFX list layout: names-first, no player photos (owner ask, 2026-08-04).

SUPERSEDES the 2026-08-03 contract this file used to pin. That version was
written for a photo-centric chip grid and asserted, among other things, that
"the photo dominates the chip" and that the photo well uses background-cover.
The owner then asked for the opposite: take the player pictures OFF the list
graphics, put the names in front, and spend the reclaimed space on the cramping.
So those assertions were not failing, they had EXPIRED, and the file is rebuilt
around the new contract rather than deleted. The old brief is preserved in the
commit history (406ac05) and in docs/EXECUTION_2026-08-04-eight-asks.md.

The carve-out matters and is pinned here too: photos come off the LISTS only.
The single-subject hero card, the compare card and the pack mini-card KEEP their
headshots, by explicit owner decision. A future edit that strips those, or that
quietly reinstates a headshot in a list row, fails here.

What is guarded:
  1. neither list renderer emits a player photo, in any form
  2. the single-subject cards still do
  3. nothing on a board renders below the 11px legibility floor
  4. the geometry search leaves no ragged last row and never clips a tile
  5. the reclaimed width actually reaches the NAME field
  6. tile names WRAP rather than ellipsise (the truncation the owner reported)
  7. both renderers normalise through _gfxRow (the 2026-08-03 blank-board bug)

Geometry is recomputed from the constants in prospx/index.html, mirroring the
shipped JS, so an edit that breaks the layout fails here rather than in an
export. Regex-over-source is the house pattern for this file (see
test_no_hardcoded_colors.py); the page's JS cannot be imported.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

INDEX = Path(__file__).parent / "prospx" / "index.html"
SRC = INDEX.read_text(encoding="utf-8")

# The floor the redesign is built to hold. The old list rows put meta at 9px,
# which at the ~600px width a social timeline actually displays lands at 3.4px.
MIN_FONT_PX = 11

# The owner's canonical board: every top-100 prospect on one 16:9 canvas.
OWNER_CAP = 100
OWNER_FORMAT = "wide"


def _jsround(x: float) -> int:
    """JS Math.round: half UP. Python's round() is banker's and disagrees on .5."""
    return math.floor(x + 0.5)


def _formats() -> dict[str, tuple[int, int]]:
    block = re.search(r"const _GFX_FORMATS = \{(.*?)\n\};", SRC, re.S)
    assert block, "could not find _GFX_FORMATS"
    out = {}
    for m in re.finditer(r"(\w+):\s*\{\s*w:\s*(\d+),\s*h:\s*(\d+)", block.group(1)):
        out[m.group(1)] = (int(m.group(2)), int(m.group(3)))
    return out


def _consts() -> dict[str, float]:
    want = {
        "PAD": r"_GFX_CHIP_PAD\s*=\s*(\d+)",
        "GAP": r"_GFX_CHIP_GAP\s*=\s*(\d+)",
        "CHROME": r"_GFX_CHIP_CHROME\s*=\s*(\d+)",
        "TILE_MIN_W": r"_GFX_TILE_MIN_W\s*=\s*(\d+)",
        "TILE_MIN_CELL_H": r"_GFX_TILE_MIN_CELL_H\s*=\s*(\d+)",
        "ROW_MIN_H": r"_GFX_LIST_MIN_ROW_H\s*=\s*(\d+)",
        "ROW_MAX_H": r"_GFX_LIST_MAX_ROW_H\s*=\s*(\d+)",
        "COL_MIN_W": r"_GFX_LIST_MIN_COL_W\s*=\s*(\d+)",
        "COL_MAX_W": r"_GFX_LIST_MAX_COL_W\s*=\s*(\d+)",
        "STACK_MIN_H": r"_GFX_LIST_META_STACK_MIN_H\s*=\s*(\d+)",
        "INLINE_MIN_W": r"_GFX_LIST_META_INLINE_MIN_W\s*=\s*(\d+)",
        "META_PX": r"_GFX_LIST_META_PX\s*=\s*(\d+)",
    }
    out: dict[str, float] = {}
    for key, pat in want.items():
        m = re.search(pat, SRC)
        assert m, f"could not find layout constant {key} ({pat})"
        out[key] = float(m.group(1))
    return out


def _fn_body(name: str) -> str:
    """Source of one top-level function, brace-matched."""
    m = re.search(r"^function %s\s*\(" % re.escape(name), SRC, re.M)
    assert m, f"could not find function {name}"
    i = SRC.index("{", m.end() - 1)
    depth, j = 0, i
    while True:
        if SRC[j] == "{":
            depth += 1
        elif SRC[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return SRC[m.start():j + 1]


C = _consts()
FMT = _formats()


# --- geometry, mirroring the shipped JS -------------------------------------

def tile_name_px(w: float) -> int:
    return 19 if w >= 230 else (17 if w >= 190 else (15 if w >= 160 else 14))


def tile_line_h(w: float) -> int:
    return _jsround(tile_name_px(w) * 1.22)


def tile_text_h(w: float) -> int:
    return tile_line_h(w) * 2 + 20 + 15 + 13 + 2


def tile_geo(cap: int, fmt: tuple[int, int], cols: int):
    w, h = fmt
    rows = math.ceil(cap / cols)
    chip_w = math.floor((w - C["PAD"] * 2 - (cols - 1) * C["GAP"]) / cols)
    if chip_w < C["TILE_MIN_W"]:
        return None
    avail = math.floor((h - C["CHROME"] - (rows - 1) * C["GAP"]) / rows)
    text_h = tile_text_h(chip_w)
    if avail < max(C["TILE_MIN_CELL_H"], text_h):
        return None
    cell_h = max(C["TILE_MIN_CELL_H"], min(avail, text_h + 14))
    return {"cols": cols, "rows": rows, "chipW": chip_w, "cellH": cell_h,
            "nameArea": chip_w * tile_name_px(chip_w), "empty": cols * rows - cap}


def tile_cols(cap: int, fmt: tuple[int, int]) -> int:
    w, _ = fmt
    usable = w - C["PAD"] * 2
    hi = max(1, min(int((usable + C["GAP"]) // (C["TILE_MIN_W"] + C["GAP"])), max(1, cap)))
    best = None
    for c in range(1, hi + 1):
        g = tile_geo(cap, fmt, c)
        if not g:
            continue
        if (best is None or g["nameArea"] > best["nameArea"] * 1.02
                or (g["nameArea"] > best["nameArea"] * 0.98 and g["empty"] < best["empty"])):
            best = g
    return best["cols"] if best else hi


def list_geo(cap: int, fmt: tuple[int, int], cols: int):
    w, h = fmt
    rows = math.ceil(cap / cols)
    col_w = min(C["COL_MAX_W"],
                math.floor((w - C["PAD"] * 2 - (cols - 1) * C["GAP"]) / cols))
    if col_w < C["COL_MIN_W"]:
        return None
    row_h = min(C["ROW_MAX_H"], math.floor((h - C["CHROME"]) / rows))
    if row_h < C["ROW_MIN_H"]:
        return None
    meta = ("stack" if row_h >= C["STACK_MIN_H"]
            else ("inline" if col_w >= C["INLINE_MIN_W"] else "none"))
    return {"cols": cols, "rows": rows, "colW": col_w, "rowH": row_h, "metaMode": meta,
            "name": 14 if row_h >= C["STACK_MIN_H"] else 13,
            "area": col_w * row_h, "empty": cols * rows - cap}


def list_cols(cap: int, fmt: tuple[int, int]) -> int:
    w, _ = fmt
    hi = max(1, min(int((w - C["PAD"] * 2 + C["GAP"]) // (C["COL_MIN_W"] + C["GAP"])),
                    max(1, cap)))
    best = None
    for c in range(1, hi + 1):
        g = list_geo(cap, fmt, c)
        if not g:
            continue
        if (best is None or g["area"] > best["area"] * 1.02
                or (g["area"] > best["area"] * 0.98 and g["empty"] < best["empty"])):
            best = g
    return best["cols"] if best else hi


CAPS = [10, 25, 50, 100]
LIST_FORMATS = ["wide", "board", "landscape", "portrait", "tall", "square", "story"]


# --- 1. the owner ask: no player photos on the lists ------------------------

PHOTO_MARKERS = [
    "_gfxHeadshotURL",        # the MLB headshot URL builder
    "_gfxListPhotoCss",       # the retired list photo-layer helper
    "_gfxChipPhotoCss",       # the retired chip photo-well helper
    "_gfxAvatar",             # the live-DOM avatar (legacy row path)
    "_gfxRowHasPhotoAvatar",  # the photos-toggle predicate
    "_gfxPhotoBaseLayer",
    "background-image",
]


@pytest.mark.parametrize("fn", ["_gfxListRowHtml", "_gfxTileHtml"])
def test_list_renderers_emit_no_player_photo(fn):
    """The owner ask, pinned at the only place it can regress: the renderers."""
    body = _fn_body(fn)
    for marker in PHOTO_MARKERS:
        assert marker not in body, (
            f"{fn} references {marker!r}. Player photos were removed from the LIST "
            "graphics on 2026-08-04 (owner ask); the name is the subject there. "
            "Hero / compare / pack cards keep theirs.")


def test_single_subject_cards_still_carry_photos():
    """The carve-out. Photos off the lists must not become photos off everything."""
    for fn in ("buildProspectCard", "buildCompareCard", "_gfxMiniCard"):
        body = _fn_body(fn)
        assert "_gfxHeadshotURL" in body, (
            f"{fn} no longer builds a headshot URL. The owner kept photos on the "
            "single-subject cards; only the list layouts are names-only.")


def test_photos_toggle_is_scoped_to_cards():
    """`photos` must not gate a list layout, or the control silently does nothing."""
    for fn in ("_gfxListRowHtml", "_gfxTileHtml"):
        assert "_gfxOpts.photos" not in _fn_body(fn), (
            f"{fn} reads _gfxOpts.photos, but list layouts are unconditionally "
            "names-only, so the toggle would be inert there.")


# --- 2. legibility floor ----------------------------------------------------

@pytest.mark.parametrize("fmt_name", LIST_FORMATS)
@pytest.mark.parametrize("cap", CAPS)
def test_no_text_below_the_legibility_floor(fmt_name, cap):
    fmt = FMT[fmt_name]

    g = list_geo(cap, fmt, list_cols(cap, fmt))
    if g:
        assert g["name"] >= 13, f"rows {fmt_name}/{cap}: name {g['name']}px"
        assert C["META_PX"] >= MIN_FONT_PX, "list meta below the floor"

    t = tile_geo(cap, fmt, tile_cols(cap, fmt))
    if t:
        assert tile_name_px(t["chipW"]) >= 14, f"tiles {fmt_name}/{cap}: name too small"


def test_the_meta_line_rose_off_the_old_nine_px():
    """9px was the one place the board still broke its own floor."""
    assert C["META_PX"] >= MIN_FONT_PX, (
        f"list meta is {C['META_PX']}px; the floor is {MIN_FONT_PX}px")


# --- 3. the grid fits, and nothing clips ------------------------------------

@pytest.mark.parametrize("fmt_name", LIST_FORMATS)
@pytest.mark.parametrize("cap", CAPS)
def test_grid_leaves_no_ragged_last_row(fmt_name, cap):
    fmt = FMT[fmt_name]
    for label, geo in (("rows", list_geo(cap, fmt, list_cols(cap, fmt))),
                       ("tiles", tile_geo(cap, fmt, tile_cols(cap, fmt)))):
        if geo:
            assert geo["empty"] < geo["cols"], (
                f"{label} {fmt_name}/{cap}: {geo['empty']} empty cells is a whole "
                f"blank column of {geo['cols']}")


@pytest.mark.parametrize("fmt_name", LIST_FORMATS)
@pytest.mark.parametrize("cap", CAPS)
def test_tile_cell_reserves_its_own_text(fmt_name, cap):
    """The clipping guard. A cell shorter than its text budget loses the meta line."""
    fmt = FMT[fmt_name]
    t = tile_geo(cap, fmt, tile_cols(cap, fmt))
    if t:
        assert t["cellH"] >= tile_text_h(t["chipW"]), (
            f"tiles {fmt_name}/{cap}: cell {t['cellH']}px < text budget "
            f"{tile_text_h(t['chipW'])}px, so content clips")


def test_tile_text_budget_is_itemised_against_the_markup():
    """Two name lines + strip + meta + padding + border.

    The first cut of this budget counted the meta line as 10px and forgot the
    2px border, under-reserving by 6px. That is exactly the "elements
    disappearing" failure the rewrite exists to remove, so the arithmetic is
    pinned rather than trusted.
    """
    for w in (140, 160, 190, 230, 400):
        assert tile_text_h(w) == tile_line_h(w) * 2 + 20 + 15 + 13 + 2


# --- 4. the reclaimed space reaches the NAME --------------------------------

def test_the_owner_board_fits_one_canvas_with_room_for_names():
    fmt = FMT[OWNER_FORMAT]
    g = list_geo(OWNER_CAP, fmt, list_cols(OWNER_CAP, fmt))
    assert g, "the owner's 100-on-16:9 board does not lay out at all"
    assert g["empty"] == 0, f"ragged board: {g['empty']} empty cells"
    # rank 24 + gaps + badge + logo + padding, the only fixed furniture left.
    name_field = g["colW"] - 8 - 24 - 6 - 28 - 18 - 12
    assert name_field >= 200, (
        f"name field is {name_field}px. Removing the 30px headshot and its 6px "
        "gutter was supposed to hand that width to the name; if this drops, the "
        "truncation the owner reported is back.")


def test_rows_are_wider_than_the_photo_era_minimum():
    """Guards the reclaimed width at the constant level, not just one board."""
    assert C["COL_MIN_W"] >= 240, (
        "list columns narrowed below the photo-era minimum, which spends the "
        "reclaimed headshot width on more columns instead of longer names")


# --- 5. names wrap rather than truncate -------------------------------------

def test_tile_name_wraps_instead_of_ellipsising():
    body = _fn_body("_gfxTileHtml")
    assert "overflow-wrap" in body, "tile name should be able to break, not clip"
    name_block = body[body.index("geo.nameLineH"):]
    assert "text-overflow:ellipsis" not in name_block, (
        "the tile name ellipsises again. Truncated names are the defect this "
        "layout was rebuilt to fix; the two-line box exists so they wrap.")


def test_card_names_step_down_to_fit():
    """Hero / compare / farm / pack names had no ellipsis and no step-down."""
    assert re.search(r"^function _gfxFitNamePx\s*\(", SRC, re.M), (
        "_gfxFitNamePx is gone; long card names will wrap and shove the card "
        "body down again (and misalign the compare columns)")
    for fn in ("buildProspectCard", "buildCompareCard", "_gfxMiniCard"):
        assert "_gfxFitNamePx" in _fn_body(fn), f"{fn} does not fit its name"


# --- 6. the 2026-08-03 blank-board bug --------------------------------------

def test_list_renderers_are_fed_through_gfxrow():
    """The chip path once shipped without _gfxRow and drew a grid of logos.

    Nothing threw, because escapeHtml returns "" for null and the badge is
    null-guarded, so it laid out perfectly while showing nothing.
    """
    board = _fn_body("buildGfxBoard")
    for renderer in ("_gfxTileHtml", "_gfxListRowHtml"):
        for m in re.finditer(re.escape(renderer) + r"\(([^,]+),", board):
            arg = m.group(1).strip()
            assert "_gfxRow" in arg, (
                f"{renderer} is called with {arg!r}, not a _gfxRow(...) result. "
                "Raw snapshot items carry player_name / fv_close / mlbam_id and "
                "every lookup misses silently.")


def test_unnormalised_rows_are_loud():
    assert re.search(r"^function _gfxWarnUnnormalized\s*\(", SRC, re.M), (
        "the un-normalised-row guard is gone; a renderer handed a raw item will "
        "draw blank cells and throw nothing")
    for fn in ("_gfxTileHtml", "_gfxListRowHtml"):
        assert "_gfxWarnUnnormalized" in _fn_body(fn), f"{fn} does not warn"


# --- 7. required elements ---------------------------------------------------

def test_row_carries_rank_name_grade_and_club():
    body = _fn_body("_gfxListRowHtml")
    assert "rank" in body
    assert "r.name" in body
    assert "fv-badge" in body
    assert "_gfxTeamLogo" in body


def test_tile_carries_rank_name_grade_and_meta():
    body = _fn_body("_gfxTileHtml")
    assert "rank" in body
    assert "r.name" in body
    assert "fv-badge" in body
    assert "r.meta" in body


def test_list_layouts_carry_no_surplus_or_dvm():
    """The value column went with the redesign and must not creep back."""
    for fn in ("_gfxListRowHtml", "_gfxTileHtml"):
        body = _fn_body(fn)
        for banned in ("r.value", "r.valueSub", "r.dvm", "DvM"):
            assert banned not in body, f"{fn} reintroduced {banned}"


# --- 8. the aspect the format label promises --------------------------------

def test_board_overflow_is_disclosed_not_silent():
    """min-height only means a long list extends past the stated aspect."""
    board = _fn_body("buildGfxBoard")
    assert "layoutOverflow" in board, (
        "the overflow disclosure is gone; a board that does not fit its format "
        "will quietly hand back a PNG whose aspect the label lies about")
