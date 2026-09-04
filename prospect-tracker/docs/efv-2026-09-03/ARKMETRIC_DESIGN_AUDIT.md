# Arkmetric design audit (2026-09-03)

Owner ask: audit the design process behind the Arkmetrics, with a focus on eFV, consensusFV
and WAG, and identify errant decisions, so eFV is as accurate and predictive as it can be on
the FanGraphs FV framework.

Method: thirteen read-only census lanes over the design surfaces, 115 candidate findings,
deduplicated to 48. The top 30 by expected impact were then verified by an independent agent
against three lenses: code truth (every cited line re-read, every number re-derived), the
mathematics (steelman the existing decision first, then adjudicate), and closure history
(against the do-not-reopen ledger, the registry rows and the gate docs). 25 verifications
completed; five ran out of session budget and are marked unverified. The remaining 18
findings are census-only.

**Nothing in this document has been shipped.** The audit is read-only. Where a verifier
corrected the census, the corrected version is what appears here and the correction is
stated.

Companion documents: `EWAR_LABEL_EPOCH_GATE.md` (the registered epoch this audit feeds),
`WAR_BASIS_RUNBOOK.md` (the ordered rebuild), `docs/EFV_GATE_STANDARD.md` (floors, controls,
estimators), `docs/reference/FANGRAPHS_FV_FRAMEWORK.md` (the framework the grade is defined
against).

---

## 0. Executive summary

1. **The single largest design defect is a shape mismatch at the centre of eFV.** The model's
   consensus term enters linearly (`fv` in the ridge, `cons_war = max(0, OLS(fv))`) while the
   served grade inverts a convex empirical curve. A chord under a convex function sits below
   it at both ends, so the fitted line goes negative below FV 37.7 where no cohort mean is
   below -0.007. Measured: in-sample mean prediction at the FV 35 cell is -1.12 WAR (hitters)
   against a realized cell mean of +0.078, and on 487 of 495 live floor hitters the non-`fv`
   part of the prediction is non-negative. The FV20 floor population is mostly chord
   geometry, not the model abstaining about the player. Fix: feed `B_pooled(fv)` to the ridge
   so a zero-deviation player round-trips to his own grade.
2. **The level of the served WAR is calibrated in-sample, where it can only expand.** The
   output calibration is an OLS of the label on the ridge's own fitted values, whose slope is
   provably at least 1 (measured 1.044 hit, 1.074 pit), while out of sample the same
   prediction is over-dispersed (slope 0.65 / 0.59). The measured fix was built (C-1) and
   reverted by owner decision for top-band agreement with scouts, at a recorded accuracy cost
   (paired MAE -0.279 hit, -0.142 pit, CIs excluding zero). Under the current accuracy goal
   this is the highest-value owner decision to revisit; the correct estimator is a
   leave-one-fold-out affine at the grade seam, not inside the production fit.
3. **Four grades ride on one predicted WAR.** Board grade (pooled outcome inverse), odds key
   (a retired map, not exported, 0.0% agreement with the board above FV 45), dollars (a rank
   quantile onto the live consensus distribution, so pool-relative and level-invariant), and
   the routed provisional map (52.8% of served grades on a hand-set linear map no eval
   touches). Each was a defensible local decision; together they mean the same player is a
   different grade depending on which consumer asks.
4. **The outcome distribution is population-inconsistent.** `p_bucket_given_fv` is fitted on
   the Clemens 2025 published percentage tables (training n 678 / 437), not on our 3,037
   resolved rows, while the bucket LEVELS are solved to reconcile to our own anchor. Pinning
   the mean while importing bust mass from a population with half our bust rate forces the
   level scale k(FV) into 0.35-0.65, so the "star" bucket at hitter FV 60 is 2.67 WAR/season,
   below its own band floor of 4.0. Every shape functional inherits this: star odds, the
   surplus fan, and the WAG baseline.
5. **WAG is three metrics.** Three code paths, three baselines (eFV at debut, the served eFV,
   the consensus), two FV-to-WAR curves, an asymmetric legacy transform that adds a level
   term to a residual and reads current age and level to modify past production, and a
   glossary that documents a fourth definition. Sign disagreement between the two live paths
   is 17.6%. The farm rollup's baseline is the served grade, which for 143 graduates has
   moved since debut and correlates with realized WAR at r 0.22, so the subtrahend partly
   encodes the outcome it subtracts.
6. **The measurement program is strong and has two real gaps.** The controls, the two
   estimators, the TOST margin and the per-feature floors are all sound and are the reason
   most of this project's nulls are trustworthy. The gaps: the public head-to-head cells pool
   Spearman across base years whose label scale differs by exposure (2017 debuts have about
   nine observed seasons, 2023 have three), which credits the public raters 0.016-0.024 rho
   and eFV 0.007; and the head-to-head universe contains zero never-debuted players in every
   frame, so the published claim cannot see the half of the label space where risk-netting is
   what an FV grade is for.
7. **On the injury question the owner asked: yes, replace it, on conditions.** The current
   penalty is a set of asserted multipliers on a population where the estimand does not hold
   (all 580 penalised rows are pre-debut, so a lost MiLB season shifts the label window rather
   than consuming it), it double-counts against a scout grade that already saw the injury on
   61% of rows, and it is priced twice into surplus through ETA. The health model is fittable
   today on MLB seasons (8,271 IL stints 2016-2025, 2,717 TJ surgeries) and the prospect-side
   substrate the closure said was missing actually exists (283 hit / 320 pit training rows
   carry pre-cutoff IL placements in `player_transactions`, against a revival trigger of 100).
   What cannot be validated until roughly 2028 is a prospect-outcome claim.
8. **Verified sound, and worth saying:** the Quantity B estimand (busts at zero), the
   inverse-variance censoring weight, the pooled outcome curve over the per-side split, the
   location-only source normalization, equal source weights, the Platt re-link on the eFV
   odds seam, surplus as an expected value, the at-debut WAG baseline pin, and the entire
   controls apparatus. The audit re-derived each and none moved.
9. **Scope discipline:** of the 30 verified findings, 3 conflict with a closed lane and say
   why they are a different question, 7 are owner decisions to revisit under the new goal,
   14 are partially adjudicated, and 6 are new. No finding proposes re-running a closed
   feature arm.
10. **The one thing to do first** is not on this list: derive the floors on the finished
    frame before reading any margin. Three of the last four sessions produced a number that
    later moved because a margin was read against a stale artifact.

---

## 1. The design chain as it ships

### 1.1 eFV, input to served number

| stage | what happens | where |
| --- | --- | --- |
| label | first-6-MLB-season summed bWAR, window = debut_year..debut_year+5, busts 0, censored rows projected at the observed rate with weight n_obs/6 | `efv_dataset.py:929-941`, `:270` |
| features | 14 hitter / 9 pitcher standardized keys; `fv` = `consensus_fv_raw` is dominant | `efv_model.py:112`, `:271` |
| fit | weighted ridge, alpha in {1,10,100} by 5-fold weighted MAE, then an in-sample affine (a,b), clamp at -2 WAR | `prospect_path.py:245-305`, `efv_model.py:1340-1368` |
| anchor | `cons_war = max(0, OLS(fv))`, unweighted | `efv_model.py:1323-1335` |
| blend | `rank_war = (1-lam)*cons_war + lam*xfv_war`, lam pinned 0.70 hit / 0.57 pit for stability | `efv_model.py:598`, `:853-866` |
| live tilts | injury, prospect age, reliever ceiling, Statcast+, S-XLINE lean, stale-anchor decay; multiplicative on the model leg only | `efv_score.py:1011-1270`, `:2176-2229` |
| grade | `xfv_grade = outcome_implied_fv(xfv_war)`, the **model leg alone** | `efv_score.py:2283`, `storage.py:4904` |
| routing | constant-anchor rows at the floor knot serve the provisional map instead | `efv_score.py:278-289` |

