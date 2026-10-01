# Master plan 2026-08-03: model/metric calibration audit + mobile audit + MLB list-display polish

Written for Claude Opus 5 to execute. Three lanes, one preflight, one verification
protocol. Every file:line below was verified against the working tree on
2026-08-03 (HEAD 7626fd0). Where a claim matters, re-verify before acting; the
repo's history shows static diagnosis being wrong often enough that the standing
pattern is "prove it by executing the code."

Read before starting (memory + repo docs, in this order):

1. memory/execution-2026-08-03-gfx-minter.md (latest session, gotchas)
2. memory/fg-board-ingest-runbook.md (the FG 2026 board just landed at 7626fd0)
3. docs/RUNBOOK_2026-08-03.md (what the box owes; known reds; registered-not-fixed)
4. docs/EFV_GATE_STANDARD.md (MDE floors; every model verdict must clear these)
5. docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md (the six "+" conventions)
6. docs/computed-stats-handoff-2026-08-01.md (verified per-stat reproduction)

## 0. State of the world (verified 2026-08-03)

- Both previously open eFV P0s are FIXED on main (commit 7967b6e):
  - efv_score.py:2066 run_backgrade NameError (r -> row): fixed, empirically
    re-verified (backgrade 32.6s/5,072 players; regen_all 108.4s end to end).
  - efv_score.py:1292 resolved-seam Platt no-op: fixed; now reads
    `provisional=not src.get("milb")` off the matrix row, matching the spec in
    tools/_prem_odds.patch:30-31.
- The full eFV artifact chain sits on ONE timestamp (2026-08-03 18:21) and one
  calibration vintage (isotonic-real-v6-evframe-2026-07-31). xfv.json meta
  live_lambda = hit 0.70 / pit 0.57.
- The box owes a regen (RUNBOOK order: run_monthly -> `python efv_export.py` ->
  run_monthly --rebuild-only). That is box-side; local work must not assume it.
- Beta is DO NOT TOUCH (owner instruction 2026-08-03; rollback recovery is a
  separate, owner-gated decision, see memory/beta-rollback-recovery-2026-08-01.md).
- Suite baseline: 2,853 passed / 3 pre-existing reds:
  1. test_team_outlook_calibration::test_recenter_remainder_near_zero
     (deliberate recenter red, 3.09 vs bar 3.0)
  2. test_overseas_stats::ScraperRoundTrip::test_returns_npb_seasons
     (FG parser returns 0 rows from cached page; Lane A work item A4.3)
  3. a documented a11y cold-load flake that passes 3/3 alone
  test_efv_export::test_xfv_golden_fingerprint fires on any intentional eFV
  regen and wants restamping once output is accepted; that is expected behavior.
- Uncommitted working-tree churn (tjstats_movers.json, tj_surgery.json, etc.) is
  nightly TTL refresh noise. Leave it; never `git add -A` (EXTERNAL-REVERTER
  gotcha: stage by explicit path only).

## 0.1 Phase 0 preflight (do these first, they unblock everything)

P0-A. Run the suite once to pin the baseline (expect the reds above). Any NEW
red you introduce must be fixed before the commit that caused it lands.

P0-B. Fix the stale CSS cache stamps NOW, or no frontend change is verifiable
on the hand-maintained pages:
- prospx/index.html:57 has `site.css?v=20260730`
- collegesavant/index.html:27 has `?v=20260730`
- collegesavant/pitcher_index.html:27 has `?v=20260709`
- site.css last changed 2026-07-31 (commit 2232925), so all three already serve
  week-stale CSS through nginx's 7-day max-age on /assets/.
Fix: bump all three to today, and close the class permanently: extend
test_asset_versioning.py to FAIL when site.css's content hash changes without
the three hand-maintained stamps changing (record the pairing in the test, or
have build_site.py rewrite the `?v=` in the three hand-maintained files the way
_asset_ver() (build_site.py:48-53) stamps generated pages; the second is better
because it removes the hand step forever). Every later CSS commit must include
regenerated pages: run `python build_site.py` after ANY site.css edit.

P0-C. Two trivial truth fixes (they mislead every future reader):
- efv_odds_calibration.py:4 docstring still says "NOT YET WIRED IN". It is
  wired at all three seams (efv_score.py:1292, :1812, :2191). Rewrite it.
- site.css:2664-2674 comment calls .mlb-rank "the PROSPX diamond read as a
  circle"; the global radius kill (site.css:126) makes it a square. Fix the
  comment or the glyph (Lane C decides the glyph; fix at least the comment now).

