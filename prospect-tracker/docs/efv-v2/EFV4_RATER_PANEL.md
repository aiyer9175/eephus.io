# eFV v4: the historical rater panel column (EFV4_RATER_PANEL)

Registration status: REGISTERED

Written 2026-10-08 (evening, US Eastern) under decisions EW2-8 to EW2-11 of 2026-10-08
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), before any statistic of the column was
computed on any frame. Research: `_finalpass_2026-09-24/efv4/RESEARCH.md` section 2.4 and
task `EFV4_RATER_PANEL_COLUMN` of `TASKS.json` beside it. No em-dashes. Nothing here, in its
code or in its artifacts, is cut by consensus-FV cell (`docs/PROSPECT_ANCHOR_GATE.md`).
Nothing served moves: the column is a lab column; `consensus.py`, `SCORED_SOURCES`, the
displayed PROSPX consensus FV and every served eFV grade are untouched.

RESERVED LIST YEARS NAMED: 2020, 2021

(The line above is the marker `efv_rater_panel.registration_names_reserved` looks for at
HEAD; until a commit carried it, no panel row of list year 2020 or 2021 was built.)

## 1. Why

On list vintages 2011 to 2016 the served consensus carries one real source per row (MLB
Pipeline; FanGraphs joins in 2017), so a model developed there learns its drivers against a
one-rater anchor, while the reserved frames are multi-source. Independent raters' errors
average out: with reliability r per rater, k raters give k r / (1 + (k - 1) r) (r 0.85: two
0.919, three 0.944). The research lane's expectation: about +0.004 to +0.010 within Spearman
on lv_dev (larger on V 2011 to 2016 folds), about +0.004 on R-LV-type frames, about 0 on
vm; P(admitted) about 0.40. Both reads below sit under the frames' resolution floors
(lv_dev E_cond floor against consensus about 0.018), so a true effect of that size reads
as a tie. That is said here before the read.

## 2. Sources (public pages only; `tools/efv4_rater_fetch.py`, cache `.cache/efv4_raters/`)

| rater | years ingested | where | notes |
|---|---|---|---|
| Baseball Prospectus Top 101 | 2011 to 2020 | baseballprospectus.com article pages | 2021 is subscriber-only (live page and every Wayback capture of 2021-01-21 to 29): skipped and named |
| FanGraphs | 2011 to 2015 | blogs.fangraphs.com | Hulet top 100 2011 to 2014, McDaniel 2015 top 200 (142 ranked); no 2016 overall list was found; 2017 on is already a consensus source |
| Baseball America Top 100 | none | | every archive and list page answers 403 without a subscription; behind a login, never fetched with credentials |
| ESPN (Keith Law) | none | | Insider paywall; the Wayback copy of the 2016 index carries the paywall shell only |

Fetch rule (EW2-11): fetched 2026-10-09 02:25 to 02:45 UTC, one request at a time, a
descriptive User-Agent, a pause between requests, into `.cache/efv4_raters/` only.

## 3. The column

For a row read at as-of date d (player p, side s, group g):

- each rater with a list of year d.year published on or before d contributes
  `consensus.implied_fv_from_rank(rank)` if it listed p, else its LIST FLOOR;
- `panel_fv` = the mean over the contributing raters; None when no rater has such a list
  (imputed at the training mean by the fit, as every sidecar column; no absence flag enters
  any head);
- `rater_panel_resid` = within-g percentile of `panel_fv` minus within-g percentile of the
  consensus FV (u_c), over g's rows that carry both.

g is (side, list vintage V) over every frame row of V with a consensus on the list-vintage
frames, and (side, decision year, train or test) on the vintage-matched frames.

Defaults (named; the owner may choose otherwise):

- LIST FLOOR: the map band one step below the band of the list's last rank (a 100 or 101
  list: 45; the 2015 FanGraphs 142 list: 40), so an unlisted player never ties a listed one.
- PANEL MEAN: every contributing rater once, unlisted at its floor.
- AS OF: a list counts only for reads in its own year on or after its publication day, and
  only when published inside [V-01-01, V-05-01); no midseason list. A list-vintage frame row
  reads on the last day of its own window (V-04-30, or the day before a debut inside the
  window), so every list published inside the row's window counts; its latest consensus
  point (often the January Pipeline board) is not the bound. A vintage-matched row reads at
  its own as-of date (matrix cutoff for training rows, pinned preseason read for test rows).
- DEVELOPMENT READ WITHOUT THE RESERVED LIST YEARS: the development read uses lists of
  2011 to 2019 only (a vm_dev row of debut year 2020 or later has no panel), so no
  reserved-year list material reaches a choice.

## 4. Identity (outcome-blind)

`efv_rater_panel.BoardIndex`: an entry (name, position, team, list year Y) is matched
against the MLB Pipeline and FanGraphs board snapshots dated in [Y-1-01-01, Y-05-01) in
`prospects.db`: a unique exact folded name; else the candidates on the entry's club (the
club the Pipeline org list placed them on); else on the entry's side; else a unique last
name plus first initial on the club and side; four explicit name variants (Raul and Raul
Adalberto Mondesi, Caleb Cowart, Dee Gordon). The module reads no outcome column (AST pin,
the `test_efv_identity` pattern). An unresolved entry is recorded and counts as unlisted.

## 5. Arms and reads

Arms: the column offered to the hitter skill head (`w2r_panel_hit`), to the pitcher skill
head (`w2r_panel_pit`), and to both (`w2r_panel_both`), each under V2's own DS-06 admission
inside every fold (`efv_v3.fit_v3` at the base configuration plus the column), through
`tools/efv_v3_backtest.build_dev` (V2 base reproduces DS-16 bit for bit before any read).

- Development (choice frames): lv_dev (list vintages 2017 to 2019 scored, training on 2011
  onward, W3, frozen fWAR label) and vm_dev (vm2, debut years 2017 to 2023). Within, pooled
  and contributor-AUC deltas against the V2 base and PROSPX consensus, E_cond CI95 (B 2000,
  paired, player-clustered); the zero-information twin (the column permuted within year and
  kind); the DS-03 balance probe of panel_absent on the lv_dev training rows the Pipeline
  lists. Rows: development rows in `data/efv_progress.json` (screening block, never charted).
- Spent (EW2-10): R-LV (list vintages 2020 and 2021) and R-VM (2025 debut cohort), read once
  on 2026-10-08 and spent, through `build_reserved` on the committed gate sha
  e7931ce4e13110eebb53555bff455ff13ca7c502. Labelled "spent frame, read after the 10-08
  confirmation"; chooses and tunes nothing; written to the artifact only (a reserved-frame
  ledger row is charted, so none is written). BP 2021 is paywalled, so R-LV 2021 rows have
  no panel; R-VM 2025 test rows have no list of their year (the task's range ends 2021).

Artifacts: `data/_labs/efv_w2/rater_panel.json` (the lists, resolved),
`data/_labs/efv_w2/efv_w2_raters.json` (the reads). Ship rule (EW2-10): beats served V2 on
lv_dev, vm_dev, R-LV and R-VM (point estimates, pooled over sides); nothing ships from this
task (flags off), whatever the read.

## 6. Results

Appended by the read commit.
