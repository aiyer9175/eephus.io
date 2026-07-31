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
