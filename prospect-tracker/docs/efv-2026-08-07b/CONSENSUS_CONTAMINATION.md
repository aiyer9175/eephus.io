# Lane D1. Retroactive contamination of historical consensus points

Status: PRE-REGISTRATION written before the measurement ran. Results appended below the
registration block, which is not edited after the fact.

Artifact: `data/consensus_contamination_eval.json`
Lab: `tools/consensus_gate_lab.py`
Plan: `docs/master-plan-2026-08-07b-efv-audit.md` section 5, defect D1; lane D-1.

This lane is READ-ONLY on `consensus.py` and `grade_normalization.py`. It measures the
leak and designs the repair. The repair ships in a later wave with its own gate doc,
because it moves a published eFV headline.

---

## 1. The claim under test

`consensus.build_timeseries` (`consensus.py:1156`) recomputes every historical point from
scratch on each run. Three ingredients of `consensus_fv_raw` are computed over the
player's or the corpus's FULL snapshot history and applied retroactively to every point:

- **C1 `total_fv_instances`.** Counted with no date filter (`consensus.py:1246-1252`),
  passed as one scalar to every event date (`consensus.py:1298`). The single-instance
  pull toward FV 35 (`consensus.py:775-787`) therefore fires or does not fire on a 2019
  point according to whether the player was re-graded in 2024.
- **C2 `dropped_off_pairs`.** Computed once over the entire snapshot pool comparing the
  two most recent org lists per (source, org) (`consensus.py:1212`, `:1021-1030`). The
  resulting `(fv+30)/2` shrink is applied at every historical point
  (`consensus.py:606-636`). A drop-off detected between the 2025 and 2026 lists shrinks a
  2020 point.
- **C3 grade normalization.** `build_remapper` (`grade_normalization.py:227`) builds cells
  from `_all_latest()` (`:72-101`), an unfiltered `SELECT ... FROM snapshots` over the
  whole table. Cells are keyed by the snapshot's own year, which is contemporaneous at
  YEAR granularity only: a February point is normalized against an offset that includes
  that source's December grades. When a `(source, role, year)` overlap is thinner than
  `_MIN_N = 30`, `_paired_dists` (`:112-132`) pools the overlap across ALL years including
  future ones.

