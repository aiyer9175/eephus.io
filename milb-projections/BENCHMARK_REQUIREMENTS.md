# Benchmark Requirements

Status: scaffolded in Phase 2 with the current champions identified; the full comparison matrix, reliability program, and negative controls are specified in Phases 10-11 below.

## Existing champions (today, per `reports/REPOSITORY_RECONNAISSANCE.md` and `reports/ARTIFACT_INVENTORY.md`)

- **MLB pitcher eWAR** (`pitcher-ewar-1.1.0`, `~/pitcher_ewar/`) — the cross-stack champion. Run-value decomposition (FI runs, contact runs, HR opportunity/conversion, park neutralization, role, replacement) with no pitch-type/arsenal component.
- **MiLB pitcher eWAR** (`milb-pitcher-ewar-1.0.0`/`1.1.0`, `~/milb_pitcher_ewar/`) — level-local currency (AAA/AA/High-A public, Low-A internal), same run-decomposition family, park-restated as of the v2 park layer. Explicitly not comparable across levels or to MLB without going through the reach/translation layer in `career_outcome_plus`.
- **MiLB rate-skill translation** (`reach-2.0.0`, `career_outcome_plus/milb/`) — the closest existing descriptive-challenger for cross-level persistence, not a pitch-quality model.

## Future comparison design (required of the external builder)

The future MiLB pitch-quality challenger must be evaluated against, at minimum, the ladder specified in `PITCH_QUALITY_RESEARCH_CONTRACT.md` §Required Comparisons (A. velocity only → I. Eephus stack + raw new-model features). This document and the research contract are the same requirement stated from two angles — read both.

## Required comparison roles (see `manifests/BENCHMARK_MANIFEST.yaml` for the machine-readable form)

`velocity_only`, `raw_pitch_results`, `shrunken_pitch_results`, `context_adjusted_pitch_results`, `contact_portability` (documented gap — see `KNOWN_GAPS.md`), `existing_eephus_pitcher_stack`, `future_latent_pitch_quality`, `champion_plus_challenger`, `champion_plus_raw_challenger_features`.

Only the Eephus-specific benchmarks (existing pitcher stacks, park factors, identity) are exported by this package. The public-data baselines (velocity-only, raw pitch results, etc.) are entirely builder-generated from data they pull themselves — this package does not and should not try to build them.

## Interpretive comparisons required

- `shrunken_pitch_results` vs `raw_pitch_results` — value of shrinkage.
- `context_adjusted_pitch_results` vs `shrunken_pitch_results` — value of context adjustment.
- `future_latent_pitch_quality` vs `context_adjusted_pitch_results` — value of the latent architecture beyond adjusted results.
- `champion_plus_challenger` vs `existing_eephus_pitcher_stack` — incremental value to Eephus.
- `champion_plus_challenger` vs `champion_plus_raw_challenger_features` — whether the constructed metric adds value beyond the raw feature bundle.

Full reliability program and negative-control requirements: see `PITCH_QUALITY_RESEARCH_CONTRACT.md`.
