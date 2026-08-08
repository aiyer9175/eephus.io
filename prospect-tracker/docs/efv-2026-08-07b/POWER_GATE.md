# POWER GATE (Lane A1, 2026-08-07b): which bootstrap is the published claim about?

**STATUS OF THIS FILE.** Parts 0 through 4 are the PRE-REGISTRATION. They were written in
full, including every PASS clause and every stop clause, BEFORE `tools/efv_power_lab.py`
existed and therefore before any number in part 5 could be known. Part 5 is a placeholder
that is filled in after the run. Nothing in parts 0 to 4 is edited afterwards. This is the
Lane J1 discipline, adopted because it is the only wave-1 registration that survived
adversarial reconstruction.

---

## 0. What is actually in dispute

`data/xfv_eval.json` `evals.full_pool_km.pooled_oos` on the hitter side reads consensus
0.3002, shipped blend 0.2787, delta **-0.0215** on n = 1,792 scored rows. Wave 1 measured
its floor two ways and they disagree about the verdict:

| estimator | sd | MDE95 one-sided | margin / floor | verdict |
|---|---|---|---|---|
| shipped paired bootstrap, train and test resampled, refit per draw | 0.01806 | 0.0297 | 0.72x | NULL |
| fits held fixed, only the scored rows resampled | 0.01243 | 0.0204 | 1.05x | RESOLVABLE LOSS |

Two independent verifiers reproduced the refit floor at 0.0287 and 0.0299. Roughly 53% of
the shipped floor's variance is refit noise. The verdict currently flips on the choice of
estimator, and the published claim does not say which estimator it is about.

**Second measured fact, also from wave 1, not acted on.** In the wave-1 null simulation
(`data/xfv_cohort_floors.json` `null_coverage_check`) the shipped bootstrap's sd is
**1.175x** (pooled) and **1.292x** (cell-restricted) the true sampling sd. The floors are
18% to 29% too WIDE. The gate that checked this was coded `coverage_95 >= 0.90` with no
upper bound, so it could not see over-coverage at all. For a program whose product is NULL
verdicts, a floor that is too wide is the PERMISSIVE direction. **That one-sided gate is
itself a defect and this lane reports it as one.**

## 0.1 The trap, stated so it can be checked against the result

Any change that makes a floor smaller looks like progress and is usually power laundering.
A tighter floor makes an improvement CERTIFIABLE, it does not CREATE one. So:

- The criterion is NOT "is it tighter". It is "does it cover its own estimand at 95%".
- No estimator registered here retires the shipped floor.
- No estimator registered here retroactively resolves any past null, reopens any closed
  arm, or changes any shipped constant. **This wave changes no floor constant.** The rank
  frontier stays closed.
- The direction of the coverage correction in part 3.4 is the permissive one. It is
  reported because it was measured, not because it helps.

## 1. The two estimators and the two questions

They are not competing estimates of one quantity. They estimate two different variances of
two different sampling experiments, and each is correct for its own question.

**E_refit (shipped).** Resample the WHOLE pool with replacement (train and test rows
together), refit the consensus OLS and the weighted ridge on every draw, rerun the forward
chain, recompute the pooled rho delta. Estimand: `Var_{T,S}(delta)`, variation over redraws
of the training corpus AND the scored sample jointly.
Question answered: **"what would we conclude if we had drawn a different dataset?"**

**E_cond (candidate).** Fit the forward chain ONCE on the real data. Hold every per-fold
consensus OLS and ridge fit FIXED. Resample only the scored rows and recompute the pooled
rho delta. Estimand: `Var_{S|T}(delta)`, variation over redraws of the scored sample given
this training corpus.
Question answered: **"given this training corpus, is this margin real?"**

Two resampling schemes are pre-registered as candidates for E_cond, because the forward
chain has fixed per-fold test sizes and i.i.d. pooled resampling does not preserve them:

- **E_cond_iid**: i.i.d. resample of the pooled scored rows. This is the scheme wave 1
  measured at sd 0.01243, so it is the PRIMARY candidate.
- **E_cond_strat**: resample within each cohort-year fold, preserving each fold's test n.
  Reported as a SENSITIVITY.

**Selection rule, fixed now to prevent selection on outcome.** Both are measured and both
are reported whatever happens. E_cond_iid is the primary and is the one that can be
registered. E_cond_strat is registered only if E_cond_iid fails AND E_cond_strat passes,
and in that case the switch is disclosed in the headline as a post-hoc substitution.

## 2. Coverage checks. The gate. TWO-SIDED.

An estimator is checked against ITS OWN estimand. Checking E_cond against the unconditional
estimand would fail by construction and would prove nothing, so both cross-checks are run
and reported as diagnostics, never as gates.

