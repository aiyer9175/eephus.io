# Pre-registration and result: body type and infield position (Lane E4)

Written 2026-08-06. Harness: `tools/anthro_position_lab.py`. Artifact:
`data/anthro_position_eval.json`. Registry row: `anthro_position_claims`.

## What this is

Three beliefs about body type and infield position, stated by the owner, tested
against the data and reported whatever they said. This is a MEASUREMENT, not a
shipping model, and that was the plan for it before it ran.

The master plan (Lane E4) is explicit about why. `positional_fit.py` is already a
validated engine for move SIZE, with a null verdict on who-gets-demoted. A prior
arm gate already NO-SHIPPED because raw arm-by-position is confounded by throw
context: 1.94 mph of context-adjusted spread against a 3.80 within-position
standard deviation. And OAA already contains arm and legs, so bolting an anthro
bonus onto the fit would double count. The plan's instruction was to test the
owner's claims directly and, if the prior fails its gate, ship the measurement as
the deliverable.

## The claims

| Id | Claim | Exposure | Outcome | Predicted sign |
|---|---|---|---|---|
| H1 | A short hitter is a poor first baseman | height, inches | career share of innings at 1B | positive |
| H2 | An elite arm suits third base | scouted `throw`, 20-80 | career share of innings at 3B | positive |
| H3 | A weak arm pushes a player to second base | scouted `throw`, 20-80 | career share of innings at 2B | negative |

## Design, fixed before fitting

* **Population.** Position players only, who carry a scouted grade and later
  recorded MLB fielding innings. Pitchers excluded, see the correction below.
* **Estimator.** Spearman rho. Scale free, and it does not assume the
  relationship is linear.
* **Outcome.** Career share of innings rather than one season, because the claims
  are about where a player ends up, and a single season is mostly noise about
  where a club happened to need him.
* **Null.** Permutation, 2,000 shuffles, two sided.
* **Interval.** Bootstrap percentile 95% CI, 2,000 resamples.
* **Zero-information control.** A uniform-noise exposure through the identical
  pipeline. If it ever returns SUPPORTED the harness is broken.
* **Verdict rule.** SUPPORTED requires all three of: permutation p below 0.05,
  a 95% CI clear of zero, and the sign the claim predicts. Two of three is not a
  pass.
* **Refusal rule, fixed in advance.** No model ships off this if a claim's CI
  includes zero, or if the effect is smaller than the within-position spread the
  earlier arm verdict measured. A pre-registration that can only succeed is not
  one.

## A correction, recorded rather than hidden

The first run reported **H1 CONTRADICTED at p = 0.0005**, a real-looking effect in
the direction opposite the claim. It was an artifact of the population, not a
finding.

Pitchers were still in the sample: 55.4% of the height rows, averaging 74.64
inches against a hitter's 72.62, and recording essentially no innings at first
base. Tall bodies with a zero outcome, in bulk, produce a negative
height-to-first-base correlation on their own.

**The zero-information control passed on that run.** It could not have caught
this. A noise exposure tests whether the estimator is honest; it says nothing
about whether the population is the one the claim is about. Those are different
failures, and only the second was present. Worth remembering the next time a
control passing is taken as evidence the design is sound.

## Results, position players only

| Claim | n | rho | 95% CI | perm p | Verdict |
|---|---|---|---|---|---|
| H1 short is a poor 1B | 742 | +0.182 | [0.113, 0.253] | 0.0005 | **SUPPORTED** |
| H2 elite arm suits 3B | 746 | +0.049 | [-0.022, 0.118] | 0.187 | NOT SUPPORTED |
| H3 weak arm pushes 2B | 746 | -0.110 | [-0.179, -0.041] | 0.003 | **SUPPORTED** |
| Zero-information control | 742 | +0.013 | includes zero | 0.741 | clean |

Two of the three hold. H1 is the strongest of them and it is the one that
required the correction above to see at all.

H2 has the sign the claim predicts and cannot be separated from zero at this
sample size. That is not evidence the belief is wrong; it is an absence of
evidence either way, and it is consistent with what the earlier arm verdict
predicted for the infield. It stays open rather than being reported as refuted.

## What this does NOT license

**A SUPPORTED verdict here means clubs behave as if the belief is true. It does
not mean the belief is true.** Career innings share is an outcome of club
decisions. A front office that holds the same folk wisdom will produce exactly
this correlation whether or not the wisdom describes anything real about the
player. Every number above is a measurement of behaviour, and the causal question
is untouched.

Three specific things that remain refused:

1. No additive anthro bonus at observed positions. OAA already contains arm and
   legs, and the earlier gate refused raw arm-by-position on confounding grounds
   that this study does nothing to remove.
2. No shipping model off H1 and H3 alone. The plan's shape for a defensible model
   is a prior on z at UNOBSERVED positions only, where the current model
   extrapolates blind, and that requires the anthro prior to clear the existing
   `conversion_accuracy` and `backtest` harnesses as a fifth scored arm on
   identical rows. That gate has not been run.
3. No public claim that a short first baseman is worse at the position. What was
   measured is that shorter players are assigned there less often.

## Next step if this is taken further

Add the anthro prior as a fifth scored arm in `positional_fit.conversion_accuracy`
and `positional_fit.backtest`, on identical rows, and ship only on a positive MAE
advantage with a CI clear of zero. If it fails, this document is the deliverable
and that is an acceptable outcome.
