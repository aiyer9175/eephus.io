# Expansion E30 — In-Season IL Status in the ROS Updater

- reconstructed 39582 IL stints (2002-2026); 60-day share 19%
- ROS rows 8649; currently-on-IL at cutoff 13.7%, on 60-day 4.3%

## Rest-of-season PA (test 2023-25)
             model     R2  MAE  RMSE    rho
        naive pace 0.5449 66.7  90.8 0.7385
      E14 base GBM 0.5430 73.2  91.0 0.7228
E14 + in-season IL 0.5734 70.9  88.0 0.7481

## Currently-on-IL-at-cutoff segment (where it should bite)
- currently on IL (n=330): MAE base 90.9 -> +IL 78.7 | pace 82.3
- on 60-day IL (n=111): MAE base 115.9 -> +IL 78.2 | pace 85.4
- healthy at cutoff (n=2940): MAE base 71.2 -> +IL 70.0 | pace 64.9

## VERDICT — SHIPS (in-season ROS updater)
Reconstructed 39,582 dated IL stints from the transaction log (owned, no
Steamer/news feed). As-of-cutoff IL features added to the E14 ROS updater:
- Overall: R² .543 -> .573, RMSE 91.0 -> 88.0, rho .723 -> .748; now beats
  naive pace on R²/RMSE/rho (base GBM did not).
- Segment validation: currently-on-IL MAE 90.9 -> 78.7; ON 60-DAY IL
  115.9 -> 78.2 (-38 PA); healthy unchanged (71.2 -> 70.0, no harm).
=> in-season IL status is a real, owned, leakage-clean ADD to the rest-of-
season product. This is the owned-data way to capture injury churn — exactly
the in-season information the oracle test (E29) identified as the remaining gap.

Scope: IN-SEASON only. Preseason model unchanged (on_il_at_od already captures
OD injury state; preseason at its ceiling). Confirms the project arc: the
remaining accuracy is in-season, recovered by OBSERVING (transaction-log IL
timeline) — not by preseason curation.
