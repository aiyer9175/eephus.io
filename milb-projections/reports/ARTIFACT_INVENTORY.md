# Artifact Inventory — MiLB Pitch-Quality Handoff

Classifications use the two axes required by the charter:

- **Publication**: `PUBLIC_GITHUB | PUBLIC_SCHEMA_ONLY | PRIVATE_EXPORT_REQUIRED | PRIVATE_OPTIONAL | INTERNAL_ONLY | DEPRECATED | NOT_NEEDED`
- **Research importance**: `BLOCKING_FOR_BUILD | BLOCKING_FOR_FINAL_RULING | REQUIRED_WHERE_COVERED | DEGRADES_VALIDATION | OPTIONAL`

Machine-readable version: `config/artifact_inventory.yaml`.

## A. Contact portability

| Artifact | Source | Publication | Importance |
|---|---|---|---|
| Statcast contact-quality models (Bat-to-Ball+, Contact+, Damage Conversion+) | `bat_to_ball_plus`, `contact_plus`, `damage_conversion_plus` | NOT_NEEDED (MLB-only, no MiLB dimension — cannot serve a portability role; documented for context only) | OPTIONAL |
| MiLB rate-skill translation architecture (persistence of K%/BB%/ISO/wOBA/Decision+ across levels) | `career_outcome_plus/milb/block2_translations.py`, `block5_recommended_architecture.md` | PUBLIC_SCHEMA_ONLY (methodology + limitation documented publicly; source is copyright-headered, not republished) | BLOCKING_FOR_FINAL_RULING (the future builder must know contact-quality portability below AAA is an open, data-blocked problem, not something to silently assume solved) |
| `latent_rate_talent.parquet` / `milb_xwar_projection.parquet` (derived outputs) | `career_outcome_plus/data/` | PRIVATE_EXPORT_REQUIRED (real values available only via a private, configurable-path export; not committed to git) | REQUIRED_WHERE_COVERED |
| Dedicated "contact portability" model (as scoped by the charter) | — | **Does not exist.** Recorded in `KNOWN_GAPS.md`, not fabricated. | — |

## B. Current MiLB pitcher stack

| Artifact | Source | Publication | Importance |
|---|---|---|---|
| AAA/AA/High-A pitcher eWAR (`{aaa,aa,higha}_pitcher_ewar.parquet`, schema `milb-pitcher-ewar-1.0.0`) | `milb_pitcher_ewar/data/` | PUBLIC_SCHEMA_ONLY for schema/methodology docs; PRIVATE_EXPORT_REQUIRED for real row values (parquet is git-ignored repo-wide and is a production data product, not redistributed wholesale) | BLOCKING_FOR_BUILD (this is the primary champion benchmark the future model must beat) |
| Low-A pitcher eWAR | `milb_pitcher_ewar/data/lowa_pitcher_ewar.parquet` | INTERNAL_ONLY (publication explicitly withheld pending approval per `FINAL_MILB_PITCHER_EWAR_BUILD_REPORT.md`) | DEGRADES_VALIDATION if omitted, but must stay internal — do not export |
| CPX/DSL pitcher eWAR | `milb_pitcher_ewar/` (no dedicated artifact; research-only) | NOT_NEEDED for benchmarking now | OPTIONAL |
| AAA Contact Management+ (component of AAA pitcher eWAR) | `milb_pitcher_ewar/data/aaa_contact_*.parquet` | PRIVATE_EXPORT_REQUIRED (component-level, needed for incremental-value testing) | REQUIRED_WHERE_COVERED |
| SEM-core architecture (AA/High-A/Low-A) | `milb_pitcher_ewar/pipeline/build_sem_ledgers.py` | PUBLIC_SCHEMA_ONLY (architecture explanation only) | REQUIRED_WHERE_COVERED |
| MLB pitcher eWAR champion (`pitcher_ewar.parquet`, schema `pitcher-ewar-1.1.0`) | `pitcher_ewar/data/` | PUBLIC_SCHEMA_ONLY + PRIVATE_EXPORT_REQUIRED (same reasoning as MiLB) | BLOCKING_FOR_BUILD (the cross-level reference champion) |
| MLB champion freeze + archive (`champion/`, `data/archive/`) | `pitcher_ewar/` | PRIVATE_EXPORT_REQUIRED (genuine historical snapshots — high value for walk-forward evaluation) | REQUIRED_WHERE_COVERED |
| Arsenal/Stuff+/Command+ pitch-level output | — | **Does not exist in either stack** — explicitly out-of-scope in both manifests. Not fabricated. | — |

## C. Park factors

