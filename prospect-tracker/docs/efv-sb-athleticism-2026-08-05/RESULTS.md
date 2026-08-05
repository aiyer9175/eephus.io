# Results: eFV stolen-base driver (B4) + athleticism blend (B5)

Date: 2026-08-05. Pre-registration: PREREG.md in this directory (written before
any run; nothing in it was relaxed). Raw artifact: results.json (seed 20260805).
Driver: run_lab.py. Matrix vintage: the committed data/xfv_hitter_matrix.json
(NOT rebuilt; byte-identical this wave). Baseline = the served hitter feature
set on the shipped forward-chained protocol, lambda 0.70, target_censored,
pooled n = 353 OOS rows over folds 2020-2023.

## Verdict, one line each

| variant | added column | pooled rho | margin | x MDE floor (0.017) | MAE margin | fold rho wins | zero-info control margin | verdict |
|---|---|---|---|---|---|---|---|---|
| baseline | (none) | 0.3882 | | | (MAE 3.9339) | | | |
| b4_sb | sb_rate_rel | 0.3958 | +0.0076 | 0.45x | +0.0064 | 2/4 | -0.0007 | NO-SHIP (sub-floor null) |
| b4_blend50 | 0.5 z(speed) + 0.5 z(sb) | 0.3950 | +0.0068 | 0.40x | +0.0069 | 3/4 | -0.0033 | NO-SHIP (sub-floor null) |
| b4_blend70 | 0.7 z(speed) + 0.3 z(sb) | 0.3932 | +0.0050 | 0.29x | +0.0062 | 2/4 | -0.0053 | NO-SHIP (sub-floor null) |
| b5_athl3 | mean-z {speed, field, throw} | 0.3863 | -0.0019 | -0.11x | -0.0265 | 2/4 | -0.0016 | NO-SHIP (negative) |
| b5_sf | mean-z {speed, field} | 0.3855 | -0.0027 | -0.16x | -0.0294 | 1/4 | +0.0019 | NO-SHIP (negative) |
| b5_st | mean-z {speed, throw} | 0.3903 | +0.0021 | 0.12x | +0.0039 | 2/4 | -0.0021 | NO-SHIP (noise) |

No variant clears the pre-registered gate. NOTHING here is ship-eligible, so
nothing touches the served model, and the no-serve stop clause was never
reached.

## B4: stolen-base driver, the honest reading

The three SB arms are the only variants that move BOTH gate metrics in the
right direction, and every one is decisively sub-floor:

- b4_sb is the strongest thing measured in this run: pooled rho +0.0076
  (0.45x the 0.017 hitter MDE95), pooled MAE 3.9339 -> 3.9275, KM-weighted MAE
  also improves (3.9084 -> 3.9051), within-tier 0.2349 -> 0.2468, t45 0.2777 ->
  0.3018, and its zero-information control is genuinely dead (-0.0007, i.e. the
  margin is NOT reproduced by a destroyed-information column, unlike the
  hit-age case where the control ate 93% of the candidate). But it wins only
  2 of 4 folds (2020 exactly ties at 0.3345 because 74% of that fold's rows
  carry no milb block and impute 0.0; 2022 dips -0.0033), and 0.45x the floor
  is not a resolvable effect on this pool. Gate clauses 1 and 3 fail.
- The blend composites are strictly weaker re-expressions of the same signal
  (+0.0068 at w=0.5 with 3/4 folds; +0.0050 at w=0.7), monotone TOWARD the
  sb leg: the more tool_speed in the composite, the smaller the margin, which
  is expected since tool_speed is already a served feature and the composite's
  speed share is redundant with it.
- Coverage bound, recorded for the re-run trigger: only 581/845 eligible rows
  (69%) carry a milb block at all, and sb_rate_rel is neutral-imputed on the
  rest; the 2020 fold is the worst (26% coverage) and is exactly the tied fold.

## B5: athleticism blend, the expected null landed

