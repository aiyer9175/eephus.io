# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential. Written by Noah J. Dengler (@ARKNDJL), 2026.
"""
Pixelate the 30 MLB team logos for eephus.io's low-fi / retro aesthetic.

Downloads the ESPN source logos -> assets/logos/orig/<ORG>.png (kept intact, so
the treatment is fully reversible), and writes pixel-art versions ->
assets/logos/pixel/<ORG>.png.

Treatment (calibrated with the user):
  - downsample to a 36px grid (LANCZOS color averaging)
  - hard alpha threshold -> crisp sprite silhouette (no soft halos)
  - bake a 1px beige sprite OUTLINE in the light-background color: invisible in
    light mode (it matches the beige bg) but a legibility halo in dark mode so
    navy/black logos stay visible on the near-black background
  - nearest-neighbor upscale 7x -> hard pixel blocks baked into the asset (so the
    pixelation survives html2canvas in the Generate GFX output, which doesn't
    honor image-rendering: pixelated)

Re-run any time:  python tools/pixelate_logos.py
"""
import os
import urllib.request
from PIL import Image, ImageFilter

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG  = os.path.join(ROOT, "assets", "logos", "orig")
PIXEL = os.path.join(ROOT, "assets", "logos", "pixel")

# ORG abbreviation -> ESPN logo slug (mirrors ESPN_LOGO_SLUGS in prospx/index.html).
SLUGS = {
    "ARI": "ari", "ATH": "ath", "ATL": "atl", "BAL": "bal", "BOS": "bos",
    "CHC": "chc", "CHW": "chw", "CIN": "cin", "CLE": "cle", "COL": "col",
    "DET": "det", "HOU": "hou", "KCR": "kc",  "LAA": "laa", "LAD": "lad",
    "MIA": "mia", "MIL": "mil", "MIN": "min", "NYM": "nym", "NYY": "nyy",
    "PHI": "phi", "PIT": "pit", "SDP": "sd",  "SEA": "sea", "SFG": "sf",
    "STL": "stl", "TBR": "tb",  "TEX": "tex", "TOR": "tor", "WSN": "wsh",
}

GRID = 36                       # pixel-art grid (calibrated)
SCALE = 7                       # nearest-neighbor upscale -> 252px baked asset
ALPHA_THRESH = 110             # hard silhouette cutoff
OUTLINE = (244, 240, 230, 255)  # --bg-primary beige: invisible in light, halo in dark

def _opaque_luma(im):
    px = im.load(); tot = 0; cnt = 0
    for y in range(0, im.height, 5):
        for x in range(0, im.width, 5):
            r, g, b, a = px[x, y]
            if a > 130:
                tot += 0.2126 * r + 0.7152 * g + 0.0722 * b; cnt += 1
    return tot / cnt if cnt else 255

def process(im):
    s = im.convert("RGBA").resize((GRID, GRID), Image.LANCZOS)
    r, g, b, a = s.split()
    a = a.point(lambda v: 255 if v >= ALPHA_THRESH else 0)
    logo = Image.merge("RGBA", (r, g, b, a))
    grown = a.filter(ImageFilter.MaxFilter(3))          # dilate 1px -> outline mask
    out = Image.new("RGBA", (GRID, GRID), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (GRID, GRID), OUTLINE), (0, 0), grown)
    out.alpha_composite(logo)                            # logo over the beige halo
    return out.resize((GRID * SCALE, GRID * SCALE), Image.NEAREST)

def fetch(org, slug):
    p = os.path.join(ORIG, org + ".png")
    if not os.path.exists(p):
        req = urllib.request.Request(
            f"https://a.espncdn.com/i/teamlogos/mlb/500/{slug}.png",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            open(p, "wb").write(r.read())
    return Image.open(p).convert("RGBA")

def main():
    os.makedirs(ORIG, exist_ok=True)
    os.makedirs(PIXEL, exist_ok=True)
    dark = []
    for org, slug in SLUGS.items():
        im = fetch(org, slug)
        process(im).save(os.path.join(PIXEL, org + ".png"))
        lum = _opaque_luma(im)
        if lum < 85:
            dark.append((org, round(lum)))
        print(f"  {org:4} ok  (luma {lum:3.0f})")
    print(f"\ndone: {len(SLUGS)} logos -> assets/logos/pixel/")
    print("dark logos (helped by the beige outline in dark mode):",
          ", ".join(f"{o}" for o, _ in sorted(dark, key=lambda x: x[1])))

if __name__ == "__main__":
    main()
