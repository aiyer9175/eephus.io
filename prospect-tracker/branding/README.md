# eephus.io brand guide

The single source of truth for the eephus.io / PROSPX identity. If the site and
this folder disagree, the site is wrong. Everything here extends the existing
marks. None of it redesigns them.

## The brand idea

An eephus is a junk pitch: a slow, high, looping lob that beats hitters with
shape and timing instead of velocity. That is the whole thesis. eephus.io wins
on guile, not radar-gun numbers. We read the same public data everyone has and
get more out of it through better models and a clearer presentation. The arc in
the logo is that pitch, and it is the one idea the rest of the system serves.

Two aesthetic anchors hold the design together:

- **The newspaper sports page.** Boards, tables, and leaderboards read like a
  broadsheet stat column: sharp corners, a tight monospace, tabular numbers,
  hairline rules. Information first.
- **The baseball card.** Player pages read like a card: a portrait, a name
  plate, a rarity treatment, a foil refractor in dark mode. The card is where
  the identity gets to show off.

## Color

The palette is fixed. Use the tokens, not raw hex, anywhere in the running site
(`assets/site.css` and `prospx/index.html` both carry the `:root` decks, kept
in sync by hand). Raw hex below is for exported art only.

### Light (warm newsprint)

| Token | Hex | Role |
|---|---|---|
| `--bg-primary` | `#F4F0E6` | page, warm paper |
| `--bg-secondary` | `#FBF8F0` | card surface |
| `--bg-tertiary` | `#ECE6D6` | alt rows |
| `--bg-header` | `#0E2B4D` | headline band, deep navy |
| `--text-primary` | `#0F1B2D` | ink |
| `--accent-red` | `#B91C1C` | cardinal, down |
| `--accent-gold` | `#C9A227` | card gold, the `.io` dot |
| `--accent-green` | `#1F7A3A` | forest, up |
| `--accent-navy` | `#0E2B4D` | links |
| `--border` | `#C9C1AE` | warm tan hairline |

### Dark (Topps-Chrome refractor)

Keep this. The dark theme is a deliberate foil-card refractor, not a generic
dark mode. Do not flatten it.

| Token | Hex | Role |
|---|---|---|
| `--bg-primary` | `#0C0C0E` | near-black field |
| `--bg-secondary` | `#1A1A1E` | card surface |
| `--bg-header` | `#08080A` | headline band |
| `--text-primary` | `#ECEEF2` | cool white |
| `--accent-lilac` | `#9B8CFF` | **the dark brand accent / the `.io`** (iridescent lilac-blurple, replaces the old gold here) |
| `--accent-green` | `#4FFF9E` | refractor mint |
| `--accent-gold` | `#FFD700` | refractor gold (FV-tier data only, not chrome) |
| `--accent-navy` | `#4FD9FF` | refractor cyan (links) |
| `--accent-cyan` | `#00D9FF` | terminal cyan |
| `--neon-violet` | `#B47CFF` | refractor purple |
| `--neon-magenta` | `#FF4FD8` | refractor magenta |

On dark mode the brand accent is iridescent lilac/blurple (`--accent-lilac`), not
yellow. Gold is kept only for the FV heat ramp, where it means "elite" and must
stay gold. The wordmark `.io` is gold on light, lilac on dark (`--logo-dot`).

### The ramp (accent stripe)

The signature gradient, the `--iridescent` token.

- Light: `#B91C1C` cardinal, `#C9A227` gold, `#1F7A3A` green, `#0E2B4D` navy.
- Dark: `#00D9FF`, `#B47CFF`, `#FF4FD8`, `#FFD700`, `#4FFF9E`.

It paints the seam arcs on the ball, the masthead underline, hover hairlines,
and the share-card rule. It is the one place loud color is allowed, and it is
always a thin accent, never a fill.

## Typography

The wordmark and all chrome are set in a Japanese screen-gothic pixel type.
This is the brand type. There is no Poppins, no Inter, no serif on the marks.

Three tokens, and they do NOT share a rule. Live values are in
`assets/site.css`; treat that file, not this list, as the source of truth.

- `--font-logo`: led by **PixelMplus12**, the bundled face, on every platform.
  Wordmark, nameplate, page H1. One identical letterform everywhere is the
  point, so this token deliberately outranks the system faces.
- `--font-retro-mono`: led by **MS Gothic**, then MS UI Gothic, then
  PixelMplus12. The blocky variant: FV badges, headings, chrome.
- `--font-retro`: led by **MS UI Gothic**, then MS Gothic, then PixelMplus12.
  The legibility variant: body and UI.

The two copy tokens lead with the Windows system faces so a Windows reader
renders body text from a system font. PixelMplus12 sits behind them for Mac,
iPhone and Linux, where MS Gothic does not exist. It is self-hosted as a Latin
subset in both weights (`assets/fonts/pixelmplus12-*.woff2`, mirrored into
`fonts/` here); the source TTFs and the M+ license live in `fonts/` too.

The logo face was DotGothic16 until 2026-08-07. It shipped a single 400 weight
and the site sets `font-synthesis: none`, so the wordmark rendered at regular
no matter what weight was asked for. PixelMplus12 has a real 700, so the
wordmark is now genuinely bold. `fonts/DotGothic16-Regular.ttf` and its OFL
license stay here for provenance only; nothing serves them.

Numbers are tabular (`font-variant-numeric: tabular-nums`). Corners are square
everywhere; radius is `0` by rule.

## Logo usage

Two marks, one system.

