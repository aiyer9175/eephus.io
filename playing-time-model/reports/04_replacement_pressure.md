# Module 4 — Replacement Pressure+ (Rung C)

- coverage of new features on pairs: {'share_pos_starts': 0.967, 'comp_best_woba': 0.911, 'comp_n': 0.967, 'comp_young': 0.967, 'team_pos_hhi': 0.967}
  (missing = player had 0 starts at any position — pure bench/PH rows)
- train 12594 / test 1990

## Pooled holdout (targets 2023-2025)
           model     R2  RMSE   MAE  Spearman
  B  (benchmark) 0.5897 148.7 116.9    0.7686
C  + replacement 0.5894 148.8 116.5    0.7681

## Segments (Rung C)
{'model': 'C age<=25 (n=599)', 'R2': 0.4062, 'RMSE': 177.7, 'MAE': 143.5, 'Spearman': 0.6484}
{'model': 'C age 26-31 (n=1066)', 'R2': 0.6624, 'RMSE': 135.9, 'MAE': 106.0, 'Spearman': 0.8011}
{'model': 'C age>=32 (n=325)', 'R2': 0.6434, 'RMSE': 129.1, 'MAE': 101.1, 'Spearman': 0.7824}
{'model': 'C pa_t<200 (n=911)', 'R2': 0.2609, 'RMSE': 132.9, 'MAE': 96.5, 'Spearman': 0.5518}
{'model': 'C pa_t>=400 (n=604)', 'R2': 0.3261, 'RMSE': 155.1, 'MAE': 128.3, 'Spearman': 0.6049}
