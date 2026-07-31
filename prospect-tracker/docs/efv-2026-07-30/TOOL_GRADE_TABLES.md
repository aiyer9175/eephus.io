# Derived tool-grade measurement tables (Phase 4, LANE-TOOLS)

Lane owner: tool grades. Plan: `docs/master-plan-2026-07-30-fv-calibration.md` Phase 4.
Reference for the published bands: `docs/reference/FANGRAPHS_FV_FRAMEWORK.md` Parts 2, 11.
Harness: `tools/tool_grade_tables_lab.py`. Artifact: `data/tool_grade_tables.json`.

This lane produces DERIVED REFERENCE TABLES. It changes no scoring path, no consensus
weight, no exporter, and no served number. Every use of these tables in scoring is a
separate gated lane.

Section 1 (pre-registration) was written and committed to this file BEFORE the first
table was fitted. Sections 2 onward are results.

---

## 1. Pre-registration

### 1.1 Populations

Two populations, both keyed on `mlbam_id`, both carrying the SAME grade source, so the
context gap between them is measurable within player rather than assumed.

| id | grade source | measurement source | context |
| --- | --- | --- | --- |
| **P-MLB** | last PRE-DEBUT `tools_consensus` point in `data/debuts.json` | `.cache/savant_mlb/statcast_batter_*.csv` (EV, hard-hit, barrel), `.cache/savant_mlb/expected_batter_*.csv` (PA, BA, wOBA, xwOBA), `.cache/fa_statsapi_hitting_*.json` / `_pitching_*.json` (HR, SB, BB%, AVG), `.cache/velo_arsenal_*.json` (fastball velocity) | MLB, the context the published tables are written in |
| **P-AAA** | latest `tools_consensus` point in `data/timeseries.json` (actives) plus the same P-MLB grades for debuted players | `.cache/savant_minors/{batter,pitcher}_*.csv` (AAA tracked parks, 2023+), `data/aaa_physics.json` (per-pitch-type velocity) | upper minors, mostly AAA |

Vintage discipline: for P-MLB the grade must predate the debut date. A post-debut re-read
is never used, because the measurement is the post-debut outcome and a re-read leaks it.
For P-AAA the grade is contemporaneous with the measurement window by construction and no
pre-dating is possible or required; the P-AAA rows are therefore CONCURRENT-frame and are
labelled as such.

### 1.2 Grade handling

Consensus tool grades are continuous (shrunk cross-source averages: 37.5, 52.5 exist).
Binned to the nearest 5 (`round(g / 5) * 5`), clipped to [20, 80]. Each published cell also
carries `grade_mean`, the mean unrounded grade inside the bin, so bin centring is visible.
Rows are one per PLAYER, never one per player-season, so no player is counted twice inside
a cell.

### 1.3 Floors and thin cells

- MLB batter: 150 career PA for the career frame, 300 career PA for the maturity frame.
- AAA batter: 100 PA in a season for that season to qualify.
- MLB pitcher velocity: presence in `velo_arsenal_YYYY` (the Savant arsenal leaderboard
  already applies its own pitch floor).
- AAA pitcher velocity: the `data/aaa_physics.json` per-type floor (10 pitches per type
  row, 50 per pitcher-season).
- **n < 15 in a cell = THIN.** A thin cell publishes n and the observed range only. It is
  never published as a point estimate, is never used in the audit, and is flagged
  `thin: true` in the artifact.

### 1.4 Statistics

Per tool per grade: n, median, p25, p75, and a 95% percentile bootstrap CI on the median,
2000 resamples over PLAYERS, seed 20260730. Monotonicity is reported separately as the
player-grain Spearman rho of measurement on unrounded grade with its own bootstrap CI. A
table can be well-centred and still carry no ordering signal; the two claims are reported
separately and neither is allowed to stand in for the other.

### 1.5 Audit rule (written before the audit ran)

For a grade g and tool t, we record DISAGREEMENT with an outlet when the outlet's published
value for (t, g) falls OUTSIDE our 95% CI on the median, and the cell is not thin. For a
banded published value (BA prints bands; FanGraphs prints bands for homers) the band is
treated as an interval and disagreement requires the whole interval to fall outside the CI.
The signed gap is reported as ours minus theirs, in the published unit. Agreement with a
band whose width exceeds our CI width is reported as UNINFORMATIVE rather than as
agreement.

