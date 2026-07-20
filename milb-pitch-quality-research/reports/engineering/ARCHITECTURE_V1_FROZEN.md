# Architecture v1.0 — Frozen

Freezes the architecture produced by `reports/architecture/` (the Architecture & Integration Charter). This document is the reference point every later engineering deliverable in `reports/engineering/` traces back to — per this charter's Governing Philosophy, engineering does not redesign architecture.

## What is frozen

- **Six modules**, as specified in `reports/architecture/MODULE_SPECIFICATIONS.md`: Physical Stuff, Arsenal Construction, Miss-Inducing Ability, Ground-Ball Tendency, Damage Suppression (research-only), Outcome-Only Result Rate.
- **Tracking-status gate**, venue-level not level-level, per `reports/architecture/TRACKING_BRANCH_ARCHITECTURE.md`.
- **Tiered-champion framing**: `stuff_plus_aaa`/`stuff_plus_external` as the pitch-quality/arsenal-layer champion; private `pitcher_ewar` stack as the full-pitcher-value champion, per `reports/architecture/BENCHMARK_INTEGRATION.md`.
- **No universal composite score** — rejected in `reports/phase1c/ARCHITECTURE_COMPARISON.md` and reaffirmed in `reports/architecture/ARCHITECTURE_SIMPLIFICATION.md`.
- **Production classification** of every construct, per `reports/architecture/PRODUCTION_CLASSIFICATION.md`.
- **Reuse of existing `prospect-tracker` infrastructure** (refresh cadence via `run_monthly.py`, publication via the existing `rsync`/manifest mechanism, glossary/model-registry schemas) rather than parallel systems, per `reports/architecture/REFRESH_ARCHITECTURE.md` and `PUBLICATION_ARCHITECTURE.md`.

## What is explicitly not frozen (deferred to this charter's own phases)

- The exact relationship between the proposed Physical Stuff module and the live `stuff_plus_aaa` — the architecture charter identified this as the largest open question but did not resolve it (`reports/architecture/BENCHMARK_INTEGRATION.md`'s own "Future work" section). Resolved in `STUFF_PLUS_RECONCILIATION.md`, this charter.
- Concrete module interfaces, data contracts, and refresh execution order — architecture specified *what* modules should exist and *why*; this charter specifies *how* they're built.

## Exception conditions (per this charter's Governing Philosophy)

Architecture changes during engineering are permitted only for:
1. **Reproducibility failure** — a number this engineering pass cannot reproduce from the cited artifact.
2. **Benchmark contradiction** — new evidence (e.g., from reading `stuff_plus_aaa`'s actual eval artifacts) that contradicts an architecture-phase claim.
3. **Interface contradiction** — a module specification that turns out to be internally inconsistent once an interface is actually drafted.
4. **Consumer contradiction** — a claimed consumer (`reports/architecture/CONSUMER_AUDIT.md`) that turns out not to exist or not to be wireable as described.
5. **Scientific error** — a Phase 1A-1C finding that turns out to have been miscomputed.

## Exceptions found and documented during this charter

One exception was triggered and is logged here per the "document every exception" instruction:

- **Interface-contradiction-adjacent finding, not a full exception**: `reports/architecture/MODULE_SPECIFICATIONS.md`'s Module 1 spec listed inputs as "`startSpeed`, `pfxX`/`pfxZ`, `spinRate`" without noting that `extension` and release position (`x0`/`y0`/`z0`) were also captured in the underlying dataset but never reliability-tested (Phase 1B). This is a **precision gap, not a contradiction** — the architecture's conclusions (0.91-0.99 reliability) remain correct for the fields they actually cover; `MODULE_INTERFACES.md` now states this precisely per-field rather than per-module. No architecture-level number changes as a result. Logged, not treated as grounds to reopen Phase 1B.

No other exceptions were found. Architecture v1.0, as summarized above, stands as the baseline for every deliverable that follows.

## Observed evidence / Inference / Speculation

This document is entirely Observed evidence — a direct summary of already-produced, already-committed architecture documents, with one logged precision gap. No new claims are introduced.

## Future work

None — this document's only job is to establish the baseline; substantive future work is tracked per-module in the deliverables that follow.
