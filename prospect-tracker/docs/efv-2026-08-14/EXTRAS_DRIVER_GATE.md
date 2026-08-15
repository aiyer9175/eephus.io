# EXTRAS DRIVER GATE (Lane D-2, 2026-08-14)

Pre-registered 2026-08-14, committed ALONE with the Results section EMPTY so git
timestamps it, BEFORE any arm is run. Clauses are frozen from this commit. No
clause is amended after it answers.

The coverage census this gate is built on was committed FIRST, in `d99a6591`,
ledger `data/xfv_driver_extras_census.json`, so the frame was fixed before the
clauses were written and neither can be tuned to the other.

Lab: `tools/efv_driver_lab.py` (reused; verified bit-parity with `_run_eval`).
Ledger: `data/xfv_driver_extras.json`, outside the `data/*_eval*.json` glob.

---

## WHY THIS LANE EXISTS

D-1 closed the free-keys frontier: 26 arms, zero survivors, and its stop clause
3 fixed the reopen burden as **new DATA**. `snapshots.tools_json._extras` is the
only large, historically deep source this model has never read.
`efv_dataset._prior_features:464-496` takes `tools_consensus` and
`per_source[s].fv_published` and nothing else.

## THE CENSUS REDESIGNED THIS LANE BEFORE IT RAN

**Pre-decision coverage is EXACTLY 0.000 for decision years 2011 through 2016**
and then 0.50 rising to 0.97 from 2017. FanGraphs `tools_json` starts 2017.

**So "has a pre-decision snapshot" is an ERA INDICATOR, not a coverage flag.**

| side | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hit train covered | **0** | **0** | **0** | **0** | 24 | 53 | 116 | 173 | 241 | 363 | 453 |
| pit train covered | **0** | **0** | **0** | **0** | 15 | 53 | 122 | 219 | 321 | 417 | 541 |

**FOUR OF ELEVEN FOLDS HAVE ZERO TRAINABLE COVERAGE ON BOTH SIDES.** In those
folds the candidate column is entirely imputed in training, the ridge cannot fit
a weight to it, and the arm is identical to the baseline BY CONSTRUCTION. Pooling
them in would drag the statistic toward zero mechanically. **That is precisely
how the registered pitcher-stuff gate came to report delta EXACTLY 0.0 on all
three ship conditions, a number a reader could have logged as "stuff does not
predict".** This gate refuses to repeat it.

## C0 THE FRAME, FIXED HERE (blocking)

- **Scored years are restricted to 2019 through 2024**, the folds with at least
  40 covered training rows on both sides. Six folds, not eleven.
- **The floor is re-derived ON THAT REDUCED FOLD SET.** The 11-fold feature-add
  floors (hit 0.0194 / pit 0.0172, `data/xfv_driver_floors.json`) are forbidden
  here BY NAME: fewer folds and fewer rows is a different variance, and gating a
  6-fold delta on an 11-fold floor is the same class of error as G2 importing a
  refit floor into a same-fit contrast.
- Every arm reports its own per-fold trainable coverage in the ledger. **A gate
  that cannot show its coverage may not report a null.**

## C1 A MISSINGNESS INDICATOR IS INADMISSIBLE

Not merely weak. `has_predecision_snapshot` is a near-deterministic function of
`decision_year >= 2017`, so it encodes the fold index. Measured, and it is
outcome-related in the counterintuitive direction: uncovered rows realize MORE
WAR (hit +4.274 against +3.882; pit +2.483 against +1.989), which is the era
confound and not talent.

**No arm in this lane may include a missingness indicator, and imputation is
`zero` with the imputed share reported per arm.** Any candidate whose measured
effect survives only when a missingness column is present is reported as an era
artifact rather than a driver.

## C2 THE CANDIDATES

Ordered by census coverage on the reduced frame. `present` is the headline.

| arm | side | coverage | note |
| --- | --- | --- | --- |
| `tool_gap` = mean(future - present) over the side's tools | both | hit 0.631 / pit 0.654 | **THE HEADLINE. Entirely unmodelled today.** mean +4.19 / +3.47, sd 2.61 / 2.40, so a real varying quantity |
| `risk` (ordinal) | both | 0.589 / 0.630 | an explicit scout variance signal |
| `sits` (fastball band) | pit | 0.590 | **a pre-Statcast stuff proxy back to 2017**, the only pitcher-stuff route that does not wait for the 2027 clock |
| `tops` | pit | 0.590 | peak velo |
| `rpm_fb` | pit | 0.509 | spin; ~13% are literal 0 and those rows are treated as MISSING, not as zero spin |
| `height`, `weight` | both | 0.638 / 0.668 | no anthro feature exists today |
| `eta_year` minus decision year | both | 0.639 / 0.668 | scout proximity |

Hitter `sits`/`tops` are 0.000 by census and are NOT arms: velocity is a pitcher
attribute and its absence on hitters is correct, not missing data.

## C3 THE PROTOCOL, UNCHANGED FROM D-1

`EFV_GATE_STANDARD.md` section 2, all four mandatory: paired bootstrap
resampling train AND test with refit per draw; a row-permuted zero-information
control KEPT in the result set; a permutation null band; and at least 4
independent time splits, which the six admissible folds supply. Both instruments
(pooled rho and block-rho) reported for every arm. B=2000, seed in the ledger.

## C4 MULTIPLICITY

Roughly 11 arms across both sides. **Holm across the whole family, both sides
pooled into one family**, exactly as D-1.

## C5 SHIP CONDITIONS (all required)

1. Positive on BOTH instruments.
2. Delta >= its own floor, re-derived on the six-fold frame.
3. Survives Holm.
4. Beats its zero-information twin by more than the noise band.
5. Wins in >= 4 of the 6 folds.
6. **Coverage-honest**: the arm's per-fold trainable coverage is >= 40 in every
   scored fold, so no fold contributes a by-construction zero.

## STOP CLAUSES

1. C0 fails, or a floor cannot be derived on the reduced frame -> BLOCKED.
2. If the zero-information control matches the best candidate, the sweep is
   UNINFORMATIVE for that side and nothing is promoted.
3. **A null here does NOT license widening the frame back to 11 folds to find a
   number.** The frame is fixed by coverage, not by what it returns.
4. **Nothing ships from this lane.** A surviving arm earns a SEPARATE,
   separately-gated feature-add epoch with the full serve-path checklist,
   because adding a column to `_FEATURES_*` moves every served grade.

## RESULT (appended after the run)

*(empty at pre-registration)*
