# eWAR v3 valuation input gate (registered 2026-10-22, NOT READ)

Status: **registered, not read.** Model id `ewar_v3_valuation_input`. At this commit no candidate
valuation exists: no Trade Machine value, FA market price, rational value, WAR path or projection has
been computed on eWAR v3, and no statistic of section 5 has been computed for either arm on any frame.
Every rule below was written before any such number existed, so none of it was chosen after seeing one.

**The one look is on 2027-11-03** (section 7), and only once the data of section 4 exist. The build
that makes eWAR v3 a valuation input follows a pass, and only when the orchestrator queues it.

## 1. Why

Owner answer **SWAR-Q4 (c) 'Also in valuations'**, 2026-10-01, recorded in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md` under 'eWAR v3 batch 2': "eWAR v3 becomes a comparison
input for Trade Machine and free-agent value after its own registered valuation test. Task
EWV3_VALUATION_GATE_REGISTRATION (the build follows a pass)". This document is that test. The eWAR v3
plan is `part8/ebr/PLAN.md` (the Part 8 bundle) and its registration is
`docs/ebr-2026-09-30/EBR_GATE.md`; task EBR_3 (EWAR_V3_ASSEMBLE) assembled the series and flipped it
to the displayed WAR (EBR_GATE.md part 11.10, integrated at `9ead814e`).

Owner decision EW3-5 (2026-10-14) waives registered dates and look days. It does not waive data: the
frame of section 4 does not exist before the 2026-27 free-agent winter and the 2027 regular season
have happened, so the date of section 7 is the earliest date the data can exist, not a waiting rule.
A look run before 2027-11-03 on complete data would be recorded as an OWNER-WAIVED EARLY READ with a
dated note below section 11; a look run before the data exist is not a look.

## 2. The candidate and the incumbents

Line numbers are pinned to `9ead814e`; the anchor beside each number wins if the two disagree.

### 2.1 What eWAR v3 is on the valuation frames

eWAR v3 (`data/ewar_v3.json`, `ewar_v3.py`, `tools/build_ewar_v3.py`, provider `ewar_v3` in
`war_source.py`) is the frozen published fWAR vintage (`data/fwar_vintage.json`) plus the departures
the looks admitted. EBR_GATE.md parts 11.10.1 and 11.10.2 record that no look-decided part was
admitted and that one part is carried by owner override (EW3-32): the ABS reattribution part,
candidate part 8, **2026 on only**, zero-sum per season and side. So, by construction and without any
measurement here:

- on every player-season before 2026, eWAR v3 equals fWAR exactly;
- in 2026, eWAR v3 minus fWAR is the ABS term alone (g_abs / RPW for a hitter, h_abs / RPW for a
  pitcher), which can be nonzero on any 2026 row with PA or IP because the failure-cost terms are
  re-centred per PA and per IP across each side.

### 2.2 The incumbent input per consumer, from the code

- **War source.** `war_source.DEFAULT_PROVIDER = "fwar"` (`war_source.py:195`, at 'DEFAULT_PROVIDER:
  str = "fwar"') is the label WAR every fitted consumer reads; `DISPLAY_PROVIDER` (`:204`) is
  `ewar_v3` since EWAR_V3_LIVE but feeds display doors only; `REFUSED_DOORS` (`:211`) refuses
  `ewar_v3` on the `arb_spine` door.
- **The shared corpus.** `fa_projection._side_war_age_maps(provider=None)` (`fa_projection.py:97`,
  default resolved at `:138`, 'provider = provider or war_source.DEFAULT_PROVIDER') reads the
  war_daily stint frames on `fwar` for every corpus row's `war` and `war_total`;
  `fa_projection._war_provider()` (`:245`) stamps the corpus with the same default.
  `proj_backtest.py:76` reads `war_source.stint_frame(side)` on the same default.
- **Consumer F, free-agent value (the FA module).** The WAR path of a free agent is
  `fa_market.contract_war_path(hist, ...)` (`fa_market.py:491`) on the corpus history above; its
  year-one WAR `_war_path.war_y1` enters the market model's years and guarantee features
  (`_features_years`, `:2067`, 'w1 = s["_war_path"]["war_y1"]' at `:2075`; `_features_guar`,
  `:2102`, the same line at `:2117`), and the path prices the rational value
  (`rational_value_usd`, `:1465`). **Incumbent F: the corpus WAR on `fwar`, the frozen fWAR vintage.**
- **Consumer T, the Trade Machine.** `bayes_trade_value.apply_platform_surplus`
  (`bayes_trade_value.py:4999`) re-points every modeled MLB row of `data/trade_values.json` to MLB
  Projections' `surTotal` (`data/mlb_projections.json`, built by `proj_export.py`, at
  'm["surTotal"] = int((ros_d or 0.0) + npv)', `proj_export.py:1448`), whose WAR path comes from the
  same projection engine and the same corpus on `fwar`. Rows the projections do not model fall back to
  the eFV backgrade surplus, whose credibility terms read the label block `career_war_label`
  (`bayes_trade_value.py:1653`, `:2061`, `:3009`, `:3671`). **Incumbent T: the corpus WAR on `fwar`
  through `surTotal` for modeled MLB rows.**

Both incumbents are fWAR. The candidate is therefore fWAR plus the 2026 ABS term on the 2026 rows of
the corpus, and the two arms differ only through 2026 player-seasons.

### 2.3 The candidate

**Arm R (replacement, the registered candidate):** the corpus's `war` and `war_total` read on
provider `ewar_v3` instead of `fwar`, through the same `war_source.stint_frame` door, with every other
input, constant, model version, fit window and code path of the consumer unchanged, and every model in
the consumer's chain refitted exactly as the incumbent is (forward-chained, on data strictly before
the frame). For consumer T the `career_war_label` block is read on the same provider in both arms of
the fallback, but fallback rows are not scored (section 4.2).

**Blends are not a separate arm.** Because the two series differ only by the ABS term, a blend
w * eWAR v3 + (1 - w) * fWAR is fWAR + w * ABS. No w has a fitted basis that does not spend the frame,
so this registration carries the replacement (w = 1) alone; a blended arm would be a new registration
on a new frame (owner question EWV3-VAL-Q1 in the task report, default: replacement only).

## 3. The frozen record

- **When.** One freeze, by a later task (proposed id EWV3_VALUATION_FREEZE), on a day on or after
  2026-11-02 (after the 2026 season is final in the frozen vintage and `data/ewar_v3.json` carries it)
  and before the first game of the 2027 regular season, never a registered look day. If the 2026
  season is not final in `data/fwar_vintage.json` on that day, the task stops with 'BLOCKER: date'.
- **What.** For both arms, from the same inputs on the same day: consumer F's predicted guarantee,
  AAV and years for every member of the 2027 free-agent class (class_year 2027, platform season 2026,
  `fa_market.py:402`, at 'class_year - 1'), trained on winters strictly before 2027 exactly as
  `fa_backtest.run_market_gate` (`fa_backtest.py:789`) trains; consumer T's `trade_value_mm` for every
  modeled MLB row of a Trade Machine board built through `tools/export_trade_values.py`'s two passes.
  The incumbent arm is the served chain re-run on that day; the candidate arm is the same chain with
  the provider of 2.3. Both are written under `.cache/ewar_v3_valuation/preview/` and frozen to
  `.cache/ewar_v3_valuation/record/<YYYY-MM-DD>.json.gz` with the SHA-256 of canonical JSON in
  `chain.json`, first write wins. Nothing under `data/` and nothing served changes.
- **Not read.** The freeze computes values, never an outcome: no actual contract, no 2027 WAR and no
  error of either arm. It prints counts only (rows per arm, rows whose inputs differ).

## 4. The frame

### 4.1 Why only this frame can discriminate

Every frame the valuation gates already score uses inputs from 2025 or earlier: FA Hard Gate 2 scores
winters 2018 on (`GATE2_WARMUP_THROUGH = 2017`, `fa_backtest.py:566`), whose platforms end in 2025;
Gate 1's target seasons end in 2025 (`fa_config.yaml`, projection.eval.target_seasons); the Trade
Machine slice of `tools/trade_machine_backtest.py` scores resolved careers. On all of them the two
arms are identical row for row (2.1), so either statistic's difference is exactly 0 there and a look
on them cannot pass. The held-out frame is therefore the next unit of each gate's own forward chain,
the first whose inputs include 2026.

### 4.2 The frame per consumer

- **F:** the 2027 free-agent class: every signing of the winter 2026-27 in the FA signing corpus Gate 2
  scores, with the same inclusion, NPV basis and deferral handling as `run_market_gate`, signed on or
  before the look's data cut (section 7). The next winter of the gate's own forward chain.
- **T:** every modeled MLB row of the frozen board (section 3) with a 2027 outcome on the label, the
  next season of the trade board's own realized-WAR backtest. Excluded and counted, never scored:
  fallback rows (no `surTotal`), prospects, and any player whose MLB debut is in 2025 or later (the
  reserved eFV frame R-VM).

### 4.3 Frames this gate never touches

The reserved eFV frames (R-LV, list vintages 2020 and 2021; R-VM, the 2025 and later debut
cohorts); the eBR outcome look's frames and the skill look's frames and holdout (EBR_GATE.md parts 5,
9.5, 9.6, 12.1 to 12.3), including the unseen frame those documents keep for a skill, position, eBR or
pitch-economy part (predictor season 2026, outcome 2027): this gate computes no number of any of those
parts on any frame, only of the two valuations, whose only departure is the ABS part, which no
document calls a skill.

## 5. The statistic

Each consumer's own validation statistic as its gate defines it:

- **F: FA Hard Gate 2** (`fa_backtest.py`, 'HARD GATE 2 market model', `run_market_gate`, artifact
  `data/fa_gate2_eval.json`; registry row `fa_market`, metric 'guarantee/AAV/years MAE (NPV basis),
  forward-chained'): the **guarantee MAE in $M NPV** over the frame of 4.2, read row by row through the
  gate's own `GATE2_COLLECT` hook (`fa_backtest.py:574`). The difference D_F = MAE(incumbent) minus
  MAE(candidate), on identical rows; positive favours the candidate.
- **T: the Trade Machine surplus gate** (`tools/trade_machine_backtest.py`, artifact
  `data/trade_machine_eval.json`; registry row `trade_machine_surplus`, metric 'Rank Spearman ...
  vs realized ... WAR'): the **rank Spearman of `trade_value_mm` against realized WAR** over the frame
  of 4.2, with realized WAR the player's total 2027 WAR on `war_source.DEFAULT_PROVIDER` as the label
  rules then in force provide it, and a player absent from 2027 scored 0 in both arms (Gate 1's
  convention). Career WAR, the gate's original horizon, cannot resolve; the next season is the only
  horizon the frame can carry, disclosed here as the one change. D_T = Spearman(candidate) minus
  Spearman(incumbent), on identical rows; positive favours the candidate.
- **Reported beside, deciding nothing:** AAV and years MAE (F); the useful-asset AUC (T); D_T with
  realized WAR read on `ewar_v3`; each consumer's count of rows whose two arms differ.

## 6. The pass rule

- **Uncertainty.** Per consumer, a paired, player-clustered bootstrap of D, B = 2000, seed 20261022;
  one-sided p = (1 + #{D* <= 0}) / (B + 1).
- **Holm across the two consumers**, m = 2, family alpha 0.05: the smaller p is compared with 0.025;
  only if it clears, the larger with 0.05.
- **Null comparator.** A consumer's D must also exceed the 95th percentile of D over 200 null arms in
  which the 2026 ABS terms are shuffled within side among the player-seasons that carry one (the same
  sizes, no player's own term), re-run through the same chain and frozen with section 3's record.
- **Resolvable.** A consumer is resolvable when at least **30** scored units have inputs that differ
  between the arms. Below 30 it reads **not resolvable** and reports n, D and the counts, no p-value
  and no outcome.
- **PASS for a consumer** = resolvable, D above 0, cleared at its Holm step, and above its null
  comparator. Outcomes: 'passes F and T', 'passes F only', 'passes T only', 'passes neither', each
  with 'not resolvable' where it applies.
- **What a pass licenses.** The build (a later task, queued by the orchestrator) for the consumer that
  passed only: eWAR v3 as a comparison input for that consumer, registered with its own flip. A pass is
  never a copy claim: `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` clause (l) holds, and no page says
  a valuation became more accurate because of a basis change. Whatever the outcome, the registry row
  moves from unvalidated to provisional with the eval artifact linked.
- **Registered expectation** (a prediction, not a measurement): the ABS term is small next to a
  season's WAR and covers one season, so 'passes neither' or 'not resolvable' is the likely outcome.

## 7. The one look

- **Date.** **2027-11-03**, the first day after the 2027 season is final in the label (November 1)
  that is not a registered look day. It moves to the next day that is not a registered look day of any
  `docs/*GATE*.md`, `docs/diamond-betting.md` or the orchestrator's calendar if it becomes one. It is
  after EBR_3 landed and after 2027-01-15, as the task required.
- **Data precondition.** The look stops with 'BLOCKER: date <d>' and computes nothing if any of these
  is missing: the frozen record of section 3; the 2027 class's signings in the FA corpus; a label series
  on `DEFAULT_PROVIDER` that covers the 2027 regular season.
- **Before it.** The scorer (proposed `tools/ewar_v3_valuation_read.py`, by a later task) refuses a
  second run (a one-run sentinel written when scoring begins), refuses any record not in `chain.json`,
  and dry-runs the whole reporting path on fixtures with nulls: a planted candidate whose input carries
  a fixed share of the outcome's deviation reads PASS on both consumers, an arm identical to the
  incumbent never reads PASS, and a shuffled-null arm never reads PASS.
- **The run.** One run. Its stdout and stderr are teed to the output directory before anything else
  runs. Output: `data/ewar_v3_valuation_eval.json` (each consumer's n, D, the bootstrap interval, p,
  the Holm step, the null comparator's percentile, the outcome, the counts and exclusions of 4.2, the
  record's SHA-256), committed with the registry update and a dated section 12 'Results' below.

## 8. Crash protocol

- A crash before scoring begins is fixed and the look runs again the same day.
- A crash after scoring began is never rerun: the scorer stops, the read is VOID, and
  `OWNER_QUESTION.md` in the output directory names what ran and what failed. A VOID look admits
  nothing; a new look needs an owner answer and a new frame (the 2028 class and the 2028 season).
- A precondition found broken after the run makes the look VOID the same way.

## 9. Bans

- **No moves before a pass.** No slot, record, ledger, edge, verdict edge, price, grade, Trade Machine
  value, FA market figure, rational value or betting number moves on eWAR v3 until this look passes,
  and then only for the consumer that passed, through its own build and flip.
- **No early look.** Before the look nobody computes, prints or commits an error, a Spearman or a
  difference of either arm on the frame. Doing so disqualifies the read; the registry row then reads
  'disqualified, early look'.
- **No statistic by consensus-FV cell** (`docs/PROSPECT_ANCHOR_GATE.md`): no realized MLB statistic,
  bust, debut or graduation rate by consensus-FV cell, in this look or its reports.
- **Untouched by this gate and its freeze:** `war_source.DEFAULT_PROVIDER`, the training label, every
  served fitted consumer, the `arb_spine` refusal, `data/ewar.json`, `data/ewar_v3.json`, and every
  `fa_*` and `proj_*` served artifact. No dark betting column is related to anything.

## 10. Registry row

`ewar_v3_valuation_input` in `data/model_registry.json`, rendered in `MODEL_REGISTRY.md`: verdict
`unvalidated` (the verdict enum has no word for registered), `registration_status` **'registered, not
read'**, `eval_artifact` null until the look, and this file named as its gate.

## 11. Read to write this

- `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, the SWAR-Q4 row ('eWAR v3 batch 2').
- `part8/ebr/PLAN.md`, the serving and clock sections ('What moves when it serves', the queue table).
- `docs/ebr-2026-09-30/EBR_GATE.md` parts 6.5, 10, 11, 11.4.6, 11.10 to 11.10.5 and the 12.1 header.
- `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`, the Z1 to Z4 paragraph and clause (l).
- `docs/trade-2026-08-19/TRADE_FORWARD_GATE.md`; `docs/trademachine-2026-10/TRADE_PARTNER_SCREEN_GATE.md`
  (form of this registration).
- Code at `9ead814e`: `war_source.py` (providers, defaults, refused doors); `fa_projection.py`
  (`_side_war_age_maps`, `_war_provider`); `fa_pipeline.py` (the Archive display door);
  `fa_market.py` (`contract_war_path`, `_features_years`, `_features_guar`); `fa_backtest.py`
  (Gate 1, Gate 2, `GATE2_COLLECT`); `proj_eval.py` and `proj_backtest.py` (headers and the default
  provider); `proj_export.py` (`surTotal`); `bayes_trade_value.py` (`apply_platform_surplus`, the
  `career_war_label` reads); `tools/export_trade_values.py`; `tools/trade_machine_backtest.py`
  (statistic and ship rule only); `fa_config.yaml` (target seasons).
- `data/model_registry.json`: the rows `ewar_v3`, `fa_market`, `fa_projection_marcel`,
  `mlb_projections_vets`, `trade_machine_surplus` and `trade_partner_screen` (fields, not results);
  the key lists of `data/trade_machine_eval.json` and `data/fa_gate1_eval.json` and the former's
  'conventions' block.
- Nothing else was read, and no result of any artifact named here was used to choose a rule.
