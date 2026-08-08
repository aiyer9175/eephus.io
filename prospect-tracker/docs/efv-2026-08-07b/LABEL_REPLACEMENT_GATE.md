# LABEL REPLACEMENT GATE (Lane B2, 2026-08-07b): one candidate for the censored-tail projection, and whether it carries information

**STATUS OF THIS FILE.** Parts 0 through 7 are the PRE-REGISTRATION. They were written in
full, including every PASS clause, every control, every threshold and the stop clause,
BEFORE `tools/efv_label_replacement_lab.py` existed and therefore before any number in
part 8 could be known. Part 8 is a placeholder filled in after the run. Nothing in parts 0
to 7 is edited afterwards.

One data probe was run before this file was written, and it is disclosed here so the
timeline reconstructs: the per-debut-year ROW COUNTS of the resolved pool (part 3.2). No
error, bias, projection or score was computed before this file was complete.

---

## 0. What is on the table

`efv_dataset._label_6yr` (efv_dataset.py:900-919) projects the unobserved tail of the
six-year bWAR label at the OBSERVED per-season rate:

```
rate = obs_sum / n_obs
censored_target = obs_sum + (6 - n_obs) * rate     # equivalently obs_sum * 6 / n_obs
```

Lane B1 (`data/xfv_label_censoring_eval.json`) measured this by truncation replay on 988
fully resolved rows and found it UNDER-states at every span: pooled mean bias -1.2354 at
n_obs = 2, decaying toward null by n_obs = 5. B1's own materiality rule marked exactly one
span-side cell MATERIAL: `n2_hit`, bias -1.6906, CI95 [-2.0907, -1.2674]. 833 shipped rows
ride the projection.

**B1's narrowing is carried here and is not re-opened.** The magnitude ladder B1 printed
(-2.55 at 3to9, -4.52 at 9to15, -7.03 at 15to24) is what a single multiplicative rescale
error looks like when it is expressed at a higher level. It is not independent top-end
damage and this lane does not treat it as a separate target.

## 0.1 The trap, stated so it can be checked against the result

The candidate below is, within any fixed span `n`, a POSITIVE SCALAR MULTIPLE of
`obs_sum`. So is the shipped projection. **Within a span the two are RANK-IDENTICAL by
construction.** Any rank movement this lane can produce comes only from rows at different
spans moving relative to each other. This is stated up front so that no rank claim can be
smuggled in later, and it is why the gate is on error, not on rank.

Second trap. A pooled share profile estimated on the same rows it scores has ZERO mean bias
BY CONSTRUCTION: the multiplier is exactly `mean(true) / mean(obs_sum)` on those rows. A
zero-bias result from an in-sample profile is failure mode G, a clause that could not have
failed. Every scored number in this lane comes from a FORWARD-CHAINED profile that never
saw the cohort it scores.

Third trap, and the one the pitcher label ledger paid for. "A label-quality scoreboard
built on a small held-out blend Spearman measures label DAMAGE, not label INFORMATION."
So the gate is the direct held-out truncation error, and the rank diagnostic is reported
against its own reference and gates nothing.

## 1. The candidate. Exactly one, and no others are built.

**PER-SEASON-INDEX SHARE PROFILE, forward chained.**

On resolved rows from STRICTLY PRIOR debut cohorts, estimate the mean bWAR realized in
season index k = 1..6, `m_k`. Define the share profile `s_k = m_k / sum_j m_j` and the
cumulative share `S_n = sum_{k<=n} s_k`. Project:

```
candidate_target(n) = obs_sum / S_n           equivalently  obs_sum * sum_j m_j / sum_{k<=n} m_k
```

The shipped projection is the special case `S_n = n / 6`, i.e. the assumption that every
season index carries an equal share. B1's pooled profile measured
0.0804 / 0.1383 / 0.1853 / 0.2150 / 0.2018 / 0.1792, so `S_2 = 0.2187` against the shipped
0.3333. That is the whole mechanism.

**Two arms, both estimated forward chained, both reported whatever happens:**

- **POOLED profile** (hitters and pitchers together). PRIMARY. B1 measured seasons-4-to-6
  shares of 0.6007 hit and 0.5883 pit, which is close, but "close" is an assumption and
  part 6.5 tests it rather than asserting it.
- **PER-SIDE profile**. SENSITIVITY.

