# Expansion E21 — FINAL MODEL vs Steamer + ZiPS

- coverage: ours projects 100% of 4444 players; Steamer 97%, ZiPS 93%

## FULL POPULATION (common universe n=4089)
                    system    n      R2   MAE  RMSE  Spearman
Ours (final, Steamer-free) 4089  0.7880  56.6  94.6    0.8446
                   Steamer 4089  0.7679  51.9  99.0    0.8446
                      ZiPS 4089 -1.5380 292.0 327.2    0.4868
    Blend (ours + Steamer) 4089  0.8063  51.5  90.4    0.8498

## Incumbents (common universe n=1980)
                    system    n      R2   MAE  RMSE  Spearman
Ours (final, Steamer-free) 1980  0.7164  93.6 123.6    0.8623
                   Steamer 1980  0.6741  90.3 132.5    0.8481
                      ZiPS 1980 -0.2970 218.4 264.4    0.5880
    Blend (ours + Steamer) 1980  0.7341  87.1 119.7    0.8702

## Prospects (common universe n=2109)
                    system    n       R2   MAE  RMSE  Spearman
Ours (final, Steamer-free) 2109   0.3495  21.9  54.7    0.4618
                   Steamer 2109   0.4556  15.7  50.0    0.4138
                      ZiPS 2109 -29.8999 361.1 376.8    0.3183
    Blend (ours + Steamer) 2109   0.4803  18.0  48.9    0.4664

## Notes
- Targets 2023-2025 pooled; realized = actual MLB PA (0 if no MLB time).
- Ours uses NO FanGraphs inputs; blend adds Steamer as a partner.
- ZiPS PA is a rate-system allocation, not a playing-time model — its low
  R2 (esp. on prospects) reflects that, and validates the harness.
