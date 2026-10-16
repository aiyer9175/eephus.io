# Baseball America kept as served, read forward (BA_KEEP_FORWARD_READ): the 2026 forward read, the 2023 Britton row, and the stale-vote rule, fixed before any number

Registration status: REGISTERED

Written 2026-10-16 (task BA_KEEP_FORWARD_READ) under the owner's decision EW3-39 of 2026-10-16
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), the answer to BA-1 of
`docs/efv-v2/BA_GRADE_IN_CONSENSUS.md` (sections 10 and 11, merged at c3516544): options (a) and
(d), KEEP the served basis (Baseball America's adjusted grade from 2026, its raw grade before) and
register a forward read. This document is committed ALONE, before the lab
`tools/ba_stale_vote_lab.py` exists and before any number of either read below is computed.
Part A is a forward registration and is read by a queued task (section A11). Part C is read once
by this task on development frames; the run appends section C11 (the numbers) and C12 (the
reading). No em-dashes. Nothing here, in its code or in its artifacts, is cut by consensus-FV cell
(`docs/PROSPECT_ANCHOR_GATE.md`, binding): the only groups are frame, side and year (list year or
debut year). No reserved row (R-LV list vintages 2020 and 2021, R-VM debut cohorts 2025 and later)
is scored by this task; `backtest.run_backtest` is never called.

## 0. What stays served

- `baseballamerica_csv.ADJUSTED_GRADE_FIRST_SEASON` stays 2026 and `fv_basis` is untouched: BA's
  `fv` is the published Adjusted Grade from 2026 and the BA Grade before. BA keeps its equal vote
  inside PROSPX consensus (`consensus.py`; `data/source_weights.json` carries no weights) and stays
  out of `source_backtest.SCORED_SOURCES`.
- No constant, flag, weight or served accuracy claim moves in this task unless the Part C read
  resolves under its own rule (section C10).

## Part A. The forward read: BA raw against risk-adjusted against excluded, inside consensus

### A1. Why forward

BA's published adjusted grade exists only from the 2026 boards (2026-02-15 preseason, 883 rows;
2026-08-05 Top 100; 2026-08-10 midseason). No development frame reaches it: BA's first board is
2023-02-15 and every development row BA reaches is a vm_dev 2023 row graded on BA's raw grade
(`BA_GRADE_IN_CONSENSUS.md` section 0). On those 166 rows the planted penalty check PL2 failed, so
the development frames cannot answer raw against adjusted (section 11 there). The answer needs a
2026 cohort whose outcome window has closed.

### A2. The cohort whose window closes first: leg 1, the 2026 debut cohort through 2028

- **Frame F-BA26-VM (leg 1, adjudicating).** One row per (player, side): every player whose
  effective debut year is 2026 (`efv_labels.effective_debut` on the frozen label, status ok), with
  a consensus grade at the latest consensus point inside his debut year's preseason window
  `efv_vintage_frame.window_bounds(2026, debut day)` = [2026-01-01, min(2026-05-01, debut day)).
  That point is the row's as-of point (the board as it stood). This is the consensus_present rule
  of the R-VM counts (`EFV_V2_GATE.md` amendment A6), the vintage-matched shape of vm_dev on which
  the development read ran. Side routing by `efv_dataset._side_match`. Group: side.
- **Label.** first3: the player's FanGraphs WAR summed over the 2026, 2027 and 2028 regular
  seasons on the frozen fWAR vintage (`fwar_vintage`, hitting plus pitching war of the record's
  id; a season with no published row reads 0.0, counted). For this cohort first3 IS career WAR to
  date at RESOLVED_THROUGH 2028, the R-VM label at its registered final boundary, and first3 is a
  registered secondary label view (`docs/efv-v2/LABEL_HORIZON_2026.md` section 5). Contributor
  flag for the secondary AUC: first3 at or above `source_backtest.CONTRIBUTOR_WAR` (3.0).
