# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""pixel_brand.py - render every eephus.io pixel mark from tools/pixel_brand_src.py.

Owner ask 2 (2026-09-30), Part 8 pixel_branding lane, BR-01 / PB-01. Moved
into the tree from the design bundle prototype (part8/branding/proposed/tools/).

Deterministic: the letters are sampled with fontTools PointInsidePen at cell
centres from the vendored branding/fonts/PixelMplus12-*.ttf (no system font),
no RNG, no anti-aliasing (every pixel is one flat colour, alpha 0 or 255),
integer scales only, and the share-card field is integer arithmetic so it does
not move with a Pillow or libm upgrade.

Writes ONLY these two folders, never data/ (the pytest-revert trap):
    assets/brand/     DOM fragments: wordmark-s2/s4/s6.svg (token-only, aria-hidden),
                      wordmark.css (classes and step-end motion), tokens.css (the
                      token block BR-02 moves into site.css); the favicon and
                      app-icon set (BR-04 / PB-04): favicon.ico (16/32/48, each an
                      exact strike), favicon.svg, favicon-16.png (the footer mark),
                      favicon-32.png, apple-touch-icon.png, icon-192.png,
                      icon-512.png, icon-maskable-512.png, and site.webmanifest
                      (the served manifest with its icons moved here)
    branding/pixel/   sheets and exported art: brand-sheet-{light,dark}.png,
                      glyphs.json (the sampled letters), wordmark PNG strikes,
                      share-default.png, og/<module>.png, marks/*.svg, eephus-arc.gif
The served pages read the icon set from assets/brand/ only when build_site.py's
PIXEL_BRAND flag is on (FAVICON_LINKS and the footer mark switch with it); the
served favicon.ico, assets/favicon.svg, favicon-16.png and favicon-32.png are
PX-23's copies of the same strikes. Behind the same flag build_site.py reads the
assets/brand wordmark fragments (BR-03), and assets/site.css carries
wordmark.css's rules; BR-05 to BR-09 swap in the rest.

    python tools/pixel_brand.py                   write into the repo
    python tools/pixel_brand.py --out DIR         same relative paths under DIR
    python tools/pixel_brand.py --check           regenerate into a temp folder and compare
                                                  (text byte for byte, images pixel for pixel)
    python tools/pixel_brand.py --style stepped   stepped (B, PB-Q1, default) | hinted (A) | lamps (C)
    python tools/pixel_brand.py --seams inward    inward ') (' (PB-Q2, default) | outward '( )'
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.ttLib import TTFont
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pixel_brand_src as SRC  # noqa: E402

ROOT = HERE.parent
TTF_BOLD = ROOT / "branding" / "fonts" / "PixelMplus12-Bold.ttf"
TTF_REG = ROOT / "branding" / "fonts" / "PixelMplus12-Regular.ttf"
ICONS_JSON = ROOT / "assets" / "eephus-icons.json"   # PX-01's bitmap table
OUT_DIRS = ("assets/brand", "branding/pixel")        # the only folders written
TEXT_SUFFIXES = (".svg", ".css", ".json", ".webmanifest")
MANIFEST = ROOT / "assets" / "site.webmanifest"      # the served manifest (BR-04 input)
STYLES = ("stepped", "hinted", "lamps")
SEAMS = ("inward", "outward")
U = 1000 / 12           # one font pixel in font units
Y0 = -1000 / 30         # the lattice sits 33.3 units under the baseline


# ============================================================== colour
def hx(h):
    if isinstance(h, tuple):
        return tuple(h[:3])
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix_pct(a, b, pct_a):
    """color-mix(in srgb, a pct_a%, b) as a browser computes it, rounded half up."""
    A, B = hx(a), hx(b)
    return "#%02X%02X%02X" % tuple((x * pct_a + y * (100 - pct_a) + 50) // 100 for x, y in zip(A, B))


def _seg(theme, t):
    """(index, fraction) of t inside the ramp's stop segments."""
    st = SRC.RAMP[theme]
    for i, ((t0, _), (t1, _)) in enumerate(zip(st, st[1:])):
        if t0 <= t <= t1 + 1e-9:
            return i, (t - t0) / (t1 - t0)
    return len(st) - 2, 1.0


def _pct(f):
    """The integer percentage of the LEFT stop, or None at a stop itself."""
    if f < .005 or f > .995:
        return None
    return round((1 - f) * 100)


def ramp_at(theme, t):
    """The ramp colour at t, exactly as the matching color-mix() token computes."""
    st = SRC.RAMP[theme]
    i, f = _seg(theme, t)
    p = _pct(f)
    if p is None:
        return st[i][1] if f < .5 else st[i + 1][1]
    return mix_pct(st[i][1], st[i + 1][1], p)


def _mix_css(theme, t):
    i, f = _seg(theme, t)
    p = _pct(f)
    if p is None:
        return f"var(--ramp-{i + 1 if f < .5 else i + 2})"
    return f"color-mix(in srgb, var(--ramp-{i + 1}) {p}%, var(--ramp-{i + 2}))"


def band_t(i):
    return (i + .5) / SRC.BANDS


def band_hex(theme):
    return [ramp_at(theme, band_t(i)) for i in range(SRC.BANDS)]


def tok(name, theme):
    return SRC.TOKENS[name][theme == "dark"]


def key_hex(key, theme):
    if key in ("ink", "k", "m", "s"):
        return tok("text-primary", theme)
    if key in ("dot", "glint"):
        return tok("logo-dot", theme)
    if key == "c":
        return SRC.BALL_FACE
    if key in ("C", "pxface"):
        return tok("bg-secondary", theme)
    if len(key) == 1 and key in "abde":
        stop = SRC.SEAM_STOPS[theme]["abde".index(key)]
        return SRC.RAMP[theme][min(stop, len(SRC.RAMP[theme])) - 1][1]
    if key.startswith("b") and key[1:].isdigit():
        return band_hex(theme)[int(key[1:])]
    if key.startswith("r:"):
        return ramp_at(theme, float(key[2:]))
    raise KeyError(key)


UNION = sorted({t for th in SRC.RAMP for t, _ in SRC.RAMP[th]})


def tokens_css():
    out = ["/* Generated by tools/pixel_brand.py from tools/pixel_brand_src.py. "
           "Every colour is an existing site.css stop or a color-mix of two. */"]
    for theme, sel in (("light", ":root"), ("dark", '[data-theme="dark"]')):
        st = SRC.RAMP[theme]
        L = [f"  --ramp-{i + 1}: {c};" for i, (_, c) in enumerate(st)]
        if len(st) < 5:
            L.append(f"  --ramp-5: var(--ramp-{len(st)});")
        L += [f"  --arc-{i + 1}: {_mix_css(theme, band_t(i))};" for i in range(SRC.BANDS)]
        L += [f"  --wm-g{i + 1}: {_mix_css(theme, t)};" for i, t in enumerate(UNION)]
        bands = ", ".join(f"var(--arc-{i + 1}) {round(i * 100 / SRC.BANDS, 1)}% {round((i + 1) * 100 / SRC.BANDS, 1)}%"
                          for i in range(SRC.BANDS))
        L.append(f"  --iridescent-steps: linear-gradient(90deg, {bands});")
        L.append(f"  --ball-face: {SRC.BALL_FACE};")
        L += [f"  --seam-{i + 1}: var(--ramp-{s});" for i, s in enumerate(SRC.SEAM_STOPS[theme])]
        out.append(sel + " {\n" + "\n".join(L) + "\n}")
    return "\n".join(out) + "\n"


