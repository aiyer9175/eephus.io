# Pre-registration: recalibrating the bust/star odds for SLOPE

Written 2026-07-31, BEFORE any fit is run for this lane. Every number quoted below is an
existing measurement from the cohort lane's adversarial pass, cited, and none of it was
produced under this hypothesis. Nothing here has shipped.

## 1. Why this lane exists

The cohort rebuild (`ODDS_COHORT_REBUILD_GATE.md`) was a NO-SHIP, and the reason it
failed is the reason this lane exists. Cohort conditioning could only ever move a
per-cell INTERCEPT, and the measured defect is a SLOPE:

- incumbent calibration slope on the resolved subpool: **0.368** (1.0 is perfect)
- incumbent ECE: **0.201**

A slope of 0.368 means the odds are compressed toward their mean by roughly a factor of
three. That is a single global distortion, and it is why every cohort grid tested came in
UNDER a one-cell grid: the cells were absorbing miscalibration, not carrying information.

## 2. The measurement that motivates it, and its exact provenance

Measured during the cohort lane's refutation on the same 517-row forward-chained pool
(`scratchpad/rv_platt.py`, reproduced independently before being recorded here):

| arm | Brier | log loss | vs CONST brier | vs CONST logloss |
|---|---|---|---|---|
| CONST (flat base rate) | 0.239340 | 0.673560 | - | - |
| INC (raw incumbent) | 0.231516 | 0.737174 | +0.007824 | **-0.063613** |
| **INC + GLOBAL PLATT** | **0.189564** | **0.571016** | **+0.049776** | **+0.102545** |

Two parameters, zero cohort information, and it clears the bar the previous two odds
lanes both died on. The raw incumbent LOSES to a flat base rate on log loss by -0.0636;
Platt turns that into +0.1025.

**This is a promising number, not a validated one.** It was produced as a control inside
someone else's gate, on one pool, with no forward-chaining discipline of its own and no
controls. That is precisely why it is being pre-registered rather than shipped.

## 3. The hypothesis

**H1:** a two-parameter monotone recalibration of the EXISTING grade-only odds curve
improves probabilistic calibration on held-out folds, against both the incumbent and a
constant base rate.

Note carefully what this is NOT. The already-spent lane re-fit the CURVE
(`data/xfv_odds_recalibration_ship_eval.json`: beats_incumbent true, beats_constant false
on CI, permutation null not cleared). This lane leaves `p_bucket_given_fv` untouched and
applies a monotone transform to its OUTPUT. If that distinction collapses under
inspection, this lane is spent too and should be closed without fitting.

## 4. Gates. Pre-registered, and a miss is a NO-SHIP

**Primary**, both required, both on held-out forward-chained folds with at least four
time splits:
1. Brier and log loss beat the **incumbent**, paired-bootstrap CI95 excluding zero.
2. Brier and log loss beat a **CONSTANT base rate**, paired-bootstrap CI95 excluding
   zero. This is the bar two prior odds lanes have failed. A point-estimate win with a
   CI touching zero is a FAIL, which is exactly how
   `xfv_odds_recalibration_ship_eval.json` failed.

**Mandatory controls**, all four, same standard the cohort lane was held to:
- paired bootstrap on the score gap,
- a zero-information control. For a global recalibration the meaningful shuffle is the
  LABEL, not a cohort tag: refit on permuted outcomes and confirm the gain vanishes,
- a permutation null with a reported p-value,
- at least four time splits.

**Monotonicity**: the transform must be monotone in the input probability, so a higher
grade can never come out with a higher bust probability. Bucket mass must still sum to 1
after the transform and `p_bust` must remain the first element, not an independent fit.

**Calibration reported, not just scored**: reliability curve, slope and ECE before and
after. The claim is specifically that slope moves toward 1.0 from 0.368. If slope does
not move, the mechanism is not what this document says it is and the lane fails even if
the scores improve.

**Blast radius, reported and not targeted**: how many served `p_bust` values move by more
than 5 points and in which direction. A slope correction on a compressed distribution
moves the TAILS hardest by construction, so expect the extremes to move most, and say so
before looking.

## 5. What would make this a NO-SHIP

- Fails to beat a constant base rate on either scoring rule with a clean CI.
- The gain does not survive the label-shuffle control or the permutation null.
- Calibration slope does not move materially toward 1.0, meaning the improvement is
  coming from somewhere other than the stated mechanism.
- It turns out to be materially the same intervention as the already-spent grade-only
  re-fit, in which case it is closed as a duplicate rather than re-litigated.

## 6. Out of scope

Cohort conditioning of any kind (measured, NO-SHIP, and negative on a calibrated base:
d_brier -0.000709, d_logloss -0.008411). Re-keying onto the pooled outcome map (measured,
rejected, KEEP THE PIN). Re-fitting `p_bucket_given_fv` itself (measured, NULL).

## 7. Status

**PRE-REGISTERED, NOT FITTED, NOT SHIPPED.** Served `p_bust` is unchanged. The next
person to pick this up should fit it under the gate above and record the verdict here,
whichever way it goes.