### 1.2 The four grade bases on one player

| served field | map | keyed on | consumer |
| --- | --- | --- | --- |
| `xfv_grade` | `outcome_implied_fv`, pooled empirical inverse | model leg | board grade, board order, farm, movement |
| `_odds_grade` | `realized_implied_fv`, retired engine inverse, **not exported** | model leg | `p_bucket`, `p_bust`, star odds |
| `xfv_grade_display` | rank quantile of `rank_war` onto the pool's consensus FV distribution | blend leg | surplus dollars, the fan, FA blocker |
| routed grade | `efv_ungraded._GRADE_MAP`, hand-set linear (hit 27 + 3.8w) | provisional no-FV ridge | 52.8% of served grades |

Board and odds grades agree on 76.8% of rows below FV 40, 1.6% between 40 and 45, and
**0.0% above FV 45** (`efv_export.py:124-127`). At 10 predicted WAR the board reads 58.6 and
the odds key 61.7.

### 1.3 consensusFV

Forward-filled latest snapshot per source, each source's FV put on the FanGraphs scale by a
per-(source, role, cycle) location offset, equal-weight mean, single-instance pull one third
toward FV 35, rank-implied fallback only when no source graded the player, a fabricated
constant FV 35 for players nobody graded, displayed with a ceiling round.

### 1.4 WAG

| path | baseline grade | curve | transform | surface |
| --- | --- | --- | --- | --- |
| engine `value_framework.wag` | eFV at debut | bust-inclusive mixture over exposure | PIT percentile | card, pill, sorts |
| legacy `storage._grad_wag` | **served** eFV | survivor curve | positive deltas 0.7d + 0.3W, times an outcome penalty | farm Talent Translation |
| prospx `gradVsFvProjection` | consensus `fv_close_raw` | hardcoded JS anchors | none | Debuted list, WARWAG |
| glossary | consensus | primer table | none | the published definition |

---

## 2. Errant or questionable decisions, ranked

Format: **(a)** decision and where, **(b)** the recorded rationale, **(c)** why it is
questionable, **(d)** evidence, **(e)** the fix as the verifier revised it, **(f)** effect
class, **(g)** closure status, **(h)** the gate.

### F01. The consensus term is linear while the grade map is convex (accuracy, large)

(a) `fv` enters the ridge linearly and `cons_war = max(0, OLS(fv))`, while
`xfv_grade = B^-1(xfv_war)` inverts the convex pooled curve (`efv_model.py:113`, `:271`,
`:1323-1335`; `efv_score.py:2124`; `data/fv_outcome_curves_pooled.json`).

(b) `_fit_ols_fv` is documented as "the bar" whose Spearman equals the FV rank correlation;
a linear term is the minimal regularized prior, and every feature arm was scored on rank,
where a monotone transform of the dominant feature is nearly invariant.

(c) Coherence requires `B^-1(model(fv, X=0)) = fv`. A least-squares chord under a convex
function lies below it at both ends. Production hitter OLS is `-18.3855 + 0.4876*fv`, zero at
FV 37.71, so the anchor is negative across the bottom third of the board where no cohort mean
is below -0.007. The grade map correctly refuses negatives and returns the floor, which makes
the floor population an artifact of the anchor's shape.

(d) In-sample cell means against cell predictions, hitters: FV 35 realized 0.078 vs predicted
-1.115; FV 40 0.399 vs 0.965; FV 55 10.010 vs 8.18; FV 65 15.944 vs 13.52. On live tracked
rows with a non-positive prediction, the non-`fv` part of the prediction is non-negative on
487 of 495 hitters (98%) and 359 of 385 pitchers (93%). Round trips: a consensus 40 returns
42.98, a 45 returns 47.68, a pitcher 55 returns 49.53.

(e) The verifier split the finding. **(A)** Feed `B_pooled(fv)` to the ridge; this is the only
path that reaches `xfv_grade` and the floor cohort. **(B)** Leave the OLS anchor as the eval
bar; changing the blend leg moves dollars and the effective lambda, which is a separate owner
decision. **(C)** Weight the anchor OLS with the same censoring weights the ridge uses, or
document why not. The verifier **removed the top-end half of the claim**: `B_pooled` equals
the hitter chord at FV 60-65 and sits below it at 55, so this does nothing for elite hitters,
and out of fold the uncorrected model already over-predicts them (+1.78 bias at consensus
>= 50).

(f) Accuracy at the level, plus coherence: `eFV - consensus` becomes a deviation rather than
chord geometry.

(g) PARTIALLY ADJUDICATED. Ledger item 1 closed 39 arms scored on Spearman and AUC, which a
monotone transform of the dominant feature barely moves; this is a level question (per-band
bias, floor share) those arms could not see. `B(fv)` as a predictor has been measured once out
of fold (`xfv_elite_band_eval` arm C: full-pool MAE 1.877 vs 2.566 hit) but never as a ridge
input.

(h) Three arms forward-chained on 11 folds per side: incumbent, `B_pooled(fv)` replacing `fv`,
and both present. Floors first: E_cond MDE95 for per-band MAE and signed bias. Primary: signed
bias per consensus band and floor share against the realized share of cohort means at or below
zero. Rank guard: TOST non-inferiority at 0.02 on pooled rho and contributor AUC. A shipped
arm is a grade-basis epoch.

### F02. The output calibration is fitted in sample, where it can only expand (accuracy, moderate)

(a) `fit_production_stack` fits (a,b) by unweighted OLS of the label on the ridge's own
in-sample fitted values; the served dispersion correction is identity since C-7
(`efv_model.py:1357-1364`, `efv_score.py:258-262`).

(b) The step is named the mean-path correction for over-projection, and the forward-chained
eval fits it the same way on train, so eval and production agree on the estimator. C-7 is an
honestly recorded owner decision: every family that calibrates the slope deflates the elite,
and the owner chose industry agreement with the accuracy debit stated in advance.

(c) For ridge fitted values the in-sample slope of label on prediction is at least 1
(measured 1.044 hit, 1.074 pit), while out of sample the prediction is over-dispersed
(0.65 / 0.59 on the current frame). The served level therefore moves in the opposite
direction to the measured error. The verifier corrected the attribution: the in-sample step
accounts for 4-7% of inflation against an OOS slope deficit of 0.35-0.45, so the errant piece
is that (a,b) is estimated in sample rather than that it exists.

(d) 3,392 of 4,687 actives at or below zero predicted WAR, 328 at the -2 clamp, 1,155 at grade
20.0. C-1c measured the corrected arm resolvably more accurate on the full pool (paired MAE
-0.2787 hit CI95 [-0.334,-0.224]; -0.1415 pit). The verifier also measured the censoring
channel through (a,b) and found it immaterial (resolved-only b within 0.001 hit, 0.06 pit), so
that leg of the census claim is dropped.

(e) Source the coefficients from a leave-one-fold-out affine on the raw ridge prediction and
apply them **at the grade seam**, not inside `fit_production_stack`; routing the correction
through the production fit pushes it into `rank_war`, which is a banned lambda change. Put
the top-band table (bias and MAE at consensus >= 50 and >= 55 per side, with n) beside the
full-pool accuracy column so the owner sees the cost. Independently: the glossary still
describes the retired affine as live.

