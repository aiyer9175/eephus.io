# M-1 gate: the head-to-head frame carries post-debut consensus reads

Pre-registered 2026-08-13, BEFORE the corrected statistic was computed. Program:
`docs/master-plan-2026-08-13-efv-accuracy.md`, owner decision 5 (strip post-debut,
keep pooled). Committed with an empty Results section so git timestamps the
pre-registration.

## The defect

`source_backtest.py` publishes the site's head-to-head claim on
`accuracy.pooled_efv_common`, built at `:1236` as every rater re-scored on the
eFV-covered rows:

    efv_common = [c for c in pooled_common if c["grades"].get("xfv") is not None]

`pooled_common` carries one row per player per base year (2017-2023). The eFV side
of the contest is a SINGLE grade per player, anchored strictly pre-debut
(`xfv_oos` is keyed by player at `:1309`). So for any player who debuted inside the
window, the later base-year rows pair a frozen pre-debut eFV grade against a
consensus grade published AFTER that player reached the majors.

This exact defect was found and fixed in the receipts table on 2026-07-15. Its
rationale is already in the tree at `source_backtest.py:795-805`:

> PRE-DEBUT only (audit fix 2026-07-15): the eFV side of this contest is anchored
> strictly pre-debut (oos_grades at the debut-year decision), so the consensus read
> must be the same vintage. The old dedup took the latest read of ANY base year -
> consensus entered the contest with up to 2.5 years of the player's actual MLB
> results in hand (all 8 receipts were post-debut reads; Deivi Garcia's verdict
> was literally inverted). A base year EQUAL to the debut year is a preseason read
> and stays eligible.

`_xfv_vs_consensus_detail` applies that filter (`:803-805`) and
`_archetype_accuracy` applies it too (`:1291-1294`). **`pooled_efv_common`, the one
statistic the published claim rests on, never received it.** The fix is not a new
idea; it is an existing, reviewed principle applied to the statistic it was never
applied to.

## What is being changed, and what is deliberately NOT

CHANGED: rows whose base year is strictly greater than the player's debut year are
removed from the head-to-head basis. A base year EQUAL to the debut year is a
preseason read and stays eligible, matching the existing convention verbatim.

NOT CHANGED: the multi-vintage frame. A player keeps every eligible pre-debut base
year. Deduplication to one row per player is a SEPARATE operation with its own
measured verdict (`EFV_GATE_STANDARD.md:425-446`) and is not part of this gate.
`accuracy.pooled` (each rater on its own rows) is untouched: it exists for the
per-source coverage and calibration story, which legitimately wants full cohorts.

## Pre-registered expectation and its direction

**The correction is expected to INCREASE eFV's delta.** Post-debut reads let the
consensus see realized major league performance, which inflates the CONSENSUS leg
of the comparison; removing them removes an advantage held by the baseline, not by
eFV. At the same time the row count falls, and the floor scales with 1/sqrt(n), so
**MDE95 is expected to RISE**. Whether the corrected delta resolves is therefore
genuinely open in both directions and is not predictable from the sign of the
change alone.

This plan's own earlier draft asserted the opposite direction (that stripping would
reduce the margin). That was wrong and is corrected here before measurement rather
than after, which is the only reason it is worth writing down.

**This correction can only flatter eFV, and that is exactly why it is
pre-registered.** The safeguards against motivated reasoning are the parity check,
the direction control, and the stop clause below, not the plausibility of the
argument.

The three frames already measured are consistent with this mechanism and must not
be conflated. Pooled multi-vintage reads +0.033; latest-vintage one-row-per-player
is a resolvable LOSS at -0.049; latest PRE-debut one-row-per-player is a tie at
+0.006. The latest-vintage frame is the one where the consensus is MOST informed
(its single retained row is typically post-debut), and the pre-debut dedup frame
loses the early base years where the consensus is weakest. The strip and the dedup
move the number for different reasons and in different directions.

## Primary statistic

    delta = spearman(xfv) - spearman(prospx_consensus)

on the corrected `pooled_efv_common` basis: eFV-covered rows, post-debut reads
removed, multi-vintage retained, every rater re-scored on identical rows.

## Floor

Re-derived on the CORRECTED frame in the SAME run as the corrected delta, at the
same B and seed, cluster bootstrap BY PLAYER (never by row: rows are ~2-3 base
years per player, so row resampling would overstate the evidence). Both estimators
reported per the standing estimator policy; neither is selected after seeing which
is friendlier. `XFV_HEADTOHEAD_MDE95 = 0.0352` is the incumbent floor for the
UNCORRECTED frame and is not assumed to carry over.

## Decision rule

- RESOLVED WIN: delta > 0 and delta >= MDE95_corrected
- RESOLVED LOSS: delta < 0 and |delta| >= MDE95_corrected
- NOT RESOLVABLE: otherwise

A verdict is quoted only with the estimator that produced it. If the two estimators
disagree on resolvability, the claim is reported as UNRESOLVED and both are printed.

## Mandatory controls

1. **PARITY.** Before applying the strip, the harness must reproduce the CURRENT
   published numbers bit-identically (n 3234, xfv 0.3485, consensus 0.3193, delta
   0.0292 against `data/source_backtest.json` generated 2026-08-12T21:02:59Z). If
   parity fails, the harness is not the one that produced the artifact and the lane
   ABORTS rather than reporting a difference of unknown origin.
2. **DIRECTION / MECHANISM.** Score the REMOVED rows separately. The mechanism
   predicts the removed rows carry a HIGHER consensus Spearman than the retained
   rows. If they do not, the stated mechanism is wrong and the result must be
   re-examined before any copy changes.
3. **DECOMPOSITION.** Report strip-only, dedup-only, and strip+dedup as three
   separate cells so no reader can conflate this gate with the dedup question.
4. **ROW ACCOUNTING.** n before, n after, rows removed, distinct players before and
   after, and the removed-row count by base year. Publish all of it.
5. **NO OTHER RATER MOVES BY ACCIDENT.** FanGraphs and MLB Pipeline are re-scored on
   the same corrected rows; their deltas are reported so a reader can see the strip
   is a basis change for every rater, not a special case carved for eFV.

## Abort and stop clauses

- ABORT if the parity control fails.
- ABORT if the corrected basis falls below the module's own 40-row publication floor.
- **STOP CLAUSE, FRAME SHOPPING.** This gate registers exactly ONE corrected frame,
  fixed by owner decision before measurement. Its verdict stands whatever it is. If
  the corrected number is unfavourable it is published unfavourable; no third frame
  is introduced afterwards to improve it, and the incumbent uncorrected number is
  not retained as an alternative headline.

## What ships either way

The corrected basis and its floor ship, and every artifact-driven surface follows
the corrected number. The site copy is already conditional on resolvability, so a
NOT RESOLVABLE outcome needs no new hedging; a RESOLVED WIN would be the first time
the claim clears its floor and the copy may state that, naming the estimator, the
frame, and the fact that the frame was corrected in eFV's favour by removing a
baseline advantage.

## Results

(empty at pre-registration; filled by the lane)
