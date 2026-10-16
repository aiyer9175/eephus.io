# Baseball America's grade inside PROSPX consensus (BA_GRADE_IN_CONSENSUS): raw, risk-adjusted or excluded, fixed before any number

Registration status: REGISTERED

Written 2026-10-16 (task BA_GRADE_IN_CONSENSUS) under the owner's decision EW3-36 of 2026-10-16
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`): "BA grade INVESTIGATE (BA_GRADE_IN_CONSENSUS: stored
BA is risk-adjusted and feeds consensus; measure raw vs adjusted vs excluded, owner decides)". The
finding it answers is PEER-5 of the pitcher eFV audit of 2026-10-16: the stored Baseball America
grade of a 2026 board is BA's risk-adjusted grade (raw minus 0 to 20), it votes inside PROSPX
consensus, and on the live pitcher board it correlates 0.135 with FanGraphs where BA's raw grade
correlates 0.578 (example: dylan_jordan, BA 40 stored, raw 50).

This document is committed ALONE, before the lab `tools/ba_grade_consensus_lab.py` exists and
before any number of this read is computed. Sections 1 to 9 are written before the read; the run
appends section 10 (the numbers) and section 11 (the reading). No em-dashes. Nothing here, in its
code or in its artifacts, is cut by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, binding): the
only groups are frame, side and year (list year or debut year), and the board summary is by side.
Only the development frames are read (lv_dev list vintages 2017 to 2019, vm_dev debut cohorts
2017 to 2023); no reserved row (R-LV list vintages 2020 and 2021, R-VM debut cohorts 2025 and
later) is built, scored or given a consensus value, and `backtest.run_backtest` is never called.
Nothing served changes in this task: no exporter runs, no flag moves, no artifact under data/ at
depth one is written.

## 0. Preconditions and outcome-blind facts (checked before this document was written)

- The stored BA grade, counted off `prospects.db` (`snapshots`, source `baseballamerica`), against
  the raw grade and risk kept in `tools_json._extras` (`ba_raw_grade`, `ba_risk`):
  - 2023-02-15 (874 rows), 2024-02-15 (844), 2025-02-15 (871): stored = raw on every row. Risk is
    published on every row on BA's older ladder (Low, Medium, High, Very High, Extreme; 2023
    counts 2 / 120 / 475 / 47 / 230).
  - 2026-02-15 (883), 2026-08-05 Top 100 (100), 2026-08-10 midseason (884): stored = raw minus
    the penalty of BA's 2026 ladder (Low 0, Mild 5, Average 10, High 15, Extreme 20) on every
    row. 2026-06-03 (100 rows) is rank-only (no grade).
- Outcome-blind reach census (the scored rows of the development frames as
  `efv_w2_anchor.build` makes them, counted by whether the latest consensus point inside the
  row's preseason window carries a BA grade): BA reaches 137 scored rows, all in vm_dev debut
  year 2023 (hitters 69 of 76, pitchers 68 of 90). It reaches no lv_dev row and no vm_dev row of
  2017 to 2022, because BA's first board in the database is 2023-02-15.
- Consequence, stated before the read: on every development row BA can reach, the stored grade
  IS the raw grade. BA published no adjusted grade before 2026, and the 2026 vintages carry no
  outcome label (their windows are open), so BA's published adjusted grade cannot be read
  against outcomes on any development frame. The adjusted arm below is therefore a registered
  PROXY: BA's raw 2023 grade minus a penalty from a crosswalk of the older risk ladder (section
  3). The board effect of the published 2026 adjusted grade is measured outcome-free (section 6).
- A full consensus rebuild (`storage.load_all_snapshots` then `consensus.build_timeseries` with
  `normalize=consensus.ADOPT_NORMALIZED_CONSENSUS`) takes about 10 s, so a null comparator of
  100 rebuilds per family is affordable.

## 1. How BA enters PROSPX consensus today, and under which rule

1. Ingest (`baseballamerica_csv.py`). `fv_basis(season)` returns "adjusted" for seasons from
   `ADJUSTED_GRADE_FIRST_SEASON` = 2026 and "raw" before, and the row's `fv` takes that field
   (`fv = adjusted if basis == "adjusted" else raw_grade`). The module docstring records the
   owner instruction this follows: "`fv` takes the Adjusted Grade, never the raw grade." The raw
   grade and the risk label are stored in `_extras` in both eras so the choice stays reversible.
2. Vote (`consensus.py`). BA is an explicit-FV source: 4,456 of its 4,556 rows carry an FV, so it
   is averaged into `consensus_fv_raw` like FanGraphs and MLB Pipeline (equal weight; the shipped
   `data/source_weights.json` carries no weights), forward-filled per source, with the
   single-instance FV 35 pull. It is not rank-only.
3. Scale (`grade_normalization.build_remapper`, adopted with `ADOPT_NORMALIZED_CONSENSUS` True and
   `GRADE_NORM_AS_OF` True). Before averaging, each BA grade is shifted by the mean gap between BA
   and FanGraphs on the players both graded in that (role, cycle year), capped as of the newest
   year in the pool. The cell is per cycle year, so the 2026 level drop of the adjusted grade
   (about 11.7 FV) is absorbed as a level; what the shift cannot absorb is the per-player risk
   penalty, which re-orders BA's 2026 vote by risk (`test_ba_era_basis.py` pins the two-era
   basis).
4. Scoring (`source_backtest.py`). `SCORED_SOURCES` = ("fangraphs", "mlb_pipeline"): BA is NOT a
   scored rater, by the rule of 2026-08-07b and `docs/efv-2026-08-07b/BA_SOURCE_CLASS_GATE.md`
   (admitting it collapses the common set to the one year BA covers). That rule is about the
   rater list. It does not keep BA out of consensus: BA votes inside `prospx_consensus`, which is
   scored. The memory line "BA restored" (2026-08-09) records the data purge and re-ingest of BA's
   boards (4,597 rows), not a rule change. Both statements hold at once.

## 2. What is compared

Four consensus arms, each a full rebuild of the consensus time series through the served code
(`storage.load_all_snapshots`, `consensus.build_timeseries(normalize=ADOPT_NORMALIZED_CONSENSUS)`)
with ONLY Baseball America's grade changed, in the snapshot corpus AND in the normalizer's paired
table (`grade_normalization._all_latest`, re-derived from the same database rows with the arm's
BA value; with the identity transform it must equal the served table exactly, P1 below):

| arm | BA's grade on each row |
|---|---|
| S (served) | the stored `fv` (raw before 2026, adjusted from 2026) |
| R (raw) | `ba_raw_grade` in every season |
| A (risk-adjusted, primary crosswalk) | `ba_raw_grade` minus the penalty of section 3 in every season; equals S on every 2026 row |
| X (excluded) | every `baseballamerica` snapshot removed (all dates, the rank-only list included) |

Sensitivity arm A2: as A with the name crosswalk of section 3. The source
`baseballamerica_statcast_by_age` (41 rows, no FV) is not BA's grade and stays in every arm.
A row with no raw grade (the rank-only list) keeps `fv` None in S, R, A and A2.

On every development row S equals R exactly (section 0); the run asserts it (P4).

## 3. The risk crosswalk for the older ladder (the proxy)

BA's 2026 ladder and penalty are published and verified (Low 0, Mild 5, Average 10, High 15,
Extreme 20; 1,867 of 1,867 graded 2026 rows obey raw minus penalty). The 2023 to 2025 ladder has
no published penalty. Two crosswalks are fixed here:

- A (primary, by position on the five-rung ladder): Low 0, Medium 5, High 10, Very High 15,
  Extreme 20.
- A2 (sensitivity, by label): Low 0, Medium 10, High 15, Very High 17.5, Extreme 20.

Neither is BA's. The read of A and A2 is a read of "BA's own risk label as a penalty on BA's raw
grade", not of BA's published adjusted grade.

## 4. The development frames, the outcome, the statistic

- Rows: the scored rows of lv_dev and vm_dev exactly as `efv_w2_anchor.build` makes them (the
  C03 frames every eFV development read uses), with their outcome (`outcome.war`, the frozen
  fWAR label; the run refuses unless `efv_labels.provider()` is "fwar" and records the label id)
  and contributor flag. Only each row's `prospx_consensus` value is replaced, by the arm's
  consensus: the `consensus_fv_raw` of the latest point inside the row's window, read by the same
  rule the frames use (`source_backtest._rater_grades_for_year` on the vm_dev debut year; the
  list-vintage window for lv_dev, which no arm can change, P3).
- Statistic: within (side, year) Spearman against the outcome, size-weighted over groups of 20
  or more rows (`efv_v2_stat`), with the paired, player-clustered E_cond CI95
  (`efv_v2_stat.paired_delta`, B 2000, seed 20260906). Groups are `frame|side|year`.
- PRIMARY SCOPE: the groups in which BA can move any row, vm_dev hitters 2023 (76 rows) and vm_dev
  pitchers 2023 (90 rows), 166 rows. Every row of those groups is used (a within rank needs the
  whole group); the rows BA does not reach carry the same consensus in every arm.
- CONTEXT SCOPE: all scored rows of both frames (the same deltas, diluted by the rows no arm can
  move). Reported, not adjudicated. Per side (hitters, pitchers) is reported, not adjudicated.
- Secondary statistics on the primary scope: pooled Spearman and contributor AUC after the
  identical output map. Reported, not adjudicated.

## 5. The comparisons, the null comparators and the planted recovery

Comparisons on the primary scope:

- C1 = R minus X: does BA's raw vote (BA as consensus has always read it before 2026) improve
  consensus?
- C2 = A minus X: does BA's risk-adjusted vote improve consensus?
- C3 = A minus R: the owner's question, risk-adjusted against raw.
- C4 = A2 minus R: sensitivity of C3 to the crosswalk. Reported, not adjudicated.

Null comparators (K = 100 rebuilds each, permutation seed 20261016):

- N1, a no-information BA vote: the raw grades of BA's 2023 board rows permuted among those rows
  within role (role by `grade_normalization._is_pitcher`). Same coverage, same marginal, no
  information. The null of C1 and C2 is the distribution of N1_k minus X.
- N2, a no-information risk penalty: the crosswalk-A penalties of BA's 2023 rows permuted among
  those rows within role and subtracted from the raw grade. The null of C3 is the distribution of
  N2_k minus R.

Planted recovery (the instrument must see a BA effect it is built to see):

- PL1 (informative BA): for the BA 2023 rows of the players BA reaches on the primary scope, within
  each side, BA's grade is replaced by the same players' own raw grades re-assigned in order of
  their outcome (highest outcome gets the highest grade; ties by player key); all other BA rows
  keep their raw grade. PASSES when PL1 minus X has CI95 above zero and exceeds the 95th
  percentile of the N1 null.
- PL2 (informative penalty): for the same rows, the same players' crosswalk-A penalties
  re-assigned so the lowest outcome carries the largest penalty, subtracted from the raw grade.
  PASSES when PL2 minus R has CI95 above zero and exceeds the 97.5th percentile of |N2_k minus R|.

## 6. The board effect (outcome-free)

On the served eFV board (`data/xfv.json`, every row by side), each arm's latest
`consensus_fv_raw` against arm S: rows whose latest point carries BA, mean and SD of the change,
mean absolute change, largest move, and the count moving 1 FV or more, by side; dylan_jordan as
the worked example. Also, on the live 2026 BA rows, the correlation of BA's stored and raw grade
with FanGraphs and MLB Pipeline by role (restating PEER-5 over the whole board). No outcome is
read for this section, and nothing is grouped by FV level. eFV is not recomputed; it re-ranks on
consensus, so a consensus change would reach it at the next rebuild.

## 7. Parity checks (the run refuses if P1, P3 or P4 fails)

- P1: the re-derived normalizer table with the identity transform equals
  `grade_normalization._all_latest()` exactly.
- P2: arm S reproduces the frames' stored `prospx_consensus` on the scored rows (share equal
  within 1e-9, largest difference) and the committed consensus within reads (0.1792 lv_dev,
  0.3814 vm_dev, `docs/efv-v2/EFV_V5_REFIT_RESULTS.md`). Reported; the read compares arms of ONE
  rebuild, so a stale artifact cannot enter a delta.
- P3: every consensus point dated before 2023-02-15 is identical in every arm.
- P4: arm R equals arm S on every development row.

### 7a. Amendment to P3, before the read (2026-10-16)

The first `--check` run (parity only; no outcome had been read, no statistic computed) refused at
P3: arm X moves 2 points dated before 2023-02-15, both of one player, `zack_britton` (2011-01-22
and 2011-04-01, consensus None in S, 55.0 in X). The cause is the same-name collision prune in
`consensus.build_timeseries` (`_prune_collision_cluster` keeps only the most recent grading
cluster of a key): a 2023 Blue Jays BA row is filed under the veteran's key (it reads as a
different player, a Blue Jays prospect of the same name), so in S the 2011 cluster is pruned, and
removing BA's rows in X restores it. He is in no development frame (debut 2011). P3 is
therefore operationalized as: no point dated before 2023-02-15 of any player with a scored
development row moves between arms (the run refuses otherwise), and every other moved point is
listed in the artifact. Nothing else in the registration changes. The identity collision is
reported to the owner as a finding outside this task's scope; it is not repaired here.

## 8. The reading rule

A comparison RESOLVES only when all three hold: its CI95 excludes zero; it lies outside its null
(C1, C2: one-sided p against N1 below 0.05 in the direction of the sign; C3: two-sided p against
N2 below 0.05); and its family's planted check passed (PL1 for C1 and C2, PL2 for C3). Otherwise
it is UNRESOLVED and the MDE95 says what size of effect the frame could have seen.

The owner decides (EW3-36). The default recommendation, fixed here:

- C3 resolves positive (adjusted better): KEEP the served basis (adjusted from 2026).
- C3 resolves negative (raw better): switch BA's `fv` to the raw grade from 2026 (one constant,
  `ADJUSTED_GRADE_FIRST_SEASON`, plus a re-ingest of the 2026 boards).
- C1 and C2 both resolve negative (BA's vote hurts consensus either way): EXCLUDE BA from
  consensus.
- Nothing resolves: KEEP the served basis. A change of the consensus basis without a resolved read
  would move served numbers on no evidence.

## 9. What this task writes

`tools/ba_grade_consensus_lab.py` and `test_ba_grade_consensus_lab.py` (fixture tests only,
committed before the read), the artifact `data/_labs/ba_grade/ba_grade_consensus_read.json`
(`data/_labs/` ships to no webroot), sections 10 and 11 of this document, and the owner question.
No served artifact, flag, constant, registry row or page changes.
