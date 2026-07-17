# FINAL RULING — Advancement Pace+

**Question:** Can Eephus publish Advancement Pace+ as a stable, peer-adjusted
description of how quickly a player has progressed through the affiliated minor-league
ladder, while guaranteeing the statistic remains completely separate from prospect
projection, talent valuation, and career-outcome modeling?

## Ruling: YES — STAGE FOR PUBLICATION (methodology 1.0.0)

The statistic, its validation, its publication contract, and its future-ready artifact
are complete. Final UI implementation is explicitly deferred to a frontend charter.

## Acceptance gates

| gate | status |
|---|---|
| level history reconciled | PASS — 96,100 authoritative rows, 0 dup keys, statsapi lineage + SHAs (01) |
| meaningful-assignment rules documented | PASS — PA ≥ 30, sensitivity table (03) |
| active-time treatment explicit | PASS — observed-active-seasons core + calendar research version; 2020 asserted absent (04) |
| peer normalization stable | PASS — all cohort margins flat within ±0.4 pts (06, 07) |
| small samples controlled | PASS — k=1 stabilizer + tiers + 70–130 cap; 0.9% of first-year rows outside 85–115 (09) |
| scale interpretable | PASS — 100/110/90 standard-unit scale; anti-percentage language embedded (08) |
| case-study review | PASS — 12-archetype panel reads correctly; rehab-veteran leak found & fixed (10) |
| era and pathway behavior sensible | PASS — era means 99.89–100.13; pathway coefficients face-valid (07, 10) |
| publication schema versioned | PASS — full charter schema + semver + level-map version (12) |
| provenance complete | PASS — input SHAs, artifact SHA, consumer lists (12) |
| predictive isolation tests pass | PASS — 6 standing tests, fail-closed build (11) |
| no production model consumes it | PASS — zero token hits outside the module; registries clean (11) |
| methodology language descriptive | PASS — card copy + glossary + hover (13, 14) |

## What ships
`~/advancement_pace/` — module, `build_all.py` (fail-closed, exit 2), 17 green tests,
`advancement_pace_public.parquet` (45,627 rows / 14,748 players / 2009–2026) with
schema.json + provenance manifest + example players, reports 01–14.

## Standing laws
1. `stat_type="descriptive"`, `model_eligible=false` on every row, forever.
2. No predictive system may read any advancement_pace artifact; the isolation tests are
   part of the permanent build and must stay green in every refresh.
3. The scale is standardized-residual based; percentage language is prohibited.
4. AP+ describes the path already taken. It makes no claim that advancing quickly causes
   future success, and its association with debut outcomes is reported only as face
   validity of the description.

## Known limitations (documented, accepted)
- DSL vs domestic complex not separable at sportId grain (entry pathway absorbs most of it).
- 2020-straddle cohort carries a bounded +1.3 artifact (card footnote specified).
- Hitters only — pitcher version is gated on a pitcher data program.
- 2008-entry careers are left-censored and excluded rather than mis-scored.