- **The window closes** when the 2028 season is frozen in the fWAR vintage after its end:
  `efv_vintage_frame.label_window_closed(2028)` returns closed and `efv_dataset.RESOLVED_THROUGH`
  is at least 2028. No 2026 cohort closes earlier on a value label: the list-vintage label W3 of
  the 2026 lists resolves at RESOLVED_THROUGH 2031 (leg 2), and the six-season label L6 of the
  2026 debut cohort at 2031 too.
- **Presence counted today (grade presence only, no grade value, no WAR, no label, as A6 counted;
  2026-10-16, on the debuts known today):** 79 hitters and 95 pitchers of the 2026 debut cohort
  carry a consensus at their as-of point (174 rows); BA votes at 136 of those as-of points (69 and
  67 with a 2026 BA grade), and 20 carry an older BA grade forward (hitters 4 from 2024 and 3 from
  2025; pitchers 3 from 2023, 1 from 2024, 9 from 2025). The read recounts on the frozen label.
- **Expected power, stated before the read.** 174 rows is the size of the development scope on
  which PL2 failed (166). Leg 1 adjudicates only through its planted checks (A8); a failed check
  makes its comparison UNRESOLVED and hands the question to leg 2.

### A3. Leg 2, the 2026 preseason lists through 2031 (adjudicating when leg 1 cannot)

- **Frame F-BA26-LV.** The list-vintage frame of `efv_vintage_frame.frame_row` at V = 2026 (window
  [2026-01-01, min(2026-05-01, debut day)), a real grader published inside the window, no MLB line
  before 2026, the outcome-blind identity), every row with a consensus grade at its as-of point.
  It holds the players who never reach the majors, which is where a risk penalty can carry
  information that a debut-conditioned frame removes. Size, for scale only: the opening-day cut of
  the same lists held 1,208 rows (`EFV_2026_HOLDOUT.md` section 11.1). Groups: side.
- **Label.** W3 (`efv_labels.py`, the scoring label of F-LV): WAR over the first three MLB seasons
  when the debut falls in 2026 to 2029, 0.0 with no debut by 2029, resolved once RESOLVED_THROUGH
  is at least 2031 and the 2031 season is frozen (`label_window_closed(2031)`).
- Leg 2 runs only if a leg-1 comparison is UNRESOLVED because its planted check failed, or if F4
  is not adjudicated on leg 1 (A6); the leg-1 task records which.

### A4. The arms (each a full rebuild of the consensus time series through the served code)

Exactly the machinery of `tools/ba_grade_consensus_lab.py` (`build`, `latest_table`, the
normalizer's paired table re-derived with the arm's BA value; P1 there is re-checked), with ONLY
Baseball America's votes changed:

| arm | BA on each row |
|---|---|
| S (served) | the stored `fv`: adjusted from 2026, raw before |
| R (raw) | `ba_raw_grade` in every season |
| X (excluded) | every `baseballamerica` snapshot removed |
| D (stale BA vote dropped) | S, except that at a consensus point of cycle y a BA vote whose snapshot year is y - 2 or earlier is removed when at least one explicit-FV vote of year y - 1 or later remains (the rule D of Part C, on BA's votes only) |
| D1 (sensitivity) | as D with "y - 1 or earlier" |

On every leg-1 and leg-2 row whose as-of point carries a 2026 BA grade, S is the published adjusted
grade, so no crosswalk is needed (the development proxy of `BA_GRADE_IN_CONSENSUS.md` section 3 is
not used).

### A5. The statistic

Within (side) Spearman of the arm's as-of consensus (`consensus_fv_raw`) against the label,
size-weighted over groups of 20 or more rows (`efv_v2_stat`), with the paired, player-clustered
E_cond CI95 (`efv_v2_stat.paired_delta`, B 2000, seed 20260906). Secondary, reported: pooled
Spearman and contributor AUC after the identical output map, and per side.

### A6. The comparisons

- F1 = R minus X (raw vote against no vote), F2 = S minus X (adjusted vote against no vote).
- F3 = S minus R: the owner's question, adjusted against raw. ADJUDICATING.
- F4 = D minus S: is a stale BA vote worse than no BA vote. Adjudicating on a leg where at least
  40 rows carry a stale BA vote (D moves their consensus); otherwise reported only.
- F5 = D1 minus S: reported only.

### A7. The null comparators (K = 100 rebuilds each, permutation seed 20261016)

- N1, a no-information BA vote: the raw grades of BA's 2026-02-15 board rows permuted among those
  rows within role. The null of F1 and F2 is the distribution of N1_k minus X (one-sided p in the
  direction of the observed sign).
- N2, a no-information risk penalty: the published 2026 penalties of those rows (BA's ladder, Low 0,
  Mild 5, Average 10, High 15, Extreme 20) permuted within role and subtracted from the raw grade.
  The null of F3 is N2_k minus R (two-sided).
- N3, a no-information drop: at the as-of points where D removes k stale BA votes, k explicit-FV
  votes chosen at random among that point's votes are removed instead (at least one kept). The null
  of F4 is N3_k minus S (one-sided).

### A8. The planted recovery (the instrument must see the effect it is built to see)

- PL1: within each side, the reached rows' own BA raw grades re-assigned in outcome order (highest
  label, highest grade; ties by player key). Passes when PL1 minus X has CI95 above zero and
  exceeds the 95th percentile of N1 minus X.
