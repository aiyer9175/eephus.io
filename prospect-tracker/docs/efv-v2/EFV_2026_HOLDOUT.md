# eFV on the 2026 season: the one holdout read (method, fixed before any number)

Written 2026-10-15 (task EFV_2026_HOLDOUT_READ) under the owner's decision EW3-13 of
2026-10-15 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, verbatim: "The 2026 season is
resolved (we're only scoring the regular season where WAR is accumulated), please use it to
improve eFV further"; asked how, the owner chose TEST ONCE, THEN TRAIN) and the waiver of
registered dates EW3-5 (2026-10-14). This document is committed ALONE, before the module
`efv_2026_holdout.py` exists and before any number is read: it fixes the frames, the labels,
the raters, the statistic, the seed, the pass rule and what the site may say under each
verdict. Sections 1 to 10 are written before the read; the run appends section 11 (the
numbers) and section 12 (the verdict). No em-dashes. Nothing here, in its code or in its
artifacts, is cut by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`, binding): the only
groups are side, list year and debut class.

## 1. What this read is, and why it is clean

Every eFV number so far was read on frames whose outcomes some earlier model had already
seen. The 2026 regular season ended on 2026-09-27 and its fWAR is frozen in the label
vintage `fwar@2026-10-02-0341299c20ec` (`data/fwar_vintage.json`). No eFV version was ever
scored against how the preseason-2026 prospects did in 2026. Scoring the current raters
ONCE on that season, with every input frozen at the 2026 opening day, is the cleanest
beat-consensus test available. After the read the frame is SPENT (section 9) and the next
task (EFV_2026_FOLD_TRAINING) may train on it; no later model is ever claimed on it.

The owner waived, for these reads only, the R-VM rule that look 2 of the 2025 and 2026
debut cohorts waits for the 2027 season (EW3-5, EW3-13). The waiver is recorded as a dated
amendment to `docs/efv-v2/EFV_V2_GATE.md`, committed after this document and before any
number. The R-VM cohorts are opened through `efv_vintage_frame.guard_vm_request` on the
gate's committed sha `e7931ce4e13110eebb53555bff455ff13ca7c502`, exactly as the v3, v4 and
v5 spent reads opened them; `source_backtest.CANDIDATE_YEARS` and
`efv_model.SCORED_YEARS` are not widened (`reserved_vm_pins()` stays empty).

## 2. The cutoff

CUTOFF = 2026-03-25, the 2026 opening day. Every rater input is dated on or before it:
board points (snapshot dates), per-source grades, the MiLB lines read (seasons through
2025), injured-list stints (before 2026-01-01, the list year's start, as on the list-vintage
frame), acquisitions (known before 2026), body mass (as of the row's as-of point), and the
v5 COMBINED candidate columns (built as of the cutoff, section 4). Nothing dated after the
cutoff enters any score.

## 3. The frames

### 3.1 F-2026-LIST (primary)

One row per (player, side): every prospect on a PRESEASON 2026 list. The construction is
the list-vintage frame of `efv_vintage_frame.frame_row` at V = 2026 with its window
[2026-01-01, 2026-03-26) (the latest board point per source dated on or before the cutoff;
nothing later), unchanged otherwise:

- a real grader (a source other than the non-rater and constant-anchor sources) PUBLISHED a
  grade inside the window (a grade carried forward from an earlier board stays an input but
  cannot put a player in the frame on its own);
- not in the frame when a published debut precedes the window or the record's id carries a
  MLB (sport-1) line in any season before 2026;
- side routing by `efv_dataset._side_match`;
- a row needs a consensus grade at its as-of point (the latest in-window point);
- every input keyed on the OUTCOME-BLIND id (`efv_identity` through 2025, DS-03, bug B4);
  the record's own id is read only by the labels (section 5).

The MiLB block reads at `efv_dataset.MILB_FLOOR_DEFAULT` on both sides, the floor of the
served live board (the board this read reproduces), not the list-vintage lift.

Group: (side, 2026). Clubs for the club-clustered interval: the org on the row's as-of board
point, `UNK` when it carries none.

### 3.2 F-2026-DEBUT (secondary)

One row per (player, side): every player whose effective debut year
(`efv_labels.effective_debut` on the frozen label, status ok) is 2025 or 2026, with a
consensus grade at a board point dated in [2025-01-01, 2026-03-26); his as-of point is the
latest such point. The 2025 debut class is scored on its 2026 season, the 2026 debut class
on its first season. Inputs are built as in 3.1 (the window is [2025-01-01, 2026-03-26),
the MiLB block reads seasons through 2025, the IL cut is 2026-01-01). Group: (side, debut
class). This frame conditions on reaching the majors (the vintage-matched shape): it is a
secondary read, reported with intervals, and adjudicates nothing.

## 4. The raters (each frozen as of the cutoff)

1. **eFV v5 COMBINED, served** (`efv5_combined`, `EFV_V5_COMBINED_ON = True` since EW3-10).
   Its production fit (`efv5_combined.production_fit`, every matrix row with a decision year
   before 2025, the registered head weights of `data/efv_v2_assembly.json`) is REBUILT on a
   training pool whose labels stop at the 2025 season (section 4.1), so the fit reads no
   2026 data. Its candidate columns are built for the frame rows by
   `efv5_combined.live_columns(today = 2026-03-25)` (read year 2027, read season 2025,
   scouting and invitation indexes capped at the cutoff plus one day, IL stints cut at the
   read, the population translator fitted only on label windows closed before 2026 with
   every frame player left out of it, the training-support clip of the served path). The
   score is the order index of `efv_v2_model.predict_v2` on the rows, exactly the call
   `efv_v2_serve.score_live` makes; the tracking-era head is not applied (its served flag,
   `EFV_TRACKING_HEAD_ON`, is False).
2. **eFV V2**: `efv_v2_model.fit_v2` (frame vm) on the same truncated pool, its order index
   (the fit `efv_v2_serve.production_models` serves with the v5 flag off).
3. **eFV v1**: `efv_v2_model.v1_fold_scorer` on the same truncated pool (v1's consensus leg
   and calibrated ridge leg at its pinned blend lambda), its WAR-scale blend.
4. **PROSPX consensus**: the consensus grade of the row's as-of point.
5. **MLB Pipeline** and 6. **FanGraphs**: each source's grade on the latest point inside the
   window that carries a grade of that source (the largest when two points share that
   date), so the latest board point per source on or before the cutoff.

### 4.1 The training pool with no 2026 data

The v1 matrices (`data/xfv_hitter_matrix.json`, `data/xfv_pitcher_matrix.json`) carry
labels at RESOLVED_THROUGH 2026. The read rebuilds, in memory, a copy whose labels stop at
2025: every debuted row's six-season label is recomputed by `efv_dataset._label_6yr` at
RESOLVED_THROUGH 2025 from the same `career_war` seasons the matrix was built from, a
career-terminal transaction resolves a row only when dated on or before the cutoff, and a
recent-bust row resolved by a terminal transaction after the cutoff is restored to its
recent-bust state. The copy is checked first: at RESOLVED_THROUGH 2026 the recomputation
must reproduce the matrix's own labels (the receipt counts any row that does not). Feature
columns are not touched (every matrix feature is dated at the row's own cutoff, before
2025). The copy is handed to the fits through `efv_dataset.matrix_path` for the life of the
run and written only under `data/_labs/efv2026/`. Disclosed, not repaired: a player who left
the lists by 2023 and first reached the majors in 2026 was a bust as of the cutoff but has no
row in the matrices (the bust loop drops a record with MLB exposure); the receipt counts
them. Any training row whose player is in a frame of this read is left out (counted;
expected 0 by construction).

### 4.2 What is NOT frozen at the cutoff (disclosed)

The models' structure was chosen in 2026-10 on labels that include 2026 seasons of OTHER
players and, for the v5 metric atlas, the 2025 and 2026 debut events of earlier season rows
(the atlas's spent `reserved_overlap` cells): v5 COMBINED's candidate list and sign
constraints, the registered head weights (re-derived 2026-10-04 on the frozen fWAR label),
V2's admission rule and v1's pinned lambda. These are constants of the models as served,
kept as they are; any tilt they carry runs toward eFV, so an eFV lead is read with it and a
deficit is not excused by it.

## 5. The labels (regular season only)

- **R2026**: 1 when the player reached MLB in the 2026 regular season: effective debut year
  2026 (`efv_labels.effective_debut` on the record's id, the frozen label's seasons and the
  2026 sport-1 regular-season lines), else 0. An `identity_conflict` (or an effective debut
  before 2026 on F-2026-LIST) leaves the row out of every label, counted. ARRIVAL only,
  never value.
- **WAR2026**: the player's 2026 regular-season fWAR on the frozen label (hitting plus
  pitching war of the record's id in `fwar_vintage.season_totals()` at season 2026; a
  debutant with no published row reads 0.0, counted); 0.0 for a non-debutant on
  F-2026-LIST. On F-2026-DEBUT every row's 2026 fWAR, 0.0 when he logged none.
- **Rate (secondary, debutants only)**: WAR2026 per 600 PA for hitters and per 150 IP for
  pitchers, PA and IP from the 2026 sport-1 regular-season lines of the record's id on the
  row's side; rows with no PA or IP on their side are left out.
- **MiLB2026 (descriptive)**: the 2026 level-relative production composite of
  `efv_surrogate` (S3 PERF). It is read only through that module's public path and its
  guard (`efv_surrogate_guard.guard_surrogate_read`, the surrogate gate's own schedule).
  If the guard refuses, the composite is NOT computed here, the refusal is recorded
  verbatim, and the owner is asked whether to open it (the surrogate gate's frames are its
  own registered frames and are not read around their guard).

The frozen label is checked by id before any read: `fwar_vintage.load()["vintage_id"]` must
equal `2026-10-02-0341299c20ec`.

## 6. The statistic

- **Within-side Spearman** (primary, `efv_v2_stat` convention): inside each group of at
  least 20 rows, the Spearman rho of each rater's OWN score against the label (average
  ranks for ties); pooled over the groups weighted by row count. On F-2026-LIST the groups
  are the two sides of 2026, so the pooled figure is the size-weighted mean of the hitter
  and pitcher rho.
- **Within-side AUC** (R2026, arrival): the same, with the AUC of the rater's own score
  for R2026 in each side.
- **Deltas**: rater minus PROSPX consensus on IDENTICAL rows (the rows where both score).
  Also eFV v5 COMBINED minus eFV V2. Pipeline and FanGraphs are compared with consensus on
  their own graded rows; all six raters are also reported on the common set (both
  Pipeline and FanGraphs graded).
- **Intervals**: percentile bootstrap, B = 4000, seed 20261021, scores fixed, paired (every
  rater and statistic read on the same draws):
  - player-clustered: a player is one cluster (`source_backtest._cluster_layout` and
    `_cluster_draw`);
  - club-clustered: a club (the as-of org) is one cluster with every row it holds.
  Each delta reports the one-sided 95 percent lower bound (the 5th percentile of the drawn
  deltas), the one-sided 95 percent upper bound (the 95th) and the two-sided CI95, under
  each clustering. In a draw a group whose rho is undefined for either rater is left out
  for both.
- Never by consensus-FV level (`docs/PROSPECT_ANCHOR_GATE.md`): no statistic, count or
  stratum is cut by a consensus-FV cell; the module's tests scan its source.

## 7. The pass rule (registered here, before any number)

**eFV beats consensus on the 2026 holdout iff the one-sided 95 percent lower bound of
(served eFV v5 COMBINED minus PROSPX consensus), within-side Spearman on WAR2026, pooled
over the two sides of F-2026-LIST, is above 0 under BOTH the player-clustered and the
club-clustered bootstrap.**

Verdict words, on that same leg:

- **beats**: both lower bounds above 0;
- **trails**: both one-sided 95 percent UPPER bounds below 0;
- **ties**: anything else.

R2026 is reported as an ARRIVAL read (tilted toward a model with a timing head), never as
value; F-2026-DEBUT, the rate label and MiLB2026 are secondary or descriptive. None of them
changes the verdict.

## 8. What the site may say under each verdict

No served number moves under any verdict: the board, grades, dollars, odds and the served
claim (`efv_v2_serve.served_claim`, which reads only reserved looks and the headline frame)
are untouched. The read lands as ONE row in `data/efv_progress.json` (frame `holdout_2026`,
role `holdout_2026`, registered in `efv_progress.FRAMES`, never charted, never claimable by
the served claim), carrying the WAR2026 within-side Spearman legs and the verdict word.

- **beats**: the Source Comparison copy changes ONLY after the owner answers a flip question
  (recorded in the results); until then it keeps "ties consensus".
- **ties**: the copy stays "ties consensus".
- **trails**: the copy stays as it is; the owner is asked whether the copy should disclose
  the holdout deficit.

## 9. One read, then spent

The read runs ONCE: `python -u efv_2026_holdout.py --run` refuses while
`data/efv_2026_holdout.json` exists. A build that aborts before any statistic is computed
may be rerun and is disclosed. After the read a dated note in `docs/efv-v2/EFV_V2_GATE.md`
marks F-2026-LIST and F-2026-DEBUT SPENT: the 2026-season outcomes of the preseason-2026
list and of the 2025 and 2026 debut classes are never again a holdout for any model.
EFV_2026_FOLD_TRAINING may then train on them.

## 10. Bans, artifacts and code

- No projections retrain; the fWAR label epoch's runbook is untouched;
  `backtest.run_backtest` is never called; nothing is pushed.
- Code: `efv_2026_holdout.py` (module root), tests `test_efv_2026_holdout.py`.
- Artifacts: `data/efv_2026_holdout.json` (every frame, rater, statistic, interval, the
  verdict and the receipts, no per-player row), `data/_labs/efv2026/efv_2026_holdout_rows.json`
  (the per-row scores and labels, not shipped), one row in `data/efv_progress.json`, and
  `docs/efv-v2/EFV_2026_HOLDOUT_RESULTS.md` in plain language.

## 11. The read (appended by the run, 2026-10-15)

Run: `python -u efv_2026_holdout.py --run` from commit c5285660 (artifact `data/efv_2026_holdout.json`, generated 2026-10-15T19:42:40Z; per-row file `data/_labs/efv2026/efv_2026_holdout_rows.json`; label `fwar@2026-10-02-0341299c20ec`; build 182.2 s). The read ran once; no build aborted. B 4000, seed 20261021.

### 11.1 Frames and receipts

- F-2026-LIST: 1208 rows (hitters 590, pitchers 618); every frame row carried a consensus and none was constant-anchor only. R2026 = 1 on 78 hitters and 89 pitchers; no identity conflict; every debutant carried a published 2026 fWAR row. Outcome-blind ids resolved on 522 of 590 hitters and 570 of 618 pitchers (a row without one reads no MiLB block, as on every list-vintage frame).
- F-2026-DEBUT: 363 rows (hitters 161 of 209 class members, pitchers 202 of 273; the rest had no real-grader board read in the window). 11 hitters and 18 pitchers carry no 2026 fWAR row (2025 debuts who did not play in the 2026 majors) and read 0.0.
- Training pool (s4.1): at RESOLVED_THROUGH 2026 the recomputation reproduced the matrices' labels on every row (0 mismatches on both sides). At 2025, 385 hitter and 453 pitcher rows changed label; 3 and 2 rows stayed terminal-resolved (no terminal transaction fell after the cutoff) and no recent-bust row was restored. The matrices held 87 hitter and 131 pitcher rows of players in a frame, every one at decision year 2025 (2025 debuts) or 2027 (busts last listed in 2026), outside every fit; the fits trained on 1,889 hitter and 1,981 pitcher rows, the served production counts. Players who left the lists by 2023 and first reached the majors in 2026: 0. The truncated copies (`data/_labs/efv2026/train_matrix_*_rt2025.json`, not tracked) had sha256 d9457745c50d7d28468634b521b9604e6f2e89fa331893c8a04da3b73d81b26b (hit) and a18a85896e5260c5172c4bfa39d9bbbe3d3117e88181ce2960e3bb8d1dddc462 (pit).
- Fits: v5 COMBINED lambda skill / timing, hitters 1000.0 / 300.0, pitchers 1000.0 / 100.0 (the served production fit chose the same, 1000 / 300 and 1000 / 100). V2 pitchers take the consensus order (no admitted skill driver, owner DS-Q2), so V2 equals consensus on every pitcher.
- v5 COMBINED candidate columns as of 2026-03-25 (hitters of F-2026-LIST): group partial; il drift; nri dark; pbp lit; pbp_bb lit; popmle lit; raters dark; report dark; w2s lit. `predict_v2` and `predict_combined` agree on every row (max difference 0).
- MiLB2026: NOT computed. The surrogate guard refused: "surrogate lv2026_surrogate read of V 2026 refused: needs the sha of the commit carrying docs/efv-v2/SURROGATE_2026_GATE.md marked REGISTERED, got '27b5353458cff0a8d38e2f3dc935b28bf293f2fc' (SURROGATE_2026_GATE.md s2.3)."

### 11.2 F-2026-LIST, WAR2026, within-side Spearman (the registered statistic)

| rater | hitters | pitchers | pooled |
|---|---|---|---|
| eFV v5 COMBINED (served) | 0.1803 (n 590) | 0.0845 (n 618) | 0.1313 (n 1208) |
| eFV V2 | 0.1733 (n 590) | 0.0731 (n 618) | 0.1220 (n 1208) |
| eFV v1 | 0.1677 (n 590) | 0.0782 (n 618) | 0.1219 (n 1208) |
| PROSPX consensus | 0.1674 (n 590) | 0.0731 (n 618) | 0.1192 (n 1208) |
| MLB Pipeline | 0.2356 (n 323) | 0.0571 (n 262) | 0.1557 (n 585) |
| FanGraphs | 0.2004 (n 533) | 0.0992 (n 575) | 0.1479 (n 1108) |

Deltas on identical rows (one-sided 95 percent lower and upper bounds, player-clustered / club-clustered; two-sided CI95 player-clustered):

| leg | n | delta | lb95 player / club | ub95 player / club | CI95 (player) |
|---|---|---|---|---|---|
| pooled: eFV v5 COMBINED minus consensus | 1208 | +0.0121 | -0.0073 / -0.0067 | +0.0312 / +0.0307 | [-0.0108, +0.0348] |
| pooled: eFV V2 minus consensus | 1208 | +0.0029 | -0.0142 / -0.0111 | +0.0204 / +0.0172 | [-0.0172, +0.0241] |
| pooled: eFV v1 minus consensus | 1208 | +0.0027 | -0.0110 / -0.0081 | +0.0167 / +0.0143 | [-0.0137, +0.0193] |
| pooled: eFV v5 COMBINED minus eFV V2 | 1208 | +0.0093 | -0.0018 / -0.0007 | +0.0205 / +0.0195 | [-0.0039, +0.0229] |
| pooled: Pipeline minus consensus (Pipeline-graded rows) | 585 | -0.0254 | -0.0640 / -0.0619 | +0.0134 / +0.0126 | [-0.0715, +0.0207] |
| pooled: FanGraphs minus consensus (FanGraphs-graded rows) | 1108 | +0.0282 | +0.0052 / +0.0105 | +0.0520 / +0.0470 | [+0.0004, +0.0569] |
| hit: eFV v5 COMBINED minus consensus | 590 | +0.0129 | -0.0203 / -0.0158 | +0.0455 / +0.0440 | [-0.0259, +0.0532] |
| hit: eFV V2 minus consensus | 590 | +0.0058 | -0.0290 / -0.0222 | +0.0418 / +0.0363 | [-0.0356, +0.0496] |
| hit: eFV v1 minus consensus | 590 | +0.0003 | -0.0192 / -0.0174 | +0.0200 / +0.0195 | [-0.0228, +0.0239] |
| hit: eFV v5 COMBINED minus eFV V2 | 590 | +0.0070 | -0.0018 / -0.0007 | +0.0161 / +0.0142 | [-0.0036, +0.0177] |
| hit: Pipeline minus consensus (Pipeline-graded rows) | 323 | -0.0225 | -0.0655 / -0.0636 | +0.0204 / +0.0262 | [-0.0757, +0.0284] |
| hit: FanGraphs minus consensus (FanGraphs-graded rows) | 533 | +0.0297 | -0.0033 / -0.0028 | +0.0634 / +0.0628 | [-0.0096, +0.0704] |
| pit: eFV v5 COMBINED minus consensus | 618 | +0.0114 | -0.0089 / -0.0058 | +0.0319 / +0.0288 | [-0.0125, +0.0365] |
| pit: eFV V2 minus consensus | 618 | +0.0000 | +0.0000 / +0.0000 | +0.0000 / +0.0000 | [+0.0000, +0.0000] |
| pit: eFV v1 minus consensus | 618 | +0.0051 | -0.0158 / -0.0109 | +0.0254 / +0.0217 | [-0.0200, +0.0291] |
| pit: eFV v5 COMBINED minus eFV V2 | 618 | +0.0114 | -0.0089 / -0.0058 | +0.0319 / +0.0288 | [-0.0125, +0.0365] |
| pit: Pipeline minus consensus (Pipeline-graded rows) | 262 | -0.0289 | -0.0969 / -0.0928 | +0.0407 / +0.0307 | [-0.1084, +0.0535] |
| pit: FanGraphs minus consensus (FanGraphs-graded rows) | 575 | +0.0267 | -0.0060 / -0.0067 | +0.0601 / +0.0635 | [-0.0128, +0.0664] |
| common set: eFV v5 COMBINED (served) minus consensus | 570 | -0.0131 | -0.0421 / -0.0332 | +0.0155 / +0.0090 | [-0.0469, +0.0203] |
| common set: eFV V2 minus consensus | 570 | -0.0149 | -0.0406 / -0.0321 | +0.0104 / +0.0039 | [-0.0461, +0.0157] |
| common set: eFV v1 minus consensus | 570 | +0.0057 | -0.0143 / -0.0073 | +0.0264 / +0.0198 | [-0.0185, +0.0294] |
| common set: MLB Pipeline minus consensus | 570 | -0.0252 | -0.0647 / -0.0622 | +0.0146 / +0.0129 | [-0.0722, +0.0214] |
| common set: FanGraphs minus consensus | 570 | +0.0141 | -0.0213 / -0.0143 | +0.0503 / +0.0452 | [-0.0272, +0.0564] |

### 11.3 F-2026-LIST, R2026 (ARRIVAL, tilted toward a model with a timing head; never value)

| leg | n | delta | lb95 player / club | ub95 player / club | CI95 (player) |
|---|---|---|---|---|---|
| pooled: eFV v5 COMBINED minus consensus (AUC) | 1208 | +0.0488 | +0.0344 / +0.0332 | +0.0638 / +0.0642 | [+0.0322, +0.0669] |
| pooled: eFV V2 minus consensus (AUC) | 1208 | +0.0487 | +0.0363 / +0.0376 | +0.0622 / +0.0603 | [+0.0342, +0.0646] |
| pooled: eFV v1 minus consensus (AUC) | 1208 | +0.0258 | +0.0141 / +0.0138 | +0.0376 / +0.0385 | [+0.0123, +0.0398] |
| pooled: Pipeline minus consensus (Pipeline-graded rows) (AUC) | 585 | -0.0346 | -0.0594 / -0.0577 | -0.0098 / -0.0112 | [-0.0650, -0.0054] |
| pooled: FanGraphs minus consensus (FanGraphs-graded rows) (AUC) | 1108 | +0.0108 | -0.0082 / -0.0076 | +0.0296 / +0.0287 | [-0.0114, +0.0330] |
| hit: eFV v5 COMBINED minus consensus (AUC) | 590 | +0.0954 | +0.0719 / +0.0724 | +0.1207 / +0.1180 | [+0.0680, +0.1249] |
| hit: eFV V2 minus consensus (AUC) | 590 | +0.0998 | +0.0747 / +0.0775 | +0.1269 / +0.1225 | [+0.0704, +0.1320] |
| hit: eFV v1 minus consensus (AUC) | 590 | +0.0128 | -0.0037 / -0.0048 | +0.0299 / +0.0296 | [-0.0070, +0.0329] |
| hit: Pipeline minus consensus (Pipeline-graded rows) (AUC) | 323 | -0.0033 | -0.0358 / -0.0327 | +0.0277 / +0.0257 | [-0.0419, +0.0339] |
| hit: FanGraphs minus consensus (FanGraphs-graded rows) (AUC) | 533 | -0.0086 | -0.0365 / -0.0321 | +0.0182 / +0.0138 | [-0.0418, +0.0232] |
| pit: eFV v5 COMBINED minus consensus (AUC) | 618 | +0.0043 | -0.0118 / -0.0127 | +0.0208 / +0.0208 | [-0.0147, +0.0244] |
| pit: eFV V2 minus consensus (AUC) | 618 | +0.0000 | +0.0000 / +0.0000 | +0.0000 / +0.0000 | [+0.0000, +0.0000] |
| pit: eFV v1 minus consensus (AUC) | 618 | +0.0383 | +0.0225 / +0.0189 | +0.0546 / +0.0610 | [+0.0193, +0.0577] |
| pit: Pipeline minus consensus (Pipeline-graded rows) (AUC) | 262 | -0.0731 | -0.1139 / -0.1144 | -0.0344 / -0.0286 | [-0.1223, -0.0283] |
| pit: FanGraphs minus consensus (FanGraphs-graded rows) (AUC) | 575 | +0.0288 | +0.0033 / +0.0036 | +0.0554 / +0.0540 | [-0.0031, +0.0607] |

Own AUC, pooled over sides: eFV v5 COMBINED (served) 0.7259 (n 1208); eFV V2 0.7258 (n 1208); eFV v1 0.7030 (n 1208); PROSPX consensus 0.6771 (n 1208); MLB Pipeline 0.6157 (n 585); FanGraphs 0.6793 (n 1108).

### 11.4 Secondary reads (adjudicate nothing)

Rate (WAR2026 per 600 PA or 150 IP, debutants of F-2026-LIST only), within-side Spearman:

| leg | n | delta | lb95 player / club | ub95 player / club | CI95 (player) |
|---|---|---|---|---|---|
| pooled: eFV v5 COMBINED minus consensus | 167 | -0.0148 | -0.0643 / -0.0635 | +0.0363 / +0.0320 | [-0.0748, +0.0460] |
| pooled: eFV V2 minus consensus | 167 | -0.0292 | -0.0691 / -0.0659 | +0.0087 / +0.0076 | [-0.0783, +0.0149] |
| pooled: eFV v1 minus consensus | 167 | -0.0041 | -0.0404 / -0.0400 | +0.0304 / +0.0302 | [-0.0468, +0.0360] |
| pooled: Pipeline minus consensus (Pipeline-graded rows) | 132 | -0.0023 | -0.0735 / -0.0690 | +0.0732 / +0.0679 | [-0.0893, +0.0863] |
| pooled: FanGraphs minus consensus (FanGraphs-graded rows) | 163 | +0.0441 | -0.0181 / -0.0142 | +0.1077 / +0.1070 | [-0.0285, +0.1219] |
| common set: eFV v5 COMBINED (served) minus consensus | 131 | -0.0680 | -0.1255 / -0.1141 | -0.0120 / -0.0159 | [-0.1376, -0.0028] |
| common set: eFV V2 minus consensus | 131 | -0.0497 | -0.1021 / -0.0944 | -0.0000 / +0.0001 | [-0.1164, +0.0092] |
| common set: eFV v1 minus consensus | 131 | -0.0000 | -0.0374 / -0.0272 | +0.0367 / +0.0308 | [-0.0453, +0.0438] |

F-2026-DEBUT, WAR2026, within (side, debut class) Spearman:

| leg | n | delta | lb95 player / club | ub95 player / club | CI95 (player) |
|---|---|---|---|---|---|
| class pooled: eFV v5 COMBINED minus consensus | 363 | +0.0325 | +0.0003 / +0.0063 | +0.0632 / +0.0589 | [-0.0050, +0.0693] |
| class pooled: eFV V2 minus consensus | 363 | +0.0166 | -0.0131 / -0.0098 | +0.0454 / +0.0428 | [-0.0176, +0.0516] |
| class pooled: eFV v1 minus consensus | 363 | +0.0069 | -0.0161 / -0.0109 | +0.0287 / +0.0251 | [-0.0212, +0.0329] |
| class pooled: Pipeline minus consensus (Pipeline-graded rows) | 291 | -0.0360 | -0.0795 / -0.0794 | +0.0114 / +0.0143 | [-0.0892, +0.0206] |
| class pooled: FanGraphs minus consensus (FanGraphs-graded rows) | 355 | +0.0286 | -0.0069 / -0.0010 | +0.0647 / +0.0602 | [-0.0134, +0.0711] |
| class 2025: eFV v5 COMBINED minus consensus | 180 | +0.0685 | +0.0205 / +0.0271 | +0.1149 / +0.1060 | [+0.0110, +0.1246] |
| class 2025: eFV V2 minus consensus | 180 | +0.0520 | +0.0076 / +0.0085 | +0.0948 / +0.0908 | [-0.0008, +0.1044] |
| class 2025: eFV v1 minus consensus | 180 | +0.0258 | -0.0067 / -0.0041 | +0.0573 / +0.0512 | [-0.0123, +0.0636] |
| class 2025: Pipeline minus consensus (Pipeline-graded rows) | 148 | -0.0553 | -0.1119 / -0.1083 | +0.0069 / +0.0042 | [-0.1245, +0.0197] |
| class 2025: FanGraphs minus consensus (FanGraphs-graded rows) | 176 | +0.0340 | -0.0128 / -0.0069 | +0.0810 / +0.0671 | [-0.0215, +0.0909] |
| class 2026: eFV v5 COMBINED minus consensus | 183 | -0.0030 | -0.0441 / -0.0391 | +0.0373 / +0.0355 | [-0.0532, +0.0464] |
| class 2026: eFV V2 minus consensus | 183 | -0.0182 | -0.0568 / -0.0514 | +0.0182 / +0.0198 | [-0.0633, +0.0259] |
| class 2026: eFV v1 minus consensus | 183 | -0.0116 | -0.0428 / -0.0378 | +0.0178 / +0.0181 | [-0.0500, +0.0236] |
| class 2026: Pipeline minus consensus (Pipeline-graded rows) | 143 | -0.0160 | -0.0839 / -0.0768 | +0.0558 / +0.0533 | [-0.0981, +0.0687] |
| class 2026: FanGraphs minus consensus (FanGraphs-graded rows) | 179 | +0.0232 | -0.0305 / -0.0267 | +0.0779 / +0.0802 | [-0.0410, +0.0880] |

Own within Spearman, pooled: eFV v5 COMBINED (served) 0.3066 (n 363); eFV V2 0.2907 (n 363); eFV v1 0.2810 (n 363); PROSPX consensus 0.2741 (n 363); MLB Pipeline 0.3001 (n 291); FanGraphs 0.3065 (n 355).

## 12. The verdict (the rule of s7)

Served eFV v5 COMBINED minus PROSPX consensus, within-side Spearman on WAR2026, pooled sides of F-2026-LIST (n 1208): +0.0121; one-sided 95 percent lower bound -0.0073 player-clustered and -0.0067 club-clustered; upper bound +0.0312 and +0.0307. Neither lower bound is above 0 and neither upper bound is below 0: **ties**. eFV does NOT beat consensus on the 2026 holdout; no served number moves and the Source Comparison copy keeps "ties consensus". One row landed in `data/efv_progress.json` (frame `holdout_2026`, role `holdout_2026`, verdict `ties`, not charted, not read by the served claim). The frame is SPENT (dated note in `docs/efv-v2/EFV_V2_GATE.md`).
