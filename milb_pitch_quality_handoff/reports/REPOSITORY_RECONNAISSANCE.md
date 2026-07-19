# Repository Reconnaissance — MiLB Pitch-Quality Handoff

Status: Phase 0 deliverable. Read-only investigation; no production code, model outputs, or repository history was modified to produce this report.

## 1. Repositories and directories inspected

| Path | Is a git repo? | Governance files found | Role |
|---|---|---|---|
| `~/Desktop/eephus.io` | Yes (`origin` = `github.com/aiyer9175/eephus.io`, private) | `README.md` only (no `AGENTS.md`/`CLAUDE.md`/`CONTRIBUTING.md` at root) | The actual Eephus platform — 6-person shared codebase. Last commit 2026-07-17. **308 pre-existing untracked files/dirs** at time of this work (unrelated WIP — left untouched). This charter's branch `milb-pitch-quality-handoff` was cut from `skill-modules-full-projection`. |
| `~/swing_plus` | Yes, no relevant remote configured | `CLAUDE.md` | Hitter Swing+/bat-tracking model. Unrelated to this charter (no pitcher/MiLB content). Has its own unrelated uncommitted WIP (park-factors-production branch) — **not touched**. |
| `~/career_outcome_plus` | No | none | Authoritative player-identity builder (`build_eephus_identity.py`) and MiLB→MLB career/rate-skill translation (`milb/` subdir). Copyright-headered (see §5). |
| `~/milb_pitcher_ewar` | No | none | Current MiLB pitcher eWAR stack (AAA/AA/High-A/Low-A/CPX/DSL). Copyright-headered. |
| `~/pitcher_ewar` | No | none | MLB pitcher eWAR — the cross-stack "champion." Copyright-headered. Has its own `champion/` freeze directory. |
| `~/milb_park_rebuild` | No | none | Current authoritative MiLB park-factor layer (v2.0.0, shipped 2026-07-18). Copyright-headered. |
| `~/environment_engine` | No | none | MLB-side air-density/wind/ball-flight physics engine — still authoritative for MLB. Its MiLB park/game-environment outputs are formally deprecated (`SELECTED_SAMPLE_INVALID`). |
| `~/env_foundation_integration` | No | none | Integration layer wiring Environment Engine outputs into consumer modules (m01–m10). Two modules (m06, m09c) are frozen pending the MiLB translation rebuild. |
| `~/bat_to_ball_plus`, `~/contact_plus`, `~/damage_conversion_plus` | No | `CLAUDE.md` in each | MLB-only hitter contact/damage models. **No MiLB dimension** — not a "contact portability" system. |
| `~/identity_plus` | No | none | Unrelated: a descriptive batted-ball explanation-layer model ("Identity+", M17), not an ID-mapping system. Name collision only. |
| `~/translation_layer` | No | none | MLB park/platoon/weather context-translation tool for projections. Not level portability. |
| `~/milb_decision_plus` | No | none | Universal-level chase/decision proxy (stringer x/y), production/public. Relevant as a fallback signal source where Statcast doesn't exist. |

No repository-level governance files (AGENTS.md/CLAUDE.md/CONTRIBUTING.md) exist at the root of `eephus.io`, so this charter's own rules (preserve production, no duplication, additive adapters only, no push without explicit permission) are the applicable governance for repo-root behavior. Three research directories (`bat_to_ball_plus`, `contact_plus`, `damage_conversion_plus`) carry their own `CLAUDE.md` with model-specific "don't touch" rules (documented in the artifact inventory) — none of those rules are inconsistent with this charter; they concern retraining/feature choices, not publication.

## 2. Central finding: "contact portability" as scoped in the charter does not exist as a shipped asset

The charter assumes a dedicated MiLB↔MLB contact-quality-portability model. Investigation across `bat_to_ball_plus`, `contact_plus`, `damage_conversion_plus`, `career_outcome_plus`, `translation_layer`, `variance_plus`, `identity_plus` found:

- All Statcast-collision-quality models (Bat-to-Ball+, Contact+, Damage Conversion+) are **MLB-only** (2023H2+ bat-tracking era) with zero MiLB dimension.
- The only real MiLB→MLB translation code is `career_outcome_plus/milb/block2_translations.py`, which translates **rate-skill persistence** (K%, BB%, ISO, wOBA, Decision+) — not Statcast contact quality (EV/barrel) — and its own docs state contact-quality **cannot** be translated below AAA due to missing Statcast coverage there ("missing-info lane").
- The code closest to this concept (`career_outcome_plus/milb/*.py`) carries `Copyright (C) 2026 Will Cahoon — All Rights Reserved / Proprietary and confidential` headers, in tension with the project's own metric registry (`identity_plus/registry/REGISTRY.md`) which tags the derived production outputs (`milb_proj_plus`) as Public.
- No pitcher-facing consumer (`milb_pitcher_ewar`, `pitcher_ewar`) currently imports any hitter-contact-quality or translation output — the stated purpose ("support MiLB pitcher/contact-quality modeling") has **no existing wiring** to build on.

