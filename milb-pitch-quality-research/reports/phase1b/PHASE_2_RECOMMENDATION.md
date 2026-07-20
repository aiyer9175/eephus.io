# Phase 2 Recommendation — Phase 1B

Deliverable 9. Should Phase 2 begin, on what subset, should any levels/families be excluded.

## Observed evidence, synthesized

- Physical-field identifiability (velocity, spin, movement) is strong and consistent at both tracked populations tested (AAA, tracked Low-A) — `IDENTIFIABILITY_REPORT.md`.
- Outcome-field identifiability is weak-to-moderate everywhere, with whiff rate as the one metric showing real (if partial) signal, and called-strike rate showing essentially none — `IDENTIFIABILITY_REPORT.md`, `NOISE_AND_STABILITY_REPORT.md`.
- Command (zone-rate proxy) is not yet identifiable at any tested sample size, though with a rising trend — `IDENTIFIABILITY_REPORT.md`.
- No venue/park effect was detected on outcome metrics at any level, at this sample size — `VARIANCE_DECOMPOSITION.md`.
- Real Eephus champion-benchmark data (park factors, pitcher eWAR) remains unavailable in this environment — `DECISION_LEDGER.md` #1, unchanged since Phase 1A.

## Recommendation: Yes, Phase 2 should begin — narrowly scoped, not as a universal build

**Should Phase 2 begin?** Yes, on the subset the evidence actually supports (per `ARCHITECTURE_RECOMMENDATION.md`'s two-branch structure), not as an attempt to build one MiLB-wide pitch-quality system.

**Should more auditing occur first?** Yes, in two specific places before any model-shaped work starts:
1. Family-restricted reliability for fastball/breaking/offspeed quality (flagged repeatedly — `LATENT_CONSTRUCT_INVENTORY.md`, `IDENTIFIABILITY_REPORT.md`) — this phase established pooled-across-pitch-type reliability, not the family-specific claim a real arsenal model needs.
2. A larger-sample retest of command/chase-rate reliability, given the still-rising stabilization curve — worth knowing whether it plateaus below or above a usable threshold before deciding whether command belongs in Branch A's feature set.

**Should multiple architectures be built?** Yes — Branch A (tracked-venue, physical-field-based) and Branch B (outcome-only, pitcher-aggregate) are both worth building, but as genuinely separate systems with different feature sets and different validation standards, not as tiers of one universal model.

**Should some levels be excluded?** Not by level — by venue-tracking status, per `ARCHITECTURE_RECOMMENDATION.md`. AA and High-A are excluded from Branch A (no tracked venues in this pilot's sample), not from the research program overall — they remain eligible for Branch B.

**Should some pitch families be excluded?** Not yet determinable — this is precisely what the flagged family-restricted reliability work (above) needs to answer. No family should be assumed viable or excluded without that test.

**Should some constructs be abandoned?** Two candidates, both provisionally rather than permanently:
- **Called-strike rate as a pitcher-skill signal** — the weakest finding in this entire phase (near-zero-to-negative reliability, no rising trend, at every level and every tested sample size). Recommend excluding it from any Phase 2 feature set unless a specific reason to revisit emerges (e.g., access to umpire/catcher context that could explain and correct for its noise).
- **Command via raw zone-rate** — not abandoned, but not includable as-is; recommend either the larger-sample retest or a redesigned (distance-based) proxy before inclusion, not zone-rate in its current form.

## What Phase 2 should NOT attempt yet

Per `ARCHITECTURE_RECOMMENDATION.md`: no single universal metric, no level-indexed architecture family, no command feature built on the current zone-rate proxy. Per the standing charter constraint carried since Phase 1A: no real Eephus champion-benchmark comparison until private exports are actually supplied (`DECISION_LEDGER.md` #1) — this is not resolved by Phase 1B and remains the single largest open blocker to any incremental-value claim.

## Inference

The evidence base built across Phase 1A and 1B is now strong enough to justify a scoped Phase 2 (tracked-venue physical-field modeling, plus a much narrower outcome-only whiff-rate-centric Branch B), but not strong enough yet to justify committing to a specific family-level or command-inclusive feature set — those need the two flagged follow-up audits first.

## Speculation

If family-restricted reliability holds up for fastball quality specifically but not for breaking/offspeed (plausible given breaking/offspeed pitches are thrown less often per pitcher, hence smaller per-family samples), Phase 2's first deliverable might reasonably be a fastball-only quality metric before attempting a full-arsenal one — but this is speculation to be tested, not a recommendation to build on directly.

## Future work

The two flagged audits (family-restricted reliability; larger-sample command retest) are the concrete, immediate next steps — smaller in scope than either Phase 1A or Phase 1B, and should resolve before Phase 2's architecture is finalized in code. Real Eephus benchmark integration remains the standing, larger blocker for any eventual incremental-value ruling, independent of this phase's findings.
