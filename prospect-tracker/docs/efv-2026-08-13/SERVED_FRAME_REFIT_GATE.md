# C-1d: re-fit the level correction on the frame where the level is actually stated

Pre-registered 2026-08-14 BEFORE any coefficient was fitted on the new frame.
Results section deliberately empty at commit so git timestamps this.

## The defect, measured

The shipped correction is `war -> a_c + b_c * war` with `a_c = 0.470359`,
`b_c = 0.663929` (hit). Its break-even, where the map neither lifts nor shrinks, is
`a_c / (1 - b_c) = ` **1.40 WAR**, which lands at roughly consensus FV 45.

Measured on the served board, by consensus band, which way the correction moves a row:

| band | n | shrinks | lifts |
| --- | --- | --- | --- |
| 55+ | 14 | **93%** | 0% |
| 50 to 55 | 35 | **97%** | 0% |
| 45 to 50 | 139 | **86%** | 0% |
| below 45 | 4,470 | 5% | **90%** |

Board-wide that is 86% lifted and 8% shrunk, which sounds benign and is not. Every
lifted row is org filler; **essentially the entire visible board is shrunk.** The
owner saw it as "eFV is deflated across the board" and as "level calibration is
punishing everyone", and both readings are correct about the part of the board a
reader ever looks at.

## Why the current frame is the wrong one

The coefficients are fitted on the whole scored pool, whose mass sits at zero WAR.
That pool decides a single global slope, and the slope it picks is the one that fits
the filler. The prospects then pay for it.

Worse, **a large part of that pool has no level statement to calibrate.** Two
separate mechanisms remove it:

- `vf.outcome_implied_fv` is FLAT at FV 20.0 for every prediction at or below 0 WAR,
  so no change to a sub-zero prediction alters the served grade at all.
- `route_floor_grade` replaces the grade outright for the constant-anchor cohort,
  from a provisional map with NO functional dependence on `xfv_war`. Measured on the
  current board: **2,400 of 4,658 active rows.**

So roughly half the served board's grades do not read the corrected quantity, while
their rows are fully weighted in the fit that produces it.

## The change

Same functional form, same estimator, same leave-one-fold-out protocol. ONLY the
fitting frame moves: fit on the rows where the level statement is actually made,
i.e. rows whose prediction resolves on the curve rather than landing in the flat
region.

    RESTRICTED FRAME:  fold rows with raw prediction > 0
    (the region where outcome_implied_fv is not flat)

**This is not a new family and is not a search for a pass.** The affine family and
its estimator are unchanged; what changes is the sample the calibration is
estimated from, on the ground that a calibration should be fitted on the population
it is applied to as a level statement. The C-1b stop clause bans fitting a SECOND
FAMILY after a failure; it does not require fitting the first one on a frame that
includes rows the statement does not describe.

Both frames are fitted and reported side by side. The incumbent is re-measured in
the same run at the same folds and seeds.

## HARD clauses. All must hold.

1. **Slope CI95 covers 1.0 on BOTH sides**, measured ON THE RESTRICTED FRAME. The
   restricted frame is the population the correction now claims to calibrate, so it
   is where the calibration claim must be tested.
2. **The break-even must move materially up in WAR**, so the correction stops
   inverting direction inside the visible board. Declared threshold: the share of
   served rows with consensus_fv >= 45 that are SHRUNK must fall below 50%, from
   the current ~88%.
3. **The elite must not invert.** Mean `eFV - consensus` over served rows with
   `consensus_fv >= 55` must be `>= -2.0`. Two-sided, unlike C-1b's clause 3, which
   was written one-sided and was satisfied at +7.91 by a family that inflated every
   grade. Upper bound: it must also be `<= +2.0`.
4. **The low-end repair must not regress.** Rows pinned at the -2.0 floor must stay
   materially below the uncorrected count, and the sub-45 served cohort's mean
   `eFV - consensus` must not fall below the uncorrected -10.97.
5. **No reordering.** `b_c > 0` and the map strictly increasing, asserted on a dense
   lattice.

## Controls

- **Incumbent re-measured in the same run.** No stored figure is compared against a
  fresh one.
- **Full-frame sanity**: the restricted-frame coefficients applied to the FULL pool
  must still improve overall MAE against uncorrected. If the fix helps the visible
  board by wrecking the aggregate, that is a trade to refer, not to ship.
- **Routed-cohort invariance**: the routed cohort must be preserved exactly, as in
  the shipped seam. Routing is decided on the uncorrected grade and that does not
  change here.

## Abort conditions

