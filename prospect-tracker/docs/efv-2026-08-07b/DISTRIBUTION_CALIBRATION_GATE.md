# Lane C1 gate: was the reliability diagnostic measuring its own label?

Master plan: `docs/master-plan-2026-08-07b-efv-audit.md`, defects D3 and D4, lane item C1.
Upstream input: Lane B1, `data/xfv_label_censoring_eval.json`, gate
`docs/efv-2026-08-07b/LABEL_CENSORING_GATE.md`.

**This file is written BEFORE the lab exists and BEFORE any arm is run.** Section 5 is a
literal placeholder and is the ONLY section that may be edited after the run. Nothing in
sections 1 to 4 may be touched once the lab has executed.

## 0. Scope limit, restated so it cannot be forgotten

This lane produces a MEASUREMENT and a recalibration brief. It does NOT recalibrate.
No edit to `p_bucket_given_fv`, to `value_framework_config.yaml`, to the odds-dispersion
Platt layer, or to any served number. A change to any of those moves surplus dollars for
the whole board and requires a `prospx_current.yaml` re-capture inside
`with vf.valuation_set("prospx_current")` plus a re-stamp of the 20-cell acceptance grid at
`test_valuation_sets.py:66-79` and the FV50 literal at `:150`. Capturing on the default set
silently yields a different grid, pitcher FV60 reading 75.2 rather than the correct 81.3.
That has cost a full cycle before.

Files this lane may write: `efv_reliability.py`, `tools/efv_dist_calibration_lab.py`,
`data/xfv_dist_calibration_eval.json`, this document. Nothing else.

## 1. The question

D3 says the SERVED (post-Platt, `after`) five-bucket outcome distribution is miscalibrated
monotonically in consensus-FV tier: realized `bust` exceeds predicted `bust` at every tier
at or below 45, and predicted `good`/`star` exceed realized at 55 and 60. Pooled bust ECE
is 0.07907 against a `BUST_ECE_TRIPWIRE` of 0.10, so the wire does not fire.

D4 says the diagnostic's realized bucket is `target_censored / 6.0`
(`efv_reliability._realized_bucket`, `:91-95`) computed on a pool prepared as
`_prep(pool, "target_censored", side)` (`:119`), where censored rows carry
`observed_seasons` of 2 to 5 and the label's unobserved tail is a FLAT per-season rate
projection.

B1 measured that projection and found it biased PESSIMISTIC, monotone in span. A
pessimistic label makes realized outcomes look worse than they were: it inflates realized
`bust` and deflates realized `good`/`star`, which is the sign of the observed
miscalibration at every tier.

**Question:** how much of the D3 miscalibration is the diagnostic grading the model against
its own label error, and how much survives a corrected label?

## 2. Design

### 2.1 What is held fixed

In all three primary arms the forward-chained out-of-fold chain is the SHIPPED one:
`efv_reliability._oof_rows`, `CHAIN_YEARS = range(2016, 2024)`, `MIN_TRAIN = 60`,
`MIN_TEST = 10`, ridge plus linear output calibration fit on `target_censored`, grade
inversion through `vf.realized_implied_fv` at `exposure_seasons = 6`, then
`vf.p_bucket_given_fv` and the odds-dispersion Platt map
`efv_odds_calibration.recalibrate_bucket(..., provisional=not src.get("milb"))`.

The PREDICTED distributions `p_before` and `p_after` are therefore IDENTICAL row-for-row
across arms (a), (b) and (c). Only the realized bucket `y` and the set of evaluated rows
change. This is deliberate: it isolates label quality from model behaviour. An arm that
also refits the model on the corrected label is run separately as a non-primary
sensitivity, arm (d), and is labelled as such.

### 2.2 The arms

- **(a) SHIPPED.** Every out-of-fold eval row. `y = bucket(target_censored / 6.0)`.
  Must reproduce the shipped `data/xfv_reliability.json` numbers to the printed precision;
  a mismatch beyond regeneration drift is a stop condition (see 4.0).