(f) Accuracy in level (no rank change: rank invariance is established, C-7 moved zero
dollars), plus product honesty.

(g) OWNER DECISION. Ledger item 5 bans a sixth correction family; re-applying the measured
first family is not a new family, and `efv_score.py:251-253` records the reopen burden as new
resolved cohorts. The reopen condition is either an explicit owner instruction that level
accuracy outranks elite agreement, or the RESOLVED_THROUGH 2026 refit.

(h) As C-1 was gated: OOS slope CI covering 1, paired full-pool MAE, rank invariance inside
the floor, FV20 population, elite band bias per side with n, and the effective pitcher lambda
proving the blend leg did not move.

### F03. The label window starts at the calendar debut year (accuracy, small; coherence, real)

(a) `_label_6yr` window is `debut_year..debut_year+5` regardless of debut date
(`efv_dataset.py:929-941`).

(b) The module header, the curve's window contract and the owner's "keep 6, document"
decision.

(c) The framework's Quantity A is average annual WAR over the first six **service** years and
Clemens's control window is roster-day based and never shorter than six seasons; a September
call-up does not burn a service year. The shipped label spends season 1 of 6 on the stub.

(d) Hitters debuting on or after 1 August (n 55 resolved through 7 seasons) log 0.151 WAR in
the debut year against 1.175 in year+6, so service alignment adds 1.024 WAR, 19.4% of their
label. 209 of 845 hitter and 254 of 983 pitcher debuted rows debut on or after 1 August. The
verifier corrected the census twice: the 15-20% loss holds for hitters at 1 August and
pitchers at 1 September, not for a quarter of the pool; and the re-date discontinuity is
mechanically wrong (the trigger is a missing season line, and it fires four times in 2,742
records).

(e) Define the debut season as service year 1 only if the debut is on or before roughly
opening day plus 14 days, else shift the window and add the stub WAR (Clemens's own
construction). Rebuild the pooled curve on the same label so `outcome_implied_fv` keeps its
window contract. **Do not fold it into the frozen RESOLVED_THROUGH-2026 pre-registration**,
which freezes the C1-C4 cells on the existing label.

(f) Level accuracy for late-debut players; rank content is invariant (Spearman between the two
labels 0.9992 hit, and rho against consensus moves +0.0004).

(g) PARTIALLY ADJUDICATED. The 6-versus-7 horizon was an owner decision recorded without an
artifact; the service-alignment sub-question is new.

(h) Runnable now on the 401 hit / 424 pit rows with seven observed seasons. Pre-register the
rank cell as a TOST equivalence check, not a superiority claim, and the level cell under the
LABEL_CENSORING materiality rule. Cheap by-product already computed:
Spearman(label6, label7) is 0.9963 hit and 0.9881 pit, which replaces the un-artifacted
"7 seasons lose accuracy" line in the memory.

### F04. `milb_unavailable` rows are imputed at the floor, not at neutral (coherence, small)

(a) The docstring says unavailable rows "stay NEUTRAL (0.0)"; in fact only `milb_missing` is
zeroed and age mean-imputed, while `level_rank`, `n_milb_seasons` and every rate key take raw
0.0 (`efv_model.py:1177-1214`).

(c) Standardization makes raw 0 neutral only at the pool mean. `level_rank` pool mean 1.913,
sd 1.938, so raw 0 is -0.99 sd against the pool and -2.27 sd against rows that have a MiLB
block. The unavailable block is 38.8% of the hitter pool at a 64.0% bust rate against 47.3%,
and 46.4% of the pitcher pool at 70.1% against 30.4%.

(d) The verifier added the decisive measurement: the block is an era proxy
(corr(has_milb, decision_year) 0.568; coverage 0.00 in 2011-2014 and 0.89 in 2024) holding two
populations with opposite labels (pre-2016 unavailable rows bust at 0.245, post-2019 no-block
rows at 0.961). Consequence: the shipped `level_rank` slope is 0.154 WAR per rung against
0.209-0.253 when the block is imputed at the has-MiLB mean, so level proximity is under-priced
by a third to a half.

(e) Do not ship a null through the flagship on the accuracy goal alone. Three tiers:
correct the docstring now; give the pre-2016 rows an era intercept or restrict the MiLB-block
coefficients to has-MiLB rows in a two-stage fit; and if an arm ships, ship it as part of a
rebuild with the AAA-versus-A gap movement disclosed.

(g) PARTIALLY ADJUDICATED. The exact arms were measured null on 2026-07-25 under a retired
basis and never ledgered.

(h) Per-feature E_refit and E_cond floors for the `level_rank` and `n_milb_seasons` cells,
the t45 fringe cell where `level_rank` earned its place, and a live-robustness clause.

### F05. The eval scores the blend; the board serves the model leg (coherence, small accuracy)

(a) `BOARD_GRADE_FIELD = xfv_grade` is the model leg alone, while `xfv_eval*.json` declares
the shipped model to be "blend" and every published accuracy sentence describes `rank_war`.

(c) An accuracy figure describes the object it was computed on. Three different objects are
called "blend" (`_run_eval` blends the raw ridge; `oos_grades` and `run_live` blend the
calibrated, clamped leg). The verifier corrected the census's lead: "served below the
consensus bar on pitchers" is an unfloored -0.0099 between two different fits, 0.23x the
applicable floor, and must not lead. What survives is that the pitcher served-versus-blend cell
sits at 0.975x its paired floor and is **undecidable at current n** (TOST needs
|delta| + floor < 0.02; 0.0153 + 0.0157 exceeds it).

(e) Ship the honesty half now, because no served number moves: one `blend_war` helper so
"blend" names one object; add a `served_leg` block to the eval artifacts carrying the served
grade's own rho and floors; derive the hero copy from the served leg; rewrite the conventions
block and the stale lambda rationale (the pitcher pin's stated reason, that a reselect
re-prints every board grade, was already false when it was written, because the board grade
left `rank_war` on 2026-07-25).

(g) PARTIALLY ADJUDICATED for the honesty half (available today, owner decision), and the
accuracy half reopens only on a new label frame.

### F06. The public claim cells pool Spearman across base years with different label scales (accuracy of the measurement)

(a) The head-to-head label is cumulative career WAR to run date, pooled across base years
2017-2023 with plain Spearman (`source_backtest.py:264-286`, `:1167-1185`).

(c) Label scale is a function of base year (2017 debuts have about nine observed seasons,
2023 about three), so rank(year) correlates with rank(WAR) and any rater whose grade level
drifts with coverage earns credit from the year axis.

(d) Verified CONFIRMED with the mathematics sound. On the vintage-matched frame (n 803),
pooled versus n-weighted within-year rho: FanGraphs 0.3489 / 0.3334, Pipeline 0.3990 / 0.3755,
consensus 0.3949 / 0.3736, eFV 0.3998 / 0.3928. The nominal ordering flips (Pipeline leads by
0.0007 pooled; eFV leads by 0.0173 within-year) but **the verdict does not**: the corrected
delta is roughly 0.55x the registered floor, so C1 and C2 stay unresolved either way. This is
a measurement-honesty defect, not an accuracy lever, and the within-year lead must not be
quoted as a win.

(e) Block-normalize within base year as the primary instrument (already implemented and
registered), report the exposure-matched six-season label as the secondary leg, publish both
frames as receipts, and have the owner sign the frame change before the V1 read.

