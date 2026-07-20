# Final Architecture Ruling

Required Final Deliverable, and the capstone of this charter. Answers the charter's Required Final Questions directly, synthesizing all 15 phase documents and the 3 prior research phases. No new claims are introduced here.

## What modules should exist?

Four, scheduled for near-term implementation: **Arsenal Construction** (Module 2), **Miss-Inducing Ability** in both its tracked (Module 3) and outcome-only (Module 6) variants, and **Ground-Ball Tendency** (Module 4) — each pending the specific reliability gap named for it in `IMPLEMENTATION_ROADMAP.md`. **Physical Stuff** (Module 1) exists as a specification but is redirected toward an integration proposal for the already-live `stuff_plus_aaa`, not a guaranteed new standalone surface, pending Implementation Phase A's empirical outcome.

## Which modules should not exist?

**Damage Suppression** (Module 5), held back entirely (`ARCHITECTURE_SIMPLIFICATION.md`) — real, non-redundant information by Phase 1C's own measure, but so weakly connected to everything else tested (1.9-3.7% R²) and so completely untested on its own reliability that building it now would violate this charter's "scientific correctness" principle. **Command/zone-rate** and **called-strike rate** as scored outputs anywhere — the two clearest negative findings across the entire three-phase research program. **A single universal composite score** — rejected on redundancy and variance-structure grounds, independent of the module-count question.

## How should tracked and outcome-only systems coexist?

As two structurally separate branches sharing a vocabulary and join key but never merged into one score (`TRACKING_BRANCH_ARCHITECTURE.md`) — gated by venue-level tracking status (a Phase 1A finding, re-confirmed structurally sound by every later phase), not level. The gate is designed to absorb future tracking expansion without redesign, tested against several concrete scenarios in `FUTURE_EXPANSION.md`.

## How should uncertainty propagate?

Not by default inheritance — by measured incremental-R² relationship between modules (`UNCERTAINTY_ARCHITECTURE.md`). Where that relationship is weak (Module 3 vs. its upstream inputs: 22.8% explained, 77.2% not; Module 5 vs. everything: 1.9-3.7%), a module's own directly-measured reliability governs its uncertainty statement, not its inputs' reliability.

## How does this integrate with the existing Eephus ecosystem?

This is the question this charter's ecosystem survey most changed the answer to. The original research charter's assumed champion (`pitcher_ewar`/Contact+/SEM-derived components) has **zero presence on the live website** — a private repo not accessible from this environment. The real, live, relevant system is `stuff_plus_aaa` (provisional, AAA-only, physics-only, run-value-trained), and this research's modules should be understood as **complementary/challenger to that system specifically**, not as filling a gap in a system (`pitcher_ewar`) the website never actually surfaces. `sem_plus`/`rem_plus` are validated, real, but a different grain and level entirely — not duplicative, not directly integrable either, without a translation layer that doesn't exist (per the same `career_outcome_plus` blocker Phase 1A already found).

## Which modules feed pitcher eWAR?

**None, currently, and none can, in this environment** — `pitcher_ewar` is private and inaccessible, unchanged since Phase 1A. This is stated as a hard fact, not a design gap this charter failed to close.

## Which feed projections?

**None** — `CURRENT_ECOSYSTEM_MAP.md` found no dedicated MiLB pitcher-projection system exists anywhere in this repo to feed. `playing-time-model/` is confirmed hitter-only.

## Which feed player pages?

Modules 2, 3, 4, 6, once their respective implementation phases close and a real consumer is built — per `CONSUMER_MAP.md`'s target state, landing on the same PROSPX pitcher-card surface `stuff_plus_aaa` already occupies. Module 1, contingent on Implementation Phase A's outcome (either as `stuff_plus_aaa` input features, or as its own display, not both).

## Which remain research-only?

Module 5 (Damage Suppression), indefinitely, per its own held-back status. Modules 2 and 4 are research-only *until* their respective reliability gaps close (Implementation Phases B and D) — a temporary, not permanent, classification.

## What benchmark evidence still remains outstanding?

The two-endpoint reconciliation (MLB Stats API vs. Baseball Savant minors search) is the single most consequential outstanding item — it blocks a rigorous answer to whether Module 1 duplicates `stuff_plus_aaa`, which in turn blocks Implementation Phase A, which this roadmap places first precisely because everything downstream is easier to reason about once it resolves. The private `pitcher_ewar` benchmark remains outstanding independent of anything this charter could do.

## What implementation order minimizes technical debt?

The order in `IMPLEMENTATION_ROADMAP.md`: Phase A (resolve the duplication risk) before B/C/D (build the non-overlapping modules), each phase required to ship a real wired consumer as part of its exit criteria — not a documented intent, per the `milb-decision-plus` cautionary precedent this charter found and took seriously (`CONSUMER_AUDIT.md`).

## Acceptance criteria, checked

| Criterion | Met? |
|---|---|
| Every production module has a single scientific purpose | Yes — `MODULE_BOOK.md` |
| Every module has at least one documented downstream consumer | **Target-state yes, current-state no** — honestly stated in `CONSUMER_MAP.md`, not glossed over |
| No unnecessary duplication remains | Identified and addressed for the one real case found (Module 1 / `stuff_plus_aaa`) — not fully resolved, since resolution requires empirical work outside this charter's scope |
| Tracked and outcome-only architectures fully specified | Yes — `TRACKING_BRANCH_ARCHITECTURE.md` |
| Integration with existing Eephus systems explicitly documented | Yes, and substantially corrected from the original charter's assumptions — `CURRENT_ECOSYSTEM_MAP.md` |
| Uncertainty propagation defined | Yes — `UNCERTAINTY_ARCHITECTURE.md` |
| Publication strategy complete | Yes — `PUBLICATION_ARCHITECTURE.md` |
| Refresh architecture complete | Yes — `REFRESH_ARCHITECTURE.md` |
| Implementation order justified | Yes — `IMPLEMENTATION_ROADMAP.md` |
| Remaining benchmark blockers explicitly documented | Yes — `KNOWN_GAPS.md` |

## Observed evidence / Inference / Speculation

This ruling is Inference synthesizing every prior document in this charter and the three research phases — it introduces no new evidence of its own. Where acceptance criteria are only partially met (the consumer criterion, chiefly), that is stated plainly rather than rounded up to "complete."

## Future work

`IMPLEMENTATION_ROADMAP.md`'s four phases, in order, are the concrete next steps. This ruling does not authorize starting them — per the charter's own governing principle, architecture is complete; implementation is a separate, future decision.
