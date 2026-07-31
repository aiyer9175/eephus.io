# Owner decision: surplus becomes an EXPECTED-VALUE quantity

Taken 2026-07-31, after the re-fit failed its MAE gate and the failure turned out to be
about the objective rather than the fit. Written BEFORE the change is made.

## 1. What was decided, and why it is not a reversal

The re-fit was measured and **lost the MAE gate on 3 of 3 folds** (11.518 shipped against
13.581 refit). That verdict stands and is not being re-litigated. What changed is the
question.

`surplus_backtest_real` scores **per-player MAE**, which is minimised by the conditional
MEDIAN. On this population the median is brutal: **86 to 90% of the bottom bins realise
$0.1M or less, so their median is exactly $0.00** while their MEAN is $1.7M to $5.9M. A
median-seeking metric therefore says $0 is the right answer for two thirds of the board,
and the shipped calibration's zero clamp is not a bug under that metric. It is the
optimum.

But `bayes_trade_value.apply_platform_surplus` consumes surplus as a **price**, and a
price is an expectation. A club acquiring 3,822 bottom-tier players is not acquiring
3,822 zeros; it is acquiring 3,822 lottery tickets with positive expected value. Under
that objective the zero clamp is simply wrong, and it is wrong by $1.7M to $3.9M a head.

**Owner decision: surplus is an expected-value quantity.** That makes the EV gate the
governing one and MAE a reported diagnostic, not the bar.

## 2. Consequence: the gate metric changes, and the map that wins changes with it

This must be stated plainly so nobody later reads this as the failed re-fit being
smuggled in. **The re-fit failed the MAE gate. It is being shipped because the objective
moved to the one it was always fitted for**: the calibration is a count-weighted PAVA on
equal-count bin MEANS, i.e. it targets the conditional mean by construction.

Governing metrics under the EV objective, held out, leave-one-year-out:

| metric | uncalibrated | shipped map | **re-fit** |
|---|---|---|---|
| **held-out bias** (mean realised minus predicted; 0 is perfect) | +2.521 | (clamps low) | **-0.028** |
| **held-out calibration slope** (1.0 is perfect) | 1.239 | | **1.059** |
| held-out MAE (now a diagnostic) | 12.251 | **11.518** | 13.581 |

The re-fit is essentially unbiased and near-perfectly sloped on the EV objective. It is
worse on MAE, and under the new objective that is an accepted, documented cost rather
than a failure: MAE rewards predicting zero for a population whose expectation is not
zero.

## 3. Ship gate for the change itself

1. **Bias must beat the incumbent on held-out folds** and land near zero. Measured:
   -0.028 against +2.521 uncalibrated.
2. **Calibration slope must move toward 1.0.** Measured: 1.059 against 1.239.
3. **Monotonicity across the whole grade range, every role.** Already guaranteed by the
   C6 floor shipped earlier today; re-verify after the map changes.
4. **No board-ORDER movement.** Surplus prices off the rank quantile, so a pricing change
   must leave grades and ranks byte-identical. Verify, do not assume.
5. **Blast radius reported**: how many rows change price, the distribution, and
   explicitly how many leave $0.

## 4. What this breaks that must move with it

- **The `$0` floor disappears.** That is the point, but it means **Arm 1's "under floor"
  display becomes wrong** and must be removed in the same change, along with the tooltip
  that explains a floor that no longer exists.
- **`test_value_framework::test_calibration_layer_is_real_fit_and_monotone`** should go
  GREEN, because `ys[0]` stops being 0. If it does not, the change did not do what this
  document claims.
- **`config/valuation_sets/prospx_current.yaml`** captures the tier dollars and must be
  re-frozen; `value_framework.py --emit-snapshots` must re-run.
- **Every dollar on the site moves.** Cards, PROSPX, the trade machine, farm finance.
  This is the largest served-number change in this program and needs a regen plus a
  golden restamp.
- **Copy.** Anywhere surplus is described as what a player is "worth" should now read as
  an expected value, because that is what it will be.

## 5. What does NOT change

Grades, ranks, board order, bust odds, and the eFV model itself. This is a pricing-layer
change only. If any of those move, something is wrong and the change should be reverted
rather than explained.

## 5a. SHIPPED 2026-07-31: what was measured after the change

Every gate condition in section 3, verified rather than assumed.

**Gate 4, no board-order movement: PASS, and it is exact.** Across all 9,334 rows, zero
changed `xfv_grade`, `xfv_grade_quantile` or `xfv_war_6yr`. Not "within tolerance" -
zero. Rowcount unchanged at 9,334.

