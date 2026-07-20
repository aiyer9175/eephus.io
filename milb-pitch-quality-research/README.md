# MiLB Pitch-Quality Research

## What this is

The external research effort that `milb-projections/` (a separate, read-only handoff package) was built to support. That package's own docs repeatedly refer to "the future external MiLB pitch-quality research effort — outside this charter"; this directory is that effort.

The governing document is the **Pitch-Quality Research Charter** (Phase I), reproduced in full context in this repository's commit history. Its central question:

> What aspects of latent pitcher and arsenal quality are actually identifiable from the information available at each MiLB level, and how should those signals be modeled if they exist?

This is explicitly **not** a "build MiLB Stuff+" project. It is an investigation into what's recoverable, trustworthy, stable, and portable — and the architecture (if any) should follow from that evidence, not be assumed up front.

## Status: Phase 1 research (1A+1B+1C) + Architecture Charter + Engineering Charter all complete — see reports/engineering/FINAL_ENGINEERING_RULING.md

**Phase 1A** (bounded pilot) determined available, trustworthy, and portable information: a venue-stratified sample across all 4 levels, real Coverage/Trust/Missingness/Field-Availability matrices (`reports/`), and the headline finding that pitch-tracking coverage is a venue property, not a level property (AAA universal, AA/High-A absent, Low-A confined to 10 spring-training-complex venues). See `reports/DATA_AUDIT_REPORT.md`.

**Phase 1B** answered five further scientific questions — what information exists, which latent pitching constructs are identifiable, how much of observed performance is stable signal vs. context vs. noise — through descriptive statistics, reliability analysis, and variance decomposition on a much larger, pitcher-volume-adequate dataset (a team/venue-stratified pull, ~1,400 games, 408,606 pitches, 2,524 pitchers). Nine deliverables under `reports/phase1b/`, starting with `IDENTIFIABILITY_REPORT.md` (primary) and `PHASE_2_RECOMMENDATION.md`.

Headline Phase 1B findings: velocity/spin/movement are highly identifiable wherever tracking exists (split-half reliability 0.91-0.99, regardless of level); most outcome-only metrics are weak-to-unidentifiable at pilot sample sizes (called-strike rate is essentially unreliable everywhere); command (zone-rate proxy) doesn't stabilize within this pilot's sample sizes even where tracking exists. Full detail in `reports/phase1b/IDENTIFIABILITY_REPORT.md`.

**Phase 1C** (this pass) completes the research audit: which feature families contain unique information vs. duplicate each other, which latent constructs deserve independent production modules, and what the minimum scientifically defensible architecture is. No new data pull — reused Phase 1B's cached games, extended with `hitData` fields (weak contact/ground-ball/damage) that Phase 1B had flagged but not computed. Nine deliverables under `reports/phase1c/`, culminating in `FINAL_PHASE1_RULING.md`.

Headline Phase 1C findings: of 45 tested family pairs, exactly one (avg. launch speed ↔ hard-hit rate, r=0.72) is genuinely redundant — everything else is largely independent; pitch mix/diversity contributes the single largest incremental-R² block to whiff rate (0.071, larger than velocity+movement+spin combined); damage suppression is barely explained by anything measured (1.9-3.7% R²) — a real structural finding, not a data gap; recommended architecture is six evidence-supported modules gated by tracking status, not one universal score. Full detail in `reports/phase1c/FINAL_PHASE1_RULING.md`.

All three research phases share the same standing constraints:
- Eephus champion-benchmark comparisons are **schema-only** (see `DECISION_LEDGER.md` #1) — the private source systems `milb-projections/` was built to export from aren't accessible from this environment. Still the largest open blocker to any incremental-value claim.
- No predictive/ML model has been built. The charter instructs against one unless "absolutely necessary to answer an identifiability question" — nothing so far has required it.

**The Architecture & Integration Charter** (`reports/architecture/`, 22 deliverables) turns the completed research into a production blueprint — and substantially corrects the original charter's assumed champion. A three-agent survey of the actual `eephus.io` website found that "pitcher eWAR/Contact+/SEM-derived components" (the original charter's named champion) have **zero presence on the live site** — that stack is a private repo not accessible from this environment. What's actually live is `stuff_plus_aaa` (an in-house AAA physics-only model, provisional verdict) and `sem_plus`/`rem_plus` (validated, but a different level/grain entirely). This research now uses a **tiered-champion framing**: `stuff_plus_aaa`/`stuff_plus_external` are the champion for the pitch-quality/arsenal layer this research addresses; the private `pitcher_ewar` stack remains the champion for full pitcher value, a layer this research doesn't touch. Full ruling in `reports/architecture/FINAL_ARCHITECTURE_RULING.md`.

