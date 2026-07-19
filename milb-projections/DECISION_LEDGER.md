# Decision Ledger

Consequential architecture and publication choices made while building this package, in the order they came up.

1. **Repository target: build inside `eephus.io`, on a new branch, rather than a standalone repo.** `eephus.io` is the only actual "Eephus" git repository; a standalone repo would satisfy the charter's letter but not its instruction to reuse an existing appropriate repository/namespace. Confirmed with Will before starting (see `reports/REPOSITORY_RECONNAISSANCE.md` §1). The branch (`milb-pitch-quality-handoff`) is additive only — the pre-existing 308 untracked files in the checkout were never staged, added, or touched.

2. **No original proprietary source is ever copied into this package.** 127 files across the source directories carry `All Rights Reserved` headers. Every adapter is newly authored, reads from a configurable path, and contains no scoring/feature-engineering logic from the source systems. See `PUBLICATION_POLICY.md`.

3. **"Contact portability" is documented as a gap, not fabricated.** No dedicated MiLB↔MLB Statcast contact-quality model exists anywhere in Eephus. Rather than inventing one or silently omitting the whole artifact group, the closest real asset (MiLB rate-skill translation) is exported and clearly labeled as a substitute with an explicit "this is not what it might look like" warning in `definitions/CONTACT_PORTABILITY.md`.

4. **Team/affiliate/park/league mapping is classified `NOT_NEEDED`, not exported.** It's reconstructable directly from the public MLB Stats API, which the charter itself says the external builder can already pull. Exporting it would duplicate public data for no reason and bloat the private-export surface.

5. **`dob` is unconditionally redacted to `birth_year`** in the identity export — not configurable, not opt-out. Full month/day birthdate is more granular than what's typically published for these players and isn't needed for the stated purpose (age-on-date at year granularity is sufficient).

6. **Low-A MiLB pitcher eWAR is never opened by any adapter in this package**, not just excluded from the output. This was a deliberate code-level choice (the adapter's level list simply omits the Low-A path) rather than a runtime filter, so a future maintainer editing the adapter can't accidentally re-enable it without noticing the omission is structural.

7. **Fixtures use `.json`, not `.parquet`/`.csv`.** `eephus.io`'s `.gitignore` globally excludes both those extensions repo-wide; rather than adding a scoped negation (which risks accidentally un-ignoring something elsewhere), fixtures are plain JSON with an explicit row-list structure that any language can parse.

8. **`coverage_matrix.json` lives under `manifests/`, not a separate `context/` directory**, deviating from the charter's suggested layout. The rest of this package's structure (`definitions/`, `contracts/`, `manifests/`, `adapters/`, `fixtures/`, `reports/`, `tests/`) doesn't otherwise use a `context/` directory, and introducing one for a single file seemed like unnecessary structure. Recorded here per the charter's own instruction to document deviations from its preferred layout rather than force it blindly.

9. **The nine-field per-module documentation template (Purpose/Inputs/Outputs/Authoritative source/Assumptions/Failure behavior/Tests/Downstream consumers/Version behavior) is not applied as a rigid checklist to every `definitions/*.md` file.** Each definitions doc covers the same underlying information (what it is, why, source, fields, feature/label classification, limitations, consumers) in a narrative structure that reads better for a human builder than nine forced headers per file would. The information is complete; the presentation is consolidated. If a future maintainer needs the rigid per-field format for tooling reasons, it can be mechanically derived from the existing docs.

10. **Real-data testing was used throughout, not just fixture testing.** Every adapter was run against the actual production parquet files during development (not just the synthetic fixtures) to catch schema drift the fixtures alone couldn't reveal — e.g., confirming `aa`/`higha` pitcher eWAR genuinely lack a `contact_runs_above_average` column rather than having it null-filled. This is why `tests/` contains both fixture-based tests (safe to run without any Eephus data present) and skip-if-absent tests against real paths (thorough when a full checkout is present).

11. **No push to the `eephus.io` remote has been made at any point in this build**, independent of what charter Phase 15 says about branch/PR workflow — per the standing safety rule that pushing to a shared remote requires separate, explicit confirmation from Will at the time of the request, not standing authorization from having approved the overall charter.
