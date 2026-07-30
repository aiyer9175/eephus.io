# The odds INDEX MISMATCH: is p_bucket_given_fv being read in the wrong units?

Lane: LANE-ODDS-INDEX. Owner decision 2026-07-30: **establish the scale mismatch, and if it
is real, fix it and measure the fix against the same three baselines the odds lane used.**

Gate standard: `docs/EFV_GATE_STANDARD.md` (all four section-2 controls are mandatory).
Predecessors, all of which this lane treats as settled and does NOT re-run:
* `docs/efv-2026-07-30/ODDS_GRADE_BASIS_GATE.md` - KEEP THE PIN. The re-key onto
  `outcome_implied_fv` is a level shift that loses to its own zero-information null.
  Section 2.11 named the units problem in passing and costed a refit.
* `docs/efv-2026-07-30/ODDS_RECALIBRATION_SHIP_GATE.md` - the Platt re-link is a **measured
  NULL** against a flat base rate on the population it would touch (`pooled_served` log loss
  d = +0.00372 CI95 [-0.12097, +0.11434], P = 0.544). **It is not re-run here.** Its
  forward-chained arm is rebuilt only as a BASELINE to score the candidate against.
* `efv_odds_calibration.py`'s docstring, which recorded the dispersion ratio in 2026-07-25.

Lab: `tools/odds_index_basis_lab.py`. Artifact: `data/odds_index_basis_eval.json`.
Registry row: `xfv_odds_index_basis`.

**PART 1 WAS WRITTEN AND COMMITTED TO DISK BEFORE THE LAB WAS WRITTEN OR RUN.** The only
thing that preceded it is the scale census in 1.1, which is a description of the INPUTS and
is what the owner asked to be established first; no arm was scored before this was on disk.
PART 2 is appended after. This lane touches NO production module.

---

# PART 1. Pre-registration

## 1.0 The hypothesis under test, in the owner's words

> `p_bucket_given_fv` is a borrowed Clemens 2025 table indexed on CONSENSUS FV but it is
> evaluated at an inverted MODEL prediction. That is a UNITS error, not a calibration
> error, and it would explain why recalibration only moved the level.

## 1.1 THE SCALE CENSUS: what the index is, and what we feed it

Established first, because if there is no mismatch this lane stops here.

**What the table's index is.** `value_framework_config.yaml:63-77` holds five grade cells
per side - `45`, `45+` (axis 47.5), `50`, `55`, `60` - reconstructed to integer counts and
fitted as a proportional-odds ordered logit into `data/value_framework_fitted.json`
(`training_n` 678 hitters / 437 pitchers, `method` `proportional_odds` on both sides). The
cells are **industry consensus FV grades from a published prospect list**. The fit records
its own support explicitly:

    "bayes": { "data_fv_range": [45.0, 60.0] }

The sub-45 block in the config (`p_bucket_given_fv_LOWTIER_ESTIMATE`) is labelled
"NO published 5-bucket table ... SUPERSEDED at runtime" and is documentation only. So
**every served probability below FV 45 is an extrapolation of a curve fitted on [45, 60].**

**What we feed it.** `efv_score.py:1188-1196` (and :1684, :2033) evaluate it at
`_odds_grade = realized_implied_fv(xfv_war, is_pit, age, position)`: the inverse of this
platform's own FV-to-WAR forward map, applied to a model prediction. Measured on the
resolved out-of-fold frame this lane uses (folds 2014-2020; 923 hit / 1,002 pit):

