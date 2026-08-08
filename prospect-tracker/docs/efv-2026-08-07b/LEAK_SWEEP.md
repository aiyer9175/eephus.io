# Lane E: leak and validity sweep (2026-08-07b)

Read-only audit. This lane owns no source file. Every edit it wants is reported to the
orchestrator, not applied here. No pytest was run.

## Pre-registration (written BEFORE any measurement was run)

Registered 2026-08-07, before the first probe executed. Success criteria are stated per
item so that a null is a recordable outcome, not a failed lane.

| # | Question | Success criterion, declared in advance |
|---|---|---|
| E1 | `milb_season - asof_year` violation count on both shipped training matrices | CONFIRMED if the count is exactly 0 on both sides. Any non-zero count is a REFUTATION of the 2026-07-24 repair and is the lane's headline. |
| E2 | Enumerate every artifact either matrix reads, classify AS-OF vs CURRENT-STATE by reading code | A finding only if a CURRENT-STATE artifact is read on the training path with a value that varies over time and enters a feature. Classification copied from the plan does not count. |
| E3 | Level-norm chain contemporaneous | CONFIRMED if no module on the eFV import graph calls `level_norms.compute_level_norms`, and `efv_dataset._resolved_norms` routes through `milb_history.league_norms(season, level, group)`. |
| E4a (D13) | Does `prospect_path`'s parallel median consensus reach any evaluated or served quantity? | REACHES = P0 second-D1. Does not reach = P2 latent. Verdict must be backed by an import/call trace, not by reading the module in isolation. |
| E4b (D14) | `_load_wag` current-state read is dead behind pinned lambdas | CONFIRMED dead if both lambda pins are unconditional at the call site and the `_load_wag` return is discarded or overridden. Propose a guard either way. |
| E4c (D15) | Quantify the live-only norm blend train/serve shift | Report the magnitude in feature units on the affected rel-stat features for live rows. A shift under the feature's own sd/10 is a NULL. |
| E4d (D18) | `fielding_census_ids.json` has no builder | CONFIRMED if no writer of that path exists anywhere in the tree. |
| E4e (D19) | `FALLBACK_SB600_NORM` inert | CONFIRMED inert if `sb_rate_rel` is absent from every shipped feature list. |
| E5 | `efv_sign_audit` incl. `explainer_narration_risk()` | Report anything not already in the ledger. D17 (`milb_missing` +0.0397 vs declared -1) is pre-noted as EXPECTED; confirming it still flags is the pass condition. Do not remove it. |
| E6 (D20) | Repo-wide test-shape sweep for a cheap format/prefix/schema assertion placed before the substantive one | List every hit with `file:line`, ranked by how load-bearing the shadowed assertion is. Zero hits is a valid result. |

Numbers below each carry a `file:line` or an artifact key. Where a plan claim could not be
reproduced, the row says FALSE and gives what was measured instead.

---

## Findings, ranked

| # | Finding | Verdict | Class |
|---|---|---|---|
| 1 | The 2026-07-24 as-of repair HOLDS. The plan's stated metric does not reproduce, but the metric is the wrong one. | E1 premise **FALSE**, repair **CONFIRMED** | P1 (doc) |
| 2 | D13. The parallel median consensus DOES reach a served number in `/projections/`. It is NOT a second D1: it is genuinely as-of. | **CONFIRMED reaching, NOT a leak** | P1 |
| 3 | D14. Dead for the served lambda, LIVE in the published eval artifact, and the function's own docstring calls itself "Leakage-free", which is false. | **CONFIRMED dead (served), FALSE claim** | P1 |
| 4 | D15 quantified. Material: 32 of 48 (group, level, stat) cells move the live feature by >= sd/10; live-row-weighted mean 0.209 sd, max 0.434 sd. 94.3% / 91.6% of live rows exposed. | **CONFIRMED, MATERIAL** | P1 |
| 5 | NEW. `stale` measures the STAT gap, not the GRADE gap. The stale-grade configuration has ZERO representation in the bust pool and E-STALE is live-only. | **NEW, CONFIRMED** | P1 |
| 6 | D20. The recorded shape is UNREPAIRED in the exact test that recorded the lesson. 89 repo-wide hits, 15 with a tripwire-flavoured shadowed assert. | **CONFIRMED, still exposed** | P2 |
| 7 | D17. FALSE as stated. `milb_missing` now fits -0.0174, the sign audit is CLEAN on both sides, and `explainer_narration_risk()` returns `{}`. Nothing flags. | **FALSE** | P2 |
| 8 | NEW. `data/xfv_driver_pos_census.json` publishes a `consumer_today` string that the code contradicts. | **NEW, CONFIRMED** | P2 |
| 9 | E3. Level-norm chain is contemporaneous. No eFV module calls `compute_level_norms`. | **CONFIRMED** | clean |
| 10 | D18. No builder exists. Already annotated in code; the artifact itself is not annotated. | **CONFIRMED** | P2 |
| 11 | D19. `FALLBACK_SB600_NORM` is inert. | **CONFIRMED inert** | P2 |
| 12 | E2. No current-state artifact with a time-varying value enters a training feature. | **CLEAN** | clean |

---

## 1. E1. The as-of contract. Repair HOLDS; the plan's metric is the wrong metric.

**Plan claim:** "Re-run the violation count: `milb_season - asof_year` on both shipped
training matrices. The repair claimed 0 violations on both sides."

**Measured, exactly as the plan states the metric:**

| matrix | rows | rows with a milb block | `milb_season - asof_year > 0` |
|---|---|---|---|
| `data/xfv_hitter_matrix.json` | 1,917 | 1,134 | **40** |
| `data/xfv_pitcher_matrix.json` | 2,040 | 1,027 | **40** |

So the metric as written is **FALSE**: it is 40 and 40, not 0. It was 38 and 36 when
`docs/EFV_FRONTIER_AUDIT.md:53-57` first measured it, so this channel has never been
zero and has grown slightly.

