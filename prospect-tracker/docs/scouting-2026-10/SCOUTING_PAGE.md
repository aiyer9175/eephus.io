# The /scouting/ page: specification and copy

Registration status: REGISTERED

Task TL_20_SCOUTING_PAGE_REGISTRATION, written 2026-10-14 at HEAD 1b947cf5 (branch
efv-conviction-2026-08-08, built in worktree lane 205). Plan: Part 9 'Projections, aging, tools and
team program', section 9.4 'Tools: framework, source accuracy, the power composite, prospect stat
projections v2, tools as eFV V2 candidates', subsection 9.4.8 'Re-derived tool tables and the
/scouting/ page (message 3)' (Part 9 bundle `PLAN.md`; finding C7 of 9.1.3 for the served FV
configs and C8 for the route; round 4 rulings R1 and R2, round 4 intents 4 and 5). Part 9 is not
yet appended to `docs/master-plan-2026-09-24-final-pass.md` at this HEAD, so the bundle copy is the
plan read. Docs only, committed alone. Nothing served moves.

The owner's ask (2026-10-01, message 3, verbatim): "You can rederive tool->statistical production
grades if needed, the FanGraphs translations are estimates and if we could make these more accurate
(+provide a standalone "scouting" page that explains the 20-80 FV grading scale, with WAR
projections for each FV tier and tool projections for each tool tier, this would be really useful
for the public space)".

Owner answers this document is written under (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, the
Part 9 table, recommended options accepted under the standing instruction of 2026-10-01):
- TL-Q7 'FV column': "Both, arrives first": two clearly labelled columns per tier, 'If he arrives'
  then 'Expected, bust-inclusive', with a two-sentence note on why they differ.
- TL-Q8 'Scout page': "/scouting/ in the nav": a standalone public page with a main-nav slot,
  linked from the glossary, PROSPX cards and Source Accuracy.

Both were answered before this task ran, so no default was taken for either.

**Nothing was scored to write this document.** No grade was paired with an outcome, no table was
fitted, no cohort or cell was counted. Every figure below is a published value transcribed from
`docs/reference/FANGRAPHS_FV_FRAMEWORK.md` with its section id, a value read from a committed
config or fitted file through the keys this program allows, or a constant. The served
`empirical_anchors.anchors` and `diagnostics` blocks of `data/value_framework_fitted.json` were not
read for this document; only `cohort_window`, `n_cohort`, `generated_at`,
`policy_digest.blend_weight_public` and `anchors_provenance` were.

Who uses this file:
- TL_22_SCOUTING_PAGE_BUILD_DARK builds `data/reference/fv_framework_tables.json`,
  `tools/scouting_export.py`, `build_site.build_scouting_page()` and `test_scouting_page.py` to it,
  dark behind `SCOUTING_PAGE_LIVE`.
- TL_23_SCOUTING_PAGE_FLIP flips the page in one commit, with the nav entry, the static navs, the
  icon, the inbound links, the registry row and the glossary entries.
- TL_24_SCOUTING_FV_COLUMN_POST_ANCHOR adds only what the Prospect Anchor look's record releases.

Preconditions checked at this commit: (1) `docs/scouting-2026-10/SCOUTING_PAGE.md` did not exist;
(2) TL_19 is committed (`e79b8f55`, integrated at `4ef73d2a`: Part T of
`docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md`, status REGISTERED); (3) the fWAR label epoch
is past its step Z entry (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9, '### 2026-10-03:
step Z, the fWAR label epoch's results'), so the repository is not between step A and step Z.

---

## 1. Purpose and route

A public explainer of the 20-80 scouting scale, the WAR each FV tier carries and the stat line each
tool grade implies, every number cited to a published source or to a served table with its
registry row.

- Route: `/scouting/`, under TL-Q8 option 1.
- Kind: a `build_site.py` generator page, like `/sources/` (`build_sources()`), on the shared
  `page()` shell. The shell, the site.css tokens, the masthead, the theme toggle and the
  content-hash asset stamping come from the generator. It is not hand-authored; if a later writer
  hand-authors it instead, it must join `HAND_AUTHORED_PAGES` so `restamp_hand_authored_pages()`
  stamps it.
- Module key: `scouting` (the nav `active` marker, the icon key and the sitemap row).
- Data: `data/scouting_reference.json`, written by `tools/scouting_export.py` (section 7 for the
  dark path). The page embeds that payload at build time; it fetches nothing at run time.
- Nav and inbound links (TL_23, under TL-Q8): `('scouting', 'Scouting', '/scouting/')` in
  `NAV_ITEMS` immediately after the Library entry (`("glossary", GLOSSARY_DISPLAY_NAME,
  "/glossary/")`); the three hand-kept static navs (`prospx/index.html`,
  `collegesavant/index.html`, `collegesavant/pitcher_index.html`) under
  `test_collegesavant_nav_in_sync.py`; an `ICON_FOR` entry for `scouting`; one link from each
  PROSPX card's grade block; one link line on Source Accuracy (`/glossary/#view=source-accuracy`)
  beside the Library entry links.
- Layout: the newspaper-board idiom of `branding/README.md`; site.css tokens only, no raw hex;
  square corners; tables in a scroll wrap with sticky headers and a sticky first column,
  right-aligned tabular numbers; no horizontal page overflow at 390 px.

Order on the page: masthead and lede; A, the 20-80 scale; B, WAR by FV tier; C, stat lines by tool
grade; D, how eephus uses grades; the sources footer.

## 2. Section A: the 20-80 scale

