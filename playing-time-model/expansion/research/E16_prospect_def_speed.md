# Expansion E16 — Prospect Defense/Speed (scouting grades)

- prospect test n=2454; with scouting grades 18% (n=451) — limited, like FV

## Pooled (test 2023-25)
- E11 base           debut_AUC 0.8921  PA_MAE 18.7  PA_rho 0.4366
- +scout def/speed   debut_AUC 0.8902  PA_MAE 18.9  PA_rho 0.4395

## On scouting-covered prospects only (fair test)
- E11 base           debut_AUC 0.8283  PA_MAE 72.0  PA_rho 0.5264
- +scout def/speed   debut_AUC 0.8242  PA_MAE 72.5  PA_rho 0.5431

## Glove-first prospects (field>=55, below-median bat; n=54)
- E11 base           debut_AUC 0.7937  PA_MAE 25.3  PA_rho 0.4293
- +scout def/speed   debut_AUC 0.7817  PA_MAE 30.4  PA_rho 0.4102

## VERDICT — REJECT for prospects too
Scouting field/speed/arm add nothing to the prospect model: pooled AUC
.892->.890, MAE 18.7->18.9; covered subset AUC .828->.824; glove-first (n=54)
AUC .794->.782, MAE 25.3->30.4 (actively worse). FV already integrates defense
(it's a composite value grade) -> component grades redundant on top of FV +
performance + 40-man. Combined with E15: DEFENSE/SPEED add nothing for
EITHER universe — mediated by usage history (incumbents) or by FV (prospects).
Defense matters for playing time but is always already captured.
