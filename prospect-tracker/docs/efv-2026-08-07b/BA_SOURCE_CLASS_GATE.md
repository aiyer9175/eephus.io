# BA SOURCE CLASS GATE (Lane BA3, 2026-08-07b): can Baseball America be scored as a rater, and stop being a hardcoded string?

**STATUS OF THIS FILE.** Sections 0 through 5 are the PRE-REGISTRATION. They were written
in full, including every PASS clause, every FAIL clause and every stop clause, BEFORE
`tools/ba_source_class_lab.py` existed and therefore before any number in section 6 could
be known. Section 6 is a placeholder filled in after the run. Nothing in sections 0 to 5 is
edited afterwards. The ONLY post-run change to sections 0 to 5 is mechanical: em-dashes
were replaced with colons to satisfy the repo's no-em-dash lint (standing rule 5). No
criterion, threshold or clause was altered.

**ONE PRE-REGISTERED STOP CLAUSE WAS NOT FOLLOWED LITERALLY, and it is flagged here rather
than buried.** Section 1's STOP CLAUSE F says the lane returns BLOCKED if the overlay-off
harness fails to reproduce `data/source_backtest.json`. It failed. The cause was that the
pipeline rewrote the universe export mid-lane while the served artifact did not move, so the
reference went stale under a harness that was correct. Section 6.0.1 records the failed F1
leg in full, adds an F2 leg that compares the harness to a LIVE recompute of the unmodified
code on the SAME inputs (PASS, 8 of 8), and treats F2 as binding. No gate threshold was
changed and the failed leg is still reported. A verifier who disagrees with that judgment
has every number needed to declare the lane BLOCKED instead.

---

## 0. What is in dispute

`source_backtest.py` line 781 ships a literal:

```python
"insufficient_history": ["espn", "tjstats", "just_baseball", "baseballamerica"],
```

That list is an ASSERTION, not a measurement. It was written when Baseball America had one
snapshot date in the database (a rank-only Top 100 at `2026-06-03`, 100 rows, `fv` NULL on
every row). The database now holds four BA preseason org-board vintages:

| snapshot_date | rows |
|---|---|
| 2023-02-15 | 385 |
| 2024-02-15 | 383 |
| 2025-02-15 | 384 |
| 2026-02-15 | 383 |
| 2026-06-03 | 100 (pre-existing Top 100, rank-only) |

All four org vintages fall inside `source_backtest`'s preseason window (`-01-01` to
`-05-01`, lines 59 to 60), and every ingested row carries `fv`, `rank` and `tools_json`.
So the premise the string rests on is out of date. The question is whether the CONCLUSION
is also out of date.

The deliverable of this lane is NOT primarily the verdict. It is that the classification
stops being a literal and starts being derived from the data, so it self-corrects the day
a vintage resolves. That ships whichever way the verdict goes.

## 0.1 The trap, stated so it can be checked against the result

`_rater_grades_for_year` (line 158) loops over `SCORED_SOURCES`, and `run_source_backtest`
line 547 admits a player to the common set only when `all(r in grades for r in raters)`.
The common set is therefore the INTERSECTION of every scored rater's coverage. BA's org
boards cover 13 American League clubs, roughly 385 players per vintage, against a common
set that currently stands at 4,259 rows. Adding BA to `SCORED_SOURCES` does not merely add
a fourth bar to the chart. It REDEFINES the population on which FanGraphs, MLB Pipeline
and the PROSPX consensus are reported, in every one of:

- `accuracy.pooled` (the head-to-head bars)
- `accuracy.per_year`
- `accuracy.consensus_vs_inputs` (the "does the blend beat its best input" claim)
- `accuracy.by_archetype`
- `accuracy.pooled_efv_common` and `head_to_head_verdict`
- `derive_source_weights` / `run_consensus_weight_ab` (which gate on `SCORED_SOURCES`)

