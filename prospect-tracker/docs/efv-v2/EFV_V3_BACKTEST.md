# eFV v3 backtest: selection rule, step log, confirmation read

Written 2026-10-08 (EFV3_W3_SELECT_CONFIRM) before any combined read, under decision EW2-6
of 2026-10-08 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), which replaces the 2026-12-01
reserved read, EV-12 and the registration sequencing with a same-day backtest. What that
decision keeps: the configuration is chosen on the development frames only, committed, and
then read ONCE on the reserved frames, so the reserved number is unbiased. No reserved-frame
number enters the choice. No em-dashes. Nothing here, in its code or in its artifacts, is
cut by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, still binding).

The tool is `tools/efv_v3_backtest.py`; the configuration space is `efv_v3.py`
(`EFV_V3_ON = False`, dark). Sections 1 to 3 are written before the selection runs; the
selection run appends section 4 and the confirmation run appends section 5.

## 1. The configuration space

The base is Driver System V2 as assembled (`efv_v2_model.fit_v2` at the P5 weights of
`data/efv_v2_assembly.json`, sha256 35fe32c7...2823; hit w_skill 0.908861 w_time 0.202573,
pit 1.0 / 0.020473), refit per fold as the model-class screen refit it
(`tools/efv_v2_model_class_screen.build_inputs`), on the frozen fWAR label
`fwar@2026-10-02-0341299c20ec`. `efv_v3.fit_v3` at `base_config()` reproduces V2's order on
every scored row bit for bit (`assert_v3_base_parity`, checked before any read) and the V2
base reproduces the DS-16 block (`base_parity`), so every delta below is the configuration
and nothing else.

A configuration is V2 plus steps from a fixed menu, in this order:

| family | steps | what a step changes |
|---|---|---|
| A anchor | `an1_rel`, `an1_pl`, `an2_pos` | u_c (the within-(side, V) consensus percentile) replaced by the wave-2 anchor arm of that name (`efv_w2_anchor`: the reliability-weighted mean of the sources' within percentiles at vintages at most V - 3; the fixed Pipeline 2.0 / FanGraphs 1.0 weights; the per-source x position-group weights shrunk toward AN-1), the heads refit on it. The comparator stays served consensus and the displayed consensus FV does not change. At most one anchor. |
| B weight factor | per (side, head) one of 0, 0.25, 0.5 | the P5 weight of that head multiplied by the factor; no refit (DIAG items 2 and 3: the heads point the right way and V2 pushes them too hard). At most one factor per (side, head). |
| C driver removal | per (side, head) any one driver of the head's candidate list (hit skill: obp_rel, contact, tool_hit, tool_speed, is_college, level_rank, pl_rev; pit skill: k_rel, bmi, pl_rev; timing on both sides: age_rel_level, level_rank, milb_absent, on_40man, nov_add) | the driver withheld from the candidate list; admission, penalty and the rest unchanged (DIAG items 4 and 5). |
| D wave-2 addition | the wave-2 columns whose registered development read admitted them in at least one fold on either frame: w2m_k_hit, w2m_iso_hit, w2m_air_hit, w2m_gb_pit (MiLB profile), w2s_brk_pit, w2s_cmd_pit, w2s_pwr_present_hit, w2s_game_pwr_hit, w2s_posval_hit (scouting grades) | the column offered to the skill head of its side beside the side's own candidates, under the unchanged DS-06 admission rule. A column refused in every fold of its development read equals V2 there and is left off the menu. |

44 steps are available from the base. A step taken leaves the menu; an anchor taken removes
the other anchors; a factor taken removes the other factors on that (side, head).

## 2. The selection rule

- Frames: lv_dev (list vintages 2017 to 2019, W3 label, n 2,862) and vm_dev (frame version
  vm2, debut years 2017 to 2023, career WAR to date, n 830), the DS-16 rows, both spent.
- Statistic: the within (side, vintage) Spearman, size-weighted over groups of at least 20
  rows (`efv_v2_stat`, the registered primary), read on the SCOPE of a step: the rows of
  the side(s) the step changes (an anchor step touches both sides, every other step one
  side). The whole-frame delta is recorded beside it and decides nothing.
- Greedy forward selection on point estimates. In each round every available step is
  evaluated against the current configuration. A step qualifies when its scope delta on
  lv_dev is at least +0.0020 and its scope delta on vm_dev is at least -0.0020. Among the
  qualifying steps the largest lv_dev scope delta wins; a tie goes to the earlier menu
  position. The round's winner joins the configuration. The selection stops when no step
  qualifies or when 6 steps have been taken (the cap).
- A removal of a driver no fold admitted under the current configuration, and a factor on
  a head no fold uses, cannot move an order; they are recorded as no-op (delta 0) without a
  fit and do not qualify.
- The two tolerances: +0.0020 is about an eighth of the lv_dev E_cond floor against
  consensus (0.0180) and -0.0020 about a tenth of the vm_dev floor (0.0229); smaller moves
  read as noise either way.
- Every evaluated step of every round is written to `data/_labs/efv_v3/efv_v3_select.json`
  with its scope and whole-frame deltas; the selected configuration is written to
  `data/efv_v3_spec.json` and read back by `efv_v3.spec_config`. The selected
  configuration's development read (E_cond, B 2000, seed 20260906, against V2, consensus,
  Pipeline and FanGraphs; within, pooled, AUC and the MAE of the priced grade; the
  position-group cells) lands as two development rows in `data/efv_progress.json` (model
  `efv_v3`, frames lv_dev and vm_dev): a read on the frames the configuration was chosen
  on, which adjudicates nothing.

