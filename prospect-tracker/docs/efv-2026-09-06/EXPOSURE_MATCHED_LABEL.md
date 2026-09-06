# A-CLAIM-3: the exposure-matched label

Registered in the master plan as "score the head-to-head on first-six-season eWAR instead of
career-to-date, in two cuts: fully resolved windows as the clean receipt, and the censored
full cut with `_label_6yr` weights and the censoring-bias direction stated beside it.
Pre-declared expectation: C1/C2 remain unresolved; a nominal flip is not quotable."

Published at `accuracy.claim_instruments.exposure_matched_label`.

## The defect it measures

Every published head-to-head cell scores grades against **career WAR to date**. A player who
debuted in 2014 has had eleven seasons to accumulate it and a 2022 debut has had three, so
the label rewards being older, and being older is a property of the base year rather than of
the grade.

The exposure-matched alternative already exists and is the label the eFV model itself trains
on: `efv_dataset._label_6yr`, the first six seasons from debut, with a flat-rate tail
projection and an exposure weight for rows not yet resolved.

## One correction to the registration

The plan says the fully resolved cut is "debuts through 2021". It is **debuts through 2020**.
`efv_dataset.RESOLVED_THROUGH` is 2025 and `TARGET_SEASONS` is 6, so a 2021 debut's window
closes in 2026 and is still censored. The artifact derives the boundary from the shipped
constants rather than restating the plan's number, so it moves on its own when
`RESOLVED_THROUGH` does.

## Results, 2026-09-06

2,113 players carry a six-season label: 1,236 fully resolved, 877 censored. Of the 812-row
vintage-matched frame, 356 rows are fully resolved.

**Fully resolved cut, n = 356, base years 2017 to 2020, every weight 1.0.**

| comparator | delta | in-run E_cond MDE95 | verdict |
|---|---|---|---|
| PROSPX consensus | -0.00010 | 0.0377 | inside the floor |
| MLB Pipeline | +0.00129 | 0.0419 | inside the floor |
| FanGraphs | +0.05627 | 0.0513 | clears, at 1.10x, and is a RECEIPT |

**Censored full cut, n = 812, mean exposure weight 0.805, minimum 0.5.**

| comparator | delta | in-run E_cond MDE95 | verdict |
|---|---|---|---|
| PROSPX consensus | -0.00264 | 0.0215 | inside the floor |
| MLB Pipeline | +0.00335 | 0.0274 | inside the floor |
| FanGraphs | +0.03362 | 0.0337 | at 1.00x its floor, which is not a result |

**The pre-registered expectation HELD.** C1 and C2 remain unresolved on both cuts. The
consensus cell on the clean receipt is **-0.00010**, which is as close to a dead heat as this
instrument can report.

The FanGraphs cell on the resolved cut clears at 1.10 times its floor. Under the
alpha-spending clause in `EPOCH_2026_PREREGISTRATION.md` that is a **receipt, not a claim**:
one confirmatory read of the family is declared at a named `RESOLVED_THROUGH` and every other
read is descriptive. On the censored cut the same comparison sits at exactly 1.00 times its
floor, which is a coin, and two adjacent cuts landing on either side of a threshold is the
definition of a margin nobody should quote.

## The censoring bias is stated, not corrected for

The tail projection assumes a flat per-season rate, which `data/xfv_label_censoring_eval.json`
measured as biased. The direction and the per-cell magnitudes travel with the censored cut in
the artifact. They are not corrected out, because the bias is a property of the shipped label
the eFV model is fitted to, and correcting it here would score the raters against a label the
model was never trained on.

## What this lane refutes, which is the more useful half

A-CLAIM-13 measured a resolvable base-year block effect in three of four raters and wrote
down **exposure** as the leading explanation, explicitly marked untested. This lane is the
test, and it runs on the same 356 rows with only the label changed.

| rater | block minus pooled, career WAR | block minus pooled, six seasons |
|---|---|---|
| FanGraphs | -0.03381 | -0.03699 |
| MLB Pipeline | -0.02995 | -0.03186 |
| PROSPX consensus | -0.04515 | -0.04680 |
| eFV | -0.02217 | -0.03374 |

**Not one of them shrinks. All four grow slightly.**

And the label did the job it was asked to do, which is what makes this a refutation rather
than a null result about nothing. The spread of block-mean outcome falls from **sd 2.611 to
sd 1.575** and the range from **7.45 to 4.86 WAR**: exposure matching removed about forty
percent of the between-block dispersion in the outcome, and the block effect did not move.

**The exposure explanation for A-CLAIM-13 is refuted.** `RATER_SCALE_VIEW.md` is corrected to
say so.

One caveat travels with it. At 356 rows the floors on this cut run 0.036 to 0.055, so the
block effect is not itself resolvable HERE; what is refuted is the mechanism's predicted
direction, not the existence of some exposure component too small to see. The point estimates
were free to shrink and did not.

## The next candidate, named with data rather than asserted

The per-block mean GRADE is now published beside the per-block mean outcome. Both decline
across base years for every rater, and the decline in the outcome survives exposure matching
because it is cohort quality rather than calendar exposure. Between-block co-movement of
grade level and outcome level would be collected by the pooled statistic as ordering skill.

That is where to look next. It is **not** measured here and is not claimed.