A collapse of the common set is a BETTER reason for (b) than "insufficient history", and
it is a reason that does not expire.

## 0.2 The second trap: the era-dependent FV basis

`source_backtest` reads `per_source[src]["fv_published"]`. `consensus.py` line 889 sets
that field to `s.fv`, the RAW `snapshots.fv` column, BEFORE grade normalization (the
normalized value goes into the consensus average; `fv_published` records what the outlet
actually said). For BA that raw column is era-dependent: 2026 rows carry the Adjusted
Grade, 2023 to 2025 rows carry the BA Grade. The measured break is a level shift of
roughly 11.4 FV at the 2025 to 2026 boundary. Spearman and AUC are rank statistics and are
invariant to a level shift WITHIN a year, but `accuracy.pooled` pools rows ACROSS years, so
a cross-era pool would be corrupted by it. This lane must state which of the two numbers it
is scoring and whether any scored pool straddles the break.

## 1. Measurement harness and its fidelity check

`data/timeseries.json` was exported at 2026-08-07 18:30, BEFORE the BA org boards were
ingested, and it carries zero BA rows with a non-null `fv_published`. So the lab cannot
read BA out of `source_backtest`'s own input. It OVERLAYS the BA rows from
`prospects.db` onto the universe by `player_key`, reproducing exactly what
`_rater_grades_for_year` will return after the next export.

An overlay is only as good as its fidelity. **CONTROL F (mandatory, run first).** With the
overlay switched OFF, the lab must reproduce the SHIPPED `data/source_backtest.json`
numbers exactly:

| quantity | shipped value |
|---|---|
| `accuracy.common_n` | 4259 |
| `pooled.fangraphs.spearman` | 0.2505 |
| `pooled.mlb_pipeline.spearman` | 0.2824 |
| `pooled.prospx_consensus.spearman` | 0.2849 |
| `pooled.fangraphs.auc` | 0.7007 |
| `pooled.mlb_pipeline.auc` | 0.7184 |
| `pooled.prospx_consensus.auc` | 0.7301 |
| `window.years` | 2017..2023 |

**STOP CLAUSE F.** If any of those eight fails to reproduce to the printed precision, the
harness is not measuring the shipped quantity and NO verdict in section 6 is reportable.
The lane returns BLOCKED and reports the discrepancy instead of a result.

## 2. Resolvability, counted in rows and not in constants

`MIN_LAG_YEARS = 3`, `CANDIDATE_YEARS = (2017 .. 2024)`, run year 2026. The lab computes,
per BA vintage, four numbers and reports all four:

- `rows_db`: rows in the snapshot with a non-null `fv`
- `rows_in_window`: of those, rows whose date falls in that base year's preseason window
- `rows_joined`: of those, rows whose `player_key` is present in the outcome universe
  (`timeseries.json` actives plus `debuts.json` graduates), i.e. rows that can carry an
  outcome at all
- `rows_resolvable`: `rows_joined` for base years satisfying `run_year - y >= MIN_LAG_YEARS`
  AND `y in CANDIDATE_YEARS`

The lab also reports the FIRST FUTURE YEAR at which each currently-unresolvable vintage
becomes scoreable, and whether `CANDIDATE_YEARS` would have to be extended for that to
take effect. A vintage that is blocked by a hardcoded tuple rather than by physics is a
finding in its own right.

## 3. The gates

Each gate is stated with its PASS clause. Marginal is FAIL (standing rule 12).

**GATE 1: RESOLVABILITY.** BA is eligible for `SCORED_SOURCES` only if it has at least one
resolvable preseason vintage with `rows_resolvable >= 100`.
PASS = at least one such vintage. FAIL = verdict (b) on resolvability grounds.

