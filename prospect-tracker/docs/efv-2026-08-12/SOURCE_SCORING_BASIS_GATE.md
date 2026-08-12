# D3: re-derive the source-scoring BASIS so a new rater does not cost 93% of the evidence

Pre-registered 2026-08-12, before the implementation existed. Committed alone so
git timestamps it. Owner instruction: re-examine this fence with fresh eyes.

## The fence, stated exactly

`source_backtest.SCORED_SOURCES = ("fangraphs", "mlb_pipeline")`. Baseball
America is kept out, and the reason in the code is measured rather than
asserted: `run_source_backtest` admits a player to the common set only when
EVERY scored rater graded him, so adding a rater does not add a bar to the
chart, **it redefines the population every other bar is computed on**. Admitting
BA takes the common set from 4,284 rows to 295, moves MLB Pipeline's pooled
Spearman by -0.0475 (7.0x the module's own MDE95), flips the rater ORDER, and
flips `accuracy.consensus_vs_inputs` on both metrics. The code says that keeping
BA out for THAT reason "is measured and does not expire".

It is right that it does not expire. That is exactly why the DESIGN, not the
membership, is what this lane re-derives.

## The crux, resolved before designing anything

The blocker could have been either of two things, and they have opposite
implications:

- **The maturation clock.** `MIN_LAG_YEARS = 3` means only base years <= 2023
  are resolvable in 2026. If BA's problem were the clock, no basis change buys
  anything and this lane is a null.
- **The global intersection.** If BA has enough resolvable history and is
  blocked only by the requirement that every scored rater cover every scored
  row, the design is the binding constraint and can be changed.

**Measured: it is the intersection.** BA carries **750 resolvable player-year
rows** (base year 2023), against `SOURCE_CLASS_MIN_ROWS = 100`. Its
`history_ok` is already TRUE and its `blocked_by` is already
`common_set_collapse`. Pairwise coverage on resolvable years:

| pair | rows |
| --- | ---: |
| fangraphs & mlb_pipeline | 4,402 |
| fangraphs & baseballamerica | 700 |
| mlb_pipeline & baseballamerica | 696 |
| three-way intersection | 666 |

So BA can be compared against either incumbent on ~700 rows **without removing a
single row from the 4,402 the incumbents are compared on**. The 93% cost is an
artifact of insisting on one global population, not a property of the evidence.

## What ships, and what explicitly does not

**SHIPS: a pairwise head-to-head block, as a LABELLED ADDITIONAL VIEW.** For
every pair of raters, on the rows BOTH cover: each rater's Spearman against
realized WAR, the difference, a player-clustered bootstrap interval, the years
covered, and a resolvable flag in the site's existing language.

**DOES NOT SHIP, and this is the no-laundering commitment:**

- `SCORED_SOURCES` is **unchanged**. Baseball America is not promoted.
- `consensus_wins`, `consensus_vs_inputs`, the pooled accuracy bars, the hero
  banner and every existing published verdict stay on the **old registered
  basis**, byte-identical.
- The new block is additive. If it disagrees with a published number, the
  published number does not move; the disagreement is disclosed.

## The control that makes a one-year comparison readable

BA is present in exactly ONE resolvable base year (2023) while the incumbents
span 2017-2023. A single cohort cannot separate rater skill from that cohort's
idiosyncrasy, and this is not hypothetical: **restricted to 2023 alone,
FanGraphs (0.2504) leads MLB Pipeline (0.2107), while pooled across all seven
years Pipeline leads.** One year flips that ordering.

So every pair scored on a subset of years must also publish the **benchmark pair
restricted to the same years**. Without it a reader cannot tell a rater
difference from a year difference, which is the cross-basis error this repo
fixed on the eFV hero banner three commits ago.

## Acceptance criteria, fixed now

1. **Regression control.** The incumbent FanGraphs-vs-Pipeline cell computed on
   the new pairwise basis must reproduce the existing served numbers on the same
   rows. If the new code cannot reproduce the old answer where the two bases
   coincide, it is wrong and nothing ships.
2. **No published verdict moves.** `data/source_backtest.json`'s existing keys
   are unchanged apart from the added block. Pinned by a test.
3. **Every cell carries its own n, its own year range and its own interval**, and
   a cell whose interval spans zero renders "not resolvable at this power" in
   the site's existing language rather than a winner.
4. **Non-comparability is structural, not a footnote.** Cells are never combined
   into a single ranking, and the block states that two cells on different rows
   are two different comparisons.
5. **Same-year benchmark** accompanies any pair not spanning the full window.

## What this lane may NOT conclude

- It may not promote Baseball America into `SCORED_SOURCES`. That remains an
  explicit, separate owner decision with its own restatement cost.
- It may not describe a one-cohort result as a track record.
- It does not re-open the consensus-weighting question. Weights stay `{}`.

## Results

To be written by the implementation. Deliberately empty at commit time.
