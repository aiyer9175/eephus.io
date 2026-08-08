# RANK / AUC GATE (lane I1 + I2 + I3, 2026-08-07b)

**Status: PRE-REGISTRATION. Parts 0 to 6 were written in full BEFORE
`tools/efv_rank_objective_lab.py` existed and before any arm was run. Part 7 is a
placeholder filled from the artifact after the run, and nothing above part 7 may be
edited after the first run.**

Producer `python tools/efv_rank_objective_lab.py all`, ledger
`data/xfv_rank_objective_eval.json`, seed 20260807.

---

## 0. What this lane is and what it is not

The eFV rank frontier is CLOSED for FEATURE COMPOSITION. Six programs, six driver arms,
six nulls, four point-negative. `EFV_GATE_STANDARD.md` section 6 says do not add and do
not remove features on sub-floor evidence, and this lane adds none and removes none.

The three arms here are **loss-function and weighting** changes, which section 6 does not
bar and which no prior program has measured:

| arm | mechanism | what production does today |
|---|---|---|
| I1 | the FIT TARGET the ridge minimizes squared error on | raw first-6yr summed bWAR |
| I2 | a classifier fit DIRECTLY to the AUC thresholds | nothing in the stack is fit to either bar |
| I3 | the FIT SAMPLE WEIGHTS | `observed_seasons/6` |

The closed ledger already contains monotone LightGBM, a ridge/GBM stack and a two-part
P(MLB) x E(WAR|MLB) model. It does NOT contain "same features, same ridge, transformed
target", "a direct threshold classifier", or "a weighting scheme compared against
alternatives".

**The expected outcome is NULL on all three. A null is a successful lane.** The value is
that these are the last untested mechanisms: closing them converts "we think we are at
the ceiling" into "we measured the ceiling on every axis we have".

This lane changes NO shipped constant, retires nothing, reopens no closed arm, and
retroactively resolves no past null. It owns exactly three new files.

---

## 1. Basis, pools, and the protocol

Fold arithmetic is `tools/efv_mde_lab.py`'s numpy replica (`ridge_fit`, `ridge_pred`,
`ols_fit`, `wrho`), which carries verified bit-parity with the shipped
`efv_model._run_eval` chain. Pools are `tools/efv_cohort_floor_lab.load_pool`, which
matches `efv_model.run()`.

- **11 forward-chained folds**, `efv_model.SCORED_YEARS` = 2014 to 2024. Guards
  `n_test >= 15`, `n_train >= 60`.
- **PRIMARY pool: `full_pool_km`** (debuted + busts minus recent busts, KM-censored
  target). Chosen before measurement for two reasons that are both structural: it is the
  frame `fit_production_stack` actually fits the SERVED model on, and it is the only
  frame that carries the zero point mass I1 is about (the debuted pool has 3 exact zeros
  per side; the full pool has 1,041 hit / 1,002 pit). It is also the power lane's
  registered primary.
- **SECONDARY pool: `debuted_km`**, reported for every arm as a sensitivity.
- Both sides (hit, pit) are separate models and are reported separately. Lambda is the
  live stamped value, hit 0.70 / pit 0.57.
- Scoring is pair-weighted pooled Spearman with the production weight
  (`observed_seasons/6`). **The SCORING weight never changes, in any arm, including I3.**
  Only the FIT changes. An arm that changed the metric would not be comparable to
  anything.

### 1.1 Legs

`blend = (1 - lam) * max(0, consensus_OLS(fv)) + lam * ridge`.

- **PRIMARY leg: `blend`.** It is what ships.
- **SECONDARY leg: `ridge`.** It is where every arm's mechanism actually lives; the blend
  dilutes it by lam.

### 1.2 The I1 baseline problem, settled in advance

A transformed-target ridge predicts on the transformed scale, so blending it with a
WAR-scale consensus at a fixed lambda is arithmetically meaningless. Every I1 arm
therefore appends a **train-fold-only linear map back to WAR**
(`efv_model._fit_linear_calibration`, fit on train rows, applied to test rows).

Production does not have that map on the eval chain. So the transform and the map would
be two changes at once. This is resolved by construction:

- The **ridge leg** is rank-invariant to a positive affine map, so the ridge-leg delta is
  a clean transform effect measured against raw production. A `recal_identity` arm must
  return a ridge-leg delta of **exactly 0.00000** against production; that is a plumbing
  check, it is not a control, and it is declared as such.
- The **blend leg** is NOT invariant to the map. So **the blend-leg baseline for I1 is the
  `recal_identity` leg**, not raw production. The delta against raw production is also
  reported, and where the two disagree the `recal_identity` comparison is the one that
  gates.

