# C-1 as a GRADE-BASIS EPOCH: pre-registration

Pre-registered 2026-08-14 BEFORE the production-frame coefficients were fitted and
before any seam moved. Results section is deliberately empty at commit so git
timestamps the pre-registration.

Owner decision, taken after the two premises below were falsified: ship the
dispersion correction THROUGH the grade map, as a full grade-basis epoch, with the
re-rank and the dollar movement budgeted rather than denied.

## Why this supersedes the narrow path

`DISPERSION_REPAIR_GATE.md` locked a narrow path on 2026-08-13 whose whole appeal
was two provable neutralities. Both are false, and both trace to the same table in
`SERVE_CHAIN_VERIFICATION.md:24-29`.

**Premise 1, "board order provably identical", is false.** It rested on
`xfv_grade = vf.outcome_implied_fv(xfv_war)` being strictly increasing. It is not.
`value_framework.py:2983-2984` returns `ks[0]` for any `war <= vs[0]`, and the
pooled curve has `value[0] = 0.0` against `knots[0] = 20.0`, so the map is FLAT at
FV 20.0 across the entire non-positive half line. Measured on `data/xfv.json`:
**3,306 of 4,653 active rows (71.1%) sit in that flat region.**

**The flat region is not even the whole of it.** `route_floor_grade`
(`efv_score.py:171-182`) fires exactly when the flagship grade equals the floor
knot, which is exactly when `war <= 0`, and replaces the grade with a value from
the provisional map that has NO functional dependence on `xfv_war` at all.
Measured: **2,137 active rows carry grades from 20.1 to 47.0 while their WAR is
<= 0**, across 200 distinct grade values. For those rows the served grade is not a
function of the quantity being corrected. Any `a_c > 0` lifts a row over the knot,
routing stops firing, and the row falls from a routed grade of up to 47.0 to a
flagship grade just above 20.0.

**Premise 2, "dollars provably do not move", is false.** The gate reasoned about
`rank_war` and the `xfv_grade_quantile` path only. Served `surplus_mm` does not
price off that path. `efv_score.py:2048` computes
`_odds_grade = vf.realized_implied_fv(xfv_war, ...)` from `xfv_war` DIRECTLY, and
`:2083` prices `xfv_surplus = vf.expected_surplus_usd(_odds_grade, ...)`, which is
what `:2120` serves as `surplus_mm`. `realized_implied_fv` is itself flat at 20.0
below zero WAR. This is a second dollar path, independent of the `rank_war` channel
the earlier document analysed.

Recording the correction rather than quietly restating it: the earlier document
claimed both neutralities, this document withdraws both. That is the second time a
neutrality claim on this lane has been wrong, which is why the ship conditions
below require the neutralities to be MEASURED and never argued.

## Scope

    xfv_war_corrected = max(-2.0, a_c + b_c * xfv_war)
    xfv_grade         = vf.outcome_implied_fv(xfv_war_corrected)
    _odds_grade       = vf.realized_implied_fv(xfv_war_corrected, ...)
    xfv_war_6yr       = xfv_war_corrected
    rank_war          = (1 - lam) * cons_war + lam * xfv_war      # UNCORRECTED

Every LEVEL statement moves onto the corrected scale together: the board grade, the
odds grade, and therefore the bucket probabilities and the served dollars. That is
the epoch.

### The blend leg stays uncorrected, and this is not the narrow path returning

The narrow path left the blend uncorrected on a NEUTRALITY argument, and that
argument has been withdrawn. The blend leg is left uncorrected here for a different
and independently recorded reason: correcting it is a BLEND-LAMBDA CHANGE, which is
a banned lane, and the specific number has already been measured as a stop.

Substituting `a_c + b_c * xfv_war` into `(1 - lam) * cons_war + lam * xfv_war` makes
the model leg carry `lam * b_c` against the consensus leg's `1 - lam`. The
equivalent pure lambda is `lam*b_c / ((1 - lam) + lam*b_c)`:

