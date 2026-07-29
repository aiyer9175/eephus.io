# eFV Accuracy Frontier Audit (2026-07-24)

Answer to "anything else can we do to improve eFV?", produced by an 11-agent program
(2 foundation + 5 levers + 3 adversarial verifiers + synthesis) after six consecutive
honest no-ships. Every figure below is from a measured run; the two defects in section 1
were re-verified INDEPENDENTLY by the lead before being written down.

## The direct answer

**No remaining lever measurably improves eFV's rank accuracy, and the eval cannot certify
one if it existed.** What the program found instead is more useful: two real correctness
defects in shipped code, and a measurement instrument that has been calibrated wrong by
7-17x. None of the top findings is an accuracy claim.

The model itself is vindicated: with `fv` held intact and the entire non-fv feature block
row-permuted, the real model-vs-consensus gain sits outside the null on all four cuts at
p <= 0.003. **eFV earns its place; its composition does not move.**

## 1. Two confirmed defects in shipped code

### 1a. The grade-normalization layer is a near-identity (VERIFIED BY LEAD)

MLB Pipeline grades run materially hotter than the FanGraphs reference on the SAME players:

    paired same-player offset, MLB Pipeline minus FanGraphs
      hitters +4.390 FV pts (SE 0.128, n_pair 951)
      pitchers +4.343 FV pts (SE 0.122, n_pair 913)
      both     +4.367 FV pts (SE 0.089, n_pair 1,864)   ~49 sigma
    outcome-equivalence offset (FV implying equal expected 6yr WAR, same player set)
      hit +4.45 CI95 [+4.18,+4.70] ; pit +4.49 CI95 [+4.26,+4.73]
      WAR-per-FV slopes near-equal (FG 0.4204 vs MP 0.4499 hitters)
      -> a pure SCALE offset, not an information difference

Independent lead verification on the 2024 hitter cycle (n_pair 401): mean Pipeline 46.56 vs
FanGraphs 42.54 = **+4.01**, and `grade_normalization.quantile_map` returns
**40->40, 45->45, 55->55** (identity) with **50->45** as an inconsistent tie artifact.

Cause: `quantile_map` computes `q = np.interp(fv, src, linspace(0,1,len(src)))` on a
DISCRETE 5-point FV lattice. With ties, `np.interp` resolves to the upper edge of each
block, and mapping that quantile back through an equally-discrete reference returns the
same grade. The layer removes ~0.7% of a real 4-point bias.

