# Pace from entry: pre-registered gate

Status (updated 2026-08-04): **MEASURED. NO-SHIP. ARM CLOSED ON ITS OWN
PRE-REGISTERED KILL CRITERION.** Flag `efv_model.PACE_FROM_ENTRY` stays False.
Columns are still emitted unconditionally by `efv_dataset._pace_from_entry` and
still feed nothing. Result artifact: `data/xfv_pace_entry_eval.json`; writeup in
`docs/EXECUTION_2026-08-04-eight-asks.md`.

The original status line, kept for the record: *"COLUMNS BUILT, FLAG DEFAULT
OFF, NOT YET MEASURED."*

**What fired.** The hitter arm fits a NEGATIVE weight on pace (-0.0419, negative
in 3 of 4 folds). That exact sign was named in advance, below, as the
survivorship-censoring artifact, so the arm closes and must not ship as "DSL
starters are worse". Permutation p=0.71 hit / 0.94 pit. The "fuller" triple
variant is a RESOLVED HARM (CI95 excludes zero), not a null, so it must not come
back as the richer spec. Coverage was not the limiter: ~80% of eval rows are
non-censored. See also the correction under "Second arm worth running" below,
whose premise did not survive measurement.

## The complaint

Owner, 2026-07-31: Franklin Arias and Josue de Paula are punished in their eFV
grade for "seasons to reach level" when they climbed from the DSL. Going
DSL -> AA covers twice the ladder a college draftee assigned to Single-A covers,
and should not read as slower.

## What is actually true (measured, and it is NOT the whole complaint)

`n_milb_seasons` is a real suppressor with a defensible sign: holding
`level_rank` and age fixed, more seasons IS more seasons spent reaching the same
rung. Its served hitter weight is -0.2239 (mu 1.49, sd 1.86), about -0.120 WAR6
per extra season.

But the model has **no entry-level term that works**. `_LEVEL_RANK` puts DSL at
0, and the only acquisition-pathway machinery is the `is_ifa` dummy, which fits
**-0.0010 (inert)** while `is_college` fits +0.2576. So a DSL entrant carries
extra counted seasons with nothing crediting the extra rungs.

Per-player contributions (production refit on the live matrix, WAR6 units):

| | arias | de_paula |
|---|---|---|
| `n_milb_seasons` | -0.302 | -0.422 |
| `age_rel_level` | +0.274 | +0.205 |
| `age` | +0.094 | +0.067 |
| **net pace+age** | **+0.066** | **-0.150** |
| headline if n_milb_seasons were 2 | +0.26 FV | +0.35 FV |

**So the penalty is real but small, and for Arias it is fully offset.** Both
still grade ABOVE consensus (+2.2 and +1.9). The louder half of the complaint is
narration: the chip prints the raw -0.30 contribution undiscounted by
calibration (b=1.042) and the blend (lambda 0.70), and it fires DOWN on 99.8% of
live hitter cards.

## What shipped WITHOUT a gate (display only)

`efv_score._relabel_pace_factor` renames the chip to "Seasons used (fast riser
from a low start)" when the player's own ladder says he is climbing at least one
rung per season. Direction and magnitude are the model's and are untouched; only
the label changes. No grade, rank or dollar moves.

## The columns

`efv_dataset._pace_from_entry(seasons, final)` -> three keys, `seasons` newest-first:

- `entry_level_rank` - the rung of the first observed pro season.
- `pace_from_entry` - `(current_rank - entry_rank) / seasons_elapsed`, 0.0 when
  the span is 0.
- `entry_observed` - 0.0 when the first observed season is at the 2015 StatsAPI
  coverage floor, i.e. the true entry may be left-censored and the pace is a
  lower bound. Borrowed from advancement_pace's own 2014 left-censor guard.

Verified values: arias **1.33**, de_paula **1.00**, college bat at AA in year two
**2.00**, a three-year AA repeater **0.00**.

Coverage: the milb block is present on 925/1927 labeled hitter rows (48.0%) and
942/2064 pitcher rows (45.6%); of those ~88-89% have an observable (non-censored)
entry, so roughly **42% of labeled rows carry a real value** and the rest impute
neutral behind `milb_missing`. That is the same support the shipped milb block
already lives with.

## PRE-REGISTERED EXPECTED FAILURE

This feature family has inverted on the hitter side three times:

| feature | marginal | conditional | verdict |
|---|---|---|---|
| `n_milb_seasons` | +0.095 | **-0.23** | shipped, sign is the conditional one |
| `seasons_at_level` (hit) | - | **+0.0945** | NO-SHIP, permutation p=0.375 |
| `age_rel_level` (pit) | - | **+0.0418** | declaration moved to 0 |

