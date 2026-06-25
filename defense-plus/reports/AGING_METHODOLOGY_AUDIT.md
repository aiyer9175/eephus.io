# Aging-Curve Methodology Audit (cross-project)
Date: 2026-06-16 · triggered by the survivorship bias caught in Defense+ Part 4

## Question
Do our shipped aging analyses use a survivorship-robust method, or do any repeat the
naive-curve mistake (cross-sectional / uncorrected-delta inflating "ages up")?

## The good news: a gold-standard implementation already exists
`~/mlb-aging-curves/bayesian_curves.py` does it right:
- `fit_hierarchical` — player random intercepts separate within-player aging from cross-sectional ability.
- `fit_joint` — hierarchical longitudinal model **+ a shared-parameter dropout hazard**: it jointly models the skill trajectory and the probability a player exits, sharing the player intercept (decliners drop out faster). This is the proper correction for *dynamic* survivorship — beyond what the delta method or my Part-4 player-intercept model do.
- `export_drift.py` confirms the shipped `aging_drift_estimates.csv` is built from the **joint-dropout** model, and `swing_plus/aging.py` consumes it. **→ Swing+ component aging is sound.**

## Audit table

| Analysis | Method | Survivorship | Verdict |
|---|---|---|---|
| **mlb-aging-curves** → Swing+ | hierarchical Bayesian **+ joint dropout** | **corrected** | ✅ gold standard |
| **swing_plus/aging.py** | consumes joint-dropout drift, ages features then re-scores | inherited correction | ✅ sound |
| **`~/aging_curves/`** (dedicated) | delta method (paired, weighted) | **measured + audited + labeled "survivors only"** | ⚠️ honest, but uncorrected — inferior to the joint model we already own |
| **contact_plus Module 7** ("contact ages UP +7.9/+11.5 by 35") | delta method, **2-yr panel (2023→24, 24→25)**, integrated to age 35 | **gap measured, NOT corrected** | ❌ high risk — the artifact, and self-contradicted |
| **Defense+ Part 4 jump (mine)** | hierarchical (player intercepts), quadratic | partial — **no dropout model** | ⚠️ upgrade to joint-dropout |
| variance_model `07_speed` | sprint speed as skill input | n/a (not an aging curve) | ✅ out of scope |

## The one real problem: "contact ages up" (contact_plus M7)
This is the maximum-risk configuration for the exact bias we caught:
1. **Delta method** — survivor-biased upward at old ages.
2. **Only 2 transition years** (bat-tracking era) integrated out to **age 35** — old-age levels are extrapolated from a handful of positively-selected survivor deltas.
3. **Survivorship measured but not corrected** (just a stayer-dropout gap).
4. **Self-contradiction:** the dedicated `~/aging_curves/` project independently concluded **"contact ages up = survivorship artifact"** and rejected contact aging — yet contact_plus still ships "contact ages UP (PASS)" and (per its docs) feeds a Contact+ "next-year" projection. If that projection ages contact *upward*, it propagates a survivorship artifact into live projections.

**Not claiming the true effect is zero** — contact may genuinely age up modestly (older hitters trade power for contact). The claim is the *magnitude and method are unreliable* and contradicted by our own better analysis. Only the joint-dropout model settles direction + size.

## Recommendations (priority order)
1. **Re-run Contact+ aging through `mlb-aging-curves` `fit_joint`** (dropout-corrected). Reconcile the contact_plus ↔ aging_curves contradiction; if the corrected curve flattens, fix any Contact+ projection that ages contact upward. *(Highest value — a shipped finding likely wrong.)*
2. **Upgrade Defense+ Part 4 jump aging** to the joint-dropout model (currently player-intercept only). Burst/OAA declines may be even steeper once dynamic dropout is modeled (survivors understate decline).
3. **Make `mlb-aging-curves` `fit_joint` the standard** for all future aging (Part 4 general-position, Part 5). Stop using uncorrected delta curves.
4. `~/aging_curves/` delta curves are labeled honestly (survivors-only) — lower priority, but re-running through the joint model would tighten the "mean reversion vs aging" conclusions.

## RESOLUTION (re-runs, 2026-06-16)
- **contact_plus M7 "contact ages up" → REFUTED.** Re-fit with `fit_joint_dropout`: Contact+ 27→33 = +0.35 (band [−1.4,+2.0]) vs the delta-method +7.9; the definitive long-history K% test (2000–2026, 6,057 seasons) shows contact 27→33 = +0.01 (flat-to-slightly-worse, not improving). `~/aging_curves` was correct. → fix Contact+'s next-year projection so it doesn't age contact upward. (`contact_plus/reports/module_07b_aging_joint.md`)
- **Defense+ Part-4 jump aging → already sound.** Joint-dropout reproduced the player-intercept curves within 0.02 SD (burst −0.61 vs −0.62, OAA −0.54 vs −0.55); `gamma`>0 confirms survivorship exists but the 10-yr panel already identified the within-player curve. The naive bins were the only real error. (`defense_plus/pipeline/10_jump_joint_dropout.py`)
- **Lesson:** the joint-dropout correction moves the answer materially only when the panel is SHORT (contact, 3 yr) — with a deep panel (jump, 10 yr) the player-intercept model suffices.

## One-line answer
We are NOT uniformly making the mistake — the best method (joint-dropout Bayesian) already exists and powers Swing+. But **contact_plus Module 7's "contact ages up" is a delta-method survivorship artifact** that contradicts our own dedicated aging project, and my Part-4 jump aging needs the dropout upgrade. Both should be re-run through `mlb-aging-curves/fit_joint`.
