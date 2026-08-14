# C-6: the board-wide eFV deflation is a comparison defect, not a model defect

Pre-registered 2026-08-14 BEFORE any serve-path line was changed. Results section
deliberately empty at commit so git timestamps this.

Opened on the owner's report that "eFV is deflated across the board". Three lanes
before this one (C-1b five families, C-1c elite bands, C-1d two fitting frames) all
looked for the deflation inside the ESTIMATOR and all returned NO_SHIP or NULL. This
lane looked at what the deflation statistic is computed FROM.

## The defect, measured before any clause was written

Board-wide, on the 4,489 active rows of the 2026-08-14 rebuild, mean
`xfv_minus_consensus` is **-5.13 FV**. Attribution, by the nature of the row's
consensus anchor rather than by anything the model produced:

| cohort | n | share | mean consensus | mean eFV | mean delta | contribution to -5.13 |
| --- | --- | --- | --- | --- | --- | --- |
| anchor is a FABRICATED constant | 2,651 | 59.1% | 35.00 | 28.36 | -6.64 | **-3.92** |
| anchor is a PUBLISHED opinion | 1,838 | 40.9% | 38.85 | 35.89 | -2.96 | -1.21 |
| ... pinned at the FV20 abstention knot | 509 | 11.3% | 36.00 | 20.00 | **-16.00** | **-1.81** |
| ... where the map expresses a level | 1,329 | 29.6% | 39.94 | 41.97 | **+2.04** | +0.60 |

**76% of the deflation is a comparison against a number this codebase fabricates,
and a further 35% is a comparison against a sentinel.** On the rows where a real
opinion exists and the map can state a level, eFV reads ABOVE consensus.

### Cohort 1: the consensus is not an opinion

All 2,651 rows carry `consensus_fv` of exactly 35.0. That is
`CONSTANT_ANCHOR_SOURCES` (`consensus.py:1139`), the `performance_ingest` auto-track
stamp, which `compute_consensus_point` parks separately and folds back in only when
nothing real graded the player. The code's own words, `consensus.py:1262`:

    Park it. It is a placeholder constant, not an opinion; it only gets to vote if
    nothing real graded this player.

The constant is load-bearing and stays: it is the only thing standing between ~2,776
genuinely ungraded auto-tracked players and having no consensus point at all. What
is not defensible is publishing `eFV minus consensus = -6.64` against it, on 59% of
the board, as though the industry had graded these players and we disagreed.

This is the same defect class the codebase already fixed once, at
`consensus.py:1130-1131`: "a fabricated 35 was averaged into the consensus at
FanGraphs' weight, the same defect class as the fabricated BA-statcast FV-40 removed
on 2026-07-30". That fix stopped the fabrication ENTERING the consensus point. It
did not stop the delta being published against it.

### Cohort 2: the grade is not a level

`vf.outcome_implied_fv` returns `ks[0]` for every `war <= vs[0]`, i.e. exactly 20.0
for any non-positive prediction (`value_framework.py:2983-2984`). Measured on the
served board, the 509 rows pinned there carry corrected predictions spanning
**-0.86 to -0.00**: the map renders that entire interval as one number. So 20.0 is
the bottom of the scale, not an estimate of a level, and `-16.00` is not a measured
16-point disagreement.

The codebase already says this in the one place it acts on it. The routing scope
note, `test_board_basis_coherence.py:395-397`:

    at the floor   vf.outcome_implied_fv maps every non-positive prediction to the
                   curve's first knot, so at the floor the flagship map is ABSTAINING
                   rather than disagreeing.

Routing acts on that reading only when the anchor is ALSO constant-only. These 509
rows have a published anchor, so they fall through routing and serve the abstention
sentinel as if it were a grade.

### What this lane does NOT claim

It does not claim the low grades are wrong. Measured out of fold on the resolved
cohort, the rows whose corrected prediction lands in (-1, 0) realized a mean of
+0.122 WAR (hit) and +0.235 (pit), with **93.4% and 87.5% realizing 0 WAR or less**.
Feeding their REALIZED outcomes through the same map returns a mean grade of 21.66
and 22.92 against the 20.0 we serve. The grades are vindicated by outcomes. It is
the DELTA that is manufactured, not the grade.