- PL2: the same rows' published penalties re-assigned so the lowest label carries the largest
  penalty, subtracted from the raw grade. Passes when PL2 minus R has CI95 above zero and exceeds
  the 97.5th percentile of |N2_k minus R|.
- PL3: within each side, the stale BA votes' own grades re-assigned so the highest goes to the
  lowest label (an informative, harmful stale vote). Passes when D minus S on the planted corpus
  has CI95 above zero and exceeds the 95th percentile of N3 minus S.

### A9. The reading rule and the defaults

A comparison RESOLVES only when its CI95 excludes zero, it lies outside its null (p below 0.05),
and its family's planted check passed (PL1 for F1 and F2, PL2 for F3, PL3 for F4). Otherwise it is
UNRESOLVED and its MDE95 is reported. The owner decides; the defaults, fixed here:

- F3 resolves positive (adjusted better): KEEP the served basis.
- F3 resolves negative (raw better): switch BA's `fv` to the raw grade from 2026 (the constant
  `ADJUSTED_GRADE_FIRST_SEASON` and a re-ingest of the 2026 and later boards).
- F1 and F2 both resolve negative: EXCLUDE BA from consensus.
- F4 resolves positive (dropping a stale BA vote helps): adopt rule D for BA's votes.
- Nothing resolves: KEEP the served basis and keep stale BA votes as they are.

### A10. Preconditions of the read task, in order (STOP at the first that fails)

1. Already done: this document carries a dated leg-1 (or leg-2) read: NOT A DEFECT, re-print it.
2. This document is at HEAD unchanged above its results sections.
3. Data exists: for leg 1, `label_window_closed(2028)` is closed and RESOLVED_THROUGH is at least
   2028; for leg 2, the same at 2031. Otherwise 'BLOCKER: date <the first day after the season is
   frozen>' (missing data is never waived).
4. Reserved frames: the 2026 debut cohort is an R-VM cohort and the 2026 lists' W3 seasons overlap
   R-VM cohorts. The read runs only after `docs/efv-v2/EFV_V2_GATE.md` section 9 holds the R-VM
   look record that owns RT 2028 (look 3), or records the 2026 cohort released; otherwise
   'BLOCKER: task <the R-VM look 3 task>'. `source_backtest.CANDIDATE_YEARS` and
   `efv_model.SCORED_YEARS` are never widened by it.
5. The label provider is the frozen fWAR (`efv_labels.provider()` is "fwar"); the run records the
   label id.

### A11. The queue

This task adds two read tasks to the single-writer queue: BA_FORWARD_READ_2028 (leg 1, not_before
2028-10-06, the first day after the 2028 regular season is expected to end and be frozen; its
precondition 3 re-dates it if the freeze is later) and BA_FORWARD_READ_2031 (leg 2, not_before
2031-10-06, requires BA_FORWARD_READ_2028; it ends as NOT NEEDED when leg 1 records that F3 and F4
both resolved). Each writes its numbers into a dated results section of this document and its
artifact under `data/_labs/ba_grade/`, and moves nothing served; a resolved default is applied by a
later task after the owner's answer.

