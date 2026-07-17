# Expansion E13 — Platoon Share + Manager Effect

- platoon universe: 6559 player-seasons (PA>=100, L/R bats); index sd 0.088

## 1. Reliability
- year-over-year platoon_index r = 0.560 (n=4271) -> platoon usage is a stable role

## 2. Projectability (target 2023-25) + new-info check
- model (champion + handedness + this-yr platoon): R2 0.262  MAE 0.057  rho 0.546
- naive (this-yr platoon_index): R2 0.159  MAE 0.061  rho 0.527
- corr(projected PA, platoon_next) = 0.472  (near 0 => platoon is genuinely NEW info beyond PA)

## 3. Manager effect (Q7) — leakage-safe residual test
- manager residual split-half (odd vs even seasons): r = 0.303 (n=76 managers)
- between-manager variance share of residual platoon usage: 30.5%
- OOS: trailing-manager platoon residual add -> MAE 0.0542 -> 0.0542 (Δ +0.0000)

## Verdict
Platoon usage stable + new-info if reliability high & PA-corr ~0. Manager ships only if split-half persists AND OOS MAE improves.

## VERDICT (concrete)
- Platoon usage = STABLE role (yoy r .560), PROJECTABLE (R2 .262 > naive .159),
  genuinely NEW info beyond PA (corr w/ projected PA only .47 vs bench .66).
  SHIPS as a separate role output.
- MANAGER (Q7): REJECT. Managers differ in-sample (between-manager variance
  30.5%, split-half .303) but trailing manager tendency adds +0.0000 OOS MAE.
  Player's own platoon history already captures deployment (platoon = real
  PLAYER talent, cf. variance_model). Leadership "behavior" is descriptive,
  not predictive — same lesson as org (E10) and GM. No leadership fixed
  effects enter Playing Time+.
