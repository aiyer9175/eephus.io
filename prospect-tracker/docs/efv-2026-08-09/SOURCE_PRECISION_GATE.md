# SOURCE PRECISION GATE (Lane C-A1, 2026-08-09): can a source be weighted WITHOUT an outcome label?

**STATUS OF THIS FILE.** Sections 0 through 6 are the PRE-REGISTRATION, written in full
before `source_cohort_accuracy.py` existed. Section 7 is a placeholder filled in after the
run. Nothing in sections 0 to 6 is edited afterwards.

**ZERO WEIGHTS SHIP FROM THIS LANE.** No `data/source_weights.json` edit, no
`data/draft_source_weights.json` edit, no change to how the consensus is computed. The
precision estimator is measured, published with its identification conditions, and NOT
wired to anything.

---

## 0. Why a label-free route exists at all

The accuracy route (see COHORT_WEIGHT_GATE.md) needs realized bWAR, so it can only score
base years old enough to have resolved, which on this data is 2017 to 2023. Three of the six
sources in the database published their first board in 2025 or 2026. They are unscoreable on
the accuracy route for another three years no matter what is done.

A PRECISION route does not need the label. If every source is a noisy read of the same
latent quality, the sources' agreement structure alone identifies each source's noise.

## 1. The model, fixed before the run

For player `i` and source `s`:

    x_is = a_s + b_s * mu_i + e_is,   Var(mu) = 1,   e_is independent across s,   Var(e_is) = sigma_s^2

`mu` is the latent prospect quality on an arbitrary scale, fixed by the normalisation
Var(mu) = 1. `b_s` is the source's loading (how much of the true spread it expresses),
`sigma_s` its idiosyncratic noise.

INTERCEPT ABSORPTION IS REQUIRED, NOT OPTIONAL. `a_s` is absorbed by centering within
(source, base year) cells. Without it a source that changed its published FV scale between
vintages has that scale break read as variance. Baseball America is the case: its 2026
vintage sits about 11.5 FV below its 2023 to 2025 vintages against the same reference (see
section 6), and the uncentered variance is inflated accordingly. The artifact reports the
uncentered and centered variance side by side so the size of the correction is visible.

## 2. Identification, fixed before the run

TWO SOURCES ARE NOT IDENTIFIED. With two sources there are three observable second moments
(two variances, one covariance) and four unknowns (`b_1`, `b_2`, `sigma_1`, `sigma_2`). The
system is underdetermined and any split of the shared variance is consistent with the data.
The two-source case is reported as NOT IDENTIFIED, with no number attached.

THREE SOURCES ARE. With `C_st` the centered cross-covariance,

    b_1^2 = C_12 * C_13 / C_23,  and cyclic,
    sigma_s^2 = Var(x_s) - b_s^2,
    reliability_s = b_s^2 / Var(x_s).

Baseball America is the ONLY third instrument with published FVs on enough shared rows, so
the identified triad is FanGraphs, MLB Pipeline, Baseball America. That is a fact about the
database, not a preference.

HEYWOOD CHECK. `sigma_s^2 < 0` (reliability above 1) means the triad model is refuted, not
that the source is perfect. Any negative is reported as a Heywood case and the block is
marked not identified. The test asserts the fixture returns a non-Heywood solution.

## 3. The weight, fixed before the run

The optimal linear combination of noisy loadings for estimating `mu` is

    w_s proportional to b_s / sigma_s^2

NOT the naive inverse variance `1 / sigma_s^2`. The distinction is load-bearing here and the
artifact says so: a source that compresses its published range has a SMALL `b_s` and a small
raw variance, so naive inverse variance REWARDS range compression. Three of the six sources
in this database publish compressed ranges (section 5), so the naive form would upweight
exactly the sources expressing the least information.

SHEPPARD LATTICE CORRECTION. Published FVs are quantized to a 5-point lattice, which adds
`h^2/12 = 25/12 = 2.083` to every observed variance. It is reported as a SEPARATE column and
is NOT subtracted from the weight, because the served aggregator observes the QUANTIZED
grade, so the quantization noise is real noise in the quantity being combined. Subtracting
it would answer a question nobody asked (how good would the source be if it published to
arbitrary precision).

