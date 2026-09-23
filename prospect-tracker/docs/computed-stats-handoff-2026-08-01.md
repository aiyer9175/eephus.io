# Computed-Stat Formulas: Backend Reproduction Handoff

Generated 2026-08-01 from the `prospect-tracker` codebase (branch `main`, HEAD `ab56f7b` at time of trace).
Audience: a backend team reproducing these calculations in a different system, without access to this repo.

**How this document was produced.** Each stat was traced end-to-end by one agent, then every quantitative claim (formulas, constants, thresholds, field names, file paths, artifact formats, baselines) was re-checked against the actual code by an independent adversarial verifier. Each write-up ends with a `### Verification log` listing what the verifier corrected; anything it could not confirm from code is flagged in-line rather than asserted.

**Cross-cutting facts the backend team should know before reading any single section:**

- **Formula vs. fitted model split.** Deterministic formulas (portable as math): `rem_plus`, `sem_plus`, `hem_plus`, `pal`, `collegesavant_plus`, `draft_stock_plus`, and the pStuff+/FVStuff+ variants of `stuff_plus`. Fitted models (must be served/ported as artifacts): `efv`/`xfv` (prior-anchored weighted ridge, refit every run from JSON matrices), `swing_plus` (externally-fitted sklearn ridge pipelines in a committed joblib), tjStuff+ and aStuff+ (LightGBM). Hybrids (deterministic pipeline over fitted components): `wag` and `value_framework` (both lean on the fitted proportional-odds bucket model + FV→WAR anchors in `data/value_framework_fitted.json` and, for dollars, the isotonic calibration in `value_framework_config.yaml`).
- **"+" scaling is NOT uniform.** At least three conventions coexist (see `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md`): bare ratio ×100 (REM+/SEM+), ratio with spread gain (HEM+, gain 2.28), 100+10z (aStuff+, pStuff+, CS+, KRP+…), 100−10z INVERTED (tjStuff+), and linear percentile (Draft Stock+). Never assume one convention generalizes.
- **Baselines are mostly recomputed live per run** (each season's own pool), with named exceptions frozen in artifacts: the `*_3yr` boards (REM+/SEM+/HEM+ trailing-3yr values are frozen lab outputs joined verbatim), Swing+ (train-time mean/SD frozen in the joblib), tjStuff+ (author's static 2024 MEAN/SD), and the value-framework fitted file (fit vintage 2026-06-21 with hand-amended sub-45 anchors — re-running `--fit` reverts them).
- **Python `int(round())` is banker's rounding** and is load-bearing in several served integers; a port that rounds half-away-from-zero will differ on exact .5 values.
- **Two live defects were found during verification** (documented, not patched): (1) `efv_score.py:2066` `run_backgrade` references an unbound name `r` (should be `row`) — a NameError introduced 2026-07-31 that silently kills the backgrade/history/export tail of the eFV regen (the pipeline wrapper swallows the crash), leaving `data/xfv.json` stale relative to the newest scored artifacts; (2) the resolved-seam Platt odds-recalibration call at `efv_score.py:1292` passes a row that never has a `milb` key, so recalibration is a silent no-op for the entire resolved cohort.
- **Trust order when sources disagree:** code > served artifact > `data/model_registry.json` row > `MODEL_REGISTRY.md` > `data/glossary.json` prose. Several glossary/registry entries are one or more vintages stale; each section flags the specific stale claims. Do not implement from the glossary.

## Contents

1. [efv](#efv) and 2. [xfv](#xfv) — one system, two names (single section pair)
3. [rem_plus](#rem_plus)
4. [sem_plus](#sem_plus)
5. [hem_plus](#hem_plus)
6. [stuff_plus](#stuff_plus) — five distinct quantities share the name
7. [pal](#pal)
8. [wag](#wag)
9. [value_framework](#value_framework) — $/WAR and surplus
10. [swing_plus](#swing_plus)
11. [collegesavant_plus](#collegesavant_plus)
12. [draft_stock_plus](#draft_stock_plus)

---


---

# efv

## Name in code & where computed

**In-code names.** The stat is displayed site-wide as **"eFV"** ("eephusFV"); every internal key is prefixed **`xfv_`** (the model program's original name — "xFV flagship model"). There is no separate "efv" number: **eFV (display) == the `xfv_*` keys (code/artifacts)**. Glossary id is `xfv`, term "eephusFV (eFV)" (`data/glossary.json`, entry `id: "xfv"`).

**Production compute sites** (all under `c:\Users\noah\baseball-projects\BaseballR\prospect-tracker\`):

| Stage | File / function | Output artifact |
|---|---|---|
| Training + live feature matrices | `efv_dataset.py` — `build_matrix()` (873), `build_live_matrix()` (1071), `run()` (1186), `build_live()` (1151) | `data/xfv_hitter_matrix.json`, `data/xfv_pitcher_matrix.json`, `data/xfv_live_hitter_matrix.json`, `data/xfv_live_pitcher_matrix.json` (`matrix_path`/`live_matrix_path`, efv_dataset.py:210-216) |
| Model definition, features, blend lambda | `efv_model.py` — `_FEATURES_HIT` (60-144), `_FEATURES_PIT` (145-274), `_vec()` (733-860), `fit_production_stack()` (900-927), `blend_lambda()` (524-556), `wag_calibration()` (375-421), `rank_calibration()` (424-521) | (fits are in-memory; eval artifact `data/xfv_eval.json` / `data/xfv_eval_pitcher.json` via `efv_model.run()` 1836-1938) |
| Core fit primitives | `prospect_path.py` — `_fit_ridge()` (245-309), `_predict()` (312-316), `_fit_linear_calibration()` (398-413) | — |
| Scoring seams (the shipped numbers) | `efv_score.py` — `run()` (1226, resolved cohort), `run_live()` (1671, active board), `run_backgrade()` (1966, graduates/busts/no-track-record), `score_history()` (1487, eFV-over-time) | `data/xfv_scored.json`, `data/xfv_scored_pitcher.json`, `data/xfv_scored_live.json`, `data/xfv_scored_live_pitcher.json`, `data/xfv_backgrade.json`, `data/xfv_history.json` |
| Grade maps + dollars | `value_framework.py` — `outcome_implied_fv()` (2953), `realized_implied_fv()` (2841), `p_bucket_given_fv()` (749), `expected_surplus_usd()` (1443), `sv_distribution()` (1857), `apply_calibration()` (1583) | curve artifact `data/fv_outcome_curves_pooled.json`; fitted odds `data/value_framework_fitted.json` |
| Odds dispersion recalibration | `efv_odds_calibration.py` — `recalibrate_bucket()` (111), `recalibrate_p_bust()` (94) | constants in-module (`_PLATT`, 87-90) |
| Consolidated export | `efv_export.py` — `run()` (83-174), `regen_all()` (300-360), `_entry()` (33-80) | **`data/xfv.json`** (the site sidecar; `OUT_PATH`, efv_export.py:24) |
| Tool eFVs | `efv_tools.py` — `run()`/`run_live()` (spec table `_TOOLS` at 38-44; pass-through disclosure `_PASSTHROUGH` at 46) | `data/xfv_tools.json`, `data/xfv_tools_live.json` (merged into `xfv.json` as `tool_xfv`, efv_export.py:112-118) |

**Production chain.** `run_daily()` (run_monthly.py:860) and the monthly `main()` tail into `rebuild_only()` (run_monthly.py:556), which calls **`efv_export.regen_all()`** (run_monthly.py:741-747). NOTE: that call is wrapped in a best-effort `try/except` ("a failure must not abort the run", run_monthly.py:746-747) — an eFV crash mid-`regen_all` logs and continues, silently leaving every downstream `xfv_*` artifact stale (this is not hypothetical; see discrepancy #2 below). `regen_all` (efv_export.py:300-360) runs, in order: `efv_dataset.run` + `build_live` (both sides) → optional `efv_model.run` (eval, opt-in via `include_eval`) → `efv_score.run` + `run_live` (both sides) → `run_backgrade` → `score_history` → `efv_tools.run`/`run_live` → best-effort `efv_ungraded.build` and `efv_reliability.build` → `efv_export.run()` → `data/xfv.json` → best-effort `_valuation_curve()` (diagnostic `data/xfv_valuation_curve.json`) and `statcast_alevel_export.run()` (re-bakes the A/CPX overlay signal file for the NEXT scoring pass; frozen coefficients, never refit — efv_export.py:346-359). Operational gotcha (memory, consistent with the code layout): only the `rebuild_only` path regenerates `xfv.json`; the heavy monthly steps alone leave it stale.

**Supporting production modules** (all imported by the scoring path): `efv_odds_calibration.py` (Platt odds fix; wiring caveat in discrepancy #3), `efv_factor_groups.py` (display-only collinear-group collapse for the "factors" chips, called from `_factors` at efv_score.py:566), `efv_statcast_line.py` (S-XLINE AAA Statcast expected-stat blend into the MiLB line; flags **ON**: `XLINE_HIT_DEFAULT=True`, `XLINE_PIT_DEFAULT=True`, `XISO_HIT_DEFAULT=True`; blend weights `W_HIT=0.7`/`W_PIT=0.5`; qualification `MIN_SAVANT_PA=100`, `FIRST_TRACKED_SEASON=2023`; measurement-sanity caps `D_CAP_AVG=.050`/`D_CAP_OBP=.050`/`D_CAP_SLG=.100`/`D_CAP_ISO=.060`, ERA multiplier clamp [0.75, 1.25] — efv_statcast_line.py:38-59), `efv_park_line.py` (W2 PARK-LINE MiLB park neutralization pre-rate-conversion, flag-gated, hook at efv_dataset.py:595-598), `efv_statcast_overlay.py` (bounded A/CPX FV lean, `OVERLAY_HIT_DEFAULT=True`/`OVERLAY_PIT_DEFAULT=True` at efv_statcast_overlay.py:87-88; `BETA_FV_PER_RESID_Z=0.6`; clamp `DELTA_CAP_FV=12.0` FV which is a **numerical-safety bound only** — the old 2-FV display cap was REMOVED by the A4 owner directive; max real lean observed 2.36 FV), `efv_topquant.py` (`apply_display_remap` hook — **gated inert**: no-op unless `data/xfv_topquant_eval.json` stamps `ship.enabled` AND `ship.gate_pass`, and the 2026-07-15 eval rejected every candidate; hook sites efv_score.py:1349-1358 and 1897-1902), `efv_board_scale.py` (W-SIDESCALE per-side affine on the board grade — **`ENABLED_DEFAULT=False`**, env `EEPHUS_BOARD_SIDE_SCALE`, disabled 2026-07-29 as a measured NULL; efv_board_scale.py:183; fitted coefficients kept at 193-196: hit `(-2.603487, 1.036284)`, pit `(-0.579380, 1.032470)`), `efv_reliability.py` (diagnostic reliability curves), `efv_ungraded.py` (separate provisional model/artifact `data/xfv_ungraded.json`, NOT the flagship; owns the thin-sample p_bust conditional), `efv_surrogate.py` / `efv_sign_audit.py` (audit lanes), `efv_proxy.py` (separate leading-indicator artifact `data/xfv_proxy_eval.json`, explicitly "NOT eFV", run_monthly.py:775-784). Everything under `tools/efv_*_lab.py` is experimental, not production.

**No frontend recompute.** JS surfaces read `data/xfv.json` fields as-is (eephus-ui.js:305 `latestFv` returns `x.xfv_grade`; trademachine.js:458/471 orders on `xfv_grade`; no JS file reads `xfv_grade_quantile` — verified by grep over `assets/*.js`). Storage's server-side rank uses `BOARD_GRADE_FIELD = "xfv_grade"` (storage.py:4758). The only frontend transformation is rounding for display: **eFV rounds to NEAREST** (`Math.round`, assets/trademachine.js:737-743, assets/fantasy.js:241-242 + 500-502) while consensus FV displays as **CEILING** (`Math.ceil`, assets/eephus-ui.js:310 "FV rounds UP"; trademachine.js:743 falls back to `Math.ceil` on consensus when no eFV). This asymmetry is deliberate and test-pinned (`test_efv_score::test_committed_grades_carry_the_round_to_nearest_signature`, referenced at efv_board_scale.py:285-292); grades are stamped on a 0.1 grid.

**Registry rows**: `data/model_registry.json` → `xfv_hitter` (champion `xfv_hit_v1_lean`, eval `data/xfv_eval.json`), `xfv_pitcher` (`xfv_pit_v1_lean`, eval `data/xfv_eval_pitcher.json`), `xfv_tools` (`xfv_tools_v0`). All three rows are verdict "provisional". **Discrepancy**: the registry notes still say hitter blend "lam=0.9" and pitcher "lam=0.66"; the served lambdas stamped in `data/xfv.json meta.live_lambda` are **hit 0.70 / pit 0.57** (verified live). Spec doc: `docs/xfv-phase1-plan.md`.

## Formula or fitted model?

**A fitted model — but NOT a gradient-boosted / pickled one.** The production scorer is a **prior-anchored linear ridge regression, refit from the JSON matrices on every pipeline run** (no persisted model binary exists; determinism comes from a fixed CV seed and pinned data). LightGBM appears **only as an eval challenger** (`_fit_lgbm_mono`, efv_model.py:930-947, `LGBMRegressor(n_estimators=250, learning_rate=0.04, num_leaves=7, min_child_samples=25, subsample=0.9, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, monotone_constraints=mono, random_state=7, deterministic=True, verbose=-1)`) — the monotone signs in `_FEATURES_*` bind only that challenger, never the shipped ridge (stated in-code at efv_model.py:192-195). Hitters and pitchers are **trained separately** (separate matrices, separate feature sets, separate fits).

**Training target**: first-6-MLB-season summed bWAR (`target_censored`), KM-censored: for a debut year `dy`, sum observed seasons `dy..dy+5` capped at `RESOLVED_THROUGH=2025`; if not fully resolved, project the unobserved tail at the observed per-season rate and weight the row by `n_obs/6` (`_label_6yr`, efv_dataset.py:715-731). Busts (never-MLB) get target 0.0, weight 1.0 (0.5 if last listed ≥2024 — "recent bust", efv_dataset.py:1015-1022; a career-terminal transaction — retirement/ban — restores weight 1.0 and clears `bust_recent`, and resolves a censored debuted row at its observed sum, efv_dataset.py:1044-1063).

**The production fit** (`fit_production_stack`, efv_model.py:900-927, shared by the scorer and the lambda selector): pool = full labeled matrix minus never-MLB recent busts; then

1. **Ridge** (`prospect_path._fit_ridge`, 245-309): features standardized (μ, σ over the training pool, σ=0→1); weighted normal equations `w = solve(Xsᵀ·diag(wt)·Xs + α·I, Xsᵀ·diag(wt)·(y − b))` with intercept `b` = weighted mean of y; sample weights = the KM `weight` column clipped ≥1e-3. α chosen from `_ALPHAS = (1.0, 10.0, 100.0)` (prospect_path.py:73) by 5-fold CV of weighted MAE over a **seeded permutation** (`_RIDGE_HOLDOUT_SEED = 20260707`, prospect_path.py:242, np.random.default_rng). Returns `{keys, mu, sd, w, b, alpha}`. Prediction: `_predict = b + Σ w_k·(feat_k − μ_k)/σ_k` (312-316). Requires ≥40 rows, else None.
2. **Linear output calibration**: OLS `realized ≈ a + b·ridge_pred` over the same pool (`_fit_linear_calibration`, prospect_path.py:398-413; needs ≥50 pairs, else identity `(0,1)`).
3. **Consensus anchor**: OLS `WAR ≈ ols_a + ols_b·consensus_fv_raw` (`_fit_ols_fv`, efv_model.py:881-893; needs ≥8 rows).

Production-stack minimum: ≥60 prepared rows, else None → `RuntimeError` in `efv_score._fit_production` (efv_score.py:1616-1618).

**Per-player scoring (live board, `run_live`, efv_score.py:1671-1959)** — exact sequence:

```python
feats    = _vec(row, side)                                   # efv_model.py:733-860
xfv_war  = max(-2.0, a + b * _predict(ridge, feats))         # model E[6yr summed bWAR] (1701)
cons_war = max(0.0, ols_a + ols_b * fv_effective)            # staleness-decayed anchor (efv_score.py:1708-1710)
rank_war = (1 - lam) * cons_war + lam * xfv_war              # guarded blend (1711)
# live overlay tilts on the MODEL leg only, then blend rebuilt (1751-1773):
adj = injury_factor * statcast_factor * age_factor * role_factor
xfv_war  = _apply_war_tilt(xfv_war, adj)                     # war*f if war>=0 else war/f; floor -2 (877-888)
xfv_war  = max(-2.0, xfv_war + ols_b * xline_overlay_fv)     # S-XLINE-4 additive lean, priced through the
                                                             # consensus OLS slope (1768-1773); lean clamp
                                                             # ±12 FV numerical-safety, typical <= ~2.4 FV
rank_war = (1 - lam) * cons_war + lam * xfv_war
xfv_grade   = vf.outcome_implied_fv(xfv_war, exposure_seasons=6)          # THE board number (1792)
_odds_grade = vf.realized_implied_fv(xfv_war, is_pit, age=_gm_age,
                                     position=pos, exposure_seasons=6)    # odds/dollar seam grade (1793)
probs = _odds_cal.recalibrate_bucket(vf.p_bucket_given_fv(_odds_grade, is_pit), is_pit,
                                     provisional=not (r.get("milb") or {}))  # (1802-1812)
surplus/dist = calibrated vf.expected_surplus_usd / sv_distribution at _odds_grade (1815-1818)
```

(`_gm_age = age + eta + 6` via `_grade_map_age`, efv_score.py:908-922 — vf.expected_war's `age` contract is post-exposure age, so the inversion is placed at expected-debut-age + 6.)

**Blend lambda** (`blend_lambda`, efv_model.py:524-556): hitters are **hard-overridden to 0.70** (`_BLEND_LAMBDA_RESELECT = {"hit": 0.70, "pit": None}`, efv_model.py:332 — the "tree-blend lambda ~0.70" ship, chosen for run-to-run grade stability, not accuracy; revert = 0.85). Pitchers are dynamic: WAG calibration (`wag_calibration`, 375-421 — through-origin weighted regression of realized per-season WAG on eFV's predicted per-season edge `(model_war − cons_war)/6`) is used only if `|spearman| ≥ _WAG_MIN_SPEARMAN=0.10` and `n ≥ _WAG_MIN_N=100` (345-346); currently non-significant on both sides, so pitchers fall to `rank_calibration` (424-521): argmax of pooled + within-tier + FV45-fringe Spearman over a 21-point grid in the band **[0.50, 0.70]** (508-511). Served value: **pit 0.57** (xfv.json `meta.live_lambda`). Fallbacks `{"hit": 0.85, "pit": 0.80}` (317), clamp (0.35, 0.90) (318). Cached per-process in `_WAG_LAMBDA_CACHE`.

**Three grade bases per row — do not conflate:**

1. **`xfv_grade`** (THE board/display number since 2026-07-30, `storage.BOARD_GRADE_FIELD`, storage.py:4758): `outcome_implied_fv(xfv_war)` — piecewise-linear **inverse of the pooled empirical curve E[first-6yr bWAR | consensus FV]** in `data/fv_outcome_curves_pooled.json` (20 knots FV 20→80, values 0.0→27.49 WAR, `curve_hash 6dbe8353f3bb`; value_framework.py:2912-2990). Strictly monotone in `xfv_war`; ≤0 WAR → 20.0; hard error if `exposure_seasons != 6` (2971-2974); not outcome-calibrated below ~FV45 (the sub-floor knots are a shape-preserving re-spread — value_framework.py:2904-2911). A missing/malformed/non-monotone curve raises `OutcomeCurveError` fatally rather than silently falling back (2915-2940).
2. **`_odds_grade`** (internal): `realized_implied_fv(xfv_war, ...)` — inversion of the value engine's own FV→control-window-WAR forward map by 40-iteration bisection on FV [45, 80]; below the FV45 WAR, a concave re-spread `20 + 25·(war/war45)^0.45` (`_LOWEND_FG_EXP = 0.45`, value_framework.py:2838, formula at 2864-2868). Drives `p_bucket`/`p_bust` and the first-pass dollars.
3. **`xfv_grade_display`** (exported as `xfv_grade_quantile`): rank-preserving interpolated quantile map of the pool's `rank_war` ordering (unrounded, player_key tiebreak) onto the pool's own consensus-FV distribution (efv_score.py:1875-1895 live; 1320-1347 resolved), post-processed by the (inert) TOP-QUANT hook and the **active** F-SIDE-FIX joint top-band recalibration (`SIDE_FAIRNESS_FIX_DEFAULT = True`, knee 52.5, per-row move cap ±3.0 FV, PAVA crosswalk with curve min n=20 and terminal-block min n=5 — efv_score.py:1016-1223). **Surplus dollars are re-priced on this grade** (`_reprice_surplus_on_display`, 925-978), overwriting the `_odds_grade` dollars, then passed through the engine's isotonic dollar calibration `vf.apply_calibration` (`_cal_mm`, 891-905; served vintage `isotonic-real-v6-evframe-2026-07-31`, stamped in `xfv.json meta.calibration`).

**Outcome odds**: `p_bucket_given_fv` (value_framework.py:749-771) dispatches on the fitted method; the committed fit is a **proportional-odds (ordered logit)** over 5 buckets [bust, bench, regular, good, star] (`_BUCKETS`, value_framework.py:86 == efv_score.py:436), parameters in `data/value_framework_fitted.json` (hitter cutpoints [7.8969, 8.8989, 10.1683, 12.4166], slope 0.17502; pitcher cutpoints [7.3437, 8.4807, 9.8364, 13.1493], slope 0.16248 — the `proportional_odds`/`map_params` blocks). Because it is fitted on the consensus-FV scale (sd 6.57) but read at `_odds_grade` (sd 15.54, 2.37x wider), a **per-side Platt map in log-odds** corrects the bust mass: `logit(p′) = A + B·logit(p)` with `_PLATT = {"hit": (0.7268, 0.3749), "pit": (0.7269, 0.3553)}` (efv_odds_calibration.py:87-90); the other four buckets rescale so the vector sums to 1 (`recalibrate_bucket`, 111-129; `provisional=True` is a hard no-op reserved for the efv_ungraded thin-sample lane). **Wiring caveat (verified)**: it is genuinely applied on the **live** seam (efv_score.py:1812; the guard is vacuous there because no-milb rows were already skipped at 1697) and the **backgrade** seam (2191, deliberately unguarded — the queue rows never carry a raw `milb` key, comment 2176-2190), but on the **resolved** seam (1292) the guard `provisional=not (r.get("milb") or {})` reads the `_prep` row, which never has a `milb` key (efv_model.py:863-874) — so `provisional` is always True and the Platt map is a **silent no-op for the entire resolved cohort** (`data/xfv_scored*.json` p_bucket/p_bust are unrecalibrated). The registered production guard was `provisional=not src.get("milb")` (tools/_prem_odds.patch:30-31; `data/xfv_odds_recalibration_ship_eval.json` "applied_population ... 906/907 hit and 920/920 pit"), i.e. the shipped line uses the wrong variable. Also, the module docstring's "NOT YET WIRED IN" (efv_odds_calibration.py:4) is stale in the other direction — it IS wired at the live + backgrade seams (comments dated 2026-07-31).

**Provisional (no-track-record) rows** (backgrade + history paths): scored via `_provisional_prior_war` (efv_score.py:95-432) instead of the ridge — `prior = clamp(cons_war + w·pull, war_floor=−2.0, war_ceiling=20.0)`, `pull = clip(slot_war − ref_war, 0, pull_cap_war=1.9)`, `ref_war = max(cons_war, 6·expected_six_year_avg_war(cons_fv))` (with a pinned pre-amendment legacy floor below FV45, `_P1_LEGACY_ANCHOR_WAR_PER_YR=0.19`, efv_score.py:64-92, 346-348), `w = ped/(ped+1)` with pick-tier precision (top-10 0.8 / round-1 (≤30) 0.4 / round-2 (≤70) 0.15 / later 0.05) plus bonus log-trust (`log10(bonus/10_000)·0.5`, ped capped at 3.0) — all constants live in `value_framework_config.yaml` `efv_provisional_prior` (enabled: true). IFA arm: `ifa_step_enabled: true`, bonus ≥ `ifa_step_bonus_usd=1_000_000` uses `ifa_step_war=1.917` with precision 0.25; sub-$1M/missing-bonus IFA rows return `cons_war` unchanged. P1 V3 ARM-A (`EEPHUS_P1_SLOT_TRUST`, default **True**) lets a current-class unsigned pick take the bonus log-trust on `slot_usd`; ARM-B (`EEPHUS_P1_DSPLUS`, default **False**, efv_score.py:170) would add DS+-based pedigree. Rows are flagged `xfv_provisional` (efv_score.py:2221-2222).

**Serving/porting**: the backend team must reproduce (a) the matrix builders, (b) the closed-form weighted ridge + α CV with the exact seed, (c) the OLS anchor and calibration, (d) λ per side (or read `xfv.json meta.live_lambda`), (e) the three grade maps (outcome-curve JSON, the value-framework inversion, the pool-quantile map + F-SIDE-FIX), (f) the ordered-logit + Platt odds (with the seam-by-seam wiring caveat above), and (g) the value_framework dollar engine (config `value_framework_config.yaml` + `data/value_framework_fitted.json`). Version pinning is via `storage.board_basis_fingerprint()` (storage.py:4836-4884) = `"xfv_grade|scale=off|grademap=outcome_pooled@<curve_hash>|roles=<role mode>|feats=<sha256[:8] of the per-side feature spec 'hit:fv+1,obp_rel+1,…pit:…'>"` and `BOARD_RANK_BASIS_EPOCH = "2026-07-30"` (storage.py:4765, strictly-after gate).

## Inputs

**Feature vectors** (`_vec`, efv_model.py:733-860; only keys in `_FEATURES_HIT`/`_FEATURES_PIT` enter the ridge):

Hitter model features (efv_model.py:60-144): `fv` (consensus_fv_raw, or staleness-decayed `fv_effective` on live rows), `obp_rel`, `k_rel`, `peak_k_rel`, `age_rel_level`, `n_milb_seasons` (capped 8), `tool_hit`, `tool_speed`, `milb_missing`, `is_ifa`, `is_college`, `ops_rel`, `age`, `level_rank`. Pitcher model features (145-274): `fv`, `peak_k_rel`, `k_rel`, `bb_rel`, `age_rel_level`, `x_era_k`, `tool_fb`, `age`, `seasons_at_level` (pitchers ONLY — the same column fits inverted for hitters and is deliberately excluded, efv_model.py:267-273). `pace_from_entry`/`entry_level_rank`/`entry_observed` are emitted but **not in the model** (`PACE_FROM_ENTRY = False`, efv_model.py:307).

**Provenance of each input:**

- `consensus_fv_raw`, per-source FVs, `fv_stddev`, `n_sources`, tools (`tools_consensus`) — from board snapshots in `data/timeseries.json` / `debuts.json` / `inactive.json` `points[]`, i.e. the site's **consensus FV pipeline** (itself a computed stat: cross-source normalized equal-weight mean; registry `consensus_fv`). As-of extraction: `_asof_point` (efv_dataset.py:269-280 — latest point strictly before debut for debuted; final point for busts; latest for live).
- Level-relative production (`k_rel`, `bb_rel`, `obp_rel`, `ops_rel`, `iso_rel`, `era_rel`, peaks, `level_rank`, `age`, `age_rel_level`, `seasons_at_level`, `prod_trend`) — from the **MLB StatsAPI MiLB ladder** via `milb_history` (`mh.player_index`, `mh.league_norms`), computed in `_milb_features` (efv_dataset.py:506-712) against contemporaneous season+level league norms; optionally pre-adjusted by **S-XLINE** (AAA 2023+ Statcast expected-stat blend, `efv_statcast_line.maybe_adjust_row`, from Savant data) and **W2 PARK-LINE** (`efv_park_line.maybe_adjust_row`).
- `pick_overall`, `bonus_usd`, `is_ifa`, `is_college` — DB `acquisitions` table (`_load_sidecars`, efv_dataset.py:737-752; `_cohort_flags` 844-858).
- `il_stints_pre`, `il_any_pre` — DB `il_history` (`_injury_features`, 861-866: stints strictly before the decision date). Live IL state (`il_on`, `il_type`, `il_days_12mo`, `il_stints_12mo`, `is_post_tj`) — timeseries `il_status`/`health_profile` (build_live_matrix, ~1104-1119).
- `statcast_plus` — timeseries record (build_live_matrix ~1122); for hitters a batted-ball-quality index, for pitchers a **Stuff+-based** index → this is the one place a Stuff+-family stat touches eFV (as a bounded live tilt only, never a trained feature).
- Labels — `career_war` DB table (bWAR seasons; build_matrix, efv_dataset.py:878-885), terminal transactions from `player_transactions` (`_load_terminal_dates`, 802-818; consumption 1044-1063).
- λ calibration reads **WAG** (`regressed_wag`, `w_obs`) from `debuts.json` `debuted_value.wag` (`_load_wag`, efv_model.py:359-372) — WAG is computed elsewhere in storage; currently inert for λ (below significance threshold; hit overridden).
- `fv_effective` = `consensus_fv_raw − _stale_anchor_discount(asof, fv)` (build_live_matrix, efv_dataset.py:1125-1131; `anchor_stale_discount` also stamped on the row and surfaced as a "Stale list coverage" chip at efv_score.py:1714-1719).

**Dependencies on other documented stats**: `value_framework` ($/WAR + surplus) — heavy consumer-side dependency (grades map, odds, surplus, dollar calibration). `wag` — λ selector input (currently gated off). `draft_stock_plus` — only in the default-OFF P1 V3 ARM-B (`EEPHUS_P1_DSPLUS = False`, efv_score.py:170). `stuff_plus` — indirectly via the pitcher `statcast_plus` tilt. **AP+ (advancement pace) is contractually forbidden from feeding eFV** (stated at efv_dataset.py:481-486 and run_monthly.py:759-760); `pace_from_entry` is the eFV-native substitute and is not in the model. `rem_plus`/`sem_plus`/`hem_plus`/`pal`/`swing_plus`/`collegesavant_plus`: no input dependency (a PAL-derived starter-shape composite — `starter_shape`/`arsenal_depth`/`relief_flag` — is computed in `_vec` for pitchers but is **inert**: never in `_FEATURES_PIT`, efv_model.py:812-841; the RELIEF-SHAPE gate failed 2026-07-15).

## Constants, baselines & normalization

- **Windows/cohorts**: `DEBUT_YEARS = 2011–2024`, `RESOLVED_THROUGH = 2025`, `TARGET_SEASONS = 6`, `CURRENT_SEASON = 2026` (efv_dataset.py:112-116). Eval folds `SCORED_YEARS = (2020, 2021, 2022, 2023)` (efv_model.py:50). Every forward-chain fold requires ≥15 test / ≥60 train rows (efv_model.py:391, 466, 575).
- **Level ranks**: `{"DSL":0,"CPX":1,"A":2,"A+":3,"AA":4,"AAA":5}` (efv_dataset.py:117). Typical level ages (static prior, measured-and-kept — the empirical 2014-2026 medians are 0.10-1.86 yr older but swapping them is a registered NULL): `{"DSL":18.0,"CPX":19.0,"A":20.0,"A+":21.0,"AA":22.5,"AAA":24.0}` (135-136). `age_rel_level` hard-clipped to ±3.5 (`AGE_REL_CAP`, 194; `AGE_REL_SOFT=False`, 195). Decimal season-midpoint age preferred over the integer StatsAPI age, with a conflict guard `AGE_CONFLICT_MAX_YR=1.05` (141, `_resolve_season_age` 144-180).
- **Rate baselines**: level-relative rates = raw rate − contemporaneous same-season/level league median from StatsAPI (`_resolved_norms`, 341-351; fallback: prior season, then static `_NORM_PRIOR` — pitching k .22 / bb .095 / era 4.30; hitting k .22 / bb .085 / iso .135 / obp .330 / ops .715, 335-338). Recomputed per season per level per run; leakage-safe by construction. Reliability shrink toward 0: `w = PA/(PA+50)` hitters / `BF/(BF+40)` pitchers (`_K_REL_PA=50`, `_K_REL_BF=40`, 327-328).
- **Imputation constants** (efv_model.py:718-730): `_TOOL_IMPUTE = {tool_hit:50.0, tool_speed:48.0, tool_fb:58.0}` (measured train means; non-lean tools 45.0), age impute 22.5, `_N_MILB_SEASONS_CAP=8.0`, `_SHAPE_IMPUTE=38.9`, `_DEPTH_IMPUTE=1.6`, `seasons_at_level` impute 1.0, `pace_from_entry` impute 1.0 / `entry_level_rank` 2.0 / `entry_observed` 0.0, `pick_overall` impute 250.0 behind `pick_missing`.
- **Blend**: `_BLEND_LAMBDA_RESELECT = {"hit":0.70,"pit":None}` (332), band [0.50,0.70] (508), clamp (0.35,0.90) (318), fallbacks {hit .85, pit .80} (317), `_WAG_MIN_SPEARMAN=0.10`, `_WAG_MIN_N=100` (345-346).
- **Stale anchor decay** (efv_dataset.py:82-106): 0 through 18 months since last list (`STALE_ANCHOR_RAMP_START_MO`), linear to full at 30 months (`STALE_ANCHOR_RAMP_FULL_MO`); terminal FV-point discounts `{35:10, 40:10, 45:10}`; other bands never decayed. Applied to the MODEL fv input + the blend's consensus leg on ACTIVE rows only; displayed consensus stays raw.
- **Live overlays** (efv_score.py): age ramp onset **23.0** (`_AGE_PENALTY_ONSET`, owner dial), −0.10/yr (`_AGE_PENALTY_PER_YR`), floor 0.75 (636-638); reliever ceiling: RP designations {SIRP,MIRP,RP,CL} (671), trigger model_war ≥ 1.5 AND RP-designated, ramp onset 23.5 (`_ROLE_RAMP_ONSET = 25.0 − 1.5`, frozen, decoupled from the age dial), same −0.10/yr slope, floor 0.70 (676-683, 726-732); IL factors `_IL_MILD_DAY0=0.99 → _IL_MILD_FLOOR=0.90` over `_IL_MILD_FULL_DAYS=30` (uninformative types: MiLB "7-day" + unrecognized, days-scaled; an on-IL row with 0 trailing days AND 0 stints reads the saturated floor), 60-day `_IL_SEVERE=0.70`, MiLB full-season = 0.70 (`_IL_FULL_SEASON = _IL_SEVERE`), 15/10-day `_IL_MODERATE=0.82`, chronicity ×0.82 (days ≥120) / ×0.90 (≥60), ×0.92 (stints ≥3), overall floor 0.5 (757-837); healthy players (il_on false) carry NO penalty. Statcast tilt slope = per-side forward-r (from `data/statcast_plus_eval.json`, fallback hit .15 / pit .12) × `_SC_TILT_PER_PT_AT_R1=0.01` per SC+ point, clamp [0.82, 1.18] (840-874). S-XLINE-4 A/CPX overlay lean: `delta_fv = clamp(0.6 · composite_residual_z, ±12.0)` (`BETA_FV_PER_RESID_Z=0.6`, `DELTA_CAP_FV=12.0` numerical-safety only — the 2-FV display cap was removed by A4; efv_statcast_overlay.py:87-99, 290-292), priced onto WAR through the consensus OLS slope, model leg only.
- **F-SIDE-FIX**: knee 52.5 raw display grade (`SFF_KNEE_RAW`), move cap 3.0 FV (`SFF_MOVE_CAP_FV`), curve min n 20 (`_SFF_MIN_CURVE_N`), terminal PAVA block min n 5 (`_SFF_MIN_TAIL_N` — added 2026-07-31 after the pitcher curve's terminal block was found to be n=1 = Ohtani's two-way WAR on a pitcher row) (efv_score.py:1016-1023). Env override `EEPHUS_SIDE_FAIRNESS_FIX` ("1"/"0").
- **KRP+ pill** (a "+"-scaled by-product exported inside `xfv.json`): `krp_plus = 100 + 10·(x − μ)/σ` where x = `_krp_display_raw(era_rel, k_rel)` (= `(−era_rel)·k_rel`, except the double-bad quadrant era_rel>0 & k_rel<0 which is `−|x|`; era_rel winsorized ±6 display-only) standardized over the **current live pitcher pool** each run (population σ via `statistics.pstdev`; needs pool ≥2 and σ>0; the old 40-160 clamp was removed 2026-07-24) — efv_score.py:1634-1668, 1916-1934. Eligibility: era_rel present AND `rates_missing == 0` read from `r["milb"]`, NOT from the feature vector (`_krp_eligible`, 1622-1631). Baseline = per-run live pitcher board.
- **Dollar layer**: all tunable constants live in `value_framework_config.yaml`, all fitted parameters in `data/value_framework_fitted.json` (paths at value_framework.py:82-84; "this module contains NO hardcoded valuation constants", 51-60); dollar calibration `isotonic-real-v6-evframe-2026-07-31` stamped in `xfv.json meta.calibration` via `vf.calibration_stamp()` (value_framework.py:1575). ETA fallback for pricing when no ETA is served: `storage.PROSPECT_ETA_FALLBACK_YEARS = 1.0` (storage.py:6306); backgraded graduates price at eta 0.5. Scale conventions doc: `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md`.

The eFV grade itself is **not** a "+" stat: no 100-centering; the 20-80 anchoring comes from the outcome-curve inversion (recomputed only when the curve artifact is refit by `tools/fv_outcome_curve_pooled.py`) and the quantile map (recomputed against the pool's consensus-FV distribution **every run**).

## Edge cases & guardrails

- **Abstention**: live scoring skips any player with no MiLB block (`if not r.get("milb"): skipped_no_track += 1`, efv_score.py:1697-1699) — no eFV without a pro track record; the backgrade path grades those prior-anchored and flags `xfv_provisional`.
- **Floors/caps**: model WAR floored at −2.0 everywhere; consensus anchor floored at 0.0 WAR; provisional prior clamped to [−2.0, 20.0] WAR (config `war_floor`/`war_ceiling`); grades clamped [20, 80]; ridge needs ≥40 rows, calibration ≥50 pairs, production stack ≥60 rows (else `RuntimeError` in `_fit_production`, efv_score.py:1616-1618); fold guards ≥15 test / ≥60 train in every forward-chain.
- **Input caps (SAFETY class)**: `age_rel_level` ±3.5; `n_milb_seasons` ≤8; tool imputes at train means; exposure gates ≥50 PA / ≥60 BF for the primary-level pick and peaks (efv_dataset.py:523, 696-697); cameo protection — if no level clears exposure, use the MOST-EXPOSED level, not the highest (564-575); era_rel winsorized ±6 (KRP+ display only).
- **Leakage guards**: as-of features strictly pre-outcome; bust season-admission fix (`first_season` respects an Oct-1 season-end cutoff, efv_dataset.py:525-543); veteran re-appearance drops (`min(seasons) < dy`), Sept/Oct postseason-debut re-dating, and WAR-gap label drops (912-931); MLB-exposed "busts" rerouted to debuted or dropped (954-1008); terminal transactions resolve censored windows (1044-1063).
- **Missing handling**: `milb_missing` distinguishes "no track record" (1.0) from "data cannot exist" (`milb_unavailable` → 0.0, the pre-2015/no-mlbam class) (efv_model.py:733-746); mean-imputes behind indicators; `_x_era_k` zeroes the double-bad quadrant (era worse AND K worse) to kill a spurious positive product (efv_model.py:690-707).
- **Tilt sign-safety**: `_apply_war_tilt` divides instead of multiplies for negative WAR so a penalty always lowers the projection (efv_score.py:877-888). Healthy counterfactual `xfv_grade_healthy` captured with only the injury term dropped (Statcast/age/role tilts kept), pre-injury, and graded on the same outcome map (1752-1775, 1799-1801, 1843-1846); served only on rows actually carrying a penalty.
- **Degrade-to-no-op patterns**: F-SIDE-FIX (returns 0 and keeps the per-side map when the other side's artifacts or curves are unavailable, 1181-1200), S-XLINE, park line, overlay, ungraded, reliability, valuation curve are all best-effort/no-op on missing inputs; the outcome curve is deliberately the opposite (fatal `OutcomeCurveError`).
- **Idempotency**: F-SIDE-FIX keys off `xfv_grade_display_preside` (efv_score.py:1155-1172) and board-scale stamping off `xfv_grade_model_raw` so re-stamping can't double-correct.
- **$0 semantics**: a legitimate $0.0 surplus serves as 0.0, never null (`is not None` checks, efv_score.py:969, 1310, 1852, 2210).

## Dependencies & discrepancies

**Consumes**: consensus FV pipeline (dominant prior), StatsAPI MiLB history + league norms, Savant/Statcast (S-XLINE, statcast_plus tilt, A/CPX overlay), acquisitions/IL/transactions/career_war DB tables, `value_framework` (grade maps, odds, surplus, $-calibration), WAG (λ selector, currently inert), Draft Stock+ (default-OFF arm only).

**Feeds**: the PROSPX board rank (`storage.BOARD_GRADE_FIELD="xfv_grade"` + `overall_rank` in `metric_snapshots`), farm-system grades/TBS tiebreak, the trade machine (via value_framework surplus and board), /projections/ and fantasy surfaces, movement engine (eFV-delta), KRP+ pill, tool eFVs, GRPO, mock draft — all through `data/xfv.json` (+ `xfv_history.json`).

**Discrepancies / multi-basis warnings (all verified in code):**
1. **Three grade bases in one artifact** (documented in `xfv.json meta.grade_scale`, efv_export.py:147-164): `xfv_grade` (board; outcome curve), `xfv_grade_quantile` (retired display; **still prices `surplus_mm`**), and the internal realized-implied grade (**still drives `p_bucket`/`p_bust`**). A re-key of odds/dollars onto the outcome scale is explicitly deferred (efv_score.py:1268-1273).
2. **P0, live right now — `run_backgrade` crashes with `NameError`** (efv_score.py:2066): `factors = _relabel_pace_factor(factors, r.get("milb"))` uses `r`, which is not bound in `run_backgrade`'s scope (the loop variable is `rec`, the feature dict is `row`; the only `r` is a set-comprehension target at 1986, which does not leak in Python 3). Introduced in commit `3ada6a00` (2026-07-31 22:43). The line sits inside the `if row.get("milb"):` branch, which the production queue takes thousands of times (2,544 non-provisional rows in the last good artifact), so `run_backgrade` cannot complete → `regen_all` aborts before `score_history`/`efv_tools`/`efv_export.run`, and the pipeline's best-effort wrapper (run_monthly.py:741-747) swallows it. Artifact-timestamp evidence: `xfv_hitter/pitcher/live matrices` and all four `xfv_scored*` files are 2026-08-01 01:36-01:37, while `xfv_backgrade.json`, `xfv_history.json`, `xfv_tools*.json`, `xfv_valuation_curve.json` froze at 2026-07-31 20:30, and the served `xfv.json` (mtime 2026-08-01 01:31, `generated_at 2026-08-01`) predates the freshest scored files. Fix: `r.get("milb")` → `row.get("milb")` (the parallel live-path call at 1713 correctly uses its own loop variable), then rerun `regen_all`.
3. **Resolved-seam Platt no-op** (efv_score.py:1292): `provisional=not (r.get("milb") or {})` reads the `_prep` row (no `milb` key ever) → `provisional=True` for every resolved row → `recalibrate_bucket` is a hard no-op on the resolved cohort, contradicting the in-code comment "wired at the three seams" and the ship-gate spec's `provisional=not src.get("milb")` (tools/_prem_odds.patch:30-31; `data/xfv_odds_recalibration_ship_eval.json`). Live (1812) and backgrade (2191) seams do apply it. Separately, `efv_odds_calibration.py`'s header still says "NOT YET WIRED IN" — stale.
4. Registry `xfv_hitter`/`xfv_pitcher` notes quote λ=0.9 / 0.66 — stale vs served 0.70 / 0.57 (`xfv.json meta.live_lambda`).
5. `data/xfv_history.json` grades history through `outcome_implied_fv` on the model WAR **without** the live tilts (a "tilt gap", efv_score.py:1571-1578), so a tilted player's last history point sits below his board grade. (And per #2, the file on disk is currently one basis-stamp regen behind the fresh scores.)
6. `efv_board_scale.py` (W-SIDESCALE) is present but **OFF** (`ENABLED_DEFAULT=False`, disabled 2026-07-29 as a measured NULL); F-SIDE-FIX is **ON** but touches only the quantile/display field — exactly one side correction may be active at a time (efv_board_scale.py:136-147).
7. Rounding split by design: eFV displays round-to-nearest, consensus FV ceil (frontend cites above; owner rule in memory "Grades round UP … eFV rounds-to-nearest (exception)").
8. Glossary (`data/glossary.json` id `xfv`): the **"GRADE SCALE, restamped 2026-07-30"** block and the `formula` field agree with the code exactly (outcome-curve grade, retired-quantile surplus, retired-map odds). Two stale residues survive in the older `methodology` paragraph of the same entry: (a) "The headline grade is rank-preserving onto the familiar 20-80 consensus distribution" — retired as the display basis 2026-07-25/30 (that map now only prices surplus); (b) the reliever ceiling described as the retired staircase ("0.80, or 0.70 from age 26") — replaced 2026-07-30 by the continuous ramp (onset 23.5, −0.10/yr, floor 0.70).
9. `efv_export._entry`'s own comment block (efv_export.py:37-43, "COMMENT CORRECTED 2026-07-14") is itself stale: it still calls `xfv_grade_quantile` "the displayed headline site-wide" and describes `xfv_grade` via `realized_implied_fv`. `meta.grade_scale` (restamped 2026-07-30, efv_export.py:141-164) is the corrected authority; trust it, not the `_entry` comment.
10. A stale inline comment at efv_score.py:1723-1725 still describes the S-XLINE-4 overlay as "clamped +-2 FV, default-OFF module flags"; the shipped module defaults are ON and the clamp is the ±12 FV numerical-safety bound (2-FV display cap removed by A4).

---

# xfv

## Name in code & where computed

**`xfv` is the internal namespace of eFV** — there is no separate statistic. Everything in the "# efv" section above **is** the xfv system; this section pins down the name mapping and the artifact schema so nothing is lost in translation.

- Modules are `efv_*.py`; artifacts, JSON keys, matrices, evals and the registry rows are `xfv_*` (`xfv_hitter_matrix.json`, `xfv_eval.json`, `xfv_scored*.json`, `xfv.json`, registry ids `xfv_hitter`/`xfv_pitcher`/`xfv_tools`). Spec: `docs/xfv-phase1-plan.md`. Glossary id: `xfv`.
- Computed in production exactly where documented in `# efv` §1: `efv_dataset.py` → `efv_model.py`/`prospect_path.py` → `efv_score.py` → `efv_export.py`, orchestrated by `efv_export.regen_all()` from `run_monthly.rebuild_only()` (run_monthly.py:741-747, best-effort wrapped), which both the daily and monthly pipelines reach.
- The consolidated consumer-facing artifact is **`data/xfv.json`** (`efv_export.OUT_PATH`, efv_export.py:24); evals are `data/xfv_eval.json` (hitters) and `data/xfv_eval_pitcher.json` (pitchers) written by `efv_model.run()` (efv_model.py:1836, output path selection at 1936).

## Formula or fitted model?

Same fitted system as `# efv` §2. What is xfv-specific is the **key semantics in `data/xfv.json`** (`_entry`, efv_export.py:33-80):

| Key | Meaning | Produced at |
|---|---|---|
| `xfv_grade` | **THE eFV board number** (display, sort, `overall_rank` basis since 2026-07-30) = `vf.outcome_implied_fv(xfv_war_6yr)` | efv_score.py:1267 (resolved), 1792 (live), 2161 (backgrade) |
| `xfv_grade_realized` | alias of `xfv_grade` (back-compat; test-pinned identical) | efv_export.py:44-45 |
| `xfv_grade_quantile` | the RETIRED per-side quantile display grade (`xfv_grade_display` in scored files); no longer displayed but **`surplus_mm` is priced through it** | efv_score.py:1875-1895 live / 1320-1347 resolved + `_reprice_surplus_on_display` 925-978 |
| `xfv_minus_consensus` / `xfv_minus_consensus_quantile` | `xfv_grade − consensus_fv` / `xfv_grade_quantile − consensus_fv` | efv_score.py:1305/1347 (export rename at efv_export.py:51-52) |
| `xfv_war_6yr` | model E[first-6-season summed bWAR] after calibration, floor −2, live tilts applied (2 dp) | efv_score.py:1306/1848 |
| `rank_war` | (scored files only; not exported) the guarded blend `(1−λ)·cons_war + λ·xfv_war` that orders the quantile map | efv_score.py:1280/1711 |
| `p_bucket`, `p_bust` | 5-bucket outcome odds at the **realized-implied** grade; Platt-recalibrated on live + backgrade rows, UNrecalibrated on resolved rows (the seam-guard defect, `# efv` discrepancy #3); `p_bust = p_bucket["bust"]` | efv_score.py:1282-1292/1802-1812/2166-2191 |
| `surplus_mm`, `band_p10_mm`, `band_p90_mm`, `dist{p10..p90,mean,p_bust}` | calibrated $M surplus + fan, finally priced at `xfv_grade_quantile` | efv_score.py:1815-1818 then 925-978 |
| `consensus_fv`, `consensus_surplus_mm` | the consensus comparison columns (consensus surplus is storage's calibrated figure passed through) | efv_score.py:1841/1853 |
| `injury_factor`, `statcast_factor`, `xfv_grade_healthy`, `factors`, `xline_note` | live overlay disclosure fields (`injury_factor`/`statcast_factor` only serialized when ≠1.0; `xfv_grade_healthy` only on injured rows) | efv_score.py:1839-1873 |
| `krp_plus` | KRP+ pill (pitchers, live pool 100+10z) | efv_score.py:1922-1934 |
| `xfv_provisional` | prior-anchored no-track-record row (backgrade path) | efv_score.py:2221-2222 |
| `realized_war` | backgraded graduate's actual career WAR (did-we-nail-it read) | efv_score.py:2225-2228 / efv_export.py:78-79 |
| `tool_xfv` | per-tool eFVs merged from `xfv_tools*.json` | efv_export.py:112-118 |
| `kind` / `side` | `"active"`(live) / `"resolved"` / backgrade `"debuted"`/`"bust"` (backgrade also emits prior-anchored `"active"` rows); `"H"`/`"P"` | efv_export.py:33-36 |
| `meta.live_lambda`, `meta.calibration`, `meta.grade_scale` | served λ per side (hit 0.70 / pit 0.57, 4 dp), dollar-calibration vintage (`vf.calibration_stamp()`), and the authoritative basis statement | efv_export.py:120-168 |

Merge order in `efv_export.run()` (83-109): resolved → backgrade (overwrites, so the whole site reads one scale) → **live overwrites** for current prospects, so one player has exactly one row.

**xfv-specific pinning**: the feature spec is hashed into `storage.board_basis_fingerprint()` (sha256[:8] of `"hit:fv+1,obp_rel+1,…pit:…"` built from `_FEATURES_HIT`/`_FEATURES_PIT` with `%+d` signs, storage.py:4874-4884), the grade map is pinned by the outcome curve's `curve_hash` (`6dbe8353f3bb`, fingerprint term `grademap=outcome_pooled@<hash>`, storage.py:4857-4861), and `BOARD_RANK_BASIS_EPOCH="2026-07-30"` gates rank history strictly-after across the basis flip (storage.py:4760-4765).

## Inputs

Identical to `# efv` §3 (the `xfv_*` matrices are the direct upstream: `xfv_hitter_matrix.json` / `xfv_pitcher_matrix.json` for training; `xfv_live_*_matrix.json` for scoring). No additional inputs exist at the xfv layer; `efv_export.py` performs joins/renames only (plus the diagnostic `xfv_valuation_curve.json`, efv_export.py:187-297).

## Constants, baselines & normalization

See `# efv` §4 — all constants are shared. xfv-layer-only items: the export tier axis `_VC_TIER_FV` (efv_export.py:181-182, valuation-curve diagnostic only; `_VC_MIN_LIVE_N=5` thin-tier gate at 184) and the meta stamps (`live_lambda` 4 dp, `calibration` from `vf.calibration_stamp()`, value_framework.py:1575). Grades in `xfv.json` are stamped on a 0.1 grid; frontends round eFV to nearest integer for display (consensus FV ceils).

## Edge cases & guardrails

See `# efv` §5. Export-layer specifics: `n_active` counts `kind=="active"` rows in the merged artifact (backgrade contributes prior-anchored actives — 264 at fix time, all `xfv_provisional` — on top of the live board; efv_export.py:128-133); the backgrade path applies the Platt odds map **without** the `provisional=` guard on purpose (the queue rows never carry a raw `milb` key — measured 0 of 2,676 debuts.json rows — so the guard expression would silently disable the correction for the exact population it was fitted on; efv_score.py:2176-2191); `xfv_provisional` rows keep consensus-anchored WAR and are flagged for every consumer; players missing from `xfv.json` simply have no eFV (site falls back to consensus FV). Backgrade also stamps `xfv_postdebut_anchor` on the 187 graduates whose only snapshots are post-debut (efv_score.py:2030-2034, 2200).

## Dependencies & discrepancies

Same graph as `# efv` §6. The xfv-layer discrepancies to hand a backend team verbatim:

1. **`xfv_grade` ≠ `xfv_grade_quantile` ≠ the odds grade** — three deliberate bases in one row; `meta.grade_scale` in `data/xfv.json` (efv_export.py:147-164) is the authoritative in-artifact statement. Reproduce all three or downstream dollars/odds will not match.
2. `xfv_grade_realized` is a pure alias of `xfv_grade` (kept for back-compat reads; efv_export.py:44-45).
3. `data/xfv_history.json` (`{basis, basis_epoch, generated_at, by_player:{pk:[{d,x,c}]}}`) is on the board basis since the A2 repoint but excludes live tilts; `storage.xfv_history_is_on_board_basis` (defined storage.py:4919, consumed at 7645-7649) compares its `basis` stamp to `board_basis_fingerprint()` and suppresses eFV-delta movement on mismatch (stamp written at efv_score.py:1590-1601). The gate is movement-only: the $DvM+ appreciation rate deliberately still reads a foreign-basis series.
4. Registry λ values (0.9/0.66 vs served 0.70/0.57), the `efv_odds_calibration.py` "not wired" docstring, the `_entry` comment block, and the resolved-seam Platt guard are all stale/defective relative to served code (details in `# efv` §6 items 2-4, 9-10; item 2 — the `run_backgrade` NameError — is the one that currently stops the artifact chain and must be fixed before the next regen is trusted).
5. The trade-board population defect fixed 2026-07-31 (Aaron Judge absent because the population was prospect-derived) was a **consumer** bug, not an xfv artifact bug — `xfv.json` itself carries prospects/graduates/busts, never the full veteran universe; consumers must not treat it as a complete player census.

### Verification log

Every citation in the final text above was opened and read in the repo at commit ab56f7b (2026-08-01). Corrections made to the draft:

1. **ADDED P0 (draft missed it): `run_backgrade` NameError.** efv_score.py:2066 `factors = _relabel_pace_factor(factors, r.get("milb"))` — `r` is unbound in `run_backgrade` (loop vars are `rec`/`row`; the only `r` is the set-comprehension target at efv_score.py:1986, which does not leak — reproduced the NameError on Python 3.13). Introduced by commit 3ada6a00 2026-07-31 22:43:55. Evidence it is biting production: `data/xfv_backgrade.json`/`xfv_history.json`/`xfv_tools*.json`/`xfv_valuation_curve.json` mtimes frozen at 2026-07-31 20:30 while the matrices and all four `xfv_scored*` files were rebuilt 2026-08-01 01:36-01:37 and `xfv.json` (01:31) predates them; `run_monthly.rebuild_only`'s try/except (run_monthly.py:741-747) swallows the crash. Draft claimed the chain runs clean; corrected in §1 (chain note), §6 discrepancy #2 and the xfv §6 item 4.
2. **CORRECTED: Platt odds "wired at all three seams".** At the resolved seam (efv_score.py:1292) the guard `provisional=not (r.get("milb") or {})` reads the `_prep` row, which never carries a `milb` key (efv_model._prep, efv_model.py:863-874 emits only player_key/kind/decision_year/feats/target/weight/fv) → `provisional=True` always → hard no-op (efv_odds_calibration.py:119). The registered guard was `provisional=not src.get("milb")` (tools/_prem_odds.patch:30-31; data/xfv_odds_recalibration_ship_eval.json "applied_population": 906/907 hit, 920/920 pit). Live seam (1812) effectively applies to every scored row (no-milb rows already skipped at 1697-1699); backgrade seam (2191) unguarded by design (comment 2176-2190). Draft's claim rewritten in §2 and §6.
3. **CORRECTED: S-XLINE-4 overlay clamp "±2 FV".** The shipped clamp is `DELTA_CAP_FV = 12.0` FV, an explicit numerical-safety bound after the A4 owner directive removed the 2-FV display cap (efv_statcast_overlay.py:90-94; clamp applied at 290-292; max real lean observed 2.36 FV). The ±2 figure survives only in a stale comment at efv_score.py:1723-1725 (which also still says "default-OFF" — flags are ON at efv_statcast_overlay.py:87-88). Fixed in §1, §2 snippet, §4; stale comment logged as discrepancy #10.
4. **AMENDED: glossary agreement claim.** The `id:"xfv"` entry's restamped "GRADE SCALE" block and `formula` field agree with code, but the `methodology` paragraph retains two stale residues: the "headline grade is rank-preserving onto the … consensus distribution" phrasing (retired display basis) and the reliever-ceiling staircase "0.80, or 0.70 from age 26" (replaced 2026-07-30 by the ramp, onset 23.5 / −0.10/yr / floor 0.70, efv_score.py:671-732). Draft's "no correction needed there" replaced by discrepancy #8.
5. **ADDED: stale `_entry` comment** (efv_export.py:37-43) still names `xfv_grade_quantile` the displayed site-wide headline and describes `xfv_grade` via `realized_implied_fv`; `meta.grade_scale` (efv_export.py:141-164) is the corrected authority (discrepancy #9).
6. **CORRECTED citations**: `board_basis_fingerprint` is storage.py:4836-4884 (draft said 4877-4884) and its grademap term is `outcome_pooled@<curve_hash>` (storage.py:4859); `storage.xfv_history_is_on_board_basis` is DEFINED at storage.py:4919 (draft cited only the consumption site 7645-7649); resolved-path quantile map is efv_score.py:1320-1347 (draft: 1328-1347); `_load_wag` is efv_model.py:359-372 ✓ but `_WAG_MIN_*` are lines 345-346 (draft: 345-347); `_asof_point` 269-280; `_label_6yr` 715-731; `fv_effective` efv_dataset.py:1125-1131; `efv_model.run` eval write at 1936 (draft: 1935-1938 — kept as 1836/1936).
7. **ADDED precision the draft omitted**: LGBM challenger also passes `verbose=-1`; `_fit_ols_fv` needs ≥8 rows; provisional-prior clamp `war_floor=-2.0`/`war_ceiling=20.0` and `ifa_step_war=1.917` with `efv_provisional_prior.enabled: true` + `ifa_step_enabled: true` (value_framework_config.yaml, verified live); S-XLINE line-blend constants (W_HIT 0.7 / W_PIT 0.5, MIN_SAVANT_PA 100, FIRST_TRACKED_SEASON 2023, D_CAP_AVG/OBP/SLG/ISO .050/.050/.100/.060, ERA mult [0.75,1.25]); `PROSPECT_ETA_FALLBACK_YEARS = 1.0` (storage.py:6306) + backgrade graduate eta 0.5; board-scale fitted coefficients hit (-2.603487, 1.036284) / pit (-0.579380, 1.032470) (efv_board_scale.py:193-196); `_BUCKETS` definition sites (value_framework.py:86, efv_score.py:436); `xfv_postdebut_anchor` flag; `realized_war` export key; `regen_all` tail steps `_valuation_curve()` + `statcast_alevel_export.run()` (efv_export.py:346-359); the best-effort try/except around the whole regen (run_monthly.py:741-747); `xfv_tools` registry champion `xfv_tools_v0`; decimal-age conflict guard `AGE_CONFLICT_MAX_YR=1.05`.
8. **VERIFIED UNCHANGED (spot-list of load-bearing numbers)**: served `meta.live_lambda {hit: 0.7, pit: 0.57}` and `meta.calibration isotonic-real-v6-evframe-2026-07-31` (data/xfv.json); ordered-logit hitter cutpoints [7.8969, 8.8989, 10.1683, 12.4166] slope 0.17502, pitcher [7.3437, 8.4807, 9.8364, 13.1493] slope 0.16248 (data/value_framework_fitted.json `proportional_odds`); `_PLATT` hit (0.7268, 0.3749) / pit (0.7269, 0.3553); curve 20 knots FV 20→80, values 0.0→27.49, hash 6dbe8353f3bb; `_LOWEND_FG_EXP=0.45` + `20+25·(war/war45)^0.45`; bisection [45,80]×40; λ machinery (0.70 override, [0.50,0.70] 21-point band, clamp (0.35,0.90), fallbacks {.85,.80}, WAG gates .10/100); ridge seed 20260707, `_ALPHAS (1,10,100)`, ≥40/≥50/≥60 minimums, KM weights clipped ≥1e-3; all `_FEATURES_HIT`/`_FEATURES_PIT` membership + `PACE_FROM_ENTRY=False`; imputes {50/48/58, 45, 22.5, cap 8, 38.9, 1.6}; stale-anchor 18→30 mo, terminals {35:10,40:10,45:10}; age ramp 23.0/−0.10/0.75; role ramp {SIRP,MIRP,RP,CL}, ≥1.5 WAR, 23.5, 0.70; IL 0.99→0.90/30d, 0.70, 0.82, ×0.82/×0.90/×0.92, floor 0.5; SC tilt fallback .15/.12 × 0.01, clamp [0.82,1.18]; F-SIDE-FIX True/52.5/3.0/20/5; KRP+ 100+10z pstdev no-clamp; norms priors and K_PA 50 / K_BF 40; DEBUT_YEARS 2011-2024, RESOLVED_THROUGH 2025, SCORED_YEARS 2020-2023; level ranks + typical ages; AGE_REL_CAP 3.5; BOARD_GRADE_FIELD/epoch; Math.round vs Math.ceil frontend split (trademachine.js:742-743, fantasy.js:502, eephus-ui.js:310); no JS consumer of `xfv_grade_quantile`; registry stale λ notes 0.9/0.66; merge order resolved→backgrade→live; `n_active` merged-count semantics.


---

# rem_plus

## Name in code & where computed

**In-code names (casing exact):**
- `rem_plus` — the served integer index; `rem_plus_raw` — unrounded float; `fip_skill` — the shrunk-FIP intermediate (served as `fip`). Dataclass fields `Reliever.fip_skill`, `Reliever.rem_plus`, `Reliever.rem_plus_raw` (`prospect-tracker/rem_plus.py:140-142`).
- JSON payload keys: `rem_plus`, `rem_plus_raw` (1 decimal), `fip` per reliever row (`rem_plus.py:462,469`); team rollup `bullpen_plus` / `bullpen_plus_raw` (`rem_plus.py:386-387`); companion columns `rem_plus_3yr`, `rem_plus_3yr_pct`, `rem_plus_3yr_tag` (`bullpen_export.py:369-371`).
- Frontend key aliases: `remPlus`, `remPlus3yr` (plus `rivPlus`, `xremPlus`, reliever-anchored `warIpPlus*`) on the /projections/ player-card pitch block (`mlb_player_export.py:409-423`, REM+ keys at :412-413); `rem` in the FA current-lines payload (`build_site.py:4074-4080`, see consumers below).

**Computation sites:**

| Site | Role |
|---|---|
| `prospect-tracker/rem_plus.py` — `rem_plus()` at :250-260, `fip_skill()` at :231-247, `build_pool()` at :195-228, `score_pool()` at :420-455, `team_bullpen()` at :353-406 | **The only formula implementation.** Pure module, no I/O. |
| `prospect-tracker/bullpen_export.py` — `export()` at :704-803 | **PRODUCTION path.** Assembles inputs, calls `rem_plus.score_pool()` (:731), writes `data/bullpen_leaderboards.json`. Invoked by `run_monthly.py` step **6b4** (`run_monthly.py:3395-3401`). |
| `bullpen_export.py` — `export_history()` at :812-861 | Production, step **6b4d** (`run_monthly.py:3448-3459`, cadence-gated via `_lab_should_skip`; `EEPHUS_LABS=1` forces): same `score_pool()` re-run per past season (2021-2025, `HISTORY_SEASONS` at `bullpen_export.py:54`) → `data/bullpen_history.json`. Each season gets its own within-season pool. Only **qualified** arms are kept, on the reduced `_HISTORY_FIELDS` tuple (`bullpen_export.py:806-809` — rounded `rem_plus` only, no `_raw`), sorted by `rem_plus` desc (:838). |
| `tools/rem_plus_lab.py` — lab, **but it defines one shipped artifact**: `_multiyear_proposed()` at :491-544 writes `data/rem_plus_multiyear_eval.json`, whose `proposed_values.players` block is joined verbatim into the production board as `rem_plus_3yr` by `bullpen_export._join_rem_plus_3yr()` (:340-386). Refreshed by `run_monthly.py` step 6b4c (:3424-3443), cadence-gated. The lab computes per-season REM+ by importing the same `rem_plus` module (`tools/rem_plus_lab.py:188-206` inside `load_season()`) — no duplicated incumbent math. (Its `_cand_fip_skill` at :149-169 reimplements the FIP composition with a SwStr-implied xK shrink target, but that is the **rejected** X-R1 candidate, lab-only.) |
| `tools/rem_plus_backtest.py` | Lab only (writes the eval artifact `data/rem_plus_eval.json`, the verdict authority); not production compute. |
| `tools/fbhr_csw_labs.py` | Lab only: gated candidate REM+ cores X-R5 (FB-conditioned HR shrink target, the xFIP-lite deferral) and X-R1b (multi-year CSW%-implied xK shrink target). Reimplements `fip_skill` with swapped shrink targets using the `rem_plus` constants (:160-191). Candidates, not production. |
| `pal_conversion.py` — `project_relief_rem_plus()` at :558-574 | Production **consumer** (PAL /pal/ page): scores a hypothetical relief conversion of a starter through the same `rem_plus.rem_plus()` function against a real reliever pool built in `pal_export._build_rem_pool()` (`pal_export.py:419-424`, used at :647). Synthesizes a `Reliever` with `k_pct + k_bump` (default `DEFAULT_RELIEF_K_BUMP = 0.025` at `pal_conversion.py:54`; production passes the measured median from conversion history when ≥5 samples, `pal_export.py:572`), `bb_pct - 0.005`, HBP 1%, HR 2.8% of TBF (`_hr_from_arm`, :577-579). Explicitly **"DISPLAY ONLY - never a scored input"** (:556) — it does not enter the PAL FIT. Same code path, so no formula discrepancy. Note `_build_rem_pool` does not run the opener exclusion, which is immaterial: it passes an empty leverage dict, so `entry_inning` is None and `_is_opener` could never fire anyway. |

**No frontend recompute.** `assets/mlbstats.js` only renders payload values — column defs `r.rem_plus` / `r.rem_plus_3yr` / `r.xrem_plus` (:186-199), the REM+×gmLI and REM+×xREM+ scatters (:48-77), depth-chart slot chips (:576), the backtest accountability chip (:611-614), compare rows (:2161-2162), history-tab key whitelist (:264-268), and the default sort `{key:"rem_plus", asc:false}` (:290, fallback :472). `assets/projections.js` renders the `remPlus`/`remPlus3yr` card tiles (:1435-1470); `assets/fantasy.js` renders `skill.rem_plus` (:215-216, :488); `assets/pal.js` renders `proj_relief_rem_plus` (:315, :424); `assets/fa.js` renders the current-lines `line.rem` chip (:1071). `build_site.py` only reads the JSON (homepage drawer :2411-2418; current-lines payload :4043-4084). There is exactly one implementation of the math.

**Registry pin:** `data/model_registry.json:659-683` — `model_id: "rem_plus"`, champion `rem_plus_v1`, verdict **validated**, eval artifact `data/rem_plus_eval.json`. Headline: forward-chained OOS Spearman vs next-year RA9 **0.2363** for REM+ vs **raw FIP 0.211** (gap lo95 +0.001), **ERA 0.0901** (gap lo95 +0.088), raw WPA 0.1055; n=878 forward pairs, seasons 2018-2025 ex-2020 (verified against `data/rem_plus_eval.json`: `forward_spearman_vs_RA9_next`, `n_forward_pairs`). NOTE: the registry's compact `card` block (:671-682) prints `champion 0.236 / baseline 0.09` — that 0.09 is the **ERA** baseline, not raw FIP. A harness-v2 restamp companion exists (`data/rem_plus_eval_restamp.json`, noted in the registry row): v1-convention rho 0.2374 vs raw FIP 0.211 (gap lo95 +0.0023); `data/rem_plus_eval.json` remains the verdict authority (the lab pins `INCUMBENT_FORWARD_RHO = 0.2363`, `tools/rem_plus_lab.py:81`). The same eval block is served to users in the payload's `backtest` card (`bullpen_export._backtest()`, :288-312: currently rho_rem_plus 0.2363 / rho_fip 0.211 / rho_era 0.0901 / gap_vs_era_lo95 0.0881 / market_rho 0.5157). Also `MODEL_REGISTRY.md:51` (rem_plus), :70 (`rem_plus_3yr`, provisional), :71 (`rem_plus_swstr` — SwStr K-prior candidate **rejected/deprecated**), :97 (`rem_sem_3yr_decay` — decay-weighted 3yr **rejected**), :102 (`k_strength_sweep` — shrink-constant grid; shipped constants 70/170/170/400 **stand**).

## Formula or fitted model?

**Deterministic formula.** No trained model, no fitted artifact, no coefficients to serve. It is a ratio-to-league index (ERA+/wRC+ family), explicitly **not** a z-score (`rem_plus.py:8-9`; `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:34` — "REM+ | 1 (ratio) | relievers only | none").

Step by step (all code from `rem_plus.py`):

**Step 0 — population.** From all MLB pitchers' season lines, keep "true relievers": `ip > 0`, `g > 0`, and `gs == 0` or `gs/g <= MAX_START_SHARE (0.10)` (`is_true_reliever`, :149-157); then drop openers when entry data exists: `entry_inning <= 1.2 and ip/g <= 1.5 and gs == 0` (`_is_opener`, :160-166). (`score_pool()` :424.)

**Step 1 — per-player component rates** (`derive_rates`, :169-180):
```python
k_pct  = SO / BF;  bb_pct = BB / BF;  hbp_pct = HBP / BF;  hr_rate = HR / BF
```

**Step 2 — reliever pool anchor** `build_pool()` (:195-228). Pool contributors = true relievers with `tbf >= POOL_MIN_TBF (50)` and `ip > 0` (:197). Pool means are **count-weighted aggregates** (sum of counts / sum of TBF), not means of per-player rates (:210-213). Pool ERA = `sum(ER)*9/sum(IP)` (:214). FIP constant chosen so the raw (unshrunk) pool FIP equals the pool ERA:
```python
raw_fip = (13.0*hr + 3.0*(bb + hbp) - 2.0*so) / ip      # :216
p.cfip  = p.pool_era - raw_fip                           # :217
```

**Step 3 — empirical-Bayes shrink + skill FIP** `fip_skill()` (:231-247). Each rate is shrunk toward the pool mean by sample size, `rate_adj = (n*rate + K*mean)/(n + K)` (`_shrink`, :99-106), with `n = TBF` and K constants `K_STRIKEOUT=70`, `K_WALK=170`, `K_HBP=170`, `K_HOMERUN=400` (:41-44). Then:
```python
k_c, bb_c, hbp_c, hr_c = k*r.tbf, bb*r.tbf, hbp*r.tbf, hr*r.tbf   # expected counts
fip = (13.0*hr_c + 3.0*(bb_c + hbp_c) - 2.0*k_c) / r.ip + pool.cfip
return max(fip, 1.0)                                               # floor, :247
```

**Step 4 — pool mean of the shrunk FIP** (:218-227): `p.mean_fip` = **IP-weighted** mean of `fip_skill` over pool contributors, so the pool average scores exactly 100 by construction.

**Step 5 — the index** (:250-260):
```python
raw = 100.0 * pool.mean_fip / f          # f = player's shrunk FIP
r.rem_plus = int(round(raw))             # Python 3 round = banker's rounding at .5
```
Higher = better; 110 = 10% better run prevention than the average reliever. Note the served int uses Python 3 `round()` (round-half-to-even); the unrounded `rem_plus_raw` is served alongside at 1 decimal (:462). The served board is sorted by `(rem_plus, rem_plus_raw)` desc (:447), and the payload carries a `pool` summary block `{n, pool_era, mean_fip, n_qualified, n_provisional}` (:451-454) — currently n=298 contributors, pool_era 3.90, mean_fip 3.87, 461 scored arms (221 qualified + 240 provisional).

**Team rollup `bullpen_plus`** (`team_bullpen`, :353-406): relief-**IP-weighted mean of the rounded per-reliever `rem_plus`** over scored arms (`num += r.rem_plus * w` at :378, `w = r.ip` at :382), rounded to int (:386); the unrounded mean is served as `bullpen_plus_raw` (:387). Leverage is deliberately excluded (a separate `leverage_deploy_plus` weights by `ip*gmli` over arms with a gmLI feed, :383,:388, with `leverage_deploy_cov`/`_n` disclosure :389-390; `high_lev_core_rem` = mean rounded REM+ of the top-3 arms by gmLI :396-400; depth ladder :401-405).

**`rem_plus_3yr`** (shipped companion column, frozen lab vintage): IP-weighted mean of the **rounded** per-season `rem_plus` over the trailing 3 seasons `[Y-2, Y-1, Y]` (`window` at `tools/rem_plus_lab.py:501`), computed only for currently-qualified board arms (:508): `r3 = Σ(rem_plus_y * ip_y) / Σ(ip_y)` (:512-520), served as `int(round(r3))` (:526) with a midrank percentile `pct = int(round(100 * (lo + (eq+1)/2 - 0.5) / n))` (:531-535) and a `tag` (`"established"` iff `seasons_used >= TAG_MIN_SEASONS (2)` and `Σip >= TAG_MIN_IP (40.0)`, else `"provisional"`, :521-522; constants :84-85). Joined **verbatim** from `data/rem_plus_multiyear_eval.json` at export (`bullpen_export.py:340-386`) — it is a frozen vintage, not recomputed per run; the payload's `multiyear` block discloses `generated_at`/`season`/`window`/`n_stamped` (:374-385, wired into the payload at :779). A decay-weighted variant (`w = IP * 0.8^years_back`) was gated and **rejected** (`MODEL_REGISTRY.md:97`). Honesty note the glossary also carries: the 3yr did **not** beat the 1yr forward (Spearman 0.237 vs 0.232, difference not significant) — it is a stability read, not a stronger forecast.

**Leverage explicitly does NOT enter REM+.** gmLI/WPA/SD-MD ride separate "Impact" columns (`rem_plus.py:11-16`); test lock `test_leverage_does_not_move_the_talent_number` (`test_rem_plus.py:67-73`). The registry notes record the empirical confirmation: a leverage-weighted variant `100+(REM+-100)*(1+d*(gmLI-1))` is monotone-worse in d (optimal d=0), yet leverage-weighted REM+ correlates with FA AAV slightly better (0.516 vs 0.508) — leverage is a price/deployment layer, not talent (`model_registry.json:667`). The "gmLI 3yr" ship is a separate deployment-context column (`gmli_3yr`/`_pct`/`_tag`) joined from `data/leverage_consistency_eval.json` (`bullpen_export.py:315-337`, refreshed by `run_monthly.py` step 6b4b :3403-3422) — "Deployment context only - never an input to REM+" (`bullpen_export.py:319-320`).

## Inputs

All REM+-bearing inputs are raw season counting stats from **MLB StatsAPI** — `GET https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&season={Y}&sportId=1&gameType=R&playerPool=all&limit=3000` (`bullpen_export.load_season_pitching`, :170-212), one combined row per pitcher (traded players pre-merged by the API):

| Field (Reliever attr ← StatsAPI key) | Used in REM+? |
|---|---|
| `so` ← `strikeOuts`, `bb` ← `baseOnBalls`, `hbp` ← `hitByPitch`, `hr` ← `homeRuns`, `tbf` ← `battersFaced`, `ip` ← `inningsPitched` | **Yes** — the five FIP components + denominators. IP is converted from MLB .1/.2 notation to thirds by `ip_to_float` (`bullpen_export.py:75-84`). |
| `er` ← `earnedRuns` | **Yes** — pool ERA → `cfip` anchor only (also display `era`). |
| `g` ← `gamesPitched`, `gs` ← `gamesStarted` | **Yes** — population filter (start share, opener heuristic). |
| `entry_inning` (median entry inning) — computed from the StatsAPI `game/{pk}/winProbability` feed by `mlb_leverage.py` (`_finalize`, :321-322; start-games with `entry_inning == 1` dropped from the reliever fold, :201) | **Indirectly** — opener exclusion from the pool only. |
| `gmli` (mean LI at entry, `mlb_leverage.py:311`), `wpa`, `wpa_li`, `sd`/`md` (±`SD_MD_THRESHOLD` 0.06 WPA per appearance, :54, :216-219) | **No** — RIV+/roles/Impact columns only. |
| `sts`/`pit` → `swstr_pct` — pybaseball `pitching_stats_bref` `StS` rate (`bullpen_export.load_bref_swstr`, :215-238; `Pit` ← `numberOfPitches` :206) | **No** — display column only; the SwStr-based K-prior REM+ candidate was rejected (`MODEL_REGISTRY.md:71`). |
| `team` — StatsAPI `teams` abbreviation map (:96-103); position filter drops non-`P` primary positions (:193-196) | Grouping/population only. |

**Dependencies on other stats in this documentation set: none.** REM+ consumes no efv/xfv, no value_framework, no stuff_plus, no sem_plus/hem_plus. It **feeds**: `bullpen_plus` (rollup, same file), PAL's display-only `proj_relief_rem_plus` (`pal_conversion.py:558-574`; see the Dependencies section for the exact — baseline-only — role REM+ plays in the PAL eval), fantasy cards (`fantasy_export.py:413,589` reads the JSON), /projections/ player cards (`mlb_player_export.py:412`), the FA-page current-MLB-lines chip (`build_site.py:4043-4084` → `data/mlb_current_lines.json` key `rem` → `assets/fa.js:1071`), homepage module drawer (`build_site.py:2411-2418`).

## Constants, baselines & normalization

**Scale convention:** ARKMETRIC convention **1 (ratio-to-mean)**, NOT the 100+10z convention — `ARKMETRIC_SCALE_CONVENTIONS.md:34-35` ("REM+ … 1 (ratio) … none [clamp]", "REM+ 3yr … 1 (ratio)"); :11 "REM+ and SEM+ are the bare ratio with no gain" (contrast HEM+, which carries `HEM_SPREAD_GAIN = 2.28`). Exact raw→plus map: `rem_plus = 100 * pool_mean_shrunk_FIP / player_shrunk_FIP`. (Contrast: the neighboring `war_ip_plus` and `riv_plus` columns in the same payload ARE 100+10z — do not conflate.)

**Baseline population:** true relievers (GS/G ≤ 0.10, non-openers) with **TBF ≥ 50** in the *same single season being scored*, current MLB regular season (`gameType=R`), all levels of playing time above the floor. Both the component-rate means and `mean_fip` are **recomputed on every export run** (run_monthly step 6b4) from that season's live data — nothing about the baseline is frozen. History seasons each get their own within-season pool (`export_history`). 100 therefore = the average *reliever* of that season, not the average pitcher.

Named constants (all code literals in `prospect-tracker/rem_plus.py` unless noted):

| Constant | Value | Where |
|---|---|---|
| `K_STRIKEOUT` / `K_WALK` / `K_HBP` / `K_HOMERUN` (EB shrink, BF units) | 70 / 170 / 170 / 400 | :41-44; grid-sweep validated to stand (`MODEL_REGISTRY.md:102`) |
| `FIP_HR`, `FIP_BBHBP`, `FIP_K` | 13.0, 3.0, 2.0 | :47 |
| `POOL_MIN_TBF` | 50.0 | :51 |
| `QUALIFY_MIN_TBF` / `QUALIFY_MIN_IP` / `QUALIFY_MIN_G` | 100.0 / 20.0 / 20 | :52-54 |
| `MAX_START_SHARE` | 0.10 | :55 |
| FIP floor | 1.0 | :247 |
| Opener heuristic | entry ≤ 1.2, IP/G ≤ 1.5, GS = 0 | :166 |
| `cfip` | derived per pool: `pool_era − raw_pool_FIP` | :217 |
| Pool fallback defaults (empty pool only) | k .20, bb .085, hbp .010, hr .028, ERA 4.20, cfip 3.10, mean_fip 4.20 | `Pool` dataclass defaults, :183-192 |
| 3yr tag floors `TAG_MIN_SEASONS` / `TAG_MIN_IP` | 2 / 40.0 | `tools/rem_plus_lab.py:84-85` |
| Role bands (payload roles, not REM+) `GMLI_HIGH`/`GMLI_SETUP`/`GMLI_MIDDLE`/`LONG_IP_PER_G`/`CLOSER_MIN_SV` | 1.50/1.15/0.85/1.6/3 | :73-77 |
| PAL relief projection K bump `DEFAULT_RELIEF_K_BUMP` | 0.025 (overridden by measured median when ≥5 history samples) | `pal_conversion.py:54`, `pal_export.py:572` |

**No clamp / winsorization on REM+.** The site-wide plus-metric clamp audit confirmed the REM+/SEM+/HEM+/RIV+/xREM+/xSEM+ family is served unclamped (`MODEL_REGISTRY.md:161` — the only removal was KRP+'s 40-160 clamp); served values run to 203 (Mason Miller, `rem_plus_raw` 203.2, current `data/bullpen_leaderboards.json`). Display rounding is round-to-nearest int (the "+"-stat exception to the FV round-UP owner rule).

## Edge cases & guardrails

- **Population gates:** `ip <= 0` or `g <= 0` → excluded; `gs/g > 0.10` → excluded (starter); opener heuristic fires only when `entry_inning` data exists (no leverage feed ⇒ no opener exclusion) (`rem_plus.py:149-166`). Position players pitching are dropped upstream by primary-position ≠ P (`bullpen_export.py:193-196`).
- **Value vs qualification:** every pool arm gets a REM+ regardless of volume (the scoring loop :428-429 runs over all filtered arms, including TBF < 50 non-contributors); `qualified = tbf >= 100 or (ip >= 20 and g >= 20)` is a flag only (`rem_plus.py:430`) — the frontend and the history export filter on it, the number itself is not gated.
- **Null handling:** `_num`/`_safe_div` map missing/NaN/zero-denominator to `None` (:80-96); `_shrink` with a `None` rate returns the pool mean outright (:104-105); `rem_plus()` returns `None` if `fip_skill` is `None` (`ip<=0` or `tbf<=0`, :235-236) or defensively if `f <= 0` (:254 — unreachable given the 1.0 floor) and the row is then dropped from the served board (:446).
- **Small-sample blow-up guards:** EB shrink itself (a 5-TBF arm sits ~at pool mean); HR regressed hardest (K=400); hard FIP floor `max(fip, 1.0)` (:247). Test lock `test_small_sample_is_shrunk` (`test_rem_plus.py:54-64`).
- **Pool degeneracy:** empty pool → hardcoded `Pool()` league-ish defaults (:198-199); `mean_fip` falls back to `pool_era` if no IP-weighted denominator (:227).
- **Feed failures (export layer):** no season pitching rows → export logs and returns 0, leaving the previous JSON in place (`bullpen_export.py:713-716`); leverage walk failure → empty leverage dict, REM+ still computed (only opener exclusion and Impact columns degrade) (:721-728); bref SwStr absent → `sts=None` ⇒ `swstr_pct` null, never a fake 0% (:250-255); 3yr artifact missing/unmatched → fields absent, column blank (:357-363); active-roster fetch failure → depth ladders left unfiltered (:756-758). Atomic tmp-file write (:794-797).
- **IP notation:** `ip_to_float` treats `.1/.2` as thirds, with a guard for an already-decimal input (`bullpen_export.py:75-84`).
- **Test locks** (`test_rem_plus.py`): scale anchored at 100 (:34), inversion direction (:42), small-sample shrink (:54), leverage exclusion (:67), population filter incl. the 0.10 boundary (:76-80), opener exclusion (:83), Bullpen+ IP-weighted-not-leverage (:90).

## Dependencies & discrepancies

**Consumes:** nothing from the other documented stats. Raw StatsAPI counting lines + the in-house winProbability leverage walk (opener flag only).

**Feeds:** `bullpen_plus` / `leverage_deploy_plus` / `high_lev_core_rem` / depth ladders (`rem_plus.py:353-406`); `rem_plus_3yr` (frozen lab artifact of itself); **pal** — two distinct roles, neither a FIT input: (a) the display-only `proj_relief_rem_plus` column (`pal_conversion.py:556-574`, "DISPLAY ONLY - never a scored input"), and (b) pre-year REM+ serves as an eval **baseline** for the RP→SP direction of the PAL conversion gate (`MODEL_REGISTRY.md:52`, baseline column: "same-event pre-year K-BB%, pre-year ERA, pre-year REM+ (RP->SP) / SEM+ (SP->RP)"; implemented as `season_rem_raw` under "per-season baseline indices" in `tools/pal_backtest_lab.py:188-201`). The `PalArm.rem_plus` field (`pal_conversion.py:118`) is declared but never populated or read in the production FIT path; fantasy RP card skill block (`fantasy_export.py:413`) and the closer-depth role score `gmli*100 + saves*3 + rem_plus*0.2` (:587-589); /projections/ player cards (`remPlus`, `mlb_player_export.py:412`); FA-page current-lines chip (key `rem`, `build_site.py:4074-4080` → `assets/fa.js:1071`); homepage drawer top-3 by REM+ (`build_site.py:2411-2418`).

**Same-payload companions that are NOT REM+** (documented so a backend reader does not conflate them): `riv_plus` (100+10z realized-impact index, `rem_plus.score_riv_plus` :272-308, weights 0.70 WPA / 0.30 SD-MD re-standardized on the blend's own pool); `xrem_plus` + `luck` (`bullpen_export._join_xrem_plus` :389-442: `100 * pool_xwOBA_against / player_xwOBA_against`, PA-weighted pool over board arms with ≥ `_XREM_MIN_PA` 80 Savant PA, inverted so lower allowed = higher; a descriptive companion — Statcast xwOBA-allowed was tested against FIP for the REM+ core and did **not** win, `MODEL_REGISTRY.md:85`); reliever-anchored `war_ip_plus` (+`_adj`/`_pct`/`_3yr`, 100+10z, `_join_war_ip_plus` :641-649). **sem_plus** is the starter *cousin*: `sem_plus.py:36-40` **imports** the shared machinery from `rem_plus` (`_num`, `_safe_div`, `_shrink`, `_round`, `FIP_HR/FIP_BBHBP/FIP_K`, all four K constants), and `hem_plus.py:39` imports the helpers too — the shrink recipe and FIP weights are literally shared code — but the pool, anchor, qualification, and role taxonomy are fully separate, and starter- and reliever-anchored numbers must never share a column (`bullpen_export.py:461-465`, citing `ARKMETRIC_SCALE_CONVENTIONS.md:77`).

**Discrepancies:** none in the math — single implementation; all callers (export, history, lab, PAL) import `rem_plus.py`. Disclosure-level caveats worth reproducing: (1) `rem_plus_3yr` is a **frozen vintage** (currently `generated_at 2026-07-15`, window [2024, 2025, 2026]) served beside a live 1-yr number; the payload's `multiyear` block is the honesty mechanism (`bullpen_export.py:346-356,374-385`). (2) `bullpen_plus` is IP-weighted over the **rounded** integer `rem_plus`, not `rem_plus_raw` (`rem_plus.py:378`), and the 3yr window likewise averages rounded per-season ints (`tools/rem_plus_lab.py:494-495,517` — "harness v2 changes evals only, never shipped display"). (3) The registry's compact card advertises "0.236 vs 0.09" — the 0.09 baseline is **ERA**, not the raw-FIP parent (0.211); the full notes field and `data/rem_plus_eval.json` carry all four baselines. The glossary entry (`data/glossary.json:4964-4986`) agrees with the code — formula string "REM+ = 100 x poolFIP / playerFIP (sample-shrunk FIP; 100 = average reliever)" matches exactly; its definition's phrase "contact-quality rates" is loose marketing for the regressed HR rate (no batted-ball data is used), a wording nit, not a formula conflict. The companion glossary entries (`bullpen_plus`, `rem_plus_3yr`, `xrem_plus`) also agree with the code, including the honest "did NOT beat the single-season number" disclosure on `rem_plus_3yr`.

### Verification log

- **CORRECTED (registry headline):** the draft's "headline forward Spearman 0.236 vs raw-FIP baseline 0.09" mislabeled the baseline. The card block (`data/model_registry.json:671-682`) prints champion 0.236 / baseline 0.09, but 0.09 is the **ERA** baseline: `data/rem_plus_eval.json` `forward_spearman_vs_RA9_next` = {rem_plus 0.2363, raw_fip 0.211, era 0.0901, raw_wpa 0.1055}, echoed in the registry notes (`model_registry.json:667`) and in the served payload's backtest card (`bullpen_export.py:288-312`; live values rho_fip 0.211, rho_era 0.0901).
- **CORRECTED (PAL role):** the draft claimed "PAL RP→SP FIT uses pre-year REM+ as a scored input per MODEL_REGISTRY.md:52". Line 52's REM+ mention is in the **baseline** column of the registry table ("same-event pre-year K-BB%, pre-year ERA, pre-year REM+ (RP->SP) / SEM+ (SP->RP)") — it is an eval comparator, not a FIT input. Confirmed in `tools/pal_backtest_lab.py:188-201` ("per-season baseline indices (REM+ for relievers…)", `season_rem_raw`). The only production PAL use is the display-only `proj_relief_rem_plus` (`pal_conversion.py:556` "DISPLAY ONLY - never a scored input"). Also noted the declared-but-unused `PalArm.rem_plus` field (`pal_conversion.py:118`).
- **CORRECTED (sem_plus code sharing):** the draft said "no code sharing of the pool or anchor" for SEM+ — pools/anchors are indeed separate, but `sem_plus.py:36-40` imports `_shrink`, the FIP weights, and all four K constants **from rem_plus**, and `hem_plus.py:39` imports the helpers; rewrote the sentence to state exactly what is and is not shared.
- **CORRECTED (minor spans):** `team_bullpen` spans `rem_plus.py:353-406` (draft said :353-391; the bullpen_plus output keys at :386-387 stand); the "Deployment context only" quote spans `bullpen_export.py:319-320`; step 6b4 spans `run_monthly.py:3395-3401`; dataclass field order is `fip_skill`/`rem_plus`/`rem_plus_raw` at :140/:141/:142.
- **ADDED (missed consumers):** FA-page current-lines chip — `build_site.build_current_lines_payload` (:4043-4084, registered at :4148) writes `data/mlb_current_lines.json` with the reliever's REM+ under the alias key `rem` (:4078), rendered by `assets/fa.js:1071`; the exact fantasy closer-depth role-score formula `gmli*100 + saves*3 + rem_plus*0.2` (`fantasy_export.py:587-589`); `assets/projections.js:1435-1470` card tiles; the full set of `mlbstats.js` render sites beyond :186-199 (scatters :48-77, depth slots :576, backtest chip :611-614, compare rows :2161-2162, default sort :290/:472).
- **ADDED (missed labs):** `tools/fbhr_csw_labs.py` — gated candidate REM+ cores X-R5 (FB-conditioned HR shrink target) and X-R1b (CSW-implied xK target), lab-only, reimplementing the FIP composition from `rem_plus` constants (:160-191); and the note that `rem_plus_lab._cand_fip_skill` (:149-169) is the rejected X-R1 candidate, not shipped math.
- **ADDED (companions/details):** `xrem_plus` companion computed in `bullpen_export._join_xrem_plus` (:389-442) with `_XREM_MIN_PA = 80` and inverted ratio; `riv_plus` formula location (:272-308); PAL projection internals (`DEFAULT_RELIEF_K_BUMP = 0.025` at `pal_conversion.py:54`, measured-median override `pal_export.py:572`, synthetic HBP 1% / HR 2.8% of TBF, and the note that `_build_rem_pool` cannot run the opener exclusion); board sort tiebreak (:447) and served `pool` summary block (:451-454) with current values (n=298, pool_era 3.90, mean_fip 3.87, 461 scored); history export field whitelist `_HISTORY_FIELDS` (:806-809, rounded int only, qualified-only, sorted :838); the harness-v2 restamp artifact (`data/rem_plus_eval_restamp.json`, lab pin `INCUMBENT_FORWARD_RHO = 0.2363` at `tools/rem_plus_lab.py:81`); the exact 3yr midrank-percentile formula (`tools/rem_plus_lab.py:531-535`); registry-notes leverage bake-off numbers (d=0 optimal; AAV 0.516 vs 0.508); companion glossary entries (`bullpen_plus`, `rem_plus_3yr`, `xrem_plus`) verified to agree with code; full `test_rem_plus.py` lock list.
- **VERIFIED (unchanged):** the entire step-by-step formula, all constants (70/170/170/400; 13/3/2; 50/100/20/20/0.10; floor 1.0; opener 1.2/1.5/0; Pool fallbacks; role bands 1.50/1.15/0.85/1.6/3; TAG floors 2/40), count-weighted pool means (:210-213), cfip construction (:214-217), IP-weighted mean_fip (:218-227), banker's-rounding int, bullpen_plus over rounded ints (:378), the 3yr frozen-vintage contract (generated_at 2026-07-15, window [2024,2025,2026], verified in the served payload), production sites 6b4/6b4b/6b4c/6b4d (`run_monthly.py:3395-3459`), StatsAPI query params (:175-177), `ip_to_float` (:75-84), bref StS-as-rate (:228-233), leverage-field derivations (`mlb_leverage.py:54,201,216-219,311,321-322`), no-clamp claim (`MODEL_REGISTRY.md:161`), served max 203 / raw 203.2 (Mason Miller), scale-convention rows (`ARKMETRIC_SCALE_CONVENTIONS.md:11,34-36`), registry verdict **validated** with n=878 / 2018-2025 ex-2020, and the glossary formula string byte-match.


---

# sem_plus

## Name in code & where computed

**In-code names (casing matters):**
- `sem_plus` — the per-starter integer index (JSON key in `data/starter_leaderboards.json` rows).
- `sem_plus_raw` — unrounded float companion (1 decimal in the export, `_round(s.sem_plus_raw, 1)` at sem_plus.py:289).
- `fip_skill` → exported as `fip` — the shrunk FIP the ratio is built on (sem_plus.py:298).
- `sem_plus_3yr`, `sem_plus_3yr_pct`, `sem_plus_3yr_tag` — trailing-3-season companion column (frozen lab vintage, see below).
- `rotation_plus` / `rotation_plus_raw`, `front_sem` — team roll-ups of SEM+ (plus sidecar team keys `n_starters`, `starter_ip`, `n_above_avg`, `total_gs`, and a `rotation` ladder of `{role, key, name, sem_plus, ip, gs}` sorted by (-sem_plus, -ip), sem_plus.py:228-247).
- `role` — SEM+-tiered rotation slot ("Ace" / "Mid-rotation" / "Back-end" / "Spot").
- Camel-case re-serves on the MLB player-card export: `semPlus`, `semPlus3yr`, `xsemPlus` (mlb_player_export.py:438-439); `sem`/`xsem` on the build_site current-lines payload (build_site.py:4068).
- Related but separate columns on the same board (NOT SEM+): `xsem_plus` (Savant xwOBA-allowed companion), `war_ip_plus` / `war_ip_plus_3yr` (starter-anchored bWAR-rate index, convention 3 = 100 + 10z), `luck`.

**Where computed:**
- Model core (pure, no I/O): `prospect-tracker/sem_plus.py` — `fip_skill()` (sem_plus.py:161-185), `sem_plus()` (sem_plus.py:188-198), `build_pool()` (sem_plus.py:124-158), `score_pool()` (sem_plus.py:251-282), `team_rotation()` (sem_plus.py:224-248), `assign_roles()` (sem_plus.py:201-214), `starter_row()` (sem_plus.py:285-302). It imports the shared shrink/FIP machinery from `rem_plus.py` (sem_plus.py:36-40).
- Export/assembly: `prospect-tracker/starter_export.py` — `export()` (starter_export.py:225-276) builds `data/starter_leaderboards.json`; `export_history()` (starter_export.py:284-317) builds `data/starter_history.json` (per-season SEM+ boards for `HISTORY_SEASONS = [2021, 2022, 2023, 2024, 2025]`, starter_export.py:47, recomputed by the same `score_pool` per season, qualified rows only).
- 3-year companion: `tools/sem_plus_lab.py` — `_multiyear_proposed()` (sem_plus_lab.py:141-183) writes `proposed_values` into `data/sem_plus_multiyear_eval.json`; `starter_export._join_sem_plus_3yr()` (starter_export.py:102-142) stamps those values VERBATIM onto the board (frozen vintage, not recomputed at export time).

**Production path:** `run_monthly.py` step "6b4e. starter lab (sem_plus + sem_plus_multiyear evals)" (run_monthly.py:3461-3478) runs `tools/sem_plus_lab.py` as a subprocess (timeout 1200s), cadence-gated: skipped if `data/sem_plus_eval.json`'s top-level `generated_at` is younger than `LAB_EVAL_FRESH_DAYS = 30` (run_monthly.py:332; gate helper `_lab_should_skip` run_monthly.py:399-416, FAIL-OPEN on a missing/corrupt artifact; `EEPHUS_LABS=1` forces). Then step "6b4f. Starter Leaderboards" (run_monthly.py:3480-3492) runs `starter_export.export()` on EVERY run, and `export_history()` behind its OWN 30-day `_lab_should_skip` gate keyed on `data/starter_history.json`'s `generated_at` (run_monthly.py:3488-3490) — same mechanism and cadence as the lab gate, different keying artifact. Registry rows: `sem_plus` (validated) at data/model_registry.json:966-990, `sem_plus_3yr` (provisional) at data/model_registry.json:992-1004; MODEL_REGISTRY.md:72-73; step→artifact map DATA_SOURCES.md:90-91.

**No duplicate implementation of the arithmetic exists**, but the module IS re-invoked by several gated lab tools besides `tools/sem_plus_lab.py` — all of them call the same `sem_plus` module functions (never re-implement the math), and none of them ship to a production surface except `sem_plus_lab`'s frozen 3yr `proposed_values`:
- `tools/sem_plus_lab.py` (the shipped-eval + 3yr artifact producer; predictor bars `MIN_IP_Y = 50.0`, `MIN_IP_NEXT = 40.0`, `BOOT = 2000`, `SEED = 20260703`, sem_plus_lab.py:57-60).
- `tools/pal_backtest_lab.py:205-224` — recomputes per-season `sem_plus_raw` as PAL's SP→RP eval baseline (it does NOT read the served board).
- `tools/phem_marcel_lite_lab.py:258-341` — rebuilds the starter pool and re-uses `sem_plus._shrink` + constants for a pooled-Marcel candidate (loss ledger).
- `tools/fbhr_csw_labs.py:179-364` — FB/HR + CSW candidate cores over `sem_plus.fip_skill` machinery (loss ledger).
- `tools/velo_decline_lab.py` — reuses `sem_plus_lab.load_season` (writes `data/sem_plus_velo_eval.json`, "never touches the shipped rem_plus_eval / sem_plus_eval", velo_decline_lab.py:25-26).
- `tools/plus_metric_recal_lab.py:203-291` — read-only clamp audit of the served artifact.

The frontend (`assets/mlbstats.js:804-833` column defs, 1074-1138 viz + rotation ladders, 2213-2214 compare-tool rows) only formats/sorts the exported values (default sort `sem_plus` desc, `starterQualifiedOnly = true` default filter, mlbstats.js:804-807; the history tabs drop the 3yr/xSEM+/luck/WAR-rate columns via `STARTER_HISTORY_DROP`, mlbstats.js:887). `fantasy_export.py:410`, `mlb_player_export.py:438-439`, and `build_site.py:4043-4070` re-serve the same exported numbers by mlbam join.

## Formula or fitted model?

**Deterministic formula. No trained/fitted model artifact — no pickle, no coefficients.** It is a sample-shrunk (empirical-Bayes), starter-pool-anchored FIP expressed as a ratio-to-pool index (ERA+/wRC+ family, NOT a z-score). The "fit" is only validation gating (forward-chained Spearman in `data/sem_plus_eval.json`, verdict "validated": rho 0.4167 vs raw FIP 0.3821 vs ERA 0.2843, n=592 pairs, seed 20260703; gap CI vs ERA mean +0.1326 lo95 +0.0797, vs raw FIP mean +0.0342 lo95 +0.0177; predictor year qualified at IP>=50, outcome year IP>=40, 2020 excluded, 111 partial-2026-outcome pairs dropped by the harness-v2 restamp).

Step by step (production path, `gb_adjust=False` everywhere in production — see Edge cases):

1. **Population filter** — keep "true starters" (`is_true_starter`, sem_plus.py:88-92):
```python
if s.ip <= 0 or s.g <= 0 or s.gs <= 0: return False
return (s.gs / s.g) >= MIN_START_SHARE      # GS/G >= 0.50
```
2. **Derive rates** (sem_plus.py:95-108): `k_pct = SO/BF`, `bb_pct = BB/BF`, `hbp_pct = HBP/BF`, `hr_rate = HR/BF` (all per batter faced; `_safe_div` returns None on 0/None denominator). Context-only rates in the same dict: `k_bb_pct`, `gb_pct = GO/(GO+AO)`, `ip_per_gs`, `strike_pct`, `era`, `ra9`.
3. **Build the pool** over true starters with `ip >= POOL_MIN_IP` (20.0) (sem_plus.py:124-158). Pool component means are aggregate ratios (e.g. `mean_k_pct = sum(SO)/sum(BF)`); pool ERA = `sum(ER)*9/sum(IP)`; the FIP constant is set so the raw pool FIP equals pool ERA:
```python
raw_fip = (FIP_HR * hr + FIP_BBHBP * (bb + hbp) - FIP_K * so) / ip
p.cfip = p.pool_era - raw_fip
```
   Then the anchor is the IP-weighted mean of every pool member's SHRUNK skill FIP (so the pool average scores exactly 100 by construction): `p.mean_fip = sum(fip_skill(s)*s.ip) / sum(s.ip)` (sem_plus.py:151-157). Partial fallbacks inside a NON-empty pool: `mean_gb_pct` falls back to 0.44 if `go+ao == 0` (sem_plus.py:147, irrelevant to the plain core), and `mean_fip` falls back to `pool_era` if no member produced a FIP (`den == 0`, sem_plus.py:157).
4. **Per-starter shrunk FIP** (sem_plus.py:161-185), using `_shrink(rate, n, k, pool_mean) = (n*rate + k*pool_mean)/(n + k)` from rem_plus.py:99-106 (a None rate returns the pool mean; a None n is treated as 0, which also returns the pool mean exactly):
```python
k   = _shrink(s.rates["k_pct"],   s.tbf, K_STRIKEOUT, pool.mean_k_pct)    # K = 70
bb  = _shrink(s.rates["bb_pct"],  s.tbf, K_WALK,      pool.mean_bb_pct)   # K = 170
hbp = _shrink(s.rates["hbp_pct"], s.tbf, K_HBP,       pool.mean_hbp_pct)  # K = 170
hr  = _shrink(s.rates["hr_rate"], s.tbf, K_HOMERUN,   pool.mean_hr_rate)  # K = 400
k_c, bb_c, hbp_c, hr_c = k * s.tbf, bb * s.tbf, hbp * s.tbf, hr * s.tbf
fip = (FIP_HR * hr_c + FIP_BBHBP * (bb_c + hbp_c) - FIP_K * k_c) / s.ip + pool.cfip
return max(fip, 1.0)
```
5. **The index** (sem_plus.py:188-198):
```python
raw = 100.0 * pool.mean_fip / f       # f = the player's shrunk FIP
s.sem_plus = int(round(raw))          # + stats round-to-nearest (owner rule exception)
```
   Returns None if `f is None or f <= 0` (the `<= 0` leg is defensively unreachable given the 1.0 floor). NOTE for porters: `round()` here is Python 3 banker's rounding (round-half-to-even) — a .5 tie rounds to the even integer, not always up.
6. **Team Rotation+** (sem_plus.py:224-248): starter-IP-weighted mean of the ROUNDED per-starter SEM+ over the team's scored starters, `int(round(...))` (raw float kept in `rotation_plus_raw`); `front_sem` = `int(round(...))` of the simple mean SEM+ of the top-3 by SEM+. Teams list sorted by `rotation_plus` desc (sem_plus.py:271); starter board sorted by `(sem_plus, sem_plus_raw)` desc (sem_plus.py:274).
7. **sem_plus_3yr** (tools/sem_plus_lab.py:141-183): for each CURRENT-season qualified starter (`gs >= sem_plus.QUALIFY_MIN_GS (10) or ip >= sem_plus.QUALIFY_MIN_IP (50)`, expressed as a skip when both fail, sem_plus_lab.py:151), IP-weighted mean of the ROUNDED per-season `sem_plus` over window `[Y-2, Y-1, Y]` (seasons with a value and nonzero IP only), then `int(round(...))`; percentile `pct` = midrank percentile over players with a value, `int(round(100.0 * (lo + (eq + 1)/2.0 - 0.5) / n))` (sem_plus_lab.py:171-175); `tag = "established"` iff `seasons_used >= TAG_MIN_SEASONS (2) and total_ip >= TAG_MIN_IP (120.0)` else `"provisional"`. Served verbatim from the frozen artifact (currently generated 2026-07-15, window [2024,2025,2026], 142 players).

Backend port: implement the arithmetic above; the only "artifact" needed is the frozen `data/sem_plus_multiyear_eval.json` (plain JSON) if the 3yr column is reproduced, plus `data/sem_plus_eval.json` (plain JSON) whose `verdict.status` and rho fields are copied into the payload `verdict`/`backtest` blocks at export time (`_verdict` starter_export.py:74-79 — falls back to the string "provisional" if the eval file is unreadable; `_backtest` starter_export.py:82-99).

## Inputs

All season-total counting stats come from **one MLB StatsAPI call** — `GET https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&season={Y}&sportId=1&gameType=R&playerPool=all&limit=3000` via `bullpen_export.load_season_pitching()` (bullpen_export.py:170-212; base URL bullpen_export.py:62). Field mapping (StatsAPI key → row key → `Starter` field, starter_export.py:50-71):

| Starter field | Row key | StatsAPI stat key | Used in SEM+ math? |
|---|---|---|---|
| `g` | `G` | `gamesPitched` | filter only (GS/G) |
| `gs` | `GS` | `gamesStarted` | filter + qualification + `ip_per_gs` |
| `ip` | `IP` | `inningsPitched` (X.1/X.2 thirds notation → decimal via `ip_to_float`, bullpen_export.py:75-84; a fraction >= .3 is assumed already-decimal and passed through) | yes (FIP denominator, pool weights) |
| `tbf` | `BF` | `battersFaced` | yes (rate denominators + shrink n) |
| `so` | `SO` | `strikeOuts` | yes |
| `bb` | `BB` | `baseOnBalls` | yes |
| `hbp` | `HBP` | `hitByPitch` | yes |
| `hr` | `HR` | `homeRuns` | yes |
| `er` | `ER` | `earnedRuns` | pool cFIP only (+ display ERA) |
| `r` | `R` | `runs` | display RA9 / eval target only |
| `pit`, `strikes` | `Pit`, `Strk` | `numberOfPitches`, `strikes` | display `strike_pct` only |
| `cg`, `go`, `ao` | `CG`, `GO`, `AO` | `completeGames`, `groundOuts`, `airOuts` | display / no-shipped GB variant only |

Rows whose primary position is not "P" are dropped (position players pitching, bullpen_export.py:193-195); rows without an mlbam id are dropped at Starter build time (starter_export.py:56-58); team abbreviations come from StatsAPI `/teams` (bullpen_export.py:96-103). `build_starters` still accepts a legacy positional `swstr` argument and IGNORES it (the bref SwStr pull was removed; starter_export.py:50-53).

**No dependency on any other documented stat.** SEM+ does not consume efv/xfv, rem_plus (only shares its code constants), hem_plus, stuff_plus, pal, wag, value_framework, swing_plus, collegesavant_plus, or draft_stock_plus. `sem_plus_3yr` consumes prior-season SEM+ (itself). Sidecar columns on the same export that are NOT SEM+: `xsem_plus`/`xwoba_against`/`luck` (Savant `expected` leaderboard via `mlb_player_export._savant("expected", season, "pitcher")`, starter_export.py:148-195) and `war_ip_plus` (+ `_adj`/`_pct`/`_3yr`) (bWAR via `bullpen_export.score_war_rate` / `join_war_rate_3yr`, starter_export.py:198-222).

## Constants, baselines & normalization

**Scale convention:** convention 1 (pure ratio), per docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:37-39 — "SEM+ | 1 (ratio) | qualified starters only | none (no clamp)". Explicit warning at lines 8-13: SEM+ carries **no spread gain** (unlike HEM+ with `HEM_SPREAD_GAIN = 2.28`), so a SEM+ 120 is a literal FIP ratio of 120 while a HEM+ 120 is not comparable.

**Baseline population:** MLB true starters (GS/G ≥ 0.50) with IP ≥ 20 in the SAME season being scored, regular season only (`gameType: "R"`). Recomputed **per run** (every `run_monthly` execution) from live StatsAPI season data; for the history file, per season at history-build time. Nothing about the baseline is a stored artifact. 100 = the IP-weighted average shrunk-FIP of that pool by construction.

Named constants (all code literals):

| Constant | Value | Location |
|---|---|---|
| `POOL_MIN_IP` | 20.0 | sem_plus.py:43 |
| `MIN_START_SHARE` | 0.50 | sem_plus.py:44 |
| `QUALIFY_MIN_GS` | 10 | sem_plus.py:45 |
| `QUALIFY_MIN_IP` | 50.0 | sem_plus.py:46 |
| `SEM_ACE` / `SEM_MID` / `SEM_BACK` | 115.0 / 100.0 / 88.0 | sem_plus.py:50-52 |
| `K_STRIKEOUT` | 70.0 BF | rem_plus.py:41 |
| `K_WALK` | 170.0 BF | rem_plus.py:42 |
| `K_HBP` | 170.0 BF | rem_plus.py:43 |
| `K_HOMERUN` | 400.0 BF | rem_plus.py:44 |
| `FIP_HR, FIP_BBHBP, FIP_K` | 13.0, 3.0, 2.0 | rem_plus.py:47 |
| FIP floor | 1.0 | sem_plus.py:185 |
| `TAG_MIN_SEASONS` / `TAG_MIN_IP` (3yr tag) | 2 / 120.0 | tools/sem_plus_lab.py:61-62 |
| `_XSEM_MIN_PA` (xSEM+ companion, not SEM+) | 150.0 | starter_export.py:145 |

The `Pool` dataclass defaults (mean_k_pct 0.21, mean_bb_pct 0.075, mean_hbp_pct 0.010, mean_hr_rate 0.030, mean_gb_pct 0.44, pool_era 4.10, cfip 3.10, mean_fip 4.10; sem_plus.py:111-121) are fallbacks used only if the pool is empty — normally all are overwritten from data (with the two partial fallbacks noted in step 3). Current served board (data/starter_leaderboards.json, generated 2026-08-01): pool n=188, pool_era 4.14, mean_fip 4.12; 222 starters served (155 qualified + 67 provisional), served SEM+ range 73-167. The shrink constants were re-challenged and STAND per the `k_strength_sweep` loss ledger (data/model_registry.json:1439-1451: champion "shipped constants (70/170/170/400) - STAND"; SEM+ tuning cleared but the holdout failed, lo95 -0.0147). The 2026-07-29 restandardization sweep (`plus_metric_recal`, data/model_registry.json:2266-2279) removed a KRP+ clamp only; REM+/SEM+/HEM+/RIV+/xREM+/xSEM+ were "already true-to-model (raws unclamped)" — SEM+ constants unchanged.

**Raw→plus scaling:** `sem_plus = round(100 * mean_fip_pool / fip_skill_player)`. Displayed integer is round-to-nearest (the documented exception to the site's "grades round UP" rule, which applies to FV/tool grades only); ties use Python banker's rounding.

## Edge cases & guardrails

- **Population gate:** `ip <= 0 or g <= 0 or gs <= 0` → excluded; GS/G < 0.50 → excluded (sem_plus.py:90-92). Excluded arms get no SEM+ at all (they belong to the reliever board / nothing).
- **Scoring gate:** `ip <= 0 or tbf <= 0` → `fip_skill` returns None → `sem_plus` None → row dropped from the export (`scored = [s ... if s.sem_plus is not None]`, sem_plus.py:273).
- **Anchor vs display:** every true starter (even 1 IP) is SCORED against the pool, but only IP ≥ 20 arms shape the anchor (sem_plus.py:128). `qualified` (`gs >= 10 or ip >= 50`, sem_plus.py:261) is a display flag only — unqualified rows still ship, marked provisional in the UI (the frontend defaults to the qualified-only view, mlbstats.js:807); the history file keeps qualified rows only (starter_export.py:298-299).
- **Small-sample guards:** the empirical-Bayes shrink itself (HR regressed hardest, K=400 BF) plus a hard FIP floor of 1.0 against a degenerate tiny-denominator blow-up (sem_plus.py:185). No cap/clamp on the index itself (true-to-model; current served max is 167).
- **Null handling:** `_num` maps None/""/NaN/unparseable → None (rem_plus.py:87-96; bullpen_export.py:65-72 is the same); `_safe_div` → None on zero/None denominator (rem_plus.py:80-84); `_shrink` with a None rate returns the pool mean (rem_plus.py:99-106). Missing StatsAPI counts default to 0.0 at Starter build time (`_num(...) or 0.0`, starter_export.py:62-69; `ip_to_float(None)` → 0.0).
- **Missing feeds:** the whole export is best-effort — empty StatsAPI pull → log + return 0, board untouched (starter_export.py:233-236; run_monthly wraps the step in try/except, run_monthly.py:3482-3492). Missing/malformed multi-year artifact → `_join_sem_plus_3yr` returns `{"available": False}` and the 3yr fields are simply absent, column renders blank (starter_export.py:113-119). Unreadable eval file → payload `verdict` falls back to "provisional", `backtest` to `{}` (starter_export.py:74-99).
- **GB-adjusted variant is NOT production:** `score_pool` is called with default `gb_adjust=False` (starter_export.py:237). The X-S3 GB-adjusted HR-target core (HR shrink TARGET scaled by `factor = max(0.6, min(1.4, 1 - 0.8*(gb - pool.mean_gb_pct)))`, sem_plus.py:175-181) FAILED its gate — `data/sem_plus_eval.json` `gb_adjusted_candidate.pass = false`, "NO SHIP: the GB-adjusted core does not beat plain FIP forward out of sample" (gap mean -0.003, lo95 -0.010).
- **3yr vintage guard:** `sem_plus_3yr` is frozen lab output read verbatim; the payload's `multiyear` block carries `generated_at`/`season`/`window`/`n_stamped`/`n_in_artifact` plus an explicit staleness note so the divergence from the live board is disclosed, not silent (starter_export.py:107-142).
- **Atomic writes:** both artifacts are written via a `.json.tmp` then `replace` (starter_export.py:272-274, 313-315).
- **Pinned invariants (test_sem_plus.py):** scale anchored at 100 (IP-weighted), inversion direction/ratio, small samples shrink toward pool, starter population filter, durability does not move the skill number, Rotation+ is starter-IP-weighted, role bands, provisional tiering. `test_starter_smoke.py` smoke-renders the JS board; `test_mlbstats_smoke.py` and `test_war_rate_plus.py` touch the same export chain.

## Dependencies & discrepancies

**Consumes:** raw MLB StatsAPI season pitching counts only. No other documented stat feeds it.

**Feeds:**
- `/mlbstats/` Starter Leaderboards + team Rotation+ ladders + the SEM+ histogram / SEM+×IP-per-GS / SEM+×xSEM+ scatters + the player compare tool (assets/mlbstats.js:804-833, 887, 893-894, 1074-1138, 2213-2214 — display only).
- `data/starter_history.json` yearly tabs (2021-2025).
- Fantasy module: pitcher card + board `skill` block `{sem_plus, luck}` in `data/fantasy.json` (fantasy_export.py:394-414; the SP branch keys on the fantasy corpus `p["pos"] == "SP"`, line 408) — rendered on the ROS board column (assets/fantasy.js:217-218) and as the SEM+ column of the probables/streamer table (assets/fantasy.js:424-433). `fantasy_export` also reads the board for `ip_per_gs` (fantasy_export.py:208-211) and as an mlbam→name source (fantasy_export.py:90-100).
- MLB player cards: `semPlus`/`semPlus3yr`/`xsemPlus` (+ starter WAR-rate keys) in the `pitch` block (mlb_player_export.py:435-445), rendered as card tiles by assets/projections.js:1435-1478. NOTE: if an arm appears on BOTH pitching boards, the reliever block wins and the starter block (SEM+) is not stamped (`if "pitch" in e: continue`, mlb_player_export.py:432-434). The board also seeds identity-only "thin rows" so leaderboard names always link to a card (mlb_player_export.py:640-664).
- Team/site payloads via `build_site.build_current_lines_payload()` (build_site.py:4043-4070): `sem`/`xsem` keys lifted verbatim per mlbam.
- PAL uses pre-year SEM+ as an eval BASELINE for SP→RP conversions (registry row `pal_conversion`, data/model_registry.json:686-698, baseline field at :690) — baseline only, not an input to PAL's score, and the lab recomputes it from the module (tools/pal_backtest_lab.py:205-224) rather than reading the served board.
- `xsem_plus` borrows the SEM+ 100-anchor convention but is computed from Savant xwOBA-allowed, separately, ratio INVERTED so lower allowed = higher (starter_export.py:148-195).

**Discrepancies found:**
1. **Glossary vs current eval numbers (stale prose):** data/glossary.json:5114 publishes "Spearman correlation of 0.39, beating ERA (0.26 ...) and edging its raw-FIP parent (0.36)" while the live eval artifact (data/sem_plus_eval.json, harness-v2 restamp 2026-07-15, n=592) and the registry card (data/model_registry.json:978-989) say 0.4167 / 0.2843 / 0.3821 (card headline 0.417 vs 0.284). The glossary quotes the pre-restamp n=702 vintage (0.3923/0.2612/0.358 rounded). The formula description itself agrees with the code; only the quoted validation rhos are an older vintage. The served payload's `backtest` block is NOT stale — it re-reads the eval file at export time (starter_export.py:82-99).
2. **Glossary sem_plus_3yr rhos also stale by one vintage:** data/glossary.json:5470 says "three-year forward Spearman 0.414 versus 0.392" (the registry note's 0.4141/0.3922, n=457 vintage), while the current artifact (restamped 2026-07-15, n_forward_pairs=363) says 0.4252 vs 0.4098, gap lo95 -0.0347. The CONCLUSION is unchanged (gate pass=false, ships provisional as a steadiness companion).
3. **"Average qualified starter" wording:** glossary (data/glossary.json:5113) and registry say 100 = "the average qualified starter", but the anchor pool is true starters with IP ≥ 20 (`POOL_MIN_IP`), a broader set than the `qualified` display bar (GS ≥ 10 or IP ≥ 50). The anchor is also IP-weighted, not a simple mean.
4. **3yr rounding asymmetry (intentional, documented in the lab):** shipped `sem_plus_3yr` display values are computed from ROUNDED per-season SEM+ (tools/sem_plus_lab.py:141-143 docstring: "harness v2 changes evals only, never shipped display"), while the eval predictor uses UNROUNDED `sem_plus_raw` — a backend reproducing the displayed column must use the rounded per-season inputs.
5. **3yr freshness:** the served board (generated 2026-08-01) carries 3yr values frozen 2026-07-15; same-row 1yr and 3yr SEM+ are therefore from different vintages (disclosed in the payload `multiyear` block).
6. No Python/JS dual-implementation drift exists: one production compute site, all consumers join on the exported JSON; the additional lab callers listed above deliberately import the same module.

### Verification log

Corrections and additions made against the draft (all verified in code):

1. **Corrected the "only Python re-computation site is the lab" claim** — four more gated lab tools re-invoke the same `sem_plus` module: tools/pal_backtest_lab.py:205-224 (recomputes per-season `sem_plus_raw` as PAL's baseline), tools/phem_marcel_lite_lab.py:258-341, tools/fbhr_csw_labs.py:179-364, tools/velo_decline_lab.py:25-26/64 (via `sem_plus_lab.load_season`), plus the read-only audit tools/plus_metric_recal_lab.py:203-291. None ship production values except sem_plus_lab's frozen 3yr `proposed_values`.
2. **Clarified the `export_history` cadence gate** — it is keyed on `data/starter_history.json`'s own `generated_at` (run_monthly.py:3488-3490), not on `sem_plus_eval.json` (the draft's "same 30-day cadence gate" was ambiguous; same mechanism `_lab_should_skip`/`LAB_EVAL_FRESH_DAYS = 30`, different artifact).
3. **Added missed consumers**: assets/fantasy.js:217-218 (board column) and :424-433 (streamer/probables SEM+ column); fantasy_export.py:208-211 (`ip_per_gs` read) and :90-100 (name source); mlb_player_export.py:640-664 (identity thin rows); assets/projections.js:1435-1478 (card tiles); assets/mlbstats.js:887 (history column drop), :893-894 (Rotation+/Front 3 team columns), :2213-2214 (compare tool); named the build_site function (`build_current_lines_payload`, build_site.py:4043-4070).
4. **Added the reliever-board precedence rule** — an arm claimed by the reliever board never gets the `semPlus` card block (mlb_player_export.py:432-434). Material for anyone reproducing the card join.
5. **Added a NEW stale-glossary discrepancy** — sem_plus_3yr methodology (data/glossary.json:5470) quotes 0.414/0.392 while the current artifact says 0.4252/0.4098 (n=363, gap lo95 -0.0347; verified via data/sem_plus_multiyear_eval.json). Conclusion (provisional, gate fail) unchanged.
6. **Added precision the draft omitted**: Python 3 banker's rounding on `int(round(...))` (sem_plus.py:197, sem_plus_lab.py:166,175); non-empty-pool partial fallbacks `mean_gb_pct → 0.44` when `go+ao == 0` (sem_plus.py:147) and `mean_fip → pool_era` when `den == 0` (sem_plus.py:157); `sem_plus()` also returns None on `f <= 0` (sem_plus.py:192); export sort orders (sem_plus.py:271,274; starter_export.py:300); rows without mlbam dropped (starter_export.py:56-58); `_verdict()` fallback "provisional" (starter_export.py:74-79); atomic `.json.tmp` writes (starter_export.py:272-274, 313-315); full team-rotation payload keys and ladder sort (sem_plus.py:228-247); served-board counts 222 starters / 155 qualified / 67 provisional and range 73-167 (data/starter_leaderboards.json, 2026-08-01); eval gap CIs (vs ERA lo95 +0.0797, vs FIP lo95 +0.0177), lab pair bars `MIN_IP_Y=50`/`MIN_IP_NEXT=40`/`BOOT=2000` (tools/sem_plus_lab.py:57-59), and the 111 dropped partial-outcome pairs (data/sem_plus_eval.json `conventions`); `ip_to_float` pass-through guard for already-decimal input (bullpen_export.py:82-83); legacy ignored `swstr` parameter (starter_export.py:50-53); frontend default sort + qualified-only default (assets/mlbstats.js:804-807); test-suite invariants (test_sem_plus.py:31-101); DATA_SOURCES.md:90-91 step map.
7. **Line-number touch-ups**: `plus_metric_recal` registry row spans data/model_registry.json:2266-2279 (draft cited 2267-2270); `pal_conversion` row spans :686-698 with the SEM+ baseline at :690 (note: that row carries a `_comment` marking it a proposed replacement pending owner merge, data/model_registry.json:685); registry card block for sem_plus at :978-989.

All other draft claims verified against code exactly as written: sem_plus.py formulas/constants/line numbers (43-52, 88-92, 95-108, 111-121, 124-158, 161-185, 188-198, 201-214, 224-248, 251-282, 285-302); rem_plus.py:41-47, 80-106; starter_export.py:42-47, 50-71, 74-99, 102-142, 145, 148-195, 198-222, 225-276, 284-317; bullpen_export.py:62, 75-84, 96-103, 170-212, 193-195; tools/sem_plus_lab.py:56-62, 141-183; run_monthly.py:332, 399-416, 3461-3478, 3480-3492; data/sem_plus_eval.json (0.4167/0.3821/0.2843, n=592, seed 20260703, validated, GB candidate NO SHIP -0.003/lo95 -0.010); data/sem_plus_multiyear_eval.json (2026-07-15, window [2024,2025,2026], 142 players); data/starter_leaderboards.json (pool n=188, pool_era 4.14, mean_fip 4.12, max 167); data/model_registry.json:966-1004, 1439-1451; MODEL_REGISTRY.md:72-73; data/glossary.json:5113-5114; docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:8-13, 37-39; production-vs-lab classification (production = sem_plus.py + starter_export.py under run_monthly 6b4e/6b4f; lab = tools/* eval harnesses, of which only the frozen 3yr values ship).


---

# hem_plus

## Name in code & where computed

**In-code names (casing matters):**
- `hem_plus` — the published integer score, key on every hitter row (dataclass field `hem_plus.py:112`, emitted in `hitter_row()` at `hem_plus.py:423`).
- `hem_plus_raw` — the unrounded float companion, 1-decimal in the export (`hem_plus.py:113`, `hem_plus.py:423`).
- `woba_skill` / exported `woba` — the shrunk-wOBA core the score is a ratio of (`hem_plus.py:110`, `hem_plus.py:427`).
- `offense_plus` / `offense_plus_raw` — PA-weighted team roll-up of `hem_plus` (`hem_plus.py:358-359`); the team block also carries `team_pa`, `n_above_avg` (HEM+ ≥ 100 count), a `lineup` ladder, constructed `orders` (vs R / vs L), and a `bench` list (`hem_plus.py:360-380`).
- `heart_hem` — mean HEM+ of the top-3 qualified regulars per team (`hem_plus.py:363-365`).
- `hem_plus_3yr`, `hem_plus_3yr_pct`, `hem_plus_3yr_tag` — trailing-3-season companion column, joined from a frozen lab artifact (`hitter_export.py:80-82`).
- JS-side card aliases (baked into JSON by Python, consumed by the frontend): `hemPlus`, `hemPlus3yr` (`mlb_player_export.py:387`), `xhemPlus`, `tier`, `qualified`, `luckGap` (`mlb_player_export.py:388-389`), `pwoba`, `fwdhemPlus` (`mlb_player_export.py:399`), `wrcPlus` (`mlb_player_export.py:400`); `hem` + `xhem` (`build_site.py:4058`).

**Computation sites:**

| Site | Role |
|---|---|
| `hem_plus.py` — `derive_rates()` (:129), `build_pool()` (:187), `woba_skill()` (:225), `hem_plus()` (:244), `assign_tiers()` (:260), `team_offense()` (:345), `score_pool()` (:383), `hitter_row()` (:417) | **The model core. Pure (no I/O). This is the only place the HEM+ math lives.** |
| `hitter_export.py` — `export()` (:641-724) calls `hem_plus.score_pool()` at :665 and writes `data/hitter_leaderboards.json` (`OUT_PATH`, :50); `export_history()` (:732-765) writes `data/hitter_history.json` per closed season (`HISTORY_SEASONS = [2021..2025]`, :54) | **PRODUCTION path.** Wired into `run_monthly.py` step **6b4g** (`run_monthly.py:3517-3533`, live export every run; history behind an immutable-data cadence gate at :3529-3531). |
| `tools/hem_plus_lab.py` — `load_season()` (:68-97) re-runs the identical `hem_plus.py` core per historical season; `_multiyear_proposed()` (:134-169) produces the `hem_plus_3yr` values | **Lab, but it defines a shipped artifact**: `data/hem_plus_multiyear_eval.json`, whose `proposed_values.players` block is read VERBATIM by `_join_hem_plus_3yr()` (`hitter_export.py:57-97`) — the served 3-yr column is frozen lab output, not per-run pipeline output (disclosed in-payload, `hitter_export.py:92-95`). The lab also writes the validation artifact `data/hem_plus_eval.json`. Both artifacts come out of one `hem_plus_lab.run()` call in `run_monthly.py` step 6b4g-lab (:3494-3507) behind a WS-R freshness gate on `hem_plus_eval.json` (`_lab_should_skip`, :3502-3503; `EEPHUS_LABS=1` forces, comment :3499-3501, env documented :329). The adjacent try-block (:3508-3515) is the sibling `xhem_plus_eval.json` refresh (`tools/xhem_plus_lab.py`), not part of HEM+. |
| `assets/mlbstats.js` — `hemClass()`/`hemCell()` (:100-111), hitter table (:1284 ff., default sort `{key:"hem_plus", asc:false}` :1271), GFX "MLB Stats · HEM+ Leaders" card spec (:2242-2257) | **Display only — no recompute.** Renders the JSON values and colors them. |
| Downstream joins (no recompute): `mlb_player_export.py:386-400` (`hem` block on player cards), `fantasy_export.py:407` (`skill.hem_plus` + `skill.luck_gap` into `fantasy.json`), `fantasy_export.py:380-391` (team `offense_plus`/`heart_hem` into streamer context), `build_site.py:4043-4060` (`hem`/`xhem` into `data/mlb_current_lines.json`, registered for write at :4148). | Verbatim lifts from `hitter_leaderboards.json`. |
| Lab/audit-only reuse of the constants (NOT production, do not mistake for compute sites): `tools/phem_marcel_lite_lab.py:184-190` rebuilds a Marcel-lite pHEM+ from `hem_plus.W_*` + `HEM_SPREAD_GAIN` (candidate LOST its gate; registry `model_registry.json:1878` — incumbents unchanged); `tools/efv_statcast_line2_lab.py:35,184` borrows the W_* weights; `tools/_am_luckrank.py:71`, `tools/_av_luck_verify.py:71`, `tools/_am_plusmetrics_coh.py:70-71` recompute the xHEM formula for audit verification. | Lab only, nothing served. |

Sibling stats computed in `hitter_export.py` on the same payload but distinct from HEM+: `xhem_plus` (:381-423, reuses `hem_plus.HEM_SPREAD_GAIN` at :418), `fwdhem_plus` (:426-484), `luck_gap` (:421), `pwoba` (:487-557), `war_pa_plus` (:560-583), and the **published** (never derived) `wrc_plus` (:210-378).

**Discrepancy flag (display vs payload):** the Python tier label uses thresholds 135/112/90 (`hem_plus.py:79-81`), while the JS cell color bands are 130/112/88 (`mlbstats.js:103-105`). A hitter at HEM+ 131 carries `tier: "Above-avg"` in the JSON but renders with the `rem-elite` color class; 88-89 label `Below-avg` but color `rem-avg`. And there is a THIRD band set: the /projections/ player-card tiles color HEM+/xHEM+ with only two breaks — `proj-pos` at ≥ 112, `proj-neg` at ≤ 88, no elite class at all (`assets/projections.js:1692-1698`). Three intentionally different band sets on the same number; a reproducing backend should treat the JSON `tier` string as canonical and know the UI colors differ per surface.

## Formula or fitted model?

**Deterministic formula.** No trained artifact, no coefficients, no pickle. (There IS an accountability *eval* artifact — `data/hem_plus_eval.json` — but it validates the formula out-of-sample; nothing is fitted from it.)

Step by step, exactly as coded:

**1. wOBA denominator (also the shrink sample size)** — `_woba_denom()`, `hem_plus.py:118-122`:
```
d = max(0, AB + BB - IBB + SF + HBP)
```

**2. Component event rates** (`derive_rates`, :129-156). Singles are back-solved `s1 = max(0, H - 2B - 3B - HR)` (`_singles`, :125-126); unintentional walks `ubb = max(0, BB - IBB)` (:131). Rates are each count divided by `d`:
```
ubb_rate=ubb/d, hbp_rate=HBP/d, s1_rate=s1/d, s2_rate=2B/d, s3_rate=3B/d, hr_rate=HR/d
```
(Context-only rates avg/obp/slg/iso/bb_pct/k_pct/babip/sb_net also derive here, :146-159 — never enter the skill number.)

**3. Hitter pool** (`build_pool`, :187-222): over all hitters with `d >= POOL_MIN_PA` (50), compute the **wOBA-denominator-weighted** mean of each component rate (`_wmean`, :201-203), then:
```
pool_woba = 0.69*mean_ubb + 0.72*mean_hbp + 0.89*mean_1b + 1.27*mean_2b + 1.62*mean_3b + 2.10*mean_hr   (:213-214)
```

**4. Per-component empirical-Bayes shrink** (`woba_skill`, :225-241), using `_shrink` imported from `rem_plus.py:99-106` (verbatim):
```python
def _shrink(rate: Optional[float], n: Optional[float], k: float,
            pool_mean: float) -> float:
    """Empirical-Bayes shrink toward the reliever-pool mean by sample size."""
    r = _num(rate)
    nn = _num(n) or 0.0
    if r is None:
        return pool_mean
    return (nn * r + k * pool_mean) / (nn + k)
```
applied with `n = d` and per-component K (see section 4), then recombined:
```python
return (W_UBB*ubb + W_HBP*hbp + W_1B*s1 + W_2B*s2 + W_3B*s3 + W_HR*hr)   # :241
```

**5. Pool anchor** (`build_pool`, :215-221): `mean_woba` = the d-weighted mean of every pool member's **shrunk** wOBA (fallback `pool_woba` if degenerate). This makes the sample-weighted pool average score exactly 100 by construction.

**6. The score** (`hem_plus()`, :244-257):
```python
raw = 100.0 + HEM_SPREAD_GAIN * (100.0 * w / pool.mean_woba - 100.0)   # :252, gain = 2.28
hi.hem_plus = int(round(raw))                                           # :256  (round-to-nearest, the "+"-stat convention)
```
`hem_plus_raw` keeps the unrounded value (:255); export rounds it to 1 dp (`hitter_row`, :423, via `rem_plus._round` :415-417). The unshrunk `_raw_woba` (same weights on actual counts, :162-171) is stored as `woba_raw` for display + the backtest comparator.

**7. Roll-ups**: `tier` via thresholds (`assign_tiers`, :260-272); team `offense_plus = round(Σ hem_plus·PA / Σ PA)` over scored hitters with PA>0 (:353-359); `heart_hem` = round(mean HEM+ of top-3 by HEM+ among ≥200-PA regulars) (:363-365). Constructed batting orders (`build_batting_order`, :299-342) use HEM+ plus a platoon heuristic (±4 pts, switch +2, stagger band 8; constants :279-282) — lineup display only, never the published number.

**`hem_plus_3yr`** (frozen lab, `tools/hem_plus_lab.py:134-169`): for each current-pool hitter with `hem_plus` present and PA ≥ 200 (gate :141), the **PA-weighted mean of the rounded per-season display HEM+** over seasons [Y-2, Y-1, Y] (loop :146-149), `int(round())` out (:155-156); `tag = "established"` iff seasons_used ≥ 2 and window PA ≥ 600, else `"provisional"` (:153, constants `TAG_MIN_SEASONS`/`TAG_MIN_PA` :57-58); `pct` = mid-rank percentile over the artifact pool, `int(round(100*(lo + (eq+1)/2 - 0.5)/n))` (:159-163). The lab loads `SEASONS + [max+1, max+2]` (:179) so the proposed-values window matches the LIVE season, not a year behind. Current artifact: season 2026, window [2024, 2025, 2026], n=257 players (verified against `data/hem_plus_multiyear_eval.json`).

**Validation (context, not computation):** `data/hem_plus_eval.json` (X-H1, generated 2026-07-15): forward-chained Spearman HEM+(Y)→wOBA(Y+1) over 2012-2024 ex-2020, 3,372 pairs: HEM+ 0.4119 vs raw wOBA 0.4087, OPS 0.4108, AVG 0.2347; gate pass (v1 AND v2), verdict "validated". `data/hem_plus_multiyear_eval.json` (X-H2, generated 2026-07-15): 3-yr HEM+ forward rho 0.4546 vs single-season 0.4278 on the same 2,382 pairs; gate pass (v1 AND v2). Registry rows `hem_plus` (`data/model_registry.json:1006` ff.) and `hem_plus_3yr` (:1032 ff.), both **validated** in `MODEL_REGISTRY.md:74-75`. NOTE a small vintage drift in the registry PROSE: the `hem_plus` notes (:1014) quote rho 0.4123/0.4089/0.411/0.2348 and the `hem_plus_3yr` notes (:1040) quote 0.4548/0.4275 — 4th-decimal remnants of an earlier lab run; the eval artifacts are canonical. The export stamps the eval's verdict/backtest block into the payload (`_verdict` :592-597, `_backtest` :600-618, stamped at :703).

## Inputs

All inputs are raw season-total counting stats from the **MLB StatsAPI season hitting leaderboard**, fetched by `fa_sources.fetch_statsapi_season_stats(season, "hitting")` (`fa_sources.py:491-506`) against `https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting&season={season}&sportId=1&limit=5000&playerPool=All` (`fa_sources.py:485-488`), disk-cached per season via `scrapers._fetch` (cache key `fa_statsapi_hitting_{season}`, :496). Mapping (`load_season_hitting`, `hitter_export.py:127-136` → `build_hitters` :140-157):

| Hitter field | StatsAPI `stat` key | Enters skill number? |
|---|---|---|
| `pa` | `plateAppearances` | No (context; team weighting) |
| `ab` | `atBats` | Yes (denominator) |
| `h` | `hits` | Yes (singles back-solve) |
| `doub`/`trip`/`hr` | `doubles`/`triples`/`homeRuns` | Yes |
| `bb`/`ibb` | `baseOnBalls`/`intentionalWalks` | Yes (ubb = BB−IBB; IBB also subtracted from denominator) |
| `hbp`/`sf` | `hitByPitch`/`sacFlies` | Yes |
| `so` | `strikeOuts` | No (context k_pct only) |
| `sb`/`cs`/`rbi`/`r` | `stolenBases`/`caughtStealing`/`rbi`/`runs` | No (context only) |
| `bats` | bulk `sports/1/players` `batSide` (`load_bat_side`, `hitter_export.py:621-638`; stamped in `export()` :656-664) | No (lineup construction only) |
| team abbrev | StatsAPI team id → `bullpen_export._team_abbrev_map` (`bullpen_export.py:96-103`), lru-wrapped as `_tmap` (`hitter_export.py:100-104`) | No (grouping) |
| `mlbam` | `player.id` | Join key everywhere |

**Dependencies on other stats in the documented list: none.** HEM+ consumes no efv/xfv/rem_plus/sem_plus/stuff_plus/pal/wag/value_framework/swing_plus/collegesavant_plus/draft_stock_plus values. The only tie to `rem_plus` is **code reuse of four pure helpers** (`_num`, `_safe_div`, `_shrink`, `_round`; imported at `hem_plus.py:39`) — no REM+ number enters. (`hitter_export.build_hitters` uses a separate but semantically identical `_num` imported from `bullpen_export` — `bullpen_export.py:65-72`, import at `hitter_export.py:42`.)

## Constants, baselines & normalization

**Baseline population:** all MLB hitters (playerPool=All, so pitchers who bat included) with wOBA-denominator ≥ 50 in the scored season — the "hitter pool". The anchor is the d-weighted mean of the pool's *shrunk* wOBAs (`hem_plus.py:187-222`). **Recompute cadence: every export run** (each `run_monthly` execution recomputes the pool from the live season; each history season gets its own within-season pool in `export_history` / the lab). Nothing about the baseline is frozen — only the 3-yr column artifact is.

**Raw→plus scaling** (convention 2 in `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:20,30` — "ratio with the HEM gain"):
```
HEM+ = 100 + 2.28 * (100 * shrunk_wOBA / pool_mean_shrunk_wOBA - 100)
```
Note this is **not** the REM+/SEM+ bare ratio and **not** a 100+10z z-scale; ~1 point ≈ 0.44% of league offense; measured qualified-pool SD ≈ 17.7 (pooled 2021-2026 qualified, n=2,069; `mlbstats.js:115`), JS comment says "SD ~16" (`mlbstats.js:99`).

All constants are code literals in `hem_plus.py` (no config yaml, no fitted artifact):

| Constant | Value | Where |
|---|---|---|
| `W_UBB, W_HBP, W_1B, W_2B, W_3B, W_HR` | 0.69, 0.72, 0.89, 1.27, 1.62, 2.10 | `hem_plus.py:44-49` (FanGraphs-family wOBA linear weights; numerically identical to `fa_config.yaml:114` `assembly.woba_weights: { bb: 0.69, hbp: 0.72, single: 0.89, double: 1.27, triple: 1.62, hr: 2.10 }`, but read from the module constants — the docstring's "hitter_export may override from fa_config" (:43) is **not implemented**; no override exists anywhere, verified by repo-wide grep) |
| `K_UBB, K_HBP, K_1B, K_2B, K_3B, K_HR` | 120, 240, 290, 1000, 1600, 170 | `hem_plus.py:55-60` (per-component stabilization PAs) |
| `POOL_MIN_PA` | 50.0 | `hem_plus.py:63` |
| `QUALIFY_MIN_PA` | 200.0 | `hem_plus.py:64` |
| `HEM_SPREAD_GAIN` | 2.28 | `hem_plus.py:75` (monotone widening to wRC+ width; rank-preserving) |
| `HEM_ELITE / HEM_ABOVE / HEM_AVG` (tier labels) | 135 / 112 / 90 | `hem_plus.py:79-81` |
| JS color bands (elite/good/avg) | 130 / 112 / 88 | `mlbstats.js:103-105` |
| /projections/ card tile bands (pos/neg) | 112 / 88 | `projections.js:1693,1698` |
| Pool fallback prior (empty pool only) | mean_ubb .075, hbp .010, 1b .150, 2b .045, 3b .004, hr .033, wOBA .315 | `hem_plus.py:177-184` (`Pool` dataclass defaults) |
| Lineup heuristics `SLOT_PRIORITY / PLATOON_ADV / PLATOON_S / STAGGER_MAX_COST` | [2,4,1,3,5,6,7,8,9] / 4 / 2 / 8 | `hem_plus.py:279-282` |
| 3yr tags `TAG_MIN_SEASONS / TAG_MIN_PA` | 2 / 600 | `tools/hem_plus_lab.py:57-58` |
| Lab gates `SEASONS / MIN_PA_Y / MIN_PA_NEXT / BOOT / SEED` | 2012-2024 ex-2020 / 150 / 150 / 2000 / 20260705 | `tools/hem_plus_lab.py:52-56` |

**Glossary check:** `data/glossary.json` id `hem_plus` (:5124-5146) matches the code — "100 times the shrunk player wOBA over the pool wOBA … stretched … by a fixed monotone gain (HEM_SPREAD_GAIN)" (:5138). Its "about 15 points per standard deviation" (:5137) is a soft approximation (measured SD 17.7, JS comment says ~16) but nothing contradicts the formula. The companion entry `hem_plus_3yr` (:5148-5169) also agrees (PA-weighted trailing 3, established = 2+ seasons and 600+ PA, "0.45 vs 0.43" ≈ the artifact's 0.4546/0.4278).

## Edge cases & guardrails

- **Zero denominator:** hitters with wOBA-denominator ≤ 0 are excluded from scoring entirely (`score_pool`, `hem_plus.py:387`); `woba_skill` returns None for d ≤ 0 (:230-231), so `hem_plus` is None.
- **Thin samples still score:** anyone with 0 < d < 50 gets a HEM+ (shrunk hard toward the pool — a 1-PA hitter reads ≈100) but does **not** shape the anchor (POOL_MIN_PA). `qualified` (d ≥ 200, computed on the wOBA denominator, not raw PA) is a display flag, never a compute gate (:393).
- **Empty pool:** `build_pool` returns the hard-coded prior `Pool()` (:191-193, and again on `dtot <= 0` :198-199); degenerate anchor (`mean_woba <= 0`) → `hem_plus` returns None (:250-251).
- **Missing/None counts:** every count defaults 0.0 via `or 0.0` (ingestion `hitter_export.py:150-155`, via `bullpen_export._num`; core math `hem_plus.py` `or 0.0` throughout); `_num` rejects NaN/non-numeric (`rem_plus.py:87-96`, identically `bullpen_export.py:65-72`); `_shrink` with a None rate returns the pool mean (`rem_plus.py:104-105`); negative back-solves are floored at 0 (`max(0, ...)`, `hem_plus.py:121,126,131`).
- **No clamps/winsorizing:** the score is unclamped end-to-end (audited: `tools/plus_metric_recal_lab.py:283-285` — "clamp: none … HEM_SPREAD_GAIN=2.28 is a MONOTONE spread WIDENING … not a clamp").
- **Rounding:** display is `int(round())` (round-to-nearest, the site's "+"-stat exception to the FV round-UP rule); ties in the board sort break on `hem_plus_raw` (:406). Pinned by `test_hem_plus.py` (100-anchor, direction/ratio, small-sample shrink, volume-independence, PA-weighted Offense+, tiering, eval-gate-passes, 3yr-beats-1yr; :33-153).
- **Export is best-effort:** no rows from StatsAPI → log + return 0, board not rewritten (`hitter_export.py:650-652`); atomic tmp-file write (:719-723); `run_monthly` wraps the step in try/except so failure never aborts the pipeline (:3532-3533).
- **3yr column gating:** artifact missing/unmatched → fields absent, column blank (`_join_hem_plus_3yr` returns bare meta on OSError/ValueError/KeyError, :69-74); PA < 200 or no current HEM+ in the LAB run → player absent from the artifact (`hem_plus_lab.py:141`); `provisional` tag under 2 seasons/600 PA; the payload carries the frozen `generated_at` vintage + an explicit in-payload note so staleness is disclosed, not silent (`hitter_export.py:85-96`).
- **History boards:** qualified hitters only (`hitter_export.py:747`), restricted to `_HISTORY_FIELDS` (:727-729) so they drop the live-only join columns (3yr, xHEM+, fwdHEM+, luck, pWOBA, wRC+, WAR/PA+ family) rather than render blanks; the JS mirrors this with `HITTER_HISTORY_DROP` (`mlbstats.js:1373-1381`) and falls back to the default hem_plus sort if the active sort key is a dropped column (:1385-1389).
- **Team roll-ups:** require PA > 0 (:349); `heart_hem` needs at least one ≥200-PA regular (else None, :363-365); constructed orders need 9 scored bats else None (`build_batting_order` :303-306).

## Dependencies & discrepancies

**Consumes:** raw StatsAPI counting stats only (plus StatsAPI batSide and a team-abbrev map for grouping/lineups). None of the other documented stats.

**Feeds:**
- `offense_plus` / `heart_hem` / lineup orders — same payload, direct roll-ups (`hem_plus.py:345-380`).
- `luck_gap = xhem_plus - hem_plus` (`hitter_export.py:421`, positive = under-performing his contact) — and `xhem_plus` itself reuses `hem_plus.HEM_SPREAD_GAIN` so both sit on one ruler (:416-418).
- `fwdhem_plus` — consumes the **unrounded** `hem_plus_raw` core as its 0.3 z-leg (`hitter_export.py:426-484`; raw map built off the scored Hitter objects at :682-683 so display rounding never enters the blend).
- Fantasy module — `skill.hem_plus` + `skill.luck_gap` baked per hitter (`fantasy_export.py:407`); buy-low/sell-high ranks hitters by `luck_gap` via `_player_luck` (:307-311) with per-side spread normalization (`_buy_sell`, :314 ff.; section comment :572-576); team streamer context lifts `offense_plus`/`heart_hem` (`_teams_context`, :380-391). Frontend `assets/fantasy.js:195-196` renders `hem_plus` (display only).
- MLB player cards — `hemPlus`/`hemPlus3yr`/`xhemPlus`/`luckGap`/`fwdhemPlus`/`pwoba`/`wrcPlus` joined by MLBAM into the card `hem` block (`mlb_player_export.py:386-400`); rendered on /projections/ cards (`projections.js:1690-1699`).
- `data/mlb_current_lines.json` — `hem` + `xhem` keys lifted verbatim (`build_current_lines_payload`, `build_site.py:4043-4060`; write registration :4148).
- GFX/team surfaces render it (mlbstats.js GFX leaders spec :2242-2257, team lineup charts :1559-1651); the published `wrc_plus` column sits beside it for comparison but is never derived from it (this site derives no wRC+; `hitter_export.py:210-378`, `build_site.py:4030-4042`).

**Discrepancies found:**
1. **Tier vs color bands** — payload `tier` thresholds 135/112/90 (`hem_plus.py:79-81`) vs frontend color breaks 130/112/88 (`mlbstats.js:100-107`) vs /projections/ card tiles 112/88 two-break (`projections.js:1692-1698`). Deliberate but divergent: values 130-134 and 88-89 label one band and color another.
2. **Stale docstring** — `hem_plus.py:43` claims hitter_export may override the wOBA weights from fa_config; no such override exists anywhere (weights are always the module literals; `fa_config.yaml:114` merely holds identical values).
3. **3yr column vintage + rounding basis** — the served `hem_plus_3yr` is a frozen lab artifact (can lag the live board and miss new pool entrants; disclosed in-payload), and its display values are built from **rounded** per-season HEM+ (`tools/hem_plus_lab.py:146-149`) while the lab's validation leg uses **unrounded** `hem_plus_raw` (`_hem3`, :122-131). Reproduce the shipped column with the rounded convention.
4. **Luck-gap tooltip sign inversion on /projections/ cards** — the served `luckGap` is xHEM+ − HEM+ with positive = UNDER-performing contact (unlucky, buy-low) (`hitter_export.py:421`, `mlb_player_export.py:389`; correctly described at `mlbstats.js:1320-1321` and `fantasy_export.py:308,572`), but the /projections/ card tooltip describes it as "HEM+ minus xHEM+: positive means results have run ahead of the contact quality" (`projections.js:1699`) — the sign story is inverted relative to the number it renders. Copy bug on that one surface; the value itself is consistent everywhere.
5. **Registry-notes rho vintage** — `model_registry.json` prose notes carry 4th-decimal rho values from an earlier lab run (hem_plus :1014: 0.4123/0.4089/0.411/0.2348; hem_plus_3yr :1040: 0.4548/0.4275) vs the current artifacts' 0.4119/0.4087/0.4108/0.2347 and 0.4546/0.4278. Status fields agree (both validated); the eval artifacts are canonical.
6. No Python-vs-JS recompute duplication exists — the frontend only renders; the single source of the math is `hem_plus.py`. (The formula reappears only in lab/audit tools listed above, none served.)

### Verification log

- Verified every `hem_plus.py` claim by reading the file end-to-end: field lines :110-115, `_woba_denom` :118-122, `_singles` :125-126, `derive_rates` :129-159, `_raw_woba` :162-171, `Pool` prior :174-184, `build_pool` :187-222, `_wmean` :201-203, pool_woba :213-214, anchor :215-221, `woba_skill` :225-241, `hem_plus()` :244-257 (gain formula :252, int-round :256), `assign_tiers` :260-272, lineup constants :279-282, `build_batting_order` :299-342, `team_offense` :345-380, `score_pool` :383-414 (d>0 filter :387, qualified :393, tie-break :406), `hitter_row` :417-437. All constants (W_*, K_*, POOL_MIN_PA 50, QUALIFY_MIN_PA 200, HEM_SPREAD_GAIN 2.28, tiers 135/112/90, prior values, lineup heuristics) match the draft exactly.
- Verified `hitter_export.py`: OUT_PATH :50, `_join_hem_plus_3yr` :57-97 (note :92-95), `_tmap` :100-104, `load_season_hitting` :106-137 (mapping :127-136), `build_hitters` :140-157, wrc_plus block :210-378, `_join_xhem_plus` :381-423 (luck_gap :421), `_join_fwdhem_plus` :426-484, `_join_pwoba` :487-557, `_join_war_pa_plus` :560-583, `_verdict`/`_backtest` :592-618, `load_bat_side` :621-638, `export()` :641-724 (score_pool call :665, raw map :682-683, atomic write :719-723), `_HISTORY_FIELDS` :727-729, `export_history` :732-765.
- Verified `tools/hem_plus_lab.py`: constants :52-58, `load_season` :68-97, `_hem3` :122-131 (unrounded), `_multiyear_proposed` :134-169 (gate :141, rounded loop :146-149, tag :153, int-round :155-156, mid-rank pct :159-163), two-extra-seasons load :179. **Corrected** the draft's loop cite ":144-152" to :146-149 with the int(round) at :155-156, and added the :179 window-alignment detail.
- Verified `run_monthly.py`: 6b4g-lab :3494-3507 (gate :3502-3503, EEPHUS_LABS comment :3499-3501, env doc :329), sibling xhem lab :3508-3515 (**added** — the draft's ":3494-3507 both labs" wording folded the xhem refresh into the HEM+ lab; clarified that both HEM+ artifacts come from the one `hem_plus_lab.run()` and the adjacent block is xhem), 6b4g export :3517-3533 (history gate :3529-3531, try/except :3532-3533).
- Verified `fa_sources.py`: URL template :485-488 exactly as quoted, `fetch_statsapi_season_stats` :491-506, cache key `fa_statsapi_hitting_{season}` :496 (**added** the cache-key name).
- Verified `rem_plus.py` helpers: `_num` :87-96, `_shrink` :99-106, `_round` :415-417. **Replaced** the draft's compressed `_shrink` paraphrase with the verbatim code (semantics were identical).
- **Corrected** the `_num`-provenance in edge cases: `build_hitters` ingestion uses `bullpen_export._num` (`bullpen_export.py:65-72`, imported at `hitter_export.py:42`), semantically identical to `rem_plus._num`; the draft attributed ingestion NaN-handling to rem_plus only.
- **Corrected** the team-abbrev cite: `bullpen_export._team_abbrev_map` is at `bullpen_export.py:96-103`; the draft's "(:100-103)" was actually hitter_export's `_tmap` wrapper (:100-104). Both now cited.
- Verified `assets/mlbstats.js`: hemClass/hemCell :100-111 (bands 130/112/88 at :103-105), SD ~16 comment :99, measured SD 17.7 :115, default sort :1271, hitter columns :1284 ff., luck column tooltip :1320-1321, HITTER_HISTORY_DROP :1373-1389, GFX spec :2242-2257.
- **Added** missed display sites: /projections/ card tiles with a THIRD band set 112/88 (`projections.js:1692-1698`) and `assets/fantasy.js:195-196` hem_plus rendering (both display-only).
- **Added** missed discrepancy #4: `projections.js:1699` luck-gap tooltip describes "HEM+ minus xHEM+" (sign inverted) while the served `luckGap` is xHEM+ − HEM+ (`hitter_export.py:421`, `mlb_player_export.py:389`); mlbstats.js :1320-1321 and fantasy_export :308,572 state it correctly.
- **Added** missed baked card fields: `luckGap`, `qualified`, `tier`, `wrcPlus`, `pwoba`, warPaPlus family (`mlb_player_export.py:386-400`; draft listed only hemPlus/hemPlus3yr and, elsewhere, xhemPlus/fwdhemPlus).
- **Added** missed fantasy feeds: `_teams_context` team offense_plus/heart_hem lift (`fantasy_export.py:380-391`) and `_player_luck`/`_buy_sell` (:307-324, :572-576); verified `skill` bake :407.
- Verified `build_site.py`: `build_current_lines_payload` :4043-4097, `hem`/`xhem` :4058, payload registration for `data/mlb_current_lines.json` :4148. **Added** the `xhem` alias (draft listed only `hem`).
- Verified eval artifacts by loading them: `hem_plus_eval.json` generated 2026-07-15, X-H1, n=3,372, rho 0.4119/0.4087/0.4108/0.2347, gate pass, verdict validated; `hem_plus_multiyear_eval.json` X-H2, n=2,382 pairs, season 2026, window [2024,2025,2026], 257 players, 3yr rho 0.4546 vs 1yr 0.4278, gate pass. **Added** the X-H2 numbers (draft omitted them).
- Verified registry: `model_registry.json` hem_plus row :1006 ff., hem_plus_3yr :1032 ff.; `MODEL_REGISTRY.md` rows 74-75 both **validated**. **Added** discrepancy #5: registry prose notes carry earlier-run rho values (0.4123/0.4089/0.411/0.2348 at :1014; 0.4548/0.4275 at :1040) that differ in the 4th decimal from the current artifacts.
- Verified `fa_config.yaml:114` woba_weights identical values; repo-wide grep for `W_UBB|HEM_SPREAD_GAIN` confirms no override exists (draft's stale-docstring claim CONFIRMED) and surfaced the lab-only constant reuse (`phem_marcel_lite_lab.py:184-190`, `efv_statcast_line2_lab.py`, `_am_/_av_` audit tools) — **added** as a labeled non-production row.
- Verified `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md`: convention 2 "ratio with the HEM gain … `100 + 2.28 * (100 * player / pool - 100)`" at :20, HEM+ table row (convention 2, qualified MLB hitters, clamp none, `hem_plus.py`) at :30.
- Verified `tools/plus_metric_recal_lab.py:282-285` no-clamp audit entry (draft cited :283; the block spans 282-285 — kept with the wider range).
- Verified glossary: `hem_plus` :5124-5146 ("about 15 points per standard deviation" :5137; formula + HEM_SPREAD_GAIN :5138) and **added** the `hem_plus_3yr` entry :5148-5169 agreement check.
- **Added** test coverage note: `test_hem_plus.py` :33-153 pins anchor/shrink/tiering/eval gates; `test_hitter_wrc_plus.py:227` pins the wRC+ band mirror.
- Production-vs-lab classification CONFIRMED as drafted: `hem_plus.py` + `hitter_export.py` are the production path (run_monthly 6b4g); `tools/hem_plus_lab.py` is lab but defines the shipped frozen `hem_plus_3yr` artifact; all frontend sites are display-only.


---

# stuff_plus

**"Stuff+" is deliberately overloaded in this repo.** Five distinct shipped quantities carry the name (the repo's own scale-conventions doc calls it "overloaded six ways", counting the pre-2026-07-29 JS divergence and a vendored sibling vintage — `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:73-77`). All five are documented below; none share a scale and they must never be mixed in one column:

| Label | Key in code | What it measures | Scale |
|---|---|---|---|
| A. tjStuff+ | `tj_stuff_plus` / `avg_stuff_plus` | external per-pitch LGBM on StatsAPI game-feed kinematics | 100 − 10z, clamped 20–180 (**inverted sign**) |
| B. aStuff+ | `stuff_plus` in `data/stuff_plus_aaa.json` (+ `astuff_pool`/`astuff` in `data/aaa_physics.json`) | in-house AAA LightGBM, per-pitch kinematics → run value | 100 + 10z, no clamp |
| C. pStuff+ | `stf_plus_periph` | peripheral results: K%, BB%, HR/9 vs level mean | 100 + 10z, clamped 0–250 |
| D. FVStuff+ | `composite_stuff` → `composite_stuff_plus` | scouting-grade arsenal composite vs prospect cohort | 100 + 10z, clamped 0–250 |
| E. CollegeSavant Stuff+ | `stuff_plus` in `collegesavant/pitcher_pitch_data_*.js` | external college TrackMan xRV model, **vendored, not computed here** | external ratio (100 = college avg, 0 = worst observed) |

## Name in code & where computed

**A. tjStuff+ (MLB/tracked-park per-pitch model — external, scored locally)**
- `prospect-tracker/mlb_stuff_plus.py` — the only computing site. `score_pitch_points()` returns a `ScoredPitches` list carrying `.baseline` (the primary fastball every row was scored against, published per view as `stuff_baseline` since 2026-09-23) and stamps `tj_stuff_plus` onto pitch rows; the model name is hoisted to one view-level `stuff_model` rather than repeated per row. Helpers: `_primary_fastball` (`:73-96`), `_feature_row` (`:99-123`).
- PRODUCTION consumer: `statcast_metrics.py::_finalize_pitch` (`statcast_metrics.py:810-811` imports and calls it, wrapped in try/except at `:809-813`) and aggregates a per-pitch-type mean as `avg_stuff_plus` (`statcast_metrics.py:852`) inside each player's `pitch_movement.pitch_summary`. Note the pre-filter: only pitch points with parseable `hb` AND `ivb` are collected at all (`statcast_metrics.py:1010-1012`), and `_finalize_pitch` further requires `hb`, `ivb` AND `pitch_type` present (`:803-806`) — so pitches without break data or a type never reach scoring. This runs in the run_monthly chain, step **"3d-ter. Statcast pitch movement / contact quality"** (`run_monthly.py:2978-3047`, fetch + `upsert_statcast_metrics` at `:3037`); the whole step is SKIPPED when ≥90% of the eligible tracked-level pool already has a fresh row (`run_monthly.py:3001-3014`) or under `--fast` (`:2984-2985`). Rows are baked into `timeseries.json` at step **"5. Export timeseries.json + summary"** (`run_monthly.py:3293`, via `storage.export_timeseries_json`, `storage.py:7546`). Called on the pooled sample AND per level split (`statcast_metrics.py:1064-1071`).
- Frontend recomputes only aggregations, not the score: `prospx/index.html:44453-44470` (`_pitcherCompositeStuffPlusFromSc` = weighted mean of `avg_stuff_plus`; weight = `usage_pct` if > 0, else `count` if > 0, else 1 — `:44462`) and `:44472-44487` (`_formatPitchStuffPercentile`, same-level peer percentile). No formula duplication.

**B. aStuff+ (AAA in-house model)**
- `prospect-tracker/stuff_plus_aaa.py` — `_featurize` (`:163-184`), `train()` (`:217-272`), `score()` (`:275-356`, writes sidecar `data/stuff_plus_aaa.json`), `refresh()` (`:359-370`), `forward_eval()` (`:373-430`, writes `data/stuff_plus_aaa_eval.json`).
- PRODUCTION: run_monthly step **"6b2b. AAA Stuff+ re-score (stuff_plus_aaa.json)"** calls `stuff_plus_aaa.refresh()` (`run_monthly.py:3365-3376`). `refresh()` fetches the current season incrementally (`fetch_all((date.today().year,))`) and re-scores against the committed model; it **never retrains** (training is hand-run, `stuff_plus_aaa.py:359-363`).
- Duplicate computing site: `prospect-tracker/aaa_physics_export.py::_score_astuff` (`aaa_physics_export.py:168-209`) re-derives the identical score (same model bundle, same shrink, same pool conventions) into `data/aaa_physics.json` as `astuff_pool` / per-type `astuff`, with a served-json agreement check recorded in `meta.served_json_agreement` (`:273-284`, `:318-321`). Two scope differences vs the served sidecar: `_score_astuff` scores EVERY cached pitcher-season ≥50 pitches (all of 2023–2026, per-season blocks), whereas `score()` keeps only each pitcher's most recent qualifying season; and per-type `astuff` only attaches to `by_type` rows that already passed the ≥10-pitch physics floor (`:79`, `:236-238`). This exporter is hand-run (`python aaa_physics_export.py`, `:54`); it is NOT in run_monthly (grep confirms no reference). Intentional duplication with an agreement guard, not a drift risk — flagged anyway, and `docs/efv-2026-07-29/GATED_CANDIDATES.md:83-88` warns the two must move together.
- **PRODUCTION eFV consumer (via `astuff_pool`)** — see "Dependencies" below: the SHIPPED, default-ON uncapped statcast overlay `efv_statcast_overlay.py` residualizes its AAA physics legs on `astuff_pool` (`:205-223`), called from the live eFV scorer `efv_score.py:1728-1737`.
- Frontend consumers (no recompute): `prospx/index.html:30958-30973` (`getAaaStuffPlus` + boot loader fetching `/data/stuff_plus_aaa.json`), `:52963-52975` (aStuff+ pill, green ≥110 / red ≤90), `:34429-34431` (dossier index); `mlb_player_export.py:475-480, 609-615` joins it onto MLB player pages as `aaaStuffPlus`/`aaaStuffN`/`aaaStuffSeason` — pitchers (or two-way) with an ex-PROSPX `origin` only, so a vet's rehab-stint AAA pitches stay off his page; rendered by `assets/projections.js:1727` (tile, green ≥110 / red ≤90) and `:1882` (share card).

**C. pStuff+ (peripheral STF+)**
- Server: `storage.py::_compute_peripheral_stf_plus` (`storage.py:169-235`), baked onto every pitcher statline as `stf_plus_periph` inside `export_timeseries_json` (`storage.py:9274-9280`; enclosing function starts `storage.py:7546`). PRODUCTION, step 5 of run_monthly.
- Client mirror: `prospx/index.html::computeStuffPlus` (`prospx/index.html:52846-52877`) — **prefers the server-baked `stf_plus_periph` when present** (`:52850-52852`) and only recomputes the identical formula from `DATA.level_norms` as a fallback. The two implementations were reconciled 2026-07-29; before that the JS ran an unweighted sum of per-9 z-scores with hardcoded σ=0.15·μ (a different metric — it pinned 251 of 1,748 qualified pitchers at the 0 floor, pool sd 53.6 vs 6.1 — history documented at `prospx/index.html:52841-52845` and in the registry row).
- Note: the TBS helper reads `sl.stf_plus` before `sl.stf_plus_periph` (`prospx/index.html:11043-11044`); no `stf_plus` key is ever written server-side (grep confirms zero writes in `storage.py` — the only `stf_plus`-adjacent identifiers are the function def at `:169` and the `stf_plus_periph` bake at `:9278-9280`), so that first branch is dead legacy code.

**D. FVStuff+ (scouting-grade composite, key `composite_stuff` / `composite_stuff_plus`)**
- `storage.py::_compute_tool_composites` (def at `storage.py:342`) builds the raw 20–80 `composite_stuff` in its pitcher branch (`storage.py:388-410`); `storage.py::_attach_tool_plus_indices` (`storage.py:501-613`) z-scores it into `composite_stuff_plus` via `_index_plus` (`storage.py:144-156`), called once over actives+inactives+graduates at `storage.py:14841`. PRODUCTION, step 5. Sibling `composite_cmd_plus` runs through the same function.

**E. CollegeSavant Stuff+**
- **Not computed in this repo.** Vendored, already-scored payloads: `collegesavant/pitcher_pitch_data_2024.js / _2025.js / _2026.js` (external model lineage by Will Cahoon, college TrackMan xRV family). Local code (`collegesavant/pitcher_app.js`) only coerces `row.stuff_plus` to Number (`pitcher_app.js:548`), computes within-year per-pitch-type percentiles (`:601-619` — needs a pool of ≥2, result clamped 1–99), and feeds it as one z-scored component of client-side CS+ (`CSPLUS_GROUPS`, `:409-414`). Registry row `collegesavant_stuff` (verdict `provisional`, governance registration; agreement `pearson_r_measured` 0.9594 with the sibling vintage, `data/collegesavant_stuff_eval.json:128`). Do not invent a formula for it.

Labs (NOT production, noted for completeness): `tools/efv_pitcher_stuff_lab.py` (E-STUFF eFV **direct-feature** overlay — gate INCONCLUSIVE/zero trainable coverage, verdict `deprecated`, `data/xfv_pitcher_stuff_eval.json`), `tools/pal_xrv_lab.py` (W3 backtest), `tools/college_stuff_translation_lab.py` (gate FAIL, `deprecated`), `tools/aaa_physics_screen_lab.py` (descriptive screen, verdict `provisional`). None of these define a served Stuff+ number — but note the screen lab's frozen coefficients ARE consumed at serve time by the shipped `efv_statcast_overlay` (below).

## Formula or fitted model?

**A. tjStuff+ — fitted model (external), deterministic local scoring.**
- Model: sklearn `Pipeline(RobustScaler → LGBMRegressor)` (introspected live, verified 2026-08-01). LGBM hyperparameters: `n_estimators=1000, learning_rate=0.01, num_leaves=31, max_depth=-1, min_child_samples=20, subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.2, random_state=42`. Feature importances (split counts): start_speed 3149, spin_rate 2828, extension 2609, az 3401, ax 2988, x0 3236, z0 3356, speed_diff 2727, az_diff 3029, ax_diff 2677.
- Artifact: `prospect-tracker/model/tjstuff_plus/lgbm_model_2020_2023.joblib` (3,092,328 bytes ≈ 3.09 MB joblib; MIT LICENSE file alongside; from Thomas Nestico's tjstuff_plus repo — `mlb_stuff_plus.py:6-11, 21`). Trained by the author on MLB 2020–2023; target = per-pitch run value. NOT re-trained locally; version pin is the file path + registry row `stuff_plus_external` (verdict `unvalidated` — external model consumed as-is; no hash pin).
- Exact local scoring (`mlb_stuff_plus.py:126-182`):
  1. Handedness mirroring per pitch: `ax_mirrored = -ax if hand=="L" else ax`; `x0_mirrored = x0 if hand=="L" else -x0`; missing hand defaults `"R"` (`:138-145`).
  2. Primary fastball: among pitch types in `FASTBALL_TYPES = {"FF","SI","FC","FT"}` (fallback: all typed pitches), pick the type maximizing `(count, mean velo)`; primary = mean `velo`, mean `az`, mean `ax_mirrored` of that type (`:73-96`).
  3. Feature vector, exact order (`FEATURES`, `:22-33`; built `:112-123`): `[velo, spin, extension, az, ax_mirrored, x0_mirrored, release_height(z0), velo−fb_velo, az−fb_az, abs(ax_mirrored−fb_ax)]`. Any None ⇒ pitch skipped.
  4. Predict (as a DataFrame with `feature_names_in_` = `['start_speed','spin_rate','extension','az','ax','x0','z0','speed_diff','az_diff','ax_diff']`), then:
```python
z = (float(pred) - TJSTUFF_TARGET_MEAN) / TJSTUFF_TARGET_STD     # 0.0035 / 0.0068
rows[idx]["tj_stuff_plus"] = round(max(20.0, min(180.0, 100.0 - (z * 10.0))), 1)
```
  (`mlb_stuff_plus.py:179-180`). **Sign is inverted** (100 − 10z: lower predicted run value ⇒ higher score). Per-type display value: `avg_stuff_plus = _mean_round([r.get("tj_stuff_plus") ...], 0)` (`statcast_metrics.py:852`).
- To port: serve the joblib pipeline (needs sklearn + lightgbm), or export the booster; the two constants and the clamp are code literals.

**B. aStuff+ — fitted model (in-house LightGBM) + deterministic post-processing.**
- Model: `lightgbm.LGBMRegressor`, params (code literal `stuff_plus_aaa.py:232-236` and confirmed byte-identical in the artifact meta): `n_estimators=500, learning_rate=0.05, num_leaves=63, min_child_samples=200, subsample=0.9, subsample_freq=1, colsample_bytree=0.9, reg_lambda=2.0, random_state=20260611, deterministic=True, force_row_wise=True` (plus `n_jobs=4, verbose=-1`). Trained on 1,194,987 AAA pitches (2023–24), validated season-out on 571,467 2025 pitches (pitch-level r 0.0213, pitcher-level r 0.2797, n=638 — `data/stuff_plus_aaa_eval.json:3-7` and artifact meta); shipping fit refits on all complete seasons including 2025 (`:262-268`). Trained 2026-06-12 (artifact `meta.trained_at`). Importances (splits): velo 3403, spin 3521, extension 2022, pfx_x_arm 3553, pfx_z 3668, release_x_arm 3906, release_z 3733, arm_angle 3531, velo_delta_vs_primary 3413, throws_r 250.
- Artifact: `prospect-tracker/model/stuff_plus_aaa.joblib` — joblib bundle `{"model": LGBMRegressor, "meta": {...}}` (`:270`), meta carries features/params/eval. Pinned by path + registry row `stuff_plus_aaa` (verdict `provisional`, eval artifact `data/stuff_plus_aaa_eval.json`); no content hash.
- Target: `delta_run_exp` per pitch from Savant minors detail (negative = good for the pitcher) (`:18, :167-168`).
- Feature vector, exact order (`FEATURES` `:187-189`, built `:163-184`; `sign = +1` for RHP, `−1` for LHP; missing `p_throws` defaults `"R"`, `:170-171`):
```python
[velo,                                   # release_speed (required)
 spin or 0.0,                            # release_spin_rate
 extension or 6.0,                       # release_extension
 (pfx_x or 0.0) * sign,                  # arm-side-signed horizontal movement
 pfx_z or 0.0,
 (release_pos_x or 0.0) * sign,
 release_pos_z or 5.5,
 arm_angle or 30.0,
 (primary_velo - velo) if primary_velo is not None else 0.0,   # primary = MAX velo in the pitcher-season (:200-201)
 throws_r]                               # 1.0 RHP / 0.0 LHP
```
  No pitch-type identity and no result fields enter the features (physics-only contract, `:192-195`).
- Deterministic scoring (`score()`, `:275-356`): per pitcher, select the most recent cached season with ≥50 scoreable pitches (`:288-293`); `rv = mean(model.predict(X))`. Pool = per-pitcher unshrunk `rv` for `VALID_SEASON = 2025` seasons with ≥`MIN_POOL_PITCHES = 300` pitches (`:306-307`); `mu = mean(pool)`, `sd = np.std(pool) or 1.0` (population std, `:310-311`). Then:
```python
shrunk = (rv * n + mu * SHRINK_K) / (n + SHRINK_K)        # SHRINK_K = 300
z = (mu - shrunk) / sd                                    # lower RV = better stuff
stuff_plus = round(100 + 10 * z, 1)
```
  (`:315-331`). Per-pitch-type scores use the **same** shrink (k=300 per type) toward the **same pooled** `mu` on the same pooled scale (`:322-327`) — deliberately not per-type-centered. Sidecar also emits `meta.league_xrv_by_type` = league-mean predicted `delta_run_exp` per pitch type over the scored pool (`:336-350`).

**C. pStuff+ — deterministic formula.** Exact code (`storage.py:225-235`; z helper `:201-224`):
```python
z_k  = (k_pct    - avg_pitcher_k_pct)  / sigma_k          # sigma = empirical level std if present & >0, else 0.15*mu
z_bb = -((bb_pct - avg_pitcher_bb_pct) / sigma_bb)        # inverted
z_hr = -((hr_per_9 - avg_hr_per_9)     / sigma_hr)        # inverted
parts = [(0.55, z_k), (0.30, z_bb), (0.15, z_hr)]         # drop None components
composite = sum(w*z) / sum(w present)                      # weights RENORMALIZE
stf = round(100 + 10 * composite);  clamp to [0, 250]
```
K% and BB% are per-batter rates (workload-neutral). Glossary formula (`data/glossary.json` id `stf_plus`) matches the code exactly.

**D. FVStuff+ — deterministic formula.** Raw composite (`storage.py:394-400`):
```python
stuff_inputs = [grades[k] for k in ("fb","sl","cb","ch") if present]        # 20-80, snapped to 0.5 first (:369)
for fv in (frame_fv, athl_fv, delivery_fv):                                  # FG -2..+2 mapped -2→30,-1→40,0→50,+1→60,+2→70 (:253-264)
    if fv is not None: stuff_inputs.append(fv)
composite_stuff = round((sum(v**3 for v in stuff_inputs)/n) ** (1/3), 2)     # power mean p=3 (:238-250, :166)
```
Then cohort standardization (`storage.py:519-542`): population mean/std of `composite_stuff` over ALL serialized prospects carrying it (min 2 samples), and
```python
composite_stuff_plus = clamp(round(100 + 10 * (value - mean) / stdev), 0, 250)   # _index_plus, storage.py:144-156
```
**Glossary discrepancy flag:** glossary `stuff_grade_plus` formula says `composite_stuff = (Σ pitch_grade³/n)^(1/3)` over pitch grades only; the code (v14, `storage.py:388-400`) also feeds Frame/Athl/Delivery FV-mapped values into that power mean. The glossary methodology also says "active-prospect cohort" while the code cohort is actives + inactives + graduates (`storage.py:14835-14841`). The `tool` glossary entry (`glossary.json:40-41`) describes the physicals correctly; the `stuff_grade_plus` formula line omits them.

**E. CollegeSavant Stuff+ — no local formula.** External fitted lineage (TrackMan physics → xRV, rescaled to a class-relative ratio: 100 = college-average xRV, 0 = worst observed; measured payload SD ≈ 23–24, observed range 3.4–185.4 — `ARKMETRIC_SCALE_CONVENTIONS.md:69, 73-77`). Local transformations only: numeric coercion, per-year per-pitch-type percentile ranking, and inclusion as one z-scored CS+ component. A separate "Will's 2026 formula-anchored vintage" exists only as sample data under `data/sources/samples/`.

## Inputs

**A. tjStuff+** — all from the **MLB StatsAPI live game feed** (`https://statsapi.mlb.com/api/v1.1/game/.../feed/live`), ingested by `statcast_metrics.py` (cached via `feed_cache`; cache version `v5` added the acceleration/release fields specifically for tjStuff+, `statcast_metrics.py:47-48`). Field mapping (`statcast_metrics.py:989-1008`): `velo`←`pitchData.startSpeed`, `spin`←`pitchData.breaks.spinRate`, `extension`←`pitchData.extension`, `ax/az`←`pitchData.coordinates.aX/aZ`, `x0`←`coordinates.x0`, `release_height`←`coordinates.z0`, `pitcher_hand`←`matchup.pitchHand.code`, `pitch_type`←`details.type.code`. Coverage is park/feed dependent (MLB + AAA + some complex parks; `TRACKED_LEVELS = {"MLB","AAA","AA","A+","A","CPX"}`, `statcast_metrics.py:66`). No dependency on any other documented stat.

**B. aStuff+** — per-pitch CSVs from **Baseball Savant statcast-search-minors** (`minors=true`, per-pitcher `pitchers_lookup`, regular season (`hfGT=R`), AAA 2023+; URL template `stuff_plus_aaa.py:77-85`), cached at `.cache/aaa_pitches/{mlbam}_{season}.csv` keeping columns `pitch_type, release_speed, release_spin_rate, release_extension, pfx_x, pfx_z, release_pos_x, release_pos_z, arm_angle, p_throws, delta_run_exp` (`:87-89`). Pitcher pool per season = Savant minors aggregate rows (`arkmetric_forward_eval.savant_rows`, `arkmetric_forward_eval.py:89-107`) ∩ pitchers whose highest MiLB level that season was AAA (`_aaa_mlbams`, `:110-119`) with `pa ≥ 50` (`stuff_plus_aaa.py:138-149`). Label `delta_run_exp` is Savant's own per-pitch run value. Forward eval additionally reads `data/debuts.json` and `milb_history` MLB rows (`:373-403`). No dependency on other documented stats.

**C. pStuff+** — from the served statline (`sl`): `k_pct`, `bb_pct` (per-batter rates), `hr_per_9`, `ip`, `batters_faced`/`tbf`, `is_pitcher`, `level` — ultimately from the tracker's own MLB StatsAPI MiLB stats ingest (career_stats rows). Baselines from `level_norms.compute_level_norms` (`level_norms.py:176-385`): `avg_pitcher_k_pct`, `avg_pitcher_bb_pct`, `avg_hr_per_9` (means) and `std_pitcher_k_pct`, `std_pitcher_bb_pct`, `std_hr_per_9` (population stdevs). Level norms are themselves computed stats (see next section) but depend on nothing else in the documented list.

**D. FVStuff+** — consensus 20–80 tool grades `fb`, `sl`, `cb`, `ch` from the scouting-source ingest (per-tool consensus in `storage.py`), plus FG plus/minus extras `frame`, `athl`, `delivery` (−2..+2). Cohort statistics computed over the exported prospect payloads themselves. No dependency on other documented stats.

**E. CollegeSavant Stuff+** — vendored payload fields only (`stuff_plus` per pitcher and per pitch type in `pitcher_pitch_data_*.js`); upstream inputs are college TrackMan kinematics, external to this repo.

Cross-list dependencies (consumers, detailed in section 6): `pal` consumes B; **`efv`/`xfv` consumes B** (as the residualization baseline inside the shipped uncapped statcast overlay — the E-STUFF *direct-feature* overlay is the thing that was gated and never shipped); `value_framework`-adjacent trade policy (`bayes_trade_value.py`) consumes A, C, D; `collegesavant_plus` (CS+) consumes E.

## Constants, baselines & normalization

**A. tjStuff+**
- `TJSTUFF_TARGET_MEAN = 0.0035`, `TJSTUFF_TARGET_STD = 0.0068` — code literals (`mlb_stuff_plus.py:37-38`), taken from the author's notebook (cell 30 prints the 2024 prediction distribution as xRV/100: mean 0.35, sd 0.68 — comment `:35-36`). **Static** — never recomputed locally; the baseline population is MLB 2024 as measured by the model author, not any local pool.
- Scaling: `100 − 10z`, clamp `[20, 180]`, round 1 dp (`:180`). `FASTBALL_TYPES = {"FF","SI","FC","FT"}` (`:39`).

**B. aStuff+**
- Code literals (`stuff_plus_aaa.py:68-75`): `SEASONS=(2023,2024,2025,2026)`, `TRAIN_SEASONS=(2023,2024)`, `VALID_SEASON=2025`, `MIN_POOL_PITCHES=300`, `SHRINK_K=300`, `THROTTLE_S=1.2`, `SEED=20260611`, `CURRENT_TTL_DAYS=14`.
- Baseline population: per-pitcher mean predicted RV over **qualified AAA 2025** pitcher-seasons (≥300 pitches). `mu`/`sd` are **recomputed at every `score()` run** (i.e., every monthly 6b2b re-score) but over the fixed most-recent-complete season, so current-season (2026) scores ride the last complete pool's scale (documented in-code `:280-282`). Scaling: `100 + 10·(mu − shrunk_rv)/sd`, shrink k=300 toward `mu`, round 1 dp, **no clamp** (also recorded in `data/_am_crossmodel_map.json:1735`). The `aaa_physics_export` re-derivation records the concrete pool numbers in `data/aaa_physics.json` `meta.astuff_scale` (`pool_mu_rv`, `pool_sd_rv`, `pool_n`).

**C. pStuff+**
- Weights `0.55 / 0.30 / 0.15` (K/BB/HR9), scale `100 + 10·composite`, clamp `[0, 250]` — code literals (`storage.py:228, 234-235`).
- Baseline = the pitcher's **current MiLB/MLB level**, computed by `level_norms.py` from the tracker's own career rows. Lookback: `cutoff_year = today.year − DEFAULT_SEASONS_WINDOW` (=2) used as an INCLUSIVE lower bound with `season < cutoff_year` skipped (`level_norms.py:49, :193, :225`) — i.e., in 2026 the window spans seasons 2024, 2025 AND the in-progress 2026 (up to 3 calendar seasons, deliberately including the current one, `:188-190`). Sample filters `MIN_IP_PITCHER = 10.0` per row (`:44`), sanity ranges (`:246-267`: ERA 0<x<30, HR/9 0≤x<5, K% 0<x<60, BB% 0≤x<30). Norms are **recomputed at every export** (`level_norms.py:28`). Level mean falls back to static tables below `MIN_SAMPLE_N = 30` rows (`:54`; `FALLBACK_PITCHER_K_PCT_NORM` / `..._BB_PCT_NORM` at `:144-149`, `FALLBACK_HR9_NORM` at `:138-140`). Sigma = empirical population stdev per level when the level has ≥30 samples (`_std_or_none(..., 30)`, `:293-302, :380-382`), else `0.15 × mean` (rule of thumb, `storage.py:201-218`).

**D. FVStuff+**
- Power-mean exponent `_TOOLS_POWER_MEAN_P = 3.0` (`storage.py:166`); FG plus/minus→FV map −2→30 … +2→70 (`_fg_pm_to_fv`, `:253-264`); overall blend `0.65·stuff + 0.35·cmd` (`:407`).
- Baseline population: **all serialized prospects** (actives + inactives + graduates, one shared cohort — `storage.py:14835-14841`); population variance (`:533-535`). Recomputed every export. Scaling `100 + 10z`, round to int, clamp `[0, 250]` (`_index_plus`, `:144-156`).
- Green-flag threshold on the plus scale: ≥115 (`storage.py:586-599`; second site `stat_flags.py:428` `TOOL_PLUS_GREEN = 115`, applied `:544-564` to both `composite_stuff_plus` and `composite_cmd_plus`). **The "≤85 red flag" exists only in a comment** (`storage.py:557-559` says "≥115 / ≤85") — no code path emits a red Stuff flag; the only composite red flag is Tool ≤40 (`storage.py:600-613`, `stat_flags.py:426, 529-542`).

**E. CollegeSavant Stuff+** — external ratio scale (100 = college-average xRV, 0 = worst observed); no local constants beyond display percentile pools per year (pool ≥2, percentile clamped 1–99, `pitcher_app.js:614-616`).

## Edge cases & guardrails

**A. tjStuff+**
- Model artifact missing or joblib unimportable ⇒ rows returned unscored (`mlb_stuff_plus.py:51-64, 129-131`); `statcast_metrics` wraps the call in try/except and proceeds without scores (`statcast_metrics.py:809-813`).
- Pitches without parseable `hb`+`ivb` never enter the tracked set (`statcast_metrics.py:1010-1012`); `_finalize_pitch` also requires a `pitch_type` (`:803-806`).
- Any missing feature (velo/spin/extension/az/ax/x0/z0 or primary-FB attributes) ⇒ that pitch is skipped, not imputed (`:110-111`). No fastball at all and no typed pitches ⇒ no pitches scored (`:148-150`).
- Missing `pitcher_hand` defaults to `"R"` (`:138`).
- Clamp 20–180. **No minimum pitch count** for the per-type `avg_stuff_plus` (a 1-pitch type gets a value); the frontend percentile display requires ≥5 same-level peer pitches of that type (`prospx/index.html:44484`).
- Consumer guard: `bayes_trade_value._stuff_or_league_avg` defaults to 100.0 only when the value `is None` (a genuine 0.0 is kept — `bayes_trade_value.py:1959-1974`). **But** the §STUFF+ CEILING block still uses the old `or 100` idiom (`bayes_trade_value.py:960, 963`), which would promote a literal 0.0 to league average — moot in practice because the clamp floor is 20.

**B. aStuff+**
- Pitch rows without parseable `release_speed` or `delta_run_exp` are dropped (`stuff_plus_aaa.py:164-169`); other features are imputed with fixed neutral values (spin 0.0, extension 6.0 ft, pfx 0.0, release_z 5.5 ft, arm_angle 30.0°, `:174-183`).
- Pitcher-season scored only at ≥50 pitches (`:288-289`); pool membership needs ≥300; scores below 300 pitches are shrunk toward the pool mean (k=300). Empty pool ⇒ `RuntimeError` (refuse to score, `:308-309`).
- `refresh()` no-ops when the model artifact is absent (`:364-366`); fetch failures fall back to a stale cached CSV ("stale beats nothing", `:125-127`); closed-season caches are immutable, current season on a 14-day TTL (`:112-115`).
- Per-type rows: typeless pitches count in the pooled score but drop from `by_type` (`:294-302`).
- Forward eval gates: graduates 2024+ (`:387-388`), strictly pre-debut AAA season (`:390`), ≥100 MLB BF (`:400`); correlations reported only at n≥8 (`:405-407`).

**C. pStuff+**
- Pitchers only; sample gate `ip ≥ 20 OR bf ≥ 30` (`storage.py:189-200`). Per-component: missing value, missing/zero level mean, or σ≤0 ⇒ that z is None (`:201-224`); all three components None ⇒ `None` (`:230-231`). Weights renormalize over present components (a K%-only line is scored on z_K alone). Clamp `[0, 250]`. JS mirror has identical gates plus `_clampPlus` (`prospx/index.html:52472-52475, 52853-52876`); leaderboard column additionally requires `minIP: 15` display support (`:18156-18157`).
- Downstream gating: breakout indicator uses `stf_plus_periph ≥ 105` (`_BREAKOUT_PITCHER_STF_PLUS_GATE`, `storage.py:629`, applied `:961-967`) or `≥ 115` (stat-only gate `_BREAKOUT_STAT_STF_PLUS_GATE`, `:660`, applied `:823-836` under pitcher age ≤ 23).

**D. FVStuff+**
- Grades outside 20–80 discarded; grades snapped to 0.5 before compositing (`storage.py:359-369`). No graded pitch and no physicals ⇒ `composite_stuff = None`. Cohort needs ≥2 samples and σ>0 for the plus index, else `None` (`:530-535`, `_index_plus:153-154`). Clamp `[0, 250]`. Two-way players get the plus stamped on `hitter_payload`/`pitcher_payload` sub-dicts with the shared cohort norms (`:548-556`).

**E. CollegeSavant Stuff+** — null/empty coerced to `null` (`pitcher_app.js:548`); unscored pitches rendered as `--`; explicitly display-only (its use as a college→A translation covariate FAILED its gate and is OFF — registry `college_stuff_translation`, `deprecated`).

## Dependencies & discrepancies

**Feeds (consumers of these stats):**
- **eFV (SHIPPED, production)**: `efv_statcast_overlay.py` — the uncapped live overlay (registry `xfv_statcast_overlay_uncapped`, **SHIPPED default-ON 2026-07-24b**, verdict `provisional`, eval `data/xfv_overlay_uncapped_eval.json`) — consumes **aStuff+** as `astuff_pool` from `data/aaa_physics.json`: each AAA pitcher leg (velo/spin/vaa) is residualized ON the season's `astuff_pool` with coefficients FROZEN in `data/aaa_physics_screen_eval.json` (`resid_fit_on_astuff` + `resid_sd`, loaded `:120-137`; legs built `:184-236`, astuff read `:205-222`), composite = equal-weight mean of directed leg z's, `delta_fv = clamp(0.6 · composite, ±12)` (`BETA_FV_PER_RESID_Z=0.6`, `DELTA_CAP_FV=12.0` numerical-safety only, `:87-94`), default ON (`OVERLAY_HIT_DEFAULT/OVERLAY_PIT_DEFAULT = True`, `:87-88`; env overrides `EEPHUS_XOVERLAY_HIT/PIT`). Called from the live eFV scorer at `efv_score.py:59, 1728-1737`. Gates: AAA legs need current tracked season/level = AAA with ≥100 physics pitches (`MIN_PITCHES`), vaa leg additionally ≥50 VAA-computable pitches; at most ONE velo-family leg (A-ball signal vs AAA residual, larger sample wins, `:224-234`). **Consequence: rescaling aStuff+ silently invalidates the frozen coefficients and moves served eFV grades** (`docs/efv-2026-07-29/GATED_CANDIDATES.md:83-88`). The *direct-feature* E-STUFF overlay is a different thing and stayed unshipped (registry `xfv_pitcher_stuff`, `deprecated`, zero trainable coverage; also `xfv_tbs2`, `deprecated`).
- **PAL** (`pal` in the documented list): `pal_conversion.astuff_composite` / `astuff_to_quality` / `stuff_read` (`pal_conversion.py:230-266`) blend the usage-weighted per-type **aStuff+** composite 50/50 (`PAL_XRV_W = 0.5`, `:227`) with the incumbent est_wOBA stuff read for covered arms — coverage gate in `pal_export.aaa_coverage` (`pal_export.py:334-346`: sidecar season ∈ {season, season−1} and ≥`PAL_XRV_MIN_PITCHES = 100`, `pal_conversion.py:226`). Mapping: `astuff_to_quality = clamp(50 + 2.5·(aStuff+ − 100), 0..100)` (`:247-253`). The ARM-2 pitch-add ranking consumes `meta.league_xrv_by_type` (`recommend_pitch`, `pal_conversion.py:817-838`; block comment `:776-816`). BOTH arms are env-gated default OFF: ARM-1 `EEPHUS_PAL_XRV`, ARM-2 `EEPHUS_PAL_XRV_RECO` (`pal_export.py:613-614`); registry `pal_stuff_xrv` (`provisional`).
- **Trade policy** (`bayes_trade_value.py`, part of the trade-value surface adjacent to `value_framework`): consumes **tjStuff+** via `pitch_movement.pitch_summary` (`_pitcher_stuff_summary` `:1977-1991`; Stuff+ ceiling penalty `:949-970` — primary-pitch Stuff+ < 95 ⇒ penalty `min(0.4, (95−sp)/25)`), **pStuff+** (`stf_plus_periph`, `:1829` red-flag helper, `:2485` breakout-starter floor ≥105, `:2496`), and **FVStuff+** (`composite_stuff_plus`, `:2162-2177` and many policy gates). Policy thresholds live in `value_framework_config.yaml:905-941` (e.g. `min_primary_stuff_plus: 105.0`, `max_composite_stuff_plus: 90.0`, `min_composite_stuff_plus: 115.0` for young_elite_stuff_pitcher).
- **CS+** (`collegesavant_plus`): consumes CollegeSavant Stuff+ as one component of the pitcher "stuff & whiffs" family (`collegesavant/pitcher_app.js:409-414`).
- **TBS** (prospect tiebreaker) weights pStuff+ 0.08 for pitchers (`_stuffPlusTBS` `prospx/index.html:11038-11047`, read `:11161`, weight `[_tbsNorm(stf, 80, 130), 0.08]` at `:11179`); breakout flag gates on pStuff+ (above); spotlights polarity/token tables carry it (`spotlights.py:48, 101`); prospect stat flags emit green chips at ≥115 (`stat_flags.py:428, 544-564`); MLB player pages join aStuff+ (`mlb_player_export.py:609-615`; rendered `assets/projections.js:1727, 1882`).

**Consumes:** none of the other documented stats (efv, xfv, rem/sem/hem, wag, swing_plus, draft_stock_plus, value_framework) feed any Stuff+ variant.

**Discrepancies / multi-implementation notes:**
1. **Five scales under one name** — including an inverted sign: tjStuff+ is `100 − 10z` clamped 20–180 while aStuff+/pStuff+/FVStuff+ are `100 + 10z`; CollegeSavant is a ratio scale where 130 is "barely plus". Documented as the canonical trap (`ARKMETRIC_SCALE_CONVENTIONS.md:47-50, 60, 69, 73-77`). Never merge columns across variants. (Side note: that doc's FVStuff+ row says "active prospect cohort"; the code cohort also includes inactives + graduates.)
2. **pStuff+ historical Python/JS divergence** — resolved 2026-07-29; JS now prefers the server-baked value and its fallback mirrors the exact formula (`prospx/index.html:52826-52877`; registry `stf_plus` row records the old divergence: per-9 unweighted, σ hardcoded, pool sd 53.6 vs 6.1). Residual dead code: `sl.stf_plus` read at `prospx/index.html:11043` can never hit.
3. **aStuff+ dual computation** — `stuff_plus_aaa.score()` (served sidecar, most-recent season per pitcher) vs `aaa_physics_export._score_astuff()` (display sidecar, EVERY cached season per pitcher), same bundle/conventions with a recorded `served_json_agreement` max-abs-diff check (`aaa_physics_export.py:273-284`). The shipped eFV overlay reads the *physics* sidecar's `astuff_pool`, so the agreement guard is load-bearing for eFV too.
4. **Glossary vs code (FVStuff+)** — glossary `stuff_grade_plus` formula omits the Frame/Athl/Delivery inputs that `storage.py:388-400` includes in the power mean, and its "active-prospect cohort" phrasing understates the actives+inactives+graduates cohort (the `tool` entry documents the physicals correctly, `glossary.json:40-41`). All other glossary formulas (`stf_plus`, `stuff_plus_aaa`) agree with the code.
5. **Comment-only red flag** — `storage.py:559`'s "(≥115 / ≤85)" comment promises a ≤85 red Stuff flag that no code emits (neither `storage.py:586-613` nor `stat_flags.py:544-564`); only the ≥115 green flag is real.
6. **Registry anchors** — `data/model_registry.json` rows: `stuff_plus_external` (unvalidated, external), `stuff_plus_aaa` (provisional, eval `data/stuff_plus_aaa_eval.json`), `stf_plus` (unvalidated display index), `fv_stuff_plus` (unvalidated display index), `collegesavant_stuff` (provisional governance row, eval `data/collegesavant_stuff_eval.json`), `xfv_statcast_overlay_uncapped` (provisional, SHIPPED — the eFV astuff_pool consumer), plus experiment rows `pal_stuff_xrv` (provisional), `xfv_pitcher_stuff` (deprecated), `xfv_tbs2` (deprecated), `college_stuff_translation` (deprecated), `aaa_physics_screen` (provisional). Human-readable mirror: `MODEL_REGISTRY.md:36-37, 193-194`. Neither model artifact is hash-pinned; pinning is path + registry row + in-bundle meta (aStuff+ only).

### Verification log
Corrections made against the draft (all verified in code 2026-08-01):
1. **MAJOR — "eFV/xFV consumes no Stuff+" was FALSE.** The shipped, default-ON uncapped statcast overlay consumes aStuff+ (`astuff_pool` from `data/aaa_physics.json`) as the residualization baseline for its AAA velo/spin/vaa legs: `efv_statcast_overlay.py:87-88` (defaults True), `:120-137` (frozen `resid_fit_on_astuff` coefficients), `:205-222` (astuff_pool read), called from the production eFV scorer at `efv_score.py:59, 1728-1737`; registry `xfv_statcast_overlay_uncapped` "SHIPPED default-ON" (`data/model_registry.json:2239-2247`). The draft's claim was true only of the *direct-feature* E-STUFF overlay (`xfv_pitcher_stuff`, deprecated). Rewrote the Inputs cross-list, Dependencies lead, and labs note; added the `GATED_CANDIDATES.md:83-88` rescale warning.
2. **"Elite/red flag thresholds ≥115 / ≤85" was half-false.** The ≤85 red flag exists only in a comment (`storage.py:557-559`); no code emits it — `storage.py:586-599` emits only the ≥115 green Stuff flag and `:600-613` a Tool ≤40 red; `stat_flags.py:544-564` likewise green-only (`TOOL_PLUS_GREEN=115`, `stat_flags.py:428`). Rewrote constant D and added discrepancy #5.
3. **Added missed consumer sites**: `stat_flags.py:428, 544-564` (`composite_stuff_plus`/`composite_cmd_plus` green chips) and `assets/projections.js:1727, 1882` (aaaStuffPlus tile ≥110/≤90 + share card). Also `mlb_player_export` join detail: origin-gated (ex-PROSPX graduates only), fields `aaaStuffPlus/aaaStuffN/aaaStuffSeason` (`mlb_player_export.py:609-615`).
4. **level_norms window precision**: "2-season window" is actually `cutoff_year = today.year − 2` used as an inclusive lower bound (`level_norms.py:193, 225`) ⇒ up to 3 calendar seasons including the in-progress one.
5. **ARM-2 gate added**: the pitch-add ranking is env-gated default OFF (`EEPHUS_PAL_XRV_RECO`, `pal_export.py:614`), not unconditionally live; draft only flagged ARM-1's `EEPHUS_PAL_XRV`. Also corrected `recommend_pitch` cite to `pal_conversion.py:817-838` (the `:776-822` range was the comment block) and added the `astuff_to_quality` mapping formula (`:247-253`).
6. **tjStuff+ pre-filter added**: pitches must have parseable `hb`+`ivb` to be collected (`statcast_metrics.py:1010-1012`) and `hb`/`ivb`/`pitch_type` to enter `_finalize_pitch` (`:803-806`).
7. **run_monthly step-3d-ter skip gate added**: skips when ≥90% of the eligible pool is fresh, or under `--fast` (`run_monthly.py:2984-2985, 3001-3014`).
8. **bayes_trade_value nuance**: the §STUFF+ CEILING block still uses the `or 100` idiom (`bayes_trade_value.py:960, 963`); the `is None` guard applies only in `_pitcher_stuff_summary`.
9. **Citation fixes**: MODEL_REGISTRY.md rows are `:36-37` (draft said `:37`); TBS 0.08 weight is at `prospx/index.html:11179` (draft cited only `:11161`); `_fg_pm_to_fv` is `:253-264` (draft `:253-259`); `_attach_tool_plus_indices` runs to `:613`; `_compute_tool_composites` def at `storage.py:342`; aStuff+ pill `:52963-52975`; `getAaaStuffPlus` `:30958-30973`; `_aaa_mlbams` `:110-119`; forward-eval graduates gate `:387-390`.
10. **aaa_physics_export scope difference documented**: `_score_astuff` scores every cached pitcher-season ≥50 pitches (per-season blocks) vs `score()`'s most-recent-only; per-type `astuff` attaches only to ≥10-pitch by_type rows.
11. **Precision additions**: `_pitcherCompositeStuffPlusFromSc` weight fallback chain (usage → count → 1, `prospx/index.html:44462`); CollegeSavant percentile pool ≥2 / clamp 1–99 (`pitcher_app.js:614-616`); aStuff+ params also carry `n_jobs=4, verbose=-1`; FVStuff+ glossary "active-prospect cohort" wording vs the actives+inactives+graduates code cohort; `xfv_pitcher_stuff` gate result is INCONCLUSIVE (zero trainable coverage), not FAIL.
12. **Verified byte-exact (no change needed)**: both joblib artifacts introspected live — tjStuff+ Pipeline(RobustScaler→LGBMRegressor) hyperparams + importances + `feature_names_in_` + 3,092,328-byte file; aStuff+ bundle meta (trained 2026-06-12, 1,194,987 train / 571,467 valid pitches, r 0.0213 / 0.2797, n=638) matches `data/stuff_plus_aaa_eval.json` exactly; all constants (`TJSTUFF_TARGET_*`, `SHRINK_K`, weights 0.55/0.30/0.15, p=3, 0.65/0.35 blend, clamps); glossary `stf_plus` + `stuff_plus_aaa` formulas; the `stuff_grade_plus` physicals omission; all registry verdicts; `ARKMETRIC_SCALE_CONVENTIONS.md` line cites; CollegeSavant agreement r 0.9594 (`data/collegesavant_stuff_eval.json:128`); the dead `sl.stf_plus` branch (zero server writes); breakout gates 105/115; `value_framework_config.yaml` thresholds; PAL constants 0.5/100.


---

# pal

## Name in code & where computed

**In-code names (casing matters):**
- `fit` — the deliverable 0-100 FIT score, one per direction: **RP->SP FIT** (key `rp2sp` in the artifact) and **SP->RP FIT** (key `sp2rp`). Computed by `pal_conversion.rp_sp_fit()` (`prospect-tracker/pal_conversion.py:318-348`) and `pal_conversion.sp_rp_fit()` (`pal_conversion.py:526-552`).
- Sub-quantities exported alongside: `relief_upside`, `components` (per-component 0-100 scores), `conversion_need`, `proj_velo`, `starter_shape` / `mismatch` / `mismatch_margin` (prospect watch, `pal_conversion.prospect_role_fit()`, `pal_conversion.py:448-485`), `reverse_index` (`reverse_platoon()`, `pal_conversion.py:413-431`), `pitch_add`/`rec` (`recommend_pitch()`, `pal_conversion.py:817-867`), `proj_relief_rem_plus` (`project_relief_rem_plus()`, `pal_conversion.py:558-574`), and conversion-history rows from `detect_conversions()` (`pal_conversion.py:599-646`) + `detect_in_progress_conversions()` (`pal_conversion.py:658-710`, thresholds at `:653-655`).

**Computation sites:**
1. `prospect-tracker/pal_conversion.py` — the pure scoring engine (no network). All FIT math lives here.
2. `prospect-tracker/pal_export.py` — the assembly/export layer. `export()` (`pal_export.py:535-805`) pulls inputs, builds `PalArm` objects (`build_arm()`, `pal_export.py:372-388`; `p_throws`/`was_starter`/`prospx_role`/`aaa_by_type` are attached after construction at `:628-632`), calls the scorers, and writes **`data/pal.json`** (`OUT_PATH`, `pal_export.py:70`). This is the only writer of the served artifact.
3. `prospect-tracker/pal_gamelogs.py` — game-log infrastructure (Lane A mid-year switch recovery, Lane B stamina features). **NOT called by `pal_export.py`**; lab-only consumers: `tools/pal_backtest_lab.py` (import at `:472`; used at `:672,701,708,711,727,746,799` — `swing_seasons`, `recover_events`, `detect_midyear_switch`, `appearances`, `relief_usage_features`) and `tools/fantasy_startscore_lab.py` (import at `:113` — reuses only the game-log fetch/cache infra, `.cache/pal_gamelogs`). The Lane-B variant `pal_conversion.rp_sp_fit_v2()` (`pal_conversion.py:375-410`, `RP_SP_WEIGHTS_V2 = {**RP_SP_WEIGHTS, "stamina_usage": 0.10}` at `:359`, `stamina_usage_score` at `:364-372` with `STAMINA_MI_FULL=0.50` / `STAMINA_B2B_FULL=0.40`) is a gated candidate — registry note: "Lane B stamina lane FAILED ... nothing live calls it" (`data/model_registry.json` `pal_gamelog_lanes` row, ~line 1467-1477).
4. **`prospect-tracker/efv_model.py:812-841` re-implements the `prospect_role_fit` shape composite inside the eFV feature builder `_vec()`** (the draft's "single computation site" claim needed this): depth counted over RAW `tool_fb/tool_sl/tool_cb/tool_ch` only (deliberately **minus `tool_ct`**, which the pre-debut anchor never captures), same step table `{0:5.0, 1:15.0, 2:45.0, 3:80.0}.get(depth, 100.0)`, `cmd_s = 50.0 if cmd is None else clamp((cmd-40.0)/20.0*100.0, 0, 100)`, `shape = round(0.60*depth_s + 0.40*cmd_s, 1)`, plus `relief_flag = 1.0 if shape < 40.0 else 0.0`. Zero observed pitch grades fall back to neutral imputes `_SHAPE_IMPUTE = 38.9`, `_DEPTH_IMPUTE = 1.6` (`efv_model.py:729-730`). **These keys (`starter_shape`, `arsenal_depth`, `relief_flag`) are emitted-but-INERT: they are never listed in `_FEATURES_PIT`** (`efv_model.py:145-274`), because the RELIEF-SHAPE gate FAILED 2026-07-15 (best pooled -0.0021; "arms SPENT, do not re-attempt blind" — comment at `efv_model.py:812-826`; ledger `data/xfv_relief_shape_eval.json`; lab `tools/efv_relief_shape_lab.py`). So PAL's shape formula has a second, inert home in eFV, and there is still **no production feedback of any PAL quantity into eFV/xFV**.

**Production path:** `run_monthly.py` step "6b5. Alchemy Lab (pal.json)" (`run_monthly.py:3556-3567`) calls `pal_export.export()`; best-effort (exception logged "alchemy lab export failed - continuing", never aborts). There is no `run_daily.py` **file**, but a daily pipeline DOES exist: `run_daily()` is a function inside `run_monthly.py` (`run_monthly.py:860`, invoked via the `--daily` CLI flag at `:3855`, and tail-chained by the monthly `main()` at `:3767`). It does **not** call `pal_export` (grep: the only `pal` reference in the pipeline is step 6b5), so PAL refreshes only on the monthly full run. Frontends are display-only:
- `assets/pal.js` fetches `/data/pal.json` (`DATA_URL` at `assets/pal.js:24`, fetched at `:1175`) and renders `fit` verbatim (`fitClass` at `assets/pal.js:158-165` is a CSS-class chooser only: >=70 `pal-hi`, >=55 `pal-good`, >=42 `pal-mid`, else `pal-lo`; null -> `pal-mid`; no recompute).
- `prospx/index.html:31183-31239` joins `prospect_watch_all` (fallback `prospect_watch` on old payloads) by `player_key` with a deaccented `name|org` fallback for the pitcher-card role-mismatch chip — display-only; hidden when the artifact is absent or the prospect is not in the watch.
- `build_site.py:2425-2440` reads `pal.json` (`_cached_data_json("pal.json")` at `:2427`) for a homepage drawer card: top **3** RP->SP candidates by `fit`, rendered as `round(fit)` — display-only.

**Serving:** the `/pal/` page dir is in `deploy/publish_paths.txt:27`; `data/` top-level JSON ships via the deploy consumers' separate data handling, and neither `pal.json` nor `pal_eval.json` appears in `deploy/data_exclude.txt`. The /pal/ page is stamped beta (`build_site.py:3012`, `MODULE_STAGE["pal"]`).

**Labs (not production):** `tools/pal_backtest_lab.py` (writes `data/pal_eval.json` — a shipped artifact: `pal_export._verdict()` at `pal_export.py:851-856` reads its `verdict.status` into the payload, defaulting to `"provisional"` when the file is absent/unreadable), `tools/pal_xrv_lab.py` (`data/pal_stuff_xrv_eval.json`), `tools/c3_pal_fa_recal_lab.py` (`data/c3_pal_fa_recal_eval.json`), `tools/era_shrink_unification_lab.py` (`data/era_shrink_unification_eval.json`), `tools/efv_relief_shape_lab.py` (`data/xfv_relief_shape_eval.json`). `tools/velo_decline_lab.py:87-88` reuses `pal_export.load_velo` as a data loader (lab only).

**Caution — same page, different stat:** the /pal/ page also has a "Position Fit" tab (`build_site.py:3022`) fed by `data/positional_fit_ui.json`, built by `build_site.build_positional_fit_payload()` (`build_site.py:3703`, wired at `build_site.py:4146`) from `data/positional_fit.json` — a hitter position-change model (its Rng+ meter is registry row `savant_sprint`, `data/model_registry.json` ~line 2917; the full `positional_fit.json` is deploy-excluded and never served). It is **not** part of the PAL conversion FIT documented here. `assets/pal.js` lazy-loads it separately (`POSFIT_URL` at `assets/pal.js:38`).

## Formula or fitted model?

**Deterministic formula.** A transparent weighted blend with frozen literature-prior weights — explicitly "a SCREEN, not a success-probability model" (`pal_conversion.py:6-35`). No trained artifact, no library. The backtest (`data/pal_eval.json`) only sign-checks; it never fits weights.

All component scores are 0-100 via `_clamp(x, 0, 100)` (`pal_conversion.py:77`).

### Shared arsenal-derived features (`pal_conversion.py:132-176`)
```python
FASTBALLS = {"FF", "SI", "FC", "FT"}
n_pitches(arm, min_usage=0.10)   # count of arsenal pitches with usage >= 0.10
fb_pct(arm)                      # sum of usage over FASTBALLS; None if no arsenal
top_pitch_share(arm)             # max usage; 0.0 if no arsenal
overall_est_woba(arm)            # usage-weighted mean of per-pitch est_woba; None if no weight
best_whiff(arm)                  # max per-pitch whiff; None if none present
overall_hard_hit(arm)            # usage-weighted mean of per-pitch hard_hit; None if no weight
```

### Component scorers (`pal_conversion.py:182-219`)
```python
arsenal_depth_score(n) = {0: 0.0, 1: 12.0, 2: 45.0, 3: 80.0}.get(n, 100.0)
command_score(bb_pct)   = 50.0 if None else clamp(100*(0.12 - bb_pct)/(0.12 - 0.05))
fb_reliance_inv(fb)     = 50.0 if None else clamp(100*(1 - clamp((fb - 0.50)/0.35, 0, 1)))
stuff_quality_score(w)  = 50.0 if None else clamp(100*(0.400 - w)/(0.400 - 0.280))   # w = overall_est_woba
putaway_score(whiff)    = 40.0 if None else clamp(100*(whiff - 0.08)/(0.35 - 0.08))
survivability_score(hh) = 50.0 if None else clamp(100*(0.45 - hh)/(0.45 - 0.30))
platoon_neutrality_score(vl, vr) = None if either None
                        else clamp(100*(1 - clamp(|vl - vr|/0.25, 0, 1)))
```

### Stuff read (shared by both FITs, `pal_conversion.py:256-266`)
```python
base = stuff_quality_score(overall_est_woba(arm))
comp = astuff_composite(arm.aaa_by_type)     # own-AAA-pitch-count-weighted aStuff+ (100+10z), pal_conversion.py:230-244
if comp is None: return base                 # default path in production
return PAL_XRV_W*base + (1-PAL_XRV_W)*astuff_to_quality(comp)   # PAL_XRV_W = 0.5
# astuff_to_quality(c) = clamp(50.0 + 2.5*(c - 100.0))          # pal_conversion.py:247-253
```
The aStuff+ branch runs **only** when env `EEPHUS_PAL_XRV` is set AND the pitcher clears the AAA coverage gate (`pal_export.py:613, 631-632`; gate in `aaa_coverage()`, `pal_export.py:334-346`: sidecar season == scored season or the prior one, AND sidecar `n_pitches >= PAL_XRV_MIN_PITCHES = 100`). It is default OFF and `run_monthly.py` never sets the flag, so production stuff reads are the incumbent est_woba path.

### Blend (`pal_conversion.py:269-277`)
```python
def _blend(weights, comps):    # weighted mean over PRESENT components, renormalized
    num = den = 0.0
    for k, w in weights.items():
        v = comps.get(k)
        if v is not None:
            num += w * v; den += w
    return round(num / den, 1) if den else 0.0
```

### RP->SP FIT (`rp_sp_fit`, `pal_conversion.py:318-348`)
```python
RP_SP_WEIGHTS = {"arsenal_depth": 0.35, "command": 0.20, "fb_reliance_inv": 0.15,
                 "stuff_quality": 0.10, "platoon_neutrality": 0.12, "survivability": 0.08}
comps = {arsenal_depth_score(n_pitches), command_score(bb_pct), fb_reliance_inv(fb_pct),
         stuff_read, platoon_neutrality_score(ops_vl, ops_vr), survivability_score(overall_hard_hit)}
fit = _blend(RP_SP_WEIGHTS, comps)
if arm.was_starter:           fit = min(100.0, fit + 3.0)   # PEDIGREE_NUDGE, pal_conversion.py:315
elif arm.prospx_role == "SP": fit = min(100.0, fit + 3.0)   # elif: at most ONE nudge
return round(fit, 1)
```
Flag chips (`_flags_rp_sp`, `pal_conversion.py:302-312`): `relief_only` when `top_pitch_share >= 0.80`; `needs_third` when `n_pitches < 3`; `fb_heavy` when `fb_pct >= 0.85`; `platoon_risk` when platoon-neutrality `< 40`; plus `started_before` / `prospect_sp` from the nudge branch.

### SP->RP FIT (`sp_rp_fit`, `pal_conversion.py:526-552`) — need-gated
```python
SP_RP_UPSIDE_WEIGHTS = {"stuff_upside": 0.35, "putaway": 0.30, "velo_leverage": 0.20, "tto_leakage": 0.15}
upside_comps = {
    "stuff_upside": stuff_read(arm),
    "putaway": putaway_score(best_whiff(arm)),
    "velo_leverage": clamp(((arm.fb_velo or 93.0) - 90.0) / (101.0 - 90.0) * 100.0),
    "tto_leakage": clamp(100.0 - 0.7*arsenal_depth_score(npi) - 0.3*fb_reliance_inv(fb_pct(arm))),
}
upside = _blend(SP_RP_UPSIDE_WEIGHTS, upside_comps)
need   = starter_need_score(arm.era, arm.ip)
factor = 0.30 + 0.70 * (need / 100.0)        # dominant SP -> 0.30x, struggling SP -> 1.0x
fit = round(upside * factor, 1)              # relief_upside = round(upside, 1); conversion_need = round(need, 1)
```
The need gate (`starter_need_score`, `pal_conversion.py:493-509`):
```python
if era is None: return 50.0
if ip and ip > 0:
    era = (ip*era + NEED_ERA_SHRINK_IP*LG_SP_ERA) / (ip + NEED_ERA_SHRINK_IP)  # 45.0 IP pseudo-count toward 4.20
return clamp(100.0 * (era - 3.20) / (5.50 - 3.20))
```
Flag chips (`_flags_sp_rp`, `pal_conversion.py:512-523`): `putaway` when `best_whiff >= 0.30`; `succeeding_sp` when `need < 30`; `struggling_sp` when `need >= 70`; `keep_starting` when `n_pitches >= 4 and command_score >= 70`.

### Velocity role projection (display, `pal_conversion.py:283-296`)
```python
shape = clamp((fb - 0.5)/0.4, 0, 1)*0.6 + clamp((3 - npi)/3.0, 0, 1)*0.4     # fb defaults 0.5 when None
mag   = min(2.2, 1.0 + shape*(2.2 - 1.0))          # BASE_VELO_DELTA=1.0, MAX_VELO_DELTA=2.2
delta = +mag to RP, -mag to SP (round 1); proj_velo = round(fb_velo + delta, 1) (None if fb_velo None)
```

### Prospect watch shape score (`prospect_role_fit`, `pal_conversion.py:448-485`)
```python
depth   = count of tool grades in PROSPECT_TOOL_KEYS = ("fb","sl","cb","ch","ct") that are >= 55
depth_s = {0: 5.0, 1: 15.0, 2: 45.0, 3: 80.0}.get(depth, 100.0)
cmd_s   = 50.0 if cmd is None else clamp((cmd - 40.0)/(60.0 - 40.0) * 100.0)
starter_shape = round(0.60*depth_s + 0.40*cmd_s, 1)
role = "SP" if "SP" in pos else ("RP" if ("RP"|"IRP"|"CL" in pos) else "SWING")
lean = "SP" if starter_shape >= 60.0 else ("RP" if starter_shape < 40.0 else "SWING")   # SHAPE_SP_MIN/SHAPE_RP_MAX, :443-444
mismatch = role and lean both clean SP/RP and role != lean
mismatch_margin = (40.0 - starter_shape) if lean=="RP" else (starter_shape - 60.0), round 1; None if no mismatch
```
`starter_shape` is heavily quantized (the depth term is a four-value step table); the whole pool carries only about two dozen distinct shapes, which is why the watch sort needs a deterministic third key.

### Conversion detection (history section)
`role_of(g, gs, ip)` (`pal_conversion.py:585-596`): `SP` if `gs/g >= 0.60 and ip/g >= 3.5`; `RP` if `gs/g <= 0.10`; else `SWING`; `None` if `g<=0 or ip<=0`. `detect_conversions` (`pal_conversion.py:599-646`) pairs consecutive-on-record seasons `b - a <= 2` with both roles clean SP/RP and both IP >= `CONV_MIN_IP=20.0`; `held` = role in season b+1 equals the new role, only when b+1 is a closed season (`last_closed_season = season-1`, passed at `pal_export.py:557`) with IP >= 20; otherwise `held=None`. In-progress detection (`detect_in_progress_conversions`, `pal_conversion.py:658-710`; constants `:653-655`): current season must read SWING with IP >= 20, prior clean SP/RP role within 2 years (>= 20 IP); `RP->SP` needs `GS >= IN_PROGRESS_MIN_GS=5` and `IP/G >= IN_PROGRESS_MIN_IP_PER_G=2.5`; `SP->RP` needs `gs_cur < g_cur` and relief-appearance share `(g-gs)/g >= IN_PROGRESS_MIN_RELIEF=0.50`; always `held=None`, tagged `in_progress: true`. The export de-dupes in-progress events against historical ones by `(mlbam, year)` (`pal_export.py:562-565`). History rows sort by `(year desc, pre_fit desc)` (`pal_export.py:722`).

### Display-only extras
- `project_relief_rem_plus` (`pal_conversion.py:558-574`): synthetic reliever with `k = min(0.60, k_pct + k_bump)`, `bb = max(0, bb_pct - 0.005)`, `hbp = 0.01*TBF`, `hr = 0.028*TBF` (`_hr_from_arm`, `pal_conversion.py:577-579`), `er=r=0`, `gs=0`, actual IP/TBF, scored by the **REM+** model against the current true-reliever pool (`pal_export._build_rem_pool`, `pal_export.py:419-424`), bypassing `score_pool`'s reliever filter. Returns None if `tbf<=0 or ip<=0 or k_pct is None`. `k_bump` = **median** of (post − pre) K% over detected SP->RP events when n >= 5, else `DEFAULT_RELIEF_K_BUMP=0.025` (`pal_export.py:569-572`); currently measured 0.0164 (`data/pal.json` `backtest.relief_k_bump_measured`). Explicitly never a scored input.
- `reverse_platoon` (`pal_conversion.py:413-431`): `reverse_index = round(own_ops - opp_ops, 3)` (own side = same hand as `p_throws`); `reverse` if `> 0.030`; `extreme` if `|vl - vr| >= 0.150`; also emits `weak_hand`. Returns None without both splits + hand.
- `recommend_pitch` (`pal_conversion.py:817-867`): rule lookup over arsenal family holes (families at min usage 0.05 via `_families`, `pal_conversion.py:760-772`: FB = `{FF,SI,FC,FT}`, BR = `{SL,CU,ST,SV,KC,SC,CS}`, OFF = `{CH,FS,FO}`, sets at `:756-757`). `big_split` = platoon split `>= 0.12`. Rule order: no BR → "Slider" (high); no OFF → "Changeup" (high if big_split else medium); `n_pitches < 3` → "A genuine third pitch" (medium); big split with deep arsenal → "Changeup" vs RHB / "Cutter" vs LHB (medium); else None. Optional xRV re-ranking of family holes (`_best_xrv_type`, `pal_conversion.py:789-800`; candidates `XRV_FAMILY_CANDIDATES = {"BR": (SL,ST,CU,KC), "OFF": (CH,FS)}`; a league mean is only trusted at `XRV_MIN_LEAGUE_N=500` pitches; lower mean_pred_rv = better) runs only when env `EEPHUS_PAL_XRV_RECO` is set (`pal_export.py:614, 640-641`) — see discrepancies.
- `role_success` (`pal_conversion.py:730-743`): RP successful if `era <= 3.50 and (kbb is None or kbb >= 0.12)`; SP if `era <= 3.90 and (kbb is None or kbb >= 0.10)`; None if `ip < 20` or `era` None. Exported as `successful` per candidate row (display tiering only).
- Live backtest stamp (`pal_export.py:654-755`): pre-conversion fits recomputed with the same engine at the true pre-season (`e["pre"]["season"]`, NOT `year-1` — the repaired T1-6 harness), same inputs as the live board (p_throws + pedigree nudge, `:671-672`), Spearman rho (`_spearman`, `pal_export.py:394-416`, tie-averaged ranks, None under n=4) vs `held` and vs `war_delta` (bWAR post − pre, closed post seasons only, `post_season < season`), per direction — reporting only. Also `converter_median_fit_pool_pctile` (`_percentile_of`, `pal_export.py:837-843`).

## Inputs

| Field (codebase name) | Source | Computed stat? |
|---|---|---|
| `G`, `GS`, `IP`, `ER`, `BB`, `SO`, `BF` (+`R`,`HR`,`HBP`,`SV`,`HLD` etc.) per pitcher-season | MLB StatsAPI `stats?stats=season&group=pitching&season=Y&sportId=1&gameType=R&playerPool=all&limit=3000` via `bullpen_export.load_season_pitching()` (`bullpen_export.py:170-212`; drops rows whose primary position is not "P"); years `HISTORY_YEARS = [2018,2019,2021,2022,2023,2024,2025,2026]` (`pal_export.py:73`) | raw. Derived in `build_arm` (`pal_export.py:372-388`): `k_pct = SO/BF`, `bb_pct = BB/BF`, `era = ER*9/ip_float`; IP via `be.ip_to_float` (X.1 = X+1/3, X.2 = X+2/3; `bullpen_export.py:75-84`) |
| `arsenal` rows: `pitch` (pitch_type), `usage`, `whiff`, `est_woba`, `hard_hit` | Statcast bulk via `pybaseball.statcast_pitcher_arsenal_stats(year)` (`pal_export.load_arsenal`, `pal_export.py:85-109`); source columns `pitch_usage`/`whiff_percent`/`hard_hit_percent` divided by 100, `est_woba` as-is | raw (Savant xwOBA is Savant-computed) |
| `fb_velo` | `pybaseball.statcast_pitcher_pitch_arsenal(year)`: `round(max(ff_avg_speed, si_avg_speed, fc_avg_speed), 1)` — note no `ft_` column despite FT in FASTBALLS (`load_velo`, `pal_export.py:112-133`) | raw |
| `ops_vl`, `ops_vr`, `platoon_tbf` | StatsAPI `people/{pid}/stats?stats=statSplits&sitCodes=vl,vr&group=pitching&season=Y&gameType=R` per pitcher-season (`_platoon_one`/`load_platoon`, `pal_export.py:136-172`; ThreadPool `workers=12`); `platoon_tbf` = min battersFaced across hands, surfaced only as `min_tbf` on reverse-platoon rows (`pal_export.py:636`) | raw |
| `p_throws` | StatsAPI `sports/1/players?season=` pitchHand code (`load_pitch_hand`, `pal_export.py:175-188`); for backtest pre-arms the bulk call is merged across each distinct pre-year (`pal_export.py:598-602`) | raw |
| `was_starter` | derived from the same season table: any prior season with `role_of == "SP"` and IP >= 40 (`_was_starter`, `pal_export.py:358-366`) | derived |
| `prospx_role` | prospect position via `data/player_links.json` (`load_player_links`, `pal_export.py:221-226`) joined to the prospect pool (`_prospx_role_for`, `pal_export.py:618-620`; `_prospect_role`, `:349-355`) | derived |
| Prospect tools `fb,sl,cb,ch,ct,cmd`; `fv` (= `fv_close` rounded 1), `position`, `org`, `status` | prospect DB: `storage.load_all_snapshots()` + `consensus.build_timeseries(..., normalize=ADOPT_NORMALIZED_CONSENSUS)`; per player the latest point's `tools_consensus`, falling back to `tools` (`load_prospect_pitchers`, `pal_export.py:244-285`) | consensus scout grades (computed upstream by the consensus module) |
| `fvE` | `xfv_grade` from `data/xfv.json` `by_player` (`_efv_by_key`, `pal_export.py:55-67`) | **depends on efv/xfv** — display field only, never gates or scores |
| `aaa_by_type` (per-type `stuff_plus`, `n_pitches`), `league_xrv_by_type` | `data/stuff_plus_aaa.json` sidecar written by `stuff_plus_aaa.py` (`_load_aaa_stuff`, `pal_export.py:321-331`; path const `:318`) | **depends on stuff_plus** (aStuff+ AAA) — env-gated OFF in production |
| bWAR per pitcher-season | `pybaseball.bwar_pitch(return_all=True)`, summed across in-season stints (`load_bref_pitcher_war`, `pal_export.py:191-218`) | raw (B-Ref); history/backtest only |
| REM+ pool | `bullpen_export.build_relievers` + `rem_plus` module: true relievers only, rates derived (`_build_rem_pool`, `pal_export.py:419-424`) | **depends on rem_plus** — display-only projection |
| `debuts.json`, career MLB IP >= 50 | graduation gates for prospect watch (`_graduated_player_keys` `pal_export.py:230-241`; `MLB_SERVICE_IP=50.0` at `:288` + `_mlb_service_keys`, `:291-307`) | derived |
| `data/pal_eval.json` `verdict.status` | written by `tools/pal_backtest_lab.py`; stamped into payload as `verdict` (`_verdict`, `pal_export.py:851-856`) | lab artifact |

No dependence on `value_framework`, `wag`, `swing_plus`, `collegesavant_plus`, `draft_stock_plus`, `hem_plus`. `sem_plus` appears only as a backtest *baseline* in the registry/lab (`MODEL_REGISTRY.md:52` pal_conversion row: "pre-year REM+ (RP->SP) / SEM+ (SP->RP)"), not in export code.

## Constants, baselines & normalization

PAL FIT is a **0-100 screen, not a 100+10z "+" Arkmetric** — it has no population baseline recomputed per run; every band edge is a hand-set code literal in `pal_conversion.py` (the ARKMETRIC_SCALE_CONVENTIONS doc covers aStuff+ 100+10z, which enters only via the OFF-by-default blend). All constants are code literals:

- Weights: `RP_SP_WEIGHTS` (.35/.20/.15/.10/.12/.08, `pal_conversion.py:57-64`); `SP_RP_UPSIDE_WEIGHTS` (.35/.30/.20/.15, `pal_conversion.py:69-74`). Frozen priors, never fitted.
- Role detection: `SP_GS_SHARE=0.60`, `SP_IP_PER_G=3.5`, `RP_GS_SHARE=0.10`, `CONV_MIN_IP=20.0` (`pal_conversion.py:44-47`); candidate floor `CAND_MIN_IP=20.0` (`pal_export.py:74`).
- Score band edges: BB% 0.12→0 / 0.05→100; FB% band 0.50-0.85; est_wOBA 0.400→0 / 0.280→100; whiff 0.08→0 / 0.35→100 (default 40); hard-hit 0.45→0 / 0.30→100; platoon gap /0.25; velo band 90→0 / 101→100 mph with 93.0 default; step tables `{0:0,1:12,2:45,3:80,else:100}` (MLB) and `{0:5,1:15,2:45,3:80,else:100}` (prospect) — all in `pal_conversion.py:182-219, 466-467, 534`.
- Need gate: `LG_SP_ERA=4.20` (`pal_conversion.py:488`); `NEED_ERA_SHRINK_IP=45.0` in `rate_stabilization.py:50` (single home, imported at `pal_conversion.py:41`; identity-guarded by `test_stabilization_constants.py:57-60`; deliberately ≠ display `K_IP=50` — provenance comment `rate_stabilization.py:39-49`, unification refused in `data/era_shrink_unification_eval.json`); ERA band 3.20→0 / 5.50→100; factor floor `0.30 + 0.70*need/100`.
- Nudges/velocity: `PEDIGREE_NUDGE=3.0` (`pal_conversion.py:315`); `BASE_VELO_DELTA=1.0`, `MAX_VELO_DELTA=2.2` (`pal_conversion.py:50-51`).
- Relief K bump: `DEFAULT_RELIEF_K_BUMP=0.025` prior (`pal_conversion.py:54`), overridden per run by the **median** converter ΔK% when n>=5 (`pal_export.py:569-572`) — the one "recomputed each run" quantity, and it only feeds the display REM+ projection.
- Prospect watch: `SHAPE_SP_MIN=60.0`, `SHAPE_RP_MAX=40.0`, `SHAPE_SWING_BAND=20.0` (`pal_conversion.py:443-445`); `PROSPECT_WATCH_FV_MIN=40.0`, `PROSPECT_WATCH_MARGIN_MIN=10.0` (half the SWING band, a-priori), `PROSPECT_WATCH_CAP=60` (`pal_export.py:465-467`), all echoed into the payload (`prospect_watch_rule`, `pal_export.py:507-529`, with `n_mismatches`/`n_qualified`/`n_shown`/`n_below_margin`/`n_over_cap`/`cap_binding`/`best_margin_below_threshold`).
- W3 blend (OFF): `PAL_XRV_MIN_PITCHES=100`, `PAL_XRV_W=0.5` (`pal_conversion.py:226-227`); `astuff_to_quality` = `clamp(50 + 2.5*(aStuff+ - 100))` (`pal_conversion.py:247-253`); `XRV_MIN_LEAGUE_N=500` (`pal_conversion.py:786`).
- In-progress detection: `IN_PROGRESS_MIN_GS=5`, `IN_PROGRESS_MIN_IP_PER_G=2.5`, `IN_PROGRESS_MIN_RELIEF=0.50` (`pal_conversion.py:653-655`).
- Success tiers: RP `ERA<=3.50`/`K-BB>=0.12`; SP `ERA<=3.90`/`K-BB>=0.10` (`pal_conversion.py:739-742`).
- History years: `HISTORY_YEARS=[2018,2019,2021,2022,2023,2024,2025,2026]` — 2020 deliberately excluded ("2020 kept out of pairs", `pal_export.py:73`).
- eFV inert twin: `_SHAPE_IMPUTE=38.9`, `_DEPTH_IMPUTE=1.6` (`efv_model.py:729-730`) — observed debuted-pool means for the never-shipped RELIEF-SHAPE columns.

Registry pinning: `pal_conversion` row in `MODEL_REGISTRY.md:52` and `data/model_registry.json` (~lines 684-698; champion `pal_v1`, eval `data/pal_eval.json`); related rows `pal_gamelog_lanes` (~`:1467`), `pal_stuff_xrv` (~`:1987`), `c3_pal_fa_recal` (~`:2281`, verdict deprecated — zero removable clamps), `savant_sprint` (~`:2917`, the Position Fit Rng+ meter). No fingerprint/hash pinning — the "model" is the code itself.

## Edge cases & guardrails

- **Board eligibility:** current-season IP >= 20 (`pal_export.py:625`), plus a non-empty Statcast arsenal (`arm.role == "RP" and arm.arsenal` / `"SP" and arm.arsenal`, `pal_export.py:637,644`). SWING-role arms (and `role_of` None: `G<=0 or IP<=0`, stored as `role=""`) are on neither board. Boards sort by `fit` desc (`pal_export.py:649-650`).
- **Missing components:** neutral defaults `command=50`, `fb_reliance_inv=50`, `stuff_quality=50`, `survivability=50`, `putaway=40`, `need=50`, velo assumed 93.0; `platoon_neutrality=None` **drops from the blend and the remaining weights renormalize** (`_blend`, `pal_conversion.py:269-277`) — an arm with no splits is scored over 0.88 of the RP->SP weight mass (weights sum to 1.00; platoon carries 0.12).
- **Clamps:** every component and the ERA-need score clamp to [0,100]; FIT capped at 100 after the +3.0 pedigree nudge (at most one nudge — `if/elif`); REM+ projection caps `k <= 0.60`, floors `bb >= 0`.
- **ERA shrink:** empirical-Bayes toward 4.20 with 45 IP pseudo-count so a 30-40 IP unlucky ace does not top the SP->RP board (`pal_conversion.py:493-509`; provenance `rate_stabilization.py:39-50`, finding M4 2026-07-01).
- **Held-label hygiene:** only closed seasons (`last_closed_season = season-1`) with IP >= 20 can certify `held`; otherwise None (`pal_conversion.py:599-646`).
- **Prospect watch gates:** consensus FV >= 40 (`fv` None → 0 → dropped); hard MLB-graduation gate (debut on record in `data/debuts.json` OR career MLB IP >= 50 across loaded seasons via player_links — backstops NPB/KBO arrivals like Senga); prospects need `status == "active"`, a pitcher position, and at least one numeric tool; mismatch severity >= 10 shape points and cap 60 for the /pal/ list; the unbounded `prospect_watch_all` keeps every FV-qualified mismatch for the prospx chip (`pal_export.py:465-529, 604-609, 770-772`). Deterministic sort: −margin, −FV, name (`pal_export.py:487-488`).
- **Network degradation:** every pull is best-effort; failures log and return `{}`/`[]` so components go None and drop (`pal_export.py:29-31` docstring, per-loader try/except). If the season's pitching leaderboard is empty the export skips entirely, returning 0 (`pal_export.py:550-552`). Writes are atomic (`.json.tmp` then replace, `pal_export.py:796-799`). The whole run_monthly step is wrapped in try/except and never aborts the pipeline (`run_monthly.py:3561-3567`).
- **W3 coverage gate:** the AAA aStuff+ blend needs the sidecar season == scored season or prior, and >= 100 AAA pitches; otherwise byte-identical incumbent path (`pal_export.py:334-346`; asserted in the registry: "pooled scores byte-identical 1379/1379").
- **Display truncation:** candidate-row `arsenal` and pitch-mix `before`/`after` lists only include pitches with usage >= 0.03 (`_cand_row` `pal_export.py:820-822`; `_mix` `:831-834`) — display filter, not a scoring input (scoring reads the full arsenal).
- **Frontend fallback:** the prospx chip falls back to a deaccented name+org join and to `prospect_watch` on old payloads; hidden when the artifact is absent (`prospx/index.html:31187-31222`). `assets/pal.js` has a visible fetch-failure state (LOAD_ERROR + Retry, `assets/pal.js:26, 1170-1179`).
- **Test guards:** `test_pal_conversion.py` (need-gate shrink, depth monotonicity, direction-specific ranking, velo sign/shape, pedigree nudge, in-progress IP/G gate, recommender, reverse platoon, REM+-projection-is-display); `test_pal_export_prospect_watch.py` (severity staging, cap reporting, player_key join, missing-key tolerance); `test_pal_smoke.py` (all /pal/ JS views incl. error states; Rng+ outfield-only + display-only guards); `test_stabilization_constants.py:57-60` (NEED_ERA_SHRINK_IP single-home identity).

## Dependencies & discrepancies

**Consumes:** StatsAPI season pitching/splits/rosters, Statcast arsenal + velocity (pybaseball), B-Ref bWAR (history only); `rem_plus` (display-only relief projection + reliever pool); consensus scout tool grades + `fv_close` (prospect watch); `xfv.json` `xfv_grade` (`fvE` display field only — eFV never gates or scores); `stuff_plus_aaa.json` aStuff+ sidecar (both uses env-gated OFF); `NEED_ERA_SHRINK_IP` from `rate_stabilization.py`; `data/pal_eval.json` verdict stamp.

**Feeds:** the /pal/ surface (`assets/pal.js`), the homepage drawer card (`build_site.py:2425-2440`, top-3 RP->SP), the prospx pitcher-card role-mismatch chip (`prospx/index.html:31183+`). Nothing model-side consumes PAL FIT — the one near-miss is the RELIEF-SHAPE twin of `starter_shape` inside `efv_model.py:812-841`, which is a re-implementation (not an import), gate-FAILED, and never in `_FEATURES_PIT` — so no production feedback into efv/xfv, value_framework, or any other documented stat.

**Discrepancies / flags:**
1. **Registry verdict vs eval vs served artifact:** `MODEL_REGISTRY.md:52` and the `model_registry.json` `pal_conversion` row say `provisional`, but `data/pal_eval.json` `verdict.status` = `"downgraded"` and the served `data/pal.json` `verdict` field is `"downgraded"` (stamped live from the eval at export time, `pal_export.py:851-856`). The registry json block even carries `"_comment": "PROPOSED replacement for the pal_conversion row ... Not applied; owner merges."` and its notes explain the enum has no "unvalidated-with-artifact" rung, so the row deliberately stays provisional with the DOWNGRADED note as authority. The glossary (`data/glossary.json` `pal_conversion` entry, ~`:5643`) says "ships provisional with a downgraded registry verdict" — consistent with that reading.
2. **Per-direction validity:** SP->RP FIT passes its gate (rho +0.2916 vs war_delta, n=61, gap lo95 +0.0745 over best baseline `kbb_pre` -0.097); RP->SP FIT is sign-wrong (-0.2062, n=25, vs best baseline `neg_era_pre` +0.1023, gap lo95 -0.7517) and ships only as a structural screen (gate: seed 20260714, B=2000, "any direction failing downgrades"). Glossary methodology (`glossary.json` ids `rp_sp_fit` ~`:5586`, `sp_rp_fit` ~`:5608`, `pal_conversion` ~`:5630`) agrees with the code and the eval (quotes "about -0.21 on 25" / "about +0.29 on 61"). The live stamp in `pal.json` (generated 2026-08-01) recomputes slightly different rhos (-0.216 / +0.295; held 0.134 n=13 / 0.43 n=22; pooled 0.281 n=35) than the frozen eval (-0.2062 / +0.2916, generated 2026-07-15) — same seasons, same `last_closed_season=2025`, identical gated-event counts (25/61), so the drift is re-pulled input data between run dates (fresh arsenal/platoon/bWAR pulls), the same "stale data drift" phenomenon the registry notes for the pooled rho (registered 0.223 vs recomputed 0.2882 vs live 0.288-then-0.281).
3. **`pal_stuff_xrv` registry says ARM-2 pitch-add xRV ranking "SHIPPED display"** (`model_registry.json` pal_stuff_xrv row, ~`:1988`), but the code path is gated behind env `EEPHUS_PAL_XRV_RECO` (`pal_export.py:614, 640-641`) which nothing in `run_monthly.py` sets; the currently served `pal.json` pitch_add recommendations contain only the incumbent rule-order names (verified: exactly {Slider, Changeup, Cutter}; no Sweeper/Splitter/Knuckle-curve/Curveball), i.e. the xRV ranking is inert in production. ARM-1 (the stuff blend) is separately marked "not shipped (gate never ran; COVERAGE-STARVED, revival ~2028)".
4. **Lane B / game logs:** `rp_sp_fit_v2` + `pal_gamelogs.relief_usage_features` are candidate-only (Lane B FAILED its sign-check -0.0013; `pal_gamelog_lanes` registry row); `pal_gamelogs.recover_events` mid-year/swing-bridge recovery is a lab sensitivity arm (`tools/pal_backtest_lab.py`) — neither is in the `pal_export` production path, though `detect_in_progress_conversions` (season-stats-only, no game logs) IS in production.
5. No frontend recompute: `assets/pal.js`, `prospx/index.html`, and `build_site.py` all render exported values verbatim — the FIT scores have a single production computation site (`pal_conversion.py` via `pal_export.py`). The `starter_shape` FORMULA alone has the second, inert home in `efv_model.py` (site 4 above).
6. The /pal/ page "Position Fit" tab is a different model (`data/positional_fit_ui.json`, hitter positional fit; Rng+ registry row `savant_sprint`) sharing the surface name "Alchemy Lab" — do not conflate with the PAL conversion FIT.
7. Served snapshot (2026-08-01 `data/pal.json`): 230 RP->SP rows, 173 SP->RP rows, `relief_k_bump_measured` 0.0164, `converter_median_fit_pool_pctile` 72, watch rule {n_mismatches 122, n_qualified 55, n_shown 55, cap_binding false, best_margin_below_threshold 8.0}.

### Verification log

- **Corrected the run_daily claim.** Draft: "There is no `run_daily.py` in this repo; PAL refreshes only on the monthly run." A daily pipeline exists as the `run_daily()` function inside `run_monthly.py` (`run_monthly.py:860`, CLI `--daily` at `:3855`, tail-chained by monthly `main()` at `:3767`); it does not call `pal_export` (only `pal` reference in the pipeline is step 6b5 at `run_monthly.py:3556-3567`), so the conclusion (monthly-only refresh) stands but the file-existence framing was misleading.
- **Corrected the pal_gamelogs consumer list and line cites.** Draft cited "tools/pal_backtest_lab.py:472,522,801" as the only consumer. Actual: import at `tools/pal_backtest_lab.py:472`, usage at `:672,701,708,711,727,746,799` (not 522/801), and `tools/fantasy_startscore_lab.py:113` also imports `pal_gamelogs` for its game-log fetch/cache infra. Both labs; production claim unaffected.
- **Added a missed computation site:** `efv_model.py:812-841` re-implements `prospect_role_fit`'s starter_shape (depth over raw fb/sl/cb/ch, no ct; same step table; `relief_flag = shape < 40`; imputes `_SHAPE_IMPUTE=38.9`/`_DEPTH_IMPUTE=1.6` at `efv_model.py:729-730`); keys emitted-but-inert, never in `_FEATURES_PIT` (`efv_model.py:145-274`); RELIEF-SHAPE gate FAILED (ledger `data/xfv_relief_shape_eval.json`, lab `tools/efv_relief_shape_lab.py`). Qualifies but does not overturn the "nothing model-side consumes PAL" claim.
- **Corrected the live-vs-frozen rho explanation.** Draft attributed the -0.216/+0.295 (live) vs -0.2062/+0.2916 (eval) gap to "the live harness includes the current season." Both use seasons [2018..2026] with `last_closed_season=2025` and identical gated ns (25/61) (`data/pal_eval.json` generated_at 2026-07-15; `data/pal.json` generated_at 2026-08-01); the difference is input-data drift between pull dates, matching the registry's "stale data drift" note on the pooled rho.
- **Verified discrepancy 3 against the served artifact:** `data/pal.json` pitch_add recs are exactly {Slider, Changeup, Cutter} — the incumbent rule order; `EEPHUS_PAL_XRV_RECO` unset in `run_monthly.py`. Claim confirmed and tightened with the ARM-1 "not shipped" registry wording.
- **Added serving/deploy facts:** `/pal/` dir at `deploy/publish_paths.txt:27`; `pal.json`/`pal_eval.json` not in `deploy/data_exclude.txt`; /pal/ page beta-stamped (`build_site.py:3012`).
- **Added precision the draft omitted:** candidate-row `arsenal` + `_mix` display filter usage >= 0.03 (`pal_export.py:820-822, 831-834`); history sort (`:722`); in-progress de-dup by (mlbam, year) (`:562-565`); `load_platoon` ThreadPool workers=12 (`:160-163`); `load_prospect_pitchers` `normalize=ADOPT_NORMALIZED_CONSENSUS` + `tools_consensus`-then-`tools` fallback (`:258-259, 271`); `load_velo` has no `ft_avg_speed` column despite FT ∈ FASTBALLS; at most ONE +3.0 pedigree nudge (if/elif); `_spearman` returns None under n=4 (`pal_export.py:394-416`); flag-chip rules for both directions (`pal_conversion.py:302-312, 512-523`); rp_sp_fit_v2 stamina constants (`:359-361`); eval gate numbers (baselines, gap CIs, seed 20260714, B=2000) from `data/pal_eval.json`; served-snapshot counts (230/173 boards, watch rule 122/55/55); glossary entry ids + line anchors (`rp_sp_fit` :5586, `sp_rp_fit` :5608, `pal_conversion` :5630, `arsenal_depth` :5653, `tto_penalty` :5673, `putaway_pitch` :5715, `starter_shape` :5818 — the `starter_shape` formula text "0.60 x arsenal-depth + 0.40 x command, pitches graded >= 55" agrees with code); PAL test-file inventory.
- **Minor cite fixes:** `_load_aaa_stuff` body at `pal_export.py:321-331` (`:318` is the path constant); homepage drawer block spans `build_site.py:2425-2440` (read at `:2427`, top-3 slice); prospx chip logic extends to `:31239`; `detect_in_progress_conversions` body at `pal_conversion.py:658-710` with constants at `:653-655`; registry `pal_conversion` row spans ~`:684-698`.
- All other quantitative claims verified against code: every constant, band edge, weight, threshold, formula, payload key, StatsAPI/pybaseball call signature, `HISTORY_YEARS`, `NEED_ERA_SHRINK_IP=45.0` (`rate_stabilization.py:50`), verdict plumbing, and the eval/registry/glossary numbers reproduced above.


---

# wag

## Name in code & where computed

WAG ("WAR Above Grade") exists in this repo as **two parallel Python implementations plus a JS frontend recompute** — all three are live in production and they do **not** agree. All paths are documented below; do not port only one without knowing which surface it feeds.

**A. Engine WAG (value_framework, "Prompt M") — the canonical per-player number.**
- `value_framework.py::wag(fv, is_pitcher, observed_war, *, position, exposure_pa, exposure_ip, service_years, age, fv_reflects_mlb, cred)` — `value_framework.py:2638-2744`.
- Its expectation core `value_framework.py::expected_war(...)` — `value_framework.py:2584-2635`.
- Shared regression core `value_framework.py::_talent_regression(...)` — `value_framework.py:2325-2387` (same constants as the debuted-player Bayes update, by design; comment at `value_framework.py:2440-2442`).
- Categorical label `value_framework.py::wag_boom_bust(wag_result)` — `value_framework.py:2747-2764`.
- Helpers `_wag_for_player` / `wag_leaderboard` / `wag_mean_by` — `value_framework.py:2767-2808` (defined but **no production caller**; `test_wag.py` only).
- Production wrapper: `storage.py::_engine_wag_result(...)` — `storage.py:6439-6464` (imports at `storage.py:6279-6280`: `wag as _engine_wag`, `wag_boom_bust as _engine_wag_boom_bust`), called from `storage.py::_build_debuted_payload(...)` — `storage.py:6467-6558`, which bakes the result into each debuted player's export payload as `debuted_value.wag` (keys: `regressed_wag`, `regressed_lo`, `regressed_hi`, `counting_wag`, `rate_wag`, `percentile`, `z`, `expected_war`, `observed_war`, `true_talent_war`, `w_obs`, `below_meaningful_exposure`, `boom_label`) — `storage.py:6539-6555`.
- The call site inside the big export: `storage.py:9766-9777` (inside `export_timeseries_json`, def at `storage.py:7546`), which writes `data/timeseries.json` + `data/debuts.json` (+ `debuts_lite.json` at `storage.py:15504`, `debuts_full/` per-player shards at `storage.py:15540`; `debuts.json` itself at `storage.py:15488`).
- **Production chain**: `run_monthly.py:655` (rebuild-only path) and `run_monthly.py:3240` (monthly step 5) call `export_timeseries_json(...)`; the chained daily's d9 full export (`run_monthly.py:1396`) rewrites the sidecars and d11 runs `build_site.main()` (`run_monthly.py:1578-1580`). So engine WAG is recomputed on every monthly/daily export run.

**B. Legacy rate-based WAG (`_grad_wag`) — still production for farm grades, org rollups, and the Overseas module.**
- `storage.py::_grad_wag(graduate_payload)` — `storage.py:5322-5400`.
- Its baseline `storage.py::_fv_to_expected_war_per_yr(fv, is_pitcher)` — `storage.py:5039-5068`, which delegates to `value_framework.survivor_expected_war` (`value_framework.py:786-802`) with a hardcoded FanGraphs-primer fallback table (`storage.py:5031-5036`).
- Positive-surprise damper `storage.py::_graduate_outcome_penalty` — `storage.py:5290-5319`.
- Sample helper `storage.py::_career_pa_ip` — `storage.py:5251-5287`; pitcher classification `storage.py::_is_pitcher_graduate` — `storage.py:5243-5248` (`stat_flags.is_pitcher(position)` OR `sabermetrics.is_pitcher is True`).
- Legacy label `storage.py::_compute_boom_bust` — `storage.py:5403-5435`; stamped on every debuted payload as top-level `boom_label` at `storage.py:10081-10087`, and used again in the farm rollup at `storage.py:11349-11362`.
- Farm-grade consumption: per-org walk at `storage.py:11218-11227` (calls `_grad_wag`; the payload's `transactions` key is filled from `transactions_by_player` at `storage.py:11224`), aggregated into `talent_translation` (`storage.py:11618-11628`), per-channel splits (IFA/draft/hitter/pitcher `*_wag_sum` — `storage.py:11363-11379`, surfaced at `storage.py:11850`, `11899`, `12014`, `12032`, `12045`). **Caution — the composite claim is subtler than it looks**: `FARM_WEIGHT_TALENT_TRANSLATION = 0.18` (`storage.py:4567`) weights WAG only into `farm_score_legacy` (`storage.py:13557-13569`, normalized at `13524`, component score at `13547`, weighted at `13562`), and that legacy score is **overwritten** by the tree composite at `storage.py:14046`. In the live tree, v40 **dropped** the `talent_translation` (WAG) leaf from the `mlb_production` parent rollup (`storage.py:13968-13979`: "raw realized graduate WAR is the production signal we grade on... The WAG leaf is still computed for display/tooltip, just no longer in the grade"). What still ships from this path: the leaf value + tooltip, the per-component rank (`storage.py:13595`, `13617`) and letter grade (`storage.py:13634-13636`, gated on ≥3 grads), and — via the legacy label — the `mlb_production_boom_pct` / `mlb_production_bust_pct` leaves which **do** remain inside the live `mlb_production` parent (`storage.py:13803-13815`, `13972-13979`). So legacy WAG no longer moves the headline farm score directly, but its boom/bust derivative does.
- **Overseas module** (missed by most greps): `overseas_export.py` imports `_grad_wag` (`overseas_export.py:77`) and computes a per-signing `wag` in `_signing_performance` (`overseas_export.py:446-486`, exported at `556` and `656`) into `data/overseas_timeseries.json`. Grade baseline there = the graduate record's own `fv_close` where present, else the overseas consensus FV — **never eFV**; the payload passes no `transactions`/`age`/`current_level`, so `_graduate_outcome_penalty` degrades to 1.0 (no churn/age/minors damping) on that surface.
- A career-cumulative variant `_grad_wag_cumulative` (`storage.py:5149-5167`, uses the `FV_EXPECTED_WAR` career table `storage.py:4980-4994` via `_fv_to_expected_war`, `storage.py:4997-5019`) is kept but is not the default.

**C. Frontend JS recompute (prospx) — a third implementation.**
- `prospx/index.html::gradVsFvProjection(g)` — `prospx/index.html:22607-22628` (mirrors `_grad_wag`), with `graduateOutcomePenalty` (`22580-22592`), `_gradPerSeasonWar` (`22600-22605`), gate/rate object `gradWarPerYr` (`22516-22578`) built on the **personal full-season denominator** `gradPersonalFullSeason` (`22484-22514`), baseline `fvExpectedWarPerYr` + static `FV_WAR_ANCHORS` table (`22136-22155`), and the per-season sparkline `makeWagChart` (`22649-22678`). Powers the Debuted-tab "WAG / season" sort/column (`18451`), the org "WAG mean (grads)" column (`18485` — engine-independent display of the *legacy* org rollup), **WARWAG** (below), the FV-tier debut cohort rank block `_debutFvCohortBlock` (`14720-14760`), and the graduate detail-page WAG rank pill (`45779-45800`, ranks `gradVsFvProjection` across `DATA.debuts`).
- Engine-output readers (no recompute): the WAG pill / shared display slot `displayMetricFor` reads `debuted_value.wag.regressed_wag` (`prospx/index.html:10258-10280`); trade-machine hindsight board reads `debuted_value.wag.regressed_wag` + `boom_label` (`20379-20401`, rendered `20515-20543`); sort key `"wag"` (`15689-15690`). The farm report-card tree UI reads the org `wag_mean` leaves (`prospx/index.html:38261-38311`, `39352`, `41860`). Python-side mirrors in `build_site.py` (`display_metric_for`, def `build_site.py:1097`, WAG branch `1150-1157`; `_wag_badge`, `build_site.py:1861-1876`) also read `debuted_value.wag`.

**D. WARWAG** (distinct displayed quantity, frontend-only):
- `prospx/index.html::gradWarWag(g)` — `prospx/index.html:22634-22641`; sort chips at `9549-9556` (WAG high/low + WARWAG high/low); sort handling `30456-30474`. Never computed in Python.

**E. Derived consumer — `regressed_wag` calibrates the eFV blend lambda (currently dormant in effect):**
- `efv_model.py::_load_wag()` — `efv_model.py:359-372` (reads `debuted_value.wag` back out of `data/debuts.json`); `efv_model.py::wag_calibration(side)` — `efv_model.py:375-421`; gating in `blend_lambda` — `efv_model.py:524-559` with `_WAG_MIN_SPEARMAN = 0.10`, `_WAG_MIN_N = 100` (`efv_model.py:345-346`), clamp `(0.35, 0.90)` and fallbacks `{"hit": 0.85, "pit": 0.80}` (`efv_model.py:317-318`).
- **Override the draft pipeline must know about**: `_BLEND_LAMBDA_RESELECT = {"hit": 0.70, "pit": None}` (`efv_model.py:332`) is checked FIRST inside `blend_lambda` (`efv_model.py:543-546`) — the hitter lambda is hand-pinned at 0.70 (2026-07-24 churn trade, stability not accuracy) and never reaches the WAG calibration; the pitcher side is dynamic but per the in-code measurements (pit WAG spearman ~0.001, hit ~0.066 — both below 0.10) currently fails the WAG gate and falls to `rank_calibration`. So the WAG→lambda path is live code and instrumentation (`lam_source` at `efv_model.py:1842-1843`) but as of now sizes **no** production lambda.

Registry row: `data/model_registry.json:236-249` / `MODEL_REGISTRY.md:26` — `model_id: "wag"`, surface "PROSPX debuted players", champion `wag_v47 (survivor curve from the calibrated bucket model)`, baseline "n/a (residual metric)", metric "PIT uniformity + coverage", eval artifact `data/value_framework_fitted.json`, verdict **validated**, notes "the template: distributionally validated, auto-propagates recalibrations". (Note: the "survivor curve" phrasing describes the **legacy** baseline, not the engine — see §6 of Discrepancies.)

Labs / non-WAG uses: `tools/bucket_age_head/patched/value_framework.py` contains a patched copy (not production). `efv_export.py:253` calls `expected_war(fv, is_pit, service_years=7)` only inside the vintage-calibration monitor (diagnostic, not WAG). Tests: `test_wag.py` (18 tests), `test_wag_stress.py` (2), `test_wag_validation.py` (5), `test_boom_bust.py`, `test_farm_grades.py`.

## Formula or fitted model?

**Hybrid**: the WAG residual itself is deterministic arithmetic, but its expectation baseline comes from a **fitted proportional-odds (ordered-logit) bucket model + fitted empirical FV→WAR anchors** stored in `data/value_framework_fitted.json` (JSON, written by `value_framework.py --fit`, `generated_by: "value_framework.py --fit"`, `framework_version: "v2.0"`, empirical-anchor block `generated_at: 2026-06-21`). Version pinning is via the model registry row (`wag_v47`) and the fit-file provenance blocks; the fitted artifact is the eval artifact itself.

**Fit-file hazard (verified in the artifact's own `anchors_provenance` string)**: the served `empirical_anchors.anchors` sub-45 knots (20/25/30/35/40) were **hand-amended 2026-07-29** (FV35/40 measured on `target_censored`; 20/25/30 are an extrapolated monotone ramp, "a floor, not a finding"; 45-80 deliberately untouched). The provenance block states outright: "Running value_framework --fit WILL revert this key" (the fit machinery cannot reproduce the amended table). Guarded by `test_value_framework::test_low_end_anchors_are_present_and_measured`. Any re-fit therefore changes every WAG expectation below FV 45 unless the amendment is re-applied.

### A. Engine WAG (`value_framework.wag`) — exact steps

Step 1 — FV-implied WAR distribution over the player's actual exposure (`expected_war`, `value_framework.py:2584-2635`):

```python
ref = 600 PA (hitter) or 200 IP (pitcher)                    # debuted.full_season_*
sample, seasons = _exposure_seasons(...)                     # service_years wins; else PA/ref or IP/ref
probs = p_bucket_given_fv(fv, is_pitcher)                    # fitted 5-vector [bust,bench,regular,good,star]
debut_age = round((age - seasons) * 2) / 2  if age is not None else None
sd_within = obs_war_sd_per_full_season[role] * sqrt(seasons) # cumulative observation noise
for b in range(5):
    traj = _bucket_season_wars(role, b, reliever=False, debut_age, _war_scale_for(fv, role))
    cum_b = _bucket_cumulative_war(traj, seasons)            # pro-rates partial season; flat past window
    comps.append((probs[b], cum_b, sd_within)); mean += probs[b]*cum_b
var = sum(w*(sw*sw + cb*cb) for w,cb,sw in comps) - mean*mean  # mixture variance
```
- `p_bucket_given_fv` (`value_framework.py:749-771`): fitted method is `proportional_odds` for both roles (fit file `method`). Fitted params (introspected from `data/value_framework_fitted.json`): hitter `slope=0.17502297799589095`, `cutpoints=[7.896939381645044, 8.898882615829814, 10.168309209219554, 12.416555560869362]`; pitcher `slope=0.16247947639606863`, `cutpoints=[7.34374550099759, 8.480670380806886, 9.836375926028913, 13.149321678505451]`; training n (`training_n`) = 678 hitters / 437 pitchers. Ordered logit `P(Y ≤ j | FV) = sigmoid(cutpoint_j − slope·FV)` (`_p_bucket_proportional_odds`, `value_framework.py:701-708`), differenced into the 5 bucket masses and `_normalize_clip`ped. Fallbacks if the fit method is absent: per-threshold isotonic (`_p_bucket_per_threshold`), then PCHIP over the config training rows (`_p_bucket_pchip`).
- `_bucket_season_wars` (`value_framework.py:1135-1144`): per-season WAR = `_calibrated_midpoints(role)[b] * war_scale * aging_shape`. Midpoint shape = config `buckets.*.midpoint_war` = `(0.0, 1.0, 2.0, 3.2, 5.0)` (`value_framework_config.yaml:38-42`; `value_framework.py:936-945`). `war_scale = _fv_war_scale(fv, role)` (`value_framework.py:961-992` incl. the public `_war_scale_for` at `985-992`, FV rounded to 0.5 for the lru cache) scales the shape so `Σ p_b·mid_b == fv_to_6yr_avg_war(fv)`.
- `fv_to_6yr_avg_war` (`value_framework.py:621-646`): piecewise-linear over the **fitted empirical anchors** (because `anchor_calibration.use_empirical: true`, `value_framework_config.yaml:184-185`): `{20:0.012, 25:0.014, 30:0.016, 35:0.019, 40:0.086, 45:0.31, 50:0.67, 55:0.98, 60:1.44, 65:2.0, 70:2.52, 80:3.5}` (fit-file `empirical_anchors.anchors`, cohort window 2014-2020, `n_cohort` 3460; see the hand-amendment hazard above). Config seed fallback: `{35:0.12, 40:0.22, 45:0.38, 50:0.70, 55:0.95, 60:1.45, 65:1.95, 70:2.60, 80:3.80}` (`value_framework_config.yaml:161`). Clamped flat outside the anchor range.
- Aging shape `_trajectory_shape` (`value_framework.py:1091-1111`) with `_aging_multiplier` (`1075-1085`): asymmetric tent, peak ages 27 (hitter) / 25 (pitcher), climb 0.04/yr below peak, decline 0.07/yr past it, floor 0.25 (`value_framework_config.yaml:286-290`), renormalized to mean 1.0 across `service_time.control_years: 6` (`yaml:300`).
- Note the reliever flag is hardcoded `False` here (`value_framework.py:2618-2621`): WAG grades on the band/talent scale; no reliever haircut.

Step 2 — the residuals (`value_framework.py:2703-2744`):

```python
observed_rate = observed_war * ref / sample
counting_wag  = observed_war - ew["mean"]                    # exposure-matched cumulative residual
rate_wag      = observed_rate - ew["mean_rate"]              # per-600-PA / per-200-IP residual
z             = counting_wag / ew["sd"]                      # 0.0 when sd == 0
percentile    = Σ_b  w_b * Φ((observed_war - cum_b) / sd_within)     # PIT in the predicted mixture
regressed_wag = w_obs * rate_wag                              # reliability-shrunk toward 0
half          = Φ⁻¹(0.5 + 0.90/2) * (ew["sd"]/seasons) * (1 - w_obs)  # cred band, credible_mass 0.90
regressed_lo/hi = regressed_wag ∓ half
```
where `w_obs = k_eff / (k_eff + k_reg)` from `_talent_regression` (`value_framework.py:2325-2387`): `k_eff = real_PA_or_IP * (1 - fv_reflects_mlb)` (with an early-career hitter defense down-weight: below `defense_seasons_to_stabilize` = 3 season-equivalents, `k_eff *= 1 - defense_early_penalty·(1 - seasons/3)` with penalty 0.5); `k_reg = 600 PA` (hitter) / `250 IP` (pitcher). **Important subtlety** (`value_framework.py:2669-2689`, `2715-2722`): when called production-style with `service_years` = MLB season count *and* real PA/IP, `rate_wag` is season-matched (WAR/season vs FV-implied WAR/season) while `w_obs` and the exposure gate use the real accumulated PA/IP.

Step 3 — label (`wag_boom_bust`, `value_framework.py:2747-2764`): `"unsettled"` if no WAG or `below_meaningful_exposure` (or missing percentile); `"boom"` if `percentile ≥ 0.80`; `"bust"` if `percentile ≤ 0.20`; else `"settled"` (config `wag.boom_bust`, `value_framework_config.yaml:430`).

Production invocation (`storage.py:6521-6537`): `service_years = len(career_war.seasons)` (count of MLB seasons, **not** the service-time decimal — the comment at `6524-6527` says service_years_decimal is None for many players and would fall the call back to PA-matching), `exposure_pa/ip` = summed MLB PA/IP via `_mlb_exposure_pa_ip` (`storage.py:6420-6436`), `fv` = `wag_fv` (eFV `xfv_grade` when present, else consensus FV — `storage.py:6533`, `9768`).

### B. Legacy `_grad_wag` (`storage.py:5322-5400`) — exact steps

```python
career_war = float(payload["career_war"]["career_war"])          # bWAR total
fv_close   = payload["fv_close_raw"] or payload["fv_close"]      # farm rollup passes eFV here when available
season_count = war_seasons_count or len(seasons) or len({MLB seasons in career_stats})
floor_ok   = ip >= 50 (pitcher) or pa >= 150 (hitter)            # MLB-level PA/IP only, AB*1.13 PA fallback
full_season_war = career_war / season_count      if season_count and floor_ok
                = career_war.war_per_yr          elif war_per_yr is not None
                = None -> return None
expected = _fv_to_expected_war_per_yr(fv_close, is_pitcher)      # = value_framework.survivor_expected_war
delta = full_season_war - expected
if delta > 0:
    delta = (delta * 0.70 + full_season_war * 0.30) * _graduate_outcome_penalty(payload)
return round(delta, 2)
```
`survivor_expected_war` (`value_framework.py:786-802`) = `Σ_{b≥1} probs[b]·mid_b·scale / Σ_{b≥1} probs[b]` (mids pre-scaled by `_war_scale_for`) — the same fitted bucket model **conditioned on non-bust** ("graduates are, by definition, survivors" — the single-source-of-truth comment at `value_framework.py:787-792`); returns None on bad FV or non-bust mass ≤ 1e-9. Fallback tables only if the engine import fails (`storage.py:5050-5056` try/except): hitter `{30:-0.1, 40:0.0, 45:0.8, 50:1.6, 55:2.5, 60:3.4, 70:5.0, 80:7.0}`, pitcher `{30:-0.1, 40:0.0, 45:1.0, 50:1.8, 55:2.6, 60:3.5, 70:5.0, 80:7.0}` (`storage.py:5031-5036`, explicitly documented at `5026-5029` as a stale FanGraphs-primer curve that ran ~2-3x hot — realized graduate means 0.34/0.77/0.94/1.23 WAR/yr at FV 45/50/55/60).
`_graduate_outcome_penalty` (`storage.py:5290-5319`): ×0.45 if ≥2 DFA/outrighted/released transactions (×0.72 if exactly 1), ×0.85 if age ≥ 26, ×0.85 if currently in the minors; clamped to [0.25, 1.0]. Applied to **positive** WAG only.

Legacy label `_compute_boom_bust` (`storage.py:5403-5435`): floor `seasons ≥ 2 OR pa ≥ 800 OR ip ≥ 200`; `boom` if `wag ≥ 2.5`, `bust` if `wag ≤ −1.5`, else `settled`; `unsettled` below floor or `wag is None`.

### C. Frontend recompute (`gradVsFvProjection`, `prospx/index.html:22607-22628`)

Same math as `_grad_wag` (per-season WAR from baked `career_war.war_per_yr` or `career_war/war_seasons_count` via `_gradPerSeasonWar`, `22600-22605`; same 0.70/0.30 blend and penalty multipliers, `graduateOutcomePenalty` `22580-22592`) **except**:
- The gate is `gradWarPerYr` (`22516-22578`): season fractions are summed per MLB year as `PA/denom` (or `IP/denom`, AB×**1.1** PA fallback at `22542`), where `denom` is the **personal** full-season baseline from `gradPersonalFullSeason` (`22484-22514`) — the mean of the player's own MLB seasons with PA ≥ 300 (hitter) / IP ≥ 50 (pitcher), falling back to **600 PA / 130 IP** (note: 130 IP, not the backend's 200) when no qualifying season exists. Gate: `count < 1 || totalFrac < 1.0 → null` (`22569`) — i.e. ≥1 full-season equivalent, not the backend's 150 PA / 50 IP floor.
- The FV baseline is `g.fv_close_raw ?? g.fv_close` (**consensus only — never eFV**, `22616`).
- Expected WAR/yr comes from the **static** `FV_WAR_ANCHORS` mirror (`22136-22139`): hitter `{30:-0.1, 40:0.62, 45:0.67, 50:0.97, 55:1.13, 60:1.57, 65:1.99, 70:2.60, 80:3.51}`, pitcher `{30:-0.1, 40:0.60, 45:0.67, 50:0.99, 55:1.16, 60:1.59, 65:2.01, 70:2.62, 80:3.51}` — a hand-synced snapshot of `survivor_expected_war` (comment `22130-22135`), linearly interpolated and clamped (`fvExpectedWarPerYr`, `22141-22155`).

### D. WARWAG (`gradWarWag`, `prospx/index.html:22634-22641`)

```js
WARWAG = perSeasonWAR + gradVsFvProjection(g)     // == 2·WAR/yr − expected(FV) when WAG un-penalized
```
(`perSeasonWAR` = `_gradPerSeasonWar(g, r)`, falling back to `r.war_per_yr`.) Null (row sinks) without ≥1 full-season equivalent or without an FV. Frontend-only; glossary entry `warwag` (`data/glossary.json:638-662`).

### E. `regressed_wag` → eFV lambda (`efv_model.wag_calibration`, `efv_model.py:375-421`)

Forward-chained per scored year (fold gates: ≥15 test rows, ≥60 train rows): for each debuted test row, `x = (model_war − consensus_war)/6` (predicted per-season edge; `cons_war = max(0, OLS(fv))`, `model_war = max(-2, a + b·ridge)` after linear calibration), `y = regressed_wag` from `debuts.json`, weight `w = w_obs`; through-origin WLS slope `Σ w·x·y / Σ w·x·x`, clamped to [0.35, 0.90] → the blend lambda, used only when `|spearman(x,y)| ≥ 0.10` and `n ≥ 100` (`efv_model.py:550`); otherwise the rank-gate fallback (`rank_calibration`) or `{hit: 0.85, pit: 0.80}` on error. **But**: `_BLEND_LAMBDA_RESELECT` (`efv_model.py:332`, checked first at `543-546`) hand-pins hit at 0.70; pit is dynamic and currently fails the spearman gate → rank gate. WAG's lambda influence is currently dormant on both sides.

## Inputs

| Input | Field in codebase | Ultimate source | Computed stat? |
|---|---|---|---|
| Grade baseline | `wag_fv` = `data/xfv.json` `by_player` row's `xfv_grade` (`_load_xfv_join`, `storage.py:4895-4903`), fallback consensus `latest_fv` / `fv_close_raw` (`storage.py:9768`, `11213-11214`, `6533`) | eFV model export (`efv_score.py` → `data/xfv.json`) / consensus FV pipeline. **One-run lag is intentional**: `export_timeseries_json` runs BEFORE `efv_export.regen_all` in run_monthly, so WAG's eFV baseline is the PRIOR run's committed xfv.json (`storage.py:4887-4894`) | **Yes — depends on xfv/efv** (engine + farm-rollup paths); frontend recompute + overseas export use consensus FV only |
| Observed WAR | `career_war.career_war`, `.seasons {year: war}`, `.war_per_yr`, `.war_seasons_count` | **Baseball-Reference bWAR** via `pybaseball.bwar_bat` / `bwar_pitch` (war_daily CSVs, fetched in parallel), summed over stints per year, batting+pitching summed for two-way — `stats.py::fetch_career_war_bulk` (`stats.py:3255-3368`, `"source": "bbref"` at `3366`); cached via `upsert_career_war`/`load_career_war` (refresh window floored at 2011, `run_monthly.py:~2860-2876`) | No (raw, ingested) |
| Exposure PA/IP | `career_stats[]` rows with `level == "MLB"`: `pa` (fallback `ab*1.13` legacy `storage.py:5281`; `ab*1.1` engine wrapper `storage.py:6429` and frontend `prospx/index.html:22542`), `ip` | MLB StatsAPI career stats ingest | No |
| Seasons | `len(career_war.seasons)` (engine, `storage.py:6528`) / `war_seasons_count` (legacy) | derived from bWAR season map | Derived |
| Age | `compute_age_decimal(birth_date)` | StatsAPI bios | No |
| Position / role | `p.position` (engine: `value_framework.is_pitcher_position` imported as `_vf_is_pitcher_position`, `storage.py:6263`, used `9753`; legacy: `_is_pitcher_graduate` = `stat_flags.is_pitcher` OR `sabermetrics.is_pitcher`, `storage.py:5243-5248`; frontend: `g.sabermetrics.is_pitcher`) | consensus board position | No |
| FV→WAR expectation | fitted bucket model + `empirical_anchors` in `data/value_framework_fitted.json` | resolved prospect cohorts 2014-2020 (realized bWAR outcomes); sub-45 anchors hand-amended 2026-07-29 | **Yes — shared with value_framework ($/WAR + surplus)**; the identical `p_bucket_given_fv × midpoints × k(FV)` core prices surplus |
| Transactions / current level / age (penalty, legacy only) | payload `transactions` (from `transactions_by_player`, `storage.py:11224`), `current_level`, `age` | transactions ingest, rosters | No |
| `fv_reflects_mlb` | 0.0 in production (default; never overridden by `_engine_wag_result`) | — | — |

Consumed by (feeds): **efv** blend lambda plumbing (`efv_model.wag_calibration` — currently gated out, see §E), farm report card (`talent_translation` leaf display/letter/rank + boom/bust % leaves — the WAG leaf itself was dropped from the live composite at v40; the 0.18 weight lives only in the overwritten `farm_score_legacy`), trade-machine hindsight board, the site-wide WAR/WAG/FV display slot, Debuted-tab sorts + cohort blocks + WAG rank pill, WARWAG, and the Overseas signings table (`data/overseas_timeseries.json`). It does **not** consume rem_plus/sem_plus/hem_plus/stuff_plus/pal/swing_plus/collegesavant_plus/draft_stock_plus.

## Constants, baselines & normalization

WAG is **not** a "+"-scaled stat (no 100-anchored normalization); it is a signed WAR residual (units: WAR or WAR/season) plus a percentile. It is absent from `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md` (verified: no match). (The org-level `wag_mean` does get z-scored to a 100-anchor inside the farm tree's `_zscore_to_100`, `storage.py:13657-13676` — but that is the farm-grade leaf machinery, not WAG itself.)

Baseline population/window: the FV-implied expectation is fitted on **resolved prospect cohorts, snapshot years 2014-2020** (`empirical_anchors.cohort_window [2014, 2020]`, `n_cohort` 3460; `anchor_calibration.resolved_lag_min: 6 / max: 12`, `value_framework_config.yaml:186-187`, reference_year = current year so the window slides). Recomputed only when `value_framework.py --fit` is run (artifact regenerated; **not** per pipeline run — and a bare `--fit` REVERTS the hand-amended sub-45 anchors, see the hazard note in §Formula). Bucket-probability fit trained on n=678 hitters / 437 pitchers.

Named constants (all config literals in `value_framework_config.yaml` unless noted):
- `debuted.full_season_pa: 600`, `full_season_ip: 200` (yaml:509-510)
- `debuted.obs_war_sd_per_full_season: {hitter: 1.3, pitcher: 1.6}` (yaml:511)
- `debuted.graduation_sample: {hitter_pa: 1200, pitcher_ip: 400}` (yaml:512; feeds `w_grad`, not WAG directly)
- `debuted.defense_early_penalty: 0.5` (yaml:513); `reliability.defense_seasons_to_stabilize: 3` (yaml:507)
- `reliability.hitter_regression_pa: 600`, `pitcher_regression_ip: 250` (yaml:505-506)
- `wag.standardized: percentile` (yaml:421); `wag.meaningful_exposure: {hitter_pa: 200, pitcher_ip: 80}` (yaml:422); `wag.baseline_fv: pre_debut` (yaml:423 — config echo only, surfaced in the methodology snapshot `value_framework.py:4030-4035`, not consumed by logic); `wag.boom_bust: {boom_percentile: 0.80, bust_percentile: 0.20}` (yaml:430)
- `fit.bayes.credible_mass: 0.90` (yaml:125) → z = 1.6449 (scipy `norm.ppf`, hardcoded fallback `1.6448536269514722`, `value_framework.py:2545-2551`)
- `buckets.midpoint_war: 0.0 / 1.0 / 2.0 / 3.2 / 5.0` (yaml:38-42); `service_time.control_years: 6` (yaml:300)
- aging: peaks 27/25 (yaml:286-287), climb 0.04 (yaml:288), decline 0.07 (yaml:289), floor 0.25 (yaml:290)
- Legacy `_grad_wag` code literals (`storage.py`): floors 150 PA / 50 IP (5380); blend 0.70/0.30 (5398); penalties 0.45/0.72/0.85/0.85, clamp [0.25, 1.0] (5310-5319); boom/bust +2.5/−1.5 (5431-5434); label floor 2 seasons / 800 PA / 200 IP (5428); farm gates ≥3 grads (`wag_mean`, 11619-11620), ≥5 settled (boom/bust %, 11612-11616); `FARM_WEIGHT_TALENT_TRANSLATION = 0.18` (`storage.py:4567` — legacy blend only, overwritten)
- Frontend literal tables: `FV_WAR_ANCHORS` (`prospx/index.html:22136-22139`) — static, must be re-synced by hand whenever the survivor curve recalibrates; personal-denominator thresholds PA ≥ 300 / IP ≥ 50 with fallback 600 PA / 130 IP (`22490-22491`); AB→PA ×1.1 (`22542`)
- eFV consumer: `_WAG_MIN_SPEARMAN = 0.10`, `_WAG_MIN_N = 100` (`efv_model.py:345-346`), clamp `(0.35, 0.90)`, fallbacks `{hit: 0.85, pit: 0.80}` (`efv_model.py:317-318`), reselect override `{hit: 0.70, pit: None}` (`efv_model.py:332`)

## Edge cases & guardrails

- **Bad FV**: `wag()`/`expected_war()` return `None` for missing/unparseable/non-finite FV (`value_framework.py:2598-2605`, via `p_bucket_given_fv`'s same contract at `755-762`).
- **Zero exposure continuity**: `seasons <= 0 or sample <= 0` returns an all-zero WAG with `percentile 0.5`, `z 0`, `below_meaningful_exposure: True` (`value_framework.py:2692-2701`).
- **Meaningful-exposure gate**: real accumulated PA/IP (not season-implied) vs 200 PA / 80 IP; below it the label is forced `unsettled` and the display layers suppress the number (`value_framework.py:2676-2678`; `build_site.py:1152`; `prospx/index.html:10271`).
- **Reliability shrink**: `regressed_wag = w_obs * rate_wag` — a thin sample shrinks hard toward 0; degenerate `sd == 0` → `z = 0` (`2707`); PIT component with `sw ≤ 1e-12` degrades to a step function (`value_framework.py:2710-2712`); PIT clamped to [0,1] (`2713`).
- **Reliever safety**: graded on the 200-IP band scale, never the bullpen-haircut value scale (`value_framework.py:2618-2621`; `_talent_regression` docstring `2334-2336`).
- **Export robustness**: the whole `debuted_value.wag` bake is wrapped in `try/except: pass` — a numerical hiccup drops the block rather than sinking the export (`storage.py:6521-6557`); `_engine_wag_result` likewise returns `None` on any exception (`storage.py:6463-6464`). Players with no MLB WAR record (or empty seasons map) carry **no** `debuted_value` at all (`storage.py:6482-6484`).
- Legacy path: `None` below 150 PA / 50 IP unless the baked `war_per_yr` fallback exists (`storage.py:5380-5388`); positive-WAG-only churn/age/minors damper (never softens underperformance, `5290-5295`); org `wag_mean` requires ≥3 qualifying grads else `None`/"—" (`storage.py:11619-11620`), boom/bust % requires ≥5 settled grads (`storage.py:11612-11616`); farm letter grade additionally gated on ≥3 grads (`13634-13636`).
- Frontend recompute: null (excluded/sunk in sorts) below 1 personal-denominator full-season-equivalent or without an FV (`prospx/index.html:22569`, `22615-22620`); "No equally-weighted fallback - better to render nothing than a misleading number" (`22476-22477`).
- Overseas path: all-None `{career_war, war_per_yr, wag}` when the signing never reached MLB (`overseas_export.py:455-458`); `_grad_wag` call wrapped in try/except → `wag: None` (`482-485`).

## Dependencies & discrepancies

**Consumes**: bWAR (Baseball-Reference war_daily via pybaseball — the "one WAR source site-wide" per the `war` glossary entry, `data/glossary.json:1500-1512`), MLB StatsAPI PA/IP, consensus FV, **xfv/efv** (`xfv_grade` as the preferred grade baseline in the engine + farm-rollup paths, one run stale by design), and the **value_framework** fitted bucket model + empirical anchors (the same artifact that prices surplus — deliberate single calibration; `survivor_expected_war` docstring `value_framework.py:787-792` and `storage.py:5022-5030` both state this "single source of truth" intent).
**Feeds**: **efv** (blend-lambda calibration plumbing via `regressed_wag`/`w_obs` — currently overridden/gated out), farm report card (talent_translation leaf display + letter + rank; boom/bust % leaves in the live composite; WAG itself dropped from the live composite at v40), trade-machine hindsight board, display metric slot, WARWAG, Overseas signings export.

**Discrepancies (all confirmed in code):**
1. **Three implementations disagree numerically.** Engine `debuted_value.wag` (pill, hindsight board, eFV calibration) vs legacy `_grad_wag` (farm-grade org rollups + overseas) vs the JS `gradVsFvProjection` (Debuted-tab sorts/chart/WARWAG/cohort blocks/rank pill). The comment at `storage.py:6444-6445` claims `_engine_wag_result` "replaces `_grad_wag`", but `_grad_wag` is still live at `storage.py:11218` and `overseas_export.py:483`, and in the frontend mirror.
2. **Different expectation baselines.** Engine `expected_war` is the **bust-inclusive** mixture over the player's exposure (bust bucket cum-WAR 0 included, `value_framework.py:2617-2624`); legacy + frontend measure against the **survivor** (non-bust-conditioned) curve. The registry champion string "survivor curve from the calibrated bucket model" (`data/model_registry.json:240`) matches the legacy/frontend baseline, not the engine.
3. **Different grade inputs.** Engine and farm-rollup `_grad_wag` use eFV (`xfv_grade`) with consensus fallback; the frontend recompute and the overseas export use consensus only; the farm-rollup's *boom label* also uses consensus (`storage.py:11349-11354`) while its *WAG* uses eFV (`storage.py:11220`) — the same rollup mixes baselines.
4. **Frontend anchor drift risk — twice over.** `FV_WAR_ANCHORS` is a hand-synced literal snapshot of `survivor_expected_war`; a `--fit` recalibration changes the backend curve without touching it — and additionally reverts the hand-amended sub-45 empirical anchors in the fit file itself (`anchors_provenance`), so a naive refit desynchronizes three layers at once.
5. **Two boom/bust labels ship on every debuted payload.** Top-level `boom_label` = legacy thresholds (WAG ≥ +2.5 / ≤ −1.5, floor 2 seasons/800 PA/200 IP, `storage.py:10081-10087`); `debuted_value.wag.boom_label` = engine percentile ≥ 0.80 / ≤ 0.20, gate 200 PA/80 IP. The frontend reads only the engine one directly (`prospx/index.html:20401`); farm boom/bust % leaves (which DO sit in the live farm composite) use the legacy one.
6. **Glossary vs code.** `data/glossary.json` `wag` (`614-637`) documents only the legacy formula `(career_war / mlb_seasons) − expected_war_per_season(FV)` with the +2.5/−1.5 thresholds and 150 PA/50 IP floor. It omits (a) the positive-delta `0.70/0.30` blend + churn/age/minors penalty that the legacy and frontend paths actually apply, (b) the entire engine WAG (`regressed_wag` — which is the number the WAG pill actually displays — percentile/PIT label, reliability shrink), and (c) the eFV-baseline substitution. The `warwag` entry's example (`glossary.json:654`) says "FV-55 expects ~2.5" — that matches the *retired* FanGraphs-primer curve, not the current anchors (FV-55 hitter → 1.13/season); the `wag` entry's own example ("FV 60 expects ~1.57/season", `glossary.json:629`) matches the current anchors. Flag: the published formula does not fully agree with any of the three code paths.
7. **Farm-composite weight is a fossil.** `FARM_WEIGHT_TALENT_TRANSLATION = 0.18` weights WAG only in `farm_score_legacy` (`storage.py:13557-13569`), which is overwritten by the tree composite (`14046`); v40 dropped the WAG leaf from the live `mlb_production` rollup (`13968-13971`). Anyone porting "WAG feeds the farm grade at 18%" would be reproducing dead code.
8. Minor: the engine wrapper's PA-from-AB fallback multiplier is `1.1` (`storage.py:6429`, matching the frontend `22542`) vs `1.13` in the legacy path (`storage.py:5281`); the frontend pitcher full-season fallback denominator is 130 IP (`22491`) vs the backend's 200 IP band; `makeWagChart` bars compare each season's raw WAR against the full-season baseline regardless of partial playing time (`prospx/index.html:22658-22659`).

Key files: `c:\Users\noah\baseball-projects\BaseballR\prospect-tracker\value_framework.py`, `value_framework_config.yaml`, `storage.py`, `overseas_export.py`, `data\value_framework_fitted.json`, `data\model_registry.json`, `data\glossary.json`, `prospx\index.html`, `build_site.py`, `efv_model.py`, `stats.py`, `run_monthly.py`.

### Verification log

Every quantitative claim in the draft was re-checked against the code. Corrections and additions:

1. **`_talent_regression` line range corrected** 2343-2387 → 2325-2387 (`value_framework.py:2325` is the `def`).
2. **Farm-composite claim corrected (material)**: the draft said WAG is "normalized into the farm-grade composite ... weight `FARM_WEIGHT_TALENT_TRANSLATION = 0.18` ... and letter-graded". In fact the 0.18 weight feeds only `farm_score_legacy` (`storage.py:13557-13569`), which is overwritten by the tree composite at `storage.py:14046`; the v40 comment at `storage.py:13968-13971` explicitly drops the `talent_translation` (WAG) leaf from the live `mlb_production` parent (`13972-13979`). WAG's surviving farm-grade footprint: leaf display/tooltip, component rank (`13595`/`13617`), letter grade (`13634-13636`), and the legacy-label-derived boom/bust % leaves which remain in the live composite (`13803-13815`). Added as Discrepancy 7.
3. **eFV blend-lambda claim corrected (material)**: the draft's §E omitted `_BLEND_LAMBDA_RESELECT = {"hit": 0.70, "pit": None}` (`efv_model.py:332`), which `blend_lambda` checks BEFORE the WAG calibration (`efv_model.py:543-546`) — the hitter lambda is hand-pinned and never consults WAG; the pitcher side currently fails the `|spearman| ≥ 0.10` gate (in-code measurements: pit ~0.001, hit ~0.066). WAG's lambda path is live plumbing but currently sizes no production lambda. `blend_lambda` def is at `efv_model.py:524` (draft said 525-556).
4. **Missing production consumer added**: `overseas_export.py` imports `_grad_wag` (`overseas_export.py:77`) and exports a per-signing `wag` (`_signing_performance`, `overseas_export.py:446-486`; emitted at `556`/`656`) into `data/overseas_timeseries.json`; baseline is graduate `fv_close` else overseas consensus FV (never eFV), and no transactions/age/level are passed so the outcome penalty degrades to 1.0.
5. **Frontend gate detail corrected/expanded**: the draft said the JS gate is "≥1 full-season-equivalent of playing time" — verified, but the denominator is the **personal** full season from `gradPersonalFullSeason` (`prospx/index.html:22484-22514`): mean of own MLB seasons ≥300 PA / ≥50 IP, fallback **600 PA / 130 IP** (130, not the backend's 200 IP). Gate literal `count < 1 || totalFrac < 1.0` at `22569`. AB→PA ×1.1 at `22542`.
6. **Additional frontend consumers added**: `_debutFvCohortBlock` FV-tier cohort ranks (`prospx/index.html:14720-14760`), graduate detail-page WAG rank pill over `DATA.debuts` (`45779-45800`), farm report-card tree UI cells reading org `wag_mean` (`38261-38311`, `39352`, `41860`).
7. **Fit-file hand-amendment hazard added**: `empirical_anchors.anchors_provenance` in `data/value_framework_fitted.json` documents the 2026-07-29 sub-45 knot amendment and states "Running value_framework --fit WILL revert this key"; guarded by `test_value_framework::test_low_end_anchors_are_present_and_measured`. Cohort n field name is `n_cohort` (=3460, verified); `generated_at: 2026-06-21`.
8. **One-run-lag gotcha added**: `_load_xfv_join` reads the PRIOR run's committed `data/xfv.json` — `export_timeseries_json` runs before `efv_export.regen_all` and reordering would be circular (`storage.py:4887-4894`), so the engine/farm WAG eFV baseline is always one pipeline pass stale.
9. **Glossary line ranges corrected**: `wag` entry is `data/glossary.json:614-637` (draft: 615-636), `warwag` `638-662` (draft: 639-661), `war` entry `1500-1512` (draft: 1512-1513 — definition line is 1512). Added the stale WARWAG example ("FV-55 expects ~2.5" = retired primer curve vs current anchor 1.13) to Discrepancy 6.
10. **Minor line-range fixes**: `_fv_war_scale` def at `value_framework.py:961` (draft: 960); aging config constants at `value_framework_config.yaml:286-290` (draft: 284-290); `_wag_badge` ends at `build_site.py:1876` (draft: 1873); `display_metric_for` def at `build_site.py:1097` with the WAG branch at 1150-1157 (draft: 1149-1157); registry row spans `data/model_registry.json:236-249` (draft: 237-248); sort chips block `prospx/index.html:9549-9556`; WARWAG sort handling `30456-30474`; `_calibrated_midpoints` at `value_framework.py:936-945` (draft: 937-945); reliever-flag lines `2618-2621`.
11. **Ordered-logit direction clarified**: code is `P(Y ≤ j) = logistic(cutpoint_j − slope·FV)` (`value_framework.py:701-708`), algebraically identical to the draft's `P(bucket > j) = sigmoid(slope·FV − cutpoint_j)`; stated in the code's own form.
12. **Import aliases documented**: `storage.py:6279-6280` (`wag as _engine_wag`, `wag_boom_bust as _engine_wag_boom_bust`).
13. **`wag.baseline_fv: pre_debut` clarified**: config echo only — surfaced in the methodology snapshot (`value_framework.py:4030-4035`), consumed by no computation.
14. **Test inventory added**: `test_wag.py` (18), `test_wag_stress.py` (2), `test_wag_validation.py` (5), plus `test_boom_bust.py` / `test_farm_grades.py`.
15. All other claims verified exactly as drafted, including: fitted slopes/cutpoints to full precision, training n 678/437, empirical + seed + legacy-fallback + frontend anchor tables value-for-value, all yaml constants and their line numbers (505-513, 419-430, 38-42, 161, 184-187, 286-290, 300), engine formulas (PIT, z, regressed band with `credible_mass 0.90` → 1.6448536269514722), the season-matched `rate_wag` vs real-PA `w_obs` subtlety, `service_years = len(seasons)` at `storage.py:6528`, `wag_fv` at `9768`/`6533`, legacy steps (floors 150/50, blend 0.70/0.30, penalties 0.45/0.72/0.85/0.85 clamp [0.25,1.0], label floors), farm gates ≥3/≥5, bWAR sourcing (`stats.py:3255-3368`), run_monthly call sites (655/3240/1578-1580), sidecar writes (15488/15504/15540), `efv_export.py:253` diagnostic, `tools/bucket_age_head/patched/` lab copy, MODEL_REGISTRY.md:26, ARKMETRIC_SCALE_CONVENTIONS.md absence, and `_wag_for_player`/`wag_leaderboard`/`wag_mean_by` having no production caller.


---

# value_framework ($/WAR series + surplus $)

## Name in code & where computed

**In-code names / keys (casing matters):**

| Quantity | Key / function | Where |
|---|---|---|
| $/WAR level (flat) | `dollars_per_war.flat`, `dollars_per_war_flat()` | `value_framework_config.yaml:232`, `value_framework.py:535` |
| $/WAR tiered rates | `dollars_per_war.tiered.rates` = `{lt_1, "1_to_2", "2plus"}`, breakpoints `[1.0, 2.0]` | `value_framework_config.yaml:233-235` |
| Per-season $ value of WAR | `tiered_war_value_usd(season_war)` (`value_framework.py:457-482`) / pure kernel `_tiered_war_value(...)` (`:485-508`) | `value_framework.py` |
| FA-implied $/WAR series | `data/fa_dpw_series.json` key `usd_per_war_by_winter` | written by `fa_backtest.py:638-652` |
| Expected surplus (raw USD) | `expected_surplus_usd(fv, is_pitcher, position, age=, eta_years=)` | `value_framework.py:1443-1508` |
| Calibrated surplus ($M, 1 dp) | `surplus_value_mm(...)` | `value_framework.py:1618-1648` |
| Dollar calibration layer | `apply_calibration` (`:1583-1615`), `calibration_version` (`:1557-1572`), `calibration_stamp` (`:1575-1580`), `calibration_zero_cross_mm` (`:1514-1554`) | `value_framework.py` |
| Surplus distribution | `sv_distribution` (`:1857-1914`), `sv_draws` (`:1845-1854`), `_sv_draws_mm` (`:1777-1843`), `_dist_output` (`:1917-1943`) | `value_framework.py` |
| Epistemic CI | `sv_credible_interval` | `value_framework.py:877-930` |
| Debuted player value | `debuted_player_value` (`:2390`), `realized_consumed_seasons` (`:2209-2281`), `_realized_consumed_usd` (`:2183-2206`), `_remaining_path_surplus_usd` (`:2062-2095`) | `value_framework.py` |
| Farm rollup | `system_surplus_distribution` | `value_framework.py:1962` |
| $ per FV point | `dollars_per_fv` | `value_framework.py:1651-1670` |

**The engine.** All $/WAR and surplus math lives in one module, `prospect-tracker/value_framework.py` (4,152 lines), whose docstring declares it "Single source of truth for FV -> surplus-value ($) conversions" (`value_framework.py:6`). It contains **no hardcoded valuation constants**: every number comes from `value_framework_config.yaml` plus the generated `data/value_framework_fitted.json` (`value_framework.py:51-60`).

**Valuation sets (load-bearing split).** `value_framework.py:295-297`:

```python
_BASE_IDENTITY_SET = "prospx_current"   # byte-identical to the base config; overlay no-op
_DEFAULT_VALUATION_SET = "clemens_2026"  # production default (flipped 2026-07; MODEL mode)
```

At config load (`_config()`, `value_framework.py:218-229`) the active set's `params` from `config/valuation_sets/<id>.yaml` are deep-merged onto the base config by `_apply_valuation_overlay` (`value_framework.py:348-363`), translated by `valuation_sets.engine_params` (`valuation_sets.py:256-327`). `prospx_current` is deliberately a no-op overlay; `clemens_2026` (the **production default**, `valuation_sets.py:58`) overrides: control 7 yr, arb basis `prior_season`, arb schedule `[0.15, 0.35, 0.50, 0.75]` (pre-arb still 3), discount 0.07 with inflation 0.0, win-cost rates 6.97/8.76/13.63 flat 11.74 $M, and `disable_fa_implied: true` (`config/valuation_sets/clemens_2026.yaml:75-107`; win_cost block at `:80-84`). It does NOT override `league_min_usd` or the super-two block, so those stay at base-config values.

**Production compute path** (labs under `tools/` such as `tools/_dpw_*` and `tools/surplus_sensitivity.py` are diagnostics, not production):

1. `fa_backtest.run_market_gate(persist=True, persist_dpw=True)` writes `data/fa_dpw_series.json` from `fa_market.dollars_per_war_by_winter` (`fa_backtest.py:638-652`, `fa_market.py:533-554`). This is a gate-run artifact, refreshed when the FA gate is run, not per nightly build. `persist_dpw=False` (added 2026-07-30) refreshes the Gate-2 eval WITHOUT rewriting the $/WAR level — the module's single biggest write hazard (`fa_backtest.py:461-468`).
2. eFV regen — `efv_export.regen_all` runs from `rebuild_only()` (`run_monthly.py:742`), which the chained daily step d9 invokes (`run_monthly.py:1396-1398`) and the monthly full run reaches the same way. `efv_score.py` prices per-player `surplus_mm` via `vf.expected_surplus_usd` on the **displayed** eFV grade (`_reprice_surplus_on_display`, `efv_score.py:925-978`; live path `:1815`, resolved-matrix path `:1296-1297` — note the resolved path prices at a hardcoded `eta_years=1.0`; backgrade path `:2194`) → `data/xfv.json` with a `meta.calibration` stamp (`efv_export.py:~121-126`). The **provisional/ungraded** cohort is priced by the same APIs in `efv_ungraded.py:681`. Raw engine dollars pass through the isotonic calibration at these seams via `_cal_mm` (`efv_score.py:891`, wraps `vf.apply_calibration`; percentiles map pointwise — sound because isotonic is monotone).
3. `run_monthly.py:826-845` — `bayes_trade_value.export_trade_values_json` → `apply_platform_surplus` (`bayes_trade_value.py:4095`) **re-points** (does not recompute) each Trade Machine record's surplus to `xfv.json by_player[key].surplus_mm` (prospects), `mlb_projections.json` `surNpv/1e6` (MLB), or a tempered xFV backgrade → `data/trade_values.json`. (`surplus_value_mm` also seeds the bayes PRIOR throughout `bayes_trade_value.py`, e.g. `:2866, :3371`.)
4. `proj_export.py` — vets: `surNpv` = NPV of (projected season value at the winter $/WAR level − actual contract salary) (`_apply_contract`, `proj_export.py:283-315`; `_season_value_usd`/`_winter_dpw`, `:226-242`; discount `r = vf._config()["discount_rate"]` at `:255`; `FIRST_SEASON=2027`, `HORIZON=5` at `:59-60`); post-ETA prospects: `surNpv = surplus_value_mm(price_fv, ...) * 1e6` (`proj_export.py:604-637`). Re-run as chained daily step d9b after the eFV regen (`run_monthly.py:1408-1412`); the monthly 6b duplicate is skipped (`run_monthly.py:3345-3351`).
5. `storage.py` — `_build_surplus_payload` (`storage.py:6321-6418`) bakes `surplus.value_mm`, `ci`, `dist`, `buckets`, `star_odds` (+ `star_odds_model`, `opt_pct`, `valuation_set`, `fv_used`) into `timeseries.json` from `surplus_value_mm` / `sv_distribution` / `sv_credible_interval` on **consensus** FV. NOTE: this bake overrides the MC draw counts — `_SURPLUS_DIST_DRAWS = 4000`, `_SURPLUS_CI_DRAWS = 2000` (`storage.py:6288-6299`) — so timeseries dist percentiles use 4,000 draws, not the config 10,000 (the eFV seam and direct calls use the config default).
6. Frontend: `data/value_framework.{json,js}` snapshot (dense `sv_curve`, grade tables, all constants) is emitted by `emit_snapshots` (`value_framework.py:4062-4075`) — **only via manual CLI `python value_framework.py --emit-snapshots`**; no pipeline step calls it (verified: zero non-test, non-tools callers). `build_site.py:3197` includes `/data/value_framework.js` on the glossary page. `assets/trademachine.js` is render-only over `trade_values.json` + `mlb_player_detail.json` — the JS never recomputes surplus (`trademachine.js:4-9`).

**JS-side surplus math (know exactly what exists).** The config comment (`value_framework_config.yaml:357-362`) declares the intent that the frontend interpolate the emitted `sv_curve` instead of re-implementing the model. In the current tree **no JS file actually reads `sv_curve`**; the live JS consumer is `assets/glossary.js`, which (a) renders the FV→WAR bar viz from `window.VALUE_FRAMEWORK.fv_to_6yr_avg_war` with a **stale hardcoded fallback table** `{40:1, 45:1.5, 50:2, 55:2.5, 60:3, 65:4, 70:5, 80:7}` (the old primer scale — live anchors are ~10-20x lower at low FV) used only when the snapshot script fails to load (`glossary.js:1102`), (b) plots `surplus_by_grade_mm.hitter` (`glossary.js:1128`), and (c) has an interactive teaching widget `_gxSurplus` (`glossary.js:~1183+`) that recomputes a **simplified** surplus (warYr × control × flat $/WAR − pre-arb/arb salaries) from snapshot constants, with hardcoded fallbacks (`flat_mm 11.74`, `league_min_mm 0.76`, arb `[0.4,0.6,0.8]`). None of these feed any served valuation.

**Near-duplicate Python implementations.** `career_war_value_mm` is genuinely non-production ("NON-PRODUCTION ... NO live caller -- only tests reference it", `value_framework.py:540-555`). `point_estimate_surplus_usd` (`value_framework.py:1395-1440`) is documented as a "COLLAPSED comparator (NOT the production path)" for quantifying the Jensen gap, **but it does have live callers**: `fa_market.qo_tax_usd` uses it as the fallback pricing of forfeited QO draft picks when the fitted slot-surplus artifact is absent (`fa_market.py:59, 1176`), and `farm_grade_backtest.py:162` uses it. Do not treat it as dead code when porting.

## Formula or fitted model?

**Hybrid: a deterministic pricing pipeline with three fitted components** (an ordered-logit P(bucket|FV), empirically re-derived FV→WAR anchors, and an isotonic dollar calibration). No serialized ML binary; everything is JSON/YAML. To reproduce `surplus_value_mm(fv, is_pitcher, position, age, eta_years)` exactly under the production `clemens_2026` set:

**Step 1 — P(bucket|FV), 5-vector over `(bust, bench, regular, good, star)`.** Fitted proportional-odds ordered logit per role, evaluated at runtime (`value_framework.py:701-708, 749-771`):

```python
# P(Y<=j) = logistic(cut_j - slope*fv), j=0..3; probs by differencing, clipped/renormalized
cum_le = [_logistic(c - slope * fv) for c in cutpoints]
```

Fitted coefficients live in `data/value_framework_fitted.json` (`method: {"hitter": "proportional_odds", "pitcher": "proportional_odds"}`):
- hitter: cutpoints `[7.896939381645044, 8.898882615829814, 10.168309209219554, 12.416555560869362]`, slope `0.17502297799589095`
- pitcher: cutpoints `[7.34374550099759, 8.480670380806886, 9.836375926028913, 13.149321678505451]`, slope `0.16247947639606863`

Trained by `python value_framework.py --fit` (`fit_and_write`, `value_framework.py:3485`) on the Clemens 2025 published outcome tables embedded in `value_framework_config.yaml:63-77` (rows expanded to per-player counts `count = round(pct * n)`; rows with `n <= fit.exclude_n_le = 3` dropped, so FV≥65 rows are excluded; "+" grades on axis 47.5 via `fit.role_axes`, `yaml:97-103`). A hierarchical-Bayes MAP + Laplace posterior (`fit.bayes`, seed 20260531, `posterior_draws: 4000`, `credible_mass: 0.90`) supplies credible intervals (`bayes` block in the fitted file). Fallback if no fit file: PCHIP interpolation of the training rows (`value_framework.py:726-746`).

**Step 2 — FV → six-year-average WAR anchor.** `fv_to_6yr_avg_war` (`value_framework.py:621-646`) piecewise-linear interpolates, clamped. Because `anchor_calibration.use_empirical: true` (`value_framework_config.yaml:184-200`) and the fit file carries `empirical_anchors`, **production uses the fitted empirical anchors**, not the yaml seed:

```
{"20":0.012, "25":0.014, "30":0.016, "35":0.019, "40":0.086, "45":0.31, "50":0.67,
 "55":0.98, "60":1.44, "65":2.0, "70":2.52, "80":3.5}   # data/value_framework_fitted.json empirical_anchors.anchors
```

(yaml seed/fallback: `fv_to_6yr_avg_war: {35:0.12, 40:0.22, 45:0.38, 50:0.70, 55:0.95, 60:1.45, 65:1.95, 70:2.60, 80:3.80}`, `value_framework_config.yaml:161`). The 45-80 knots were derived by `--fit`'s continuous anchor calibration from resolved cohorts in window `[year-12, year-6]` (currently [2014, 2020]; `n_cohort` 3,460), blended toward the Edwards-implied `public_reference` (weight 0.5 base + 0.4 extra as tier n→0, `min_cohort: 200`, `min_n_robust: 40`). **CRITICAL PORTING GOTCHA:** the sub-45 knots (20/25/30/35/40) were **hand-amended on 2026-07-29** (measured on `target_censored`: FV35 0.0188 n=909, FV40 0.0862 n=2083; 20/25/30 are an extrapolated monotone ramp, "a floor, not a finding") and are **NOT reproducible by the fit machinery — running `value_framework.py --fit` WILL revert this key** (the `anchors_provenance` string in the fitted file documents why: `anchor_calibration.tiers` starts at 40, the public-reference fallback and flat 0.50 blend weight reproduce the old defect, and `round(v,2)` collapses sub-45 values). Guarded by `test_value_framework::test_low_end_anchors_are_present_and_measured`. Ship the fitted file verbatim; do not regenerate it casually.

**Step 3 — FV-dependent bucket WAR levels.** Fixed bucket shape midpoints `(0.0, 1.0, 2.0, 3.2, 5.0)` (`buckets.*.midpoint_war`, yaml:36-42; read by `_calibrated_midpoints`, `value_framework.py:936-945`) scaled by `k(FV) = anchor(FV) / Σ_b P(b|FV)·midpoint_b` (`_fv_war_scale`, `value_framework.py:960-982`; FV rounded to 0.5 for caching, `_war_scale_for` `:985-992`). So the P-weighted 6yr-avg WAR reconciles to the anchor at every FV. (`war_anchor_scale` is a diagnostic-only lever, default 1.0, `:948-957`.)

**Step 4 — per-bucket season WAR paths.** `_bucket_season_wars` (`value_framework.py:1135-1144`): level = midpoint·k(FV) (relievers: `min(reliever_war_ceiling=1.5, mid*65/200)` via `_reliever_level`, `value_framework.py:1114-1132`), times a mean-1.0 trajectory shape. With aging enabled and debut age known, the shape is the asymmetric tent `_aging_multiplier` (`value_framework.py:1075-1085`): climb 0.04/yr before peak (hitter peak 27, pitcher 25), decline 0.07/yr after, floor 0.25, renormalized to mean 1.0 (`_trajectory_shape`, `:1091-1111`); else fixed `bucket_trajectory_shape.default = [0.80,0.95,1.05,1.10,1.10,1.00]` (bust all-zero). `debut_age = age + eta_years` (`_resolve_timing`, `value_framework.py:1344-1365`). Note: with `control_years: 7` (clemens_2026) the 6-length fixed shape is tiled+renormalized to 7 (`value_framework.py:1107-1110`).

**Step 5 — per-season $ market value (the convex $/WAR kernel).** `value_framework.py:485-508`, production `kernel_mode: smoothed`:

```python
b1, b2 = 1.0, 2.0; r_lo, r_mid, r_hi = 6.97e6, 8.76e6, 13.63e6   # clemens_2026 rates
c_lo, c_mid, c_hi = b1 - 0.5, b1 + 0.5, b2 + 0.5   # tier centers: 0.5, 1.5, 2.5
if w <= c_lo:   rate = r_lo
elif w <= c_mid: rate = r_lo + (r_mid - r_lo) * smoothstep((w - c_lo)/(c_mid - c_lo))
elif w <= c_hi:  rate = r_mid + (r_hi - r_mid) * smoothstep((w - c_mid)/(c_hi - c_mid))
else:            rate = r_hi
value = w * rate            # WAR<=0 or None -> $0; smoothstep(t)=t*t*(3-2t)  (:448-454)
```

`"bucket_step"` mode (hard 3-step at the breakpoints) exists for calibration replication only. A back-compat hard-step rate helper `dollars_per_war()` ($M/WAR) survives for `mlb_trade_lookup` (`value_framework.py:516-532`).

**Step 6 — service-path salaries.** `_service_path_salaries` (`value_framework.py:1200-1231`): first `pre_arb_years=3` seasons at `league_min_usd = 0.76e6` (base config `yaml:301`; clemens_2026 does not override it); then arb year i pays `frac_i ×` basis, where under clemens_2026 `arb_basis="prior_season"`: `salary_t = max(league_min, frac_i * market_{t-1})` with `frac = [0.15, 0.35, 0.50, 0.75]` (under the base `current_season` basis: `frac_i * market_t`, no explicit floor). Super-two (`super_two: {enabled: true, fraction: 0.22}`, yaml:310) drops one pre-arb year and prepends an early arb year at `min(super_two_first_fraction=0.25, frac[0])` — clamped to 0.15 under clemens_2026 (`_arb_ladder`, `value_framework.py:1179-1197`); the standard and super-two paths are blended 0.78/0.22 (`_bucket_sv_usd`, `value_framework.py:1234-1257`).

**Step 7 — discounting.** One net factor per season (`_service_path_surplus_usd`, `value_framework.py:1154-1176`):

```python
net = (1.0 + infl) / (1.0 + r)                      # clemens_2026: (1+0.0)/(1+0.07)
SV  = Σ_t (market_t - salary_t) * net ** (eta_years + t)
```

`discount_from: debut` means `eta_years` (years to projected debut) adds discounting before any surplus accrues (`value_framework_config.yaml:274-283`).

**Step 8 — pitcher role mix.** `_effective_bucket_sv` (`value_framework.py:1290-1309`): each pitcher bucket blends full-SP and bullpen-capped-RP values by `P(reliever|bucket)` = `{bench:0.60, regular:0.45, good:0.20, star:0.05}` (`yaml:349`); SP tag scales those by 0.40 (`starter_tag_multiplier`); RP tag forces 1.0 on non-bust buckets (`_pitcher_rp_by_bucket`, `:1270-1287`); `injury_hazard: 0.0` (off).

**Step 9 — expected surplus + low-tier anchor + monotonicity floor.** `expected_surplus_usd` (`value_framework.py:1443-1508`):
- FV ≤ `cutover_fv=40`: Edwards dollar anchor `2.0e6` (pitcher ×0.90), decayed `exp(-0.16*(40-fv))` below 40, discounted by `net**eta` (`_lowtier_anchor_usd`, `value_framework.py:1379-1392`).
- 40 < FV < `bridge_to_fv=45`: linear bridge anchor→pipeline (pipeline evaluated at FV45's WAR scale, `:1475-1480`).
- FV ≥ 45: mixture pipeline `Σ_b P(b|FV) · bucket_SV_b` (`_pipeline_surplus_from_svs`, `:1371-1376`).
- C6 floor: `base = max(base, _lowtier_anchor_usd(min(f, cutover), role, ee))` (`value_framework.py:1505`) so a better grade can never price below a worse one (reliever bridge inversion fix; the bridge dipped DOWNWARD for RP because the bullpen-capped pipeline at FV45 was $1.668M vs a $1.800M anchor at FV40 — the served effect once compounded to a FV44.5 reliever pricing 28x below a FV40 one, `:1484-1505`).
- Then `max(0.0, base * position_multiplier)` (multiplier is 1.0 in production; `apply_market_scarcity: false`, `yaml:323`; `apply_position_mult=False` gates ONLY the multiplier, never the role tag).

**Step 10 — dollar calibration (the fitted output layer).** `surplus_value_mm = round(apply_calibration(expected_surplus_usd/1e6), 1)` (`value_framework.py:1644-1648`). The shipped calibration (`value_framework_config.yaml:525-544`) is `enabled: true`, `method: isotonic`, **version `"isotonic-real-v6-evframe-2026-07-31"`** (`yaml:538`), a monotone piecewise-linear interpolation over knots (`yaml:541-543`):

```yaml
x_mm: [0.82, 1.1, 1.42, 1.85, 2.09, 3.34, 5.06, 8.04, 9.59, 19.35, 36.42, 400.0]
y_mm: [0.67, 1.59, 2.78, 2.95, 3.48, 5.2, 9.3, 13.76, 20.78, 35.68, 57.56, 523.59]
```

Fitted by `tools/fit_surplus_calibration.py` (count-weighted PAVA on equal-count bin **means** — an expected-value objective, $0 floor removed; `ys[0]=0.67`) on the `surplus_backtest_real` resolved pool 2017-2019 n=2236, on the normalized consensus frame production serves; region above the $36.42M knot is linearly extrapolated (final fitted segment slope 1.2818 continued to a 400 knot), documented as EXTRAPOLATED in `fit_provenance` (yaml:544, which also preserves the superseded v5 linear map `max(0, 1.382491*raw − 2.318551)`, v4, and v3 knot tables). Clamped flat outside `[x_mm[0], x_mm[-1]]` (inputs below 0.82 → 0.67; above 400 → 523.59); malformed table → identity (`value_framework.py:1599-1613`). The v6 map deliberately LOSES v5's MAE gate (13.581 vs 11.518, 3/3 folds) and wins the EV metrics (held-out bias −0.028 vs +2.521 uncal; slope 1.059) — surplus is consumed as a PRICE (an expectation), and MAE is minimized by the conditional median, which is $0 for 86-90% of bottom bins. Spec docs: `docs/efv-2026-07-30/SURPLUS_EV_OBJECTIVE.md`, `docs/efv-2026-07-31/SURPLUS_PRICING_KEY_GATE.md` (both exist).

**Distribution contract** (`sv_distribution`, `value_framework.py:1857-1914`; draws built in `_sv_draws_mm`, `:1777-1843`): Monte Carlo (10,000 draws by default via `output.monte_carlo_draws`, `yaml:403` — the `distribution.monte_carlo_draws: 20000` is the superseded fallback, `yaml:376`; storage's timeseries bake overrides to 4,000). RNG seed `(base_seed + round(fv*100) + is_pitcher) % 2^32` with `base_seed = distribution.seed = 1234567`. Bucket sampled ~ P(bucket|FV), within-bucket mean-preserving Gamma with cv `{bust:0, bench:0.30, regular:0.38, good:0.48, star:0.70}` (`yaml:382-387`); bucket means pre-scaled so the mixture mean equals the anchor-adjusted expected surplus; sample re-centered multiplicatively to the exact mean. Source disagreement (across-source FV stddev) inflates cv in quadrature via `fv_sd_to_cv=0.12` without moving the mean (`:1808-1816`). Output keys: `mean` (2 dp; `surplus_value_mm` rounds to 1), `percentiles` p10/25/50/75/90 (`output.percentiles`, `yaml:401` — the docstring's "p5/p50/p95" example is illustrative, config wins), `p_bust`, `p_above_threshold` (threshold `distribution.sv_threshold_mm = 50.0`), `downside_metric` = CVaR over the worst quartile (`output.downside_metric: cvar_25` parsed by `_downside_quantile`, `value_framework.py:404-421`), `risk_adjusted_score = mean − λ(mean − downside)` with top-level `risk_aversion_lambda = 0.0` (`yaml:405`), plus `std`, `mc_mean`, `draws`, `fv_sd`, `fv_dispersion`, `n_sources`.

**Debuted-player mode** (`debuted_player_value`, `value_framework.py:2390`): value = REALIZED (each consumed season: actual fWAR priced through the tiered kernel minus actual/estimated salary, compounded forward at `(1+r)^(n-1-i)`; `_realized_consumed_usd`, `value_framework.py:2183-2206`; `realized_consumed_seasons`, `:2209-2281` — Spotrac `salary_by_year` overrides the engine's own service-time estimate per year; realized market uses `market_mm` = `tiered_war_value_usd(fwar)` with a legacy `fwar × hard-step dpw` fallback; historical `league_min_by_year` table `yaml:583-592` covers realized seasons) + REMAINING (bucket posterior Bayes-updated by observed WAR; `_remaining_path_surplus_usd` prices seasons `start_k..end` on the actual service clock honoring `arb_basis` + the league-min floor, discounting from now, `:2062-2095`; role-mixed via `_effective_remaining_bucket_sv`, `:2115-2134`; graduated continuous-talent branch `_remaining_continuous_sv_usd`, `:2137-2151`). Reduces exactly to the prospect model at 0 MLB exposure (`start_k=0`, eta=0).

**How a backend team should port it:** implement the deterministic pipeline above; ship the two JSON/YAML artifacts verbatim (`value_framework_config.yaml` + `config/valuation_sets/*.yaml`, `data/value_framework_fitted.json` — remembering the fitted file's hand-amended sub-45 anchors are not regenerable); version-pinning is via the config `calibration.version` string stamped into every artifact (`calibration_stamp`, `value_framework.py:1575-1580`), registry row `prospect_surplus` in `data/model_registry.json` (champion "career-path mixture + isotonic-real-v6-evframe calibration (2026-07-31; count-weighted binned PAVA on the production/normalized frame, targeting the conditional MEAN)", eval `data/surplus_backtest_real.json`), and snapshot-drift tests (`test_value_framework_integration.py:37-60`: on-disk `value_framework.json` must equal a fresh `build_snapshot()`, and the JS sidecar must round-trip to the same payload).

## Inputs

| Input | Field name | Ultimate source | Computed stat? |
|---|---|---|---|
| FV grade | `fv` (continuous, 20-80) | consensus FV (`consensus.py` mean of scraped source lists) on the storage path; **displayed eFV grade** `xfv_grade_display` / `_odds_grade` on the xfv path (`efv_score.py:954, 1296, 1815`) | Yes — the eFV/xFV model output for xfv.json rows; raw scouting consensus for `timeseries.json` `surplus` leaves and `consensus_surplus_mm` |
| Role | `is_pitcher` / `position` | roster/position strings from ingest; classified by `position.pitcher_positions` = `[RHP, LHP, SP, RP, MIRP, SIRP, P, CL]` / `reliever_positions` = `[RP, SIRP, MIRP, CL]` (yaml:334-335) | No |
| Age | `age` | player bios (MLB StatsAPI / list ingests) | No |
| ETA gap | `eta_years` | ETA estimates (`_eta_years_from`, `storage.py:6309-6318`, half-season aware); prospect fallback `PROSPECT_ETA_FALLBACK_YEARS = 1.0` (`storage.py:6306`), shared by both surplus writers (efv_score imports it) | Yes (derived from ETA model) |
| Source spread | `fv_dispersion`, `n_sources` | population stddev of per-source FVs (consensus layer) | Yes |
| $/WAR level (optional re-anchor) | `data/fa_dpw_series.json` `usd_per_war_by_winter` | Spotrac-ingested FA signings (deferral-adjusted `npv_guarantee_usd` numerator) + projected contract WAR paths; per winter: `Σ NPV guarantee / Σ discounted projected contract WAR`, winters kept only if `Σwar > 20` and `n ≥ 25` (`fa_market.py:533-554`) | Yes — FA module output; **not consumed under the production clemens_2026 set** (see below). Also read directly by `fa_class.py:239`, `fa_export.py:649`, `proj_export.py:239` |
| Salaries (realized/vets) | `salary_by_year` / contract `salary_by_year` | Spotrac contract ingest (`spotrac.py` via fa/proj pipelines) | No |
| Realized WAR | `fwar` per season | recorded WAR (bWAR site-wide per owner decision) via timeseries/debuts | No |
| Outcome training tables | `p_bucket_given_fv_{hitter,pitcher}` | Ben Clemens, FanGraphs 2025 (transcribed literals, yaml:63-77) | External data |
| Contract conventions | arb schedule/basis, control years, discount | `config/valuation_sets/clemens_2026.yaml` (fetched from FanGraphs 2026-07-03, checksum-guarded in `valuation_sets.py:84-95`, tolerances 0.05 $M / 0.001 odds) | External data |

Dependencies on other documented stats: **efv/xfv** supplies the grade the xfv-path surplus is priced on (and surplus feeds back into xfv.json rows); **wag** consumes `survivor_expected_war` (`value_framework.py:786-802`) so WAG and surplus share one FV→WAR map; **value_framework feeds** trade machine, FA module (discount via `fa_market._discount_rate`/`_dpw_inflation`, `fa_market.py:58-59, 219-224` — note `dollars_per_war_inflation` is 0.0 under production clemens_2026, which silently no-op'd three FA de-staling mechanisms until the FA lane grew its own fitted rate, registry BUG-2 2026-07-24), MLB Projections, farm grades (`storage.py:~11051`), draft pool efficiency, `bayes_trade_value` prior, QO pick tax (`fa_market.qo_tax_usd` fallback). It does **not** consume rem/sem/hem/stuff/swing/collegesavant/draft_stock (stuff_plus appears only in bayes_trade_value archetype gates, a different model).

## Constants, baselines & normalization

This is not a "+"-scaled stat; there is no 100-baseline. All constants and their homes:

- **$/WAR baseline (production, clemens_2026):** flat `$11.74M`, tiers `lt_1 $6.97M / 1_to_2 $8.76M / 2plus $13.63M`, breakpoints `[1.0, 2.0]` WAR — the **2024-2026 FA-signings average** published by FanGraphs, stored in `config/valuation_sets/clemens_2026.yaml:80-84`. Static (checksum-guarded); updated only by a deliberate set re-fetch. The base-config table (same values, `value_framework_config.yaml:232-235`) is a hand-computed trailing 3-yr mean of `historical_dollars_per_war` (yaml:573-580) — "re-average annually as new years are appended" (v44 note).
- **FA-implied re-anchor** (`_apply_fa_implied_reanchor`, `value_framework.py:178-215`): when `dollars_per_war.fa_implied.enabled`, the flat level is replaced by the trailing-`trailing_years=3` winter mean of `data/fa_dpw_series.json`, and every tier rate scales by `level/base_flat` (convex shape preserved; the `_fa_reanchor` provenance dict is written into the loaded config). Recomputed **at config load** from whatever series file is committed; the series itself is rewritten only when `fa_backtest.run_market_gate(persist=True, persist_dpw=True)` runs (registry `fa_dpw_series`, champion `fa_signings_implied_v1`, eval `data/dpw_forecast_eval.json`). **Under the production default clemens_2026 this is DISABLED** (`disable_fa_implied: true` → overlay writes `fa_implied.enabled=false`, `valuation_sets.py:275-279`); it is live when pricing under `prospx_current` (`config/valuation_sets/prospx_current.yaml:112`, `disable_fa_implied: false`).
- **Discounting:** clemens_2026 `discount_rate = 0.07`, `dollars_per_war_inflation = 0.0` (net-7%-flat, `engine_params` discount translation `valuation_sets.py:285-298`); base config fallback 0.09 / 0.05 (yaml:258, 283).
- **Service time:** clemens_2026 `control_years 7`, `pre_arb_years 3`, arb `[0.15,0.35,0.50,0.75]` of prior-season FA-equivalent value, league min `$0.76M` (base value, not overridden; the `league_min_by_year` table yaml:583-592 is used for realized historical seasons), super-two fraction 0.22 with first-fraction 0.25 clamped to arb-1.
- **Bucket shape:** midpoints `(0, 1.0, 2.0, 3.2, 5.0)` WAR; reliever normalization `65 IP / 200 IP` (`reliever_full_season_ip` / `pitcher_band_ip`), ceiling 1.5 WAR; legacy `relief_war_haircut 0.50` fallback if IP keys absent (yaml:330-333).
- **Low-tier anchor:** `$2.0M` at FV40 (pitcher ×0.90), decay `0.16`/FV-pt, cutover 40, bridge to 45 (yaml:209-216).
- **Aging:** peaks 27/25, climb 0.04, decline 0.07, floor 0.25 (yaml:284-290).
- **Calibration knots:** in `value_framework_config.yaml:541-543` (values quoted above); baseline population = resolved 2017-2019 prospect cohorts (n=2,236), refit manually, versioned; recomputed only by an owner-gated re-fit, never per run.
- **Empirical anchors:** in `data/value_framework_fitted.json`; 45-80 knots recomputed only during `--fit` (rolling resolved-cohort window, currently [2014, 2020]); sub-45 knots hand-amended 2026-07-29 and NOT regenerable (see Step 2 gotcha).
- **Distribution:** draws 10,000 (`output.monte_carlo_draws`; storage bake overrides 4,000 dist / 2,000 CI), seed 1234567, cv per bucket, CVaR quantile 0.25, λ=0, threshold $50M.
- **Snapshot curve:** FV 20→80, step 0.5 (yaml:359-362).

## Edge cases & guardrails

- **Missing/invalid FV:** every dollar API returns `None` for `None`/unparseable/non-finite FV (`value_framework.py:1456-1462` and equivalents; `p_bucket_given_fv` matches the same degrade-to-None contract, `:753-762`). A legitimate $0.0 serves as 0.0, not null (`is not None` checks, `efv_score.py:967-969`).
- **Floors:** each bucket SV floored at `surplus_floor_usd` (all 0; bust ⇒ $0); final surplus floored at `max(0, ·)` (`value_framework.py:1508`) — but the served calibration no longer clamps to $0 (v6 EV frame; `calibration_zero_cross_mm` returns None on the shipped map since no `y ≤ 0` knot exists, `value_framework.py:1514-1554` — callers must treat None as "no threshold known" and show the number).
- **C6 monotonicity floor:** no branch may price below the anchor's reading for a worse grade (`value_framework.py:1484-1505`).
- **Ladder clamp:** super-two first fraction clamped ≤ arb-1 so the arb ladder is monotone under every set (`value_framework.py:1179-1197`).
- **Reliever guards:** non-finite/negative band WAR → 0 before the ceiling min (NaN would defeat `min(ceil, ·)` in CPython; `value_framework.py:1119-1132`).
- **Training-row threshold:** fit drops rows with `n ≤ 3` (`fit.exclude_n_le`, yaml:104; FV≥65 rows excluded); extrapolation carries extra posterior widening `extrapolation_extra_sd_per_fv: 0.01` logit-sd per FV-pt beyond the [45,60] data range (yaml:127, applied in `p_bucket_posterior_draws`, `:845-854`).
- **Fallback chain for P(bucket|FV):** fitted proportional-odds → per-threshold cumulative logits + isotonic monotonicity correction → PCHIP → degenerate all-bust if probabilities sum ≤ 0 (`value_framework.py:690-698, 711-723, 749-771`).
- **FA-implied re-anchor fallback:** silently keeps the curated table if `fa_dpw_series.json` is absent/malformed (`value_framework.py:193-197`).
- **Source-disagreement gates:** needs ≥ `min_sources 2`; magnitude capped at `max_fv_sd 6.0`; bad per-source values (non-numeric, non-finite FV/offset, non-positive weight) dropped, never poisoning (`aggregate_source_fvs` / `_source_fv_sd`, `value_framework.py:1698-1758`); master gate `source_uncertainty.use_dispersion` (yaml:461) supersedes `source_disagreement.enabled`.
- **Cache rounding:** FV to 0.5, debut age to 0.5 yr, ETA to 0.25 yr (`_round_timing`, `value_framework.py:1260-1264`); valuation-set switches must clear all derived caches (`_reset_caches`, `value_framework.py:244-261` — the F6 bughunt note documents the stale-PCHIP leak this prevents; `_reset_derived_caches` `:264-271` serves the in-place sensitivity harness).
- **Config validation:** malformed/missing CORE keys raise `ConfigError` at load (`_validate_config`, ends `value_framework.py:175`); valuation sets refuse to load on nulls, unknown tier labels, out-of-range star_odds, or checksum drift (`valuation_sets.py:129-194`).
- **ETA:** negative/non-finite ETA clamped to 0; `discount_from:"now"` zeroes the ETA discount gap (`value_framework.py:1344-1365`).
- **Calibration-vintage guard:** every surplus-carrying artifact must embed `calibration_stamp()` and all must agree (`test_calibration_vintage.py:35-41` maps the stamp locations: `xfv.json` `("meta","calibration")`, `trade_values.json` `("calibration",)`, `mlb_projections.json` `("calibration",)`, `timeseries.json` `("calibration",)`). This exists because on 2026-07-31 four served artifacts disagreed (v5 vs v6 maps): the v6 re-fit landed at 14:42, `timeseries.json` was written at 21:12 on the pre-change config held in memory by a long-running export; on the served board one player flipped between $87.4M (#1) and $63.4M (#4) with the grade chip.

## Dependencies & discrepancies

**What surplus is a surplus RELATIVE TO, per population:**
- **Prospects** (`timeseries.json` surplus leaves, `xfv.json surplus_mm`, prospect `surNpv`): market value of projected control-window WAR **minus modeled service-time salaries** (3 league-min pre-arb years + 4 arb years at 15/35/50/75% of prior-season FA-equivalent value, over 7 control years), net-7% discounted **from projected debut** (ETA gap included).
- **Debuted, remaining years:** same service path from the current service year, discounted from now, with bucket weights Bayes-updated by observed WAR (`debuted_player_value`).
- **Debuted, consumed years (realized ledger):** actual fWAR × tiered market − actual (Spotrac `salary_by_year`) or engine-estimated salary, compounded to present (`realized_consumed_seasons`).
- **Signed MLB vets** (`mlb_projections.json surNpv`, computed in `proj_export.py`, not in value_framework): projected per-season value at the winter's FA-implied $/WAR level escalated (`_season_value_usd`) **minus actual contract salary_by_year**, NPV'd at the platform discount rate; seasons without a filed salary carry no surplus claim (contribute `None` to `sur[]`; `surNpv` only set if any salary exists — `proj_export.py:299-315`).
- **Free agents** (`/fa/` rational value / Deal+): NPV of projected production at convex tier pricing vs actual price — a separate model (`fa_rational_value` registry row) that only borrows this engine's discount/inflation/kernel constants.

**Consumes:** eFV/xFV grade (xfv path), consensus FV (storage path), ETA model, FA-signings-implied $/WAR series (prospx_current only), Spotrac contracts, recorded WAR.
**Feeds:** `xfv.json` (`surplus_mm`, `band_p10/p90_mm`, `dist`, `consensus_surplus_mm`), `trade_values.json` (`trade_value_mm` via `apply_platform_surplus` passthrough), `mlb_projections.json` (`surNpv`, `sur[]`), `timeseries.json` (`surplus.value_mm/ci/dist/buckets/star_odds/star_odds_model/opt_pct`), farm grade Value branch, WAG (via `survivor_expected_war`), `bayes_trade_value` priors, draft-pick surplus (`valuation_sets.implied_pick_surplus`, `valuation_sets.py:330-356` — table-mode tier value minus actual bonus or slot cost; never guesses a cost), QO pick tax fallback (`fa_market.py:1176`).

**Discrepancies found:**
1. **`data/glossary.json` is stale versus the code.** The five relevant entries (in the `entries` list): `tvi` (Sur+) and `value_framework` describe the retired **v32.1** point-estimate formula (`Sur+ = (WAR_peak(fv) × 6 × ramp × p_success(fv) × $/WAR_tier(WAR_peak) − cost_basis) × position_mult`); `fv_to_war_table` publishes the OLD survivor/peak-scale table (`80→7.0 ... 45→1.5, 35→0.6` WAR/yr — the live empirical anchors are 0.31 at FV45); `bust_prob` publishes industry success-rate literals (FV50 hitter 32%) instead of the fitted ordered-logit. `dpw_tier` is PARTIALLY current (its tier rates 6.97/8.76/13.63 and flat 11.74 match config) but its "since the v3 re-anchor the tier rates rescale at load" claim only holds under `prospx_current` — the production clemens_2026 set disables the rescale. The live engine is the v2.0 career-path mixture with per-role ordered-logit weights, FV-dependent bucket scaling, the smoothstep kernel, and NO position multiplier. A matching stale comment sits above the storage import block (`storage.py:6250-6257`, labeled v32.0, same `WAR_peak * 6 * ramp * p_success * $/WAR_tier` formula and a claim that position multipliers drive value). Do not implement from the glossary or that comment.
2. **Two $/WAR regimes coexist by valuation set.** Production default (`clemens_2026`) prices at the published FG 2024-26 tier table with the FA-implied re-anchor **disabled**; `prospx_current` (base-identity, used by comparison harnesses and table-mode captures) re-anchors the level to `fa_dpw_series.json`. Any consumer that switches sets (e.g. `efv_export`'s valuation-check block, `efv_export.py:246-266`) must do so inside the `vf.valuation_set(...)` context or leak the wrong rates (the context manager restores the previous set and clears caches, `value_framework.py:316-334`).
3. **`prospx_current.yaml` tier `surplus_musd` values are a captured snapshot** of live engine output (re-captured 2026-07-31 for v6) — they go stale whenever the calibration changes and are re-captured by policy, not automatically. Re-capture must happen INSIDE the set's own valuation context (memory: pit FV60 81.3 vs 75.2 otherwise).
4. **`data/value_framework.{json,js}` regeneration is manual** (`--emit-snapshots`); a config edit without re-emitting leaves the frontend sidecar stale (guarded by `test_value_framework_integration.py:37-60`). The glossary page's JS additionally carries its own hardcoded fallback FV→WAR table (`assets/glossary.js:1102`) on the OLD primer scale, used only when the snapshot script fails to load.
5. Multiple historical calibration vintages (v3/v4/v5/v6) are preserved in `calibration.fit_provenance`; only `isotonic-real-v6-evframe-2026-07-31` is live, and the per-artifact stamp + `test_calibration_vintage.py` exist precisely because mixed vintages once served simultaneously.
6. **The fitted file cannot be regenerated as committed.** `--fit` would revert the hand-amended sub-45 empirical anchors (see Step 2). Treat `data/value_framework_fitted.json` as a versioned artifact, not a derived cache.
7. **Two eFV pricing seams use different ETA conventions:** the resolved-matrix/consensus-column seam prices at a hardcoded `eta_years=1.0` (`efv_score.py:1296-1297`) while the live-board seam uses the row's resolved ETA (`:1815`); both share the `PROSPECT_ETA_FALLBACK_YEARS = 1.0` fallback with storage.

### Verification log

Every quantitative claim above was checked against the code on 2026-08-01. Corrections and material additions made to the draft:

1. **Line count**: `value_framework.py` is 4,152 lines, not 4,153 (`wc -l`).
2. **`point_estimate_surplus_usd` "non-production" claim corrected**: it has live callers — `fa_market.py:59` imports it and `fa_market.py:1176` (`qo_tax_usd`) uses it as the fallback pricing of forfeited QO picks when the fitted slot artifact is absent; `farm_grade_backtest.py:162` also calls it. The draft's "explicitly non-production" wording was wrong for this function (it remains correct for `career_war_value_mm`, `value_framework.py:540-555`).
3. **Empirical-anchors regeneration claim corrected**: the committed sub-45 knots (20/25/30/35/40) were hand-amended 2026-07-29 and are NOT reproducible by `--fit` — running `--fit` reverts them (documented in `empirical_anchors.anchors_provenance` inside `data/value_framework_fitted.json`; guarded by `test_value_framework::test_low_end_anchors_are_present_and_measured`). The draft said the anchors are "recomputed only during --fit", which is only true of the 45-80 knots. Also added `n_cohort: 3460`.
4. **"JS interpolates the emitted sv_curve" corrected**: no JS file references `sv_curve` (grep over `assets/` and the tree); the actual consumers are `assets/glossary.js:1102` (FV→WAR viz with a stale hardcoded fallback table `{40:1,...,80:7}`), `:1128` (`surplus_by_grade_mm` curve), and the `_gxSurplus` teaching widget (`:~1183+`) which recomputes a simplified surplus from snapshot constants with hardcoded fallbacks (11.74 / 0.76 / `[0.4,0.6,0.8]`). The config comment (`yaml:357-362`) states the sv_curve intent but nothing interpolates it today.
5. **timeseries MC draw counts added**: `storage.py:6288-6299` overrides draws for the bake — `_SURPLUS_DIST_DRAWS = 4000`, `_SURPLUS_CI_DRAWS = 2000` (the comment documents these were previously undefined NameErrors silently swallowed). The 10,000 config default applies to the eFV seam and direct calls only.
6. **Additional compute sites added**: `efv_ungraded.py:681` (provisional ungraded rows) and `efv_score.py:2194` (backgrade path) also price via `expected_surplus_usd`/`sv_distribution`; the resolved-matrix seam (`efv_score.py:1296-1297`) prices at hardcoded `eta_years=1.0` (new discrepancy #7). `_cal_mm` helper located at `efv_score.py:891`.
7. **Pipeline step précis corrected**: `run_monthly.py:742` is inside `rebuild_only()`, reached nightly via chained-daily step d9 (`run_monthly.py:1396-1398`); d9b proj_export re-bake at `run_monthly.py:1408-1412`; monthly 6b skip at `:3345-3351`. Trade export block is `run_monthly.py:826-845` (draft said 826-848).
8. **Storage line refs corrected**: stale v32-era comment is `storage.py:6250-6257` and says v32.0 (draft: 6255-6259/"v32.1" — the glossary entries do say v32.1); import block `6258-6287`; `_build_surplus_payload` spans `6321-6418` and also emits `star_odds_model`, `opt_pct`, `valuation_set`, `fv_used` (added).
9. **Function-range refinements**: `tiered_war_value_usd` 457-482 vs `_tiered_war_value` 485-508 (draft merged them); `calibration_version` 1557-1572 vs `calibration_stamp` 1575-1580; `emit_snapshots` 4062-4075; integration tests `test_value_framework_integration.py:37-60`; `fa_backtest` series write 638-652; clemens params block `:75-107`; fa_market constants `fa_market.py:58-59, 219-224`.
10. **glossary.json claims verified and sharpened**: all five entries (`tvi`, `value_framework`, `dpw_tier`, `fv_to_war_table`, `bust_prob`) found in the `entries` list and quoted; `dpw_tier` is partially current (tier rates match) but its load-time-rescale claim only holds under prospx_current — noted.
11. **fa_dpw_series consumers added**: `fa_class.py:239`, `fa_export.py:649`, `proj_export.py:239` read the series directly, alongside `value_framework.py:195`. Also added the `persist_dpw` write-hazard flag (`fa_backtest.py:461-468`) and registry BUG-2 (FA lane no longer borrows `dollars_per_war_inflation`, which is 0.0 in production).
12. **Verified unchanged (spot-checked against code, no edit needed)**: `_BASE_IDENTITY_SET`/`_DEFAULT_VALUATION_SET` (`:295-297`); ordered-logit cutpoints/slopes byte-exact vs `data/value_framework_fitted.json`; empirical anchor values byte-exact; kernel constants and tier centers (0.5/1.5/2.5); clemens_2026 overrides (7yr control, prior_season arb `[0.15,0.35,0.50,0.75]`, net-7% via `valuation_sets.py:285-298`, `disable_fa_implied` translation `:275-279`); checksum guard (`valuation_sets.py:84-95`, tolerances 0.05/0.001); arb clamp 0.25→0.15; super-two 0.78/0.22 blend; reliever 65/200 + 1.5 cap; aging 27/25/0.04/0.07/0.25; low-tier anchor $2.0M ×0.90 decay 0.16 cutover 40 bridge 45; C6 floor at `:1505`; calibration knots and version string byte-exact vs `yaml:538-543`; v6 provenance (PAVA on bin means, n=2236 2017-2019, ys[0]=0.67, slope 1.2818 to 400 knot); `calibration_zero_cross_mm` None-on-shipped-map; distribution seed formula, cv map, `output` supersession (10000 draws, p10-p90, cvar_25, λ=0); source-disagreement gates (min 2, cap 6.0, `fv_sd_to_cv` 0.12); `_round_timing` 0.5/0.5/0.25; PCHIP + all-bust fallbacks; debuted-mode mechanics including `arb_basis` honoring in `_remaining_path_surplus_usd` and Spotrac salary override in `realized_consumed_seasons`; `dollars_per_war_by_winter` gates (Σwar>20, n≥25, NPV numerator); `apply_platform_surplus` re-pointing; proj_export `surNpv` construction both populations; `_eta_years_from` + `PROSPECT_ETA_FALLBACK_YEARS = 1.0`; vintage test artifact map; registry `prospect_surplus` champion string and eval artifact; `build_site.py:3197` include; `trademachine.js` render-only header; `prospx_current.yaml:112`; existence of `tools/fit_surplus_calibration.py`, `tools/surplus_sensitivity.py`, `docs/efv-2026-07-30/SURPLUS_EV_OBJECTIVE.md`, `docs/efv-2026-07-31/SURPLUS_PRICING_KEY_GATE.md`, `docs/METHODOLOGY.md`.


---

# swing_plus

## Name in code & where computed

**In-code names (casing matters):**
- `swing_plus` — the served value: JSON key in `data/swing_plus.json` (`players.{mlbam}.swing_plus` and `players.{mlbam}.seasons.{year}.swing_plus`), and the DataFrame column produced by the scorer (`vendor_swing_plus.py:162,164`).
- `swing_plus_raw` — the pre-shrink score, internal only (`vendor_swing_plus.py:155`).
- `swingPlus` / `swingPlusSeasons` / `swingN` — camelCase renames in the player-detail export (`mlb_player_export.py:600-608`).
- `swing_trend` — display-only per-player delta annotation (`fantasy_export.py:367`), rendered by `assets/fantasy.js:460-464`.
- `data/swing_delta.json` — display-only year-over-year delta sidecar (`build_site.py:3967-4025`).
- Registry id: `swing_plus_external` (`data/model_registry.json:480`); glossary id: `swing_plus` (`data/glossary.json`). The registry↔glossary mapping is itself pinned by `test_methodology_freshness.py:62`.

**Where computed (production chain):**
1. `prospect-tracker/vendor_swing_plus.py` — class `SwingPlusModel` (`vendor_swing_plus.py:48`): `filter_swings` (69-89), `build_profiles` (94-123), `score_profiles` (128-166), `score_pitch_level` (171-180). This is the ONLY place the Swing+ math executes. It is a **vendored, byte-identical copy of Will Cahoon's inference module** (verified: `diff` against the author's working copy at `BaseballR/swing-plus/swing_plus.py` returns no differences; copyright header `vendor_swing_plus.py:1-4`).
2. `prospect-tracker/swing_plus_ingest.py` — orchestrator: builds the player pool (`default_pool`, 117-159), fetches per-(player, season) Savant pitch CSVs (`fetch_player_season`, 93-114), calls the vendored scorer pooled (`score_pool`, 162-248: `model.score_pitch_level(pitches, group_by=[])` at line 209) and per-season (`group_by=["season"]`, line 232), and writes `data/swing_plus.json` (`run`, 251-272). (`build_profiles`'s own default `group_by` is `["half"]` if a `half` column is present, else `[]` — production always passes an explicit list, so the default never fires.)
3. **Production trigger:** `run_monthly.py:3353-3363`, step `"6b2. Swing+ scoring (swing_plus.json)"`, best-effort (exceptions logged, run continues). There is no daily re-score — `run_daily` is a function inside `run_monthly.py` (def at line 860) and swing ingest is invoked nowhere in its step chain; a 6-day cache TTL on the current season (`swing_plus_ingest.py:63`) bounds staleness between monthly runs. Can also be run by hand: `python swing_plus_ingest.py [--limit N]`.
4. Downstream production joins (no recompute, values copied verbatim):
   - `build_site.py:3967-4025` `build_swing_delta_payload` → `data/swing_delta.json` (written in the derived-payloads loop at `build_site.py:4146-4153`; a `None` payload skips the write and leaves the existing file untouched).
   - `mlb_player_export.py:469-474, 600-608` → `swingPlus`/`swingN`/`swingPlusSeasons` on `/projections/` player pages. Attach gate: `if sw and (not p["isPit"] or p.get("twoWay"))` (line 601) — hitters and two-way players only.
   - `fantasy_export.py:350-368` `_attach_swing_trend` (called at 556, so the daily `refresh_live` path re-bakes it too) → `swing_trend` chip.
   - Frontend display only — **no JS recomputes the score; only rounding, colors, and deltas**:
     - `prospx/index.html:30933-30952` — the sidecar loader: fetches `/data/swing_plus.json` once at boot; `getSwingPlus(p)` resolves `p.mlbam_id || (p.career_war || {}).mlbam_id` and returns `row.swing_plus` verbatim (comment block 30874-30875).
     - `prospx/index.html:12133-12141` — compact-row Statcast chip strip: `Math.round`, hitters only (`!isP`), color ≥105 green / ≤95 red (12138-12139).
     - `prospx/index.html:16460-16463` — signals list on the scout view (Math.round, same breakpoints).
     - `prospx/index.html:18117-18123` — a **sortable "+"-leaderboard column** `swing_plus` (label "Swing+", `hi: true`, `minAB: 0`, hitter side, `Math.round` fmt, getter = `getSwingPlus`). The prospx board can be user-sorted/ranked by Swing+ — still the served value verbatim, never a model input.
     - `prospx/index.html:34304-34310` — hero/share card tile (Math.round, same breakpoints).
     - `prospx/index.html:36824-36834` — at-a-glance header-ribbon stat pill (hitters, Math.round).
     - `prospx/index.html:43274-43281` — "Bat-tracking model" tile group on the advanced tab (hitters, Math.round).
     - `prospx/index.html:46200-46211` — compare-style tile with an `n_swings` sub-label read straight off the `_SWING_PLUS` row.
     - `assets/projections.js:1712` (Swing+ tile, shows the stored 1-decimal value with `n=` sub-label, ≥105/≤95 colors), `1717-1726` (per-season trend tile: seasons `Math.round`ed per slice at 1720, `*` marks `low_n`, trend color at ±5, line 1723), `1881` (`shareMlbCard` passes `Math.round(p.swingPlus)` to the hub card).
     - `assets/projections.js:116, 1344-1355` (lazy `ensureSwingDelta` fetch of `/data/swing_delta.json`) and `1357-1392` `batSpeedChip` — the year-over-year "Bat speed" chip rendered into the `/projections/` player card at line 1757: shows `d` at 1 decimal, `prior → latest`, "partial tracking" when `lowN`, and a "bottom decile" alert flag + `is-alert` class when `d <= dist.p10`; two explicit no-data states (no prior season vs not scored at all, using `nLatestOnly`).
     - `assets/fantasy.js:460-464` — renders the server-baked `swing_trend` chip (`ff-mech-up`/`ff-mech-down`, delta displayed at 0 decimals via `num(mt.delta, 0)`); the comment at 457-459 restates that the buy/sell sort is luck-only.
     - `assets/eephus-hub.js:294-301` — the `player-projection` share-card ("GFX") template pushes a Swing+ tile (line 299) from the value `projections.js:1881` passed in. "GFX hero rail" is the registry/team-page name for this surface (`data/model_registry.json:481`, `content/team.json:22`).

**Git-tracked state (matters for a backend port):** `vendor_swing_plus.py`, `model/swing_plus/swing_plus_model_v1.joblib`, `data/swing_plus.json`, and `data/swing_delta.json` are all committed (`git ls-files` verified). `.gitignore:41-44` explicitly documents that `swing_plus.json` is deliberately NOT untracked because it is a monthly-only producer (a daily pull would otherwise leave it absent for up to a month).

**Not production:** `tools/bat_tracking_lab.py` is a separate, pre-registered experimental lane on Savant bat-tracking *leaderboard aggregates* (registry id `bat_tracking_hitters`, verdict `deprecated`, surface "model-dev artifact (rendered nowhere) - loss ledger"; its header explicitly states the terms "appear only in the vendored swing_plus ingest, which is untouched here", `tools/bat_tracking_lab.py:6-7`). The author's full training project sits as a sibling directory `BaseballR/swing-plus/` (outside `prospect-tracker/`); it is Will Cahoon's repo (training pipeline `swing-plus/pipeline/20_build_deployable.py`), not part of the site pipeline. Meta/audit surfaces that mention swing_plus but compute nothing: `tools/_arch_axes_census.py:102`, `tools/gen_audit_docs.py:311`, `data/_am_crossmodel_map.json:327`, `MODEL_REGISTRY.md:38`, `DATA_SOURCES.md`, `SITE_MAP.md`, `docs/audit/current_state_map.md:34`, and team-page prose `content/team.json:22`.

**Stale lead refuted:** `proj_ml.py` does NOT use Swing+ as a feature. Its only mention is a comment about a shared warning-suppression pattern (`proj_ml.py:64`; the filter at 65-66 suppresses the same "X does not have valid feature names" UserWarning message for proj_ml's own models). Nothing uses Swing+ as a model/scoring input anywhere in the platform (asserted in comments at `fantasy_export.py:354-356`, `mlb_player_export.py:604-606`, `swing_plus_ingest.py:224-226`, registry notes). The one nuance: the prospx "+" leaderboard column (`prospx/index.html:18120-18123`) lets a USER sort/rank the displayed board by Swing+ — a display sort of the served value, not a model consuming it.

## Formula or fitted model?

**Hybrid: a fitted model (external, vendored) wrapped in exact deterministic scoring code that runs locally.** The two fitted sub-models were trained by Will Cahoon; this repo runs inference only (`swing_plus_ingest.py:6-8`, registry row `swing_plus_external`). The inference math is fully specified below; the *fit itself* (ridge coefficients, calibration constants) is not reproducible from prospect-tracker — the backend team must carry the `.joblib` artifact (or a port of its coefficients).

**Model type + library:** two scikit-learn `Pipeline(StandardScaler → PolynomialFeatures(degree=2, include_bias=False) → RidgeCV(alphas=(0.1, 1.0, 10.0, 100.0)))` regressors, step names `('scale', 'poly', 'ridge')` (introspected from the artifact; both selected `alpha_=100.0`, 9 inputs → 54 polynomial features, intercepts `pipe_bip`=0.3591397144286994, `pipe_pow`=0.05653652655250356). `pipe_bip` predicts P(ball-in-play per competitive swing); `pipe_pow` predicts run value given BIP. Training targets (per artifact `notes`): "park+pitch-quality-adjusted P(BIP) and RV|BIP", trained on Statcast bat tracking 2023 H2 – 2025 H2 (`trained_through: "2025_H2"`; ~1700 player-half profiles per the author's project notes, `swing-plus/CLAUDE.md`). Note the training window starts 2023 H2 while the local ingest fetches 2024+ only (`FIRST_TRACKING_SEASON = 2024`) — the public-boundary statement everywhere on-site is "MLB bat tracking 2024+".

**Artifact:** `prospect-tracker/model/swing_plus/swing_plus_model_v1.joblib` (joblib pickle, 4,070 bytes; byte-identical to the author's copy at `BaseballR/swing-plus/swing_plus_model_v1.joblib`, verified with `cmp`). Keys (all verified by loading it): `version` ("1.0.0"), `model_type` ("swing_plus_phase_1"), `features`, `tracking_cols`, `min_swings` (180), `reliability_k` (360), `rv_nonbip_constant` (-0.0659), `train_xrv_mean` (-0.019957514273182344), `train_xrv_std` (0.007941284889764921), `pipe_bip`, `pipe_pow`, `real_swing_filter` (dict of 8 thresholds), `notes`, `trained_through`. **Pinning:** registry row `swing_plus_external` in `data/model_registry.json:479-490` (verdict deliberately `unvalidated`, `eval_artifact: null` — external model, "validated in the author's repo; not re-derived here"; `last_checked: 2026-07-23`); no hash/fingerprint beyond the `version` key. **Serving caveat:** the artifact was pickled under sklearn 1.8.0 and is scored locally under 1.7.2 (verified live: `InconsistentVersionWarning` "from version 1.8.0 when using version 1.7.2" fires for StandardScaler/PolynomialFeatures/RidgeCV/Pipeline on both pipes; suppressed at `swing_plus_ingest.py:166-167`, `207-208`, and `230-231`; registry note says "pin on next env refresh"). To port without joblib, extract each pipeline's `StandardScaler` mean/scale and `RidgeCV` `coef_` (54 floats each) + `intercept_`.

**The 9 model features, in fitted order** (the artifact's `features` list — the profile means of all 7 tracking columns plus exactly TWO of the stds; the other 5 `_std` columns are computed by `build_profiles` but never enter the model):
```python
["bat_speed_mean", "swing_length_mean", "attack_angle_mean",
 "attack_direction_mean", "swing_path_tilt_mean",
 "intercept_ball_minus_batter_pos_x_inches_mean",
 "intercept_ball_minus_batter_pos_y_inches_mean",
 "bat_speed_std", "attack_angle_std"]
```

**Exact inference pipeline** (all from `vendor_swing_plus.py`; `score_pitch_level` = filter → profile → score → sort by `swing_plus` descending, lines 171-180):

Step 1 — competitive-swing filter (lines 69-89). Keep pitch rows where `bat_speed` and `swing_length` are non-null AND:
```python
(bat_speed >= 40) & (bat_speed <= 90) &
(swing_length >= 4) & (swing_length <= 12) &
(abs(attack_angle) <= 45) &
(swing_path_tilt >= 10) & (swing_path_tilt <= 50) &
(abs(attack_direction) <= 60)
```
(thresholds live in the artifact's `real_swing_filter` — keys `bat_speed_min/max`, `swing_length_min/max`, `attack_angle_abs_max`, `swing_path_tilt_min/max`, `attack_direction_abs_max` — not code literals).

Step 2 — profiles (lines 94-123). Group by `batter` (+ optional group cols; production pooled pass uses `group_by=[]`, per-season pass `group_by=["season"]`). For each of the 7 `tracking_cols` (`bat_speed`, `swing_length`, `attack_angle`, `attack_direction`, `swing_path_tilt`, `intercept_ball_minus_batter_pos_x_inches`, `intercept_ball_minus_batter_pos_y_inches`) compute pandas `mean` and `std` → columns `{col}_mean`, `{col}_std`. Also `n_swings` = group size, `bip = (type == "X")`, `n_bip`, `bip_rate_obs = n_bip / n_swings`. Drop groups with `n_swings < min_swings` (line 122).

Step 3 — score (lines 128-166). With `X = df[self.features].values` (the 9 columns above, fitted order preserved by the column selection); rows with any NaN feature dropped (line 145):
```python
p_bip_pred   = clip(pipe_bip.predict(X), 0, 1)
rv_bip_pred  = pipe_pow.predict(X)
xrv_per_swing = p_bip_pred * rv_bip_pred + (1 - p_bip_pred) * rv_nonbip      # rv_nonbip = -0.0659
swing_plus_raw = 100 + (xrv_per_swing - train_xrv_mean) / train_xrv_std * 10
w = n_swings / (n_swings + reliability_k)                                     # k = 360
swing_plus = w * swing_plus_raw + (1 - w) * 100
```
(A `reliability_weight=False` code path exists at lines 163-164 that skips the shrink; production never uses it.)

Step 4 — ingest post-processing (`swing_plus_ingest.py`): pooled score rounded to 1 decimal (line 214). Per-season slices: same model instance with `min_swings` temporarily forced to 2 in a try/finally (lines 227-234; "n=1 lacks a std anyway"), rounded to 1 decimal, `low_n: true` when the season's `n_swings < 180` (lines 241-242, compared against the saved original `min_swings`); slices attach only to batters that earned a pooled score (lines 237-238) and the per-player `seasons` dict is key-sorted (lines 244-246). Output payload (lines 256-267) carries `generated_at`, `model`, `data_boundary`, `min_swings`, `reliability_k`, `n_scored`, `players` (NOTE: `score_pool`'s internal `n_player_seasons` count is NOT in the served payload). Live payload sanity (2026-08-01 build): `n_scored: 270`; e.g. `players["701762"] = {"swing_plus": 134.1, "n_swings": 1478, "name": "Nick Kurtz", "seasons": {"2025": {...}, "2026": {...}}}`.

**Derived sidecar** `data/swing_delta.json` (`build_site.py:3967-4025`): `latest`/`prior` = two most recent seasons present anywhere in the per-season slices (returns `None` — file untouched — if fewer than 2 distinct seasons exist, lines 3979-3980); per player `d = round(latest.swing_plus - prior.swing_plus, 1)` only when BOTH seasons scored (latest-only players are counted in `nLatestOnly`, lines 3987-3991); `lowN` if either side `n_swings < 180` (lines 4000-4001); distribution block p10/p25/p50/p75/p90/mean via linear-interpolated percentiles over the delta population (lines 4005-4010, percentiles rounded to 2 decimals); returns `None` when fewer than 30 deltas (line 4003). Payload fields: `generated_at`, `model`, `priorSeason`, `latestSeason`, `minSwings`, `n`, `nLatestOnly`, `nScored`, `dist`, `players` (lines 4012-4025). Live (2026-08-01): `priorSeason: 2025, latestSeason: 2026, n: 218, nLatestOnly: 31, dist.p10: -3.96`.

## Inputs

Per-pitch Statcast bat-tracking columns, fetched raw from **Baseball Savant `statcast_search` CSV API** (URL template `swing_plus_ingest.py:67-76`: regular season only `hfGT=R%7C`, `player_type=batter`, `type=details`, full param skeleton because sparse param sets silently fall back to defaults, one request per `batters_lookup[]={mlbam}` × season, seasons `range(2024, current_year + 1)` at line 175; cached under `.cache/swing_pitches/{mlbam}_{season}.csv`, line 97). Columns read (`_NEED_COLS`, `swing_plus_ingest.py:78-81`) — Statcast names verbatim, no renames (the author's repo conventions explicitly forbid renaming):

| Column | Meaning | Computed? |
|---|---|---|
| `batter` | MLBAM id (join key everywhere downstream) | raw |
| `bat_speed` | mph | raw Statcast bat tracking |
| `swing_length` | feet | raw |
| `attack_angle`, `attack_direction`, `swing_path_tilt` | degrees | raw |
| `intercept_ball_minus_batter_pos_x_inches`, `..._y_inches` | intercept point, inches | raw |
| `type` | 'X' in play / 'S' strike / 'B' ball | raw |
| `season` | added by the ingest per fetched file (`swing_plus_ingest.py:193`) | local label |

**Pool membership inputs** (who gets fetched, not what is scored; `swing_plus_ingest.py:117-159`): `data/debuts.json` (debut year ≥ 2024, position not in P/SP/RP/LHP/RHP; TWP kept), `data/fa_class.json` members (name+pos only) resolved to MLBAM via `fa_ident.resolve(name, range(season-4, season))` over the war_daily identity index (pitcher-prefixed positions skipped), and `data/mlb_projections.json` `vets` with `twoWay` (the Ohtani case — debut pre-2024 + pitcher-coded position would otherwise exclude him). The last one is an artifact of the projections module, but it gates *membership only* — no value flows from it into the score.

**Dependencies on other stats in this documentation set: none.** Swing+ consumes no efv/xfv/rem+/sem+/hem+/stuff+/pal/wag/value_framework/collegesavant+/draft_stock+ quantity, and none of them consume Swing+ as a model input (display co-location only).

## Constants, baselines & normalization

**Raw→plus scaling:** `swing_plus_raw = 100 + 10 * (xrv_per_swing − train_xrv_mean) / train_xrv_std` — i.e. 100 = training-population mean expected run value per competitive swing, 10 points = 1 training SD. **The baseline is STATIC**: `train_xrv_mean = -0.019957514273182344` and `train_xrv_std = 0.007941284889764921` are frozen in the joblib artifact, computed once over the author's training profiles (MLB player-halves, 2023 H2 – 2025 H2; see the author's builder `swing-plus/pipeline/20_build_deployable.py:94-100` — `xrv = clip(pipe_bip.predict(X),0,1) * pipe_pow.predict(X) + (1-p) * RV_NONBIP_CONSTANT`, then `xrv.mean()` / `xrv.std()` over the training X). Nothing is re-baselined per run/season locally — new seasons are scored against the frozen 2023-25 anchor, which is what keeps scores comparable across years.

All named constants:

| Constant | Value | Lives in |
|---|---|---|
| `train_xrv_mean` / `train_xrv_std` | -0.019957514273182344 / 0.007941284889764921 | joblib artifact |
| `rv_nonbip_constant` | -0.0659 (mean run value of non-BIP competitive swings — whiffs+fouls — from full 5-half training data, `20_build_deployable.py:90-92`) | joblib artifact |
| `min_swings` | 180 | joblib artifact |
| `reliability_k` | 360 (shrink weight `n/(n+360)` toward 100) | joblib artifact |
| `real_swing_filter` | bat_speed [40,90], swing_length [4,12], \|attack_angle\|≤45, swing_path_tilt [10,50], \|attack_direction\|≤60 | joblib artifact |
| ridge `alpha_` | 100.0 (both pipelines, selected by RidgeCV from (0.1, 1.0, 10.0, 100.0)) | joblib artifact |
| `FIRST_TRACKING_SEASON` | 2024 | code literal `swing_plus_ingest.py:61` |
| `THROTTLE_S` / `CURRENT_TTL_S` | 1.5 s / 6 days (`6 * 86400`) | code literals `swing_plus_ingest.py:62-63` |
| season-slice `min_swings` override | 2 | code literal `swing_plus_ingest.py:229` |
| `_SWING_MIN_N` | 180 (low-N convention echoed for the delta sidecar) | code literal `build_site.py:3964` |
| fantasy trend threshold | \|delta\| ≥ 5 | code literal `fantasy_export.py:366` |
| delta-sidecar minimum population | 30 deltas | code literal `build_site.py:4003` |
| delta-sidecar minimum seasons | 2 distinct seasons | code literal `build_site.py:3979` |
| display color breakpoints | ≥105 green / ≤95 red | frontend literals `prospx/index.html:12138, 16463, 34308, 36831, 43279, 46206`, `assets/projections.js:1712` |
| trend-tile color breakpoints | season delta ≥ +5 green / ≤ −5 red | `assets/projections.js:1723` |
| test sanity bounds | served value in [40, 180] | `test_mlb_player_pages.py:77` |

Note `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md` does not cover swing_plus (verified: no mention; it is an external model, not an in-house Arkmetric), even though the artifact happens to follow the same 100±10 convention.

## Edge cases & guardrails

- **Data boundary (the big one):** Statcast bat tracking exists only at MLB, 2024+. No public MiLB tracking exists at any season (the ingest header says "verified against the Savant minors aggregates 2023-2026"), so pre-debut prospects can NEVER score; the pill appears only after debut (`swing_plus_ingest.py:13-19`, stated in the JSON payload `data_boundary`, the registry notes, and the glossary).
- **Minimum sample:** pooled profiles with `n_swings < 180` are EXCLUDED entirely (`vendor_swing_plus.py:122`). Kept scores shrink toward 100 with weight `n/(n+360)` — e.g. 180 swings ⇒ only 1/3 weight on the raw score.
- **Per-season slices:** floor lowered to 2 (never 1 — std undefined) so partial-coverage 2024 doesn't blank trend lines; thin seasons flagged `low_n` instead of dropped, and the shrink already pulls them hard toward 100. Slices exist only for players with a pooled score (`swing_plus_ingest.py:237-238`). Display-only by contract (comment at 218-226).
- **Measurement garbage:** the competitive-swing filter drops check swings/tips/tracking failures (30-50% of rows with `bat_speed` populated, per the author's project notes `swing-plus/CLAUDE.md`); `p_bip_pred` clipped to [0,1] (`vendor_swing_plus.py:148`); NaN-feature profile rows dropped (line 145).
- **Fetch robustness:** 1.5 s throttle (`_throttle`, 85-90); closed-season CSVs cached immutably, current season on a 6-day TTL (98-102); fetch failure falls back to any existing cached file (`swing_plus_ingest.py:108-113`); per-file read failures and files with zero tracked swings skipped (186-192). Pool sub-sources are each best-effort try/except (117-159).
- **Pipeline gating:** step 6b2 is fully best-effort — a total failure leaves the previous `data/swing_plus.json` in place (`run_monthly.py:3358-3363`); `run(persist=True)` only overwrites the file when `n_scored > 0` (`swing_plus_ingest.py:268`).
- **Delta sidecar guards:** both seasons required, else the player is skipped (latest-only players counted in `nLatestOnly`); whole file skipped under 2 distinct seasons or under 30 deltas (build_site returns `None` → the writer loop leaves the previous file as-is, `build_site.py:4143-4153`); the "alert cut" is the measured p10 of the population, never hand-set (`build_site.py:3957-3963`, applied client-side at `assets/projections.js:1377-1391` with a "bottom decile" flag and a tooltip that explicitly disclaims predictive value).
- **Frontend resilience:** every fetch has a catch that installs an empty `{players:{}}` (prospx 30944, projections.js 1354), so a missing sidecar renders empty states, never errors; prospx repaints via `scheduleRender()` when the async sidecar lands after first paint (30939-30942).
- **Tests:** `test_mlb_player_pages.py:72-93` pins sanity bounds (every served `swing_plus` in [40, 180], `n_swings > 0`, the boundary string in `data_boundary`), the honest `unvalidated` + `eval_artifact: null` registry posture with "MiLB" stated in the notes, and the prospx wiring (`getSwingPlus`, `swing_plus.json`, `chip("Swing+"`). `test_methodology_freshness.py:62` pins the registry-id→glossary-id mapping.

## Dependencies & discrepancies

**Consumes:** raw Savant bat tracking only. Pool membership (not values) touches `debuts.json`, `fa_class.json` (+ `fa_ident`/war_daily identity), `mlb_projections.json`.

**Feeds:** display surfaces only — PROSPX chips/pills/tiles + a user-sortable leaderboard column (seven distinct render sites, enumerated above), `/projections/` player-page tile + per-season trend tile + year-over-year bat-speed chip (via `swing_delta.json`), fantasy buy/sell `swing_trend` chip, share-card GFX tile ("GFX hero rail"). It is a model input to NOTHING: no model, projection, or valuation reads it, and no server-side ranking/section-membership sorts on it (the `bat_tracking_hitters` lab that tested bat-tracking signal in projections used Savant leaderboard aggregates, not Swing+, and shipped nothing). One registered future exception: the registry notes reserve a "NOV-A 2026-11-15 re-gate arm" that MAY consume the per-season variant per its registration — as of now nothing does.

**Discrepancies / flags:**
1. **Provenance:** the "external vendor" is Will Cahoon's `swing-plus` project, which physically sits as a sibling directory in this workspace (`BaseballR/swing-plus/`); `vendor_swing_plus.py` and the joblib are byte-identical copies of it (both re-verified by diff/cmp). Training code (`swing-plus/pipeline/20_build_deployable.py`) exists there but is NOT part of the site pipeline, and the training *data* (profiles parquet) is not in prospect-tracker — the fit is not reproducible from this repo; the artifact is the source of truth.
2. **Glossary metadata conflict** (`data/glossary.json` id `swing_plus`): `definition`/`methodology` correctly credit "Built by Will Cahoon; eephus.io runs the model's scoring" and agree with the code (competitive-swing filter → per-hitter aggregation → run-value pipelines → reliability shrink toward 100 below ~180 swings, MLB-2024+ boundary; `formula` deliberately null). But the entry's `shelf` is `"ark"` and `origin` says "Arkmetric, created by Noah J. Dengler, original to eephus.io.", contradicting its own definition, the registry, and the code headers.
3. **Stale docstrings:** `swing_plus_ingest.py:31` says scoring uses `score_to_leaderboard`, and the vendored module's own usage docstring (`vendor_swing_plus.py:18`) advertises `model.score_to_leaderboard(pitch_df, group_by="season")` — no such method exists in the class; the actual entry point is `score_pitch_level` (`swing_plus_ingest.py:209,232`).
4. **Three delta implementations**, all display-only and all "latest minus prior" but with different framing: `build_site.build_swing_delta_payload` (population-wide two most recent seasons, 1-decimal, p10 alert cut), `fantasy_export._attach_swing_trend` (per-player last two scored seasons, annotates only |Δ|≥5, rendered at 0 decimals by `fantasy.js`), and `assets/projections.js:1721` (client-side trend-tile color from the player's own last two slices, unrounded delta vs ±5). No conflict in the served pooled score itself.
5. **Rounding:** stored values are 1-decimal; PROSPX (all seven surfaces), the trend-tile season segments, and the GFX payload display `Math.round` (round-to-nearest — the documented "+"-stat exception to the grades-round-UP rule), while the projections Swing+ tile and the bat-speed chip show 1-decimal values.
6. **Environment pin:** artifact pickled under sklearn 1.8.0, scored under 1.7.2 in production (InconsistentVersionWarning verified live and suppressed at three sites in `swing_plus_ingest.py`; registry flags "pin on next env refresh"). A backend port should match sklearn ≥1.8 or serve extracted coefficients to avoid unpickle drift.
7. **Registry surface row is incomplete:** `model_registry.json:481` lists "PROSPX debuted-prospect cards + GFX hero rail + /projections/ player pages" but omits the fantasy `swing_trend` chip and the prospx leaderboard column (the notes field does mention the fantasy chip).

### Verification log

- Verified byte-identical vendoring: `diff prospect-tracker/vendor_swing_plus.py swing-plus/swing_plus.py` clean; `cmp` of the joblibs clean (author's copy is at `swing-plus/swing_plus_model_v1.joblib`, repo root, not a `model/` subdir — clarified).
- Verified every artifact constant by loading the joblib: version 1.0.0, model_type swing_plus_phase_1, min_swings 180, reliability_k 360, rv_nonbip -0.0659, train_xrv_mean/std exact to all printed digits, filter thresholds, alphas (0.1, 1.0, 10.0, 100.0), alpha_=100.0 both pipes, 9→54 features, intercepts 0.3591397144286994 / 0.05653652655250356, size 4,070 bytes; captured the live InconsistentVersionWarning (1.8.0→1.7.2), local sklearn 1.7.2.
- **Added the explicit 9-feature list** — the draft said "features list below" but never listed it (artifact `features` key; only `bat_speed_std` + `attack_angle_std` of the 7 computed stds enter the model).
- **Expanded the prospx surface list from 2 sites to 8** (loader 30933-30952; chip 12133-12141; signals 16460-16463; sortable leaderboard column 18117-18123; card tile 34304-34310; header pill 36824-36834; advanced-tab tile group 43274-43281; compare tile 46200-46211) and **qualified the "nothing sorts on Swing+" claim**: the prospx "+" leaderboard column is a user-facing sort by Swing+ (minAB 0, hitters, Math.round), still not a model input.
- **Added missed consumers**: `assets/fantasy.js:460-464` (swing_trend chip render, 0-decimal display), `test_methodology_freshness.py:62` (registry↔glossary mapping test), meta/audit mentions (`tools/_arch_axes_census.py:102`, `tools/gen_audit_docs.py:311`, `data/_am_crossmodel_map.json:327`, `content/team.json:22`).
- **Corrected "bat-speed-delta board"** → it is a per-player `batSpeedChip` on the `/projections/` player card (`assets/projections.js:1357-1392`, rendered at 1757; lazy fetch at 116, 1344-1355), with a "bottom decile" alert when `d <= dist.p10` and two explicit no-data states — not a board.
- **Corrected the mlb_player_export citation** 471-472 → 469-474 (the try/except read spans 469-474) and added the attach gate `not p["isPit"] or p.get("twoWay")` at line 601.
- **Corrected the projections.js trend-tile range** 1712-1724 → 1712-1726, noted per-season segments are `Math.round`ed (1720) and the ±5 trend color literal (1723); corrected eephus-hub.js citation 290-299 → 294-301 (tile push at 299).
- **Added the second stale-docstring site**: `vendor_swing_plus.py:18` also advertises the nonexistent `score_to_leaderboard` (draft only cited `swing_plus_ingest.py:31`).
- **Added the third warning-suppression site** `swing_plus_ingest.py:230-231` (draft listed only 166-167, 207-208).
- **Added git-tracked state**: vendor module, joblib, swing_plus.json, swing_delta.json all committed; `.gitignore:41-44` documents swing_plus.json is deliberately tracked (monthly-only producer).
- **Added the <2-distinct-seasons guard** (`build_site.py:3979-3980`) and the delta-writer mechanism (`build_site.py:4143-4153`: None → skip, file left as-is); percentiles rounded to 2 decimals (4010).
- **Added registry details**: full notes verified (env-pin note, "DELIBERATELY kept UNVALIDATED", per-season W6 note) plus the **NOV-A 2026-11-15 re-gate arm** that may consume the per-season variant, and `last_checked: 2026-07-23`; flagged the registry surface field omitting the fantasy chip + leaderboard column (new discrepancy 7).
- **Attributed the ~1700 player-halves and 30-50%-garbage figures** to `swing-plus/CLAUDE.md` (the draft vaguely said "the author's notes"; the artifact `notes` key contains neither figure); noted the 2023-H2-training vs 2024+-public-boundary nuance.
- Verified run_monthly step 6b2 (3353-3363, label at 3357, try/except 3358-3363), the no-daily-re-score claim (`run_daily` def at run_monthly.py:860; only call site of the ingest is 3359-3360), `run(persist)` gate at 268, seasons range at 175, cache path at 97, TTL/throttle literals 61-63, `_NEED_COLS` 78-81, season label 193, pooled round 214, season floor 229, low_n 241-242, slice gate 237-238, payload keys 256-267 (and that `n_player_seasons` is NOT served), sorted seasons 244-246.
- Verified fantasy_export `_attach_swing_trend` 350-368 (threshold 366, call site 556), test_mlb_player_pages 72-93 (bounds [40,180] line 77), glossary entry (shelf `"ark"` / origin "Arkmetric, created by Noah J. Dengler, original to eephus.io." conflict exactly as drafted), ARKMETRIC_SCALE_CONVENTIONS.md non-coverage, proj_ml.py:64 comment-only mention, bat_tracking_lab header lines 6-7 + registry verdict `deprecated` (id `bat_tracking_hitters`, "rendered nowhere"), builder constants at `20_build_deployable.py:90-100`.
- Added live-payload spot checks (2026-08-01: n_scored 270; swing_delta 2025→2026, n=218, nLatestOnly=31, p10=-3.96) and the frontend empty-state/catch behavior.


---

# collegesavant_plus

## Name in code & where computed

**In-code names (casing matters):**
- `cs_plus` — the metric key used in every leaderboard/column/route definition (`collegesavant/app.js:539`, `collegesavant/pitcher_app.js:819`, `pitcher_app.js:1675`), the glossary id (`data/glossary.json:157`), and the model-registry `model_id` (`data/model_registry.json:2563`).
- `computeCSPlus(players)` / `computeCSPlus(pitchers)` — the two computing functions.
- `state.csPlus` — the result, a `Map` of player `slug -> rounded CS+ | null`.
- Display names: "CS+", "CS+ (CollegeSavant+)", "college tracked-skill index" (glossary term + aliases); the home widgets label it "CS+ (pro profile)" (`app.js:59`, `pitcher_app.js:54`).

**Computing sites (all of them):**

| Site | File:line | What |
|---|---|---|
| Hitter app | `prospect-tracker/collegesavant/app.js:120-152` (`computeCSPlus`), groups at `app.js:99-110`, `meanStd` at `app.js:112-118` | hitter CS+ |
| Hitter app invocation | `app.js:325` (inside `setActiveYear`, `app.js:319-326`; also reached via `render()` on a hash-year change, `app.js:398`) | recomputed per selected season |
| Pitcher app | `prospect-tracker/collegesavant/pitcher_app.js:430-462` (`computeCSPlus`), groups at `pitcher_app.js:409-420`, `meanStd` at `pitcher_app.js:422-428` | pitcher CS+ |
| Pitcher app invocation | `pitcher_app.js:586` (inside `setActiveYear`, `pitcher_app.js:579-591`) | recomputed per selected season |
| Team roll-up | `app.js:710-718` (`teamMetricValue`, cs_plus branch `711-713`) and `pitcher_app.js:1020-1028` (branch `1021-1023`) | "Team CS+" = arithmetic mean of members' CS+ |

**CS+ is computed CLIENT-SIDE ONLY, in the browser, at page load / year switch. Nothing server-side produces it.** The registry row states this explicitly: *"COMPUTING SITE: the two CollegeSavant client apps, computed in the browser from the embedded season payloads; nothing server-side produces CS+"* (`data/model_registry.json`, `cs_plus` row at lines 2562-2572, `model_id` at line 2563). `college_translation.py:22-23` confirms: *"Tier 3 - the pure tracked skills stay the CS+ index (college-relative), not a Single-A projection; computed in the frontend, not here."* A repo-wide grep for `cs_plus`/`csPlus`/`CSPlus` hits exactly 8 files: the two apps, `data/glossary.json`, `data/model_registry.json`, the generated `MODEL_REGISTRY.md` (summary row at line 183), `docs/audit/current_state_map.md`, and two tests (`test_collegesavant_smoke.py`, `test_methodology_freshness.py:432`) — no Python computes it, and no `assets/` JS or `*_export.py` touches it.

**Production-path note:** `run_monthly.py` / `build_site.py` never compute or export CS+. The only pipeline touchpoints in the module are (a) `run_monthly.py:719-725` (rebuild path calls `college_translation.build()` — the separate Single-A translation, not CS+) and (b) `run_monthly.py:1944-1952` (`college_stats.refresh_collegesavant_stats`, gated on `COLLEGESAVANT_MAX_TEAMS` — NCAA box scores into `prospects.db` for the translation join, not CS+). The input payloads the JS reads (`collegesavant/hitter_year_data.js`, `collegesavant/pitcher_data.js`) are **vendored static files committed to the repo**, deployed as-is. Commit lineage: `bc2d81f` "Add CollegeSavant app" → `68e0f67` folder reorg → `d9656bb` "CollegeSavant module" (the payload files enter here) → `92618b5` "year-split eager payloads" (also adds `test_collegesavant_payload_split.py`).

The hitter and pitcher implementations are duplicated code with **identical scaling math but different component lists** (intentional, per side). Both must be kept in sync by hand; `test_collegesavant_smoke.py:90-164` exercises both via V8/MiniRacer (render smoke + asserts the `cs-plus-pill` and the `data-sort="cs_plus"` column render, but no numeric value assertions).

## Formula or fitted model?

**Deterministic formula. No trained model, no fitted artifact.** It is a pool-anchored z-average on the house `100 + 10z` convention (Convention 3; the CS+ row of the cross-family table is `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:46`).

Exact algorithm (quoting `app.js`; `pitcher_app.js:430-462` is byte-equivalent except for the component list):

**Step 0 — pool selection.** The cohort is every row of the selected season in the embedded payload: `state.players = state.allPlayers.filter((player) => player.year === state.year)` (`app.js:323`; pitcher: `pitcher_app.js:583`). No PA/pitch-count filter is applied to the pool (the leaderboard Min PA / Min pitches inputs filter display rows only, after CS+ is computed).

**Step 1 — component families** (`app.js:99-110`, hitters):
```js
const CSPLUS_GROUPS = [
  { name: "contact quality", parts: [
    { key: "90th_percentile_exit_velocity", dir: 1 },
    { key: "barrel_pct", dir: 1 },
    { key: "hard_hit_pct", dir: 1 },
  ] },
  { name: "plate discipline", parts: [
    { key: "zone_contact_pct", dir: 1 },
    { key: "whiff_pct", dir: -1 },
    { key: "chase_pct", dir: -1 },
  ] },
];
```
Pitchers (`pitcher_app.js:409-420`):
```js
const CSPLUS_GROUPS = [
  { name: "stuff & whiffs", parts: [
    { key: "stuff_plus", dir: 1 },
    { key: "swinging_strike_pct", dir: 1 },
    { key: "chase_pct", dir: 1 },
  ] },
  { name: "contact suppression", parts: [
    { key: "barrel_pct", dir: -1 },
    { key: "hard_hit_pct", dir: -1 },
    { key: "xwoba_against", dir: -1 },
  ] },
];
```
Note `chase_pct` flips sign between sides (bad for hitters, good for pitchers) — intentional.

**Step 2 — per-component population mean/SD** over the year cohort (`app.js:112-118`):
```js
function meanStd(values) {
  const v = values.filter(Number.isFinite);
  if (!v.length) return [0, 1];
  const m = v.reduce((a, b) => a + b, 0) / v.length;
  const sd = Math.sqrt(v.reduce((a, b) => a + (b - m) * (b - m), 0) / v.length);
  return [m, sd || 1];
}
```
This is the **population** SD (divide by N, not N−1); a zero SD falls back to 1.

**Step 3 — z-score, family means, cross-family mean, rescale** (`app.js:120-152`):
```js
function computeCSPlus(players) {
  const stats = {};
  for (const group of CSPLUS_GROUPS) {
    for (const part of group.parts) {
      if (!stats[part.key]) stats[part.key] = meanStd(players.map((p) => p[part.key]));
    }
  }
  const out = new Map();
  for (const player of players) {
    const groupZ = [];
    for (const group of CSPLUS_GROUPS) {
      const zs = [];
      for (const part of group.parts) {
        const value = player[part.key];
        if (!Number.isFinite(value)) continue;
        const [m, sd] = stats[part.key];
        zs.push(part.dir * (value - m) / sd);
      }
      if (zs.length) groupZ.push(zs.reduce((a, b) => a + b, 0) / zs.length);
    }
    if (!groupZ.length) { out.set(player.slug, null); continue; }
    const avgZ = groupZ.reduce((a, b) => a + b, 0) / groupZ.length;
    out.set(player.slug, Math.round(100 + 10 * avgZ));
  }
  return out;
}
```
So: `CS+ = round(100 + 10 * mean(family means of dir-signed z-scores vs the per-year cohort))`, with missing components dropping out of their family and empty families dropping out of the outer mean. **Unclamped** (the 40-160 clamp was removed 2026-07-29 — comment at `app.js:142-148` / `pitcher_app.js:452-458`).

**Team CS+** (Team Tendencies tab) = plain mean of the members' already-computed CS+ values (`teamMetricValue`, `app.js:710-718` / `pitcher_app.js:1020-1028`), gated at 3+ tracked players per team — the gate itself is the `ps.length < TEAM_MIN_BATTERS` / `< TEAM_MIN_ARMS` skip inside `computeTeamTendencies` (`app.js:730`, `pitcher_app.js:1040`).

To reproduce server-side: load the season's payload rows, compute per-key population mean/SD over ALL rows of that season (finite values only), then apply the code above verbatim.

## Inputs

All inputs come from **vendored static JS payloads committed under `prospect-tracker/collegesavant/`** — external CollegeSavant college-TrackMan data (GFX caption credits "CollegeSavant by Joseph Gillis", `app.js:681`, `pitcher_app.js:998`). No ingest module in this repo produces or refreshes these numbers; they were committed as files (`git log`: `d9656bb` "CollegeSavant module", `92618b5` year-split).

**Hitter CS+ inputs** — from `collegesavant/hitter_year_data.js` (`window.HITTER_DATA`, one row per hitter-season), numerically coerced in `normalizePlayer` (`app.js:293-317`):
- `90th_percentile_exit_velocity` (mph, TrackMan batted-ball tracking)
- `barrel_pct`, `hard_hit_pct` (%, TrackMan batted-ball classification)
- `zone_contact_pct`, `whiff_pct`, `chase_pct` (%, TrackMan pitch/swing tracking)
- plus `year` (pool selector) and `hitter_name` → `slug` (key). Measured payload coverage: 2024 = 3,607 rows (all fields incl. `pa`, `team` — 3,607 occurrences each); 2025 = 184 rows (**no `pa`, no `team` field**; team resolved via `window.B1G_TEAMS` in `data.js`, `app.js:306-307`). All six CS+ component keys are present on **all 3,791 rows** (3,607 + 184), and the hitter payload contains **zero `null` values** — so on the hitter side the missing-component path is currently never exercised.
- **Coercion hazard (hitter side only):** `normalizePlayer` maps only the empty string to null: `player[metric.key] = raw === "" ? null : Number(raw)` (`app.js:297`). A literal JSON `null` would coerce via `Number(null) === 0` and enter the pool as a real zero. Latent today (no nulls in the payload), but a porting hazard — the pitcher side handles null explicitly (`pitcher_app.js:563`: `row[metric.key] === null || row[metric.key] === "" ? null : Number(...)`). A missing key yields `Number(undefined) = NaN`, which is non-finite and drops out on both sides.

Legacy fallback (hitter app only, `app.js:213-228`): if `window.HITTER_DATA` is absent, the app first uses the inline `window.B1G_CSV` string — a ~29.8KB Big-Ten-only 2025 CSV blob defined in `collegesavant/data.js` (loaded on both pages before the apps: `index.html:94`, `pitcher_index.html:96`) — and only if that global is also absent does it `fetch(CSV_PATH)` for `b1g_2025_hitter_xwoba_min30pa.csv` (`app.js:1`, `app.js:219-222`). **That CSV file does not exist anywhere in the repo or its git history**, so the fetch leg is dead code: it would 404 and paint the visible error state. All fallback rows are treated as `year: 2025` (`app.js:223`).

**Pitcher CS+ inputs** — from `collegesavant/pitcher_data.js` (`window.PITCHER_DATA`), coerced in `normalizePitcher` (`pitcher_app.js:560-577`):
- `stuff_plus` — **itself a computed stat, but computed EXTERNALLY**: the pitcher-level average of CollegeSavant Stuff+, an external college-TrackMan xRV model built by Will Cahoon (glossary `collegesavant_stuff_plus`, id at `data/glossary.json:6332`, origin at `:6350`; registry row `collegesavant_stuff`, `data/model_registry.json:2014-2027`). The repo vendors already-scored payloads and "does not fit or re-derive the model". **This is NOT the repo's `stuff_plus` stat family** (aStuff+/pStuff+/tjStuff+) — see Dependencies.
- `swinging_strike_pct`, `chase_pct` (%, TrackMan outcomes)
- `barrel_pct`, `hard_hit_pct` (%, contact allowed), `xwoba_against` (expected wOBA allowed)
- plus `year`, `pitcher_name`+`pitcher_id` → `slug` (`pitcher_app.js:567`). Measured coverage: 2024 = 4,485 rows (full outcome fields); 2025 = 199; **2026 = 842 rows are shape-only** — `swinging_strike_pct` / `chase_pct` / `k_pct` / `bb_pct` / `z_contact_pct` appear on exactly 4,684 rows (= 4,485 + 199; the 2026 rows carry none of them), while `stuff_plus`, `xwoba_against`, `barrel_pct`, `hard_hit_pct`, `pitch_count`, `team` appear on all 5,526 rows. So in 2026 the "stuff & whiffs" family collapses to `stuff_plus` alone (the documented "absent parts drop out" behavior, comment at `pitcher_app.js:404-405`), while the contact-suppression family stays fully populated. The display-side year gate agrees: `hasPitchByPitchOutcomes(year)` is hard-coded `year === 2024 || year === 2025` (`pitcher_app.js:1607-1609`).
- **Null inventory (pitcher payload, 45 `:null` values total):** `avg_ivb` 21 (not a CS+ input), `stuff_plus` 20, `chase_pct` 2, `k_pct` 1, `bb_pct` 1. `normalizePitcher` maps them to `null` → non-finite → the component drops out of its family. A 2026 pitcher whose `stuff_plus` is null would have an empty first family and get CS+ from contact suppression alone.

**Dependencies on the other documented stats:** none of `efv, xfv, rem_plus, sem_plus, hem_plus, pal, wag, value_framework, swing_plus, draft_stock_plus` are inputs. The only relative is the `stuff_plus` **name collision** (vendored external metric, different scale) — flagged below.

## Constants, baselines & normalization

**Baseline population:** the per-year college cohort = every row of the selected season in the shipped payload, side-specific (all tracked hitters, or all tracked pitchers). Same pool the page's percentile sliders use (`computePercentiles`, `app.js:336-365`). 100 = that season's college pool mean; +10 = one population SD better.

**Recomputed:** every page load and every year toggle, in the browser (`setActiveYear`, `app.js:319-326` / `pitcher_app.js:579-591`). The baseline is never persisted, fitted, or versioned — it changes only when the vendored payload files change (a manual vendor drop, not a nightly job).

**Scaling formula:** `CS+ = Math.round(100 + 10 * avgZ)` — literals `100` and `10` at `app.js:149` and `pitcher_app.js:459`. All constants are **code literals in the two JS files**; there is no config yaml and no fitted artifact.

Named constants:
| Constant | Value | Location |
|---|---|---|
| center | `100` | `app.js:149`, `pitcher_app.js:459` |
| per-sigma | `10` | same lines |
| SD fallback | `sd \|\| 1` | `app.js:117`, `pitcher_app.js:427` |
| clamp | **none** (40/160 removed 2026-07-29) | comment `app.js:142-148`, `pitcher_app.js:452-458` |
| pill/table color thresholds | `>=110` good, `<=90` bad (display only) | `app.js:158, 599, 667`; `pitcher_app.js:467, 873` |
| `TEAM_MIN_BATTERS` | `3` (team roll-up gate) | declared `app.js:708`, enforced `app.js:730` |
| `TEAM_MIN_ARMS` | `3` | declared `pitcher_app.js:1018`, enforced `pitcher_app.js:1040` |
| `LEADERBOARD_LIMIT` | `300` (display truncation, also caps the projections boards) | `app.js:77`, `pitcher_app.js:51` |

Observed served ranges (from the clamp-removal comments): hitters 80.3-118.7 (2024), 85.6-111.7 (2025); pitchers 65.2-123.3 (2024), 84.7-140.2 (2025), 66.8-122.2 (2026).

## Edge cases & guardrails

- **No minimum-sample gate on CS+ itself.** Every payload row of the season enters the pool and gets a CS+ if it has ≥1 finite component. Any sample gating happened upstream when the payloads were exported (e.g. the legacy CSV fallback is explicitly `min30pa`; the vendored national payloads' qualification rules are external and not reproducible from this repo). The UI "Min PA" / "Min pitches" inputs (`app.js:568-573`, `pitcher_app.js:846-852`) filter displayed rows only, **after** CS+ is computed on the full pool. Hitter rows with `pa == null` (all of 2025) always pass the Min PA filter (`app.js:573`); the pitcher filter has **no such null-pass** — `(p.pitch_count || 0) >= minPitch` (`pitcher_app.js:851`), and `normalizePitcher` defaults a missing `pitch_count` to `0` (`pitcher_app.js:565`), so a row without a pitch count would be hidden by any positive minimum (all 5,526 shipped rows carry `pitch_count`).
- **Missing components drop out** at two levels: a non-finite component is skipped inside its family (`app.js:134`), and a family with zero present components is skipped from the outer mean (`app.js:138`). A player with no components at all gets `null` (`app.js:140`) — rendered " - ", no pill (`plusPill` returns `""` for non-finite, `app.js:156-157`), excluded from the CS+ leaders sort (`app.js:528-529`, `pitcher_app.js:806-808`) and from team means (`filter(Number.isFinite)`, `app.js:712`).
- **Zero/empty pool:** `meanStd` returns `[0, 1]` for an empty pool and forces `sd=1` when the SD is 0, so division never blows up.
- **No capping/winsorizing:** the 40-160 display clamp was removed 2026-07-29 ("full true-to-model"); values print whatever the formula produces.
- **Year-dependent component availability** (pitchers): shape-only seasons (2026) compute the first family from `stuff_plus` alone by design; a 2026 row with `stuff_plus:null` (20 exist payload-wide) falls back to the contact family alone.
- **Payload failure:** a missing data script paints a visible error state instead of a blank page (`app.js:234-237`, `pitcher_app.js:536-539`; tests `test_collegesavant_smoke.py:204-226`).
- **Rounding:** `Math.round` to integer at compute time (the stored Map value is already rounded; the home widget re-rounds harmlessly at `app.js:516` / `pitcher_app.js:795`, and the `plus` formatter re-rounds at `app.js:557` / `pitcher_app.js:835`).
- **Sort-state details:** on the pitcher app, `cs_plus` as the active sort key explicitly survives a year switch (`state.sortKey !== "cs_plus"` guard, `pitcher_app.js:588-590`); the hitter leaderboard's Reset button sets the sort to `cs_plus` (`app.js:646`).

## Dependencies & discrepancies

**Consumes:**
- Vendored CollegeSavant TrackMan tracked-skill fields (external, static files).
- Vendored **CollegeSavant Stuff+** as one pitcher component. Scale-collision warning: that input is an external ratio scale (100 = college-average xRV, 0 = worst observed, measured SD ~23-24 per season, observed 3.4-185.4 — `data/glossary.json:6343-6344`) — one of **six** unrelated "Stuff+" scales in this tree (`glossary.json:6344` methodology; `ARKMETRIC_SCALE_CONVENTIONS.md:69, 73-77`): (1) this CollegeSavant display scale, (2) Will's 2026 formula-anchored vintage, (3) aStuff+ (`stuff_plus_aaa.py`, 100+10z vs qualified AAA), (4) tjStuff+ (`mlb_stuff_plus.py`, 100−10z INVERTED, clamped 20-180), (5) pStuff+ in Python (`storage.py`), (6) pStuff+ in the PROSPX leaderboard JS. Backend porters must take `stuff_plus` verbatim from `pitcher_data.js`, never substitute another Stuff+.

**Feeds: nothing outside the two pages.** CS+ is display-only. Its full consumption surface, all in-page: the leaderboard CS+ column (default/reset sort on the hitter board), the home "CS+ (pro profile)" top-10 widget (`app.js:59, 502-534`; `pitcher_app.js:54, 790-813`), player-profile pills (`app.js:1026`, `pitcher_app.js:1289`), Team Tendencies "Team CS+" (`app.js:697, 710-713`; `pitcher_app.js:1008, 1021-1023`), the leaderboard GFX board column with legend "CS+ 100 = D1 average" (`app.js:659-690`; `pitcher_app.js:933-961`), and — easy to miss — the **MiLB Projections boards, which are RANKED by CS+** (translation rows sorted `(b.cs ?? -Infinity) - (a.cs ?? -Infinity)`, `app.js:902-906` with the pill at `:912`; `pitcher_app.js:1153-1157`, pill at `:1163`). No export, no Python consumer, no model input; registry verdict `unvalidated` / "descriptive college-pool-relative tracked-skill index; explicitly NOT a Single-A or pro projection". The pro-projection question is handled by the *separate* `college_translation` model (matched-pair K%/BB% Single-A translation, `college_translation.py`, registry row `college_translation`, artifacts `data/college_translation_eval.json`, `data/collegesavant_translation.js`, `data/collegesavant_milb_equiv.json`) — CS+ is not an input to it (it only orders its display board). **FV is deliberately NOT projected from CS tracked data**: across 236 matched players every tracked metric correlates with scout FV at ~0 (90th EV −0.01, barrel 0.05, K% −0.09), so no CS+→FV model exists (recorded in the project's module-state notes, verified; context only — do not build one).

**Discrepancies found:**
1. **Stale clamp documentation.** The code is unclamped (removed 2026-07-29, `app.js:142-149`), and the glossary agrees — `data/glossary.json:170` ends its scaling sentence "(unclamped)" (the sentence reads garbled: "Rescaled 100 + 10 x z and clamped to 100 plus 10z (unclamped)", clearly a partial edit, but the operative word is there). BOTH `data/model_registry.json:2571` (`cs_plus` notes: "SCALE: 100 + 10z against the per-year college cohort, clamped 40-160") and `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:46` (clamp column "40-160") + `:78` ("CS+ and $DvM+ clamp at 40-160") still say 40-160. The code and glossary are correct; the registry notes and scale-conventions table are stale. (The generated `MODEL_REGISTRY.md:183` summary row truncates before the clamp text, so it carries no claim either way.) Do not implement a clamp.
2. **Duplicated implementation.** `computeCSPlus`/`meanStd` exist twice (`app.js` and `pitcher_app.js`) with identical math but different `CSPLUS_GROUPS`; there is no shared module, so any port must implement both component lists against one shared kernel.
3. **`chase_pct` sign flip** between sides (hitter dir −1, pitcher dir +1) — intentional, but an easy porting bug.
4. **Hitter/pitcher null-coercion asymmetry** in the normalizers: pitcher maps JSON `null` → `null` (drops out); hitter maps only `""` → `null`, so a JSON `null` would become `0` via `Number(null)`. Currently latent (hitter payload holds zero nulls; pitcher payload holds 45), but a server port reading raw JSON must replicate the *pitcher* semantics on both sides or guarantee null-free hitter input.
5. No Python/JS recompute mismatch exists (unlike SC+/pStuff+): there is **no Python implementation at all** — the JS is the single source of truth for CS+ values.

### Verification log

Corrections and additions made against the code (draft was largely accurate; every formula, constant, threshold, and line range in the algorithm sections verified exact):

1. **Hitter legacy-fallback chain corrected.** Draft said the app "fetches `b1g_2025_hitter_xwoba_min30pa.csv`" when `HITTER_DATA` is absent. The code tries the inline `window.B1G_CSV` blob first (`app.js:219`: `const text = window.B1G_CSV || await fetch(CSV_PATH)...`), defined in `collegesavant/data.js` (which also defines `window.B1G_TEAMS`) and loaded on both pages before the apps (`index.html:94`, `pitcher_index.html:96`). The CSV file itself does not exist in the working tree or anywhere in git history (`git log --all -- "*b1g_2025*"` is empty), so the fetch leg is dead and would paint the error state.
2. **Team-gate location refined.** The 3+ member gate is enforced in `computeTeamTendencies` (`app.js:730`, `pitcher_app.js:1040`), not inside the roll-up ranges the draft cited (`app.js:708-718`, `pitcher_app.js:1018-1027` — those contain the constants and `teamMetricValue`).
3. **Added a missed consumption surface:** the MiLB Projections translation boards are *ranked by CS+* (`app.js:902-906`, pill `:912`; `pitcher_app.js:1153-1157`, pill `:1163`), plus player-profile pill sites (`app.js:1026`, `pitcher_app.js:1289`) and the leaders-route metric resolver (`pitcher_app.js:1675`).
4. **Added the pitcher-payload null inventory** (45 `:null` total: `avg_ivb` 21, `stuff_plus` 20, `chase_pct` 2, `k_pct` 1, `bb_pct` 1; measured by regex over `pitcher_data.js`) and the fact the hitter payload has zero nulls with all six components on all 3,791 rows.
5. **Added the hitter `Number(null) === 0` coercion hazard** (`app.js:297` maps only `""` → null) vs the pitcher's explicit null handling (`pitcher_app.js:563`) — new discrepancy #4.
6. **Field-census precision:** pitcher outcome fields (`swinging_strike_pct`/`chase_pct`/`k_pct`/`bb_pct`/`z_contact_pct`) counted at exactly 4,684 keys = 4,485 (2024) + 199 (2025); `stuff_plus`/`xwoba_against`/`barrel_pct`/`hard_hit_pct`/`pitch_count`/`team` on all 5,526 rows; hitter `pa`/`team` on exactly the 3,607 2024 rows. Row counts 3,607/184 and 4,485/199/842 verified by per-year key counts.
7. **Added `hasPitchByPitchOutcomes(year) === (year === 2024 || year === 2025)`** (`pitcher_app.js:1607-1609`) corroborating the shape-only-2026 claim, and the pitcher Min-pitches filter's lack of a null-pass (`(p.pitch_count || 0) >= minPitch`, `pitcher_app.js:851`; default 0 at `:565`).
8. **Registry row bounds tightened:** `cs_plus` row spans `data/model_registry.json:2562-2572` with `model_id` at exactly `:2563`; stale clamp text at `:2571`. `collegesavant_stuff` row at `:2014-2027` (draft said 2015-2027; `model_id` is at 2015, the object opens at 2014). Generated `MODEL_REGISTRY.md:183` summary row noted.
9. **Glossary quotes verified precisely:** id `cs_plus` at `glossary.json:157`; the "(unclamped)" sentence at `:170` is garbled ("clamped to 100 plus 10z (unclamped)") — quoted as-is so porters are not confused; `collegesavant_stuff_plus` id at `:6332` (draft pointed at `:6350`, which is the `origin` field carrying the Will Cahoon / "does not fit or re-derive" text — both now cited at their exact lines).
10. **Commit lineage expanded:** `bc2d81f` "Add CollegeSavant app" and `68e0f67` folder reorg predate `d9656bb` (where `hitter_year_data.js`/`pitcher_data.js` enter); `92618b5` year-split also added `test_collegesavant_payload_split.py`. Draft's two commits verified real with those exact subjects.
11. **run_monthly touchpoint range widened** to `:1944-1952` — the `refresh_collegesavant_stats` call is gated on `COLLEGESAVANT_MAX_TEAMS` (`:1944`), material for anyone tracing why the ingest may not run.
12. **FV-correlation aside verified** against the module-state note: exactly 236 matched players (draft said "~236"), correlations −0.01 / 0.05 / −0.09 as quoted.
13. **Smoke-test characterization sharpened:** `test_collegesavant_smoke.py:90-164` asserts the `cs-plus-pill` and `data-sort="cs_plus"` strings render (presence, not values); error-state tests at `:204-226` confirmed.
14. Verified unchanged (no correction needed): both `CSPLUS_GROUPS` blocks, `meanStd`, `computeCSPlus` (quoted byte-exact from `app.js:99-152` / `pitcher_app.js:409-462`), population-SD claim, `sd || 1` fallback, unclamped status + clamp-removal comments with the served ranges, invocation sites (`app.js:325`, `pitcher_app.js:586`), pill thresholds (`app.js:158/599/667`, `pitcher_app.js:467/873`), `LEADERBOARD_LIMIT` 300 (`app.js:77`, `pitcher_app.js:51`), `TEAM_MIN_BATTERS`/`TEAM_MIN_ARMS` = 3, Min-PA null-pass (`app.js:573`), CS+ leaders-sort exclusion (`app.js:528-529`), `college_translation.py:22-23` quote, `run_monthly.py:719-725`, `test_methodology_freshness.py:432`, ARKMETRIC cites (`:46, :69, :73-77, :78`), GFX caption credit (`app.js:681`), client-side-only classification, and the empty repo-wide grep for any other computing site (8 files total, none computing).


---

# draft_stock_plus

## Name in code & where computed

**In-code names (exact, case-sensitive):**
- `draft_stock_plus` — the served, post-college-nudge value on each draft-prospect record in `data/draft_timeseries.json` (`prospect-tracker/draft_export.py:669`); also copied verbatim onto every mock-draft pick row (`mock_draft.py:367`), so the artifact carries it in TWO places per class: `classes[].prospects[].draft_stock_plus` and `classes[].mock_draft.picks[].draft_stock_plus` (mock baked at `cls["mock_draft"]`, `mock_draft.py:412`)
- `draft_stock_plus_pre_college` — the rank-only value before the college nudge (`draft_export.py:670`)
- `draft_stock_plus_college_boost` — `sp_boosted - sp`, the applied nudge; `0` when a z was computed but rounded/clamped to nothing, `None` when `sp` is `None` (`draft_export.py:671`)
- `stock_plus_mean` — class-level mean, one per class block (`draft_export.py:839`)
- Display labels: "DS+" and "Draft Stock+" are the glossary aliases (`data/glossary.json:5779-5782`); "Stock+" and "Stk+" are frontend-only labels (`prospx/index.html:16750`, `:33580`, `:33725`) and are NOT in the glossary alias list

**Computation sites:**

1. **PRODUCTION** — `prospect-tracker/draft_export.py`:
   - `_stock_plus(rank, class_ranks)` at `draft_export.py:220-233` (the rank→index map; comment block `:217-219`)
   - `_college_perf_z(summary)` at `draft_export.py:179-214` and `_summarize_college_stats` at `draft_export.py:132-176` (the college nudge signal); pitcher-row detection `_is_pitcher_stat_row` at `:126-129`
   - Assembly inside `_build_class` at `draft_export.py:507-516` (class consensus ranks), `:554-557` (per-player `sp`), `:595-608` (college boost), `:669-671` (output fields), `:839` (class mean)
   - Pipeline chain: `run_monthly.py:1953` calls `export_draft_json(out_dir / "draft_timeseries.json")` inside `_run_draft_pipeline` (step `"0c. Draft pipeline (scrape + promote + export)"`, `run_monthly.py:1890`), and `run_monthly.py:592` calls it again in the `rebuild_only` hook (`:586-595`). `export_draft_json` (`draft_export.py:1031-1040`) → `build_draft_export` (`draft_export.py:940`) → `_build_class`. The artifact is `data/draft_timeseries.json`. The draft source-weight A/B (`run_draft_weight_ab`, `run_monthly.py:3655-3656`) runs AFTER the export in the same monthly run.

2. **Duplicate implementation (replica)** — `prospect-tracker/efv_score.py`, inside `_provisional_prior_war`:
   - `_v3_stock_plus` at `efv_score.py:212-222` is an explicit replica of `draft_export._stock_plus` ("draft_export._stock_plus replica (rank-consensus DS+)").
   - `_v3_class_dsplus` (`efv_score.py:224-242`) recomputes per-class DS+ from the `draft_snapshots` DB table for historical classes; `_v3_current_class_dsplus` (`efv_score.py:244-262`) prefers joining the CURRENT class through the served payload's `draft_stock_plus_pre_college` field (read at `:255`), falling back to the DB recompute. `_v3_build_dsplus_map` (`:264-304`) only enumerates classes with `draft_year >= 2018` (`:274-275`).
   - **This lane is OFF in production**: it is the P1 V3 "ARM-B" eFV provisional-prior arm, gated by env flag `EEPHUS_P1_DSPLUS`, whose shipped default is `False` (`_p1v3_defaults = {"EEPHUS_P1_SLOT_TRUST": True, "EEPHUS_P1_DSPLUS": False}`, `efv_score.py:170`; env read at call time, `:172-181`). Flip record: `docs/efv-provisional-prior/GATES.md` — ARM-B FAILED its B1 gate (covered n=294, delta Spearman -0.0016, CI95 [-0.0077, +0.0030], `GATES.md:416`); the basis is documented in `data/xfv_provisional_prior_eval.json:330` ("rank-consensus DS+ ... BEFORE the college +-6 boost, one basis for live + historical"). Unless someone sets the env var, `_v3_dsplus` returns `None` (`efv_score.py:306-315`) and DS+ never touches eFV.

3. **Lab (not production)** — `tools/efv_provisional_prior_lab.py:713-732`: `_v3_class_dsplus` there imports the production `_stock_plus` (`from draft_export import _stock_plus`, `:718`) for backtesting. Defines no shipped artifact.

4. **Consumers that do NOT recompute it:**
   - `mock_draft.py` (production; called via `attach_mock_draft` from `build_draft_export` at `draft_export.py:1002-1006`; only built for the `is_current` class with no real picks yet, `mock_draft.py:284-289`): reads `p.get("draft_stock_plus")` as a `1e-4`-weight deterministic tiebreak in pick scoring (`mock_draft.py:256`, with FV at `1e-6` on `:257`), as the first tiebreak after `consensus_pick` in the board sort (`mock_draft.py:300-305`, DS+ desc at `:302`), and copies it onto each mock pick (`mock_draft.py:367`). The mock's `basis` string names it ("Board (consensus rank + Draft Stock+) anchors each pick", `:376-378`) and is rendered verbatim by the frontend (`prospx/index.html:24013`). Defaults: `_DEFAULT_ROUNDS = 2` (`:45`), candidate window `_WINDOW = 7` (`:50`).
   - Frontend `prospx/index.html`: pure display/sort/consume — never recomputes. Full site list:
     - Sort mode `stock_plus` (`:23380-23382`; `?? -Infinity` sinks nulls) selected by the dropdown `<option value="stock_plus">` (`:9346`)
     - Rankings board card chip "DS+ NNN" inside `_renderDraftCard` (`:23548-23549` read, chip at `:23736-23739`); class header strip copy "normalized within this class only (100 = class median)" (`:23527`)
     - Default draft sort: FV desc, then TBS (which embeds DS+) via shim objects `{fv_close, draft_stock_plus, tools, tool_grades}` (`:23441-23456`)
     - Draft-cohort TBS anchor term: `dsPlus` read at `:11105`; `dsPlus != null` selects the DRAFT TBS weighting branch (`:11114`); parts list `[_tbsNorm(dsPlus, 70, 130), 0.27]` (`:11119`) — the largest single weight; `_tbsNorm(v, lo, hi)` = `clamp((v-lo)/(hi-lo), 0, 1)` (`:10937-10941`); missing signals drop out and remaining weights renormalize
     - Mock-draft table DS+ column (`:24004`, header `:24023`, legend "DS+ = Draft Stock+ (100 = class median)" `:24016`)
     - Leaderboard view `_renderDraftLeaderboard` (`:24624`): class-wide ranking sorted DS+ desc then FV desc (`:24633-24634`), top-50 cap `LEADER_CAP = 50` (`:24637`), per-position bests keyed on max DS+ (`:24647-24651`, rendered `:24655`), main table DS+ column (`:24733`), caption "ranked by Draft Stock+ (100 = class median), then consensus FV" (`:24738-24743`)
     - Detail page hero DS+ chip (`:28403`) and Overview stat tile (`:28423-28424`)
     - Detail sidebar "signals" row in `_draftDetailSidebarCards` (`:16750-16751`) with its OWN color thresholds: `>=110` → `var(--up)`, `<=90` → `var(--down)`, else neutral — different bands from `_stockPlusColor`
     - Compare/scatter chart axis: `CHART_AXES.draft` row `{key: "draft_stock_plus", label: "Draft Stock+", fmt: formatMetric(v, 'plus')}` (`:18457`)
     - News-GFX draftee cards: value line `"Stk+ " + Math.round(p.draft_stock_plus)` (`:33580`), legend `draftee: "Stk+ = Draft Stock+ (100 = class median) · badge = consensus FV"` (`:33725`)
     - College-stats card note consuming `draft_stock_plus_college_boost`: "Currently nudging DS+ by +N." (`:28703-28704`)
     - Color mapping `_stockPlusColor` (`:22738-22745`)
   - No other frontend surface: a repo-wide grep for `dsPlus|stock_plus|Draft Stock` finds NOTHING under `assets/` or any other HTML/JS — `prospx/index.html` is the only frontend consumer. CAUTION: the `dsPlus` identifier at `prospx/index.html:40051` is `org.dvm_plus` (org development-vs-mean), an unrelated quantity that merely reuses the variable name.
   - Tests (recompute/pin behavior, not production): `test_audit_fixes.py:19-28` pins the M8 fix (fractional consensus ranks 4.4 vs 4.6 must yield distinct DS+); `test_methodology_freshness.py:435` maps registry id → glossary id; `test_mock_draft.py:35` fabricates DS+ (`140 - pick`) for mock tests.

**Registry anchors:** `data/model_registry.json` row `model_id: "draft_stock_plus"` (object at lines 2595-2605; verdict `unvalidated`, `eval_artifact: null`, "2026-07-29 display-index registration ... Served on 2,344 of 2,832 draft rows"); `MODEL_REGISTRY.md:186`; `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:64` classifies DS+ as scale family "5 (linear percentile)"; glossary entry `data/glossary.json:5772-5791`. Note `docs/audit/current_state_map.md:69` still lists DS+ among "glossary metrics with NO registry row" — that doc predates the 2026-07-29 registration and is stale on this point.

**Discrepancy flags (details in section 6):** the module docstring at `draft_export.py:43` claims each timeseries `points[]` entry carries a per-snapshot `draft_stock_plus: 150` — it does not (the actual point dict at `draft_export.py:571-581` has only `snapshot_date, source, interval_label, rank, fv, fv_plus, tools`). The frontend calls DS+ "z-normalized" in two places (`prospx/index.html:28403`, `:28424`) — it is not a z-score.

## Formula or fitted model?

**Deterministic formula. No trained model, no fitted artifact, no coefficients.** The registry row says so explicitly: baseline "n/a (heuristic stock indicator, explicitly not a projection)", verdict `unvalidated`, `eval_artifact: null` (`data/model_registry.json:2600-2603`). Everything is a code literal.

**Step 1 — per-source latest rank.** For one class year, take every row of the `draft_snapshots` table with that `draft_year` (`_build_class`, `draft_export.py:492`), group by (deduped) `player_key`, and for each player keep the latest snapshot per `source` (`_latest_per_source`, `draft_export.py:245-250` — sort ascending by `snapshot_date`, last write per source wins).

**Step 2 — consensus rank = equal-weight mean, 2 dp.** `_consensus(plist, "rank")` (`draft_export.py:510`, function at `:273-289`): mean of the latest non-null `rank` per source, `round(..., 2)` (`:287`; Python round-half-even at 2 dp). Rank consensus is **deliberately unweighted** — the accuracy-weighted source votes apply only to FV, not rank (FV consensus passes `weights=_DRAFT_SOURCE_WEIGHTS` at `:550`; "Rank stays unweighted - vote weights are a FV-accuracy result, not a rank one", `draft_export.py:548-549`). A single-source player's "consensus" is just that source's rank. Ranks are kept as floats; the class list is `class_rank_list = sorted(consensus_ranks.values())` (`draft_export.py:516`; the comment at `:513-515` records that `int()` truncation used to collapse 4.4 and 4.6 into a tie — regression-pinned by `test_audit_fixes.py:19-28`).

**Step 3 — rank → index.** `draft_export.py:217-233`, verbatim:

```python
# Draft Stock+ - class-normalized index. 100 = class median rank,
# 130 ≈ +2 sigma toward #1 (so a top-5 pick reads ≥130 in most classes),
# 70 ≈ -2 sigma (toward the back of the class). Lower rank = higher stock.
def _stock_plus(rank: float | None, class_ranks: list[float]) -> int | None:
    if rank is None or not class_ranks:
        return None
    n = len(class_ranks)
    if n < 2:
        return 100
    # Convert rank → percentile (lower rank = higher percentile). Position is
    # the count of strictly-better (lower) consensus ranks, computed on the raw
    # floats so 4.4 and 4.6 stay distinct; an exact tie shares a position.
    sorted_ranks = sorted(class_ranks)
    pos = sum(1 for r in sorted_ranks if r < rank)
    pct = 1.0 - (pos / max(1, n - 1))
    # Map pct → 70-130 index, with 0.5 → 100 (median)
    return int(round(70 + pct * 60))
```

So: `pos` = count of consensus ranks strictly lower (better) than this player's; `pct = 1 - pos/(n-1)`; `DS+ = round(70 + 60*pct)`. Best rank → 130, worst unique rank → 70, ties share a `pos`. (The "≈ +2 sigma" comment language is loose: this is a linear percentile map, not a sigma map — the registry row says so explicitly.) This value is `draft_stock_plus_pre_college` (`sp`).

**Step 4 — college-performance z.** `_college_perf_z` (`draft_export.py:179-214`) reads the **latest season** of the player's amateur statlines (`summary["trail"][0]["payload"]`, `:187-188`; the trail is sorted newest-first by season alone at `:139` — among two rows in the SAME season, Python's stable sort keeps DB row order, so which one becomes the headline is data-order-dependent):
- Pitcher rows (detected on the latest payload by any of `ip/era/k_per_9/fip` set, `draft_export.py:126-129, 141-142`): `z = round((4.0 - float(FIP or ERA)) / 1.5, 2)` — FIP preferred, ERA fallback; anchor 4.00, 1.5 runs ≈ 1σ (`:193-197`). NOTE: the function docstring (`:179-184`) says "ERA- for pitchers ... each -10 = ~1σ" — stale; the code uses RAW FIP/ERA (no league/park minus-scaling) with a 1.5-run sigma.
- Hitter rows: `z = round((wrc_plus - 100.0) / 30.0, 2)` if wRC+ present (`:202-207`), else `z = round((ops - 0.850) / 0.150, 2)` (`:208-213`), else `None` (`:214`).

**Step 5 — nudge + clamp.** `draft_export.py:595-608` (assembly comment at `:595-598`):

```python
sp_boosted = sp
if sp is not None and cperf_z is not None:
    # Cap the boost at ±6 pts so DS+ retains its rank-driven
    # character (rank is the primary signal - college is a
    # secondary confidence layer).
    boost = max(-6, min(6, round(cperf_z * 3.0)))
    sp_boosted = max(60, min(140, sp + boost))
```

`draft_stock_plus = sp_boosted`; `draft_stock_plus_college_boost = (sp_boosted - sp) if (sp is not None and sp_boosted is not None) else None` (`:669-671`).

**Step 6 — class aggregate.** `stock_plus_mean = round(sum(stock_plus_values) / len(stock_plus_values), 1)` if any, else `None` (`draft_export.py:839`) — note it accumulates the **pre-boost** `sp` (appended at `:556-557`, before the boost at `:602-608`), so the class mean is a pre-college-nudge mean even though the module docstring at `:16` calls it "class-median draft stock+" (it is a mean, not a median).

**How the backend team would port it:** pure arithmetic over (a) per-source draft board ranks and (b) latest amateur-season wRC+/OPS or FIP/ERA. Nothing to serve; reproduce the six steps above exactly, including the 2-dp rounding of consensus ranks, strict-less tie handling, the `n-1` denominator, and Python 3 `round()` semantics — banker's rounding on exact .5 applies to `round(cperf_z * 3.0)`, `int(round(70 + pct * 60))`, and the 2-dp consensus rounding.

## Inputs

| Input | Exact field | Ultimate source | Computed stat? |
|---|---|---|---|
| Source board rank | `draft_snapshots.rank` (per `player_key`, `source`, `snapshot_date`, `draft_year`), loaded by `storage.load_draft_snapshots` (imported `draft_export.py:88`) | Scraped draft boards via `scrapers.scrape_all_draft` (`scrapers.py:3026`): ESPN (`scrape_espn_draft`, `scrapers.py:2671`, source `espn_draft` at `:2828`), MLB Pipeline (`scrape_mlb_pipeline_draft`, `scrapers.py:2867`, source `mlb_pipeline_draft` at `:3012`); the `DraftSnapshot.source` enum also allows `'fangraphs' \| 'manual'` (`scrapers.py:132`) from the FG article/CSV ingestion lane. Historical 2018+ classes are backfilled final PRE-draft vintages (`efv_score.py:227-228`; `tools/efv_provisional_prior_lab.py:716-717`). | No — raw published ranks |
| College/HS statline payload | `draft_statlines.payload` keys `wrc_plus`, `ops` (hitters), `fip`, `era` (pitchers), grouped per player in `build_draft_export` (`draft_export.py:951-956`) | FanGraphs player-page amateur stats, scraped by `draft_stats.refresh_draft_stats` (`draft_stats.py:96`) reusing `overseas_stats.scrape_fg_player_stats` (imported `draft_stats.py:30`); rows filtered to amateur levels (`_DRAFT_LEVEL_PREFIXES`, `draft_stats.py:39-53`, gate `_is_draft_level` `:56-82`); provenance tag `"fg"` (`draft_stats.py:156`) with `ncaa`/`mlb_pipeline` rows possible via the `college_stats` fallback lane (frontend source labels at `prospx/index.html:28708`) | wRC+ is FanGraphs' computed stat, ingested as-is; not computed locally |
| Source vote weights | `data/draft_source_weights.json` loaded once at import (`draft_export.py:253-270`) | `draft_source_backtest.run_draft_weight_ab` (`run_monthly.py:3655-3656`) | **Not actually an input to DS+**: weights apply only to the FV consensus (`draft_export.py:550`); the rank consensus that feeds DS+ is always the equal mean (`:510`, `:548-549`). Current file (generated 2026-08-01) ships `"weights": {}` with note "equal-weight (ship=False on the latest A/B)" anyway. |

**Dependencies on other stats in the documented list: none as inputs.** DS+ consumes no efv/xfv, no rem/sem/hem/stuff/pal/wag/swing/collegesavant value, and no value_framework quantity. It shares the `_college_perf_z` helper with the draft-cohort `rps_plus` (RPS+ = `100 + 15*z`, clamp [60,140], `draft_export.py:740-747`) — same z, different scaling.

## Constants, baselines & normalization

**Baseline population:** the draft class itself — every prospect in the same `draft_year` with a computable consensus rank (`class_rank_list`, `draft_export.py:516`). 100 = class median board position. **Recomputed on every export run** (each `run_monthly.py` draft phase / rebuild-only pass); nothing is frozen or vintage-pinned — as new snapshots land or the class grows, every player's DS+ can move. Time window: latest snapshot per source (all history retained in `points[]`, but only the latest per source votes).

**Raw→plus scaling (all code literals in `draft_export.py`; no config yaml, no fitted artifact):**

| Constant | Value | Where |
|---|---|---|
| Index floor / span | `70 + pct * 60` (i.e. 70-130) | `draft_export.py:233` |
| Degenerate-class value | `100` when class has < 2 ranked players | `draft_export.py:224-225` |
| Percentile denominator | `n - 1` (via `max(1, n-1)`) | `draft_export.py:231` |
| Consensus-rank rounding | 2 dp | `draft_export.py:287` (`_consensus`, equal-mean path) |
| Hitter z anchor / scale | wRC+ 100, ÷30 per σ | `draft_export.py:205` |
| Hitter OPS fallback anchor / scale | 0.850, ÷0.150 per σ | `draft_export.py:211` |
| Pitcher z anchor / scale | FIP/ERA 4.00, ÷1.5 per σ (negated: lower = better; FIP preferred, ERA fallback) | `draft_export.py:193-197` |
| z rounding | 2 dp | `draft_export.py:197,205,211` |
| Boost multiplier | `cperf_z * 3.0` | `draft_export.py:607` |
| Boost clamp | ±6 | `draft_export.py:607` |
| Final clamp (post-boost only) | [60, 140] | `draft_export.py:608` |
| Class-mean rounding | 1 dp | `draft_export.py:839` |
| eFV ARM-B (default OFF) scale | `ped += 0.4 * max(0.0, (DSplus - 100.0) / 10.0)`; 0.4 and /10 are "frozen a-priori registration constants"; capped by `max_pedigree_precision` (default 3.0) | `efv_score.py:150-155` (docstring), `:421-424` (code) |
| Frontend TBS normalization | `_tbsNorm(dsPlus, 70, 130)` = `clamp((DS+ - 70)/60, 0, 1)`, weight **0.27** in the draft TBS parts list (largest single weight; DS+ presence selects the draft branch) | `prospx/index.html:10937-10941, 11105, 11114, 11119` |
| Frontend color bands (`_stockPlusColor`) | ≥130 green, ≥110 cyan, ≥90 neutral, ≥70 orange, else red; null → tertiary | `prospx/index.html:22738-22745` |
| Sidebar-signals color bands (separate!) | ≥110 `var(--up)`, ≤90 `var(--down)`, else neutral | `prospx/index.html:16750-16751` |
| Mock-draft tiebreak weights | DS+ `* 1e-4`, raw FV `* 1e-6` | `mock_draft.py:256-257` |

Scale family per `docs/efv-2026-07-29/ARKMETRIC_SCALE_CONVENTIONS.md:64`: "5 (linear percentile) | consensus board rank mapped to about 70-130, plus a college nudge of about 6 | clamped" — i.e. NOT `100+10z`, NOT a ratio.

## Edge cases & guardrails

- **No consensus rank** (`rank is None`) or empty class → `draft_stock_plus = None` (`draft_export.py:221-222`); excluded from `stock_plus_mean` (`:556-557`); frontend renders "-" (mock table `:24004`, card chip `:23739`, leaderboard `:24733`) and unranked rows sink in sorts (`?? -Infinity`, `prospx/index.html:23382`).
- **Class of one ranked player** (`n < 2`) → hard `100` (`draft_export.py:224-225`).
- **Ties:** exact consensus-rank ties share a `pos` (strictly-less count), so tied players get identical DS+; fractional ranks are preserved to keep near-ties distinct (`draft_export.py:228-230, 513-516`).
- **No college stats / no usable headline metric** → `_college_perf_z` returns `None` at each fallthrough (`draft_export.py:185-186, 194-195, 214`) → boost skipped, `sp_boosted = sp`, boost field reads `0` (both non-None) or `None` (`:671`).
- **Boost clamps:** nudge capped at ±6; post-boost value clamped [60,140] (`:607-608`). Pre-boost value is naturally bounded [70,130] with no clamp needed.
- **Type errors** in statline floats → caught, `None` (`:196-199, 204-213`, plus `:151-154` in the headline formatter).
- **No minimum-sample threshold** on the college season (a tiny-sample season still nudges — even a 0.1-IP row flips the player to the pitcher branch via `_is_pitcher_stat_row`), and no gate on class size beyond n≥2. No minimum source count on the rank consensus either — one source is a valid "consensus".
- **Same-season ambiguity:** the headline season is chosen by `sorted(statlines, key=-season)` (`:139`) — season only, stable sort — so among multiple rows in the same season (e.g. college + Cape Cod), DB row order decides which payload feeds the z.
- **Name-variant dedupe** runs before consensus so a split player doesn't appear twice with two DS+ values (`_dedupe_merge_map`, applied `draft_export.py:493-505`).
- **eFV replica guardrails** (only relevant if `EEPHUS_P1_DSPLUS` is ever turned on): lookups key on `(pick_overall, bonus_usd)` — `(int(pick), float(bonus) or None)` (`efv_score.py:289-290`, lookup `:315`); a missing-bonus key with a current-class candidate resolves to the current class's DS+ (`:297-300`); any other key is served only when every candidate class maps to the SAME DS+, else dropped (row unchanged) (`:301-303`; docstring `:156-159`); historical recompute is limited to `draft_year >= 2018` (`:274-275`); the added precision only applies above the class median (`max(0.0, ...)`, `:423`) and is capped by `max_pedigree_precision` (default 3.0, `:424`).

## Dependencies & discrepancies

**Feeds (downstream consumers):**
- **Mock draft** (`mock_draft.py`, production via `attach_mock_draft` from `build_draft_export`, `draft_export.py:1002-1006`; current pre-draft class only): board sort first-tiebreak after `consensus_pick` (`:300-305`), candidate-score deterministic tiebreak `score += ds * 1e-4` (`:256`), and the per-pick export field (`:367`). Mock output is served inside the same artifact at `classes[].mock_draft` (`:412`).
- **TBS (draft variant)** in `prospx/index.html:11105-11126`: DS+ is the **anchor term** of the draft prospect tiebreaker score — `[_tbsNorm(dsPlus, 70, 130), 0.27]` (`:11119`) — the largest single weight, and `dsPlus != null` is what selects the draft-cohort weighting branch (`:11114`); used for same-FV ordering on the draft board (`:23441-23456`). (TBS itself is registered `unvalidated`, `model_registry.json` `tbs_prospect` row, lines 2606-2614.)
- **eFV provisional prior ARM-B** (`efv_score.py:421-424`): reads `draft_stock_plus_pre_college` (the PRE-college value — registry note confirms "eFV reads the PRE-college value"; basis re-confirmed in `data/xfv_provisional_prior_eval.json:330`) from the served `data/draft_timeseries.json` for the current class, replica-recomputes for historical classes. **Shipped default OFF** (`EEPHUS_P1_DSPLUS` default `False`, `efv_score.py:170`; gate outcome B1 FAIL, `docs/efv-provisional-prior/GATES.md:416`), so in an unmodified production environment DS+ does not affect eFV.
- Frontend display/sort surfaces enumerated in section 1 (rankings cards, leaderboard, mock table, detail page, sidebar signals, compare-chart axis, news GFX).
- Not consumed by rem+/sem+/hem+/stuff+/pal/wag/value_framework/swing+/collegesavant+.

**Consumes:** no other documented stat. Shares the `_college_perf_z` signal with draft-cohort `rps_plus` (different scaling: RPS+ `100+15z` clamp [60,140] vs DS+ nudge `round(3z)` clamped ±6).

**Discrepancies found:**
1. **Stale docstring** — `draft_export.py:43` documents a per-snapshot `"draft_stock_plus": 150` inside each `points[]` entry; the actual point dict (`draft_export.py:571-581`) carries no DS+. Only the player-level (latest-consensus) value exists. Backend team: do not implement a per-snapshot DS+.
2. **Frontend copy vs math (two sites)** — the detail hero tooltip (`prospx/index.html:28403`, "Draft Stock+ - z-normalized within the ... class") AND the Overview stat-tile title (`:28424`, "Z-normalized within this draft class. 100 = class median.") both call DS+ z-normalized. It is a linear percentile map, not a z-score (registry row: "a LINEAR PERCENTILE style map, not a z-score and not a ratio", `model_registry.json:2604`). The glossary entry (`glossary.json:5784-5786`) is accurate and agrees with the code.
3. **Loose sigma/decile copy** — the code comment (`draft_export.py:217-219`, "130 ≈ +2 sigma") and the rankings-card chip tooltip (`prospx/index.html:23738`, "+30 ≈ top decile") both describe the percentile map in distribution language it doesn't have: DS+ ≥ 124 is the top decile (`pct ≥ 0.9`); 130 requires `pct ≥ 0.99167`, roughly the top 0.8% of the class.
4. **Stale `_college_perf_z` docstring** — `draft_export.py:180-184` says the pitcher signal is "ERA- ... each -10 = ~1σ"; the implementation uses raw FIP (preferred) or ERA anchored at 4.00 with 1.5 runs per σ (`:193-197`) — no ERA-minus normalization exists anywhere in the lane.
5. **`stock_plus_mean` basis** — the class mean aggregates the **pre-college-boost** `sp` values (`draft_export.py:556-557` runs before `:602-608`), while the displayed per-player `draft_stock_plus` is post-boost. The module docstring (`:16`) also calls it a "median" — it is a mean.
6. **Two implementations of the rank→index map** — production `draft_export._stock_plus` (`draft_export.py:220-233`) and the `efv_score.py:212-222` replica. Math is currently identical (float ranks, strict-less position, `70 + 60*pct`, `n-1` denominator, equal-mean 2-dp consensus). The replica's historical-class consensus (`efv_score.py:229-240`) always uses the equal mean directly from `draft_snapshots`; production's rank consensus is also always equal-mean, so they agree today — but if rank weighting were ever introduced in `draft_export`, the replica would silently diverge. A third copy in `tools/efv_provisional_prior_lab.py:713-732` imports the production function (no divergence risk; lab only).
7. **Inconsistent frontend color semantics** — `_stockPlusColor` (`prospx/index.html:22738-22745`) colors 90-109 neutral with green only at ≥130, but the detail-sidebar signals row (`:16751`) flips positive at ≥110 / negative at ≤90 with a different palette. Same number, two visual encodings.
8. **Stale audit doc** — `docs/audit/current_state_map.md:69` lists DS+ as having no registry row; the row exists (`model_registry.json:2595-2605`, added 2026-07-29).
9. **Registry/glossary agreement** — `model_registry.json:2595-2605`, `MODEL_REGISTRY.md:186`, `ARKMETRIC_SCALE_CONVENTIONS.md:64`, and `glossary.json:5772-5791` all describe the code accurately (rank-to-index ~70-130 + ~±6 college nudge, clamped, heuristic/unvalidated). No version pin, fingerprint, or eval artifact exists for DS+ itself — appropriate, since there is no fitted model to pin. (The only eval artifact touching DS+ is `data/xfv_provisional_prior_eval.json`, which evaluates the eFV ARM-B lane that FAILED and ships OFF.)

### Verification log

- CORRECTED: `prospx/index.html:24004` was attributed to the "draft-board column" — it is the **mock-draft table** DS+ column (renderer ends `:24028`, mock rows built from `mock.picks`; header `:24023`, legend `:24016`). The Rankings board renders DS+ as a card chip inside `_renderDraftCard` (`:23548-23549`, chip `:23736-23739`), not a column; the only DS+ table column on the board side is the Leaderboard view (`:24733`).
- CORRECTED: "best-by-position widget (`:24633-24655`)" expanded to the full `_renderDraftLeaderboard` view (`:24624`): DS+-desc class ranking (`:24633-24634`), `LEADER_CAP = 50` (`:24637`), per-position bests (`:24647-24651`), DS+ column (`:24733`), caption (`:24738-24743`).
- CORRECTED: alias attribution — `glossary.json` aliases are only "DS+" and "Draft Stock+" (`:5779-5782`); "Stock+" (`prospx/index.html:16750`) and "Stk+" (`:33580`, `:33725`) are frontend-only labels, not glossary aliases.
- CORRECTED: `_DRAFT_LEVEL_PREFIXES` is `draft_stats.py:39-53` (draft said 39-55); the level gate `_is_draft_level` is `:56-82`.
- CORRECTED: ARM-B application code range is `efv_score.py:421-424` (the `max_pedigree_precision` cap at `:424` is part of the lane), and the registry row object spans `model_registry.json:2595-2605`.
- CORRECTED: `run_draft_weight_ab` call is `run_monthly.py:3655-3656` (3653 is a comment line).
- ADDED consumption sites the draft missed (all verified): detail-sidebar signals row with its own ≥110/≤90 color thresholds (`prospx/index.html:16750-16751`, inside `_draftDetailSidebarCards` at `:16610`); compare/scatter `CHART_AXES.draft` axis (`:18457`); news-GFX "Stk+" value line (`:33580`) + draftee legend (`:33725`); sort dropdown option (`:9346`); class header-strip copy (`:23527`); Overview stat-tile title (`:28424`); college-stats card boost note consuming `draft_stock_plus_college_boost` (`:28703-28704`); mock `basis` string naming DS+ (`mock_draft.py:376-378`, rendered `:24013`).
- ADDED: mock output is baked at `cls["mock_draft"]` (`mock_draft.py:412`), so DS+ ships twice in `data/draft_timeseries.json` (prospects[] and mock_draft.picks[]); mock defaults `_DEFAULT_ROUNDS = 2` / `_WINDOW = 7` (`mock_draft.py:45,50`); mock built only for `is_current` classes with no real picks (`:284-289`); FV secondary tiebreak weight `1e-6` (`:257`).
- ADDED discrepancy: SECOND "z-normalized" copy error at `prospx/index.html:28424` (stat-tile title) alongside the already-flagged `:28403`.
- ADDED discrepancy: stale `_college_perf_z` docstring (`draft_export.py:180-184` claims "ERA- ... each -10 = ~1σ"; code uses raw FIP/ERA, anchor 4.00, ÷1.5 at `:193-197`).
- ADDED discrepancy: loose sigma/decile copy (`draft_export.py:217-219` "130 ≈ +2 sigma"; `prospx/index.html:23738` "+30 ≈ top decile"; actual top-decile threshold is DS+ ≥ 124, and 130 ≈ top 0.8%).
- ADDED discrepancy: two conflicting frontend color encodings (`_stockPlusColor` `:22738-22745` vs sidebar `:16751`).
- ADDED: `_v3_build_dsplus_map` restricts historical classes to `draft_year >= 2018` (`efv_score.py:274-275`); ARM-B gate outcome specifics (B1 FAIL, n=294, delta -0.0016, CI95 [-0.0077, +0.0030], `docs/efv-provisional-prior/GATES.md:416`); ARM-B basis note at `data/xfv_provisional_prior_eval.json:330`.
- ADDED: regression/support tests — `test_audit_fixes.py:19-28` (M8 fractional-rank distinctness pin on `_stock_plus`), `test_methodology_freshness.py:435` (registry↔glossary id map), `test_mock_draft.py:35` (synthetic DS+).
- ADDED: current `data/draft_source_weights.json` contents verified (generated 2026-08-01, `"weights": {}`, note "equal-weight (ship=False on the latest A/B)").
- ADDED: stale-audit-doc note (`docs/audit/current_state_map.md:69` predates the 2026-07-29 registry row).
- ADDED: name-collision caution — `dsPlus` at `prospx/index.html:40051` is `org.dvm_plus` (development-vs-mean), unrelated to DS+.
- ADDED: same-season headline nondeterminism (`draft_export.py:139` sorts by season only; stable sort → DB row order picks among same-season rows) and the no-min-source-count note on the rank consensus.
- ADDED: run_monthly context detail — `:1953` sits inside `_run_draft_pipeline`, step "0c. Draft pipeline (scrape + promote + export)" (`:1890`); rebuild-only call at `:592` inside the `:586-595` block; the source-weight A/B runs after the export.
- VERIFIED UNCHANGED (spot-checked against code): the `_stock_plus` and boost snippets are byte-accurate (`draft_export.py:217-233`, `:602-608`); all constants in the constants table; `_consensus` 2-dp equal-mean (`:273-289`); FV-weighted/rank-unweighted split (`:548-550`); output fields (`:669-671`); `stock_plus_mean` pre-boost basis (`:556-557`, `:839`); points dict shape (`:571-581`) vs docstring `:43`; `_p1v3_defaults` (`efv_score.py:170`); replica math (`:212-222`); `(pick, bonus)` keying and drop-on-disagreement (`:289-303`, `:156-159`); `mock_draft.py:256/302/367`; scrapers anchors (`scrapers.py:132, 2671, 2828, 2867, 3012, 3026`); `draft_stats.py:30, 96, 156`; registry/glossary/scale-conventions/MODEL_REGISTRY.md rows; `_tbsNorm` and the 0.27 anchor weight (`prospx/index.html:10937-10941, 11119`); `_stockPlusColor` bands (`:22738-22745`); sort mode (`:23380-23382`); TBS shim tiebreak (`:23441-23456`).
