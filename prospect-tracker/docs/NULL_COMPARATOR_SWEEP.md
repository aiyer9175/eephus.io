# Null comparator sweep: registration

Registered 2026-10-22, before any null in this document was computed. Task NULL_COMPARATOR_SWEEP (orchestrator 2026-10-19, under the owner's standing ask to take every model as far as it can honestly go). Lab: `tools/null_comparator_sweep_lab.py`. Outputs after the one run: `data/null_comparator_sweep.json` (deploy-excluded, rendered nowhere) and `docs/null-comparator-sweep/RESULTS.md`. Registry at registration: `data/model_registry.json` at commit 466c712b, 400 rows (55 validated, 202 provisional, 51 unvalidated, 92 deprecated).

## 1. Why this exists

On 2026-10-15 the positional ladder v2 passed its registered rule: it beat v1 on leave-one-season-out MAE (+0.886, lo95 +0.717). An independent check then showed an all-zero ladder ties it (+0.049, CI95 -0.005 to +0.099). MAE on a noisy, centred target falls as any ladder shrinks toward zero, so "beats the incumbent" rewarded flatness. The lesson, recorded the same day: every gate needs a NULL comparator (zero, no effect, a naive carry, a constant, or the consensus it claims to beat) that the candidate must also beat, and a planted-recovery check that shows the instrument can find a known effect. This sweep asks that question of every row the site calls validated, and of every provisional row whose served copy makes a comparative claim.

## 2. Scope

- Every row whose verdict is `validated` (55 rows).
- Every row whose verdict is `provisional` and whose served copy states a comparison against something (beats, ties or loses to a named comparator), 47 rows. Provisional rows that are descriptive, measurement only, by inheritance only, not served, registered and not yet read, or an owner-directed policy are out of scope; the reason is their own registry summary.
- Deprecated and unvalidated rows are out of scope.

## 3. Definitions

- **Null comparator.** A prediction that carries no information about the player, or only the information the claim says it improves on: a zero (or no adjustment), a constant at the population level, the prior-season (or 5/4/3) carry-forward, a permuted or shuffled twin, or the consensus or source the row says it beats. An AUC of 0.5 or a rank correlation of 0 counts as an ANALYTIC null for a pure discrimination or ordering claim.
- **Planted-recovery check.** A run on the real design in which a known effect is planted and the instrument is shown to recover it (or a simulation under a known truth that fixes the instrument's null band).
- **Census words.** null: PRESENT, ANALYTIC, MISSING, or NA (no comparative claim). action: COVERED (a valid null was in the gate), RUN:S1/S2/S3 (section 7), DEFERRED (a null exists in principle but a binding rule stops it, named in the note), NA.

## 4. Binding rules

1. The frame of every run is the one the row's eval artifact was read on: its seasons, bases, population and loss. No frame, cell or metric is chosen after seeing a number. Where the stored artifact sits on a retired WAR label, the frame definition is reproduced on the current training label (published fWAR frozen 2026-10-02, the war_source default) and the row's own model is re-scored on the identical rows in the same run; the stored number is quoted beside it as history.
2. Each registered null runs ONCE. The lab refuses a second run once `data/null_comparator_sweep.json` records one. A dry run on synthetic fixtures (an empty cell and a failed run included) precedes it and reads no real outcome.
3. Nothing is stratified by consensus-FV level, no FV-cell realized WAR mean, bust, debut or graduation rate is computed (docs/PROSPECT_ANCHOR_GATE.md), and no reserved eFV frame (R-LV, the 2020 and 2021 list vintages; R-VM, the 2025+ debut cohorts) is scored. `backtest.run_backtest` is never run. No dark betting column is read.
4. The PROJ_PATH_SHAPE_GATE frames are respected: S2 reads only label seasons 2017 to 2025 (that gate's TIER-2 READ frame, already read) and never its GATE (2012 to 2014) or CONFIRM (2026) label seasons, and scores no candidate arm of that gate.
5. Nothing served moves. No exporter runs, no verdict, summary or card in the registry changes, and no glossary entry changes. A row whose served claim ties or loses to its null is listed with a proposed copy downgrade (validated to provisional) as an OWNER QUESTION; the verdict changes only on the owner's answer.
6. Every projection cache the lab touches is a private copy (`--cache-dir`); the shared `.cache` is never written.

## 5. Census: validated rows

| row | served | comparator in its gate | null | planted | action | note |
|---|---|---|---|---|---|---|
| `ba_source_classification` | no | the hardcoded insufficient-history list | NA | no | NA | a data derivation (row counts), no predictive claim |
| `c3_proj_trans_recal` | yes | the clamped band | NA | no | NA | a clamp audit judged on monotone invariance; no accuracy claim |
| `consensus_contamination` | no | zero-information control | PRESENT | no | NA | a measurement; the leak claim already failed its control |
| `consensus_coverage_shrinkage` | no | permuted-coverage control | PRESENT | no | NA | a null result |
| `consensus_fv` | yes | best single source on the same rows, argmax redrawn per draw | PRESENT | no | COVERED | claims to beat the sources it blends; AUC null 0.5 is analytic (served AUC 0.767) |
| `consensus_org_rank_split` | yes | the label-only guard | NA | no | NA | a correctness repair; zero rows of the grade move |
| `consensus_rank` | no | rank permuted within cell | PRESENT | no | NA | a measurement with a permutation null |
| `consensus_recency_decay` | no | permuted publication dates | PRESENT | no | NA | a null result |
| `draft_slot_curve` | yes | the hand-set step table only | MISSING | no | RUN:S3 | no flat or zero curve was scored on the 2015-18 holdout |
| `efv_scoreboard` | yes | consensus FV on identical rows | PRESENT | no | COVERED | the comparator is the consensus it is read against |
| `eta` | yes | naive level-to-years table | PRESENT | no | COVERED | naive table is the null |
| `eta_fg_blend` | yes | CH40 champion | MISSING | no | DEFERRED | FanGraphs ETA alone was registered as NOT scored on the look frame (a source score over 2025-26 debut rows); owner question |
| `fa_dpw_series` | yes | fitted trend and trend plus CBT | PRESENT | no | COVERED | the winner IS the naive flat carry |
| `fa_market` | yes | nearest-comps median, trend inflated | PRESENT | no | COVERED | comps median is the naive null |
| `fa_projection_marcel` | yes | 5/4/3 carry-forward of actual WAR | PRESENT | no | RUN:S1 | carry-forward is present; a zero or constant prediction was never scored, and MAE on an absent-as-zero label rewards shrinkage |
| `fa_war_paths_decay` | yes | marcel_decay_v2 champion | MISSING | no | RUN:S2 | challenger vs champion only; no zero or carry path on the horizon frame |
| `fv_to_war_anchors` | yes | public primer table | MISSING | no | DEFERRED | any null needs an FV-cell realized WAR mean: docs/PROSPECT_ANCHOR_GATE.md |
| `hem_plus_3yr` | yes | single-season HEM+ on the same set | PRESENT | no | COVERED | single-season HEM+ is the naive carry of the same metric |
| `dem_plus` | yes | fielding pct, innings, raw rate; permuted twin | PRESENT | no | COVERED | ties its raw parent, disclosed |
| `mlb_projections_vets` | yes | inherits Gate 1 and the horizon eval | MISSING | no | RUN:S2 | row-matched claim h1 0.5846 vs 0.5988 has no zero or carry path |
| `phem_marcel_lite` | yes | 1yr HEM+, flat 3yr, textbook Marcel | PRESENT | no | COVERED | 1yr HEM+ is the naive carry |
| `plus_metric_recal` | yes | clamped display | NA | no | NA | a clamp audit judged on invariance |
| `positional_ladder` | yes | folklore table, level-corrected; zero-information control; H0 shape simulation | PRESENT | yes | COVERED | control at -5.02 runs; the consumer-level predictive gate is already a NULL |
| `proj_def_prior` | yes | the model without the feature | PRESENT | no | COVERED | an ablation: the zero-adjustment null |
| `prospect_surplus` | yes | identity calibration | PRESENT | no | DEFERRED | re-measure waits for the Prospect Anchor look (row note); its frame is the surplus backtest, never run here |
| `pwoba_blend_regate` | yes | incumbent pWOBA, xwOBA alone | PRESENT | no | COVERED | xwOBA(Y) alone is a naive carry |
| `rem_plus` | yes | ERA, raw FIP, raw WPA | PRESENT | no | COVERED | ERA is the naive carry |
| `savant_sprint` | yes | r = 0 (no range read) | PRESENT | no | COVERED | Fisher CI lower bound vs zero |
| `sc_plus_component_diagnostic` | no | n/a | NA | no | NA | a measurement |
| `sem_plus` | yes | ERA, raw FIP | PRESENT | no | COVERED | ERA is the naive carry |
| `source_cohort_accuracy` | yes | equal weight, random-cohort control | PRESENT | no | NA | a null result; no weight ships |
| `source_track_record` | yes | n/a | NA | no | NA | a measurement |
| `surplus_decomposition_v6` | no | zero-information constant board, permuted truth | PRESENT | no | NA | a measurement |
| `surplus_sensitivity_diagnostic` | no | n/a | NA | no | NA | an invariance measurement |
| `war_cohort_diagnostic` | no | n/a | NA | no | NA | a measurement |
| `xfv_bughunt2` | no | n/a | NA | no | NA | an audit |
| `xfv_dist_calibration` | no | n/a | NA | no | NA | a measurement |
| `xfv_dist_recalibration` | no | permuted-tier twin, zero-information constant | PRESENT | no | NA | a no-ship; the constant reproduced 152.7 percent of the gain |
| `xfv_label_censoring` | no | n/a | NA | no | NA | a measurement |
| `xfv_label_replacement` | no | level twin, permuted share profile | PRESENT | no | NA | a null result |
| `xfv_lambda_adjudication` | no | null E (frozen stamps) | PRESENT | no | COVERED | lab artifact |
| `xfv_lambda_reselect` | yes | lambda grid from 0.5 (no consensus-alone arm) | MISSING | no | DEFERRED | scored years 2020-2023 overlap the reserved list-vintage frame R-LV; consensus-vs-eFV v1 is a tie in xfv_hitter and xfv_headtohead_frame |
| `xfv_level_rank_fringe` | no | the lean set without the feature | PRESENT | no | COVERED | ablation null; never re-run (its t45 cell is a consensus-FV stratum) |
| `xfv_odds_calibration_slope` | yes | incumbent curve and a constant base rate | PRESENT | no | COVERED | beats the constant, CI clear of zero |
| `xfv_ops_rel_fringe` | no | the lean set without the feature | PRESENT | no | COVERED | ablation null; never re-run (consensus-FV stratum) |
| `xfv_rank_objective` | no | permuted-weight control | PRESENT | no | NA | a null result |
| `xfv_stale_anchor` | yes | the raw anchor served as fresh (zero decay) | PRESENT | no | DEFERRED | zero adjustment is present; a time-flat discount null needs bust rates by FV band (PROSPECT_ANCHOR_GATE) |
| `xhem_plus` | yes | actual wOBA forward rho | PRESENT | no | COVERED | actual wOBA(Y) is the naive carry |
| `xfv_side_calibration` | no | the other side within band | NA | no | NA | an audit; FV-band realized means, never re-run |
| `xfv_headtohead_frame` | yes | consensus FV on identical rows | PRESENT | no | COVERED | the served copy is a tie |
| `xfv_ewar_label_epoch` | no | zero-information twin, permutation null | PRESENT | no | NA | a measurement |
| `hof_induction_ledger` | no | the unrepaired ledger | NA | no | NA | a repair |
| `hof_public_bakeoff` | yes | JAWS reference and the resampled public argmax | PRESENT | no | COVERED | the served comparison is a loss, said as a loss |
| `efv_matrix` | yes | PROSPX consensus on identical rows | PRESENT | no | COVERED | comparator is the consensus |
| `fa_destination` | no | random, payroll, permuted control L_perm | PRESENT | no | COVERED | not served |

## 6. Census: provisional rows with a served comparative claim

| row | served | comparator in its gate | null | planted | action | note |
|---|---|---|---|---|---|---|
| `arb_award` | yes | MDE95 floor and a zero-information control | PRESENT | no | COVERED |  |
| `betting_game_prob` | yes | home-field constant, flat 0.500 | PRESENT | no | COVERED |  |
| `college_translation` | yes | predict-the-Single-A-mean | PRESENT | no | COVERED |  |
| `college_translation_scorecard` | yes | predict-the-Single-A-mean | PRESENT | no | COVERED |  |
| `control_window_salary_path` | yes | no price (surplus 0) | PRESENT | no | COVERED |  |
| `draft_consensus_weight` | yes | best single source, equal weight | PRESENT | no | COVERED | the edge is within noise, said so |
| `eta_hazard_lite` | yes | the incumbent path (zero adjustment) | PRESENT | no | COVERED |  |
| `farm_grades` | yes | prospect-count ranking | PRESENT | no | COVERED |  |
| `fwdhem_plus` | yes | xwOBA alone | PRESENT | no | COVERED |  |
| `btblend_plus` | yes | the served xHEM+ Blend; xwOBA alone | PRESENT | no | COVERED |  |
| `dem_plus_3yr` | yes | single-season DEM+ | PRESENT | no | COVERED |  |
| `rem_plus_3yr` | yes | single-season REM+ | PRESENT | no | COVERED |  |
| `sem_plus_3yr` | yes | single-season SEM+ | PRESENT | no | COVERED |  |
| `leverage_consistency` | yes | a fixed bar (rho 0.30) above zero | PRESENT | no | COVERED |  |
| `mlb_projections_prospects` | yes | three stat-line challengers | ANALYTIC | no | COVERED | a rank claim; a constant has rank correlation 0 |
| `mlb_projections_prospects_statline` | yes | B0 league-average rookie line | PRESENT | no | COVERED |  |
| `overseas_translation` | yes | published primer factors | MISSING | no | DEFERRED | n 3 KBO hitters; no null can be powered |
| `proj_components` | yes | naive three-season rate | PRESENT | no | COVERED |  |
| `spotlights_movement` | yes | random matched controls | PRESENT | no | COVERED |  |
| `statcast_alevel_display` | yes | the stat line alone | PRESENT | no | COVERED |  |
| `stuff_plus_aaa` | yes | r = 0 | ANALYTIC | no | COVERED |  |
| `statcast_plus` | yes | publish-the-r | ANALYTIC | no | COVERED |  |
| `team_win_projections` | yes | prior-season wins carry-forward | PRESENT | no | COVERED |  |
| `etool_ehit` | yes | the consensus tool grade | PRESENT | no | COVERED |  |
| `etool_epow` | yes | the consensus tool grade | PRESENT | no | COVERED |  |
| `etool_esel` | yes | the consensus tool grade | PRESENT | no | COVERED |  |
| `etool_ebat` | yes | the consensus tool grade | PRESENT | no | COVERED |  |
| `etool_efb` | yes | the consensus tool grade | PRESENT | no | COVERED |  |
| `etool_ecmd` | yes | the consensus tool grade | PRESENT | no | COVERED |  |
| `trade_machine_surplus` | yes | consensus FV ordering | PRESENT | no | COVERED |  |
| `fantasy_combined_rank` | yes | vintage consensus FV rank | PRESENT | no | COVERED | loses to consensus, said so |
| `mock_draft` | yes | the raw consensus board | PRESENT | no | COVERED |  |
| `grpo_prospect` | yes | zero-information shuffle, FV-only control | PRESENT | no | COVERED |  |
| `scores_mlb_wp` | yes | home-win base rate | PRESENT | no | COVERED |  |
| `rpw_fit` | yes | FanGraphs closed form | PRESENT | no | COVERED |  |
| `milb_fielding_runs` | yes | zero, fielder shuffle, within-position permutation | PRESENT | yes | COVERED | the reference design: null plus planted recovery |
| `efv_v2` | yes | PROSPX consensus and eFV v1 | PRESENT | yes | COVERED | served as a tie |
| `xfv_thin_pbust` | yes | grade-only curve, constant, permuted grade and level | PRESENT | no | COVERED |  |
| `xfv_tools` | yes | consensus tool grade alone | PRESENT | no | COVERED |  |
| `xfv_ungraded` | yes | rank vs zero; constant first-grade MAE | PRESENT | no | COVERED | loses the level to a constant, said so |
| `provisional_first_grade` | yes | per-set constant, level-rank and younger nulls | PRESENT | no | COVERED |  |
| `provisional_v2` | yes | level-rank and younger nulls, constant | PRESENT | no | COVERED |  |
| `ifa_step_prior` | yes | difference vs zero | PRESENT | no | COVERED |  |
| `xfv_statcast_line` | yes | unadjusted AAA lines | PRESENT | no | COVERED |  |
| `xfv_odds_grade_basis` | yes | the re-key and a constant | PRESENT | no | COVERED | loses to the constant, said so |
| `fa_team_fit` | yes | random, payroll-only, behavior-only | PRESENT | no | COVERED |  |
| `fv_outcome_pooled_grade` | yes | the side-neutral inversion | MISSING | no | DEFERRED | an FV-to-outcome curve: PROSPECT_ANCHOR_GATE |

Planted-recovery checks are rare: of the 102 rows in scope, three carry one (positional_ladder's H0 shape simulation, milb_fielding_runs, efv_v2). The sweep records this; it does not retrofit planted checks into closed gates, and section 7 gives each run its own instrument check instead.

## 7. Registered runs

Shared machinery. delta = loss(null) minus loss(model), so a positive delta means the model beats the null. Player-clustered bootstrap (resample unique player keys with replacement; a drawn player brings all his rows), B = 2000, seed 20261022, percentile CI95. Verdict per null: BEATS if the CI95 lies above zero, LOSES if it lies below zero, TIES otherwise. Instrument check in every cell (the planted-recovery requirement applied to this lab): a planted-better arm, halfway from the model to the realized value, must BEAT the model, and a planted-worse arm, the model plus seeded Gaussian noise at the residual standard deviation, must LOSE to it; a cell whose check fails is VOID and adjudicates nothing.

### S1. fa_projection_marcel (Gate 1, WAR)

- Frame: `fa_backtest.run_projection_gate(persist=False, reexport=False)` with `GATE1_COLLECT`, the gate's own WAR pool: targets 2015 to 2025 without 2020, every player with an input season, absent target season scored as 0 for every arm. Stored: WAR MAE 0.5157 against 0.6242 for the 5/4/3 carry-forward, n 20,721, on the eWAR v2 label.
- Nulls: ZERO (predict 0 WAR); POP_MEAN (per target, the mean over that target's scored rows of each row's own prior-season WAR, 0 when absent; known at forecast time, carries no per-player information).
- Primary cell: pooled WAR MAE. Reported, adjudicating nothing: hitters and pitchers apart.

### S2. fa_war_paths_decay and mlb_projections_vets (the horizon eval)

- Frame: the `proj_eval.run_rowmatch` row-matched frame, bases 2017, 2018, 2019, 2021, horizons 1 to 5, identical (player, horizon) rows for every arm, absent target season = 0. Challenger: proj_lgbm_v1 point-in-time bundles (labels through B-1, full quantiles, trained into the private cache). Champion: marcel_decay_v2 (`use_ml=False`). Stored (2026-08-19, before the two-way label repair and the fWAR epoch): h1 MAE 0.5846 challenger against 0.5988 champion, n 8,053.
- Nulls: ZERO path; CARRY_543_FLAT (the Gate 1 baseline, a 5/4/3 weighted mean of the player's own last three seasons of WAR, held flat across all five horizons).
- Primary cell: h1 MAE of the challenger (what `/projections/` serves). Reported beside it: h2 to h5 and the pooled h1 to h5 cell, for both the challenger and the champion (what `/fa/` prices). A tie or loss at h2 to h5 is reported as a finding about the loss, not used to adjudicate the primary.

### S3. draft_slot_curve

- Frame: `tools/fit_draft_slot_curve.py`, the first-8-season curve fitted on the 2005 to 2014 drafts (picks 1 to 500, unsigned excluded, never-MLB scored 0), scored on the 2015 to 2018 holdout. Metric: the artifact's own `holdout_mae`, the unweighted mean over the 12 pick buckets of |bucket prediction minus realized bucket mean|. Stored: 2.73 on the fWAR label (generated 2026-10-03), which the run must reproduce.
- Nulls: FLAT (the pooled first-8 mean of the 2005 to 2014 scored picks, one number for every pick); ZERO.
- Bootstrap: resample holdout picks within each bucket (stratified, so no bucket empties), B = 2000, seed 20261022. Secondary, adjudicating nothing: per-pick mean squared error under the same draws.
- Instrument check: planted-better bucket predictions halfway to the realized bucket means; planted-worse, the curve's bucket values in reversed order.
- Disclosed before the run: the artifact names this holdout right-censored (a 2018 pick debuting 2022 has four observed seasons by 2025) and calls it a diagnostic, not the ship criterion. A level null on a censored holdout favours low predictions, so a TIES or LOSES here is reported with that confound beside it, and the owner question says so.

## 8. Decision rule

For each row run: BEATS_EVERY_NULL if the primary cell's instrument check passes and every null reads BEATS; TIES_OR_LOSES_NULL if the check passes and any null reads TIES or LOSES; VOID if the check fails. A TIES_OR_LOSES_NULL row goes to the owner with options (default first): (a) downgrade the copy validated to provisional and name the null it does not clear; (b) keep the verdict and add the null result to the row's notes; (c) keep the verdict unchanged. Deferred rows go to the owner only where the note asks a question (eta_fg_blend).

## 9. Results

Appended after the run, below this line, with a pointer to `docs/null-comparator-sweep/RESULTS.md`. Nothing above this section changes after the run.

### 9.1 The one run, 2026-10-22 (04:31 to 04:40 UTC)

`python -u tools/null_comparator_sweep_lab.py --run --cache-dir <scratch>`, once, after the fixture dry run; exit 0, stderr empty. Full output: `docs/null-comparator-sweep/RESULTS.md` and `data/null_comparator_sweep.json`. Every cell's instrument check passed (no VOID).

- **S3 draft_slot_curve: TIES_OR_LOSES_NULL.** The frame reproduces exactly (holdout bucket MAE 2.73, stored 2.73, n 1,968 holdout picks). FLAT reads 1.7123 against the curve's 2.7299 (delta -1.0176, CI95 -2.3103 to +0.6581, TIES); ZERO reads 2.3852 (delta -0.3446, CI95 -1.7112 to +1.2894, TIES). Secondary per-pick MSE: FLAT -0.4249 (CI95 -1.4382 to +0.8385), ZERO -0.2188 (CI95 -1.3840 to +1.1907), both TIES. Both point estimates favour the null. The confound named before the run applies: the holdout is right-censored and reads low, which favours low predictions. Owner question SWEEP-Q1.
- **S1 fa_projection_marcel: BEATS_EVERY_NULL.** On the fWAR label the gate's own frame reads model WAR MAE 0.4924 against 0.5874 for the 5/4/3 carry (stored on eWAR v2: 0.5157 against 0.6242), n 20,721. ZERO 0.5784 (delta +0.0861, CI95 +0.0682 to +0.1046); POP_MEAN 0.7660 (+0.2737, CI95 +0.2600 to +0.2877). Pitchers clear ZERO by the least: +0.0243, CI95 +0.0053 to +0.0423 (MAE 0.3997 against 0.4240).
- **S2 fa_war_paths_decay and mlb_projections_vets: BEATS_EVERY_NULL on the primary cell.** Challenger h1 MAE 0.4925 (stored 0.5846 on the pre-repair, pre-epoch label), ZERO 0.6177 (+0.1252, CI95 +0.1045 to +0.1488), CARRY_543_FLAT 0.6252 (+0.1327, CI95 +0.1205 to +0.1462), n 8,053. Reported, adjudicating nothing: the challenger TIES ZERO at h4 (+0.0073, CI95 -0.0051 to +0.0198) and clears it narrowly at h2, h3 and h5; the champion decay path, which `/fa/` prices, beats ZERO only at h1 and pooled, TIES it at h2, h3 and h5 and LOSES at h4 (-0.0226, CI95 -0.0369 to -0.0074). CARRY_543_FLAT loses to both models at every horizon. Owner question SWEEP-Q2 (no verdict change proposed).

### 9.2 Owner questions

- **SWEEP-Q1 (draft_slot_curve, validated).** Its only out-of-sample read ties a flat curve and a zero curve, and both point estimates favour the null; the holdout is right-censored, so the read is confounded toward low predictions. Options, default first: (a) downgrade the copy validated to provisional and name the null it does not clear, keeping the level claim (the hand table undershot resolved 2005-14 means about 3x); (b) keep validated and add this result and its confound to the row's notes; (c) keep the row unchanged. Default (a) changes the registry verdict and summary only; no served number moves.
- **SWEEP-Q2 (fa_war_paths_decay and mlb_projections_vets, validated).** Both clear every null at h1, but MAE on an absent-as-zero label cannot separate the decay path from a zero path past h1 (ties at h2, h3, h5, a loss at h4). Options, default first: (a) keep both verdicts and add a ZERO-path column to the horizon eval's published receipts so out-year accuracy copy is read against it; (b) keep both verdicts unchanged; (c) downgrade fa_war_paths_decay to provisional because `/fa/` prices the decay path, which loses to zero at h4. Default (a) adds a receipt column; no served number moves.
- **SWEEP-Q3 (eta_fg_blend, validated, deferred).** FanGraphs' ETA alone, the source the blend leans on, was registered as NOT scored on the 2024 look frame (a source score over 2025-26 debut rows). On the development vintages it read MAE 0.874 against the blend's 0.981 but marked 263 more active prospects overdue. Options, default first: (a) leave it unscored and say in the row's notes that the blend was never compared with FanGraphs alone on the look frame; (b) authorize one FanGraphs-alone score on the 2024 frame, debut years only; (c) leave the row unchanged.
