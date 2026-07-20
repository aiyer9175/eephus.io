# System Architecture

Required Final Deliverable. Synthesizes `MODULE_SPECIFICATIONS.md`, `DEPENDENCY_GRAPH.md`, `TRACKING_BRANCH_ARCHITECTURE.md`, and `MODULE_INTERACTION.md` into one system-level view. Detail lives in those four documents; this is the map of the map.

## The system in one paragraph

A tracking-status-gated (not level-gated) pitch-quality subsystem, positioned as a **Layer 1 (pitch-quality/arsenal) challenger** to the already-live `stuff_plus_aaa`/`stuff_plus_external`, explicitly not attempting Layer 2 (full pitcher value, owned by the private, currently-inaccessible `pitcher_ewar` stack). Four modules are recommended for near-term implementation (Arsenal Construction, Miss-Inducing Ability × 2 variants, Ground-Ball Tendency); one (Physical Stuff) is redirected from a standalone surface toward an integration proposal for the existing `stuff_plus_aaa` model; one (Damage Suppression) is held back pending its own reliability confirmation.

## System diagram

```mermaid
graph TD
    RAW[Raw public data - two endpoints, unreconciled] --> GATE{Tracking-status gate}
    GATE -->|tracked| TRACKED[Tracked pathway - Modules 1,2,3,4,5]
    GATE -->|untracked| OUTCOME[Outcome-only pathway - Module 6]

    TRACKED --> INTEG{"Phase A: Module 1 vs stuff_plus_aaa"}
    INTEG -->|integrate| SPA[stuff_plus_aaa, enhanced]
    INTEG -->|independent| M1STANDALONE[Module 1, standalone]

    TRACKED --> M2[Module 2: Arsenal - pending reliability]
    TRACKED --> M3[Module 3: Miss-Inducing Ability]
    TRACKED --> M4[Module 4: Ground-Ball - pending reliability]
    TRACKED --> M5["Module 5: Damage Suppression - HELD BACK"]
    OUTCOME --> M6[Module 6: Result Rate]

    M2 --> M3
    M1STANDALONE -.-> M3
    SPA -.-> M3

    M3 --> CONSUMER{Real wired consumer - required, not optional}
    M4 --> CONSUMER
    M6 --> CONSUMER
    CONSUMER --> SITE[prospect-tracker live site]
```

## Five governing constraints this system satisfies

1. **Scientific correctness** — every module traces to a specific Phase 1B/1C reliability or incremental-R² number; nothing is included on predictive-performance grounds alone (`MODULE_SPECIFICATIONS.md`).
2. **Interpretability** — no universal composite; every module answers one stated baseball question (`ARCHITECTURE_COMPARISON.md`, Phase 1C).
3. **Ecosystem integration** — every module's consumer status is honestly audited, including the finding that none currently have one (`CONSUMER_AUDIT.md`) and the concrete requirement that implementation include wiring a real consumer, not just documenting an intent.
4. **Extensibility** — the tracking-status gate absorbs future tracking expansion without module redesign, tested against several concrete scenarios (`FUTURE_EXPANSION.md`).
5. **Long-term maintainability** — reuses existing infrastructure (`run_monthly.py`, `model_registry.json`, `glossary.json`, the nginx single-writer deploy model) rather than building parallel systems (`REFRESH_ARCHITECTURE.md`, `PUBLICATION_ARCHITECTURE.md`).

## Observed evidence / Inference / Speculation

This document is pure synthesis — every claim traces to one of the four cited detail documents, which in turn trace to Phase 1B/1C evidence or the ecosystem survey. No new claims are introduced here.

## Future work

See `IMPLEMENTATION_ROADMAP.md` for the concrete next phases.
