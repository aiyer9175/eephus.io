# eTools gate: stat sub-drivers for tool grades, accuracy weighting, and the pitch-rate read

Registration status: REGISTERED

Task ETOOLS (owner asks of 2026-10-15, decision EW3-15 and the eTools ask in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), written 2026-10-15 on branch
efv-conviction-2026-08-08 (lane worktree, base c2519975). Docs only. This is the ONE
registration of the eTools reads, committed alone, before any number on any frame named
here exists.

The owner's asks, verbatim. (1) "Can we derive sub-drivers for tool grades using an atlas
similar to the one we did for eFV? This should effectively be 'eTools', like 'eHIT',
'ePOW', etc. - basically figuring out what other stats correspond to each tool grade
(using the FanGraphs tool grade -> MLB statistical outcomes framework) and using them to
make our tool grades more precise / improved from consensus. Can we accuracy-weight tool
grades as well? Since we're using tool grades as a driver input for eFV, setting up these
sub-drivers and eTools should improve eFV as well." (2) "Can we also check P/PA, P/IP,
P/BF, and PAR for any eFV related correlations that we could use to improve tool grades
and/or drivers?"

**Nothing was scored to write this document.** No candidate was paired with an outcome,
no table was fitted, no frame was counted. Every figure below is a constant, a date, a
seed, or a figure already published in a committed document, cited by location.

Producer: `etools.py` (with `test_etools.py`). Artifacts: `data/_labs/etools/etools_atlas.json`
(every test row), `data/_labs/etools/etools_eval.json` (the verdicts, the accuracy-weighting
arm, the pitch-rate read, the spent marker), the dark preview
`.cache/etools/preview.json`. Results: `docs/tools-2026-10/ETOOLS_RESULTS.md`.

---

## 0. Disclosures

0.1 **What earlier reads already saw.** Look W (`TOOL_IMPLIED_PRODUCTION_GATE.md` Part 8,
2026-10-14) read FanGraphs, MLB Pipeline and Baseball America tool grades against MLB K%,
sprint speed, OAA, arm, ISO, pitcher K% and BB% on board years 2017 to 2024; its source
reweighting was NULL for hit, field and speed. BA2 (`data/ba_tool_grade_eval.json`) read
board years 2020 to 2025. The tool tables (`data/tool_grade_tables.json`) read the grade
to stat relations on a pool that overlaps every frame here. So the grade side of every
estimand below is not new; what is new is each CANDIDATE sub-driver's increment over the
consensus tool grade, which no earlier read computed. The pitch-rate eFV arms `ppa_rel`
and `pbf_rel` were REFUSED at DS-06 on 2026-10-14 (`data/_labs/efv_pitch_rate_admission.json`);
section P re-reads pitch rates in the atlas form, which is a different statistic on
different rows, and that refusal stands for those two arms whatever P finds.

0.2 **EFV_X1 is not on this branch at registration.** The translated, reliability-shrunk
MiLB rates come from `efv_x1_translate.py` at commit 80915e33 (branch
wt-EFV_X1_MLE_TRANSLATION, registration ab1665e9). After this document is committed, the
lane merges 80915e33 (it adds only new files) so `etools.py` can import it. No X1 constant
is changed; X1's own read (no feature added to consensus FV) stands.

0.3 **Imputed snapshot dates.** Every MLB Pipeline snapshot is dated YYYY-01-22 and every
Baseball America snapshot YYYY-02-15 (imputed at ingest). The as-of rule here (seasons up
to Y - 1 for every stat candidate) does not depend on the day inside the preseason
window, so the imputation moves nothing; it is stated because the board-dated FanGraphs
extras (3.4) rest on FanGraphs' own dates.

0.4 **FanGraphs throw.** From 2021 FanGraphs carries arm in `_extras.arm`, not the `throw`
key; Look W read only `throw`. This gate reads the FanGraphs throw grade as `throw`, else
`_extras.arm` (the atlas rule, `efv_w2_scout.py` line 48). Pipeline 2011 to 2013 grades
printed only in report text are read through `efv_w2_scout.report_grades`.

0.5 **Survivorship.** MLB tool outcomes exist only for players who reached the majors. Every
MLB-label number is accuracy AMONG DEBUTS. Each is paired with a second label, the
translated upper-minors outcome (2.2), which exists for debuts and non-debuts alike, and
both are reported side by side with this sentence.

0.6 **Forking paths.** This read tests 13 tools, a fixed candidate list (Part 3) on two
labels, one eTool per tool, three accuracy-weighting arms and the pitch-rate family of
Part P. The count of tests is written into the artifact; BH q runs within each (tool,
label) family as declared, and no candidate, frame or label is added after the read.

