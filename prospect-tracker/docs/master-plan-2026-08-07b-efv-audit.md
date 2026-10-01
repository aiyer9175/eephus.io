# Master plan 2026-08-07b: audit of eFV, consensus FV, surplus, and every eFV driver

Written for the executing session (Claude Opus 5, Max / Thinking mode). The planning
session ran a read-only recon over `efv_*.py`, `consensus.py`, `grade_normalization.py`,
`source_backtest.py`, `value_framework.py`, `surplus_backtest_real.py`,
`bayes_trade_value.py`, the committed eval artifacts, and the standing gate docs. Every
claim below carries a file:line or an artifact key. Nothing was edited and no test was run.

Scope: audit the four systems, find and fix bugs, data leaks and measurement issues, and
look for genuine improvement. Those are not separate goals here. On this codebase the
improvements that remain ARE the correctness repairs, and section 1 explains why.

---

## 0. How to use this document

1. Read sections 1 through 4 before touching a lane. Section 1 is the strategic frame,
   section 2 is the closed ledger (do not re-attempt), section 3 is the standing rules,
   section 4 is Lane 0.
2. Run Lane 0 first, in the first hour, alone. It verifies premises. This plan's evidence
   is from 2026-08-07 recon and the nightly box rewrites `data/` between 00:30 and 04:00
   local. **If a number below does not reproduce, stop and re-diagnose rather than
   working the lane as written.** The omnibus-2 plan had 4 of 5 checked premises turn out
   false, and the omnibus-3 plan was wrong in 5 places including its own headline.
3. After Lane 0, lanes A through H are largely independent. Suggested order: B, C, D
   (the three lanes with real statistical power), then A, E, G (measurement and validity),
   then F, H.
4. Every model-affecting change needs: a pre-registered gate doc written BEFORE the fit
   runs, a `data/model_registry.json` row plus an eval artifact (verdict enum
   `validated` / `provisional` / `unvalidated` / `deprecated`; a measured no-ship is
   `deprecated`, never `rejected`), a `MODEL_GLOSSARY` entry, and a fingerprint or epoch
   bump when it re-ranks anything.
5. Losses are committed with artifacts. Marginal is FAIL. One attempt per registered
   experiment.
6. No em-dashes anywhere, including in this document's descendants. Owner rule, lint-gated
   by `test_copy_gates.py` through `tools/strip_emdashes.py --check` and
   `tools/copy_lint.py --check`.

---

## 1. The strategic frame. Read this before choosing what to work on.

### 1.1 The rank-accuracy frontier is closed, and the eval cannot see past it

This is settled by six consecutive programs and it is not worth re-testing:

- `docs/EFV_FRONTIER_AUDIT.md`: "No remaining lever measurably improves eFV's rank
  accuracy, and the eval cannot certify one if it existed."
- `docs/efv-drivers-2026-08-07/GATE_RECORD.md`: six driver arms, six nulls, four of them
  point-negative, every one chosen because its prior pointed positive.
- `docs/EFV_GATE_STANDARD.md` section 6: of 22 shipped features exactly one (hitter `fv`)
  is individually resolvable, and backward elimination is out-of-fold negative at every
  depth. Composition is not measurable in either direction.
- The 11-fold promotion did not buy power. Model-vs-consensus MDE95 measured 0.0440 hit /
  0.0436 pit on the doubled pool against ~0.045 on the old one. The binding term is ridge
  refit variance on a resampled training frame, not test n.

The current published headline makes the point plainly. From `data/xfv_scoreboard_eval.json`
(generated 2026-08-07):

| statistic | eFV | consensus | margin | floor | ratio |
|---|---|---|---|---|---|
| hit pooled rho, n 755 | 0.3993 | 0.3919 | +0.0074 | 0.0440 | 0.17x |
| head to head, identical rows, n 3,210 | 0.3511 | 0.3214 | +0.0297 | 0.0352 | 0.84x |
| block-rho pair-weighted, n 1,645 | 0.3228 | 0.3107 | +0.0121 | 0.0325 | 0.37x |

**A feature-hunting session on the eFV rank model is a session spent producing nulls.**
Do not open one. If the owner asks for one anyway, the answer is section 2.

### 1.2 Where power actually exists

Every pool below is larger, or the statistic denser, than the 755 / 890 fold pool that
gates feature adds. These are the places where a change can be measured and therefore where
a change can honestly ship.

| lane | pool | why it resolves |
|---|---|---|
| B, the label's censoring extrapolation | 993 resolved debuts + 2,131 busts, plus 833 censored rows to correct | Held-out truncation on resolved rows is a direct measurement, not a rank delta. n is large and the estimand is the label itself. |
| C, the served outcome distribution | 2,823 out-of-fold rows (`data/xfv_reliability.json` `pooled_n`) | Log score / ECE on a five-category distribution uses far more information per row than a rank correlation on one summary statistic. |
| D, consensus FV | 4,259 common rows (`data/source_backtest.json` `common_n`) | 4.7x the hitter fold pool. Consensus changes propagate into eFV through its dominant feature, so this is the one place where an eFV input can be improved with resolvable evidence. |
| C/G, surplus pricing | 3,368 listings, 2,236 resolved (`surplus_backtest_real`) | Dollar error is a continuous quantity with a bootstrap that already exists. |

### 1.3 The frame in one sentence

The remaining honest work on eFV is not "make the ranking better". It is: **the numbers
downstream of the ranking (the grade scale, the outcome distribution, the dollars) and the
number upstream of it (the consensus) have never been held to the standard the ranking has,
and that is where both the defects and the improvements are.**

---

## 2. CLOSED. Do not re-attempt any of these.

Re-opening a closed arm costs a session and produces a null. Each entry names its ledger.

**Feature composition.** Do not add and do not remove features on sub-floor evidence
(`EFV_GATE_STANDARD.md` section 6). Specifically closed: `sb_rate_rel`, pitcher `is_lhp`,
hitter bats side, five gated tool-threshold pairs, wRC+ (one attempt spent, re-open
condition consumed), POW+/HIT+/PD+/ISO+ as training drivers, SC+ components as training
features, projected ETA, decimal age, signing bonus and draft slot, `fv_trend`, `pos_prem`,
level-jump, K-BB%, age x level, `iso_rel`, `peak_iso_rel`, game power, command, the
2026-06-22 conditional-power family. Ledgers: `docs/efv-drivers-2026-08-07/GATE_RECORD.md`,
the inline comment blocks in `efv_model.py:95-399`.

**Model-side pooling, alpha and shrinkage tuning, ensembling, monotone tail transforms.**
All null (`EFV_FRONTIER_AUDIT.md` section 3). Spearman is invariant to monotone transforms
by construction, so a tail fix cannot move the rank gate at all.

**Lambda.** Both pins re-swept on the 11-fold basis 2026-08-07 and both held
(`data/xfv_driver_lambda_sweep.json`). Hit 0.70, pit 0.57, both at
`efv_model.py:581`. The sweep's argmax is the clamp floor on both sides at 0.27x its floor
with a CI straddling zero. `efv_model.py:480-483` is the reopening rule; it refuses this.

**Elite-band conviction (the Witt / Julio ask).** Unanswerable at the model layer. The
FV55+ band's own MDE95 is 0.16 hit (n 76) and 0.35 pit (n 26), which is 10x to 25x any
effect this model produces. Any elite-conviction statement has to be a display decision
with a disclosure, or nothing.

**Labels and label sourcing.** MiLB deep backfill (regressed, era-shifted), old-cohort id
resolution as a model input, TJ surgery as a pitcher feature, the 3yr surrogate ladder both
sides, MLB Pipeline historical vintages into consensus (0 of 4,210 live rows overlap).
Ledgers: `docs/SURROGATE_LABEL_PROGRAM.md`, `docs/PITCHER_LABEL_LEDGER.md`, memory
`efv-data-sourcing-program-2026-07-24`. **Note the economic bound**: deleting the entire
censored pitcher block, the maximum perturbation any label instrument can cause, moves the
served board by rho 0.9441. Lane B is scoped inside that bound on purpose, and its value is
correctness plus its effect on Lane C, not rank.

**Do not ship** `anchor_calibration.blend_weight_public` 0.5 to 0.0 (MAE-neutral but
collapses served surplus 96 to 99% for the 77% of the board at FV40-45), the literal
`quantile_map` mid-rank edit, or a deeper lambda cut.

**Consensus source weights.** Reverted to equal 2026-07-25 and the ship gate was hardened
to require a gain the test can resolve (`source_backtest.py:897-915`). Only 2 of 8 outlets
have resolvable history and their precisions are indistinguishable (residual variance
14.362 vs 14.462, CI95 [-0.649, +0.454], `source_backtest.py:900-906`). **Lane D does not
re-fit outlet weights.** It works on recency and shrinkage, which are different parameters
and have never been fitted at all.

---

## 3. Standing rules. Violating these has burned sessions.

1. **pytest and file edits can NEVER overlap, including the orchestrator's own edits.**
   `conftest.py:225-266` snapshots which tracked files are dirty at session start and
   `git checkout`s anything the suite dirtied at session end. A file edited DURING a run
   is silently reverted. This caught the omnibus-3 orchestrator editing
   `tools/strip_emdashes.py` mid-run.
2. **The full suite crashes in one process.** `python -m pytest` hard-crashes near 52% with
   a Windows access violation in the native json decoder inside
   `storage._load_ungraded_by_org`. It is memory exhaustion after repeated 74MB and 11MB
   parses plus sklearn, lightgbm and chromium in one process, not corruption. Rebuild the
   chunked runner (8 test files per subprocess, 33 chunks, roughly 280s) as the first thing
   this session does, and check chunk return codes rather than a parsed total: a naive
   summary parser double-counts `xfailed` as `failed` on the substring.
