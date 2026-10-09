# Prospect stat-line gate: the arrival line (`prospect_statline`), one look on holdout H

Registration status: REGISTERED

Task TL_3_STATLINE_GATE_REGISTRATION, written 2026-10-09 at HEAD e0d89e38 (branch
efv-conviction-2026-08-08, worktree lane wt-TL_3_STATLINE_GATE_REGISTRATION). Plan: Part 9 of
`docs/master-plan-2026-09-24-final-pass.md`, section 9.4 'Tools: framework, source accuracy, the
power composite, prospect stat projections v2, tools as eFV V2 candidates', subsection 9.4.6
'Prospect stat-line projections' (Part 9 bundle `PLAN.md`; design context in `LANE_C.md` sections
1.5, 1.6, 2.1, 2.6 and 3, which this document overrides wherever they differ; conflicts resolved
by PLAN 9.7, in particular the row 'The label question'). Docs only. This is the ONE registration of
the recorded v2 prospect fork, named `prospect_statline`, committed alone before any number on
its frames exists.

The owner's ask (message 1, 2026-10-01, verbatim): "Can we use tool-implied statistics in
combination with aging curves for prospects to project their stats better, using the FanGraphs
framework (ex. power grade -> ISO)? Can we use our projected MLB-first xwOBA from PROSPX to improve
prospect projections further as well?"

Owner answers this document is written under (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, the
Part 9 table, recommended options accepted under the standing instruction of 2026-10-01): TL-Q6,
"Arrival line on both pages" (the rates with bands on /projections/ and the PROSPX card, beside
what the grades imply and the translated minor league line; the WAR shown stays the served
bust-inclusive number). The label and frame rules are PLAN 9.7 and the unifier amendments U2 to
U5: every label is FanGraphs' WAR from the frozen fWAR vintage, and the stat line's WAR leg stays
on FanGraphs' frame for the whole program.

**Nothing was scored to write this document.** No model was fitted, no input was paired with an
outcome, no cohort, cell or overlap was counted, and no new outcome number appears below. Every
figure in it is a constant, a date, a seed, a threshold, a figure already published in a committed
artifact (cited with its location), or a prediction labelled as one.

Who uses this file:
- TL_8_PROXY_BACKFILL refits `efv_proxy` backward on debut cohorts 2016 to 2021 only (lab artifact
  `data/_labs/proxy_backfill_eval.json`); its guard reads Part 13 of this file.
- TL_11_STATLINE_BUILD_DARK builds `prospect_statline.py` and `test_prospect_statline.py` to this
  document, runs the ONE development read (`data/_labs/prospect_statline_dev.json`), and adds the
  registry row `mlb_projections_prospects_statline` as "registered, development read only".
- TL_17_STATLINE_LOOK runs the look on holdout H once and writes its entry in Part 13.
- TL_18_STATLINE_DISPLAY_FLIP serves what Part 12 allows.

The look runner refuses to score without the sha of the commit that carries this file with the
status line above, alone on its line, reading REGISTERED.

---

## What may be added to this file after this commit

Nothing above Part 13 is edited. Only these dated amendments may be added, each committed alone
and each before the look:

1. The development-read freeze (1.7), written by TL_11 with its dev-read commit: the frozen
   specification of the candidate, never a holdout number.
2. An amendment in the 5c form (`docs/diamond-betting.md`) naming what moved on disk, if an input
   this document names changes between this commit and the look. It changes no threshold, frame,
   candidate, seed, statistic or baseline.

---

## Part 0. Disclosures

**0.1 The development cohorts are spent, and the prior is a loss.** WS-7 (`prospect_path.py`,
artifact `data/prospect_path_eval.json`, registry row `mlb_projections_prospects`) read debut
cohorts 2017 to 2021, scored 2019 to 2021 forward-chained, against the FV-anchored path, on
first-three-season bWAR. Published there: the MiLB-stats ridge won MAE (1.509 against 1.548) and
lost rank (Spearman 0.154 against 0.193), n 487 (`challenger_pooled_oos`, `baseline_pooled_oos`);
LightGBM lost both. The development frame of this gate (3.1) is those same cohorts, so the
development read is a re-read of spent rows and decides nothing; only holdout H (3.2) carries a
verdict. The label differs: WS-7 scored bWAR; this gate scores the frozen fWAR label (2.3).

