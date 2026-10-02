# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""pixel_icons.py - the pixel icon set (final-pass plan section 5.7, PX-01).

The ICONS table below is the source of truth for every drawing. It moved here
from the 2026-09-24 design bundle (_finalpass_2026-09-24/pixelart/synthesis/src/
icons_src.py) unchanged, so the sprite this writes is the prototype the owner
answered (PX-Q1, Scorebook ink in 2 px stems).

Writes assets/ and branding/ only, never data/ (pytest reverts data/ writes):
    assets/eephus-icons.svg                one sprite, one <symbol id="i-<key>"> per icon
    assets/eephus-icons.json               the same bitmaps for a canvas painter
    branding/pixel/icons-sheet-light.png   review sheet, light newsprint
    branding/pixel/icons-sheet-dark.png    review sheet, dark refractor

The grid: every icon is drawn on a 12 x 12 CORE and placed at (2,2) inside a
16 x 16 <symbol>, so the 12 px menu crop (viewBox "2 2 12 12") is the same
drawing. Stroke rule from PixelMplus12 Bold: vertical stems 2 px wide,
horizontal rules 1 px tall, masses solid, diagonals step one row per row.
In the rows, '#' is ink (currentColor), '+' the one accent group
(var(--ico-accent,currentColor)) and '.' is off. Rows may be fewer than 12;
the drawing is centred in the core (floor).

Every <symbol> carries fill="currentColor" and shape-rendering="crispEdges"
itself, so an external <use> still paints in ink when a consumer forgets the
.ico rule. The sprite has no comments and no trailing newline: a double hyphen
inside a comment is not well-formed XML, and a one-line file with no line end
is byte-identical on every checkout whatever core.autocrlf does.

Usage:
    python tools/pixel_icons.py                write the sprite, the json and both sheets
    python tools/pixel_icons.py --check        exit 1 when the committed sprite or json is stale
    python tools/pixel_icons.py --show KEY...  print the 16 x 16 grid of each key
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPRITE = ROOT / "assets" / "eephus-icons.svg"
BITMAPS = ROOT / "assets" / "eephus-icons.json"
SHEET_DIR = ROOT / "branding" / "pixel"

CORE, OFF, BOX = 12, 2, 16
ACCENT_STYLE = "fill:var(--ico-accent,currentColor)"

