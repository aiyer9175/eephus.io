# Audit Findings: Holistic Pass 3 (2026-07-01)

Curated findings ledger for the third pre-Beta audit pass. Sorted by severity, then expected value.
Dispositions: FIXED / FLAGGED (review queue) / HIDDEN / VERIFIED-OK / NOT-REPRODUCED.
Baseline: commit 4525ec5, clean tree, 5/5 artifacts fingerprinted as `p3-base`,
model registry 39 rows (15 validated / 21 provisional / 3 unvalidated), validate() clean.

## P1

### F-01: Summed quantile totals displayed as WAR bands
- Location: proj_export.py:274 and :399 (`warTotalP90 = round(sum(p90_arr))`), fa_export.py:328,
  displayed in assets/fa.js:506 and :798, assets/projections.js:624/954/1028,
  exported by mlb_player_export.py:286. test_proj_export.py:57 asserts against the summed field.
- Issue: the total band shown as "(P10-P90)" sums per-year quantile points. The sum of per-year
  P90s is not the P90 of the multi-year total unless year-to-year outcomes are perfectly
  correlated; the displayed band is systematically too wide (overstated upside, understated floor).
  The standing methodology rule already prohibits summing ML quantile points in backtests; the
  display surface violates the same statistics.
- Impact: every FA and Projections total-WAR band a front-office reader sees is wider than the
  model's actual predictive interval. Point estimates (warTotal) are unaffected.
- Severity: P1. Effort: M (needs a path-total quantile, e.g. per-path simulation or a
  rank-correlation assumption, plus re-export and copy updates).
- Disposition: FLAGGED (review queue). Changing band semantics alters published numbers 10 days
  before launch; the fix needs an owner decision on the dependence assumption. New work in this
  pass (upside display) uses per-year quantiles only and never sums them.

## P2

### F-02: Module apps fail silently when the data payload is missing
- Location: assets/mlbstats.js:359-362 (fetch failure -> DATA=null -> render), and the
  equivalent loaders in assets/projections.js, assets/pal.js, collegesavant apps.
- Issue: on fetch failure or non-OK response the apps render blank or partially blank pages with
  no visible error. PROSPX (prospx/index.html ~10236-10298) is the reference: structured
  `__error` payload plus a visible state message.
- Disposition: FIX in this pass (lane H), with per-page test assertions that the error-state
  string exists.

### F-03: Glossary version stamp hand-set in two diverging places
- Location: data/glossary.json ("2026-06-24") vs build_glossary_data.py:277 ("2026-06-10").
- Disposition: FIX in this pass (lane H): derive the stamp from the build, remove both literals.

### F-04: Copy gates not enforced by the test suite
- Location: tools/copy_lint.py and tools/strip_emdashes.py exist but have zero references in
  conftest.py or any test; nothing stops a copy regression from landing.
- Disposition: FIX in this pass (lane H): new test_copy_gates.py invokes both.

### F-05: Same-concept stabilization constants scattered with no provenance
- Location: storage.py:8373 (K_AB=170), storage.py:8352 (K_IP=50),
  college_translation.py:64 (BF_PER_9=38), college_translation.py:68 (SLOPE_SHRINK_K=20),
  pal_conversion.py:346 (NEED_ERA_SHRINK_IP=45).
- Issue: five stabilization/shrinkage constants across three modules, two of which (K_IP=50 vs
  NEED_ERA_SHRINK_IP=45) shrink the same quantity (ERA) toward different pseudo-counts with no
  documented reason.
- Disposition: FIX names in this pass (lane B): central module with provenance comments, values
  unchanged, output-diff proven neutral. Value unification is FLAGGED (review queue) because it
  changes published numbers.

### F-06: Replacement-level 47.7 duplicated as two literals
- Location: proj_export.py:598 and proj_backtest.py:54.
- Note: value_framework bucket floors (surplus_floor_usd) are USD surplus floors, a different
  concept; they are intentionally separate and must not be "unified" with the runs baseline.
- Disposition: FIX in this pass (lane B): single shared constant or cross-assert test.

## P3 / informational

### F-07: Prior recon claims that did not reproduce
- "K_AB duplicated in college_translation.py": wrong; that file has BF_PER_9 and SLOPE_SHRINK_K,
  no K_AB. Corrected sites listed in F-05.
- "Run environment implemented in multiple sites": grep for RUNS_PER_WIN / run_env found no
  duplicated run-environment constant outside tests. NOT-REPRODUCED.
- "data/fa_aging_curves.json is unused": wrong; fa_projection.py declares it CURVES_PATH (L50)
  and writes it (L394). It is the committed fit artifact. Do not delete.
- "Pre-existing failing bayes test": REPRODUCED on the full baseline run (1 failed / 1687
  passed / 17 skipped): test_fv50_active_prospect_gets_trade_rarity_floor asserted the
  final-value clamp tag must fire, but the tune in 2a00e00 plus the surplus realignment moved
  the fixture 0.2 above the floor, so the clamp legitimately no longer binds. The policy
  invariant (trade_value_mm >= active rarity floor) held throughout. FIXED (9fe4852): floor
  exposed in the in-memory result (board_slim drops it from the written payload; trade_values
  .json unchanged), test asserts the invariant instead of the tag. Suite fully green.
- "Glossary copy backlog is 78 items": ledger totals in docs/archive/glossary-copy-audit.md are
  PASS 158 / LIGHT 8 / REWRITE 3 / RESTRUCTURE 13 -> 24 open items.

### F-08: /mlbstats/ headline metrics lack on-page explainers
- REM+ and Bullpen+ have glossary entries but no on-page explainer or glossary deep-link.
- Disposition: FIX in this pass (lane H).

### F-09: positions_played.json refresh wiring
- run_monthly.py step 3a-ii (~L1684) calls fielding_positions.build_positions_played gated on
  `not skip_stats`. VERIFY the daily path's flag value, then document in DATA_SOURCES.md.

## Pre-registered experiment gates (written before any experiment ran)

Owner policy for this pass: gated experiments; ship only on clear gate pass with before/after
documented; marginal or failed results go to the loss ledger and review queue. All stochastic
steps seeded.

