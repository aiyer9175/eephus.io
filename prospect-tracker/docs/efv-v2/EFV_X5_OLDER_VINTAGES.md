# eFV X5: older prospect-list vintages for the label pool (method, fixed before any number)

Written 2026-10-15 (task EFV_X5_OLDER_VINTAGES) under the owner's decision EW3-12 of
2026-10-15 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, verbatim "Let's do all of the
above"), item (5) of the expert eFV program: source older list vintages to enlarge the label
pool, the binding constraint (the eFV feature frontier is closed, 39 arms, zero survivors).
This document is committed ALONE, before any source is counted, any list row is resolved or
any frame row is built: it fixes the candidate sources, the eligibility rule, the dating rule,
the identity rule, the counting estimand, the floor arithmetic and the pass rule. Sections 1
to 8 are written before any number; the run appends section 9 (results) and nothing above it
moves. No em-dashes. Nothing served moves in this task, under any result.

Registration status: REGISTERED

## 1. What this task measures, and what it does not

The estimand is a COUNT: how many resolved (side, list vintage, person) rows the development
list-vintage frame lv_dev gains when the older vintages are ingested, and what that count does
to the minimum detectable effect (mde95) of the frame's eFV-versus-consensus Spearman delta.

It reads NO outcome. No WAR, no label, no debut outcome, no eFV, no consensus score and no
source score is computed on any row this task ingests, on any frame. The label join for the new
rows (efv_labels on their resolved ids) is owed by the task that trains on them (EFV_X3 or the
2026 fold), under its own registration. Counting rows is the only operation on the frame.

## 2. Frames and reserved data

- Development frame lv_dev: list vintages 2011 to 2019 today (`efv_vintage_frame.DEV_VINTAGES`).
  The older vintages this task can add are 2006 to 2010 (section 5 explains the 2006 floor).
  Rows a new source adds inside 2011 to 2019 (a player the current frame does not hold at that
  vintage) also count as gains.
- R-LV (list vintages 2020 and 2021) follows EW3-13's record for R-LV: SPENT. This task ingests
  no list dated 2020 or later and builds no row at those vintages, so the reserved guard is
  never asked. R-VM (2025 and later debut cohorts) is not touched: nothing here reads a debut.
- The new vintages 2006 to 2010 are development vintages when a later registration adopts them;
  this task does not widen `DEV_VINTAGES` (a constant other modules read), it reports what the
  widening would add.

## 3. Candidate sources (probed in this order)

| id (new source key) | publisher | what | years probed | access path |
|---|---|---|---|---|
| `ba_top100_hist` | Baseball America | preseason Top 100 Prospects | 2006 to 2019 | the Internet Archive's Wayback Machine copies of baseballamerica.com pages captured while the lists were free to read (no login) |
| `ba_org10_hist` | Baseball America | preseason organization top 10 lists | 2006 to 2013 | same |
| `mlbcom_top50_hist` | MLB.com (Jonathan Mayo, pre-Pipeline) | preseason Top 50 | 2006 to 2010 | mlb.com news archive or Wayback copies |
| `bp_top100_hist` | Baseball Prospectus (Kevin Goldstein) | preseason Top 100 / Top 101 | 2006 to 2010 | free copies (si.com syndication, Wayback copies of free BP pages) |
| `sickels_hist` | John Sickels, Minor League Ball | preseason Top 100 / organization lists with letter grades | 2006 to 2010 | minorleagueball.com or Wayback copies |
| `fg_hulet_hist` | FanGraphs (Marc Hulet) | organization top 10 lists | 2009 to 2010 | WebFetch only (FanGraphs HTML blocks Python) |

A source not listed here may be added only if it meets every eligibility rule below; the run
names it in section 9 with the reason. None of these keys enters `source_backtest.SCORED_SOURCES`,
consensus.py, the served boards or any served artifact in this task.

## 4. Eligibility (all four, per source)

1. PUBLIC: readable without a login or payment at the access path used, and no robots rule
   at the access path disallows the fetch. Paid, login-walled and Cloudflare-challenged pages
   are not fetched by Python; FanGraphs is read through WebFetch only.
2. TERMS RECORDED: the source's terms and the archive's terms are written into the source
   record. Only facts are kept (printed name, list rank, organization, position, letter grade
   if printed, list date, URL and capture timestamp); no prose is stored in the repository.
   Raw captures live under `.cache/EFV_X5_OLDER_VINTAGES/` (gitignored) only.
