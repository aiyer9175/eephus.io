# eFV against consensus as published: the timing-edge read (method, fixed before any number)

Registration status: REGISTERED

Written 2026-10-15 (task EFV_BEAT_TIMING_EDGE) under the owner's decision EW3-11 of
2026-10-15 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, verbatim: 'Can we please use the
drivers to beat consensus with eFV?'; the owner picked the timing edge as path 1) and the
waiver of registered dates EW3-5. This document is committed ALONE, before the module
`tools/efv_timing_edge.py` exists and before any number is read: it fixes the estimand,
the frames, the read dates, the raters at each read date, the statistic, the seed, the
pass rule and what the site may say under each verdict. Sections 1 to 12 are written
before the read; the run appends section 13 (the numbers) and section 14 (the verdict).
No em-dashes. Nothing here, in its code or in its artifacts, is cut by consensus-FV cell
(`docs/PROSPECT_ANCHOR_GATE.md`, binding): the only groups are side, list year (or debut
year), read date and read month.

## 1. Why this read

Every eFV read so far froze eFV and consensus at the SAME as-of date (the preseason point
of the list year). That removes, by construction, the one advantage the served board has
over a published list: eFV re-reads the minor league lines every day of the season
(`efv_dataset.build_live_matrix` reads the current season to date), while consensus moves
only when a source publishes (the preseason lists in January and February, and one
midseason update). This read measures that advantage as the board would have shown it:
at a grid of read dates inside each development season, eFV v5 COMBINED with its minor
league inputs read through the read date, against consensus as it was last published on
or before the read date.

A census of the board points' dates was taken before this document (counts of points by
month, 2017 to 2023; no grade compared, no label read, no score): points cluster in
January and February (the preseason lists) and in one midseason month (FanGraphs: August
2018, July 2019, July 2021, August 2022, August 2023; no midseason update in 2017), with a
few dozen scattered points in other months. That census set the read grid below and is
the only thing read before this registration.

## 2. The estimand

For a read date d inside season S, and the prospects still unpromoted at d:

    Delta(d) = rho_within(eFV v5 COMBINED as of d, label)
             - rho_within(consensus as published on or before d, label)

with rho_within the within-group Spearman of section 7, groups (side, list year or debut
year, read date). The headline is Delta pooled over every read date of a frame by row
count (the size-weighted mean over groups, which is what the within statistic does when
the groups are (side, year, read date)).

## 3. The frames (development only)

- **lv_dev**: the list-vintage frame of the eFV v5 COMBINED development read, list
  vintages V 2017, 2018 and 2019 (`efv5_combined.build_dev`, the C03 fold shape), scored
  rows only (consensus, a W3 label and a V2 score). Label: W3 on the frozen fWAR label
  `fwar@2026-10-02-0341299c20ec`, exactly the value the development read scores. Read
  season S = V.
- **vm_dev**: the vintage-matched frame vm2 of the same read, debut years Y 2017 to 2023,
  scored rows only. Label: career WAR to date, exactly the value the development read
  scores. Read season S = Y.
- **Membership at a read date.** A row is in the read-date frame at d when the player had
  not reached the majors on or before d:
  - lv_dev: the row's effective debut year (the label's own `debut_year`) is not V, or it
    is V and the record's debut day (`efv_dataset.debut_day_for_cutoff`, placeholders
    never read as a day) is after d. A row debuting in V with no usable debut day is
    dropped at every read date of V (count disclosed).
  - vm_dev: the matrix row's debut day (its `cutoff`, the debut date the matrix was cut
    at) is after d. A row whose debut day is not a full date inside Y is dropped (count
    disclosed).
  - Both raters are scored on exactly the same rows at every read date.
- **R-LV and R-VM (spent).** Read only if the development pass rule (section 8) passes,
  and then once each, labelled SPENT (both were read by v3, v4, v5 and v5 COMBINED), with
  the same construction on the committed gate sha
  `e7931ce4e13110eebb53555bff455ff13ca7c502`; a pass there is corroboration, never the sole
  claim. If the development rule fails, neither spent frame is opened.