### X-ISO: Out-of-fold isotonic calibration of the eFV 5-bucket outcome distribution
- Hypothesis: OOF isotonic per bucket improves probability calibration without hurting ranking.
- Gate (ALL must hold, forward-chained / out-of-fold, no same-player leakage):
  1. OOF Brier score and log-loss improve versus the uncalibrated 5-bucket distribution,
     pooled and per bucket (no bucket materially worse).
  2. Forward Spearman of the resulting grade/rank versus realized outcomes does not degrade
     relative to the shipped model (tolerance: no decrease beyond -0.002).
  3. Reliability curves improve in every FV tier (no tier gets worse).
- Ship path on pass: registry row update + committed eval artifact + methodology-freshness map
  entry + expected-CHANGED pipeline_artifact_diff limited to xfv.json, trade_values.json and
  direct downstreams, each delta justified in CHANGELOG.
- On marginal/fail: loss-ledger entry in the eval artifact + review-queue spec. No ship.

### X-D1: Reliever leverage-consistency (multi-year gmLI deployment stability)
- Hypothesis: a reliever's manager-assigned leverage (gmLI) is stable enough year-over-year to
  be a meaningful displayed context metric on /mlbstats/.
- Gate: Y->Y+1 autocorrelation of gmLI on the reliever pool (min-BF qualified) is materially
  positive (rho >= 0.30 on the pooled 2018-2025 sample, ex-2020), and the metric survives a
  split-half stability check. Displayed as context (deployment), never folded into REM+ skill.
- Ship path on pass: registry row (provisional acceptable, disclosed) + eval artifact +
  glossary entry + /mlbstats/ column.

### X-D2: Age-relative outperformance index (production vs age-matched level cohort)
- Hypothesis: a displayed index of production versus same-age same-level peers adds signal
  beyond the existing age_rel_level model feature's internal use.
- Gate: forward correlation of the index with realized outcomes (graduate cohort) is positive
  and at least comparable to existing descriptive metrics (r >= 0.10 on n >= 80), and the index
  is stable under the standard shrinkage treatment (no small-sample blowups; EB-shrunk at source
  like RPS+ per the 2026-06-18 rule).
- Ship path on pass: registry row + eval artifact + glossary entry + PROSPX display chip
  (rounding: "+"-style metrics round to nearest).

## Experiment outcomes (wave 1, 2026-07-01)

### X-ISO: FAIL (loss ledger in data/xfv_isotonic_eval.json)
Condition 1 passed strongly (pooled Brier -18.6%, log-loss -16.7%, every bucket improved).
Conditions 2 and 3 failed: calibrated-rank Spearman 0.2227 vs shipped 0.2392 (delta -0.0165,
tolerance -0.002; caused by isotonic flat-segment ties) and the FV-35 tier reliability gap
worsened (0.00265 to 0.00493; 5/6 tiers improved). NO SHIP. Genuine signal recorded for a
future gated attempt: bust/bench probabilities at FV 45+ are substantially miscalibrated
(tier-45 gap 0.0946, tier-55 0.1616); a rank-preserving monotone recalibration of the
p_bucket_given_fv tables in grade space could capture the calibration gain without the
tie-induced rank loss. Harness: tools/efv_isotonic_lab.py (SEED=7, forward-chained OOF).

### X-D5: SHIPPED (artifact data/surplus_sensitivity.json)
Surplus ordering is essentially invariant to the $/WAR level: zero top-50 churn at every
shift from -20% to +20%, max top-50 rank move 2 spots (at -20% only), FV45+ rank rho >=
0.9999 everywhere. Dollar levels move roughly with the shift (FV60+ median +24% at +20%).
Two structural observations recorded: (1) FV<=40 players (3,491 of 4,000) are $/WAR-level-
invariant because the fixed-dollar low-tier anchor is not indexed to the market level;
(2) the isotonic calibration layer locally amplifies level shifts up to ~1.9x in FV 45-50
and pins ~3,300 low-tier players at the $1.44M floor. Both are pre-existing design facts,
not bugs; flagged for owner awareness.

### X-C3: DONE, keep composite as-is (artifact data/sc_plus_component_eval.json)
Hitters: Barrel%/BBE carries the contact-quality signal (r 0.254 vs first-MLB OPS, n 54);
EV weak (0.104); HardHit% and SwingMiss% ~ noise. Pitchers: SwingMiss% carries it (r 0.359
vs first-MLB ERA inverted); barrels/EV noise. The forward-chained top-2 blend beat the
composite by +0.053 (hit) / +0.048 (pit) pooled OOS r, just under the pre-set both-sides
>= 0.05 reweight rule, so the composite stays. Side finding: reference approach stats
(hitter BB% r 0.33, pitcher K% r 0.49) out-signal all contact-quality components but are
already priced into consensus FV and eFV features; do not double-count.

### Lane B (F-05/F-06): SHIPPED
rate_stabilization.py centralizes K_AB/K_IP/NEED_ERA_SHRINK_IP/BF_PER_9/SLOPE_SHRINK_K +
REPLACEMENT_WINS=47.7 with provenance; values byte-identical; consuming sites import it.
New fact: fa_config.yaml carries its own replacement_wins=47.7 (config-driven by design,
documented in the module; left separate). docs/aging-curves.md documents the three-way
aging fork as defensible.

### Lane H2 (F-03/F-04/A3): SHIPPED
Version stamp single-sourced (build_glossary_data.glossary_version(), payload now
2026-07-01). A3 audit: 22 of 24 open ledger items were ALREADY fixed in the live payload
by earlier one-time updaters (ledger was stale); 3 remaining mutations applied via
build_glossary_copy_pass.py (240 entries; idempotent). PWR+ confirmed alias-only, marked
legacy alias of POW+. test_copy_gates.py wires both copy tools into the suite. F-09
RESOLVED: positions_played refreshes on the MONTHLY cadence only; run_daily() never calls
fielding_positions (run_monthly.py:1689-1700 lives in main() only, gated by --skip-stats,
default False). Memory's "run_monthly 3a-ii" wiring is real but monthly, matching the
step's own comment; document in DATA_SOURCES.md.

## Pre-registered experiment gates: eFV round (written 2026-07-02, before any run)

