# MiLB Park Factors (v2, authoritative)

## What it is

The finalized, empirical MiLB park-factor layer. Grain: team × season (`venue_id` carries park identity; a team can share a venue with others in some seasons). 600 team-seasons, 124 venues, all levels. Version `milb-park-factors-2.0.0`, status `SHIP FULL EMPIRICAL`, shipped 2026-07-18.

## Why it exists / what it replaced

It supersedes `environment_engine`'s MiLB park artifact, which was a 119-row **air-density index** (correlation with true HR park effect: r=0.164 — i.e., not a park factor at all) built on a game feed with a real coverage defect: 3.12% of games (1,203 of 38,554 authoritative completed games) were silently absent, 4 venues had zero coverage, and the missingness correlated with run environment (-0.80 runs/game, z=-5.76) — a `SELECTED_SAMPLE_INVALID` condition, not a "weather bug" as originally hypothesized. This v2 layer is a full rebuild from team home/road StatsAPI splits against the authoritative 38,554-game universe, with zero weather dependency (`weather_required` is `False` on every row, enforced as an invariant).

## Method

Empirical home/road team splits (`park_factor_method == "EMPIRICAL_HOME_ROAD_NO_WEATHER"` on every row), league-season centered, Empirical-Bayes shrunk, computed over a 3-season venue window. Validation: year-over-year persistence 0.943 (run) / 0.952 (HR); split-half reliability 0.806 (run) / 0.816 (HR).

## Fields (real columns, confirmed against the live parquet)

`season, level, league_id, league_name, team_id, team_name, venue_id, venue_name, run_park_factor, hr_park_factor, run_pf, hr_pf, run_pf_sample, hr_pf_sample, home_games, away_games, run_pf_reliability, hr_pf_reliability, centering_group, centering_residual, park_factor_method, park_factor_confidence, coverage_share, weather_required, model_version, as_of_date`.

- **Published factors**: `run_park_factor`, `hr_park_factor` (final, EB-shrunk). `run_pf`/`hr_pf` are the pre-3-year-rolling intermediate values — kept for transparency, not the headline number.
- **No contact factor, no strikeout/batter-eye factor exists.** Only run and HR factors are modeled — do not assume a `contact_factor` or `strikeout_factor` column; they were never built.
- **Sample size**: `run_pf_sample`, `hr_pf_sample`, plus `home_games`/`away_games`.
- **Shrinkage weight**: `run_pf_reliability`, `hr_pf_reliability` (Empirical-Bayes weights).
- **Confidence**: `park_factor_confidence` (mean of the two reliability weights) — there is no separate variance/CI column.
- **Coverage**: `coverage_share` (invariant: exactly 1.0 on every row — complete universe by construction, unlike the deprecated engine).
- **Version/source**: `model_version` (`"milb-park-factors-2.0.0"`), `as_of_date` (`"2026-07-18"`).

## Temporary venues / anomalies

No dedicated temporary-venue flag exists; venue identity is season-effective via the affiliate mapping join. Known anomaly: Amarillo (Texas League) is the most extreme HR park in the system (HR factor ~1.37-1.41 across seasons) — independently confirmed by both the empirical model and the deprecated air-density incumbent. Greensboro (HR factor 1.37) is a low-altitude bandbox the air-density incumbent completely missed — a concrete example of why the incumbent was invalid, not just imprecise.

## Downstream restatement

The MiLB pitcher eWAR v1.1.0 restatement (22,076 rows across AAA/AA/High-A/Low-A, 2021-2025) is the direct consumer, applying `effective_hr_pf` park-neutralization. Mean restatement delta ≈0 at every level (the park layer redistributes rank, it doesn't inflate value); qualified-subset (≥100 BF) MAE ranges 0.0227 (Low-A) to 0.0380 (AA). See `reports/HISTORICAL_SNAPSHOT_AUDIT.md` for the full restatement-ledger treatment.

## What is explicitly NOT touched or re-derived by this package

`env_foundation_integration`'s `m06_stadium_translation.py` and `m09c_lower_milb_translation.py` are still reading the deprecated air-density artifact and are frozen (`FROZEN_PENDING_INPUT_REBUILD`) pending a separate, not-yet-executed rebuild charter. This handoff package does not migrate them, does not recompute park factors, and does not alter `milb_park_factors_v2.parquet` or its consumers in any way — see `tests/test_park_context_compatibility.py`.

## Feature / label / benchmark classification

`run_park_factor`/`hr_park_factor`: **context**, used to neutralize outcomes before attributing them to a pitcher — a future pitch-quality model should adjust for park the same way pitcher eWAR does, never treat park factor itself as a quality signal about the pitcher. `park_factor_confidence`/reliability columns: context (down-weight low-confidence venues, especially thin-sample low-affiliate parks).

## Known limitations

No contact/strikeout/batter-eye park factor exists. No per-pitch-type park adjustment exists (park factors are season-aggregate, not split by batted-ball or pitch type).
