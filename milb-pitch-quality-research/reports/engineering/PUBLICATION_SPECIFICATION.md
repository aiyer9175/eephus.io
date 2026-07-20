# Publication Specification

Phase 6. Per-output publication spec, extending `reports/architecture/PUBLICATION_ARCHITECTURE.md` with the concrete fields this charter's engineering standards require.

| Field | Module 1 | Module 3a (tracked whiff) | Module 3b/6 (outcome-only) | Module 2, 4 | Module 5 |
|---|---|---|---|---|---|
| **Destination** | `data/physical_stuff.json` | `data/miss_ability_tracked.json` | `data/miss_ability_outcome_only.json` | internal only, no destination | none |
| **Consumer** | PROSPX pitcher cards (interim, non-`stuff_plus_aaa` path) | PROSPX pitcher cards | PROSPX pitcher cards, untracked-venue pitchers | Modules 3/4 internally | none |
| **Refresh schedule** | Daily | Daily | Daily | Daily (internal) | not scheduled |
| **Version** | `physical-stuff-1.0.0` | `miss-ability-tracked-1.0.0` | `miss-ability-outcome-1.0.0` | unversioned (internal) | n/a |
| **Uncertainty** | `velocity_reliability`, `movement_reliability`, `spin_reliability` fields | `whiff_reliability` (by level) | `whiff_reliability` + mandatory `evidence_strength: "limited"` | none published | n/a |
| **Confidence** | per-field, only where tested (`MODULE_INTERFACES.md`) | per-level | per-level, always qualified | n/a | n/a |
| **Methodology** | `model_registry.json` entry, `verdict: "provisional"` | same pattern | same pattern, methodology text must explicitly state the R²=0.016 finding | none — not published | none |
| **Glossary entry** | required before publish | required before publish | required before publish, must define "limited evidence" plainly | not applicable | not applicable |
| **API exposure** | none (static JSON only, matching site convention) | none | none | none | none |
| **Player page** | Yes | Yes | Yes | No | No |
| **Leaderboard** | Not yet — no MiLB pitch-quality leaderboard exists (`WEBSITE_INFORMATION_ARCHITECTURE.md` gap) | Same | Same | No | No |
| **Research page** | No — no research-page route exists on the live site at all (`CURRENT_ECOSYSTEM_MAP.md`) | No | No | No — stays in this repo's own `reports/` | No — stays in this repo's own `reports/` |
| **Internal only** | No | No | No | **Yes** | **Yes** |

## What this table enforces

Every published field (Modules 1, 3a, 3b/6) has a non-empty entry in every row above — nothing ships without a destination, a named consumer, a refresh schedule, a version, an uncertainty field, a methodology entry, and a glossary entry. This is the direct operationalization of the Global Eephus Engineering Rule's checklist ("real downstream consumer... integrated... validated... versioned... refresh behavior defined... uncertainty preserved... regression tests exist... documentation matches implementation") applied per-field, not just asserted at the module level.

Modules 2, 4, and 5 have no player-page/leaderboard/research-page destination by design (`CONSUMER_WIRING_PLAN.md`) — their row is "internal only: Yes" across the board, not a gap to fill later without evidence, but a deliberate publication-scope decision matching their current evidentiary status.

## Observed evidence / Inference / Speculation

This is a specification document — Inference and design choice throughout, built on the evidentiary distinctions already established (Observed) in `MODULE_INTERFACES.md` and `PRODUCTION_CLASSIFICATION.md`. No new empirical claims are introduced.

## Future work

If Modules 2 or 4 clear their reliability gaps (`IMPLEMENTATION_SEQUENCE.md`), this table gains new rows — designed to extend without restructuring, per the same "additive, not breaking" discipline as `DATA_CONTRACTS.md`.