Owner directive 2026-07-02: target eFV for any remaining improvement. Constraints
carried over: gated experiments only; clear pass or loss ledger; forward-chained
OOS with no same-player leakage; seeded; do NOT re-attempt loss-ledgered dead ends
(statcast features, power features, dedicated mean head, tail transforms, def-value
swap, level_jump, type-conditioned consensus weights).

### E-ISO2: Rank-preserving monotone recalibration of the eFV bucket distribution
- Successor to the rejected X-ISO. Hypothesis: a strictly-increasing monotone
  recalibration applied in GRADE space to the p_bucket_given_fv anchor tables captures
  the X-ISO calibration gain (FV45+ bust/bench gaps 0.09-0.16) without PAVA tie-flattening.
- Gate (ALL, forward-chained OOF, SEED documented):
  1. Pooled and per-bucket Brier/log-loss improve (no bucket materially worse).
  2. Forward Spearman delta >= -0.002 vs shipped (strict monotonicity should make this
     hold by construction; it must still be measured).
  3. Per-FV-tier reliability: no tier worse, including FV-35 (the tier X-ISO degraded).
- Ship path on pass: changes published bucket probabilities -> surplus -> trade values.
  Expected-CHANGED output-diff limited to xfv.json + trade_values.json + downstreams,
  every delta justified in CHANGELOG; registry row update + eval artifact + freshness map.

### E-LAMBDA: Per-cohort blend lambda for the eFV/consensus blend
- Hypothesis: the global per-side blend lambda (pitchers 0.66 after the 2026-06-24 recal)
  leaves cohort-level headroom; intl bats is the lone cohort where consensus still beats
  eFV, suggesting cohort-conditional weighting (NOT the rejected type-conditioned source
  weights; this is the model-vs-consensus blend, not source accuracy weights).
- Gate (forward-chained by cohort-year, out-of-fold lambda selection):
  1. Pooled OOS Spearman does not decrease on either side.
  2. At least one cohort improves materially (rho +0.010 or better) and NO cohort
     degrades by more than 0.005.
  3. Selected lambdas are stable across folds (no oscillation; report per-fold choices).
- Ship path: changes xfv_grade for affected cohorts -> same expected-CHANGED discipline.

### E-STUFF: Upper-level pitcher Tier-2 overlay (aStuff+ / whiff analog)
- Hypothesis (deferred xfv-phase2 A3/A4, never tested): for AA/AAA pitchers, the in-house
  aStuff+ (pitcher-level forward r 0.28) or the SC+ whiff component (X-C3: r 0.359 vs
  first-MLB ERA) adds OOS signal the production features miss.
- Gate (forward-chained, pitcher side only):
  1. OOS Spearman improves on the pitcher pool overall (delta >= +0.005).
  2. The upper-level (AA/AAA) pitcher sub-cohort improves (delta >= +0.010).
  3. No degradation of the lower-level pitcher cohort beyond -0.003 (missing-data
     handling must not poison rows without tracking data; coverage reported).
- Ship path: same expected-CHANGED discipline as E-LAMBDA.

## Wave 2 outcomes (2026-07-02): adversarial verify + eFV round

VERIFY (4 read-only lanes over 4525ec5..HEAD, 16 findings, no P0):
- P1 FIXED: the X-D2 owner-decision spec that four docs referenced did not exist in
  docs/archive/REVIEW_QUEUE.md; now item 11.
- P2 FIXED: C1 track-record panel deep link used /glossary/?view=... but the glossary app
  parses hash only; now #view=source-comparison.
- P2 FIXED: tools/leverage_consistency_eval.py hardcoded CURRENT_SEASON/MULTI_YEAR_SEASONS
  while run_monthly 6b4b runs it monthly forever; the 2027 season would have silently frozen
  the gmLI 3yr window. Seasons now derive from the leaderboards payload; gate math is
  unchanged (2018-2025 caches; verified identical after regen: rho 0.4683 / split 0.5294).
- P2 FIXED: X-C3 decision instrument sat on in-progress 2026 outcomes (irreproducible
  committed numbers). Decision now pinned to CLOSED outcome seasons. NOTE the pin flipped
  the rule to "reweight" (closed-basis blend gain +0.14 hit / +0.28 pit, n=23/side):
  recorded as a QUEUED candidate (docs/archive/REVIEW_QUEUE.md item 12), composite unchanged; a
  published-metric change needs its own pre-registered gate.
- P3s FIXED: gmLI pct cell now fInt-coerced; bullpen join count only counts rendering rows;
  glossary writers share one no-trailing-newline convention; leverage artifact writes
  atomically (tmp+replace); run_monthly regenerates the generated audit docs right after
  registry restamps (keeps test_generated_docs_in_sync green across monthly runs); the
  Upside strip gets an auto-fill grid (uneven 3+2 wrap); static pages' stale ?v=
  cache-busters fixed by a site rebuild in the close-out commit.
- P3s ACCEPTED/RECORDED, no code change: X-D1 pooled CI treats season-pairs as i.i.d.
  (cluster bootstrap suggested at next refresh; per-pair rhos all clear the bar anyway);
  X-ISO condition-1 wording pooled-vs-per-side ambiguity (E-ISO2's pre-registration states
  it explicitly); X-C3 prior wording implied both sides missed the 0.05 bar (hitters
  cleared it; pitcher side missed).
- CLARIFIED: data/timeseries.json is UNTRACKED by design (daily pipeline owns it); the
  golden fingerprint "CHANGED" verdicts on it reflect daily data, not code. All tracked
  golden artifacts match HEAD; wave-2 verifier rerun churn on ~50 tracked data files was
  git-restored.

eFV ROUND (3 gated experiments, gates pre-registered 2026-07-02, ALL NO-SHIP):
- E-ISO2 (grade-space monotone recal): REJECTED. Fixed X-ISO's tie-flattening (exact
  within-cell rank preservation) and doubled down on the calibration gain (tier-45 gap
  0.0946 -> 0.0156) but pooled Spearman -0.0115 vs -0.002 tolerance, entirely cross-cell,
  and the IDENTITY transform scores -0.0041 on the same metric: the tolerance is tighter
  than the eval's own noise floor. Any future attempt must first fix the rank metric in a
  new pre-registration. Loss ledger: data/xfv_grade_recal_eval.json.
