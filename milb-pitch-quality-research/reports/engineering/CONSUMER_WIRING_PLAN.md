# Consumer Wiring Plan

Phase 3. Per the Global Eephus Engineering Rule, "documentation alone does not constitute integration" — this plan exists precisely because `milb-decision-plus/` proved a fully-built, validated system can ship with zero real consumers (`CURRENT_ECOSYSTEM_MAP.md`). Every module below gets a real design, not a restated intention.

## Module 1 (Physical Stuff)

- **Current consumers**: none.
- **Future consumer**: `stuff_plus_aaa`'s feature pipeline, per `STUFF_PLUS_RECONCILIATION.md`'s verdict — **blocked on the data-source reconciliation**, not implementable today.
- **Interim consumer** (does not require the blocker resolved): a **new PROSPX pitcher-card field**, positioned alongside the existing `stuff_plus_aaa` pill, showing raw velocity/movement/spin — this requires only Module 1's own pipeline (MLB Stats API-sourced), no reconciliation with Savant's endpoint.
- **Missing consumer work**: a new sidecar JSON export (`data/physical_stuff.json`, mirroring `stuff_plus_aaa.json`'s existing shape), a `build_site.py`/pitcher-card template change, a `model_registry.json` entry, a `glossary.json` entry.
- **Required API endpoints**: none — static JSON, per the site's existing convention (`CURRENT_ECOSYSTEM_MAP.md`).
- **Required publication**: add `data/physical_stuff.json` to `deploy/publish_paths.txt`.
- **Required website integration**: pitcher-card template change (small, additive).
- **Required documentation**: glossary entry + model-registry entry (`verdict: "provisional"` at best, per `PUBLICATION_ARCHITECTURE.md`).
- **Required refresh**: new stage in `run_monthly.py --daily`.
- **Required tests**: schema validation test (mirrors `test_fixtures_match_contracts.py`'s pattern from `milb-projections/`), a `test_generated_docs_in_sync.py`-style check if a new doc is auto-generated.
- **Required monitoring**: freshness stamp (`last_checked`/`stale`/`artifact_age_days`), matching `model_registry.py`'s existing convention.

## Module 2 (Arsenal Construction)

- **Current consumers**: none.
- **Future consumer**: internal only — feeds Module 3's decomposition. No player-facing consumer is recommended until family-restricted reliability is tested (`MODULE_INTERFACES.md`).
- **Design decision**: **do not wire a public consumer for this module yet.** Per the charter's own instruction ("if a module has no consumer, design one or remove the module"), the honest design here is to keep Module 2 as **internal infrastructure feeding Module 3**, not to force a premature public surface. This satisfies "has a consumer" (Module 3 is a real, defined consumer) without overclaiming readiness.

## Module 3a (Miss-Inducing Ability, tracked)

- **Current consumers**: none.
- **Future consumer**: PROSPX pitcher cards (same surface as Module 1, natural pairing).
- **Missing consumer work**: same pattern as Module 1 (sidecar JSON, card template, registry/glossary entries).
- **Dependencies**: none blocking — doesn't require the `stuff_plus_aaa` reconciliation to ship, since it's not a Stuff+-adjacent feature-engineering question, it's its own metric.

## Module 3b / Module 6 (Outcome-Only Result Rate)

- **Current consumers**: none.
- **Future consumer**: PROSPX pitcher cards **for pitchers at untracked venues specifically** — the one module that could give AA/High-A pitchers any pitch-quality-adjacent card content at all, where today they have none (`stuff_plus_aaa` doesn't cover them).
- **Design note**: must ship with the `evidence_strength: "limited"` field (`MODULE_INTERFACES.md`) surfaced in the UI, not just the API — a card showing a bare number here would misrepresent R²=0.016 worth of evidence as something more.

## Module 4 (Ground-Ball Tendency)

- **Current consumers**: none.
- **Future consumer**: none recommended until own-metric reliability is tested (`MODULE_INTERFACES.md`) — same "don't force a premature consumer" design as Module 2.
- **Design decision**: remains a research-tracked construct, revisited once its reliability gap closes (`IMPLEMENTATION_SEQUENCE.md`).

## Module 5 (Damage Suppression)

- **Current consumers**: none.
- **Future consumer**: **none proposed.** Per `MODULE_INTERFACES.md`, this module intentionally has no production interface at all — there is nothing to wire.

## Cross-module: what a "real" consumer requires (the milb-decision-plus lesson)

`milb-decision-plus/`'s own `REPORT.md` states an "Integration Rule" (its projected K%/BB% should feed the main projection engine) that was never implemented — the clearest evidence in this codebase that a documented intention is not a consumer. This plan avoids repeating that pattern by only counting a consumer as "future" if it has (a) a named file/template that would need to change, and (b) no dependency on work outside this charter's visibility. Modules 2, 4, and 5 do not meet that bar today and are correctly left without a forced consumer, per the charter's own "design one or remove the module" instruction — the module isn't removed (real evidence supports its existence as internal infrastructure or research), but it doesn't get a fabricated public consumer either.

## Observed evidence / Inference / Speculation

The specific file paths and mechanisms (`deploy/publish_paths.txt`, `run_monthly.py --daily`, `model_registry.json`'s schema) are Observed evidence from the ecosystem survey. Which modules "should" get a consumer now vs. later is Inference, directly following the reliability/evidence thresholds already established in `MODULE_INTERFACES.md`.

## Future work

Modules 2 and 4 are the two modules whose consumer status should be revisited first, gated on the reliability tests named in `IMPLEMENTATION_SEQUENCE.md`.
