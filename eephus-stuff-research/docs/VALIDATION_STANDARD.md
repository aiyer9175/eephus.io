# Validation Standard

This document is the operational companion to `STATISTICAL_GOVERNANCE.md`
Layer 2 — it says *how* validation is implemented in this repository, not
just what's required conceptually.

## Test taxonomy (Part AA)

Six distinct, separately-run test classes. Do not mix them into one
undifferentiated suite — each answers a different question and a reviewer
should be able to run just one class to answer just that question.

| Directory | Question it answers |
|---|---|
| `tests/unit/` | Do small functions/transformations do what their contract says? |
| `tests/invariants/` | Do mathematical identities and conservation rules hold? |
| `tests/regression/` | Has a previously verified output silently changed? |
| `tests/integration/` | Do multiple pipeline components work correctly together? |
| `tests/statistical/` | Do estimator properties, simulation recovery, and calibration hold? |
| `tests/certification/` | Do the high-level gates required before promotion pass? |

## Tests of failure (Part AB)

A system is not robust merely because valid inputs pass. Every module that
accepts external data must have tests proving it *fails correctly* on bad
input, not just tests proving it succeeds on good input. At minimum, the
fixtures in `tests/fixtures/bad/` cover: duplicate identifiers, missing
required columns, impossible physical values, malformed season identifiers,
a leakage field present where it shouldn't be, empty training data,
train/validation overlap, an unknown pitch classification code, and NaN
contamination in a target column. See `tests/certification/test_deliberate_
failures.py` for the harness that runs all of them and asserts each one
fails for the *right* reason (not just "raises some exception").

## Property-based testing (Part AC)

Use `hypothesis` where a property should hold across a wide input space
rather than at a handful of hand-picked examples:

- Row-ordering should not change a permutation-invariant aggregate.
- Adding an irrelevant column should not change a result that doesn't
  depend on it.
- Splitting a dataset and recombining it should preserve additive totals.
- A deterministic function should remain deterministic under re-invocation.
- Schema-preserving row permutations should not alter permutation-invariant
  quantities.

See `tests/invariants/test_permutation_invariance.py` for the reusable
Hypothesis strategies this program built for dataframe permutation testing.

## Simulation harness (Part AD)

`src/eephus_research/statistics/simulation.py` generates synthetic data with
a known data-generating process, so future estimators can be checked against
ground truth before being trusted on observational data. It supports
varying: true effect (zero / positive / negative), noise level, sample size,
clustering strength, missingness, pitcher heterogeneity, and feature
correlation. A method that cannot recover a known simulated truth under
these variations should not be trusted on real baseball data — this is a
precondition for Layer 2 certification of any estimator, not an optional
nicety.

## Split validation (Part AF)

See `STATISTICAL_GOVERNANCE.md`'s train/validation/test contract section.
The four/five split regimes (`RANDOM_ROW`, `GAME_GROUPED`,
`PITCHER_GROUPED`, `TEMPORAL`, `PITCHER_GROUPED_TEMPORAL`) are implemented
in `src/eephus_research/diagnostics/splits.py`; `tests/statistical/
test_splits.py` proves each one actually enforces the grouping/temporal
ordering it claims to (e.g. that `PITCHER_GROUPED` never puts the same
pitcher ID in both train and test).

## Negative controls (Part AJ)

Infrastructure for negative-control testing lives in
`src/eephus_research/diagnostics/negative_controls.py`: shuffled targets,
permuted pitcher identities, irrelevant features, deliberately
future-inappropriate features (to prove the leakage detector catches them),
and pseudo-outcomes that should not be predictable. A future model should
beat these controls by a documented, non-trivial margin — "did not check"
is not the same as "passed."

## Ablation framework (Part AK)

Feature-family ablation is supported via a family-tagging convention in
`src/eephus_research/validation/feature_families.py` — conceptual families
(`VELOCITY, MOVEMENT, RELEASE, SPIN, LOCATION, COUNT, SEQUENCE, ARSENAL,
PITCHER_IDENTITY, CONTEXT`) are declared, not decided, by this program.
Which families actually belong in a future Stuff model is explicitly out of
scope here — this only makes it mechanically possible to remove one family
at a time and re-measure later.

## Reliability framework (Part AM)

`src/eephus_research/statistics/reliability.py` provides split-half
reliability, year-to-year reliability, and empirical-Bayes shrinkage
utilities, parameterized by exposure (pitch count, PA count, game count) so
future work can build stabilization curves rather than assume a fixed
sample-size cutoff. No specific reliability estimator is endorsed by this
program — infrastructure only, per Part AM.

## Calibration framework (Part AN)

`src/eephus_research/diagnostics/calibration.py` computes predicted-vs-
observed calibration curves, calibration slope, and calibration intercept,
with support for grouped (by level, by season) and temporal calibration.
Predictive performance and calibration are different questions — do not
infer model quality from correlation/discrimination alone.

## Metric registry (Part AO)

`registry/experiments/` entries require declaring exactly one primary
metric, a list of secondary metrics, and a list of diagnostic metrics, drawn
from a fixed vocabulary (`RMSE, MAE, LOG_LOSS, BRIER, AUC, R2, SPEARMAN_R,
PEARSON_R, CALIBRATION_SLOPE`, extensible only by adding to
`schemas/experiment.schema.json`). This exists to prevent metric shopping —
picking whichever metric looks best after the fact.
