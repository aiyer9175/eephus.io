# MiLB Pitch-Quality Research

## What this is

The external research effort that `milb-projections/` (a separate, read-only handoff package) was built to support. That package's own docs repeatedly refer to "the future external MiLB pitch-quality research effort — outside this charter"; this directory is that effort.

The governing document is the **Pitch-Quality Research Charter** (Phase I), reproduced in full context in this repository's commit history. Its central question:

> What aspects of latent pitcher and arsenal quality are actually identifiable from the information available at each MiLB level, and how should those signals be modeled if they exist?

This is explicitly **not** a "build MiLB Stuff+" project. It is an investigation into what's recoverable, trustworthy, stable, and portable — and the architecture (if any) should follow from that evidence, not be assumed up front.

## Status: Phase 1B, identifiability / information-content / noise isolation

**Phase 1A** (bounded pilot) determined available, trustworthy, and portable information: a venue-stratified sample across all 4 levels, real Coverage/Trust/Missingness/Field-Availability matrices (`reports/`), and the headline finding that pitch-tracking coverage is a venue property, not a level property (AAA universal, AA/High-A absent, Low-A confined to 10 spring-training-complex venues). See `reports/DATA_AUDIT_REPORT.md`.

**Phase 1B** (this pass) answers five further scientific questions — what information exists, which latent pitching constructs are identifiable, how much of observed performance is stable signal vs. context vs. noise — through descriptive statistics, reliability analysis, and variance decomposition on a much larger, pitcher-volume-adequate dataset (a team/venue-stratified pull, ~1,400 games, 408,606 pitches, 2,524 pitchers). Nine deliverables under `reports/phase1b/`, starting with `IDENTIFIABILITY_REPORT.md` (primary) and `PHASE_2_RECOMMENDATION.md`.

Headline Phase 1B findings: velocity/spin/movement are highly identifiable wherever tracking exists (split-half reliability 0.91-0.99, regardless of level); most outcome-only metrics are weak-to-unidentifiable at pilot sample sizes (called-strike rate is essentially unreliable everywhere); command (zone-rate proxy) doesn't stabilize within this pilot's sample sizes even where tracking exists. Full detail in `reports/phase1b/IDENTIFIABILITY_REPORT.md`.

Both phases share the same standing constraints:
- Eephus champion-benchmark comparisons are **schema-only** (see `DECISION_LEDGER.md` #1) — the private source systems `milb-projections/` was built to export from aren't accessible from this environment. Still the largest open blocker to any incremental-value claim.
- No predictive/ML model has been built. The charter instructs against one unless "absolutely necessary to answer an identifiability question" — nothing so far has required it.

## Relationship to `milb-projections/`

`milb-projections/` is a separate package with its own documented contract: it is additive, read-only with respect to Eephus's production systems, and is not modified by this research effort. This directory consumes its schemas/definitions/fixtures for context but does not alter anything under `milb-projections/`.

## Layout

```
milb-pitch-quality-research/
├── README.md              — this file
├── PILOT_SCOPE.md          — Phase 1A venue-stratified sampling methodology, and why
├── DECISION_LEDGER.md      — consequential choices made across both phases
├── scripts/                — Phase 1A pull pipeline + matrix builders (see PILOT_SCOPE.md)
│   └── phase1b/             — Phase 1B: team/venue-stratified sampler, pitch-dataset builder,
│                              reliability/variance-decomposition/promotion-seam analysis
├── data_cache/              — gitignored; raw pulled JSON + derived pitch_dataset.parquet,
│                              regenerable, never committed
└── reports/                 — Phase 1A: ARCHITECTURE_MAP.md, the four coverage matrices,
                               DATA_AUDIT_REPORT.md
    └── phase1b/             — Phase 1B's 9 deliverables + RELIABILITY_STATS.json,
                               VARIANCE_STATS.json, PROMOTION_SEAM_STATS.json
```

## Start here

Read `PILOT_SCOPE.md` and `reports/DATA_AUDIT_REPORT.md` for Phase 1A, then `reports/phase1b/IDENTIFIABILITY_REPORT.md` (primary) and `reports/phase1b/PHASE_2_RECOMMENDATION.md` for Phase 1B.
