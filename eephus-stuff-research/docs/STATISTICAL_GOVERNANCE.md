# Statistical Governance

## Ten questions before any inferential analysis

Before running any inferential analysis, a preregistered experiment
(`registry/experiments/`) must give explicit answers to:

1. What is the population?
2. What is the observational unit?
3. What is the estimand?
4. Which observations are dependent on each other?
5. What creates repeated measures (same pitcher, same game, same season)?
6. What is the clustering structure?
7. What uncertainty quantity is actually meaningful for this question?
8. Is the objective descriptive, predictive, causal, or measurement-oriented?
9. What is the validation population, and does it match the population the
   claim will be made about?
10. What constitutes generalization here — same pitchers unseen data,
    unseen pitchers same level, unseen pitchers unseen level, or a future
    season entirely?

An experiment entry that leaves any of these `NOT_MEASURED` may still run as
exploratory work, but its conclusions cannot be certified past Layer 2 (see
`RESEARCH_CONSTITUTION.md`) until they're answered.

## Sample size discipline (Part W)

Never report only a pitch count when the effective inferential sample
involves pitchers, pitcher-seasons, games, teams, parks, or seasons. Reports
must identify counts at every relevant grain, e.g.:

```
Pitches:          412,880
Plate appearances:  98,214
Games:               3,190
Pitchers:              841
Pitcher-seasons:       912
Seasons:                 3
```

Millions of pitches are not millions of independent experimental units.

## Clustering and repeated measures (Part X)

Explicitly evaluate dependence induced by: multiple pitches within a plate
appearance, multiple plate appearances within a game, repeated games by the
same pitcher, repeated seasons by the same pitcher, pitch types nested
within pitchers, parks, teams, and opponents. Do not default to an IID
assumption without stating why it's defensible for the specific question
being asked — it rarely is, at the pitch level.

## Uncertainty (Part Y)

Every consequential empirical result gets an uncertainty treatment matched
to its estimand: analytical standard errors, cluster-robust standard errors,
bootstrap, cluster bootstrap, Bayesian posterior intervals, or repeated
out-of-sample evaluation. The choice must be justified in the experiment
entry. Do not mechanically bootstrap individual pitches when the scientific
unit of variation is pitchers — see
`src/eephus_research/statistics/clustering.py` for the cluster-aware
resampling helper this program built specifically to make the naive,
wrong version harder to reach for by accident.

## Determinism and randomness (Part Z)

Seeds are centralized: `config/research.yaml`'s `seed.default` and
`pyproject.toml`'s `[tool.eephus_research].default_seed` must agree (a
regression test checks this — `tests/regression/test_seed_consistency.py`).
Every experiment registers its own seed explicitly in
`registry/experiments/`; the central default is a fallback for exploratory
work only, never load-bearing for a certified result. Where an algorithm
remains nondeterministic despite a fixed seed (e.g. some parallelized
reductions), document that limitation next to the result — do not claim
determinism you haven't verified. Prefer deterministic transformations
wherever there's no scientific reason for randomness.

## Train/validation/test contract (Part AF, AG, AH)

No future model may declare success from a random row split alone. This
repository's split-validation tooling
(`src/eephus_research/diagnostics/splits.py`) supports, at minimum:

```
RANDOM_ROW  GAME_GROUPED  PITCHER_GROUPED  TEMPORAL
PITCHER_GROUPED_TEMPORAL
```

The strictest generalization claim made about a result must correspond to
the strictest relevant validation design actually used — a model validated
only with `RANDOM_ROW` cannot be described as generalizing to unseen
pitchers.

Any learned transformation (mean/SD for standardization, imputation values,
PCA, embeddings, categorical encoders, feature selection, hyperparameter
tuning, target encoding, calibration) must be **fit on training data only**.
`src/eephus_research/validation/fit_transform.py` provides a `FitOnTrain`
wrapper that raises if `.transform()` is called before `.fit()` was called
on a disjoint training split, specifically to make accidental full-dataset
fitting hard to do by accident.