**But the metric is not the contract.** `efv_dataset._milb_features:700-706` anchors the
season floor on `cutoff` (the DECISION date), not on `asof_date` (the vintage of the
scouting snapshot):

```python
first_season = decision_year - 1
if cutoff:
    _cy, _cm = int(str(cutoff)[:4]), int(str(cutoff)[5:7])
    first_season = min(first_season, _cy if _cm >= 10 else _cy - 1)
```

Re-run against the code's own rule, with `decision_year = debut_year` for `kind ==
"debuted"` (`efv_dataset.py:1064`, `:1098`) and `decision_year = last_list_year + 1` for
`kind == "bust"` (`efv_dataset.py:1190`):

| matrix | rows checked | `milb_season > first_season` |
|---|---|---|
| HIT | 581 debuted + 553 bust = 1,134 | **0** |
| PIT | 693 debuted + 334 bust = 1,027 | **0** |

`asof_date > cutoff` is 0 on both matrices. So no row uses a snapshot dated at or after
its own decision point, and no row uses a MiLB season that had not ended by its decision
point. **The as-of contract is intact.**

**What the repair actually fixed, and it fixed it completely.** The frontier audit's real
finding was never the `delta > 0` channel; it was the `delta == 0` channel, where row
timing was a near-perfect label proxy. That is now gone:

| channel | 2026-07-24 (frontier audit) | now |
|---|---|---|
| HIT `delta == 0`, of which busts | 360, 344 busts (95.6%) | **22, 0 busts** |
| PIT `delta == 0`, of which busts | 264, 238 busts (90.2%) | **29, 0 busts** |
| `P(kind == bust \| delta == 0)` | 0.956 | **0.000** |

**Are the 40 + 40 a leak?** No. Every one is a `debuted` row whose scouting grade went
stale years before he debuted while he kept playing in the minors: `dashawn_keirsey_jr`
as-of 2019-07-31 with `milb_season` 2023, `cutoff` in his debut year. The decision point
is the DEBUT, the label window starts at the debut, and a 2023 MiLB line is strictly
prior to it. Nothing in the row is future information relative to its own label.

**Verdict:** E1 premise **FALSE** as written; the repair it was checking is **CONFIRMED
INTACT**. Recommendation: state the contract metric in the plan as
`milb_season > first_season(decision_year, cutoff)`, not `milb_season - asof_year`, so a
future re-audit does not re-open a closed finding.

---

## 2. D13. The parallel median consensus reaches a served number. It is not a second D1.

**Confirmed:** `prospect_path._load_db:94-112` builds a second consensus that bypasses
`consensus.py` entirely, `statistics.median` over each source's latest strictly-pre-debut
raw `snapshots.fv`. It is the only median consensus and the only un-normalized one in the
codebase (no `grade_normalization` remap, no single-source shrinkage, no drop-off shrink).

**It reaches a served quantity. Full trace:**

1. `prospect_path.py:112` `fv_pre[pk] = statistics.median(v for _, v in by_src.values())`
2. `prospect_path.py:202` `fv = fv_pre.get(pk)`; a row with no `fv_pre` is DROPPED
   (`acct["no_pre_debut_fv"]`), so this median also decides cohort membership
3. `prospect_path.py:228` `base = _baseline_first3(fv, is_pit, pos, debut_age)`
4. `prospect_path.py:583-584`
   `ic_full = sum(r["baseline"] - r["target"] for r in rows) / len(rows)`
5. `prospect_path.py:649` writes it as
   `calibration_intercept_only.full_window_shift` = **0.2673**, `ship: true`
   (verified in `data/prospect_path_eval.json`)
6. `proj_export._prospect_calibration_shift:846-849` reads exactly that key
7. `proj_export.py:952`
   `mean_path = [round(max(0.0, w - cal_shift / 3.0), 2) if t < 3 else w ...]`

So **every prospect row on `/projections/` has 0.0891 WAR per season subtracted from each
of its first three projected seasons**, and that constant is a function of a median,
un-normalized consensus that exists nowhere else in the tree.

**It is NOT a second D1.** D1 is retroactive contamination: history recomputed with
ingredients drawn from the player's future. `_load_db:105` is
`if r["snapshot_date"] >= dd: continue`, a hard per-player as-of filter, and it does not
recompute a time series at all. There is one point per source per player and every one is
strictly pre-debut. **No leak.**

`test_phase4b_evals.py:236 test_prospect_path_not_dispatched` pins this design: the module
must not be imported by `proj_export`, but the artifact read is explicitly required
(`assert "prospect_path_eval.json" in src`, `:248`). So the reach is intentional and
tested. What has never been recorded is that the constant is derived through a consensus
definition that disagrees with the production one.

**Verdict: CONFIRMED reaching a served quantity; NOT a leak; P1 consistency defect.**
This belongs to Lane D's consensus scope, not to a leak repair.

---

## 3. D14. `_load_wag` is dead for the served lambda, live in the published artifact, and
mis-documented.

**The current-state read is real.** `efv_model._load_wag:613` reads
`debuted_value.wag.regressed_wag` from `data/debuts.json` (2,394 of 2,696 records carry
one). That block is built at `storage.py:10289-10297` from
`career_war.get(p.player_key)` (the player's ENTIRE career WAR to date) baselined against
`_wag_fv = _xfv_by_key[...]["xfv_grade"]` (`storage.py:10288`), which is the CURRENT eFV
grade, itself an output of the model being calibrated. There is no as-of filter on either.

**Dead for the served lambda: CONFIRMED.** `efv_model.blend_lambda:826-829` returns
`_BLEND_LAMBDA_RESELECT[side]` before the WAG branch at `:831` is reachable, and
`_BLEND_LAMBDA_RESELECT` is `{"hit": 0.70, "pit": 0.57}` at `:581` with both sides
non-None. `data/xfv_eval.json` `lambda_calibration.source` reads `"pinned_reselect"`,
confirming the served path.

**NOT dead in the published eval.** `efv_model.run:2500` calls `wag_calibration(side)`
unconditionally, before `blend_lambda` at `:2501`. So the current-state read still
executes on every eval regen, its spearman still decides `lam_selector` at `:2507-2508`,
and the block still ships into the artifact as evidence.

**FALSE claim in the code.** `efv_model.py:630` ends the `wag_calibration` docstring with
`Leakage-free."""`. The regressand `y` is `wg["regressed_wag"]` (`:658`), a
current-state quantity computed over seasons after each fold's decision year. That
sentence is wrong today, and it is exactly the sentence a future reader would rely on when
removing a pin.

**Guard proposed (edit 1 and edit 2 below):** correct the docstring, and make
`blend_lambda` refuse the WAG branch structurally rather than by accident of a pin, so
removing a pin cannot silently re-arm a current-state calibrator.

---

## 4. D15. The live-only norm blend, quantified.

**Mechanism confirmed.** `milb_history.league_norms:293-306` blends the current season's
norm with the prior season's, `w = n_cur / (n_cur + n_prior)`, gated on
`if season == _date.today().year:` at `:294`.

**Never a leak: CONFIRMED.** Zero training rows carry `milb_season == 2026` on either
matrix (HIT max 2025 with n=8; PIT max 2025 with n=8), so the branch cannot fire on a
training row. The train/serve asymmetry is real: every training row's `k_rel` / `bb_rel` /
`iso_rel` / `obp_rel` / `ops_rel` / `era_rel` was computed against a PURE contemporaneous
norm; the live rows' were not.

**Exposure.** Live rows whose FINAL MiLB season is 2026, and therefore blend-exposed:
**2,014 / 2,136 hitters (94.3%)** and **2,259 / 2,465 pitchers (91.6%)**.

**Magnitude.** `_season_rates` (`efv_dataset.py:519-555`) makes every rel-stat a
DIFFERENCE against the norm, so a norm shift of `s` moves the feature by `-s` (scaled down
by the reliability weight `w = exposure/(exposure+K)`, so these are upper bounds).
Reconstructing the unblended norm from the shipped blend, `cur = (b - (1-w)*p) / w`:

| group | level | stat | feature | blend w | norm shift | d(feature) | live sd | d/sd | live rows |
|---|---|---|---|---|---|---|---|---|---|
| hitting | CPX | bb_pct | bb_rel | 0.490 | -0.0145 | +0.0145 | 0.0333 | **0.434** | 297 |
| hitting | A+ | iso | iso_rel | 0.481 | -0.0218 | +0.0218 | 0.0511 | **0.426** | 391 |
| hitting | A | iso | iso_rel | 0.462 | -0.0215 | +0.0215 | 0.0511 | **0.421** | 436 |
| hitting | A+ | ops | ops_rel | 0.481 | -0.0405 | +0.0405 | 0.0982 | **0.412** | 391 |
| hitting | DSL | obp | obp_rel | 0.447 | -0.0150 | +0.0150 | 0.0375 | **0.400** | 341 |
| pitching | CPX | era | era_rel | 0.486 | -0.6963 | +0.6963 | 1.7478 | **0.398** | 312 |
| hitting | AA | iso | iso_rel | 0.471 | -0.0193 | +0.0193 | 0.0511 | 0.378 | 381 |
| pitching | CPX | bb_pct | bb_rel | 0.486 | -0.0121 | +0.0121 | 0.0397 | 0.304 | 312 |
| hitting | AAA | ops | ops_rel | 0.464 | -0.0075 | +0.0075 | 0.0982 | 0.076 (NULL) | 168 |
| pitching | AAA | era | era_rel | 0.450 | -0.0824 | +0.0824 | 1.7478 | 0.047 (NULL) | 196 |

**Summary: 32 of 48 (group, level, stat) cells clear the pre-registered sd/10 bar.
Live-row-weighted mean `|d|/sd` = 0.2088. Max = 0.434 sd.** The shift is one-directional
almost everywhere (the 2026 partial-season norms run HOT at every level except AAA, so
blending pulls them down, so every live player's level-relative rate reads HIGHER than the
same line would have read in training). AAA is the clean level: 5 of 5 hitting cells and
2 of 3 pitching cells are NULLs there, which is exactly what the 2026-07-14 audit note at
`milb_history.py:285-292` predicted (the qualifier-selection skew is a low-level problem).

**Verdict: CONFIRMED, MATERIAL, and not a leak.** This is a genuine train/serve
distribution shift on ~92-94% of served rows, concentrated at DSL/CPX/A/A+/AA, and it is
the first time it has been sized. It is NOT obviously a defect: the blend exists because
the un-blended mid-season norm is the biased one. But the model was fitted on the
un-blended convention, so the shift is real regardless of which norm is "right". Lane C or
Lane D should decide; this lane records the number.

---

## 5. NEW. `stale` measures the STAT gap, not the GRADE gap.

Found while characterising the 40 + 40 rows from E1.

`efv_dataset.py:822`: `"stale": float(decision_year - 1 - final["season"])`. It is the gap
between the decision year and the last MiLB season used. There is **no feature anywhere in
either training matrix for the gap between the decision year and `asof_date`**, i.e. how
old the scouting grade is. The only field naming it is `asof_date` itself, which
`efv_model._vec` never reads.

Measured `cutoff_year - asof_year` (the GRADE gap) on the shipped matrices:

| matrix | kind | n | mean grade gap | fraction >= 2 years |
|---|---|---|---|---|
| HIT | debuted | 845 | 0.36 | **9.7%** |
| HIT | bust | 1,072 | **0.00** | **0.0%** |
| PIT | debuted | 981 | 0.29 | **8.1%** |
| PIT | bust | 1,059 | **0.00** | **0.0%** |

The bust column is 0.00 by construction: `efv_dataset.py:1181` sets a bust's
`cutoff = last_date`, the date of his own final snapshot. So a bust can never be a
stale-anchor row.

And on the 80 `delta > 0` rows from E1, mean `stale` is **0.05 (hit) / 0.07 (pit)** against
**0.66 / 0.56** for the rest: these are precisely the rows with the freshest stats and the
oldest grades, and the model's only staleness feature reads them as the freshest rows in
the pool.

Meanwhile the E-STALE anchor decay (`efv_dataset._stale_anchor_discount:103-122`) is
applied at **`efv_dataset.py:1329` only**, inside `build_live_matrix`. It is the sole
consumer, so the training pool contains no representation of the discounted configuration
at all.

The module comment at `efv_dataset.py:85-94` already states the qualitative version of
this ("~16% of debuted TRAINING rows also carry >1y-stale anchors ... but ALL bust rows
anchor at their final list point ... The model structurally cannot learn the stale-anchor
BUST discount"). Reproduced: debuted rows with grade gap >= 1 are 14.9% (hit) and 15.5%
(pit), consistent with the recorded ~16%. **What is new here is the >= 2 year split, the
exact 0.00 / 0.0% bust column, and the `stale` mean inversion on the E1 rows.**

**Verdict: NEW, CONFIRMED, not a leak.** It is a specification gap: the feature named
`stale` does not measure the staleness the serve path corrects for, and the correction's
own configuration is unrepresented in the label pool it would be validated against. This
is the honest justification for E-STALE being a policy overlay rather than a fitted term,
and it should be recorded that way rather than left implicit.

---

## 6. D20. The test-shape sweep. The recorded shape is unrepaired where it was recorded.

Repo-wide AST sweep over **264 test files**. A hit is a test function where an assertion
about how a thing is LABELLED or SHAPED (`.startswith`/`.endswith`, a schema key-presence
check, `isinstance`/`type`, a key-SET equality, or an equality against a string literal on
a naming-ish slot) executes strictly BEFORE a numeric tripwire (numeric comparison,
`abs()<tol`, `pytest.approx`, or an `all(...)` monotonicity check).

**89 hits. 15 carry a tripwire-flavoured shadowed assertion.** Ranked by how load-bearing
the shadowed assertion is:

### Rank 1. `test_value_framework.py:60-93` `test_calibration_layer_is_real_fit_and_monotone`

**The original, and it is still exposed.** The 2026-07-29 repair recorded at
`value_framework_config.yaml:527-534` conformed the CONFIG NAME so the prefix assertion
would pass. It did not reorder the assertions. Current order:

```
:60  assert cal["enabled"] is True
:61  assert cal["method"] == "isotonic"
:69  assert cal["version"].startswith(("isotonic-real-", "linear-real-")), cal["version"]
:76  assert len(xs) == len(ys) >= 3
:77  assert xs == sorted(xs) and ys == sorted(ys)
:78  assert "REAL-data fit" in cal["fit_provenance"]
:80  assert ("leave-one-year-out" in cal["fit_provenance"] or "LOyO" in ...)
:93  assert ys[0] > 0            <-- THE LIVE DEGENERACY TRIPWIRE
:97  assert ys[-1] > ys[0] * 5
```

Five naming / provenance / shape assertions still stand in front of the tripwire. Any
future version rename, method flip, or provenance re-wording re-masks `ys[0] > 0` exactly
as the v5 rename did. The test's own comment at `:64-68` documents the lesson and the fix
it received was the narrow one.

Two further notes on that test: the comment block at `:84-96` asserts "THIS IS THE LIVE
TRIPWIRE AND IT IS EXPECTED TO FAIL ... ys[0] is 0.0 under v5". That is now stale: the
shipped v6 map has `y_mm[0] = 0.67` (`value_framework_config.yaml:541`), so the tripwire
passes. A reader of that comment would conclude a red line is expected when it is not.

### Rank 2. `test_empirical_anchors.py:92` `test_low_end_anchors_are_present_and_measured`

```
:92  for key in ("20","25","30","35"): assert key in anchors, (...)   # schema presence
:96  assert anchors["40"] < 0.12, (...)                               # measured CI95 bound
```

A missing sub-45 anchor key short-circuits before the FV40 bound is ever checked. Lower
severity than rank 1 because a missing key would independently `KeyError` further down,
but the specific `anchors["40"] < 0.12` claim (2.2x over-statement, per its own message)
never runs if any of four other keys is absent.

### Rank 3. `test_pal_smoke.py:349` `test_rng_plus_is_outfield_only_and_never_admits_an_infield_position`

`assert set(ship) == {"LF","CF"}` (key-set equality) precedes
`assert r and r.get("r",0) > 0.15` (4 shadowed numeric asserts). Widening the whitelist
also silences the correlation floor that justifies the whitelist.

### Ranks 4 to 15 (tripwire-flavoured, lower load)

| file:line | test | cheap assert | first shadowed numeric assert |
|---|---|---|---|
| `test_valuation_sets.py:111` | `test_clemens_default_applies_and_context_restores` | `arb_basis == "prior_season"` | `:112 discount_rate == approx(0.07)` (6 shadowed) |
| `test_pal_smoke.py:381` | `test_rng_plus_is_display_only_and_never_reaches_the_model` | `:381 re.search(...)` on source | `:389 {"plus","fts","season"} <= set(g)` |
| `test_betting_results_refresh.py:243` | `test_the_nightly_actually_reruns_the_backtest` | `:243 "betting_model.backtest(" in daily` | `:249 snap < refit` ordering guard |
| `test_efv_proxy.py:13` | `test_proxy_eval_structure_and_sanity` | `:13 kind == "leading_indicator_not_xfv"` | `:15` (5 shadowed) |
| `test_phase4b_evals.py:107` | `test_eta_artifact_records_the_ship` | `:107 sd["decision"].startswith("SHIP")` | `:109 km_recalibrated.mae < v38_incumbent.mae` (5 shadowed) |
| `test_fa_fit.py:156` | `test_team_baselines_falls_back_when_artifact_is_defective` | `:156 baseline_source == "contracted_core"` | `:160 approx(..., abs=0.11)` |
| `test_positional_fit.py:407` | `test_savant_directional_splits_are_still_unread_by_the_shipped_model` | `:407 set(row) == {...}` | `:408 approx(3.0)` |
| `test_statcast_aaa_hitters.py:42` | `test_payload_shape` | `:42 set(payload) == {...}` | `:45 len(by) > 500` |
| `test_trade_board_coverage.py:110` | `test_projection_only_rows_price_on_the_projection_basis` | `:110 surplus_source == "projection"` | `:113 approx(..., abs=0.05)` |
| `test_efv_export.py:686` | `test_xfv_golden_fingerprint` | `:686 isinstance(bp, dict)` | `:689 lo <= len(bp) <= hi` truncated-regen tripwire |
| `test_fa_tier1.py:292` | `test_opt_out_is_priced_on_the_remaining_guarantee_not_one_season` | `:292 method == "band_priced_..."` | `:294 0.2 < enter_prob < 0.8` |
| `test_wag.py:206` | `test_wag_mean_by_source_is_the_bias_signal` | `:206 set(agg) == {"FG","BA"}` | `:208 agg[g]["n"] >= 1` |

Full machine-readable list (89 rows) is reproducible with the AST scanner; the ranking
weights are `3 x tripwire-word-count + min(n_shadowed, 5) + 3 for a startswith/regex cheap
assert + 2 for a schema/key-set assert`.

**Systemic note.** The 89 hits are not 89 bugs. The exposure only bites when the cheap
assertion can fail INDEPENDENTLY of the substantive one, which is true for names,
versions, and schema shapes (they change on a rename) and largely false for computed tags.
The only structural fix that generalizes is to put the tripwire FIRST, which costs
nothing. Rank 1 is the only one this lane recommends editing now.

---

## 7. D17. FALSE as stated. The sign audit is clean.

**Plan claim:** "`milb_missing` fits +0.0397 against a declared sign of -1
(`efv_model.py:135-143`) ... Confirm `efv_sign_audit` still flags it."

**Measured on the current matrices:**

- `efv_model.py:135` declares `("milb_missing", 0)`, not -1. The `-1` in the plan is the
  FORMER declaration; the code comment says so ("declared 0 (sign audit 2026-07-25):
  served fit is +0.0397 against a declared -1"), and the plan read the historical clause
  as the current state.
- `efv_sign_audit.contradicts:157-161`: "declared == 0 is 'no directional claim' and can
  never contradict." So it cannot flag by construction.
- `efv_sign_audit.contradictions("hit")` and `("pit")` both return `{}`.
- `efv_sign_audit.explainer_narration_risk("hit")` and `("pit")` both return `{}`.
- `efv_sign_audit.undeclared_provisional()` returns `{"hit": [], "pit": []}`.
- `audit_provisional` for both sides: every key `"classification": "OK"`, zero
  contradictions.
- The `milb_missing` weight itself has MOVED: served standardized ridge weight is now
  **-0.0174** (marginal -0.0463), not +0.0397. `|w| = 0.0174 <= NOISE_W = 0.02`, so it is
  now below the audit's own noise bar and would be classified NOISE even if it contradicted
  something.

**Nothing was flagged, so nothing was touched.** Instruction honoured.

**Full served sign table, for the record** (`efv_sign_audit.audit`, production fit pool):

| hit feature | declared | fitted w | marginal | sign vs marginal |
|---|---|---|---|---|
| fv | +1 | +2.5022 | +0.5796 | agree |
| obp_rel | +1 | +0.0471 | +0.1349 | agree |
| k_rel | 0 | +0.1844 | -0.0936 | **OPPOSITE** |
| peak_k_rel | -1 | -0.1120 | -0.1200 | agree |
| age_rel_level | -1 | -0.2147 | -0.2148 | agree |
| n_milb_seasons | 0 | -0.1856 | +0.0378 | **OPPOSITE** |
| tool_hit | +1 | +0.3069 | +0.3091 | agree |
| tool_speed | +1 | +0.2255 | +0.0732 | agree |
| milb_missing | 0 | -0.0174 | -0.0463 | agree (and sub-noise) |
| is_ifa | 0 | +0.0782 | -0.0389 | **OPPOSITE** |
| is_college | 0 | +0.3231 | +0.0343 | agree |
| ops_rel | +1 | +0.2289 | +0.1495 | agree |
| age | 0 | +0.0376 | +0.0172 | agree |
| level_rank | +1 | +0.3062 | +0.1440 | agree |

| pit feature | declared | fitted w | marginal | sign vs marginal |
|---|---|---|---|---|
| fv | +1 | +1.2932 | +0.4316 | agree |
| peak_k_rel | +1 | +0.1529 | +0.1015 | agree |
| k_rel | +1 | +0.1762 | +0.1234 | agree |
| bb_rel | -1 | -0.0601 | -0.0546 | agree |
| age_rel_level | 0 | +0.0566 | -0.0824 | **OPPOSITE** |
| x_era_k | +1 | +0.0742 | +0.0870 | agree |
| tool_fb | +1 | +0.0897 | +0.1435 | agree |
| age | 0 | +0.1016 | -0.0214 | **OPPOSITE** |
| seasons_at_level | -1 | -0.1054 | -0.0381 | agree |

Five features fit opposite their own marginal correlation with realized WAR. All five are
covered by a declared remedy, which is why `explainer_narration_risk` is empty, and each
remedy was checked individually rather than assumed:

| side / feature | remedy | source |
|---|---|---|
| hit `k_rel` | grouped (`k_rate`) | `efv_factor_groups.group_id` |
| hit `n_milb_seasons` | relabelled | `efv_sign_audit.DISPLAY_ACKNOWLEDGED` |
| hit `is_ifa` | skipped | `efv_score._EXPLAINER_SKIP` |
| pit `age_rel_level` | skipped | `efv_score._EXPLAINER_SKIP_SIDE["pit"]` |
| pit `age` | skipped | `efv_score._EXPLAINER_SKIP_SIDE["pit"]` |

**Verdict: E5 CLEAN. D17 FALSE as stated.** Nothing new surfaced.

---

## 8. NEW. `data/xfv_driver_pos_census.json` publishes a claim the code contradicts.

`data/xfv_driver_pos_census.json` (`generated_at: 2026-08-07T18:05:33Z`, i.e. today) has:

```json
"consumer_today": "efv_model._observed_pos_map reads data/positions_played.json, the OLD
career-to-date pre-debut artifact; the as-of census is not wired into the model at all"
```

The first half is false as of the wave-6 change. `efv_model._observed_pos_map:1045-1062`
now returns `{}` unconditionally and its docstring says so: "It used to load
data/positions_played.json ... The default is therefore empty". The second half is
correct, but for a different reason than stated: the census is unreachable because
`POS_PREMIUM_USES_OBSERVED = False` (`efv_model.py:1002`) gates BOTH routes at `:1084`.

This also resolves plan item 0.4 ("The memory index still lists this as an unfixed defect;
recon says wave 6 fixed it. Confirm which is true."): **recon is right, wave 6 fixed it**,
and the position census reaches no training feature by two independent guards.

---

## 9. E3. The level-norm chain is contemporaneous. CONFIRMED.

- `efv_dataset._resolved_norms:481-504` calls `mh.league_norms(season, level, group,
  fetch=False)` at `:486`, then `season - 1` at `:488`, then the static `_NORM_PRIOR`.
  Season-keyed at every rung.
- `level_norms.compute_level_norms:222-239` is `date.today()`-anchored
  (`today = today or date.today()`, `cutoff_year = today.year - seasons_window`).
- **Its only callers in the tree are `storage.py:8340` / `:8636` (the site export path)
  and two lab tools (`tools/era_shrink_unification_lab.py:69`, `tools/_c_agenorms.py`).
  No eFV module calls it.** `import level_norms` appears in exactly three files
  (`efv_dataset.py:50`, `test_metrics_audit.py:35`, and one lab), and `efv_dataset` uses
  it only for `sb600_league_norm` (`:497`, `:499`) and `FALLBACK_SB600_NORM` (`:501`).
- `level_norms.sb600_league_norm:171-195` is itself season-keyed
  (`mh.season_splits(sport, season, ...)`), so even that leg is contemporaneous.

**Verdict: CONFIRMED. No `compute_level_norms` on any eFV path.**

---

## 10. D18. No builder. CONFIRMED.

`data/fielding_census_ids.json`: 191,987 bytes, mtime **2026-07-30 19:43:41**,
`generated_at: "2026-07-30"`, keys `{generated_at, note, provenance_counts, matrix, live}`,
`provenance_counts: {known: 3387, name: 446, ambiguous: 38, unresolved: 160}`,
1,840 matrix bindings + 1,993 live bindings.

Searched the whole tree for a writer. **Only readers exist:**
`tools/efv_driver_lab.py:603` and `tools/pos_census_repoint_lab.py:57`. No `.py` file
anywhere writes that path or emits a `provenance_counts` key. `fielding_positions.py`'s
four writers (`:460`, `:686`, `:713`, `:771`) all target other artifacts.
`deploy/data_exclude.txt:66` excludes it from deploy.

The 91.8% figure lives at `data/xfv_driver_pos_census.json` `asof_route.coverage.all.frac
= 0.9176`, and is reachable only through those bindings: through the matrix rows' own
`mlbam_id` it is 58.6%.

**Already annotated in code** at `efv_model.py:962-972`, verbatim: "That file has NO
builder anywhere in the tree (committed as a one-off in fef6599), is frozen at 2026-07-30,
and is excluded from deploy." **Not annotated in the artifact itself**, which is what a
reader of the 91.8% figure would open. See edit 4.

---

## 11. D19. `FALLBACK_SB600_NORM` inert. CONFIRMED.

`level_norms.FALLBACK_SB600_NORM:165-168` is an all-time pooled constant (2015-2024
empirical medians, per its own comment at `:161-162`) with no season key. It reaches
`sb_rate_rel` through `efv_dataset._resolved_norms:501` -> `_season_rates:552`.

`sb_rate_rel` is computed into both matrices (`efv_dataset.py:552`, `:593`, `:851`) and
appears in **neither** `_FEATURES_HIT` nor `_FEATURES_PIT`. The comment at
`efv_dataset.py:551` states it: "INERT in the served model until `_FEATURES_HIT` names it,
which it does not." `efv_model.py:419` records the closed arm: "sb_rate_rel (hit) +0.0027
= 0.13x floor, 4 of 11 folds".

**Verdict: CONFIRMED inert.** It is a two-step latent: reviving `sb_rate_rel` would
reintroduce a level-only, season-blind constant into a feature whose entire justification
is level-and-season relativity. See edit 3 for the tripwire comment.

---

## 12. E2. Artifact enumeration and AS-OF / CURRENT-STATE classification.

Verified by reading the code, not copied from the plan. `AS-OF` means the value is keyed
to something at or before the row's own decision point.

### Training matrix, `efv_dataset.build_matrix:1039-1236`

| # | Artifact | Read at | Class | Note |
|---|---|---|---|---|
| 1 | `data/debuts.json` | `:1039` | **AS-OF** | `points[]` filtered by `_asof_point(rec, dd):409-419`, strictly `< cutoff`. `debuted_value.wag` is NOT read here. |
| 2 | `data/inactive.json` | `:1040` | **AS-OF** | `_asof_point(rec, None)` returns the FINAL point, which for a bust IS the decision point (`cutoff = last_date`, `:1181`). |
| 3 | DB `career_war` | `:1046` region | **CURRENT-STATE, label side** | This is the label. Labels see the future by construction. |
| 4 | DB `acquisitions` | `_load_sidecars:906-911` | **CURRENT-STATE table, TIME-INVARIANT value** | `pick_overall`, `bonus_usd`, `method`, `year` are historical facts fixed at signing. No date filter, but no time-varying value. Latent only if a `method` were ever revised. |
| 5 | DB `il_history` | `_load_sidecars:912-914` | **AS-OF** | `_injury_features:1029` filters `d < cutoff`. |
| 6 | DB `player_transactions` | `_load_terminal_dates:971-973` | **CURRENT-STATE, label side** | Resolves censoring via `_terminal_resolves:951-963`. Correct: it can only shorten a label window the player cannot play. |
| 7 | `.cache/milb_stats/{group}_{sport}_{season}.json` via `mh.player_index(season, group)` | `:708` | **AS-OF** | Season-keyed. Season floor enforced at `:700-706`. |
| 8 | `mh.league_norms(season, level, group)` | `_resolved_norms:486`, `:488` | **AS-OF** | The `date.today()` blend at `milb_history.py:294` provably cannot fire: 0 training rows carry `milb_season == 2026`. |
| 9 | `level_norms.sb600_league_norm(season, level)` | `_resolved_norms:497`, `:499` | **AS-OF** | Season-keyed. Feeds only `sb_rate_rel` (unshipped). |
| 10 | `level_norms.FALLBACK_SB600_NORM` | `_resolved_norms:501` | **CURRENT-STATE (all-time pooled)** | Inert: `sb_rate_rel` unshipped. See finding 11. |
| 11 | Savant AAA aggregates via `arkmetric_forward_eval.savant_rows(season, ...)` | `efv_statcast_line._gap_index:105-111` | **AS-OF** | Season-keyed, `lru_cache` per `(season, side)`. `XLINE_*_DEFAULT = True` (`:41-42`), so this IS live. |
| 12 | `data/milb_park_factors.json` | `efv_park_line.py:88` | **not read** | `PARKLINE_HIT_DEFAULT = PARKLINE_PIT_DEFAULT = False` (`:55-56`). |
| 13 | StatsAPI sport-1 caches via `_mlb_exposed_ids:988-996` | `:1118` | **CURRENT-STATE, cohort-membership guard** | Uses post-decision MLB exposure to EXCLUDE a row from the bust pool. This is a label-integrity guard (the `adolis_garcia` fix); it makes labels more honest, not less. Named here because it does mean cohort membership is decided with post-decision information. |
| 14 | `data/positions_played_seasons.json` + `data/fielding_census_ids.json` | `efv_model._season_census`, `_observed_pos_as_of:1025-1042` | **not read** | Double-gated: `POS_PREMIUM_USES_OBSERVED = False` (`:1002`) AND `_observed_pos_map()` returns `{}` (`:1045-1062`). |

### Live matrix, `efv_dataset.build_live_matrix:1240-1345`

| # | Artifact | Read at | Class | Note |
|---|---|---|---|---|
| 15 | `data/timeseries.json` | `:1248` | **CURRENT-STATE, correct** | The live decision point IS now. `_asof_point(rec, None)` = latest snapshot (`:1283`). |
| 16 | `mh.league_norms(2026, ...)` | via `_resolved_norms` | **CURRENT-STATE (blended)** | The D15 shift. Fires on 94.3% / 91.6% of live rows. |
| 17 | `date.today()` via `_stale_anchor_discount:113` | `:1329` | **CURRENT-STATE, live-only** | Sole call site. Never touches training. |
| 18 | Same DB sidecars (`acquisitions`, `il_history`) | `:1322` | **CURRENT-STATE, correct** | `cutoff is None` for live rows, so all IL history counts, which is right for a now-decision. |

**Verdict: CLEAN. No current-state artifact with a time-varying value enters a training
feature.** The only `date.today()` reads on the whole eFV path are
`efv_dataset.py:113` (live-only), `milb_history.py:294` (provably unreachable from
training), and `generated_at` stamps.

---

## Edits requested (this lane owns no source file; the orchestrator applies these)

### Edit 1. Correct a false leakage claim. `efv_model.py:630`

`wag_calibration`'s regressand is `wg["regressed_wag"]` (`:658`), read by `_load_wag:613`
from `debuts.json`, built at `storage.py:10289-10297` from full career WAR baselined
against the CURRENT eFV grade. It is not leakage-free.

- old: `    blend. Returns {lambda, slope_wobs, slope_unweighted, spearman, n}. Leakage-free."""`
- new: `    blend. Returns {lambda, slope_wobs, slope_unweighted, spearman, n}.`
  `` + newline + ``
  `    NOT LEAKAGE-FREE (audit 2026-08-07b, D14). The FEATURE side is forward-chained, but`
  `    the regressand is not: _load_wag reads debuted_value.wag from debuts.json, which`
  `    storage.py:10289-10297 builds from the player's FULL career_war baselined against his`
  `    CURRENT xfv_grade, with no as-of filter. A fold scored at year Y therefore regresses`
  `    on an outcome that includes seasons after Y. Harmless today only because both sides`
  `    carry a _BLEND_LAMBDA_RESELECT pin, so this never selects the served lambda; it does`
  `    still ship into the eval artifact via run():2500. Do not un-pin without an as-of WAG."""`

