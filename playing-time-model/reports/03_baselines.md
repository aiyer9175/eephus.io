# Module 3 — Validation Ladder: Rungs A0 / A / B

- prediction pairs: 14584 (feature years 2000-2024, targets exclude 2020/2026)
- train pairs: 12594, test pairs: 1990 (targets 2023-2025)

## Pooled holdout (targets 2023-2025)
                model     R2  RMSE   MAE  Spearman
A0 persistence (pa_t) 0.4569 171.1 125.8    0.6958
 A  usage history GBM 0.5738 151.6 120.5    0.7492
      B  + talent GBM 0.5897 148.7 116.9    0.7686

## By target year (Model B)
{'model': 'B @ 2023', 'R2': np.float64(0.5825), 'RMSE': 149.7, 'MAE': 116.6, 'Spearman': 0.7566}
{'model': 'B @ 2024', 'R2': np.float64(0.5754), 'RMSE': 149.9, 'MAE': 118.7, 'Spearman': 0.7647}
{'model': 'B @ 2025', 'R2': np.float64(0.6101), 'RMSE': 146.3, 'MAE': 115.4, 'Spearman': 0.7832}

## By segment (Model B, pooled)
{'model': 'B age<=25 (n=599)', 'R2': np.float64(0.4095), 'RMSE': 177.2, 'MAE': 143.9, 'Spearman': 0.6511}
{'model': 'B age 26-31 (n=1066)', 'R2': np.float64(0.6613), 'RMSE': 136.2, 'MAE': 106.6, 'Spearman': 0.8003}
{'model': 'B age>=32 (n=325)', 'R2': np.float64(0.6434), 'RMSE': 129.1, 'MAE': 101.1, 'Spearman': 0.78}
{'model': 'B pa_t<200 (n=911)', 'R2': np.float64(0.2678), 'RMSE': 132.3, 'MAE': 96.7, 'Spearman': 0.5533}
{'model': 'B pa_t>=400 (n=604)', 'R2': np.float64(0.3264), 'RMSE': 155.1, 'MAE': 128.6, 'Spearman': 0.6063}