Hyperparameter selection happens inside the training regime, never against
the final holdout. Where relevant, maintain a conceptual three-way split —
`TRAIN`, `TUNE`, `FINAL_HOLDOUT` — and leave the final holdout untouched
until candidate selection is frozen, recorded as such in the experiment
entry.

## Leakage audit (Part AE)

`src/eephus_research/diagnostics/leakage.py` implements a reusable leakage
checker. Future models must be run through it before any claim about
predictive performance is made, checking for: exact target leakage, proxy
target leakage, future information, post-outcome features, normalization
fitted using validation data, player-identity leakage, duplicate rows across
folds, game overlap across folds, pitcher overlap across folds, and
target-derived pitch classifications. It returns explicit findings — it does
not silently pass.

## Effect size vs. statistical significance (Part AP)

Reports must separate effect size, uncertainty, statistical detectability,
and practical/baseball relevance as distinct statements. A tiny effect with
narrow uncertainty is not automatically important. A useful effect with
broad uncertainty is not automatically absent.

## Multiple testing (Part AQ)

When many hypotheses are evaluated, the multiple-comparison problem must be
named, not silently corrected for with one universal method or silently
ignored. Distinguish confirmatory tests (preregistered, drives the headline
claim), secondary tests (preregistered, supporting), and exploratory tests
(not preregistered, hypothesis-generating only) — visibly, in the report.

## Sensitivity analysis and the robustness matrix (Part AR, AS)

Major claims should be tested under plausible alternative choices —
minimum pitch threshold, season inclusion, pitch classification mapping,
outlier handling, normalization, weighting, cluster level, target variant —
predefined where possible, not turned into unlimited post hoc specification
searching. The standard output is a robustness matrix: claims as rows,
alternate specifications as columns, `+`/`0`/`-` cells showing whether the
claim holds, is neutral, or reverses under each alternative.

## Falsification-first standard (Part AT)

Every important model claim requires a stated answer to: *what observation
would convince us this claim is wrong?* A claim without a meaningful
falsification condition gets the status `NOT_FALSIFIABLE_AS_SPECIFIED` until
that's fixed — it is not certified in that state, regardless of how good it
looks empirically.

## Competing explanations (Part AU)

Whenever a model appears predictive, alternative explanations must be
actively checked, not just left unmentioned: pitcher identity, velocity
alone, role, pitch type, arsenal, platoon usage, selection effects,
survivorship, pitch classification, command/location, count leverage.
Predictive success is not proof of the preferred mechanism.

## Interpretation ladder (Part AV)

```
OBSERVED
ASSOCIATED
PREDICTIVE_IN_SAMPLE
PREDICTIVE_OUT_OF_SAMPLE
TEMPORALLY_TRANSPORTABLE
PLAYER_TRANSPORTABLE
MEASUREMENT_VALIDATED
CAUSALLY_IDENTIFIED
```

Never jump levels. "Predictive on known pitchers" does not establish
"transportable to unseen pitchers" — those are two different rungs and
require two different validation designs to claim.

## Identity-reconstruction audit (Part AL)

`src/eephus_research/diagnostics/identity_audit.py` is the dedicated hook
for the mandatory future audit: whether a supposedly pitch-quality model is
primarily reconstructing pitcher identity rather than measuring anything
about the pitch. It supports feature→pitcher-ID prediction, score→pitcher-ID
prediction, pitcher-ID→score prediction, within-pitcher vs. between-pitcher
variance decomposition, known-pitcher vs. unseen-pitcher validation,
identity-ablation tests, and pitcher-label permutation tests. This audit is
**mandatory**, not an optional sensitivity check, for any future
pitch-quality model — see `docs/CERTIFICATION_STANDARD.md`, gate `P0-23` and
its successor gate in the next program's certification standard.
