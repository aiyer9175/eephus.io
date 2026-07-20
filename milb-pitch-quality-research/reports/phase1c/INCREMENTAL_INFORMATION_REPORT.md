# Incremental Information Report — Phase 1C

Deliverable 2. Block-wise R² increments (numpy OLS least-squares, no `statsmodels`/`sklearn` — consistent with Phase 1B's no-heavy-dependency approach) quantifying how much *additional* variance each feature family explains in a chosen downstream metric, added in a scientifically motivated order. This is explicitly **not** a predictive model being tuned or evaluated — R² here is a variance-accounting tool, per the charter's instruction to optimize for scientific understanding, not prediction. Full numbers: `INCREMENTAL_STATS.json`. Population: 600 pitchers with ≥100 tracked pitches (577 also clear ≥15 batted balls for `hitData`-dependent chains); AAA + tracked Low-A venues.

## Observed evidence

### Chain 1: Physical families → Whiff rate

| Family added | Cumulative R² | Incremental R² |
|---|---|---|
| + Velocity | 0.0395 | 0.0395 |
| + Movement | 0.0598 | 0.0203 |
| + Spin | 0.0664 | 0.0066 |
| + Pitch mix/diversity | 0.1372 | **0.0708** |
| + Location (zone rate) | 0.2022 | **0.0650** |
| + Swing decision (chase rate) | 0.2276 | 0.0254 |

Total: all six families together explain 22.8% of cross-pitcher variance in whiff rate. **Pitch mix/diversity and location contribute the two largest single increments** — larger than velocity, movement, or spin individually. ~77% of whiff-rate variance remains unexplained by every family tested.

### Chain 2: Physical families + whiff → Weak contact (avg. exit velocity allowed)

| Family added | Cumulative R² | Incremental R² |
|---|---|---|
| + Velocity | 0.0039 | 0.0039 |
| + Movement | 0.0091 | 0.0052 |
| + Spin | 0.0117 | 0.0026 |
| + Location | 0.0155 | 0.0038 |
| + Whiff ability | 0.0186 | 0.0031 |

Total: **1.9%.** Essentially none of a pitcher's measurable physical stuff or whiff ability predicts the average exit velocity they allow, in this sample.

### Chain 3: Physical families + whiff → Damage suppression (hard-hit rate)

| Family added | Cumulative R² | Incremental R² |
|---|---|---|
| + Velocity | 0.0084 | 0.0084 |
| + Movement | 0.0125 | 0.0040 |
| + Spin | 0.0293 | **0.0169** |
| + Location | 0.0304 | 0.0011 |
| + Whiff ability | 0.0368 | 0.0064 |

Total: **3.7%.** Weak but non-trivial — spin contributes the largest single increment among the physical families here, unlike in the weak-contact chain above.

### Chain 4: Physical families → Ground-ball tendency

| Family added | Cumulative R² | Incremental R² |
|---|---|---|
| + Velocity | 0.0200 | 0.0200 |
| + Movement | 0.1228 | **0.1029** |
| + Spin | 0.1341 | 0.0112 |

Total: **13.4%** — the strongest physical-to-outcome relationship found this phase, driven almost entirely by movement's large increment (10.3 points), consistent with induced vertical break being the direct mechanical driver of ground-ball tendency.

### Chain 5: Swing decision → Whiff rate, all-levels (outcome-only) population

| Family added | Cumulative R² | Incremental R² |
|---|---|---|
| + Swing rate (all-levels) | 0.0158 | 0.0158 |

Total: **1.6%.** The only chain available without tracking data explains almost nothing — a direct, quantified illustration of Phase 1B's architectural finding that outcome-only levels have far less recoverable structure.

## Inference

Four distinct patterns, not one:
1. **Whiff rate** is meaningfully explained by the combination of physical and mix/location families (22.8%) — no single family dominates; pitch mix and location matter as much as or more than raw stuff.
2. **Weak contact / damage suppression** are barely explained by anything measured here (1.9% and 3.7%) — this is the clearest incremental-information finding of the phase: contact quality allowed looks close to independent of the physical/whiff features available in this dataset.
3. **Ground-ball tendency** is meaningfully explained by movement specifically (13.4% total, 10.3 points from movement alone) — a real, mechanically sensible relationship, unlike the near-null weak-contact/damage chains.
4. **Outcome-only information is thin**, quantitatively confirming Phase 1B's qualitative finding — 1.6% total from the one chain available without tracking.

## Speculation

The near-null weak-contact/damage-suppression chains could mean either (a) genuine independence — contact quality is driven by factors this pilot doesn't measure (defense positioning, park, batted-ball luck), or (b) the `avg_launch_speed`/`hard_hit_rate` metrics are simply noisier at this sample size than the physical/whiff metrics (their reliability wasn't separately tested this phase). This report cannot distinguish those explanations.

## Future work

Retest the weak-contact/damage-suppression chains after a dedicated reliability check on those two metrics specifically (not run in Phase 1B, which didn't compute `hitData` fields at all). Extend Chain 1 with a sequencing family once within-PA pitch order is extracted (flagged in `FEATURE_FAMILY_INVENTORY.md`).
