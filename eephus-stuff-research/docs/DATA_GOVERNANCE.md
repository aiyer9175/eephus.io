# Data Governance

## Production boundary

The following are **production** and are **read-only** to everything in
`eephus-stuff-research/`, without exception, unless a future program records
an explicit authorized-promotion decision in `registry/decisions/`:

- `eephus.io`'s `main` branch and anything merged into it
- `defense-plus/`, `swing-plus/`, `milb-decision-plus/`, `playing-time-model/`,
  `xRV models/`, `advancement_pace/`, `milb-projections/`, `prospect-tracker/`
- `xwoba_model.pkl`, `NCAA 26 Averages S+.csv` at the `eephus.io` repo root

No script in this repository writes to any path outside
`eephus-stuff-research/`. `config/research.yaml`'s `production_boundary.
frozen_paths` lists these paths machine-readably; provenance/manifest tooling
should refuse to write to a path matching that list (see
`src/eephus_research/provenance/`).

## Dataset registry

Every research dataset — raw, external, or derived — gets an entry in
`registry/datasets/` with a unique ID (`DS-001`, `DS-002`, ...) recording:
logical name, source, acquisition method, acquisition timestamp, raw parent
(if derived), transformations applied, grain, seasons covered, row count,
column count, unique-key definition, duplicate count, missingness summary,
checksum, schema version, and any known licensing/publication restriction.
Derived datasets list their parent dataset IDs — provenance must chain back
to an acquisition event, not dead-end at an unexplained file.

`src/eephus_research/provenance/manifest.py` generates the manifest entries
this requires automatically from a dataframe + a producer identifier; it
does not replace the registry entry, which also needs the human-authored
fields (source, licensing, acquisition method).

## Schema contracts

Every consequential tabular artifact gets an explicit schema in `schemas/`
(JSON Schema), specifying per column: name, dtype, nullable status, unit,
valid range where known, semantic meaning, and key status.
`src/eephus_research/validation/schema.py` validates a dataframe against one
of these and **fails loudly** — it does not silently coerce a structurally
incompatible column. It specifically guards against:

- integer/string ID mismatches
- season string/int mismatches (`"2026"` vs `2026`)
- renamed pitch classes between data-source versions
- duplicate keys where the schema declares a unique key
- timezone-naive vs timezone-aware datetime mixing
- missing identifier columns
- accidental numeric-to-string parsing failures (e.g. a velocity column that
  silently became `object` dtype because one row had `"—"`)

## Missing data governance (Part BP)

Never silently fill missing values merely to satisfy a downstream algorithm.
For each variable that matters, the schema or the mathematical contract
(`docs/MATHEMATICAL_GOVERNANCE.md`) must classify its missingness handling
as one of:

```
ERROR  DROP  IMPUTE  MISSING_CATEGORY  NOT_APPLICABLE
```

Record the count of affected rows before and after handling — a missingness
report that only states "handled" without a before/after count is
incomplete.

## Outlier governance (Part BQ)

Do not automatically winsorize or delete extreme observations. Distinguish,
explicitly, in whatever report touches the data:

- impossible values (e.g. a 250 mph fastball — a measurement/parsing error)
- measurement errors (plausible magnitude, implausible for this context)
- rare but valid pitches (a real 102 mph fastball from a real outlier
  pitcher)
- genuine distribution tails that should stay in the analysis

Any filtering rule applied gets written down with its row-count impact, in
the dataset's registry entry or the experiment's report — not applied
silently inside a notebook cell.

## Benchmark isolation (Part AI)

Before any benchmark metric (e.g. an external Stuff+ number, or Eephus's own
`xwoba_model.pkl` output) is used anywhere near model construction, classify
it as exactly one of:

```
TRAINING_TARGET  FEATURE  VALIDATION_ONLY  DESCRIPTIVE_COMPARATOR
PROHIBITED_FROM_MODEL
```

and record that classification in the relevant experiment's registry entry
(`registry/experiments/`). A benchmark being *available* is not license to
use it in feature engineering or model selection unless a preregistered
experiment explicitly says so. `milb-projections/BENCHMARK_REQUIREMENTS.md`
already defines the champion metrics for pitch-quality-adjacent work
specifically — a future Stuff Research Program should read it, not
re-derive an equivalent list from scratch.

## Large data handling (Part BI)

This machine had 37 GB free at time of writing (`docs/MACHINE_STATE.md`),
on a drive already 93% full. Do not blindly duplicate multi-gigabyte
datasets. Where possible: reference an immutable source location, generate
a checksum instead of a copy, build a small deterministic fixture for tests,
and document the external dependency rather than vendoring it. The ~1 GB
`milb-pitch-quality-research/data_cache/` sitting in this worktree
(documented in `REPOSITORY_INVENTORY.md`) is exactly this kind of thing to
be deliberate about, not casually duplicated into `data/raw/`.

## Data security (Part BH)

Search for secrets before committing anything. Do not print secrets into
reports. `config/paths.yaml` (real, machine-specific paths — potentially
pointing at licensed data or private export targets) is gitignored on
purpose; only `config/paths.example.yaml` is tracked.
