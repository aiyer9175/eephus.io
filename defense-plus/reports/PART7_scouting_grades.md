# Part 7 (core) / Part 6 quality — Do scouting grades predict MLB defense?
Date: 2026-06-18 · `pipeline/16_scouting_quality.py`

## Test
The prompt's bar: grades only earn their place if they beat position + age **out-of-sample**.
Outcome = **within-position** MLB OAA (z-scored within Pos-year, Inn-weighted per player) — so
we test whether scouts see *quality at the position*, which position alone can't encode.
Grades = earliest-snapshot field/throw/speed (prospect-time). n = 214 graded players with MLB OAA.

## Result 1 — correlation with within-position MLB OAA quality
| grade | r |
|---|--:|
| **field** | **+0.29** |
| **speed** | **+0.23** |
| throw | −0.05 |
| FV (overall) | −0.09 |

## Result 2 — OOS incremental (5-fold CV R², predicting within-position MLB OAA)
| features | CV R² |
|---|--:|
| position only | −0.01 *(≈0 by construction — z'd within position)* |
| + debut age | +0.00 |
| **+ field grade** | **+0.05** |
| + field+speed+throw | +0.05 |

**Field grade earns its place** — it adds real OOS signal (R² ~0 → 0.046) over position + age. Magnitude: **+0.40 SD of MLB OAA per +10 field-grade points** (a 60-grade glove vs a 50 ≈ +0.4 SD). Speed adds a touch; throw and FV add nothing.

## Reads
1. **Scouts have genuine, modest defensive signal.** Field grade is a real but noisy within-position quality prior (r 0.29, OOS R² 0.05) — use it, weighted modestly. This quantifies the "treat grades as noisy priors" stance: real, not dominant.
2. **Throw grade ≠ OAA signal** — and that's *correct*: OAA is range, not arm. Throw is an arm grade; it should be validated against **arm strength** (mph), not OAA. So don't read its OAA-null as "arm doesn't matter" — it's the wrong outcome for it.
3. **FV is offense-weighted — never use it as a defensive prior** (r −0.09).
4. **Speed grade carries range signal** (r 0.23) — athletic range translates from the scouting eye.

## Use for Defense+ / MiLB translation
- **Quality prior = field grade + speed grade** (modest weight), on top of the Part-6 position-history viability priors. A prospect's projected MLB defensive quality ≈ position-history viability (Part 6) shaped by field/speed grade (here).
- **Exclude throw (for OAA) and FV** from the range-quality prior; route throw grade to an **arm** sub-model (vs Savant arm strength) instead.

## Caveats
- n = 214, modest; CV R² 0.05 is small and noisy. Direction is robust (field/speed > throw/FV) but treat magnitude as indicative.
- OAA is range-only and single-metric noisy; a DRS/composite quality outcome (and a larger pre-2018 grade backfill) would sharpen it.
- "Earliest snapshot" reduces but doesn't fully eliminate post-prospect updating.

## Files
- `pipeline/16_scouting_quality.py` → `reports/16_scouting_quality.csv`
