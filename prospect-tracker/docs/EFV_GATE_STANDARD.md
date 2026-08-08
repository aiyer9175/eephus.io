# eFV Gate Standard (adopted 2026-07-24)

**SUPERSEDES the noise floors registered in `docs/efv-2026-07-14/GATES.md` (0.0023,
"identity-refit movement", ship bar +0.0046) and `docs/efv-2026-07-15/GATES.md`
(hit 0.0011 / pit 0.0006).** Those numbers measure NUMERICAL perturbation of one fixed
dataset. They do not measure SAMPLING variability, and they understate the real floor by
**7-17x**. Every eFV ship/reject decision made against them was made below the detection
limit of its own test.

Derivation and the full audit: `docs/EFV_FRONTIER_AUDIT.md`.

## 1. The floor (minimum detectable effect at P > 0.95)

Measured by paired bootstrap resampling the WHOLE pool (train AND test) and refitting
ridge + consensus OLS + calibration on every draw, under the production fit config
(sample_weight = observed_seasons/6, full pool minus recent busts), B = 2000.

**MDE95 is ONE-SIDED (1.645 sd) throughout this table.** The convention was implicit
until 2026-08-07 and had to be recovered by re-measurement. Two-sided it would be
1.96 sd, roughly 19% wider, and several past calls sat between the two.

### 1a. 11-FOLD PAIR-WEIGHTED basis (measured 2026-08-07, CURRENT)

The basis that ships: `SCORED_YEARS` = 2014-2024, headline pooled rho pair-weighted by
`prospect_path._score`. Producer `python tools/efv_mde_lab.py mde 2000` (seed 20260807);
ledger `data/xfv_mde_floor.json`; full write-up
`docs/EFV_EVAL_BASIS_LEDGER_2026-08-07.md`.

| statistic class | MDE95 | sd | pool |
|---|---|---|---|
| model vs consensus, pooled rho, pair-weighted | **0.0440 hit / 0.0436 pit** | 0.0268 / 0.0265 | 755 / 890 |
| model vs consensus, pooled rho, unweighted | 0.0376 hit / 0.0376 pit | 0.0228 / 0.0229 | 755 / 890 |
| model vs consensus, block-rho, pair-weighted | **0.0325** | 0.0198 | 1,645 |
| model vs consensus, block-rho, unweighted | 0.0279 | 0.0170 | 1,645 |
| eFV vs consensus, common-set head-to-head | **0.0352** | 0.0214 | 3,210 rows / 1,050 players |

`source_backtest.XFV_VS_CONSENSUS_MDE95` publishes 0.044 (the two sides agree to
0.0004). The head-to-head row is a DIFFERENT pool and a different statistic; it has its
own constant, `source_backtest.XFV_HEADTOHEAD_MDE95`, and ledger
`data/xfv_headtohead_gap.json`.

**THE 11-FOLD PROMOTION DID NOT BUY POWER.** Pool n went 353/438 to 755/890 and the
floor did not move: the bootstrap resamples the TRAIN frame, so the ridge's refit
variance is in the delta and does not shrink with test n; the added folds are the thin
2014-2019 cohorts plus the censored 2024 one; and pair-weighting 2024 at 0.333 returns
the effective n the extra rows bought. Any plan that budgets a smaller floor because
the pool grew is wrong on this eval.

### 1b. 4-FOLD UNWEIGHTED basis (measured 2026-07-24, RETIRED 2026-08-06)

`SCORED_YEARS` = 2020-2023, unweighted pooled rho. Kept because ledger entries dated
before 2026-08-06 were gated against these numbers and cannot be read without them.
Nothing new may be adjudicated here.

| statistic class | MDE95 |
|---|---|
| model vs consensus, pooled rho | **~0.045** (all four cuts) |
| incremental feature add, pooled rho | **~0.017 hit / ~0.016 pit** |
| blend-lambda shift, pooled rho | **0.0076-0.011 hit / 0.005-0.008 pit** |
| FV-45 fringe t45 | **~0.055 hit / ~0.10 pit** |
| MAE delta | 0.20 hit-debuted / 0.06 pit WAR |

The 2026-08-07 lab re-measures the model-vs-consensus row of this table at 0.0376 hit /
0.0487 pit, which brackets the published 0.045 and is the parity check that validates
both the method and the one-sided convention.

The other four rows have NOT been re-measured on the 11-fold basis. Feature-add,
lambda-shift, t45 and MAE gates are still running against 4-fold floors. Do not assume
they moved in either direction; re-measure the row you need before you gate on it.

