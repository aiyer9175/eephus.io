# eFV level-calibration findings and pre-registration - 2026-07-29

Governed by `docs/EFV_GATE_STANDARD.md`. This document states what is measured, what is
proposed, and the gates, BEFORE any fit is run. Nothing here is shipped yet.

## Why this exists

The 2026-07-25 session measured two level defects and then died to the weekly credit limit
before recording either. The artifacts survived as orphan eval files with no registry rows
(`data/xfv_pred_dispersion_eval.json`, `data/xfv_level_calibration_eval.json`), which is why
`test_model_registry::test_every_eval_artifact_is_registered` is red. Both findings are real,
both carry proper controls, and both feed served surplus dollars. They are the substantive
answer to "make eFV more accurate" that does NOT violate the standing loss ledgers, because
neither is a RANK lever.

This matters now for a second reason. The board no longer serves the rank-quantile grade: since
the 07-25 `efv-unify-and-anchor` decision, `xfv_grade` is a raw-plus-affine transform of model
output (`efv_board_scale.board_value`). The older frontier-audit conclusion that "level accuracy
cannot move served surplus, because surplus is a function of rank only" was true under the
quantile display basis and is NOT true under the board-scale basis. Level work now moves served
numbers.

## Defect A - the model's WAR prediction is over-dispersed

Statistic: OLS slope of realized first-6-year bWAR on the out-of-sample prediction. A slope of
1.0 is calibrated in level; below 1.0 means the prediction spreads wider than reality.

| side | eFV slope | CI95 | consensus slope | n |
|---|---|---|---|---|
| hit | 0.654 | [0.362, 0.764] | 0.921 | 749 |
| pit | 0.587 | [0.233, 0.721] | 1.192 | 819 |

Late-model subsets are worse (`lm_slope_xfv_war` 0.618 hit, 0.372 pit).

Control: permuting the prediction gives CI95 [-0.070, 0.092] hit and [-0.087, 0.124] pit. The
measured slopes sit far outside the zero-information band, so this is a real measurement and not
a small-sample artifact. Note the comparison that matters: **consensus FV is close to calibrated
in level while eFV is not.** eFV wins on rank and loses on level, which is consistent with the
long-standing "eFV beats consensus on Spearman, loses on MAE" ledger, now given a mechanism.

Served consequence: `data/xfv.json` currently carries **3,821 of 9,318 rows with a negative
projected 6-year WAR**, floor -2.0. At the bottom of the scale the model predicts -1.03 where
realized is +0.13. Over-dispersion is why the bottom tail runs negative.

## Defect B - the grade-to-WAR anchor over-states the bottom of the board

Statistic: `bias = realized - implied`, where implied is
`6 * value_framework.fv_to_6yr_avg_war(grade)`, the config's own declared meaning of a grade.
Negative bias means the config promises more WAR than the tier delivers. Forward-chained OOS,
fully-resolved decision years only.

| tier | n | bias | CI95 | zero-info control CI95 | verdict |
|---|---|---|---|---|---|
| 35 | 87 | -0.943 | [-1.181, -0.410] | [-0.531, +1.147] | REAL, over-stated |
| 40 | 471 | -0.883 | [-1.014, -0.607] | [-0.070, +0.718] | REAL, over-stated |
| 45 | 94 | +0.387 | [-0.781, +1.624] | [-1.166, +0.697] | null |
| 50 | 51 | +2.181 | [+0.112, +4.303] | [-3.372, -0.975] | REAL, under-stated |
| 55 | 27 | +3.178 | [-0.905, +6.245] | wide | null |
| 60 | 14 | -0.234 | [-4.301, +4.301] | wide | null |

Pooled hit bias -0.326, CI95 [-0.570, -0.045].

The FV40 cell is the finding. It is the modal cell of the board (n=471), its CI excludes zero
comfortably, and it sits entirely outside its own permuted-grade control band. The anchor
promises roughly 0.9 more 6-year WAR at FV40 than that tier has ever delivered. FV35 agrees in
direction. FV50 runs the other way. So the declared anchor curve is too flat: too generous at the
bottom, too stingy in the middle.

This is the same `fv_to_6yr_avg_war` layer that `data/value_framework_fitted.json` supplies, and
it is exactly the layer the killed `dpw-reconcile-surplus-recal` workflow was sequenced to refit
before the surplus map. Defect B is therefore direct evidence that the anchors refit belongs
IN scope for the surplus window, not deferred.

## How A and B relate

They are distinct layers and must not be conflated. A is the model's predicted WAR
(`xfv_war_6yr`). B is the config's declared WAR meaning of a displayed grade. Surplus consumes
both: the board grade comes from model output through the board scale, and dollars come from the
grade through the anchor curve and then the surplus map. A mis-level in either propagates to
dollars, which is why the FV40 cell and the negative-WAR tail both end up mispricing the 77
percent of the board that sits at FV40-45.

## Pre-registered repair and gates

Order is forced by the layering: fix the anchor curve before refitting the surplus map on top of
it, otherwise the surplus fit silently absorbs anchor error. This is the same mistake as the
2026-07-14 lambda retraction, where a conclusion was drawn on top of an uncorrected layer.

1. **Anchors (Defect B).** Refit `fv_to_6yr_avg_war` on the normalized FV scale over the
   resolved cohort. PASS requires: per-tier bias CI95 covering zero at FV35, FV40 and FV50
   simultaneously; monotone curve preserved; no tier discontinuity that trips
   `test_no_jump_across_specific_grade_boundary`.
2. **Dispersion (Defect A).** A rank-preserving level correction of `xfv_war_6yr`. PASS requires:
   slope CI95 covering 1.0 on both sides; **Spearman unchanged within the registered MDE95
   floors on both sides** (this is a level fix and must not be allowed to become a rank change);
   negative-WAR row count materially reduced with the floor no longer binding at -2.0.
3. **Surplus map.** Only after 1 and 2, refit on the normalized pool, then the coordinated
   `prospx_current` re-freeze.

Mandatory controls on every arm, per the gate standard: a zero-information twin, a rank-identical
level twin, and a permutation null with a reported p-value. Any arm whose effect sits inside its
own null band is a non-ship and gets a loss ledger.

Explicitly NOT in scope: feature composition, model class, pooling, alpha, ensembling, blend
lambda. Those lanes are closed by prior ledgers and nothing here reopens them.

## Registry

Both artifacts get rows in this program (`xfv_pred_dispersion`, `xfv_level_calibration`),
verdict `provisional`, with these findings as notes. That closes part of baseline cluster 4.
