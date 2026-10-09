# Tool-implied production gate: look P (the power composite) and look W (tool source weights and TAG)

Registration status: REGISTERED

Task TL_2_TOOL_GATE_REGISTRATION, written 2026-10-09 at HEAD 572c3fda (branch
efv-conviction-2026-08-08). Plan: Part 9 of `docs/master-plan-2026-09-24-final-pass.md`, section
9.4 'Tools: framework, source accuracy, the power composite, prospect stat projections v2, tools as
eFV V2 candidates', subsections 9.4.2 to 9.4.5 (Part 9 bundle `PLAN.md`; design context in
`LANE_C.md` sections 2 and 3, which this document overrides wherever they differ, in particular
`LANE_C.md` 2.4's superseded list of look W primaries). Docs only. This is the ONE registration of
look P and look W, committed alone, before any number on either frame exists.

The owner's asks (2026-10-01, verbatim). Message 2: "Similar to the way we do WAG, can we check each
debuted player's statistical production against their tool-implied statistical production (using
the FanGraphs framework, ex. power tool -> ISO, hit tool -> batting average, etc.) to see where
different sources miss or hit more based on tools, and then accuracy-weight our tool grades
accordingly? After doing so, if this proves to improve tool grade accuracy, can we then check if
tool grades can be used as eFV drivers / how they should be weighted?" Message 1: "Right now, we are
only using raw power grade for our power tool composite grade and across the site. We have the data
for "Game Power" tool on FanGraphs as well. Can we incorporate game power in some way and test to
see if it corresponds as an eFV driver? Can we blend game power into our power composite grades to
make them more accurate (and then test our power tool as an eFV driver)?"

Owner answers this document is written under (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, the
Part 9 table, recommended options accepted under the standing instruction of 2026-10-01): TL-Q2,
K% is the hit tool's primary stat and batting average is reported beside it on the same rows; TL-Q4,
PWR means production power and answers to realized ISO; TL-Q1 (a), tool features are pre-declared
for the next registration and never join V2 here; TL-Q5, a passing tool weight shows on served
chips through a display key. Baseball America's single Power grade stays mapped to `game_pwr`
(`baseballamerica_csv.py` BA_POWER_TARGET), as measured; that is fixed and was not asked.

**Nothing was scored to write this document.** No grade was paired with an outcome, no table was
fitted, no cohort or cell was counted, and no outcome number appears below. Every figure in it is a
constant, a date, a seed, a count of earlier looks, or a prediction labelled as one. Earlier
outcome results are cited by their location, never restated.

Who uses this file:
- TL_4_TOOL_LAB_BUILD builds `tool_implied.py` and `tools/tool_accuracy_lab.py` to it, adds the
  registry rows (`tool_implied_production`, `tool_source_accuracy`, `power_composite_v2`), and
  writes Part 4 as a dated amendment.
- TL_5_POWER_COMPOSITE_LOOK runs look P once and writes its entry in Part 8.
- TL_12_TOOL_WEIGHTS_LOOK runs look W once and writes its entry in Part 8.
- TL_19_TOOL_TABLE_REDERIVE_REGISTRATION adds the heading '## Part T' (left free here) as a dated
  amendment.

The look runners refuse to score without the sha of the commit that carries this file with the
status line above, alone on its line, reading REGISTERED.

---

## What may be added to this file after this commit

Nothing above Part 8 is edited. Only these dated amendments may be added, each committed alone and
each before the look it touches:

1. Part 4's k_m constants (TL_4), before either look.
2. '## Part T', the re-derived tool table gate (TL_19), and Part T's dated MDE95 amendment (TL_4,
   computed on FIT rows only, committed alone before the look T date TL_19 registers).
3. Look W's fallback amendment (W.12), only if the fallback becomes active.
4. An amendment in the 5c form (`docs/diamond-betting.md`) naming what moved on disk, if an input
   this document names changes between this commit and a look. It changes no threshold, frame,
   candidate, seed or statistic.

---

## Part 0. Disclosures