**Gate 3, monotonicity: PASS.** Swept FV20-80 in 0.5 steps, both roles, both valuation
sets. No inversion. `calibration_zero_cross_mm()` now returns `None`, which is the
intended steady state and is documented as such at the function.

**Gate 5, blast radius.** All 9,334 prices moved and all moved UP:

| | |
|---|---|
| rows priced at exactly $0 | **6,271 -> 0** |
| delta min / median / p90 / max | +$0.70M / +$2.00M / +$8.20M / +$11.30M |
| rows that fell | **0** |
| board total | $33,660M -> $58,688M (**+74.4%**) |

Tier grid, base-identity context. The SHAPE is the evidence that this is a median-to-mean
switch and not a revaluation: the top barely moves because up there the median and the
mean are the same player, while the middle and bottom lift hard because that is where the
two diverge.

| | 35+ | 45 | 50 | 60 | 70 |
|---|---|---|---|---|---|
| hitter v5 -> v6 | 0.0 -> 2.5 | 11.7 -> 21.6 | 32.8 -> 43.4 | 90.5 -> 97.0 | 206.0 -> **204.0** |
| pitcher v5 -> v6 | 0.0 -> 2.0 | 7.4 -> 12.2 | 23.2 -> 34.3 | 73.6 -> 81.3 | 178.1 -> **178.2** |

**Downstream: the trade machine damps it.** $46,070M -> $54,497M, +18.3% against the
board's +74.4%, because four archetype floors are denominated in absolute dollars and did
not re-scale. 5,107 of 6,414 rows moved, median +$0.7M, and a minority FELL (min -$3.9M)
where a widened relative cap stopped binding. That asymmetry is registered, with its own
gate, in `TRADE_ARCHETYPE_FLOOR_GATE.md` - it is a consequence of this change and is
deliberately NOT repaired inside it.

**Tripwires that fired, and what each turned out to be.** All were re-examined rather
than widened:

- `test_calibration_layer_is_real_fit_and_monotone` went GREEN, as section 4 predicted it
  must. If it had not, this change did not do what this document claims.
- Three FV50 price literals restamped across `test_valuation_sets` and
  `test_clemens_reconciliation`. Where a literal was standing in for an invariant, the
  invariant is now asserted directly (model/table separation; cache-cleared-on-switch;
  posterior never above `prior * 0.75`) so the next re-price restamps one number instead
  of quietly voiding a guard.
- **`fit_tier_reconciliation`'s k flipped below 1.0** (hitter 0.90, pitcher 0.95, both
  interior to the 0.5-4.0 grid, so converged not clamped). The model now prices ABOVE the
  published industry tiers. That is the expected direction under an EV objective and is
  the same fact as section 6's caveat, arriving from a different instrument.
- `test_low_prior_partial_sample_hitter_gets_surplus_cap`: the cap is relative
  (`prior * mult`), the FV42 fixture drifted to the far side of a steep step in the new
  curve, and the guard still fires across FV34-40. Fixture moved to FV40, invariant added.
- One PRE-EXISTING defect surfaced and confirmed red at HEAD, so not caused by this
  change: the MLB projection anchor is announced and then silently overridden by
  `archetype_posterior_floor` on 77 of 276 anchored rows ($1,365M). Gated, xfailed
  strict, not repaired here.
- One pre-existing identity collision baselined: `drew_smith`, two genuinely different
  humans (mlbam 622098 and 805021) on one slug, inactive record, zero active impact.

## 6. The honest caveat to publish

An expected value on a lottery-shaped population is dominated by outcomes that will not
happen to the individual player in front of you. The typical bottom-tier prospect really
does return nothing; the tier as a whole does not. Both facts are true, and the site will
now be publishing the second one. The card copy should say so rather than letting a
reader infer that a $1.5M prospect is likely to return $1.5M.

**And the bottom is still flat, just no longer at zero.** The isotonic map clamps below
its first knot (raw $0.82M), so **3,906 of 9,334 served rows share one price, $0.70M**.
That is 42% of the board carrying no ordering information in its dollars. This is not a
regression - those same rows previously shared $0.00M, so the flat block is exactly as
wide as it was and is merely at an honest level now. But it does mean "ranked 6,000th vs
6,500th" says nothing about price, and the card tooltip says so in those words. Anyone
tempted to read fine structure into the bottom of the surplus column should read this
paragraph first.
