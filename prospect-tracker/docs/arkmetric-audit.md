# Arkmetric suite — Phase 0 inventory (ground truth as built)

Scope: POW+/PWR+, HIT+, ISO+, RPS+, SC+, DvM+, $DvM+, ToolDvM+, WAG. This document
records what each metric *is today* — formula, inputs, baseline, weights, surfaces,
dependencies — and marks each as empirically grounded or ad hoc. Nothing is changed.
Open items where a computation site could not be fully pinned in this pass are listed
at the end. (Phases 1–3 follow at the checkpoints.)

## Naming resolution — POW+ vs PWR+
`computePowerPlus` (the implementation) and the glossary entry use **POW+** as the
canonical name; **PWR+** appears only as an alias in the glossary and in a handful of
labels/comments. **Canonical = POW+.** PWR+ should be removed as a surfaced label
(kept, if anywhere, as a search alias only). Logged for Phase 2 cleanup.

## Three structural findings that cut across the whole suite

1. **Three different math definitions hide under one "+" label.** The guardrail says
   "100 = average, 1 point = 1% of baseline." Only some metrics honor that:
   | Convention | Metrics | 1 point means |
   |---|---|---|
   | **Ratio** `100·v/μ` | ISO+, POW+, HIT+ | literally 1% of the baseline ✓ |
   | **z-score ×10** `100+10·(v−μ)/σ` | RPS+ (generic), DvM+, ToolDvM+, $DvM+, Stf+ | 0.1 σ ✗ |
   | **z-score ×15** `100+15·(v−μ)/σ` | SC+, RPS+ (draft cohort) | 0.15 σ ✗ |
   The z-score metrics do **not** satisfy "1 point = 1%"; their points are σ-units, and
   the σ-per-point scale is itself inconsistent (10 vs 15). This is the single most
   important conceptual finding — "111 = 11% above average" is true for the ratio
   metrics and false (or differently scaled) for the z-score ones.

2. **Two different FV→WAR curves are live at once.** WAG subtracts
   `_fv_to_expected_war_per_yr` (storage `FV_EXPECTED_WAR_PER_YR_HITTER/PITCHER`,
   ~survivor expectation: 45→0.8, 50→1.6, 55→2.5, 60→3.4). The surplus model
   (DvM+/$DvM+ feed off it) uses `value_framework.fv_to_6yr_avg_war` (bust-INCLUSIVE,
   recently recalibrated: 45→0.38, 50→0.70, 55→0.95, 60→1.45). These measure different
   populations (survivors vs all), but WAG is presented as *the* calibration-error
   signal on the FV scale, so the inconsistency needs an explicit reconciliation
   (Phase 1 item).

3. **Frontend vs backend rigor split.** The backend z-score metrics (DvM+, Stf+) already
   carry empirical-Bayes machinery: `test_metrics_audit.py` shows Stf+ uses empirical
   `pstdev` above a sample threshold (15%-of-mean only as fallback) and DvM+ shrinks
   small-n toward the league mean. The **frontend ratio metrics (POW+/HIT+/ISO+) have
   none of this** — a games gate, then full value, clamped to [0,250]. The biggest
   precision problems are concentrated in the frontend ratio blends.

## Per-metric ground truth

### ISO+ — `computeIsoPlus` (prospx/index.html ~41905)
- **Formula:** `100 · player_ISO / level_avg_ISO`, clamp [0,250].
- **Inputs:** `statline.iso`; `DATA.level_norms[level].perf.avg_iso`.
- **Baseline:** level-specific mean ISO from `level_norms.py::compute_level_norms` —
  per-level mean over a trailing-N-calendar-year window **including the in-progress
  season**, computed from all players' MiLB career rows at that level. **No park factor.
  No stddev.** Means only.
- **Sample handling:** 20-game gate (`PLUS_PROVISIONAL_GAMES`), then full value. **No
  regression toward a prior.**
- **Verdict:** baseline is level-correct (good) but **no park, no shrinkage** → ad hoc on
  reliability; ratio scale honors the "+" paradigm.