**0.1 BA2 read tool grades against outcomes on rows this gate reads again.** Lane BA2
(`docs/efv-2026-08-07b/TOOL_GRADE_WEIGHT_GATE.md`, lab `tools/ba_tool_grade_lab.py`, artifact
`data/ba_tool_grade_eval.json`, registry row `ba_tool_grade_weight`) ran on 2026-08-08 over board
years 2020 to 2025 (its section '### 8.2 ARM A'). List vintages 2020 and 2021 were reserved for the
eFV v2 read on 2026-09-24 (`efv_vintage_frame.RESERVED_LV`), after BA2 ran. That is the B9a pattern
(`docs/efv-v2/EFV_V2_GATE.md` '## 5. Disclosures'): source scores read on R-LV rows before the
reservation. Consequence: BA2's hit result may not be credited to any eFV V2 candidate, and look W
reads BA2's own board years again (W.9). A second exposure follows from BA2's frame definition and
is stated here as an inference, not a count: a board year 2025 row carries an outcome only from MLB
seasons after 2025, so every such row BA2 scored belongs to a player who debuted in 2025 or 2026,
which is R-VM (`efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR`), read before that reservation too. Neither
look here reads a board year after 2024 or a debut year after 2024.

**0.2 The tool tables' pool overlaps both frames.** `docs/efv-2026-07-30/TOOL_GRADE_TABLES.md`
(artifact `data/tool_grade_tables.json`, registry row `tool_grade_tables`) fitted grade-to-stat
tables on 2026-07-30 over its P-MLB pool (every debuted player with a pre-debut consensus grade,
measured over the MLB seasons on disk that day) and its P-AAA pool. That pool includes players of
list vintages 2020 and 2021 and of the 2025 and 2026 debut cohorts, and it read hit against K%,
game power against HR per 600, raw power against exit velocity, speed against stolen bases, field
against OAA and command against walk rate. Consequences: (a) no table in that artifact scores any
row here; every TIP table in this gate is refit on the rows Part 1 names; (b) two choices this
document carries were made with that artifact's results in view, and are disclosed in 0.5.

**0.3 The R-LV record, and where it lives.** Wherever this document (and the Part 9 specs that
point at it) says "the R-LV record", it means the one read of list vintages 2020 and 2021 under
`docs/efv-v2/EFV_V2_GATE.md`. That file's section '## 11. Registration by decision EW2-6' (dated
2026-10-08) states that its '## 9. Results' stays empty and that the reserved numbers live in
`docs/efv-v2/EFV_V3_BACKTEST.md` section '### 5.1 R-LV, list vintages 2020 and 2021' and in
`data/_labs/efv_v3/efv_v3_confirm.json`. That read ran on 2026-10-08 on the gate sha e7931ce4 and
was recorded at commit 1c73c420. Decision EW2-10 (2026-10-08) records R-LV and R-VM as spent. So
the R-LV record EXISTS at this registration: it is the section 5.1 entry at commit 1c73c420, which
is the commit a look runner takes as `--rlv-record`. An entry under EFV_V2_GATE.md '## 9. Results',
should one ever be written, counts as the record too. This reading is a default taken at
registration; it is recorded as an owner question (TL2-Q1) in the task report, with the literal
reading as the alternative. R-VM stays closed to both looks whatever the answer: no debut year after
2024 enters either frame.

**0.4 Forking paths, counted, against which every number here is read.**
- BA2: ten gate cells (five tools by two arms), each with two primary comparisons; lag 2 and lag 1
  sensitivity runs of its Baseball America arm (five tools at each lag) and of its powered arm (the
  lag table in its '### 8.5'); seven controls (C6.1 to C6.7) plus its self-added C6.1b and C0; and
  the B4 outcome read of BA Power, FanGraphs game power and FanGraphs raw power against ISO.