Outlets audited: FanGraphs (S3 2014 objective table, Smith W2 2013 z-tables where they are
the only published unit scale), Baseball America (B1, current), MLB Pipeline (publishes NO
measurement table at any grade for any tool, so for every cell the Pipeline column reads
`no published band` and our table is the only audit that exists).

### 1.6 Context handling (mandatory, not optional)

Every AAA row is reported with a measured AAA-minus-MLB offset for the same metric,
computed WITHIN PLAYER over players present in both populations, with its own n and CI.
No AAA row is compared to an MLB-context published band without that offset stated on the
same line. Where the within-player offset has n < 30 the AAA row is reported as
context-uncalibrated and excluded from the audit.

### 1.7 Tools with no ground truth: reported as findings

Declared in advance so a null cannot be quietly upgraded later. A tool is declared
NO MEASUREMENT if this tree contains no observation of the physical quantity the grade
names, only a model output or a role proxy. The candidates going in: `field`, `throw`,
`pitch_sel`, `bat_ctrl`, `delivery`, `athl`, `frame`. Speed is a partial case and is
reported as a proxy-only tool if no run time exists.

### 1.8 Inventions, each with its pass condition written first

- **INV-1, measurement-implied tool grade.** Invert the derived median table to map a
  player's measurement back onto the 20-80 scale. PASS to publish as a display third
  opinion if (a) Spearman rho against the scout consensus grade is in [0.25, 0.85]
  (informative but not a restatement) and (b) the share of players with
  |implied - scout| >= 10 (two full grades) is between 5% and 40%: below 5% it flags
  nothing, above 40% it is noise. Report the rate whatever it is.
- **INV-2, per-source grade-minus-measurement drift index.** Per source and tool, the mean
  of (source grade - measurement-implied grade). PASS if the between-source difference is
  (a) sign-stable across 2000 bootstrap resamples at 95% and (b) at least 1.0 grade point.
  Source floor: 100 players for that tool. Sources with fewer are reported as
  not computable, named.
- **INV-3, per-tool grade aging curves.** Descriptive, from the longitudinal per-source
  grade history. PASS to publish if at least 200 players carry >= 3 grade snapshots for
  the tool spanning >= 2.0 years, and the mean per-year grade change has a bootstrap CI
  excluding zero for at least one tool.

None of the three may be wired into consensus weighting or eFV scoring in this lane. Each
would need its own accuracy gate against realized outcomes, which this lane does not run.

### 1.9 What would make this lane a null

If the grade-to-measurement Spearman is under 0.20 at the player grain for a tool, that
tool's table is published as DESCRIPTIVE ONLY with an explicit note that the grade does not
order the measurement in our data, and it is excluded from INV-1 and INV-2.

---

## 2. Results

Harness run 2026-07-30, seed 20260730, artifact `data/tool_grade_tables.json` (47 tables,
13 audits, 14 context offsets, 3 inventions). Pools: **P-MLB 1,765** graded players with a
pre-debut consensus grade, **P-AAA 3,419**. Joined n per table runs 199 to 809.

### 2.1 The single result that organizes everything else

**Our measured tool curves are flatter than every published table, at every tool, in both
contexts.** The published ladders are steeper than what the grades actually deliver.

FanGraphs is the only outlet that states a distributional claim: 10 grade points is one
standard deviation (framework doc X1; Baseball America and MLB Pipeline never make the
claim). Measured on our pool, standard deviations of the measurement per 10 grade points:

| tool and measurement | SD per 10 grade points |
| --- | --- |
| fastball velocity, MLB, starters, career max | 0.97 |
| fastball velocity, MLB, starters, first season | 0.91 |
| fastball velocity, MLB, all roles | 0.84 |
| whiff rate, upper minors (hit) | 0.82 |
| fastball velocity, upper minors | 0.81 |
| fastball velocity, MLB, relievers | 0.81 |
| strikeout rate, MLB (hit) | 0.75 |
| walk rate, upper minors (command) | 0.74 |
| barrels per PA, MLB (game power) | 0.67 |
| stolen bases per 600 PA, MLB (speed) | 0.57 |
| exit velocity, MLB (raw power) | 0.56 |
| fielding runs, MLB full-time seasons | 0.55 |
| batting average, MLB full-season frame (hit) | 0.43 |

