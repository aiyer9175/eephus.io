# Production Classification

Phase 7. Classification vocabulary per this charter: `Production Metric | Production Feature | Projection Feature | Pitcher eWAR Feature | Player Page Metric | Leaderboard Metric | Research Metric | Internal Diagnostic | Deprecated | Unsupported`. Builds on `reports/phase1c/PRODUCTION_COMPONENT_RECOMMENDATIONS.md`'s evidence but applies this charter's own categories, which are ecosystem-integration-oriented rather than purely evidentiary.

| Construct | Classification | Evidence | Why not a different classification |
|---|---|---|---|
| Velocity | **Player Page Metric** (within Module 1) | Split-half r=0.98-0.99 (Phase 1B) | Reliable and interpretable enough to show directly, not just use internally — but no confirmed leaderboard or eWAR wiring exists yet, so not those categories until `CONSUMER_AUDIT.md`'s gaps close. |
| Movement, Spin | **Player Page Metric** (within Module 1) | Split-half r=0.91-0.98 (Phase 1B) | Same reasoning as velocity. |
| Pitch mix/diversity | **Production Feature** | Largest incremental-R² contributor to whiff rate (Phase 1C) | Real, non-redundant information, but own reliability untested (Phase 1B/1C gap) — a feature for other modules, not yet a standalone displayed metric. |
| Whiff rate (tracked) | **Player Page Metric** | Split-half r=0.33-0.51 (Phase 1B); non-redundant (Phase 1C) | Moderate but real reliability, directly interpretable to a baseball audience. |
| Whiff rate (outcome-only, Module 6) | **Research Metric** | R²=0.016 from its only predictor (Phase 1C) | Too weak for a confident player-facing display; useful only as an internal descriptive research figure until/unless it improves. |
| Ground-ball tendency | **Research Metric** | Real relationship to Movement (R²=0.134) but own reliability untested | One step from Player Page Metric — needs the reliability check flagged in `MODULE_SPECIFICATIONS.md` first. |
| Damage suppression (merged) | **Internal Diagnostic** | Nearly unexplained by anything measured (1.9-3.7% R², Phase 1C); own reliability untested | Not ready for any public-facing classification — appropriate only as an internal signal for further investigation, per Phase 1C's "research-only" finding, tightened here given how weak the connecting evidence is. |
| Command / zone rate | **Unsupported** | Split-half r=0.07-0.19, still rising at largest tested threshold (Phase 1B) | Directly excluded per repeated evidence across two phases. |
| Called-strike rate | **Unsupported** | r=-0.10 to +0.06 everywhere, every sample size (Phase 1B) | The clearest negative finding in this entire research program. |
| Venue/park effects (this research's own finding) | **Internal Diagnostic** | ICC 0.01-0.3% at every level (Phase 1B) | A null-ish result worth keeping as an internal sanity check (e.g., re-verify if a future venue changes tracking status), not a public metric. |
| `stuff_plus_aaa` (existing system) | Already **Player Page Metric**, live | `provisional` verdict, model registry | Out of scope to reclassify — this charter evaluates against it, doesn't own it. |
| Real Eephus pitcher eWAR | Would be **Pitcher eWAR Feature** if accessible | N/A — blocked | Cannot be classified as anything beyond "blocked" while private-export access remains unresolved. |
| Any single composite pitch-quality score | **Unsupported** (as an architecture, not a per-construct classification) | Redundancy/variance-structure evidence, `ARCHITECTURE_COMPARISON.md` | Rejected architecturally; no construct should be built to feed one. |

## Observed evidence / Inference / Speculation

Every classification traces to a specific Phase 1B/1C number (Observed evidence). Column 4 ("why not a different classification") is Inference explaining the boundary between adjacent categories — most of it hinges on whether a *confirmed, wired* consumer exists (Player Page Metric / Leaderboard Metric) vs. whether the construct is merely evidence-supported but unwired (Production Feature / Research Metric). `CONSUMER_AUDIT.md` interrogates that distinction directly.

## Future work

Nothing here is classified as **Projection Feature** or **Leaderboard Metric** — no evidence from any phase supports either classification yet (no projection system for MiLB pitchers exists to feed, per `CURRENT_ECOSYSTEM_MAP.md`; no leaderboard currently displays anything this research produces). If a future phase builds the `stuff_plus_aaa` integration flagged in `BENCHMARK_INTEGRATION.md`, several rows here would likely be reclassified upward.