Content, each statement cited (framework section, source id):

| statement | framework section | source |
|---|---|---|
| 50 is major league average; each 10 points is one standard deviation | 1.1 | S3 (McDaniel 2014), S2 (Longenhagen and McDaniel 2018) |
| three deviations each way hold 99.7% of a normal population, hence 20 to 80 | 1.1 | S3 |
| the population is major league players | 1.1 | L7 (Longenhagen 2022) |
| censored at both ends: an 80 is three deviations or more, a 20 three below or less | 1.2 | L7, W2 (Smith 2013) |
| an 80 is about 1 player in 1,000; about 750 open the season on rosters | 1.2 | W3 (Smith 2013) |
| 45 and 55 near average; 35 and 65 mostly from analysts | 1.1 | S2 |
| where 50 sits: a league-average hitter over 550 PA is 2.0 WAR | 6.1, 6.4 D2 | W1 (Cistulli 2013) |
| FanGraphs claims a deviation scale; BA and Pipeline publish adjectives only | 11.4 X1 | P1, B1 |
| the 2-8 convention, no half grades, named by all three outlets | 1.3, 11.4 X8 | S3, P1, B1 |
| the adjective ladder | 1.3 (table), 11.1, 11.2 | S3, L10 (McDaniel 2015), P1, B1 |
| present/future notation, 20/50 | 1.4 | S3 |
| the worked report line (Joey Gallo) | 1.4 | L14 (McDaniel 2014) |
| FV is one grade for the whole player, with risk and proximity inside it | 3.2, 5.5, 7.1 | S2 |
| five position-player tools; pitchers graded per pitch plus command | 1.5 | S3 |
| game power against raw power | 1.5 | L16 (McDaniel 2014) |