---

## 1. Frames

1.1 **Development board years only:** Y in 2011 to 2019 and 2022 to 2024. Board years 2020
and 2021 (R-LV list vintages) are never read. The runner asserts it.

1.2 **Grades.** For each source (fangraphs, mlb_pipeline, baseballamerica), the earliest
snapshot dated in [Y-01-01, Y-05-01) (`source_backtest._WINDOW_START_MMDD`,
`_WINDOW_END_MMDD`), future grades parsed into [20, 80], plus the 0.4 readings. The
consensus tool grade G_c is `consensus.py`'s rule: the unweighted mean across the outlets
publishing the key, rounded to 0.5 (`tool_accuracy_lab.consensus_tool_grade`).

1.3 **Rows.** One row per (board year Y, player) with a G_c for the tool, an identity from
`efv_identity` (outcome-blind; a record whose own mlbam id disagrees with the outcome-blind
id is dropped and counted), and no MLB line in any season before Y (pre-debut). Side from
the board position (pitcher tokens P, RHP, LHP, SP, RP, SIRP, MIRP). Records come from
`efv_vintage_frame.load_universe` (debuts, inactive and active), so non-debuts are rows.

1.4 **Position groups** (descriptive cells and the weighting arm): hitters C, SS, CF, IF
(2B, 3B, IF, UT), COF (LF, RF, OF), 1B/DH from the board position token
(`efv5_atlas.POS_GROUP`); pitchers SP or RP from the player's latest MiLB season up to Y - 1
(games started over games at least 0.5 is SP; no line leaves the group empty).

1.5 **Never** a stratum, cell, key, filter or weight by consensus FV or any source's FV
(`docs/PROSPECT_ANCHOR_GATE.md`). Tool-grade values enter as covariates only.

---

## 2. Labels (the estimands)

2.1 **L_MLB, the framework label (among debuts).** The outcome window is the first three MLB
seasons strictly after Y and no later than 2026; the player's first MLB season is 2024 or
earlier (R-VM never read). Pooled from counts as in `tool_accuracy_lab` (gate 3.3), each
oriented so higher is better:

| tool | L_MLB | floor | source |
|---|---|---|---|
| hit | K% negated | 300 PA | `.cache/fa_statsapi_hitting_*` |
| game_pwr | ISO | 300 PA | same |
| raw_pwr | average exit velocity | 300 PA and 100 batted balls | `.cache/savant_mlb/statcast_batter_*` |
| speed | sprint speed (competitive-run weighted) | Savant qualifier | `.cache/savant_sprint` |
| field | OAA per 1,000 innings, 1B to RF, no catchers | 700 innings | `.cache/savant_oaa`, `data/fielding_innings.json` |
| throw | arm z within (season, IF/OF group), no C or 1B | Savant qualifier, 2020+ | `.cache/savant_arm` |
| pitch_sel | chase rate (oz swing %) negated, season 2026 | 100 PA | `.cache/savant_custom/custom_batter_2026.csv` |
| bat_ctrl | zone contact %, season 2026 | 100 PA | same |
| fb | pitcher K% | 100 BF | `.cache/fa_statsapi_pitching_*` |
| cmd | pitcher BB% negated | 100 BF | same |
| sl | whiff % on SL and ST, pitch weighted over window seasons 2024 to 2026 | 50 pitches of the class | `.cache/savant_mlb/arsenal_pitcher_*` |
| cb | whiff % on CU, KC and SV, same | same | same |
| ch | whiff % on CH and FS, same | same | same |

pitch_sel and bat_ctrl read the one cached season (2026), which is strictly after every
development board year. sl, cb and ch read only the arsenal seasons on disk (2024 to 2026).

2.2 **L_UM, the survivorship label (debuts and non-debuts).** Seasons Y to Y + 2, capped at
2024 (no season after 2024 is read as an outcome), Double-A and Triple-A lines only:

| tool | L_UM | floor |
|---|---|---|
| hit | X1-translated K% negated (league factor and team factor of 80915e33, pooled from counts) | 300 PA |
| game_pwr | X1-translated ISO | 300 PA |
| speed | stolen bases per PA over the level-season mean (sum SB / sum PA x level-season SB/PA) | 300 PA |
| fb | X1-translated pitcher K% | 150 BF |
| cmd | X1-translated pitcher BB% negated | 150 BF |
| raw_pwr | tracked exit velocity, mean (Triple-A 2022+, Florida State League 2021+) | 50 tracked PA |
| pitch_sel | tracked chase rate negated, same levels | 50 tracked PA |
| bat_ctrl | tracked zone contact, same levels | 50 tracked PA |
| sl, cb | tracked breaking-ball whiff rate, same levels | 100 tracked pitches |
| ch | tracked offspeed whiff rate, same levels | 100 tracked pitches |
| field, throw | none: no MiLB fielding or arm measurement exists | |