**The fix is NOT the literal mid-rank remap.** A discrete mid-rank quantile collapses
distinct grades (45 and 40 land on the same output; 50->46.25, 55->50.5), destroys
injectivity, and turns the 22-block cross-split NEGATIVE (mean -0.0126, 10+/12-). The
correction must ship as a **continuous per-source offset** on the FV scale, gated on the
bias measurement (49 sigma) and NEVER on a downstream eFV rho (its downstream delta is
+0.0145 = 0.97x the evaluator's own MDE, i.e. unresolvable).

### 1b. The feature matrices violate their own as-of contract (VERIFIED BY LEAD)

`efv_dataset.py` documents "features built strictly as-of a pre-outcome decision point".
Counting `milb_season - asof_year` on the shipped matrices:

    hitters   delta 0: 360 rows, 344 of them BUSTS (95.6%);  delta > 0: 38 rows, up to +6 yrs
    pitchers  delta 0: 264 rows, 238 of them BUSTS (90.2%);  delta > 0: 36 rows
    unambiguous violations (future season, or a Jan/Feb as-of using that same year): 260
    verified examples: dashawn_keirsey_jr as-of 2019-07-31 carries milb_season 2023;
                       sandro_fabian as-of 2020-01-22 carries 2023;
                       lake_bachar as-of 2021-01-22 carries 2023

The structural problem is a KIND-DEPENDENT TIMING ASYMMETRY: the pipeline attaches a bust's
FINAL MiLB season (the year he washed out) but a debuted player's PRIOR completed season.
Debuted rows get delta -1 435 times vs delta 0 only 16 times; busts get delta 0 344 times vs
delta -1 only 17 times. **P(bust | delta = 0) = 95.6%** - row timing is a near-perfect label
proxy, so features drawn from that timing carry the label.

Scrub test (set `milb=None` wherever `milb_season >= asof_year`, refit, B=300 paired
bootstrap) cuts the program's only two surviving positive claims:

    hit drop:fv                        +0.0443 (P=0.960) -> +0.0356 (P=0.927)   -20%
    pit production block               +0.0286 (P=0.893) -> +0.0162 (P=0.727)   -43%

**Expect measured OOS to go DOWN when this is repaired. The current headline numbers are
partly artifact.** That is a true-to-model win, not a regression.

## 2. The measurement verdict

Minimum detectable effect (paired refit bootstrap, train AND test resampled, production fit
config), by statistic class:

| statistic class | MDE95 |
|---|---|
| model vs consensus, pooled rho | ~0.045 (all four cuts) |
| incremental feature add, pooled rho | ~0.017 hit / ~0.016 pit |
| lambda shift | 0.0076-0.011 hit / 0.005-0.008 pit |
| FV-45 fringe t45 | ~0.055 hit / ~0.10 pit |
| recommended evaluator, block-rho | 0.0149 |

**The registered noise floor was wrong by 7-17x.** `docs/efv-2026-07-*/GATES.md` used an
identity-variant refit movement of 0.0011-0.0023 (and a ship bar of +0.0046). That measures
NUMERICAL perturbation of one fixed dataset, not SAMPLING variability. The correct
pairing-preserving control (zero-information placebo columns) reaches p95 0.0031-0.0073
pooled and 0.0106-0.0538 t45.

Consequently essentially every eFV decision since 2026-06-22 sits inside its own floor:

| decision | claim | floor | ratio |
|---|---|---|---|
| A1 blend-lambda 0.70 -> 0.85 | +0.0048 pooled | 0.0076 | 0.63x |
| ops_rel (M5 fringe) | t45 +0.0237 | 0.058 | 0.41x |
| level_rank (LR-FRINGE) | t45 +0.0192 | 0.053 | 0.36x, BELOW its own placebo p95 (+0.0256) |
| age (hit / pit) | +0.0019 / +0.0028 | 0.017 | 0.11x / 0.17x |
| x_era_k (pit) | +0.0074 | 0.016 | 0.46x; cross-split mean -0.0094, 9 of 11 folds NEGATIVE |
| n_milb_seasons | +0.010 | 0.0154 | 0.65x |
| cohort indicators | +0.005 | 0.021 | 0.23x |
| consensus source-reweight | +0.0011 | - | cross-split +0.0008 se 0.0036, t=0.22 |

The REJECTIONS were equally unresolvable (E-LEAN1 rejected 9 arms at +0.0003/+0.0008 against
a 0.015-0.019 floor), so this is not a one-directional bias. Two past calls look BETTER by
this floor: the E-LAMBDA cap-raise retraction was correct, and S-XLINE holds up.

**This is an audit, not a blame exercise.** The decisions were made in good faith against a
floor that looked principled; it simply measured the wrong quantity.

## 3. Lever results (all five)

| lane | verdict | detail |
|---|---|---|
| feature ablation | DIAGNOSTIC | Of 22 shipped features exactly ONE is individually resolvable (hitter `fv`). Four are point-negative. But pruning is out-of-fold NEGATIVE at every depth (-0.0137 hit / -0.0159 pit), so **do not prune** - the lean sets are already about right and the eval cannot adjudicate composition. |
| pool both sides | NULL | Premise was wrong: the ridge already trains on n=3,370 pooled rows (353/438 are TEST counts, not train). Cross-side sharing helps only below 40-60% of current data and harms at full data (-0.0045). Pooling buys ZERO measurement precision (SNR flat 0.92 vs 0.95). Pool the EVALUATOR, not the model. |
| regularization / ensembling | NULL | Alpha curve flat across three orders of magnitude (0.1-100 spans 0.0004 vs a 0.0025 null band); per-row shrinkage wrong-signed; ensembling costs rank AND raises churn. One usable result: lowering blend lambda is the only lever that reduces served-grade churn. |
| consensus anchor | DIAGNOSTIC | See 1a. |
| surplus chain | DIAGNOSTIC | See 4. |

## 4. Surplus findings (the owner's stated focus)

Dollar error decomposes as **58% ranking / 16% level-given-perfect-information / 26% pricing
floor** (n=2,236 resolved listings, player-clustered bootstrap B=2000):

    incumbent board                                 MAE $13.473M
    perfect ranking, same served FV multiset        MAE  $5.677M  -> ranking headroom $7.796M
    perfect 6yr-WAR foresight, grade unconstrained  MAE  $3.558M  -> level/constraint $2.119M

Two structural findings clear their nulls decisively:
1. **Served eFV surplus is a function of RANK ONLY.** A monotone rescale of `rank_war` moves
   served grades by exactly 0.000000; the display quantile map re-inflates model WAR by +37%
   (hit) / +85% (pit) before pricing. So level-accuracy work cannot move served surplus.
2. **The FV->WAR anchor over-predicts at every tier by design** (FV45: 1.86 shipped vs 0.70
   realized, n=679, CI95 [+0.94,+1.37], P=1.000), because
   `anchor_calibration.blend_weight_public = 0.5` blends realized value 50/50 into an
   optimistic public table.

**DO NOT ship `blend_weight_public` 0.5 -> 0.0**: it is MAE-neutral but collapses served
surplus 96-99% for the 77% of the board at FV40-45. MAE is structurally blind to that.

Usable deliverable: a **gate currency** - +0.01 pooled eFV Spearman is worth **-$0.0704M**
surplus MAE per prospect, CI95 [-0.0878,-0.0550], P=1.000. That converts every future rank
claim into dollars.

## 5. What to do (ranked, none of the top three is an accuracy claim)

1. **Repair the as-of contract** (1b). Validity, not accuracy. Attach the prior completed
   MiLB season for bust rows the same way debuted rows already do. Headline OOS will FALL.
2. **Repair the grade-normalization offset** (1a) as a continuous per-source offset, gated
   on the 49-sigma bias measurement, never on a downstream rho.
3. **Adopt the two-metric gate + the corrected floor.** Full-pool discrimination AUC reads
   SNR 6.25 / 4.08 against block-rho's 1.72 / 1.25 on the two candidates known to be real,
   and it survives leak-scrubbing where block-rho does not. Worth more than any feature ever
   tested. Register the corrected MDEs above in the GATES docs.
4. **Churn reduction**: hit lambda 0.85 -> 0.70 cuts served-grade churn 6.0% at rho -0.00049
   (CI95 [-0.0045,+0.0070]) - a non-inferiority product trade, with a one-time transition cost.
5. **Determinism hygiene**: 5-fold CV alpha selector; served numbers unchanged (alpha=100
   both sides at production n). Free.

**Do not ship:** `blend_weight_public` 0.5->0.0; the deep lambda cut (pit 0.37 is outside the
hard-coded 0.50-0.70 re-derivation band); the literal `quantile_map` mid-rank edit.

**Stop re-tilling:** feature composition changes, side-pooling of the model, alpha/shrinkage
tuning, ensembling, and any lane whose expected effect is under ~0.015 pooled rho - the gate
cannot see it, so the result will be noise in whichever direction the sample happens to fall.

## 6. EXECUTED (2026-07-24, owner authorized all five)

| # | change | file | measured effect |
|---|---|---|---|
| 1 | as-of contract repair | `efv_dataset.py` | debuted cuts EXACTLY unchanged; full-pool hit +0.0012 / pit -0.0041 (inside floor) |
| 2 | grade-norm continuous offset | `grade_normalization.py` | removes the measured ~4 FV Pipeline offset; propagates on the next pipeline run |
| 3 | gate standard + corrected floors | `docs/EFV_GATE_STANDARD.md` | documentation; supersedes the old identity floor |
| 4 | hit blend lambda 0.85 -> 0.70 | `efv_model.py` | rho -0.0043 (inside the 0.0076 floor); MAE better on all three cuts; -6.0% served-grade churn |
| 5 | 5-fold CV alpha selector | `prospect_path.py` | hit -0.0004 / pit +0.0026 (inside floor); removes selector chatter |

**Item 1 detail.** The repair is strictly subtractive (`min()` against the old bound), so it
touched ONLY the 582 contaminated bust rows (344 hit / 238 pit) and left every debuted row
byte-identical. Remaining as-of violations: **0** on both sides. Coverage 904 -> 884 (hit) and
914 -> 895 (pit); most contaminated rows fell back to an earlier LEGITIMATE season rather than
losing features. NOTE, correcting an over-claim in the source verification: the leakage was
NOT materially inflating the shipped headline numbers (the debuted cuts contain no bust rows,
so they did not move at all). The verifier's "-20% / -43%" came from a harsher scrub (nuking
MiLB features entirely) under a different evaluator.

