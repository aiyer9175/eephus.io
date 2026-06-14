# Module 15 — Call-up / Debut Hazard (Model D v1)

- universe: 21508 AA/AAA pre-debut player-seasons (9497 players)
- train 14670 (targets 2010-19+2022, debut rate 7.2%), test 2454 (2023-25, 12.2%)
- FV coverage in test: 18.5%

## Debut-in-t+1 classification (ablation ladder)
      model    AUC  Brier  LogLoss
       PERF 0.8322 0.0836   0.2857
     +DRAFT 0.8462 0.0828   0.2782
+TX(40-man) 0.8650 0.0768   0.2620
        +FV 0.8738 0.0774   0.2625

## Calibration (+FV, test)
                                    pred  actual    n
(-0.00013600000000000005, 0.0026]  0.001   0.004  246
(0.0026, 0.00768]                  0.005   0.008  245
(0.00768, 0.0133]                  0.010   0.012  245
(0.0133, 0.0221]                   0.018   0.041  246
(0.0221, 0.0352]                   0.028   0.045  245
(0.0352, 0.0581]                   0.045   0.037  245
(0.0581, 0.104]                    0.078   0.098  246
(0.104, 0.239]                     0.163   0.102  245
(0.239, 0.578]                     0.379   0.253  245
(0.578, 0.966]                     0.782   0.618  246

## PA_next regression (same features): MAE 21.6, RMSE 55.2

## FV incremental on FV-covered test rows (n=454)
              model    AUC  Brier  LogLoss
no-FV on FV-covered 0.7992 0.1805   0.5656
   FV on FV-covered 0.7905 0.1966   0.6001
