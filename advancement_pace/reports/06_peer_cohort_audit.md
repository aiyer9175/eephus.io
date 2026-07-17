# 06 — Comparison Cohort Audit

Peer dimensions adopted (empirically justified, per charter):

| dimension | form | kept because |
|---|---|---|
| starting level | 5 levels, interacted with experience | the dominant driver: expected height after N seasons differs by ~3 rungs between Rk and AAA entries |
| active experience | integer years, interacted with starting level | pace is meaningless unconditioned on time |
| entry age | buckets ≤17 / 18 / 19–20 / 21–22 / 23+ | +0.24 rungs expected height for 23+ vs ≤18 entries at same start |
| entry pathway | draft_college / draft_hs / intl_amateur / undrafted_other (draft file × entry age) | intl amateurs −0.33 rungs vs college draftees at same start/age — real, face-valid (DSL depth) |
| era (entry cohort) | 2009–13 / 2014–16 / 2017–19 / 2021+ | 2017–19 cohorts +0.13 rungs (system contraction pushed movement); kept for era comparability |
| position group | Catcher / MIF / CIF / OF / Utility | see below |
| hitter vs pitcher | hitters only | no pitcher data program exists |
| domestic vs international | folded into entry pathway | draft file is the reliable signal; DSL not separable at level grain |

## Position group: tested, and INCLUDED
The charter allowed dropping position if immaterial. Initial identity-based positions
covered only 26% of players (current players only) — inadequate and biased. Rebuilt from
`milb_fielding_full` (innings-weighted primary MiLB position, Utility if no position
holds ≥40% of innings): **99.4% of scoreable rows covered, era-correct**. Unadjusted
group effects are systematic and face-valid — catchers ≈1.8 public points slower than
middle infielders (99.3 vs 101.1 pre-adjustment). Since the public explanation promises
"similar … position group", position stays in the adjustment. Post-adjustment group
means: Catcher 100.15, CIF 100.05, MIF 100.02, OF 100.03, UT 100.14 — flat.

## No tiny cohorts
Cohort cells are never used raw: starting_level × experience cells are EB-style
protected (rare cells fit their own mean → members score ≈100 — deliberately
conservative for oddball entries like AA/AAA foreign-pro signings), and all other
dimensions enter additively (coefficients estimated on the full population, not cells).