## 4. Estimator, fixed before the run

PRIMARY: EM / FIML for a multivariate normal with missing data, on the per-(source, year)
centered grades, then the closed-form triad on the EM covariance. Complete-case triad is
reported BESIDE it as the robustness check, not instead of it, because the complete-case
subsample is the rows all three sources chose to cover and that is a selected population.

Report the observed missingness PATTERN counts (which sources present, how many rows) and
the ratio of usable n to complete-case n, so the EM's leverage is visible rather than
asserted.

Uncertainty: nonparametric bootstrap over PLAYERS, B = 2000, seed 20260809, on
`alpha_fg = w_fg / (w_fg + w_mp)`. Deterministic RNG, fixed iteration order.

## 5. Sources that get a sigma and NO weight, fixed before the run

ESPN, Just Baseball and TJStats are reported with `sigma`, `n` and a `range_restricted`
flag, and NO weight is computed for them. Reason, stated before the numbers: their published
FV standard deviations are materially below FanGraphs' on the same players. Range restriction
deflates the variance and the covariance in OPPOSITE directions relative to the model, so a
triad solved with a restricted instrument in it is biased in a direction the triad cannot
detect from within.

The diagnostic that makes this checkable rather than asserted: build the 6-source
PAIRWISE-COMPLETE covariance matrix and report its eigenvalues. Pairwise-complete covariance
is not constrained to be positive semidefinite when the pairs come from different
populations. A negative eigenvalue, or any pair whose covariance exceeds the product of the
two sds (implied correlation above 1), is direct evidence that the six series are not reads
of one latent variable on one population. Both are reported.

## 6. Two structural findings that must be recorded whatever the numbers say

VINTAGE AVAILABILITY. Precision needs three sources on the SAME board year. The third
instrument's first preseason vintage is 2023. The accuracy A/B needs base years with three
years of resolved outcomes, so Y <= 2023. Report per board year whether precision is
estimable, and report the intersection with the A/B-eligible years explicitly. If the two
sets are disjoint, then a precision weight cannot be validated against an outcome on this
data at all, and the first year it could be is the first year a precision-estimable vintage
also becomes outcome-resolved. That is STRUCTURAL, not a power problem, and no amount of
additional players fixes it. This is the single most important thing this artifact says
about the label-free route.

PRECISION VERSUS ACCURACY. Across the six archetypes, correlate the precision-implied
`alpha_fg` with the accuracy-implied direction of `d_rho`. Report Pearson r and a two-sided
permutation p. PRE-REGISTERED READING: if precision and accuracy DISAGREE on the one cohort
where accuracy is resolvable, then a precision weight would have been wrong exactly where it
mattered, and that sentence goes in the artifact regardless of how the other five cells land.

CALIBRATION DRIFT TRIPWIRE. Compute each source's mean offset against a reference source on
same-quarter common slots, per year. Flag any (source, year) whose offset moves at least 3.0
FV year over year. `grade_normalization` already handles a level shift correctly, per
calendar cycle with all cells at n >= 30, so the SERVED consensus is not at risk today. What
does not exist today is DETECTION: nothing in the pipeline notices when a source rebases its
scale. That is the most likely future silent-corruption vector for the consensus, and this
block is the tripwire, not a repair.

## 6.1 lambda_k is NOT a lane, recorded before it is proposed again

`lambda_k`, a coverage-dependent shrink exponent, is recorded as NULL and closed. Four
reasons, all pre-registered:

1. Lane M4 (2026-08-08) measured coverage dependence at p 0.048 PRE-shrinkage and p 0.944
   POST-shrinkage. The incumbent `SINGLE_SOURCE_K = 0.5` already absorbs it.
2. `lambda_k` is a continuous-in-k reparameterisation of the SAME estimand M4 already tested,
   not a new one.
3. Its proposed interaction gate needs roughly n = 2000 in the k = 1 stratum. The
   outcome-resolvable window's k = 1 stratum is two orders smaller (the count is reported in
   the artifact). The live board's k = 1 count is irrelevant: those rows have no outcome.
4. Its input `sigma_pub` has no vintage estimate before 2024, so it cannot be computed on any
   year the A/B can score. Same disjointness as section 6.