Read this as a LOWER bound on the true ratio, not a point estimate. Per-player sampling
noise sits in the denominator and pushes every ratio down, which is exactly why fastball
velocity (measured over thousands of pitches per player, almost noise-free) is the one
quantity that reaches the claimed 1.0 and why batting average over a 350 PA season, the
noisiest measurement in the set, is the lowest. The honest statement is: the
10-points-is-one-SD claim survives only where we can measure the quantity precisely, and
where it survives it survives well.

The same compression shows up directly against the published ladders, as a slope ratio of
ours over theirs, over the grades where both sides have a value and our cell is not thin:

| quantity | vs FanGraphs 2014 | vs Baseball America |
| --- | --- | --- |
| fastball velocity, SP, first MLB season | 0.84 | 0.96 |
| fastball velocity, SP, career max | 0.86 | 0.99 |
| fastball velocity, RP, first MLB season | no band | 0.83 |
| home runs per 600 PA, career frame | 0.66 | 0.56 |
| home runs per 600 PA, full-season frame | 0.75 | 0.65 |
| home runs per 600 PA, age 26+ frame | 0.71 | 0.50 |
| batting average, career frame | 0.67 | 0.62 |
| batting average, full-season frame | 0.45 | 0.50 |
| batting average, age 26+ frame | 0.67 | 0.61 |

Velocity is nearly right. Power and hit are delivered at half to three quarters of the
published rate per grade point.

### 2.2 Fastball velocity: our data sides with Baseball America and settles the 2 mph gap

The framework doc's X2 records a 2 mph offset between the two published tables and argues
from BA's own text that the FanGraphs 2014 column is stale rather than wrong. Our
measurement is the first outside test of that argument.

Starters, first qualifying MLB season, n = 227, Spearman 0.691:

| grade | n | median mph | IQR | 95% CI on median | FanGraphs 2014 | BA current |
| --- | --- | --- | --- | --- | --- | --- |
| 40 | 9 | 91.4 | 90.6-91.8 | thin | 88 | 90-91 |
| 45 | 7 | 91.0 | 90.1-92.5 | thin | 89 | 92 |
| 50 | 75 | 93.0 | 92.3-93.9 | 92.8-93.4 | 90-91 | 93 |
| 55 | 27 | 94.0 | 93.2-94.6 | 93.5-94.5 | 92 | 94 |
| 60 | 60 | 94.6 | 93.6-95.5 | 94.0-94.9 | 93 | 95 |
| 65 | 30 | 96.0 | 94.9-97.2 | 95.3-96.6 | 94 | 96 |
| 70 | 13 | 96.7 | 95.5-97.5 | thin | 95 | 97 |
| 75 | 3 | 98.8 | 98.3-99.1 | thin | 96 | (no row) |
| 80 | 3 | 96.7 | 94.6-97.8 | thin | 97 | 98+ |

BA hits three of the four auditable cells exactly (50, 55, 65) and misses 60 by 0.4 mph.
FanGraphs 2014 misses all four by 1.6 to 2.5 mph, always cold. Smith W2 2013 misses the two
cells it covers by 1.6 and 2.0, also cold. **Our data confirms BA's recentring and confirms
the FanGraphs published velocity column is stale.** Reading a 93 mph starter as a 60 off the
FanGraphs table reads him one and a half tiers hot.

One measurement caveat that cuts the other way: the Savant arsenal column we read is
max(FF, SI, FC) average speed, so a two-fastball pitcher reads at his harder pitch. Measured
inside our own AAA data, that definition is worth **+0.30 mph** (CI 0.23 to 0.37, n = 729)
against a usage-primary fastball. Subtracting it leaves BA still correct at 50 and 55 to
within a third of a mile per hour.