(g) NEW. Not closed anywhere; the M-1 frame work addressed timing and dedup, not exposure
scale.

### F07. The outcome mixture is population-inconsistent (accuracy of every shape functional, moderate)

(a) `p_bucket_given_fv` is a proportional-odds fit whose only training rows are the Clemens
2025 published percentage tables (`value_framework_config.yaml:56-83`;
`data/value_framework_fitted.json` training_n 678 / 437), with bucket levels solved by k(FV)
to reconcile to `fv_to_6yr_avg_war`.

(c) With P(bust) fixed from a population with roughly half our bust rate and E[WAR] from our
own anchor, the survivor level is forced down: k(FV) is 0.349 at hitter 45 and 0.535 at 60, so
the star bucket at hitter 60 is 2.67 WAR/season against its own band floor of 4.0, and
`survivor_expected_war(60, hit)` is 1.546 against the bust-inclusive pooled curve's 1.824 at
the same FV, which is impossible for a coherent mixture. Three bucket definitions coexist: the
config's per-season talent bands at a three-year horizon, the monitor's realized six-year
averages, and the engine's k(FV)-scaled midpoints.

(d) Verified with the mathematics sound. Model star odds at FV 60 read 0.057 against a
published 0.33 and a realized 8 of 21. Registry and glossary provenance is wrong: the glossary
says the buckets are "estimated from the site's own resolved cohorts".

(e) Split. Step 1, documentation only: name the Clemens training tables, the sub-45
extrapolation and the 50/50 Edwards blend; regenerate the stale registry numbers; label the
dead fitted midpoint block. Step 2, one registration: replace {P(b|FV), k(FV), band priors}
with a population-consistent object fitted on the resolved frame, ordered logit shrunk toward
the Clemens shape with per-band conditional means from the same rows.

(g) PARTIALLY ADJUDICATED. Recalibration **maps** of the borrowed curve are closed (ledger
item 6); a joint refit of probabilities and levels on one label definition is not adjudicated
anywhere.

(h) Proper scores (RPS, multinomial log loss) with a Murphy decomposition against the
zero-information constant, both estimators, star column pre-declared unpowered where stars are
under 20 per side.

### F08. Two E[WAR|FV] curves coexist (coherence, moderate)

(a) `fv_to_6yr_avg_war` is 0.5 times our cohort mean plus 0.5 times an Edwards-implied public
reference, pooled across sides, and it prices dollars, keys odds and baselines WAG; the board
grade inverts a different curve.

(c) Both estimate the same quantity. A flat 0.5 weight is not shrinkage (K/(K+n) at n 1,415
would be 0.021). At FV 45 the anchor serves 0.31 against a cohort mean of 0.126 and a resolved
curve of 0.378.

(d) The verifier corrected the mechanism: the anchor's low means are **not** censoring
(closed-window means 0.111 / 0.523 at 45/50 against all-rows 0.130 / 0.502) but frame
construction, a raw source FV averaged over up to seven years of snapshots across two sources
on different scales, which is also future-informed. The 0.5 blend then accidentally repairs
FV 45 and under-repairs 50-60. So the resolved evidence points **up** at every knot 45-65,
the opposite of the census's stated direction at 45.

(e) Do not write a third estimator. Have one fitter own the estimand: `empirical_anchors`
consumes the eFV matrix frame (or reads the pooled curve at the tier knots) with the per-side
Clemens control-war prior at K/(K+n) replacing `blend_weight_public`, then re-fit the v6 dollar
map on the new raw layer.

(g) PARTIALLY ADJUDICATED. Not on either ledger. The 2026-07-29 owner decision left FV 45-80
untouched on a coin flip; the frontier audit's warning against zeroing the blend applies to
the naive frame, not to a resolved-frame refit.

### F09. Four grade bases (coherence, small)

Covered in section 1.2. Verified CONFIRMED on every load-bearing claim. The verifier rejected
one argument: the BLP tail-bias story does not apply because the reference marginal is the
consensus distribution, another shrunk predictor, so the quantile map narrows rather than
widens. The correct defect statement for dollars is rank-only dependence, pool relativity, and
grade-versus-dollar ordering disagreement within side.

Fix sequence: export `_odds_grade` now (owner decision S-3 of 2026-08-13, no measurement
needed); then unify the forward curve (F08), after which the two inverses nearly coincide and
the odds re-key becomes a near no-op; only then re-key odds and dollars in one epoch.

### F10. FanGraphs "+" tiers are discarded at ingest (accuracy, small)

`_parse_fv` returns the bare tier, so 45+ reads 45 on the dominant feature, while the
p_bucket training axis places 45+ at 47.5. Latest FanGraphs board: 745 of 1,384 rows carry the
flag (53.8%); 1,019 of 4,687 actives carry it.

The verifier narrowed the claim: the information loss is concentrated at 35+ and 40+ where the
realized gap is 0.0-0.45 WAR over six years, the sides disagree about what "+" buys, and the
45+ cell is unidentified today (n 9 / 7 resolved). Fix by cost: retire the stale ingest comment
and collapse the duplicated axis keys; move the p_bucket 45+ abscissa to the Clemens-consistent
45.8 hit / 46.5 pit; and fit a per-side increment with K=30 shrinkage only for 40+ and 35+,
under the consensus vintage A/B gate.

### F11. The age overlay contradicts its own non-measurement rationale (accuracy, moderate)

The ramp (onset 23, -0.10 per year, floor 0.75) is justified as un-gateable because the
training pool is survivorship-censored to debuted players. That is factually stale: the pool
includes 1,054 hitter and 1,051 pitcher bust rows, and the eval has a full-pool cut. The
served ridge fits age **positive** conditional on FV; the overlay subtracts 10% of E[WAR] per
year, three times larger and opposite in sign, on 1,933 of 4,687 actives (1,378 above the
floor). The onset was chosen to move one named player, documented honestly as policy.

The verifier's measurement: conditional on FV the age slope is positive on every frame, and a
hinge at 23 is null with wide intervals; the overlay's mass sits at ages 23-25.5, a region the
frames **do** observe, while the genuinely unobservable class (old and graded) is where the
ramp is already at its floor. Two quantities are conflated: E[WAR | reach], already in the
ridge and rising with age at fixed FV, and P(reach | age), which the pool cannot see for old
graded rows.

Fix: correct the docstring (the unobservable class is never-**listed**, not never-debuted);
run the serve-rule sweep on the full-pool frame (onset 23/24/25 by slope 0.05/0.10, Holm); if
no no-harm band clears, remove the ramp from the 23-25.5 band and keep only a bounded
never-listed hazard above 26, or move the whole ramp out of the grade into a labelled age-risk
indicator that achieves the same policy without touching the accuracy component.

### F12. The current-IL haircut (accuracy, small; coherence, real)

See section 3 for the full treatment. Verified CONFIRMED. The verifier found one plain bug
worth stating here: for 245 constant-anchor rows the served grade is the provisional map while
the healthy counterfactual is computed through the pooled map floored at 20, so
`xfv_grade_healthy` is **lower** than the served grade on 192 cards, and both the export
comment and the card copy assert a basis identity the code does not implement.

### F13. The health-model closure was measured on the wrong substrate (accuracy, small)

