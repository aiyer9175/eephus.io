# 11 — Predictive Isolation Audit

## Placement
The module lives at `~/advancement_pace/` — a standalone descriptive namespace, not
under `career_outcome_plus/`, `swing_plus/`, or any predictive package. It imports
nothing from predictive packages (AST-enforced, see below).

## Sweep performed (2026-07-17)
`advancement_pace`, `advancement_pace_plus`, `advancement_percentile` grepped across
every production tree (`career_outcome_plus`, `swing_plus`, `projection_engine`,
`eowar`, `ewar*`, `playing_time_model`, `identity_plus`, `variance_plus`,
`environment_engine`, `batter_ecosystem`, `pd_integration_audit`) and the
`infra_hardening/manifests/*.yaml` feature registries: **zero hits outside this module.**

## Standing enforcement — `tests/test_isolation.py` (runs in every build, fail-closed)
1. token sweep over all production trees (py/yaml/yml/json);
2. token sweep over feature-registry manifests;
3. AST import guard: no module file may import from
   `career_outcome_plus | swing_plus | projection_engine | eowar | ewar* | playing_time_model`;
4. artifact rows must carry `stat_type="descriptive"` and `model_eligible=False`;
5. no ambiguous column names (`velocity`, `development_score`, `future_value`,
   `readiness`, `opportunity`, `p_reach`, `xwar`, `xfv`, `efv`, `ewar`, `eowar`);
6. provenance manifest must enumerate the forbidden consumers.

`build_all.py` exits 2 if any test fails — nothing publishes.

## Naming collision audit
The PD-integration work uses **development velocity (timing)** as a *predictive* lever.
This statistic deliberately shares no name, field, or artifact with it
(`development_velocity` is on the forbidden-names list), and measures a different
object: the realized historical path, not a forward-looking rate estimate.

## Permitted consumers (stamped in provenance)
descriptive publication layer · internal QC reports · future player-card UI ·
data exports explicitly labeled descriptive. Everything else is forbidden by contract.