## Standing rules that bind every lane

- Measurement before recommendation. On 2026-07-31 a plan-recommended and
  owner-approved surplus re-key was REFUTED by measuring first. Any model
  change: measure on the existing harness, clear docs/EFV_GATE_STANDARD.md MDE
  floors, ship only measured wins, commit losses as loss ledgers.
- CLOSED lanes. Do not re-open, re-test, or re-recommend: K-prior; deep Savant
  into proj_lgbm; surrogate labels (both sides; pitcher lane SPENT); old-cohort
  mlbam id backfill; TJ-surgery feature; park/age/velo/decay eFV lanes; B3
  level blend; E1 hitter arm; arm gate; cross-outlet tool normalization;
  xfv_proxy power features; REM+ SwStr overhaul (X-R1); SEM+ GB adjust (X-S3);
  type-conditioned consensus weights; surplus re-key onto xfv_grade; board
  basis reversion (consensus FV is not cross-side comparable); defense into
  prospect xFV. Each has a committed loss ledger; the ledger is the answer.
- v6 dollar calibration (value_framework_config.yaml:525-544) ships a
  DOCUMENTED 18% held-out MAE regression accepted on an EV objective by owner
  decision. Do not relitigate the objective. Auditing whether every consumer
  actually wants a conditional mean (A2.3) is in scope; flipping the objective
  is not.
- Owner display rules: FV/tool grades display CEILING; eFV and "+" stats round
  to nearest. No em-dashes in user-facing prose (strip_emdashes --check +
  copy_lint gate). bWAR site-wide. Sharp corners: border-radius 0 globally.
  Keep the Topps-Chrome refractor dark theme; deepen, never replace. Tickers
  and the starfield twinkle deliberately IGNORE prefers-reduced-motion (owner
  ask): gate mobile perf work by pointer/width, never by reduced-motion.
  Farm grid must NOT get overflow-x (the ≤900 column-drop at
  prospx/index.html:6847-6856 is the honored pattern; preserve it).
- Pipeline rules: value_framework.py edits need --emit-snapshots; any basis or
  export-semantic change needs the TWO-pass regen (run_monthly, efv_export.py
  by hand, run_monthly --rebuild-only); never sum ML quantile points; Savant
  ingest arg is `year` (`season=` is silently ignored); homepage drawer lives
  in build_site.py, never edit generated index.html directly.
- Tools: node exists via `ELECTRON_RUN_AS_NODE=1 ".../Code.exe"` (v24). ruff
  0.12.0 exists; `--select F821` has caught 3 real bugs; ruff honors only the
  LAST --exclude flag (comma-join). pytest: conftest git-restores data churn at
  session end; tools/ is excluded from collection by design.
- Adversarial verification: for each lane's findings, verify by running the
  real functions before shipping a fix (3 of 5 agent verdicts were wrong in one
  past session; executing the code caught all 3).

---

# LANE A: model, module, and metric accuracy/calibration audit

Ordered by expected value. A1-A3 are the core; A4 is structural safety; A5 is
owner-flagged stretch. Every ship follows the standing rule: registry row +
eval artifact + freshness map entry, enforced by test_model_registry.py and
test_methodology_freshness.py.

## A1. Calibration truth (highest value in the repo)

A1.1 The live calibration monitor measures a basis the site no longer serves.
efv_reliability.py:123 calls `vf.p_bucket_given_fv(grade, is_pit)` WITHOUT
`efv_odds_calibration.recalibrate_bucket()`. The public "model grading itself"
card (assets/glossary.js:1276/:1382/:1462, guarded by
test_reliability_surface.py:51-57) therefore reports the PRE-fix distribution:
bust ECE 0.128 against a tripwire of 0.14 that was tuned to the old
miscalibration band ("tripped: false"). Since 7967b6e all three scoring seams
apply the Platt map, so the monitor is diagnosing a corrected defect.
Fix: compute and emit BOTH curve sets (raw and recalibrated) in
data/xfv_reliability.json; surface the recalibrated one as the headline;
re-derive the tripwire threshold from the post-fix expected band (justify the
number in the artifact); keep the raw curve as a drift reference. Update the
glossary card copy (copy_lint applies). Add a test pinning that the served
curve set is the recalibrated one.

