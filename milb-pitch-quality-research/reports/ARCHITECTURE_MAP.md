# Architecture Map — Phase 1

Per the charter's Repository Governance section: read governance/architecture docs, then produce this map before writing any implementation. This is that map.

## What already exists (read, not modified)

```
                    EEPHUS PRODUCTION SYSTEMS (unmodified, this charter never touches these)
                    --------------------------------------------------------------------
  pitcher_ewar (MLB champion, pitcher-ewar-1.1.0)
  milb_pitcher_ewar (AAA/AA/High-A public, Low-A internal, milb-pitcher-ewar-1.0.0/1.1.0)
  milb_park_rebuild (MiLB park factors v2, milb-park-factors-2.0.0)
  career_outcome_plus (player identity, MiLB rate-skill translation)
                            |
                            v  (export adapters, built in a prior session)
              milb-projections/  -- READ-ONLY HANDOFF BOUNDARY
              adapters/*.py, contracts/*.schema.json, fixtures/*.json (synthetic),
              definitions/*.md, manifests/BENCHMARK_MANIFEST.yaml
              -- documents what Eephus can offer this research; contains no
                 pitch-quality model itself; not modified by this effort.
```

**Status found at the start of this work**: the private source directories the adapters read from (`~/pitcher_ewar`, `~/milb_pitcher_ewar`, `~/milb_park_rebuild`, `~/career_outcome_plus`) do not exist on this machine. `milb-projections/`'s own schemas, docs, and *synthetic* fixtures are available and used for structure; real row-level champion-benchmark values are not available in this environment. See `DECISION_LEDGER.md` #1.

## What this pilot adds

```
              PUBLIC MLB STATS API (statsapi.mlb.com)
              -- confirmed reachable from this environment; no auth required
                            |
                            v
              milb-pitch-quality-research/scripts/
              pull_schedule.py    -> data_cache/schedules/{level}.json
              sample_games.py     -> data_cache/samples/{level}.json (venue-stratified)
              pull_game_feeds.py  -> data_cache/{level}/{gamePk}.json (raw, gitignored)
              build_matrices.py   -> reports/{FIELD_AVAILABILITY,COVERAGE,MISSINGNESS,TRUST}_MATRIX.{json,md}
                            |
                            v
              reports/DATA_AUDIT_REPORT.md
              -- Phase 1 synthesis: what's recoverable, where, at pilot scale
```

## Consumers

The only consumer of this pilot's outputs is the rest of this same research effort — later phases (reliability program, identifiability investigation, candidate architecture) if and when they're chartered. Nothing here is wired into any Eephus production system, website route, or refresh job. `milb-projections/` is a read dependency, not a consumer.

## Explicitly out of scope / not touched

- Every Eephus production system listed above — read-only, via `milb-projections/`'s documentation only.
- `milb-projections/` itself — no files under it are modified.
- Any other in-progress work in this repository (`swing-plus/`, `defense-plus/`, `prospect-tracker/`, etc.) — untouched.

## Open gap this map surfaces

Real Eephus champion-benchmark integration (`existing_eephus_pitcher_stack`, park-factor context, identity joins) is a **hard dependency** for any future incremental-value ruling (per `PITCH_QUALITY_RESEARCH_CONTRACT.md`'s prohibition on issuing a production recommendation from in-sample fit alone) but is currently blocked on private data this environment doesn't have. This is recorded, not worked around — see `reports/DATA_AUDIT_REPORT.md` for the concrete next step.
