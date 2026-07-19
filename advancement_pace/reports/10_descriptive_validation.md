# 10 — Descriptive Validation

This is validation that the statistic *describes advancement history* stably — not
predictive validation (none exists, by design).

| check | result | verdict |
|---|---|---|
| rank stability across thresholds | final AP+ ρ = 0.965 (T20) / 0.930 (T50) vs T30; chosen raw measure ρ ≥ 0.981 for T ∈ {10..75} | PASS |
| robustness to brief assignments | cameos below 30 PA never count; threshold-clearing cameos only shift a PA-weighted mean; rehab-veteran leak found and closed (01) | PASS |
| era comparability | era means 99.89–100.13 post-adjustment | PASS |
| position-group stability | group means 100.02–100.15 post-adjustment | PASS |
| age adjustment | bucket means 99.80–100.32 | PASS |
| entry-path adjustment | pathway means 99.81–100.31 | PASS |
| 2020 sensitivity | straddle cohort +1.3 artifact, bounded and documented (04); zero 2020 rows asserted | PASS w/ documented caveat |
| stability across refreshes | residuals from a ≤2023-only fit vs full fit: r = 0.9973 on shared rows | PASS |
| extreme small samples | 0.9% of first-year rows outside 85–115; cap hits 0.14%/0.40% | PASS |
| face validity | case-study panel below | PASS |

## Case studies (interpretability, not proof)

| path archetype | player | AP+ (pct, tier) | trajectory |
|---|---|---|---|
| teenage intl mover | Jackson Chourio | 124.8 (99th, Est) | Rk→A+→AA by age 19 |
| teenage intl mover | Jesús Made | 123.3 (99th, Est) | Rk→A+→AA in 3 seasons |
| polished college, high start | Nick Kurtz | 125.4 (99th, Dev) | A→AAA in 2 seasons |
| polished college, high start | Jac Caglianone | 113.0 (95th, Dev) | A+→AAA in 2 seasons |
| catcher (vs catcher peers) | Samuel Basallo | 113.6 (94th, Est) | Rk→Rk→A+→AAA at 16-entry |
| catcher, college | Dalton Rushing | 106.5 (78th, Est) | A→A+→AAA |
| repeating levels | Byron Chourio | 95.0 (30th, Est) | Rk,Rk,A,A,A over 5 seasons |
| repeating levels | Kevin Made | 98.3 (44th, Est) | A,A+,A+,AA,AA |
| slow high-pedigree start | Ethan Holliday | 92.4 (11th, Dev) | A,A in first 2 seasons |
| rapid HS-draft riser | Jordan Lawlar | 135.6→cap 130 (100th) | A→AA→AAA by 20 |
| one complex season | Deinis Chourio | 103.5 (71st, Early) | single Rk season, shrunk toward 100 |
| rehab veterans | Hamilton / Wright / D. Young | **excluded** | post-debut rows dropped (leak fixed) |

Fast paths read fast, repeaters read slow, catchers are judged against catchers,
one-season players sit near 100 with an Early tag, and rehab paths cannot appear.
The score reads exactly as the methodology copy claims.
