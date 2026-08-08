# Master plan 2026-08-08: eFV conviction, measurement power, and the open driver frontier

**Status: PLAN, not executed.** Written 2026-08-08 against HEAD `82a13e37`, tree clean of
audit work (the 15 dirty `data/*.json` + baked HTML files predate this session; standing
rule: classify and revert churn, never commit it blind).

Owner ask, verbatim intent: *further improve eFV and our measurements for eFV as much as
possible, with a specific focus on developing new/improved drivers, giving eFV more
conviction vs the consensusFV basis, and making eFV as predictive for prospect future
value / WAR production as possible.*

Predecessor: `docs/master-plan-2026-08-07b-efv-audit.md` (executed, four waves, 12 of 24
lane headlines did not survive adversarial verification). This plan starts from that
program's verified end-state, which this session re-verified in the tree (three read-only
recon passes, 2026-08-08). Every number in section 1 was read from the current tree, not
from memory.

---

## 0. The frame: where accuracy can still come from

The flagship rank frontier is **measured closed on every axis tested**: feature
composition, target choice, objective choice, sample weighting (`EFV_GATE_STANDARD.md`
section 6; `data/xfv_rank_objective_eval.json` 20 of 20 cells fail, I2 loses on the very
AUC it was fit to; six driver arms null in `docs/efv-drivers-2026-08-07/GATE_RECORD.md`).
**This plan does not open a flagship feature hunt.** A blind feature session on this model
produces nulls by construction, because the published margins sit at 0.17x-0.84x of their
own floors.

What remains, ranked by expected value per unit of work:

1. **Measurement power (lane M1).** The eFV-vs-consensus common-set margin is +0.0297
   against a 0.0352 floor (0.84x) under the only estimator wired into the scoreboard
   (E_refit, which includes ridge refit variance that does not shrink with test n). The
   registered second instrument (E_cond, gate standard section 7) has floors 0.45x-0.71x
   as wide on the four cuts where it was derived, and it has **never been derived for the
   head-to-head, block-rho, feature-add, or lambda statistic classes**, nor wired into
   `source_backtest`. Deriving and wiring it is the cheapest way this program either
   certifies eFV's edge or certifies that it is not there. Both outcomes are conviction:
   a certified win upgrades the site's claim, a certified null keeps the honest tie, and
   a certified loss (one already exists: hit full_pool, section 1.2) gets published.
2. **Serve-path coherence (M2, R1).** The published accuracy does not describe the served
   board. Four grade bases coexist in production (display, odds, dollars, history), the
   odds basis is not exported at all, 75.19% of scored live rows sit at the FV20 knot, and
   the one measurement of served-vs-blend rank was left UNRESOLVED because it borrowed a
   floor from a different experiment. If the served grade genuinely ranks below `blend`,
   fixing the serve path is a certified accuracy win larger than any feature could buy,
   with zero model risk.
3. **The provisional model (M6).** It grades the largest population the site serves
   (5,993 scored, ~2,434 routed onto the board) and its gate says: certified win over the
   incumbent constant, **NULL against a `level_rank`-only dumb control** (B5, 0.921x
   floor). Its frontier was never audited and is genuinely open. This is where "new and
   improved drivers" can actually be developed and certified.
4. **Input integrity (M3, M4, M7, R3).** Consensus is eFV's dominant feature AND its
   baseline. It still carries one confirmed-material as-of leak (grade-normalization thin
   cells pool across future years: 58.12% of matrix rows move, mean +0.94 FV, worst folds
   2013-2015 at +3.7), one knowingly mis-typed board (2022 in-season FanGraphs, 1,272 org
   ranks read as global), unfitted shrinkage constants shaping most of the live board
   (D10), and a scoreboard that holds it to a softer standard than eFV (D5). Every one of
   these blurs the eFV-vs-consensus comparison in an unknown direction.
5. **The label, for the distribution chain (M5, R2).** The censoring projection is
   measurably biased pessimistic (hit n_obs=2 bias -1.691, CI95 [-2.091, -1.267]) and the
   flat-rate multiplier is already optimal in its family, so the RANK label stays. What is
   still broken is the distribution chain that consumes the label's LEVEL: the served
   outcome distribution is miscalibrated monotonically in tier, the recalibration was
   NO_SHIP because its gate was degenerate, and the incumbent bust-only Platt structurally
   cannot move tiers 55/60.
6. **New data, honestly bounded (R4, R5).** Almost every external-data lever has been
   tested and closed (section 2). What remains: two bounded, pre-registered tests on data
   already in-house, and the archival infrastructure that makes 2027-2029 drivers possible
   at all. There is currently NO dated archive of the underlying MiLB Statcast/Stuff+
   analog components; the DB tables are keyed to overwrite. Time is the only driver
   frontier that is provably open, and today we are not banking it.

---

## 1. State of the world (verified in-tree 2026-08-08)

> **EXECUTION HAS STARTED. Wave 0 ran 2026-08-08; record at
> `docs/efv-2026-08-08/WAVE0_RECORD.md`.** It refuted three items of P0.3, corrected R1's
> call-site count, lowered M4's expected value, answered M7a's drift question in the
> affirmative, and flagged M5 as adversarial rather than open. Read that record before
> acting on any lane below, because several numbers in this section are pre-regen.

### 1.1 Pools and basis

- Matrices (mtime 2026-08-07): hit 1,917 rows (1,535 resolved / 382 censored), pit 2,040
  (1,589 / 451). Censored total 833, observed_seasons 2-5. `RESOLVED_THROUGH = 2025` is
  already baked in; there is no free pool growth this cycle.
- `SCORED_YEARS` = 2014-2024 (11 folds), pair-weighted. Legacy 4-fold retired 2026-08-06.
- `anchor_constant_only` rows: 2,659 of 4,601 live (hit 1,121/2,136, pit 1,538/2,465).
- Baseball America ingested: 1,635 snapshot rows, 980 players, 4 preseason vintages
  2023-2026 (13 orgs) plus a 2026-06-03 Top 100. In consensus, NOT in `SCORED_SOURCES`
  (admitting it collapses the common set 4,284 -> 295 and flips `consensus_wins`).

### 1.2 Floors and current margins (the conviction scoreboard)

One-sided MDE95 throughout. E_refit = shipped estimator (train+test resampled, refit per
draw). E_cond = registered second instrument (fits held fixed), `data/xfv_power_eval.json`.

| cell | current margin | E_refit floor | E_cond floor | status |
|---|---|---|---|---|
| head-to-head common set (n 3,210) | +0.0297 | 0.0352 (0.84x) | **never derived** | null |
| block-rho model-vs-consensus (n 1,645) | +0.0121 | 0.0325 (0.37x) | **never derived** | null |
| hit debuted_km (n 755) | +0.0074 | 0.0445 | 0.0213 (0.35x) | null |
| pit debuted_km (n 890) | +0.0067 | 0.0425 | 0.0301 (0.22x) | null |
| pit full_pool_km (n 1,885) | +0.0157 | 0.0268 | 0.0218 (0.72x) | null |
| hit full_pool_km (n 1,792) | -0.0215 | 0.0289 (0.74x, null) | 0.0204 (**1.049x**) | **resolvable LOSS under E_cond**, p 0.0415, one-sided only |
| top20_capture curve_area (n 3,678) | -0.0081 | 0.0133 (0.61x) | 0.0084 (0.97x) | NULL, CLOSED (`xfv_cohort_floors.json` q4) |

`XFV_FULLPOOL_COND_MDE95 = 0.0204` exists in exactly one place, `POWER_GATE.md:362`, as an
unfulfilled request. Nothing in `source_backtest.py` publishes an E_cond floor.

### 1.3 The serve chain (from `efv_score.py:8-17`, verified accurate)

```
ridge E[6yr WAR] -> linear cal -> xfv_war
  -> vf.outcome_implied_fv(...)  = xfv_grade          <- the board number (BOARD_GRADE_FIELD)
  -> vf.realized_implied_fv(...) = _odds_grade        <- odds only; retired map; NOT exported
  -> p_bucket_given_fv + bust-only Platt              <- the published odds
  -> rank_war quantile           = xfv_grade_display  <- prices ALL dollars via _reprice_surplus_on_display
xfv_history / movement run on the quantile basis (a third live basis on user-facing charts)
```

- `_odds_grade` agreement with the exported `xfv_grade`: 76.8% below FV40, 1.6% in
  (40,45), **0.0% above FV45**. Nothing in `xfv.json` identifies the grade the published
  odds were computed on (`efv_export.py:44-63`).
- 3,319 of 4,414 scored live rows (75.19%) sit at the FV20 knot; 2,434 route to the
  provisional grade via `route_floor_grade` + `efv_ungraded._GRADE_MAP`, a map no eval in
  the flagship chain touches.
- The wave-3 served-vs-blend rank verdict is UNRESOLVED (borrowed floor, replayed per-fold
  calibration where production applies ONE pooled (a,b)). Under production calibration the
  served grade ranked BELOW `blend` on both sides in that replay.
- `data/xfv.json` is one regen behind (2026-08-06; `grade_basis` on 0 of 9,382 rows).

### 1.4 Open defects this plan owns (carried from the 08-07b ledger, all verified open)

| id | defect | where verified |
|---|---|---|
| D5 | per-source bars in-sample by admission; `consensus_wins` a bare unfloored `>=` (ties read true) | `source_backtest.py:526-531, :780-785, :941-951` |
| D6 | three grade bases on one card (odds / dollars / display), plus history on a fourth | serve chain above; owner decision |
| D7 | 71% of live rows below the outcome curve's data floor, priced off an explicit display re-spread | `value_framework.py` `_LOWEND_FG_EXP` |
| D8 | `xfv_grade_display` is pool-relative; a player's grade and price move when others move; never measured | Lane G never named it |
| D10 | `SINGLE_SOURCE_K=0.5` / `SINGLE_SOURCE_PRIOR=35` never fitted; fires on most of the live board, ~1% of the backtest window | `consensus.py:166-167, :1027-1039` |
| D16 | same-name merges reach the training matrix (carlos_sanchez cluster; 23 unjoined matrix rows; `_SAME_NAME_NOT_DUPES` empty) | `CONSENSUS_REPAIR.md` 8.5 |
| C-4 | grade-norm thin cells pool across FUTURE years; 58.12% of matrix rows move, mean +0.94 FV; BLOCKED on the pre-2017 FanGraphs reference gap | `grade_normalization.py:112-132, :227-295`; `CONSENSUS_REPAIR.md` 6 |
| - | 2022 in-season FG board (1,288 rows): fingerprint 0.8667 vs the 0.90 bar, refused, ~1,272 org ranks feed `implied_fv_from_rank` as global | `consensus.py:150, :541`; `consensus_rank_eval.json` posthoc |
| - | `players.org` carries 1,144 non-canonical values reaching 3,786 snapshot rows | 08-07b execution record |
| - | D3 miscalibration stands UNREPAIRED (recal was NO_SHIP; tripwire 0.10 sits above the 0.079 defect); per-tier gap .020/.042/.054/.051/.072/.122 | `xfv_dist_recalibration_eval.json`, `efv_reliability.py:118` |
| - | provisional model B5: NULL vs `level_rank`-only control; labeled pool 34.1% AA / 2.6% DSL vs served 34.7% DSL / 10.9% AA | `xfv_ungraded_eval.json` |
| - | pitcher provisional serve decision owed (two estimators disagree: 0.854x refit / 1.312x conditional) | 08-07b wave 3 |

