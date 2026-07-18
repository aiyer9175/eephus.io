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
- **value column / photos / team logos** - toggles (default on).

### Photos & team logos — fallback chain

Each row's avatar is a **rectangular** portrait crop (matches the main-site
headshot), never a broken image:

1. **Prospect headshot** (`img.mlbstatic.com`) when *photos* is on and the player
   has an `mlbam_id`.
2. **Team logo** (`a.espncdn.com`) when the headshot 404s (or *photos* off and
   *team logos* on).
3. **Silhouette** - an inline-SVG person painted as the cell background.

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
  optional `valueSub`) + `_gfxAvatar()` (fallback chain) + `_gfxPalette()`; QR via
  `_gfxDeepLink()`.
- Export: `exportElementAsImage(el, { scale: 2 })`.
- Shared engine (`EEPHUS_GFX`): `open({kind:"board"|"card", module, title,
  subtitle?, url, filenameBase, accentToken?, board:{columns[], rows[], counts?,
  defaultCount?, legend?}|card})`; formats wide/portrait/tall/square/story;
  `wideOnly` columns may sit anywhere (original cell indices are preserved when
  they drop on narrow canvases - the 2026-07-18 A4 fix).
