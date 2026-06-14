# Expansion E14 — In-Season Rest-of-Season PA Updating

- universe: 8649 player-cutoff rows; train 5379, test 3270 (cutoffs May31+Jun30 pooled)
- league fraction-elapsed: May31 ~0.36, Jun30 ~0.52

## Rest-of-season PA: in-season model vs stale-preseason baselines
                model     R2  MAE  RMSE    rho
B1 preseason-prorated 0.4261 80.4 102.0 0.6432
        B2 naive pace 0.5449 66.7  90.8 0.7385
   M  in-season model 0.5476 73.1  90.6 0.7266

## By cutoff (in-season model)
- May 31 (~1/3 in) (n=1572): model MAE 82.2 vs preseason-prorated MAE 91.1  (rho 0.722)
- Jun 30 (~1/2 in) (n=1698): model MAE 64.6 vs preseason-prorated MAE 70.5  (rho 0.719)

## Read
- B1 = the stale preseason projection prorated for time left (what you'd
  use without updating). If M beats B1, in-season updating adds value.
- gains should grow from May->Jun as more in-season info accrues.

## VERDICT
- IN-SEASON UPDATING IS HIGHLY VALUABLE: rest-of-season R2 .426 -> .548,
  MAE 80.4 -> ~67 vs the stale preseason projection. Confirmed at both
  cutoffs (May 31: model MAE 82.2 vs preseason 91.1; Jun 30: 64.6 vs 70.5).
- BUT naive pace (extrapolate current PA rate, league-elapsed-fraction) is a
  very strong baseline (R2 .545, MAE 66.7) and the GBM only TIES it (R2 .548,
  MAE 73.1 — worse on MAE, the recurring mean-vs-median skew). The value is
  the UPDATE, not model sophistication.
- DEPLOYABLE in-season ROS engine = pace-anchored, shrunk toward the preseason
  projection for small samples (May), trusting pace more by midseason. Stale
  preseason should NOT be used past ~May once PA-to-date exists.
- Next refinements (likely to finally beat pace): start-rate-to-date + current
  IL status as features (role/health context pace can't see); per-PA shrinkage
  weight; separate hitters who changed teams at the deadline.