Recommended near-term implementation: 4 of 6 specified modules (Arsenal Construction, Miss-Inducing Ability × 2 variants, Ground-Ball Tendency), each pending a named reliability gap; Physical Stuff redirected toward reconciling with `stuff_plus_aaa` rather than a guaranteed new surface; Damage Suppression held back entirely. See `reports/architecture/IMPLEMENTATION_ROADMAP.md`.

**The Engineering Charter** (`reports/engineering/`, 13 deliverables) resolves the Stuff+ reconciliation question definitively (`STUFF_PLUS_RECONCILIATION.md`: a precise hybrid — Module 1 augments `stuff_plus_aaa` where it operates in AAA, extends independently into tracked Low-A where it doesn't — blocked on reconciling two different public data endpoints), specifies every module's implementable interface (`MODULE_INTERFACES.md`), and reaches a split GO/NO-GO on Module 1 (`MODULE1_READINESS.md`): GO for its independent pipeline and a new PROSPX pitcher-card field, NO-GO for the `stuff_plus_aaa`-augmentation path until the data-source blocker clears. Honest bottom line (`FINAL_ENGINEERING_RULING.md`): every module across four charters of work is still fully unimplemented — documentation and specification are complete, but zero production code exists yet, and no module currently has a real (built, not just designed) downstream consumer.

## Relationship to `milb-projections/`

`milb-projections/` is a separate package with its own documented contract: it is additive, read-only with respect to Eephus's production systems, and is not modified by this research effort. This directory consumes its schemas/definitions/fixtures for context but does not alter anything under `milb-projections/`.

## Layout

```
milb-pitch-quality-research/
├── README.md              — this file
├── PILOT_SCOPE.md          — Phase 1A venue-stratified sampling methodology, and why
├── DECISION_LEDGER.md      — consequential choices made across all three phases
├── scripts/                — Phase 1A pull pipeline + matrix builders (see PILOT_SCOPE.md)
│   ├── phase1b/             — Phase 1B: team/venue-stratified sampler, pitch-dataset builder,
│   │                          reliability/variance-decomposition/promotion-seam analysis
│   └── phase1c/             — Phase 1C: hitData-extended dataset builder,
│                              incremental-information/redundancy analysis
├── data_cache/              — gitignored; raw pulled JSON + derived pitch_dataset*.parquet,
│                              regenerable, never committed
└── reports/                 — Phase 1A: ARCHITECTURE_MAP.md, the four coverage matrices,
                               DATA_AUDIT_REPORT.md
    ├── phase1b/             — Phase 1B's 9 deliverables + RELIABILITY_STATS.json,
    │                          VARIANCE_STATS.json, PROMOTION_SEAM_STATS.json
    ├── phase1c/             — Phase 1C's 9 deliverables + INCREMENTAL_STATS.json,
    │                          REDUNDANCY_STATS.json, culminating in FINAL_PHASE1_RULING.md
    ├── architecture/         — Architecture & Integration Charter's 22 deliverables
    │                          (15 phase docs + SYSTEM_ARCHITECTURE/MODULE_BOOK/DATA_FLOW/
    │                          CONSUMER_MAP/FINAL_ARCHITECTURE_RULING/DECISION_LEDGER/
    │                          KNOWN_GAPS — the last two scoped to this charter, distinct
    │                          from the package-root files of the same name)
    └── engineering/          — Engineering Charter's 13 deliverables: frozen architecture,
                               module interfaces, Stuff+ reconciliation, consumer wiring/
                               validation, data contracts, refresh/publication specs,
                               engineering standards, Module 1 readiness, implementation
                               sequence, culminating in FINAL_ENGINEERING_RULING.md
```

## Start here

Read `reports/engineering/FINAL_ENGINEERING_RULING.md` first — it's the current end state of this entire research program: what's frozen, what's specified, what's blocked, and the one concrete unblocked next action (Module 1's independent implementation path). From there: `reports/engineering/STUFF_PLUS_RECONCILIATION.md` (the central open question, now resolved) and `reports/engineering/MODULE1_READINESS.md` (the GO/NO-GO verdict). For the research/architecture detail underneath: `reports/architecture/FINAL_ARCHITECTURE_RULING.md`, `PILOT_SCOPE.md` and `reports/DATA_AUDIT_REPORT.md` (1A), `reports/phase1b/IDENTIFIABILITY_REPORT.md` (1B), `reports/phase1c/MINIMUM_ARCHITECTURE.md` (1C), `reports/architecture/CURRENT_ECOSYSTEM_MAP.md` (the real-website survey that reframed the champion question).
