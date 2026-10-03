# eFV v2 model-class screen: the pre-declaration (MODEL_CLASS_SCREEN)

Pre-declared 2026-10-02 (task EFV3_C01_MODEL_CLASS_PREDECLARE) on the code at 8318051d, branch
`efv-conviction-2026-08-08`, and committed ALONE before any screen runs. It fixes ONE
development screen of five model-class arms against the assembled Driver System V2 base: the
arms, the frames, the statistic, the controls, the admission rule, the forking-path count and
the timing. Sources: section 5 'The model class candidates, and the scrap-or-rebuild answer' of
`_finalpass_2026-09-24/efv3/EFV3_PLAN.md` and sections 2 and 4 of `LANE_C.md` beside it.

This document is not the gate. `docs/efv-v2/EFV_V2_GATE.md` stays DRAFT and is the only file
whose status line opens a reserved frame; nothing here opens one, admits a candidate, moves a
served number or writes a ledger row. An arm the screen admits reaches the gate only through
the amendment EFV3_C04 (labelled secondaries in a new s4.7) before EV-12. No frame was scored
in writing this. No statistic here, in the screen's code or in its artifact is cut by
consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`). No em-dashes.

---

## 0. Preamble: the scrap-or-rebuild answer (owner message 2 of 2026-10-02)

Owner, message 2 (2026-10-02, verbatim): "It doesn't make sense that eFV isn't beating
consensus when it was specifically designed to beat consensus. If needed, we can scrap the
current model and build from scratch, either by re-deriving all of our drivers with our now
improved dataset and database or by moving away from the driver system entirely in pursuit of
something better (or a blend? drivers + something else? figure it out)"

Owner answer E3-Q1 (Scrap/keep), recorded 2026-10-02 in `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`
under 'ANSWERED 2026-10-02 (standing instruction), eFV frontier v3': **C. Keep V2 as the one
primary, re-derive it at P5, enter the rest as labelled secondaries** (the recommended option,
accepted under the owner's standing instruction of 2026-10-01).

### 0.1 The answer, verbatim (EFV3_PLAN.md s5.1; "section" inside the quote means a section of EFV3_PLAN.md)

> Recommendation: **(c), in this exact form.** Keep Driver System V2 as the ONE registered primary and
> re-derive it on the improved dataset (the identity repairs of section 3, the lifted MiLB floor, the
> fWAR label after the epoch, the bust pool behind its flag; the re-derivation is the gate's own P5
> step and happens once on the frozen label). Enter "something else" through two pre-declared screens
> as LABELLED SECONDARIES read beside V2 on the same reserved frames with no ship weight: the
> reliability-weighted anchor (MC-2, the only admissible form of a per-source stacked ensemble), the
> model-class arms of section 5.2, and whatever the screening lab admits (the text family is the one
> new information source). Replace nothing before a reserved read. If V2 reads BEHIND consensus on
> R-LV by a resolvable margin at the 2026-12 read, the class is redone for the 2027 registration
> cycle, which is what the owner's 2026-09-24 instruction already says.
>
> Stated plainly, because it governs what "re-derive" means: V2 IS the served eFV today
> (`efv_v2_serve.SERVE_EFV_V2 = True`, line 92; `production_models()`, lines 147 to 166, fits
> `fit_v2` through `_skill_fit` and `_timing_fit` with `load_weights()` from
> `data/efv_v2_assembly.json`). So the P5 re-derivation on the frozen label rewrites the weights the
> served fit loads and is itself a served-grade move; it is governed by the fWAR epoch gate (the
> step Z restamp under clause (l), `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`), not by this
> plan, and no task here runs it (C03 stops with a BLOCKER if the epoch has not recorded it). The
> same holds for any change to `_skill_fit` or `_timing_fit`: MC-4a is coded behind
> `V2_SIGN_CONSTRAINED = False`, the served fit byte-identical with the flag off, the look runner
> reading both, and the flag flips only after a registered look passes, through EV-15.
>
> Why not (a) alone (re-derive every driver, keep the class): it is the P5 step and is in the plan,
> but it cannot move the margin by itself. The admitted drivers carry a partial correlation of 0.076
> with the outcome given consensus; re-deriving them on more rows tightens their slopes, it does not
> add information. Expected gain of (a) over V2 as drafted: 0 to +0.003.
>
> Why not (b) (replace the driver system): every version on record lost. LightGBM lambdarank over
> all vintage-matched inputs with consensus as an input: hit -0.027, pit -0.021 (`data/
> xfv_model_class_sweep_eval.json`); ridge on a rank target below base; rank-space stacks of sources
> and model vm -0.006 to -0.015, lv -0.004 to -0.007; learned source weights +0.0047 pooled, ship
> false; hierarchical per-cohort weights NO SHIP (5 of 6 conditions failed); per-row credibility
> weights -0.004 vs flat; hurdle product below v1 on both frames; monotone GBM hit -0.0355 / pit
> +0.0081, all four cells NULL. The combination bound (+0.0085 on the debut frame; a +0.0073 lead
> needs about 14,000 rows to resolve) says that no estimator over the same inputs can reach +0.03. A
> "from scratch" rebuild on the spent frames would also be the 39-arm frontier run again under a new
> name, which the do-not-reopen list bans. Expected gain of (b): -0.02 to +0.005, with the largest
> forking-path cost of any option.
>
> What (c) adds over (a): the anchor arm (+0.005 to +0.015 vs served consensus on R-LV, about 0 vs
> Pipeline), the text family (0 to +0.010), and a registered answer to "why not a ranking loss" (MC-1,
> expected 0.000). Cost: 5 model-class arms (10 frame reads) plus 7 screening arms with their noise
> floors, one pre-declaration document, one candidate module, and two registered runs on the frozen
> label before EV-12. Leakage guards: every arm is admitted-drivers-only, fit within (side, vintage),
> reliabilities from vintages at most V - 3, no FV cell, no reserved row, the AST import bans. How it
> enters the gate: as labelled secondaries in a new s4.7 (EFV3_C04) and the screening s10 (EFV3_B6),
> both amendments to the DRAFT before the status line changes; the primary stays m 1 per frame.
>
> (d), the design the lanes found better than any class change: more information on more rows, scored
> where consensus is weakest. Concretely, the F-LV list-vintage frame (consensus rho 0.16 to 0.19
> against 0.41 at debut) is where new columns can show, the headline vm frame is where they cannot, and
> the three things with room above +0.01 are report text now, the anchor as a secondary now, and
> physical data through the surrogate chain from 2027. That is the whole of this plan.

### 0.2 The three numbers (EFV3_PLAN.md s1.3 item 2, verbatim)

> **The drivers carry almost nothing consensus has not priced.** eFV correlates 0.9175 with
> consensus; its partial correlation with the outcome given consensus is 0.076 (E1,
> `DRIVER_SYSTEM_V2.md` s1). The best linear combination of eFV v1 and consensus on the debut
> frame reads 0.4219 against consensus 0.4134, +0.0085 (`scratchpad/efv2/E3_model_class/
> probe_ceiling_power.json`), and a new component would need validity 0.436 at r 0.85 with
> consensus (0.404 at r 0.70) to lift by +0.03. The information set, not the estimator, is the
> bound.

### 0.3 The record of every replacement class that lost (LANE_C.md s1.2, verbatim)

| family | record | artifact |
|---|---|---|
| Learning-to-rank (LightGBM lambdarank), standalone, pooled statistic, 4 folds | hit 0.3492 vs base 0.3761 (-0.027); pit 0.2824 vs 0.3032 (-0.021) | `data/xfv_model_class_sweep_eval.json` variants hit_lgbm_rank, pit_lgbm_rank |
| Ridge on a rank target | hit 0.3442, pit 0.2808, both below base | same, hit_target_rank, pit_target_rank |
| Rank-space targets and weights (I1, I3) | fold-mean delta -0.0230 to +0.0006, 0 to 6 of 11 fold wins | `data/xfv_rank_objective_eval.json` rank.cells (per MODEL_CLASS.md s2) |
| Rank target in the V2 lanes | -0.0116 (lane I3) | DRIVER_SYSTEM_V2.md s3 "measured and closed" |
| Monotone LightGBM, 11-fold; mean(ridge, mono) | hit -0.0355 / pit +0.0081; mean pit +0.0186 (Holm no); all four cells NULL, model class CLOSED on that label | `data/xfv_model_class_readjudication_eval.json` verdict |
| Learned source weights (two-source A/B, forward-chained, k 150 shrink) | weighted 0.2775 vs equal 0.2728 pooled (+0.0047), AUC +0.0057; ship false (needs +0.0068 rho and +0.0052 AUC) | `data/consensus_weight_eval.json` pooled, notes |
| Archetype-shrunk weights | d_rho -0.00455 | same, cohort_ab.arms.archetype_shrunk |
| Rank-space stacks (sources, sources + model, regime stacks) | vm -0.006 to -0.015; lv -0.004 to -0.007; FG-gap regime vm +0.0008 | DRIVER_SYSTEM_V2.md s3 closed list; I5 IDEAS.md s5 |
| Pipeline alone vs consensus within (V, side) | +0.018 (CI95 +0.006 to +0.032, I4), n 5,646; raw pooled +0.017 (CI95 +0.004 to +0.029); -0.008 pooled after the map (CI95 -0.023 to +0.011) | DRIVER_SYSTEM_V2.md s2 (S1) |
| Credibility (per-level) weights vs a flat weight | A_fix minus A_flat vm -0.0041, lv -0.0041 raw, -0.0074 (CI95 -0.0146 to 0.0000) within | I5 IDEAS.md s3 |
| Hierarchical per-cohort lambda | NO SHIP, 5 of 6 conditions failed | `data/xfv_cohort_lambda_hier_eval.json` |
| Low constant weight (0.28 hit / 0.22 pit) vs v1's 0.70 / 0.57, with the within map | lv +0.0075 (CI95 -0.0035 to +0.0194); vm -0.0008; inside groups on vm +0.011 over v1 (CI95 +0.0017 to +0.0198) | I5 IDEAS.md s2 |
| Context corrections to consensus by position, age, age-for-level, route, org | position -0.0317, age -0.0105, age-for-level -0.0083, route -0.0388, org -0.0525; every sign flips between vintages | DRIVER_SYSTEM_V2.md s3 closed list (lane I1) |
| Reach-conditional heads; hurdle product (H0) | vm -0.028, lv -0.026; H0 below v1 on both frames | I5 IDEAS.md s6; STATUS.md |
| Combination bound on F-VM | best linear combination of eFV v1 and consensus 0.4219 vs 0.4134 (+0.0085); a new component needs validity 0.436 at r 0.85 with consensus, 0.404 at r 0.70, to lift by +0.03 | `scratchpad/efv2/E3_model_class/probe_ceiling_power.json` |
| Stacking resolvability | a +0.0073 lead needs about 14,000 identical rows | same, n_needed_for_mde95 |

Paths named `scratchpad/...` and the lane files (I1 to I5, MODEL_CLASS.md) are the planning
lanes' records under `_finalpass_2026-09-24/efv3/` and the session scratchpad; they are not
tracked in this repository. Every `data/` and `docs/` path is.

---

## 1. The screen at a glance (EFV3_PLAN.md s5.2)

| arm | family | definition (s2 below is the exact text) | expected vs V2, F-LV | F-VM | route |
|---|---|---|---|---|---|
| MC-1 | ranking loss | Bradley-Terry residual skill head within (side, vintage), pairs weighted by outcome distance, L2 on V2_ALPHAS, admitted drivers only, listwise weighting as a sensitivity | 0.000 (-0.005 to +0.005) | 0.000 | screen; secondary if admitted (lane C E3-Q4 default: screen once) |
| MC-2 | stacking | reliability-weighted anchor u_c*: weighted mean of in-window sources' within percentiles, weights from each source's within-W3 Spearman at vintages at most V - 3, k 150 shrink, clamp (0.6, 1.5), single-source rule unchanged, comparator stays served consensus | +0.005 to +0.015 vs consensus; 0 to +0.005 vs Pipeline | about 0 | labelled secondary on both reserved frames (owner answer E3-Q4) |
| MC-3 | per-level | two-band DS-08 weight (AA or AAA vs A+ or below or no block; no-block rows take the lower band), rule years to 2016, clip [0, 1] | 0 to +0.004 | about 0 | screen; secondary at most |
| MC-4a | monotone | sign-constrained ridge (active-set refit) | 0.000 to +0.002 | same | adoptable on non-inferiority, no margin claim (lane C E3-Q3 default A), behind `V2_SIGN_CONSTRAINED = False` |
| MC-4b | monotone | 3-knot monotone I-spline residual per admitted driver, fallback to MC-4a under 300 has-block rows | -0.003 to +0.004 | -0.003 to +0.002 | screen; secondary at most |
| MC-5 | calibration | pricing line with position-family and age-at-read covariates; order_idx bit-identical (test) | 0 exactly | 0 exactly | pricing item (EV-15), MAE row only, OUTSIDE the family |

The five arms of the family are **MC-1, MC-2, MC-3, MC-4a, MC-4b**. MC-5 is listed for the
record as a pricing item; it is not an arm of the family, takes no Holm slot and has no
admission leg. The arms are not additive: MC-2 changes the anchor the others ride on, and
MC-1, MC-3 and MC-4 compete for the same 1 to 5 driver columns. Every arm is a different object
from the closed record of s0.3 (a residual to u_c, within (side, vintage), admitted drivers
only), screened once on the frozen label.

---

## 2. The arms, exact definitions

The base every arm is compared with is **V2 as assembled, at the DS-08 weights, re-derived on the
frozen fWAR label** (the gate's P5 step, run by the epoch, not by this screen). V2's class for
reference (LANE_C.md s1.1, function names at 8318051d in `efv_v2_model.py`):

    u_c       = within-(s, V) percentile of consensus FV                 (within_pct)
    e_skill   = skill head driver sum / its own consensus slope           (e_skill)
    e_time    = timing head logit driver sum / its own logit slope        (e_time)
    order_idx = u_c + w_skill * e_skill + w_time * e_time                 (predict_v2)
    grade     = output_map(order_idx, groups, consensus values)
    efv_war   = fit_war_map line in the grade, pricing only

The skill head is a weighted ridge of the within-year target percentile u_y on [1, u_c, z(x)]
over has-block rows, intercept and u_c unpenalized (`_skill_fit`); the timing head is a
penalized logistic of REACHED on the same design over every row (`_timing_fit`); penalties by
nested forward-chained CV over `V2_ALPHAS` (1, 3, 10, 30, 100, 300, 1000, infinity); drivers
enter only through the DS-06 admission rule (`admission_check`); weights by the DS-08 combiner
rule (`combiner_rule`). Everything an arm does not name below is V2's, unchanged.

### MC-1, pairwise (Bradley-Terry) residual skill head (ranking loss)

A pairwise logistic (Bradley-Terry) residual head in place of the skill head's squared-error
fit: for every pair (i, j) inside one training (side, vintage) group with u_y_i > u_y_j, the
loss is log(1 + exp(-(s_i - s_j))) with s = b_uc * u_c + z(x) @ beta, b_uc free and beta
L2-penalized on the same grid (`V2_ALPHAS`), pairs weighted by |u_y_i - u_y_j| so that ties at
W3 = 0 (the bulk of every list-vintage group) contribute nothing and the far pairs contribute
most. Linear in the admitted drivers only (the DS-06 rule unchanged), has-block rows only,
Newton from zero (deterministic), the same nested forward-chained penalty choice. The order
index is unchanged in form: u_c + w_skill * (driver sum / b_uc). The listwise form (a
Plackett-Luce likelihood on the group) is the same model with a different pair weighting and
is NOT a separate arm: one arm, the pairwise form, with the listwise weighting recorded as a
sensitivity (printed beside the arm, selected nowhere, outside the Holm family).

Guards: pairs formed only inside one training group (never across vintages, never across
sides); the fold's test players left out of training as V2 does; the module imports no label
module (AST test, as `efv_drivers` has); a reversed-target fit must flip every slope (test);
the penalty grid and the pair weighting are the ones above, fixed now; one arm, one read per
frame. Expected gain 0.000 within on both frames, range -0.005 to +0.005.

### MC-2, reliability-weighted anchor (stacking)

u_c is replaced by u_c* = the weighted mean of each in-window source's within-(side, V)
percentile, weights r_source(s, V) from the within-W3 Spearman of that source on list vintages
at most V - 3 (the `consensus_weight_eval` vintage rule, "weights for board-year Y use base
years <= Y - 3 only"), shrunk toward equal with the shipped k 150 pseudo-n and clamped to
(0.6, 1.5) (`data/consensus_weight_eval.json` notes: "weights shrunk toward equal with k=150
pseudo-n, clamped (0.6, 1.5)"), with the served single-source rule applied unchanged (a
one-source row is that source's shrunk value, as `consensus.compute_consensus_point` does
today). The drivers, the heads, the admission rule and the combiner weights are V2's. The
comparator stays served PROSPX consensus (owner DS-Q4 = A). Stacking the MODEL leg with
sources (I5 structure c) is NOT in this arm: it read -0.0105 on vm and needs about 14,000 rows.

Design rule (the "WAG is three metrics" lesson): every source is first placed on ONE baseline,
its within-(side, V) percentile over its own rows; every reliability is measured by ONE rule
on ONE statistic (the within statistic) and ONE label (W3 on list vintages, career WAR on the
debut frame), forward-chained; the arm's output is a percentile, which `output_map` turns into
a grade.

Guards: reliabilities from list vintages at most V - 3 only (test: the weight table for V
reads no row at or after V - 2); a source absent on a row contributes no weight and no
indicator (source presence is an outcome proxy on list vintages, bug B4's cousin); the
single-source rule unchanged so the arm is "weights only"; no FV-cell cut anywhere (the
weights are per source, side and vintage); the weight rule is fixed here and not tuned.

Disclosures carried into any registration: the arm was designed after reconciliation S1 was
seen, so its development read on V 2017 to 2019 is not evidence; only R-LV is. MLB Pipeline's
+0.018 within lead over consensus (CI95 +0.006 to +0.032, n 5,646, V 2011 to 2019, I4) reads
-0.008 pooled after the map (CI95 -0.023 to +0.011, S1); the pooled secondary will show that.
The arm cannot beat Pipeline on list vintages by construction, because its anchor converges to
Pipeline where Pipeline is the reliable source. Expected +0.005 to +0.015 within on F-LV
against served consensus, 0 to +0.005 against Pipeline, about 0 on F-VM.

### MC-3, two-band weight (per level)

w_skill and w_time fixed by the DS-08 rule run separately on the upper band (last level AA or
AAA at the read) and the lower band (A+ or below, or no block), rule years up to 2016 as today,
both bands clipped to [0, 1]. A no-block row takes the lower band's weight, never a third
value, so block absence carries no weight signal (B3). Everything else is V2.

Guards: band from the as-of MiLB block (through V - 1) only; the rule reads no row after 2016
(the existing row-set assertion); the band's weight table written to the screen's artifact
before any scored read; one boundary (AA or above), fixed now and never re-shopped. Disclosed:
the split was seen on development frames (I5 level index), so a development win is not
creditable. Expected 0 to +0.004 within on lv_dev, about 0 on vm2.

### MC-4a, sign-constrained ridge (monotone)

The same ridge with each admitted driver's slope constrained to its admitted sign, a
bound-constrained least squares solved by the active-set rule: fit, zero every slope with the
wrong sign, refit on the rest, repeat; deterministic. The skill head and the timing head both
take the constraint. The sign is the one the DS-06 admission returns on the fold's training
vintages only; on the vm frame, whose folds store no admitted sign in
`data/efv_v2_assembly.json`, it is the sign `admission_check` returns at fit time.

Guards: sign from admission on training vintages only; the test asserts no fitted slope
opposes its admitted sign. In code the arm sits behind `V2_SIGN_CONSTRAINED = False` in
`efv_v2_model.py`: with the flag off the served fit and `data/efv_v2_assembly.json` are
byte-identical to the unconstrained V2 (test-pinned); the screen and, later, the look runner
read the constrained fit with the flag on in-process; the flag flips only after a registered
look passes, through EV-15. Expected 0.000 to +0.002 within; a variance guard, not a lever.

### MC-4b, monotone 3-knot I-spline residual (monotone)

Each admitted driver enters as a 3-knot monotone I-spline with the admitted direction, knots
at the training terciles of that driver, the same ridge penalty; linear in the basis so Newton
and nested CV are unchanged. MC-4b is screened only on folds with at least 300 has-block
training rows; on a fold under 300 it falls back to MC-4a, and the artifact says which folds
fell back.

Guards: knots from training rows only; the test asserts each spline basis is non-decreasing in
the admitted direction. Expected -0.003 to +0.004 within on F-LV, -0.003 to +0.002 on F-VM.

### MC-5, pricing calibration by position and age (outside the family)

`fit_war_map` gains position-family dummies (C, SS and CF against 1B, LF, RF and DH; a
continuous dummy set on the line, never a table by grade) and age-at-read (hitters) or role
(SP vs RP tool_fb shape, pitchers) as continuous covariates of the WAR line. Position at the
read is the in-window listed position, never the served current one. Scored by MAE and by
calibration-in-the-large per position family on the development frames; an MAE row only,
labelled "pricing, no rank claim". The order index is untouched: a test asserts order_idx is
bit-identical with and without the term, so its Spearman and AUC deltas are 0 exactly. The
served price moves only through EV-15 after the reserved reads and the anchor look
(EFV3_C05 builds it).

---

## 3. Frames and guards

- **lv_dev**: F-LV at list vintages 2017 to 2019 (W3 label, outcome-blind identity ids,
  `reserved_vm` rows kept at W3 = 0 per `EFV_V2_GATE.md` s5 B9b, their count printed). Fold V
  fit on labelled F-LV rows at vintages before V with every player in the V frame left out
  (`v2_lv_scores`).
- **vm_dev** at frame version **vm2**: debut years 2017 to 2023, outcome career WAR to date,
  timing-pinned inputs. Fold y fit on matrix rows at decision years before y (`v2_vm_scores`).
- Guards asserted before any score (`tools/efv_v2_dev_read.py` `_ds16_guards`): no list
  vintage above 2019 or in `RESERVED_LV`, no vm base year or debut year at or after 2025,
  `reserved_vm_pins()` empty, the combiner rule's years below the first scored year. A guard
  failure ends the run with nothing scored.
- The frames are spent: the screen adjudicates the arms against V2 only, as development rows;
  it makes no claim against any source.

## 4. Statistic, intervals, comparisons

- Primary: `efv_v2_stat.within`, the size-weighted mean over (side, vintage) groups of at
  least `MIN_GROUP_ROWS` (20) rows of the Spearman rho of each rater's OWN score against the
  outcome. Secondary: `pooled`, Spearman after `efv_v2_model.output_map` (each rater's order
  inside a group placed onto the group's consensus values). Contributor AUC of the mapped
  score: veto only.
- Intervals: `efv_v2_stat.paired_delta` on identical rows, paired, player-clustered bootstrap,
  B 2000, seed 20260906, E_cond (scores fixed, players resampled).
- Comparisons per arm, per frame: arm minus V2 base (the admission leg); arm minus PROSPX
  consensus (the ledger row); arm minus MLB Pipeline and arm minus FanGraphs (descriptive,
  each on the rows that source grades).

## 5. Controls

- **Zero-information twin**, one per arm: the arm's non-consensus columns permuted within
  vintage (the driver columns for MC-1, MC-4a and MC-4b; the band assignment for MC-3; the
  source reliability weights, exchanged across sources within (side, V), for MC-2), refit and
  scored exactly as the arm. An arm whose twin reaches its delta over V2 has no result.
- **Per-fold signs**: the arm-minus-V2 within delta on each of the 3 lv folds and each of the
  7 vm debut years, published.
- **Permutation null**: 500 draws on the within statistic (the outcome permuted inside each
  (side, vintage) group, seed 20260906, the arm-minus-V2 delta recomputed per draw), its
  95th percentile printed beside the observed delta.
- **mde95**: 1.645 x the SD of the arm-minus-V2 paired draws, stated from this screen's own
  draws (the arms share V2's u_c, so the paired SD is expected below the DS-16 floors of 0.0155
  lv and 0.0146 vm, which were against consensus).

## 6. Admission rule (fixed now, before any read)

An arm enters `EFV_V2_GATE.md` as a labelled SECONDARY (no ship weight, through EFV3_C04) only
if ALL hold:

1. its within delta over V2 is at least +0.005 on BOTH frames;
2. the delta has the same sign in at least 2 of 3 lv folds and 5 of 7 vm years;
3. its lower CI95 bound against V2 is above -0.005 on both frames (non-inferiority);
4. its twin's delta over V2 is below the arm's on both frames;
5. the AUC veto does not fire (the arm-minus-V2 contributor AUC delta is not below minus its
   own mde95 on either frame, PROGRAM.md s4 item 6 "adverse beyond its floor");
6. it survives Holm with m = 5 across MC-1, MC-2, MC-3, MC-4a, MC-4b on the vs-V2 within leg,
   one-sided family alpha 0.05, each arm's p being the larger of its two frames' bootstrap
   shares of draws at or below zero (1 - `p_gt_0`), because admission needs both frames.

MC-4a is marked ADOPTABLE on non-inferiority alone (item 3 on both frames, no veto) under
lane C E3-Q3 = A, with no margin claim; adoptable means coded behind `V2_SIGN_CONSTRAINED =
False`, read beside V2 by the look runner, the flag staying off until a registered look
passes (V2 is the served eFV, `efv_v2_serve.SERVE_EFV_V2 = True`), flipped only through EV-15.

An arm that fails is recorded null in `data/xfv_arm_ledger.json` and never re-run on these
frames. With five null arms at the E_cond floor the expected maximum point delta is about
+0.011 within, which is why no arm is admitted on a point estimate alone; at nominal 5
percent, 0.25 spurious CI-excluding reads are expected from the screen.

The rank-consistent combiner weight (lane C E3-Q2 = A) is NOT an arm: a sensitivity reported
beside V2 at the DS-08 weights (w chosen on the same rule rows, years up to 2016, by maximizing
the within-(side, year) Spearman of u_c + w * e over the grid {0, 0.1, ..., 1.0}, ties to the
smaller w), selected nowhere, outside the Holm family, logged under its own name.

## 7. The forking-path count it adds

5 arms (MC-1, MC-2, MC-3, MC-4a, MC-4b) and 10 frame reads (each arm on lv_dev and vm2), on
top of the denominator in `EFV_V2_GATE.md` s6. MC-5 adds an MAE row only. EFV3_C04 writes the
count into s6 when it amends the gate.

## 8. Timing and the run

- ONE run, on the frozen fWAR label, after EPOCH_RUN and Z1_RUN and before EFV_V2_EV12 (task
  EFV3_C03, which also requires EFV3_C01, EFV3_C02, EFV3_A2 and EFV3_B3, and stops with a
  BLOCKER until the epoch has recorded the P5 re-derivation of `data/efv_v2_assembly.json`).
  Never on 2026-10-23, 2026-11-06, 2026-11-13, 2026-11-20 or 2026-12-01, nor on any other
  registered look's date (`docs/*GATE*.md`).
- `tools/efv_v2_model_class_screen.py` (EFV3_C03), one process, one session, no other lab.
  Outputs `data/efv_v2_model_class_screen.json`; development rows in `data/efv_progress.json`
  (model `efv_v2_mc_<arm>`, role development, resolvable none, note "model-class screen, spent
  frame, not a claim"); ten probes in `data/xfv_arm_ledger.json`; a dated section in
  `docs/efv-v2/STATUS.md`; a Source Comparison row per arm through the existing ledger render
  (the matrix shows them under "development frame").
- An exploratory run on the eWAR v2 label is allowed only as a smoke test of the code on
  synthetic rows, never on a frame.
- The outcome feeds EFV3_C04: admitted arms are written into `EFV_V2_GATE.md` s4 as labelled
  secondaries, s6's forking count is updated, pins re-taken, and `tools/efv_v2_look.py`
  reports the secondaries beside the primary on every reserved cell. The primary stays m = 1
  per frame. Under owner answer E3-Q3 (Admit window) EV-12 waits for this run with a hard
  cutoff of 2026-11-15; an arm admitted after it waits for the 2027 registration.

## 9. Owner answers this screen runs under

Unified questions (`SP/efv3/OWNER_QUESTIONS.json`), answered 2026-10-02 under the owner's
standing instruction of 2026-10-01 and recorded in `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`
('ANSWERED 2026-10-02 (standing instruction), eFV frontier v3'):

- **E3-Q1 Scrap/keep = C**: keep V2 as the one primary, re-derive it at P5, enter the anchor,
  the model-class arms and the screened families as labelled secondaries; redo the class only
  if V2 reads BEHIND on R-LV.
- **E3-Q2 Epoch ids = A**: land the override ids and resolve the 135 keys inside EPOCH_E2,
  before step C; the ids feed the label join only.
- **E3-Q3 Admit window = A**: EV-12 waits for both registered screens, hard cutoff 2026-11-15;
  the reserved read date does not move.
- **E3-Q4 Secondaries = A**: the labelled secondaries (MC-2, admitted arms, the rank-rule
  sensitivity) and a Family S stratum Holm family on the reserved reads, no ship weight.

Lane C questions (`SP/efv3/LANE_C_questions.json`), folded into the plan at their recommended
option and taken as design (EFV3_PLAN.md s10); no separate answer is recorded for them, so each
is the DEFAULT TAKEN and the owner may reverse any by one line:

- **lane C E3-Q2** (weight rule): default taken, A, the rank-consistent rule as a sensitivity
  only (s6 above).
- **lane C E3-Q3** (sign slopes): default taken, A, MC-4a adoptable on non-inferiority with no
  margin claim, coded behind `V2_SIGN_CONSTRAINED = False` that stays off until a registered
  look passes. This is not the unified E3-Q3 (Admit window).
- **lane C E3-Q4** (pairwise arm): default taken, A, screen MC-1 once, secondary if admitted.
  Had it been B, MC-1 would not be built and Holm would run with m = 4.
- lane C E3-Q1 (anchor arm as a labelled secondary) is carried by the unified E3-Q4 = A.

## 10. Bans restated

- No read of R-LV (list vintages 2020 and 2021) or R-VM (debut cohorts 2025 and later).
- No statistic by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, look not before
  2026-11-20).
- No re-run of the 39 closed arms (`data/xfv_arm_ledger.json`) or of the lambdarank sweep, the
  monotone GBM re-adjudication, the hierarchical lambda or the learned-weight A/B on their spent
  frames; no re-shopping of any boundary, grid or weight fixed here.
- No 2026 outcome associated with any score.
- No change to the served grade, the comparator (served consensus, DS-Q4), the primary
  candidate (V2), the statistic (DS-Q3), the frames or the reserved guards.

## 11. What this document does not do

It moves no served number, writes no ledger row and scores no frame. It does not claim a lead:
every expected delta in s1 is inside the development floor and the reserved floors except the
top of MC-2's range, which is itself a transfer assumption. It does not close the Pipeline gap
on list vintages (-0.0277 within on lv_dev); only information Pipeline does not hold at the
read can.
