# Consumer Validation

Phase 9. For every downstream consumer named in `CONSUMER_WIRING_PLAN.md`, verify input/output/behavior/failure/monitoring/compatibility — none of this has been built yet, so this document specifies the validation checklist each future consumer must pass, not a report of passing checks.

## PROSPX pitcher-card consumer (Modules 1, 3a, 3b/6)

| Check | Requirement |
|---|---|
| Input | The card template must handle `null` gracefully for every field `MODULE_INTERFACES.md` allows to be `null` (below-threshold pitchers) — display "insufficient sample," not a blank or a zero. |
| Output | Displayed value must match the published JSON exactly — no silent unit conversion or rounding beyond what the contract specifies. |
| Expected behavior | A pitcher who newly crosses a stabilization threshold should see their card populate on the next refresh, not require a manual intervention. |
| Failure behavior | If a module's JSON is missing/malformed for a pitcher, the card must omit that field's display, not crash or show stale data silently. |
| Monitoring | The card's data source freshness (`artifact_age_days`) should be checkable the same way `stuff_plus_aaa`'s is, per `model_registry.json`'s existing convention. |
| Version compatibility | The card template must not break on a MINOR version bump (new optional field) — must be built to ignore unknown fields, per `DATA_CONTRACTS.md`'s compatibility guarantee. |
| Regression coverage | A test rendering the card against both the fixture and a "missing field" edge case, mirroring `milb-projections/tests/test_fixtures_match_contracts.py`'s approach. |

## `stuff_plus_aaa` feature-pipeline consumer (Module 1, augmentation path — blocked)

| Check | Requirement |
|---|---|
| Input | `stuff_plus_aaa.py`'s training pipeline must be able to accept Module 1's fields in place of (or alongside) its current Savant-sourced ones — **cannot be validated until the data-source reconciliation (`STUFF_PLUS_RECONCILIATION.md`) happens.** |
| Output | The retrained model's `stuff_plus_aaa_eval.json`-style output must be compared against the current baseline (season-out pitcher-level r=0.28) to determine if the augmentation actually helped — an empirical test, not assumed. |
| Status | **Not validatable today.** This entire consumer path is blocked, consistent with `STUFF_PLUS_RECONCILIATION.md`'s explicit flag. |

## Internal consumers (Module 2 → Module 3, Module 1 → Module 4)

| Check | Requirement |
|---|---|
| Input | Module 3's pipeline must handle Module 2's `null` outputs (pitchers below the family-analysis threshold) without erroring — same "fail gracefully on missing covariate" standard as the card consumer. |
| Output | Not published externally — validation here means "does Module 3's decomposition still make sense when Module 2 is null for a given pitcher" (it should — Module 3's own whiff-rate estimate doesn't require the decomposition to exist). |
| Regression coverage | A test confirming Module 3 still produces a valid (if less-decomposed) output when Module 2's covariate is missing. |

## What "no module ships without consumer validation" means concretely here

Per the charter's own instruction, **no module in this research is ready to ship today** — every consumer above is either unbuilt (PROSPX card integration) or blocked (the `stuff_plus_aaa` path). This is not a failure of this charter; it's the honest output of following "no implementation should begin until [Stuff+ reconciliation] is resolved" and "no module should ship without consumer validation" simultaneously — both instructions point to the same conclusion, examined directly in `MODULE1_READINESS.md`.

## Observed evidence / Inference / Speculation

The checklist items are Inference — validation requirements this document specifies for consumers that don't exist yet, not empirical findings. The "not validatable today" / "blocked" statuses are direct, honest restatements of `STUFF_PLUS_RECONCILIATION.md`'s and `CONSUMER_WIRING_PLAN.md`'s already-Observed findings.

## Future work

Building the PROSPX pitcher-card integration for Module 1/3a/3b is the one consumer-validation path that doesn't require the `stuff_plus_aaa` blocker to resolve first — the concrete, unblocked next implementation step, named again in `IMPLEMENTATION_SEQUENCE.md`.