| side | lam | b_c (registered folds) | lam_eff | b_c (PRODUCTION) | **lam_eff** |
| --- | --- | --- | --- | --- | --- |
| hit | 0.70 | 0.6212 | 0.5917 | 0.667655 | **0.6090** |
| pit | 0.57 | 0.4213 | 0.3583 | 0.546925 | **0.4203** |

**The production refit weakens this argument and it is restated on the new number
rather than left standing on the old one.** The 2026-08-13 stop was written when
pitcher `b_c` was 0.4213, which put `lam_eff` at 0.3583, eight thousandths above
`_BLEND_LAMBDA_CLAMP`. On the 11-fold production frame `b_c` is 0.546925 and
`lam_eff` is **0.4203**, clear of the floor by 0.070 rather than 0.008, and the
fold-to-fold spread tightens from 0.308-0.651 to 0.506-0.738. The clamp-proximity
half of the stop is largely gone.

What survives is the part that never depended on the margin: 0.4203 is still
outside everything TOST covered (.65 / .60 / .51), and blend-lambda shifts are a
banned lane on their own terms, not because of how close they land to a clamp.
Routing the correction through the blend would still spend the calibration fix as
an unmeasured lambda change. The conclusion holds; one of its two supports does not,
and mixing a stored figure with a fresh fit is the specific error this programme
has crossed a verdict boundary on twice.

So the split is deliberate and its cost is stated: the grade and the blend read two
versions of one quantity. The argument is that the blend is an ORDERING instrument
whose weights were gated on the uncorrected scale, while the grade and the odds are
LEVEL statements to a reader. Correcting the level without disturbing the gated
ordering is coherent, and it only stays coherent if it is said out loud where a
reader finds it (condition 12).

A separately gated pitcher lambda decision remains open and is NOT taken here.

### Two seam decisions, both load bearing

**Correct THEN clamp, not clamp then correct.** Let `u` be the value at the clamp
seam. `A = max(-2, a_c + b_c*u)` and `B = a_c + b_c*max(-2, u)` agree for every row
iff `a_c <= 2*b_c`. Outside that regime `B` collapses every sub-floor row onto one
identical positive grade and lifts the block above rows with strictly better
predictions, and `B` can also emit a served WAR below -2.0, which breaks the floor
contract every downstream consumer assumes (`_apply_war_tilt:1094`, the xline lean
at `:2027`, `efv_export.py:86`). The registered coefficients satisfy
`a_c <= 2*b_c` with margin on both sides, so the choice is free today and safe if
the refit moves.

**Apply at the LAST seam before the grade, after the tilt and the xline lean, not
at `:1914`.** `_apply_war_tilt` (`efv_score.py:1083-1094`) is multiplicative and
sign aware, so `(a_c + b_c*w)*f` is not `a_c + b_c*(w*f)` whenever `a_c != 0`.
Inserting the affine upstream of the tilt makes the tilt magnitude depend on `a_c`
and can invert pairs that the correction alone would not touch, and the `w >= 0`
versus `w < 0` branch switch at `:1093` compounds it for any sign crossing shift.
Applying after `:2016` and `:2027` keeps the composition a single monotone
transform of the served WAR, which is the weakest condition under which any
ordering statement is available at all.

## Coefficients

Re-fit on the PRODUCTION frame, `SCORED_YEARS = (2014 ... 2024)`, 11 folds, not the
registered 2016-2020 five. The measurement used the narrow set for parity with the
2026-07-29 registration; a ship prices off the frame the served model is actually
fitted on. Fitted with `_fit_affine` on the pre-clamp `raw` column, one global
`(a_c, b_c)` per side, pooled over all OOS fold rows. The per-fold leave-one-out
coefficients stay in the eval artifact as the stability evidence, and are not what
serves.

`b_c <= 0` on either side is an ABORT, not a clamp.

## Ship conditions

