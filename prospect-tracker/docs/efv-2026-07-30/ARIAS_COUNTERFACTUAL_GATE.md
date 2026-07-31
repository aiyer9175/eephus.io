# Arias counterfactual gate - grade-normalization basis (LEVER 2)

**Written 2026-07-30, BEFORE any measurement was run. The criteria below are frozen.**

Owner context: Franklin Arias (`franklin_arias`) is wanted back at #1 on the eFV board.
Two levers were nominated. This document gates LEVER 2 only. LEVER 1 is already answered
and is NOT re-run here (see the closing section).

---

## 1. Question

Does turning cross-source grade normalization OFF
(`consensus.ADOPT_NORMALIZED_CONSENSUS` True -> False) improve eFV **out-of-sample
accuracy**?

This is an accuracy question, not a board-position question. Whether the flip moves Arias
up is measured and reported SEPARATELY (section 6) and carries no weight in the verdict.

## 2. Primary metric

Pooled OOS Spearman of the shipped blend versus realized first-6-MLB-season bWAR, **per
side**, on the forward-chained `efv_model.SCORED_YEARS` folds (2020, 2021, 2022, 2023),
using the shipped protocol in `tools/efv_lab_runner.py`:

* pool = matrix rows with `kind == "debuted"` and a non-null `target_censored`
* per fold `yr`: train = `decision_year < yr`, test = `decision_year == yr`,
 gates `len(test) >= 12` and `len(train) >= 50`
* legs: `cons = max(0, _pred_ols(_fit_ols_fv(train), fv))`,
 `model = _predict(_fit_ridge(train, _feature_spec(side)[0]), feats)`
* blend = `(1 - lam) * cons + lam * model`, `lam = blend_lambda(side)`
* target = `target_censored`, sample weights = matrix `weight`

## 3. Secondary metrics

* full-pool debut / no-debut discrimination **AUC** (pool = full labeled matrix minus
 `bust_recent` busts). Admissible here: the candidate is a change of BASIS on the
 consensus column, which cannot sense whether a row has a MiLB production block, so the
 2026-07-25 carve-out in `docs/EFV_GATE_STANDARD.md` section 3 does not bind.
* **block-rho**: (side x cohort-year) block-normalized pooled Spearman, both sides pooled.

## 4. SHIP criterion (frozen)

Recommend flipping normalization OFF **only if**:

* pooled Spearman delta (OFF minus ON) **>= +0.017 on the hitter side**, AND
* pooled Spearman delta (OFF minus ON) **>= +0.016 on the pitcher side**, AND
* paired-bootstrap **lo95 > 0 on BOTH sides**.

Those two floors are the `docs/EFV_GATE_STANDARD.md` section 1 MDE95 incremental floors.

## 5. REJECT criterion (frozen)

If the delta is below its floor on **either** side, or if `lo95 <= 0` on **either** side,
the result is a **NULL / NO-SHIP**. It is reported as a null. It is not a "directional
signal", a "small win", or a "fringe gain", and it is not re-cut post hoc looking for a
subgroup where it clears.

## 6. Mandatory controls (all four required, per gate standard section 2)

1. **Paired player-clustered bootstrap**, B = 2000, seed 20260730, resampling **train AND
 test** with a **refit of ridge + consensus OLS on every draw**. ON and every arm share
 the identical resample sequence so the deltas are paired.
2. **Zero-information control**: a twin of the consensus column carrying its marginal but
 no information - the ON consensus values **row-permuted within decision-year strata**.
 Reported beside the candidate. If the control scores as well as the candidate, there is
 no result.
3. **Permutation null band** for the same delta: the OFF consensus column permuted within
 decision-year strata, full forward chain re-run per draw, delta distribution reported
 with an empirical two-sided p-value for the observed OFF delta.
4. **The delta averaged over >= 4 independent time splits, reported per split.** Primary
 folds are the four SCORED_YEARS; the multi-split arm extends the forward chain to
 decision years 2018-2024 (7 splits) and reports every fold separately, not just pooled.

Additional arm, reported as a diagnostic (not part of the gate): **rank-identical twin**,
the OFF marginal placed on the ON rank order. Grade normalization is a per-(source, role,
cycle) additive offset, so it can only move ranks where the SOURCE MIX differs between
players. This arm separates "the reordering carries information" from "the scale/marginal
moved".

## 7. Replication fidelity precondition (frozen)

