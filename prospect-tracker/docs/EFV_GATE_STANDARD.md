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

| statistic class | MDE95 |
|---|---|
| model vs consensus, pooled rho | **~0.045** (all four cuts) |
| incremental feature add, pooled rho | **~0.017 hit / ~0.016 pit** |
| blend-lambda shift, pooled rho | **0.0076-0.011 hit / 0.005-0.008 pit** |
| FV-45 fringe t45 | **~0.055 hit / ~0.10 pit** |
| MAE delta | 0.20 hit-debuted / 0.06 pit WAR |

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

> **+0.01 pooled eFV Spearman = -$0.0704M surplus MAE per prospect**
> CI95 [-0.0878, -0.0550], P(improves) = 1.000, n = 2,236 resolved listings.

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