| scale | hit mean | hit sd | hit share < 45 | pit mean | pit sd | pit share < 45 |
|---|---|---|---|---|---|---|
| **consensus FV** (the table's native index) | 42.24 | 5.66 | 0.740 | 41.52 | 4.50 | 0.814 |
| **`_odds_grade`** (what production feeds it) | **37.00** | **15.26** | 0.654 | **35.66** | **10.15** | 0.775 |
| `outcome_implied_fv` (the re-key, rejected) | 37.92 | 13.92 | 0.697 | 38.47 | 9.72 | 0.839 |
| per-side rank-quantile grade (consensus-scale) | 42.91 | 6.57 | 0.704 | 41.69 | 4.89 | 0.813 |

**VERDICT: the mismatch is REAL, and it has two separable parts.**

1. **A DISPERSION mismatch.** The served argument's sd is **2.70x** the consensus marginal's
   on hitters (15.26 vs 5.66) and **2.26x** on pitchers (10.15 vs 4.50), with the mean
   **5.2 to 5.9 FV LOWER**. This is the same defect `efv_odds_calibration.py` recorded on
   2026-07-25 at 2.37x on the served-comparable cut, restated on the full frame.
2. **A SUPPORT mismatch, which is larger and which nobody has stated.** The fit's support is
   [45, 60]. **65% to 84% of every column in that table sits below 45**, including the
   consensus column. The table is being read outside its fitted range on the majority of
   rows *no matter which scale we index it on*. Re-indexing cannot fix that, and this lane
   is written so that the measurement can say so.

Two numbers in the owner's brief do not reproduce on this frame and are corrected here
rather than carried: consensus is mean 42.24 sd 5.66 (hit) / 41.52 sd 4.50 (pit), not
"~36.79 sd ~3.6"; and the retired model grade is mean 37.00 sd 15.26 (hit) / 35.66 sd 10.15
(pit), not "~25.07 sd ~10.25". The quoted pair look like live-board figures (served
`xfv.json` today: `xfv_grade` mean 31.29 sd 12.16, `consensus_fv` mean 38.84 sd 5.15 over
9,331 rows), which is a different population from the resolved cohort. **The DIRECTION and
the MAGNITUDE CLASS of the brief are both confirmed; only the digits move.**

## 1.2 The fix, chosen and justified

The owner offered two: evaluate at a consensus-scale input, or re-index the table.

**This lane evaluates at a CONSENSUS-SCALE input.** Re-indexing the table means discarding
the published cells and refitting P(bucket | our grade) on our own resolved cohort, and
`ODDS_GRADE_BASIS_GATE.md` 2.11(c) already costed that and found the data does not support
it: pitcher `good` n = 11 and `star` n = 2, so the top two cutpoints would be invented, and
they are load-bearing for `expected_surplus_usd`, `survivor_expected_war` and the published
star odds. Re-indexing is also unnecessary to answer the owner's question: if feeding the
table a genuine consensus-scale number does not fix the forecast, then re-indexing is not
what is wrong with it either.

**The consensus-scale field.** `efv_score.run` already computes one: `xfv_grade_display`, a
rank-preserving quantile map of `rank_war` onto the scored pool's own consensus-FV
distribution (`efv_score.py:1232-1251`). By construction its marginal IS the consensus
marginal. The out-of-fold analogue used here is built **forward-chained**: the fold's
training rows supply both the `rank_war` ECDF and the consensus-FV quantile function, and
test rows are read through them. Production computes the map on the whole live pool
including the row itself; using the training pool is the honest OOS version and it is
declared here rather than discovered later.

## 1.3 The arms

Every arm scores the SAME out-of-fold `xfv_war` from the SAME refit chain
(`_fit_ridge` -> `_fit_linear_calibration` -> `xfv_war = max(-2, a + b*raw)`), which is
`efv_score.run`'s chain. Only the argument fed to `p_bucket_given_fv`, or the post-map,
differs.

| arm | probability | role |
|---|---|---|
| **INC** | `p_bucket_given_fv(realized_implied_fv(war, is_pit, age, pos))[bust]`, verbatim from `efv_score.py:1188-1196` | BASELINE 1 (the incumbent) |
| **CAL** | INC through a forward-chained Platt map in logit space, refit per fold on prior folds only | BASELINE 2 (the recalibrated arm; NOT re-litigated, rebuilt only to score against) |
| **CONST** | a constant at the **within-cut** base rate of the same cut's prior folds | BASELINE 3 (the flat base-rate constant) |
| **QNT** | `p_bucket_given_fv(consensus-scale rank-quantile grade)[bust]` | **THE CANDIDATE** |
| **QWAR** | `p_bucket_given_fv(q(xfv_war))[bust]`, the same quantile construction on the PURE model WAR instead of the consensus-guarded `rank_war` | candidate variant: isolates the units fix from the consensus information `rank_war` carries |
| **NAT** | `p_bucket_given_fv(consensus_fv_raw)[bust]` - the table read at its NATIVE index | **THE DECISIVE DIAGNOSTIC** |
| **QNT+Platt** | QNT through the same forward-chained Platt map | the level-shift trap (1.6.3) |

**Why NAT decides this lane and why it is not a forecast.** NAT is not shippable: it is the
consensus grade, so it contains no model at all. It is here because it answers the only
question that separates a UNITS defect from a POPULATION defect. If the table read at a
genuine consensus FV **also** loses to the flat constant on our cohort, then the index is
exonerated and the error is that Clemens's published-list pool busts at 51-53% at FV 45
while our whole-cohort matrix busts at 84-88%. No re-indexing and no rescaling of the
argument can repair a base-rate gap of that size. If NAT **beats** the constant, the units
hypothesis is alive and QNT is the right shape of fix.

`CONST` is fitted WITHIN the cut, as in `ODDS_RECALIBRATION_SHIP_GATE.md` 1.5, because the
served-comparable population's bust base rate is far below the full frame's and scoring it
against the full frame's 0.86 would hand every candidate a free win against a strawman.

## 1.4 The frame

Identical to both predecessor lanes, so the three baselines are comparable row for row.

**Pool.** `data/xfv_hitter_matrix.json` / `data/xfv_pitcher_matrix.json`, minus rows with
`kind == "bust" and bust_recent`, prepped through `efv_model._prep(pool, "target_censored",
side)`.

**Test restriction.** `censored is False`, `target_resolved` numeric, and
`consensus_fv_raw` present (NAT and QNT both need it; `efv_score.run` requires it anyway,
`efv_score.py:1191`).

**Folds.** Forward-chained on `efv_model._decision_year`, decision years **2014-2020**,
seven folds, each trained strictly on `decision_year < fold`. 2021+ is excluded because the
six-season window has not closed there and every resolved row is a bust by construction;
2011-2013 does not carry enough prior rows to fit the chain.

**Label.** The shipped bust event, unchanged: first-6yr TOTAL bWAR / 6 < 0.5, i.e.
`target_resolved < 3.0` (`value_framework_config.yaml:38`, `tools/_prem_odds.py:41`).

**Cuts.** `hit`, `pit`, `pooled`, and `hit_served`, `pit_served`, `pooled_served`
(`milb.rates_missing == 0.0`, the population `run_live` abstains down to and the population
the recalibration guard would apply to).

No star arm is fitted. The frame carries 9 hitter stars and 2 pitcher stars; the basis gate
pre-registered that as unpowered and it has not become powered since.

## 1.5 The metrics and the controls

Per arm, per cut, AND per fold: **Brier**, **log loss** (natural log, clipped to
[1e-6, 1-1e-6]), **ECE** (ten equal-count bins), the **Murphy decomposition**
(`Brier = reliability - resolution + uncertainty`), **calibration slope and intercept**
(`y ~ a + b*logit(p)` by IRLS), **calibration-in-the-large** (`mean(p) - mean(y)`), the
**reliability curve** with Wilson intervals, and **AUC** (secondary, diagnostic).

Controls, all four from gate standard section 2:

1. **Paired bootstrap resampling TRAIN AND TEST with a full refit on every draw.** Clusters
   are `player_key`. Each draw resamples the prepped pool with replacement at the player
   level, re-runs the whole seven-fold chain (ridge + linear calibration + consensus OLS),
   **rebuilds the consensus-scale quantile map on the resampled training rows**, re-fits the
   forward-chained Platt maps, and records the paired deltas. B = 1000, seeded.
2. **Zero-information control**: arm CONST, and it is half the ship criterion, not a footnote.
3. **Permutation null band**: 1000 draws with the label permuted within fold. Load-bearing
   here for the same reason it was for the recalibration lane: QNT is a NARROWER forecast
   than INC (sd 6.57 against 15.26 on the argument), and under random labels a narrower
   forecast beats a sharper one automatically, so `metric(INC) - metric(QNT)` has a
   POSITIVE null by construction. An observed delta inside that band is a null regardless
   of its bootstrap CI. The `CONST - QNT` delta has the mirror property (negative null).
4. **Per-split values** for every headline number, all seven folds.

## 1.6 THE SHIP CRITERION (fixed here, not alterable afterwards)

The owner set it. It is restated verbatim and not softened.

A re-index of the argument ships only if the candidate (QNT):

1. beats the **flat base-rate constant** on **Brier AND log loss**, and
2. does so on the **pooled** cut AND on **`pooled_served`**, and
3. the paired player-clustered refit-every-draw bootstrap **CI95 excludes zero** on all four
   of those (metric x cut) combinations.

Two further pre-registered rules:

4. **The level-shift trap.** If QNT's advantage does not survive forward-chained Platt
   recalibration of both arms, the difference is level/shape and carries no information, and
   the verdict is NOT a re-index even if 1-3 fire. Same rule as `ODDS_GRADE_BASIS_GATE.md`
   1.7.3.
5. **The permutation rule.** An observed delta inside its own null band is a null.

**If QNT fails, that is a NULL and it is reported as one.** The pre-registered reading of a
NULL where NAT also loses to the constant is stated now so it cannot be constructed
afterwards: *the units mismatch is real and is not the binding defect; the binding defect is
that the table's population busts at half our cohort's rate and its fitted support does not
cover our cohort at all.* In that case the recommendation is to STOP, not to go looking for
a different fix.

## 1.7 What this lane will NOT do

It will not edit `efv_score.py`, `value_framework.py`, `efv_ungraded.py`, `storage.py` or
any other production module; it will not re-run the recalibration gate; it will not run
pytest, any exporter, `run_monthly`, `build_site`, a scraper or a matrix rebuild; it will
not `git add` a `data/` path it did not create; and it will not fit a star map or refit the
bucket table.

---

# PART 2. Results

*(Appended after the measurement. Everything above this line was on disk first.)*

Artifact: `data/odds_index_basis_eval.json`. Lab runtime 363.5s, B = 1000 paired bootstrap
draws with a full refit of the ridge, the linear calibration, the consensus OLS, the
consensus-scale quantile map and the forward-chained Platt maps on every draw; B = 1000
permutation draws.

## 2.0 VERDICT: THE MISMATCH IS REAL. FIXING IT IS A NULL. DO NOT RE-INDEX.

The owner asked two questions and they have different answers.

**Is it a mismatch? YES**, on two counts, both quantified in 1.1 and neither disputed by the
measurement: a 2.70x / 2.26x dispersion gap with the mean 5 to 6 FV low, and a fitted support
of [45, 60] that excludes 72% to 78% of the rows on every scale.

**Does fixing it fix the forecast? NO.** The candidate fails the owner's pre-registered ship
criterion on both required cuts, for two different reasons:

* **pooled: FAILS, with the CI excluding zero in the WRONG direction.** QNT vs the flat
  constant, Brier d = **-0.02083** (bootstrap mean -0.02287, CI95 [-0.03974, -0.00716],
  P(candidate better) = 0.001); log loss d = **-0.06599** (CI95 [-0.11610, -0.03014],
  P = 0.001). Climatology is decisively better.
* **pooled_served: FAILS on the interval.** Brier d = +0.03538 (CI95 [-0.00727, +0.06996],
  P = 0.932); log loss d = +0.06322 (CI95 [-0.04710, +0.15074], P = 0.831). The point
  estimates favour the candidate; neither interval excludes zero.

**And the decisive diagnostic settles the attribution.** On the primary frame the table read
at its NATIVE consensus-FV index also loses to the flat constant (Brier d = -0.01399 CI95
[-0.02778, +0.00035]; log loss d = -0.04465 CI95 [-0.07921, -0.00875], P = 0.006). Fed exactly
the units it was fitted on, on exactly the population production serves, the curve is beaten by
a number that knows nothing but the base rate. **The index is exonerated. The population is
convicted.**

One result does NOT collapse and is registered rather than shipped: the consensus-scale keying
carries genuinely MORE information than the incumbent keying, and that survives recalibration
(2.5). The units question was worth asking; it is just not what is wrong with the served odds.

## 2.1 Provenance: both baselines reproduce exactly

Before any verdict. This lab rebuilds the incumbent and the recalibrated arm from scratch and
lands on the predecessor lanes' published numbers:

| arm | this lab, pooled | predecessor | source |
|---|---|---|---|
| INC Brier / log loss | 0.14080 / 0.46089 | 0.14080 / 0.46088 | `ODDS_GRADE_BASIS_GATE.md` 2.2 |
| CAL Brier / log loss | 0.11308 / 0.37864 | 0.11308 / 0.37864 | `ODDS_RECALIBRATION_SHIP_GATE.md` 2.3 |

Frame identity is exact too: 923 hit / 1,002 pit resolved out-of-fold rows, bust base rates
0.8397 / 0.8782, 516 served-comparable. The replication of the served scoring chain is correct
and the three baselines are the same objects the owner named.

**One declared difference.** `CAL` here is a per-fold Platt map fitted on the whole side's
out-of-fold rows and then read on each cut, where `ODDS_RECALIBRATION_SHIP_GATE.md` fitted it
WITHIN the served cut. On `pooled_served` that makes this lane's CAL slightly stronger
(0.19545 / 0.61283 against that gate's 0.20277 / 0.63595). CAL is a baseline, so a stronger
baseline is conservative for the candidate and does not flatter it. `CONST` IS fitted within
the cut, exactly as pre-registered.

## 2.2 The arms

**Pooled** (n = 1,925, base rate 0.8597)

| arm | Brier | log loss | ECE | reliability | resolution | mean p - obs | AUC |
|---|---|---|---|---|---|---|---|
| INC | 0.14080 | 0.46089 | 0.1747 | 0.0483 | 0.0273 | -0.1533 | 0.7967 |
| CAL | 0.11308 | 0.37864 | 0.0678 | 0.0113 | 0.0178 | -0.0366 | 0.7675 |
| **CONST** | **0.12902** | **0.41980** | 0.1384 | 0.0221 | 0.0146 | -0.1384 | 0.7679 |
| **QNT** | 0.14985 | 0.48580 | 0.2411 | 0.0609 | **0.0311** | **-0.2411** | **0.8289** |
| QWAR | 0.15186 | 0.49475 | 0.2445 | 0.0626 | 0.0302 | -0.2445 | 0.8171 |
| **NAT** | 0.14301 | 0.46446 | 0.2296 | 0.0541 | 0.0301 | -0.2296 | 0.8338 |
| QNT_P | **0.10305** | **0.34118** | 0.0518 | 0.0065 | 0.0211 | -0.0326 | 0.8063 |

**Served-comparable** (n = 516, base rate 0.6822)

| arm | Brier | log loss | ECE | reliability | resolution | mean p - obs | AUC |
|---|---|---|---|---|---|---|---|
| INC | 0.23196 | 0.73794 | 0.2096 | 0.0535 | 0.0392 | -0.1414 | 0.7386 |
| CAL | 0.19545 | 0.61283 | 0.1009 | 0.0134 | 0.0347 | +0.0971 | 0.7293 |
| **CONST** | **0.23738** | **0.66899** | 0.1383 | 0.0287 | 0.0097 | -0.1107 | 0.5073 |
| **QNT** | 0.20199 | 0.60577 | 0.1605 | 0.0287 | 0.0427 | -0.1605 | 0.7646 |
| QWAR | 0.21646 | 0.64926 | 0.1807 | 0.0379 | 0.0381 | -0.1788 | 0.7432 |
| **NAT** | **0.18082** | **0.54754** | 0.1303 | 0.0183 | **0.0546** | -0.1303 | **0.7996** |
| QNT_P | 0.19273 | 0.58522 | 0.1255 | 0.0192 | 0.0401 | +0.1004 | 0.7560 |

## 2.3 The gate, scored

`d = metric(baseline) - metric(candidate)`. POSITIVE means the candidate is better. The
bootstrap is the paired, player-clustered, refit-every-draw one (B = 1000).

| cut | comparison | metric | point d | bootstrap CI95 | P(cand) | permutation null band95 |
|---|---|---|---|---|---|---|
| **pooled** | **QNT vs CONST** | **Brier** | **-0.02083** | **[-0.03974, -0.00716]** | **0.001** | [-0.05860, -0.04848] |
| **pooled** | **QNT vs CONST** | **log loss** | **-0.06599** | **[-0.11610, -0.03014]** | **0.001** | [-0.16547, -0.13867] |
| **pooled_served** | **QNT vs CONST** | **Brier** | +0.03538 | **[-0.00727, +0.06996]** | 0.932 | [-0.06003, -0.02529] |
| **pooled_served** | **QNT vs CONST** | **log loss** | +0.06322 | **[-0.04710, +0.15074]** | 0.831 | [-0.18381, -0.09391] |
| hit | QNT vs CONST | Brier | -0.01960 | [-0.04035, -0.00099] | 0.016 | [-0.07151, -0.05484] |
| pit | QNT vs CONST | Brier | -0.02197 | [-0.04646, -0.00660] | 0.003 | [-0.04904, -0.03570] |
| hit_served | QNT vs CONST | Brier | +0.04032 | [-0.00935, +0.08504] | 0.954 | [-0.08763, -0.03204] |
| pit_served | QNT vs CONST | Brier | +0.03095 | [-0.02880, +0.06907] | 0.796 | [-0.03794, -0.00053] |

**Criteria 1 to 3 FAIL.** The pooled cut fails outright with the interval excluding zero on the
constant's side; the served cut fails the interval requirement on both metrics. Under the
pre-registered rule that is a NULL, and 1.6 says the recommendation is to stop.

**The permutation control clears the candidate of the RE-KEY's failure mode, and this is worth
stating precisely because it is the one thing that separates this result from the basis gate's.**
`ODDS_GRADE_BASIS_GATE.md` 2.6 found the re-key's apparent wins were SMALLER than what a
forecast with the same marginal and no label information would deliver. QNT is not that: every
observed delta above sits on the correct side of its own null band. QNT is a real forecast that
loses to a constant on level, not a phantom that wins by being flat.

`QWAR`, the same construction on pure model WAR instead of the consensus-guarded `rank_war`, is
uniformly slightly worse than QNT (pooled Brier 0.15186 against 0.14985; served 0.21646 against
0.20199). The consensus information in `rank_war` helps; the units change is not doing the work
by itself.

## 2.4 The decisive diagnostic: NAT, and what it proves

NAT is `p_bucket_given_fv` evaluated at the row's own `consensus_fv_raw` - the table read at
exactly the index it was fitted on. It is not shippable (it contains no model), and that is the
point: it isolates the INDEX from the POPULATION.

| cut | comparison | metric | point d | bootstrap CI95 | P | permutation null band95 |
|---|---|---|---|---|---|---|
| **pooled** | NAT vs CONST | Brier | **-0.01399** | [-0.02778, +0.00035] | 0.028 | [-0.04887, -0.03868] |
| **pooled** | NAT vs CONST | log loss | **-0.04465** | **[-0.07921, -0.00875]** | 0.006 | [-0.12867, -0.10385] |
| **pooled_served** | NAT vs CONST | Brier | **+0.05656** | **[+0.02281, +0.08929]** | **1.000** | [-0.04546, -0.01225] |
| **pooled_served** | NAT vs CONST | log loss | **+0.12145** | **[+0.04692, +0.19895]** | **0.999** | [-0.12785, -0.04650] |

Read the two rows together. **On the full resolved cohort, the curve fed its own units loses to
climatology on both proper scores.** On the served-comparable subset - rows with a real MiLB
track record, the population `run_live` abstains down to and the one that most resembles a
published prospect list - **the same curve, same units, beats climatology decisively, with the
CI excluding zero and the observed far above its own null band.**

That is the whole finding. The table is not broken and its index is not the binding defect.
It is a model of a PUBLISHED-LIST population (Clemens 2025: 51% to 53% bust at FV 45) being
scored on the whole eFV cohort matrix (84% to 88% bust). No change of argument can move a
forecast across a base-rate gap of thirty-five points, which is why re-indexing moves the level
the wrong way and why the 2026-07-25 recalibration moved only the level.

`ODDS_GRADE_BASIS_GATE.md` 2.11(c) named this population problem while costing a refit. This
lane measures it directly and promotes it from a caveat to the answer.

## 2.5 What DOES survive: the consensus-scale keying carries more information

Not a ship. Reported because it is true and because 1.6 rule 4 required the test.

The level-shift trap asks whether the candidate's difference from the incumbent survives an
out-of-fold monotone recalibration of both. **It does, and it goes the candidate's way:**

| cut | metric | QNT_P vs CAL, point d | bootstrap CI95 | P | permutation null band95 |
|---|---|---|---|---|---|
| pooled | Brier | +0.01003 | **[+0.00300, +0.02144]** | 0.997 | [-0.00229, +0.00245] |
| pooled | log loss | +0.03746 | **[+0.01717, +0.07518]** | 0.999 | [+0.01008, +0.03200] |
| hit | Brier | +0.01779 | [+0.00443, +0.03535] | 0.999 | [+0.00025, +0.00747] |
| pit | Brier | +0.00288 | [-0.00420, +0.01644] | 0.842 | [-0.00692, -0.00174] |

Three independent readings agree that this is information and not level:

1. **Discrimination is higher.** Pooled AUC 0.8289 (QNT) against 0.7967 (INC); on the served cut
   0.7646 against 0.7386. Contrast the re-key, whose AUC was identical to the incumbent's to
   three decimals - that is exactly what told the basis gate its candidate was pure level.
2. **Murphy resolution is higher.** 0.0311 against 0.0273 pooled; 0.0427 against 0.0392 served.
3. **After recalibrating both arms out of fold the gap persists**, with the CI excluding zero
   and the observed above its null band, on the pooled cut and on hitters. It is a null on
   pitchers.

So the consensus-scale grade is a BETTER-ORDERED key than the retired realized-implied grade.
Its raw form is nonetheless worse, because its level is worse: calibration-in-the-large goes
-0.1533 (INC) to -0.2411 (QNT), since the consensus-scale grade is higher on average (pooled
mean 42.28 against 36.30) and the table returns a lower p_bust at a higher grade, on a curve
that is already fifteen points too low.

**This is registered, not recommended.** Acting on it would mean shipping QNT plus a
recalibration, and the recalibration half is `ODDS_RECALIBRATION_SHIP_GATE.md`'s measured NULL
against a base rate. A better-ordered key stacked on a link that cannot beat climatology is not
a served improvement, and this lane will not assemble one out of two components that each
failed their own gate.

## 2.6 The support problem, which re-indexing makes slightly worse

Share of rows below the fit's own recorded support of FV 45, pooled:

| argument | mean | sd | share below 45 |
|---|---|---|---|
| INC (`realized_implied_fv`) | 36.30 | 12.87 | 0.717 |
| QNT (consensus-scale quantile) | 42.28 | 5.78 | 0.761 |
| QWAR | 42.42 | 6.14 | 0.763 |
| NAT (`consensus_fv_raw`) | 41.87 | 5.10 | 0.779 |

Re-indexing fixes the DISPERSION (sd 12.87 to 5.78, essentially matching the consensus marginal
of 5.66 / 4.50 in 1.1) and does nothing at all for the SUPPORT: about three quarters of rows sit
outside [45, 60] on every scale, and the better-matched the scale, the slightly higher that
share. Every served p_bust on those rows is an ordered-logit extrapolation, and no re-argument
changes that.

## 2.7 Per split (gate standard 2.4)

Pooled, `d = metric(CONST) - metric(candidate)`, all seven folds:

| fold | n | base rate | QNT d_Brier | QNT d_logloss | NAT d_Brier |
|---|---|---|---|---|---|
| 2014 | 185 | 0.789 | -0.0057 | -0.0509 | +0.0017 |
| 2015 | 173 | 0.734 | +0.0246 | +0.0588 | +0.0257 |
| 2016 | 213 | 0.845 | +0.0023 | -0.0050 | +0.0051 |
| 2017 | 199 | 0.900 | -0.0032 | -0.0284 | +0.0146 |
| 2018 | 389 | 0.918 | **-0.0719** | **-0.1792** | -0.0654 |
| 2019 | 393 | 0.863 | -0.0408 | -0.1201 | -0.0328 |
| 2020 | 373 | 0.877 | +0.0022 | -0.0112 | +0.0071 |

Only three of seven folds favour the candidate on Brier, and the two heaviest losses are the
two largest folds, which are also the two with the highest bust base rates (0.918 and 0.863).
That is the level story again: the higher the fold's true bust rate, the worse a forecast that
systematically under-predicts bust does against a constant that does not.

## 2.8 What should actually happen

1. **DO NOT RE-INDEX.** The candidate fails its pre-registered criterion on both required cuts.
   `xfv_odds_index_basis` registers as `deprecated`.
2. **The units mismatch is real and should be DOCUMENTED at the seam rather than repaired.**
   `efv_score.py:1188-1196` and `value_framework.p_bucket_given_fv`'s docstring should say what
   1.1 establishes: the curve is fitted on 678 / 437 published-list rows over consensus FV
   [45, 60], production reads it at an inverted model prediction 5 to 6 FV lower with 2.3x to
   2.7x the dispersion, and roughly three quarters of served rows are extrapolations. That is a
   documentation change, not a model change, and it belongs to whoever next edits that seam.
3. **The binding defect is the POPULATION, and it now has a measurement.** The same curve, same
   units, beats a flat base rate on the served-comparable cut and loses to it on the full
   cohort. Any real repair has to either restrict the odds to the population the curve fits or
   fit a second, seam-scoped curve on ours - and `ODDS_GRADE_BASIS_GATE.md` 2.11(c) has already
   established that our cohort cannot support the top two cutpoints (pitcher `good` n = 11,
   `star` n = 2). That is a data problem, not a modelling choice, and it should be named as one.
4. **Do not stack QNT on the recalibration.** Both halves failed their own gates. 2.5 is a
   registered observation about ordering, not a build instruction.
