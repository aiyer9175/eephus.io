# Website Information Architecture

Phase 11. Information architecture only — where things live and what's exposed, not visual design. Mapped onto `prospect-tracker`'s actual existing routes (`CURRENT_ECOSYSTEM_MAP.md`), not a hypothetical new site.

## Per-module classification

| Module | Public? | Internal? | Advanced? | Research-only? |
|---|---|---|---|---|
| Module 1 (Stuff) | Yes | — | No — reliable and interpretable enough for the standard player-page surface | No |
| Module 2 (Arsenal) | — | Yes | — | Yes, until family-restricted reliability confirmed |
| Module 3 (Miss, tracked) | Yes | — | Yes — should carry an uncertainty indicator that basic surfaces don't typically show | No |
| Module 3 variant (Module 6, outcome-only) | Yes, with a strong caveat | — | Yes — the "limited signal" labeling this needs (`PUBLICATION_ARCHITECTURE.md`) is itself an advanced/qualified presentation | No |
| Module 4 (Ground-Ball) | — | Yes | — | Yes, until own reliability confirmed |
| Module 5 (Damage Suppression) | — | Yes | — | Yes |

## Existing routes this research would integrate with

- **Player pages** (`/prospx/#player=`, standalone `prospect-tracker/player/`): the natural home for Modules 1 and 3 once integration-ready — same surface `stuff_plus_aaa`'s pill already occupies, so this would sit alongside it, not create a new page type.
- **Leaderboards** (`/mlbstats/`): not currently a fit — `/mlbstats/`'s existing leaderboards are MLB-level, season-grain (SEM+/REM+); this research's modules are MiLB-level, pitch-grain. A MiLB pitch-quality leaderboard would be a **new page type**, not an addition to an existing one — flagged, not assumed trivial.
- **Pitch pages**: no such page type currently exists anywhere in `prospect-tracker` (confirmed by the ecosystem survey — CollegeSavant's pitcher app comes closest, with embedded pitch-shape data, but it's college-only and has no MiLB equivalent). Building one would be new information architecture, not a slot-in.
- **Research pages**: **none exist on the live site at all** — `CURRENT_ECOSYSTEM_MAP.md` confirms "no dedicated 'research' route exists on the live site; research is all off-site in sibling directories." This means Modules 2/4/5 (Research-only, per the table above) currently have **no publication surface whatsoever**, even an internal one, beyond this repository's own markdown reports.
- **Glossary** (`/glossary/`): every module above, public or internal, needs an entry per `PUBLICATION_ARCHITECTURE.md` — the glossary's existing `module` field already supports grouping entries by source system, so this is a schema-compatible addition, not a schema change.
- **Methodology**: `prospect-tracker/docs/METHODOLOGY.md` is currently scoped narrowly to prospect valuation (`CURRENT_ECOSYSTEM_MAP.md`) — this research's methodology would need either an extension of that doc or a new, separate methodology doc; the model registry itself (`MODEL_REGISTRY.md`) is the better-fitting existing mechanism (per-model methodology fields already exist there).
- **APIs**: none exist (`CURRENT_ECOSYSTEM_MAP.md` — the "API" is static JSON). This research's outputs would follow the same convention: a static JSON sidecar file, not a new API endpoint.
- **Downloads**: no existing download mechanism was found for any model's raw output in the ecosystem survey — not a gap specific to this research, a repo-wide absence.
- **Developer documentation**: `SITE_MAP.md` (auto-generated route/payload index) is the closest existing mechanism — any new route or JSON payload this research introduces should be added there, keeping it accurate (a `test_generated_docs_in_sync.py`-style sync check already exists and should cover any addition).

## Observed evidence / Inference / Speculation

The "which routes exist" claims are Observed evidence from the ecosystem survey. The "where modules would integrate" claims are Inference — a plausible mapping onto existing routes, not a confirmed design (no design/wireframe work has happened, correctly out of scope per this charter's "information architecture only, not UI" instruction).

## Future work

A MiLB pitch-quality leaderboard and/or a general "research pages" route are both real, identified gaps in the existing site's information architecture — building either is a decision for whoever owns `prospect-tracker`'s roadmap, not something this charter can resolve unilaterally.
