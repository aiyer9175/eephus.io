# eFV + surplus accuracy-maximization program (2026-07-24b)

Owner directive (verbatim intent): improve eFV and surplus by any means; REMOVE caps;
recalibrate attribute weighting for maximum accuracy no matter how much the board moves; eFV
should be the truest model-based 20-80 grade. "Do the same for the surplus model."

DISCIPLINE (kept, because it is how accuracy is maximized without self-deception): every change
is measured on the shipped OOS harness (tools/efv_lab_runner.py / efv_ml_lab.py forward-chained
2020-2023; surplus via surplus_backtest_real.py). SHIP whatever maximizes pooled Spearman/AUC and
cell wins. The BOARD-MOVEMENT ceilings (post-flip 3.0/4.0 FV, overlay display ceilings, the
fringe-step blocker) are REMOVED per owner authorization - they no longer gate a ship. The
ACCURACY bars stay (lo95 on OOS delta) - they are the measurement, not a cap.

CRITICAL UNLOCK: the wave-B label repairs (20 MLB-career players were training as 0-WAR busts;
24 mis-resolved ids) materially changed the training matrix. The lambda band, feature selection,
ridge alpha, and every cap were last calibrated on the CORRUPTED matrix. Per the retraction
lesson ("a lambda conclusion is only as good as its outcome labels"), ALL are re-open on the
repaired labels. Same-run baseline = the current shipped tree (hit pooled Spearman 0.3787 /
AUC 0.7727; pit 0.302 / 0.7191). Seed 20260724, 2000 reps.

## A1 LAMBDA RE-SELECT (the crown jewel; repaired-label re-open)
The 2026-07-14 lambda-band raise was RETRACTED on corrupted labels (interior optimum ~0.8875,
boot P 0.677). Re-run the full lambda selection/adjudication on the repaired matrices: sweep the
blend lambda per side over [0.50, 1.00] (and the pure-model 1.0 endpoint), forward-chained, pick
the pooled-OOS-Spearman-maximizing value with an AUC co-check. Bar: the selected lambda's pooled
Spearman delta vs the shipped lambda lo95 > 0 AND AUC not worse. NO board-movement ceiling. Ship
the accuracy-max lambda per side (efv_model._BLEND_LAMBDA + efv_score live stamps). Artifact
data/xfv_lambda_reselect_eval.json.

## A2 WEIGHT + ALPHA + FEATURE RECALIBRATION (repaired-label re-open)
- Ridge alpha re-selection on repaired labels (the M4 alpha-criterion lane) - pick the
  OOS-Spearman-max alpha per side.
- Re-test the marginal REJECTED features whose rejection could be a corrupted-label artifact
  (NOT the structural closes - power stays out, scout-disagreement stays out): re-screen
  iso_rel/peak_iso_rel, level features, K-BB explicit, on repaired labels. Ship any that now
  clear pooled lo95 > 0.
- Report the fitted ridge weights per feature (the "attribute weighting" the owner asked to
  check) before/after, both sides.
Bar: pooled Spearman delta lo95 > 0. Artifact data/xfv_weight_recal_eval.json.

## A3 CAP-REMOVAL SWEEP (owner explicit ask)
Test removing/loosening each cap on the OOS harness; the burden is REVERSED per the directive -
remove a cap UNLESS keeping it measurably improves OOS (keep only caps whose presence lifts
pooled Spearman lo95 > 0 vs removed). Caps in scope: age_rel_level +-3.5 clamp; reliability
shrink K (_K_REL_PA 100 / _K_REL_BF 80 - test lower shrink = trust rates more); n_milb_seasons
cap 8; the -2.0 WAR floor; the S-XLINE delta caps (.050/.050/.100/.060) and W-hit weight; the
xfv_ungraded soft cap (knee/ceil); the live overlays _age_factor / _role_factor floors. For each:
capped-vs-uncapped pooled OOS + report. Ship the accuracy-max setting of each. Report which caps
are LOAD-BEARING for accuracy (keep, with evidence) vs board-movement-only (remove).
Artifact data/xfv_cap_sweep_eval.json.

