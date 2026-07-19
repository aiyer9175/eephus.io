# Publication Policy

## Governing constraint

Eephus is a commercial platform (see project memory `feedback_commercial_data_licensing`). 127 source files across `career_outcome_plus`, `milb_pitcher_ewar`, `pitcher_ewar`, and `milb_park_rebuild` carry explicit `Copyright (C) 2026 Will Cahoon — All Rights Reserved / Proprietary and confidential` headers. This policy exists to make sure nothing proprietary is committed to a public/shared GitHub history, while still giving the external builder everything they legitimately need.

## The rule

**No original pipeline or model source file is ever copied into this package, in whole or in part.** Everything under `adapters/` is newly authored by this handoff effort, describes *how* to reach an output (a path, a shape, a validation rule), and contains no proprietary business logic (no feature engineering, no model coefficients, no scoring formulas). Documentation under `definitions/` describes *what* an output means and *why*, in original language, not by pasting docstrings or code comments from the source directories.

## Classification legend (used in `config/artifact_inventory.yaml` and `manifests/BENCHMARK_MANIFEST.yaml`)

| Classification | Meaning | Where it lives |
|---|---|---|
| `PUBLIC_GITHUB` | Safe to commit as-is: newly authored docs, schemas, tests, adapter code | This repo, tracked |
| `PUBLIC_SCHEMA_ONLY` | The shape/methodology is public; the underlying values or source code are not | `contracts/*.schema.json` + `definitions/*.md` in this repo; real data stays out |
| `PRIVATE_EXPORT_REQUIRED` | Real row-level values must reach the external builder, but not via public git history | Adapter writes to a configurable private path (env var `EEPHUS_HANDOFF_PRIVATE_OUT`, documented per-adapter); `fixtures/` carries a synthetic stand-in with identical schema |
| `PRIVATE_OPTIONAL` | Nice to have privately, not required for the build to proceed | Same mechanism as above, lower priority |
| `INTERNAL_ONLY` | Do not export in any form, public or private, without a separate explicit approval (e.g. Low-A pitcher eWAR, publication withheld per its own build ruling) | Referenced by name/classification only |
| `DEPRECATED` | Superseded; kept only as historical/incident context | Referenced in docs, never exported as current data |
| `NOT_NEEDED` | Reconstructable by the external builder from public sources, or genuinely doesn't exist | Not exported; documented as such so the builder doesn't waste time looking for it |

## Mechanics

- `.gitignore` in `eephus.io` globally excludes `*.csv`/`*.parquet`. `fixtures/` in this package therefore uses `.json`/`.jsonl` for synthetic sample data — no gitignore exception is needed or added.
- Real private exports never touch this git history. The default private output root is `~/eephus_handoff_private_exports/` (outside any git working tree), documented per-adapter in `PORTING_GUIDE.md`.
- Any file containing full birthdates (`dob` in `eephus_identity.parquet`) is truncated to birth-year (or dropped) before it leaves the private-export boundary — see `definitions/IDENTITY_SYSTEM.md`.
- Nothing in this package alters `eephus.io`'s existing `.gitignore`, CI, or publication routes.

## What is explicitly never committed, public or private

Raw Statcast/TrackMan pitch-level data, raw MLB Stats API pulls, and anything licensed from a third party under non-redistribution terms are never staged by this package — the external builder pulls those themselves per the charter's own scoping.