- **(b) RESOLVED ONLY.** Eval rows with `censored == False`. Labels unchanged (for these
  rows `target_censored == target_resolved` by construction).
- **(c) CORRECTED.** Every out-of-fold eval row. `y = bucket(corrected_target / 6.0)`,
  where `corrected_target` is the season-share ratio estimator defined in 2.3 on censored
  rows and is EXACTLY the shipped target on every other row.
- **(d) SENSITIVITY, non-primary.** Full chain refit with the corrected label as the
  training target as well as the evaluation label. Reported for robustness only. It does
  not determine the verdict.

### 2.3 The corrected label

`efv_dataset._label_6yr` censored branch projects the tail at the observed per-season rate:
`censored_target = obs_sum + (6 - n_obs) * obs_sum / n_obs = obs_sum * 6 / n_obs`.
That assumes each of the six post-debut seasons carries an equal share of the six-year WAR
total, which B1 showed is false: the mass is back-loaded.

The corrected label replaces the flat share with the EMPIRICAL season-index share profile:

    share_i = mean_WAR_at_season_index_i / sum_j mean_WAR_at_season_index_j,   i = 0..5
    S(k)    = sum_{i < k} share_i
    corrected_target = obs_sum / S(n_obs)

`share_i` is computed per side (`hit`, `pit`) on the FULLY RESOLVED debuted pool
(`debut_year + 6 - 1 <= RESOLVED_THROUGH`, i.e. debut year at most 2020), joined to the
`career_war` table, which is the same source `_label_6yr` reads. Censored rows all have
debut year 2021 or later, so the profile is fit on a player set DISJOINT from the rows it
corrects. It is nevertheless an in-sample fit on the resolved cohort and is applied
out-of-cohort; SENS-1 below tests that.

`obs_sum` is recomputed directly from `career_war` and reconciled against the shipped
`target_censored` (which must equal `round(obs_sum * 6 / n_obs, 3)`). A reconciliation
mismatch rate above 1 percent is a stop condition.

The identity `corrected_target = target_censored * (n_obs / 6) / S(n_obs)` holds, so the
correction is a per-`n_obs` multiplicative factor `f(side, n_obs) = (n_obs / 6) / S(n_obs)`,
which is at least 1 whenever the mass is back-loaded.

### 2.4 Metrics

Computed with the SHIPPED functions, not reimplementations: `_reliability_bins`
(10 equal-width probability bins, bins with fewer than 5 rows dropped) and
`_tier_reliability` (`_tier` = FV rounded to nearest 5, `MIN_TIER_N = 15`), both on
`key = "p_after"`, the served distribution D3 reports.

- **M1 (primary):** pooled `bust` ECE on `after`. This is the tripwire's own quantity.
- **M2 (primary):** n-weighted mean per-tier `gap`. Unweighted mean reported beside it.
- **M3:** pooled ECE for all five buckets.
- **M4:** signed per-tier residual `realized_freq - mean_p` for `bust`, `good`, `star`.
  This carries the SIGN the hypothesis predicts and is the sharper test: the hypothesis
  says the correction should move realized bust DOWN and realized good/star UP.
- **M5:** per-tier censored share, so the reader can see which tiers can move at all.

### 2.5 Sensitivities

- **SENS-1, cohort drift in the share profile.** Refit `share_i` on debut years 2011-2015
  only, and again on 2016-2020 only, and re-run arm (c) with each. If the two disagree by
  more than the (a)-to-(c) movement itself, the corrected label is not stable enough to
  support a conclusion and the lane reports the contrast as unresolved.
- **SENS-2, arm (d)**, the refit chain, as described above.

## 3. Controls. These are pre-registered and will be reported whatever they say.

- **CTRL-0, no-op on resolved rows.** `corrected_target` must equal the shipped target
  EXACTLY on every row with `censored == False`. Any mismatch invalidates arm (c).
