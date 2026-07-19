# Missing Private Assets

Assets that would strengthen this handoff but are not yet exported, with enough detail that a future maintainer can add them without re-doing the reconnaissance.

## 1. MLB pitcher eWAR champion freeze + archive

- **Authoritative owner**: `~/pitcher_ewar/champion/`, `~/pitcher_ewar/data/archive/`
- **Why needed**: a `TRUE_HISTORICAL_SNAPSHOT`-classified asset with genuine checksummed immutability — the strongest walk-forward-safe reference in the whole ecosystem.
- **Exact schema**: same as `contracts/pitcher_ewar.schema.json#mlb_pitcher_ewar`, plus `champion_model_manifest.json`'s MD5 map and `champion_reconciliation.json`.
- **Exact date range**: frozen 2026-07-17, covering the 2021-2025 seasons as scored by `pitcher-ewar-1.0.0-CANDIDATE`.
- **Publication restriction**: same as the live champion (`PRIVATE_EXPORT_REQUIRED`).
- **Blocking level**: `REQUIRED_WHERE_COVERED`, not blocking — the live champion export already gives the builder a working reference.
- **Available substitute**: `adapters/export_pitcher_ewar_mlb.py`'s live export, with the caveat that it reflects `1.1.0`, not the frozen `1.0.0-CANDIDATE`.
- **Recommended transfer method**: a new `adapters/export_pitcher_ewar_champion_freeze.py` following the exact pattern of `export_park_context.py` (pure pass-through, hash-verify against `champion_model_manifest.json`'s MD5s before export).

## 2. MiLB pitcher eWAR restatement ledger

- **Authoritative owner**: `~/milb_park_rebuild/data/MILB_PITCHER_EWAR_RESTATEMENT_LEDGER.parquet`
- **Why needed**: the best available worked example of a legitimate restatement (vs. a leak) for `TEMPORAL_INTEGRITY.md` — currently only described in prose in `reports/HISTORICAL_SNAPSHOT_AUDIT.md`, not exported as data.
- **Exact schema**: `player_id, player_name, season, level, league, team_id, batters_faced, innings_pitched, role, pitcher_ewar_v1_0_0, pitcher_ewar, hr_pf_3yr, effective_hr_pf, park_adjustment_method, park_exposure_method, park_exposure_confidence, delta_ewar, rank_old, rank_new, rank_delta, reason` (22,076 rows).
- **Exact date range**: 2021-2025 seasons, restatement event 2026-07-18.
- **Publication restriction**: `PRIVATE_EXPORT_REQUIRED`.
- **Blocking level**: `REQUIRED_WHERE_COVERED`, not blocking.
- **Available substitute**: the prose summary in `reports/HISTORICAL_SNAPSHOT_AUDIT.md` (MAE/RMSE/rank-movement statistics by level).
- **Recommended transfer method**: a straightforward pass-through adapter, same pattern as `export_park_context.py`.

## 3. `career_outcome_plus/milb` sibling artifacts (`milb_career_distribution.parquet`, `milb_xfv_projection.parquet`, `milb_debut_timing.parquet`, `prospect_mlb_status.parquet`)

- **Authoritative owner**: `~/career_outcome_plus/data/`
- **Why needed**: only if a future phase of pitch-quality research extends into career-outcome/debut-timing modeling for pitchers specifically — out of scope for the current pitch-quality charter.
- **Blocking level**: `OPTIONAL`.
- **Recommended transfer method**: extend `adapters/export_contact_translation.py`'s `SOURCE_ARTIFACTS` dict if/when needed.

## Not on this list, and why

- **Low-A MiLB pitcher eWAR** is deliberately absent from this report as well as from every export — it is `INTERNAL_ONLY` pending a separate approval that is outside this charter's authority to request or grant, not a missing asset to transfer.
- **A dedicated contact-quality portability model** is absent because it does not exist anywhere in Eephus, not because of an access restriction — see `KNOWN_GAPS.md`.
