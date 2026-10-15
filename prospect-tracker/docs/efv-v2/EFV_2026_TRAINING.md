# eFV training through the 2026 season: the training-window amendment (registered before any fit)

Written 2026-10-15 (task EFV_2026_FOLD_TRAINING) under the owner's decision EW3-13 of 2026-10-15
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, verbatim: "The 2026 season is resolved (we're only
scoring the regular season where WAR is accumulated), please use it to improve eFV further";
asked how, the owner chose TEST ONCE, THEN TRAIN). The test ran first and once
(EFV_2026_HOLDOUT_READ, `docs/efv-v2/EFV_2026_HOLDOUT.md`, verdict ties, frames SPENT by the dated
note of 2026-10-15 in `docs/efv-v2/EFV_V2_GATE.md`). This document is the TRAIN half. It is
committed ALONE, before the code that reads it and before any fit on the rows it opens. No
em-dashes. Nothing here, in its code or in its receipts, is grouped, counted or averaged by
consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, binding).

Registration status: REGISTERED (training-window amendment; it opens fits, never a look)

## 1. What this amendment does

Until today every eFV fit stopped before `efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR` (2025): the
2025 and later debut cohorts were the prospective reserved frame R-VM, held out for looks. The
2026 holdout read spent the 2026-season outcomes of those cohorts. This amendment lets the
development and production FITS read decision years and debut cohorts through the 2026 season,
behind one flag, so a new model (EFV_X3 or a successor) can train on the 2025 and 2026 debut
classes and the 2026 season.

- **The flag.** `efv_vintage_frame.EFV_TRAIN_THROUGH_2026`, default **False**. It stays False
  until EFV_X3 or a successor model is registered WITH it (that model's own registration names
  the flag and is committed before its first fit). Flipping it is not part of this task.
- **The bound.** `efv_vintage_frame.TRAIN_THROUGH_SEASON = 2026`. One function,
  `efv_vintage_frame.train_end_year()`, returns the first decision year a FIT may not read:
  `R_VM_FIRST_DEBUT_YEAR` (2025) with the flag off, exactly as today; `TRAIN_THROUGH_SEASON + 1`
  (2027) with the flag on. Every fit-row threshold in the guards this task names reads it:
  `efv_v2_model._check_years`, the production training filters (`efv_v2_serve`, `efv_v3`,
  `efv_v4`, `efv5_group_drivers`, `efv5_combined.production_train`) and the vintage-matched
  column builders that skip reserved-year rows on a training path (no gate sha).
- **The rows.** The fits read the v1 matrix pool (`efv_v2_model.training_rows`, v1's pool rule,
  recent never-MLB busts left out as v1 leaves them out). With the flag on that pool is read
  from a TRAINING-ONLY copy of the matrices,
  `data/_labs/efv2026/train_matrix_{side}_through2026.json`, written by
  `python efv_2026_fold.py --build`: `efv_dataset.build_matrix` with `DEBUT_YEARS` widened to
  2011 through `TRAIN_THROUGH_SEASON`, every other rule unchanged. The build refuses to write
  unless every row it shares with the served matrix is identical to the served row (so the
  copy is the served pool plus the 2026 debut class and nothing else). The 2025 debut class is
  already in the served matrices (two observed seasons, weight 0.333); the 2026 debut class
  enters with one observed season at the builder's own censoring rule (weight 0.167, the
  observed-rate tail projection of `efv_dataset._label_6yr`). The served matrices,
  `efv_dataset.DEBUT_YEARS` and every served artifact are untouched.

## 2. What it does NOT open

- `source_backtest.CANDIDATE_YEARS`, `efv_model.SCORED_YEARS` and `reserved_vm_pins()` are not
  widened: no served claim, Source Comparison score or headline frame reads a 2025 or 2026
  cohort.
- `guard_vm_request`, `guard_score_request` and `RESERVED_LV` keep their rules. A LOOK or a
  SCORE on a reserved frame still needs the committed gate sha. The list vintages 2020 and 2021
  (R-LV) stay reserved for every purpose.
- `efv_labels` keeps withholding R-VM labels on the list-vintage frame. A successor
  registration may open them for its own fits; this one does not.
- `efv_v2_serve.served_claim` and the served-score frame (`V2_FIRST_SCORED_YEAR` to
  `R_VM_FIRST_DEBUT_YEAR`) are unchanged.
- No projections retrain, no `backtest.run_backtest`, no fWAR epoch runbook step, no push.

## 3. The closed-window rule (no fit reads an open label)

A fit may read decision year y only when season y's label window is CLOSED, checked by
`efv_vintage_frame.label_window_closed(y)` at the moment the flag is read:

1. `y <= efv_dataset.RESOLVED_THROUGH` (the last fully played season of the label), and
2. the frozen fWAR vintage (`data/fwar_vintage.json`) holds season y with both groups frozen,
   and `fwar_vintage.season_complete(y, fetch date)` is True for the date each group was
   fetched (the regular season had ended before the freeze).

With the flag on and the rule failing for `TRAIN_THROUGH_SEASON`, `train_end_year()` raises
`ReservedFrameError` and no fit runs. A row whose decision year is after
`TRAIN_THROUGH_SEASON` (a bust last listed in 2026 carries decision year 2027) is never read.
Today the rule holds for 2026: `RESOLVED_THROUGH = 2026` and the vintage
`2026-10-02-0341299c20ec` froze 2026 on 2026-10-02, after the regular season ended 2026-09-27.