**Consequence for the rest of this charter:** Phase 3 ("Publish contact-portability contracts and exports") cannot package a "contact portability" model that doesn't exist. Instead it will document (a) what does exist and is closest (the MiLB rate-skill translation architecture and its explicit data-coverage limitation), and (b) formally record the absence as a `KNOWN_GAPS.md` item, per the charter's own instruction not to fabricate missing fields. This is flagged, not treated as a blocker — see `reports/ARTIFACT_INVENTORY.md`.

## 3. Authoritative sources, by artifact group

**A. MiLB Pitcher eWAR** — `~/milb_pitcher_ewar/data/{aaa,aa,higha,lowa}_pitcher_ewar.parquet`, schema `milb-pitcher-ewar-1.0.0` per `MILB_PITCHER_EWAR_SCHEMA.json`. AAA/AA/High-A = public/shippable; Low-A = internal-only (publication withheld pending approval); CPX/DSL = research-only, no dedicated artifact. No pitch-type/arsenal output exists anywhere in this stack (explicitly out-of-scope per its own manifest). No champion-freeze/archive directory exists yet for MiLB (unlike MLB — see below); this is a real infrastructure gap this handoff should not paper over.

**B. MLB Pitcher eWAR (champion)** — `~/pitcher_ewar/data/pitcher_ewar.parquet`, schema `pitcher-ewar-1.1.0`. Has a genuine frozen-champion directory (`~/pitcher_ewar/champion/`, MD5-checksummed) and a dated `data/archive/` with prior-version snapshots — this is the cross-stack reference point (`MILB_PITCHER_EWAR_MANIFEST.json` cites `"champion_reference": "pitcher-ewar-1.1.0 (MLB)"`).

**C. MiLB Park Factors** — `~/milb_park_rebuild/data/milb_park_factors_v2.parquet`, version `milb-park-factors-2.0.0`, grain team-season, 600 rows, 124 venues. Only `run_park_factor`/`hr_park_factor` exist (no contact/strikeout/batter-eye factor). Supersedes `~/environment_engine`'s MiLB park artifact, which is formally marked `SELECTED_SAMPLE_INVALID` (a coverage/missingness defect — 3.12% of games silently absent from the old engine, correlated with run environment — not a "weather bug" as originally hypothesized). Two consumers (`env_foundation_integration/modules/m06_stadium_translation.py`, `m09c_lower_milb_translation.py`) are still reading the deprecated artifact and are formally frozen (`FROZEN_PENDING_INPUT_REBUILD`) pending a separate, not-yet-executed rebuild charter — **this handoff must not be mistaken for that rebuild** and must not touch m06/m09c.

**D. Identity** — Player identity: `~/career_outcome_plus/build_eephus_identity.py` → `~/career_outcome_plus/data/eephus_identity.parquet` (current-state only, no effective-dating, no team/affiliate/league/park columns — those live in a separate, disjoint system). Team/affiliate/park/venue: `~/milb_pitcher_ewar/pipeline/build_infrastructure.py` → `milb_affiliate_mapping.parquet` / `milb_park_mapping.parquet` / `milb_league_environment.parquet` (season-grain, **not joined to player identity anywhere in the codebase today**). Neither system supports historical point-in-time joins. `chadwick_birthdays.csv` carries full (year/month/day) birthdates — flagged for redaction to birth-year-only before any public export.

**E. Historical snapshots** — Genuine dated archive infrastructure exists only for MLB pitcher eWAR (`~/pitcher_ewar/data/archive/`, `~/pitcher_ewar/champion/`) and for the MiLB park-rebuild's own restatement ledger (`MILB_PITCHER_EWAR_RESTATEMENT_LEDGER.parquet`, a genuine before/after diff of the v1.1.0 restatement). MiLB pitcher eWAR itself has no archive/snapshot directory — only current-state files. `career_outcome_plus/milb/handoff/00_baseline_manifest.json` is a single dated Phase-0 baseline freeze, not a running snapshot series.

## 4. Known consumers (cross-directory)

- `bat_to_ball_plus`/`contact_plus` outputs → consumed by `arsenal_vulnerability`, `eowar_offense_remediation`, hitter-ecosystem website code. All MLB-only; no MiLB pitcher consumer exists.
- `eephus_identity.parquet` → consumed by `build_website_projection.py`, `swing_plus/publish_and_validate.py`, `advancement_pace/build_history.py`, `pd_integration_audit`. None of these join it against the team/affiliate/park mapping system.
- `milb_park_factors_v2.parquet` → newly authoritative; its own rebuild pipeline (`finalize_park_layer.py`) is the only current consumer feeding restated MiLB pitcher eWAR v1.1.0. `env_foundation_integration`'s m06/m09c have **not** migrated to it yet (frozen on the deprecated artifact).
- MLB `pitcher_ewar` and MiLB `milb_pitcher_ewar` are structurally parallel (same schema shape, same run-decomposition logic) but have zero code-level coupling — no shared import found.

