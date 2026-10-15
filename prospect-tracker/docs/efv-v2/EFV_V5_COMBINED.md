# eFV v5 COMBINED: one jointly weighted model of every atlas driver (method, fixed before any fit)

Written 2026-10-15 (EFV5_COMBINE_WEIGHT_SHIP) under the owner's decisions EW3-8 and EW3-9 of
2026-10-15 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, verbatim: 'After driving as many
drivers as possible via the eFV atlas, make sure to weight everything properly and apply it to
eFV'; ship rule 'Beats current eFV overall'). This document is committed ALONE, before the
module `efv5_combined.py` fits anything: it fixes the candidate list, the model, the penalty
grid, the folds, the seeds, the reads and the ship rule. Sections 1 to 9 are written before
the fit; the fit appends section 10, the spent-frame read appends section 11, and the verdict
appends section 12. No em-dashes. Nothing here, in its code or in its artifacts, is cut by
consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, binding): the groups are level, age band,
pitcher role and position family.

## 1. Why one joint fit

The atlas work produced drivers four ways: the metric atlas's clean candidate cells built as
group drivers (`efv5_group_drivers.py`, 28 columns), the tool-grade atlas's four clean cells
(`efv5_atlas_tools.py`), the tracking-era head (`efv5_tracking_head.py`, pitchers ship by its
own registered rule), and the earlier new-source columns of eFV v4 and the wave-2 scouting
columns of eFV v3, each admitted in at least one development fold. Every one of them was read
one at a time, by a greedy forward selection that admits a step only on a +0.0020 bar. The
owner asks for the opposite: every candidate in ONE model, weighted jointly, each weight
shrunk by a penalty chosen out of fold, so that a driver's weight is what it adds beside every
other driver and beside consensus, not what it adds alone.

## 2. The model

eFV v5 COMBINED keeps Driver System V2's structure and anchor exactly (consensus FV kept as
the anchor, owner EW2-9 kept the P5 head weights):

    order_idx = u_c + w_skill * e_skill + w_time * e_time        inside (side, list year)
    grade     = the group's consensus FV value at order_idx's rank (efv_v2_model.output_map)

