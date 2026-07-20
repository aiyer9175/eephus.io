# Variance Decomposition — Phase 1B

Deliverable 5. Method-of-moments one-way and nested random-effects ANOVA (`scripts/phase1b/variance_decomposition.py`; no `statsmodels` dependency — not installed in this environment, and unneeded for a "where does variance live" decomposition rather than a precision estimate). Full numbers: `VARIANCE_STATS.json`.

## Observed evidence

### By-pitcher variance share (ICC), physical vs. outcome metrics

| Metric family | AAA between-pitcher ICC | Low-A (tracked) between-pitcher ICC |
|---|---|---|
| Velocity | 24.3% | 27.4% |
| Spin rate | 27.1% | 31.3% |
| Movement (pfxX) | 26.6% | 34.8% |
| Movement (pfxZ) | 12.3% | 11.7% |
| Whiff rate | 1.3% | 1.5% |
| Called-strike rate | 0.0% | 0.2% |
| Swing rate | 0.4% | 0.6% |
| In-play rate | 0.2% | 0.3% |
| Foul rate | 0.2% | 0.2% |
| Zone rate | 0.2% | 0.6% |
| Chase rate | 0.7% | 0.8% |

**A single-pitch-level ICC of ~1% for whiff rate does not contradict the ~0.33-0.51 split-half reliability reported elsewhere.** ICC answers "how much does knowing the pitcher help predict *this one pitch's* outcome" — properly small, since a single pitch's outcome is dominated by batter/count/location noise. Split-half reliability answers "how much does a pitcher's rate *over many pitches* predict their rate over many *other* pitches" — a different, aggregate-level question where the same per-pitch noise partially cancels out (this is exactly the Spearman-Brown principle the reliability script applies). Both numbers are correct simultaneously; they're different lenses required by the charter's own five-question structure (Question 1 vs. Questions 3-5).

### By-venue variance share (ICC), ALL_LEVELS metrics, every level

Between-venue ICC ranges 0.01–0.3% for whiff/called-strike/swing/in-play/foul rate, at every level including AAA (30 venues) and the untracked levels (30-31 venues each). No meaningful venue-level signal was detected for any outcome metric at any level in this pilot.

### Nested pitcher × pitch-family decomposition (tracked levels only)

| Metric | Level | Between-pitcher var | Family-within-pitcher var | Residual (pitch-to-pitch) var |
|---|---|---|---|---|
| Velocity (mph²) | AAA | 8.35 | 35.01 | 4.25 |
| Velocity (mph²) | Low-A | 9.24 | 32.46 | 4.69 |
| Spin rate (rpm²) | AAA | 35,422 | 118,647 | 21,228 |
| Spin rate (rpm²) | Low-A | 43,887 | 116,639 | 24,607 |
| pfxX | AAA | 9.09 | 31.79 | 5.70 |
| pfxX | Low-A | 11.50 | 26.49 | 5.59 |
| pfxZ | AAA | 2.67 | 22.90 | 4.91 |
| pfxZ | Low-A | 2.71 | 24.75 | 5.37 |
| Zone rate | AAA | 0.0006 | 0.0064 | 0.2443 |
| Zone rate | Low-A | 0.0014 | 0.0052 | 0.2453 |
| Chase rate | AAA | 0.0014 | 0.0043 | 0.2003 |
| Chase rate | Low-A | 0.0016 | 0.0033 | 0.1859 |

For velocity/spin/movement, **which pitch type was thrown explains more variance than who threw it**, which in turn explains more than pitch-to-pitch residual noise — the expected, physically sensible ordering (a pitcher's fastball-vs-offspeed velocity gap is bigger than the person-to-person gap within a single pitch type). For zone rate and chase rate, **residual pitch-to-pitch noise dominates overwhelmingly** (>95% of total variance in both cases, at both tracked levels) — neither the pitcher nor the pitch family explains much of where a given pitch actually lands relative to the zone.

## Inference

Two structurally different variance regimes exist in this data:

1. **Physical fields**: variance is meaningfully partitioned across pitcher and pitch-family, with modest residual — consistent with these being real, structured, partially-controllable pitcher and pitch-design properties.
2. **Location/chase fields**: variance is almost entirely residual — consistent with location outcomes being dominated by pitch-to-pitch execution noise (or measurement noise) that neither pitcher identity nor pitch-family explains at this sample size.

Outcome-result fields (whiff/called-strike/swing/in-play/foul) sit close to the location/chase regime at the single-pitch grain, but unlike zone/chase rate, several of them (whiff rate especially) show real season-aggregate reliability — meaning their "signal" is a weak-per-pitch, additive-over-many-pitches phenomenon, not something a per-pitch variance decomposition alone reveals.

## Speculation

The zone-rate/chase-rate residual dominance might shrink with either (a) more pitches per pitcher (per `IDENTIFIABILITY_REPORT.md`'s stabilization-curve finding that these metrics were still climbing at the largest tested thresholds), or (b) a genuinely different construct than "does the pitch land in the zone" — e.g. distance-to-intended-target, which this data source can't compute without target information.

## Future work

A true mixed-effects model (with `statsmodels`, `lme4`-equivalent, or a Bayesian hierarchical model) would provide confidence intervals around these point estimates and handle the unbalanced nesting more precisely than this pilot's average-cell-size approximation (documented in `scripts/phase1b/variance_decomposition.py`'s docstring). Not attempted this phase, consistent with the charter's preference for descriptive/variance work over precision optimization at this stage.
