# 09 — Reliability and Sample-Size Rules

## Tiers (`score.sample_quality`)

| tier | rule | published rows |
|---|---|---|
| Insufficient | no meaningful assignment yet (never enters the scored panel) | score suppressed (NaN by contract) |
| Early | 1 active season and no completed promotion | 14,107 |
| Developing | 2 active seasons OR ≥1 meaningful promotion | 12,256 |
| Established | ≥3 active seasons AND ≥3 meaningful assignments | 19,264 |

Early information is **not suppressed** (charter): a first-year score publishes with its
tier label; uncertainty is communicated by tier + shrinkage, not by hiding the number.

## Shrinkage
Public score shrinks toward 100 with k=1 on meaningful assignments
(m=1 → 50% shrink, m=3 → 75% kept, m=8 → 89% kept). Both scores publish:
`advancement_pace_plus` (stabilized, capped) and `advancement_pace_plus_raw_internal`
(+ uncapped internal), per the charter's dual-publication requirement.

## Behavior at the thin end
First-year rows: SD of public score 5.4; only **0.9%** fall outside 85–115. Extreme
small-sample scores are structurally impossible at the public surface (cap + shrinkage),
while genuinely long fast paths (Lawlar-type) still reach the 130 cap.
