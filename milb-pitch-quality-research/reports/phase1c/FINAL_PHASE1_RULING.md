# Final Phase 1 Ruling

Deliverable 9. Synthesizes Phases 1A (coverage/trust/missingness), 1B (identifiability/reliability/variance), and 1C (incremental information/redundancy/architecture) into one ruling. This closes the charter's Phase 1; it does not authorize implementation by itself — see "which components proceed directly to implementation" below for what that would actually require.

## Can a scientifically defensible MiLB pitch-quality system be built?

**Yes, for a defined subset — not as a universal MiLB pitch-quality system.**

The evidence across all three phases converges on the same boundary: pitch-tracking coverage is a venue property (Phase 1A), physical-field identifiability tracks that same boundary regardless of level (Phase 1B), and the feature families available at tracked venues carry real, largely non-redundant incremental information (Phase 1C). A system built for AAA + the 10 identified tracked Low-A venues, using the six-module architecture in `reports/phase1c/MINIMUM_ARCHITECTURE.md`, is scientifically defensible on the evidence gathered. A system claiming to cover MiLB uniformly is not.

## What should it look like?

The six-module, tracking-status-gated architecture from `MINIMUM_ARCHITECTURE.md`:
1. Physical Stuff (velocity + movement + spin) — highest-confidence module, tracked venues only.
2. Arsenal Construction (pitch mix/diversity) — tracked venues only, contributes real independent information.
3. Miss-Inducing Ability (whiff rate) — tracked venues, moderate reliability, not redundant with 1-2.
4. Ground-Ball Tendency — tracked venues, real relationship to Movement, own reliability unconfirmed.
5. Damage Suppression (merged avg. launch speed + hard-hit rate) — research-only pending its own reliability check.
6. Outcome-Only Result Rate (whiff rate, all-levels) — the sole module covering AA/High-A/untracked Low-A.

No single composite score. Per `ARCHITECTURE_COMPARISON.md`, the evidence directly contradicts collapsing these into one number — they're largely independent (`FEATURE_REDUNDANCY_REPORT.md`) and driven by different upstream factors (`LATENT_CONSTRUCT_GRAPH.md`).

## What should it not attempt to estimate?

- **Command / location**, as a scored production output. Split-half reliability 0.07-0.19 at typical sample sizes across three phases of testing — the weakest-supported tracked-only construct in this entire research program.
- **Called-strike rate**, as a pitcher-skill signal. r=-0.10 to +0.06 at every level and every tested sample size (Phase 1B) — the single clearest negative finding across all three phases.
- **A single "Stuff+"-style composite.** Rejected on redundancy and variance-structure grounds (Phase 1C), not merely on the charter's own stated preference against one.
- **Anything requiring release deception, tunneling, or true intended-target command.** Not identifiable from any data source available to this research (`NON_IDENTIFIABLE_CONSTRUCTS.md`, Phase 1B) — a structural limitation of public MLB Stats API data, not a sample-size problem.
- **Cross-level or MLB-translated value.** Blocked on real Eephus benchmarks, unresolved since Phase 1A (`DECISION_LEDGER.md` #1).

## Which architectures should be abandoned?

- **Universal single-score architecture** — contradicted by the redundancy and incremental-information evidence.
- **Level-indexed architecture family** — contradicted by Phase 1A's venue-level (not level-level) coverage finding, reconfirmed by nothing in Phase 1B/1C overturning it.
- **Any architecture treating command or called-strike rate as a scored output** — not an architecture rejection per se, but a hard constraint on any architecture that is adopted.

## Which components should proceed directly to implementation?

**None, strictly speaking — not yet.** Every module in `MINIMUM_ARCHITECTURE.md` is evidence-supported at the *research* level (real signal, measured reliability or incremental information), but "proceed directly to implementation" would mean building production code, and three concrete gaps stand between this ruling and that:
1. Modules 4 and 5's *own* reliability was never tested (only their relationship to other modules) — `PRODUCTION_COMPONENT_RECOMMENDATIONS.md` flags both explicitly.
2. Module 2's family-restricted reliability (fastball-quality-specifically, not pooled-across-types) was never tested — flagged since Phase 1B, still open.
3. Real Eephus champion-benchmark data remains unavailable in this environment — without it, no incremental-value claim over the existing pitcher ecosystem can be made, which the research contract's own required-comparisons section treats as a precondition for any production recommendation.

Modules 1 and 3 (Physical Stuff, Miss-Inducing Ability) are the closest to implementation-ready — best-supported reliability, confirmed non-redundant, real incremental contribution to a downstream outcome — but even these should wait for the Eephus-benchmark blocker to clear before a genuine "should this replace/augment the champion" conversation can happen.

## Which should remain research-only?

Damage Suppression (Module 5) explicitly, per `PRODUCTION_COMPONENT_RECOMMENDATIONS.md` — real redundancy-informed design (merging two correlated metrics into one), but its connection to everything else tested is so weak (1.9-3.7% R²) that its own internal reliability needs confirming before it's treated as more than a descriptive research metric.

## Which future research questions remain?

In priority order, given what would unblock the most (per `MINIMUM_ARCHITECTURE.md`'s and `PRODUCTION_COMPONENT_RECOMMENDATIONS.md`'s flagged gaps):

1. **Real Eephus benchmark integration** — the single largest, longest-standing blocker (open since Phase 1A).
2. **Family-restricted reliability** for Arsenal Construction (fastball/breaking/offspeed quality specifically) — flagged in every phase since 1B.
3. **Own-reliability checks** for Ground-Ball Tendency and Damage Suppression — never tested, only their relationships to other modules were.
4. **A larger-sample retest of Command/chase-rate reliability** — the stabilization curve was still rising, not flat, at the largest tested threshold (Phase 1B); worth resolving "needs more data" vs. "not recoverable" before final exclusion.
5. **Sequencing** — count-state fields exist in the dataset but were never built into a feature family, at any phase.
6. **A dedicated missingness-mechanism study** for the spin-rate completeness gap noted at tracked venues (Phase 1C's `INFORMATION_CONTENT_REPORT.md`... actually Phase 1B's, referenced here).
7. **Multi-season data** for any development-trajectory/pitch-aging work — this entire research program has been single-season (2025) throughout.

## Observed evidence / Inference / Speculation

This ruling is Inference synthesizing Observed evidence already established and cited across all three phases' reports — it introduces no new numbers of its own. Where it recommends against implementation (the "None, strictly speaking" answer above), that is a deliberate, evidence-grounded caution, not a default hedge — the specific gaps blocking implementation are named, not vague.

## Future work

Items 1-7 above, in the stated priority order, constitute the concrete Phase 2 prerequisite list. Per the charter's own governing principle, none of this ruling should be read as a green light to build a MiLB Stuff+ system — it's a scientifically bounded recommendation for a smaller, evidence-supported subset, with explicit gates before even that subset reaches production.