The adjective table: one row per grade the outlets publish (80, 75, 70, 65, 60, 55, 50, 45, 40, 35,
30, 25, 20), columns Grade, SD from average ((grade - 50) / 10, the scale's own definition, S3),
FanGraphs (S3 1.3 table, the 'Tool Is Called' column, blanks kept blank), Baseball America (B1,
11.2 ladder, without the named player examples), MLB Pipeline (P1, 11.1, banded: 20-30 and 70-80
share one term). A row no outlet names prints its grade and SD only.

No percentile column: the sources give rarity statements (1.2) and those print as prose; the page
does not compute normal-tail shares.

## 3. Section B: WAR by FV tier

Two quantities, never mixed (framework 7.1): **'If he arrives'** (Quantity A, a talent statement
about a player who reaches his role) and **'Expected, bust-inclusive'** (Quantity B, the mean over
every prospect at the grade with zeros kept). They never share a column. The two-sentence note on
why they differ is copy item B-TRAP (section 8).

HARD RULE (round 4, orchestrator ruling R2), verbatim: "nothing is computed by consensus-FV cell before PROSPECT_ANCHOR_LOOK; the served anchor table (in part a realized table) is printed exactly as served with its provenance".

Before PROSPECT_ANCHOR_LOOK's record exists (`docs/PROSPECT_ANCHOR_GATE.md` section 18), the page
shows only published industry tables and served configs read at grades 20 to 80 through the three
served functions `value_framework.fv_to_prime_war`, `value_framework.fv_to_6yr_avg_war` and
`value_framework.p_bucket_given_fv`. It reads no debuts, cohorts or outcomes. The FV 35 and 40 cells
are not held back: they print as served, with the provenance sentence. After the look, only what
its record releases (TL_24, behind `SCOUTING_ANCHOR_COLUMN_LIVE`).

### 3.1 The FV tier table (the headline, TL-Q7)

One row per FV g in 20, 25, ..., 80 (13 rows). Columns, left to right:

| column | group | source | values |
|---|---|---|---|
| FV | | the row's grade | integer |
| Role: hitter / starter / reliever | If he arrives | McDaniel 2014 combined table, 3.1, S3 | published text; 20 and 25 print 'not published'; relievers 65 and up print 'n/a' as the source does |
| Prime-season WAR (our table) | If he arrives | served `fv_to_prime_war(g)` | WAR, one decimal; g below 35 prints 'no table' (the table starts at 35; the function clamps there and the clamp is not a value) |
| WAR per season, first six seasons (our valuation table) | Expected, bust-inclusive | served `fv_to_6yr_avg_war(g)` | WAR, one decimal; every g prints |

Table notes, in order: the 'If he arrives' note (B-A-NOTE); under the expected column the
provenance sentence (B-PROV), the calibration line (B-CAL) and the reconciliation note (B-REC),
each verbatim; the page form of the hard rule (B-HARD).

**What `fv_to_prime_war` is.** `value_framework_config.yaml` at '# PRIME / TALENT anchor' calls it
"FV -> peak-season annual WAR for a player who STICKS and plays a full prime season", a display
anchor of industry shape (35 0.3, 50 1.7, 60 3.0, 80 6.5). That is a peak reading (framework 7.1
calls it Quantity A-prime; 6.4 D4), not the primers' six-season average, so its column is labelled
'prime season' and the note says the primers read FV as a six-season average. It is still not
bust-inclusive, so it sits under 'If he arrives'.

**What `fv_to_6yr_avg_war` serves (round 4, ruling R1).** It reads
`data/value_framework_fitted.json` `empirical_anchors.anchors` while
`anchor_calibration.use_empirical` is true (it is, at 'use_empirical: true'), and falls back to the
yaml table only when that key is absent; the yaml comment at '# v47' describes only that fallback
seed. EPOCH_RUN step J ran `value_framework.py --fit` and then re-applied the sub-45 knots,
re-measured on the fWAR label, recording that in `anchors_provenance`. No task of this program
re-applies the knots, edits `anchors_provenance` or runs `--fit`: that is step J's alone.

The provenance sentence is this TEMPLATE, verbatim, with its four slots filled at build time by
TL_22 from the fit file as it stands after step J:

> 45 and up: the {Y0}-{Y1} average ({N} players), blended half and half with the public Edwards scale, more public weight where a tier is thin, the top tier the public scale alone; 35 and 40: re-measured on {LABEL} without a blend; below 35: a floor, not a measurement.

- {Y0} and {Y1}: `empirical_anchors.cohort_window`.
- {N}: `empirical_anchors.n_cohort`, printed with a thousands comma.
- {LABEL}: the label the post-step-J `anchors_provenance` names for the 35 and 40 knots. Under owner
  answer EPOCH-Q4 it is FanGraphs WAR, written 'FanGraphs WAR'; the displayed WAR stays eWAR.
- 'half and half' holds only while `policy_digest.blend_weight_public` is 0.5.
- 'the top tier the public scale alone' is not pinned: tier counts live in `diagnostics`, which
  no test of this page reads.

Example, labelled as an example (this task runs after the step Z entry, so it may print one). Read
at HEAD 1b947cf5 from the post-step-J fit file (`empirical_anchors.generated_at`
2026-10-03T16:35:15; `cohort_window` [2014, 2020]; `n_cohort` 3463; `blend_weight_public` 0.5;
`anchors_provenance` opens "SUB-45 KNOTS RE-AMENDED 2026-10-03 for the fWAR LABEL EPOCH" and records
"RE-MEASURED ON THE fWAR LABEL (published FanGraphs WAR"):

> Example, not pinned here: 45 and up: the 2014-2020 average (3,463 players), blended half and half with the public Edwards scale, more public weight where a tier is thin, the top tier the public scale alone; 35 and 40: re-measured on FanGraphs WAR without a blend; below 35: a floor, not a measurement.

TL_22 re-reads the file at its own build, copies the marker substrings it finds into the test and
fills the template from that read; this example does not bind it.

**The calibration line** (round 4, intent 4; `docs/PROSPECT_ANCHOR_GATE.md` 10.1 copy limits),
verbatim under the expected column:

> This column is the table our valuations use today. It is under a registered calibration test, the Prospect Anchor gate, and it is not a measured result until that test reads.

No copy on the page calls the anchor accurate or validated.

**The reconciliation note**, verbatim beside it:

> The glossary's methodology table prints the configuration's starting values for this table until the Prospect Anchor gate moves that table to what serves; this page prints what serves.

It carries no number, so the exporter reads nothing new for it. Fact behind it, checked at this
HEAD: `data/value_framework.json` `fv_to_6yr_avg_war` is the yaml seed (35 0.12 ... 80 3.8), which
`assets/glossary.js` draws for 'the FV to WAR table' (`_vizFvWar`); the gate's 12.1 flip repoints
that emitter at the served function.

### 3.2 Published: if he arrives

Transcribed exactly as published (no re-rounding), rows 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30,
20:

| column | framework section | source |
|---|---|---|
| McDaniel 2014: WAR per season, true talent | 3.1 | S3 (repeated in L10) |
| FanGraphs primer, hitters: WAR per season over the first six seasons, band | 3.2, 3.4 | S2 (2018), L7 (2022, identical bands) |
| FanGraphs primer, starters: same, band | 3.3, 3.4 | S2, L7 |

A cell the source does not publish prints 'not published'. Then the 2022 low-end role tables:
hitters 30 to 45 with the plus tiers (3.5, L7) and relievers 30 to 50 (3.6, L7), role text and the
source's examples as printed.

### 3.3 Published: expected, bust-inclusive

The Clemens 2026 table as the framework records it (7.2, L1): rows 70, 65, 60, 55, 50, 45+, 45, 40+,
40, 35+; columns hitter expected WAR, hitter star odds, pitcher expected WAR, pitcher star odds.
Expected WAR is the team-control total, undiscounted, not per season; the dollar column is not
printed (the page is about WAR). Values exactly as published (0.75 stays 0.75).

### 3.4 Chance of each outcome by FV

Two tables, hitters and pitchers. Rows g in 20, 25, ..., 80; columns the five buckets of
`value_framework_config.yaml` `buckets` with Clemens 2025's names and bands (7.7, L6): Washed out
(under 0.5 WAR), Backup (0.5 to 1.5), Regular (1.5 to 2.5), Above average (2.5 to 4), Star (4+).
Cells: served `p_bucket_given_fv(g, is_pitcher)` in percent, nearest integer (after rounding a row can sum to 99 or 101;
the note says so).

What this function is: the value framework's mixture weights, an ordered-logit curve fit on Clemens
2025's published table (yaml `p_bucket_given_fv_hitter` and `_pitcher`, rows 45 to 60; 65 and up
excluded as too thin) and extended outside that range. It is read at a consensus FV. PROSPX's odds
column serves a Platt-recalibrated version at the eFV grade (registry row
`xfv_odds_calibration_slope`), so the two differ by design and the note says so.

Beneath, the published Clemens 2025 shares (7.7, L6), hitters and pitchers, rows 45 to 80 as
published with the source's counts, so the curve's training rows are visible.

## 4. Section C: stat lines by tool grade

