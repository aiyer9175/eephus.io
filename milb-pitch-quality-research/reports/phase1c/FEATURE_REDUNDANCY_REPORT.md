# Feature Redundancy Report — Phase 1C

Deliverable 3. Pairwise and partial correlation among family-representative per-pitcher metrics (600 pitchers, `REDUNDANCY_STATS.json`). Redundancy is measured, not assumed — most candidate pairs turn out weakly correlated.

## Observed evidence

### Pairwise correlation matrix (family-representative metrics)

| | velocity | movement_pfx_z | spin_rate | pitch_entropy | zone_rate | chase_rate | whiff_rate | avg_launch_speed | hard_hit_rate | ground_ball_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| velocity | 1.00 | 0.33 | 0.27 | -0.44 | -0.07 | -0.02 | 0.20 | 0.06 | 0.09 | 0.14 |
| movement_pfx_z | 0.33 | 1.00 | -0.06 | -0.12 | 0.15 | -0.11 | 0.05 | 0.08 | -0.03 | -0.25 |
| spin_rate | 0.27 | -0.06 | 1.00 | -0.33 | -0.05 | -0.05 | 0.15 | -0.04 | -0.09 | -0.01 |
| pitch_entropy | -0.44 | -0.12 | -0.33 | 1.00 | 0.02 | 0.17 | -0.08 | -0.00 | -0.00 | -0.04 |
| zone_rate | -0.07 | 0.15 | -0.05 | 0.02 | 1.00 | -0.02 | -0.28 | 0.07 | 0.01 | -0.07 |
| chase_rate | -0.02 | -0.11 | -0.05 | 0.17 | -0.02 | 1.00 | 0.18 | -0.04 | -0.01 | -0.04 |
| whiff_rate | 0.20 | 0.05 | 0.15 | -0.08 | -0.28 | 0.18 | 1.00 | -0.05 | -0.08 | 0.03 |
| avg_launch_speed | 0.06 | 0.08 | -0.04 | -0.00 | 0.07 | -0.04 | -0.05 | 1.00 | **0.72** | -0.09 |
| hard_hit_rate | 0.09 | -0.03 | -0.09 | 0.01 | 0.01 | -0.01 | -0.08 | **0.72** | 1.00 | 0.02 |
| ground_ball_rate | 0.14 | -0.25 | -0.01 | -0.04 | -0.07 | -0.04 | 0.03 | -0.09 | 0.02 | 1.00 |

**One clear redundancy**: `avg_launch_speed` and `hard_hit_rate`, r=0.72. Expected — `hard_hit_rate` is defined as the share of batted balls exceeding a fixed velocity threshold, so it's mechanically a (nonlinear) transform of the same underlying quantity `avg_launch_speed` measures directly. This is the only pair in the matrix exceeding |r|=0.45.

**Everything else is weakly-to-moderately correlated**, not redundant by any reasonable threshold:
- `velocity` vs. `pitch_entropy`: -0.44 — the largest non-trivial correlation outside the launch-speed/hard-hit pair. Harder-throwing pitchers show somewhat lower pitch-mix diversity (rely more on their primary pitch) — a real relationship, not redundancy (entropy and velocity measure different things; one doesn't mechanically determine the other).
- `spin_rate` vs. `pitch_entropy`: -0.33 — similar pattern.
- `velocity` vs. `movement_pfx_z`: 0.33; `velocity` vs. `spin_rate`: 0.27 — modest positive correlation among the three physical dimensions, consistent with them being related but distinct.
- `whiff_rate` vs. `zone_rate`: -0.28 — pitchers who locate in the zone less often show somewhat higher whiff rates, plausible (more edge/chase pitches draw more misses) but far from redundant.

### Partial correlations (controlling for a plausible confound)

| Pair | Controlling for | Partial r |
|---|---|---|
| Velocity vs. whiff rate | Movement, spin | 0.1556 |
| Whiff rate vs. avg. launch speed | Velocity, movement, spin | -0.0639 |
| Zone rate vs. chase rate | Velocity | -0.0248 |
| Spin rate vs. movement | Velocity | -0.1620 |

Velocity retains a real, independent relationship with whiff rate even after controlling for movement and spin (partial r=0.156, close to its raw pairwise r=0.20 — controlling barely changes it, meaning movement/spin aren't absorbing velocity's whiff-rate relationship). Whiff rate's relationship with contact quality (avg. launch speed) is weak and slightly negative even before controlling for anything, and controlling for the physical families doesn't change that picture — consistent with the incremental-information finding that nothing tested here explains contact quality well.

## Inference

Redundancy in this feature set is the exception, not the rule. Of 10 families' pairwise combinations (45 pairs), exactly one shows a correlation strong enough to call genuinely redundant. This directly supports the charter's preference for "a smaller architecture with independent information sources" — but the evidence says that smaller architecture should merge `avg_launch_speed`/`hard_hit_rate` specifically, not consolidate broadly across families.

## Speculation

The velocity/pitch-entropy negative correlation may reflect a real pitching-development pattern (max-effort velocity pitchers investing less in secondary-pitch development) rather than a measurement artifact — plausible but untested as a causal claim here.

## Future work

Test redundancy within the outcome-only (ALL_LEVELS) metric set (`whiff_rate_all_levels`, `swing_rate_all_levels`, `called_strike_rate` from Phase 1B) using the same method — not done this phase since the incremental chains already showed that population has little structure to begin with.