The 80 row inverting (96.7, below 75's 98.8) is n = 3 on both cells and is reported as thin,
not as a finding.

### 2.3 The published velocity adjustments: one confirmed, one not supported

Both outlets publish two modifiers. We tested both at matched grade, so neither contrast is
a grade-composition artifact.

| published adjustment | published value | ours | n |
| --- | --- | --- | --- |
| left-handers throw softer at the same grade | 1.0 mph (Smith W2 and BA both) | **1.19 mph** | 93 LHP vs 288 RHP, 5 matched bins |
| relievers throw harder at the same grade | 1 to 2 mph (BA); 1 to 3 mph (Smith W2) | **0.59 mph** | 409 SP vs 221 RP, 7 matched bins |

The handedness adjustment is right. The reliever adjustment measures at about a third to a
half of the published value. Read that as a LOWER bound rather than a refutation: our role
split is realized MLB usage, so most of the RP group are prospects scouted as starters who
ended up in relief, a population selected downward on velocity relative to a scouted
reliever.

### 2.4 Game power: neither published table is right, and they are wrong in opposite places

Home runs per 600 MLB PA, full-season frame (the player's highest-PA MLB season, 350 PA
floor, so the rate is not selected on the outcome). n = 301, Spearman 0.577.

| grade | n | median HR | IQR | 95% CI | FanGraphs | BA | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 30 | 15 | 7.1 | 4.6-12.1 | 3.2-13.0 | 3-5 | 5-9 | both fit (n = 15, CI too wide to separate) |
| 40 | 41 | 14.9 | 10.4-19.7 | 12.2-17.0 | 8-12 | 10-13 | **FG too low**, BA fits |
| 45 | 38 | 14.7 | 12.1-19.9 | 13.2-17.5 | 12-15 | 14-18 | both fit |
| 50 | 83 | 19.6 | 16.5-24.5 | 18.3-20.9 | 15-18 | 19-22 | FG too low, BA fits |
| 55 | 46 | 20.1 | 15.8-25.2 | 18.1-22.4 | 19-22 | 23-27 | FG fits, **BA too high** |
| 60 | 42 | 23.4 | 19.5-30.5 | 21.0-27.1 | 23-27 | 28-33 | FG fits, **BA too high** |
| 65 | 14 | 27.9 | 24.8-35.0 | thin | 27-30 | (no row) | thin |

**The disagreement cell nobody else has: we disagree with Baseball America at 55 in all
three frames we computed** (career, full-season, age 26+) and at 60 in two of the three, by
4.9 to 9.3 home runs, while agreeing with FanGraphs at both. The one exception is the age-26
frame's 60 cell, n = 24, whose CI is wide enough to overlap BA's band. At 40 and 50 the
direction reverses and BA is the closer table. BA's recentring for the home run era over-corrected at the top of the scale: their
stated reason (framework doc X3) is a league home run rate argument, but the grades their
published table moved most are the ones our data says did not move.

Two biases run in opposite directions here and both are stated rather than corrected. Our
pool is conditioned on reaching MLB with 300 PA, which pushes the LOW grades up (a 30-power
hitter who gets 350 MLB PA is a selected 30). Our pool is also young, so no frame reaches the
"at maturity" the published tables specify, which pushes the HIGH grades down. The age-26-plus
frame is the closest available control and it reproduces the same BA disagreement at 55, so
the top-end finding is not purely a maturity artifact.

### 2.5 Hit tool: the two outlets agree with each other and both are hot above 50

Framework doc X4 uses the FanGraphs and BA hit tables agreeing with each other as the control
proving the velocity and power gaps are real recalibration rather than a general offset. Our
data agrees that the two outlets agree, and then finds both of them hot.

MLB batting average, full-season frame, n = 301, Spearman 0.312:

| grade | n | median AVG | 95% CI | FanGraphs | BA band | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 40 | 39 | .240 | .229-.248 | .240 | .235-.244 | both fit exactly |
| 45 | 30 | .253 | .239-.259 | .250 | .245-.254 | both fit |
| 50 | 88 | .253 | .247-.262 | .260 | .255-.264 | both fit (BA band wider than our CI) |
| 55 | 53 | .258 | .251-.266 | .270 | .265-.274 | **FG too high**, BA fits |
| 60 | 66 | .265 | .256-.271 | .280 | .275-.294 | **both too high** |
| 65 | 16 | .263 | .250-.281 | .290 | (inside the BA 60 band) | thin |

The career frame reads 16 to 38 points below every published table at every grade. That is
the frame, not the scale: a career average that includes 60 PA call-up seasons is not the
quantity the published tables describe. The full-season frame is the honest comparison and
the one to quote.

The hit tool is also the weakest ordering signal among the primary tools: Spearman 0.31
against MLB batting average, against 0.69 for velocity and 0.72 for speed. It is much
stronger against strikeout rate (-0.55 in MLB, -0.57 in the minors, -0.59 against minor
league whiff rate), which is a real result about what the hit grade is: our sources' hit
grades order CONTACT far better than they order batting average. That is McDaniel's own
reservation about the hit column (framework doc 2.1) measured rather than asserted.

### 2.6 Speed: no run time exists, and the one published table in outcome units survives

Verified exhaustively: this tree contains **no sprint speed, no 60-yard time and no
home-to-first time** in any structured field. The string appears only inside scouting report
prose. Both the FanGraphs and the BA speed tables are published in seconds, so **neither is
auditable here and we report that as a gap rather than filling it with a guess.**

What is auditable is Smith W2's stolen-base table, and it is the single published table that
comes through our audit essentially intact. Stolen bases per 600 PA, full-season frame,
n = 301, Spearman 0.716 (the strongest grade-to-measurement ordering of any tool we hold):

| grade | n | median SB | 95% CI | Smith W2 SB/season |
| --- | --- | --- | --- | --- |
| 30 | 22 | 1.4 | 0.9-2.3 | -10 (impossible; Smith flags it) |
| 40 | 35 | 4.4 | 2.5-6.7 | (blank in the source) |
| 50 | 62 | 10.0 | 6.5-12.9 | 9 |
| 55 | 39 | 17.1 | 13.1-22.5 | (no row) |
| 60 | 49 | 17.6 | 15.2-22.5 | 19 |
| 65 | 16 | 19.0 | 16.1-21.9 | (no row) |
| 70 | 11 | 26.2 | thin | 29 |
| 80 | 4 | 41.7 | thin | 38 |

Smith's 50 and 60 rows both land inside our CI. His negative rows below 40 are impossible by
construction, as he says himself, and our measured floor there is 1.4 SB per season.

Stolen bases are an outcome proxy carrying manager and era effects, not a run time. Triples
per 600 PA is the second proxy (Spearman 0.46 in MLB, 0.39 in the minors) and is weaker.

### 2.7 Field: measurable after all, and Smith's defensive table is hot at both ends

The lane went in expecting field to be a NO MEASUREMENT finding. It is not. Joining the
cached Savant OAA leaderboards to `data/fielding_innings.json` gives 199 graded players with
at least one full-time MLB season (700+ innings at the OAA primary position) and 638 players
with any OAA season.

Fielding runs prevented, median full-time season, n = 199, Spearman 0.309:

| grade | n | median runs | IQR | 95% CI | Smith UZR/150 | Smith Fld/3 |
| --- | --- | --- | --- | --- | --- | --- |
| 45 | 26 | -0.5 | -3.9 to 1.4 | -2.5 to 0.8 | -5.4 at 40 | -4.0 at 40 |
| 50 | 78 | -0.25 | -3.4 to 3.9 | -2.0 to 1.0 | +1.6 | +1.5 |
| 55 | 35 | 0.0 | -3.0 to 4.5 | -2.0 to 3.5 | (no row) | (no row) |
| 60 | 31 | 4.0 | -0.5 to 8.5 | 0.0 to 6.0 | +8.7 | +6.9 |
| 65 | 11 | 8.0 | 0.8 to 10.0 | thin | (no row) | (no row) |

Both Smith tables disagree with us at 50 and at 60. At 50 they put an average defender at
+1.5 to +1.6 runs; we measure -0.25, statistically indistinguishable from zero. Smith flagged
that wrinkle himself (his 50 row is the qualified-population mean, not the league mean) and
our data says his own caveat was the right reading: **a 50 field grade is a zero-run
defender.** At 60 both his tables are roughly twice our measured value.

Caveats that belong on this table rather than in a footnote: OAA is range and positioning
only, so catcher framing and catcher throwing sit outside it entirely, and the grade is
pooled across positions exactly as Smith pooled his.

### 2.8 Command: Smith's control table is too steep above 50

MLB walk rate, starters, n = 241, Spearman -0.373 (the sign is correct; a higher command
grade must read a lower walk rate).

| grade | n | median BB% | 95% CI | Smith W2 SP |
| --- | --- | --- | --- | --- |
| 40 | 17 | 9.42 | 8.24-10.99 | 9.8 (fits) |
| 45 | 36 | 8.71 | 8.10-9.54 | (no row) |
| 50 | 89 | 8.86 | 8.39-9.45 | 7.8 (**too low**) |
| 55 | 44 | 8.12 | 7.41-8.73 | (no row) |
| 60 | 45 | 7.48 | 6.94-7.96 | 5.7 (**too low**) |

Relievers behave the same way: his 40 row fits, his 50 row fits, his 60 row (6.8%) sits below
our 7.87% CI. The compression pattern again, and it is worse at the top.

### 2.9 Raw power in tracking units: no outlet publishes anything, so this is the only table

Neither FanGraphs nor Baseball America nor MLB Pipeline publishes a grade-to-exit-velocity
band. There is nothing to audit against; the table below IS the audit.

Average MLB exit velocity by raw power grade, n = 553, Spearman 0.562:

| grade | n | median EV | IQR | 95% CI |
| --- | --- | --- | --- | --- |
| 30 | 18 | 86.75 | 85.0-87.7 | 85.1-87.6 |
| 40 | 53 | 86.85 | 85.6-88.4 | 86.4-88.0 |
| 45 | 73 | 87.34 | 86.4-88.6 | 86.8-87.6 |
| 50 | 128 | 88.13 | 87.1-89.3 | 87.7-88.5 |
| 55 | 90 | 88.67 | 87.5-89.8 | 88.3-89.1 |
| 60 | 98 | 89.18 | 88.3-90.5 | 89.0-89.7 |
| 65 | 21 | 89.77 | 89.3-91.0 | 89.3-90.5 |
| 70 | 49 | 90.12 | 89.2-91.3 | 89.7-90.7 |
| 80 | 12 | 91.58 | 91.0-92.8 | thin |

The upper-minors table is the better read BELOW 50, and the reason is structural: the MLB
table is conditioned on reaching the majors, so its 30 and 40 cells are survivors and read
almost flat (86.75 and 86.85). The AAA pool carries the prospects who never got there:

| grade | n | median EV, upper minors | 95% CI | MLB, same grade |
| --- | --- | --- | --- | --- |
| 30 | 28 | 84.65 | 83.2-85.6 | 86.75 |
| 40 | 85 | 86.20 | 85.7-86.9 | 86.85 |
| 50 | 165 | 87.52 | 87.0-87.9 | 88.13 |
| 60 | 134 | 89.11 | 88.6-89.5 | 89.18 |
| 70 | 51 | 90.69 | 90.3-90.9 | 90.12 |

The two tables converge from 50 up and diverge below it by up to 2.1 mph, which is the size
of the survivorship correction at the bottom of the raw power scale.

Companion tables in the artifact, all the same shape: ev50 (the top half of batted balls, the
cleanest raw power signal at Spearman 0.669), max exit velocity, hard-hit rate, adjusted exit
velocity, and barrels per PA and per batted ball for game power.

### 2.10 Context: AAA and MLB are the same scale for exit velocity, and for nothing else

Measured WITHIN PLAYER over players present in both pools, so this is not a population
comparison. AAA minus MLB:

| quantity | n | mean offset | 95% CI on the mean | reading |
| --- | --- | --- | --- | --- |
| average exit velocity | 422 | **-0.06 mph** | -0.23 to +0.12 | no offset; the AAA EV table reads on the MLB scale directly |
| hard-hit rate | 422 | +1.79 pts | +1.25 to +2.31 | AAA reads hot |
| barrels per batted ball | 422 | +0.32 pts | +0.05 to +0.60 | AAA reads slightly hot |
| expected batting average | 550 | +0.018 | +0.015 to +0.021 | AAA reads hot |
| expected wOBA | 554 | +0.040 | +0.036 to +0.044 | AAA reads hot |
| batting average | 394 | +0.044 | +0.041 to +0.048 | AAA reads hot |
| strikeout rate, hitters | 394 | -4.05 pts | -4.45 to -3.66 | AAA hitters strike out less |
| walk rate, hitters | 394 | +3.74 pts | +3.49 to +3.99 | AAA hitters walk more |
| fastball velocity | 445 | -0.77 mph | -0.90 to -0.64 | AAA reads cold |
| fastball velocity, like for like | 445 | -0.51 mph | -0.62 to -0.41 | after removing the max-of-three definition gap |
| strikeout rate, pitchers | 460 | +3.36 pts | +2.93 to +3.79 | AAA pitchers strike out more |
| walk rate, pitchers | 460 | +1.20 pts | +0.92 to +1.51 | AAA pitchers walk more |

The exit velocity null is the useful one. Bat-to-ball impact transfers unchanged; every
outcome built on top of it does not. Every AAA row in the artifact carries its offset, and
the two AAA quantities with no measured offset partner (aStuff+, triples per 600) are marked
context-uncalibrated and excluded from the audit.

### 2.11 Tools with no ground truth (reported as findings, not as gaps)

| tool | status |
| --- | --- |
| **throw / arm** | **NO MEASUREMENT.** No throw velocity, no catcher pop time, no outfield arm-runs split anywhere in the tree. BA's catcher pop-time table is the only published arm scale in measured units at any outlet and it is unauditable here. Smith W2's arm table is in defensive runs and he disclaims it himself as measuring the wrong thing. |
| **pitch_sel** | NO MEASUREMENT of the tool. Walk rate is a consequence, not the skill, and no swing-decision decomposition is joined at the player-season grain in either context. |
| **bat_ctrl** | NO MEASUREMENT. The Savant minors export carries `bat_speed` and `swing_length` as columns and they are EMPTY in every row of every season we hold (0 of 723 in 2025). MLB bat tracking exists in `.cache/bat_tracking` but carries no prospect-grade join. |
| **delivery, athl, frame** | NO MEASUREMENT. Arm angle and extension exist in `data/aaa_physics.json` but neither is what the grade names. |
| **speed** | PARTIAL. Outcome proxies only (section 2.6). The published tables are unauditable. |
| **sl, cb, ch** | INDIRECT ONLY, and mostly null: no per-pitch MLB shape measurement is joined, so these read a pitch grade against a whole-arsenal outcome. Slider clears the 0.20 signal floor on both arms and only just (0.209 against MLB strikeout rate, 0.201 against minor league whiff rate); curveball fails both (0.127 and 0.140); changeup fails both, at 0.075 and **-0.039**, which is no relationship at all. Curveball and changeup are marked DESCRIPTIVE ONLY per section 1.9. |
| **fb against aStuff+** | The aStuff+ of the primary fastball orders the fastball GRADE at 0.092, below the floor: our sources' fastball grades track velocity (0.62) and not modeled stuff. Marked DESCRIPTIVE ONLY. |
| **hit against xwOBA** | Upper-minors xwOBA orders the hit grade at 0.140, below the floor, because xwOBA is mostly power. Marked DESCRIPTIVE ONLY. |

### 2.12 Inventions

**INV-1, measurement-implied tool grade.** Invert the derived median table and read a
player's measurement back onto the 20-80 scale.

| tool | context | n | rho vs scout grade | share 2+ grades apart | verdict |
| --- | --- | --- | --- | --- | --- |
| fb | MLB | 675 | 0.640 | 24.2% | **PASS** |
| speed | MLB | 301 | 0.713 | 30.9% | **PASS** |
| game_pwr | MLB | 301 | 0.569 | 31.6% | **PASS** |
| cmd | MLB | 697 | 0.397 | 35.4% | **PASS** |
| field | MLB | 199 | 0.322 | 29.7% | **PASS** |
| fb | upper minors | 726 | 0.613 | 23.0% | **PASS** |
| hit | upper minors | 809 | 0.570 | 18.5% | **PASS** |
| game_pwr | upper minors | 806 | 0.637 | 25.8% | **PASS** |
| cmd | upper minors | 858 | 0.548 | 26.9% | **PASS** |
| raw_pwr | MLB | 553 | 0.548 | 51.0% | FAIL (flag rate) |
| raw_pwr | upper minors | 738 | 0.574 | 44.7% | FAIL (flag rate) |
| hit | MLB | 301 | 0.291 | 49.2% | FAIL (flag rate) |
| speed | upper minors | 806 | 0.383 | 59.3% | FAIL (flag rate) |

Nine of thirteen pass. The four failures all fail the same way and for the reason section 2.1
gives: where the measured band is compressed, inverting it is ill-conditioned, so a fraction
of a mile per hour of exit velocity swings the implied grade by two tiers. The FAIL is
therefore informative rather than merely negative: **raw power and MLB batting average cannot
be inverted to a grade at usable precision, and the compression is why.** The passing set is
a legitimate third opinion for a disagreement display, subject to the standing rule that
display is not scoring.

**INV-2, per-source grade-minus-measurement drift index.** The per-source grade history comes
from the `prospects.db` snapshot table (2011-2026; FanGraphs 22,219 rows, MLB Pipeline 16,489,
TJStats 3,489), not from the timeseries points, which prune per-source tool blocks on old
vintages: only about 150 debuted players retain one there.

Paired head to head on the players BOTH outlets graded, so no population-composition
confound. FanGraphs grade minus MLB Pipeline grade:

| tool | context | n | mean | 95% CI | excludes zero |
| --- | --- | --- | --- | --- | --- |
| fb | MLB | 526 | **-3.35** | -3.86 to -2.83 | yes |
| hit | MLB | 266 | **-2.54** | -3.35 to -1.75 | yes |
| speed | MLB | 266 | **-2.50** | -3.40 to -1.67 | yes |
| field | MLB | 172 | **-2.33** | -3.28 to -1.42 | yes |
| game_pwr | MLB | 266 | **-1.47** | -2.14 to -0.79 | yes |
| cmd | MLB | 545 | -0.66 | -1.17 to -0.15 | yes |
| fb | upper minors | 577 | **-3.89** | -4.46 to -3.31 | yes |
| hit | upper minors | 676 | **-3.69** | -4.24 to -3.11 | yes |
| game_pwr | upper minors | 676 | **-2.09** | -2.55 to -1.65 | yes |
| cmd | upper minors | 649 | **-1.15** | -1.67 to -0.59 | yes |

**MLB Pipeline's tool grades run hot relative to FanGraphs' on every tool, in both contexts,
on the same players, and every interval excludes zero.** The gap is about two thirds of a tier on
fastballs and half a tier on hit. This is the direction the framework doc's X6
inferred from the published text alone (Pipeline's All-Star anchor sits one tier above
FanGraphs' and BA's) and it is now measured on 500-plus paired players rather than argued
from one sentence.

Against MEASUREMENT rather than against each other, the drift index passes its pre-registered
gate on 6 of 12 tool-context cells (speed and fb in MLB; game_pwr, hit, fb and cmd in the minors),
with Pipeline positive (grades above what the measurement implies) and FanGraphs at or below
zero everywhere. The failures are CI-overlap failures at smaller n, not sign reversals. Note
that both outlets feed the consensus the implied grade is built from, so the absolute drift
level is attenuated toward zero; the paired contrast above is the unattenuated statistic and
is the one to quote.

**Baseball America: NOT COMPUTABLE, and that is itself a finding.** BA contributes rank and
FV to this tree and **zero tool grades, across the entire 2011-2026 snapshot history.** No BA
drift index can exist. BA's published bands can be audited against our measurements (sections
2.2 through 2.8) but never against BA's own grades. This is a concrete instance of the
Phase 5.3 ingestion question and it answers part of it: there is nothing to normalize on the
BA tool axis because we ingest nothing on it.

