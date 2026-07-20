# Data Audit Report — Phase 1 Pilot

Status: **pilot-scale** (361 games, 3-per-venue stratified sample, 2025 season, public MLB Stats API only). This is the charter's Phase 1 data audit — determining what's recoverable before any model architecture is chosen — not the full multi-season build, and not a model. Full source data: `reports/{FIELD_AVAILABILITY,COVERAGE,MISSINGNESS,TRUST}_MATRIX.{json,md}`.

## Headline finding

**Pitch-tracking coverage in the public MLB Stats API is not a level property. It's a venue/tracking-install property, and it cuts across levels in a specific, identifiable pattern:**

| Level | Venues sampled | Venues with any tracking data | Pattern |
|---|---|---|---|
| AAA | 30 | **30/30 (100%)** | Universal — every AAA park in the sample has full tracking |
| AA | 31 | **0/31 (0%)** | None of the sampled AA parks had any tracking data |
| High-A | 30 | **0/30 (0%)** | None of the sampled High-A parks had any tracking data |
| Low-A | 31 | **10/31 (32%)** | Partial — see below |

The 10 covered Low-A venues are not a random subset — they are **Florida spring-training complexes that double as Low-A (Florida State League) home parks**: Roger Dean Chevrolet Stadium, BayCare Ballpark, Lee Health Sports Complex, TD Ballpark, LECOM Park, Publix Field at Joker Marchant Stadium, Clover Park, George M. Steinbrenner Field, Yankee Complex Field 2, Holman Stadium. Every one of these is a facility an MLB parent club already uses for major-league spring training, where a permanent optical tracking system (Trackman/Hawkeye) was presumably installed for MLB purposes and happens to also cover the FSL games played there. This is a specific, explicable mechanism, not a coincidence.

**Coverage is all-or-nothing at the venue grain, and stable within the season.** Every single one of the 122 sampled venues showed either full coverage or zero coverage across all 3 of its sampled games (spread across April/May, June/July, and August/September) — `MISSINGNESS_MATRIX.md`: 0 "mixed within venue" venues at any level. Whatever determines coverage is a fixed property of the physical installation, not something that turned on or off mid-2025.

**Where data exists, it is genuinely full Statcast/Trackman-grade** — not sparse or partial. Tracked venues show ~99-100% coverage for pitch type, velocity, movement (`pfxX`/`pfxZ`), spin rate/direction, release extension, and plate location, and ~93-100% coverage for batted-ball exit velocity/launch angle. One minor secondary finding: `spin_rate` coverage at a small number of otherwise-fully-tracked AAA venues dips noticeably below the other fields (e.g. The Ballpark at America First Square: 99.9% `start_speed` vs. 68.9% `spin_rate`) — spin appears to be a comparatively less reliable derived quantity even at tracked parks. This is a real, measured pattern, not assumed.

## Corroboration with Eephus's own findings

This pilot was built schema-only, without access to Eephus's real coverage numbers (see `DECISION_LEDGER.md` #1). It's therefore notable that it independently rediscovered a pattern Eephus's own production system already found through a completely different signal: `milb-projections/definitions/COVERAGE_AND_TRUST.md` reports AAA pitcher-eWAR's contact-quality component is covered 2023-2025 (`PARTIAL`, level-and-season-gated) while AA and High-A are **100% `fi_only`** — no contact component exists at all, "by design, not a defect." That's Eephus's own contact-model coverage, derived from a different (proprietary, non-public) pipeline. This pilot's public-API pitch-tracking coverage shows the identical AAA-vs-AA/High-A split. Two independent measurements landing on the same architectural boundary is a meaningfully stronger signal than either alone.

## Implication for the charter's Coverage Philosophy question

The charter explicitly asks whether different levels need different architectures (e.g. "AAA → full arsenal, High-A → fastball-centric, Low-A → velocity-driven" as illustrative examples). The pilot's answer is a specific correction to that framing: **the stratifying variable isn't level at all — it's tracking-install presence, which happens to align with "AAA" almost perfectly and with "Low-A" only at a narrow, identifiable spring-training-complex subset.** A single universal architecture would be wrong for the reason the charter anticipated (heterogeneous information availability), but a *level*-indexed family of architectures would also be wrong — it would incorrectly lump all Low-A parks together and give up on AA/High-A entirely when in fact the real boundary is venue-level and explicable.

