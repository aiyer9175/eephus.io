# Historical Snapshot Audit

Classification legend: `TRUE_HISTORICAL_SNAPSHOT | SEASON_END_DESCRIPTIVE | CURRENT_MODEL_BACKFILL | RECONSTRUCTED_AS_OF | UNKNOWN`.

## MLB pitcher eWAR archive (`~/pitcher_ewar/data/archive/`)

- Files: `pitcher_ewar_pitcher-ewar-1.0.0-CANDIDATE_2026-07-17.parquet`, `pitcher_ewar_pitcher-ewar-1.1.0_2026-07-17.parquet`.
- Earliest/latest snapshot: both dated 2026-07-17 (same day, two model versions) — **only one calendar date exists in the archive so far**. There is no multi-date time series yet.
- Update cadence: undefined — this archive appears to be seeded at a version-change event, not on a fixed schedule.
- Classification: **CURRENT_MODEL_BACKFILL**. Each file is today's model version applied to the full 2021-2025 season range, not a record of what the system actually output on each historical date. Safe for descriptive comparison ("how does 1.0.0 differ from 1.1.0 over history"), **not safe as a stand-in for what a live system would have reported in, say, 2022** — the whole file was generated on 2026-07-17.
- Allowed use: descriptive version-diff comparison. Prohibited use: walk-forward evaluation as if these were point-in-time forecasts.

## MLB pitcher eWAR champion freeze (`~/pitcher_ewar/champion/`)

- Frozen at 2026-07-17, `model_version: "pitcher-ewar-1.0.0-CANDIDATE"`, MD5-checksummed for both code and data (`champion_model_manifest.json`).
- Classification: **TRUE_HISTORICAL_SNAPSHOT** for the frozen *model state* — the freeze mechanism (checksums covering both code and inputs) genuinely guarantees this artifact will never silently change, which is the property a walk-forward benchmark needs. It is still, however, a snapshot of *one* model version at *one* freeze date, not a series of forecasts made across time as the season unfolded.
- Allowed use: stable reference point for "did the champion change" comparisons; component-level input files (`champion_input_*.parquet`) are usable for incremental-value testing of individual components.

## MiLB pitcher eWAR restatement ledger (`~/milb_park_rebuild/data/MILB_PITCHER_EWAR_RESTATEMENT_LEDGER.parquet`)

- 22,076 rows. Columns: `player_id, player_name, season, level, league, team_id, batters_faced, innings_pitched, role, pitcher_ewar_v1_0_0, pitcher_ewar, hr_pf_3yr, effective_hr_pf, park_adjustment_method, park_exposure_method, park_exposure_confidence, delta_ewar, rank_old, rank_new, rank_delta, reason`.
- Classification: **RECONSTRUCTED_AS_OF**. This is a genuine, ledgered before/after diff of a real methodology change (the v2 park-factor rebuild) applied to real historical pitcher-seasons — it changes what the historical value *is* (a restatement), and every changed row carries both the old and new value plus a `reason`, so nothing is silently overwritten. This is the single best asset in the whole package for teaching a future model what "a legitimate restatement" looks like versus "future information leaking into the past."
- Allowed use: worked example of restatement discipline; NOT a forecast snapshot, and not evidence that pre-2026-07-18 systems knew about the v2 park factors.

## MiLB pitcher eWAR itself (`~/milb_pitcher_ewar/`)

- No archive/snapshot/champion-freeze directory exists at all (confirmed by directory listing — only `pipeline/` and `data/` current-state files).
- Classification: not applicable — there is nothing to classify. This is recorded as a genuine infrastructure gap in `KNOWN_GAPS.md`, not papered over with a fabricated snapshot.

## `career_outcome_plus/milb/handoff/00_baseline_manifest.json`

- A single dated (2026-07-09) baseline freeze with sha256/byte-count/row-count/mtime per artifact (`milb_career_distribution.parquet`, `milb_xwar_projection.parquet`, `milb_xfv_projection.parquet`, `milb_debut_timing.parquet`, `prospect_mlb_status.parquet`, `career_distribution_player_outputs.parquet`), `model_version: "reach-2.0.0"`.
- Classification: **SEASON_END_DESCRIPTIVE**-adjacent — it's a single point-in-time freeze of a set of derived tables, not a running series and not itself a per-row historical-snapshot mechanism. Useful as a fixed reference for reproducibility checks, not for walk-forward evaluation.

## MiLB park factors v2 (`~/milb_park_rebuild/data/milb_park_factors_v2.parquet`)

- Single current version (`milb-park-factors-2.0.0`, `as_of_date: "2026-07-18"`), no archive directory. Each row does carry a `season` column spanning 2021-2025, but the whole table was computed once, as of one date, over all five seasons together (a 3-season rolling window per the manifest) — it is **not** a record of what park factors would have been computable using only data available as of each season's end.
- Classification: **CURRENT_MODEL_BACKFILL**. Safe for descriptive use (e.g., "Amarillo has been the most extreme HR park across 2021-2025"); **not safe** for a walk-forward pitch-quality evaluation that needs "the park factor as it would have been known during the 2022 season" — that information doesn't exist as a separate artifact.

## Player identity (`eephus_identity.parquet`)

- Current-state only, no historical versioning found at all (no dated identity snapshots exist anywhere in the codebase).
- Classification: **UNKNOWN** for anything but "identity as of the last build run." Do not assume any historical identity fact (e.g., a player's organization in 2022) is recoverable from this file — it reflects only the most recent build.

## Summary table

| Asset | Historical status | Safe for walk-forward eval? |
|---|---|---|
| MLB pitcher eWAR archive (2 dated files) | CURRENT_MODEL_BACKFILL | No |
| MLB pitcher eWAR champion freeze | TRUE_HISTORICAL_SNAPSHOT (of model state) | Yes, for model-stability comparisons only |
| MiLB pitcher eWAR restatement ledger | RECONSTRUCTED_AS_OF | Yes, as a restatement worked example; not a forecast |
| MiLB pitcher eWAR (no archive) | n/a — gap | n/a |
| career_outcome_plus baseline manifest | SEASON_END_DESCRIPTIVE-adjacent | No |
| MiLB park factors v2 | CURRENT_MODEL_BACKFILL | No |
| Player identity | UNKNOWN (current-state only) | No |

No asset in this audit is silently excluded — every one is preserved in the manifest with its historical-status field restricting its benchmark role, per the charter's instruction not to drop backfilled assets, only to restrict their use.
