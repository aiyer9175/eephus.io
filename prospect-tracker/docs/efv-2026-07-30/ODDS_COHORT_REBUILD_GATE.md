# Pre-registration: a cohort-anchored rebuild of the bust/star odds

Commissioned by the owner 2026-07-30 after the calibration-versus-cohort gap was put to
them as a choice. Written BEFORE any fitting, per ground rule 12 of
`docs/master-plan-2026-07-30-nine-asks.md`. Nothing here has been measured yet; every
number quoted is an existing committed measurement, cited.

## 1. The defect, stated as a number

Served today:

| player | served `p_bust` | own outcome comp cohort |
|---|---|---|
| brayden_taylor | 0.264 | AAA, age >= 23.5, ops_rel < 0: **77.1% bust** (n=83) |
| enrique_bradfield_jr | 0.243 | same cohort, 70.3% at the wider cut (n=145) |

A model that prices a 24-year-old repeating Triple-A at a one-in-four bust rate, when the
players who most resemble him busted three times in four, is not mis-scaled. It is
answering a different question from the one a reader thinks they are asking.

**Neither existing basis fixes it.** The odds key off `_odds_grade`, which is the RETIRED
`realized_implied_fv` map, deliberately pinned there when the board moved to the pooled
outcome curve. Re-keying onto the new map was measured and moves `p_bust` DOWN (hit mean
-0.0120, pit -0.0400, `POOLED_OUTCOME_REFIT.md` 2.3), i.e. away from the cohort. A
same-day re-key gate concluded KEEP THE PIN, and a separate recalibration re-fit came back
a NULL against its own base rate (`data/xfv_odds_recalibration_ship_eval.json`: beats the
incumbent but NOT a constant, and does not clear the permutation null).

So both roads out of the current model have been tried. That is why this is a rebuild
rather than another re-key.

## 2. The hypothesis

The odds are a function of GRADE alone: `p_bucket_given_fv(fv, is_pitcher)`, a smooth
monotone 5-vector over a single scalar. Two players with the same grade get the same
bust probability regardless of how they got there.

But grade is a summary that has already averaged away the thing that predicts busting.
A 45 FV who is 20 and just reached Double-A and a 45 FV who is 24 and repeating Triple-A
are the same number and emphatically not the same risk. The cohort evidence is already in
hand and is stark: the Arias-shaped cell (AAA, age <= 22, ops_rel > 0, n=20) realized
10.29 mean WAR and **10% bust**, while the Bradfield-shaped cell (AAA, age >= 23.5,
ops_rel < 0, n=83) realized 0.50 mean WAR and **77% bust**. Same neighbourhood of the
grade scale, a 7.7x spread in bust rate.

**H1:** conditioning the outcome-bucket distribution on (grade, age-for-level, recent
production) rather than grade alone materially improves probabilistic calibration.

## 3. What gets built

`tools/odds_cohort_lab.py` fitting P(bucket | grade, age_rel_level, ops_rel/k_rel) on the
resolved pool, with the existing `p_bucket_given_fv` as the shrinkage prior for thin
cells. Same 5-bucket target and the same monotonicity contract in grade, so the curve
remains monotone at fixed cohort. Deliverables: `data/xfv_odds_cohort_eval.json`, a
registry row, and this file's verdict section.

Design constraints fixed now, not after seeing results:

1. **Cell thinness is the enemy.** The motivating cells are n=20 and n=83. Every cell
   shrinks toward the grade-only curve by n/(n+k) with k pre-declared, and the artifact
   reports per-cell n and prior weight the way `fv_outcome_curves_pooled.json` does.
2. **Monotone in grade at fixed cohort.** A higher grade must never carry a higher bust
   probability within a cohort. Violations get repaired, and the repair magnitude is
   reported.
3. **No look-ahead.** Cohort features must be as-of the decision date, using the same
   `cutoff` discipline `_milb_features` already enforces.
4. **Bucket mass conserved.** The 5-vector sums to 1 after any repair, and `p_bust` stays
   its first element rather than becoming an independent fit.

## 4. Gates. Pre-registered, and a miss is a NO-SHIP

These are PROBABILITY forecasts, so the metrics are proper scoring rules, not Spearman.

**Primary:** Brier score and log loss on held-out, forward-chained folds, against BOTH
baselines, because the last odds lane failed exactly here:
- the incumbent grade-only curve, and
- a CONSTANT base rate.

Beating the incumbent while losing to a constant is not a result; it is what
`xfv_odds_recalibration_ship_eval.json` already recorded (`beats_incumbent` true,
`beats_constant` false, `pass` false). Both CIs must exclude zero.

**Mandatory controls**, all four: paired bootstrap on the score gap, a zero-information
control (cohort labels shuffled across rows), a permutation null with a reported p-value,
and at least four time splits.

**Calibration, reported per cohort not just pooled:** a reliability curve with the
observed bust rate against the predicted one. The whole point is the cohort cells, so a
pooled improvement that leaves the Bradfield-shaped cell still reading 0.24 is a failure
of the stated goal even if it passes the score gates.

**Blast radius, reported and not targeted:** how many served `p_bust` values move by more
than 5 points, and the direction. Odds feed the PROSPX odds column and the star-odds
display; they do NOT feed grade, rank or surplus, which is what makes this lane safe to
attempt at all.

## 5. What would make this a NO-SHIP

- Fails to beat a constant base rate on either scoring rule, the exact failure the
  previous lane recorded.
- Gains do not survive the zero-information control or the permutation null.
- The gain is pooled-only and the motivating cohort cells do not move.
- Monotonicity repair has to move cells by more than the gain is worth, meaning the fit
  is being driven by thin-cell noise.

