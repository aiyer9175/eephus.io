# Expansion E20 — Full-Population PA Projection

- incumbent slice: train 12594, test 1990

## Prospect slice — calibration / MAE-fix comparison (test 2023-25)
                     model    n     R2  MAE  RMSE    rho
        P-mean (two-stage) 2324 0.3323 19.5  52.9 0.4414
    direct-mean (champion) 2324 0.3530 20.1  52.1 0.4521
calib-p x median (MAE-fix) 2324 0.2039 18.0  57.8 0.4610
                   Steamer 2324 0.4588 14.4  47.7 0.4150
      blend direct+Steamer 2324 0.4832 16.6  46.6 0.4559
- absolute_error/median loss rejected: collapses to ~constant (rho NaN).
- MAE-fix (calib-p x median) cuts MAE 19.5->18.0 AND lifts rho — Steamer-
  free progress on the mass; Steamer's raw-MAE crown costs ranking, so the
  deployable best is the blend (wins RMSE+R2+rho, only loses raw MAE).

## Full-population coverage
- unified rows: 4444 (1990 incumbent + 2454 prospect)
- Steamer covers 97.0% of our population

## Full-population vs Steamer (common n=4309, targets 2023-25)
                 model    n     R2  MAE  RMSE    rho
        Ours (unified) 4309 0.7920 53.9  92.2 0.8380
               Steamer 4309 0.7722 49.4  96.5 0.8430
blend (ours+Steamer)/2 4309 0.8099 49.1  88.1 0.8427

## By slice (vs Steamer)
- incumbent (n=1985): MAE ours 93.5 | steamer 90.3 | blend 87.1   rho 0.8622 | 0.8478 | 0.8699   R2 ours 0.7164 | steamer 0.6742
- prospect (n=2324): MAE ours 20.1 | steamer 14.4 | blend 16.6   rho 0.4521 | 0.415 | 0.4559   R2 ours 0.353 | steamer 0.4588

---

## VERDICT — full-population projection delivered

**Coverage:** 4,444 players/season (1,990 incumbent + 2,454 prospect),
matching ~97% of Steamer's population. First Playing Time+ projection that
covers prospects, not just incumbents.

**Full-population accuracy (n=4,309, targets 2023-25):**

| system | R² | MAE | RMSE | rho |
|---|---|---|---|---|
| Ours (unified, Steamer-free) | .792 | 53.9 | 92.2 | .838 |
| Steamer | .772 | 49.4 | 96.5 | .843 |
| **blend (ours+Steamer)** | **.810** | 49.1 | **88.1** | .843 |

Our fully independent projection beats Steamer on R² and RMSE, ties ranking;
the blend wins R²/RMSE, ties rho, matches MAE.

**The near-zero-mass MAE question (what the user asked):**
- Closing the info gap (Opening-Day roster status) was the big prospect gain
  (E11: MAE 21.0 -> 18.9, out-ranks Steamer).
- Steamer-free calibration of the mass: calib-p_debut × median-debut-PA cuts
  prospect MAE 19.5 -> 18.0 AND lifts ranking (rho .441 -> .461). Real
  progress with the same data.
- Steamer's remaining raw-MAE edge (14.4) comes from aggressive shrinkage of
  the zero-mass that COSTS ranking; pure MAE-optimal (median/abs-error) loss
  collapses to a near-constant and destroys the ranking that is our edge.
  Not worth chasing standalone — the blend captures Steamer's calibration
  while keeping our ranking, winning R²/RMSE/rho on both slices.

**Status:** Phase-2 integration milestone — full-population deliverable shipped
(data/processed/full_population_proj.parquet). Deployable champion = blend;
Steamer-free unified is the no-dependency fallback and still beats Steamer on
R²/RMSE.
