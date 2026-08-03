# LANE G2: Top-100 GFX — measured space budget, legibility, and redesign inputs

## 0. Where the engine actually lives

- `assets/eephus-gfx.js` is NOT the top-100 engine. It is the shared modal for non-prospx surfaces (FA, MLB Projections, plus news-day and glossary source-comparison kinds) — its own header says so (`assets/eephus-gfx.js:9-11`, kinds documented :13-30), it draws canvas-native boards, and **prospx/index.html contains zero references to `eephus-gfx`** (grep confirmed, 0 hits). Prospx ships its own inline DOM+html2canvas engine.
- The top-100 engine is inline in `prospx/index.html`:
  - Modal + controls HTML: `prospx/index.html:8665-8741` (Show select incl. `<option value="100">Top 100</option>` at :8710)
  - Formats: `_GFX_FORMATS` at `prospx/index.html:33260-33266` — `portrait 1080x1350, tall 1080x1620, square 1080x1080, story 1080x1920, wide 1600x900`
  - Defaults: `_gfxOpts` at :33271 — `{ count: 50, format: "wide", showValue: true, photos: true, logos: true, variant: "compact", ... }`; session-only (never localStorage); list boards force `format = "wide"` on every open (`:35043`) but `count` is NOT reset per open
  - Row normalizer `_gfxRow`: :33454-33598; board builder `buildGfxBoard`: :34817-34944; column logic `_gfxColumnCount`: :34805-34816
  - Export: `exportElementAsImage(el, { scale: 2 })` at :35080, html2canvas wrapper at :33118-33150 (config :33131-33137, retry loop :33140+), vendored **html2canvas 1.4.1** (`vendor/html2canvas.min.js` header)

## 1. Space arithmetic (computed, Show=100, default wide 1600x900, photos+logos+value on)

Load-bearing geometry (all `prospx/index.html`):
- Board frame: `min-height:${H}px; padding:40px` (:34910). **Height is min-height only; rows never shrink to fit** — the code admits it: "long lists extend below it" (:34907-34909; same admission at :33258-33259).
- Columns: `_gfxColumnCount` (:34805-34816): `TARGET_PER_COL=24, MIN_COL_W=360, GUT=28`. Wide: `maxByWidth = floor((1600+28)/388) = 4` → **4 columns x 25 rows**. All 1080-wide formats: `maxByWidth = floor((1080+28)/388) = 2` → **2 columns x 50 rows**. Grid gap `gap:0 28px` (:34905).
- Row (:34878-34887): flex, `gap:10px`, `padding:7px 8px`, `border-bottom:1px`. Children: rank span (15px mono, `width:30px`), fv-badge (13px, `min-width:40px`, `padding:3px 10px` — `.fv-badge` at :2375-2387; global `* { box-sizing: border-box }` at :633), avatar **40x52** (`_gfxAvatar` :33677-33715, dims at :33682), name 15px bold, meta 11px mono + 18px team logo (:34877), value 13px, valueSub/$DvM+ **10px**.
- Row height = avatar 52 + padding 14 + border 1 = **67px**.
- Header (:34912-34937): title 40px `--font-retro` lh 1.05 (≈42px) + subtitle 15px + 9px margin (left ≈69px); right block QR 74px (`_gfxQR(...,74)` :34935) governs; + 16 padding-bottom + 3px rule ⇒ **≈93px**. Footer (:34939-34942): 16+1+11+~13 ⇒ **≈41px**. Rows band `padding:20px 0` (:34938).

**Total canvas, wide Top-100:** 40+93+20 + (25x67 = 1675) + 20+41+40 = **~1929px tall at 1600 wide** → exported PNG **3200x~3858** (scale 2). The "Wide 16:9" label is false for 100 players: actual aspect ≈ 1:1.21. Portrait 1080x1350 at 100: 254 + 50x67 = **~3604px tall at 1080** → PNG 2160x~7208, aspect 1:3.34 vs the promised 4:5. Every 1080 format yields the same ~3604px ribbon.

**Area budget (wide Top-100, 1x, total 1600x1929 = 3,086,400 px²; components sum exactly):**

| element | px² | share |
|---|---|---|
| 100 chips (359x67 each; colW = (1520−3x28)/4 = 359) | 2,405,300 | 77.9% |
| outer 40px frame | 275,920 | 8.9% |
| header (1520x93) | 141,360 | 4.6% |
| 3 column gutters (28x1675) | 140,700 | 4.6% |
| footer (1520x41) | 62,320 | 2.0% |
| rows-band padding (1520x40) | 60,800 | 2.0% |

