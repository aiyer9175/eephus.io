# Expansion E26 — Depth-Chart Depth-Rank Feature Test

- test n=1990; on a depth chart: 57%; of those, starters: 64%

## Overall (incumbents, test 2023-25)
                model    n     R2  MAE    rho
             champion 1985 0.7145 94.5 0.8615
champion + depth-rank 1985 0.7145 94.5 0.8615
  Steamer (yardstick) 1985 0.6742 90.3 0.8478

## LOSS ZONE — does depth-rank close the gap toward Steamer? (MAE)
segment                         n   champ     +DC  Steamer
age<=23                       231   128.7   128.7    110.9
rookie <500 PA                747    93.4    93.4     84.1
proj-ish 100-500 (base)      1102   123.3   123.3    122.3
base pred 500+                243   101.6   101.6     83.6
on OD roster                 1107   119.7   119.7    113.5

## rho on loss zone (ranking)
- age<=23 (n=231): champ 0.749 | +DC 0.749 | Steamer 0.773
- rookie <500 PA (n=747): champ 0.768 | +DC 0.768 | Steamer 0.768
- proj-ish 100-500 (base) (n=1102): champ 0.598 | +DC 0.598 | Steamer 0.605
- base pred 500+ (n=243): champ 0.284 | +DC 0.284 | Steamer 0.350
- on OD roster (n=1107): champ 0.704 | +DC 0.704 | Steamer 0.707
