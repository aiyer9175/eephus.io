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

**Amendment of 2026-10-14 (TL_4_TOOL_LAB_BUILD, item 1 of the list at the top; committed alone, before either look).** Measured by `python tools/tool_accuracy_lab.py --k-m` on MLB player-seasons with no prospect join, no grade read and no debut read, from the per-event caches on disk: `.cache/pbp_corpus/plays/<season>/plays-<season>.parquet` and `pitches-<season>.parquet`, `.cache/pbp_runners/plays/<season>/pa-<season>.parquet` (launch speed) and `runners-<season>.parquet` (stolen bases). Receipt `data/_labs/tool_accuracy/k_m.json`, sha256 9384ca02ec17ae4469e86dfb27d0c0fc12a18d79e461ffe0f872dc29bf0bd4b8.

Seasons: of the 2015 to 2019 window, the per-event caches on disk hold [2018, 2019] only (no 2015, 2016 or 2017 MLB feed is cached), so every constant below is measured on those two seasons (default D-k1, recorded in the task report; the alternative is a fetch of the 2015 to 2017 feeds, about 7,300 games, before a look). The split is odd and even plate appearances (events) for every rate, odd and even batted balls for exit velocity, odd and even out-of-zone pitches for chase rate, odd and even in-zone swings for zone contact, odd and even fastballs for velocity, and odd and even games for stolen bases (a runner event, not a plate appearance). With r the split-half Pearson correlation across player-seasons at mean half exposure n_h, R = 2r / (1 + r) and k_m = 2 n_h (1 - R) / R, in the stat's own exposure unit. Player-season floors on total exposure (default D-k2): k_pct 300, hr_pa 300, avg 240, iso 240, babip 180, sb_per600 300, ev_avg 100, chase_pct 400, z_contact_pct 150, k_pct_pit 100, bb_pct_pit 100, fb_velo 200. Swing codes S, F, X, D, E, T, W, L, M, Q, R, O; contact codes F, X, D, E, T, L, O; zones 1 to 9 in, 11 to 14 out.

| stat | exposure unit | player-seasons | split-half r | R (full) | k_m |
|---|---|---|---|---|---|
| k_pct | pa | 552 | 0.8435 | 0.9151 | 46.7354 |
| hr_pa | pa | 552 | 0.5611 | 0.7188 | 197.0406 |
| avg | ab | 605 | 0.3159 | 0.4801 | 468.3212 |
| iso | ab | 605 | 0.5492 | 0.709 | 177.5259 |
| babip | ab (less SO and HR, plus SF) | 584 | 0.2861 | 0.4449 | 401.5923 |
| sb_per600 | pa (odd and even games) | 552 | 0.7689 | 0.8694 | 75.7105 |
| ev_avg | attempts (batted balls) | 764 | 0.7562 | 0.8612 | 43.6082 |
| chase_pct | oz_pitches | 726 | 0.8719 | 0.9316 | 68.3172 |
| z_contact_pct | iz_swings | 858 | 0.8036 | 0.8911 | 59.3017 |
| k_pct_pit | bf | 1040 | 0.6863 | 0.814 | 76.5133 |
| bb_pct_pit | bf | 1040 | 0.4258 | 0.5973 | 225.8052 |
| fb_velo | fastballs (FF, SI, FC) | 1080 | 0.9993 | 0.9997 | 0.2552 |
| sprint | competitive_runs | n/a | n/a | n/a | NOT COMPUTABLE: no per-run sprint data for 2015-2019 on disk (.cache/savant_sprint/ is a season leaderboard) |
| oaa_per1000 | innings | n/a | n/a | n/a | NOT COMPUTABLE: no per-play OAA for 2015-2019 on disk (.cache/savant_oaa/ is a season leaderboard) |
| arm_z | throws | n/a | n/a | n/a | NOT COMPUTABLE: arm strength is cached from 2020 (.cache/savant_arm/) |
| brl_pa | pa | n/a | n/a | n/a | NOT COMPUTABLE: no per-event barrel flag for 2015-2019 on disk |

