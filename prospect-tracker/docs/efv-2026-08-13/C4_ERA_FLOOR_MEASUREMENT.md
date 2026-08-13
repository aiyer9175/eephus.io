# C-4 era floor: measured, not yet implemented

Measured 2026-08-13 against the live DB. Owner decision 3 of the 2026-08-13
programme selected the era floor as the C-4 repair. This document records the
measurement that decision needs, BEFORE any code moves, because the flip itself
is a basis change on eFV's dominant feature.

## What is actually broken

`grade_normalization._paired_dists` falls back to pooling a thin cell across all
years for that (source, role). For a cell EARLIER than
`_REFERENCE_FIRST_YEAR = 2017` there are no own-year pairs at all, because
FanGraphs, the reference scale, has no row before 2017-02-15. So a pre-2017 grade
gets an offset estimated from pairs that are **entirely later than the grade being
normalized**: mlb_pipeline hitter 2013 is estimated off 3,982 pairs, every one of
them from 2017 through 2026.

The as-of cap shipped on 2026-08-09 deliberately EXEMPTS these cells, because a
strict cap would drop their offset altogether and move all 3,478 served units by
+3.89 to +3.91 FV. The exemption is correct and the leak it leaves is the open
piece.

## The repair

For a cell earlier than the reference's first year, pool only the EARLIEST year
the reference exists (2017) instead of every year. That is the closest available
era rather than the whole future, and it keeps an offset rather than dropping to
raw, so it avoids both the leak and the discontinuity.

## Measured effect

| source | role | today, all years | era floor, 2017 only | delta |
| --- | --- | --- | --- | --- |
| mlb_pipeline | hitter | +4.0457 (3,982 pairs) | +4.2880 (309 pairs) | **+0.2423** |
| mlb_pipeline | pitcher | +3.7429 (3,325 pairs) | +4.0603 (282 pairs) | **+0.3174** |

Both era-floor cells clear `_MIN_N = 30` comfortably, so the floor is well defined
exactly where it is needed.

Every other source is THIN at 2017 and cannot form an era-floor cell:
mlb_pipeline_international (0 pairs), baseballamerica (0), espn (0). That is not a
gap. The module docstring records that the 3,478 pre-2017 SERVED units are ALL
mlb_pipeline, because no other source grades players that early. The floor is
defined precisely where it serves and undefined precisely where it does not.

## Reading

The offset is applied as `fv - (mean_src - mean_ref)`, so a LARGER offset makes a
normalized grade LOWER. Pre-2017 mlb_pipeline grades would come out about 0.24 FV
(hitters) and 0.32 FV (pitchers) lower than today.

The direction is the one the era argument predicts. The FanGraphs-to-Pipeline
offset drifts DOWN over time, +4.175 in 2017 to +3.269 in 2026, a decline of about
7.7 sigma. Pooling all years therefore imports a decade of later drift into grades
published before any of it happened, and shrinks the offset relative to what a
2013 observer could have measured. The floor removes that import.

Magnitude is small, about a third of an FV, and it is small in a way that is
itself informative: the leak is real but it was never going to be worth a large
number, so nobody should expect this flip to move a margin.

## Why this is recorded rather than shipped in the same pass

The flip is NOT the one-line change it looks like. `consensus.py:206-224` lists
five OTHER call sites that build the remapper directly and would keep the uncapped
basis, and names `surplus_backtest_real.py:133` as the binding one: flipping the
flag alone puts the SERVED BOARD and the SURPLUS BACKTEST on two different
normalizations. `tools/consensus_gate_lab.py` additionally carries its own
re-implementation of the pooling that needs the same treatment.

A partial flip is worse than no flip, so the implementation wants a session that
can carry the whole checklist plus the matrix rebuild and the margin re-read that
must follow it. The expensive and uncertain half, whether the era floor is even
well defined and how large it is, is done and is above.

## What a shipping session has to do

1. Add the era floor inside `_paired_dists`: when the cell year is below
   `_REFERENCE_FIRST_YEAR`, bound the pooled years at `_REFERENCE_FIRST_YEAR`
   rather than at `as_of_year`.
2. Flip `consensus.GRADE_NORM_AS_OF = True` and thread the cutoff through all six
   construction sites in the same commit.
3. Rebuild the matrices. `consensus_fv_raw` is simultaneously eFV's dominant
   feature and eFV's baseline, so both move.
4. Re-read every margin the programme quotes BEFORE adjudicating anything, per
   the standing rule that a fresh delta is never read against a stored floor.
5. Expect the served effect to be small and report it as such. The pre-2017 rows
   are decision years 2011-2016 and `SCORED_YEARS` begins at 2014, so only the
   earliest folds carry affected test rows.