A1.2 Score the newly-recalibrated resolved cohort. 925/1,927 hitter and
941/2,063 pitcher resolved rows (~48%/46%) started receiving a strong
flattening (p_bust 0.20 -> 0.55; 0.92 -> 0.84) on 2026-08-03 and NOBODY has
scored the corrected probabilities against realized outcomes. Run the paired
bootstrap Brier/logloss gate (the harness exists: the original fix was gated at
Brier +0.03953 CI95 [+0.01655, +0.05934]) on the CURRENT tree, resolved cohort,
both sides. Outcomes: (a) confirms, commit artifact + registry note; (b)
refutes, escalate to owner before touching (the Platt constants would then be
wrong in the other direction).

A1.3 Platt slope drift. efv_odds_calibration.py:84-90 records per-fold slopes
falling monotonically 0.470 / 0.392 / 0.289 / 0.276 as the training window
grows. A monotone trend in a "fixed constant" is a re-fit trigger, not a
stability proof. Re-measure on the current frame; if the trend continues,
propose (do not ship without a gate win) a window-disciplined re-fit. Document
either way in the eval artifact.

A1.4 Per-year WAR band coverage. docs/archive/REVIEW_QUEUE.md item 13: displayed totals
covered 0.63 vs the 0.80 design; totals were dropped rather than fixed, and the
per-year bands still carry the defect (survived-only coverage ~0.55, driven by
a strictly-positive decayed p10 while ~40% of real seasons are <=0 WAR).
proj_eval.py already measures pooled AND survived-only coverage plus pinball;
the instrument exists. Measure current state, then gate a candidate fix
(letting p10 reach <=0 along the decay path is the obvious one; it was the
root cause named in the Phase-0 findings). Ship only on a pinball/coverage win
on held-out years; rerun proj_eval.py and commit the artifact.

## A2. Basis-coherence audit (where the money crosses scales)

A2.1 Three grade bases live in one artifact: xfv_grade (board, outcome curve),
_odds_grade (realized-implied, drives p_bucket/p_bust, deliberately not
re-keyed, efv_score.py:1268-1273), and xfv_grade_display (quantile map +
F-SIDE-FIX; surplus dollars are re-priced on THIS via
_reprice_surplus_on_display, efv_score.py:925-978). Audit every consumer
(efv_export.py:141-164, storage.py board fields, trade machine, projections,
FA, prospx JS) and verify none reads a value fitted on one scale at another.
Deliverable: a short basis map appended to ARKMETRIC_SCALE_CONVENTIONS.md or a
sibling doc, plus a test for any crossing found. Fix crossings as P1 bugs.

