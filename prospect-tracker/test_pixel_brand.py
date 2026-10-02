# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""BR-01 / PB-01 (owner ask 2, 2026-09-30): the pixel brand generator.

Pins tools/pixel_brand.py and tools/pixel_brand_src.py: the committed outputs
are exactly what the generator writes (text byte for byte, images pixel for
pixel); the letters are PixelMplus12's own bitmap, sampled from the vendored
TTF and never redrawn; the palette mirrors equal the site.css decks; every DOM
fragment is token-only, integer, aria-hidden and small; the ball is 4 s wide
(plus 1 at odd s); the arc is symmetric and never shrinks toward the apex; the
favicon carries exactly the 16, 32 and 48 strikes; the motion is step-end
only, plays once, and stops under reduced motion, hover included.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import pixel_brand as PB  # noqa: E402
import pixel_brand_src as SRC  # noqa: E402

BRAND = ROOT / "assets" / "brand"
PIXEL = ROOT / "branding" / "pixel"
FRAGMENTS = [BRAND / f"wordmark-s{s}.svg" for s in SRC.FRAGMENT_SCALES]
HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")


@pytest.fixture(scope="module")
def drift():
    return PB.check(ROOT)


def test_check_reproduces_every_output(drift):
    assert drift == [], drift
    assert PB.check.written >= 44


def test_outputs_land_only_in_the_two_brand_folders(tmp_path):
    written = PB.build(tmp_path)
    assert written
    for rel in written:
        assert rel.startswith(("assets/brand/", "branding/pixel/")), rel
    assert not (tmp_path / "data").exists()


def test_generator_uses_no_system_font_and_no_randomness():
    for name in ("pixel_brand.py", "pixel_brand_src.py"):
        src = (ROOT / "tools" / name).read_text(encoding="utf-8")
        for banned in ("ImageFont", "truetype(", "Windows/Fonts", "import random", "from random",
                       "numpy.random", "requestAnimationFrame"):
            assert banned not in src, (name, banned)


# ------------------------------------------------------------- the letters
def _fresh_sample(path: Path, ch: str) -> list[str]:
    f = TTFont(str(path))
    gs, cmap = f.getGlyphSet(), f.getBestCmap()
    g = cmap[ord(ch)]
    u = 1000 / 12
    cols = round(f["hmtx"][g][0] / u)
    rows = []
    for r in range(9, -3, -1):
        line = ""
        for c in range(cols):
            pen = PointInsidePen(gs, ((c + .5) * u, -1000 / 30 + (r + .5) * u))
            gs[g].draw(pen)
            line += "#" if pen.getResult() else "."
        rows.append(line)
    return rows


def test_glyph_bitmaps_equal_a_fresh_sample_of_the_font_file():
    doc = json.loads((PIXEL / "glyphs.json").read_text(encoding="utf-8"))
    fonts = {"bold": PB.TTF_BOLD, "regular": PB.TTF_REG}
    for face, path in fonts.items():
        assert doc["font_sha256"][face] == hashlib.sha256(path.read_bytes()).hexdigest(), face
        assert doc[face], face
        for ch, rows in doc[face].items():
            assert rows == _fresh_sample(path, ch), (face, ch)
    for ch in SRC.TEXT:
        assert ch in doc["bold"], ch


def test_lockup_letters_are_the_sampled_glyphs():
    comp = PB.compose(2)
    grid, _, ox = PB.lockup_cols()
    want = {((x + ox) * 2 + dx, (SRC.BASE - 9 + y) * 2 + dy)
            for y in range(12) for x in range(len(grid[0])) if grid[y][x] != "."
            for dx in range(2) for dy in range(2)}
    assert set(comp["letters"]) == want
    joined = ["".join(r) for r in zip(*[_fresh_sample(PB.TTF_BOLD, c) for c in SRC.TEXT])]
    assert ["".join("#" if v != "." else "." for v in row) for row in grid] == joined


