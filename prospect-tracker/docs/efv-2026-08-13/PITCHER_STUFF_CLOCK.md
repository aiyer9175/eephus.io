# P-0: why the pitcher stuff feature is still untrainable, and exactly what unblocks it

Measured 2026-08-13 against the live matrices. Program:
`docs/master-plan-2026-08-13-efv-accuracy.md`, owner decision 1 (pitcher drivers).

## The short version

The stuff feature is not blocked by missing data, by the model, or by a verdict.
It is blocked by a one-year label-window bound, and that bound is correct. It
lifts on its own the moment `RESOLVED_THROUGH` advances to 2026.

## What the earlier gate actually said

`data/xfv_pitcher_stuff_eval.json` (2026-07-15) reports `overall_verdict: FAIL`
with all three ship conditions at **delta exactly 0.0**. That is not a
measurement of stuff being useless. Its own `trainable_coverage` block says why:

    train_covered_rows_all_folds: 0
    test_covered_rows_all_folds:  0
    trainable: false

With zero covered training rows every arm is identical to the baseline BY
CONSTRUCTION, so the three zeros are arithmetic, not evidence. Anyone reading the
verdict without that block would record "stuff does not help" as a result. It is
not one, and `test_pitcher_stuff_clock.py` now pins the gate to keep saying so.

## Why coverage is zero, measured rather than assumed

AAA pitch tracking begins in 2023, so strict pre-decision coverage is zero for
every cohort through 2023 and first appears afterwards. From the artifact's own
`future_coverage`, and confirmed against the matrix:

| debut cohort | pitcher rows in matrix | strict pre-decision stuff coverage |
| --- | --- | --- |
| 2022 | 221 | 0 |
| 2023 | 249 | 0 |
| 2024 | 256 | 46 to 48 |
| 2025 | **0** | 64 (would be, if the cohort existed in the matrix) |

A feature reaches the model only through TRAINING rows. Training for test year Y
is `decision_year < Y`. So:

- test year 2024 trains on 2023 and earlier: **zero covered rows**, which is
  today's state and why every delta is 0.0.
- test year 2025 trains on 2024: **48 covered rows**, the first fold that can
  train on the feature at all.

## The bound that removes the 2025 fold

    efv_dataset.RESOLVED_THROUGH = 2025
    efv_dataset.DEBUT_YEARS      = 2011 .. 2024

The pitcher matrix holds **256 rows at decision year 2024 and zero debuted rows
at 2025**. The 16 rows that do sit at 2025 are all busts and all `bust_recent`,
so `_prep` drops every one and the fold table steps straight from 2024 to 2027.

This is NOT missing data. `debuts.json` already carries **243 debuts from 2025**
and 208 from 2026. They are excluded by the window bound alone.

## The bound is right, and should not be moved early

Stopping one year short of `RESOLVED_THROUGH` guarantees every admitted cohort
has at least TWO observed seasons:

| debut | observed seasons | label weight |
| --- | --- | --- |
| 2023 | 3 | 0.500 |
| 2024 | 2 | 0.333 |
| 2025 | 1 | 0.167 |

Admitting 2025 today would project a six-season target off a SINGLE observed
season at weight 1/6. `_label_6yr` is a flat-rate tail projection, and the
censoring work has already measured it as materially biased at low observed
counts (hit -1.691 at two observed seasons, decaying to null by five). One
observed season is the worst regime it has, and the 2025 rows would be both the
new training rows AND the new test rows for the fold in question. Buying one thin
fold at that price would produce a null driven by label noise and then invite
someone to record it as a verdict on stuff.

**So the recommendation is to wait, and the waiting is short.**

## The unlock, stated as a checkable condition

When the 2026 season completes and `RESOLVED_THROUGH` moves to 2026:

1. `DEBUT_YEARS` now extends to 2025 **automatically**. As of 2026-08-13 it is
   derived (`tuple(range(2011, RESOLVED_THROUGH))`) rather than the literal
   `range(2011, 2025)` it used to be. The two were byte-identical, so the change
   is a no-op today; its purpose is that the unlock cannot be missed.
2. The 2025 cohort enters with two observed seasons, matching the weakest label
   already admitted rather than introducing a worse one.
3. `SCORED_YEARS` may extend to 2025, which is the first fold that trains on
   stuff-covered rows.
4. The gate at `tools/efv_pitcher_stuff_lab.py` becomes runnable for the first
   time instead of structurally untrainable.

Extending `SCORED_YEARS` remains a FRAME CHANGE: every floor in the program is
measured on the current fold set, so the whole floor battery is re-derived in the
same run, per the standing rule that a fresh delta is never read against a stored
constant.

## Power, stated in advance so nobody is surprised

Even after the unlock the first fold is thin: roughly 48 covered training rows
and a test cohort whose labels carry two observed seasons. This is a lane that
starts a clock rather than settling a question. The honest first outcome is
plausibly a null with a TOST bound, and it should be pre-registered that way, so
that a null is recorded as "still underpowered" and not as "stuff does not
predict".

## What was changed today

- `DEBUT_YEARS` derived from `RESOLVED_THROUGH`; byte-identical output, verified.
- `test_pitcher_stuff_clock.py`: four pins, mutation-proved by making
  `DEBUT_YEARS` reach `RESOLVED_THROUGH`, which fails two of them.
- No model, no feature, no served grade touched.
