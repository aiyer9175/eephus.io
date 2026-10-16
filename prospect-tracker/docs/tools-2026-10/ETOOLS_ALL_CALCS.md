# eTools in every tool-grade calculation, the eTool composite, and the registered re-reads (ETOOLS_ALL_CALCS)

Registration status: REGISTERED

Task ETOOLS_ALL_CALCS, written 2026-10-15 on lane wt-ETOOLS_ALL_CALCS (base 67fab873). Docs only,
committed alone before any number named in Part 3 is computed and before any code that serves an
eTool composite exists.

Owner decision EW3-30 (2026-10-15, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`), verbatim: "Make sure
we are using eTools in all calculations for tool grades across the site, as well as making an eTool
composite (we currently are just showing tool composite grade)."

Context. Since ETOOLS_SITEWIDE_FLIP (135a0912, owner decision EW3-27) every surface that PRINTS a
prospect tool grade prints the eTool where one passed (eHIT, ePOW, eSEL, eBAT, eFB, eCMD) and the
consensus grade otherwise (raw power, speed, field, arm, slider, curveball, changeup; eRAW and eSPD
failed the MLB label at the look). The calculations that READ a tool grade still read consensus. This
file inventories every one of them, classifies each, says what this task does with it, and registers
the re-reads that decide whether a registered model may take eTool inputs.

**Nothing was scored to write this document.** No composite was recomputed, no model was run with an
eTool input and no outcome was read. Every figure below is a constant, a date, a seed, a threshold, a
line number at base 67fab873, or a figure already published in a committed artifact.

---

## Part 1. Inventory and classification

Grep at base 67fab873 over the module root, `assets/`, `prospx/index.html` and `tools/` for
`tools_consensus`, `tools_json`, `tool_grades`, `tools.grades`, `composite_*`, `tool_hit` and the
per-tool keys. A consumer is REGISTERED when it has a gate document or a validated registry row,
DESCRIPTIVE otherwise (the task's rule). Four further classes say why a reader is not a consumer of
the shown grade at all.

### 1.1 Descriptive: switch to the shown grades (eTool where one passed, else consensus)

| # | consumer | where (67fab873) | what it computes | registry |
|---|---|---|---|---|
| D1 | the Tool, O-Tool, D-Tool, stuff and command composites (the shown "Tool composite") | `storage.py:343` `_compute_tool_composites`, called for the served payload at `storage.py:12227`, `:12252`, `:12256` | power means of the per-tool grades with the Frame, Athleticism and Delivery inputs | none (glossary `tool`, `o_tool`, `d_tool`) |
| D2 | FVStuff+ and Command+ cohort indices, the top-level `tool` row pill, the composite green and red flags | `storage.py:501` `_attach_tool_plus_indices` | 100 + 10z of the stuff and command composites; the row pill; Tool 60+ and 40- flags | `fv_stuff_plus`, `composite_cmd_plus` (unvalidated, descriptive) |
| D3 | per-tool green and red flags | `stat_flags.py:432` `compute_tool_flags` (called `storage.py:12377`) | 60+ plus, 65+ carry, 35- hole callouts per tool | none |
| D4 | the board's same-grade tiebreak proxy | `storage.py:13415` `_tool_overall` inside `_tbs_proxy` | the Tool composite term (weight 0.6) of the server tiebreak that orders exact grade ties | `tbs_prospect` (unvalidated ordering heuristic) |
| D5 | farm Tool Quality leaf | `storage.py:13916` | top-10 mean of the Tool composite per org; its rank and leaf letter on the report card (it enters only the legacy blend, which the tree composite overwrites) | `farm_grades` (provisional; the letter is unvalidated, the eval measures surplus mass) |
| D6 | movement engine flash floor | `spotlights.py:676` `_tools_flash_floor` | any non-bat tool at 70+ lowers the riser OPS bar | none |
| D7 | Alchemy Lab Prospect Watch starter shape | `pal_export.py:369` (pool), `:720` and `:813` `prospect_role_fit` | arsenal depth (pitches at 55+) and command into the starter shape, the role lean and the mismatch margin | `pal_*` rows score other pal models; the shape has no eval |
| D8 | the client TBS per-tool max | `prospx/index.html:11474` `_perToolMax` | the highest tool grade, a TBS input (weight 0.10) | `tbs_prospect` (unvalidated) |
| D9 | the client composite readers (row Tool pill, strip TOOL chip, card chips, sorts, filters, rail, compare, GFX, TBS composite term, farm and IFA tables) | `prospx/index.html` (`composite_overall` and `p.tool` readers) and `ifa_export.py:212` | they read the served composite fields, so they follow D1 with no code of their own | as D1 |

### 1.2 Registered or validated: re-read before any switch (Part 3)

| # | consumer | where | gate or row | this task |
|---|---|---|---|---|
| M1 | tool-implied production (TIP), the grade-to-stat tables | `tool_implied.py` (a pure library: callers declare rows) | `docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md` Part 1.2, row `tool_implied_production` | re-read R-TIP (3.1) |
| M2 | the prospect stat-line projection | `prospect_statline.py` (TIP_first and TIP_now from hit, game power, fastball, command) | `docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md`, row `mlb_projections_prospects_statline` | re-read R-SL (3.2) |
| M3 | the trade-value archetype policy | `bayes_trade_value.py:2273` (`composite_stuff_plus` in four policy rules) | rows `prospect_surplus` (validated) and `trade_machine_surplus` | re-read R-TV (3.3) |

### 1.3 Blends of a grade with the same stat line: kept on consensus

| # | consumer | where | why not switched |
|---|---|---|---|
| K1 | POW+, HIT+ and PD+ (DISC+) | `prospx/index.html` `computePowerPlus`, `computeHittingPlus`, `computeDisciplinePlus`; `prospx_leaderboard_export.py:534`, `:598` | each blends the tool grade (game and raw power; hit and bat control; pitch selection) with the prospect's own MiLB rate (ISO, K%, BB%). An eTool is the consensus grade moved by those same rates (its sub-drivers are translated ISO, K% and walk rate), so an eTool input counts the stat line twice. Kept on consensus and said in their tooltips; owner question ETOOLS-ALL-Q2 |

### 1.4 Histories, per-source measurements, amateurs and owned inputs: not a shown-grade consumer

| # | reader | where | why unchanged |
|---|---|---|---|
| H1 | tool deltas and tool history charts; per-tool DvM+ and ToolDvM+ (farm development) | `storage.py` `_compute_tool_deltas`, `prospx` `_toolHistoryChart`; `org_tendencies.py:1053`, `dev_attribution.py:380` | a history of consensus grades over time; an eTool is one dated snapshot with no history |
| H2 | per-source accuracy and vintage tables | `source_backtest.py`, `draft_source_backtest.py`, `pipeline_vintage.py`, `tools/tool_accuracy_lab.py:1527` (TAG, Source Accuracy Tools tab), `tools/ba_tool_grade_lab.py` | they score each outlet's own grade by definition |
| H3 | comps and archetype comps | `comps_engine.py:81` (data/comps.json), `archetype_comps_export.py:152` | comps measure a live subject against historical donors on as-of consensus tool features from the eFV matrix (owned by EFV_ETOOLS_REWEIGHT); a donor eTool cannot exist for the reserved 2020 and 2021 lists or before 2011, so a subject on eTools would be measured against donors on consensus. Archetype comps are historical strata with no live bucketing in the artifact |
| H4 | amateurs and international players | `draft_export.py:753` (Tool+), `overseas_export.py:784`, `mock_draft.py:144`, `ifa_export.py:217` (at-signing tool line), `draft_promotion.py:153` | no minor-league line, so no eTool: their eTool IS the consensus grade (owner rule 5). No number moves |
| H5 | eFV inputs | `efv_dataset.py:682` and every `efv_*` reader | owned by EFV_ETOOLS_REWEIGHT (EW3-26); untouched |
| H6 | the eTool builder and ingest | `etools.py`, `consensus.py`, `scrapers.py`, `fangraphs_csv.py`, `tjstats.py`, `baseballamerica_csv.py` | consensus is the eTool's own input, or the code produces consensus |
| H7 | display pass-throughs | `mlb_player_export.py:511`, `report_excerpt.py` | the MLB player page resolves eTools in the browser since 135a0912; report_excerpt cuts report text and reads no grade |

---

## Part 2. The eTool composite (D1, D2)

2.1 **Inputs.** Per player, the consensus grade map (`tools_consensus` at the latest point) with each
passing eTool in its place, read from `data/etools.json` (matched by player key, then MLBAM id, as the
site matches it), and the one Power grade (`pwr`) replaced by game power's eTool, exactly as prospx
`toolGradesShown` does. Every other tool keeps its consensus grade. The eTool enters at its 2 dp value
and is cleaned to the half grade like every consensus input.

2.2 **Formula.** `storage._compute_tool_composites`, unchanged: Tool p = 4 power mean, O-Tool weighted
mean (HIT 40, PWR 40, BCTRL 10, PSEL 6, RUN 4), D-Tool weighted p = 3 power mean, stuff p = 3 power
mean with Frame, Athleticism and Delivery, overall pitcher 0.65 stuff + 0.35 command.

2.3 **Served.** `tools.composite_*` carry the eTool composites; `tools.grades` keeps the consensus
grades; `tools.composite_cons` keeps the consensus composites and the consensus FVStuff+ and Command+;
`tools.composite_basis` says "etools" or "consensus"; `tools.etool_keys` names the tools an eTool
replaced. The card shows the eTool composite with the consensus composite beside it as a reference
and a tooltip naming the basis. The flag `etool_composite.ETOOLS_COMPOSITE_ON` False reproduces the
consensus payload byte for byte.

2.4 **Rounding.** The composite keeps its documented display rule (rounded up, as a tool grade).

---

## Part 3. The registered re-reads

Each re-read runs ONCE, after this commit, with the runner `tools/etools_all_calcs_reread.py`, and
writes `data/_labs/etools/etools_all_calcs_reread.json` (role development, off the webroot). Its result
is pasted into Part 4. No frame below reads a 2020 or 2021 list (R-LV), a 2025 or later debut (R-VM), a
consensus-FV cell or any statistic keyed by one (`docs/PROSPECT_ANCHOR_GATE.md`).

### 3.1 R-TIP: is a TIP table read at the eTool no worse than one read at the consensus grade?

- **Estimand.** TIP's own (gate Part 1.2): the realized MLB stat a tool grade implies over the first
  three MLB seasons after the board year (TIP_f3), for the four PASS eTools whose eTool label is a TIP
  stat: hit to K%, game power to ISO, fastball to pitcher K%, command to pitcher BB%. Pitch selection
  and bat control have no TIP table and are not read.
- **Frame.** The eTools development frame (`etools.py`: board years 2011 to 2019, 2022 to 2024; debut by
  2024; label L_MLB), rows carrying the tool's consensus start G_c (the three-outlet mean) and a finite
  label, built by the same `load_board`, `build_universe`, `attach_candidates`, `attach_labels`,
  `tool_frames` path as the look.
- **Folds.** Leave one board year out, player-disjoint (`etools.fold_train_mask`). In each fold the
  eTool is fit on the training rows only (`etools.etool_fit` with the look's admitted set from
  `data/_labs/etools/etools_eval.json`), applied to the training and test rows; a TIP table
  (`etools.fit_tip`: 5-point bins, thin under 15, PAVA) is fit on the training rows twice, once on the
  eTool and once on G_c, and each is read at its own grade on the test rows (linear between knots, flat
  beyond).
- **Statistic.** d = MAE(eTool table) minus MAE(consensus table) on the identical test rows, pooled
  over folds, unweighted, on the label's scale. Interval: player-clustered paired bootstrap, B 2000,
  seed 20261030, percentile.
- **Pass rule (per tool).** NON-INFERIOR when the upper 95% bound of d is at most 5% of the consensus
  table's MAE (the 5% margin of TOOL_IMPLIED_PRODUCTION_GATE.md Part T). Holm is not applied: each tool
  is its own decision and a non-inferiority pass is the conservative direction for a switch.
- **What it decides.** TIP is a library whose served reader (the Source Accuracy Tools tab, TAG)
  scores each outlet's own grade, so no served number reads a TIP table at the shown grade. A pass is
  the evidence a later stat-line registration (3.2) may cite to take eTool inputs; a fail keeps every
  TIP reader on consensus and says so.
- **Prediction, written before any number.** Non-inferior on all four, d below zero for hit and fastball
  (the eTool's largest rank gains at the look).

### 3.2 R-SL: the prospect stat-line projection

The stat-line model is registered and unserved; its one development read is spent (gate 1.7, frozen by
Amendment 1 of 2026-10-14) and holdout H is read once by TL_17_STATLINE_LOOK. Its gate allows no second
development read and no change to the candidate before the look ("a change made after any holdout row
has been read voids the look"; amendments "change no threshold, frame, candidate"). So no eTool-input
re-read of the stat-line can run under its own gate before TL_17. R-SL is registered as: KEEP
CONSENSUS until TL_17's look is recorded; then the eTool-input variant is a new registration whose
license is R-TIP's result. Owner question ETOOLS-ALL-Q3.

### 3.3 R-TV: the trade-value archetype policy

- **Estimand.** The trade-value model's own output per player (`bayes_trade_value.compute_all_trade_values`
  on the served payload: value, posterior multiplier, floors and tags), whose validated row is scored on
  held-out surplus calibration (`prospect_surplus`), a backtest this task may not run
  (`backtest.run_backtest` is banned).
- **Read.** Run `compute_all_trade_values` twice on the identical player list from the rebuilt export:
  once with `composite_stuff_plus` on the consensus basis (`tools.composite_cons`), once on the eTool basis.
- **Pass rule.** SWITCH only if every player's output is identical (no rule fires differently), so the
  eTool version cannot be worse on the validated estimand. Any difference keeps consensus, because the
  only scorer of a difference is the banned backtest; the count and the players are recorded.

---

## Part 4. Results

EMPTY AT REGISTRATION. Each re-read's result is pasted here, dated, by this task's results commit.