## Part B. The 2023 Blue Jays BA row filed under the veteran's key (a defect repair, no read)

The BA 2023 Blue Jays Top 30 (2023-02-15, rank 24, BA Grade 40, risk High) row printed
"Zack Britton" and was resolved by `baseballamerica_csv.resolve_identities` onto the existing key
`zack_britton`, the veteran left-hander (MLBAM 502154, debut 2011). Its text is the Blue Jays'
2020 fifth-round outfielder from Louisville (136th overall), Zach Britton, MLBAM 676309. Through
the same-name collision prune (`consensus._prune_collision_cluster`, a gap over eight years keeps
only the newest cluster) the row hides the veteran's 2011 history in the served build
(`BA_GRADE_IN_CONSENSUS.md` section 7a). The repair is committed separately in this task: the row
and the 2020 draft spine that reached the veteran's key move to `zach_britton`, chosen by an
outcome-blind rule (the printed name, the board date, the row's side and pre-2023 affiliated
minor league lines and draft picks only; no debut, MLB line, WAR or label), with ingest pins so a
re-ingest cannot put it back. It moves no development row: neither key is in lv_dev or vm_dev.

## Part C. The stale-vote rule: does a grade carried forward from an older cycle belong in consensus

### C1. How consensus treats a stale vote today (read off the code, 2026-10-16)

- `consensus.build_timeseries` forward-fills per source: each point uses the latest snapshot of
  every source that ever graded the player; a vote is replaced only by a newer snapshot of the same
  source and never expires.
- Every explicit-FV vote counts once at equal weight (`compute_consensus_point`, the WS-5 weights
  are all 1.0); a vote's age plays no part.
- Grade normalization maps each vote through the cell of ITS OWN snapshot year
  (`grade_norm(base_fv, source, position, year of the vote's snapshot)`), so a 2024 BA grade on a
  2026 point is put on the FanGraphs scale of 2024, not 2026.
- The only rule that acts on a player a source stopped listing, the drop-off shrink, is off
  (`DROPOFF_SHRINK_ENABLED` False) and reads team Top 30 lists only.
- So a BA grade from a 2023, 2024 or 2025 board of a player BA did not list in 2026 votes at full
  weight beside a 2026 FanGraphs or MLB Pipeline grade.

### C2. Counts on the served board (outcome-free, the latest point of every active eFV board row)

The 240 hitters and 170 pitchers whose BA vote predates 2026 (`BA_GRADE_IN_CONSENSUS.md` section
10) split by the vote's age in cycles relative to the point that carries it:

| side | BA vote 1 cycle old | 2 cycles | 3 cycles | same cycle as a pre-2026 latest point |
|---|---|---|---|---|
| hitters | 80 | 41 | 12 | 107 |
| pitchers | 74 | 19 | 14 | 63 |

The last column is players whose latest consensus point itself predates 2026 (no outlet graded them
in 2026), so their BA vote is as current as every other vote on that point. Stale votes are not
BA's alone: on the same points FanGraphs carries 24 hitter and 12 pitcher votes two or more cycles
old, MLB Pipeline 28 and 34.

### C3. What the development frames can read (outcome-blind count)

BA's first board is 2023-02-15, so no development row ever carries a BA vote older than one cycle:
a BA-only stale-vote read is impossible on development data, and BA's own question is read
forward (F4, Part A). The source-general rule is readable as a proxy. At the as-of points of the
scored development rows (`efv_w2_anchor.build`, the frames of `BA_GRADE_IN_CONSENSUS.md`), votes
two or more cycles old sit on 33 lv_dev rows of 2,862 and on 35 vm_dev rows of 830 that also carry
a fresher vote (3 more vm_dev rows carry only stale votes), every one a FanGraphs or MLB Pipeline
vote; one-cycle-old votes sit on 148 lv_dev and 59 vm_dev rows. Expected power, stated before the
read: about 68 touched rows out of 3,692.

### C4. The rules

