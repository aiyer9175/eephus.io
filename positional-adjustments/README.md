# Defensive positional adjustments

Fitted positional adjustments from eephus.io, published for Will's eWAR and SDR
work. Regenerate with:

    python prospect-tracker/tools/export_positional_ladder.py

Files:

| file | what it is |
| --- | --- |
| `positional_ladder_v1.json` | the full record: both bases, CIs, era splits, window sensitivity, the identification block, the folklore comparison |
| `positional_ladder_v1.csv` | the two ladders plus CI, one row per position |

## The short version

Runs per 650 PA of exposure, relative to the league-average defensive position.

| Pos | Exposure-weighted | Fielder-centred |
| --- | ---: | ---: |
| C | +10.88 | +9.40 |
| SS | +9.38 | +7.90 |
| 2B | +5.12 | +3.64 |
| CF | +4.14 | +2.66 |
| 3B | +3.62 | +2.14 |
| LF | -6.39 | -7.87 |
| RF | -6.52 | -8.00 |
| 1B | -8.40 | -9.88 |
| DH | -13.70 | -15.18 |

**Use the exposure-weighted column** unless you have a specific reason not to.
It is what every internal valuation runs on and it is the basis that matches the
Baseball-Reference frame eWAR rides.

The two columns differ by a single constant (1.48 runs), so every GAP between
two positions is identical in both. Only the zero point moves.

## Three sums, and only one of them is zero

This is the part that generates bug reports, so it is worth reading once.

- **Exposure-weighted over all nine rungs = 0.** Imposed by the fit. This is the
  only sum that is a constraint.
- **Equal-weight over nine rungs = -1.87.** Not a defect. DH is about 9% of
  league exposure, not one ninth, so equal-weighting over-counts its large
  negative rung.
- **Equal-weight over the eight fielders, on the exposure-weighted column =
  +11.83.** Also not a defect: once the weighted sum is pinned at zero, this
  value is forced arithmetically.

On the fielder-centred column the eight fielders do sum to zero, with DH outside
the sum. That is the folklore convention and it is why that column exists.

## What this is, and what it is not

The ladder is a least-squares **inversion** of Baseball-Reference's own
`runs_position` per 650 PA on per-row innings shares, no intercept, recentred so
the exposure-weighted sum is zero. Current fit: 2021-2026, n=2,023
player-seasons, min 200 PA, R-squared 0.974.

So a rung reads as **what Baseball-Reference prices that position at**, not as
an independent measure of how hard the position is to play. For work riding the
bWAR frame that is exactly what you want. For a from-scratch defensive model it
is a constraint to be aware of.

The rolling six-season window is a measured choice, not an assumption: it beat
the 2012-onward pool by 0.10 runs per 650 PA of held-out error (bootstrap
interval 0.079 to 0.115, better in all three held-out seasons) under a
pre-registered forward-chained gate.

Era drift is real and larger than the sampling intervals, which is why the
window rolls. `era_splits` in the JSON carries the per-era rungs.

## The folklore comparison, and its trap

`folklore_comparison` in the JSON holds the FanGraphs/Tango table everyone
quotes (C +12.5, SS +7.5, 2B/3B/CF +2.5, LF/RF -7.5, 1B -12.5, DH -17.5).

**Do not subtract it from ours directly.** That table is quoted per full
defensive season (162 games, 1,458 innings); ours is per 650 PA of exposure,
which at this fit's innings-per-PA is about 1,278 innings. Subtracting as quoted
overstates the folklore magnitudes by roughly 14%. First base reads 4.1 runs of
disagreement as quoted and 2.6 on a like-for-like basis; catcher reads 1.6 as
quoted and lands within 0.1.

The JSON carries both the raw table and a rescaled one, and **neither is
presented as the answer**. The convention is genuinely ambiguous (the folklore
table is quoted per 162 games in some sources and per 600-700 PA in others), and
it is the FanGraphs ladder while this fit inverts Baseball-Reference, so the
comparison is cross-system before it is cross-basis.

## Reliability constants

`signal_k_inn` carries the per-position innings constants `ewar.py` already
consumes for shrinkage. SDR will want an equivalent, and these are the piece of
the positional fit that fielding work actually touches.

## Provenance

Sliced read-only from `prospect-tracker/data/positional_fit.json` by
`tools/export_positional_ladder.py`. The exporter refuses to refit: the fit has
one owner (`positional_fit.fit_ladder`), because two independently refitted
ladders once disagreed by 0.35 runs. `source_generated_at` in the JSON is the
artifact's own stamp.
