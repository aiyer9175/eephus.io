# Expansion E28 — Allocation Engine + Oracle Ceiling

- role-PA prior by usage rank (training): r1:669, r2:621, r3:574, r5:477, r8:310, r10:205, r13:74
- test incumbents 1985; with OD team 56%

## Overall (incumbents, test 2023-25)
                       model     R2  MAE  RMSE    rho
         champion (baseline) 0.7145 94.5 124.0 0.8615
     AUTO-alloc (deployable) 0.6711 97.1 133.1 0.8488
            blend champ+auto 0.7110 93.3 124.8 0.8602
      ORACLE-alloc (ceiling) 0.8785 59.6  80.9 0.9221
blend champ+oracle (ceiling) 0.8468 70.0  90.8 0.9173
         Steamer (yardstick) 0.6742 90.3 132.5 0.8478

## Projected-regular band pred>=500 (where the gap lives) — MAE
- champion         101.6
- auto             100.6
- blend+auto       96.6
- ORACLE           52.6
- blend+ORACLE     68.2
- Steamer          83.6

## Read
- champion->ORACLE = total ceiling of curated allocation.
- AUTO->ORACLE = value of correct human job-resolution (the manual layer).
- if blend+ORACLE ~ champion, even perfect curation doesn't help -> don't build.
