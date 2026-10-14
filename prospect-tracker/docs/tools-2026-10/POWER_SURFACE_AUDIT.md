# Power surface audit: where the one PWR grade comes from and what reads it

Task TL_1_POWER_SURFACE_AUDIT, written 2026-10-08 against HEAD 0f9fb164 (branch
efv-conviction-2026-08-08). Plan: Part 9 section 9.4.1 'The power composite audit', which
publishes LANE_C.md section 1.2 (Part 9 bundle) re-verified at HEAD. Class 1: docs only,
nothing served moves. No statistic against any outcome is computed in this document; every
outcome figure below is quoted from a record that already exists, with its location.

The owner's ask (2026-10-01, verbatim): "Right now, we are only using raw power grade for our
power tool composite grade and across the site. We have the data for "Game Power" tool on
FanGraphs as well. Can we incorporate game power in some way and test to see if it corresponds
as an eFV driver? Can we blend game power into our power composite grades to make them more
accurate (and then test our power tool as an eFV driver)?"

## 1. Verdict on the owner's sentence

**Where it holds.** On every hitter FanGraphs grades, the one PWR the site shows is half
FanGraphs' raw power grade. FanGraphs is the only outlet that publishes raw power on the live
board (ESPN adds it on one active hitter), so that half is a one-outlet input, and it carries
the same weight as the game power consensus, which up to five outlets share (six on one
player today). Today that is 857 of the 1,041 active players with a power grade (82%).

**Where it does not hold.**
- No surface reads raw power alone. The served `pwr` is the mean of the game and raw
  consensus grades; where raw is absent it is the game consensus.
- No eFV model reads any power grade. eFV v1's hitter feature list has no power term
  (`efv_model._FEATURES_HIT`), the V2 hitter block has none (`efv_v2_model` hit block:
  obp_rel, contact, tool_hit, tool_speed, is_college, level_rank), and the dark eFV v3
  selection of 2026-10-08 adds no hitter column.
- Every outlet's single "Power" grade lands on `game_pwr`, not `raw_pwr`: MLB Pipeline,
  TJStats, Baseball America, Just Baseball, and ESPN when ESPN prints only "Power".

So game power is already in the composite, from every outlet. What the owner is seeing is the
weight: FanGraphs' raw grade sets half of PWR on its own.

## 2. Where the grades come from (producers) and the snapshot census

Producer mappings at HEAD (raw power reaches the database from FanGraphs and ESPN only):

| producer | anchor | line at HEAD | mapping |
|---|---|---|---|
| FanGraphs CSV | `fangraphs_csv.py` column table at '("game pwr",' | 279-280 | "game pwr" to `game_pwr`, "raw pwr" to `raw_pwr` |
| MLB Pipeline | `scrapers.py` PIPELINE_TOOL_KEY | 630 (632) | "power" to `game_pwr`; a "raw power" key exists, no row carries it |
| ESPN (labels) | `scrapers.py` ESPN_TOOL_KEY | 647 (649-651) | "game power" and bare "power" to `game_pwr`, "raw power" to `raw_pwr` |
| ESPN (prose) | `scrapers.py` ESPN_PROSE_TOOL_NOUN | 767-769 | same three nouns, same keys |
| Just Baseball | `scrapers.py` JB_TOOL_KEY | 1903 (1911-1913) | "power" to `game_pwr`; a "raw power" key exists, no row carries it |
| TJStats | `tjstats.py` _BAT_TOOL_MAP | 177 | "power" to `game_pwr` |
| Baseball America | `baseballamerica_csv.py` BA_POWER_TARGET | 459 (reason 454-458; column map 391) | "Power" to `game_pwr` |

Snapshot census, recounted read-only (`prospects.db` opened with mode=ro, the worktree copy,
latest snapshot_date 2026-10-07): rows whose `tools_json` carries a non-null grade.

