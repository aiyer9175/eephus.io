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
| **Contact+** | whiff | 0.625 | 0.707 | **+0.082** | **PASS — upgraded (v2 shipped)** |
| **Contact+** | K% | 0.530 | 0.562 | +0.032 | ↑ part of v2 |
| **Swing+** | EV90 | 0.527 | 0.595 | +0.068 | PASS-signal / **not housed here** (see below) |
| **Swing+** | ISO | 0.234 | 0.240 | +0.007 | no gain |
| **B2B+** | xwOBAcon | 0.086 | 0.286 | **+0.200** | standalone PASS / **framework-redundant** |
| **Decision+** | BB% | 0.403 | 0.387 | −0.016 | **REJECT** |
| **Decision+** | wOBA | 0.022 | 0.007 | −0.015 | **REJECT** |
| **DC+** | ISO | 0.035 | 0.106 | +0.072 | standalone PASS / framework-redundant |

*(Numbers re-verified after fixing a stand-split duplicate-row bug in the audit join —
all verdicts unchanged; see Reproducibility note.)*

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
year, shrunk K=150 swings. **Champion vs challenger:** next-whiff r −0.846 (v2) vs −0.793 (v1);
next-K% −0.773 vs −0.761. 1,479 player-years scored incl. **463 direct-2026** (no calibration
detour needed — collision data is live for 2026). Face validity: top = Arraez 127, Simpson 125,
Hoerner 123, Kwan 120; bottom = Murakami 84, Raley 84, Kurtz 86.

Boards carry `contact_axis` = v2 with v1 fallback.

## Addendum: DCV+ (Damage Conversion+) as 5th Hitter+ axis

**Experiment:** dcv-axis-2026-06-10 · external damage-geometry framework
(`~/damage_conversion_plus`, dcv_plus = pull-air 0.20 / spray 0.02 / HR-window 0.13 blend).

**Pre-registered concern (cannibalization):** DCV+ correlates 0.92 with shrunk pulled-air
rate — if B2B+ already proxies pull-air, the OPS-optimal DCV+ weight should collapse to ~0.
**Result: no cannibalization.** corr(B2B+, pull-air) = **−0.14** (B2B+ carries no pull-air
info; Swing+ only +0.22), and DCV+ holds a healthy weight.

- Axis orthogonality: DCV+ vs Swing+ +0.21, Decision+ +0.13, B2B+ −0.08, Contact+ v2 −0.12.
- **5-axis OPS weights: Swing 0.31 / Dec 0.16 / B2B 0.23 / Contact 0.17 / DCV 0.13** (n=749).
- Gains (5-fold CV r): same-season ISO 0.69 → **0.81**, OPS 0.65 → **0.69**;
  next-ISO 0.58 → **0.64**, next-OPS 0.50 → 0.51, next-K% 0.79 (unchanged). Verdict: **PASS — shipped.**
- 2026 coverage: `dcv_2026.py` replicates the framework's raw damage-geometry rates from
  raw Statcast (replication r = 1.000 on pulled-air/pulled-barrel/HR-window), calibrates
  dcv_plus ~ shrunk rates (2023-25, **R² = 0.985**), predicts 2026 (397 hitters, K=100 BIP
  shrink). 2026 top: Torkelson, Y. Álvarez, Schwarber — the pull-air board, as expected.

## Reproducibility note (2026-06-10)

The original audit joined the season leaderboard without collapsing stand-split rows,
duplicating ~8% of pairs (and contact_v2 scores). Fixed in `collision_audit.build()`
(groupby-mean to one row per batter-year) + de-dup in `bat_to_ball._v2()`; boards rebuilt
at original grain (3,028 / 2,194 / 836 rows). All audit numbers above are post-fix;
every verdict was re-verified and unchanged.

## Summary

| Model | Improved by new data? |
|---|---|
| Swing+ | Signal exists (+0.068 EV90 standalone) but rejected for inclusion — redundant with deployed features, retrain risk > benefit |
| Decision+ | **No** (negative ΔR² — collision is post-swing) |
| Contact+ | **Yes — upgraded to v2** (+0.082 OOS whiff R², next-whiff r −0.79 → −0.85) |
| B2B+ | Standalone yes (+0.200 xwOBAcon) but framework-redundant (+0.010 beyond all 5) — external artifact left unchanged, documented |
| DC+ | Standalone +0.072 ISO, framework-redundant (+0.001) — unchanged |
| Hitter+ | **5-axis**: + Contact+ v2 and DCV+ (0.31/0.16/0.23/0.17/0.13); ISO r 0.69→0.81, next-ISO 0.58→0.64 |