### POW+ (canonical; "PWR+") — `computePowerPlus` (~41961)
- **Formula:** `blend3(rawPerf, statcastPower, toolPlus; 0.45, 0.25, 0.30)`,
  renormalized over whichever components are present.
  - `rawPerf` = `0.6·ISO+ + 0.4·HR-rate+`.
    - **HR-rate+** = `100 · (HR/PA) / (0.18·level_avg_ISO)`, or via games
      `100·(HR/G)/(0.72·level_avg_ISO)`. **0.18 and 0.72 are assumed constants** (no
      citation, no fit).
  - `statcastPower` = `0.55·(HH%/33) + 0.45·(Barrel%/6)`. **33 and 6 are fixed pool
    anchors, not level-specific** (a single MLB-ish pool).
  - `toolPlus` = `_toolToPlus(power grade)` = `100 + (grade−50)·2`. **Linear, assumed**
    (a 60 power grade → 120; not calibrated to the ISO/HR a 60 historically produces).
- **Weights 0.45/0.25/0.30:** fixed hand-tuned constants (comment notes "was 70/30").
- **Inputs:** ISO+, HR/PA or HR/G, level_avg_ISO, HH%, Barrel%, power tool grade.
- **Verdict: ad hoc.** Assumed grade→outcome + HR/ISO constants; **additively stacks four
  correlated power measures** (ISO, HR-rate, hard-hit/barrel, power tool) → overconfident;
  Statcast pool-anchored while perf is level-anchored (mixed baselines); **no shrinkage**.

### HIT+ — `computeHittingPlus` (~42030)
- **Formula:** `blend3(rawPerf, statcastHit, toolPlus; 0.45, 0.25, 0.30)`.
  - `rawPerf` = `100·(0.6·(AVG/level_avg_AVG) + 0.4·(level_avg_K%/player_K%))` (AVG ratio +
    K%-avoidance contact ratio; contact-only fallback if avg_avg absent).
  - `statcastHit` = `0.5·(Z-Contact%/80) + 0.5·(26/Whiff%)`. **80 and 26 fixed pool anchors.**
  - `toolPlus` = `_toolToPlus(mean(Hit grade, Bat-Control grade))`.
- **Verdict: ad hoc.** Same pattern as POW+ — additively stacks AVG, K%, Z-contact, whiff,
  hit tool (all correlated contact measures), assumed pool anchors + linear tool map, no
  shrinkage. AVG (very slow to stabilize) carries 0.6 of rawPerf with no regression.

### RPS+ — multiple implementations (NOT one)
- **Draft cohort** (`draft_export.py` 451/491): `100 + 15·z(college_perf)`, clamp [60,140].
- **Overseas cohort** (`overseas_export.py` `_cohort_plus`): z-score vs the overseas cohort.
- **Active MiLB prospects:** surfaced as `statline.rps_plus`, consumed widely (breakout
  gates, leaderboards). **The exact main-pipeline computation was not pinned in this pass**
  (it is produced upstream of the export, level-cohort z-score in form) — *open item*.
- **Verdict:** z-score standardization (reasonable in principle) but **cohort-dependent and
  scale-inconsistent** (draft ×15 vs generic ×10), and the main MiLB formula must be
  confirmed before judging its baseline/σ.

### SC+ (Statcast+) — `statcast_plus.py`
- **Formula:** each component z-scored vs the **side-matched active pool**, averaged,
  rescaled to `100 + 15·z` (real `pstdev`, anchor 100, 15 pts/σ).
  - Hitters: EV / HH% / Barrel% (contact quality) + Z-Contact% / −Whiff% / −Chase% (zone).
  - Pitchers: Whiff% / Chase% (swing-miss) + −HH% / −Barrel% (contact suppression).
- **Baseline:** the active prospect pool (**not level-specific**), side-matched.
- **Surfaced:** baked `p.statcast_plus`; frontend `getStatcastPlus` falls back to recompute.
- **Verdict:** genuinely grounded standardization (empirical σ, real z-scores). Caveats:
  pool-anchored not level-anchored; 15 pts/σ differs from RPS+/DvM+ (10 pts/σ); tracking
  exists only at some levels → coverage/missing-data question for Phase 1.

