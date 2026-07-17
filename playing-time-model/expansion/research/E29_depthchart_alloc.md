# Expansion E29 — Depth-Chart Allocation: achievable vs ceiling

- test incumbents 1985; on OD depth chart 57%

## Overall (incumbents, test 2023-25)
                         model     R2   MAE  RMSE    rho
                      champion 0.7145  94.5 124.0 0.8615
       auto-alloc (model rank) 0.6711  97.1 133.1 0.8488
DEPTH-CHART alloc (achievable) 0.6261 101.3 141.9 0.8310
        blend champ+depthchart 0.7029  94.6 126.5 0.8566
        ORACLE alloc (ceiling) 0.8785  59.6  80.9 0.9221
           Steamer (yardstick) 0.6742  90.3 132.5 0.8478

## pred>=500 band — MAE
- champion           101.6
- auto               100.6
- depth-chart        119.3
- blend+depthchart   104.7
- ORACLE             52.6
- Steamer            83.6

## Ceiling capture (overall MAE): champion 94.5 -> oracle 59.6 (ceiling 34.9 PA). Best achievable (depth-chart) 94.6 = 0% of ceiling.
- decision: if achievable capture is large AND beats Steamer (90.3) -> build the curated layer; if ~0 -> OD role knowledge doesn't help, skip.

## VERDICT — the manual curated layer would NOT fill the gap

| allocation ranking | overall MAE | % of oracle ceiling captured |
|---|---|---|
| champion (no alloc) | 94.5 | — |
| auto (rank by model) | 97.1 | 0% (hurts) |
| **depth-chart (achievable OD roles)** | **101.3 / blend 94.6** | **0% (hurts/flat)** |
| ORACLE (realized usage rank) | **59.6** | 100% (ceiling = 34.9 PA) |
| Steamer | 90.3 | — |

THE FINDING: the oracle ceiling is huge (34.9 PA) BUT it is captured 0% by
Opening-Day role knowledge. The entire ceiling is the DIFFERENCE between
oracle (realized usage ranks) and depth-chart (OD slated roles) = mid-season
churn: who got hurt, who got called up and seized the job, who broke out or
busted. That is UNKNOWABLE at projection time by anyone — human curator or
model. OD role resolution (the only thing a manual layer adds) is worth ~0
because (a) we already capture OD roles via usage history + roster, and
(b) final usage diverges from OD roles via unpredictable in-season events.

=> DO NOT build the manual curated allocation layer. It would cost ongoing
human effort and capture ~0% of the gap. Steamer's residual regular-band edge
(83.6 vs 101.6) is NOT replicable OD role knowledge either — it's smooth
magnitude calibration + spring-injury info we exclude by design.

## Where the 34.9-PA ceiling ACTUALLY lives — and how to get it
It is IN-SEASON information. The only way to access realized-usage knowledge is
to OBSERVE it as the season unfolds. That is exactly the in-season ROS updater
(E14: rest-of-season R² .426 -> .548, MAE 80 -> 67). So the gap is filled
NOT by a preseason curated layer but by IN-SEASON UPDATING — which we already
built and validated. Preseason, the owned model is at its true ceiling.
