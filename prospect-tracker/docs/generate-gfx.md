# Generate GFX — social-ready graphics

The **Generate GFX** button (top global controls, next to Watchlist/Compare/Theme)
turns whatever ranked list you're viewing into a clean, PROSPX-branded PNG that's
ready to post — download or copy straight to the clipboard.

It snapshots the **current section + filters + sort** at the moment you open the
modal, so the graphic always matches what's on screen.

## Section coverage (templates)

Every ranked surface has a GFX template. The `kind` drives the per-row layout +
the footer legend:

| Section | `kind` | Badge | Value shown | Footer legend |
|---|---|---|---|---|
| Prospects | `prospect` | consensus FV | engine expected surplus ($M) | `$M = engine expected surplus value` |
| Graduates | `graduate` | final prospect FV | WAG (WAR above grade) | `WAG = WAR above grade (engine)` |
| Draft | `draftee` | consensus FV | Draft Stock+ | `Stk+ = Draft Stock+ (100 = class median)` |
| Overseas | `overseas` | consensus FV | — | `badge = consensus FV` |
| Leaderboards | `leader` | consensus FV | the selected stat | `value = the selected stat` |
| Farm | `farm` | — (farm rank) | composite farm grade | `grade = composite farm-system grade` |
| Spotlights | `spotlight` | current FV | FV Δ (recent movement) | `FV Δ = recent consensus-FV movement` |
| Int'l Amateurs | `ifa` | consensus FV | signing bonus | `$ = signing bonus` |

## Formats (aspect ratios)

Four export formats, all rendered at **2× (retina)** via `html2canvas`:

| Format | Pixels | Ratio | Use |
|---|---|---|---|
| Portrait | 1080 × 1350 | 4:5 | Instagram feed / X portrait |
| Square | 1080 × 1080 | 1:1 | Instagram square / avatars |
| Story | 1080 × 1920 | 9:16 | IG/TikTok stories, Reels |
| Wide | 1600 × 900 | 16:9 | X landscape, thumbnails, slides |

Short lists (≤12) render a single column; longer lists use two columns. Wide
always uses two columns to fill the horizontal space.

## Customization (before export)

The modal exposes a customization row — every control re-renders the live preview:

- **Format** — portrait / square / story / wide (above). **Wide (16:9) is the default** — list graphics land Twitter/X-ready with no crop; prospect-card kinds keep their own portrait/tall geometry.
- **Theme** — `Auto (site)` / `Dark` / `Light`. Forces the board (and the open
  modal) to the chosen theme by flipping the root `data-theme` while the modal is
  open; the live site theme is restored on close. Both themes are first-class.
- **Show** — Top 10 / 25 / 50 / All.
- **Title** — overrides the auto-derived headline (placeholder tracks the count).
- **Accent** — accent swatch for the badges/values/wordmark.
- **value column** — toggle the right-hand value (surplus/WAG/stat/etc.) on/off.
- **photos** — toggle prospect headshots on/off (default on).
- **team logos** — toggle team logos on/off (default on).

### Photos & team logos — fallback chain

Each row gets a circular avatar. The chain degrades gracefully so a graphic is
**never** left with a broken-image icon:

1. **Prospect headshot** (`img.mlbstatic.com`) — when *photos* is on and the
   player has an `mlbam_id`.
2. **Team logo** (`a.espncdn.com`) — when the headshot fails (or *photos* is off
   and *team logos* is on).
3. **Silhouette** — an inline-SVG person placeholder painted as the cell
   background, revealed when both images fail.

Images load with `crossorigin="anonymous"`; the exporter uses `useCORS: true`, so
the CDN images rasterize into the PNG rather than tainting the canvas.

## Branding

- **Header** — the PROSPX baseball-badge logo (inline SVG) + the **PROSPX**
  wordmark, recolored by the chosen accent.
- **Watermark** — every exported PNG carries a small bottom-right
  `PROSPX · prospx.app` watermark in a mid-gray that reads on light *and* dark,
  corner-anchored so it isn't trivially cropped without losing the image edge.

## Export

- **Download PNG** — saves at 2×, filename derived from the title.
- **Copy** — copies the PNG to the clipboard (where the browser supports
  `ClipboardItem`; otherwise falls back to Download).
- **Esc** or backdrop click closes the modal (and restores the live theme).

## Implementation notes

- Snapshot: `_gfxSet(section, kind, items, meta)` is called from each section's
  render at its sorted-array point; the modal reads `_gfxSnapshot`.
- Options live on `_gfxOpts` (`format`, `theme`, `count`, `title`, `accent`,
  `showValue`, `photos`, `logos`).
- Board build: `buildGfxBoard()` → `_gfxRow()` (per-kind normalizer, carries
  `mlbam`/`org`) + `_gfxAvatar()` (fallback chain) + `_gfxPalette()`.
- Export: `exportElementAsImage(el, { scale: 2 })` (adds the watermark, rasterizes
  at 2× with `useCORS`).
