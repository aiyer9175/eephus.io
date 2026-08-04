# xFV — Phase 1: discovery, data verdict, and model spec (for sign-off)

Status: **Phase 1 deliverable. No model has been built.** Methodology needs explicit sign-off
before any code. Numbers below were measured directly against `prospects.db`, `debuts.json`,
`inactive.json`, `timeseries.json`, the consensus/value engines, and a leakage-safe
correlation sweep on the resolved cohort (3,786 player-rows). Voice: plain, honest about
what the data does and does not support.

---

## 0. The one-paragraph verdict

We have a genuinely usable labeled sample (~1,500 leakage-clean debuted prospects with a
pre-debut FV, plus ~2,000 confirmed busts) and a strong existing surplus/calibration engine
to feed. But the empirical sweep says the hard thing out loud: **consensus FV is the single
best predictor of realized WAR (Spearman 0.38 hitters / 0.25 pitchers), and nothing we hold
beats it.** The closest prior model (`prospect_path`) already tried and lost on rank. The
honest headroom over consensus is small and lives in exactly three places: (1) the
hit-tool + on-base/contact translation that scouts under-weight, (2) strikeout-rate
translation for pitchers, and (3) a *correction* of the power over-pricing scouts build into
FV. So xFV should be built as **consensus-FV-as-prior plus outcome-grounded adjustments**,
and its flagship case rests primarily on the **calibrated distribution, the uncertainty band,
and the surplus output** — not on a blanket claim of beating consensus on ranking. We design
to that truth.

---

## 1. Step 1 — Discovery and the data verdict

### 1.1 The labeled target (what we can actually train on)

| Slice | N | Source |
|---|---|---|
| Graduated/debuted prospects with realized bWAR | 1,756 (1,668 nonzero) | `career_war` table / `debuts.json` |
| ...with a prior consensus FV snapshot (pairs) | 1,754 | snapshots ∩ career_war |
| ...**leakage-clean** (FV snapshot strictly before debut) | **1,501** | per-player MIN(snapshot_date < debut_date) |
| Confirmed busts (tracked, never reached MLB, WAR≈0) | ~2,031 | `inactive.json` |
| **Full labeled ceiling** (debuted + busts, all carry prior FV) | **~3,785** | union |
| Fully-resolved 6-yr cohort (2017–2020 entry) | 2,684 | `empirical_anchors` window |

- **Target = bWAR only** (bbref; site-wide owner convention). Primary label: **first-6-MLB-season
  summed bWAR, bust-inclusive (never-MLB = 0)** — the same construct `empirical_anchors.py`
  already uses. Secondaries (career bWAR, WAR/yr) rank-order almost identically.
- **Right-censoring is real:** median debuted player has 3 career seasons; 2022+ debut cohorts
  have incomplete 6-yr windows. Must be handled (restrict to resolved vintages, or KM-style).
- **Top tiers are unlearnable from data:** in the resolved cohort, FV60 n=21, FV65 n=9,
  FV70 n=2, FV80 n=0. Star-tier behavior must be anchored to the public/reference scale
  (as `empirical_anchors` already does via public-reference blending), not learned.
- Empirical bust% by tier (the consensus-implied curve to beat): FV40 86%, 45 81%, 50 52%,
  55 42%, 60 19%.

**This is a small-to-medium, outcome-sparse-at-the-top sample. It dictates a regularized,
shrinkage-heavy, prior-anchored model — not a flexible/deep one.**

### 1.2 The Statcast-vs-outcomes tension (quantified, and it is severe)

- **Every Statcast / zone / Arkmetric table in the DB is 2026-only and overwritten each run.**
  `metric_snapshots` (the only point-in-time derived store) has **15 days** of history. There
  is **no historical Statcast** to attach to resolved prospects.
- **Structural coverage hole:** AA and A+ have **zero** batted-ball and **zero** pitch-tracking
  rows. EV/barrel exist only at AAA+MLB (and thin A/CPX). Plate-discipline (zone whiff/chase/
  z-contact) reaches down to A/CPX. **No sprint speed and no arm velocity exist anywhere.**
  Swing+ is MLB-2024+ only (155 players).
