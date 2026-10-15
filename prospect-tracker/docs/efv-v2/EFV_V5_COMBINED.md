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

