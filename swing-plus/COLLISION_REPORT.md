# Savant Collision Data — Per-Model Audit Report

**Experiment:** collision-2026-06-09 · **Data:** Savant `bat-tracking/swing-timing-miss-distance`
(2023 ASG → 2026-06-09), 2,241 player-seasons + 3,854 within-season halves ·
**Code:** `savant_collision.py` (pull) → `collision_audit.py` (audits) → `contact_v2.py` (production change) ·
**Owner:** @willclq · Deterministic (no random seeds; CV folds = transition years).

## The dataset

19 features per (batter, season): avg **miss distance**, **perfect/flawed contact %**,
horizontal alignment (tied-up/centered/flailed), **timing** (early/on-time/late, ms),
vertical alignment (over/lined-up/under, in), + engineered biases and entropies.
No missingness above the 25-swing pull floor.

## Reliability (Step 3) — these are real skills

| feature | split-half r | year-to-year r |
|---|---|---|
| collision_entropy | 0.72 | **0.82** |
| flailed % / horiz_bias | 0.74 / 0.75 | 0.80 / 0.79 |
| vert. alignment (over/lined/under) | 0.72–0.74 | 0.74–0.76 |
| perfect % / flawed % | 0.61 / 0.62 | 0.73 / 0.72 |
| miss distance | 0.51 | 0.64 |
| timing (late %, timing_bias) | 0.57–0.65 | **0.45–0.51** (weakest) |

Verdict: **PASS** for everything except the timing-bias family, which is borderline.

## Projectability (Step 4) — strongest year-t → year-t+1 signals (n=908 pairs)

`collision_entropy` → next whiff **0.73**, next K% 0.63, next EV90 **0.49**;
`perfect/flawed %` → next whiff ∓0.68–0.70; `vert_entropy` → next whiff 0.70.
Nothing projects next BB% or next wOBA meaningfully (|r| ≤ 0.18).

## Per-model verdicts (Steps 5, 8, 11) — out-of-sample ΔR², leave-transition-year-out CV

| Model | Target (next yr) | Base R² | +Collision | ΔR² | Verdict |
|---|---|---|---|---|---|
| **Contact+** | whiff | 0.629 | 0.719 | **+0.089** | **PASS — upgraded (v2 shipped)** |
| **Contact+** | K% | 0.530 | 0.562 | +0.032 | ↑ part of v2 |
| **Swing+** | EV90 | 0.462 | 0.521 | +0.059 | PASS-signal / **not housed here** (see below) |
| **Swing+** | ISO | 0.234 | 0.240 | +0.007 | no gain |
| **B2B+** | xwOBAcon | 0.086 | 0.262 | **+0.176** | standalone PASS / **framework-redundant** |
| **Decision+** | BB% | 0.403 | 0.387 | −0.016 | **REJECT** |
| **Decision+** | wOBA | 0.022 | 0.007 | −0.015 | **REJECT** |
| **DC+** | ISO | 0.035 | 0.106 | +0.072 | standalone PASS / framework-redundant |

**Beyond the FULL framework (all 5 model scores as baseline):** whiff **+0.025**, EV90 **+0.037**,
K% +0.008, xwOBAcon +0.010, ISO +0.001, wOBA −0.014, BB% −0.025.
The genuinely *new* information at framework level is contact-frequency projection and a
modest EV90 kicker. Everything else collision "adds" to individual models is information
the framework already carries via other axes.

### Robustness (Steps 9–10)
- Per-fold ΔR² positive in **all 3 transition years** for all three wins
  (Contact+ whiff +0.05…+0.11; Swing+ EV90 +0.02…+0.11; B2B+ xwOBAcon +0.17…+0.19).
- Survives strict thresholds (≥300 swings t, ≥400 PA t+1): whiff +0.099, EV90 +0.076, xwOBAcon +0.202.
- By archetype: positive for contact (+0.144), balanced (+0.094), power (+0.034) hitters; L/R/S all positive.

### Leakage (Step 6): **LOW.** Features are year-t aggregates, targets year-t+1; the
endpoint's own `whiff_rate` column is excluded from features. No identity/derived leakage.

### Causal homes (Step 7)
- Collision geometry is **post-swing contact execution** → belongs in the **Contact / bat-to-ball layer**.
- Its EV90 signal (`vert_entropy`, `flawed %` load *positively* on future EV90) is the
  power-swing signature — aggressive swings miss more but hit harder. That info lives in
  Swing+'s bat-speed features already; per CLAUDE.md we do **not** retrain the deployed
  Swing+ artifact for a +0.04 framework-level kicker (Phase-2 lesson: feature creep there overfits).
- Decisions are pre-swing; collision is post-swing. The empirical REJECT confirms the DAG.

## Production change shipped: Contact+ v2 (`contact_v2.py`)

Ridge on [Contact+ v1, perfect %, flawed %, vert_entropy, lined-up %, over %,
collision_entropy, miss distance] → next-season whiff; score = −prediction, 100±10 per
year, shrunk K=150 swings. **Champion vs challenger:** next-whiff r −0.854 (v2) vs −0.799 (v1);
next-K% −0.736 vs −0.715. 1,616 player-years scored incl. **463 direct-2026** (no calibration
detour needed — collision data is live for 2026). Face validity: top = Arraez 127, Simpson 125,
Hoerner 123, Kwan 120; bottom = Murakami 85, Raley 85, Kurtz 86.

Boards now carry `contact_axis` = v2 with v1 fallback (coverage ↑: season 1,616→1,890 axis rows).

## Hitter+ (4-axis) — weights refit with v2 (Step 14 decision impact)

OPS-optimal weights: **Swing 0.37 / Decision 0.20 / B2B 0.24 / Contact 0.18**
(was 0.35/0.23/0.22/0.20 with v1). Composite performance: same-season OPS r 0.65,
K% 0.88, **next-OPS 0.52, next-K% 0.81** — identical to v1 at the composite level
(documented honestly: the v2 gain lives in the axis, not the blend), and still well clear
of SEAGER (next-OPS 0.34). Coverage: 681 all-time / 1,890 season rows.

## Summary

| Model | Improved by collision data? |
|---|---|
| Swing+ | Signal exists (+0.059 EV90 standalone) but rejected for inclusion — redundant with deployed features, retrain risk > benefit |
| Decision+ | **No** (negative ΔR² — collision is post-swing) |
| Contact+ | **Yes — upgraded to v2** (+0.089 OOS whiff R², next-whiff r −0.80 → −0.85) |
| B2B+ | Standalone yes (+0.176 xwOBAcon) but framework-redundant (+0.010 beyond all 5) — external artifact left unchanged, documented |
| DC+ | Standalone +0.072 ISO, framework-redundant (+0.001) — unchanged |
| Hitter+ | Rebuilt 4-axis on Contact+ v2, weights 0.37/0.20/0.24/0.18 |
