# Architecture Comparison — Phase 1C

Deliverable 5. Evaluated against evidence accumulated across all three phases. No winner assumed here — `MINIMUM_ARCHITECTURE.md` makes the final call.

## One universal model (single score combining everything)

- **Strengths**: simplest to communicate; one number per pitcher.
- **Weaknesses**: `LATENT_CONSTRUCT_GRAPH.md` shows the underlying constructs have genuinely different upstream drivers (Movement drives ground-ball tendency; Mix/Location drive whiff; nothing tested drives damage suppression) — collapsing them loses exactly the structure Phase 1C exists to surface. `FEATURE_REDUNDANCY_REPORT.md` shows most families aren't redundant, so there's little statistical justification for combining them either.
- **Scientific assumptions**: that all constructs share a common latent factor worth compressing to one dimension — contradicted by the near-independence found in the redundancy analysis.
- **Maintenance burden**: low (one model) but at the cost of opacity — a change in the composite is hard to attribute.
- **Extensibility**: poor — adding a new signal means re-deriving the whole composite's weighting.
- **Redundancy risk**: paradoxically higher, not lower — a single score built from correlated-but-distinct inputs (e.g. velocity/movement/spin, r=0.27-0.33) risks implicitly double-counting shared variance without a principled way to detect it.
- **Interpretability**: low — a single "pitch quality" number can't answer "quality at what."
- **Verdict**: not supported by this phase's evidence.

## Tracking-specific architecture (Branch A/B split — Phase 1B's own recommendation)

- **Strengths**: directly matches the hard data boundary found in Phase 1A/1B (pitch-type identity itself absent at untracked venues) — not an arbitrary split.
- **Weaknesses**: Branch B (outcome-only) has very little recoverable structure (Chain 5: 1.6% R²) — a real architecture, but a thin one.
- **Scientific assumptions**: that tracking availability, not level, is the right stratifying variable — directly evidenced (Phase 1A/1B), not assumed.
- **Maintenance burden**: moderate — two codepaths, but each is internally simpler than a universal model trying to paper over the data-availability gap.
- **Extensibility**: good — Branch A can grow richer (sequencing, family-restricted reliability) independent of Branch B.
- **Redundancy risk**: low — the two branches use almost entirely disjoint inputs by construction.
- **Interpretability**: good — a Branch A output can be labeled "physical/tracked-signal" honestly, a Branch B output "outcome-only."
- **Verdict**: supported by evidence; carried forward as this phase's starting point.

## Level-specific architecture (one model per level)

- **Strengths**: intuitive, matches how the sport is organized.
- **Weaknesses**: directly contradicted — tracking coverage doesn't align with level (Low-A splits into tracked/untracked; AAA and tracked Low-A behave alike). Phase 1B already rejected this explicitly.
- **Scientific assumptions**: that level is a good proxy for information availability — falsified by Phase 1A's venue-level finding.
- **Verdict**: rejected, per Phase 1B and reconfirmed by nothing new this phase contradicting that rejection.

## Pitch-family architecture (separate model per fastball/breaking/offspeed)

- **Strengths**: `LATENT_CONSTRUCT_GRAPH.md`'s Mix/Diversity family contributes real, independent incremental information (0.071 R² increment to whiff, the single largest block) — pitch identity clearly matters.
- **Weaknesses**: family-restricted reliability was never separately tested (flagged repeatedly since Phase 1B) — this phase's incremental analysis uses *pooled-across-family* metrics as inputs, not per-family-restricted ones, so it cannot yet confirm a pitch-family-specific model would be reliable, only that pitch-family membership matters as a covariate.
- **Scientific assumptions**: that a pitcher's fastball quality and breaking-ball quality are separable enough to model independently — plausible given the nested-variance findings in Phase 1B (family explains more variance than pitcher for velocity/spin/movement) but not confirmed at the reliability level.
- **Maintenance burden**: higher — N pitch-family models instead of one.
- **Extensibility**: good once/if family-restricted reliability is confirmed.
- **Redundancy risk**: low, if family-restricted samples are large enough to be genuinely distinct estimates.
- **Interpretability**: high, if it works — "this pitcher's fastball grades well, breaking ball doesn't" is exactly the kind of statement scouts and analysts want.
- **Verdict**: promising but not yet supported at the reliability level — a Phase 2 prerequisite, not a Phase 1C conclusion.

## Hierarchical latent architecture (nested nan Pitcher > Family > residual, as in Phase 1B's variance decomposition)

- **Strengths**: directly matches the actual variance structure found (`VARIANCE_DECOMPOSITION.md`, Phase 1B) — family-within-pitcher variance genuinely exceeds pitcher-level variance for the physical fields.
- **Weaknesses**: statistically more demanding (needs a real mixed-effects framework, not the method-of-moments approximation used so far) and harder to communicate than a flat per-pitcher score.
- **Scientific assumptions**: that the nesting structure (pitcher contains families) is the right hierarchy — well-supported by the variance decomposition.
- **Maintenance burden**: highest of the architectures considered — hierarchical models need careful re-fitting discipline.
- **Extensibility**: excellent — new pitch families or levels slot into the existing hierarchy.
- **Redundancy risk**: low by construction (variance is explicitly partitioned, not left to implicit correlation).
- **Interpretability**: moderate — powerful for someone who understands variance decomposition, less immediately legible to a general audience than a flat score.
- **Verdict**: the most evidence-aligned option for Branch A specifically, but a heavier lift than this phase's evidence alone justifies committing to immediately — see `MINIMUM_ARCHITECTURE.md`.

## Hybrid architecture (Branch A/B split, with Branch A internally family-aware but not fully hierarchical)

- **Strengths**: takes the confirmed parts of the hierarchical case (family matters, tracking-status gates everything) without committing to the heavier mixed-effects machinery before family-restricted reliability is confirmed.
- **Weaknesses**: a deliberate middle ground — less statistically elegant than the full hierarchical case, less simple than one flat model.
- **Verdict**: this is what `MINIMUM_ARCHITECTURE.md` actually recommends — evidence-supported now, with a clear upgrade path to the full hierarchical case once family-restricted reliability is tested.

## Component architecture (independent modules, one per confirmed-independent construct)

- **Strengths**: directly matches `FEATURE_REDUNDANCY_REPORT.md`'s finding that most families are independent — a component per confirmed-independent construct avoids forcing correlated-but-distinct signals into one number.
- **Weaknesses**: more production surface area (more things to build, test, and maintain) than a universal model.
- **Scientific assumptions**: that each component's independence (measured here) is stable, not a sample-specific artifact — untested longitudinally.
- **Maintenance burden**: moderate-high, proportional to the number of confirmed components.
- **Extensibility**: excellent — new evidence can add or merge components without disturbing the others.
- **Redundancy risk**: lowest of all options considered, specifically because redundant pairs (`avg_launch_speed`/`hard_hit_rate`) get merged before becoming separate components.
- **Interpretability**: high — each component has a clear, named meaning.
- **Verdict**: supported by evidence; the organizing principle behind `MINIMUM_ARCHITECTURE.md`.

## Observed evidence / Inference / Speculation

The comparisons above are Observed evidence where they cite a specific number from this phase's or Phase 1B's JSON output, Inference where they connect that number to an architectural implication, and explicitly labeled Speculation where extrapolating beyond what's been tested (e.g. the pitch-family architecture's promise).
