# A-CLAIM-13: the rater scale view

Registered in the master plan as "a side x year block-rho row per rater beside
`accuracy.per_year`, marked additional view; measured expectation MP pooled -0.0113 (0.93x
floor), no verdict change". Published at `accuracy.per_year_scale_view`.

## What it separates

The pooled Spearman stacks base years and sides. Both carry scale that belongs to the block
rather than to the rater. A base year with more rows contributes more pairs, and a base year
whose cohort realized more WAR contributes a longer outcome scale. The two sides are not on
one outcome scale at all: at the same consensus grade, pitchers realize a fraction of the
WAR hitters do, so a rater graded on a different hitter share is otherwise credited with a
difference between populations.

Percentile-normalizing the grade and the outcome inside each side-year block removes both,
and what is left is within-cohort ordering only.

## Why it is a view and not a verdict

Normalizing the target discards the MAGNITUDE of the outcome, and magnitude is most of what
a prospect grade is for. A rater who separates a 40 WAR career from a 4 WAR one has earned
the credit the raw scale gives him. This row answers the narrower question of within-cohort
ordering. The pooled cell stays primary and no published call reads this block.

## Results, 2026-09-06, on the 812-row vintage-matched frame

Fourteen blocks (seven base years by two sides), none below the eight-row minimum.

| rater | pooled rho | block rho | raw delta | placebo mean | delta net of placebo | in-run floor |
|---|---|---|---|---|---|---|
| FanGraphs | 0.3697 | 0.3371 | -0.03256 | -0.01100 | **-0.02156** | 0.0238 |
| MLB Pipeline | 0.4104 | 0.3737 | -0.03677 | -0.00928 | **-0.02749** | 0.0248 |
| PROSPX consensus | 0.4127 | 0.3823 | -0.03038 | -0.00628 | **-0.02410** | 0.0267 |
| eFV | 0.4056 | 0.3969 | -0.00878 | -0.00664 | **-0.00214** | 0.0344 |

**All three published raters carry block scale worth about 0.022 to 0.027 of their pooled
rho. eFV carries essentially none.** The three raters' raw deltas clear their own E_cond
floors AND fall outside their permutation bands; eFV's clears neither and sits inside its
band.

**THE REGISTERED EXPECTATION IS REFUTED ON SIZE AND HELD ON CONSEQUENCE.** The plan
predicted MLB Pipeline at -0.0113, which is 0.93 of its floor and therefore not resolvable.
Measured, it is -0.03677 raw and -0.02749 net, about three times the predicted size, and it
resolves. The "no verdict change" half of the prediction HELD: nothing published reads this
view, and the eFV-versus-consensus gap does not resolve on either the pooled cell or this
one.

## It is the base YEAR, not the side

| blocking | FanGraphs | MLB Pipeline | consensus | eFV |
|---|---|---|---|---|
| side only (2 blocks) | -0.00801 / 0.0141 | -0.01035 / 0.0133 | -0.00453 / 0.0177 | +0.00172 / 0.0261 |
| year only (7 blocks) | -0.02188 / 0.0189 | -0.02552 / 0.0190 | -0.02335 / 0.0197 | -0.00889 / 0.0196 |

Delta over its own floor. Every side-only cell sits inside its floor; every rater year-only
cell clears it. The side scale, which was the half of this lane anybody would have guessed
was doing the work, buys nothing measurable. The base year does all of it.

The leading explanation was exposure: older base years have had more seasons to accumulate
WAR, so pooling across vintages rewards a rater for the age of the cohort rather than for
ordering inside it, and eFV is an expected-WAR model that already prices exposure. **That
mechanism is a hypothesis and has not been tested here.** It was written down as the thing to
falsify next, not as a result.

### It was falsified the same day, by A-CLAIM-3

`EXPOSURE_MATCHED_LABEL.md` re-ran this exact view on the same 356 fully-resolved rows with
only the label changed, from career WAR to first-six-season WAR. **Not one rater's block
effect shrank. All four grew slightly** (FanGraphs -0.0338 to -0.0370, MLB Pipeline -0.0300
to -0.0319, consensus -0.0452 to -0.0468, eFV -0.0222 to -0.0337).

The label did what it was asked to do: the spread of block-mean outcome fell from sd 2.611 to
sd 1.575 and the range from 7.45 to 4.86 WAR, so about forty percent of the between-block
dispersion in the outcome was removed and the effect did not move. At 356 rows the block
effect is not itself resolvable on that cut, so what is refuted is the mechanism's predicted
DIRECTION, not the existence of some exposure component too small to see. The point estimates
were free to shrink and did not.

The next candidate is drift rather than exposure: the per-block mean GRADE is now published
beside the per-block mean outcome, and both decline across base years for every rater, with
the outcome decline surviving exposure matching because it is cohort quality rather than
calendar exposure. Between-block co-movement of grade level and outcome level would be
collected by the pooled statistic as ordering skill. That is where to look next and it is not
measured here.

## The gaps this view displays, floored

Four block rhos printed next to each other is a comparison whether or not it is labelled
one, so every gap carries its floor.

| gap | delta | in-run floor | CI95 | verdict |
|---|---|---|---|---|
| eFV vs FanGraphs | +0.05975 | 0.0345 | [0.0182, 0.1021] | clears, and is a RECEIPT |
| eFV vs MLB Pipeline | +0.02319 | 0.0283 | [-0.0095, 0.0578] | not resolvable |
| eFV vs consensus | +0.01450 | 0.0217 | [-0.011, 0.0407] | not resolvable |

The FanGraphs cell clears at 1.73 times its floor with an interval excluding zero. Under the
alpha-spending clause in `EPOCH_2026_PREREGISTRATION.md` this is a **receipt, not a claim**:
one confirmatory read of the claim family is declared at a named `RESOLVED_THROUGH` and
every other read, including this one, is descriptive. It does not go on the site and it does
not enter a Holm family.

## The sign flip, which is the most useful thing here

The eFV-versus-consensus gap is **-0.0071 on the pooled cell and +0.0145 on this view**. It
changes sign depending on whether the block scale is removed, and **neither reading
resolves**. The block view's floor is the tighter of the two (0.0217 against 0.0303), so if
anything it is the more sensitive instrument for this comparison, and it still cannot
separate them.

That is the strongest available argument for the published claim being "indistinguishable"
rather than a direction. A gap whose sign depends on a defensible choice of normalization,
under two instruments that both decline to resolve it, is not a gap anybody should be
quoting a direction for.

## On the honesty of adding controls after the first read

The placebo and the attribution were added AFTER the first measurement, because the first
measurement produced something the registration did not predict. Adding controls after a
surprising result is exactly when they are most necessary and most suspect, so what was done
is recorded rather than smoothed over.

The mitigation is that the placebo is a pre-specified null with nothing to tune: block labels
permuted at fixed block sizes, the same code path as the real pass, a fixed seed. It is not a
knob that could be turned until the answer improved.

And it earned its place immediately. The FIRST version used ONE permutation, and one draw
said the placebo accounted for essentially all of eFV's loss (-0.0091 permuted against
-0.0088 observed) and almost none of the raters'. That reading was wrong. At 200
permutations the placebo mean is similar for everybody (-0.006 to -0.011): the transform
costs every column about the same, and the difference between eFV and the raters is in the
signal, not in the method. A single-draw placebo is not a placebo.
