# Architecture Simplification

Phase 14. Attempts to merge modules — succeeding only where the charter's four conditions all hold (scientific meaning preserved, unique information not lost, consumers satisfied, interpretability improves).

## Merge attempt 1: Module 1 (Stuff) into `stuff_plus_aaa`

- **Scientific meaning preserved?** Partially — `stuff_plus_aaa` predicts run value from physical features; Module 1 reports the physical features themselves. Folding Module 1 entirely into `stuff_plus_aaa` would lose the raw-trait layer that `BENCHMARK_INTEGRATION.md` found is far more reliable (0.91-0.99 vs. 0.28) than the run-value output built from it.
- **Verdict**: **do not fully merge — but do not build Module 1 as an independent standalone production surface either.** The right simplification is narrower: propose Module 1's features as *additional inputs* to `stuff_plus_aaa`'s existing model (per `BENCHMARK_INTEGRATION.md`'s future-work item), rather than shipping a second, parallel "stuff" score. This satisfies "prefer fewer well-justified modules" without losing Module 1's information.

## Merge attempt 2: Module 3 (tracked) and Module 6 (outcome-only) into one "Whiff Rate" module

- **Scientific meaning preserved?** No — `TRACKING_BRANCH_ARCHITECTURE.md` already established these operate in fundamentally different reliability regimes (R²=0.228 explained vs. R²=0.016). Merging them into one module/score would either overstate the outcome-only branch's precision or understate the tracked branch's.
- **Verdict**: **do not merge.** Keep as one module family with two clearly-labeled variants, per the existing design — this isn't a simplification opportunity, it's a place where apparent simplicity would actively mislead.

## Merge attempt 3: Module 4 (Ground-Ball) into Module 1 (Stuff), since Movement predicts most of it

- **Scientific meaning preserved?** No — Module 4 is an *outcome* (realized ground-ball rate), Module 1 is a *physical trait* (movement). R²=0.134, not 1.0 — Movement explains most but not all of Module 4's variance, and the unexplained portion is real, distinct information (or noise not yet characterized; either way, not identical to Movement).
- **Verdict**: **do not merge.** This mirrors the charter's own illustrative caution against combining unrelated concepts "simply because they correlate."

## Merge attempt 4: Module 5 (Damage Suppression) — should it exist as a module at all?

- **Scientific meaning preserved?** N/A — the question here isn't merging, it's whether Module 5 should exist as a distinct module or be dropped from this architecture entirely.
- **Unique information?** Real (per `FEATURE_REDUNDANCY_REPORT.md`, avg. launch speed and hard-hit rate aren't redundant with anything else measured) but the module's connection to the rest of the architecture is nearly nonexistent (1.9-3.7% R²) and its own reliability is untested.
- **Consumers satisfied?** No consumer exists (`CONSUMER_AUDIT.md`).
- **Verdict**: **simplify by demotion, not merge** — Module 5 should not be built as a production module in this implementation cycle. It remains a named, evidence-motivated research construct (kept in `MODULE_SPECIFICATIONS.md` for traceability) but is excluded from `IMPLEMENTATION_ROADMAP.md`'s actual build scope until its own reliability is tested. This is the architecture's single largest simplification: six specified modules, effectively five candidates for near-term implementation (Module 5 held back), one of those five (Module 1) redirected from a standalone surface into an integration proposal rather than a new production surface.

## What doesn't simplify further

Modules 2 (Arsenal) and Module 3/6 (Miss-Inducing Ability, both variants) resist every merge attempt tried above and have no existing-system overlap (`CONSUMER_AUDIT.md`) — they are the architecture's most defensible standalone components as currently specified.

## Net result of this simplification pass

| Before | After |
|---|---|
| 6 modules, all specified as standalone production candidates | 4 modules proceed as standalone candidates (2, 3-tracked, 3-outcome/Module 6, 4) |
| Module 1 as a new standalone surface | Module 1 redirected to an integration proposal for `stuff_plus_aaa` |
| Module 5 as a "research-only" module | Module 5 held back from implementation scope entirely, kept only as a documented research finding |

## Observed evidence / Inference / Speculation

Each merge attempt's verdict traces directly to a Phase 1C R² or redundancy number (Observed evidence). The "net result" table is this document's own Interpretation of what those verdicts imply for `IMPLEMENTATION_ROADMAP.md`'s scope — a design recommendation, not a new empirical claim.

## Future work

Revisit Module 5's status once its own reliability is tested (flagged repeatedly since Phase 1C) — if it turns out to be reliable despite being unexplained by everything else, that would itself be a notable finding (a construct that's real and stable but not predictable from anything else measured) worth a status upgrade.