## 5. Publication-restriction signal

127 files across `career_outcome_plus`, `milb_pitcher_ewar`, `pitcher_ewar`, and `milb_park_rebuild` carry `Copyright (C) 2026 Will Cahoon — All Rights Reserved / Proprietary and confidential` headers. Per [[feedback_commercial_data_licensing]] (Eephus is a commercial platform; no non-commercial-only data feeds may be used in anything published), and per the charter's own instruction not to publish restricted data or introduce a second source of truth: **no original pipeline/model source files will be copied verbatim into the public handoff package.** Export adapters will be newly written, reading from configurable paths, producing only derived contracts/schemas/documentation/fixtures — never re-publishing the underlying proprietary implementation. This is recorded as a standing rule in `PUBLICATION_POLICY.md` (Phase 2).

## 6. Repository mechanics affecting this build

- `eephus.io/.gitignore` globally ignores `*.csv` and `*.parquet` (with one unrelated carve-out for `prospect-tracker/manual_rankings.csv`). Any fixture files this handoff produces must therefore use a non-ignored format (`.json`, `.jsonl`, or an explicit `.gitignore` negation scoped to `milb_pitch_quality_handoff/fixtures/`) — decided in Phase 2 scaffolding.
- No remote push has been made and none will be made without separate, explicit user confirmation at the time of the request (independent of what the charter's Phase 15 instructions say about branch/PR workflow).

## 7. Architecture graph

```text
                    AUTHORITATIVE SOURCE                         PRODUCTION OUTPUT
                    --------------------                         -----------------
  career_outcome_plus/build_eephus_identity.py  ------------->  data/eephus_identity.parquet
                                                                 (current-state player identity)

  milb_pitcher_ewar/pipeline/build_infrastructure.py -------->  data/milb_affiliate_mapping.parquet
                                                                 data/milb_park_mapping.parquet
                                                                 data/milb_league_environment.parquet
                                                                 (season-grain team/park; NOT joined to identity)

  milb_pitcher_ewar/pipeline/{build_sem_ledgers,               data/{aaa,aa,higha,lowa}_pitcher_ewar.parquet
    assemble_aaa_ewar,...}.py  ------------------------------>  (schema milb-pitcher-ewar-1.0.0/1.1.0)

  pitcher_ewar/pipeline/assemble_pitcher_ewar.py -------------> data/pitcher_ewar.parquet  (champion, 1.1.0)
                                                                 champion/ (frozen 1.0.0-CANDIDATE, MD5s)
                                                                 data/archive/ (dated snapshots)

  milb_park_rebuild/{build_park_factors_v2,                    data/milb_park_factors_v2.parquet (2.0.0)
    finalize_park_layer}.py  ---------------------------------> + restated milb_pitcher_ewar v1.1.0 ledgers
                                                                 + MILB_PITCHER_EWAR_RESTATEMENT_LEDGER.parquet

  environment_engine (MLB physics core, still authoritative) -> data/park_air_factors.parquet (MLB only)
  environment_engine (MiLB layer, DEPRECATED/SELECTED_SAMPLE_INVALID) -> superseded by milb_park_factors_v2

                            |
                            v
              HANDOFF EXPORT ADAPTERS (new, this charter)
              adapters/*.py — read-only, configurable path,
              no recomputation, no verbatim proprietary source
                            |
                            v
              PUBLISHED CONTRACT / PRIVATE BUNDLE
              contracts/*.schema.json, manifests/BENCHMARK_MANIFEST.yaml,
              fixtures/*.json (synthetic), definitions/*.md
                            |
                            v
              FUTURE EXTERNAL RESEARCH BUILDER
              (MiLB pitch-quality challenger, pulls MLB API directly,
               consumes only what's in this package)
```

## 8. Unresolved ambiguities / carried into Phase 1

1. Whether Low-A MiLB pitcher eWAR (internal-only, publication withheld) should be represented in the handoff at all, or only referenced as `PRIVATE_EXPORT_REQUIRED`/`INTERNAL_ONLY` with schema-only publication. Deferred to Phase 1 classification.
2. Whether the "contact portability" gap (§2) should be satisfied by documenting the rate-skill translation architecture as a partial substitute, or left as a pure `KNOWN_GAPS.md` entry with no export at all. Deferred to Phase 3.
3. Whether `env_foundation_integration`'s frozen m06/m09c modules should be mentioned only as a dependency-map note (no export) since they are out of scope (that rebuild is a separate, not-yet-chartered project). Current plan: reference only, no export.
4. The identity system's lack of effective-dating is a genuine limitation for "historical joins" (charter Phase 6 requirement) — will be documented as a known limitation, not fabricated.