### Edit 2. Guard the pin. `efv_model.blend_lambda`, around `:830-836`

Today the current-state calibrator is disarmed only by the accident of a pin being set.
Make it structural, so removing a pin cannot silently re-arm it.

- old:
```
        try:
            wc = wag_calibration(side)
            rho = wc.get("spearman")
            if rho is not None and abs(rho) >= _WAG_MIN_SPEARMAN and (wc.get("n") or 0) >= _WAG_MIN_N:
                _WAG_LAMBDA_CACHE[side] = wc["lambda"]
            else:
                _WAG_LAMBDA_CACHE[side] = rank_calibration(side)["lambda"]
```
- new:
```
        try:
            # D14 GUARD (audit 2026-08-07b). wag_calibration's regressand is a
            # CURRENT-STATE quantity (see its docstring): debuted_value.wag is built from
            # full career_war against the current xfv_grade, so a fold scored at year Y
            # regresses on seasons after Y. It must never size the SERVED lambda. The pin
            # above already prevents that; this flag makes it structural rather than
            # incidental, so removing a pin cannot silently re-arm it. Flip only when an
            # as-of WAG exists.
            wc = wag_calibration(side)
            rho = wc.get("spearman")
            if (_WAG_LAMBDA_IS_ASOF and rho is not None
                    and abs(rho) >= _WAG_MIN_SPEARMAN and (wc.get("n") or 0) >= _WAG_MIN_N):
                _WAG_LAMBDA_CACHE[side] = wc["lambda"]
            else:
                _WAG_LAMBDA_CACHE[side] = rank_calibration(side)["lambda"]
```
plus a module constant beside `_BLEND_LAMBDA_RESELECT` at `efv_model.py:581`:

