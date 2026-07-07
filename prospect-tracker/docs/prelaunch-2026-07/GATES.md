# Pre-launch eFV accuracy pass: pre-registered gates (2026-07-07)

Registered BEFORE any lab run, per the standing "don't ship losses" rule. Each
experiment ships only if every clause of its gate holds on the forward-chained
OOS protocol (the same fold machinery as efv_model.evaluate / rank_calibration).
Failures are recorded as loss ledgers plus model-registry rows and are binding
against this data vintage.

Baselines at registration (data/xfv_eval.json, data/xfv_eval_pitcher.json,
data/source_backtest.json, all stamped 2026-07-07):
- HIT blend pooled Spearman 0.3524 (n=399), PIT 0.2839 (n=466), debuted_km cut.
- Live lambdas: blend_lambda('hit') = 0.557, blend_lambda('pit') = 0.66.
- Head-to-head pooled: xfv Spearman 0.3600 / contributor-AUC 0.7641 vs consensus
  0.2797 / 0.7340.
- Noise floors from the lean+1 ledger: 0.0023 (hit) / 0.0035 (pit) pooled.

## M1: AUC instrumentation plus artifact truthing (measurement, ships regardless)

Not a model change. Adds per-cohort (hs/college/ifa/draft), per-era, and
per-FV-tier contributor-AUC (cumulative bWAR >= 3) and star-AUC (>= 10) to
efv_model.evaluate outputs, and records the LIVE blend_lambda(side) as
shipped_lambda with rank-gate provenance in data/xfv_eval*.json. No grade or
export changes; golden unaffected.

## M2: lambda re-selection confirmation lab (capped)

Sweep lambda over [0.45, 0.80] step 0.0125, both sides, identical fold machinery
as rank_calibration. SHIP iff ALL of:
1. Composite (pooled + within-tier weighted + t45 fringe, the rank_calibration
   composite) improves >= +0.005 over the live lambda on that side.
2. Pooled Spearman >= -0.002 vs live.
3. No era cell (<=2018, 2019-21, 2022-23) drops > 0.015 on either side.
4. Bootstrap (1000 resamples) P(composite gain > 0) >= 0.75.
Expected outcome: confirms the live 0.557/0.66 (the 0.50-0.70 band was chosen by
a prior bootstrap; pooled is flat 0.80-1.0 with CI positive only near 0.65).
Value either way: a registered confirmation plus the truthed artifact.

## M3: hierarchical shrunk per-cohort lambda

lambda_c = (n_c * lambdahat_c + k * lambda_global) / (n_c + k); lambdahat_c
selected out-of-fold on prior years only (E-LAMBDA protocol); shrinkage
k in {50, 100, 200} selected on pre-2023 folds only. Named keep-alive successor
in data/xfv_cohort_lambda_eval.json (pit:ifa +0.0247 proven direction). SHIP iff
ALL of:
1. Pooled Spearman no-decrease (>= -0.000) on both sides.
2. Each target cohort (pit:ifa, pit <=2018 era; n >= 25) improves >= +0.01.
3. No cohort with n >= 25 degrades > 0.005.
4. Per-era cells: no drop > 0.01 on either side.
5. Within-tier and t45 >= -0.005.
6. E-LAMBDA fold-stability rule: selected lambda_c range across folds <= 0.2 and
   no opposite-sign consecutive fold steps > 0.1.

## M4: ridge alpha grid plus selection criterion

_ALPHAS widens to (0.3, 1, 3, 10, 30, 100, 300); holdout selection switches from
MAE to weighted Spearman (seeded permutation holdout + KM weights retained).
SHIP iff ALL of:
1. Forward-chained OOS blend Spearman improves >= +0.003 on at least one side.
2. The other side >= -0.002.
3. Within-tier and t45 >= -0.005.
4. Per-era cells: no drop > 0.01 on either side.
MAE regression is acceptable (eFV's MAE loss is a committed, documented trade).

## M5: FV-45 fringe ops_rel feature (one attempt)

ops_rel enters the hitter lean set with a fringe-targeted gate (the lean+1
ledger documented a genuine t45 signal of about +0.02 that the pooled-first
gate could not ship). SHIP iff ALL of:
1. t45 tier Spearman >= +0.015.
2. Pooled >= -0.003.
3. Within-tier >= -0.003.
4. Per-era cells: no drop > 0.01 on either side.
One attempt; on failure, ledger and stop. No re-litigation.

## Ship mechanics

Winners plus M1 ship together in ONE regen chain (efv regen -> timeseries ->
proj_export -> mlb_player_export -> build_site), one _GOLDEN_XFV_SHA256 bump
with a dated note, CHANGELOG entry, registry restamp, full suite green.
