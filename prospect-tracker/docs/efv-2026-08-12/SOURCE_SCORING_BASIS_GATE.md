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

## Results (2026-08-12, `data/source_backtest.json` -> `pairwise_head_to_head`)

**SHIPPED as an additional view. Baseball America is now scored, three years
before the old basis could have scored it, and nothing was taken from anyone.**

| pair | n | years | rho A | rho B | delta | CI95 | verdict |
| --- | ---: | --- | ---: | ---: | ---: | --- | --- |
| BA vs FanGraphs | 700 | 2023 | 0.1395 | 0.2401 | -0.1006 | [-0.1712, -0.0333] | **FanGraphs better, resolved** |
| BA vs Pipeline | 696 | 2023 | 0.1541 | 0.2264 | -0.0722 | [-0.1339, -0.0101] | **Pipeline better, resolved** |
| FanGraphs vs Pipeline | 4,299 | 2017-2023 | 0.2473 | 0.2810 | -0.0336 | [-0.0602, -0.0062] | regression control, no verdict |

**Baseball America orders outcomes materially worse than either incumbent on the
rows they share, and both comparisons resolve.** This agrees with the
independent label-free precision estimate, which has BA as the noisiest of the
three (sigma 4.80 against about 3.0), so two instruments that share no machinery
point the same way.

### Acceptance criteria

1. **Regression control PASSES exactly.** The incumbent cell returns FanGraphs
   0.2473 and Pipeline 0.2810 on n=4,299, which is byte-identical to
   `accuracy.pooled`. Pinned by a test and mutation-proved.
2. **No published verdict moved.** `SCORED_SOURCES` unchanged, and every key the
   site reads is asserted still present.
3. Cells whose interval spans zero read "not resolvable at this power".
4. Non-comparability is structural: cells are never combined into a ranking.
5. Same-year benchmark ships for every short-window pair.

### The tension this surfaced, and how it is resolved

The pre-registration's regression control did more than confirm the machinery:
it exposed that **`source_cohort_accuracy` publishes this same incumbent pair as
NOT RESOLVABLE** (n 1,520, d_rho -0.0293, CI [-0.0640, +0.0076]) while this
basis resolves it (n 4,299, delta -0.0336, CI [-0.0602, -0.0062]). The
difference is not the estimate, which agrees to about 0.004. It is the
POPULATION: 4,299 rows against 1,520.

Both are right on their own rows, and a reader handed two verdicts for one pair
has been handed a contradiction rather than a measurement. **So the incumbent
pair keeps its NUMBERS here, which is what makes it a regression control, and
hands its VERDICT back to the artifact that owns the source-versus-source
question.** Pinned by its own test.

### Honest limits

- **BA sits in exactly ONE resolvable base year (2023).** A single cohort cannot
  separate rater skill from that cohort's idiosyncrasy. This is not a
  formality: restricted to 2023 alone FanGraphs (0.2533) leads Pipeline (0.2137)
  while pooled over seven years Pipeline leads. **One year flips the incumbent
  ordering.** The same-year benchmark ships beside the BA cells for exactly this
  reason, and it reads "not resolvable at this power" on n=828, which is the
  honest yardstick for how much a single 2023 cohort can say.
- The BA result is therefore a ONE-COHORT read and must never be described as a
  track record. It gains a second year in 2027 and a third in 2028.
- This does not promote BA into `SCORED_SOURCES`. That remains a separate owner
  decision with its own restatement cost.
