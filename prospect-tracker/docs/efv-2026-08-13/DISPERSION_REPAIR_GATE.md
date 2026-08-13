# C-1 gate: the rank-preserving level correction for Defect A

Pre-registered 2026-08-13 BEFORE the correction was fitted. Results section is
deliberately empty at commit so git timestamps the pre-registration.

This gate EXECUTES a repair that was pre-registered on 2026-07-29 and never
built. It does not re-open the diagnosis and it does not invent new PASS
conditions: the three below are copied from
`docs/efv-2026-07-29/CALIBRATION_FINDINGS.md` section "Pre-registered repair and
gates", item 2. Registry row `xfv_pred_dispersion`, artifact
`data/xfv_pred_dispersion_eval.json`.

## The defect, as already measured

`xfv_war_6yr` is over-dispersed out of sample. OLS slope of realized first-6yr
WAR on the OOS prediction, where 1.0 is calibrated:

| side | slope | CI95 | consensus FV on the same rows |
| --- | --- | --- | --- |
| hit | 0.6540 | [0.3624, 0.7637] | 0.9210 |
| pit | 0.5868 | [0.2326, 0.7210] | 1.1920 |

Neither CI covers 1.0. The permuted-prediction zero-information control sits at
[-0.070, +0.092] hit and [-0.087, +0.124] pit, so the measurement resolves and
is not an artifact of the estimator.

Mechanism, and why the existing layer does not already fix it: `efv_score`
serves `clamp(-2, a + b * ridge_pred)` where `(a, b)` come from
`_fit_linear_calibration` fitted on that fold's TRAINING rows. A calibration
fitted in-sample on train does not transfer: out of fold the predictions spread
wider than the outcomes they are calibrated against. So the served number is
systematically too extreme in both directions.

## What is being repaired, and what is deliberately untouched

REPAIRED: the level of the published `xfv_war_6yr`.

NOT TOUCHED: anything that decides order. This is a level fix and the gate below
exists to stop it becoming a rank change. Also not touched: feature composition,
model class, pooling, alpha, ensembling and blend lambda, all closed by prior
ledgers, per the same section that registered this repair.

## Why this cannot move a single dollar, stated in advance

Served surplus prices off `xfv_grade_quantile`, a rank-quantile map of a frozen
`rank_war`. A strictly increasing transform of the predicted WAR leaves every
quantile position identical, so the dollar effect is exactly $0.00 by
construction, not approximately zero. The 2026-07-29 record makes the same point
and it is re-verified here rather than assumed: the lane reports the served
surplus diff and it must be zero rows moved.

The value of the repair is therefore the honesty of the published WAR number,
the negative-row count, and MAE, which is the metric eFV has a standing
committed loss on. No rank claim is made and none may be made from this lane.

## The correction

An affine, strictly increasing map fitted OUT OF FOLD:

    war_corrected = a_c + b_c * war_pred      with b_c > 0 enforced

Estimated leave-one-fold-out: for scored fold Y the correction is fitted on the
OOS rows of every OTHER fold and applied to Y, so no row contributes to the
correction that is applied to it. A global in-sample refit would report a slope
of 1.0 by construction and prove nothing.

`b_c <= 0` is an ABORT, not a clamp: a non-increasing correction would reorder
the board, which is out of scope for this lane by its own definition.

## PASS conditions (copied from the 2026-07-29 pre-registration, item 2)

1. **Slope CI95 covers 1.0 on BOTH sides** after correction.
2. **Spearman unchanged within the registered MDE95 floors on both sides.** This
   is the clause that stops a level fix becoming a rank change.
3. **Negative-WAR row count materially reduced, with the -2.0 floor no longer
   binding.**

All three must hold. A partial pass is a NO_SHIP with a loss ledger, except that
per the 2026-07-29 precedent a side-split outcome (one side passing, one not) is
reported and referred rather than half-shipped silently.

## Mandatory controls (from the same pre-registration)

- **Zero-information twin**: permute the predictions and re-fit. The corrected
  slope must NOT reproduce on permuted input.
- **Rank-identical level twin**: a correction that shifts level without changing
  order must reproduce the rank metrics exactly. This distinguishes a level
  effect from a rank effect.
- **Permutation null with a reported p-value.**
- Any arm whose effect sits inside its own null band is a non-ship and gets a
  loss ledger.

## Additional clauses this lane adds, and why

- **TAIL MAE MUST NOT WORSEN.** Not in the 2026-07-29 list, added here because
  E2b failed on exactly this in 2026-08-12 and the 2026-06-25 global linear
  recalibration failed on it before that. Fitting a level map on a pool whose
  mass sits near zero WAR drags the sparse high end toward the crowd, and the
  tail is where the board order and the dollars live. Reported for the top
  decile of realized WAR, both sides.
- **The clamp is measured, not assumed.** `clamp(-2, .)` is flat below the floor,
  so rows pinned at exactly -2.0 are TIED. If the correction lifts them off the
  floor those ties break, which can move Spearman slightly even though the affine
  map itself is rank-preserving. The lane reports tie counts before and after and
  attributes any Spearman movement to the clamp rather than to the map.

## Abort conditions

- ABORT if `b_c <= 0` on either side.
- ABORT if the parity check fails: the lane must first reproduce the registered
  uncorrected slopes (0.6540 hit, 0.5868 pit) on its own reconstruction of the
  pool before it is allowed to report a corrected one.

## Stop clause

This gate tests ONE functional form, affine, chosen because it is the minimal
rank-preserving level correction and because the defect is a slope. If it fails,
the lane records a loss ledger. It does NOT proceed to fit a second family in
search of a pass. That is the failure mode the FV45 band correction was banned
for on 2026-08-12.

## Results

(empty at pre-registration; filled by the lane)