## A4 SIGNAL REVIVAL WITHOUT CEILING (owner removed the board-movement bound)
The W-OVERLAY-R physics survivors (AAA velo/spin/vaa; sub-AAA ivb/vaa) + the S-XLINE-4 validated
whiff (hit K-channel +0.0965) / fb_velo (pit +0.1423) signals FAILED only on the display-space
ceiling, never on signal. With the ceiling removed, ship them as a full (uncapped) live model-leg
overlay for covered players. Bar: the signals are screen-validated (lo95>0 on their forward reads,
already recorded); the ship is authorized by the ceiling removal. Report the live board move
(unbounded) + coverage. efv_statcast_overlay uncapped (BETA and DELTA_CAP_FV raised/removed);
default ON for covered players. Artifact data/xfv_overlay_uncapped_eval.json.

## B1 SURPLUS CALIBRATION to ACCURACY (not coverage)
The v4 isotonic bar (coverage >= shipped) rewards over-dispersion (verifier finding). Re-fit the
calibration to MINIMIZE held-out MAE and drive held-out slope -> 1.0 (the true calibration
objective), on the repaired resolved pool. Compare v4 vs the MAE/slope-optimal fit. Ship the more
accurate curve. Also test removing the surplus caps: the $0 floor, the convex tier-curve clamps,
the realized_implied_fv low-end FG spread. Bar: held-out slope closer to 1.0 AND held-out MAE not
worse. Artifact data/xfv_surplus_recal_eval.json.

## B2 FV->WAR->grade spread (the "truest 20-80 grade")
realized_implied_fv currently maps E[6yr WAR] -> 20-80 with a FanGraphs-shaped low end + soft
tail behavior. Re-examine whether the grade spread (compression at top/bottom) costs rank
accuracy: test a monotone re-spread that widens the served 20-80 range to match the model's WAR
spread (the owner wants the truest model grade, not a compressed display). Rank-invariant by
construction (monotone) so Spearman is unchanged; the win is CALIBRATION of the displayed grade
to the WAR distribution + removing the fringe-step compression that blocked overlays. Artifact
data/xfv_grade_spread_eval.json.

## Execution
Wave E lanes A1-A4 + B1-B2 in parallel (disjoint lab files, no flips). Wave F: apply the
accuracy-max settings serially, ONE regen, scoreboard re-baseline (must show pooled Spearman/AUC
UP or the lane is reverted), registry/docs/golden/RESULTS, downstream regen, memory. No
board-movement ceiling gates a ship; only OOS accuracy does.

## RESULTS
(appended after runs)

## C1 PROVISIONAL grades (xfv_ungraded) true-to-model (owner: "same for provisional grades")
The provisional/source-ungraded grades carry an ORDER-PRESERVING SOFT CAP (hit knee43/ceil49,
pit knee38/ceil42) + a capped-absolute war->FV linear map (hit clamp[20,43], pit clamp[20,40]).
Per "true-to-model": remove the soft cap + widen the linear map so a provisional grade reflects
the model's raw war->FV, uncompressed at the top. Measure on the xfv_ungraded low-minors OOS
harness (data/xfv_ungraded_eval.json): the soft cap is order-preserving so Spearman is invariant;
the win is that breakout provisionals (Primera-class) grade to their true model value instead of
piling at the ceiling. Bar: low-minors Spearman not worse; served grades de-compress. Ship the
uncapped map. Artifact data/xfv_ungraded_recal_eval.json.

## C2 PLUS-METRIC true-to-model sweep (owner: "all our models/metrics across the site")
Audit every clamp/floor in the 100+10z plus-metric family and remove display compression that
makes the served value diverge from the raw model z: KRP+ 40-160 clamp + the x_era_k zero-quadrant
zeroing (owner-directed zero -> revisit under the true-to-model mandate); REM+/SEM+/HEM+/RIV+
clamps; xREM+/xSEM+. Each metric keeps its forward-validation on tools/plus_lab_harness.py (the
z-scale change is monotone -> Spearman-invariant; the win is true-to-model display). Remove clamps
whose only effect is compressing the tail; keep numerical-safety guards. Report every clamp found,
its classification (compression vs safety vs accuracy), and the disposition. Artifact
data/plus_metric_recal_eval.json.