**0.2 HOLDOUT OVERLAP DISCLOSURE (round 4, leakage 8).** Holdout H is touched once by this gate,
but it is not untouched by the program. Before TL_17's look, three registered looks read realized
MLB lines of players in the 2022 to 2024 debut cohorts:
- look P (TL_5_POWER_COMPOSITE_LOOK, `docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md` Part P):
  ISO, board years 2022 to 2024 among others, debuts up to 2024;
- look T (TL_21_TOOL_TABLE_REDERIVE_LOOK, the same document's Part T once TL_19 registers it):
  AVG, K%, ISO, HR and BB% over FIT MLB seasons 2015 to 2025 and the 2026 holdout season;
- look W (TL_12_TOOL_WEIGHTS_LOOK, the same document's Part W): tool outcomes over board years
  2017 to 2024, debuts up to 2024, MLB seasons through 2026.

Consequences, binding: (a) TL_17 counts the holdout players who appear in each of those looks'
frames from row keys only (player key and debut year, no outcome read) and prints the three counts
and their union with its result; (b) no table fit by look P, T or W (look P's served a, Part T's
candidate tables, look W's weights or TAG tables) is an input or a baseline of
`prospect_statline`, and `test_prospect_statline.py` (TL_11) scans the module for an import or
read of those looks' artifacts; (c) B2's TIP_first tables are fit inside each fold on training
cohorts only (Part 4), and B3's proxy on cohorts up to 2021 only (TL_8); (d) choices in this
document made after those looks' registrations (the stat list, the baselines) were made before any
of them produced a number, so the overlap is of rows read, not of results seen.

**0.3 Served fits that read holdout rows, and how each is kept out.**
- `milb_translation.py` (registry row `milb_translation`, unvalidated): its served fits are
  matched pairs over every debut on disk, holdout cohorts included. Never used as served; refit
  inside each fold (1.1).
- `efv_proxy.py` (registry row `xfv_proxy`): served fit on `COHORT_YEARS = (2024, 2025, 2026)`,
  which reads holdout cohort 2024 and R-VM. Its served fit and its evaluation
  (`data/xfv_proxy_eval.json`) are never an input, a baseline or cited evidence here; only TL_8's
  backward refit is used (1.1).
- `data/tool_grade_tables.json` (TOOL_IMPLIED_PRODUCTION_GATE.md 0.2): its pool overlaps both
  frames. No table in it scores a row here.
- The incumbent (INC, 4.5) prices through `value_framework.p_bucket_given_fv`, whose empirical
  anchors are partly a realized table refit at the epoch's step J. Any holdout player inside that
  fit tilts L2 toward INC, the conservative direction for the challenger. TL_17 counts the holdout
  players inside the anchor's fit cohort (`empirical_anchors._cohort`, the fitted file's
  `cohort_window`) from row keys only and prints the count.

**0.4 Forking paths already spent on this question, counted.** WS-7: four comparisons on the
same rows (the ridge, LightGBM, the calibrated baseline, the intercept-only baseline;
`data/prospect_path_eval.json`). `milb_translation`: four leave-one-out fits (hitter and pitcher
K% and BB%). `efv_proxy`: one forward evaluation per side on R-VM rows, not cited. This document:
none.

**0.5 Survivorship, stated once and repeated beside every headline.** Only players who reached
the majors have a realized MLB line. Every number the look produces is accuracy AMONG DEBUTS,
conditional on reaching MLB, not accuracy over all prospects.

**0.6 R-LV and R-VM.** This gate scores no eFV, consensus or source value; its frames are cut by
debut year. List vintages 2020 and 2021 enter only as the as-of points of the 2020 and 2021 debut
cohorts in the development frame; the R-LV record exists (TOOL_IMPLIED_PRODUCTION_GATE.md 0.3,
commit 1c73c420). R-VM, debut cohorts 2025 and later (`efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR`),
is never read: any such row raises in every mode.

---

## Part 1. The candidate

### 1.1 Inputs and their leakage rules (LANE_C.md 2.6's table, exactly)

| input | source | leakage rule |
|---|---|---|
| TIP_first per stat | `tool_implied.py` (TL_4), TOOL_IMPLIED_PRODUCTION_GATE.md 1.2 point 4 | tables fit on training cohorts only, forward-chained by debut year |
| translated MiLB rates | `milb_translation` fits for K% and BB%; level norms (`level_norms.compute_level_norms`) for ISO and BABIP as league-relative inputs | refit inside each fold; never the served fits |
| xwOBA prior | `efv_proxy` refit backward (TL_8, cohorts 2016 to 2021) | refit inside each fold on that fold's training cohorts; never the served 2024 to 2026 fit |
| age shape | the one aging service, `aging_v3.AgingModel.component_curve(side, comp, bucket)` (LANE B, AG_5) | consumed as served, with `aging="v2"` (U3), frozen at the dev read (1.7) |
| FanGraphs present grades | `snapshots.tools_json._extras.present`, read as TIP_now (TOOL_IMPLIED_PRODUCTION_GATE.md 1.2 point 6) | as of the decision point only (2.1); its own input, never averaged into the future grade |
| playing time | LANE A's component framework (`proj_components.py`, PJ) | LANE A's rule; never the scored player's realized exposure |

Every input is built from data dated strictly before the player's decision point (2.1). Every
fitted input is refit inside each fold on that fold's training cohorts; a fold's test cohort
never enters any fit, table, norm or penalty choice of that fold.

### 1.2 The model

Per stat and side (the stats of 2.2), a stacked ridge: level 0 is the inputs of 1.1, each
expressed as its own prediction of the stat where it has one (TIP_first, TIP_now, the
translation, the proxy) plus the age delta; level 1 is a ridge with an intercept on the
standardized level-0 values, rows weighted by pooled exposure (PA or BF over the window). A missing
input enters as the training mean with a missing indicator. Weights are learned in the model,
never set by hand.

The penalty is chosen by nested forward-chained cross-validation inside the training cohorts:
for each inner year, fit on the training cohorts strictly earlier and score that year; the
penalty minimizing pooled exposure-weighted MAE over the inner years is taken. Grid: 10 to the
power k for k in -3, -2.5, ..., 3 (13 values); a tie resolves to the larger penalty.

### 1.3 Bands

P10 and P90 per player, stat and side: the point prediction plus the 10th and 90th percentiles of
the out-of-fold residuals (realized minus predicted) of the training rows from the inner chain of
1.2. No hand scaling, no smoothing across stats.

### 1.4 WAR

WAR over the first three seasons comes through LANE A's component assembly (`proj_components.py`)
on FanGraphs' frame, for the whole program (U5; PLAN 9.7 'The label question'): the predicted
rates and LANE A's playing time are turned into runs and wins by that assembly (hitters: batting
runs from projected wOBA and PA, positional runs from the as-of position, league and replacement
runs; pitchers: FIP-based WAR from K%, BB% and HR per BF over the projected innings). Components
the stat line does not project (baserunning, fielding) enter at the value the assembly gives a
player with no MLB history, recorded in the dev artifact. WAR is assembled from the point (mean)
predictions; it is never a sum of quantile points, and no WAR band is built by adding rate bands.
It never switches to a house eWAR v3 part.

### 1.5 Playing time

LANE A's heads are veterans-only at this registration (LANE_A.md: "PJ is veterans only"). TL_11
records, before the holdout exists to it, the exposure rule it takes from LANE A's framework for a
player at arrival, and that rule is frozen at the dev read (1.7). It never reads the scored
player's realized PA, BF or innings. If LANE A's assembly cannot take rates and an exposure, TL_11
stops ('BLOCKER: other component framework missing').

### 1.6 Guards inside the module

- Any debut year 2025 or later raises, in every mode (R-VM).
- In development mode, any debut year 2022 or later raises (the holdout is touched once, by
  TL_17).
- The look mode refuses to run without the gate sha of this file at REGISTERED, the dev-read
  freeze (1.7) and a clean spent check (Part 10).

### 1.7 The development read and its freeze

TL_11 runs ONE development read on the development frame (3.1) and writes
`data/_labs/prospect_statline_dev.json` with role "development". With that commit, TL_11 adds
one dated amendment to this file (the list at the top, item 1) that freezes: the input list and
each input's code sha; the penalty grid and the chosen penalties per fold; the aging mode; the
playing-time rule; the assembly constants; the missing-input rule. The look uses that frozen
specification. Any change after the dev read is an amendment committed alone before the look in
the 5c form; a change made after any holdout row has been read voids the look.

---

## Part 2. The unit and the outcomes

### 2.1 The unit

Each debuted player at his last snapshot strictly before his MLB debut date:
`efv_dataset._asof_point(rec, debut_date)`, with the debut date from
`efv_dataset.resolved_debut_date` and its placeholder handling as `efv_dataset` applies it. A
player with no point before his debut leaves every leg and is counted. The side is the as-of side
(hitter or pitcher by the as-of position, `value_framework.is_pitcher_position`). One row per
player; a player is his own cluster.

### 2.2 The rate outcomes

Pooled over the player's first three MLB seasons, the debut season D and seasons D + 1 and D + 2
(calendar years), as event totals over exposure totals:

| side | stats | exposure floor, pooled over the window |
|---|---|---|
| hitters | K%, BB%, ISO, AVG, BABIP, wOBA, xwOBA | 150 PA, per rate |
| pitchers | K%, BB%, HR per BF, BABIP against, xwOBA against | 150 BF, per rate |

Counting stats come from the StatsAPI season lines through
`fa_sources.fetch_statsapi_season_stats(season, group)` (the source the component gate uses for
exposure, `docs/PROJ_COMPONENTS_GATE.md` 8.3 D1). xwOBA is the Savant expected-stats `est_woba`
(`.cache/savant_mlb/expected_batter_YYYY.csv` and `expected_pitcher_YYYY.csv`), exposure-weighted
across seasons by the file's own PA; a window season without its file is fetched by TL_8 (2020)
before the dev read. A row under a rate's floor leaves that rate's rows only, and is counted. A
season of the window with no MLB line contributes nothing to the pooled rate.

### 2.3 The WAR outcome

First-three-season WAR: the sum of the player's fWAR over seasons D to D + 2 from the frozen fWAR
vintage (`fwar_vintage.load()`, `data/fwar_vintage.json`, vintage id 2026-10-02-0341299c20ec,
frozen by EPOCH_D9_FREEZE at 7e34799f), through `war_source` provider `fwar`; never
`.cache/statsapi_saber_*` and never an eWAR provider (U2). A window season with no row counts 0,
so the label is bust-inclusive among debuts. Every holdout row's window ends by 2026, a final
season.

---

## Part 3. Frames

### 3.1 Development frame (spent, 0.1)

Debut cohorts 2017 to 2021, forward-chained: scored test years 2019, 2020 and 2021, each fit on
the debut cohorts strictly earlier, starting no earlier than 2016 (the first Savant expected-stats
season on disk). Training labels are the training cohorts' full windows, as WS-7 used them; no
test player's outcome enters any fit. The 2020 season (60 games) is inside the windows of the
2018 to 2020 cohorts and is flagged beside every per-year number.

### 3.2 Holdout H (one look)

Debut cohorts 2022, 2023 and 2024, read once by TL_17. The model, every input fit, every table,
norm and penalty, and every baseline are fit once on debut cohorts up to 2021 (2016 to 2021 where
the input reaches that far), then applied to all three holdout cohorts together; no holdout
outcome enters any fit. The overlap of 0.2 and 0.3 is printed beside the result.

### 3.3 Never

Debut cohorts 2025 and later (R-VM). No other frame, no re-cut of the holdout, no second holdout.

---

## Part 4. Baselines

Each baseline is fit on the same training cohorts as the model in the same fold, and scored on
identical rows.

| id | baseline | stats it serves |
|---|---|---|
| B0 | the league-average rookie line: the exposure-weighted mean of the stat's pooled first-three-season line over the training cohorts, by side and position group (Part 7) | every stat of 2.2 |
| B1 | `milb_translation` alone, refit on training cohorts | K% and BB%, both sides |
| B2 | TIP_first alone, at the tool the framework table maps to the stat (TOOL_IMPLIED_PRODUCTION_GATE.md 1.1: ISO from game power, AVG and BABIP from hit), tables fit inside each fold on training cohorts only | hitter ISO, AVG and BABIP |
| B3 | the backward-refit proxy alone (TL_8), refit on training cohorts up to 2021 | hitter xwOBA, pitcher xwOBA against |
| INC | the served FV-anchored path, `prospect_path._baseline_first3`'s machinery (`value_framework.p_bucket_given_fv` times `_bucket_season_wars` from the debut age, the first three seasons summed, as `proj_export._prospect_rows` renders), at the as-of consensus FV of 2.1 | first-three-season WAR (L2) |

The best baseline for a stat and side is the eligible baseline with the lowest exposure-weighted
MAE on the scored rows of that frame; choosing it on the scored rows can only make the test
harder for the model. INC is the FV-anchored path as served on the look day (after the
PROSPECT_ANCHOR look), pinned by sha in the record; the as-of consensus FV enters it as one
continuous number and is never binned.

---

## Part 5. Leg L1, the stat line

**5.1 Statistic.** Per stat and side: MAE weighted by the row's pooled exposure, of the model and
of the best baseline (Part 4), on identical rows. d = MAE(best baseline) minus MAE(model), so
positive means the model is better.

**5.2 Interval.** Paired, player-clustered bootstrap: resample players with replacement within
each (side, debut cohort) group, B 2000, seed 20261210; the same draws serve every stat and both
legs. One-sided 95% lower bound of d (the 5th percentile of the draws). One-sided p = (1 + the
number of draws with d at or below 0) / (B + 1).

**5.3 Multiplicity.** Holm at 0.05 within each side's stat family: hitters m = 7 (K%, BB%, ISO,
AVG, BABIP, wOBA, xwOBA), pitchers m = 5 (K%, BB%, HR per BF, BABIP against, xwOBA against).