def wordmark_css():
    """Classes and motion for the fragments (PB-Q4: pitch, replay, glint).

    The base style of every piece is its finished frame; an animation only hides
    or offsets it for a moment, so a browser that runs none of it shows the
    finished mark. step-end only (whole-pixel frames, no tweening), one
    iteration, no script. Hover replays on inner groups, so leaving the hover
    never replays. No reduced-motion rule: the site policy (owner, 2026-10-01,
    assets/site.css) runs every animation as it runs without the preference,
    and it supersedes PB-03's 'reduced motion stops everything'.
    """
    m = SRC.MOTION
    drop, fr = m["drop_ms"], m["glint_frame_ms"]
    fills = [".wm-px .wm-ink { fill: var(--text-primary); }",
             ".wm-px .wm-dot { fill: var(--logo-dot); }",
             ".wm-px .wm-k { fill: var(--text-primary); }",
             ".wm-px .wm-c { fill: var(--ball-face); }",
             ".wm-px .wm-a { fill: var(--seam-1); }",
             ".wm-px .wm-b { fill: var(--seam-2); }",
             ".wm-px .wm-d { fill: var(--seam-3); }",
             ".wm-px .wm-e { fill: var(--seam-4); }"]
    fills += [f".wm-px .wm-b{i} {{ fill: var(--arc-{i + 1}); }}" for i in range(SRC.BANDS)]
    drop_kf = ("{ 0% { opacity: 0; } 1% { opacity: 1; transform: translateY(calc(-2 * var(--u))); } "
               "34% { transform: translateY(calc(-1 * var(--u))); } 67% { transform: translateY(var(--nudge)); } }")
    css = [
        "/* Generated by tools/pixel_brand.py from tools/pixel_brand_src.py. */",
        ".eephus-wordmark-px { display: inline-block; position: relative; line-height: 0; margin: 0; }",
        ".eephus-wordmark-px .wm-txt { position: absolute; width: 1px; height: 1px; overflow: hidden; "
        "clip: rect(0 0 0 0); white-space: nowrap; }",
        ".wm-px { display: block; overflow: visible; shape-rendering: crispEdges; }",
        *fills,
        ".wm-px .wm-glint path { fill: var(--logo-dot); opacity: 0; }",
        "@keyframes wm-on { from { opacity: 0; } }",
        "@keyframes wm-on-h { from { opacity: 0; } }",
        "@keyframes wm-drop " + drop_kf,
        "@keyframes wm-drop-h " + drop_kf,
        "@keyframes wm-flash { from { opacity: 1; } to { opacity: 1; } }",
        ".wm-px--play .wm-s { animation: wm-on 1ms step-end backwards; "
        "animation-delay: calc(var(--i) * var(--step)); }",
        f".wm-px--play .wm-ball {{ animation: wm-drop {drop}ms step-end backwards; animation-delay: var(--drop-at); }}",
        f".wm-px--play .wm-glint .g1 {{ animation: wm-flash {fr}ms step-end var(--glint-at) 1; }}",
        f".wm-px--play .wm-glint .g2 {{ animation: wm-flash {fr}ms step-end calc(var(--glint-at) + {fr}ms) 1; }}",
        f".wm-px--play .wm-glint .g3 {{ animation: wm-flash {fr}ms step-end calc(var(--glint-at) + {2 * fr}ms) 1; }}",
        ".eephus-wordmark-px:hover .wm-h { animation: wm-on-h 1ms step-end backwards; "
        "animation-delay: calc(var(--i) * var(--step)); }",
        f".eephus-wordmark-px:hover .wm-bh {{ animation: wm-drop-h {drop}ms step-end backwards; "
        "animation-delay: var(--drop-at); }",
    ]
    return "\n".join(css) + "\n"


# ============================================================== glyphs
@lru_cache(maxsize=None)
def _font(path):
    f = TTFont(str(path))
    return f, f.getGlyphSet(), f.getBestCmap()