- **The 2026 holdout record** (`data/efv_2026_holdout.json`, EFV_2026_HOLDOUT_READ, spent
  after its read) is read as written for corroboration only: it froze every rater at the
  2026 opening day, so it is the same-date control on 2026, not a timing read. Nothing is
  recomputed on 2026.

## 4. The read dates

Six per season, the last day of each month April to September:

    S-04-30, S-05-31, S-06-30, S-07-31, S-08-31, S-09-30

for S in 2017, 2018, 2019 (lv_dev) and 2017 to 2023 (vm_dev). Season 2020 had no minor
league season: its read dates read no 2020 line (the true state of the board then), and
its rows are kept.

## 5. The raters at a read date

- **Consensus as published (the comparator).** The record's latest board point with
  `snapshot_date` on or before d inside [S-01-01, d] (the list year's points; the
  preseason point is always among them), its `consensus_fv_raw` (else `consensus_fv`):
  the board as it stood at d, never a later point. Every per-source date on that point
  is asserted on or before d.
- **eFV v5 COMBINED as of d (the candidate).** The fold models of the development read
  unchanged (fold V trains on list vintages before V with every V-frame player left out;
  fold Y trains on matrix rows with a decision year before Y; lambda and alpha as the
  folds chose them; no refit, nothing tuned here), applied to the row re-read at d:
  - the anchor u_c: the within-(side, year, read date) percentile of consensus as
    published at d (section 5, first bullet), the same value the comparator scores;
  - the prior block (`efv_dataset._prior_features`: tools, rank context) at that same
    point;
  - the minor league block (`efv_dataset._milb_features`) read the way the live board
    reads it (`build_live_matrix`: the current season first), with season S replaced by
    its season-to-date lines through d: StatsAPI `stats=byDateRange` from S-01-01 to d,
    every affiliated minor league sport id, both groups, cached under
    `.cache/efv_timing_edge/` and never written into `.cache/milb_stats`; the level norms
    of season S taken from the same to-date lines and blended with season S-1's full
    norm by qualified count, as `milb_history.league_norms` does for a season in
    progress; the AAA Statcast line and park line adjustments are not applied to the
    to-date season (no tracked slice dated by d exists on disk); the season age, a
    function of the birth date only, is taken from the season file where StatsAPI omits
    it on a date-range line. Seasons before S are read exactly as the development read
    reads them;
  - every candidate column of v5 COMBINED at its development (preseason) value. The live
    board reads the group, tool, pitch-event, population and scouting columns off the
    last ENDED season, which at an in-season d is S-1, the season the preseason read
    reads; the dated families (injured list, invitations, raters, reports) are held at
    their preseason read, which only leaves eFV staler than the board was (default D-2);
  - the sidecars (body mass, Pipeline revision, protection status, acquisition) at their
    preseason values, all dated before d.
- **V2 as of d.** The development read's V2 fold model on the same re-read rows (the
  base model, reported beside the candidate).
- **Controls (the old tie).** On the same read-date rows: eFV v5 COMBINED and V2 at the
  PRESEASON read (the development read's own orders) against consensus at the preseason
  point (the same-date comparison every earlier read made), and consensus as published
  at d against consensus at the preseason point (what the published updates did).

## 6. No look-ahead (asserted in code; the run refuses on a violation)

- every board point a read-date row reads is dated on or before d, and every per-source
  date on it is on or before d;
- every to-date minor league file is requested with endDate d and carries d in its
  receipt; season S is read from it and from nothing else;
- every row kept at d has its debut after d (section 3), so the label's first counted
  season-event (the debut; W3 and career WAR count only major league seasons from the
  debut) is after the read window: the label starts after the window;
- every candidate column and sidecar value is the preseason read, dated before
  S-05-01, so on or before the first read date S-04-30;
- the fold models are the development read's, fitted before d's rows are built and
  never refitted on them.

## 7. The statistic

- **Primary.** Within Spearman: for each group (side, year, read date) with at least
  20 rows (`efv_v2_stat.MIN_GROUP_ROWS`), the Spearman rho of the rater's own score (the
  eFV order index; consensus FV) against the label; the size-weighted mean over groups.
  Paired: a group counts only when both raters have a rho. Delta = eFV minus consensus
  as published, pooled over every read date of the frame by row count.
