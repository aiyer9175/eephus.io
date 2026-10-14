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

**Look W entry, written 2026-10-14 by TL_12_TOOL_WEIGHTS_LOOK; the runner's record is pasted verbatim
below the next heading.** Run once from HEAD 01593da7 (the runner's record extension, committed before the
run) by `python -u tools/tool_accuracy_lab.py --look W --gate-sha 77bd4302 --rlv-record 1c73c420`, teed to
the task's output directory before anything else ran; the dry run on fixtures carrying None values completed
first (Part 5 clause 2). An OWNER-WAIVED EARLY READ under EW3-5 (owner 2026-10-14; the dated note at the end
of this file). Artifact `data/tool_accuracy_eval.json`, sha256 211b7b9914efd6ec4e7a13583bc6a720299c38f04e6f0dc3563cdc356aca9ccd, spent marker set, inputs unchanged
from the start to the end of the run (36 inputs); display copy only at
`.cache/tool_accuracy/preview/tool_source_accuracy.json`; no served file written.

Reading under W.6 and W.7: THE LOOK IS VOID. The C6.3 shuffled-outcome control of the speed cell did not
collapse (weighted blend Spearman 0.1005 on the within-board-year permuted outcome at
n 679, equal 0.1021, against the runner's chance band 2.5 / sqrt(n) = 0.0959),
and W.7 says a shuffled-outcome result that does not collapse voids the look. The per-tool lines below
(hit NULL, speed VOID, field NULL, throw LOSS) are printed as the runner wrote them and are credited to nothing: equal weight retains for every
tool (a NULL retains; a void look serves nothing). The secondary rows adjudicate nothing (W.4); the hit to AVG
row's G1 to G5 line is descriptive, and BA2's verdicts and TL-Q2 stand. The record is read against the forking
paths of Part 0.4. No second run, seed, frame or estimator (Part 5 clause 5): a re-read of look W needs a new
registration. Nothing above Part 8 was edited.

### Look W (2026-10-14)

Gate sha 77bd4302; --rlv-record 1c73c420; runner HEAD 01593da7.
Frame (W.8): board years [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024], debut year at most 2024, MLB seasons through 2026; universe counts {'debuted_before_board_year': 795, 'no_debut_record': 4705, 'identity_disagrees_with_record': 16, 'identity_no_candidate': 34, 'identity_ambiguous': 55, 'debut_after_frame': 820, 'rows': 3516}.
Constants (W.1): MIN_LAG_YEARS 3, WEIGHT_SHRINK_K 150, WEIGHT_CLAMP [0.6, 1.5], SPEARMAN_FLOOR 0.05, B 2000, permutation draws 1000, seeds 8641 and 1337; Holm m = the computable primaries at 0.05; look void True.

Primaries (W.2, W.6), arm A FanGraphs against MLB Pipeline:
- hit (k_pct): verdict NULL; Holm step 4 p 0.863137 rejected False (m 4); flat-weight disclosure (W.9): board years [2017, 2018, 2019] carry flat weights and are skipped, so the informative rows are BA2's own board years; a hit PASS is read on BA2's rows and is not independent of BA2 (W.9); arm B: NULL by construction: Baseball America's earliest tool vintage is 2023
  common set by year {'2017': 102, '2018': 118, '2019': 145, '2020': 141, '2021': 123, '2022': 125, '2023': 74, '2024': 29}; pooled n 857; thin years (under 20) []; evaluable years [2020, 2021, 2022, 2023, 2024]
  n 492: equal rho 0.4058 AUC 0.696; weighted rho 0.405 AUC 0.6982; d_rho -0.000812; d_auc 0.002124
  floors (C6.1, 1000 draws): F_rho 0.009548, F_auc 0.004875, margin over F_rho -0.085; permutation p_rho 0.863137, p_auc 0.418581
  bootstrap (B 2000, seed 8641): d_rho lo95 -0.010334 hi95 0.008395 sd 0.005876; d_auc lo95 -0.003091 hi95 0.00726
  G1 rho resolvable False, G2 AUC resolvable False, G3 rho lo95 above 0 False, G4 AUC lo95 above 0 False, G5 not knife edge False; G1 to G5 False; loss clause False
  weights by year: 2017 (n 102, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2018 (n 118, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2019 (n 145, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2020 (n 141, weight base n 102): fangraphs 1.067, mlb_pipeline 0.933; 2021 (n 123, weight base n 220): fangraphs 1.0887, mlb_pipeline 0.9113; 2022 (n 125, weight base n 365): fangraphs 1.0596, mlb_pipeline 0.9404; 2023 (n 74, weight base n 506): fangraphs 1.0638, mlb_pipeline 0.9362; 2024 (n 29, weight base n 629): fangraphs 1.0614, mlb_pipeline 0.9386
  C6.1 permuted source label: draws 1000, non-flat 1000, abs d_rho p95 0.009548 max 0.016996, abs d_auc p95 0.004875 max 0.009378, weight spread median 0.0498 p95 0.1312
  C6.3 shuffled outcome: n 492, equal rho -0.0455, weighted rho -0.043, collapsed True
  C6.4 forced equal identity: n 857, d_rho 0.0, d_auc 0.0, passes True
  C6.5 seed stability (seed 1337): d_rho lo95 -0.011328 hi95 0.009003, d_auc lo95 -0.003283; permutation (200 draws) F_rho 0.009256 p_rho 0.875622; verdict moves between seeds False
  C6.7 player-disjoint weights: n 492, equal rho 0.4058, weighted rho 0.4034, d_rho -0.002437, d_auc 0.000488; weights by year: 2017 (n 102, weight base n 0): no weights, skipped: flat weights; 2018 (n 118, weight base n 0): no weights, skipped: flat weights; 2019 (n 145, weight base n 0): no weights, skipped: flat weights; 2020 (n 141, weight base n 77): fangraphs 1.0633, mlb_pipeline 0.9367; 2021 (n 123, weight base n 189): fangraphs 1.0554, mlb_pipeline 0.9446; 2022 (n 125, weight base n 320): fangraphs 1.0573, mlb_pipeline 0.9427; 2023 (n 74, weight base n 479): fangraphs 1.0595, mlb_pipeline 0.9405; 2024 (n 29, weight base n 613): fangraphs 1.0584, mlb_pipeline 0.9416
  single-source context: pooled n 492, years [2020, 2021, 2022, 2023, 2024]; fangraphs rho 0.3746; mlb_pipeline rho 0.3562; equal_mean rho 0.4058
  C0 estimator equivalence: numpy True, array A/B True
  arm B (FanGraphs, MLB Pipeline, Baseball America): pooled n 97, gate NOT COMPUTABLE (pool under 100 players)
- speed (sprint): verdict VOID; Holm step 2 p 0.055944 rejected False (m 4); flat-weight disclosure (W.9): board years [2017, 2018, 2019] carry flat weights and are skipped, so the informative rows are BA2's own board years; arm B: NULL by construction: Baseball America's earliest tool vintage is 2023
  common set by year {'2017': 140, '2018': 161, '2019': 196, '2020': 193, '2021': 165, '2022': 162, '2023': 107, '2024': 52}; pooled n 1176; thin years (under 20) []; evaluable years [2020, 2021, 2022, 2023, 2024]
  n 679: equal rho 0.7255 AUC 0.8389; weighted rho 0.7293 AUC 0.8414; d_rho 0.003857; d_auc 0.002473
  floors (C6.1, 1000 draws): F_rho 0.003945, F_auc 0.002386, margin over F_rho 0.9777; permutation p_rho 0.055944, p_auc 0.043956
  bootstrap (B 2000, seed 8641): d_rho lo95 -0.000456 hi95 0.007578 sd 0.002472; d_auc lo95 -0.000413 hi95 0.005262
  G1 rho resolvable False, G2 AUC resolvable True, G3 rho lo95 above 0 False, G4 AUC lo95 above 0 False, G5 not knife edge False; G1 to G5 False; loss clause False
  weights by year: 2017 (n 140, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2018 (n 161, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2019 (n 196, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2020 (n 193, weight base n 140): fangraphs 0.9974, mlb_pipeline 1.0026; 2021 (n 165, weight base n 301): fangraphs 0.986, mlb_pipeline 1.014; 2022 (n 162, weight base n 497): fangraphs 0.9814, mlb_pipeline 1.0186; 2023 (n 107, weight base n 690): fangraphs 0.9763, mlb_pipeline 1.0237; 2024 (n 52, weight base n 855): fangraphs 0.9753, mlb_pipeline 1.0247
  C6.1 permuted source label: draws 1000, non-flat 1000, abs d_rho p95 0.003945 max 0.007148, abs d_auc p95 0.002386 max 0.003952, weight spread median 0.0109 p95 0.032
  C6.3 shuffled outcome: n 679, equal rho 0.1021, weighted rho 0.1005, collapsed False
  C6.4 forced equal identity: n 1176, d_rho 0.0, d_auc 0.0, passes True
  C6.5 seed stability (seed 1337): d_rho lo95 -0.00047 hi95 0.00784, d_auc lo95 -0.000455; permutation (200 draws) F_rho 0.004105 p_rho 0.069652; verdict moves between seeds False
  C6.7 player-disjoint weights: n 679, equal rho 0.7255, weighted rho 0.7293, d_rho 0.003865, d_auc 0.002542; weights by year: 2017 (n 140, weight base n 0): no weights, skipped: flat weights; 2018 (n 161, weight base n 0): no weights, skipped: flat weights; 2019 (n 196, weight base n 0): no weights, skipped: flat weights; 2020 (n 193, weight base n 107): fangraphs 0.9957, mlb_pipeline 1.0043; 2021 (n 165, weight base n 260): fangraphs 0.9915, mlb_pipeline 1.0085; 2022 (n 162, weight base n 443): fangraphs 0.9823, mlb_pipeline 1.0177; 2023 (n 107, weight base n 640): fangraphs 0.9784, mlb_pipeline 1.0216; 2024 (n 52, weight base n 830): fangraphs 0.9769, mlb_pipeline 1.0231
  single-source context: pooled n 679, years [2020, 2021, 2022, 2023, 2024]; fangraphs rho 0.6804; mlb_pipeline rho 0.7278; equal_mean rho 0.7255
  C0 estimator equivalence: numpy True, array A/B True
  arm B (FanGraphs, MLB Pipeline, Baseball America): pooled n 147, gate NULL (no board year has both a non-flat weight vintage and resolvable outcomes at lag 3)
- field (oaa_per1000): verdict NULL; Holm step 3 p 0.63037 rejected False (m 4); flat-weight disclosure (W.9): board years [2017, 2018, 2019] carry flat weights and are skipped, so the informative rows are BA2's own board years; arm B: NULL by construction: Baseball America's earliest tool vintage is 2023
  common set by year {'2017': 87, '2018': 101, '2019': 123, '2020': 117, '2021': 102, '2022': 105, '2023': 63, '2024': 27}; pooled n 725; thin years (under 20) []; evaluable years [2020, 2021, 2022, 2023, 2024]
  n 414: equal rho 0.4031 AUC 0.706; weighted rho 0.4061 AUC 0.7095; d_rho 0.003034; d_auc 0.003454
  floors (C6.1, 1000 draws): F_rho 0.011283, F_auc 0.006208, margin over F_rho 0.2689; permutation p_rho 0.63037, p_auc 0.288711
  bootstrap (B 2000, seed 8641): d_rho lo95 -0.008125 hi95 0.01395 sd 0.00657; d_auc lo95 -0.002985 hi95 0.010204
  G1 rho resolvable False, G2 AUC resolvable False, G3 rho lo95 above 0 False, G4 AUC lo95 above 0 False, G5 not knife edge False; G1 to G5 False; loss clause False
  weights by year: 2017 (n 87, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2018 (n 101, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2019 (n 123, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2020 (n 117, weight base n 87): fangraphs 0.9074, mlb_pipeline 1.0926; 2021 (n 102, weight base n 188): fangraphs 0.9176, mlb_pipeline 1.0824; 2022 (n 105, weight base n 311): fangraphs 0.9382, mlb_pipeline 1.0618; 2023 (n 63, weight base n 428): fangraphs 0.9767, mlb_pipeline 1.0233; 2024 (n 27, weight base n 530): fangraphs 0.9829, mlb_pipeline 1.0171
  C6.1 permuted source label: draws 1000, non-flat 1000, abs d_rho p95 0.011283 max 0.021227, abs d_auc p95 0.006208 max 0.012604, weight spread median 0.0435 p95 0.1346
  C6.3 shuffled outcome: n 414, equal rho 0.0134, weighted rho 0.0054, collapsed True
  C6.4 forced equal identity: n 725, d_rho 0.0, d_auc 0.0, passes True
  C6.5 seed stability (seed 1337): d_rho lo95 -0.008141 hi95 0.013877, d_auc lo95 -0.003119; permutation (200 draws) F_rho 0.010278 p_rho 0.59204; verdict moves between seeds False
  C6.7 player-disjoint weights: n 414, equal rho 0.4031, weighted rho 0.4062, d_rho 0.003151, d_auc 0.003291; weights by year: 2017 (n 87, weight base n 0): no weights, skipped: flat weights; 2018 (n 101, weight base n 0): no weights, skipped: flat weights; 2019 (n 123, weight base n 0): no weights, skipped: flat weights; 2020 (n 117, weight base n 67): fangraphs 0.8634, mlb_pipeline 1.1366; 2021 (n 102, weight base n 163): fangraphs 0.8991, mlb_pipeline 1.1009; 2022 (n 105, weight base n 273): fangraphs 0.9331, mlb_pipeline 1.0669; 2023 (n 63, weight base n 404): fangraphs 0.9538, mlb_pipeline 1.0462; 2024 (n 27, weight base n 515): fangraphs 0.9745, mlb_pipeline 1.0255
  single-source context: pooled n 414, years [2020, 2021, 2022, 2023, 2024]; fangraphs rho 0.363; mlb_pipeline rho 0.3908; equal_mean rho 0.4031
  C0 estimator equivalence: numpy True, array A/B True
  arm B (FanGraphs, MLB Pipeline, Baseball America): pooled n 84, gate NOT COMPUTABLE (pool under 100 players)
- throw (arm_z): verdict LOSS; Holm step 1 p 0.042957 rejected False (m 4); flat-weight disclosure (W.9): board years [2017, 2018, 2019] carry flat weights and are skipped, so the informative rows are BA2's own board years; arm B: NULL by construction: Baseball America's earliest tool vintage is 2023
  common set by year {'2017': 101, '2018': 118, '2019': 148, '2020': 138}; pooled n 505; thin years (under 20) []; evaluable years [2020]
  n 138: equal rho 0.5342 AUC 0.7408; weighted rho 0.5197 AUC 0.7353; d_rho -0.014547; d_auc -0.005461
  floors (C6.1, 1000 draws): F_rho 0.013851, F_auc 0.009137, margin over F_rho -1.0502; permutation p_rho 0.042957, p_auc 0.281718
  bootstrap (B 2000, seed 8641): d_rho lo95 -0.028233 hi95 -0.002275 sd 0.00784; d_auc lo95 -0.01383 hi95 0.002817
  G1 rho resolvable False, G2 AUC resolvable False, G3 rho lo95 above 0 False, G4 AUC lo95 above 0 False, G5 not knife edge False; G1 to G5 False; loss clause True
  weights by year: 2017 (n 101, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2018 (n 118, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2019 (n 148, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2020 (n 138, weight base n 101): fangraphs 1.0257, mlb_pipeline 0.9743
  C6.1 permuted source label: draws 1000, non-flat 1000, abs d_rho p95 0.013851 max 0.022573, abs d_auc p95 0.009137 max 0.016278, weight spread median 0.0304 p95 0.0862
  C6.3 shuffled outcome: n 138, equal rho -0.0274, weighted rho -0.0296, collapsed True
  C6.4 forced equal identity: n 505, d_rho 0.0, d_auc 0.0, passes True
  C6.5 seed stability (seed 1337): d_rho lo95 -0.027982 hi95 -0.001841, d_auc lo95 -0.014373; permutation (200 draws) F_rho 0.014635 p_rho 0.064677; verdict moves between seeds False
  C6.7 player-disjoint weights: n 138, equal rho 0.5342, weighted rho 0.5197, d_rho -0.014547, d_auc -0.005461; weights by year: 2017 (n 101, weight base n 0): no weights, skipped: flat weights; 2018 (n 118, weight base n 0): no weights, skipped: flat weights; 2019 (n 148, weight base n 0): no weights, skipped: flat weights; 2020 (n 138, weight base n 77): fangraphs 1.0296, mlb_pipeline 0.9704
  single-source context: pooled n 138, years [2020]; fangraphs rho 0.438; mlb_pipeline rho 0.5256; equal_mean rho 0.5342
  C0 estimator equivalence: numpy True, array A/B True
  arm B (FanGraphs, MLB Pipeline, Baseball America): pooled n 0, gate NOT COMPUTABLE (pool under 100 players)

Secondary rows (W.4), descriptive, adjudicating nothing; BA2's verdicts stand:
- game_pwr (game_pwr to iso): secondary: no verdict; BA2 NO SHIP; arm B pooled n 97 NOT COMPUTABLE
  common set by year {'2017': 102, '2018': 118, '2019': 145, '2020': 141, '2021': 123, '2022': 124, '2023': 74, '2024': 29}; pooled n 856; thin years (under 20) []; evaluable years [2020, 2021, 2022, 2023, 2024]
  n 491: equal rho 0.5771 AUC 0.7558; weighted rho 0.5802 AUC 0.7571; d_rho 0.003093; d_auc 0.001344
  floors (C6.1, 1000 draws): F_rho 0.007148, F_auc 0.003966, margin over F_rho 0.4327; permutation p_rho 0.405594, p_auc 0.529471
  bootstrap (B 2000, seed 8641): d_rho lo95 -0.003372 hi95 0.009681 sd 0.003971; d_auc lo95 -0.00254 hi95 0.005415
  G1 rho resolvable False, G2 AUC resolvable False, G3 rho lo95 above 0 False, G4 AUC lo95 above 0 False, G5 not knife edge False; G1 to G5 False; loss clause False
  weights by year: 2017 (n 102, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2018 (n 118, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2019 (n 145, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2020 (n 141, weight base n 102): fangraphs 0.9621, mlb_pipeline 1.0379; 2021 (n 123, weight base n 220): fangraphs 0.9556, mlb_pipeline 1.0444; 2022 (n 124, weight base n 365): fangraphs 0.9793, mlb_pipeline 1.0207; 2023 (n 74, weight base n 506): fangraphs 0.9869, mlb_pipeline 1.0131; 2024 (n 29, weight base n 629): fangraphs 0.9936, mlb_pipeline 1.0064
  C6.1 permuted source label: draws 1000, non-flat 1000, abs d_rho p95 0.007148 max 0.012351, abs d_auc p95 0.003966 max 0.006396, weight spread median 0.02 p95 0.059
  C0 estimator equivalence: numpy True, array A/B True
- fb (fb to k_pct_pit): secondary: no verdict; BA2 resolved LOSS; arm B pooled n 143 NULL
  common set by year {'2017': 94, '2018': 140, '2019': 166, '2020': 154, '2021': 127, '2022': 126, '2023': 104, '2024': 55}; pooled n 966; thin years (under 20) []; evaluable years [2020, 2021, 2022, 2023, 2024]
  n 566: equal rho 0.3481 AUC 0.6672; weighted rho 0.346 AUC 0.6664; d_rho -0.002125; d_auc -0.00073
  floors (C6.1, 1000 draws): F_rho 0.00945, F_auc 0.004951, margin over F_rho -0.2249; permutation p_rho 0.655345, p_auc 0.761239
  bootstrap (B 2000, seed 8641): d_rho lo95 -0.008652 hi95 0.004504 sd 0.003969; d_auc lo95 -0.004626 hi95 0.003395
  G1 rho resolvable False, G2 AUC resolvable False, G3 rho lo95 above 0 False, G4 AUC lo95 above 0 False, G5 not knife edge False; G1 to G5 False; loss clause False
  weights by year: 2017 (n 94, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2018 (n 140, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2019 (n 166, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2020 (n 154, weight base n 94): fangraphs 1.0181, mlb_pipeline 0.9819; 2021 (n 127, weight base n 234): fangraphs 0.9334, mlb_pipeline 1.0666; 2022 (n 126, weight base n 400): fangraphs 0.976, mlb_pipeline 1.024; 2023 (n 104, weight base n 554): fangraphs 1.0024, mlb_pipeline 0.9976; 2024 (n 55, weight base n 681): fangraphs 1.0248, mlb_pipeline 0.9752
  C6.1 permuted source label: draws 1000, non-flat 1000, abs d_rho p95 0.00945 max 0.015939, abs d_auc p95 0.004951 max 0.008179, weight spread median 0.0613 p95 0.1744
  C0 estimator equivalence: numpy True, array A/B True
- cmd (cmd to bb_pct_pit): secondary: no verdict; BA2 NO SHIP; arm B pooled n 143 NULL
  common set by year {'2017': 94, '2018': 139, '2019': 166, '2020': 154, '2021': 128, '2022': 126, '2023': 104, '2024': 55}; pooled n 966; thin years (under 20) []; evaluable years [2020, 2021, 2022, 2023, 2024]
  n 567: equal rho 0.3164 AUC 0.6381; weighted rho 0.3204 AUC 0.6421; d_rho 0.004064; d_auc 0.004031
  floors (C6.1, 1000 draws): F_rho 0.009998, F_auc 0.005151, margin over F_rho 0.4065; permutation p_rho 0.43956, p_auc 0.155844
  bootstrap (B 2000, seed 8641): d_rho lo95 -0.004863 hi95 0.012371 sd 0.005277; d_auc lo95 -0.001203 hi95 0.009341
  G1 rho resolvable False, G2 AUC resolvable False, G3 rho lo95 above 0 False, G4 AUC lo95 above 0 False, G5 not knife edge False; G1 to G5 False; loss clause False
  weights by year: 2017 (n 94, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2018 (n 139, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2019 (n 166, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2020 (n 154, weight base n 94): fangraphs 0.9713, mlb_pipeline 1.0287; 2021 (n 128, weight base n 233): fangraphs 0.989, mlb_pipeline 1.011; 2022 (n 126, weight base n 399): fangraphs 0.9677, mlb_pipeline 1.0323; 2023 (n 104, weight base n 553): fangraphs 0.9151, mlb_pipeline 1.0849; 2024 (n 55, weight base n 681): fangraphs 0.881, mlb_pipeline 1.119
  C6.1 permuted source label: draws 1000, non-flat 1000, abs d_rho p95 0.009998 max 0.019543, abs d_auc p95 0.005151 max 0.008927, weight spread median 0.0468 p95 0.1468
  C0 estimator equivalence: numpy True, array A/B True
- hit_avg (hit to avg): secondary: no verdict; BA2 TL-Q2 beside; arm B pooled n 97 NOT COMPUTABLE
  common set by year {'2017': 102, '2018': 118, '2019': 145, '2020': 141, '2021': 123, '2022': 125, '2023': 74, '2024': 29}; pooled n 857; thin years (under 20) []; evaluable years [2020, 2021, 2022, 2023, 2024]
  n 492: equal rho 0.1773 AUC 0.5743; weighted rho 0.1985 AUC 0.5847; d_rho 0.02126; d_auc 0.010452
  floors (C6.1, 1000 draws): F_rho 0.009147, F_auc 0.004925, margin over F_rho 2.3243; permutation p_rho 0.000999, p_auc 0.000999
  bootstrap (B 2000, seed 8641): d_rho lo95 0.010559 hi95 0.031006 sd 0.006166; d_auc lo95 0.003854 hi95 0.016388
  G1 rho resolvable True, G2 AUC resolvable True, G3 rho lo95 above 0 True, G4 AUC lo95 above 0 True, G5 not knife edge True; G1 to G5 True; loss clause False
  weights by year: 2017 (n 102, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2018 (n 118, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2019 (n 145, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2020 (n 141, weight base n 102): fangraphs 0.9959, mlb_pipeline 1.0041; 2021 (n 123, weight base n 220): fangraphs 0.8431, mlb_pipeline 1.1569; 2022 (n 125, weight base n 365): fangraphs 0.7756, mlb_pipeline 1.2244; 2023 (n 74, weight base n 506): fangraphs 0.7074, mlb_pipeline 1.2926; 2024 (n 29, weight base n 629): fangraphs 0.6503, mlb_pipeline 1.3497
  C6.1 permuted source label: draws 1000, non-flat 1000, abs d_rho p95 0.009147 max 0.016877, abs d_auc p95 0.004925 max 0.009626, weight spread median 0.0875 p95 0.2776
  C0 estimator equivalence: numpy True, array A/B True
- speed_sb (speed to sb_per600): secondary: no verdict; BA2 secondary; arm B pooled n 97 NOT COMPUTABLE
  common set by year {'2017': 102, '2018': 118, '2019': 145, '2020': 141, '2021': 123, '2022': 125, '2023': 74, '2024': 29}; pooled n 857; thin years (under 20) []; evaluable years [2020, 2021, 2022, 2023, 2024]
  n 492: equal rho 0.7595 AUC 0.888; weighted rho 0.7624 AUC 0.8907; d_rho 0.002887; d_auc 0.002727
  floors (C6.1, 1000 draws): F_rho 0.004802, F_auc 0.002727, margin over F_rho 0.6012; permutation p_rho 0.267732, p_auc 0.050949
  bootstrap (B 2000, seed 8641): d_rho lo95 -0.000705 hi95 0.006385 sd 0.002157; d_auc lo95 0.00061 hi95 0.004947
  G1 rho resolvable False, G2 AUC resolvable True, G3 rho lo95 above 0 False, G4 AUC lo95 above 0 True, G5 not knife edge False; G1 to G5 False; loss clause False
  weights by year: 2017 (n 102, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2018 (n 118, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2019 (n 145, weight base n 0): fangraphs 1.0, mlb_pipeline 1.0, skipped: flat weights; 2020 (n 141, weight base n 102): fangraphs 1.0003, mlb_pipeline 0.9997; 2021 (n 123, weight base n 220): fangraphs 0.9922, mlb_pipeline 1.0078; 2022 (n 125, weight base n 365): fangraphs 0.9997, mlb_pipeline 1.0003; 2023 (n 74, weight base n 506): fangraphs 0.9985, mlb_pipeline 1.0015; 2024 (n 29, weight base n 629): fangraphs 0.997, mlb_pipeline 1.003
  C6.1 permuted source label: draws 1000, non-flat 1000, abs d_rho p95 0.004802 max 0.008972, abs d_auc p95 0.002727 max 0.005371, weight spread median 0.0128 p95 0.0362
  C0 estimator equivalence: numpy True, array A/B True

TAG tables (W.5), per source, tool and board year, thin cells flagged:
- TAG hit / k_pct: frame 1001; k_m 46.7354 (pa); regressed TAG computed
  baseballamerica: n 101, computable True; ordering 0.1707; bias regressed 1.1413, bias PIT minus 0.5 0.0598; error abs regressed 4.1304
    2017: n 0
    2018: n 0
    2019: n 0
    2020: n 0
    2021: n 0
    2022: n 0
    2023: n 72, mean gap 1.171, regressed 1.1138, PIT minus 0.5 0.068, abs regressed 4.0999, ordering rho 0.1535
    2024: n 29, mean gap 1.2783, regressed 1.2093, PIT minus 0.5 0.0401, abs regressed 4.2062, ordering rho 0.2134
  fangraphs: n 949, computable True; ordering 0.39; bias regressed 0.3979, bias PIT minus 0.5 0.0083; error abs regressed 4.0524
    2017: n 107, mean gap -0.7305, regressed -0.6487, PIT minus 0.5 -0.0403, abs regressed 3.6656, ordering rho 0.4021
    2018: n 121, mean gap -1.8673, regressed -1.6919, PIT minus 0.5 -0.0995, abs regressed 4.0835, ordering rho 0.3355
    2019: n 151, mean gap -0.1858, regressed -0.1232, PIT minus 0.5 -0.0215, abs regressed 4.059, ordering rho 0.3764
    2020: n 167, mean gap 0.1916, regressed 0.2244, PIT minus 0.5 -0.0014, abs regressed 3.9359, ordering rho 0.502
    2021: n 146, mean gap 1.1544, regressed 1.1112, PIT minus 0.5 0.0432, abs regressed 3.9056, ordering rho 0.3746
    2022: n 142, mean gap 1.5708, regressed 1.5204, PIT minus 0.5 0.0793, abs regressed 4.4577, ordering rho 0.3836
    2023: n 83, mean gap 2.2906, regressed 2.1901, PIT minus 0.5 0.1231, abs regressed 4.2792, ordering rho 0.3345
    2024: n 32, mean gap 2.4256, regressed 2.2807, PIT minus 0.5 0.1034, abs regressed 4.0889, ordering rho 0.2783
  mlb_pipeline: n 909, computable True; ordering 0.3394; bias regressed -0.3107, bias PIT minus 0.5 -0.0227; error abs regressed 4.0334
    2017: n 116, mean gap -1.3185, regressed -1.1899, PIT minus 0.5 -0.0683, abs regressed 4.1645, ordering rho 0.3199
    2018: n 133, mean gap -1.3628, regressed -1.2216, PIT minus 0.5 -0.0793, abs regressed 4.5056, ordering rho 0.2536
    2019: n 154, mean gap -0.4799, regressed -0.407, PIT minus 0.5 -0.0341, abs regressed 4.2372, ordering rho 0.3935
    2020: n 142, mean gap -0.5567, regressed -0.493, PIT minus 0.5 -0.0456, abs regressed 4.0167, ordering rho 0.3947
    2021: n 125, mean gap 0.1479, regressed 0.1581, PIT minus 0.5 0.0089, abs regressed 3.6148, ordering rho 0.3385
    2022: n 130, mean gap 0.2439, regressed 0.2578, PIT minus 0.5 0.0253, abs regressed 3.8294, ordering rho 0.4137
    2023: n 77, mean gap 0.568, regressed 0.5517, PIT minus 0.5 0.0309, abs regressed 3.7284, ordering rho 0.2165
    2024: n 32, mean gap 1.8693, regressed 1.7188, PIT minus 0.5 0.0904, abs regressed 3.8873, ordering rho 0.2598
  TIP_f3 for 2017 (fit on the other board years, 675 rows): knots [40.8036, 45.0732, 50.2557, 54.8974, 59.0479, 65.0833], values [28.5117, 26.0365, 24.1636, 21.8841, 21.8841, 21.3621], thin bins [30, 35, 70]
  TIP_f3 for 2018 (fit on the other board years, 564 rows): knots [40.8793, 45.0833, 50.3684, 54.8857, 59.191, 65.0882], values [27.9309, 25.984, 24.1636, 21.8713, 21.8713, 21.5172], thin bins [30, 35, 70]
  TIP_f3 for 2019 (fit on the other board years, 448 rows): knots [41.1735, 45.123, 50.2938, 54.85, 59.2727, 65.075], values [28.4424, 26.88, 23.7435, 22.8581, 22.8581, 21.9251], thin bins [30, 35, 70]
  TIP_f3 for 2020 (fit on the other board years, 397 rows): knots [41.3382, 45.0763, 50.2986, 54.8581, 59.0526, 65.1765], values [30.6682, 27.1457, 23.9831, 22.4913, 22.4913, 22.4913], thin bins [30, 35, 70, 75]
  TIP_f3 for 2021 (fit on the other board years, 455 rows): knots [41.0667, 45.0423, 50.328, 54.9643, 58.6765, 65.1765], values [32.1937, 27.1457, 24.0125, 23.5021, 21.9051, 21.9051], thin bins [30, 35, 70, 75]
  TIP_f3 for 2022 (fit on the other board years, 512 rows): knots [41.0833, 44.9786, 50.3265, 55.0, 58.7361], values [31.6357, 27.4806, 24.2812, 22.7394, 21.5795], thin bins [30, 35, 65, 70, 75]
  TIP_f3 for 2023 (fit on the other board years, 736 rows): knots [40.9596, 45.0, 50.3204, 55.0, 58.8553], values [29.7189, 27.6623, 24.8063, 22.2494, 21.6842], thin bins [30, 35, 65, 70, 75]
  TIP_f3 for 2024 (fit on the other board years, 898 rows): knots [40.9386, 45.0126, 50.2735, 54.961, 58.9154, 65.0], values [29.6602, 26.8924, 24.5499, 22.2828, 21.6842, 21.5172], thin bins [30, 35, 70, 75]
- TAG speed / sprint: frame 1432; k_m None (competitive_runs); regressed TAG NOT COMPUTABLE
  baseballamerica: n 161, computable True; ordering 0.7243; bias regressed None, bias PIT minus 0.5 0.0223; error abs regressed None
    2017: n 0
    2018: n 0
    2019: n 0
    2020: n 0
    2021: n 0
    2022: n 0
    2023: n 108, mean gap 0.0587, regressed None, PIT minus 0.5 0.0147, abs regressed None, ordering rho 0.7481
    2024: n 53, mean gap 0.1092, regressed None, PIT minus 0.5 0.0377, abs regressed None, ordering rho 0.6759
  fangraphs: n 1328, computable True; ordering 0.6877; bias regressed None, bias PIT minus 0.5 0.0369; error abs regressed None
    2017: n 146, mean gap 0.164, regressed None, PIT minus 0.5 0.0655, abs regressed None, ordering rho 0.7445
    2018: n 169, mean gap -0.0175, regressed None, PIT minus 0.5 -0.0, abs regressed None, ordering rho 0.6899
    2019: n 209, mean gap -0.1884, regressed None, PIT minus 0.5 -0.0588, abs regressed None, ordering rho 0.6983
    2020: n 234, mean gap 0.0898, regressed None, PIT minus 0.5 0.0316, abs regressed None, ordering rho 0.6644
    2021: n 198, mean gap 0.1567, regressed None, PIT minus 0.5 0.0489, abs regressed None, ordering rho 0.6271
    2022: n 193, mean gap 0.3534, regressed None, PIT minus 0.5 0.1091, abs regressed None, ordering rho 0.6816
    2023: n 123, mean gap 0.2179, regressed None, PIT minus 0.5 0.0708, abs regressed None, ordering rho 0.7175
    2024: n 56, mean gap 0.2845, regressed None, PIT minus 0.5 0.0856, abs regressed None, ordering rho 0.7605
  mlb_pipeline: n 1278, computable True; ordering 0.7348; bias regressed None, bias PIT minus 0.5 -0.0472; error abs regressed None
    2017: n 164, mean gap -0.2057, regressed None, PIT minus 0.5 -0.0799, abs regressed None, ordering rho 0.7679
    2018: n 186, mean gap -0.2722, regressed None, PIT minus 0.5 -0.0891, abs regressed None, ordering rho 0.7336
    2019: n 218, mean gap -0.3595, regressed None, PIT minus 0.5 -0.1204, abs regressed None, ordering rho 0.7339
    2020: n 198, mean gap -0.114, regressed None, PIT minus 0.5 -0.0493, abs regressed None, ordering rho 0.7546
    2021: n 168, mean gap -0.0342, regressed None, PIT minus 0.5 -0.0077, abs regressed None, ordering rho 0.7073
    2022: n 173, mean gap 0.0921, regressed None, PIT minus 0.5 0.0279, abs regressed None, ordering rho 0.7249
    2023: n 114, mean gap 0.0192, regressed None, PIT minus 0.5 0.003, abs regressed None, ordering rho 0.7254
    2024: n 57, mean gap 0.084, regressed None, PIT minus 0.5 0.0232, abs regressed None, ordering rho 0.7073
  TIP_f3 for 2017 (fit on the other board years, 979 rows): knots [30.4653, 35.1596, 40.288, 44.9511, 50.1193, 54.8585, 59.4146, 65.1286, 69.4595], values [26.0614, 26.5546, 27.1316, 27.6737, 27.9214, 28.1353, 28.7501, 29.0014, 29.3684], thin bins [20, 25, 75, 80]
  TIP_f3 for 2018 (fit on the other board years, 809 rows): knots [30.319, 35.2093, 40.211, 44.94, 50.1688, 54.8295, 59.4078, 65.1552, 69.7321], values [26.0259, 26.5721, 27.1685, 27.8508, 27.9136, 28.2318, 28.8213, 29.0321, 29.3692], thin bins [20, 25, 75, 80]
  TIP_f3 for 2019 (fit on the other board years, 638 rows): knots [30.2037, 35.2812, 40.2438, 44.9438, 50.0775, 54.8478, 59.3571, 65.375, 69.875], values [26.0549, 26.6035, 27.2, 27.6419, 28.0195, 28.4344, 28.9317, 29.3074, 29.4755], thin bins [20, 25, 75, 80]
  TIP_f3 for 2020 (fit on the other board years, 553 rows): knots [30.25, 35.3, 40.1591, 44.9262, 50.0223, 54.8986, 59.1222], values [25.9196, 26.6472, 27.2791, 27.4638, 27.75, 28.2575, 28.8581], thin bins [20, 25, 65, 70, 80]
  TIP_f3 for 2021 (fit on the other board years, 670 rows): knots [30.3175, 35.1304, 40.15, 45.0, 49.9346, 54.9659, 59.1624, 65.0833, 69.4048], values [26.0, 26.6031, 26.9288, 27.3193, 27.7023, 28.4576, 28.8389, 28.9424, 29.2], thin bins [20, 25, 75, 80]
  TIP_f3 for 2022 (fit on the other board years, 735 rows): knots [30.4643, 35.0714, 40.1937, 45.0306, 50.0621, 54.961, 58.9624, 65.0, 69.3056], values [26.0, 26.2477, 26.8, 27.3912, 27.7381, 28.2522, 28.7287, 28.7287, 28.7287], thin bins [20, 25, 75, 80]
  TIP_f3 for 2023 (fit on the other board years, 1004 rows): knots [20.0, 25.0, 30.4598, 34.9746, 40.2565, 45.0, 50.0112, 55.0, 59.0879, 65.0, 69.3], values [25.3943, 25.3943, 26.0405, 26.6341, 26.9604, 27.5795, 27.8, 28.2522, 28.7137, 28.7137, 29.1], thin bins [75, 80]
  TIP_f3 for 2024 (fit on the other board years, 1242 rows): knots [20.0, 25.0, 30.5294, 35.0448, 40.281, 45.0156, 50.0977, 54.8983, 59.213, 64.9643, 69.386], values [25.5203, 25.5203, 26.0016, 26.5721, 27.0131, 27.4921, 27.8435, 28.2213, 28.8217, 28.8217, 29.2], thin bins [75, 80]
- TAG field / oaa_per1000: frame 847; k_m None (innings); regressed TAG NOT COMPUTABLE
  baseballamerica: n 87, computable False; ordering 0.3886; bias regressed None, bias PIT minus 0.5 0.0374; error abs regressed None; NOT COMPUTABLE: pool under 100 players
    2017: n 0
    2018: n 0
    2019: n 0
    2020: n 0
    2021: n 0
    2022: n 0
    2023: n 61, mean gap 0.9548, regressed None, PIT minus 0.5 0.0559, abs regressed None, ordering rho 0.4266
    2024: n 26, mean gap 0.2518, regressed None, PIT minus 0.5 -0.0048, abs regressed None, ordering rho 0.2996
  fangraphs: n 805, computable True; ordering 0.3316; bias regressed None, bias PIT minus 0.5 0.0017; error abs regressed None
    2017: n 92, mean gap 0.2634, regressed None, PIT minus 0.5 0.0208, abs regressed None, ordering rho 0.2289
    2018: n 104, mean gap -0.5283, regressed None, PIT minus 0.5 -0.005, abs regressed None, ordering rho 0.3006
    2019: n 129, mean gap -0.2094, regressed None, PIT minus 0.5 -0.0181, abs regressed None, ordering rho 0.2796
    2020: n 140, mean gap -0.0386, regressed None, PIT minus 0.5 -0.0217, abs regressed None, ordering rho 0.3896
    2021: n 124, mean gap -0.5642, regressed None, PIT minus 0.5 -0.0386, abs regressed None, ordering rho 0.4098
    2022: n 120, mean gap 1.1416, regressed None, PIT minus 0.5 0.0406, abs regressed None, ordering rho 0.3274
    2023: n 69, mean gap 1.6099, regressed None, PIT minus 0.5 0.0784, abs regressed None, ordering rho 0.4067
    2024: n 27, mean gap 1.5003, regressed None, PIT minus 0.5 0.0164, abs regressed None, ordering rho 0.2162
  mlb_pipeline: n 767, computable True; ordering 0.3551; bias regressed None, bias PIT minus 0.5 -0.0265; error abs regressed None
    2017: n 97, mean gap -0.8082, regressed None, PIT minus 0.5 -0.0199, abs regressed None, ordering rho 0.3422
    2018: n 115, mean gap -1.0478, regressed None, PIT minus 0.5 -0.037, abs regressed None, ordering rho 0.302
    2019: n 130, mean gap -0.9635, regressed None, PIT minus 0.5 -0.0425, abs regressed None, ordering rho 0.3026
    2020: n 117, mean gap -0.7095, regressed None, PIT minus 0.5 -0.0526, abs regressed None, ordering rho 0.3527
    2021: n 103, mean gap -1.0063, regressed None, PIT minus 0.5 -0.0643, abs regressed None, ordering rho 0.3882
    2022: n 110, mean gap 0.3472, regressed None, PIT minus 0.5 0.0286, abs regressed None, ordering rho 0.4558
    2023: n 66, mean gap 0.7269, regressed None, PIT minus 0.5 0.0197, abs regressed None, ordering rho 0.4665
    2024: n 29, mean gap 0.2494, regressed None, PIT minus 0.5 0.0067, abs regressed None, ordering rho 0.101
  TIP_f3 for 2017 (fit on the other board years, 574 rows): knots [41.1897, 45.0952, 50.1269, 54.9691, 59.1379], values [-3.1144, -3.1144, -1.8888, 1.9614, 2.2348], thin bins [30, 35, 65, 70, 75]
  TIP_f3 for 2018 (fit on the other board years, 472 rows): knots [41.0926, 45.1017, 50.2488, 54.963, 59.2905], values [-3.166, -3.166, -1.4324, 1.967, 3.1555], thin bins [30, 35, 65, 70, 75]
  TIP_f3 for 2019 (fit on the other board years, 376 rows): knots [40.8864, 45.1224, 50.2395, 54.9538, 59.5673], values [-3.1501, -3.1501, -0.9062, 1.967, 4.1371], thin bins [30, 35, 65, 70, 75]
  TIP_f3 for 2020 (fit on the other board years, 335 rows): knots [41.025, 45.1667, 50.2105, 54.9712, 59.1667], values [-2.5939, -2.5939, -1.2471, 0.6045, 1.7187], thin bins [30, 65, 70, 75]
  TIP_f3 for 2021 (fit on the other board years, 384 rows): knots [41.42, 45.1125, 50.3421, 54.9769, 59.2157], values [-2.4205, -2.1906, -1.1002, -0.4653, 3.3953], thin bins [30, 65, 70, 75]
  TIP_f3 for 2022 (fit on the other board years, 430 rows): knots [41.6111, 45.0811, 50.1382, 54.9805, 58.9286], values [-4.4666, -4.4666, -1.7899, -0.6105, 3.3803], thin bins [65, 70, 75]
  TIP_f3 for 2023 (fit on the other board years, 618 rows): knots [41.5741, 45.0, 50.119, 55.0, 59.0802], values [-4.6705, -4.6705, -1.9501, 0.336, 3.2583], thin bins [30, 65, 70, 75]
  TIP_f3 for 2024 (fit on the other board years, 756 rows): knots [41.5571, 45.0217, 50.1973, 55.0118, 59.1473], values [-3.5117, -3.5117, -1.9501, 0.895, 3.3653], thin bins [30, 35, 65, 70, 75]
- TAG throw / arm_z: frame 964; k_m None (throws); regressed TAG NOT COMPUTABLE
  baseballamerica: n 113, computable True; ordering 0.6483; bias regressed None, bias PIT minus 0.5 0.0684; error abs regressed None
    2017: n 0
    2018: n 0
    2019: n 0
    2020: n 0
    2021: n 0
    2022: n 0
    2023: n 80, mean gap 0.1943, regressed None, PIT minus 0.5 0.0933, abs regressed None, ordering rho 0.6415
    2024: n 33, mean gap -0.0176, regressed None, PIT minus 0.5 0.0096, abs regressed None, ordering rho 0.665
  fangraphs: n 551, computable True; ordering 0.4995; bias regressed None, bias PIT minus 0.5 -0.0148; error abs regressed None
    2017: n 106, mean gap -0.1853, regressed None, PIT minus 0.5 -0.0375, abs regressed None, ordering rho 0.5365
    2018: n 122, mean gap -0.1231, regressed None, PIT minus 0.5 -0.0266, abs regressed None, ordering rho 0.4995
    2019: n 156, mean gap -0.1984, regressed None, PIT minus 0.5 -0.0458, abs regressed None, ordering rho 0.4948
    2020: n 167, mean gap 0.0419, regressed None, PIT minus 0.5 0.0382, abs regressed None, ordering rho 0.4804
    2021: n 0
    2022: n 0
    2023: n 0
    2024: n 0
  mlb_pipeline: n 916, computable True; ordering 0.5757; bias regressed None, bias PIT minus 0.5 -0.0066; error abs regressed None
    2017: n 116, mean gap -0.1708, regressed None, PIT minus 0.5 -0.0483, abs regressed None, ordering rho 0.5408
    2018: n 134, mean gap -0.149, regressed None, PIT minus 0.5 -0.0485, abs regressed None, ordering rho 0.5561
    2019: n 159, mean gap -0.2537, regressed None, PIT minus 0.5 -0.0983, abs regressed None, ordering rho 0.595
    2020: n 141, mean gap -0.001, regressed None, PIT minus 0.5 0.0138, abs regressed None, ordering rho 0.5241
    2021: n 123, mean gap 0.1972, regressed None, PIT minus 0.5 0.0557, abs regressed None, ordering rho 0.5799
    2022: n 120, mean gap 0.176, regressed None, PIT minus 0.5 0.0581, abs regressed None, ordering rho 0.6083
    2023: n 85, mean gap 0.153, regressed None, PIT minus 0.5 0.0669, abs regressed None, ordering rho 0.6501
    2024: n 38, mean gap -0.0241, regressed None, PIT minus 0.5 0.0148, abs regressed None, ordering rho 0.5786
  TIP_f3 for 2017 (fit on the other board years, 638 rows): knots [40.8929, 45.0, 50.1832, 55.0, 59.3571, 65.0, 69.8333], values [-0.6252, -0.6193, -0.1686, 0.3455, 0.6661, 1.607, 1.607], thin bins [75, 80]
  TIP_f3 for 2018 (fit on the other board years, 520 rows): knots [40.7, 45.0, 50.2667, 55.0, 59.3952, 65.0, 69.7059], values [-0.5629, -0.5629, -0.1339, 0.3224, 0.5856, 1.5882, 1.5882], thin bins [35, 75, 80]
  TIP_f3 for 2019 (fit on the other board years, 393 rows): knots [40.7353, 45.0, 50.2212, 55.0, 59.375, 65.0], values [-0.7757, -0.5912, -0.068, 0.4844, 0.6116, 1.6353], thin bins [35, 70, 75, 80]
  TIP_f3 for 2020 (fit on the other board years, 360 rows): knots [40.6522, 45.0, 50.2434, 55.0, 59.2089, 65.0], values [-0.6668, -0.6668, -0.1434, 0.1477, 0.568, 1.6612], thin bins [35, 70, 75, 80]
  TIP_f3 for 2021 (fit on the other board years, 498 rows): knots [40.7258, 45.0, 50.1212, 55.0, 59.1667, 70.0], values [-0.6996, -0.6996, -0.2562, 0.1513, 0.4114, 1.156], thin bins [35, 65, 75]
  TIP_f3 for 2022 (fit on the other board years, 555 rows): knots [40.9615, 45.0, 50.2232, 55.0, 59.1443, 70.0], values [-0.8402, -0.6979, -0.1427, -0.0521, 0.509, 1.4174], thin bins [35, 65, 75]
  TIP_f3 for 2023 (fit on the other board years, 696 rows): knots [40.8333, 45.0, 50.2934, 55.0, 59.3919, 65.0, 70.0], values [-0.8402, -0.6979, -0.1418, 0.1078, 0.5827, 1.7317, 1.7317], thin bins [35, 75]
  TIP_f3 for 2024 (fit on the other board years, 852 rows): knots [40.7979, 45.0, 50.3571, 55.0, 59.3574, 65.0, 70.0], values [-0.8402, -0.7068, -0.1427, 0.2434, 0.6489, 1.6156, 1.6156], thin bins [35, 75, 80]
- TAG game_pwr / iso: frame 1001; k_m 177.5259 (ab); regressed TAG computed
  baseballamerica: n 101, computable True; ordering 0.5973; bias regressed -0.0114, bias PIT minus 0.5 -0.1322; error abs regressed 0.0253
    2017: n 0
    2018: n 0
    2019: n 0
    2020: n 0
    2021: n 0
    2022: n 0
    2023: n 72, mean gap -0.0174, regressed -0.0131, PIT minus 0.5 -0.1469, abs regressed 0.0255, ordering rho 0.5882
    2024: n 29, mean gap -0.0108, regressed -0.0069, PIT minus 0.5 -0.0965, abs regressed 0.0249, ordering rho 0.6201
  fangraphs: n 949, computable True; ordering 0.5223; bias regressed 0.0024, bias PIT minus 0.5 0.0088; error abs regressed 0.0259
    2017: n 107, mean gap 0.0252, regressed 0.0205, PIT minus 0.5 0.1598, abs regressed 0.0332, ordering rho 0.4002
    2018: n 121, mean gap 0.0163, regressed 0.0137, PIT minus 0.5 0.1044, abs regressed 0.0286, ordering rho 0.4848
    2019: n 151, mean gap -0.0071, regressed -0.0044, PIT minus 0.5 -0.0384, abs regressed 0.0243, ordering rho 0.595
    2020: n 167, mean gap -0.0028, regressed -0.0011, PIT minus 0.5 -0.0126, abs regressed 0.0233, ordering rho 0.5412
    2021: n 146, mean gap -0.005, regressed -0.0031, PIT minus 0.5 -0.0501, abs regressed 0.0237, ordering rho 0.5611
    2022: n 142, mean gap -0.0003, regressed 0.0006, PIT minus 0.5 -0.0014, abs regressed 0.0253, ordering rho 0.4938
    2023: n 83, mean gap -0.0057, regressed -0.0039, PIT minus 0.5 -0.0615, abs regressed 0.0251, ordering rho 0.5203
    2024: n 32, mean gap -0.0021, regressed 0.0002, PIT minus 0.5 -0.0403, abs regressed 0.026, ordering rho 0.5835
  mlb_pipeline: n 908, computable True; ordering 0.561; bias regressed -0.0016, bias PIT minus 0.5 -0.0328; error abs regressed 0.0254
    2017: n 116, mean gap 0.0162, regressed 0.0136, PIT minus 0.5 0.092, abs regressed 0.0292, ordering rho 0.4963
    2018: n 133, mean gap 0.0144, regressed 0.0123, PIT minus 0.5 0.0823, abs regressed 0.0281, ordering rho 0.5872
    2019: n 154, mean gap -0.0075, regressed -0.0045, PIT minus 0.5 -0.0412, abs regressed 0.0247, ordering rho 0.5634
    2020: n 142, mean gap -0.0069, regressed -0.0042, PIT minus 0.5 -0.0524, abs regressed 0.0247, ordering rho 0.5343
    2021: n 125, mean gap -0.0132, regressed -0.0094, PIT minus 0.5 -0.106, abs regressed 0.0235, ordering rho 0.5516
    2022: n 129, mean gap -0.0112, regressed -0.0081, PIT minus 0.5 -0.0928, abs regressed 0.0226, ordering rho 0.591
    2023: n 77, mean gap -0.0158, regressed -0.012, PIT minus 0.5 -0.1141, abs regressed 0.0249, ordering rho 0.5979
    2024: n 32, mean gap -0.0117, regressed -0.0077, PIT minus 0.5 -0.1221, abs regressed 0.0256, ordering rho 0.621
  TIP_f3 for 2017 (fit on the other board years, 675 rows): knots [30.1667, 35.0, 40.5984, 45.0759, 49.7548, 55.04, 59.2644], values [0.079, 0.1167, 0.1218, 0.1442, 0.1562, 0.1844, 0.1851], thin bins [20, 25, 65, 70]
  TIP_f3 for 2018 (fit on the other board years, 564 rows): knots [30.431, 35.0, 40.5593, 45.08, 49.7713, 55.0556, 59.4359], values [0.0963, 0.1167, 0.1251, 0.1435, 0.1586, 0.1708, 0.1886], thin bins [25, 65, 70]
  TIP_f3 for 2019 (fit on the other board years, 448 rows): knots [30.0, 34.925, 40.5597, 45.0672, 49.9022, 55.0612, 59.4603], values [0.0998, 0.1188, 0.1367, 0.1567, 0.1666, 0.1791, 0.1896], thin bins [20, 25, 65, 70]
  TIP_f3 for 2020 (fit on the other board years, 397 rows): knots [30.1667, 34.9, 40.3788, 45.1364, 49.9409, 55.0652, 59.3469], values [0.0998, 0.1072, 0.1342, 0.1535, 0.1708, 0.1708, 0.1916], thin bins [20, 65, 70]
  TIP_f3 for 2021 (fit on the other board years, 455 rows): knots [30.0806, 35.0, 40.3353, 45.0357, 49.9252, 55.0263, 59.0268], values [0.0929, 0.1184, 0.1352, 0.1426, 0.1726, 0.1825, 0.1907], thin bins [20, 25, 65, 70]
  TIP_f3 for 2022 (fit on the other board years, 512 rows): knots [30.0806, 35.0, 40.3866, 44.9706, 49.764, 55.075, 58.8942], values [0.0819, 0.1167, 0.1338, 0.1417, 0.164, 0.1849, 0.1907], thin bins [20, 25, 65, 70]
  TIP_f3 for 2023 (fit on the other board years, 736 rows): knots [30.2326, 35.0, 40.3889, 45.0, 49.866, 55.0, 59.0], values [0.081, 0.1175, 0.1342, 0.1447, 0.1659, 0.1851, 0.1922], thin bins [20, 25, 65, 70]
  TIP_f3 for 2024 (fit on the other board years, 898 rows): knots [30.2451, 35.0429, 40.4386, 45.0625, 49.7956, 54.9567, 59.0678], values [0.0819, 0.1184, 0.1308, 0.1426, 0.1607, 0.1845, 0.1899], thin bins [20, 25, 65, 70]
- TAG fb / k_pct_pit: frame 1358; k_m 76.5133 (bf); regressed TAG computed
  baseballamerica: n 162, computable True; ordering 0.4174; bias regressed 0.4592, bias PIT minus 0.5 0.0232; error abs regressed 2.6709
    2017: n 0
    2018: n 0
    2019: n 0
    2020: n 0
    2021: n 0
    2022: n 0
    2023: n 111, mean gap 0.3415, regressed 0.3517, PIT minus 0.5 0.0111, abs regressed 2.6159, ordering rho 0.3547
    2024: n 51, mean gap 0.7882, regressed 0.6932, PIT minus 0.5 0.0489, abs regressed 2.7904, ordering rho 0.5538
  fangraphs: n 1220, computable True; ordering 0.2448; bias regressed 0.5183, bias PIT minus 0.5 0.0179; error abs regressed 2.9008
    2017: n 101, mean gap -0.0007, regressed 0.1331, PIT minus 0.5 -0.0257, abs regressed 3.4249, ordering rho 0.1771
    2018: n 156, mean gap 0.2487, regressed 0.3321, PIT minus 0.5 0.002, abs regressed 2.9776, ordering rho 0.1435
    2019: n 191, mean gap 0.1124, regressed 0.2735, PIT minus 0.5 -0.003, abs regressed 2.806, ordering rho 0.1888
    2020: n 201, mean gap 0.2479, regressed 0.3122, PIT minus 0.5 0.0039, abs regressed 2.7862, ordering rho 0.1629
    2021: n 178, mean gap 1.1982, regressed 1.0432, PIT minus 0.5 0.0534, abs regressed 3.0119, ordering rho 0.2467
    2022: n 186, mean gap 0.8313, regressed 0.7446, PIT minus 0.5 0.0374, abs regressed 2.8479, ordering rho 0.3253
    2023: n 138, mean gap 0.5404, regressed 0.5098, PIT minus 0.5 0.0153, abs regressed 2.671, ordering rho 0.357
    2024: n 69, mean gap 0.9767, regressed 0.8344, PIT minus 0.5 0.0811, abs regressed 2.8718, ordering rho 0.5212
  mlb_pipeline: n 1103, computable True; ordering 0.2722; bias regressed -0.1157, bias PIT minus 0.5 -0.0315; error abs regressed 2.7878
    2017: n 131, mean gap -0.5916, regressed -0.3629, PIT minus 0.5 -0.0761, abs regressed 3.3064, ordering rho 0.2088
    2018: n 171, mean gap -0.6602, regressed -0.4161, PIT minus 0.5 -0.0574, abs regressed 2.8804, ordering rho 0.2059
    2019: n 190, mean gap -0.8899, regressed -0.5926, PIT minus 0.5 -0.0558, abs regressed 2.6505, ordering rho 0.2808
    2020: n 173, mean gap -0.6356, regressed -0.4381, PIT minus 0.5 -0.0478, abs regressed 2.5949, ordering rho 0.2321
    2021: n 138, mean gap 0.6462, regressed 0.5849, PIT minus 0.5 0.0208, abs regressed 2.8344, ordering rho 0.224
    2022: n 133, mean gap 0.3641, regressed 0.3679, PIT minus 0.5 0.0074, abs regressed 2.5975, ordering rho 0.4085
    2023: n 111, mean gap 0.118, regressed 0.1743, PIT minus 0.5 -0.0123, abs regressed 2.6577, ordering rho 0.3412
    2024: n 56, mean gap 0.598, regressed 0.5433, PIT minus 0.5 0.0269, abs regressed 2.9489, ordering rho 0.3763
  TIP_f3 for 2017 (fit on the other board years, 981 rows): knots [45.0349, 50.4952, 54.9689, 59.6806, 65.0, 69.4667], values [20.4066, 20.4066, 21.4099, 22.1094, 22.9958, 24.3289], thin bins [30, 35, 40, 75, 80]
  TIP_f3 for 2018 (fit on the other board years, 798 rows): knots [45.0417, 50.5056, 54.9645, 59.6557, 65.0, 69.5196], values [20.1246, 20.1246, 21.1796, 22.3195, 23.8755, 24.5342], thin bins [30, 35, 40, 75, 80]
  TIP_f3 for 2019 (fit on the other board years, 669 rows): knots [45.0, 50.5767, 54.946, 59.8141, 64.9706, 69.5111], values [19.6356, 19.8328, 21.3759, 22.7399, 23.253, 24.8952], thin bins [30, 35, 40, 75, 80]
  TIP_f3 for 2020 (fit on the other board years, 620 rows): knots [45.0429, 50.6538, 54.9873, 59.7241, 64.9268, 69.41], values [19.6356, 20.1754, 21.2682, 22.4857, 22.5032, 25.2396], thin bins [30, 35, 40, 75, 80]
  TIP_f3 for 2021 (fit on the other board years, 711 rows): knots [44.95, 50.8182, 55.0248, 59.6545, 64.9667, 69.4286], values [19.1394, 20.3347, 20.3347, 21.5457, 22.449, 24.6433], thin bins [30, 35, 40, 75, 80]
  TIP_f3 for 2022 (fit on the other board years, 770 rows): knots [45.0, 50.7653, 54.9659, 59.6638, 65.0341, 69.4388], values [20.7751, 20.7751, 20.992, 21.1207, 22.9607, 24.1237], thin bins [35, 40, 75, 80]
  TIP_f3 for 2023 (fit on the other board years, 939 rows): knots [45.0, 50.5483, 55.0, 59.6432, 65.0, 69.4915], values [20.7578, 20.7578, 21.3004, 21.3115, 22.9958, 24.94], thin bins [30, 40, 75, 80]
  TIP_f3 for 2024 (fit on the other board years, 1152 rows): knots [45.0375, 50.5798, 54.9548, 59.6649, 65.0205, 69.4941, 79.6875], values [20.3325, 20.3325, 21.1783, 21.4017, 22.9401, 24.5342, 27.2945], thin bins [30, 35, 40, 75]
- TAG cmd / bb_pct_pit: frame 1358; k_m 225.8052 (bf); regressed TAG computed
  baseballamerica: n 162, computable True; ordering 0.4149; bias regressed 0.268, bias PIT minus 0.5 0.0367; error abs regressed 1.3217
    2017: n 0
    2018: n 0
    2019: n 0
    2020: n 0
    2021: n 0
    2022: n 0
    2023: n 111, mean gap 0.185, regressed 0.2861, PIT minus 0.5 0.0407, abs regressed 1.375, ordering rho 0.45
    2024: n 51, mean gap 0.2091, regressed 0.2288, PIT minus 0.5 0.0283, abs regressed 1.2057, ordering rho 0.3387
  fangraphs: n 1219, computable True; ordering 0.3033; bias regressed 0.0888, bias PIT minus 0.5 -0.005; error abs regressed 1.3672
    2017: n 101, mean gap -0.4626, regressed -0.2001, PIT minus 0.5 -0.0446, abs regressed 1.0957, ordering rho 0.4739
    2018: n 154, mean gap -0.716, regressed -0.3358, PIT minus 0.5 -0.0704, abs regressed 1.2245, ordering rho 0.4348
    2019: n 191, mean gap -1.032, regressed -0.4621, PIT minus 0.5 -0.0899, abs regressed 1.3613, ordering rho 0.2915
    2020: n 201, mean gap -0.5953, regressed -0.1996, PIT minus 0.5 -0.0627, abs regressed 1.3806, ordering rho 0.2273
    2021: n 179, mean gap 0.5729, regressed 0.4928, PIT minus 0.5 0.0709, abs regressed 1.5066, ordering rho 0.2077
    2022: n 186, mean gap 0.8653, regressed 0.721, PIT minus 0.5 0.0901, abs regressed 1.508, ordering rho 0.2446
    2023: n 138, mean gap 0.5314, regressed 0.4836, PIT minus 0.5 0.0796, abs regressed 1.4047, ordering rho 0.4061
    2024: n 69, mean gap 0.2627, regressed 0.2826, PIT minus 0.5 0.0286, abs regressed 1.2434, ordering rho 0.2145
  mlb_pipeline: n 1104, computable True; ordering 0.3711; bias regressed -0.0552, bias PIT minus 0.5 -0.0255; error abs regressed 1.2747
    2017: n 131, mean gap -0.416, regressed -0.1458, PIT minus 0.5 -0.035, abs regressed 1.1379, ordering rho 0.4173
    2018: n 171, mean gap -0.864, regressed -0.4364, PIT minus 0.5 -0.0893, abs regressed 1.2257, ordering rho 0.3857
    2019: n 190, mean gap -0.9511, regressed -0.4325, PIT minus 0.5 -0.0796, abs regressed 1.2462, ordering rho 0.4002
    2020: n 174, mean gap -0.8124, regressed -0.3555, PIT minus 0.5 -0.0811, abs regressed 1.2704, ordering rho 0.3382
    2021: n 138, mean gap 0.0362, regressed 0.1854, PIT minus 0.5 0.0124, abs regressed 1.3122, ordering rho 0.3132
    2022: n 133, mean gap 0.5803, regressed 0.5796, PIT minus 0.5 0.0715, abs regressed 1.3992, ordering rho 0.3062
    2023: n 111, mean gap 0.477, regressed 0.493, PIT minus 0.5 0.0589, abs regressed 1.383, ordering rho 0.454
    2024: n 56, mean gap 0.409, regressed 0.3478, PIT minus 0.5 0.0679, abs regressed 1.2512, ordering rho 0.3552
  TIP_f3 for 2017 (fit on the other board years, 981 rows): knots [35.12, 40.8937, 44.9536, 49.9779, 54.9767, 58.8987], values [11.3365, 10.6028, 10.2207, 9.2885, 8.3726, 8.3726], thin bins [30, 65, 70]
  TIP_f3 for 2018 (fit on the other board years, 799 rows): knots [35.125, 40.837, 44.9444, 50.0138, 54.9737, 59.0515], values [11.3629, 10.8911, 10.1443, 9.0491, 8.1444, 8.1444], thin bins [30, 65, 70]
  TIP_f3 for 2019 (fit on the other board years, 669 rows): knots [35.0652, 40.8659, 44.9308, 49.9017, 54.9341, 59.1698], values [11.3924, 10.6061, 9.8427, 9.2664, 7.6779, 7.4856], thin bins [30, 65, 70]
  TIP_f3 for 2020 (fit on the other board years, 619 rows): knots [35.0938, 40.8472, 44.8981, 50.0391, 54.9703, 59.0463], values [10.8059, 10.8059, 10.7143, 9.1206, 7.9188, 7.4618], thin bins [30, 65, 70]
  TIP_f3 for 2021 (fit on the other board years, 711 rows): knots [40.9847, 44.9211, 50.0768, 54.9864, 58.8766], values [11.2999, 10.9462, 9.6317, 8.2248, 7.5117], thin bins [30, 35, 65, 70]
  TIP_f3 for 2022 (fit on the other board years, 770 rows): knots [41.0316, 45.0103, 49.926, 55.0583, 58.6728], values [11.9048, 10.8545, 9.9567, 8.2505, 7.8125], thin bins [30, 35, 65, 70]
  TIP_f3 for 2023 (fit on the other board years, 939 rows): knots [41.0047, 44.9726, 50.026, 54.9871, 58.6068], values [10.9034, 10.6267, 9.4911, 8.6937, 8.1081], thin bins [30, 35, 65, 70]
  TIP_f3 for 2024 (fit on the other board years, 1152 rows): knots [35.075, 40.956, 45.0152, 49.9734, 55.0441, 58.7161], values [11.0586, 10.9077, 10.491, 9.4595, 8.272, 8.126], thin bins [30, 65, 70]
- TAG hit_avg / avg: frame 1001; k_m 468.3212 (ab); regressed TAG computed
  baseballamerica: n 101, computable True; ordering 0.0733; bias regressed 0.0007, bias PIT minus 0.5 -0.0013; error abs regressed 0.0118
    2017: n 0
    2018: n 0
    2019: n 0
    2020: n 0
    2021: n 0
    2022: n 0
    2023: n 72, mean gap -0.0013, regressed 0.0003, PIT minus 0.5 0.0031, abs regressed 0.0124, ordering rho 0.0827
    2024: n 29, mean gap 0.0009, regressed 0.0018, PIT minus 0.5 -0.0119, abs regressed 0.0102, ordering rho 0.0499
  fangraphs: n 949, computable True; ordering 0.1086; bias regressed 0.0009, bias PIT minus 0.5 -0.0039; error abs regressed 0.0127
    2017: n 107, mean gap 0.0058, regressed 0.0052, PIT minus 0.5 0.0713, abs regressed 0.014, ordering rho 0.212
    2018: n 121, mean gap 0.0013, regressed 0.0026, PIT minus 0.5 0.02, abs regressed 0.0131, ordering rho 0.0831
    2019: n 151, mean gap -0.0046, regressed -0.0009, PIT minus 0.5 -0.0369, abs regressed 0.0137, ordering rho 0.0699
    2020: n 167, mean gap -0.0044, regressed -0.0012, PIT minus 0.5 -0.0494, abs regressed 0.012, ordering rho 0.119
    2021: n 146, mean gap -0.0062, regressed -0.0028, PIT minus 0.5 -0.0576, abs regressed 0.0116, ordering rho 0.1037
    2022: n 142, mean gap 0.0025, regressed 0.0027, PIT minus 0.5 0.0572, abs regressed 0.0118, ordering rho 0.1899
    2023: n 83, mean gap 0.0019, regressed 0.0026, PIT minus 0.5 0.0201, abs regressed 0.0135, ordering rho -0.0794
    2024: n 32, mean gap 0.0037, regressed 0.0036, PIT minus 0.5 -0.005, abs regressed 0.0116, ordering rho 0.1352
  mlb_pipeline: n 909, computable True; ordering 0.2961; bias regressed 0.0002, bias PIT minus 0.5 -0.0134; error abs regressed 0.0122
    2017: n 116, mean gap 0.0058, regressed 0.0051, PIT minus 0.5 0.0589, abs regressed 0.014, ordering rho 0.3007
    2018: n 133, mean gap 0.0026, regressed 0.0033, PIT minus 0.5 0.0148, abs regressed 0.0134, ordering rho 0.3522
    2019: n 154, mean gap -0.005, regressed -0.0013, PIT minus 0.5 -0.0456, abs regressed 0.013, ordering rho 0.2866
    2020: n 142, mean gap -0.0056, regressed -0.0022, PIT minus 0.5 -0.0625, abs regressed 0.0119, ordering rho 0.289
    2021: n 125, mean gap -0.0066, regressed -0.003, PIT minus 0.5 -0.0484, abs regressed 0.0112, ordering rho 0.2521
    2022: n 130, mean gap 0.0003, regressed 0.0012, PIT minus 0.5 0.0203, abs regressed 0.0105, ordering rho 0.4022
    2023: n 77, mean gap -0.0052, regressed -0.0019, PIT minus 0.5 -0.0245, abs regressed 0.0117, ordering rho 0.1268
    2024: n 32, mean gap 0.0013, regressed 0.002, PIT minus 0.5 0.0118, abs regressed 0.0102, ordering rho 0.2707
  TIP_f3 for 2017 (fit on the other board years, 675 rows): knots [40.8036, 45.0732, 50.2557, 54.8974, 59.0479, 65.0833], values [0.2315, 0.2334, 0.2354, 0.2421, 0.2421, 0.2442], thin bins [30, 35, 70]
  TIP_f3 for 2018 (fit on the other board years, 564 rows): knots [40.8793, 45.0833, 50.3684, 54.8857, 59.191, 65.0882], values [0.2319, 0.2333, 0.2349, 0.2445, 0.2455, 0.2457], thin bins [30, 35, 70]
  TIP_f3 for 2019 (fit on the other board years, 448 rows): knots [41.1735, 45.123, 50.2938, 54.85, 59.2727, 65.075], values [0.231, 0.2354, 0.2379, 0.2486, 0.2507, 0.2507], thin bins [30, 35, 70]
  TIP_f3 for 2020 (fit on the other board years, 397 rows): knots [41.3382, 45.0763, 50.2986, 54.8581, 59.0526, 65.1765], values [0.2236, 0.2334, 0.2434, 0.2507, 0.2511, 0.2511], thin bins [30, 35, 70, 75]
  TIP_f3 for 2021 (fit on the other board years, 455 rows): knots [41.0667, 45.0423, 50.328, 54.9643, 58.6765, 65.1765], values [0.2249, 0.2335, 0.243, 0.2534, 0.2551, 0.2551], thin bins [30, 35, 70, 75]
  TIP_f3 for 2022 (fit on the other board years, 512 rows): knots [41.0833, 44.9786, 50.3265, 55.0, 58.7361], values [0.2234, 0.2308, 0.2408, 0.2464, 0.2509], thin bins [30, 35, 65, 70, 75]
  TIP_f3 for 2023 (fit on the other board years, 736 rows): knots [40.9596, 45.0, 50.3204, 55.0, 58.8553], values [0.2234, 0.2333, 0.2427, 0.2463, 0.2555], thin bins [30, 35, 65, 70, 75]
  TIP_f3 for 2024 (fit on the other board years, 898 rows): knots [40.9386, 45.0126, 50.2735, 54.961, 58.9154, 65.0], values [0.2246, 0.2333, 0.2392, 0.2463, 0.2487, 0.2487], thin bins [30, 35, 70, 75]
- TAG speed_sb / sb_per600: frame 1001; k_m 75.7105 (pa); regressed TAG computed
  baseballamerica: n 101, computable True; ordering 0.7617; bias regressed 2.1713, bias PIT minus 0.5 0.0482; error abs regressed 5.238
    2017: n 0
    2018: n 0
    2019: n 0
    2020: n 0
    2021: n 0
    2022: n 0
    2023: n 72, mean gap 1.9199, regressed 1.8256, PIT minus 0.5 0.0325, abs regressed 5.3371, ordering rho 0.7359
    2024: n 29, mean gap 3.4447, regressed 3.0294, PIT minus 0.5 0.0877, abs regressed 4.9918, ordering rho 0.8257
  fangraphs: n 949, computable True; ordering 0.6851; bias regressed 2.3566, bias PIT minus 0.5 0.044; error abs regressed 6.2002
    2017: n 107, mean gap -0.1664, regressed -0.0618, PIT minus 0.5 -0.0289, abs regressed 5.208, ordering rho 0.636
    2018: n 121, mean gap -1.2044, regressed -0.9775, PIT minus 0.5 -0.1061, abs regressed 5.7068, ordering rho 0.6199
    2019: n 151, mean gap -0.8118, regressed -0.642, PIT minus 0.5 -0.0806, abs regressed 5.9171, ordering rho 0.647
    2020: n 167, mean gap 4.3529, regressed 3.9793, PIT minus 0.5 0.1016, abs regressed 6.3636, ordering rho 0.7023
    2021: n 146, mean gap 4.5016, regressed 4.1237, PIT minus 0.5 0.1154, abs regressed 6.392, ordering rho 0.7141
    2022: n 142, mean gap 5.9022, regressed 5.378, PIT minus 0.5 0.1613, abs regressed 7.3245, ordering rho 0.7232
    2023: n 83, mean gap 4.0789, regressed 3.7706, PIT minus 0.5 0.1171, abs regressed 6.2042, ordering rho 0.7232
    2024: n 32, mean gap 4.1143, regressed 3.5941, PIT minus 0.5 0.1096, abs regressed 5.993, ordering rho 0.7852
  mlb_pipeline: n 909, computable True; ordering 0.7043; bias regressed 0.6298, bias PIT minus 0.5 -0.0347; error abs regressed 5.9052
    2017: n 116, mean gap -2.4571, regressed -2.1139, PIT minus 0.5 -0.1484, abs regressed 5.4184, ordering rho 0.6774
    2018: n 133, mean gap -3.4668, regressed -3.023, PIT minus 0.5 -0.1617, abs regressed 6.2914, ordering rho 0.6272
    2019: n 154, mean gap -1.8384, regressed -1.5724, PIT minus 0.5 -0.1024, abs regressed 6.1029, ordering rho 0.6091
    2020: n 142, mean gap 2.7267, regressed 2.5103, PIT minus 0.5 0.006, abs regressed 5.8732, ordering rho 0.7151
    2021: n 125, mean gap 2.9148, regressed 2.6674, PIT minus 0.5 0.0306, abs regressed 5.9927, ordering rho 0.7442
    2022: n 130, mean gap 3.909, regressed 3.5893, PIT minus 0.5 0.0882, abs regressed 5.8922, ordering rho 0.7735
    2023: n 77, mean gap 3.1544, regressed 2.9406, PIT minus 0.5 0.0574, abs regressed 5.801, ordering rho 0.814
    2024: n 32, mean gap 2.8313, regressed 2.4688, PIT minus 0.5 0.0667, abs regressed 5.2169, ordering rho 0.8321
  TIP_f3 for 2017 (fit on the other board years, 675 rows): knots [30.6932, 35.1364, 40.2338, 44.9224, 50.1963, 54.82, 59.3238, 65.1111, 69.8913], values [1.41, 2.7624, 4.7138, 6.8293, 11.2711, 14.6771, 17.1443, 22.8242, 32.8767], thin bins [20, 25, 75, 80]
  TIP_f3 for 2018 (fit on the other board years, 564 rows): knots [30.4429, 35.1622, 40.3448, 44.9043, 50.2972, 54.7923, 59.4, 65.15, 70.0], values [1.6854, 2.7624, 5.2764, 7.1429, 12.0, 14.9341, 19.2073, 27.0034, 33.5968], thin bins [20, 25, 75, 80]
  TIP_f3 for 2019 (fit on the other board years, 448 rows): knots [30.2424, 35.2143, 40.3563, 44.9082, 50.2097, 54.7818, 59.306, 69.8611], values [1.3857, 2.4039, 5.2897, 6.2547, 12.0, 15.08, 19.3772, 33.2368], thin bins [20, 25, 65, 80]
  TIP_f3 for 2020 (fit on the other board years, 397 rows): knots [30.2903, 35.2609, 40.4, 44.9362, 50.0946, 54.8393, 58.9855], values [1.884, 1.884, 4.5455, 4.9107, 8.5229, 14.0179, 15.6863], thin bins [20, 25, 65, 70, 80]
  TIP_f3 for 2021 (fit on the other board years, 455 rows): knots [30.2778, 35.1, 40.2388, 45.0349, 50.0227, 54.9048, 59.0584, 69.2188], values [1.8225, 1.8225, 3.0501, 4.2654, 8.251, 16.2601, 16.2601, 16.2601], thin bins [20, 25, 65, 75, 80]
  TIP_f3 for 2022 (fit on the other board years, 512 rows): knots [30.5488, 35.0, 40.0823, 45.0385, 50.1727, 54.9262, 58.8229, 65.0, 69.3421], values [1.1881, 1.4711, 2.1016, 4.2654, 9.919, 13.6674, 15.7068, 16.9506, 16.9506], thin bins [20, 25, 75, 80]
  TIP_f3 for 2023 (fit on the other board years, 736 rows): knots [30.5357, 34.9674, 40.2282, 45.0, 50.0875, 55.0, 58.9918, 65.0, 69.537], values [1.5312, 2.1273, 3.4202, 6.4748, 10.4953, 13.9998, 16.1568, 19.1304, 24.0], thin bins [20, 25, 75, 80]
  TIP_f3 for 2024 (fit on the other board years, 898 rows): knots [30.6615, 35.1071, 40.2429, 44.9786, 50.1757, 54.9176, 59.1235, 65.0, 69.6094], values [1.1881, 1.9905, 3.7879, 4.9169, 10.7482, 14.3322, 17.9539, 20.5897, 26.2037], thin bins [20, 25, 75, 80]
- TAG raw_pwr / ev_avg: frame 949; k_m 43.6082 (attempts); regressed TAG computed
  fangraphs: n 949, computable True; ordering 0.507; bias regressed 0.0376, bias PIT minus 0.5 -0.004; error abs regressed 1.2183
    2017: n 107, mean gap 0.0128, regressed 0.0294, PIT minus 0.5 -0.0127, abs regressed 1.2621, ordering rho 0.4608
    2018: n 121, mean gap -0.1672, regressed -0.133, PIT minus 0.5 -0.0251, abs regressed 1.1523, ordering rho 0.5331
    2019: n 151, mean gap -0.2595, regressed -0.2219, PIT minus 0.5 -0.063, abs regressed 1.212, ordering rho 0.57
    2020: n 167, mean gap -0.1818, regressed -0.1547, PIT minus 0.5 -0.0303, abs regressed 1.1887, ordering rho 0.4849
    2021: n 146, mean gap 0.1033, regressed 0.1046, PIT minus 0.5 0.0164, abs regressed 1.193, ordering rho 0.5078
    2022: n 142, mean gap 0.504, regressed 0.4867, PIT minus 0.5 0.0724, abs regressed 1.3276, ordering rho 0.4726
    2023: n 83, mean gap 0.0904, regressed 0.0967, PIT minus 0.5 -0.0029, abs regressed 1.1117, ordering rho 0.5333
    2024: n 32, mean gap 0.5223, regressed 0.485, PIT minus 0.5 0.0722, abs regressed 1.411, ordering rho 0.4619
  TIP_f3 for 2017 (fit on the other board years, 674 rows): knots [30.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0], values [86.252, 86.8366, 87.564, 88.3108, 88.9186, 89.119, 90.058, 90.1591], thin bins [35, 80]
  TIP_f3 for 2018 (fit on the other board years, 566 rows): knots [40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0], values [86.8991, 87.5607, 88.4087, 89.0699, 89.119, 90.2355, 90.3053], thin bins [30, 35, 80]
  TIP_f3 for 2019 (fit on the other board years, 438 rows): knots [40.0, 45.0, 50.0, 55.0, 60.0, 70.0], values [87.4431, 87.5006, 88.5434, 88.7263, 89.2297, 90.3381], thin bins [30, 35, 65, 80]
  TIP_f3 for 2020 (fit on the other board years, 365 rows): knots [40.0, 45.0, 50.0, 55.0, 60.0, 70.0], values [87.2357, 87.2357, 88.7425, 88.934, 89.2075, 90.4518], thin bins [30, 35, 65, 80]
  TIP_f3 for 2021 (fit on the other board years, 420 rows): knots [40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0], values [87.4589, 87.4589, 88.0103, 88.6547, 89.0705, 89.6614, 90.4175], thin bins [30, 35, 80]
  TIP_f3 for 2022 (fit on the other board years, 481 rows): knots [40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0], values [86.9183, 87.3689, 87.7935, 88.1703, 89.5027, 90.0335, 90.1855], thin bins [30, 35, 80]
  TIP_f3 for 2023 (fit on the other board years, 697 rows): knots [30.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0], values [86.155, 87.284, 87.5674, 88.0892, 88.624, 89.3165, 90.0457, 90.44], thin bins [35, 80]
  TIP_f3 for 2024 (fit on the other board years, 856 rows): knots [30.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0], values [86.155, 86.8467, 87.5005, 88.1132, 88.6582, 89.2297, 89.7823, 90.4175], thin bins [35, 80]
- TAG pitch_sel / chase_pct: frame 438; k_m 68.3172 (oz_pitches); regressed TAG computed
  fangraphs: n 438, computable True; ordering 0.4644; bias regressed -0.0068, bias PIT minus 0.5 -0.0037; error abs regressed 0.0307
    2021: n 133, mean gap -0.0144, regressed -0.0081, PIT minus 0.5 -0.0584, abs regressed 0.0336, ordering rho 0.4336
    2022: n 145, mean gap -0.0193, regressed -0.0122, PIT minus 0.5 0.0549, abs regressed 0.0328, ordering rho 0.4852
    2023: n 105, mean gap -0.0044, regressed -0.0013, PIT minus 0.5 0.0228, abs regressed 0.0282, ordering rho 0.4828
    2024: n 55, mean gap 0.0015, regressed -0.0, PIT minus 0.5 0.0176, abs regressed 0.0229, ordering rho 0.4487
  TIP_f3 for 2021 (fit on the other board years, 141 rows): knots [40.0, 45.0, 50.0, 55.0, 60.0], values [0.343, 0.318, 0.2848, 0.2848, 0.268], thin bins [20, 30, 35, 70]
  TIP_f3 for 2022 (fit on the other board years, 86 rows): knots [55.0, 60.0], values [0.299, 0.271], thin bins [30, 35, 40, 45, 50, 70]
  TIP_f3 for 2023 (fit on the other board years, 167 rows): knots [30.0, 40.0, 45.0, 50.0, 55.0, 60.0], values [0.3475, 0.3475, 0.313, 0.304, 0.291, 0.26], thin bins [35, 70]
  TIP_f3 for 2024 (fit on the other board years, 298 rows): knots [30.0, 40.0, 45.0, 50.0, 55.0, 60.0], values [0.348, 0.348, 0.323, 0.312, 0.288, 0.257], thin bins [20, 35, 70, 80]
- TAG bat_ctrl / z_contact_pct: frame 446; k_m 59.3017 (iz_swings); regressed TAG computed
  fangraphs: n 446, computable True; ordering 0.4016; bias regressed 0.0074, bias PIT minus 0.5 -0.0057; error abs regressed 0.03
    2021: n 139, mean gap -0.0019, regressed 0.0022, PIT minus 0.5 -0.0459, abs regressed 0.0314, ordering rho 0.387
    2022: n 147, mean gap 0.0094, regressed 0.0084, PIT minus 0.5 -0.0331, abs regressed 0.03, ordering rho 0.4627
    2023: n 105, mean gap 0.0205, regressed 0.0166, PIT minus 0.5 0.0826, abs regressed 0.0305, ordering rho 0.3767
    2024: n 55, mean gap -0.0047, regressed 0.0006, PIT minus 0.5 -0.0226, abs regressed 0.0256, ordering rho 0.3232
  TIP_f3 for 2021 (fit on the other board years, 127 rows): knots [40.0, 45.0, 50.0, 55.0, 60.0], values [0.788, 0.836, 0.8395, 0.8395, 0.8395], thin bins [20, 30, 35, 70]
  TIP_f3 for 2022 (fit on the other board years, 82 rows): knots [40.0, 50.0, 60.0], values [0.774, 0.8422, 0.8422], thin bins [20, 30, 35, 45, 55, 70]
  TIP_f3 for 2023 (fit on the other board years, 165 rows): knots [40.0, 45.0, 50.0, 55.0, 60.0], values [0.7495, 0.8205, 0.8235, 0.8508, 0.8508], thin bins [20, 30, 35, 65, 70, 80]
  TIP_f3 for 2024 (fit on the other board years, 302 rows): knots [40.0, 45.0, 50.0, 55.0, 60.0], values [0.79, 0.835, 0.84, 0.849, 0.863], thin bins [20, 30, 65, 70, 80]

Controls (W.7): C6.1 the permuted-source-label floor, C6.3 the shuffled outcome, C6.4 the forced-equal identity, C6.5 seed stability at 1337, C6.7 the player-disjoint weight arm and the single-source context are printed per cell above. C6.2 (pooled-tool) is not computed by this runner (gate Part 6: no tool pooling; it would be a control only, never a result). C6.6 (the survivorship boundary) is the sentence below with the universe counts above.

Inputs sha256 at start (unchanged through the run: True):
  .cache/fa_statsapi_hitting_2018.json 0ed27cb23043ba42c748622f855ee676222aff4700656e93183d465bafbd1e97
  .cache/fa_statsapi_hitting_2019.json 66af1f1fa1869f5e22a3e20760d7f7929635b2600781c816822c7e7401142036
  .cache/fa_statsapi_hitting_2020.json 60a5ab0cc36c99bbbe322e1f0479bc5049a51b8eea4a2344eb0fb6c4c9869f5a
  .cache/fa_statsapi_hitting_2021.json ec737cc5087fb03ae3cc2d3db1a7a5dc46d2d68e661c3d53639d76bd3b1dda02
  .cache/fa_statsapi_hitting_2022.json 44ac1610bfda4cb594effa32a728aba9e756fecd163408b2525c1c6bd98c9599
  .cache/fa_statsapi_hitting_2023.json 1434de28fbc752eabb57804b184823fdf521f731169c22b71c7ad098c5986c5c
  .cache/fa_statsapi_hitting_2024.json 8bb44c15db16a8f8cfe2bccc08e5ad304be72ca38960a101de2454175dabd8c8
  .cache/fa_statsapi_hitting_2025.json a1e6455e8758ea0350b07bbcfe0126d1f5e71b56616ff819211677e7a1094935
  .cache/fa_statsapi_hitting_2026.json 1c7b86415b27d2fa6724d69ab88c947d5b839583e429f33a475d8a2fa375aabf
  .cache/fa_statsapi_pitching_2018.json 6c2f6dc7623cb7cdea905b739ab50b85f018c28c35ad09ae66e092f537da677e
  .cache/fa_statsapi_pitching_2019.json f7059a367d50d6ed41d40ddc1bb59ba0fbc7e82f1407983f0cb526c4ae1b9864
  .cache/fa_statsapi_pitching_2020.json 6f6e128c1f0f55f4445d9ec10ddb175f0a89475db94e931dddc7a97252c1ac62
  .cache/fa_statsapi_pitching_2021.json 6063e2ffac8f8f883ce9e88f823863d107b77cb6066a9b8d56aa43cdfe519c70
  .cache/fa_statsapi_pitching_2022.json fd7fb55b0a903cbe74885cfab53142b23a73f629e6140b83809eba183c7baad8
  .cache/fa_statsapi_pitching_2023.json 8fb532797c229434c33a165506232cfac116071cf3e3322df9ab3eb5b116df75
  .cache/fa_statsapi_pitching_2024.json f00d025220bb6ccacc24784de50c42f4a8135d7690af6026aeace9172dcdb225
  .cache/fa_statsapi_pitching_2025.json 18085f1ff299af1724d677928fae14166429658971bd62a14dc59e6cb2be5392
  .cache/fa_statsapi_pitching_2026.json b81b02f8f44ca543d5cc77d260f83feea5ef2c2baf77c96a0b62965bc3adbe0c
  .cache/savant_sprint/sprint_2018.csv a48305018976f4cd5255c4fb03d877ad9d6a1d54aaa546f8fd2bdc147762e452
  .cache/savant_sprint/sprint_2019.csv 63a9a5ae8b40ad52161a4f707c357d2ef70d16b656472a22bbb88e67a56724e7
  .cache/savant_sprint/sprint_2020.csv 3e738ef9c260c454e4ec76b41b681918115a919fb6a58355d9d51f046aa89c30
  .cache/savant_sprint/sprint_2021.csv b37712650abe963431530953039a8fb15f331d9a54ba8b43dcadfab36734fcbb
  .cache/savant_sprint/sprint_2022.csv 0705e947a0a183dcfc79545a83c668d8ecf1750a3fa2a6022fc17564a50768a4
  .cache/savant_sprint/sprint_2023.csv 1d6ce0c818c1ec18e84a83b934e26e229c1001c5f66cca3d69049978df05c265
  .cache/savant_sprint/sprint_2024.csv 270fdc5232eef62f8c74b376d0dfc670c79aa4e69bb0d575debfe220f1865855
  .cache/savant_sprint/sprint_2025.csv c72bce2fad5c6c708796d4133d2da3b6bb5f010b0635896bcc32cacd28d76f66
  .cache/savant_sprint/sprint_2026.csv 6457586d8a675540a38774e509ea6159fedab07690ca6ef6dd6f0af1617d1502
  .cache/savant_arm/arm_2020.csv 05cd36b211236825b56bbc42d61090679db47a0d2ce9ca4ba34960e11b19fbe5
  .cache/savant_arm/arm_2021.csv 16bb297fa631349ec94f7e663ad9e88cd1dd90b3961c023a0aa9535fe7017a60
  .cache/savant_arm/arm_2022.csv 06115a3f6b6c6c43f19407d2ed2508097f33dbbbfbe4b0498bdcad8969ad5093
  .cache/savant_arm/arm_2023.csv 23aa59669768c3e7408da22021bde717c2a43d6768f892f8259e41a77b7f4263
  .cache/savant_arm/arm_2024.csv c6b96226c5c6b9cd5b4eae5d2b68093860f0a41b33570bd55c9fba4ae7a3fbf1
  .cache/savant_arm/arm_2025.csv c959b2533a7e0c4e6b6436a33c770010e76688ad922e2ff51a13707d2fd5caf8
  .cache/savant_arm/arm_2026.csv 3913cbdba6a21fb590138c5945aceb202b101b116161a68afb81207e6799ebe8
  data/fielding_innings.json d572e2c1dd02f8f26ea5b835a0b55e092bd68251fb8c3be058f4991d36ac5e31
  data/hitter_leaderboards.json c5b7442f8523432ef7fae933705dcef2b6f9645e79928ab5b7c991e7bd20caf6

Accuracy AMONG DEBUTS: only players who reached the majors have a realized MLB quantity, so this is not accuracy over all graded prospects (gate Part 0.6).

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

**Amendment of 2026-10-14 (TL_4_TOOL_LAB_BUILD, item 2 of the list at the top; committed alone, on a calendar day before the look).** Computed by `python tools/tool_accuracy_lab.py --look T --mde-only` on FIT rows only: MLB seasons [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025] (velocity [2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]); no HOLDOUT row and no 2026 line was loaded (asserted by the runner). The fold deltas are in `data/_labs/tool_tables_rederived/mde95_folds.json` (sha256 fc989b2ed453ace41900321e83345c633e4b4d6e7fc3a55c7395e03120f9d308). Frozen grade rows `data/_labs/tool_tables_rederived/grade_rows_frozen.json`: 1379 rows, sha256 eb7f31c1033de8afef9db868dc2c25c3982a5febe056536c3f60118034ff206c.

| cell | MDE95 | folds used | rows per fold (season: n) | skipped folds |
|---|---|---|---|---|
| game_pwr__hr_per600 | 0.771543 | 8 | {'2017': 74, '2018': 93, '2019': 120, '2021': 122, '2022': 135, '2023': 155, '2024': 170, '2025': 170} | 2015: under 60 rows; 2016: under 60 rows |
| game_pwr__iso | 0.011502 | 8 | {'2017': 74, '2018': 93, '2019': 120, '2021': 122, '2022': 135, '2023': 155, '2024': 170, '2025': 170} | 2015: under 60 rows; 2016: under 60 rows |
| hit__avg | 0.004357 | 8 | {'2017': 74, '2018': 93, '2019': 120, '2021': 122, '2022': 135, '2023': 155, '2024': 170, '2025': 170} | 2015: under 60 rows; 2016: under 60 rows |
| hit__k_pct | 0.310511 | 8 | {'2017': 74, '2018': 93, '2019': 120, '2021': 122, '2022': 135, '2023': 155, '2024': 170, '2025': 170} | 2015: under 60 rows; 2016: under 60 rows |
| speed__sb_per600 | 0.42331 | 8 | {'2017': 74, '2018': 93, '2019': 120, '2021': 122, '2022': 135, '2023': 155, '2024': 170, '2025': 170} | 2015: under 60 rows; 2016: under 60 rows |
| cmd__bb_pct_sp | 0.138746 | 8 | {'2016': 65, '2018': 67, '2019': 78, '2021': 76, '2022': 98, '2023': 112, '2024': 131, '2025': 121} | 2015: under 60 rows; 2017: under 60 rows |
| fb__velo_sp | 0.493917 | 7 | {'2018': 67, '2019': 78, '2021': 76, '2022': 98, '2023': 112, '2024': 131, '2025': 121} | 2017: under 60 rows |

MDE95 is 1.645 times the sample standard deviation (ddof 1) of d_s over the folds used; a fold with fewer than 60 rows leaves (the hitter cells' 2015 and 2016 folds, the SP cells' 2015 to 2017 folds as listed). Every primary cell holds at least 5 folds, so none is NOT COMPUTABLE for want of an MDE95.

FIT inputs, sha256:
- `.cache/fa_statsapi_hitting_2015.json`: 22afbc2b209e26c6a23cd1fdda51125756a1998b2d1d713c63b3be7cd5c3afc2
- `.cache/fa_statsapi_hitting_2016.json`: b04598774abf37ad482bd17cc95b42972fa3837e364706ec404faa36b3c18817
- `.cache/fa_statsapi_hitting_2017.json`: bb14f2a006eece205a1f1dc17a734c7eaa441eb2b9468e3f9c42dbff47577d39
- `.cache/fa_statsapi_hitting_2018.json`: 0ed27cb23043ba42c748622f855ee676222aff4700656e93183d465bafbd1e97
- `.cache/fa_statsapi_hitting_2019.json`: 66af1f1fa1869f5e22a3e20760d7f7929635b2600781c816822c7e7401142036
- `.cache/fa_statsapi_hitting_2021.json`: ec737cc5087fb03ae3cc2d3db1a7a5dc46d2d68e661c3d53639d76bd3b1dda02
- `.cache/fa_statsapi_hitting_2022.json`: 44ac1610bfda4cb594effa32a728aba9e756fecd163408b2525c1c6bd98c9599
- `.cache/fa_statsapi_hitting_2023.json`: 1434de28fbc752eabb57804b184823fdf521f731169c22b71c7ad098c5986c5c
- `.cache/fa_statsapi_hitting_2024.json`: 8bb44c15db16a8f8cfe2bccc08e5ad304be72ca38960a101de2454175dabd8c8
- `.cache/fa_statsapi_hitting_2025.json`: a1e6455e8758ea0350b07bbcfe0126d1f5e71b56616ff819211677e7a1094935
- `.cache/fa_statsapi_pitching_2015.json`: 64f223e3f62297abc922ebc2952cabfba462f1788e74fd8ae11a811f8e7e0ddb
- `.cache/fa_statsapi_pitching_2016.json`: 1e8cdd99e1ce92b443dcfc373ffc185a9a94f4bf25a65a381deb07f8be0825f0
- `.cache/fa_statsapi_pitching_2017.json`: 3ffab5e561f0cf194a4c51dea8d6638c223d83a1827af446b320da7fedb76369
- `.cache/fa_statsapi_pitching_2018.json`: 6c2f6dc7623cb7cdea905b739ab50b85f018c28c35ad09ae66e092f537da677e
- `.cache/fa_statsapi_pitching_2019.json`: f7059a367d50d6ed41d40ddc1bb59ba0fbc7e82f1407983f0cb526c4ae1b9864
- `.cache/fa_statsapi_pitching_2021.json`: 6063e2ffac8f8f883ce9e88f823863d107b77cb6066a9b8d56aa43cdfe519c70
- `.cache/fa_statsapi_pitching_2022.json`: fd7fb55b0a903cbe74885cfab53142b23a73f629e6140b83809eba183c7baad8
- `.cache/fa_statsapi_pitching_2023.json`: 8fb532797c229434c33a165506232cfac116071cf3e3322df9ab3eb5b116df75
- `.cache/fa_statsapi_pitching_2024.json`: f00d025220bb6ccacc24784de50c42f4a8135d7690af6026aeace9172dcdb225
- `.cache/fa_statsapi_pitching_2025.json`: 18085f1ff299af1724d677928fae14166429658971bd62a14dc59e6cb2be5392
- `.cache/velo_arsenal_2017.json`: 1de85c5aefb22511e8eebb60cfe784154f5d13039605b2f7b265e261e4d875dc
- `.cache/velo_arsenal_2018.json`: 4f04b07237aae015ee39a4adb77fdff46396cc7ead774cf9d297a37ab28e2465
- `.cache/velo_arsenal_2019.json`: 8fd4e1186bc7ccf1a26b067f3099bc26d8066eedbb3b2a86d32fc11ae4463a07
- `.cache/velo_arsenal_2021.json`: 10715f92e81d188c154d3d96b99926ddc40b2aebad928656e6c1bef6d2f7329a
- `.cache/velo_arsenal_2022.json`: d64131221e64de9300f284543e9c4e364bc23096a54b1644033a1783476396ef
- `.cache/velo_arsenal_2023.json`: a03e160ef5390256cda682dc413432271bb572a5d03736ec7dc03b1b835549f6
- `.cache/velo_arsenal_2024.json`: fb5cb50451407c7247503473285ca32dc4042b85b5addb8b1e3d25df4870178d
- `.cache/velo_arsenal_2025.json`: 827868119115d06f811e17620656c255074a640b6c81cba00f7ab1e16df11736

`.cache/velo_arsenal_2026.json`: present True, sha256 fadbb7483c682e582e63e76867c31cd7a4de2f20ea00fd884e41d78eb665f71d, written 2026-10-14T15:48:07.298070+00:00 through `pal_export.load_velo(2026)` (602 rows) after the 2026 regular season ended; no value in it was read.

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

### 2026-10-14: look W taken as an OWNER-WAIVED EARLY READ (EW3-5)

Dated note appended by TL_12_TOOL_WEIGHTS_LOOK below the last section, as the owner's instruction of
2026-10-14 directs (EW3-5, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`: registered dates and look days are
waived for every task; an early look is recorded as an owner-waived early read). W.11's day rule named the
first day after TL_4_TOOL_LAB_BUILD landed (ccec9eb7, 9d351dc3 and 77bd4302, all 2026-10-14) and after the
R-LV record (1c73c420, 2026-10-08) on which the W.8 frame is complete and no other registered look is
recorded; the plan's floor of 2026-12-03 had already been replaced by that condition. Other gate documents
carry look entries dated 2026-10-14 under the same waiver, so W.11's 'no other look recorded that day' clause
and the 'looking early disqualifies' clause are waived by EW3-5, not met. The W.8 frame was complete on disk
(MLB seasons through 2026 in every input, each frozen by sha256 in the Part 8 record and unchanged from the
start to the end of the run). The look ran once; its record is the Part 8 'Look W' entry; it is VOID under
W.7, and nothing above Part 8 was edited.
