# Current Ecosystem Map

Phase 1 of the Architecture & Integration Charter. Maps every pitcher-relevant (and adjacent) system found in the actual `eephus.io` repository — this git worktree, which is a real checkout of the production platform, distinct from the private computation repos (`~/pitcher_ewar`, `~/milb_pitcher_ewar`, `~/milb_park_rebuild`, `~/career_outcome_plus`) confirmed absent from this machine since Phase 1A. Built from a three-agent codebase survey (website/API/publication, pitcher-adjacent model packages, SEM/Contact+/eWAR/glossary references) rather than assumption.

## Observed evidence

### The single production application

**`prospect-tracker/`** *is* eephus.io — a static site (`build_site.py` generates it; no JS framework, no bundler, no traditional backend API). Routes include `/prospx/` (flagship prospect tracker, pitcher cards live here), `/mlbstats/` (Starter/Bullpen leaderboards), `/pal/` (Pitcher Alchemy Lab), `/collegesavant/` (has its own separate pitcher app), `/glossary/`, `/projections/`, `/fa/`, `/trademachine/`, `/fantasy/`. Data is served as static JSON fetched client-side (`SITE_MAP.md` enumerates the exact JSON-per-route mapping); the only real backend is Supabase, scoped entirely to accounts/forums, unrelated to analytics data.

**Publication mechanics**: production is a single-writer nginx box running `deploy/nightly-build.sh` on cron (03:10 ET) — pull → pipeline (`run_monthly.py`, full on the 1st / `--daily` otherwise) → `build_site.py` → pytest gate → rsync per the shared manifest `deploy/publish_paths.txt`. GitHub Actions (`.github/workflows/deploy-prospect-tracker.yml`, the only workflow in the repo) builds and tests on every push but only publishes if `EEPHUS_CI_PUBLISH=true` is explicitly armed — off by default after a documented July 2026 incident where a CI cold-rebuild overwrote production history. `prospects.db` (SQLite) is the durable state a cold rebuild cannot recreate.

### Existing pitcher-relevant systems, by name

| System | File(s) | What it actually is | Verdict (model registry) | Surface |
|---|---|---|---|---|
| `stuff_plus_aaa` | `prospect-tracker/stuff_plus_aaa.py` | In-house LightGBM, physics-only features (velocity, spin, extension, `pfx_x`/`pfx_z`, release position, **arm angle**, velo-delta-vs-primary) → `delta_run_exp` label. Data source: **Baseball Savant `statcast-search-minors`**, not the MLB Stats API feed this research used. AAA 2023+ only. Reliability-shrunk toward pool mean below 300 pitches. | `provisional` | PROSPX pitcher cards, MLB player pages (recent graduates) |
| `stuff_plus_external` | `prospect-tracker/mlb_stuff_plus.py` | Port of the external tjStuff+ LightGBM model (2020-2023 train), applied to MLB Stats API pitch feeds. No local baseline, no local eval artifact. | `unvalidated` | PROSPX pitcher pages |
| `sem_plus` | `prospect-tracker/sem_plus.py` | "Starter Evaluation Metric+" — empirical-Bayes-shrunk, starter-pool-anchored FIP (durability held out). **Not** a structural equation model despite the name; naming collision with `milb-projections`' "SEM-core architecture" (a private, unrelated MiLB-pitcher-eWAR pipeline component). | `validated` | `/mlbstats/` Starter Leaderboards |
| `rem_plus` | `prospect-tracker/rem_plus.py` | Reliever counterpart to SEM+ — empirical-Bayes-shrunk, reliever-pool-anchored FIP. | `validated` | `/mlbstats/` Bullpen Leaderboards |
| `pal_conversion` | `prospect-tracker/pal_conversion.py` | SP↔RP role-conversion fit, uses SEM+/REM+ as predictors. | `provisional` (sign-check only) | `/pal/` |
| `xfv_pitcher` | (data: `data/xfv_eval_pitcher.json`) | Pitcher variant of the eephusFV blended-grade model. | not directly assessed this survey | PROSPX |
| `milb-decision-plus/` | top-level directory (`~/milb_decision_plus` self-identified in `REPORT.md`) | MiLB swing-decision system (Decision+), 6 levels, 2021-2026, stringer-pixel-coordinate zone calibration. Ships descriptive Decision+ plus projected K%/BB%. | descriptive, ships with a stated (not yet wired) integration rule | **Zero consumers found anywhere in this checkout** — fully standalone |