- E-LAMBDA (per-cohort blend lambda): REJECTED on all 3 conditions; per-cohort argmax on
  25-160-row pools is noise-dominated (5/6 cohorts fold-unstable). Do not re-attempt
  without hierarchical shrinkage toward the global lambda. Loss ledger:
  data/xfv_cohort_lambda_eval.json.
- E-STUFF (AA/AAA pitcher tracking overlay): INCONCLUSIVE by the pre-registered
  insufficient-n rule (0 trainable rows: tracking starts 2023, scored cohorts end at debut
  2023); recorded as FAIL, hypothesis neither confirmed nor refuted; first trainable fold
  arrives with the 2024-cohort resolution. Loss ledger: data/xfv_pitcher_stuff_eval.json.
- Bottom line: eFV is at its trainable-data ceiling on ranking; the one real, measured
  improvement available (bucket-probability calibration) cannot ship under a rank gate
  whose tolerance sits below the eval's noise floor. Registry rows 45-47 record all three.

## Pre-registered experiment gates: review-queue round (written 2026-07-02, before any run)

Owner decisions 2026-07-02: fix the F-01 bands via simulated total quantiles (coverage-
gated, fallback = drop total bands); AgeRel+ stays parked; implement review-queue items
2/4/5/6/8/9/10; re-attempt the eFV bucket calibration under a redesigned production-
relevant gate. Standing discipline unchanged: seeded, forward-chained, clear pass or
loss ledger, registry row + eval artifact + freshness map for anything model-shaped.

### R-BAND: Simulated path-total quantile bands (F-01 remediation, review-queue item 7)
- Hypothesis: totals bands built as P10/P90 of simulated multi-year paths (per-year
  quantile curves + year-to-year dependence estimated from the realized proj_eval corpus)
  are calibrated, unlike the current sum-of-quantiles bands.
- Gate (ALL, seeded, holdout = cohorts never used to fit the dependence):
  1. Coverage: realized multi-year WAR totals fall inside the simulated P10-P90 band for
     75% to 85% of holdout players (target 80%).
  2. The simulated band is narrower than the summed band on average (sanity: the fix
     must tighten, not widen).
  3. Point estimates (warTotal) are byte-unchanged; only band fields move.
- Ship path on pass: re-export FA/Projections/player payloads with the new band fields
  under the SAME keys (frontends unchanged), update test_proj_export.py, close F-01.
  Expected-CHANGED tracked payloads: mlb_projections.json, fa_class*.json,
  mlb_player_detail.json (band fields only; documented in CHANGELOG).
- On fail: drop the summed total bands from display (owner-approved fallback).

### R-PARK: MiLB per-park factors (review-queue item 2)
- Hypothesis: Savant-minors (2023+) per-park aggregates support stable park factors that
  improve the college -> Single-A translation (its documented SOS/park gap).
- Gate: (1) per-park factors are stable (year-over-year correlation rho >= 0.50 on parks
  with adequate batted-ball n, reported with n); (2) adding the park adjustment to
  college_translation improves LOO MAE or interval coverage on the matched-pair set
  WITHOUT degrading the hitter K% r2 (the one strong component); (3) coverage of parks
  is reported honestly (untracked FSL/DSL parks excluded, not imputed).
- Ship path on pass: college_translation park adjustment + artifact + registry row.
  On fail/insufficient data: loss ledger, no ship.

### R-SHRINK: ERA-shrink value unification (review-queue item 6)
- Hypothesis: one shared ERA shrink pseudo-count can serve both K_IP=50 (display index)
  and NEED_ERA_SHRINK_IP=45 (PAL need gate) without degrading either objective.
- Gate: a single candidate value must beat or tie BOTH current values on their own
  objectives: (1) era_minus_level display stability (small-sample blowup count + split-
  half stability of the index) and (2) the PAL need-gate's demotion-board ordering vs the
  conversion-history labels. Ties broken toward keeping two values (the null).
- Expected outcome per the provenance notes: FAIL (they were tuned for different
  objectives); the experiment resolves the queue item either way.

### E-ISO3: eFV bucket-distribution calibration, production-relevant gate
- Successor to E-ISO2 (rejected). Redesign rationale, stated a priori: in production every
  player is scored by the SAME season's map, so cross-year map drift (the entire E-ISO2
  Spearman deficit) never manifests on any surface; and E-ISO2's per-tier tolerance
  (1e-4 absolute) was far tighter than tier-gap estimation noise. The board DOES rank
  hitters and pitchers together, so cross-side stability within a season is real and
  stays in the gate.
