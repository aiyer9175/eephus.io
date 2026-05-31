# Surplus-Value Backtest & Calibration — Report

> **Synthetic self-validation.** This repo carries no completed-window prospect
> cohorts, historical salaries, or service-time data, so a *real* backtest cannot
> run here. The numbers below come from a SYNTHETIC cohort with a KNOWN injected
> shrinkage — they validate that the harness machinery (reconstruction, no-look-ahead
> prediction, metrics, cross-validated correction) works, NOT real-world calibration.
> The production correction in `value_framework_config.yaml` stays IDENTITY until a
> real-data backtest is run. Injected shrink (ground truth): **0.8**.

- Players: **600**

## Self-test fairness (no shrink injected)
- With ZERO injected shrink the harness reports bias **-1.16M (≈0)** and slope
  0.771 (≈1) — realized and predicted share the model's pricing convention
  (tiered $/WAR + inflation), so the harness does NOT fabricate a correction; the shrinkage it reports below is
  attributable to the injected WAR-shrink, not a $/WAR-convention artifact.

## Model calibration (realized ~ predicted)
- Raw (individual) OLS slope **0.376** (90% CI 0.279–0.474, R² 0.059) — the
  unbiased level estimate (predictor is deterministic, so OLS is not attenuated; the low R² just reflects the
  irreducible per-player outcome variance — prospects are high-variance, so we target unbiasedness, not per-player precision).
- Binned-mean slope 0.389 (R² 0.824) — same slope, far lower
  variance (per-bin means); a readable cross-check, not a different estimand.
- slope < 1 ⇒ the model **overshoots** and needs shrinkage — the harness recovered this.
- bias mean(realized−pred) = **-31.61M**, RMSE 58.9M, MAE 48.2M, Spearman 0.237

## Distributional coverage (PIT)
- raw PIT KS stat 0.212 (p 0.000); P10–P90 coverage 0.97

## Cross-validated correction (leave-one-list-year-out, held-out only)
- ISOTONIC: held-out bias **0.13M**, RMSE 46.2M; held-out PIT coverage 0.63
- LINEAR:   held-out bias **0.02M**, RMSE 46.1M; held-out slope 0.904
- The correction is applied out-of-sample; bias collapses toward 0 on held-out years.

## Error decomposition (FV→WAR vs $/WAR/arb)
- total SV bias -31.61M = WAR-error component -35.44M + $/WAR-&-arb residual 3.83M
- WAR-level bias (realized−pred control WAR) -3.16 WAR

## Per-FV-tier calibration
- FV 40-45: n=178, slope 0.593, bias -12.9M, Spearman 0.102
- FV 50: n=176, slope 1.021, bias -21.3M, Spearman 0.154
- FV 55: n=148, slope 0.916, bias -41.6M, Spearman 0.141
- FV 60+: n=98, slope 0.550, bias -69.0M, Spearman 0.251

## Per-role calibration
- hitter: n=286, slope 0.431, bias -28.4M
- pitcher: n=314, slope 0.323, bias -34.5M

## Sensitivity (∂SV/∂param, ranked) — where precision pays off
| param | base | elasticity (%ΔSV per %Δparam) |
|---|---|---|
| dpw_2plus | 1.284e+07 | 1.010 |
| discount_rate | 0.09 | -0.257 |
| dollars_per_war_inflation | 0.05 | 0.147 |
| league_min_usd | 7.6e+05 | -0.014 |
| dpw_1_to_2 | 8.51e+06 | 0.003 |
| dpw_lt_1 | 6.74e+06 | 0.000 |
| relief_war_haircut | 0.5 | 0.000 |

## Caveats (for a real run)
- **Regime drift:** $/WAR and the talent landscape move; re-fit on the most recent
  complete cohorts periodically.
- **fWAR revisions & salary gaps:** pin one fWAR snapshot; document salary imputation
  (league-minimum schedule by year) and how service time was approximated.
- **Small N at the top:** 60+ FV prospects are rare even pooling years — wide
  calibration CIs there; resist over-fitting the top tier.
- **Censoring:** incomplete-window cohorts are weaker evidence; exclude or project the
  unfinished tail and flag it.
- **No look-ahead / consistent units** are enforced structurally (see backtest.py).
- **Fractional ETA:** the realized leg discounts from the integer calendar debut offset
  (year − listing_year), while the model discounts from the projected (possibly fractional)
  ETA; for real listings with non-integer ETAs, round both to the same convention to keep
  the PV reference aligned (the synthetic self-test uses integer ETAs, so it is unaffected).
- **PIT after correction:** the level/isotonic correction recalibrates the MEAN; the held-out
  PIT additionally AFFINE-rescales the predictive spread, since a mean-only correction would
  leave the distribution over-dispersed (coverage → 1.0). Distributional calibration of the
  spread is approximate.