**Selection rule, fixed now to prevent selection on outcome.** POOLED is the arm that can
be recommended. PER-SIDE is registered as the recommendation ONLY if POOLED fails its gate
AND PER-SIDE passes, and in that case the substitution is disclosed in the headline as
post hoc. Both are reported in full either way.

## 2. The scoring statistic, and the floor for it

Truncation replay, exactly B1's design: take a fully resolved row, patch
`efv_dataset.RESOLVED_THROUGH` to `debut_year + n - 1`, read `obs_sum` and the shipped
projection from the SHIPPED `_label_6yr`, and compare against the six-year total that is
already known. No reimplementation of the shipped function.

Per row, per span `n` in {2, 3, 4, 5}:

```
d_i(n) = (candidate_i - true_i)^2 - (shipped_i - true_i)^2
DELTA_MSE(n) = mean_i d_i(n)                       negative = candidate better
```

**PRIMARY statistic: `DELTA_MSE`.** Chosen because it is the only one of the three that can
separate the candidate from its level twin: a pure level shift and a pure rescale both drive
mean bias to zero, so mean bias cannot discriminate and is descriptive only. MSE decomposes
into bias squared plus error variance, so a bias fix that costs more variance than it buys
shows up here and nowhere else.

**SECONDARY, reported always, gating nothing:** `DELTA_MAE`, `DELTA_RMSE`, and the mean bias
of each arm.

**THE FLOOR IS DERIVED FOR THIS STATISTIC ON THESE ROWS.** No floor is imported from any
other experiment. Both registered power instruments are computed and both are reported, and
the verdict must hold under BOTH:

- **E_cond**: the forward-chained profiles and level constants are held FIXED at their real
  values, only the scored rows are resampled i.i.d. with replacement within the cell.
  B = 5000. Question: given this training corpus, is this margin real?
- **E_refit**: the FULL resolved pool is resampled with replacement by row, the forward
  chain is REBUILT from the resampled prior cohorts, every arm is rescored, and
  `DELTA_MSE` is recomputed. B = 2000 (heavier per draw). Question: what would we conclude
  from a different dataset? Within a draw the eligible cohort set is held at the real one
  (part 3.2) and a cohort with zero resampled prior rows is skipped for that draw.

`MDE95` one-sided for each estimator is `1.645 * sd_boot`. `margin_over_floor` =
`|DELTA_MSE| / MDE95`. **If the two instruments disagree, that disagreement is the
headline and the verdict is the more conservative of the two.**

## 3. The rows

### 3.1 Pool

Identical to B1: every row in `data/xfv_hitter_matrix.json` and
`data/xfv_pitcher_matrix.json` with `kind == "debuted"` and
`debut_year + 5 <= RESOLVED_THROUGH (2025)`, joined to the `career_war` table. B1 recorded
n = 988 (460 hit, 528 pit) and reconciled 988 of 988 against the shipped
`target_resolved`. The same reconciliation is re-run here and must come back 988/988.

**Staleness bound.** The program's STATE note says the served eFV matrices are stale in the
sense that their PREDICTIONS reproduce `consensus_fv_raw` on 74.8 percent of rows. This
lane reads no prediction from those files. It reads the row roster only: `player_key`,
`kind`, `debut_year`, `censored`. A stale prediction column cannot move any number here.

### 3.2 Forward chain, and the eligibility threshold

Cohort `Y` is SCORED using a profile estimated only on rows with `debut_year < Y`. Cohort
row counts in the pool, probed before this file was written:

| debut year | rows | hit | pit | rows in strictly prior cohorts |
|---|---|---|---|---|
| 2011 | 18 | 10 | 8 | 0 |
| 2012 | 55 | 25 | 30 | 18 |
| 2013 | 108 | 55 | 53 | 73 |
| 2014 | 101 | 48 | 53 | 181 |
| 2015 | 134 | 62 | 72 | 282 |
| 2016 | 88 | 39 | 49 | 416 |
| 2017 | 76 | 46 | 30 | 504 |
| 2018 | 97 | 44 | 53 | 580 |
| 2019 | 148 | 72 | 76 | 677 |
| 2020 | 163 | 59 | 104 | 825 |

**THRESHOLDS THIS LANE ADDS, disclosed as such:** a cohort is eligible only if its prior
pool holds at least **100 rows pooled AND at least 60 rows on each side**. Cohorts that
fail are DROPPED, never backfilled from the pooled profile, because a backfill would leak
the scored cohort into its own profile.

