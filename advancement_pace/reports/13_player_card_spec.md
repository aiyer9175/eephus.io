# 13 — Future Player-Card Content Specification

Content spec only — no final UI, no visual styling (Eephus design system owns that).
Maps onto the existing MiLB module conventions (hash routes, sub-tabs, byline).

## Card block

```
Advancement Pace+        118
86th percentile · Developing sample
```

- Score: `advancement_pace_plus` (already capped 70–130), 0 decimals.
- Percentile: `min(advancement_percentile, 99)`, ordinal suffix.
- Tier chip: `sample_quality`.

**Primary explanation (one line):**
"Advanced through the minor-league ladder faster than comparable players with a similar
age, position group, entry pathway, and professional experience."
(swap *faster* → *slower* below 100, *at a typical pace* for 97–103)

**Methodology hover:**
"Advancement Pace+ describes how quickly a player has progressed through affiliated
minor-league levels relative to comparable peers (100 = typical; 110 ≈ one standard
unit faster). It is not a talent grade or a projection, and it does not feed any
Eephus projection or valuation model."
Never render percentage language ("18% faster" is wrong on this scale).

**Sample note:** "Based on {active_pro_seasons} active professional seasons and
{meaningful_assignments} meaningful level assignments."

**Trajectory display** (derive from `level_history.parquet`, meaningful assignments only):
```
2024  Complex
2025  Low-A → High-A
2026  Double-A
```

## Display behavior matrix

| state | detection | behavior |
|---|---|---|
| insufficient sample | no row / tier Insufficient | show "—" + "Not enough professional history yet"; no number |
| Early tier | `sample_quality="Early"` | show score with tier chip; hover adds "small sample — score is shrunk toward 100" |
| 2020-adjusted career | meaningful play ≤2019 and ≥2021 | footnote "2020 minor-league season cancelled; not counted as development time" |
| currently injured / inactive season | player has no current-season row | show latest as-of season explicitly: "through 2025" |
| ambiguous level history | `entry_pathway="undrafted_other"` & starting_level ∈ {AA, AAA} | footnote "entered affiliated ball at an advanced level" |
| already debuted | `season == mlb_debut_season` is last row | freeze card at final pre-debut as-of; label "MiLB path through debut (2025)"; never update again |
| retired / inactive | no row for ≥2 seasons and no debut | render score with "final as-of {season}" label |

Field mapping is 1:1 with the publication schema; no computation happens in the UI.