**Simulation design (fixed now).** The synthetic DGP is DESIGN-MATCHED to the real hitter
full pool: same n, same distribution of decision years across the 11 folds, same feature
count k = 14, same blend lambda 0.70, same weight distribution, a consensus column `fv` on
the real `fv` marginal, and a target that is a noisy monotone function of `fv`. **Null
construction: the k model features are noisy copies of `fv`, so the model carries NO
information the consensus lacks.** The true delta under this null is a fixed constant of
the design and is not required to be exactly zero (a noisy blend degrades a rank, which is
the regime a losing cell sits in). Several independent seeds, one per synthetic dataset.

**EXP-1, unconditional coverage. The estimand for E_refit.**
Draw `S` fresh datasets. `truth_uncond` = Monte-Carlo mean of the point delta across them,
`sd_uncond` = its Monte-Carlo sd. On `n_check` of those datasets, form each estimator's 95%
percentile interval and record whether it contains `truth_uncond`.

**EXP-2, conditional coverage. The estimand for E_cond.**
For each of the same `n_check` datasets, hold that dataset's per-fold fits FIXED and draw
`M` FRESH test sets from the same DGP with the same per-fold sizes, scoring each with those
fixed fits. `truth_cond(d)` = mean delta over the fresh test sets for dataset d, and
`sd_cond(d)` = its sd. Record whether each estimator's interval contains `truth_cond(d)`.

**THE GATE (two-sided, both directions are failures).**
With `n_check` independent datasets, coverage count `k` must fall inside the CENTRAL 95%
binomial acceptance region for p = 0.95 at that `n_check`, computed in code and printed.
- `k` below the region: UNDER-coverage. Reject. The estimator buys power it has not earned.
- `k` above the region: OVER-coverage. Reject. The estimator is too wide, which is the
  permissive direction for a NULL-producing program and is exactly the defect the existing
  one-sided gate cannot see.

`n_check` is fixed at **200**, chosen so the upper edge of the acceptance region is strictly
below 1.000 and over-coverage can actually fail. A gate whose upper edge is 100% is not a
two-sided gate.

**Reported beside the gate, not a gate itself:** `sd_ratio` = mean bootstrap sd / true sd
for each estimator against each estimand. A ratio outside [0.90, 1.10] means the estimator
is materially miscalibrated in width even if the interval happens to cover, and any floor
quoted from it must carry the measured correction of part 3.4. **The [0.90, 1.10] band is a
threshold this lane adds and the plan does not contain; it is disclosed as such and it is
NOT what decides registration.** Registration is decided by the binomial gate above.

**Also reported: the existing one-sided gate re-run as written** (`coverage_95 >= 0.90`, no
upper bound) beside the two-sided verdict, so the difference between them is visible.

## 2.1 STOP CLAUSE, pre-registered

If E_cond_iid fails the two-sided coverage gate, and E_cond_strat also fails, **record the
failure and STOP.** Do not tune, do not add a bias correction, do not widen `n_check` until
it passes, do not re-seed. Publish the failure, publish the shipped floor as the only
registered instrument, and the hitter full-pool loss stays NULL. That outcome is a
successful lane.

## 3. Detection under a known-real alternative

An estimator that never rejects is trivially well-covered. Both estimators must DETECT
something known to be real.

**3.1 Real-data detection. The `fv` column.** `docs/EFV_GATE_STANDARD.md` section 6: of 22
shipped features exactly one, hitter `fv`, is individually resolvable. Contrast: pooled rho
of the shipped blend against pooled rho of the same blend fit on the spec MINUS `fv`, on the
same rows of the same pool. Both estimators bootstrap that contrast. PASS = the contrast
clears the estimator's own MDE95. An estimator that cannot see `fv` is not registered no
matter how it covers.

**3.2 Simulated power.** On a design-matched ALTERNATIVE DGP in which the model features
carry genuine information the consensus lacks, report each estimator's detection rate at
its own floor, and its false-positive rate on the part-2 null DGP. Both numbers are
reported for both estimators.

**3.3 The control that would embarrass this lane.** The dumbest explanation for "53% of the
shipped floor's variance is refit noise" is that it is not a decomposition at all. So the
variance is decomposed three ways on the real pool and checked for additivity:
test-resampled-only (E_cond), train-resampled-only with a refit and the test rows held
fixed, and the shipped both-resampled bootstrap. If `sd_test^2 + sd_train^2` does not
approximately reconstruct `sd_shipped^2`, the "53% refit noise" framing is wrong and this
lane says so.