3. **Run pytest from `prospect-tracker/`.**
4. **After every wave, classify `data/` diffs as timestamp-only versus substantive and
   revert anything no shipped code change requires.** Artifact churn happened twice in
   omnibus-3. Leaderboards cannot regenerate correctly in this sandbox (SSL fails for the
   live fetches), so a locally regenerated leaderboard committed here is a real regression.
   `wire_fv_first_seen.json` has been truncated by an agent twice. **Check
   `git status data/` after every wave, before committing.** The working tree already
   carries nine modified `data/` files at plan time; treat those as the dirty-at-start
   baseline and do not sweep them up.
5. **Exclusive file ownership per agent, enforced in the brief.** Zero collisions across 15
   agents in omnibus-3. When a lane needs a file it does not own it REPORTS the exact edit
   and the orchestrator applies it afterward. Section 9 assigns ownership.
6. **A spec that names a field is not a licence to write it. Check the READ precedence
   first.** The wave-3 board dedupe wrote `_xfv_entry`, which `getEfv()` reads BEFORE
   `_EFV`, and the board served provisional grades unscoped for two waves, demoting 183 rows
   by up to 14.0 FV.
7. **Grades round UP for display (FV and tool grades, ceiling). eFV and "+" stats round
   nearest.** eFV is the documented exception.
8. **Every claimed PASS gets independently re-verified on the real path before shipping.**
   A fabricated PASS reached a ship decision once. Three of five agent verdicts were
   materially wrong in one 2026-07-31 round and the adversarial pass caught all three.
9. Workflow scripts: backticks inside prompt text break the parser. Build prompts as
   `[...].join('\n')` arrays.
10. A test asserting a literal copy string breaks on a legitimate copy improvement. Use
    `_visible_text()` (strip tags) and assert against that.

---

## 4. Lane 0: verify these premises in the first hour, alone, before any lane opens

Report each as CONFIRMED, MOVED (with the new number) or FALSE. Do not proceed on a FALSE
premise; re-diagnose it and say so.

| # | premise | where to check |
|---|---|---|
| 0.1 | Suite is green on the chunked runner, and the pre-existing reds are only the golden fingerprint restamp and any deliberate xfail. | chunked runner |
| 0.2 | `_BLEND_LAMBDA_RESELECT == {"hit": 0.70, "pit": 0.57}` and both eval artifacts report `source: "pinned_reselect"`. | `efv_model.py:581`, `data/xfv_eval.json`, `data/xfv_eval_pitcher.json` |
| 0.3 | `SCORED_YEARS` is the 11-fold 2014-2024 tuple and `xfv_scoreboard_eval.json` was generated on it. | `efv_model.py:81` |
| 0.4 | `_observed_pos_map()` returns `{}` unconditionally and the as-of route `_observed_pos_as_of` reads `positions_played_seasons.json`. **The memory index still lists this as an unfixed defect; recon says wave 6 fixed it. Confirm which is true.** | `efv_model.py:1025-1062` |
| 0.5 | `POS_PREMIUM_USES_OBSERVED is False` and 0 of ~4,046 train+live rows move with it off. | `efv_model.py:1002` |
| 0.6 | `data/source_weights.json` `weights` is `{}`. | artifact |
| 0.7 | `ADOPT_NORMALIZED_CONSENSUS is True` and the shipped correction is the continuous mean offset, not a quantile map. | `consensus.py:153`, `grade_normalization.py:135-158` |
| 0.8 | Calibration version is `isotonic-real-v6-evframe-2026-07-31` and `calibration_zero_cross_mm()` returns `None`. | `value_framework_config.yaml:538`, `value_framework.py:1514` |
| 0.9 | `SERVE_PROVISIONAL_FOR_CONSTANT_COHORT is True` and the routing is scoped (roughly 2,434 rows serve provisional, roughly 184 of the cohort do not). | `efv_score.py:119`, `efv_score.py:64-183` |
| 0.10 | Reliability bust ECE is roughly 0.079 against a 0.10 tripwire, and the per-tier gap runs 0.020 / 0.042 / 0.054 / 0.051 / 0.072 / 0.122 at FV 35/40/45/50/55/60. | `data/xfv_reliability.json` |
| 0.11 | Censored row counts: hit 382 (obs_seasons 2:91, 3:92, 4:127, 5:72), pit 451 (2:119, 3:126, 4:101, 5:105). | the two matrix artifacts |
| 0.12 | `curve_area` in the scoreboard reads eFV 0.8148 against consensus 0.8229, i.e. eFV LOSES the value-capture instrument while winning `top20` by 0.0003. | `data/xfv_scoreboard_eval.json` `top20_capture` |
| 0.13 | The golden `xfv` fingerprint restamp is still owed and one cycle of eFV movement chips is still suppressed (`xfv_history_is_on_board_basis()` reads False until `score_history` restamps). | `test_efv_export.py`, `storage.py:4998` |

---

## 5. The defect ledger. Twenty candidates from recon, ranked.

Each is a claim to VERIFY, then fix if confirmed. Ownership in section 9. Anything that
moves a served number needs its own gate doc.

### P0 candidates (a served number is wrong, or a training feature sees the future)

**D1. Historical consensus points are contaminated by the player's future.**
This is the most important finding in the recon and it appears in no prior audit.
`consensus.build_timeseries` recomputes every historical point from scratch on each run,
and three ingredients of `consensus_fv_raw` are computed over the player's FULL snapshot
history and then applied retroactively to every point:

- `total_fv_instances` is counted with **no date filter** (`consensus.py:1248-1252`) and
  passed as one scalar to every event date (`:1298`). The single-instance pull toward FV 35
  at `consensus.py:775-787` therefore fires on a 2019 point based on whether the player was
  re-graded in 2024.
- `dropped_off_pairs` is computed once over the entire snapshot pool comparing the **two
  most recent** org lists (`consensus.py:1212`, `:1025-1030`) and the resulting `(fv+30)/2`
  shrink is applied at every historical point (`:606-636`). A drop-off detected between the
  2025 and 2026 lists can shrink a 2020 point.
- The grade-normalization remapper keys cells by the snapshot's own year
  (`consensus.py:624`), which is contemporaneous, **except** when a `(source, role, year)`
  overlap is thinner than `_MIN_N = 30`, where `_paired_dists` pools the overlap across all
  years including future ones (`grade_normalization.py:120-127`).

Why it matters: `consensus_fv_raw` at the as-of point is `_FEATURES_HIT[0]` and
`_FEATURES_PIT[0]`, the dominant feature, AND it is the consensus OLS leg of the blend, AND
it is the baseline the model must beat (`efv_model.py:21`, `:2539`). The as-of machinery in
`efv_dataset._asof_point` is correct: it picks the right POINT. The contamination is inside
the point's VALUE.

Required: quantify each of the three channels separately on the training matrices (how many
rows carry a value that would differ if the ingredient were computed as-of), then decide.
The likely repair is to make each ingredient as-of at the point being computed. Expect the
headline OOS to MOVE, possibly down, and that is a true-to-model win, exactly as the
2026-07-24 as-of repair was. Gate it on the leak measurement, never on a downstream rho.

**D2. The label's censoring adjustment is a flat-rate extrapolation, and its bias is
unmeasured.** `efv_dataset._label_6yr` at `:879-894`:

```python
rate = obs_sum / n_obs if n_obs else 0.0
censored_target = round(obs_sum + n_missing * rate, 3)
weight = round(n_obs / TARGET_SEASONS, 3)
```

The module header calls this "KM-from-the-start" (`efv_dataset.py:30`). It is not a
Kaplan-Meier estimator and there is no survival fit anywhere on this path. It assumes a flat
per-season WAR rate across the six-year window. Two known facts point in opposite
directions and neither has been measured on this label: for survivors, seasons 4 to 6 carry
58.9% of WAR mass (`docs/PITCHER_LABEL_LEDGER.md`), which makes flat-rate UNDER-state; and
32.8% of debuted players vanish before season 6, which makes it OVER-state. 833 rows ride
this assumption (382 hit, 451 pit) at `observed_seasons` 2 to 5, and they are exactly the
2021-2024 folds, the recent regime the board actually serves.

This is directly measurable and Lane B owns it.

**D3. The served outcome distribution is measurably miscalibrated, monotonically in
tier, and the tripwire is set above the defect.** From `data/xfv_reliability.json`
(generated 2026-08-06), on the SERVED (`after`, Platt-mapped) curves:

| consensus FV tier | n | gap | realized bust | predicted bust |
|---|---|---|---|---|
| 35 | 626 | 0.020 | 0.9808 | 0.9302 |
| 40 | 1,587 | 0.042 | 0.9351 | 0.8305 |
| 45 | 304 | 0.054 | 0.7336 | 0.6167 |
| 50 | 186 | 0.051 | 0.4570 | 0.5013 |
| 55 | 77 | 0.072 | 0.4416 | 0.4635 |
| 60 | 32 | 0.122 | 0.3125 | (see artifact) |

Bust is under-stated at every tier at or below 45; `good` and `star` are over-stated at 55
and 60 (at tier 55, predicted good 0.2245 against realized 0.1039). Bust ECE is 0.07907
against a `threshold` of 0.10, so `tripped` is `false`. **The tripwire does not fire on the
defect it exists to catch.** Since surplus is `sum(P(bucket) x bucket_surplus)`, an
over-stated `good`/`star` mass at the top of the board is an over-stated price at the top of
the board.

**Before fixing this, answer D4.** If the miscalibration is a censoring artifact the fix
would bake the artifact in.