# (key, label, group, rows). key = the NAV_ITEMS key where one exists.
ICONS = [
    # top-nav leaves
    ("home", "Home", "nav", [
        ".##########.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".###....###.",
        "..###..###..",
        "...######...",
        "....####....",
        ".....##....."]),
    ("prospx", "PROSPX", "nav", [
        ".##########.",
        ".##......##.",
        ".##..++..##.",
        ".##.++++.##.",
        ".##..++..##.",
        ".##.++++.##.",
        ".##.++++.##.",
        ".##......##.",
        ".##.####.##.",
        ".##......##.",
        ".##.##...##.",
        ".##########."]),
    ("collegesavant", "CollegeSavant", "nav", [
        "...######...",
        ".##......##.",
        "##...++...##",
        "##...++...##",
        "##++++++++##",
        "##.++++++.##",
        "##..++++..##",
        "##..+..+..##",
        "##.+....+.##",
        ".##......##.",
        "...######..."]),
    ("franchise", "Franchise", "mlb", [
        "....++++....",
        "....++++....",
        ".....##.....",
        ".....##.....",
        ".##########.",
        ".##......##.",
        ".##......##.",
        "####....####",
        "#..#....#..#",
        "####....####"]),
    ("fa", "Free Agency", "mlb", [
        ".....##.....",
        "...######...",
        "..##.##.##..",
        "..##.##.....",
        "...#####....",
        "....######..",
        ".....##.##..",
        "..##.##.##..",
        "...######...",
        ".....##....."]),
    ("projections", "Projections", "mlb", [
        ".....##.....",
        ".....##.....",
        "....####....",
        "....####....",
        "...##..##...",
        "...##..##...",
        "..##.++.##..",
        "..##.++.##..",
        ".##......##.",
        ".##......##.",
        "############",
        "############"]),
    ("mlbstats", "MLB Stats", "mlb", [
        "############",
        "##..#..#..##",
        "##..#..#++##",
        "############",
        "##..#..#..##",
        "##..#..#..##",
        "############",
        "##..#..#..##",
        "##..#..#..##",
        "############"]),
    ("pal", "Alchemy Lab", "mlb", [
        "..########..",
        "...##..##...",
        "...##..##...",
        "...##..##...",
        "..##....##..",
        ".##......##.",
        "##........##",
        "##+.+.+.+.##",
        "##.+.+.+.+##",
        "##+.+.+.+.##",
        "############"]),
    ("trademachine", "Trade Machine", "mlb", [
        "........#...",
        "........##..",
        "###########.",
        "###########.",
        "........##..",
        "........#...",
        "...#........",
        "..##........",
        ".###########",
        ".###########",
        "..##........",
        "...#........"]),
    ("arbitration", "Arbitration", "mlb", [
        ".....++.....",
        "############",
        ".#...##...#.",
        ".#...##...#.",
        "#.#..##..#.#",
        "###..##..###",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        "...######...",
        "..########.."]),
    ("ledger", "Club Ledger", "mlb", [
        "############",
        "###.......##",
        "###.####..##",
        "###.......##",
        "###.#####.##",
        "###.......##",
        "###.###...##",
        "###.......##",
        "###.+++++.##",
        "###.......##",
        "###.+++++.##",
        "############"]),
    ("management", "In-Game Management", "mlb", [
        "##..........",
        "##++++++++..",
        "##+++++++...",
        "##++++++....",
        "##+++++++...",
        "##++++++++..",
        "##..........",
        "##..........",
        "##..........",
        "##..........",
        "####........",
        "####........"]),
    ("hof", "Hall of Fame", "mlb", [
        ".....++.....",
        "...######...",
        ".##########.",
        "############",
        "............",
        ".##..##..##.",
        ".##..##..##.",
        ".##..##..##.",
        ".##..##..##.",
        "............",
        ".##########.",
        "############"]),
    ("fantasy", "Fantasy", "diamond", [
        ".....##.....",
        "....####....",
        "...##..##...",
        "..##.++.##..",
        ".##.++++.##.",
        "##.++++++.##",
        "##.++++++.##",
        ".##.++++.##.",
        "..##.++.##..",
        "...##..##...",
        "....####....",
        ".....##....."]),
    ("betting", "Sports Betting", "diamond", [
        "############",
        "##..#.....##",
        "##....###.##",
        ".#..#.....#.",
        "..#...##.#..",
        "..#.#....#..",
        ".#....###.#.",
        "##..#.....##",
        "##........##",
        "############"]),
    ("diamond", "Diamond Pass", "diamond", [
        ".....##.....",
        "....####....",
        "...######...",
        "..########..",
        ".##########.",
        "############",
        "############",
        ".##########.",
        "..########..",
        "...######...",
        "....####....",
        ".....##....."]),
    ("articles", "Articles", "nav", [
        "...#########",
        "..#######.##",
        ".########.##",
        ".########.##",
        "..#######.##",
        "....#####.##",
        ".......##.##",
        ".......##.##",
        ".......##.##",
        ".......##.##",
        ".......##.##",
        "......###.##"]),
    ("forums", "Forums", "nav", [
        "############",
        "##........##",
        "##.++..++.##",
        "##.++..++.##",
        "##..+...+.##",
        "##........##",
        "############",
        "..###.......",
        "..##........",
        "..#........."]),
    ("glossary", "Glossary", "nav", [
        "...######...",
        "..##....##..",
        "..##........",
        "...####.....",
        "..##..###...",
        "..##....##..",
        "...###..##..",
        ".....####...",
        "........##..",
        "..##....##..",
        "...######..."]),
    ("team", "Developers", "nav", [
        "############",
        "############",
        "##........##",
        "##.##.....##",
        "##..##....##",
        "##...##...##",
        "##..##....##",
        "##.##.+++.##",
        "##........##",
        "############"]),
    # footer-only routes
    ("models", "Model Accountability", "footer", [
        "..........##",
        ".........##.",
        "........##..",
        ".......##...",
        "##....##....",
        ".##..##.....",
        "..####......",
        "...##.......",
        "............",
        "############",
        "#.+.#.+.#.+#"]),
    ("parks", "MiLB Park Factors", "footer", [
        "....####....",
        "..##....##..",
        ".#........#.",
        "##........##",
        "##........##",
        ".##......##.",
        "..##....##..",
        "...##++##...",
        "....#++#....",
        ".....##....."]),
    ("news", "Prospect News", "footer", [
        "#######.....",
        "##.....#....",
        "##.++++.#...",
        "##.......###",
        "##.###.##.##",
        "##.###....##",
        "##.###.##.##",
        "##........##",
        "##.######.##",
        "##........##",
        "############"]),
    ("history", "Today in Prospect History", "footer", [
        "..#......#..",
        "############",
        "############",
        "##........##",
        "##.#.#.#..##",
        "##........##",
        "##.#.++.#.##",
        "##...++...##",
        "##.#.#.#..##",
        "##........##",
        "############"]),
    # PROSPX tabs + Watchlist
    ("px-prospects", "MiLB Prospects", "prospx", [
        "++.#########",
        "............",
        "##.########.",
        "............",
        "##.#######..",
        "............",
        "##.########.",
        "............",
        "##.######..."]),
    ("px-spotlights", "Spotlights", "prospx", [
        "############",
        "##++.++.++##",
        "##++.++.++##",
        "############",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        ".....##.....",
        "...######...",
        "..########.."]),
    ("px-farm", "Farm Systems", "prospx", [
        ".....##.....",
        "...##..##...",
        ".##......##.",
        "##...++...##",
        "##...++...##",
        "##........##",
        "##.######.##",
        "##.#.##.#.##",
        "##.##..##.##",
        "##.#.##.#.##",
        "############"]),
    ("px-transactions", "Transactions", "prospx", [
        "......######",
        "......##..##",
        "..+...##..##",
        "..++..##..##",
        "+++++++#..##",
        "+++++++#..##",
        "..++..##..##",
        "..+...##..##",
        "......##..##",
        "......######"]),
    ("px-il", "Injured List", "prospx", [
        "...######...",
        "...#....#...",
        "############",
        "##........##",
        "##...++...##",
        "##.++++++.##",
        "##.++++++.##",
        "##...++...##",
        "##........##",
        "############"]),
    ("px-leaderboards", "Leaderboards", "prospx", [
        "....++++....",
        "....++++....",
        "....++++....",
        "....++++....",
        "....++++.###",
        "###.++++.###",
        "###.++++.###",
        "###.++++.###",
        "###.++++.###"]),
    ("px-debuted", "Debuted", "prospx", [
        ".....++.....",
        "...######...",
        "..##.#####..",
        ".##..######.",
        ".##.#######.",
        "############",
        "############",
        ".......#####"]),
    ("px-draft", "MLB Draft/HS", "prospx", [
        ".....##.....",
        "...######...",
        ".##########.",
        "############",
        ".##########+",
        "...######..+",
        "...######..+",
        "...######.++",
        "...######.++"]),
    ("px-intl", "International Amateurs", "prospx", [
        "...######...",
        ".##..##..##.",
        "##..#..#..##",
        "##..#..#..##",
        "############",
        "##..#..#..##",
        "##..#..#..##",
        "############",
        "##..#..#..##",
        ".##..##..##.",
        "...######..."]),
    ("px-overseas", "Overseas", "prospx", [
        ".....##.....",
        ".....##.....",
        "....####....",
        "...######...",
        ".##########.",
        "############",
        "##...##...##",
        ".....##.....",
        ".....##.....",
        "....####....",
        "...######..."]),
    ("px-timemachine", "Time Machine", "prospx", [
        "############",
        ".##......##.",
        "..##++++##..",
        "...##++##...",
        "....####....",
        ".....##.....",
        "....#..#....",
        "...##..##...",
        "..##.++.##..",
        ".##++++++##.",
        "############"]),
    ("px-scatter", "Scatterplots", "prospx", [
        "##..........",
        "##......++..",
        "##......++..",
        "##..........",
        "##...++..++.",
        "##...++..++.",
        "##..........",
        "##.++.......",
        "##.++.......",
        "##..........",
        "############"]),
    ("watchlist", "Watchlist", "prospx", [
        ".....##.....",
        ".....##.....",
        "....####....",
        "############",
        ".##########.",
        "..########..",
        "...######...",
        "...######...",
        "..###..###..",
        "..##....##..",
        ".##......##."]),
    # optional sections
    ("li", "Leverage Index", "optional", [
        "..##........",
        ".####.......",
        "######......",
        "..##....##..",
        "..##....##..",
        "..##....##..",
        "..##....##..",
        "..##....##..",
        "..##..######",
        "..##...####.",
        "..##....##.."]),
    ("defense", "Defense", "optional", [
        ".....##.....",
        ".....##.....",
        "..###..###..",
        "..#......#..",
        "..#......#..",
        "###..++..###",
        "###..++..###",
        "..#......#..",
        "..#......#..",
        "..###..###..",
        ".....##.....",
        ".....##....."]),
    ("dynasty", "Dynasty", "optional", [
        "##...##...##",
        "##..####..##",
        "###.####.###",
        "############",
        "############",
        "############",
        "............",
        "++++++++++++"]),
    ("redraft", "Redraft", "optional", [
        "...######.#.",
        ".##......###",
        "##......####",
        "##..........",
        "##..........",
        "..........##",
        "..........##",
        "####......##",
        "###......##.",
        ".#.######..."]),
    ("dfs", "DFS", "optional", [
        "....####....",
        ".....##.....",
        "...######.#.",
        ".##......###",
        "##...##...##",
        "##...##...##",
        "##...+++..##",
        "##........##",
        ".##......##.",
        "...######..."]),
    # nav controls (PX-22, owner answer PX-Q2)
    ("search", "Search (Ctrl+K)", "control", [
        "..######....",
        ".##....##...",
        "##......##..",
        "##......##..",
        "##......##..",
        ".##....##...",
        "..######....",
        ".......###..",
        "........###.",
        ".........###"]),
    ("theme-dark", "Theme: switch to dark", "control", [
        "...#####....",
        ".####.......",
        "###.........",
        "###.........",
        "###.........",
        "###.......##",
        ".###.....##.",
        "..#########.",
        "....#####..."]),
    ("theme-light", "Theme: switch to light", "control", [
        ".....##.....",
        ".#...##...#.",
        "..#......#..",
        "....####....",
        "...######...",
        "##.######.##",
        "...######...",
        "....####....",
        "..#......#..",
        ".#...##...#.",
        ".....##....."]),
    # wire event pictograms
    ("ev-up", "FV up", "wire", [
        ".....##.....",
        "....####....",
        "...######...",
        "..########..",
        ".##########.",
        "############"]),
    ("ev-down", "FV down", "wire", [
        "############",
        ".##########.",
        "..########..",
        "...######...",
        "....####....",
        ".....##....."]),
    ("ev-promo", "Promotion", "wire", [
        ".....##.....",
        "....####....",
        "...##..##...",
        "..##....##..",
        ".....##.....",
        "....####....",
        "...##..##...",
        "..##....##.."]),
    ("ev-demo", "Demotion", "wire", [
        "..##....##..",
        "...##..##...",
        "....####....",
        ".....##.....",
        "..##....##..",
        "...##..##...",
        "....####....",
        ".....##....."]),
    ("ev-il", "Injured list", "wire", [
        "....####....",
        "....####....",
        "....####....",
        "############",
        "############",
        "############",
        "....####....",
        "....####....",
        "....####...."]),
    ("ev-signing", "Signing", "wire", [
        ".........##.",
        "........###.",
        ".......###..",
        "......###...",
        ".....###....",
        "....###.....",
        "...###......",
        "..##........",
        ".#..........",
        "............",
        "############"]),
    # The card-foil rarity sprite (PX-24, owner answer PX-Q1: CARD FOIL only on
    # the PROSPX player card and the FV key). One card outline, the PROSPX card
    # drawn empty, with one more foil corner per FV threshold the rank border
    # already uses (45, 50, 55, 61) and a centre stone at 70. The COUNT carries
    # the tier, so it reads without colour; the corners are the one accent
    # group. Keys name the threshold, never a tier word.
    ("fv-45", "FV 45+", "fv", [
        ".+++#######.",
        ".++......##.",
        ".++......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##########."]),
    ("fv-50", "FV 50+", "fv", [
        ".+++####+++.",
        ".++......++.",
        ".++......++.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##########."]),
    ("fv-55", "FV 55+", "fv", [
        ".+++####+++.",
        ".++......++.",
        ".++......++.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".++......##.",
        ".++......##.",
        ".+++#######."]),
    ("fv-61", "FV 61+", "fv", [
        ".+++####+++.",
        ".++......++.",
        ".++......++.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".##......##.",
        ".++......++.",
        ".++......++.",
        ".+++####+++."]),
    ("fv-70", "FV 70+", "fv", [
        ".+++####+++.",
        ".++......++.",
        ".++......++.",
        ".##......##.",
        ".##..++..##.",
        ".##.++++.##.",
        ".##.++++.##.",
        ".##..++..##.",
        ".##......##.",
        ".++......++.",
        ".++......++.",
        ".+++####+++."]),
]
# Aliases: one idea, one drawing, referenced by <use> inside the sprite.
ALIASES = [
    ("ev-debut", "Debut", "wire", "px-debuted"),
    ("ev-trade", "Trade", "wire", "trademachine"),
]