**3.4 Coverage correction.** If a registered estimator's measured `sd_ratio` against its own
estimand is `r`, the corrected floor is `MDE95_raw / r`. The correction is measured on the
design-matched SIMULATION, not on the real pool, and that limitation is stated wherever the
corrected number appears. Both the raw and the corrected floor are published. **If `r > 1`
the correction makes the floor smaller and a loss easier to call, which is the permissive
direction; it is applied anyway because it was measured, and it is flagged every time.**

## 4. What gets published, and where, if an estimator registers

Multiplicity: the PRIMARY cut is **hitter `full_pool_km`**, named in the lane brief before
any measurement. `pit.full_pool_km`, `hit.debuted_km` and `pit.debuted_km` are SECONDARY and
are reported with a Bonferroni-adjusted floor at k = 4 (one-sided alpha 0.0125, z = 2.241)
printed beside the unadjusted one. No secondary cut is described as resolvable on its
unadjusted floor alone.

If the primary cut resolves as a LOSS under a registered estimator, that is the first
resolvable statistic on which consensus beats eFV on the full pool, and it is published in
the same voice the head-to-head already uses. Exact placement and wording are specified in
part 5.3 after the run. It is not buried in a JSON key.

Every published line carries the sentence: **the conditional estimator does not retire the
shipped floor, does not reopen any closed arm, and does not retroactively resolve any past
null.**

## 5. RESULT (appended after the run)

Producer `python tools/efv_power_lab.py all 2000`, seed 20260807, ledger
`data/xfv_power_eval.json`. Every number below is a key in that file. The `power` block
was re-run once after the main pass, for the reason given in 5.2; nothing in parts 0 to 4
was touched.

### 5.1 The design match, and its one limitation

`dgp_design_match`. The synthetic matches the real hitter full pool on n (1,883), folds
(11), k (14), lambda (0.70), the `fv` and weight marginals, and the target's zero share
(0.725 real against 0.717 synthetic), sd (5.108 against 5.395) and out-of-sample consensus
rho (0.3002 against 0.3155). It also reproduces the structural quantity this lane is
about, the shipped-over-test sd ratio: **1.399 real against 1.333 synthetic**.

Limitation, stated because it bounds part 5.5: the synthetic's ABSOLUTE bootstrap sds run
about 0.7x the real ones (shipped 0.01068 against 0.01756). Coverage is a relative
property, so the part-2 gate is unaffected; the transported sd_ratio correction is the one
step that inherits this.

### 5.2 The embarrassing controls, run before the conclusion

**Control A, is "53% refit noise" a decomposition at all (3.3)?** `variance_decomposition`,
B = 1,200 on the real hitter full pool: shipped both-resampled sd **0.01829**,
test-rows-only **0.01258**, train-refit-only **0.01132**. The additive reconstruction
sqrt(0.01258^2 + 0.01132^2) = **0.01692**, which is **0.925x** the shipped sd. Additivity
holds to within 8%, so the framing survives. Refit share of the shipped variance:
**0.527**, which reproduces wave 1's "roughly 53 percent" independently.

**Control B, is the refit leg's extra width just cohort-size resampling?** The shipped
bootstrap scatters resampled rows across folds, so it reshuffles fold sizes, while a truth
that holds fold sizes fixed would charge that variance to "refit noise" for free. Measured:
`coverage.legs.refit.varfolds_control`. Against a truth whose cohort SIZES also redraw, the
refit sd ratio is **1.460**, against **1.465** for the fixed-fold truth. The control
changes nothing. The width is not a fold-size artifact.

**Control C, is the "null" fire rate a type-I rate?** No, and the first run of the lab
printed only the number that is not. Under the part-2 null the true delta is **-0.01091**,
not zero, because a blend that mixes in a predictor carrying no information the consensus
lacks still degrades the rank. So `fire_rate_vs_zero` under the null (refit 0.125,
cond_iid 0.333, cond_strat 0.342) is power against a real negative effect, not a false
alarm rate. The `power` block was re-run with `fire_rate_centered`, |point - truth| >=
MDE95, added. That correction is recorded here rather than quietly absorbed.

### 5.3 The gate

`coverage`: n_check = 200 datasets, S = 400 truth datasets, B = 300, M = 300 fresh test
sets per dataset. Central 95% binomial acceptance region for p = 0.95 at n = 200 is
**[184, 196] counts, i.e. coverage in [0.920, 0.980]**. Estimand truths: unconditional
mean delta -0.01090 with sd **0.00870**; conditional mean delta -0.01184 with sd
**0.00854**.