`il_stints_pre` reads `il_history` (a scrape that started 2026-06-06), and the registry closed
the lane as coverage-starved at 2 of 845 hitter rows. But `player_transactions` (8,054 players,
187,444 transactions, 2019-2026) is already parsed into `injury_history` by `storage` for the
live board, and joined to the training matrices it gives pre-cutoff IL placements on **283 of
845 hitter and 320 of 983 pitcher** debuted rows, against a revival trigger of 100. The
closure premise is falsified on the repo's own data.

The verifier measured the prospect-side signal: restricted to payload-bearing rows with cutoff
year 2019 or later, a weighted regression gives -0.90 WAR for hitters (permutation p 0.044)
and -0.49 for pitchers (p 0.074), correctly signed, marginal, and confounded three ways
(censoring, roster-tracking selection, and asymmetric bust coverage). Honest prior: small,
possibly detectable, not yet shown.

### F14. Forward-filled grades are served as today's consensus (product honesty)

Each source's latest snapshot is carried forward indefinitely at weight 1.0 with no as-of date
and no stale state, while eFV's own input decays. Measured: 536 of 2,023 real-graded actives
have a newest vote older than a year (243 older than two years), and the site's own re-listing
study says dropped players in the 35-45 bands bust at 0.893-0.938 and realize an implied FV of
20.0-23.5 against re-listed controls at 30.6-37.9.

The verifier separated the claims. Product honesty: sound, and needs no measurement, because
`anchor_asof_date` is already in the live matrices. Accuracy: the census overstates, because a
second fitted staleness charge adds no information beyond E-STALE's own frame, and on the
grade it is nearly inert (257 of 278 discounted rows were already at the FV20 floor). Fix:
serve the as-of date and a tri-state freshness marker, show the decayed consensus beside the
raw grade where a discount applies, difference the delta chip against the decayed value so the
chip stops encoding staleness as disagreement, and delete the never-firing drop-off shrink
rather than fitting it.

### F15. The Clemens prior enters at span factor 1.0 (accuracy at the top, small)

The curve's prior is the Clemens 2026 table at factor 1.000, although that quantity spans six
to seven-plus control years while our label is exactly six seasons. The lab's own
pre-registered sensitivity (factor 6/7) has **lower bias and lower MAE on both sides**
(hit bias -0.248 to -0.039, MAE 1.604 to 1.530; pit -0.167 to -0.035, 1.179 to 1.116), and the
top knots are 57-97% prior. Fix: estimate the horizon factor in fold as a bounded scalar, or
declare it and report both. Effect is confined to predicted WAR above about 10, roughly the
top 30-50 live rows, and it moves grades **up**, which bears on F02.

### F16. Baseball America's risk axis is discarded in normalization (coherence, moderate)

For 2023-2025 vintages the stored BA field is the raw upside grade with risk carried
separately, and the normalizer reads only `fv`. A single location offset assumes the
FanGraphs-minus-BA gap is constant across risk tiers; it is not. Paired same-player residuals
after the offset: Medium about -4.4, High -0.9, Extreme +3.5, stable in each of 2023, 2024 and
2025, with an OLS risk coefficient of -2.02 per tier. In the 2026 adjusted-basis cells the
residual shrinks to +1.7 / -1.5, which is the natural control: the defect is the raw basis, not
BA.

Verified CONFIRMED with the mathematics sound. The verifier preferred putting BA on one basis
before normalizing (derive an adjusted grade with a fitted per-tier penalty, hierarchically
shrunk) over stratifying the offset, because it removes the era seam rather than adding to it.

### F17. The pooled side-neutral curve, and what the code says about it

The policy is defensible (one eFV means one expected WAR) but the code's rationale cites a
whole-pool MAE control that could not see a top-of-board side gap by construction (2,458 of
3,037 rows sit at consensus 45 or below, where the sides do not differ). The honest rationale
is "unresolvable at current n, plus policy". The verifier rejected the census's proposal to
implement the narrow FV-45 correction: that is exactly the E2b-narrow arm, already run and
NO_SHIP on all three clauses. Documentation and disclosure only: restate the rationale, publish
a per-side FanGraphs-equivalent as a secondary field, label the served grade as a cross-side
value grade, and retire the obsolete board-scale module's present-tense claims.

### F18. Half the served grades ride a hand-set provisional map (coherence, small)

52.8% of grades carrying a basis are `provisional_capped`, served through a linear map
calibrated to a distribution spec ("most land 20-30"), jointly ranked with outcome-scale
grades that disagree by -7 to +13 FV at matched WAR. The routing has no registry row although
the ship doc names one.

Fix in two steps: write the registry row now and add the routed share to the claims-freshness
test; then, rather than inverting the pooled curve over its prior-only 20-30 segment, fit a
calibration on the thin-sample cohort and serve the inverse only above the data-backed knot,
keeping the provisional grade as the sort key below it.

### F19. The abstention is labelled 20.0 (product honesty, moderate)

`outcome_implied_fv` returns 20.0 for every non-positive prediction, and knots 20/25/30 are a
synthetic concave re-spread the artifact itself calls "NOT a measurement": 15 FV points span
0.069 WAR, a slope of 830 FV per WAR between 20 and 25. 1,155 of 4,687 actives (24.6%) print a
grade FanGraphs never publishes.

The verifier corrected the argument's basis (comparing to McDaniel's per-season Quantity A
table is the trap; under Quantity B the honest statement is that no graded cohort has a mean
below about 0.04, so every prediction at or below the FV 35 knot value is at or below the
lowest identifiable cohort mean) and corrected the mechanics: define abstention on the WAR
side, not on grade equality, or moving the floor strips 2,473 provisional grades; serve 35.0
with an "at most 35" render and an `abstain_floor` basis; keep the synthetic knots in the
artifact as provenance and stop inverting below knot 35 instead.

### F20. The claim cells contain no never-debuted players (coherence, moderate)

The verifier found the mechanism misattributed and the population fact stronger than stated:
the vintage-matched filter is not what removes busts, the head-to-head universe never loads
`inactive.json` at all, so **every** frame contains zero true busts while eFV's own OOS pool
is 55% busts. The framework nets bust risk into the grade, so the published claim cannot see
the half of the label space that risk-netting is for.

Fix: add the never-debuted records to the universe (1,714 common rows / 825 players available
now), match busts on base year equal to cutoff year, keep the debuted-only cell as the shipped
headline until the bust-inclusive cell clears its own floor, and stop scoring **active**
undebuted players as zero WAR (they are censored, not busts). The AUC leg on a bust-inclusive
frame stays closed.

### F21. The forward chain averages eleven models, none of them the deployed one (accuracy, small)

The deployed ridge trains on about 845 / 981 rows; scored folds train on 90 to 754. The
verifier found the census's headline stale: the learning-curve slope on the current pooled
debuted cells is null (hit -0.005, pit +0.028, both intervals straddling zero) and the one
positive slope was measured on a retired frame. What survives is that the promotion's stated
purpose (power) was falsified by the standard's own text, and the thin-fold refit variance is
the component that makes E_refit cells undecidable. Fix: do not move `SCORED_YEARS` (seven
chain seams share the guard); surface the existing per-fold series and the deployed-n
prediction as a labelled companion, and register an `n_train >= 250` companion frame in the
2026 pre-registration.

### F22. The lambda band truncates the encompassing question (accuracy, small)

The owner's real question, does eFV add information the consensus lacks, is a
forecast-encompassing question. The verifier rejected the causal story (the endpoints are
measured on every frame and the shift floor scales with the step) but agreed the **statistic**
is missing: run the level-based encompassing regression once
(`y = a + b1*cons_war + b2*model_war`) and publish `b2` with its interval as the single "does
eFV add information" number. Drop the proposed Spearman-argmax interval, which is degenerate
on a curve whose slope sign flips by frame.

