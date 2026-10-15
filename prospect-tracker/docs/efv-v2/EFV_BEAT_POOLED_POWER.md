# eFV against consensus, pooled for power (method, fixed before any number)

Written 2026-10-15 (task EFV_BEAT_POOLED_POWER) under the owner's decision EW3-11 of
2026-10-15 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`; asked why eFV still ties consensus
when every atlas driver helps, the owner wrote "Can we please use the drivers to beat
consensus with eFV?" and picked three paths: the timing edge, pooled power and tilted
labels). This document is path 2, POOLED POWER. It is committed ALONE, before the module
`tools/efv_beat_pooled_power.py` exists and before any pooled number is read: it fixes the
frames, the de-duplication rule, the raters, the statistic, the seed, the pass rule and what
the site may say under each verdict. Sections 1 to 11 are written before the read; the run
appends section 12 (the numbers) and section 13 (the verdict). No em-dashes. Nothing here,
in its code or in its artifacts, is cut by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`,
binding): the only groups are frame, side, list year and debut class.

## 1. Why pool

eFV v5 COMBINED serves by owner override (EW3-10). Against PROSPX consensus its published
development reads are lv_dev -0.0107 (CI95 -0.0411 to +0.0183) and vm_dev -0.0203 (-0.0528
to +0.0127), and its spent reads R-LV -0.0015 and R-VM +0.0118
(`data/_labs/efv5/efv5_combined_fit.json`, `data/_labs/efv5/efv5_combined_spent.json`).
Each single-frame interval is about +/-0.02 to +/-0.03 wide, so a real edge of +0.005 to
+0.01 would read as a tie on any one frame. This read registers ONE estimand pooled over
every development frame, so the interval narrows and the question "does eFV beat consensus"
is asked once, on the most rows the development pool holds, with its power stated first.