- **The resolved×Statcast overlap is tiny:** ~99 debut-pairs with usable pre-debut AAA
  Statcast; the forward-validation cohorts are n≈49 hitters / 50 pitchers (rate outcomes),
  ~100 (2-yr WAR). You cannot train a primary model on that.
- **Verdict on Statcast:** it is a **current-state, upper-level-only, low-weight, optional**
  feature with an explicit missingness indicator — never the backbone, and never reconstructable
  historically. This kills the "modern Statcast layer trained on resolved outcomes" idea at
  scale; the realistic version is a thin, provisional overlay (see §2.C two-tier plan).

### 1.3 What the empirical sweep found (the decisive part)

Two leakage-safe analyses on real data. **A:** every feature vs realized bWAR on the resolved
set, with a rank-partial that removes consensus FV (does it add signal *beyond* FV?). **B:**
every current-board feature vs consensus FV (what scouts already price in). Cross them:
an xFV *edge* = adds WAR signal beyond FV (A) **and** is under-priced by scouts (B).

**Headline: consensus FV is king and is not beaten by any single feature.**
- FV → career bWAR: hitters Spearman **0.379**, pitchers **0.252**, all-types 0.319,
  full-pool (busts=0) 0.229. (Beats `prospect_path`'s FV-only 0.21 on this larger/cleaner cut.)
- Per-source FVs, signing bonus, and draft pick all have partial-given-FV ≈ 0 — **already
  priced into FV.**

**The only features that ADD signal beyond FV (rank-partial | FV):**

| Hitters | partial vs WAR | priced into FV? (Analysis B) | read |
|---|---|---|---|
| peak-MiLB OBP | **+0.16** | barely (0.10) | **edge — under-priced discipline** |
| peak-MiLB K% | **−0.14** | barely (−0.04) | **edge — under-priced contact** |
| HIT tool | **+0.14** | moderate (0.23) | **edge — best single tool for WAR** |
| peak-MiLB OPS | +0.13 | low (0.16) | edge (collinear w/ OBP) |
| raw_pwr / game_pwr tool | **−0.14 / −0.12** | **highest priced (0.27/0.30)** | **TRAP — power over-priced** |
| ISO / ISO+ | +0.02 / +0.03 | low (0.15) | power predicts power, not WAR |
| fv_spread / fv_stddev (disagreement) | **~0.00** | n/a | **dead — no outcome signal** |

| Pitchers | partial vs WAR | priced into FV? | read |
|---|---|---|---|
| peak-MiLB K% | **+0.17** | low (0.10) | **edge — under-priced** |
| peak-MiLB K/9 | **+0.15** | low (0.06) | **edge** |
| peak-MiLB ERA | **−0.13** | low (−0.06) | edge |
| fastball tool | +0.10 | low (0.10) | modest |
| command tool | ~0.01 | **highest priced (0.29)** | scouts over-weight cmd for WAR |
| disagreement | ~0.00–0.06 | n/a | **dead** |

**Four conclusions that reshape the brief's feature plan:**
1. **The edge is stat-translation of plate discipline / contact / K-rate**, which scouts
   demonstrably under-weight (current production is near-orthogonal to FV: hitter ISO/OPS ≈
   0.15, K%/BB% ≈ 0; pitcher ERA/K9 ≈ 0.06). This is xFV's real lever.
2. **Power is a trap.** It is the top-priced hitter tool (game_pwr 0.30) yet anti-signal for
   *incremental* WAR (partial −0.12 to −0.14), even though it cleanly predicts MLB ISO
   (0.47–0.51). xFV's biggest *correction* of consensus may be **down-weighting power**, not
   adding a new signal. A "POW+" composite would not help xFV; a "HIT+" composite (hit tool +
   OBP + contact) would.
3. **Scout disagreement carries no outcome signal** (Spearman ≈ 0, partial ≈ 0, doesn't
   predict busts or variance). The brief proposed it as both an uncertainty feature and a
   tie-breaker; the data supports neither as a *mean-shifting* feature. Keep it, if at all,
   only as a candidate variance-width input — and even that is unproven here.
4. **Statcast is barely priced into FV and barely predicts WAR where we can test it.** It is a
   small, level-gated, current-state nicety, not a backbone.

(Open flag: the sweep's reconstructed ISO+ → MLB-ISO came in at ~0.49–0.51 vs the
`arkmetric-audit.md` figure of 0.24. Both are internally consistent; likely a different
sample/level gate. It does not change any conclusion — ISO+ predicts ISO, not WAR — but worth
reconciling when we touch the power-tool xFV.)

### 1.4 The model tier the data supports

**Tier: a calibrated, prior-anchored, shrinkage-heavy distributional model — "prospect_path v2."**
Not a deep model, not a strong-rank-beating claim. Concretely:
- Consensus FV (raw) is the **prior backbone**; the model predicts an **adjustment** toward
  realized outcomes from a small set of earned features (discipline/contact translation, hit
  tool, K-rate, power-correction), with hard regularization and partial pooling.
- Output is a **5-bucket outcome distribution** (the existing engine's representation), summarized
  to an FV grade with an uncertainty band, and fed to the surplus engine.
- **The flagship case is the distribution + uncertainty + surplus + the power correction +
  the as-of-time trajectory** — because matching/beating consensus on rank is not well
  supported, and we say so on the methodology page.

---

## 2. Step 2 — The model spec (propose for sign-off)

### A. Target and training set
- **Predict** P(bucket) over [bust, bench, regular, good, star] (the engine's existing
  `p_bucket_given_fv` representation). One predicted distribution → two outputs (the FV grade
  via inversion; the surplus via the engine), no double-counting.
- **Primary label:** first-6-season summed bWAR, bust-inclusive, mapped to the 5 buckets by the
  existing thresholds. **Train set:** `debuts.json` (1,501 leakage-clean) ∪ `inactive.json`
  busts (≈2,031, outcome 0) — never `career_war` alone (survivorship). Mirror
  `source_backtest.py`: preseason cohorts, undebuted=0, MIN_LAG≥3, rate outcomes for censoring.
- **Censoring (DECIDED — KM from the start):** use Kaplan-Meier-style censoring (as `eta.py`
  already does) to include the 2021–2023 cohorts alongside the fully-resolved 2017–2020 set,
  rather than restricting to resolved-only. Pass 1 builds censoring-aware labels: a prospect with
  an incomplete 6-yr window contributes its observed-to-date WAR with a censoring weight, not a
  hard 0; busts that have aged out (median never-debuted age 27.7) resolve to 0. This is the
  ambitious choice and it adds modeling assumptions about incomplete outcomes — we validate the
  censoring treatment explicitly (sensitivity vs the resolved-only cut).

### B. Features — re-tiered by what the data earned (not the wish list)
Build **as-of the decision point**, strictly pre-date, from the `snapshots` table; recompute
age from `birth_date`; freeze level-norm vintage (the default `date.today()` window leaks).

- **Tier 1 (backbone, fully as-of-reconstructable, full history):**
  consensus_fv_raw (prior), per-source FV (FG + MLB Pipeline), the **HIT tool** + full tool
  vector, **translated production** via `level_norms.compute_level_norms` + the storage
  EB-shrink (ops_plus_level / era_minus_level, and the rate slate: **OBP, K%, BB%, K-BB%** for
  hitters; **K%, K/9, BB/9, ERA-** for pitchers), **age-relative-to-level** (re-derived clean
  from birth_date + contemporaneous norms — the leaky current-state version must be rebuilt),
  position, height/weight/handedness (~89%), draft **pick_overall** (raw, leak-free) + slot,
  signing bonus (signed-conditional, missingness-flagged), injury history from `il_history`/
  `roster_status.injury_history` anchored to the decision date.
- **Tier 2 (provisional overlay, current-state only, level-gated, low weight):**
  pitch-physics **Stuff+** (pitchers; real OOS r=0.28 — the strongest modern signal we have),
  contact quality (EV/HH/barrel, AAA+MLB only), plate-discipline (zone whiff/chase/z-contact,
  down to A), SC+. All with sample-size shrinkage and explicit missingness indicators. **No
  historical reconstruction** — used for live scoring of upper-level prospects, validated on the
  ~99-pair forward cohort, flagged provisional.
- **Demote / drop (data-driven):** scout disagreement (no outcome signal — keep only as a
  candidate variance input, not a mean feature); raw power/ISO as a *positive* WAR driver
  (model it for the power-tool xFV, but let the WAR-anchored overall down-weight it); WAG/DvM+/
  $DvM+/realized_implied_fv as inputs (outcome-derived — leakage); Swing+ as a prospect feature
  (MLB-only).
- **Engineering that matters most (per the data):** the contact/discipline translation, the
  clean age-vs-level interaction, and treating the **hit tool ≠ power tool** asymmetry. Heavy
  missingness handling (impute + indicator), especially tools and Tier-2.

### C. Architecture (sklearn + lightgbm only — no pymc/scipy/xgboost/statsmodels)
A small ensemble, prior-anchored, with the FV-only model as the baseline to beat:
1. **Prior-anchored cumulative-link core** (extends `value_framework`'s proportional-odds
   `p_bucket_given_fv`): FV is the dominant term; the earned features enter as **regularized
   adjustments** with **monotone constraints** (younger-for-level, higher K-BB%, higher OBP,
   higher hit tool never lower the prediction; higher K% never raises it). Hand-rolled
   **empirical-Bayes / partial pooling by (level × archetype)** stands in for the unavailable
   pymc hierarchical layer — thin cells shrink to the FV prior.
2. **Monotone LightGBM challenger** on the full feature set (heavily regularized; the prior-art
   LightGBM already lost on rank, so it is a challenger, not the default), to catch nonlinearity
   and interactions the linear core misses.
3. **k-NN comp model** (interpretable; also the "nearest historical comps" UI feature and a
   sanity check).
Blend by out-of-fold performance; shrink the GBM toward the core hard. Separate hitter and
pitcher models; SP/RP handled in the bucket/outcome mapping (relievers cap lower).

### D. Tool xFVs
Each tool predicts the **realized stat it is supposed to forecast**, grounded where data exists:
hit → MLB contact/OBP; **power → MLB ISO (works: 0.50–0.56)**; speed → sprint/steals; field/arm
→ what little we have. Crucial asymmetry from §1.3: tool xFVs feed the overall as informative
features, but the overall stays **anchored to realized WAR**, which *automatically* down-weights
power relative to consensus. Pitchers: each pitch from velo/movement/whiff where Tier-2 covers,
command from walk/location — provisional, upper-level only.

### E. Backtesting
- **Headline:** xFV vs consensus FV out of sample on realized value. Report rank agreement
  (Spearman), top-N hit rates, distributional proper scores (log loss, Brier, CRPS-style),
  PIT/coverage, and the **decision metric** (value/surplus captured ranking by xFV vs consensus).
- **Out of time, no leakage:** forward-chain (train on < Y), leave-one-year/class-out where depth
  is thin, strictly pre-decision features, busts kept at 0. **Start from `prospect_path.py`'s
  harness** (cohort builder, as-of FV vintage, dual MAE+Spearman gate, forward-chaining) — reuse
  the hand-rolled `_spearman/_auc/_rankdata`.
- **Bar (and the honest fallback):** beat FV-only on **both MAE and Spearman** to claim a rank
  win. If it ties rank (the likely outcome), it earns flagship only through calibration +
  distribution + uncertainty + surplus, **and we state that plainly** (registry verdict +
  glossary). A miscalibrated headline grade is sev-1.

### F. Calibration
- Out-of-fold **isotonic** on the bucket probabilities and on the surplus (reuse
  `backtest.fit_isotonic` / `fit_isotonic_binned`; never per-player PAVA at the zero-heavy
  bottom). Reliability diagrams overall, per bucket, per FV tier; recenter mean only; do **not**
  double-correct a value the downstream engine already calibrates.
- **Calibrate the surplus distribution too**, not just the grade (reuse `sv_credible_interval`).
- **Feedback loop:** as cohorts resolve, refit/recalibrate and surface the track record (extends
  the existing source-calibration loop). Eval artifact is public, so losses are published honestly.

### G. The brief's accuracy ideas — accepted / modified / rejected with reasons
- **Ground in realized outcomes, not consensus** — ✅ core of the design.
- **Translate before modeling** — ✅ high value; the discipline/contact translation IS the edge.
- **Age-relative-to-level first-class** — ✅, but the stored version is leaky; must rebuild clean.
- **Disagreement as signal/uncertainty** — ⚠️ **rejected as a mean feature** (zero outcome signal
  in the data); retained only as a candidate variance-width input, unproven.
- **Two-tier / proxy targets for Statcast** — �ðŸ”„ **modified:** no historical Statcast exists, so
  the "modern layer trained on resolved outcomes" is infeasible at scale; replaced by a thin
  current-state Tier-2 overlay + optional faster-resolving proxy targets (reach-AAA, first-MLB
  K%/ISO) for recent cohorts as auxiliary signals only.
- **Hierarchical shrinkage** — ✅, hand-rolled empirical-Bayes (no pymc).
- **As-of-time trajectory** — ✅ (coarse/seasonal pre-2026; design for irregular spacing).
- **Durability as distribution shift** — ✅ from `il_history`, anchored to the decision date.
- **Ensemble + validate on surplus** — ✅.
- **Regress Statcast for sample; censoring as real outcomes** — ✅.

### H. Integration and rollout
- xFV becomes the flagship grade + ranking source **only if** it clears its bar (or the agreed
  distribution/surplus fallback). Consensus FV stays on the prospect page as reference +
  comparison ("our grade vs consensus, and where they differ"); consensus tool grades stay
  beside our tool xFVs.
- **Surplus seam:** add a thin shim — `surplus = Σ_b probs[b]·_effective_bucket_sv[b]` →
  `apply_calibration()` — reusing the engine internals; do **not** reimplement $/WAR. **Invert**
  distribution → FV by bisecting `p_bucket_given_fv`. Mirror the `sv_distribution` output contract
  so xFV drops into every existing surface.
- **Pitchers:** fix the broken `is_pitcher` (all 0) before any pitcher $ claim; flag pitcher
  surplus provisional until validated.
- **Live rankings:** fold the (thin, 2026-only, ~136-player) TJStats stream in as one source,
  then retire the surface. Fold first, then remove.
- **Governance:** add a `model_registry.json` row (provisional until a committed forward-chained
  artifact beats the named FV-only baseline); add `test_methodology_freshness` glossary entry
  (≥80 chars) or the suite fails; write the honest glossary methodology (what goes in, what it
  predicts, how calibrated, how confident).

---

## 3. Step 3 — Execution sequence (approve one pass at a time)

- **Pass 1 — Training set + data verdict lock.** Assemble the leakage-clean as-of feature
  matrix (snapshots-based, hitters) + **KM-censored labels** (2017–2020 resolved + 2021–2023
  censored, per §2.A); freeze level-norm vintages; reproduce the FV-only baseline
  (Spearman ~0.38) as the bar; sensitivity check censored vs resolved-only; commit
  `data/xfv_eval.json` skeleton. Deliverable: the matrix + baseline + honest sample report. **No model.**
- **Pass 2 — Hitter model.** Prior-anchored core + monotone GBM challenger + comps; OOS
  forward-chained; report vs consensus honestly (including losses).
- **Pass 3 — Calibration + uncertainty + surplus seam.** Isotonic out-of-fold; reliability
  diagrams; the vector→surplus shim; distribution→FV inversion; censored-cohort extension.
- **Pass 4 — Pitcher model** (fix `is_pitcher` first) + Tier-2 Statcast overlay (provisional).
- **Pass 5 — Tool xFVs.**
- **Pass 6 — Integration, glossary, registry, live-rankings retirement.**
Each pass: show results + validation honestly, re-verify every number, keep changes reversible,
build no component before its method is approved.

---

## 4. Decisions — RESOLVED 2026-06-21 (owner sign-off)

1. **Flagship bar:** ✅ **Tie rank + add distribution/surplus.** xFV becomes flagship if it
   *matches* consensus on out-of-sample rank and adds the calibrated distribution, uncertainty
   band, surplus, and the power-overpricing correction — stated plainly on the methodology page.
   A rank win is a bonus, not the gate.
2. **First-build scope:** ✅ **Hitters first**, pitchers in a later pass (after fixing the broken
   `is_pitcher` flag).
3. **Censoring / cohort:** ✅ **KM-censoring from the start** — include 2021–2023 cohorts with
   Kaplan-Meier censoring (per §2.A), not resolved-only. The ambitious choice; validate the
   censoring treatment vs the resolved-only cut.
4. **Tier-2 Statcast overlay:** ✅ **Backbone first, overlay later.**
5. **Begin Pass 1?** — awaiting the explicit green light (Pass 1 = training-set + feature-matrix
   assembly + baseline reproduction; **still no model**).

---

## Execution log (Phase 2) — Passes 1-6 complete, 2026-06-21

- **Pass 1 (training set):** `xfv_dataset.py` (side-aware), leakage verified zero, KM-censored 6yr bWAR labels, FV-only baseline reproduced.
- **MLB Pipeline 2011-2016 ingest + WAR backfill:** boards extended to 2011 in `scrapers.py`; 1,294 new players matched to MLBAM ids from cached Apollo JSON; bbref WAR backfilled (812 debuted + 482 busts); marked debuts and ran `rebuild_only` so the cohort is in `debuts.json`/`inactive.json` site-wide. Debut window widened to 2011-2023 — the matrix now sources everyone directly (augment retired).
- **Pass 2 (models):** `xfv_model.py` (FV-prior ridge + monotone LightGBM + k-NN comps + LOFO calibration), forward-chained. Honest result on the full clean rebuild: hitters TIE consensus on rank; pitchers TRAIL consensus on rank. Losses committed in `data/xfv_eval.json` / `xfv_eval_pitcher.json`.
- **Pass 3 (distribution/surplus seam):** `xfv_score.py` — grade + 5-bucket distribution + surplus + uncertainty via the existing engine. Headline grade re-anchored to the 20-80 consensus scale (rank-preserving); the deflated realized grade drives surplus.
  - *CORRECTION 2026-08-04 (the line above is a dated record, kept as written):* the rank-preserving quantile map (`xfv_grade_display` / `xfv_grade_quantile`) STOPPED being the headline on 2026-07-25, when `storage.BOARD_GRADE_FIELD` moved to the raw `xfv_grade` and display, sort and `overall_rank` unified on one number. The quantile map is retained only as the SURPLUS-PRICING basis (the surplus and WAR-path curves were fitted on it). Anything still describing the displayed/headline eFV as "rank-mapped to the 20-80 scale" or as a rank-preserving map onto the consensus distribution is describing the retired field.
- **Surplus re-calibration:** anchor window widened to [2014,2020] (`value_framework_config.yaml`), refit + snapshot re-emitted; top tiers data-grounded; all surplus tests green ([2011,2020] was rejected for failing the FV60-65 smoothness gate).
- **Pass 4 (pitchers):** `is_pitcher` column fixed; pitcher matrix/model/score built. Consensus FV is the stronger pitcher predictor; xFV deflates pitcher surplus ~50% reflecting realized bust rates (flagged provisional).
- **Pass 5 (tool xFVs):** `xfv_tools.py` — grounded in realized MLB stats. Tool grades already strong (power->ISO 0.52); production adds beyond the grade mainly for fastball->K% (0.28->0.32). Field/arm/pitch-shapes pass through.
- **Pass 6 (integration):** consolidated `data/xfv.json` (4,055 players); glossary entries `xfv` + `xfv_tools`; `model_registry.json` rows `xfv_hitter`/`xfv_pitcher`/`xfv_tools` (all **provisional**, losses committed); `test_methodology_freshness` mappings added.

**Flagship-swap decision (deferred, deliberately):** xFV ties consensus on rank for hitters and trails for pitchers, so per the brief's own rule it has NOT earned the right to REPLACE consensus FV as the sole ranking source. It ships as a documented, first-class grade shown ALONGSIDE consensus (data + glossary + registry done); ripping consensus out of the prospx frontend headline is a gated deploy decision, not done here. Live rankings (TJStats) remain folded as one consensus source; UI retirement is part of that same deferred frontend step.
