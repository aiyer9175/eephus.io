# Master plan 2026-08-03: the eight owner asks (GFX overhaul, site audits, eFV program, WAR basis)

Written for Claude Opus 5 to implement. Every file:line below was verified by a 10-lane
read-only recon on 2026-08-03 against the current tree (main @ 5325440, 23 commits ahead of
origin). Treat citations as ground truth as of that date; re-verify anything the tree has
moved under.

## 0. Ground rules (read before any edit)

1. **NEVER edit source while pytest runs.** conftest snapshots dirty files at session start
   and git-checkouts whatever became dirty by session end; mid-run edits are silently
   reverted. Run the suite once, serially, from the orchestrator. Forbid pytest inside
   parallel agents.
2. **The nightly box pipeline runs ~00:30-04:00 local and rewrites data artifacts under
   you.** Before diagnosing a red, check `git status prospect-tracker/data/` and artifact
   mtimes. Do not run regens or commit data churn in that window. The box is the single
   writer of gitignored artifacts (prospects.db, timeseries.json, trade_values.json,
   mlb_projections.json, xfv.json regen, source_backtest.json).
3. **23 commits on main are NOT pushed** (fa4e8ea..5325440). The box also owes: (a) the
   RUNBOOK_2026-08-03 two-pass regen (run_monthly -> `python efv_export.py` -> run_monthly
   `--rebuild-only`; nightly does NOT run efv_export), (b) the id+stats resolution pass
   (241 id bindings local-only), (c) statcast standout/recent repopulation in SERVED data,
   (d) build_site restamp of 18 shells. `test_xfv_golden_fingerprint` fires on the box eFV
   regen and wants restamping. Push first, box regen second, beta sync only after push
   (docs/RUNBOOK_2026-08-03.md:42). Do not start lanes that need fresh served artifacts
   before this choreography runs.
4. **Deliberate suite reds** (do not "fix" blindly): `test_recenter_remainder_near_zero`
   (bound stays 3; currently 3.02, see Lane F), `test_board_basis_coherence` strict xfail
   (history tilt gap), NPB parser red (Lane J repairs it). A new `data/*_eval*.json`
   without a registry row turns the suite red; a measured no-ship is verdict `deprecated`
   plus a MODEL_GLOSSARY `"internal"` mapping; `unvalidated` requires `eval_artifact: null`.
