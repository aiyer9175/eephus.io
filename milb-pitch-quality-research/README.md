# MiLB Pitch-Quality Research

## What this is

The external research effort that `milb-projections/` (a separate, read-only handoff package) was built to support. That package's own docs repeatedly refer to "the future external MiLB pitch-quality research effort — outside this charter"; this directory is that effort.

The governing document is the **Pitch-Quality Research Charter** (Phase I), reproduced in full context in this repository's commit history. Its central question:

> What aspects of latent pitcher and arsenal quality are actually identifiable from the information available at each MiLB level, and how should those signals be modeled if they exist?

This is explicitly **not** a "build MiLB Stuff+" project. It is an investigation into what's recoverable, trustworthy, stable, and portable — and the architecture (if any) should follow from that evidence, not be assumed up front.

## Status: Phase 1, data audit pilot

Phase 1's job is to determine available, trustworthy, stable, and portable information *before* any model architecture is chosen. This first pass is a **bounded pilot**, not the full charter-scale build:

- One complete season (2025), venue-stratified sample across all four public MiLB levels (AAA/AA/High-A/Low-A), pulled from the public MLB Stats API.
- Real Coverage/Trust/Missingness/Field-Availability matrices built from that sample — see `reports/`.
- Eephus champion-benchmark comparisons are **schema-only** for now (see `DECISION_LEDGER.md` #1) — the private source systems `milb-projections/` was built to export from aren't accessible from this environment. Real benchmark integration is flagged as a clear next step, not fabricated or skipped silently.
- The full charter (reliability program, negative controls, promotion-seam validation, identifiability investigation, latent-quality modeling) is intentionally **not attempted yet** — it's only meaningful once the coverage findings from this pilot are in. See `reports/DATA_AUDIT_REPORT.md` for what's proposed next.

## Relationship to `milb-projections/`

`milb-projections/` is a separate package with its own documented contract: it is additive, read-only with respect to Eephus's production systems, and is not modified by this research effort. This directory consumes its schemas/definitions/fixtures for context but does not alter anything under `milb-projections/`.

## Layout

```
milb-pitch-quality-research/
├── README.md              — this file
├── PILOT_SCOPE.md          — exact sampling methodology for the Phase 1 pilot, and why
├── DECISION_LEDGER.md      — consequential choices made while building this pilot
├── scripts/                — MLB Stats API pull pipeline + matrix builders (see PILOT_SCOPE.md)
├── data_cache/              — gitignored; raw pulled JSON, regenerable, never committed
└── reports/                 — ARCHITECTURE_MAP.md, the four Phase 1 matrices, DATA_AUDIT_REPORT.md
```

## Start here

Read `PILOT_SCOPE.md`, then `reports/DATA_AUDIT_REPORT.md`.