These are the 2026-07-29 clauses, unchanged, plus the epoch clauses this scope
requires. A partial pass is a NO_SHIP.

1. Slope CI95 covers 1.0 on BOTH sides after correction, on the production frame.
2. Negative-WAR row count materially reduced, with the -2.0 floor no longer binding.
3. Parity: the lane reproduces the registered uncorrected production-frame slopes
   before it is allowed to report a corrected one.
4. **The re-rank is MEASURED and published**, not asserted absent: rows moved, max
   and median rank delta, and membership change at top 10 / 25 / 100 / 250.
5. **The dollar movement is MEASURED and published**, both channels named
   separately (the `_odds_grade` channel and the `rank_war` quantile channel).
   A zero here would now be a surprise and must be explained if it appears.
6. **The routing flip is MEASURED**: how many rows cross the 0-WAR knot, how many
   lose a routed provisional grade, and the largest single grade drop.
7. Epoch bump on `storage.BOARD_RANK_BASIS_EPOCH` plus a fingerprint term that
   NAMES the correction, in the same commit as the seam change.
8. `prospx_current` re-capture INSIDE `with vf.valuation_set("prospx_current")`,
   then a golden restamp.
9. Every margin this programme quotes is re-read on the new basis BEFORE anything
   is adjudicated against it. A fresh delta is never read against a stored floor.

## Clauses that are reported, not gated

**Tail MAE worsens and that is accepted.** Top decile of realized WAR, measured
7.13 to 8.39 hit and 5.81 to 6.71 pit on the registered frame. A slope-1 map is the
linear map that minimises squared error overall, and on a noisy predictor it
necessarily pulls extremes toward the middle, so no affine map improves the level
and the tail at once. The stop clause below forbids answering this by fitting a
second family. It is disclosed to the reader instead (condition 12).

## Additional obligations this scope creates

10. **Server and client tiebreaks must not diverge.** `storage.py:11119-11142`
    sorts on `_tbs_proxy`, which does not read `xfv_war`; the client
    `tiebreakerScore` (`prospx/index.html:11473-11479`) weights
    `xfv_war_6yr` at 0.90. Correcting the served WAR moves one and not the other.
    Either both move or the client is repointed, in this commit.
11. `bayes_trade_value.py:4832` reads `xfv_war_6yr` and must be pointed
    deliberately, not by default.
12. Disclose in the glossary: a star's projected WAR reads about 1.25 (hit) and
    0.90 (pit) below outcome over six years, in exchange for the level being right
    everywhere else.

## Abort conditions

- ABORT if `b_c <= 0` on either side.
- ABORT if the production-frame parity check fails.
- ABORT if the re-rank moves top-10 membership. That is not a gate on the size of
  the change, it is a tripwire on the possibility that the correction is doing
  something other than what this document describes.

## Stop clause

One functional form, affine, because the defect is a slope. If it fails, the lane
records a loss ledger. It does NOT proceed to fit a second family in search of a
pass, which is what the FV45 band correction was banned for on 2026-08-12.

## Results

Measured 2026-08-14 on the PRODUCTION frame (`efv_model.SCORED_YEARS`, 11 folds),
with the coefficients that actually serve. Nothing here is inherited from the
registered 2016-2020 measurement.

### Coefficients, and the parity check that licenses them

| side | n | a_c | b_c | LOO b_c range |
| --- | --- | --- | --- | --- |
| hit | 1,779 | 0.460179 | 0.667655 | 0.607 to 0.737 |
| pit | 1,878 | 0.494262 | 0.546925 | 0.506 to 0.738 |

Parity PASSED on the registered frame before anything was reported on the new one:
reproduced 0.6489 against 0.654 registered (hit) and 0.5624 against 0.5868 (pit),
both inside `PARITY_TOL` 0.12.

`b_c > 0` on both sides, so no abort. `a_c <= 2*b_c` on both (margins -0.875 and
-0.600), so correct-then-clamp and clamp-then-correct are provably identical here
and the seam order costs nothing.