If it is a null it gets a loss-ledger row like every other null in this program, and the
honest conclusion is published instead: that our bust odds are calibrated to the grade
and not to the player, and readers should use the outcome-comp cohorts directly.

## 6. Explicitly out of scope

Re-keying the odds onto the pooled outcome map (measured, rejected, KEEP THE PIN) and
re-fitting the grade-only curve (measured, NULL). This lane exists because those two are
already spent.

---

# VERDICT 2026-07-31: NO-SHIP. Loss ledger.

Measured, then adversarially re-measured because the first pass reached the right answer
through wrong reasoning. Both passes are recorded; the second is the one that stands.

## The kill: the mandatory zero-information control fires

The gate made four controls mandatory. The **zero-information control** (cohort labels
shuffled across rows, 200 shuffles, pre-registered grid) settles the lane on its own.
Observed gains against the shuffled null band:

| metric | observed | shuffled-null CI95 | verdict |
|---|---|---|---|
| d_inc_brier | +0.007819 | [+0.000537, +0.010918] | **INSIDE the null** |
| d_inc_logloss | +0.007052 | [-0.011079, +0.021850] | **INSIDE the null** |
| d_const_brier | +0.015643 | [+0.008361, +0.018742] | **INSIDE the null** |
| d_const_logloss | -0.056561 | [-0.074693, -0.041764] | **INSIDE the null** |

Shuffling the cohort labels reproduces the entire gain on all four metrics. The
cohort information contributes nothing. Under section 5 that is a NO-SHIP, and it is
not a close one.

## The motivating axis WAS fit, and it also fails

The first pass tested only `age_rel_level` grids. But the motivating cells
(`data/archetype_comps.json` facets.age, edges 20 / 22 / 23.5) are cut on **absolute
age**, so the axis the whole lane exists to exploit had never actually been fit. It has
now been:

| grid | cells | d_inc_brier | CI95 |
|---|---|---|---|
| level x ABS-AGE x sign (the motivating axis) | 35 | +0.007831 | [-0.001055, +0.018863] |
| level x ABS-AGE | 19 | +0.009251 | [-0.002580, +0.021121] |
| ABS-AGE x sign | 8 | +0.011918 | [+0.001509, +0.020238] |

Two of the three include zero. The one that does not is the COARSEST, which is the tell
below.

## The gain is strictly decreasing in cell count, which inverts the hypothesis

d_inc_brier by number of cells: 1 cell **+0.0222**, 2 +0.0198, 4 +0.0139, 8 +0.0119,
19 +0.0093, 33 +0.0078, 35 +0.0078.

A ONE-CELL grid carries no cohort information at all. It is a pure global recalibration.
It beats the 33-cell pre-registered grid by **2.8x on Brier and 6.5x on log loss**, both
with paired-bootstrap CI95 clean of zero. Every cell added subtracts. H1 predicted the
opposite.

## What the defect actually is, and it is not cohorts

The incumbent's calibration slope on this subpool is **0.368** with ECE **0.201**. The
defect is SLOPE, and a per-cohort logit OFFSET can only move the intercept. That is why
the lane could never have worked as designed.

Fit a global Platt (2 parameters, ZERO cohort information) and then add the cohort
offsets on top, and the cohorts go **negative**:

| arm | Brier | log loss | vs CONST (brier / logloss) |
|---|---|---|---|
| CONST (flat base rate) | 0.239340 | 0.673560 | - |
| INC (raw incumbent) | 0.231516 | 0.737174 | +0.007824 / -0.063613 |
| INC + cohort offsets (pre-registered arm) | 0.223697 | 0.730122 | +0.015643 / -0.056561 |
| **INC + GLOBAL PLATT** | **0.189564** | **0.571016** | **+0.049776 / +0.102545** |
| PLATT + cohort offsets | 0.190273 | 0.579427 | +0.049067 / +0.094133 |

Incremental value of cohort conditioning: on the raw incumbent +0.0078 / +0.0071, on a
properly calibrated base **-0.000709 / -0.008411**. Cohorts only ever looked useful
because they were absorbing miscalibration that two global parameters absorb better.

## A correction to the first pass, so it does not enter the ledger as fact

The first pass proposed to record this lane as failing with "the identical
beats_incumbent-true / beats_constant-false signature already recorded in
`data/xfv_odds_recalibration_ship_eval.json`". **That is false and must not be
published.** That artifact records `d_const_brier +0.013289` and `d_const_logloss
+0.041014`, both POSITIVE: the earlier lane beat the constant on point estimate and
failed on CI width and the permutation null. Different failure in kind.

The first pass also charged the candidate with a log-loss loss to the constant that
**pre-exists it**: the raw incumbent loses to the same constant by -0.063613 on the same
517 rows, and the cohort head improves that to -0.056561. Blaming the candidate for an
inherited loss is not a valid falsification, which is why the controls above carry the
verdict instead.

## The honest conclusion to publish

Our bust odds are calibrated to the GRADE and not to the player, exactly as section 5
anticipated, and conditioning them on cohort does not fix it. A reader who wants to know
how a 24-year-old repeating Triple-A actually fares should use the outcome-comp cohorts
directly, which already carry the 77.1% figure. The served `p_bust` is unchanged.

## Spun out, NOT shipped here: the calibration-slope lane

The Platt row above is a real and large finding that this lane was not chartered to
make, and it clears the exact bar section 4 calls the hard one (beating a constant on
both scoring rules, +0.0498 and +0.1025). It is explicitly NOT shipped on the back of a
gate written for a different hypothesis. It gets its own pre-registration:
`ODDS_CALIBRATION_SLOPE_GATE.md`. Note it is adjacent to the already-spent "re-fit the
grade-only curve" lane but is not the same thing: that lane re-fit the CURVE, this one
leaves the curve alone and applies a two-parameter monotone recalibration to its output.
