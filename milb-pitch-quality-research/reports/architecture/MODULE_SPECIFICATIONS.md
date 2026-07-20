# Module Specifications

Phase 2. Specifies the modules recommended by `reports/phase1c/MINIMUM_ARCHITECTURE.md`, now positioned relative to the real ecosystem mapped in `CURRENT_ECOSYSTEM_MAP.md`. Evidence unchanged from Phase 1A-1C is not re-derived here — this document is the module-level specification, not new analysis.

## Module 1: Physical Stuff

- **Scientific purpose**: quantify a pitcher's raw physical pitch characteristics (velocity, movement, spin) independent of outcomes.
- **Baseball question answered**: "How good are this pitcher's pitches, physically?"
- **Inputs**: `startSpeed`, `pfxX`/`pfxZ`, `spinRate` from the MLB Stats API live-feed (this research's pipeline). **Note for implementation**: `stuff_plus_aaa` sources the same conceptual features from Baseball Savant's `statcast-search-minors` instead, which additionally exposes `arm_angle` and a real `delta_run_exp` label — a richer source worth reconciling before implementation (see `FUTURE_EXPANSION.md`).
- **Outputs**: per-pitcher (and, pending family-restricted reliability, per-pitch-family) physical-trait scores.
- **Dependencies**: tracking-status gate (AAA + the 10 confirmed tracked Low-A venues only).
- **Consumers**: internal to Module 3 (Miss-Inducing Ability) and Module 4 (Ground-Ball Tendency) per the incremental-information findings; potential direct challenger/input to `stuff_plus_aaa`.
- **Confidence**: highest of any module — split-half reliability 0.91-0.99 (Phase 1B).
- **Coverage requirement**: tracked venues only.
- **Refresh cadence**: see `REFRESH_ARCHITECTURE.md`.
- **Research maturity**: reliability-confirmed; not yet benchmarked against `stuff_plus_aaa` (open item, `BENCHMARK_INTEGRATION.md`).
- **Known limitations**: spin-rate completeness gap even at tracked venues (Phase 1B); different public data source than `stuff_plus_aaa` uses, so a head-to-head comparison requires reconciling data sources first.

## Module 2: Arsenal Construction

- **Scientific purpose**: quantify what a pitcher throws (pitch mix, diversity), not how well any one pitch is thrown.
- **Baseball question answered**: "How is this pitcher's arsenal built?"
- **Inputs**: `pitch_type_code`, aggregated to family shares and Shannon entropy.
- **Outputs**: per-pitcher pitch-family shares and a diversity/entropy score.
- **Dependencies**: tracking-status gate (needs pitch-type identity, which is itself tracking-dependent).
- **Consumers**: Module 3 (largest single incremental-R² contributor to whiff rate, Phase 1C).
- **Confidence**: real, independent incremental information confirmed (Phase 1C); own reliability not separately tested.
- **Coverage requirement**: tracked venues only.
- **Research maturity**: contributes real information in a pooled test; family-restricted reliability untested — flagged since Phase 1B, still the top open item before this module could be considered validated on its own.
- **Known limitations**: no consumer for this construct currently exists on the live site — `stuff_plus_aaa` doesn't decompose by pitch family (explicitly "no pitch-type identity" in its own feature set).

## Module 3: Miss-Inducing Ability

- **Scientific purpose**: quantify realized swing-and-miss outcomes and how much of them is explained vs. unexplained by physical traits and arsenal.
- **Baseball question answered**: "Does this pitcher get swings and misses, and how much of that is 'stuff' vs. something else?"
- **Inputs**: whiff rate (swing-conditional), Modules 1-2's outputs, location (zone rate).
- **Outputs**: per-pitcher whiff rate with an explicit stuff/mix/location decomposition.
- **Dependencies**: Modules 1-2 as covariates, not hard inputs (whiff rate itself is computable at any tracked venue independent of them).
- **Consumers**: potential incremental-value comparison point against `stuff_plus_aaa`'s `delta_run_exp`-based score, since both ultimately relate to pitch effectiveness.
- **Confidence**: moderate reliability (split-half r=0.33-0.51, Phase 1B); not redundant with Modules 1-2 (R²=0.228 total, most of it unexplained — Phase 1C).
- **Coverage requirement**: tracked venues (Branch A of this module); a parallel, much-weaker outcome-only version exists for untracked venues (Module 6).
- **Research maturity**: reliability-confirmed and non-redundancy-confirmed; not yet compared against `stuff_plus_aaa`'s run-value label directly.
- **Known limitations**: ~77% of its own variance remains unexplained by every family tested.

## Module 4: Ground-Ball Tendency

- **Scientific purpose**: quantify realized batted-ball trajectory outcomes and their relationship to physical traits (chiefly movement).
- **Baseball question answered**: "Does this pitcher generate ground balls, and is that explained by pitch movement?"
- **Inputs**: `hitData.trajectory`, Module 1's movement output.
- **Outputs**: per-pitcher ground-ball rate.
- **Dependencies**: batted-ball volume (≥15 in this research's pilot threshold) on top of the tracking gate.
- **Consumers**: none currently on the live site — no existing system decomposes ground-ball tendency for MiLB pitchers.
- **Confidence**: real relationship to movement (R²=0.134, driven mostly by movement — Phase 1C); own reliability never separately tested.
- **Coverage requirement**: tracked venues, batted-ball-volume gated.
- **Research maturity**: relationship confirmed; own-metric reliability is the concrete next step before this is more than a descriptive research finding.
- **Known limitations**: could be dominated by noise at typical batted-ball sample sizes — untested.

## Module 5: Damage Suppression (research-only)

- **Scientific purpose**: quantify contact quality allowed (merges `avg_launch_speed` and `hard_hit_rate`, confirmed redundant at r=0.72, Phase 1C).
- **Baseball question answered**: "How hard is this pitcher hit when contact occurs?"
- **Inputs**: `hitData.launchSpeed`.
- **Outputs**: per-pitcher average exit velocity allowed / hard-hit rate (one merged metric, not two).
- **Dependencies**: batted-ball volume gate.
- **Consumers**: none currently — this is the one module this charter explicitly does not recommend building a production consumer for yet.
- **Confidence**: lowest of the tracked-venue modules — nearly unexplained by anything else measured (1.9-3.7% R², Phase 1C), and its own reliability was never tested (only its relationship to other modules was).
- **Coverage requirement**: tracked venues, batted-ball-volume gated.
- **Research maturity**: research-only, explicitly, per `reports/phase1c/PRODUCTION_COMPONENT_RECOMMENDATIONS.md`.
- **Known limitations**: could be dominated by park, defense, or batted-ball luck rather than pitcher skill — genuinely unresolved.

## Module 6: Outcome-Only Result Rate

- **Scientific purpose**: the one construct recoverable at AA/High-A/untracked-Low-A venues — a pitch-type-agnostic whiff-rate proxy.
- **Baseball question answered**: "Does this pitcher miss bats, at a level where no tracking exists?"
- **Inputs**: swing/whiff outcome flags only (no tracking fields available by construction).
- **Outputs**: per-pitcher outcome-only whiff rate.
- **Dependencies**: none beyond the outcome data every level has.
- **Consumers**: the only module capable of providing any coverage outside AAA/tracked-Low-A — a real gap-filler role, not a duplicate of anything.
- **Confidence**: weak (Chain 5: R²=0.016 from the only available predictor, Phase 1C) — the thinnest module in this architecture.
- **Coverage requirement**: all levels.
- **Research maturity**: identifiability-confirmed as weak-but-real; this is the ceiling of what's achievable at untracked venues, not a placeholder awaiting more work.
- **Known limitations**: cannot be pitch-type-specific, cannot support any of Modules 1-2, 4-5's questions.

## Explicitly not specified as modules (evidence says no)

- **Command/location** as a standalone module — split-half r=0.07-0.19 (Phase 1B), weakest-supported construct tested.
- **Called-strike rate**, anywhere — r=-0.10 to +0.06 at every level/sample size (Phase 1B), the clearest negative finding in this research.
- **A single universal composite** — rejected on redundancy and variance-structure grounds (Phase 1C).

## Observed evidence / Inference / Speculation

Every confidence/maturity claim above cites a specific Phase 1B/1C finding. The "Consumers" fields are Inference — connecting module outputs to plausible real integration points identified in `CURRENT_ECOSYSTEM_MAP.md` — not confirmed integrations (none exist yet; that's precisely what `CONSUMER_AUDIT.md` interrogates).

## Future work

Reconciling Module 1's MLB-Stats-API-sourced features against `stuff_plus_aaa`'s Baseball-Savant-sourced features (different endpoints, an `arm_angle` field this research never extracted) is the single most concrete next step before any of these modules can be honestly compared to the live champion.
