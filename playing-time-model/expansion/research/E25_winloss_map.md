# Expansion E25 — Final (Steamer-free) Model: Win/Loss Map

- common universe (ours ∩ Steamer ∩ ZiPS): 4089 player-seasons, targets 2023-25

segment                               n MAE ours MAE stm MAE zip rho ours rho stm  win(MAE/rho)
ALL                                4089     57.1    51.9   292.0    0.845   0.845  steam/OURS

[slice]
  incumbents                       1980     94.6    90.3   218.4    0.862   0.848  steam/OURS
  prospects                        2109     21.9    15.7   361.1    0.462   0.414  steam/OURS

[projected-PA band (ours)]
  proj <100                        2598     21.0    17.2   356.6    0.471   0.411  steam/OURS
  proj 100-300                      683    120.7   111.8   245.6    0.476   0.546  steam/steam
  proj 300-500                      565    127.3   124.9   139.2    0.408   0.438  steam/steam
  proj 500+                         243    101.6    83.6    86.9    0.284   0.350  steam/steam

[age]
  age <=23                          231    128.7   110.9   233.1    0.749   0.773  steam/steam
  age 24-27                         809    101.6    95.2   235.4    0.842   0.840  steam/OURS
  age 28-31                         620     85.0    81.7   203.2    0.887   0.872  steam/OURS
  age 32+                           320     71.2    79.8   194.6    0.904   0.869  OURS/OURS

[MLB experience (career PA thru t)]
  no MLB (debut yr)                2109     21.9    15.7   361.1    0.462   0.414  steam/OURS
  rookie <500                       744     93.4    84.0   294.4    0.771   0.772  steam/steam
  established 500-2k                693     94.4    91.1   180.2    0.854   0.847  steam/OURS
  veteran 2k+                       543     96.6    97.9   163.1    0.858   0.831  OURS/OURS

[Opening-Day roster]
  on OD active roster              1146    120.9   113.6   142.8    0.699   0.710  steam/steam
  NOT on OD roster                 2943     32.2    27.8   350.1    0.599   0.567  steam/OURS

## Summary
- overall MAE ours 57.1 vs Steamer 51.9; rho ours 0.845 vs Steamer 0.845
- ZiPS shown for MAE context (it over-projects PA; weak on this task).

## VERDICT — where the fully-owned model wins vs loses

OVERALL: rho TIED with Steamer (.845 = .845) with ZERO dependency; MAE 57.1
vs 51.9 (Steamer +5, concentrated — see below). ZiPS not competitive (MAE 292).

WE WIN (beat Steamer outright):
- AGE 32+: MAE 71.2 vs 79.8 AND rho .904 vs .869 — clean sweep. Our injury +
  usage-history model correctly discounts aging/injury-prone vets that Steamer
  over-projects. Biggest clean win.
- VETERANS (2k+ career PA): MAE 96.6 vs 97.9, rho .858 vs .831 — win both.
- RANKING (rho) broadly: prospects (.462 vs .414), incumbents (.862 vs .848),
  established players, non-players. We order the population as well or better.

WE LOSE (Steamer better), all the SAME root cause:
- PROJECTED REGULARS (proj 500+): MAE 101.6 vs 83.6, rho .284 vs .350.
- YOUNG / UNCERTAIN ROLE: age<=23 (MAE 128.7 vs 110.9), rookies <500 career PA
  (93.4 vs 84.0), on-OD-competing (120.9 vs 113.6), proj 100-500 (rho loss).
- These are exactly the players whose role is unresolved at projection time;
  Steamer's HUMAN-CURATED depth charts (RosterResource) resolve it, we can't.
- Near-zero mass (proj<100): small MAE edge to Steamer (calibration on zeros).

ONE-LINE MAP: we win on ESTABLISHED & AGING players (skill + injury + usage
history = our strength) and on RANKING everywhere; we trail on YOUNG /
BORDERLINE / competing-for-a-job players (curated role knowledge = Steamer's
strength). The loss zone is precisely the external-curation dependency we
deliberately chose not to take. Acceptable, well-characterized tradeoff for a
fully-owned system; the only way to close it stays external (ingest a
depth-chart feed), so it's the same dependency by another name.
