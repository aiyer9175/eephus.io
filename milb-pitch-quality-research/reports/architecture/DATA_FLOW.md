# Data Flow

Required Final Deliverable. The polished, final version of `DEPENDENCY_GRAPH.md` + `TRACKING_BRANCH_ARCHITECTURE.md`, read top-to-bottom as the single reference for "where does a number on the website ultimately come from."

```mermaid
graph TD
    A["1. Raw public data\nMLB Stats API (this research) OR\nBaseball Savant minors search (stuff_plus_aaa)\n-- UNRECONCILED, see Implementation Phase A"]
    B["2. Cleaning\nschedule/game-feed pull, JSON cache, parse"]
    C["3. Normalization\ntracking-status gate (venue-keyed, seasonal re-check)\npitch-family mapping, season-third bucketing, min-volume gates"]
    D["4. Feature engineering\n9 feature families, split TRACKED_ONLY / ALL_LEVELS"]
    E["5. Latent modules\nModules 1-6, per MODULE_BOOK.md"]
    F["6. Pitch-quality ecosystem layer\nthis research's outputs + stuff_plus_aaa + stuff_plus_external\n-- separate scores, shared vocabulary, no composite"]
    G["7. Pitcher ecosystem (real, live)\nstuff_plus_aaa, stuff_plus_external, sem_plus, rem_plus, pal_conversion"]
    H["8. Pitcher eWAR (private, blocked)\nLayer 2 champion -- not reachable from this system"]
    I["9. Player pages\nPROSPX pitcher cards"]
    J["10. Leaderboards\n/mlbstats/ -- season-grain, different modules feed this today"]
    K["11. Website\nstatic JSON, build_site.py, nightly rsync, single writer"]
    L["12. Future models\nsee FUTURE_EXPANSION.md"]

    A --> B --> C --> D --> E --> F
    F --> G
    G --> I
    G --> J
    F -.->|blocked, DECISION_LEDGER #1| H
    I --> K
    J --> K
    K --> L
```

## What each numbered stage actually requires, per this charter's other documents

| Stage | Governing document |
|---|---|
| 1. Raw data | `DEPENDENCY_GRAPH.md` (the two-endpoint problem) |
| 3. Normalization / gate | `TRACKING_BRANCH_ARCHITECTURE.md` |
| 5. Modules | `MODULE_SPECIFICATIONS.md`, `MODULE_BOOK.md` |
| 6-7. Ecosystem integration | `BENCHMARK_INTEGRATION.md`, `CONSUMER_AUDIT.md` |
| 9-10. Website surfaces | `WEBSITE_INFORMATION_ARCHITECTURE.md` |
| 11. Publication mechanics | `PUBLICATION_ARCHITECTURE.md`, `REFRESH_ARCHITECTURE.md` |
| 12. Extensibility | `FUTURE_EXPANSION.md` |

## Observed evidence / Inference / Speculation

Purely a synthesis diagram — no new claims. Every stage and arrow traces to a specific document listed above.

## Future work

Stage 6 → 8 (the dashed, blocked arrow) is the single most consequential open item in this entire data flow — everything upstream of it can be built and validated; nothing downstream of it can, in this environment, regardless of how much implementation work happens.