The tracked labels include the Florida State League (Single-A) and say so; there is no
tracked Double-A.

2.3 **Computable.** A (tool, label) pool is computable with at least 100 players carrying
G_c and the label and at least 3 board years of 20 or more rows; otherwise NOT COMPUTABLE,
named in the artifact.

---

## 3. Candidates (fixed here; nothing is added after the read)

3.1 **As of.** Every stat candidate reads MiLB seasons up to Y - 1 only
(`efv_w2_milb.last_readable_season(Y, None)`), and the runner asserts the latest season it
read for each row. The FanGraphs extras (3.4) are read off the same board snapshot as the
grade.

3.2 **X1 family** (`efv_x1_translate.features(pid, Y, None, side)`): MLE-translated,
reliability-shrunk, Marcel (5, 4, 3) rates over the last three played seasons. Hitters
`k_rw, bb_rw, iso_rw, babip_rw, woba_rw, age_rel_level`; pitchers `k_rw, bb_rw, hr9_rw,
gb_rw, kbb_rw, age_rel_level`.

3.3 **Level-season z family.** For a per-line metric v with exposure e at (pid, season,
level): z = (v - mu) / sd within the (season, level), mu and sd exposure-weighted over the
lines meeting the source's own exposure floor (30 or more lines). The as-of value is the
Marcel (5, 4, 3 by recency) and exposure weighted mean of z over seasons Y - 3 to Y - 1,
times the reliability E / (E + k), E the Marcel-weighted exposure and k the metric's
year-over-year stabilization point: k = n_bar (1 - r) / r, r the Pearson correlation of a
player's season z in consecutive played seasons over seasons up to Y - 1 (pairs with both
seasons at or above the floor), n_bar their mean exposure; r at or below 0.05 makes the
candidate missing at that Y. Members:
- `sb_rel` and `tri_rel` (stolen bases and triples per PA, `.cache/milb_stats`, floor 100 PA);
- `pbp_*` from `.cache/efv4_pbp_discipline` (efv5_atlas.pbp_metrics; floor 100 PA or BF):
  hitters `contact, swstr, swing, two_strike_contact, fstrike_taken`; pitchers `swstr, cstr,
  csw, fstrike, ball_rate`;
- `bb_*` batted-ball rates from `.cache/efv4_pbp_bb` (floor 50 balls in play): hitters
  `fb, pull, hard`;
- `trk_*` tracked components (efv5_atlas.tracking_metrics; Triple-A 2022+, Florida State
  League 2021+): hitters `ev_p90, ev_max, barrel, hard_hit, chase, zone_contact, whiff`;
  pitchers `fb_velo_mean, fb_velo_p95, fb_ivb, extension, whiff_fb, whiff_br, whiff_os,
  chase, zone`;
- the pitch rates of Part P, `ppa_raw, ppa_par` (hitters), `pbf_raw, pbf_par, pip_raw,
  pip_par` (pitchers).
- Fielding position history (`.cache/statsapi_field_season`, games by position up to
  Y - 1, no z): `prem_share` (games at SS or CF over all fielding games) and `arm_share`
  (games at SS, 3B, RF or C over all fielding games), reliability games / (games + 50).

3.4 **FanGraphs board extras**, dated at the board, unshrunk: `fg_sits` (the midpoint of
the sits range), `fg_tops`, `fg_rpm_fb`, `fg_rpm_break`, `fg_avg_ev`, `fg_max_ev`.

3.5 **Per tool:**

