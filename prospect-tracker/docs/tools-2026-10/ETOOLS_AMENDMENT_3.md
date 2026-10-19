# eTools amendment 3: MiLB fielding runs as sub-drivers for the field and arm tools (eFLD, eARM)

Registration status: REGISTERED

Task ETOOLS_FIELD_ARM_MFR (owner decision EW3-44, 2026-10-19, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`:
"ETOOLS_FIELD_ARM_MFR tests MiLB fielding runs as eFLD (vs MLB OAA by position) and eARM (vs arm
strength / arm runs) sub-drivers under the eTools rules; a passing tool becomes the shown grade and
joins the eTool composite"), written 2026-10-19 on lane wt-ETOOLS_FIELD_ARM_MFR (base 6d3515be).
Docs only, committed alone before any statistic named here is computed. It amends
`docs/tools-2026-10/ETOOLS_GATE.md` (registered 3f240da6, look dc271ac2) and follows amendments 1
and 2. Timing: an OWNER-WAIVED EARLY READ under EW3-5 (no look day applies).

## 0. Why, and what was already seen

At the look (2026-10-15) field and throw kept the consensus grade: NO SUB-DRIVER (the premium
position share read d +0.024, LB -0.006 on the MLB label), and gate 2.2 gave neither tool a minors
label ("no MiLB fielding or arm measurement exists"), so gate 5.2 could not pass them. On
2026-10-16 MILB_FIELDING_RUNS (`docs/sdr-2026-08-18/MILB_FIELDING_RUNS_GATE.md`, merged 80b7a9a9)
built that measurement: MiLB fielding runs (MFR) from play-by-play, seasons 2021 to 2026, by
component (range, double plays, outfield arm, catcher framing, catcher throwing).

**Seen before this document** (all published in that gate's part 10): (a) persistence PASS
(0.2483); (b) pre-debut MFR against MLB fielding runs PASS (T1 rfield 0.2559, T2 OAA per 1,000
0.1980, on debuts 2022 to 2024); (c) incremental over the frozen consensus field grade
UNDERPOWERED (rank partial T1 0.2774, LB95 0.1207; T2 OAA 0.1455, LB95 -0.0248; planted P-c
failed). **The eFLD MLB-label read below is therefore not blind:** (c) already related total MFR
to MLB OAA given a consensus field grade on an overlapping population (debuts 2022 to 2024). What
differs here: the grade (the board-year consensus at Y, not the last pre-debut frozen point), the
predictor (the range component as of Y, not total MFR to the debut season), the statistic (the
gate 4.1 out-of-fold within-board-year increment, not a rank partial) and the second label. No
arm-component statistic against any outcome has been computed by anyone.

**Counted by this lane before writing** (`python etools_mfr.py --check`: rows, candidate coverage
and label presence; no label value entered any statistic): the frame (section 1) holds 3,485
(board year, player) rows after identity, hitters only below. Field: 1,713 rows with a consensus
field grade (578, 564, 571 in 2022, 2023, 2024), 1,407 carrying the MFR candidate; carrying the
candidate and L_MLB 121, 71 and 28 rows (137 players); the candidate and the minors analog 343, 275
and 190 (481 players). Arm: 1,702 rows with a consensus arm grade, 563 carrying the candidate
(outfielders only); the candidate and L_MLB 46, 33 and 14 (62 players), so **the eARM incremental
test on L_MLB is NOT COMPUTABLE under gate 2.3** (under 100 players, 2024 under 20 rows); the
candidate and the minors analog 121, 107 and 78 (191 players). Reliability constants (section 2.3)
were computed by the check: range k 260 (CF, 1B) to 575 (2B) innings, outfield arm k 1,497 (CF) to
2,218 (LF) innings (split-half r 0.13 to 0.20: the arm component is noisy and is shrunk hard).

## 1. Frame

1.1 **Board years 2022, 2023 and 2024 only**: the development years (gate 1.1) whose as-of window
(seasons up to Y - 1) holds an MFR season (MFR begins in 2021). Board years 2020 and 2021 (R-LV)
are never read; 2011 to 2019 carry no MFR season and are left out (in them every eTool equals the
consensus grade, so they would add only exact zeros). The runner asserts the years.

1.2 Grades, rows, identity and the pre-debut rule exactly as gate 1.2 and 1.3
(`etools.load_board`, `etools.build_universe`, unchanged); hitters only. G_c is the consensus field
grade for eFLD and the consensus throw grade (FanGraphs `throw`, else `_extras.arm`, gate 0.4) for
eARM, rounded to 0.5.

1.3 **Never** a stratum, cell, key, filter or weight by consensus FV or any source's FV
(`docs/PROSPECT_ANCHOR_GATE.md`). Tool grades are covariates only.

## 2. Candidates (fixed here; nothing is added after the read)

2.1 **As of.** The MFR season table (`.cache/milb_fielding/tables/season_table.parquet`, the
MILB_FIELDING_RUNS build) read over seasons 2021 to Y - 1 only; the runner asserts the latest
season read for each board year.

2.2 **Primary position.** The rated position (C, 1B, 2B, 3B, SS, LF, CF, RF) with the most MiLB
innings over those seasons, all levels pooled (ties to the lower position code). Position groups
(EW3-44): SS; 2B/3B; CF; corner OF (LF, RF); 1B. **Catchers are excluded** from both tools: a row
whose primary position is C carries no candidate (eTool = G_c). eARM's candidate exists only for
an outfield primary position (CF, corner OF): the MFR components that measure a throw are the
outfield arm (kills, holds, extra bases) and catcher throwing; catchers are off the arm label (gate
2.1: no C or 1B) and infielders have no MFR throwing component (the double-play component measures
the pivot, not the arm).

2.3 **Value.** For the component c (eFLD: `range_runs`, the range and out-conversion component;
eARM: `arm_runs`, the outfield arm component) at the primary position k:
v = 1,000 x sum over levels L of F_L x c_L / (innings at k + k_c(k)), with F_L the registered MFR
level factors (AAA 1, AA 0.3663, A+ 0.1719, A 0.0501, ROK 0.0222; MFR part 10) and k_c(k) the
component's own split-half reliability constant at k (MFR part 3 machinery,
`milb_fielding_runs.shrink_k` with the component as the runs, on game rows of seasons 2021 to 2023,
the last season any candidate reads). Missing below 50 innings at k. Every MFR component is already
centred within (level, season, position).

2.4 **Candidate.** `mfr_range` (eFLD) and `mfr_arm` (eARM) = (v - mean_g) / sd_g, mean and sd over
every MiLB player (not only board rows) whose as-of primary position is in group g with 200 or more
innings at it, at the same Y: the shrunk residual on a common scale across position groups. The
eTool (gate 5.1) then takes its residual on G_c.

## 3. Labels (the estimands)

3.1 **L_MLB, unchanged from gate 2.1** (among debuts; first MLB season 2024 or earlier; the first
three MLB seasons strictly after Y, to 2026): field, OAA per 1,000 innings over 1B to RF, 700
innings; throw, Savant arm z within (season, IF/OF group), no C or 1B, 2020 on. For eARM the label
rows include infielders, who carry no candidate (eTool = G_c there).

3.2 **L_UM, the upper-minors analog (new).** The field tool's analog of the hit tool's translated
K%: the same MFR component at Double-A and Triple-A over seasons Y to Y + 2 capped at 2024 (gate 2.2
cap), at the player's primary Double-A/Triple-A position (most innings there) when it is in the
tool's groups, 200 or more innings at it, value 1,000 x sum_L F_L x c_L / innings (translated to the
Triple-A scale, unshrunk, as a label). eFLD: range runs; eARM: outfield arm runs. It shares the
survivorship caveat of every L_UM: it is accuracy AMONG PROMOTED players (amendment 1, A1); the
four-way promotion counts (A1.1) are reported beside it.

3.3 **Reported, deciding nothing.** eFLD: the L_MLB OAA rate centred within the MLB primary
position (the position with the most MLB innings over the label's seasons, `data/fielding_innings.json`),
the lesson of MFR part 0. eARM: FanGraphs FRP arm runs (`aFRP`) per 1,000 outfield innings over the
first three MLB seasons after Y with outfield innings (to 2026), 300 innings. Each with the gate 4.1
incremental statistic and, where an eTool is built, its d against G_c.

3.4 Computable: gate 2.3 (100 players, 3 board years of 20 or more rows), so with three board
years every year needs 20 rows.

## 4. The statistic and admission (gate 4, unchanged machinery)

4.1 Gate 4.1 to 4.3 exactly (`etools.incr_test`): out-of-fold [1, G_c, candidate] by player-disjoint
leave one board year out; d = rho_w(augmented) - rho_w(G_c); player-clustered bootstrap B 2000, seed
20261023 (the amendment 2 F3.2 re-ranked draws, the current `within_rho`); permuted floor 200 draws,
seed 20261024.

4.2 **BH q over the amendment's whole family**: the four pooled tests (eFLD and eARM, each on L_MLB
and L_UM), stricter than the gate's per (tool, label) family (one candidate each, where q = p).

4.3 **Admission: gate 4.4** (`etools.admit`): on at least one label q at or below 0.10, LB above 0
and d above the permuted floor; on the other label, where computable, d above 0.

## 5. The eTool and the pass rule (gate 5, unchanged)

5.1 Construction gate 5.1 (`etools.etool_eval`): TIP tables per label on the fold's training rows,
c by OLS on both labels stacked, eTool = clamp(G_c + c u, 20, 80), 80% band.

5.2 **PASS** when the one-sided 95% lower bound of d_E = rho_w(eTool) - rho_w(G_c) is above 0 on
BOTH labels, over every row carrying G_c and the label (rows without the candidate carry G_c). NO
SUB-DRIVER when nothing is admitted. The **forced eTool** (the 5.1 eTool built on the candidate
whether or not admitted) is reported beside every verdict and decides nothing.

## 6. Comparators (the pass needs them)

6.1 **Zero comparator.** The candidate set to 0 on every row carrying it: the eTool equals G_c and
d_E must be exactly 0 on both labels (a plumbing identity, printed). Passing means clearing it
(LB above 0).

6.2 **Null comparator.** The candidate permuted among the rows carrying it within (board year,
position group), seed 20261025; the 4.1 test on both labels and the forced eTool on both labels.
If the null's 4.1 LB is above 0 on either label, or its forced eTool clears gate 5.2, the tool's
read is **VOID** (a leak), never a pass.

6.3 **Planted recovery.** On the rows carrying the real candidate (its own missingness): per label,
a synthetic candidate 0.25 x z(within-board-year rank of that label) + sqrt(1 - 0.0625) x z(noise),
seed 20261026, through the 4.1 test with the permuted floor; recovered when LB is above 0 and d is
above the floor. For the eTool, one synthetic candidate 0.25 x (z of the L_MLB rank + z of the
L_UM rank, 0 for a missing label) + sqrt(1 - 0.125) x z(noise), through gate 5.2; recovered when it
passes. A tool that does not pass and whose planted check fails on a label (or on the eTool) is
recorded **NOT PASS; UNDERPOWERED** (named): the design could not certify a planted gain of that
size, so the read is not evidence of no gain.

## 7. Descriptive cells (never admitting)

The position groups of 2.2 (eFLD: SS, 2B/3B, CF, corner OF, 1B; eARM: CF, corner OF), on each label:
the 4.1 statistic on the cell's rows carrying the candidate and the label, board years with 10 or
more rows, 30 or more players (below the gate's 100-player cell floor, which no cell here reaches;
these cells are description only), B 2000, seed 20261023.

## 8. What follows the verdict

- **PASS** (eFLD, eARM or both): before serving, the amendment 2 F1 drift and re-centring read runs
  once for the passing tool (F1.2 to F1.7 unchanged; its serving rule picks the re-centred or the
  uncentred eTool), and the A1.1 promotion counts are disclosed. Then the tool is served as the
  shown grade on the ETOOLS_SITEWIDE_FLIP pattern (eTool shown to the nearest whole grade, the
  consensus beside it as the reference, `data/etools.json`), enters the eTool composite on the
  ETOOLS_ALL_CALCS plumbing (the shown grades feed the descriptive composites; the registered
  readers M1 to M3 stay on their own re-read rules), with a glossary entry and the `etools` registry
  row updated (provisional). The served numbers that move are reported before and after.
- **Not PASS** (NO SUB-DRIVER, NOT PASS, UNDERPOWERED or VOID): the consensus field and arm grades
  stay the shown grades; the results are recorded in `docs/tools-2026-10/ETOOLS_RESULTS.md` and
  nothing served moves.

## 9. The one read

`python etools_mfr.py --run --amend-sha SHA` refuses unless SHA names a commit carrying this file as
REGISTERED; it asserts the board years, no candidate season at or after Y, no minors-label season
outside Y to 2024, no L_MLB row with a first MLB season after 2024 and no FV-keyed grouping; it reads
every input's sha256 at start and end. `--check` counts; `--dry-run` runs the reporting path on
fixtures. The read begins at the first statistic that pairs a grade or candidate with a label; it
runs once and `data/_labs/etools/etools_mfr_reads.json` carries a spent marker. On an exception
after that point: no rerun, the read is recorded as spent, and the question goes to the owner. Never
`backtest.run_backtest`, `run_monthly` or `build_site` from the runner; no network request.

## 10. Results

(Empty at registration. Results go to this section as a dated note and to
`docs/tools-2026-10/ETOOLS_RESULTS.md`.)

### 2026-10-19: THE READ, once (OWNER-WAIVED EARLY READ, EW3-5)

`python etools_mfr.py --run --amend-sha e1c13320`, run once (2026-10-19T18:22:05Z to 18:22:14Z,
head 2c3593bd) after the fixture dry run; no exception; every input's sha256 matched at start and
end; stdout and stderr kept in the task's output directory. Artifact
`data/_labs/etools/etools_mfr_reads.json` (spent marker). d is the out-of-fold within-board-year
Spearman gain over the consensus grade; LB the one-sided 95% lower bound (B 2000).

**eFLD (MFR range component): NO SUB-DRIVER.** 1,713 frame rows (1,065 players), 1,407 carrying
the candidate.

| label | rows (players) | consensus | with MFR | d (LB) | q |
|---|---|---|---|---|---|
| L_MLB, OAA per 1,000 | 220 (137) | 0.377 | 0.364 | -0.013 (-0.073) | 0.71 |
| L_UM analog, MFR range at AA/AAA | 808 (481) | 0.107 | 0.093 | -0.014 (-0.055) | 0.71 |

The candidate alone orders the labels at 0.120 (MLB) and 0.151 (minors) and is nearly unrelated
to the consensus field grade (0.03 and 0.10), yet it adds nothing out of fold. The forced eTool:
d -0.002 (LB -0.029, 226 rows) on L_MLB and -0.008 (LB -0.023, 835 rows) on L_UM. Comparators: the
zero comparator gives d exactly 0 on both labels; the null (permuted within board year and position
group) reads d -0.029 and -0.012 (forced eTool LB -0.029 and -0.014) and does not clear, so the read
is not void; planted recovery succeeds on L_UM (d +0.123, LB +0.059, above its floor 0.017) and
fails on L_MLB (d +0.011, LB -0.050) and on the eTool's MLB label (d +0.014, LB -0.008). So on the
minors analog, where a planted gain of the registered size is recovered, the real candidate shows
none (CI95 upper end +0.035): a powered null. On the MLB label (137 players) the design could not
certify a planted gain: that label is UNDERPOWERED.

Descriptive cells (never admitting): shortstops on L_MLB d -0.312 (41 players, LB -0.573); center
fielders on L_MLB +0.035 (32 players, LB -0.035); every other cell within plus or minus 0.07 with its
LB below 0; first base and corner outfield on L_MLB under 30 players. Reported: OAA centred within
the MLB primary position, incremental d -0.054 (LB -0.154), forced eTool +0.0005 (LB -0.021).

Post-hoc, computed after the read and deciding nothing: the fold OLS weight on the candidate for
L_UM is -0.83 when board year 2022 is held out and +2.1 and +2.0 in the other two folds; within
2022, 2023 and 2024 the candidate's Spearman with L_UM is 0.20, 0.09 and 0.15 (the grade's 0.14,
0.14 and 0.00). The as-of candidate rests on one MFR season at board year 2022 and on three at
2024, and its relation to the label moves with that, so a weight fit on two board years does not
carry to the third.

**eARM (MFR outfield arm component): NO SUB-DRIVER; UNDERPOWERED (L_MLB, L_UM, eTool).** 1,702
frame rows, 563 carrying the candidate (outfielders).

| label | rows (players) | consensus | with MFR | d (LB) | q |
|---|---|---|---|---|---|
| L_MLB, arm z | 93 (62) | NOT COMPUTABLE (2024 has 14 rows) | | | |
| L_UM analog, MFR arm at AA/AAA | 306 (191) | 0.187 | 0.248 | +0.061 (-0.0004) | 0.13 |

On the minors analog the gain is above its permuted floor (0.017) but its lower bound is not above
0 (CI95 -0.009 to +0.128, p 0.044) and q is above 0.10: not admitted. The forced eTool: d +0.005
(LB -0.006, 267 rows, 93 with the candidate) on L_MLB and +0.003 (LB -0.009, 365 rows) on L_UM.
Comparators: zero exactly 0; the null reads d -0.007 on L_UM (LB -0.037) and its forced eTool LB
-0.023 and -0.016, so it does not clear; planted recovery fails on L_UM (d +0.056, LB -0.014), is
not computable on L_MLB and fails on the eTool. Cells: center field L_MLB -0.041 (43 players, LB
-0.104), L_UM +0.042 (101, LB -0.034); corner outfield L_UM +0.045 (100, LB -0.038). Reported:
FanGraphs FRP arm runs, not computable (62 players). The arm component leans positive on the
minors analog, but these rows cannot certify even a planted gain of that size and there is no MLB
read at all: a lean, not a sub-driver.

**What this does.** Nothing served moves. Field and arm keep the consensus grade (rounded up) as
the shown grade on every surface; neither enters `data/etools.json`, the eTool composite or
eTools+. Inside the development frame these pools cannot grow (board years and debuts end at
2024), so a stronger read of eARM would need frames this program keeps reserved: an owner call,
not a re-run.
