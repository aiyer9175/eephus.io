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

(empty at pre-registration)