**Item 2 detail.** The fix is a continuous per-source offset (`fv - (mean_src - mean_ref)` on
the paired same-player distribution, clamped to 20-80), NOT the discrete mid-rank remap that
was tested and rejected. Verified live: Pipeline 2024 hitters map 40->35.99, 45->40.99,
55->50.99 against a measured +4.01 offset; strictly order-preserving; FanGraphs still maps to
itself. All 11 `test_grade_normalization.py` tests pass. The served effect appears when
consensus is rebuilt on the next pipeline run.

**Test repair (incidental, real).** Three `test_efv_model.py` lambda tests were ALREADY
FAILING before this work: `_BLEND_LAMBDA_RESELECT` short-circuits the WAG/rank/fallback ladder,
so `fresh_lambda_cache` could not make `blend_lambda` recompute and the ladder tests were
silently testing nothing from the moment the A1 re-select shipped a hit override.
`test_hard_fallback_on_error` passed only because that override coincidentally equalled the
fallback constant. The fixture now clears the override, and two new tests pin the override
mechanism itself and the fact that the lambda constant is a churn trade inside its own floor.
eFV-related suite: **231 passed, 1 failed** - the `xfv_golden_fingerprint`, which was verified
to be failing BEFORE any change here (served numbers moved earlier the same day). It needs the
usual restamp on the deploy box.