| tool | candidates |
|---|---|
| hit | k_rw, babip_rw, woba_rw, age_rel_level, pbp_contact, pbp_swstr, pbp_two_strike_contact, trk_zone_contact, trk_whiff, ppa_raw, ppa_par |
| game_pwr | iso_rw, woba_rw, age_rel_level, bb_fb, bb_pull, bb_hard, trk_barrel, trk_ev_p90 |
| raw_pwr | iso_rw, bb_hard, trk_ev_p90, trk_ev_max, trk_hard_hit, fg_avg_ev, fg_max_ev |
| speed | sb_rel, tri_rel, age_rel_level |
| field | prem_share, age_rel_level |
| throw | arm_share |
| pitch_sel | bb_rw, k_rw, pbp_swing, pbp_fstrike_taken, trk_chase, ppa_raw, ppa_par |
| bat_ctrl | k_rw, pbp_contact, pbp_two_strike_contact, trk_zone_contact, ppa_raw, ppa_par |
| fb | k_rw, kbb_rw, age_rel_level, pbp_swstr, pbp_csw, fg_sits, fg_tops, fg_rpm_fb, trk_fb_velo_mean, trk_fb_velo_p95, trk_fb_ivb, trk_whiff_fb, pbf_raw, pbf_par, pip_raw, pip_par |
| cmd | bb_rw, pbp_ball_rate, pbp_fstrike, pbp_cstr, trk_zone, pbf_raw, pbf_par, pip_raw, pip_par |
| sl, cb | k_rw, pbp_swstr, fg_rpm_break, trk_whiff_br, trk_chase, pbf_raw, pbf_par, pip_raw, pip_par |
| ch | k_rw, pbp_swstr, trk_whiff_os, trk_chase, pbf_raw, pbf_par, pip_raw, pip_par |

---

## 4. The sub-driver statistic

4.1 **Incremental over the consensus tool grade, out of fold.** For (tool, candidate,
label), on the rows carrying G_c, the label and the candidate: the base score is G_c; the
augmented score is the OLS prediction from [1, G_c, candidate] fit on the training rows of
each fold. Folds are board years; a fold's training rows exclude every row of the test
year's players (leave one board year out, player-disjoint). The statistic is
d = rho_w(augmented) - rho_w(G_c), rho_w the n-weighted mean of within-board-year
Spearman over board years with 20 or more rows.

4.2 **Interval.** Player-clustered bootstrap, predictions fixed and players resampled
(efv5_atlas.cluster_weights and within_rho), B 2000, seed 20261023. One-sided 95% lower
bound = the 5th percentile of the draws; p one-sided from the bootstrap sd,
p = 1 - Phi(d / sd). BH q within each (tool, label) family.

4.3 **Permuted floor.** 200 draws, seed 20261024: the candidate shuffled within board year
among the rows carrying it, the whole fold pipeline rerun; floor = the 95th percentile of
the drawn d.

4.4 **Admission, per (tool, candidate).** ADMITTED when all hold:
1. on at least one label: q at or below 0.10, the one-sided lower bound above 0, and d above
   its permuted floor;
2. on the other label, where computable: d above 0;
3. forward selection, ordered by the qualifying label's q then d: the candidate's Spearman
   with every candidate already chosen for the tool, on the rows carrying both, is at most
   0.6 in absolute value;
4. at most 3 per tool.

4.5 **Cells.** Every admission reads the pooled cell. Descriptive cells, read with the same
statistic and never admitting: position group (1.4), level at Y - 1 (the highest level of a
qualified line: low = DSL, CPX, A- and A; A+; AA; AAA) and age band (terciles of X1
`age_rel_level`); a cell needs 100 players.

---

## 5. The eTool

5.1 **Construction.** For tool t with admitted set S (empty S: eTool = G_c, flagged
"consensus"). In each fold (4.1), on training rows:
- each label is put on the grade scale by its TIP table: per-tool-grade-bin medians of the
  label (bins round(G_c / 5) x 5, bins under 15 rows dropped), weighted isotonic (PAVA,
  increasing), linear between bin grade means, flat beyond; y_g = the table's inverse at
  the realized label (gate 1.2, refit here on the fold's training rows);
- for each j in S: zhat_j = a_j + b_j G_c by OLS, and the residual u_j = z_j - zhat_j
  (0 where the candidate is missing). The candidates are already reliability-shrunk (3.2,
  3.3), so a thin record carries a residual near its prior's;
- c by OLS without intercept of (y_g - G_c) on u, on the stacked training rows of both labels;
- eTool = clamp(G_c + sum_j c_j u_j, 20, 80), unrounded; the 80% band is
  eTool +/- 1.2816 sigma, sigma the training residual sd of (y_g - eTool).
The display value rounds UP to the next 5 (the grades rule); eFV reads the unrounded value.

5.2 **eTool PASS.** On each label, out of fold, over every row carrying G_c and the label
(rows with no candidate carry eTool = G_c): d_E = rho_w(eTool) - rho_w(G_c), the 4.2
bootstrap. PASS when the one-sided 95% lower bound of d_E is above 0 on BOTH labels. A tool
without a computable L_UM (field, throw) cannot pass and is reported as such. NO
SUB-DRIVER when S is empty.

---

## 6. Accuracy weighting

6.1 **Arms**, each per tool, out of fold as in 4.1:
- AW0, the equal consensus G_c (the comparator);
- AW1, outlet weights by position group: BA2's estimator (`ba_tool_grade_lab.derive_weights`:
  common-set Spearman relative to the mean, shrunk toward 1 with k 150, clamped 0.6 to 1.5)
  over FanGraphs and MLB Pipeline on the training rows of the group, oriented label L_MLB
  where computable else L_UM; a group under 100 players takes the pooled weight; the
  weighted grade is the weighted mean of the outlets the row carries;