### F23. Floor conventions (documentation)

Three separable defects: E_refit floors ship raw although a 1.45x coverage correction was
pre-registered; "MDE95" is a one-sided 1.645 sd bar applied to an absolute value, so the
centered size is about 0.10 while the copy says 95%; and floors are quoted on pooled n while
the binding constraint is the resolved-and-featured intersection. The verifier rejected
publishing a corrected E_refit (it is inconsistent with E_cond on 8 of 14 cells) and
recommended demoting E_refit to a replication diagnostic with E_cond as the only quoted floor,
plus renaming the bar or requiring a pre-registered sign.

### F24 to F30 (five unverified, one verified)

**F24 (unverified).** The engine WAG baseline is bust-inclusive, so a graduate is compared
against an expectation that includes outcomes impossible for him: at FV 45 with P(bust) 0.505,
an exactly average survivor reads a PIT of 0.636. Realized settled graduates read a mean PIT of
0.560 with boom and bust shares of 24.5% and 7.8% against a 20/20 design. The coherent baseline
is `E[WAR | FV, debuted, exposure]`, which lies between the two curves the code currently
offers.

**F25 (verified, large).** WAG's three paths. Verified CONFIRMED with the mathematics sound.
The legacy transform is discontinuous in slope at zero, non-invertible, adds a level term to a
residual, and reads current age and level to modify past production, so `E[WAG | on grade]` is
not zero and the farm branch ranks orgs by a leaderboard preference. Fix: one definition
(engine WAG on the at-debut grade, baked once, every surface reading the baked block), delete
the duplicates, and if a sustained-performance filter is wanted apply it as a display filter,
not inside the metric.

**F26 (verified, moderate).** WAG counts exposure in calendar seasons at a full 600 PA or 200
IP each, while the median real load is 0.31 of a season, and 769 of 1,580 settled rows have
zero MLB PA or IP recorded, which a `pa or None` seam converts into "unknown" so the gate
passes on a fabricated full-season load. The verifier separated the owner's estimand (seasons,
deliberately, so injuries count) from the defect (the **measure** of a season): use service
time, not `len(seasons)`, pass a measured zero as zero, and fit the Marcel constants rather
than asserting them.

**F27 (unverified).** The WAG registry row is "validated" against an artifact containing no
WAG evidence, and the only PIT test samples outcomes from the model itself. Separately,
`wag_calibration`'s regressand is measured against eFV, so a perfectly calibrated eFV yields
slope 0 rather than 1: the identification is broken independently of the recorded leak.

**F28 (unverified).** The consensus-FV consumers of `p_bucket` (trade machine, projections,
the PROSPX bucket bar) serve the uncorrected curve, which the Platt lane itself measured to
under-call bust by 0.11-0.17 at that key and to lose to climatology.

**F29 (unverified).** The surplus fan applies a mean-calibration map to quantiles of a hand-set
dispersion; measured p10-p90 coverage is 0.59 raw and 0.73 held out against a nominal 0.80.

**F30 (unverified).** The uncapped Statcast lean moves flagship grades by up to 5 FV and 325
ranks on a screen validated against next-season K% residuals rather than WAR, with its
coefficient asserted. Owner checkpoint: either move it to a displayed indicator or size the
coefficient from the interval's lower bound and restore a numerical ceiling.

---

## 2b. Census-only findings (18, not verified this session)

F31 Statcast+ tilt keyed to the wrong outcome, multiplicative where its sibling is additive,
applied outside its calibration cohort. F32 a fabricated FV 35 displayed as the consensus for
2,689 of 4,687 live players while the site's own provisional model puts their median at 26.4.
F33 same-name timeseries merged without an identity check. F34 the single-instance pull shrinks
toward 35 rather than the graded-pool mean (about -0.5 to -1.8 FV of deterministic bias).
F35 the location offset is not constant along the scale (Pipeline-minus-FanGraphs 2.8 at 40
against 4.9 at 50) and is extrapolated to org-list players at the bottom. F36 tool grades
feeding eFV are an unweighted cross-source mean with no scale correction while the same
sources' overall grades are corrected (Pipeline hit +4.65 against FanGraphs). F37 the low-tier
dollar anchor is an Edwards 2019 constant under a valuation set that claims Clemens 2026.
F38 ridge alpha is selected by MAE on a label whose conditional median is zero, and lands on
the grid edge. F39 the -2.0 clamp is underived and the tie-break key ignores both the clamp and
the live tilts. F40 no floored top-weighted or proper-score companion exists on the claim
frame. F41 the burden of proof is asymmetric between accuracy candidates and product changes.
F42 the top of the scale is degenerate (FV 70-80 spans 0.02 WAR by an epsilon step). F43 ceil
display of the consensus beside a round-nearest eFV makes the delta chip arithmetically
inconsistent. F44 DvM+ chips are not on the scale the glossary claims, $DvM+ re-injects FV
growth into the Financial branch, and `FV_EXPECTED_WAR` is an invented career-total table
attributed to the primer. F45 KRP+'s product form is non-monotone in run prevention. F46
accuracy-claim surfaces publish superseded wins, including one hardcoded "ahead of the field"
template. F47 glossary and team copy misstate served mechanics. F48 consensusFV construction is
misdescribed on every surface, including a docstring that presents inert code as live.

---

## 3. The injury penalty and the health model

**The owner's question, verbatim:** "I'm also not sure about the injury penalty we do for
players that are on IL - should we instead penalize players based on a 'health model' that
evaluates injuries and injury severity to build a health profile on each player, and adjust
their grade based on that health model (and do away entirely with IL adjustments to FV)?"

**Answer: yes, build the health model and let it replace the dial, but not in one step, and
not on a prospect-outcome claim.**

### 3.1 What the current penalty is, mathematically

A multiplicative haircut on the model's predicted WAR while the player is on the IL, applied at
serve time only: 0.70 for a 60-day or full-season designation, 0.82 for moderate, a days-based
ramp saturating at 0.90 for mild types, then chronicity multipliers of 0.82 (120+ days in 12
months), 0.90 (60+ days) and 0.92 (three or more stints). It composes multiplicatively with the
age, reliever and Statcast dials with no composite floor, so the arithmetic minimum is 0.215.
It touches 580 live rows; the served grade delta averages 1.15 FV with a maximum of 4.6.

### 3.2 What is wrong with it

1. **Estimand.** All 580 penalised rows are pre-debut. The label is WAR over the six seasons
   from debut, so a lost MiLB season shifts the window rather than consuming it. The only
   channels an injury has into that label are P(never debut), talent loss and debut age. A flat
   0.70 is coherent only as an assertion that bust probability rises by 0.30 to 0.47, which
   nobody asserted or measured.
2. **Double counting against the grade.** FanGraphs nets injury risk into FV at list time. Of
   335 penalised rows with a real anchor, 205 (61.2%) were placed on the IL **before** the
   anchor's source date, median 65 days earlier, so the newest grade already saw the injury.
3. **Double counting into dollars.** Exposure is already priced through ETA (+1.0 year for
   60-plus days), and nothing states which channel prices exposure and which prices talent.
4. **Provenance.** The constants appeared fully formed alongside an unconditional post-TJ
   multiplier that was later shown to be wrong-signed; every later change anchored to them and
   was gated on board movement only.
