# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""generate_brand_assets.py - one-time generator for the committed brand artifacts.

Writes (web-served):
    favicon.ico                    (root; crawlers request /favicon.ico unconditionally)
    assets/favicon.svg             (the SVG favicon: ball strike 16, crisp edges)
    assets/favicon-32.png          (32x32 PNG, wired in <head>)
    assets/favicon-16.png          (16x16 PNG, the footer mark)
    assets/apple-touch-icon.png    (180x180, opaque, P/X monogram, per Apple spec)
    assets/icon-192.png            (192x192 PWA icon, full mark)
    assets/icon-512.png            (512x512 PWA icon, full mark)
    assets/icon-maskable-512.png   (512x512 maskable - mark inside the safe area)
    assets/share-default.png       (1200x630 Open Graph / Twitter default card)

And assembles the documented export bundle under branding/ (copies of the
web assets + the hand-authored SVGs + the generated cards).

The favicons and the footer mark are the hand-tuned ball strikes of
tools/pixel_brand.py (PX-23); branding/marks/*.svg are hand-authored vector
twins and are not drawn here. These are COMMITTED artifacts - run this script once when
the brand changes, review the output, and commit. The nightly build never runs
it, so every box serves byte-identical icons regardless of installed fonts.

The mark is the PROSPX baseball: cream face, dark outline, two seam arcs in the
light-theme ramp (cardinal / gold / green / navy), plus the interlocking P/X
gothic monogram at >=48px - drawn here with PIL rather than rasterized from the
SVG so this script has no extra deps.

Usage:  python tools/generate_brand_assets.py              every artifact
        python tools/generate_brand_assets.py --favicons  the favicon set only
"""
from __future__ import annotations

import shutil
import sys
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

# Dark-theme share-card palette. The dark brand accent is iridescent lilac /
# blurple (replaces the old yellow gold); the ramp is the holo blue->purple->
# magenta the pixel starfield shimmers through (matches site.css --star-holo-*).
DARK_BG = (12, 12, 14, 255)      # #0C0C0E (near-black field)
DARK_FG = (236, 238, 242, 255)   # #ECEEF2
DARK_SUB = (124, 128, 138, 255)  # #7C808A
LILAC = (155, 140, 255, 255)     # #9B8CFF (dark brand accent, the .io)
RAMP_DARK = [(0.0, (0, 217, 255)), (0.34, (139, 127, 255)), (0.67, (180, 124, 255)),
             (1.0, (255, 79, 216))]


def _ball(size: int, pad_frac: float = 0.04, supersample: int = 4,
          monogram: bool = False) -> Image.Image:
    """The baseball mark on a transparent canvas, drawn at `supersample`x and
    downscaled for clean edges. With monogram=True, overlays the interlocking
    P/X gothic monogram (only legible at >=48px; the favicon stays ball-only)."""
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
    if monogram:
        gf = _gothic_font(int(S * 0.50))
        # The X sits over the P, interlocked at the ball's center; a thin
        # cream stroke under the fill keeps the overlapping edges crisp.
        for ch, dx, fnt in (("P", -0.085, gf), ("X", 0.085, _gothic_font(int(S * 0.52)))):
            d.text((S * 0.5 + S * dx, S * 0.52), ch, font=fnt, fill=NAVY,
                   anchor="mm", stroke_width=max(1, S // 130), stroke_fill=CREAM)
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


# The BOLD cut, not the regular: PIL has no synthetic-bold path, so pointing this
# at a regular face would silently render the wordmark at 400 while the site logo
# renders at 700 (2026-08-07 swap from DotGothic16, which only ever had a 400).
_LOGO_TTF = str(ROOT / "branding" / "fonts" / "PixelMplus12-Bold.ttf")


def _logo_font(px: int) -> ImageFont.FreeTypeFont:
    """The brand wordmark face: self-hosted PixelMplus12 Bold (the same pixel-gothic
    the site logo uses), so the cards / gif match the in-site logo exactly. Falls
    back to the mono face if the vendored ttf is missing."""
    try:
        return ImageFont.truetype(_LOGO_TTF, px)
    except OSError:
        return _font(px)


# Y2K / cybergothic dark field for the icons + social art: near-black with a soft
# lilac/blurple radial glow and faint pixel scanlines.
DARK_FIELD = (12, 12, 14)          # #0C0C0E
LILAC_GLOW = (110, 92, 255)        # #6E5CFF


def _y2k_field(W: int, H: int, origin=(0.5, 0.32), scan: bool = True) -> Image.Image:
    """A dark holo field: near-black base, a soft lilac radial glow at `origin`
    (fractional), and faint horizontal scanlines. The cybergothic icon/banner bg."""
    img = Image.new("RGB", (W, H), DARK_FIELD)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = int(W * origin[0]), int(H * origin[1])
    R = int(max(W, H) * 0.75)
    for r in range(R, 0, -max(1, R // 90)):
        a = int(46 * (1 - r / R) ** 2)
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=LILAC_GLOW + (a,))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    if scan:
        sl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sl)
        step = max(3, H // 220)
        for y in range(0, H, step * 2):
            sd.rectangle([0, y, W, y + step - 1], fill=(0, 0, 0, 26))
        img = Image.alpha_composite(img.convert("RGBA"), sl).convert("RGB")
    return img


def _pixel_stars(d: ImageDraw.ImageDraw, W: int, H: int, n: int, seed_step: int = 1) -> None:
    """Chunky pixel-art sparkle-stars in the holo palette, for the social banners.
    Deterministic (no RNG - placed on a hashed lattice) so the artifact is stable."""
    ramp = [(0, 217, 255), (91, 200, 255), (139, 127, 255), (180, 124, 255), (255, 79, 216)]
    for i in range(n):
        # cheap deterministic scatter
        x = (i * 1973 * seed_step + (i * i) % 131) % W
        y = (i * 769 * seed_step + (i * i) % 257) % H
        col = ramp[(i * 7) % len(ramp)]
        bright = (i % 9) == 0
        bs = 3 if bright else 2
        a = 150 if bright else 90
        # plus-sparkle of chunky blocks
        d.rectangle([x - bs, y - bs, x + bs, y + bs], fill=col + (a,))
        arm = bs * (3 if bright else 2)
        d.rectangle([x - arm, y - 1, x + arm, y + 1], fill=col + (a,))
        d.rectangle([x - 1, y - arm, x + 1, y + arm], fill=col + (a,))


def _gothic_font(px: int) -> ImageFont.FreeTypeFont:
    """The blackletter/old-style face for the P/X monogram, matching the in-app
    mark's "Old English Text MT" stack. Falls back to a bold serif so the
    monogram still reads as a classic ball-cap mark on a box without the
    blackletter face installed."""
    candidates = [
        "C:/Windows/Fonts/OLDENGL.TTF",            # Old English Text MT
        "C:/Windows/Fonts/UnifrakturCook-Bold.ttf",
        "C:/Windows/Fonts/georgiab.ttf",           # bold serif fallback
        "C:/Windows/Fonts/timesbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, px)
        except OSError:
            continue
    return ImageFont.load_default(px)


def _y2k_icon(size: int, ball_frac: float = 0.76, monogram: bool = True,
              border: bool = True) -> Image.Image:
    """A Y2K-gothic app icon: the cream ball + P/X monogram on a dark holo field
    (near-black + lilac glow + faint scanlines) inside a thin lilac pixel border."""
    img = _y2k_field(size, size, origin=(0.5, 0.42), scan=(size >= 120)).convert("RGBA")
    if border:
        d = ImageDraw.Draw(img)
        bw = max(2, size // 44)
        for i in range(bw):
            d.rectangle([i, i, size - 1 - i, size - 1 - i], outline=LILAC[:3])
    bs = int(size * ball_frac)
    mark = _ball(bs, monogram=monogram)
    off = (size - bs) // 2
    img.alpha_composite(mark, (off, off))
    return img.convert("RGB")


def make_favicons() -> None:
    """The tiny favicons and the footer mark: the clean ball, hand-hinted
    (owner answer PX-Q4, final-pass plan 5.7 PX-23).

    They are NOT drawn here any more. A 48 px drawing downsampled to 16 read as
    an "O" on a browser tab (Part 8 defect F6), so every small size is now its
    own hand-tuned strike from tools/pixel_brand.py (pixel_brand_src.py holds
    the pixels): 16 and 32 are exact strikes, 48 is strike 24 at 2x, the SVG
    favicon is strike 16 on a 16-unit grid with crisp edges, and the footer
    mark is strike 16 drawn 1:1. Same anatomy at every size: cream face, navy
    rim, the inward ") (" seams (owner answer PB-Q2) in the light ramp. No
    font, no RNG, no anti-aliasing, so every box writes the same bytes."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pixel_brand as PB  # noqa: E402  (tools/ sibling, fontTools + PIL)

    fav = PB.favicon_strikes()
    fav[48].save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)],
                 append_images=[fav[16], fav[32]])
    fav[32].save(ROOT / "assets" / "favicon-32.png")
    fav[16].save(ROOT / "assets" / "favicon-16.png")
    (ROOT / "assets" / "favicon.svg").write_bytes(
        PB.standalone_svg(PB.ball(16), "light", "eephus.io", 1).encode("utf-8"))
    print("wrote favicon.ico (16/32/48 strikes), assets/favicon-32.png, "
          "assets/favicon-16.png (footer mark), assets/favicon.svg (strike 16)")


def make_apple_touch() -> None:
    # apple-touch-icon: the Y2K-gothic dark-holo treatment (home-screen pin).
    # These represent eephus.io (the site), so they use the CLEAN ball - the
    # P/X monogram is reserved for PROSPX-specific art.
    _y2k_icon(180, ball_frac=0.74, monogram=False).save(ROOT / "assets" / "apple-touch-icon.png")
    print("wrote assets/apple-touch-icon.png")


def make_app_icons() -> None:
    """PWA icons referenced by site.webmanifest, in the Y2K-gothic dark-holo style
    (the clean eephus.io ball on a near-black lilac-glow field with a thin lilac
    border - NO P/X monogram, which is PROSPX-only). The maskable variant keeps
    the mark inside the safe area."""
    _y2k_icon(192, ball_frac=0.74, monogram=False).save(ROOT / "assets" / "icon-192.png")
    _y2k_icon(512, ball_frac=0.74, monogram=False).save(ROOT / "assets" / "icon-512.png")
    # Maskable: dark field fills the square (so a platform mask crops the field,
    # not the mark); the ball sits at ~58% well inside the 80% safe area.
    _y2k_icon(512, ball_frac=0.56, border=False, monogram=False).save(ROOT / "assets" / "icon-maskable-512.png")
    print("wrote assets/icon-192.png, icon-512.png, icon-maskable-512.png")


def make_transparent_ball() -> None:
    """The baseball mark on a TRANSPARENT canvas (no dark holo field) - the raster
    twin of the hand-authored SVGs, for overlaying the mark on arbitrary
    backgrounds (dark headers, colored cards, print). Two variants:
      ball-transparent-{sz}.png           the clean eephus.io ball (no monogram)
      ball-transparent-monogram-{sz}.png  the full PROSPX mark (P/X monogram),
                                          the raster twin of marks/px-ball-monogram.svg
    Written straight into branding/icons/ since these are export artifacts, not
    web-served icons."""
    icons = ROOT / "branding" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    for sz in (192, 512, 1024):
        _ball(sz, monogram=False).save(icons / f"ball-transparent-{sz}.png")
        _ball(sz, monogram=True).save(icons / f"ball-transparent-monogram-{sz}.png")
    print("wrote branding/icons/ball-transparent[-monogram]-{192,512,1024}.png")


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
    img = _y2k_field(W, H, origin=(0.30, 0.18)).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    _pixel_stars(d, W, H, 90)
    # Wordmark + ramp rule + tagline. 108 and 36 are 9x and 3x the face's native
    # 12px grid, so the pixel rows land whole.
    f_brand = _logo_font(108)
    f_tag = _logo_font(36)
    f_mods = _font(24, bold=False)
    # Placed by INK top, not by PIL's default ascender anchor: the gap between a
    # face's ascender line and its cap line is 23px at this size, so a literal y
    # slides the whole lockup on any face change while the ramp rule at 348 and
    # the ball at 86 stay put. Anchoring the ink keeps the composition fixed.
    y_brand = 237 - d.textbbox((0, 0), "EEPHUS", font=f_brand)[1]
    d.text((PAD, y_brand), "EEPHUS", font=f_brand, fill=DARK_FG[:3])
    we = d.textlength("EEPHUS", font=f_brand)
    d.text((PAD + we, y_brand), ".IO", font=f_brand, fill=LILAC[:3])
    _ramp_rule(d, PAD, W - PAD, 348, 5)
    y_tag = 392 - d.textbbox((0, 0), "sabermetrics", font=f_tag)[1]
    d.text((PAD, y_tag), "sabermetrics", font=f_tag, fill=DARK_FG[:3])
    d.text((PAD, 436),
           "PROSPX consensus board / MLB free agency / projections / collegesavant",
           font=f_mods, fill=DARK_SUB[:3])
    ball = _ball(180, monogram=False)   # eephus.io default card = the clean ball, not the PROSPX monogram
    img.alpha_composite(ball, (W - PAD - 180, 86))
    d.text((PAD, H - 72), "eephus.io", font=_font(26), fill=DARK_SUB[:3])
    img.convert("RGB").save(ROOT / "assets" / "share-default.png")
    print("wrote assets/share-default.png")


def make_twitter() -> None:
    """Twitter/X-ready art in the Y2K-gothic identity: square avatars (400x400)
    and header banners (1500x500) for eephus.io and PROSPX."""
    social = ROOT / "branding" / "social"
    social.mkdir(parents=True, exist_ok=True)

    # --- avatars (400x400): the mark on the dark holo field, lilac border ---
    av = _y2k_icon(400, ball_frac=0.72, monogram=True)
    av.save(social / "twitter-avatar-prospx.png")
    av2 = _y2k_icon(400, ball_frac=0.72, monogram=False)  # eephus.io: clean ball
    av2.save(social / "twitter-avatar-eephus.png")

    # --- banners (1500x500): a simple CENTERED lockup (icon + wordmark) over a
    # one-line tagline. Centered horizontally so Twitter's bottom-left profile
    # picture (which overlaps ~the left 200px / bottom 150px) never covers it. ---
    def _banner(path, accent_io, title, tagline, monogram):
        W, H = 1500, 500
        img = _y2k_field(W, H, origin=(0.5, 0.28)).convert("RGBA")
        d = ImageDraw.Draw(img, "RGBA")
        _pixel_stars(d, W, H, 120)
        f_brand = _logo_font(120)
        f_tag = _logo_font(36)   # 10x and 3x the face's native 12px grid
        cy = 275
        wm_w = d.textlength(title, font=f_brand)
        wm_x0 = (W - wm_w) / 2
        wm_x1 = wm_x0 + wm_w
        cxc = (wm_x0 + wm_x1) / 2
        # The signature lob arc OVER the wordmark, painted in the brand ramp, with
        # the ball at its apex (the merged eephus.io lockup as raster).
        bbox = d.textbbox((wm_x0, cy), title, font=f_brand, anchor="lm")
        wm_top = bbox[1]
        end_y = wm_top + 2
        peak_y = wm_top - 100
        p0 = (wm_x0 - 18, end_y)
        p1 = (cxc, 2 * peak_y - end_y)
        p2 = (wm_x1 + 18, end_y)
        span = max(1.0, p2[0] - p0[0])
        bw, n = 6, 170
        for i in range(n + 1):
            t = i / n
            x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
            col = _ramp_color((x - p0[0]) / span)
            d.ellipse([x - bw / 2, y - bw / 2, x + bw / 2, y + bw / 2], fill=col)
        # ball at the apex of the arc
        ball_sz = 72
        ball = _ball(ball_sz, monogram=monogram)
        img.alpha_composite(ball, (int(cxc - ball_sz / 2), int(peak_y - ball_sz / 2)))
        # the wordmark
        if accent_io:
            d.text((wm_x0, cy), "EEPHUS", font=f_brand, fill=DARK_FG[:3], anchor="lm")
            we = d.textlength("EEPHUS", font=f_brand)
            d.text((wm_x0 + we, cy), ".IO", font=f_brand, fill=LILAC[:3], anchor="lm")
        else:
            d.text((wm_x0, cy), title, font=f_brand, fill=DARK_FG[:3], anchor="lm")
        # tagline centered below
        tag_w = d.textlength(tagline, font=f_tag)
        d.text(((W - tag_w) / 2, cy + 92), tagline, font=f_tag, fill=DARK_FG[:3])
        img.convert("RGB").save(path)

    _banner(social / "twitter-banner-eephus.png", True, "EEPHUS.IO",
            "sabermetric / scouting analytics website", False)
    _banner(social / "twitter-banner-prospx.png", False, "PROSPX",
            "eephus.io prospect tracker", True)
    print("wrote branding/social/twitter-avatar-*.png + twitter-banner-*.png")


def _bez(t: float, p0, p1, p2):
    """Point on a quadratic bezier at parameter t."""
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def _ramp_color(frac: float):
    """Refractor-ramp color at horizontal fraction `frac` (0..1)."""
    frac = max(0.0, min(1.0, frac))
    for i in range(len(RAMP_DARK) - 1):
        t0, c0 = RAMP_DARK[i]
        t1, c1 = RAMP_DARK[i + 1]
        if t0 <= frac <= t1:
            f = (frac - t0) / max(1e-9, t1 - t0)
            return tuple(int(a + (b - a) * f) for a, b in zip(c0, c1)) + (255,)
    return RAMP_DARK[-1][1] + (255,)


def _ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def _animation_frame(prog: float, W: int, H: int, sc: float) -> Image.Image:
    """One frame of the animated mark (dark variant, transparent bg). `prog` 0..1
    is the whole-shot progress: arc draws over the first ~62%, the ball drops and
    settles over ~55-85%, the wordmark fades in over ~25-65%."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Geometry in the 300x104 wordmark viewBox, scaled by sc.
    p0, p1, p2 = (18, 56), (150, -18), (282, 56)
    x_lo, x_hi = 18.0, 282.0
    # --- arc: brush-stroke polyline up to the drawn fraction ---
    arc_p = _ease_out(min(1.0, prog / 0.62))
    w = max(2, int(2.2 * sc))
    n = 130
    for i in range(int(n * arc_p) + 1):
        t = i / n
        x, y = _bez(t, p0, p1, p2)
        col = _ramp_color((x - x_lo) / (x_hi - x_lo))
        cx, cy = x * sc, y * sc
        d.ellipse([cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2], fill=col)
    # --- wordmark fade-in (auto-fit to ~74% of the width; baseline raised so
    #     the 'p' descender clears the bottom edge). The .22 reserve is set by
    #     the face: PixelMplus12 drops its 'p' a full .20em under the baseline,
    #     more than twice the .09em the previous logo face used, and the old .16
    #     reserve left only ~1px before the frame edge. ---
    tp = max(0.0, min(1.0, (prog - 0.25) / 0.40))
    if tp > 0:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        f10 = _logo_font(40)
        target_w = W * 0.74
        fs = max(10, int(40 * target_w / max(1.0, ld.textlength("eephus.io", font=f10))))
        f = _logo_font(fs)
        a = int(255 * tp)
        total_w = ld.textlength("eephus.io", font=f)
        x0 = (W - total_w) / 2
        baseline = H - int(0.22 * fs) - 6
        ld.text((x0, baseline), "eephus", font=f, anchor="ls", fill=DARK_FG[:3] + (a,))
        w_e = ld.textlength("eephus", font=f)
        ld.text((x0 + w_e, baseline), ".io", font=f, anchor="ls", fill=LILAC[:3] + (a,))
        img = Image.alpha_composite(img, layer)
    # --- ball drop + settle onto the apex ---
    bp = max(0.0, min(1.0, (prog - 0.55) / 0.30))
    if bp > 0:
        # easeOutBack for a small overshoot
        s = 1.70158
        e = 1 + (s + 1) * (bp - 1) ** 3 + s * (bp - 1) ** 2
        dy = (-12 * (1 - e)) * sc
        r = int(9 * sc * (0.7 + 0.3 * min(1.0, bp * 1.3)))
        bx, by = 150 * sc, 20 * sc + dy
        # A real cream baseball (with seam arcs) at the apex, not a bare circle.
        bsz = max(4, int(2 * r))
        mark = _ball(bsz)
        fade = min(1.0, bp * 1.5)
        if fade < 1.0:
            mark.putalpha(mark.getchannel("A").point(lambda v: int(v * fade)))
        img.alpha_composite(mark, (int(bx - bsz / 2), int(by - bsz / 2)))
    return img


def make_animation() -> None:
    """Render the animated mark as a transparent PNG frame sequence (the export
    source for an alpha WebM/MP4 via ffmpeg - see branding/animated/EXPORT.md) and
    a matted GIF (GIF only does 1-bit transparency, so it gets a dark matte)."""
    out = ROOT / "branding" / "animated"
    frames_dir = out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("frame_*.png"):
        old.unlink()
    W, H, sc = 600, 208, 2.0
    N_DRAW, N_HOLD = 30, 12
    frames = []
    for i in range(N_DRAW + N_HOLD):
        prog = min(1.0, i / (N_DRAW - 1))
        fr = _animation_frame(prog, W, H, sc)
        fr.save(frames_dir / f"frame_{i:03d}.png")
        # Matte onto the Y2K holo field for the GIF (GIF is 1-bit transparency).
        matte = _y2k_field(W, H, origin=(0.5, 0.18), scan=True)
        matte.paste(fr, (0, 0), fr)
        frames.append(matte)
    durations = [40] * N_DRAW + [40] * (N_HOLD - 1) + [1600]  # hold the last frame
    frames[0].save(out / "eephus-arc.gif", save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    print(f"wrote branding/animated/frames/ ({N_DRAW + N_HOLD} frames) + eephus-arc.gif")


def assemble_branding() -> None:
    """Copy the web-served artifacts into the documented branding/ bundle so the
    folder is a complete, self-contained export (the SVG marks under
    branding/marks/ and the README/manifest are hand-authored and left in place)."""
    B = ROOT / "branding"
    pairs = [
        (ROOT / "assets" / "favicon.svg",            B / "icons" / "favicon.svg"),
        (ROOT / "favicon.ico",                       B / "icons" / "favicon.ico"),
        (ROOT / "assets" / "favicon-32.png",         B / "icons" / "favicon-32.png"),
        (ROOT / "assets" / "favicon-16.png",         B / "icons" / "favicon-16.png"),
        (ROOT / "assets" / "apple-touch-icon.png",   B / "icons" / "apple-touch-icon.png"),
        (ROOT / "assets" / "icon-192.png",           B / "icons" / "icon-192.png"),
        (ROOT / "assets" / "icon-512.png",           B / "icons" / "icon-512.png"),
        (ROOT / "assets" / "icon-maskable-512.png",  B / "icons" / "icon-maskable-512.png"),
        (ROOT / "assets" / "site.webmanifest",       B / "site.webmanifest"),
        (ROOT / "assets" / "share-default.png",      B / "social" / "share-default.png"),
        # The served subsets of the brand face. Both weights ship because the
        # logo is drawn at 700 and the copy tokens use 400.
        (ROOT / "assets" / "fonts" / "pixelmplus12-regular.woff2", B / "fonts" / "pixelmplus12-regular.woff2"),
        (ROOT / "assets" / "fonts" / "pixelmplus12-bold.woff2",    B / "fonts" / "pixelmplus12-bold.woff2"),
    ]
    n = 0
    for src, dst in pairs:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    print(f"assembled branding/ bundle ({n} artifacts copied)")


FAVICON_BUNDLE = ("favicon.svg", "favicon.ico", "favicon-32.png", "favicon-16.png")


if __name__ == "__main__":
    if "--favicons" in sys.argv[1:]:
        # The PX-23 set only: the hinted favicons and footer mark, plus their
        # copies in branding/icons/. Leaves every other committed image alone.
        make_favicons()
        for name in FAVICON_BUNDLE:
            src = (ROOT / name) if name == "favicon.ico" else (ROOT / "assets" / name)
            shutil.copy2(src, ROOT / "branding" / "icons" / name)
        print(f"copied {len(FAVICON_BUNDLE)} favicon artifacts into branding/icons/")
        sys.exit(0)
    make_favicons()
    make_apple_touch()
    make_app_icons()
    make_transparent_ball()
    make_share_card()
    make_twitter()
    make_animation()
    assemble_branding()
