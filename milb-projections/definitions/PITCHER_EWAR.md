# Pitcher eWAR (MLB champion)

## What it is

`pitcher_ewar.parquet` (grain: pitcher × season, `player_id`/`season`) is Eephus's production run-value-decomposition WAR metric for MLB pitchers. Version `pitcher-ewar-1.1.0`, ruling status `SHIP_WITH_LIMITED_REMEDIATION` (`~/pitcher_ewar/FINAL_PITCHER_EWAR_RULING.md`, 2026-07-16/17).

## Why it exists

To attribute run prevention to a pitcher independent of defense/park/luck, decomposed into interpretable components (fielding-independent runs, contact-suppression runs, HR opportunity vs. conversion, park neutralization, league/role adjustment, replacement level), rather than a single opaque score.

## Observation unit

Pitcher × season (`player_id`, `season`). 4,371 rows, 2021-2025, all pitchers with ≥1 batter faced.

## Model / version

`pitcher-ewar-1.1.0` (see `PITCHER_EWAR_MODEL_MANIFEST.json`). A frozen prior candidate (`pitcher-ewar-1.0.0-CANDIDATE`) is checksummed under `~/pitcher_ewar/champion/`.

## Governing timestamp

`as_of_date`, `data_freshness` columns per row.

## Fields (real columns, confirmed against the live parquet)

`player_id, player_name, season, team, role, starter_share, opener_share, bulk_reliever_share, short_reliever_share, innings_pitched, batters_faced, fi_runs_observed, fi_runs_stabilized, hr_runs_above_average, hr_opportunity_runs, hr_conversion_runs, all_contact_suppression_runs, contact_runs_above_average, contact_missing, league_adjustment_runs, pitcher_runs_above_average, replacement_runs, runs_above_replacement, runs_per_win, pitcher_ewar, fi_runs_sd, contact_runs_sd, pitcher_ewar_sd, pitcher_ewar_low, pitcher_ewar_high, reliability, sample_tier, hr, hr_neut, hr_pf_exposure, park_hr_credit_runs, park_adjustment_method, park_adjustment_confidence, framing_runs_exposure, framing_coverage, framing_treatment, position_player_pitching_flag, model_version, as_of_date, data_freshness`.

## Feature / label / benchmark classification

- **Benchmark/label for a future pitch-quality model**: `pitcher_ewar`, `runs_above_replacement`, and the run-component breakdown (`fi_runs_observed`, `contact_runs_above_average`, `hr_opportunity_runs`, `hr_conversion_runs`) are the target the future model is compared against — never a feature to train on directly (that would be target leakage for any model trying to predict/explain this same value).
- **Context**: `role`, `starter_share`/*_share columns, `sample_tier`, `reliability` describe usage pattern, safe as conditioning context.
- **Uncertainty**: `fi_runs_sd`, `contact_runs_sd`, `pitcher_ewar_sd`, `pitcher_ewar_low`/`_high` (80% band, ±1.28×sd), `reliability`.

## Known limitations

- No pitch-type/arsenal decomposition exists in this metric at all — it is season-aggregate only.
- HR-conversion residual is documented elsewhere in Eephus (project memory) as "zero-skill, quarantine" — treat `hr_conversion_runs` as a noisier, less-repeatable component than `fi_runs_observed`.
- `contact_missing` flags rows where contact could not be estimated (not zero-imputed) — check this before using `contact_runs_above_average` as a benchmark.

## Downstream consumers (within Eephus)

`MILB_PITCHER_EWAR_MANIFEST.json` cites this as `champion_reference: "pitcher-ewar-1.1.0 (MLB)"` for the MiLB stack. No other cross-repo consumer found.
