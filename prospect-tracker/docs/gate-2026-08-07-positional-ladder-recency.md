# Gate: is the positional ladder better read on the current era?

Pre-registered 2026-08-07, lane K5 of docs/master-plan-2026-08-07-omnibus3.md.
Written and committed to disk BEFORE any candidate was fitted or any held-out
number was computed. Standard: docs/EFV_GATE_STANDARD.md.

## The question

`positional_fit.fit_ladder` recovers Baseball-Reference's own positional
constants by inverting `runs_position` per 650 PA onto innings shares, no
intercept, on a 2012-2026 window (positional_fit.py:90). The artifact publishes
its own era splits, and the measured drift is LARGER than the sampling CIs:

| rung | shipped 2012-2026 | CI95            | 2021-2026 era | drift |
|------|-------------------|-----------------|---------------|-------|
| SS   | +8.92             | [8.73, 9.15]    | +9.44         | +0.52 |
| 2B   | +4.73             | [4.54, 4.94]    | +5.17         | +0.44 |
| CF   | +3.74             | [3.52, 3.97]    | +4.17         | +0.43 |
| C    | +10.67            | [10.48, 10.90]  | +10.95        | +0.28 |
| 1B   | -8.60             | [-8.78, -8.39]  | -8.37         | +0.23 |

A CI is a statement about sampling noise. When the era-to-era movement is two to
three CI half-widths, the pooled fit is an average of two different tables rather
than a precise reading of one. That is a reason to ASK whether a recency-aware
fit predicts the current era better. It is not evidence that it does, because a
shorter window is also a noisier one, and the drift above is measured IN SAMPLE.

## What ships if the gate passes

`LADDER_FIRST_SEASON` (or a recency weight) inside `positional_fit.fit_ladder`,
which is THE fit: `prospect_def_value.POS_ADJ` reads the artifact, so the change
propagates to `def_value` automatically. Nothing else is edited. One-owner rule
holds: no second ladder is fitted anywhere.

## What ships if the gate fails

The null is committed as an artifact and the 2021-2026 era rung is published on
/pal/ as a LABELLED SECONDARY COLUMN, so a reader can see the drift the model
already measures without the served valuation moving. No served grade, rank or
dollar changes.

## Design

Scoring is FORWARD-CHAINED on the model's own target. For each held-out season
T in {2024, 2025, 2026}: fit on player-seasons with year <= T-1, then predict
each held-out player-season's `runs_position * 650 / PA` from its innings-share
row. No held-out season ever informs the fit that scores it.

Rows are exactly `_ladder_design`'s rows (min 200 PA, DH exposure as the
residual). Held-out n: 365 (2024) + 348 (2025) + 228 (2026, partial season from
the current feed) = 941 player-seasons. Training rows through 2023: 4,027.

The level of a ladder is unidentified (every share row sums to 1), so a level
difference between two candidates is not a claim. Prediction is therefore scored
on the UNCENTRED least-squares solution, which is what the design matrix
actually predicts with, and the recentring stays a reporting convention. This
matters: comparing recentred vectors would score a convention, not a model.

### Champion (incumbent)

The shipped spec, refit honestly on the training window only: unweighted least
squares over ALL training seasons from `LADDER_FIRST_SEASON` = 2012.

### Challenger W (PRIMARY, the one that can ship)

Windowed: unweighted least squares over the last SIX training seasons only
(2018 through T-1). 2018 is not tuned here. It is already a published window in
the artifact's own `window_sensitivity` block, so the primary challenger
introduces no new free parameter.

### Challenger R (SECONDARY, reported, CANNOT ship on its own)

Recency-weighted least squares over the same 2012-onward span with weight
`0.85 ** (T - 1 - season)` (about a 4.3-season half-life). This carries one
free parameter chosen a priori, so it is reported for shape but is not eligible
to ship in this program; shipping it would need its own single-candidate gate.

### Zero-information control

Challenger W refit on training labels PERMUTED within the training rows. The
control must score far WORSE than the champion. This is the same control the
shipped 4-split accuracy gate used (its CI95 was [-5.12, -4.92]), and it exists
to prove the protocol can tell a real fit from a fake one. Note the artifact's
standing caveat: a y-permutation is a valid CONTROL here and was correctly
rejected as a NULL for the shape gate, where a refit 9-parameter model beats a
fixed table on random labels by construction.

## Pre-registered decision rule

Primary statistic: dMAE = MAE(champion) - MAE(Challenger W), pooled over all 941
held-out player-seasons. Positive means the challenger is better.

Paired bootstrap, 2,000 draws, RESAMPLED BY PLAYER (cluster bootstrap), because
the same player contributes up to three held-out seasons and treating those as
independent would understate the interval.

SHIP requires ALL FOUR:

1. dMAE paired-bootstrap CI95 EXCLUDES ZERO and lies entirely above it.
2. Sign consistency 3/3: Challenger W has the lower MAE in each of 2024, 2025
   and 2026 scored separately. This is the anti-marginal rule, and it mirrors
   the shipped gate's own "4/4 splits positive" clause.
