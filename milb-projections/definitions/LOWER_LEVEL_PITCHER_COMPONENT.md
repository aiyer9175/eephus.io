# Lower-Level Pitcher Component (SEM-Core / "SEM Core" Architecture)

## What it is

The architecture used for AA, High-A, and Low-A pitcher eWAR (see `definitions/MILB_PITCHER_PROJECTION.md`) where no batted-ball contact coverage exists. Code: `~/milb_pitcher_ewar/pipeline/build_sem_ledgers.py` (docstring: "Phases 5-9 — SEM-core pitcher eWAR ledgers per level-league-season"). Rows carry `architecture == "SEM_CORE"`.

## Naming note

"SEM-core" here is unrelated to the MLB-side `sem_plus`/`rem_plus` plus-scale metrics referenced in `~/pitcher_ewar/SEM_REM_RUNS_CONVERSION.md`. Same acronym, different system — SEM-core is an architecture label for the MiLB FI-only build path, not the MLB "Standard Error Method" plus-metric.

## Why it exists

Approximating contact-quality where there's no batted-ball data would fabricate signal the charter explicitly forbids ("approximating it is forbidden by charter" — `AA_PITCHER_EWAR.md`). Instead, SEM-core computes league-season-centered fielding-independent (FI) runs, role-aware replacement, and park/league adjustment, and explicitly declares the missing contact dimension via `coverage_level == "fi_only"` and `missing_components`.

## What it does NOT produce

No `contact_runs_above_average` column exists at all for AA/High-A/Low-A (confirmed absent from the live parquet schema — this is not a null-filled column, the column itself doesn't exist). No HR-opportunity/HR-conversion decomposition either — those require contact/batted-ball classification that isn't available.

## Feature / label / benchmark classification

Same rules as `definitions/MILB_PITCHER_PROJECTION.md`: FI-runs-based columns (`fi_runs_observed`, `pitcher_runs_above_average`, `pitcher_ewar`) are benchmark/label material for the future pitch-quality model, never a feature. A future model should not attempt to reconstruct a missing contact component for these levels by inference from this file — that would repeat the exact fabrication the SEM-core architecture was built to avoid.

## Known limitations

No contact signal at all below AAA. Not comparable to AAA/MLB pitcher eWAR without accounting for the missing component (`missing_components` must be checked before any cross-level comparison).