## 4. Claims: the 2026 frame stays spent

- The 2026 holdout frames (F-2026-LIST, F-2026-DEBUT) are SPENT. No model is ever claimed on
  them, and a model fitted with the flag on trained on them.
- R-VM look 2 and look 3 (career WAR on the 2025 and 2026 debut cohorts, the O'Brien-Fleming
  schedule of `EFV_V2_GATE.md` s2.2) can adjudicate only a model that did NOT train on those
  cohorts. A model fitted with the flag on is not eligible for them.
- Any later "beats consensus" claim for a model fitted with the flag on names a frame the
  model did not train on: the 2027 season (the preseason 2027 lists scored on 2027
  regular-season WAR, and the 2027 debut class), read once under its own registration
  committed before the read.
- Development reads on the opened rows are development rows (role development) and
  adjudicate nothing.

## 5. What the task reports (counts and arithmetic only, no rater scored)

- Rows gained per side: the training pool (after v1's pool rule) with the flag on minus the
  pool with it off, by decision year.
- The change in the minimum detectable effect of the forward-chained development read: the
  published floor `data/xfv_mde_floor.json` (weighted, one-sided and two-sided) rescaled by the
  sqrt rule `PROGRAM.md` s2.5 and `LABEL_HORIZON_2026.md` s3 already use,
  `mde95_after = mde95_before x sqrt(W_before / W_after)`, where W is the pair-weight mass
  (sum of observed_seasons / 6) of the debuted rows a forward-chained read can score: decision
  years 2014 through 2024 today, 2014 through 2026 with the flag on. Also the row-count
  version. It is arithmetic on a published sd, not a measured floor, and it applies to
  development selection only: the 2025 and 2026 rows can never be a claim frame.

## 6. Tests (`test_efv_2026_fold.py`)

- Flag off: `train_end_year()` is 2025, `_check_years` refuses 2025 as before, `_matrix_path`
  is the served matrix, the training pool and the production training rows are identical to
  the incumbent's, and the guards' messages and pins are unchanged.
- Flag on: the pool gains exactly the 2025 and 2026 debut-class rows, no row has a decision
  year after 2026, `_check_years` admits 2025 and 2026 and refuses 2027, and `reserved_vm_pins()`
  is still empty.
- Flag on with an open window (a label resolved only through 2025, or a vintage whose 2026
  groups were fetched before the regular season ended): `train_end_year()` raises and no fit
  reads a row.
- The served claim and the served-score year range do not move with the flag.
- The source names no consensus-FV cell.

## 7. Implementation and receipt (appended 2026-10-15, after the code)

Code: `efv_vintage_frame.py` (the flag, `TRAIN_THROUGH_SEASON`, `label_window_closed`,
`train_end_year`, `fold_matrix_path`, `training_matrix_path`), `efv_v2_model.py`
(`_matrix_path` reads the fold matrix with the flag on; `_check_years` reads
`train_end_year`), the production training filters of `efv_v2_serve.py`, `efv_v3.py`,
`efv_v4.py`, `efv5_group_drivers.py` and `efv5_combined.py`, the vintage-matched column
builders `efv5_group_drivers.vm_columns` and `efv5_combined.tool_vm_columns`, the tool
`efv_2026_fold.py` and the tests `test_efv_2026_fold.py`.

One departure from s1, disclosed: `efv5_combined.production_train` REFUSES with the flag on
(NotImplementedError) instead of fitting. Its group and tool columns read the 2025 and 2026
rows, but the v4 and scouting families (population translation, scouting index, IL, NRI,
play-by-play, rater panel, report reads) cap every read at the R-VM cohort, so a v5 COMBINED
fit through 2026 would train on columns silently missing on the new rows. A model registered
with the flag (EFV_X3 or a successor) wires its own builders, or a later task extends these.
The V2 production fit (`efv_v2_model.fit_v2` on the pool) runs with the flag on.

Receipt (`data/_labs/efv2026/efv_2026_fold_training.json`, `python efv_2026_fold.py --build
--report`): the fold matrices add 94 hitter and 119 pitcher rows, every one a 2026 debut, and
every shared row is identical to the served matrix. The production training pool grows from
1,889 to 2,079 hitter rows (+96 at decision year 2025, +94 at 2026) and from 1,981 to 2,218
pitcher rows (+118, +119); no row is lost and the largest decision year read is 2026. The
development read's scored mass (debuted rows, decision years 2014 on) grows from 782 rows and
pair-weight mass 684.167 to 972 and 731.833 (hitters) and from 907 and 788.5 to 1,144 and
847.667 (pitchers). On the published weighted floor that moves the one-sided mde95 from
0.0321 to 0.0310 (mass rule; 0.0288 by rows) for hitters and from 0.0281 to 0.0271 (0.0250 by
rows) for pitchers; the two-sided mde95 from 0.0383 to 0.0370 (0.0344) and from 0.0335 to
0.0323 (0.0298). Arithmetic on a published sd, development selection only. With the flag off
the served production models are byte-identical to the incumbent's (sha256 of the serialized
fits c62ec1a7 before and after the change).
