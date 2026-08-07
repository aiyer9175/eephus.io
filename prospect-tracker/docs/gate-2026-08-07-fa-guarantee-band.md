# PRE-REGISTRATION: per-player FA guarantee/AAV band (omnibus-3 lane N)

Written 2026-08-07 BEFORE any arm was run. One attempt. Marginal is a FAIL.
Protocol: docs/EFV_GATE_STANDARD.md, narrowed by the criteria below.

## What is on the board today, and why it is a problem

Every priced member of the 2027 free-agent class carries the SAME relative
uncertainty. Measured on the served data/fa_class.json (generated 2026-08-06):

    projGuarP90 / projGuarP10 = 10.8610 for all 223 priced members,
    identical to six significant figures. projAavP90 / projAavP10 is the same
    number, because the AAV band is the guarantee band divided by the same
    term (fa_market.py:1774-1780).

So Tarik Skubal's $39.4M AAV is published with a P10 of $12.9M and a P90 of
$140.4M, and so is every other arm's, scaled. The width is a property of the
model's residual pool, not of the player. A disclosure currently fires above
2.5x, which means it fires on all 223 rows and therefore says nothing.

## Champion and challenger

  CHAMPION   flat band. Unconditional deciles of the training residual pool
             (fa_market.MarketModel.resid_log_guar), applied multiplicatively.
             BAND_SCALE_GUAR = False. This is what ships.
  CHALLENGER location-scale band. fa_bands.fit on the restricted z
             (pos group, log predicted guarantee, years, age, QO, prior TJ
             count), ridge-shrunk toward the flat band, failing to flat.
             BAND_SCALE_GUAR = True, BAND_RIDGE_GUAR = 3.0.

BAND_RIDGE_GUAR is FIXED at 3.0 in advance. The lab carries a ridge sweep
(0.0 / 0.3 / 1.0 / 3.0 / 10.0 / 30.0); running it and reporting the best arm
would be a six-way search reported as one test, which is exactly the failure
the standard exists to prevent. 3.0 is the value the 2026-07-25 T1.2 run
carried, so this is a re-test of one registered arm, not a search.

## Why this is a new gate and not a re-run of a measured null

T1.2 (2026-07-25, recorded at fa_market.py:144-168) tested this same arm on a
PINBALL-LOSS criterion and found nothing: pinball delta -0.00007 against an
MDE95 of 0.00288, and a zero-information control whose null band
[-0.00153, +0.00269] CONTAINS the candidate's delta.

This gate asks a different question, the one the served artifact makes urgent:
not "is the band sharper on average" but "is the band's WIDTH ALLOCATION less
wrong". A flat band can score well on average pinball while being far too wide
on the players everyone looks at and too narrow on the rest. The criteria below
are therefore interval-calibration criteria, and the primary one is a distance
to nominal coverage, which T1.2 did not test.

## Pre-registered criteria (both must hold)

  PRIMARY, interval calibration. On the 9 forward-chained held-out winters
  (2018-2026), the challenger's P10-P90 empirical coverage must be CLOSER to
  the nominal 0.80 than the champion's:

        |cov_scale - 0.80| < |cov_flat - 0.80|

  and the improvement must exceed the paired-bootstrap MDE95 for that
  statistic. T1.2's bootstrap put MDE95 for raw coverage at 0.01875 on this
  corpus and estimator; the improvement must clear the MDE95 measured in THIS
  run's bootstrap, and if no bootstrap is run because the point estimate does
  not even move in the right direction, the T1.2 figure is the ceiling on what
  a bootstrap could have found.

  SECONDARY, no accuracy regression. Guarantee and AAV MAE must stay within
  the champion's MDE. NOTE, and this is checked numerically rather than
  assumed: the band affects only proj_guarantee_p10_usd / proj_guarantee_p90_usd
  and their AAV siblings. proj_guarantee_usd, proj_years and proj_aav_usd are
  computed before the band is consulted (fa_market.py:1740-1758), and the band
  fit does not touch coef_guar or coef_years. So the point predictions are
  expected to be IDENTICAL between arms, and if they are not, the run is
  invalid and this gate is void.

  CONTROL, required to interpret either. The permuted-residual arm
  (BAND_PERMUTE_SEED set, the same estimator on a row-permuted residual
  column) must NOT score as well as the candidate. If the permutation null
  band contains the candidate's delta, the corpus does not support a
  conditional variance function and the result is a no-ship whatever the point
  estimate says.

  Conditional coverage (by predicted-guarantee decile, position group, age
  band and the megadeal slice) is reported for diagnosis. It is NOT a ship
  criterion here: cond-cov RMSE carried an MDE95 of 0.01264 at T1.2, which is
  larger than any movement this corpus has ever produced on it.

