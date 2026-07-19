# Expansion E11 — Prospect Playing-Time Projection + Value Audit

- prospect universe: 21508 AA/AAA pre-debut seasons; eval (2023-25) n=2454, debut rate 12.2%, median debut PA 78

## Incremental value ladder (expected PA, OOS targets 2023-25)
          model    n  MAE  RMSE    rho  debut_AUC
   M0 age+level 2454 22.2  63.1 0.1780     0.6399
M1 +minors perf 2454 20.3  58.8 0.3801     0.8413
      M2 +draft 2454 20.4  58.1 0.4004     0.8510
     M3 +40-man 2454 20.1  57.3 0.4080     0.8634
         M4 +FV 2454 19.7  55.2 0.4199     0.8805

## FV increment on FV-covered prospects only (n=454)
{'model': 'M3 +40-man', 'n': 454, 'MAE': 72.0, 'RMSE': 119.5, 'rho': 0.458, 'debut_AUC': 0.7946}
{'model': 'M4 +FV', 'n': 454, 'MAE': 72.3, 'RMSE': 114.6, 'rho': 0.5081, 'debut_AUC': 0.8112}

## Prospect benchmark vs Steamer (n=2324, targets 2023-25)
                      model  MAE  RMSE    rho
Ours (M3, prospect-trained) 21.0  58.1 0.4102
                    Steamer 14.4  47.7 0.4150
     blend (ours+Steamer)/2 16.7  48.4 0.4392

## Read
- debut_AUC = stage-1 ranking of WHO debuts; rho = ranking of how much PA.
- ladder shows which signals actually move prospect playing time.
- Steamer comparison = what a prospect-specific model adds over the public system that already projects these players.

---

## VERDICT (prospect playing-time research)

**What predicts prospect PA, ranked by incremental value:**
1. Minors performance — the dominant signal (debut AUC .640 -> .841).
2. FV pedigree — **REAL ADD in the prospect universe** (AUC .863 -> .881
   pooled; FV-covered subset rho .458 -> .508, RMSE 119.5 -> 114.6). Contrast
   with parent Module 6, where FV was REJECTED for incumbents. Prospects are
   exactly where pedigree carries information -> FV EARNS inclusion here.
3. Draft pedigree + 40-man selection — small but positive.
4. Org tendency — REJECTED earlier (E10, mediated by 40-man).

**Does our prospect model beat the public system?** Not on magnitude.
Steamer MAE 14.4 / RMSE 47.7 beats ours 21.0 / 58.1; we tie on ranking
(rho .410 vs .415). The blend lifts ranking to .439 (best). Caveat: same
info-date asymmetry as incumbents — Steamer is a near-Opening-Day projection
(spring + roster info); ours predicts from end of minor-league season.

**So: standalone prospect model adds only modest value over Steamer (ranking
via blend), but the prospect-specific FEATURES (perf + FV) are validated.**
Per the directive ("if no clear added value, move to full-population
projection"): the evidence supports moving to the FULL-POPULATION
integration stage, where the prospect slice = our debut-ranking model
(perf + FV + draft + 40-man) blended with Steamer for PA magnitude, unified
with the incumbent champion. The remaining open lever before that: add
Opening-Day roster status (on-40-man / recalled by OD) to the prospect
model to close the info-date gap with Steamer — cheap, timestamp-valid,
likely the biggest available magnitude gain.

## UPDATE — Opening-Day roster info closes the gap (the fair-info test)

Adding on-40-man / on-active / depth at Opening Day (timestamp-valid, same
info date Steamer uses) to the prospect model:

| prospect model (2023-25, n=2,324) | MAE | RMSE | rho | debut AUC |
|---|---|---|---|---|
| Ours, no OD info | 21.0 | 58.1 | .410 | .858 |
| **Ours + Opening-Day roster** | 18.9 | 52.7 | **.430** | **.876** |
| Steamer | 14.4 | 47.7 | .415 | — |
| **blend (ours+OD, Steamer)** | 16.0 | **46.8** | **.445** | — |

With a fair info date our prospect model OUT-RANKS Steamer (rho .430 > .415);
the blend beats Steamer on RMSE and rho. Steamer keeps the raw-MAE edge
(better calibrated on the near-zero mass) — same incumbent pattern. The
earlier "Steamer wins prospects" was the info-date handicap, not a model gap.

**FINAL: prospect research yields real added value.** Validated prospect
feature stack = minors performance + FV pedigree + draft + 40-man +
Opening-Day roster. GREENLIGHT the full-population integration: prospect
slice = this model (blended with Steamer for magnitude), unified with the
incumbent champion to project the entire player population.