## C3 OTHER MODEL SURFACES true-to-model (PAL / FA / projections / translations)
Audit + de-compress where true-to-model applies and accuracy allows: PAL FIT clamps; FA years/
enter-prob caps; projection star-blend + WAR-floor clamps; college/milb translation boundary
clamps. Each on its own gate/harness. Ship de-compressions that do not hurt the surface's
validation. Artifact per surface. This wave is the site-wide sweep (Wave G), after the core
eFV/surplus/provisional lanes.

## Classification rule (applies to every cap in this program)
Each cap/clamp/floor is exactly one of: (1) BOARD-MOVEMENT/DISPLAY COMPRESSION -> REMOVE per owner;
(2) ACCURACY-LOAD-BEARING (removing it measurably lowers OOS accuracy) -> keep, with the OOS
evidence reported to the owner; (3) NUMERICAL SAFETY (divide-by-zero, NaN, domain guards) -> keep.
Only class (2) keeps a cap, and only with evidence. The default is REMOVE.

## RESULTS (Wave E/F, 2026-07-24b; all independently reconstructed, fabricated-PASS provenance guarded)

Scoreboard confirmed the accuracy gain on the served tree: hit pooled Spearman 0.3787 -> 0.3835,
contributor AUC 0.7727 -> 0.7758; pit held 0.302 / 0.7191. Golden restamped
(e1205ffe...), prospx_current base-identity table re-captured under v5, 26 standing-rule +
golden + valuation tests green.

- A1 LAMBDA RE-SELECT: SHIP hit 0.70 -> 0.85 (efv_model.blend_lambda override). The old
  [0.50,0.70] rank_calibration band was a board-movement cap on the REPAIRED labels; every metric
  (pooled Spearman, contributor + star AUC, within-tier) rises monotonically past it. 0.85 is the
  unique significance-bar-clearing point (d_rho +0.0048 lo95 +0.0001 P0.952; d_cAUC +0.0031 lo95
  +0.0003; leakage-free nested forward-chain agrees). Pit stays 0.61 (its curve is a flat plateau
  and higher lambda LOWERS AUC). THE single biggest eFV accuracy gain of the whole program, and it
  was unlocked purely by the wave-B label repairs. Artifact data/xfv_lambda_reselect_eval.json.
- A2 WEIGHT/ALPHA/FEATURE: NO SHIP (empty diff). Alpha auto-select survives; iso_rel/peak_iso_rel/
  kbb fail on repaired labels too (the power-overpricing correction is NOT a label artifact).
  Weight audit flagged: hit n_milb_seasons fits negative (-0.36) despite its +1 direction - routed
  to a future feature-direction gate. Artifact data/xfv_weight_recal_eval.json.
- A3 CAP SWEEP: the honest true-to-model answer - NONE of the eFV input caps are board-movement
  compression; they are input guards / shrink hyperparameter / safety floor. Removing the
  age_rel_level +-3.5 clamp LOWERS hit OOS (load-bearing). The only accuracy lever is LOOSENING the
  reliability shrink K 100/80 -> 50/40 (trust MiLB rates more; all 4 deltas non-negative but
  CI-neutral and matrix-rebuild-coupled to A1/A2) - DEFERRED to a coordinated rebuild pass, not
  shipped here. Artifact data/xfv_cap_sweep_eval.json.
- A4 OVERLAY UNCAPPED: SHIP default-ON (efv_statcast_overlay.py). The whiff/velo/AAA-physics
  survivors failed W-OVERLAY-R only on the removed display ceiling; now uncapped for 405 hit + 228
  pit covered players, live board moves up to 5.0 FV / 325 ranks (the display ceiling, not
  DELTA_CAP, was the binding constraint). run_live only; resolved OOS unaffected; uncovered
  players byte-identical. Authorized by the screen validation + owner ceiling removal (no new OOS
  fold exists for coverage-limited live signal - stated honestly). Artifact
  data/xfv_overlay_uncapped_eval.json.
