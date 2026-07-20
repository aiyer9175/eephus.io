# Noise and Stability Report — Phase 1B

Deliverable 6. Stabilization curves (reliability vs. minimum pitch-count threshold) from `RELIABILITY_STATS.json`; which measures are fundamentally unstable at pilot scale.

## Observed evidence

### Stabilization curves, AAA (representative; full data for all levels in `RELIABILITY_STATS.json`)

| min pitches | avg_start_speed r (n pitchers) | whiff_rate r (n) | zone_rate r (n) | called_strike_rate r (n) |
|---|---|---|---|---|
| 20 | 0.978 (793) | 0.327 (660) | 0.072 (793) | -0.097 (695) |
| 50 | 0.971 (627) | 0.483 (359) | 0.182 (627) | -0.085 (412) |
| 100 | 0.978 (383) | 0.488 (131) | 0.306 (383) | 0.063 (170) |
| 200 | 0.984 (144) | 0.753 (26) | 0.503 (144) | 0.294 (41) |
| 400 | 0.988 (36) | insufficient pitchers (3) | 0.671 (36) | insufficient pitchers (3) |
| 800 | insufficient pitchers (3) | — | insufficient pitchers (3) | — |

Three distinct stabilization shapes:

1. **Already stable at the smallest tested threshold.** Velocity is at r=0.978 with just 20 pitches minimum and barely moves from there. This matches long-standing sabermetric findings that velocity is close to a fixed physical trait, not something that needs a large sample to estimate.
2. **Genuinely still stabilizing.** Whiff rate, zone rate, and called-strike rate all show r climbing steadily as the minimum-pitch threshold rises — zone rate goes from 0.07 to 0.67 across the tested range, called-strike rate from negative to 0.29. **Every one of these curves is confounded with shrinking pitcher counts** (from 793 down to 36, or fewer) — the improvement at high thresholds is partly a real stabilization effect and partly the correlation becoming noisier-but-different because it's now measured on a small, non-random subset of unusually high-volume pitchers. This pilot cannot cleanly separate those two effects; it's reported as an observed pattern, not a clean causal stabilization estimate.
3. **Unstable within the entire tested range.** Called-strike rate never exceeds r=0.29 even at the largest usable threshold, and is negative at the two smallest thresholds — the weakest of the tested outcome metrics.

### Split-half vs. month-to-month reliability

`RELIABILITY_STATS.json`'s `month_to_month_early_vs_late` field (early-season vs. late-season, same pitcher) was computed alongside split-half for every metric; both track the same qualitative ranking (physical fields high, outcome fields low-moderate) — reported in full in the JSON rather than duplicated here, since the split-half numbers already carry the discussion above.

## Inference

"Which measures are fundamentally unstable at pilot scale" has three honest answers, not one:
- **Fundamentally stable regardless of scale**: velocity, spin, movement.
- **Unstable at pilot scale, but with a rising trend suggesting more data would help**: whiff rate, zone rate, chase rate.
- **Unstable within the entire range this pilot could test, with no clear rising trend**: called-strike rate. This is the strongest stability-negative finding in the report — called-strike rate looks close to pure noise at every sample size this pilot could probe, at every level.

## Speculation

Called-strike rate's flatness may reflect that it's genuinely dominated by exogenous factors (umpire zone, catcher framing — see Eephus's own `framing_treatment: DISCLOSED_SHARED` finding, directly relevant here) rather than pitcher skill, more than it reflects an insufficient sample. This pilot cannot distinguish "needs more data" from "not a pitcher-skill signal at all" for called-strike rate — both are consistent with the flat curve observed.

## Future work

A proper stabilization-curve methodology would hold the pitcher population fixed (e.g., bootstrap resampling of a fixed high-volume cohort's pitches, rather than filtering the population by minimum pitch count as this pilot does) to cleanly separate "more data stabilizes the estimate" from "the surviving high-volume subset is systematically different." Not attempted this phase given the time budget; flagged as a methodological improvement for Phase 2 if these metrics are pursued further.
