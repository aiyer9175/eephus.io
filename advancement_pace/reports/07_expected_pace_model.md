# 07 — Expected-Advancement Baseline

**Adopted: joint fixed-effects least squares** (`peer_baseline.py`):

```
area_pace ~ one dummy per (starting_level × experience_year) cell        [~60 cells]
          + entry-age bucket + era + position group + entry pathway      [additive]
```

The baseline is used ONLY for peer adjustment. Its target is the player's observed
historical pace; it never sees or predicts WAR, FV, reach, readiness, or any outcome.

## Two rejected constructions (kept for the record)
1. **Pure EB cell hierarchy** (6 nested levels, k=25): thin deepest cells shrink away
   whichever adjustment sits deepest — flattening position reopened a 2.2-point era
   drift (whack-a-mole).
2. **Sequential two-stage** (cells, then additive OLS on residual): pathway/age
   correlate with starting level, so globally-applied stage-2 coefficients broke the
   start-level margin (A-starters 96.3, AAA-starters 107.7).

Joint estimation fixes both: OLS residuals are orthogonal to every included regressor,
so **all margins are flat simultaneously** (each within ±0.4 of 100; experience-year
means within ±0.11).

## Interpretability check — expected ladder height by start × active seasons

| start | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Rk | 1.01 | 1.17 | 1.40 | 1.71 | 2.07 | 2.36 |
| A  | 2.02 | 2.44 | 2.87 | 3.19 | 3.42 | 3.60 |
| A+ | 2.94 | 3.23 | 3.56 | 3.77 | 3.91 | 3.96 |
| AA | 3.91 | 4.06 | 4.18 | 4.25 | 4.45 | 4.42 |
| AAA| 4.99 | 4.88 | 4.88 | 4.89 | 4.91 | 4.92 |

Monotone in experience, sensible spacing, no era pathology. Additive coefficients
(rung units): entry 23+ +0.244, 21–22 +0.194, ≤17 −0.058; era 2017–19 +0.126;
MIF +0.094 / OF +0.055 / CIF +0.034 vs Catcher; intl_amateur −0.332,
undrafted_other −0.140, draft_hs −0.038 vs draft_college. All face-valid.

Residual scale for standardization: residual SD per experience year (pooled fallback
below n=50), so early-career and late-career scores are standardized against their own
dispersion. GAM/survival alternatives were unnecessary: the cell+additive fit already
delivers stable residuals, adequate cells, sensible age effects, era stability, and
interpretable expectations — the charter's "simplest approach that provides" test.
