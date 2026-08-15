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

Run 2026-08-14, `tools/efv_driver_lab.py extras 2000`, 641 s. Ledger
`data/xfv_driver_extras.json`. 13 arms, 0 skipped. No clause amended.

### C0: THE SIX-FOLD FLOOR, AND RESTRICTING THE FRAME COST NOTHING

| side | six-fold floor (2019-2024) | 11-fold floor | change |
| --- | --- | --- | --- |
| hit | **0.0161** | 0.0194 | -17% |
| pit | **0.0142** | 0.0172 | -17% |

**The reduced frame is BETTER powered, not worse**, which was not the reason for
choosing it. Fewer folds but larger, more stable training sets: a noise column
perturbs a 754-row training frame less than a 90-row one. So the frame
restriction that C0 imposed for correctness also bought about 17% more
resolution, and the 11-fold floor would have been the CONSERVATIVE choice rather
than the permissive one. Recorded because it is the opposite of what a reader
would assume when they see "we dropped nearly half the folds".

### THE VERDICT: 13 ARMS, ZERO SURVIVORS

| arm | d_rho | x floor | d_block | control | folds | Holm |
| --- | --- | --- | --- | --- | --- | --- |
| pit.height_in | +0.00302 | **0.213x** | +0.00022 | -0.00241 | 4/6 | no |
| pit.weight | +0.00258 | 0.182x | -0.00038 | -0.00205 | 3/6 | no |
| **hit.tool_gap** | **+0.00087** | **0.054x** | -0.00054 | -0.00073 | 3/6 | no |
| **pit.tool_gap** | **-0.00012** | -0.008x | -0.00522 | +0.00256 | 4/6 | no |
| hit.eta_delta | -0.00051 | -0.032x | -0.00239 | -0.00378 | 0/6 | no |
| hit.weight | -0.00076 | -0.047x | -0.00137 | -0.00180 | 2/6 | no |
| hit.height_in | -0.00093 | -0.058x | -0.00125 | -0.00778 | 2/6 | no |
| hit.risk_ord | -0.00317 | -0.197x | -0.00864 | -0.00045 | 0/6 | no |
| pit.eta_delta | -0.00546 | -0.385x | +0.00245 | +0.00268 | 5/6 | no |
| pit.rpm_fb | -0.00567 | -0.399x | -0.00174 | -0.00098 | 2/6 | no |
| pit.tops | -0.00645 | -0.454x | -0.00146 | +0.00400 | 2/6 | no |
| pit.sits_mid | -0.00648 | -0.456x | -0.00154 | -0.00444 | 2/6 | no |
| pit.risk_ord | -0.01510 | **-1.063x** | +0.00330 | -0.00555 | 4/6 | no |

**Not one arm clears C5.** The best reaches 0.213x. **None survives Holm** (best
p 0.408). Only two arms are positive on BOTH instruments and both are anthro.

### THE HEADLINE CANDIDATE IS FLAT, AND THAT IS THE FINDING

**`tool_gap` reads +0.00087 on hitters (0.054x) and -0.00012 on pitchers.** Both
are within a thousandth of zero.

This was the best-motivated candidate in the entire programme: entirely
unmodelled, 0.631 / 0.654 coverage, a real spread (mean +4.19 / +3.47 grade
points, sd 2.61 / 2.40), and an obvious mechanism, since how much growth a scout
projects ought to say something about who grows. **It says nothing.** The future
grade already carries whatever the present-future difference could have added,
which is consistent with `fv` being the dominant feature at weight 3.428 / 1.692.

### THE PRE-STATCAST STUFF PROXIES ALL FAIL, WHICH ANSWERS A STANDING HOPE

`pit.sits_mid` -0.00648, `pit.tops` -0.00645, `pit.rpm_fb` -0.00567, all
NEGATIVE, all winning 2 of 6 folds. These were the one route to pitcher stuff
that does not wait for `DEBUT_YEARS` to reach 2026. **That route is closed on
this evidence**, and the aStuff+ clock remains the only live path.

### THE ONLY ARM THAT EXCEEDS ITS FLOOR IS NEGATIVE

`pit.risk_ord` reads **-0.01510 against a 0.0142 floor, 1.063x, in the WRONG
DIRECTION**. The gate is one-sided so this is not a ship, and with 13 arms one
excursion past a floor is unremarkable. It is reported rather than dropped
because a lane that only reports its positive excursions is not measuring.
Read at most as: the scout risk ordinal does not help the pitcher model and may
cost it. Not adjudicated as harm; a directional finding on one arm.

### WHAT THIS CLOSES

Per stop clause 3 the frame is NOT widened back to eleven folds. Per stop clause
4 nothing ships. With D-1's 26 arms, **39 gated feature arms across the two
lanes have now returned zero survivors**, on the free columns and on the one
large historically deep source the model had never read.

**The eFV driver frontier is closed on features.** The remaining constraint is
the LABEL POOL, not the feature set: `RESOLVED_THROUGH` advancing to 2026
admits the 2025 cohort and is the only mechanism left that adds information.