- **CTRL-1, zero-information constant.** Apply a SINGLE global multiplicative constant to
  every censored row's label, chosen so the pooled mean corrected label matches arm (c)'s
  pooled mean. This carries no information about `n_obs`. If it reproduces 80 percent or
  more of arm (c)'s M1 reduction, the finding is a LEVEL effect and must be reported as
  "the censored labels were too low on average", NOT as "the flat-rate shape was wrong".
- **CTRL-2, permuted correction factors.** Permute the per-row factors `f(side, n_obs)`
  among censored rows within side, 200 draws, seed 20260807. This preserves the marginal
  distribution of corrections and destroys the row-level correspondence. Report the mean
  and the 5th/95th percentile of the M1 reduction under permutation. If arm (c) does not
  sit outside the permutation band, the correction carries no row-level information.
- **CTRL-3, wrong direction.** Apply the reciprocal factor (deflate the censored labels).
  M1 and M2 must get WORSE. If deflating also improves them, the metric is not measuring
  what this gate assumes and the lane reports NULL.
- **CTRL-4, composition decomposition.** Because arms (a) and (c) agree exactly on every
  resolved row, and arm (b) is exactly that set of rows, the following identity must hold
  numerically and will be printed:
  `M(a) -> M(b)` decomposes as `[M(a) -> M(c)]` (label only, same pool) plus
  `[M(c) -> M(b)]` (composition only, labels unchanged on the retained rows).
  The (a)-to-(b) contrast is CONFOUNDED and will only ever be quoted with that label
  attached. The (a)-to-(c) contrast is the measurement.
- **CTRL-5, ceiling.** Report the number of rows whose realized BUCKET actually changes
  under the correction. If that count is small relative to the pool, state the mechanical
  ceiling on how much of D3 the correction could possibly explain, before interpreting.

## 4. Decision rule, fixed now

### 4.0 Stop conditions

- Arm (a) fails to reproduce the shipped `xfv_reliability.json` bust ECE to within 0.005.
- `obs_sum` reconciliation mismatch above 1 percent of censored rows.
- CTRL-0 fails.
- CTRL-3 fails (deflation improves calibration).

Any stop condition means the lane reports NULL and hands the design to a later wave.

### 4.1 Verdict

Let `R1 = 1 - M1(c) / M1(a)` and `R2 = 1 - M2(c) / M2(a)`, both computed on the SAME pool.

- **CONFIRMED, "the diagnostic was measuring its own label":** `R1 >= 0.50` AND
  `R2 >= 0.50`, with CTRL-1 below 0.80 and arm (c) outside the CTRL-2 band.
- **PARTIAL:** `max(R1, R2) >= 0.20` but the CONFIRMED bar is not met. The lane reports how
  much is label and how much survives, and hands a scoped brief for the remainder.
- **FALSE / SURVIVES:** `max(R1, R2) < 0.20`. The D3 miscalibration is not a censoring
  artifact. The lane hands a scoped recalibration brief to a later wave.

**Disclosure required by the wave-2 standing rules:** the 0.50 and 0.20 bars, and the 0.80
CTRL-1 bar, are thresholds this gate ADDS. The master plan says only "shrinks materially"
and does not quantify it. If either bar determines the verdict, the report must say so in
its headline.

### 4.2 The one permitted fix, the tripwire bar

Secondary, and only reported, not shipped by this lane. The orchestrator decides.

`BUST_ECE_TRIPWIRE = 0.10` watches POOLED bust ECE. Two questions:

1. Can that statistic express the D3 defect at all? The defect is monotone IN TIER; a
   pooled ECE over probability bins may be structurally blind to it. Report the pooled bust
   ECE that the D3 tier pattern actually produces.
2. If a corrected bar is proposed, it must come with a FALSE POSITIVE RATE measured on
   HELD-OUT FOLDS: leave-one-chain-year-out, recompute the statistic on each held-out fold,
   and report the fraction of folds that would fire at the candidate bar in the system's
   CURRENT state. A bar whose held-out nuisance-alarm rate exceeds 0.25 is not proposed.
   The bar must also retain the existing regression-test property: it must still fire if
   the Platt map is silently dropped, i.e. it must sit below the `before` value.

