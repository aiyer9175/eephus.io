# Consumer Audit

Phase 13, mandatory. The honest answer, checked against `CURRENT_ECOSYSTEM_MAP.md`'s findings rather than assumed: **no module in this research currently has a real, wired consumer anywhere in this codebase.** This is stated plainly, not softened, because `milb-decision-plus/` is direct, concrete proof that "fully built and well-validated" does not imply "gets consumed" in this codebase — it shipped a real Decision+ metric with a documented integration rule, and zero code anywhere reads its output.

## Per-module audit

| Module | Who consumes this today? | Why (if consumed)? | Can another module already provide this? | Duplication risk | Can it be simplified? |
|---|---|---|---|---|---|
| Module 1 (Stuff) | **No one.** | N/A | **Partially — `stuff_plus_aaa` already exists** and covers physics-only per-pitch quality at AAA, live, on PROSPX pitcher cards. | **Real, the highest of any module.** `BENCHMARK_INTEGRATION.md` found this is a complement (Module 1's raw-trait reliability of 0.91-0.99 vs. `stuff_plus_aaa`'s run-value-trained pitcher-level stability of 0.28), not a pure duplicate — but this must be demonstrated empirically before Module 1 ships, not assumed from this document alone. | Yes — if the endpoint reconciliation (`DEPENDENCY_GRAPH.md`) shows Module 1 adds nothing `stuff_plus_aaa` doesn't already capture once its features are examined directly, Module 1 should not become a separate production surface; it should become an input proposal to `stuff_plus_aaa`'s own model instead. |
| Module 2 (Arsenal) | No one. | N/A | No existing system decomposes MiLB pitch mix/diversity (`stuff_plus_aaa` explicitly has "no pitch-type identity"). | Low. | No — this is the clearest non-duplicative, no-existing-analog module in the set. |
| Module 3 (Miss, tracked) | No one. | N/A | No — no existing system reports MiLB whiff rate with a stuff/mix/location decomposition. | Low, though `stuff_plus_aaa`'s `delta_run_exp` label is *correlated* with whiff outcomes (not the same measurement). | No. |
| Module 3 variant (Module 6, outcome-only) | No one. | N/A | No existing system covers AA/High-A/untracked-Low-A pitch quality at all. | None — the one module with a genuine, currently-unfilled gap to fill. | No. |
| Module 4 (Ground-Ball) | No one. | N/A | No existing system reports MiLB ground-ball tendency. | Low. | No. |
| Module 5 (Damage Suppression) | No one. | N/A | No existing system reports MiLB contact quality allowed. | Low, but the module's own weak internal evidence (`PRODUCTION_CLASSIFICATION.md`: Internal Diagnostic) is a stronger reason to hold it back than duplication risk is. | Possibly — given how weak its connection to everything else is (`BENCHMARK_INTEGRATION.md`), it may simplify to "not built at all" rather than "built as a module," pending its own reliability test. |

## The `milb-decision-plus` lesson, applied directly

`milb-decision-plus/REPORT.md` states its own integration rule ("the main projection model should consume `proj_k_pct`/`proj_bb_pct`") but `CURRENT_ECOSYSTEM_MAP.md` confirms zero code anywhere reads it. The lesson for this architecture: **a documented integration rule is not a consumer.** `IMPLEMENTATION_ROADMAP.md` must treat "write the consuming code, not just document the intent" as part of the deliverable for any module that proceeds — not a follow-up task that can slip.

## Removal/redesign per the charter's own rule

Per "if a module has no clearly defined downstream consumer, remove or redesign it": **strictly applied, every module in this research currently fails this test.** This document does not recommend removing all six modules — that would ignore the distinction between modules with a plausible, evidence-backed *future* consumer (Modules 1, 3, 6 — real gaps or real complements to `stuff_plus_aaa`) and modules with no consumer even in principle (none of the six are in this category; all answer a real, currently-unaddressed baseball question, except Module 1 which has genuine duplication risk). The redesign this audit actually recommends: **no module proceeds to implementation without its consumer being built in the same implementation phase**, not designed and left to a documented-but-unwired intent, per the lesson above.

## Observed evidence / Inference / Speculation

"No one consumes any of these modules today" is Observed evidence (confirmed absence in the ecosystem survey). The duplication-risk assessment for Module 1 is Inference from `BENCHMARK_INTEGRATION.md`'s reliability comparison — real evidence, but not yet a controlled empirical test of whether Module 1 literally adds nothing `stuff_plus_aaa` doesn't have. The "can be simplified" judgments are this document's own Interpretation, clearly distinguished from the Observed absence-of-consumer findings above them.

## Future work

The Module 1 vs. `stuff_plus_aaa` duplication question is the single highest-priority open item this audit surfaces — it should be resolved (empirically, per `BENCHMARK_INTEGRATION.md`'s future-work recommendation) before Module 1 is scheduled for implementation, not after.
