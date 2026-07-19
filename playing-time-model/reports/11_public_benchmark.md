# Module 11 — Public Benchmark (Steamer / ZiPS preseason PA)

- test universe: 1990 player-seasons (targets 2023-2025)
- Steamer coverage of universe: 99.7%, ZiPS: 99.7%

## Common universe (champion ∩ Steamer ∩ ZiPS) (n=1980)
            model      R2  RMSE   MAE  Spearman
Champion (E2 GBM)  0.5987 147.1 115.2    0.7761
Steamer preseason  0.6741 132.5  90.3    0.8481
   ZiPS preseason -0.2970 264.4 218.4    0.5880
 Persistence pa_t  0.4592 170.7 125.6    0.6983

## Champion vs Steamer (full Steamer overlap) (n=1985)
            model     R2  RMSE   MAE  Spearman
Champion (E2 GBM) 0.5991 147.0 115.1    0.7763
Steamer preseason 0.6742 132.5  90.3    0.8478
 Persistence pa_t 0.4596 170.6 125.5    0.6981

## Segments (common universe)
- age<=25 (n=599): MAE champ 141.6 | steamer 109.5 | zips 234.6   rho 0.6659 | 0.7848 | 0.435
- pa_t<200 (n=904): MAE champ 94.2 | steamer 68.2 | zips 292.5   rho 0.5849 | 0.7257 | 0.3257
- pa_t>=400 (n=603): MAE champ 128.2 | steamer 104.6 | zips 127.4   rho 0.5995 | 0.6735 | 0.5989
- by year 2023 (n=681): MAE champ 113.9 | steamer 86.7 | zips 218.0   rho 0.7679 | 0.8627 | 0.6086
- by year 2024 (n=652): MAE champ 117.2 | steamer 94.0 | zips 215.5   rho 0.771 | 0.8375 | 0.5747
- by year 2025 (n=647): MAE champ 114.6 | steamer 90.4 | zips 221.9   rho 0.787 | 0.8574 | 0.5752

## Caveats
- Public systems embed winter injury knowledge; this model excludes medical info by design (separate model planned). Advantage: them.
- FG Depth Charts (curated PA, strongest public comp) archive is member-only; not compared. Steamer/ZiPS PA are model-allocated.
- Incumbent universe only (MLB PA in year t); debutants excluded.
