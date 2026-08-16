# Eephus MiLB value data — SDR + eWAR

Derived Eephus minor-league statistics, stored in git ahead of any frontend or public
integration. **Nothing here is wired into the site.**

## Contents

| file | rows | what it is |
|---|---:|---|
| `data/milb_sdr.csv` | 16,824 | Spatial Defensive Runs (SDR) + positional value |
| `data/milb_hitter_ewar.csv` | 17,833 | Eephus hitter WAR |
| `data/milb_pitcher_ewar.csv` | 22,076 | Eephus pitcher WAR |
| `data/metadata.json` | — | producer versions, positional coefficients, accounting identity |
| `MANIFEST.json` | — | per-file checksums, provenance, verification record, open defects |

**SDR = Spatial Defensive Runs**, Eephus's ball-in-play defensive metric. It is a *component*,
not a full defensive rating: it excludes positional adjustment (carried separately as
`position_runs`), and for catchers it covers balls in play only — framing, blocking and
throwing are unobserved and declared per row in `unobserved_defense_components`.

## Scope

```
seasons : 2021-2025
levels  : AAA, AA, High-A, Low-A     (full-season affiliated only)
grain   : player_id x season x level
```

A player who changed level within a season has one row per level. Run currency (`runs_per_win`)
is level-local — never sum run components across levels.

### Deliberately excluded

- **2026** — 0 rows. The 2026 defensive substrate (SDR era refit, d02, league environment,
  park factors) does not exist, so 2026 is not certified. This is a historical-only release.
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
