# Module 6 — Prospect Pedigree+ (Rung E)

- pedigree rows: 3814 across target years 2022-2025
- test pairs with any pedigree: 12.5% (incumbent universe — most MLB regulars are post-prospect)

## Pooled holdout (targets 2023-2025)
        model     R2  RMSE   MAE  Spearman
B (benchmark) 0.5897 148.7 116.9    0.7686
 E + pedigree 0.5897 148.7 116.9    0.7686

## Where pedigree should matter
- age<=25 (n=599): MAE 143.9 -> 143.9, R2 0.4095 -> 0.4095, rho 0.6511 -> 0.6511
- rookie-ish (pa_l1 NaN/0) (n=617): MAE 114.8 -> 114.8, R2 0.4122 -> 0.4122, rho 0.6739 -> 0.6739
- had pedigree (n=248): MAE 153.0 -> 153.0, R2 0.2167 -> 0.2167, rho 0.5175 -> 0.5175
- top100 at cutoff (n=34): MAE 225.8 -> 225.8, R2 -0.7987 -> -0.7987, rho 0.1276 -> 0.1276
