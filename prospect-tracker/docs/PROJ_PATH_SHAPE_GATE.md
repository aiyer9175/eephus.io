# MLB Projections path-shape gate (pre-registered 2026-09-18)

Covers two programs on the `/projections/` WAR paths, both ordered by the owner on
2026-09-18:

- **ARM A, the smoothness refit.** A joint refit of the `proj_lgbm` quantile heads
  across horizons under an age-smoothness penalty, replacing fifty independently
  fitted per-horizon heads.
- **ARM B, the three bias levers.** The age-by-side slope, the catcher role
  correction and the star-slice recalibration that `proj_calibration_map` and
  `fa_war_paths_decay` measured and never shipped.

Producers, none of which exist yet: `tools/proj_shape_blast_lab.py`,
`tools/proj_shape_mde_lab.py`, `tools/proj_shape_gate.py`. Artifacts:
`data/proj_shape_blast.json`, `data/proj_shape_mde.json`,
`data/proj_shape_gate.json`. Pinned by `test_proj_shape_gate.py`. Registry rows
touched: `fa_war_paths_decay` and `proj_calibration_map`.

Written and committed BEFORE any candidate exists, in the shape of
`docs/ARBITRATION_GATE.md` and under the rules of `docs/diamond-betting.md` 5c.

Where this document and a later measurement disagree, **the measurement is what
this gate uses**, and the disagreement is recorded rather than edited away.

**AMENDED 2026-09-18, before any look: see section 21.** The two-sided label
defect recorded in open question 18.8 is repaired. Section 21 names which of this
document's design-day descriptives go stale with it and what each is restated
from. No threshold, frame boundary, decision rule or criterion in this document
is changed by that amendment.

---

## G-0. Honesty clause, first