Hygiene-grade (fix in wave 0, no gate needed): `xfv_eval.json` `honest_note` still claims
"BEAT consensus on both cuts" while its own full_pool block records the loss; `block_rho:
null` in both eval artifacts (scoreboard recomputes live); no consensus-flag provenance
(`ASOF_FV_INSTANCES` etc.) stamped into `timeseries.json` meta; curve_area floor not
attached to the scoreboard weak_cell; `tools/efv_oldcohort_id_resolve.py:76` writes
`data/` while its reader reads `data/sources/`; several artifacts carry bare date strings
with no `produced_by`; the consolidated D1-D20 verdict list required by the 08-07b
definition of done was never written; `_WAG_LAMBDA_IS_ASOF = False` publishes a
future-contaminated diagnostic into eval artifacts (inert while lambdas are pinned, one
word from live).

### 1.5 Lambda state (for M1's pre-registered cell)

`_BLEND_LAMBDA_RESELECT = {"hit": 0.70, "pit": 0.57}`, both pinned. The selector's own
argmax is **0.51 on both sides**, recorded in the shipped artifacts
(`shipped_equals_selected: false`; hit composite 0.7483 shipped vs 0.7922 selected).
Note the direction: the selector prefers MORE consensus weight, not less. "Conviction"
means certifying the right lambda, not raising it.

---

## 2. The closed ledger (binding; reopening any of these requires NEW data, not re-analysis)

| lane | verdict | record |
|---|---|---|
| Flagship feature composition, target transform, objective, sample weighting | closed, 20/20 cells fail | `xfv_rank_objective_eval.json`, gate standard s6 |
| Six driver arms (sb_rate, is_lhp, bats-side, gated pairs, elite band, wRC+) | all null | `docs/efv-drivers-2026-08-07/GATE_RECORD.md` |
| Elite-band (FV55+) discrimination | unanswerable, 10x-25x underpowered | same |
| Consensus recency decay | null; degenerate arm 6.8x WORSE, so the motivating prior is backwards | `consensus_recency_eval.json` |
| consensusRank (lane J) | **J1 ran 2026-08-07: NULL / FAIL** by pre-registered clauses (FG global gamma -0.010 p 0.690; MLBP global +0.093 p 0.008 but the two-segment sign clause failed); sizing premise false (92.0% of FG ranked rows are ORG ranks) | `consensus_rank_eval.json`, `CONSENSUS_RANK_GATE.md` |
| Label replacement (per-season-share shape) | NULL; worse in all 8 cells; out-of-cohort multiplier 2.74-3.15 brackets the shipped 3.000 | `xfv_label_replacement_eval.json` |
| Surrogate labels (hitter + pitcher), pitcher long-horizon | closed; "headroom" was a measurement artifact (constant control scored 87%) | `PITCHER_LABEL_LEDGER.md` |
| MiLB deep backfill (2005-2013) | no-ship, model regressed; only pre-registered revival is the SYMMETRIC id variant (R4c below) | data-sourcing runbook 2026-07-24 |
| TJ history as standalone feature | no-ship; survival-labeling use only | same |
| Peak-WAR training target | keep cumulative; eFV already ranks peak better | `efv_peak_war_lab` |
| ETA / level-weighting / AA columns / age-x-level / decimal age / SP-RP split / K-BB explicit / level-jump / draft-slot + bonus / fv_trend / iso_rel / scout disagreement | all rejected OOS | registry notes, sessions 2-6 |
| Statcast into /projections/ | rejected | standing memory + registry |
| eFV tail fixes (high end) | committed loss; rank-invariant by construction | registry notes 2026-06-25 |
| Feature pruning | out-of-fold negative at every depth | gate standard s6 |
| BA into `SCORED_SOURCES` | forbidden; collapses common set 4,284 -> 295, flips `consensus_wins` | `ba_source_class_eval.json` |
| BA per-tool consensus weighting | equal weight retains on all 11 tool keys | `TOOL_GRADE_WEIGHT_VERIFICATION.md` |
| Drop-off shrink FITTING (old D-4) | dead as written; the shrink never fired in production (0 legacy slugs in 54,061 snapshots) | `CONSENSUS_REPAIR.md` |
| Pooled bust ECE as a recalibration gate | degenerate; a zero-information constant reaches 152.7% of the candidate's gain | `xfv_dist_recalibration_eval.json` |
| curve_area value-capture deficit | NULL, closed, floored both estimators | `xfv_cohort_floors.json` q4 |
| K-prior; outlet accuracy re-weighting | closed permanently / reverted 2026-07-25 | standing memory |

---

## 3. Process rules (binding on every lane; violations burned prior sessions)

1. **Three adversarial verifiers per lane before any headline is committed.** 12 of 24
   lane headlines in the predecessor did not survive verification; the arithmetic was
   almost always right and the INTERPRETATION wrong. Never commit on a lane headline
   before its verification finishes (that exact failure shipped -$0.117M into the gate
   standard and had to be retracted two commits later).
2. **Pre-register J1-style**: gate doc first, PASS clauses and a literal result
   placeholder, then the lab. A threshold added mid-lane that flips the verdict must be
   disclosed in the headline. Watch for vacuous PASS clauses (empty set, f(X)==f(X),
   an arm that cannot fail, guaranteed-by-DGP).
3. **The four mandatory controls** (gate standard s2) on every claim: paired bootstrap
   with refit, zero-information twin, permutation null band, >= 4 time splits. Every
   coverage check TWO-SIDED (s7.4).
4. **Every published claim names its estimator** (E_refit vs E_cond) once M1 lands.
5. **Exclusive file ownership per agent.** A lane that needs a file it does not own
   reports the exact edit; the orchestrator applies it.
6. **No lane runs pytest** (conftest git-checkouts files dirtied during a run); the
   orchestrator runs the CHUNKED runner serially afterwards, keys on chunk RETURN CODES,
   and re-runs a fresh process after heavy agent load (Windows access violations appear
   after ~50 agents; a red in a degraded run is not evidence of a defect).
7. **No DB writes by lanes**, stated in every brief (an agent once ran a live ingest
   mid-audit). No RNG streams or iteration order derived from sets or `hash()`.
8. **After every wave: classify `data/` diffs** as timestamp-only vs substantive and
   revert anything no shipped code change requires.
9. **No em-dashes in any repo copy or doc.** Grades round up EXCEPT eFV (round-nearest).
10. **Artifacts self-date** with full ISO timestamps and `produced_by`.
11. **Numerical dependency rule (measured in-tree 2026-08-08, supersedes the spec-era
    "no scipy" note in older memory).** Installed and available: numpy 2.3.5, pandas
    2.3.3, scikit-learn 1.7.2, lightgbm 4.6.0, scipy 1.16.3, statsmodels 0.14.5, numba
    0.62.1, matplotlib 3.10.6, joblib, pyarrow. **ABSENT: torch, pymc, cvxpy, xgboost.**
    `requirements.txt` declares only scikit-learn, lightgbm, pyyaml, orjson, requests,
    bs4, markdown, pybaseball, pytest, py_mini_racer.
    - **scipy is SAFE in shipped code**: scikit-learn requires it, so it is guaranteed
      present on the deploy box transitively.
    - **statsmodels, numba and matplotlib are NOT safe in shipped code**: installed here,
      undeclared there. A lab under `tools/` may use them only if the lab never runs on
      the box; anything reachable from `run_monthly` must not import them without an
      explicit `requirements.txt` addition, which is an owner-visible deploy change.
    - **No probabilistic-programming or deep-learning solution is implementable**
      (pymc/torch absent). Any method in section 9 that needs one is out of scope by
      construction, not by preference. Hand-rolled EM, empirical Bayes and closed-form
      numpy/scipy linear algebra are the tools available.

---

## 4. Wave 0: prerequisites (serial, before any lane)

**P0.1 Rebuild and re-baseline.** The served matrices are STALE (74.8% of
`consensus_fv_raw` reproduces; 53.6% on busts) and `xfv.json` is one regen behind. Run the
full local regen (`run_monthly.rebuild_only()` semantics), regenerate both matrices and
all eFV artifacts, restamp the golden fingerprint with a note (factors arrays moved on the
Pinazzi skip; no served grade claim), and run the chunked suite in a fresh process for a
green baseline. **Every wave-1 margin is re-read off the rebuilt artifacts before
adjudication**; the section 1.2 numbers are the stale-tree values and will move.

**P0.2 Premise battery.** Verify before relying on (the predecessor's plan was wrong on
at least four premises; Lane 0 caught two stale memories):

1. Single-source shrink exposure: re-measure "fires on 62.9% of live board / 1.0% of
   backtest window" on the rebuilt tree.
2. `pipeline_vintages.json` grade coverage joined to RESOLVED matrix rows (expected
   small; 2015-2021 Top-100s only; the count decides whether R4b runs at all).