**D4. The reliability diagnostic divides a censored label by a constant 6.**
`efv_reliability._realized_bucket` (`:90-95`) computes `target_war_6yr / TARGET_SEASONS`
with `TARGET_SEASONS = 6.0` fixed, on a pool prepared as
`_prep(pool, "target_censored", side)` (`:119`), where rows carry `observed_seasons` from 2
to 5 and the production fit weights them by `n_obs/6`. The chain is
`CHAIN_YEARS = range(2016, 2024)`. If D2's flat-rate projection is biased, that bias flows
straight into the "realized bucket" this diagnostic grades against, and the public "model
grading itself" card inherits it. Lane C cannot ship a recalibration until Lane B has
answered this.

**D5. `source_backtest` holds the consensus and eFV to different standards on the same
page.** By the file's own admission at `source_backtest.py:335-336`, the per-source bars
are "the in-sample common-set backtest the sources share" while eFV enters through its
forward-chained OOS protocol. And `consensus_wins` at `:730` is a bare inequality with no
MDE floor, currently reading `true` on a 0.0025 Spearman margin over MLB Pipeline
(consensus 0.2849 vs Pipeline 0.2824), while the eFV claim two blocks away is correctly
gated at `XFV_VS_CONSENSUS_MDE95 = 0.044` and reads "not resolvable at this power". The
same reasoning that produced `XFV_VS_CONSENSUS_MDE95` and `XFV_HEADTOHEAD_MDE95` has never
been applied to the consensus's own claim. Fix: measure a floor for
`consensus_vs_inputs`, gate on it, and either build a forward-chained consensus protocol or
label the bars in-sample where the user reads them.

### P1 candidates (a published claim is wrong, or a diagnostic is blind)

**D6. Three different grades appear on one player card and only one is disclosed.**
Odds (`p_bucket`, `p_bust`) key off `realized_implied_fv`, the RETIRED map
(`efv_score.py:1480`, `:2048`). Dollars key off `xfv_grade_display`, the rank-quantile map
onto the consensus distribution (`efv_score.py:1131-1177`). The board shows `xfv_grade`
from `outcome_implied_fv`. Measured over 9,334 served rows
(`docs/efv-2026-07-31/SURPLUS_PRICING_KEY_GATE.md:35-39`): `xfv_grade_quantile` mean 38.92
sd 5.01, `xfv_grade` mean 32.51 sd 12.36. Registered, not shipped, disclosed in tooltips.
Audit whether the disclosure actually reaches a phone-sized viewport, given the
`.section-sub` clamp defect wave 6 found on exactly that class of text.

**D7. 71% of live board rows carry a grade that is explicitly not outcome-calibrated, and
the site prices dollars off it.** `value_framework.py:2904-2911`: the outcome curve's pool
has no row under consensus FV 34.9, the curve is nearly flat under 45 (0.069 total WAR at
FV35, 0.453 at FV40), and the three sub-floor knots are the `_LOWEND_FG_EXP = 0.45` display
re-spread. The comment ends "A grade under about 45 is a display re-spread. Never present
it as calibrated." Check what the user is told. This is a disclosure question first and a
modelling question second, and section 6 lane C3 scopes the modelling half.

**D8. The displayed grade, and therefore the price, is pool-relative.** `xfv_grade_display`
is a per-side rank-quantile map onto the LIVE pool's own consensus FV distribution
(`efv_score.py:1526-1559`, `:2184-2200`). A player's displayed grade and his surplus dollars
move when other players move, with nothing about him changing. This has never been measured.
Quantify it: replay two adjacent vintages and decompose grade movement into own-rank change
versus pool-composition change. If the pool term is material, it belongs in the movement
engine's de-noising and in the disclosure.

**D9. The consensus has no recency weighting at all.** `build_timeseries` forward-fills
each source's last-known snapshot into every later event date indefinitely and undiscounted
(`consensus.py:1266-1292`). A 2019 FanGraphs 55 votes at full weight on a 2026 point. The
only decay in the whole system is the eFV-layer E-STALE discount
(`efv_dataset.py:88-107`), which is scoped to FV bands 35/40/45 only, ramps between 18 and
30 months, and by design does not touch the DISPLAYED consensus
(`efv_dataset.py:1289-1291`). The UI flag `TOOL_FRESHNESS_DAYS = 365`
(`storage.py:136-141`) only de-emphasizes visually and states "Tool always uses each
source's latest publication regardless of age." Lane D owns fitting a decay on the 4,259-row
pool.

**D10. The consensus shrinkage constants have never been fitted.** `SINGLE_SOURCE_K = 0.5`,
`SINGLE_SOURCE_PRIOR = 35.0` (`consensus.py:127-141`), the `(2/3)*pre + (1/3)*35` single-
instance pull (`:775-787`), and the `(base_fv + 30.0)/2.0` drop-off shrink (`:634`) are all
hand-set. The single-source pull fires on **62.9% of the live board** but only 1.0% of the
backtest window (`consensus.py:1185-1195`), so the parameter that shapes most of what users
see is validated on almost none of the evidence. Note also that
`DEFAULT_SHRINKAGE_K` / `DEFAULT_N_FULL` / `FALLBACK_PRIOR_FV` are labeled INERT
(`consensus.py:124-129`) and `apply_shrinkage` / `compute_prior_mean_fv` (`:907`, `:950`)
are dead code; an earlier audit lost real time to a docstring claiming otherwise
(`consensus.py:1173-1180`). Delete or clearly quarantine the dead path while you are in
there.

**D11. eFV loses the value-capture instrument.** `data/xfv_scoreboard_eval.json`
`top20_capture`: eFV `curve_area` 0.8148 against consensus 0.8229, a margin of -0.0081,
while `top20` is +0.0003. The site sells surplus dollars, which are a value-weighted
quantity, and the headline is a rank correlation, which is not. This cell has never been
investigated and it has no floor. Measure its MDE the same way the others were measured,
then either explain the loss or report it beside the wins.

**D12. The provisional model serves 2,434 board rows on a 2026-07-14 eval with no
gate-standard controls.** `data/xfv_ungraded_eval.json` is a bare Spearman by cohort
(hit all-levels 0.2985, low-minors 0.2369; pit 0.1854 / 0.0867), generated before
`UNCAPPED_GRADE = True` shipped and long before floor routing put those grades on the main
board. No paired bootstrap, no zero-information control, no permutation null, no MDE, no
multi-split average. A served grade is held to `EFV_GATE_STANDARD.md` section 2 and this one
is not. Lane F brings it under the standard. This is the largest single population on the
board graded by an unvalidated model.

### P2 candidates (correctness, hygiene, or a latent path)

**D13.** `prospect_path.py:94-112` builds a second, parallel consensus that bypasses
`consensus.py` entirely: `statistics.median` of each source's latest pre-debut RAW
snapshot. It is the only median consensus in the codebase and the only un-normalized one.
`prospect_path` also owns `_fit_ridge` and `_score`, and `_score` is what the pair-weighting
uses. Determine whether that parallel consensus reaches any evaluated or served quantity.
If it does, it is a second D1.

**D14.** `_load_wag()` (`efv_model.py:613`) reads the CURRENT-state `debuted_value.wag`
block from `debuts.json` to select lambda. Dead today because both lambdas are pinned
(`efv_model.py:808-811`), live the moment a pin is removed. Guard it or document it at the
pin.

**D15.** Live norm blending: `milb_history.league_norms:293-306` blends the current
season's norm with the prior season's weighted by sample count, gated on
`season == date.today().year`. It fires on live rows only, never training rows. Not a leak,
but a train/serve distribution shift that has never been quantified.

**D16.** `_SAME_NAME_NOT_DUPES` is EMPTY (`consensus.py:1357-1359`), so two genuinely
different players whose normalized names collide will merge silently. Given the Jack Natili
and Jose Fernandez incidents, add a detector that reports collisions rather than relying on
an empty allowlist.

**D17.** `milb_missing` fits +0.0397 against a declared sign of -1
(`efv_model.py:135-143`). Recorded as inert (dropping it moves pooled rho -0.00022) and
section 6 of the gate standard forbids removing it on sub-floor evidence. Confirm
`efv_sign_audit` still flags it and that `explainer_narration_risk()` covers it, then leave
it alone. Do not "fix" it.

**D18.** `data/fielding_census_ids.json` has NO builder anywhere in the tree, is frozen
2026-07-30, and is what the published 91.8% pos-census coverage figure is reached through
(`data/xfv_driver_pos_census.json`). It is correctly excluded from the model route and from
deploy. Either write the builder or annotate the figure as unreproducible.

**D19.** `FALLBACK_SB600_NORM` (`level_norms.py:165-168`) is an all-time pooled constant
("2015-2024 empirical medians") feeding `sb_rate_rel`, which is not a shipped feature. Inert
today. Record it as a vintage tripwire on the closed `sb_rate_rel` arm so a future revival
does not reintroduce it silently.

**D20. A test-shape defect worth sweeping repo-wide.** `value_framework_config.yaml:527-534`
records that a cheap naming-prefix assertion placed BEFORE the load-bearing assertion in
`test_calibration_layer_is_real_fit_and_monotone` meant a naming violation short-circuited
the live degeneracy tripwire, so the `ys[0] > 0` check never ran. Grep for the same shape:
any test that leads with a format, prefix or schema assertion before its substantive one has
the same exposure. This is cheap and has already burned the repo once.

**Owed from omnibus-3**, close in Lane H: the golden `xfv` fingerprint restamp (factors
arrays moved from the Pinazzi skip and the stale-chip fix; no served grade moved), one cycle
of suppressed eFV movement chips, registry rows for the six deprecated driver arms, the 15
unclaimed eval artifacts, the 28 artifacts with no self-declared date.

---

## 6. The lanes

Each lane states its question, its instrument, its pre-registered success criterion, and its
stop clause. **Write the gate doc before the fit runs.** Registrations that postdate results
are worthless and the repo's own driver ledger says so
(`docs/efv-drivers-2026-08-07/GATE_RECORD.md` section 0).