with u_c the within-group consensus percentile, w_skill and w_time the registered P5 weights
of `data/efv_v2_assembly.json` (hit 0.908861 / 0.202573, pit 1.0 / 0.020473), and each head's
e the head's driver part over its own consensus slope (consensus-percentile equivalents).
What changes is INSIDE each head. The combined skill head of a side is one weighted ridge of
the target percentile u_y on

    [1, u_c (free), z(V2's admitted skill drivers) at V2's own penalty alpha,
     z(every candidate skill column of the side) at the candidate penalty lambda]

over the has-block training rows, and the combined timing head is one penalized logistic of
REACHED on the same shape with V2's admitted timing drivers and every candidate timing column.
All drivers of a head are fitted TOGETHER in one least-squares (skill) or one likelihood
(timing) problem: a joint fit, not a stack of separately fitted pieces.

- V2's own drivers enter as V2 fits them: the DS-06 admission rule inside the fold decides
  which of V2's candidates enter, and V2's nested forward-chained rule picks their penalty
  alpha (`efv_v2_candidates._select_alpha_g`), exactly as `efv_v2_model.fit_v2` does. Their
  slopes are then re-estimated jointly with the candidate columns at that alpha.
- Every candidate column enters without a per-column admission test. Its slope is shrunk by
  one shared ridge penalty lambda on its standardised column, and where the atlas showed a
  one-signed effect (section 3) its slope is constrained to that sign (a bound at zero), so a
  column whose joint slope wants the other sign reads exactly zero.
- A group driver is an interaction, metric times a group indicator, z-scored inside its
  level-season and centered within the in-group rows of the read year (the column
  `efv5_group_drivers` builds, unchanged). Its slope is therefore the group's departure from
  the pooled slopes V2's own drivers carry, shrunk toward zero (the pooled slope) by lambda.
- lambda is chosen by NESTED forward-chained cross-validation inside the fold's own training
  years (V2's rule: each inner year scored by a fit on the years before it; skill: weighted
  squared error of u_y on the inner year's has-block rows; timing: log loss of REACHED; ties
  to the larger penalty; no inner year gives lambda infinity), on the grid

    lambda in {1, 3, 10, 30, 100, 300, 1000, infinity}   (efv_v2_model.V2_ALPHAS)

  Inside the inner folds V2's admitted keys and alpha are the fold's own (fixed), so the
  nested choice is lambda alone. At lambda = infinity every candidate slope is zero and the
  head IS V2's head on the same rows, bit for bit: the fit can choose V2.
- The constrained weighted ridge is solved exactly (bounded least squares on the augmented
  system, `scipy.optimize.lsq_linear`, method bvls); the constrained penalized logistic by
  L-BFGS-B with bounds on the convex penalized log-likelihood (gradient tolerance 1e-9).
- Standard errors: for every driver of the final fits the ridge sandwich SE,
  sigma^2 (Z'WZ + P)^-1 Z'WZ (Z'WZ + P)^-1 on the standardised design (skill; sigma^2 the
  weighted residual variance) and the penalized Fisher sandwich for the logistic timing head;
  a slope sitting on its sign bound is reported as 0 'at bound' with the SE of the
  unconstrained ridge in its place. These are approximations for a penalized, bounded fit and
  are reported as such.
- Pitchers keep owner DS-Q2: in a fold where no pitcher skill driver is usable the pitcher
  order is consensus. A candidate column with a non-zero joint slope makes the combined
  pitcher skill head usable (that is the point of the combination); the timing head of
  pitchers keeps its P5 weight 0.020473.

## 3. The candidate list (fixed here; every column enters every fit)

Columns are keyed on each row's V2 view under `efv_v2_model.V2_SCREEN_PREFIX` plus the name,
as the v3, v4 and v5 columns were. A row that lacks a value takes the training mean (DS-04
imputation, V2's own rule), which contributes zero to its order.

### 3.1 Group drivers of the metric atlas (28, `efv5_group_drivers.menu_columns`)

The sign constraint is the atlas's full-population raw AUC against reaching the majors on the
cell the column represents: constrained to + when the raw CI95 lies above 0.5, to - when below
0.5, free when the interval holds 0.5 (an age column is read as 'younger for the level').

| # | column | side | head | group | statistic | atlas raw AUC (CI95) | sign |
|---|---|---|---|---|---|---|---|
| 1 | `g5_hit_A_all_all_k_pct` | hit | skill | A all all | k_pct_hit | 0.355 (0.335 to 0.373) | - |
| 2 | `g5_pit_A_all_all_k_minus_bb` | pit | skill | A all all | k_minus_bb_pit | 0.677 (0.665 to 0.691) | + |
| 3 | `g5_hit_A_all_all_age` | hit | timing | A all all | age_hit | 0.327 (0.307 to 0.345) | - |
| 4 | `g5_hit_A_all_all_bb_minus_k` | hit | skill | A all all | bb_minus_k_hit | 0.651 (0.633 to 0.671) | + |
| 5 | `g5_pit_A_all_all_k_pct` | pit | skill | A all all | k_pct_pit | 0.652 (0.638 to 0.666) | + |
| 6 | `g5_hit_A_young_all_k_pct` | hit | skill | A young all | k_pct_hit | 0.331 (0.312 to 0.353) | - |
| 7 | `g5_pit_A_all_all_age` | pit | timing | A all all | age_pit | 0.397 (0.380 to 0.415) | - |
| 8 | `g5_hit_A_young_all_bb_minus_k` | hit | skill | A young all | bb_minus_k_hit | 0.681 (0.657 to 0.700) | + |
| 9 | `g5_pit_A_young_all_k_pct` | pit | skill | A young all | k_pct_pit | 0.674 (0.652 to 0.693) | + |
| 10 | `g5_pit_A_young_all_k_minus_bb` | pit | skill | A young all | k_minus_bb_pit | 0.693 (0.674 to 0.715) | + |
| 11 | `g5_hit_A_all_all_avg` | hit | skill | A all all | avg_hit | 0.740 (0.723 to 0.754) | + |
| 12 | `g5_hit_A_young_all_age` | hit | timing | A young all | age_rel_level_hit | 0.411 (0.387 to 0.433) | - |
| 13 | `g5_hit_A_all_all_ops` | hit | skill | A all all | ops_hit | 0.754 (0.738 to 0.768) | + |
| 14 | `g5_hit_A_all_all_woba` | hit | skill | A all all | woba_hit | 0.747 (0.731 to 0.762) | + |
| 15 | `g5_pit_A_all_SP_k_pct` | pit | skill | A all SP | k_pct_pit | 0.677 (0.660 to 0.696) | + |
| 16 | `g5_hit_A_all_all_slg` | hit | skill | A all all | slg_hit | 0.747 (0.730 to 0.761) | + |
| 17 | `g5_hit_CPX_all_all_avg` | hit | skill | CPX all all | avg_hit | 0.775 (0.742 to 0.810) | + |
| 18 | `g5_hit_Ap_young_all_pbp_contact` | hit | skill | A+ young all | pbp_contact_hit | 0.612 (0.571 to 0.648) | + |
| 19 | `g5_hit_Ap_young_all_pbp_swstr` | hit | skill | A+ young all | pbp_swstr_hit | 0.378 (0.340 to 0.418) | - |
| 20 | `g5_hit_Ap_young_all_pbp_two_strike_contact` | hit | skill | A+ young all | pbp_two_strike_contact_hit | 0.630 (0.586 to 0.667) | + |
| 21 | `g5_hit_A_young_all_avg` | hit | skill | A young all | avg_hit | 0.755 (0.739 to 0.772) | + |
| 22 | `g5_pit_A_all_SP_k_minus_bb` | pit | skill | A all SP | k_minus_bb_pit | 0.689 (0.674 to 0.709) | + |
| 23 | `g5_pit_A_all_SP_bf_per_g` | pit | skill | A all SP | bf_per_g_rel_pit | 0.520 (0.497 to 0.539) | free |
| 24 | `g5_pit_A_all_SP_age` | pit | timing | A all SP | age_rel_level_pit | 0.444 (0.423 to 0.465) | - |
| 25 | `g5_hit_Ap_all_all_pbp_swstr` | hit | skill | A+ all all | pbp_swstr_hit | 0.404 (0.376 to 0.434) | - |
| 26 | `g5_hit_Ap_all_all_pbp_contact` | hit | skill | A+ all all | pbp_contact_hit | 0.592 (0.561 to 0.624) | + |
| 27 | `g5_hit_CPX_all_all_ops` | hit | skill | CPX all all | ops_hit | 0.771 (0.737 to 0.801) | + |
| 28 | `g5_hit_CPX_all_all_woba` | hit | skill | CPX all all | woba_hit | 0.769 (0.736 to 0.800) | + |

### 3.2 Tool-grade cells of the tool and Statcast atlas (4, `data/efv5_atlas_tools.json`)

Built here for the first time as group columns by the same rule as 3.1 (the grade as of the
row's own read, from the FanGraphs and Pipeline boards dated inside the row's own list window
and on or before its as-of date, `efv5_atlas_tools.tool_values`; the group test on the row's
highest qualified level in its read season, its age band and its role; z-scored inside the
level-season over the listed rows that carry the grade; centered within the read year). The
sign constraint reads the cell's raw within-season Spearman with early WAR (w3).

| # | column | side | head | group | statistic | atlas raw rho (CI95) | sign |
|---|---|---|---|---|---|---|---|
| 29 | `t5_pit_Ap_all_SP_sl_gap` | pit | skill | A+ all SP | tg_sl_gap_pit (slider future minus present) | -0.254 (-0.400 to -0.095) | - |
| 30 | `t5_pit_Ap_young_all_sl_gap` | pit | skill | A+ young all | tg_sl_gap_pit | -0.206 (-0.330 to -0.058) | - |
| 31 | `t5_pit_Ap_all_all_sl_gap` | pit | skill | A+ all all | tg_sl_gap_pit | -0.126 (-0.248 to -0.006) | - |
| 32 | `t5_pit_AAA_all_all_fb_fut` | pit | skill | AAA all all | tg_fb_fut_pit (fastball future grade) | -0.040 (-0.203 to +0.116) | free |

No Statcast component cleared the atlas rule (none enters). The tracking-era metrics enter
through the head of section 4, not as columns.

### 3.3 The eFV v4 new-source columns admitted in at least one development fold (40, `efv_v4.menu_columns`)

The v4 menu as registered (`docs/efv-v2/EFV_V4_BACKTEST.md` s1), including the pitcher
writer-minus-stated report field the v4 selection admitted. No atlas direction exists for
these columns, so they enter free (ridge only). Each is built at every row's own as-of read
by its family's own builder (`tools/efv_v4_backtest.v4_values`, development and spent).

| # | column | side | head | family | arg | admitted folds lv_dev / vm_dev |
|---|---|---|---|---|---|---|
| 33 | `w2i_stints_time_hit` | hit | timing | il | il_stints_pre | 0/3 / 4/8 |
| 34 | `w2i_days_time_hit` | hit | timing | il | il_days_pre | 0/3 / 7/8 |
| 35 | `w2i_sixty_time_hit` | hit | timing | il | il_60day_pre | 0/3 / 1/8 |
| 36 | `w2i_open_time_hit` | hit | timing | il | il_open_at_read | 0/3 / 2/8 |
| 37 | `w2i_recur_time_hit` | hit | timing | il | il_recurrent_pre | 0/3 / 7/8 |
| 38 | `w2i_stints_time_pit` | pit | timing | il | il_stints_pre | 1/3 / 0/8 |
| 39 | `w2i_days_time_pit` | pit | timing | il | il_days_pre | 1/3 / 0/8 |
| 40 | `w2i_recur_time_pit` | pit | timing | il | il_recurrent_pre | 2/3 / 0/8 |
| 41 | `w2i_stints_skill_pit` | pit | skill | il | il_stints_pre | 1/3 / 0/8 |
| 42 | `w2i_days_skill_pit` | pit | skill | il | il_days_pre | 1/3 / 0/8 |
| 43 | `w2i_sixty_skill_pit` | pit | skill | il | il_60day_pre | 2/3 / 0/8 |
| 44 | `w2i_open_skill_pit` | pit | skill | il | il_open_at_read | 1/3 / 0/8 |
| 45 | `w2i_recur_skill_pit` | pit | skill | il | il_recurrent_pre | 1/3 / 0/8 |
| 46 | `w2n_nri_pre_hit` | hit | timing | nri | nri_pre | 3/3 / 6/7 |
| 47 | `w2n_nri_pre_pit` | pit | timing | nri | nri_pre | 1/3 / 0/7 |
| 48 | `w2n_nri_count_pre_hit` | hit | timing | nri | nri_count_pre | 3/3 / 6/7 |
| 49 | `w2n_nri_count_pre_pit` | pit | timing | nri | nri_count_pre | 1/3 / 0/7 |
| 50 | `w2p_swstr_h` | hit | skill | pbp | swstr_h | 3/3 / 0/8 |
| 51 | `w2p_contact_h` | hit | skill | pbp | contact_h | 2/3 / 0/8 |
| 52 | `w2p_swing_h` | hit | skill | pbp | swing_h | 1/3 / 0/8 |
| 53 | `w2p_two_strike_contact_h` | hit | skill | pbp | two_strike_contact_h | 2/3 / 0/8 |
| 54 | `w2p_cstr_p` | pit | skill | pbp | cstr_p | 2/3 / 0/8 |
| 55 | `w2p_csw_p` | pit | skill | pbp | csw_p | 2/3 / 0/8 |
| 56 | `w2p_k_resid_p` | pit | skill | pbp | k_resid_p | 2/3 / 0/8 |
| 57 | `w2p_fstrike_p` | pit | skill | pbp | fstrike_p | 0/3 / 1/8 |
| 58 | `w2b_pull_h` | hit | skill | pbp_bb | pull_h | 2/3 / 0/7 |
| 59 | `w2b_pu_p` | pit | skill | pbp_bb | pu_p | 1/3 / 0/7 |
| 60 | `w4p_pop_hit` | hit | skill | popmle | w4p_pop_hit | 0/3 / 4/7 |
| 61 | `w4p_pop_pit` | pit | skill | popmle | w4p_pop_pit | 3/3 / 5/7 |
| 62 | `w2r_panel_hit` | hit | skill | raters | w2r_panel_hit | 3/3 / 0/7 |
| 63 | `w2r_panel_pit` | pit | skill | raters | w2r_panel_pit | 2/3 / 0/7 |
| 64 | `rpt_conviction_hit` | hit | timing | report | txt_conviction | 0/3 / 6/7 |
| 65 | `rpt_hedge_count_hit` | hit | timing | report | txt_hedge_count | 2/3 / 2/7 |
| 66 | `rpt_risk_hit` | hit | timing | report | txt_risk | 3/3 / 6/7 |
| 67 | `rpt_approach_concern_hit` | hit | timing | report | txt_approach_concern | 1/3 / 6/7 |
| 68 | `rpt_writer_minus_stated_hit` | hit | timing | report | txt_writer_minus_stated | 0/3 / 6/7 |
| 69 | `rpt_arrival_hit` | hit | timing | report | txt_arrival | 3/3 / 6/7 |
| 70 | `rpt_conviction_pit` | pit | skill | report | txt_conviction | 1/3 / 1/7 |
| 71 | `rpt_writer_minus_stated_pit` | pit | skill | report | txt_writer_minus_stated | 2/3 / 3/7 |
| 72 | `rpt_arrival_pit` | pit | timing | report | txt_arrival | 1/3 / 0/7 |

### 3.4 The wave-2 scouting-grade columns of eFV v3 (5, `efv_v3.W2_COLUMNS`, module efv_w2_scout)

| # | column | side | head | component |
|---|---|---|---|---|
| 73 | `w2s_brk_pit` | pit | skill | best breaking ball future grade |
| 74 | `w2s_cmd_pit` | pit | skill | control or command future grade |
| 75 | `w2s_pwr_present_hit` | hit | skill | present game power grade |
| 76 | `w2s_game_pwr_hit` | hit | skill | game power future grade |
| 77 | `w2s_posval_hit` | hit | skill | positional adjustment of the listed position |

Free (no atlas direction). Built by `efv_w2_scout.values_for` at each row's as-of date; the
2025 test rows read the look index opened on the committed gate sha, as the v3 confirmation did.

### 3.5 Excluded, and why

- The four wave-2 MiLB-profile columns (`w2m_k_hit`, `w2m_iso_hit`, `w2m_air_hit`,
  `w2m_gb_pit`): their module has no held-out builder (its profile cache ends with the 2022
  season and `tools/efv_v3_backtest.w2_values_reserved` raises on them), so they cannot be
  read on R-VM and cannot be served; a column that cannot be read on the held-out frame cannot
  enter a model judged on it.
- The anchors, weight factors and driver removals of the v3 menu: spent on the 10-08
  confirmation and kept by the owner (EW2-9).
- The 68 spent-overlap atlas cells: the atlas's own rule (they read the spent R-VM cohorts).

Per side the candidate list is therefore: hitters 42 columns (19 group
drivers, 20 v4, 3 wave-2 scouting), pitchers 35 columns
(9 group drivers, 4 tool cells, 20 v4, 2 wave-2
scouting). The timing head takes 15 hitter columns (`g5_hit_A_all_all_age`, `g5_hit_A_young_all_age`, `w2i_stints_time_hit`, `w2i_days_time_hit`, `w2i_sixty_time_hit`, `w2i_open_time_hit`, `w2i_recur_time_hit`, `w2n_nri_pre_hit`, `w2n_nri_count_pre_hit`, `rpt_conviction_hit`, `rpt_hedge_count_hit`, `rpt_risk_hit`, `rpt_approach_concern_hit`, `rpt_writer_minus_stated_hit`, `rpt_arrival_hit`) and 8 pitcher
columns (`g5_pit_A_all_all_age`, `g5_pit_A_all_SP_age`, `w2i_stints_time_pit`, `w2i_days_time_pit`, `w2i_recur_time_pit`, `w2n_nri_pre_pit`, `w2n_nri_count_pre_pit`, `rpt_arrival_pit`); every other column is a
skill column.

## 4. The tracking-era head

`efv5_tracking_head.py` is a separate model on a short-horizon label whose registration
(`docs/efv-v2/EFV_TRACKING_HEAD_GATE.md` s8) fixed its own admission and weight: a side that
ships blends, for its tracked prospects only, u = 0.5 u(order) + 0.5 u(head) within the
tracked subset, the subset keeping its own multiset of order indices
(`efv5_tracking_head.blend_orders`). Its artifact (`data/efv5_tracking_head.json`) ships the
pitcher side and not the hitter side. The combined model applies that blend, at the
registered weight 0.5 and for pitchers only, AFTER the combined order index, wherever a
row's cohort has a tracked line the head never trained on:

- lv_dev, R-LV: no row reads a tracked season (tracking starts with FSL 2021 and AAA 2022; a
  2021 list vintage reads season 2019 under the as-of rule), so the head is inert there;
- vm_dev: its 2022 and 2023 decision years read seasons 2021 and 2022, the head's OWN training
  cohorts; applying the head there would read its training rows, so the head is NOT applied on
  vm_dev and the document says so;
- R-VM (the 2025 debut cohort): the pinned preseason read of 2025 reads the 2024 tracked
  season, which the head never trained on (2024 is not resolvable at H = 2026); the blend
  applies to the 2025 pitchers with a 2024 tracked line carrying every core metric;
- the live board: the latest finished MiLB season, as `apply_to_live` reads it.

The head's weight is not estimated here: it is the registered 0.5, and the head's own flag
(`EFV_TRACKING_HEAD_ON`) is untouched. The combined read reports R-VM pitchers with and
without the blend so the head's share of the result is visible.

## 5. The frames and the folds (weights estimated out of fold, development only)

- lv_dev: list vintages V 2017, 2018, 2019, W3 on the frozen fWAR label
  `fwar@2026-10-02-0341299c20ec`, n 2,862; fold V trains on the labelled list vintages 2011
  to V - 1 with every player of the V frame left out (`efv_v2_model.v2_lv_scores`, the C03
  fold shape of `tools/efv_v3_backtest.build_dev`).
- vm_dev: the vintage-matched frame vm2, debut years 2017 to 2023, career WAR to date,
  n 830; fold Y trains on the v1 matrix rows with decision year before Y.
- Every weight below is estimated on a fold's training rows and read on its test rows. The
  reported final weights are those of the production fit (the vm frame on every matrix row
  with a decision year before 2025, the fit `efv_v2_serve.production_models` would serve)
  and of the lv fit on list vintages 2011 to 2019, each with its standard error, each listed
  with the drivers whose weight shrank to zero or sits on its sign bound.
- Statistic: the within (side, vintage) Spearman, size-weighted over groups of at least 20
  rows (`efv_v2_stat`, the registered primary), pooled Spearman after the identical output map,
  contributor AUC and the MAE of the priced grade, overall, per side and per position-group
  cell (C, IF, OF; pitchers one cell; never an FV cell), against served eFV (V2), PROSPX
  consensus, MLB Pipeline and FanGraphs.
- Intervals: E_cond (scores fixed, players resampled, paired, player-clustered, B 2000, seed
  20260906); on the held-out frames also E_refit (the pool resampled by player, every fold of
  the combined model and of V2 refit per draw with lambda re-chosen inside the draw, B 200,
  seed 20260907).
- The development read is a read on the frames the penalty was chosen on; it adjudicates
  nothing and lands as two development rows (model `efv_v5_combined`, frames lv_dev and
  vm_dev) in `data/efv_progress.json`.

## 6. The held-out read (once, spent frames)

R-LV (list vintages 2020 and 2021, W3, n 2,349) and R-VM (the 2025 debut cohort under the vm2
rule, n 147) are built by `efv_w2_il_backfill.build_reserved_capturing` through
`tools/efv_v3_backtest.build_reserved` on the committed gate sha
`e7931ce4e13110eebb53555bff455ff13ca7c502`, exactly as the v4 and v5 spent reads were. These
frames were read once on 2026-10-08 and again by v4 and v5; they are SPENT. Every block of this
read is labelled 'spent frame, read after the 10-08 confirmation'; nothing is chosen or tuned
on it (lambda is re-chosen only inside each fold's own training years, never on a test row);
no progress-ledger row is written for it; the owner's EW3-5 waiver is recorded as a dated
note in `EFV_V2_GATE.md`. The read happens ONCE: a second spent run refuses while the
artifact exists.

## 7. The ship rule (owner EW3-9, fixed here before any read)

eFV v5 COMBINED ships if BOTH hold, point estimates, pooled over sides:

1. its within Spearman beats served eFV (V2) on the POOLED development plus held-out frames:
   sum over the four frames (lv_dev, vm_dev, R-LV, R-VM) of n_frame times (within v5 minus
   within V2) divided by the total row count is above 0;
2. it does not trail served eFV by more than 0.005 within Spearman on either held-out frame:
   (v5 minus V2) on R-LV >= -0.005 and on R-VM >= -0.005.

If it ships: `EFV_V5_COMBINED_ON = True` in `efv5_combined.py` makes the production fit the
served eFV fit (`efv_v2_serve.production_models`, the export, the board grade path), with
the live columns built by the same builders at the live read; the registry row, MODEL_REGISTRY.md,
the glossary eFV method text, the Source Comparison ledger and copy are updated, and tests pin
the flag, the served path and the weights file `data/efv5_combined_weights.json`. The copy may
say 'beats consensus' only where the CI95 lower bound against consensus is above 0 (E_refit
on the held-out frames); every other reading is a tie. If it does not ship, it stays dark
behind the flag and the document says which drivers carried weight and why the held-out read
fell short. Every frame and interval is reported either way.

## 8. Defaults applied (the owner may choose differently)

- D-1 one shared lambda for every candidate column of a head (not one per family or group).
- D-2 the sign constraint from the atlas's full-population raw interval (3.1, 3.2), not the
  listed-rows one; a free column where that interval holds the null.
- D-3 V2's own drivers keep the DS-06 admission and alpha of the fold; only the candidate
  columns are weighted by the joint rule.
- D-4 the tracking head at its registered weight 0.5, pitchers only, not on vm_dev (section 4).
- D-5 a column with no live coverage (the report fields: corpus 2013 to 2019; the rater
  panel) is served at its training mean, contributing nothing on the live board, as it
  contributes nothing on the rows that lack it in the backtest; disclosed in the results.
- D-6 the spent read writes no ledger row (the v4 and v5 precedent).

## 9. Bans and hygiene

- No reserved row enters any fit: the development build raises on list vintages 2020 and 2021
  and stops before the 2025 cohort (`efv_vintage_frame`); the spent build opens them on the
  gate sha only.
- No statistic by consensus-FV cell anywhere (`docs/PROSPECT_ANCHOR_GATE.md`); the test scans
  the module source.
- No projections retrain; the fWAR label epoch's runbook is untouched; `backtest.run_backtest`
  is never called.
- Code: `efv5_combined.py` (flag `EFV_V5_COMBINED_ON = False` until the rule passes), tests
  `test_efv5_combined.py`; artifacts `data/_labs/efv5/efv5_combined_fit.json` (the
  development fit and read), `data/_labs/efv5/efv5_combined_spent.json` (the one held-out
  read), `data/efv5_combined_weights.json` (the production fit's weights and standard errors).

## 10. The fit and the development read (appended by the fit run, 2026-10-15)

Run: `python -u efv5_combined.py --fit` from commit d7240219 (artifact `data/_labs/efv5/efv5_combined_fit.json`, generated 2026-10-15T13:58:22Z, 239.3 s; label `fwar@2026-10-02-0341299c20ec`; the V2 base reproduces the DS-16 block; v3 at base_config reproduces V2 on all 3692 scored rows; every candidate column built on both frames, coverage in the artifact's `column_receipts`). E_cond B 2000, seed 20260906. The development read adjudicates nothing (lambda was chosen on these frames out of fold); two development rows (model `efv_v5_combined`) landed in `data/efv_progress.json`.

### 10.1 Within (side, vintage) Spearman, pooled over sides

| frame | n | v5c | V2 | consensus | Pipeline | FanGraphs | v5c minus V2 (E_cond CI95) | v5c minus consensus (CI95) | v5c minus Pipeline | v5c minus FanGraphs |
|---|---|---|---|---|---|---|---|---|---|---|
| lv_dev | 2,862 | 0.1685 | 0.1676 | 0.1792 | 0.2034 | 0.1714 | +0.0009 (-0.0179 to +0.0193) | -0.0107 (-0.0411 to +0.0183) | -0.0318 | +0.0115 |
| vm_dev | 830 | 0.3611 | 0.3713 | 0.3814 | 0.3816 | 0.3363 | -0.0102 (-0.0306 to +0.0095) | -0.0203 (-0.0528 to +0.0127) | -0.0205 | +0.0248 |

Per side (within, v5c, V2, consensus; v5c minus V2; v5c minus consensus):

- lv_dev hit n 1465: v5c 0.1625, V2 0.1740, consensus 0.1948; vs V2 -0.0115 (-0.0470 to +0.0224); vs consensus -0.0324 (-0.0865 to +0.0182)
- lv_dev pit n 1397: v5c 0.1749, V2 0.1609, consensus 0.1629; vs V2 +0.0140 (-0.0023 to +0.0299); vs consensus +0.0120 (-0.0157 to +0.0370)
- vm_dev hit n 406: v5c 0.3448, V2 0.3752, consensus 0.3954; vs V2 -0.0304 (-0.0602 to -0.0000); vs consensus -0.0506 (-0.1107 to +0.0116)
- vm_dev pit n 424: v5c 0.3773, V2 0.3674, consensus 0.3674; vs V2 +0.0099 (-0.0163 to +0.0344); vs consensus +0.0099 (-0.0163 to +0.0344)

Per fold, v5c minus V2 within: lv_dev hit|2017 -0.0234 (n 472), hit|2018 +0.0068 (n 450), hit|2019 -0.0164 (n 543), pit|2017 +0.0140 (n 469), pit|2018 +0.0027 (n 439), pit|2019 +0.0241 (n 489); vm_dev hit|2017 -0.2248 (n 30), hit|2018 -0.0607 (n 36), hit|2019 -0.0033 (n 59), hit|2020 -0.0081 (n 54), hit|2021 -0.0528 (n 51), hit|2022 +0.0015 (n 100), hit|2023 -0.0032 (n 76), pit|2017 n/a (n 16), pit|2018 +0.0021 (n 38), pit|2019 +0.0336 (n 63), pit|2020 +0.0623 (n 77), pit|2021 -0.0844 (n 75), pit|2022 +0.0191 (n 65), pit|2023 +0.0238 (n 90).

Pooled Spearman after the map, contributor AUC and the MAE of the priced grade, v5c minus V2 / minus consensus:

- lv_dev: pooled +0.0056 (-0.0140 to +0.0251) / -0.0072; AUC +0.0055 (-0.0112 to +0.0212) / -0.0061; MAE -0.0170 / +0.0112 (a scale reading, not accuracy).
- vm_dev: pooled +0.0070 (-0.0075 to +0.0218) / -0.0030; AUC +0.0069 (-0.0021 to +0.0158) / +0.0027; MAE -0.0272 / +0.0456 (a scale reading, not accuracy).

Position-group cells, v5c minus V2 within (E_cond CI95) and v5c minus consensus:

- lv_dev: hit:C n 168 -0.0211 (-0.1494 to +0.1008) / -0.0510; hit:IF n 710 +0.0158 (-0.0296 to +0.0609) / +0.0110; hit:OF n 572 -0.0347 (-0.0943 to +0.0249) / -0.0835; pit:pit n 1397 +0.0140 (-0.0023 to +0.0299) / +0.0120.
- vm_dev: hit:C n 41 not scored; hit:IF n 207 -0.0068 (-0.0277 to +0.0125) / -0.0028; hit:OF n 144 -0.0137 (-0.0536 to +0.0247) / -0.0462; pit:pit n 424 +0.0099 (-0.0163 to +0.0344) / +0.0099.

Group cells (the scored rows inside a group or tool column's own group; level, age band and role only):

- lv_dev: g5_hit_A_all_all_k_pct n 418 -0.0380 (-0.1011 to +0.0266); g5_pit_A_all_all_k_minus_bb n 374 -0.0034 (-0.0329 to +0.0263); g5_hit_A_young_all_k_pct n 360 -0.0251 (-0.0885 to +0.0407); g5_pit_A_young_all_k_pct n 290 +0.0024 (-0.0354 to +0.0372); g5_pit_A_all_SP_k_pct n 310 -0.0008 (-0.0326 to +0.0303); g5_hit_CPX_all_all_avg n 266 +0.0086 (-0.0333 to +0.0522); g5_hit_Ap_young_all_pbp_contact n 267 -0.0312 (-0.1123 to +0.0459); g5_hit_Ap_all_all_pbp_swstr n 320 -0.0295 (-0.1016 to +0.0426); t5_pit_Ap_all_SP_sl_gap n 39 -0.0238 (no interval); t5_pit_Ap_young_all_sl_gap n 41 +0.0053 (no interval); t5_pit_Ap_all_all_sl_gap n 48 +0.0158 (no interval); t5_pit_AAA_all_all_fb_fut n 65 -0.0065 (-0.0695 to +0.0424).
- vm_dev: g5_hit_Ap_young_all_pbp_contact n 110 -0.0149 (-0.0565 to +0.0174); g5_hit_Ap_all_all_pbp_swstr n 130 -0.0123 (-0.0436 to +0.0152); t5_pit_AAA_all_all_fb_fut n 61 -0.0066 (-0.1599 to +0.1595).

### 10.2 The penalties the folds chose

| fold | alpha skill / timing (V2's) | lambda skill / timing | V2 skill keys | non-zero slopes, V2 and candidate, skill / timing |
|---|---|---|---|---|
| lv_dev hit|2017 | 30.0 / 30.0 | 300.0 / 100.0 | obp_rel, contact, tool_speed | 21 / 17 |
| lv_dev hit|2018 | 100.0 / 30.0 | 300.0 / 300.0 | obp_rel, is_college | 19 / 16 |
| lv_dev hit|2019 | 100.0 / 30.0 | 300.0 / 300.0 | obp_rel, contact, is_college | 20 / 17 |
| lv_dev pit|2017 | 30.0 / 30.0 | 300.0 / 10.0 | k_rel | 22 / 12 |
| lv_dev pit|2018 | 300.0 / 100.0 | 1000.0 / inf | k_rel | 20 / 1 |
| lv_dev pit|2019 | 300.0 / 100.0 | 1000.0 / inf | k_rel | 22 / 1 |
| vm_dev hit|2017 | None / inf | 100.0 / 10.0 | none | 16 / 13 |
| vm_dev hit|2018 | 10.0 / 1.0 | 1000.0 / 10.0 | tool_hit | 21 / 16 |
| vm_dev hit|2019 | 10.0 / 1.0 | inf / 300.0 | tool_hit, tool_speed | 2 / 14 |
| vm_dev hit|2020 | 30.0 / 1.0 | 1000.0 / 300.0 | tool_hit, tool_speed, is_college | 23 / 14 |
| vm_dev hit|2021 | 30.0 / 1.0 | 1000.0 / 300.0 | tool_hit | 21 / 14 |
| vm_dev hit|2022 | 30.0 / 1.0 | inf / 300.0 | tool_hit | 1 / 14 |
| vm_dev hit|2023 | 30.0 / 1.0 | inf / 1000.0 | tool_hit | 1 / 14 |
| vm_dev pit|2017 | None / inf | 1000.0 / 1.0 | none | 20 / 6 |
| vm_dev pit|2018 | None / inf | 1000.0 / 1.0 | none | 23 / 6 |
| vm_dev pit|2019 | None / 10.0 | 1000.0 / 100.0 | none | 22 / 8 |
| vm_dev pit|2020 | None / 10.0 | 1000.0 / 300.0 | none | 24 / 7 |
| vm_dev pit|2021 | None / 1.0 | 1000.0 / 300.0 | none | 24 / 7 |
| vm_dev pit|2022 | None / 100.0 | 1000.0 / 1000.0 | none | 23 / 7 |
| vm_dev pit|2023 | None / 30.0 | 1000.0 / 1000.0 | none | 24 / 7 |

### 10.3 Every driver's final weight and standard error (the production fit)

The production fit is the vm fit on every matrix row with a decision year before 2025 (the fit the
served path would use). beta is the slope on the standardised column; the weight is w_head x beta /
b_uc, in consensus-percentile equivalents (how much of one consensus percentile a one-sd move of
the driver is worth in the order index); SE by the ridge sandwich (document s2). A slope of zero
is listed as such; 'at bound' marks a sign-constrained slope the data wanted the other way.

#### hit: n 1,889 training rows, decision years 2011 to 2024, w_skill 0.908861, w_time 0.202573

skill head: alpha 100.0, lambda 1000.0, consensus slope b_uc 0.190149, usable True; 19 non-zero slopes, 9 zero.

| driver | source | sign | beta | SE | weight (pct equiv) | SE | note |
|---|---|---|---|---|---|---|---|
| `tool_hit` | v2 | V2 | +0.0339 | 0.0084 | +0.1619 | 0.0403 |  |
| `w4p_pop_hit` | v4 | free | +0.0218 | 0.0040 | +0.1040 | 0.0192 |  |
| `w2s_game_pwr_hit` | w2s | free | +0.0093 | 0.0039 | +0.0446 | 0.0184 |  |
| `w2r_panel_hit` | v4 | free | +0.0083 | 0.0041 | +0.0397 | 0.0197 |  |
| `w2b_pull_h` | v4 | free | -0.0042 | 0.0041 | -0.0202 | 0.0196 |  |
| `w2p_swing_h` | v4 | free | -0.0040 | 0.0038 | -0.0190 | 0.0181 |  |
| `w2s_posval_hit` | w2s | free | +0.0034 | 0.0041 | +0.0165 | 0.0194 |  |
| `g5_hit_A_all_all_slg` | group | + | +0.0028 | 0.0027 | +0.0133 | 0.0127 |  |
| `w2p_contact_h` | v4 | free | +0.0023 | 0.0025 | +0.0112 | 0.0121 |  |
| `g5_hit_A_all_all_ops` | group | + | +0.0023 | 0.0019 | +0.0110 | 0.0090 |  |
| `g5_hit_A_all_all_woba` | group | + | +0.0021 | 0.0021 | +0.0102 | 0.0099 |  |
| `w2p_two_strike_contact_h` | v4 | free | +0.0019 | 0.0030 | +0.0090 | 0.0145 |  |
| `g5_hit_Ap_all_all_pbp_contact` | group | + | +0.0019 | 0.0025 | +0.0089 | 0.0118 |  |
| `w2p_swstr_h` | v4 | free | -0.0014 | 0.0024 | -0.0065 | 0.0114 |  |
| `g5_hit_Ap_all_all_pbp_swstr` | group | - | -0.0013 | 0.0026 | -0.0064 | 0.0123 |  |
| `g5_hit_A_young_all_avg` | group | + | +0.0010 | 0.0032 | +0.0049 | 0.0153 |  |
| `g5_hit_Ap_young_all_pbp_contact` | group | + | +0.0009 | 0.0022 | +0.0044 | 0.0105 |  |
| `w2s_pwr_present_hit` | w2s | free | +0.0008 | 0.0040 | +0.0040 | 0.0190 |  |
| `g5_hit_A_all_all_avg` | group | + | +0.0003 | 0.0028 | +0.0013 | 0.0134 |  |
| `g5_hit_A_all_all_k_pct` | group | - | +0.0000 | 0.0029 | +0.0000 | 0.0138 | zero, at bound |
| `g5_hit_A_all_all_bb_minus_k` | group | + | +0.0000 | 0.0028 | +0.0000 | 0.0132 | zero, at bound |
| `g5_hit_A_young_all_k_pct` | group | - | +0.0000 | 0.0028 | +0.0000 | 0.0136 | zero, at bound |
| `g5_hit_A_young_all_bb_minus_k` | group | + | +0.0000 | 0.0028 | +0.0000 | 0.0135 | zero, at bound |
| `g5_hit_CPX_all_all_avg` | group | + | +0.0000 | 0.0033 | +0.0000 | 0.0157 | zero, at bound |
| `g5_hit_Ap_young_all_pbp_swstr` | group | - | +0.0000 | 0.0025 | +0.0000 | 0.0119 | zero, at bound |
| `g5_hit_Ap_young_all_pbp_two_strike_contact` | group | + | +0.0000 | 0.0030 | +0.0000 | 0.0145 | zero, at bound |
| `g5_hit_CPX_all_all_ops` | group | + | +0.0000 | 0.0025 | +0.0000 | 0.0118 | zero, at bound |
| `g5_hit_CPX_all_all_woba` | group | + | +0.0000 | 0.0024 | +0.0000 | 0.0116 | zero, at bound |

Drivers whose weight is zero: `g5_hit_A_all_all_k_pct`, `g5_hit_A_all_all_bb_minus_k`, `g5_hit_A_young_all_k_pct`, `g5_hit_A_young_all_bb_minus_k`, `g5_hit_CPX_all_all_avg`, `g5_hit_Ap_young_all_pbp_swstr`, `g5_hit_Ap_young_all_pbp_two_strike_contact`, `g5_hit_CPX_all_all_ops`, `g5_hit_CPX_all_all_woba`.

timing head: alpha 1.0, lambda 300.0, consensus slope b_uc 3.356596, usable True; 8 non-zero slopes, 8 zero.

| driver | source | sign | beta | SE | weight (pct equiv) | SE | note |
|---|---|---|---|---|---|---|---|
| `level_rank` | v2 | V2 | +2.3917 | 0.1341 | +0.1443 | 0.0081 |  |
| `w2i_days_time_hit` | v4 | free | +0.1002 | 0.0227 | +0.0060 | 0.0014 |  |
| `w2i_open_time_hit` | v4 | free | +0.0991 | 0.0278 | +0.0060 | 0.0017 |  |
| `w2i_sixty_time_hit` | v4 | free | -0.0822 | 0.0273 | -0.0050 | 0.0016 |  |
| `w2n_nri_pre_hit` | v4 | free | +0.0432 | 0.0232 | +0.0026 | 0.0014 |  |
| `w2n_nri_count_pre_hit` | v4 | free | +0.0310 | 0.0233 | +0.0019 | 0.0014 |  |
| `w2i_stints_time_hit` | v4 | free | +0.0230 | 0.0196 | +0.0014 | 0.0012 |  |
| `w2i_recur_time_hit` | v4 | free | +0.0177 | 0.0231 | +0.0011 | 0.0014 |  |
| `g5_hit_A_all_all_age` | group | - | +0.0000 | 0.0249 | +0.0000 | 0.0015 | zero, at bound |
| `g5_hit_A_young_all_age` | group | - | +0.0000 | 0.0233 | +0.0000 | 0.0014 | zero, at bound |
| `rpt_conviction_hit` | v4 | free | +0.0000 | 0.0000 | +0.0000 | 0.0000 | zero |
| `rpt_hedge_count_hit` | v4 | free | +0.0000 | 0.0000 | +0.0000 | 0.0000 | zero |
| `rpt_risk_hit` | v4 | free | +0.0000 | 0.0000 | +0.0000 | 0.0000 | zero |
| `rpt_approach_concern_hit` | v4 | free | +0.0000 | 0.0000 | +0.0000 | 0.0000 | zero |
| `rpt_writer_minus_stated_hit` | v4 | free | +0.0000 | 0.0000 | +0.0000 | 0.0000 | zero |
| `rpt_arrival_hit` | v4 | free | +0.0000 | 0.0000 | +0.0000 | 0.0000 | zero |

Drivers whose weight is zero: `g5_hit_A_all_all_age`, `g5_hit_A_young_all_age`, `rpt_conviction_hit`, `rpt_hedge_count_hit`, `rpt_risk_hit`, `rpt_approach_concern_hit`, `rpt_writer_minus_stated_hit`, `rpt_arrival_hit`.

#### pit: n 1,981 training rows, decision years 2011 to 2024, w_skill 1.0, w_time 0.020473

skill head: alpha None, lambda 1000.0, consensus slope b_uc 0.267721, usable True; 24 non-zero slopes, 3 zero.

| driver | source | sign | beta | SE | weight (pct equiv) | SE | note |
|---|---|---|---|---|---|---|---|
| `w4p_pop_pit` | v4 | free | +0.0217 | 0.0043 | +0.0809 | 0.0159 |  |
| `w2s_cmd_pit` | w2s | free | +0.0105 | 0.0041 | +0.0393 | 0.0155 |  |
| `w2p_csw_p` | v4 | free | +0.0101 | 0.0041 | +0.0377 | 0.0154 |  |
| `w2b_pu_p` | v4 | free | -0.0101 | 0.0044 | -0.0376 | 0.0163 |  |
| `w2p_k_resid_p` | v4 | free | +0.0088 | 0.0040 | +0.0327 | 0.0148 |  |
| `w2s_brk_pit` | w2s | free | +0.0073 | 0.0044 | +0.0272 | 0.0163 |  |
| `t5_pit_Ap_all_all_sl_gap` | tool | - | -0.0069 | 0.0044 | -0.0258 | 0.0165 |  |
| `w2i_days_skill_pit` | v4 | free | -0.0068 | 0.0036 | -0.0255 | 0.0134 |  |
| `g5_pit_A_all_SP_k_pct` | group | + | +0.0062 | 0.0031 | +0.0231 | 0.0117 |  |
| `g5_pit_A_all_SP_k_minus_bb` | group | + | +0.0040 | 0.0031 | +0.0148 | 0.0114 |  |
| `w2i_recur_skill_pit` | v4 | free | +0.0034 | 0.0036 | +0.0125 | 0.0136 |  |
| `w2i_sixty_skill_pit` | v4 | free | -0.0034 | 0.0043 | -0.0125 | 0.0161 |  |
| `w2r_panel_pit` | v4 | free | -0.0033 | 0.0044 | -0.0125 | 0.0165 |  |
| `w2p_cstr_p` | v4 | free | +0.0033 | 0.0039 | +0.0123 | 0.0147 |  |
| `t5_pit_AAA_all_all_fb_fut` | tool | free | +0.0033 | 0.0044 | +0.0122 | 0.0164 |  |
| `w2i_stints_skill_pit` | v4 | free | +0.0032 | 0.0032 | +0.0120 | 0.0120 |  |
| `g5_pit_A_all_all_k_pct` | group | + | +0.0026 | 0.0033 | +0.0099 | 0.0125 |  |
| `w2p_fstrike_p` | v4 | free | -0.0012 | 0.0042 | -0.0044 | 0.0157 |  |
| `g5_pit_A_all_SP_bf_per_g` | group | free | +0.0006 | 0.0044 | +0.0024 | 0.0163 |  |
| `w2i_open_skill_pit` | v4 | free | -0.0003 | 0.0044 | -0.0011 | 0.0163 |  |
| `g5_pit_A_young_all_k_pct` | group | + | +0.0001 | 0.0034 | +0.0004 | 0.0127 |  |
| `g5_pit_A_all_all_k_minus_bb` | group | + | +0.0000 | 0.0031 | +0.0000 | 0.0115 | zero, at bound |
| `g5_pit_A_young_all_k_minus_bb` | group | + | +0.0000 | 0.0035 | +0.0000 | 0.0129 | zero, at bound |
| `t5_pit_Ap_all_SP_sl_gap` | tool | - | -0.0000 | 0.0000 | -0.0000 | 0.0000 |  |
| `t5_pit_Ap_young_all_sl_gap` | tool | - | +0.0000 | 0.0000 | +0.0000 | 0.0000 | zero, at bound |
| `rpt_conviction_pit` | v4 | free | +0.0000 | 0.0000 | +0.0000 | 0.0000 |  |
| `rpt_writer_minus_stated_pit` | v4 | free | +0.0000 | 0.0000 | +0.0000 | 0.0000 |  |

Drivers whose weight is zero: `g5_pit_A_all_all_k_minus_bb`, `g5_pit_A_young_all_k_minus_bb`, `t5_pit_Ap_young_all_sl_gap`.

timing head: alpha 10.0, lambda 100.0, consensus slope b_uc 2.937118, usable True; 6 non-zero slopes, 3 zero.

| driver | source | sign | beta | SE | weight (pct equiv) | SE | note |
|---|---|---|---|---|---|---|---|
| `level_rank` | v2 | V2 | +0.7991 | 0.0636 | +0.0056 | 0.0004 |  |
| `w2n_nri_count_pre_pit` | v4 | free | -0.1619 | 0.0394 | -0.0011 | 0.0003 |  |
| `w2i_recur_time_pit` | v4 | free | +0.0537 | 0.0434 | +0.0004 | 0.0003 |  |
| `w2i_stints_time_pit` | v4 | free | +0.0424 | 0.0405 | +0.0003 | 0.0003 |  |
| `w2i_days_time_pit` | v4 | free | +0.0299 | 0.0437 | +0.0002 | 0.0003 |  |
| `w2n_nri_pre_pit` | v4 | free | +0.0172 | 0.0394 | +0.0001 | 0.0003 |  |
| `g5_pit_A_all_all_age` | group | - | +0.0000 | 0.0417 | +0.0000 | 0.0003 | zero, at bound |
| `g5_pit_A_all_SP_age` | group | - | +0.0000 | 0.0411 | +0.0000 | 0.0003 | zero, at bound |
| `rpt_arrival_pit` | v4 | free | +0.0000 | 0.0000 | +0.0000 | 0.0000 | zero |

Drivers whose weight is zero: `g5_pit_A_all_all_age`, `g5_pit_A_all_SP_age`, `rpt_arrival_pit`.

## 11. The held-out read (appended by the spent run, 2026-10-15; spent frames)

Run: `python -u efv5_combined.py --spent --gate-sha e7931ce4e13110eebb53555bff455ff13ca7c502` from commit d293a927 (artifact `data/_labs/efv5/efv5_combined_spent.json`, generated 2026-10-15T15:13:27Z, 4351.8 s; label `fwar@2026-10-02-0341299c20ec`; v3 at base_config reproduces V2 on all 2496 scored reserved rows; E_cond B 2000, E_refit B 200). Every block is labelled 'spent frame, read after the 10-08 confirmation'; no ledger row was written. A first build of this read aborted inside the tool-cell builder before any statistic (a reserved-year matrix row outside the fold read the development board index and raised); the builder was corrected to skip rows outside the fold and the read ran once.

| frame | n | v5c | V2 | consensus | Pipeline | FanGraphs | v5c minus V2 (E_cond; E_refit) | v5c minus consensus (E_cond; E_refit) | v5c minus Pipeline (E_refit) | v5c minus FanGraphs (E_refit) |
|---|---|---|---|---|---|---|---|---|---|---|
| R-LV | 2,349 | 0.1479 | 0.1511 | 0.1494 | 0.1988 | 0.1469 | -0.0032 (-0.0237 to +0.0175; -0.0369 to +0.0171) | -0.0015 (-0.0313 to +0.0264; -0.0438 to +0.0218) | -0.0353 (-0.0840 to +0.0018) | +0.0066 (-0.0370 to +0.0354) |
| R-VM | 147 | 0.3451 | 0.3739 | 0.3333 | 0.3142 | 0.3568 | -0.0288 (-0.0733 to +0.0165; -0.0744 to +0.0756) | +0.0118 (-0.0570 to +0.0810; -0.0847 to +0.0912) | +0.0309 (-0.0980 to +0.1351) | -0.0118 (-0.1240 to +0.0748) |

Per side:

- R-LV hit n 1195: v5c 0.1609, V2 0.1590, consensus 0.1533; vs V2 +0.0019 (-0.0185 to +0.0214); vs consensus +0.0076 (-0.0357 to +0.0547); E_refit vs V2 -0.0364 to +0.0204, vs consensus -0.0475 to +0.0398
- R-LV pit n 1154: v5c 0.1344, V2 0.1429, consensus 0.1455; vs V2 -0.0085 (-0.0442 to +0.0267); vs consensus -0.0111 (-0.0475 to +0.0257); E_refit vs V2 -0.0550 to +0.0367, vs consensus -0.0604 to +0.0323
- R-VM hit n 72: v5c 0.2888, V2 0.3374, consensus 0.2545; vs V2 -0.0486 (-0.1169 to +0.0168); vs consensus +0.0343 (-0.0953 to +0.1650); E_refit vs V2 -0.1082 to +0.1348, vs consensus -0.1444 to +0.2039
- R-VM pit n 75: v5c 0.3992, V2 0.4090, consensus 0.4090; vs V2 -0.0098 (-0.0781 to +0.0555); vs consensus -0.0098 (-0.0781 to +0.0555); E_refit vs V2 -0.0921 to +0.0580, vs consensus -0.0919 to +0.0580

Per fold, v5c minus V2 within: R-LV hit|2020 +0.0103 (n 596), hit|2021 -0.0064 (n 599), pit|2020 +0.0170 (n 572), pit|2021 -0.0335 (n 582); R-VM hit|2025 -0.0486 (n 72), pit|2025 -0.0098 (n 75).

Pooled Spearman, contributor AUC and MAE, v5c minus V2 / minus consensus (E_refit CI95 on the V2 leg):

- R-LV: pooled -0.0006 (-0.0375 to +0.0170) / +0.0040; AUC +0.0007 (-0.0189 to +0.0270) / +0.0159; MAE -0.0115 / +0.0056.
- R-VM: pooled -0.0303 (-0.0797 to +0.0826) / +0.0138; AUC +0.0029 (-0.0322 to +0.0981) / +0.0561; MAE +0.0523 / -0.0072.

Position-group cells, v5c minus V2 within (E_cond CI95) / v5c minus consensus:

- R-LV: hit:C n 117 -0.0185 (-0.0817 to +0.0380) / +0.0407; hit:IF n 575 -0.0122 (-0.0416 to +0.0159) / -0.0092; hit:OF n 481 +0.0233 (-0.0081 to +0.0539) / +0.0292; pit:pit n 1154 -0.0085 (-0.0442 to +0.0267) / -0.0111.
- R-VM: hit:C n 11 not scored; hit:IF n 35 -0.0268 (no interval) / +0.1350; hit:OF n 26 -0.0486 (no interval) / +0.1287; pit:pit n 75 -0.0098 (-0.0781 to +0.0555) / -0.0098.

Group cells:

- R-LV: g5_hit_A_all_all_k_pct n 302 +0.0299 (-0.0146 to +0.0731); g5_pit_A_all_all_k_minus_bb n 285 -0.0268 (-0.1120 to +0.0586); g5_hit_A_young_all_k_pct n 274 +0.0213 (-0.0216 to +0.0638); g5_pit_A_young_all_k_pct n 195 -0.0416 (-0.1441 to +0.0627); g5_pit_A_all_SP_k_pct n 225 -0.0409 (-0.1487 to +0.0576); g5_hit_CPX_all_all_avg n 149 -0.0051 (-0.0410 to +0.0319); g5_hit_Ap_young_all_pbp_contact n 187 +0.0425 (-0.0277 to +0.1128); g5_hit_Ap_all_all_pbp_swstr n 206 +0.0421 (-0.0251 to +0.1069); t5_pit_Ap_all_SP_sl_gap n 75 +0.0213 (-0.2646 to +0.2859); t5_pit_Ap_young_all_sl_gap n 68 -0.0466 (-0.3071 to +0.2009); t5_pit_Ap_all_all_sl_gap n 97 -0.0158 (-0.2306 to +0.1835); t5_pit_AAA_all_all_fb_fut n 51 +0.1813 (no interval).
- R-VM: t5_pit_AAA_all_all_fb_fut n 30 +0.0314 (no interval).

The tracking-era head on R-VM: hit|2025: does not ship (untouched); pit|2025: ships, 49 of 95 test rows tracked in season 2024, 47 re-ordered.
Without the blend (the combined order alone): vs V2 -0.0190 (-0.0662 to +0.0293), vs consensus +0.0216; pitchers vs V2 +0.0095.

Fold penalties on the spent frames: R-LV hit|2020 lambda 300.0 / 300.0, non-zero 20 / 17; R-LV hit|2021 lambda 1000.0 / 300.0, non-zero 23 / 16; R-LV pit|2020 lambda 1000.0 / inf, non-zero 26 / 2; R-LV pit|2021 lambda 300.0 / inf, non-zero 21 / 0; R-VM hit|2025 lambda 1000.0 / 1000.0, non-zero 19 / 14; R-VM pit|2025 lambda 1000.0 / 1000.0, non-zero 22 / 7.

## 12. The verdict (EW3-9, the rule of section 7)

| frame | n | v5c minus V2 within |
|---|---|---|
| lv_dev | 2,862 | +0.0009 |
| vm_dev | 830 | -0.0102 |
| R-LV | 2,349 | -0.0032 |
| R-VM | 147 | -0.0288 |

Pooled over the four frames by row count (6,188 rows): -0.0028. Rule 1 (above 0): NOT met. Rule 2 (no held-out frame trails V2 by more than 0.005): NOT met. **eFV v5 COMBINED does NOT ship; `EFV_V5_COMBINED_ON` stays False.**

- Against consensus on R-LV: -0.0015 (E_refit CI95 [-0.0438, 0.0218]); a tie: the CI95 lower bound is not above 0, so the copy may not say beats consensus.
- Against consensus on R-VM: +0.0118 (E_refit CI95 [-0.0847, 0.0912]); a tie: the CI95 lower bound is not above 0, so the copy may not say beats consensus.

