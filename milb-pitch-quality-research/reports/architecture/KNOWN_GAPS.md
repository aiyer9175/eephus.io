# Known Gaps — Architecture & Integration Charter

Required Final Deliverable, scoped to this charter. Distinct from the package-root `milb-pitch-quality-research/KNOWN_GAPS.md` (none currently exists at that path from Phase 1A-1C — Phase 1A-1C's gaps live inline in each phase's reports; this file is this charter's own, parallel record).

## Blocking gaps carried forward, unresolved

- **Private `pitcher_ewar`/`milb_pitcher_ewar`/`milb_park_rebuild`/`career_outcome_plus` access.** Unchanged since Phase 1A. No architecture work can close this — it requires either running the `milb-projections/` export adapters against the real source repos (which aren't on this machine) or receiving their output directly.

## New gaps this charter surfaces

- **Two unreconciled public data sources.** This research's pipeline uses the MLB Stats API live-feed; `stuff_plus_aaa` uses Baseball Savant's `statcast-search-minors`. They likely overlap heavily but haven't been compared field-for-field, row-for-row. Blocks any rigorous claim about whether Module 1 duplicates `stuff_plus_aaa` (`BENCHMARK_INTEGRATION.md`, `IMPLEMENTATION_ROADMAP.md` Phase A).
- **No formal confidence intervals anywhere in this research.** Phase 1B/1C used reliability coefficients and R², not bootstrap CIs — a real gap relative to `sem_plus`/`rem_plus`'s existing bootstrap-CI convention in this same codebase (`UNCERTAINTY_ARCHITECTURE.md`).
- **Three modules' own reliability was never tested**, only their relationship to other modules: Module 2 (Arsenal, family-restricted), Module 4 (Ground-Ball), Module 5 (Damage Suppression). Each has a named implementation phase or explicit hold-back status (`IMPLEMENTATION_ROADMAP.md`, `ARCHITECTURE_SIMPLIFICATION.md`) but none is resolved.
- **`xRV models/` ownership is unconfirmed.** A ten-file pickled-model directory with no README, no code referencing it anywhere in the repo, one commit by `jgillisBU`. Not part of this research's architecture, but flagged since it surfaced during the ecosystem survey and no other document in this repo tracks it.
- **No research-pages route exists on the live site at all.** Modules classified Research Metric or Internal Diagnostic (`PRODUCTION_CLASSIFICATION.md`) currently have no publication surface, even internal, beyond this repository's own markdown — a gap in the website's information architecture, not something this charter can build (`WEBSITE_INFORMATION_ARCHITECTURE.md`).
- **No MiLB pitch-quality leaderboard page type exists.** If Modules 2-4/6 eventually warrant a leaderboard (not evaluated as necessary by this charter), building one is new information architecture, not a slot-in to `/mlbstats/`'s existing season-grain MLB leaderboards.
- **Naming collisions across the repo** (`Career+` in `defense-plus/` vs. private `career_outcome_plus`; "SEM"/`sem_plus` vs. `milb-projections`' "SEM-core architecture"; "Contact+" in `swing-plus/` vs. private `~/contact_plus`) — not this research's to fix, but worth a repo-wide documentation pass independent of this charter.

## Explicitly not gaps (resolved or never applicable)

- Tracking-status-vs-level-status routing — resolved, Phase 1A/1B, reconfirmed structurally sound in `TRACKING_BRANCH_ARCHITECTURE.md`.
- Feature-family redundancy — resolved, Phase 1C (one confirmed redundant pair, everything else independent).
- Whether a universal composite score is justified — resolved (no), `ARCHITECTURE_COMPARISON.md`.

## Observed evidence / Inference / Speculation

Every gap here is Observed (a specific, named absence or unresolved question), not speculation about what might be missing. Where a gap has an assigned implementation phase, that's stated; where it doesn't (the private-data blocker, the naming collisions), that's stated too, rather than implying false progress.
