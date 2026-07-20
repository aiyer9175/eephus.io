# Architecture Recommendation — Phase 1B

Deliverable 7. What architecture the evidence supports. Recommended only where supported — per the charter's explicit instruction not to force a single-architecture conclusion.

## Observed evidence, synthesized

Three separate pieces of evidence, each already established, converge on the same shape:

1. **Tracking coverage is a venue property** (Phase 1A): AAA universal, AA/High-A absent, Low-A confined to 10 FSL/spring-training-complex venues.
2. **Physical-field identifiability tracks tracking coverage, not level** (`IDENTIFIABILITY_REPORT.md`): velocity/spin/movement are highly identifiable at AAA and the tracked Low-A subset, not identifiable at all at AA/High-A or the untracked majority of Low-A.
3. **Outcome-field identifiability is roughly constant across levels, but weak everywhere** (`IDENTIFIABILITY_REPORT.md`): whiff rate is moderately identifiable at all 4 levels (r=0.33-0.51, no strong level pattern); called-strike rate and command are weak-to-unidentifiable at all 4 levels.

## Recommended architecture: tracking-status-gated, not level-gated

**A two-branch architecture is supported by the evidence; a single universal architecture and a purely level-indexed family of architectures are both contradicted by it.**

- **Branch A — tracked-venue pitch-quality analysis** (AAA + the 10 identified Low-A/FSL venues): can use velocity, movement, spin, and location fields; family-level (fastball/breaking/offspeed) decomposition is plausible per the nested-variance findings, though not yet validated at the family-restricted level (`LATENT_CONSTRUCT_INVENTORY.md`). This branch is NOT "the AAA architecture" — it should be defined by venue-tracking status and applied identically to AAA and the qualifying Low-A venues, since the evidence shows no reason to treat the physical fields differently between those two populations (Low-A tracked-subset reliability numbers are, if anything, marginally higher than AAA's).
- **Branch B — outcome-only analysis** (AA, High-A, the untracked majority of Low-A, and optionally also AAA/tracked-Low-A as a fallback/cross-check): limited to pitcher-aggregate result rates (whiff, swing, foul, in-play), never pitch-type-specific, given pitch type itself is unrecoverable without tracking. Called-strike rate and any zone/location-dependent metric should NOT be included in this branch's feature set at all — the evidence (near-zero-to-negative reliability, at every level) doesn't support treating it as signal anywhere, tracked or not.

This is not "AAA gets a full arsenal model, lower levels get a fastball-centric model" (one of the charter's own illustrative — not prescriptive — examples). The evidence supports a coarser, cleaner split than a level-by-level gradient: **can this specific venue's pitches be measured at all**, then, separately, **which outcome metrics carry real signal regardless of measurement source**.

## What the evidence does not support

- **A single universal metric or score** combining physical and outcome signal into one number: the two signal families have different variance structure, different confounds (opponent/umpire/catcher for outcomes; none of that for physical fields), and different levels of identifiability. Collapsing them would hide exactly the distinction Phase 1B exists to surface.
- **A level-indexed architecture family** (one model per level): contradicted directly by Low-A's split tracking status and by outcome-metric reliability not varying meaningfully by level.
- **Command/location as a first-class feature in either branch**, given the current proxy (zone rate): the evidence (near-zero reliability at typical sample sizes, residual-dominated variance decomposition) doesn't support building on it yet. It's a candidate for future inclusion pending the proxy or sample-size improvements noted in `IDENTIFIABILITY_REPORT.md` and `NOISE_AND_STABILITY_REPORT.md`, not a rejected construct forever.

## Inference

The tracking-status boundary discovered in Phase 1A turns out to be architecturally load-bearing, not just a data-coverage footnote — it's the actual fault line the evidence wants the system built around, more than level is.

## Speculation

If Branch A's family-restricted reliability (not yet tested) holds up, a pitch-family-nested structure within Branch A (rather than a flat per-pitcher structure) may be the more natural fit, given the nested decomposition already shows family explaining more variance than pitcher identity for the physical fields. Speculative pending the future work flagged in `LATENT_CONSTRUCT_INVENTORY.md`.

## Future work

Confirm Branch A's family-level reliability before committing to a nested-vs-flat structure within it. Confirm whether Branch B's whiff-rate signal, the one outcome metric with real reliability, is worth a dedicated architecture on its own or is better treated as a single feature within whatever the existing Eephus FI-runs-based approach already does at those levels (see `PHASE_2_RECOMMENDATION.md`).