**5.4 Coverage veto.** The share of the stat's scored rows whose realized pooled value lies in
[P10, P90] (1.3). Outside [0.75, 0.85] vetoes that stat; the veto cannot make a pass.

**5.5 Verdict per stat and side.** PASS when the lower bound is above 0, the stat survives Holm and
coverage is inside [0.75, 0.85]; LOSS when the one-sided 95% upper bound of d is below 0; NULL
otherwise. A stat with fewer than 60 scored rows is NOT COMPUTABLE and named. A NULL is a finding.

---

## Part 6. Leg L2, WAR

**6.1 Statistic.** On identical debuted rows (every holdout row with an INC value and an
assembled WAR), the model's first-three-season WAR (1.4) against INC on the label of 2.3:
- MAE: d_mae = MAE(INC) minus MAE(model);
- rank: d_rho = rho(model) minus rho(INC), with rho the within-(side, debut cohort) Spearman,
  the row-count-weighted mean over the six groups (a group under 20 rows leaves the mean);
- calibration slope: the least-squares slope of realized WAR on predicted WAR, pooled, as
  `prospect_path._calibration` computes it.

**6.2 Interval.** The draws of 5.2; one-sided 95% lower bounds of d_mae and d_rho.

**6.3 Verdict.** PASS when both lower bounds are above 0 AND the model's slope is not further
from 1 than INC's (|slope(model) minus 1| at most |slope(INC) minus 1|, point values). Both
conditions must hold, so no multiplicity correction applies. Otherwise INC retains. This is the
`prospect_path` ship rule, hardened with intervals.

