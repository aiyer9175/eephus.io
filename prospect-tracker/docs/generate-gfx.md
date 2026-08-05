# Generate GFX — social-ready graphics

Two Generate-GFX systems ship on eephus.io, unified by the same design language
(theme-aware, PROSPX/eephus brand ramp, format presets, one export path):

1. **PROSPX in-page engine** (`prospx/index.html`) — DOM boards + collectible
   cards rasterized by html2canvas. The richest surface; documented in detail below.
2. **Shared `EEPHUS_GFX`** (`assets/eephus-gfx.js`) — a canvas-native board/card
   modal used by every other module (FA, Projections, MLB Stats, PAL, Trade
   Machine, CollegeSavant). `EEPHUS_GFX.open(spec)` + `EEPHUS_GFX.chipHTML(id,label)`.

Both snapshot the **current section + filters + sort** at the moment you open the
modal, so the graphic always matches what's on screen.

## Module coverage (as of 2026-07-18)

| Surface | Boards | Card |
|---|---|---|
| PROSPX | Prospects, Injured, Watchlist, Spotlights, Leaderboards, Debuted, Draft, Int'l Amateurs, Overseas, Farm | player card (5 variants), farm card, compare card, scatterplot |
| Free Agency | Class board, Signing tracker, **Fits**, **Archive** | player market card |
| Projections | Players, Team Outlook, **Accountability** | player card, head-to-head compare |
| MLB Stats | **Relievers (REM+), Team Bullpens, Starters (SEM+), Hitters (HEM+), Leverage (WPA)** | — |
| PAL | **RP->SP candidates, SP->RP candidates** | — |
| Trade Machine | **Trade board** | **deal card** |
| CollegeSavant | **leaderboard board** | player card (via the shared modal) |

**Bold** entries shipped in the 2026-07-18 rollout; the rest predate it.

## Section coverage — PROSPX templates (`kind`)

Each `kind` drives the per-row layout and the footer legend. Every row now
surfaces a richer meta line + a value/sub pair (2026-07-18 information pass):

| Section | `kind` | Badge | Value (+ sub) | Meta line |
|---|---|---|---|---|
| Prospects | `prospect` | eFV or consensus (lead-toggle) | engine surplus ($M) + $DvM+ | pos, org, age, level |
| Injured | `prospect` (IL wrapper) | eFV/consensus | **IL type + days on IL** | pos, org, age |
| Graduates | `graduate` | final prospect grade | career WAR | pos, org, age, level |
| Draft | `draftee` | consensus FV | Draft Stock+ | pos, school, age |
| Overseas | `overseas` | consensus FV | **OPS / ERA line** | pos, league, age |
| Leaderboards | `leader` | eFV/consensus | selected stat | pos, org, level, **sample (PA/IP)** |
| Farm | `farm` | (window rank) | window letter grade + **net surplus $M** | **top prospect, N ranked, avg age** |
| Spotlights | `spotlight` | current FV | FV delta + **top driver** | pos, org, level, **stat line** |
| Int'l Amateurs | `ifa` | consensus FV | signing bonus | pos, country, org |

FV rounding is repo-wide: **consensus FV rounds up** (`fvCeil`), **eFV rounds to
nearest** (`efvGradeDisplay`, the quantile headline). The Injured value shows IL
context instead of surplus because that board is about health, not value.

## Formats (aspect ratios)

Rendered at **2x (retina)** via html2canvas.

| Format | Pixels | Ratio | Use |
|---|---|---|---|
| Wide | 1600 x 900 | 16:9 | **default for list boards** - X-ready, no crop |
| Portrait | 1080 x 1350 | 4:5 | Instagram feed / X portrait |
| Tall | 1080 x 1620 | 2:3 | tall card geometry |
| Square | 1080 x 1080 | 1:1 | IG square / avatars |
| Story | 1080 x 1920 | 9:16 | IG/TikTok stories, Reels |

**Space use** (2026-07-18 layout pass): the rows block is vertically centered so
short lists no longer leave a dead gap between the last row and the footer;
columns scale with list length + canvas width (`_gfxColumnCount`) - a Top 100 in
Wide fills four columns. When a count exceeds what's shown, the footer reads
`... top N shown, +M more at eephus.io/prospx`, and the header QR encodes the
**live section + filters hash** so a scan reproduces the exact list.

## Customization (before export)

The modal customization row re-renders the live preview on every change:

- **Format** - wide / portrait / tall / square / story (above).
- **Template** - for card kinds: detailed / compact / scouting / stats / back.
- **Frame** - for prospect cards: rarity (FV-tier) / chrome / retro / team.
- **Theme** - Auto (site) / Dark / Light. Flips the root `data-theme` while the
  modal is open (both themes first-class); the live theme is restored on close.
- **Show** - Top 10 / 25 / 50 / 100 / All.
- **Title** - overrides the auto-derived headline.
- **Accent** - six brand accent swatches for badges/values/wordmark.
- **card pack** - render the list as a sheet of mini collectible cards (3-across).
- **value column / photos / team logos** - toggles (default on). *photos* is
  shown for the cards, the card pack and the **Rows** list; it is hidden on the
  Tiles list and the farm board, where it would be inert.

### Photos & team logos

**Where photos appear** (2026-08-04d). The two decisions that produced today's
behaviour, in order:

- 2026-08-04: player pictures came **off** the list graphics entirely. They
  looked janky and were crushing name widths.
- 2026-08-04d: they came **back to the Rows list only, gated by geometry**, and
  never at the cost of the name.