- **Interval (decides).** Paired, player-clustered bootstrap (a player's rows across
  every read date and year drawn together; `source_backtest._cluster_layout` and
  `_cluster_draw`), scores fixed, B 2000, seed 20261015. The one-sided 95 percent lower
  bound is the 5th percentile of the drawn deltas; the two-sided CI95 is reported beside
  it.
- **Club-clustered sensitivity (reported, does not decide).** The same bootstrap with
  the cluster the player's organization on his preseason point of that year (a player
  in two years may sit in two clusters; disclosed), B 2000, seed 20261015.
- **Reported cuts (descriptive).** By side; by read month (pooled over years); by year;
  the V2 leg; the controls of section 5; on lv_dev the arrival label R3 (reached the
  majors with a debut in V to V+3; resolved) as a secondary label read the same way
  (vm_dev rows all reached, so it has no arrival read); row counts per (side, year,
  read date). Never by consensus-FV level.

## 8. The pass rule (fixed here, before any number)

The timing edge PASSES when, pooled over read dates by row count, the one-sided 95
percent player-clustered lower bound of Delta (eFV v5 COMBINED as of d minus consensus
as published at d, within Spearman, the primary label) is above 0 on lv_dev AND on
vm_dev. Anything else is NOT PASS. The club-clustered lower bounds, the arrival label,
the controls and every cut are reported and do not change the verdict.

## 9. The spent frames

Only on a PASS: R-LV (list vintages 2020 and 2021, read seasons 2020 and 2021) and R-VM
(the 2025 debut cohort, read season 2025) are read once each by the same code, labelled
SPENT, with the same statistic; their lower bounds are corroboration and never the sole
claim. The owner's EW3-5 waiver covers the dates; a dated note goes below the last
section of `docs/efv-v2/EFV_V2_GATE.md` if they are opened. On NOT PASS they are not
opened.

## 10. What the site may say

- **PASS, and the owner answers the flip question yes** (`OWNER_QUESTION.md` in the
  task's output directory; nothing served moves before that answer): one sentence on the
  Source Comparison page, derived from the artifact, of the form 'Read during the season,
  eFV ordered prospects' later WAR better than consensus as it was published at the
  time (development seasons 2017 to 2023, one-sided 95 percent lower bound +X)', labelled
  a development read on a frame the models' penalties were chosen on, and never the
  headline 'beats consensus' of the vintage-matched frame, whose comparison is same-date.
- **PASS without the owner's answer**: nothing served moves.
- **NOT PASS**: nothing served moves; the copy keeps 'ties consensus'; the site says
  nothing about a timing edge.

Whatever the verdict: no served number, grade, chip, ledger row or claim moves in this
task; the read writes no row to `data/efv_progress.json` (a timing frame is not the
vintage-matched frame of the progress chart).

## 11. Defaults applied (the owner may choose differently)

- D-1 read dates: the last day of each month April to September (six per season).
- D-2 candidate columns, dated families and sidecars at their preseason read (section 5);
  only the anchor, the prior block and the minor league block move with d.
- D-3 the to-date season's level norms blended with the prior season by qualified count
  (the live board's rule).
- D-4 the spent frames read only on a development PASS.
- D-5 rows with no usable debut day in the read season dropped at every read date of it.
- D-6 the club cluster is the organization on the preseason point.

## 12. Bans and hygiene

- No reserved row is built unless section 9 opens it; the development build raises on
  list vintages 2020 and 2021 and stops before the 2025 cohort (`efv_vintage_frame`).
- No statistic by consensus-FV cell anywhere (`docs/PROSPECT_ANCHOR_GATE.md`); the test
  scans the module source.
- No projections retrain; the fWAR label epoch's runbook is untouched;
  `backtest.run_backtest` is never called; no model is refitted on a read-date row.
- Code: `tools/efv_timing_edge.py`, tests `test_efv_timing_edge.py`; artifact
  `data/_labs/efv5/efv_timing_edge.json`; cache `.cache/efv_timing_edge/` (to-date minor
  league lines, fetched outside the 06:00 to 11:00 UTC nightly window).