**The 11-fold frame is materially better behaved on the pitcher side**: LOO `b_c`
tightens from the registered 0.308-0.651 to 0.506-0.738. The registered spread was
the single least stable number in this lane and it was the reason the full-epoch
route looked dangerous; on the production frame it is not.

### Ship conditions

| # | condition | hit | pit |
| --- | --- | --- | --- |
| 1 | slope CI95 covers 1.0 | 0.6926 -> **1.0151**, CI [0.8457, 1.1848] PASS | 0.6741 -> **1.1778**, CI [0.9129, 1.4783] PASS |
| 2 | negatives down, floor not binding | 643 -> 409, floor 117 -> **13** PASS | 530 -> 147, floor 24 -> **10** PASS |
| 3 | parity before corrected report | PASS | PASS |
| 4 | re-rank MEASURED | 4,585 of 4,664 moved, max 3,414, median 354, p90 377 | |
| 5 | dollars MEASURED | 2,397 rows move `_odds_grade`; `rank_war` untouched so the quantile channel is 0 by construction | |
| 6 | routing flip MEASURED | **0 lost, 0 gained** | |
| 7 | epoch + fingerprint term | `BOARD_RANK_BASIS_EPOCH` 2026-08-13, `disp=` term added and the pinned constant restamped | |

Top-of-board movement, the abort tripwire: **top-10 membership changes 0**. top25 2,
top100 1, top250 3. The churn is entirely in the 250 to 3,000 band, which is the
same signature the 2026-08-07 floor-routing bump was written for.

### Condition 6 is the finding, not a formality

The naive seam decides routing on the CORRECTED grade. Measured that way:

    currently routed             2,397
    cross the 0-WAR knot upward  1,065
    LOSE a routed grade            950
    largest drops   diego_fernandez  40.1 -> 25.0   (war -0.68 -> +0.01)
                    sebastian_puche  40.0 -> 25.0   (war -0.68 -> +0.01)
                    kevin_martinez   36.6 -> 25.0   (war -0.68 -> +0.01)

A 15-point grade drop on a WAR move of eight hundredths. The mechanism:
`route_floor_grade` uses "the flagship grade sits exactly on the floor knot" as its
proxy for "the model has no real prediction for this player", and a positive
intercept breaks that proxy for every row at once. The provisional map exists
BECAUSE the flagship curve is unusable near zero, so lifting 950 players onto that
exact region is the opposite of the repair's intent.

Routing is therefore answered on the uncorrected grade. It is a question about the
model, not about the calibration of its level. With that ordering the routed cohort
is preserved exactly and the re-rank p90 tightens from 1,253 to 377.

### Reported, not gated

Tail MAE worsens, as pre-registered: hit 7.480 -> 8.664 (+15.8%, n=178), pit
6.303 -> 6.836 (+8.5%, n=188). Overall MAE improves 10.7% and 8.0%. The trade is
intrinsic to any affine map on a noisy predictor and the stop clause forbids
answering it by fitting a second family. Disclosed to the reader in
`data/glossary.json` per condition 12, at the measured magnitude (about 1.2 WAR
hit, 0.5 pit) rather than the registered-frame figures.

### Limits

- The pitcher slope OVERSHOOTS 1.0 (1.1778) and its CI is wide, [0.913, 1.478]. It
  covers 1.0, which is the clause, but the pitcher correction remains the imprecise
  half of this lane.
- The correction is fitted on the pre-clamp model prediction and applied at the
  grade seam, which is post-tilt. For rows carrying an overlay (injury, Statcast,
  age, reliever ceiling) the domain therefore differs slightly from the fitted one.
  For every row with `adj_factor == 1.0` and no xline lean, which is the large
  majority and ALL of the measured frame, the two coincide exactly.
- `board_sort_key` stays on the uncorrected pre-clamp value. Order is unaffected
  because the correction is strictly increasing, but the key is not on the same
  basis as the grade it breaks ties for, and that predates this change.
