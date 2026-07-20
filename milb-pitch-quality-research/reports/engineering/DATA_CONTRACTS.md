# Data Contracts

Phase 4. Explicit input/intermediate/output contracts per module, following `milb-projections/contracts/*.schema.json`'s existing convention (one JSON Schema per artifact) rather than leaving interfaces implicit.

## Contract layers, shared across all modules

1. **Input contract**: `pitch_dataset_v2.parquet`'s schema (`scripts/phase1c/build_pitch_dataset_v2.py`) — `pitcher_id`, `batter_id`, `level`, `venue_id`, `tracked`, `game_date`, `pitch_type_code`, outcome flags, tracked-field values, `hitData` fields. This is the one shared input contract every module reads from; no module should define its own parallel extraction of the raw feed.
2. **Intermediate contract**: per-pitcher family-aggregate tables (`scripts/phase1c/family_analysis.py`'s `build_pitcher_table` output) — internal only, not published, but versioned the same way (a change to the aggregation logic is a version bump even though nothing external consumes it directly, since Module 3/4's outputs are downstream of it).
3. **Output contract**: one JSON Schema per module's published artifact (`data/physical_stuff.schema.json`, etc.), mirroring `milb-projections/contracts/pitcher_ewar.schema.json`'s structure (required vs. optional fields, types, enums, nullability rules).

## Versioning

Semver per module (`physical-stuff-1.0.0`, etc., per `MODULE_INTERFACES.md`). Rules:
- **PATCH**: bug fix that doesn't change output shape or values' meaning (e.g., a timezone-handling fix in `game_date`).
- **MINOR**: additive change (a new field, a new confidence indicator once tested) — must remain readable by an old consumer that ignores unknown fields.
- **MAJOR**: any change to an existing field's meaning, removal of a field, or a change to the population a module covers (e.g., if tracked Low-A's venue list changes).

## Migration strategy

Follows `milb-projections/PORTING_GUIDE.md`'s existing validation-checklist pattern: any consumer integrating a module should (1) validate against the fixture before requesting real data, (2) check the contract's required-vs-optional fields, (3) check `historical_status` before any walk-forward use (`TEMPORAL_INTEGRITY.md`'s standing rules apply here too — none of this research's modules are `TRUE_HISTORICAL_SNAPSHOT` yet; all are `CURRENT_MODEL_BACKFILL`-equivalent until an archive mechanism exists, per `REFRESH_ARCHITECTURE.md`'s archive-strategy recommendation).

## Compatibility guarantees

- A MINOR or PATCH version bump never breaks an existing consumer — this is the hard guarantee.
- A MAJOR version bump requires a documented migration note (which fields changed meaning, what a consumer must update) before publishing, mirroring `milb-projections/DECISION_LEDGER.md`'s discipline of recording every consequential change with its reasoning.

## Schema evolution: the two anticipated near-term changes

1. **Extension/release-position confidence fields** (Module 1) — additive, MINOR, once reliability-tested (`MODULE_INTERFACES.md`'s flagged gap).
2. **Arsenal/Ground-Ball confidence fields** (Modules 2, 4) — additive, MINOR, once their own-reliability gaps close.

Both were designed for in `MODULE_INTERFACES.md` specifically so their eventual arrival doesn't require a MAJOR bump — the schema already has room for them; they're absent now because there's no evidence to fill them with, not because the schema wasn't built to hold them.

## What is explicitly NOT contracted yet

Module 5 (Damage Suppression) has no output contract — per `MODULE_INTERFACES.md`, it has no production interface at all. Writing a contract for it would imply a publication commitment this research doesn't support.

## Observed evidence / Inference / Speculation

The contract structure directly reuses `milb-projections/contracts/*.schema.json`'s and `PORTING_GUIDE.md`'s already-observed, working conventions (Observed evidence). The versioning rules and the "designed for future fields" claim are Inference — a design decision this document makes, not a finding from data.

## Future work

Actually writing the JSON Schema files themselves (not just describing their structure) is implementation work, correctly deferred past this architecture/engineering-specification charter per its own scope boundary ("no implementation should begin").