- AW2, AW1 plus the stat reading as a third input: STAT = the fold OLS of y_g on the
  admitted candidates alone, weighted by the same estimator (present only where S is
  non-empty and the row carries a candidate).
6.2 Lags: weights are fit by pooled player-disjoint leave one board year out, not on a
year lag (under lag 3 only board years 2022 to 2024 would carry a resolved weight in the
development frame). 6.3 Each arm is reported with d against AW0 and its interval on both
labels; BEATS CONSENSUS when the lower bound is above 0 on both, else NULL. The arm serves
nothing.

---

## Part P. P/PA, P/IP, P/BF and PAR (EW3-15)

P.1 **Definitions** (`pitch_rates.py`: P/IP line 166, P/BF 174, P/PA 178, PAR 182): per
(player, season, level) line from `pitch_rates.player_lines`, usable level-seasons only
(the tracking guard). raw = the rate; par = the rate over its level-season (role) anchor.
Hitters P/PA; pitchers P/BF and P/IP on the majority role line.

P.2 **As tool sub-drivers:** the rows of Part 3 (3.3 construction) under the 4.4 rule.

P.3 **As direct eFV drivers:** the first atlas's rows and labels (`efv5_atlas.build_tables`,
one row per player, season S and level, consensus FV read in the V = S + 1 window), metrics
`ppa_raw_hit, ppa_par_hit, pbf_raw_pit, pbf_par_pit, pip_raw_pit, pip_par_pit` on the line
itself, the par forms shrunk toward 1 by n / (n + k) (k of 3.3, seasons up to S). Statistic:
`efv5_atlas.score_cell` (incremental over consensus FV, out of fold, player-clustered
CI95), B 2000, seed 20261023, over the atlas cells (side x level x age band x group);
labels reach3 and reach5 on their clean frames, w3 and l6. BH q within (pitch-rate family,
label). Flagged when the increment is above 0, its CI95 lower bound above 0 and q at or
below 0.10 (`efv5_atlas.CANDIDATE_Q`). A flag is a candidate for the EFV_X3 registration;
nothing here enters eFV.

P.4 **Redundancy receipt:** per metric, the Spearman with the line's walk rate and strikeout
rate (level-relative), on the same rows.

P.5 **Grade revisions, descriptive, no outcome:** for board years Y and Y + 1 both in the
development list, the change in the consensus hit, pitch_sel, bat_ctrl and cmd grades
against the player's pitch rate as of Y (Spearman, n).

---

## 7. What follows a verdict

- A PASS builds nothing served: the dark preview `.cache/etools/preview.json`
  (flag `ETOOLS_ON = False` in `etools.py`; with the flag on the same builder writes
  `data/etools.json`) carries eHIT, ePOW, eRAW, eSPD, eFLD, eARM, eSEL, eBAT, eFB, eCMD,
  eSL, eCB, eCH for live prospects, the eTool where it passed and the consensus with
  `"basis": "consensus"` where it did not. The owner decides any flip.
- Passing eTools are pre-declared as ONE arm of the EFV_X3 registration: they replace the
  raw `tool_*` features (`efv_dataset.py`), the `W2S_COLUMNS` and the `TOOL_CELLS`
  (`efv5_combined.py`), and the X1 features that feed an eTool leave X3's own list so a
  stat line is not counted twice. Served eFV (`EFV_V5_COMBINED_ON`) does not move.

## 8. The one look

The runner (`python etools.py --run --gate-sha SHA`) refuses unless SHA names a commit
carrying this file with the status line REGISTERED; it asserts no board year 2020 or 2021,
no MLB first season after 2024 in an L_MLB row, no L_UM season after 2024, no candidate
season at or after Y, and no FV-keyed grouping. `--check` counts rows and candidate
coverage; `--dry-run` runs the reporting path on fixtures. The look begins at the first
statistic that pairs a grade or candidate with a label; it runs once, and the artifact
carries a spent marker. On an exception after that point: no rerun, the look is recorded
as spent, and the question goes to the owner. Never `backtest.run_backtest`, never
`run_monthly` or `build_site`, never a push; nothing served moves.

## 9. Results

(Empty at registration. Results go to `docs/tools-2026-10/ETOOLS_RESULTS.md`.)