### DvM+ — `_blend_dvm_3way` (storage ~11149)
- **Formula:** 50/30/20 blend of **FV-DvM / Tool-DvM / SC-DvM** (user-specified), with an
  adaptive tool-weight penalty on the FV+Tool sub-blend and missing-axis fallbacks (SC
  missing → 2-way FV/Tool; tool missing → 70/30 FV/SC; FV missing → 60/40 Tool/SC).
  - **FV-DvM:** FV appreciation — recent-window FV vs baseline-window FV (`_trajectory_score`
    family), z-scored ×10.
  - **Tool-DvM:** ToolDvM+ (below).
  - **SC-DvM:** Statcast development, z-scored ×10.
- **Verdict:** z-score components have empirical-Bayes shrinkage (per test suite). Blend
  weights (50/30/20, adaptive penalty) are **hand-specified, not derived** → ad hoc on
  weighting, grounded on the per-axis standardization.

### ToolDvM+ — `_bucket_tool_dvm_plus` (storage ~11217)
- **Formula:** position-weighted mean of per-tool DvM+ z-scores, weights from
  `_BUCKET_TOOL_WEIGHTS` (hand-assigned per position: e.g. C arm 0.25, INF hit 0.25, SP
  fb/cmd 0.25 each), renormalized over present tools.
- **Verdict:** per-tool DvM+ is a grounded z-score; the **position-tool importance weights
  are hand-assigned** (reasonable, undocumented derivation) → ad hoc on weighting.

### $DvM+ — `dollar_dvm` (storage ~8913)
- **Formula:** a prospect's per-prospect engine surplus, z-scored vs the **same FV-tier**
  mean (surplus-development vs FV-tier peers). Feeds the `fin_dollar_dvm` farm leaf.
- **Verdict:** **same-tier baseline (good)** and grounded standardization; inherits the
  surplus model's correctness (separately audited/recalibrated). Scale = z-score ×10.

### WAG — `_grad_wag` (storage ~3927)
- **Formula:** full-season-equivalent realized WAR (career WAR/(PA|IP) × role full-season
  target from `role_full_season_baselines.json` = MLB qualifier medians) **minus
  `_fv_to_expected_war_per_yr(fv_close)`**.
