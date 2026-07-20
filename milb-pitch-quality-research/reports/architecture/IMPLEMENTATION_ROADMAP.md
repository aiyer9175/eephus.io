# Implementation Roadmap

Phase 15 and a Required Final Deliverable. Ordered by confidence, downstream value, implementation risk, and ecosystem impact — reflecting `ARCHITECTURE_SIMPLIFICATION.md`'s net result, not the original six-module list unchanged. **No implementation should begin from this document alone** — it defines order and exit criteria; actual coding is future work outside this charter's scope (per the charter's own "No production implementation should begin until this architectural blueprint is complete," now complete, but implementation itself is the next charter, not this one).

## Implementation Phase A: Module 1 / `stuff_plus_aaa` reconciliation (do first)

- **Purpose**: resolve the largest open risk in this entire architecture — whether Module 1 duplicates `stuff_plus_aaa` — before any other module is scheduled, since the answer changes how much of this research ships as new surfaces vs. integration proposals.
- **Dependencies**: read access to `stuff_plus_aaa`'s actual training data (Baseball Savant `statcast-search-minors`) or a documented reason it can't be obtained.
- **Required benchmarks**: `stuff_plus_aaa`'s own eval artifact (`stuff_plus_aaa_eval.json`, already read in `BENCHMARK_INTEGRATION.md`) as the baseline to beat or complement.
- **Required validation**: does adding Module 1's raw-trait features to `stuff_plus_aaa`'s LightGBM model improve its pitcher-level stability (currently 0.28) or forward-gate performance (currently r=0.505 vs. MLB K%, n=18)? A real, answerable empirical question.
- **Expected deliverables**: a data-source reconciliation decision (adopt Savant, extend the MLB Stats API pipeline, or maintain both) and an integration test result.
- **Exit criteria**: either (a) demonstrated improvement to `stuff_plus_aaa` from Module 1's features, recommending integration rather than a standalone surface, or (b) demonstrated independence, recommending Module 1 proceed as its own surface after all — either outcome unblocks the rest of this roadmap.

## Implementation Phase B: Module 2 (Arsenal Construction) family-restricted reliability

- **Purpose**: close the one reliability gap standing between Module 2's confirmed incremental-information value (largest single R² contributor to whiff rate, Phase 1C) and its readiness for `PRODUCTION_CLASSIFICATION.md`'s "Player Page Metric" tier.
- **Dependencies**: none beyond this research's existing pitch-level dataset (`data_cache/derived/pitch_dataset_v2.parquet`).
- **Required benchmarks**: none external — this is a reliability re-test, not a comparison.
- **Required validation**: split-half/month-to-month reliability computed *within* each pitch family (fastball-specifically, breaking-specifically, offspeed-specifically), not pooled across them as Phase 1B/1C did.
- **Expected deliverables**: a reliability report matching Phase 1B's format, scoped to per-family metrics.
- **Exit criteria**: family-restricted reliability clears a threshold comparable to Module 1's pooled physical-trait reliability (a bar, not a guess — set relative to what's already been shown achievable in this research).

## Implementation Phase C: Module 3/6 (Miss-Inducing Ability, both variants) — implement and wire a real consumer

- **Purpose**: ship the module with the strongest already-demonstrated non-redundant value (Phase 1C) and the clearest unfilled gap (Module 6 covers levels nothing else touches).
- **Dependencies**: Phase A's outcome informs whether Module 3 references Module 1's reconciled feature set or its own.
- **Required benchmarks**: none directly comparable exists for whiff-rate-with-decomposition at MiLB levels (`CONSUMER_AUDIT.md`).
- **Required validation**: the `PUBLICATION_ARCHITECTURE.md` gates (stabilization threshold, glossary entry, model-registry entry) must all be met before publish, not treated as optional polish.
- **Expected deliverables**: production code, a wired consumer (a real route or JSON payload actually read by `prospect-tracker`'s build — per the `milb-decision-plus` lesson in `CONSUMER_AUDIT.md`, not a documented-but-unread intent), glossary + model-registry entries.
- **Exit criteria**: the module is live on at least one real page and appears in `SITE_MAP.md`'s generated route index.

## Implementation Phase D: Module 4 (Ground-Ball Tendency) own-reliability test

- **Purpose**: close the same kind of gap as Phase B, for the module with the second-strongest physical-relationship evidence (R²=0.134, Movement-driven).
- **Dependencies**: none beyond the existing dataset.
- **Required validation**: split-half/month-to-month reliability of `ground_ball_rate` itself (never separately tested — Phase 1C only tested its relationship to Movement).
- **Expected deliverables**: a reliability report.
- **Exit criteria**: reliability clears a defensible threshold; if it doesn't, Module 4 joins Module 5 in held-back status per `ARCHITECTURE_SIMPLIFICATION.md`'s pattern rather than shipping regardless.

## Held back, not scheduled: Module 5 (Damage Suppression)

Per `ARCHITECTURE_SIMPLIFICATION.md`, Module 5 does not get an implementation phase in this roadmap. It remains a documented, evidence-motivated research finding, revisited only if a future reliability test (unscheduled, contingent) changes its status.

## Not implementable in any phase: value-integration with `pitcher_ewar`

No implementation phase exists for connecting any of this research's outputs to `pitcher_ewar`/full pitcher value — this remains blocked on private data access, unchanged since Phase 1A (`KNOWN_GAPS.md`), and no phase of this roadmap can resolve it.

## Observed evidence / Inference / Speculation

Phase ordering (A before B/C/D) is Inference — Phase A's outcome plausibly changes what the other phases build, so resolving it first minimizes wasted work, but this is a project-management judgment, not an empirical finding. Every phase's "required validation" is Observed evidence about what's currently missing (traced to specific gaps named across Phase 1B/1C and this charter's own documents).

## Future work

This roadmap is itself the "future work" output of the entire three-phase research program plus this architecture charter — its phases are the concrete next charter(s), not further architecture work.