### Lane A. Is the gate itself the binding constraint, and can that be fixed honestly?

**A1. Audit the estimator, do not just adopt a tighter one.**
The paired bootstrap resamples train AND test with a refit per draw. That answers "what
would we conclude from a different dataset". A ship decision on a fixed training corpus
arguably wants the conditional-on-train error, which is narrower. **This is a trap dressed
as an opportunity: any change that makes the floor smaller will look like progress and may
simply be power laundering.** So the criterion is not "is it tighter", it is:

- Simulate under the null (a pure-noise column, several seeds) and check the candidate
  estimator achieves nominal 95% coverage. An estimator that under-covers is rejected
  regardless of how much power it appears to buy.
- Simulate under a known-real alternative (the `fv` column itself, the only individually
  resolvable feature) and check it is detected.
- Report both estimators side by side in `docs/EFV_GATE_STANDARD.md`. If the conditional
  estimator passes both checks, it is registered as a SECOND row with an explicit statement
  of what question each answers. It does NOT retire the existing floor and it does not
  retroactively resolve any past null.

Stop clause: if the conditional estimator fails the coverage check, record the failure and
stop. Do not tune it into passing.

**A2. A denser statistic: proper scoring rules as a third gate instrument.**
The model emits a five-bucket distribution and the gate scores a rank correlation on one
summary. A log score or ranked probability score uses more information per row. Measure the
MDE of a feature add on a proper score with the SAME paired bootstrap on the SAME rows, so
the comparison is apples to apples. If the proper-score MDE is materially smaller, register
it as a third instrument in section 3 of the gate standard, with the same carve-out
discipline the AUC row already carries.

**Carve-out to check up front, by analogy with the AUC carve-out at
`EFV_GATE_STANDARD.md:110-133`:** a proper score on the bucket distribution is a function of
the calibration layer, so a calibration change would score as a "model improvement" on it.
Register the instrument for FEATURE adds only, or decompose the score into calibration and
discrimination (a Murphy or Brier decomposition) and gate features on the discrimination
term alone.

**A3. Give `curve_area` a floor and an explanation (D11).** Measure its MDE. If eFV's
-0.0081 loss is inside the floor, say so on the scoreboard. If it is outside, that is the
first resolvable statistic on which consensus beats eFV and it needs to be reported that way
and investigated.

**Deliverables:** `tools/efv_power_lab.py`, `data/xfv_power_eval.json`, a new dated section
in `docs/EFV_GATE_STANDARD.md`, registry rows.

### Lane B. The label. Highest-power lane in the plan.

**B1. Measure the flat-rate projection's bias directly (D2).**
Take every FULLY RESOLVED debuted row (debut year such that debut+5 <= 2025). Truncate its
observed seasons to n = 2, 3, 4, 5. Apply the shipped `_label_6yr` projection. Compare the
projected six-year total to the true one. Report bias and spread by n_obs, by side, by
debut-year cohort, and by realized magnitude (the pitcher-label ledger found the failure is
a two-sided top-tail swap, so a pooled mean will hide it). n is roughly 993 resolved debuts
plus the bust pool; this is a measurement, not a rank contest, and it will resolve.

**B2. If the bias is material, build one replacement and gate it.**
The obvious candidate is a per-season-index profile (mean share of six-year WAR realized in
season k, estimated on resolved rows, forward-chained so a fold never sees its own cohort)
in place of the flat rate. Mandatory controls per `EFV_GATE_STANDARD.md` section 2, plus the
two the pitcher-label ledger added and which are non-negotiable here:

- a **rank-identical level twin** (a label that shifts every value by a constant), and
- a **random-label null band**, and
- a permutation p-value.

The ledger's lesson is exact: "a label-quality scoreboard built on a small held-out blend
Spearman measures label DAMAGE, not label INFORMATION." Score B2 on the held-out truncation
error from B1, which is a direct measurement, and report the downstream rank delta only as
a secondary diagnostic against its own floor.

**B3. Pin lambda during any label experiment.** `_BLEND_LAMBDA_RESELECT["pit"]` used to be
`None`, meaning served pitcher lambda was re-derived each run by `rank_calibration("pit")`,
whose target IS `target_censored`. It is pinned at 0.57 today, so this is currently safe,
but a synthetic label plus an unpinned lambda silently moves the served blend. Assert the
pin in the lab, do not assume it.

**B4. Fix the naming.** `efv_dataset.py:30` says "KM-from-the-start" for something that is
not a Kaplan-Meier estimator. That phrase has propagated into four memory files and at least
two docs. Rename it to what it is (observed-rate tail projection with an exposure weight)
everywhere, in the same commit as B1's measurement.

**Stop clause:** if B1 shows the projection is unbiased within its own bootstrap band across
all n_obs strata, B2 does not run. Record the null, fix the naming, and hand the result to
Lane C, which needs it either way.

**Deliverables:** `tools/efv_label_censoring_lab.py`, `data/xfv_label_censoring_eval.json`,
`docs/efv-2026-08-07b/LABEL_CENSORING_GATE.md`.

### Lane C. The served distribution and the surplus chain. Highest dollar value.

**C1. Resolve the censoring question first (D4), using Lane B's result.**
Re-run the reliability chain with the corrected realized bucket. If the miscalibration in D3
shrinks materially, the finding is "the diagnostic was measuring its own label", which is a
clean, publishable correction and possibly the whole lane. If it survives, go to C2.

**C2. If the miscalibration survives, recalibrate the served distribution.**
Objective: the distribution is consumed as a price, so per the 2026-07-31 owner ruling that
surplus is an expected-value quantity, gate on **calibration** (ECE, reliability slope,
held-out bias) with log score reported beside it, and report MAE as a diagnostic rather than
the arbiter. Mandatory: forward-chained out-of-fold, held-out folds, and a control that
shows the recalibration is not just refitting noise (a permuted-tier twin).

Constraints that bind this lane and must be stated in its gate doc:

- Any change to `p_bucket_given_fv` or the Platt layer moves surplus dollars for the whole
  board and requires a `prospx_current.yaml` re-capture INSIDE
  `with vf.valuation_set("prospx_current")` plus a re-stamp of the 20-cell acceptance grid
  at `test_valuation_sets.py:66-79` and the FV50 literal at `:150`. Capturing on the default
  set silently yields a different grid (pitcher FV60 reads 75.2 rather than the correct
  81.3). This has cost a full cycle before.
- Odds stay on the realized grade and dollars stay on the display grade
  (`efv_score.py:1137-1139`). Do not "unify" them as a side effect; that is D6 and it is an
  owner decision, not a lane decision.
- `apply_calibration` is applied exactly once, at the reprice seam (`efv_score.py:1097-1111`,
  called at `:1583-1585`). Verify that is still true before and after.

**C3. The sub-45 grade scale (D7).** Two honest options, and the lane's job is to
recommend one with evidence, not to pick by taste:

- (a) Disclosure only: confirm the user is told that a grade under about 45 is a display
  re-spread and not outcome-calibrated, on the surfaces where it is priced. Cheap, safe,
  and possibly sufficient.
- (b) Extend the calibrated region: the outcome curve is indexed on CONSENSUS FV and the
  sources do not publish below 35, which is why the pool floor is 34.9. But the resolved
  BUST pool has thousands of rows below any published grade, and the provisional model
  produces a production-only ordering for exactly that population. Test whether a
  low-end outcome curve indexed on the provisional model's own output (rather than on
  consensus FV) is estimable, forward-chained, with a permuted control.

Report (b) as an investigation with a verdict, not as a promised ship. If it does not
resolve, (a) is the deliverable.

**C4. Surplus chain re-decomposition.** The frontier audit's decomposition (58% ranking /
16% level / 26% pricing floor, n 2,236) predates the v6 EV re-fit that removed the $0 floor
entirely and re-priced 6,271 rows off zero. Re-run it on the v6 frame. The 26% floor term
should be gone; where did it go? Also re-derive the gate currency (+0.01 pooled rho =
-$0.0704M surplus MAE per prospect), because it is quoted in `EFV_GATE_STANDARD.md`
section 4 and was measured on the old frame.

**C5. Per-player dispersion (investigation, not a promised ship).** Today the outcome
distribution is a function of the GRADE alone, so a player graded 45 on 80 DSL plate
appearances and a player graded 45 on four full seasons receive the same distribution and
therefore the same price. One exception already exists and shows the shape of the fix:
`efv_ungraded.thin_sample_p_bust` replaces `p_bust` on provisional rows because the
Clemens-fitted curve was 0.13 to 0.17 too low at grade 35+ for thin rows
(`efv_score.py:1142-1159`). Test whether a reliability-conditioned dispersion generalizes to
the graded pool. Gate on a proper score, mean-preserving by construction (widen the spread,
do not move the mean), with a permuted-reliability control. If it does not clear, this is
one more entry in the loss ledger and that is a fine outcome.

**Deliverables:** `tools/efv_dist_calibration_lab.py`, `data/xfv_dist_calibration_eval.json`,
`docs/efv-2026-08-07b/DISTRIBUTION_CALIBRATION_GATE.md`,
`docs/efv-2026-08-07b/SURPLUS_DECOMPOSITION_V6.md`.

### Lane D. The consensus FV model. Largest pool, least-audited system.

The consensus is a weighted arithmetic mean over normalized per-source grades with a
single-source pull, a drop-off shrink and a ceiling round
(`consensus.compute_consensus_point`, `:545-883`). It is the dominant eFV feature, the
baseline eFV must beat, and a published grade in its own right. It has never been held to
`EFV_GATE_STANDARD.md`.

**D-1. Close the retroactive contamination (D1 above).** Highest priority in the lane.
Measure the three channels separately, then repair. Expect the eFV headline to move.

