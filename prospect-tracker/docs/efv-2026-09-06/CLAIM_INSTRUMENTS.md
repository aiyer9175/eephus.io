# A-CLAIM-4: the bust-inclusive head-to-head frame

Registered 2026-09-06. The screens, the vintage rule and the pre-registered expectations
below were fixed before the frame was scored; the Results section was empty when they
were written and is filled in at the end.

## The defect this closes

`source_backtest._is_vintage_matched` requires `debut_year is not None`. A prospect who
never reached the major leagues therefore **cannot enter the flagship head-to-head frame**,
not because anybody filtered him out but because the frame is keyed on a debut he does not
have.

Every accuracy cell the artifact publishes is measured on players who all made it. That is
survivorship, and it is the most common way a forecasting claim flatters itself: the
players a grade got most wrong are exactly the ones who vanished. `data/inactive.json`
holds 2,346 of them and not one carries a debut date.

## What this lane is and is not

It is a **coverage receipt**. It adds a frame; it corrects nothing and it moves no
published cell. The blast-radius rule below is what keeps that true, and it is checked
rather than asserted.

## The screens, frozen

Two, and both fire on real rows.

**Real major-league value.** A player carrying career WAR is not a bust however he got into
the file. Exactly one qualifies: Zack Britton at 11.73 WAR over twelve seasons. Scoring him
as a never-debuted failure would be a plain lie about a player a reader may remember.

**Identity collision.** A bust whose `player_key` or MLBAM id already appears in the
debuted universe is the same human reached by two routes, and counting him on both sides
would let one player be his own control. Eight qualify, all by MLBAM id.

## The vintage rule, frozen

A bust is scored at his **last list year**: the latest year anybody still ranked him, which
is the last point at which the raters were all still making a claim about him. An earlier
year would ask what they thought before the evidence arrived. Every year would weight a
long-lingering prospect more heavily than a quick failure.

The outcome is zero WAR, and that is **measured rather than imputed**: the first screen
removed everybody who accumulated any.

## The pool is COMBINED, and the first build got this wrong

Scored on their own, every bust has the same outcome, so a rank correlation against it is
undefined and every bootstrap draw returns NaN. The first build did exactly this and the
floor reported "not derived: too few usable draws", which is correct and useless.

The question was never how a grade orders the failures among themselves. It is whether the
grade still orders outcomes **once the failures are in the pool**, and that needs both
halves.

Both halves are scored on **raw out-of-sample eFV**. The common set's stored `xfv` values
are rewritten in place onto the consensus-FV distribution, so using them for the debuted
half would compare a remapped number against a raw one.

## The comparators, frozen

FanGraphs and MLB Pipeline only. The consensus bust cell is the already-measured
`full_pool_km`, and re-deriving it here would be a second read of a cell that has one.

## The blast-radius rule

The bust rows are assembled and scored in their own frame and are **never** added to
`common_by_year`, `pooled_common`, `efv_common` or `efv_common_vintage`. The in-place eFV
remap re-derives its grid from whatever population it is handed, so admitting them would
re-bin the ties for every existing row and move cells this lane is not entitled to touch.

**Verified by running the backtest with this lane stashed and comparing.** Every published
cell was byte-identical with and without it.

## Pre-registered expectations

1. **Both registered legs come back NOT RESOLVABLE on both sides.** No absolute delta
   exceeds its own in-run E_cond MDE95. This would be wrong if any of the four crossed.
2. The product is a coverage receipt, not a win. The plan's own registration for this lane
   is "hitter nominal loss, pitcher null".

## Results, 2026-09-06

787 busts kept of 2,346 read. The receipt accounts for every drop: 9 excluded by the
screens, 128 with no ranking history, 494 whose last list year falls outside the resolvable
window, 922 not graded by all three raters in that year, 6 with no out-of-sample eFV.
Combined with 812 debuted rows, the frame is 1,599.

| comparator | n | delta | in-run E_cond MDE95 | verdict |
|---|---|---|---|---|
| FanGraphs | 1,599 | +0.01564 | 0.0268 | inside the floor |
| MLB Pipeline | 1,599 | +0.00231 | 0.0229 | inside the floor |

Per side, all four cells also sit inside their own floors: hitters +0.02491 against 0.0333
and +0.00301 against 0.0268; pitchers +0.01206 against 0.0436 and +0.01543 against 0.0396.

**Prediction 1 HELD.** Nothing is resolvable. eFV is nominally ahead of both raters on the
bust-inclusive pool and every margin sits inside the floor that pool can resolve, so no
claim may be made in either direction.

**What the lane bought.** Not a result about eFV. It bought the ability to say what the
published head-to-head does and does not cover, and to say it with a number: the flagship
frame is 100% survivors by construction, and on the one pool that includes the failures,
nothing separates the raters.

## A note on cohort drift, recorded because it bit during this session

`data/timeseries.json` is gitignored, so `conftest`'s end-of-session revert cannot see it:
that guard works off `git diff --name-only` and an ignored file never appears there. A
suite chunk regenerated it mid-session and added one player to the universe. Downstream,
the vintage-matched frame moved from 796 rows to 812 and the A-CLAIM-10 disagreement share
moved from 54.8% with an interval containing the coin to 57.3% with an interval excluding
it. Same code, same method, one extra player, opposite verdicts.

Nothing in this lane depends on which side that lands, and its own result is a null with
room to spare. It is recorded here because any future reader comparing two runs of this
artifact needs to know that the population underneath it is not pinned by git.

## The asymmetry control, added 2026-09-06 after the first build

The registration asked for one thing the first build did not deliver: score the busts "at
the preseason point of the last list year (or restrict to busts whose final list point is
itself preseason, 375 of 794, publishing the 419 in-season-final rows as an asymmetry
control)". The build took the first branch and skipped the control, which left the lane
unable to say whether its null holds in both subgroups or is carried by one.

Both groups are scored on the same preseason grades, so the grade vintage is symmetric
across raters in both. What differs is how long the raters held the player: an in-season
final point means somebody was still ranking him in June of the year they gave up on him.

The split is 374 preseason-final and 413 in-season-final of the 787 kept, against the
registration's predicted 375 and 419. That is close enough to treat the registration's
census as confirmed rather than merely restated.

| subgroup | comparator | n | delta | in-run E_cond MDE95 | verdict |
|---|---|---|---|---|---|
| preseason final | FanGraphs | 1,186 | +0.02613 | 0.0306 | inside the floor |
| preseason final | MLB Pipeline | 1,186 | -0.00095 | 0.0255 | inside the floor |
| in-season final | FanGraphs | 1,225 | +0.01899 | 0.0281 | inside the floor |
| in-season final | MLB Pipeline | 1,225 | +0.00416 | 0.0240 | inside the floor |

Each subgroup is smaller than the headline pool and therefore carries a wider floor, so a
subgroup crossing while the headline does not would have been the interesting outcome
rather than a contradiction. Nothing crosses. The closest cell is FanGraphs on the
preseason-final subgroup at 0.85 of its own floor, and the eFV-vs-Pipeline sign flips
between the two subgroups, which is what a null looks like.

No claim is made from a subgroup alone. The control exists so the headline null can be
said to hold in both halves rather than asserted over their average.