@lru_cache(maxsize=None)
def glyph(ch, bold=True):
    """The glyph's own bitmap: 12 rows (font rows 9 .. -2) sampled at cell centres."""
    f, gs, cmap = _font(TTF_BOLD if bold else TTF_REG)
    g = cmap[ord(ch)]
    cols = round(f["hmtx"][g][0] / U)
    rows = []
    for r in range(9, -3, -1):
        line = ""
        for c in range(cols):
            pen = PointInsidePen(gs, ((c + .5) * U, Y0 + (r + .5) * U))
            gs[g].draw(pen)
            line += "#" if pen.getResult() else "."
        rows.append(line)
    return tuple(rows)


def text_rows(s, bold=True, ls=0, dot_from=None):
    cells = [glyph(ch, bold) for ch in s]
    width = sum(len(c[0]) for c in cells) + ls * (len(cells) - 1)
    grid = [["."] * width for _ in range(12)]
    x = 0
    for i, cell in enumerate(cells):
        ch = "l" if (dot_from is not None and i >= dot_from) else "#"
        for y, row in enumerate(cell):
            for cx, v in enumerate(row):
                if v == "#":
                    grid[y][x + cx] = ch
        x += len(cell[0]) + ls
    return grid


def used_chars():
    """Every character each face draws, for glyphs.json."""
    bold = set(SRC.TEXT) | set(SRC.DEFAULT_CARD_TAG) | {c for _, t, _, _ in SRC.MODULES for c in t}
    reg = set("eephus.io") | {c for _, _, r, line in SRC.MODULES for c in r + line}
    reg |= {c for c in "".join(_SHEET_LABELS)}
    return "".join(sorted(bold)), "".join(sorted(reg))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def glyphs_json():
    bold, reg = used_chars()
    doc = {
        "about": "PixelMplus12 glyph bitmaps sampled at cell centres by tools/pixel_brand.py; "
                 "rows run font row 9 down to -2, '#' is ink.",
        "font_sha256": {"bold": _sha(TTF_BOLD), "regular": _sha(TTF_REG)},
        "bold": {c: list(glyph(c, True)) for c in bold},
        "regular": {c: list(glyph(c, False)) for c in reg},
    }
    return json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


