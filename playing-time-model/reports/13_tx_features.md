# Module 13b — Transaction / Offseason Features

- tx features: (602127, 13), target years 2004-2026
- pairs with tx data: 87% (players w/o any career transaction before Oct -> 0)

## OCT frame (full test universe)
          model     R2  RMSE   MAE  Spearman
       champion 0.5992 147.0 115.1    0.7756
F-oct  champ+tx 0.6042 146.1 114.1    0.7811

## PRESEASON frame (common universe n=1985)
                    model     R2  RMSE  MAE  Spearman
        Steamer preseason 0.6742 132.5 90.3    0.8478
                    stack 0.6949 128.2 98.1    0.8444
      F-pre  stack+tx+off 0.6962 127.9 97.6    0.8465
blend (F-pre + Steamer)/2 0.7042 126.2 91.3    0.8539

## Segments (MAE: steamer | stack | F-pre)
- age<=25 (n=599): MAE 109.5 | 117.6 | 117.6   rho 0.7848 | 0.7813 | 0.7813
- pa_t<200 (n=909): MAE 68.1 | 77.4 | 76.7   rho 0.7228 | 0.7091 | 0.7158
- shuttle=1 (n=971): MAE 78.5 | 88.7 | 87.8   rho 0.7742 | 0.7537 | 0.7615
- optioned in t (n_opt>0) (n=680): MAE 83.4 | 91.5 | 91.5   rho 0.758 | 0.7406 | 0.7404
- off_traded (n=129): MAE 98.3 | 104.4 | 103.9   rho 0.7989 | 0.7896 | 0.787
- off_des_out_clw (n=217): MAE 40.4 | 61.2 | 59.2   rho 0.5679 | 0.4206 | 0.431