**No candidate was scored to write this document.** Nothing was fitted, no arm was
run, no candidate was compared against the shipped engine. Every number below is
one of: a figure already published in a committed eval artifact, a registry row or
a commit message; a descriptive statistic computed over the SERVED artifact
`data/mlb_projections.json` (the shipped engine's own output, generated 2026-09-18);
or a row or byte count on disk. Describing what the board already shows is not
scoring a candidate.

**Looking early disqualifies.** 5c rule 1, verbatim in force here: a candidate
measured before its section exists is disqualified, whatever it measured. Each arm
below has exactly one look, on a date fixed in section 13. A number computed on a
candidate before that date voids the arm for this battery, and the arm may return
only as a new registration that discloses the early read.

### G-0.1 The READ LEDGER, complete, and the burn standard applied evenly

An earlier draft of this document called base years 2022-2024 BURNED for having been
read four times, and called bases 2014-2016 and base 2025 clean. That was the same
standard applied unevenly. Here is the complete ledger of every base a `proj_lgbm`
challenger has been scored on in a committed artifact, and the LABEL SEASONS those
reads consumed (base `B`, horizon `h` scores label season `B+h-1`):

| artifact / block | engine scored | bases | label seasons consumed |
|---|---|---|---|
| `proj_horizon_eval.json` `challenger_blocks.gate1_targets` (`proj_lgbm_v1_gate1targets`) | CHALLENGER: per-horizon mae, bias, mae_star, bias_star, coverage, pinball_q10, pinball_q90 | 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025 | 2015 - 2025 |
| `challenger_blocks.dev`, `dev_statcast_v2_rejected` | CHALLENGER | 2017, 2018, 2019, 2021 | 2017 - 2025 |
| `challenger_blocks.holdout_2022_2024`, `_starblend` | CHALLENGER | 2022, 2023, 2024 | 2022 - 2025 |
| `rowmatch_champion_vs_challenger` | CHALLENGER and CHAMPION, row matched | 2017, 2018, 2019, 2021 | 2017 - 2025 |
| `proj_def_feature_eval.json` | CHALLENGER | dev 2017-2021, holdout 2022-2024 | 2017 - 2025 |
| P-MBLEND re-measure (registry `fa_war_paths_decay`, 2026-07-24) | CHALLENGER, blended | 2019 - 2022 | 2019 - 2025 |
| `proj_calibration_eval.json`, 65 cells | CHAMPION ONLY (`fm._decay_path`) | 2014 - 2021 ex 2020 | 2014 - 2025 |
| `holdout_2022_2024_champion` | CHAMPION | 2022, 2023, 2024 | 2022 - 2025 |

Read off the ledger, and this is the fact that drove every frame decision below:

> **Every label season from 2015 through 2025 has already been scored on the
> shipped challenger, on exactly the statistics S1 through S6 use.** The block that
> does most of it, `gate1_targets`, is the one `proj_eval.run_rowmatch`'s own
> docstring flags as the block that "invites a false win claim". The label seasons
> with no prior challenger read are **2008 through 2014** and, once the season
> completes, **2026**.

`test_proj_ml.test_training_frame_no_lookahead_property` pins only that training
labels are at or below `max_label_season`. It establishes nothing about frame
disjointness and is no longer cited for it.

### G-0.2 The priors read during design, recorded so a run cannot quietly beat them

`data/mlb_projections.json` of 2026-09-18 and the descriptive statistics in 4.5;
`data/proj_horizon_eval.json` in full, **including `challenger_blocks.gate1_targets`**,
whose per-horizon incumbent statistics are Tier-2 by G-0.1;
`data/proj_calibration_eval.json` (all 65 cells, champion engine);
both registry rows in full; `model/proj_lgbm/meta.json`; the row counts of
`.cache/proj_ml_frame_fe323aac_2003_2025_2000_2026_ewar_v2.pkl`; the on-disk size of
`.cache/proj_ml_pit_*.joblib` (29 files, 793,446,247 bytes); commit `05a25ce1`.

Exactly one of those reads touches a label season this gate scores, and it is
recorded here rather than denied:

> `proj_calibration_eval.json` pools bases 2014-2021 across five horizons, so its
> cells include label season 2014, which the GATE frame owns. The read is of the
> **CHAMPION**, pooled across 35 base-horizon cells, and does not isolate 2014. The
> champion is S2's floor and is never the primary comparator, which is one more
> reason S2 is not the primary. Nothing else read touches label seasons 2008-2014
> or 2026.

Nothing else about a candidate's behaviour was read, because nothing else exists.

**Stop rule.** If section 2 (label quality) fails, no arm runs, whatever the
calendar says. If section 3 (power) is not on disk, no criterion below may be read.

---

## 0. What is being fixed, measured first

Every row was measured before any model was written. The rows marked PLAN WAS WRONG
are the reason this is not the document the owner's report implies.

| claim | the report said | measured 2026-09-18 | verdict |
|---|---|---|---|
| two-way players need two aging curves | "maybe two different aging curves for batters/pitchers, and using both aging curves for two way players" | `fa_market._decay_path` (fa_market.py:291) is keyed by side AND profile role; `proj_export.py:703-745` runs both sides through their own curves and sums per season; `warHit`/`warPit` ship at 827-829 | **PLAN WAS WRONG.** Already done |
| Ohtani's level is the model | implied | commit `05a25ce1` (2026-09-18 09:51:31) reverted the DISPLAY from the if-healthy q70 series to the expected value. Vets 5y `warPTH` 4,716.1 against `war` 2,925.6, 37.9% high; Ohtani `warTotalPTH` 36.4 against `warTotal` 32.1 | **largely the DISPLAY, and that half already shipped** |
| the wobble is overfitting in the aging operator | "players randomly fluctuating downward between years in their prime" | the champion aging path wobbles on **0 of 311** served rows under the 4.5 rule; the ML central path wobbles on **153 of 278** | CONFIRMED real, and it is NOT the aging operator |
| the wobble has one cause, independent heads | the working diagnosis | **three** mechanisms: 50 heads fitted per (side, horizon, quantile) with nothing coupling them; `_params_for(h)` swaps `LGBM_PARAMS` (400/31/60) for `LGBM_PARAMS_LONG_H` (600/63/30) at h>=4; the lift-only recenter lambdas step 1.0/1.0/1.0/0.5/0.5 and the star top-up fires at h5 alone | **PLAN WAS WRONG.** A heads-only refit leaves two of the three standing |
| the three bias cells describe the served engine | assumed | `tools/proj_calibration_lab.py` `collect()` calls `fm._decay_path` directly (line 80) and the artifact stamps `model = "marcel_decay_v2 (champion projection engine)"`. It never touches `proj_ml` | **PLAN WAS WRONG.** All three cells were measured on the FALLBACK engine, which `/fa/` serves and `/projections/` does not |
| the three bias cells are on the served WAR basis | assumed | `data/proj_calibration_eval.json` is stamped 2026-07-25 and `data/proj_horizon_eval.json` 2026-08-19; the eWAR v2 epoch landed 2026-09-03/04 and the bundle was retrained on it 2026-09-04 (`44c089c2`) | **PLAN WAS WRONG.** Every cell, including `age:<=24:pit +0.2217`, sits on bWAR |
| 2022-2024 is the burned holdout, and 2014-2016 plus base 2025 are clean | an earlier draft of this document | `challenger_blocks.gate1_targets` scored the shipped challenger on bases 2015-2025 and published exactly S1-S6's statistics, which covers two of the three bases that draft called GATE and both cells it called FRESH | **PLAN WAS WRONG.** See G-0.1. The clean window is 2008-2014, plus 2026 once it completes |
| the published forward-chained receipts score what is served | assumed | `proj_eval.run_rowmatch` DOES pass `proj_ml.QUANTILES` (proj_eval.py:219), so `full_qs` is True. The blends stay inert because `proj_ml.train()` never writes `mean_blend` or `star_blend` into bundle meta; they are stamped post-hoc onto the LIVE bundle alone, by `tools/apply_mean_blend.py` and `tools/fit_star_blend.py --apply` | **PLAN WAS WRONG, and so was an earlier draft's reason.** Every published comparison scores an UNBLENDED q50 while the serve is blended, but the mechanism is the missing meta key, not `LEAN_QUANTILES` |
| the registry publishes the shipped bundle's hash | assumed | row `fa_war_paths_decay` narrates `442428a6498b1426` then `6a691e03ff096a35`; `model/proj_lgbm/meta.json` carries `train_hash 4baf67400e5af498`, `max_label_season 2025` | stale; open question 18.1, not fixed here |
| the two-way workload discount protects the priced number | implied by `TWO_WAY_PIT_PTH_FACTOR` | 0.48 is applied ONLY when summing `war_by_year_pth` (proj_export.py:740-746). `_sum_arr("war_by_year")` takes no discount | **the served two-way `war` sum carries NO workload discount at all**, which is the shape of the owner's Ohtani complaint. Surplus and FA rational value always priced off `war`; what `05a25ce1` moved was the DISPLAY |
| each side's model estimates that side's WAR | assumed | `fa_projection._war_age_maps` returns "{(mlbam, season): war} (bat+pit summed)" and `build_corpus` writes that total onto the hit row AND the pit row. 671 of 35,825 player-seasons carry both, identical in all 671. `build_training_frame` (proj_ml.py:336) then does `war_actual[key] += r["war"]` over BOTH sides, and `proj_eval._assemble` does the same | every side-keyed model estimates E[TOTAL WAR given this side's line], and those player-seasons train and score at 2x |

### 0a. GATE 0.1 - the blast-radius bound, run before anything is fit

`tools/proj_shape_blast_lab.py` -> `data/proj_shape_blast.json`. **No arm may be
fitted before this artifact exists.** It bounds what a pure SHAPE change can move
without fitting anything, by reshaping the SERVED paths at the extremes of what a
smoothness penalty can do:

- **IDENTITY**: the served `war` path, as it ships today.
- **MAXSMOOTH**: each row's `warChamp` path rescaled to that row's served 5-year
  `war` total. This is the smoothest admissible shape (the champion is the fitted
  aging curve and wobbles on 0 rows) at an unchanged total.
- **RAMP**: a straight line from `war[0]` to `war[4]` preserving the 5-year total.
  Deliberately beyond anything a penalty would return, so the bound is a bound.

Reported for each reshape against IDENTITY, over the 895 rows carrying `surNpv`:
mean, median and max absolute move in `surNpv` and `surTotal`; mean relative move;
and **Spearman(pre, post) over `surTotal`**.

Two pre-registered consequences, in the shape of ARBITRATION_GATE 0a:

1. **If Spearman comes back at or above 0.9990, the reordering criterion cannot
   discriminate** and is demoted to a regression guard: a shape change that DID
   reorder the trade board would mean something broke, but an unchanged order is
   not evidence for the refit and must not be cited as such.
2. **This is a SHAPE-ONLY bound and says nothing about the level.** A refit moves
   the level too. The level move is bounded by S3 (4.8) and by the dollar bands in
   section 9, not by this artifact, and the artifact says so in its own `reading`.

---

## 1. The estimands

### 1.1 ARM A, the smoothness refit

> For a player-side line observable as of the end of season `B-1`, this arm
> estimates the **same five conditional quantiles of that player's WAR in seasons
> `B` through `B+4`** that `proj_lgbm_v1` estimates today, from the same features on
> the same rows with the same labels, under a single joint fit in which the five
> horizons of one player are predicted by one model per (side, quantile), horizon
> and age-at-target are features, and the loss carries an explicit second-difference
> penalty across a player's available predictions.
>
> It does NOT estimate a smoother TRUTH. The labels score an absent season as 0.0
> WAR, so the expected path of a population whose survival probability decays is
> genuinely not smooth in age, and part of the roughness this arm removes is real
> attrition signal. That is the trade this gate prices: 4.8 registers the accuracy
> the arm may spend, 4.5 registers the roughness it is buying out, and the artifact
> publishes both at every point on a pre-registered lambda grid rather than at the
> chosen point alone.
>
> It does NOT estimate anything about two-way players (section 7), does NOT
> re-estimate the champion aging curves, and does NOT support a claim that a
> per-player path is what would have been said at base `B` in real time (4.7, leak 6).

### 1.2 ARM B, the three bias levers

Each lever estimates a **correction to the conditional mean of the SERVING engine's
central path on a named slice**, fitted forward-chained and applied at serve:

- **B-AGE.** A side-keyed slope in **age-at-target** (not age-at-base, not a level).
  Prior, on the champion engine on bWAR: hitters at or under 24 read -0.1982 and 34
  and over read +0.1273 (the curve is too flat); pitchers at or under 24 read +0.2217
  and 34 and over read -0.0287 (the reverse). It is a slope, not a level: `ageh:34+`
  runs +0.1099 at h1 and +0.0041 at h5. **A pooled age recentering is banned**
  (section 15): the two sides cancel and it would fix neither. **B-AGE therefore has
  no one-parameter twin** (5.4).
- **B-C.** A catcher correction. Prior, champion engine, bWAR: `role:C` +0.2453
  [+0.186, +0.309] on n=4,585, projecting 0.537 WAR per season and delivering 0.292.
  The artifact's own reading constrains the form: "the WAR map's C x PA/600 term
  (+0.6227) is fit on observed catcher seasons, so the miss is in projected catcher
  PT/rate, not in the map's slope."
- **B-STAR.** A star-slice recalibration on the ex-ante star slice (base WAR at or
  above 4). Prior, champion engine: -0.3961 [-0.621, -0.149] on n=2,085. On the
  SERVED engine the disclosed miss runs deeper: "long-horizon star bias ~0.2 WAR
  deeper than champion", holdout h1 star bias -0.6545 and h4 -1.4510.

> **These three cells were chosen from a 65-cell screen.** `resolvable_biases_ranked`
> in `data/proj_calibration_eval.json` carries at least nine resolvable entries
> (star -0.3961, role:C +0.2453, age:<=24:pit +0.2217, age:<=24:hit -0.1982,
> age:25-27:hit -0.1573, survived -0.1538, age:34+:hit +0.1273, absent +0.1131,
> ageh:34+:h1 +0.1099, and more). The Holm family in 5.5 corrects the ADJUDICATION
> of three levers; **no correction in this document covers that selection.** The
> published priors are selected maxima and are winner's-curse inflated, which is why
> the detection check in section 3 plants the nearer-zero end of each cell's
> published CI and never its point estimate, and why the B0 re-measure on the serving
> engine is the only admissible effect size for every other purpose.

> None of the three estimates the CAUSE of its cell. B-C in particular repairs a
> number produced by projected catcher playing time and rate; if the output-side form
> is what ships, the artifact must say so in those words.

**All three estimate the EXPECTED VALUE that surplus prices.** None is display-only,
and section 8 records why that is not a choice.

---

## 2. Label-quality gates. Nothing ships if these fail.

These run on the corpus and the frame, before any model exists. A failure here means
the data is wrong, not the model.

- **L1 two-sided label census.** Count player-seasons carrying both a hit row and a
  pit row, and the subset with absolute WAR at or above 0.5 on both. Design-day:
  **671 of 35,825** corpus player-seasons (1.9 percent), identical `war` in all 671,
  **327** above the magnitude floor; each enters the frame as two base rows, and the
  scored-row share is recounted at scoring time and published rather than carried
  from here. Criterion: the census is published, and **every two-sided row is
  excluded from every fitted cell and every scored cell in both arms, and from the
  comparator S's point-in-time refits as well**, so the contrast is between two
  consistently built arms. If a lab is found scoring them, the run is void.
  **Disclosed consequence:** the LIVE served bundle carries no such exclusion, so
  this gate measures a contrast and does not measure the served bundle's absolute
  level. The artifact says so in those words.
- **L2 the side label is not side-specific.** Both arms inherit
  E[TOTAL player WAR given this side's line]. **No arm may make a claim about
  two-way accuracy, in either direction.** The served two-way population is n = 1.
- **L3 one WAR basis.** Every arm, both comparators, the corpus and the re-measured
  calibration map run on `war_provider = ewar_v2`. The artifact stamps the provider;
  a run that cannot name its provider is void. Consequence, pre-registered: **every
  published number in `data/proj_horizon_eval.json` and
  `data/proj_calibration_eval.json` predates the 2026-09-03/04 epoch and may be
  cited as a prior, never as a comparator.**
- **L4 the zero convention is published.** `war_actual.get((mlbam, target), 0.0)`:
  an absent season is a zero, not a missing value. The artifact states it beside
  every roughness number, because it is the reason the truth is not smooth.
- **L5 revision leakage, disclosed and not fixable in scope.** Labels come from a
  live `war_daily` pull and eWAR v2 repriced pitcher seasons globally, so a 2009
  label carries its 2026 value. It is shared by both arms and does not bias an
  arm-vs-arm contrast. **It voids any claim of the form "this is what we would have
  said in 2012"**, and no artifact may make one.
- **L6 the calibration map must be re-measured on the SERVING engine before ARM B
  exists.** The three cells describe `marcel_decay_v2`. Re-measuring them on the
  served composition measures the shipped engine, not a candidate, so it burns
  nothing. A lever whose cell is not resolvable on the serving engine ON THE GATE
  FRAME, under the map's own convention (absolute bias above 1.96 sd, 300-draw
  cluster bootstrap over players, at least 20 players per cell), is **DEAD ON
  ARRIVAL** and its arm does not run (5.6).
- **L7 population drift.** `build_features` returns None exactly when the champion
  cannot project (`test_no_population_drift_vs_champion`). Row-matched scoring
  (`proj_eval.run_rowmatch`, which raises on any n mismatch) is the only admissible
  cut. Cross-base comparisons are inadmissible and the registry already says so:
  "Cross-base comparisons ... must not be cited as a win."
- **L8 the training frame is triangular and the penalty must survive it.**
  `build_training_frame`'s own docstring: "a row contributes to horizon h only when
  `base+h-1 <= max_label_season` (later horizons simply have fewer rows)". Design-day
  at `max_label_season 2025`: hit 19,965 / 19,038 / 18,092 / 17,187 / 16,341 and pit
  24,325 / 22,997 / 21,617 / 20,340 / 19,083, so 81.8 percent of hit base rows and
  78.4 percent of pit base rows carry all five horizons, and the share is LOWER at
  every historical base. The penalty's definition on short groups is registered in
  4.1 item 3 and the per-base share is published in the gate artifact. A lab that
  silently drops short groups instead of applying the registered rule is void: it
  would train on a survivor-selected frame.

---

## 3. Power, measured before anything is adjudicated

`tools/proj_shape_mde_lab.py` -> `data/proj_shape_mde.json`. **No criterion below
may be read before this artifact exists.**

### 3.1 The frame this lab is allowed to touch

**The MDE lab runs on the DEV frame (4.6) and on design-matched simulation, and on
nothing else.** A GATE, CONFIRM or Tier-2 row appearing anywhere in
`data/proj_shape_mde.json` or in the process that produced it is an **automatic
VOID that consumes the arm's look**, because the candidate's point estimate on a
verdict-bearing frame would then exist three weeks before the registered look. The
artifact records the exact bases and label seasons it read, and
`test_proj_shape_gate.py` pins that the recorded set is a subset of DEV.

Transport of the DEV standard error to the GATE frame is registered here and is not
chosen later: `sd_GATE = sd_DEV * sqrt(n_players_DEV / n_players_GATE)`, with both
player counts published. Clustering is on player, so the scaling is in players and
not in rows.

### 3.2 The protocol

- **Paired bootstrap, clustered on PLAYER, never on row.** One player supplies
  several horizons at one base and several bases; a row-level bootstrap would treat
  hundreds of thousands of correlated rows as independent. The calibration lab
  already clusters on players and refuses a cell with fewer than 20.
- **The bootstrap that will actually run, registered as such.**
  `docs/EFV_GATE_STANDARD.md:90` records that a test-only bootstrap understates sd by
  1.6 to 1.8 times, and 4.12 records that a full refit per draw across three GATE
  bases and two arms is weeks of compute. An unrunnable protocol becomes a cheap one
  at scoring time, in the direction that ships the arm, so the runnable one is
  registered now:
  - **PRIMARY: B = 1000 test-only paired draws, clustered on player, SEED = 20260918**,
    with a **registered variance inflation factor VIF = 1.8** applied to every `sd`
    before any bound or p-value is formed. 1.8 is the TOP of the house's published
    range, because an inflated sd is the conservative direction for every clause in
    this gate (3.4).
  - **CALIBRATION: B = 200 full-refit draws on the DEV frame only**, refitting both
    arms per draw, to MEASURE `ratio = sd_full / sd_test`. If the measured ratio
    exceeds 1.8, **the measured ratio replaces 1.8**. It is never replaced by a
    smaller number, whatever the measurement says.
  - `data/proj_shape_gate.json` records, and `test_proj_shape_gate.py` pins:
    `B`, `refits_per_draw`, `train_resampled` (bool), `vif_registered`,
    `vif_measured`, `vif_applied`, `seed`, and the wall time. A downgrade is then
    visible in the artifact instead of invisible in a script.
- **Forward-chained.** The DEV bases are named in 4.6 and the lab may use no others.
- **MDE95 is ONE-SIDED (1.645 sd)** for every directional clause, stated explicitly
  because this convention was implicit in this repo once and had to be recovered.
  The re-measured calibration map (L6) keeps its own **two-sided 1.96 sd**
  `resolvable` convention, because an unsigned bias has no registered direction.
  Every clause below names which one it uses.
- **One floor per statistic class, and floors are NOT transferable between classes**:
  pooled MAE delta; per-horizon MAE delta; pooled signed bias; star-slice MAE;
  star-slice bias; P10-P90 coverage; pinball q10 and q90; and, separately, each
  ARM B lever's slice bias.

### 3.3 The detection check

A design-matched simulation with an effect planted at the size being claimed. For
ARM A, a planted +0.0065 WAR MAE degradation. For each ARM B lever, a planted bias
equal to the **nearer-zero end of that lever's published CI**, not its point estimate:
role:C +0.186, star -0.149, age cells at their own CI bounds. The point estimates are
selected maxima from a 65-cell screen (1.2) and planting them would overstate the
battery's power and make an UNDERPOWERED verdict less likely than it should be. If
the harness cannot see the planted effect, a verdict on that clause is a dead
instrument, not a finding, and the clause reads UNDERPOWERED.

### 3.4 Which direction a wrong floor errs, stated correctly

An earlier draft said "an over-wide floor is the permissive direction: it
manufactures passes". That is backwards for this battery and is corrected here:

- S1 forms a one-sided UPPER bound, `point + 1.645 * sd`, and passes when the bound
  is below M. **A larger sd raises the bound and makes a pass HARDER.** A
  too-NARROW sd manufactures the non-inferiority pass.
- ARM B's Holm steps reject when `p` is small, and `p` grows with sd. **A larger sd
  makes a Holm rejection HARDER.** A too-narrow sd manufactures the Holm pass.
- An over-wide sd therefore manufactures NULLs and UNDERPOWERED verdicts, not passes.

So the floor estimator's own **two-sided coverage check, `n_check >= 200`**, exists
to catch the NARROW direction above all, and the registered VIF (3.2) exists because
the executable bootstrap is known to err narrow. Both are published.

### 3.5 The margin guard

ARM A's primary margin is `M = 0.0065` WAR (4.8). If the power artifact returns
`MDE95(delta pooled MAE) >= M` after the VIF is applied, the arm's verdict is
pre-registered as **UNDERPOWERED_NO_MARGIN**: the battery cannot resolve a
degradation smaller than the margin it is allowed to spend, the arm does not ship on
this battery whatever the point estimate says, and that is NOT a pass.
---

## 4. ARM A - the joint refit with an age-smoothness penalty

### 4.1 What the arm is, in code

The owner ordered a refit with a smoothness penalty, not a clamp and not a post-hoc
monotone projection. The penalty couples the predictions of one player, which no
per-model LightGBM fit can express, so this is a change of estimator shape:

1. **Long-format frame.** One row per (player, base, horizon) instead of one row per
   (player, base) with five label vectors. Cheap: `build_training_frame` already
   stores `X` once with `rows[h]` as an index vector, so the long frame is a vstack
   plus a horizon column. No feature is recomputed. Design-day size at
   `max_label_season 2025`: 90,623 hit rows plus 108,362 pit rows = **198,985**.
2. **Ten heads instead of fifty**, one per (side, quantile), with **horizon** and
   **age-at-target (`age + h - 1`)** as features. Today age-at-target is not
   expressible: only age-at-base is a feature and the horizon is implicit in which
   of fifty models you called.
3. **A custom objective, defined on the horizons that exist.** For player-base group
   `i` with horizon set `H_i` and predictions `p_h` at quantile `q`, the loss is
   `pinball_q(p, y) + lambda * P_i` with

   `P_i = sum over every h such that {h-1, h, h+1} is a subset of H_i, of (p_{h+1} - 2 p_h + p_{h-1})^2`

   A group with no three consecutive horizons contributes **zero penalty and full
   pinball**, and is kept, never dropped (L8). This matters: at
   `max_label_season 2025` about a fifth of base rows are short, and the share is
   higher at every historical base, so a lab that dropped them would train on a
   survivor-selected frame.

   The penalty is quadratic, so its Hessian is exact, constant and computable per
   row: the diagonal contributed to row `h` is
   `2 * lambda * sum over admissible triples containing h of c^2`, where `c` is +1 at
   a triple's endpoints and -2 at its centre. On a complete five-horizon group that
   is exactly `lambda * [2, 10, 12, 10, 2]`. Pinball's own second derivative is zero,
   so a constant pseudo-Hessian of **1.0** is supplied for that part, which is the
   documented LightGBM convention for a custom quantile objective.
4. **The penalty covers ALL FIVE quantile heads, not q50 alone.** `war_by_year_pth`
   is built from the pre-recenter q50 plus `0.8 * (q75 - pre-recenter q50)`, so a
   penalty on q50 alone leaves q75 unsmoothed and `warPTH` keeps wobbling where
   `war` stops. One lambda is shared across all five quantiles (a per-quantile
   lambda is refused, section 15: five parameters chosen after seeing five
   frontiers).
5. **The penalty is applied to the RAW head output**, before the cross-quantile
   monotone sort and before either blend.

### 4.1a The joint heads' hyperparameters, REGISTERED, not tuned later

An unregistered hyperparameter set is a second grid that can be searched after the
dev frontier opens. So the joint arm is fitted at **exactly `proj_ml.LGBM_PARAMS` as
it stands today**, for every horizon and every quantile:

```
objective         custom (pinball + second-difference penalty; see 4.1 item 3)
n_estimators      400
learning_rate     0.05
num_leaves        31
min_child_samples 60
subsample         0.9      subsample_freq 1
colsample_bytree  0.9
reg_lambda        1.0
deterministic     True     force_row_wise True     n_jobs 1
random_state      SEED = 20260611
```

**No hyperparameter above may be changed at any point in this battery, for any
reason, including a failed S6.** The only free parameter is `lambda`, on the fixed
grid in 4.4. `LGBM_PARAMS_LONG_H` has no expression in the joint shape (4.2) and may
not be reintroduced under another name.

### 4.2 The decisions this arm takes in advance, not silently

- **The h4 capacity step disappears.** With horizon as a feature there is one
  parameter set across horizons, so `LGBM_PARAMS_LONG_H` has no expression. This is
  a deliberate removal, and it has a cost: that parameter set was added for a
  measured reason ("the default capacity pulling star medians toward the zero mass,
  h5 star bias -0.88 vs champion -0.64"). The mitigation is horizon and
  age-at-target as features plus the hard star bound S6. **If S6 fails, the arm is
  abandoned, not re-tuned by re-introducing per-horizon capacity**, because that
  would re-introduce the discontinuity the arm exists to remove.
- **Both blend lambda sets are refit POINT-IN-TIME, per base, for BOTH arms.**
  `_implied_mean`'s own docstring: the (1,2,2,2,1)/8 weights and the lift-only
  lambdas are fitted against THIS estimator and must not survive a change to it. A
  heads refit changes q50 and the spread. So at every scored base `B`, both arms'
  mean-blend and star-blend lambdas are refit by the identical published procedures
  (`tools/apply_mean_blend.py`, `tools/fit_star_blend.py`) **on labels at or below
  `B-1` only**. The shipped lambdas are NEVER injected into a historical bundle
  (4.7, leak 10). `data/proj_shape_gate.json` records both arms' per-base lambda
  vectors side by side.
  - **The incumbent's denied horizons carry over.** The shipped star-blend h2 lambda
    is 0 because it FAILED its 2022-2024 holdout confirmation, and `data/proj_star_blend.json`
    reads `{1:0, 2:0, 3:0, 4:0, 5:1.0}`. A candidate may not carry a nonzero lambda
    at a horizon where the incumbent's was denied for failing confirmation. The
    candidate's fitted-but-denied values are published; the served values are zero
    there. Otherwise the candidate would ship a lambda the incumbent was refused.
  - At the FLIP, the live bundle's lambdas are refit on full labels by the same two
    tools and re-stamped, and `test_mean_blend_pinned_to_artifact` /
    `test_star_blend_pinned_to_artifact` move in the same commit.
- **Both arms are scored BLENDED.** This departs from every published forward-chained
  receipt, which scores an unblended q50 because `train()` never writes the blend
  lambdas into bundle meta (section 0). The departure is the point: the thing
  measured must be the thing served. Every prior receipt is therefore a prior, not a
  comparator (L3).

### 4.3 The comparators, all three named before any number

- **S (the shipped composition)**: `proj_lgbm_v1` heads, retrained point-in-time per
  base with FULL quantiles, under the L1 two-sided exclusion, plus the mean blend
  and the star blend refit point-in-time per 4.2. **This is the comparator the
  primary criterion tests against.**
- **A0 (the identity arm)**: the joint shape at `lambda = 0`, under the same custom
  objective, the same long frame and the same ten heads. It exists because
  `objective="quantile"` performs leaf-value renewal (leaf outputs replaced by a
  weighted percentile of leaf residuals) and a custom objective does not, so **the
  candidate at lambda = 0 is NOT the shipped estimator**. Without A0 any measured
  delta is the objective change plus the penalty with nothing separating them.
- **C (the champion)**: `marcel_decay_v2` via `contract_war_path(use_ml=False)` on
  the same rows. It is the floor in S2 and the smoothness reference in 4.5. It is
  never the headline comparator.

**A0's reproduction tolerance is checked on the DEV frame and nowhere else**, so
that the check cannot become a second look: pooled h1 MAE within **0.0050** and
pooled signed bias within **0.0100** of S on the same DEV row-matched cut. If A0
lands inside that tolerance, the primary is scored against S alone on the GATE
frame. **If A0 lands outside it, the primary must clear against BOTH S and A0 on the
GATE frame**, and the arm may not cite whichever comparator is kinder; the artifact
publishes both deltas side by side. S8 (4.8) records which of the two branches fired.

### 4.4 How lambda is chosen, before the look

Lambda is selected **on the DEV frame only** (4.6), on the pre-registered grid
`lambda in {0, 0.05, 0.10, 0.20, 0.40, 0.80}`, by one rule, in the form the S2
feasibility pre-flight (4.4a) leaves standing:

> **Form 1 (if the pre-flight says S beats the champion at every DEV horizon):**
> the largest lambda on the grid whose DEV per-horizon MAE stays strictly below the
> champion's DEV per-horizon MAE at every horizon present in the DEV frame.
>
> **Form 2 (if the pre-flight says S does not):** the largest lambda on the grid
> whose DEV per-horizon shortfall against the champion exceeds the INCUMBENT's own
> shortfall by no more than `M = 0.0065` at any horizon present in the DEV frame,
> that is `MAE(cand,h) - MAE(champ,h) <= MAE(S,h) - MAE(champ,h) + 0.0065`.

Form 1 is the rule the mean-blend lambdas were chosen under ("raised to the MAX that
still beats the prior champion's holdout MAE"), reused verbatim so the selection is
not a new degree of freedom. Form 2 exists because a criterion that the INCUMBENT
also fails is not a criterion about the candidate; both forms are registered here,
before any candidate exists, and which one applies is decided by a measurement on
the incumbent alone.

**The DEV frame carries horizons h1 to h4 only** (4.6). That is deliberate and not a
gap: the second-difference penalty's triples are centred at h2, h3 and h4, so DEV
covers the whole region the penalty acts on, and h5 enters only as the right endpoint
of the h4-centred triple. The h5 champion comparison is adjudicated on the GATE frame
by S2 and by nothing else.

**No lambda is chosen or adjusted after the look.** The artifact publishes the full
grid: `(lambda, pooled MAE, per-horizon MAE, pooled bias, coverage, RS2, UAF)` at
every grid point, so the roughness/accuracy frontier is visible and the chosen point
is not the only one shown. If no grid point satisfies the applicable form, the arm
reads **NULL_NO_ADMISSIBLE_LAMBDA** and is abandoned; the grid is not extended after
the fact.

### 4.4a The S2 feasibility pre-flight, which scores the INCUMBENT and burns nothing

Before the ARM A look, `S` alone (blended, point-in-time, row-matched, under the L1
exclusion) is scored against the champion per horizon on the DEV frame and on the
GATE frame. This measures the shipped engine, not a candidate, so it burns nothing.
Its date is 2026-10-09 (section 13) and it must exist before 4.4's lambda rule can be
applied.

It exists because the arithmetic already on disk says the champion floor may not be
clearable by the SERVED composition. The row-matched unblended challenger beat the
champion by 0.0142 at h1 on the 2017-2021 bases; the P-MBLEND re-measure records that
the mean blend costs **+0.0186 MAE at h1** (CI95 [+0.0153, +0.0215]). On different
bases the same re-measure records the blended composition clearing the champion
(h1 0.5734 against 0.6129), so this is genuinely unknown until it is measured. A gate
whose champion floor is unclearable by the incumbent would return
NULL_NO_ADMISSIBLE_LAMBDA for an arithmetic reason that has nothing to do with
smoothness, and that is not a finding.

The pre-flight result selects Form 1 or Form 2 in 4.4 and the corresponding S2 row in
4.8, **per frame**, and the selection is recorded in `data/proj_shape_gate.json`
before the look with the incumbent's numbers beside it.

### 4.5 The smoothness statistic, named exactly, and why it is NOT the criterion

**The registered primary smoothness statistic is RS2, the per-path root-mean-square
second difference of the served central path over h1..h5:**

> for a path `w1..w5`, `RS2 = sqrt( (1/3) * sum over t in 2..4 of
> (w_{t+1} - 2 w_t + w_{t-1})^2 )`, reported as the MEAN and the MEDIAN over the pool.

**The registered second statistic is UAF, the up-after-a-fall STEP RATE:** the
fraction of adjacent steps `t -> t+1` that are strictly upward after the path has
already fallen at least once at or before `t`.

**RAF, the rise-after-a-fall PATH COUNT** (the owner's "257 of 447"), is reported for
continuity and is explicitly **not** a registered headline.

Pool, and it is counted at scoring time, not carried from here: served veteran rows
with a complete five-year path whose year-1 value is at or above 1.0 WAR. Design-day
values on the 2026-09-18 artifact, published so the recount can be checked against
them rather than replaced by them:

| series | pool | RS2 mean | RS2 median | UAF | RAF |
|---|---|---|---|---|---|
| `war` (served central path, what the board and surplus read) | 278 | **0.4362** | 0.3668 | **177 / 1,112 = 0.1592** | 153 |
| `warPTH` (the pre-`05a25ce1` display series) | 447 | 0.5749 | 0.4778 | 328 / 1,788 = 0.1834 | 279 |
| `warChamp` (the champion aging path) | 311 | **0.0670** | 0.0451 | **0 / 1,244 = 0.0000** | 0 |

The owner's 257 of 447 is `warPTH` on an earlier regeneration of the same artifact;
the same rule on the same denominator reads 279 today, with no code change in
between. That drift is itself the argument below.

**Why RS2 and not RAF.** RAF saturates (a path that wobbles once counts the same as
one that wobbles four times), is magnitude-blind (a 0.01 WAR uptick counts the same
as a 2.0 WAR uptick), and is defined only on a filtered pool, so it moves nightly as
the artifact regenerates. It already moved 257 to 279 on its own. RS2 is continuous,
magnitude-weighted, defined on every path and is the exact quantity the penalty
minimises.

**And that last property is precisely why RS2 cannot be a criterion.** A smoothness
penalty makes RS2 fall **by construction**. Scoring the arm on RS2 would be
reporting the arm's own objective back as evidence that the arm worked. So:

> **RS2, UAF and RAF are DESCRIPTIVE. No verdict in this gate turns on any of them
> in the PASSING direction. The only clauses they govern, A-SHAPE and Tripwire 2,
> can FAIL an arm and can never pass one.**

UAF is reported alongside RS2 because it is **not** the objective: a
second-difference penalty can reduce curvature without changing the sign pattern of
the steps, so a large RS2 fall with an unchanged UAF is informative about what the
penalty actually did.

#### A-SHAPE, the minimum shape effect. NECESSARY, never sufficient.

Every binding clause in 4.8 is an accuracy non-degrade bound, and a candidate that
smooths essentially nothing passes all of them trivially. Without a floor on the
effect, `lambda = 0.05` with a negligible penalty is the cheapest way to clear S1
through S6, and "the smoothness refit" would then ship, bump `MODEL_VERSION`, refit
both blends and move every priced number on the board, having repaired nothing the
owner reported. So:

> At the chosen lambda, on the recount over the served `war` pool, **both** must
> hold, or the verdict is **NO_EFFECT** and the flag stays `False`:
>
> - **RS2 mean at or below 0.2617**, a fall of at least 40 percent from the
>   design-day 0.4362; and
> - **UAF at or below 0.1192**, a fall of at least 0.0400 absolute from the
>   design-day 0.1592.

Derivation, fixed here so it cannot be re-derived to fit a result: the champion path
sits at RS2 mean 0.0670 and UAF 0.0000 and the served path at 0.4362 and 0.1592; a
repair that does not close at least 40 percent of the distance from the served value
toward zero has not repaired what the owner reported. `0.4362 * 0.60 = 0.26172`,
registered as 0.2617. The UAF bar is deliberately smaller in relative terms, 0.0400
of 0.1592, because the sign pattern of the steps is **not** what the penalty targets
and demanding a large UAF fall would be demanding an effect the estimator was not
asked to produce.

**A-SHAPE is necessary and never sufficient.** Clearing it is not evidence that the
arm worked, because RS2 falls by construction; failing it is evidence that it did
not. It replaces the earlier draft's Tripwire 1, which was a conjunction that a
candidate at `RS2 = 0.2999` with UAF unchanged would have walked straight past.

**Tripwire 2, the stack-collapse tripwire.** If `RS2 mean` falls to or below the
champion's `RS2 mean` (design-day 0.0670), the arm must publish the share of
candidate prediction variance attributable to `champ_h1..champ_h5` (permutation
importance over those five columns, same seed), pre and post. **If that share rises
by more than 10 percentage points, the arm is abandoned**: the refit has re-become
the champion, whose shape is already a stack feature, and "smooth" would mean "we
stopped modelling".

### 4.6 The frames, and how they are kept disjoint

The frames are cut **by LABEL SEASON**, and the cut is real this time. G-0.1 leaves
label seasons **2008 through 2014** with no prior challenger read, plus **2026** once
the season completes. A cell `(B, h)` belongs to whichever frame owns its label
season `B + h - 1`. Evaluation bases start at 2008 so that every scored bundle has at
least five base-years of training data behind it (`first_base = 2003`, and
`build_features` needs three prior seasons, so 2003 is the earliest base that exists
at all).

| frame | label seasons it owns | cells | horizons present | used for | may it carry a verdict |
|---|---|---|---|---|---|
| **DEV** | 2008, 2009, 2010, 2011 | (2008, h1-h4), (2009, h1-h3), (2010, h1-h2), (2011, h1) = 10 | h1-h4 | lambda selection (4.4), the frontier table, the A0 tolerance check (4.3), the MDE lab (3.1), every ARM B lever FIT | **no** |
| **GATE** | 2012, 2013, 2014 | (2008, h5), (2009, h4-h5), (2010, h3-h5), (2011, h2-h4), (2012, h1-h3), (2013, h1-h2), (2014, h1) = 15 | h1-h5 | the primary and every secondary in 4.8-4.9; every ARM B adjudication in 5.5 | **yes** |
| **CONFIRM** | 2026 | (2022, h5), (2023, h4), (2024, h3), (2025, h2), (2026, h1) | h1-h5 | the touched-once confirmation, opened exactly once at the ARM A look | **yes, once, and only under 4.6b** |
| **TIER-2 (READ)** | 2015 - 2025 | everything the ledger in G-0.1 consumed | h1-h5 | reported, labelled READ; the full-depth transport check (4.6c) | **VETO ONLY (4.6a)** |

**What the cut does and does not claim.** No scored OUTCOME is used by two frames:
the label-season partition is exact and `test_proj_shape_gate.py` pins that the
label-season sets of DEV, GATE and CONFIRM are pairwise disjoint and that each
published cell's label season lies in its own frame's set. A single evaluation base
can contribute cells to two frames, because one bundle predicts five horizons: base
2010 gives h1-h2 to DEV and h3-h5 to GATE. **The frames therefore share a FIT while
sharing no LABEL**, which is the same relationship any horizon-split validation has,
and it is disclosed here rather than claimed away. The control on it is that lambda
is one ordered choice from a fixed six-point grid under a rule fixed in advance
(4.4), not an optimisation over the GATE frame, and that the full frontier is
published so the selection is auditable.

**Two disclosures that ride with this frame, and neither is optional.**

1. **Era.** The GATE frame's label seasons are 2012-2014. The served population is
   2027. A shape effect validated on that run environment may not transport, and no
   artifact may claim it does. The CONFIRM frame (label season 2026) exists partly
   to speak to this, and the Tier-2 transport check (4.6c) exists entirely for it.
2. **Training depth.** A bundle evaluated at base 2012 trains on bases 2003-2011,
   about nine base-years; the serving bundle trains on about 23. Both arms carry the
   identical depth at every base, so the PAIRED delta is unbiased by it, but the
   lambda chosen at DEV depth need not be the lambda that is right at serving depth.
   That is what 4.6c measures.

#### 4.6a A read frame may VETO, never CONFIRM

Tier-2 label seasons are read, so a candidate result on them cannot be evidence that
the arm worked. But a read frame can still say the arm is broken, and refusing to
look at it would be discarding the most informative data in the repo. So the
asymmetry is registered:

> **Tier-2 reports its pooled and per-horizon deltas with full bounds. If the Tier-2
> pooled one-sided upper bound on `delta MAE` reaches or exceeds `M = 0.0065`, ARM A
> does NOT ship, whatever the GATE frame says. No Tier-2 number may ever be cited in
> support of shipping, in any artifact, note or commit message.**

A frame that can only fail an arm cannot be gamed into passing one.

#### 4.6b CONFIRM, and the condition under which it exists

CONFIRM is label season 2026, which no artifact in this repo has ever scored, on
either engine, because the label did not exist. It opens **only** when the corpus
carries complete 2026 season WAR for the scored population, asserted by a registered
check that the artifact records (`corpus["last"] >= 2027` under the harness's
complete-seasons convention, plus a published 2026 games-played census). Today
`season_fraction` reads 0.947.

- If the condition holds at the ARM A look, CONFIRM is scored **once**, it is spent,
  and it may CONFIRM or VETO: its own one-sided upper bound reaching or exceeding `M`
  fails the arm.
- If the condition does not hold, CONFIRM reads **NOT_AVAILABLE**, the ARM A verdict
  rests on the GATE frame alone, and the artifact says so. NOT_AVAILABLE is not a
  pass and is not a failure.
- If the row-matched scored n in CONFIRM falls below **1,000** after matching, CONFIRM
  reads **UNDERPOWERED** with the shortfall published, and the verdict again rests on
  GATE alone.
- ARM B reads CONFIRM only if ARM A left it unspent. If ARM A spent it, ARM B reports
  it as ALREADY READ and it carries no verdict for ARM B.

#### 4.6c The full-depth transport check, veto-only

After the ARM A look and never before, both arms are refit at FULL depth
(`max_label_season 2025`) and scored on the Tier-2 frame. This is the only
measurement in the battery taken at serving depth. It is reported with its bounds,
labelled READ, and it is governed by 4.6a: it can veto the arm and it can never
support it. Its purpose is to answer, on the record, whether the lambda chosen at DEV
depth is still admissible at serving depth.

#### 4.6d Held fixed across every arm, so the contrast is the penalty and nothing else

The same `.cache/fa_corpus.pkl` with the same `first`/`last` and
`war_provider = ewar_v2`; `first_base = 2003`; `max_label_season = B - 1` per base;
point-in-time `fp.fitted_models(corpus, B - 1)` for both arms; `champ_h1..h5` from
the same `use_ml=False` path; the identical row population, row-matched by
`run_rowmatch`; the L1 two-sided exclusion on both arms; one blend convention across
both arms (4.2); `SEED = 20260611` for the fits, `deterministic=True`, `n_jobs=1`,
`force_row_wise=True`; the same five quantiles, the same cross-quantile monotone sort
and the same `_extend` for h6-h15.

A model evaluated at base `B` trains only on rows whose LABEL season is at or below
`B - 1`. **The fit half is never graded, by construction rather than by discipline**,
and any lab that trains once on all labels and scores several bases is void.

### 4.7 The leak inventory, and the control for each

1. **The shipped bundle has seen everything** (`max_label_season 2025`). It is never
   the arm scored at a historical base. Per-base bundles only, and the scorer
   compares `meta["max_label_season"]` against `B - 1` and raises.
2. **The frame disk cache key carries nothing about the rows.** An arm on a modified
   corpus reads AND overwrites the production frame. **Every candidate lab passes
   `use_cache=False`**, which disables both the read and the write. This is the
   P-FITCACHE trap; `fp.fitted_models` is safe today only because its key digests
   the rows via `_corpus_sig`, and the proj_ml frame key does not.
3. **PIT bundle collision.** `proj_ml_pit_{MODEL_VERSION}_{SCHEMA_TAG}_{max_label_season}_{qtag}{war_tag}`:
   an unbumped `MODEL_VERSION` writes a candidate bundle where the champion's is
   read. The real readers of `proj_ml.train_cached` are **`proj_eval.py:219`** and
   **`tools/war_cohort_diagnostic.py:236`**; `fa_market.py:2169` is a COMMENT
   recording that ML paths FAILED FA Gate 2, and the FA market stack calls
   `fp.fitted_models` with `use_def=FA_PRICING_USE_DEF` and prices off champion
   paths. **Bumping `MODEL_VERSION` is a correctness control here, not bookkeeping**
   (section 8).
4. **In-process `_PIT_CACHE` is keyed by `max_label_season` alone** (proj_ml.py:560,
   566), so one process evaluating two arms at one base serves the first arm's bundle
   to the second. Arms run in separate processes, or the dict is cleared between
   them, and the artifact records which.
5. **No outcome-season feature exists, and this is stated so nobody re-flags it.**
   `war_l*` and `expo_l*` read base-1..3; `_xstats` reads base-1; `_def_prior` reads
   base-1..3; `_league_mean(league, base-1)` resolves through `_league_recent` to
   base-1..base-3. The `+1` that looks like lookahead is a target-season convention
   shared with `fit_war_map`.
6. **Revision leakage** (L5): shared by both arms, biases no contrast, voids any
   real-time claim.
7. **Read frames** (G-0.1, 4.6a): Tier-2 carries no confirming verdict.
8. **`predict_path`'s schema guard compares WIDTH, not names** (proj_ml.py:468), so
   two schemas of equal width pass and mis-predict positionally. The joint shape
   changes the feature count anyway, but the guard is upgraded to compare names in
   the same commit, and the upgrade is listed in section 12.
9. **`season_idx = float(base)`** and the live serve builds at base 2027 while the
   deepest training base with an h1 label is 2025. Trees cannot extrapolate, so 2027
   lands in the terminal bin. A train/serve shift, not a leak, and the artifact says
   so beside the served numbers.
10. **BLEND-LAMBDA LOOKAHEAD, the leak the earlier draft did not list.** The shipped
    mean-blend lambdas were fitted 2026-06-13 and holdout-confirmed on 2022-2024; the
    shipped star-blend lambda was fitted on dev bases through 2021. Injecting either
    into a bundle evaluated at base 2012 imports labels from 2022-2024 into a 2012
    prediction. **Control: both arms' blend lambdas are refit point-in-time on labels
    at or below `B - 1` at every scored base** (4.2), the shipped lambdas are never
    injected into a historical bundle, and the per-base lambda vectors are published
    for both arms. A run whose artifact does not carry per-base lambda vectors is
    void.

### 4.8 The criteria. S1 is the PRIMARY and it is an accuracy test, not a smoothness test

**The primary criterion is that accuracy does not get worse.** It cannot be
smoothness: a smoothness penalty makes the path smoother by construction (4.5), so a
smoothness criterion is a criterion the arm passes by existing. The only thing that
is genuinely at risk when the estimator shape changes is accuracy, so that is what is
adjudicated, as a **non-inferiority** test with a margin registered before any
number is read.

| id | claim | statistic and direction | criterion | fails if |
|---|---|---|---|---|
| **S1 PRIMARY** | the refit is not less accurate than what serves today | `delta = MAE(candidate) - MAE(S)`, pooled over h1-h5 and both sides on the GATE frame, row-matched, paired bootstrap clustered on player, B=1000, seed 20260918, sd multiplied by the registered VIF (3.2). Lower is better; the test is **one-sided non-inferiority** | the **one-sided upper 95% bound (point + 1.645 sd) of `delta` is strictly below M = +0.0065 WAR** | the bound reaches or exceeds +0.0065 |
| **S1b** | no single horizon pays for the pooled pass | per-horizon `delta` on the GATE frame, **point estimate**, no significance test | at every horizon, point `delta` strictly below **+0.0130 WAR** | any horizon at or above +0.0130 |
| **S1c** | the read frame does not contradict the verdict | Tier-2 pooled `delta` upper bound (4.6a), and CONFIRM's upper bound when 4.6b makes it available | both strictly below M = +0.0065 | either reaches or exceeds M. **Neither may ever support a pass** |
| S2 | the refit does not fall behind the fallback engine | candidate MAE against champion `marcel_decay_v2` MAE, per horizon, same rows, in the form the 4.4a pre-flight leaves standing. Lower is better | **Form 1:** candidate MAE strictly below champion MAE at every horizon. **Form 2:** `MAE(cand,h) - MAE(champ,h) <= MAE(S,h) - MAE(champ,h) + 0.0065` at every horizon | the applicable form is violated at any horizon |
| S3 | the level does not drift | pooled signed bias per horizon, point estimate. Nearer zero is better | absolute bias grows by at most **+0.0200 WAR** at any horizon against S | any horizon worse by more than 0.0200 |
| S4 | the bands survive a penalty applied to all five heads | P10-P90 empirical coverage, per horizon, **as a delta against S measured on the same frame** | coverage moves by at most **0.0200 absolute** against S at any horizon, and stays within **[0.75, 0.87]** in absolute terms | either bound crossed |
| S5 | the tails are not paid for out of the quantiles | pinball loss at q10 and q90, per horizon, point estimate. Lower is better | worsens by at most **+0.0050** at either tail at any horizon | any tail worse by more than 0.0050 |
| S6 | the star slice does not pay for the smoothing | star-slice (ex-ante base WAR at or above 4) MAE and signed bias, per horizon, point estimate | star MAE worsens by at most **+0.0500**, and star bias does not become **deeper** (further from zero) than S at any horizon | either bound crossed |
| S7 | the population did not move | scored row count per cell against S | identical by construction; `run_rowmatch` raises on any mismatch | any mismatch |
| S8 | the objective change is separated from the penalty | A0 reproduction on DEV (4.3) | A0 within pooled h1 MAE 0.0050 and pooled bias 0.0100 of S on DEV, **or** S1 cleared on GATE against both S and A0 | neither holds |
| **A-SHAPE** | the penalty did something (NECESSARY, never sufficient) | RS2 mean and UAF on the served `war` recount at the chosen lambda (4.5) | RS2 mean at or below **0.2617** AND UAF at or below **0.1192** | either misses: verdict **NO_EFFECT** |

**Where M = 0.0065 comes from, derived before any number.** The row-matched edge the
served engine holds over the champion is 0.0142 / 0.0271 / 0.0279 / 0.0199 / 0.0106
by horizon, mean 0.019940. M is **one third of that mean edge, rounded DOWN**:
`0.019940 / 3 = 0.006647`, registered as **0.0065**. Rounding down is the
conservative direction, because a smaller margin is a harder bar. The reasoning, fixed
here so it cannot be re-derived to fit a result: a shape repair may spend at most a
third of the accuracy that justified serving this engine over the fallback at all.
Spending more means the repair has traded away the reason the engine exists, and the
correct response to that trade is to serve the champion, not a smoother challenger.
M is stated in WAR and not as a percentage because every consumer of `war` is linear
in WAR. **The source numbers are pre-epoch priors (L3) and M is frozen regardless of
what a later re-measure on `ewar_v2` returns** (section 15).

**Where S1b's +0.0130 comes from.** A per-horizon cell carries roughly a fifth of the
pooled n, so its sampling noise is about `sqrt(5) = 2.24` times wider. Doubling the
pooled margin is deliberately LESS than that, so S1b stays a real constraint rather
than a formality, while not failing an arm for ordinary per-horizon noise.

**Why the significance test runs only on S1 and S1c.** They are non-inferiority
tests: the candidate must PROVE it is not worse, so requiring statistical resolution
is the conservative direction. S1b and S3 to S6 are non-degrade bounds and are scored
on the **point estimate against an absolute bound, with no significance test**,
because requiring a degradation to be statistically resolvable before it counts is
the **permissive** direction: it manufactures passes. Their bootstrap intervals are
still published; they are evidence, not the gate.

### 4.9 Why ARM A has no Holm family, stated so the absence is a decision

The house corrects multiplicity when several arms compete to show an improvement and
the winner ships. **No leg of ARM A claims an improvement.** S1 and S1c are
non-inferiority and S1b, S2 to S6 are non-degrade bounds; A-SHAPE can only fail.
Running Holm over non-degrade legs would loosen each leg's alpha and make degradation
harder to resolve, which is backwards: it would let an arm ship by testing more
things. So ARM A is adjudicated leg by leg against the absolute bounds above, and the
multiplicity correction is reserved for ARM B (5.5), where three levers do compete to
show a resolvable improvement and whichever passes would ship.

This is written down because an absent Holm family and a forgotten Holm family look
identical in an artifact. `data/proj_shape_gate.json` carries
`"holm": {"arm_a": "NOT_APPLICABLE_NON_INFERIORITY", "arm_b": {...}}` rather than
omitting the key.

### 4.10 Arms refused, and why, so a later retreat to one is visible as a retreat

- **A clamp on the served series.** Refused by the owner on 2026-09-18 and refused
  here: it moves a served number without measuring anything.
- **LightGBM `monotone_constraints`.** A WAR path is not monotone in age (it peaks),
  and a monotone-in-horizon constraint is a forced decline, false for young players.
  This is the clamp wearing a hyperparameter costume.
- **Post-hoc isotonic or monotone projection of the five points.** The post-hoc
  projection the owner refused.
- **A low-dimensional smooth shape head** (a level at h1 plus a fitted shape basis).
  It converges on re-becoming the champion, whose shape is already the fitted aging
  curve and already a stack feature. Tripwire 2 (4.5) exists because the penalised
  refit can drift toward this without anyone choosing it.
- **"Leave it and disclose."** Refused by the owner.
- **A per-quantile lambda.** Five parameters chosen after seeing five frontiers.
- **Re-introducing per-horizon capacity after a failed S6** (4.2), or changing any
  hyperparameter in 4.1a for any reason.

### 4.11 What makes ARM A FAIL and be abandoned

Abandoned means: the flag stays `False`, `MODEL_VERSION` does not move, the shipped
bundle keeps serving, the NULL sentence in section 11 is published, and the arm may
return only as a new registration on a later label year.

- **A-F1.** The one-sided upper bound of pooled `delta MAE` against S on the GATE
  frame reaches or exceeds **+0.0065 WAR**. In words: the repair costs more than a
  third of the accuracy edge that justified serving this engine over the champion.
- **A-F1b.** Any per-horizon point `delta` reaches or exceeds **+0.0130**.
- **A-F1c.** Tier-2's or an available CONFIRM's own upper bound reaches or exceeds M
  (4.6a, 4.6b). In words: the frame that has the most data says the arm is worse, and
  a read frame is allowed to say that.
- **A-F2.** S2's applicable form is violated at any horizon. In words: a smoother
  path that is not better than the aging curve is the aging curve, and the aging
  curve is already on disk and free.
- **A-F3.** A0 misses its DEV reproduction tolerance AND the primary does not clear
  on GATE against both S and A0. In words: the measured delta is the objective change
  plus the penalty and nothing separates them.
- **A-F4.** Coverage moves by more than 0.0200 against S at any horizon, or leaves
  [0.75, 0.87] absolutely. In words: the penalty was paid for out of the bands.
- **A-F5.** Star MAE worsens by more than 0.0500 or star bias gets deeper at any
  horizon. In words: the removal of the h4 capacity step cost the star regime the
  structure it was added to give it.
- **A-F6.** A-SHAPE misses on either leg: **NO_EFFECT**. In words: the penalty did
  not smooth the board, and the arm is abandoned rather than re-tuned by raising
  lambda after the look.
- **A-F7.** Tripwire 2: `RS2 mean` at or below the champion's and the champion-stack
  variance share up more than 10 points. In words: the refit re-became the champion.
- **A-F8.** `MDE95(delta pooled MAE) >= 0.0065` from the power artifact:
  **UNDERPOWERED_NO_MARGIN**, which is not a pass.
- **A-F9.** No grid lambda satisfies the applicable form in 4.4:
  **NULL_NO_ADMISSIBLE_LAMBDA**.
- **A-F10.** Any leak control in 4.7 is found violated in the run: **VOID**, under
  the cap in 4.11a.

#### 4.11a The VOID cap, because a do-over is not free

A VOID is a re-run the operator declares on itself, so without a cap it is an
uncapped do-over that ends whenever a result is liked.

> **At most ONE void re-run per arm.** The void is appended to section 19, naming the
> control that was violated and the artifact hash of the voided run, **before** the
> re-run starts; no voided artifact is deleted. A SECOND void on the same arm closes
> the arm for this battery with verdict **VOID_CLOSED**, and the arm returns only as
> a new registration that discloses both voids.

### 4.12 Cost, measured once rather than inherited

Fitting is single-digit minutes per bundle in either shape, and a Python objective
callback over about 200k rows is not the bottleneck. **Frame assembly dominates**:
each of about 44k base rows runs a full champion `contract_war_path` plus a second
`project_player` in Python, and a K-base battery rebuilds whole prefix frames, so
budget tens of minutes to a couple of hours per arm. The B=200 full-refit calibration
bootstrap (3.2) is the largest single item and is confined to DEV for that reason.
Disk, measured on 2026-09-18: `.cache` currently holds **29 point-in-time pit bundles
totalling 793,446,247 bytes (about 757MB)**, and a new `_SCHEMA_TAG` re-materialises
those plus 6 frame caches at about 17MB each. Serve cost is flat (about 38k
single-row `_predict1` calls either way, about 3.5s). **These are estimates with
their basis stated. The gate artifact records the measured wall time of the first run
and this paragraph is then replaced by it.**
---

## 5. ARM B - the three bias levers

### 5.1 The prerequisite, and why it burns nothing

**B0.** Re-measure `proj_calibration_map` on the **serving composition** and on
**`ewar_v2`**: the LightGBM q50 head after the mean blend and the star blend, not
`fm._decay_path`. Same protocol as the published map (forward-chained, curves and
WAR map fit on labels at or below `B-1`, absent target scored 0, 300-draw cluster
bootstrap over players, `resolvable = |bias| > 1.96 sd`, at least 20 players per
cell). B0 publishes **two cuts**:

- **B0-COMPARE**, on the published map's own 7 bases (2014-2021 ex-2020), so the
  champion map and the served map are comparable cell by cell. These are Tier-2 label
  seasons and this cut is a measurement of the INCUMBENT; it burns nothing and it
  carries no adjudication.
- **B0-GATE**, on the **GATE frame** (4.6). These are the cells every clause in 5.5
  reads. B0-GATE is the PRE leg of the paired statistic in 5.5 and is measured on the
  incumbent by design, so it is not a candidate read.

**B0-GATE will be thinner than the published map and that is the conservative
direction.** The GATE frame carries 15 base-horizon cells against the published map's
35, so a cell's n should land near 40 percent of its published n (role:C 4,585,
star 2,085, age:<=24:pit 755). A cell that is no longer resolvable at that n is
**DEAD ON ARRIVAL** (B-F1). **Widening the frame to restore resolvability is banned**
(section 15): it would be re-cutting the gate after seeing that a lever failed it.

This measures the shipped engine. It is a **prerequisite**: until it exists, no lever
is fitted. B0 publishes, for each of the three cells, the champion-engine bWAR prior,
the B0-COMPARE value and the B0-GATE value side by side. The prior is a prior. The
B0-GATE value is the number every clause below reads.

### 5.2 The order, which the owner fixed

Smoothness first, then the levers. Concretely:

1. ARM A runs and its verdict is written into `data/proj_shape_gate.json`.
2. B0 is re-run **on whichever engine serves after that verdict**. If ARM A ships,
   that is the refit engine; if ARM A is abandoned, it is `proj_lgbm_v1` as served.
3. Each lever is then fitted on the DEV frame and adjudicated on the GATE frame
   against the B0-GATE cells of that engine.

**The pre-refit cells may never be cited as evidence for a post-refit lever.**

### 5.3 The absorption rule, which is the whole interaction

The refit makes **age-at-target a feature** and couples the horizons. That is exactly
the mechanism that could absorb B-AGE, and it could move the other two as well.

> **A lever whose B0-GATE cell is no longer resolvable on the serving engine is
> ABANDONED, not shipped and not weakened.** The gate publishes, in these words:
> "the refit absorbed it", with the pre and post cell values and their intervals.

Two consequences, registered now so neither can be decided after a result:

- **k does not shrink.** The Holm family stays at **k = 3** even if one or two levers
  are abandoned at B0. Re-sizing a family after seeing which members survived is
  running the family twice and reporting whichever half won. The mechanics that make
  k = 3 binding in code are in 5.5.
- **A cell that GROWS is not a new arm.** If the refit makes a cell resolvably worse,
  that is reported in the gate artifact and in the registry note, and a lever
  targeting it is a **new registration**, not a reallocation of a slot in this one.

### 5.4 The three levers, one registered PRIMARY form each

| id | registered PRIMARY form | fitted on | parsimony twin | direction |
|---|---|---|---|---|
| **B-AGE** | a side-keyed linear slope in age-at-target applied to the central path, one slope for `hit` and one for `pit`, shipped or not shipped **as a unit** | DEV frame, forward-chained, out of fold, both sides jointly | **NONE.** A single shared slope across sides IS the pooled recentering banned in section 15, and the earlier draft offered it as a twin, which was a direct self-contradiction. B-AGE has exactly one form | reduce absolute bias in the age-at-target cells without raising pooled MAE beyond 5.5's budget |
| **B-C** | a **projected-PT/rate correction on catcher rows**, because the map's own reading locates the miss there ("the miss is in projected catcher PT/rate, not in the map's slope") | catcher rows only, DEV frame, forward-chained, out of fold | an output-side LEVEL term, admissible ONLY under 5.4a | reduce `role:C` bias toward zero |
| **B-STAR** | a star-slice recalibration of the SERVING engine's central path on the ex-ante star slice (base WAR at or above 4) | star rows only, DEV frame, forward-chained, out of fold, on the serving engine | a single scalar on the slice, admissible ONLY under 5.4a | move star bias toward zero without deepening pooled bias |

#### 5.4a The parsimony twin may REPLACE a pass, never RESCUE a failure

The earlier draft let B-C's output-side twin ship when the PT-side primary failed.
That turned a parsimony rule into a second attempt inside one Holm slot, with no
multiplicity accounting. Registered instead:

> **A twin is evaluated only after its lever's PRIMARY form has already PASSED every
> clause in 5.5.** If the primary failed, the lever is a NULL and the twin is not
> run, not reported as a candidate and not shipped.
>
> When the primary passed, the twin ships in its place on parsimony if
> `share >= 0.75`, where
> `share = (|bias_pre| - |bias_post,twin|) / (|bias_pre| - |bias_post,primary|)`,
> both post values being point estimates on the same B0-GATE cell and the same
> out-of-fold rows. **At exactly 0.75 the twin ships** (the boundary is registered so
> it is not chosen later). If the denominator is at or below zero the primary did not
> reduce bias, so it cannot have passed, and the question does not arise.

**B-AGE ships as a unit and k counts it once.** The two sides are one construct, the
pooled version is banned because the sides cancel, and allowing one side to ship
alone would reintroduce that cancellation in the pooled board while giving the family
a fourth shot it was not sized for.

**B-STAR carries a banned list of its own.** The three mean-head forms already
rejected on this row may not be re-run under any name:
`mean_head_rejected` (a dedicated regression head: star bias -0.635 to -0.30 but
pooled MAE 0.507 to 0.543), `star_mean_head` (dev lands on about zero lift, holdout
unchanged), `star_slice_mean_head` (2026-07-24 W-STAR FAIL: dev star bias +0.065 to
+0.276, star MAE 1.84 to 1.93). The registry's own conclusion stands and is quoted
in the artifact: "the mean-head lever is exhausted; the real remaining lever stays a
heads-level aging/tail refit." **If ARM A is abandoned, B-STAR does not run at all**,
because the only admissible remaining form of this lever is a recalibration of the
refit heads, and without the refit the lever is one of the three banned arms.

### 5.5 The Holm family, declared before any number is read

> **Family BIAS = {B-AGE, B-C, B-STAR}. k = 3, always. Holm step-down via
> `tools/efv_power_lab.holm_family`, alpha = 0.05, ties broken on the fixed input
> order (B-AGE, B-C, B-STAR). Floors land under the key `mde95_holm_k3`.**

#### 5.5a The mechanics that make k = 3 real, because the code derives k from its input

`tools/efv_power_lab.py:834` sets `k = len(cells)`; `k` is not a parameter. Handing
the function only the surviving levers would silently give `k = 1`, `alpha = 0.05`,
and floors under `mde95_holm_k1` while this document promised `mde95_holm_k3`. So:

> **`holm_family` is always called with exactly three cells, in the fixed order
> B-AGE, B-C, B-STAR.** A lever that was not fitted (DEAD_ON_ARRIVAL, ABSORBED, not
> run, or NULL before its Holm step) enters as `delta = 0.0` with its **registered
> floor as `sd`**, which gives `p_one_sided = 0.5`, sorts it last, and lets it hold
> its slot without blocking the step-down for the levers above it.
> `test_proj_shape_gate.py` pins `artifact["holm"]["arm_b"]["k"] == 3`, the presence
> of all three keys, the fixed order, and that every floor is reported under
> `mde95_holm_k3`.

#### 5.5b The signed statistic, because the function is one-sided on an ABSOLUTE value

`_p_one_sided` computes `p` from `abs(delta) / sd`, so a lever that moved its cell's
bias the WRONG way by a large amount would read `clears_own_holm_step = True`. So the
statistic is named, and its sign is a precondition:

> For each lever, `delta = |bias_pre| - |bias_post|` on its own B0-GATE cell, where
> positive means the bias moved TOWARD zero. **`sign(delta) > 0` is checked BEFORE
> the Holm step.** A lever with `delta <= 0` reads **NULL** regardless of its
> absolute t, and enters the family under the 5.5a substitution.
> `test_proj_shape_gate.py` pins that a negative-delta lever reads NULL whatever its
> `abs_t` is.

#### 5.5c What each lever must clear

- **B1** clear its Holm step at k = 3 on the signed statistic in 5.5b, out of fold,
  on the GATE frame, paired bootstrap clustered on player, B=1000, seed 20260918,
  with the registered VIF applied to sd (3.2);
- **B2** beat its **permuted twin**: **200 permutation draws, seed 20260918**, the
  lever's keying column permuted across players within (label season x horizon)
  cells. Statistic: `cost_ratio = (pooled MAE rise) / (|bias| reduction)` on the
  lever's own cell. The real lever must satisfy
  `cost_ratio_real < 0.5 * median(cost_ratio_permuted)`; the permuted distribution's
  median and IQR are published, not just a point. **Zero-denominator rule:** if the
  permuted twin's `|bias|` reduction is at or below 0.01 WAR the ratio is undefined
  and B2 reads PASS_BY_CONSTRUCTION with the permuted reduction published; if the
  REAL lever's reduction is at or below 0.01 WAR, B2 reads NULL regardless of
  anything else. Precedent: the P-MBLEND re-measure showed a row-permuted
  implied-mean gap buying the same bias reduction at 2.2x the MAE cost, and that
  ratio is what made the targeting real;
- **B3** stay inside its MAE budget: **pooled MAE may rise by at most +0.0100 WAR**,
  and **slice MAE may not rise at all on the point estimate**. The pooled budget is
  deliberately below the +0.0186 h1 MAE the house paid for P-MBLEND, because that
  purchase bought 0.09 to 0.11 WAR of pooled bias while these cells live on narrow
  slices;
- **B4** not deepen any other resolvable cell in the B0-GATE map by more than 0.0500
  WAR. A lever that fixes catchers by breaking corner outfielders has moved the
  problem.

### 5.6 What makes each lever FAIL and be abandoned

- **B-F1, any lever.** Its B0-GATE cell on the serving engine is not resolvable
  (absolute bias at or below 1.96 sd), or the cell holds fewer than 20 players.
  **DEAD ON ARRIVAL**: the lever is not fitted, it enters the family under 5.5a, and
  if ARM A shipped, the published words are "the refit absorbed it". The frame is not
  widened to rescue it.
- **B-F2, any lever.** Its signed bias reduction does not clear its Holm step at
  k = 3, or its sign is non-positive (5.5b). Published as a **NULL**, in that word.
- **B-F3, any lever.** B2 fails under any of its three branches. In words: the lever
  is a level move wearing a slice costume, and what it measured is not the slice.
- **B-F4, any lever.** Pooled MAE rises by more than +0.0100, or slice MAE rises at
  all. In words: the correction is paid for by the rows it was meant to fix.
- **B-F5, any lever.** Another resolvable cell deepens by more than 0.0500.
- **B-F6, B-C specifically.** If the output-side twin ships under 5.4a, **the
  artifact and the registry note must both carry the sentence that the miss is in
  projected catcher PT and rate and that this term repairs the number and not the
  cause.** If that sentence is absent from either, the lever is not shipped. The twin
  may never ship on a failed primary (5.4a).
- **B-F7, B-STAR specifically.** ARM A abandoned, or the fitted form is any of the
  three banned mean-head arms: the lever does not run and the registry's "exhausted"
  sentence is republished.
- **B-F8, any lever.** Its own detection check (3.3) cannot see a planted effect the
  size of the **nearer-zero end** of its published prior CI: **UNDERPOWERED**, which
  is not a pass.

---

## 6. The decision made before the gate ran, and why it was made first

This registration has the same awkward shape as ARBITRATION_GATE 11a and
IN_GAME_MANAGEMENT_GATE: **part of the change already shipped.** On 2026-09-18 at
09:51:31, before any acceptance number for this gate existed, commit `05a25ce1` moved
the `/projections/` DISPLAY from the if-healthy `warPTH` series to the expected-value
`war` series, because the display was running 37.9 percent above the expected value
league-wide and the median row ratio read 0.563. Surplus, FA rational value and Team
Outlook always priced off `war`; what moved was which series the reader saw. Three
consequences, written down rather than left to be discovered:

1. Every clause here is committed BEFORE the code that scores against it. That is
   the part of "pre-registered" that still holds, and it is not a formality: the
   criteria cannot be tuned to a result nobody has seen.
2. It is NOT true that the display revert cleared a bar before it reached a reader.
   It did not. It was a level repair with its own arithmetic in the commit message,
   and it is a receipt, not evidence.
3. **A failure in this gate therefore cannot withhold a ship that already
   happened.** What a failure does is keep a served number where it is, or move it
   back. Section 12 fixes in advance which failure does which.

Section 0a's standing rule applies unchanged: a number measured after a decision is
a receipt, not evidence for it.

---

## 7. Two-way players, under each arm

The served two-way population is **n = 1** (Shohei Ohtani). Everything in this
section follows from that and from L1/L2.

- **Under ARM A.** Two-sided rows (671 corpus player-seasons, 327 with absolute WAR
  at or above 0.5 on both sides) are **excluded from the training frame and from
  every scored cell, in both arms and in the comparator S**. They carry the player's
  TOTAL WAR on each side and are accumulated across sides again by
  `build_training_frame` (proj_ml.py:336) and `proj_eval._assemble`, so they train
  and score at 2x. Excluding them is the only way the contrast means anything.
  **Disclosed:** the live served bundle carries no such exclusion, so the gate
  measures a contrast and not the served bundle's absolute level (L1).
- **Under ARM A, at serve.** The refit still produces a two-way row, because
  `proj_export` runs both sides and sums. The gate makes **no claim** that the row
  got better. The flip commit publishes Ohtani's five-year `war`, `warHit`, `warPit`,
  `warTotal`, `warP10`, `warP90`, `surNpv` and `surTotal` pre and post as a
  **disclosure**, beside the sentence that the population is one, that the label is
  not side-specific, and that the served `war` sum carries no workload discount.
- **Under B-AGE.** The lever keys on side and age-at-target, so it reaches both of a
  two-way player's sides. Permitted, because the slope is a population correction
  and the two-way row is scored by neither half of the fit.
- **Under B-C.** Assert that the catcher slice and the two-way row are disjoint, in
  the commit rather than in a belief. If a future two-way catcher appears, the lever
  does not apply to that row until this gate is amended.
- **Under B-STAR.** Ohtani is ex-ante star (base WAR at or above 4), so the lever
  would reach him. **Two-sided rows are excluded from the star lever's FIT** (L1),
  and applying a lever fitted on single-sided star rows to a two-way row is a
  **separate owner decision** under the section 9.1 rule, not something the Holm
  result authorises.
- **The workload discount is out of scope, named, and given a hard consequence.**
  `TWO_WAY_PIT_PTH_FACTOR = 0.48` applies only to the `warPTH` sum
  (`proj_export.py:740-746`); `_sum_arr("war_by_year")` takes none, so the served
  two-way `war` sum carries **no workload discount at all**. That is the shape of
  the owner's Ohtani complaint and it is an export-lane change (open question 18.7),
  which this lane may not make. **No clause in this battery adjudicates it, so a PASS
  here is not evidence that the owner's Ohtani complaint was addressed.** The half
  this gate addresses is the wobble; the level half shipped in `05a25ce1`. Three
  things this gate does enforce:
  1. the flip commit must state, in the commit message, whether the `war` sum carries
     a workload discount (today: it does not);
  2. the factor was tuned against a PTH series built from the pre-recenter q50 and
     q75, so **any heads refit re-opens that tuning**, and the flip commit must state
     whether the factor was re-tuned or left alone;
  3. the owner-decision trigger in 9.1 fires on Ohtani's row by name.

---

## 8. SERVE flags, MODEL_VERSION, and why nothing here is display-only

### 8.1 Nothing here is display-only, and that is not a choice

The board, the surplus, the trade-board join and every downstream consumer read
`war`; `05a25ce1` closed the gap between the series the reader saw and the series the
price used. A display-only lever would reopen exactly that divergence (37.9 percent
league-wide, median row ratio 0.563). **So every arm in this gate moves the expected
value that surplus prices**, each one behind a flag, each one with a named dollar
band (section 9). `warPTH` stays a derived display series and is rebuilt from the same
refit quantiles (4.1, item 4); it is never corrected separately.

### 8.2 The flags, default off, following the local idiom

The projections and FA lanes use a module constant plus an `EEPHUS_*` override read
at **call** time, so the OFF path is byte-identical (`fa_projection.DEF_FEATURE_DEFAULT`
with `EEPHUS_FA_DEF`; `fa_market.FA_PRICING_USE_DEF`; `proj_ml.EEPHUS_STAR_MEAN_HEAD`).
Two flags, both defaulting off:

```
# Whether the JOINT smoothness-refit bundle is SERVED. Set from the ARM A verdict in
# docs/PROJ_PATH_SHAPE_GATE.md, never from the size of the RS2 reduction, and a flip
# is the owner's call even on a PASS.
# False loads model/proj_lgbm/models.joblib (the v1 fifty-head layout) and the
# per-horizon predict loop, reproducing today's payload bit for bit. True loads
# model/proj_lgbm_v2/models.joblib (ten joint heads) and the joint predict path.
# BOTH bundles stay in the tree; the revert is this constant, not a re-fit.
# Flipping it moves /projections/ war, warPTH, warP10, warP90, warTotal,
# warTotalPTH, warHit, warPit; surplus surNpv, surRos, surTotal; the trade board
# rows that price off them; the /fa/ FUTURE-class overlay (warSource =
# mlb_projections); /arbitration/'s projected ladder and totals; the Team Outlook
# top-3 strip; and horizons 6-15 through _extend's h5 anchor. It does NOT move
# warChamp, warY1Champ, the Team Outlook WAR roll-up or lockedPct, the depth pool,
# /fa/ current-class pricing, the prospect rows, or any eFV number.
# With it, in ONE commit: bump MODEL_VERSION, refit and re-stamp both blend
# artifacts, move the pins in test_proj_ml.py, and re-run proj_export.
SERVE_SHAPE_REFIT = False        # env override EEPHUS_PROJ_SHAPE_REFIT, read at call time

# Which bias levers are SERVED. The REACH is an explicit frozenset, not "whatever
# passed", because a flag whose effect can grow by itself is a flag whose measured
# effect is no longer the one that was gated.
_ADMISSIBLE_LEVERS = frozenset({"age_side", "catcher", "star"})
SERVE_BIAS_LEVERS: frozenset[str] = frozenset()   # env override EEPHUS_PROJ_BIAS_LEVERS
```

A member outside `_ADMISSIBLE_LEVERS` raises rather than being ignored. The empty
frozenset reproduces the prior payload bit for bit.

**A flip is the owner's call even on a PASS, and never a function of effect size.**

### 8.3 MODEL_VERSION

`proj_ml.MODEL_VERSION` (currently `"proj_lgbm_v1"`, proj_ml.py:69) is stamped onto
every served path dict (`"model": proj_ml.MODEL_VERSION`, fa_market.py:513), carried
in the bundle meta and folded into the point-in-time bundle cache key. The house rule
is that a PRICER change bumps it, "because a ledger that pools two pricers under one
version measures a mixture nobody priced". Both arms are pricer changes, so:

| serving state | MODEL_VERSION |
|---|---|
| today | `proj_lgbm_v1` |
| ARM A shipped | `proj_lgbm_v2` |
| levers on top, in fixed order | `proj_lgbm_v2_age`, `proj_lgbm_v2_age_c`, `proj_lgbm_v2_age_c_star` |
| a lever shipped with ARM A abandoned | `proj_lgbm_v1_age`, and so on |

The string is **derived deterministically** from `SERVE_SHAPE_REFIT` and the sorted
`SERVE_BIAS_LEVERS`, so it cannot drift out of sync with what is serving.

**The bump on ARM A is also a leak control**, not bookkeeping: it re-keys every
`proj_ml_pit_*` file, so a candidate bundle can never be loaded where a champion
bundle was expected by `proj_eval.py:219` or `tools/war_cohort_diagnostic.py:236`
(4.7, leak 3). `_SCHEMA_TAG` changes on its own when the feature list gains horizon
and age-at-target, which re-materialises 6 frame caches and the 29 point-in-time
bundles now on disk. That is the intended behaviour.

---

## 9. The served numbers that move, with the bands, and the ones that must not

### 9.1 What moves

Named in advance, so that nothing moves without having been named and measured.
Design-day baselines from `data/mlb_projections.json` (generated 2026-09-18,
`first_season` 2027, horizon 5, 1,383 vets, 183 prospects, `dpw_usd` 17,971,003):

| quantity | served today | band before a SEPARATE owner decision is required |
|---|---|---|
| vets, sum of `war` over 5 years | 2,925.6 | plus or minus 5%, i.e. **2,779.3 to 3,071.9** |
| vets, sum of year-1 `war` | 852.0 | plus or minus 5% |
| vets, median year-1 `war` | 0.25 | plus or minus 0.05 WAR absolute |
| rows carrying `surNpv` | 895 | plus or minus 10 rows |
| sum of `surNpv` | $15,205,338,537 | plus or minus 7.5%, i.e. **$14.065B to $16.346B** |
| any single row's `warTotal` | - | plus or minus 20% or 2.0 WAR, whichever is larger |
| rows whose `warTotal` moves by more than 3.0 WAR | - | each listed BY NAME in the flip commit; **more than 50 such rows is a separate owner decision** |
| Ohtani `warTotal` | 32.1 | **a move of more than 4.0 WAR is a separate owner decision** (n = 1, so this is a trigger and not a statistical band) |
| Ohtani `surNpv` / `surTotal` | $401,046,245 / $409,804,789 | reported pre and post; **a `surNpv` move of more than $75M is a separate owner decision** |
| `/arbitration/` total projected ladder dollars | recount at flip | plus or minus 7.5% |
| `/arbitration/` any single player's `tot` | - | plus or minus 20% or $2.0M, whichever is larger |
| Team Outlook top-3 strip, teams whose membership changes | - | **more than 5 teams is a separate owner decision** |
| Spearman(pre, post) over `surTotal` | - | RECORDED, not gated. Below 0.95 is a separate owner decision |

**`/arbitration/` is in this table, not in 9.2.** `arb_export._projected_war`
(arb_export.py:82-99) reads `war` straight out of `data/mlb_projections.json` and
`arb_export.py:175` writes it onto the row the arb model prices, so the published
per-step predictions, the ladder `l` and the total `tot` all move with either arm.
An earlier draft asserted the opposite. The arbitration lane's own registry row
(`arb_award_v1`) rests on a gate scored with a different WAR input and must be
re-checked; that is open question 18.13, not a clause here.

Also moving, and each one asserted in the flip commit rather than assumed:
`/projections/` `warPTH`, `warP10`, `warP90`, `warTotalPTH`, `warHit`, `warPit`;
surplus `surRos`; the **FA future-class overlay**, which reaches the FA board through
`_apply_proj_override` with `warSource = "mlb_projections"` even though FA pricing
pins the champion (fa_export.py:703-712); the **Team Outlook top-3 strip**, which
reads `(m.get("war") or [None])[0]` at proj_export.py:1876; horizons 6-15 in the
10-year paths, because `_extend` scales the champion series by the h5 ratio and the
h5 anchor moves; and every consumer of `data/mlb_projections.json`: `arb_export`,
`bayes_trade_value`, `fa_fit`, `mlb_player_export`, `prospect_path`,
`swing_plus_ingest`, `value_framework`, `leaderboard_vintages`, `build_site`.

A band is a trigger for an owner decision, not a criterion. Landing inside every
band is not evidence that an arm worked, and the artifact says so.

### 9.2 What must NOT move, asserted rather than believed

Each is an assertion in the commit that moves a flag, checked pre and post:

- `warChamp` and `warY1Champ`, and therefore the **Team Outlook WAR roll-up**,
  `lockedPct` and `byYear[].war`, which sum `warChamp` (proj_export.py:1843-1856) and
  are pinned by `test_proj_export.test_team_outlook_uses_champion_mean_not_display`.
  Insulated by construction because neither arm re-estimates the champion curves.
  **The Team Outlook top-3 strip is NOT insulated and is in 9.1.**
- The Team Outlook **depth pool** (`proj_export.py:1670`, `use_ml=False`).
- **The prospect rows in their entirety.** `_prospect_rows` prices through
  `vf.prospect_prime_path(price_fv, ...)` and never calls `proj_ml`, so the 183
  prospect rows and their 683.1 five-year WAR sum do not move under either arm. An
  earlier draft gave them a band, which was a band on a number no arm can touch.
- **`/fa/` current-class pricing**: guarantee, AAV, verdict terciles and market
  features, all pinned to the champion at `fa_export.py:703-712` because the ML-path
  version failed its Gate 2.
- `proj_eval`'s champion **baseline**, pinned by
  `test_proj_ml.test_champion_pinned_in_eval_baseline`.
- `/arbitration/`'s `ou_war` column, which is computed from the panel's REALISED
  `war` (arb_export.py:289), not from a projection.
- Every eFV number, `Sur+`, `OrgSur+`, farm surplus and Grad-Contract Surplus, which
  price through `value_framework` and do not enter this path.
- Every route, hash and deep-link key. No new one is introduced by either arm.

**One standing exception that voids these baselines.** If the two-sided label defect
(18.8) is fixed before either flip, the corpus and therefore the champion curves
change, every number in 9.1 and 9.2 is restated, and this gate's design-day baselines
are void.

---

## 10. Cross-arm rules, decided in advance for every combination

| ARM A | ARM B | what happens |
|---|---|---|
| ships | at least one lever ships | Two flags flip, in **two separate commits** with two separate `MODEL_VERSION` strings, ARM A first. They ship as two evidence trails and **neither may cite the other's gate**. CONFIRM (4.6b), if it was available, is spent by ARM A and ARM B reports it as ALREADY READ |
| ships | all three abandoned | ARM A ships alone. The registry note records, in these words, which levers the refit ABSORBED and which were NULL, with the pre and post cells. This is the expected outcome for B-AGE if the refit works, because age-at-target becomes a feature |
| abandoned | levers still resolvable at B0-GATE | **B-AGE and B-C may still run** on `proj_lgbm_v1`, because a post-hoc slice correction does not depend on the estimator shape. **B-STAR does not run** (5.4): without the refit its only admissible form is one of the three banned mean-head arms |
| abandoned | all abandoned | Nothing flips. The shipped engine keeps serving with the wobble, the wobble is published in the served `notes` and in the registry note with its recount, and the lane closes. That is a complete deliverable: the level half already shipped in `05a25ce1`, and what remains is a disclosed defect with a measured size rather than an unmeasured one |

**A failure on either arm never reopens `05a25ce1`.** The display revert is a
separate, already-taken decision and no clause here adjudicates it.

---

## 11. Pre-commitments: the exact sentence each failure publishes

An effect below its floor is reported as a **NULL**, in that word. Not a small win,
not a directional signal, not a fringe gain.

- **A-F1, A-F1b or A-F2 fires:** *"The joint refit with an age-smoothness penalty is
  NOT non-inferior to the shipped `proj_lgbm_v1` composition. It buys a smoother path
  at an accuracy cost larger than the margin registered before the run, and it does
  not ship. The served paths remain non-monotone in age and that defect is published
  with its size rather than repaired."*
- **A-F1c fires:** *"The GATE frame did not fail this arm, and the read frame did.
  A read frame cannot pass an arm and it can fail one, and it failed this one. The
  refit does not ship."*
- **A-F3 fires:** *"The measured difference is the change of objective plus the
  penalty, and nothing in this battery separates them. The result is a NULL and the
  quantity measured is a re-implementation of the estimator, not a smoothness
  effect."*
- **A-F6 fires (NO_EFFECT):** *"The penalty did not smooth the served paths by the
  minimum registered before the run. The recount at the chosen lambda leaves the
  board too close to the shipped engine for this to be the repair the owner reported.
  This is a failed implementation, not a finding about smoothness, and the arm is
  abandoned rather than re-tuned."*
- **A-F7 fires:** *"The refit reproduced the champion. Its roughness fell to the
  fitted aging curve's and its dependence on the champion stack rose by more than ten
  points, so what it learned is a path this repo already serves for free at
  `use_ml=False`. Reported as a NULL."*
- **A-F8 fires:** *"This battery cannot resolve a degradation as small as the margin
  it was allowed to spend. The verdict is UNDERPOWERED_NO_MARGIN. It is not a pass,
  and no number from this run may be cited as evidence that accuracy was preserved."*
- **Any lever fails B1:** *"The [age-by-side slope / catcher correction / star-slice
  recalibration] is a NULL on the serving engine under a Holm family of three. The
  cell `proj_calibration_map` published on the champion decay path does not reproduce
  as a fixable bias on the engine that actually serves."*
- **Any lever fails B2:** *"The lever's permuted twin buys at least half of the same
  bias reduction at the same accuracy cost. What the lever measured is a level move,
  not the slice it names. Reported as a NULL."*
- **A lever is absorbed (B-F1):** *"The smoothness refit absorbed this bias. The cell
  is no longer resolvable on the serving engine on the gate frame. The lever is
  abandoned, not shipped at reduced size and not rescued by widening the frame, and
  the family size k = 3 is unchanged so the surviving levers get no easier bar from
  this abandonment."*
- **B-STAR blocked:** *"The mean-head lever is exhausted; three arms
  (`mean_head_rejected`, `star_mean_head`, `star_slice_mean_head`) have already
  failed, and without the heads refit no admissible form of this lever remains. Not
  run."*
- **Unconditionally, in every artifact this gate writes:** *"Every criterion in this
  battery is scored on `war_provider = ewar_v2`. The champion-versus-challenger
  numbers in `data/proj_horizon_eval.json` (2026-08-19) and every cell of
  `data/proj_calibration_eval.json` (2026-07-25) predate the 2026-09-03/04 eWAR epoch
  and are priors, not comparators. Label seasons 2015 through 2025 were already
  scored on the shipped challenger by `challenger_blocks.gate1_targets` and carry no
  confirming verdict here."*
- **Unconditionally, beside any roughness number:** *"An absent season is scored as
  0.0 WAR, so the expected path of a population whose survival probability decays is
  genuinely not smooth in age. Part of the roughness removed here is attrition
  signal, and the accuracy column is what prices that. RS2 falls by construction
  under a second-difference penalty and no verdict here turns on it in the passing
  direction."*
- **Unconditionally, beside any two-way number:** *"The served two-way population is
  one player. Each side's model estimates the player's TOTAL WAR given that side's
  line, so the two sides are two estimates of one quantity, and no claim about
  two-way accuracy is supported by this battery in either direction. The served
  two-way `war` sum carries no workload discount and no clause here adjudicates
  that."*
- **Unconditionally, beside the verdict:** *"The verdict-bearing frame is label
  seasons 2012-2014, and the served population is 2027. Transport across that gap is
  disclosed, not demonstrated."*

---

## 12. The atomic commit, and the response to a failure

### 12.1 One commit per flag, listing everything that moves with it

ARM A's flip commit contains, or it does not ship:

`proj_ml.SERVE_SHAPE_REFIT`; `proj_ml.MODEL_VERSION` (derived, 8.3);
`model/proj_lgbm_v2/models.joblib` and its `meta.json` (which must now stamp
`war_provider` and the real per-horizon params, 18.4 and 18.5);
`model/proj_lgbm/models.joblib` **kept**, so the revert is a constant;
`proj_ml.feature_names` / `_SCHEMA_TAG`; `proj_ml.predict_path` (the joint path, and
the width-only schema guard upgraded to compare NAMES, 4.7 leak 8);
`proj_ml.save` / `load` / `train_cached`; `tools/train_proj_models.challenger_fn`
and `eval_bases`; `proj_eval.run_rowmatch`; `fa_market.contract_war_path`
(`_extend`, the p10/p90/pth reads); refit and re-stamped `data/proj_mean_blend.json`
and `data/proj_star_blend.json`; `data/proj_shape_gate.json`;
`data/mlb_projections.json` and every downstream artifact re-run;
`test_proj_ml.py` (the fitted fixture, the monotone test, the schema test and both
blend pin tests); `test_proj_rowmatch.py`; `test_proj_export.py`;
`test_team_outlook_calibration.py`; `test_proj_shape_gate.py`; the registry row
`fa_war_paths_decay`; and the **verdict demotion**: `fa_war_paths_decay` moves
`validated` to `provisional` at the moment of the swap and stays there until the
next completed label year re-confirms it.

ARM B's flip commit contains: `proj_ml.SERVE_BIAS_LEVERS`; the derived
`MODEL_VERSION`; the fitted lever constants and their artifact; the re-run exports;
`test_proj_shape_gate.py`; and the registry row `proj_calibration_map`, whose
verdict moves from `provisional / measurement_only` to a fitted verdict only for the
levers that shipped.

### 12.2 The response to a failure, fixed in advance

| failed clause | pre-registered response |
|---|---|
| A-F1, A-F1b, A-F1c, A-F2 | `SERVE_SHAPE_REFIT` stays `False`. `proj_lgbm_v1` keeps serving. The NULL sentence is published and the recount is published beside it |
| A-F3 | stays `False`, and the artifact records that the battery measured an estimator swap, not a penalty |
| A-F4, A-F5 | stays `False`. Explicitly NOT rescued by re-introducing per-horizon capacity, by exempting the star slice from the penalty, or by touching any hyperparameter in 4.1a |
| A-F6 (NO_EFFECT), A-F7 | stays `False`, arm abandoned, no lambda is re-chosen and the grid is not extended |
| A-F8, A-F9 | stays `False`, verdict UNDERPOWERED_NO_MARGIN or NULL_NO_ADMISSIBLE_LAMBDA, re-scorable only on a later label year as a new registration |
| A-F10 | the run is VOID under the one-void cap in 4.11a, recorded in 19 before the re-run, re-run from a clean `.cache`. A second void is VOID_CLOSED |
| any B failure | that lever's name never enters `SERVE_BIAS_LEVERS`. The others are unaffected and k stays 3 |
| B-F6 without its sentence | the catcher lever does not ship, even though it passed |
| a band in 9.1 is crossed | the flip does not happen until the owner has decided, whatever the gate verdict says |
| a "must not move" number in 9.2 moves | the flip is reverted to `False` immediately: that is an implementation defect, not a measurement |

**If ARM A ships and a defect is later found, the revert is one constant.** Both
bundles are in the tree and `False` reproduces today's payload bit for bit. A gate
whose failure carries no mechanical consequence is a note; this one carries a
constant.
---

## 13. The clock. One look per arm, on a fixed date

**Looking early disqualifies the arm for this battery.** A look after its date
requires an amendment filed before the look, saying what moved on disk since this
document was committed (the 5c amendment form).

| date | what | frame it may touch | may it be read before |
|---|---|---|---|
| **2026-09-25** | `data/proj_shape_blast.json` (GATE 0.1, no fit required) | the SERVED artifact only | this is the first artifact; nothing may be fitted before it exists |
| **2026-10-02** | `data/proj_shape_mde.json` (power, section 3) | **DEV only**, plus simulation. A GATE, CONFIRM or Tier-2 row in this artifact is an automatic VOID that consumes the look (3.1) | no criterion may be read before it exists |
| **2026-10-09** | the S2 feasibility pre-flight (4.4a) and **B0-COMPARE** (5.1). Both score the INCUMBENT and burn nothing | DEV, GATE and Tier-2, on the INCUMBENT only | the pre-flight must exist before 4.4's lambda rule can be applied; B0-COMPARE before any lever is fitted |
| **2026-10-23** | **ARM A LOOK. Once.** The GATE frame is opened; CONFIRM is opened here if 4.6b's condition holds and is then spent; the Tier-2 full-depth transport check (4.6c) runs in the same session and under 4.6a | GATE, CONFIRM, Tier-2 | not before |
| **2026-11-06** | **B0-GATE** re-run on whichever engine the ARM A verdict leaves serving (5.1). Scores the incumbent, is the PRE leg of 5.5b | GATE, on the serving engine | no lever may be fitted before it exists |
| **2026-11-13** | **ARM B LOOK. Once**, and only after ARM A's verdict is in `data/proj_shape_gate.json` and B0-GATE exists | GATE (adjudication); DEV (fit) | not before |
| **2027-02-15** | earliest admissible re-read of either arm, as a NEW registration, once 2026 labels are complete (`season_fraction` reads 0.947 today) | - | the new registration must disclose that this battery was read |

The dev frontier (4.4) may be computed at any time after 2026-10-02, because it is
fitted and read on the DEV frame only and carries no verdict. **Reading a GATE,
CONFIRM or Tier-2 number while computing it is an early look and disqualifies the
arm.**

---

## 14. Pools, the artifact, and the test that stops a criterion being edited

- **Pools are counted at scoring time and published with their clause.**
  `data/mlb_projections.json` regenerates nightly and the training frame regenerates
  with the corpus. The 2026-09-18 numbers in this document are design-day
  descriptives, published so the recount can be checked against them, never quoted
  as the result. The 257-to-279 drift in RAF (4.5) is the demonstration.
- **`data/proj_shape_gate.json` carries each criterion VERBATIM beside its result**,
  with the clause's n, its verdict, the comparator it was scored against, the frame
  and the LABEL SEASONS that frame covered, the seed, B, `refits_per_draw`,
  `train_resampled`, `vif_registered`, `vif_measured`, `vif_applied`, and the wall
  time of the run.
- **`test_proj_shape_gate.py` pins the CRITERIA as well as the verdicts**, so a
  criterion cannot be edited after a result has been seen. It also pins:
  - that the DEV, GATE and CONFIRM label-season sets are pairwise DISJOINT and match
    4.6 exactly, and that every published cell's label season lies in its own frame's
    set;
  - that `data/proj_shape_mde.json`'s recorded bases and label seasons are a subset
    of DEV (3.1);
  - that no Tier-2 or CONFIRM number appears in any field the artifact marks as
    supporting a PASS (4.6a);
  - `artifact["holm"]["arm_b"]["k"] == 3`, all three lever keys present in the fixed
    order, every floor reported under `mde95_holm_k3`, and that a lever with
    `delta <= 0` reads NULL whatever its `abs_t` (5.5a, 5.5b);
  - the bootstrap provenance fields above, so a downgrade from the registered
    protocol is visible;
  - that `SERVE_SHAPE_REFIT` and `SERVE_BIAS_LEVERS` default off, that
    `MODEL_VERSION` is derived from them, and that the flags' OFF payload matches the
    pre-change payload;
  - that no two-sided row appears in any scored cell of either arm or of S (L1);
  - that both arms' per-base blend lambda vectors are present (4.7, leak 10).
- **Every clause states its own direction.** Nothing is assumed to be
  higher-is-better.
- **The verdict vocabulary is closed**, and it separates decisions from absences:
  `PASS`, `NULL`, `NULL_HOLM`, `NULL_NO_ADMISSIBLE_LAMBDA`, `NO_EFFECT`, `ABSORBED`,
  `DEAD_ON_ARRIVAL`, `UNDERPOWERED`, `UNDERPOWERED_NO_MARGIN`,
  `NOT_ADJUDICATED_NO_HOLM`, `NOT_ADJUDICATED_NO_FLOOR`, `NOT_AVAILABLE`,
  `PASS_BY_CONSTRUCTION`, `VOID`, `VOID_CLOSED`. A gate that cannot fail is not a
  gate, and a gate that spells an absence of evidence the way it spells cleared
  evidence is worse than no gate.

---

## 15. Banned, and enforced mechanically

- **Every numeric threshold in this document is FROZEN.** `M = 0.0065`, S1b's
  +0.0130, A-SHAPE's 0.2617 and 0.1192, S3's 0.0200, S4's 0.0200 and [0.75, 0.87],
  S5's 0.0050, S6's 0.0500, A0's 0.0050 and 0.0100, B3's +0.0100, B4's 0.0500, B2's
  0.5 ratio and 0.01 WAR floor, 5.4a's 0.75 share, CONFIRM's n = 1,000, the VIF's
  1.8 lower bound, Tripwire 2's 10 points, k = 3, the lambda grid, and every band in
  section 9. **None may be re-derived, for any reason, including a later re-measure
  of the engine-versus-champion edge on `ewar_v2`.** Re-measuring that edge scores no
  candidate and is legal at any time; it may be published, and it may not move M.
  **No amendment may loosen a threshold in the permissive direction. An amendment
  that does is a NEW registration that discloses this one.**
- **A pooled (not side-keyed) age recentering**, under any name, including "a single
  shared slope across sides". The two sides run in opposite directions and a pooled
  correction cancels them and fixes neither. The lever's fit function raises if it is
  handed rows of both sides without a side key.
- **The three mean-head arms** `mean_head_rejected`, `star_mean_head`,
  `star_slice_mean_head`, under any name. The lab raises on a config that reproduces
  any of them.
- **Widening a frame, or adding a base or a label season to one, after any look**,
  including to restore a cell's resolvability (5.1).
- **Running a lever's parsimony twin on a failed primary** (5.4a).
- **Calling `holm_family` with fewer than three cells** (5.5a).
- **Scoring a two-sided row** in any cell of either arm or of the comparator (L1).
  The scorer raises.
- **Dropping short-horizon groups from the penalised fit** instead of applying 4.1
  item 3 (L8).
- **Injecting the shipped blend lambdas into a historical bundle** (4.7, leak 10).
- **Reading the frame disk cache in a candidate lab** (4.7, leak 2): candidate labs
  pass `use_cache=False` and the lab raises if the flag is absent.
- **Grading the live bundle at a historical base** (4.7, leak 1). The scorer compares
  `meta["max_label_season"]` against `B - 1` and raises.
- **Changing any hyperparameter in 4.1a**, including re-introducing
  `LGBM_PARAMS_LONG_H` under another name.
- **Citing a Tier-2 or CONFIRM number in support of a PASS** (4.6a).
- **Citing a cross-base comparison as a win** (L7), or citing the 0.557 / 0.627
  headline, which the registry row itself forbids.
- **Citing a pre-epoch number as a comparator** (L3).
- **Extending the lambda grid, re-choosing lambda, or re-sizing k after any look.**
- **A post-hoc monotone projection or clamp on any served series.**
- **A second VOID on the same arm** (4.11a); the second one is VOID_CLOSED.

---

## 16. Underpowered is a verdict, and it is not a pass

Four pre-registered underpowered outcomes, each with its consequence fixed:

1. **ARM A, `MDE95(delta pooled MAE) >= 0.0065`** after the VIF: `UNDERPOWERED_NO_MARGIN`.
   The arm does not ship, no number from the run is cited as evidence of preserved
   accuracy, and the re-read is 2027-02-15.
2. **Any lever whose detection check cannot see a planted effect the size of the
   nearer-zero end of its published prior CI**: `UNDERPOWERED`. The lever does not
   ship and its Holm slot is still counted in k = 3 under 5.5a.
3. **CONFIRM** (4.6b): if the row-matched scored n falls below **1,000** after
   matching, CONFIRM reads `UNDERPOWERED` and the ARM A verdict rests on the GATE
   frame alone, with the shortfall published. It is not read as a confirmation and it
   is not read as a contradiction.
4. **CONFIRM unavailable** (4.6b): if 2026 labels are not complete at the look,
   CONFIRM reads `NOT_AVAILABLE`. Also not a pass and not a failure.

---

## 17. The registered successor questions

**No clause here scores whether the served five-year path is a good estimate of a
player's realised five-year value in dollars.** This gate scores WAR-space accuracy
row by row, and surplus is a nonlinear functional of the whole path against a salary
path. The successor gate is a realised control-window surplus label set (realised
WAR times the realised winter dollars-per-win, minus money actually paid, over closed
windows), which ARBITRATION_GATE 11g also names as its own successor. It is named
here and in the gate artifact so the hole is not later rediscovered as a finding.

Three smaller successors, all disclosed rather than gated:

1. **Horizons 6 to 15 are not heads at all.** `_extend` scales the champion series by
   the h5 ratio, so this gate's penalty reaches every out-year of the ten-year paths
   through a single anchor it never scored. That anchor's behaviour under a smoothed
   h5 is unmeasured.
2. **Transport from label seasons 2012-2014 to a 2027 serve** (4.6). The Tier-2
   full-depth check (4.6c) can veto on it and cannot resolve it.
3. **The two-way workload discount** (section 7, 18.7). The owner's Ohtani report has
   a half this battery does not touch.

---

## 18. Consumers and files this lane does not own

Every item is a change some other lane owns, with the file and the exact text. This
lane wrote one document and touched nothing else.

1. **`data/model_registry.json`, row `fa_war_paths_decay`.** Append: *"2026-09-18:
   the bundle hash on disk is 4baf67400e5af498 (max_label_season 2025), after the
   2026-09-04 eWAR v2 retrain at 44c089c2. The two hashes narrated above
   (442428a6498b1426, 6a691e03ff096a35) are superseded and are kept only as the
   ship-day and def-prior-refit receipts. Every gate number in this note predates the
   2026-09-03/04 eWAR epoch and was measured on bWAR labels."*
2. **`data/model_registry.json`, row `proj_calibration_map`.** Append: *"FRAME: these
   cells score the CHAMPION decay path (tools/proj_calibration_lab.py calls
   fm._decay_path at line 80), not the served proj_lgbm_v1 heads plus the mean and
   star blends. Any lever fitted to a cell here must be re-measured on the served
   engine before it ships. Measured 2026-07-25 on bWAR; the pitcher age cells predate
   the 2026-09-03 epoch that repriced pitcher-season WAR. The 65 cells are a screen:
   the three levers registered in docs/PROJ_PATH_SHAPE_GATE.md were selected from
   them and no multiplicity correction covers that selection, so the published cell
   values are selected maxima."*
3. **`data/model_registry.json`, row `fa_war_paths_decay` or a new note.** Append:
   *"READ LEDGER: challenger_blocks.gate1_targets scored proj_lgbm_v1 on bases
   2015-2025 and published per-horizon mae, bias, mae_star, bias_star, coverage and
   pinball. Label seasons 2015-2025 are therefore READ on the challenger and carry no
   confirming verdict in any later gate."*
4. **`proj_ml.py` (engine lane).** `train()`'s meta records `dict(LGBM_PARAMS)` while
   `h >= 4` is fitted with `LGBM_PARAMS_LONG_H`, so the shipped `meta.json`
   **misreports** the h4 and h5 hyperparameters. Record `_params_for(h)` per horizon.
5. **`proj_ml.py` (engine lane).** `meta` carries no `war_provider`, so a bundle on
   disk cannot say which WAR basis it was trained on. Stamp
   `corpus.get("war_provider")` into meta at train time.
6. **`proj_ml.py` (engine lane).** `train_hash` digests `str(X.shape)` plus
   `X.sum(axis=0)` only, never `y`. Two frames with identical shape and identical
   column totals hash the same, and a pure label-basis change does not move it. State
   the weakness in the docstring or digest `y` as well.
7. **`proj_export.py` (export lane).** `TWO_WAY_PIT_PTH_FACTOR = 0.48` is applied only
   to the `warPTH` sum (lines 740-746). The board and every priced number read `war`,
   which sums both sides with **no** workload discount. Either the discount moves to
   the expected-value sum or the payload discloses, in the served `notes`, that it
   does not apply there.
8. **`fa_projection.py` / `proj_ml.py` / `proj_eval.py` (label lane).** The corpus
   carries the player's TOTAL WAR on both his hit row and his pit row (671
   player-seasons, identical in all 671, 327 above absolute WAR 0.5), and
   `build_training_frame` (proj_ml.py:336) and `_assemble` then sum across sides, so
   those rows train and score at 2x. A fix moves BOTH arms and invalidates every
   published receipt, so it needs its own registration. If it lands before either
   flip here, every design-day baseline in section 9 is void and this gate is
   restated.
9. **`data/proj_mean_blend.json`, `data/proj_star_blend.json` (blend lane).** A heads
   refit invalidates both lambda sets by construction, and
   `test_mean_blend_pinned_to_artifact` / `test_star_blend_pinned_to_artifact` fail
   until they are refit and re-stamped by `tools/apply_mean_blend.py` and
   `tools/fit_star_blend.py --apply`.
10. **`proj_eval.py` / `tools/train_proj_models.py` (harness lane).** `train()` never
    writes `mean_blend` or `star_blend` into bundle meta, so every point-in-time
    bundle predicts an UNBLENDED q50 while the serve is blended, even though
    `run_rowmatch` does pass the full quantile set. Either the harness injects
    point-in-time-fitted lambdas (4.2) or every block in `data/proj_horizon_eval.json`
    is labelled *"unblended q50, not the served composition"*.
11. **`docs/aging-curves.md` section 2** says the LightGBM heads produce "calibrated
    P10-P90 uncertainty bands around the projection, not the central path". That has
    been false since the 2026-06-11 ship. Add: *"Since 2026-06-11 the q50 head also
    serves the central path on /projections/; the fitted curves remain the h6+ shape,
    the fallback, and the engine /fa/ pricing serves."*
12. **`proj_ml.predict_path` (engine lane).** The schema guard (proj_ml.py:468)
    compares feature **width**, not names, so two schemas of equal width pass and
    mis-predict positionally. `_SCHEMA_TAG` catches it at the cache layer and nothing
    catches it at the serve layer.
13. **`data/model_registry.json`, row `arb_award_v1` (arbitration lane).**
    `arb_export._projected_war` reads `war` from `data/mlb_projections.json` and
    `arb_export.py:175` writes it onto the priced row, so the arbitration ladder is a
    downstream consumer of this engine. Append: *"The served ladder's WAR input is
    data/mlb_projections.json `war`. A flip of proj_ml.SERVE_SHAPE_REFIT or
    SERVE_BIAS_LEVERS changes that input and this row's gate numbers were not
    measured under it."*

---

## 19. The append-only record

Every run this gate authorises appends a row here with its date, its arm, its
verdict, its artifact hash and its wall time, including **VOID** runs. A run is never
deleted and a verdict is never edited; a correction is a new row. A VOID is appended
BEFORE its re-run starts, naming the control that was violated, and the one-void cap
in 4.11a counts rows here.

An amendment to this document is admissible **only before the arm's first look**, on
an established fact about the data, is filed with what moved on disk since this
document was committed, and **may not loosen any threshold in section 15**. That is
the 5c amendment form and it is the only way this document changes.

| date | arm | verdict | artifact | notes |
|---|---|---|---|---|
| 2026-09-18 | - | registered | - | pre-registration committed; no candidate scored |
| 2026-09-18 | - | amended | - | AMENDMENT A-1 (section 21): the two-sided label defect is repaired; the design-day descriptives it moves are named and restated. No candidate scored, no look spent, no threshold moved |
| 2026-09-18 | - | restated | - | REPAIR + RESTATEMENT (section 22): the label repair landed and every descriptive A-1 named as stale is restated from the repaired corpus. No candidate scored, no arm fitted, no look spent, no threshold moved |
| 2026-09-30 | - | noted | - | CONTRACT TAIL (owner answer 2026-09-25, census M05-01 step 2): proj_export.PRICE_CONTRACT_TAIL prices a guaranteed contract past 2031 through its last season, those seasons on `warChamp` extended (the champion mean, insulated from both arms by 9.2), so neither SERVE flag moves them. It moves the served baselines 9.1 is read against: sum of `surNpv` $13,488.3M to $13,385.9M on the same 904 rows, 39 rows, Ohtani `surNpv` $211.7M to $155.3M. A flip's pre and post are both read on the tail-priced payload. No candidate scored, no look spent, no threshold moved |

---

## 20. What this revision changed, and what it refused to change

Two adversarial reviews were run against the first draft on 2026-09-18, one hunting
for ways to game the gate and one checking every number and code claim against the
repo. Neither scored a candidate. This section records the disposition of every
structural finding, so that a later reader can see which objections were answered and
which were declined and why.

### 20.1 Accepted, and where the fix landed

| finding | fix |
|---|---|
| DEV / GATE / FRESH were not disjoint in label season, while 4.6 claimed they were | frames re-cut by label season for real (4.6), the false citation of `test_training_frame_no_lookahead_property` deleted, and the disjointness pinned by the test (14) |
| `challenger_blocks.gate1_targets` had already scored the shipped comparator on bases 2015-2025, covering two of three old GATE bases and both old FRESH cells, on exactly S1-S6's statistics | the complete READ LEDGER (G-0.1), the burn standard applied evenly, the verdict frame moved to label seasons 2012-2014, and the read frame demoted to VETO-ONLY (4.6a) |
| the power artifact had no assigned frame and could legally be the early look | MDE lab pinned to DEV plus simulation, transport formula registered, a GATE/CONFIRM/Tier-2 row in it made an automatic VOID that consumes the look (3.1) |
| the registered bootstrap was not executable and the cheap substitute narrows sd, the permissive direction | the runnable protocol registered with a registered VIF of at least 1.8, a B=200 DEV-only calibration bootstrap to measure the real ratio, and provenance fields pinned in the test (3.2) |
| no minimum shape effect; Tripwire 1 was a conjunction a near-no-op walked past | A-SHAPE registered as a NECESSARY-never-sufficient condition with both legs failing independently (4.5) |
| M could be re-derived upward before the look | every threshold frozen in section 15, with the explicit statement that a re-measure of the engine-versus-champion edge may be published and may not move M |
| `holm_family` derives k from `len(cells)`, so k could collapse to 1 | 5.5a: always three cells, unfitted levers enter as delta 0 with their floor as sd, and the test pins k == 3 and the key names |
| `holm_family` is one-sided on an absolute value, so a wrong-signed lever could clear | 5.5b: the signed statistic named, sign checked as a precondition, pinned by the test |
| each lever had two adjudications in one slot, and the twin could rescue a failed primary | 5.4a: one registered primary per lever; the twin may replace a pass on parsimony and may never rescue a failure; the share formula and its boundary registered |
| the three cells were selected from a 65-cell screen and the detection check planted the selected maximum | 1.2 states the selection and that nothing corrects it; 3.3 plants the nearer-zero CI bound instead |
| section 15 banned a pooled age recentering while 5.4 offered exactly that as B-AGE's twin | B-AGE now has NO twin (5.4), and the ban names the shared-slope form explicitly (15) |
| VOID was an uncapped self-declared do-over | 4.11a: one void per arm, appended before the re-run, second void is VOID_CLOSED |
| the read frame could only fail the arm on a SIGN contradiction | 4.6a and S1c: a magnitude veto on the bound, not a sign test |
| no per-horizon non-inferiority against S | S1b added, with its +0.0130 derivation registered |
| the joint heads' hyperparameters were unregistered, leaving a second searchable grid | 4.1a registers them exactly and bans changing any of them |
| S excluded the two-sided rows while the serve does not | S is retrained under the identical exclusion so the contrast is clean, and L1 carries the disclosure that the gate measures a contrast and not the served absolute level |
| the candidate's star blend could carry an h2 lambda the incumbent was denied | 4.2: the incumbent's denied horizons carry over to the candidate |
| the S4 coverage bound was absolute, asymmetric and not anchored on the gate frame | S4 re-anchored as a delta against S on the same frame, with a wider absolute guard around it |
| "an over-wide floor is the permissive direction" was inverted for S1 | 3.4 states the direction correctly for every clause and explains why the VIF and the coverage check exist |
| B2's permuted twin had no draw count, no uncertainty and no zero-denominator rule | 5.5c: 200 draws, seeded, median and IQR published, three explicit branches |
| the penalty was undefined for groups with fewer than five horizons | 4.1 item 3 defines it on consecutive available horizons, L8 registers the census, and dropping short groups is banned |
| blend-lambda lookahead was absent from the leak inventory | 4.7 leak 10, with per-base refitting and a void condition |
| leak 3 cited `fa_market:2169`, which is a comment | corrected to `proj_eval.py:219` and `tools/war_cohort_diagnostic.py:236` |
| the `LEAN_QUANTILES` mechanism was wrong | corrected in section 0 and 18.10: `run_rowmatch` passes the full quantile set; the blends are inert because `train()` never writes them into meta |
| `/arbitration/` was listed as insulated and is not | moved to 9.1 with bands, and 18.13 opened for the arbitration lane |
| the prospect rows carried a band and cannot move | moved to 9.2, band deleted |
| the Team Outlook top-3 strip reads `war[0]` and moves | split: roll-up and lockedPct in 9.2, top-3 strip in 9.1 with a band |
| the champion-beating rule was plausibly unsatisfiable for the blended composition at any lambda | 4.4a registers a feasibility pre-flight on the INCUMBENT and both forms of the rule, before any candidate exists |
| ARM B had no frame discipline of its own and section 10 contradicted 2.6 | 5.1 splits B0-COMPARE from B0-GATE, 5.2 fixes the order, and section 10 is consistent with 4.6b |
| `war` RS2 median was 0.3691 | corrected to 0.3668 |
| M was stated as one third of the mean edge but 0.019940/3 = 0.006647 | stated as one third rounded DOWN, with rounding down named as the conservative direction |
| line references were off by a few lines | corrected: `fa_export.py:703-712`, `proj_export.py:1670`, `proj_export.py:740-746`, `proj_ml.py:336`, `proj_ml.py:468` |
| the disk estimate was low | replaced with the measured figure: 29 bundles, 793,446,247 bytes |
| "since 05a25ce1 every priced consumer read war" | corrected: pricing always read `war`; the commit moved the DISPLAY |
| the Ohtani row carried no owner-decision trigger | 9.1 gives his `warTotal` and `surNpv` explicit triggers, and section 7 states in words that a PASS here is not evidence his complaint was addressed |

### 20.2 Declined, with the reason

- **"683.1 is the 7-entry sum."** Recomputed on `data/mlb_projections.json` of
  2026-09-18: 683.1 is the sum over all **183** prospect rows. The reviewer's
  substantive point, that prospects do not move under either arm, is correct and is
  accepted; the arithmetic claim behind it is not, and is not repeated here.
- **"Two-sided rows should be included so the comparator matches the serve."** The
  implied fix would score a known 2x label defect in both arms. The gate keeps the
  exclusion and discloses what the exclusion costs (L1) rather than scoring a defect
  it can name.
- **"The gate should adjudicate the two-way workload discount."** This lane may not
  touch `proj_export.py`, and a clause over a number no arm in this battery moves is
  a clause that cannot fail, which is worse than an open question. It is 18.7, plus
  the three enforcement hooks in section 7 and the owner-decision triggers in 9.1.
- **"Row share of two-sided players is 3.7 percent."** Not reproduced here. The
  verified figure is 671 of 35,825 corpus player-seasons entering as two base rows
  each; the scored-row share is recounted at scoring time and published (L1), rather
  than asserting a number this document cannot check.
- **"Restate the burn standard so it is applied evenly" as an ALTERNATIVE to moving
  the frame.** Both were done, not one. The standard is restated evenly in G-0.1 AND
  the verdict frame moved, because restating alone would have left the verdict on
  label seasons whose incumbent statistics are already published.

---

## 21. AMENDMENT A-1, 2026-09-18: the two-sided label defect is repaired, and the descriptives that move with it

This section is an amendment under the form registered in section 19. It records a
defect in the training and scoring LABELS, filed before any look, and it restates
which of this document's design-day numbers go stale when that defect is repaired.
**It changes no decision rule, no threshold, no frame boundary and no primary
criterion.** Section 21.5 lists what it did not change, item by item, so the absence
of a change is on the record rather than inferred.

### 21.1 Standing: what admits an amendment at this point

`docs/diamond-betting.md` 5c, protocol rule 1, verbatim:

> "Each candidate gets its own gate section in this document before any number is
> computed on it. The section names the estimand, the split, the criteria and the
> thresholds, the way 11a and 11b do. **A candidate measured before its section
> exists is disqualified, whatever it measured.**"

Rule 1 binds a number computed ON A CANDIDATE. It does not reach a fact established
about the DATA, and the precedent in this repo says so in those words: 5c-B's
standing paragraph admits a section under rule 1 because it "was written ... before
any number related the column ... to a game outcome or a price", and the
`out_of_sample_skill` section's disclosure reads "Nothing was run. Every number
quoted below was already on the record."

Section 19 of this document sets the same bar for changing it:

> "An amendment to this document is admissible **only before the arm's first look**,
> on an established fact about the data, is filed with what moved on disk since this
> document was committed, and **may not loosen any threshold in section 15**."

All four conditions hold, and each is checkable:

1. **Before the first look.** The ARM A look is 2026-10-23 and the ARM B look is
   2026-11-13 (section 13). Today is 2026-09-18. Every intermediate artifact date is
   also still ahead: the blast-radius bound 2026-09-25, the power artifact 2026-10-02,
   the S2 pre-flight and B0-COMPARE 2026-10-09, B0-GATE 2026-11-06. **None of the
   three producers exists yet**, so no artifact this gate authorises has been written.
2. **An established fact about the data.** How it was established is in 21.2: three
   source files were READ (`fa_projection.py`, `proj_ml.py`, `proj_eval.py`) and rows
   of the corpus were COUNTED. Nothing was fitted, no arm was run, no candidate was
   compared against the shipped engine, no lambda was chosen, no frame in 4.6 was
   opened for a candidate, and no statistic in S1 through S6, A-SHAPE, B1 through B4
   or the Holm family was computed on anything. That is the identical standard the
   G-0 honesty clause applies to the original registration, applied again.
3. **Filed with what moved on disk.** 21.3.
4. **Loosens no threshold in section 15.** 21.5, and in particular 21.4's treatment
   of A-SHAPE, whose two bars stay at 0.2617 and 0.1192 even though the design-day
   baselines they were derived from are restated. Re-deriving them from a restated
   baseline would be exactly the move section 15 forbids, and it is refused here.

**Why the order is amend, then fix, then re-measure.** Repairing the label moves the
training labels, which moves the frames and therefore moves descriptives this
registration quotes. Amending first records which numbers are stale and what they
will be restated from, **before** any of them has been recomputed; doing it the other
way round would file an amendment against numbers that were already in hand, which is
the shape of the error the honesty clause exists to prevent.

### 21.2 The defect, and how it was measured

**Mechanism.** `fa_projection._war_age_maps` (fa_projection.py:87) returns
`{(mlbam, season): war}` and its own docstring says the value is **"(bat+pit
summed)"**. Line 117 is the accumulation:

```
war[key] = war.get(key, 0.0) + _f(row.WAR)
```

The loop at line 105 runs over `("bat", "pit")` and the key carries no side, so one
map value is the player-season's WHOLE WAR. `build_corpus` then writes that same map
value onto the hitter row (fa_projection.py:292) and onto the pitcher row
(fa_projection.py:332) through the identical `war_map.get(key)` call. A player-season
with rows on both sides therefore carries his TOTAL WAR twice.

Both consumers then sum across sides a second time:

- `proj_ml.build_training_frame`, proj_ml.py:336 - `war_actual[key] = war_actual.get(key, 0.0) + r["war"]`
- `proj_eval._assemble`, proj_eval.py:85 - the same line, and its docstring says so:
  "war_actual sums WAR across sides per (mlbam, season), matching the label the
  harness scores."

Neither of those two lines is wrong given a correct corpus. The defect is upstream,
in a side-blind map written onto side-keyed rows, and the two sums downstream are
what turn it into a factor of two.

**Measured on the corpus, 2026-09-18, with no candidate scored:**

| quantity | measured |
|---|---|
| corpus player-seasons carrying rows on BOTH sides | **671** of 35,825 (1.9 percent) |
| of those, share holding the IDENTICAL value on each row | **100 percent**, all 671 |
| Ohtani 2023, hitter row / pitcher row / value entering the frame | 8.54 / 8.54 / **17.08** |
| Ohtani 2025, value entering the frame against his real WAR | **16.72** against 8.36 |
| Ohtani 2024, a season he did not pitch | **9.04**, correct |
| the five largest doubled labels in the whole corpus | all five are his |
| aggregate phantom WAR across the corpus | **138.6** against a corpus total of **26,408**, = **0.52 percent** |
| concentration | roughly **60 player-seasons a year**, most of them position players who threw a mop-up inning and had their whole season doubled for it |

The last row is the part that is not an Ohtani story. A position player with one
mop-up inning gets a pitcher row, and that row and his hitter row each carry his
entire season's value, so the frame sees his year at twice its size on both sides.

**This is open question 18.8, and this lane closes it.** 18.8 already recorded the
defect, the counts and the consequence: "If it lands before either flip here, every
design-day baseline in section 9 is void and this gate is restated." This amendment
is that restatement, filed before the fix rather than after it.

**The repair, named so the restatement has a source.** `_war_age_maps` becomes
side-keyed, so the hitter row carries the player's hitting WAR and the pitcher row
his pitching WAR. The two downstream sums at proj_ml.py:336 and proj_eval.py:85 are
left alone and become correct by arithmetic: `H + P = T` where they currently produce
`T + T`. **The label the models see is still TOTAL player WAR**, which is why L2 is
unchanged (21.5).

### 21.3 What moved on disk, and what re-derives from the repair

**First-order.** The `war` value on the corpus rows of the 671 two-sided
player-seasons, on both sides.

**Second-order, and it reaches every player, not only the 671.** `fit_war_map`
(fa_projection.py:1659) regresses `r["war"]` per side over corpus rows, and
`fit_aging_curves` is fitted on the same rows. Two-sided rows are in both fits today
carrying a value that belongs partly to the other side, so the repair moves **both
WAR maps and both curve sets**, and therefore moves the champion path
`contract_war_path(use_ml=False)` for **every** player. That in turn moves
`build_features`' `champ_h1..champ_h5` stack columns for every row, and the
`war_l1..war_l3` lags for the two-sided rows.

**Caches, and which ones invalidate themselves.**

| cache | key | self-invalidating | consequence |
|---|---|---|---|
| `.cache/fa_corpus.pkl` | none; read unless `force` (fa_projection.py:207) | **no** | must be force-rebuilt, or the repair is invisible |
| `.cache/fa_fits_*.pkl` | includes `_corpus_sig`, which digests every row's `war` (fa_projection.py:397) | **yes** | re-keys on its own; the comment at fa_projection.py:467 says so |
| `.cache/proj_ml_frame_*.pkl` | `_SCHEMA_TAG`, first_base, max_label_season, `corpus.first`, `corpus.last`, `_war_tag` - **nothing about the rows** (proj_ml.py:322) | **no** | holds doubled labels; must be deleted. This is the same key 4.7 leak 2 already names, and `_war_tag`'s own docstring at proj_ml.py:299 states the weakness |
| `.cache/proj_ml_pit_*.joblib` (29 files, 793,446,247 bytes) | MODEL_VERSION, `_SCHEMA_TAG`, max_label_season, qtag, war_tag - nothing about labels | **no** | all 29 were fitted on doubled labels and must be deleted |
| `model/proj_lgbm/models.joblib` (the live bundle) | n/a | n/a | trained on the doubled frame; `train_hash` digests `X.shape` and `X.sum(axis=0)` and never `y` (18.6), so a pure label change does not move it |

4.7's existing control for candidate labs (`use_cache=False`, leak 2) is unchanged and
still binding. What is new is a fact about disk and not a rule: the PRODUCTION frame
cache and the point-in-time bundle cache currently hold doubled labels and do not
re-key themselves, so a run that reads either of them after the repair is reading the
defect. `G-0.2` records a read of
`.cache/proj_ml_frame_fe323aac_2003_2025_2000_2026_ewar_v2.pkl`; that read stays on
the ledger as it happened, and the file it names may not be reused.

**One consequence of the repair that is disclosed here and adjudicated nowhere.** A
player-season can carry a row on one side only: a pitcher whose plate appearances
fall below the hit-row threshold gets no hitter row at all. Today his batting WAR
still reaches the label through the side-blind map. Under a side-keyed map it does
not, so for those rows the repair REMOVES a small true component instead of removing
a phantom one. It is named here so the restatement measures and publishes it rather
than discovering it later; **no clause in this gate adjudicates it**, and it is
successor question 21.6 item 2.

### 21.4 The registration numbers that go stale, and what each is restated from

Grouped by why. The numbers are reprinted here so the restatement can be checked
against them rather than replacing them silently, which is the same discipline
section 14 sets for the pools.

#### A. The corpus census (L1, section 7, section 0's last row)

| as registered | status under the repair | restated from |
|---|---|---|
| L1: "**671 of 35,825** corpus player-seasons (1.9 percent)" | **UNCHANGED as a count.** Which player-seasons carry rows on both sides is structural and does not depend on the label value | the rebuilt corpus; L1 already requires the recount at scoring time |
| L1: "**identical `war` in all 671**" | **SUPERSEDED, by construction.** After the repair the two sides hold different values except where a player's hitting and pitching WAR happen to coincide. This sentence is the defect's signature, and it is what the repair removes | the rebuilt corpus |
| L1 and section 7: "**327** above the magnitude floor" (absolute WAR at or above 0.5 on BOTH sides) | **STALE and expected to fall sharply.** The floor was applied to doubled values; a mop-up inning that reads as a whole season's WAR today reads as a fraction of a WAR after the repair | the rebuilt corpus, under L1's own rule unchanged |
| section 0, last table row: "those player-seasons train and score at **2x**" | **REPAIRED.** The 2x is what the fix removes | n/a; the row stands as the record of what was found |

#### B. The frame descriptives (L8, 4.1 item 1)

| as registered | why it can move | restated from |
|---|---|---|
| L8: hit **19,965 / 19,038 / 18,092 / 17,187 / 16,341**; pit **24,325 / 22,997 / 21,617 / 20,340 / 19,083** | row inclusion does NOT turn on the label value: proj_ml.py:355-361 appends `war_actual.get(target, 0.0)` unconditionally once the base row exists. It turns on `build_features` returning non-None, which is None exactly when the champion cannot project (proj_ml.py:220-224), and the champion is built from `curves` and `war_map` that the repair moves. Any movement is therefore second-order, through champion feasibility, not first-order through the labels | `build_training_frame(corpus, 2003, 2025)` on a force-rebuilt corpus with the frame disk cache bypassed |
| L8: "**81.8 percent** of hit base rows and **78.4 percent** of pit base rows carry all five horizons" | same | same |
| 4.1 item 1: "**90,623** hit rows plus **108,362** pit rows = **198,985**" | same | same |

**These are republished whether or not they move.** A count that comes back identical
is published as identical; silence is not a restatement.

#### C. The served descriptives (4.5, section 0)

Every cell of 4.5's table, and the section 0 rows that quote it:

| series | pool | RS2 mean | RS2 median | UAF | RAF |
|---|---|---|---|---|---|
| `war` | 278 | 0.4362 | 0.3668 | 177 / 1,112 = 0.1592 | 153 |
| `warPTH` | 447 | 0.5749 | 0.4778 | 328 / 1,788 = 0.1834 | 279 |
| `warChamp` | 311 | 0.0670 | 0.0451 | 0 / 1,244 = 0.0000 | 0 |

plus section 0's "the champion aging path wobbles on **0 of 311** served rows ... the
ML central path wobbles on **153 of 278**", and section 0's "Vets 5y `warPTH`
**4,716.1** against `war` **2,925.6**, **37.9%** high; Ohtani `warTotalPTH` **36.4**
against `warTotal` **32.1**".

**All of them are STALE**, including the `warChamp` row, because the champion curves
are refitted on the repaired corpus (21.3). They are restated from the first
regeneration of `data/mlb_projections.json` after the repair lands, which requires a
force-rebuilt corpus, a cleared frame cache and a retrained live bundle. **This lane
does not run that regeneration**, so the restatement is filed at the regeneration and
governed by section 14's standing rule: pools are counted at scoring time and
published with their clause, and the numbers above are design-day descriptives that
the recount is checked against, never quoted as the result.

> **A-SHAPE's two bars do NOT move with the baselines they were derived from.** RS2
> mean at or below **0.2617** and UAF at or below **0.1192** are frozen by section 15
> and are NOT re-derived from a restated 0.4362 or a restated 0.1592. If the restated
> RS2 mean comes in lower, the frozen absolute bar is a strictly harder relative bar;
> if it comes in higher, the frozen bar is harder still. Both directions are
> non-loosening, which is why freezing is the admissible response and re-deriving is
> not. **Disclosed contingency, recorded and not repaired:** if the restated RS2 mean
> or UAF already sits at or below its frozen bar, A-SHAPE becomes non-binding on that
> leg. That would be recorded in `data/proj_shape_gate.json` in those words. It is not
> fixed by moving the bar, because moving it is a new registration (section 19), and
> nothing in this amendment authorises one.

#### D. The design-day baselines and bands (section 9)

Section 9.2 already pre-registered this exact event, and it fires now:

> "**One standing exception that voids these baselines.** If the two-sided label
> defect (18.8) is fixed before either flip, the corpus and therefore the champion
> curves change, every number in 9.1 and 9.2 is restated, and this gate's design-day
> baselines are void."

**Void and restated**, from a regenerated `data/mlb_projections.json` and its
downstream exports: `1,383` vets, `183` prospects, `dpw_usd 17,971,003`; vets 5-year
`war` sum **2,925.6** and the derived band **2,779.3 to 3,071.9**; vets year-1 `war`
sum **852.0**; vets median year-1 `war` **0.25**; rows carrying `surNpv` **895**; sum
of `surNpv` **$15,205,338,537** and the derived band **$14.065B to $16.346B**; Ohtani
`warTotal` **32.1**; Ohtani `surNpv` / `surTotal` **$401,046,245 / $409,804,789**.

> **The BANDS themselves are frozen and are not re-derived.** Plus or minus 5 percent,
> plus or minus 7.5 percent, plus or minus 10 rows, plus or minus 0.05 WAR absolute,
> plus or minus 20 percent or 2.0 WAR whichever is larger, the 50-row trigger, the
> Ohtani 4.0 WAR trigger, the Ohtani $75M `surNpv` trigger, the 5-team Team Outlook
> trigger and the 0.95 Spearman trigger all stand exactly as written in 9.1. What is
> restated is the BASELINE each band is applied to; the two ranges printed above are
> arithmetic consequences at the same frozen percentages and are recomputed, not
> re-chosen.

Section 9.2's "must not move" list needs one distinction recorded, and it is a
distinction about scope, not a change to the rule:

- `warChamp`, `warY1Champ`, the Team Outlook WAR roll-up, `lockedPct` and
  `byYear[].war` are listed as "insulated by construction because neither arm
  re-estimates the champion curves". **That insulation is against THE ARMS and it
  still holds against the arms.** It does not hold against the label repair, which
  does refit the champion curves. So their pre/post values are restated once, at the
  repair, and 9.2's assertion is then checked against the RESTATED values at each flag
  flip, exactly as written. The rule is unchanged.
- **The prospect rows.** 9.2 says the 183 prospect rows and their **683.1** five-year
  WAR sum "do not move under either arm", and 20.2 restates 683.1 as the sum over all
  183 rows. `vf.prospect_prime_path` (value_framework.py:1023) takes an FV, a role and
  an age, and does not take the corpus, so the claim about the ARMS stands unchanged.
  Whether the repair reaches those rows by some other route is **not asserted here**
  and is checked and published at the repair.

#### E. What does NOT go stale, stated so it is not restated by mistake

- Every number sourced from the committed artifacts `data/proj_horizon_eval.json`
  (2026-08-19) and `data/proj_calibration_eval.json` (2026-07-25). The repair does not
  regenerate either file. That covers **M's source edge** 0.0142 / 0.0271 / 0.0279 /
  0.0199 / 0.0106 and therefore **M = 0.0065**; the three levers' priors and intervals
  (role:C +0.2453 [+0.186, +0.309] on n=4,585; star -0.3961 [-0.621, -0.149] on
  n=2,085; the four age cells); 3.3's planted effect sizes, which are the nearer-zero
  ends of those intervals; 5.1's expectation that a B0-GATE cell lands near 40 percent
  of its published n; and the 65-cell selection disclosure in 1.2.
- **L3 already governs all of them**: they are priors and never comparators. The
  repair adds one more reason they are priors and changes nothing about their status.
- The READ LEDGER in G-0.1. It records reads that happened; a label repair does not
  un-read them.
- 4.6b's `season_fraction` 0.947, which moves with the calendar and not with this
  repair.
- 4.12's disk figures (29 bundles, 793,446,247 bytes) are a measurement of disk, not
  of the registration. They go stale when those bundles are deleted (21.3), and 4.12
  already states that the paragraph is replaced by the gate artifact's measured wall
  time.

### 21.5 What this amendment did NOT change, item by item

- **No threshold in section 15.** `M = 0.0065`; S1b's +0.0130; A-SHAPE's 0.2617 and
  0.1192; S3's 0.0200; S4's 0.0200 and [0.75, 0.87]; S5's 0.0050; S6's 0.0500; A0's
  0.0050 and 0.0100; B3's +0.0100; B4's 0.0500; B2's 0.5 ratio and 0.01 WAR floor;
  5.4a's 0.75 share; CONFIRM's n = 1,000; the VIF's 1.8 lower bound; Tripwire 2's 10
  points; k = 3; the lambda grid {0, 0.05, 0.10, 0.20, 0.40, 0.80}; and every band in
  section 9. **None is re-derived, in either direction.**
- **No frame boundary.** DEV = label seasons 2008-2011, GATE = 2012-2014, CONFIRM =
  2026, Tier-2 = 2015-2025, `first_base = 2003`, and 4.6's cell table stand exactly as
  written. No base and no label season is added to or removed from any frame; section
  15 bans widening and this amendment does not test that ban.
- **No primary criterion.** S1 is still the primary, still an accuracy non-inferiority
  test against S, still one-sided at 1.645 sd with the VIF applied. A-SHAPE is still
  NECESSARY and never sufficient. RS2, UAF and RAF are still DESCRIPTIVE and still
  cannot pass an arm in any direction.
- **No decision rule.** 4.4's Form 1 and Form 2 and the rule that selects between
  them; 4.4a's pre-flight; 4.3's comparator set and A0's tolerance branch; 4.6a's
  veto-only asymmetry; 4.6b's CONFIRM conditions; 4.11a's one-void cap; 5.1's B0 split;
  5.2's order; 5.3's absorption rule; 5.4a's twin rule; 5.5's Holm family, its k = 3
  and 5.5a's substitution; 5.5b's sign precondition; 5.5c's four legs; 12.2's failure
  responses; section 11's pre-committed sentences; and section 14's closed verdict
  vocabulary. All unchanged.
- **No clock date.** Section 13 stands: 2026-09-25, 2026-10-02, 2026-10-09,
  **2026-10-23 (ARM A look)**, 2026-11-06, **2026-11-13 (ARM B look)**, 2027-02-15.
  This amendment does not move a look and does not spend one.
- **No flag default.** `SERVE_SHAPE_REFIT = False` and
  `SERVE_BIAS_LEVERS = frozenset()` (8.2), and `MODEL_VERSION` stays derived from
  them (8.3).
- **No estimand in section 1**, and **L2 in particular is unchanged.** After the
  repair, `war_actual` at proj_ml.py:336 and proj_eval.py:85 still sums both sides per
  (mlbam, season), so each side-keyed model still estimates **E[TOTAL player WAR given
  this side's line]**. What the repair removes is the DOUBLING, not the totality. No
  arm may make a claim about two-way accuracy in either direction, and the served
  two-way population is still n = 1.
- **No change to L1's exclusion.** Every two-sided row stays excluded from every
  fitted cell and every scored cell in both arms **and** from the comparator S's
  point-in-time refits. The repair removes the 2x that was the exclusion's stated
  reason, and the exclusion still stands, because relaxing a control on the strength
  of a newly established fact is a re-registration and not an amendment. L1's
  disclosed consequence is also unchanged: the gate measures a CONTRAST between two
  consistently built arms and does not measure the served bundle's absolute level.
- **Nothing in section 20 is edited.** Two of its entries touch this row and both
  stand as the record of what was decided on design day: 20.1's row "S excluded the
  two-sided rows while the serve does not", and 20.2's declined item "Two-sided rows
  should be included so the comparator matches the serve", whose stated reason was
  that the implied fix "would score a known 2x label defect in both arms". That reason
  is superseded by the repair; **the decision it supported is not reopened here**, and
  reopening it is successor question 21.6 item 1.
- **No new criterion, clause, tripwire or verdict** is added by this amendment. It
  restates descriptives and records a repair. A gate that gains a clause in an
  amendment is a gate that was re-registered.

### 21.6 Successor questions this amendment opens and does not answer

1. **Whether L1's two-sided exclusion is still warranted** once the labels are
   correct. It is kept here unchanged. Revisiting it is a new registration that
   discloses this one.
2. **The one-sided-row consequence** in 21.3: a side-keyed map drops a true WAR
   component for a player-season that has a row on one side only. Measured and
   published at the repair; adjudicated by no clause here.
3. **18.7, the two-way workload discount.** Untouched. `TWO_WAY_PIT_PTH_FACTOR = 0.48`
   still applies only to the `warPTH` sum, the served `war` sum still carries no
   workload discount, and section 7's statement that a PASS in this battery is not
   evidence the owner's Ohtani complaint was addressed is unchanged.
4. **The live bundle.** `model/proj_lgbm/models.joblib` was fitted on the doubled
   frame. The comparator S is retrained point-in-time per base by the harness and
   therefore inherits the repair automatically; the LIVE bundle is what generates
   `data/mlb_projections.json` and therefore every descriptive in 21.4 group C and
   group D, and it does not. When it is retrained, and by whom, is not decided here.

### 21.7 The record

Filed 2026-09-18. No candidate scored, no arm run, no look spent, no threshold moved.
The row is appended to section 19.

---

## 22. THE RESTATEMENT, 2026-09-18: the repair landed and the numbers A-1 named are restated

Section 21 named the descriptives the two-sided label repair would move and named
the SOURCE each would be restated from. This section is that restatement, and it
contains **nothing but measurements**. It adds no clause, no criterion, no tripwire
and no verdict, it moves no threshold in either direction, and it spends no look.
Nothing was fitted and no candidate was scored: the only estimators run below are
the CHAMPION (`contract_war_path(use_ml=False)`) and the SHIPPED live bundle, both
of which are the incumbent, and both were run on the shipped corpus and on the
repaired corpus so the pair brackets the repair.

### 22.1 How the pair was measured, so the repair is separated from the drift

The `.cache/fa_corpus.pkl` on disk was pickled 2026-09-17 and the eWAR frames are
rebuilt nightly, so a straight before/after against that pickle mixes the repair
with a day of in-progress-season drift: measured, 791 player-seasons move for that
reason alone, all of them 2026. So both arms of every comparison below were rebuilt
from the SAME war_daily frames in the same session:

- **CONTROL**: `build_corpus(force=True)` on the shipped code. Its frame reproduces
  every L8 count and 4.1 item 1 exactly (22.3), which is what qualifies it as a
  control.
- **REPAIRED**: the same call on the repaired code.

The difference between the two arms is the repair and nothing else.

### 22.2 Group A, the corpus census (L1, section 7, section 0's last row)

| as registered | restated | verdict |
|---|---|---|
| L1: 671 of 35,825 corpus player-seasons (1.9 percent) carry rows on both sides | **671 of 35,825, 1.87 percent** | UNCHANGED, as A-1 predicted: which player-seasons carry two rows is structural |
| L1: identical `war` in all 671 | **6 of 671** | SUPERSEDED. The 6 are player-seasons whose hitting and pitching WAR happen to coincide. The other 665 held the same number on each row only because it was the same number: the whole-player total, written twice |
| L1 and section 7: 327 above the magnitude floor (absolute WAR at or above 0.5 on BOTH sides) | **7** | STALE, and it fell as A-1 predicted it would. The floor was being applied to a doubled whole-player value on both rows; on the repaired rows a mop-up inning reads as a fraction of a WAR |
| section 0, last row: those player-seasons train and score at 2x | **REPAIRED.** On the control/repaired pair the label moves on exactly **670** player-seasons and the ratio control/repaired is **exactly 2.0000 on every one of them** (min = max). The 671st has a zero label either way | the 2x is removed, and the measurement says it was a clean factor of two and not a mixture |

**The label itself.** Corpus label sum **26,408.0 control, 26,269.7 repaired**: the
repair removes **138.4 WAR, 0.524 percent**. That is A-1's 138.6 against 26,408,
reproduced on a same-session pair.

**Ohtani, the five largest doubled labels in the corpus, restated:**

| season | control | repaired | his hitter row `war` | his pitcher row `war` |
|---|---|---|---|---|
| 2021 | 15.84 | **7.92** | 4.89 | 3.03 |
| 2022 | 18.64 | **9.32** | 3.40 | 5.92 |
| 2023 | 17.08 | **8.54** | 6.11 | 2.43 |
| 2024 | 9.04 | **9.04** | 9.04 | (no pitcher row) |
| 2025 | 16.72 | **8.36** | 6.58 | 1.78 |

### 22.3 Group B, the frame descriptives (L8, 4.1 item 1): restated as IDENTICAL

A-1 required these to be republished whether or not they moved, because silence is
not a restatement. `build_training_frame(corpus, 2003, 2025, use_cache=False)` on
both arms:

| as registered | control | repaired |
|---|---|---|
| L8 hit per-horizon 19,965 / 19,038 / 18,092 / 17,187 / 16,341 | identical | **identical** |
| L8 pit per-horizon 24,325 / 22,997 / 21,617 / 20,340 / 19,083 | identical | **identical** |
| L8: 81.8 percent of hit base rows and 78.4 percent of pit base rows carry all five horizons | 0.8185 / 0.7845 | **0.8185 / 0.7845** |
| 4.1 item 1: 90,623 hit rows plus 108,362 pit rows = 198,985 | identical | **identical** |

**Not one row moved.** A-1 reasoned that any movement here could only be
second-order, through `build_features` returning None when the champion cannot
project, because row inclusion never turns on the label value. The champion did
move (22.4) and it did not move any row across the feasibility boundary.

The label SUMS inside those unchanged rows do move, and they are published because
they are what the frame trains on: hit `y` by horizon 12,771.9 / 11,135.3 / 9,256.9
/ 7,362.3 / 5,706.3 becomes **12,661.5 / 11,040.9 / 9,164.9 / 7,282.1 / 5,655.5**,
and pit 8,876.3 / 7,569.6 / 6,228.0 / 4,941.6 / 3,785.8 becomes **8,819.0 / 7,533.7
/ 6,192.1 / 4,914.3 / 3,773.7**.

### 22.4 What 21.3 said moved on disk, checked against what did

Three of A-1's own statements are corrected here by measurement, under this
document's standing rule that where it and a later measurement disagree, the
measurement is what the gate uses. All three corrections run in the same direction:
the repair is better contained than A-1 assumed.

| 21.3 said | measured | correction |
|---|---|---|
| the repair "moves both WAR maps and both curve sets, and therefore moves the champion path for EVERY player" | **919 of 2,199** champion paths at the serving base move at all (41.8 percent). Median 5-year move **0.0000**, mean **-0.0013 WAR**, p95 **0.14**, and only **2** rows move by more than 1.0 WAR, both of them Ohtani's two sides | the reach claim was too strong. The maps and the curves do move (hitter coefficients [-0.1495, 1.98, 0.868, -0.1483, 0.2647] to [-0.1479, 1.9778, 0.8661, -0.1540, 0.2670], pitcher [-0.1259, 0.9564, 1.1887, 0.2264] to [-0.1248, 0.9612, 1.1779, 0.2196]), and most players' champion path does not |
| `model/proj_lgbm/models.joblib`: "`train_hash` digests `X.shape` and `X.sum(axis=0)` and never `y` (18.6), so a pure label change does not move it" | on the control/repaired pair the shipped recipe returns **a30bb9ae8f9cd9c3** and **cb42b96eb5ea533c** | the recipe's blindness to `y` is real and 18.6 stands, but THIS repair is not a pure label change: `champ_h1..champ_h5` are columns of `X` and the champion moves, so the hash moves anyway. A retrain will be visible in the hash |
| `.cache/proj_ml_frame_*.pkl` and the 29 `.cache/proj_ml_pit_*.joblib` "must be deleted" | the repair stamps `label_shape` on the corpus and `proj_ml._war_tag` carries it, so the frame key becomes `proj_ml_frame_fe323aac_2003_2025_2000_2026_ewar_v2_side_keyed_v1.pkl` and every pit bundle re-keys with it | they no longer need deleting, because they can no longer be read. Deleting them is now housekeeping rather than a correctness step. `.cache/fa_corpus.pkl` likewise no longer needs a manual `force`: `_corpus_label_shape_stale` refuses a corpus without the stamp |

`.cache/fa_fits_*.pkl` self-invalidated exactly as 21.3 said, through `_corpus_sig`,
which digests every row's `war`.

**What is NOT covered, stated so it is not assumed.** `model/proj_lgbm/models.joblib`
loads by path and carries no key at all, so nothing re-keys it. It is stamped and
announced instead: `train()` now writes `war_provider` and `label_shape` into bundle
meta and `load()` logs when a bundle predates the repair. That is A-1's successor
question 21.6 item 4 and it is still open: the live bundle is not retrained by this
lane.

### 22.5 Groups C and D are NOT restated here. This is the pre-view, and it is labelled as one

A-1 filed the served descriptives (4.5's table, section 0's rows, and all of section
9's design-day baselines) to be restated **at the first regeneration of
`data/mlb_projections.json` after the repair**, under section 14's standing rule that
pools are counted at scoring time. **This lane does not run that regeneration and
does not restate them.** What follows is the incumbent engine scored on both corpora
over a corpus-derived population of 2,199 rows, published so that the regeneration
has something to be checked against, and it is **not** the recount. It is also not a
candidate: the estimator is the shipped bundle in both arms.

| 4.5 row | as registered (served artifact) | pre-view, control | pre-view, repaired |
|---|---|---|---|
| `war` pool / RS2 mean / RS2 median / UAF / RAF | 278 / 0.4362 / 0.3668 / 0.1592 / 153 | 257 / 0.4519 / 0.3821 / 0.1615 / 144 | **258 / 0.4514 / 0.3852 / 0.1628 / 146** |
| `warPTH` | 447 / 0.5749 / 0.4778 / 0.1834 / 279 | 450 / 0.5740 / 0.4701 / 0.1861 / 284 | **443 / 0.5728 / 0.4810 / 0.1868 / 278** |
| `warChamp` | 311 / 0.0670 / 0.0451 / 0.0000 / 0 | 311 / 0.0661 / 0.0443 / 0.0000 / 0 | **311 / 0.0668 / 0.0443 / 0.0000 / 0** |

The `warChamp` pool of 311 comes back at exactly 311, on the same rule, from the
engine rather than from the artifact. **A-SHAPE's contingency does not fire on this
pre-view**: the `war` RS2 mean sits at 0.4514 against a frozen bar of 0.2617 and UAF
at 0.1628 against 0.1192, so both legs remain binding, and neither bar is touched.

**The wobble is not what this repair fixes, and the numbers say so.** RS2 mean moves
by 0.0005 and UAF by 0.0013. The owner's first symptom stays exactly where ARM A
found it.

**The level moves, and the two-way row moves a lot.** 5-year served `war` over the
2,199 rows: **3,031.7 to 2,999.4, -1.06 percent**, with a median row move of 0.0000
and 698 rows moving at all. Ohtani's two sides sum **31.30 to 21.90, a 9.40 WAR
fall**. Section 9.1's Ohtani trigger fires at a move of more than 4.0 WAR, so **that
trigger is crossed on the pre-view**, and it is recorded here rather than discovered
at the flip. Ten rows move by more than 1.0 WAR and two by more than 3.0, which is
well inside 9.1's 50-row threshold. The other movers of size are position players
whose PITCHER row used to carry their whole batting season: four of them fall from
about 1.6 to 2.0 five-year WAR to about 0.03 to 0.06, which is the cohort section
0 described as "position players who threw a mop-up inning and had their whole value
doubled for it", finally reading as what they are.

### 22.6 Successor question 21.6 item 2, answered

A-1 disclosed that a side-keyed map would drop a TRUE component of the label for a
player-season carrying a corpus row on ONE side only (a pitcher's plate appearances
are excluded from the hitter corpus by position, so his batting WAR would have no
row to ride on), and filed it as measured at the repair and adjudicated by no clause.

**Measured: 7,745 player-seasons and 44.3 WAR, and the repair does not incur it.**
The corpus carries two columns rather than one: `war` is the row's own side, which
is what the per-side fits regress, and `war_total` is the player-season's whole WAR,
which is what the label reads, ONCE, through `fa_projection.war_actual_map`. On the
control/repaired pair **zero one-sided player-seasons move**. The estimand L2
registers, E[TOTAL player WAR given this side's line], is therefore unchanged in
fact and not only in intent.

The per-side column does move, and that is the point of it: 601 of 17,091 hitter
rows and 7,619 of 19,405 pitcher rows, net -3.3 and -90.9 WAR. Those rows are the
input to `fit_war_map` and `fit_aging_curves`, which were regressing a pitcher's WAR
on his innings while his batting WAR sat in the dependent variable.

### 22.7 What this section did NOT do

- **No candidate was scored.** No arm was fitted, no lambda was chosen, no frame in
  4.6 was opened for a candidate, no look was spent, and no statistic in S1 through
  S6, A-SHAPE, S7, S8, B1 through B4 or the Holm family was computed on anything.
  The two estimators run above are the champion and the shipped bundle.
- **No threshold moved**, in either direction. Every number in section 15 stands,
  including A-SHAPE's 0.2617 and 0.1192 against a restated baseline, which is
  precisely the case 21.4 froze them for.
- **No clock date moved and no look was spent.** Section 13 stands.
- **No flag default moved.** `SERVE_SHAPE_REFIT = False` and
  `SERVE_BIAS_LEVERS = frozenset()` are unwritten and stay that way.
- **L1's two-sided exclusion is unchanged**, still in force, still disclosed. The
  repair removes its stated reason and reopening it remains successor question 21.6
  item 1.
- **Sections 9.1 and 9.2 are not restated.** They are restated at the regeneration,
  from the served artifact, per 21.4 group D. The pre-view in 22.5 is not that
  restatement and may not be quoted as it.

### 22.8 The record

Measured and filed 2026-09-18. No candidate scored, no arm run, no look spent, no
threshold moved. The row is appended to section 19.