- old: `_BLEND_LAMBDA_RESELECT: dict[str, float | None] = {"hit": 0.70, "pit": 0.57}`
- new: `_BLEND_LAMBDA_RESELECT: dict[str, float | None] = {"hit": 0.70, "pit": 0.57}`
  `` + newline + ``
  `#: D14 (audit 2026-08-07b). False while debuted_value.wag is current-state. Gates the`
  `#: WAG branch of blend_lambda so an un-pinned side falls to the rank gate instead of to`
  `#: a calibrator whose regressand sees the future. Flip to True only with an as-of WAG.`
  `_WAG_LAMBDA_IS_ASOF = False`

Note: this changes no served number (both sides are pinned, and the un-pinned fallback was
already `rank_calibration`), and it does not touch the eval-artifact emission at `:2500`.

### Edit 3. D19 vintage tripwire. `level_norms.py:165`

- old: `FALLBACK_SB600_NORM: dict[str, float] = {`
- new:
```
# VINTAGE TRIPWIRE (audit 2026-08-07b, D19). This table is level-keyed and SEASON-BLIND:
# one pooled 2015-2024 median per level, applied to every season. Inert today only because
# sb_rate_rel is computed into the matrices (efv_dataset.py:552) but named in NEITHER
# _FEATURES_HIT NOR _FEATURES_PIT, and the arm is closed (efv_model.py:419, +0.0027 =
# 0.13x floor). Reviving sb_rate_rel WITHOUT first checking the contemporaneous coverage
# of sb600_league_norm would put a season-blind constant inside a feature whose entire
# justification is level-and-season relativity. Check the fallback hit rate before any
# revival, and prefer widening the empirical leg over relying on this.
FALLBACK_SB600_NORM: dict[str, float] = {
```