5. **Copy rules**: no em/en dashes anywhere user-facing (tools/strip_emdashes.py --check +
   tools/copy_lint.py gate); eFV rounds NEAREST, consensus FV rounds CEIL; assets/*.js
   null marker is `" - "`.
6. **Measurement discipline**: every model claim gets forward-chained evaluation on the
   existing harness, compared against the shipped champion, with MDE floors (hit 0.017 /
   pit 0.016 Spearman) and a zero-information control. Do not trust a single-pass agent
   measurement on this repo (3 of 5 agent verdicts were wrong on 07-31; adversarial
   verification caught all three). Ship only measured wins; commit losses to the registry.
7. **The banned-experiment ledger is binding.** Registry rows `xfv_hitter`
   (data/model_registry.json:534-545) and `xfv_pitcher` (:561-573) plus
   docs/efv-2026-07-29/DEFECT_C_LOSS_LEDGER.md and docs/efv-2026-07-30/*GATE*.md list every
   measured null. Highlights that must NOT be re-attempted blind: hitter power features
   (5 rejections), level-weighting family, two-part P(MLB)xE(WAR), LightGBM stacks, tail
   fixes, ETA feature, decimal-age feature, peak-WAR training target, odds re-key,
   provisional map re-point (3 of 6 stop conditions fired), surplus map refit, statcast
   into /projections/, K-prior, wRC+ as eFV feature, seasons_at_level for hitters.
8. **Commit explicit paths only** (never `git add -A`); running build_site.py or exports
   regenerates artifacts, restore everything except intended asset-hash bumps before
   committing. ruff 0.12.0 IS installed (`--select F821` gate exists); node is available
   via `ELECTRON_RUN_AS_NODE=1 ".../Code.exe"`.
9. **Owner-decision queue**: items marked [OWNER] below must be surfaced with measurements,
   never resolved silently.

Lanes A-C and G-I are display/consistency work (parallelizable). Lanes D-F are model work
(gated, serialized within themselves). Lane J is cross-cutting hygiene. Suggested order:
J0 (push/box choreography) -> A, B, C, G, H, I in parallel -> E, F -> D (the WAR program,
its own multi-session track).

---

## LANE A: generateGFX overhaul (photos out, names first, one font, no clipping)

Owner asks: remove player pictures from GFX, names instead; use the reclaimed space to
de-cramp; fully overhaul so there are no missing-space name bugs, wrong fonts, or
disappearing elements.

Current system map: prospx/index.html:33045-35786 (html2canvas engine; ~40 functions,
inventory verified 2026-08-03). Formats `_GFX_FORMATS` :33268-33281; defaults `_gfxOpts`
:33290 (rows layout on wide 1600x900 as of v46). A second, canvas-native engine
assets/eephus-gfx.js (788 lines) serves FA/Projections/mlbstats/news boards. Photo
plumbing: `_gfxHeadshotURL` :33649, `_gfxChipPhotoCss` :33705, `_gfxAvatar` :33720,
`_gfxListPhotoCss` :35046.

### A1. Remove player photos from board GFX; redesign rows as a names-first table
- Flip `_gfxOpts.photos` default to false and REMOVE the photo cell from the rows layout
  (`_gfxListRowHtml` :35062-35095) and the chips layout entirely (chips exist to showcase
  photos; with photos gone, retire chips from the layout select or keep as a hidden legacy
  option). Rebuild `_gfxListGeoFor`/`_gfxListColumns` (:35012, :35029) for text-first
  geometry: reclaim the 30px photo square + gap into the name field.
- New row budget: raise name to 14-16px bold (from 12.5/11.5), raise meta from 9px to a
  hard 11px floor (the chip work already established "no text under 11px" at :34879), keep
  rank 24px, FV badge right-aligned, team logo (16px) stays as an OPTION under the
  existing `logos` toggle since the owner only asked to remove player pictures.
- Kill the known cramp/bleed list while in there:
  - Ellipsis + step-down sizing for card names that today wrap unguarded: prospect-card
    44px hero name :34511, compare 22px :34770, farm 40px title :34680, mini pack 18px
    :34848. Use a char-count step-down (or measure via canvas) instead of wrap.
  - Compare card: give the three player columns a shared grid (photo/name/meta/badge rows)
    so a long name cannot misalign the columns (:34765-34774).
  - Honest aspect: every board pins min-height only (:35261-35264); when the geometry
    search falls past its floors (:34964, :35040) surface "extends past 16:9" in the
    footer or auto-switch format.
  - `GFX_MAX_ROWS 200` canvas-cap guard stays (:35124-35132).
  - Pack sheet: fix the returned `w` lie (:35150-35158) and derive pack columns from the
    selected format instead of fixed 3-across.
  - Dev-mode assert in the row/chip renderers (`r && "name" in r`) so a raw un-normalized
    item renders loud, not blank (the 2026-08-03 chip bug class, comment :35235-35243).
  - `_gfxAwaitAssets` also walks `getComputedStyle(node).backgroundImage` (:33070-33078
    currently inline-only).
- Default `count` to 100 when layout=rows and format is wide/board, and persist last-used
  opts in localStorage (today session-only, :33290).

### A2. Single-subject cards (prospect card, farm card, compare) [OWNER]
The hero prospect card is built around a 264x352 headshot (:34124). The directive read
literally removes it; a typography-led card (big name block, FV badge, tile rail,
tool radar, career table) is the default deliverable. Implement photo-off as the DEFAULT
for all card kinds but keep the `photos` checkbox working, and surface to the owner:
"cards are now name-led; the toggle restores headshots if you want them only on cards".
Do not delete the photo pipeline (headshots.py, photo_ctx.json); prospx page UI still
uses it outside GFX.

### A3. One export font, everywhere
- Today the GFX inherits `--font-retro` whose first families are Windows-only (MS UI
  Gothic / MS Gothic, index.html:234-245); exports made on any other OS silently render
  in SF Mono/Menlo/DejaVu, which invalidates every px budget. Fix: self-host ONE face
  (DotGothic16 already has a @font-face at site.css:19-20; else vendor Roboto Mono), put
  it FIRST in all GFX-generated HTML and in the SVG literal stacks (`_gfxToolRadar`
  :33943, `_gfxRadarOverlay` :34699, `_gfxFvOverlay` :34725, wordmark SVG Georgia
  fallback :33806), and `document.fonts.load()` the exact weights before capture
  (`_gfxAwaitAssets` already awaits fonts.ready; make the GFX face explicit).
- eephus-gfx.js has NO font preload before `g.font` drawing (grep 0 hits); first-open
  canvases draw in fallback mono. Add a fonts.load await in `open()` (~:755).
- Trim the Google Fonts request (index.html:67-70): Inter/JetBrains/Source Serif/VT323/
  Press Start 2P are in no token stack; the load only slows fonts.ready.
- Fix the stale refractor sync pointer (index.html:115 says ~L26970, actual :33903), or
  better: derive `_gfxRarityGradient` stops at runtime via getComputedStyle so there is
  nothing to hand-sync.

### A4. Verification protocol (all measured, not eyeballed)
Run the shipped layout functions under `ELECTRON_RUN_AS_NODE` (extract script blocks
first) and assert: 0 empty cells at n in {10,25,50,100} for every format; no text below
11px; vertical fill >= 90% on wide/board; name field >= 20 chars before ellipsis at
n=100 wide. Then a headless Chromium pass that actually exports PNGs for the full
matrix (7 formats x kinds x light/dark) and checks canvas non-blank + expected pixel
dims. Keep the acceptance numbers in the session record.

---

## LANE B: eFV grades and rankings, one basis everywhere

The board basis is `xfv_grade` = `vf.outcome_implied_fv(E[6yr WAR])`, fingerprint
`xfv_grade|scale=off|grademap=outcome_pooled@6dbe8353f3bb|roles=usage_both|feats=dbb1bc2a`
(storage.py:4891). Recon found these divergences, in priority order:

- B1 **P1: /projections/ shows the RETIRED quantile as eFV.** proj_export.py:577-585
  display precedence is quantile-first; the board flipped to raw xfv_grade 2026-07-25 and
  build_site got the same repair (build_site.py:785-804) but proj_export kept its own
  copy. Reorder to `efv_board_scale.board_value` -> realized -> quantile; keep `price_fv`
  (:586-594) on the quantile (deliberate, documented); fix the stale "matches the PROSPX
  board" comment. Needs a box export to serve.
- B2 **P1: `_gradePrimary()` overloads state.sort.** prospx/index.html:32429 returns
  "xfv" for ANY sort other than literal "fv", so a Consensus-mode user who sorts by age
  or loads `sort=eta` silently flips 19 surfaces (call sites enumerated: 13097, 15689,
  22416, 32287, 32532, 33503, 33577, 33764, 33775, 34003, 34315, 35959, 46827, 49045,
  plus GFX legends). Fix: dedicated `state.gradePrimary` written only by the grade toggle
  (:54687-54698; precedent `state.debutGrade`), sort dropdown stops implying grade choice
  (:54706-54719), URL param + resets updated (:13425, :54954, :36305). Browser-verify.
- B3 **P2: /fantasy/ has two different "eFV"s on one page.** Dynasty column serves
  `xfv_grade_quantile` labeled "The eFV grade" (fantasy_export.py:497-519, fantasy.js:241)
  while the callup section serves raw `xfv_grade` (fantasy_export.py:67-75). Display the
  board grade in both (keep the quantile inside the blend score input, which is a
  registered legit use), or relabel.
- B4 **P2: glossary eFV entry contradicts its own restamp** (data/glossary.json:4828
  still claims rank-preserving-onto-consensus + dollars-priced-on-displayed-grade, both
  retired). Fix in the generating build_glossary_* source, not the JSON.
- B5 **P2: GFX basis leaks**: spotlight GFX prints consensus while the on-screen list
  forces eFV (prospx:33547 vs :17642); IFA GFX applies ceil to values that may be
  eFV-basis and the footer hardcodes "badge = consensus FV" (:33555-33564, :33785 vs
  ifa_export.py:132-142). Route both through `gradeBlock`/fv_basis-aware rounding.
- B6 **P3 batch**: build_site banker's rounding on eFV labels (`int(round())` at
  build_site.py:1166, :1302, :1311-1316; use floor(x+0.5) per the :889 precedent);
  trademachine.js search/seed sub-lines print raw unrounded consensus (:180, :207);
  consensus-mode lead rank is the eFV-basis overall_rank (prospx:32535, :34316; label it
  or compute a client-side consensus rank); IFA progression chip tiers off fvCeil for eFV
  values and mixes bases in its delta (:25194, :25198); stale-doc sweep
  (efv_board_scale.py:116-119 vs :170-183 contradiction, prospx:32228-32241 rebase now
  deletable post-A2-repoint pending served-artifact confirmation, prospx:29876,
  trademachine.js:490); add a pin test for fa_fit's deliberate consensus-scale
  `xfv_grade_quantile` dependency (fa_fit.py:389-397) so a future quantile removal cannot
  silently break it.
- B7 [OWNER] **Provisional vs flagship map divergence is deliberate but invisible.**
  efv_ungraded's affine map grades the same predicted WAR ~7-12 FV below the flagship
  through 1.5-3.5 WAR (efv_ungraded.py:107-141 vs value_framework.py:2953) and the two
  interleave on one board ordering (prospx:32151, storage.py:5009). The re-point was
  measured and REFUSED (3 of 6 stop conditions; docs/efv-2026-07-30/
  PROVISIONAL_GRADE_MAP_GATE.md); do not re-attempt. The open question is purely display:
  does the owner want a marker beyond the dashed border. Surface with examples.

Deliberate exceptions that HOLD (verify, do not "fix"): draft/overseas/entity pages stay
consensus (eFV abstains without pro track record); fa_fit blocker threshold stays
consensus-scale; ToolDvM+ stays consensus tool grades.

---

## LANE C: Trade Machine consistency with eFV surplus

State verified 2026-08-03: `apply_platform_surplus` (bayes_trade_value.py:4114-4291)
repoints prospects to xfv.json surplus_mm (top-5 spot check EXACT match), vets to
surTotal-first (:150-166), tiers/letters off the final value; JS letter cuts match python
exactly; anchor outranks every archetype floor; floors are FV-anchored. Fix the residue:

- C1 **Artifact race**: trade_values.json exported at 22:10, xfv.json finalized 22:12;
  92 prospect rows (2.0%, max $5.7M, cade_obermueller) disagree with prospx until the
  next TM export. Reorder the pipeline so the TM export reads the FINALIZED xfv pass
  (run_monthly step order; d9 runs the trade export, see pipeline-slim notes), or re-run
  the TM export after efv_export in the chain.
- C2 **Served-wrong rows**: the 3 `bayes_unrepointed` rows are identity collisions
  (kelvin_herrera age 18.6 "debuted" HOU, jose_ortega, rowan_wick). Root-cause the
  name-key collisions; resolve identity or exclude. An 18.6-year-old under a retired
  reliever's key is visibly wrong on a served board.
- C3 **GRPO leak on unrepointed rows**: `grpo_fv_adj` still shifts the prior inside the
  bayes compute (:3378-3390) while the UI promises "does not change the surplus"; zero it
  in compute or assert repoint coverage == 100% of served rows.
- C4 **Constant unification + parity guards**: bayes-internal tier labeler (:3665-3676,
  low>=2) vs `_platform_tier` (:4000-4013, low>=0); make the internal path call
  `_platform_tier` or delete it. Add a pytest that regex-extracts `_tbGrade` cuts from
  trademachine.js and asserts equality with `_TRADE_GRADE_CUTS` (:4021); none exists.
  Fix docstring drift at :4120 ("surNpv" -> surTotal-first).
- C5 **Display coherence**: evaluator dollar colors break at 80/35/12 while board tiers
  break at 40/20/8 (trademachine.js:125-133 vs :463-466); unify on the tier scale.
  Projection-sourced vet rows have null lo/hi bands (deliberate basis guard,
  :4246-4252) but warTotalP10/P90 exist; price a projection-basis band so vets get the
  range tooltip. Show the surRos rental split as a column/chip (today label-only,
  trademachine.js:161-165).
- C6 **Open pricing work** (models, gated): star-rental deadline premium (registered at
  proj_export.py:337-342; needs a deadline-trade backtest harness before any constant
  ships); the 167 published `no_contract` pre-arb vets (price at league-minimum salary
  basis is the registered decision, bayes:4376-4379; largest coverage hole).

---

## LANE D: The WAR program (eWAR > fWAR > improved bWAR)

Owner wants eWAR (Will's WAR) site-wide, or fWAR, or a bWAR upgrade (FIP-based pitching,
better defense), and wants eFV/WAG backtests on the better label. Recon facts that shape
this:

- **fWAR ingestion is refused on evidence from this box**: FanGraphs is Cloudflare-403
  (docs/efv-2026-07-30/DEFENSIVE_SOURCE_PROBE.md:9-26; pybaseball FG endpoint 403,
  stats.py:3386-3389). Do not re-probe. An fWAR path exists only via Will's machine or
  the deploy box; treat as [OWNER] infrastructure question, not a default.
- **Pitcher eWAR already exists** outside prospect-tracker: milb-projections/ exports
  `pitcher_ewar.parquet` handoffs (model_version pitcher-ewar-1.1.0,
  milb-projections/manifests/BENCHMARK_MANIFEST.yaml:9-28). No hitter eWAR exists.
- **Components for an in-house WAR are already on disk**: FIP components + constants
  (fa_projection.py:161-279, proj_export.py:1229), linear weights + wOBA machinery,
  OAA+FRP 2016-2026 (data/savant_oaa.json, 13,001 rows), B-Ref war_def + runs_position
  2000-2026 (data/mlb_def_history.json), fielding innings, MLB Savant + in-house MiLB
  park factors, the in-house positional ladder (prospect_def_value.py), replacement
  level 47.7/.294 (rate_stabilization.py:69-77), and self-computed leverage (gmLI/WPA in
  mlb_leverage.py). Gaps: baserunning runs (extractable: war_daily raw CSVs carry the
  full run decomposition; extend tools/build_def_history.py:53's column set), catcher
  defense (no OAA at C, positional_fit.py:50), DRS (unavailable, out of scope).
- **The switch surface is NOT one fetcher**: 10 direct bwar_bat/bwar_pitch call sites
  (stats.py:3453, fa_projection.py:87, fa_ident.py:22, fa_pipeline.py:62,
  mlb_player_export.py:245, pal_export.py:206, proj_backtest.py:70, proj_export.py:85,
  tools/build_def_history.py:51, bullpen_export.py:490) + the career_war sqlite funnel +
  bWAR-pinned artifacts (REPLACEMENT_WINS, draft_slot_curve, the empirical FV curve fit
  on 3,037 rows at value_framework.py:2887, FV_EXPECTED_WAR + survivor curve + prospx
  FV_WAR_ANCHORS mirror, war_rate_plus frozen vintages) + copy gates that assert "bWAR"
  (build_glossary_copy_pass.py:126, build_site.py:3157, dozens of tooltips). B-Ref cannot
  be fully dropped even if the headline series changes: fa_ident keys identity on
  war_daily name_common, proj_backtest needs its stint frame, def_history needs its
  decomposition.

### D0. Prerequisite: the war_source facade
Create one module (`war_source.py`) wrapping {per-season WAR by mlbam, stint frame,
run-value decomposition, name index}, and migrate all 10 direct call sites onto it.
Behavior-neutral refactor, pinned by a byte-diff test on career_war payloads. Only after
this does any basis decision become a data-layer swap. While in there, fix two verified
bugs: stats.py:662 stale "FanGraphs flavor" comment on sabermetrics.war (same class as
5325440), and the dead fallback prospx:47138-47140 reading `sabermetrics.war_per_yr`
which no producer writes.

### D1. Build eWAR v1 = component-corrected bWAR (the fundable path)
On the B-Ref frame (which we already trust for offense + stints), recompute:
- Pitching: FIP-basis runs allowed (FIP with our park factors, HR/FB regression optional
  later), reliever leverage credit via our own gmLI (mlb_leverage), same replacement
  level. This is exactly "adjust bWAR to be better (FIP-based pitching)".
- Fielding: replace rfield with OAA/FRP where covered (2016+), shrunk by fielding-innings
  k_inn (positional_fit constants), keep runs_position; pre-2016 and catchers fall back
  to B-Ref rfield.
- Baserunning + offense: keep B-Ref runs (extract runs_br via build_def_history
  extension) so the accounting identity stays closed.
- Cross-check the pitcher side against Will's pitcher_ewar parquet where the handoff is
  available; disagreements are the review queue.
Ship as `data/ewar.json` + registry row + eval artifact. No consumer changes yet.

### D2. Validity gates (pre-registered, before ANY consumer flips)
1. Team-level: sum of player eWAR vs actual team wins, 2016-2025; eWAR must beat bWAR on
   team-win correlation/MAE (the standard WAR validity test) or at minimum tie while
   beating on the pitching sub-test (FIP-basis year Y predicting year Y+1 runs allowed
   better than RA9-basis).
2. Player-level persistence: year-to-year self-correlation by role (FIP-based pitcher WAR
   should persist better; that is its whole case).
3. Label quality for eFV: re-run the eFV eval protocol (tools/efv_lab_runner.py) with the
   TARGET series swapped to first-6yr eWAR. The decision metric is the model-vs-consensus
   MARGIN (both scored on the same label): a cleaner label should widen eFV's edge. Also
   re-run WAG calibration and the reliability monitor on the new label. If the margin
   does not widen outside noise, the label swap for eFV is a no-ship (owner rule: change
   nothing not explicitly proven to improve the model).
4. Same protocol for the FA/projection stack (fa_backtest Gate 1 on eWAR labels).

### D3. Staged rollout (only what passes its gate) [OWNER at each stage]
- Stage 1: eWAR as a DISPLAYED column beside bWAR (mlbstats boards, player cards),
  glossary entry, methodology note. Zero model risk.
- Stage 2: eFV + WAG + surplus backtests re-labeled onto eWAR behind a config flag, with
  the full artifact-refit cascade: fv_outcome_curves re-fit, FV_EXPECTED_WAR + survivor
  curve + FV_WAR_ANCHORS, empirical anchors, draft slot curve, Platt odds refit-check,
  reliability regen, prospx_current re-freeze (capture INSIDE
  `vf.valuation_set("prospx_current")`), fingerprint gains a `label=` term (a fingerprint
  only guards what it NAMES), epoch bump, two-pass export. This is a coordinated
  re-anchor: one session, one runbook, box executes.
- Stage 3: site-wide display swap (tooltips, glossary war definition, about page, copy
  gates updated in the same commit as the assert flip).
If D2 fails: keep bWAR, ship eWAR as the Stage-1 display column only if the owner still
wants it labeled clearly as experimental, and record the loss in the registry.

---

## LANE E: eFV model program (bug sweep done; now the experiment queue)

Current champion state (verified): features `_FEATURES_HIT` 14 / `_FEATURES_PIT` 9
(efv_model.py:60-274), lambdas hit 0.70 pinned / pit dynamic (:317-332), K_REL 50/40,
SIDE_FAIRNESS on, overlays on, odds Platt LIVE at all 3 seams since 07-31
(efv_score.py:1292/1812/2191), reliability after-basis ECE 0.0754 vs 0.10 tripwire.
Headline OOS: hit blend 0.3791/AUC 0.7715 vs consensus 0.332/0.7446; pit 0.3056/0.7195
vs 0.2638/0.7102 (data/xfv_eval*.json, 2026-07-24 vintage).

### E0. Hygiene first (correctness of measurement, the owner's "calculated correctly")
- Regen the stale eval artifacts: xfv_eval_pitcher.json predates the `seasons_at_level`
  ship and both predate the outcome_pooled grade map. Registry rows point at stale
  artifacts. Record the served dynamic pit lambda into the artifact
  (`shipped_lambda_provenance` slot exists) to close the 0.59-vs-0.54 discrepancy.
- Reconcile the reliability-frame ambiguity (0.0754 served vs 0.0263 lab expectation:
  different frames; state which in the artifact note).
- Ship a live-board disagreement artifact: a ranked `xfv_minus_consensus_display` view
  (run_live already computes everything, efv_score.py:1949-1952). This is the owner's
  "closer on the biggest disagreements" instrument: it makes the disagreement tail a
  standing review queue instead of an anecdote.
- .cache/milb_full_stats has one reader and NO producer (wrc_rates.py:54, 53.3% stale);
  either write the producer or register the cache frozen.

### E1. Run the four already-built, gated-not-run experiments (highest expected value,
zero new code):
1. **B3 level blend** (exposure-weighted multi-level rates): defect measured at 22%/19%
   of multi-level rows scored on a lesser-exposure level, ~100k PA/BF discarded
   (efv_dataset.py:395-414; docs/efv-2026-07-30/B3_LEVEL_BLEND_GATE.md). Run the gate.
2. **PACE_FROM_ENTRY** (efv_model.py:277-307, kill criteria pre-registered).
3. **C3-ETA age interpolation** KM gate via eta_backtest protocol
   (docs/efv-2026-07-30/EFV_LANE_GATES.md:406-423).
4. **GATED_CANDIDATES C1-C5** (docs/efv-2026-07-29/GATED_CANDIDATES.md): C3 aStuff+
   denominator (7.16 vs advertised 10 pts/sigma) is the largest pure-correctness item;
   C1 SC+ shrink, C2 draft/overseas z-scale (atomic with `_tbsNorm`), C4 RPS+ TBS term,
   C5 projection-surplus anchor.

### E2. New drivers to test (none on the banned ledger; forward-chained, MDE-floored,
permutation-controlled; expect mostly nulls and say so):
1. **MiLB park-factor adjustment of rate inputs**: obp_rel/k_rel/ops_rel are level-normed
   but park-blind; in-house MiLB park factors exist for 202 venues
   (park_factors_export.py, efv_park_line.py). Test park-adjusting the rate features in
   the matrix build. This is the one substrate improvement with a genuinely new,
   validated data source behind it.
2. **Statcast physics overlay extension to A/FSL 2021+** (registered future extension;
   overlay machinery already shipped and uncapped). Coverage gate first: if A-ball
   tracking rows are too thin per cohort, record and stop.
3. **eWAR label swap** (Lane D3 Stage 2 gate): per the owner's own hypothesis this is
   the biggest permissible accuracy lever left, since the model is at the trainable-data
   ceiling on features.
4. **wOBA-component rate features** (obp_rel -> woba_rel using the D2 wRC substrate):
   LOW prior (wRC+ as a feature was null at 0.0003 vs MDE 0.017); run once through
   efv_lab_runner, expect null, commit the ledger entry so it stays closed.
5. **Cross-side top-knot prior re-read** when 2026-27 cohorts resolve (FV60 tier gap
   0.1245 on n=32 is prior-dominated; a curve prior item, NOT a model change). Time-gated;
   register, do not force.
Time-gated instruments to leave alone: the promo watch (frozen cohort, scores 2027-01-15),
injury-history feature (~2028), 23 cohort-slice ideas (fold artifacts).

### E3. Protocol reminders specific to this lane
Two-metric gates must agree in sign (AUC up with rho down is NOT support); a lambda or
weight conclusion is only as good as its labels; PINNED_MIX is a band, the fingerprint is
exact; any ship = epoch + fingerprint term + sign-declaration test + registry + glossary
moved together (E1 precedent, docs/efv-2026-07-30/E1_REPEAT_LEVEL_GATE.md:134-137).

---

## LANE F: MLB Free Agency + MLB Projections models

Verified state: the 361-vet team drop is FIXED (proj_export.py:479, test_proj_team_join);
league roster_war_sum 932.8, remainder 3.02 vs the <3 bound (one nudge from the first
green since 06-12); Gate 2 passes (guar 9.678 vs 10.860); Gate 3 fitted-transfer loses to
the live analog and the concentration tripwire FAILS in the committed artifact (LAD top1
share 0.52 vs 0.25 threshold). Work items in value order:

1. **Re-measure cohort intercepts on post-F-DEF paths** (the last red): the 07-31 refit
   lost its holdout on E3 paths, but commit 4853e68 changed every vet path again.
   Harness proj_backtest.py writes challenger_wins; serving already gated
   (proj_export.py:713-720). Scoreboard: the remainder bound.
2. **Regen the stale gate artifacts on the shipped engine**: fa_gate1_eval (pre-F-DEF
   numbers committed; the improved 0.5736 exists only in a commit message),
   fa_gate2_eval, war_cohort_eval (2026-06-25 vintage). Standing registry rule requires
   artifacts to match the shipped champion.
3. **Score the LGBM market challenger once** (`run_market_gate(challenger=True,
   persist_dpw=False)`); ship criteria coded at fa_backtest.py:622-631; committed
   artifact has no challenger block, so "OLS retains" is an untested prior.
4. **Re-run Gate 3 + concentration under the SHIPPED weights** (fa_config.yaml:154
   need .40/behavior .45); if LAD concentration still fails, the measured lever is the
   need component; any re-weight gates on concentration PASS with MRR not-worse.
5. **fa_dpw_series re-anchor** [OWNER]: the deliberately-frozen +16% $/WAR drift
   (14.92 -> 17.29). A coordinated box regen (18 valuation-set tests + golden + two-pass
   ordering), not a ride-along. Present the drift measurement and let the owner pull the
   trigger.
6. **Make fa_penter scorable for 2026-27**: persist a per-winter enter_prob snapshot at
   window-open (Oct 1); events accrue in fa_events but predictions live only in the
   continuously-overwritten fa_class.json; test_fa_tier1.py:362-385 is the waiting gate.
7. **Promote the mega slice to gating** after item 2 (currently tracked-only, a
   regression there is invisible to `pass`).
8. **Reconcile depth-pool docstring vs test floor** (proj_export.py:776-778 "~870-930" vs
   the 900 floor; the test docstring itself says both should not stand).
9. Registered, time-gated: h5 star tail (first holdout with 2027 labels; h2-ban precedent
   binding), star-rental premium (needs the deadline backtest harness, Lane C6).

---

## LANE G: MLB Stats module

The bullpen data-contract red is RESOLVED (c26c6d6; REM+ 203 = Mason Miller, honest;
harmonic-anchor invariant green vs the 08-01 artifact). Do not re-litigate the 40..200
band. Improvement queue (all client-side unless noted):

1. Frozen-vintage disclosure: payload carries `multiyear`/`war_rate` vintage blocks the
   frontend never renders (bullpen_export.py:352-356; zero "multiyear" refs in
   mlbstats.js). Render generated_at in column tooltips/board note.
2. Provisional-row ghosting: `tr.is-provisional td {opacity:.82}` (site.css:1816) defeats
   the frozen first column's opaque fill; apply opacity to text color only.
3. PAL frozen-column collision: /pal/ inherits the `.mlbstats-scroll` freeze but its
   first column is the rank digit, orphaning the name (pal.js:297); scope the freeze to
   `.mlbstats-app` or freeze PAL's name column.
4. Season + sort into the hash (writeHash/readHash mlbstats.js:755-784) so history boards
   deep-link.
5. Missing glossary ids: `rotation_plus`, `offense_plus`, `rng_plus`; fix the borrowed
   `data-gl="sem_plus"` badge (:1143) and the Lev-Deploy+ `bullpen_plus` proxy (:282).
6. Per-player trend sparkline: 2021-2025 history JSONs + live board are enough for a
   row-expand REM+/SEM+/HEM+ by-season line; today users flip season pills and re-search.
7. Freshness banner parity: bullpen-only `banner()` (:600-616) extended to
   starters/hitters/leverage (payloads carry as_of).
8. GFX specs for Team Rotations / Team Lineups (:1008, :1677, :2147).
9. History wRC+ column (hitter_export.py:211 acknowledged drop; feed serves past
   seasons).
10. Filters: team select + role chips + min-IP/PA slider (data already on rows).
11. Port the served-artifact contract tests (harmonic anchor, sort, pool count) from
    bullpen to starter/hitter exports; today they have only smoke tests.
12. mlbstats.js gets the pinned `formatMetric` mirror + join the parity test (it is the
    one board JS outside the contract, mlbstats.js:36, :362).

---

## LANE H: Prospect pages, player pages, FA pages

From the full render-order inventory (recon lane 5). In value order:

1. **prospx Overview overload**: 15 stacked sections (prospx:49130). Add in-tab
   jumplinks; extend the `<details>` treatment (already used for scouting reports) to
   valuation + news + source blocks; promote the sidebar "Key signals" card into the tab
   below 1300px where the rail is hidden (comment :49211-49217).
2. **Duplicate playerNewsSection** on Overview AND Scouting (:49130, :49167): drop one.
3. **Merge the two Statcast panels**: statcastSection vs statcastPercentilesSection are
   mutually exclusive with different visual languages (:47729, :47742); unify on the
   percentile-slider language /projections/ uses (projections.js:1300).
4. **Mobile board trend signal**: every trend column is desktop-only (:17461-17469);
   surface fvTrend/rankTrend arrows or a micro-sparkline in the phone-visible toolstrip
   (makeListRowSummary :37726).
5. **Board chip-viz consistency**: Surplus has an outcome-bucket bar; Star Odds and PLUS%
   are bare numbers (:35892, :35943); add matching micro-bars.
6. **projections.js inline-style burn-down** (92 occurrences; start with mlbpTabs active
   state -> `[aria-selected]` CSS, scatter legend, accountability cards, compare button;
   iOS-zoom precedent site.css:1929-1933).
7. **Tab the FA player card** (the last untabbed card of the three): adopt mlbpTabs
   (projections.js:1632) for fa.js renderPlayer (:943-1048): Market / Season-by-season /
   Comps+Fits / Discussion (FA is also the only module card without a Discussion mount).
8. **FA rails on tracker/fits/archive** (boardRail only mounts on board, fa.js:807).
9. **Tape fade-mask** on `.mlb-tape-inner` (site.css:2906) matching `.mlb-sortbar`
   (:3015) so off-screen chips are discoverable on touch.
10. **Ht/Wt/BMI column demotion** to flag-gated (like Star Odds), buying a default column
    slot for a higher-value axis (e.g. SC+).
11. **dpwTrendChart pattern reuse** (fa.js:775, the best small-viz in the codebase):
    Team Outlook rows and the prospx surplus cell are natural hosts.
12. **Cross-module compare**: prospect-vs-vet compare does not exist anywhere even though
    the Trade Machine prices both on one currency; a #cmp that joins prospx and
    projections data is a genuinely new capability.
13. **#now=1 Current-slate flip** (projections.js:499-514, NOW_DEFAULT=false) once the
    soak clears; one line.
14. **prospx breakpoint consolidation** to the documented 4-tier set (prospx:439-449),
    the standing debt from the mobile pass.

---

## LANE I: Homepage + theme + holistic

Homepage reality check (rendered-file verified): ticker, sidebar (news feed + single
Top-Riser spotlight), masthead, lead story (STALE since June 5, the only article ever),
6-module grid, cross-module strip, forums placeholder, teasers. Improvements, all
build-time feasible with data already on disk:

1. **eFV distribution module**: build-time SVG histogram of `_primary_fv` with
   tier-color bands (45/50/55/61/70 matching the rarity ramp); data already in memory in
   build_home. Zero runtime cost.
2. **Stale-lead fallback**: when articles[0] is older than N days, generate the lead from
   yesterday's biggest wire event or the Top Riser (the more-soon-strip has shown for two
   months).
3. **Real scatter teaser**: replace the 16 RANDOM fake dots (build_site.py:2337-2340)
   with real (age, eFV) points. Same SVG budget, becomes truthful.
4. **Cross-module strip gaps**: add Fantasy and Leverage cards (artifacts fresh); wire
   the Trade Machine rows to deep-link (today bare /trademachine/, :2394).
5. **glossary.json transfer**: eephus-gl.js:38 fetches 366KB with cache:"no-cache" on
   EVERY page; switch to `?v=<hash>` + long max-age or defer to first tooltip. The single
   heaviest recurring transfer on the site.
6. **Date callout coverage**: only 2 events known (:2306-2311); add trade deadline,
   Rule 5, FG list season, Futures Game.
7. **Glossary teaser breadth**: rotate over the 285 real entries, not the 6-term
   hardcode (:1776-1783).
8. **Forums placeholder collapse** when Supabase LIVE() is false (eephus-ui.js:1423).
9. **Spotlight rotation**: riser/faller/hot-sample from the three spotlight buckets
   (engine already computes them) instead of one riser card.
10. **Homepage starfield FV hook**: call EephusBG.setIntensity keyed to the No. 1
    prospect's grade (only prospx calls setFV today); on-theme dark polish.
11. **/history/ discoverability**: add to footer links; it has no nav entry anywhere.
12. Optional: self-hosted team-logo sprite (~69 ESPN CDN requests on the homepage) -
    deploy-box asset decision [OWNER].