**Per-chip budget (359x67 = 24,053 px²):** content 343px wide = rank 30 + badge 40 + avatar 40 + 4 flex gaps (40) + value col (~45px for "$57.3M" over "$DvM+ 108") + **name/meta block ≈148px**. Photo is 40x52 = 2,080 px² — **8.6% of the chip**.

**Text line sizes (CSS px at 1x):** title 40, subtitle 15, header url/date 12 (:34933), rank 15, name 15, badge 13, value 13, footer 11, meta 11, **valueSub/$DvM+ 10 = the legibility floor** (:34886). At a 600px-wide social timeline render, 10px scales to 3.75px (wide) / 5.6px (1080 formats); even the 15px name displays at ~5.6px on wide. Fonts are `--font-retro`/`--font-retro-mono` = "MS UI Gothic"/"MS Gothic" stacks (:234-245), half-width advance ≈0.5em, so ~19 name chars fit in 148px at 15px.

## 2. Overlap / cramping risk inventory

- **Name**: ellipsized via CSS (`white-space:nowrap;overflow:hidden;text-overflow:ellipsis` :34883). Longest names on the board (measured): "Anthony Santa Cruz de Oviedo" (28 ch), "Sherrintley Da Costa Gomez" (26 ch), "Bryce Martin-Grudzielanek" (25 ch) — truncate at ~19 ch.
- **Meta line** (`pos · org · Age x.x · level`, built :33566-33571): ellipsized (:34884). Typical "SS · MIL · Age 19.2 · AA" = 24 ch vs ~22-ch budget (148 − 18 logo − 5 gap = 125px at ~5.5px/ch) → routinely clips; multi-position strings exist up to `"3B/2B/SS"`, `"SS/2B/OF"` (8 ch; payload histogram: 4 distinct position strings ≥6 chars, on 5 players, of 37 distinct position strings).
- **Value column**: `flex:none`, **no truncation** (:34886); name block is `min-width:0;flex:1` (:34882) so a long value silently squeezes the name toward zero rather than colliding.
- **Rank**: `(i+1)` in a right-aligned `width:30px` box at 15px mono (:34879) — "100" ≈22.5px, fits; 4-digit ranks (count=all only) are 30px at MS Gothic's exact 0.5em advance — zero slack, and they overflow on the fallback mono stacks (SF Mono/Consolas ≈0.55-0.6em → 33-36px; overflow is visible, no clip on the span).
- **Title/subtitle**: the BOARD has **no shrink-to-fit** — there is zero `measureText` anywhere in prospx/index.html (grep: 0 hits), and the prospx compare card renders names at a fixed 22px (:34715). The only measure-loop precedents live in the sibling engine: `fitTxt` (`assets/eephus-gfx.js:294-299`) and the sourcecomp title-shrink loop (`assets/eephus-gfx.js:490-494`). Prospx's only adaptive-text precedent is char-count font stepping on draft-list names (`:23718`, `:26079`: >18 ch → 11px, >15 → 12px, else 13px). Long board titles wrap (header left is `min-width:0`, no nowrap) and grow the canvas taller.
- **Headshot distortion (real, current)**: the avatar `<img>` relies on `object-fit:cover` in a 40x52 box (:33702), but vendored html2canvas 1.4.1 has **zero occurrences of object-fit/objectFit** (grep of `vendor/html2canvas.min.js`: 0) — the export stretches the ~square source ~30% vertically. The codebase itself documents this limitation and fixed only the logo path (:33709-33714).

## 3. Data inventory for a board chip

`_gfxRow` receives the raw player object (active board snapshot set at `_gfxSet("active","prospect", getFilteredActives(), {})`, `prospx/index.html:17429`; items are players directly, `:33547 const p = item.p || item`). Renderer currently consumes: `player_name, mlbam_id, org, position, age, fv_close, points[last].consensus_fv_label, statline.level, dollar_dvm_plus` + `getEfv(p)` + `displaySurplusMM(p)`.

