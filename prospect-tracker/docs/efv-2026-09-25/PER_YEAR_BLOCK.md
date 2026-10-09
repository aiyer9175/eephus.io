# Pre-registration: the per-year vintage-matched block on Source Comparison

REGISTERED 2026-10-08, BEFORE any per-year number on the frame below exists. This document
is committed alone; the writer (`source_backtest.py`), the chart (`assets/glossary.js`
`_methPerYearChart`) and their tests land in a later commit. Where this document and the
later build disagree, this document governs and the build is fixed.

Owner answer M7-1 (2026-09-25, final-pass 'more' batch 7,
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`): pre-register a per-year vintage-matched block
with a floor per cohort, then draw every grader.

## 0. Honesty clause

Nothing was scored to write this document. No per-cohort count, Spearman, delta or floor
on the frame below was computed or read. The only numbers used are constants in committed
code (`source_backtest._CLAIM_BOOT_B`, `_CLAIM_SEED`, `_CLAIM_MIN_CLUSTERS`, `_Z95`) and the
pooled headline already served (`accuracy.head_to_head_verdict`, n 830 over the resolved
base years 2017 to 2023).

## 1. What changes, and why

The per-year chart on `/glossary/#view=source-comparison` reads `accuracy.per_year`: each
public board on its full common cohort per base year, with eFV left out because it covers
only part of each cohort (census X01-01, 2026-09-24). That frame mixes base years before
and after a player's debut, so it is not the headline frame, and eFV cannot be drawn on
it. This block replaces the chart's input with a frame on which every grader, eFV
included, is scored on identical rows.

## 2. The frame

1. **Rows.** Exactly the rows the pooled headline cell scores: the timing-pinned
   vintage-matched frame vm2 (owner answer FP3-1, batch 3; `source_backtest.VM2_BASIS`,
   `accuracy.pooled_efv_common_vintage_matched_vm2`). A row is an eFV-covered common-set
   row whose base year equals the player's debut year, with eFV's grade the timing-pinned
   out-of-sample score. No row is added and none is dropped: the cohort counts sum to the
   pooled n.
2. **Cohorts.** One cohort per debut year (which on this frame is also the base year).
   Each player appears in exactly one cohort.
3. **Years.** Whatever resolved years the run produces inside
   `source_backtest.CANDIDATE_YEARS`. The R-VM pin (no debut cohort 2025 or later,
   `efv_vintage_frame.reserved_vm_pins`) is not widened. The R-LV reserved frame is the
   list-vintage frame of `efv_vintage_frame`, a different population; this block reads
   only the rows the served pooled vm2 cell already scores.
4. **Graders.** Four, in this order: eFV (`xfv`), PROSPX consensus (`prospx_consensus`),
   MLB Pipeline (`mlb_pipeline`), FanGraphs (`fangraphs`). Every row of the frame carries
   all four grades by construction.
5. **Statistic.** Spearman rank correlation of each grade with the realized WAR on the
   cohort's rows, the same statistic and outcome as the pooled cell. No AUC is drawn.

## 3. The floor per cohort

1. **Minimum n: 40 rows.** The same 40-row cell floor the scoreboard matrix uses
   (`tools/efv_matrix.py`, lane D E3-Q4). A cohort with fewer than 40 rows is UNDER ITS
   FLOOR.
2. **Per-cohort MDE95.** For a cohort at or above 40 rows, the run derives, for eFV minus
   each of the other three graders, a paired player-clustered E_cond bootstrap of the
   Spearman delta with the module's own resampler (`_paired_delta_ci`): B 2000, seed
   `_CLAIM_SEED`, MDE95 = 1.645 x sd, minimum 30 clusters, the CI95 beside it. The floor
   is called with a 40-row minimum so every cohort that clears section 3.1 gets one.
3. A cohort at or above 40 rows whose floor cannot be derived (too few usable draws,
   numpy absent) is treated as UNDER ITS FLOOR.
4. A cohort under its floor still publishes its n and its four Spearman values, with
   `under_floor: true` and no MDE95.

## 4. The served key

`accuracy.per_year_vintage_matched` in the source backtest artifact:

- `frame_version` "vm2", `basis` equal to `VM2_BASIS`, `cohort` "debut year",
  `statistic` "spearman", `min_n` 40, `graders` (the four keys of section 2.4 in order),
  `floor_estimator` (the section 3.2 recipe in words), `registration` (this file's path).
- `cohorts`: one entry per debut year, keyed by the year as a string, each with `n`,
  `under_floor`, `spearman` (grader to value) and `floor_vs_efv` (grader to the E_cond
  block for eFV minus that grader; null when under the floor).
- `n_total`, equal to the pooled vm2 n.

The key is ADDITIVE. No other number in the artifact moves.

## 5. What the chart draws, and what it never draws

1. The chart reads `accuracy.per_year_vintage_matched` and nothing else: never
   `accuracy.per_year`, never the vm1, pre-debut or all-vintages frame, never a tilted
   frame. With the key absent, or fewer than two cohorts, the chart is not drawn; there
   is no fallback to another frame.
2. Every grader of section 2.4 is drawn per cohort, with no typed number: every value,
   n and floor on the chart is read from the key.
3. A cohort under its floor is drawn HOLLOW (open markers, no line segment into or out of
   it) and labelled under its year as under the floor, with its n.
4. Under each cohort at or above the floor the chart prints its n and the MDE95 of eFV
   minus the PROSPX consensus.
5. **No win count.** No caption, label or tooltip counts the cohorts any grader leads, and
   no per-cohort verdict word (beats, loses, best) is printed. The block describes; it
   adjudicates nothing. The headline verdict stays the pooled vm2 cell.

## 6. Tests (land with the build)

- The chart function references `per_year_vintage_matched` and does not reference
  `accuracy.per_year`, `per_year_scale_view`, or any other frame key.
- The chart function carries no statistic literal and no win-count wording.
- A cohort below `min_n` renders hollow and labelled; a cohort at or above it renders
  filled with its n and MDE95.
- The writer: cohort n sum to the pooled vm2 n; every cohort under 40 rows has
  `under_floor` true and null floors; the four graders are present on every cohort;
  no year is 2025 or later.

## 7. What this block does not do

It refits nothing, changes no gate constant, blend lambda, pinned weight or served grade,
and moves no pooled or headline number. It does not stratify by consensus FV
(`docs/PROSPECT_ANCHOR_GATE.md`): the only grouping is debut year.