From the counts above these thresholds admit cohorts **2014 through 2020**, n = 807
(370 hit, 437 pit), and they admit the IDENTICAL cohort set for the pooled arm and the
per-side arm, which is required for the two arms to be comparable. The thresholds were
chosen from row counts only. No error or bias number existed when they were set.

### 3.3 Family and multiplicity

- **PRIMARY CELL: `n2_hit`.** This carries B1's narrowing. It is the one cell B1's
  materiality rule marked MATERIAL, and it is named before the run.
- **FAMILY: the 8 span-by-side cells** (n in 2..5, side in hit/pit). `k of 8` significant is
  reported together with the Holm-adjusted count at alpha 0.05. The family is not narrowed
  after the fact. The 4 pooled-side cells are reported separately and are not counted into
  the family, because they are deterministic functions of the 8.

## 4. MANDATORY CONTROLS. All four run. All four are reported whatever they say.

### 4.1 RANK-IDENTICAL LEVEL TWIN (mandatory, and the one that can kill the lane)

```
twin_target(n) = shipped_target(n) + c_n
c_n = mean(true - shipped_target(n)) over STRICTLY PRIOR cohorts     # forward chained
```

Within a span this shifts every value by one constant, so it is RANK-IDENTICAL to the
shipped label and carries exactly ZERO additional information. It removes the mean bias and
nothing else.

```
DELTA_MSE_vs_twin(n) = MSE(candidate) - MSE(twin)
```

**INFORMATION CLAUSE.** The candidate is credited with information only if
`DELTA_MSE_vs_twin` has a bootstrap CI95 whose UPPER bound is below 0 under BOTH E_cond and
E_refit. If the CI covers 0, the finding is **LEVEL SHIFT ONLY**: the candidate is doing
what a constant does, and the correct object of any owner decision is the constant, not the
profile. If the CI lies ABOVE 0, the twin BEATS the candidate and the recommendation is
against the candidate.

What would fail this clause: the candidate scoring within band of, or worse than, an
additive constant. This is a live outcome, not a formality, because the candidate multiplies
`obs_sum` by a number larger than the shipped one and therefore INFLATES error variance
while it removes bias, whereas the twin removes bias at zero variance cost.

### 4.2 RANDOM-LABEL NULL BAND (mandatory)

Two nulls, because they break different things.

- **NULL-A, permuted share profile.** Take the prior-cohort mean-WAR vector `m_1..m_6` and
  apply each of the 720 permutations of its entries, deterministically enumerated in
  `itertools.permutations` order, no RNG. Each permutation yields a different `S_n` and a
  different rescale. The band is the [2.5, 97.5] percentile of `DELTA_MSE` over the 719
  non-identity permutations. This asks whether the ORDERING of the season shares matters or
  whether any reshuffle of the same six numbers does as well.
- **NULL-B, zero-information projection.** Permute the candidate's projected values ACROSS
  ROWS within each span-side cell, so the marginal distribution of the projection is
  preserved exactly and its pairing with the truth is destroyed. 1000 draws,
  `np.random.default_rng(20260807)`, the seed inherited from B1 and fixed before the run.
  `DELTA_MSE` for this null must be strongly POSITIVE. If the real candidate's
  `DELTA_MSE` is not far outside this band, nothing was measured.

### 4.3 PERMUTATION P-VALUE (mandatory)

Paired sign-flip permutation on the per-row differences `d_i`. Under the null of a symmetric
difference distribution centred on 0, draw 10000 sign vectors with
`np.random.default_rng(20260807)` and report
`p = (1 + #{draws with mean d <= observed}) / (1 + 10000)`, one sided in the direction of
improvement. Reported for the primary cell and for all 8 family cells.

### 4.4 THE CONTROL THAT WOULD EMBARRASS ME: the one-parameter scalar fit

The candidate is, per span, ONE NUMBER: the multiplier `1 / S_n`. A season-share profile is
an elaborate way to choose one number. So a plain scalar, fitted on the same prior cohorts
with no season-index structure at all, is run beside it:

```
r*_n = argmin_r sum_prior (r * obs_sum - true)^2 = sum(obs_sum * true) / sum(obs_sum^2)
scalarfit_target(n) = obs_sum * r*_n
```

If `scalarfit` matches or beats the candidate, then the season-share profile contributes
NOTHING beyond a fitted constant, and the honest recommendation names the constant. This is
reported in the headline if it happens.

## 5. Pins and bounds asserted in the lab, not assumed