Per tool, the FanGraphs framework estimate in the stat's published unit, labelled 'FanGraphs
framework estimate' with author and year, and our measured value only in cells that PASSED Part T
(TL_21, `data/tool_tables_rederived_eval.json`), with n and interval. Tool grades print as integers.
Published values print exactly as published; a disclosed floor prints as the floored value with
the source's value in the note.

| tool | stat | FanGraphs framework estimate printed (section, source) | Part T cell | measured column |
|---|---|---|---|---|
| hit | AVG | 'Batting Avg' at maturity, 30 to 80 by 5 (2.1, S3); beside it, Smith's BA, 20 to 80 by 10 (2.2 '### Hit tool', W2) | 3, hit to AVG | on PASS only |
| hit | K% | none published (2.1: the hit column is batting average only) | 4, hit to K% (incumbent: the grade-blind league line, never printed as an estimate) | on PASS only; otherwise nothing prints |
| game power | HR | 'Homers' per full season at maturity, band, 30 to 80 by 5 (2.1, S3); 80 is '40+' | 1, game_pwr to HR per 600 PA | on PASS only, labelled per 600 PA |
| game power | ISO | Smith's ISO column, 20 to 80 by 10 (2.2 '### Power tool', W2), labelled 'FanGraphs framework estimate (Smith, 2013)'; the 20 row prints .000 with the source's -.013 in the note | 2, game_pwr to ISO | on PASS only |
| raw power | exit velocity | none published by any outlet (2.1 note; TOOL_GRADE_TABLES 2.9) | none (secondary cell, no verdict) | never |
| speed | SB | Smith's SB per season, 20 to 80 by 10 (2.2 '### Speed tool', W2); 20 and 30 print 0 with the source's -20 and -10 in the note; 40 is blank in the source and prints 'blank in source'; beside it, the run-time scale: home to first RHH and LHH, 60-yard dash, 30 to 80 by 5 (2.1, S3) | 5, speed to SB per 600 PA | on PASS only, labelled per 600 PA |
| field | fielding runs | Smith's UZR/150 and Fld per season, 20 to 80 by 10 (2.2 '### Defense tool', W2) | none (OAA is a secondary cell, no verdict) | never |
| fastball | velocity | 'Fastball Velo', mph, 30 to 80 by 5 (2.1, S3); beside it, Smith's SP and RP velocity, 20 to 80 by 10 (2.2 '### Fastball velocity, split by role', W2) | 7, fb to velocity (SP) | on PASS only, starters |
| command | BB% | Smith's SP and RP BB%, 20 to 80 by 10 (2.2 '### Control', W2); lower is better | 6, cmd to BB% (SP) | on PASS only, starters |

**A PASS cell** (Part T, T.6) prints beside the estimate, labelled 'measured on debuted players',
at each non-thin bin of the candidate table: the smoothed value, the bin's n and its 95% interval
(T.5's percentile bootstrap on the bin median over FIT players), plus one verdict line with both
MAEs and the holdout n, and the survivorship sentence. Copy never says our table is more accurate
for a cell that did not pass. `FAIL` and `NOT COMPUTABLE` cells print the estimate alone (or nothing,
for K%) with the matching copy item. Secondary cells (raw power to exit velocity, speed to sprint
speed, field to OAA, reliever BB% and velocity) and the beside columns never print as measured
values.

**Tools with no ground truth** (TOOL_GRADE_TABLES '### 2.11'), listed in copy item C-NOGT: throw
and arm strength, pitch selection, bat control, delivery, athleticism and frame; slider, curveball
and changeup (indirect only, whole-arsenal outcomes). W2's arm table (outfield arm runs) is named in
the note and not printed as a tier table, because its author disclaims it.

## 5. Section D: how eephus uses grades

- Consensus FV and 20-80 tool grades display rounded up to the whole grade (ceiling): 62.1 prints
  as 63. On this page every grade is already a whole number, so the rule changes nothing printed.
- eFV, our model grade, rounds to the nearest whole grade, and so do plus stats.
- Our consensus maps MLB Pipeline and Baseball America grades onto the FanGraphs scale before it
  combines sources (framework Part 11; `grade_normalization`). TL_22 confirms this against
  `grade_normalization.py` and `consensus.py` at its HEAD and deletes the sentence if it does not
  hold.
- Links: the Library (`/glossary/`), PROSPX (`/prospx/`), Source Accuracy
  (`/glossary/#view=source-accuracy`).

## 6. Number-source map

Every number on the page maps to a registry row id in `data/model_registry.json`. TL_22's
`sources` array in `data/scouting_reference.json` carries, per block, the row id, the file or
function read, and the framework section and source id for transcribed values.

| page block | what is read | registry row |
|---|---|---|
| A, adjective table and SD column | transcription, framework 1.3, 11.1, 11.2 | `scouting_reference` (new, TL_23) |
| B 3.1, role text | transcription, 3.1 | `scouting_reference` |
| B 3.1, prime-season WAR | served `fv_to_prime_war` (yaml `fv_to_prime_war`, a display config of industry shape) | `scouting_reference`; no registry row serves this config today (finding F2) |
| B 3.1, WAR per season, first six seasons | served `fv_to_6yr_avg_war` | `fv_to_war_anchors` (its pending calibration test: `prospect_anchor`) |
| B 3.2, 3.3 and the published 7.7 shares | transcription, 3.1 to 3.6, 7.2, 7.7 | `scouting_reference` |
| B 3.4, outcome chances | served `p_bucket_given_fv` | `prospect_surplus` (the career-path mixture these weights feed); `xfv_odds_calibration_slope` named for the PROSPX difference |
| C, FanGraphs framework estimates | transcription, 2.1, 2.2 | `scouting_reference` |
| C, tools with no ground truth | `docs/efv-2026-07-30/TOOL_GRADE_TABLES.md` 2.11 | `tool_grade_tables` |
| C, measured PASS cells | `data/tool_tables_rederived_eval.json` | `tool_tables_rederived` (row lands with TL_21) |

The new row `scouting_reference` (written by TL_23 through the idempotent registry script):
descriptive, not a forecaster; surface `/scouting/`; predicts 'nothing forward: published 20-80
tables transcribed with section and source ids, plus served value-framework configs read at grades
20 to 80'; eval artifact `data/reference/fv_framework_tables.json` (the transcription TL_22
commits, every cell carrying its framework section id and source id); freshness is the commit of
`docs/reference/FANGRAPHS_FV_FRAMEWORK.md` (`07abfc82`, 2026-07-30, at this HEAD); verdict
`provisional`, the registry's word for a measured-but-descriptive row (its enum has no word for a
reference), with that reason in its notes.

