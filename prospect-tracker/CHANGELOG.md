# Changelog

Running changelog for holistic pass 3 (started 2026-07-01, Beta launch
2026-07-11). One entry per landed package, newest first inside each day.
Curated by hand; the generated audit deliverables (MODEL_REGISTRY.md,
SITE_MAP.md, DATA_SOURCES.md) are NOT logged here on regeneration, only when
their generator changes behavior.

Companion ledgers: docs/audit-2026-07/AUDIT_FINDINGS.md (findings +
pre-registered experiment gates), docs/audit-2026-07-18/FINDINGS.md (fresh
audit), REVIEW_QUEUE.md (deferred work), BETA_READINESS.md (go/no-go).

## 2026-08-06b (tool provenance on the board)

GOLDEN FINGERPRINT RESTAMPED 344db288 -> 5430ea7b. No served GRADE moved; the
meta block gained a field.

A served tool_xfv is a bare {tool: grade}, so a reader could not tell a grade
that BLENDS MiLB production from one that passes the consensus grade straight
through. That distinction became material the same day: the tool gate gained a
real paired-bootstrap MDE, `hit` failed it, and 8 of the 9 tools on the board
are now grade-only. Nothing on any surface said so.

data/xfv.json meta now carries tool_provenance, read from the gate's own
verdicts rather than restating them so it cannot drift from what actually
decided the grade. Per TOOL rather than per player: it is identical on every
row, and duplicating it 3,007 times would be wire weight for no information. An
absent tool artifact yields an empty block and the surface shows no chip, which
is the honest failure: we do not know the basis, so we do not claim one.

## 2026-08-06 (OWNER-DECIDED protocol promotion + a real MDE on the tool gate)

GOLDEN FINGERPRINT RESTAMPED. `_GOLDEN_XFV_SHA256` in test_efv_export.py moves
ad57da0f -> 344db288. Two deliberate changes moved served values; neither is a
bug fix and both were taken by the owner with the costs in front of them.

1. SCORED_YEARS PROMOTED, 4 folds to 11 (Lane C3). (2020..2023) becomes
   (2014..2024). Pooled n rises 353 -> 755 hit and 438 -> 890 pit.
   THE COST, and it is the headline: model-minus-consensus pooled rho falls from
   +0.0361 hit / +0.0533 pit to +0.0113 / +0.0108, against a model-vs-consensus
   MDE95 of about 0.045. Pitchers CLEARED that floor at 4 folds; at 11 folds both
   sides are NULLS. "eFV beats consensus" is no longer RESOLVABLE at this power.
   It is not shown false, it is unmeasurable, and the published surface now says
   so instead of asserting it.
   The pitcher two-metric win also flips: blend MAE was 2.372 against a baseline
   2.381, and is now 2.762 against 2.711.
   CAVEAT THAT TRAVELS WITH EVERY NUMBER THIS PRODUCES: each 2024 debuted row is
   observed_seasons=2, censored, weight=0.333, with target_censored exactly 3x
   the observed two-season bWAR, while prospect_path._score pools UNWEIGHTED. So
   210 rows enter the published figure at full weight with two thirds of each
   label extrapolated.
   SCORED_YEARS_LEGACY_4FOLD is kept so a ledger number recorded on the old basis
   can still be reproduced. About thirty lab tools import this constant; any
   ledger entry dated before today is on the 4-fold basis and must be read that
   way.

2. THE TOOL GATE GOT A REAL MDE. efv_tools._oos_validate decided whether a
   tool's MiLB blend reaches the served grade with a bare `bool(br > gr)`: no
   minimum detectable effect, no bootstrap, no interval, on a quantity that
   controls 3,007 of 9,382 served rows. Measured before the change, three of the
   five gates sat inside 0.008 of the line and `speed` was an exact tie at
   +0.00000 decided purely by the choice of `>` over `>=`.
   It now requires a PAIRED bootstrap on the difference (B=2000, seeded) with the
   one-sided 95% lower bound above zero. Paired because the arms are scored on
   identical rows.
   VERDICTS MOVED: `hit` fails (margin +0.0002 under the new folds, lo95 -0.0101)
   where it previously passed at +0.0079, so that tool reverts to grade-only.
   `fb` survives comfortably (margin +0.0731, lo95 +0.0439). game_pwr, speed and
   cmd were already failing and still fail.

BLAST RADIUS, measured against the previous commit rather than estimated:
178 players' tool_xfv blocks changed, median move 1.0 grade point and max 2.5.
ZERO headline xfv values changed. The re-grade is real but contained to the tool
column.

## 2026-07-18 (fresh audit fixes + Generate-GFX overhaul & site-wide rollout + eFV improvement sweep)

Owner-directed pass: a fresh 8-lane adversarial audit of the least-recently-audited
surfaces (the 07-16/17 payload+export surge, draft-night, statcast process-pool,
FA wave-2, prospx frontend, module JS), a Generate-GFX overhaul + rollout to every
module, and a pre-registered eFV improvement sweep. Full ledger:
docs/audit-2026-07-18/FINDINGS.md; GFX design: docs/generate-gfx.md; eFV gates +
results: docs/efv-2026-07-18/GATES.md. (CHANGELOG note: the 07-16/17 owner commits
- payload slimming, DB repairs, injury/reliever directives, FA wave-2, draft
ingestion - landed without their own stanzas; see `git log 6c11abb..` for that span.)

