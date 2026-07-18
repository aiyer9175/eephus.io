# eFV improvement sweep — pre-registered gates (2026-07-18)

Registered BEFORE any arm was run (program rule). Lab: `tools/efv_improve_sweep_lab.py`.
Artifact: `data/xfv_improve_sweep_eval.json`. Loser or winner, the result is committed.

## Vintage caveat (binding on every verdict below)

This machine does not hold the canonical `prospects.db` (the 07-16 seed lives on the
production box); `data/xfv_{hitter,pitcher}_matrix.json` were restored from git
`13d7728^` — the **2026-07-14 post-label-repair, pre-2024-fold-unlock** vintage
(hit 2,052 rows / pit 2,039). Cohort flags (`is_ifa`/`is_college`) come from the
matrix rows themselves (no DB join); `career_war`/acquisitions joins are unused.
Baselines are recomputed at THIS vintage, so within-sweep comparisons are
self-consistent — but **every PASS is PRELIMINARY**: re-run the lab against the
canonical matrix (box or seeded dev env) before any ship that changes a served
number. Arms that are eval-measurement-only (E-FWDCAL, E-HURDLE) may commit their
artifacts immediately since they alter no served output.

Blend lambda is HELD FIXED at the shipped live stamps (hit 0.70 / pit 0.61) for
every arm, so arm effects are not confounded with lambda re-selection.

Identity noise floor: measured per side by the duplicate-feature identity arm
(`fv_dup` = fv appended); floor = |rho(identity) − rho(base)|.

## Arms

### E-FWDCAL — forward-chained per-fold output calibration (eval-measurement)
- Mechanism: within each forward fold, fit linear calibration (target ~ a + b·pred)
  on TRAIN rows only; apply to the fold's test predictions for the ridge and blend
  legs (`ridge_fwdcal`, `blend_fwdcal`). Leakage-clean (train-only fit), unlike the
  LOFO diagnostic. Production already applies a full-window linear calibration when
  scoring live (`fit_production_stack`), so this leg measures the production-shaped
  quantity; the current eval's raw legs are the mismatch.
- Gate (per side): (1) `blend_fwdcal` MAE < consensus baseline MAE; (2) `blend_fwdcal`
  Spearman > consensus baseline Spearman; (3) `blend_fwdcal` Spearman ≥ blend Spearman
  − 0.002. All three ⇒ the dual-gate `rank_win` flips honestly via measurement
  plumbing; ship = add the leg to `efv_model._run_eval` + re-register what "blend"
  means in the verdict block. Fail any ⇒ committed loss, raw legs stand.

### E-RECENCY — recency-weighted training (fit-population change)
- Mechanism: train sample weight ×= decay^(max_train_year − decision_year),
  decay grid {0.95, 0.90, 0.85, 0.80}. Attacks the measured pattern that the blend
  loses to consensus on ≤2018 eras while winning 2019+ (scouting improved).
- Gate (per side, best single decay, chosen by pooled rho — grid disclosed): (1)
  pooled OOS Spearman ≥ base + max(0.005, 2× noise floor); (2) within-tier wm ≥
  −0.003; (3) t45 ≥ −0.003; (4) no era cell down > 0.010; (5) ≤1 of 4 per-year
  folds down. Per-side ship permitted (age-feature precedent). PRELIMINARY only —
  requires canonical-vintage re-gate before touching `_fit_ridge` call sites.

### E-IPCW — inverse-probability-of-censoring training weights
- Mechanism: fit on RESOLVED rows only, weighted 1/P(resolved | decision-year band
  × FV band), probabilities estimated within-fold from train rows only, weight cap
  5.0 (`_SF_IPCW_CAP` program standard). Replaces the observed-fraction weighting
  of censored rows with the classical IPCW estimand.
- Gate: same 5 clauses as E-RECENCY. PRELIMINARY only.

### E-STACK — forward-chained OOF stacking (one attempt; model-class sweep adjacency
  disclosed: the sweep's verdict was "nothing beats the shipped ridge", so this gets
  exactly one pre-registered attempt)