---

## LANE J: Cross-cutting hygiene + choreography

- J0 **First actions of the execution session**: push the 23 commits; coordinate the box
  runbook (see rule 3); restamp the golden after the box eFV regen; verify
  `xfv_history_is_on_board_basis()` flips true and the movement suppression self-clears;
  then beta sync.
- J1 **Seed known ids at seed_signed_draftees** (draft_promotion.py:194): write
  draft_players.mlbam_id (136/565 already populated), tjstats `_extras` ids, and
  player_photos bindings into the stats id cache so draftees never depend on name-search
  (docs/EXECUTION_2026-08-03-audit-owner-bugs.md:109-114).
- J2 **NPB parser repair** (overseas_stats.py; test_overseas_stats.py:74): fix for the
  new FG page shape AND make zero-row parses raise instead of returning empty (the
  silent-empty class that froze the 2027 FA board once already).
- J3 **History-basis xfail narrowing**: restrict to untilted rows or build as-of tilt
  inputs so the strict xfail can retire (test_board_basis_coherence.py:199-207).
- J4 [OWNER] **Grade-floor product question**: 1-6 game negative-WAR samples grade to the
  20.0 floor below the no-evidence prior (kreiling/bogenpohl class); machinery correct,
  presentation decision open.
- J5 **eephus-config.js 404 + small consoles**: keep an eye out during page work; the
  committed-blank-stub pattern is the precedent.

---

## Acceptance shape for the whole program

Each lane lands as its own commit series with: measured before/after numbers in the
commit body, suite run serially at the end (expected reds only), registry/glossary
updates in the same commit as any model/metric change, and a session record under
docs/. Items marked [OWNER] get a decision block with the measurement attached, never a
silent resolution. The WAR program (Lane D) is its own multi-session track and must not
ride along with display lanes; its Stage-2 flip is the single highest-blast-radius
change in this plan and gets its own runbook, fingerprint term, and box choreography.