| source | years with a power grade | game_pwr rows | raw_pwr rows | both |
|---|---|---|---|---|
| mlb_pipeline | 2011-2026 | 13,078 | 0 | 0 |
| fangraphs | 2017-2026 | 11,594 | 11,596 | 11,594 |
| tjstats | 2026 | 5,095 | 0 | 0 |
| baseballamerica | 2023-2026 | 2,454 | 0 | 0 |
| just_baseball | 2026 | 288 | 0 | 0 |
| espn | 2025-2026 | 46 | 40 | 38 |
| total | | 32,555 | 11,636 | 11,632 |

FanGraphs by year (game / raw): 2017 348/348, 2018 810/810, 2019 915/915, 2020 1,215/1,217,
2021 1,317/1,317, 2022 1,270/1,270, 2023 1,226/1,226, 2024 1,205/1,205, 2025 1,339/1,339,
2026 1,949/1,949. Pipeline by year: 2011 41, 2012 144, 2013 2, 2014 341, 2015 498, 2016 514,
2017 512, 2018 525, 2019 525, 2020 526, 2021 542, 2022 584, 2023 567, 2024 593, 2025 576,
2026 6,588. Baseball America: 2023 476, 2024 472, 2025 461, 2026 1,045. ESPN: 2025 4/1,
2026 42/39. No other key naming power exists in any source's `tools_json`.

Against LANE_C 1.2's census of 2026-10-01: FanGraphs, Baseball America and ESPN are unchanged;
Pipeline rose from 12,927 to 13,078 and TJStats from 4,967 to 5,095 (daily live rows since);
Just Baseball's 288 is unchanged. FanGraphs carries two raw-only rows (2020).

## 3. The composition arithmetic

The code path (section 5 rows S1 and S2): each tool key is an unweighted mean across the
outlets that publish it, rounded to 0.5; then `pwr` = round-half(mean(game consensus, raw
consensus)) when both exist, else the one present.

For a hitter graded by FanGraphs and Pipeline only:

    game consensus = (FG game + Pipeline power) / 2
    raw consensus  = FG raw
    pwr            = (game consensus + raw consensus) / 2
                   = 0.25 FG game + 0.25 Pipeline power + 0.50 FG raw

In general, with k outlets publishing a game grade and FanGraphs the only raw publisher, FG raw
carries 0.50, each game outlet carries 0.50 / k, and FanGraphs' total share is
0.50 + 0.50 / k (1.00 when FanGraphs is the only game publisher, 0.67 at k = 3).

Live composition, recounted (latest consensus point of every active player in
`data/timeseries.json`, generated 2026-10-07T16:22:59Z, 4,691 players):

| latest point carries | players |
|---|---|
| game_pwr, raw_pwr and pwr | 857 |
| game_pwr and pwr, no raw_pwr | 184 |
| raw_pwr without game_pwr | 0 |
| no power grade | 3,650 |

On all 857 both-carriers the served `pwr` equals round-half(mean(game consensus, raw
consensus)) exactly (857 of 857 checked). Against LANE_C's 2026-10-01 count (857 / 183 / 0),
the game-only group gained one player.