The norm=OFF consensus must be produced by machinery whose norm=ON output reproduces the
stored `consensus_fv_raw` to within 0.01 FV on **>= 99% of matrix rows**. If that bar is
not met, the run STOPS and reports why; no verdict is issued on an unvalidated
replication.

## 8. What is measured separately and is NOT part of the gate

Arias's consensus-input effect: his consensus FV under ON and OFF, his consensus
percentile among live active hitters under each, and his consensus-FV gap to
`jesus_made` under each. This is a **CONSENSUS-INPUT** effect. It is **not** a re-scored
board rank - `efv_score.run_live` is not re-run, and no board rank is claimed.

## 9. LEVER 1 (reliability shrink K) - already answered, not re-run

`data/xfv_cap_sweep_eval.json` was generated when K = 100/80 was the shipped value; its
`sides.{hit,pit}.caps.reliability_shrink_K.K_x0.5` cell IS today's shipped K = 50/40. The
deltas recorded there (K50 minus K100) are:

| side | dSpearman | CI95 | dAUC |
|---|---|---|---|
| hit | +0.00052 | [-0.00277, +0.00384] | +0.00075 |
| pit | +0.00340 | [-0.00152, +0.00862] | +0.00021 |

Reverting to K = 100/80 reverses those signs. Both are NULL under gate standard section 1
(incremental floors 0.017 hit / 0.016 pit; a lambda-class floor would still be 0.0076 hit /
0.005 pit). LEVER 1 is a null in both directions and is closed without a re-run.

## 10. Constraints on this run

No production module is edited. Any production constant needed at a different value is
monkeypatched at runtime inside `tools/efv_gradenorm_basis_lab.py`. No pytest, no
`run_monthly`, no export module, no scraper. `data/xfv_*_matrix.json` are read only; the
norm=OFF variants live in memory.

---

# RESULTS

_Appended after the run. The criteria above were not altered. Full numbers:
`data/xfv_gradenorm_basis_eval.json`. Harness: `tools/efv_gradenorm_basis_lab.py`
(B = 2000, seed 20260730, permutation B = 2000, runtime 1642 s)._

## VERDICT: NULL / NO-SHIP

The flip does **not** improve out-of-sample accuracy. It is negative on the primary metric
on both sides, it fails every leg of the ship criterion, and its measured effect is
indistinguishable from a random re-basing of the same magnitude on hitters and **worse than
random** on pitchers. `consensus.ADOPT_NORMALIZED_CONSENSUS` should stay `True`.

## 0. Replication fidelity (precondition - CLEARED)

The counterfactual did not require re-implementing `compute_consensus_point`.
`consensus.build_timeseries` is a pure function of the snapshot pool, so it was called
twice in memory on `storage.load_all_snapshots()` (50,977 snapshots), with
`normalize=True` and `normalize=False`. The replication is therefore the shipped code path.

| side | rows | within 0.01 FV | max abs dev | unmatched keys |
|---|---|---|---|---|
| hit | 1927 | **1919 = 99.585%** | 0.01 | 0 |
| pit | 2063 | **2059 = 99.806%** | 0.01 | 0 |

Bar was >= 99% on both sides. All 12 non-matching rows deviate by *exactly* 0.01 - they are
`round()` half-way boundaries (stored 35.62 vs recomputed 35.63), not a logic difference.
Max deviation anywhere in the pool is 0.01 FV.

**Completeness of the substitution.** `efv_model._feature_spec` is
`['fv', ...]` on both sides and contains neither `fv_trend` nor
`consensus_fv_pre_shrinkage`, so the consensus basis reaches the model through exactly two
channels - the `fv` ridge column and the consensus OLS leg - both driven off
`consensus_fv_raw`. Overwriting that one number is the complete counterfactual.

**Protocol equivalence.** The numpy refit twin used for the 2000-draw bootstrap reproduces
the shipped pure-Python fit: ON pooled rho 0.389200 (python) vs 0.389207 (numpy) on hitters
(|d| 6.6e-06) and 0.307700 vs 0.307662 on pitchers (|d| 3.8e-05). Every point estimate
below is the pure-Python number.

## 1. Primary metric - pooled OOS Spearman, debuted pool, SCORED_YEARS folds

Baselines: hit rho **0.38921** (n = 353 test rows, lam 0.70), pit rho **0.30766**
(n = 438, lam 0.54). (These sit slightly above the 0.3787 / 0.3020 quoted in the
2026-07-24 cap-sweep header because the matrices were rebuilt on 2026-07-29 and the hit
lambda is now 0.70.)