*Self-added threshold, declared under standing rule 8.* The 100-row floor is MINE; the
brief does not contain it. Justification: `_spearman` needs n >= 4 and `_archetype_accuracy`
uses `ARCH_MIN_N = 40`, so 100 is the smallest round number that leaves a pooled estimate
with any precision at all after the common-set intersection cuts it down. It is a floor on
ELIGIBILITY, not on the verdict; if it is the binding constraint I will say so in the
headline.

**GATE 2: COMMON-SET INTEGRITY.** Adding BA must not collapse the common set.
PASS = `common_n_with_BA >= 0.75 * common_n_without_BA`.
FAIL = verdict (b) on common-set grounds, which supersedes gate 1 either way.

*Self-added threshold, declared under standing rule 8.* The 25%-relative-loss bar is MINE.
Justification: a source that costs a quarter of the evaluation population buys its own bar
by deleting three quarters of everyone else's evidence. I expect this gate to be the
binding one and I am registering it before I know the number.

**GATE 3: NO SILENT RESTATEMENT.** Adding BA must not move the incumbent published
numbers by more than the third decimal place the site prints.
PASS = `|rho_after - rho_before| <= 0.02` and `|auc_after - auc_before| <= 0.02` for EACH of
fangraphs, mlb_pipeline, prospx_consensus.
FAIL = verdict (b), and the magnitude of the move is the headline.

*Self-added threshold, declared under standing rule 8.* The 0.02 bar is MINE. Justification:
the repo's own smallest measured MDE95 on a comparable pooled-Spearman delta is 0.0068
(`source_backtest.py` line 908, the consensus-weight A/B), and `XFV_HEADTOHEAD_MDE95` is
0.0352. 0.02 sits between them: a move larger than 0.02 is larger than one of the two
effects the site currently gates ship decisions on, so it cannot be called cosmetic.

**GATE 4: ERA PURITY.** No pooled BA statistic may mix rows graded on the BA Grade basis
with rows graded on the Adjusted Grade basis.
PASS = every scored BA base year sits on ONE basis. FAIL = the pooled statistic is not
reportable and only per-year numbers are.

**GATE 5: GRADE-NORM ABSORPTION (diagnostic, does not gate the verdict).** The brief asserts
that `grade_normalization` keys by (source, role, cycle-year) and should therefore absorb the
era break as a per-year offset. This must be CONFIRMED, not assumed, because
`_paired_dists` (line 121) POOLS a cell across all years when the cycle overlap is thinner
than `_MIN_N = 30`, and a pooled cell mixes eras by construction. The lab reports, per
(role, year), the BA-to-FanGraphs paired overlap n, the `pooled` flag, and the fitted
offset. Any BA cell with `pooled = True` is a defect report regardless of this lane's
verdict.

## 4. Controls that would embarrass me (standing rule 10)

- **CONTROL F**: overlay off must reproduce the shipped artifact. Section 1. If this fails
  nothing else is reportable.
- **CONTROL S (scale break)**: independently reproduce the brief's stated same-player
  consecutive-board deltas (2023>2024 mean -0.64, 2024>2025 -0.83, 2025>2026 -11.89) and the
  BA-minus-FanGraphs gaps (+6.57, +6.80, +6.38, -4.98) from the database. If my numbers
  disagree with the brief's, the brief's premise is what is wrong and I report that.
- **CONTROL C (coverage, not skill)**: BA is a quality-selected Top-30 population. If BA
  scores WELL on its own rows, that is expected from restriction of range in the WRONG
  direction and proves nothing; the only honest read is on the common set. The lab therefore
  reports BA's own-rows Spearman AND its common-set Spearman side by side, and if the
  own-rows number is the flattering one I say so.
- **CONTROL R (rank-only fallback)**: the pre-existing 2026-06-03 Top 100 carries `fv` NULL.
  Confirm those rows contribute nothing to any FV statistic, so a null-FV row cannot be
  silently read as FV 0.
- **CONTROL L (league selection)**: all 13 clubs are American League. The lab counts, for
  the scored population, the mean number of contributing sources per player split by the
  player's league, before and after BA. A consensus whose vote count depends on league is a
  reportable asymmetry even when this lane ends at (b).
