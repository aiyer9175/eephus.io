# PX sweep, October 2026: every served mark, glyph and animation against the pixel system

Owner ask, 2026-10-02 (verbatim): "Make sure all logos/animations/glyphs are now using/displaying our new pixel art system, and continue to build upon the new pixel art system (as you planned to)".

Task PX_SYSTEM_SWEEP, built 2026-10-09 on branch wt-PX_SYSTEM_SWEEP. The system is final-pass plan section 5.7 (PX-01 to PX-24); the drawings are tools/pixel_icons.py; the motion rules are 5.7.1 items 10 to 12 with the owner's 2026-10-01 Reduce Motion amendment (every animation runs with or without the preference; the pointer parallax is the one exception).

How the inventory was taken: a scan of every served .html, .js and .css under the publish list (deploy/publish_paths.txt) plus build_site.py for characters in the arrow and supplemental-arrow, technical, box-drawing, geometric-shape, miscellaneous-symbol, dingbat and emoji blocks, the bullet and section signs, and the text glyphs used as icons ($ and the Greek delta on the player hub strip); a scan for inline `<svg>` that is not a `<use>` of the sprite; the raster marks on the publish list; and every `@keyframes`, `animation` and `transition` in site.css, the PROSPX `<style>`, the module stylesheets and the injected sheets (with the animation audit's catalogue, M01 to M29 and R01 to R19, as the checklist). Each line in a code comment was read and left alone: a comment is not drawn.

Disposition key. CONVERT: drawn from the sprite, the state component or a steps() / step-end animation now. CONVERT (FU-n): the same, but larger than this task; the follow-up spec at the end builds it. KEEP: stays as it is, with the rule that allows it. RETIRE: removed.

Counts: 68 rows. CONVERT 43 (36 built here, G36 built by HOME_8, 6 by follow-up specs), KEEP 20, RETIRE 5.

## 1. Glyphs, marks and inline drawings

| ID | Item | File : anchor | Disposition | Conversion or rule |
|---|---|---|---|---|
| G01 | GFX chip glyph U+25A4 | build_site.py `_gfx_chip_html`, `_feed_day_header` (egfx-day-chip); assets/eephus-gfx.js `chipHTML`; assets/fa.js (3); assets/projections.js (4); assets/scores.js `sc-gfx`; collegesavant/app.js and pitcher_app.js `cs-lb-gfx` | CONVERT | i-gfx at 12 px inside the unchanged `.egfx-chip-glyph` span |
| G02 | PROSPX GFX buttons, emoji U+1F4CA | prospx/index.html `.gfx-list-btn-icon`, `.gfx-card-btn-icon` (2), `.gfx-compare-btn` | CONVERT | i-gfx at 12 px |
| G03 | CollegeSavant "share card" arrow U+21E9 | collegesavant/app.js and pitcher_app.js `#cs-share` | CONVERT | i-gfx at 12 px |
| G04 | Export chip vector copy glyph (an anti-aliased 13 px path) | assets/eephus-export.js `chip.innerHTML` | CONVERT | i-export at 12 px |
| G05 | Phone menu toggle U+2630 | assets/eephus-nav.js `ensureNavToggle` | CONVERT | i-menu at 16 px |
| G06 | Sign-in glyph U+25D4 | assets/eephus-ui.js account button `data-act="signin"` | CONVERT | i-account at 12 px |
| G07 | Watchlist buttons, filled and hollow star | prospx/index.html `.watch-btn` (9 renders, 2 toggles) | CONVERT | i-watchlist (starred) and the new i-watch-off; the starred state reads in --accent-lilac, not gold (rule 7) |
| G08 | Watchlist empty states, 32 px hollow star and "(star)" in the sentence | prospx/index.html `#watchlist-empty`, farm twin | CONVERT | i-watch-off at 32 px and 12 px |
| G09 | Copy link emoji U+1F517 | prospx/index.html `#detail-copy-url`, `#chart-share` | CONVERT | i-link at 12 px |
| G10 | Close U+2715 | prospx/index.html `#gfx-close`, `.chart-fchip`, `_mtRemove`, `#ifa-clear-filter`; build_site.py `_TRADE_MACHINE_BODY` profile-group close | CONVERT | i-close at 16 px (modal) and 12 px |
| G11 | Reset U+21BA | prospx/index.html `.reset-chip` (9) | CONVERT | i-reset at 12 px |
| G12 | Compare U+21C6 and U+21C4 | prospx/index.html `#global-compare`; assets/projections.js `.proj-cmp-btn`; the player page's "Trade Machine" chip (U+21C6) | CONVERT | i-compare at 12 px; the Trade Machine chip takes i-trademachine |
| G13 | Injury discount U+2695 | assets/trademachine.js signals; prospx/index.html twin and the eFV history row | CONVERT | ev-il at 12 px |
| G14 | Current class, emoji U+23F3 | prospx/index.html IFA and draft class buttons, tables and headings (6) | CONVERT | i-hourglass at 12 px |
| G15 | Locked eFV, emoji U+1F512 | prospx/index.html eFV history row | CONVERT | i-lock at 12 px |
| G16 | Caution U+26A0 as a callout prefix | assets/fa.js (4); assets/glossary.js `.meth-caveats-title` (2); assets/trademachine.js worry label; prospx/index.html worry twin and the boot error toast | CONVERT | i-warn at 12 px |
| G17 | Player hub strip text glyphs (filled circle, $, Greek delta) in gold | assets/eephus-hub.js `MODULES`, `stripHTML`; site.css `.hub-glyph` | CONVERT | i-prospx, i-fa, i-projections at 12 px in the chip's ink (gold never draws an icon) |
| G18 | /team/ card-back web and mail vector marks | build_site.py `_SOC_SVG` | CONVERT | i-web, i-mail at 12 px |
| G19 | X, LinkedIn, GitHub and Discord marks | build_site.py `_X_SVG`, `_DISCORD_SVG`, `_SOC_SVG` | KEEP | third-party marks are never redrawn (5.7.5, "pixelated third-party marks") |
| G20 | WIRE empty fallback, a text diamond | build_site.py `_ticker_html` | CONVERT | i-news at 12 px |
| G21 | Diamond preview stage chip sigil | build_site.py `MODULE_STAGE` fantasy, betting, diamond | RETIRE | the masthead already draws i-diamond at 32 px; the chip reads "Diamond preview" |
| G22 | Homepage calendar callout sigil ("Live", "Upcoming") | build_site.py `_date_callout` (cal-tag) | RETIRE | a decorative diamond on a text tag; the words stay |
| G23 | PROSPX empty-state flag U+2690 and the error "!" box | prospx/index.html `.state-message::before`, `.state-message.is-error::before` | CONVERT | the state component's on-deck scene and E scoreboard (PX-11), one ink through a mask, tokens only |
| G24 | PROSPX GFX card and board header: the vector ball with a serif P/X (the retired mark, raw hex) | prospx/index.html `_gfxWordmark`, list-board header | CONVERT | the 22 x 22 pixel PROSPX mark (PB-05) cloned from the masthead at a whole multiple of 22 px |
| G25 | Wire glyph field in the /news/ GFX data blob | build_site.py `_collect_events` `add(...)` glyph argument | KEEP | the canvas painter's fallback when the icon table fails to load (PX-18); never drawn when it loads |
| G26 | Sort indicators (up and down triangles, small triangles) | 25 sites: franchise, hof, ledger, management, projections, trademachine, arbitration, fa, dfs, dynasty, redraft, awards-ballot, collegesavant, PROSPX | CONVERT (FU-1) | a sort-asc / sort-desc pair |
| G27 | Pagers and disclosure carets (Prev / Next triangles, Time Machine angle steps, the right and down small triangles) | prospx/index.html `.pg-nav`, `.tm-step`, `.stint-caret`, `.psh-fold-caret`; assets/trademachine.js `.pg-nav`; assets/parks.js; assets/fa.js and projections.js detail buttons; build_site.py `filter-toggle-arrow` | CONVERT (FU-1) | caret-right, caret-down, page-prev, page-next |
| G28 | Top-bar group caret | build_site.py `_nav` `.nav-caret`; the three static navs | KEEP | 5.7.1 rule 9 and owner answer PX-Q2: the top bar stays text |
| G29 | PROSPX event glyphs outside the ribbon: the FV-history timeline marker map, "debuted" and "MLB DEBUT" labels, the Time Machine change groups | prospx/index.html `TRANSACTION_KINDS` (promotion ... signed_free_agent), `.tm-delta`, `_tmChangeGroup` | CONVERT (FU-2) | the ev-* pictograms drawn here |
| G30 | Account and forum layer glyphs and emoji: bell, badges, notification icons, verify mark, markdown toolbar, modal close, vote triangles, "Share" arrow | assets/eephus-ui.js `BADGE_ICON`, `NOTIF_ICON`, `.eph-bell`, `.eph-md-btn`, `.eph-modal-close`, `.eph-vbtn` | CONVERT (FU-3) | new account-layer symbols; the layer is inert without its backend config |
| G31 | Direction arrows that are part of a value ("up 5 FV", "from #12", stock counts, delta chips) | build_site.py `row-delta`; PROSPX stock and rank lines; assets/trademachine.js | KEEP | the glyph is part of the number's text (5.7.1 rule 13; rule 7 keeps direction colour) |
| G32 | Arrows in running text and link labels ("Back to list", "All MLB News", the external-link arrow, org-to-org) | build_site.py, assets/*.js, prospx/index.html | KEEP | typography inside a sentence or a label, not an icon |
| G33 | Keyboard hints (arrow keys, return, Ctrl+K) | assets/eephus-gl.js `.qk-foot`; prospx/index.html | KEEP | keycap text |
| G34 | Verdict marks (check, ballot x, caution in a result cell; "Link copied", "Following") | assets/glossary.js, fa.js, eephus-ui.js, prospx/index.html | KEEP | the mark is the content of the cell or status (rule 13) |
| G35 | Legend marks with a printed key (graded-prospect star, best-grader star, the tools dual-marker diamond, platoon-edge dot, FV badge corner marks) | assets/glossary.js, mlbstats.js, prospx/index.html | KEEP | a typographic legend the page prints a key for; 5.7.5 rules out per-row badges |
| G36 | PROSPX ribbon unicode event glyphs | prospx/index.html `renderWhatsNew` | CONVERT | built by HOME_8 (8482e8d2), listed here as the plan asks |
| G37 | WIRE ticker separator bullet | assets/site.css `.home-ticker` item `::after` | KEEP | R18: the WIRE marquee is not touched |
| G38 | Box drawing and symbols inside code comments | everywhere | KEEP | not drawn |
| G39 | Remaining PROSPX control glyphs: GFX "Download PNG" (U+2913), "Share" (U+21EA) and "Animate" (U+2726), farm "Strength" sort (U+2195), org picker "all" hollow diamond, methodology "Export (PDF)" (U+2399) | prospx/index.html `#gfx-download`, `#gfx-share`, `#gfx-animate`, farm sort chip, `_orgPickerOptionsHTML`; assets/eephus-teampick.js; assets/glossary.js | CONVERT (FU-1) | share, animate, sort, all, print symbols |
| G40 | Headshot fallback silhouettes (anti-aliased vector) | prospx/index.html `prospect-headshot-silhouette`, list-row twin, GFX photo-well data URI | CONVERT (FU-1) | a pixel silhouette at 24 and 32 px |
| G41 | Data charts drawn as inline SVG (FV history, fan charts, scatters, ladders) | assets/*.js, prospx/index.html | KEEP | data visualization with role=img and a table; the plan's pixel viz rows (PX-14 to PX-19) are the scope, 5.7.5 rules out pixel fan charts |
| G42 | Club logos and headshots | eephus-hub.js `teamLogo`, PROSPX | KEEP | third-party marks, recognition beats texture (5.7.5) |
| G44 | Library chip section sign in gold | assets/fa.js and assets/projections.js `.chip-glyph`; site.css `.fa-app a.chip .chip-glyph` | CONVERT | i-library at 12 px in the chip's ink |
| G43 | Favicons, footer ball, share cards, wordmark, PROSPX mark | assets/brand/, build_site.py | KEEP | already the pixel system (PX-23, Q11_04 to Q11_07, PX_LOGO_ANIMATION) |

## 2. Animations and transitions

| ID | Item | File : anchor | Disposition | Conversion or rule |
|---|---|---|---|---|
| M12 | PROSPX news ribbon marquee, a continuous translate | prospx/index.html `marqueeifyTicker` | CONVERT | `steps(<one copy width in px>, end)` set with the measured duration: one whole pixel per step, same cadence |
| M13 | PROSPX in-app loaders: the steps(8) rotating square and its opacity fade | prospx/index.html 12 `state-message is-loading` sites | CONVERT | the lamp loader (EephusState loading, px-lob 1.6 s step-end) through `pxLoadingHTML()` |
| M14 | FV badge edge pulse, ease-in-out | prospx/index.html `fvIndicatorPulse` | CONVERT | 2.4 s step-end: a lamp at full, then at 30% |
| M15 | Breakout edge colour cycle, ease-in-out | prospx/index.html `fvBreakoutColor` | CONVERT | 2 s step-end |
| M16 | Recent-debut banner dot, a soft ring growing by sub-pixels | prospx/index.html `grb-pulse` | CONVERT | a lamp blink, 2 s step-end, the WIRE blip's idiom |
| M17 | Freshness dot ring | prospx/index.html `freshPulse` | CONVERT | a lamp blink, 2.4 s step-end |
| M18 | Foil shimmer (FV 50) | prospx/index.html `foil-shift 8s` | CONVERT | steps(32, end) |
| M19 | Chrome shimmer (FV 55) | prospx/index.html `chrome-shimmer 4.2s` (3 hosts) | CONVERT | steps(16, end) |
| M20 | Holo shift (FV 61) | prospx/index.html `holo-shift 6s` and `5s` | CONVERT | steps(24, end) and steps(20, end) |
| M21 | Legendary shift (FV 70) | prospx/index.html `legendary-shift 3s`, headshot `holo-shift 3s` | CONVERT | steps(12, end) |
| M22 | Headshot outline pulses | prospx/index.html chrome, holo and legendary `-headshot-pulse` | CONVERT | 2 s step-end |
| M23 | Glossary card highlight, ease-out | assets/site.css `.gl-app .glossary-card.is-highlighted`; prospx/index.html twin | CONVERT | 1.8 s steps(4, end): the tint dims in four lamp steps |
| M24 | GFX busy spinner, a rotating ring | prospx/index.html `.gfx-busy-spin` | CONVERT | the lamp loader markup inside `#gfx-busy`, its label in `.gfx-busy-label` |
| M25 | /team/ card flip | assets/team.css `tc-turn-a/b` | KEEP | already whole-pixel steps (TEAM_2_CARD_BACKS, steps(3)) |
| M26 | Export chip and toast, GFX flash | assets/eephus-export.js injected sheet; assets/site.css `.egfx-flash` | CONVERT | chip .12 s steps(3, start); toast .15 s steps(4, start) (8 px in 2 px steps, the first at once); flash .2 s steps(4, start) |
| M27 | Glossary tooltip show delay | assets/eephus-gl.js | KEEP | a delay; nothing moves |
| M28 | Short hover and focus transitions (colour, background, border, caret turn) | assets/site.css and module sheets | KEEP | functional feedback; 5.7.1 rule 4 accent states are colour only |
| M29 | Smooth scrolling | prospx/index.html `html`; assets/sports-page.css reduce rule | KEEP | open owner question RM-Q1 |
| M30 | WIRE marquee and blink | assets/site.css `ticker-scroll`, `ticker-blip` | KEEP | owner exemption R18; the blink is already step-end |
| M31 | Starfield twinkle and parallax | assets/eephus-bg.js | KEEP | owner exemption |
| M32 | Pixel pieces already in the idiom: wordmark pitch, lamp loader, 404 foul ball, card-foil edge sweep, tc-holo, model-updates lamps, scores end-marker blink | site.css, team.css, model_updates.css, scores-pixel.css, prospx | KEEP | step-end or steps(); the scores blink's Reduce Motion stop waits on SCORES_7b OWNER-Q4 |
| R01 | `@keyframes prospx-spin` and the steps(8) square rule | prospx/index.html | RETIRE | replaced by M13 |
| R02 | `@keyframes state-pulse` | prospx/index.html | RETIRE | replaced by M13 |
| R03 | `@keyframes gfx-spin` and `.gfx-busy-spin` | prospx/index.html | RETIRE | replaced by M24 |

## 3. New sprite symbols (tools/pixel_icons.py, 12 x 12 cores in the scorebook ink idiom)

MLB news families (site-pass plan 3.3; HOME_7 swaps them into `_WIRE_TYPES`): ev-mlb (home plate), ev-callup, ev-dfa, ev-claim, ev-release, ev-retire, ev-suspend, ev-award, ev-option, ev-qo, ev-il-off. The aliases ev-draft (px-draft) and ev-intl (px-intl) were already in `ICON_FOR` (HOME_2).

Controls: gfx, export, link, account, close, reset, menu, watch-off, compare, hourglass, lock, warn, web, mail.

Sprite: 79 to 104 symbols (25 new), 23,466 to 30,050 bytes (budget 40,960).

## 4. Plan rows (PX-01 to PX-24)

Built before this task: PX-01 to PX-14, PX-16 (homepage and spotlight), PX-17 to PX-24 (FIX_REPORTs PX_A to PX_E, PX_VIZ_COLOUR, Q11_01 to Q11_10, PX_LOGO_ANIMATION). PX-15 stays skipped (the Club Ledger NEVER list: room under the threshold reads as cap space). Completed here: PX-11 and PX-12 for PROSPX's 12 in-app loaders and every PROSPX empty and error state (the R01 half the PX_C pass left). Open: PX-16's later half, the PROSPX `_miniSparkline` (FU-4).

## 5. Follow-up task specs

The PX_SYSTEM_SWEEP report carries each in the dispatch form. In short:

- FU-1 Controls and carets: G26, G27, G39, G40. Draw sort-asc, sort-desc, caret-right, caret-down, page-prev, page-next, share, animate, print and a 24 / 32 px silhouette; swap the 40-odd sites through window.EephusIco (generated pages and modules) and pxIcoHTML (PROSPX); keep every aria-sort, aria-expanded and label; update the sort-header tests that read the glyph.
- FU-2 PROSPX event glyphs: G29. The FV-history timeline markers (an SVG text glyph per event) become `<use>` of the ev-* symbols at 12 px (resolved inline for the GFX export, as `_gfxResolveVars` does), the Time Machine change groups and the "debuted" labels take ev-debut, ev-up, ev-down; read the event code through EEPHUS_HUB.wireType.
- FU-3 Account layer: G30. Bell, badge, notification, verify, markdown and vote symbols; swap in assets/eephus-ui.js; render in the PREVIEW store.
- FU-4 PX-16 second half: the PROSPX `_miniSparkline` becomes the whole-pixel step line `build_site._fv_sparkline` draws (one run per snapshot, grade rules at multiples of 5), with its test.
