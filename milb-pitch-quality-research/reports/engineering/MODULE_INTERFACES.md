# Module Interfaces

Phase 1. Internal API for every module in `reports/engineering/ARCHITECTURE_V1_FROZEN.md`. Each module should be implementable directly from its section below. Field-naming follows `milb-projections/contracts/*.schema.json`'s existing convention (snake_case, explicit `_sd`/`_low`/`_high` suffixes for uncertainty) for consistency with the rest of the Eephus codebase.

## Module 1: Physical Stuff

- **Purpose**: per-pitcher physical-trait averages (velocity, movement, spin), no outcome label.
- **Inputs**: `pitch_dataset_v2.parquet` rows where `tracked = true`.
- **Outputs**: one row per `(pitcher_id, level, season)`.
- **Schema**:
  | Field | Type | Reliability status |
  |---|---|---|
  | `pitcher_id` | int, required | — |
  | `level` | enum(AAA, Low-A) | — |
  | `season` | int | — |
  | `n_tracked_pitches` | int | — |
  | `velocity_mean` | float (mph) | **tested**, split-half r=0.98-0.99 |
  | `movement_pfx_x_mean`, `movement_pfx_z_mean` | float | **tested**, r=0.91-0.98 |
  | `spin_rate_mean` | float (rpm) | **tested**, r=0.98, known completeness gap |
  | `extension_mean` | float (ft) | **captured, not reliability-tested** — must not ship with a confidence claim until tested |
  | `release_x0_mean`, `release_z0_mean` | float (ft) | **captured, not reliability-tested** — same caveat |
