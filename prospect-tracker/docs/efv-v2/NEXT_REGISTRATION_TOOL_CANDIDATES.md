# Tool-family candidates for the next eFV registration (TL_16)

Written 2026-10-15 by TL_16_EFV_TOOL_DEV_ADMISSION (Part 9 PLAN section 9.4.5 'Tools as eFV
drivers'; LANE_C.md section 2.7, route (a)). Owner ask of 2026-10-01, message 2's last
sentence, verbatim: 'After doing so, if this proves to improve tool grade accuracy, can we
then check if tool grades can be used as eFV drivers / how they should be weighted?'
Route: owner answer TL-Q1 (a) 'Next registration' (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`).
This document adjudicates nothing and moves nothing served: the served eFV grade does not
change.

## 0. Why this may run at all

The eFV feature frontier is closed (plan Part 2; the 2026-08-14 closure, 39 arms, zero
survivors) and game power failed as an eFV driver four times (the Phase 1 partial, D-1
tool_game_pwr -0.0047, the C3 power pairs, iso_rel 0 of 11 folds; `data/xfv_arm_ledger.json`);
nothing here re-runs a spent arm. The columns are NEW (a power composite chosen on realized
ISO by a registered look, a tool-implied ISO residual, the inputs of an accuracy-weighted hit
consensus) and exist on the owner's 2026-10-01 asks.

## 1. The result: the candidate list is EMPTY

No arm was admitted in every fold, so no tool-family column is pre-declared for the next
registration. The rule entered no head and nothing was fitted beyond the rule's own
single-column reads.

| arm | verdict | folds admitted (of 10) | where it failed |
|---|---|---|---|
| `TL:hit.skill.tool_hit_w` | REFUSED | 9 (lv 2017 to 2021, vm 2020 to 2023) | vm 2024: the 2023 training vintage gave t -0.0548 against five positive vintages (sign flipped) |
| `TL:hit.skill.tip_iso_resid` | REFUSED | 0 | lv 2017 to 2019 and vm 2020: fewer than 2 vintages give a t; lv 2020, 2021: mean abs t 0.362 and 0.355, below 1.0; vm 2021: 0.758, below 1.0; vm 2022 to 2024: sign flipped |
| `TL:hit.skill.pwr_comp` | NOT RUN | none | look P served C0 (not C2 with a below 1), so the column is the spent key D-1:tool_game_pwr:hit and is not a candidate |

Per fold, the training vintages that give a t and their t values (W3 percentile on [1,
consensus percentile, z(column)], has-block rows, at least 60 observing rows per vintage):

- `tool_hit_w`, lv folds. 2017: 2012 +2.33, 2014 +3.23, 2015 +3.99, 2016 +4.28 (mean abs t
  3.46). 2018: adds 2017 +0.68 (2.29). 2019: adds 2018 +2.37 (2.41). 2020: adds 2019 +1.95
  (2.42). 2021: adds 2020 +1.71 (2.31). Every vintage positive.
- `tool_hit_w`, vm folds. 2020: 2018 +0.86, 2019 +2.33 (1.59). 2021: adds 2020 +2.25 (1.83).
  2022: adds 2021 +0.89 (1.59). 2023: adds 2022 +0.96 (1.47). 2024: adds 2023 -0.05 (1.24,
  REFUSED on the flip).
- `tip_iso_resid`, lv folds. 2019: 2018 +0.33 only. 2020: 2018 +0.23, 2019 +0.49 (0.36).
  2021: adds 2020 +0.42 (0.35). Folds 2017 and 2018 have no vintage with 60 observing rows
  (the TIP table is computable from list vintage 2018).
- `tip_iso_resid`, vm folds. 2020: 2019 -0.74 only. 2021: adds 2020 -0.78 (0.76). 2022:
  adds 2021 +0.28 (flip). 2023 and 2024 keep the flip.

The artifact is `data/_labs/efv_tool_admission.json` (sha256
11448141d3ace559c4d193db2e630c181f2a07106818ada55c2556faa52caccc, generated
2026-10-15T12:23:36Z, code at `fa8da6eb` plus this task's uncommitted tool); the two arms and
their per-fold, per-vintage signs are rows of `data/xfv_arm_ledger.json` (role development;
400 to 402 arms, 11 to 12 lanes).

### 1.1 What the near miss of tool_hit_w is, read honestly

`tool_hit_w` is close to a column V2 already carries. On the lv folds its Spearman with the
admitted V2 column `tool_hit` over the observing training rows is 1.000, 0.9995, 0.9967,
0.9928 and 0.9889 (folds 2017 to 2021); on the vm folds, where the matrix `tool_hit` is a
different read, 0.785 to 0.848. In lv folds 2017 to 2019 the weights are flat (BA2's
estimator has no FanGraphs board year at or before V - 3, since FanGraphs tool grades start
in 2017), so there the column is the plain per-source mean, which is `tool_hit`'s own
ordering: its admission in those folds repeats `V2-LV:hit.skill.tool_hit` (ADMITTED in every
V2 fold) and is no new evidence. From fold 2020 the weights move Pipeline up (lv 2020:
FanGraphs 0.9488, Pipeline 1.0512 on 115 rows; vm 2024: 0.8464 and 1.1536 on 1,061 rows),
BA2's direction. Had every fold admitted it, the expected effect would still have been
+0.000 to +0.003 on the within statistic against about 0.03 resolvable on R-LV.

### 1.2 The owner's precondition, by candidate

- hit (`tool_hit_w`): look W (`docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md` Part 8,
  2026-10-14, an owner-waived early read) recorded hit NULL and the look VOID under W.7. Not
  a PASS: 'if this proves to improve tool grade accuracy' is NOT met for hit.
- the composite (`pwr_comp`): look P (same file, Part 8, 2026-10-14) served C0. No PASS for
  C1 or C2: NOT met.
- `tip_iso_resid`: no accuracy look applies (a production-beyond-grade residual, not a tool
  weight).

So the honest answer to the owner's question, on this registration's evidence: tool grades
already enter eFV through the hit tool (`tool_hit`, weighted inside the V2 skill head by the
ridge penalty and the DS-08 combiner, never by hand); an accuracy-weighted hit consensus did
not hold its sign in every fold and its tool-accuracy precondition is not met; the
tool-implied ISO residual never cleared the rule; the power composite is not a candidate.

## 2. Each candidate, defined exactly (for any later registration that names them)

- `tool_hit_w`: per row, sum over the row's sources of w_s times the source's hit grade,
  divided by the sum of w_s; the grade is each source's EARLIEST snapshot inside the row's
  frame window [V-01-01, min(V-05-01, debut day)) (`efv_tool_features.earliest_grades`); w is
  BA2's estimator (`tools/ba_tool_grade_lab.derive_weights`, imported, not retyped: Spearman
  floor 0.05, shrink K 150, clamp 0.6 to 1.5, flat under 60 rows) on FanGraphs and MLB
  Pipeline hit grades with the outcome BA2 uses (MLB AVG after the board year, MLB seasons
  before 2026 only), board years at most V - 3, players of the fold's frame left out; a
  source outside the two weighs 1.0; a row with no hit grade is None and imputes at the
  fold's observed training mean (no flag). It replaces `tool_hit` in the head for its own arm
  only; the rule reads one column at a time, so the replacement moves nothing it reads.
- `tip_iso_resid`: the PA-shrunk pre-V MiLB ISO at the frame block's level and season minus
  `tool_implied.tip_level` at that level for the game_pwr consensus, the TIP table fit on MLB
  ISO pooled to V - 1 of frame players who debuted before V, level norms and the AAA offset
  rebuilt per V from seasons V - 5 to V - 1 (`efv_tool_features.py`,
  `data/_labs/efv_tool_features.json`).
- `pwr_comp`: a candidate only if look P serves C2 with a below 1, its a cross-fitted per
  fold on board years up to V - 3 using players outside the fold, never the served a.

## 3. Frames, folds and label

- lv folds V 2017 to 2021, each on its own training vintages (list vintages below V, every
  player of the V frame left out, gate s4.5). List vintages 2020 and 2021 are read as
  development rows because the R-LV record exists: `docs/efv-v2/EFV_V3_BACKTEST.md` s5.1 at
  commit 1c73c420 (the reserved read of 2026-10-08), decision D-k3 (the TL2-Q1 reading;
  `EFV_V2_GATE.md` s9 stays empty by its s11); the guard opened on the committed gate sha
  e7931ce4e13110eebb53555bff455ff13ca7c502. The sidecar was extended to V 2020 and 2021 in
  this task (V 2011 to 2019 rows byte-identical in content).
- vm folds 2020 to 2024 on the v1 training matrices (decision years below 2025), training
  rows below the fold year as `tools/efv_v2_assemble.vm_folds` reads them; a matrix row takes
  the sidecar row of its latest list vintage V whose read window closed (V-05-01) on or
  before its as-of date (1,219 of 1,889 rows joined).
- Label: the frozen fWAR label `fwar@2026-10-02-0341299c20ec` (lv: W3 percentile within
  (side, V); vm: the matrix target percentile within decision year). On the lv training rows
  86 rows whose debut falls in a reserved cohort are kept at W3 = 0 exactly as the
  registered procedure keeps them (gate s5, B9b); none of their seasons is read.
- R-VM (the 2025 and later debut cohorts) is untouched: no matrix decision year at or after
  2025 and no sidecar row of such a debut enters. Nothing is grouped by consensus-FV level
  (`docs/PROSPECT_ANCHOR_GATE.md`); the only groupings are fold and training vintage.

## 4. The rule for the next registration

A tool-family column enters the next registration (V3 at the 2027 label epoch, or the next
registration `docs/efv-v2/PROGRAM.md` names) only if it is named in section 1 of this
document as admitted in every fold, and only by being written into that registration's
candidate list before its first read. Today that list is empty. A column refused here may
return only as a NEW pre-declaration with new evidence (for hit: a look W re-read that
records PASS under a new registration; for the composite: a look P that serves C2 with a
below 1), committed before the registration's first read, and it never re-runs on the frame
that refused it. Expected effect of the whole family, stated before any such read: +0.000 to
+0.003 on the within statistic, against about 0.03 resolvable on R-LV.

## 5. Defaults taken in this task

- TL-Q1 answered (a) in DECISIONS_FOR_OWNER.md; no default needed for it.
- The R-LV record read as decision D-k3 (EFV_V3_BACKTEST.md s5.1 counts).
- Look days waived by owner EW3-5 (2026-10-14); no look runs here.
- The rule runs in a new task tool, `tools/efv_tool_admission.py`, calling the same function
  as `tools/efv_driver_admission.py` (`efv_v2_model.admission_for_key`), the precedent of
  Q10_11's `tools/efv_pitch_rate_admission.py`; `data/xfv_driver_admission.json` is not
  rewritten.
- BA2's weights read FanGraphs and MLB Pipeline only (BA2's arm A; the sidecar carries no
  other dated hit grade), and MLB seasons before 2026 only (round 4, leakage 2).
- vm rows join the sidecar at the latest list vintage whose window closed before the row's
  as-of date.
