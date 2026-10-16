# eFV tool inputs on eTools (EFV_ETOOLS_REWEIGHT): the correlation recheck and the re-weight, fixed before any number

Registration status: REGISTERED

Written 2026-10-16 (task EFV_ETOOLS_REWEIGHT) under the owner's decision EW3-26 of 2026-10-15
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), verbatim: "We should also recheck correlations
for tool weights in eFV using eTools once we're done with all of them, since we're making them
better. Make sure to re-weight as well." EW3-28 (the eTools composite) will read the tool
weights this task re-derives; EW3-31 asks that this build on the pitcher head as amended by
EFV_RELIEVER_ADJ.

This document is committed ALONE, before the module `efv_etools_reweight.py` exists and before
any number of this read is computed. Sections 1 to 11 are written before the read; the run
appends section 12 (the numbers) and section 13 (the verdict). No em-dashes. Nothing here, in
its code or in its artifacts, is cut by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`,
binding): the groups are side, list year or decision year, fold, board year, position group,
role and age band. Only the development frames are read (lv_dev, vm_dev); no reserved row
(R-LV list vintages 2020 and 2021, R-VM debut cohorts 2025 and later) is built or scored, and
`backtest.run_backtest` is never called.

## 0. Preconditions (checked before this document was written)

- ETOOLS_FLIP_PREP is done: the final eTools are the re-centred construction (amendment 2,
  read dd33ad7d), PROMOTION-CLEAR on the any-level label and the IPW read, with the BA weight
  fix; they are the shown grade site wide since ETOOLS_SITEWIDE_FLIP (135a0912). The served
  eTools and their admitted sub-drivers are `data/etools.json`: eHIT (translated K%, P/PA PAR,
  translated BABIP), ePOW (translated ISO, fly-ball rate), eSEL (pitch-level swing rate), eBAT
  (pitch-level contact rate), eFB (translated K%, P/BF, swinging-strike rate), eCMD (translated
  BB%, first-pitch strike rate, P/BF PAR). This read uses exactly those lists.
- EFV_FIX_B_REFIT is done and serving: the registered re-fit variant RT
  (`docs/efv-v2/EFV_V5_REFIT.md`, read 1b8f3f58, flipped by the owner at 8ae40518,
  `efv5_refit.EFV_V5_REFIT_ON` True). Its served weights: hitters w_skill 0.297, w_time 0;
  pitchers w_skill 1.0, w_time 0. Its committed development read: within Spearman 0.1683 on
  lv_dev (n 2,862) and 0.3937 on vm_dev (n 830).
- EFV_RELIEVER_ADJ (EW3-31) is read and NO candidate passed its rule
  (`docs/efv-v2/EFV_RELIEVER_ADJ_RESULTS.md`); nothing was prepared to flip, so the pitcher head
  this task builds on is RT's own, unamended. Only the usage label reached the card.
- EFV_X5's older list vintages: the list sources of 2006 to 2010 carry no tool grade (an
  outcome-blind inventory of `prospects.db`: zero snapshots with tool grades dated before 2011;
  the first are 152 MLB Pipeline snapshots of 2011), and the X5 rows were kept as a lab artifact
  under X5-Q1's default (a), not adopted into the frame. So no eTool and no consensus tool grade
  exists on any X5 row of 2006 to 2010, and X5 adds no row to this read. Stated, not read.

## 1. What is compared

The model is eFV v5 COMBINED as re-fitted by EFV_FIX_B_REFIT, variant RT (A1 population norms
repair, A2 dark columns dropped, A3 timing head on the list-vintage pool, A4 live-timing twin
rows, A5 the population column as a within-group rank), with its fold design, its penalty
grid, its nested lambda rule, its DS-06 admission, its output map and the frozen fWAR label
`fwar@2026-10-02-0341299c20ec`. This task changes ONE thing: which value sits in each
consensus tool input of the SKILL head. The timing head reads no tool input and is RT's.

The comparator RT is recomputed in the same run on the same rows and must reproduce the
committed development read (within 0.1683 on lv_dev, 0.3937 on vm_dev, each within 1e-4)
before anything is read; the run refuses otherwise.

## 2. The eTool on an eFV row

### 2.1 The construction

For tool T with admitted sub-drivers J_T (section 0), a fit Phi = (lines a_j, b_j; slopes c_j)
is `etools.etool_fit` on the eTools frame of T (board years 2011 to 2019 and 2022 to 2024,
`etools.DEV_YEARS`, built by `etools.load_board`, `build_universe`, `attach_candidates`
(last season 2023) and `attach_labels`, the look's own construction) restricted to a training
mask (2.3). On an eFV row with an OBSERVED consensus grade g for T and sub-driver values Z_j:

    eT = clip(g + sum over the j the row carries of c_j (Z_j - a_j - b_j g - delta_j), 20, 80)

where delta_j is amendment 2's re-centring (F1.5): the mean residual Z_j - a_j - b_j g over the
cohort's rows carrying j, minus the mean residual over the fit's training rows carrying j. The
cohort is the eFV rows that share the fit and the board year (2.3). A row without an observed
g keeps the consensus slot's own value (the imputation the head already applies); a row with g
and no sub-driver keeps g. Every value is unrounded.

The sub-driver values Z_j of an eFV row are `etools.attach_candidates` on (mlbam id, board year
b), the same function the eTools frame reads, so a frame row and an eFV row of the same player
and board year carry the same Z. The board year of an eFV row is the season after the minor
league season its read sees: list vintage V for a list-vintage row (b = V); read season
R = `efv_w2_milb.last_readable_season(decision year, cutoff)` plus one for a matrix row, its
live-timing twin (same R) and a production row. Every Z reads seasons before b only (the
guards of `attach_candidates` raise otherwise). A matrix row whose b is 2020 or 2021 (a vm_dev
row of decision year 2020 or 2021) gets its Z from the same function; the eTools frame itself
never contains board years 2020 or 2021 and no label of those board years is read.

The observed g of each slot: the hit slot reads the row's own consensus hit grade before
`efv_model._vec`'s imputation (the list-vintage frame row's prior block, the matrix row, the
twin's consensus point, the live matrix row); the game power and command slots read the
scouting column's own value (`efv_w2_scout`, None when unobserved); the fastball slot reads the
row's consensus fastball grade before imputation.

### 2.2 Live rows (the served path, dark)

On the live board the eTool is the served one (`data/etools.json`: the look's final fit on every
development board year, re-centred on the live cohort). With the served consensus gc and the
served re-centred contributions p_j of the j the player carries, the value at the slot's own g is

    eT = clip(g + sum_j p_j - (g - gc) * sum_j c_j b_j, 20, 80)

(identical to 2.1 at g = gc). A player not in `data/etools.json` keeps g.

### 2.3 The fold design (nested inside the development folds, forward chained)

No eTool value read by a fold depends on a label of that fold's test players or of a later
board year than the fold:

- lv_dev fold V (2017, 2018, 2019): test rows use Phi fitted on board years before V, every
  player of the fold's test rows removed. A training row of list vintage Y < V uses Phi fitted
  on board years before V except Y, the fold's test players and the vintage-Y training players
  removed (an out-of-fold value: no training row's eTool saw its own label).
- vm_dev fold Y (decision years 2017 to 2023): test rows use Phi on board years before Y,
  the fold's test players removed; a training row (twins included) of board year b uses Phi on
  board years before Y except b, the fold's test players and the board-year-b training players
  removed.
- the production fit (the served flag): a training row of board year b uses Phi on every
  development board year except b, the board-year-b training players removed; the live rows use
  2.2.

Disclosed: the eTools frame's labels (MLB K% and the like among debuts, translated upper-minors
lines) are realized after the board year, as the eFV label itself is; the forward chaining is on
the row's year, the convention of every development fold.

## 3. Part 1: the correlation recheck (descriptive, decides nothing)

On the scored test rows of lv_dev and vm_dev, each row's eTool from its fold's test fit (2.3)
beside the consensus grade it replaces (the slot's g), on the rows that carry g:

- A. within (side, list year) Spearman of the eTool with the frame's label and of the consensus
  grade with it (`efv_v2_stat`'s within, groups of 20 or more), the eTool minus consensus grade
  difference with a paired E_cond CI95 (B 2000, seed 20260906, player-clustered);
- B. the incremental gain over consensus FV: a linear score s_X = u_c + b z(X) with b the OLS
  slope of u_y on [1, u_c, z(X)] fitted on the frame's other folds' scored rows (leave one fold
  out, z standardized on those rows); within Spearman of s_X minus that of consensus FV, for X
  the eTool and X the consensus grade, and s_eTool minus s_consensus-grade, each with its paired
  E_cond CI95;
- by position group (hitters C, IF, OF as the frames' cells; pitchers SP and RP by the last
  season's starts share before the board year, `etools.attach_candidates`' group) and by age
  band (young, average, old: terciles of age for level within side over the frame's scored rows
  that carry it), each cell scored when it holds 20 or more rows; never by consensus-FV level.

The tools: eHIT, ePOW, eFB, eCMD (the four with an eFV slot, 4.1); eRAW (consensus raw power,
the row's raw power grade) and eSPD (consensus speed, the row's speed grade) as sensitivity
rows, with the look's admitted sub-drivers (translated ISO; level-relative stolen bases per PA);
eSEL and eBAT on the vm_dev rows whose (player, board year) sits in their eTools frame (their
consensus grades start on the 2021 boards and the eFV row block carries neither tool): read only
where a (side, year) group reaches 20 rows, else reported as not computable with the count.

## 4. Part 2: the re-weight

### 4.1 The slots

| slot in RT's skill head | what it holds in RT | in the eTool configurations |
|---|---|---|
| `tool_hit` (V2 key, hitters) | consensus hit grade | eHIT (the V2 key slot: DS-06 admission and V2's alpha as before) |
| `w2s_game_pwr_hit` (candidate column) | consensus game power future grade | ePOW, sign bound +1 |
| `w2s_cmd_pit` (candidate column) | consensus command future grade | eCMD, sign bound +1 |
| `t5_pit_AAA_all_all_fb_fut` (candidate column) | consensus fastball future grade, z inside the Triple-A cell | removed; a new column `e5_fb_pit` holds eFB on every pitcher with a fastball grade, sign bound +1 |

The fastball slot widens from the Triple-A cell to every graded pitcher because the eTool is
defined on every graded pitcher; the null configuration EC (4.2) carries the same widened slot
with the consensus grade, so the widening is measured apart from the eTool. Every other column
and key of RT is unchanged. V2 keys carry no sign bound in RT's machinery; eHIT keeps that (the
DS-06 one-sign admission stands in for it). The candidate eTool columns are bounded at +1 (a
higher grade is the better outcome, the direction every eTool was built in).

**The X1 rates.** EW3-26 asks that the X1 rates the eTools already contain leave the head so a
stat line is not counted twice. RT's head holds no X1 column (no k_rw, bb_rw, iso_rw or
babip_rw). It does hold raw strikeout and first-pitch strike rates that measure the same line
as an eTool sub-driver; the variant ED removes those (4.2).

### 4.2 The configurations

| id | what | role |
|---|---|---|
| RT | the served re-fit, recomputed | the comparator (parity, section 1) |
| E | RT with the four slots of 4.1 holding eTools | primary candidate |
| ED | E minus the columns that carry the same rate as an admitted eTool sub-driver: hitters the V2 contact key (strikeout rate relative to level) and `g5_hit_A_all_all_k_pct`, `g5_hit_A_young_all_k_pct` (eHIT's translated K%); pitchers `g5_pit_A_all_all_k_pct`, `g5_pit_A_young_all_k_pct`, `g5_pit_A_all_SP_k_pct` (eFB's translated K%) and `w2p_fstrike_p` (eCMD's first-pitch strike rate) | registered variant (the double-count removal) |
| EC | E's structure with the consensus grade g in every eTool slot (the eTool shift set to 0) | null comparator: what the restructuring does without the eTools |
| EP | E with each row's eTool shift (eT - g) permuted among the rows of its (side, fit, board year) cohort that carry g, seed 20261017 | null comparator: the eTool shift with the player link broken |
| ES | E plus eSPD in the `tool_speed` V2 key slot | sensitivity (eSPD did not pass its look); decides nothing |

Each configuration's skill head is RT's joint penalized fit (`efv5_combined.joint_skill`) with
its own lambda chosen by RT's nested forward-chained rule (`select_lambda`) inside each
development fold's training rows, so every tool's weight is re-estimated jointly with every
other column of the head, out of fold. The training rows, twins, timing head and population
rank are RT's.

## 5. The weights (EFV_FIX_B_REFIT's fold design, unchanged)

Per side and configuration, `efv5_refit`'s section 4 exactly: forward-chained heads, DS-08's OLS
u_y ~ 1 + u_c + e_skill + e_time pooled over every development fold of both frames,
w_skill = clip(c_skill / c_uc, 0, 1), w_time = clip(c_time / c_uc, 0, 1); served weights from the
pool of every fold; the read's weights cross-fitted (each fold scored with the pool that leaves
it out); a player-clustered bootstrap of the ratios, B 2000, seed 20261016. Each tool's weight is
reported as the production head's standardized slope, its percentile-equivalent weight
(`efv5_combined.weights_table`) and that times w_skill, for RT (old) and for each candidate
(new).

## 6. The statistic

The program's primary: within (side, list year) Spearman of the order with the frame's label,
size-weighted over groups of 20 or more rows, pooled over sides, per side beside it; paired
E_cond intervals (B 2000, seed 20260906, player-clustered) through
`tools/efv_v3_backtest.frame_block`. Raters on the scored rows: every configuration, PROSPX
consensus, MLB Pipeline, FanGraphs. Secondary: pooled Spearman after the output map and
contributor AUC. Position-group cells (hitters C, IF, OF; pitchers one cell), reported. Against
consensus each candidate's difference is reported with its CI95 and one-sided 95 percent lower
bound on each frame and pooled over the two frames by row count.

## 7. The ship rule (fixed here, before any number)

A candidate C in {E, ED} passes when BOTH hold (point estimates, within Spearman pooled over
sides; EFV_BEAT_POOLED_POWER's estimand, the two development frames pooled by row count):

1. it beats RT on the pooled development frames: (n_lv_dev x (C minus RT on lv_dev) +
   n_vm_dev x (C minus RT on vm_dev)) / (n_lv_dev + n_vm_dev) > 0;
2. it trails RT by no more than 0.005 on either frame: C minus RT >= -0.005 on lv_dev and on
   vm_dev.

If both pass, the one with the larger pooled difference is prepared (a choice between two
registered candidates; disclosed).

**The attribution check (reported with the verdict; it does not block the dark build).** A pass
is called an eTool gain only when the prepared candidate also beats its own null EC by the same
pooled estimand (> 0) and beats EP (> 0). If the rule passes and either check fails, the result
is written as a restructuring effect, and the owner question's default is NOT to flip.

## 8. On a pass, and on a fail

On a pass: the flip is PREPARED DARK and the owner flips it.
`efv_etools_reweight.EFV_ETOOLS_REWEIGHT_ON = False`; with it True (and the re-fit's flag on),
`efv_v2_serve.production_models` serves the prepared candidate's production fit stored in
`data/efv_etools_reweight_weights.json`, the live rows carrying the eTools of 2.2 in the slots of
4.1. With the flag False every served artifact is byte identical to the code before this task.
`docs/efv-v2/EFV_ETOOLS_REWEIGHT_OWNER_QUESTION.md` states the board effect on the live board as
of the run date against `data/xfv.json`: the 50 largest movers by absolute change in eFV per side,
the counts moved by 1 or more and 3 or more, the served top 50 kept, and the mean absolute eFV
minus consensus per side before and after (eFV printed to one decimal, rounded to nearest).
Whether or not it passes, the re-weighted tool arm (the slots of 4.1 and the eTool construction
of section 2, `efv_etools_reweight.etool_inputs`) is handed to EFV_X3_POOLED_MODEL as its tool
inputs, and each tool's re-derived weight is the input EW3-28's eTools composite reads.

On a fail: nothing is prepared to serve; the read and the weights are recorded and the results
say what fell short.

## 9. The artifacts

- `data/_labs/efv5/efv_etools_reweight_fit.json`: the parity receipt, the eTool fit receipts
  (per fold and board year: rows, players removed, c), the Part 1 tables, every configuration's
  development read, weights and intervals, the ship reading and attribution check, the
  production driver tables, the board effect.
- `data/efv_etools_reweight_weights.json`: the production fit of each candidate (read by the
  serve path only when the flag is True).
- `data/efv_progress.json`: two development rows (model `efv_etools_reweight`, frames lv_dev and
  vm_dev, role development, adjudicates nothing).
- Code `efv_etools_reweight.py`, tests `test_efv_etools_reweight.py` (fixtures only: the eTool
  formula, the fold masks, the live formula against served values, a planted shift recovered by
  the joint fit, the permutation null, the flag routing, the source scan).
- `docs/efv-v2/EFV_ETOOLS_REWEIGHT_RESULTS.md` (plain language: every tool's old and new weight
  and correlation).

## 10. Defaults applied (the owner may choose differently)

- D-1 the eTool construction is the served one (re-centred, full admitted lists), applied at
  each slot's own consensus value g.
- D-2 eTool fits forward chained by board year inside each development fold, out of fold for
  training rows (2.3).
- D-3 the fastball slot widened to every graded pitcher, measured against EC.
- D-4 ED's removal list is the exact-rate matches of section 4.2; no X1 column exists to remove.
- D-5 eSEL and eBAT enter no slot (no consensus input to replace, no grade before the 2021
  boards); eSPD only as ES; eRAW only in Part 1.
- D-6 if E and ED both pass, the larger pooled difference is prepared; the attribution check
  sets the owner question's default.

## 11. Bans and hygiene

- No reserved row: the development build raises on list vintages 2020 and 2021 and stops before
  the 2025 cohort (`efv_vintage_frame`); the eTools frame is `etools.DEV_YEARS` only.
- No statistic by consensus-FV cell anywhere; the test scans the module source.
- No projections retrain; the fWAR label epoch's runbook is untouched; `backtest.run_backtest`
  is never called.
- The served grade does not move in this task: every new path is behind
  `EFV_ETOOLS_REWEIGHT_ON = False`.

## 12. The read (appended by the run, 2026-10-16; development frames)

Run: `python -u efv_etools_reweight.py --prep --cache <scratch>` (builds and fits, no
statistic; code 5350c182) then `python -u efv_etools_reweight.py --run --cache <scratch>`
once (artifact `data/_labs/efv5/efv_etools_reweight_fit.json`, generated 2026-10-16T20:09:12Z;
E_cond B 2000, seed 20260906; weight bootstrap B 2000, seed 20261016). No reserved row was
built; nothing was cut by consensus-FV level.

**Disclosures.**
- The label: the frozen fWAR vintage's id reads `fwar@2026-10-02-57bf90f7143e`, not the
  `0341299c20ec` this document names: c7dacaaa added plate appearances to every hitting row of
  the vintage with every published value unchanged, which moves the id. The RT parity below
  (exact to four places on both frames) confirms the scored labels are the re-fit's.
- Section 3's eSEL and eBAT rows: the first write counted the matched vm_dev rows but did not
  read them (a harness omission). The registered read of those rows was run once afterwards
  (`--part1-frame`, the same artifact, key `part1_frame_tools_read`); it decides nothing.

### 12.1 Receipts

- RT parity: recomputed within 0.1683 (lv_dev) and 0.3937 (vm_dev), the committed read's own;
  RT's production fit, re-fitted here, reproduces the served board exactly (0 of 1,055 hitters
  and 0 of 941 pitchers move).
- The eTools frame: rebuilt with the look's universe (8,898 rows) and every look d of the
  eight tools reproduced within 5e-5 before any eFV row was touched.
- Row contexts: 14,877 rows (frame folds, production rows, twins); 22,257 observed-grade checks
  against the rows' own features, 0 mismatches; the sub-driver values of an eFV row equal the
  eTools frame's on every shared (player, board year): 38,035 values compared, 0 differ.
- 56 eTool fits (tool, board years, players out), each recorded with its rows and slopes.
- Coverage on the scored test rows (rows with an observed grade; rows whose eTool differs from
  it): lv_dev hit 1,400 / 1,299, game power 1,397 / 1,284, fastball 1,349 / 1,271, command
  1,342 / 1,274; vm_dev hit 479 / 475, game power 435 / 428, fastball 538 / 529, command
  509 / 504. Mean eTool minus grade within 0.12 of 0 everywhere (the re-centring).

### 12.2 Part 1: the correlation recheck

Within (side, year) Spearman with later WAR, eTool against the consensus grade it replaces
(A), and the incremental gain over consensus FV of each (B), on the scored rows that carry the
grade (E_cond CI95):

| frame | tool | n | eTool | consensus grade | A: difference (CI95) | B: eTool gain | B: grade gain | B: difference (CI95) |
|---|---|---|---|---|---|---|---|---|
| lv_dev | eHIT | 1,400 | 0.089 | 0.131 | -0.042 (-0.087 to +0.003) | +0.0013 | -0.0004 | +0.0017 (-0.004 to +0.008) |
| lv_dev | ePOW | 1,397 | 0.075 | 0.075 | +0.000 (-0.018 to +0.018) | -0.0117 | -0.0122 | +0.0005 (-0.002 to +0.003) |
| lv_dev | eFB | 1,349 | -0.013 | -0.038 | +0.025 (-0.025 to +0.071) | +0.0058 | +0.0072 | -0.0014 (-0.007 to +0.004) |
| lv_dev | eCMD | 1,342 | 0.118 | 0.147 | -0.029 (-0.053 to -0.005) | +0.0082 | +0.0111 | -0.0029 (-0.006 to +0.000) |
| lv_dev | eRAW (sens.) | 1,127 | 0.045 | 0.041 | +0.003 (-0.003 to +0.009) | -0.0065 | -0.0065 | -0.0001 (-0.001 to +0.001) |
| lv_dev | eSPD (sens.) | 1,400 | 0.018 | 0.010 | +0.008 (-0.007 to +0.022) | +0.0023 | -0.0048 | +0.0071 (-0.003 to +0.016) |
| vm_dev | eHIT | 406 | 0.194 | 0.299 | -0.106 (-0.165 to -0.048) | +0.0067 | +0.0065 | +0.0002 (-0.010 to +0.010) |
| vm_dev | ePOW | 403 | 0.122 | 0.123 | -0.000 (-0.031 to +0.030) | +0.0109 | +0.0165 | -0.0055 (-0.012 to -0.000) |
| vm_dev | eFB | 423 | 0.127 | 0.095 | +0.032 (-0.032 to +0.097) | -0.0102 | -0.0163 | +0.0061 (-0.014 to +0.026) |
| vm_dev | eCMD | 422 | 0.165 | 0.191 | -0.026 (-0.054 to -0.002) | +0.0046 | +0.0063 | -0.0018 (-0.008 to +0.004) |
| vm_dev | eRAW (sens.) | 405 | 0.055 | 0.049 | +0.006 (-0.015 to +0.028) | +0.0143 | +0.0144 | -0.0001 (-0.005 to +0.005) |
| vm_dev | eSPD (sens.) | 406 | 0.114 | 0.097 | +0.018 (-0.011 to +0.046) | +0.0052 | +0.0040 | +0.0012 (-0.006 to +0.009) |
| vm_dev 2023 | eSEL | 73 | 0.149 | 0.120 | +0.029 (-0.027 to +0.083) | not derived (one group, under the floor gate) | | |
| vm_dev 2023 | eBAT | 73 | -0.011 | -0.043 | +0.033 (-0.040 to +0.111) | not derived | | |

eSEL and eBAT: the 2022 decision-year group (89 rows) has no earlier board year to fit on, so
only the 2023 group (73 rows, fit on board year 2022) is read. By position group and age band
(the artifact's `part1.*.by_position_group` and `by_age_band`): no cell's B difference has an
interval above zero (the overall vm_dev ePOW one lies below it); eHIT's A difference is negative in every hitter cell of 100 or more rows
but catchers on lv_dev (old hitters on lv_dev -0.066, CI95 -0.133 to -0.003; infielders on
vm_dev -0.113, CI95 -0.207 to -0.024).

### 12.3 The weights (section 5; per side, forward-chained heads, both frames pooled)

| config | hitters w_skill (OLS ratio; CI95) | pitchers w_skill (ratio; CI95) | w_time |
|---|---|---|---|
| RT | 0.297 (0.297; 0.065 to 0.594) | 1.0 (1.053; 0.534 to 1.918) | 0, 0 |
| E | 0.218 (0.218; 0.010 to 0.480) | 0.884 (0.884; 0.413 to 1.629) | 0, 0 |
| ED | 0.226 (0.226; 0.015 to 0.492) | 0.886 (0.886; 0.413 to 1.636) | 0, 0 |
| EC | 0.296 | 0.956 | 0, 0 |
| EP | 0.267 | 0.939 | 0, 0 |
| ES | 0.229 | 0.884 | 0, 0 |

Each tool's weight in the production fit (percentile-point equivalents, w_skill included; RT
old, E new):

| tool slot | RT (consensus input) | E (eTool) | ED |
|---|---|---|---|
| hit (V2 key) | 0.0507 (admitted) | 0 (eHIT refused by DS-06's one-sign rule) | 0 (refused) |
| game power | 0 (the hitter head at lambda infinity) | 0.0091 | 0.0094 |
| fastball | 0.0172 (Triple-A cell) | 0.0658 (every graded pitcher) | 0.0673 |
| command | 0.0551 | 0.0561 | 0.0535 |

eHIT in the hit key passes DS-06's admission in 1 of 7 vm_dev folds and 2 of 3 lv_dev folds;
the consensus hit grade in 7 of 7 and 0 of 3. With the hit key refused, E's hitter head takes
lambda 1000 (RT's took infinity) and spreads small weights over the stat columns.

### 12.4 The development read (within (side, list year) Spearman, pooled over sides)

| frame | n | RT | E | ED | EC | EP | ES | consensus | Pipeline | FanGraphs |
|---|---|---|---|---|---|---|---|---|---|---|
| lv_dev | 2,862 | 0.1683 | 0.1632 | 0.1635 | 0.1638 | 0.1639 | 0.1635 | 0.1792 | 0.2034 | 0.1714 |
| vm_dev | 830 | 0.3937 | 0.3916 | 0.3926 | 0.3915 | 0.3946 | 0.3925 | 0.3814 | 0.3816 | 0.3363 |

| comparison | lv_dev (CI95) | vm_dev (CI95) | pooled |
|---|---|---|---|
| E minus RT | -0.0052 (-0.0100 to -0.0003) | -0.0021 (-0.0157 to +0.0113) | -0.0045 |
| ED minus RT | -0.0049 (-0.0098 to -0.0001) | -0.0011 (-0.0155 to +0.0122) | -0.0040 |
| E minus EC (the eTool shift) | -0.0006 (-0.0038 to +0.0027) | +0.0001 (-0.0133 to +0.0135) | -0.0005 |
| E minus EP | -0.0008 (-0.0030 to +0.0015) | -0.0030 (-0.0144 to +0.0085) | -0.0013 |
| EC minus RT (the restructuring) | -0.0046 (-0.0080 to -0.0011) | -0.0022 (-0.0066 to +0.0019) | |
| E minus consensus | -0.0161 (-0.0348 to +0.0031; LB -0.032) | +0.0102 (-0.0105 to +0.0288; LB -0.006) | -0.0101 |
| ED minus consensus | -0.0158 (-0.0348 to +0.0035; LB -0.032) | +0.0113 (-0.0090 to +0.0299; LB -0.005) | -0.0097 |
| RT minus consensus | -0.0109 (-0.0311 to +0.0098) | +0.0123 (-0.0123 to +0.0343) | |
| ES minus E | +0.0003 (-0.0004 to +0.0010) | +0.0009 (-0.0002 to +0.0024) | |

Per side, E minus RT: lv_dev hitters +0.0009 (-0.0048 to +0.0072), pitchers -0.0116 (-0.0191 to
-0.0039; EC minus RT -0.0093 of it, the eTool shift -0.0023); vm_dev hitters -0.0035, pitchers
-0.0007. Secondary (pooled after the map; AUC), E minus RT: lv_dev -0.0018 and -0.0014, vm_dev
+0.0024 and -0.0028.

### 12.5 The board (descriptive; no candidate passed)

E's production fit against `data/xfv.json`: hitters 175 of 1,055 move by a grade or more
(34 by three or more, largest 8.9), mean |eFV minus consensus| 0.559 to 0.380; pitchers 48 of
941 (1 by three or more), 1.259 to 1.180. Nothing is prepared, so nothing here is proposed.

## 13. The verdict (section 7)

| candidate | lv_dev minus RT | vm_dev minus RT | pooled (3,692 rows) | rule 1 | rule 2 | passes |
|---|---|---|---|---|---|---|
| E | -0.0052 | -0.0021 | -0.0045 | no | no | no |
| ED | -0.0049 | -0.0011 | -0.0040 | no | yes | no |

Neither candidate passes; nothing is prepared and no dark serve path is built
(`EFV_ETOOLS_REWEIGHT_ON` stays False, `data/efv_etools_reweight_weights.json` records NOT
PREPARED). The attribution check reads no eTool gain either: against EC and EP the eTool shift
is -0.0005 and -0.0013 pooled. The loss against RT is the restructuring (mostly the pitcher
fastball slot widened from the Triple-A cell, lv_dev pitchers), not the eTools; the eTools
themselves add nothing to the WAR order over consensus FV, and eHIT orders later WAR worse than
the consensus hit grade it was built to sharpen (it predicts strikeout rate, the hit tool's own
label, and strikeout rate is not what separates later WAR once consensus FV is known). The
served eFV keeps the consensus tool inputs. The arm (`efv_etools_reweight.etool_inputs`, the
slots of 4.1, the fold design of 2.3) is handed to EFV_X3_POOLED_MODEL as registered, with this
read as its prior.