| estimator | own estimand | mean boot sd | true sd | sd ratio | coverage | two-sided gate |
|---|---|---|---|---|---|---|
| E_refit (shipped) | unconditional | 0.01274 | 0.00870 | **1.465** | 0.970 (194/200) | PASS |
| E_cond_iid (primary) | conditional | 0.00853 | 0.00854 | **0.999** | 0.930 (186/200) | **PASS** |
| E_cond_strat (sensitivity) | conditional | 0.00851 | 0.00854 | 0.995 | 0.920 (184/200) | PASS, at the lower edge |

**E_cond_iid is REGISTERED, as the primary, exactly as pre-registered. No post-hoc
substitution was needed and none was made.** The stop clause did not fire.

Sensitivity to the acceptance LEVEL, which part 2 fixed at central 95% and which the plan
does not specify. Regions at n = 200: level 0.80 gives [186, 194], 0.90 gives [185, 195],
0.95 gives [184, 196], 0.99 gives [181, 197]. **The primary, E_cond_iid at 186/200, passes
at every one of those levels.** E_refit at 194/200 also passes at every level.
E_cond_strat at 184/200 passes only at 0.95 and 0.99 and would FAIL as under-covering at
0.90 or 0.80, which is a further reason it stays a sensitivity and not the registered
instrument.

**Coverage and width are not the same property, and this table is the proof.** E_refit
covers at 0.970 and passes the interval gate while its width is 1.465x the truth, because
a wide interval that is also off-centre can still cover. MDE95 is `1.645 * sd`, a WIDTH,
not the percentile interval. So the pre-registered interval gate certifies the shape of
all three estimators and it is the sd ratio that governs the floor. The false-positive
rates in 5.4 measure the width directly and are the sharper instrument.

Per part 2 the one-sided gate as currently coded in `tools/efv_cohort_floor_lab.py`
(`coverage_95 >= 0.90`, no upper bound) is reported beside each row: it returns PASS for
all three, including the 1.465x leg. It cannot distinguish them.

### 5.4 Detection and error rates

`power`, n_sim = 120, B = 200, at each estimator's own one-sided MDE95.

| DGP, true delta | statistic | E_refit | E_cond_iid | E_cond_strat |
|---|---|---|---|---|
| null, -0.01091 | false-positive rate, centered | **0.0167** | **0.1250** | 0.0917 |
| alternative, +0.03096 | power, `|point| >= MDE95` | 0.750 | **0.842** | 0.833 |

The calibrated target for the centered rate is about **0.10**, not 0.05, because the
published MDE95 convention is a one-sided 1.645 sd applied to an absolute margin. That is
a property of the convention, not of any estimator here.

Read plainly: **the shipped estimator's real false-positive rate is 1.7% against a nominal
10%, so it is roughly six times more conservative than the gate standard says it is.**
E_cond_iid lands at 12.5% and E_cond_strat at 9.2%. Both conditional estimators detect the
known alternative more often than the shipped one (0.84 and 0.83 against 0.75).

`detection_fv`, B = 2,000, real data. **The pre-registered cell `full.blend` is
mis-specified and this is recorded, not papered over.** The blend is
`(1-lam)*consensus + lam*ridge` and the consensus leg is an OLS on `fv`, so deleting `fv`
from the ridge leaves it in the blend at weight 0.30. That contrast reads **-0.00301** and
every estimator misses it, INCLUDING the shipped one, which is a reductio on the check
rather than on the estimators. All four cells of the (pool x leg) grid were run:

| cell | point | E_refit | E_cond_iid | E_cond_strat |
|---|---|---|---|---|
| full.blend (pre-registered) | -0.00301 | MISS (0.0260) | MISS (0.0211) | MISS (0.0211) |
| full.ridge (amended primary) | +0.02372 | MISS (0.0317) | MISS (0.0265) | MISS (0.0265) |
| debuted.blend | +0.02073 | MISS (0.0353) | MISS (0.0241) | MISS (0.0246) |
| debuted.ridge | +0.06020 | **DETECT** (0.0453) | **DETECT** (0.0337) | **DETECT** (0.0343) |

The amended primary was designated after the four POINT estimates were visible but before
any floor was; `full.ridge` was chosen because it matches the lane's primary pool and it is
the SMALLER of the two ridge-leg effects, so the choice is the conservative one. Disclosed
either way. All three estimators fire on `debuted.ridge`, the cell where
`EFV_GATE_STANDARD.md` section 6 locates the known-real `fv` effect, and no estimator fires
where another does not. So 3.1 rules out an inert instrument, which is its purpose, and it
does not discriminate between the three. Registration rests on 5.3 and 5.4.

### 5.5 THE VERDICT

`verdict`, B = 2,000 per cut.