### Audit fixes (safe correctness / dead-code / display; no published-number model change)
- A1 (payload/perf): the debuts_full per-player shard path was dead - prospx read
  DATA._slices.debuts_full but storage advertises it under _slices_dir, so every
  graduate card fell back to the full debuts monolith (defeating the 07-16 sharding).
  Routed the JS through _slices_dir.debuts_full, and added /data/debuts_full/*** to
  the nightly rsync + CI staging (shipped by neither before).
- A2 (prospx display): farm-detail showed two different eFV grades for one player -
  the graded-by-level list + _rosterGrade sort + farm-compare top-prospect used the
  raw xfv_grade; the affiliate table used the quantile headline. All routed through
  efvGradeDisplay/efvRankValue (the raw->quantile map is non-monotone).
- A3 (prospx feature): Chase% was dead on ~8 surfaces (statcast strip, outlier/ribbon
  chips, actives sort, SC+ JS fallback, watch card, compare cart) - the JS read
  z.chase_pct but zone rows serialize o_swing_pct. Backfill chase_pct from o_swing_pct
  on every zone row at boot (_normalizeZoneChase).
- A4 (GFX engine): eephus-gfx.js indexed row cells by filtered column position after
  dropping wideOnly columns, shifting later cells when a wideOnly column is
  non-trailing (FA specs) - Deal WAR printed under the Surplus header on narrow
  formats. Preserve original column indices.
- A5 (FA nav): future-class views dropped the class= hash param on player/rail links.
- A6 (hub nav): the hub strip's "MLB Projections" chip fired for never-debuted
  prospects (dead-end); player_links now tags projection-universe players proj:true.
- A7 (prospx display): WAG list pills recomputed client-side and disagreed with the
  server-baked eFV-basis regressed_wag; prefer the baked value when present.
- A8 (statcast ops): pass-3 swallowed worker/pool failures silently - a BrokenProcess
  Pool could stale hundreds of rows in a "success" run. Added a loud log.warning.
- A9/A10/A12 (dead code): removed the shadowed _statcast_drivers in spotlights.py, the
  dead renderTradeBoard() in trademachine.js, and the dead _GFX_SECTIONS map; fixed the
  shared GFX modal dropping control changes made mid-render.
- A11 (CollegeSavant): descending leaderboard sort floated missing values to the top;
  nulls now sink last in both directions.
- Deferred to owner (moves published numbers or needs the canonical DB - see FINDINGS
  B1-B6): the debuted-player super_two dead-parameter, the 2026 draft team-pool
  inflation claim, draft overperformers/simulate-slot edge cases, deeper statcast
  spawn-hardening.

### Generate-GFX overhaul (prospx) + site-wide rollout
- prospx information pass: farm rows gained a top-prospect/count/avg-age meta line +
  net surplus $M (were rank+letter only); injured rows show IL type + days (were
  surplus $); overseas rows gained an OPS/ERA value (was blank); spotlights gained the
  stat line + top driver; leaderboards gained the rolling-window label + PA/IP sample.
- prospx layout pass: rows vertically centered (kills the short-list dead gap); footer
  "+N more at eephus.io/prospx"; the header QR encodes the live section+filters deep
  link; the farm snapshot now fires after its filters; card-pack minis show the value.
- Shared engine: added the Tall 2:3 format, an optional footer legend, and the A4 fix.
- Rollout - new Generate-GFX on Trade Machine (board + shareable deal card), MLB Stats
  (REM+/Bullpen+/SEM+/HEM+/WPA leader boards), PAL (RP->SP & SP->RP boards),
  Projections Accountability, FA Fits + Archive, and CollegeSavant (leaderboard board +
  the share card upgraded to the format/theme/accent modal). eephus-gfx.js added to the
  mlbstats/pal/collegesavant shells.

### eFV improvement sweep (all five arms committed LOSSES - docs/efv-2026-07-18/GATES.md)
- Pre-registered five arms against the shipped blend on the same forward-chained
  protocol: E-FWDCAL (per-fold output calibration), E-RECENCY (recency-decay training
  weights), E-IPCW (inverse-P(censoring) weights), E-STACK (OOF simplex stacker),
  E-HURDLE (full-pool P(contributor)xE[WAR|debut] head). All FAIL both sides; the MAE
  half of the dual gate does not close even with leakage-clean forward calibration - a
  fourth independent confirmation the current matrix vintage is at its trainable-data
  ceiling for pooled rank. One live-but-ungated signal noted for a future owner-signed
  pre-registration: the hit hurdle head's +0.019 full-pool contributor-AUC. Artifact
  data/xfv_improve_sweep_eval.json + registry row xfv_improve_sweep; no served numbers
  changed (screen only).

## 2026-07-15 (eFV 2024-fold unlock: governance re-runs + level_rank ship + label integrity)

The owner-queued 2024-fold unlock (docs/efv-2026-07-15/GATES.md; gates
pre-registered before any keep-alive ran). `_GOLDEN_XFV_SHA256` bumped for the
matrix + feature ships below.

- 2024-fold unlock: efv_dataset.DEBUT_YEARS widened to 2011-2024; 210 dated-2024
  debuts enter as censored weight-0.333 rows (hit +91, pit +119). SCORED_YEARS
  unchanged - the rows enrich existing fold training pools. New selftest
  baselines: hit blend 0.3765 / pit 0.3028.
- Governance discharged (F-SIDE S5 + the bucket-head rerun marker): E-ISO4-path,
  M3, E-STUFF and BUCKET-AGE-HEAD all re-ran at the new vintage with their
  registered gates and all FAIL on their original binding cells - every
  calibration-line close stands; registry rows restamped. The BUCKET-AGE-HEAD
  lab now lives in-repo at tools/bucket_age_head/ (was temp-dir only).
- level_rank SHIPPED into the hitter lean set under the pre-registered LR-FRINGE
  gate (t45 +0.0192 vs bar +0.015; pooled/within-tier at the 0.0011 identity
  noise floor; resolved-target sensitivity agrees). Ledger
  data/xfv_level_rank_fringe_eval.json + registry row xfv_level_rank_fringe;
  test_efv_model pins updated.
- Keep-alives honestly closed at the new vintage: pit elasticnet (+0.0033) and
  pit residual-target (+0.0030) still under the +0.0046 bar; E-LEAN1 five all
  fail at re-measured noise floors; M3 re-run also consumes the pit:ifa-shrink
  and c6 keep-alives (pit:ifa +0.0068 under the +0.01 bar). Next new
  information for all of them = resolved 2024+ cohorts.
- Label integrity: career-terminal transactions (lifetime DEI ban / retirement,
  raw player_transactions, no-later-activation rule) now resolve censored
  debuted rows at the observed sum with weight 1.0 (Marcano no longer
  extrapolates a season he is banned from playing; alu/kirilloff/pint/ridings
  likewise) and unflag recent-bust retirees (weight 0.5 -> 1.0).
- Debut re-fire guard (storage.auto_debut_player): a player with any debuted
  snapshot no longer re-fires on veteran re-appearances (the ryan_vilade
  class), and a detected date later than roster_status.mlb_debut_date is
  clamped to the known true debut. New pins in test_auto_graduation.py. The
  41 historical run-date-stamped rows are left for an owner-approved repair.
- PROSPX Generate GFX prospect card: the hero badge label now tracks the badge
  value (eFV / Provisional eFV / Consensus FV on true fallback) instead of
  hardcoding "Consensus FV" over an eFV number.

## 2026-07-07 (pre-launch pass: models + deploy + freshness + cards + polish)

The final pre-Beta debugging/polish/refinement pass (plan:
docs/prelaunch-2026-07/, gates pre-registered in GATES.md before any lab ran).
`_GOLDEN_XFV_SHA256` bumped for the eFV ship below.

- eFV accuracy round (4 gated experiments, docs/prelaunch-2026-07/WSM_RESULTS.md):
  ops_rel SHIPPED into the hitter lean set under the pre-registered fringe-tier
  gate (FV-45 tier Spearman +0.0237, about 10x the noise floor; pooled and
  within-tier costs sit at the identity noise floor). Lambda-confirm,
  hierarchical cohort-lambda, and alpha-criterion all NO SHIP with loss-ledger
  artifacts + registry rows (the lambda sweep flags an owner decision: the
  hitter composite is monotone to the 0.80 sweep ceiling, so a cap-raise
  experiment above the registered [0.50,0.70] band is the follow-up).
  evaluate() now also writes per-cohort/era/tier contributor-AUC (WAR >= 3) and
  star-AUC (>= 10) for blend vs consensus, and records the LIVE blend lambda
  with rank-gate provenance (fixes a stale shipped_lambda desync).
- Deploy reconciliation (P0): nightly-build.sh restores the tracked tree before
  git pull and runs its pytest gate under EEPHUS_DEPLOY_RUN=1, which relaxes the
  xfv golden fingerprint to shape checks (exists, parses, row count within 20%,
  generated_at < 48h) for runs that legitimately regenerate the artifact. Dev/CI
  keep the exact hash. Without this the first nightly with real data movement
  froze publishing permanently. Runbook: docs/prelaunch-2026-07/DEPLOY_RUNBOOK.md.
- Stale-asset fix (P0): nginx /assets/ goes no-cache (etag revalidation);
  45 unversioned CSS/JS refs across prospx + collegesavant now carry ?v= stamps;
  new test_asset_versioning.py guards them.
- Beta badge: accounts created on/after BETA_START (eephus-ui.js, one-line
  constant) get a computed beta_tester chip via withComputedBadges(), rendered on
  the profile modal and forum comment heads from the single flair path. No DB
  writes; inert-without-config preserved.
- Runtime cuts (measured baseline 52m49s, docs/prelaunch-2026-07/WSR_NOTES.md):
  the monthly-chained daily skips d5c/d5d (235s, the monthly just fetched them);
  the four eval-lab subprocesses gate on 30-day artifact age (503s when fresh,
  EEPHUS_LABS=1 forces); positional versatility gates on a 7-day artifact
  freshness check (437s). New daily step d5e rebuilds leaderboard_gamelogs.json
  (top 200, 210s soft budget) - it was stale since Jun 16 with no producer wired.
- Freshness: L15 OPS chip on hitter detail pages (top-200, client-side from the
  daily recent_games sidecars); the date-window leaderboard shows a "window data
  through <date>" notice when its payload is over 3 days old.
- MLB player cards: hitter HEM+ (plus 3yr/x variants), reliever/starter
  REM+/RIV+/SEM+ baked onto mlb_player_detail.json (client fetch kept only as
  fallback); ex-PROSPX cards gain a scouting slice (latest report, capped) and a
  consensus-FV trajectory sparkline; Discussion tab mounts the shared forum; PAL
  rows now link player names to the projections card (was a dead end).
- Consensus weighting: verified live end-to-end (weighted mean receipts;
  non-FG/Pipeline sources vote 1.0); glossary methodology extended (vintage
  cutoff, live weights, draft-board equal-weight clause). Draft-side hygiene:
  draft_source_backtest now RESETS draft_source_weights.json to equal-weight on
  a ship=False verdict (a stale 2026-06-25 ship=True file was still applying
  near-unity weights against the current failing A/B).
- Site polish: neon/up/down tokens promoted from .gl-app scope to :root (fixes
  the dead mlbstats hover + trademachine hardcoded-hex fallbacks); module chips
  flipped alpha -> beta for launch; visual sweep of 192 route/viewport/theme
  cells found 0 page errors and 5 defects, all fixed (draft_live.json idle stub
  ends year-round console 404s, host-relative headshot normalize, home module
  min-width bleed at 375, farm grid tightened to fit 1280 without breaking the
  sticky header, leaderboard filter chips wrap).
- Registry hygiene: xfv_backgrade registered; external/unvalidated rows
  (stuff_plus_external, swing_plus_external, spotlights_movement) get precise
  dated notes; 4 new experiment rows; registry at 79 models, validate clean.
  Supabase abuse-surface audit: RLS confirmed on across tables, rate limits live
  in 0003; two trivial client fixes (comment maxlength, protocol-relative link
  reject); thread-moderation SQL drafted NOT-APPLIED as owner action
  (docs/prelaunch-2026-07/ABUSE_SURFACE.md).

## 2026-07-06 (S-1 Leverage follow-ups: yearly history + charts)

The two deferred follow-ups on the S-1 Leverage Leaderboards (the board shipped
table-only, current-season-only in 6444bbd). Additive, self-contained, offline:
no model, registry, or golden-artifact change.

- Yearly leverage history: `leverage_export.export_history` writes a new
  `data/leverage_history.json` (per-season qualified batter + starter boards,
  2021-2025) and the /mlbstats/ Leverage board grows season pills (Current +
  five prior seasons), mirroring the reliever/starter/hitter history state
  machines. The prior seasons are already in the winProbability cache (the
  reliever + gmLI-3yr walks warm 2019+), so the multi-season fold is a disk walk
  (one schedule + two statline calls per season is the only network); a season
  that fails to load is logged and skipped, never aborting the run. Wired into
  run_monthly 6b4h after the live export.
- Leverage charts: a Charts collapsible on the board. Batters get the WPA
  distribution plus a production-vs-leverage scatter (WPA/LI context-neutral
  production on x, pLI leverage faced on y, dots tinted by Clutch: green
  clutch-positive, red clutch-negative). Starters get the WPA-per-start
  distribution plus a context-vs-realized WPA scatter. Renders for any season
  the pills select. Reuses the shared EEPHUS_HUB histogram/scatter helpers, so
  no new chart code.
- Tests: export_history qualified-only + fail-skip unit tests (test_mlb_leverage,
  no network); season-pill + charts render smoke tests (test_mlbstats_smoke).

## 2026-07-05 (owner-request batch: eFV bug-fixes + site polish)

- eFV FLAGSHIP CORRECTION (two bugs; `_GOLDEN_XFV_SHA256` bumped, rank gate held).
  (1) The WAR->grade map inverted a 6-season model prediction against the clemens
  `control_years=7` curve (a valuation flip had silently re-pointed the eFV grade
  denominator), deflating top-end grades. efv_score now passes
  `exposure_seasons=TARGET_SEASONS` (6) at every `realized_implied_fv` call
  (rank-preserving; jesus_made 61.8->64.9, franklin_arias 61.6->64.5,
  leo_de_vries 61.4->64.4, back in line with consensus + the codebase's own 6yr
  anchor). New guard `test_efv_grade_map_inverts_on_model_window`.
  (2) efv_dataset._season_rates treated a MISSING level norm as league-average-0,
  so a raw DSL K% masqueraded as a level-relative edge and spiked young low-level
  arms; now falls back prior-season -> static prior (fredy_penuelas 6yr WAR
  5.57->3.0, grade 52->47.8). Provisional pitcher ceiling de-rated (efv_ungraded
  _GRADE_MAP KNEE 38->34 / CEIL 42->38) so un-scouted DSL arms top out at org
  depth (~38), not a fringe-regular 42. eval rank gate flat (hit 0.362->0.353,
  pit 0.279->0.284); <=2018 hitter blend up 0.509->0.515.
- eFV display consistency: /projections/ baked a stale eFV vintage vs the daily
  PROSPX board (62 vs 63). run_daily now re-bakes proj_export after the eFV regen
  (step d9b) and proj_export prefers `xfv_grade_realized` (PROSPX's precedence).
- MLB Projections sort: prospects were sorted on a 7yr prime total while the Total
  column showed the 5yr window; projections.js now sorts (+ the Top-projected rail)
  on the same displayed windowed 5yr WAR (`warShown`), so late-ETA arms sink to
  where their visible total puts them.
- HEM+/Offense+ spread widened to the wRC+ convention (hem_plus.HEM_SPREAD_GAIN,
  a monotone/rank-preserving display gain; qualified HEM+ SD 7->16, team Offense+
  SD 2->4.5). Both validation gates re-confirmed (X-H1 vs raw wOBA lo95 -0.0092,
  X-H2 3yr gap lo95 +0.0053). Dedicated hemClass color bands so REM+/SEM+ colors
  are untouched.
- Lineup Charts: sabermetric batting-order construction (best two bats hit 2nd/4th,
  handedness stagger, vs-LHP/vs-RHP toggle, bench bats shown separately) via pure
  hem_plus.build_batting_order + hitter_export.load_bat_side (batSide bulk call).
- xREM+ / xSEM+: Savant "deserved run prevention" companion columns + Luck residual
  for relievers/starters, mirroring xHEM+ (inverted ratio, role-anchored pool).
  Framed per the loss ledger (xwOBA-allowed did NOT beat FIP, so REM+/SEM+ stay
  FIP-based); shipped provisional (registry rows, glossary, freshness map).
- Trade Machine promoted to its own top-level module (/trademachine/) under the
  MLB Modules nav group; legacy #view=trademachine redirects; trademachine.css
  re-scoped from #proj-view-trademachine to .tm-app so the standalone page themes
  correctly.
- Scouting reports: backfilled the FanGraphs "sa..." player ids that pre-2026-06-25
  boards never stored, so "View on FanGraphs" links resolve (+2,552 players); one-
  shot fangraphs_csv.backfill_fg_player_ids.
- MLB Stats leaderboard clickability: thin player cards for leaderboard players
  outside the projections/FA universe + collision-safe keys (fixes Max Muncy /
  Sabrowski / Fuentes; takes effect on next player-detail rebuild).
- PAL Conversion History: recency-first + click-column sorting; in-progress
  (current-season) conversion detector so mid-year converts like Griffin Jax show
  up (needs a pal.json regen to populate).
- Site polish: light-mode background pinstripe "scanlines" removed (dots kept);
  Discord CTA on the homepage; Developers page badges removed + click-to-flip
  cards; CollegeSavant homepage card attribution/alpha tag removed; "Top movers"
  rail relabeled to its real window; FV tape shrunk to a one-line chip strip;
  redundant second surplus outcome-range fan suppressed; outcome-mix top band
  relabeled "Elite" + canonical "Star Odds" line added to the eFV detail card.

## 2026-07-05 (Clemens 2026 followups: default flip + safety flags + Tier 2 surfacing)

The owner-gated followups from the recalibration, executed.

- Production default FLIPPED to `clemens_2026` (MODEL mode). Split
  `_BASE_IDENTITY_SET` (prospx_current, the byte-identical base config, overlay
  no-op) from `_DEFAULT_VALUATION_SET` (clemens_2026) so the clemens overlay
  actually applies on the default path -- the naive two-constant flip was a
  mislabeled no-op. The board reprices per player under the FanGraphs market
  conventions (prior-season arb, 4-step arb, 7yr control, net-7%, published
  cost-of-win): 50 FV hitter model surplus ~$18.5M (+3% whole-stock), NOT the flat
  ~2x table. This shifts the SHARED $/WAR conventions site-wide (FA / projections /
  trade / WAG also reprice). value_framework.{json,js} re-emitted.
- Model<->table reconciliation is now a REPORTED diagnostic, not forced:
  `surplus_tier_calibration` + `fit_tier_reconciliation` (a per-role WAR-anchor
  multiplier via the identity-default `war_anchor_scale` lever) report the best-fit
  alignment + irreducible residual in star_odds_eval.json + validation.md. No scale
  is written to the shipped set, so the live board is never rescaled to the table.
- Validation report: residence-reconciled org rollup (top org ~$858M raw ->
  reconciled toward the published ~$671M) + a FanGraphs-Board-aligned universe
  comparison (793 of 1005 ranked).
- Safety flags enabled: mlb_trade_lookup per-season kernel is now the default
  (opt-out via TRADE_LOOKUP_PER_SEASON_KERNEL=0); the PROSPX Star Odds column is on.
- Tier 2 surfaced: OPT% (upgrade-option) is an opt-in PROSPX column (`#optpct`,
  surplus.opt_pct via published_opt_pct); the cross-source normalized consensus is
  now the LIVE consensus scale (consensus.build_timeseries normalize=
  ADOPT_NORMALIZED_CONSENSUS; per-source published grades untouched). Glossary +
  registry + freshness-map updated. Full suite green (1871 passed).

## 2026-07-04 (Clemens 2026 recalibration, Tier 2: upgrade-option + grade normalization)

Two analytical layers on top of the Tier 1 valuation sets. Both ship as reports +
eval artifacts with UI deferred; neither changes any live surface.

- Upgrade-option layer (upgrade_option.py): a prospect's grade modeled as a
  role-split absorbing Markov chain (grades 35-70 plus graduated and out, annual
  step), estimated from our dated grade history (prospects.db snapshots, fangraphs +
  mlb_pipeline pooled), Laplace-smoothed; graduated = debuts.json, out =
  inactive.json, still-active last year censored. Payoff = the clemens_2026 table
  value of the grade a player graduates from. total (full chain) vs intrinsic
  (frozen-grade) gives option value and OPT% = option/total. A 45 FV hitter is
  option-dominated (OPT% about 60%); high grades run low or negative OPT% (thin data
  plus net-downgrade risk at the top). Config-prior cross-check (labelled 20% upgrade
  anchor). reports/upgrade_option.md, data/upgrade_option_eval.json; registry
  provisional.
- Cross-source grade normalization (grade_normalization.py): quantile-map each
  source's grade distribution onto FanGraphs FV on the OVERLAP (players graded by
  both), per role per cycle, so coverage is controlled for and only a true scale
  bias remains. Raw and normalized grades side by side; a normalized consensus is
  the mean of the FanGraphs-scale grades. Reference maps to itself (identity),
  recomputation deterministic; the 2026 cycle flags mlb_pipeline and espn as grading
  materially higher than FanGraphs on shared players. Analytical layer only, the live
  consensus is unchanged. reports/grade_normalization.md,
  data/grade_normalization_eval.json; registry provisional.

## 2026-07-04 (Clemens 2026 prospect valuation recalibration, Tier 1)

Recalibrated the surplus engine to the new FanGraphs / Ben Clemens (2026)
prospect-valuation framework behind versioned valuation sets. The production
default is UNCHANGED (`prospx_current`, alias `edwards_2019`); the new framework
ships as a selectable set (`clemens_2026`) for the diff, the published Star Odds,
and draft pick surplus. No published board number moves until the diff report is
reviewed. Two-part write-up in docs/METHODOLOGY.md; reports in reports/.

- Versioned valuation sets: config/valuation_sets/{prospx_current,clemens_2026}.yaml
  + valuation_sets.py loader (checksum-validated on load: 50 FV hitter $45.0M /
  13.5%, 50 pitcher $33.5M / 7.0%, 45 $14.5M, 45+ $18.5M, 40 $5.5M, 70 in
  $150-200M). Table mode (price at tier values) vs model mode (the mixture engine).
  prospx_current table mode reproduces the live board at the tier grid. Outputs
  are tagged with the active valuation_set (snapshot header + per-prospect payload).
- Convex kernel: added a bucket_step mode (faithful hard per-bucket rates) beside
  the production smoothed ramp; Jensen test proves transform-first beats
  price-the-mean. Fixed the mlb_trade_lookup vet price-the-mean (per-season kernel)
  behind TRADE_LOOKUP_PER_SEASON_KERNEL (default off, live board unchanged);
  annotated the deliberate bayes defensive floor and the non-production comparators.
- Salary + discount: clemens_2026 uses a 4-step 15/35/50/75 arbitration schedule
  on the prior season's value (floored at league min) over a 7-season control
  window, and a net 7% discount; a test proves a single net discount factor (no
  double inflation).
- Star Odds (new metric): P(2+ control seasons of 4+ WAR), computed analytically
  (per-bucket Gamma season WAR + Poisson-binomial, role-mixed for pitchers),
  monotone-in-FV via isotonic shrinkage. The board shows the FanGraphs published
  tier value (table mode); the engine's per-player odds are a diagnostic, reported
  against the published tiers in data/star_odds_eval.json (registry: provisional,
  model runs below the published tiers under the v47 anchors). xFV label view in
  data/star_label_view.json (real MLB WAR; ~108 career stars). Column on the PROSPX
  board behind #starodds=1 (dark by default). Glossary + registry + freshness map.
- Validation: reports/validation.md, sensitivity.md, diff.md over the 4,044-player
  graded stock. Residence-time reconciliation lands the sub-50 pool at $6.29B
  (published $6.30B) and the whole-minors total at $11.13B, inside the published
  $10.5B-$13.75B band. Sensitivity signs match the published discount/win-cost/arb
  directions (flat-kernel and residence differ in size, explained by our
  sub-50-heavy universe).
- Draft War Room: implied pick surplus = clemens_2026 tier value for the drafted
  player's FV and role minus the cost (actual signing bonus if known, else the
  expected slot), from REAL ingested bonus/slot data. Surfaced in draft_export +
  the live poller. War Room column added; the War Room chip is now always
  discoverable in the draft section (lands on the "opens on draft night" state
  pre-draft); a homepage banner links to it while the live feed reports status live.

Tier 2 (upgrade-option Markov layer, cross-source grade normalization) is gated
behind a checkpoint and NOT started.

## 2026-07-04 (research sweep + model frontier)

Discovery ran as a 20-agent read-only audit (registry / glossary census /
correctness / frontier feasibility) with adversarial verification of every
blocker/fix-now claim. That pass refuted or downgraded 4 of 6 checked fix-now
claims: the zone/plate-discipline models are regime-safe by construction
(percentiles rank within-level; chase comes from a geometric MLB-trained zone
applied uniformly, not the ABS zone) and value_framework verified exemplary on
transform-first-aggregate-last. Deliverables: docs/audit/current_state_map.md,
docs/audit/research_check.md, docs/plans/sweep_and_frontier_plan.md,
docs/roadmap/post_launch_frontier.md.

Research-check fixes:
- OPS+ published formula corrected to the level-relative OPS ratio the code
  actually computes (was the Bill James OBP/SLG decomposition, which the shipped
  level norms cannot even reproduce). Copy-only.
- ABS-challenge-era caveats added to Chase% and CSW% (the site was silent on the
  2026 league-wide ABS regime; AAA since 2023, FSL since 2022). RPS+ headline now
  states its two scales plainly (draft z-score vs active ratio). pStuff+
  leaderboard tooltip corrected to the shipped per-batter formula. The two
  player-card "Stuff+" labels disambiguated (pStuff+ / Stuff+ (Statcast)).
- NUMBER CHANGE (owner-approved with output diff, docs/audit/rc6_shrink_impact):
  per-season ops_plus_level / era_minus_level now apply the same K_AB=170 /
  K_IP=50 empirical-Bayes shrink the headline statline uses, killing the "OPS+
  374 on 4 AB" cameo blowups. Qualified rows barely move (OPS+ median 5, ERA-
  median 10); every small-sample extreme is tamed.
- em-dashes in storage.py generated card-flag / statline notes (which bake into
  debuts.json / inactive.json outside the copy-gate scope) replaced with ' - ';
  a narrow regression test guards the note strings. statcast_plus docstring
  corrected (10 pts/sigma, z-scale not the ratio family).

Glossary reclamation (the "reclaim the glossary" mandate):
- Three shelves via a new `shelf` field: 143 Arkmetric / 23 industry / 82
  foundation (universal standard stats moved off the industry shelf).
- An `origin` credit line on every Arkmetric and industry entry: Arkmetrics say
  "original to eephus.io"; 23 industry metrics name their creator and source
  (Tango/FanGraphs for wRC+/wOBA/FIP/WPA/leverage index; Studeman xFIP; MLB
  Statcast for the bat/batted-ball/tracking suite; Alex Fast/Pitcher List CSW%).
- Three displayed-but-undefined metrics added (xwOBA, BABIP, VAA). Shelf badge +
  Origin line now render on every card (eephus-gl.js passes the fields through).
- DEFERRED to the roadmap: 41 weak-stub rewrites, 7 near-duplicate merges, 13
  multi-resolving alias disambiguations (touching aliases/permalinks 8 days from
  launch was needless risk).

Tier 1 frontier (all five owner-approved, each behind a flag, each with a
registry row + glossary entry at birth):
- Model Report Cards v0: inline champion-vs-baseline proof bars on 8 flagship
  Models & Proofs rows, behind #cards=1. Every card number traces to its eval
  artifact (a test is the anti-drift fence; the field survives refresh_stamps).
- System Duration / Window Alignment: surplus-weighted farm ETA vs the
  controlled-core WAR center on the Team Outlook board, behind #window=1. An
  economic lens no public farm ranking uses (5/30 orgs aligned, median +0.39).
- Risk-adjusted Surplus (Sortino): downside-deviation + bust column on the Trade
  Machine, behind #risk=1, from the persisted eFV fan. Local half-lambda; the
  global risk_aversion_lambda is untouched (no re-ranking).
- FV Tape: candlesticks + momentum / RSI / volatility on the consensus FV
  history, dark by default (localStorage, set via ?tape=1). Descriptive market
  signals, not predictions; RSI drops flat re-confirmations so a static grade
  never pins the gauge.
- Draft War Room: a cron (tools/draft_live_poller.py) writes a READ-ONLY
  data/draft_live.json on draft night and the PROSPX War Room view prices each
  live pick against our board and the historical pick-value curve (reach/steal
  in surplus dollars). The poller never touches prospects.db /
  draft_timeseries.json (a test asserts byte-invariance), so it cannot kill the
  mock or trigger promotion. Ships dark until the artifact appears.

Down-tiering: three "frontier" ideas (Crunch Index, Portfolio Frontier, IFA
Efficiency) are largely already built and become small display adds post-launch.
Blocked (spec, no start): Catcher/Challenge Value (no catcher-defense or ABS data
ingested), sequencing/judgment/matchups (only aggregates retained). Polish:
sticky Projections/FA headers shipped; money formatter, origin badges, qualifier
chips, nav naming deferred to the roadmap.

## 2026-07-02 (review-queue round)

- E-ISO4, the owner-approved final eFV bucket-calibration attempt, closes the
  line honestly. Tying both sides to one shared monotone grade map solved the
  cross-side ranking churn that failed the prior three attempts (cross-side
  Spearman delta is exactly 0 by construction), which isolated the real
  blocker: the pitcher bench bucket comes out materially worse no matter how
  the grade is remapped, because fixing the large and real FV45+ calibration
  gap pulls pitcher mid-grade mass toward bust. No grade-space monotone map
  can ship; the fix needs resolved 2024+ cohorts and a method below the
  grade-monotone constraint. Four attempts, four honest loss ledgers; eFV
  published numbers unchanged. Registry row xfv_grade_recal4.
- F-01 total-WAR bands DROPPED from the FA and Projections display (the
  owner-approved fallback after the R-BAND gate failed). The R-BAND
  experiment found the displayed total bands were miscalibrated beyond the
  summing bug: the incumbent summed band covers only 63% of realized
  multi-year totals (vs 80% design) because roughly a quarter of realized
  totals fall below its floor path, since players who wash out realize about
  zero WAR while the decayed p10 never reaches zero. The bands are
  mis-centered high, not merely too wide, so a narrower dependence-correct
  band covers even less (41%). Point estimates and the per-year bands stay;
  the real long-term fix (recalibrating the per-year quantile marginals to
  carry league-attrition zero mass) is REVIEW_QUEUE item 13. Loss ledger:
  data/total_band_eval.json.
- PROSPX grade cluster refactor (review-queue item 5) plus a grade-scale
  outcome band (item 4). One gradeBlock() helper now single-sources the
  eFV-round-to-nearest vs consensus-FV-ceiling decision; five duplicated
  sites route through it with byte-identical output (verified by a
  py_mini_racer golden harness), and six sites with genuinely different
  fallbacks are left in place and documented. The player-detail hero gains
  an "Outcome band" on the 20-80 grade scale, derived by inverting the
  published surplus pricing anchor at the outcome P10/P90 (a faithful
  re-expression, reproducing the grade to 0.4 MAE), hidden for provisional
  and degenerate rows, tooltip disambiguating it from scout disagreement.
- Gated experiments, all resolved honestly with loss ledgers and registry
  rows: MiLB park factors (item 2) are infeasible on cached data (the
  minors feed has no venue dimension and the Single-A statlines have no park
  key); the ERA-shrink unification (item 6) confirms the two pseudo-counts
  should stay (no shared value beats both objectives); the eFV bucket
  calibration re-attempt under a production-relevant gate (E-ISO3) fails on
  a per-side materiality check and year-dependent cross-side rank churn, the
  final attempt against this data vintage. eFV published numbers unchanged.
- Overseas re-check (item 8): the hitter wRC+ factor blocker has dissolved
  for NPB (FanGraphs already supplies league-and-park-adjusted wRC+ that
  overseas_stats.py parses; the only missing input is curating about ten
  FanGraphs player ids), upgraded to READY-TO-RUN and queued with a
  pre-registered gate; CPBL and Cuba stay blocked on cohort and source
  gaps. docs/audit-2026-07/overseas-factors-recheck.md.
- Country/IFA entity pages (item 9) deferred: the build lane failed on a
  structured-output error, not a data problem; re-run queued as item 14.

## 2026-07-02

- Wave 2 close-out: adversarial verification of the whole pass (4 read-only
  lanes, 16 findings, none P0) plus the owner-directed eFV improvement round
  (3 gated experiments, gates pre-registered before any run, all NO-SHIP).
  Fixes landed from the verification: the track-record panel's glossary deep
  link now uses the hash form the glossary actually parses; the gmLI
  consistency tool derives its seasons from the leaderboards payload instead
  of freezing at 2026 (gate numbers unchanged: pooled rho 0.4683, split-half
  0.5294) and writes atomically; the SC+ component diagnostic pins its
  keep/reweight decision to closed outcome seasons (the in-progress 2026
  season had made committed numbers drift) and its now-firing reweight signal
  is queued as REVIEW_QUEUE item 12 rather than shipped (n=23 per side); the
  monthly pipeline regenerates the generated audit docs right after registry
  restamps; the Upside strip lays out evenly at any season count; static
  pages rebuilt so their cache-busters match the shipped JS. eFV round
  verdicts, all honest loss ledgers with registry rows: the grade-space
  monotone recalibration fixed the isotonic candidate's rank-flattening and
  doubled the calibration gain but still fails the rank tolerance (which the
  identity transform itself fails, a gate-design fact recorded for any future
  attempt); per-cohort blend lambdas are noise-dominated at current cohort
  depth; the AA/AAA pitcher tracking overlay has zero trainable coverage
  until the 2024 debut cohort resolves. eFV stays at its trainable-data
  ceiling on ranking; its published numbers are unchanged.
- PROSPX display work (lane P): the player-detail Surplus card now shows the
  eFV surplus credible band in plain dollars ("Surplus band P10 to P90",
  explicitly surplus dollars, never a grade band; hidden when the band is
  degenerate); Generate GFX prospect badges follow the board's Rank-by toggle
  (eFV rounded to nearest when eFV leads, consensus FV ceiling otherwise) and
  graduate badges follow the Debuted lead-grade toggle, with footer legends
  tracking the mode; new collapsed "eFV vs consensus FV" track-record panel on
  the Debuted tab (pooled OOS Spearman per side, per-era and per-tier splits,
  resolved-disagreement receipts from committed eval artifacts); new inline-SVG
  reliability diagram of the shipped 5-bucket outcome distribution (the
  rejected isotonic candidate's "before" curves, which are the live model).
- Module apps (lane H1): every MLB module app (projections, mlbstats, pal, fa,
  both collegesavant apps) now renders a visible error state with a retry
  affordance when its data payload fails to load, replacing silent blanks;
  /mlbstats/ leads with 2-sentence REM+ and Bullpen+ explainers deep-linked to
  the glossary; projections player cards gained a per-year P90 "upside"
  element (per-year percentiles only, never a summed total; the flagged
  warTotalP90 surfaces are byte-unchanged); prospect grade language on the
  projections board and #cmp compare is eFV-primary (round to nearest) with
  consensus-FV-ceiling fallback. Five smoke-test files extended/added.
- Experiments X-D1 and X-D2 evaluated against their pre-registered gates.
  X-D1 (reliever leverage consistency) PASSED cleanly: pooled Y to Y+1 gmLI
  Spearman 0.4683 (CI floor 0.412 vs the 0.30 bar), split-half 0.5294;
  ships as a deployment-context column (wiring follows this pass). X-D2
  (age-relative outperformance, AgeRel+) met the numeric bar on its face
  (pooled r 0.1237, n=369) but is NOT a clear pass (post-hoc stability
  instruments, out-predicted by the plain level-relative comparator, upper-
  level selection confound): NOT wired, queued for owner decision. Both
  artifacts registered (registry now 44 rows).
- Audit deliverables (lane G): MODEL_REGISTRY.md, SITE_MAP.md and
  DATA_SOURCES.md are generated by tools/gen_audit_docs.py and drift-guarded
  by test_generated_docs_in_sync.py; CHANGELOG.md, REVIEW_QUEUE.md and
  BETA_READINESS.md are curated. REVIEW_QUEUE.md carries specs for every
  deferred item, including the F-01 summed-quantile WAR bands.

## 2026-07-01

- d60c4d3: wave-1 experiments. The surplus $/WAR stress test shipped
  (ordering level-invariant: zero top-50 churn at 20 percent shifts, FV45+
  rank rho at or above 0.9999); SC+ per-component isolation shipped (barrel
  rate carries the hitter signal, whiff rate the pitcher signal; composite
  stays per the pre-set rule); the eFV per-bucket isotonic candidate was
  REJECTED at its pre-registered gate (calibration improved but rank
  Spearman fell 0.0165 vs a 0.002 tolerance from PAVA tie-flattening) and
  lives on as a loss ledger with a deprecated registry row.
- f894429: glossary version stamp single-sourced (payload 2026-07-01); the
  copy-audit backlog cleared (22 of 24 open verdicts were already fixed in
  the live payload, 3 real fixes applied); PWR+ formally a legacy alias of
  POW+; copy gates (copy_lint + strip_emdashes) suite-enforced via
  test_copy_gates.py.
- 8570cf7: stabilization constants centralized in rate_stabilization.py
  (K_AB, K_IP, NEED_ERA_SHRINK_IP, BF_PER_9, SLOPE_SHRINK_K) plus the
  REPLACEMENT_WINS=47.7 team-roll-up baseline (was two literals); values
  byte-identical, output-neutrality proven by pipeline_artifact_diff;
  docs/aging-curves.md documents the intentional three-way aging fork.
- 9fe4852: fixed the pre-existing red test
  `test_fv50_active_prospect_gets_trade_rarity_floor`. The tune in 2a00e00
  plus the surplus realignment moved the fixture 0.2 above the rarity floor,
  so the final-value clamp tag legitimately stopped firing while the policy
  invariant (trade_value_mm at or above the active rarity floor) held
  throughout. The test now asserts the rarity-floor invariant instead of the
  clamp tag, and the floor is exposed in the in-memory result only
  (board_slim drops it from the written payload; data/trade_values.json is
  byte-unchanged). Suite fully green after the fix.

<!-- APPEND PACKAGE ENTRIES BELOW THIS LINE (newest first within each day;
     add a new "## YYYY-MM-DD" heading when the day changes) -->

## 2026-07-03 (follow-up Wave B2: starter metrics)

- New Starter Leaderboards section on /mlbstats/, the starter counterpart to the
  Bullpen Leaderboards. Three gated experiments (pre-registered; harness
  tools/sem_plus_lab.py, seed 20260703):
  - SEM+ (Starter Evaluation Metric, X-S1) ships VALIDATED. A starter-pool-
    anchored, sample-shrunk FIP (100 = average qualified starter), pure run-
    prevention skill. Forward-chained out of sample over 2018-2025 (excluding
    2020, 702 season-to-season pairs), SEM+ predicts a starter's next-year
    runs-allowed rate at a Spearman correlation of 0.39, beating ERA (0.26; gap
    confidence floor above zero) and edging its raw-FIP parent (0.36). It is a
    stronger forward predictor than the reliever REM+ (0.24) because starters
    carry larger, steadier single-season samples. Durability (innings, games
    started, average start length) is shown as context, never mixed into the
    skill number.
  - A "more than FIP" test (X-S3, a ground-ball-adjusted home-run expectation)
    was REJECTED: it scored 0.3905 versus plain FIP 0.3923 out of sample, so the
    plain core ships. Starter samples are large enough that the observed home-run
    rate is already a strong estimate, the same finding as the reliever SwStr
    test. Loss ledger inside data/sem_plus_eval.json.
  - 3-year SEM+ (X-S2) ships PROVISIONAL as a companion column: it forward-
    predicts a touch better than a single season (0.41 versus 0.39 on the same
    starters, gap not statistically separable) and is steadier by construction.
  - Team Rotation+ rolls SEM+ up by starter innings; yearly history tabs read
    per-season boards from data/starter_history.json (2021-2025).
- New modules sem_plus.py (reuses the validated REM+ FIP machinery) and
  starter_export.py; run_monthly steps 6b4e (starter lab) and 6b4f (starter
  export + history); registry now 57 rows; glossary adds sem_plus and
  sem_plus_3yr. Golden artifacts byte-unchanged.

## 2026-07-02 (follow-up Wave B1: reliever metrics)

- Bullpen Leaderboards gains a richer, honest reliever picture. Three gated
  experiments (pre-registered before any number was computed; harness
  tools/rem_plus_lab.py, seed 20260702):
  - REM+ skill overhaul (X-R1) was REJECTED at its gate. The owner's central
    "make REM+ more than a FIP proxy" ask was tested directly: shrink the K
    component toward a SwStr-implied expected-K prior instead of the pool mean.
    Candidate forward rho 0.2277 vs the incumbent FIP core 0.2246, bootstrap gap
    lo95 -0.0066, a wash within noise. The incumbent already regresses K% by
    sample; at reliever volumes observed K% is a strong enough estimate that a
    SwStr prior adds no forward signal. The FIP-based REM+ skill core stays
    unchanged and REM+ published numbers are unchanged. Loss ledger
    data/rem_plus_swstr_eval.json.
  - 3-year REM+ (X-R2) ships PROVISIONAL as a companion display column. An
    IP-weighted trailing-3-season REM+ forward-predicts next-year run prevention
    at least as well as one season (0.2366 vs 0.2316 on the same 668 arms; the
    gap is not distinguishable from zero), and it is more stable by construction,
    since single reliever seasons are noisy. Its value is stability, not sharper
    prediction. Joined into the leaderboard by MLBAM like gmLI 3yr.
  - RIV+ (Reliever Impact Value, X-R3) ships as a new realized-VALUE column, the
    two-number design the owner asked for: REM+ stays pure skill, RIV+ carries
    the leverage-weighted impact. RIV+ is a 100-anchored index of the wins a
    reliever actually added (WPA-primary, with a shutdowns-minus-meltdowns
    overlay). Both pre-registered checks passed: RIV+ is materially less
    repeatable year to year than REM+ (0.209 vs 0.352, confirming why leverage
    stays out of the skill scale) and it tracks what teams pay relief free agents
    better than REM+ (0.576 vs 0.508). Computed live in rem_plus.score_riv_plus;
    accountability artifact data/riv_plus_eval.json.
- Yearly reliever history: data/bullpen_history.json carries per-season
  qualified-reliever boards (2021-2025) for the /mlbstats/ history tabs, so users
  can read past seasons and see how REM+ (skill) and RIV+ (impact) played
  forward. Monthly refresh wired as run_monthly steps 6b4c (reliever lab) and
  6b4d (history). Registry now 55 rows; glossary adds riv_plus and rem_plus_3yr.