---

## Part 7. Strata, and the FV-cell ban

Reported beside both legs, never adjudicated, each with its n (a stratum under 20 rows prints n
only):
- side;
- debut age band, by whole years of age at debut: 21 or younger, 22 to 23, 24 to 25, 26 or older;
- position group: hitters C, IF (1B, 2B, 3B, SS), OF (LF, CF, RF), DH and other; pitchers SP and
  RP (`value_framework.is_reliever_position`), by the as-of position;
- last pre-debut level: AAA, AA, A+ or below, none (no MiLB season on the ladder).

**NEVER by consensus-FV cell** (`docs/PROSPECT_ANCHOR_GATE.md`): no realized statistic, mean,
residual, cohort count, bust, debut or graduation rate by FV cell, tier or band, and no stratum,
key, label or filter named after one. `test_prospect_statline.py` (TL_11) enforces it by a source
scan of `prospect_statline.py` in the pattern of `test_efv_vintage_frame.py`
`test_no_fv_cell_grouping`, adapted: no name or short string containing `by_fv`, `fv_band`,
`fv_bin`, `fv_cell`, `fv_tier`, `fv_bucket` or `groupby`; no numeric literal on the FV grid (35 to
80 in steps of 5); and the strata keys equal exactly the four above.

---

## Part 8. The expected result, written as a prediction before any number