## 5. RESULT (appended after the run)

Lab: `tools/efv_dist_calibration_lab.py`. Artifact: `data/xfv_dist_calibration_eval.json`,
generated 2026-08-08T01:55:13Z. Every number below reproduces from that file.

### 5.1 Verdict: SURVIVES. The D3 miscalibration is NOT a censoring artifact.

| arm | n | bust ECE | tier gap (n-weighted) |
|---|---|---|---|
| (a) shipped | 2,822 | 0.07908 | 0.04068 |
| (b) resolved only, CONFOUNDED | 2,199 | 0.10208 | 0.04567 |
| (c) corrected label, same pool as (a) | 2,822 | 0.07660 | 0.03883 |
| (d) refit chain, non-primary | 2,822 | 0.07653 | 0.03894 |

`R1 = 0.03136`, `R2 = 0.04548`. Both are far below the pre-registered PARTIAL bar of 0.20
and roughly one sixteenth of the CONFIRMED bar of 0.50. **The 0.20 bar did NOT determine
the verdict**: the measured reduction is 3 to 5 percent, so any bar between about 0.06 and
0.50 returns the same answer.

All four stop conditions passed. Arm (a) reproduces the shipped
`xfv_reliability.json` bust ECE to 1e-5 (0.07908 against 0.07907; n 2,822 against 2,823,
one row of regeneration drift). `obs_sum` reconciled 833 of 833 censored rows with zero
mismatches. CTRL-0 held on all 3,030 resolved rows exactly. CTRL-3 deflation made both
metrics worse (0.08227 and 0.04281), so the metrics respond in the expected direction.

### 5.2 Why. Three independent reasons, all measured.

**Reason 1, the worst-biased span is not in the frame.** B1's headline (-1.691 WAR hitters,
30.26 percent bucket change, 2-to-1 pessimistic) is the `n_obs = 2` stratum. The reliability
chain runs `CHAIN_YEARS = 2016-2023`, and its 623 censored eval rows carry
`observed_seasons` of 3 (218), 4 (228) and 5 (177). **There is not one `n_obs = 2` row in
the frame.** The applicable correction factors, derived from the empirical season-share
profile and matching B1's measured ratios to four decimals, are 1.252 / 1.077 / 1.013
(hitters) and 1.215 / 1.078 / 1.019 (pitchers).

**Reason 2, a mechanical ceiling of 1.24 percent.** Applying the corrected label changes the
realized bucket of 35 of 2,822 rows (5.6 percent of the censored rows), all 35 upward, which
is the direction the hypothesis predicts. Thirty-five rows cannot carry a 0.079 pooled ECE.

**Reason 3, the tiers that dominate the statistic are made of rows censoring cannot touch.**
Tiers 35 and 40 hold 2,212 of 2,822 rows (78 percent). Of the realized-bust rows there,
83.39 percent (512 of 614, tier 35) and 67.30 percent (998 of 1,483, tier 40) are
`kind == "bust"` never-debuted rows
whose label is exactly 0.0 with `censored == False`. No tail-projection correction reaches
them. The censored share does rise monotonically with tier (0.150 / 0.186 / 0.336 / 0.462 /
0.364 / 0.406 at 35/40/45/50/55/60), which is why the hypothesis was worth testing, but the
rows are concentrated where censoring is rarest.

### 5.3 The sign story is more complicated than D3 states, and it cuts both ways.