**D-2. Give the consensus an honest evaluation protocol (D5 above).** Build a
forward-chained consensus backtest (refit anything fitted per fold, score the fold), measure
an MDE for `consensus_vs_inputs`, and gate the published claim on it. If the consensus does
not resolvably beat MLB Pipeline, the page must say so, in the same voice the eFV
head-to-head already uses ("not resolvable at this power").

**D-3. Fit the recency decay (D9).** Candidate: a per-source exponential or piecewise decay
on vote weight as a function of days since that source's own publication date. Fit
forward-chained on the 4,259-row common pool, score on consensus accuracy directly
(Spearman and contributor AUC against realized WAR), with a permuted-date control. This is
the single most plausible real improvement in the whole plan: it is a mechanism nobody has
tested, it operates on a pool 4.7x the eFV fold pool, and it has an obvious prior (a
seven-year-old grade should not vote at full weight).

Interaction to handle explicitly: E-STALE already discounts the MODEL's `fv_effective` in
bands 35/40/45 between 18 and 30 months (`efv_dataset.py:88-107`). If a consensus-layer
decay ships, E-STALE is at risk of double-discounting. Measure the overlap and state the
resolution in the gate doc before shipping either.

**D-4. Fit the shrinkage constants (D10).** `SINGLE_SOURCE_K`, `SINGLE_SOURCE_PRIOR`, the
`(2/3, 1/3)` single-instance pull, the `(fv+30)/2` drop-off shrink. Same protocol as D-3.
Note the sampling problem up front: the single-source pull fires on 62.9% of the live board
and 1.0% of the backtest window, so fitting it on the backtest window and shipping it to the
board is an extrapolation. Say that in the gate doc and bound it, or restrict the fit to the
drop-off shrink, which has better overlap. The ground truth for drop-off is already
measured and strong (dropped-from-lists players bust roughly 91% against roughly 55% for
re-listed controls, `efv_dataset.py:76-79`), so a fitted shrink there has a real prior.

**D-5. Hygiene.** Delete or quarantine the dead `apply_shrinkage` / `compute_prior_mean_fv`
path and the three INERT constants (a docstring claiming they were live already cost one
audit real time). Add the same-name collision detector for the empty `_SAME_NAME_NOT_DUPES`
(D16). Audit the raw-versus-normalized asymmetry at `consensus.py:646-658` and confirm every
consumer of `fv_published` wants raw (`source_backtest.py:178`, `efv_dataset.py:444-445`,
`movement.py:100-116`).

**Do NOT** re-fit outlet weights. See section 2.

**Deliverables:** `tools/consensus_gate_lab.py`, `data/consensus_gate_eval.json`,
`docs/efv-2026-08-07b/CONSENSUS_GATE.md`, registry rows for anything that ships.

### Lane E. Leak and validity sweep, read-only, reports edits

Re-audit the as-of contract from scratch rather than trusting that the 2026-07-24 repair
still holds after dozens of regens.

1. Re-run the violation count: `milb_season - asof_year` on both shipped matrices. The
   repair claimed 0 violations on both sides. Confirm.
2. Enumerate every artifact either matrix reads and classify each as as-of or current-state.
   The recon's classification is in section 5 of this plan's source material; verify it
   rather than copying it.
3. Confirm the level-norm chain is contemporaneous: eFV uses
   `milb_history.league_norms(season, level, group)` through
   `efv_dataset._resolved_norms:481-504`, NOT `level_norms.compute_level_norms`, which is
   `date.today()`-anchored with a trailing window and is display-only. Verify no eFV module
   calls the latter.
4. Verify D13 (the parallel median consensus in `prospect_path`), D14 (`_load_wag`), D15
   (live norm blending), D18 (`fielding_census_ids.json`), D19 (`FALLBACK_SB600_NORM`).
5. Run `efv_sign_audit` including `explainer_narration_risk()` and report anything new.
6. Run the D20 test-shape sweep.

This lane OWNS no source file. It reports exact edits and the orchestrator applies them.

**Deliverables:** `docs/efv-2026-08-07b/LEAK_SWEEP.md`, one row per finding with a verdict.

### Lane F. Bring the provisional model under the gate standard (D12)

`efv_ungraded` grades roughly 5,983 players and, since floor routing shipped, 2,434 of them
serve their provisional grade on the main board. Its eval is a bare Spearman from
2026-07-14, predating `UNCAPPED_GRADE = True` and the routing.

Required: regenerate the eval on the current code with the full section-2 battery (paired
bootstrap resampling train and test with a refit per draw, a row-permuted zero-information
control, a permutation null, and at least four independent time splits), and derive its own
MDE. Report the two-metric gate. Then answer the question the routing decision needed and
never had: **on the routed cohort specifically, is the provisional grade better than the
constant-anchor flagship grade it replaced?** The routing shipped on a coherence argument
(a constant is not a grade), which is sound, but it has never been scored.

Also re-derive `_PROV_RANK_PENALTY` (currently a hardcoded 4 at `prospx/index.html:31243`)
against `data/provisional_calibration_eval.json`'s own estimator B, since the de-cap moved
the grade distribution the penalty was fitted against.

Stop clause: if the provisional model does not clear its own floor against the constant it
replaced, that is a finding about the routing, not a licence to revert it silently. Report
it and let the owner decide.

**Deliverables:** `tools/efv_ungraded_gate_lab.py`, regenerated
`data/xfv_ungraded_eval.json`, `docs/efv-2026-08-07b/PROVISIONAL_GATE.md`, registry row.

### Lane G. Serve-path integrity: does the published accuracy describe the served number?

The eval scores `blend`. The board serves `blend` then the grade map, then floor routing,
then the Statcast overlay, then the injury haircut, then the age and role factors, then
side-fairness, then the display quantile map, then provisional substitution. Nothing scores
the number at the END of that chain.

1. Build an end-to-end probe that takes the SERVED grade for the resolved cohort and scores
   it against realized WAR, so the published claim describes what the site shows. Extend
   `tools/efv_board_serve_probe.py`, which already asserts rendered equals served.
2. Quantify D8 (pool-relative display grade) by replaying two adjacent vintages and
   decomposing movement into own-rank versus pool-composition terms.
3. Verify the live-only overlays are still live-only and never touch the training matrix:
   SC+ tilt, injury factor, age factor, role factor, S-XLINE-4 A/CPX overlay, E-STALE
   `fv_effective`. Note that S-XLINE (the AAA Savant line adjustment,
   `efv_statcast_line.py`, `XLINE_*_DEFAULT = True`) DOES touch training rows by design and
   is contemporaneous; confirm that is still true.
4. Confirm `efv_score.run_live` still abstains on rows with no MiLB block
   (`skipped_no_track`), which is what keeps `milb_missing`'s trained bust penalty off
   current draftees.

**Deliverables:** `docs/efv-2026-08-07b/SERVE_PATH_INTEGRITY.md`, probe extension, one
scoreboard cell if the served-number score differs materially from the published one.

### Lane I. Rank and AUC improvement, added 2026-08-07b on owner ask

Owner asked directly: find specific ways to raise eFV's Spearman and AUC, within cohorts
and holistically; the same for consensus FV; and say whether better MEASUREMENT can raise
the scores. Section 1 says the frontier is closed. That remains true for the thing it was
measured on, which is **feature composition**. This lane is scoped to the levers that sit
OUTSIDE the closed ledger, plus the measurement question, which has a real answer.

**Framing to keep straight, and to state in the gate doc.** Three of the mechanisms below
raise the REPORTED score without the model changing. That is legitimate only if the repair
is validated on its own terms (the label repair is validated by held-out truncation error,
not by the rho it produces). Anything that raises a reported number and is justified BY
that number is circular and must be refused.

**I1. The fit target. Untested and not in the closed ledger.**
`prospect_path._fit_ridge` minimizes squared error on raw WAR. The target is heavily
right-skewed with a point mass at 0 (2,131 bust rows), and the gate metric is a rank
correlation. The closed ledger contains monotone LightGBM, a ridge/GBM stack, and a
two-part P(MLB) x E(WAR|MLB) model, but it does NOT contain "same features, same ridge,
rank-transformed or log1p-transformed target". This is a loss-function change, not a feature
change, so section 6 of the gate standard does not bar it. Prior pointing the right way: the
FV55+ tier is over-predicted in level (10.4 predicted against 7.7 realized), which is where
squared loss concentrates its weight. Gate on pooled rho AND block-rho with the full
section-2 battery, plus the live-robustness clause (max absolute rank shift on the live
matrix), which killed two otherwise-unremarkable driver arms.

**I2. AUC as its own objective. Untested.**
`auc_contributor` (WAR >= 3.0) and `auc_star` (WAR >= 10.0) are threshold metrics and
nothing in the stack is fit to either. Test a direct contributor/star classifier as an
ADDITIONAL rater in `_run_eval`, never as a replacement for the blend. Note the frontier
audit's two-part rejection was measured on the full-pool debut/no-debut AUC, a different
statistic on a different pool, so it does not settle this. **Carve-out that applies:** the
full-pool debut/no-debut AUC is inadmissible for any candidate that can sense a missing MiLB
block (`EFV_GATE_STANDARD.md:110-133`). The contributor/star AUCs are computed on the
debuted pool and are not obviously subject to it, but confirm that before gating on them.

**I3. Sample weighting in the fit.** Production weights rows by `observed_seasons/6`.
Never compared against alternatives despite IPCW machinery already existing in the fairness
eval (`efv_model._sf_ipcw_frame:2277`). This interacts with Lane B: if the censored label is
biased, the weight and the label are two corrections to the same problem.