### Confirmed absent from the live site, present only as private references

- **Pitcher eWAR** (MLB and MiLB) — never displayed, computed, or consumed anywhere in `prospect-tracker/`. Appears only (a) inside `milb-projections/`'s documentation and export adapters, and (b) as a forbidden-consumer name in `advancement_pace/`'s isolation contract (governance, not evidence of use).
- **Contact+** (the private `~/contact_plus`) — referenced only from `milb-projections/`. A *different*, locally-built "Contact+" (`swing-plus/contact_v2.py` etc.) exists inside `swing-plus/`, explicitly built as a challenger to the private repo's output — a second naming collision.
- **MiLB park factors v2** (`~/milb_park_rebuild`) — private, absent. Two unrelated local park-factor efforts exist: `swing-plus/park_factors.py` (MLB hitter-side) and `prospect-tracker/tools/milb_park_factors.py` (an explicitly-not-shipped feasibility probe, "R-PARK").
- **`career_outcome_plus`** — private, absent, referenced extensively by `milb-projections/` and by `advancement_pace/`'s isolation guard. A *different* "Career+" exists locally in `defense-plus/` (fielder-value-only) — a third naming collision worth flagging so this charter never conflates the two.

### Other pitcher-adjacent packages, briefly

- **`playing-time-model/`** — hitter-only; actively filters out pitcher rows at the spine-build stage (`# hitter filter: drop pitchers-who-batted`). Not a consumer candidate for anything pitch-quality related.
- **`advancement_pace/`** — descriptive-only, AST-import-guarded and test-enforced (fail-closed) against feeding *any* predictive/valuation system, including eWAR. Not a consumer candidate.
- **`defense-plus/`** — fielder/hitter defensive value; no pitcher content.
- **`swing-plus/`** — hitter bat-tracking; touches pitcher data only as opposing-arsenal matchup context (`matchup.py`), not pitcher evaluation.
- **`xRV models/`** (top-level, space in name) — 10 pickled per-pitch-type run-value models, one commit, no README, **no code anywhere in the repo loads them**. Orphaned; flagged, not assumed live.
- **Root-level `data_analysis.py`, `xwoba_model.pkl`, `NCAA 26 Averages S+.csv`** — pre-merge legacy artifacts from a different original repo, zero current-code references. Not part of the live ecosystem.

### Glossary / registry infrastructure

- **`prospect-tracker/data/glossary.json`** (268 entries, versioned, categorized) — the site's actual glossary, rendered at `/glossary/`.
- **`prospect-tracker/data/model_registry.json`** + generated `MODEL_REGISTRY.md`** — 113 models, per-model `verdict` (validated/provisional/unvalidated/deprecated), staleness-gated (240 days), tested for regeneration-sync (`test_generated_docs_in_sync.py`).

## Inference

The original Phase I research charter's framing of "pitcher eWAR, Contact+, SEM-derived components" as the production champion describes systems that are real and rigorously built, but **live in a different repository than this one and have zero presence on the actual website**. The website's real pitcher-quality story runs through `stuff_plus_aaa`/`stuff_plus_external` (pitch-level) and `sem_plus`/`rem_plus` (season-level run-prevention skill) — a fundamentally different (though not necessarily contradictory) set of systems. Per your decision, this charter treats these as a tiered champion structure: `stuff_plus_aaa`/`stuff_plus_external` are the champion for the pitch-quality/arsenal layer this research's modules address; the private `pitcher_ewar` stack remains the champion for full pitcher value, a layer this research's modules don't directly answer.

`milb-decision-plus/` is architecturally significant precedent: it's a fully-built, well-validated MiLB-level metric system with a stated (documented) integration rule that has never actually been wired into anything. This is the clearest cautionary case for this charter's Consumer Audit (Phase 13) — evidence that "build it and it gets consumed" is not a safe assumption in this codebase, and every module this charter proposes needs an explicit, real consumer, not just a stated intent.

## Speculation

None — every claim in this document traces to a specific file path found by the three-agent survey.

## Future work

`xRV models/`'s ownership/purpose should be confirmed with whoever committed it (`jgillisBU` per git log) before any future work assumes it's either live or safe to ignore. The `sem_plus`/"SEM-core" and `contact_v2`/`contact_plus` and `defense-plus Career+`/`career_outcome_plus` naming collisions should be flagged to whoever maintains repo-wide documentation, independent of this charter's scope.