**Fields on board rows** (measured from `data/timeseries.json` `players[]` = the active pool, 4,526 rows; `total_tracked` 9,619; coverage = share non-null):
- **100%**: `player_key, player_name, org, position, eta` (object: `year, confidence, age_adj, fv_adj, health_adj, perf_adj, season_phase, ...`), `overall_rank, org_rank, org_rank_total, consensus_live_rank, consensus_live_rank_delta, fv_close, fv_close_raw, fv_high/low(+labels/dates), stock` (object: `direction, delta, basis:"xfv", strength, confidence, from/to_label, drivers[]` — drivers on 100%), `surplus` (object: `value_mm, dist, buckets, star_odds, opt_pct, valuation_set, ci, eta_years, fv_used, is_pitcher`), `dollar_dvm_plus, tool_flags, stat_flags, breakout_flag, il_status, health_profile, career_stats, trades, transactions`
- **Partial** (corrected by measurement): `mlbam_id` **94.5%**, `age`/`birth_date` **94.5%**, `current_level`/`statline_level`/`statline` **94.3%** (statline incl. `level, level_label, ops, era, fip, k_pct, ...`; `wrc_plus_level` on 1,970 rows), `acquisition` 99.1%, `statcast_plus` **78.4%**, `zone_metrics` 78.0%, `live_signal` 45.2%, `position_observed` **43.1%** (1,949/4,526), `tools` **39.9%** (object: `grades{hit,game_pwr,raw_pwr,speed,field,throw,athl,...}, composite_*, publishing_sources`), `statcast_metrics` 37.3%, `prev_overall_rank` 28.1%, `rank_movement` 6.0%, `top100_pedigree` **3.0%** (138/4,526)
- **Always null in this export**: `pitch_arsenal`, `sabermetrics` (keys present on all 4,526 rows, value null on all — do NOT plan chip content on them)

**eFV entry** via `getEfv(p)` (`:31021-31030`; `_EFV = xfv.json.by_player` at :30997, **9,338 entries**): entry keys exactly = `xfv_grade, xfv_grade_quantile, xfv_grade_realized, xfv_minus_consensus, xfv_minus_consensus_quantile, xfv_war_6yr, surplus_mm, band_p10_mm, band_p90_mm, dist, p_bust, p_bucket, consensus_fv, side, kind, tool_xfv, factors, realized_war` (verified against a live entry).

Owner-required fields: picture = `mlbam_id` (94.5% coverage; missing rows degrade to team-logo/silhouette chain) → `_gfxHeadshotURL` (:33630-33641, requests `w_${max(120, px*2)}` — currently w_120 for the 52px cell; **must raise the px arg if the photo grows**); eFV = `getEfv(p).xfv_grade` through `efvGradeDisplay`; rank = `i+1` in board order (or baked `overall_rank`). Preferred: `statline.level`/`current_level` (94.3%), `age` (94.5%), `position` (100%). Being removed: `displaySurplusMM` (:22406-22410) value and `dollar_dvm_plus` sub-line (:34886).

## 4. eFV grade display rule at this surface — VERIFIED correct

Board GFX rows lead with eFV when the board's Rank-by toggle is eFV (default: `state.sort:"xfv"` :14979; `_gradePrimary()` :32421): `_gfxRow` :33556-33565 calls `efvGradeDisplay(_px)`, which is `Math.round(efvBoardValue(x))` — **round-to-nearest** (`:32257-32260`, comment at :32252-32254: "eFV rounds to nearest, not up"). Consensus fallback uses `fvCeil` = `Math.ceil` (`:12691-12696`). This matches the owner rule (eFV nearest, consensus/tool ceiling); the footer legend states which grade is shown (`_gfxFooterNote` :33719-33731).

## 5. Aspect-ratio math for candidate 100-chip grids

Model: chrome reserve as currently built = 254px vertical (40 frame x2 + 93 header + 40 band padding + 41 footer), 80px horizontal; inter-chip gap g=12 (tighter than the current 28 gutter, realistic for photo chips). Cell = ((W−80−(cols−1)g)/cols) x ((H−254−(rows−1)g)/rows). All px at 1x; export doubles. (Table re-verified cell-by-cell.)

| Canvas (WxH) | 10x10 | 5x20 | 4x25 | 20x5 | 25x4 |
|---|---|---|---|---|---|
| 1080x1350 (portrait) | **89x99** | 190x43 | 241x32 | 39x210 | 29x265 |
| 1200x1500 | **101x114** | 214x51 | 271x38 | 45x240 | 33x303 |
| 1920x1080 (landscape) | 173x72 | 358x30 | 451x22 | **81x156** | 62x198 |
| 1600x2000 | **141x164** | **294x76** | 371x58 | 65x340 | 49x428 |
| 1600x900 (current wide) | 141x54 | 294x21 | 371x14 | 65x120 | 49x153 |
| 1080x1920 (story) | 89x156 | 190x72 | 241x55 | 39x324 | 29x408 |

