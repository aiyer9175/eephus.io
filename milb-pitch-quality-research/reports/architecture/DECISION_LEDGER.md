# Decision Ledger — Architecture & Integration Charter

Required Final Deliverable, scoped to this charter specifically — distinct from the package-root `milb-pitch-quality-research/DECISION_LEDGER.md` (Phase 1A-1C decisions), to avoid the naming collision the charter's required-deliverables list would otherwise create.

1. **Tiered-champion framing adopted, per explicit user decision.** The original Phase I charter named "pitcher eWAR, Contact+, SEM-derived components" as the production champion, but a three-agent ecosystem survey found none of those are live on the actual website — `stuff_plus_aaa`/`stuff_plus_external` are. Rather than silently substituting one for the other, the user was asked directly; the answer (tiered champions — `stuff_plus_aaa` for the pitch-quality/arsenal layer, `pitcher_ewar` for full pitcher value) governs every downstream document in this charter.

2. **`stuff_plus_aaa`'s real evaluation artifacts were read directly** (`prospect-tracker/data/stuff_plus_aaa_eval.json`, `stuff_plus_aaa.json`) — they exist in this repository and are git-tracked, unlike the private `pitcher_ewar` stack. Reading them is using existing evidence, not repeating Phase 1A-1C's research, consistent with the charter's "unless a reproducibility issue is discovered" carve-out (no reproducibility issue was found; this was new-to-this-charter benchmark evidence that simply hadn't been looked at yet).

3. **`reports/architecture/` subdirectory, not flat files at the package root.** The charter's own required-deliverables list includes `DECISION_LEDGER.md` and `KNOWN_GAPS.md` — names already used at the package root for Phase 1A-1C decisions. A subdirectory avoids overwriting or ambiguously extending those, matching the precedent set by `reports/phase1b/` and `reports/phase1c/`.

4. **`IMPLEMENTATION_ROADMAP.md` does not include actual implementation work.** The charter states "No production implementation should begin until this architectural blueprint is complete" — this charter's job is the blueprint itself; Implementation Phases A-D are specified (purpose, dependencies, benchmarks, validation, deliverables, exit criteria) but not executed. Executing them is future work, explicitly out of this charter's scope.

5. **Module 1 (Physical Stuff) is not recommended as a guaranteed standalone production surface.** Given its substantial conceptual overlap with the already-live `stuff_plus_aaa`, this charter recommends resolving that overlap empirically (Implementation Phase A) before committing to a standalone surface — a direct application of Governing Philosophy #3 (no parallel systems) and the Consumer Audit's duplication-risk finding.

6. **Module 5 (Damage Suppression) is held back from the implementation roadmap entirely**, not merely marked "research-only" as in Phase 1C. Phase 1C's own finding (1.9-3.7% R² explained by everything else measured) combined with this charter's Consumer Audit (no consumer, no plausible one identified) justified a stricter disposition here than the research phase alone required.

7. **This document does not attempt to resolve the `pitcher_ewar` private-data-access blocker.** It remains exactly where Phase 1A left it (`milb-pitch-quality-research/DECISION_LEDGER.md` #1) — restating it here would imply architecture work could close a data-access gap, which it cannot.
