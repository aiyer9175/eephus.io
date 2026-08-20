# Eephus MLB value data — SDR + eWAR

Derived Eephus major-league statistics, stored in git ahead of any frontend or public
integration. **Nothing here is wired into the site.** This is the MLB sibling of
`milb-value/` and follows the same shape: `data/` + `MANIFEST.json` + this README.

## Contents

| file | rows | seasons | what it is |
|---|---:|---|---|
| `data/mlb_sdr.csv` | 24,669 | 2006–2026 | Spatial Defensive Runs (SDR) |
| `data/mlb_position_player_ewar.csv` | 8,818 | 2016–2026 | Eephus position-player WAR |
| `data/mlb_pitcher_ewar.csv` | 4,066 | 2021–2025 | Eephus pitcher WAR |

## Freshness is per file, not global

There is **no** single "current through" date for this directory, and any statement that
there is would be false:

```
mlb_sdr.csv                    current through 2026-08-19
mlb_position_player_ewar.csv   current through 2026-07-30
mlb_pitcher_ewar.csv           season 2025 — no 2026 at all
```

**SDR is current; position-player eWAR is not, and pitcher eWAR has no 2026.**

The reason position-player eWAR lags is worth stating plainly, because it is easy to assume
otherwise: its fielding component is **Defense+, not SDR**. Refreshing MLB SDR does not make
eWAR fielding current by that route. eWAR is limited by its own offence substrate, whose
2026 rows carry roughly 108 team games against a league median of 127 at 2026-08-19.

Pitcher eWAR ends at 2025 because its upstream substrate does. It is not extrapolated.

## Catchers

`mlb_sdr.csv` contains **no catcher rows at all** — the model's MLB position scope is 1B,
2B, 3B, SS, LF, CF and RF. Final catcher SDR is not certified, and nothing here should be
read as covering catcher defence.

## Calibration is frozen forward

Pooled parameters are estimated once on the certified historical window and then applied to
later seasons. Adding a season does not refit prior seasons or restate previously published
player values.

## What SDR is

**SDR = Spatial Defensive Runs**, Eephus's ball-in-play defensive metric. It is a
*component*, not a full defensive rating: it measures outs made above expectation on balls
in play given where and how they were hit. It excludes positional adjustment, and it does
not observe catcher framing, blocking or throwing.

SDR is **not** claimed to be superior to OAA, DRS, UZR or FRP. Its year-to-year
self-persistence is well below OAA's, and its middle-of-distribution ordering is at chance
in the modern era. It is an independent construct, not a better one. The full audit,
including the unfavourable findings, is published with the methodology package.

## Provenance

```
SDR model release   SDR-ERA-REFIT-D007SAFE-1.0.0
SDR generation      E-E04-D007-1.2.0+daily.2026-08-20T020943
software release    eephus-metrics-2026.08.6
```

Daily SDR is score-only against frozen model bundles: the daily job may score, it may not
train.
