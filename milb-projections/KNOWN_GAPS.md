# Known Gaps

Things that are missing, inaccessible, or weakly covered — recorded here rather than papered over.

## Missing entirely

- **No dedicated MiLB↔MLB Statcast contact-quality portability model.** See `definitions/CONTACT_PORTABILITY.md`. The closest substitute (MiLB rate-skill translation) is exported, clearly labeled as not the same thing.
- **No pitch-type/arsenal-level output anywhere in either pitcher-eWAR stack.** This is precisely the gap the future research effort exists to fill — not a defect in this handoff.
- **No champion-freeze/archive directory for MiLB pitcher eWAR** (exists for MLB pitcher eWAR, not MiLB). Any future restatement of the MiLB stack has no frozen prior version to diff against, unlike the MLB side.
- **No effective-dated ("as of") identity joins.** Both the player-identity system and the team/affiliate/park mapping system are current-state or season-grain only. A future model cannot ask "what team/level was this player on as of a specific date" from Eephus data alone.
- **No standalone uncertainty column on the AAA Contact Management+ intermediate file** (`aaa_contact_runs.parquet`) — use the parent `aaa_pitcher_ewar.parquet`'s `contact_runs_sd` instead.
- **No raw pitch-tracking coverage/trust assessment from Eephus** (pitch type, velocity, location, EV, launch angle, catcher, tracking-source metadata) — no Eephus system ingests this today, so there's no prior finding to share either way. See `definitions/COVERAGE_AND_TRUST.md`.

## Weak / partial coverage

- AAA contact-component coverage is 2023-2025 only (2021-2022 rows are `fi_only`) — see `manifests/coverage_matrix.json` for exact row counts.
- Identity field coverage is uneven: `fangraphs_id`/`bbref_id`/`retro_id`/`dob`/`organization`/`primary_position` are only ~55% covered; `bats` is 7.6%; `throws` and `secondary_positions` are 0% (placeholder columns, never populated upstream).
- Only one dated snapshot exists in the MLB pitcher eWAR archive (2026-07-17) — insufficient for a true time-series; classified `CURRENT_MODEL_BACKFILL`, not `TRUE_HISTORICAL_SNAPSHOT`, in `reports/HISTORICAL_SNAPSHOT_AUDIT.md`.

## Access-restricted, not fabricated around

- Low-A MiLB pitcher eWAR — `INTERNAL_ONLY`, publication withheld pending a separate approval that is outside this charter's authority to grant.
- 127 proprietary-headered source files — their methodology is documented; their code is not republished. See `PUBLICATION_POLICY.md`.

## Deferred to a separate, already-chartered effort

- `env_foundation_integration`'s `m06_stadium_translation.py` and `m09c_lower_milb_translation.py` are frozen, reading the deprecated air-density park index, pending `NEXT_MILB_TRANSLATION_REBUILD_CHARTER.md` (a distinct, not-yet-executed piece of work). This handoff references but does not touch or fix them.

## Not yet built in this package (future work if the private-export surface needs to grow)

- A dedicated adapter for `pitcher_ewar/champion/` (the MLB champion freeze) and for `MILB_PITCHER_EWAR_RESTATEMENT_LEDGER.parquet` — both are documented and classified in `manifests/BENCHMARK_MANIFEST.yaml` (`export_path: "... not yet built ..."`) but no `adapters/export_*.py` exists for them yet, since neither was strictly required to unblock the external builder's first research pass. Building them is a natural next increment, not a blocker.
- No dedicated adapter/export exists for the `career_outcome_plus/milb/handoff/00_baseline_manifest.json`-covered artifacts beyond `latent_rate_talent.parquet`/`milb_xwar_projection.parquet` (already covered by `adapters/export_contact_translation.py`) — the other three (`milb_career_distribution.parquet`, `milb_xfv_projection.parquet`, `milb_debut_timing.parquet`, `prospect_mlb_status.parquet`) are out of scope for pitch-quality research specifically and were not exported.
