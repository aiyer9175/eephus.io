# Career+ — Career Defensive-Value Projection (CAPSTONE)
Date: 2026-06-18 · `pipeline/17_career_plus.py` · Monte Carlo (2000 paths/player)

## What it is
The integration of the whole program: a per-player **remaining-career defensive value** projection that combines every part —
- **current talent** (Part 2 — `06_defense_plus_2025.csv`, position-relative runs + posadj + SD),
- **aging** (Part 4 — per-position runs/yr decline: C −0.80, CF −0.73, SS −0.62 … 1B +0.07),
- **migration** (Part 5 — down-spectrum move rates, rising with age at SS/CF),
- **longevity** (Part 5 — regular exit hazard by age: ~8–13% prime → 17–30% late 30s).

Each simulated career-year: age the talent by the position's slope, add the positional adjustment, accrue value (×0.85 playing time), then maybe migrate down the spectrum (posadj drops, range talent carries) and maybe exit. Output = career defensive runs / dWAR with an 80% credible interval and expected career length.

## The program's 5 questions, answered per player
Example (current MLB defenders):

| player | pos | age | 1) now (runs/yr) | 2) ages | 4) 80% CI (runs) | 5) career runs / dWAR / yrs |
|---|---|--:|--:|---|---|---|
| **Patrick Bailey** | C | 26 | **+28** | −0.8/yr | [0, 268] | **134 / 13.4 / ~6** |
| **Bobby Witt Jr.** | SS | 25 | +20 | −0.6/yr | [14, 149] | 77 / 7.7 / ~7 |
| Ke'Bryan Hayes | 3B | 28 | +20 | −0.2/yr | [0, 125] | 61 / 6.1 / ~6 |
| Pete Crow-Armstrong | CF | 23 | +17 | −0.7/yr | [0, 88] | 40 / 4.0 / ~7 |

(3) *what position* = starts at current position with down-spectrum drift modeled; PCA's CF value erodes fastest (steep aging + corner migration), Hayes's 3B holds (gentle aging, low migration).

## Reads
- **Catchers dominate career defensive value** (Bailey, Kirk, Narváez, Dingler top the board): framing runs + the highest positional adjustment (+12.5) + near-zero migration (Part 5: catchers stay or retire) compound over a full career. Correct for a *defensive-only* projection.
- **PCA vs Witt** captures the program: PCA is elite *now* but CF ages hardest (Part 4) and migrates to a corner (Part 5), so his career defensive value (40) trails Witt's (77) despite similar current talent — the projection rewards positions that *hold* their value.
- **Uncertainty is large and honest** (Witt [14,149]) — career defensive value depends on longevity × aging × migration, all stochastic. The right output is a distribution, not a point.

## Assumptions / caveats (v1)
- **Defensive value only** — no offense. A full Career+ would net this against offensive aging/survival; catchers would shift (offense-light) and the M11-A survival economics would gate playing time. The hook to offense is the survivorship layer (M11-A): a premium defender clears a lower offensive bar, so his *defensive* career is less likely cut short — a refinement for v2.
- Exit hazard is by age only (not talent) → elite defenders likely last longer, so top projections are mildly conservative.
- Migration simplified (modal down-spectrum destination; range talent carries unchanged).
- Fixed 0.85 playing-time factor; 10 runs = 1 WAR.
- Right-skewed career outcomes → p10 floors near 0 for high-variance (catcher/CF) profiles.

## v1.1 refinements (CF/PCA review) — `pipeline/18_career_plus_v11.py`
Two fixes prompted by reviewing PCA's CF projection:
1. **Quality-conditioned migration.** v1 used a flat position move-rate; but Part 5's retention model shows defensive quality governs staying (CF bad-glove 38% → good 77%). v1.1 draws P(stay) each year from the per-position retention logistic conditioned on the player's current OAA-z (DRS-z for catchers). **Elite CF now stay in CF** (Kiermaier/Taylor/JBJ pattern) — PCA **40→56 runs (+40%)**, Rafaela 48→67.
2. **Component-profile OF aging.** v1 aged every CF at the position average. v1.1 scales each OF's aging slope by their jump-component value profile (Part 4: burst ages fast, reaction/route durable). **PCA's elite defense is *burst* (98–99th pct), the fastest-aging component → multiplier 1.07 (no slow-aging bonus)**; a reads/routes CF (e.g. Rafaela, 0.92) ages slower. The honest finding: an athleticism-CF (PCA) is *not* a slow-aging glove despite staying in center — only an instincts-CF is.

(Also fixed: catchers have no OAA → retention now fit on DRS, their real quality metric; Bailey 134→106, between the over-sticky and under-retained extremes.) v1.1 board: Bailey 106 / Witt 79 / Hayes 75 / Rafaela 67 / PCA 56.

## This closes the program
Career+ answers all five "final goal" questions — how good now (Part 2), in 5 years (Part 4), at what position (Parts 5–6), how certain (CI throughout), and total career value (this) — for any current MLB defender, and (via Parts 6–7) for prospects through the MiLB translation + scouting priors.

## Files
- `pipeline/17_career_plus.py` → `reports/17_career_plus.csv`
