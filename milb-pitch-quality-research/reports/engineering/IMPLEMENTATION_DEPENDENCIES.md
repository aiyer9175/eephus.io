# Implementation Dependencies

Phase 7. Module ordering, shared utilities, and infrastructure reuse — "no module should duplicate infrastructure."

## Module ordering

Directly follows `REFRESH_EXECUTION_PLAN.md`'s dependency-respecting order: Module 1 and Module 2 first (parallelizable, no dependencies beyond the raw pipeline), then Module 3 variants and Module 4 (depend on 1-2 as covariates, not hard blockers — could technically build before 1-2 finish, but should ship after for interpretive consistency), Module 5 never scheduled for production. This mirrors `IMPLEMENTATION_SEQUENCE.md`'s rollout plan, restated here from the dependency-graph angle rather than the timeline angle.

## Shared utilities (already exist — reuse, don't rebuild)

- **`scripts/common.py`** (this research's pilot): HTTP fetch/retry, cache-path management, level/sportId mapping — every module's data pipeline should import from here, not reimplement.
- **`scripts/phase1c/build_pitch_dataset_v2.py`**'s extraction logic: the single source of truth for turning a raw game feed into pitch-level rows. No module should write its own parallel extraction.
- **`prospect-tracker/model_registry.py`**: freshness-stamping (`refresh_stamps()`, `stale`, `artifact_age_days`) — reuse directly rather than building a second freshness system for this research's modules.
- **`prospect-tracker/build_glossary_data.py`**'s pattern (script-driven glossary entries, not hand-JSON-editing) — if this research's modules need several related glossary entries, follow this precedent rather than hand-editing `glossary.json` directly.

## Common feature engineering

Modules 1, 2, 3, 4 all read from the same `pitch_dataset_v2` intermediate (`DATA_CONTRACTS.md`) — this is the one mandatory shared-computation point. No module should independently re-derive `is_whiff`/`is_called_strike`/etc. flags from raw `call_description` strings; those derivations live once, in the shared dataset builder.

## Reusable services

None of `stuff_plus_aaa`, `sem_plus`, or `rem_plus` expose a reusable *service* (no API, per `CURRENT_ECOSYSTEM_MAP.md` — everything is a batch script producing static JSON) — so "reusable services" in this codebase means reusable *scripts/modules*, not running services. This research's modules should follow the same pattern (batch Python scripts, static JSON output), not introduce the codebase's first live service.

## Configuration

Reuse `milb-projections/config/artifact_inventory.yaml`'s pattern (a single machine-readable manifest of what's public/private/internal) if this research's modules accumulate enough config surface to warrant one — not needed yet at 6 modules, flagged as a threshold to watch, not built preemptively (`ENGINEERING_STANDARDS.md`'s "no hidden dependencies" cuts against introducing config machinery before it's needed).

## Testing

Reuse `milb-projections/tests/test_fixtures_match_contracts.py`'s pattern (fixture-vs-contract schema validation, runnable without real data) and `prospect-tracker/test_generated_docs_in_sync.py`'s pattern (regenerate-and-byte-compare for any auto-generated doc) — both proven, both directly applicable once this research's modules have contracts (`DATA_CONTRACTS.md`) and any auto-generated docs.

## Monitoring

Reuse `model_registry.json`'s `last_checked`/`stale`/`artifact_age_days` fields — no new monitoring system needed.

## Infrastructure this research should NOT build

- A second static-site generator or publish path (`build_site.py`/`nightly-build.sh` already exist).
- A second glossary or model registry (`glossary.json`/`model_registry.json` already exist).
- A second freshness/staleness mechanism (`model_registry.py`'s already exists).
- A second raw-data cache convention (`scripts/common.py`'s already exists and is proven resumable).

## Observed evidence / Inference / Speculation

Every reused utility named above is Observed evidence (a real file in this repo, confirmed by the ecosystem survey or this research's own pilot work). The "should reuse, not rebuild" recommendations are Inference directly following Governing Philosophy #3 (ecosystem integration, no parallel systems) from the architecture charter.

## Future work

If module count grows meaningfully past the current 6, revisit the "no config machinery yet" call above — the threshold where a manifest becomes worth its own maintenance cost isn't crossed today, but isn't permanently zero either.
