# Eephus MiLB value data — SDR + eWAR

Derived Eephus minor-league statistics, stored in git ahead of any frontend or public
integration. **Nothing here is wired into the site.**

## Contents

| file | rows | what it is |
|---|---:|---|
| `data/milb_sdr.csv` | 19,462 | Spatial Defensive Runs (SDR) + positional value |
| `data/milb_hitter_ewar.csv` | 20,515 | Eephus hitter WAR |
| `data/milb_pitcher_ewar.csv` | 22,076 | Eephus pitcher WAR |
| `data/metadata.json` | — | producer versions, positional coefficients, accounting identity |
| `MANIFEST.json` | — | per-file checksums, provenance, verification record, open defects |

**SDR = Spatial Defensive Runs**, Eephus's ball-in-play defensive metric. It is a *component*,
not a full defensive rating: it excludes positional adjustment (carried separately as
`position_runs`), and for catchers it covers balls in play only — framing, blocking and
throwing are unobserved and declared per row in `unobserved_defense_components`.

## Scope

```
seasons : 2021-2026
levels  : AAA, AA, High-A, Low-A     (full-season affiliated only)
grain   : player_id x season x level
```

**2021-2025 are certified completed seasons. 2026 is certified season-to-date, through
2026-08-19.** The 2026 season is a full methodological peer of the completed ones -- same
estimator, same grain, same accounting identities, same replacement and league-adjustment
economy, and calibration frozen on the certified historical window. It differs only in
having partial exposure: roughly 121 of ~150 team games had been played at the
source-through date, so counting totals are lower by construction while rate quantities sit
inside the historical band. It is not provisional and it is not a final season.

Pitcher eWAR remains **2021-2025**: its upstream substrate ends at 2025 and has not been
extended. Freshness is per file, not global.

A player who changed level within a season has one row per level. Run currency (`runs_per_win`)
is level-local — never sum run components across levels.

### Deliberately excluded

- **2026 catchers** — 681 player-seasons withheld from `milb_hitter_ewar.csv` and
  `milb_sdr.csv`. Any 2026 player-season with catcher innings carries a defensive value
  covering **spatial balls in play only**; framing, blocking and throwing are unobserved,
  and final catcher SDR is not certified. 2021-2025 catcher rows remain exactly as
  previously published, with the limitation declared per row in
  `unobserved_defense_components` — historical scope is deliberately unchanged rather than
  quietly rewritten to match 2026.
- **2026 pitcher eWAR** — 0 rows. The pitcher substrate genuinely ends at 2025 and is not
  manufactured.
- **Rookie/CPX (sportId 16) and DSL (sportId 17)** — not supported by the canonical model.
  Work exists only as unpromoted research and would need its own certification.

## Provenance

Built by `s03_release.py` from the promoted production run `20260814_045956_26062c` and copied
here byte-for-byte. No recomputation, no rounding, no schema change — the files in `data/` are
sha256-identical to the certified release artifact, and an independent reconstruction from the
production parquets reproduced every column exactly (max |Δ| = 0.000e+00). See `MANIFEST.json`.

## Reading the CSVs

Floats are written at shortest round-trip precision. Empty string is written as an empty field,
which is distinct from null:

```python
pd.read_csv(path, float_precision="round_trip", keep_default_na=False, na_values=[])
```

## Open defects — read before using this data

| id | status |
|---|---|
| **D-007** | The promoted SDR generation was fit with a leaked feature (`loc_code`). A de-leaked replacement exists and is byte-reproducible but is **not yet promoted**. On MiLB SDR the correction moves r to 0.848 with 15.47% sign flips and max \|Δ\| 11.56 runs. Affects `milb_sdr` and, through `defense_runs`, `milb_hitter_ewar`. **Resolve before any site-facing use.** |
| **D-001** | Whether publicly redistributing an aggregated statistic computed downstream of MLBAM access is permitted is unresolved. These files are in a **private** repo and are not published. Must be closed before any public exposure. |
| pitcher AAA join gap | `milb-pitcher-ewar-1.2.0` leaves `sportId/g/gs/r/lg_ra9` null for all AAA rows. Those fields are excluded from this schema; `pitcher_ewar` itself is complete. |

## Methodology

Not documented here. The canonical methodology and certification record live with the producer
(`ewar_production`): positional adjustment `POSADJ-EEPHUS-2.0.0`, hitter `milb-hitter-ewar-1.3.0`,
pitcher `milb-pitcher-ewar-1.2.0`, SDR `sdr-era-refit-2026-07-20`. Version stamps are carried on
every row.

## 2026 park factors

Through 2025, MiLB park factors came from a league home/away aggregate endpoint. That
endpoint now returns nothing for **any** season, so from 2026 the same quantity is derived
from a game ledger built on the schedule primitive. This changes the *transport*, not the
estimator: the run-factor estimator, its grain, its shrinkage and its league-season
centring are unchanged, and certified 2021-2025 values were preserved rather than restated.

Run over the 600 overlapping team-seasons, the two transports agree at Pearson **0.9982**,
Spearman **0.9977**, mean absolute difference **0.0023**, median difference **0.0000**, with
88.5% of home-game counts exact (2023: 100%). Same-park year-over-year persistence across
the seam (2025 to 2026) is **higher** than any adjacent pair built entirely on the legacy
transport.

The quantity consumed by hitter eWAR is the single-season shrunk run factor. Home-run park
factors and the three-year smoothed factor are **not published for 2026** — the schedule
primitive carries no home-run or plate-appearance counts, and a centred three-year window
covering 2026 would recompute 2025's own value. Neither is consumed by hitter eWAR.

## Calibration is frozen forward

Pooled parameters — the linear weights that convert events to runs, the shrinkage constants
that pull sparse defensive samples toward zero, and the dispersion behind defensive standard
errors — are estimated once on the certified historical window and then **applied** to later
seasons. Adding a season does not refit prior seasons. A value published for 2023 is the
same value after 2026 is added.

## One historical correction since the previous release

2021-2025 SDR-derived values in this release differ from the 2026-08-16 ingestion. That is
the **D-007 SDR correction** (`C-SDR-E-E04-D007-1.2.0`), certified 2026-08-18, and it is
recorded rather than silently applied. `batting_runs` is unchanged (0 cells). The 2026
extension itself changed no historical value: maximum absolute delta **0.0**.
