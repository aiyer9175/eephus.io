# Module 21 — Injury Severity / Duration

- impact_windows player ids ∩ spine: 1453 (confirms MLBAM keying)
- walk-forward region tables built for target years 2010-2026
- OD IL designations: {2.0: 676, 3.0: 384, 1.0: 186} (1=D10,2=D15,3=D60)
- severity features: (1246, 4); region attributed to 976/1246 OD-injured

## Steamer-free preseason frame, common universe (n=1985)
                          model     R2  RMSE  MAE  Spearman
            Steamer (reference) 0.6742 132.5 90.3    0.8478
Module 20 champion (IL history) 0.7155 123.8 93.6    0.8620
21 + severity/duration  <-- new 0.7164 123.6 93.5    0.8622
           blend (21 + Steamer) 0.7341 119.7 87.1    0.8699

## The target segment — on IL at Opening Day
- on_il_at_od=1 (n=73): MAE steamer 99.6 | m20 108.8 | m21 100.8   rho 0.7277 | 0.635 | 0.6861
-   of which D60: n=13
-   of which D10/D15 (n=60): MAE steamer 107.5 | m20 111.8 | m21 108.3   rho 0.6733 | 0.6087 | 0.6288
- age>=32 (n=321): MAE steamer 79.6 | m20 68.9 | m21 69.0   rho 0.8694 | 0.9052 | 0.9072
- il_days_t>=30 (n=239): MAE steamer 127.3 | m20 111.2 | m21 109.5   rho 0.4755 | 0.5057 | 0.519
