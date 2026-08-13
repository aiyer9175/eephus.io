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

Measured 2026-08-13. Lab `tools/efv_headtohead_frame_lab.py 2000`, artifact
`data/xfv_headtohead_frame_eval.json`, B=2000, seed 20260808, cluster paired
bootstrap by player, all frames scored INSIDE THE SAME DRAWS.

### Every control passed

- **PARITY: exact.** The incumbent frame reproduced the published artifact
  bit-identically on all four raters at n=3,234 (xfv 0.3485, consensus 0.3193,
  fangraphs 0.2765, mlb_pipeline 0.3226, delta 0.0292).
- **ROW ACCOUNTING**: 3,234 rows to 2,684; 550 removed; 1,051 players to 1,006.
  Removed by base year: 2017:14, 2018:33, 2019:48, 2020:89, 2021:136, 2022:106,
  2023:124.
- **DIRECTION CONTROL: confirmed, and not marginally.** The consensus scores
  **0.4003** on the removed post-debut rows against **0.3012** on the retained
  ones. It orders far better precisely where it has already watched the player in
  the majors. eFV moves the other way (0.2889 removed vs 0.3637 retained), which
  is what a grade frozen at the decision date should do.
- The pre-registered direction was right: the strip **increased** the delta
  (+0.0313 to +0.0625, paired difference +0.0312 with CI95 [0.0180, 0.0457], so
  the two frames are themselves distinguishable) and **raised** the floor
  (0.0355 to 0.0372) as n fell.

### The headline result is NOT the one the strip alone produces

| frame | n | delta | MDE95 | margin | verdict |
| --- | --- | --- | --- | --- | --- |
| all base years | 3,234 | +0.0313 | 0.0355 | 0.881x | not resolvable |
| pre-debut only | 2,684 | **+0.0625** | 0.0372 | **1.679x** | would read "beats consensus" |
| base year == decision year | 802 | **+0.0040** | 0.0303 | **0.131x** | not resolvable |

Production `oos_grades` path reproduces the ordering on its own numbers:
+0.0292 / +0.0602 / **+0.0014**.

**THE PRE-DEBUT FRAME IS THE ONLY ONE THAT CLEARS A FLOOR AND IT IS NOT SHIPPED
AS THE HEADLINE.** The strip removes the rows where the CONSENSUS holds an
information edge and keeps the rows where eFV holds one: eFV carries a single
grade per player fitted at the decision year, so a base year EARLIER than that
compares eFV's later-vintage grade against a consensus read taken before it. The
frame is not symmetric, it is tilted the other way, and its margin is earned
partly by that tilt rather than by better ordering.

The vintage-matched cell is the symmetric contest, and it reads a dead tie. Its
floor is the **smallest of the three** (0.0303), because one row per player
removes the duplication that inflates variance under player resampling, so the
tie is measured MORE precisely than either alternative. "Not resolvable" here is
not a power excuse. This also independently reproduces the +0.00567 tie the gate
standard recorded for the latest-pre-debut frame, by a different route.

### What this changes on the page

On the vintage-matched basis the ordering is eFV 0.3937, **MLB Pipeline 0.3956**,
consensus 0.3923, FanGraphs 0.3482. eFV's lead over the best public source is
**-0.0019**, i.e. nominally behind, at a fraction of any floor.

The hero copy asserted "it ranks ahead of every public source" as fixed prose and
spliced in a lead behind a hard-coded "+". On this basis it would have rendered
"ahead of every one of them ... a +-0.002 point estimate": a false claim and
broken arithmetic in one sentence. Both the claim and the sign are now DERIVED,
with a third branch for the indistinguishable case. Hard-coded accuracy numbers
in copy are already banned; a hard-coded accuracy CLAIM is the same defect in
prose.

While fixing that, `_methHeroBanner` was about to reference an `hhv` binding that
did not exist in its scope, which is the same ReferenceError shape that blanked
this whole view once before and passed the suite because the view-walk test
accepted the empty state. Caught before it ran; declared at function scope.

### Verdict

**The corrected frame is adopted as a basis and REFUSED as a headline.** The
defect the strip fixes is real and the strip is kept: the receipts table and the
archetype table have stripped post-debut reads since 2026-07-15 and the pooled
head-to-head basis never did. But the published verdict is read off the
vintage-matched basis, and on equal information **eFV and the public consensus
are statistically indistinguishable**.

All three frames ship in `accuracy.head_to_head_by_frame`, each against its own
floor, so a reader can see that the frame decides the answer and by how much.

### Limits

- Floors here are the REFIT estimator. E_cond's floor for this statistic class is
  the smaller of the two (0.0322 against 0.0345, `EFV_GATE_STANDARD.md` 7.6), so
  no verdict above can flip toward LESS resolvable under it, but E_cond was not
  re-derived on these frames. Owed.
- The vintage-matched basis is defined as base year == debut year, which equals
  `efv_model._decision_year` for debuted players. Never-debuted busts have no
  debut year and are absent from this cell; the common set is close to fully
  debuted, so the effect is small but it is a population difference, not a
  reweighting of the same one.
- n=802 is the smallest of the three cells. Its floor is nonetheless the
  smallest, which is the point.