- ABORT if `b_c <= 0` or the map is not strictly increasing.
- ABORT if the restricted frame has fewer than 400 rows on either side.
- ABORT if clause 4 fails: buying the top by breaking the bottom is not a fix, it is
  the same defect pointing the other way.

## If it ships

Another grade-basis epoch: coefficients change, so the fingerprint `disp=` term
changes with them, the epoch bumps, `prospx_current` re-captures, golden restamps,
and every margin is re-read. The `Level calibration` chip's magnitudes move and its
direction flips for much of the board, which is the visible point of the change.

## Results

Measured 2026-08-14, `tools/efv_served_frame_lab.py 2000`, artifact
`data/xfv_served_frame_eval.json`.

**ABORT. The restricted frame is NO_SHIP, and it fails worse than the incumbent.**

| frame | side | n | a_c | b_c | break-even | elite mean | sub45 mean | visible shrunk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| incumbent | hit | 1,779 | +0.4704 | 0.6639 | **1.40** | -4.95 | -5.44 | **100%** |
| incumbent | pit | 1,879 | +0.4937 | 0.5469 | 1.09 | | | |
| restricted | hit | 1,131 | **-0.3406** | 0.8033 | **-1.73** | -3.50 | **-11.72** | **100%** |
| restricted | pit | 1,349 | -0.0034 | 0.8122 | -0.02 | | | |

Clause 2 fails on BOTH frames: 100% of the 188 visible rows are shrunk either way.
Clause 3 fails on both. Clause 4 fails on the restricted frame, which is the
decisive one: the sub-45 cohort goes to **-11.72**, worse than the uncorrected
-10.97, and the floor rows barely improve (125 to 108 against the incumbent's 13).

### Why the frame change did not help, and what it actually revealed

Restricting the frame did what it was supposed to do to the SLOPE: `b_c` rises
from 0.664 to 0.803 on hitters, so the shrinkage of high predictions genuinely
eases, and the elite gap narrows from -4.95 to -3.50.

But `a_c` goes NEGATIVE (-0.34), which moves the break-even from +1.40 WAR to
**-1.73 WAR**. So the map now shrinks everything above -1.73 instead of everything
above +1.40, i.e. MORE of the board, and it pushes the low end down hard enough to
fail clause 4. Trading a small gain at the top for a large loss at the bottom is
precisely what clause 4 was written to refuse.

**The structural fact, now confirmed from a third independent direction: `b_c` is
below 1.0 on EVERY frame tried.** Full pool 0.664 / 0.547. Restricted to rows that
resolve on the curve, 0.803 / 0.812. C-1b's five families, all of them. The model
is over-dispersed out of sample on every population it is measured on, so any
affine map that calibrates it must shrink high predictions, and the only thing a
frame change moves is WHERE the break-even sits.

There is no frame on which the correction stops shrinking good prospects, because
the thing being corrected is real.

## RETRACTION: my own "+13 FV optimism" figure was a Jensen artifact

Earlier in this session I reported, to the owner, that "consensus is optimistic by
+13.12 FV (hit) and +12.51 (pit)" from comparing a mean consensus FV of 41.13
against a mean realized-implied FV of 28.01. **That comparison is not sound and I
am withdrawing it.**

`outcome_implied_fv` is steeply convex in WAR (0 WAR to FV 20.0, 1 WAR to FV 42.8,
3 WAR to FV 46.6), so `E[g(W)]` is not `g(E[W])`. Measured on a spread of WAR
values: mean of the FVs is 47.93, FV of the mean WAR is 52.48, a 4.5 point gap
created by the curve alone. Averaging FV across a population whose WAR distribution
is mass-at-zero manufactures most of the "+13".

The sound comparison is in WAR space, which C-1c already did: on the elite band the
corrected arm's bias is -1.33 WAR (hit) and -2.52 (pit), against the uncorrected
+1.78 and -0.74. Those are the numbers that carry the claim. **The direction of the
earlier statement survives on hitters and the magnitude does not, and no conclusion
in this programme should rest on the retracted figure.**

## What ships

Nothing. Two frames, both NO_SHIP. Combined with C-1b's five families and C-1c's
null, three independent lanes now agree that the elite shrinkage is a property of
the model rather than of the correction's functional form or its fitting frame.

The remaining candidate is the one none of these lanes touched: **the outcome
curve itself**, which is flat below 0 WAR, runs about 122 FV per WAR between knots
30 and 35, and is blended to an industry prior above FV 57. Every lane so far has
corrected the INPUT to that curve. Nothing has questioned the curve.
