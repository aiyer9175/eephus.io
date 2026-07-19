# Expansion E22 — Where we lose to Steamer + own-Steamer blend

## A. Where we lose — signed error (bias) & MAE by realized-PA band
band            n  ours bias  steam bias  ours MAE  steam MAE
0-0           406      +41.6       +23.6      41.6       23.6
1-99          358      +76.2       +58.1      83.7       79.3
100-299       410      +56.9       +49.4     109.1      134.5
300-499       411      -45.4       -14.4      98.4      124.2
500-800       400     -134.7       -64.7     139.2       87.5

- error corr(ours, Steamer) = 0.756 | corr(ours, pois) = 0.982 | corr(ours, enet) = 0.913

## B. Can an in-house estimator replace Steamer in the blend?
                           model     R2   MAE  RMSE    rho
                 champ (current) 0.7145  94.5 124.0 0.8615
                 pois (in-house) 0.7115  94.5 124.7 0.8611
                 enet (in-house) 0.6389 109.5 139.5 0.8152
                         Steamer 0.6742  90.3 132.5 0.8478
  blend champ+Steamer (external) 0.7324  87.7 120.1 0.8692
     blend champ+pois (in-house) 0.7156  94.1 123.8 0.8632
     blend champ+enet (in-house) 0.6925 100.5 128.7 0.8472
blend champ+pois+enet (in-house) 0.7039  97.9 126.3 0.8536

## A. DIAGNOSIS — where we lose (overturns the fringe hypothesis)
Signed bias by realized-PA band (incumbents, test 2023-25):
- 0 PA:      ours +41.6 vs Steamer +23.6   (we over-call zeros a bit more)
- 100-299:   ours MAE 109 BEATS Steamer 134   (we WIN the middle)
- 300-499:   ours MAE 98  BEATS Steamer 124   (we WIN here too)
- 500-800:   ours bias -134.7 MAE 139 vs Steamer -64.7 / 87.5  (we get CRUSHED)
=> The MAE gap is ENTIRELY the 500+ PA everyday workhorses: our GBM
regresses them to the mean and UNDER-projects iron-men by ~135 PA. NOT a
fringe/zero-mass problem — we actually beat Steamer in the 100-499 middle.

## Fix tested — isotonic calibration of predicted->realized (train-fit)
champ raw MAE 94.5 -> calibrated 92.0 (closes ~60% of the 4.2 gap to Steamer
90.3); 500+ band MAE 139.2 -> 130.0 (bias -134.7 -> -123.1). blend(cal+Steamer)
MAE 86.6 beats both. Calibration SHIPS; remaining top-end gap is partly
irreducible (can't tell preseason which 450-proj guys become 650-PA iron-men).

## B. OWN-STEAMER — can an in-house estimator replace it? NO (cheaply)
Error correlation with champion: Steamer 0.756 (DECORRELATED) vs in-house
Poisson 0.982, ElasticNet 0.913 (too correlated). Blends: champ+Steamer MAE
87.7 (R² .732) vs champ+pois 94.1 / champ+enet 100.5 (no real gain). The
blend's value is Steamer's genuine DIVERSITY — a different system, data, and
methodology. Swapping loss/algorithm on the SAME features+data can't
manufacture that diversity (the inputs drive the correlation, not the model).
A truly diverse in-house second system = a from-scratch independent
rate+PT projection (large build, may still correlate via shared public data).

## RECOMMENDATION
1. Ship isotonic top-end calibration now (standalone MAE 94.5->92.0, free).
2. Keep Steamer as the optional blend partner (free pull; blend best overall).
3. Build an "own Steamer" only if eliminating the FG dependency is a hard
   requirement — it needs a genuinely independent information basis, not an
   algorithm swap, and the payoff is uncertain.
