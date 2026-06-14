# Module 18 — Engine-Talent Backfill (walk-forward backbone)

- building engine panel (features through season t only)...
- engine_talent: (20606, 12), target years 2004-2026
- engine coverage on pairs (2004+ targets): 100.0%

## Steamer-free preseason frame (test n=1990, targets 2023-25)
                   model     R2  RMSE  MAE  Spearman
    BASE trailing talent 0.6879 129.7 99.6    0.8463
+ENG (trailing + engine) 0.6863 130.0 99.1    0.8465
      SWAP (engine only) 0.6838 130.5 99.7    0.8454

## Segments (MAE: BASE | +ENG | SWAP)
- age<=25 (n=599): MAE 125.4 | 126.2 | 125.9   rho 0.7611 | 0.7556 | 0.7634
- pa_t<200 (n=911): MAE 77.4 | 76.0 | 75.9   rho 0.7421 | 0.7446 | 0.7483
- pa_t>=400 (n=604): MAE 119.5 | 119.9 | 121.8   rho 0.6649 | 0.6619 | 0.6513
- rookie-ish (n=617): MAE 98.2 | 97.2 | 97.3   rho 0.8012 | 0.8 | 0.8031