- Any composite carrying tool_field REGRESSES: athl3 -0.0019 with MAE worse by
  0.0265 and t45 collapsing 0.2777 -> 0.2343; speed+field -0.0027 with t45
  0.2012, 1/4 folds, and its own permuted control (+0.0019) OUTSCORES it, i.e.
  destroying the column's information helps more than keeping it.
- speed+throw is pure noise: +0.0021 = 0.12x floor, 2/4 folds.
- PREREG expectation scored honestly: the field/throw null was called in
  advance and confirmed; the sub-call that speed+field would be "the
  informative variant" was WRONG (it is the worst of the three).
- This is the fourth consecutive defense-adjacent refutation on this target,
  after xfv_defense_tools, the Will's-proxy arm, and the def_value swap: the
  binding constraint is the offense-dominated first-6yr-WAR TARGET
  (prospect_def_value.py:37-42), and re-packaging the same grades as
  composites does not change the target.
- Stale-ledger note confirmed in passing: tool_throw is NO LONGER
  "2017-2020-only" (717/845 coverage across debut years 2014-2024); the
  xfv_defense_tools note predates matrix rebuilds. Its coverage was not the
  reason these arms failed.

## Equivalence checks (PREREG section 5), all passed

1. Driver baseline reproduces the stock efv_lab_runner baseline pooled
   Spearman EXACTLY: 0.3882 == 0.3882.
2. In-memory sb recompute vs the committed matrix: 581/581 rows with a stored
   milb block checked on k_rel / obp_rel / level_rank, 0 mismatches (tolerance
   1e-9). All consumed seasons are >= 2014 past-season caches; every one
   carries `sb`; no network was touched (fetch=False norms; player_index reads
   warm caches).
3. MAE was the only addition to the run_variant copy; no fitting logic changed.

Feature-column statistics recorded per PREREG section 3: sb_rate_rel observed
mean +6.3316, sd 12.8574 (n = 581; prospects run well above level median, as a
selected-athlete pool should).

Wall clock: total 8.1 s for the full run (recompute 7.7 s; each variant fit
< 0.1 s). Protocol deviations beyond the three pre-registered ones: none.

## What ships anyway (and its inertness, verified)

The sb plumbing is KEPT per the lane instruction: level_norms.FALLBACK_SB600_NORM
+ level_norms.sb600_league_norm (empirical contemporaneous median, cache-only),
efv_dataset._resolved_norms sb600 chain, _season_rates "sb_rate_rel",
_blend_level_rates + the _milb_features keep tuple. Verified INERT end-to-end:
the committed matrix was not rebuilt (artifact byte-identical); on a future
rebuild the new key rides the milb block, but efv_model._vec does not emit
sb_rate_rel and the served fit reads only _feature_spec(side) names
(_FEATURES_HIT, unchanged) through fit_production_stack, which is the one
production fit shared by efv_score._fit_production (efv_score.py:1627-1640)
and the lambda selector. No served number can move until _FEATURES_HIT names
the key behind its own gate.

The empirical sb-norm leg lives in level_norms.py but reads the milb_history
cache, NOT career_stats: career_stats hitter rows carry `sb` with no `pa`
(0 of 1,816 sampled), so an exact per-600-PA norm is impossible from that
substrate. Declared in PREREG and in the level_norms comment.

## Re-run triggers (earned, narrow)

- B4: a genuinely different feature, not more of this one: (a) CS ingest
  lands (success-rate spec instead of volume; requires the hitting-cache
  schema migration and a refetch, declined this wave as not cheap/safe), or
  (b) milb coverage of the eval pool materially rises (the 2020 fold tie is a
  coverage artifact, 26% covered). Re-running the volume spec blind on an
  unchanged pool is spending a spent arm.
- B5: closed on the same grounds as the three standing refutations; the
  sanctioned lanes for this signal remain display chips and the MLB-side
  defense-IS-WAR surfaces (prospect_def_value.py:37-42). Do not re-attempt
  blind.
