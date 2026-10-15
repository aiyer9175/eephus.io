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
