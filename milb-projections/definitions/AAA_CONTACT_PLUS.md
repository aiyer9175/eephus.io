# AAA Contact Management+

## What it is

The AAA-level contact/HR-suppression component feeding into AAA pitcher eWAR's `contact_runs_above_average`, `hr_opportunity_runs`, `hr_conversion_runs` columns. It is **not** the same system as the hitter-side `~/contact_plus` package (`Contact+`) — different subject (pitcher batted-ball-damage suppression vs. batter contact skill), different estimand, zero code-level relationship (no cross-references found in either directory).

## Why the name collision matters

"AAA Contact+" and hitter "Contact+" are easy to confuse. This package always refers to the pitcher-side component as **AAA Contact Management+** to avoid that.

## Source and output

Intermediate artifact: `aaa_contact_runs.parquet` (3,730 rows). Confirmed live columns: `pitcher, season, contact_runs_above_average, n_bip`. Grain: pitcher × season, AAA only, 2023+ coverage (batted-ball data doesn't exist at AAA before 2023 in this pipeline; 2021-2022 AAA rows are `coverage_level == "fi_only"` in the parent `aaa_pitcher_ewar.parquet`, with `contact` listed in `missing_components`, never zero-imputed).

## Relationship to the published AAA pitcher eWAR schema

This intermediate output is folded into `aaa_pitcher_ewar.parquet`'s `contact_runs_above_average`, `hr_opportunity_runs`, `hr_conversion_runs` columns — see `definitions/MILB_PITCHER_PROJECTION.md`. Exported here as a standalone component for incremental-value testing (so the future builder can measure the marginal effect of contact-management skill separately from the aggregate eWAR number), per charter Phase 4's "component-level outputs needed for incremental-value testing" requirement.

## Feature / label / benchmark classification

`contact_runs_above_average`: benchmark/label — this is exactly the kind of pitcher-level run-value signal a future pitch-quality model should be checked against for incremental value, not trained to reproduce directly. `n_bip`: context (sample-size gate; treat estimates with low `n_bip` as unreliable — no explicit uncertainty column exists on this intermediate file, unlike the parent eWAR file's `contact_runs_sd`).

## Known limitations

AAA-only; no equivalent component exists at AA/High-A/Low-A (forbidden by the MiLB build charter due to lack of batted-ball coverage). No standalone uncertainty/SD column on this intermediate file — use the parent `aaa_pitcher_ewar.parquet`'s `contact_runs_sd` instead where per-pitcher uncertainty is needed.
