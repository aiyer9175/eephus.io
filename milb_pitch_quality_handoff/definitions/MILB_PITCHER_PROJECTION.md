# MiLB Pitcher eWAR

## What it is

The level-local counterpart to MLB pitcher eWAR (`definitions/PITCHER_EWAR.md`). Same run-decomposition family, applied per level with level-appropriate architecture. Grain: pitcher × league × season (a pitcher who moves levels mid-season gets one row per level-league-season).

## Why two architectures exist

- **AAA — `MODIFIED_MLB` architecture**: has real batted-ball contact data (2023+), so it carries the full contact/HR-opportunity/HR-conversion decomposition, mirroring the MLB metric.
- **AA / High-A / Low-A — `SEM_CORE` architecture**: no batted-ball contact coverage exists at these levels; approximating it is explicitly forbidden by the build charter. These levels carry fielding-independent (FI) runs, role-aware replacement, and park/league adjustment, but **no contact component** — `missing_components` lists this explicitly per row rather than zero-imputing it.

## Publication status by level (per `~/milb_pitcher_ewar/FINAL_MILB_PITCHER_EWAR_BUILD_REPORT.md`)

| Level | Architecture | Publication | Rows |
|---|---|---|---|
| AAA | MODIFIED_MLB | public | 6,167 |
| AA | SEM_CORE | public | 4,985 |
| High-A | SEM_CORE | public | 5,019 |
| Low-A | SEM_CORE | **internal only — publication withheld pending approval** | 5,905 |
| CPX/DSL | — | research only, no dedicated artifact | — |

**Low-A is excluded from every export this package produces**, per `PUBLICATION_POLICY.md` — `INTERNAL_ONLY` classification means no export in any form without separate approval.

## Version

`milb-pitcher-ewar-1.0.0` baseline; park-restated subset stamped `milb-pitcher-ewar-1.1.0` after the MiLB park factors v2 rebuild (see `definitions/MILB_PARK_FACTORS.md` and `reports/HISTORICAL_SNAPSHOT_AUDIT.md` for the restatement ledger).

## Fields (real columns, confirmed against the live parquet)

AAA (`aaa_pitcher_ewar.parquet`): `player_id, player_name, season, level, league, league_id, org, team_id, role, starter_share, innings_pitched, batters_faced, fi_runs_observed, fi_runs_stabilized, hr_runs_above_average, hr_opportunity_runs, hr_conversion_runs, contact_runs_above_average, league_adjustment_runs, pitcher_runs_above_average, replacement_runs, runs_above_replacement, runs_per_win, pitcher_ewar, fi_runs_sd, contact_runs_sd, pitcher_ewar_sd, pitcher_ewar_low, pitcher_ewar_high, reliability, sample_tier, architecture, coverage_level, missing_components, park_adjustment_method, framing_treatment, model_version, as_of_date`.

AA/High-A/Low-A (`{aa,higha,lowa}_pitcher_ewar.parquet`, same shape): `player_id, player_name, team_id, league, level, sportId, season, innings_pitched, batters_faced, so, bb, hbp, hr, g, gs, r, org, league_id, runs_per_win, lg_ra9, fi_runs_observed, fi_runs_stabilized, starter_share, role, replacement_runs, league_adjustment_runs, pitcher_runs_above_average, runs_above_replacement, pitcher_ewar, fi_runs_sd, contact_runs_sd, pitcher_ewar_sd, pitcher_ewar_low, pitcher_ewar_high, sample_tier, reliability, architecture, coverage_level, missing_components, park_adjustment_method, framing_treatment, model_version, as_of_date`.

Note: `contact_runs_sd` exists as a column name at all four levels for schema uniformity, but is not a meaningful contact-uncertainty figure at AA/High-A/Low-A (`architecture == "SEM_CORE"`, `coverage_level == "fi_only"`) since there is no contact component to have uncertainty about there — always check `architecture`/`coverage_level`/`missing_components` before reading `contact_runs_sd` or `contact_runs_above_average` at these levels (AA/High-A/Low-A do not even carry a `contact_runs_above_average` column — confirmed absent from the live schema).

## Currency law

**Level-local only.** `runs_per_win` and replacement pools are computed independently per level; `pitcher_ewar` is not comparable across levels or to MLB without going through a separate translation/reach layer (none exists for pitchers today — see `KNOWN_GAPS.md`). `tests/test_milb_cross_level_guards.py` (in `~/milb_park_rebuild/tests/`) enforces this as a regression guard.

## Feature / label / benchmark classification

Same as MLB pitcher eWAR (`definitions/PITCHER_EWAR.md`): the run-value columns are benchmark/label material, never a training feature for a model predicting the same construct. `architecture`, `coverage_level`, `missing_components` are mandatory conditioning context — a future pitch-quality model must not compare AAA contact-inclusive rows to AA/High-A/Low-A FI-only rows as if they were the same measurement.

## Known limitations

- No pitch-type/arsenal output anywhere in this stack (explicitly out-of-scope per its own manifest).
- No champion-freeze/archive directory exists yet for MiLB (unlike MLB) — only current-state files.
- Low-A excluded from publication entirely.