- **LAMBDA PIN.** `efv_model._BLEND_LAMBDA_RESELECT` must read `hit 0.70, pit 0.57`. The lab
  ASSERTS this and records the value read and the line number it was found on. B1's artifact
  cites efv_model.py:581; a later edit in this program may have moved it, so the lab records
  the observed line and flags a mismatch rather than trusting the citation. A synthetic label
  beside an unpinned lambda would silently move the served blend.
- **NO WRITE TO THE SERVED PATH.** The lab writes exactly one file,
  `data/xfv_label_replacement_eval.json`. It restores `efv_dataset.RESOLVED_THROUGH` in a
  `finally` block and asserts the restoration. It fits no model, rebuilds nothing, and
  writes nothing to `prospects.db`.
- **ECONOMIC BOUND, restated so no rank claim can exceed it.** Deleting the ENTIRE censored
  pitcher block, the maximum perturbation any label instrument in this program can cause,
  moves the served board by rho 0.9441. This lane cannot produce a large rank effect and
  will not claim one.

## 6. PASS clauses. Stated in full before the run.

**GATE 1, versus shipped (the stop clause's gate).**
`DELTA_MSE` in the PRIMARY CELL `n2_hit` has a bootstrap CI95 with UPPER bound strictly
below 0 under BOTH E_cond AND E_refit.

**GATE 2, versus the level twin (the information clause).**
`DELTA_MSE_vs_twin` in `n2_hit` has a bootstrap CI95 with UPPER bound strictly below 0 under
BOTH E_cond AND E_refit.

**GATE 3, null separation.**
The observed `DELTA_MSE` in `n2_hit` lies BELOW the 2.5th percentile of the NULL-A band AND
below the 2.5th percentile of the NULL-B band.

**GATE 4, permutation.**
The sign-flip permutation p in `n2_hit` is below 0.05.

**GATE 5, breadth.**
`DELTA_MSE` is negative with CI95 upper below 0 in at least 4 of the 8 family cells under
E_cond, and the Holm-adjusted significant count at alpha 0.05 is at least 2.

**VERDICT MAP.**
- All five gates pass: `REPLACEMENT_BEATS_SHIPPED_AND_TWIN`. Recommend the swap to the
  owner. Do not perform the swap.
- Gate 1 passes, Gate 2 fails: `LEVEL_SHIFT_ONLY`. The measured object is a constant.
  Recommend nothing be swapped on the strength of the profile.
- Gate 1 fails: `NULL`. Stop clause fires (part 7).
- Gate 1 and 2 pass but 3, 4 or 5 fail: `UNDERPOWERED_OR_UNSTABLE`. Report, recommend
  nothing.

## 7. STOP CLAUSE

If the candidate does not beat the shipped projection on held-out truncation error by more
than its own bootstrap band (Gate 1), the NULL is recorded and the lane stops. NO LABEL
CHANGE IS SHIPPED IN ANY CASE. The label feeds every downstream gate in this program and a
swap needs its own owner decision. The deliverable is a measured recommendation, never an
edit to `efv_dataset.py`.

**Also not run under the stop clause:** the downstream refit. Even if every gate passed, a
served-board rank delta requires refitting the eFV forward chain and rescoring, which would
touch served artifacts this lane is forbidden to write. The lane therefore reports a
LABEL-SPACE rank diagnostic instead (Spearman between the shipped and candidate targets over
the 833 shipped rows that ride the projection, plus the induced realized-bucket movement),
labels it as label space and NOT a served-board delta, and points at the 0.9441 economic
bound as the ceiling on anything a refit could have shown. This substitution is registered
here, before the run, and not after.

## 6.5 Pooled versus per-side, tested rather than assumed

Report, on the prior-cohort profiles actually used: the per-side cumulative shares `S_n`,
their difference, and a bootstrap CI on the hit-minus-pit difference in `S_2` from the
2013-and-earlier estimation pool. Report `DELTA_MSE` for the PER-SIDE arm beside the POOLED
arm in every cell. The pooled arm remains primary under part 1's selection rule regardless
of which scores better.

---

## RESULT (appended after the run)

Artifact: `data/xfv_label_replacement_eval.json`. Lab: `tools/efv_label_replacement_lab.py`.
Every number below reproduces from that artifact.

### 8.0 VERDICT: NULL. The stop clause fired. No label change is recommended.

The candidate is not merely unproven. It is **measurably WORSE than the projection it was
built to replace, in all 8 family cells**, and worse than the level twin in all 8.

### 8.1 Setup that held

- Pool re-derived at n = 988 (460 hit, 528 pit), identical to B1. Ground-truth
  reconciliation 988 of 988, zero mismatches.
- Lambda pin asserted and OK: `hit 0.70, pit 0.57`. **The pin has MOVED: it now lives on
  efv_model.py:586, not the :581 B1 cited.** The lab records the line it found rather than
  trusting the citation. Value unchanged, so nothing is compromised.
- Eligibility thresholds admitted cohorts **2014 through 2020**, n = 807 (370 hit, 437 pit),
  the identical cohort set for the pooled and per-side arms, exactly as part 3.2 predicted.
- Forward-chained cumulative share at n = 2 was `S_2 = 0.223` on the first fold, so the
  candidate multiplier is **4.485** where the shipped one is 3.000.

### 8.2 GATE 1, versus shipped: FAILED, in the wrong direction

Primary cell `n2_hit`, n = 370:

| arm | mean bias | sd of error | MSE | RMSE | MAE |
|---|---|---|---|---|---|
| shipped | -1.6267 | 4.5962 | 23.7138 | 4.8697 | 3.2573 |
| candidate (pooled profile) | -0.3843 | 5.9738 | **35.7379** | 5.9781 | 3.9614 |
| level twin | -0.3893 | 4.6139 | **21.3822** | 4.6241 | 3.1714 |
| scalar fit (control 4.4) | -1.6979 | 4.6363 | 24.3201 | 4.9315 | 3.2726 |

`DELTA_MSE = +12.024`. E_cond CI95 [+5.451, +20.123], sd 3.815, MDE95 6.276,
margin/floor 1.92. E_refit CI95 [+4.630, +26.932], sd 5.846, MDE95 9.616, margin/floor 1.25.
**The two power instruments AGREE.** Both put the entire interval above zero.

The candidate does exactly what it was designed to do to the bias, cutting `n2_hit` from
-1.6267 to -0.3843 and `n2_pit` from -0.7855 to -0.0559. It pays for that with error
variance: sd of error 4.5962 to 5.9738 on hitters. **The bias was only 11 percent of the
shipped MSE** (bias squared 2.646 of 23.714), so there was at most 2.6 of MSE to win, and
the rescale cost 14.6 of variance.

All 8 family cells: `DELTA_MSE` positive everywhere, +12.024, +8.390, +5.640, +2.302,
+1.075, +0.324, +0.243, +0.081. Sign-flip permutation p in the improvement direction:
0.9998, 1.0000, 1.0000, 1.0000, 0.9985, 0.9704, 0.9999, 0.9945.

### 8.3 GATE 2, versus the level twin: FAILED. And the twin BEAT the shipped label.

`DELTA_MSE_vs_twin` in `n2_hit` = **+14.356**, E_cond CI95 [+8.190, +22.013], E_refit CI95
[+6.803, +28.819]. The candidate loses to a label that shifts every value by one constant
and therefore carries zero information. **This is the LEVEL SHIFT ONLY diagnosis in its
sharpest form: the profile is not merely a level shift, it is worse than one.**

### 8.4 GATE 3, nulls: FAILED on NULL-A, PASSED on NULL-B

- **NULL-A, permuted share profile.** In `n2_hit`, of the 719 non-identity permutations of
  the six season-index means, **672 do STRICTLY BETTER, 47 tie, and 0 do worse.** The 47
  ties are exactly the 2! x 4! - 1 permutations that preserve the leading pair, which is a
  design check that the enumeration is correct. **The TRUE season ordering is the worst of
  all 720 orderings.** Same at n = 3 (684 better, 0 worse). At n = 4 and n = 5 the true
  ordering finally stops being the worst (96 and 240 permutations do worse), but the
  observed delta is still positive there.
- **NULL-B, zero-information projection.** `n2_hit` band [+96.13, +121.36], observed
  +12.02, which is far below. So the candidate is NOT a zero-information projection. It
  retains the rank information in `obs_sum` intact. Its defect is purely the scale.

Those two nulls together are the mechanism: the projection keeps all the signal and gets
the multiplier badly wrong.

### 8.5 CONTROL 4.4, the embarrassing one: it landed, and it explains the failure

The least-squares one-parameter multiplier fitted on strictly prior cohorts, `r*_2`, came
back at **3.0757, 3.1514, 2.8092, 2.8038, 2.7661, 2.7435, 2.8029** across the seven forward
chained folds. The shipped multiplier is **3.000**. The candidate's is **4.02 to 4.56**.

**Out of cohort, in all seven folds, the shipped 6/n multiplier is already within noise of
the squared-error optimum.** The scalar-fit arm's MSE at `n2_hit` is 24.3201 against the
shipped 23.7138, a difference of +0.606. There is no multiplier that materially beats the
shipped one, so no rescale-shaped candidate could have passed, and the share profile is not
being punished for its season structure but for choosing a ratio-of-means estimator on a
noisy right-skewed regressor.

### 8.6 GATE 4: FAILED. p = 0.9998 in `n2_hit`, and above 0.97 in all 8 cells.

### 8.7 GATE 5, breadth: FAILED. 0 of 8 under E_cond, 0 of 8 under E_refit, 0 Holm significant.

Reported for multiplicity in the honest direction: **7 of 8 family cells are significantly
WORSE** under E_cond (all but `n4_pit`, CI95 [-0.033, +0.670]), and the same 7 of 8 under
E_refit.

### 8.8 Part 6.5, pooled versus per-side: the pooled profile is estimable

On the pre-2014 estimation pool (90 hit, 91 pit), `S_2` is 0.2280 hit and 0.2129 pit,
difference **+0.0151**, bootstrap CI95 **[-0.0840, +0.1118]**, which covers zero. Pooling
is not doing damage. **This clause could have failed and did not.** The per-side arm was run
anyway and does not rescue anything: `DELTA_MSE` +12.864 on `n2_hit` (worse than pooled) and
+8.218 on `n2_pit` (marginally better than pooled's +8.390), both far above zero. The
pre-registered selection rule keeps POOLED as primary and no post-hoc substitution is made.

### 8.9 Part 7 label-space rank diagnostic, and a small data defect found on the way

Over the 833 shipped rows that ride the projection (210 / 218 / 228 / 177 at n = 2..5,
382 hit and 451 pit), the candidate target correlates with the shipped target at Spearman
**0.99788**, and 62 of 833 rows (7.44 percent) change realized bucket, all 62 upward. That
is comfortably inside the 0.9441 economic ceiling. No refit was run and no served-board rank
delta is claimed.

**Defect found while building that pool, reported not fixed:** window arithmetic marks 838
debuted rows censored, but the shipped matrices flag 833. The five extra rows are
`jake_alu`, `tucupita_marcano`, `alex_kirilloff`, `riley_pint`, `stephen_ridings`, all
carrying `observed_seasons = 6` and `weight = 1.0` because `efv_dataset`'s career-terminal
transaction rule closed their windows early. They are correctly NOT censored, and excluding
them reproduces B1's 833 exactly. This is a naming and reconciliation hazard for any future
lane that recomputes the censored set from `debut_year` alone, which is what B1's
`population_mix_estimate` label "n_rows_riding_the_projection" would invite.

### 8.10 POST HOC, not pre-registered, gates nothing

Reported because an owner deciding what to do about B1's bias needs it, and because hiding a
number that was computed would be worse than disclosing that it was computed late. It was
appended after every pre-registered draw, so no number in 8.1 to 8.9 moved.

**Level twin versus shipped.** `n2_hit` `DELTA_MSE` **-2.332**, E_cond CI95
[-3.492, -1.159], E_refit CI95 [-3.684, -1.029], both entirely below zero. `n2_all` -1.207,
also both below zero. **Every other cell covers zero**, including `n2_pit` (-0.254, CI95
[-1.133, +0.622]). And even where it wins, the MAE gain is -0.086 WAR at `n2_hit` while MAE
gets WORSE in 7 of the 8 cells (`n2_hit` is the only one where it improves).

So the only label change with any measured support is a single additive constant on the
hitter n = 2 cell, worth 2.3 MSE and 0.09 MAE. That is not gated here, it was not
pre-registered, and this lane does not recommend it. If anyone wants it, it needs its own
gate doc and its own owner decision.

### 8.11 What a future lane should NOT do

Do not build another rescale-shaped candidate. Section 8.5 closes that shape: the shipped
multiplier is already the out-of-cohort least-squares optimum at every span. The censoring
bias is real (B1) and is simultaneously **not recoverable by any function of `obs_sum`
alone**, because the only lever such a function has is a multiplier and the best multiplier
is the one already shipped. A candidate that could win would have to use information the
current label ignores, for example per-row features at the truncation point, and it would
then be a MODEL of the tail rather than a projection of it, with all the leakage exposure
that implies.