5. **The severity class is a duration class.** `_IL_SEVERE_TYPES` is commented as the MLB
   60-day IL but fires almost entirely on the MiLB 60-day IL, which is an administrative
   duration, not a severity.
6. **A live bug.** For 245 constant-anchor rows the served grade comes from the provisional map
   while the "healthy" counterfactual is computed through the pooled map, so `xfv_grade_healthy`
   is lower than the served grade on 192 cards, under copy that asserts they share a basis.

### 3.3 What a health model would be

Per-player expected availability and re-injury hazard as a function of injury history (type,
severity class, recency, count), age and role, entering the grade as
`E[WAR] = E[rate | healthy] * E[seasons-equivalent | health profile]` rather than as a flat
haircut on the level.

### 3.4 What can be fitted today

| substrate | contents | use |
| --- | --- | --- |
| `player_transactions` | 8,054 players, 187,444 transactions 2019-2026; 14,337 IL placements, 11,226 activations | MLB hazard features and the prospect-side re-test |
| `.cache/war_daily` parquet | PA and IPouts per player-season | the availability label |
| `data/tj_surgery.json` | 2,717 surgeries, 2,516 players, 99.4% with an MLB id, as-of safe | severity and recency |
| `il_history` | 1,648 rows, 1,402 of them in 2026 | live status only, not history |

The MLB pool has labels on every row: 8,271 IL stints across 2016-2025 for 2,685 players. The
prospect pool does not, and cannot before roughly 2028, because MiLB IL history begins in
2026-06.

Two measured facts constrain the design. First, the "coverage-starved" closure that stopped
this lane was measured on `il_history`, the wrong substrate: on `player_transactions` the
training matrices carry pre-cutoff IL placements on 283 hitter and 320 pitcher rows against a
revival trigger of 100. Second, the sibling lane already ran the family: IL **day counts**
failed both arms on era drift, while **recent TJ within 24 months** passed at 8.39x its noise
level with the whole effect in recency. eFV's chronicity modifiers are exactly the failed
family.

### 3.5 The design refutation to fix before building

The health-model design draft was refuted on three fatal points, all of which must be answered
in the revision:

1. The transfer ratio is undefined at the apply location. Training rows require prior-season
   MLB exposure; every prospect row has none, and under an additive model the ratio depends on
   the persistence level at which it is evaluated, so a coefficient of a few hundredths sweeps
   the whole bound.
2. The served multiplier is decided by an ungated structural assumption: with no persistence
   past one horizon the multiplier is at least 0.95 for any first-horizon ratio above 0.70, so
   the assumed decay alone decides whether a haircut survives.
3. The apply-side input is a different construct from the training input: the live 12-month IL
   day count **includes the elapsed days of the current open stint** (live medians 63.5 and 80
   days), while training uses closed prior-season stints. A player 80 days into a stint is fed
   as if he lost 80 days last season.

### 3.6 Recommendation

1. **Now, no measurement needed:** fix the counterfactual routing bug and delete the "same
   basis" claims; apply only the chronicity component when the IL placement predates the
   anchor date; put a composite floor on the product of the dials.
2. **Next:** fit the hazard on MLB seasons 2016-2025 with severity class by recency, forward
   chained, target the exposure ratio, with the incumbent being prior-season availability
   carry-forward. Publish it as a Health profile card indicator with its measured effect.
3. **Then, and only then:** transfer to prospects as a bounded, pre-registered exposure
   multiplier, preferably as an out-of-fold column inside the ridge rather than a live-only
   tilt, so it sits inside the gate machinery instead of beside it. Retire `_injury_factor` in
   the same commit that ships the gated column.
4. **Do not** remove IL adjustments before that column exists: a current 60-day placement is
   real information that postdates the last list on 39% of penalised rows.

---

## 4. Decisions verified sound

| decision | why it holds |
| --- | --- |
| Busts at zero, negative seasons kept (Quantity B) | Matches the framework's bust-inclusive definition exactly; inverting E[label given consensus FV] yields a consensus-equivalent grade |
| Censoring weight n_obs/6 with the 6/n multiplier | Under the flat per-season model this is exactly the inverse-variance weight; the weight prices variance, the multiplier prices the mean. Not double handling |
| Scoring censored rows against the extrapolated label | Within a fold all rows share n_obs, so it is a positive rescale and Spearman is invariant |
| Pooled outcome curve over the per-side split | The per-side curve lost to its side-permuted control; the pooled inverse of the mean is the only inversion whose quantity matches the label |
| Inverting the conditional mean, not the median | With busts at zero the per-cell median is exactly 0.000 at every knot at or below 45, where 81% of the pool sits |
| Weighted PAVA with a per-knot prior | The x grid has a real hole between 43.0 and 45.5; a spline would interpolate it with basis functions rather than a stated prior |
| Routing decided on the uncorrected grade | Deciding on the corrected grade stripped 950 provisional grades onto the flat part of the flagship curve |
| Location-only source normalization | The WAR-per-FV slopes are near equal across sources (0.4204 against 0.4499), so a shift is the right correction; the quantile map was a near-identity on a discrete lattice |
| Equal source weights | The vintage A/B sits below its own gate on both legs; measured precisions are indistinguishable |
| Single-source pull toward a floor at k = 0.5 | 2/3 is within 0.04 of the derived lambda at k = 1; the shrink gate's interaction test collapses on the served scale |
| Constant-anchor votes never average beside a real grade | Closes a defect where a fabricated 35 diluted a published 40 to 36 |
| Platt re-link on the eFV odds seam | Correct diagnosis of a dispersion-induced slope error, two parameters, strictly monotone, gated against both the incumbent and a constant |
| Surplus as an expected value | The consumer is a price; MAE is minimized by the conditional median, which is zero for most bottom bins |
| WAG baseline pinned to the at-debut grade | Prevents realized WAR leaking into the subtrahend through post-debut re-grading |
| Exposure-matched, age-placed WAG expectation | A rookie is expected to produce less than his six-year average; the trajectory renormalizes so the six-year total is unchanged |
| Tilts applied to the model leg only, sign-aware | Avoids haircutting the consensus anchor twice and avoids a penalty raising a negative projection |
| The controls apparatus | Each control has a recorded case where its absence produced a false result |
| E_cond registration by two-sided coverage | Over-coverage fails like under-coverage; detection of the known-real effect confirmed |
| Player-clustered bootstrap for the head-to-head | Row resampling narrows the sd by 1.519x and under-covers at 0.800 |
| Per-feature floors | Paired-difference variance scales with how much the candidate moves the model |
| TOST at 0.02 with decidability triage | Converts nulls into ruled-out where the arithmetic allows, which is positive knowledge |

---

## 5. Owner decisions that traded accuracy for product or stability

| decision | measured cost at the time | does the accuracy goal argue for revisiting |
| --- | --- | --- |
| C-7, revert the dispersion correction to identity (2026-08-14) | Corrected arm resolvably more accurate on the full pool: paired MAE -0.2787 hit, -0.1415 pit, CIs excluding zero; FV20 floor grew 784 to 1,149 | **Yes.** The trade bought agreement on 13 to 34 elite rows. Revisit with the top-band table in view (F02) |
| Lambda pins 0.70 / 0.57 for run-to-run stability | Every shift ruled out by TOST; the selector prefers 0.50 on both sides | No. The pins are certified; but the stated rationale is stale, since the board grade left `rank_war` in July |
| `blend_weight_public` 0.5 in the anchors | Serves 0.31 at FV 45 against a cohort mean of 0.126 and a resolved curve of 0.378 | **Yes**, but as a resolved-frame refit (F08), not as the previously refused zeroing on the naive frame |
| Ceiling display of the consensus grade | Mean bias +0.165 FV, 34.6% of rows lifted a grade | Cosmetic; the real defect is that the delta chip is on the raw scale (F43) |
| Uncapped Statcast lean | Up to 5 FV and 325 ranks on a K-rate screen | **Yes**, as the checkpoint in F30 |
| The age ramp's onset chosen to move a named player | No accuracy measurement was taken | **Yes**: the frame that was said to make it un-gateable exists (F11) |
| Keep 6 seasons rather than 7 | Recorded as an accuracy cost with no artifact | Now measured: Spearman(label6, label7) is 0.9963 hit, 0.9881 pit (F03) |

