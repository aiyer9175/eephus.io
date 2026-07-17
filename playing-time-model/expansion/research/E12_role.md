# Expansion E12 — Role: full-time + bench share

## Full-time role probability  (P(>=100 starts next year))
- base rate: train 0.303, test 0.286
- model:  AUC 0.8809  Brier 0.1253
- naive (was FT this yr): AUC 0.7501  Brier 0.2075

## Bench share  ((games-starts)/games, players w/ >=20 games next yr)
- year-over-year reliability (this yr vs next): r = 0.682 (n=9323)
- model (champion feats): R2 0.397  MAE 0.090  rho 0.717
- naive (this-yr bench share): R2 nan  MAE nan  rho nan

## Is bench share just inverse PA? (new-info check)
- corr(projected PA, actual bench_share_next) = -0.658 (high |corr| => largely redundant with PA)

## VERDICT
- Full-time role probability: SHIPS — model AUC .881 vs naive (was-FT) .750,
  well-calibrated probabilistic role output the framework asked for.
- Bench share: stable (yoy r .68) and projectable (R2 .397) but ~43%
  redundant with PA (corr -.66) — keep as derived output, not a priority
  feature. Genuinely new role info lives in PLATOON (E13), not bench share.
