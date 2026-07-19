# Porting Guide

Status: scaffolded in Phase 2; per-adapter instructions added as each adapter is built (Phases 3-6); privacy-safe fixture/schema instructions finalized in Phase 12.

## For the external builder

1. **Pull public data yourself.** Raw pitch-by-pitch data, boxscores, schedules, rosters, and team/affiliate/league/venue reference tables are all available from the public MLB Stats API. Don't look for them in this package — they're intentionally not here (see `config/artifact_inventory.yaml`, `PUBLIC`/`NOT_NEEDED` entries).
2. **Understand the schema before requesting real data.** Every exportable asset has a schema in `contracts/` and a synthetic fixture in `fixtures/` with identical shape, units, and null behavior — validate your pipeline against the fixture first.
3. **Request private exports through the documented path, not by asking for raw source code.** Each `PRIVATE_EXPORT_REQUIRED` asset in `config/artifact_inventory.yaml` names the adapter that produces it (`adapters/export_*.py`) and the environment variable that controls its output location. Run the adapter (or ask Will to run it) to regenerate the real export — do not request the underlying model source, which is proprietary and not licensed for redistribution.
4. **Read the definition doc before using any field as a feature.** `definitions/*.md` states explicitly which fields are safe as model features, which are labels/benchmarks only, and which are context/metadata only.
5. **Read `PITCH_QUALITY_RESEARCH_CONTRACT.md` before writing a single line of the pitch-quality model.** It states what you may and may not claim about raw pitch-outcome data.
6. **Read `TEMPORAL_INTEGRITY.md` before doing any walk-forward evaluation.** Several benchmarks are current-model backfills, not true historical snapshots — using them naively will overstate model performance.

## Validation checklist per asset

For each asset you plan to use:
- [ ] Load the fixture in `fixtures/`, confirm your ingestion code handles its schema without modification.
- [ ] Read the matching `contracts/*.schema.json` — confirm required vs. optional columns, types, enums.
- [ ] Read the matching `definitions/*.md` — confirm feature/label/context classification and known limitations.
- [ ] Check `manifests/BENCHMARK_MANIFEST.yaml` for `allowed_uses`/`prohibited_uses` and `historical_status`.
- [ ] If doing walk-forward evaluation, confirm the asset's `historical_status` supports it (only `TRUE_HISTORICAL_SNAPSHOT` and correctly-labeled `RECONSTRUCTED_AS_OF` rows are safe; `CURRENT_MODEL_BACKFILL` is descriptive-only).

## For whoever maintains this package

Re-running an adapter never mutates the authoritative source — it only reads from the path in its config and writes a new export. Re-run adapters whenever the authoritative source refreshes; there is no caching/staleness logic to fight — each run reflects the source's current state at run time, stamped with the source's own `model_version`/`as_of_date`.