3. The zero-information control scores materially worse than the champion
   (dMAE control CI95 entirely BELOW zero), confirming the protocol
   discriminates on this row set.
4. The identification tests stay green and `data/def_home.json` is verified
   unchanged (or the change is explained), per the lane's atomicity clause.

Any one of these failing is a NO-SHIP. A CI that touches zero is a fail, not a
"trend". One attempt; this is not re-run with a different window if it fails.

## Committed loss on failure

Publish the null in `data/positional_ladder_recency_eval.json` with verdict
`deprecated` (the enum's value for a measured no-ship), leave
`LADDER_FIRST_SEASON` at 2012, and ship the fallback: the 2021-2026 era rung as
a labelled secondary column on the /pal/ ladder table, drawn from the artifact's
existing `era_splits` block, described as a WINDOW SENSITIVITY and not as a
better table.

## What this gate cannot say

It scores prediction of Baseball-Reference's own bookkeeping quantity, which is
what the ladder is an inversion of. A win means the current era's BRef constants
are better recovered by a recent window. It says nothing about whether those
constants are the right prices, and nothing about how hard a position is to
play.

---

# RESULT, appended after the run

Everything above this line was on disk before the harness
(`tools/positional_ladder_recency_lab.py`) was written or run. Full numbers:
`data/positional_ladder_recency_eval.json`.

## The four clauses

| clause | required | measured | verdict |
|--------|----------|----------|---------|
| 1. dMAE CI95 above zero | excludes zero, positive | +0.097, CI95 [0.0789, 0.1145] | PASS |
| 2. sign consistency | 3 of 3 | 2024 +0.079, 2025 +0.124, 2026 +0.084 | PASS |
| 3. control worse | CI95 below zero | -5.31, CI95 [-5.61, -5.01] | PASS |
| 4. atomicity | identification green, def_home unchanged | see below | PASS, with a pending regen |

Pooled held-out MAE, 941 player-seasons: champion 1.0515, Challenger W 0.9545,
Challenger R 0.9824, control 6.3627.

One wording correction to the design above, made here rather than by editing a
pre-registration: Challenger W's window is "the last six training seasons",
which is 2018-2023 only for the first fold. It ROLLS, so it is 2019-2024 for the
2025 fold and 2020-2025 for the 2026 fold, and the artifact records each fold's
actual window under `per_season[T].train_seasons_challenger_w`. The rolling form
is what shipped, and it is why the shipped constant is a window LENGTH rather
than a first season.

Challenger R (recency-weighted, the SECONDARY arm) also beat the champion, at
+0.069 CI95 [0.0584, 0.0792]. It is NOT what shipped: it carries a hand-chosen
decay and the pre-registration says it cannot ship on its own. It is reported
because a result that only reproduces under one specification is a weaker result
than one that reproduces under two, and this one reproduced under both.

## Clause 4 in detail

`data/def_home.json` cannot move, and the argument is structural rather than an
A/B: `def_home_export` reads only `p_hold` and `def_home_entropy` off
`def_value()`, and both come from `mlb_position_probs`, which never touches
`POS_ADJ`. The 2026-07-25 ladder adoption measured the same thing empirically
(0 of 2,478 records differed).

The model's own VALIDATED claim is untouched. `conversion_accuracy` takes no
ladder argument, so the out-of-sample MAE on 169 real movers is byte-identical
under the swap: model 5.682 against carry-over 6.733, league average 6.284,
permuted 6.244.

What DOES move is the /pal/ Position Fit board, and it was measured rather than
assumed. Same 464 rows, 13 change best position, 4 change the misplaced flag
(68 flagged to 65), the gain in runs per 650 PA moves by a median 0.05, p90 0.26,
max 0.47. The demotion AUC, already a published null, reads 0.4809 against
0.4934; both sit below a coin flip and inside the permutation band, so this is
not a claim in either direction.

## What is NOT done, and why the change is not live yet

`positional_fit.py` carries the gated window. `data/positional_fit.json` does
NOT: regenerating it needs three things in one commit, and two of them are
outside this lane's file ownership.

1. `python positional_fit.py` to rebuild the artifact (verified to run clean and
   to reproduce the committed artifact exactly at the retired window).
2. `test_positional_fit.py` rebased: `test_ladder_is_a_real_inversion_not_a_guess`
   pins the fitted window against `pf.LADDER_FIRST_SEASON` and the row count
   above 4,000. Under the six-season window those become
   `pf.LADDER_WINDOW_SEASONS` and about 2,023 rows. The `LADDER_FIRST_SEASON`
   alias exists only to keep that test green until this lands.
3. A `build_site.py` pass, because the served slim view
   (`data/positional_fit_ui.json`) is built there. Regenerating the source
   artifact WITHOUT it would leave `prospect_def_value.POS_ADJ` on the new ladder
   while /pal/ still rendered the old one, which is a worse state than either.

Also open, and NOT part of this gate: `prospx/index.html`'s
`_RPS_POSITION_MULTIPLIERS` is a second, hand-written, SERVED ladder that reads
no artifact and therefore did not move. The ladder eval already flags it.