**INV-3, per-tool grade aging curves.** Descriptive. Mean grade change per year among players
with 3 or more grade snapshots spanning 2 or more years. PASS on the pre-registered gate
(10 of 19 tools clear the 200-player floor with a CI excluding zero).

| tool | n players | grade change per year | 95% CI |
| --- | --- | --- | --- |
| bat_ctrl | 513 | **-1.05** | -1.32 to -0.80 |
| hit | 1,067 | **-0.66** | -0.78 to -0.54 |
| fb | 1,092 | **-0.38** | -0.49 to -0.28 |
| cmd | 1,092 | **-0.36** | -0.46 to -0.26 |
| cb | 669 | -0.26 | -0.38 to -0.15 |
| delivery | 395 | -0.25 | -0.48 to -0.03 |
| pwr | 1,067 | **+0.34** | +0.23 to +0.46 |
| speed | 1,067 | +0.17 | +0.06 to +0.27 |
| sl | 870 | +0.14 | +0.03 to +0.25 |
| throw | 965 | +0.10 | +0.02 to +0.18 |
| athl, ch, field, frame, game_pwr, pitch_sel, raw_pwr | 396 to 1,067 | no significant drift | CI spans zero |

The pattern is coherent: contact and command grades DECAY the longer a player stays on lists,
power grades RISE, and the physical description grades (frame, athleticism, field) do not move
at all. The obvious confound is stated rather than corrected: this pool is list-retention
selected, and a player only accumulates three snapshots over two years by staying rankable, so
these are curves for survivors and not for a cohort. They are published as descriptive and are
fit to nothing.

### 2.13 What this lane did NOT do

No production module was edited. No consensus weight, no eFV scoring path and no exporter
reads `data/tool_grade_tables.json`. The instrument Phase 4.2 names, flagging source grades
that disagree with measurement by two or more tiers, is now MEASURABLE (INV-1 gives the
implied grade, INV-2 the per-source drift) and is deliberately NOT wired: it needs its own
accuracy gate against realized outcomes, which this lane did not run and whose result is not
implied by anything above.
