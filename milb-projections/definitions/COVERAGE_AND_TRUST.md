# Coverage and Trust

This is the Eephus-specific record of known data coverage and field trust — what Eephus's own production systems have already learned about their inputs' completeness and reliability. It is **not** the raw-public-data coverage audit the external builder will perform themselves against the MLB Stats API; that's their job, using data this package doesn't contain.

Trust statuses: `TRUSTED | USABLE_WITH_FILTER | PARTIAL | SYSTEMATICALLY_MISSING | KNOWN_DEFECT | NOT_VALIDATED | UNAVAILABLE`.

Machine-readable version: `context/coverage_matrix.json` (see below — placed under `context/` per the charter; this package uses `manifests/coverage_matrix.json` since no separate `context/` directory exists elsewhere in this package's structure — see `DECISION_LEDGER.md`).

## Batted-ball / contact coverage (measured directly, not inferred from non-null rate alone)

| Level | Seasons with contact coverage | Trust status | Evidence |
|---|---|---|---|
| MLB | 2021-2025 (bat-tracking era 2023H2+ for Damage Conversion+ specifically) | TRUSTED | `pitcher_ewar.parquet` carries `contact_runs_above_average` + `contact_runs_sd` for all seasons; `contact_missing` flag available for edge cases |
| AAA | 2023-2025 only (`coverage_level == "full"`: 3,726 of 6,167 rows). 2021-2022 rows are `coverage_level == "fi_only"` (2,441 rows) — contact explicitly listed in `missing_components`, never zero-imputed | PARTIAL (level-and-season-gated, not level-wide) | Directly measured from `aaa_pitcher_ewar.parquet`: 2021 fi_only=1177, 2022 fi_only=1257(+3 stragglers), 2023-2025 full except a handful of stragglers (3, 1, 3 rows) likely small-sample pitchers who didn't clear a contact-model threshold |
| AA | None — 100% `fi_only` across all seasons (4,985/4,985 rows) | SYSTEMATICALLY_MISSING | Directly measured; by design, not a defect — "approximating it is forbidden by charter" |
| High-A | None — 100% `fi_only` across all seasons (5,019/5,019 rows) | SYSTEMATICALLY_MISSING | Same as AA |
| Low-A | Not independently re-verified in this audit (internal-only artifact, not exported) | NOT_VALIDATED (by this package) | See `PUBLICATION_POLICY.md` — Low-A is never opened by any adapter here |
| CPX/DSL | No dedicated artifact exists | UNAVAILABLE | Research-only, no output to assess |

## Park factor coverage

| Level | Coverage | Trust status | Evidence |
|---|---|---|---|
| All MiLB levels, 2021-2025 | `coverage_share == 1.0` on every one of 600 team-season rows (complete universe by construction) | TRUSTED | `milb_park_factors_v2.parquet` invariant, enforced by `tests/test_milb_empirical_park_factors.py` upstream |
| Deprecated air-density index (pre-v2) | 3.12% of games silently absent, 4 venues zero-coverage, missingness correlated with run environment (z=-5.76) | KNOWN_DEFECT — `SELECTED_SAMPLE_INVALID`, formally deprecated | `environment_engine/PRODUCTION_STATUS.json`; do not use for anything current |

## Identity field coverage (measured directly from `eephus_identity.parquet`, 10,679 players)

| Field | Coverage share | Trust status |
|---|---|---|
| `name` | 100.0% | TRUSTED |
| `fangraphs_id` | 55.6% | USABLE_WITH_FILTER — check `fangraphs_coverage` before joining |
| `bbref_id` | 55.6% | USABLE_WITH_FILTER |
| `retro_id` | 54.9% | USABLE_WITH_FILTER |
| `dob` (exported as `birth_year`) | 54.7% | USABLE_WITH_FILTER |
| `organization` | 54.6% | USABLE_WITH_FILTER |
| `primary_position` | 54.7% | USABLE_WITH_FILTER |
| `bats` | 7.6% | SYSTEMATICALLY_MISSING — do not rely on this field for anything requiring near-complete coverage |
| `throws` | 0.0% | UNAVAILABLE — placeholder column, "not on disk," always null |
| `secondary_positions` | 0.0% | UNAVAILABLE — same as `throws` |

These are real, measured coverage shares (computed directly against the live parquet at report time), not estimates.

## Framing

`pitcher_ewar.parquet`'s `framing_treatment` column takes the value `DISCLOSED_SHARED` — meaning framing credit is disclosed as shared between pitcher and catcher rather than fully attributed to the pitcher. Treat any framing-adjacent signal as `PARTIAL` trust for isolating pure pitcher skill.

## Pitch-type, velocity, location, exit velocity, launch angle, catcher, tracking-source metadata

**Not assessed by Eephus today** — no Eephus production system currently ingests or scores raw pitch-by-pitch tracking data (this is confirmed by the absence of any arsenal/pitch-type output anywhere in either pitcher-eWAR stack, per `reports/REPOSITORY_RECONNAISSANCE.md`). Classification: `NOT_VALIDATED` for all of these fields — Eephus has no prior finding to share, favorable or unfavorable. The external builder's own raw-data coverage audit (using the public MLB Stats API / tracking feeds) is the first assessment of these fields; this package does not pre-empt it and should not be read as implying any of these fields are trustworthy or untrustworthy.

## Do not infer field quality from non-null rate alone

Every `USABLE_WITH_FILTER`/`SYSTEMATICALLY_MISSING` classification above is backed by a directly-measured coverage share plus, where available, a documented reason (charter-mandated exclusion, missing upstream source, "not on disk" placeholder) — not a bare non-null percentage. Where no reason is known beyond the raw share, the field is marked `NOT_VALIDATED` rather than assigned a trust level it hasn't earned.