---

## 6. Documentation and claim defects

| statement | code truth | severity |
| --- | --- | --- |
| Glossary: bucket probabilities "estimated from the site's own resolved cohorts" | Fitted on the Clemens 2025 published tables, training n 678 / 437, then Platt-corrected | public-facing false claim |
| Glossary: the affine dispersion correction "brings the calibration slope to about 1.0" | Identity since 2026-08-14; the quoted floor counts are the retired map's | public-facing false claim |
| `_methAccuracyChart` template: "eFV orders realized WAR ahead of the field" | Vintage-matched eFV 0.3983 against Pipeline 0.3990 in the same sentence; the hero two functions later renders "indistinguishable" correctly | public-facing false claim, banned class |
| `consensus.py` docstring: the k_eff / N_full Bayesian shrinkage | Inert; dead keyword arguments. The live path is the single-instance pull | internal stale note |
| Registry `xfv_hitter` / `xfv_pitcher` lead paragraphs | Retired 2026-06 claims ("BEATS consensus", "lambda is None") against an artifact whose honest note says every cut is null | internal stale note |
| Registry `wag` "validated" | The cited artifact contains no WAG evidence | internal stale note |
| `efv_score.py` age docstring: "the debuted-only training pool" | The pool carries 1,054 hitter and 1,051 pitcher bust rows | internal stale note |
| `xfv_grade_healthy` "same basis as xfv_grade" | Different map on 245 routed rows; lower than the served grade on 192 cards | public-facing, wrong number |
| `consensus.py:766` comment: "55+ maps to 57.5 on ingest" | The parser has returned the bare tier since v26 | internal stale note |
| Registry `xfv_injury_history` "coverage-starved" | The revival trigger is met three times over on `player_transactions` | internal stale note |
| `efv_model.py` comment: `milb_unavailable` rows "stay NEUTRAL" | Only `milb_missing` and age are neutral | internal stale note |
| Methodology: 9% discount, six control years | The shipped valuation set is seven years at net 7% | internal stale note |

---

## 7. Recommended program

Ordering principle: fix the estimand before fitting anything to it, derive floors on the
finished frame, and keep the WAR-basis epoch's attribution clean.

**W0, immediate, no measurement, no served number moves.** The documentation table in section
6, in one commit per surface, each pinned by a test that reads the code constant. Export the
odds key. Write the missing registry rows (floor routing, the health lane's substrate
correction). Fix the healthy-counterfactual routing bug.

**W1, the eWAR label epoch (already registered).** Run the runbook. Keep Appendix A minimal:
see section 9, question 1. Floors first, margins re-read only after regeneration.

**W2, the estimand lanes, in this order.**
1. F08, one E[WAR|FV] for grade, dollars, odds and WAG, derived on the resolved frame with the
   published table as a shrinkage prior rather than a flat blend.
2. F07, one population-consistent outcome distribution fitted on the same frame, retiring
   k(FV) and the borrowed band midpoints.
3. F09, the grade-basis unification that becomes nearly free once (1) and (2) land.

**W3, the model-shape lanes.**
1. F01 arm (ii): `B_pooled(fv)` as the ridge feature, three arms, level clauses primary, rank
   TOST as the guard.
2. F02: the leave-one-fold-out affine at the grade seam, with the elite table in front of the
   owner.
3. F04: neutral imputation or the two-stage fit, ridden on the epoch's rebuild.

**W4, the measurement lanes** (no served number moves, and they change what the site may
claim). F06 block normalization, F20 the bust-inclusive universe, F22 the encompassing
regression, F23 the floor conventions, F40 a proper-score companion.

**W5, the overlay lanes.** F11 the age ramp's serve-rule gate; F12 and F13 the health model as
section 3 sequences it; F30 the Statcast lean checkpoint; F31 the Statcast tilt.

**W6, consensus integrity.** F16 the BA risk basis, F14 the staleness state, F10 the plus
tiers, F32 the fabricated 35, F33 the same-name merge, F34 the shrink prior, F35 the offset
shape.

**W7, WAG.** F25 consolidation to one definition, then F24 the baseline conditional and F26
the exposure measure, then re-point the registry row at a real artifact (F27).

---

## 8. Refuted candidates

**None.** Every finding that reached a verifier survived with corrections. The five findings
listed as "killed" by the workflow (F24, F27, F28, F29, F30) lost their verifier to the session
budget and are unverified, not refuted; they appear above with that status stated. Verifiers
did refute individual **arguments** inside surviving findings, and those corrections are
recorded in place: the top-end half of F01, the censoring mechanism in F02 and F08, the
re-date discontinuity in F03, the "served below the consensus bar" lead in F05, the BLP tail
argument in F09, the learning-curve headline in F21, the causal story in F22, the corrected
E_refit proposal in F23, and the proposal to implement the narrow FV-45 correction in F17.

---

## 9. Open questions for the owner

1. **What does Appendix A of the epoch carry?** Recommendation: **F03 and F04 only**, each
   built as its own matrix arm inside the same rebuild (four matrices instead of two) so the
   cross-label matrix can attribute the WAR basis separately from the fixes. Everything else
   runs as its own lane on the finished frame. The alternative, an empty Appendix A, gives the
   cleanest attribution but pays the re-derivation twice.
2. **C-7: does level accuracy now outrank elite agreement?** (F02.) The measured trade is
   full-pool MAE -0.28 hit and -0.14 pit against agreement on 13 to 34 elite rows and a worse
   elite-pitcher bias. Default if unanswered: leave identity in place and ship the glossary
   correction only.
3. **What number does an abstention print?** (F19.) Recommendation: 35.0 rendered "at most 35"
   with an abstain basis. Default: keep 20.0 and disclose.
4. **The age ramp** (F11): measured serve rule, or a labelled policy indicator outside the
   grade? Default: run the gate first, decide after.
5. **The Statcast lean** (F30): displayed indicator, or in the grade with a restored ceiling?
6. **Grade rounding** (F43): one rule for both grades, or keep the ceiling and compute the chip
   on displayed values?
7. **The fabricated FV 35** (F32): keep it as the board-construction device, or serve an
   explicit ungraded state with the provisional grade as the sort key?
8. **Star odds** (F07 and F42): serve measured rates where n is sufficient, or keep the
   published table as the display?

---

## 10. Provenance

Thirteen census lanes, 115 candidate findings, deduplicated to 48; 30 verified by an
independent three-lens agent, 25 verifications completed. Every number in this document is
either cited to a file and line read during the audit or to an artifact key. Where the census
and the verifier disagreed, the verifier's measurement is what appears, and the correction is
named. Numbers describing the live board were read from artifacts regenerated 2026-09-03 and
will move with the next rebuild; the shape of every finding was checked against both the
current and the previous build where they differed.