The transcription's scope: framework 1.3, 2.1, 2.2, 3.1 to 3.6 (as TL_22's specification lists),
plus 7.2, 7.7, 11.1 and 11.2, which sections A and B print. It is a reference, not a model output,
and is committed, not generated.

## 7. Flags

- `SCOUTING_PAGE_LIVE` in `build_site.py`, default False. While False, `tools/scouting_export.py`
  writes only `.cache/scouting/preview/scouting_reference.json` and the generator writes only
  `.cache/scouting/preview/scouting/index.html`; nothing under `data/` or the served tree changes
  (byte-identical, asserted). The nav entry and the sitemap row are emitted only when it is True
  (`sitemap_pages()`); the three static navs cannot read a flag and change only in TL_23's flip
  commit (round 4, intent 5).
- `SCOUTING_ANCHOR_COLUMN_LIVE`, default False, TL_24's: a third FV tier column only if the Prospect
  Anchor look's record releases a table for display.
- The flip is one commit (TL_23): the flag, `data/scouting_reference.json`, the generated page, the
  nav and sitemap row, the static navs, the icon, the inbound links, the registry row and the
  glossary entries (scouting scale, Future Value tiers, tool-implied production), naming every new
  key, file and row count.
- The exporter's second output path (`.cache/scouting/preview/` and `data/`) is redirected to a tmp
  path in the tests in the same commit that adds it.

## 8. Copy

Every reader-facing string, keyed for the tests. Rules: no em or en dash; none of
`tools/copy_lint.py`'s BAN words or `docs/COPY_STYLE.md` hallmarks; no hedge without a number; no
forecast word on a descriptive number; no caps emphasis; no internal identifier; body sentences 25
words or fewer except the verbatim items. Quoted published text keeps author, year and a link to
the source URL in the framework's 'Sources read' table. Citations in copy are author and year
(source ids stay in this document and the payload).

### 8.1 Head

- TITLE: Scouting - eephus.io
- H1: Scouting
- LEDE: The 20-80 scale, WAR by FV tier and the stat line each tool grade implies, with sources
- META (share card): How the 20-80 scouting scale works: what each FV tier means in WAR and each tool grade in stats, sourced.

### 8.2 Section A

- A-HEAD: The 20-80 scale
- A-1: 50 is major league average, and each 10 points is one standard deviation from it (McDaniel 2014; Longenhagen and McDaniel 2018).
- A-2: Three deviations each way hold 99.7% of a normal population, so the scale runs from 20 to 80 (McDaniel 2014).
- A-3: The population is major league players, not all of baseball (Longenhagen 2022).
- A-4: Both ends are censored: an 80 means three deviations above average or more, and a 20 means three below or less (Longenhagen 2022).
- A-5: At three deviations, an 80 is about 1 player in 1,000; about 750 players open a season on major league rosters (Smith 2013).
- A-6: Scouts grade in 45 and 55 around average, where players cluster; 35 and 65 come mostly from analysts reading measured data (Longenhagen and McDaniel 2018).
- A-7: Where 50 sits depends on the population counted: a league-average hitter over 550 plate appearances is worth 2.0 WAR (Cistulli 2013).
- A-8: FanGraphs defines the scale by standard deviations; Baseball America and MLB Pipeline publish adjectives without that claim (Glaser; MLB.com glossary).
- A-9: Some clubs grade on a 2-8 scale with no half grades, and all three outlets say so.
- A-TBL-CAP: Adjectives by grade, as each outlet publishes them
- A-TBL-COLS: Grade | SD from average | FanGraphs (McDaniel 2014) | Baseball America (Glaser) | MLB Pipeline (MLB.com glossary)
- A-TBL-NOTE: A blank cell is blank in the source. FanGraphs names no grade below 45, and MLB Pipeline bands 20 to 30 and 70 to 80.
- A-10: Each tool carries a present and a future grade, written present/future: 20/50 is a present 20 and a future 50 (McDaniel 2014).
- A-11 (quoted, McDaniel 2014, on Joey Gallo): "Hit: 30/45, Game Power: 60/70, Raw Power: 80/80, Speed: 40/40, Field: 45/50, Throw: 70/70"
- A-12: FV, Future Value, is one 20-80 grade for the whole player, with risk and distance from the majors inside it (Longenhagen and McDaniel 2018).
- A-13: Hitters carry five tools: hit, power, run, field and throw. Pitchers carry a grade per pitch plus command (McDaniel 2014).
- A-14: Power splits into game power, home runs per full season at maturity, and raw power, the deepest batting-practice shot (McDaniel 2014).