### Edit 4. Annotate the unreproducible 91.8% figure, and fix a stale claim beside it

`data/xfv_driver_pos_census.json` publishes `asof_route.coverage.all.frac = 0.9176`,
reachable only through an artifact with no builder, and next to it a `consumer_today`
string the code now contradicts. The writer is `tools/efv_driver_lab.py:625`.

- file: `tools/efv_driver_lab.py`
- old: `        "id_bindings": "data/fielding_census_ids.json (census-scoped, not a global id override)",`
- new: `        "id_bindings": "data/fielding_census_ids.json (census-scoped, not a global id override). UNREPRODUCIBLE: that file has NO builder anywhere in the tree, is frozen 2026-07-30, and is excluded from deploy (deploy/data_exclude.txt:66), so every coverage figure under asof_route is unrebuildable. Through the matrix rows' own mlbam_id the same coverage is 58.6 percent, not 91.8.",`

and, in the same dict, the stale consumer claim (`_observed_pos_map` returns `{}`
unconditionally since wave 6, `efv_model.py:1045-1062`, and both routes are gated off by
`POS_PREMIUM_USES_OBSERVED = False`, `efv_model.py:1002`):

- old: `efv_model._observed_pos_map reads data/positions_played.json, the OLD career-to-date pre-debut artifact; the as-of census is not wired into the model at all`
- new: `efv_model._observed_pos_map returns {} unconditionally since wave 6 (efv_model.py:1045-1062) and BOTH position routes are gated off by POS_PREMIUM_USES_OBSERVED = False (efv_model.py:1002); the census reaches no training feature by either guard`

