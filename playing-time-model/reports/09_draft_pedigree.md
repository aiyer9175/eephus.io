# Module 9 — Draft Pedigree (Rung E2)

- drafted share of pairs: 70.2% (0 = international signing)

## Pooled holdout (targets 2023-2025)
              model     R2  RMSE   MAE  Spearman
        F' champion 0.5952 147.7 115.7    0.7739
E2 + draft pedigree 0.5992 147.0 115.1    0.7756

## Segments
- age<=25 (n=599): MAE 142.6 -> 141.6, R2 0.4221 -> 0.4364, rho 0.661 -> 0.6659
- first_rounder (n=343): MAE 132.1 -> 129.7, R2 0.534 -> 0.5512, rho 0.7587 -> 0.761
- top10_pick (n=152): MAE 130.7 -> 125.6, R2 0.5604 -> 0.5907, rho 0.7873 -> 0.7898
- pa_t<200 (n=911): MAE 94.6 -> 94.0, R2 0.2906 -> 0.3097, rho 0.5777 -> 0.5839
- yrs_since_draft<=4 (n=218): MAE 152.6 -> 149.3, R2 0.297 -> 0.3494, rho 0.6466 -> 0.6384