- **CONTROL X (selection hazard)**: reproduce the brief's debut-rate lift for BA-covered
  rows against the shipped training matrices. The recorded precedent (a MiLB deep backfill
  that regressed ridge `debuted_km` 0.3854 to 0.3678 because coverage correlated with
  survival) means a selection-correlated coverage change reaches the model THROUGH the
  consensus, which is `_FEATURES_HIT[0]`. This lane does not add BA to the consensus, but it
  must state the exposure.

## 5. What ships either way

Regardless of verdict, `source_backtest.py` stops hardcoding the classification. The
replacement derives, from the universe it already loads:

- for every non-scored source seen in `per_source`, its resolvable preseason row count, its
  vintage list, and the first run year at which it would become scoreable;
- an `insufficient_history` entry that is an OBJECT carrying those numbers, not a bare
  string;
- a `scoreable_now` list computed from the same counts, so that promoting a source is a data
  event and not an edit.

The served `data/source_backtest.json` is NOT written by this lane. The lab writes
`data/ba_source_class_eval.json` under its own name.

## 6. RESULT (appended after the run)

Run `python tools/ba_source_class_lab.py`, artifact `data/ba_source_class_eval.json`,
run year 2026, universe export of 2026-08-08 01:05 local. Every number below reproduces
from that artifact.

**VERDICT: (b), and NOT for the reason the shipped string gives.** Baseball America HAS
resolvable history. It is kept out because admitting it would delete 93% of everyone else's
evidence and invert two published conclusions.

### 6.0.0 A disclosure that has to come first: the inputs moved mid-lane

The pipeline rewrote `data/timeseries.json` and `data/debuts.json` at 2026-08-08 01:05,
between this lane's first measurement pass and its last, while `data/source_backtest.json`
still dates from the 2026-08-07 17:59 export. The new export CARRIES the BA org boards, so
the second pass is no longer a simulation: BA is really in `per_source` and the numbers
below are measured, not overlaid.

Both passes are recorded and both reach the same verdict:

| quantity | pass 1, 17:59 export | pass 2, 01:05 export (reported) |
|---|---|---|
| common set without BA | 4,259 | 4,284 |
| common set with BA | 275 | 295 |
| retention | 0.0646 | 0.0689 |
| year-matched retention (2023) | 0.3468 | 0.3624 |
| BA resolvable rows, 2023 vintage | 329 | 332 |
| largest incumbent Spearman move | fangraphs +0.0613 | mlb_pipeline -0.0475 |
| `consensus_wins` flips | Spearman only | Spearman AND AUC |

The verdict is not sensitive to the vintage. The pass-2 numbers are the ones reported
because they are measured on the universe the code will actually run on.

### 6.0.1 CONTROL F: harness fidelity, split into two legs after the re-export

- **F1, against the SERVED artifact: FAIL, 7 of 8, and correctly diagnosed.** The lab reads
  `common_n` 4284 against the artifact's 4259 and all six pooled numbers differ in the
  fourth decimal. `reference_is_same_vintage` is False (served `2026-08-07T21:59:21Z`,
  export `2026-08-08T05:05:44Z`). The stop clause in section 1 exists to catch a broken
  harness; what it caught is a STALE REFERENCE. Firing the stop clause on that would be
  wrong, so the binding leg was moved to F2 rather than the criterion being loosened.
- **F2, against a LIVE recompute of `run_source_backtest` on the SAME inputs: PASS, 8 of 8.**
  `common_n` 4284 = 4284, years 2017 to 2023, fangraphs 0.2490 / 0.7013, mlb_pipeline
  0.2806 / 0.7189, prospx_consensus 0.2837 / 0.7308, every one identical. This leg cannot
  go stale and it is the one the results rest on.