---

## 2. The registered arms. One attempt each, no re-runs.

### I1, the fit target (features unchanged)

The target is right-skewed with a large point mass at 0 and the gate metric is a rank
correlation, so squared loss concentrates its weight exactly where the gate does not
look. The prior pointing the right way: the FV55+ tier is over-predicted in level, 10.4
predicted against 7.7 realized.

| id | transform of the TRAIN target |
|---|---|
| `T0 recal_identity` | g(y) = y, plus the train-fold linear map (the I1 blend baseline) |
| `T1 signed_log1p` | g(y) = sign(y) * log1p(abs(y)) |
| `T2 rank_normal` | van der Waerden: g(y) = Phi^-1((rank_train(y) - 0.5) / n_train) |

`signed_log1p` rather than plain `log1p` because the target GOES NEGATIVE (min -5.20 hit,
-5.34 pit), so `log1p` is undefined on 324 hit / 382 pit rows and `log1p(max(0,y))` would
destroy the ordering of every negative row, making it a rank-DESTROYING transform rather
than the rank-identical relabel the arm is about. The signed form is strictly monotone on
all of R and coincides with `log1p` on y >= 0.

Both transforms are computed on the TRAIN fold only. Test rows are never transformed:
scoring is always against raw y.

### I2, AUC as its own objective (an ADDITIONAL rater, never a replacement)

| id | fit |
|---|---|
| `A1 clf_contributor` | weighted logistic ridge on 1[y >= 3.0] |
| `A2 clf_star` | weighted logistic ridge on 1[y >= 10.0] |

Same feature spec, same standardization, same production weights, penalty chosen by the
same seeded 5-fold CV the production ridge uses (weighted log-loss). Fit forward-chained
on the same folds. Scored against BOTH bars and against pooled rho, beside the shipped
blend and the consensus anchor, on identical rows and identical labels.

AUC is `source_backtest._auc` (Mann-Whitney U, ties 0.5), unweighted, which is what
`efv_model._auc_breakdown` publishes.

### I3, sample weighting (fit weights only)

| id | fit weight |
|---|---|
| `W1 uniform` | 1.0 for every row (what the fit did before 2026-07) |
| `W2 sqrt` | sqrt(observed_seasons / 6) |
| `W3 ipcw` | resolved rows only, 1 / P(resolved) capped at 5.0, P estimated inside the TRAIN fold in (fold-year, nearest-5 FV) cells with a (fold-year) fallback below 5 rows, mirroring `efv_model._sf_ipcw_weights` |

**The label interaction is not double-counted.** If the censored label is biased, the
weight and the label are two corrections to the SAME problem. So I3 is scored against the
production label only, and any I3 result is reported jointly with I2's censoring
measurement rather than added to it.

---

## 3. The controls. Each one names the result that would fail it.

### 3.1 Paired bootstrap, BOTH registered estimators (mandatory, section 2 clause 1)

B = 2000, seed 20260807, paired: the arm and its baseline are scored on the SAME
resample every draw.

- **E_refit**: resample the whole pool (train AND test), refit both legs on every draw.
- **E_cond**: fits held fixed from the real chain, resample the scored rows, both legs
  scored on the same resampled indices.

MDE95 is ONE-SIDED (1.645 sd), the convention of `EFV_GATE_STANDARD.md` sections 1 and 7.
Two-sided is also reported. **Each arm's floor is derived from its own bootstrap on its
own rows.** No floor is borrowed from another experiment; in particular
`XFV_VS_CONSENSUS_MDE95` = 0.044 is a MODEL-VS-CONSENSUS refit floor and is not usable
for an arm-vs-production paired delta.

The two estimators answer different questions and neither is authoritative alone. Where
they disagree, the disagreement IS the finding.

### 3.2 Zero-information control and permutation null band (clauses 2 and 3)

One construction per arm serves both roles, and this doc says so rather than counting one
thing twice silently: the **single matched twin** is clause 2, the **K = 200 draw
distribution of that twin** is clause 3.

| arm | zero-information twin | what would fail it |
|---|---|---|
| I1 | `monotone_warp`: a RANDOM strictly monotone warp of the train target (Dirichlet increments on the quantile scale, mapped back through the train y range). Identity is the centre of the family. | If `signed_log1p` / `rank_normal` sit inside the warp band, then ANY rank-identical relabel of the fit target moves rho as much as the registered transforms do, and there is no result. |
| I2 | `label_permuted`: the classifier fit on row-permuted binary labels, scored against the real ones. | If the permuted classifier's AUC is not near 0.50, the classifier is reading something other than the label. If the real classifier's AUC margin over the blend sits inside the permuted band, there is no result. |
| I3 | `weight_permuted`: the production weight vector permuted across rows. Identical marginal, no link to censoring. | If a permuted weight vector moves rho as much as `uniform` / `sqrt` / `ipcw` do, then weighting carries no information and every I3 arm is noise. |

