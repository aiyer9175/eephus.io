# MiLB → MLB Defense+ Prospect Prior (assembles Parts 6 + 7 + 8)
Date: 2026-06-20 · `pipeline/26_prospect_prior.py`

Combines the three pure-defense prospect signals into one per-prospect projection — the one part of the system that's useful **without offense** (you're projecting a glove, not a career):
- **Position history** (Part 6 — does he hold the position through AAA?)
- **Scouting grades** (Part 7 — field/speed → MLB range)
- **Frame** (Part 8 — frame → position retention + aging)

Trained on 214 graduated players (prospect-era inputs → realized MLB OAA), applied to current prospects.

## Key result — the signals divide cleanly: grade → quality, frame → position
**Quality** (projected MLB OAA-z), 5-fold CV R²:
| features | CV R² |
|---|--:|
| field grade only | **+0.046** |
| + speed | +0.038 |
| + frame (BMI, height) | +0.029 |

**The field grade is the workhorse; speed and frame do NOT add OOS** — scouts already bake frame into the field grade, so adding it as a separate feature only adds noise. (coef: +0.34 OAA-z per +10 field grade.)

**Position retention**, by contrast, is where **frame dominates**: in the hold model, BMI coef −0.19 (heavier → lower hold) while field grade ≈ 0. So:
> **grade tells you how good a defender he'll be; frame tells you where he'll stay.**

## Output — per-prospect Defense+ prior
- **`defense_plus_prior`** (100±10) = projected MLB defensive quality, field-grade-driven.
- **`p_hold`** = P(holds his premium position), **position-aware**: Part-6 base rate (C 0.92 sticky / SS 0.57 / CF 0.70 / 2B 0.56) + Part-8 frame penalty for SS/CF only (−0.022 per BMI pt; catchers stick regardless, 2B is a landing spot).

Top current premium-position prospects (`reports/26_prospect_prior.csv`, 48 total): Tsung-Che Cheng (SS, field 65 → 106.6, hold .54), Carson Williams (SS, lean → 102.2, hold .62), Alika Williams, Luis Vázquez — all real elite-defense SS prospects; catchers (Marchán, Romo) project as sticky (hold .92).

## Honest limits
- This is a **prior**, not a high-accuracy model — MiLB defense is genuinely low-signal (the Part-6 premise). Quality R² 0.046 is modest; n=214 (quality), small grade-overlap sample.
- Field grade is the only validated quality input; the frame/speed nulls are real (no incremental OOS value over the grade).
- The hold prior leans on Part-6 base rates + a calibrated Part-8 frame term rather than a fitted joint model (the joint hold model had n=30 and mis-handled catchers).

## Files
- `pipeline/26_prospect_prior.py` → `reports/26_prospect_prior.csv`
