# Architecture

See `reports/REPOSITORY_RECONNAISSANCE.md` §7 for the full architecture graph. Summary below, oriented around consumers and adapters rather than reconnaissance narrative.

## Source systems (authoritative, unmodified by this package)

| System | Path | Version | Owner directory |
|---|---|---|---|
| MLB pitcher eWAR (champion) | `~/pitcher_ewar/data/pitcher_ewar.parquet` | `pitcher-ewar-1.1.0` | `~/pitcher_ewar/` |
| MiLB pitcher eWAR | `~/milb_pitcher_ewar/data/{aaa,aa,higha,lowa}_pitcher_ewar.parquet` | `milb-pitcher-ewar-1.0.0` (park-restated subset at `1.1.0`, see `~/milb_park_rebuild/`) | `~/milb_pitcher_ewar/` |
| MiLB park factors v2 | `~/milb_park_rebuild/data/milb_park_factors_v2.parquet` | `milb-park-factors-2.0.0` | `~/milb_park_rebuild/` |
| Player identity | `~/career_outcome_plus/data/eephus_identity.parquet` | unversioned (current-state) | `~/career_outcome_plus/` |
| MiLB rate-skill translation | `~/career_outcome_plus/data/{latent_rate_talent,milb_xwar_projection}.parquet` | `reach-2.0.0` (per `milb/handoff/00_baseline_manifest.json`) | `~/career_outcome_plus/milb/` |
| MLB environment physics (reference only) | `~/environment_engine/data/park_air_factors.parquet` | live per `RESULTS.md` | `~/environment_engine/` |

## Adapters (new, in this package)

Each adapter in `adapters/` is a small, standalone read-only script:

- Takes its source path from an environment variable or CLI flag with a documented default (never a hardcoded absolute path containing a username).
- Loads the authoritative parquet/json as-is.
- Validates required columns/types against the matching file in `contracts/`.
- Writes: (a) the real export to a private output path (not committed), and (b) nothing else — schema publication and fixtures are handled separately, not by the adapter re-deriving them each run.
- Never recomputes a value; if a field required by the contract is absent upstream, the adapter must omit it and note the gap, not synthesize it.

Planned adapters (built in Phases 3-6): `export_contact_translation.py`, `export_pitcher_ewar_mlb.py`, `export_pitcher_ewar_milb.py`, `export_park_context.py`, `export_identity.py`.

## Contracts

One JSON Schema (or equivalent) per exported artifact in `contracts/`, named to match its manifest entry. Contracts are the enforcement mechanism for "no drift from the authoritative source" — `tests/test_park_context_compatibility.py` (Phase 5) is the concrete example: it loads both the authoritative `milb_park_factors_v2.parquet` and this package's exported copy and asserts they match for the same `model_version`.

## Consumers (downstream of this package)

The only intended consumer of this package is the future external MiLB pitch-quality research effort. This package has no consumers inside Eephus itself — it is additive and read-only with respect to every existing system. No existing Eephus pipeline, website route, or refresh job reads anything under `milb_pitch_quality_handoff/`.

## Explicitly out of scope / not touched

- `env_foundation_integration/modules/m06_stadium_translation.py` and `m09c_lower_milb_translation.py` — frozen, pending a separate rebuild charter (`NEXT_MILB_TRANSLATION_REBUILD_CHARTER.md`). Referenced in documentation only.
- `swing_plus` — unrelated hitter model with its own in-progress uncommitted work; not read for authoritative data, not modified.
- Any website/publication route in `eephus.io` outside `milb_pitch_quality_handoff/`.