**A claimed effect smaller than its row above is a NULL. Report it as a null.** It is not
a "small win", a "directional signal", or a "fringe gain".

## 2. Mandatory controls

No eFV result may be shipped, ledgered as a win, or cited in the registry without all four:

1. **Paired bootstrap** resampling train AND test with a refit each draw. A test-only
   bootstrap understates sd by 1.6-1.8x.
2. **A zero-information control** beside the claim. For a feature: the same column,
   row-permuted (identical marginal, no information). For a label or a level change: a
   rank-identical twin. If the control scores as well as the candidate, there is no result.
   This is the check whose absence invalidated the pitcher-label program
   (`docs/PITCHER_LABEL_LEDGER.md`), where a constant captured 87% of a claimed headroom.
3. **A permutation null band** for the same quantity.
4. **The effect averaged over >= 4 independent time splits**, not one. Several shipped
   features are positive on the 4 scored years and negative across 11 forward-chained folds
   (`x_era_k`: cross-split mean -0.0094, 9 of 11 folds negative).

## 3. The two-metric gate

Pooled Spearman alone is a low-power instrument at these n. Report BOTH:

- **block-rho**: (side x cohort-year) block-normalized pooled Spearman, both sides pooled
  (n = 1001 test rows vs 353/438 separately). MDE95 **0.0149**.
  IMPLEMENTED 2026-08-07 as `efv_model.block_rho_eval()`; emitted into both
  `data/xfv_eval*.json`, `source_backtest.xfv_vs_consensus.block_rho`, and
  `data/xfv_scoreboard_eval.json`. On the 11-fold pair-weighted basis it reads n 1,645,
  consensus 0.3107, blend 0.3228, delta +0.0121.
  **The 0.0149 is the INCREMENTAL FEATURE ADD floor on this instrument** (the
  `EFV_FRONTIER_AUDIT.md` "recommended evaluator" row), measured on the 2020-2024
  n = 1001 pool. A MODEL-VS-CONSENSUS delta on block-rho has its own, much larger floor:
  **0.0325** pair-weighted on the current basis (section 1a). Do not gate a
  feature add against 0.0325, and do not gate a model-vs-consensus claim against
  0.0149. The feature-add row has not been re-measured on the 11-fold basis.
- **full-pool discrimination AUC** (debut / no-debut). On the two candidates known to be
  real it reads SNR **6.25 / 4.08** against block-rho's **1.72 / 1.25**, and it survives
  leak-scrubbing where block-rho does not.

> **CARVE-OUT ADDED 2026-07-25 (archetype-mechanism lane). The full-pool debut /
> no-debut AUC is NOT admissible for any candidate that can sense whether a row has
> a MiLB production block.** Measured on the production fit pool: a row with no MiLB
> block is the same row as a row with no resolved mlbam id 96.4% of the time on the
> hitter side and 94.4% on the pitcher side (`_milb_features` needs the id). Identity
> resolution is far easier for players who reached MLB, so within the 2020+ decision
> cohorts that dominate the scored folds, an unresolved-id row debuts **1.9% (hit) /
> 1.3% (pit)** of the time against **58.7% / 72.0%** for track-record rows. A
> missingness indicator is therefore a near-deterministic proxy for the AUC LABEL,
> not a predictor of it.
>
> Observed consequence: an honest no-track indicator (covering all 975 hit / 1069 pit
> rows that lack the block, versus the 32 / 51 that `milb_missing` actually fires on)
> scores pitcher AUC **+0.0792** against a row-permuted twin at **+0.0003**, while
> pooled rho goes **-0.0049**. Every archetype arm that could express missingness
> reproduced the same signature: AUC up, rank flat or down, control flat. Restricting
> the pool to decision year >= 2017 concentrates the artifact rather than scrubbing it
> (pit AUC +0.0743). SIX ARMS in the 2026-07-25 archetype program would have read as
> wins under this metric; all six are nulls on rank.
>
> Admissible substitutes for this candidate class: pooled rho and block-rho, and AUC
> computed on the TRACK-RECORD population only (which is also the population
> `efv_score.run_live` serves, since it abstains on rows without a MiLB block).
> Ledger: `tools/_arch_MECH_scrub.py`.

Pooling belongs in the EVALUATOR, not the model: a pooled MODEL is a measured null that
trends negative (cross-side coefficient sharing helps only below 40-60% of current training
data and harms at full data).

## 4. Surplus-side currency

Convert any rank claim into dollars before deciding it matters:

> **THE POINT ESTIMATE IS WITHDRAWN, 2026-08-07b. There is no single number here.**
> The value published here was **-$0.0704M**, CI95 [-0.0878, -0.0550], n = 2,236 resolved
> listings, fitted on the pre-v6 frame.

