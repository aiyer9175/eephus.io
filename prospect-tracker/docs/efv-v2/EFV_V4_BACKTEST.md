# eFV v4 backtest: selection rule, step log, spent-frame read

Written 2026-10-09 (EFV4_SELECT_SHIP) before any combined read, under decisions EW2-8 to
EW2-12 of 2026-10-08 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`): eFV v4 is built from
NEW SOURCES ONLY (the 420 arms on existing columns are closed, do-not-reopen item 1); the
configuration is chosen on the development frames only, committed, and then read once on
the reserved frames R-LV and R-VM, which the v3 confirmation of 2026-10-08 already spent
(EW2-10: "R-LV/R-VM are spent and reported as such"). No reserved-frame number enters the
choice. No em-dashes. Nothing here, in its code or in its artifacts, is cut by
consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, still binding).

The tool is `tools/efv_v4_backtest.py`; the configuration space is `efv_v4.py`
(`EFV_V4_ON = False`, dark). Sections 1 to 4 are written before the selection runs; the
selection run appends section 5 and the spent-frame run appends section 6.

## 1. The configuration space

The base is Driver System V2 as assembled (`efv_v2_model.fit_v2` at the P5 weights of
`data/efv_v2_assembly.json`; hit w_skill 0.908861 w_time 0.202573, pit 1.0 / 0.020473),
refit per fold as the model-class screen refit it, on the frozen fWAR label
`fwar@2026-10-02-0341299c20ec`. The owner KEPT these weights (EW2-9), so v4 starts from the
served V2 and nothing in the menu re-weights, removes or re-anchors a V2 head: the v3 menu
(anchors, weight factors, driver removals, the MiLB profile and scouting-grade columns) was
selected once and read once on the reserved frames (`docs/efv-v2/EFV_V3_BACKTEST.md` s5)
and is spent. `efv_v4.fit_v4` is `efv_v3.fit_v3` at a configuration whose only entries are
ADDED columns; at `base_config()` it reproduces V2's order on every scored row bit for bit
(`assert_v4_base_parity`, checked before any read), so every delta below is the added
columns and nothing else.

A configuration is V2 plus ADD steps from a fixed menu. One step offers ONE v4 column to
ONE head of ONE side beside the side's own candidates, under the unchanged DS-06
admission rule inside every fold (the lab's rule: the fold admits the column only when
its sign agrees across the fold's training vintages and its mean |t| clears the bar;
otherwise the fold is V2 there). A column enters at the head its registered development
read declared for it: the IL columns at the timing head of both sides and the pitcher
skill head; the NRI columns at the timing head; the pitch-event, batted-ball, population
and rater-panel columns at the skill head; the report fields at the head the
`report_absent` balance probe resolved (hitters: timing head only, the probe reads
IMBALANCED on the fWAR label; pitchers: skill head, with the two timing fields at the
timing head).

THE MENU. A v4 column is on the menu when its registered development read
(`data/_labs/efv_w2/efv_w2_<family>.json`) admitted it in at least one fold of lv_dev or
vm_dev; a column refused in every fold of both frames equals V2 there and cannot lift. The
two report fields withheld by the name-redaction invariance control (`role_ceiling`) are
not offered; the park correction of the batted-ball bundle is a flagged replacement of
`obp_rel`, not a column, and is not offered. `efv_v4.menu_columns()` derives the list from
the artifacts; this is it, 40 columns in menu order (family order, then each family's
registered order), each with its development admission receipt (lv_dev folds / vm_dev
folds):

| family (module) | head | columns (admitted lv / vm) |
|---|---|---|
| MiLB IL stints (`efv_w2_il_backfill`) | hit timing | w2i_stints_time_hit (0/3, 4/8), w2i_days_time_hit (0/3, 7/8), w2i_sixty_time_hit (0/3, 1/8), w2i_open_time_hit (0/3, 2/8), w2i_recur_time_hit (0/3, 7/8) |
| | pit timing | w2i_stints_time_pit (1/3, 0/8), w2i_days_time_pit (1/3, 0/8), w2i_recur_time_pit (2/3, 0/8) |
| | pit skill | w2i_stints_skill_pit (1/3, 0/8), w2i_days_skill_pit (1/3, 0/8), w2i_sixty_skill_pit (2/3, 0/8), w2i_open_skill_pit (1/3, 0/8), w2i_recur_skill_pit (1/3, 0/8) |
| non-roster invitations (`efv_w2_nri`) | timing | w2n_nri_pre_hit (3/3, 6/7), w2n_nri_pre_pit (1/3, 0/7), w2n_nri_count_pre_hit (3/3, 6/7), w2n_nri_count_pre_pit (1/3, 0/7) |
| pitch-event discipline (`efv_w2_pbp`) | hit skill | w2p_swstr_h (3/3, 0/8), w2p_contact_h (2/3, 0/8), w2p_swing_h (1/3, 0/8), w2p_two_strike_contact_h (2/3, 0/8) |
| | pit skill | w2p_cstr_p (2/3, 0/8), w2p_csw_p (2/3, 0/8), w2p_k_resid_p (2/3, 0/8), w2p_fstrike_p (0/3, 1/8) |
| batted ball (`efv_w2_pbp_bb`) | skill | w2b_pull_h (2/3, 0/7), w2b_pu_p (1/3, 0/7) |
| population translation (`efv_w2_popmle`) | skill | w4p_pop_hit (0/3, 4/7), w4p_pop_pit (3/3, 5/7) |
| rater panel (`efv_w2_raters`) | skill | w2r_panel_hit (3/3, 0/7), w2r_panel_pit (2/3, 0/7) |
| report extraction (`efv_w2_report_llm`) | hit timing | rpt_conviction_hit (0/3, 6/7), rpt_hedge_count_hit (2/3, 2/7), rpt_risk_hit (3/3, 6/7), rpt_approach_concern_hit (1/3, 6/7), rpt_writer_minus_stated_hit (0/3, 6/7), rpt_arrival_hit (3/3, 6/7) |
| | pit skill | rpt_conviction_pit (1/3, 1/7), rpt_writer_minus_stated_pit (2/3, 3/7) |
| | pit timing | rpt_arrival_pit (1/3, 0/7) |

Off the menu, by name (refused in every development fold): w2i_sixty_time_pit,
w2i_open_time_pit; w2p_k_resid_h, w2p_fstrike_taken_h, w2p_swstr_p, w2p_ball_rate_p;
w2b_ld_h, w2b_pu_h, w2b_oppo_hard_h, w2b_gb_p, w2b_ld_against_p; rpt_injury_mention_hit,
rpt_makeup_hit, rpt_body_projection_hit, rpt_role_floor_hit, rpt_hedge_count_pit,
rpt_risk_pit, rpt_injury_mention_pit, rpt_makeup_pit, rpt_body_projection_pit,
rpt_role_floor_pit, rpt_reliever_risk_pit. Withheld: rpt_role_ceiling_hit,
rpt_role_ceiling_pit. Not a column: w2b_park_obp_hit.

Values are built by each family's own registered builder at each row's own as-of read
(an lv row at its frame row's window start or list date on its OUTCOME-BLIND id, a vm
training row at its matrix cutoff, a vm test row at its pinned preseason read), exactly
as the family's development read built them; the pitch-event columns are None off the
has-full-pbp rows (imputed by the fit at the has-block training mean, DS-04), as the
family's full-frame read had them. A step taken leaves the menu. Each column is one
step; there is no interaction, factor or removal step.

## 2. The selection rule

- Frames: lv_dev (list vintages 2017 to 2019, W3 label, n 2,862) and vm_dev (frame version
  vm2, debut years 2017 to 2023, career WAR to date, n 830), the DS-16 rows, both spent.
- Statistic: the within (side, vintage) Spearman, size-weighted over groups of at least 20
  rows (`efv_v2_stat`, the registered primary), read on the SCOPE of a step: the rows of
  the side the step changes. The whole-frame delta is recorded beside it and decides
  nothing.
- Greedy forward selection on point estimates. In each round every available step is
  evaluated against the current configuration. A step qualifies when its scope delta on
  lv_dev is at least +0.0020 and its scope delta on vm_dev is at least -0.0020. Among the
  qualifying steps the largest lv_dev scope delta wins; a tie goes to the earlier menu
  position. The round's winner joins the configuration. The selection stops when no step
  qualifies or when 6 steps have been taken (the cap). The same constants as v3:
  +0.0020 is about an eighth of the lv_dev E_cond floor against consensus (0.0180) and
  -0.0020 about a tenth of the vm_dev floor (0.0229); smaller moves read as noise either
  way, and v3's own confirmation showed what a +0.002 bar can fit (the lift did not
  survive the reserved frames). The rule is kept as the owner fixed it (EW2-10 "fixed
  now"); it is not tightened after the fact.
- Every evaluated step of every round is written to `data/_labs/efv_v4/efv_v4_select.json`
  with its scope and whole-frame deltas; the selected configuration is written to
  `data/efv_v4_spec.json` and read back by `efv_v4.spec_config`. The selected
  configuration's development read (E_cond, B 2000, seed 20260906, against V2, consensus,
  Pipeline and FanGraphs; within, pooled, AUC and the MAE of the priced grade; the
  position-group cells) lands as two development rows in `data/efv_progress.json` (model
  `efv_v4`, frames lv_dev and vm_dev): a read on the frames the configuration was chosen
  on, which adjudicates nothing. If no step qualifies in round 1, the selected
  configuration is V2 itself; the artifact says so, no spec is committed as a model and
  the ship rule fails by construction (a tie with V2 is not a win).

## 3. The spent-frame read

- Frames: R-LV, list vintages 2020 and 2021 (W3; every V-frame player left out of the
  fold's training rows), and R-VM, the 2025 debut cohort under the vm2 rule, built by
  `tools/efv_v3_backtest.build_reserved` on the committed gate sha the v3 confirmation
  opened them on (`e7931ce4e13110eebb53555bff455ff13ca7c502`), the v4 columns built on
  them by each family's spent builder (a reserved list vintage reads lists, documents,
  rosters and seasons dated inside its own window; the population translator is refit
  per read year with every frame player left out). These frames were read ONCE on
  2026-10-08 under the owner's waiver and are SPENT: every block of this read is
  labelled "spent frame, read after the 10-08 confirmation", nothing is chosen or tuned on
  it, and it writes NO progress-ledger row (the reserved rows in the ledger are the v3
  look; a spent read is not a look).
- Read: eFV v4 at the committed configuration against served eFV (V2), PROSPX consensus,
  MLB Pipeline and FanGraphs: within and pooled Spearman, contributor AUC and the MAE of
  the priced grade, overall and per side, each with an E_cond CI95 (B 2000, seed 20260906,
  paired, player-clustered) and an E_refit CI95 (B 200, seed 20260907: the pool resampled
  by player, every fold of v4 and V2 refit per draw, the 2.5th and 97.5th percentiles of
  the draws; mde95 1.645 x sd), plus the position-group cells (`efv_strata.position_family`:
  C, IF, OF for hitters; pitchers one cell) with within deltas against V2 and consensus.
  No FV cell.
- Written to `data/_labs/efv_v4/efv_v4_spent.json`. A second spent run refuses while the
  artifact exists.

## 4. The ship rule (EW2-10, fixed before the read)

- eFV v4 ships (EFV_V4_ON = True, the served fit and export wired to it, with the
  registry row, MODEL_REGISTRY.md, the glossary method text and the Source Comparison view
  updated) only if its within Spearman beats served eFV (V2) on ALL FOUR frames: lv_dev,
  vm_dev, R-LV and R-VM, point estimates, pooled over sides. Otherwise it stays dark and
  the served grade does not move.
- The copy may say eFV v4 "beats consensus" only where the CI95 lower bound against
  consensus is above 0 (E_refit on the spent frames); every other reading is a tie.
- The displayed PROSPX consensus FV never changes; no served number moves in this task
  unless the rule above passes.