**Full lockup, the eephus.io merged wordmark.** The lob arc is part of the
lettering: it spans the word with the ball at its apex, the word set in
PixelMplus12 Bold, the `.io` in gold. It is live text plus inline SVG in the site
(`build_site.py:eephus_merged_wordmark`); the portable twin is
`marks/eephus-wordmark.svg` (and `-dark`). Use it in mastheads, the nav, and
footers.

**Compact mark, the eephus.io ball.** A vintage Topps baseball: cream face, navy
outline, two seam arcs in the ramp (`marks/compact-mark.svg`). This is the
eephus.io compact mark, and the favicon and the whole app-icon set are derived
from it - the CLEAN ball, no monogram. Use it where the full wordmark will not
fit: the favicon, app icons, the mobile header, small chips, loaders.

**PROSPX mark, the px-ball + monogram.** The same ball with the interlocking P/X
gothic monogram (`marks/px-ball-monogram.svg`), at 48px and up. This is the
PROSPX mark, reserved for PROSPX-specific things (the PROSPX app masthead, its
Twitter avatar/banner). It is NOT the eephus.io site mark - the favicon, the PWA
icons, and the default share card all use the clean ball above.

**Clear space and minimums.** Keep at least the height of the ball as clear
space around any lockup. Minimum sizes: full wordmark no smaller than 20px cap
height; px-ball no smaller than 16px (ball-only below 40px).

**Don'ts.**

- Do not redraw or re-letter the wordmark, or swap the font.
- Do not recolor the ramp or apply it as a fill behind text.
- Do not add the P/X monogram to the favicon or any sub-40px mark.
- Do not round the corners of any container; the square corner is the brand.
- Do not place the light mark on a busy photo without the cream card behind it.
- One mark per surface. The badge is defined in several spots in code for
  historical reasons; treat this folder as canonical and do not fork a new one.

## The dark-mode starfield

The canonical dark background is a Y2K / chrome-holo night sky drawn on one fixed
full-viewport canvas (`assets/eephus-bg.js`), mounted only under
`data-theme="dark"` and torn down completely otherwise. The stars are crisp
PIXEL sparkles, not anti-aliased circles: a bright center pixel with a twinkling
4-point "+" of pixels and a soft square bloom. They carry an iridescent holo
palette (cyan, sky, blurple, violet, magenta) that slowly shimmers through the
ramp like a hologram, with a few bright white-blue anchor stars. It stays a
background: whisper opacity, `aria-hidden`, content always sits on solid cards
above it.

It is cheap by design: a hard star-count ceiling, device-pixel-ratio capped at
2, one animation loop paused on hidden tabs. The twinkle always runs (a static
star sky reads as dead); it is aria-hidden decoration, so it keeps twinkling even
under `prefers-reduced-motion`, as does every other animation on the site (owner
rule 2026-10-01: the motion is minimal and is never switched off for the Reduce
Motion setting); only the user-tracking parallax honors the OS motion
preference, since pointer-following drift reads very differently. Every dial lives in the `[data-theme="dark"]` token block in
`site.css` (`--star-holo-*`, `--star-density-base`, etc.). It also responds to a
prospect page's headline FV through `EephusBG.setFV()`: better prospects, a
denser, brighter field.

## Share cards

A link to eephus.io should unfurl with the identity, never a bare URL. Cards are
1200x630 (Open Graph / Twitter `summary_large_image`), dark refractor aesthetic,
wordmark plus a clean line, the ball top-right, the ramp rule.

- `social/share-default.png`: the site-wide default.
- Per-page cards: pass `image`/`og_title`/`og_description` at the `page()` call
  site in `build_site.py`; `_social_meta()` handles the tags.
- Player cards: a parameterized template renders a small baseball card (name,
  org crest, position, headline FV) per prospect at build time. The host is
  static, so cards are pre-rendered PNGs, not generated on the fly.

All cards are produced by `tools/generate_brand_assets.py` (PIL, no extra deps),
run once when the brand changes and committed. The nightly build never runs it,
so every box serves byte-identical art.

## Voice

Direct and human. Short sentences. Plain words. We explain the number, we don't
sell it. No em dashes. None of the model-tell words: delve, elevate, unlock,
robust, seamless, leverage, tapestry. When in doubt, write it the way you would
say it to someone who knows baseball.

## Asset index

```
branding/
  README.md                     this brand guide
  site.webmanifest              PWA manifest (name, colors, icon set)
  marks/
    eephus-wordmark.svg         full lockup, light
    eephus-wordmark-dark.svg    full lockup, dark
    compact-mark.svg            px-ball, ball only (favicon twin), light
    compact-mark-dark.svg       px-ball, dark-surface variant
    px-ball-monogram.svg        px-ball + P/X monogram - the PROSPX mark only
  icons/
    favicon.svg                 vector favicon (ball only)
    favicon.ico                 16/32/48 multi-res
    favicon-32.png              32px PNG
    apple-touch-icon.png        180px, clean ball on the dark holo field
    icon-192.png                PWA, clean ball (eephus.io)
    icon-512.png                PWA, clean ball (eephus.io)
    icon-maskable-512.png       PWA maskable (mark inside the safe area)
  animated/
    eephus-arc.svg              the animated mark (CSS, the in-site source)
    EXPORT.md                   how to export PNG frames / GIF / WebM-alpha
    frames/                     PNG frame sequence (the export source)
    eephus-arc.gif              matted GIF (one-bit transparency fallback)
  social/
    share-default.png           1200x630 default Open Graph card
```

Regenerate the raster artifacts with `python tools/generate_brand_assets.py`.
The SVG marks, the manifest, and this guide are hand-authored.
