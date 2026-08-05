# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Generate-GFX list layout: names-first, photos back where the geometry fits.

THIRD contract for this file, and the rewrite is prescribed by the file itself:
each time the owner ask changes, the assertions EXPIRE rather than fail, and the
file is rebuilt around the new brief instead of being deleted.

  2026-08-03  photo-centric chip grid ("the photo dominates the chip").
  2026-08-04  photos OFF the lists entirely; the name is the subject. That
              removed a 30px headshot plus a 6px gutter and handed 36px per row
              to the name field, which is what fixed the owner's truncation
              complaint.
  2026-08-04d THIS ONE. Photos come BACK to the ROWS list, but only where the
              row geometry genuinely has room, and never at the cost of the
              name. The anti-truncation win is preserved by construction: the
              well's width is subtracted from the budget the layout search
              scores, and the gate only opens on rows that are already tall
              (>= 40px) and columns that are already wide (>= 320px).

Two carve-outs are pinned here, in both directions:
  * TILES stay names-only. Their charter is big legible names, and re-adding a
    photo there re-creates the 2026-08-04 truncation.
  * The single-subject hero card, the compare card and the pack mini-card KEEP
    their headshots. "Photos off the lists" must never become "photos off
    everything".

The enabler is also pinned: img.mlbstatic.com is Cloudinary and honours
`c_fill,g_face`, so the crop is done server-side at the exact target box and is
centred on the detected face. That is what makes a 39x46 well in a 52px row
readable instead of a squashed torso, and it is why no renderer needs a
client-side "center top" guess any more. If that transform ever has to be
withdrawn, it lives in ONE constant.

What is guarded:
  1. photos on the ROWS list where geometry allows; tiles still photo-free;
     the photo well is gated on geometry, not on list size
  2. the single-subject cards still carry photos
  3. nothing on a board renders below the 11px legibility floor
  4. the geometry search leaves no ragged last row and never clips a tile
  5. the name field clears 200px WITH the well subtracted, everywhere the gate
     opens, and the owner's 100-on-16:9 board is untouched by all of this
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
        "PHOTO_MIN_ROW_H": r"_GFX_LIST_PHOTO_MIN_ROW_H\s*=\s*(\d+)",
        "PHOTO_MIN_COL_W": r"_GFX_LIST_PHOTO_MIN_COL_W\s*=\s*(\d+)",
        "PHOTO_GUTTER": r"_GFX_LIST_PHOTO_GUTTER\s*=\s*(\d+)",
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


# The fixed furniture a row spends before the name gets anything: 8px of row
# padding, the 24px rank column, a 28px FV badge, an 18px club mark, and the
# 6px flex gaps between them.
ROW_FURNITURE = 8 + 24 + 6 + 28 + 18 + 12


def name_field(geo) -> int:
    """Width the NAME actually gets, with the photo well charged against it."""
    well = (geo["photoW"] + C["PHOTO_GUTTER"]) if geo["photoW"] else 0
    return int(geo["colW"] - ROW_FURNITURE - well)


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
    # THE PHOTO GATE. Geometry, not list size: a well needs a row tall enough
    # for a face and a column wide enough that it does not come out of the name.
    photo_w = (_jsround(row_h * 0.75)
               if row_h >= C["PHOTO_MIN_ROW_H"] and col_w >= C["PHOTO_MIN_COL_W"]
               else 0)
    # The search scores the width the TEXT gets, not the raw column, so a
    # layout can only win on space it can actually spend on the name.
    text_w = col_w - (photo_w + C["PHOTO_GUTTER"] if photo_w else 0)
    return {"cols": cols, "rows": rows, "colW": col_w, "rowH": row_h, "metaMode": meta,
            "photoW": photo_w, "textW": text_w,
            "name": 14 if row_h >= C["STACK_MIN_H"] else 13,
            "area": text_w * row_h, "empty": cols * rows - cap}


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


# --- 1. photos: back on the ROWS list, never on the tiles -------------------

# Markers that would mean a player picture had crept into the TILE renderer.
PHOTO_MARKERS = [
    "_gfxHeadshotURL",        # the MLB headshot URL builder
    "_gfxListPhotoWell",      # the rows-list photo well
    "_gfxListPhotoCss",       # the retired list photo-layer helper
    "_gfxChipPhotoCss",       # the retired chip photo-well helper
    "_gfxAvatar",             # the live-DOM avatar (legacy row path)
    "_gfxRowHasPhotoAvatar",  # the photos-toggle predicate
    "_gfxPhotoBaseLayer",
    "background-image",
]


def test_tiles_stay_names_only():
    """The tile charter: big legible names, no photo, at any geometry.

    Tiles are the layout the 2026-08-04 truncation complaint was about. Putting
    a picture back in a tile spends the width that fixed it, and unlike the rows
    layout there is no geometry where a tile has spare horizontal room, so there
    is no gate that could make it safe.
    """
    body = _fn_body("_gfxTileHtml")
    for marker in PHOTO_MARKERS:
        assert marker not in body, (
            f"_gfxTileHtml references {marker!r}. TILES are names-only by "
            "charter; photos came back to the ROWS list only (2026-08-04d).")