Why it matters: `consensus_fv_raw` at the as-of point is `_FEATURES_HIT[0]` and
`_FEATURES_PIT[0]`, it is the consensus OLS leg of the blend, and it is the baseline the
model must beat (`efv_model.py:21`, `efv_model.py:1268` via `_prep`'s `"fv"` key).
`efv_dataset._asof_point` (`efv_dataset.py:409-418`) picks the correct POINT. The
contamination is inside the point's VALUE.

## 2. What is measured

Replay `build_timeseries`'s per-player loop in the lab, five ways, over the real snapshot
corpus (`storage.load_all_snapshots()`, `prospects.db`):

| arm | C1 | C2 | C3 |
|---|---|---|---|
| `baseline` | full history | full corpus | full corpus |
| `asof_c1` | as-of event date | full corpus | full corpus |
| `asof_c2` | full history | as-of event date | full corpus |
| `asof_c3` | full history | full corpus | as-of event date |
| `asof_all` | as-of | as-of | as-of |

"As-of event date" means the ingredient is recomputed using only snapshots whose
`snapshot_date <= ` the event date being built.

The comparison population is the two shipped training matrices,
`data/xfv_hitter_matrix.json` (1,917 rows) and `data/xfv_pitcher_matrix.json` (2,040
rows), joined on `(player_key, asof_date)`. Per arm and per side:

- `n_differ` at a 0.005 FV tolerance,
- `delta = asof_value - baseline_value`: mean, sd, max absolute, counts above 0.5 and 1.0,
- the worst-hit fold, where fold is `efv_model._decision_year` (`efv_model.py:883-887`)
  restricted to `SCORED_YEARS` (`efv_model.py:81`),
- the leak test in section 3.

## 3. Fidelity gate, run BEFORE any of the above is believed

The lab's `baseline` arm must reproduce the shipped matrix's `consensus_fv_raw` on the
joined rows. Criterion, pre-registered: **at least 99.0% of joined rows agree to within
0.005 FV**. Below that the replay is not a faithful copy of production and every number
in this document is void. Rows that do not reproduce are enumerated in the artifact under
`fidelity.mismatch_sample` and excluded from every downstream statistic, with the
exclusion count reported.

## 4. The leak test

Contamination that is pure noise is a defect but not a leak. Contamination is a LEAK if
the future-informed value ranks the outcome better than the as-of value would have. On
the affected subset only (rows where the arm changes the value):

- `rho_baseline` = Spearman(`consensus_fv_raw` baseline, target)
- `rho_asof` = Spearman(`consensus_fv_raw` as-of, target)
- `d_rho = rho_baseline - rho_asof`

Target: `target_censored`, the model's primary (`efv_model.py:14`). `target_resolved` is
the sensitivity check. Noise band: 2,000 paired bootstrap resamples of the affected subset,
CI95 on `d_rho`.

**This is a diagnostic, not a ship gate.** Per the brief and plan section 5, the repair is
gated on the leak measurement (section 5), never on a downstream rho. `d_rho > 0` outside
its band is evidence the contamination is informative, which STRENGTHENS the case for the
repair while predicting the published headline will fall.

## 5. Pre-registered verdict rule, per channel

- **FALSE**: the channel changes zero rows.
- **CONFIRMED-IMMATERIAL**: the channel changes rows, but every one of these fails:
  (a) at least 1.0% of joined rows move by 0.5 FV or more, (b) mean absolute delta over
  affected rows is 0.25 FV or more, (c) `d_rho` CI95 excludes zero.
  A CONFIRMED-IMMATERIAL channel is ledgered, not repaired, and that is a successful
  outcome, not a failed lane.
- **CONFIRMED-MATERIAL**: any of (a), (b), (c) holds. Repair specified and handed to the
  next wave.

The combined `asof_all` arm is reported under the same rule. Channels can interact: C1
gates a multiplicative pull and C2/C3 move its input, so `asof_all` is not the sum of the
three singles and is not reported as such.

## 6. Explicitly out of scope

Outlet weights. Reverted to equal on 2026-07-25, ship gate hardened, arm CLOSED
(plan section 2). Not touched, not refit, not measured here.

---

# RESULTS

Every number below carries a key into `data/consensus_contamination_eval.json`.
Corpus: 54,061 snapshots, 3,957 matrix rows, 45 distinct as-of dates (`inputs`).
`ADOPT_NORMALIZED_CONSENSUS = True`, `SINGLE_SOURCE_K = 0.5`, `_MIN_N = 30`.

## R0. Fidelity. The pre-registered gate FAILED. Read this before anything else.

`fidelity.pct_within_tol = 87.824%` on 3,934 joined rows (3,455 within 0.005 FV). The
pre-registered bar was 99.0%. **The gate as written FAILED.** It is recorded as a failure
and the bar was not moved.

Diagnosis, and it is not a replay defect. 478 of the 479 mismatches are exactly 0.01 FV
(`fidelity.n_mismatch_le_0p02 = 478`); `fidelity.pct_within_0p02 = 99.975%`. That is the
signature of an artifact-vintage drift, not a logic difference: the shipped matrices were
built against an earlier `prospects.db` state, and because
`grade_normalization._apply_offset` is a mean-difference over the whole paired overlap
(`grade_normalization.py:155`), any change to the DB moves every offset by a hair and
every normalized grade by a rounding step.

The pre-registered check confounded two questions. A second check was ADDED, and is
labelled as post-hoc in the artifact (`fidelity_replay.added_post_hoc = true`): call
`consensus.build_timeseries` itself on the same snapshots and compare point-for-point.
`fidelity_replay.pct_within_tol = 99.975%`, 3,933 of 3,934, ONE mismatch. The replay is a
faithful copy of production.

The single mismatch is `carlos_sanchez` at 2026-08-07, replay 40.7 versus production 35.0.
It is not a replay bug either. It is D16 (section R7): two different players named Carlos
Sanchez, and production's same-name merge hands the training row the other one's grade.

That row is excluded from every statistic below (`clean`, n = 3,933). The 478 hairline
rows are kept: dropping 12% of the pool over a difference smaller than the display
precision of the column being measured would cost more than it buys, and the delta
statistics compare two replay arms to each other, so a common vintage offset cancels.

A further 23 matrix rows do not join at all (`fidelity.n_unjoined = 23`), every one
because the row's `asof_date` is not a date on which that player has any snapshot. Those
are D16 as well, and they are counted there rather than discarded quietly.

## R1. Channel verdicts

`channels.<arm>.by_side.both`. Delta = as-of value minus baseline value, in FV.

| channel | n_differ | % of 3,933 | mean d | sd | mean abs d (affected) | max abs d | >=0.5 FV | >=1.0 FV | verdict |
|---|---|---|---|---|---|---|---|---|---|
| C1 `total_fv_instances` | 117 | 2.98% | -0.092 | 0.617 | 3.104 | 10.42 | 112 | 112 | CONFIRMED-MATERIAL |
| C2 `dropped_off_pairs` | 0 | 0.00% | 0.000 | 0.000 | 0.000 | 0.00 | 0 | 0 | **FALSE** |
| C3 grade normalization | 2,286 | 58.12% | +0.940 | 1.590 | 1.693 | 4.29 | 1,142 | 1,098 | CONFIRMED-MATERIAL |
| ALL three | 2,316 | 58.89% | +0.822 | 1.603 | 1.620 | 7.93 | 1,160 | 1,089 | CONFIRMED-MATERIAL |

C1 and C3 clear criteria (a) and (b) on their own magnitudes. `asof_all` additionally
clears (c) (section R4).

**C2 is FALSE, and the reason is a second, larger defect. See R2.**

Worst movers under `asof_all` (`top_movers_asof_all`), all of them repairs DOWNWARD, all
of them debut-cohort training rows:

| player | as-of | side | baseline | as-of | delta |
|---|---|---|---|---|---|
| tyler_skaggs | 2012-01-22 | pit | 66.26 | 58.33 | -7.93 |
| dansby_swanson | 2016-01-22 | hit | 60.95 | 55.00 | -5.95 |
| andrew_benintendi | 2016-01-22 | hit | 60.95 | 55.00 | -5.95 |
| haseong_kim | 2021-02-26 | hit | 50.00 | 45.00 | -5.00 |
| kevin_gausman | 2013-01-22 | pit | 56.26 | 51.67 | -4.59 |

## R2. C2 is FALSE because the drop-off detector has never fired. New P1 defect.

`c2_detector`:

- `occurrences_of_legacy_slug_in_corpus = 0`
- `occurrences_of_human_org_label_in_corpus = 13,251`
- `shipped_detector_pairs_full_corpus = 0`
- `corrected_detector_pairs_full_corpus = 463`

`_dropped_off_pairs` skips any snapshot whose `interval_label` lacks the substring
`_org_` (`consensus.py:1001-1002`). That legacy slug form occurs **zero** times in this
corpus. The org lists are all in the human-readable form, 478 distinct labels of the shape
`MLB Pipeline 2021 Nationals Top 30`, 30 orgs, 16 cycles 2011 to 2026, 13,051 snapshot
rows over 5,434 distinct players. So `dropped_off_pairs` is the empty set on every run,
and the `(fv+30)/2` drop-off shrink at `consensus.py:606-636` **has never fired in
production**.

This is the same two-format bug the rank-implied-FV path already caught and fixed. The
comment at `consensus.py:686-698` documents it verbatim ("Two label formats to catch:
internal slug `_org_` (legacy), human-readable `MLB Pipeline 2021 Nationals Top 30`. Bryan
Sanchez was the canary"). The fix went into the rank path via `_ORG_LIST_LABEL_RE` and was
never propagated 300 lines up to `_dropped_off_pairs`.

Consequences that matter beyond this lane:

1. `consensus.py:1207-1210` says drop-off detection "runs ONCE across the full snapshot
   pool ... to avoid O(N x M) recomputation". It runs once and returns nothing.
2. Plan lane **D-4** proposes fitting the `(fv+30)/2` shrink and calls it the constant with
   "better overlap" and "a real prior". It has zero overlap. D-4 cannot fit this constant
   until the detector is repaired, and fitting it on the current detector would be fitting
   a coefficient on an all-zero regressor.
3. The `dropped_off` flag on `per_source` is likewise always false, so any UI or export
   reading it shows nothing. Not audited here.

With a corrected detector (dual-format slug, `tools/consensus_gate_lab.py:_org_slug`), the
D1 channel-2 contamination is real and large. `pairwise.c2_corrected_asof_vs_corrected_full`
isolates it: **410 of 3,933 rows (10.4%) change, mean absolute delta on affected rows 3.44
FV, max 15.47 FV.** That is the biggest per-row contamination of any channel. It is latent,
not live, because the detector is dead, and it becomes live the moment the detector is
fixed. Fixing the detector without the as-of fix in the same change would INTRODUCE a P0.

Direct evidence that the retroactive form is a leak, `channels.fix_c2_detector.leak_fullpool`
and `channels.fix_c2_detector_asof.leak_fullpool`:

| arm | side | rho_baseline | rho_arm | d_rho | CI95 |
|---|---|---|---|---|---|
| corrected detector, RETROACTIVE | hit | 0.2750 | 0.2814 | -0.0064 | [-0.0128, -0.0005] |
| corrected detector, AS-OF | hit | 0.2750 | 0.2735 | +0.0016 | [-0.0098, +0.0122] |
| corrected detector, RETROACTIVE | pit | 0.2121 | 0.2175 | -0.0055 | [-0.0126, +0.0020] |
| corrected detector, AS-OF | pit | 0.2121 | 0.2174 | -0.0053 | [-0.0186, +0.0068] |

The retroactive detector improves hitter rank resolvably (CI excludes zero). The as-of
detector does not move it. On hitters, the entire measurable ranking gain of the drop-off
shrink comes from information that did not exist at the decision point. That is the leak,
demonstrated directly rather than inferred.

## R3. Side and fold

C3 is the broad channel and it is symmetric: 61.4% of hitter rows, 55.1% of pitcher rows
(`channels.asof_c3.by_side`). Its sign is consistent and its fold profile is monotone in
snapshot density, which is the tell that the mechanism is the thin-cell pooling. The worst
folds (`channels.asof_c3.worst_folds`) are the earliest ones, where as-of there is no
qualifying overlap at all and the grade falls back to raw, while production applies an
offset pooled from up to fifteen later years:

| fold | n | n_differ | mean delta |
|---|---|---|---|
| hit:2013 | 56 | 56 | +3.785 |
| hit:2014 | 96 | 96 | +3.741 |
| hit:2015 | 78 | 78 | +3.721 |
| pit:2013 | 56 | 56 | +3.496 |

Every row in those folds moves, by an average of 3.5 to 3.8 FV. The sign is positive
because the pooled offset de-biases MLB Pipeline's roughly +4.4 FV hot scale
(`grade_normalization.py:141-144`) using data the point could not have seen.

C1 is concentrated and violent rather than broad: 117 rows, but a mean absolute delta of
3.10 FV on those rows and a maximum of 10.42. Worst folds
(`channels.asof_c1.worst_folds`) are pit:2011 (5 of 8 rows, mean -2.56), pit:2012 (15 of
30, mean -2.38), hit:2011 (5 of 10, mean -1.99). The sign is negative: as-of, an early-year
player often has exactly one FV instance and the FV-35 pull SHOULD fire, and production
suppresses it because the player was re-graded years later.

The pitcher side is worse than the hitter side on both live channels: C1 3.75% of rows
versus 2.15%, C3 full-pool `d_rho` +0.0082 versus +0.0011.

## R4. Leak test

Pre-registered form, on the affected subset (`channels.<arm>.leak`), target
`target_censored`:

| arm | side | n | rho_baseline | rho_asof | d_rho | CI95 | excludes 0 |
|---|---|---|---|---|---|---|---|
| C1 | hit | 41 | 0.2825 | 0.2825 | 0.0000 | [0.000, 0.000] | no |
| C1 | pit | 76 | 0.2175 | 0.2175 | 0.0000 | [0.000, 0.000] | no |
| C3 | hit | 1,169 | 0.3171 | 0.3226 | -0.0054 | [-0.0199, +0.0089] | no |
| C3 | pit | 1,117 | 0.2599 | 0.2449 | +0.0150 | [-0.0042, +0.0349] | no |
| ALL | hit | 1,178 | 0.3171 | 0.3189 | -0.0018 | [-0.0171, +0.0142] | no |
| ALL | pit | 1,138 | 0.2560 | 0.2295 | **+0.0265** | **[+0.0046, +0.0477]** | **YES** |

`target_resolved` agrees throughout (ALL/pit +0.0254 [+0.0043, +0.0460]).

**The combined contamination is a resolvable leak on the pitcher side.** Criterion (c) is
met for `asof_all`. The contaminated consensus ranks pitcher outcomes 0.027 Spearman
better than the honest as-of value on the same 1,138 rows, and the interval excludes zero
on both targets independently.

C1's `d_rho` is exactly 0.0 with a zero-width interval. That is not a null, it is a
DEGENERATE STATISTIC and it must not be reported as evidence of anything. Every affected
row receives the identical affine map `2/3 x + 35/3`, which is monotone, so within the
affected subset Spearman cannot move by construction. The affected-subset form has zero
power for this channel. A full-pool form was ADDED for that reason
(`channels.<arm>.leak_fullpool`; `leak_test_fullpool` is documented as post-hoc in the
lab):

| arm | side | rho_baseline | rho_asof | d_rho | CI95 |
|---|---|---|---|---|---|
| C1 | hit | 0.2750 | 0.2726 | +0.0025 | [-0.0025, +0.0077] |
| C1 | pit | 0.2121 | 0.2091 | +0.0030 | [-0.0049, +0.0102] |
| C3 | hit | 0.2750 | 0.2739 | +0.0011 | [-0.0083, +0.0103] |
| C3 | pit | 0.2121 | 0.2038 | +0.0082 | [-0.0029, +0.0196] |
| ALL | hit | 0.2750 | 0.2727 | +0.0024 | [-0.0070, +0.0126] |
| ALL | pit | 0.2121 | 0.2008 | +0.0113 | [-0.0005, +0.0227] |

Six of six positive, none individually resolvable, ALL/pit a hair from it. Consistent with
the affected-subset result and with a small real leak. Reported as a direction, not a size.
The C1 and C3 verdicts do not rest on any of it: they rest on criterion (a), the
magnitude, which does not touch the outcome variable at all.

## R5. What this predicts for the published headline

The repair moves `consensus_fv_raw` on 58.9% of training rows and by 0.5 FV or more on
29.5% of them. The eFV headline is scored against an OLS baseline on that exact column
(`efv_model._fit_ols_fv`, fed by `_prep`'s `"fv"` key at `efv_model.py:1268`), and the
column is also `_FEATURES_HIT[0]` and `_FEATURES_PIT[0]`. The headline WILL move, and the
consensus baseline will get slightly WORSE on pitchers, so the eFV-minus-consensus margin
will probably WIDEN.

**That is not a win and must not be reported as one.** It is the baseline losing borrowed
information, which is what a true-to-model correction looks like, exactly as the 2026-07-24
as-of repair did. Section 4 of the pre-registration and plan section 5
(`docs/master-plan-2026-08-07b-efv-audit.md:238-241`) both forbid gating on it. The ship
gate for wave 2 is the leak measurement in R1 to R4, which is already met.

## R6. D-5 hygiene. CONFIRMED, no edit needed.

`d5_hygiene`. `apply_shrinkage` (`consensus.py:907`) and `compute_prior_mean_fv`
(`consensus.py:950`) have ZERO production callers tree-wide; the only importer is
`test_consensus.py:24`. `DEFAULT_SHRINKAGE_K` / `DEFAULT_N_FULL` / `FALLBACK_PRIOR_FV`
(`consensus.py:127-129`) occur in exactly five other places: the two dead functions'
defaults (`:910`, `:911`, `:952`) and three `build_timeseries` keyword defaults
(`:1159-1161`) whose parameter names never recur anywhere in the function body. They are
INERT.

The docstring at `consensus.py:1173-1180` already says so correctly and already records
that an earlier version of it was false and cost an audit real time. **No edit is
required.** Deleting the functions would break `test_consensus.py:24`, so a delete is a
two-file change and is not worth an owner-visible diff; leave them.

## R7. D16 same-name collisions. CONFIRMED, and it reaches the training matrix.

`_SAME_NAME_NOT_DUPES` is `set()` at `consensus.py:1359`, so the allowlist branch at
`:1370-1373` is unreachable and every normalized-name collision merges silently.

Measured on the live corpus (`d16`):

- 436 normalized names carry more than one `player_key`
- 939 player_keys involved, **503 merged away**
- 357 collisions are the intended `__noid` case
- **79 are NOT the `__noid` case** and are merged with no check at all
- 32 of those 79 have OVERLAPPING publication windows, which one player cannot have
- **4 are provably different people**: the colliding keys carry two different MLBAM ids
  (`adrian_martinez_837701` vs `adrian_martinez_834255`; `jose_gonzalez_806919` vs
  `jose_gonzalez_837212`; `luis_de_leon_808029` vs `luis_de_leon_825479`;
  `luis_hernandez_801346` vs `luis_hernandez_815211`)

This is not cosmetic. `d16.matrix_impact`: **24 of 3,957 eFV training rows carry a
`consensus_fv_raw` that belongs to a different player.** The mechanism is that
`consensus.py:1381-1391` pools points across the merged keys and `efv_dataset._asof_point`
(`efv_dataset.py:409-418`) then selects one; when the merged-in key owns the point at that
date, the training row gets the other player's grade. Verified against the DB:

| matrix key | as-of | kind | value actually came from |
|---|---|---|---|
| `josh_smith__sa3009923` | 2022-02-24 | debuted | `josh_smith`, FanGraphs FV 50.0, org TEX |
| `carlos_sanchez` | 2026-08-07 | bust | `carlos_sanchez_801522`, performance_ingest FV 35.0, org MIA. The Reds prospect's own point is FV 45.0, org CIN, a 10 FV error |
| `luis_meza` | 2023-08-01 | bust | `luis_meza__sa3018423`, FanGraphs FV 35.0, org TOR |

The `carlos_sanchez` case is the one that broke the replay fidelity check in R0, which is
how it surfaced: the defect announced itself.

Recommended edit is a DETECTOR, not a policy change, and is specified in the return value.
It does not move any served number. Deciding which collisions are genuine merges is a data
question for a later lane; making the 79 visible is one counter and one log line.

## R8. The repair, verified and timed

`repair_prototype`. The naive as-of repair rebuilds the grade-norm remapper at each event
date, which is quadratic inside a loop that already walks every event date of every
player: **1.78s for 45 dates, extrapolating to 39.2s for the corpus's 994 dates**, against
a current whole-`build_timeseries` cost of 5.2 to 7.2s
(`fidelity_replay.build_timeseries_sec`). That is a 6x to 8x regression on the hot path and
it is not acceptable.

The incremental formulation is exact and free. `_apply_offset`
(`grade_normalization.py:155`) reduces each cell to `mean(src) - mean(ref)`; the sorted
arrays it is handed are never read for anything else. So the whole as-of timeline can be
built in ONE ascending pass over the snapshot rows, maintaining running pair sums per
`(source, role, year)` plus per-value counters for the `_mappable` uniqueness check.
`tools/consensus_gate_lab.py:build_offset_timeline` implements it and it is verified
against the from-scratch builder: **1,323 cells across all 45 as-of dates, 0 mismatches at
1e-9** (`repair_prototype.exact = true`), in **0.18s for all 994 dates**, a 218x speedup
over the extrapolated naive form and about 3% of the current build cost.

One trap the prototype had to be corrected for, and wave 2 will hit it too:
`_all_latest` (`grade_normalization.py:96`) keeps a row only when it is STRICTLY newer, so
the FIRST row wins a same-date tie. An incremental builder that overwrites unconditionally
drifts the pair sums and produced 320 mismatched cells before this was matched.

The exact function-by-function repair, with signatures and call sites, is in the lane's
return value and is not restated here. It ships in wave 2 with its own gate doc.