## Ship rule

Ship only if PRIMARY and SECONDARY both hold and the CONTROL separates.

Otherwise: no-ship. BAND_SCALE_GUAR stays False, the >2.5x disclosure stays
on the board, and the result is committed as an artifact with verdict
`deprecated` (a measured no-ship is deprecated, never rejected) plus a
MODEL_GLOSSARY entry. A loss is committed with its numbers, the same as a win.

## Result: NO-SHIP (2026-08-07)

Run after the criteria above were written. Point chain: 9 forward-chained
winters, 1,199 scored held-out signings. Bootstrap: B=40 paired draws
resampling the whole corpus with a refit per draw, the permuted control on the
same draws.

    arm      coverage   |cov-0.80|   pin_avg    cond_rmse   ratio_sd
    flat      0.82485     0.02485    0.16046     0.05355     1.4426
    scale     0.82235     0.02235    0.16074     0.05650     2.7379
    perm      0.81818     0.01818    0.16121     0.05742     2.1450

PRIMARY, FAILED. The challenger does move coverage toward nominal, by 0.00730
on the bootstrap mean, and it is the right direction. It is inside the noise:
MDE95 on this statistic is 0.01782 and the CI95 is [-0.02085, +0.01502], which
contains zero. The improvement is 2.4 times smaller than the smallest effect
this design could detect.

CONTROL, FAILED, and this is the decisive one. The zero-information arm, the
same estimator fit on a row-PERMUTED residual column, improves coverage
closeness by 0.00549 against the candidate's 0.00730, with an identical
p_improves of 0.775 and an overlapping interval. On the single point chain the
control is actually the closest of the three to nominal coverage (0.01818 vs
the candidate's 0.02235). Shuffling the residuals buys three quarters of the
candidate's entire result, so there is no result.

SECONDARY, held, and carries no evidence. 0 of 1,199 point predictions differ
between arms; guarantee MAE $9.7177M and AAV MAE $3.1258M in both. As
predicted, the criterion is satisfied by construction, so it cannot support a
ship on its own.

The fit is not inert: ratio_sd goes 1.4426 to 2.7379 with p_improves 0.05, so
the widths reliably spread apart. They just do not spread toward where the
errors are.

## What ships

Nothing. BAND_SCALE_GUAR stays False. The flat band and the >2.5x disclosure
stay exactly as they are.

This is the SECOND independent no-result on this arm: T1.2 (2026-07-25) on a
pinball criterion, this gate on an interval-calibration criterion, both with a
permutation control that scored as well as the candidate. Do not re-open it
with a ridge sweep over the same conditioning set; that is a six-way search on
a corpus that has now twice failed to separate from its own shuffle. It wants a
materially larger signing corpus or a different conditioning set.

## Owed follow-ups (files this lane does not own)

1. Move docs/fa_guar_band_eval.json to data/fa_guar_band_eval.json in the SAME
   commit as items 2 and 3. On its own in data/ it fails
   test_model_registry.test_every_eval_artifact_is_registered.
2. Registry row for data/model_registry.json:

       {"model_id": "fa_guar_band",
        "surface": "/fa/ (predicted guarantee and AAV bands)",
        "predicts": "P10-P90 interval width for a free agent's guarantee, as a function of the player rather than a flat multiple of the point estimate",
        "champion": "flat band (unconditional training residual deciles)",
        "baseline": "flat band",
        "metric": "held-out P10-P90 coverage distance from 0.80, forward-chained over 9 winters",
        "eval_artifact": "data/fa_guar_band_eval.json",
        "verdict": "deprecated",
        "notes": "NO-SHIP 2026-08-07 (docs/gate-2026-08-07-fa-guarantee-band.md). Coverage closeness improved 0.00730 against an MDE95 of 0.01782, CI95 [-0.02085,+0.01502], and the permuted zero-information control improved 0.00549 with the same p_improves 0.775. Second independent null on this arm after T1.2 (2026-07-25, pinball). Point predictions are band-invariant: 0 of 1199 rows differ, guarantee MAE $9.7177M in both arms. BAND_SCALE_GUAR stays False."}

3. MODEL_GLOSSARY line in test_methodology_freshness.py (the map is
   bidirectional, so the row above turns the suite red without it):

       "fa_guar_band": "internal",   # measured no-ship; no user-facing surface

4. assets/fa.js:715-721 says the per-tier fix "is not done". It is done and it
   failed. The comment wants one sentence pointing at this doc. Note also that
   the disclosure fires on 223 of 223 priced members (P90/point is 3.5601 for
   every one of them), so as a discriminator it currently carries no
   information; whether that should become unconditional copy is a display
   decision, not a model one.