3. DATED: each (source, list year) has a publication date, taken from the page itself (a
   dateline or byline date), or from the publisher's announced release date, or, when neither
   is printed, the earliest archive capture of the list (an upper bound on the publication).
   The date must lie inside the preseason window [V-01-01, V-05-01) of the list year V
   (`source_backtest._WINDOW_START_MMDD`, `_WINDOW_END_MMDD`); a list dated outside it is not
   ingested.
4. RESOLVABLE: the outcome-blind resolver (`efv_identity.resolve` on the printed name, V and
   the routed side, index through V - 1) gives a person id (routes name_unique, name_side,
   name_recency) on at least 80% of the (source, list year)'s side-routed rows. A list year
   under 80% is recorded and not ingested.

## 5. The ingest and the dating rule

- Each eligible list row becomes one dated board point under its source key, in a
  universe-shaped record (`player_key` = `x5:<source>:<normalized printed name>`,
  `player_name` as printed, `position` as printed, `points[]` with `snapshot_date` = the
  publication date and `per_source[<source>]` = {rank, grade as printed or None,
  `fv_published` None unless the list printed a 20-80 FV, `snapshot_date`, `published_on`,
  `capture_ts`, `url`}).
- The artifact is `data/_labs/efv_x5/older_vintage_points.json` (depth two under `data/_labs/`,
  which ships in neither deploy consumer).
- NO LOOK-AHEAD, test-enforced (`test_efv_x5_older_vintages.py`): every point's
  `snapshot_date` equals its `published_on`, no point is dated after its list publication,
  every `published_on` is inside its list year's preseason window, every capture is at or
  after the publication date (the archive saw the list after it was published), and the
  resolver's index for a row of vintage V holds seasons through V - 1 only.
- Why 2006 is the floor: the resolver's minor league index starts at 2005
  (`efv_identity.FIRST_INDEX_SEASON`, the first season on disk). A 2005 or earlier list has no
  pre-V season to match against, so its rows cannot resolve outcome-blind. This task does not
  move FIRST_INDEX_SEASON (it would change the candidate sets of every existing lv_dev row).
  Pre-2006 coverage is recorded as available, not ingested.

## 6. Frame membership for a new row (counts only)

A new row (source record, V, side) is in the augmented frame when, exactly as
`efv_vintage_frame.frame_row` would admit it:

- the record routes to the side (`efv_dataset._side_match` on the printed position);
- it has a point published inside the V window, by a source that printed a rank or a grade
  (a top 100 list prints a rank, not an FV: a rank is a read for membership here);
- the resolver gives a person id (section 4.4);
- the resolved id has no major league (sport 1) line in any season 2005 to V - 1 on the cache
  (the frame's "not yet a major leaguer at V" rule; the frame itself reads 2014 to V - 1 because
  its vintages start 2011, and a published debut date before the window does the rest).

A gained row is a (side, V, person id) in the augmented frame and NOT in the current frame
(`build_frame(side, V, milb=False, sidecars=False)`, ids read from its `mlbam_id` field, the
outcome-blind id) for V 2011 to 2019; for V 2006 to 2010 the current frame is empty, so every
augmented row is a gain. A person on two new lists in the same (side, V) counts once.

## 7. The floor arithmetic (no data read beyond the counts)

The reference is the census's `floor_curve.references.lv_econd_within` in
`data/efv_label_pool_census.json`: sd_ref 0.01093 at n_ref 2,862 rows (1,753 player clusters),
the E_cond within-delta of V2 versus PROSPX consensus on lv_dev
(`data/efv_v2_dev_eval.json`, key `ds16.frames.lv_dev.deltas.v2_vs_prospx_consensus.spearman.sd`).
The formula is the census's own: mde95(n) = 1.645 * sd_ref * sqrt(n_ref / n).

- Retention r = 2,862 / N_cur, with N_cur the number of resolved (side, V, id) rows of the
  current frame over V 2011 to 2019 counted by section 6's rule. r is the share of resolved
  frame rows that reach the scored lv_dev frame (label resolved, comparator present), a ratio
  of counts.
- PRIMARY: n_after = 2,862 + r * G, with G the gained rows (section 6). Report mde95 before
  (n_ref) and after, and the change.
- SECONDARY (upper bound): n_after_ub = 2,862 + G.
- CLUSTER READ: c_after = 1,753 + r * P, with P the gained distinct persons not in any current
  frame row; mde95 scaled by sqrt(1,753 / c_after) beside the row read.
- Caveat written now: the scaling ignores that the new rows' comparator would be the archived
  source's own rank (no PROSPX consensus exists before 2011) and that era shifts the label; the
  measured floor of an augmented frame is owed by the task that scores it.

Seed: none. Every number here is a deterministic count; nothing is resampled.

## 8. Pass rule and what moves