- Mechanism: for fold year Y, inner-forward-chain over train years to build OOF
  (ridge, lgbm, comps) → target rows; fit non-negative meta-weights (coarse simplex
  grid, step 0.05, deterministic); apply to test-year predictions from full-train fits.
- Gate (per side): pooled ≥ base_blend + 0.0046; wm/t45 ≥ −0.0023 (the sweep's own
  bars). PRELIMINARY only.

### E-HURDLE — two-stage full-pool head: P(contributor) × E[WAR | debut] (new
  measurement surface; does NOT alter the flagship debuted-frame rank)
- Mechanism: stage 1 = hand-rolled L2 logistic on the lean features, label =
  target_censored ≥ 3.0 (contributor), trained on the full pool (debuted + busts);
  stage 2 = the shipped ridge fit on debuted train rows; head score = P × E.
  Forward-chained on the full_pool_km frame.
- Gate: (1) full-pool pooled Spearman ≥ shipped blend + 0.005; (2) full-pool
  contributor-AUC ≥ blend AUC + 0.005; (3) full-pool Spearman ≥ consensus baseline.
  Pass ⇒ candidate ordering head for full-pool surfaces (trade-machine useful-asset
  ordering; board rank unaffected) — owner decision to wire; artifact-only now.

## RESULTS (2026-07-18, artifact `data/xfv_improve_sweep_eval.json`)

**All five arms FAIL their gates on both sides. All losses committed.** Identity
noise floors measured: hit 0.0020, pit 0.0008. Local-vintage blend baselines:
hit ρ 0.3514, pit ρ 0.2822 (vs shipped-artifact 0.3787/0.302 — the expected
vintage gap; comparisons within this sweep are self-consistent).

| arm | hit | pit |
|---|---|---|
| E-FWDCAL | rho>baseline ✓ but MAE still loses + rank cost −0.002+ → FAIL | rho>baseline ✓, tolerance ✓, MAE still loses → FAIL |
| E-RECENCY | best decay Δρ −0.0017 → FAIL | Δρ −0.0046 → FAIL |
| E-IPCW | Δρ −0.0205 → FAIL | Δρ −0.0018 → FAIL |
| E-STACK | Δρ −0.0352 → FAIL | Δρ −0.0034 → FAIL |
| E-HURDLE | ρ −0.0042 (fail) but **contributor-AUC +0.0193 vs blend** | ρ +0.0061 ✓ but AUC +0.0017 (fail), loses to consensus |

Reading: a fourth independent confirmation (after E-LEAN1 ×2 and the model-class
sweep) that the current matrix vintage is at its trainable-data ceiling for pooled
rank — now extended to fit-population reweighting (recency, IPCW), stacking, and
per-fold calibration plumbing. The MAE half of the dual gate does not close even
with leakage-clean forward calibration: the spread eFV predicts is intrinsic.

**Ledger note (no re-gate without new authority):** the hit-side hurdle head's
+0.0193 full-pool contributor-AUC with no rank gain is the one live signal. Per
the anti-gate-shopping rule this sweep does NOT re-gate it as an AUC-only ship;
a future AUC-only application (e.g. trade-machine useful-asset ordering head)
requires fresh owner-signed pre-registration at the canonical matrix vintage.
The genuine capacity unlocks remain the time-gated calendar: resolved 2024+
cohorts and E-STUFF at the 2025 fold.

## Do-not-retry check (ledger sweep performed pre-registration)

None of the five arms re-opens a closed line: whole-distribution calibration
(E-ISO*) is untouched (E-FWDCAL calibrates the MEAN of a rank leg, not the bucket
simplex); per-cohort λ/coefficients untouched (E-RECENCY/E-IPCW are global weight
changes); feature additions untouched (no new features anywhere); the model-class
sweep's residual-target loss is not re-run (E-HURDLE decomposes the estimand, not
the target; its frame is full-pool, which the sweep never targeted). F-SIDE S1–S5
apply to any eventual ship; the S-gate check runs at canonical-vintage re-gate time.