### 8.3 Section B

- B-HEAD: WAR by FV tier
- B-1: FanGraphs maps FV to average annual WAR over a player's first six major league seasons, not a peak season (Longenhagen and McDaniel 2018).
- B-TRAP (the two-sentence note, pinned): 'If he arrives' is WAR for a player who reaches his projected role; 'Expected, bust-inclusive' averages every prospect at the grade, busts at zero. Reading one as the other overprices a 50 FV about two times and a 40 or 45 FV about three times (Longenhagen and McDaniel 2018; Clemens 2026).
- B-HARD: No number in this section is computed here from player outcomes by FV tier. The expected column prints our valuation table as served, in part a realized average, with its provenance.
- B-TBL-CAP: WAR by FV tier: two quantities, never mixed
- B-TBL-COLS: FV | Role: hitter / starter / reliever (McDaniel 2014) | If he arrives: prime-season WAR (our table) | Expected, bust-inclusive: WAR per season, first six seasons (our valuation table)
- B-A-NOTE: Our prime-season table gives WAR in a full prime season for a player who sticks, from FV 35 up. The FanGraphs primers read FV as a six-season average, and a player's peak season grades one to two grades above that (Longenhagen 2022).
- B-PROV: the TEMPLATE of section 3.1, filled by TL_22 at build time.
- B-CAL (verbatim): This column is the table our valuations use today. It is under a registered calibration test, the Prospect Anchor gate, and it is not a measured result until that test reads.
- B-REC (verbatim): The glossary's methodology table prints the configuration's starting values for this table until the Prospect Anchor gate moves that table to what serves; this page prints what serves.
- B-NOTABLE: no table (prime column, FV 20 to 30); not published (role text, FV 20 and 25)
- B-PA-CAP: Published: if he arrives
- B-PA-COLS: Grade | McDaniel 2014: WAR per season, true talent | FanGraphs primer, hitters: WAR per season over the first six (2018, 2022) | FanGraphs primer, starters (2018, 2022)
- B-PA-NOTE-1: McDaniel's 2014 table stops at 30. The primers publish no 25, 35, 65 or 75 row, and the 2022 starter table relabels its 30 row as 35/35+.
- B-PA-NOTE-2: In 2015 McDaniel read the 2014 column as a peak season; the 2018 and 2022 primers read FV as a six-season average (McDaniel 2015; Longenhagen 2022).
- B-ROLE-CAP: Roles at the low end, with the plus tiers (Longenhagen 2022)
- B-ROLE-NOTE: The 2022 reliever table stops at 50, no-doubt closers; McDaniel's 2014 table stopped relievers at 60.
- B-PB-CAP: Published: expected, bust-inclusive (Clemens 2026)
- B-PB-COLS: FV | Hitters: expected WAR, team-control total | Hitters: star odds | Pitchers: expected WAR, team-control total | Pitchers: star odds
- B-PB-NOTE-1: Expected WAR is the total, undiscounted WAR over team control, averaged over every prospect at the grade, including those who never reached the majors.
- B-PB-NOTE-2: A star posts two or more seasons of 4+ WAR in team control. The table has no 75 or 80 row (Clemens 2026).
- B-PB-NOTE-3: Our column is per season and this one is a team-control total, so the two sit on different scales.
- B-PO-CAP: Chance of each outcome by FV, hitters (and: Chance of each outcome by FV, pitchers)
- B-PO-COLS: FV | Washed out (under 0.5 WAR) | Backup (0.5 to 1.5) | Regular (1.5 to 2.5) | Above average (2.5 to 4) | Star (4+)
- B-PO-NOTE-1: Each outcome is WAR in one projected season three years after the grade, per 600 PA or 200 IP (Clemens 2025).
- B-PO-NOTE-2: The curve is fit to Clemens's published rows from 45 to 60. Outside that range it extends the fit, with no published row under it.
- B-PO-NOTE-3: These are our valuation's outcome weights at a consensus FV. PROSPX odds apply a further calibration at the eFV grade, so they differ.
- B-PO-NOTE-4: Shares are rounded to the nearest point, so a row can sum to 99 or 101.
- B-PL6-CAP: Published: outcome shares by FV (Clemens 2025)
- B-PL6-NOTE: Counts are graded prospects. The rows above 60 rest on one to three prospects each.

### 8.4 Section C

