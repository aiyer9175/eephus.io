# Decision Ledger

Consequential choices made while building the Phase 1 pilot, in the order they came up.

1. **Real Eephus champion-benchmark values are deferred, not fabricated.** The private source directories `milb-projections/` was built to export from (`~/pitcher_ewar`, `~/milb_pitcher_ewar`, `~/milb_park_rebuild`, `~/career_outcome_plus`) do not exist on this machine (checked: home directory, `eephus.io`'s sibling directories, depth 6 — nothing found). This pilot proceeds schema-only, using `milb-projections/fixtures/` for structure where relevant, and explicitly flags every point a real benchmark value would be needed. Real integration is a documented next step, contingent on the private exports being supplied later (either by running `milb-projections/adapters/*.py` against the real source paths, or by the exports being handed over directly).

2. **Sampling is stratified by venue within level, not just by level.** A one-game-per-level sanity probe (see `PILOT_SCOPE.md`) showed 100% pitch-tracking coverage at the sampled AAA and Low-A venues and 0% at the sampled AA and High-A venues — the opposite of a clean "AAA good, lower levels worse" gradient. A level-only sample would average this into a misleading fractional number per level. Venue-level stratification is the only way to actually test whether coverage is a level property, a venue/tracking-install property, or both, rather than assuming the answer.

3. **Season chosen: 2025, not 2026.** 2026 is in progress as of this research (today: 2026-07-19); using an incomplete season would bias any within-season "did coverage change" comparison and undercount games per venue for levels/parks with fewer scheduled dates so far. 2025 is the most recent fully completed season.

4. **Raw pulled data is cached locally but never committed.** Consistent with `milb-projections/`'s own reasoning for using JSON over CSV/Parquet (`eephus.io`'s `.gitignore` excludes both globally) — but raw per-game API responses are large, numerous (~300-360 files), fully public, and trivially regenerable from `scripts/`. Committing them would bloat git history for no benefit; a scoped `.gitignore` entry (`milb-pitch-quality-research/data_cache/`) keeps them out entirely. Only the aggregated matrix outputs (small, derived, and the actual research product) are committed.

5. **New sibling directory, not built inside `milb-projections/`.** `milb-projections/`'s own `ARCHITECTURE.md` documents it as additive and read-only with respect to Eephus, with "no consumers inside Eephus itself." Building the actual research inside it would blur a boundary that package's own docs go out of their way to establish. `milb-pitch-quality-research/` is a new, separate directory at the same level.

6. **No push to any remote at any point**, matching the standing precedent in `milb-projections/DECISION_LEDGER.md` #11 — pushing to a shared remote requires separate, explicit confirmation at the time of the request.

7. **Level scope: AAA/AA/High-A/Low-A only, no CPX/DSL.** Matches `milb-projections/manifests/BENCHMARK_MANIFEST.yaml`'s own scope (CPX/DSL have no dedicated pitcher-eWAR artifact in Eephus, so there would be nothing to eventually benchmark against even if coverage there turned out to be good).