The regressed TAG of a NOT COMPUTABLE stat is not computed; its gap and percentile are, and no other frame substitutes. The lab carries these values as `K_M` in `tools/tool_accuracy_lab.py`, pinned to this table by `test_tool_accuracy_lab.py`.

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

---

## Part T. Re-derived tool-to-stat tables against the published estimates

Part T status: REGISTERED

Dated amendment of 2026-10-09, item 2 of the list at the top of this file. Task
TL_19_TOOL_TABLE_REDERIVE_REGISTRATION, written at HEAD c3ac7156 (built on branch
efv-conviction-2026-08-08). Plan: Part 9 section 9.4.8 'Re-derived tool tables and the /scouting/
page (message 3)' (Part 9 bundle `PLAN.md`; round 4 dispositions intent 3 and leakage 6; round 5
item 5). Docs only, committed alone, before any number on this frame exists: at this commit there is
no `data/tool_tables_rederived_eval.json` and no `data/_labs/tool_table*`. Nothing above Part 8 is
edited by it: Part T sits after Part 8, so no line above Part 8 moves.

The owner's ask (2026-10-01, message 3, verbatim): "You can rederive tool->statistical production
grades if needed, the FanGraphs translations are estimates and if we could make these more accurate
(+provide a standalone "scouting" page that explains the 20-80 FV grading scale, with WAR
projections for each FV tier and tool projections for each tool tier, this would be really useful
for the public space)".

**Nothing was scored to write this part.** No grade was paired with an outcome, no table was
fitted, no cell or row was counted and no outcome number appears below. Every figure in it is a
published value transcribed with its section id, a constant, a date, a seed, or a prediction
labelled as one. The 2026-07-30 tool table results are cited by location, never restated.

Who uses this part:
- TL_4_TOOL_LAB_BUILD builds `tools/tool_accuracy_lab.py --look T` (with `--dry-run` and
  `--mde-only`) to it, writes the frozen grade rows of T.3, and writes T.10 as one dated amendment
  committed alone.
- TL_21_TOOL_TABLE_REDERIVE_LOOK runs look T once (T.7) and writes T.12.
- TL_20, TL_22 and TL_23 print the /scouting/ tool-tier column by T.6.

### T.1 The incumbent

One incumbent per primary cell, each a fixed function of the grade that reads no row. The values are
the published tables exactly as transcribed in `docs/reference/FANGRAPHS_FV_FRAMEWORK.md` Part 2
and, where the artifact carries the same column, in `data/tool_grade_tables.json`
`audit_vs_published` (its `published` field per row, for the outlet named).

Reading rules, common to every incumbent:
1. g is the unrounded consensus grade of T.3, clipped to [20, 80].
2. Between two published grades the incumbent is linear in g. Below the lowest published grade or
   above the highest it is held flat at that row. No extrapolation (the candidate obeys the same
   rule, T.2).
3. A published band (lo to hi) is read at its midpoint. An open band is read at its stated bound.
4. A published value below zero for a stat that cannot be negative is floored at zero before
   interpolation, and the floor is disclosed beside the cell.
5. A blank cell in the source is not a row; rule 2 interpolates across it.