- L1: PASS for hitter K% (the translation's published leave-one-out r2 0.355, n 349,
  `data/milb_translation.json` `validation.hit_k` at e0d89e38; LANE_C.md cited 0.326, n 297, from
  an earlier build), likely PASS for ISO (the published grade-only Spearman of game power against
  ISO 0.4833, n 703, `data/xfv_tools.json` at e0d89e38; LANE_C.md cited 0.4961, n 606, from an
  earlier build); BB% and the pitcher rates are coin flips; AVG, BABIP and wOBA are expected NULL.
  Both cited figures read rows that overlap these frames (0.3) and are priors, not evidence.
- L2: a tie or a rank loss against INC (WS-7, 0.1), so the FV-anchored WAR stays served and the
  stat line ships, if at all, as components only.
- The proxy's increment over its own inputs is expected near zero (LANE_C.md 1.5 point 2).

These predictions bind nothing; they are written so a result cannot be read as a surprise after
the fact.

---

## Part 9. The look date

**9.1 The condition (orchestrator decision EPOCH-NOW, 2026-10-02).** THE FIRST DAY on which all of
these hold:
1. TL_11_STATLINE_BUILD_DARK has landed and its dev-read commit (with the 1.7 freeze) is at least
   14 days old;
2. the PROSPECT_ANCHOR look record exists in `docs/PROSPECT_ANCHOR_GATE.md` section 18 'Results',
   dated an earlier day (that look's own day is the later of 2026-11-20 and 14 days after the
   step Z entry of 2026-10-03, by its section 14);