- **CONTROL E, export equivalence (added after the re-export): AGREES EXACTLY.** Measuring
  BA from the database overlay and from the exported `per_source` gives the identical common
  set (295 = 295) and identical Spearman and AUC for all four raters. The overlay was the
  path the real code takes.

### 6.1 Resolvability, counted in rows

| snapshot | rows | with FV | in window | joined to universe | resolvable | lag | in CANDIDATE_YEARS | scoreable from |
|---|---|---|---|---|---|---|---|---|
| 2023-02-15 | 385 | 385 | yes | 332 | **332** | 3 | yes | 2026 (now) |
| 2024-02-15 | 383 | 383 | yes | 375 | 0 | 2 | yes | 2027 |
| 2025-02-15 | 384 | 384 | yes | 382 | 0 | 1 | **no** | 2028, tuple permitting |
| 2026-02-15 | 383 | 383 | yes | 378 | 0 | 0 | **no** | 2029, tuple permitting |
| 2026-06-03 | 100 | 0 | no | 0 | 0 | 0 | no | never (rank-only, midseason) |

**GATE 1 RESOLVABILITY: PASS.** One vintage, 332 resolvable rows against a 100-row floor.
The shipped `"insufficient_history"` claim about BA is FALSE as of this run year. My
self-added 100-row floor determined nothing: 332 clears it 3.3x, and the verdict is decided
by gates 2 and 3.

**Second finding, unprompted.** `CANDIDATE_YEARS = (2017 .. 2024)` blocks the 2025 and 2026
base years independently of lag. The 2024 vintage becomes scoreable in 2027 by both physics
and the tuple; 2025 and 2026 satisfy the lag in 2028 and 2029 and are still excluded until
someone edits the tuple. The same tuple blocks ESPN's and TJ Stats' 2026 preseason cohorts.
That is a second hardcoded constant that fails silently, and the derived classification now
reports it per source under `base_years_blocked_by_candidate_years`.

### 6.2 GATE 2 COMMON-SET INTEGRITY: FAIL, by an order of magnitude

| basis | without BA | with BA | retention |
|---|---|---|---|
| all resolved years, 2017 to 2023 | 4,284 | **295** | **0.0689** |
| year-matched to 2023 only | 814 | 295 | 0.3624 |

Per year with BA admitted: 2017 (315), 2018 (459), 2019 (603), 2020 (665), 2021 (691) and
2022 (737) all go to ZERO, because BA has no vintage before 2023 and the common set is an
intersection. Even charitably restricted to 2023, the only year BA can contribute to,
admitting it still costs 64% of the rows. Against the pre-registered 0.75 floor this fails
by roughly 11x on the real basis and by half on the charitable one.

### 6.3 GATE 3 NO SILENT RESTATEMENT: FAIL, 4 of 6 cells

| rater | Spearman before to after | delta | AUC before to after | delta |
|---|---|---|---|---|
| fangraphs | 0.2490 to 0.2818 | **+0.0328** | 0.7013 to 0.7248 | **+0.0235** |
| mlb_pipeline | 0.2806 to 0.2331 | **-0.0475** | 0.7189 to 0.7043 | -0.0146 |
| prospx_consensus | 0.2837 to 0.2719 | -0.0118 | 0.7308 to 0.7095 | **-0.0213** |

Multiplicity, per standing rule 9: 4 of 6 cells exceed the 0.02 bar. MLB Pipeline's Spearman
move is **7.0x** the 0.0068 MDE95 this module already uses to gate the consensus-weight A/B
(line ~908) and **1.35x** `XFV_HEADTOHEAD_MDE95` (0.0352). Not one grade changed.

**GATE 3b, the downstream claims. Both invert.**

1. The RATER ORDER flips. `prospx_consensus > mlb_pipeline > fangraphs` becomes
   `fangraphs > prospx_consensus > mlb_pipeline`. FanGraphs goes from last of three to
   first, MLB Pipeline from second to last.
