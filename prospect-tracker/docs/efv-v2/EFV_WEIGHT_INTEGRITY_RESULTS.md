# eFV driver weight integrity: results for the owner (2026-10-22)

Plain language. Every number is copied from `data/efv_weight_integrity.json`; the method, fixed
before the read, and the full tables are in `docs/efv-v2/EFV_WEIGHT_INTEGRITY.md` (sections 11 and
12). Development frames only (list years 2017 to 2019, debut cohorts 2017 to 2023); nothing here is
cut by consensus-FV level. No em-dashes.

## The one-line answer

The served eFV weights hold up: no simpler head, re-standardized input or rank-based objective
was shown to be as good as the served heads under the registered rule, so nothing changes. Five
pitcher drivers and the hitter hit tool are real; the other fifteen pitcher drivers are too small
to confirm one at a time. The hitter side adds nothing measurable over consensus on these
frames; the pitcher side adds about one point of rank correlation, inside the noise.

## What was asked and what was not reopened

You asked whether eFV's driver and sub-driver weights are accurate to MLB outcomes, without
redoing what failed. This read only re-weights the keys the served heads already carry, on the
rows they were already fitted on. No new driver, model class, calibration, label or vintage was
tried. Every comparison was made against the served heads, against consensus alone, and against a
planted signal pushed through the same pipeline to prove the test could see a real difference.

One correction to the task text: the served hitter skill head has ONE key, the hit tool grade, at
weight 0.297. The nine hitter keys sometimes counted are the arrival (timing) head, which carries
weight 0 and moves nothing.

## Which weights are real and which are noise

Each driver's weight per standard deviation, in percentile points of consensus rank, with how
sure we are (95 percent range, resampling players and, separately, whole clubs):

| driver | weight per SD | 95 percent range | verdict |
|---|---|---|---|
| hitters: hit tool grade | +5.1 at the served weight (+17.1 in the head) | +9.2 to +28.9 in the head | real |
| pitchers: population translation | +12.8 | +7.5 to +20.1 | real |
| pitchers: called plus swinging strikes | +6.8 | +2.1 to +12.1 | real |
| pitchers: popups per ball in play | -6.7 | -12.6 to -1.7 | real (fewer popups grade up) |
| pitchers: strikeouts beyond whiffs | +5.5 | +1.3 to +10.8 | real |
| pitchers: command grade | +5.5 | +1.4 to +11.0 | real |
| pitchers: IL days | -4.1 | -8.8 to +0.2 | weak |
| the other 15 pitcher drivers | -1.9 to +3.0 | every range crosses 0 | noise |

"Noise" needs care. When we planted slopes of the served size into the same rows, the test could
confirm only about a third of them. So the fifteen are not shown to be zero; they are too small to
confirm one at a time with about 1,700 pitcher rows. Taken together they still move pitcher grades.

The head weights: the hitter weight 0.297 is real but loose (95 percent range 0.08 to 0.59). The
pitcher weight sits at the cap of 1.0 on a ratio whose range is 0.53 to 1.87. The arrival weight is
0 on both sides, and the data back that (both ratios are negative).

## Did a simpler or differently fitted head do as well?

Against the served heads, on the pooled development frames (positive is better than served):

| head | hitters | pitchers |
|---|---|---|
| unit weights on the steady drivers (one fitted scale) | -0.0054 | +0.0007 |
| heavier ridge (grid extended past the served 1000) | +0.0006 | +0.0002 |
| sparse, the top few steady drivers | -0.0017 | -0.0131 |
| inputs re-standardized by level and season | +0.0002 | -0.0048 |
| rank-based (pairwise) loss | +0.0013 | -0.0015 |
| consensus alone (no drivers at all) | +0.0014 | -0.0095 |

The registered rule asked each one to be shown no worse than served by more than 0.005, with
both kinds of resampling, after correcting for ten tests at once, AND not to trail consensus alone.
Only the re-standardized hitter head cleared the first part, and it trails consensus alone, as the
served hitter head does. Nothing passed.

The near miss worth knowing about: unit weights on the pitcher side match the served head in
accuracy (+0.0007) while cutting the sampling noise in pitcher grades to a fifth (a typical
pitcher's driver contribution has a sampling spread near 10 percentile points under the served
head, near 3 under unit weights). Its range (-0.011 to +0.012) is too wide to prove it is not worse,
so under the rule it does not ship.

## What shift was found between the live board and training

A classifier separating today's board from the training rows, on the drivers the served heads
read, scores 0.72 for pitchers and 0.62 for hitters (0.5 is no difference). The shift sits in:

- the pitcher 60-day IL count, 1.23 standard deviations higher on today's board (the known
  bookkeeping and league-practice drift);
- the pitcher command grade, 0.39 lower;
- the hitter hit tool grade, 0.46 lower (and, outside the served head, the power grade 0.69 lower).

Re-reading those drivers within level and season removes most of it (pitchers 0.72 to 0.62,
hitters 0.62 to 0.51) but costs pitcher accuracy (-0.0048) and is not proven harmless, so it is
not adopted. A shift that moves every player the same way does not change anyone's rank; only
spread changes and changes in who sits where do.

## What we should do

1. Keep the served weights. Nothing tested here beats or safely replaces them.
2. Expect little from the hitter drivers on these frames: the served hitter head ties consensus
   (-0.0014, range -0.021 to +0.017). It does better on the six-season WAR label (+0.0086, range
   -0.012 to +0.028), also a tie. More hitter drivers will not help until there is more signal to
   find, and the feature frontier is already closed.
3. The pitcher unit-weight head is the one idea with a real argument (equal accuracy, much less
   noise). It can only be adopted through a new registered read on a frame this read did not
   use, such as the 2025 debut cohort when its look opens; that is an owner choice (below).
4. The 60-day IL drift on the live board is real and large. It belongs with the existing dark
   drift fix (EFV_PIT_DRIFT_REBASE), which is already built and waiting on an owner decision.

## Owner questions (defaults applied: nothing changes)

- Q1 Pitcher unit weights. (a, default) keep the served 21-driver pitcher head. (b) register a
  confirmatory read of the unit-weight pitcher head on the next frame that opens (the 2025 debut
  cohort look), adopting it only if it passes there. (c) adopt it now by owner override: 196 of 941
  pitchers move by a grade or more, 12 by three or more, 40 of the top 50 stay.
- Q2 Hitter drivers. (a, default) keep the hit tool at 0.297. (b) register a read of a
  consensus-only hitter eFV (weight 0) on the next frame that opens, since the served hitter head
  ties consensus here.

## What changed

Nothing served. No flag, no dark build, no weights file. The artifact
`data/efv_weight_integrity.json` and these two documents are the whole output; the efv_v2 row of
`data/model_registry.json` carries a note.
