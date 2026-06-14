# Module 2 — Usage Spine Report

- dropped 12228 pitcher-only batting rows (pre-universal-DH NL pitchers)
- spine: 17074 player-seasons, 3285 players, seasons 2000-2026
- PA cross-check vs deep_mlb: 17018 matched rows, 99.2% exact match, mean abs diff 0.02 PA
- spine rows >=50 PA missing from deep_mlb: 0 (deep_mlb had its own filters; spine is the authority for usage)
- saved usage_spine.parquet: (17074, 41)

## League PA by season (sanity)
season
2000    183882
2001    180869
2002    180559
2003    181369
2004    182394
2005    180165
2006    182023
2007    182777
2008    181662
2009    181066
2010    179602
2011    179286
2012    178269
2013    179363
2014    178452
2015    178252
2016    179270
2017    180025
2018    180047
2019    181444
2020     66503
2021    177133
2022    182046
2023    184101
2024    182447
2025    182919
2026     77536
