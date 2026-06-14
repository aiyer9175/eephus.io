# Module 14b — Opening Day Roster Features

- od features: (10913, 6), years 2004-2026
- sanity: of pairs with on_active_od=1, next-year PA mean 396 vs not-on-OD 106

## PRESEASON frame, common universe (n=1985)
                      model     R2  RMSE  MAE  Spearman
          Steamer preseason 0.6742 132.5 90.3    0.8478
                F-pre (13b) 0.6962 127.9 97.6    0.8465
                 F-pre + OD 0.7153 123.8 93.4    0.8585
blend (F-pre+OD, Steamer)/2 0.7177 123.3 88.7    0.8613

## Segments (MAE: steamer | F-pre | F-pre+OD)
- off_des_out_clw>0 (n=217): MAE 40.4 | 59.2 | 55.6   rho 0.5679 | 0.431 | 0.4949
- pa_t<200 (n=909): MAE 68.1 | 76.7 | 72.6   rho 0.7228 | 0.7158 | 0.7459
- age<=25 (n=599): MAE 109.5 | 117.6 | 115.1   rho 0.7848 | 0.7813 | 0.7907
- not on OD active (n=878): MAE 61.0 | 72.1 | 64.8   rho 0.6056 | 0.6292 | 0.6126
- on OD active (n=1107): MAE 113.5 | 117.7 | 116.1   rho 0.7067 | 0.7125 | 0.7179
