# eFV v5 group drivers: selection rule, step log, spent-frame read

Written 2026-10-15 (EFV5_GROUP_DRIVERS) before any combined read, under the owner's
decisions EW3-1 to EW3-5 of 2026-10-14 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`) and the
ship rule EW2-10. The owner asked that eFV find as many statistical correlations as possible
for different position, age and level groups and build them into eFV drivers. The eFV v5
metric atlas (`efv5_atlas.py`, `data/efv5_metric_atlas.json`, commit cbf5146b) scored every
MiLB metric twice per group: raw, like the owner's chart, and INCREMENTAL over PROSPX
consensus FV. Only the incremental score can admit a driver. This task takes the atlas
candidates on the families that carry a long label and offers each to Driver System V2 as a
column that applies only inside its own group. The configuration is chosen on the
development frames only, committed, and then read once on the reserved frames R-LV and
R-VM, which the v3 confirmation of 2026-10-08 already spent. No reserved-frame number enters
the choice. No em-dashes. Nothing here, in its code or in its artifacts, is cut by
consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, still binding): the groups are level, age
band and pitcher role.

The module is `efv5_group_drivers.py` (`EFV_V5_ON = False`, dark), registered in
`tools/efv_screen_lab.py` as the wave-5 module. Sections 1 to 4 are written before the
selection runs; the selection run appends section 5 and the spent-frame run appends
section 6.

## 1. The configuration space

The base is Driver System V2 as assembled (`efv_v2_model.fit_v2` at the P5 weights of
`data/efv_v2_assembly.json`; hit w_skill 0.908861 w_time 0.202573, pit 1.0 / 0.020473),
refit per fold, on the frozen fWAR label `fwar@2026-10-02-0341299c20ec`, exactly as the v4
backtest read it. The owner kept these weights (EW2-9); nothing in the menu re-weights,
removes or re-anchors a V2 head. `efv5_group_drivers.fit_v5` is `efv_v3.fit_v3` at a
configuration whose only entries are ADDED columns; at `base_config()` it reproduces V2's
order on every scored row bit for bit (checked before any read: 3,692 of 3,692 rows on the
development frames), so every delta below is the added columns and nothing else.

A configuration is V2 plus ADD steps from a fixed menu. One step offers ONE column to ONE
head of ONE side beside the side's own candidates, under the unchanged DS-06 admission rule
inside every fold (sign held in every training vintage that gives a t, mean |t| at least 1;
otherwise the fold is V2 there).

### 1.1 The menu, derived from the atlas

`efv5_group_drivers.menu_columns()` derives the menu from the committed atlas artifact and
nothing else:

1. Every atlas candidate cell on a CLEAN frame (status `clean`: the label window closes
   before the 2025 debut cohort), of a family with a long label (`box`, season lines 2005+;
   `pbp`, pitch calls 2007+), whose incremental lift over consensus is above 0 with the CI95
   lower bound above 0 and q at or below 0.10 (the atlas's declared rule, BH within family
   and label). That is 47 cells, all on reach labels (reach3 or reach5); no w3 or l6 cell
   and no bb or tracking cell cleared the atlas rule. The 68 spent-overlap cells select
   nothing (the atlas's rule; they read the spent R-VM cohorts).
2. One column per (side, level, age band, role group, statistic): a level-and-age relative
   rate (`_rel`) and its raw rate are one statistic, and so are age and age for level
   (identical inside one level-season, and the column is centered inside each read year).
   The cell with the smallest q represents the statistic (then the larger lift, then the raw
   name), whichever label it was read on. 47 cells become 28 columns.
3. The head: age is arrival evidence, so the four age columns go to the TIMING head (Driver
   System V2 principle 4: timing is not talent); every performance statistic goes to the
   SKILL head. On pitchers the timing head carries the P5 weight 0.020473, so a pitcher age
   column can move the order only slightly; that is the kept weight, not a menu choice.
4. Menu order: q ascending, then lift descending, then name.

The group of each column is the atlas cell's group, fixed by the atlas before any read.
The 28 columns in menu order (atlas receipt: label, incremental lift with CI95,
q, rows; and the in-group scored rows on lv_dev / vm_dev from the coverage check, which
reads no statistic):

| # | column | side | level | age band | role | statistic (atlas metric) | head | atlas label | atlas lift (CI95) | q | atlas rows | in-group scored rows lv_dev / vm_dev |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `g5_hit_A_all_all_k_pct` | hit | A | all | all | k_pct_hit | skill | reach3 | +0.0357 (+0.0203 to +0.0520) | 0.00835 | 1,108 | 418 / 28 |
| 2 | `g5_pit_A_all_all_k_minus_bb` | pit | A | all | all | k_minus_bb_pit | skill | reach3 | +0.0535 (+0.0291 to +0.0785) | 0.01345 | 931 | 374 / 55 |
| 3 | `g5_hit_A_all_all_age` | hit | A | all | all | age_hit | timing | reach3 | +0.0375 (+0.0197 to +0.0549) | 0.01345 | 1,108 | 418 / 28 |
| 4 | `g5_hit_A_all_all_bb_minus_k` | hit | A | all | all | bb_minus_k_hit | skill | reach3 | +0.0330 (+0.0159 to +0.0501) | 0.01345 | 1,108 | 418 / 28 |
| 5 | `g5_pit_A_all_all_k_pct` | pit | A | all | all | k_pct_pit | skill | reach3 | +0.0522 (+0.0274 to +0.0793) | 0.01455 | 931 | 374 / 55 |
| 6 | `g5_hit_A_young_all_k_pct` | hit | A | young | all | k_pct_hit | skill | reach3 | +0.0399 (+0.0180 to +0.0600) | 0.01459 | 952 | 360 / 25 |
| 7 | `g5_pit_A_all_all_age` | pit | A | all | all | age_pit | timing | reach3 | +0.0539 (+0.0264 to +0.0793) | 0.01506 | 931 | 374 / 55 |
| 8 | `g5_hit_A_young_all_bb_minus_k` | hit | A | young | all | bb_minus_k_hit | skill | reach3 | +0.0375 (+0.0171 to +0.0569) | 0.02165 | 952 | 360 / 25 |
| 9 | `g5_pit_A_young_all_k_pct` | pit | A | young | all | k_pct_pit | skill | reach3 | +0.0603 (+0.0262 to +0.0914) | 0.0273 | 699 | 290 / 30 |
| 10 | `g5_pit_A_young_all_k_minus_bb` | pit | A | young | all | k_minus_bb_pit | skill | reach3 | +0.0561 (+0.0229 to +0.0886) | 0.03214 | 699 | 290 / 30 |
| 11 | `g5_hit_A_all_all_avg` | hit | A | all | all | avg_hit | skill | reach3 | +0.0239 (+0.0103 to +0.0359) | 0.03214 | 1,108 | 418 / 28 |
| 12 | `g5_hit_A_young_all_age` | hit | A | young | all | age_rel_level_hit | timing | reach3 | +0.0305 (+0.0119 to +0.0492) | 0.04812 | 952 | 360 / 25 |
| 13 | `g5_hit_A_all_all_ops` | hit | A | all | all | ops_hit | skill | reach3 | +0.0199 (+0.0073 to +0.0320) | 0.04849 | 1,108 | 418 / 28 |
| 14 | `g5_hit_A_all_all_woba` | hit | A | all | all | woba_hit | skill | reach3 | +0.0201 (+0.0074 to +0.0326) | 0.05169 | 1,108 | 418 / 28 |
| 15 | `g5_pit_A_all_SP_k_pct` | pit | A | all | SP | k_pct_pit | skill | reach3 | +0.0373 (+0.0130 to +0.0595) | 0.06661 | 770 | 310 / 45 |
| 16 | `g5_hit_A_all_all_slg` | hit | A | all | all | slg_hit | skill | reach3 | +0.0166 (+0.0051 to +0.0268) | 0.07918 | 1,108 | 418 / 28 |
| 17 | `g5_hit_CPX_all_all_avg` | hit | CPX | all | all | avg_hit | skill | reach3 | +0.0648 (+0.0267 to +0.1126) | 0.07993 | 624 | 266 / 2 |
| 18 | `g5_hit_Ap_young_all_pbp_contact` | hit | A+ | young | all | pbp_contact_hit | skill | reach5 | +0.0578 (+0.0291 to +0.0949) | 0.08238 | 341 | 267 / 116 |
| 19 | `g5_hit_Ap_young_all_pbp_swstr` | hit | A+ | young | all | pbp_swstr_hit | skill | reach5 | +0.0564 (+0.0229 to +0.0950) | 0.08238 | 341 | 267 / 116 |
| 20 | `g5_hit_Ap_young_all_pbp_two_strike_contact` | hit | A+ | young | all | pbp_two_strike_contact_hit | skill | reach5 | +0.0511 (+0.0199 to +0.0848) | 0.08238 | 341 | 267 / 116 |
| 21 | `g5_hit_A_young_all_avg` | hit | A | young | all | avg_hit | skill | reach3 | +0.0243 (+0.0085 to +0.0402) | 0.0842 | 952 | 360 / 25 |
| 22 | `g5_pit_A_all_SP_k_minus_bb` | pit | A | all | SP | k_minus_bb_pit | skill | reach3 | +0.0384 (+0.0094 to +0.0639) | 0.08625 | 770 | 310 / 45 |
| 23 | `g5_pit_A_all_SP_bf_per_g` | pit | A | all | SP | bf_per_g_rel_pit | skill | reach3 | +0.0382 (+0.0114 to +0.0617) | 0.08722 | 770 | 310 / 45 |
| 24 | `g5_pit_A_all_SP_age` | pit | A | all | SP | age_rel_level_pit | timing | reach3 | +0.0415 (+0.0109 to +0.0678) | 0.09111 | 770 | 310 / 42 |
| 25 | `g5_hit_Ap_all_all_pbp_swstr` | hit | A+ | all | all | pbp_swstr_hit | skill | reach3 | +0.0402 (+0.0174 to +0.0663) | 0.09662 | 558 | 320 / 140 |
| 26 | `g5_hit_Ap_all_all_pbp_contact` | hit | A+ | all | all | pbp_contact_hit | skill | reach3 | +0.0384 (+0.0166 to +0.0620) | 0.09662 | 558 | 320 / 140 |
| 27 | `g5_hit_CPX_all_all_ops` | hit | CPX | all | all | ops_hit | skill | reach3 | +0.0507 (+0.0169 to +0.0847) | 0.09703 | 624 | 266 / 2 |
| 28 | `g5_hit_CPX_all_all_woba` | hit | CPX | all | all | woba_hit | skill | reach3 | +0.0521 (+0.0168 to +0.0875) | 0.09988 | 624 | 266 / 2 |

Level A is the StatsAPI sport 14 level (Low-A before 2021, Single-A after); A+ is sport 13;
CPX the complex leagues (sport 16). "young" is the lower tercile of age inside the
level-season's qualified lines; SP is a pitcher whose games started over games is at least
one half on that line.

### 1.2 The column (metric times a group indicator)

A row read at year Y as of a cutoff reads season S, the last MiLB season that had ended by
the read (the `efv_w2_milb` as-of rule, identical), stepped back over 2020, when no MiLB
season was played (so a list vintage 2021 row reads 2019). The row is IN the column's group
when the player has a qualified line (100 PA or 100 batters faced) at the column's level in
season S, no MLB line in any season at or before S, an age band that matches and, for the SP
columns, a role that matches. An in-group row's value is the statistic z-scored inside its
level-season (mean and sd over the qualified lines; the pitch-call statistics over the lines
the pitch-call aggregate keeps), centered at the mean of the in-group rows of the same
(side, read year) on the frame being built: a predictor-only transform, no outcome and no
grade read, so the column carries the statistic within the group and not the group's own
level. Every other row, and an in-group row whose statistic is missing, takes 0, the
interaction's zero. The statistics are computed by the atlas's own readers
(`efv5_atlas.box_lines`, `hit_rates`, `pit_rates`, `_relative`, `_age_bands`,
`pbp_metrics`), so a column means what its atlas cell meant. The person id is the row's
OUTCOME-BLIND id (`mlbam_id` on a list-vintage frame row; the matrix id on a
vintage-matched row, read at its decision year as of its matrix cutoff, as the MiLB profile
family reads it). No fetch: every input is on disk (`.cache/milb_stats`,
`.cache/efv4_pbp_discipline`).

A step taken leaves the menu. Each column is one step; there is no factor or removal step,
and no group-specific slope beyond the column itself (the interaction IS the group slope;
the V2 heads shrink it with their own ridge penalty).

## 2. The selection rule

The rule is v4's, kept as the owner fixed it (EW2-10 "fixed now"):

- Frames: lv_dev (list vintages 2017 to 2019, W3 label, n 2,862) and vm_dev (frame version
  vm2, debut years 2017 to 2023, career WAR to date, n 830), both spent development frames.
- Statistic: the within (side, vintage) Spearman, size-weighted over groups of at least 20
  rows (`efv_v2_stat`, the registered primary), read on the SCOPE of a step: the rows of the
  side the step changes. The whole-frame delta is recorded beside it and decides nothing.
- Greedy forward selection on point estimates. In each round every available step is
  evaluated against the current configuration. A step qualifies when its scope delta on
  lv_dev is at least +0.0020 and its scope delta on vm_dev is at least -0.0020. Among the
  qualifying steps the largest lv_dev scope delta wins; a tie goes to the earlier menu
  position. The round's winner joins the configuration. The selection stops when no step
  qualifies or when 6 steps have been taken (the cap, 6 steps).
- Every evaluated step of every round is written to
  `data/_labs/efv5/efv5_group_select.json` with its scope and whole-frame deltas; the
  selected configuration to `data/_labs/efv5/efv5_group_spec.json`, read back by
  `efv5_group_drivers.spec_config`. The selected configuration's development read (E_cond,
  B 2000, seed 20260906, against V2, consensus, Pipeline and FanGraphs; within, pooled, AUC
  and the MAE of the priced grade; the position-group cells and each added column's own
  group cell) lands as two development rows in `data/efv_progress.json` (model `efv_v5`,
  frames lv_dev and vm_dev): a read on the frames the configuration was chosen on, which
  adjudicates nothing. If no step qualifies in round 1, the selected configuration is V2
  itself; the artifact says so and the ship rule fails by construction (a tie with V2 is not
  a win).
- Multiple testing: the atlas corrected its 24,046 tests with Benjamini-Hochberg within
  (family, label); this selection adds 28 menu columns and up to 6 rounds of evaluations on
  two spent frames. The forking-path count of the gate (`EFV_V2_GATE.md` s6) gains every
  evaluated step, all recorded in the selection artifact.

## 3. The spent-frame read

- Frames: R-LV, list vintages 2020 and 2021 (W3; every V-frame player left out of the fold's
  training rows), and R-VM, the 2025 debut cohort under the vm2 rule, built by
  `efv_w2_il_backfill.build_reserved_capturing` through `tools/efv_v3_backtest.build_reserved`
  on the committed gate sha the v3 confirmation opened them on
  (`e7931ce4e13110eebb53555bff455ff13ca7c502`), the v5 columns built on them by the same
  builder (a reserved list vintage reads its own window; the 2025 rows read season 2024).
  These frames were read ONCE on 2026-10-08 and are SPENT: every block of this read is
  labelled "spent frame, read after the 10-08 confirmation", nothing is chosen or tuned on
  it, and it writes NO progress-ledger row. The owner's EW3-5 waiver is recorded as a dated
  note in `EFV_V2_GATE.md`.
- Read: eFV v5 at the committed configuration against served eFV (V2), PROSPX consensus, MLB
  Pipeline and FanGraphs: within and pooled Spearman, contributor AUC and the MAE of the
  priced grade, overall and per side, each with an E_cond CI95 (B 2000, seed 20260906,
  paired, player-clustered) and an E_refit CI95 (B 200, seed 20260907: the pool resampled by
  player, every fold of v5 and V2 refit per draw), plus the position-group cells
  (`efv_strata.position_family`: C, IF, OF for hitters; pitchers one cell) and each added
  column's group cell. No FV cell.
- Written to `data/_labs/efv5/efv5_group_spent.json`. A second spent run refuses while the
  artifact exists.

## 4. The ship rule (EW2-10, fixed before the read)

- eFV v5 ships (EFV_V5_ON = True, the served fit and export wired to it, with the registry
  row, MODEL_REGISTRY.md, the glossary method text and the Source Comparison view updated)
  only if its within Spearman beats served eFV (V2) on ALL FOUR frames: lv_dev, vm_dev,
  R-LV and R-VM, point estimates, pooled over sides. Otherwise it stays dark (EFV_V5_ON =
  False) and the served grade does not move.
- The copy may say eFV v5 "beats consensus" only where the CI95 lower bound against
  consensus is above 0 (E_refit on the spent frames); every other reading is a tie.
- The displayed PROSPX consensus FV never changes; no served number moves in this task
  unless the rule above passes.

## 5. The step log (appended by the selection run, 2026-10-15)

Run: `python -u efv5_group_drivers.py --select` from commit 5bfd913e (artifact
`data/_labs/efv5/efv5_group_select.json`, generated 2026-10-15T12:48:00Z, 256.9 s; label
`fwar@2026-10-02-0341299c20ec`; the V2 base reproduces the DS-16 block; v5 at base_config()
reproduces V2 on all 3,692 scored rows bit for bit; the 28 columns built in the same run).
Scope deltas are lv_dev / vm_dev, within Spearman on the side the step touches, against the
current configuration.

| round | available | qualified (scope delta lv / vm) | admitted |
|---|---|---|---|
| 1 | 28 | add hit skill g5_hit_A_all_all_woba (+0.00421 / 0); g5_hit_A_all_all_ops (+0.00412 / 0); g5_hit_A_all_all_slg (+0.00390 / 0) | add hit skill g5_hit_A_all_all_woba |
| 2 | 27 | add hit skill g5_hit_A_all_all_slg (+0.00221 / 0); ops now +0.00178 / 0, under the bar | add hit skill g5_hit_A_all_all_slg |
| 3 | 26 | none (best lv step g5_pit_A_young_all_k_pct +0.00044 / 0; ops now -0.00015) | stop |

Round 1, the other steps: the Single-A hitter plate-discipline columns read below V2 on
lv_dev (K% -0.00392, BB minus K -0.00187, young K% -0.00296, young BB minus K -0.00127)
and 0 on vm_dev; the Single-A pitcher columns read 0 or near it on lv_dev (K% +0.00012,
young K% +0.00044, K-BB% 0, young K-BB% 0, SP K% 0, SP K-BB% 0, SP batters per game 0)
and K-BB% read -0.00648 on vm_dev, SP K-BB% -0.00179; the High-A pitch-call hitter
columns (contact, whiff rate, two-strike contact, young and all) read 0 on lv_dev and
-0.00273 to -0.00563 on vm_dev; the four age columns (timing head), the three
complex-league columns and the two Single-A batting-average columns read 0 on both
frames: the admission rule refused them in every fold. A 0 is V2 itself, not a
measurement of the column. Every evaluated step is in the artifact.

The selected configuration (`data/_labs/efv5/efv5_group_spec.json`): hitters, the
Single-A wOBA and slugging columns (the in-group z of the statistic in the player's last
completed Single-A season, centered within the read year) offered to the skill head;
pitchers unchanged (V2). The admission rule took both in the lv 2017 and 2018 folds and
wOBA alone in 2019 (beside obp_rel and the fold's own V2 drivers); it took neither in any
vm_dev fold, where only 2 to 28 scored hitters per fold sit in the group, so v5 equals V2
on every vm_dev row.

The selected configuration's development read (E_cond, B 2000; a read on the frames it
was chosen on, which adjudicates nothing):

| frame | n | v5 within | V2 | consensus | Pipeline | FanGraphs | v5 minus V2 (CI95) | v5 minus consensus (CI95) | v5 minus Pipeline | v5 minus FanGraphs |
|---|---|---|---|---|---|---|---|---|---|---|
| lv_dev | 2,862 | 0.1709 | 0.1676 | 0.1792 | 0.2034 | 0.1714 | +0.0033 (-0.0007 to +0.0073) | -0.0083 (-0.0292 to +0.0120) | -0.0292 (-0.0591 to +0.0015) | +0.0089 (-0.0256 to +0.0429) |
| vm_dev | 830 | 0.3713 | 0.3713 | 0.3814 | 0.3816 | 0.3363 | 0 (0 to 0) | -0.0101 (-0.0391 to +0.0160) | -0.0103 (-0.0490 to +0.0268) | +0.0350 (-0.0101 to +0.0781) |

Per side, within, v5 minus V2 and v5 minus consensus: lv_dev hitters +0.0064 (-0.0012 to
+0.0147) and -0.0144 (-0.0503 to +0.0208), pitchers 0 (V2) and -0.0020; vm_dev hitters 0
and -0.0202, pitchers 0 and 0. Per fold, v5 minus V2 on lv_dev hitters: 2017 +0.0107,
2018 +0.0087, 2019 +0.0008 (one sign). Pooled after the map: lv_dev +0.0002 vs V2, -0.0125
vs consensus; vm_dev 0 and -0.0100. Contributor AUC: lv_dev +0.0027 vs V2 (-0.0017 to
+0.0070), -0.0090 vs consensus; vm_dev 0 and -0.0042. Position-group cells on lv_dev, v5
minus V2 within: C +0.0173 (n 168), IF +0.0026 (n 710), OF +0.0059 (n 572), pitchers 0;
v5 minus consensus: C -0.0126, IF -0.0023, OF -0.0429, pitchers -0.0020. The group cell
(lv_dev scored hitters in the Single-A group, n 418, 369 players): v5 minus V2 +0.0161
(-0.0071 to +0.0406), v5 minus consensus -0.0109 (-0.0826 to +0.0583); on vm_dev the
group holds 27 scored rows and is not scored. The MAE of the priced grade: lv_dev v5 minus
V2 -0.0019 (a scale reading, not accuracy; not compared).

Reading, development only: two Single-A hitter columns (wOBA and slugging, the
performance end of the atlas's Single-A hitter candidates) cleared the bar on lv_dev,
worth +0.0033 within over V2 pooled over sides (+0.0064 on hitters), both intervals
spanning zero; vm_dev cannot see them
(the group is nearly empty at the debut-year read). Every pitcher candidate of the atlas,
the strongest raw signals included (Single-A K% and K-BB%), adds nothing the admission
rule keeps on lv_dev (W3 on the frozen fWAR label): the atlas lifts were read on
reaching MLB, and eFV's skill head scores WAR given consensus. v5 still trails consensus
on both frames (-0.0083, -0.0101).