The development frames were used to choose the v5 COMBINED penalty (out of fold, inside each
fold's training years) and are not held out. A pass here is a development result; the copy
in section 10 says so.

## 2. The frames

### 2.1 Pooled (the estimand)

- **lv_dev**: the list-vintage frame (frame version lv1_v2) at list vintages 2017, 2018 and
  2019, exactly the rows of the DS-16 development read and of the v5 COMBINED development fit
  (2,862 rows: 1,465 hitters, 1,397 pitchers). Outcome: W3, WAR over the first three MLB
  seasons (0 if no debut within three seasons of the list year), on the frozen fWAR label the
  v5 COMBINED fit read (`efv_labels.provider() == "fwar"`; the tool refuses any other).
- **vm_dev**: the vintage-matched frame (frame version vm2) at debut cohorts 2017 to 2023,
  exactly the rows of the DS-16 read and of the v5 COMBINED fit (830 rows: 406 hitters, 424
  pitchers). Outcome: career WAR to date on the same label.

### 2.2 No other development frame is admissible (stated before the read)

- **Earlier list vintages (2011 to 2016).** They are in `efv_vintage_frame.DEV_VINTAGES`
  but they are the years V2's registered head weights and consensus combiner rule were fit
  on (`efv_v2_model.V2_FIRST_SCORED_YEAR` = 2017; the gate's `rule_last_year` = 2016). Scoring
  them would score V2 and v5 COMBINED in sample. Not pooled.
- **The 2024 debut cohort.** Not resolved by the label pool (`source_backtest._resolved_years`
  ends at 2023). Not pooled. The 2025 and later cohorts are R-VM and never enter here.
- **List vintages 2020 and 2021.** R-LV. Never enter the pooled estimand (section 7).
- **The timing edge's as-published frame (EFV_BEAT_TIMING_EDGE).** The spec says to pool it
  under the same rule if its registration exists at this task's HEAD. At HEAD 1aca3796 no
  document, tool or commit registers it (searched: `docs/`, `tools/`, every `*.py`, the git
  log of every branch for TIMING_EDGE and as-published). Not pooled.

### 2.3 The de-duplication rule (fixed here)

A player who appears in both frames keeps his lv_dev rows; his vm_dev row is dropped. The
match is on `player_key` (the frames' own id). Reason: each vm_dev player has one row and an
lv_dev player up to three (one per list year), so dropping the vm_dev side drops the fewest
rows, and the lv_dev rows are the reads made before the player's debut. Players who appear
only in vm_dev keep their vm_dev row. Inside lv_dev a player read in two or three list years
keeps every row, as the registered lv_dev frame does; the player-clustered interval
(section 5) carries that dependence.

Two disclosed sensitivities are computed and reported beside the estimand; neither enters the
pass rule: (a) the opposite rule (keep the vm_dev row, drop that player's lv_dev rows), (b) no
de-duplication.

## 3. The raters

All four are scored on the SAME de-duplicated rows; a row enters only when all four carry a
score.

1. **eFV v5 COMBINED** (served). Its out-of-fold development order on each frame: the
   combined fit per (frame, side, fold) of `efv5_combined.Fits` on the inputs of
   `efv5_combined.build_dev`, with the tracking-era head blended exactly as the development
   fit applies it, the order index (the score V2's own statistic reads, not the mapped grade).
   Parity guard, checked before any pooled number: the recomputed per-frame v5 COMBINED minus
   consensus and minus V2 within deltas must equal the fit artifact's
   (`data/_labs/efv5/efv5_combined_fit.json`) to 1e-4 on both frames, else nothing is read.
2. **eFV V2**: its order index on the same rows (already on the frame rows).
3. **eFV v1**: the DS-16 development read's v1 score (`tools/efv_v2_dev_read.v2_lv_dev` and
   `v2_vm_dev`), joined on (side, year, player_key). Parity guard: on every joined row the
   DS-16 rows' V2 order, consensus grade and outcome must equal the v5 COMBINED rows' (else
   nothing is read), and the join must cover every row.
4. **PROSPX consensus**: the consensus grade on the row (the comparator).

## 4. The statistic (the estimand)

For a rater r the pooled within statistic is

    W(r) = sum over groups g of n_g x rho_g(r)  /  sum over groups g of n_g

where a group is (frame, side, year): (lv_dev, side, list vintage) or (vm_dev, side, debut
cohort), so the codes of the two frames never merge; rho_g(r) is the Spearman rho (ties
averaged) of r's own score against the frame's outcome on the group's rows; n_g is the
group's row count; a group enters when it holds at least 20 rows of the de-duplicated pool
(`efv_v2_stat.MIN_GROUP_ROWS`), and a paired comparison counts a group only when both raters
have a rho there (`efv_v2_stat._within_pair`, the registered DS-15 statistic, unchanged).
The label scales of the two frames differ (W3 against career WAR); a within-group rank
correlation does not read the scale, so the groups pool.

THE ESTIMAND: D = W(eFV v5 COMBINED) minus W(PROSPX consensus), every group of both frames,
both sides (pooled over sides). Also reported, never in the pass rule: the same difference for
V2 and v1 against consensus, v5 COMBINED against V2, and each by side (hitters, pitchers).

## 5. The intervals and the power

- **Primary interval**: paired and player-clustered (E_cond: the scores are fixed, players are
  resampled with replacement, every row of a drawn player comes with him, across both frames),
  the resampler of `source_backtest` (`_cluster_layout` / `_cluster_draw`), B = 4000 draws,
  seed 20261016. In a draw a group whose rho is undefined for either rater is left out for both
  (the DS-15 rule).
- **Club-clustered sensitivity**: the same statistic with clubs resampled instead of players.
  A row's club is the org on the latest board point of the player dated inside the row's read
  window [year-01-01, year-05-01) (`source_backtest`'s preseason window), else the latest
  point dated before the window's end, else `UNK`. Same B and seed.
- From each set of draws: lb95 = the 5th percentile (one-sided 95 percent lower bound),
  ub95 = the 95th, ci95 = the 2.5th and 97.5th percentiles, sd, and mde95 = 1.645 x sd (the
  one-sided minimum detectable effect, `docs/EFV_GATE_STANDARD.md`).
- **The power is reported first**: the mde95 of D under both clusterings is printed and
  written before the point estimate of D in the artifact, the log and the results document.

## 6. The pass rule

**PASS** when the pooled D's one-sided 95 percent lower bound is above 0 under BOTH the
player-clustered interval and the club-clustered sensitivity. Otherwise **FAIL**, worded
"trails" when the player-clustered ub95 is below 0 and "ties" in every other case.
Nothing else enters the rule: not the by-side legs, not V2 or v1, not the sensitivities, not
the spent frames, not the 2026 holdout.

## 7. The spent frames (corroboration only)

R-LV (list vintages 2020 and 2021, `lv_res`) and R-VM (the 2025 debut cohort, `vm_pros`)
were read before (v3 on 2026-10-08, v4, v5, v5 COMBINED on 2026-10-15) and are SPENT. They
are read at most ONCE more here, through `efv5_combined.build_spent` on the gate's committed
sha `e7931ce4e13110eebb53555bff455ff13ca7c502` (as every spent read opened them), labelled
SPENT, with the same pooled statistic over the two spent frames (the de-duplication rule of
2.3 with lv_res in the place of lv_dev), the same B and seed, v5 COMBINED and V2 against
consensus (v1 is not built on the spent frames by this pipeline and is not reported there).
A pass there corroborates and never stands as the claim; a failure there is printed beside a
development pass.

## 8. The 2026 holdout (corroboration only)

EW3-13: the 2026 season was the one-time holdout read by EFV_2026_HOLDOUT_READ and is spent.
This task does not recompute it; it reads the record `data/efv_2026_holdout.json` (leg
`war2026|spearman|pooled|efv_v5_combined-consensus` of frame `list`: delta, player and club
lb95) and prints it beside the pooled development verdict, for corroboration only.

## 9. What does not happen

- No fit, penalty, weight, flag, gate constant or served number changes. The v5 COMBINED folds
  are refit in memory exactly as the development fit fitted them (the parity guard proves it).
- No projections retrain; `backtest.run_backtest` is not run; the fWAR label epoch's runbook
  is not touched.
- Nothing is stratified, counted or averaged by consensus-FV level; the test scans the module.
- Nothing served moves under either verdict without the owner's answer (section 10).

## 10. What the site may say

- **FAIL (ties or trails).** Nothing changes. The copy keeps "ties consensus". The results
  document may say: "Pooled over every development frame (N rows), eFV v5 COMBINED minus
  PROSPX consensus reads D (one-sided 95 percent lower bound L); the pooled read could detect
  an edge of M or larger, and it does not find one."
- **PASS.** Nothing changes until the owner answers the flip question this task writes
  (OWNER_QUESTION.md in the task's output directory, options: keep "ties consensus"; print a
  development-labelled line on Source Comparison; print it in the eFV copy too). The only copy
  allowed after a yes is: "Pooled over every development frame (N rows, list years 2017 to
  2019 and debut classes 2017 to 2023), eFV ranks prospects' later WAR better than PROSPX
  consensus: +D within-year Spearman, one-sided 95 percent lower bound +L. These frames were
  used to build eFV; on the held-out 2026 season it reads +H against consensus (lower bound
  B)." The words "beats consensus" are allowed in that line only; the spent frames and the
  2026 holdout are quoted beside it as they read.

## 11. Outputs

- `tools/efv_beat_pooled_power.py` (the read; refuses to run twice over an existing
  artifact), `data/_labs/efv5/efv_beat_pooled_power.json` (off the webroot: `data/_labs/`
  ships in neither deploy consumer), `test_efv_beat_pooled_power.py`,
  `docs/efv-v2/EFV_BEAT_POOLED_POWER_RESULTS.md` (plain language for the owner), and sections
  12 and 13 appended below.