**I4. The unexplained hitter full-pool loss.** From `data/xfv_eval.json`, cut
`full_pool_km`: consensus 0.3002 against blend 0.2787, **gap -0.0215 on n=1,792**, larger in
magnitude than any margin eFV wins by anywhere. Pitchers go the other way (+0.0158 on
n=1,886). This cell is in no weak-cell list and no scoreboard headline. Derive its MDE (n is
2.4x the debuted pool so the floor should be smaller) and determine whether eFV RESOLVABLY
loses the hitter full pool. If it does, that is the most important accuracy finding
available and it must be published, not buried.

**I5. Per-cohort floors before any per-cohort claim.**
Current weak cells and their n: hit fv_tier 55 (-0.2271, n 46), hit fv_tier 60 (-0.0209,
n 34), hit cohort hs (-0.0182, n 201), hit cohort other (-0.0195, n 170), pit fv_tier 50
(-0.0508, n 101), pit cohort college (-0.0023, n 324), pit cohort hs (-0.0211, n 190),
archetype hs_bat (-0.0277, n 168), hs_arm (-0.0183, n 144). The elite band is already proven
unresolvable (own MDE 0.16 hit at n 76, 0.35 pit at n 26). **Deliverable is a floor per
cell, and an explicit list of which cells can be adjudicated at all.** Any cell whose floor
exceeds its margin is reported as a null and closed, which will likely be most of them. Do
not propose a per-cohort fix for a cell that cannot be measured.

**I6. Consensus FV rank and AUC. The largest real headroom in the plan.**
Runs inside Lane D's protocol (forward-chained, on the 4,259-row common pool, permuted
control), and every arm below is measured on the CONSENSUS's own accuracy, never through a
downstream eFV rho:

- recency decay on vote weight (D9 above). Never tested; forward-fill is indefinite.
- **aggregator functional form**: `compute_consensus_point` takes a weighted arithmetic MEAN
  (`consensus.py:727-729`). Median, trimmed mean and precision weighting have never been
  tried. The 2026-07-25 A/B tested outlet WEIGHTS, which is a different parameter. Note
  `prospect_path.py:94-112` already computes a median consensus for its own purposes, so a
  reference implementation exists.
- the four hand-set shrinkage constants (D10).
- `implied_fv_from_rank` (`consensus.py:316-329`): a hardcoded step function
  (1 -> 70, <=15 -> 60, <=40 -> 55, <=110 -> 50, <=200 -> 45, else 40), never fitted, used
  whenever a source publishes a rank and no FV.

**I7. Can measurement itself raise the score? Answer the question properly.**
Three mechanisms, and the lane must keep them separate in its write-up:

1. **Label-noise attenuation. Raises the reported score, legitimately.** A rank correlation
   against a noisy label is attenuated toward zero, so both eFV and consensus are scored
   below their true correlation, and the GAP between them is attenuated by roughly the same
   factor. 833 of 3,957 label-bearing rows ride the flat-rate projection. **The clean
   experiment holds the pool fixed**: take resolved rows, truncate to n_obs = 2..5, apply
   the shipped projection, and measure how much Spearman and AUC attenuate per unit of
   induced label noise. Then multiply through.
   **Do NOT use the `debuted_km` versus `debuted_resolved` comparison as the estimator.**
   Those are different pools (755 versus 370 rows, older cohorts only), so that contrast
   confounds label quality with cohort composition. It is a hint, not a measurement. Recorded
   because the planning session nearly used it: hit consensus 0.3919 -> 0.4075 and blend
   0.3993 -> 0.4106 both rise, but pit blend FALLS 0.2562 -> 0.2374, which is what a
   confounded contrast looks like.
2. **The AUC positive class is censored. Raises the reported AUC, legitimately.**
   Contributor and star are thresholds at WAR 3.0 and 10.0 applied to `target_censored`
   (`efv_model._auc_breakdown:1757`, `_CONTRIB_WAR`/`_STAR_WAR` at `:599-600`). A
   two-season row's label is his two-year sum times three. Under-projection makes genuine
   contributors false negatives; over-projection does the reverse. Quantify how many rows
   change class under Lane B's corrected label and re-report the AUCs.
3. **Estimator power. Does NOT raise the score.** Lane A1 owns it. A tighter floor makes an
   improvement certifiable, it does not create one, and it must pass the nominal-coverage
   check before it is registered. Say this explicitly wherever the lane's results are
   published so a smaller floor is never read as a better model.

**Also examine, since it moves both the estimate and the floor:** the headline is
pair-weighted by `observed_seasons/6`, giving `n_effective` 594 of 755 (hit) and 696.5 of
890 (pit), and the unweighted floor (0.0376) is tighter than the pair-weighted one (0.0440).
The weighting was adopted as a basis decision, not chosen as an estimator. Ask whether it is
the right estimator for a rank statistic and report both.

**Stop clause for the whole lane:** every arm here is gated by
`EFV_GATE_STANDARD.md` section 2 in full. Marginal is FAIL. One attempt per registered arm.
Expected outcome for I1 through I3 on the base rate of this codebase is null; the lane's
value is that these are the last untested mechanisms and closing them converts "we think we
are at the ceiling" into "we measured the ceiling on every axis we have".

**Deliverables:** `tools/efv_rank_objective_lab.py`, `data/xfv_rank_objective_eval.json`,
`data/xfv_cohort_floors.json`, `docs/efv-2026-08-07b/RANK_AUC_GATE.md`, registry rows.

### Lane J. consensusRank: recover the ordering the FV lattice throws away

Added 2026-08-07b on owner ask: use source RANKINGS alongside source FV grades, so that
rank-only outlets can contribute and eFV gains specificity; build an accuracy-weighted
"consensusRank" analogous to consensusFV.

**This is the strongest untested lever in the program, and it is not in the closed ledger.**
Every closed arm re-combined information the model already had. This one admits information
that exists in the same database table and is currently discarded.

#### J0. The measurement that motivates the lane (taken 2026-08-07b, reproduce before building)

Query `snapshots` (`prospects.db`), which carries `source, snapshot_date, player_key, rank,
fv, fv_plus`:

| source | ranked rows | rows in an FV tie | ties with distinct ranks | median distinct FV per snapshot | median distinct rank | median n |
|---|---|---|---|---|---|---|
| fangraphs | 24,300 | 24,274 (99.9%) | 24,274 (99.9%) | **7** | 100 | 1,005 |
| mlb_pipeline | 18,240 | 18,232 (100%) | 18,226 (99.9%) | **3** | 100 | 100 |
| tjstats | 4,498 | 4,498 (100%) | 4,498 (100%) | **3** | 100 | 100 |
| espn | 252 | 251 (99.6%) | 251 (99.6%) | **3** | 100 | 101 |
| just_baseball | 126 | 125 (99.2%) | 125 (99.2%) | 4 | 63 | 63 |

Largest single tie cell: **626 FanGraphs players all at FV 40 on 2026-08-02, spread across
42 distinct ranks.** MLB Pipeline 2016: 601 players at FV 45.

So the consensus FV, which is `_FEATURES_HIT[0]`, `_FEATURES_PIT[0]`, the consensus OLS leg
of the blend, AND the baseline eFV is measured against, is built from inputs whose own
published ordering is discarded on **99.9% of rows**. A FanGraphs snapshot resolves roughly
1,005 players onto 7 distinct grades. The rank column resolves the same players onto 100.

**This lands precisely on the one weakness the frontier audit could not close.** That audit
concluded the genuine high-end gap is "within-elite-tier DISCRIMINATION (FV55+ realized
spreads far wider than predictions, within-cohort slope ~2.0) = a new-feature problem". Rank
within tier IS that discriminator, and it has been sitting in the snapshots table since 2011.

#### J0b. Two owner premises the data corrects. State these back before building.

1. **JustBaseball DOES publish FV grades.** 126 rows, all 126 carry an `fv`
   (`rank-but-no-fv` = 0). The sample confirms real varying grades (Konnor Griffin rank 1
   FV 70 on 2026-03-04; Jesus Made rank 1 FV 60 on 2026-06-04).
2. **The genuinely rank-only population is small today**: Baseball America 100 rows on ONE
   date (2026-06-03), MLB Pipeline 538, tjstats 4. Roughly 642 rows total.

So the payoff is NOT mainly "admit rank-only outlets", which is worth a few hundred rows. It
is **recover the discarded within-tier ordering from the outlets that already contribute**,
which is roughly 47,000 ranked rows. The owner's instinct is right and the prize is about
70x larger than the stated rationale, in a slightly different place. Admitting Baseball
America comes free once the machinery exists.

#### J1. The gate-opening measurement. Run this BEFORE building anything.

**Question: within a single (source, snapshot_date, fv) cell, does that source's own rank
predict realized WAR?** If it does not, the whole lane is dead and costs one day. If it
does, the lane is justified on a pool of tens of thousands of rows.

Protocol: restrict to resolved rows (label available), group by (source, date, fv), keep
cells with n >= 5, compute a within-cell rank concordance against realized WAR, pool across
cells with cell-size weights. **Mandatory control: the same statistic with rank permuted
WITHIN each cell** (identical marginal, no ordering information). Report a permutation null
band. Report separately for FanGraphs and MLB Pipeline, and by FV tier, since the elite
tiers are where the claim matters most and where cells are smallest.

Stop clause: if the within-cell concordance does not clear its permuted control, record the
null and CLOSE the lane. Do not proceed to J2 on a point estimate.

#### J2. Build consensusRank. Design, hardest problems first.

Four structural problems, each with a decided approach:

1. **Heterogeneous list lengths.** FanGraphs publishes roughly 1,005 per cycle, Pipeline
   100, BA 100. A rank of 50 means very different things. Normalize within source and date
   to a common latent scale before aggregating.