- D (drop, primary): at a consensus point of cycle y (its year), an explicit-FV vote (a source not
  in `consensus.CONSTANT_ANCHOR_SOURCES`) whose snapshot year is y - 2 or earlier is removed when at
  least one explicit-FV vote of year y - 1 or later remains on the point. "Older than one cycle":
  one full cycle has passed since that outlet last graded the player. Every other input of the
  point (ranks, the single-instance count, normalization, the other votes) is unchanged.
- W (decay): the same votes are kept at weight 0.5 ** (age - 1) (two cycles 0.5, three 0.25),
  every other vote at 1.0, through `compute_consensus_point`'s own `source_weights` path.
- D1 (sensitivity, reported only): as D with "y - 1 or earlier".

### C5. The frames, the as-of points and the parity checks

- Rows: the scored rows of lv_dev (list vintages 2017 to 2019, label W3) and vm_dev (debut cohorts
  2017 to 2023, career WAR to date) exactly as `efv_w2_anchor.build` makes them, with their outcome
  (`outcome.war` on the frozen fWAR label; the run refuses unless `efv_labels.provider()` is
  "fwar") and contributor flag.
- As-of point: vm_dev, the latest point in [Y-01-01, Y-05-01) (`source_backtest`'s rule); lv_dev,
  the latest point in `efv_vintage_frame.window_bounds(V, debut day)` with the debut day of
  `efv_dataset.debut_day_for_cutoff`.
- Each arm's value is `compute_consensus_point` called on the exact arguments the served
  `build_timeseries` hands it at that point (captured from one served build), with the arm's change
  to the votes. Q1: the unchanged recomputation equals the frames' stored consensus on every row
  (the run refuses otherwise). Q2: every as-of point is found and captured (refuses otherwise,
  after the same-name fold of build_timeseries is followed).

### C6. The statistic

Within (frame|side|year) Spearman, size-weighted over groups of 20 or more rows, on all 3,692
development rows (the rows no arm moves carry the same value in every arm), with
`efv_v2_stat.paired_delta` (B 2000, seed 20260906). Reported, not adjudicated: the same per frame,
pooled Spearman and contributor AUC.

### C7. The comparisons

- G1 = D minus S and G2 = W minus S, ADJUDICATING, Holm over the two null p values.
- G3 = D1 minus S, reported.

### C8. The null comparators (K = 200 draws each, seed 20261016; no rebuild is needed)

- ND: at every as-of point where D removes k votes, k explicit-FV votes chosen at random among that
  point's votes are removed instead (at least one kept). The null of G1 is ND_k minus S.
- NW: at the same points, the weights W gives are assigned to randomly chosen votes of the point
  instead. The null of G2 is NW_k minus S.
- p is one-sided in the direction of the observed sign, (1 + hits) / (1 + K).

### C9. The planted recovery

PLD: at the touched points, within (frame, side), the stale votes' own published grades re-assigned
so the highest goes to the lowest-outcome row (ties by player key), every other vote unchanged.
D minus S on the planted corpus must have CI95 above zero and exceed the 95th percentile of ND_k
minus S. PLD gates G1 and G2.

### C10. The reading rule and what moves

G1 (or G2) RESOLVES positive when its CI95 is above zero, its Holm-adjusted null p is below 0.05,
and PLD passed. Defaults, fixed here:

- Neither resolves: nothing served changes; BA's own question waits for F4 (Part A).
- G1 or G2 resolves positive: the rule that resolved becomes a served candidate for every outlet
  (the read is source-general), built behind a constant that stays off until the owner answers;
  BA-only application waits for F4.
- Either resolves negative (stale votes help): nothing changes and the finding is recorded.

### C11 and C12

Appended by the run.

## D. What this task writes

This document (alone, first); `tools/repair_zack_britton_collision.py`, the ingest pins in
`baseballamerica_csv.py` and `scrapers.py`, and their test (the Part B repair; the database is
repaired by running the script); `tools/ba_stale_vote_lab.py` and its fixture test (committed
before the Part C read); the artifact `data/_labs/ba_grade/ba_stale_vote_read.json`
(`data/_labs/` ships to no webroot) and sections C11 and C12; the two queued read tasks. No served
artifact, flag, constant, weight, registry row or page changes unless C10 says so.