- Gate (ALL, forward-chained OOF on the X-ISO cohort splits, SEED=7):
  1. Pooled AND per-side AND per-bucket Brier/log-loss improve (no bucket materially
     worse on either side, stated per-side explicitly this time).
  2. Within-(side, year) rank preservation is EXACT (strict monotonicity in grade space).
  3. Cross-side, within-YEAR pooled Spearman delta >= -0.002 for every evaluation year
     (never pooled across years).
  4. Per-tier reliability: every tier at FV 45+ improves; no tier's gap worsens by more
     than 0.005 absolute (FV-35's E-ISO2 move was +0.0009).
- Ship path on pass: wire into efv_score.py; registry row update + eval artifact +
  freshness map; expected-CHANGED limited to xfv.json + trade_values.json + direct
  downstreams, every delta justified in CHANGELOG; reliability diagram on PROSPX gains
  the before/after view.
- On fail: final loss ledger; no further calibration attempts against this data vintage.

## Wave 3 outcomes (2026-07-02, review-queue round)

First eight-lane run landed two lanes (E-ISO3, farm snapshotting) before a session-limit
interruption; the resume landed five more; the entity-pages lane failed on a structured-
output error (not a data problem) and is deferred (additive static pages, not launch-
critical; docs/archive/REVIEW_QUEUE.md). Outcomes:

- R-BAND (F-01 remediation): gate FAIL, and the failure is more informative than expected.
  The simulated path-total band (Gaussian AR(1) copula, estimated dependence rho 0.345,
  SEED 20260702) covers only 0.41 of realized multi-year totals vs the 0.75-0.85 gate. Root
  cause: the INCUMBENT summed band already UNDER-covers (0.63, not over-covers), because
  25.9% of realized totals fall below its p10 path (league attrition: washouts realize ~0
  WAR, below a strictly-positive decayed p10). Coverage is monotone increasing in dependence,
  so no admissible narrowing reaches 0.75. The bands are MIS-CENTERED (too high), not too
  wide, so the "summing makes them too wide" framing of F-01 was incomplete. OWNER-APPROVED
  FALLBACK TAKEN: the total P10-P90 bands are dropped from the FA and Projections display
  (assets/fa.js, assets/projections.js); point estimates and the statistically-fine per-year
  bands stay. F-01 disposition: FIXED (bands removed). NEW review-queue item: recalibrate the
  per-year WAR quantile marginals to carry league-attrition zero mass (a proj_ml/Gate-1
  quantile-head change), after which a dependence-aware total band becomes worth revisiting.
  Loss ledger: data/total_band_eval.json, registry row war_total_band_calibration.
- R-PARK (item 2): INFEASIBLE, gate cannot run. The cached Savant-minors data is player-
  season aggregates with no venue dimension, and the Single-A statline target has no park
  join key; best-case venue attribution reaches ~18% of matched players and only 2026.
  No ship; college_translation unchanged. Prereq for any retry: a venue dimension on the
  minors ingest + a park key on the Single-A statlines. Loss ledger:
  data/milb_park_factors_eval.json, registry row milb_park_factors.
- R-SHRINK (item 6): FAIL to unify, as the provenance predicted. Across shared ERA-shrink
  candidates 35..65 the display objective is a monotone blowups/full-season-distortion
  tradeoff balanced at K_IP=50, and the PAL need-gate ordering is flat within a wide
  bootstrap CI on 36 labeled conversions. No single value beats both, so K_IP=50 and
  NEED_ERA_SHRINK_IP=45 STAY. Resolves item 6. Loss ledger:
  data/era_shrink_unification_eval.json, registry row era_shrink_unification.
- PROSPX gradeBlock + grade band (items 5 + 4): SHIPPED. Extracted one gradeBlock() helper
  and routed 5 duplicated grade-rendering sites through it, verified byte-identical via a
  py_mini_racer golden harness (0 non-band diffs across 72 renders); 6 further sites were
  intentionally left un-routed (each has a genuinely different fallback; routing them would
  drift output) and flagged. Added a grade-scale "Outcome band" to the player-detail hero,
  derived by inverting the published surplus_by_grade_mm anchor at the payload's surplus
  P10/P90 (reproduces xfv_grade to MAE 0.385, so a faithful re-expression on the grade axis,
  not fabrication), hidden for provisional/degenerate/ungraded rows, tooltip disambiguating
  outcome-distribution from scout disagreement. Copy gates pass.
- OVERSEAS (item 8): investigation only. VERDICT: the hitter wRC+ blocker has DISSOLVED for
  NPB (READY-TO-RUN) and is marginally ready for KBO; CPBL and Cuba stay BLOCKED (CPBL has
  zero MLB transitions; Cuba has no Serie Nacional wRC+ source plus a defection-gap problem).
  FanGraphs already publishes league+park-adjusted NPB/KBO/MLB wRC+ on one page and
  overseas_stats.py already parses it, so no league-context scrape is needed; the only new
  input is curating ~7-10 fg_player_ids (an owner-extendable ledger task). A ready-to-run
  gated refit is spec'd in docs/audit-2026-07/overseas-factors-recheck.md and queued
  (docs/archive/REVIEW_QUEUE.md). No code changed.

### Earlier partial-landing note (superseded by the outcomes above)

- E-ISO3: REJECTED (2 of 4 conditions), FINAL loss ledger for the bucket-calibration
  line against this data vintage (per the pre-registration). C2 (exact within-side-year
  rank preservation) and C4 (every FV45+ tier improves; FV-35 +0.0009) PASS; the large
  calibration gain is real (tier-45 gap 0.0946->0.0156, tier-55 0.1616->0.0436). But C1
  fails on a per-side materiality check the redesign added: the pitcher bench bucket is
  +1.4% rel worse (vs 1% tolerance); and C3 fails because cross-side within-YEAR Spearman
  flips sign by year (2020 +0.012 / 2021 -0.026 / 2022 +0.006 / 2023 -0.025), noise-
  dominated at n~300-550/year, and the 2021 identity delta (+0.014) confirms the recal
  itself churns cross-side interleaving there. Takeaway: a side-ASYMMETRIC grade map
  cannot ship because the board ranks the two sides together; any future attempt needs
  jointly-constrained side maps AND resolved 2024+ cohorts before re-registering. Line:
  X-ISO -> E-ISO2 -> E-ISO3, all rejected; eFV published numbers unchanged. Registry row
  xfv_grade_recal3 (deprecated). tools/efv_grade_recal3_lab.py, data/xfv_grade_recal3_eval.json.
- Farm-grade LETTER snapshotting (review-queue item 10): SHIPPED. New append-only
  farm_grade_history table + snapshot_farm_grades() in storage.py (mirrors
  snapshot_farm_ranks; captures the board-displayed 7y-window letter + numeric composite,
  self-heals, one row per org per day), wired as a never-aborts monthly step in
  run_monthly right after the farm-rank snapshot; one snapshot backfilled today (30 orgs,
  2026-07-02) so the letter history the farm_grades registry row needs for forward
  validation starts accruing immediately. test_farm_grade_history.py covers schema,
  letter-set alignment, append-only, same-day idempotence, self-heal.

## Pre-registered gate: E-ISO4 (written 2026-07-02, before the run)

Owner decision after E-ISO3: one more eFV bucket-calibration attempt, this time with a
JOINTLY-CONSTRAINED side-symmetric grade map so cross-side ranking is preserved by
construction (the one failure mode shared by X-ISO, E-ISO2, E-ISO3). All three prior
attempts fit each side's grade map independently, which churns the pooled cross-side
ranking the board relies on. E-ISO4 ties the two sides.

### E-ISO4: joint side-symmetric bucket-distribution recalibration
- Design constraint (the whole point): the RANKING grade is remapped by a SINGLE shared
  monotone function g(grade) applied identically to hitters and pitchers, so any two
  players in any side with grades a <= b satisfy g(a) <= g(b): pooled cross-side ranking
  is preserved exactly (condition 3 becomes 0 by construction). The candidate to test is
  whether a shared grade map (optionally with side-specific bucket-probability tables kept
  for display/surplus, but the SHARED map driving both the grade and the ranking) still
  delivers the calibration gain. Explore both formulations: (a) one shared grade->grade
  monotone recal with pooled calibration loss; (b) shared grade map + side-specific
  residual bucket tables that do NOT affect ranking order.
- Gate (ALL, forward-chained OOF on the X-ISO cohort splits, SEED=7):
  1. Pooled AND per-side AND per-bucket Brier/log-loss improve, no bucket materially worse
     on either side (>1% relative). This is the condition E-ISO3 failed (pit bench bucket).
  2. Within-(side,year) rank preservation EXACT.
  3. Cross-side within-YEAR pooled Spearman delta >= -0.002 for every evaluation year
     (should hold BY CONSTRUCTION under the shared-map design; measure it to confirm the
     implementation actually preserves order and there is no numerical leak).
  4. Per-tier reliability: every FV45+ tier improves; no tier worsens by more than 0.005.
- Ship path on pass: wire into efv_score.py; registry row + eval artifact + freshness map;
  expected-CHANGED limited to xfv.json + trade_values.json + downstreams, each delta
  justified in CHANGELOG; PROSPX reliability diagram gains before/after.
- On fail: this is the FINAL calibration attempt against this data vintage across all
  formulations (owner: one more attempt). Loss ledger; revisit only with 2024+ cohorts.

## E-ISO4 outcome (2026-07-02): the eFV calibration line is definitively closed

E-ISO4 FAILED (final loss ledger, data/xfv_grade_recal4_eval.json), and it is the most
informative of the four attempts because it isolated the true blocker. The joint
side-symmetric design WORKED at its stated job: one shared strictly-increasing grade map
applied to both sides made condition 3 (cross-side within-year Spearman) exactly 0.0 for
every eval year by construction, killing the ranking churn that failed X-ISO, E-ISO2 and
E-ISO3. But condition 1 still fails, and now we know WHY: the pitcher BENCH bucket gets
materially worse (formulation a +1.54% log-loss; formulation b added pit GOOD +3.7%, so
a per-side residual does not recover it). The FV45+ calibration gain is real and large
(pooled Brier 0.2466 to 0.1964; tier-45 gap 0.0946 to 0.0137) but NO grade-space monotone
map can fix that gap without pulling pitcher mid-grade probability mass toward bust. That
is a model-structural limit, not a ranking or gate-design artifact. Definitive close of
the bucket-calibration line (X-ISO -> E-ISO2 -> E-ISO3 -> E-ISO4, all rejected) against
this data vintage; eFV published numbers unchanged throughout. The path forward, recorded
for when it exists, needs resolved 2024+ cohorts AND a method operating below the
grade-monotone constraint (direct per-side bucket-structure recalibration). Registry row
xfv_grade_recal4 (deprecated), 52 rows.

## Follow-up program Wave B1: reliever-metric pre-registrations (2026-07-02)

Owner batch after Pass 3: overhaul REM+ so it is "not just a proxy for FIP", add a
separate reliever IMPACT metric, add a 3-year REM+, and yearly reliever history. Owner
design decision (recorded in memory pass3-followup-program-2026-07): REM+ stays a PURE
SKILL number with DEEPER skill inputs; leverage moves into a SEPARATE new impact metric,
preserving the validated two-number finding (leverage is a deployment/price layer, not
repeatable skill). Gates are pre-registered here BEFORE any candidate number is computed.
Incumbent baseline (data/rem_plus_eval.json): REM+ forward-chained Spearman vs RA9(Y+1)
= 0.2363 over 878 Y->Y+1 pairs, 7 seasons (2018-2025 ex-2020), beating raw FIP 0.211
(gap lo95 +0.0013), ERA 0.0901, raw WPA 0.1055. Split-half reliability only ~0.34 at
100-150 BF (single reliever seasons are noisy).

- **X-R1 - REM+ skill overhaul (SwStr-informed expected-K core).** Hypothesis: shrinking
  the K component toward a player-specific SwStr%-derived expected-K (SwStr% stabilizes
  ~50 pitches, faster than K% ~70 BF and BB% ~170 BF) is a better skill estimate than
  shrinking toward the pool mean, so REM+ becomes more than a one-year-FIP proxy and
  forward-predicts next-year run prevention better. bref SwStr% confirmed available for
  all backtest seasons (831-863 non-null rows/yr). GATE (ship-or-ledger, pre-registered):
  candidate REM+ forward-chained Spearman vs RA9(Y+1), same seasons + same MIN_TBF_Y=100 /
  MIN_TBF_NEXT=60 convention as the incumbent, must EXCEED 0.2363 with a seeded
  2000-resample bootstrap-CI gap (candidate minus incumbent) lo95 >= 0 AND a positive
  point estimate. Clear positive gap -> ship (rem_plus.py skill core changes, expected
  bullpen_leaderboards.json CHANGE with the delta documented, registry row updated, eval
  artifact, glossary + freshness map). Within-noise or negative -> KEEP the FIP core,
  loss ledger, review queue. All stochastic steps seeded.

- **X-R2 - 3-year REM+ (trailing-3-season talent estimate).** Hypothesis: an IP-weighted
  trailing-3-season REM+ is a more stable talent read than one season (split-half rho only
  ~0.34) and forward-predicts next-year RA9 better. GATE: 3yr REM+ through year Y forward
  Spearman vs RA9(Y+1), on the reliever set that HAS a 3yr value and a real Y+1 sample
  (TBF>=60), must EXCEED single-season REM+(Y) forward rho on the SAME player set, seeded
  bootstrap-CI gap lo95 >= 0. Clear positive gap -> ship a rem_plus_3yr companion display
  column (like gmli_3yr), joined into bullpen_leaderboards.json + proposed_values for the
  current pool. Marginal -> provisional-with-r; negative -> ledger.

- **X-R3 - RIV+ (Reliever Impact Value, realized-value index).** NEW additive column, NOT
  a change to REM+ published numbers, so the pre-registered checks are descriptive-validity
  not a forward-skill ship gate. RIV+ = a 100-anchored index of realized leverage-weighted
  value (context wins added: WPA, plus leverage-weighted shutdowns-minus-meltdowns),
  DISCLOSED as a deployment/value metric that by design is NOT a repeatable-skill number.
  Pre-registered honesty checks (reported in the eval, ship regardless as a labeled Impact
  descriptor since it is a realized-value measure not a prediction): (1) RIV+ aligns with
  what teams pay RP free agents at least as well as REM+ does (rho vs RP AAV >= REM+'s),
  showing it captures deployed value; (2) RIV+ is materially LESS forward-stable Y->Y+1
  than REM+, CONFIRMING the two-number design. If RIV+ turned out MORE forward-stable than
  REM+, that would overturn the leverage-isn't-skill thesis and force a rethink before any
  ship. Registry row + glossary + freshness map required either way.

## Follow-up program Wave B2: starter-metric pre-registrations (2026-07-03)

Owner ask: a new Starter Leaderboards section on /mlbstats/ with SEM+ (Starter Evaluation
Metric+) and a 3-year SEM+, mirroring the reliever board. Recon: StatsAPI season pitching
carries every FIP input + durability (gamesStarted, inningsPitched, completeGames) and a
batted-ball signal (groundOutsToAirouts), but NOT quality starts or times-through-order
(those need game logs / a feed the pipeline does not have). So SEM+ is the starter analog
of REM+: a starter-pool-anchored empirical-Bayes-shrunk FIP (100 = average qualified
starter), pure run-prevention skill, with durability (IP, GS, average start length) shown
as CONTEXT, never folded into the skill number unless a gate proves it predicts forward.
Starters are not leverage-deployed, so there is no leverage walk and no starter RIV+. Gates
pre-registered here before any number was computed; harness tools/sem_plus_lab.py; seed
20260703; same forward-chained convention as REM+ (Y qualified, RA9 in Y+1).

- **X-S1 - SEM+ skill validation.** SEM+ = starter-pool EB-shrunk FIP. GATE (ship): SEM+
  forward-chained Spearman vs RA9(Y+1) BEATS ERA (the naive baseline) with a seeded
  bootstrap-CI gap lo95 > 0, AND is not worse than its raw-FIP parent (gap lo95 >= -0.01).
  Clear pass -> ship SEM+ as a validated starter run-prevention index; else provisional
  with the r published. Starter pool = primarily-starting pitchers (GS/G >= 0.5) with a
  real sample; qualification pre-set at IP >= 40 provisional, the season leaderboard bar
  (~1 IP per team game) for qualified.

- **X-S2 - 3-year SEM+.** IP-weighted trailing-3-season SEM+. GATE: 3yr SEM+ forward rho vs
  RA9(Y+1) on arms with a 3yr value EXCEEDS single-season SEM+ on the same set, seeded
  bootstrap-CI gap lo95 >= 0. Clear positive -> ship a sem_plus_3yr companion column;
  marginal -> provisional-with-r; negative -> ledger. (Starters have larger single-season
  samples than relievers, so the 3-year stability gain may be smaller; report honestly.)

- **X-S3 (informative, optional) - "more than FIP" for starters.** Does a batted-ball
  (groundOutsToAirouts) adjustment to the HR expectation improve SEM+ forward prediction
  over plain FIP? Ship the adjusted core ONLY if it beats plain FIP forward with a
  bootstrap gap lo95 >= 0; otherwise keep plain FIP and record the loss ledger (the
  reliever SwStr analog X-R1 was rejected, so the prior is skeptical).

## Changelog of findings in this pass

- 2026-07-03 (follow-up Wave B3, DEFERRED with specs): the two remaining owner-batch model
  experiments both change PUBLISHED numbers and cannot be responsibly shipped in the 8-day
  pre-launch window, so they are queued with concrete specs rather than rushed. (a) Overseas
  translated stats -> eFV features (the Yamamoto low-eFV concern): would change data/xfv.json
  (a GOLDEN artifact held byte-neutral all pass) for overseas prospects, but the graduated-
  overseas-with-outcome cohort is ~10 (the overseas translation cohort is 28 resolved NPB/KBO
  transitions total), far too thin for the per-side, no-degradation, bootstrap-CI rigor the
  four prior eFV experiments were held to; the eFV calibration line is already closed at the
  trainable-data ceiling. docs/archive/REVIEW_QUEUE.md item 15, with the method + the zero-risk interim
  (surface the validated MLB-equivalent line as card CONTEXT without moving eFV). (b) Per-year
  WAR quantile marginal recalibration is docs/archive/REVIEW_QUEUE.md item 13, already spec'd (attrition zero-
  mass, gate coverage [0.75,0.85]); it is high-blast-radius on published /projections/ + /fa/
  bands and its total-band sibling was already shown miscalibrated and dropped, so it stays
  deferred rather than shipped unvalidated pre-launch. Both respect the standing rule: gate
  every model change; never ship an unvalidated published-number change, least of all a golden
  artifact, days before Beta.
- 2026-07-03 (follow-up Wave B2, starter metrics): the three pre-registered starter gates
  ran (harness tools/sem_plus_lab.py; seed 20260703; StatsAPI season pitching, no leverage
  walk). RESULTS:
  * X-S1 SEM+ VALIDATED and shipped. Forward-chained OOS (702 Y->Y+1 pairs, 2018-2025
    ex-2020): SEM+ predicts next-year RA9 at rho 0.3923 vs raw FIP 0.358, ERA 0.2612;
    bootstrap CI on the gap beats ERA (lo95 +0.081) and edges raw FIP (lo95 +0.019).
    Forward predictiveness is much higher than REM+ (0.24) because starters carry larger,
    more stable single-season samples. data/sem_plus_eval.json, registry sem_plus
    (validated). New surface: /mlbstats/ Starter Leaderboards.
  * X-S3 "more than FIP" (ground-ball-adjusted HR expectation) REJECTED. Candidate 0.3905
    vs plain 0.3923, gap lo95 -0.0086. Plain FIP stays (starter samples are large enough
    that observed HR rate is already a strong estimate). Loss ledger inside sem_plus_eval.
    Consistent with the reliever SwStr rejection (X-R1): peripheral priors do not beat
    sample-shrunk FIP for full-season pitcher samples.
  * X-S2 3-year SEM+ MARGINAL -> shipped PROVISIONAL. 3yr 0.4141 vs 1yr 0.3922 same-set
    (+0.022, a larger gain than the reliever 3yr case), gap CI includes 0 (lo95 -0.0257).
    Per the pre-registered rule ships provisional with the r published; value is stability.
    data/sem_plus_multiyear_eval.json, registry sem_plus_3yr (provisional), joined by
    starter_export._join_sem_plus_3yr.
  Also shipped: data/starter_history.json (per-season qualified boards 2021-2025); new
  modules sem_plus.py (reuses the rem_plus FIP machinery) + starter_export.py; run_monthly
  steps 6b4e (starter lab) + 6b4f (starter export/history); build_site adds the Starter
  Leaderboards section; registry 57 rows; glossary +2 (sem_plus, sem_plus_3yr).
- 2026-07-02 (follow-up Wave B1, reliever metrics): the three pre-registered gates ran on
  the forward-chained pool (2018-2025 ex-2020; leverage from the warm winProbability cache;
  seed 20260702; harness tools/rem_plus_lab.py). RESULTS:
  * X-R1 REM+ SwStr overhaul FAILED its gate (NO SHIP, loss ledger data/rem_plus_swstr_eval
    .json). Candidate SwStr-xK skill core forward rho 0.2277 vs incumbent FIP core 0.2246
    on 1036 pairs; bootstrap gap lo95 -0.0066 (< 0), a wash within noise. The incumbent
    already regresses K% by sample; at reliever volumes observed K% is a strong enough K
    estimate that a SwStr prior adds no forward signal. The FIP-based REM+ skill core stays
    unchanged; REM+ published numbers unchanged. Registry row rem_plus_swstr (deprecated).
  * X-R2 3-year REM+ MARGINAL -> shipped PROVISIONAL. 3yr forward rho 0.2366 vs 1yr 0.2316
    on the same 668 arms; point estimate favors 3yr but the same-set bootstrap gap CI
    includes 0 (lo95 -0.043). Per the pre-registered rule (marginal -> provisional-with-r)
    it ships as a companion display column (value is stability, not sharper prediction:
    single reliever seasons split-half only ~0.34). data/rem_plus_multiyear_eval.json,
    registry row rem_plus_3yr (provisional), joined by bullpen_export._join_rem_plus_3yr.
  * X-R3 RIV+ BOTH checks PASSED -> shipped. RIV+ is materially less forward-stable than
    REM+ (Y->Y+1 rho 0.209 vs 0.352, confirming the two-number design) and aligns with RP
    AAV better than REM+ (0.576 vs 0.508, 271 signings). Computed live in
    rem_plus.score_riv_plus; data/riv_plus_eval.json, registry row riv_plus (provisional).
  Also shipped: data/bullpen_history.json (per-season qualified boards 2021-2025 for the
  /mlbstats/ yearly history tabs); run_monthly steps 6b4c (reliever lab) + 6b4d (history).
  Registry now 55 rows; glossary +2 entries (riv_plus, rem_plus_3yr). The owner's "make
  REM+ more than a FIP proxy" ask was tested directly (X-R1) and honestly rejected; the
  richer picture comes from the NEW metrics (3yr REM+ stability + RIV+ realized impact),
  not a changed skill core.
- 2026-07-01: ledger created; F-01..F-09 recorded; X-ISO/X-D1/X-D2 gates pre-registered.
- 2026-07-01 (wave 1): X-ISO failed gate (no ship, loss ledger); X-D5 and X-C3 artifacts
  shipped; lanes B and H2 landed. Lanes G, H1, P and experiments X-D1, X-D2 pending re-run
  (session-limit interruption).
- 2026-07-02 (wave 1b): X-D1 gmLI leverage-consistency PASSED its gate cleanly (pooled
  Y->Y+1 rho 0.4683, bootstrap CI floor 0.412 vs the 0.30 bar; split-half 0.5294; ships
  as deployment context, wiring follows). X-D2 AgeRel+ met the numeric bar on its face
  (pooled r 0.1237 n=369) but is NOT a clear pass: the strict pre-registered no-blowups
  screen failed (17 pitcher ERA tails) and the pass reading relies on parity instruments
  formalized after inspecting the failure; the plain level-relative comparator
  out-predicts it (r 0.1559 vs 0.1237); upper-level same-age cohorts are promoted elites
  (selection confound in display semantics). Per the ship policy: NOT WIRED, owner
  decision queued in docs/archive/REVIEW_QUEUE.md. Lane H1 landed F-02 (visible error states + retry
  in all six module apps) and F-08 (REM+/Bullpen+ explainers) plus per-year P90 upside
  and eFV-primary grade language on projections/#cmp. Lane P landed D4 (surplus $ band),
  B3 (GFX follows rank mode), C1 (track-record panel), C2 (reliability diagram of the
  shipped distribution). F-02/F-08 dispositions: FIXED. Full battery green: 1,714 passed
  / 17 skipped, copy gates clean, p3-base vs p3-wave1b IDENTICAL.
- 2026-07-01 (wave 2, lane G): audit deliverables landed. MODEL_REGISTRY.md /
  SITE_MAP.md / DATA_SOURCES.md are GENERATED (tools/gen_audit_docs.py, drift-guarded
  by test_generated_docs_in_sync.py; DATA_SOURCES.md carries a verbatim-round-tripped
  CURATED block); CHANGELOG.md / docs/archive/REVIEW_QUEUE.md / docs/archive/BETA_READINESS.md are curated.
  Registry at generation time: 42 rows (17 validated / 21 provisional / 3 unvalidated /
  1 deprecated), validate() clean. F-01 spec'd in docs/archive/REVIEW_QUEUE.md item 7. NOTE: rerun
  tools/gen_audit_docs.py after ALL lanes land (SITE_MAP/DATA_SOURCES introspect live
  source, so sibling-lane edits will show as expected drift).
