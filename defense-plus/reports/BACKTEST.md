# Career+ Backtest — does the integrated projection actually work?
Date: 2026-06-18 · `pipeline/23_backtest.py`

## Era handling (the prerequisite)
Checked first: OAA/DRS are league-relative each year, and the **spread is stable** (all-position OAA SD 7.7→7.2 runs, 2016→2025). League BABIP improved gradually (.304→.294 over the decade; **flat .294→.295 into 2026** — no "light-years" jump). So working in **era-relative runs** is fair, and the "rising bar" is auto-absorbed by the relative metric + the within-player aging curves. No extra era term needed.

## Design
Defenders established (Inn≥600) in a base year (2016–2018; n=4,671 player-base-years). Project their defensive runs to 2025 with the Career+ engine (shrunk base talent + per-position aging + exit hazard + migration). Compare to realized (sum of actual DRS + earned positional value, base+1…2025).

## Results
| metric | result | verdict |
|---|---|---|
| Rank accuracy (Spearman) | **+0.77** | ✅ orders defenders correctly |
| Calibration bias | **−45 runs** (proj −3 vs realized +42) | ❌ systematic under-prediction |
| 80% interval coverage | **31%** | ❌ intervals far too narrow |
| MAE | 102 runs | ❌ large |

By position (proj vs realized): **C +18 vs +205**, SS +28 vs +187, 3B −3 vs +44, CF +0 vs +13, 1B −45 vs −141.

## Diagnosis
- **Ranking works** (rho 0.77) — the relative ordering of defenders is sound. Trust *rankings*.
- **Absolute values are too low** and **intervals far too tight** — do NOT trust the career-WAR magnitudes or CIs yet.
- **Root cause = exit hazard too high for this cohort.** Established starters (Inn≥600) outlast the generic "regular" hazard — they keep playing and banking positional value (a catcher earns +12.5/yr for years), but the model retires them too early. This hits **premium positions hardest** (high posadj × long careers), which is why C/SS are the most under-projected. Steep C/SS aging compounds it.

## Fix list (recalibration, then re-validate)
1. **Talent-conditioned exit hazard** — elite/established players last much longer; this is most of the −45 bias. (Was already an open TODO; backtest confirms it's the priority.)
2. **Widen + re-center uncertainty** — 31% coverage means the MC intervals need real work: add talent-estimate uncertainty and longevity variance, and re-center after fixing #1.
3. Re-run the backtest after each change until calibration (|bias| small) and coverage (~80%) land.

## The deeper cause: defense-only can't calibrate career value (offense governs longevity)
Tested whether the miss is structural to projecting defense without offense. The error vs offense tier (n=4,614):

| offense (wRC+) | n | model error | career PA |
|---|--:|--:|--:|
| bad <85 | 785 | under +40 | 1,302 |
| 85–100 | 2,565 | under +51 | 2,115 |
| 100–115 | 1,152 | under +51 | 3,790 |
| **115+** | 112 | **OVER −123** | 4,658 |

Offense decouples career length from defensive value **two opposite ways**:
1. **Glove-first players (weak bats) under-predicted** — they stick only while the glove holds (defense = insurance, M11-A), banking positive defense; the model retires them too early.
2. **Bat-first elite hitters massively over-predicted (−123)** — they play longest but are kept for the *bat* as their defense craters / they slide to 1B/DH; the model keeps crediting defense they no longer provide.

→ A **defense-only** model structurally cannot calibrate absolute career defensive value: offense determines both who stays long enough to accrue it and who keeps playing despite none. The exit-hazard patch fixes only the glove-first half. **Career+ v2 (offense integration + M11-A survival economics) is the prerequisite for a calibrated value model**, not optional. Ranking (rho 0.77) remains usable today.

## Bottom line
The integrated Career+ is **a good ranking model and a mis-calibrated value model.** Every individual part validated OOS, but assembling them produced a longevity-pessimistic projection with over-tight intervals — exactly the kind of integration error a backtest exists to catch. Use it to *order* defenders today; recalibrate (start with talent-conditioned exit hazard) before quoting absolute career numbers.

## Files
- `pipeline/23_backtest.py` → `reports/23_backtest.csv`
