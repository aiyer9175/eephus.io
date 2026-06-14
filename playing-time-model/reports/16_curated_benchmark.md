# Module 16 — Curated Benchmark (target 2025: ATC + Depth Charts)

- FG-id bridge: 4955 ids
- DC Dec-2024 rows mlbam-linked: 97.7% of 664

- 2025 test universe: 649; coverage {'pa_steamer': '100%', 'pa_zips': '100%', 'pa_atc': '86%', 'pa_dc': '87%'}

## Five-system shootout, common universe (n=542)
              model      R2  RMSE   MAE  Spearman
    Ours (F-pre+OD)  0.6594 134.1 106.9    0.8252
Steamer (preseason)  0.6644 133.1 102.0    0.8195
   ZiPS (preseason) -0.1448 245.8 197.5    0.5675
ATC (Mar 7 capture)  0.5669 151.2 114.8    0.7712
DC (Dec 2 capture*)  0.3441 186.0 139.9    0.7217
 blend ours+Steamer  0.6821 129.5 101.6    0.8323
     blend ours+ATC  0.6639 133.2 104.7    0.8180

*DC capture is Dec 2, 2024 — pre-offseason-moves vintage; handicapped vs the others.

## Ours vs Steamer vs ATC (n=560, no DC/ZiPS constraint)
                 model     R2  RMSE   MAE  Spearman
                  Ours 0.6674 133.0 105.5    0.8317
               Steamer 0.6714 132.1 100.5    0.8253
                   ATC 0.5751 150.3 113.6    0.7757
        blend ours+ATC 0.6703 132.4 103.6    0.8235
blend ours+ATC+Steamer 0.6769 131.0 101.7    0.8279