**What a re-derivation on the v6 EV frame actually supports** (`data/surplus_decomposition_v6.json`,
`docs/efv-2026-08-07b/SURPLUS_DECOMPOSITION_V6.md`):

> **+0.01 pooled eFV Spearman is worth somewhere in -$0.06M to -$0.17M of surplus MAE
> per prospect, and the position within that range depends on the instrument, the FV
> scale and the segment. The withdrawn -$0.0704M lies inside it.**

**This is not a conversion rate and must not be used as one.** Three separate sweeps break
it, and they are the reason a point estimate is refused rather than replaced:

- **By segment**: a **2.23x spread** across five mixing segments (production cell,
  price-ranked: -0.154 / -0.134 / -0.110 / -0.069 / -0.075) against a 2.0x stability bar.
- **By instrument**: the two instruments disagree in SIGN about what the v6 re-fit did.
  Price-ranked, all four cells read raw_v5 -0.155, raw_v6 -0.135, normalized_v5 -0.158,
  normalized_v6 -0.134, i.e. the v6 frame makes a rank point worth 13 to 15 percent LESS.
  A served-FV-ranked reading suggests the opposite. The 2x2 was never completed for the
  second instrument, so neither direction is established.
- **By mechanism**: tie-breaking is worth about -$0.058M and cross-grade movement about
  -$0.232M INSIDE the published segment, so "a rank point" is not one quantity.

An earlier draft of this section installed **-$0.117M** and a "1.66x understatement"
claim. That was withdrawn on adversarial review: it replaced one non-reproducible point
estimate with another, on the instrument whose 2x2 was never finished, while the
pre-registered instrument pointed the other way.

Bounding facts to read before leaning on any dollar conversion. A **near-zero-rank-information
board** (median FV for everyone, but still carrying age, eta and position through
`expected_surplus_usd`, giving 150 distinct prices and Spearman 0.023 against truth) beats
the production board on MAE **on the v6 frame** (11.560 against 12.202) and LOSES on the v5
frame (9.860 against 9.837), and loses on MSE either way. So MAE alone cannot arbitrate a
board. The error decomposition is also PATH DEPENDENT (rank/level 0.382/0.232 under one
removal order, 0.712/-0.098 under the other, interaction 0.330) and OBJECTIVE DEPENDENT
(level share 0.232 in MAE against 0.032 in MSE, CI spanning zero under the EV-consistent
loss). Quote shares only with the order and the objective attached.

Served eFV surplus is a function of **rank only** with respect to `rank_war`: a monotone
rescale of `rank_war` moves served grades by exactly 0.000000, so recalibrating the WAR
scale cannot move served surplus no matter how much it improves WAR accuracy.

> **CORRECTED 2026-07-25 - do not read the paragraph above more broadly than it is
> written.** It was previously stated as "level-calibration work cannot move served
> surplus", full stop. That is FALSE, and it licensed a wrong conclusion twice.
> `efv_score.run_live` builds the headline by reading the **sorted consensus_fv of the
> live pool** at each row's rank quantile, and `_reprice_surplus_on_display` prices
> dollars off that grade. So anything that changes the CONSENSUS FV DISTRIBUTION
> reprices the entire board even though every rank is untouched. The grade-normalization
> repair is exactly such a change.
>
> **P0 CLOSED 2026-07-31. Kept below because the finding is worse than the warning was,
> and because the calibration it indicts is still shipped.** Regenerating
> `surplus_backtest_real` on the NORMALIZED frame (its own default; the committed artifact
> predated the switch) flips the bias sign: -4.586 raw to **+2.521** normalized, i.e. the
> model UNDER-predicts on the frame it actually serves, while MAE improves 12.019 to
> 11.577 and Spearman 0.117 to 0.150. The shipped map then SUBTRACTS $2.32M from a model
> already too low in all eight bins, raising mean binned absolute error 2.52 to 3.05 and
> clamping the bottom three bins to zero, which IS the $0 floor. Re-fit on the production
> frame the intercept is **+1.233, positive**.
>
> **UPDATE 2026-07-31, same day: the re-fit was RUN and FAILED its gate**, losing to the
> shipped map on held-out MAE on 3 of 3 folds (11.518 shipped against 13.581 refit). The
> sharper claim above, that the calibration is pointed the wrong way, is **WITHDRAWN**: it
> is correctly pointed for an MAE objective, because 86 to 90% of the bottom bins realise
> nothing, the conditional MEDIAN is zero, and MAE is minimised by the median. What
> survives is the FRAME correction, which is real and is why the artifact was regenerated.
> Surplus dollars remain provisional for a DIFFERENT reason than this P0 gave: they are an
> MAE-optimal point forecast being consumed as an expected-value price, and the two
> objectives disagree by $1.7M to $3.9M per bottom-tier player. Rank claims remain the safe
> form. Full measurement: `docs/efv-2026-07-30/ZERO_FLOOR_PRICING_GATE.md` M5 and M6.
>
> **Original P0 text, 2026-07-25: the surplus calibration is fit on a different FV scale
> than production feeds it.** `surplus_backtest_real._load_inputs` medians the RAW
> per-source `fv` straight from the snapshots table with no grade normalization, and the
> shipped calibration (`config/valuation_sets/prospx_current.yaml`,
> `linearmap-v5-todaypriced-2026-07-24`, `corrected = max(0, 1.382491*raw - 2.318551)`,
> n = 2,236) was fit on that pool. Production prices on the NORMALIZED consensus. Before
> the normalization repair the two scales nearly agreed through the fat middle; after it
> they do not, and they diverge most at the top of the board. Until that calibration is
> refit on the normalized scale, treat surplus DOLLARS as provisional and make surplus
> claims in rank terms. The dollar-per-rank conversion above inherits the same caveat.

