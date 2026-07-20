# Identifiability Report — Phase 1B (Primary Deliverable)

Deliverable 4. Per construct × level: identifiable / partially / not, using which information, at what confidence. Grounded in `RELIABILITY_STATS.json` and `VARIANCE_STATS.json` computed from the full 408,606-pitch, 2,524-pitcher, 4-level Phase 1B dataset. Positive conclusions are not forced — several rows below are negative, per the charter's explicit acceptance of that outcome.

## Velocity

| Level | Identifiable? | Using which information | Confidence |
|---|---|---|---|
| AAA | **Yes** | `startSpeed`, tracked venues (~100% coverage) | High — split-half r=0.98 (n=822 pitchers), between-pitcher ICC 24% |
| AA | **Not from this data source** | No tracking present in the sampled venues | N/A — 0 pitchers with tracked data |
| High-A | **Not from this data source** | Same as AA | N/A |
| Low-A | **Yes, at the 10 tracked (FSL-complex) venues only** | `startSpeed`, tracked subset | High — split-half r=0.99 (n=398), ICC 27% |

## Spin rate

| Level | Identifiable? | Using which information | Confidence |
|---|---|---|---|
| AAA | **Yes** | `spinRate`, tracked venues | High — split-half r=0.98, ICC 27%, but see Information Content Report's completeness caveat (spin is measured less completely than velocity even at tracked venues) |
| AA / High-A | Not from this data source | — | N/A |
| Low-A | **Yes, tracked subset** | `spinRate` | High — split-half r=0.98, ICC 31% |

## Movement (pfxX/pfxZ)

| Level | Identifiable? | Using which information | Confidence |
|---|---|---|---|
| AAA | **Yes** | `pfxX`/`pfxZ`, tracked venues | High — split-half r=0.93-0.97, ICC 12-27% |
| AA / High-A | Not from this data source | — | N/A |
| Low-A | **Yes, tracked subset** | Same fields | High — split-half r=0.91-0.98, ICC 12-35% |

## Fastball / breaking-ball / offspeed quality (family-specific)

| Level | Identifiable? | Using which information | Confidence |
|---|---|---|---|
| AAA / Low-A (tracked) | **Plausible, not directly confirmed** | Nested pitcher×family decomposition shows real family-level and pitcher-level velocity/movement/spin variance | **Moderate** — the underlying fields are reliable, but family-restricted reliability wasn't separately computed this phase (see `LATENT_CONSTRUCT_INVENTORY.md`) |
| AA / High-A | **Not identifiable** | Pitch type identity itself is absent | N/A |

## Whiff rate (outcome, pitcher-aggregate)

| Level | Identifiable? | Using which information | Confidence |
|---|---|---|---|
| AAA | **Partially** | Swing/whiff outcome fields, all pitches | Moderate — split-half r=0.33, promotion-transition r=0.30 (n=348) |
| AA | **Partially, somewhat stronger in this sample** | Same | Moderate — split-half r=0.51 |
| High-A | **Partially** | Same | Moderate — split-half r=0.49 |
| Low-A | **Partially** | Same | Moderate — split-half r=0.34 |

Note: reliability here is a season-aggregate property (many pitches pooled), not a single-pitch property — see `VARIANCE_DECOMPOSITION.md` for why pitch-level ICC (~1.3%) and season-aggregate split-half (~0.3-0.5) are both correct and not contradictory.

## Called-strike rate

| Level | Identifiable? | Using which information | Confidence |
|---|---|---|---|
| All 4 levels | **Not identifiable at this sample size** | Call-outcome fields, all pitches | **Low/negative** — split-half r ranges from -0.10 to +0.06 across levels; promotion-transition r=0.05 (n=404). This is close to what a pure-noise process would produce. |

## Chase rate

| Level | Identifiable? | Using which information | Confidence |
|---|---|---|---|
| AAA (tracked) | **Weakly** | Zone + swing fields | Low-moderate — split-half r=0.21 |
| Low-A (tracked) | **Moderately** | Same | Moderate — split-half r=0.55 — notably higher than AAA in this sample; not explained, flagged as an open question rather than resolved |
| AA / High-A | **Not identifiable** | Requires zone, which is tracking-dependent | N/A |

## Command (zone rate as proxy)

| Level | Identifiable? | Using which information | Confidence |
|---|---|---|---|
| AAA (tracked) | **Not identifiable at pilot sample sizes** | Zone field | Low — split-half r=0.07 at the default threshold; only reaches 0.50-0.67 among the small subset (n=36-144) of pitchers with 200-400+ tracked pitches. Residual (pitch-to-pitch) variance dominates the nested decomposition (~98% of total variance in the zone-rate breakdown). |
| Low-A (tracked) | **Not identifiable at pilot sample sizes** | Same | Low — split-half r=0.19 at default threshold |
| AA / High-A | **Not identifiable** | Zone field absent | N/A |

This is the clearest negative finding of Phase 1B: even where tracking exists, and even with real pitcher-level and family-level velocity/movement signal established elsewhere in this same dataset, a simple zone-based command proxy does not stabilize within this pilot's sample sizes. See `NON_IDENTIFIABLE_CONSTRUCTS.md`.

## Venue/park effects on outcome metrics

| Level | Identifiable? | Using which information | Confidence |
|---|---|---|---|
| All 4 levels | **Not detected at pilot sample size** | By-venue one-way variance decomposition, `ALL_LEVELS` metrics | Between-venue ICC is 0.01-0.3% across every level/metric combination — essentially zero. Either park/scorer effects on these particular outcome definitions are genuinely negligible, or 30-31 venues with the pitch volumes sampled here is too few groups to detect a real but small effect (method-of-moments ANOVA needs adequate between-group replication; not diagnosed further this phase). |

## Promotion-seam persistence (exploratory)

| Metric | Persistence across a level change? | Confidence |
|---|---|---|
| Whiff rate | Some — r=0.30 (n=348 transitions) | Exploratory — see `PHASE_2_RECOMMENDATION.md` caveats on transition-direction ambiguity |
| Called-strike rate | Essentially none — r=0.05 (n=404) | Exploratory, consistent with the within-level unreliability finding above |
| Swing rate, in-play rate, foul rate | Weak — r=0.11-0.17 | Exploratory |

## Observed evidence
Every cell above traces to a specific number in `RELIABILITY_STATS.json`, `VARIANCE_STATS.json`, or `PROMOTION_SEAM_STATS.json` — none are assumed or extrapolated beyond what those files report.

## Inference
A clean two-tier pattern: physically-measured fields (velocity, spin, movement) are reliably identifiable wherever tracking exists, regardless of level; outcome-derived fields are only moderately identifiable (whiff rate) or not identifiable at all (called-strike rate, command) at this pilot's sample sizes, regardless of level or tracking status. Level, by itself, is not the deciding factor for either tier — tracking-venue status is, for the physical tier; sample size and inherent noisiness are, for the outcome tier.

## Speculation
Command may become identifiable at larger sample sizes (the stabilization curve was still rising, not flattening, at the largest thresholds this pilot could test) — this is a hypothesis for Phase 2, not a finding of this phase.

## Future work
Family-restricted reliability for fastball/breaking/offspeed quality specifically (flagged repeatedly above and in `LATENT_CONSTRUCT_INVENTORY.md`); a distance-based command proxy instead of zone-rate; larger per-pitcher samples to properly test whether command and chase-rate reliability continue climbing past this pilot's largest tested threshold (400+ pitches).