Additionally, a **shared reference band** is reported for all three arms: five pure-noise
N(0,1) columns appended to the ridge, the construction `tools/efv_driver_lab.py`
`floor_mode` uses. This is a zero-information change to the FIT, so it answers the dumbest
available alternative explanation for any arm's delta: "a change to the fit of this size
moves pooled rho by this much regardless of what the change is."

### 3.3 Time splits (clause 4)

Per-fold delta over the 11 forward-chained folds, with the sign count and the cross-fold
mean. A pooled gain with no fold majority behind it is a pooling artifact (this is the
exact reading that closed the C4a pitcher arms at 0/11 and 1/11).

### 3.4 The live-robustness clause

Both the production stack and the arm stack are fit on the FULL production training frame
(`fit_production_stack`'s pool: full minus recent busts) and both score the LIVE matrix.
Reported: Spearman(old, new), median / p99 / max absolute rank shift, max absolute WAR
delta, and the top movers with their consensus FV.

**Registration note on staleness.** The served eFV matrices are known stale (they
reproduce `consensus_fv_raw` on 74.8 percent of rows). The consequence is bounded and
stated rather than ignored: the live clause measures movement of the CURRENT served board.
A stale board understates movement if a refresh would spread the grades, so the live
numbers here are a LOWER bound on blast radius, which is the conservative direction for a
clause used to disqualify.

---

## 4. PASS clauses. Marginal is FAIL.

### 4.1 A rank arm (I1 and I3) is ship-eligible only if ALL of:

- **P1** `|delta| >= MDE95_onesided` under **BOTH** E_refit and E_cond, same sign, on the
  BLEND leg, on the PRIMARY pool.
- **P2** The block-rho delta has the SAME SIGN as the pooled-rho delta. A sign
  disagreement between the two registered instruments is a FAIL before magnitude is
  considered.
- **P3** Fold majority: strictly more than 6 of the 11 forward-chained folds positive.
- **P4** The delta exceeds the p95 of its own zero-information band, signed, in the
  candidate's direction.
- **P5** It survives Bonferroni over the registered primary family, k = 10 (5 rank arms
  x 2 sides), one-sided z = 2.5758.
- **P6** Live robustness: Spearman(old, new) >= 0.999 AND max absolute rank shift <= 100
  places, on BOTH sides.

### 4.2 An I2 AUC claim is ship-eligible only if ALL of:

- **Q1** `classifier_AUC - blend_AUC >= MDE95_onesided` under BOTH estimators, on the bar
  the classifier was fit to, on the debuted pool.
- **Q2** The **carve-out admissibility check passes** (section 5). If it fails, the AUC is
  INADMISSIBLE for this candidate class and I2 reports on rank only.
- **Q3** The **censoring check** does not flip the verdict: the same comparison run on the
  resolved-only subset must reach the same verdict. If censored and resolved disagree, the
  AUC verdict is UNRESOLVED, not a win.
- **Q4** The margin exceeds the p95 of the `label_permuted` band.
- **Q5** The permuted-label control's own AUC is inside [0.45, 0.55]. If it is not, the
  instrument is broken and no I2 number may be read.

### 4.3 Self-added thresholds, declared here

These are MY thresholds, not inherited ones. Each is listed in the headline if it
determines a verdict:

1. Live-robustness bound: **Spearman(old,new) >= 0.999 and max abs rank shift <= 100**.
2. Fold majority: **> 6 of 11**.
3. Control band bar: **p95**, signed.
4. Carve-out operational bar (section 5): missingness-indicator standalone AUC inside
   **[0.45, 0.55]** and label positive-rate ratio between missing and non-missing rows
   **below 2.0x**.
5. Bonferroni family size **k = 10** (primary pool only; k = 20 including the secondary
   pool is also reported).

---

## 5. The carve-out that has to be checked FIRST

`EFV_GATE_STANDARD.md` lines 110 to 133 make the full-pool debut / no-debut AUC
INADMISSIBLE for any candidate that can sense a missing MiLB block, because a row with no
MiLB block is the same row as a row with no resolved mlbam id 96.4 / 94.4 percent of the
time, and identity resolution is far easier for players who reached MLB. Six archetype
arms read as wins under that metric and all six were rank nulls.

**The hitter feature spec contains `milb_missing`. The candidate class therefore CAN
sense missingness and the carve-out is live, not hypothetical.**

The contributor and star AUCs are computed on the DEBUTED pool, where the label is a WAR
threshold rather than debut itself, so they are probably not subject to it. That is a
hypothesis and this lane tests it rather than asserting it:

- **C-I2a** `milb_missing` rate on the debuted pool, per side.
- **C-I2b** Standalone AUC of the missingness indicator against the contributor label and
  against the star label, on the debuted pool. **Admissible only inside [0.45, 0.55].**
- **C-I2c** Positive rate of each label among missing rows against non-missing rows.
  **Admissible only below a 2.0x ratio.**
- **C-I2d** The same AUC restricted to the TRACK-RECORD population (rows that HAVE a MiLB
  block), which the gate standard names as an admissible substitute. If the verdict
  differs between the full debuted pool and the track-record subset, the full-pool number
  is discarded.

## 5.1 The censored star class, quantified

Wave 1 measured that the star positive class is CENSORED: the WAR >= 10 bar loses about
40 percent of its true positives at `observed_seasons = 2`. Any star AUC on a frame
carrying 2023 to 2024 debuts is scored against a mutilated positive class.

This lane re-measures on ITS OWN frame and reports:

- rows whose contributor class differs between `target_censored` and `target_resolved`;
- the same for the star class;
- positive counts under each label;
- the AUC comparison re-run on resolved-only rows (clause Q3).

---

## 6. What each outcome means

- **All three NULL.** The expected result. The lane closes the last three untested rank
  mechanisms and the ledger records the measured margins, so the next program does not
  re-open them on a hunch. This is a successful lane.
- **An arm PASSES all clauses.** Report it as a measured candidate with its margin, its
  estimator disagreement if any, its live blast radius, and its multiplicity position.
  It is NOT shipped by this lane, which owns no production file.
- **An arm is point-positive but sub-floor.** It is a NULL. Not a small win, not a
  directional signal, not a fringe gain.
- **The estimators disagree.** Report both, name which question each answers, and call
  the cell UNRESOLVED rather than choosing the flattering one.

Multiplicity is reported across all three arms jointly, at the full family size, and the
family is not narrowed after the fact to make anything pass.

---

## 7. RESULT (appended after the run)

Ledger `data/xfv_rank_objective_eval.json`. Every number below reproduces from it.
Nothing above this line was edited after the run.

### 7.0 Headline

**All three arms are NULL. Twenty of twenty rank cells fail the PASS clauses, zero pass.
The only cells that resolve at all in the entire lane are LOSSES: log-transforming the
hitter target, and the direct AUC classifier on both sides.** The rank frontier is now
closed on target choice, on objective choice and on sample weighting, not only on
feature composition.

Two things that were NOT expected and are reported as findings rather than footnotes:

1. **A pre-registered plumbing clause FAILED** (7.2). It was stated at the wrong level
   of aggregation. The mechanism is identified, the consequence is bounded, and the
   registration is not amended.
2. **The contributor / star AUC is admissible on the DEBUTED pool and INADMISSIBLE on
   the FULL pool**, measured (7.3). That extends `EFV_GATE_STANDARD.md`'s carve-out to a
   metric the carve-out did not name, and it is the reason the classifier's sign flips
   between the two pools.

**The nulls are informative, not inert.** A post-hoc liveness control (7.2b, disclosed as
post-hoc because it could only damage this lane) points the identical battery at blanking
`fv` and it fires on 3 of 4 cells under BOTH estimators, at 2.1x to 3.9x the largest
ridge-leg delta any arm here produced.

**Self-added thresholds did not decide anything.** The live-robustness bound
(Spearman >= 0.999, max shift <= 100) fails on all ten arm-side cells, but every one of
those cells already fails P1 on its own floor, so the bound is corroboration and not the
decisive clause. Same for the fold-majority bar and the Bonferroni family: no cell
reaches its own UNADJUSTED floor in the winning direction anywhere, so no multiplicity
correction is load-bearing.

### 7.1 Parity, run first

| check | result |
|---|---|
| vectorized `rankavg` / `wrho` / `block_norm` vs the shipped `efv_mde_lab` ones, real scored vectors, all 4 pools | max abs diff **0.0** on every pool (n 1,792 / 755 / 1,885 / 890) |
| pooled blend rho vs `efv_mde_lab.chain` | identical to 1e-12, hit 0.39933, pit 0.25606 |
| pooled blend rho vs the shipped artifact | hit 0.3993, pit 0.2562 (artifact is 4dp) |
| `_auc_np` vs `source_backtest._auc`, with and without ties | equal to 1e-12 |
| Acklam Phi^-1 vs the scalar-erf Newton reference, 4,000 points | max abs diff **3.65e-9** |

Two implementation deviations from a naive build are recorded in the lab and both are
arithmetic-neutral: the vectorized rank (the shipped Python tie-loop raised a Windows
access violation after roughly 1e5 calls and killed four runs) and the vectorized
Phi^-1 (the erf-Newton form is about 2e9 scalar calls per arm).

### 7.2 The pre-registered plumbing clause FAILED. Recorded, not amended.

Section 1.2 registered: *a `recal_identity` arm must return a ridge-leg delta of exactly
0.00000 against production, because a positive affine map cannot reorder.*

Measured pooled ridge-leg delta, `recal_identity` minus production:

| cell | pooled ridge rho delta | max WITHIN-fold ridge rho delta |
|---|---|---|
| hit.full | +0.000095 | **0.000e+00** |
| hit.debuted | +0.000421 | **0.000e+00** |
| pit.full | **-0.002060** | **0.000e+00** |
| pit.debuted | -0.001830 | **0.000e+00** |

**The clause is false as written and true one level down.** Within each fold the delta is
exactly zero, so the affine-invariance reasoning is correct. The pooled figure moves
because each of the eleven folds receives its OWN affine map, so cross-fold ordering
shifts. That is precisely the mechanism `efv_model._lofo_calibrate`'s corrected docstring
records, and this lane walked into it anyway.

Consequence, bounded: **no verdict changes.** Every I1 arm is gated against
`recal_identity`, not against raw production, exactly as section 1.2 required, so the
artifact is differenced out of every I1 number. Its size (max 0.00206) is 12% of the
largest I1 blend-leg delta and 7% of the largest ridge-leg delta.

### 7.2b Harness liveness. A POST-HOC control, added because it could only hurt.

**Not pre-registered. Added after the arms were measured, and disclosed as such.** The
reason it is here: a lane whose product is twenty NULL verdicts is worthless if the
harness cannot fire at all, and nothing in parts 0 to 6 tested that. The control can only
damage this lane's conclusions, never flatter them, which is why adding it late is
defensible where adding a PASS clause late would not be.

Same `gate_arm` battery, same B = 2000, same pools, pointed at a change that is known to
be resolvable: blanking `fv`, the one feature `EFV_GATE_STANDARD.md` section 6 calls
individually resolvable and the cell `POWER_GATE.md` 3.1 uses as its amended detection
primary. Expected direction is a resolvable LOSS on the ridge leg.

| cell | ridge-leg delta | E_refit | E_cond | blend-leg delta |
|---|---|---|---|---|
| hit.debuted | **-0.06021** | 1.343x RESOLVABLE LOSS | 1.766x RESOLVABLE LOSS | -0.02073 |
| pit.full | **-0.05679** | 1.634x RESOLVABLE LOSS | 1.878x RESOLVABLE LOSS | -0.01731 |
| pit.debuted | **-0.05597** | 1.114x RESOLVABLE LOSS | 1.447x RESOLVABLE LOSS | -0.00794 |
| hit.full | -0.02372 | 0.755x NULL | 0.891x NULL | +0.00301 |

**The harness is live: 3 of 4 cells fire on the ridge leg under BOTH estimators.** The
effects it detects are 2.1x to 3.9x the largest ridge-leg delta any arm in this lane
produced (-0.02849). So the twenty nulls are informative: this battery resolves an effect
of the size a real lever would have, and none of the three arms is that size.

The blend leg is muted exactly as `POWER_GATE.md` 3.1 predicts, and on hit.full it even
turns positive (+0.00301) while the ridge leg loses -0.02372. That is the documented
mis-specification, not a finding: the blend keeps `fv` at weight (1 - lambda) through the
consensus OLS anchor no matter what the ridge does. It is reported because it is also the
reason the blend leg is the conservative primary for arms whose mechanism lives in the
ridge.

### 7.3 The carve-out, run before any AUC number was read

Measured on the RAW row ("no pre-decision MiLB production block",
`efv_model._vec:1171`), not on the feature list. That distinction matters: the pitcher
spec contains no `milb_missing` feature, so a check that read the feature list would have
inspected an empty set on the pitcher side and reported a pass that could not have
failed. On the raw indicator the pitcher side has 288 of 981 debuted rows missing.

| pool | rows with no MiLB block | indicator AUC vs contributor | vs star | verdict |
|---|---|---|---|---|
| hit.debuted | 264 / 845 (31.2%) | 0.5010 | 0.5140 | **ADMISSIBLE** |
| pit.debuted | 288 / 981 (29.4%) | 0.5340 | 0.5327 | **ADMISSIBLE** |
| hit.full | 768 / 1,883 (40.8%) | **0.4432** | 0.4610 | **INADMISSIBLE** |
| pit.full | 975 / 1,980 (49.2%) | **0.4144** | **0.4290** | **INADMISSIBLE** |

Positive-rate ratios between missing and present rows are 1.006 to 1.323 on the debuted
pools and 1.363 to 1.853 on the full pools, all under the 2.0 bar, so the AUC leg is what
fails.

**This is a new result, not a restatement.** The gate standard's carve-out names the
full-pool debut / no-debut AUC. It did not name contributor / star AUC. Measured, that
metric inherits the same defect on the FULL pool and is clean on the DEBUTED pool, which
is why Q1 registered the debuted pool. It is also why the classifier's margin changes
sign between the two pools (7.6).

C-I2d, the gate standard's own admissible substitute (track-record rows only), reproduces
the debuted verdict's SIGN in all four debuted cells, so nothing is discarded there.

### 7.4 The censored positive class, measured on this frame

| side | bar | positives, censored label | positives, resolved label | rows changing class | share of censored positives lost |
|---|---|---|---|---|---|
| hit | >= 3 | 322 | 281 | 41 | 12.7% |
| hit | >= 10 | 140 | 114 | **26** | **18.6%** |
| pit | >= 3 | 259 | 214 | 45 | 17.4% |
| pit | >= 10 | 62 | 47 | **15** | **24.2%** |

Rows with `observed_seasons <= 2`: 91 hit / 119 pit. Among them the class changes are 18
hit / 18 pit at the contributor bar and **5 hit / 1 pit** at the star bar.

**The wave-1 figure does not reproduce on this frame and the discrepancy is reported
rather than smoothed.** Wave 1 recorded that the star bar loses about 40 percent of its
true positives at `observed_seasons = 2` (136 true against 82 projected). Here the
pool-wide loss is 18.6% / 24.2%, and the `observed_seasons <= 2` rows contribute only 5 of
the 26 hitter changes and 1 of the 15 pitcher changes. The two are different frames
(this is the eFV matrix debuted pool, 845 / 981 rows) and this lane did not reconcile
them; the number to use for an eFV-matrix star AUC is the one in the table above.

Q3, the clause that matters: **the verdict does not flip under the resolved label.** Both
cells that resolve as losses stay losses (hit.debuted contributor -0.0321 censored,
-0.0326 resolved; pit.debuted contributor -0.0205, -0.0127). The one sign change,
hit.debuted star -0.0101 to +0.0020, happens inside a cell that is NULL under both
labels, so no verdict depends on the censoring choice.

### 7.5 I1, the fit target. NULL, and the resolvable direction is DOWN.

Blend leg, primary. Baseline `recal_identity`.

| cell | delta pooled | delta block | delta ridge leg | folds won | E_refit | E_cond |
|---|---|---|---|---|---|---|
| hit.full signed_log1p | **-0.01273** | -0.01378 | -0.01543 | 3/11 | 0.635x NULL | **1.231x RESOLVABLE LOSS** |
| hit.full rank_normal | -0.00673 | +0.00217 | -0.01168 | 6/11 | 0.260x NULL | 0.456x NULL |
| pit.full signed_log1p | -0.00216 | -0.00253 | -0.00311 | 3/11 | 0.159x NULL | 0.343x NULL |
| pit.full rank_normal | -0.01056 | -0.00685 | -0.01431 | 3/11 | 0.513x NULL | 0.700x NULL |
| hit.debuted signed_log1p | **-0.01657** | -0.02029 | **-0.02849** | 2/11 | 0.510x NULL | **1.075x RESOLVABLE LOSS** |
| hit.debuted rank_normal | -0.00387 | -0.01429 | -0.01013 | 5/11 | 0.115x NULL | 0.274x NULL |
| pit.debuted signed_log1p | +0.00002 | -0.00213 | +0.00235 | 5/11 | 0.001x NULL | 0.001x NULL |
| pit.debuted rank_normal | +0.00165 | -0.00030 | +0.00316 | 5/11 | 0.077x NULL | 0.127x NULL |

- **No arm wins a fold majority anywhere.** Best is 6 of 11, which does not clear the
  registered bar of strictly more than 6.
- **The estimators disagree on exactly two cells**, both `signed_log1p` on hitters. Under
  the registered joint clause they are NULL. The honest reading is the one section 7.1 of
  `POWER_GATE.md` demands: *conditional on this training corpus*, log-transforming the
  hitter target is a resolvable LOSS, and *over redraws of the corpus* it is not
  resolvable either way.
- **The zero-information control bites in the informative direction, on two cells, and
  one of them is width-sensitive. Both facts are reported.** At the registered k = 20
  width, `hit.debuted signed_log1p` (-0.01657) sits BELOW the warp band's p05 of -0.01347
  and `pit.full rank_normal` (-0.01056) sits below its p05 of -0.00367: those two
  transforms are worse than 95% of arbitrary smooth monotone relabels of the same target.
  **`hit.debuted signed_log1p` does NOT clear that bar at k = 5** (p05 -0.01813, so the
  arm is inside the band there); it does at k = 20 and k = 50. `pit.full rank_normal` is
  below p05 at all three widths. The other six I1 cells are inside the band at every
  width.
- **The band width is reported rather than tuned.** Across 5, 20 and 50 knots its p95
  moves by at most **0.00256** (largest spread, pit.debuted: +0.00822 / +0.01078 /
  +0.00929; hit.full: +0.01154 / +0.00996 / +0.01023). No arm's PASS/FAIL verdict depends
  on the width, because no arm is positive; only the descriptive "worse than a random
  relabel" reading moves, and that movement is stated above rather than hidden.
- The prior that motivated the arm (FV55+ over-predicted in level, 10.4 against 7.7) is
  not refuted as a LEVEL claim. What is refuted is the inference from it: moving squared
  loss off the right tail does not buy rank, and on hitters it costs rank.

### 7.6 I2, AUC as its own objective. The classifier loses to the blend it was meant to beat.

Registered pool: DEBUTED (Q1). All four admissible cells:

| cell | consensus AUC | blend AUC | classifier AUC | clf - blend | E_cond | E_refit |
|---|---|---|---|---|---|---|
| hit.debuted, WAR >= 3 | 0.7439 | 0.7477 | 0.7156 | **-0.03213** | **2.117x RESOLVABLE LOSS** | **1.267x RESOLVABLE LOSS** |
| hit.debuted, WAR >= 10 | 0.8145 | 0.8233 | 0.8132 | -0.01012 | 0.641x NULL | 0.290x NULL |
| pit.debuted, WAR >= 3 | 0.6944 | 0.6969 | 0.6764 | -0.02045 | **1.137x RESOLVABLE LOSS** | 0.816x NULL |
| pit.debuted, WAR >= 10 | 0.8167 | 0.8200 | 0.7939 | -0.02619 | 0.851x NULL | 0.432x NULL |

**A logistic ridge fit DIRECTLY to the threshold beats neither the shipped blend nor the
consensus anchor on that threshold, on either side, at either bar.** All four margins are
negative; two resolve as losses. Its pooled rank rho is worse too (hit.debuted 0.3407 at
the contributor bar and 0.3942 at the star bar, against the blend's 0.3993).

The full-pool cells go the other way (hit +0.00598 and +0.00376, both NULL at 0.479x and
0.245x) and **that pool is inadmissible by 7.3**. The direction reversal between an
admissible and an inadmissible pool, on the same model and the same bars, is the
carve-out's signature and is reported as such rather than as a hint of a win.

Controls: the permuted-label classifier scores AUC 0.5094 / 0.5229 (hit) and 0.5114 /
0.5049 (pit), all inside the registered [0.45, 0.55], so Q5 passes and the instrument is
sound. Q4's band (`vs_blend` p95 around -0.15 to -0.23) is trivially cleared by any real
margin; that clause is weak by construction and is reported as weak rather than as a
control that passed.

### 7.7 I3, sample weighting. Unresolvable, in both directions.

| cell | delta pooled | folds won | E_refit | E_cond |
|---|---|---|---|---|
| hit.full uniform | +0.00018 | 1/11 | 0.220x | 0.284x |
| hit.full sqrt | +0.00009 | 1/11 | 0.193x | 0.266x |
| hit.full ipcw | +0.00039 | 1/11 | 0.123x | 0.157x |
| pit.full uniform | +0.00039 | 2/11 | 0.449x | 0.671x |
| pit.full sqrt | +0.00027 | 1/11 | 0.583x | 0.834x |
| pit.full ipcw | -0.00156 | 2/11 | 0.314x | 0.382x |
| hit.debuted uniform / sqrt / ipcw | -0.00009 / -0.00002 / -0.00049 | 1/11 each | 0.047x / 0.014x / 0.077x | 0.102x / 0.030x / 0.113x |
| pit.debuted uniform / sqrt / ipcw | +0.00004 / -0.00011 / -0.00082 | 0/11, 0/11, 1/11 | 0.024x / 0.134x / 0.124x | 0.035x / 0.189x / 0.165x |

Every cell NULL, the largest at 0.834x of its own floor, and the largest absolute delta
in the whole arm is 0.00156, a LOSS.

**The zero-information control is decisive here.** Permuting the production weight vector
across rows, keeping its marginal and destroying its link to censoring, moves the blend
leg with p95 +0.0080 (hit.full and hit.debuted), +0.0060 (pit.debuted) and +0.0023
(pit.full). **Every real I3 arm sits inside that band.** A weight vector with the right
marginal and the wrong rows perturbs pooled rho by MORE than the production scheme
differs from uniform, sqrt or IPCW.

The correct reading is therefore neither "the weighting is right" nor "the weighting is
wrong": at these n the fit weighting is **not measurable on rank**, and
`observed_seasons/6` is neither vindicated nor indicted. Consistent with the section 2
warning, I3 is not credited alongside I2's censoring measurement: the two would be
corrections to the same problem and only one of them, the label, is measurable at all.

### 7.8 The live-robustness clause. Every arm fails it, and it decided nothing.

Both legs fit on the production training frame, both scoring the live matrix.

| arm | side | rho(old, new) | median shift | p99 | max | clause |
|---|---|---|---|---|---|---|
| I1.rank_normal | hit | **0.7986** | **193** | 976 | **1152** | FAIL |
| I1.rank_normal | pit | 0.8610 | 178 | 1047 | **1522** | FAIL |
| I1.signed_log1p | hit | 0.9722 | 65 | 461 | 591 | FAIL |
| I1.signed_log1p | pit | 0.9934 | 40 | 278 | 522 | FAIL |
| I3.ipcw | hit | 0.9777 | 51 | 426 | 722 | FAIL |
| I3.ipcw | pit | 0.9625 | 93 | 583 | 1030 | FAIL |
| I3.uniform | hit | 0.9899 | 35 | 269 | 390 | FAIL |
| I3.uniform | pit | 0.9940 | 37 | 237 | 363 | FAIL |
| I3.sqrt | hit | 0.9979 | 15 | 118 | 186 | FAIL |
| I3.sqrt | pit | 0.9989 | 16 | 100 | 154 | FAIL |

**Stated plainly so it cannot be misread: this clause determined no verdict.** All ten
cells already fail P1 on their own floors, so the clause is corroboration only, and the
self-added 0.999 / 100 bound is not load-bearing anywhere in this lane.

It does record one thing worth carrying forward. `I3.sqrt` on hitters is a pooled-rho
null at **0.193x** of its floor with a point delta of +0.00009, and it still moves the
median served player 15 places and the worst 186. **A rank-null is not a board-stable
change.** Any future arm that is defended as "harmless because the rank metric cannot
see it" has to answer this table.

Staleness, as registered: the served matrices reproduce `consensus_fv_raw` on 74.8% of
rows, so a refresh that spread the grades would move these numbers UP. The figures above
are a lower bound on blast radius, which is the conservative direction for a
disqualifying clause.

### 7.9 Multiplicity, at full family size

- **20 rank cells** measured (10 primary on the full pool, 10 sensitivity on the debuted
  pool). **0 pass.** The family was not narrowed.
- **8 AUC comparisons** (2 bars x 2 sides x 2 pools). On the admissible pool, 0 favour
  the candidate; 4 of 4 favour the incumbent blend.
- Bonferroni is moot and is reported as moot: **no cell in the lane reaches its own
  unadjusted one-sided floor in the winning direction**, so no correction changes any
  call. The registered constants (k = 10, z = 2.5758; k = 20, z = 2.7344) are carried in
  the artifact for completeness.
- **Every cell that resolves in this lane resolves as a LOSS.** That asymmetry is the
  cleanest available evidence that the instrument is not simply inert.

### 7.10 What is now closed

The three mechanisms this lane was given were the last untested rank levers outside the
closed feature-composition ledger. All three are measured and all three are null:

- **the fit target** is not a lever (and the two natural transforms cost rank on hitters);
- **the AUC objective** is not a lever (a classifier fit to the bar loses to the
  regression blend on that bar);
- **the fit weighting** is not a lever (it is inside its own permutation band).

"We think we are at the ceiling" is now "we measured the ceiling on every axis we have."
Nothing here licenses a change to any shipped file, and this lane changed none.
