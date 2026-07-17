# Module 17 — Steamer dependency ablation

Question (user): why feed Steamer as a feature when we have our own system?

Setup: preseason frame, targets 2023-25, common universe n=1,985.
"No-Steamer" = champion E2 + transaction features + OD roster features,
zero FanGraphs inputs of any kind.

| model | R2 | RMSE | MAE | Spearman |
|---|---|---|---|---|
| Steamer alone | .6742 | 132.5 | 90.3 | .8478 |
| OURS no-Steamer (champ+tx+OD) | .6871 | 129.8 | 99.7 | .8458 |
| OURS with Steamer feature | .7153 | 123.8 | 93.4 | .8585 |
| blend no-Steamer + Steamer | .7237 | 122.0 | 89.6 | .8626 |
| blend with-Steamer + Steamer | .7177 | 123.3 | 88.7 | .8613 |

Verdicts:
1. The independent model beats Steamer on R2/RMSE with no FG inputs;
   Steamer's residual MAE edge ~= winter injury/news info (excluded by design).
2. Steamer-as-feature helps the standalone (+.028 R2) — info aggregation.
3. BEST overall = blend(no-Steamer ours, Steamer): ensemble diversity —
   keeping Steamer OUT of the model decorrelates errors, so the blend
   gains more than the better-but-correlated stacked variant.

ARCHITECTURE DECISION: champion = Steamer-free model (full ownership,
no FG dependency). Steamer (or any public system) = optional blend
partner at deploy time. Next talent upgrade: backfill engine v2
historical projections to replace trailing-rate talent features.