Practical scope this implies for any future model build:
- **AAA**: full Statcast-grade tracking-based pitch-quality work is plausible across essentially the whole level.
- **Low-A, FSL/spring-training-complex subset only** (10 of 31 sampled venues): the same tracking-based approach is plausible, but only for pitchers/games at those specific parks — a genuinely smaller, identifiable slice, not "Low-A" broadly.
- **AA, High-A, and the remaining ~2/3 of Low-A**: no tracking-based construct is buildable from this public data source in the 2025 season. Any future model here has to be outcome-only (count/result-based, no velocity/movement/location features) — which is architecturally what Eephus's own FI-runs-based pitcher eWAR already does at these levels, for what looks like the same underlying reason.

## What this pilot does not establish (explicitly out of scope)

- **Reliability/stabilization**: no split-half, month-to-month, or year-to-year reliability has been measured. That's only meaningful within the AAA/FSL-Low-A tracking-eligible subset identified above, and is the natural next phase.
- **Pitch-family-specific coverage**: not broken out yet (e.g. whether breaking-ball spin is measured as reliably as fastball spin). Flagged, not attempted.
- **Whether "0% coverage" is truly total for the season**: each 0%-venue was checked on 3 dates spread across the season; a sporadic single-day outage or install elsewhere in the schedule can't be fully ruled out from 3 samples, though uniform 0% across all 3 widely-spaced dates at every one of 61 AA/High-A venues is strong evidence of a structural absence rather than noise.
- **Real Eephus benchmark comparison**: park factors, pitcher eWAR, identity — all schema-only in this pass (`DECISION_LEDGER.md` #1). No incremental-value claim can be made yet; that requires the real private exports.
- **Any pitch-quality model, identifiability analysis, or negative-control battery.** This is a data audit, not a model build.

## Preliminary answers to the charter's Required Final Questions

Labeled preliminary because the full reliability/validation/negative-control program hasn't run. These are coverage-audit-level answers, not final scientific rulings.

- **Can latent pitch quality be recovered?** Plausibly, but only where tracking data exists — not as a blanket MiLB answer.
- **Can latent arsenal quality be recovered?** Same scope constraint — arsenal-level (movement/spin) constructs require the tracking fields, which are venue-gated as above.
- **At which MiLB levels?** Full: AAA. Partial, venue-specific: Low-A (FSL/spring-training-complex subset only, ~32% of sampled venues). Not from this data source: AA, High-A, remaining Low-A.
- **For which pitch families?** Not yet assessed — future work, only meaningful within the tracking-eligible subset.
- **Using which information?** Full Statcast-grade fields (velocity, movement, spin, location, hit data) where tracking exists; count/outcome-only elsewhere.
- **With what uncertainty?** Not yet quantified — no reliability program has run.
- **How much incremental value over the existing Eephus pitcher ecosystem?** Cannot be assessed yet — blocked on real champion-benchmark exports (see `DECISION_LEDGER.md` #1).
- **Should the project proceed to implementation?** Recommend yes, but explicitly rescoped: a tracking-based pitch-quality construct for AAA (+ the identified Low-A/FSL subset), and continued reliance on outcome-only modeling elsewhere — not a single universal MiLB pitch-quality model, and not yet with a committed architecture.
- **If yes, what architecture?** Not determined by this pilot — that's the job of the reliability and identifiability work this pilot unblocks, not this coverage audit.

## Recommended next steps

1. Obtain real Eephus champion-benchmark exports (park factors v2, pitcher eWAR AAA/AA/High-A, identity) to unblock incremental-value comparisons — currently the single largest gap (`DECISION_LEDGER.md` #1).
2. Run the reliability program (split-half, month-to-month, year-to-year, promotion-seam) on the AAA and Low-A/FSL tracking-eligible subset specifically — the only place it's meaningful.
3. Extend the pilot's venue enumeration to prior seasons (2021-2024) to confirm the AAA/FSL tracking pattern is stable over time, not a 2025-specific artifact (relevant since AAA-wide Hawkeye/optical tracking rollout has its own installation history worth confirming against).
4. Investigate whether pitch-family-specific coverage (e.g. breaking-ball spin reliability) varies within the tracking-eligible subset, per the charter's Coverage Philosophy instructions.
5. Do not attempt a unified AA/High-A/Low-A-broad tracking-based model — the evidence doesn't support one existing in this data source at pilot scale.