# ------------------------------------------------------------- the palette
def _deck(css: str, selector: str) -> dict[str, str]:
    m = re.search("^" + re.escape(selector) + r" \{$(.*?)^\}", css, re.M | re.S)
    assert m, selector
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    return {k: v.strip() for k, v in re.findall(r"--([\w-]+)\s*:\s*([^;]+);", body)}


def _resolve(deck, name, fallback=None):
    v = deck.get(name, (fallback or {}).get(name))
    m = re.fullmatch(r"var\(--([\w-]+)\)", v or "")
    return _resolve(deck, m.group(1), fallback) if m else v


@pytest.fixture(scope="module")
def decks():
    css = (ROOT / "assets" / "site.css").read_text(encoding="utf-8")
    light = _deck(css, ":root")
    return light, _deck(css, '[data-theme="dark"]')


def test_tokens_equal_the_site_css_decks(decks):
    light, dark = decks
    for name, (lv, dv) in SRC.TOKENS.items():
        assert _resolve(light, name).upper() == lv.upper(), (name, "light")
        assert _resolve(dark, name, light).upper() == dv.upper(), (name, "dark")


# BR-02 (PB-Q1 B, stepped): the site.css decks define every brand token of
# assets/brand/tokens.css with the same value, except the --wm-g* gradient
# stops, which only direction A uses and which stay out of site.css.
def test_site_css_carries_the_brand_tokens(decks):
    css = (BRAND / "tokens.css").read_text(encoding="utf-8")
    for sel, deck in zip((":root", '[data-theme="dark"]'), decks):
        want = _deck(css, sel)
        brand = {k: v for k, v in want.items() if not k.startswith("wm-g")}
        assert len(brand) == 19, (sel, sorted(brand))
        for name, value in brand.items():
            assert name in deck, (sel, name)
            assert " ".join(deck[name].split()) == " ".join(value.split()), (sel, name)
        assert not [k for k in deck if k.startswith("wm-g")], sel


def test_ramp_equals_the_iridescent_stops(decks):
    for theme, deck in zip(("light", "dark"), decks):
        stops = re.findall(r"(#[0-9A-Fa-f]{6})\s+([\d.]+)%", deck["iridescent"])
        got = tuple((round(float(p) / 100, 2), h.upper()) for h, p in stops)
        assert got == tuple((t, h.upper()) for t, h in SRC.RAMP[theme]), theme


def test_ball_face_is_the_compact_mark_cream():
    assert SRC.BALL_FACE.upper() in (ROOT / "branding" / "marks" / "compact-mark.svg").read_text(
        encoding="utf-8").upper()


def test_tokens_css_adds_no_new_hex(decks):
    light, dark = decks
    known = {v.upper() for d in decks for v in d.values() if HEX.fullmatch(v)} | {SRC.BALL_FACE.upper()}
    css = (BRAND / "tokens.css").read_text(encoding="utf-8")
    for h in HEX.findall(css):
        assert h.upper() in known, h


def test_band_colours_equal_their_color_mix_tokens():
    css = (BRAND / "tokens.css").read_text(encoding="utf-8")
    for theme, sel in (("light", ":root"), ("dark", '[data-theme="dark"]')):
        deck = _deck(css, sel)
        for i, want in enumerate(PB.band_hex(theme)):
            expr = deck[f"arc-{i + 1}"]
            m = re.fullmatch(r"color-mix\(in srgb, var\(--ramp-(\d)\) (\d+)%, var\(--ramp-(\d)\)\)", expr)
            ramp = {j + 1: c for j, (_, c) in enumerate(SRC.RAMP[theme])}
            if m:
                a, p, b = ramp[int(m.group(1))], int(m.group(2)), ramp[int(m.group(3))]
                got = "#%02X%02X%02X" % tuple((x * p + y * (100 - p) + 50) // 100
                                              for x, y in zip(PB.hx(a), PB.hx(b)))
            else:
                got = ramp[int(re.fullmatch(r"var\(--ramp-(\d)\)", expr).group(1))]
            assert got == want, (theme, i)