2. `accuracy.consensus_vs_inputs` flips **True to False on BOTH metrics**: Spearman
   (consensus 0.2719 against best input 0.2818) and AUC (consensus 0.7095 against best input
   0.7248). That pair of booleans is the site's entire defence of blending sources at all,
   and admitting a fourth rater would negate it without any rater changing a grade.

This is the trap section 0.1 registered, and it is worse than "the bar moves": the
conclusion moves.

### 6.4 GATE 4 ERA PURITY: PASS, by accident of timing

Only base year 2023 is scoreable, so the scored BA pool is entirely BA Grade and no pooled
statistic straddles the Adjusted Grade break. The field scored is confirmed to be
`per_source.baseballamerica.fv_published`, which `consensus.py:889` sets to `s.fv`, the RAW
`snapshots.fv` column, before grade normalization. That is the BA Grade for 2023 to 2025 and
the Adjusted Grade for 2026, exactly as the brief states, and it is the number this lane
intends to score for 2023. **The gate passes only because 2024 is not yet resolvable.** In
run year 2029, when 2026 becomes scoreable, `accuracy.pooled` would pool one Adjusted-Grade
year with three BA-Grade years and the 11.4 FV level shift would corrupt the pooled rank
statistic. Registered here so it is not discovered then.

### 6.5 GATE 5 GRADE-NORM ABSORPTION: 7 of 8 cells absorb it, 1 does not

| role | year | cycle pairs | below `_MIN_N` | pooled across years | n used | offset |
|---|---|---|---|---|---|---|
| hitter | 2023 | 169 | no | no | 169 | +6.361 |
| **pitcher** | **2023** | **0** | **yes** | **YES** | **461** | **+1.920** |
| hitter | 2024 | 175 | no | no | 175 | +6.686 |
| pitcher | 2024 | 134 | no | no | 134 | +6.754 |
| hitter | 2025 | 166 | no | no | 166 | +7.470 |
| pitcher | 2025 | 159 | no | no | 159 | +5.094 |
| hitter | 2026 | 171 | no | no | 171 | -5.175 |
| pitcher | 2026 | 168 | no | no | 168 | -4.940 |

The brief's assumption is CONFIRMED for the seven per-cycle cells: the offsets are fitted
per year and the sign flips cleanly at 2026, so the 11.4 FV era break is absorbed as a
level shift, as designed. It is FALSIFIED for one cell, and the reason is an INGEST defect,
not a normalization defect.

**CONTROL P, the root cause.** The `2023-02-15` board stored `position` as NULL on 363 of
385 rows; the other 22 carry the token `CP`, which is not a position code and which on
inspection is every catcher on the board (O'Hoppe, Quero, Yainer Diaz, Korey Lee,
Soderstrom, Susac, Bo Naylor, Lavastida). Neither NULL nor `CP` is in
`grade_normalization._PITCHER_TOKENS`, so **all 385 rows of the 2023 board are classified
role = hitter**. Cross-checked against the position the same players carry on their
FanGraphs and MLB Pipeline snapshots for 2023, 152 of 350 checkable rows are mis-roled: a
**43.4% role error rate** on that one vintage, against 0.29%, 0.28% and 0.00% for 2024,
2025 and 2026, whose position columns are fully populated with real tokens.

Two consequences, one live and one armed:

- LIVE: BA 2023 arms are normalized on the hitter-cell offset of +6.361 instead of their own
  within-2023 offset of +6.955, an error of 0.594 FV on 152 rows. Small, and small BY LUCK:
  the two 2023 offsets happen to be close.