- **Data types**: all floats IEEE-754 double; nulls represented as JSON `null`, never `0` or `-999` sentinel.
- **Refresh cadence**: daily (`reports/architecture/REFRESH_ARCHITECTURE.md`).
- **Versioning**: `physical-stuff-1.0.0` (semver; a MINOR bump adds a field, a MAJOR bump changes an existing field's definition).
- **Dependencies**: tracking-status gate (upstream, not a module).
- **Expected latency**: sub-second per pitcher at query time if precomputed nightly (no live computation planned).
- **Confidence fields**: `velocity_reliability`, `movement_reliability`, `spin_reliability` (the Phase 1B split-half coefficients, refreshed each cadence per `UNCERTAINTY_ARCHITECTURE.md`'s reliability-indicator design) — `extension`/`release_position` fields carry **no** reliability field until tested, by design, not omission.
- **Reliability fields**: `min_pitches_for_stable_estimate` (from the Phase 1B stabilization curve, per field).
- **Missing-value behavior**: a pitcher below any field's stabilization threshold returns `null` for that field specifically, not for the whole row — fields stabilize at different pitch counts (Phase 1B).
- **Failure behavior**: if `tracking_status_gate` cannot classify a venue, the row is omitted entirely (fail closed, not fail with a guessed value).
- **Consumer list**: none confirmed yet — see `CONSUMER_WIRING_PLAN.md`.
- **Backward compatibility**: adding `extension`/`release_position` reliability fields once tested is a MINOR version bump (additive); removing a field is MAJOR.
- **Future extension points**: `arm_angle` (Savant-exclusive today, not computable from this module's current data source — see `STUFF_PLUS_RECONCILIATION.md`), `velo_delta_vs_primary` (derivable from this module + Module 2, not yet implemented).

## Module 2: Arsenal Construction

- **Purpose**: pitch-mix/diversity per pitcher.
- **Inputs**: `pitch_dataset_v2.parquet` rows where `tracked = true` and `pitch_type_code` is non-null.
- **Outputs**: one row per `(pitcher_id, level, season)`.
- **Schema**: `pitcher_id`, `level`, `season`, `share_fastball` (float, 0-1), `share_breaking`, `share_offspeed`, `pitch_entropy` (float, Shannon entropy, nats).
- **Data types**: shares sum to 1.0 ± floating-point tolerance; entropy ≥ 0.
- **Refresh cadence**: daily.
- **Versioning**: `arsenal-construction-1.0.0`.
- **Dependencies**: Module 1's tracking gate (shared, not a data dependency).
- **Expected latency**: sub-second, precomputed.
- **Confidence fields**: **none defined yet** — family-restricted reliability is untested (flagged since Phase 1B); this module ships without a confidence field until that gap closes, per `ARCHITECTURE_V1_FROZEN.md`'s exception-logging discipline (a real limitation, not an oversight).
- **Reliability fields**: not applicable until the above is resolved.
- **Missing-value behavior**: pitchers with fewer than the family-analysis minimum (100 tracked pitches, per Phase 1C) return `null` for all fields.
- **Failure behavior**: same fail-closed pattern as Module 1.
- **Consumer list**: internal only — feeds Module 3 as a covariate (see `DATA_CONTRACTS.md`); no external consumer identified.
- **Backward compatibility**: adding a pitch family (currently only 3: fastball/breaking/offspeed) is MAJOR (changes the meaning of existing shares).
- **Future extension points**: per-pitch-family reliability once tested; sequencing features (unbuilt, per `reports/phase1c/FEATURE_FAMILY_INVENTORY.md`).

## Module 3: Miss-Inducing Ability (two variants)

### 3a. Tracked-venue variant
- **Purpose**: whiff rate at tracked venues, with a stuff/mix/location decomposition.
- **Inputs**: `pitch_dataset_v2.parquet`, `tracked = true`, swing-conditional.
- **Outputs**: `pitcher_id`, `level`, `season`, `whiff_rate` (float, 0-1), `n_swings`.
- **Confidence fields**: `whiff_reliability` (split-half r=0.33-0.51 by level, Phase 1B — must be reported per-level, not pooled, since the range spans levels meaningfully).
- **Missing-value behavior**: `null` below the stabilization threshold for the pitcher's level.
- **Consumer list**: none confirmed — see `CONSUMER_WIRING_PLAN.md`.

### 3b. Outcome-only variant (= Module 6, same interface family)
- **Purpose**: whiff rate at untracked venues.
- **Inputs**: `pitch_dataset_v2.parquet`, any venue, swing-conditional (no `tracked` filter).
- **Outputs**: same schema as 3a, plus `evidence_strength: "limited"` (a required, non-optional field — the R²=0.016 finding means this variant must always self-report its weak evidentiary basis, per `PUBLICATION_ARCHITECTURE.md`).
- **Confidence fields**: same `whiff_reliability` field, but the value itself is near-uninformative (R²=0.016) — the field exists for schema consistency with 3a, not because it's a strong number.
- **Backward compatibility note**: 3a and 3b share a schema deliberately, so a consumer can query "whiff rate" uniformly and inspect `evidence_strength`/`tracked` to decide how much to trust it — not two incompatible APIs.

## Module 4: Ground-Ball Tendency

- **Purpose**: ground-ball rate, its relationship to Module 1's movement output.
- **Inputs**: `pitch_dataset_v2.parquet`, `tracked = true`, `has_hit_data = true`, `n_battedballs >= 15`.
- **Outputs**: `pitcher_id`, `level`, `season`, `ground_ball_rate` (float, 0-1), `n_battedballs`.
- **Confidence fields**: **none — own reliability untested**, the central open item from `reports/architecture/MODULE_SPECIFICATIONS.md`. Ships without a confidence field, same discipline as Module 2.
- **Missing-value behavior**: `null` below 15 batted balls.
- **Consumer list**: none.
- **Future extension points**: promote to a confidence-bearing field once own-reliability is tested (see `IMPLEMENTATION_SEQUENCE.md`).

## Module 5: Damage Suppression (research-only — no production interface)

- **Purpose**: research diagnostic only, per `reports/architecture/PRODUCTION_CLASSIFICATION.md` (`Internal Diagnostic`).
- **Interface**: intentionally **not specified as a production API** in this document — an internal-diagnostic construct doesn't get a versioned consumer-facing interface under this charter's engineering standards (`ENGINEERING_STANDARDS.md`). Available only via direct query of `reports/phase1c/`'s research artifacts, not a module with a refresh/versioning/consumer contract.

## Module 6: Outcome-Only Result Rate

Same interface as Module 3b above — Module 3b *is* Module 6, named once in `MODULE_SPECIFICATIONS.md`'s module list and once in the tracking-branch framing (`TRACKING_BRANCH_ARCHITECTURE.md`); this engineering pass treats them as one interface with two population filters, not two separate APIs, since duplicating the schema would violate `ENGINEERING_STANDARDS.md`'s "no module should duplicate infrastructure" rule one phase early.

## Observed evidence / Inference / Speculation

Every reliability figure cited traces to a specific Phase 1B/1C number (Observed evidence). The decision to withhold a confidence field from Modules 2 and 4 (rather than shipping a placeholder or an untested estimate) is Inference — a deliberate engineering choice enforcing `ARCHITECTURE_V1_FROZEN.md`'s standard that documentation must match implementation, not a finding from the data itself.

## Future work

Modules 2 and 4's confidence fields are the two concrete "add a field, bump MINOR version" future changes this document anticipates and is designed to accommodate without a breaking change.