Reading: for a picture-led chip (photo + eFV badge + rank + one meta line), the workable cells are **1600x2000 @ 10x10 (141x164: ~68x90 photo + 14px name)**, **1200x1500 @ 10x10 (101x114)**, **1920x1080 @ 20x5 (81x156 vertical chips)**, and **1600x2000 @ 5x20 (294x76 horizontal rows: 52x64 photo + 14/11px two-line text)**. 4x25 and 25x4 are below legibility at every size; anything on the current 1600x900 canvas cannot hold 100 legible chips (row heights 14-54px). Header-slimming yields (corrected): dropping the QR alone frees only ~5px (the 74px QR governs header content height, but the 40px title block ≈69px then governs); collapsing the header to a single slim strip (small wordmark + date inline, `_gfxHeader`-style eyebrow) frees ~50px; deleting the band frees the full 93. The formula above lets the plan re-run with any g/reserve.

## 6. Defects found (plan must fix) — all reproduced against source

1. **Format aspect is a lie for Top-100** — `min-height` only, no fit-down ladder (`:34910`, admitted at :34907-34909). Wide 16:9 exports at 1:1.21; portrait 4:5 exports a 1:3.34 ribbon. The sibling engine has a working precedent (fit ladder + canvas growth, `assets/eephus-gfx.js:307-317`).
2. **Exported headshots are stretched** — html2canvas 1.4.1 ignores `object-fit:cover` on the avatar img (`:33702`; confirmed 0 object-fit hits in `vendor/html2canvas.min.js`); code fixed only the logo path (:33709-33714).
3. **Show=All is catastrophic** — `cap = total` (:34841); the unfiltered active pool is 4,526 rows (measured; `players[]` length = `active_count`), → wide: 1,132 rows/col x 67px ≈ 76,000px board, x2 scale ≈ 152,000px — far beyond the ~32,767px browser canvas dimension cap → blank/failed export with no user-facing error (1080 formats are worse: 2 cols → ~303,000px at 2x).
4. **Dead code**: `buildGfxBoard` returns `w`/`h` that no caller reads (single call site `:34957` destructures `{board, total}` only); `_GFX_FORMATS[*].label` fields are dead (all 5 accesses read only `.w`/`.h`; modal options hardcoded at :8674-8678); `_gfxSyncControls` fallback `_gfxOpts.variant || "detailed"` (:34997) can never fire (variant initialized `"compact"` :33271, never cleared) and contradicts the real default.
5. **Duplicated branding block**: the list-board header inlines its own wordmark SVG + as-of + QR (:34917-34936) instead of reusing `_gfxWordmark` (:33740) / `_gfxHeader` (:33809) used by pack (:34855), prospect card (:34449), farm card (:34620), compare card (:34759) — two sources of truth.
6. **Empty 36px spacer** for prospect rows with no displayable grade (`lead` else-branch :34868-34871 renders a `width:36px` 13px-mono span containing "" whenever `r.fv == null && r.rank == null`; prospect rows never carry `r.rank`, so any row whose eFV, consensus label, and fv_close are all absent gets a blank spacer).
7. **Rank box tight/overflowing at 4 digits** (`width:30px` :34879) — 4 digits = 30.0px at MS Gothic's 0.5em advance (zero slack) and overflows on fallback mono stacks; only reachable via Show=All, couples with defect 3.
8. Minor: the Animate (foil-sweep) button is offered in list-board mode though the effect is card-designed (`:35050-35051` gates only on `_gfxAnimateSupported()` codec support; `_gfxApplyModeUI` :35015-35030 never touches it; intent comment :35233-35236); default `count:50` means "Top 100" always requires a manual Show change each session (:33271 vs :8710; `openGfxModal` resets title/format but not count).

Key files: `c:\Users\noah\baseball-projects\BaseballR\prospect-tracker\prospx\index.html` (engine, all line refs above), `c:\Users\noah\baseball-projects\BaseballR\prospect-tracker\assets\eephus-gfx.js` (sibling canvas engine, fit-ladder precedent), `c:\Users\noah\baseball-projects\BaseballR\prospect-tracker\vendor\html2canvas.min.js` (1.4.1), `c:\Users\noah\baseball-projects\BaseballR\prospect-tracker\data\timeseries.json` + `data\xfv.json` (field inventories).

