# 05 — Raw Advancement Measure Comparison

Four candidates were built (`raw_pace.py`) and compared on latest as-of rows, T=30:

| measure | definition | verdict |
|---|---|---|
| A `steps_per_season` | (highest rank − starting rank) / active seasons | rejected as primary |
| B arrival gaps | active seasons between consecutive first meaningful arrivals | diagnostic only |
| C `highest_rank` | highest meaningful level reached (residualized vs experience by the baseline) | shadow of D |
| **D `area_pace`** | **mean PA-weighted ladder height per active season** | **adopted** |

## Evidence

Inter-correlations (spearman, latest as-of):
- D vs C: **0.970** — same ranking information, but D is continuous where C is a 5-step integer.
- D vs A: 0.727; A vs C: 0.819.

Threshold robustness (ρ vs T=30 build across T ∈ {10,20,50,75}):
- D: **0.989 / 0.995 / 0.991 / 0.981** (most robust)
- C: 0.970–0.988
- A: 0.890–0.969 (least robust — promotion counting is cameo-sensitive)

Measure B face validity: median gap between meaningful arrivals at consecutive rungs is
**exactly 1.0 active season** (mean 1.31, n = 12,668 transitions) — the ladder moves one
level per year for the typical climber, which is the folk prior. B is reported as a
diagnostic; as a score it only exists for players with ≥1 transition.

## Why D (area under the level-over-time trajectory, per active season)

- Rewards **sustained placement** at higher levels, per the charter's own design note.
- **Repetition/regression handled without punitive add-ons** (charter 5E): a player who
  repeats a level accrues flat height while peers climb; a player demoted after
  meaningful higher-level exposure accrues height below their peak. No explicit demotion
  penalty is imposed — and rehab/paper transactions therefore cannot generate one.
- Robust to brief assignments twice over: sub-threshold stints don't count at all, and
  a threshold-clearing cameo only shifts a PA-weighted average.

A weighted composite of A/C/D was considered and rejected: D alone carries C's ranking
(ρ 0.97) and is more stable than A — a composite would add opacity for no descriptive gain
(charter: avoid black-box if a simple calculation matches).
