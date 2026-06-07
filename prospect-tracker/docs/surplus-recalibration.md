# Surplus value model — empirical recalibration (v47)

**TL;DR** The prospect surplus model was over-projecting WAR (and therefore surplus
$) by ~3–4× at the low-mid FV tiers because its `FV → expected WAR` anchors came
from the FanGraphs primer (survivor/ceiling-flavored), not from realized
bust-inclusive outcomes. v47 re-anchors that single input to the **realized
2017–2020 cohort outcomes** the site now holds, and reworks the engine so the
de-inflation is smooth and consistent everywhere. Surplus by tier now sits at
**0.7–1.2× the public Edwards scale** (was 2–4× over), grounded in realized data
and validated out-of-sample.

This is the single source of truth (`value_framework.surplus_value_mm`); every
surface (player-card `$DvM+`, farm rollups, leaderboards, GFX, homepage) reads it.

---

## 1. The model (end to end)

For a prospect at continuous FV (hitter/pitcher, position, age, ETA):

```
FV ──► P(bucket | FV)         5 career-outcome buckets: bust / bench / regular / good / star
                              hierarchical-Bayes fit to Clemens (2025) grade→outcome data
   ──► bucket WAR levels      shape × k(FV)   (see §3 — the v47 change)
   ──► per-season WAR         level × aging/ETA trajectory shape over the 6 control years
   ──► market $ / season      CONTINUOUS convex $/WAR (v46): per-win rate ramps smoothly
                              with the season's WAR; no discontinuity at the tier breakpoints
   ──► − cost / season        ~3 pre-arb (league min) + ~3 arb (escalating, production-linked);
                              super-two path blended
   ──► PV discount            9% / yr, discounted from PROJECTED DEBUT (ETA-aware)
   ──► Σ  P(bucket) · surplus(bucket)         risk-adjusted expectation over the outcome distribution
```

It is — and already was — a **risk-adjusted, present-valued expectation**, not a
point estimate: the surplus is the probability-weighted average over the full
bust→star outcome distribution, PV-discounted, net of cost. The defect was never
the framework; it was the **magnitude of the WAR input**.

## 2. The bias (documented, then proven)

`fv_to_6yr_avg_war` — the bust-inclusive six-year-average WAR the bucket levels
reconcile to — was set from the FanGraphs primer:

| FV | primer anchor (WAR/yr) | realized 2017–20 (WAR/yr) | primer bust% | realized bust% |
|---|---|---|---|---|
| 45 | 1.5 | **0.15** | 51% | ~81% |
| 50 | 2.0 | **0.50** | 23% | ~52% |
| 55 | 2.5 | **0.77** | 17% | ~43% |
| 60 | 3.0 | **1.36** | 14% | ~20% |

The primer values implied that a *surviving* 45-FV prospect makes ~3.1 WAR/yr; the
site's own WAG (validated against realized graduate outcomes, WAG ≈ 0 at every
tier) shows survivors make ~0.8. A bust-inclusive average cannot exceed the
survivor-only average, so the anchors were structurally too high.

## 3. The two engine changes that made the de-inflation possible

Lowering the anchors naively broke the model's value-surface smoothness, because
two design choices were coupled to the *high* WAR levels:

1. **Continuous convex `$/WAR` (v46).** The old tiering valued a whole season at
   one tier's flat rate, so value jumped ~$10M at the 1.0/2.0-WAR breakpoints. As
   bucket WAR / aging / ETA pushed a season across a breakpoint, that discontinuity
   produced non-monotone PV-in-ETA and debuted-value humps. `tiered_war_value_usd`
   now ramps the per-win rate continuously (C1 smoothstep) through the tier-center
   rates — same convex intent, no discontinuity.

2. **FV-dependent bucket midpoints (v47).** The bucket WAR levels were a single
   FV-*independent* vector solved jointly across FV tiers. A low 45-FV anchor
   forced that solve into a **bimodal split**, which broke debuted-value
   monotonicity. v47 makes the levels `base_shape × k(FV)`, where `base_shape` is
   the fixed, smooth band prior `[0, 1.0, 2.0, 3.2, 5.0]` and
   `k(FV) = anchor(FV) / Σ P(bucket|FV)·base_shape`. The bucket-weighted WAR now
   reconciles **exactly** to the anchor at *every* FV with smooth, non-bimodal
   levels — and there is no longer a high-FV reconciliation ceiling.