## The change

Serve-path only, `run_live`. No coefficient, no curve, no feature, no fit, and no
re-rank. `xfv_grade`, `xfv_war_6yr`, `rank_war`, `p_bucket`, `p_bust`, `surplus_mm`
and every dollar figure are byte-identical after this change; only the published
DELTA and two new marker fields move.

1. `xfv_minus_consensus` is `None` where the anchor is constant-only, because there
   is no published opinion to differ from.
2. `xfv_minus_consensus` is `None` where the served grade sits exactly on the
   abstention knot, because the map has not stated a level.
3. Two markers are published so surfaces can render the reason rather than a blank:
   `consensus_is_placeholder` and `xfv_grade_is_floor`.
4. Every board-level aggregate over the delta (`realized_grade_divergence_vs_consensus`,
   `biggest_disagreements`) is computed over rows that HAVE a delta, and publishes
   its own `n` so a suppressed row cannot be mistaken for a zero.

## HARD clauses. All must hold.

1. **Dollar and probability byte-neutrality.** For every active row, `surplus_mm`,
   `consensus_surplus_mm`, `dist`, `band_p10_mm`, `band_p90_mm`, `p_bust`,
   `p_bucket`, `rank_war`, `xfv_war_6yr` and `xfv_grade` are unchanged to the
   published precision. Asserted row by row against the pre-change artifact, not
   argued from the call graph.
2. **No re-rank.** `board_sort_key` and the ordering it induces are unchanged for
   every row.
3. **Suppression is exactly the two declared cohorts.** The count of rows with a
   null delta equals the count of rows that are constant-anchor OR floor-pinned,
   with no third population appearing.
4. **The surviving delta is the honest one.** Mean `xfv_minus_consensus` over rows
   that still publish one must equal the +2.04 measured for the published-opinion,
   level-expressing cohort, within rounding.
5. **No surface renders a null delta as 0.0.** Every consumer of the field is
   enumerated and each either renders the marker or omits the row.

## Abort conditions

- ABORT if any clause 1 quantity moves. This lane is not permitted to move a dollar.
- ABORT if the suppressed count exceeds the two cohorts' union.
- ABORT if a consumer is found that cannot express "no comparison" and would render
  a null as a zero or as a missing player.

## If it ships

No epoch bump and no golden restamp on the grade basis: `board_basis_fingerprint`
names the things that set grades, and none of them moves. The artifact schema gains
two fields and one field gains a null, so any consumer pinned on the schema is part
of clause 5.

## Results

Measured 2026-08-14 against the pre-change artifact captured before the first edit.
Verification harness re-ran `python efv_score.py --live` on both sides and compared
row by row. **SHIPS. All five clauses hold.**

### Clause 1 and 2: nothing that carries a number moved

**94,269 frozen-field comparisons across 4,489 rows, 0 violations.** Compared per
row: `xfv_grade`, `xfv_grade_healthy`, `xfv_war_6yr`, `rank_war`, `p_bucket`,
`p_bust`, `surplus_mm`, `consensus_surplus_mm`, `dist`, `band_p10_mm`,
`band_p90_mm`, `consensus_fv`, `board_sort_key`, `xfv_grade_display`,
`xfv_grade_display_preside`, `factors`, `factors_more`, `statcast_factor`,
`injury_factor`, `position`, `kind`. Not one dollar, probability, grade or sort key
moved. The lane changed a claim, not a number.

### Clause 3: the suppression is exactly the two declared cohorts

    suppressed 3,160    placeholder 2,651    floor 784    union 3,160

Third population: **0**. The 275 difference between 2,651 + 784 and 3,160 is the
overlap, routed rows whose provisional grade happens to land on 20.0, and they are
correctly counted once.

### Clause 4: the surviving delta is the honest one