3. the frame named in 3.2 is complete: the 2026 season files the runner reads were written after
   the 2026 regular season ended (it ended 2026-09-27), and the runner records each input's
   sha256;
4. no other registered look is recorded that day, and the day is not one another registered gate
   fixes for its own look (`docs/*GATE*.md` and `docs/**/*GATE*.md`, `docs/diamond-betting.md`,
   the U1c floor list, including look P, look T and look W days), nor an excluded date.

The plan's earlier floor of 2026-12-10 is replaced by this condition (default taken under
EPOCH-NOW, as TOOL_IMPLIED_PRODUCTION_GATE.md P.10 and W.11 did). A later day that meets the same
conditions reads the same rows and needs no amendment; an earlier day voids the look.

**9.2** Never on the day of the eFV reserved read or of the PROSPECT_ANCHOR look.

**9.3** Projections inputs are not touched on a PROJ look day (`docs/PROJ_PATH_SHAPE_GATE.md`).

---

## Part 10. The one-look rules and the crash protocol

1. The look runs ONCE. A look entry in Part 13, or a spent marker in
   `data/prospect_statline_eval.json`, makes the runner refuse.
2. First, a dry run of the whole reporting path on fixtures carrying None values (`--dry-run`),
   which reads no real row and must complete.
3. Then tee stdout and stderr to the task's output directory before anything else runs.
4. Before any score the runner asserts: the gate sha names a commit carrying this file with the
   REGISTERED status line; the 1.7 freeze exists; no debut year at or after 2025; no FV-keyed
   grouping; the label is the frozen vintage of 2.3; and it records the sha256 of every input at
   start and end.
