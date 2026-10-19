# eFV against consensus on arrival labels: the tilted-labels read (method, fixed before any number)

Registration status: REGISTERED

Written 2026-10-19 (task EFV_BEAT_TILTED_LABELS) under the owner's decision EW3-11 of
2026-10-15 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`; asked why eFV still ties consensus
when every atlas driver helps, the owner wrote 'Can we please use the drivers to beat
consensus with eFV?' and picked three paths: the timing edge, pooled power and tilted labels,
'copy limited to arrival'). This document is path 3, TILTED LABELS. It is committed ALONE,
before the module `tools/efv_beat_tilted_labels.py` exists and before any number of this read
is computed: it fixes the claim, the estimand, the frames, the labels, the raters, the
statistic, the seed, the pass rule and what the site may say under each verdict. Sections 1
to 13 are written before the read; the run appends section 14 (the numbers) and section 15
(the verdict). No em-dashes. Nothing here, in its code or in its artifacts, is cut by
consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, binding): the only groups are frame, side
and year (list year or debut year).

## 1. The claim, kept apart from the value claim

This read registers an ARRIVAL claim: whether eFV orders prospects by WHO REACHES THE MAJORS
better than PROSPX consensus does. It is not the long-run value claim. The value claim (W3 on
list vintages, career WAR on debut cohorts) stays exactly where the earlier reads left it,
'ties consensus', and nothing in this read can change it. The labels here are tilted: they
reward the timing information a model with an arrival (timing) head carries by construction,
so a pass here says nothing about how good eFV's grades are as grades.

## 2. What was seen before this document (disclosed)

- The prior finding the task names: consensus plus age plus level beat consensus by +0.047 on
  R3 (reached the majors within three seasons of the list year). The memory and documents call
  this TILT because R3 is the timing head's own training target.
- `docs/efv-v2/EFV_BEAT_TIMING_EDGE.md` section 13.3: eFV v5 COMBINED (the pre-refit
  development fit) re-read at in-season dates against consensus as published, on lv_dev, R3,
  within 0.3536 against 0.3504, +0.0031 (CI95 -0.0253 to +0.0322). A different rater (pre-refit,
  in-season inputs) at different read dates.
- `data/efv_2026_holdout.json` (EW3-13, spent): on the 2026 season, arrival in 2026 (R2026),
  AUC, the then-served v5 COMBINED minus consensus +0.0488 (player lower bound +0.0344),
  hitters +0.0955, pitchers +0.0043.
- `data/_labs/efv5/efv5_refit_fit.json`: the re-fit's value-label reads (W3, career WAR), not
  any arrival label.

No arrival-label number of the served eFV (the re-fit RT) on a development frame has been
computed by anyone before this document. The author has read none.

## 3. The raters

All raters are scored on the SAME rows of a frame; consensus is the comparator.

1. **eFV served (the deciding rater).** The served eFV at HEAD is eFV v5 COMBINED as re-fit,
   variant RT (`efv5_combined.EFV_V5_COMBINED_ON` and `efv5_refit.EFV_V5_REFIT_ON` both True;
   `efv_v2_serve.production_models` serves `efv5_refit.production_models()`; model id
   `efv_v5_combined`). Its development order is the re-fit's out-of-fold order: the RT fold
   packs of `efv5_refit.Run.fold_packs("RT", ..., design="FC")` on the inputs of
   `efv5_refit.Run.build1()` (repaired population norms), combined as
   `u_c + w_skill x e_skill + w_time x e_time` with each fold's cross-fitted weights from
   `efv5_refit.cross_fitted` with the guard as committed at HEAD
   (`CROSSFIT_MIN_NONZERO` = 100, `docs/efv-v2/EFV_PIT_AUDIT_FIXES.md` section 1). Reason: the
   site's sentence would be about the eFV the site serves, so the served model decides.
2. **eFV v5 COMBINED, development fit (reported).** The rater the task names: the pre-refit
   development order (`efv5_refit.Run.phase0()`, the fold orders of
   `efv5_combined.Fits` on `efv5_combined.build_dev` with legacy norms, no tracking head blend
   on these frames).
3. **The timing heads alone (reported).** The arrival head's own order: `u_c + e_time` of the
   fold's timing head, rank-equivalent to the head's fitted logit (`b_uc` > 0 for a usable
   head; a fold with no usable timing head scores consensus there, disclosed). Two of them:
   the re-fit RT's timing head (fitted on the list-vintage pool, served at weight 0) and the
   v5 COMBINED development fit's timing head.
4. **PROSPX consensus (the comparator)**: the consensus grade on the row, the same value every
   development read scores.

No model is refitted, tuned or chosen here; the folds are rebuilt in memory exactly as the
re-fit's read built them.

## 4. The frames (development only)

- **lv_dev**: list vintages V 2017, 2018 and 2019 (frame version lv1_v2), the scored rows of
  the development read (2,862 rows in the re-fit and v5 COMBINED reads).
- **vm_dev**: debut cohorts Y 2017 to 2023 at frame version vm2, the scored rows of the same
  reads (830 rows). Every vm_dev row is a player who debuted in Y, read in the preseason
  window of Y ([Y-01-01, Y-05-01)).
- **Parity guards (the run refuses on a failure, before any arrival number).** (a) The v5
  COMBINED development order reproduces the committed within Spearman of
  `data/_labs/efv5/efv5_combined_fit.json` on both frames (the re-fit's own guard, 5e-5).
  (b) The RT order with the re-fit's AS-READ cross-fitted weights (guard off,
  `min_nonzero` = 0) reproduces the RT within Spearman of `data/_labs/efv5/efv5_refit_fit.json`
  on both frames to 1e-4 (that artifact rounds to four places). (c) The scored row keys of
  both builds are equal.
- **R-LV and R-VM (spent)**: section 10.
- **The 2026 holdout**: quoted only, section 11.

## 5. The labels

Read on the frozen label the development reads score (`efv_labels.provider()` == 'fwar',
`fwar@2026-10-02-0341299c20ec`; the tool refuses any other provider). No 2026 season is read
by any development label below.

### 5.1 lv_dev (list vintage V)

- **R3**: `efv_labels.labels_for(...)["r3"]`: 1 when the player REACHED (BUST2 rule) with an
  effective debut year in V to V+3, else 0.
- **R5**: 1 when the player REACHED with an effective debut year in V to V+5, else 0 (the same
  `labels_for` record: its `reached` class and `debut_year`). For V = 2019 the window ends with
  2024, so no 2025 or 2026 debut is ever counted.
- **W2 (early WAR)**: `efv_labels.labels_for(...)["w2"]`: WAR over the first two MLB seasons
  (dy, dy+1) when the debut is in V to V+3, else 0.
- A row whose label is None (an identity conflict, a reserved debut) leaves that label's read
  (count disclosed).

### 5.2 vm_dev (debut cohort Y)

Every vm_dev row reached the majors in Y, its read year, so R3 and R5 are 1 on every row and
have no order to score. On this frame:

- **AD (arrival day)**: how early in season Y the player debuted: minus the number of days
  from Y-01-01 to the debut day, so an earlier debut scores higher. The debut day is the
  matrix row's own debut date (`cutoff`, the date the matrix was cut at), used only when it is
  a full date inside Y and the record's debut date is not a placeholder; any other row leaves
  the AD read (count disclosed). AD is the vm_dev leg of the arrival claim (default D-1).
- **W2 (early WAR)**: WAR in seasons Y and Y+1 on the frozen label (Y+1 is at most 2024).

### 5.3 Which label decides

- **PRIMARY (the stated label, decides)**: ARRIVAL = R3 on lv_dev and AD on vm_dev.
- **Secondary (reported with the same rule; a secondary pass licenses no copy by itself)**:
  R5 on lv_dev with AD on vm_dev; W2 on both frames.

## 6. The statistic

- **Primary.** Within Spearman: for each group (side, year) with at least 20 rows of the
  label's read (`efv_v2_stat.MIN_GROUP_ROWS`) and a label that is not constant inside the
  group, the Spearman rho (ties averaged) of the rater's own score against the label; the
  size-weighted mean over groups. Paired: a group counts only when both raters have a rho
  there (`efv_v2_stat` DS-15 rule). Delta = rater minus PROSPX consensus.
- **AUC (reported, decides nothing).** On the binary labels (R3, R5): the within (side, year)
  Mann-Whitney AUC of the rater's score for the label, size-weighted over the same groups.
- **Intervals.** Paired E_cond bootstrap (scores fixed, clusters resampled with replacement,
  every row of a drawn cluster comes with it; `source_backtest._cluster_layout` and
  `_cluster_draw`), B 2000, seed 20261017, under two clusterings: the PLAYER, and the CLUB (the
  org on the player's latest board point dated in [year-01-01, year-05-01), else the latest
  point dated before that window's end, else UNK; the rule of
  `tools/efv_beat_pooled_power.club_of`). From the draws: lb95 the 5th percentile (one-sided 95
  percent lower bound), ub95 the 95th, ci95 the 2.5th and 97.5th, mde95 = 1.645 x sd.
- **Null comparator (required).** Consensus is the zero-adjustment null (an order equal to
  u_c). Beside it, a permutation null: within each fold's test rows the served rater's
  (e_skill, e_time) pairs are permuted together across rows, u_c and the fold's weights held,
  200 permutations, seed 20261017; the null's 95th percentile of delta (served minus
  consensus, primary label) is reported per frame.
- **Planted recovery (required).** A planted rater P = u_c + 0.15 x (q - 0.5), with q the
  within (side, year) percentile of (the primary label standardized within the group plus a
  standard normal draw, seed 20261017). P minus consensus is read with the same statistic and
  a player-clustered bootstrap of B 500, seed 20261017. It shows the pipeline sees a rater that
  carries arrival information, with the orientation of each label right (on AD, earlier is
  better).
- **Reported cuts (descriptive).** By side; by year; every rater against consensus; the served
  rater against the v5 COMBINED development fit; row counts per (side, year). Never by
  consensus-FV level.

## 7. The pass rule (fixed here, before any number)

The arrival claim PASSES when, for the served eFV minus PROSPX consensus on the PRIMARY label
(R3 on lv_dev, AD on vm_dev), within Spearman:

1. the one-sided 95 percent lower bound is above 0 under BOTH the player-clustered and the
   club-clustered bootstrap, on lv_dev AND on vm_dev; and
2. on each frame the observed delta is above the 95th percentile of the permutation null; and
3. on each frame the planted rater's player-clustered lower bound is above 0 (else the frame
   is UNRESOLVED and the claim does not pass).

Anything else is NOT PASS, worded 'trails' on a frame whose player-clustered ub95 is below 0,
'unresolved' on a frame whose planted check failed, and 'ties' otherwise. The secondary labels
get the same reading and are reported; they decide nothing. The v5 COMBINED development fit
and the timing heads get the same reading and are reported; they decide nothing.

## 8. No look-ahead and no leakage

- Every order is out of fold: the re-fit's and v5 COMBINED's folds train on rows with a
  decision year before the scored year (vm_dev) or on list vintages other than the scored
  one with every scored player left out (lv_dev), as their reads did; the cross-fitted weights
  of a fold are estimated with that fold left out.
- No fold is refitted on, tuned on or selected by an arrival label of this read.
- The labels start at or after the read: an lv_dev label counts debuts from V on, the frame
  is read at V's preseason; a vm_dev AD is the debut day inside Y, read in Y's preseason
  window (a row whose debut day falls before its read date stays in the read and is disclosed
  as a count; the matrix pins the read to the preseason point before the debut).

## 9. Defaults applied (the owner may choose differently)

- D-1 the vm_dev arrival leg is AD (arrival day), because R3 and R5 are constant on a frame of
  debut cohorts. Alternatives: (b) read the arrival claim on lv_dev alone (the AND rule then
  needs the owner to relax it); (c) let W2 stand as the vm_dev leg.
- D-2 the deciding rater is the served eFV (re-fit RT); the pre-refit v5 COMBINED development
  fit the task names is read and reported beside it.
- D-3 the cross-fitted weights carry the guard committed at HEAD (`CROSSFIT_MIN_NONZERO` 100);
  the as-read weights reproduce the re-fit artifact (parity) and are reported.
- D-4 the primary label is R3 (with AD on vm_dev); R5 and W2 are secondary.
- D-5 both clusterings must clear 0 (the pooled-power precedent).
- D-6 the spent frames are not opened unless the development rule passes (section 10).

## 10. The spent frames

R-LV (list vintages 2020 and 2021) and R-VM (the 2025 debut cohort) were read before (v3,
v4, v5, v5 COMBINED, the pooled-power read) and are SPENT. They are opened only on a
development PASS, at most once each, labelled SPENT, on the gate's committed sha
`e7931ce4e13110eebb53555bff455ff13ca7c502`, primary label only (R3 on R-LV, which reads debuts
through 2024; AD on R-VM), for corroboration, never the sole claim. The served re-fit has no
spent-frame builder (`efv5_refit` fits development folds only); on a development PASS this
task records the spent read as the next registered step and does not build one around the
registration. On NOT PASS they are not opened.

## 11. The 2026 holdout (corroboration only)

EW3-13: the 2026 season was the one-time holdout read by EFV_2026_HOLDOUT_READ and is spent.
Nothing is recomputed on 2026. The record `data/efv_2026_holdout.json` is quoted as written:
the legs `r2026|auc|pooled|efv_v5_combined-consensus`, `r2026|auc|hit|...` and
`r2026|auc|pit|...` of frame `list` (delta, player and club lb95). It froze the then-served
pre-refit v5 COMBINED at the 2026 opening day; it is a different rater from the served re-fit
and is printed as such.

## 12. What the site may say

- **PASS, and the owner answers the flip question yes** (`OWNER_QUESTION.md` in the task's
  output directory): one sentence, derived from the artifact, on the Source Comparison page and
  nowhere else until the owner widens it: 'eFV beats consensus at predicting who reaches the
  majors (arrival): within-year Spearman +X on list years 2017 to 2019 (reached within three
  seasons; one-sided 95 percent lower bound +L) and +Y on debut classes 2017 to 2023 (how early
  in the season; lower bound +M). Development frames, used to build eFV; on later WAR eFV ties
  consensus.' Never 'better prospect grades', never a long-run value word, never the headline
  'beats consensus' of the vintage-matched frame. The Source Comparison row (frame 'arrival
  (tilted, development)', never on the progress chart) and the sentence are drafted in this task
  behind a flag that defaults off, and nothing shows before the owner's answer.
- **PASS without the owner's answer**: nothing served moves.
- **NOT PASS**: nothing served moves; no arrival sentence is drafted or printed; every copy
  keeps 'ties consensus'.

Whatever the verdict: no served number, grade, chip, ledger row or claim moves in this task;
the read writes no row to `data/efv_progress.json`.

## 13. Bans, hygiene and outputs

- No reserved row is built unless section 10 opens it; the development builds raise on list
  vintages 2020 and 2021 and stop before the 2025 cohort (`efv_vintage_frame`).
- No statistic by consensus-FV cell anywhere (`docs/PROSPECT_ANCHOR_GATE.md`); the test scans
  the module source.
- No projections retrain; the fWAR label epoch's runbook is untouched;
  `backtest.run_backtest` is never called; no model is refitted on an arrival label.
- Code `tools/efv_beat_tilted_labels.py` (refuses to run twice over an existing artifact),
  test `test_efv_beat_tilted_labels.py`, artifact `data/_labs/efv5/efv_beat_tilted_labels.json`
  (off the webroot), plain-language results `docs/efv-v2/EFV_BEAT_TILTED_LABELS_RESULTS.md`,
  and sections 14 and 15 appended below. The re-fit's resumable builds are cached in a scratch
  directory outside the repository.