| cell | incumbent (section id) | published rows, grade: value (point read) |
|---|---|---|
| game_pwr to HR per 600 PA | 2.1, S3 (2014) 'Homers', home runs per full MLB season at maturity, read per 600 PA as `audit_vs_published.hr_per600_fullseason` (outlet `fangraphs_2014`) reads it | 30: 3-5 (4); 35: 5-8 (6.5); 40: 8-12 (10); 45: 12-15 (13.5); 50: 15-18 (16.5); 55: 19-22 (20.5); 60: 23-27 (25); 65: 27-30 (28.5); 70: 30-35 (32.5); 75: 35-40 (37.5); 80: 40+ (40) |
| game_pwr to ISO | 2.2 '### Power tool', Mark Smith W2 (2013), ISO column | 20: -.013 (floored to .000); 30: .038; 40: .089; 50: .140; 60: .191; 70: .242; 80: .294 |
| hit to AVG | 2.1, S3 (2014) 'Batting Avg', batting average at maturity (`avg_fullseason`, outlet `fangraphs_2014`) | 30: .220; 35: .230; 40: .240; 45: .250; 50: .260; 55: .270; 60: .280; 65: .290; 70: .300; 75: .310; 80: .320 |
| hit to K% | none published; the grade-blind line | the season's MLB K% over qualified rows (below) |
| speed to SB per 600 PA | 2.2 '### Speed tool', W2 SB/3 column, stolen bases per season, read per 600 PA as `sb_per_season` (outlet `smith_2013`) reads it | 20: -20 (floored to 0); 30: -10 (floored to 0); 40: blank (interpolated, 4.5); 50: 9; 60: 19; 70: 29; 80: 38 |
| cmd to BB% (SP) | 2.2 '### Control', W2 SP BB% column, percent, lower is better (`bb_pct_sp`, outlet `smith_2013_sp`) | 20: 13.9; 30: 11.8; 40: 9.8; 50: 7.8; 60: 5.7; 70: 3.7; 80: 1.7 |
| fb to fastball velocity (SP) | 2.1, S3 (2014) 'Fastball Velo', mph, not split by role, read for starters as `fb_velo_sp` (outlet `fangraphs_2014`) reads it | 30: 86; 35: 87; 40: 88; 45: 89; 50: 90-91 (90.5); 55: 92; 60: 93; 65: 94; 70: 95; 75: 96; 80: 97 |

Notes, cell by cell:
- **game_pwr to ISO** (round 4, intent 3; round 5, item 5). The incumbent is W2's ISO column, not a
  grade-blind line: a grade-blind incumbent where a published table exists would let the page
  replace a FanGraphs estimate on a win the gate did not earn. The column's one negative row (20,
  -.013), which Smith calls "a glitch", is floored at .000 and disclosed; its other six rows are
  positive. The HR/PA column's negatives (30 -0.4%, 20 -1.8%) belong to another column and are not
  this cell's incumbent. The 50 row's z is blank in the source; its ISO (.140) is published and is
  read. `data/tool_grade_tables.json` carries no ISO block, so this column is transcribed from the
  framework document alone. TL_20 and TL_22 print it, labelled.
- **game_pwr to HR per 600 PA.** The artifact writes the open 80 band as [40, 55], an upper bound
  the source does not state; this registration reads the source's stated bound, 40 (default D1; the
  artifact's midpoint would read 47.5).
- **hit to K%.** No source in Part 2 publishes a grade-to-K% table (S3's hit column is batting
  average only, the caveat McDaniel states in L10). The incumbent is the grade-blind line: for a
  season Y, 100 times the sum of strikeOuts over the sum of plateAppearances across every row of
  `.cache/fa_statsapi_hitting_Y.json` with at least 300 PA (every MLB hitter, not only graded
  players), labelled "grade-blind league line". In the HOLDOUT, Y is 2026; in a T.10 fold, Y is the
  held-out season. The pooled form is default D2 (an unweighted mean of qualified rows is the
  alternative). The line knows the holdout season's league rate, which the candidate does not, so
  it favours the incumbent.
- **speed to SB per 600 PA.** S3's two speed columns are run times in seconds, for which this frame
  holds no outcome series (TOOL_GRADE_TABLES '### 2.6'), so W2's stolen-base column is the only
  FanGraphs-framework incumbent in an outcome unit. Its 20 and 30 rows are negative, which Smith
  and the framework document both call impossible; they are floored at 0 (rule 4) before the
  blank 40 row is interpolated (rule 5). Reading "per season" as "per 600 PA" follows the
  artifact's own audit and is disclosed.
- **cmd to BB% (SP).** The framework document's sign note applies: a higher grade reads a lower
  walk rate, and the table is used as published, with no sign flip.