def centre(key: str, rows: list[str]) -> list[str]:
    """Place a drawing in the 12 x 12 core, centred on its lit bounding box."""
    assert all(len(r) == CORE for r in rows), (key, [len(r) for r in rows])
    assert len(rows) <= CORE, (key, len(rows))
    assert set("".join(rows)) <= set("#+."), key
    lit = [(x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c != "."]
    xs = [p[0] for p in lit]
    ys = [p[1] for p in lit]
    w = max(xs) - min(xs) + 1
    h = max(ys) - min(ys) + 1
    ox = (CORE - w) // 2 - min(xs)
    oy = (CORE - h) // 2 - min(ys)
    g = [["."] * CORE for _ in range(CORE)]
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c != ".":
                g[y + oy][x + ox] = c
    return ["".join(r) for r in g]


def rects(grid: list[str], ch: str) -> list[list[int]]:
    """Merge the cells of one colour into rectangles: runs per row, and a run
    that repeats on the next row at the same x and width grows downward."""
    open_: dict = {}
    out: list[list[int]] = []
    for y in range(CORE + 1):
        row = grid[y] if y < CORE else "." * CORE
        runs, x = [], 0
        while x < CORE:
            if row[x] == ch:
                s = x
                while x < CORE and row[x] == ch:
                    x += 1
                runs.append((s, x - s))
            else:
                x += 1
        nxt = {}
        for r in runs:
            if r in open_:
                open_[r][3] += 1
                nxt[r] = open_.pop(r)
            else:
                nxt[r] = [r[0], y, r[1], 1]
        out.extend(open_.values())
        open_ = nxt
    return out


def d_of(rs: list[list[int]]) -> str:
    return "".join(f"M{x + OFF} {y + OFF}h{n}v{h}h-{n}z"
                   for x, y, n, h in sorted(rs, key=lambda r: (r[1], r[0])))


def build() -> tuple[str, str, dict]:
    """Return (sprite text, bitmap json text, bitmaps) without writing."""
    syms: list[str] = []
    bits: dict = {}
    for key, label, group, rows in ICONS:
        assert key not in bits, key
        g = centre(key, rows)
        bits[key] = {"label": label, "group": group, "rows": g}
        ink, acc = d_of(rects(g, "#")), d_of(rects(g, "+"))
        body = (f'<path d="{ink}"/>' if ink else "") + (
            f'<path style="{ACCENT_STYLE}" d="{acc}"/>' if acc else "")
        syms.append(f'<symbol id="i-{key}" viewBox="0 0 {BOX} {BOX}" fill="currentColor" '
                    f'shape-rendering="crispEdges">{body}</symbol>')
    for key, label, group, ref in ALIASES:
        assert ref in bits and "alias" not in bits[ref], ref
        assert key not in bits, key
        bits[key] = {"label": label, "group": group, "alias": ref}
        syms.append(f'<symbol id="i-{key}" viewBox="0 0 {BOX} {BOX}" fill="currentColor" '
                    f'shape-rendering="crispEdges"><use href="#i-{ref}"/></symbol>')
    svg = '<svg xmlns="http://www.w3.org/2000/svg">' + "".join(syms) + "</svg>"
    ET.fromstring(svg)  # well-formed or raise
    assert "--" not in svg.replace("--ico-accent", ""), "double hyphen in the sprite"
    return svg, json.dumps(bits, separators=(",", ":")), bits


def rows_of(key: str, bits: dict) -> list[str]:
    b = bits[key]
    return bits[b["alias"]]["rows"] if "alias" in b else b["rows"]


def ascii_of(key: str, bits: dict) -> list[str]:
    pad = "." * BOX
    return [pad, pad] + [".." + r.replace("+", "#") + ".." for r in rows_of(key, bits)] + [pad, pad]


# Review sheets. PNG exports may carry raw hex (plan 5.7.1 line 5); these are
# the light and dark token values of assets/site.css at 2026-10-01.
THEMES = {
    "light": {"page": "#F4F0E6", "cell": "#FAF5E6", "ink": "#0F1B2D", "accent": "#6E56CF",
              "label": "#4A5468", "dim": "#6B6657", "rule": "#E2DCC9"},
    "dark": {"page": "#0C0C0E", "cell": "#1A1A1E", "ink": "#ECEEF2", "accent": "#9B8CFF",
             "label": "#A6ABB5", "dim": "#868A95", "rule": "#2B2B31"},
}
SHEET_COLS, CELL_W, CELL_H, PAD, SCALE = 7, 168, 76, 8, 3


def render_sheet(theme: str, bits: dict):
    """Every icon at the 12 px crop, 16 px and 32 px (core at 2x), ink plus the
    accent group, drawn cell by cell with integer rectangles, then scaled up by
    an integer factor with nearest-neighbour so no pixel is resampled."""
    from PIL import Image, ImageDraw, ImageFont

    t = THEMES[theme]
    keys = list(bits)
    nrows = -(-len(keys) // SHEET_COLS)
    head = 28
    w = PAD * 2 + SHEET_COLS * CELL_W
    h = PAD * 2 + head + nrows * CELL_H
    img = Image.new("RGB", (w, h), t["page"])
    dr = ImageDraw.Draw(img)
    dr.fontmode = "1"  # no antialiasing: the pixel face stays on whole pixels
    font_path = ROOT / "branding" / "fonts" / "PixelMplus12-Regular.ttf"
    bold_path = ROOT / "branding" / "fonts" / "PixelMplus12-Bold.ttf"
    font = ImageFont.truetype(str(font_path), 12)
    bold = ImageFont.truetype(str(bold_path), 12)
    dr.text((PAD, PAD + 4), f"eephus.io pixel icons, {len(keys)} symbols, 12 / 16 / 32 px, {theme}",
            font=bold, fill=t["ink"])

    def paint(rows, x0, y0, k, inset):
        for y, r in enumerate(rows):
            for x, c in enumerate(r):
                if c == ".":
                    continue
                col = t["ink"] if c == "#" else t["accent"]
                px, py = x0 + (x + inset) * k, y0 + (y + inset) * k
                dr.rectangle([px, py, px + k - 1, py + k - 1], fill=col)

    for i, key in enumerate(keys):
        cx = PAD + (i % SHEET_COLS) * CELL_W
        cy = PAD + head + (i // SHEET_COLS) * CELL_H
        dr.rectangle([cx, cy, cx + CELL_W - 1, cy + CELL_H - 1], fill=t["cell"], outline=t["rule"])
        rows = rows_of(key, bits)
        base = cy + 6 + 32  # icons sit on a shared baseline
        paint(rows, cx + 6, base - 12, 1, 0)          # 12 px: the core
        paint(rows, cx + 24, base - 16, 1, OFF)       # 16 px: core at (2,2)
        paint(rows, cx + 46, base - 32, 2, OFF)       # 32 px: the full box at 2x
        dr.text((cx + 6, cy + 42), bits[key]["label"][:26], font=font, fill=t["label"])
        dr.text((cx + 6, cy + 58), "i-" + key, font=font, fill=t["dim"])
    return img.resize((w * SCALE, h * SCALE), Image.NEAREST)


def write(sheets: bool = True) -> dict:
    svg, js, bits = build()
    SPRITE.write_bytes(svg.encode("utf-8"))
    BITMAPS.write_bytes(js.encode("utf-8"))
    print(f"  wrote {SPRITE.relative_to(ROOT).as_posix()} ({len(svg.encode('utf-8'))} B, {len(bits)} symbols)")
    print(f"  wrote {BITMAPS.relative_to(ROOT).as_posix()} ({len(js.encode('utf-8'))} B)")
    if sheets:
        SHEET_DIR.mkdir(parents=True, exist_ok=True)
        for theme in THEMES:
            out = SHEET_DIR / f"icons-sheet-{theme}.png"
            render_sheet(theme, bits).save(out, optimize=True)
            print(f"  wrote {out.relative_to(ROOT).as_posix()}")
    return bits


def stale() -> list[str]:
    """Committed outputs that differ from a fresh build (empty when current)."""
    svg, js, _ = build()
    out = []
    for path, want in ((SPRITE, svg), (BITMAPS, js)):
        if not path.exists() or path.read_bytes() != want.encode("utf-8"):
            out.append(path.relative_to(ROOT).as_posix())
    return out


def main(argv: list[str]) -> int:
    if "--check" in argv:
        bad = stale()
        for p in bad:
            print(f"  STALE {p}: run python tools/pixel_icons.py")
        return 1 if bad else 0
    if "--show" in argv:
        _, _, bits = build()
        for k in argv[argv.index("--show") + 1:]:
            print(k)
            print("\n".join(ascii_of(k, bits)))
        return 0
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