## 5. What this standard retires

- The "identity-variant refit movement" floor and the "+2x noise" ship bar.
- Post-hoc fringe gating on t45 without the t45 floor above (~0.055 hit / ~0.10 pit).
  `level_rank` shipped at t45 +0.0192, which is BELOW its own zero-information placebo p95
  of +0.0256.
- Single-split evidence of any kind.

## 6. Standing implication for the existing feature set

Of 22 shipped features exactly ONE (`fv`, hitters) is individually resolvable. That is NOT
a reason to prune: leave-one-origin-out backward elimination is out-of-fold NEGATIVE at
every depth (-0.0137 hit / -0.0159 pit), so the lean sets are already near the right
complexity and the eval simply cannot adjudicate their composition. **Do not add and do not
remove features on sub-floor evidence.** The block as a whole is real (block-permutation
null p <= 0.003 on all four cuts); its composition is not measurable.

## 7. SECOND INSTRUMENT: the conditional-on-train floor (added 2026-08-07b, Lane A1)

**This section ADDS a row. It retires nothing above it, changes no constant above it, and
retroactively resolves no past null.** Section 1's floors and `XFV_VS_CONSENSUS_MDE95`
(0.044) / `XFV_HEADTOHEAD_MDE95` (0.0352) are unchanged.

Registration `docs/efv-2026-08-07b/POWER_GATE.md` (parts 0-4 written before the lab
existed), producer `python tools/efv_power_lab.py all 2000`, ledger
`data/xfv_power_eval.json`, seed 20260807.

### 7.1 Two estimators, two questions. Say which one your claim is about.

| estimator | resampling | estimand | the question it answers |
|---|---|---|---|
| **E_refit** (section 1, shipped) | whole pool, train AND test, refit per draw | Var over redraws of the training corpus AND the scored sample | *what would we conclude from a different dataset* |
| **E_cond** (registered here) | scored rows only, per-fold fits held FIXED | Var over redraws of the scored sample given this training corpus | *given this training corpus, is this margin real* |

Both are legitimate. They are not competing estimates of one number. A published claim that
does not name its estimator is incomplete, because on at least one shipped cut the two
disagree about the verdict.

### 7.2 Registered floors, hitter and pitcher, 11-fold basis

Paired, B = 2,000, weighted pooled rho, same primitives as `tools/efv_mde_lab.py`.

| cut | n | E_refit MDE95 | **E_cond MDE95** |
|---|---|---|---|
| hit full_pool_km | 1,792 | 0.0289 | **0.0204** |
| pit full_pool_km | 1,885 | 0.0268 | **0.0218** |
| hit debuted_km | 755 | 0.0445 | **0.0213** |
| pit debuted_km | 890 | 0.0425 | **0.0301** |

MDE95 is ONE-SIDED (1.645 sd) here, the same convention as section 1. The gap is widest on
the small-train debuted pools, where refit variance dominates.

### 7.3 What earned the registration, and the trap it was built against

A tighter floor makes an improvement CERTIFIABLE. It does not CREATE one. So the criterion
was nominal coverage of the estimator's OWN estimand, not tightness, and the gate was coded
TWO-SIDED. Design-matched simulation, n_check = 200, acceptance region [0.920, 0.980]:

| estimator | own estimand | boot sd / true sd | coverage | gate |
|---|---|---|---|---|
| E_refit | unconditional | **1.465** | 0.970 | PASS |
| E_cond (iid) | conditional | **0.999** | 0.930 | PASS, REGISTERED |
| E_cond (fold-stratified) | conditional | 0.995 | 0.920 | PASS, sensitivity |

Centered false-positive rate at each estimator's own floor, nominal 0.10 for this
convention: E_refit **0.0167**, E_cond_iid **0.1250**, E_cond_strat 0.0917. Power against a
known alternative: 0.750 / 0.842 / 0.833. Both conditional estimators detect the known-real
hitter `fv` effect wherever the shipped one does.

Controls that could have killed the result and did not: the variance decomposition is
additive to within 8% (0.01258 test-only and 0.01132 train-only reconstruct 0.925x of the
0.01829 shipped sd), and the refit leg's extra width survives a truth whose cohort SIZES
also redraw (1.460 against 1.465).

### 7.4 THE ONE-SIDED COVERAGE GATE IS A DEFECT. Fix it where you find it.

`tools/efv_cohort_floor_lab.py` `nullcov` codes `passes = coverage_95 >= 0.90` with **no
upper bound**. An over-wide floor therefore reads as PASS. For a program whose product is
NULL verdicts, over-wide is the PERMISSIVE direction: it manufactures nulls. That gate
returns PASS for an estimator measured at 1.465x its true width.

**Any coverage check written from here on must be two-sided.** Use a central binomial
acceptance region for p = 0.95 at the checked n, and size n so the upper edge is strictly
below 1.000; at n = 40 it is not, so wave 1's `null_coverage_check` could not have failed
on over-coverage even if it had been coded correctly.

### 7.5 Consequence on a shipped cut

> **SUPERSEDED 2026-08-08, and the earlier claim is RETRACTED.** This section previously
> published hitter `full_pool_km` as **1.049x its floor, a RESOLVABLE LOSS** with bootstrap
> p(delta > 0) = 0.0415, on delta -0.02143 at n = 1,792. **That cell no longer resolves.**
> It is retracted explicitly rather than quietly amended because it was published as the
> one cell the conditional instrument could resolve, and other work may have leaned on it.

**Re-derivation on the rebuilt basis** (producer `python tools/efv_power_lab.py all 2000`,
seed 20260807, artifact `data/xfv_power_eval.json`; matrices and evals regenerated
2026-08-08 against a current consensus, record `docs/efv-2026-08-08/WAVE0_RECORD.md`):

| cut | delta | n | E_refit MDE95 | E_cond MDE95 | margin/floor (cond) | verdict |
|---|---|---|---|---|---|---|
| hit `full_pool_km` | **-0.01894** | 1,792 | 0.0296 | **0.0206** | **0.921x** | NULL |
| pit `full_pool_km` | +0.01398 | 1,883 | 0.0259 | 0.0212 | 0.660x | NULL |
| hit `debuted_km` | +0.01121 | 755 | 0.0437 | 0.0209 | 0.536x | NULL |
| pit `debuted_km` | +0.00612 | 889 | 0.0423 | 0.0290 | 0.211x | NULL |

**The floor barely moved (0.0204 to 0.0206). The DELTA moved**, from -0.02143 to -0.01894,
because the eval artifacts had been two days staler than the matrices and three days staler
than the consensus they read. The verdict flipped on the data, not on the instrument.

**The instrument re-validates on the new basis.** Two-sided coverage passes for all three
estimators (E_refit sd ratio 1.454, coverage 0.970; E_cond_iid ratio 1.000, coverage 0.930;
E_cond_strat 0.995, coverage 0.925, acceptance [0.920, 0.980]), and E_cond_iid re-registers
as primary exactly as pre-registered. Refit variance is **54.1%** of shipped variance
(shipped sd 0.01848, test-only 0.01253, train-only 0.01112), which is the measured reason
the 4-to-11-fold promotion bought no power and why more cohorts cannot buy it either.

**E_cond now resolves NOTHING in the four pre-registered cuts, in either direction.** The
"it resolved exactly one cell and it was a loss" argument for the instrument's honesty no
longer applies as written; the standing check is instead that its detection behaviour is
unchanged (it still detects the known-real hitter `fv` effect wherever E_refit does, and
misses where E_refit misses). **A tighter floor still does not create a result**, and on
current data it certifies neither a win nor a loss.

**Standing lesson, worth more than the number.** Every margin in this document is a
function of a regen. Adjudicating a cell against artifacts that are even two days stale can
cross a verdict boundary. Re-read the margins after any regen, before publishing.