- **Sample floor:** hitters ≥150 PA, pitchers ≥50 IP (else None).
- **Verdict:** grounded residual-vs-expectation construct. **But** it is measured against a
  *different* FV→WAR curve than the surplus model uses (finding #2), and there is no
  visible feedback loop writing WAG's measured error back into either curve — so the
  "calibration-error → recalibrate" loop is open.

## Dependency graph (who feeds whom)
- `level_norms` (means) → ISO+, POW+ (perf core), HIT+, Stf+.
- ISO+ → POW+ (rawPerf). HR-rate+ → POW+.
- Tool grades (20–80) → POW+/HIT+/ToolDvM+ via `_toolToPlus` (and into FV upstream of the
  consensus system — **potential circularity:** tool grades inform FV, FV-DvM feeds DvM+,
  and tool grades also feed ToolDvM+ which feeds DvM+; to be quantified in Phase 1).
- SC+ → DvM+ (SC-DvM axis) and stands alone.
- FV history → FV-DvM → DvM+. Engine surplus → $DvM+. RPS+/Stf+ → breakout gates (not FV).
- WAG ← career WAR + FV (one-way today; no feedback to FV→WAR).

## Open items to confirm before Phase 1 sign-off
1. The **main-pipeline MMiLB `rps_plus`** exact composite + scale (×10 vs ×15) — pin the
   upstream computation site.
2. Whether any **park factor** exists anywhere (none found in the rate-+ paths).
3. Exact **missing-data handling** in SC+/zone when tracking is absent at a level
   (dropped vs imputed) — partially visible (components drop out), to be confirmed end-to-end.
4. The **FV-DvM** baseline window + whether it shares variance with ToolDvM+/$DvM+.

---

# Phase 1 — Statistical audit (empirical, ranked by distortion)

Open items closed: **(1)** active-MiLB `rps_plus` is NOT computed — 0 of 2,015 actives
carry it; it exists only for draft (`100+15z(college perf)`) and overseas (cohort z).
The real park+league-adjusted hitter index for actives is **wRC+ ingested from
FanGraphs** (`stats.py` `wRcPlus`), unbranded. **(2)** No park factor exists anywhere
in the rate-+ paths (confirmed). **(3)** Missing Statcast → components drop out and the
z-average renormalizes over present ones (mean-imputation-like, not zero-fill);
coverage is 582/2,015 (29%).

Findings, ranked by how much they distort the numbers:

1. **Additive stacking of near-redundant components (POW+/HIT+).** Empirically,
   ISO+ vs HR-rate+ correlate **r = 0.91** across active hitters — the two halves of
   the POW+ performance core (0.6·ISO+ + 0.4·HR-rate+) are nearly the same measurement.
   perf vs Statcast-power r = 0.45, perf vs power-tool r = 0.36. Additively summing
   four correlated power signals produces overconfident, variance-shrunk, inflated
   readings. This is the largest precision defect.
2. **Baseline population ≠ comparison population; no park.** Active-pool ISO+ mean is
   **111.4** (median 106.5), not 100 — because the baseline is *all* players at the
   level while the readers interpret it as "vs the average prospect," and prospects are
   a positively-selected subset. Combined with **zero park adjustment** (MiLB park
   effects on power are large, esp. PCL), the level-relative ratio is biased and
   context-contaminated.
3. **No sample-size regression (frontend ratio metrics).** Structurally there is only a
   20-game gate, then full value clamped to [0,250]. 288 active hitters under 120 AB
   span ISO+ 19–250 unregressed; a hot 60-AB stretch posts a high POW+. (The backend
   z-metrics DvM+/Stf+ already shrink small-n; the ratio metrics do not.)
4. **Tool→stat map is not outcome-calibrated.** Assumed `100+(grade−50)·2` vs observed
   mean ISO+ by power grade: 40→80 assumed / **97 observed**; 50→100 / **115**; 60→120 /
   **124**; 65→130 / **157**. The linear map mis-scales the tool contribution (too low at
   the bottom, too compressed at the top). (Observed is selection-confounded, but the
   divergence is unambiguous.)
5. **Weak out-of-sample validity.** final-MiLB ISO+ predicts MLB ISO at **r = 0.24**
   (n = 171 graduates) — low for a metric whose entire purpose is to forecast MLB power.
   This is the headline "is it precise" number and the Phase 3 improvement target.
6. **Scale-convention inconsistency.** Ratio (POW+/HIT+/ISO+, 1 pt = 1%), z×10
   (RPS+/DvM+/ToolDvM+/$DvM+, 1 pt = 0.1σ), z×15 (SC+, RPS+-draft). "1 point = 1%" is
   only literally true for the ratio family; the guardrail paradigm is not uniformly met.
7. **Statcast baselines are pool-anchored, not level-anchored**, and are blended with
   level-anchored performance inside the same POW+/HIT+ sum (mixed reference frames).
8. **WAG vs surplus FV→WAR mismatch, loop open.** WAG measures error against
   `_fv_to_expected_war_per_yr`; the surplus that feeds $DvM+ uses `fv_to_6yr_avg_war`;
   no feedback writes WAG's measured error back into either curve.
9. **Circularity (to quantify in fix design).** Tool grades inform FV; FV-growth →
   FV-DvM → DvM+; tool grades also → ToolDvM+ → DvM+ — shared signal enters DvM+ twice.

Recommended Phase 2 direction (for approval): empirical-Bayes shrinkage with
stat-specific stabilization points on the ratio metrics; regressed MiLB park factors +
keep level baselines; reliability-weighted dynamic blend (tool prior when PA thin →
stats/Statcast as PA accrue) replacing fixed 0.45/0.25/0.30; collinearity-aware
combination (don't sum ISO+ and HR-rate+ at r=0.91 — pick one or shrink for shared
variance); outcome-calibrated grade→+ map; one scale convention; reconcile the two
FV→WAR curves and close the WAG loop; resolve/brand RPS+ (lean on wRC+).

---

# Phase 2/3 — Implemented (frontend ratio metrics) + backtest

Scope this pass: the precision-critical frontend ratio metrics POW+, HIT+, ISO+
(findings 1, 3, and the reliability-weighted-blend recommendation). These are computed
live from statlines in `prospx/index.html` — **no historical snapshot stores them**, so
changing them mutates no snapshotted history (the Phase-3 recompute decision applies only
to backend snapshotted metrics, untouched here).

Changes:
- **Empirical-Bayes shrinkage** (`_ebShrinkPlus`): ratio metrics shrink toward the level
  average (100) by sample reliability `AB/(AB+k)`, stat-specific `k` (ISO 150 PA, HIT
  perf 170 PA). Standalone ISO+ is now shrunk; a 40-AB hot streak no longer posts an
  extreme value.
- **Reliability-weighted blend** (`_blendPlus3Rel`) replaces the fixed 0.45/0.25/0.30:
  the scouting tool grade is the prior (full base weight); the performance and Statcast
  observations are down-weighted by their own sample reliability (`AB/(AB+k)`,
  `BBE/(BBE+40)`, `pitches/(pitches+200)`). Thin samples lean on the prior; full seasons
  lean on observed performance.
- **Collinearity fix (POW+):** the performance signal is **ISO+ alone**. ISO+ and HR-rate+
  correlate r=0.91 across active hitters; the old `0.6·ISO+ + 0.4·HR-rate+` summed one
  latent trait twice and inflated the spread. (HIT+ keeps AVG + K%-avoidance — distinct,
  not as collinear.)

**Backtest (n≈158 graduates, predictive corr vs MLB ISO):**
| metric | old r | new r |
|---|---|---|
| ISO+ (raw → shrunk) | +0.21 | **+0.25** |
| **POW+ full (reliability-weighted)** | +0.35 | **+0.50** |

POW+ predictive correlation improved **0.35 → 0.50** (+43% relative). The gain comes from
leaning on the scouting prior when samples are thin; the collinearity fix is roughly
prediction-neutral but removes inflated magnitude. Glossary/tooltip formulas updated.

## Methodology changelog
- **Arkmetric audit v1** — POW+/HIT+/ISO+: added empirical-Bayes small-sample shrinkage;
  replaced fixed blend weights with reliability-weighted blending (tool grade as the prior
  when PA are thin); removed the ISO+/HR-rate+ double-count in POW+ (r=0.91). Backtested
  POW+→MLB-ISO 0.35→0.50. Live-computed (no snapshot recompute).

## Deferred (scoped, not done this pass — for a later checkpoint)
- **Regressed MiLB park factors** (finding 2): needs a park run-environment source; the
  level baseline stands in the meantime. Pool-vs-100 bias (active ISO+ mean 111) noted.
- **Outcome-calibrated grade→+ map** (finding 4): needs clean out-of-sample grade→MLB
  outcome data; the reliability blend already reduces reliance on the assumed linear map.
- **Backend items** (6–9): scale-convention harmonization (z×10 vs z×15), the WAG↔surplus
  FV→WAR reconciliation + feedback loop, and the DvM+ circularity — these touch the
  just-recalibrated surplus/farm engine and the snapshotted DvM+ history, so they are
  gated behind the Phase-3 historical-recompute decision and a dedicated change.
- **RPS+ resolution:** brand/standardize on the park+league-adjusted wRC+ that already
  exists for actives (RPS+ is unpopulated for 0/2,015 actives).

## Historical-recompute decision (for your call — nothing changed yet)
The frontend metrics changed here are **not snapshotted**, so there is nothing to
recompute for them. The decision applies only when the backend snapshotted metrics
(DvM+ trajectory) are changed in a later pass — options then: (A) recompute history under
the new formula (consistent charts, but rewrites stored snapshots) vs (B) splice at the
change date (preserves the audit trail, visible discontinuity). Awaiting your call before
any backend snapshot change.