**n_compared 1,329, mean signed delta +2.03**, against the +2.04 measured for this
cohort before any code changed. Per side: hit 652 rows at +2.10, pit 677 at +1.97.

### The headline

| | before | after |
| --- | --- | --- |
| mean eFV minus consensus | **-5.13** over 4,489 rows | **+2.03** over the 1,329 rows that carry a comparison |

The board-wide deflation the owner reported does not survive the removal of
comparisons that were never comparisons. eFV reads slightly ABOVE the industry
wherever the industry published an opinion and the map could state a level.

### Clause 5, and the defect it caught

**This clause was the whole ship.** Enumerating consumers found that suppressing the
artifact field alone would have changed **nothing on screen**:

- `prospx/index.html` `efvMinusConsensus` carried an explicit fallback that
  subtracts `efvBoardValue(x) - x.consensus_fv` whenever the pre-baked field is
  absent. A null would have been recomputed into the identical number.
- `efvMinusConsensusDisplay`, which is the function that renders the CHIP the reader
  actually sees, **never read the pre-baked field at all**. It subtracts the two
  displayed integers directly.

So the artifact-only version of this change would have been a silent no-op on the
one surface the complaint came from. Both functions now consult
`efvComparisonSuppressed(x)` before their own computation, and `efv_export._entry`
carries the two markers through to `xfv.json`, without which the page cannot see
them. This is the same failure class as `C4_REACHABILITY_DEFECT.md`: a change that
is correct at its own seam and dead by the time it reaches the board.

Downstream rendering degrades correctly on the null: `efvDeltaText(null)` returns
the empty string and every call site is already guarded by `dtxt ? ... : ""`, so a
suppressed row shows no chip rather than a zero.

### A defect in the first shipped version of this lane, found and fixed the same run

The first `is_floor` read "served grade equals the outcome curve's first knot" and
that is TWO different statements, because **`efv_ungraded._GRADE_MAP["hit"]["FLOOR"]
is also 20.0**. A routed row can serve 20.0 as the provisional model's own resolved
answer at its floor, which is not an abstention by the outcome map at all. The first
version marked **784** rows, of which 259 were routed and were being told "not a
resolved level" about a map that had not produced their grade.

Scoped to `grade_from_outcome_map`, i.e. `_grade_basis == "outcome_pooled"`. Floor
marks go **784 to 525**, and the 525 are verified all-flagship and all exactly 20.0.

**It changed no delta**, which is the point: the 259 are constant-anchor by
construction (routing requires it), so they were already suppressed as placeholders.
Re-verified against the pre-refinement artifact, **71,824 frozen-field comparisons
with `xfv_minus_consensus` ITSELF included, 0 violations**. n_compared stays 1,329,
mean stays +2.03, suppressed union stays 3,160. Pinned by
`test_a_routed_grade_on_the_same_number_is_not_an_abstention`, which also asserts the
two constants still collide so the guard cannot be deleted as dead once they diverge.

### Marking, per the owner decision

The 509 floor rows now carry a dashed badge and read `at the scale floor, not a
resolved level`, and placeholder rows read `no source grade published` in place of a
fabricated `Consensus FV 35` reference line.

### Pins and mutation proof

`test_consensus_delta_honesty.py`, 13 tests, all green. Mutation-proved rather than
asserted: removing the guard from `efvMinusConsensusDisplay` alone fails
`test_prospx_does_not_re_manufacture_a_suppressed_delta`, and disabling the
placeholder branch of the predicate fails
`test_placeholder_consensus_publishes_no_delta`. Both restored, 13 green again. The
suite carries a non-vacuity pin first, because a predicate that suppressed
everything would satisfy every other pin in the file.

### Scope, stated so it is not overread

Serve path `run_live` only. The resolved-path `run()` report is untouched: it feeds
evaluation artifacts, whose frames are pre-registered elsewhere, and moving them
inside this lane would change what other gates are measured against.
`xfv_minus_consensus_display`, the retired quantile delta, is also untouched; it is
kept for back-compat reads and is not rendered.

**Not claimed: that the grades are too low.** The evidence points the other way and
is recorded above.
