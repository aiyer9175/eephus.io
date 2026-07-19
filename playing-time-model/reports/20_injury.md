# Module 20 — Injury Model Integration (leakage-clean)

- clean injury features (stint history through t): (3348, 6), targets 2016-2025
- DROPPED rate-table cols (p_any_il_next, mean_il_games_next): deterministic recode of
  career_il_stints AND fit on full window incl. test seasons -> the .716->.761 jump was leakage.

## Steamer-free preseason frame, common universe (n=1985, targets 2023-25)
                               model     R2  RMSE  MAE  Spearman
                 Steamer (reference) 0.6742 132.5 90.3    0.8478
                    BASE (no injury) 0.6871 129.8 99.7    0.8458
BASE + INJ (clean)  <-- new champion 0.7155 123.8 93.6    0.8620
           blend (BASE+INJ, Steamer) 0.7342 119.7 87.0    0.8699

## Per target year (BASE+INJ clean)
  2023: {'model': 'x', 'R2': 0.7151, 'RMSE': 123.7, 'MAE': 92.0, 'Spearman': 0.8552}
  2024: {'model': 'x', 'R2': 0.7162, 'RMSE': 122.6, 'MAE': 93.3, 'Spearman': 0.8614}
  2025: {'model': 'x', 'R2': 0.7169, 'RMSE': 124.7, 'MAE': 95.0, 'Spearman': 0.8689}

## Segments (MAE: steamer | BASE | BASE+INJ clean)
- on_il_at_od=1 (n=73): MAE 99.6 | 117.6 | 108.8   rho 0.7277 | 0.555 | 0.635
- career_il_stints>=3 (n=414): MAE 112.8 | 116.6 | 108.2   rho 0.637 | 0.6424 | 0.6408
- il_days_t>=30 (n=239): MAE 127.3 | 125.2 | 111.2   rho 0.4755 | 0.5209 | 0.5057
- age>=32 (n=321): MAE 79.6 | 79.7 | 68.9   rho 0.8694 | 0.8812 | 0.9052
- no IL history (n=1178): MAE 77.0 | 89.3 | 84.5   rho 0.7738 | 0.7869 | 0.7947