# ------------------------------------------------------------- the fragments
@pytest.mark.parametrize("path", FRAGMENTS, ids=lambda p: p.name)
def test_fragment_is_token_only_integer_and_hidden(path):
    raw = path.read_bytes()
    assert len(raw) <= 6 * 1024, len(raw)
    text = raw.decode("utf-8")
    root = ET.fromstring(text)
    assert root.tag.endswith("svg")
    assert root.get("aria-hidden") == "true"
    assert not HEX.search(text), "raw hex in a DOM fragment"
    assert "rgb(" not in text and "hsl(" not in text
    for el in root.iter():
        assert el.get("fill") in (None,) or el.get("fill").startswith("url(#"), el.get("fill")
        if el.tag.endswith("path"):
            assert el.get("class", "").startswith(("wm-", "g")), el.get("class")
            nums = re.findall(r"-?[\d.]+", el.get("d"))
            assert nums and all(re.fullmatch(r"-?\d+", n) for n in nums), el.get("d")[:80]
    for attr in ("width", "height"):
        assert re.fullmatch(r"\d+", root.get(attr)), attr
    assert all(re.fullmatch(r"\d+", n) for n in root.get("viewBox").split())
    assert all(re.fullmatch(r"\d+(px|ms)", v.split(":")[1]) for v in root.get("style").split(";"))


def test_wordmark_css_fills_are_tokens_and_motion_is_step_end_once():
    css = (BRAND / "wordmark.css").read_text(encoding="utf-8")
    assert not HEX.search(css)
    for v in re.findall(r"fill:\s*([^;]+);", css):
        assert v.strip().startswith("var(--"), v
    anims = re.findall(r"animation:\s*([^;]+);", css)
    assert anims
    for a in anims:
        if a.strip().startswith("none"):
            continue
        assert "step-end" in a, a
        assert "infinite" not in a, a
    assert "transition" not in css
    rm = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", css, re.S).group(1)
    for sel in (".wm-s", ".wm-h", ".wm-ball", ".wm-bh", ".wm-glint path"):
        assert sel in rm, sel
    assert "animation: none !important" in rm
    animated = {m.group(1).split()[-1] for m in re.finditer(r"([^{}\n]+)\{[^{}]*animation:\s*wm-", css)}
    assert animated <= {".wm-s", ".wm-h", ".wm-ball", ".wm-bh", ".g1", ".g2", ".g3"}, animated


def test_hero_fragments_play_once_and_the_nav_only_replays():
    for s, path in zip(SRC.FRAGMENT_SCALES, FRAGMENTS):
        cls = ET.fromstring(path.read_text(encoding="utf-8")).get("class").split()
        assert ("wm-px--play" in cls) == (s in SRC.PLAY_SCALES), s


# ------------------------------------------------------------- ball and arc
def test_ball_is_four_s_wide_plus_one_at_odd_s():
    for s, n in SRC.BALL_FOR_SCALE.items():
        assert n == 4 * s + (s % 2), s
        for seams in PB.SEAMS:
            rows = PB.ball(n, seams)
            assert len(rows) == n and all(len(r) == n for r in rows), (s, seams)
    for n in SRC.HAND_STRIKES:
        assert n in SRC.SEAM_COLS, n


@pytest.mark.parametrize("s", sorted(SRC.BALL_FOR_SCALE))
def test_ball_centres_on_the_apex_column(s):
    comp = PB.compose(s)
    x0, _, n = comp["ball_box"]
    assert 2 * x0 + n == comp["W"], (x0, n, comp["W"])


