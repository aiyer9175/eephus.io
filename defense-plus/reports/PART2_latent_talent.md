# Defense+ — Part 2: Latent Defensive Talent
Date: 2026-06-16 · Module 04 (range factor, the proof-of-concept)

## Setup
Range is the universal, highest-value defensive skill (all positions but C) and has three
noisy indicators of the *same* thing: **OAA** (Statcast), **rPM** (DRS plus/minus), **RngR**
(UZR range). They correlate 0.45–0.69 — shared enough for a common factor, disagreeing
enough that combining denoises. Sample: 844 player-position-seasons (SS/2B/3B/CF/LF/RF,
Inn≥400, 2021–2025), z-scored within position-year.

## 1. Measurement model — variance decomposition
Single common factor:

| indicator | loading | communality (shared) | uniqueness (metric-specific) | Part-1 Rel |
|---|--:|--:|--:|--:|
| OAA  | 0.67 | 0.45 | 0.52 | 0.83 |
| rPM (DRS) | 0.96 | 0.92 | 0.05 | 0.71 |
| RngR (UZR) | 0.68 | 0.46 | 0.51 | 0.46 |

- **Mean communality 0.61** = variance shared across all three ≈ a *ceiling* on true-talent share. OAA and UZR each carry ~half their variance as metric-specific (method + noise) that the latent strips out. DRS-range sits "central" (shares the most with both).
- **Caution:** shared variance still contains shared *confounds* — positioning, park, opportunity quality inflate all three identically and survive in the common factor. 0.61 is signal **+ shared confound**, not pure talent. Peeling those out is Part 3, not solvable by combining metrics.

## 2. Out-of-sample validation (the actual test)
Does a combined estimate predict next-year range better than any single metric? n=351 season pairs (Inn≥400 both years). Correlation of estimator_t with next-year targets:

| estimator_t | next OAA | next rPM | next RngR | next AVG(3) |
|---|--:|--:|--:|--:|
| OAA | **.488** | .361 | .307 | .452 |
| rPM | .353 | **.456** | .352 | .454 |
| RngR | .241 | .318 | **.376** | .365 |
| equal-weight | .425 | .447 | .408 | .500 |
| **reliability-weighted** | .448 | .450 | .397 | **.506** |
| factor score | .370 | .461 | .366 | .468 |

**Reliability-weighted composite wins: r=0.506 vs best single (rPM) 0.454 → +11.6%.** It predicts each metric's own future about as well as that metric predicts itself (.448 vs OAA's .488; .450 vs rPM's .456) *and* beats UZR at predicting future UZR (.397 vs .376) — i.e. combining is never meaningfully worse on home turf and much better on the broad future. Thesis validated: estimate talent, don't reproduce a metric.

### The method surprise
**Factor analysis (0.468) LOSES to the simple reliability-weighted average (0.506).** FA chases *shared* variance, so it over-weights the "central" metric (loading 0.96 on DRS) and discards OAA's independent signal. The reliability weighting — straight from Part 1 (OAA 0.83 > DRS 0.71 > UZR 0.46) — deliberately keeps the most-reliable metric's signal. Same lesson as the projection engine's "full prior stack overfits": the principled simple weighting beats the fancier latent extraction. **Recommendation: reliability-weighted composite, not factor analysis, for combining same-skill indicators.**

## 3. Shipped — 2025 latent range talent
`reports/04_range_talent_2025.csv`: reliability-weighted composite, shrunk toward 0 by innings (rel = Inn/(Inn+269), Part-1 OAA stabilization), with per-player posterior SD. 2025 used OAA+DRS only (**UZR/RngR not yet published for 2025 — publication lag; another mark against UZR**). Top 10 (Hayes, M.Garcia, Hoerner, Rafaela, Crow-Armstrong, Kwan, Witt) are all consensus-elite gloves → face-valid.

## Recommended Part-2 framework (emerging)
Per position, per skill domain: **reliability-weighted composite of that skill's indicators** (weights ∝ Part-1 reliability), shrunk by exposure, uncertainty = √(1−rel)·σ.
- Range (done): OAA + DRS-rPM + UZR-RngR
- Arm (next, OF): rARM + UZR-ARM + Savant arm-strength(mph); (IF): Savant arm-strength
- Double play (IF): DRS-rGDP + UZR-DPR
- Framing/blocking/throwing (C): CFraming/Savant-RV + pop time + blocking
- Errors/hands: ErrR + rGFP
Then combine skill composites → total positional Defense+ talent via run-value weights (+ positional adjustment for cross-position comparison).

## Module 05 — other skill composites: the rule is CONDITIONAL
Same reliability-weighted template applied to arm / double-play / errors / catcher. OOS lift of composite vs best single indicator:

| Skill (pos) | indicators (reliability) | composite vs best single |
|---|---|--:|
| Range (IF+OF) | OAA .83 / rPM .71 / RngR .46 | **+11.6%** |
| Catcher framing | CFraming .63 / Savant rv_tot .62 | +0.9% |
| Errors | ErrR .29 / rGFP .12 | +3.2% |
| Double play (IF) | rGDP .22 / DPR .17 | −2.1% |
| Arm (OF) | arm-strength .85 / rARM .33 / ARM .14 | −1.7% |
| Catcher throwing | pop time .76 / rSB .19 | −1.6% |

**Combining only helps when indicators are comparably reliable AND semi-independent** (range). The framework is conditional:
- **One tool dominates** (arm-strength mph .85, pop time .76) → just use the tool; adding noisy run-metrics hurts.
- **Two redundant reliable measures** (the two framing metrics) → either works; composite ≈ marginal.
- **All indicators noisy** (DP rel ~.2, errors ~.2) → low OOS ceiling (~.20); these skills are only weakly persistent → estimate with heavy shrinkage, expect little.
Range was the special case that motivated the prompt's "combine metrics" thesis; it doesn't generalize uniformly.

## Module 06 — total positional Defense+ talent (capstone)
Blend the two independent total-defense systems + range: **OAA + DRS + FRP**, reliability-weighted, shrunk by innings, → runs + positional adjustment. Pooled total-system reliabilities (Inn≥300): **FRP .52 > OAA .47 > DRS .40** (Statcast FRP is the most reliable single *total* system).

- **OOS:** Defense+ blend r=0.496 vs best single (FRP) 0.475 → **+4.4%**. Smaller lift than range (+11.6%) because the total systems partially overlap — FRP already contains OAA, so they're less independent. Honest: combining pays off in proportion to indicator independence.
- **Shipped `06_defense_plus_2025.csv`** — cross-position talent in runs (position-relative `dplus_runs` + positional-adjustment `dplus_total`), per-player SD. Top 2025: Bailey (C, +28), Kirk (C), Witt (SS), Hayes (3B), Rafaela (CF), Crow-Armstrong (CF), Winn (SS), Hoerner (2B) — all consensus-elite gloves → face-valid.

## PART 2 — STATUS: COMPLETE
Latent talent estimable per skill via reliability-weighted composites (conditional on indicator independence), combined into a validated total positional Defense+ talent (runs + uncertainty). Recommended method = **reliability-weighted composite, not factor analysis**. The variance-decomposition question (team/park/positioning share) remains gated by Part 3 — the *shared confound* no metric-combination can remove.

## Files
- `pipeline/04_latent_range_talent.py`, `reports/04_range_oos.csv`, `reports/04_range_talent_2025.csv`
- `pipeline/05_skill_composites.py`, `reports/05_skill_composites.csv`
- `pipeline/06_total_defense_plus.py`, `reports/06_total_oos.csv`, `reports/06_defense_plus_2025.csv`
