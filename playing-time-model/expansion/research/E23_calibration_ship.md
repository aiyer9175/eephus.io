# E23 — Isotonic calibration: tested properly, NOT shipped + where the gap really is

## Calibration does NOT survive a correct test
Shipped attempt = isotonic recalibration fit on OUT-OF-FOLD train predictions
(the correct way), applied per-slice to the full-population projection:

| full pop (n=4,309) | R² | MAE | RMSE | rho |
|---|---|---|---|---|
| Ours RAW | .791 | 54.4 | 92.5 | .838 |
| Ours CALIBRATED (OOF isotonic) | .789 | 54.5 | 92.9 | .838 |

WASH (marginally worse). The E22 "94.5→92.0 win" was an IN-SAMPLE artifact:
fitting isotonic on the GBM's own train preds (tighter than OOS) over-lifted
in a way that happened to help test. Done correctly (OOF) it does nothing.
=> NOT shipping. Canonical projection restored to the validated uncalibrated
champion (full_population_proj.parquet).

## Why monotone recalibration CAN'T fix the top end
Players we PREDICT 400-520 PA (n=303) have realized PA: mean 477, std 159,
28% reach 600+, 15% fall <=300. Wide BIMODAL spread at a fixed prediction.
The model is mean-calibrated (pred ~460, realized ~477). Isotonic maps
prediction->realized monotonically, so it cannot lift the iron-men without
also lifting the busts that share their prediction. The earlier "500+ band
under-prediction" was itself outcome-conditioning (selecting the top of the
spread). Not a recalibratable bias.

## Durability features — no-add
PA-floor, max-recent-PA, consecutive-500+ seasons, clean-health streak added
to champion: MAE 94.5 -> 94.9 (no-add). The GBM already has lagged PA; explicit
durability is redundant.

## Where the gap REALLY is (deployable, no outcome conditioning)
On players OUR model predicts as regulars:
- pred >= 500 (n=243):   ours MAE 101.6  vs Steamer 83.6   (Steamer +18)
- pred 400-520 (n=303):  ours MAE 128.9  vs Steamer 116.0  (Steamer +13)
Steamer is genuinely better on projected regulars. It is not recalibratable
and not extractable from our usage/durability features -> it is Steamer's
DEPTH-CHART / ROLE information (explicit "everyday starter -> ~650 PA"
allocation against a team PA budget) that we do not encode.

## Two ways to close it
1. The Steamer blend (already deployed): blend MAE 87.7 beats Steamer 90.3 —
   captures the depth-chart info Steamer has. Practical answer.
2. Build a DEPTH-CHART PA ALLOCATOR: allocate each team's ~6,200-PA budget down
   a projected role depth chart so regulars get ~650 and the team sums to the
   constraint. This is the real in-house path to Steamer's edge (and the true
   "own Steamer" — a constrained allocator, not an algorithm swap). Scoped next
   build; uncertain payoff but the only lever left that targets this gap.