## 7. RESULTS

Run 2026-08-09. Block `precision_label_free` and block `calibration_drift` of
`data/source_cohort_accuracy.json`. Basis: player-year rows over ALL snapshots (no preseason
window, per section 0's argument that precision needs no lookahead guard), per-(source,
year) mean centering. The window would have cut Just Baseball from 126 usable rows to 26 and
decided the range-restriction question by sampling instead of by measurement.

### 7.1 Missingness and the EM's leverage

Third instrument present in board years 2023, 2024, 2025, 2026. Triad patterns on those
years: FanGraphs+Pipeline 2,413; all three 1,533; FanGraphs+BA 87; Pipeline+BA 69. Usable at
at least 2 of 3 sources = 4,102. EM leverage over complete case = 2.68x.

### 7.2 Intercept absorption is worth the code

Baseball America variance reads 48.089 uncentered and 40.441 after per-(source, year)
centering, a 15.9 percent reduction. FanGraphs 29.339 to 29.169 and Pipeline 31.945 to
31.635 barely move. The correction is essentially all BA, which is exactly what section 1
predicted from a source that rebased its scale (see 7.6).

### 7.3 The estimator

EM / FIML, 82 iterations, non-Heywood, 6,072 rows:

| source | b | sigma | reliability | GLS weight |
|---|---|---|---|---|
| fangraphs | 4.352 | 3.140 | 0.658 | 0.4415 |
| mlb_pipeline | 4.578 | 3.051 | 0.693 | 0.4919 |
| baseballamerica | 4.076 | 4.798 | 0.419 | 0.1771 |

alpha_fg 0.4730, bootstrap CI95 [0.3870, 0.5436] over 200 player-bootstrap refits.

Complete case (n 1,533) as the robustness check: sigma 3.126 / 3.062 / 4.834, reliability
0.677 / 0.716 / 0.429, alpha_fg 0.4721, CI95 [0.3885, 0.5579] over 2,000 draws. The two
estimators agree to 0.0009 in alpha, so the EM's extra rows buy precision, not a different
answer.

Sheppard: h^2/12 = 2.0833, which is 21.1 / 22.4 / 9.1 percent of each source's residual
variance. Reported and NOT subtracted, per section 3.

alpha_fg's CI spans 0.5 on both estimators. **The precision route does not resolve a
preference between FanGraphs and MLB Pipeline either.**

### 7.4 The structural finding, which is the point of this file

Precision is estimable in 2023 (complete case 295), 2024 (371), 2025 (421) and 2026 (446).
All four are non-Heywood. The per-year alpha_fg is 0.496, 0.558, 0.562, 0.235: the 2026
vintage disagrees with the three before it by more than the bootstrap CI is wide, which is
the same event section 6 flags as calibration drift.

A precision weight for board year Y is vintage-legal only when an estimable year sits at or
before Y - 3, so the first board year that could carry one is 2026. The A/B can only score
board years 2017 to 2023. **THE TWO SETS ARE DISJOINT: the overlap is empty.** The first
year a precision weight can be scored against a realized outcome is 2029.

This is STRUCTURAL. It is not a power problem and no number of extra players moves it.

Correction to the pre-registration's expectation: section 6 anticipated the estimable set
starting in 2024. It starts in 2023, because Baseball America's 2023 vintage joins 295
complete-case rows. The disjointness conclusion is unchanged and the dates shift by one
year: first weightable board year 2026 rather than 2027, first A/B-able year 2029.

### 7.5 Precision versus accuracy: they disagree where it matters

| archetype | n | precision alpha_fg | accuracy d_rho |
|---|---|---|---|
| hs_bat | 205 | 0.6065 | -0.0356 |
| hs_arm | 154 | 0.5034 | -0.1195 |
| college_bat | 270 | 0.2342 | -0.0456 |
| college_arm | 388 | 0.5384 | -0.0060 |
| intl_bat | 356 | 0.5569 | +0.0069 |
| intl_arm | 155 | 0.2632 | +0.0607 |

Pearson r -0.2733, exact permutation p 0.5931 over all 720 orderings. No relationship.

