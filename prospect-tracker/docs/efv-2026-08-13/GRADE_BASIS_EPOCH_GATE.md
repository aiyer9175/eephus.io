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

| side | lam | mean b_c | lam_eff | against clamp floor 0.35 |
| --- | --- | --- | --- | --- |
| hit | 0.70 | 0.6212 | 0.5917 | +0.242 clear |
| pit | 0.57 | 0.4213 | **0.3583** | **+0.008 clear** |

The hitter figure sits beside 0.60, already TOST-ruled-out as a difference. The
pitcher figure is eight thousandths above `_BLEND_LAMBDA_CLAMP` and far outside
anything tested (TOST covered .65 / .60 / .51), and pitcher `b_c` is the least
stable quantity in the lane (0.308 to 0.651 across folds). Routing the correction
through the blend would spend the calibration fix as an unmeasured lambda cut to the
clamp floor.

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

(empty at pre-registration)
