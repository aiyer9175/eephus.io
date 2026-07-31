# Pitcher Label Instrument - Loss Ledger (2026-07-24)

Prototype program for a pitcher label instrument, run as a 13-agent workflow
(4 diagnostics -> 5 candidate instruments -> 3 adversarial verifiers -> synthesis).

**Verdict: NO-SHIP on all five candidates, and the lane is CLOSED on economic grounds.
The measurement instrument failed before the label instruments did.**

## The correction that matters

This program was launched on a premise from the earlier surrogate gate: that the pitcher
ORACLE (true first-6yr WAR on the recently-censored cohorts) lifts the model's blend
Spearman from 0.1164 to 0.2260, "proving" +0.1096 of real label headroom for arms.

**That premise was substantially a measurement artifact.** Measured this session:

| control label on the censored block (span 3) | blend rho | "% of headroom" |
|---|---|---|
| constant at the KM mean (zero information) | 0.2115 | **86.8%** |
| uniform noise (zero information) | 0.2402 | **113.0%** |
| KM + 1.8 (rank-identical to KM) | - | 37.3% |
| best real candidate | 0.1312 | 13.5% |

Mechanism: the KM-labelled censored block is *actively destructive* training data for the
small unweighted ridge (ridge arm: KM 0.0627, constant 0.2161, oracle 0.2174). Anything
that neutralizes its leverage scores well while carrying zero information. The gate was
measuring **label damage removal, not label information**.

Permutation null (B=1500, mid labels shuffled, marginal preserved exactly): the oracle
itself has **p(null >= real) = 0.183**. The entire quantity was inside the noise floor.

Under the **shipped** fit configuration (sample_weight = observed_seasons/6 per
`prospect_path._fit_ridge`, plus the ~1008 bust rows `efv_model.fit_production_stack`
actually trains on), the censored block's leverage falls 37.9% -> 14.3%, and a **perfect**
label is worth **+0.0518** at span 3 and **+0.0248** at production's real mixed spans -
roughly a quarter of the advertised headroom.

Also corrected: the univariate isotonic surrogate was reported at +2.7% of headroom; two
independent re-runs measure **-2.7%**. A sign flip, recorded honestly.

## Why the lane is closed (the economic bound)

Deleting the ENTIRE censored pitcher block from production - the maximum possible
perturbation any label instrument could ever cause - moves the served pitcher board by
Spearman **0.9441**, mean **|dWAR| 0.204**, top-50 churn **4**. Every actual candidate's
served effect: rho 0.9976-0.9993, mean |d| 0.077-0.102, top-50 churn 1-2.

**The whole censored-pitcher-label problem is worth less than a rounding change to the
shipped board.** No instrument, however clever, can be worth more than that bound.

## Candidates (all NO-SHIP)

| candidate | best reported | official span-3 delta | cross-split mean (4 splits) | production-config delta |
|---|---|---|---|---|
| rateanchored | span4 208.9% | +0.0148 (P=0.62) | **-0.0133** (neg on all 4) | -0.0057 |
| longhorizon | span4 65.2% | +0.0026 (P=0.53) | **-0.0124** (neg on all 4) | -0.0015 |
| twopart | span3 54% | +0.0592 | not run | not run |
| multivariate | span3 15.6% | +0.0171, CI95 crosses 0 | not run | not run |
| roleconditioned | span3 15.4% | +0.0169, CI95 crosses 0 | not run | not run |
| *control: drop the block* | 34.5% | +0.0378 | +0.0320 (best of anything) | -0.0372 |

Two real code-level defects found by verification (in prototypes, never shipped):
`rateanchored.py:276-280` extrapolates past the observed range unclamped and labels
paul_skenes at **50.99** six-year WAR; `longhorizon.py:92-93` loops `range(TARGET_SEASONS)`
instead of `range(span)` - a temporal leak that is inert in-sim but live in production.

## Mechanical findings that DO stand (reusable knowledge)

