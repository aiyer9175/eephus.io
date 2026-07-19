# Module 12 — Steamer Stack

- Steamer feature coverage by era: pre-2010 targets 0%, 2010+ targets 85%

## Head-to-head, common universe (n=1985, targets 2023-25)
                        model     R2  RMSE   MAE  Spearman
            Steamer preseason 0.6742 132.5  90.3    0.8478
          Champion (Oct info) 0.5991 147.0 115.1    0.7763
STACK (champ + Steamer prior) 0.6949 128.2  98.1    0.8444
    50/50 stack+Steamer blend 0.7026 126.6  91.7    0.8518

## Segments (MAE: steamer | stack)
- age<=25 (n=599): MAE 109.5 | 117.6   rho 0.7848 | 0.7813
- pa_t<200 (n=909): MAE 68.1 | 77.4   rho 0.7228 | 0.7091
- pa_t>=400 (n=603): MAE 104.6 | 114.4   rho 0.6735 | 0.6628
- shuttle=1 (n=971): MAE 78.5 | 88.7   rho 0.7742 | 0.7537
- 2023 (n=686): MAE 86.5 | 94.7   rho 0.8618 | 0.8476
- 2024 (n=652): MAE 94.0 | 98.5   rho 0.8375 | 0.8389
- 2025 (n=647): MAE 90.4 | 101.3   rho 0.8574 | 0.8455