### Verification log

Every numeric/line/formula claim was re-checked against source; arithmetic re-run. Corrections made:

1. **STRUCK false precedent cite (section 2)**: draft claimed "compare-card and sourcecomp titles shrink in a measure loop, e.g. :34491 area". Evidence: `:34491` is `buildFarmCard`'s `_GFX_FORMATS` lookup (no loop); `buildCompareCard` (:34674-34719) renders names at fixed 22px with no shrink; grep `measureText` in prospx/index.html = **0 hits**. The measure-loop precedents exist only in `assets/eephus-gfx.js` (`fitTxt` :294-299; sourcecomp title loop :490-494). Added prospx's real (char-count) precedent at :23718/:26079.
2. **Coverage numbers corrected (section 3)**: draft said "100% coverage unless noted", `position_observed` 51%, `top100_pedigree` 24%. Measured over all 4,526 `players[]` rows: `position_observed` **43.1%** (1,949), `top100_pedigree` **3.0%** (138), `mlbam_id` **94.5%** (not 100%), `age`/`birth_date` 94.5%, `statline`/`current_level`/`statline_level` 94.3%, `tools` 39.9%, `statcast_plus` 78.4%, `statcast_metrics` 37.3%, `zone_metrics` 78.0%, `live_signal` 45.2%, `prev_overall_rank` 28.1%, `rank_movement` 6.0%, `acquisition` 99.1%.
3. **`pitch_arsenal` and `sabermetrics` are null on ALL 4,526 rows** (keys present, value null) — draft listed them as available chip data; flagged as unusable.
4. **Longest-name list corrected**: #2 is "Sherrintley Da Costa Gomez" (26 ch); "Bryce Martin-Grudzielanek" (25) is #3. #1 (28 ch) confirmed.
5. **Position histogram precision**: "5 pos strings ≥6 chars" → **4 distinct strings on 5 players** (`SS/2B/OF` 1, `RHP/DH` 2, `3B/2B/SS` 1, `OF/3B/1B` 1), of 37 distinct position values.
6. **Header-slimming estimate corrected (section 5)**: draft's "drop QR/eyebrow frees ~90px" overstated — QR removal alone frees ~5px (title block ≈69px then governs the 93px band); ~50px needs a single-strip header; 93px only by deleting the band.
7. **Defect 7 nuanced**: 4 digits at 15px = exactly 30px at MS Gothic's 0.5em advance (zero slack, not strictly overflow); overflow is real on non-MS-Gothic fallback stacks.
8. **Added**: `xfv.json.by_player` size 9,338; `_EFV` load site :30997; `players[]` = active pool (`total_tracked` 9,619); html2canvas wrapper extends to :33150 (retry loop); `stock.drivers` present on 100%.

Confirmed-as-written (no change): engine location + zero `eephus-gfx` refs in prospx; all `_GFX_FORMATS`/`_gfxOpts` values; `_gfxColumnCount` constants and 4x25 / 2x50 results; row/chip geometry (67px rows, 359px cols, 343px content, 148px name block, 8.6% photo share); full area-budget table (components sum exactly to 3,086,400 px²); 1929px/3604px canvas heights, 1:1.21 and 1:3.34 aspects, 3200x3858 / 2160x7208 PNGs; every cell of the section-5 grid table; all text sizes incl. the 10px floor; font stacks :234-245; `.fv-badge` :2375-2387; `box-sizing` :633; ellipsis/no-truncation behavior (:34882-34886); html2canvas 1.4.1 + 0 object-fit occurrences; `_gfxHeadshotURL` `max(120, px*2)`; `_gfxSet` :17429; `getEfv` :31021-31030; `displaySurplusMM` :22406-22410; section-4 grade-rule chain (:14979, :32421, :32257-32260, :12691-12696, :33719-33731); defects 1-6 and 8 all reproduced (defect 4's dead `w`/`h` via single call site :34957; dead `.label` via all 5 access sites reading only `.w`/`.h`; defect 6's empty spacer reproduced from the :34868-34871 branch logic; animate gating via :35050-35051 + `_gfxApplyModeUI` :35015-35030).
