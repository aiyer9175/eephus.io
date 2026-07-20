# Module Interaction

Phase 5. Which modules feed others, and by what kind of effect — grounded in the actual incremental-R² and correlation numbers from Phase 1C, not assumed from the module list alone.

## Direct vs. mediated effects

The charter's illustrative contrast — "Physical Stuff → Miss Ability → Pitcher Value" (mediated) vs. "Physical Stuff → Pitcher Value" (direct) — maps onto real measured quantities here:

| Path | Type | Evidence |
|---|---|---|
| Module 1 (Stuff) → Module 3 (Miss) | **Direct + mediated**, both real | Stuff alone: cumulative R²=0.066 into whiff rate. Adding Module 2 (Arsenal) on top: +0.071 (largest single increment). Both contribute independently — neither fully mediates the other. |
| Module 2 (Arsenal) → Module 3 (Miss) | **Direct**, largest single contributor | 0.071 incremental R², larger than Stuff's full 0.066. |
| Module 1 (Stuff, specifically Movement) → Module 4 (Ground-Ball) | **Direct, dominant** | 0.103 of the module's total 0.134 R² comes from Movement alone — the strongest single relationship found anywhere in Phase 1C. |
| Module 1+3 (Stuff, Whiff) → Module 5 (Damage Suppression) | **Weak/near-absent** | Total R²=0.019-0.037 across all tested predictors — evidence *against* a meaningful mediated or direct path, not evidence it exists. |
| Module 3 (Miss, tracked) → Module 6 (Result Rate, outcome-only) | **No path — disjoint populations** | Different venues by construction; not comparable, not mediating. |

## Shared inputs (not the same as redundancy)

Modules 1, 3, and 4 all consume tracked-pitch volume from the same underlying pitch-level dataset — a shared *input*, not shared *information*. `FEATURE_REDUNDANCY_REPORT.md` (Phase 1C) already distinguished this: correlated-but-distinct (velocity/movement/spin, r=0.27-0.33) is not the same as redundant (avg. launch speed/hard-hit rate, r=0.72). Sharing raw pitch-level input data across modules is expected and fine; the one place two modules threatened to duplicate the *same derived signal* (avg. launch speed and hard-hit rate) was resolved by merging them into a single Module 5, not by building two modules from one input.

## Circular dependencies

**None found, by design.** The module list is a DAG (Modules 1-2 → Module 3-5; Module 6 is a disjoint sibling, not downstream of 1-5). No module's output is used, directly or transitively, as an input to a module upstream of it. This was verified by construction (the incremental-information chains in Phase 1C were built physical-features-first, outcome-features-last, and no chain ever fed an outcome metric back into a physical one).

## Duplicated information

The one confirmed case (Module 5's internal merge) was resolved within `MODULE_SPECIFICATIONS.md`. Outside this research's own modules, `MODULE_SPECIFICATIONS.md` already flags the more consequential duplication risk: **Module 1 (Physical Stuff) substantially overlaps with the already-live `stuff_plus_aaa`** — both are physics-only, AAA-scoped (for `stuff_plus_aaa`; this research's Module 1 also covers tracked Low-A), per-pitch models. This is the central question `BENCHMARK_INTEGRATION.md` and `CONSUMER_AUDIT.md` exist to resolve — flagged here as an interaction risk, not resolved here.

## Unnecessary coupling

None identified. Each module's dependency is either (a) the tracking-status gate (a precondition, not coupling to another module's output) or (b) a confirmed, evidence-backed incremental-information relationship (Modules 1-2 → 3-4). No module depends on another module's output merely for convenience or shared code — every dependency in `MODULE_SPECIFICATIONS.md` traces to a specific number.

## Observed evidence / Inference / Speculation

The direct/mediated classifications above are Inference drawn directly from Phase 1C's R² numbers (Observed evidence). The "no circular dependencies" and "no unnecessary coupling" findings are verification claims about this architecture's own design, not empirical findings about the world — stated plainly as such.

## Future work

If Module 2's family-restricted reliability is confirmed (flagged repeatedly since Phase 1B), re-run this interaction analysis with per-family-restricted versions of Modules 1 and 3 to check whether the direct/mediated split holds within each pitch family, not just pooled across them.
