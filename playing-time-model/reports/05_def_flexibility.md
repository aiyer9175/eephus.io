# Module 5 — Defensive Flexibility+ (Rung D ablation)

## Pooled holdout (targets 2023-2025)
               model     R2  RMSE   MAE  Spearman
 B minus flexibility 0.5888 148.9 116.9    0.7635
B (with flexibility) 0.5897 148.7 116.9    0.7686

## Segments most likely to need flexibility
- multi-pos (n_positions>=2) (n=821): MAE 128.5 -> 128.8  R2 0.4752 -> 0.475
- single-pos (n=1169): MAE 108.7 -> 108.5  R2 0.6538 -> 0.6554
- premium (C/SS/CF) (n=935): MAE 121.4 -> 122.2  R2 0.5176 -> 0.5222
- DH-heavy (dh_share>.3) (n=232): MAE 122.4 -> 120.6  R2 0.5759 -> 0.5798
- age<=25 (n=599): MAE 142.3 -> 143.9  R2 0.4188 -> 0.4095