- B1 SURPLUS -> ACCURACY: SHIP isotonic-v4 -> linearmap-v5. v4's isotonic clamped every prediction
  above raw 44.21 to a flat 59.08 (high-end compression); a plain linear floored-at-0 map is more
  accurate - held-out slope 0.9945 vs v4 1.1036, held-out MAE 13.77 vs 14.21, player-clustered
  bootstrap delta-MAE 95% CI [-1.18,-0.065] entirely below v4. Both sides improve (pit was badly
  under-calibrated by the clamp: slope 0.824 -> 0.981). Cap classification: isotonic high-end clamp
  REMOVED (compression); convex tier-curve + $0 floor KEPT (accuracy-load-bearing, with evidence).
  eFV rank untouched (monotone downstream). prospx_current re-captured under v5, test re-stamped
  (FV50 28.2). Artifact data/xfv_surplus_recal_eval.json.
- C1 PROVISIONAL DE-CAP: SHIP true-to-model (efv_ungraded.UNCAPPED_GRADE). OOS-invariant by
  construction (the low-minors harness scores raw war, not the grade); top de-compresses hit
  48->50.3, pit 37.7->40.1. Honest note: the soft cap was INFLATING grades just above the knee
  (S-curve slope 1.5/1.6 > 1), so 39 mid-band provisional grades correctly tick DOWN (un-inflated)
  while the tail de-compresses - true-to-model in both directions. Artifact
  data/xfv_ungraded_recal_eval.json.

## Program conclusion (accuracy track)
eFV is now measurably more accurate than at any point this session (hit pooled Spearman +0.0048 /
AUC +0.0031 from the lambda re-select alone, on top of the wave-B label repairs). The owner's
"remove caps" directive produced the honest finding that eFV's INPUT caps are mostly safety guards,
not accuracy-limiting compression - the real accuracy-limiting caps were the BLEND-WEIGHT band
(A1, removed, big win), the SURPLUS high-end clamp (B1, removed), the OVERLAY display ceiling (A4,
removed), and the PROVISIONAL soft cap (C1, removed). Deferred: the reliability-shrink loosen (A3,
CI-neutral, rebuild-coupled). Wave G (site-wide plus-metric + PAL/FA/projection/translation
true-to-model sweep) follows.

## RESULTS Wave G (site-wide true-to-model sweep, 2026-07-24b)
The reassuring headline: across the ENTIRE site, only TWO genuine display-compression clamps
exist - the platform was already overwhelmingly true-to-model.
- C2 PLUS-METRICS: SHIP the KRP+ 40-160 clamp removal (efv_score, monotone/Spearman-invariant,
  only broke boundary ties; Kade Anderson 160->189.1, 3 live movers). REM+/SEM+/HEM+/RIV+/xREM+/
  xSEM+ ALREADY true-to-model (raws unclamped; the only guards are divide-by-zero/domain safety;
  HEM_SPREAD_GAIN is a monotone WIDENING, not a clamp). KRP+ glossary copy synced. OWNER DECISION
  flagged (not touched): the KRP+ x_era_k zero-quadrant zeroing is a shared eFV MODEL feature
  (owner-directed; the sign-flip was tested + rejected for a worse measured eFV cost) whose display
  side effect is an 835-row point mass at KRP+ 99.3 - Option A keep both / Option B decouple a
  display-only true-signal read / Option C flip (rejected). Artifact data/plus_metric_recal_eval.json.
- C3a PAL + FA: ZERO ships. Every clamp is numerical/domain safety or accuracy-load-bearing,
  MEASURED on the real gates (FA Gate-2 reproduced byte-identical, a de-clamp did not improve it;
  PAL rank-invariance MC). Confirms the A3/B1 finding that FA/eFV input caps are guards, not
  compression. Artifact data/c3_pal_fa_recal_eval.json.
