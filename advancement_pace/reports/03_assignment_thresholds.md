# 03 — Meaningful-Assignment Rules

**Rule adopted: a level-season counts as a meaningful assignment at PA ≥ 30.**
(`MEANINGFUL_PA_THRESHOLD = 30` in `score.py`.)

Games/days-on-roster variants were not adopted: the authoritative sources are season
lines, and PA is the only exposure measure observed consistently across all five levels
and all 18 seasons. 30 PA ≈ 8–10 games ≈ two weeks of everyday play — comfortably above
September cameos, single-series promotions, emergency assignments, and rehab-length
stints, while letting genuine late-season promotions count.

## Share of level-season assignments retained

| threshold | kept |
|---|---|
| PA ≥ 10 | 88.5% |
| PA ≥ 20 | 81.2% |
| **PA ≥ 30** | **76.3%** |
| PA ≥ 50 | 69.6% |
| PA ≥ 75 | 62.5% |

## Sensitivity of the final statistic to the threshold

Spearman rank correlation of final published AP+ (latest as-of per player) against the
T=30 build:

| comparison | ρ |
|---|---|
| T=20 vs T=30 | 0.965 |
| T=50 vs T=30 | 0.930 |

At the raw-measure level the chosen measure (area pace) is even more robust:
ρ ≥ 0.981 across T ∈ {10, 20, 50, 75} vs T=30 (see 05).

Rankings are threshold-stable; T=30 sits at the flat center of the sensitivity curve
and matches the charter's candidate rule. Changing it is a methodology-version bump.
