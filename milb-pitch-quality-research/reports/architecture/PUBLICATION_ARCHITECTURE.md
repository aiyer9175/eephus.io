# Publication Architecture

Phase 8. What becomes public, what stays internal, and what publication safeguards each requires — modeled directly on `prospect-tracker`'s existing, working conventions (`model_registry.json`'s verdict system, `glossary.json`'s structured entries) rather than inventing a parallel system.

## Public vs. internal, by module

| Module | Public? | Required safeguards before publishing |
|---|---|---|
| Module 1 (Physical Stuff) | **Public** (Player Page Metric, per `PRODUCTION_CLASSIFICATION.md`) | None beyond standard sample-size labeling — this is the most reliable construct in the whole research program. |
| Module 2 (Arsenal Construction) | **Internal for now** | Family-restricted reliability check (open since Phase 1B) before any public claim about per-family quality. |
| Module 3 (Miss-Inducing Ability, tracked) | **Public**, with an uncertainty band | Split-half r=0.33-0.51 — real but moderate; must not be presented as precise. |
| Module 3 variant (Module 6, outcome-only) | **Public, but explicitly labeled "limited signal"** | R²=0.016 supporting evidence — a stronger warning than a typical sample-size note; see `UNCERTAINTY_ARCHITECTURE.md`. |
| Module 4 (Ground-Ball Tendency) | **Internal for now** | Own-metric reliability untested — publish only after that gap closes. |
| Module 5 (Damage Suppression) | **Internal, research-only** | Nearly unexplained by anything else measured (1.9-3.7% R²); own reliability untested. Do not publish until both close. |
| Venue/park-effect finding | **Internal diagnostic**, could be a one-time public research note | Not a live metric; a null finding worth stating once, not a recurring published number. |

## What requires each safeguard

- **Uncertainty (all public modules)**: every published figure carries the reliability class it earned in Phase 1B — "high confidence" (r>0.9), "moderate confidence" (r 0.3-0.6), or, for anything weaker, it doesn't publish at all under this architecture (`Unsupported`/`Internal Diagnostic` per `PRODUCTION_CLASSIFICATION.md`).
- **Stabilization indicators**: Modules 1/3's stabilization curves (Phase 1B) directly inform a minimum-pitch-count gate before a pitcher's score displays at all — mirroring `swing-plus`'s existing pattern (`k=360 swings` reliability-weighting) and `sem_plus`/`rem_plus`'s empirical-Bayes shrinkage, both already-shipped precedents in this codebase.
- **Confidence intervals**: this research has not computed formal CIs (Phase 1B/1C used reliability coefficients and R², not bootstrap CIs) — a gap relative to `sem_plus`/`rem_plus`'s bootstrap-CI convention, flagged in `KNOWN_GAPS.md`, not silently matched.
- **Sample-size warnings**: required on every tracked-venue module given the small AAA/Low-A-FSL pitcher-level cohort sizes this research validated against (577-600 pitchers) — smaller than `stuff_plus_aaa`'s or `rem_plus`'s validation cohorts.
- **Glossary documentation**: every published module needs an entry in `prospect-tracker/data/glossary.json` following its existing schema (`id`, `term`, `category`, `module`, `aliases`, `priority`, `definition`, `methodology`) — not a new glossary system.
- **Methodology documentation**: every published module needs a model-registry-style entry (`prospect-tracker/data/model_registry.json`'s existing schema: `model_id`, `surface`, `predicts`, `champion`, `baseline`, `metric`, `verdict`, `eval_artifact`) — this research's own verdicts (per `PRODUCTION_CLASSIFICATION.md`) map directly onto that registry's `provisional`/`unvalidated`/`validated` vocabulary.

## What this means concretely for the registry

If any module from this research is implemented, it should ship with a `verdict: "provisional"` entry (matching `stuff_plus_aaa`'s own current verdict) at best — none of this research's modules have the forward-chained validation that earns `sem_plus`/`rem_plus`'s `validated` verdict. Overstating verdict would violate the registry's own evidentiary standard, which this research should meet, not undercut.

## Observed evidence / Inference / Speculation

The safeguard requirements are Inference drawn from Phase 1B/1C's specific reliability numbers, mapped onto `prospect-tracker`'s existing, already-observed publication conventions (glossary schema, model registry schema, `swing-plus`/`rem_plus`'s shrinkage precedents — all confirmed real in `CURRENT_ECOSYSTEM_MAP.md`). Nothing here is speculative about what the safeguards should look like; it is speculative only in the sense that no module has actually been published yet to test whether these safeguards work in practice.

## Future work

A formal CI/bootstrap layer, matching `sem_plus`/`rem_plus`'s convention, is the concrete gap between this research's current reliability-coefficient-based uncertainty language and what this codebase's existing validated models report. See `UNCERTAINTY_ARCHITECTURE.md`.
