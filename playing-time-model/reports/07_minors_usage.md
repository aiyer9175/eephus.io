# Module 7 — Minors Usage / Shuttle (Rung F')

- pairs with any minors PA in feature year (2008+): 61.7%

## Pooled holdout (targets 2023-2025)
            model     R2  RMSE   MAE  Spearman
    B (benchmark) 0.5897 148.7 116.9    0.7686
F' + minors usage 0.5957 147.6 115.8    0.7747

## Segments
- pa_t<200 (n=911): MAE 96.7 -> 94.6, R2 0.2678 -> 0.2922, rho 0.5533 -> 0.5804
- age<=25 (n=599): MAE 143.9 -> 142.9, R2 0.4095 -> 0.4234, rho 0.6511 -> 0.663
- shuttle=1 (n=971): MAE 109.2 -> 107.4, R2 0.3712 -> 0.3879, rho 0.6235 -> 0.6431
- pa_t>=400 (n=604): MAE 128.6 -> 128.8, R2 0.3264 -> 0.3236, rho 0.6063 -> 0.6024