## 3. The confirmation read

- Frames: R-LV, list vintages 2020 and 2021 (W3; every V-frame player left out of the fold's
  training rows, which run through list vintage V - 1 and so include 2020 for the 2021
  fold), and R-VM, the 2025 debut cohort under the vm2 rule (both scored sources and the
  consensus graded inside the 2025 preseason window, the timing-pinned read as the input,
  fit on the v1 matrices at decision years before 2025, outcome career WAR to date over the
  2025 and 2026 seasons). The reserved guards (`efv_vintage_frame.guard_score_request`,
  `guard_vm_request`, `efv_v2_model._check_years`) open on the sha of the commit that carries
  `docs/efv-v2/EFV_V2_GATE.md` marked REGISTERED and on nothing else; `reserved_vm_pins()`
  stays empty (the pinned constants are not widened).
- Read: eFV v3 at the committed configuration against served eFV (V2), PROSPX consensus,
  MLB Pipeline and FanGraphs: within and pooled Spearman, contributor AUC, and the MAE of
  the priced grade (the fold's consensus-FV-to-WAR line at each rater's grade), overall and
  per side, each with an E_cond CI95 (B 2000, seed 20260906, paired, player-clustered) and
  an E_refit CI95 (B 200, seed 20260907: the pool resampled by player, every fold of v3 and
  V2 refit per draw, the 2.5th and 97.5th percentiles of the draws; mde95 1.645 x sd), plus
  the position-group cells (`efv_strata.position_family`: C, IF, OF for hitters; pitchers
  one cell) with within deltas against V2 and consensus. No FV cell.
- Reading (decision EW2-7, recorded before the read): eFV v3 is shippable if its within
  Spearman beats served eFV (V2) on both reserved frames (point estimates, pooled over
  sides); the copy can say it beats consensus only if the CI95 lower bound against consensus
  is above 0. This task ships nothing (`EFV_V3_ON` stays False); the ship task reads the
  artifact.