| Surface | Photo? |
|---|---|
| Rows list | **yes, where the geometry allows** (see the gate below) |
| Tiles list | **no**, by charter: big legible names is the whole point of that layout |
| Farm board (legacy rows) | no, farm rows carry no `mlbam` |
| Prospect card / compare card / pack mini-card | **yes**, always |

**The gate is geometry, not list size.** `_gfxListGeoFor` reserves a well only
when the row is tall enough for a face and the column wide enough to spare the
width:

```
photoW = (rowH >= 40 && colW >= 320) ? Math.round(rowH * 0.75) : 0
```

`photoW + 6` is then subtracted from the width the column search scores, so a
layout can only win on space it can actually spend on the name. Measured across
the whole format x count matrix, that subtraction changes no chosen column count
today; it exists so the search stays honest if the constants move.

Where that lands, measured 2026-08-04:

| Count | Photos on |
|---|---|
| Top 10 | all seven formats |
| Top 25 | all seven formats |
| Top 50 | every format except Square (36px rows) |
| Top 100 | Board only (52px rows, 498px columns) |

Everything else self-excludes, including the owner's canonical Top 100 on Wide
16:9 (28px rows, 371px columns). The narrowest name field that ends up **with** a
photo is 353px, against a 200px floor. `test_gfx_chip_layout.py` pins all of it.

**Face-centred crops.** `img.mlbstatic.com` is Cloudinary and honours
`c_fill,g_face`: `c_fill` returns exactly the requested box, `g_face` centres
that crop on the detected face. Source headshots are 480x720 (2:3), so every
consumer that wanted a square or a 3:4 well used to crop blind, and canvas
consumers (`drawImage` has no `object-fit`) squashed the face outright. Asking
the CDN for the exact box fixes both at the source, and it is why nothing needs
a client-side "center top" guess any more.

The transform lives in ONE constant per module (`_GFX_FACE_CROP` in
`prospx/index.html`, `FA_FACE_CROP` in `assets/fa.js`) so a CDN lockdown is a
one-line revert. Verified live on both the `67` and `milb` contexts: exact pixel
dimensions returned, `Access-Control-Allow-Origin: *` intact. `c_thumb` is not
interchangeable, it zooms far too tight on the face.

**Fallback chain.** Every photo well is a **rectangular** portrait crop, never a
broken image:

1. **Player headshot** (`img.mlbstatic.com`) when *photos* is on, the geometry
   gate passed, and `data/photo_ctx.json` says the id has a real photo in the
   `67` or `milb` context.
2. **Team logo** (`a.espncdn.com`) when the context is `none`, the id is
   missing, or the headshot 404s.
3. **Silhouette** - an inline-SVG person painted as the cell background, for
   subjects with no MLB org (draftees, overseas).

The well is **always reserved once the gate opens**, even for a subject with no
photo; it just shows the club mark. Dropping the element on those rows would
ripple the name column in and out down the board.

The URL builder deliberately omits Cloudinary's `d_people:generic` default,
which serves a silhouette at HTTP 200. With it, `onerror` never fires and every
step of this chain is dead code.

Images load `crossorigin="anonymous"`; the exporter uses `useCORS: true`, so CDN
images rasterize into the PNG rather than tainting the canvas.

## Branding

- **Header** - PROSPX ball-badge (inline SVG) + the **PROSPX** wordmark, recolored
  by the accent; `eephus.io/PROSPX, <as-of date>` + a deep-link QR.
- **In-board branding** - the wordmark/URL live in the board markup itself; there
  is no separate watermark appended at export time.

## Export

- **Share** (where `navigator.canShare` supports files), **Download PNG** (2x,
  filename from the title), **Copy** (clipboard where `ClipboardItem` supported,
  else download), **Animate** (a short foil-shimmer WebM, where `MediaRecorder`
  supports it). **Esc** / backdrop closes and restores the live theme.

## Implementation notes

- Snapshot: `_gfxSet(section, kind, items, meta)` is called from each section's
  render at its filtered+sorted-array point (after filters - the farm board was
  fixed on 2026-07-18 to snapshot after its search/tendency filters like every
  other section); the modal reads `_gfxSnapshot`.
- Options live on `_gfxOpts` (`format`, `theme`, `accent`, `count`, `title`,
  `showValue`, `photos`, `logos`, `variant`, `frame`, `pack`).
- Board build: `buildGfxBoard()` -> `_gfxRow()` (per-kind normalizer, now emits an
  optional `valueSub`) + `_gfxAvatar()` (legacy row path) / `_gfxListPhotoWell()`
  (Rows list, gated on `geo.photoW`) + `_gfxPalette()`; QR via `_gfxDeepLink()`.
  Headshot URLs come from `_gfxHeadshotURL(mlbamId, boxW, boxH)`, which asks the
  CDN for that exact box, face-centred.
- `_gfxApplyModeUI()` decides which controls apply to the current mode. It runs
  on open **and** on any `layout` / `pack` change, since both change the answer
  (a rows board has a photos toggle, a tiles board does not).
- Export: `exportElementAsImage(el, { scale: 2 })`.
- Shared engine (`EEPHUS_GFX`): `open({kind:"board"|"card", module, title,
  subtitle?, url, filenameBase, accentToken?, board:{columns[], rows[], counts?,
  defaultCount?, legend?}|card})`; formats wide/portrait/tall/square/story;
  `wideOnly` columns may sit anywhere (original cell indices are preserved when
  they drop on narrow canvases - the 2026-07-18 A4 fix).