2. **Truncation is informative and is not a rank.** Absent from a Top-100 means "worse than
   100th", which is a censored observation, not missing data. Define each source's UNIVERSE
   per date (the population it was ranking) and encode non-listed members as censored below
   the last listed rank. Getting this wrong in the naive direction (drop the unlisted) makes
   consensusRank a top-of-board-only signal and silently selects on quality.
3. **Org lists must never be pooled with global lists.** `consensus._ORG_LIST_LABEL_RE`
   (`:336`) already exists for exactly this and the canary is recorded: Bryan Sanchez's only
   signal was rank 30 on a 2021 Nationals Top-30, the legacy check missed the label format,
   rank 30 inflated to FV 55, and he sorted **#19 overall with zero published FVs**. Reuse
   that regex, do not re-derive it, and pin it with a test.
4. **Per-source per-date scale drift.** JustBaseball's #1 is FV 70 in March and FV 60 in
   June. `grade_normalization` corrects FV scale across sources; there is NO rank analogue,
   and rank normalization is a different problem (it is about list length and depth, not
   grader generosity).

**Estimator, simplest first, escalate only if the baseline clears:**

- **Arm A, baseline: within-source normal scores.** Map each source's rank to a van der
  Waerden normal score over its own list, then take a precision-weighted mean across sources
  on the intersection. Hand-rollable in numpy, no scipy, matches the repo's stated modelling
  constraint (empirical-Bayes by hand, sklearn and lightgbm only).
- **Arm B, challenger: Plackett-Luce latent strength**, fit by minorization-maximization
  updates (roughly twenty lines of numpy, no pymc). Handles variable list lengths, partial
  overlap and censored truncation natively, and returns a continuous latent score with
  uncertainty, which is what a ridge feature wants. Run only if Arm A clears.

**Accuracy weighting: build the mechanism, expect to ship it INERT, and pre-register that.**
The owner asked for accuracy weighting "similarly to consensusFV". The honest read of
consensusFV's history is that its outlet weights were REVERTED to equal on 2026-07-25
because only 2 of 8 outlets have resolvable outcome history and their precisions are
indistinguishable (residual variance 14.362 vs 14.462, CI95 [-0.649, +0.454]). **The same
constraint binds harder here**: Baseball America has one snapshot date, JustBaseball two,
ESPN three. Fitting outlet weights on that is fitting noise, and `source_backtest` already
classifies those three as `insufficient_history`. So: implement the weighting seam, shrink
hard toward equal, and require the same hardened ship gate `source_backtest.py:897-915`
applies to consensusFV. Shipping equal weights is the expected and correct outcome, and it
is not a failure of the lane.

**As-of discipline.** consensusRank must be built as-of from the start. If it is recomputed
over full history it reproduces **D1** on a new artifact, and D1 is the worst defect in this
plan. Every ingredient (universe definition, truncation encoding, any fitted weight) must be
computable from data dated strictly before the point being built.

#### J3. Three routes into the product. Keep them separate, they have different gates.

- **Route 1, the clean experiment: consensusRank as a new eFV ridge feature** beside `fv`.
  Gated at the feature-add floor (0.0193 hit / 0.0127 pit pooled, 0.0216 / 0.0182 block-rho)
  with the full section-2 battery plus the live-robustness clause. Its prior is far better
  than any closed arm because it carries new information rather than a recombination, but
  the bar is the same bar. **This is the arm to run first**, because it does not move the
  baseline and is therefore interpretable.
- **Route 2, the bigger and confounded one: consensusRank refines `consensus_fv_raw`
  itself** (within-tier ordering breaking the 7-value lattice into something finer). This
  moves the model's dominant feature, the consensus OLS leg AND the baseline simultaneously.
  **It must be gated on CONSENSUS accuracy on the 4,259-row common pool, never through a
  downstream eFV rho**, because improving the baseline shrinks eFV's published margin even
  when eFV itself improved. Failing to separate these two would produce a result that looks
  like an eFV regression and is not.
- **Route 3, zero model risk: rank as a display tiebreaker.** The board already orders by
  continuous decimal with a TBS tiebreaker on exact ties. A consensusRank tiebreak is a
  display change, needs no accuracy gate, and is the fallback deliverable if Routes 1 and 2
  both fail.

#### J4. What this lane must NOT do

Do not let consensusRank silently become a second path for a rank-implied FV. The existing
`implied_fv_from_rank` step function (`consensus.py:316-329`: 1 -> 70, <=15 -> 60, <=40 ->
55, <=110 -> 50, <=200 -> 45, else 40) is unfitted and is a FALLBACK used only when a player
has zero explicit FVs (`consensus.py:757`). Fitting that step function is Lane I6's job.
consensusRank is a separate quantity on its own scale and conflating the two would make both
unmeasurable.

**Deliverables:** `tools/consensus_rank_lab.py`, `data/consensus_rank_eval.json`,
`data/consensus_rank.json` (as-of, if it ships), `docs/efv-2026-08-07b/CONSENSUS_RANK_GATE.md`,
registry rows, glossary entry if it reaches a surface.

### Lane K. Accuracy-weighted TOOL grades, and the training-data backfill

Added 2026-08-07b on owner ask: can we accuracy-weight tool grades by source accuracy?
Answer: yes, and this is the ONE weighting problem in the system with a real chance of
clearing its gate. Also records the Baseball America decision so it is not re-litigated.

#### K0. Coverage, measured 2026-08-07b from `snapshots.tools_json`

| source | rows | with tools | share | span |
|---|---|---|---|---|
| fangraphs | 24,503 | 24,501 | 100% | 2017-02-15 .. 2026-08-02 |
| mlb_pipeline | 18,778 | 18,240 | 97% | **2011-01-22** .. 2026-08-07 |
| tjstats | 4,502 | 4,202 | 93% | 2026 only |
| just_baseball | 126 | 126 | 100% | 2026 only |
| espn | 252 | 131 | 52% | 2025-2026 |
| baseballamerica | 100 | **0** | 0% | 2026-06-03 |

Shared vocabulary across sources: `hit`, `game_pwr`, `raw_pwr`, `speed`, `field`, `throw`
(hitters); `fb`, `cmd`, `ch`, `cb`, `sl`, `ct` (pitchers). JustBaseball additionally
publishes `pitch_sel`. **Baseball America carries no tool grades at all**, so the BA
question and this lane are disjoint.

#### K1. Why this is better powered than the FV weighting that failed

The FV outlet weights were reverted to equal on 2026-07-25 because only 2 of 8 outlets had
resolvable outcome history and their precisions were indistinguishable (residual variance
14.362 vs 14.462, CI95 [-0.649, +0.454]). Four things differ here:

1. **Five to seven observations per player instead of one.** Each player contributes a full
   tool row, so n multiplies rather than the ~4,259-row FV pool.
2. **Each tool predicts a SPECIFIC, directly measured quantity**, not a six-year WAR total.
   Speed maps to Statcast sprint speed, `fb` to fastball velocity, `raw_pwr` to max exit
   velocity or barrel rate, `throw` to arm strength, `field` to OAA. These are instrument
   readings, not multi-year aggregates of a noisy outcome.
3. **The label horizon is SHORT.** Sprint speed and fastball velocity are measurable in a
   player's first MLB game. The label-horizon trap that dominates every eFV lane (best-measured
   cohorts are unresolved, resolved cohorts predate measurement) does not bind here.
4. **The machinery already exists.** `efv_tools.py` (397 lines) computes per-tool eFVs
   "grounded in the realized MLB stat each tool predicts", so the tool-to-outcome mapping is
   built and validated. **Read it and reuse its mapping. Do NOT invent a new one.**

#### K2. Protocol

Per `(source, tool)`, forward-chained, score the source's published grade against the
realized quantity on players who reached MLB. Derive a precision per cell, shrink hard toward
equal, and require the same hardened ship gate `source_backtest.py:897-915` applies to FV
weights (a gain larger than the test can resolve, on both metrics).

Mandatory controls, in addition to the section-2 battery:
- **Permuted-source-label control.** Reassign grades to sources at random within a
  (player, tool, date) cell. If the permuted weights score as well, there is no result. This
  is the control whose absence produced the FV weighting that had to be reverted.
- **Per tool, never pooled.** A source may read power well and hit poorly. A pooled weight
  would average a real signal against a real anti-signal and report zero.
- **State the survivorship boundary.** Only players who reached MLB carry Statcast, so this
  measures tool accuracy AMONG DEBUTS, which is not tool accuracy overall. Where AAA Savant
  coverage allows (2021+), widen the pool and report both.

Expected honest outcome: tjstats, JustBaseball and ESPN are 2026-only and have no
forward-chained history at all, so they shrink to equal exactly as the FV outlets did. The
lane realistically weights **FanGraphs against MLB Pipeline**, which is the same two outlets
as before, but with roughly 5x the observations against a high-precision short-horizon label.
That is the axis on which the FV attempt failed, so a different verdict here is plausible
rather than wishful. **Pre-register that shipping equal weights is an acceptable outcome.**

#### K3. Where a weight would go, two routes with different gates

- **Route 1: re-weight the tool CONSENSUS** that feeds `tools_consensus` on the dated
  snapshot point. Gated on tool accuracy directly, on the tool pool, never through a
  downstream eFV rho.
- **Route 2: the eFV features.** `tool_hit` and `tool_speed` are in `_FEATURES_HIT`,
  `tool_fb` is in `_FEATURES_PIT`, and they ride the dated consensus point
  (`efv_dataset.py:452-453`). A re-weighted tool consensus moves those three columns, so it
  is gated at the feature-perturbation floor, not the feature-add floor, and it needs the
  live-robustness clause.

#### K4. Baseball America. DECISION RECORDED, do not re-litigate.

The owner asked whether BA's Scouting Grades (FV, rank, tools) could be pulled through a
paywall-circumvention service for training use only. **Declined, and no circumvention path
is to be built.** The grades are the product BA sells; a non-display use addresses
redistribution but not acquisition, and the ask was for an industrialized backfill across
30 clubs and multiple decades.