- ARMED: because no 2023 BA row is ever classified pitcher, the `(baseballamerica, pitcher,
  2023)` cell has zero cycle pairs, falls through `_paired_dists`' `len(pairs) < _MIN_N`
  branch at line 121, and pools 461 pairs drawn from 2024 + 2025 + **2026**. That pooled
  offset is +1.920 because the Adjusted-Grade year drags it down, against a true within-2023
  pitcher offset of +6.955. The cell is inert only because nothing routes to it. Any fix
  that gives the 2023 board real positions, WITHOUT also fixing the pooling, would activate
  a **5.035 FV** under-correction on BA's 2023 arms.

So "keying by cycle-year absorbs the break" is true of the fitted offsets and false of the
FALLBACK. The fallback pools across eras by construction, and `_MIN_N` decides when it
fires. This is a defect report against `grade_normalization._paired_dists` and against the
2023 board's ingest, neither of which this lane owns.

### 6.6 CONTROL C, coverage not skill: cuts AGAINST the flattering read, reported anyway

BA's own-rows numbers are Spearman 0.2173, AUC 0.6239, n 331, debut rate 69.8%. Its
common-set numbers are Spearman 0.2261, AUC 0.6231, n 295. The own-rows Spearman is LOWER
and the own-rows AUC is higher by 0.0008, which is nothing. Restriction of range did not
flatter BA and I cannot claim it did.

What the common set does show is that on identical players BA is the WEAKEST of the four
raters on both metrics (0.2261 / 0.6231 against consensus 0.2719 / 0.7095, FanGraphs
0.2818 / 0.7248, MLB Pipeline 0.2331 / 0.7043). That is a real result and it points the same
way as gate 2, but it is not WHY the verdict is (b): gates 2 and 3 would fail identically if
BA had been the strongest rater on the board.

### 6.7 CONTROL S, the brief's scale-break premise: CONFIRMED

Same-player consecutive boards, reproduced independently from the database:

| pair | n | mean | sd | brief |
|---|---|---|---|---|
| 2023 to 2024 | 194 | -0.64 | 4.49 | -0.64 |
| 2024 to 2025 | 198 | -0.83 | 4.56 | -0.83 |
| 2025 to 2026 | 196 | **-11.89** | 5.66 | -11.89 |

BA minus contemporaneous FanGraphs: 2023 n 302 +6.61, 2024 n 310 +6.73, 2025 n 326 +6.32,
2026 n 339 **-5.06**. The brief quoted +6.57 / +6.80 / +6.38 / -4.98 on identical n. The
means differ by at most 0.08 FV, which is a difference in which FanGraphs snapshot counts as
contemporaneous, not a disagreement. The premise stands.

### 6.8 CONTROL R, rank-only rows: CONFIRMED CLEAN

100 BA rows carry `fv` NULL, all on `2026-06-03`. They are dropped before any FV statistic
and none can be read as an FV of zero. The shipped derived classification records them under
`out_of_window_rows_by_year` and `rank_only_rows_by_base_year`, so a rank-only or
midseason-only source is classified as such instead of disappearing from the list.

### 6.9 CONTROL L, league selection: the asymmetry is already live

BA's org boards cover 13 clubs: ATH, BAL, BOS, CHW, CLE, DET, HOU, KCR, LAA, MIN, NYY, TBR,
TOR. That is 13 of the 15 American League clubs (SEA and TEX absent) and 0 of 15 National
League clubs. Of the 1,707 players carrying a graded 2026 point, 730 are in a BA-covered org
and 977 are not, and **507 already carry a BA vote in the exported consensus**.

| basis | BA-covered orgs | other orgs | asymmetry |
|---|---|---|---|
| excluding BA's own vote | 1.875 mean sources (median 2) | 1.895 (median 2) | **-0.020** |
| as currently exported | 2.489 mean sources (median 3) | 1.955 (median 2) | **+0.534** |

