# eFV v5 COMBINED, the registered re-fit (EFV_FIX_B_REFIT): method, fixed before any number

Registration status: REGISTERED

Written 2026-10-15 (task EFV_FIX_B_REFIT) under the owner's decision EW3-21 of 2026-10-15
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), after the eFV driver audit (defects D1 to D6,
its section 4 items B1 to B5). The owner's four answers this document carries out:

1. the hitter arrival (timing) term is RE-DERIVED through a registered read on the
   outcome-blind list-vintage frame, not removed by fiat;
2. the skill weights of both sides are re-derived by a REGISTERED re-fit whose fold design
   is fixed here; the served hitter w_skill stays 0.908861 until this read is in;
3. the live board KEEPS reading the 2026 season (disclosed since EFV_FIX_A A3), and the
   re-fit adds training rows read at the live timing;
4. the served "ties consensus" claim stays until this re-fit reads, and is then re-derived
   from the re-fit's own numbers.

This document is committed ALONE, before the module `efv5_refit.py` exists and before any
number of this read is computed. Sections 1 to 11 are written before the read; the run
appends section 12 (the numbers) and section 13 (the verdict). No em-dashes. Nothing here,
in its code or in its artifacts, is cut by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`,
binding): the groups are side, list year or decision year, fold, level, age band, role and
position family. Only the development frames are read (lv_dev, vm_dev); no reserved row
(R-LV list vintages 2020 and 2021, R-VM debut cohorts 2025 and later) is built or scored,
and `backtest.run_backtest` is never called.

## 1. What is re-fitted and what is not

The model stays eFV v5 COMBINED (`docs/efv-v2/EFV_V5_COMBINED.md` sections 2 and 3, served
by owner override EW3-10):

    order_idx = u_c + w_skill * e_skill + w_time * e_time        inside (side, list year)
    grade     = the group's consensus FV value at order_idx's rank (efv_v2_model.output_map)

with each head one sign-bounded joint penalized fit of V2's admitted drivers at V2's alpha
and the candidate columns at one lambda chosen by nested forward-chained CV (unchanged:
`efv5_combined.joint_skill`, `joint_timing`, `select_lambda`, the grid V2_ALPHAS, the sign
bounds of the atlas). What this re-fit changes is fixed by five arms, A1 to A5; nothing
else moves (the output map, the anchor, the candidate list minus the dark columns, the
sign bounds, the penalty grid, the admission rule, W_MAX = 1, the frozen fWAR label
`fwar@2026-10-02-0341299c20ec`). The pitcher tracking-era head stays at its own flag
(off); it is not applied anywhere in this read.

## 2. The arms

### A1. The population norms repair (audit D5, EFV_FIX_A A1 and A6)

`efv_w2_popmle.POP_REPAIR_ON` is True for every fit, column and read of the re-fit (each
count column summed once in the league norms; non-affiliated Mexican League lines out of
the population). The translator is rebuilt by its own construction; the population
column `w4p_pop_{side}` is rebuilt on every frame, the twin rows (A4) and the live board.

### A2. Dark columns held at zero (audit B4)

A column that reads no value on the live board cannot move a served grade, but its slope
moves every other slope of its head. The re-fit DROPS from both heads, in every fit
(development folds and production), the columns the 2026-10-15 live read lists as dark or
withheld (`data/xfv.json` `meta.served_model.disclosures.dark`, the receipt of
`efv5_combined.live_columns`):

- the rater panel: `w2r_panel_hit`, `w2r_panel_pit` (no list of the read year);
- the report extraction: `rpt_conviction_hit`, `rpt_hedge_count_hit`, `rpt_risk_hit`,
  `rpt_approach_concern_hit`, `rpt_writer_minus_stated_hit`, `rpt_arrival_hit`,
  `rpt_conviction_pit`, `rpt_writer_minus_stated_pit`, `rpt_arrival_pit` (None by
  construction);
- the support-withheld tool cells: `t5_pit_Ap_all_SP_sl_gap`, `t5_pit_Ap_young_all_sl_gap`,
  `t5_pit_Ap_all_all_sl_gap` (lit in one training read season).

A dropped column is a slope fixed at 0; the other slopes are re-estimated without it. The
run re-reads the live receipt and records it beside this list; the list above is what the
fit uses. The pitch-event family is lit on the live board since EFV_PBP_2026 and stays in.

### A3. The timing head on the outcome-blind list-vintage frame (audit D1, B2)

The arrival head is a penalized logistic of REACHED. On the v1 matrix rows the label and
the row's read date are aligned with the outcome (a debuted row is read the season before
its debut, a bust at its last list year), which is what made the level slope five times
the list-vintage one (audit D1: 0.727 against 0.144 per consensus slope). The re-fit
fits the timing head, everywhere, on the list-vintage frame (every listed player at the
preseason point of list vintage V, REACHED = R3, a debut in V to V + 3), with the timing
menu that the live board can read:

- the drivers: V2's vm-frame timing candidates (`efv_v3.head_candidates(base_config,
  side, "timing", ids_outcome_blind=False)`: no protection status and no absence flag,
  which the live board does not carry) under the DS-06 admission and V2's alpha inside the
  training rows, with every non-dark candidate timing column (section 3 of the v5
  document minus A2) at the nested lambda, through `efv5_combined.joint_timing`;
- the training rows:
  - lv_dev fold V (2017, 2018, 2019): the fold's own training rows (list vintages 2011 to
    V - 1, every player of the V frame left out), as v5 did;
  - vm_dev fold Y (2017 to 2023): the list-vintage rows of vintages 2011 to
    min(2019, Y - 1), every player of fold Y's test rows left out (the lv_dev fold rule
    applied to the debut year);
  - production: the list-vintage rows of vintages 2011 to 2019, all players;
- the candidate timing columns on those rows are built by the list-vintage builders of the
  development read (`efv5_group_drivers.lv_columns`, the eFV v4 family builders), on one
  frame that holds every list-vintage row of 2011 to 2019.

e_time is the head's logit driver sum over its own logit consensus slope, read on the
fold's test rows (or the live rows) as before. w_time is then re-derived by section 4.

### A4. Training rows at the live timing (audit D3, B3)

The live board reads the latest ENDED minor league season on 15 October with consensus as
it stands that day (an October Pipeline re-rank for about half the board, an August
midseason list or older for the rest). No training row is read that way: every v1 matrix
row pairs its consensus point with the season before it, almost always a preseason list
dated after that season (audit T1: no training row has consensus dated within 0 to 30 days
of its read season's end). An outcome-blind inventory of the board points (counts of
`snapshot_date` by month over `efv_dataset.asof_records`, no grade, no label) shows that
historical October points barely exist (2 in 2020, 3 in 2021, 4 in 2022, 1 in 2025, none
before 2020), so a training row with consensus inside the strict 0 to 30 day window cannot
be built from history. The re-fit therefore adds rows read on the live board's own
calendar day, with whatever consensus stood on that day, which is how the live board
itself takes it:

- for every v1 matrix row of the vm frame (side s, decision year dy, cutoff c, read
  season R = `efv_w2_milb.last_readable_season(dy, c)`), its TWIN is read on
  T = R-10-15:
  - the twin's consensus point is the record's latest board point with `snapshot_date`
    on or before T that carries `consensus_fv_raw` (`efv_dataset.asof_records`);
  - no twin when T is on or after c (the row's own decision point), when there is no such
    point, or when that point is the row's own as-of point (the twin would be the row);
  - the twin is the row with its prior block (`efv_dataset._prior_features`: consensus FV,
    per-source FV, spread, trend, tools) read at that point, the construction
    `efv_v2_model.pinned_inputs` uses for the timing pin; the minor league block is the
    row's own (the row and its twin both read season R); BMI as of T;
  - the twin keeps the row's decision year (its within-year group, so u_c and u_y are
    ranked among the year's rows and twins), its target, REACHED and weight;
  - every candidate column of the twin is read as of the twin (read year R + 1, cutoff T,
    as-of date the point's date) by the live board's as-of builders
    (`efv5_combined.asof_columns`, the primitives `live_columns` and `history_columns`
    call), unclipped, as a training column;
- twins enter the SKILL head's training rows of every vm-frame fit (vm_dev fold Y: twins
  of decision years before Y; production: twins of decision years before 2025) beside the
  rows themselves; they enter neither the timing head (A3) nor any test row of the
  primary read nor the weight estimate (section 4);
- the lv_dev folds take no twins: their skill head trains on the list-vintage frame, whose
  rows are read at one preseason point per vintage by the vintage frame's own builder.

Reported with the twins (outcome-blind): counts per side and decision year, and the
distribution of the twin's consensus lag (point date minus R-10-01) beside the live
board's. The strict 0 to 30 day part of the live board (its October 2026 re-ranks) stays a
regime no training row covers; the results say so.

### A5. The population tail transform (audit POP-4, B5): a registered variant

The population column enters linearly and its live tail sits at the edge of the training
range (Nelson Rada, 99.86th live percentile). The variant RT replaces `w4p_pop_{side}` by
its within-group mid-rank percentile minus 0.5 among the group's rows carrying a value
(monotone, bounded, centered within the read year): a training row's group is its
(frame, decision year or list vintage) among the rows of the fit (twins with their
decision year), a test row's group is its fold's test rows, a live row's group is the live
board side. A row without a value stays None (the training-mean imputation). No cap.

## 3. The candidates read

| id | what | role |
|---|---|---|
| V5 | eFV v5 COMBINED as served: legacy norms, every candidate column, the vm-frame timing head, the P5 weights (hit 0.908861 / 0.202573, pit 1.0 / 0.020473) | the comparator, recomputed in the same run on the same rows; it must reproduce the committed development read (lv_dev 0.1685, vm_dev 0.3611 within, pooled over sides) |
| R | A1 + A2 + A3 + A4, weights by section 4 | the primary candidate |
| RT | R + A5 | the registered variant |
| W | V5's heads with weights by section 4 | decomposition only (the weight effect alone) |
| R0 | R without A4 | decomposition only (the twins' effect) |

## 4. The weights (the fold design, fixed here)

**Heads: forward chaining.** Each development fold's heads are fitted on rows before the
fold (lv_dev fold V: list vintages before V, the fold's players left out; vm_dev fold Y:
decision years before Y), exactly the folds of every development read and of the ship rule
below. The audit shows the answer depends on this choice (hitter w_skill 0.467 forward
chained, 0.852 leave-one-year-out, on V5's heads). Forward chaining is fixed because:

1. the served board is a forward read: its heads are fitted on years before the live year
   and read a later cohort; a leave-one-year-out head reads earlier cohorts with heads that
   saw later ones (later era norms, later list coverage, shorter career-WAR horizons on the
   vm frame), a direction the board never has;
2. the development reads and the ship rule are forward chained; a weight estimated on
   leave-one-year-out heads would be applied to heads it was not estimated for;
3. the known cost is stated, not hidden: an early forward fold trains on fewer years than
   the production fit (2011 to 2016 against 2011 to 2024), its e terms are noisier, and a
   regression on noisier e terms shrinks the weight toward 0 (consensus). That error is
   toward the anchor, the direction the audit found safe (D4: large hitter calls realized
   10 to 25 percent of their size).

Leave-one-year-out is computed for R as a SENSITIVITY (lv_dev: vintages 2011 to 2019 but V,
V's players left out; vm_dev: decision years 2011 to 2023 but Y) and reported beside the
forward-chained weights; it decides nothing.

**The weight rule (DS-08's successor).** Per side, pool every development fold of both
frames: on each fold's test rows u_c and u_y (the within-(side, year) consensus and target
percentiles), e_skill and e_time of the fold's heads; OLS u_y ~ 1 + u_c + e_skill + e_time;
w_skill = clip(c_skill / c_uc, 0, 1), w_time = clip(c_time / c_uc, 0, 1) (W_MAX = 1, both 0
when c_uc <= 0; a head unusable on every row, or a column zero on every pooled row, gets
weight 0). This is DS-08's form on the development frames instead of the rule years.

- **Served weights** (the production fit): the pool of every fold of the side.
- **Read weights (cross-fitted)**: a fold's orders in the development read use the weights
  of the pool with that fold left out, so no fold is scored with a weight estimated on its
  own rows.
- **Interval**: player-clustered bootstrap of the pooled OLS (players drawn with
  replacement, all their fold rows together), B 2000, seed 20261016; CI95 of each ratio
  reported. The unclipped ratios are reported beside the clipped weights.

**The project's objective alongside.** The within (side, vintage) Spearman of the order
(the statistic below) is reported at the cross-fitted weights (the read) and, descriptively,
on a grid w_skill in {0, 0.1, ..., 1.0} with w_time at 0 and at its estimate (in sample on
the pooled frames; it chooses nothing). The audit found the rank statistic falling as the
hitter weights grow; the grid shows whether the re-fit's heads still do.

## 5. The statistic and the intervals

The registered primary of the program (`efv_v2_stat`): the within (side, list year)
Spearman of the rater's score with the frame's label, size-weighted over groups of at least
20 rows, pooled over sides; per side beside it. Raters on the scored rows: each candidate,
V5, PROSPX consensus, MLB Pipeline, FanGraphs. Paired E_cond intervals (scores fixed,
players resampled, player-clustered, B 2000, seed 20260906), the development read's own
machinery (`tools/efv_v3_backtest.frame_block`, `paired`). Secondary: pooled Spearman after
the output map and contributor AUC, reported. Position-group cells (hitters C, IF, OF;
pitchers one cell), reported. Never a cell by consensus-FV level.

**The live-timing read (secondary, reported, decides nothing).** On vm_dev, every scored
test row that has a twin (A4) is read as its twin: V5's and the candidate's fold models
applied to the twin (u_c within (side, Y) among the twins), consensus the twin's own
point; within Spearman per (side, Y) as above, candidate minus V5 and minus consensus with
E_cond intervals. It is the dev-frame read at the live timing the audit asks for (B3); the
results report it as such.

## 6. The ship rule (fixed here, before any number)

A candidate C in {R, RT} passes when BOTH hold, point estimates, within Spearman pooled
over sides:

1. it beats V5 on the pooled development frames: (n_lv_dev x (C minus V5 on lv_dev) +
   n_vm_dev x (C minus V5 on vm_dev)) / (n_lv_dev + n_vm_dev) > 0;
2. it trails V5 by no more than 0.005 on either frame: C minus V5 >= -0.005 on lv_dev and
   on vm_dev.

If both pass, the one with the larger pooled difference is prepared (a choice between two
registered candidates on the frames they are read on; disclosed). Against consensus, the
read is reported (point, CI95) on each frame and pooled; it does not enter the rule.

On a pass: the flip is PREPARED DARK and the owner flips it. `efv5_refit.EFV_V5_REFIT_ON =
False`; with it True, `efv_v2_serve.production_models` serves the re-fit's production fit
(A1 to A4, A5 if RT, the served weights of section 4 from `data/efv5_refit_weights.json`),
the board's served model id is `efv_v5_combined`, and its claim is the one section 7
derives. `efv_w2_popmle.POP_REPAIR_ON` moves with it (EFV_FIX_A: it never flips alone; a
test pins the two flags equal). With the flags False every served artifact is byte
identical to the code before this task.

On a fail: nothing is prepared to serve; the read and the weights are recorded and the
owner question says what fell short.

## 7. The served claim, re-derived (owner answer 4)

The claim the board prints today (`meta.served_model.claim`) is V2's "ties" on the vm2
frame under model id `efv_v2`; the audit (W6) found it describes a model that no longer
serves. Re-derived from the re-fit's own development numbers: for the served model id
`efv_v5_combined`, the word reads the vm_dev frame (the vintage-matched frame of this
read) by the rule of `efv_v2_serve.served_claim` ("trails" when the CI95 against
consensus lies below 0; "ties" otherwise; a development frame can never read "leads"),
with the lv_dev figure stated beside it. If R or RT is prepared, the claim is the prepared
candidate's; otherwise it is V5's own development numbers (the committed v5 read). The
claim text is stated in the owner question for approval WITH the flip; it does not reach
the board before the owner flips.

## 8. The board effect (reported in the owner question)

On the live board as of the run date (the served read: list year 2026, read season 2026,
`efv_v2_serve.score_live`), the candidate's production fit against the served grades of
`data/xfv.json`: Nelson Rada (rank, eFV, consensus, his chips), the 50 largest movers by
absolute change in eFV per side, and the mean absolute eFV minus consensus per side, before
and after. The eFV grade is printed to one decimal (eFV rounds to nearest).

## 9. The ledger and the artifacts

- `data/_labs/efv5/efv5_refit_fit.json`: every candidate's development read, the weights
  and their intervals, the leave-one-year-out sensitivity, the objective grid, the twins'
  receipts, the live-timing read, the ship reading, the board effect.
- `data/efv5_refit_weights.json`: the served weights per side and the production fit's
  driver table (read by the serve path only when the flag is True).
- `data/efv_progress.json`: two development rows (model `efv_v5_refit`, frames lv_dev and
  vm_dev, role development, adjudicates nothing), drawn hollow on the Source Comparison
  page as every development row is.
- Code `efv5_refit.py`, tests `test_efv5_refit.py`.

## 10. Defaults applied (the owner may choose differently)

- D-1 forward-chained heads for the weight (section 4); leave-one-year-out a sensitivity.
- D-2 the weight is DS-08's OLS ratio pooled over both development frames by row; the
  within Spearman is the read, not the selector.
- D-3 twins read on 15 October of the read season with the latest point, no lower bound on
  the point's age (the live board's own rule), at the row's own weight; vm frame only.
- D-4 the timing head on the list-vintage frame with the vm-frame menu (no protection or
  absence keys); vm_dev fold Y reads vintages up to min(2019, Y - 1).
- D-5 the dark list of A2 as the 2026-10-15 live receipt has it.
- D-6 the popmle variant is the within-group mid-rank percentile (not log1p).
- D-7 if R and RT both pass, the larger pooled difference is prepared.

## 11. Bans and hygiene

- No reserved row: the development build raises on list vintages 2020 and 2021 and stops
  before the 2025 cohort (`efv_vintage_frame`); the production timing pool stops at 2019.
- No statistic by consensus-FV cell anywhere; the test scans the module source.
- No projections retrain; the fWAR label epoch's runbook is untouched;
  `backtest.run_backtest` is never called.
- The served grade does not move in this task: every new path is behind
  `EFV_V5_REFIT_ON = False`.

## 12. The read (appended by the run, 2026-10-15 local, 2026-10-16 UTC; development frames)

Run: `python -u efv5_refit.py --run --cache <scratch>` after the registration commit ed078e80
(artifact `data/_labs/efv5/efv5_refit_fit.json`, generated 2026-10-16T00:24:08Z; label
`fwar@2026-10-02-0341299c20ec`; E_cond B 2000, seed 20260906; weight bootstrap B 2000, seed
20261016). No reserved row was built; nothing was cut by consensus-FV level.

**Disclosed harness defect, corrected before any reading was used.** The first write of the
artifact keyed every configuration's scored-row orders by (side, fold, player) across BOTH
frames, so a player who sits in a list-vintage fold and a debut-year fold of the same year took
his vm_dev order on lv_dev. The registered parity check of section 3 caught it (V5 recomputed on
lv_dev 0.1615 against the committed 0.1685). The orders are now keyed inside their frame, the run
asserts parity before it reads anything (it refuses otherwise), and the statistics were
recomputed from the same cached builds, fits and weights: no column, fit, penalty or weight
changed, and the vm_dev numbers were unaffected. The first write is kept outside the repository.

### 12.1 Receipts

- V5 parity: recomputed V5 within 0.1685 (lv_dev) and 0.3611 (vm_dev), the committed read's own.
- A2: the live receipt of the run lists exactly the registered dark columns on both sides
  (hitters: the rater panel and the six report fields; pitchers: the rater panel, the three
  report fields and the three withheld High-A slider cells).
- A3: the list-vintage timing pool holds 3,053 hitter and 2,909 pitcher rows (list vintages
  2011 to 2019); every candidate timing column was built on it.
- A4: twins exist for 640 of 1,889 hitter and 676 of 1,981 pitcher matrix rows (no consensus
  point by the read day: 1,123 and 1,173; the point was the row's own: 126 and 130; read day not
  before the cutoff: 0 and 2). The twin's consensus lag (point date minus 1 October of the read
  season) has median -63 days (hitters) and -62 (pitchers), 10th percentile -253; no twin's
  consensus is dated 0 to 30 days after the season (share 0.0): the October re-rank regime of
  the live board stays untrained, as the registration expected.

### 12.2 The weights (section 4; per side, forward-chained heads, both frames pooled)

| config | side | w_skill (OLS ratio; CI95) | w_time (OLS ratio; CI95) | ratio on lv_dev / vm_dev (skill; time) |
|---|---|---|---|---|
| W (V5's heads) | hit | 0.465 (0.465; 0.266 to 0.707) | 0 (-0.027; -0.129 to +0.065) | 0.521 / 0.161; -0.009 / -0.027 |
| W | pit | 1.0 (1.098; 0.569 to 1.811) | 0 (-0.129; -0.265 to -0.012) | 1.066 / 1.791; -0.241 / +0.083 |
| R | hit | 0.312 (0.312; 0.089 to 0.595) | 0 (-0.257; -0.561 to +0.028) | 0.330 / 0.232; -0.372 / -0.056 |
| R | pit | 1.0 (1.105; 0.593 to 2.026) | 0 (-0.542; -0.908 to -0.230) | 0.943 / 0.978; -0.623 / +1.237 |
| RT | hit | 0.297 (0.297; 0.065 to 0.594) | 0 (-0.242; -0.542 to +0.036) | 0.289 / 0.312; -0.349 / -0.053 |
| RT | pit | 1.0 (1.053; 0.534 to 1.918) | 0 (-0.496; -0.834 to -0.199) | 0.922 / 1.004; -0.588 / +1.141 |
| R0 | hit | 0.324 | 0 | |
| R0 | pit | 0.927 | 0 | |

Leave-one-year-out sensitivity (R; decides nothing): hitters w_skill 0.431 (lv_dev 0.465, vm_dev
0.275), w_time 0 (ratio -0.310); pitchers w_skill 0.836, w_time 0 (ratio -2.550). W's hitter
estimate (0.465) reproduces the audit's forward-chained 0.467 on V5's heads. Served before this
read: hit 0.908861 / 0.202573, pit 1.0 / 0.020473.

Cross-fitted read weights (each fold's from the pool without it): hitters 0.28 to 0.33 skill and
0 timing in every fold of every candidate; pitchers 0.91 to 1.0 skill and 0 timing in every
fold but lv_dev pit|2017, where the pooled timing ratio without that fold turned positive and
the clip set w_time to 1.0 (R and RT).

### 12.3 The development read (within (side, list year) Spearman, pooled over sides)

| frame | n | V5 | R | RT | R0 | W | consensus | Pipeline | FanGraphs |
|---|---|---|---|---|---|---|---|---|---|
| lv_dev | 2,862 | 0.1685 | 0.1696 | 0.1683 | 0.1684 | 0.1801 | 0.1792 | 0.2034 | 0.1714 |
| vm_dev | 830 | 0.3611 | 0.3869 | 0.3937 | 0.3844 | 0.3764 | 0.3814 | 0.3816 | 0.3363 |

Paired differences (E_cond CI95):

| comparison | lv_dev | vm_dev |
|---|---|---|
| R minus V5 | +0.0011 (-0.0187 to +0.0209) | +0.0258 (-0.0008 to +0.0514) |
| RT minus V5 | -0.0002 (-0.0208 to +0.0205) | +0.0326 (+0.0056 to +0.0585) |
| R minus consensus | -0.0096 (-0.0307 to +0.0116) | +0.0056 (-0.0190 to +0.0289) |
| RT minus consensus | -0.0109 (-0.0311 to +0.0098) | +0.0123 (-0.0123 to +0.0343) |
| V5 minus consensus | -0.0107 (-0.0411 to +0.0183) | -0.0203 (-0.0528 to +0.0127) |
| RT minus R | -0.0013 (-0.0034 to +0.0009) | +0.0068 (-0.0007 to +0.0143) |
| W minus V5 (weights alone) | +0.0116 (-0.0043 to +0.0270) | +0.0153 (-0.0021 to +0.0343) |
| R0 minus V5 (R without twins) | -0.0001 (-0.0194 to +0.0191) | +0.0233 (+0.0029 to +0.0451) |
| R minus R0 (the twins) | +0.0012 (-0.0002 to +0.0025) | +0.0025 (-0.0117 to +0.0159) |
| R minus Pipeline | -0.0326 (-0.0641 to -0.0014) | +0.0053 (-0.0335 to +0.0406) |
| R minus FanGraphs | +0.0132 (-0.0206 to +0.0471) | +0.0506 (+0.0063 to +0.0892) |

Per side (within; candidate minus V5 and minus consensus, E_cond CI95):

- lv_dev hitters (n 1,465): V5 0.1625, R 0.1917, RT 0.1913, consensus 0.1948; R minus V5 +0.0292
  (-0.0040 to +0.0642), R minus consensus -0.0032 (-0.0272 to +0.0194); RT minus consensus -0.0035.
- lv_dev pitchers (n 1,397): V5 0.1749, R 0.1464, RT 0.1442, consensus 0.1629; R minus V5 -0.0285
  (-0.0498 to -0.0053), RT minus V5 -0.0307 (-0.0527 to -0.0076). By fold, R minus V5: pit|2017
  -0.0865, pit|2018 -0.0026, pit|2019 +0.0040: the loss sits in the fold whose cross-fitted
  pitcher w_time hit the clip at 1.0 (12.2).
- vm_dev hitters (n 406): V5 0.3448, R 0.3952, RT 0.4021, consensus 0.3954; R minus V5 +0.0503
  (+0.0020 to +0.0931), RT minus V5 +0.0573 (+0.0084 to +0.1023); RT minus consensus +0.0067
  (-0.0188 to +0.0308).
- vm_dev pitchers (n 424): V5 0.3773, R 0.3788, RT 0.3853, consensus 0.3674; RT minus V5 +0.0080
  (-0.0157 to +0.0325); RT minus consensus +0.0179 (-0.0211 to +0.0560).

Secondary statistics (pooled after the map; contributor AUC), RT minus V5: lv_dev -0.0055 and
-0.0049; vm_dev +0.0101 and +0.0089. RT minus R on lv_dev AUC -0.0044 (CI95 -0.0080 to -0.0009).
Position-group cells, R minus V5 within: lv_dev hit:C +0.049, hit:IF -0.003, hit:OF +0.062
(+0.011 to +0.113), pit -0.028; vm_dev hit:IF +0.021, hit:OF +0.059, pit +0.001 (hit:C under 20
rows).

### 12.4 The objective alongside (descriptive, in sample on the pooled frames)

Pooled within Spearman by w_skill at w_time 0: hitters (RT's heads) 0.2383 at 0 (consensus
alone), 0.2422 at 0.1 (the peak), 0.2396 at 0.2, 0.2376 at 0.3, 0.2298 at 0.5, 0.2132 at 1.0;
on V5's heads 0.2385 at 0.1, 0.2263 at 0.5, 0.2030 at 1.0. Pitchers (RT) 0.2105 at 0, 0.2209 at
0.5, 0.2218 at 0.7 (the peak), 0.2212 at 1.0; V5's own pooled pitcher within is 0.2220. The rank
statistic still falls as the hitter weight grows past about 0.1; the OLS ratio (0.30) sits where
the rank statistic equals consensus alone.

### 12.5 The live-timing read (secondary, decides nothing)

vm_dev scored rows read as their twins (787 rows: 392 hitters, 395 pitchers; consensus the
twin's own point, median 62 days before the season's end): within RT 0.3170, R 0.3171, V5
0.2895, consensus at the twin 0.2808. RT minus twin consensus +0.0362 (CI95 +0.0083 to +0.0615);
R +0.0363 (+0.0088 to +0.0617); V5 +0.0087 (-0.0270 to +0.0435); RT minus V5 +0.0275 (-0.0031 to
+0.0578). Hitters: RT minus consensus +0.0165 (-0.0094 to +0.0400); pitchers +0.0565 (+0.0098 to
+0.1011). A development read on frames the weights were estimated on, read at a consensus that
had not seen the season: it is the timing advantage the live board has over a stale list, not a
lead over consensus as re-ranked, and the site may not say it.

### 12.6 The production fits

- RT hitters: the nested CV chose lambda infinity on the skill head, so every candidate column's
  slope is zero and the hitter skill head is V2's own (the hit tool, weight 0.051 percentile
  equivalents at w_skill 0.297); the timing head carries weight 0. RT pitchers: skill lambda
  1000, the largest weights the population translation (rank) 0.128, called-plus-swinging
  strikes 0.067, popup rate -0.067, K residual 0.055, command grade 0.055; timing unusable.
- R hitters: skill lambda 1000 (hit tool 0.050, population translation 0.034, game power 0.012,
  swing rate -0.011, positional value 0.011); timing weight 0. R pitchers as RT, the population
  translation 0.156.
- Both timing heads, fitted on the list-vintage frame, drop V2's level reached (its alpha went to
  infinity); the arrival term carries no weight on either side.

### 12.7 The board effect (live board of 2026-10-15 against data/xfv.json)

| | hitters RT | hitters R | pitchers RT | pitchers R |
|---|---|---|---|---|
| mean abs(eFV minus consensus), served then re-fit | 1.656 to 0.558 | 1.656 to 0.654 | 0.887 to 1.257 | 0.887 to 1.176 |
| eFV moved by 1 or more / 3 or more | 586 / 131 of 1,055 | 565 / 94 | 175 / 4 of 941 | 82 / 2 |
| largest move | 10.9 | 7.6 | 4.0 | 4.2 |
| served top 50 still top 50 | 30 | 35 | 43 | 43 |

Nelson Rada (consensus 43.6): served 55.6, rank 7 of 1,055; RT 46.9, rank 81 (one chip, the hit
tool +5.7 percentile points); R 49.6, rank 30 (translation +11.4, hit tool +5.6). The fifty largest
movers of each side are listed in the artifact (`board.RT.hit.top_movers` and the like).

## 13. The verdict (section 6)

| candidate | lv_dev minus V5 | vm_dev minus V5 | pooled (3,692 rows) | rule 1 | rule 2 | passes |
|---|---|---|---|---|---|---|
| R | +0.0011 | +0.0258 | +0.0066 | yes | yes | yes |
| RT | -0.0002 | +0.0326 | +0.0072 | yes | yes | yes |

Both pass; RT has the larger pooled difference and is PREPARED (D-7, a choice between two
registered candidates on the frames they were read on). The flip is built dark:
`efv5_refit.EFV_V5_REFIT_ON = False` (with `efv_w2_popmle.POP_REPAIR_ON`, test-pinned equal);
`data/efv5_refit_weights.json` stores the production fit of both passing candidates and serves RT
unless `efv5_refit.SERVE_CANDIDATE` names R. Nothing served moved.

The claim, re-derived from the prepared candidate's own development read (section 7), for the
owner to approve with the flip: "Ties PROSPX consensus on the development frames: within
Spearman difference +0.0123 (CI95 -0.012 to +0.034) on the vintage-matched frame (n 830) and
-0.0109 (CI95 -0.031 to +0.010) on list vintages 2017 to 2019 (n 2862); development reads
(2026-10-15)." Under R it reads +0.0056 (-0.019 to +0.029) and -0.0096 (-0.031 to +0.012); V5's
own (if nothing flips) -0.0203 (-0.053 to +0.013) and -0.0107 (-0.041 to +0.018). Every reading
is a tie; none may say "beats consensus".

## Note 2026-10-16 (EFV_PIT_AUDIT_FIXES)

The pitcher list-year loss in section 12.3 (RT minus V5 -0.0307, fold pit|2017 -0.0898) is a cross-fit
effect of the harness: with lv_dev pit|2017 left out, the pitcher arrival term was nonzero on 16 scored
rows of the pool (the vm_dev 2017 cohort), and the fold's arrival weight came from them (ratio 1.895,
clipped to 1.0). At the served weights the pitcher read on lv_dev is -0.0035 against V5 (CI95 -0.0107 to
+0.0037). `cross_fitted` now holds a term lit on fewer than 100 pool rows at 0
(docs/efv-v2/EFV_PIT_AUDIT_FIXES.md, data/_labs/efv5/efv5_refit_pit_reread.json). The read above is not
rerun and its artifact is unchanged.