A2.2 Arkmetric convention pooling. Six incompatible "+" conventions ship under
one 100-anchor look (conventions doc). Audit every composite, sort, filter, or
leaderboard that pools two metrics for a cross-convention mix (the known trap:
HEM+ carries a 2.28x spread gain that SEM+/REM+ do not, on adjacent tabs of
/mlbstats/). Grep candidates: any sum/average/rank over two different *_plus
keys in exports and in assets/*.js. Do NOT re-scale metrics (tool
normalization is a closed lane); fix only actual pooling bugs, and improve
user-facing disambiguation (glossary/tooltip copy) where adjacent surfaces
imply comparability.

A2.3 v6 consumer audit. For each surplus consumer (board, trade machine,
/projections/ surNpv, FA), confirm it semantically wants an EV (mean) number.
Any consumer that ranks or thresholds on the calibrated dollars is fine; any
that treats them as a median or a floor is a finding. Document; fix only clear
bugs.

## A3. Registry and eval hygiene (the standing rule, enforced)

A3.1 xfv_backgrade has NO eval artifact of its own, is provisional, is live on
every debuted/graduated prospect, and OVERWRITES most resolved rows in the
merge. It is also the seam that silently died for two days. Build a real eval:
backgrade grades/WAR vs realized outcomes on the resolved cohort (the labels
exist in the matrices), forward-disciplined. Register it; verdict per results.

A3.2 Refresh the stalest live-surface evals, oldest first:
trade_machine_surplus (39d; /trademachine/ ordering; bayes_trade_value.py
self-flags "latent-P0 on any coverage" at :690), statcast_plus (53d; the
component diagnostic already suggests reweighting, docs/archive/REVIEW_QUEUE.md item 12),
farm_grades (53d), draft_slot_curve + fa_qo_pick_tax (53d), fa_dpw_series
(53d), mlb_projections_prospects (52d). Rerun each on its existing harness;
update registry verdicts honestly; ship measured wins only.

A3.3 Make the freshness system able to fire: model_registry.py:45 STALE_DAYS
= 240 while the oldest artifact is 53d, so the stale flag is structurally
inert. Lower to 90 (advisory), and add a suite check that any VALIDATED model
with a live surface whose artifact exceeds the threshold goes visibly stale in
the registry render. Also fix efv_il_severity: its "artifact" is a .md that
validate() never parses; either produce a JSON artifact or add an explicit
allowed-type with a validation path.

A3.4 The C-list gap rows that make quantitative claims with null artifacts:
surplus_downside_risk, prospect_greeks, draft_war_room, xrem_plus/xsem_plus,
leverage_board. For each: cheapest honest eval on existing data, or an explicit
registry note stating why descriptive-only is the accurate verdict (the
governance doc's position), so the gap list goes to zero either way.

## A4. Structural safety (the recurring failure classes)

A4.1 The best-effort wrapper that hid the P0: run_monthly.py:741-747 swallows
regen-tail crashes by design ("a failure must not abort the run"). Keep the
never-abort property but make failure LOUD: write a failures ledger into the
run summary artifact, and add a freshness tripwire test comparing
xfv_backgrade/history mtimes against xfv_scored mtimes (>24h divergence =
red). The 07-31 incident becomes structurally impossible to miss.

A4.2 BOARD_RANK_BASIS_EPOCH (storage.py:4765) is hand-maintained; the comment
at :4796 admits nothing forces a bump. Add a guard: persist the
board_basis_fingerprint (storage.py:4836) alongside the epoch (in a small
committed stamp file); test fails when the fingerprint changes without an epoch
bump. Same class as the calibration-vintage test that already exists
(test_calibration_vintage.py); copy its shape.

A4.3 Silent-empty parser sweep. The repo's recurring failure class is parsers
returning [] instead of raising (the FA 2027 board freeze; the current NPB
red; the cached-page trap). Sweep scrapers.py, fangraphs_csv.py,
overseas_stats.py, spotrac.py for `return []`-on-failure shapes; convert to
raise-or-flag with an explicit empty-page guard (the fa_pipeline
empty-available-page guard is the precedent). Fix the NPB parser against its
cached page if the page shape supports it; otherwise mark the test xfail with
a dated reason and file the parser as data-blocked. This should turn known red
#2 green or honestly quarantined.

A4.4 Regen-order dependency: fa_export reads mlb_projections.json and degrades
silently if run out of order (RUNBOOK:53-61). Add a staleness assertion inside
fa_export (mlb_projections.json mtime within N hours, warn-not-fail) so the
intended degradation is at least visible in logs.

## A5. Owner-flagged stretch (in scope if time permits, each needs its gate)

- Star-rental premium: prorated RoS WAR through the full-season convex curve
  under-prices deadline rentals. Needs a measured premium from real deadline
  trades before shipping anything.
- The 361 no_contract pre-arb vets are unpriced on the trade board (largest
  open value). A real model with a real gate: arb-fraction pricing exists in
  value_framework; scope, measure, gate.
- _gradePrimary() overload (prospx returns "xfv" for any sort != "fv") is a
  frontend state bug, needs a browser: do it inside Lane B/C's Playwright
  passes (state.debutGrade is the named precedent).

---

# LANE C: MLB Projections / MLB Stats / MLB Free Agency list displays

(C before B in execution: these are the same surfaces Lane B verifies on
phones; land the display upgrades first so the mobile pass validates the new
layout, not the old one.)

Owner ask: polish and improve the list displays, no overlap/bleeding/density
issues, upgrade everything to be more on theme. "On theme" = the prospx/site
visual language: token palette both themes, sharp corners, refractor accents,
diamond rank glyphs, org-color identity, one table dialect, EM_DASH nulls.

## C1. Foundation: make the theme actually reach these surfaces

C1.1 Cards are invisible. .mlb-card background is
`var(--panel-bg, var(--card-bg, transparent))` (site.css:2628) and NEITHER
token is defined anywhere, so every Projections and FA board card renders
transparent over the grain field, while fantasy's .ff-card gets a real
`var(--bg-secondary)` fill (site.css:2746). Define the tokens (or point
.mlb-card at --bg-secondary) in BOTH themes, add a hover state consistent with
the tables' (site.css:1468/:1699).

C1.2 The org stripe is dead on both boards. .mlb-card::before falls back
through `var(--org-color, var(--accent, currentColor))` (site.css:2637-2643);
--accent is undefined site-wide, orgColor is absent from ALL 1,323 rows of
mlb_projections.json (projections.js:1006 guards on it), and fa.js never emits
it (verified zero occurrences). Emit org colors: add orgColor to proj_export
rows (an org->color map exists for prospx; reuse it) and set `--org-color`
inline per card in both projections.js and fa.js. FA options keep their gold
override (site.css:2862) but layered ON the org color, not instead of it.

C1.3 Kill the off-token spots:
- projections.js:744 verdictBadge: raw #0b0b0b + dead border-radius:10px in an
  inline style. Replace with a CSS class using --text-on-accent (verify the
  token exists first; define it if not) and no radius.
- site.css:1543-1546: FA verdict pills use baked LIGHT-theme rgba washes
  (rgba(31,122,58,.08) / rgba(185,28,28,.08)) that do not flip in dark theme.
  Replace with the color-mix pattern already used two rules below
  (site.css:1565: `color-mix(in srgb, var(--accent-gold) 14%, transparent)`).
- site.css:1725 .bp-slot-adv hardcoded #1F7A3A fallback: drop the fallback.
- Dead radius declarations (site.css:2627/2642/2669/2687/2789, mlbstats 1644):
  delete them; the design is square, own it.

C1.4 Rank glyph: .mlb-rank renders as a flat square while prospx/fantasy use
the rotated-45deg diamond with an org-color border (.ff-rank,
site.css:2759-2771). Adopt the diamond on Projections and FA boards; feed it
--org-color from C1.2. mlbstats tables get a rank column treatment consistent
with it only if it does not widen the tables (C2.3 constraint).

## C2. Structural fixes (overlap, bleed, broken stickiness)

C2.1 Sticky that never sticks, everywhere, one root cause: an
`overflow-x:auto` ancestor becomes the sticky containing block with
content-height, so `top:0` never engages. Instances:
- .mlbstats-table th (site.css:1690) inside .mlbstats-scroll (1652): on a
  610-row hitter board the header scrolls away immediately. Highest impact.
- .fa-app .detail-table thead th (1461) inside #fa-rows (1483) or
  .fa-board-main (1585).
- .fa-board-rail sticky (1586) inert for the same reason, while the IDENTICAL
  projections rail sticks because #proj-rows carries no overflow. Two boards,
  same markup, different behavior.
Fix pattern: give the scroll container a bounded height (e.g. max-height:
calc(100dvh - <chrome>) with overflow:auto both axes) so sticky headers engage
against it, OR move the overflow wrapper to a deeper element that excludes
thead. Decide once, apply to all instances; verify in-browser both themes.
For #fa-rows, drop the blanket overflow-x and wrap only the actual tables
(fits/archive/model views), which restores the rail's stickiness for free.

C2.2 Team Outlook table pans the document at 721-1000px: renderTable writes an
11-12 column nowrap table straight into #proj-rows (projections.js:695) and
the only escape hatch fires at <=720 (site.css:1854). Wrap the table in its
own overflow container at all widths (this is a table, not the card board; the
farm-grid no-overflow rule does not apply here).

C2.3 mlbstats identity loss: 19-24 column nowrap tables (REL_COLS
mlbstats.js:184, HITTER_COLS :1282, STARTER_COLS :818) at ~1500-1900px natural
width scroll horizontally at every desktop width with NO frozen name column.
Freeze it: `position:sticky; left:0` on td.mlbstats-name + its th (works
inside an overflow-x container; needs an opaque background from C1.1's token
work and a z-index above cell content). Also stop the prov/qualification badge
being the first thing ellipsized: move .bp-prov BEFORE the ellipsizing span or
give the name cell a two-line grid (name+team on line 1, role+prov chips on
line 2), raising max-width:260px (site.css:1694) as needed within the frozen
column budget.

C2.4 Row-1 clipping on the card boards: .proj-card is a fixed 104px with
overflow:hidden (site.css:2855/2848-2856) and .mlb-sub wraps but row-gap:0
(2885) cuts a wrapped second line mid-glyph. Either ellipsize the sub-line
(nowrap + ellipsis on the container) or let the card grow by one sub-line
(min-height instead of height; contain-intrinsic-size updated to match). FA's
108px card + 2-line clamped status (2857/2879-2884) gets the same decision;
add the standard `line-clamp` alongside -webkit-line-clamp.

C2.5 Chip tape squeeze: 7 chips at flex:1 1 0 (site.css:2685) ellipsize their
LABELS ("downside WAR", "yrs P10-P90") into meaninglessness at 1101-1250px.
Give .mlb-chip a min-width floor (~72px) and let .mlb-tape-inner scroll the
overflow (it already has overflow-x:auto, 2683); shorten the two longest FA
labels; keep .mlb-chip-ct's 1.8fr allowance (2896).

C2.6 Fits-table mini-bars: .fa-cbar's absolutely-positioned 9px label overlay
(site.css:1598-1602) overlaps the bar edge for wide values. Give the label a
right-aligned inset with overflow:visible guard, or move the value outside the
bar. Also the blockedBy chip run (fa.js:1154) needs min-width:0 handling in
its cell.

C2.7 Async inserts must reserve space: projections.js injects the `$ FA` chip
into a zero-width .proj-fa-slot (projections.js:1010, 1152-1161) inside an
already-full fixed-height clipped card. Reserve the slot's box like FA does
for headshots (fa.js:259 + site.css:2560).

## C3. Unification (three surfaces, one product)

C3.1 One table dialect. .mlbstats-table (site.css:1686-1699) vs .fa-app
.detail-table (1448-1470) disagree on font-size (12.5 vs 12), padding (6x9 vs
6x10), header alignment (right vs center), header bg (--bg-secondary vs
--bg-tertiary) and header color. Define ONE shared spec (a .eephus-table block
or unify on .detail-table), apply to both, keep numeric columns right-aligned
by class not by dialect.

C3.2 One number vocabulary. fa.js:29-44 formatMetric is the reference
implementation. projections.js reimplements money()/fmtWar() locally;
mlbstats.js has its own f1/f2/fInt/fPct/fSigned family AND emits "" for null
(mlbstats.js:351) where the other two emit EM_DASH. Extract formatMetric to a
shared asset (or copy verbatim with a sync test) and adopt the EM_DASH null
convention on mlbstats.

C3.3 One control language on /mlbstats/. Three nav tiers at three font sizes
with three active treatments (site.css:1620/1630/1640), and the season pills
are the site's only solid-fill active control (1648) with a dead 999px radius
(1644). Restyle all three tiers on the house chip (.fa-app button.chip,
1424-1447: outline + iridescent underline active state).

C3.4 Merge the double sort strip on the card boards: .mlb-sortbar (7 tape
keys) sits directly above mlb-card-head (aligned column headers), two
near-identical uppercase strips costing ~60px of chrome
(projections.js:1089-1095; fa.js:655-667). Fold the tape keys into the header
strip (a second row inside one visual band) or into a sort dropdown; whatever
lands must have a phone rule (Lane B item B2.4 covers the <=640 behavior).

C3.5 De-inline projections.js: 93 inline style= occurrences vs 15 (fa.js) and
9 (mlbstats.js). Move the repeated ones (compare button projections.js:995,
verdict badge :744, warmap cells) into classes. Inline styles are invisible to
the theme system and to test_no_hardcoded_colors.

C3.6 Density polish: raise .proj-tag off 8px to >=10px (site.css:1826);
reclaim the 92px .bp-slot role track when rendering 1-9 lineup digits
(site.css:1719, mlbstats.js:1607: pass a narrower track or a modifier class);
change .bp-slot 1fr to minmax(0,1fr) (1719).

## C4. Lane C verification

- Playwright before/after screenshots: each of the three surfaces x
  1280/768/390 widths x light/dark; zero console errors; zero document-level
  horizontal scroll; sticky headers verified by scripted scroll.
- Guard tests after CSS: pytest test_design_tokens.py
  test_no_hardcoded_colors.py test_index_html_loads.py; extend
  test_no_hardcoded_colors to cover assets/projections.js inline styles if
  feasible (cap-and-ratchet like the prospx cap).
- Rerun `python build_site.py` (cache-bust) in every CSS-touching commit.
- Tooltip regression: [data-gl] terms inside the new scroll containers
  (eephus-gl positions from viewport coords and does not track container
  scroll; verify tips stay attached after C2.1's container changes, fix
  placement math in eephus-gl.js if they detach).

---

# LANE B: mobile audit + improvements

The mobile recon produced a ranked 15-item list; B executes it in dependency
order. The stamp fix (its #1) is already Phase 0. Canonical breakpoints: the
documented 4-tier policy for new CSS (<=640 / 641-1024 / >=1025 / >=1440);
phone baseline 390x844.

## B1. Global mechanics (site-wide, one commit each)

B1.1 Touch targets on module surfaces. .fa-app button.chip is ~26px tall and
SHRINKS to ~23px at <=720 (site.css:1424-1427, 1851), on the primary filter
control of seven surfaces. Apply the PROSPX pattern (prospx/index.html:
8388-8415, 44px targets at <=640) to: .fa-app chips, .gl-app chips (1909),
.news-app chips (1025), .mlbstats-sectionbtn/-tab/-season (1625/1635/1645),
.hub-chip (2520), .mlb-card-head [role=button] (2944), collegesavant .cs-tabs
a (styles.css:56). Pair each with the swipe-strip pattern below so bigger
chips do not stack 6 rows deep.

B1.2 Swipeable filter rows. site.css:2572-2594 already implements the masked
horizontal scroll strip for .news-app/.gl-app/.mlbstats-sectionnav. Extend the
selector list to: .fa-filter-bar (25 controls currently wrap ~140px deep,
1570), .mlb-sortbar (2781, no phone rule at all), .mlbstats-tabs and
.mlbstats-seasons, prospx filter rows where applicable.

B1.3 iOS input zoom. Every text input except one (prospx/index.html:8259) is
below 16px and zooms the page on focus; 13+ rules inventoried (site.css:2287
qk-input 15px, :914, :1906, :1681, :1810, :2359; build_site.py:2842;
eephus-account.css:152; prospx:3411, :1344, :1521, :25539; collegesavant
styles.css:204-215). Add a coarse-pointer/<=640 rule raising font-size to 16px
on focusable text inputs and selects site-wide (one shared block in site.css +
the prospx and collegesavant equivalents), adjusting padding so the controls
do not balloon.

B1.4 The 641-1024 nav gap. .eephus-links is a scrollbar-less nowrap swipe
strip (site.css:349-354): links past ~4 are undiscoverable on tablets and
landscape phones, the exact failure the <=640 hamburger fixed. Either extend
the hamburger breakpoint to <=1024 or add a visible affordance (fade + arrow,
or allow wrap at 641-1024). Update eephus-nav.js's matchMedia (eephus-nav.js:
29) to whatever breakpoint lands, and keep the homepage drawer
(_HOME_DRAWER_JS, build_site.py:2476-2509) consistent; consider unifying the
two drawers (recon item 11) if the diff stays reviewable, otherwise document
the pairing in both files.

B1.5 Viewport units + safe areas. Replace 100vh with 100dvh at site.css:252
(starfield canvas), :900 (homepage sidebar), prospx/index.html:5796, 7075,
7082, 7351 (.compare-panel) (precedent: prospx:8249). Add
env(safe-area-inset-bottom) to the nav drawer panel and any bottom-pinned
sticky (precedent: prospx:8270).

B1.6 Overlay scroll-lock. .qk-overlay (site.css:2280), .egfx-overlay (2339),
.eph-modal-overlay (eephus-account.css:102), .compare-panel (prospx:7348)
leave the body scrollable behind them. Add a shared body-lock helper (set
overflow:hidden + preserve scroll position) used by all four open/close paths.
Do NOT add a global overflow-x:hidden on html/body; fix the overflow sources
instead (B2) so real layout bugs stay visible.

## B2. Per-surface overflow + layout repairs

B2.1 /glossary/: the scroll wrapper class does not exist on the page.
glossary.js emits <div class="table-scroll-x"> at 7 sites (659, 673, 699, 879,
908, 1512, 1699) but .table-scroll-x is defined ONLY in prospx/index.html:3585.
Define it in site.css (move the rule), and wrap the 4 unwrapped tables
(.meth-cmp :474, .meth-tier-table :1370, .meth-table :1430/:1450). This is the
canonical definitions page panning sideways on every phone today.

B2.2 /trademachine/: #tb-group-panel renders 9-col and 4-col tables
(trademachine.js:1047, :1075) into a plain div (build_site.py:2844) OUTSIDE
#tradeboard-content, so the overflow rule (trademachine.css:190-194) never
reaches them: wrap them. The hindsight board grid .tm-board--hind is ~497px
minimum with NO media override (prospx/index.html:4593-4596, duplicated
trademachine.css:19-22): add a <=640 collapse (column-drop like the farm
pattern or a contained scroll; prefer column-drop for consistency), and
de-duplicate the two grid definitions if practical.

B2.3 /collegesavant/: no phone tier at all (styles.css stops at 720; no <=640
block). Add one: .cs-bar collapse (title row + swipe-strip tabs), 44px tap
targets, 16px search input, table wrappers, percentile-profile reflow. Two
apps (hitter + pitcher_index) share the stylesheet, verify both.

B2.4 prospx sticky stack: .section-tabs z-50, .detail-tabs z-30,
.detail-jumplinks z-5 all top:0, and --sticky-top hard-codes 56px
(prospx:4811) while an expanded <=640 tab strip is 4-5 rows of 44px, pinning
.farm-header (:4813) and .farm-roster-filters (:5833) behind it. Verify on a
real 390px viewport (Playwright device emulation acceptable); fix by measuring
the actual tabs height into the custom property (tiny script or
ResizeObserver) rather than hard-coding. PRESERVE the farm no-overflow rule
and the column-drop pattern.

B2.5 Filter accordion boot-state: FILTER_MOBILE_BP is read once at init
(prospx:54044/:54056) and never re-evaluated; rotate a phone and the default
is wrong. Re-evaluate on the matchMedia change event (pattern:
eephus-nav.js:104-113).

B2.6 Forums/account + remaining thin surfaces: eephus-account.css has one
<=640 block (448-454); give the composer/comment tree a phone pass (indent
depth cap, 44px controls, 16px inputs). /report/ form inputs same treatment.

## B3. Touch interaction layer

B3.1 title= tooltips are dead on touch: 884 in prospx + 153 in module JS,
including load-bearing methodology copy (prospx:32589 S-XLINE paragraph,
:39018 farm-grade window) and 65 cursor:help markers that promise help touch
never delivers. Strategy: (a) for [data-gl]-eligible terms, migrate the title
into the glossary system (eephus-gl already tap-toggles on hover:none,
eephus-gl.js:349-362); (b) for the long-form one-off explanations, move the
copy into a tappable info affordance (the existing popover/bottom-sheet
patterns in prospx); (c) leave decorative titles alone. Triage by grepping
title= with >80 chars of content; do the load-bearing ones, log the count.

B3.2 Starfield on phones (dark theme only): ungated 60fps rAF + full-canvas
clear, pointermove parallax registered on ALL devices (eephus-bg.js:240-242),
and resize -> debounced FULL star regeneration (232-235) which fires on every
mobile URL-bar show/hide (visible star pop + realloc churn). Fixes, all gated
by (pointer:coarse), never by reduced-motion (owner rule): skip the parallax
listener; on resize, preserve star positions and only resize the canvas
(regenerate only when width changes materially); consider halving the frame
rate on coarse pointers. Keep MAX_STARS/MAX_DPR as is.

B3.3 Sticky-hover artifacts: .mlb-card:hover::before, .feed-item:hover,
.farm-rows-cards .farm-row:hover transform latch on touch. Wrap hover-only
effects in @media (hover:hover).

## B4. Lane B verification

- Recreate the Playwright sweep in the scratchpad (the old
  c:/tmp/site_debug_sweep.py + route_probe.py are the precedent): every route x
  {390x844, 768x1024, 1280x800} x {light, dark}; assert zero console errors,
  zero document horizontal overflow, tap-target spot checks on the fixed
  surfaces; screenshot archive for the owner.
- PYTHONIOENCODING=utf-8 for Playwright runs (cp1252 console).
- Re-run the suite guard trio after CSS edits + full suite before push.
- Verify farm grid still has NO overflow-x at any width (owner rule).

---

# Execution order, commits, and deliverables

Order: Phase 0 -> Lane A1-A3 (calibration truth + hygiene) -> Lane C (displays)
-> Lane B (mobile) -> Lane A4 (structural safety; A4.1/A4.2 can land any time
they are ready) -> A5 stretch. Rationale: A1 findings could force a regen
decision that the owner should see early; C lands before B so the mobile pass
verifies the new displays; A4/A5 are independent.

Commit discipline: small thematic commits, suite green (minus the documented
reds) per commit; stage by explicit path; en-dash/copy lint any user-facing
copy; regenerate pages in the same commit as CSS changes; loss ledgers for
refuted model candidates per the artifact conventions (failed challengers are
blocks in the parent artifact). Do not push to beta. Do not run
value_framework --fit (it reverts the hand-amended sub-45 anchors).

If Lane A ships anything that changes served numbers: follow the two-pass
regen locally to verify (proj/trade/fa exports run in 22-47s off cache;
regen_all ~108s), expect the golden fingerprint to fire, restamp only when the
output is the accepted one, and append the box's owed-regen list in a new
dated runbook (the box already owes the RUNBOOK_2026-08-03 regen; consolidate,
do not fork instructions).

Deliverables:
1. Code + tests per the lanes above.
2. Refreshed eval artifacts + registry rows (A3), each committed with its
   verdict.
3. A dated execution report doc (docs/) recording ships, refutations with
   numbers, and the updated known-reds ledger.
4. Playwright screenshot archive (scratchpad, referenced from the report).
5. Memory update at session end (execution record + any new gotchas).

Escalate to the owner (do not proceed silently) if: A1.2 refutes the Platt
constants; any basis-crossing found in A2.1 changes served dollars by more
than noise; a display change requires abandoning the fixed-height card model
entirely; or anything requires touching beta.
