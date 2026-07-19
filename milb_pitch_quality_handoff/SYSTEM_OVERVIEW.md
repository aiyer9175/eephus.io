# System Overview

## Purpose

Eephus already has a mature MLB pitcher-evaluation stack (pitcher eWAR, `pitcher-ewar-1.1.0`) and a parallel-but-independent MiLB pitcher-evaluation stack (MiLB pitcher eWAR, `milb-pitcher-ewar-1.0.0`/`1.1.0`), both grounded in run-value decomposition rather than pitch-level "stuff" modeling. Neither stack models pitch-type/arsenal quality. A future research effort — outside this charter — will attempt to build a MiLB pitch-quality/arsenal proxy from noisy pitch-level outcomes. That effort needs two things Eephus already has and the builder does not:

1. **Context to interpret pitch outcomes correctly** — park factors, identity/level mapping, and existing pitcher-value benchmarks, so raw pitch results aren't naively equated with pitch quality (see `PITCH_QUALITY_RESEARCH_CONTRACT.md`).
2. **Something to benchmark against** — the existing champion pitcher-eWAR stacks, so any future model's incremental value can be measured honestly (see `BENCHMARK_REQUIREMENTS.md`).

This package is the boundary between "what Eephus already knows and owns" and "what the external builder must independently discover." Everything on the Eephus side of that boundary that cannot be reconstructed from public data is inventoried, classified, and exported here.

## End-to-end flow

1. **Authoritative Eephus systems** (pitcher eWAR ×2, MiLB park factors v2, player identity, MiLB rate-skill translation) run in their own directories, on their own refresh cadences, completely unaffected by this package. See `ARCHITECTURE.md` for exact paths.
2. **Export adapters** (`adapters/`) are new, additive, read-only code. Each adapter reads one authoritative output from a configurable path (never a hardcoded absolute path), validates it against its contract, and writes a handoff-shaped export (real values to a private location; schema/fixture to this repo).
3. **Contracts** (`contracts/`) define the exact schema each export must satisfy — types, units, nullability, keys. Tests in `tests/` enforce these contracts and, for park factors specifically, enforce that the export matches the authoritative source (no drift, no recomputation).
4. **The benchmark manifest** (`manifests/BENCHMARK_MANIFEST.yaml`) is the single machine-readable index of every benchmark asset: its role (champion / component / research benchmark / historical snapshot), its authoritative source, its allowed and prohibited uses.
5. **Documentation** (`definitions/`, `PITCH_QUALITY_RESEARCH_CONTRACT.md`, `TEMPORAL_INTEGRITY.md`) gives the external builder the interpretive rules needed to not misuse any of the above — most importantly, to not equate raw pitch-type outcomes with intrinsic pitch quality, and to not leak future information into historical rows given that none of Eephus's identity or benchmark systems currently support true point-in-time joins (a documented gap, not a hidden one).

## What the builder brings themselves

Per the charter's own scoping: raw pitch-by-pitch Statcast/TrackMan-equivalent data, boxscores, schedules, rosters, and team/affiliate/league/venue reference data are all directly available from the public MLB Stats API and are **not** included here (see `config/artifact_inventory.yaml`, artifact `milb_team_affiliate_park_mapping`, classified `NOT_NEEDED`/reconstructable).

## What genuinely does not exist yet (and is not fabricated here)

- A dedicated MiLB↔MLB Statcast-grade contact-quality portability model.
- Any pitch-type/arsenal-level output in either pitcher-eWAR stack.
- A champion-freeze/archive directory for MiLB pitcher eWAR (exists for MLB, not MiLB).
- Effective-dated ("as of") identity joins — both identity systems are current-state or season-grain only.

These are documented in `reports/ARTIFACT_INVENTORY.md` and `KNOWN_GAPS.md` rather than invented to complete a checklist.