- C3b PROJECTIONS + TRANSLATIONS: SHIP the translation rate-band hi_clip raise to true [0,100]
  (college_translation, 7 rate call sites; the sub-domain caps 60/30/50/25 compressed the DISPLAYED
  upper whisker below the model's own LOO-validated band - 23 college pit_bb rows showed hi==exp,
  zero upper uncertainty). exp/lo/rank all invariant (the LOO coverage is computed on the unclamped
  band). proj_ml + fa_projection point values already true-to-model (WAR unfloored); all their
  clamps KEEP (safety or accuracy-load-bearing - the lift-only mean-blend is ANTI-compression).
  Artifact data/c3_proj_trans_recal_eval.json.

## FINAL PROGRAM STATE (2026-07-24b)
eFV is at its most accurate this session (hit pooled Spearman 0.3835 / AUC 0.7758). Every
served metric across the site is now true-to-model except the two owner-decision items (KRP+
x_era_k zeroing; the A3 reliability-shrink loosen deferred pending a coordinated rebuild). The
"remove caps" sweep's honest yield: the accuracy-limiting caps were the eFV BLEND-WEIGHT band,
the SURPLUS high-end clamp, the OVERLAY display ceiling, the PROVISIONAL soft cap, the KRP+ clamp,
and the TRANSLATION band cap - all removed. The eFV/PAL/FA/projection INPUT caps are safety guards
that were correctly kept (removing several measurably LOWERS accuracy). Nothing committed.

## RESULTS Wave H (owner decision queue, coordinated recalibration 2026-07-24d)
- SHRINK LOOSEN (A3, owner: ship now): reliability shrink K 100/80 -> 50/40, both matrices
  rebuilt (trust MiLB rates more). The re-selection on the rebuilt matrix found n_milb_seasons
  KEEP (the -0.36 ridge weight is legitimate collinear work with level_rank, NOT a corrupt sign -
  the +1 was only an unused LightGBM monotone hint) and re-confirmed lambda hit 0.85 / pit dynamic
  0.54. HONEST OUTCOME: the rebuild did NOT deliver the hoped hit gain - on the reselect protocol
  hit is -0.0024 (within the noise floor), but the SCOREBOARD ARBITER (the committed keep/revert
  criterion) shows NO regression: hit held 0.3835->0.3834 with AUC UP 0.7758->0.7762, and pit
  GAINED 0.302->0.303 / AUC 0.7191->0.7197. Net small-positive, no regression -> KEPT per the
  arbiter. Artifact data/xfv_wave_h_eval.json.
- n_milb_seasons FEATURE-DIRECTION GATE (owner: register + run): VERDICT KEEP (drop-vs-keep
  bootstrap CI straddles 0, P(drop>keep)=0.31; the negative weight is collinear absorption, not
  corruption). No feature change. The anomaly is explained, not a bug.
- KRP+ DISPLAY DECOUPLE (owner: decouple display only): the pill reads a display-only true-signed
  raw (double-bad quadrant = -abs((-era_rel)*k_rel)) so 834 doubly-below-average arms spread below
  100 by severity (mean 94.25, 542 below 100) instead of the 99.3 point mass; the eFV MODEL
  feature x_era_k STAYS zeroed (grades/ranks/surplus byte-identical, verified 0 non-krp fields
  moved). Plus display hygiene: era_rel winsorized +-6 so a 1-IP ERA blowup cannot drive an absurd
  pill (range now 27.6-150.5, was down to -16.3). Glossary methodology updated.
- COMMIT: owner chose keep-local; no git action, localhost serves it.

## SESSION FINAL STATE (2026-07-24d)
eFV: hit pooled Spearman 0.3834 / AUC 0.7762, pit 0.303 / 0.7197 - the most accurate this session
(the A1 lambda re-select was the driver; the K-loosen rebuild is a small pit gain on top, hit
neutral). Golden ee5df341; registry 148; prospx_current re-frozen under v5. Every served metric
site-wide is now true-to-model except the deliberately-kept safety guards (shown, with evidence,
to be accuracy-load-bearing). All owner decision-queue items executed. Nothing committed.