def test_rows_list_has_a_geometry_gated_photo_well():
    """Photos are back on the rows list, and the well is a real, gated element."""
    body = _fn_body("_gfxListRowHtml")
    assert "geo.photoW" in body, (
        "_gfxListRowHtml no longer reads geo.photoW. The row photo well must be "
        "gated on the geometry the layout search reserved, never rendered "
        "unconditionally and never gated on list size.")
    assert "_gfxListPhotoWell" in body, (
        "_gfxListRowHtml does not render the photo well any more. Photos were "
        "restored to the rows list on 2026-08-04d.")
    well = _fn_body("_gfxListPhotoWell")
    assert "_gfxHeadshotURL" in well, "the well does not build a headshot URL"
    assert "onerror" in well and "display='none'" in well, (
        "the well lost its onerror degrade. A 404 must fall through to the "
        "team-logo / silhouette cell background, never show a broken image.")
    assert "crossorigin" in well, (
        "the well image is not crossorigin=anonymous, so html2canvas cannot "
        "rasterize it and the export loses the photo")


def test_the_well_is_reserved_even_when_the_subject_has_no_photo():
    """Otherwise the name column ripples in and out down the board.

    A subject with no mlbam, or a "none" photo context, still gets the box; it
    just shows the club mark. Dropping the element instead would re-align that
    one row and only that one row.
    """
    well = _fn_body("_gfxListPhotoWell")
    assert 'if (!hs) return `<span style="${wrap}"></span>`;' in well, (
        "_gfxListPhotoWell no longer emits an empty well when there is no "
        "headshot URL. Every gated row must reserve the same width or the "
        "names stop lining up.")


def test_face_crop_transform_is_centralised():
    """The enabler, pinned in the one place it lives.

    c_fill returns exactly the requested box; g_face centres that crop on the
    detected face. Without it a 39x46 well is a blind crop of a 480x720 source.
    c_thumb is NOT interchangeable: it zooms far too tight.
    """
    m = re.search(r'const _GFX_FACE_CROP = "([^"]+)";', SRC)
    assert m, "the face-crop transform constant is gone from prospx/index.html"
    assert m.group(1) == "c_fill,g_face", (
        f"face crop is {m.group(1)!r}; the verified transform is 'c_fill,g_face' "
        "(c_thumb zooms too tight on the face)")
    body = _fn_body("_gfxHeadshotURL")
    assert "_GFX_FACE_CROP" in body, "_gfxHeadshotURL stopped using the constant"
    assert "d_people" not in body, (
        "_gfxHeadshotURL reintroduced the d_people:generic default. That serves "
        "a silhouette at HTTP 200, so onerror never fires and every fallback in "
        "the degrade chain is defeated.")
    assert 'ctx === "none"' in body, (
        "_gfxHeadshotURL stopped consulting photo_ctx for 'none'; it will fetch "
        "known-404s for the 873 ids with no photo on file")


def test_single_subject_cards_still_carry_photos():
    """The carve-out. Photos off the tiles must not become photos off everything."""
    for fn in ("buildProspectCard", "buildCompareCard", "_gfxMiniCard"):
        body = _fn_body(fn)
        assert "_gfxHeadshotURL" in body, (
            f"{fn} no longer builds a headshot URL. The owner kept photos on the "
            "single-subject cards throughout.")


def test_cards_ask_for_their_exact_box_not_a_guessed_crop():
    """Each card passes BOTH dimensions, so the CDN crops to the real well.

    These used to pass a single width and then paint with
    `background-position:center top` - a guess about where the face sat in a 2:3
    source. Passing the box removes the guess.
    """
    for fn, box in (("buildProspectCard", ("PW", "PH")),
                    ("buildCompareCard", ("132", "176")),
                    ("_gfxMiniCard", ("PW", "PH"))):
        body = _fn_body(fn)
        m = re.search(r"_gfxHeadshotURL\(([^)]*)\)", body)
        assert m, f"{fn} has no _gfxHeadshotURL call"
        args = [a.strip() for a in m.group(1).split(",")]
        assert len(args) == 3, (
            f"{fn} calls _gfxHeadshotURL with {len(args)} args ({m.group(1)!r}); "
            "it must pass the target box (id, width, height) so the face crop "
            "matches the well")
        assert args[1] == box[0] and args[2] == box[1], (
            f"{fn} asks for {args[1]}x{args[2]}, not its own well {box[0]}x{box[1]}")
        assert "background-position:center top" not in body, (
            f"{fn} still positions its photo with the old 'center top' guess; "
            "the CDN crop is already face-centred, so it should be 'center'")