This is also what this repo already decided on its own evidence. `docs/SOURCE_AUDIT.md` and
the 2026-07-24 source survey classify Baseball America as one of the two **best LICENSING
targets** (alongside The Athletic / Keith Law), not a scrape target. The codebase has an
established owner-endorsed pattern for exactly this: the open SportsCardsPro action is a
written-permission email, taken because their terms forbid third-party-accessible use
without one. **The BA path is the same email.** Note also that BA carries 0 tool grades in
the tree today, so licensing BA would add FV and rank, not tools, and does not block K1-K3.

#### K5. The legitimate backfill that IS available, and is currently declined for the wrong reason

`mlb_pipeline` GraphQL (`data-graph.mlb.com/graphql`) is **open and unauthenticated**, the
repo already reverse-engineered its grade schema
(`gradesHitting` / `gradesPitching` as key-value lists, Overall = FV, hitter
Hit/Power/Run/Arm/Field, pitcher FB/CB/SL/CH/Control), and `pipeline_vintage.py` plus
`data/pipeline_vintages.json` already exist with boards 2015-2026 at 100% mlbam coverage.

Pipeline vintages were declined for consensus on 2026-07-24 because **0 of 4,210
live-scored prospects overlap a vintage grade**. That reasoning is correct for the LIVE
BOARD and irrelevant for TRAINING, because the eFV training matrix is built entirely on
historical decision cohorts (2011-2024). **Re-examine it as a training-data backfill under
its own gate**, and check specifically whether the org Top-30 history is fully ingested or
whether the hardcoded `{y}-01-22` interval in `MLB_PIPELINE_ORG_INTERVALS` left gaps.

Carry the Test-1 warning: a previous MiLB deep backfill REGRESSED the model (ridge
debuted_km 0.3854 to 0.3678) because the frozen model was co-adapted to treat old rows as
production-neutral and old-era production is era-shifted. The pre-registered revival
condition was **era control OR symmetric bust-side coverage**. Any grade backfill inherits
that condition: backfilling grades for debuted rows but not bust rows reproduces the
"has-a-grade correlates with survival" leak in a new place.

**Deliverables:** `tools/tool_grade_weight_lab.py`, `data/tool_grade_weight_eval.json`,
`docs/efv-2026-08-07b/TOOL_GRADE_WEIGHT_GATE.md`, registry rows, and a one-paragraph BA
decision note in `docs/SOURCE_AUDIT.md`.

### Lane H. Close-out and hygiene

Golden `xfv` fingerprint restamp with a note. Registry rows for the six deprecated driver
arms. The 15 unclaimed eval artifacts. Self-declared dates on the 28 artifacts that lack
them (they currently fall back to file mtime, which is meaningless on a box whose nightly
runs `git checkout`). Registry and `MODEL_GLOSSARY` entries for everything this program
ships, bidirectionally (the glossary link fails either way if split). Confirm no registry
row links to an artifact under `docs/` or `tools/`, since neither deploy path ships those
and that produced four 404 links once already.

---

## 7. What this program does NOT do

State these back to the owner if asked, rather than quietly doing them:

- It does not add or remove eFV features.
- It does not move either blend lambda.
- It does not re-fit consensus outlet weights.
- It does not attempt an elite-band conviction change at the model layer.
- It does not flip `POS_PREMIUM_USES_OBSERVED`.
- It does not unify the three grades on a card (D6). That is an owner decision.
- It does not change `blend_weight_public`.

---

## 8. Owner decisions to surface (do not block on them; note them and proceed)

1. **If Lane D-1 confirms the retroactive consensus contamination, the eFV headline will
   move and probably down.** The 2026-07-24 precedent says ship the correctness repair and
   restate the headline. Confirm the owner still wants that ordering when the number is on
   the table rather than hypothetical.
2. **If Lane C-2 recalibrates the distribution, every surplus dollar on the board moves**
   and `prospx_current.yaml` plus roughly 20 test literals get re-stamped. That is the
   sanctioned coordinated re-anchor, done twice before, but it is a board-wide dollar move.
3. **D6, the three-grade problem.** Odds on the retired map, dollars on the quantile map,
   display on the outcome map. Unifying them is a real product change with a real accuracy
   argument on both sides. Surface the measurement; do not pick.
4. **D7 option (a) versus (b)** for the sub-45 scale.
5. **Lane F's verdict on floor routing** if the provisional grade does not clear the
   constant it replaced.

---

## 9. Waves and exclusive file ownership

Exclusive ownership is enforced in each agent brief. A lane that needs a file it does not own
REPORTS the edit; the orchestrator applies it between waves.

**Wave 0 (serial, orchestrator only).** Rebuild the chunked suite runner. Run Lane 0. Snapshot
`git status data/` as the dirty-at-start baseline.

**Wave 1 (parallel, 3 agents).** The three lanes with real power, and they are independent.

| agent | lane | owns |
|---|---|---|
| 1 | B, label censoring | `efv_dataset.py`, `tools/efv_label_censoring_lab.py` (new) |
| 2 | D, consensus | `consensus.py`, `grade_normalization.py`, `source_backtest.py`, `tools/consensus_gate_lab.py` (new) |
| 3 | E, leak sweep | READ-ONLY, owns nothing, reports edits |

**Wave 2 (parallel, 3 agents).** Lane C depends on Lane B's answer, so it starts here.

| agent | lane | owns |
|---|---|---|
| 4 | C, distribution and surplus | `efv_reliability.py`, `value_framework_config.yaml`, `tools/efv_dist_calibration_lab.py` (new), `tools/fit_surplus_calibration.py` |
| 5 | F, provisional | `efv_ungraded.py`, `tools/efv_ungraded_gate_lab.py` (new) |
| 6 | A, measurement | `tools/efv_power_lab.py` (new), `tools/efv_scoreboard.py`, `docs/EFV_GATE_STANDARD.md` |

**Wave 3 (parallel, 2 agents).**

| agent | lane | owns |
|---|---|---|
| 7 | G, serve path | `efv_score.py`, `tools/efv_board_serve_probe.py` |
| 8 | H, close-out | `data/model_registry.json`, `MODEL_REGISTRY.md`, `docs/` |
| 9 | I, rank and AUC | `tools/efv_rank_objective_lab.py` (new), `prospect_path.py` |
| 10 | J, consensusRank | `tools/consensus_rank_lab.py` (new), `consensus_rank.py` (new) |

**Lane J's J1 measurement runs in WAVE 1, alone and early**, because it is cheap, it is
read-only against `prospects.db`, it collides with nothing, and its verdict decides whether
the largest build in the program happens at all. The rest of Lane J waits for Lane D, since
J2 must be as-of and Lane D owns the as-of repair it would otherwise reproduce.

Lane I is sequenced LAST on purpose even though it answers the owner's most direct
question. I1 through I3 need Lane B's label verdict (a rank arm measured against a biased
label is measuring the bias), I6 needs Lane D's contamination repair (fitting an aggregator
on a contaminated history fits the contamination), and I7 mechanism 3 needs Lane A1. Running
it first would produce numbers that Lanes B and D then invalidate. If the owner wants an
early read, I4 and I5 are the two arms that depend on nothing and can run in wave 1.

`efv_model.py` is orchestrator-only throughout: three lanes need to read it and none should
write it unopposed.

After each wave: verify serially, classify `data/` diffs against the wave-0 baseline, revert
anything no shipped code change requires, then commit per lane.

---

## 10. Definition of done

1. Every one of D1 to D20 has a verdict: CONFIRMED and fixed, CONFIRMED and ledgered as an
   owner decision, or FALSE with the evidence that refuted it.
2. Every shipped change has a pre-registered gate doc, an eval artifact, a registry row and
   a glossary entry, and every no-ship has the same minus the glossary entry.
3. The suite is green on the chunked runner, with any red explicitly named and explained.
4. `data/` carries only the diffs a shipped code change requires.
5. The scoreboard and the glossary describe the number the site actually serves, with every
   published margin stated against its own floor.
6. A single execution memory records: what moved, what did not, which premises in this plan
   were false, and the loss ledger. Prior programs have been wrong about their own headline
   premise twice in a row; assume this one is too and write down which part.

---

## 11. Source material for every claim in this document

Gate and audit docs: `docs/EFV_GATE_STANDARD.md`, `docs/EFV_FRONTIER_AUDIT.md`,
`docs/EFV_EVAL_BASIS_LEDGER_2026-08-07.md`, `docs/efv-drivers-2026-08-07/GATE_RECORD.md`,
`docs/PITCHER_LABEL_LEDGER.md`, `docs/SURROGATE_LABEL_PROGRAM.md`,
`docs/efv-2026-07-31/SURPLUS_PRICING_KEY_GATE.md`,
`docs/efv-2026-07-30/SURPLUS_EV_OBJECTIVE.md`,
`docs/efv-2026-07-30/TRADE_ARCHETYPE_FLOOR_GATE.md`,
`docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_GATE.md`,
`docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_SHIP.md`, `docs/archive/REVIEW_QUEUE.md` item 15.

Artifacts: `data/xfv_eval.json`, `data/xfv_eval_pitcher.json`,
`data/xfv_scoreboard_eval.json`, `data/xfv_mde_floor.json`, `data/xfv_headtohead_gap.json`,
`data/xfv_reliability.json`, `data/xfv_ungraded_eval.json`,
`data/provisional_calibration_eval.json`, `data/source_backtest.json`,
`data/source_weights.json`, `data/xfv_driver_*.json`, `data/surplus_calibration_fit.json`,
`data/fv_outcome_curves_pooled.json`.

Code anchors are cited inline throughout sections 4 and 5.