3. BA-vs-other-source overlap on 2023-2026 org-list rows (decides M4's design n).
4. Confirm the E_cond estimand transfers to the head-to-head statistic (the common-set
   comparison holds fits fixed by construction; if its E_refit sd already excludes refit
   variance, M1's expected shrink is smaller; measure, do not assume).
5. Confirm `_reprice_surplus_on_display` still overwrites all dollar fields (serve chain
   above) and `efv_board_scale.ENABLED_DEFAULT` still False.
6. Confirm reliability chain still divides censored labels by 6.0 (D4 carrier).
7. Confirm the routed-cohort count on the rebuilt board (~2,434 expected near, not at).
8. Confirm 2022 board fingerprint still reads 0.8667 (it is data, it cannot move, but the
   detector code may have).

**P0.3 Hygiene batch** (mechanical, no gates, one commit). **RESCOPED 2026-08-08 after the
wave-0 premise battery refuted three of its items; see `docs/efv-2026-08-08/WAVE0_RECORD.md`
section 2.**

REMOVED, because they are already fixed in source and only the ARTIFACTS are stale, so the
remedy is P0.1's regen and a code lane here would produce a no-op diff:
- `honest_note` is already derived (`efv_model._honest_note` :1690-1743, assigned
  :2652-2654, built from `verdict_vs_consensus` :1540-1555).
- `block_rho` is already emitted (`block_rho_eval()` :1619-1687, wired :2647-2651). Note
  it is ABSENT from the served artifacts, not `null`, so a test written against
  `block_rho is None` passes vacuously.

RESCOPED:
- Provenance stamp goes at `storage.py:15914`, immediately after `"run"`, because
  `timeseries.json` has **no `meta` object**; the fields are top-level in the `boot` dict.
- The undated-artifact sweep is a PROGRAM, not a batch line: 129 of 180 `data/*_eval.json`
  carry a bare date with no `produced_by` and 27 carry no `generated_at` at all. Fix only
  the artifacts this program writes; register the rest.

KEPT: attach the q4 floors to the scoreboard weak_cell (`tools/efv_scoreboard.py:456`);
fix `tools/efv_oldcohort_id_resolve.py` (write path `:76`, cwd-relative `Path("data")`
`:10`, POSIX `/tmp` cache default `:37`); the consolidated D1-D20 verdict table; export the
odds grade, which is a TWO-PART edit because `_odds_grade` is a local in all three scorers
(`efv_score.py:1480`, `:2048`, `:2542`) and is never stamped on the row.

ADDED (found in the battery): correct `efv_board_scale.py:117`, whose docstring claims
`ENABLED_DEFAULT is True` while `:184` sets it False in the same file; correct
`docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_GATE.md:187`, which claims
`SERVE_PROVISIONAL_FOR_CONSTANT_COHORT` defaults False while it is True.

---

## 5. Wave 1: measurement lanes (parallel, read-only labs, 3 verifiers each)

### M1. Power: extend E_cond, wire it, adjudicate the pre-registered cells

Owns: `tools/efv_power_lab.py`, new `docs/efv-2026-08-08/POWER_EXTENSION_GATE.md`,
`data/xfv_power_eval.json` (extend), then a reported edit to `source_backtest.py`
constants + `EFV_GATE_STANDARD.md` s7.

1. Derive E_cond MDE95 for: head-to-head common set, block-rho model-vs-consensus,
   feature-add (pooled rho AND block-rho), lambda-shift (at steps 0.05 / 0.10 / 0.19,
   the 0.70 -> 0.51 distance), MAE delta. Same producer discipline as the existing s7
   (B=2000, seed, two-sided coverage acceptance region, fold-stratified sensitivity).
2. Publish BOTH floors for every scoreboard statistic (`XFV_HEADTOHEAD_MDE95_COND` etc.)
   and adopt the naming rule: no claim without its estimator.
3. Adjudicate, Bonferroni across the family, on REBUILT artifacts: head-to-head, block-rho,
   pit full_pool, hit full_pool (confirm the E_cond loss on fresh matrices), hit/pit
   debuted, the pitcher ensemble-vs-blend gap (+0.0037 at last reading), and the lambda
   pinned-vs-argmax composite gap.
4. Pre-committed outcomes, all acceptable: (a) head-to-head certifies under E_cond ->
   owner decision 7 (site claim upgrade, conditional wording: "given this training
   corpus"); (b) stays null -> the honest tie stands, and the gate standard records that
   the margin is unresolvable under both estimators at current n; (c) hit full_pool loss
   confirms -> it gets a published weak-cell floor annotation and R1 weighs it.
   **Every one of these is re-read after M3's denoised-baseline control**, which can move
   the margin in either direction and is the more informative comparison.
4b. **Adopt the section 9.1 measurement items in this lane**: TOST equivalence bounds so
   every gate resolves SHIP / RULED OUT / UNDECIDED (the single highest value-per-line item
   in the plan, and it converts roughly half the existing nulls into knowledge); the
   decidability triage that converts each open cell's required n into a DATE and retires
   the permanently undecidable ones; Holm in place of Bonferroni; emission of a per-fold
   delta series (absent today) followed by REML + HKSJ pooling with meta-regression on
   log(n_train) to reach the deployed model, which is represented by no fold; and the look
   policy (a re-run on frozen data is not a look; alpha-spending with a declared maximum
   information beats a confidence sequence roughly tenfold at our once-a-year look rate).
5. Stop clause: if the E_cond head-to-head floor lands above +0.0297 anyway, record it,
   close the cell, and do NOT go floor-shopping for a third estimator. Section 7.3's
   trap note binds: a tighter floor makes an improvement certifiable, it does not create
   one, and the check that E_cond is not power laundering is that it can resolve losses.

### M2. Serve path: resolve the UNRESOLVED served-grade question, end to end

Owns: `tools/efv_serve_path_lab.py` (new), `docs/efv-2026-08-08/SERVE_PATH_GATE.md`,
`data/xfv_serve_path_eval.json` (v2).

1. Score, OOS on the same folds, the ACTUAL served chain: pooled (a,b) calibration as
   production applies it, floor routing ON for the routed cohort, `_GRADE_MAP` re-basing,
   against `blend` and against consensus. Correct floors this time (M1's head-to-head
   class, both estimators), not the borrowed 0.044.
2. Measure D8 for the first time: pool-relative displacement of `xfv_grade_display` (how
   far a fixed player's grade/price moves under pool churn alone, replayed across
   vintages).
3. Measure the history-basis divergence user-visibly (chart grade vs served grade,
   distribution of gaps; Bradfield 46.60 vs 50.97 class).
4. Deliverable: a decision table for R1. If served < blend resolves under E_cond, the
   repair is mandatory, not optional.

### M3. Scoreboard symmetry (D5): hold consensus to eFV's standard

Owns: `source_backtest.py` (this lane, alone), `docs/efv-2026-08-08/CONSENSUS_GATE.md`
(the never-run D-2 deliverable), `data/consensus_gate_eval.json`.

1. Score `consensus_vs_inputs` OOS, forward-chained, the protocol
   `consensus_recency_lab` already built (3,472 OOS rows exist).
2. Give `consensus_wins` an MDE floor and three-valued verdict, same shape as
   `head_to_head_verdict`. The current margin over MLB Pipeline is 0.0025 on a bare `>=`;
   expectation: unresolvable, verdict flips from "true" to "not resolvable at this
   power", and the site copy that leans on it gets the derived string.
3. Label every in-sample number on the page as in-sample, or re-score it OOS. No mixed
   tables without a basis column.
4. **THE DENOISED-BASELINE CONTROL (section 9.3 item 3), and it may cut against us.**
   eFV sees per-source values and coverage; the baseline sees a plain mean. So part of
   "eFV beats consensus" may be "eFV denoises better", which is a real serving gain but
   **not new signal**. Re-run the head-to-head with the baseline given M4's
   sigma_s-weighted, lambda_k-shrunk, lattice-corrected consensus. If eFV's edge collapses,
   the edge WAS measurement-error handling and it should ship as a baseline improvement,
   which is cheaper and more interpretable than any model change. **Expect the conviction
   headline to get harder to clear, not easier.** If it survives a denoised baseline it is
   worth far more than it is today. Corollary: any denoising that makes the consensus
   supervised must be OOS-gated exactly like eFV, or D5 reappears in a new place.
5. This lane makes eFV's OOS discipline the page-wide standard. That is conviction by
   symmetry: eFV stops competing against an in-sample-advantaged baseline, and after item 4
   it stops competing against an un-denoised one.

### M4. Consensus denoising (D10): derive the shrinkage instead of fitting a constant

Owns: `tools/consensus_shrink_lab.py` (new), `docs/efv-2026-08-08/SHRINK_GATE.md`,
`data/consensus_shrink_eval.json`.

**The design below SUPERSEDES this lane's first draft (a BA-overlap simulation gated on
pooled delta-R^2), which section 9.3 item 2 shows was pre-registering a null: the effect is
~0.007 on the labeled frame against an MDE of 0.054.** The replacement is label-free, better
powered, and derives the constant rather than fitting it.

1. **Estimate per-source noise with no labels.** `sigma_s` is exactly identified from three
   pairwise overlap variances via `var(d_st) = sigma_s^2 + sigma_t^2`, **Sheppard-corrected
   for the 5-point lattice** (h^2/12 = 2.083 FV^2, which is 28.2% of our measured
   per-publisher noise; omitting it biases the estimates non-uniformly, +23% on the best
   source and +5% on the worst).
   **ALREADY MEASURED IN WAVE 0, and the result lowers this lane's expected value.**
   `docs/efv-2026-08-08/WAVE0_RECORD.md` section 3: pooling 2023-2026 gives a max/min
   ratio of 2.78, but that is an ARTIFACT of pooling across Baseball America's 2026 basis
   change and the offset drift. Measured WITHIN year the ratio is **1.33 / 1.21 / 1.58 /
   1.19** for 2023-2026, straddling this lane's own 1.25 ship bar, and in 2026 Baseball
   America is the QUIETEST of the three (2.160 against FanGraphs 2.569 and Pipeline 2.302).
   **Gate per year or on a properly pooled within-year estimate; never on the cross-year
   pool.** State the marginality up front rather than discovering it at the gate. Residual
   confound to remove first: the median publication gap is 1-8 days for BA against
   FanGraphs but 24 days against Pipeline, so BA's pair variances still carry drift.
2. **Replace the hand-set constant with the derived reliability**
   `lambda_k = sigma_true^2 / (sigma_true^2 + sigma_pub^2 / k)` (0.705 at k=1, 0.877 at
   k=3), plus per-source inverse-variance weighting. Refinement if cheap: an
   interval-censored (coarsened-data) likelihood, since FV 45 means latent talent in
   [42.5, 47.5), which yields a player-specific posterior variance that distinguishes
   {45, 45} from {40, 50} and is a strictly better input than k alone.
3. **Fit the extremization parameter JOINTLY** (section 9.3 item 6): correlated publishers
   make a simple average under-confident, so `mu + gamma * (consensus - mu)` runs opposite
   to lambda_k shrinkage and the two double-count if fitted separately. Deflate effective k
   by the residual inter-publisher correlation, which is estimable from the paired data.
4. **Gate on the INTERACTION, not pooled delta-R^2**: regress
   `y ~ x_obs + x_obs * (k - k_bar)` and test the interaction term (simulated power 78.0%
   at n=2,000). Report the served-frame effect beside the labeled-frame one; they differ
   by 3.6x because coverage correlates with level.
5. **Controls**: source-label permutation null for the sigma_s spread (validated
   separation of 37.7 permutation sd in simulation); permuted-k interaction (validated at a
   5.2% false-positive rate against nominal 5%); a no-shrink arm; the incumbent
   K=0.5/prior=35 as the null hypothesis rather than the challenger.
6. **Ship bar (R3)**: clears its gate AND does not degrade OOS consensus accuracy from M3's
   protocol; live-board churn counted and disclosed (owner decision 4: ship if gated).
7. **The per-year offset drift test is ALREADY ANSWERED, in the affirmative** (wave 0,
   `WAVE0_RECORD.md` section 4). The FanGraphs-to-Pipeline offset runs
   +4.175 / +4.747 / +4.222 / +4.487 / +4.165 / +4.181 / +3.903 / +3.790 / +3.312 / +3.269
   across 2017-2026 at n 594-852 and SE 0.131-0.160 per year. The 2018-to-2026 decline is
   **1.478 FV, roughly 7.7 sigma**, and close to monotone after 2022. **A single global
   offset is therefore not admissible**, and any thin-cell normalization pooling across
   years applies about +4.0 where the truth ranges 3.27 to 4.75. This lane now inherits the
   result instead of spending the two hours, and M7a inherits it as a measured input.

### M5. Label bias, scoped to the distribution chain (D3/D4 successor)

Owns: `tools/efv_label_bias_lab.py` (new), `docs/efv-2026-08-08/LABEL_BIAS_GATE.md`,
extension of `data/xfv_label_censoring_eval.json`.

The rank label stays (closed ledger). Two deliverables:

1. **A bias-corrected realized-bucket assignment for calibration/reliability only.**
   **Arm (0), NEW and now ranked first (section 9.2 item 4): interval-censored partial
   identification.** This is not classical right-censoring; the accrued total is a LOWER
   BOUND on the six-year sum, so many censored rows are **already bucket-determined** (14
   WAR in four seasons is a star regardless of seasons 5-6). Each censored row contributes
   an interval; rows inside one bucket are effectively fully observed, and rows spanning
   buckets contribute a coarsened-data likelihood equal to the sum of feasible bucket
   probabilities. Exact, assumption-free, cheap, and it strictly dominates both original
   arms wherever it resolves. Then: (a) resolved-only chain for what it does not resolve;
   (b) bias-corrected projection from the measured per-n_obs bias curve (EVAL only, never
   the training label); (c) multiple imputation with Rubin's rules if the residual matters,
   which is the only option giving an unbiased distributional target AND correct variance.
   Gate: which arm's reliability read is stable under truncation replay (truncate resolved
   rows to k seasons, compare to their true buckets, a self-consistency check a constant
   fill fails by construction).
1b. **TEST THIS FIRST, because it may collapse two defects into one (section 9.2 item 4).**
   A flat-rate fill substitutes a conditional MEAN for a DRAW, removing within-player
   variance from 21% of rows, and censoring concentrates in recent higher-graded cohorts,
   which is exactly the elite tier where the variance shortfall was measured. **Our
   censoring defect and our elite-tier under-dispersion may be the same defect.** The test
   costs almost nothing: recompute the within-cohort slope on complete-window rows only.
   Run the other cheap diagnostics beside it (PIT / rank histogram on the current fans,
   spread-versus-skill by tier, CORP reliability per threshold per tier), since together
   they decide whether R2 needs full IDR or a parametric correction suffices.
2. **The tripwire honesty item**: `BUST_ECE_TRIPWIRE = 0.10` sits above the standing
   0.079 defect and survived only because nothing displaced it. Re-derive the threshold
   from the pre-registered FPR estimator on the corrected assignment, or replace the
   tripwire statistic with one that has resolution (Murphy), per the C2 lesson.

**WAVE-0 WARNING, this lane is ADVERSARIAL rather than open.** The D4 carrier is real:
`efv_reliability._realized_bucket` (:126-149) divides by a constant `TARGET_SEASONS = 6.0`
(:60) while rows carry observed_seasons 2-5, and exposure is carried as `weight = n_obs/6`
but ignored by the bucket divisor. **However its docstring at `:130-147` is an explicit
pre-registered do-not-reopen recording that the season-share-corrected relabel WAS already
run and moves pooled bust ECE only 0.07908 to 0.07660, i.e. 3.1%.** M5 must engage that
measurement head-on and say why a second attempt is expected to differ, rather than
re-deriving it and reporting the same 3.1% as if it were new. If the answer is that the
correction matters for the DISTRIBUTION rather than for ECE, say exactly that and gate on
the distribution, not on ECE.

Stop clause: if truncation replay says neither arm beats the incumbent assignment,
record it and leave the chain alone; R2 then gates on proper score with the incumbent
assignment and wider error bars.

### M6. The provisional model: the open driver frontier

Owns: `efv_ungraded.py` (read-only this wave), `tools/efv_ungraded_gate_lab.py` (extend),
`docs/efv-2026-08-08/PROVISIONAL_FRONTIER_GATE.md`, `data/xfv_ungraded_eval.json`
(extend).

1. **Re-base the eval on the served domain, and publish the effective sample size beside
   it (section 9.3 item 5).** The labeled pool is 34.1% AA / 2.6% DSL; the served board is
   34.7% DSL / 10.9% AA. Add an importance-reweighted eval beside the unweighted one, both
   estimators. **The number that must ship with it: Kish ESS is 390 of 2,000 (19.5%), and
   the DSL third of the served board rests on 52 labeled rows at an SE 6.2x the pooled
   SE.** Weight clipping is a known-size bias purchase, not a fix (clipping at 5 lifts ESS
   to 1,064 while moving total-variation distance to the served frame to 0.181).
   **Gate: refuse to publish a pooled served-population accuracy number when ESS/n < 0.25;
   publish the per-stratum table with SE multiples instead.** Control: a random density
   ratio from the same marginal must not move the reported number. Categorical strata give
   exact ratios, so no kernel density-ratio machinery is needed.
2. **Beat the dumb control.** B5 is the standing gap: provisional vs `level_rank`-only is
   +0.0706 at 0.921x floor. Pre-register a bounded battery ON THIS COHORT (the flagship
   closure does not bind here, but the gate standard's controls do): park/venue-adjusted
   rate norms (via `venue_meta`, affiliate home parks), DSL/CPX-specific age-for-level
   curves, exposure-weighted multi-season aggregation, position flag. Floors from the
   lane's own MDE (0.0433 block-rho at last derivation, re-derive on the reweighted
   basis). The PASS bar for any candidate is the margin over the DUMB CONTROL, not over
   the constant.
3. **Audit `_GRADE_MAP`.** BASE/SLOPE/KNEE/CEIL were hand-set 2026-06-23 and re-capped
   2026-07-25; 2,434 routed board rows ride them and no eval touches the map. Fit the
   linear segment on realized WAR of the routed-cohort analog, gate on the routed-cohort
   rank + a calibration read, and bring the knee/ceiling into the artifact with a
   derivation instead of a comment.
4. **Pitcher serve decision pack** (owner decision 5, ANSWERED: hold). Pitchers stay on
   the flagship grade this program. M6 delivers both estimators' verdicts, Bonferroni
   status and the reweighted read as a decision pack for a LATER cycle, not a ship. The
   hitter routing is untouched.

### M7a. Consensus as-of completion: the C-4 decision pack + targeted repairs

Owns: `grade_normalization.py` (read-only this wave), `tools/consensus_asof_lab.py`
(new), `docs/efv-2026-08-08/ASOF_DECISION_PACK.md`.

1. Measure all four C-4 options on the matrix: (1) fallback reference pre-2017,
   (2) era floor (drop pre-2017 training rows), (3) ship with an era indicator,
   (4) NEW, this plan: pin pre-2017 offsets at each source's earliest measurable own-year
   offset (2017), keeping one reference scale with no normalization-OFF cliff. For each:
   per-fold `consensus_fv_raw` deltas, model-vs-consensus margin movement under both
   estimators, and the discontinuity size at the 2017 boundary. Deliver the table; owner
   picks (decision 2). Expectation to state plainly: removing a future-info leak from the
   BASELINE may lower the baseline and RAISE eFV's measured edge, or reveal the edge was
   partly leak-fed; either is worth knowing before any conviction claim ships.
2. **2022 board targeted repair**: a hand-verified per-board override table
   (board key -> classification) rather than loosening `MIN_OFFSET_EXACT_FRAC` globally;
   the 4-of-30-orgs fingerprint disagreement gets manually adjudicated once, with the
   evidence in the override entry. Detector bar stays 0.90 for everything else.
3. **D16 same-name split spec** + `players.org` canonicalization spec (1,144 values), as
   reported edits for R3.

### M7b. Drop-off shrink, gated as a candidate (owner decision 6a)

Owns: `tools/consensus_dropoff_lab.py` (new), `docs/efv-2026-08-08/DROPOFF_GATE.md`,
`data/consensus_dropoff_eval.json`. Split out of M7 so it cannot starve C-4.

Pre-register first. Score the repaired detector's 463 pairs against realized outcomes with
all four mandatory controls, both estimators, **on the as-of timeline only** (the
retroactive version IS the leak and must not be scored as if it were a candidate). State
in advance: this parameter has never fired in production, so there is no incumbent
performance to beat and the question is whether the shrink adds information at all. The
746 live grade moves are counted and disclosed at decision time regardless of verdict. A
null CLOSES it permanently and the dormant flag comes out of the tree, which is worth more
than leaving it enabled-able.

---

## 6. Wave 2: ships, each gated on its wave-1 lane

### R1. Serve-path coherence (needs M2; owner decisions 3 and 7 ANSWERED, see section 8 delta A)

- If served < blend resolved: repair the binding stage (pooled-vs-per-fold calibration,
  or serve the blend-basis grade) with an epoch bump and full disclosure. If null: ship
  only the coherence items below.
- **D6 is decided: UNIFY ALL FOUR BASES onto the served grade.** Odds re-pointed off the
  retired `realized_implied_fv` map, dollars re-pointed off the display quantile, history
  and movement re-based. Ships in ONE coordinated epoch with R2 (both move prices), with
  the full re-capture mechanics and the odds-calibration risk check in delta A.
- Re-base `xfv_history` / movement onto the served basis (kills the third live basis).
- D7: the sub-floor display re-spread either gets an eval or keeps its "never present as
  calibrated" scope enforced in copy at every consumer (audit which).
- Board-serve probe (`tools/efv_board_serve_probe.py`) extended to assert odds-basis and
  dollar-basis agreement with the artifact, not just the rendered grade.

### R2. Distribution recalibration, done right this time (needs M5; owner decision 6)

- **Family DECIDED by section 9.2: isotonic distributional regression (IDR / EasyUQ), cut
  at the four bucket thresholds.** Four PAVA fits on `sklearn.isotonic`, roughly twenty
  lines, non-crossing by construction because the threshold indicators are pointwise
  ordered. The correction becomes an arbitrary MONOTONE function of the score, so unlike
  the incumbent it CAN move tiers 55/60, and our measured tier gaps are monotone increasing
  in tier, which is the signature of a single-slope correction applied where the true
  correction varies. Fallback if IDR reads jumpy on the board: a partial-proportional-odds
  cumulative-link recalibration with a grade-varying threshold shift.
  **Three hazards to pre-register**: fit on OUT-OF-FOLD scores (IDR is optimal in-sample by
  construction, the biggest trap here); IDR cannot extrapolate above the training maximum,
  which caps the published fan, so smooth it; and the star cell inside FV60 may hold 10-25
  events, so report that probability as a Venn-Abers INTERVAL rather than a point.
- **Gate DECIDED: mean RPS primary (ordinal, unlike anything we use today) with a CORP /
  MCB-DSC-UNC decomposition**, four arms in one table (incumbent, candidate, global
  climatology, tier-marginal climatology), on M5's corrected bucket assignment, both
  estimators, Holm. **A zero-information constant fails this by construction**: it has
  discrimination and calibration components identically zero, so its score equals the
  uncertainty term exactly and its skill score is exactly 0. That is the structural fix for
  the C2 embarrassment, replacing a gate we had to hand-check with one that cannot be
  passed by a constant.
- **The dollar layer finally gets a gate**: because EV is affine in the four exceedance
  probabilities, use threshold-weighted RPS with weights equal to the surplus jumps (our
  dollar error IS a jump-weighted sum of four Brier scores), plus an auto-calibration
  residual by predicted-EV decile and a Murphy diagram so the claim reads "not worse at any
  threshold".
- Ship mechanics: re-stamp `prospx_current.yaml` INSIDE `vf.valuation_set("prospx_current")`,
  re-capture the ~20 test literals, disclose board dollar movement, epoch bump.
- The tier-55/60 over-pricing (top realized-WAR quartile over-priced $18.9M-$25.3M under
  perfect foresight) is the target; report movement on exactly that cell.
- **Coordinated with R1** (owner decision 3): R1's re-basing and R2's recalibration both
  move served prices, so they share one epoch, one `prospx_current` re-capture and one
  golden restamp. Sequence: R1's basis change lands first in the working tree, R2 is
  gated and fitted ON the unified basis, then the pair ships together. Fitting R2 on the
  old basis and re-basing afterwards would invalidate the gate.

### R3. Consensus input repairs (needs M3, M4, M7a, M7b; owner decisions 2, 4, 6a)

- C-4 option per owner, chosen off M7a's measured table, shipped with per-fold
  before/after and the model margin re-read under both estimators.
- Single-source K/prior refit if M4 cleared, with churn disclosure (decision 4: ship if
  gated).
- 2022 board override; same-name splits; org canonicalization. Each with a
  consensus-movement count and an eFV margin re-read (these move the baseline, so the
  conviction numbers must be re-read after every one of them, not once at the end).
- `DROPOFF_SHRINK_ENABLED`: ships only if M7b's gate clears, with the 746 live grade moves
  disclosed. If M7b is null, the flag and its machinery are REMOVED rather than left
  dormant.

### R4. Bounded new-driver tests (needs M1 floors; all pre-registered, all with the 4 controls; budget: one session, hard stop)

Ranked; run in order; each has a power check BEFORE any fit (if the covered-subset floor
exceeds any plausible effect, record the bound and stop; do not manufacture a null):

- **R4a. Park/venue-adjusted MiLB rate norms** (flagship + provisional). This is a
  feature-VALUE correctness refinement (the DSL-labeling precedent), not a composition
  change: rate features are level-normalized but park-blind, and `venue_meta` (228 parks,
  elevation) + affiliate home parks are already on disk. Ship bar: neutral-to-better on
  the gate battery, shipped as correctness if within floor, celebrated only if it clears.
- **R4b. Pipeline vintage tool grades 2015-2021** as features on resolved folds (P0.2
  premise 2 decides). Power check first; expectation: coverage-bound null; record it.
- **R4c. The pre-registered symmetric-coverage id retest** (the ONLY sanctioned milb
  backfill revival): merge the 735 debut + 283 bust overrides (path fix from P0.3),
  era-restricted 2015-2018, exactly as Test-1's revival clause specified. Expectation:
  neutral; value is closing a 2-year-old registered experiment and the id assets stop
  being orphans.
- **R4d. BA risk grade into the p_bust chain** (calibration-side, never rank): busts
  resolve faster than stars, so 2023-2024 BA vintages may already have resolvable bust
  outcomes. Power check first; if underpowered, register the revival clock (each season
  resolves more of the 980 BA-graded players).

Anything beyond these four on the flagship is out of scope, per the closed ledger.

### R5. Archival infrastructure: bank the only open frontier (owner decision 8 ANSWERED: monthly)

- **Monthly dated, append-only archiving** for `statcast_metrics`, `zone_metrics`,
  `pitch_arsenals` (currently PK `player_key`, so every refetch clobbers the prior row),
  plus dated snapshots of `stuff_plus_aaa.json` / `aaa_physics.json`. One dated dump per
  table per month wired into run_monthly beside `metric_snapshots` (which has accrued
  board scalars daily since 2026-06-06 with no pruning code, and proves the pattern).
  Season-level resolution is what a training feature needs; daily was declined.
- Include a written retention and size note at ship time. `metric_snapshots` reached
  181,183 rows in 62 days with no pruning; a monthly cadence on three payload tables is a
  fraction of that, but the box should not learn its disk budget by running out.
- Register the revival clocks in the registry so future sessions find them: IL/injury
  feature (~2028, il_history began 2026-06), MiLB-Statcast training features (2028-29,
  when 2023+ tracked cohorts resolve), BA risk power (2027-28), single-source shrink
  re-fit (as BA vintages accrue). Each clock names the artifact that will carry it and the
  gate it must clear, so the revival is a measurement and not a re-litigation.

---

## 7. Wave 3: close-out

- Consolidated verdict ledger for THIS plan (every lane, every pre-registered clause,
  what survived verification), plus the D1-D20 back-fill from P0.3.
- Registry rows + eval artifacts for every lane per the standing rule; failed challengers
  as blocks in parent artifacts, never standalone.
- Site copy: every conviction claim reads a DERIVED verdict string (M1/M3 outputs), no
  hand-written "beats" prose anywhere (grep for the pattern and pin with a test).
- Chunked suite in a fresh process; classify + revert `data/` churn; commit per lane;
  memory files updated.

---

## 8. Owner decision queue: ANSWERED 2026-08-08, all nine

Answered by the owner before execution. Three answers CHANGE LANE SCOPE and the changes
are folded into sections 5 and 6 above; the deltas are called out here.

| # | decision | answer |
|---|---|---|
| 1 | Estimator policy | **Dual estimator, E_cond gates.** Every claim names E_refit or E_cond; ship gates must clear E_cond and must not be contradicted by E_refit; E_cond-only certifications carry conditional wording. |
| 2 | C-4 grade-norm repair | **Decide after M7a's measured table.** All four options measured first (per-fold deltas, margin movement under both estimators, 2017 boundary discontinuity). |
| 3 | Grade-basis scope | **UNIFY EVERYTHING onto the served grade.** Not the labeled-bases option. See delta A. |
| 4 | Single-source shrink | **Ship if gated, churn disclosed.** |
| 5 | Pitcher provisional serve | **Hold pitchers on the flagship grade; M6 re-reads on the served-mix reweighted basis with both estimators.** Hitters unchanged. |
| 6 | Distribution recalibration | **Ship if it clears the proper-score plus resolution gate** (Brier + logloss + Murphy resolution against the zero-information constant, both estimators, Bonferroni). |
| 6a | `DROPOFF_SHRINK_ENABLED` | **Gate it as a real candidate**, do not leave it dormant and do not enable it ungated. See delta B. |
| 7 | Site messaging | **Upgrade with conditional wording** if the head-to-head certifies under E_cond, derived from the verdict string, never hand-written. |
| 8 | Archive cadence | **Monthly dated dumps** wired into run_monthly beside the metric_snapshots writer. |

### Delta A: R1 becomes a full re-basing, not a labeling pass (decision 3)

Unifying all four bases onto the served grade is the larger of the two options offered and
it moves published numbers. R1 therefore owns:

- Re-point the odds chain: `p_bucket` / `p_bust` computed on the served grade rather than
  `_odds_grade` (`vf.realized_implied_fv`, the retired map). Every published probability
  moves. The 0.0% agreement above FV45 is the size of the change at the top of the board.
- Re-point dollars: retire `_reprice_surplus_on_display`'s quantile keying, or promote the
  quantile to the served basis, whichever the M2 measurement shows preserves the surplus
  chain's calibration. **This collides with R2**: both move served prices, so R1 and R2
  ship in one coordinated epoch with a single re-capture, not two.
  **THREE call sites, not two** (wave-0 correction): `run()` at `efv_score.py:1584-1585`,
  `run_live()` at `:2219`, and `run_backgrade()` at `:2600`. The backgrade path was omitted
  from this plan's first draft; missing it leaves every backgraded row on the retired
  quantile while the live board moves, which is a silent two-basis split of exactly the
  kind D6 exists to remove.
- Re-base `xfv_history` / movement (kills the third user-visible basis).
- Mandatory ship mechanics: epoch bump, `prospx_current.yaml` re-capture INSIDE
  `with vf.valuation_set("prospx_current")` (capturing on the clemens_2026 default
  silently yields a different grid and has cost a full cycle before), the ~20 test
  literals, `test_valuation_sets` and the prospx_current grid test, golden restamp, and a
  board-serve probe extended to assert odds-basis and dollar-basis agreement.
- **Pre-registered risk to disclose at decision time**: the served grade
  (`outcome_implied_fv`) and the retired odds map are different quantities, so unification
  is not a relabeling. If the odds calibration degrades on the served basis (measure it:
  re-fit the Platt correction on the new basis and compare proper scores), report that
  before shipping rather than absorbing it silently.

### Delta B: M7 splits into M7a and M7b (decision 6a)

M7 as written could not absorb a second gated candidate without starving C-4.

- **M7a**: the C-4 decision pack (four options measured), the 2022 board override, the D16
  same-name split spec, `players.org` canonicalization spec. Unchanged scope otherwise.
- **M7b, NEW**: gate `DROPOFF_SHRINK_ENABLED` as a candidate. Pre-register first. Score
  the repaired detector's 463 pairs against realized outcomes with all four mandatory
  controls (paired bootstrap with refit, zero-information twin, permutation null band,
  >= 4 time splits), both estimators, on the as-of timeline ONLY (never the retroactive
  version, which is the leak). Ship only if it clears; the 746 live grade moves are
  disclosed at decision time either way. Expected outcome to state honestly in advance:
  the parameter has never fired, so there is no incumbent performance to beat and the
  test is whether the shrink adds information at all. A null closes it permanently, which
  is worth more than leaving a dormant flag in the tree.

### NEWLY SURFACED by the section 9 research, UNANSWERED (not blocking)

9. **The indifference margin Delta for the TOST / equivalence bounds.** Needed before
   wave 1 can report RULED OUT verdicts. Recommendation: set it in rank units at the
   smallest delta that would change a board decision, and register it before looking.
10. **The false-ship to missed-improvement loss ratio.** Testing at alpha = 0.05 with a
    30-gate correction silently encodes a roughly 60:1 asymmetry that nobody chose. Most
    of our ships are reversible (a constant, a flag, an epoch bump), which argues the
    implicit threshold is far too strict. Write the ratio down, derive the threshold from
    it, and stop inheriting 0.05 from publication convention.
11. **Look policy and maximum information**, if the alpha-spending design in section 9.1
    item 5 is adopted: declare the projected cohort count through roughly 2035 as the
    maximum information. Recommendation: adopt, since it buys unlimited looks for 3-6%
    where a confidence sequence costs 29-55%.

### Delta C: M6 pitcher scope is now explicit (decision 5)

Pitchers stay on the flagship grade this program. M6 delivers the reweighted re-read as a
decision pack for a LATER cycle, not a ship. The hitter routing is untouched.

---

## 9. The advanced mathematical program (owner ask, 2026-08-08)

Researched 2026-08-08 across three literature lanes. **This section does not reopen the
closed rank frontier.** Every item below sits in a layer the closure does not cover:
the ESTIMATOR, the DISTRIBUTION, the CALIBRATION, the VARIANCE, the DOLLARS, or the
INPUT MEASUREMENT MODEL. Anything that would need a feature hunt is rejected on sight.

Implementability filter applied throughout (rule 11): numpy / scipy / scikit-learn /
lightgbm only. **NGBoost, LightGBMLSS, MAPIE, distributional random forests, venn-abers,
dirichletcal, onlineFDR, pymc, torch and cvxpy are all absent and would each add an
undeclared dependency**, so anything requiring them is registered as a dev-only arm or
hand-rolled. PAVA (`sklearn.isotonic`), Lambert W (`scipy.special.lambertw`) and the
rest of what follows are already available.

### 9.0 Two findings that reorganize the program

**FINDING 1: the floor is an ESTIMAND problem, not a measurement problem, and this
explains the 4-to-11-fold null analytically.**

Decomposing the two measured floors (`var_total ~= var_refit + var_test`), refit variance
is **53.2% to 78.5%** of total. Therefore driving test n to INFINITY moves the floor only
from 0.0440 to 0.0321-0.0390, an 11-27% gain. That is the entire remaining headroom
available from more cohorts, and it is why promoting 4 folds to 11 did not move the floor
by a single point. **Stop buying cohorts to fix power.**

Three independent routes agree on the fixed-fit floor and none reproduces the refit floor:

| route | floor |
|---|---|
| our measured E_cond bootstrap | 0.0204-0.0301 |
| Steiger / Dunn-Clark analytic at r(eFV, consensus) ~ 0.90-0.97 | 0.0203-0.0300 |
| design-matched Monte Carlo, n=800, paired | 0.0257-0.0270 |
| **our E_refit bootstrap** | **0.0440** |

The analytic route reproducing E_cond **to three decimals** is strong independent
validation that E_cond is correctly calibrated and that E_refit's extra width is genuine
refit variance rather than a pairing failure. Owner decision 1 (E_cond gates) therefore
has theory behind it and is worth **2.1x to 4.7x effective sample size**.

**VERIFIED IN TREE, and it closes the one risk that could have invalidated the ledger.**
Both briefs warned that if the bootstrap resampled ROWS rather than PLAYERS (the
head-to-head set is 3,210 rows over 1,050 players, 3.06 rows each), precision would be
overstated 1.27x-1.75x in the ANTI-CONSERVATIVE direction and every null would be
suspect. Measured 2026-08-08: `tools/efv_mde_lab.py:494` documents and implements a
**cluster paired bootstrap that resamples by player**, and both matrices are exactly
**one row per player** (hit 1,917/1,917, pit 2,040/2,040), so the four matrix cuts cannot
have the defect by construction. **No correction owed. The covariance term is captured.**

**FINDING 2: the five buckets are cuts of ONE latent CDF, and the dollar EV is an affine
function of exactly four exceedance probabilities.**

With thresholds t = (0.5, 1.5, 2.5, 4.0) on average annual WAR:

```
P(bucket_k | x) = F(t_k | x) - F(t_{k-1} | x)
EV(x)          = s_1 + SUM_k (s_{k+1} - s_k) * [1 - F(t_k | x)]
```

So buckets, the P10-P90 fan and the dollar price are three VIEWS of one object. Today they
are three separately-maintained layers that can and do disagree. Estimating one conditional
CDF and cutting it makes ordinality, non-negativity, sum-to-one and fan/EV coherence
structural rather than enforced. It also means the correct scoring rules for all three
consumers are one family (RPS is CRPS discretized at our thresholds), and that **the dollar
error is exactly a jump-weighted sum of four Brier scores**, which finally gives the dollar
layer a proper pre-registerable gate. It has none today.

Critically: **a monotone recalibration of score to distribution is RANK-INVARIANT**, so
this entire program is orthogonal to the closed frontier.

### 9.1 Measurement mathematics (folds into M1)

Ordered by value per unit of work. The headline: **the program is variance-limited, not
alpha-limited.** The entire multiplicity envelope is worth at most 60% and realistically
0-11%; the paired covariance was worth 2x-10x and is already banked; the estimand choice
is worth 2.1x-4.7x and is decision 1.

1. **TOST / equivalence bounds on every null. Highest value per line in the whole plan.**
   Both briefs raised it independently. Our gates currently resolve two ways (SHIP,
   NULL) and 12 of 24 lane headlines died as uninformative nulls. Adding a pre-registered
   indifference margin `Delta` makes every gate resolve THREE ways: **SHIP** (CI entirely
   above Delta), **RULED OUT** (CI entirely inside +/- Delta), **UNDECIDED**. This costs
   zero statistical power and converts roughly half of the existing nulls into positive
   knowledge. Example available today: at a 0.16x margin the E_refit basis already
   licenses "the delta is at most 0.033", and E_cond tightens that to 0.019. Cost ~40 LOC
   plus one owner decision on Delta. **Register Delta before looking.**
2. **Decidability triage, published.** For each open cell compute the n multiplier needed
   and convert it to a DATE at the known cohort accrual rate. The 0.84x cells need ~1.42x
   effective n, i.e. roughly 4-5 more cohort-years, decidable around 2030-2031 with zero
   methodological change. Cells at 0.16x need ~39x and are **permanently undecidable**:
   retire them explicitly rather than re-testing them every cycle and re-reporting the
   same null. This is the honest version of "the frontier is closed".
3. **Bonferroni to Holm.** Uniformly more powerful, valid under arbitrary dependence,
   one line. Worth 0% at the first rejection, 3.4% at the second, 7% at the third. Free
   and cannot lose. Note our Bonferroni is hand-rolled z-based in the labs, so this is a
   small shared helper rather than a `statsmodels` call (rule 11: statsmodels is not
   shippable here).
4. **Analytic cross-check of E_cond** via Steiger/Dunn-Clark plus Zou's CI method. Buys
   essentially ZERO power (it estimates the same asymptotic variance) but is a fast,
   transparent, seed-free second route, and it already reproduces our number. Two
   corrections are mandatory and are the reason this is a lane and not a one-liner:
   Steiger-on-ranks is not valid off the shelf (ranks of independent data are dependent),
   so use the Bonett-Wright variance `(1 + rho_s^2/2)/(n-3)` as the marginal correction,
   or the proper U-statistic multivariate CLT for a vector of rank correlations on the
   same data. Our naive SE is 2-5% too small at rho_s 0.30-0.45. **Declare that this
   route silently targets the CONDITIONAL estimand**; adopting it without saying so is
   exactly the smuggling the gate standard forbids.
5. **Look policy, and a rejection.** An information-bearing look happens when a cohort's
   six-year window closes, i.e. about ONCE A YEAR. Re-running a gate on frozen data is
   deterministic and is not a look, needs no correction, and should be stated as policy.
   **REJECT confidence sequences / anytime-valid inference here**: a tuned AsympCS costs
   1.29x-1.55x in width (the cost falls as alpha tightens, so at our per-gate Bonferroni
   level it is 1.29x / 1.68x in n) and only beats Bonferroni-over-looks past roughly 21
   looks, or ~35-40 at our corrected level. At one informative look per year that is a
   35-year payback. **Adopt instead a Lan-DeMets alpha-spending design (O'Brien-Fleming
   shaped) keyed to information fraction, with the maximum information declared as the
   projected cohort count through ~2035**, which buys unlimited looks for 3-6% in maximum
   n instead of 65%. We can declare a maximum because the cohort supply is finite and
   forecastable. If the horizon ever becomes genuinely open-ended, the fallback is an
   asymptotic CS on the influence-function representation, and it must then be clustered
   at the PLAYER level (n~1,050); an AsympCS at 11 year-clusters has no guarantee at all.
6. **Per-fold delta emission, then REML + HKSJ meta-analysis.** The eval currently emits
   no per-fold delta series (only `per_fold_top25_display`, a different quantity), so
   this starts with an artifact addition. Then combine folds by REML with the
   Hartung-Knapp-Sidik-Jonkman adjustment. **Adopt for VALIDITY, not power: it will widen
   us 15-40%** (HKSJ alone swaps z=1.960 for t_10=2.228). **Never ship plain
   DerSimonian-Laird** (type-I error inflates past 30% at k=11; a quarter of DL-significant
   results reverse under HKSJ). Suppress I^2, which sits near 0.99 mechanically at our
   per-fold n; report tau on the z scale. **Highest-value variant: meta-regression on
   log(n_train)**, because the deployed model trains on ALL cohorts and is therefore
   represented by NO fold; nothing else in the toolkit can extrapolate to the thing we
   actually ship. Declare the estimand change (fixed-effect = these 11 cohorts;
   random-effects = a superpopulation of cohort-years, where the forward claim is licensed
   by the PREDICTION interval, not the CI on the mean).
7. **Loss ratio, an owner decision this plan surfaces.** Testing at alpha = 0.05/30
   encodes an unexamined ~60:1 asymmetry between a false ship and a missed improvement.
   If a swap is nearly free and reversible (it usually is here: a constant, a config flag,
   an epoch bump), the implied threshold is far too strict. Write the ratio down, then
   derive the threshold from it, rather than inheriting 0.05 from publication convention.
8. **Rank-scale LOCO for driver questions** (Lei et al. 2018), built on a CONCORDANCE loss
   (delta Somers' D with DeLong-style covariance) rather than absolute error. It is
   paired, distribution-free, and **inference conditional on the fit, so refit variance is
   not in its target at all**, which is exactly the right frame for "does driver X add
   anything beyond consensus FV". Preferred over DML, which is rejected below.
9. **Influence-function / infinitesimal-jackknife decomposition as a DIAGNOSTIC.** Ridge
   has a closed-form weight derivative; composed with the analytic Spearman influence
   function it decomposes the floor into train and test contributions with zero Monte
   Carlo error. Its value is diagnostic, not a smaller floor. **Implementation trap: use
   the analytic Spearman IF, never numerical differentiation, because the derivative of a
   rank function is almost everywhere zero.**
10. **Free hygiene**: pre-registered one-sided tests (worth 11% effective n, legitimate
    because we only ship on eFV > consensus, and the convention is already one-sided);
    exhaustive 2^11 = 2048 sign enumeration for exact randomization inference on the
    year-clustered test (zero Monte Carlo error, seconds of compute); an 8-seed
    replication diagnostic to close the Monte Carlo question permanently.

**Rejected in this lane, with reasons.** Monte Carlo variance reduction of every kind
(control variates, antithetic, balanced, Rao-Blackwell, quasi-MC, bag of little
bootstraps): MC error is ~0.001 of a 0.0440 floor, so driving it to zero moves the floor
by 0.025% and a perfect 50x control variate changes nothing. Online FDR (LORD, LORD++,
SAFFRON, ADDIS, alpha-investing): wrong problem class, since our gates are pre-registered
and known in advance, wrong scale, since the authors state these need T > 1000 and warn
they are uncompetitive at small T and low discovery rate, and three of them require
INDEPENDENT p-values, which is flatly false on our overlapping data. Benjamini-Yekutieli:
its `c(30) = 3.995` penalty makes it 12% WORSE than the Bonferroni we already run.
Benjamini-Hochberg: at R <= 1 rejections its threshold is algebraically identical to
Bonferroni, and FDR at R <= 1 IS FWER, exactly. Westfall-Young maxT: valid but the
multiplicity threshold is so flat that collapsing 30 effective gates to 10 buys 12%,
not worth the permutation compute. DML as the primary frame: p/n ~ 0.004 so it reduces to
Frisch-Waugh-Lovell with robust SEs, and it targets a conditional-MEAN parameter on a
label our own audit calls mean-scale-biased, giving up the monotone invariance that makes
rank statistics robust. Nadeau-Bengio correction: does not apply to our pooled-row
estimator, only to a fold-averaged one (it becomes relevant only if item 6 is adopted,
where it implies a further 11-21% sd inflation and is a LOWER bound because
forward-chaining uses nested training sets). m-out-of-n bootstrap and subsampling: remedies
for inconsistency, and Spearman-of-ridge is Hadamard differentiable. More folds: empirically
falsified by our own 4-to-11 result. Tie corrections for POWER reasons: simulation across
0-65% zero-WAR mass shows the MDE is flat, so ties do not cost power (they still matter for
analytic-formula correctness).

### 9.2 Distribution, calibration and dollar mathematics (folds into M5 and R2)

This is where the largest honest accuracy gains live, because it is rank-invariant and
therefore untouched by the closed frontier.

1. **Fix the GATE before fitting anything. RPS primary, CORP decomposition, constant as a
   registered ARM.** Our C2 embarrassment (a zero-information constant reaching 152.7% of
   the candidate's gain) was not bad luck, it is a theorem: ECE is not a proper scoring
   rule and is trivially minimized by a feature-ignoring constant, and bust-only ECE
   additionally discards the ordering, which is why it is structurally blind to the
   FV55/60 defect. Replace with **mean RPS** (ordinal, squared cumulative differences)
   decomposed via **CORP / MCB-DSC-UNC** (PAV-based, reproducible, no arbitrary binning).
   **Why a constant then provably cannot pass**: a constant forecast has DSC = 0 and
   MCB = 0 identically, so its score equals UNC exactly, its R* = 0 exactly and its skill
   score is 0 exactly. Any gate carrying a strictly positive discrimination clause or a
   strictly positive skill clause is **unpassable by a zero-information predictor by
   construction**, which is precisely the property the gate standard has been demanding
   and hand-checking. Pre-register four arms in one table every time: incumbent,
   candidate, global climatology, tier-marginal climatology.
2. **Isotonic distributional regression (IDR) / EasyUQ: one conditional CDF, cut at the
   four thresholds.** EasyUQ is literally our problem statement (single-valued model
   output plus outcomes, produce a calibrated predictive distribution, no model access).
   Restricted to our four business thresholds it collapses to **four PAVA fits on
   `sklearn.isotonic`, about twenty lines**, and because the threshold indicators are
   pointwise ordered the fitted curves **cannot cross**, giving ordinality-respecting,
   renormalization-free bucket probabilities. What it buys, defect by defect: the
   correction becomes an arbitrary MONOTONE function of the score, so unlike the incumbent
   global Platt it **can move FV 55/60**; our measured tier gaps
   (.020/.042/.054/.051/.072/.122) are monotone increasing in tier, which is the exact
   signature of a single-slope correction applied where the true correction varies in the
   covariate; and the conditional SPREAD is estimated nonparametrically, where Platt has no
   spread parameter at all. It is tuning-free, O(n log n), and under low signal-to-noise
   the number of PAVA blocks adapts downward, which is an intrinsic regularizer.
   **Three implementation hazards to pre-register**: (a) IDR is optimal in-sample by
   construction, so fit on OUT-OF-FOLD scores and evaluate held out, which is the single
   biggest trap; (b) IDR CDFs jump only at observed response values and cannot
   extrapolate above the training max, which caps the published fan (fix with smoothed
   EasyUQ); (c) the top threshold is the binding constraint, since stars inside FV60 may
   be 10-25 events, so the star probability there must be reported as an INTERVAL (item 5)
   rather than a fake point estimate.
3. **A proper dollar gate, which does not exist today.** Because EV is affine in the four
   exceedance probabilities, the correct primary is **threshold-weighted RPS with weights
   equal to the surplus jumps**, i.e. our dollar error IS a jump-weighted sum of four
   Brier scores. Pair it with an **auto-calibration** requirement (E[realized surplus |
   EV = v] = v), checked by binning on predicted-EV decile, plus portfolio total. A
   constant fails both by construction (zero decile spread, zero skill). Add a **Murphy
   diagram** over the elementary-score threshold so the claim becomes "not worse at any
   threshold", which is far stronger than a single aggregate. Isotonic recalibration of EV
   against realized surplus achieves auto-calibration while preserving rank.
4. **Censoring: partial identification FIRST, and a hypothesis worth testing before any
   modelling.** This is not classical right-censoring; the accrued total is a LOWER BOUND
   on the six-year sum. Many censored rows are therefore **already bucket-determined** (a
   player with 14 WAR in four seasons is a star regardless of seasons 5-6). Each censored
   row contributes an interval on average annual WAR; rows whose interval lies inside one
   bucket are effectively fully observed, and rows spanning buckets contribute a
   coarsened-data likelihood equal to the sum of feasible bucket probabilities. This is
   exact, assumption-free, and cheap, and it should be done before anything fancier.
   **THE HYPOTHESIS TO TEST FIRST, because it may unify two defects into one**: a
   flat-rate fill substitutes a conditional MEAN for a DRAW, which removes within-player
   variance from 21% of rows, and censoring concentrates in recent higher-graded cohorts,
   i.e. exactly the elite tier where we measured the variance shortfall. **Our censoring
   defect and our elite-tier variance defect may be the same defect.** Test cheaply by
   recomputing the within-cohort slope on complete-window rows only. If it holds, item 2
   plus this repair addresses both.
5. **Venn-Abers intervals for the thin top cells.** Isotonic calibration with a
   finite-sample validity guarantee whose output is a probability INTERVAL. The honest
   answer to 10-25 star events inside FV60 is to publish an interval, not a point.
   Hand-rollable on PAVA, no new dependency.
6. **Conformal prediction for the published fans, with an honest guarantee statement.**
   Order: split conformal, then conformalized quantile regression (LightGBM quantile heads
   plus a conformal correction, which also attacks the variance defect), then
   Mondrian/group-conditional for PER-TIER coverage, clustering the sparse top tiers.
   **Diagnose first**: an 80% band covering 0.31-0.41 is roughly the width of a confidence
   interval on the conditional MEAN rather than a prediction interval on the OUTCOME, which
   would be a one-line fix making conformal unnecessary. **Two hard caveats to
   pre-register**: exact per-PLAYER coverage is impossible distribution-free, so guarantee
   per-TIER and write the user-facing copy accordingly; and censoring breaks
   exchangeability, so never conformalize the raw censored label. **Coverage alone must
   never be the gate** (an infinitely wide band covers perfectly), so pair it with the
   interval/Winkler score, which is the bands-layer version of the ECE lesson.
7. **Cheap diagnostics before any of the above, half a day total**: PIT / rank histogram
   on the current fans (a U-shape is the textbook under-dispersion signature and 0.31-0.41
   coverage predicts a severe one), spread-versus-skill by tier, the complete-window slope
   test from item 4, and CORP reliability diagrams per threshold per tier, which will show
   whether the 0.122 gap at FV60 is a level shift or a slope failure and therefore whether
   full IDR is needed or a parametric partial-proportional-odds correction suffices.

**Rejected in this lane.** ECE as a primary gate (not proper, admits a constant; demote to
a reported diagnostic beside discrimination). Anything bust-bucket-only (discards ordering,
structurally blind to the measured 55/60 defect). Temperature scaling (one parameter,
strictly weaker than the incumbent two, still cannot vary with grade). Unregularized matrix
scaling (30 parameters per side at our n, documented overfitting). Dirichlet calibration
(not ordinal-aware, and item 2 makes a parametric multiclass layer unnecessary; also a new
dependency). Pseudo-observations as a distributional label (unbiased for the MEAN functional
only, wrong dispersion, can fall outside support; the salvageable form is threshold-wise on
the exceedance indicators). LightGBM Tweedie (assumes non-negative support with a mass at
zero; WAR is genuinely negative for busts, and shifting corrupts the zero-mass semantics).
NGBoost, LightGBMLSS, distributional random forests, MAPIE (all real methods, all new
undeclared dependencies; register NGBoost as a dev-only arm whose expected verdict is NULL
given the rank ceiling, so that a null is a shippable finding rather than a sunk session).
Full Bayesian GAMLSS / Stan (pymc absent, and PAVA buys the same monotone correction).
Deep ensembles, MC dropout, Bayesian neural nets (n~2,000 with 13 features is not the
regime; torch absent anyway). Complete-case deletion of the censored 21% (censoring
correlates with grade, so dropping is biased, not merely lossy). IPCW as primary (unbiased
but discards 21% of rows at an n we cannot afford; keep as a robustness arm only).
Promising per-player band coverage (impossible distribution-free).

### 9.3 Measurement-model mathematics for the consensus (folds into M3, M4, M6, M7a)

This lane produced the sharpest results because it derived constants FROM OUR OWN
published statistics rather than from the literature.

**What our own FG-vs-Pipeline pair statistic already contains.** From the published
SE 0.089 at n_pair 1,864: the paired difference sd is **3.842 FV**, so per-publisher noise
is **sigma_pub = 2.717 FV**, of which **28.2% is pure lattice quantization** (Sheppard,
h^2/12 = 2.083 FV^2 at h = 5). Decomposing E[(pipeline - fg)^2] = 19.07 (offset^2) + 14.76
(variance): **the mean offset we already ship removes 56.4% of the total**, leaving
14.76 FV^2 of which 4.17 is irreducible. **Maximum recoverable by any harmonization
method: 10.60 FV^2.** That is the honest size of the entire harmonization prize.

**THE HEADLINE, and it redirects two lanes.** Harmonization (aligning source scales) is
56% done with a bounded remainder. **DENOISING is a different problem with a different and
OPEN frontier**: at reliability lambda ~ 0.70-0.80, perfectly denoising a single-source
grade would raise its correlation with realized WAR by **1/sqrt(lambda) = 1.19x at k=1**
and 1.10x at k=2. Separate the two words everywhere in this program; they have been
conflated and they have very different ceilings.

1. **Per-source inverse-variance weighting, with a Sheppard-corrected sigma_s. (~3h,
   label-free.)** `sigma_s` is **exactly identified with no labels**: three sources give
   three pairwise overlap variances and `var(d_st) = sigma_s^2 + sigma_t^2` inverts
   exactly. Verified in simulation: truth [2.0, 3.2, 4.5] recovers as
   [1.983, 3.208, 4.517] WITH the Sheppard term, and as [2.453, 3.518, 4.742] without it,
   i.e. omitting the lattice correction biases estimates **non-uniformly** (+23% on the
   best source, +5% on the worst), which is exactly the direction that would corrupt a
   precision weighting. At n_pair 1,864 the SE on sigma_s is 0.107, so a one-point gap is
   9.3 sigma. Payoff scales with the precision ratio: 1.6% at 1.25x, 9.7% at 1.75x, 18.9%
   at 2.25x. **Gate**: ship iff max/min sigma_s > 1.25 AND the spread exceeds the 95th
   percentile of a source-label permutation null. **Control validated in simulation**:
   real spread 2.269 against a permuted null of 1.060 with 5-95 percentile [1.016, 1.117],
   a separation of 37.7 permutation sd.
   **Note this is NOT the closed outlet-accuracy-weighting lane.** That lane weighted
   sources by their measured ACCURACY against outcomes and was reverted. This weights by
   measured NOISE, is estimated with no labels and no outcomes, and is therefore immune to
   the power problem that closed the accuracy lane.
2. **Coverage-aware reliability shrinkage lambda_k. This SUPERSEDES the M4 design as
   written, and its gate design is the reason. (~4h.)** The correct shrinkage is
   `lambda_k = sigma_true^2 / (sigma_true^2 + sigma_pub^2 / k)`, which is **0.705 at k=1
   against 0.877 at k=3**: a player 15 FV above the mean should be predicted 10.57 with one
   source and 13.16 with three, a **2.59 FV gap that a single hand-set constant gets wrong
   for every k**. That is precisely the D10 defect, and this is the principled replacement
   for `SINGLE_SOURCE_K = 0.5` / `SINGLE_SOURCE_PRIOR = 35`.
   **THE GATE INSIGHT, which would have wasted the lane**: because coverage correlates with
   level, this is worth 0.71% of reducible MSE on the LABELED frame but **2.57% on the
   SERVED frame, a 3.6x under-crediting**, and the labeled-frame MDE on delta-R^2 is 0.054
   against an effect of ~0.007. **Pre-registering a pooled delta-R^2 gate is
   pre-registering a null.** Gate instead on the INTERACTION: regress
   `y ~ x_obs + x_obs * (k - k_bar)` and test the interaction term. Simulated power at
   n=2,000 is **78.0%** (45.5% at n=1,000, 97.2% at n=4,000). Control: permuted-k
   interaction, verified at a 5.2% false-positive rate against a nominal 5%.
   **Refinement available for free**: the lattice is properly a COARSENED-DATA problem
   (Heitjan-Rubin), where FV 45 means latent talent in [42.5, 47.5). An interval-censored
   likelihood is simpler than any IRT threshold model, recovers the 2.083 FV^2/source that
   quantization destroys, and yields a **player-specific posterior variance**, so {45, 45}
   and {40, 50} are correctly distinguished despite identical means. That posterior
   variance is a strictly better input to lambda than k alone.
3. **THE FAIRNESS CONTROL THIS PROGRAM OWES ITS OWN HEADLINE, and it may cut against us.**
   If the model sees per-source values and coverage while the baseline sees only a plain
   mean, then "eFV beats consensus" is partly just "eFV denoises better". That is a real
   serving gain but it is **not new signal**. The clean control is to give the BASELINE the
   same treatment (the sigma_s-weighted, lambda_k-shrunk, lattice-corrected consensus) and
   re-run the head-to-head. **If eFV's edge collapses, the edge was measurement-error
   handling, and it should ship as a BASELINE improvement**, which is cheaper, more
   interpretable and more robust than a model change. Improving the baseline raises the
   bar, which is fairer, not unfair: the current comparison flatters the model. This lands
   in M3 beside the D5 symmetry repair, and the owner should expect the conviction headline
   to get HARDER to clear, not easier. If it survives a denoised baseline, the claim is
   worth far more than it is today.
   Corollary that binds: any denoising that makes the consensus supervised in any way must
   be OOS-gated exactly like eFV, or D5 reappears in a new place.
4. **Per-year source-offset drift test. Cheapest, best-powered check on the board (~2h).**
   About 116 FG/Pipeline pairs per year gives SE 0.356 FV on a year-specific offset, so a
   1.0-point yearly deviation is 2.81 sigma, 1.5 points is 4.21 sigma, and a smooth trend
   across 16 years is detectable at 0.25 FV. This directly tests whether ONE global offset
   is admissible, which is the premise underneath both the current normalization and the
   C-4 options in M7a. Control: permute year labels within source.
5. **Honest stratified reporting plus an ESS gate. (~3h, and it changes what we publish.)**
   Using level alone as the shift variable, the importance weights give **Kish effective
   sample size 390 of 2,000, i.e. 19.5%**, and the **DSL third of the served board rests on
   52 labeled rows** carrying 34.7% of any served-population estimate at an SE 6.2x the
   pooled SE. Weight clipping is a known-size bias purchase and not a fix (clipping at 5
   lifts ESS to 1,064 while moving total-variation distance to the served frame to 0.181).
   **Gate: refuse to publish a pooled served-population accuracy number when ESS/n < 0.25;
   publish the per-stratum table with SE multiples instead.** Control: a random density
   ratio drawn from the same marginal must not move the reported number. This tightens
   M6's reweighted-eval design from "reweight and report one number" to "reweight, report
   the ESS, and refuse the pooled number when it is not supportable".
6. **Extremization of the consensus (~2h, genuinely new here).** A simple average of
   experts who share information is systematically UNDER-confident, so the optimal
   aggregate is extremized away from the center: `mu + gamma * (consensus - mu)` with
   gamma > 1, one parameter, fitted out of sample. **It runs in the OPPOSITE direction from
   the lambda_k shrinkage in item 2, so the two must be fitted JOINTLY or they will
   double-count.** Related and load-bearing: publishers read each other, so conditional
   independence is violated, correlated raters inflate apparent consensus reliability, and
   sigma_s will read too small while effective k reads too large. Estimate the residual
   correlation from the paired data and deflate k accordingly.
7. **Partial pooling, which is NOT the closed full-pooling null.** The measured null was
   FULL pooling (cross-side coefficient sharing, which hurt at full data). Partial pooling
   is the estimator that would have RETURNED "approximately zero sharing" if that were the
   right answer, so the prior result is not evidence against it. Where it can help and full
   pooling could not: cohort-year intercepts (16 groups at ~125 rows each, comfortably
   above the floor for a random effect) and level intercepts (well populated except DSL,
   which is exactly the cell that most needs to borrow strength). Empirical Bayes is
   indistinguishable from full Bayes at 16-100 groups, so no probabilistic-programming
   stack is required, which matters because none is installed.
8. **MRP as the model-based alternative to importance weighting (~1 day, second wave).**
   Varying intercepts and slopes by level and cohort-year, then poststratify to the served
   board's level-by-cohort table. Dramatically more stable than multiplying 52 DSL rows by
   13.35: the model borrows from adjacent levels instead. Unifies items 5 and 7. Gate:
   must beat the clipped-importance-weighted estimate on held-out served-like strata.
   Control: poststratify to a PERMUTED served frame and the correction must vanish. Watch
   the age-period-cohort collinearity trap if both cohort-year and era enter.
9. **Prediction-powered inference over the ~6,000-player unlabeled pool (~1 day, second
   wave).** Use the production model's predictions on unlabeled rows with a labeled
   correction term; inference stays valid even when the model is poor. Realistic gain
   `var_ssl/var_sup ~= 1 - rho * R^2`: at R^2 = 0.10 it is +8.1% effective n, +29% at 0.30,
   +60% at 0.50. Real but not transformative, and the right use is inference ON THE SERVED
   FRAME rather than chasing R^2.

**Rejected in this lane, and two of these correct ideas I would otherwise have planned.**
Quantile mapping, optimal transport and any marginal-matching harmonizer AS THE SERVED MAP:
**this is now understood, not just observed.** The best linear predictor of latent talent
has dispersion `sqrt(lambda) * sigma_true`, deliberately NARROWER than the reference
marginal, while marginal matching forces the reference's dispersion and is therefore biased
outward by construction, and **worst for exactly the noisiest source you most want to
down-weight** (RMSE gain of BLP over matching: 3.0% for a faithful source, 7.1% for a noisy
one). Confirmed end to end: under a stretched basis change a distributional-transform map
beats the flat offset by 22.4% RMSE, but under a COMPRESSED basis it LOSES to the flat
offset (3.230 against 3.054), because stretching a compressed noisy source re-amplifies its
noise. **This retires the OT/quantile-map idea as a primary lane and explains our own
2026-07 quantile_map failure mechanistically.** The distributional transform survives only
as a shape DIAGNOSTIC and an affine re-basing, gated on a dispersion ratio differing from 1
by more than 3 sigma, and never applied to a compressed source. (Worth noting what the
diagnostic already shows: the DT map differs from the flat offset by +2.1 FV at grade 35
and about -0.4 in the middle, so **the incumbent's harmonization error is concentrated at
the BOTTOM of the scale, which is where the DSL players who are 34.7% of the served board
live.** The harmonization defect and the shift defect compound.)
Also rejected: full Dawid-Skene confusion matrices (121 free parameters per publisher on an
11-grade scale with 3 publishers, over-parameterized, and it discards ordinality);
full graded-response or many-facet Rasch as the PRODUCTION aggregator (thresholds and slopes
buy 0.5-1% against precision weighting's 8.7%, i.e. 20x the implementation cost for the
smaller half; a just-detectable 3-sigma slope difference explains 0.48% of residual
variance, while one large enough to explain 10% would be 13.7 sigma and we would already
know); **global disattenuation of the consensus coefficient** (correct for etiologic
inference, WRONG for prediction, since we would disattenuate at fit time and re-attenuate at
serve time; only DIFFERENTIAL attenuation across k is a real defect, and that is item 2);
SIMEX (diagnostic-grade only, since sigma_pub is exactly identified from replicates so the
extrapolation step adds variance for nothing); Heckman selection correction (needs an
exclusion restriction driving publisher coverage but not WAR, and no credible one exists
here; prefer pattern-mixture by coverage pattern plus tipping-point sensitivity);
unclipped importance weighting for a pooled served number (ESS 390); KLIEP / uLSIF / KMM
(the shift variable is categorical, so direct stratum ratios are exact and kernel
density-ratio machinery is unnecessary); self-training or pseudo-labeling the unlabeled pool
(confirmation bias with no validity guarantee, and PPI gives the same data usage WITH
validity); probabilistic-programming hierarchical rater models (not installed, and empirical
Bayes matches them at our group counts).

**One suggestion held back deliberately.** The research proposed Plackett-Luce aggregation
over published ordered lists as scale-free information immune to the offset, the lattice and
the era-dependent basis. That is a good idea in general and it is **already closed here**:
lane J1 ran on 2026-08-07 and returned NULL / FAIL on its pre-registered clauses, and the
sizing premise failed because 92.0% of FanGraphs ranked rows carry ORG ranks rather than
global ones. The one live thread is that MLB Pipeline's global segment read +0.093 at
p = 0.008 while failing only the two-segment sign clause. **Do not reopen the lane. At most,
register a bounded, pre-registered revival keyed to that single segment**, and only after
the M1 floors exist, so it is gated properly rather than re-litigated. This is recorded here
so a future session does not rediscover the idea and mistake it for new.

### 9.4 What this section changes, and what it costs

**Sequencing.** The label-free consensus items (9.3 items 1, 2, 4, plus the fairness
control in item 3) are roughly 12 hours combined, attack the defects with the best-measured
effect sizes, and carry validated permutation nulls. The distribution items (9.2 items 1,
2, 4, 7) are the highest-value accuracy work in the plan and are rank-invariant. The
measurement items (9.1 items 1, 2, 3) are cheap and convert existing nulls into knowledge.
Everything else is second wave.

**Where each folds in**: 9.1 into M1 (with items 1 and 2 also rewriting how every other
lane REPORTS its null); 9.2 into M5 and R2 (and R2's family choice is now decided: IDR
cut at the four thresholds, gated on RPS with a CORP decomposition); 9.3 items 1, 2, 4, 6
into M4 (whose gate design is superseded), item 3 into M3, item 5 into M6, items 7, 8, 9
into a second wave.

**The three claims from this research that most change the plan**, each stated so a
verifier can attack it: (1) more cohorts cannot fix our power, because refit variance is
53-78% of the floor and infinite test n buys only 11-27%; (2) the harmonization prize is
bounded at 10.60 FV^2 and is 56% collected, while DENOISING is open at 1.19x on
single-source rows, so the two must stop being one word; (3) our conviction headline has
never been run against a denoised baseline, and doing so may reduce eFV's measured edge.

## 10. Definition of done

Wave 0 green baseline; all seven M-lanes delivered with verified gate docs; R-lanes
shipped or recorded as gated no-ships with their floors; both estimators wired and
published on every scoreboard statistic; the consolidated verdict ledger written; no
claim anywhere in served copy that a derived verdict does not back; suite green in a
fresh process; memory updated. The plan is also DONE-enough at the end of wave 1 if the
owner stops there: wave 1 alone converts every open conviction question into a certified
answer or a certified power bound, which is the ask's center of mass.