Mechanism: the training pool is survivorship-censored to players who DEBUTED, so
"moved slowly and is still on the board" selects for players the system kept.
**If the hitter arm fits a negative weight on pace (fast movers score worse),
that is the censoring artifact and the arm CLOSES.** It must not ship as "DSL
starters are worse". Recording this before the measurement so the result cannot
be reinterpreted after it.

## Gate to run

1. Forward-chained pooled blend Spearman, both sides, against MDE95 floors
   **0.017 hit / 0.016 pit**.
2. Zero-information control: the same column row-permuted, kept IN the feature
   set (the B3/E1 control shape).
3. Feature-specific permutation null, 30 draws from the true marginal with the
   row link broken - the bar `seasons_at_level` cleared at p=0.032.
4. Paired bootstrap B=2000.
5. Sign check against the pre-registration above.

Harness cost is small: `efv_model.run(persist=False, side=...)` is ~34s hit /
~7s pit and a matrix rebuild is ~3-4s per side. **Matrices are gitignored - back
them up first and verify the restore (arias ops_rel 0.24769633507853406, level
AA), and `git checkout` the two tracked `*_dataset_report.json` files after.**

## Second arm worth running (possibly the better one)

> **CORRECTION 2026-08-04: the claim in this section DOES NOT REPRODUCE. The
> original text is kept below, unedited, because it was part of the stated
> motivation and the record should show what was believed at the time.**
>
> Measured on the live matrices under four plausible specifications of "the
> `efv_ungraded` set" - {production-bearing rows, all labeled rows} x {pace
> alone, the full triple} - `pace_from_entry` fits **POSITIVE in every one**, on
> both sides:
>
> | spec | hit | pit |
> |---|---|---|
> | production_bearing / single (n 907 / 919) | +0.1879 | +0.1559 |
> | production_bearing / triple | +0.3440 | +0.2708 |
> | all_labeled_rows / single (n 1927 / 2064) | +0.0993 | +0.0751 |
> | all_labeled_rows / triple | -0.0559 | +0.1401 |
>
> Nothing near -0.5943. The nearest match in any of those fits is
> `entry_observed`, the left-censoring indicator (-0.4263 hit / -0.4462 pit
> production-bearing triple, -0.5329 hit all-labeled triple), which is a
> different column. The -0.5943 also appears verbatim in `efv_model.py` as
> `age_rel_level`'s `efv_ungraded` **pitcher** weight, so the likeliest story is
> a column mix-up when this section was written, not a since-drifted fit.
>
> The arm was run anyway rather than dropped on the bad premise, and is reported
> on its own OOS numbers. It lost: deltas vs base are negative on both sides
> (pit -0.0363 low-minors / -0.0046 all-levels), inside zero-information control
> range. Reconciliation block:
> `data/xfv_pace_entry_eval.json -> sides.{hit,pit}.doc_claim_reconciliation`.
>
> **The arm did not close because of this number.** It closed on the
> pre-registered kill criterion in the section above (negative hitter pace
> weight = the censoring artifact). The correction removes a motivation, not the
> verdict.

*Original text, superseded:*

The same column fits **-0.5943 in the `efv_ungraded` provisional set**, which has
no `fv` anchor, against ~0 in the anchored flagship. Where scouts have already
priced the pace, the model learns nothing; where they have not, it may be the
whole signal. If the flagship arm nulls, run `efv_ungraded` before closing.

## Relationship to AP+

AP+ (`advancement_pace_export.py`) is the same idea done properly: peer baseline
with fixed effects per (starting_level x experience_year) plus entry-age, era,
position-group and pathway dummies. It rates arias **112.4 (91st percentile)**
and de_paula **108.4** - it agrees with the owner and against `n_milb_seasons`.

It is NOT used here. AP+ is hitters-only, and its served artifact is
latest-as-of-2026, so joining it to historical training rows leaks. This column
is computed from the same StatsAPI substrate, as-of by construction, and works
for pitchers. See the contract note in `advancement_pace_export.py`.

Descriptive correlations on today's board (nothing fed anywhere):
AP+ vs `xfv_grade` +0.190, vs `xfv_minus_consensus` +0.107 (eFV's adjustment
already leans AP+'s way), vs `n_milb_seasons` only **-0.117** (they are NOT the
same signal), vs `age_rel_level` -0.348 (the main overlap channel).
