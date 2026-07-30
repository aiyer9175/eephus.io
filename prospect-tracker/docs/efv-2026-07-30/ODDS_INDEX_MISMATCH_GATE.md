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
