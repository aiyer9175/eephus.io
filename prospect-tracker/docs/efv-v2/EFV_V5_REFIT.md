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