| side | ON | OFF | delta (point) | bootstrap delta | CI95 | P(improves) | floor | clears? |
|---|---|---|---|---|---|---|---|---|
| hit | 0.38921 | 0.38561 | **-0.00360** | **-0.00465** | [-0.01726, +0.00749] | 0.213 | +0.017 | **NO** |
| pit | 0.30766 | 0.28858 | **-0.01908** | **-0.01754** | [-0.04344, +0.00764] | 0.078 | +0.016 | **NO** |

Both deltas are **negative**, both `lo95 <= 0`, and neither approaches its floor. The
pitcher point loss (-0.019) is larger in magnitude than the pitcher ship floor itself.
REJECT criterion met on both sides independently.

## 2. Secondary metrics - the two-metric gate DISAGREES IN SIGN

Full labeled production pool (matrix minus `bust_recent` busts), debut / no-debut AUC:

| side | ON auc | OFF auc | d_auc (point) | bootstrap d_auc CI95 | full-pool d_rho CI95 |
|---|---|---|---|---|---|
| hit | 0.86115 | 0.86817 | +0.00702 | +0.00768 [-0.00050, +0.01723] | -0.00847 [-0.01866, +0.00177] |
| pit | 0.77719 | 0.78990 | +0.01271 | +0.01131 [-0.00032, +0.02398] | -0.01746 [-0.03638, +0.00066] |

AUC moves **up** while rank moves **down**, on both sides, and both AUC CIs still include
zero. Block-rho (blocks = side x cohort-year, both sides pooled):

| arm | block-rho | delta vs ON | bootstrap CI95 | MDE95 |
|---|---|---|---|---|
| ON | 0.33619 | - | - | 0.0149 |
| OFF | 0.32240 | **-0.01379** | [-0.03010, +0.00319] | 0.0149 |

Block-rho is negative at 0.93x its own floor. Two of the three admissible metrics are
negative; the one that is positive is not resolvable. This is the same
metrics-disagree-in-sign signature the gate standard flags, and it is not a pass under any
reading.

## 3. Control 1 - zero-information control (prescribed)

`ZI_CTRL` = the ON consensus row-permuted within decision-year strata (marginal preserved
per stratum, information destroyed).

| side | d_rho point | bootstrap CI95 |
|---|---|---|
| hit | -0.03506 | -0.04194 [-0.10653, +0.01980] |
| pit | -0.09100 | -0.11014 [-0.20429, -0.02850] |

This confirms the instrument responds and that the consensus column is the dominant signal
in the model - destroying it costs 9-28x what the basis flip costs. It is a **floor check,
not a discriminating null for a basis change**, because it removes the whole column rather
than the part that changes. Stated plainly so it is not over-read.

## 4. Control 1b - correctly-scaled zero-information twin of the CHANGE (added)

`SHIFT_CTRL` = ON plus the per-row `(OFF - ON)` shift **permuted within decision-year
strata**: identical shift marginal, scrambled as to which player receives which shift. This
is the control that is magnitude-comparable to the candidate.

| side | SHIFT_CTRL d_rho | bootstrap CI95 | OFF d_rho |
|---|---|---|---|
| hit | -0.00560 | -0.00560 [-0.01870, +0.00631] | -0.00465 |
| pit | +0.00992 | +0.00913 [-0.01336, +0.03127] | -0.01754 |

Direct paired contrast, **OFF minus SHIFT_CTRL** (B = 2000, refit per draw):

| side | contrast | CI95 | P(real re-basing better than random) |
|---|---|---|---|
| hit | **+0.00080** | [-0.01383, +0.01641] | **0.540** |
| pit | **-0.02771** | [-0.06147, +0.00538] | **0.046** |

This is the decisive read. On hitters the real re-basing is a **coin flip** against a random
re-basing of the same size. On pitchers the real re-basing is **worse than random in 95.5%
of draws**. Whatever the flip does to the consensus column, the specific information it
supposedly restores is not detectable, and on the pitcher side its direction is actively
wrong.

## 5. Control 2 - permutation null band

The OFF column permuted within decision-year strata, full forward chain re-run, B = 2000:

| side | null mean | null CI95 | p95 abs | observed OFF delta | p (two-sided) |
|---|---|---|---|---|---|
| hit | -0.04068 | [-0.05808, -0.02639] | 0.05348 | -0.00360 | 0.9995 |
| pit | -0.10643 | [-0.13531, -0.08327] | 0.12955 | -0.01908 | 1.0000 |