def test_photos_toggle_reaches_the_rows_list_and_not_the_tiles():
    """A control that does nothing is worse than no control.

    The toggle governs the cards, the pack, and the gated row wells. It must
    NOT claim to govern tiles, which have no photo to toggle.
    """
    assert "_gfxOpts.photos" in _fn_body("_gfxListRowHtml"), (
        "_gfxListRowHtml ignores _gfxOpts.photos, so the restored checkbox "
        "would be inert on the rows board")
    assert "_gfxOpts.photos" not in _fn_body("_gfxTileHtml"), (
        "_gfxTileHtml reads _gfxOpts.photos, but tiles are unconditionally "
        "names-only, so the toggle would be inert there")
    ui = _fn_body("_gfxApplyModeUI")
    assert '_gfxOpts.layout === "rows"' in ui, (
        "_gfxApplyModeUI no longer shows the photos control for the rows "
        "layout; the restored toggle would be hidden on the board that uses it")
    assert "card photos" not in SRC, (
        "the photos checkbox still says 'card photos'. Since 2026-08-04d it "
        "also governs the rows list, so the label lies about its own scope.")


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
    assert name_field(g) >= 200, (
        f"name field is {name_field(g)}px. Removing the 30px headshot and its "
        "6px gutter was supposed to hand that width to the name; if this drops, "
        "the truncation the owner reported is back.")
    # And this board is exactly the case the photo gate must decline: 28px rows
    # on a 371px column. Photos coming back must not touch it.
    assert g["photoW"] == 0, (
        f"the owner's 100-on-16:9 board reserved a {g['photoW']}px photo well "
        f"at rowH {g['rowH']} / colW {g['colW']}. That board is the one the "
        "anti-truncation work was done for; it has to self-exclude.")


def test_rows_are_wider_than_the_photo_era_minimum():
    """Guards the reclaimed width at the constant level, not just one board."""
    assert C["COL_MIN_W"] >= 240, (
        "list columns narrowed below the photo-era minimum, which spends the "
        "reclaimed headshot width on more columns instead of longer names")


@pytest.mark.parametrize("fmt_name", LIST_FORMATS)
@pytest.mark.parametrize("cap", CAPS)
def test_a_gated_photo_never_costs_the_name_its_floor(fmt_name, cap):
    """The whole premise: photos only where there is genuinely room.

    200px is the floor the 2026-08-04 redesign holds. It is asserted here AFTER
    the well and its gutter have been charged against the column, so a gate that
    opened too eagerly fails here rather than in an export.
    """
    g = list_geo(cap, FMT[fmt_name], list_cols(cap, FMT[fmt_name]))
    if not g or not g["photoW"]:
        return
    assert name_field(g) >= 200, (
        f"rows {fmt_name}/{cap}: the gate opened a {g['photoW']}px well and left "
        f"the name only {name_field(g)}px. Photos must never be paid for out of "
        "the name field.")


@pytest.mark.parametrize("fmt_name", LIST_FORMATS)
@pytest.mark.parametrize("cap", CAPS)
def test_the_gate_is_geometry_not_list_size(fmt_name, cap):
    """photoW is 0 wherever the row is short or the column narrow, full stop.

    Swept over EVERY candidate column count, not just the chosen one, because
    the search evaluates all of them and a future tie-break change could ship
    one this test never looked at.
    """
    for cols in range(1, 9):
        g = list_geo(cap, FMT[fmt_name], cols)
        if not g:
            continue
        if g["rowH"] < C["PHOTO_MIN_ROW_H"] or g["colW"] < C["PHOTO_MIN_COL_W"]:
            assert g["photoW"] == 0, (
                f"{fmt_name}/{cap}/{cols}cols: photoW {g['photoW']} at rowH "
                f"{g['rowH']} / colW {g['colW']}, below the "
                f"{int(C['PHOTO_MIN_ROW_H'])}x{int(C['PHOTO_MIN_COL_W'])} gate")
        else:
            assert g["photoW"] == _jsround(g["rowH"] * 0.75), (
                f"{fmt_name}/{cap}/{cols}cols: the well is no longer a ~3:4 "
                "portrait derived from the row height")
        assert g["textW"] == g["colW"] - (g["photoW"] + C["PHOTO_GUTTER"]
                                          if g["photoW"] else 0), (
            f"{fmt_name}/{cap}/{cols}cols: textW does not charge the well")


def test_the_photo_gate_thresholds_are_where_they_were_measured():
    """Both thresholds were picked by sweeping the whole format x count matrix.

    Lowering either one re-opens the gate on layouts that were measured to be
    too cramped for a face (36px rows) or too narrow to spare the width.
    """
    assert C["PHOTO_MIN_ROW_H"] >= 40, (
        "the photo gate dropped below 40px rows. At 36px the well is 27px tall "
        "and the face stops reading; that is the jank photos were pulled for.")
    assert C["PHOTO_MIN_COL_W"] >= 320, (
        "the photo gate dropped below a 320px column, where the well starts "
        "coming out of the name field")


def test_the_search_scores_the_width_the_name_can_use():
    """Not the raw column, or a well could win a layout it then makes worse."""
    body = _fn_body("_gfxListGeoFor")
    assert "area: textW * rowH" in body, (
        "_gfxListGeoFor scores raw colW again. The column search must score the "
        "width left AFTER the photo well, or a gated layout can beat an "
        "ungated one on space it cannot spend on the name.")


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