| Artifact | Source | Publication | Importance |
|---|---|---|---|
| MiLB park factors v2 (`milb_park_factors_v2.parquet`, `milb-park-factors-2.0.0`) | `milb_park_rebuild/data/` | PUBLIC_SCHEMA_ONLY for schema/methodology; PRIVATE_EXPORT_REQUIRED for real factor values | BLOCKING_FOR_BUILD (any pitch-quality model touching HR/run outcomes needs park context) |
| MiLB park factor tests (`tests/test_milb_*.py`) | `milb_park_rebuild/tests/` | PUBLIC_GITHUB — these are new, non-proprietary test assertions and are the mechanism for the required compatibility test | BLOCKING_FOR_FINAL_RULING |
| Deprecated MiLB air-density index (`environment_engine/data/environment/milb_park_factors.parquet`) | `environment_engine/` | DEPRECATED — referenced in docs as historical/incident context only, never exported as current data | REQUIRED_WHERE_COVERED (needed to document the incident and why r=.164 correlation matters) |
| MLB park/air-density physics (`park_air_factors.parquet`) | `environment_engine/` | NOT_NEEDED for this charter (MLB-side, out of scope; still authoritative for its own consumers) | OPTIONAL |
| `env_foundation_integration` m06/m09c (frozen MiLB translation consumers) | `env_foundation_integration/modules/` | NOT_NEEDED — referenced only as a dependency-map note; this handoff is not the pending rebuild for these modules | OPTIONAL |

## D. Identity systems

| Artifact | Source | Publication | Importance |
|---|---|---|---|
| Player identity (`eephus_identity.parquet`: eephus_pid, mlbam_id, fangraphs/bbref/retro ids, name, org, level, dob, position) | `career_outcome_plus/build_eephus_identity.py` | PRIVATE_EXPORT_REQUIRED, with `dob` truncated to birth-year (or dropped) before any export — full month/day birthdate is more granular than typically published and is flagged for redaction | BLOCKING_FOR_BUILD (every other export needs a join key) |
| Team/affiliate/league/park mapping (`milb_affiliate_mapping.parquet`, `milb_park_mapping.parquet`, `milb_league_environment.parquet`) | `milb_pitcher_ewar/pipeline/build_infrastructure.py` | NOT_NEEDED — this is reconstructable from the public MLB Stats API directly (season/team/affiliate/league/venue), which the charter itself says the external builder can already pull. Documented as "you can get this yourself" rather than exported. | OPTIONAL |
| Historical/effective-dated identity (promotions, trades, as-of joins) | — | **Does not exist.** Both identity systems are current-state-only, season-grain at best. Recorded as a limitation in `TEMPORAL_INTEGRITY.md` and `KNOWN_GAPS.md`, not fabricated. | BLOCKING_FOR_FINAL_RULING (future builder must not assume point-in-time joins are safe) |
| Collision/ambiguity handling | `build_eephus_identity.py` (silent `drop_duplicates(keep="last")`, no logged collision count) | Documented as a known defect/gap, not silently passed through | BLOCKING_FOR_FINAL_RULING |

## E. Historical benchmark snapshots

| Artifact | Source | Classification | Historical status |
|---|---|---|---|
| MLB pitcher eWAR archive (`pitcher_ewar/data/archive/*_2026-07-17.parquet`) | `pitcher_ewar/` | PRIVATE_EXPORT_REQUIRED, REQUIRED_WHERE_COVERED | Dated snapshots exist, but only one date so far (2026-07-17) — insufficient for a real time series; treat as `CURRENT_MODEL_BACKFILL` until more dates accumulate (see Phase 7 audit) |
| MLB pitcher eWAR champion freeze (`pitcher_ewar/champion/`) | `pitcher_ewar/` | PRIVATE_EXPORT_REQUIRED, REQUIRED_WHERE_COVERED | `TRUE_HISTORICAL_SNAPSHOT` for the frozen 1.0.0-CANDIDATE model state (checksummed, immutable) |
| MiLB pitcher eWAR restatement ledger (`MILB_PITCHER_EWAR_RESTATEMENT_LEDGER.parquet`) | `milb_park_rebuild/data/` | PRIVATE_EXPORT_REQUIRED, REQUIRED_WHERE_COVERED | Genuine before/after diff of a real methodology change — valuable as a worked example of restatement, not a forecast snapshot |
| MiLB pitcher eWAR itself | `milb_pitcher_ewar/` | — | No archive/snapshot directory exists at all — current-state only. Recorded as a gap. |
| `career_outcome_plus/milb/handoff/00_baseline_manifest.json` | `career_outcome_plus/` | PRIVATE_OPTIONAL | Single dated baseline freeze, not a running series — `SEASON_END_DESCRIPTIVE`-adjacent, not a true snapshot series |

## F. Definitions and rules

All of the following are newly-authored documentation (not copies of proprietary source) and are PUBLIC_GITHUB, BLOCKING_FOR_FINAL_RULING:

- Pitcher eWAR definition (MLB and MiLB), Contact Management+ / SEM-core definition, MiLB pitcher-eWAR-vs-MLB-champion relationship
- Park-adjustment methodology (empirical home/road, no-weather-dependency, EB shrinkage/centering)
- Level-translation and mixed MiLB/MLB season handling (career_outcome_plus reliability-collapse-at-AA finding)
- Role classification, temporal cutoffs, missingness behavior (documented per-artifact, not globally)

## Summary of blocking items

`BLOCKING_FOR_BUILD`: identity export (redacted), MiLB pitcher eWAR (AAA/AA/High-A) private export, MLB pitcher eWAR champion private export, MiLB park factors v2 private export.
`BLOCKING_FOR_FINAL_RULING`: contact-portability gap documentation, identity temporal-join limitation, identity collision-handling gap, all Section F definitions, park-factor compatibility tests.
No artifact required for this charter is classified `BLOCKED` — everything either has an available (if private) source, or its absence is being explicitly documented rather than treated as a blocker.