### Edit 5. D20 rank 1. Put the tripwire in front of the naming checks.
`test_value_framework.py`, `test_calibration_layer_is_real_fit_and_monotone`

The 2026-07-29 repair conformed the config name; it did not remove the shape. Move the
degeneracy tripwire above the five naming / provenance / shape assertions so a future
rename cannot mask it again. Minimal version: hoist `assert ys[0] > 0` (currently `:93`)
and its `xs, ys` binding (currently `:70`) to immediately after
`cal = vf._config()["calibration"]` (`:59`), leaving `:60`, `:61`, `:69`, `:76`, `:77`,
`:78`, `:80` in place below it. The `ys[-1] > ys[0] * 5` non-degeneracy check at `:97`
should move with it.

While there, the comment block at `:84-96` is stale and should be corrected: it says the
tripwire "IS EXPECTED TO FAIL ... ys[0] is 0.0 under v5", but the shipped v6 map has
`y_mm[0] = 0.67` (`value_framework_config.yaml:541`) and the assertion passes. Leaving it
tells a future reader a green line is red.

I did not run pytest to confirm the reorder is green (standing rule 2). The reorder is
mechanically safe: `xs`/`ys` depend only on `cal`, and all seven remaining assertions are
independent of each other.

---

## What this lane did NOT do

- Did not re-measure D1. `consensus.build_timeseries` contamination is Lane D's and was
  not re-derived here; nothing found contradicts it.
- Did not run pytest, not once (standing rule 2).
- Did not refit anything. Every number above is a read of a shipped artifact, a read of
  the source, or a deterministic recomputation from committed norms.
- Did not touch `milb_missing` (instructed), and there was nothing to touch: it does not
  flag.
- Did not write to `data/`.
