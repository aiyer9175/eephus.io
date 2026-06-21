# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""generate_brand_assets.py - one-time generator for the committed brand artifacts.

Writes:
    favicon.ico                  (root; crawlers request /favicon.ico unconditionally)
    assets/favicon-32.png        (PNG fallback referenced from <head>)
    assets/apple-touch-icon.png  (180x180, opaque background per Apple spec)
    assets/share-default.png     (1200x630 Open Graph / Twitter default card)

assets/favicon.svg is hand-authored (vector twin of the same mark) and not
touched here. These are COMMITTED artifacts - run this script once when the
brand changes, review the output, and commit. The nightly build never runs it,
so every box serves byte-identical icons regardless of installed fonts.

The mark is the PROSPX baseball: cream face, dark outline, two seam arcs in
the light-theme ramp (cardinal / gold / green / navy) - drawn here with PIL
arcs rather than rasterized from the SVG so this script has no extra deps.

Usage:  python tools/generate_brand_assets.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

# Light-theme brand palette (matches the px-ball SVG gradient stops + the
# Topps-cream paper tokens in site.css).
CREAM = (246, 241, 228, 255)     # --bg-primary (light)  #F6F1E4
NAVY = (15, 27, 45, 255)         # --text-primary (light) #0F1B2D
CARDINAL = (185, 28, 28, 255)    # #B91C1C
GOLD = (201, 162, 39, 255)       # #C9A227
GREEN = (31, 122, 58, 255)       # #1F7A3A
DEEPNAVY = (14, 43, 77, 255)     # #0E2B4D

# Dark-theme share-card palette (matches eephus-hub.js shareCard fallbacks).
DARK_BG = (16, 16, 20, 255)      # #101014
DARK_FG = (236, 238, 242, 255)   # #ECEEF2
DARK_SUB = (124, 128, 138, 255)  # #7C808A
RAMP_DARK = [(0.0, (0, 217, 255)), (0.30, (180, 124, 255)), (0.55, (255, 79, 216)),
             (0.78, (255, 215, 0)), (1.0, (79, 255, 158))]


def _ball(size: int, pad_frac: float = 0.04, supersample: int = 4) -> Image.Image:
    """The baseball mark on a transparent canvas, drawn at `supersample`x and
    downscaled for clean edges at favicon sizes."""
    S = size * supersample
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(S * pad_frac)
    stroke = max(supersample, S // 18)
    d.ellipse([pad, pad, S - pad, S - pad], fill=CREAM, outline=NAVY, width=stroke)
    # Two seam arcs - vertical-ish curves, like the px-ball SVG. Each seam is a
    # partial ellipse offset outside the ball so only the inner sweep shows.
    seam_w = max(supersample, S // 14)
    # Right seam: ellipse centered right of the ball, left edge sweeping inside.
    rs = [int(S * 0.58), int(S * 0.10), int(S * 1.25), int(S * 0.90)]
    # Left seam mirrors it.
    ls = [int(-S * 0.25), int(S * 0.10), int(S * 0.42), int(S * 0.90)]
    # Paint each seam in two color segments to suggest the brand ramp without
    # a true gradient (reads as cardinal-over-navy at 16px).
    d.arc(rs, start=125, end=180, fill=CARDINAL, width=seam_w)
    d.arc(rs, start=180, end=235, fill=DEEPNAVY, width=seam_w)
    d.arc(ls, start=305, end=360, fill=GOLD, width=seam_w)
    d.arc(ls, start=0, end=55, fill=GREEN, width=seam_w)
    return img.resize((size, size), Image.LANCZOS)


def _font(px: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """A monospace font for the share card. Tries the usual suspects; the
    artifact is committed, so whichever machine runs this once decides."""
    candidates = [
        "C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, px)
        except OSError:
            continue
    return ImageFont.load_default(px)


def make_favicons() -> None:
    ico_sizes = [16, 32, 48]
    base = _ball(48)
    base.save(ROOT / "favicon.ico", sizes=[(s, s) for s in ico_sizes])
    _ball(32).save(ROOT / "assets" / "favicon-32.png")
    # apple-touch-icon wants an opaque square; cream pads the mark like a card.
    touch = Image.new("RGBA", (180, 180), CREAM)
    mark = _ball(150)
    touch.paste(mark, (15, 15), mark)
    touch.convert("RGB").save(ROOT / "assets" / "apple-touch-icon.png")
    print("wrote favicon.ico, assets/favicon-32.png, assets/apple-touch-icon.png")


def _ramp_rule(d: ImageDraw.ImageDraw, x0: int, x1: int, y: int, h: int) -> None:
    """The iridescent dark-theme rule, painted as per-pixel column stops."""
    for x in range(x0, x1):
        t = (x - x0) / max(1, x1 - x0 - 1)
        for i in range(len(RAMP_DARK) - 1):
            t0, c0 = RAMP_DARK[i]
            t1, c1 = RAMP_DARK[i + 1]
            if t0 <= t <= t1:
                f = (t - t0) / max(1e-9, t1 - t0)
                col = tuple(int(a + (b - a) * f) for a, b in zip(c0, c1))
                d.rectangle([x, y, x, y + h - 1], fill=col)
                break


def make_share_card() -> None:
    W, H, PAD = 1200, 630, 64
    img = Image.new("RGB", (W, H), DARK_BG[:3])
    d = ImageDraw.Draw(img)
    # Wordmark + ramp rule + tagline, mirroring the canvas share card layout.
    f_brand = _font(110)
    f_tag = _font(34, bold=False)
    f_mods = _font(24, bold=False)
    d.text((PAD, 200), "EEPHUS.IO", font=f_brand, fill=DARK_FG[:3])
    _ramp_rule(d, PAD, W - PAD, 340, 5)
    d.text((PAD, 372), "sabermetric analysis", font=f_tag, fill=DARK_FG[:3])
    d.text((PAD, 430),
           "PROSPX consensus board / MLB free agency / projections / collegesavant",
           font=f_mods, fill=DARK_SUB[:3])
    ball = _ball(170)
    img.paste(ball, (W - PAD - 170, 96), ball)
    d.text((PAD, H - 70), "eephus.io", font=_font(26), fill=DARK_SUB[:3])
    img.save(ROOT / "assets" / "share-default.png")
    print("wrote assets/share-default.png")


if __name__ == "__main__":
    make_favicons()
    make_share_card()
