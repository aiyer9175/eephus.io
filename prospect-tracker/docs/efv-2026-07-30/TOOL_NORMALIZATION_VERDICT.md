# Lane D verdict: NO-SHIP the tool-grade normalization, and the real defect is underneath it

Owner ask 4 (accuracy-weight tool grades and ground them in outcomes). Measured
2026-07-31 BEFORE building anything, against the arm the master plan named PRIMARY:
correcting MLB Pipeline's measured hot bias onto the FanGraphs frame inside
`consensus.py`'s currently-unweighted per-tool mean.

## VERDICT: NO-SHIP, on two independent grounds

Either one alone would be sufficient.

## 1. The blast radius is not there

Live board, from `tools.publishing_sources` on each active player:

| cohort | n | share |
|---|---|---|
| graded by BOTH outlets | 1,043 | 57.8% |
| **Pipeline-only (the only players an offset moves)** | **188** | **10.4%** |
| FanGraphs-only | 575 | 31.8% |

And that 188 is deep-tier org filler: **one player inside the top 100**, median overall
rank **2,772**, max eFV quantile 43.7 against a board max of 60.1, and **$23.2M of total
surplus against a board total of $33,724M, which is 0.07%.** On a single-source player
the correction also collapses to a constant after `consensus.py`'s 0.5-grade rounding, so
it is a fixed nudge to a fixed set of low-leverage players.

## 2. The offsets do not replicate, which is the decisive one

`data/tool_grade_tables.json` INV-2 measured the FanGraphs-minus-Pipeline gap on a
historical pre-debut pool. Re-running the identical paired measurement on the **1,043
live players both outlets grade** does not reproduce it:

| tool | INV-2 said | live says | agree? |
|---|---|---|---|
| hit | -2.54 | **-4.48** | no, each outside the other's CI |
| fb | -3.35 | **-1.99** | no, each outside the other's CI |

It is also **not flat across the grade scale** (hit -4.03 at FV<=40 against -6.36 at
FV>=50; game_pwr flips sign at FV>=50), and the MEDIAN gap is exactly zero on five of six
tools, meaning an additive mean offset mis-corrects the 33 to 40% of players where the two
outlets already agree.

Worse, the sign **flips** on the secondary pitches INV-2 never measured: sl +0.83,
ch +1.27, cb +1.61. FanGraphs runs hot on breaking and offspeed while Pipeline runs hot on
the fastball. Correcting `fb` alone would break a cancellation that currently protects
`composite_stuff` for the 1,043 both-graded players.

**Fixing 76 Pipeline-only arms by degrading 1,043 both-graded ones is a bad trade.**

## 3. The finding worth keeping: the outlets publish DISJOINT tool sets

This is bigger than the offset question and no additive correction touches it.

| tool | FanGraphs | Pipeline |
|---|---|---|
| raw_pwr | 844 | **0** |
| bat_ctrl | 819 | **0** |
| pitch_sel | 754 | **0** |
| throw | 0 | **present** |

So `storage._compute_tool_composites` is taking power-means over **structurally
different input sets**: a mean of 8.18 tool keys for both-graded players, 6.78 for
FanGraphs-only, 4.70 for Pipeline-only. Two players' Tools+ numbers are not built from
the same quantities, and that affects the entire 1,806-player tool board rather than the
188. A per-tool offset cannot address a missing tool.

That is the defect worth a lane, if any of this gets one. It is a composition problem,
not a calibration problem.

## 4. And it would be a model change, not a display patch

About **23% of the eFV label pool is Pipeline-only** (pre-debut source mix on
`debuts.json`: both 1,401, Pipeline-only 518, FanGraphs-only 218). `tools_consensus`
feeds `efv_dataset`, so any normalization at the consensus layer requires a matrix
rebuild and the full eFV gate. The training pool is considerably more exposed than the
live board, which is the opposite of what a low-blast-radius display fix looks like.

## 5. What this leaves of ask 4

The ask was to accuracy-weight tool grades and ground them in outcomes. The measured
answer, across this lane and the Lane A arm work on the same day:

- **Per-source accuracy weighting**: already twice refuted at the FV level (board-side
  and draft-side both shipped equal weights after measuring gains inside the noise), and
  now refuted at the tool level for a different reason, non-replication.
- **Per-source normalization**: refuted here.
- **Grounding tool grades in measurement**: this one is real and already shipped as
  `data/tool_grade_tables.json`, 47 grade-to-measurement tables. What it lacked was an
  arm and a throw table, because nothing in the tree measured them. **That gap closed
  today**: `savant_arm_strength.py` landed the same day, so a scouted throw grade can now
  be audited against radar for the first time. That is the honest, buildable remainder of
  ask 4, and it is a measurement table, not a weight.

## 6. Corrections to the record

- `consensus.py:17`'s docstring still cites the reverted 0.939/1.061 FV weights. Stale.
- Two of the four TBS tool legs named in the plan are **dead lookups** that no code path
  populates. Anyone budgeting blast radius from that list would overcount.
