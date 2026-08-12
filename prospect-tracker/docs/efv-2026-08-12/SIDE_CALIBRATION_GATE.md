# E2a: is eFV systemically undervaluing pitchers?

Pre-registered 2026-08-12, BEFORE the lab existed and before any outcome was
read. Committed alone so git timestamps it. Producer:
`tools/efv_side_calibration_lab.py`. Artifact:
`data/xfv_side_calibration_eval.json`.

## The owner's question, and the constraint that comes with it

> Can we check to make sure we aren't systemically undervaluing pitchers in the
> eFV model? [...] Only 8 of our Top 100 are pitchers, that seems extremely low.
> Make sure we're evaluating source biases relative to WAG, rather than relative
> to other sources (ex. a source is not "overinflating pitchers" if they're
> consistently right about the WAR production that pitchers produce, even if
> other sources are lower on pitchers).

That second sentence is binding and it decides the whole design. **The reference
is realized outcomes, never another source's grade.** "eFV has fewer pitchers in
its top 100 than the consensus does" is not evidence of anything on its own;
whichever of the two is wrong is decided by what the players went on to produce.

## What is already known without reading an outcome

Structural, from the served artifact, and it is why this lane exists:

- Live board: eFV top 100 holds 8 pitchers, consensus top 100 holds 27.
- On the resolved pool the served eFV grade puts **0 pitchers at FV 60+, 6 at
  55, 23 at 50**, against consensus **12 / 48 / 103**.
- In the consensus top-300 band the mean eFV-minus-consensus is **+1.96 FV for
  hitters and -0.17 for pitchers**, so the gap is hitters being promoted past
  pitchers rather than pitchers being marked down.
- eFV grades come from `realized_implied_fv(E[6yr WAR])`: ONE shared WAR-to-FV
  curve for both sides. Predicted 6-year WAR averages 3.59 for hitters and 1.66
  for pitchers, so a shared curve necessarily grades pitchers lower.

So the mechanism is not in dispute. The question is whether that mapping is
RIGHT, and that is an outcome question.

## The two conventions, named, because they are different quantities

This is the Quantity A versus Quantity B trap that has cost this repo real time
before (see the FV industry framework note: five FV-to-WAR tables measuring five
different things, and the trap runs 2-3x).

- **VALUE SCALE (what eFV ships today).** FV means expected 6-year WAR through
  one shared curve. Equal FV means equal expected value regardless of side. A
  pitcher who will produce less WAR than a hitter grades below him, by design.
- **PERCENTILE SCALE (what the industry ships).** FV is graded within side. A 55
  pitcher is a 55 among pitchers. This is why public boards carry many more
  pitchers near the top.

Neither is wrong. They answer different questions, and the failure mode is
serving one while readers assume the other.

## Estimands, registered

Frame: the resolved pool, `kind` in (debuted, bust), busts entered at realized
6-year WAR = 0. Busts are INCLUDED because excluding them is survivor bias and
the bust rate differs by side (H 1,147 / P 1,082). n = 4,634.

- **M1, the decisive one.** Within each grade band, mean realized 6-year WAR by
  side, computed separately for the served eFV grade and for consensus FV.
  - If, at equal **eFV**, pitchers and hitters realize the same WAR, then eFV is
    calibrated on its own value scale and its low pitcher share is HONEST.
  - If, at equal **consensus FV**, pitchers realize materially less WAR than
    hitters, then the consensus is over-grading pitchers against outcomes, and
    eFV's lower pitcher grades are the more accurate reading of value.
- **M2.** Per-side calibration of predicted E[6yr WAR] against realized WAR:
  bias and slope, hitters and pitchers separately. Answers "is the model's
  pitcher WAR forecast itself biased", which is a different question from how
  the grade map spends it.
- **M3.** Top-100 pitcher share under three conventions: as served, under value
  parity, and under within-side percentile parity. Descriptive, no verdict.

## Decision rule, fixed now

1. **If M1 shows equal realized WAR at equal eFV** (side gap inside its
   bootstrap floor), eFV's value scale is calibrated. The low pitcher share is
   then a CONVENTION difference, not an accuracy defect, and any parity ship is
   a display decision that must be labelled as one. It must NOT be described as
   an accuracy improvement.
2. **If M1 shows pitchers realizing MORE WAR than hitters at equal eFV**,
   pitchers are genuinely undervalued on eFV's own scale. That is a real
   miscalibration and the remedy is a per-side grade-map correction, which is an
   accuracy fix and may be described as one.
3. **If M1 shows pitchers realizing LESS WAR at equal eFV**, eFV is if anything
   over-grading pitchers already, and a parity ship makes the value scale less
   accurate. It may still ship as a labelled convention, but the cost is stated
   in the copy and in this document.
4. **M2 is reported whatever it shows** and does not gate anything on its own: a
   biased WAR forecast is a model problem, not a grade-map problem, and fixing
   it in the map would hide it.

## Floors

Side gaps are read against a paired bootstrap over players, B = 2000, seed
20260812, clustered by player (one row per player, which this pool already is).
A gap inside its 95 percent interval is reported as not resolvable at this
power, in the language the rest of the site uses. Bands with fewer than 30 rows
on either side are reported and excluded from the pooled verdict; the eFV 60 and
55 pitcher cells (0 and 6 rows) are known in advance to fall here, and their
emptiness is itself the finding rather than a cell to be scored.

## What this lane may NOT conclude

- It may not call the consensus wrong because it disagrees with eFV, or eFV
  wrong because it disagrees with the consensus. Only realized WAR adjudicates.
- It may not read the served board's pitcher share as evidence. The served board
  is unresolved by construction; only the resolved pool carries outcomes.
- It does not re-open the rank frontier. Nothing here changes an ordering:
  every remedy in scope is a monotone per-side transform of the grade, which is
  rank-invariant within side by construction.

## Results

To be written by the lab. This section is deliberately empty at commit time.
