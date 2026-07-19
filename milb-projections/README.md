# MiLB Pitch-Quality Research Handoff

## What this is

A packaging layer that exports Eephus-specific assets — model outputs, schemas, methodology, identity mappings, park factors, and governance rules — so that an external, technically competent builder can independently research a **MiLB pitch-quality and arsenal proxy system**, and later benchmark it against the existing Eephus pitcher ecosystem, without having to reverse-engineer or duplicate that ecosystem.

The external builder is assumed to be able to pull public MLB/MiLB data (pitch-by-pitch, boxscore, roster, schedule) directly from the MLB Stats API and other public sources. This package therefore does **not** contain raw public data — only what cannot legitimately be reconstructed externally.

## What this is not

- **Not** the MiLB pitch-quality model itself. No arsenal/Stuff+/Command+ model exists yet anywhere in Eephus (confirmed in `reports/REPOSITORY_RECONNAISSANCE.md`); building it is future, out-of-charter work.
- **Not** a rebuild of any production model. Pitcher eWAR, MiLB park factors, Contact+/Bat-to-Ball+, and the identity system are all reused as-is via read-only export adapters — nothing here recomputes or redefines them.
- **Not** a public data dump. Real row-level values for proprietary/commercial Eephus outputs are delivered through a private, configurable export path (`PRIVATE_EXPORT_REQUIRED` in `config/artifact_inventory.yaml`), never committed to this git history. What's public here is schemas, documentation, synthetic fixtures, and validation tooling.
- **Not** a declaration that the future MiLB pitch-quality model is superior to, or ready to replace, any existing component. The champion–challenger relationship stays open; see `PITCH_QUALITY_RESEARCH_CONTRACT.md`.

## Layout

```
milb-projections/
├── README.md                    — this file
├── SYSTEM_OVERVIEW.md            — end-to-end explanation of the handoff layer
├── ARCHITECTURE.md               — source systems, adapters, exports, contracts, consumers
├── PUBLICATION_POLICY.md         — what's public / private / internal / restricted, and why
├── TEMPORAL_INTEGRITY.md         — historical snapshot rules, leakage guards
├── PORTING_GUIDE.md              — how the external builder obtains/validates/uses each asset
├── BENCHMARK_REQUIREMENTS.md     — champions today, required future comparisons
├── PITCH_QUALITY_RESEARCH_CONTRACT.md — noise-isolation and interpretation rules
├── DECISION_LEDGER.md            — consequential architecture/publication choices
├── KNOWN_GAPS.md                 — missing snapshots, inaccessible assets, weak coverage
├── definitions/                  — one doc per model/concept (what it is, why, limitations)
├── contracts/                    — schemas for every exported artifact
├── manifests/                    — BENCHMARK_MANIFEST.yaml (machine-readable benchmark registry)
├── adapters/                     — read-only export adapters (new code, configurable paths)
├── fixtures/                     — synthetic, non-sensitive sample data matching real schemas
├── reports/                      — reconnaissance, inventory, audits, final readiness reports
└── tests/                        — schema/cardinality/temporal/versioning/compatibility tests
```

## Start here if you are the external builder

Read `reports/EXTERNAL_BUILDER_START_HERE.md` (produced at the end of this build) first.

## Start here if you are maintaining this package

Read `reports/REPOSITORY_RECONNAISSANCE.md`, then `reports/ARTIFACT_INVENTORY.md`, then `DECISION_LEDGER.md`.