Without BA the two groups are indistinguishable. With BA the covered group carries **+0.534
more voting sources, as a pure function of the player's league**. This is not a hypothetical
this lane is proposing: the 01:05 export already serves it. Every consensus quantity that
varies with how many sources voted (the mean itself, and `n_sources`, `fv_spread`,
`fv_stddev`, all three of which are eFV matrix feature columns) now has an AL/NL step in it.
This lane owns none of that machinery and changes none of it. The number is recorded so the
decision is made with it in hand, and it is the strongest argument in this document for
looking at what the BA ingest did to the CONSENSUS, which is a separate lane from this one.

### 6.10 CONTROL X, selection hazard: reproduced

| matrix | pool debuted | BA-covered debuted | lift |
|---|---|---|---|
| hitter | 845/1917 = 44.08% | 108/145 = 74.48% | **+30.4 pts** |
| pitcher | 981/2040 = 48.09% | 104/127 = 81.89% | **+33.8 pts** |

The brief's +30.7 / +34.6 reproduce (small n differences, 145/127 against the brief's
139/121, from which BA vintages count as coverage). Coverage correlates with the outcome by
roughly 30 points either way. Since `consensus_fv_raw` is `_FEATURES_HIT[0]` and
`_FEATURES_PIT[0]` AND the consensus leg of the blend AND the baseline eFV is scored
against, anything that puts BA into the consensus injects a selection-correlated change into
the model's dominant feature. The recorded precedent (MiLB deep backfill, ridge `debuted_km`
0.3854 to 0.3678) had exactly this shape, and its pre-registered revival condition is era
control OR symmetric bust-side coverage. An org Top 30 is bust-side-truncated by
construction, so BA cannot satisfy the second.

**This lane changes nothing about the consensus. But 6.9 establishes that the BA ingest
already put BA into it, so the exposure described here is live and unmeasured.** Measuring
it is out of this lane's scope and out of its file ownership; it is handed on as the single
highest-value follow-up.

### 6.11 What shipped

`source_backtest.py` no longer hardcodes the classification. `_all_source_grades_by_year`
counts every `per_source` key's preseason, rank-only and out-of-window coverage in one pass;
`classify_sources` derives the record from those counts plus the common-set overlap; and
`run_source_backtest` publishes it as `source_classification`, with `insufficient_history`
reduced to a projection of it (still a list of names, because `assets/glossary.js` renders
it with `.join(", ")`).

Verified live, from `run_source_backtest(write=False)` on the 01:05 export:

| source | blocked_by | preseason rows by base year | common-set retention | scoreable from | blocked by CANDIDATE_YEARS |
|---|---|---|---|---|---|
| baseballamerica | **`common_set_collapse`** | 2023: 331, 2024: 420, 2025: 470, 2026: 471 | 0.0689 | 2027 | 2025, 2026 |
| espn | `insufficient_history` | 2026: 113 | 0.0 | none yet | 2026 |
| just_baseball | `insufficient_history` | 2026: 26 (it publishes in-season: 111 out-of-window) | 0.0 | none yet | none |
| tjstats | `insufficient_history` | 2026: 110 | 0.0 | none yet | 2026 |

(The 2024 to 2026 row counts exceed the 383 to 384 rows those boards actually published
because the export forward-fills a source's last known grade onto later in-window snapshot
dates. That is the correct quantity here: it is exactly what `_rater_grades_for_year` would
read if BA were promoted. CONTROL E confirms it for the scored year: database overlay and
exported `per_source` give the identical 295-row common set.)

All four names from the old literal are preserved, each now with a measured reason instead
of a bare string, and BA's reason is the true one. The end-to-end run touches no file under
`data/`, and `common_n` and all six incumbent pooled numbers are byte-identical to a run of
the unmodified code on the same inputs (CONTROL F2).

BA is NOT added to `SCORED_SOURCES`. Promotion stays a deliberate edit because it restates
every published accuracy number and, on this evidence, would negate two of them. What the
code no longer does is assert the answer: when a source clears both conditions it sets
`scoreable_now` and logs a warning, so promotion becomes a data event someone is told about
rather than an assumption nobody revisits.
