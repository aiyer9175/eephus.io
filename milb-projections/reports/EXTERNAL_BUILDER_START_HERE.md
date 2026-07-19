# External Builder — Start Here

Welcome. This package exists so you can research a MiLB pitch-quality/arsenal proxy system without duplicating what Eephus already has, leaking future information into historical evaluation, or misreading noisy pitch outcomes as intrinsic pitch quality.

## What you can pull yourself, right now, from public sources

Raw pitch-by-pitch data, boxscores, schedules, rosters, and team/affiliate/league/venue reference tables (season, team, parent org, league, level, venue) are all directly available from the public MLB Stats API. Don't look for them here — they're intentionally absent (`config/artifact_inventory.yaml`, classification `NOT_NEEDED`).

## What Eephus provides (this package)

| What | Where | How real | Read first |
|---|---|---|---|
| MLB pitcher eWAR (champion) | `adapters/export_pitcher_ewar_mlb.py` | Private export, `fixtures/pitcher_ewar_mlb.fixture.json` for schema testing | `definitions/PITCHER_EWAR.md` |
| MiLB pitcher eWAR (AAA/AA/High-A) | `adapters/export_pitcher_ewar_milb.py` | Private export, `fixtures/pitcher_ewar_milb.fixture.json` | `definitions/MILB_PITCHER_PROJECTION.md`, `definitions/AAA_CONTACT_PLUS.md`, `definitions/LOWER_LEVEL_PITCHER_COMPONENT.md` |
| MiLB park factors v2 | `adapters/export_park_context.py` | Private export, verified pass-through, `fixtures/park_context.fixture.json` | `definitions/MILB_PARK_FACTORS.md` |
| Player identity (redacted) | `adapters/export_identity.py` | Private export, `fixtures/identity.fixture.json` | `definitions/IDENTITY_SYSTEM.md` |
| MiLB rate-skill translation (contact-portability substitute) | `adapters/export_contact_translation.py` | Private export, `fixtures/contact_translation.fixture.json` | `definitions/CONTACT_PORTABILITY.md` — **read the warning before using `con` as a contact-quality field** |

Getting the real values: run the relevant `adapters/export_*.py` script (requires read access to the corresponding Eephus source directory) or ask Will to run it and share the output via the private path documented in each adapter's docstring.

## How to validate each artifact before you build on it

1. Load the matching fixture in `fixtures/` — confirm your ingestion code handles the schema, nulls, and key structure without modification.
2. Read the matching schema in `contracts/`.
3. Read the matching doc in `definitions/` — every one states what's a feature, what's a label/benchmark, what's context-only, and what the known limitations are.
4. Check `manifests/BENCHMARK_MANIFEST.yaml` for `allowed_uses`/`prohibited_uses` and `historical_status` before using anything in a walk-forward evaluation.

## What cannot be treated as a feature

- Any `pitcher_ewar`/`runs_above_replacement`/run-component column from either eWAR stack — these are the benchmark you're compared against, not something to train on.
- `latent_rate_talent`/`milb_xwar_projection`'s `con` field — it means "1 − K%," not batted-ball contact quality. Do not use it as, or represent it as, a contact-quality signal.

## Which benchmarks are champions

`production_champion`: MLB pitcher eWAR (`pitcher-ewar-1.1.0`) and MiLB pitcher eWAR (AAA/AA/High-A, `milb-pitcher-ewar-1.0.0`/`1.1.0`). Full role assignments in `manifests/BENCHMARK_MANIFEST.yaml`.

## Required scientific interpretation limits

Read `PITCH_QUALITY_RESEARCH_CONTRACT.md` in full before writing a line of the pitch-quality model. In short: keep observed pitch outcomes, context-adjusted outcomes, stable repeatable signal, and latent arsenal quality as four distinct things, never collapse them, and run the full reliability program and negative-control battery before claiming you've found real pitch quality rather than an artifact of park, level, organization, or sample size. Read `TEMPORAL_INTEGRITY.md` before any walk-forward evaluation — most Eephus benchmarks here are current-model backfills, not true point-in-time snapshots.

Nothing in this package is a claim that a future pitch-quality model is ready to replace anything. See `BENCHMARK_REQUIREMENTS.md` for the comparison ladder that has to be run before that conversation even starts.