The signed bust residual (realized minus predicted) under arm (a) is
+0.0506 / +0.1046 / +0.1169 at tiers 35/40/45 and **-0.0443 / -0.0219 / -0.0397** at
50/55/60. Bust is UNDER-stated at the bottom and OVER-stated at the top. A pessimistic-label
correction can only push realized bust DOWN, so it is the right medicine below 45 and the
wrong medicine above it. That is visible in arm (c): the tier-45 gap improves 0.05370 to
0.04975 and the tier-50 gap improves 0.05125 to 0.04050, but **the tier-55 gap gets WORSE**,
0.07231 to 0.07750. Tier 60 does not move at all. The top-of-board defect that D3 correctly
identifies (predicted `good` 0.2245 against realized 0.1039 at tier 55) is an
OVER-prediction of `good`/`star`, and correcting the label makes realized `good` rise, which
is directionally right, but the effect is 0.0 at tier 55 and only +0.0107 at tier 50.

### 5.4 Controls. Two of them cut against this lane and are reported anyway.

- **CTRL-1, zero-information constant.** A single global factor of 1.176 applied to every
  censored label reproduces **128.6 percent of R1 and 137.3 percent of R2**, i.e. the dumb
  constant beats the shaped correction. `level_effect_only` is true. Whatever tiny movement
  exists is a LEVEL effect, not a vindication of the season-share shape.
- **CTRL-2, permuted factors, 200 draws, seed 20260807.** Permuted R1 band [0.03591,
  0.07625], mean 0.05512. The actual R1 of 0.03136 sits BELOW the 5th percentile. It is
  "outside the band" as the gate's clause is literally written, but on the refuting side:
  one-sided permutation p is 0.975 for R1 and 1.000 for R2. Shuffling the correction factors
  among censored rows does BETTER than assigning them correctly. The `n_obs` shape carries
  no calibration-improving row-level information at the spans present here. **Disclosure: the
  gate's CONFIRMED clause tested `outside_band` two-sided, which would have been satisfied by
  this refuting result. It is moot, because R1 and R2 fail the 0.50 bar by an order of
  magnitude, but the clause was loosely written and is recorded as such.**
- **CTRL-4, composition decomposition.** The identity holds exactly. For bust ECE, the
  (a)-to-(b) move of +0.02300 splits into **-0.00248 label-only** and **+0.02548
  composition-only**. Composition is 111 percent of it and points the opposite way. The
  resolved-only pool is MORE miscalibrated, not less. Anyone who had "cleaned" this
  diagnostic by restricting it to resolved rows would have pushed bust ECE to 0.10208 and
  TRIPPED the wire, entirely on cohort composition. The (a)-to-(b) contrast is quoted here
  only with that label attached.
- **CTRL-6, ORACLE upper bound. Added after the primary run, and it partly embarrasses this
  lane.** Relabelling the 623 censored rows FREELY to whatever minimises pooled bust ECE
  reaches 0.00643, a maximum possible R1 of **0.919**. So the censored rows are numerous
  enough in the informative probability bins that a label correction is not structurally
  incapable of erasing D3. The SURVIVES verdict is therefore a claim about PLAUSIBLE
  corrections, not about censoring in the abstract, and CTRL-7 is what bounds it.
- **CTRL-7, how large would the label error have to be.** Uniform multiplicative factor
  scan on the censored labels: R1 reaches 0.121 at 1.5x, 0.211 at 2.0x, 0.354 at 3.0x,
  0.497 at 10x, and crosses 0.50 only near 25x. The n-weighted tier gap bottoms out at 3.0x
  (0.03213, R2 =
  0.21) and gets WORSE beyond it, so R2 never reaches 0.50 at any factor. B1 measured
  1.25x / 1.08x / 1.01x for the spans in this frame. **Reaching the CONFIRMED bar needs a
  label error roughly 10x to 25x the one B1 measured, and the tier gap cannot be brought
  there at all.** Only 2 of the 623 censored eval rows have zero observed WAR, so the
  immovable share (0.32 percent) is not the binding constraint; magnitude is.

### 5.5 Sensitivities

- **SENS-1, cohort drift.** Fitting the share profile on 2011-2015 debuts gives R1 = 0.018;
  on 2016-2020 debuts, R1 = 0.049. The spread (0.031) equals the effect itself, which is a
  fair warning about the profile's stability, but BOTH ends are an order of magnitude below
  the PARTIAL bar, so the verdict does not turn on it.
