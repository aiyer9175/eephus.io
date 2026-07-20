# Information Flow — Phase 1C

Deliverable 8. Complete flow from raw public data to pitcher-ecosystem integration, emphasizing clarity and traceability over any single phase's detail (each stage links to the report that established it).

```mermaid
graph TD
    RAW["Raw public data\nMLB Stats API live-feed endpoint\nstatsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"]

    CLEAN["Cleaning / extraction\nscripts/pull_schedule.py, sample_team_stratified.py,\npull_game_feeds.py, build_pitch_dataset_v2.py\n1,402 games cached, 408,606 pitches, 2,524 pitchers"]

    GATE{"Tracking-status gate\nvenue property, not level property\nPhase 1A: AAA 30/30, AA 0/31, High-A 0/30, Low-A 10/31"}

    subgraph TrackedFamilies["Tracked-venue feature families"]
        FVEL[Velocity]
        FMOV[Movement]
        FSPIN[Spin]
        FMIX[Pitch mix/diversity]
        FLOC[Location - zone_rate]
        FHIT["hitData - launch speed, trajectory, hardness"]
    end

    subgraph UntrackedFamilies["Outcome-only feature families - all venues"]
        FOUT["Call outcome, count state, swing/whiff flags"]
    end

    subgraph LatentA["Latent constructs - tracked"]
        STUFF["Physical Stuff\nModule 1"]
        ARSENAL["Arsenal Construction\nModule 2"]
        MISS["Miss-Inducing Ability\nModule 3"]
        GBTEND["Ground-Ball Tendency\nModule 4"]
        DAMAGE["Damage Suppression (research-only)\nModule 5"]
        COMMAND["Command - EXCLUDED, unsupported"]
    end

    subgraph LatentB["Latent constructs - untracked"]
        OUTRATE["Outcome-Only Result Rate\nModule 6"]
    end

    PQOUT["Pitch-quality outputs\nper-module scores, NOT one composite\nsee ARCHITECTURE_COMPARISON.md"]

    ECOSYS["Pitcher ecosystem integration\nBLOCKED: real Eephus benchmarks unavailable\nDECISION_LEDGER.md #1"]

    RAW --> CLEAN --> GATE
    GATE -->|tracked| TrackedFamilies
    GATE -->|untracked| UntrackedFamilies

    FVEL --> STUFF
    FMOV --> STUFF
    FSPIN --> STUFF
    FMIX --> ARSENAL
    STUFF --> MISS
    ARSENAL --> MISS
    FLOC --> MISS
    FMOV --> GBTEND
    FHIT --> DAMAGE
    FLOC -.->|not supported, r=0.07-0.19| COMMAND

    FOUT --> OUTRATE

    STUFF --> PQOUT
    ARSENAL --> PQOUT
    MISS --> PQOUT
    GBTEND --> PQOUT
    DAMAGE -.->|research-only, not yet a scored output| PQOUT
    OUTRATE --> PQOUT

    PQOUT -.-> ECOSYS
```

## Observed evidence

Every node and edge in this diagram is traceable to a specific artifact:

| Stage | Artifact |
|---|---|
| Raw data → cleaning | `scripts/pull_schedule.py`, `scripts/phase1b/sample_team_stratified.py`, `scripts/pull_game_feeds.py`, `scripts/phase1c/build_pitch_dataset_v2.py` |
| Tracking-status gate | `reports/DATA_AUDIT_REPORT.md` (Phase 1A) |
| Feature families | `reports/phase1c/FEATURE_FAMILY_INVENTORY.md` |
| Latent constructs | `reports/phase1c/LATENT_CONSTRUCT_GRAPH.md`, `MINIMUM_ARCHITECTURE.md` |
| Production classification | `reports/phase1c/PRODUCTION_COMPONENT_RECOMMENDATIONS.md` |
| Ecosystem integration block | `milb-pitch-quality-research/DECISION_LEDGER.md` #1 |

## Inference

The flow is deliberately **not** a single pipeline — it forks at the tracking-status gate into two structurally different paths that never fully recombine (Module 6's outcome-only rate is a peer of the tracked modules, not an input to them), and it stops short of ecosystem integration entirely, blocked on a dependency (real Eephus benchmarks) outside this research's control.

## Speculation

None — this deliverable is a synthesis diagram of already-established findings, not a source of new claims.

## Future work

The `ECOSYS` node is the clearest concrete blocker in this diagram: nothing downstream of it can be built or validated until real Eephus benchmark exports are supplied, independent of how much further Phase 1 research work happens.