- Written to `data/_labs/efv_v3/efv_v3_confirm.json` and, as two reserved-frame rows
  (frames lv_res and vm_pros, trigger look, model `efv_v3`, labelled "eFV v3 backtest,
  reserved frames, owner waiver 2026-10-08"), to `data/efv_progress.json`. A second
  confirmation run refuses while the artifact exists.

## 4. The step log (appended by the selection run, 2026-10-08)

Run: `python -u tools/efv_v3_backtest.py --select` from commit fc5b9cc0 (artifact
`data/_labs/efv_v3/efv_v3_select.json`, generated 2026-10-08T20:47:57Z, 428.7 s; label
`fwar@2026-10-02-0341299c20ec`; V2 base reproduces the DS-16 block; v3 at base_config()
reproduces V2 on all 3,692 scored rows bit for bit). Scope deltas are lv_dev / vm_dev.

| round | available | qualified (scope delta lv / vm) | admitted |
|---|---|---|---|
| 1 | 44 | scale hit skill x0.25 (+0.02102 / +0.00190); scale hit skill x0.5 (+0.01611 / +0.00652); remove hit skill contact (+0.00384 / 0); remove hit skill is_college (+0.00803 / +0.00597); add pit skill w2s_cmd_pit (+0.00257 / 0) | scale hit skill x0.25 |
| 2 | 41 | scale hit timing x0 (+0.00380 / +0.02119); x0.25 (+0.00388 / +0.02133); x0.5 (+0.00270 / +0.01657); remove hit timing level_rank (+0.00230 / +0.02139); add pit skill w2s_cmd_pit (+0.00257 / 0) | scale hit timing x0.25 |
| 3 | 38 | add pit skill w2s_cmd_pit (+0.00257 / 0) | add pit skill w2s_cmd_pit |
| 4 | 37 | remove pit skill k_rel (+0.00305 / 0) | remove pit skill k_rel |
| 5 | 36 | none | stop |

Steps that did not qualify, round 1 (the full list is in the artifact): the three anchors
lift lv_dev and lower vm_dev beyond the tolerance (an1_rel +0.01407 / -0.01875, an1_pl
+0.01724 / -0.01093, an2_pos +0.01407 / -0.02453, each the wave-2 artifact's own number);
hit skill x0 (+0.01691 / -0.01938); hit timing x0 (+0.00141 / +0.01134, under the lv bar);
remove hit skill tool_hit (a no-op on lv_dev, -0.02209 on vm_dev); the MiLB profile columns
(w2m_k_hit -0.00044, w2m_iso_hit -0.00564, w2m_air_hit -0.00750 on lv_dev); every pitcher
step reads 0 on vm_dev (pitchers are the consensus order there in every fold).

The selected configuration (`data/efv_v3_spec.json`): hitters, the skill head at a quarter
of its P5 weight (0.908861 to 0.227215) and the timing head at a quarter (0.202573 to
0.050643); pitchers, the K-rate driver withheld and the scouting command grade
(w2s_cmd_pit) offered to the skill head, which the admission rule admitted on the lv 2017
fold alone (the 2018 and 2019 lv folds and every vm fold stay the consensus order).

The selected configuration's development read (E_cond, B 2000; a read on the frames it
was chosen on, which adjudicates nothing):

| frame | n | v3 within | V2 | consensus | Pipeline | FanGraphs | v3 minus V2 (CI95) | v3 minus consensus (CI95) | v3 minus Pipeline | v3 minus FanGraphs |
|---|---|---|---|---|---|---|---|---|---|---|
| lv_dev | 2,862 | 0.1831 | 0.1676 | 0.1792 | 0.2034 | 0.1714 | +0.0155 (-0.0020 to +0.0330) | +0.0039 (-0.0035 to +0.0110) | -0.0153 (-0.0370 to +0.0071) | +0.0240 (-0.0043 to +0.0505) |
| vm_dev | 830 | 0.3829 | 0.3713 | 0.3814 | 0.3816 | 0.3363 | +0.0116 (-0.0064 to +0.0303) | +0.0015 (-0.0116 to +0.0138) | +0.0013 (-0.0312 to +0.0334) | +0.0466 (+0.0093 to +0.0805) |

Per side, within, v3 minus V2 and v3 minus consensus: lv_dev hitters +0.0249 (-0.0008 to
+0.0512) and +0.0041 (-0.0092 to +0.0168), pitchers +0.0056 (-0.0162 to +0.0278) and
+0.0037 (-0.0032 to +0.0102); vm_dev hitters +0.0232 (-0.0153 to +0.0599) and +0.0031
(-0.0236 to +0.0297), pitchers 0 and 0 (consensus order). Pooled after the map: lv_dev
+0.0153 vs V2, +0.0026 vs consensus; vm_dev +0.0088 and -0.0012. Contributor AUC: lv_dev
+0.0167 vs V2 (+0.0010 to +0.0310), +0.0051 vs consensus; vm_dev +0.0067 and +0.0025.
Position-group cells, v3 minus consensus within: lv_dev C +0.0046 (n 168), IF +0.0095
(n 710), OF -0.0053 (n 572), pitchers +0.0037 (n 1,397); vm_dev IF +0.0063 (n 207), OF
+0.0144 (n 144), C under 60 rows, pitchers 0. The MAE of the priced grade: lv_dev v3
0.9157 against V2 0.9405 and consensus 0.9122; vm_dev 3.6629 against 3.6976 and 3.6248 (a
source's MAE prices its own FV through the consensus-fitted line and reads a scale
difference, not accuracy; it is not compared).

Reading, development only: the configuration closes V2's gap to consensus on both frames
(V2 minus consensus -0.0116 and -0.0101 become +0.0039 and +0.0015) and reads about +0.012
to +0.016 above V2, every interval against consensus spanning zero. The lift over V2 is
the hitter weight factor (DIAG item 2, the quarter weights); the pitcher steps add +0.003
on lv_dev pitchers and nothing on vm_dev. A tie with consensus, selected on these frames:
only section 5 can say more.