THE ONE CELL WHERE ACCURACY IS RESOLVABLE IS HS ARMS, and there precision points to
FanGraphs (alpha_fg 0.5034) while accuracy says MLB Pipeline by 0.1195 rho. **A precision
weight would have been wrong exactly where it mattered.** Emitted as
`precision_vs_accuracy.on_the_resolvable_cells`.

### 7.6 The restricted instruments

Centered sd: ESPN 3.831 (n 216), Just Baseball 3.879 (n 126), TJStats 3.781 (n 155), against
FanGraphs 5.751 and Pipeline 5.518. Ratios 0.657 to 0.674. All three flagged
`range_restricted`. NO WEIGHT COMPUTED for any of them.

The pre-registered non-PSD diagnostic DID NOT FIRE on this vintage. The 6-source
pairwise-complete centered covariance has eigenvalues 0.856, 1.338, 6.729, 19.820, 20.416,
98.827, all positive, and no pair has an implied correlation above 1 (the largest,
FanGraphs against Just Baseball, is 0.637). That expectation is retracted.

The swap diagnostic, which section 5 registered as the checkable version of the claim, DOES
fire and is stronger:

| third instrument | b_fangraphs | reliability_fangraphs | reliability_third | n vs FG |
|---|---|---|---|---|
| baseballamerica | 4.628 | 0.648 | 0.397 | 1,620 |
| espn | 5.745 | 0.998 | 0.347 | 216 |
| just_baseball | Heywood | Heywood | Heywood | 125 |
| tjstats | 5.540 | 0.928 | 0.406 | 152 |

FanGraphs' own reliability moves from 0.648 to 0.998 depending only on which instrument
completes the triad, and the Just Baseball triad is refuted outright. If the six series were
reads of ONE latent variable on ONE population, `b_fangraphs` would not depend on the third
column. A reliability of 0.998 is not a finding about FanGraphs; it is the range-restricted
instrument absorbing the shared variance. That is the reason no weight is computed for
ESPN, Just Baseball or TJStats, and it is measured rather than asserted.

### 7.7 Calibration drift: the tripwire fires once

Offsets against FanGraphs on same-quarter common slots.

| source | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| mlb_pipeline | +3.793 | +3.765 | +3.309 | +3.937 |
| baseballamerica | +5.646 | +6.779 | +6.502 | -0.489 |
| espn | | | +1.620 | +1.812 |
| just_baseball | | | | +1.186 |
| tjstats | | | | +2.165 |

ONE flag: Baseball America, 2026, move -6.991 FV in a single cycle. MLB Pipeline is stable
to within 0.63 FV across ten years, which is what an unflagged source looks like.

Preseason-only (Q1) detail, which is the vintage-comparable series: BA runs +5.112, +6.864,
+6.727, +1.310 for 2023 to 2026, a -5.42 FV move into 2026. The mixed-quarter series above
is larger because BA's 2026 midseason boards sit lower still (2026 Q2 -1.772, Q3 -1.759).

`grade_normalization` absorbs this correctly today, per calendar cycle with all cells at
n >= 30, so the SERVED consensus is fine. Nothing DETECTS it. That gap is what this block
closes, and it is the reason the 2026 per-year precision alpha (0.235) departs from the
three vintages before it.

### 7.8 lambda_k

Recorded NULL and not a lane, with the counts section 6.1 asked for: the k = 1 stratum is
514 of 2,044 deduped players in the outcome-resolvable window, against roughly n 2,000
needed for the proposed interaction gate, and 3,363 of 4,623 on the live board where there
is no outcome. Its input `sigma_pub` has no vintage estimate before 2023, so it cannot be
computed on any year the A/B can score. Correction to the pre-registration: the resolvable
k = 1 count is 514, not the two-orders-smaller number the lane brief assumed. It is still
3.9x short of the gate, and reasons 1, 2 and 4 are untouched.

### 7.9 Verdict

Precision is estimable, the EM works, and the answer it gives (alpha_fg 0.473, CI spanning
0.5) is that the two scoreable sources are indistinguishable on precision as well as on
accuracy. Even if it had given a sharp answer, it could not be validated against an outcome
before 2029, and on the one cohort where accuracy is resolvable it points the wrong way.
NO WEIGHT SHIPS FROM THIS ROUTE.