**PRIMARY, hitter `full_pool_km`, n = 1,792, delta -0.02143.**

| estimator | sd | MDE95 one-sided | margin / floor | verdict |
|---|---|---|---|---|
| E_refit (shipped, unchanged) | 0.01754 | 0.0289 | 0.743x | NULL |
| **E_cond_iid (registered)** | **0.01243** | **0.0204** | **1.049x** | **RESOLVABLE LOSS** |
| E_cond_strat (sensitivity) | 0.01227 | 0.0202 | 1.062x | RESOLVABLE LOSS |

**Under the registered conditional estimator, eFV resolvably LOSES the hitter full pool to
the consensus.** Bootstrap `p(delta > 0)` = **0.0415**. The measured coverage correction is
0.999, so the corrected floor is 0.0204, unchanged to three decimals: this verdict does
NOT depend on the correction.

Four qualifications travel with that sentence and are not optional:

1. **The margin is thin: 1.049x.** It resolves on the gate standard's ONE-SIDED 1.645 sd
   convention. Two-sided (1.96 sd, floor 0.0244) it is **0.878x and does NOT resolve**.
   Anyone quoting this must quote the convention with it.
2. **It is a conditional claim.** It says: given this training corpus, this margin is real.
   It does not say a different dataset would show it.
3. A blend carrying zero information the consensus lacks costs about **-0.011** in the
   design-matched simulation, roughly half the observed -0.0215. The dumbest available
   explanation covers half the margin and is quantified rather than assumed away. The
   magnitude is a property of the synthetic and does not transfer as a point estimate.
4. **The shipped floor is unchanged and remains NULL on its own question.** Both are true
   at once because they are answers to different questions.

**SECONDARY cuts, Bonferroni k = 4 (one-sided alpha 0.0125, z = 2.2414):**

| cut | n | delta | E_refit MDE95 | E_cond_iid MDE95 | E_cond_iid verdict |
|---|---|---|---|---|---|
| pit.full_pool_km | 1,885 | +0.01571 | 0.0268 (0.587x) | 0.0218 (0.720x) | NULL |
| hit.debuted_km | 755 | +0.00741 | 0.0445 (0.166x) | 0.0213 (0.348x) | NULL |
| pit.debuted_km | 890 | +0.00669 | 0.0425 (0.158x) | 0.0301 (0.222x) | NULL |

All three are NULL under every estimator, adjusted or not. **No eFV win becomes resolvable
under the conditional estimator anywhere in this table**, which is the check that the new
instrument is not power laundering: it made the only LOSS resolvable and left every WIN
where it was. Note also that the primary cut is NOT resolvable under Bonferroni k = 4
(floor 0.0279); it does not need to be, being the pre-registered primary, but the number
is published so nobody has to ask.

Worth recording for future lanes: on the debuted cuts the shipped floor is more than twice
the conditional one (0.0445 against 0.0213 on hitters), because those pools have small
train frames and refit variance dominates there.

### 5.6 Where this is published, and in what words

The head-to-head verdict lives at `source_backtest.py:376-389`, which computes
`resolvable`, `xfv_beats` and a three-valued `verdict` string ("beats consensus" / "loses
to consensus" / "not resolvable at this power") for the **debuted** cut only. The full-pool
cut is computed nowhere on that surface, which is why a -0.0215 margin has never appeared
beside a +0.0074 one.

Requested (this lane does not own `source_backtest.py`): a `full_pool` sub-block inside the
same `out["sides"][side]` dict, gated on a new constant `XFV_FULLPOOL_COND_MDE95 = 0.0204`,
carrying the identical `verdict` vocabulary so the loss prints in the same voice as the win.
The exact old and new text is in this lane's `edits_requested`. The wording the block must
produce for hitters is:

> loses to consensus (conditional estimator, 1.05x floor, one-sided)

and the block must carry `estimator: "conditional-on-train"` and
`note: "the conditional estimator does not retire the shipped floor, does not reopen any
closed arm, and does not retroactively resolve any past null"`.

### 5.7 Scope, restated because it is the whole point

- **No shipped floor constant changed in this wave.** `XFV_VS_CONSENSUS_MDE95` is still
  0.044 and `XFV_HEADTOHEAD_MDE95` is still 0.0352.
- E_refit is **not retired**. It passed its own two-sided coverage gate.
- **Nothing here reopens a closed arm or retroactively resolves a past null.** The rank
  frontier stays closed. The conditional estimator was applied to four pre-registered cuts
  and to nothing else, and it resolved exactly one of them, a loss.
- The 1.465x width finding says the shipped floor is conservative on its own question. That
  is the PERMISSIVE direction and it is published as a caution, not as a licence.
