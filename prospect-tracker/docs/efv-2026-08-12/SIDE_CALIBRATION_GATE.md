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

## Results (2026-08-12, `data/xfv_side_calibration_eval.json`)

Pool 4,634 (2,266 hitters / 2,368 pitchers), busts at realized WAR 0,
bootstrap B=2000 seed 20260812.

### The headline answers the owner's question, and it is not the feared one

**At equal CONSENSUS FV, pitchers massively underdeliver at the top.** In the
consensus FV 55 band: hitters realize **13.41** first-six-year WAR, pitchers
**4.84**, a gap of **-8.58 [-12.69, -4.46]**, resolvable. This is not a
bust-rate artifact and that was checked: both cells are essentially all
debuted (hitters 76 of 76, pitchers 47 of 48), so this is what happened to the
players who actually reached the majors.

Measured against outcomes, which is the only reference this lane accepts, **the
industry's higher pitcher share at the top is not vindicated. It is
over-grading.** eFV serving fewer top-100 pitchers than the consensus is the
more accurate reading of value, not a defect.

### But eFV genuinely under-grades pitchers in one band

At **eFV 45**, pitchers realize **+1.13 [0.19, 2.04]** WAR more than hitters
carrying the same eFV grade (n 368 hitters / 372 pitchers), resolvable. Decision
rule 2 fires for this cell: on eFV's own value scale, pitchers in that band are
undervalued. Part of it is a lower bust rate (15.9% against 23.9%).

Every other scorable cell on both graders is **not resolvable at this power**.
1 of 4 scored eFV cells and 1 of 4 scored consensus cells resolve, so this is a
band-local finding, not a sweep.

### The model's own WAR forecast is not the problem

M2, and it rules out the simplest explanation: hitters bias **-0.105**, pitchers
bias **-0.007**, slopes 1.139 and 1.169. The pitcher WAR forecast is close to
unbiased and no worse calibrated than the hitter one. **eFV is not systemically
under-forecasting pitcher WAR.** It correctly predicts that pitchers produce
less (mean predicted 1.163 against 2.037; mean realized 1.170 against 2.142),
and a single shared WAR-to-FV curve then necessarily grades them lower. The low
share is the shared curve spending a real difference, not a broken forecast.

### What each convention would do (M3, descriptive)

On the resolved pool's top 100: as served, eFV puts **0** pitchers there;
consensus as-ranked puts **23**; within-side percentile parity puts **51** on
either grader.

### Verdict against the registered decision rule

Mixed, and the two halves point opposite ways, so neither alone decides:

- **Rule 1 holds at the top.** eFV's value scale is doing its job there, and the
  consensus is the one disagreeing with outcomes. A blanket parity ship would
  promote precisely the cohort measured to underdeliver by 8.58 WAR, which is
  rule 3: it may ship as a labelled convention but it makes the value scale less
  accurate and the copy must say so.
- **Rule 2 holds at FV 45.** A targeted per-side correction there is an accuracy
  fix and may be described as one.

So the evidence supports a **narrow** correction and contradicts a **blanket**
one. That is a genuine conflict with the owner decision taken on 2026-08-12,
which was recorded BEFORE this lane ran and selected cross-side parity outright.
It is referred back rather than resolved here, per the standing rule that a
pre-registration does not get to spend an owner decision the measurement has
since undercut.

### Limits, stated

- The served eFV grade is retrospective on this pool: this measures the SHIPPED
  grade map against outcomes, not an out-of-sample forecast.
- Bands are coarse and the top pitcher cells are thin by construction (0 rows at
  eFV 60, 6 at 55), which is itself the finding rather than a cell to score.
- Nothing here re-opens the rank frontier. Every remedy in scope is a monotone
  per-side transform and is rank-invariant within side.