- A source PASSES ingestion when it meets all four eligibility rules in section 4 on at least
  one list year; only its passing list years are ingested.
- The task PASSES when at least one source passes and G > 0. It reports G by (side, V), P, and
  mde95 before and after (primary, upper bound, cluster read).
- Nothing served moves under any result: no SCORED_SOURCES edit, no consensus input, no
  exporter, no served page, no registry row that adjudicates. Adopting the rows (widening
  DEV_VINTAGES, joining labels, scoring) is a later registered task's decision and an owner
  question (OWNER_QUESTION.md in the result).
- Anchor gate (`docs/PROSPECT_ANCHOR_GATE.md`): no count, mean or residual is cut by
  consensus-FV level; the only strata are source, list year, vintage, side and identity route.

## 9. Results (appended 2026-10-15 after the run; sections 1 to 8 unchanged)

Run: `python tools/efv_x5_older_vintages.py --fetch --write` then a cache-only
`--write` (generated 2026-10-15T20:54:14Z on top of the registration commit d9413f3a,
40.9 s from the cache). Artifacts: `data/_labs/efv_x5/older_vintage_points.json` (1,974
records, 2,646 dated points) and `data/_labs/efv_x5/older_vintage_census.json`. No
outcome, label, eFV, consensus or source score was read or computed.

Sources (pooled match rate is resolved over side-routed rows of the lists read in their
window):

| source | coverage found | depth | grade field | lists ingested | rows ingested | match rate |
|---|---|---|---|---|---|---|
| `ba_top100_hist` | 1990 to 2017 on the all-time index; 2006 to 2013 dated by the year pages, 2015 by an in-window capture | 100 | rank | 9 (2006 to 2013, 2015) | 900 | 0.9488 |
| `ba_org10_hist` | 207 organization lists, 2007 to 2013 folders | 10 | rank | 78 dated January to April | 779 | 0.9182 |
| `bp_top100_hist` | 2007 to 2011 free articles | 100 to 101 | rank | 5 | 502 | 0.9183 |
| `sickels_hist` | 25 Sickels organization posts dated January to April, 2009 to 2011 | 20 to 24 | rank and letter grade | 23 | 465 | 0.8931 |
| `mlbcom_top50_hist` | 2004 to 2010 | 50 | rank | 0 (2009 published December 2008; 2010 has no reachable publisher date) | 0 | not read |
| `fg_hulet_hist` | not probed in the time box | 10 | rank | 0 | 0 | not read |

Not ingested: 125 lists dated outside their window (almost all BA organization lists
published October to December of V - 1), 6 lists under the 0.80 match rate (4 BA
organization lists, 2 Sickels lists), BA Top 100 2014, 2016 and 2017 (no page dateline
in the archive and no in-window capture holds the list). The all-time BA index agrees with
the dated year pages on 95 to 99 of 100 names a year.

Gains (registration s6), resolved (side, V, person) rows the development frame does not
hold today:

| vintages | hitters | pitchers | total |
|---|---|---|---|
| 2006 to 2010 (new vintages) | 439 | 380 | 819 |
| 2011 to 2019 (rows new at an existing vintage) | 98 | 78 | 176 |
| all | 537 | 458 | 995 |

By vintage: 2006 71, 2007 150, 2008 150, 2009 209, 2010 239, 2011 145 (the current 2011
frame holds 122 resolved rows), 2012 24, 2013 5, 2015 2, 2014 and 2016 to 2019 0. Distinct
new persons (in no current frame row): 612. Identity routes of the gained rows:
name_unique 966, name_side 22, name_recency 7.

Floor (registration s7; N_cur 5,706 resolved rows in the current frame 2011 to 2019,
retention r = 2,862 / 5,706 = 0.5016):

| read | n before | n after | mde95 before | mde95 after | change |
|---|---|---|---|---|---|
| primary (retention-adjusted rows) | 2,862 | 3,361.1 | 0.01798 | 0.01659 | -0.00139 |
| upper bound (every gained row scores) | 2,862 | 3,857 | 0.01798 | 0.01549 | -0.00249 |
| cluster read (persons) | 1,753 | 2,060.0 | 0.01798 | 0.01659 | -0.00139 |

Verdict under s8: PASS (four sources pass, G = 995 > 0). Nothing served moves; adopting
the rows is an owner question (`docs/efv-v2/EFV_X5_OLDER_VINTAGES_RESULTS.md`).
Disclosure: seven Baseball Prospectus requests (the free 'Top 400' index article, robots.txt
and the five list articles) went out 1.5 s apart, under robots.txt's Crawl-delay of 2; the
committed tool waits 2.5 s.