5. **Crash protocol.** On any exception after scoring began: stop without rerunning, mark the look
   spent in `data/prospect_statline_eval.json`, write OWNER_QUESTION.md in the task's output
   directory, and end with 'BLOCKER: answer TL-STATLINE-CRASH'. No second run, seed, frame,
   baseline or estimator.

---

## Part 11. Bans

- No statistic by consensus-FV cell (Part 7), anywhere, in any mode.
- No R-VM row (debut 2025 or later), ever, not even as a smoke test.
- No holdout row in development mode; no second holdout read.
- Never `value_framework.py --fit`; never `backtest.run_backtest`.
- No projections input touched on a PROJ look day; no projections retrain
  (`tools/train_proj_models.py`).
- No table fit by look P, T or W as an input or a baseline (0.2).
- No served fit of `milb_translation` or `efv_proxy` as an input or a baseline (0.3); no table
  from `data/tool_grade_tables.json` scores a row.
- No label from `.cache/statsapi_saber_*` or from an eWAR provider; no house eWAR v3 part.
- No sum of quantile points into WAR.
- No served file written by the look; the look writes Part 13, the eval artifact and the registry
  row only.

---

## Part 12. What each verdict serves

- **L1 PASS for at least one stat.** TL_18_STATLINE_DISPLAY_FLIP serves the arrival line behind
  `SERVE_PROSPECT_STATLINE` (class 2, default off until the flip) under owner answer TL-Q6
  (a), "Arrival line on both pages": /projections/ prospect rows and the PROSPX card, a row headed
  "If he reaches the majors, first three seasons", only the stats that passed, with P10 to P90
  bands, beside "What his grades imply" (TIP_first) and "What his minor league line translates
  to". The WAR cell stays the served bust-inclusive FV-anchored number with its existing label.
- **L1 fails everywhere.** The FV-anchored path stays the only prospect projection, recorded in
  Part 13; nothing is served.
- **L2 PASS.** An owner question at that time; never an automatic WAR change.
- `SERVE_PROSPECT_STATLINE` is distinct from `SERVE_PROSPECT_ANCHOR_V2`
  (`value_framework.py`); neither flag reads the other.

---

## Part 13. Results

EMPTY AT REGISTRATION. The look entry is written here by TL_17, pasted verbatim from its runner
and dated: L1 per stat and side (MAE of the model and of the best baseline, which baseline, d, its
lower bound, p, the Holm step, coverage, the verdict); L2 (MAE and within Spearman of the model
and INC, the lower bounds, both calibration slopes, the verdict); the strata of Part 7; the
overlap counts of 0.2 and 0.3; the survivorship sentence; the row accounting; the input sha256
list; the gate sha and the INC sha. Artifact `data/prospect_statline_eval.json` (a registry eval
artifact that ships); registry row `mlb_projections_prospects_statline`. Nothing above this part
is edited once anything is written below it, except by the amendments listed at the top.