Read correctly: this null also destroys the column, so it centres far negative. The
p-values near 1.0 say the observed OFF delta is *much smaller in magnitude* than the null - i.e. **OFF retains essentially all of ON's information**. It does not certify that the
small OFF-vs-ON difference is signal, and it cannot; section 4 is the null that adjudicates
that, and it says no.

## 6. Control 3 - the delta over 7 independent time splits

Per-fold `d_rho(OFF - ON)`, each fold fit and scored on its own:

| fold | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | mean | folds positive |
|---|---|---|---|---|---|---|---|---|---|
| hit | +0.0077 | -0.0156 | +0.0197 | -0.0285 | -0.0100 | -0.0063 | +0.0042 | **-0.0041** | 3 of 7 |
| pit | -0.0020 | +0.0024 | -0.0491 | -0.0250 | -0.0174 | +0.0105 | -0.0157 | **-0.0138** | 2 of 7 |

Negative on average on both sides, sign-unstable on hitters, and consistently negative on
pitchers. No time-split reading rescues the candidate.

## 7. Diagnostic - where the (small) loss comes from

`RANKID` = the OFF marginal placed on the ON rank order (rank-identical twin of ON carrying
OFF's scale): hit -0.00065 point / -0.00209 bootstrap; pit -0.00634 / -0.00448.

The two bases are nearly rank-identical to begin with - Spearman(ON, OFF) = **0.9917**
hitters / **0.9783** pitchers, mean absolute rank change 42 of 845 / 60 of 981 rows. The
scale change alone costs almost nothing. On pitchers roughly two thirds of the -0.019 loss
comes from the **reordering** the flip introduces, which is exactly the part section 4
shows is no better than random.

## 8. Board effect - CONSENSUS-INPUT ONLY (reported separately, no gate weight)

`efv_score.run_live` was **not** re-run. No board rank is claimed. What follows is the
effect on the consensus INPUT that feeds both the headline's consensus leg and the `fv`
feature.

Over 2,101 live active hitters with a resolvable consensus key, the flip shifts consensus by
mean **+0.779 FV** (sd 1.203, range 0 to +7.93); **64.6% of live hitters do not move at
all** (FanGraphs is the reference scale, so FG-only prospects have a zero offset).

| player | consensus ON | consensus OFF | delta | rank by consensus ON | rank by consensus OFF | pctile ON | pctile OFF |
|---|---|---|---|---|---|---|---|
| `franklin_arias` | 58.1 | 60.0 | +1.9 | 3 | **3** | 99.905 | 99.905 |
| `jesus_made` | 60.1 | 62.0 | +1.9 | 1 | **1** | 100.0 | 100.0 |

**Arias minus Made consensus gap: -2.0 ON, -2.0 OFF, change exactly 0.000.**

This is not a coincidence and not a small effect - it is **mechanically impossible for the
flip to move Arias relative to Made**. `grade_normalization._apply_offset` is a pure
per-(source, role, cycle) **additive** offset applied identically to every player that
outlet grades, and the consensus is an equal-weight mean (`data/source_weights.json` was
reverted to empty on 2026-07-25). Both players are graded by the identical five-source set,
so both receive the identical shift:

| source | offset applied | Arias published | Made published |
|---|---|---|---|
| fangraphs (reference) | 0.00 | 60 | **65** |
| just_baseball | -1.51 | 60 | 60 |
| espn | -2.14 | 60 | 60 |
| tjstats | -2.12 | 60 | 60 |
| mlb_pipeline | -3.72 | 60 | **65** |

Made is ahead because two outlets - including the reference scale itself - publish him a
full grade higher. Arias is 60 across the board. **No basis change on the consensus column
can close that gap.** If Arias is to be #1 it has to come from the model leg, not from the
consensus basis.

## 9. Disposition

* LEVER 2 (`ADOPT_NORMALIZED_CONSENSUS` -> False): **NULL / NO-SHIP.** Negative on the
 primary metric on both sides; fails all three legs of the ship criterion; indistinguishable
 from a random re-basing on hitters and worse than random on pitchers. Keep `True`.
* LEVER 1 (reliability shrink K 50/40 -> 100/80): **NULL, closed without a re-run** on the
 existing `data/xfv_cap_sweep_eval.json` evidence (section 9 above).
* Neither lever moves Arias to #1, and LEVER 2 provably cannot move him relative to
 `jesus_made` at all.
* Nothing was tuned toward the Arias outcome. No production module was edited; no
 constant was changed on disk.
