# eTools amendment 4: eTools for stale-graded players (does the gain hold when the consensus grade is old?)

Registration status: REGISTERED

Task ETOOLS_STALE_GRADES (owner decision EW3-46, 2026-10-19, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`:
"ETOOLS_STALE_GRADES extends eTools to board players whose latest tool grade predates the 2026
lists (e.g. justin_riemer, FG 2024-08-01), checking first that each tool's gain holds on
stale-grade rows; tooltip names the scouting grade's date"), written 2026-10-19 on lane
wt-ETOOLS_STALE_GRADES (base 1ea310d8). Docs only, committed alone before any statistic named here
is computed. It amends `docs/tools-2026-10/ETOOLS_GATE.md` (registered 3f240da6, look dc271ac2) and
follows amendments 1 to 3. Timing: an OWNER-WAIVED EARLY READ under EW3-5 (no look day applies).

## 0. Why, and what was already seen

The served eTools (`data/etools.json`, `etools.build_preview`) cover only players with a tool grade
on a 2026 list: `etools.live_rows` reads each outlet's latest snapshot dated on or after
`LIVE_FROM` (2026-01-01), 1,632 players. The eFV board (`data/xfv.json`, kind active, 4,691
players) carries older grades forward, so a player whose last tool grade is from an earlier list
shows that consensus grade with no eTool. Example: justin_riemer, FanGraphs only, last
2024-08-01, hit 70.

**Seen before this document** (all published): every look, review, flip-prep and amendment 3
number in `docs/tools-2026-10/ETOOLS_RESULTS.md`, including the fresh-row re-centred eTool reads
this amendment cites as its fresh reference (amendment 2 F1.6: eHIT +0.302 / +0.274, ePOW +0.033 /
+0.039, eSEL +0.089 / +0.071, eBAT +0.092 / +0.080, eFB +0.067 / +0.176, eCMD +0.041 / +0.073,
MLB / minors) and the fresh-row L_ANY reads (F2.2). **No statistic on a stale-graded row has been
computed by anyone.** Every development row before this amendment carried a board-year grade.

**Counted by this lane before writing** (`python etools_stale.py --check`: rows, grade ages and
label presence; no grade or candidate was paired with a label value). The stale frame (section 1)
holds 6,333 (board year, player) rows after identity and the pre-debut rule (7,062 dropped for an
MLB line before the board year; 15,284 tool slots dropped because the carried-forward grade would
come from a 2020 or 2021 list, 1.3). Per passing tool, rows and the 12-month stratum (S12, 1.4):

| tool | stale rows (players) | S12 rows | S12 with L_MLB (players, years of 20+) | S12 with L_UM | S12 with L_ANY |
|---|---|---|---|---|---|
| hit | 2,971 (868) | 2,739 | 105 (63, 1) | 694 (365, 10) | 951 (515, 10) |
| game_pwr | 2,970 (868) | 2,738 | 105 (63, 1) | 693 (364, 10) | 950 (514, 10) |
| pitch_sel | 365 (249) | 119 | 3 (3, 0) | 22 (22, 1) | not covered |
| bat_ctrl | 398 (267) | 136 | 3 (3, 0) | 24 (24, 1) | not covered |
| fb | 2,638 (798) | 2,382 | 205 (125, 5) | 652 (355, 9) | 866 (476, 9) |
| cmd | 2,637 (797) | 2,382 | 205 (125, 5) | 652 (355, 9) | 866 (476, 9) |

Grade age at the read date, all stale rows of hit: quartiles 465, 1,195 and 2,290 days. The live
stale cohort (section 6) on the eFV board: hit and game power 287 players, pitch selection 227,
bat control 242, fastball and command 233; every one 12 or more months old today (age quartiles
445, 635 and 809 days for hit).

So, from presence alone: **L_MLB is not computable on S12 for hit and game power** (63 players;
stale-graded players rarely debut), and **pitch selection and bat control are not computable on any
label** (no tracked chase or zone-contact label for 22 to 24 players).

## 1. Frames

1.1 **Development board years only**, gate 1.1: 2011 to 2019 and 2022 to 2024; 2020 and 2021 are
never board years here.

1.2 **Fresh rows**: the look's frame, unchanged (`etools.load_board`, `build_universe`,
`tool_frames`): the board-year consensus G_c from snapshots dated in [Y-01-01, Y-05-01).

1.3 **Stale rows.** For board year Y and player, for each tool that NO outlet graded in the
board-year window: each outlet's latest grade for the tool dated before Y-01-01 (parsed as gate
1.2 and 0.4); the carried-forward consensus G_s is their unweighted mean rounded to 0.5 (the
consensus rule). A tool whose latest pre-window grade at any outlet is from a 2020 or 2021 list is
dropped for that row (R-LV; never an older substitute). Identity, the pre-debut rule and the side
exactly as gate 1.3; a stale row whose (Y, player) has a fresh row on the other side is dropped.
Candidates are read as of Y exactly as for fresh rows (gate 3.1: seasons up to Y - 1).

1.4 **Grade date and age.** The grade date is the latest date among the outlet grades averaged;
the age is the read date minus the grade date, the read date May 1 of the board year (the end of
the gate 1.2 window). Strata: **S12**, age 365 days or more (deciding); **U12**, under 365 days;
**ALL**, every stale row. Descriptive age cells inside S12: 365 to 729 days and 730 or more.

1.5 **Never** a stratum, cell, key, filter or weight by consensus FV or any source's FV
(`docs/PROSPECT_ANCHOR_GATE.md`). Tool grades and grade age are covariates or strata only.

## 2. Labels

2.1 L_MLB (gate 2.1) and L_UM (gate 2.2), unchanged, with their survivorship caveats.

2.2 **L_ANY** (amendment 2 F2.1, unchanged: the X1-translated line at any Minor League level,
seasons Y to Y + 2 capped at 2024, 300 PA or 150 BF) for hit, game power, fastball and command.
It needs no promotion, which matters here: stale-graded players are mostly players who left the
lists.

2.3 Computable: gate 2.3 (100 players, 3 board years of 20 or more rows), on the stratum's rows.

## 3. The stale eTool (the served construction, out of fold)

3.1 For each passing tool t (hit, game_pwr, pitch_sel, bat_ctrl, fb, cmd) with the look's admitted
set S (unchanged), and each board year Y holding stale rows: the gate 5.1 fit on the FRESH rows of
the other board years with every year-Y player (fresh or stale) removed; applied to the year-Y
stale rows: u_j = z_j - (a_j + b_j G_s), eTool = clamp(G_s + sum_j c_j (u_j - delta_j), 20, 80).

3.2 **Re-centring** (amendment 2 F1.5, the served construction for all six): delta_j = the mean
residual over the FRESH year-Y rows carrying j minus the training rows' mean. The stale rows are
NOT re-centred on themselves: players who fall off the lists may differ from the grade in a real,
systematic way, and centring on them would erase it. Live, this is the fresh 2026 cohort's shift
(section 6). The uncentred stale eTool is reported beside it and decides nothing.

3.3 **Grade age is a stated input, not a fitted term.** The served record carries the grade's date
and age (section 6); no age term enters the fit (an age interaction would be a new model and needs
its own registration).

## 4. The statistic and the rule

4.1 Gate 5.2 on the stratum's stale rows: d_E = rho_w(stale eTool) - rho_w(G_s) per label,
within-board-year Spearman, player-clustered bootstrap B 2000, seed 20261023 with the amendment 2
F3.2 re-ranked draws (`etools.paired_d`); one-sided 95% lower bound (LB).

4.2 **HOLDS** for tool t when, on S12, the LB is above 0 on L_UM AND on the second label, where the
second label is L_MLB when L_MLB is computable on S12, else L_ANY (hit, game power, fastball,
command). A tool with L_UM or both second labels not computable on S12 cannot hold (NOT
COMPUTABLE). The other computable label is reported beside the verdict and decides nothing.

4.3 Reported, deciding nothing: U12 and ALL with the same statistic; the uncentred stale eTool on
S12; the two S12 age cells; the fresh reference (amendment 2 F1.6, cited, and its point d
reproduced to 5e-5 before any stale statistic, else the read stops).

## 5. Comparators (the rule needs them)

5.1 **Zero comparator.** Every sub-driver contribution set to 0: the eTool equals G_s and d_E must be
exactly 0 on every label (a plumbing identity, printed).

5.2 **Null comparator.** Each stale row's sub-driver vector permuted among the stale rows of its
board year, seed 20261025, through 3.1 and 4.2 on S12. If the null HOLDS under 4.2, the tool's
read is **VOID** (a leak), never a pass.

5.3 **Planted recovery.** A synthetic single sub-driver 0.25 x (z of the within-board-year rank of
L_UM + z of the rank of the tool's second label, 0 where a label is missing) + sqrt(1 - 0.125) x
z(noise), on the fresh rows (seed 20261026) and the stale rows (seed 20261027), each with the
missingness of the tool's first admitted sub-driver; through 3.1 and 4.2 on S12. A tool that does
not hold and whose planted check also fails is recorded **DOES NOT HOLD; UNDERPOWERED**: the design
could not certify a planted gain of that size, so the read is not evidence of no gain.

5.4 Verdicts: HOLDS, DOES NOT HOLD, DOES NOT HOLD; UNDERPOWERED, NOT COMPUTABLE, VOID.

## 6. What follows the verdict

- **HOLDS:** the tool is served for every live eFV-board player (data/xfv.json, kind active) whose
  latest consensus grade for it predates the 2026 lists: the carried-forward consensus (each
  outlet's latest grade before 2026-01-01; for live rows any list year), the admitted sub-drivers
  read through season 2026, the look's final fit, re-centred with the live FRESH cohort's shift
  exactly as `build_preview` applies it to the fresh players, so **no fresh player's eTool moves**.
  `data/etools.json` gains those records with `grade_date` and `grade_age_months`; the PROSPX card
  tooltip and eTools block name the scouting grade's date ("scouting grade from Aug 2024"). The
  eTool composite and eTools+ follow from `data/etools.json` by their own unchanged builders. A
  player with any 2026 grade for the tool is never touched.
- **Anything else:** stale-graded players keep the consensus grade for that tool, as now, and the
  results say so.

## 7. The one read

`python etools_stale.py --run --amend-sha SHA` refuses unless SHA names a commit carrying this file
as REGISTERED; it asserts no board year 2020 or 2021, no development grade from a 2020 or 2021 list,
no stale grade dated inside the board-year window, no L_MLB row with a first MLB season after 2024
and no FV-keyed grouping; it reads every input's sha256 at start and end. `--check` counts;
`--dry-run` runs the reporting path on fixtures. The read begins at the first statistic that pairs
a grade or candidate with a label; it runs once and `data/_labs/etools/etools_stale_reads.json`
carries a spent marker. On an exception after that point: no rerun, the read is recorded as spent,
and the question goes to the owner. Never `backtest.run_backtest`, `run_monthly` or `build_site`
from the runner; no network request.

## 8. Results

(Empty at registration. Results go to this section as a dated note and to
`docs/tools-2026-10/ETOOLS_RESULTS.md`.)

### 2026-10-19: THE READ, once (OWNER-WAIVED EARLY READ, EW3-5)

`python etools_stale.py --run --amend-sha dff62ea9`, run once (41 s, code at d3824ea8) after the
fixture dry run; no exception; every input's sha256 matched at start and end; stdout and stderr
kept in the task's output directory. Artifact `data/_labs/etools/etools_stale_reads.json` (spent
marker). The fresh-row re-centred d of all six tools reproduced amendment 2 F1.6 exactly (12 of
12). d is the out-of-fold within-board-year Spearman gain of the stale eTool over the stale
consensus grade; LB the one-sided 95% lower bound (B 2000).

| tool | S12 rows | L_MLB d (LB), players | L_UM consensus to eTool, d (LB), players | L_ANY consensus to eTool, d (LB), players | second label | verdict |
|---|---|---|---|---|---|---|
| hit | 2,739 | not computable (63) | 0.352 to 0.769, +0.417 (+0.340), 365 | 0.309 to 0.784, +0.476 (+0.404), 515 | L_ANY | **HOLDS** |
| game_pwr | 2,738 | not computable (63) | 0.463 to 0.557, +0.094 (+0.067), 364 | 0.395 to 0.548, +0.153 (+0.126), 514 | L_ANY | **HOLDS** |
| pitch_sel | 119 | not computable (3) | not computable (22) | not covered | none | NOT COMPUTABLE |
| bat_ctrl | 136 | not computable (3) | not computable (24) | not covered | none | NOT COMPUTABLE |
| fb | 2,382 | 0.279 to 0.231, -0.047 (-0.179), 125 | 0.133 to 0.384, +0.251 (+0.194), 355 | 0.095 to 0.409, +0.314 (+0.267), 476 | L_MLB | DOES NOT HOLD; UNDERPOWERED |
| cmd | 2,382 | 0.359 to 0.385, +0.025 (-0.053), 125 | 0.420 to 0.578, +0.159 (+0.117), 355 | 0.390 to 0.616, +0.226 (+0.188), 476 | L_MLB | DOES NOT HOLD; UNDERPOWERED |

Comparators. Zero: d exactly 0 on every computable label of every tool. Null (sub-driver vectors
permuted within board year): hit -0.234 / -0.203 (L_UM / L_ANY), game power -0.066 / -0.051,
fastball -0.069 / -0.007 / -0.018 (L_MLB / L_UM / L_ANY), command -0.190 / -0.159 / -0.138; no null
clears, so no read is void. Planted recovery: recovered for hit (+0.136, LB +0.089 on L_UM; +0.138,
LB +0.100 on L_ANY) and game power (+0.079, LB +0.054; +0.083, LB +0.061); NOT recovered on the MLB
label for fastball (+0.077, LB -0.013) and command (+0.039, LB -0.022), so their L_MLB reads cannot
certify a gain of the planted size: underpowered, not evidence of no gain.

Reported, deciding nothing. The stale consensus grade orders the labels worse than a board-year
grade (hit on L_UM 0.352 stale against 0.436 fresh), and the eTool's gain is larger on stale rows
than on fresh ones (hit +0.417 against +0.274). The gain grows with the grade's age: hit on L_UM
+0.377 (LB +0.294) at 12 to 24 months and +0.473 (LB +0.364) at 24 months or more; game power
+0.058 (LB +0.021) and +0.123 (LB +0.083). Under 12 months (U12) only L_ANY is computable for the
hitters (hit +0.488, LB +0.368, 140 players). The uncentred stale eTool reads within 0.004 of the
re-centred one. Mean stale eTool minus stale grade on S12: hit -0.73, game power +0.70, fastball
-0.83, command -0.21 grade points.

**What this does.** eHIT and ePOW are served for the eFV-board hitters whose latest hit and game
power grades predate the 2026 lists: 287 players (574 eTools; grades from 2019 to 2025, 14.6 to
86.6 months old), on the look's final fit and the live fresh cohort's re-centring shift, so the
1,632 fresh players' records are byte-identical. Fastball, command, pitch selection and bat control
keep the consensus grade for stale-graded players.
