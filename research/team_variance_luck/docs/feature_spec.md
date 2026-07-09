# Feature spec

## What this feature is

`team_variance_luck` is a lightweight, team-level interface for exporting and
loading luck, variance, roster-health, injury-context, and schedule-context
features for downstream ELO modeling. It is intentionally disconnected from
the website runtime and leaves the full model implementation for later work
under `team_variance_luck/core/`.

## Owner

Will Cahoon is the responsible developer and initial maintainer.

## Inputs

- A local CSV or Parquet table containing every field in the documented ELO
  schema.
- Optional internal, non-schema columns may be present, except for explicitly
  forbidden player-level and medical-detail columns.

## Outputs

- A validated Parquet feature table containing only the canonical ELO columns.
- An optional CSV copy of the same canonical table.

Generated exports belong in ignored local storage or external object storage;
they are not committed to GitHub. The tracked `artifacts/` directory contains
only `.gitkeep`.

## Data dependencies

There are no required external data dependencies for this interface package.
It does not directly query tables, APIs, endpoints, external datasets, or
services.

Current runtime dependencies:

- `pandas` for CSV loading, validation, and table handling.
- An optional pandas Parquet engine such as `pyarrow` for Parquet reads/writes.

Future full-model data sources and services must be documented before they are
introduced under `team_variance_luck/core/`.

## Definition of done

- The canonical schema and field semantics are documented.
- CSV and Parquet inputs can be loaded and validated.
- ELO exports contain only canonical columns.
- Forbidden player-level and medical-detail fields fail validation.
- Confidence and integer-like season values are validated.
- Unit tests pass, with Parquet tests skipped only when its optional engine is
  unavailable.
- No raw datasets, generated feature exports, large binaries, or website
  runtime changes are included.