- C-HEAD: Stat lines by tool grade
- C-1: Each tool grade implies a stat line. The published scales are estimates, labelled FanGraphs framework estimate with author and year.
- C-2: A measured column appears only where our re-derived table beat the estimate on the 2026 season in a registered test.
- C-SURV (beside every measured value): Only players who reached the majors have an MLB stat line, so a measured value describes debuted players' MLB seasons, not every graded prospect.
- C-EST-LABEL: FanGraphs framework estimate ({author}, {year})
- C-ISO-LABEL (verbatim): FanGraphs framework estimate (Smith, 2013)
- C-MEAS-LABEL: measured on debuted players
- C-PASS: Measured on debuted players' MLB seasons, 2015 to 2025, 2020 excluded. On the 2026 season it beat the estimate: MAE {cand} against {inc}, n {n}.
- C-FAIL: Our re-derived table did not beat this estimate on the 2026 season, so the estimate stands.
- C-NC: Too few 2026 seasons to test our re-derived table, so the estimate stands.
- C-K-NONE: No outlet publishes a strikeout rate by hit grade, and our re-derived table did not clear the 2026 test, so no number prints.
- C-VOID (if Part T's record is VOID or absent): The 2026 test of our re-derived tables did not report, so the estimates stand.
- C-HIT-HEAD: Hit
- C-HIT-NOTE: Batting average at maturity (McDaniel 2014), with Smith's 2010 to 2012 averages beside it. The hit grade covers batting average, so patient hitters rank above their hit grade (McDaniel 2015).
- C-GP-HEAD: Game power
- C-GP-NOTE-1: Home runs per full season at maturity; an 80 is 40 or more (McDaniel 2014).
- C-GP-NOTE-2: Smith's 20 row reads -.013, which he calls a glitch; it prints as .000.
- C-RP-HEAD: Raw power
- C-RP-NOTE: No outlet publishes a raw power scale in exit velocity or distance. Scouts grade it on the deepest batting-practice shot (McDaniel 2014).
- C-SP-HEAD: Speed
- C-SP-NOTE-1: Run times are seconds, lower is faster, and the left-handed column sits 0.10 seconds faster at every grade (McDaniel 2014).
- C-SP-NOTE-2: Smith's stolen-base column reads -20 and -10 at 20 and 30, which no player posts; those rows print as 0, and his 40 row is blank.
- C-FD-HEAD: Field
- C-FD-NOTE: Smith pooled every position into one table, and his 50 row sits at +1.6, the qualified-player mean rather than zero (Smith 2013).
- C-FB-HEAD: Fastball
- C-FB-NOTE: Average fastball velocity in mph, with Smith's starter and reliever columns beside it. Baseball America's current scale sits about 2 mph higher (Glaser).
- C-CM-HEAD: Command
- C-CM-NOTE: Walk rate in percent; lower is better, so the rate falls as the grade rises (Smith 2013).
- C-NOGT: No measured scale exists here for arm strength, pitch selection, bat control, delivery, athleticism or frame. Slider, curveball and changeup grades have only whole-arsenal outcomes to read against, so no scale prints for them.
- C-ARM: FanGraphs' one arm table counts outfield arm runs, and Smith says it measures the wrong thing (Smith 2013).

### 8.5 Section D and footer

- D-HEAD: How eephus uses grades
- D-1: Consensus FV and tool grades print rounded up to the whole grade: 62.1 prints as 63.
- D-2: eFV, our model grade, rounds to the nearest whole grade, as do plus stats.
- D-3 (deleted by TL_22 if it does not hold at its HEAD): Our consensus maps MLB Pipeline and Baseball America grades onto the FanGraphs scale before combining sources.
- D-4: Definitions live in the Library, player grades on PROSPX, and Source Accuracy compares each outlet's grades by cohort.
- FOOT: Sources: FanGraphs (McDaniel 2014 and 2015; Smith 2013; Cistulli 2013; Longenhagen and McDaniel 2018; Longenhagen 2022; Clemens 2025 and 2026), Baseball America (Glaser) and the MLB.com glossary, linked per table.

## 9. Tests TL_22 adds

In a new `test_scouting_page.py`, plus `test_build_site.py` and `test_asset_versioning.py`:

1. `test_flag_off_served_tree_byte_identical`: with `SCOUTING_PAGE_LIVE` False, a build writes
   nothing under `data/` or the served tree that differs from HEAD; the export lands only under
   `.cache/scouting/preview/` (redirected to a tmp path in the test).
2. `test_every_number_has_registered_source`: every numeric cell in the payload carries a `sources`
   entry whose row id resolves in `data/model_registry.json` (`scouting_reference` resolves from
   TL_23 on; before it, the test accepts that id only from the registered list in this document).
3. `test_fv_cell_guard_imports`, `test_fv_cell_guard_attributes`, `test_fv_cell_guard_literals`,
   `test_fv_cell_guard_fit_path_untouched`: the ast scan of `tools/scouting_export.py` and its
   direct imports. Allowed: the standard library and `value_framework`; from it only
   `fv_to_prime_war`, `fv_to_6yr_avg_war` and `p_bucket_given_fv`; never `fit_and_write`,
   `_fitted` or `empirical_anchors`. Forbidden: importing `empirical_anchors`, `efv_*`, `storage`,
   `consensus` or any module that opens prospects.db; a literal naming `data/debuts.json`,
   prospects.db, `value_framework_fitted`, `empirical_anchors`, a cohort, outcome or eFV file; a
   group-by on FV. The run with `value_framework.fit_and_write` and
   `empirical_anchors.derive_empirical_war_anchors` monkeypatched to raise leaves the output
   unchanged.
4. `test_fv_tier_block_keys_registered`: the FV tier block carries only the keys this document
   names and only the sources 'industry' and 'served_config' until TL_24.
5. `test_provenance_sentence_matches_fit_file`: reads only `cohort_window`, `n_cohort`,
   `policy_digest.blend_weight_public` and `anchors_provenance` of
   `data/value_framework_fitted.json` `empirical_anchors` (never `anchors` or `diagnostics`), and
   `anchor_calibration.use_empirical` from the yaml. Asserts the printed sentence equals the
   section 3.1 template filled from the file; `blend_weight_public` is 0.5 while the copy says 'half
   and half'; both marker substrings copied at build are present; `use_empirical` is true (if false,
   the sentence must describe the yaml seed instead, and the test says so). On any mismatch it fails
   with exactly 'the fit file no longer matches the provenance sentence: change the copy', and that
   is its only remedy.
6. `test_calibration_line_and_reconciliation_note_verbatim`: B-CAL and B-REC appear verbatim on the
   page, beside the expected column; no copy on the page contains 'accurate' or 'validated' near
   the anchor.