# ============================================================== ball
def _circle(n, rim):
    c = n / 2.0
    r = n / 2.0 - SRC.CIRCLE_TRIM.get(n, SRC.CIRCLE_TRIM_DEFAULT)
    g = [["."] * n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            if (x + .5 - c) ** 2 + (y + .5 - c) ** 2 <= r * r:
                g[y][x] = "c"
    if rim == 1:
        edge = [(x, y) for y in range(n) for x in range(n) if g[y][x] == "c" and any(
            not (0 <= x + dx < n and 0 <= y + dy < n) or g[y + dy][x + dx] == "."
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        for x, y in edge:
            g[y][x] = "k"
        return g
    ri = r - rim
    for y in range(n):
        for x in range(n):
            if g[y][x] == "c" and (x + .5 - c) ** 2 + (y + .5 - c) ** 2 > ri * ri:
                g[y][x] = "k"
    return g


@lru_cache(maxsize=None)
def ball(n, seams=SRC.SEAMS):
    """The ball strike n px wide: k rim, c face, a/b left seam top/bottom, d/e right."""
    table = SRC.SEAM_COLS if seams == "inward" else SRC.SEAM_COLS_OUT
    rim = 2 if n >= SRC.RIM_2PX_FROM else 1
    g = _circle(n, rim)
    mid = (n - 1) / 2.0
    if n in table:
        for y, spec in table[n].items():
            x0, w = (spec, 1) if isinstance(spec, int) else spec
            for x in range(x0, x0 + w):
                assert g[y][x] == "c" and g[y][n - 1 - x] == "c", (n, y, x)
                top = y < mid
                g[y][x] = "a" if top else "b"
                g[y][n - 1 - x] = "d" if top else "e"
        return tuple("".join(r) for r in g)
    c = n / 2.0
    seam_w = next(w for lim, w in SRC.FALLBACK_SEAM_W if n <= lim)
    k_off, k_r = SRC.FALLBACK_SEAM_GEOM[seams]
    off, R = c * k_off, c * k_r
    cents = ((c - off, "L"), (c + off, "R")) if seams == "inward" else ((c + off, "L"), (c - off, "R"))
    for y in range(n):
        for x in range(n):
            if g[y][x] != "c":
                continue
            for cx, side in cents:
                if abs(math.hypot(x + .5 - cx, y + .5 - c) - R) <= seam_w / 2:
                    top = y + .5 < c
                    g[y][x] = ("a" if top else "b") if side == "L" else ("d" if top else "e")
    return tuple("".join(r) for r in g)


def pxmark():
    """The PROSPX mark, 22 x 22 (drawn at 2x and up only)."""
    n = SRC.PX_SIZE
    g = _circle(n, 1)
    for y, x in SRC.PX_SEAM.items():
        top = y < (n - 1) / 2
        stitch = y % 2 == 1
        g[y][x] = "s" if stitch else ("a" if top else "b")
        g[y][n - 1 - x] = "s" if stitch else ("d" if top else "e")
    for yy, row in enumerate(SRC.PX_P):
        for xx, v in enumerate(row):
            if v == "#":
                g[SRC.PX_TOP + yy][SRC.PX_P_AT + xx] = "m"
    ink = {(SRC.PX_X_AT + xx, SRC.PX_TOP + yy) for yy, row in enumerate(SRC.PX_X)
           for xx, v in enumerate(row) if v == "#"}
    for (x, y) in sorted(ink):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, y + dy)
            if q not in ink and g[q[1]][q[0]] in "mabdes":
                g[q[1]][q[0]] = "c"
    for (x, y) in ink:
        g[y][x] = "m"
    return tuple("".join(r).replace("c", "C") for r in g)   # C = the PROSPX face (--bg-secondary)


# ============================================================== lockup cells
def runs_cols(W, runs, end_row):
    """Column -> row and column -> run index for a symmetric stepped arc W wide."""
    col_row, run_of, x, row, k = {}, {}, 0, end_row, 0
    for n in runs:
        for _ in range(n):
            col_row[x] = col_row[W - 1 - x] = row
            run_of[x], run_of[W - 1 - x] = k, 2 * len(runs) - k
            x += 1
        row -= 1
        k += 1
    for xx in range(x, W - x):
        col_row[xx], run_of[xx] = row, len(runs)
    return col_row, run_of, 2 * len(runs) + 1


def lockup_cols():
    """Lockup width in u (odd, ink plus 1 u each side) and the letters' x offset."""
    grid = text_rows(SRC.TEXT, ls=SRC.LETTER_SPACING_U, dot_from=SRC.DOT_FROM)
    tw = len(grid[0])
    lit = [x for x in range(tw) if any(grid[y][x] != "." for y in range(12))]
    W = lit[-1] - lit[0] + 3
    W += (W % 2 == 0)
    return grid, W, 1 - lit[0]


def arc_grid(s):
    """(W2, cell px, col_row, run_of, runs) of the stepped arc at scale s."""
    _, W, _ = lockup_cols()
    if s >= 4 and s % 2 == 0:
        W2 = W * 2 if (W * 2) % 2 else W * 2 - 1
        col_row, run_of, nr = runs_cols(W2, SRC.HALF_RUNS, SRC.ARC_END_ROW * 2 + 1)
        return W2, s // 2, col_row, run_of, nr
    col_row, run_of, nr = runs_cols(W, SRC.ARC_RUNS, SRC.ARC_END_ROW)
    return W, s, col_row, run_of, nr


@lru_cache(maxsize=None)
def compose(s, style=SRC.STYLE, seams=SRC.SEAMS):
    grid, W, ox = lockup_cols()
    tw = len(grid[0])
    letters = {}
    for y in range(12):
        for x in range(tw):
            if grid[y][x] != ".":
                key = "ink" if grid[y][x] == "#" else "dot"
                for dy in range(s):
                    for dx in range(s):
                        letters[((x + ox) * s + dx, (SRC.BASE - 9 + y) * s + dy)] = (key, None)
    arc = {}
    Wpx = W * s
    if style == "hinted":
        t_px = max(2, round(s * .55))
        x0, x1 = .5 * s, Wpx - .5 * s
        ye, ya = (SRC.ARC_END_ROW + .5) * s, 2.5 * s
        cols = {}
        for px in range(Wpx):
            uu = max(-1.0, min(1.0, ((px + .5) - (x0 + x1) / 2) / ((x1 - x0) / 2)))
            top = int(math.floor(ya + (ye - ya) * uu * uu - t_px / 2 + .5))
            cols[px] = list(range(top, top + t_px))
        for px in range(1, Wpx):
            a, b = cols[px - 1], cols[px]
            if b[0] > a[-1] + 1:
                cols[px] = list(range(a[-1] + 1, b[-1] + 1))
            elif b[-1] < a[0] - 1:
                cols[px] = list(range(b[0], a[0]))
        groups = 12
        for px, ys in cols.items():
            for y in ys:
                arc[(px, y)] = ("r:%.4f" % (px / (Wpx - 1)), min(groups - 1, px * groups // Wpx))
    else:
        W2, h, col_row, run_of, nr = arc_grid(s)
        lamp = {gx: i for i, gx in enumerate(sorted(g for g in col_row if g % 2 == 0))}
        groups = len(lamp) if style == "lamps" else nr
        for gx, gy in col_row.items():
            if style == "lamps" and gx % 2:
                continue
            band = min(SRC.BANDS - 1, int(gx / (W2 - 1) * SRC.BANDS))
            grp = lamp[gx] if style == "lamps" else run_of[gx]
            for dy in range(h):
                for dx in range(h):
                    arc[(gx * h + dx, gy * h + dy)] = (f"b{band}", grp)
    n = SRC.BALL_FOR_SCALE[s]
    bx0, by0 = int(round(Wpx / 2 - n / 2)), int(round(2 * s - n / 2))
    balls = {(bx0 + x, by0 + y): (ch, None) for y, r in enumerate(ball(n, seams))
             for x, ch in enumerate(r) if ch != "."}
    return {"s": s, "style": style, "W": Wpx, "H": SRC.ROWS * s, "letters": letters, "arc": arc,
            "groups": groups, "ball": balls, "ball_box": (bx0, by0, n)}


def glint_frames(comp):
    s = comp["s"]
    x0, y0, n = comp["ball_box"]
    cx, cy = x0 - s, y0 + s
    dot = {(cx + dx, cy + dy) for dx in range(s) for dy in range(s)}
    plus = set(dot) | {(cx + ax * s + dx, cy + ay * s + dy) for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1))
                       for dx in range(s) for dy in range(s)}
    return [dot, plus, dot]


def timeline(comp):
    m = SRC.MOTION
    step = max(m["min_step_ms"], round(m["arc_ms"] / comp["groups"]))
    drop = comp["groups"] * step + m["drop_gap_ms"]
    return step, drop, max(1, round(comp["s"] / 3)), drop + m["glint_after_ms"]


# ============================================================== raster
def to_png(comp, theme, bg=None, pad=0, reveal=None, ball_dy=0, show_ball=True, glint=None):
    W, H = comp["W"] + 2 * pad, comp["H"] + 2 * pad
    im = Image.new("RGBA", (W, H), bg if bg is not None else (0, 0, 0, 0))
    px = im.load()
    cache = {}

    def put(x, y, key):
        if key not in cache:
            cache[key] = hx(key_hex(key, theme)) + (255,)
        if 0 <= x + pad < W and 0 <= y + pad < H:
            px[x + pad, y + pad] = cache[key]
    for (x, y), (k, g) in sorted(comp["arc"].items()):
        if reveal is None or g is None or g < reveal:
            put(x, y, k)
    for (x, y), (k, _) in sorted(comp["letters"].items()):
        put(x, y, k)
    if show_ball:
        for (x, y), (k, _) in sorted(comp["ball"].items()):
            put(x, y + ball_dy, k)
    for (x, y) in sorted(glint or ()):
        put(x, y, "glint")
    return im


def rows_png(rows, pal, scale=1, bg=None):
    n_w, n_h = len(rows[0]), len(rows)
    im = Image.new("RGBA", (n_w * scale, n_h * scale), bg if bg is not None else (0, 0, 0, 0))
    px = im.load()
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch == ".":
                continue
            col = hx(pal[ch]) + (255,)
            for dy in range(scale):
                for dx in range(scale):
                    px[x * scale + dx, y * scale + dy] = col
    return im


def ball_png(n, theme="light", scale=1, seams=SRC.SEAMS, bg=None):
    return rows_png(ball(n, seams), {k: key_hex(k, theme) for k in "kcabde"}, scale, bg)


def pxmark_png(theme="light", scale=2):
    assert scale >= SRC.PX_MIN_SCALE, "no P/X below 40 px"
    return rows_png(pxmark(), {k: key_hex(k, theme) for k in "kmsCabde"}, scale)


def favicon_strikes(seams=SRC.SEAMS):
    """{size: image} for favicon.ico: 16 and 32 are their own strikes, 48 is strike 24 at 2x."""
    return {16: ball_png(16, seams=seams), 32: ball_png(32, seams=seams), 48: ball_png(24, scale=2, seams=seams)}


# ============================================================== SVG
def _merge(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    open_, out = {}, []
    for y in range(h + 1):
        runs, x = [], 0
        while x < w:
            if (x0 + x, y0 + y) in pts and y < h:
                s0 = x
                while x < w and (x0 + x, y0 + y) in pts:
                    x += 1
                runs.append((s0, x - s0))
            else:
                x += 1
        nxt = {}
        for rr in runs:
            if rr in open_:
                open_[rr][3] += 1
                nxt[rr] = open_.pop(rr)
            else:
                nxt[rr] = [rr[0], y, rr[1], 1]
        out.extend(open_.values())
        open_ = nxt
    return "".join(f"M{x0 + x} {y0 + y}h{n}v{hh}h-{n}z" for x, y, n, hh in sorted(out, key=lambda r: (r[1], r[0])))


def _paths(cells, cls_of):
    by = {}
    for xy, (k, _) in cells.items():
        by.setdefault(cls_of(k), set()).add(xy)
    return [(c, _merge(p)) for c, p in sorted(by.items())]


def lockup_svg(comp, uid="wm", play=False, glint=False):
    """A DOM fragment: token-only (classes and var()), integer coordinates, aria-hidden."""
    step, drop, nudge, gl_at = timeline(comp)
    defs, arc = "", []
    if comp["style"] == "hinted":
        stops = "".join(f'<stop offset="{t}" style="stop-color:var(--wm-g{i + 1})"/>' for i, t in enumerate(UNION))
        defs = (f'<defs><linearGradient id="wmg-{uid}" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{comp["W"]}" '
                f'y2="0">{stops}</linearGradient></defs>')
    by_g = {}
    for xy, v in comp["arc"].items():
        by_g.setdefault(v[1], {})[xy] = v
    for g in sorted(by_g):
        if comp["style"] == "hinted":
            body = "".join(f'<path fill="url(#wmg-{uid})" d="{d}"/>' for _, d in _paths(by_g[g], lambda k: "arc"))
        else:
            body = "".join(f'<path class="wm-{c}" d="{d}"/>' for c, d in _paths(by_g[g], lambda k: k))
        arc.append(f'<g class="wm-s" style="--i:{g}"><g class="wm-h">{body}</g></g>')
    parts = ['<g class="wm-arc">' + "".join(arc) + "</g>"]
    parts += [f'<path class="wm-{c}" d="{d}"/>' for c, d in _paths(comp["letters"], lambda k: k)]
    ball_p = "".join(f'<path class="wm-{c}" d="{d}"/>' for c, d in _paths(comp["ball"], lambda k: k))
    parts.append(f'<g class="wm-ball"><g class="wm-bh">{ball_p}</g></g>')
    if glint:
        parts.append('<g class="wm-glint">' + "".join(
            f'<path class="g{i + 1}" d="{_merge(fr)}"/>' for i, fr in enumerate(glint_frames(comp))) + "</g>")
    cls = f"wm-px wm-px--{comp['style']}" + (" wm-px--play" if play else "")
    style = f"--u:{comp['s']}px;--nudge:{nudge}px;--step:{step}ms;--drop-at:{drop}ms;--glint-at:{gl_at}ms"
    return (f'<svg class="{cls}" width="{comp["W"]}" height="{comp["H"]}" viewBox="0 0 {comp["W"]} {comp["H"]}" '
            f'aria-hidden="true" focusable="false" style="{style}">{defs}{"".join(parts)}</svg>')


def standalone_svg(rows_or_comp, theme, label, scale=1):
    """A portable mark: raw hex is allowed in exported art (branding/README.md,
    Color), and the letters are paths, so it renders as the real mark anywhere."""
    if isinstance(rows_or_comp, dict):
        comp = rows_or_comp
        cells = {}
        for layer in ("arc", "letters", "ball"):
            cells.update(comp[layer])
        W, H = comp["W"], comp["H"]
    else:
        rows = rows_or_comp
        cells = {(x, y): (ch, None) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch != "."}
        W, H = len(rows[0]), len(rows)
    by = {}
    for xy, (k, _) in cells.items():
        by.setdefault(key_hex(k, theme), set()).add(xy)
    body = "".join(f'<path fill="{c}" d="{_merge(p)}"/>' for c, p in sorted(by.items()))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W * scale}" height="{H * scale}" viewBox="0 0 {W} {H}" '
            f'shape-rendering="crispEdges" role="img" aria-label="{label}">{body}</svg>\n')


# ============================================================== cards and icons
@lru_cache(maxsize=None)
def _field(W, H, ox_pct, oy_pct):
    """The dark field in integer arithmetic: base, a cubic lilac glow, scanlines."""
    im = Image.new("RGB", (W, H))
    px = im.load()
    cx, cy, R = W * ox_pct // 100, H * oy_pct // 100, max(W, H) * 3 // 4
    step = max(3, H // 220)
    base, glow = SRC.FIELD_BASE, SRC.FIELD_GLOW
    k = SRC.FIELD_GLOW_PCT * SRC.FIELD_GLOW_MIX_PCT
    den = 10_000 * R ** 3
    sc = SRC.FIELD_SCANLINE_PCT
    for y in range(H):
        dark = (y // step) % 2 == 0
        for x in range(W):
            d = math.isqrt((x - cx) ** 2 + (y - cy) ** 2)
            a3 = (R - d) ** 3 if d < R else 0
            col = [b + (g - b) * k * a3 // den for b, g in zip(base, glow)]
            if dark:
                col = [c * sc // 100 for c in col]
            px[x, y] = tuple(col)
    return im


def field(W, H, origin=(50, 35)):
    return _field(W, H, origin[0], origin[1]).convert("RGBA")


def stars(img, n, seed=1, avoid=()):
    """Pixel stars at fixed arithmetic positions (no RNG)."""
    px = img.load()
    W, H = img.size
    ramp = SRC.STAR_RAMP
    for i in range(n):
        x, y = (i * 1973 * seed + (i * i) % 131) % W, (i * 769 * seed + (i * i) % 257) % H
        if any(a[0] <= x <= a[2] and a[1] <= y <= a[3] for a in avoid):
            continue
        col = ramp[(i * 7) % len(ramp)]
        arm = 4 if i % 9 == 0 else 2
        for dx in range(-arm, arm + 1):
            for dy in (-1, 0, 1):
                for X, Y in ((x + dx, y + dy), (x + dy, y + dx)):
                    if 0 <= X < W and 0 <= Y < H:
                        px[X, Y] = col + (255,)


def text_png(s, text, color, bold=True):
    return rows_png(["".join(r) for r in text_rows(text, bold=bold)], {"#": color}, s)


def icons():
    return json.loads(ICONS_JSON.read_text(encoding="utf-8")) if ICONS_JSON.exists() else {}


def icon_png(key, scale, theme, bits):
    b = bits[key]
    if "alias" in b:
        b = bits[b["alias"]]
    rows = ["." * 16, "." * 16] + [".." + r.replace("+", "A") + ".." for r in b["rows"]] + ["." * 16] * (14 - len(b["rows"]))
    return rows_png(rows, {"#": tok("text-primary", theme), "A": tok("logo-dot", theme)}, scale)


def rule_png(width, h, theme, style):
    im = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    px = im.load()
    bands = band_hex(theme)
    for x in range(width):
        i = min(SRC.BANDS - 1, x * SRC.BANDS // width)
        if style == "lamps" and (x // h) % 2:
            continue
        col = hx(ramp_at(theme, x / max(1, width - 1)) if style == "hinted" else bands[i]) + (255,)
        for y in range(h):
            px[x, y] = col
    return im


def og_card(style, seams, key=None, title=None, line=None, route="", bits=None):
    W, H = SRC.CARD_W, SRC.CARD_H
    img = field(W, H)
    sub = hx(tok("text-secondary", "dark"))
    if key is None:
        lock = to_png(compose(SRC.STRIKES["og"], style, seams), "dark")
        tag = text_png(4, SRC.DEFAULT_CARD_TAG, hx(tok("text-primary", "dark")))
        x0, y0 = (W - lock.width) // 2, 104
        stars(img, 90, avoid=[(x0 - 30, y0 - 30, x0 + lock.width + 30, y0 + lock.height + 40 + tag.height + 30)])
        img.alpha_composite(lock, (x0, y0))
        img.alpha_composite(tag, ((W - tag.width) // 2, y0 + lock.height + 40))
        url = text_png(2, "eephus.io", sub, bold=False)
        img.alpha_composite(url, ((W - url.width) // 2, H - 64))
        return img.convert("RGB")
    lock = to_png(compose(SRC.STRIKES["og_small"], style, seams), "dark")
    ic = icon_png(key, 8, "dark", bits)
    st = 6 if len(title) * 36 < W - 64 - ic.width - 96 else 5
    tx = text_png(st, title, hx(tok("text-primary", "dark")))
    iy = 214
    stars(img, 70, seed=3, avoid=[(40, 30, 64 + lock.width + 30, 40 + lock.height + 30),
                                  (40, iy - 20, W - 20, iy + ic.height + 170)])
    img.alpha_composite(lock, (64, 40))
    img.alpha_composite(ic, (64, iy))
    ty = iy + (ic.height - 12 * st) // 2
    img.alpha_composite(tx, (64 + ic.width + 32, ty))
    img.alpha_composite(rule_png(tx.width - st, st, "dark", style), (64 + ic.width + 32, ty + 14 * st))
    ln = text_png(2, line, sub, bold=False)
    assert 64 + ln.width <= W - 64, f"card line too wide for {key}: {ln.width} px"
    img.alpha_composite(ln, (64, iy + ic.height + 40))
    img.alpha_composite(text_png(2, "eephus.io" + route, sub, bold=False), (64, H - 64))
    return img.convert("RGB")


def app_icon(size, scale, seams, border=True):
    img = field(size, size, origin=(50, 42))
    if border:
        px = img.load()
        bw = max(2, size // 44)
        col = hx(SRC.APP_ICON_BORDER) + (255,)
        for i in range(bw):
            for t in range(size):
                for X, Y in ((t, i), (t, size - 1 - i), (i, t), (size - 1 - i, t)):
                    px[X, Y] = col
    b = ball_png(32, "light", scale, seams)
    img.alpha_composite(b, ((size - b.width) // 2, (size - b.height) // 2))
    return img.convert("RGB")


# The icon set BR-04 writes under assets/brand/ (file name -> what draws it).
APP_ICONS = {
    "apple-touch-icon.png": (180, 4, True),
    "icon-192.png": (192, 4, True),
    "icon-512.png": (512, 12, True),
    "icon-maskable-512.png": (512, 9, False),   # no border: a platform mask crops the edge
}
BRAND_ICON_DIR = "assets/brand/"


def brand_manifest():
    """The served web manifest with every icon moved to assets/brand/: the
    same name, colours and sizes, read from assets/site.webmanifest (LF)."""
    text = MANIFEST.read_text(encoding="utf-8").replace("\r\n", "\n")
    out = text.replace('"src": "/assets/', '"src": "/' + BRAND_ICON_DIR)
    doc = json.loads(out)
    assert doc["icons"] and all(i["src"].startswith("/" + BRAND_ICON_DIR) for i in doc["icons"]), doc["icons"]
    return out


def gif_frames(style, seams, s=4):
    """The pitch as frames on the dark field colour: arc run by run, then the drop."""
    comp = compose(s, style, seams)
    step, drop, nudge, _ = timeline(comp)
    m = SRC.MOTION
    frames = []
    for t in range(0, drop + m["drop_ms"] + m["gif_frame_ms"], m["gif_frame_ms"]):
        reveal = min(comp["groups"], t // step + 1)
        k = (t - drop) / m["drop_ms"]
        show = t >= drop
        dy = 0 if not show or k >= 1 else (-2 * s if k < .34 else -s if k < .67 else nudge)
        f = to_png(comp, "dark", pad=3 * s, reveal=reveal, ball_dy=dy, show_ball=show)
        matte = Image.new("RGBA", f.size, SRC.FIELD_BASE + (255,))
        matte.alpha_composite(f)
        frames.append(matte.convert("RGB"))
    return frames


def gif_palette_frames(frames):
    """Exact palette conversion: every colour gets its own entry, so no dither."""
    cols = sorted({c for f in frames for _, c in f.getcolors(1 << 16)})
    assert len(cols) <= 256, len(cols)
    pal = Image.new("P", (1, 1))
    flat = [v for c in cols for v in c] + [0] * (3 * (256 - len(cols)))
    pal.putpalette(flat)
    return [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]


_SHEET_LABELS = ("s2 nav", "s4 phone hero", "s6 hero", "ball strikes 8 12 13 16 24 32",
                 "favicon 16 32 48", "PROSPX mark 2x 4x")


def sheet(theme, style, seams):
    """A review sheet: lockups at s 2/4/6, ball strikes at 1x and 4x, the
    favicon strikes at 1x and 4x, the PROSPX mark (2x and up only)."""
    bg = hx(tok("bg-primary", theme)) + (255,)
    lab = hx(tok("text-secondary", theme))
    pad, gap, lh = 24, 24, 12 + 8
    fav = favicon_strikes(seams)
    fav1 = [fav[k] for k in sorted(fav)]
    rows = [  # (heading or None, images, per-image labels or None)
        (None, [to_png(compose(s, style, seams), theme) for s in SRC.FRAGMENT_SCALES], _SHEET_LABELS[:3]),
        (_SHEET_LABELS[3], [ball_png(n, theme, 1, seams) for n in SRC.HAND_STRIKES], None),
        (None, [ball_png(n, theme, 4, seams) for n in SRC.HAND_STRIKES], None),
        (_SHEET_LABELS[4], fav1, None),
        (None, [im.resize((im.width * 4, im.height * 4), Image.Resampling.NEAREST) for im in fav1], None),
        (_SHEET_LABELS[5], [pxmark_png(theme, 2), pxmark_png(theme, 4)], None),
    ]
    W = 2 * pad + max(sum(i.width for i in ims) + gap * (len(ims) - 1) for _, ims, _ in rows)
    H = pad + sum((lh if (head or labels) else 0) + max(i.height for i in ims) + gap for head, ims, labels in rows)
    out = Image.new("RGBA", (W, H), bg)
    y = pad
    for head, ims, labels in rows:
        if head:
            out.alpha_composite(text_png(1, head, lab, bold=False), (pad, y))
        x = pad
        for i, im in enumerate(ims):
            if labels:
                out.alpha_composite(text_png(1, labels[i], lab, bold=False), (x, y))
            x += im.width + gap
        if head or labels:
            y += lh
        x = pad
        for im in ims:
            out.alpha_composite(im, (x, y))
            x += im.width + gap
        y += max(i.height for i in ims) + gap
    return out


# ============================================================== outputs
def build(out: Path, style: str = SRC.STYLE, seams: str = SRC.SEAMS):
    out.mkdir(parents=True, exist_ok=True)
    w = {}

    def put_text(rel, text):
        assert any(rel.startswith(d + "/") for d in OUT_DIRS), rel
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))
        w[rel] = len(text.encode("utf-8"))

    def put_img(rel, im, **kw):
        assert any(rel.startswith(d + "/") for d in OUT_DIRS), rel
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        im.save(p, **kw)
        w[rel] = p.stat().st_size

    # DOM fragments (assets/brand/): referenced by nothing until BR-03.
    for s in SRC.FRAGMENT_SCALES:
        play = s in SRC.PLAY_SCALES
        put_text(f"assets/brand/wordmark-s{s}.svg", lockup_svg(compose(s, style, seams), f"wms{s}", play=play, glint=play))
    put_text("assets/brand/tokens.css", tokens_css())
    put_text("assets/brand/wordmark.css", wordmark_css())

    # Sheets and exported art (branding/pixel/).
    P = "branding/pixel/"
    put_text(P + "glyphs.json", glyphs_json())
    for theme in ("light", "dark"):
        put_img(P + f"brand-sheet-{theme}.png", sheet(theme, style, seams))
        for s in SRC.FRAGMENT_SCALES:
            put_img(P + f"wordmark-s{s}-{theme}.png", to_png(compose(s, style, seams), theme))
    # The favicon and app-icon set (BR-04, assets/brand/): served only through
    # build_site.py's PIXEL_BRAND flag; the manifest points at the same folder.
    I = BRAND_ICON_DIR
    fav = favicon_strikes(seams)
    put_img(I + "favicon.ico", fav[48], sizes=[(16, 16), (32, 32), (48, 48)], append_images=[fav[16], fav[32]])
    put_img(I + "favicon-16.png", fav[16])
    put_img(I + "favicon-32.png", fav[32])
    put_text(I + "favicon.svg", standalone_svg(ball(16, seams), "light", "eephus.io", 1))
    for name, (size, scale, border) in APP_ICONS.items():
        put_img(I + name, app_icon(size, scale, seams, border=border))
    put_text(I + "site.webmanifest", brand_manifest())
    put_img(P + "share-default.png", og_card(style, seams))
    bits = icons()
    if bits:
        for key, title, route, line in SRC.MODULES:
            put_img(P + f"og/{key}.png", og_card(style, seams, key, title, line, route, bits))
    for theme, suffix in (("light", ""), ("dark", "-dark")):
        put_text(P + f"marks/eephus-wordmark{suffix}.svg",
                 standalone_svg(compose(SRC.STRIKES["og_small"], style, seams), theme, "eephus.io"))
        put_text(P + f"marks/compact-mark{suffix}.svg", standalone_svg(ball(32, seams), theme, "eephus.io"))
    put_text(P + "marks/px-ball-monogram.svg", standalone_svg(pxmark(), "light", "PROSPX", SRC.PX_MIN_SCALE))
    fr = gif_palette_frames(gif_frames(style, seams))
    m = SRC.MOTION
    # No loop key: the GIF plays once and holds the finished mark (nothing loops).
    put_img(P + "eephus-arc.gif", fr[0], save_all=True, append_images=fr[1:],
            duration=[m["gif_frame_ms"]] * (len(fr) - 1) + [m["gif_hold_ms"]])
    return w


def _frames(im):
    n = getattr(im, "n_frames", 1)
    for i in range(n):
        im.seek(i)
        yield im.convert("RGBA")


def same_pixels(a: Image.Image, b: Image.Image) -> bool:
    """Every RGBA value equal. (ImageChops.difference(...).getbbox() is not a
    pixel test on RGBA: Pillow's getbbox reads only the alpha band by default,
    so two opaque images of the same size always passed it.)"""
    a, b = a.convert("RGBA"), b.convert("RGBA")
    return a.size == b.size and a.tobytes() == b.tobytes()


def same_image(a: Path, b: Path) -> bool:
    ia, ib = Image.open(a), Image.open(b)
    if a.suffix == ".ico":
        sa, sb = sorted(ia.ico.sizes()), sorted(ib.ico.sizes())
        if sa != sb:
            return False
        return all(same_pixels(ia.ico.getimage(sz), ib.ico.getimage(sz)) for sz in sa)
    if getattr(ia, "n_frames", 1) != getattr(ib, "n_frames", 1):
        return False
    return all(same_pixels(fa, fb) for fa, fb in zip(_frames(ia), _frames(ib)))


def check(out: Path = ROOT, style: str = SRC.STYLE, seams: str = SRC.SEAMS) -> list[str]:
    """Regenerate into a temp folder; return every output that does not reproduce."""
    tmp = Path(tempfile.mkdtemp(prefix="pixel_brand_"))
    try:
        written = build(tmp, style, seams)
        bad = []
        for rel in sorted(written):
            a, b = tmp / rel, out / rel
            if not b.exists():
                bad.append(f"missing {rel}")
            elif a.suffix in TEXT_SUFFIXES:
                if a.read_bytes() != b.read_bytes():
                    bad.append(f"text drift {rel}")
            elif not same_image(a, b):
                bad.append(f"pixel drift {rel}")
        brand = out / "assets" / "brand"
        if brand.exists():
            for p in sorted(brand.rglob("*")):
                rel = p.relative_to(out).as_posix()
                if p.is_file() and rel not in written:
                    bad.append(f"stale {rel}")
        check.written = len(written)
        return bad
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render every eephus.io pixel mark.")
    ap.add_argument("--out", default=str(ROOT))
    ap.add_argument("--style", default=SRC.STYLE, choices=STYLES)
    ap.add_argument("--seams", default=SRC.SEAMS, choices=SEAMS)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        bad = check(Path(a.out), a.style, a.seams)
        for line in bad:
            print(line)
        print(f"{check.written - sum(not b.startswith('stale') for b in bad)} of {check.written} outputs reproduce"
              + (f"; {sum(b.startswith('stale') for b in bad)} stale" if any(b.startswith('stale') for b in bad) else ""))
        return 1 if bad else 0
    res = build(Path(a.out), a.style, a.seams)
    print(f"{len(res)} outputs, {sum(res.values()):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