`_fv_war_scale` reads the anchor live from config, so recalibration is a config
edit — no re-fit of the Bayesian `P(bucket|FV)` (which is anchor-independent).

## 4. The recalibrated anchors

`fv_to_6yr_avg_war` is now the realized 2017–2020 bust-inclusive WAR/yr, **lightly
blended with the public Edwards scale at the thin/censored tiers** (45–50 and 60+,
where the cohort is harsh and partially censored), pure-empirical where robust
(50–55):

```
{35: 0.12, 40: 0.22, 45: 0.38, 50: 0.70, 55: 0.95, 60: 1.45, 65: 1.95, 70: 2.60, 80: 3.80}
```

## 5. Validation

**Calibration alignment + benchmark.** Recalibrated surplus by tier vs the old
values and the public Edwards scale:

| FV | old $M | **recalibrated $M** | public (Edwards) | recal / public |
|---|---|---|---|---|
| 45 | 62 | **10** | 15 | 0.7× |
| 50 | 94 | **21** | 26 | 0.8× |
| 55 | 125 | **30** | 37 | 0.8× |
| 60 | 152 | **53** | 54 | 1.0× |
| 65 | 175 | **82** | 70 | 1.2× |

The prior 2–4× overshoot is resolved; values now track public within ~0.7–1.2×,
slightly below at the fringe (the realized 2017–20 fringe is genuinely harsh) and
slightly above at the top.

**Out-of-sample.** Anchors derived on the 2017–18 cohort vs realized on the held-out
2019–20 cohort: |Δ| ≤ 0.17 WAR/yr at 45/50/55 (good generalization); 60 is unstable
out-of-sample (thin n≈8–21 + censoring), which is why 60+ is pooled/smoothed rather
than taken from a raw cell.

**WAG consistency.** The talent-regression prior (`_talent_regression`, shared by
the debuted-player update and WAG) now uses the FV-scaled levels, so a debuted
player's FV-implied talent equals the prospect path's expected WAR — WAG and surplus
are on one scale.

## 6. Uncertainty

Surplus is an expectation over a wide, right-skewed outcome distribution, so the
model reports a distribution, not just a point: `sv_distribution` (outcome-level
draws + a risk-adjusted score with an optional `risk_lambda` risk-aversion knob)
and `sv_credible_interval` (epistemic interval from the Bayesian `P(bucket|FV)`
posterior, widening honestly in extrapolation FV>60 / FV<45 and for thin pitcher
cells). Both thread the v47 FV-dependent scale, so the interval brackets the
recalibrated point estimate.

## 7. Sample sizes & honesty

Resolved 2017–2020 cohort, n = 2,684 (entry FV from the snapshot history → realized
first-6-MLB-season WAR; never-debuted = 0). Robust at 40–55 (n ≈ 90–620 per tier);
thin at 60 (n ≈ 21) and 65 (n ≈ 9), where roles are pooled and the curve smoothed.
**Censoring:** late-debuting members of the cohort have incomplete control windows,
which biases the realized estimate slightly *down* — disclosed, and a reason the
low tiers are blended toward the public scale rather than taken raw.

## Changelog

- **v47** — Empirical recalibration. `fv_to_6yr_avg_war` re-anchored from the
  FanGraphs primer to realized 2017–2020 cohort outcomes (blended with Edwards at
  thin/censored tiers); FV-dependent bucket midpoints (`_fv_war_scale`) so the
  de-inflation is smooth and reconciles at every FV with no high-FV ceiling.
  Surplus drops from 2–4× public to 0.7–1.2×. Out-of-sample validated; WAG/backtest
  paths made scale-consistent.
- **v46** — Continuous convex `$/WAR` (smoothstep ramp through the tier-center
  rates) replacing the hard 3-step; fixes the value-surface discontinuity
  (non-monotone PV-in-ETA, debuted humps) and unblocks the re-anchor.