- **fb to fastball velocity (SP).** S3 does not split by role (McDaniel: "I and many teams don't do
  that"); the artifact's starter audit reads it for starters, and so does this cell.
- **Beside, never deciding.** Two other FanGraphs-framework columns exist in a primary cell's unit:
  W2's BA column (2.2 '### Hit tool': 20 .199, 30 .221, 40 .244, 50 .267, 60 .290, 70 .313, 80
  .336) beside hit to AVG, and W2's SP Velo column (2.2 '### Fastball velocity, split by role': 20
  84, 30 86, 40 88, 50 91, 60 93, 70 95, 80 97) beside fb to velocity (SP). Each is scored on the
  same rows with the same statistic and printed "secondary: no verdict". Neither enters Holm, and
  neither changes what T.6 prints.
- Baseball America and MLB Pipeline bands in the artifact are not FanGraphs-framework tables and are
  not read.

### T.2 The candidate

OUR table, one per cell, by the TIP_mat rule of Part 1.2 step 1 and PLAN 9.4.2, fit on the cell's
FIT rows (T.3) only:
1. Each FIT row is one player: his grade g for the cell's tool and his FIT value.
2. Bin b = round(g / 5) * 5 (Python's `round`, as `tools/tool_grade_tables_lab.py` bins), clipped to
   [20, 80]. Each bin carries n, the median of its FIT values (one value per player, unweighted)
   and `grade_mean`, the mean unrounded grade in the bin.
3. A bin with n under 15 is THIN and dropped.
4. The non-thin bin medians are smoothed by weighted isotonic regression (PAVA, weight = bin n) in
   the expected direction: non-decreasing in g for HR per 600, ISO, AVG, SB per 600 and velocity;
   non-increasing for K% and BB%.
5. The table reads g by linear interpolation between the smoothed values placed at each non-thin
   bin's `grade_mean`, and is flat beyond the first and the last non-thin bin. No extrapolation.
6. A cell with no non-thin bin has no candidate and is NOT COMPUTABLE. A cell with one non-thin bin
   has a flat candidate, which is scored.

No free parameter remains. The bin width, the thin floor, the smoothing direction and the
interpolation are fixed above and in `docs/efv-2026-07-30/TOOL_GRADE_TABLES.md` '### 1.2' and
'### 1.3' (written before that lane's first table was fitted). Part 1.2 step 1's choice between the
age-26-and-over frame and the full-season frame does not arise: Part T fits the FIT frame of T.3
and nothing else. No table in `data/tool_grade_tables.json` is read (Part 6).

### T.3 Rows

**Grade.** For each record of `data/debuts.json`, the grade point is the last entry of `points`
whose `snapshot_date` is before the record's `debut_date` and whose `tools_consensus` is not empty
(TOOL_GRADE_TABLES '### 1.1', the P-MLB rule, as `load_grade_pools` in
`tools/tool_grade_tables_lab.py` applies it). A cell's grade is that point's `tools_consensus`
value for the cell's tool; a point without the tool gives the player no row in that cell. A record
whose `debut_date_is_placeholder` is true is dropped and counted, because the pre-debut rule cannot
be checked against it. The side is the harness's `is_pitcher` rule on `position`: hitter cells take
position players, pitcher cells take pitchers.

**Identity.** Outcome-blind, mlbam ids only (Part 3.1): the row's id is
`efv_identity.resolve_record(rec, V, index, side)` with V the calendar year of the grade point's
`snapshot_date`. A row that does not resolve, or resolves to an id other than the record's
`mlbam_id`, is dropped and counted in the artifact; the record's carried id is never used alone.

**Always excluded, asserted before any score.**
- R-LV: a grade point dated in 2020 or 2021 (its calendar year read as its list vintage, a superset
  of the preseason-window definition). Part T excludes these rows although the R-LV record exists
  (Part 0.3), as its specification reads.
- R-VM: a debut in 2025 or later.

**Frozen grade rows.** TL_4 writes the rows above, for the seven primary tools and the secondary
tools of T.4, to `data/_labs/tool_tables_rederived/grade_rows_frozen.json`: the mlbam id, side,
debut date, the grade point's snapshot date and its `tools_consensus` values for those tools, and
nothing else (no FV field of any kind, no outcome). Its sha256 is recorded in T.10. T.10 and look T
read grades from that file only.

**Season lines.** A player's season line is his one row in that season's
`.cache/fa_statsapi_hitting_Y.json` or `.cache/fa_statsapi_pitching_Y.json` (regular season, as
those files carry it). A hitter season qualifies with at least 300 PA, the full-season floor this
registration takes (default D3: TOOL_GRADE_TABLES '### 1.3' names 300 PA for its maturity frame
while its harness's full-season frame used 350 PA, `method.floors.mlb_fullseason_pa`; 300 is also
look P's hitter floor). A pitcher season qualifies as a starter season with at least 100 batters
faced (the harness's `MLB_BF_FLOOR`) and gamesStarted over gamesPlayed at or above 0.50 (the
harness's role rule, applied per season); a velocity season also needs the pitcher in that season's
velocity file (TOOL_GRADE_TABLES '### 1.3', presence in the arsenal leaderboard).

**FIT.** One row per player: his qualifying MLB seasons 2015 to 2025, with 2020 excluded, pooled
by exposure: HR per 600 = 600 x sum HR / sum PA; ISO = (sum TB - sum H) / sum AB; AVG = sum H / sum
AB; K% = 100 x sum SO / sum PA; SB per 600 = 600 x sum SB / sum PA; BB% = 100 x sum BB / sum BF;
velocity = the BF-weighted mean of his season velocities. The velocity series is
`.cache/velo_arsenal_Y.json`, written by `pal_export.load_velo(Y)` (the max of FF, SI and FC average
speed); it begins in 2017, so the velocity cell's FIT seasons are 2017 to 2025 without 2020. No 2026
line enters any FIT row or any candidate table, and the lab asserts it.

**HOLDOUT.** One row per player: his qualifying 2026 MLB season only, read from the 2026 season
files after the regular season ended, each file's sha256 and mtime recorded. TL_4 writes
`.cache/velo_arsenal_2026.json` through `pal_export.load_velo(2026)` after the regular season ended
and records its sha256 in T.10 without reading a value from it. This is a time-forward holdout.

**Disclosure: the July 2026 tables.** `data/tool_grade_tables.json` (generated 2026-07-30) lists no
seasons in its `pools` block (P_MLB n 1,765 from `data/debuts.json`; P_AAA n 3,419). Its harness
reads the StatsAPI season files of 2000 to 2026 that exist (`load_mlb_season_hitting` and
`load_mlb_season_pitching` at 'range(2000, 2027)'), MLB Statcast seasons 2016 to 2026
(`MLB_YEARS`), velocity files 2017 to 2026 and minor league seasons 2023 to 2026, and it ran on
2026-07-30, mid-season. So it may have read partial 2026 lines, descriptively, and its pools
include players whose 2026 lines are HOLDOUT lines here. Its tables score no row here (Part 6). The
candidate method has no parameter chosen on 2026: every rule in T.2 was fixed before that lane
fitted a table or by Part 1.2 of this file, and T.2 adds none. The predictions in T.5 were written
with that artifact's sections 2.1 and 2.2 in view.

### T.4 Cells

**Primary, fixed (seven).** Each is one Holm member when computable.

| # | tool | stat | side and qualifying season | MAE weight |
|---|---|---|---|---|
| 1 | game_pwr | HR per 600 PA | hitters, 300 PA | PA |
| 2 | game_pwr | ISO | hitters, 300 PA | PA |
| 3 | hit | AVG | hitters, 300 PA | PA |
| 4 | hit | K% | hitters, 300 PA | PA |
| 5 | speed | SB per 600 PA | hitters, 300 PA | PA |
| 6 | cmd | BB% (SP) | starter seasons | BF |
| 7 | fb | fastball velocity (SP) | starter seasons in the velocity file | BF |

A primary cell with fewer than 60 HOLDOUT rows is NOT COMPUTABLE: named, not a fail, and out of the
Holm family.

**Secondary, reported only** (no verdict, no Holm, never printed on /scouting/ as a measured
value), on the same grade rows, FIT seasons and holdout season, with the same candidate rule:
- raw_pwr to average exit velocity: `avg_hit_speed` of `.cache/savant_mlb/statcast_batter_Y.csv`,
  weighted by `attempts` (seasons 2016 on); hitter seasons of 300 PA.
- speed to sprint speed: `sprint_speed` of `.cache/savant_sprint/sprint_Y.csv`, weighted by
  `competitive_runs`; a season counts when the file carries the player (Part W.3).
- field to OAA per 1,000 innings: Part W.3's definition (positions 3 to 9, catchers excluded,
  innings from `data/fielding_innings.json`), a season counting at 700 innings, weighted by
  innings.
- cmd to BB% and fb to velocity for relievers: pitcher seasons of 100 BF with gamesStarted over
  gamesPlayed below 0.50, weighted by BF.

Secondary incumbents: W2's RP BB% column (2.2 '### Control': 20 16.3, 30 13.9, 40 11.6, 50 9.2, 60
6.8, 70 4.4, 80 2.0) and W2's RP Velo column (2.2 '### Fastball velocity, split by role': 20 84, 30
86, 40 89, 50 92, 60 95, 70 97, 80 100), read by T.1's rules. Exit velocity, sprint speed and OAA
have no published table in their unit, so each is read against its grade-blind season line (the
exposure-weighted mean over every qualifying row of that season's file), labelled.

### T.5 Statistic and pass rule

Per primary cell, on the cell's HOLDOUT rows, identical for both tables:
- MAE_w(table) = sum of w x |table(g) - y| over sum of w, with w the cell's MAE weight (T.4) and y
  the row's 2026 value.
- delta = MAE_w(candidate) - MAE_w(incumbent), in the stat's units; negative favours the candidate.
- Interval: a paired bootstrap over players, B 2000, each cell drawing from its own fresh
  `numpy.random.default_rng(20261028)`, n rows drawn with replacement from n, delta recomputed in
  each draw. Both tables stay fixed; no table is refit inside a draw. UB95 is the 95th percentile of
  the draws (one-sided upper bound). p = (1 + the number of draws with delta at or above 0) / (B +
  1).
- MDE95 per cell is copied from T.10 and never computed in the look session (round 4, leakage 6).

**PASS for a cell**, all of:
1. UB95 below 0;
2. the point improvement, -delta, at least max(MDE95, 0.05 x MAE_w(incumbent));
3. Holm across the computable primary cells (m = their count) at family alpha 0.05 on p.

Otherwise FAIL; marginal is FAIL. A cell short of rows, of a non-thin FIT bin or of a T.10 MDE95 is
NOT COMPUTABLE.

**Printed beside each verdict, never deciding:** n; both MAEs; delta, UB95, p, the Holm step; the
candidate table's non-thin bins with n, `grade_mean`, raw median, smoothed value and a 95%
percentile bootstrap interval on the bin median over FIT players (B 2000, the same seed); the beside
columns of T.1 and the secondary cells of T.4, each marked "secondary: no verdict"; the sensitivity
of T.11 (b); the survivorship sentence of Part 0.6.

**Predictions, written before any number.** Our curves are flatter than every published table
(TOOL_GRADE_TABLES '### 2.1'), so the candidate is expected to win where the published ladder is
steepest (power and hit at 60 and above, W2's ISO column included) and to beat the grade-blind line
on K%; velocity is expected to favour our table ('### 2.2'). These come from results on pools that
overlap both frames (T.3 disclosure) and carry no weight in the verdict. A null is a finding: the
incumbent keeps every cell it is not beaten on.

### T.6 What a verdict does

- A PASSING cell may print on the /scouting/ tool-tier column (TL_23) as "measured on debuted
  players", beside the FanGraphs estimate, with its n and interval.
- A FAIL or NOT COMPUTABLE cell prints the FanGraphs estimate labelled "FanGraphs framework
  estimate", or nothing where none exists (hit to K%).
- Copy never says our table is more accurate for a cell that did not pass, and every printed
  measured value carries the survivorship sentence of Part 0.6.
- The verdict moves no served grade, no consensus weight, no eFV input and no TIP table used by look
  P or look W (those fit their own declared rows).

### T.7 The one look

Look T runs ONCE, by TL_21_TOOL_TABLE_REDERIVE_LOOK, as `python tools/tool_accuracy_lab.py --look
T`.

**Date (orchestrator decision EPOCH-NOW, 2026-10-02).** THE FIRST DAY after TL_4_TOOL_LAB_BUILD
lands (its build commit, its Part 4 amendment and the T.10 amendment all committed, T.10 on a
calendar day before the look) on which the frame named in T.3 is complete and no other registered
look is recorded that day. The frame is complete when the 2026 season files the HOLDOUT reads
(`.cache/fa_statsapi_hitting_2026.json` and `.cache/fa_statsapi_pitching_2026.json`) were written
after the 2026 regular season ended (the 2026 season is final) and T.10 records
`.cache/velo_arsenal_2026.json` as written after that day or as absent. If
`pal_export.load_velo(2026)` yields no rows, the velocity cell is NOT COMPUTABLE for that reason; it
does not hold the look. The day is
never a day another registered gate fixes for its own look (`docs/*GATE*.md` and
`docs/**/*GATE*.md`, the U1c floor list), never a day a gate defines by rule from recorded inputs
before its record is written, and never the day look P or look W runs (P.10, W.11). The plan's
earlier date of 2026-10-28 is replaced by this condition; where TL_21's own checks name 2026-10-28,
this condition is the registered date. A later day that meets the same conditions reads the same
rows and needs no amendment; a run on a day that does not meet them is early and voids the look.
The late-look clause (round 4, ruling R8), verbatim: "if today is after the registered date, first
file a docs-only dated amendment to the gate naming the new date and the reason, commit it alone,
and only then run; never early". Under this condition it applies only if a condition above is ever
changed.

**Order.** First, `--look T --dry-run` on fixtures carrying None values, which reads no real row
and must complete. Then stdout and stderr are teed to the task's output directory before anything
else runs. Before any score the runner asserts: the `--registration` sha names a commit carrying
this part with its status line reading REGISTERED; the `--mde` sha names the T.10 amendment; no
grade point dated 2020 or 2021; no debut in 2025 or later; no 2026 line in any FIT row; no grouping
key naming an FV cell; and it records the sha256 of every input at start and at end. On any
exception after scoring began: stop without rerunning, record the look as spent, and write
OWNER_QUESTION.md with the traceback. No second run, seed, frame or estimator.

**Spent.** A T.12 record or a spent marker in `data/tool_tables_rederived_eval.json` makes the
runner refuse.

### T.8 Bans

- No change to any rule of this part after its commit. The only later edits are the T.10 amendment
  and the T.12 record, each committed alone, and the late-look amendment of T.7 if it ever applies.
- No row from R-LV (a grade point dated 2020 or 2021) or R-VM (a debut in 2025 or later).
- No realized statistic by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`). Tool-grade bins are
  not FV cells. No stratum, key, label, filter or weight names an FV cell; a source scan test in
  `test_tool_accuracy_lab.py` forbids an `fv` grouping key in the lab, and the frozen grade rows
  carry no FV field.
- No Statcast value and no other tool grade is an input to a candidate: each candidate is a function
  of the one tool grade of its cell. Statcast enters only as an outcome unit of a secondary cell.
- No table from `data/tool_grade_tables.json` scores a row; no WAR, WAR part or label is read.
- No 2026 line in any FIT row, candidate table or T.10 fold.
- No served file is written by the look; its eval artifact is a registry eval artifact.

### T.9 Registry

A row `tool_tables_rederived`, status 'registered, not read', eval artifact
`data/tool_tables_rederived_eval.json` (an eval artifact that ships, never listed in
`deploy/data_exclude.txt`), written by TL_21 through the idempotent registry script with a dated
note listing each cell's verdict read from the artifact. This commit carries the document alone; the
row lands with TL_21.

The artifact carries: `generated_at`; the registration sha; the T.10 sha; the sha256 of every holdout
and FIT input and of the frozen grade rows; per cell n, incumbent MAE, candidate MAE, delta, UB95, p,
MDE95 (copied from T.10), the margin, the Holm step and the verdict (PASS, FAIL or NOT COMPUTABLE);
the candidate bins of T.5; the beside, secondary and sensitivity reads marked as such; and the
survivorship sentence.

### T.10 MDE95 per primary cell

PENDING: written by TL_4_TOOL_LAB_BUILD (`--look T --mde-only`) as one dated amendment committed
alone, on a calendar day before the look.

Method, fixed here. FIT rows only: MLB seasons 2015 to 2025 with 2020 excluded (velocity 2017 to
2025); no HOLDOUT row and no 2026 line loaded, asserted. For each primary cell and each of its FIT
seasons s, leave season s out:
1. Refit the candidate by T.2 on FIT values pooled over each player's qualifying seasons other than
   s (a player with no other qualifying season leaves that fit).
2. Score the players with a qualifying season-s line (T.3 grade and exclusion rules) on that one
   line: d_s = MAE_w(candidate refit without s) - MAE_w(incumbent), with the weights of T.4; for hit
   to K% the incumbent is season s's grade-blind line.
3. A fold with fewer than 60 rows leaves.

MDE95 = 1.645 x the sample standard deviation (ddof 1) of d_s over the remaining folds, the house's
one-sided convention. A cell with fewer than 5 remaining folds has no MDE95 and is NOT COMPUTABLE at
the look. The amendment prints, per cell, MDE95, the folds used and each fold's row count, the
sha256 of the frozen grade rows and of every FIT input, and the sha256 of
`.cache/velo_arsenal_2026.json` (or its absence); the fold deltas themselves go only to
`data/_labs/tool_tables_rederived/mde95_folds.json`.

### T.11 Disclosures carried into the verdict

- **(a) The July 2026 tables** (T.3): possible partial 2026 lines read descriptively, pools that
  overlap both frames, predictions written with their results in view.
- **(b) Not a player hold-out.** A HOLDOUT player's 2015 to 2025 seasons may sit in the FIT rows of
  the table that scores his 2026 line. Sensitivity, reported only: each primary delta again with the
  candidate refit on the FIT rows of players who hold no HOLDOUT row in that cell, printed
  "sensitivity: no verdict".
- **(c) Survivorship and maturity.** Only players who reached the majors and hold a qualifying 2026
  season are scored (Part 0.6). The published tables describe hitters "at maturity"; the rows here
  are MLB seasons at every age, the frame the candidate is fit in and the incumbent is not. A verdict
  says "on debuted players' MLB seasons", never "at maturity".
- **(d) Holdout overlap with the stat-line gate** (PLAN 9.4.6, round 4): look T reads realized
  lines of the 2022 to 2024 debut cohorts before TL_17; TL_3 discloses this, and no Part T table is
  an input or a baseline of `prospect_statline`.
- **(e) Forking paths added by this part** (to Part 0.4): seven primary cells, two beside columns,
  five secondary cells and one sensitivity read.
- **(f) Defaults taken at registration:** D1, the open 80 HR band read at its stated bound 40; D2,
  the grade-blind K% line pooled from counts; D3, the 300 PA hitter season floor; D4, the
  incumbents chosen where two FanGraphs-framework columns share a unit (S3 for AVG and velocity,
  W2's columns printed beside); D5, a grade point's calendar year read as its list vintage for the
  R-LV exclusion; D6, Part T placed after Part 8, so nothing above Part 8 moves.

### T.12 Results

EMPTY AT REGISTRATION. Look T's record is written here by TL_21, pasted verbatim from the runner and
dated.