- TOOL_GRADE_TABLES: 47 tables, 13 audits, 14 context offsets and 3 inventions (its '## 2.
  Results' header line).
- The frame projectability lane of 2026-09-25 (`DECISIONS_FOR_OWNER.md`, 'RESULT frame
  projectability'): 21 outcome probes, including the hitter read that located a lean-body
  raw power effect.
- Game power as an eFV driver: four arms in `data/xfv_arm_ledger.json` (the D-1 free key, the two
  C3 pairs, `iso_rel`), on the WAR label, not on these outcomes.
- Lane D (`docs/efv-2026-07-30/TOOL_NORMALIZATION_VERDICT.md`): grade-against-grade reads only, no
  outcome; listed so the record is whole.
- This document: none. `docs/tools-2026-10/POWER_SURFACE_AUDIT.md` (TL_1) computed no outcome
  statistic either.

**0.5 Choices made with earlier outcome results in view.**
- Hit's primary stat is K% (TL-Q2). It was chosen after TOOL_GRADE_TABLES '### 2.5' showed the
  hit grade ordering MLB strikeout rate more strongly than batting average on a pool that overlaps
  look W's rows.
- Look P's target is ISO (TL-Q4), and its prediction (P.9) was written from BA2's B4 read and the
  frame projectability lane, both on rows that overlap look P's frame.
- Look W's four primaries were chosen as the pairs BA2 did not read; BA2's three read pairs are
  secondary rows here precisely because their outcome is already known (W.4).

**0.6 Survivorship, stated once and repeated beside every headline.** Only players who reached the
majors have a realized MLB quantity. Every number either look produces is accuracy AMONG DEBUTS
(BA2 C6.6), not accuracy over all graded prospects.

---

## Part 1. The framework table and tool-implied production

### 1.1 The framework table

"Future grade" is the canonical consensus grade (`fangraphs_csv.py` docstring). A present grade
exists for FanGraphs only (`snapshots.tools_json._extras.present`).

| tool | FanGraphs-framework stat (the owner's mapping) | the unit this gate measures | secondary units, descriptive | sources with grade history | role here |
|---|---|---|---|---|---|
| hit | AVG | MLB K% (lower is better), TL-Q2 | AVG (on the same rows), BABIP | FanGraphs 2017+, MLB Pipeline 2011+, Baseball America 2023+ | look W primary |
| game_pwr | ISO, HR per PA | MLB ISO | HR per PA, barrels per PA | every outlet (each single "Power" maps here) | look P target; look W secondary only |
| raw_pwr | exit velocity | MLB average exit velocity | ev50, max EV, hard-hit rate | FanGraphs only (plus ESPN rows) | look P secondary; TAG table only |
| speed | SB, sprint speed | Savant sprint speed (ft/s) | SB per 600 PA, triples | FanGraphs, MLB Pipeline, Baseball America | look W primary |
| field | OAA or DRS by position | OAA per 1,000 innings, catchers excluded | by position group (descriptive) | FanGraphs, MLB Pipeline, Baseball America | look W primary |
| throw | arm runs | Savant arm strength (mph), by position group | none (no pop time on disk) | MLB Pipeline, Baseball America, FanGraphs where present | look W primary |
| fb | velocity, K% | MLB K% (pitchers) | first-season velocity | FanGraphs, MLB Pipeline, Baseball America | look W secondary only |
| cmd | BB%, zone rate | MLB BB% (pitchers, lower is better) | none | FanGraphs, MLB Pipeline, Baseball America | look W secondary only |
| pitch_sel, bat_ctrl | chase rate, zone contact | chase%, zone contact% (`data/hitter_leaderboards.json`) | bat tracking 2024+ | FanGraphs only | TAG table only |
| sl, cb, ch | pitch whiff and run value | none adjudicated | per-pitch whiff% | FanGraphs, MLB Pipeline, Baseball America | descriptive only |
| frame, athl, delivery | none | no measurement (TOOL_GRADE_TABLES '### 2.11') | none | FanGraphs only | none |

A single-source tool (raw_pwr, pitch_sel, bat_ctrl) has no weight to derive and appears only as a
TAG table.

### 1.2 Tool-implied production, exact definition

For tool t, stat m, grade g (unrounded; the consensus grade or one source's grade) and context c:

1. **TIP_mat(t, m, g), the maturity table.** Read from per-grade-bin medians of m over a declared
   row set, in the MLB age-26-and-over frame where the row set supports it, else the full-season
   frame. Bins are `round(g / 5) * 5`; a bin with fewer than 15 rows is THIN and dropped
   (TOOL_GRADE_TABLES '### 1.3'). The medians are smoothed by weighted isotonic regression (PAVA,
   weight = bin n, oriented by the stat's expected sign), interpolated linearly at each bin's
   `grade_mean`, and held flat beyond the last non-thin bin. No extrapolation.
2. **A table is a function of its rows.** Every use below names the rows its table is fit on, and a
   table that scores a row is never fit on a row of that row's board year or player (2.1).
3. **TIP_f3(t, m, g).** The step 1 table fit on the same exposure frame as the TAG outcome: m pooled
   over each player's first three MLB seasons strictly after his board year (3.3). TAG reads TIP_f3,
   so TAG needs no age curve.
4. **TIP_first(t, m, g, a).** TIP_mat plus delta(m, a to 27, bucket), the stat-specific age change
   from arrival age a supplied by `aging_v3` (U3: called with aging="v2" until
   `docs/AGING_V3_GATE.md` records a pass; never a local curve). Where the service carries no curve
   for m, the table's first-season frame is read directly and the row says so. TIP_first belongs to
   the stat-line model (`docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md`); neither look here
   reads it.
5. **TIP_level, point in time.** At AAA, TIP_AAA = TIP_MLB plus the within-player AAA-minus-MLB
   offset of the stat. Below AAA, TIP is league-relative (TIP_MLB divided by the MLB league mean,
   times the level-season mean from `level_norms.compute_level_norms`) and labelled uncalibrated.
   For an eFV vintage V every input is built from seasons up to V - 1 only: the level norms with an
   explicit as-of date of December 31 of V - 1 (never the function's default of today), the AAA ISO
   offset measured within player on seasons up to V - 1 (never
   `data/tool_grade_tables.json` `context_offset_aaa_minus_mlb`, a 2023-onward concurrent frame),
   and the TIP table from MLB seasons up to V - 1 of players who debuted before V. The build raises
   if any input season is at or after V, or is 2026 or later. Neither look here reads TIP_level; it
   is defined here once for the features of PLAN 9.4.5.
6. **TIP_now(t, m, present).** TIP_mat at a FanGraphs present grade, the MLB-equivalent read today.
   It is its own input to the stat-line model and is never averaged into the future grade.

---

## Part 2. Tool above grade (TAG) and the three source metrics

### 2.1 The per-player triple

For a debuted player p, source s, tool t, stat m, at s's grade for p at board year Y:

- **TAG gap**: realized m (3.3) minus TIP_f3(t, m, s's grade), in stat units, oriented so that
  positive means the player produced above what the grade implies ("ISO above grade").
- **TAG percentile (the headline)**: the mid-rank percentile of p's realized m among the table's fit
  rows in the same grade bin as s's grade (the PIT; 0.5 means on grade). Not computed in a thin bin.
- **Regressed TAG** (the shrunk gap): gap times w, w = E / (E + k_m), with E the player's exposure
  in the stat's own unit (PA, competitive runs, innings, throws) and k_m from Part 4. Not computed
  for a stat Part 4 names NOT COMPUTABLE.

TIP_f3 for scoring board year Y is fit on the frame's rows of every OTHER board year, with Y's
players removed (leave one board year out, player-disjoint), on the consensus grade; the table is
then read at s's grade.

### 2.2 The three source metrics, per (source, tool)

1. **Ordering**: the within-board-year Spearman of s's grade against realized m on the common set
   (BA2's M1 in the V2 within form: the n-weighted mean of per-year rho). Ordering is the ONLY input
   to a weight, through BA2's estimator (W.1).
2. **Bias**: the mean regressed TAG and the mean of (TAG percentile minus 0.5). Displayed, never
   applied as an offset (Lane D: per-source offsets do not replicate).
3. **Error**: the mean absolute regressed TAG, in stat units. Displayed.

---

## Part 3. Identity, vintage, exclusions, thin rules, survivorship

### 3.1 Identity
`efv_identity` outcome-blind resolution (DS-03; bug B4, where outcome-aware resolution inflated a
read), mlbam ids only. A row whose id resolves only through an outcome-bearing path is dropped and
counted in the artifact.

### 3.2 Vintage
Board year Y takes each source's earliest snapshot dated in [Y-01-01, Y-05-01)
(`source_backtest._WINDOW_START_MMDD`, `_WINDOW_END_MMDD`), one grade per (source, player, tool, Y),
grades parsed into [20, 80] from `snapshots.tools_json` with `_extras` stripped. The player must not
have debuted before Y-01-01 (pre-debut). Outcome seasons are strictly after Y (BA2's section 1.2
departure, kept). The consensus grade at Y is `consensus.py`'s per-tool rule (the unweighted mean
across the outlets publishing that key, rounded to 0.5) applied to those grades.

### 3.3 Outcome window
A player's outcome window is his first three MLB seasons strictly after Y and no later than 2026
(fewer if fewer exist), each season counted if he appears in it at the stat's source. Rate stats are
pooled over the window from counts (ISO = (TB - H) / AB; K% = SO / PA; BB% = BB / BF for pitchers),
so the pooling is exposure-weighted. MLB rate lines come from `.cache/fa_statsapi_hitting_*.json`
and `.cache/fa_statsapi_pitching_*.json`; Statcast units from
`.cache/savant_mlb/statcast_batter_*.csv`; sprint speed from `.cache/savant_sprint/`; arm strength
from `.cache/savant_arm/`; OAA from `.cache/savant_oaa/` with innings from
`data/fielding_innings.json`. No WAR, no WAR component and no label is read by either look (U2 does
not bind a WAR label here because none is used).

### 3.4 Exclusions
- Debut year 2025 or later (R-VM): always excluded, asserted before any score.
- Board years 2020 and 2021: excluded until the R-LV record (0.3). The record exists at this
  registration, so look W admits them (W.8). Look P's frame excludes them by its own definition
  (P.2).
- No row is grouped, filtered, binned or weighted by consensus FV or any source's FV
  (`docs/PROSPECT_ANCHOR_GATE.md`). The grade bins of Part 1 and Part 2 are TOOL grade bins.

### 3.5 Thin rules
- A (source, tool, board year) cell under 20 rows reports n and range only and leaves the
  within-year mean.
- A (source, tool) pool under 100 players is NOT COMPUTABLE, named in the artifact.
- A grade bin under 15 rows is thin (1.2 step 1).

### 3.6 Survivorship
The sentence of 0.6 is printed beside every headline number either look writes.

---

## Part P. The power composite look

**P.1 Candidates** (a fixed list; each a pure function of the board-year consensus grades of 3.2):
- **C0**, the served v12 formula (`consensus.py` at '# v12'): round-half(mean(game consensus, raw
  consensus)).
- **C1**, production power: the game consensus alone.
- **C2**, the accuracy-weighted blend: round-half(a times game consensus + (1 - a) times raw
  consensus), a on the grid 0.0, 0.1, ..., 1.0. For scoring board year Y, a is fit by leave one board
  year out on the other board years of the frame, with Y's players excluded from the fit
  (player-disjoint), maximizing the pooled Spearman with realized ISO; ties on the grid resolve to
  the a nearer 0.5. The served a, written beside the verdict, is the fit on all of the frame's board
  years; it is reported and is not what the test scores. If the served a is 1.0, C2 serves as C1
  (PLAN 9.4.5).

**P.2 Frame.** Hitters carrying BOTH a game consensus and a raw consensus at board years 2017 to
2019 and 2022 to 2024, debut year at most 2024, with at least 300 MLB PA pooled over the outcome
window of 3.3. Board years 2020 and 2021 are out of look P by this definition, as the specification
wrote it before the R-LV record existed; admitting them is owner question TL2-Q2 in the task report,
and would need an amendment in the form of the list at the top, before the look.

**P.3 Outcome.** MLB ISO pooled over the outcome window (3.3). TL-Q4's answer names ISO, so no
substitution applies.

**P.4 Statistic.** Within-board-year Spearman of the candidate against ISO, as the n-weighted mean
of per-year rho (board years under 20 rows leave the mean, 3.5). d(C1) = rho(C1) minus rho(C0) and
d(C2) = rho(C2) minus rho(C0), on identical rows. Interval: paired, player-clustered bootstrap (a
player recurs across board years), B 2000, seed 20261021, one-sided 95% lower bound.

**P.5 Floor.** Draw 1,000 times: in each row, swap the game and raw consensus with probability 0.5,
re-run the whole pipeline (C2's cross-fit included) and recompute d. The floor F(C) is the p95 of
|d| over the draws. The same draws give the AUC floor (P.6) and the permutation p (add-one corrected
share of draws with d at or above the observed d).

**P.6 Pass, per candidate.** All of:
1. the one-sided 95% lower bound on d is above 0;
2. d is at least 2 times F(C) (marginal is FAIL);
3. the contributor AUC is not worse beyond its own floor: AUC of the candidate for the top ISO
   tercile within board year (n-weighted over years), d_auc = AUC(C) minus AUC(C0), and the
   candidate is vetoed if d_auc is below minus the p95 of |d_auc| over the P.5 draws (veto only;
   it cannot make a pass);
4. Holm across C1 and C2 at 0.05 on the permutation p of P.5.

**P.7 Serve rule.** C2 if C2 passes; else C1 if C1 passes; else C0 retains. A pass serves only
through Part 7.

**P.8 Secondary reads, never deciding.** The same statistic, interval and floor on HR per PA,
barrels per PA and average exit velocity over the same rows and window (Statcast units from 2016;
a row without them leaves that read only). Reported beside the verdict; none can pass, veto or
change the serve rule.

**P.9 The expected result, written as a prediction before any number.** C1 and C2 ahead of C0 by
+0.01 to +0.03 in within-year Spearman on ISO, with the fitted a near 0.7 to 1.0; C0 ahead of C1 on
average exit velocity. Basis: BA2 B4 and the frame projectability lane (0.4, 0.5), both on
overlapping rows, both unresolved. A NULL is a finding: C0 retains and the copy says so.

**P.10 Look date (orchestrator decision EPOCH-NOW, 2026-10-02).** THE FIRST DAY after
TL_4_TOOL_LAB_BUILD lands (its build commit and its Part 4 amendment both committed) on which the
frame named in P.2 is complete and no other registered look is recorded that day. The frame is
complete when the 2026 MLB season files the runner reads were written after the 2026 regular season
ended (the 2026 season is final); the runner records each input's sha256. The day is also on or
after 2026-10-10 (seven days after the step Z entry of 2026-10-03, already passed), is never a day
another registered gate fixes for its own look (`docs/*GATE*.md` and `docs/**/*GATE*.md`, the
U1c floor list, this program's look T day), and is never the day look W runs. The plan's earlier
floor of 2026-10-21 is replaced by this condition. A later day that meets the same conditions reads
the same rows and needs no amendment; an earlier day voids the look.

**P.11 The record.** One Part 8 'Look P' entry pasted verbatim from the runner: per candidate d,
lower bound, floor, ratio to floor, d_auc and its floor, permutation p, Holm step and verdict; the
fold-wise and served a; rows by board year; the secondary reads; the survivorship sentence; the
input sha256 list; the gate sha. Artifact `data/power_composite_eval.json` (a registry eval
artifact that ships).

---

## Part W. The source-weight look

**W.1 Estimator and gate, imported by name, never retyped.** From `tools/ba_tool_grade_lab.py`
and `source_backtest`: `MIN_LAG_YEARS` = 3, `WEIGHT_SHRINK_K` = 150, `WEIGHT_CLAMP` = (0.6, 1.5),
`SPEARMAN_FLOOR` = 0.05, fewer than 60 common rows returns equal weights, a year whose derived
weights are all 1.0 is skipped; the common-set rule; metrics M1 and M2 (BA2 '### 4.1'); gate
clauses G1 to G5 (BA2 '## 5. THE SHIP GATE'; marginal is FAIL); the permuted-source-label floor
(C6.1, 1,000 draws); the player-clustered paired bootstrap (B 2000) at BA2's seeds (`SEED` 8641,
`SEED_ALT` 1337 for C6.5); the stop clauses of BA2 '### 5.1', with Part 6's stricter lag ban.
Weights are indexed by tool, never pooled.

**W.2 Primaries, one per weightable tool that BA2 did not read** (round 4, leakage 5):

| tool | primary stat (oriented so higher is better) | exposure unit |
|---|---|---|
| hit | MLB K%, negated (TL-Q2, answered 2026-10-01) | PA |
| speed | Savant sprint speed | competitive runs |
| field | OAA per 1,000 innings, pooled across positions, catchers excluded | innings |
| throw | Savant arm strength, by position group | throws |

**W.3 Outcome definitions** (over the 3.3 window):
- hit: SO / PA pooled; 300 PA floor (look P's hitter floor).
- speed: the season `sprint_speed` values weighted by `competitive_runs`; a season counts when the
  cached leaderboard carries the player (Savant's own qualifier, no added floor).
- field: the sum of `outs_above_average` over the cached position files for 1B, 2B, 3B, SS, LF, CF
  and RF (`oaa_YYYY_pos3` to `pos9`; never `pos2`) divided by the innings at those positions in
  `data/fielding_innings.json`, times 1,000; floor 700 innings pooled, the full-time line of
  TOOL_GRADE_TABLES '### 2.7' (a self-added threshold, declared here).
- throw: position group infield (`arm_inf`, weight `total_throws_inf`) or outfield (`arm_of`,
  weight `total_throws_of`), the group with more throws in the window; catchers and first basemen
  excluded; each season's value is standardized as a z within (season, group) over every cached
  leaderboard row of that season and group, then throw-weighted; seasons before 2020 carry no arm
  read (`.cache/savant_arm/` begins in 2020), so a window that ends before 2020 has no outcome. The
  by-position-group table is descriptive.

**W.4 Secondary rows, descriptive, adjudicating nothing** (no re-run of BA2, PLAN 9.10): game_pwr
to ISO (BA2: NO SHIP), fb to K% (BA2: resolved LOSS), cmd to BB% (BA2: NO SHIP), hit to AVG on the
hit rows (TL-Q2), speed to SB per 600 PA. Each is computed on this frame with the same estimator
and printed with "secondary: no verdict"; BA2's verdicts stand.

**W.5 TAG tables.** Per source, tool and board year, with thin flags (3.5), the triple of 2.1 and
the metrics of 2.2, for the four primaries, the W.4 rows, and the single-source tools (raw_pwr to
average exit velocity, pitch_sel to chase rate, bat_ctrl to zone contact rate). Descriptive.

**W.6 Verdict per primary.** PASS when G1 to G5 hold on arm A (FanGraphs against MLB Pipeline) and
the tool survives Holm at 0.05 across the four primaries (m = 4) on the permutation p; LOSS when
the weighted consensus is worse by more than the floor with a bootstrap upper bound below 0; NULL
otherwise. Arm B (adding Baseball America) is NULL by construction: Baseball America's earliest tool
vintage is 2023, so under lag 3 it first carries a weight at board year 2026, outside the frame.
A NULL is a finding: equal weight retains.

**W.7 Controls**, BA2's C6.1 to C6.7 imported: permuted source label (the floor), pooled-tool
(control only, never a result), shuffled outcome, forced-equal identity in its honest form, seed
stability at 1337, the survivorship boundary, and the player-disjoint weight arm (C6.7). A verdict
that moves between seeds is FAIL. A shuffled-outcome result that does not collapse voids the look.

**W.8 Frame.** Board years 2017 to 2024 (2020 and 2021 admitted because the R-LV record exists,
0.3, at commit 1c73c420), debut year at most 2024, MLB seasons through 2026 frozen by sha256 at the
look.

**W.9 Disclosures carried into the verdict.** Under lag 3, board years 2017 to 2019 have no
resolved base vintage (FanGraphs tool grades begin in 2017), so their weights are flat and BA2's
skip rule drops them (BA2 '### 8.2'). The informative rows are board years 2020 to 2024, BA2's own
board years. A hit PASS is read on BA2's rows and is not independent of BA2; the verdict line says
so beside it.

**W.10 The expected result, written as a prediction before any number.** Hit is the only plausible
PASS, with MLB Pipeline weighted up. NULL is the modal result for speed, field and throw (two
sources with history, precisions likely indistinguishable). Arm B NULL by construction.

**W.11 Look date (EPOCH-NOW).** THE FIRST DAY after TL_4_TOOL_LAB_BUILD lands (its build commit and
its Part 4 amendment both committed) and after the R-LV record (0.3, 2026-10-08) on which the frame
named in W.8 is complete and no other registered look is recorded that day, under the same day rules
as P.10 (never a day another registered gate fixes for its own look, never the day look P runs). The
plan's earlier floor of 2026-12-03 is replaced by this condition.

**W.12 Fallback, registered and inactive.** If no R-LV record (0.3) exists on 2027-02-01, which can
happen only if the owner answers TL2-Q1 that only an entry under EFV_V2_GATE.md '## 9. Results'
counts and that section is still empty then, look W runs on or after 2027-02-01 on board years 2017
to 2019 and 2022 to 2024 only (2020 and 2021 never read), after a docs-only dated amendment
committed alone that names the fallback and its reason. Under the fallback only board years 2022 to
2024 carry resolved weights, and the verdict says so.

**W.13 The record.** One Part 8 'Look W' entry pasted verbatim from the runner: per tool n, equal
and weighted rho and AUC, d, floors, lower bounds, permutation p, Holm step, verdict (PASS, NULL or
LOSS), the derived weights by year; the W.4 rows marked secondary; the TAG tables; every control;
the survivorship sentence; the input sha256 list; the gate sha and the `--rlv-record` sha. Artifact
`data/tool_accuracy_eval.json` (a registry eval artifact that ships); a display copy only at
`.cache/tool_accuracy/preview/tool_source_accuracy.json`.

---

## Part 4. The k_m stabilization constants

PENDING: written by TL_4_TOOL_LAB_BUILD as one dated amendment committed alone, before either look.

Method, fixed here: for each TAG stat, split-half reliability on MLB player-seasons 2015 to 2019,
with no prospect join and no grade read. The split uses per-game or per-event data for those
seasons (odd and even games, or odd and even events). With r the split-half correlation at mean
half-season exposure n_h, the Spearman-Brown reliability of the full season is R = 2r / (1 + r) at
exposure n = 2 n_h, and k_m = n (1 - R) / R, in the stat's own exposure unit. A stat whose
2015-to-2019 per-game or per-event data are not on disk (arm strength, cached from 2020) is named
NOT COMPUTABLE in the amendment: its regressed TAG is not computed, its gap and percentile are, and
no other frame substitutes.

---

## Part 5. The one-look rules

1. Each look runs ONCE. A look record in Part 8, or a spent marker in its artifact
   (`data/power_composite_eval.json`, `data/tool_accuracy_eval.json`), makes the runner refuse.
2. First, a dry run of the whole reporting path on fixtures carrying None values
   (`--dry-run`), which reads no real row and must complete.
3. Then tee stdout and stderr to the task's output directory before anything else runs.
4. Before any score the runner asserts: the gate sha names a commit carrying this file with the
   REGISTERED status line; no debut year at or after 2025; no board year 2020 or 2021 unless the
   R-LV record is passed (`--rlv-record`, look W only); no FV-keyed grouping; and it records the
   sha256 of every input at start and end.
5. On any exception after scoring began: stop without rerunning, record the look as spent, and
   write OWNER_QUESTION.md. No second run, seed, frame or estimator.

---

## Part 6. Bans

- No lag other than `MIN_LAG_YEARS` = 3, not even as a labelled sensitivity (stricter than BA2
  '### 5.1' clause 1).
- No tool pooling to reach n (the C6.2 pooled control runs as a control only).
- No per-source offset, and no weighting of a single-source tool.
- No stratum, key, label or filter by consensus FV or any source's FV
  (`docs/PROSPECT_ANCHOR_GATE.md`); no realized statistic by FV cell.
- No read of R-LV before its record (0.3), and no read of R-VM ever: no debut year after 2024.
- Never `backtest.run_backtest`.
- No re-run of BA2 and no new verdict on its three pairs (W.4).
- No table from `data/tool_grade_tables.json` scores a row; no table scores a row of its own fit set.
- No WAR, no WAR part and no label read by either look.
- No served file written by either look.

---

## Part 7. What each verdict serves

- **Look P.** TL_6_POWER_COMPOSITE_DARK builds the winner behind `POWER_COMPOSITE_MODE` (default
  off, byte-identical off) and measures the blast flag on against flag off (the surfaces of
  POWER_SURFACE_AUDIT.md section 6); TL_7_POWER_COMPOSITE_FLIP serves it under TL-Q4 (production
  power, the look's winner served if it passes). A C0 verdict serves nothing new.
- **Look W.** TL_13_TOOL_WEIGHTS_DARK builds a passing tool's weighted grade on a separate key,
  `tools_consensus_w`; TL_14_TOOL_ACCURACY_DISPLAY_DARK builds the Source Accuracy "Tools" tab behind
  `SOURCE_ACCURACY_TOOLS_TAB`; TL_15_TOOL_DISPLAY_FLIP serves them under TL-Q5 (served chips through
  the display key). A NULL serves the tab's evidence and equal weight.
- **Neither verdict moves an eFV input.** No eFV model reads a power grade (POWER_SURFACE_AUDIT.md
  rows S17 to S21), and `tools_consensus_w` is a key `efv_dataset` never reads. The eFV route for
  tool features is TL-Q1 (a): a development-fold admission diagnostic that pre-declares candidates
  for the next registration. `pwr_comp` is a candidate only if look P serves C2 with a below 1.

---

## Part 8. Results

EMPTY AT REGISTRATION. The look P and look W entries are written here by TL_5 and TL_12, each pasted
verbatim from its runner and dated, and nothing above this part is edited once anything is written
below it, except by the amendments listed at the top.