@pytest.mark.parametrize("s", [2, 3, 4, 6, 10])
def test_arc_runs_symmetric_and_non_shrinking_toward_the_apex(s):
    W2, _, col_row, _, _ = PB.arc_grid(s)
    assert sorted(col_row) == list(range(W2))
    for x in range(W2):
        assert col_row[x] == col_row[W2 - 1 - x], x
    runs, prev = [], None
    for x in range(W2 // 2 + 1):
        if col_row[x] != prev:
            runs.append(0)
            if prev is not None:
                assert col_row[x] == prev - 1, x
            prev = col_row[x]
        runs[-1] += 1
    runs[-1] = W2 - 2 * sum(runs[:-1])      # the apex run spans both halves
    assert all(a <= b for a, b in zip(runs, runs[1:])), runs


def test_run_tables_are_non_decreasing():
    for runs in (SRC.ARC_RUNS, SRC.HALF_RUNS):
        assert all(a <= b for a, b in zip(runs, runs[1:])), runs


# ------------------------------------------------------------- raster art
def _same(a: Image.Image, b: Image.Image) -> bool:
    return a.size == b.size and not ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).getbbox()


def test_favicon_ico_carries_exactly_16_32_48_each_its_strike():
    ico = Image.open(PIXEL / "favicon.ico")
    assert sorted(ico.ico.sizes()) == [(16, 16), (32, 32), (48, 48)]
    want = PB.favicon_strikes()
    for n in (16, 32, 48):
        assert _same(ico.ico.getimage((n, n)), want[n]), n
    assert _same(Image.open(PIXEL / "favicon-16.png"), want[16])
    assert _same(Image.open(PIXEL / "favicon-32.png"), want[32])


def _palette(theme):
    keys = ["ink", "dot", "k", "c", "a", "b", "d", "e"] + [f"b{i}" for i in range(SRC.BANDS)]
    return {PB.hx(PB.key_hex(k, theme)) for k in keys}


@pytest.mark.parametrize("name,theme", [(f"wordmark-s{s}-{t}.png", t) for s in SRC.FRAGMENT_SCALES
                                        for t in ("light", "dark")] + [("favicon-16.png", "light"),
                                                                       ("favicon-32.png", "light")])
def test_strikes_have_no_anti_aliasing(name, theme):
    im = Image.open(PIXEL / name).convert("RGBA")
    pal = _palette(theme)
    for count, (r, g, b, a) in im.getcolors(1 << 16):
        assert a in (0, 255), (name, a)
        if a:
            assert (r, g, b) in pal, (name, (r, g, b))


def test_the_gif_plays_once_and_ends_on_the_finished_mark():
    im = Image.open(PIXEL / "eephus-arc.gif")
    assert "loop" not in im.info
    im.seek(im.n_frames - 1)
    last = im.convert("RGB")
    comp = PB.compose(4)
    still = PB.to_png(comp, "dark", pad=3 * 4)
    matte = Image.new("RGBA", still.size, SRC.FIELD_BASE + (255,))
    matte.alpha_composite(still)
    assert _same(last, matte.convert("RGB"))


def test_px_monogram_never_below_40_px():
    root = ET.fromstring((PIXEL / "marks" / "px-ball-monogram.svg").read_text(encoding="utf-8"))
    assert int(root.get("width")) >= 40 and int(root.get("height")) >= 40
    with pytest.raises(AssertionError):
        PB.pxmark_png("light", 1)


def test_card_lines_follow_the_copy_rules():
    banned = re.compile(r"\b(seamless|robust|delve|comprehensive|crucial|essential|powerful|showcase|"
                        r"utilize|unlock|elevate|game-changing|cutting-edge|tapestry|meticulous|"
                        r"underscore|harness|leverag\w*|luck|due|regress\w*|trending|will|sleeper)\b", re.I)
    for key, title, route, line in SRC.MODULES:
        for text in (title, line):
            assert chr(0x2014) not in text and chr(0x2013) not in text, key
            assert not banned.search(text), (key, text)
        assert route == f"/{key}/"
