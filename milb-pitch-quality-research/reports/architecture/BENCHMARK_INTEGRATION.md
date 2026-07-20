# Benchmark Integration

Phase 6. The largest remaining scientific blocker, addressed as far as this environment allows. Unlike the private pitcher-eWAR stack, `stuff_plus_aaa`'s evaluation artifacts (`prospect-tracker/data/stuff_plus_aaa_eval.json`, `stuff_plus_aaa.json`) **are present in this repository and were read directly** — this is genuinely new benchmark evidence, not a repeat of Phase 1A-1C's own research, and is exactly what "no benchmark should be ignored" requires.

## Observed evidence: `stuff_plus_aaa`'s own validation numbers

From `prospect-tracker/data/stuff_plus_aaa_eval.json` (generated 2026-07-16):

| Metric | Value | Reading |
|---|---|---|
| Season-out pitch-level r | 0.0213 | Near-zero, as expected — a single pitch's `delta_run_exp` is dominated by noise. |
| **Season-out pitcher-level r** | **0.2797** (n=638 pitchers) | The stability of the *run-value-trained* score, pitcher-season to pitcher-season. |
| Forward gate vs. MLB ERA⁻¹ | r=0.047 (n=18) | Essentially no forward signal for run prevention — small sample, weak relationship. |
| Forward gate vs. MLB K% | r=0.505 (n=18) | Moderate forward signal specifically for strikeout rate. |

**Direct comparison to this research's own reliability findings (Phase 1B)**: this research's Module 1 (raw physical-trait averages: velocity, movement, spin) has split-half reliability of **0.91-0.99** — dramatically higher than `stuff_plus_aaa`'s pitcher-level stability of **0.28**. This is not a contradiction between the two research efforts; it's expected and mutually corroborating: `stuff_plus_aaa` predicts a *run-value outcome* (noisy) from physical inputs, while this research's Module 1 measures the *physical inputs themselves* (far less noisy). The gap between 0.99 and 0.28 is itself evidence for exactly the point Phase 1B's reliability program was built to make — outcome-derived scores are much less stable than the physical measurements underneath them.

`sem_plus`/`rem_plus` (`sem_plus_eval.json`, `rem_plus_eval.json`) are forward-chained-Spearman-validated, season-level run-prevention-skill metrics at the MLB level (n=878 forward pairs for REM+) — a different grain (season, not pitch) and different level (MLB, not MiLB) than anything in this research. They are not directly comparable benchmarks for this research's modules, but are relevant *consumers* to note for later value-integration (see `FUTURE_EXPANSION.md`).

## Incremental value / shared information / replacement value / research-only value / redundant information, per benchmark

| Benchmark | Shared information | Incremental value of this research's modules | Replacement value | Verdict |
|---|---|---|---|---|
| `stuff_plus_aaa` (Layer 1 champion) | Both use physics-only pitch features at AAA. Different endpoint (Savant minors search vs. MLB Stats API feed), different label (run value vs. raw physical averages / whiff rate / GB rate), different scope (AAA-only vs. AAA + tracked Low-A). | Real, plausible, **not yet measured** — this research's Modules 2 (arsenal), 4 (ground-ball), and the Branch A/B tracking-status architecture are capabilities `stuff_plus_aaa` doesn't have (it's explicitly "no pitch-type identity," single-output). Module 1 offers a much more reliable raw-physical-trait layer underneath `stuff_plus_aaa`'s noisier run-value output. | **None currently claimed** — `stuff_plus_aaa` is "provisional" but has real forward-validation evidence (K% forward gate); this research has no forward-validation of its own yet. A replacement claim would require this research's modules to be forward-tested the same way, which hasn't been done. | **Complement/extend, not replace** — pending the endpoint reconciliation flagged in `DEPENDENCY_GRAPH.md`. |
| `stuff_plus_external` (tjStuff+ port) | Same physics-only concept, MLB-scoped, external model, "unvalidated" (no local eval artifact at all). | This research has no MLB-level component, so no direct incremental claim. | None. | Out of scope for this research's modules (different level). |
| `sem_plus`/`rem_plus` | Season-level run-prevention skill, MLB-level, outcome-based (FIP-derived) — a different grain and level than any of this research's modules. | None directly — potential *future* value-integration point once this research's outputs could feed a MiLB-to-MLB translation, which doesn't exist (see `career_outcome_plus`, next row). | None. | Not a duplicate; a distinct, validated system this research doesn't touch. |
| Contact Portability (`career_outcome_plus`'s rate-skill translation) | Conceptually adjacent (cross-level persistence) but for **hitters**, not pitchers — `milb-projections/definitions/CONTACT_PORTABILITY.md` explicitly documents it's not a pitcher-contact-quality system. | None — wrong domain. | None. | Not applicable to this research; `milb-projections/KNOWN_GAPS.md`'s finding stands (no MiLB pitcher contact-portability model exists anywhere in Eephus). |
| `pitcher_ewar`/`milb_pitcher_ewar` (Layer 2 champion) | Full pitcher run-value-above-replacement, MLB + MiLB, level-local — a different question (total value) than anything this research's modules answer (physical/outcome pitch-quality components). | Potentially large, but **completely untestable in this environment** — private, absent (`DECISION_LEDGER.md` #1). | None claimed or claimable without real data access. | Blocked, unchanged from Phase 1A. |
| Park Factors (`milb_park_rebuild`, private) | This research's Module 4/5 findings already show **no detectable venue effect** on any outcome metric at any level (Phase 1B, ICC 0.01-0.3%) — a finding that doesn't need the private park-factor values to state, since it's about outcome variance, not park-factor values themselves. | Low — this research's own venue-ICC finding is already a (weak) form of park-context awareness. | None. | Schema-only, unchanged from Phase 1A; the "do we need it" question is partially pre-answered by the near-zero venue ICC already found. |

## Inference

The one genuinely new, actionable finding this phase produced is the reliability contrast between `stuff_plus_aaa` (0.28 pitcher-level stability) and this research's Module 1 (0.91-0.99). That gap is the strongest evidence yet for *why* a physical-trait-first architecture (this research's recommendation) could have real value even in a codebase that already ships a pitch-quality model — not because `stuff_plus_aaa` is wrong, but because it's solving a harder, noisier problem (predicting run value) than the more tractable one (measuring physical traits directly) this research's Module 1 addresses.

## Speculation

Whether this research's Modules would actually improve `stuff_plus_aaa`'s forward-prediction performance if combined (e.g., as additional LightGBM features) is untested — plausible given the reliability contrast, but a real empirical claim would require running that comparison, which is out of scope for an architecture charter that explicitly instructs against new modeling work.

## Future work

The single highest-value next research step this phase surfaces: reconcile the two data sources (MLB Stats API feed vs. Baseball Savant minors search) and test whether this research's Module 1 physical-trait scores, added as features to `stuff_plus_aaa`'s LightGBM model, improve its pitcher-level stability or forward-gate performance. This is a real, scoped, answerable question — and a much more concrete "Phase 2" than anything speculative.