- **SENS-2, arm (d), refit chain.** The mirror of `_oof_rows` reproduces the shipped chain
  byte-identically with no override (max `p_after` delta 0.0, zero `y` differences, both
  sides). Refitting the model on the corrected label as well gives R1 = 0.032, R2 = 0.043,
  indistinguishable from arm (c). The conclusion does not depend on holding predictions
  fixed.

### 5.6 The tripwire. The plan's framing is half right.

**The 0.10 bar is not structurally blind.** Defect injection: flipping realized non-bust
outcomes to bust among the 177 eligible tier-50-and-above rows (the realistic worsening, an
over-priced `good`/`star` top of board) drives pooled bust ECE to 0.09235 at 25 percent
flipped (+0.148 mean signed bust residual in band) and **0.10794 at 50 percent (+0.285),
which TRIPS the wire**. So a large top-of-board defect does fire it. What is true is that
the bar sits above the STANDING state by design (it was set at roughly 1.33x the served
0.0754 baseline as a drift wire) and therefore cannot fire on a defect of the size D3
actually reports.

**Recommended bar: 0.09.** Measured on a block bootstrap over chain-year folds (B = 1,000,
seed 20260807), which is the right estimator because the shipped wire judges the POOLED
value, not a per-fold one. Pre-registered per-fold counts are in the artifact beside it.

| bar | nuisance-alarm rate, current state | detection if the Platt map is dropped |
|---|---|---|
| 0.080 | 0.484 | 1.000 |
| **0.090** | **0.199** | **1.000** |
| 0.100 (shipped) | 0.069 | 0.998 |
| 0.110 | 0.019 | 0.923 |

0.09 is the tightest bar meeting the pre-registered FPR ceiling of 0.25. It keeps the
regression-test property (the pooled `before` bust ECE is 0.12748, bootstrap mean 0.12771,
and detection is 1.000), it
does not fire on the current state (0.07908), and it needs NO test re-stamp: the existing
band assertion at `test_efv_levers.py:51-52` requires only `0.0754 < bar < 0.1281`. It moves
the top-of-board detection threshold from a +0.285 signed bust residual to +0.148.

**Not proposed, handed to a later wave:** no bar on POOLED bust ECE can be made sensitive to
a top-of-board defect at an acceptable alarm rate, because tiers 50 and above are 295 of
2,822 rows and can contribute at most 10.5 percent of the statistic, while that is exactly
where the surplus dollars are. The wire needs a SECOND, tier-located statistic. This lane
does not ship one.

### 5.7 Brief handed forward (C2 is now unblocked and required)

D3 stands. The distribution is genuinely miscalibrated and the miscalibration is not the
diagnostic's own label. The remainder, with the shapes a recalibration must fit:

1. **Bottom of the board, tiers 35-45, 2,516 rows.** `p_bust` is under-predicted by +0.051 /
   +0.105 / +0.117. Non-bust mass is spread too thickly across low-FV prospects. This is the
   larger n but the smaller dollar consequence.
2. **Top of the board, tiers 50-60, 295 rows.** `good` is over-predicted by -0.042 / -0.121 /
   -0.050 and at tier 60 `star` is predicted at 0.2143 against a realized 0.0000 on n = 32.
   Since surplus is `sum(P(bucket) x bucket_surplus)`, this is the over-priced end.
3. **Constraints that bind C2**, restated: gate on calibration (ECE, reliability slope,
   held-out bias) with log score beside it; forward-chained OOF with held-out folds; a
   permuted-tier control; and the full `prospx_current.yaml` re-capture and 20-cell grid
   re-stamp described in section 0.
4. **The label is still biased even though it is not the cause of D3.** B1's `n_obs = 2`
   stratum enters the PRODUCTION fit (833 rows ride the projection, expected total label
   bias -470 WAR) even though it does not enter this diagnostic's 2016-2023 chain. That is a
   Lane B item, not a Lane C one, and this measurement neither supports nor refutes it.