Publishers on the 857 both-carriers (from each latest point's `per_source`):
- raw power: FanGraphs alone on 856, FanGraphs and ESPN on 1.
- game power, outlets per player: 1 on 145 (FanGraphs only, so PWR is FanGraphs' own
  (game + raw) / 2), 2 on 98, 3 on 535, 4 on 33, 5 on 45, 6 on 1.
- game power by outlet: FanGraphs 857, Pipeline 685, Baseball America 640, Just Baseball 66,
  TJStats 59, ESPN 2.

The 184 game-only players are graded by Pipeline (141), Baseball America (130), Just Baseball
(1) and TJStats (1), with 1 outlet on 97, 2 on 85 and 3 on 2; their PWR is the game consensus.

A side finding that bends the arithmetic on a few rows (section 7, item O1): on 41 of the
1,041 latest points the game consensus differs from the round-half mean of the per-source
grades the point lists, because one outlet entered twice on the same day.

## 4. What the record already says (quoted, not recomputed)

- **BA2 B4** (`docs/efv-2026-08-07b/TOOL_GRADE_WEIGHT_GATE.md` '### 8.6', item B4): on the
  common-set read against realized MLB ISO (n 228), BA Power 0.3646, FG game power 0.3106,
  FG raw power 0.2560. The one difference given an interval there, BA minus FG game
  (+0.054, CI95 -0.0349 to +0.1461), includes zero; no interval for FG game minus FG raw is
  on record, so that ordering is a direction, not a resolved result. On level, on the 634-row
  overlap, FG raw averages 53.92 against FG game 48.01 and BA Power 50.16. B4's board years
  include list vintages 2020 and 2021, which were reserved later (LANE_C 1.1 disclosure);
  this document does not re-read them.
- **Frame projectability, 2026-09-25** (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, the
  'RESULT frame projectability' entry near line 303): for hitters the lean-body signal ran
  the wrong way for forward MiLB ISO, located where scouts raise raw power for lean
  projectable bodies and game ISO does not follow. Post hoc, so a hypothesis only; a fresh
  pre-declared test exists and is an open owner choice there.
- **Disjoint tool sets** (`docs/efv-2026-07-30/TOOL_NORMALIZATION_VERDICT.md` '## 3. The
  finding worth keeping'): raw_pwr, bat_ctrl and pitch_sel are FanGraphs-only keys, so the
  Tools+ power mean runs over different input sets for FanGraphs-graded and Pipeline-only
  players. Raw power's half share of PWR is one instance of that composition problem.
- **Game power as an eFV driver** has been tested four times and lost every time (LANE_C 1.3;
  `data/xfv_arm_ledger.json`). Raw power and the PWR composite have never been an eFV arm.
  Under owner answer TL-Q1 (a) this program gives the power composite no eFV verdict; the
  blend itself is gated as look P (plan 9.4.4, LANE_C '### 2.5'), and owner answer TL-Q4
  (2026-10-01) set PWR to mean production power, answering to realized ISO.

## 5. Every reader of a power grade at HEAD

Method: grep for `raw_pwr`, `game_pwr`, the bare word `pwr`, `composite_overall` and
`composite_off` across the module root's `*.py`, `assets/*.js` and `prospx/index.html`,
excluding `test_*.py` and `tools/`; each hit read in place. Lines are at HEAD 0f9fb164; where
LANE_C's line differs, the anchor is what was matched. "Moves" answers: would a change to the
served `pwr` formula (consensus.py '# v12') move what this surface shows or writes? Readers
that compute their own per-source mean of game and raw are marked no, with the formula they
carry, since a consensus change does not reach them.

### 5.1 Python (exporters and the build)

| # | surface | anchor | line at HEAD | grade it reads | moves |
|---|---|---|---|---|---|
| S1 | per-tool consensus | `consensus.py` compute_consensus_point(), at '# Per-tool consensus = unweighted mean' | 1591-1602 | `game_pwr` and `raw_pwr` as separate keys, each an equal mean across its publishers, round 0.5 | no (these are the formula's inputs) |
| S2 | the served `pwr` | `consensus.py` at '# v12' | 1603-1614 | round-half(mean(game, raw)), else the one present | yes (this is the formula) |
| S3 | O-Tool `composite_off` | `storage._compute_tool_composites` (343), at 'O-Tool weighted blend', `_pwr_value` (419) | 413-449 | `pwr` at weight 0.40 (fallback mean of game and raw) | yes |
| S4 | Tool `composite_overall` | same function, at 'Tool (overall) is the EQUALLY-WEIGHTED' | 450-473 | `pwr` inside the p = 4 power mean | yes |
| S5 | payload `tool` (row pill and sort) | `storage.py` at 'Top-level convenience field for row pills' | 544-548 | round(`composite_overall`) | yes (added) |
| S6 | payload `tool_flags` (Tool, O-Tool at 60 and 40) | `storage.py` at 'Composite-driven green/red flags' | 558 onward | `composite_overall`, `composite_off` | yes (added) |
| S7 | stat flags, per tool | `stat_flags.compute_tool_flags`, loop over `_TOOL_LABELS_HITTER` | 406-418, 447 | `game_pwr` and `raw_pwr` separately; `pwr` is not a labelled key | no |
| S8 | stat flags, composites | `stat_flags.py` at 'Only composite_overall fires the red flag' | 504-529 | `composite_overall`, `composite_off` | yes |
| S9 | per-tool DvM+ groups | `storage.TOOL_GROUPS` ('pwr': ['pwr']), `_BUCKET_TOOL_IMPORTANCE` | 8538 (8540), 8562-8567 | `pwr` deltas across consensus history | yes |
| S10 | PowerDvM+ league pass and Tools DvM+ | `storage.py` at 'Per-tool DvM+ league pass', `_HITTER_TOOL_DVM_KEYS`, `_BUCKET_TOOL_WEIGHTS` | 14570, 14759, 15681-15690 | `pwr` | yes |
| S11 | DvM+ tree PWR leaf | `storage.py` `_HIT_TOOLS` ('pwr', 'PWR') | 6860 (6862) | `pwr` | yes |
| S12 | board order on equal surfaced grade | `storage.py` `_tool_overall`, `_tbs_proxy` | 12803, 12818 | `composite_overall` (tool term weight 0.6 in the proxy) | yes (added) |
| S13 | farm Tool Quality and the farm score | `storage.py` at 'Tool Quality accumulator', `tools_quality`, FARM_WEIGHT_TOOLS_QUALITY 0.03 | 13285-13300, 13991, 5049 (used 15911), letter 15987 | top-10 and pool mean of `composite_overall` | yes (added) |
| S14 | IFA export, current tool | `ifa_export.py` at 'Tool composite: current' | 210-214 | `composite_overall` as `tool_current` | yes |
| S15 | IFA export, at-signing tool | `ifa_export.py` `tool_signing` | 215-220 | mean of every numeric value in the earliest point's `tools_consensus`, which holds `game_pwr`, `raw_pwr` and `pwr` together | yes (added; see O2) |
| S16 | PROSPX Leaderboards POW+ | `prospx_leaderboard_export._pwr_grade`, `pow_plus` | 516, 529 (tool term 555, weight 0.30) | `pwr`, else mean(game, raw) | yes (added) |
| S17 | eFV v1 | `efv_model._FEATURES_HIT`; `_vec` | 113; 1473 | no power grade in the feature list; `_vec` builds `tool_game_pwr` that no head reads | no |
| S18 | eFV explainer labels | `efv_score._FACTOR_LABELS` | 816 | a label for `tool_game_pwr`, which no served head carries | no (added) |
| S19 | eFV V2 | `efv_v2_model.py` hit block | 655 | no power grade | no |
| S20 | eFV v3 (dark) | `efv_v3.W2_COLUMNS` (w2s_pwr_present_hit, w2s_game_pwr_hit), `efv_w2_scout` columns | 92-93; 143-148 | per-source game and raw future and present grades; EFV_V3_ON False (66); `data/_labs/efv_v3/efv_v3_select.json` (2026-10-08) selects no hitter column | no (added) |
| S21 | eFV matrices | `efv_dataset._HIT_TOOLS` | 467 (2065) | `tool_game_pwr`, `tool_raw_pwr` columns | no |
| S22 | tool eFV | `efv_tools._TOOLS`, `_PASSTHROUGH` | 40, 46 | `game_pwr` against ISO; `raw_pwr` passes through | no |
| S23 | comps | `archetype_comps_export.py` tool_game_pwr CORE, tool_raw_pwr EXT; `comps_engine.ARCHETYPE_AXES` | 158, 209; 81 | both, game as the core cut | no |
| S24 | org tool development | `org_tendencies.HIT_TOOLS` | 80 | both, separately | no |
| S25 | mock draft tool tilts | `mock_draft._TOOL_LABELS` | 86 | labels for `game_pwr` and `raw_pwr` tilts | no (added) |
| S26 | /projections/ scouting pills | `assets/projections.js` TOOL_PILLS | 3162 | "Game Pwr" and "Raw Pwr" as two pills | no |
| S27 | GRPO power tier | `grpo_prospect.py` at 'Raw power tier from max_ev' | 271-276 | Statcast max exit velocity, not a grade | no |
| S28 | FA profile "pwr" | `fa_projection.py` | 795-826 | MLB ISO relative to league, not a grade | no |
| S29 | projections ML profile flag | `proj_ml.py` | 273 | the FA profile suffix '\|pwr', not a grade | no (added) |

### 5.2 PROSPX (`prospx/index.html`)

| # | surface | anchor (function) | line at HEAD | grade it reads | moves |
|---|---|---|---|---|---|
| X1 | the PWR label | TOOL_DISPLAY_NAMES | 10768-10772 | label only | no |
| X2 | FV tie order | `_toolComposite` (used by fvCmpDesc) | 11559-11562 | `composite_overall` | yes |
| X3 | list-row tool strip | `_toolGradeStripHTML` | 12622-12644 | `grades.pwr`, else the latest point's `pwr` | yes |
| X4 | active tool filter | `#tool-filter-key` option "pwr"; getFilteredActives | 9542; 16297-16306 | `grades.pwr`; "Any tool" also reads `game_pwr` and `raw_pwr` | yes for "Power" (added); "Any tool" no while the formula stays a convex blend of game and raw |
| X5 | active tool sort | `#tool-sort-select`; getFilteredActives | 9627-9633; 16405-16426, 16608 | `composite_overall`; "Game Pwr" and "Raw Pwr" separately, no PWR option | yes for the composite; no for game and raw |
| X6 | detail sidebar peers | `_prospectDetailSidebarCards` | 17355 | `composite_overall` | yes |
| X7 | draft and IFA detail sidebars | `_draftDetailSidebarCards`, `_overseasDetailSidebarCards` (`_toolMean`) | 17490-17503, 17645-17672 | own formula: mean over outlets of each outlet's PWR (FanGraphs' (game + raw) / 2) from `tool_grades` | no |
| X8 | active context rail | renderActiveContextRail TOOL_OPTS | 18030-18033 | game and raw separately | no |
| X9 | chart axis "Power" | CHART_AXES, `_tcOf` | 19499, 19589 | latest point's `pwr` | yes |
| X10 | radar | `_radarToolsFor` | 20991-20995 | `grades.pwr` | yes |
| X11 | draft and IFA board sorts | `_applyDraftSort`, `_applyOverseasSort` | 24801-24814, 27293-27300 | own "composite": mean of every per-outlet grade from `tool_grades` (game and raw each counted) | no |
| X12 | draft and IFA best-tool cards | `_renderDraftLeaderboard` (`_bump`), `_renderOverseasLeaderboard` (toolBest) | 26135-26152, 31203-31215 | own formula: best single outlet's PWR | no |
| X13 | per-source tool grid | `_renderProspectToolsGrid` | 27740-27753 | own formula: each outlet's round((game + raw) / 2) | no |
| X14 | draft detail strip and class comparison | renderDraftDetail `_consensusToolGrade`, toolsVsClassSection | 30171-30184, 30216-30226 | game and raw separately; class comparison as X7 | no |
| X15 | archetype and insight labels | `_ARCH_DIM_LABEL`, `_gfxInsight` | 33745, 36566 | labels only | no |
| X16 | prospect card radar and tool row | buildProspectCard | 36739-36747 | `grades.pwr`, else latest `pwr` | yes |
| X17 | compare card radar | buildCompareCard | 37392-37394 | `pwr` | yes |
| X18 | quick-read summary (top two tools) | makeQuickReadSummaryParts | 39863-39886 | `pwr` | yes |
| X19 | tool chips and tooltip | `_resolvePwr`; makeToolGradeChips | 40281-40289; 40506 (Tool chip), 40522 (PWR chip), 40533 (tooltip) | `composite_overall`; `pwr`, else mean(game, raw) | yes |
| X20 | tool history chart | `_toolHistoryChart` (local `_resolvePwr`) | 40329-40344 | `pwr` on every consensus point | yes |
| X21 | farm roster snapshot "Tool top10" | makeRosterSnapshotTile | 42321 | `tools_quality.top10_mean` (S13) | yes (added) |
| X22 | farm tool development "Power" cell | makeFarmToolDevCard | 42369 | PowerDvM+ (S10) | yes (added) |
| X23 | age and FV scatter | makeAgeFvScatter | 43930 | `composite_overall` | yes (added) |
| X24 | player page top tool tile | renderPlayerDetail topToolTile | 49759-49779 | `grades.pwr`, else mean(game, raw) | yes |
| X25 | player page Tool and O-Tool chips | renderPlayerDetail compositeNum, compositeChip | 49792, 50694, 50727-50729, 50900 | `composite_overall`, `composite_off` | yes |
| X26 | player page per-source tool rows and history | renderPlayerDetail toolsSection, resolveHist, perSourceTabbedSection, perSourceToolsSection | 50600-50605, 50968-50974, 51753-51757, 51848-51850 | own formula: each outlet's (game + raw) / 2 | no |
| X27 | PWR glossary link | renderPlayerDetail TOOL_TO_GLOSSARY | 50649 | maps `pwr` to the `game_power` entry (see O3) | no (copy) |
| X28 | similar prospects | similarProspectsSection | 52172-52173 | `composite_overall` distance | yes (added) |
| X29 | org tendencies labels | `_OT_TOOL_LABELS`, `_OT_TOOL_NAME` | 52849, 53365-53366 | game and raw labels | no |
| X30 | farm roster sort and tool leaders | `_renderFarmDetailBody` ROSTER_SORTERS, toolsLeaders | 53688-53689, 54407-54409 | `composite_overall` | yes (added) |
| X31 | Tool pill | toolPlusPillHTML | 56450-56465 | `composite_overall`; `pwr` in the breakdown | yes |
| X32 | POW+ (browser) | `_pwrToolGrade`, computePowerPlus | 56627-56631, 56697-56707 | `pwr`, else mean(game, raw); tool term weight 0.30 | yes (added) |
| X33 | compare stat table | makeCompareStatTable | 57193-57213 | `pwr` row and Tool composite row | yes |

### 5.3 Surfaces this audit adds to LANE_C 1.2's table

S5, S6, S12, S13, S15, S16, S18, S20, S25, S29 on the Python side; X4, X21, X22, X23, X28,
X30, X32 on PROSPX. The ones that move with a `pwr` change and were not in the table: the
payload `tool` field and `tool_flags`, the board's equal-grade order through `_tbs_proxy`,
farm Tool Quality and its 0.03 share of the farm score, the IFA at-signing tool, POW+ on
the Leaderboards export and in the browser, the PROSPX "Power" tool filter, the farm "Tool
top10" and "Power" development cells, the age and FV scatter, similar prospects, and the
farm roster's tool sort and leaders. LANE_C's PROSPX line numbers (39305 and nearby) have
drifted by about 1,000 lines; the anchors above are current.

## 6. What a change to the served `pwr` formula moves

By construction (rows marked yes): the 857 both-graded hitters' `pwr` and, through it,
`composite_off` and `composite_overall`; the payload `tool` field and `tool_flags`; stat
flags crossing 60 or 40; PowerDvM+, the per-bucket Tools DvM+ and the DvM+ tree PWR leaf;
the board's equal-grade order; farm Tool Quality, the farm score's Tool Quality term and its
letter; the IFA export's `tool_current` and `tool_signing`; POW+ in
`data/prospx_leaderboard.json` and in the browser; and on PROSPX the chips, strip, radar,
cards, filter, sorts, history chart, scatter, similar prospects and compare table listed
above. The 184 game-only players move only under a formula that changes the game-only case.

Not moved by construction: eFV v1, V2 and v3 (no power input), tool eFV, comps, org tool
development, GRPO, the FA and projections profiles, the /projections/ pills, the PROSPX
per-source rows and history, and the draft and IFA board surfaces that carry their own
per-source formula (X7, X11, X12, X13, X14). Those last ones would then disagree with the
consensus PWR; whether they follow is a question for the flip task, not this audit.

## 7. Side observations (recorded, not fixed here)

- **O1. Same-day duplicate outlet rows enter the tool consensus.** On the latest point,
  `tools_consensus` differs from the round-half mean of the listed per-source grades on 41 of
  1,041 game_pwr carriers, 50 of 1,041 hit carriers and 41 of 1,041 speed carriers; raw_pwr
  matches on all 857. The checked case (Caden Bodine, 2026-10-02) has two MLB Pipeline rows that day
  ('MLB Pipeline 2026 Rays Top 30' and 'MLB Pipeline Live 2026-10-02'), so Pipeline counts
  twice (game consensus 41.0 against a five-outlet mean of 40). The comment in
  `consensus.py` near line 1380 says each outlet arrives at most once. Not power-specific;
  a separate defect task.
- **O2. The IFA at-signing tool counts power up to three times.** `ifa_export.py` 215-220
  averages every numeric value in the earliest `tools_consensus`, so a FanGraphs-graded
  hitter's game, raw and `pwr` all enter, beside FanGraphs' physical grades.
- **O3. The PWR label points at the game power definition.** On the player page the "Power"
  tool links to the glossary entry `game_power` ("20-80 grade for in-game power output"),
  while the value shown is half raw power for 857 hitters. No glossary entry names PWR
  itself. The chip tooltip that discloses "Game x, Raw y (mean)" (X19, 40533) fires only when
  `pwr` is absent, which no served row is today, so the split is not shown anywhere on the
  served chip.
- **O4. Four PWR formulas live on PROSPX.** The consensus `pwr` (X3 and the rows marked yes),
  each outlet's (game + raw) / 2 (X13, X26), a mean over outlets of those (X7, X14) and the
  best single outlet's (X12), plus the draft and IFA sort's mean of every per-outlet grade
  (X11). For a FanGraphs and Pipeline hitter the mean over outlets (X7, X14) is
  ((FG game + FG raw) / 2 + Pipeline power) / 2, which gives FanGraphs raw a weight of 0.25,
  not the consensus formula's 0.50.

## 8. Reproduce

Counts in sections 2 and 3, read-only, from the module root: open `prospects.db` as
`sqlite3.connect('file:prospects.db?mode=ro', uri=True)`, parse `snapshots.tools_json` and
count non-null `game_pwr` and `raw_pwr` by source and the year of `snapshot_date`; load
`data/timeseries.json` and classify each player's last entry in `players[].points` by which
of `game_pwr`, `raw_pwr` and `pwr` its `tools_consensus` carries, and its `per_source`
entries by which outlets carry each key. Surfaces in section 5:

    grep -nE "raw_pwr|game_pwr|\bpwr\b|composite_overall|composite_off" *.py assets/*.js prospx/index.html

with `test_*.py` and `tools/` excluded and each hit read in place.

## 9. Blast radius (measured)

Left empty for TL_6_POWER_COMPOSITE_DARK, which measures it flag on against flag off on every
served artifact.

look P: C0 retains; nothing built