7. `test_quantity_a_and_b_never_share_a_column`: every column of every section B table is tagged A
   or B or neither, never both, and the A group precedes the B group.
8. `test_tool_cells_measured_only_on_pass`: a measured cell exists only where
   `data/tool_tables_rederived_eval.json` records PASS for that primary cell; secondary and beside
   cells never print as measured; K% prints no estimate.
9. `test_iso_column_labelled_estimate`: the game power to ISO column carries 'FanGraphs framework
   estimate (Smith, 2013)' and the 20 row prints .000 with its note.
10. `test_grades_integer_war_one_decimal`: FV and tool grades print as integers (ceiling at the
    display boundary); served WAR prints one decimal; transcribed values print exactly as the
    transcription carries them; percentages nearest integer.
11. `test_static_constants_match_config`: the exporter's copy constants that mirror the yaml (the
    five bucket bands, the prime table's lowest grade 35) equal `value_framework_config.yaml`; the
    test reads the yaml, the exporter never does.
12. `test_scouting_copy_lint`: the page's copy passes `tools/copy_lint.py` (served rules) and the
    dash check.

## Findings at registration (for TL_22 and TL_23; nothing here is fixed by this commit)

- F1. `fv_to_prime_war` is a peak-season reading (Quantity A-prime), while TL-Q7's question text
  called it per-season WAR for a player who reaches his role. The owner's answer still holds (both
  columns, arrives first); the column is labelled 'prime season' and B-A-NOTE says how it differs
  from the primers.
- F2. No registry row serves `fv_to_prime_war` (rows mentioning it: `fv_outcome_curves`, not
  shipped). Default here: map it to `scouting_reference`, with the row's notes naming it as a
  served display config. A separate `fv_to_prime_war` row is the alternative (owner question 2 in
  the task report).
- F3. The `fv_to_war_anchors` registry row's summary and champion still read "2017-2020 cohorts";
  the fit file it points at carries `cohort_window` [2014, 2020] and `n_cohort` 3463 after step J.
  TL_23 corrects that text through the idempotent registry script when it adds
  `scouting_reference`.
- F4. The glossary module displays as the Library; B-REC's verbatim 'glossary's' names its URL
  and data file, not its display name (owner question 1 in the task report).
- F5. Served per-season WAR at one decimal prints FV 20 to 35 as 0.0 and FV 40 as 0.1 on the
  expected column; that is the served value rounded, not a hidden cell (owner question 3 in the task
  report).

## Defaults taken by this registration

- D1. Section B is one headline table with the two quantities as two column groups, 'If he arrives'
  left of 'Expected, bust-inclusive' (TL-Q7's answer), with the published industry tables printed
  in full beneath it rather than as extra columns, so the headline stays readable at 390 px.
- D2. The prime-season column prints 'no table' below FV 35 instead of the function's clamped value.
- D3. `fv_to_prime_war` maps to `scouting_reference` (F2).
- D4. `p_bucket_given_fv` maps to `prospect_surplus`, with `xfv_odds_calibration_slope` named for
  the PROSPX difference.
- D5. The transcription adds framework 7.2, 7.7, 11.1 and 11.2 to the sections TL_22's
  specification lists, because sections A and B print them.
- D6. Section C prints FanGraphs framework tables only; Baseball America's bands appear in notes,
  not columns (Part T reads no BA table either).
- D7. Served WAR at one decimal, as TL_22's specification says (F5).
- D8. `scouting_reference` takes the verdict `provisional`, with the reason in its notes.
- D9. The page embeds `data/scouting_reference.json` at build time and fetches nothing at run
  time, like `/sources/`; the payload still ships under `data/` for readers and tests.

## What this document does not do

It builds nothing, writes nothing under `data/`, adds no flag, no route, no registry row and no
glossary entry; it reads no debut, cohort or outcome; it computes nothing by consensus-FV cell; it
does not re-apply anchors, edit `anchors_provenance` or run `value_framework.py --fit`.

---

## Amendment 2026-10-15 (TL_23_SCOUTING_PAGE_FLIP): B-CAL after the Prospect Anchor look

Filed by TL_23_SCOUTING_PAGE_FLIP in the flip commit. It changes one copy item and nothing else:
no table, source, flag, frame, cell or test criterion moves.

Why. Section 8's B-CAL was written before the Prospect Anchor look and says the expected column
"is not a measured result until that test reads". The look was taken once on 2026-10-14, an
OWNER-WAIVED EARLY READ under EW3-5, and `docs/PROSPECT_ANCHOR_GATE.md` section 18 records the
verdict UNDECIDED: nothing served moves, the question re-arms under a new registration when
`RESOLVED_THROUGH` reaches 2027 (the 2022 debut cohort resolves), and "UNDECIDED is not a
confirmation and no copy may treat it as one". Printing the old sentence after the look would
describe a test that has not read. The page prints no number from the look (TL_24 owns any
release, and an UNDECIDED record releases nothing for display), so the FV tier block still
carries only the sources 'industry' and 'served_config'.

- B-CAL (verbatim, replaces the section 8 text from TL_23 on): This column is the table our valuations use today. Its registered calibration test, the Prospect Anchor gate, read it once on 2026-10-14 and could not decide it, which is not a confirmation. The question opens again once the 2022 debut cohort resolves.

B-REC is unchanged: under UNDECIDED the gate does not repoint the glossary's emitter, so the
glossary keeps printing the configuration's starting values and the sentence still holds.