1. **Attrition dominates mass, not rank.** Seasons 4-6 hold 58.9% of pitcher 6yr WAR mass
   and 45.0% of its variance; 32.8% of debuted pitchers throw zero MLB innings there.
   Survival is highly predictable early (out-of-sample AUC 0.758 -> 0.865 from workload and
   role). But an ORACLE survival flag moves label rank only 0.7983 -> 0.8047 (+0.006 of a
   0.202 gap). **Do not build a survival classifier expecting rank lift.**
2. **The binding constraint is magnitude-among-survivors.** Among 356 survivors, early WAR
   gets rho 0.4149 with late WAR and no early feature adds partial rho above 0.16
   (gs 0.160, ip_per_season 0.155, kbb 0.141).
3. **The label failure is a two-sided top-tail swap.** 3-year WAR under-ranks slow-burn aces
   (burnes 13.83 true vs 1.30 KM; giolito 10.33 vs -0.54) and over-ranks fast-start
   innings-eaters (fulmer 11.58 vs 20.90). Rows with TRUE >= 5 WAR are 24.2% of the block but
   carry **87.9%** of squared label error. Any monotone function of war3 structurally cannot
   fix this, which is why every isotonic-on-war3 arm returns ~0.
4. **Label fidelity does not predict model lift, and sometimes anti-predicts it.** span-5
   labels are near-perfect (rho 0.9665) yet score below span-4. Both leading candidates'
   winning arms have WORSE label rho than KM. Selecting on rho/MAE would have rejected every
   arm that scored.
5. **n is the binding constraint, not modeling.** 216 early rows to fit an instrument, 348 to
   fit an 8-feature ridge, 180 test rows, arm-level bootstrap sd ~0.074. Hyperparameters were
   NOT fragile (15/15 and 9/9 configs same-sign); the sample is. Progress needs pooling and
   repeated averaged splits, not a cleverer label.
6. **Shipped-pipeline observation.** `_BLEND_LAMBDA_RESELECT["pit"] is None`, so the served
   pitcher blend lambda is re-derived each run by `rank_calibration("pit")`, whose target IS
   `target_censored` - 75.8% of the selector's scored rows are the censored block. Any future
   label experiment must PIN that lambda, or a synthetic label silently moves the served
   blend weight (one arm would have moved it 0.54 -> 0.65 on nothing but its own labels).

## Dead ends - do not spend another slot on these

Role-conditioned calibration maps (4 arms, all negative, -0.6% to -12.2%); survival
classifiers as a rank instrument; univariate isotonic on war3; TJ/injury as an attrition
feature (partial rho 0.073); ERA as a hazard feature (0.022); span >= 5 (dominated by span 4
at 2x the latency and 23.3% coverage).

## If this is ever revived (pre-registered)

**Arm 0 (mandatory first):** rebuild the gate - production fit config (sample weights +
busts), real mixed spans (2021@5 / 2022@4 / 2023@3 / 2024@2), three mandatory controls beside
every arm (rank-identical level twin, random-label null band over >=20 seeds, permutation
p-value), train-resampling bootstrap rather than test-only, deltas averaged over >=6 time
splits, `Z_drop_censored` promoted to the bar in place of KM, and a pinned pitcher lambda.

**Arm 1 (the only hypothesis with clean evidence):** a hazard x magnitude label whose hazard
covariates are strictly NON-WAR (ip_per_season, ip_last, ip_slope, seasons_pitched,
appear_frac, gs_ratio + drift, exposure-shrunk kbb/k_pct, age_debut) with a multiplicative
magnitude arm (IP_hat x (WAR/IP)_hat), at span 2-3 only. Evidence: twopart's U3 ablation is
the one clean positive in the program (non-WAR hazard covariates give +0.0363 at span 3;
WAR-only gives +0.0004). Ship only if the mean paired delta across >=4 independent splits is
> 0 at P > 0.95 under production config AND it beats both its rank-identical level twin and
the drop-censored control. Prior probability on current evidence: low.

**Arm 2 (highest expected value): stop working this lever.** See the economic bound above.
