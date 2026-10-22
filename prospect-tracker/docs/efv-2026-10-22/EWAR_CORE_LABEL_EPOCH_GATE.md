# eWAR core label epoch: eFV's label moves from published fWAR to core eWAR (pre-registration, 2026-10-22)

STATUS: REGISTERED, RESULTS EMPTY. Task EFV_LABEL_EPOCH_EWAR (owner decisions EW3-17, EW3-19 and
EW3-20 with its amendment, 2026-10-15). This document is committed ALONE, before any number of
its estimands is computed: no core label value has been frozen, no guard statistic, no blast
radius figure and no eFV read on the core label exists at this commit. Nothing in this commit
changes a model, an exporter, a flag or a served artifact. Part 11 is filled in afterwards and
nothing above part 11 may be edited once anything is written below it; a change is a dated
amendment under part 11, committed alone. Its pin test is
`test_ewar_core_label_epoch_registration.py`.

- Predecessor of this class: `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` (the fWAR label
  epoch, step Z recorded 2026-10-03). Its clauses (a) to (l) are carried by reference in part 7.
- The series: `docs/ewar/EWAR_HISTORY_GATE.md` (task EWAR_BACKGRADE_HISTORY), which defines
  CORE and FULL and says in part 0 that switching eFV's label to eWAR is this task, under its
  own registration.
- eWAR itself: `docs/ebr-2026-09-30/EBR_GATE.md` amendment 11.10 (the frozen fWAR vintage plus
  the named departures of `data/ewar_v3.json`) and the skill look of part 12.2 (no candidate
  part admitted, 2026-10-19).
- Standard: `docs/EFV_GATE_STANDARD.md` (floors, controls, the 0.02 margin).

## 0. What kind of decision this is

**The label basis is an OWNER BASIS DECISION, and one registered condition stands in front of
it: the circularity guard of part 4.** The owner lifted the 2026-09-11 fWAR label lock in favour
of eWAR (EW3-17). Choosing which WAR the site trains and anchors on is not a claim that the new
series makes eFV, the projections or any priced number more accurate, and no clause here
measures that claim. What is pre-committed is what gets measured, how it is reported, the one
condition the switch must meet first, and what moves when it does.

The condition exists because the new label is a series the site produces itself. Evaluating a
model on a label you also produce is circular (`ewar_map/PLAN.md` T5). So the label is first
checked against targets the site does not produce, next-season published fWAR and next-season
club runs and wins (part 4), and every eFV read on the new label is reported beside the same
read on the incumbent fWAR label (part 6).

## 1. Decision record

1. **EW3-17 (owner, 2026-10-15), verbatim:** "Yeah we can switch the eFV label. We should be able
   to do this by backgrading previous seasons (which we should show in the MLB Stats section, no
   reason to not have stats going back as far as we can with our metrics)". The backgrade
   landed as task EWAR_BACKGRADE_HISTORY (`611e16b4`, eWAR on MLB Stats from 2000).
2. **EW3-19 (owner, 2026-10-15):** a change to the frozen label vintage takes a NEW VINTAGE ID and
   re-fingerprints, and the dependent label reads re-run.
3. **EW3-20 (owner, 2026-10-15), with its amendment:** eWAR is published as two numbers that share
   every measured part: the headline (predictive) eWAR and eWAR realized. "The eFV label is the
   PREDICTIVE (de-noised) core eWAR, with the realized core eWAR read as a registered
   sensitivity; report both."
4. **The task specification** names the label: "the CORE eWAR from EWAR_BACKGRADE_HISTORY,
   era-consistent, frozen as a vintage with its fingerprint".
5. **How this reads beside the history gate.** `EWAR_HISTORY_GATE.md` part 5 says CORE is "never a
   column, a sort key, a label, a driver or a model input". That sentence governs the history
   task and its artifact `data/ewar_history.json`, and the same gate's part 0 hands the label
   switch to this registration. This registration does not read `data/ewar_history.json`: it
   freezes its own label vintage (part 3) with the history gate's CORE formula, and CORE is still
   never displayed, never a column and never a sort key on any served surface.
6. **Owner question recorded, not blocking (EWLE-Q1).** The era-consistent CORE drops two parts
   that published fWAR carries in every eFV label season from 2011: the rest of baserunning
   (UBR and double plays, or FanGraphs' other baserunning runs) and catcher framing. Part 10
   states the options. The default applied is the specification's: CORE.

## 2. The label

For season s, every hitting-group row i and pitching-group row j of the frozen fWAR vintage
(`data/fwar_vintage.json`), with B_i, Fr_i and RPW_fg,s exactly as `EWAR_HISTORY_GATE.md` part 3
defines them under its amendment 9.1 (a part's term enters only in a season whose stamp carries
it):

```
core_i  = war_i - (B_i + Fr_i)              hitter: published fWAR less the re-centred rest of
                                            baserunning and framing, in wins at FanGraphs' own RPW
core_j  = war_j                             pitcher: published fWAR
label(p, s) = core of p's hitting row + core of p's pitching row     (the fwar transform's two-group sum)
```

- **The label is CORE: published fWAR built only from the parts present in every season 2000 to
  2026** (batting, steal runs, fielding, the positional, league and replacement terms, and
  FanGraphs' FIP-based pitching). It is the predictive core: every part the headline eWAR
  carries in every season, and no part the skill look did not admit (part 12.2 of the eBR gate
  admitted none, so the headline eWAR is published fWAR plus the ABS part from 2026, and ABS is
  not present in every season).
- **The realized-core sensitivity** is the label plus the realized pitching departure R2
  (`dr - dh` on the pitching side of `data/ewar_v3.json`, seasons 2016 on). Before 2016 it equals
  the label. It is NOT era-consistent across 2000 to 2026 by construction (R2 exists from 2016),
  and every report says so beside it. It is a sensitivity: it trains nothing and anchors nothing.
- **The transform contract is the fwar transform's.** The label moves values, never the season
  set: a season the frozen vintage does not serve for a player (before 2000, or no feed row)
  keeps the stored value and is recorded as a fallback, exactly as
  `war_source.fwar_seasons_from_incumbent` records it. Values are rounded to 2 decimals like
  the fwar series.
- **Where the label equals fWAR.** Every pitching row; every hitting row in 2000 and 2001 (no
  season stamp carries either part there); and every season in which a player's re-centred
  terms are zero. Busts who never reached MLB carry 0 on every basis.

## 3. The frozen label vintage and the provider

- **The file.** `data/ewar_core_label.json`, written ONCE by `python tools/build_ewar_core_label.py
  --write`. It stores, per season, FanGraphs' RPW and per (mlbam, season) the hitting departure
  `core - war` and the pitching departure R2 (6 decimals), with the frozen fWAR vintage's id and
  sha256, the sha256 of `data/ewar_v3.json` (read for R2 only), the formula version
  (`ewar_core_label_v1`, the history gate's part 3 with amendment 9.1) and a `content_sha256`
  over the departures. Its `vintage_id` is `ewar-core-<fWAR vintage id>-<first 12 hex of
  content_sha256>`.
- **Frozen.** The builder refuses to overwrite a file whose content differs; a new label value
  needs a new vintage id through a dated amendment here (the EW3-19 precedent). It reads only
  the frozen fWAR vintage and `data/ewar_v3.json`, never a feed.
- **Identities checked at build (any miss refuses and nothing is written).** Per row, the
  hitting departure equals `-(B_i + Fr_i)` from `ewar_history.core_full` within 1e-9 wins; per
  season, the departures of the hitting group sum to zero within 1e-6 wins (CORE preserves
  each season's published fWAR total, the history gate's identity 2); every departure in 2000
  and 2001 is zero; the R2 departures equal `data/ewar_v3.json`'s `dr - dh` on the pitching side.
- **Off the webroot.** The file is listed in `deploy/data_exclude.txt`, like the fWAR vintage.
- **The provider.** `war_source` gains provider `ewar_core`, built ON `fwar` the way `ewar_v3` is:
  every door computes the `fwar` answer and adds the label's departures (headline series) or
  the departures plus R2 (realized series). It is servable on request and is NOT the default:
  `war_source.LABEL_EWAR_CORE` defaults to False, and `DEFAULT_PROVIDER` reads `"ewar_core"` only
  when it is True. The flag flips at step D + U of the epoch run (part 8), never in this task.
- **Display doors never see it.** `DISPLAY_PROVIDER` is unchanged. A stored `ewar_core` row keeps
  `seasons_fwar` beside its `seasons`, and `war_source.row_on_provider` re-expresses it on any
  other provider from that kept series, so every display door prints exactly what it prints
  today after the flip.
- **The fingerprint.** `storage.board_basis_fingerprint`'s label term reads
  `ewar_core@<vintage id>` under the new default, in the same commit as the flag (part 8, D + U).
- **Registry.** A row `ewar_core_label` (status provisional, `measurement_only`, eval artifact the
  guard record of part 4), claiming no accuracy.

## 4. The circularity guard (the one condition in front of the flip)

Read ONCE, after the vintage of part 3 is frozen and before any eFV read on the new label. Both
legs read published fWAR and Baseball-Reference stint frames and StatsAPI standings from disk;
nothing is fetched. Seasons: predictor seasons Y in 2011 to 2018 and 2021 to 2024 (every pair
that touches 2020 is excluded, the house rule; 2025 is left out because the 2025 to 2026 pairs
are the eWAR v3 holdout, `c0a1141f`). Seeds and B are fixed here.

### 4.1 G-1, the player leg: next-season published fWAR

- **Pairs.** Hitting-group rows of the vintage with 300 or more plate appearances in Y and in
  Y + 1 and a non-null war in both seasons, keyed (mlbam, Y).
- **Series.** a = the label's hitting value core_i(Y); b = published fWAR war_i(Y). **Target:**
  published fWAR war_i(Y + 1), hitting group.
- **Statistic.** S(x) = the pair-count-weighted mean over predictor seasons of the within-season
  Spearman correlation of x with the target (average ranks for ties). **Gap = S(a) - S(b).**
- **Interval.** Player-clustered bootstrap, B 2,000, seed 20261022: each draw takes players with
  replacement with all their pairs, and both series are re-scored on the same draw. lower = the
  5th percentile of the drawn gaps (one-sided 95), sd = their standard deviation, MDE95 =
  1.645 x sd.
- **Rule. NON-INFERIOR when lower > -0.02.**
- **The permuted twin (the null comparator).** Within each predictor season the label's hitting
  departures are permuted among that season's hitting rows (seasons ascending, rows in
  ascending mlbam, one `numpy.random.default_rng(20261022)`), twin = war + permuted departure,
  scored with the same statistic on the same draws. The twin decides nothing; if it is also
  NON-INFERIOR the record states that G-1 cannot separate the label's change from a random
  change of the same size, beside the verdict.

### 4.2 G-2, the club leg: next-season runs and wins (the eBR gate's team guard 11.2.4, verbatim)

- `tools/swar_targets.team_guard` and `roster_matrix`, unchanged: each player's value in Y per
  unit of exposure (PA, or innings from the vintage's outs) is placed on his club-seasons of Y +
  1 by his Y + 1 exposure there (Baseball-Reference stint frames, last-good cache), and summed
  per club-season.
- **Series.** frame = published fWAR on both sides; part = the label on the hitting side and fWAR
  on the pitching side (they are equal there); ref = bWAR, reported beside.
- **Outcomes carried.** runs scored (hitting sum), runs allowed (hitting sum, sign reversed, since
  framing is run prevention), run differential (total) and wins (total), StatsAPI standings of
  Y + 1.
- **Interval and rule, as registered in 11.2.4.** dT = r(part sum, outcome) - r(frame sum,
  outcome); a player-clustered and a franchise-clustered bootstrap, B 2,000 each, seed 20261024;
  **NON-INFERIOR when dT - 1.645 sd > -0.02 under both bootstraps for every carried outcome.** A
  half-width above 0.02 is recorded as underpowered and is not NON-INFERIOR.

### 4.3 Secondary legs (descriptive: each decides nothing)

1. G-1 on the rate (war per 600 PA in Y against war per 600 PA in Y + 1).
2. G-1 at a 200 PA floor in both seasons.
3. The realized-core sensitivity on pitchers: pitching rows with 50 or more innings in Y and Y +
   1, Y in 2016 to 2018 and 2021 to 2024; gap of (war + R2)(Y) against war(Y) at ranking
   pitching war(Y + 1), same statistic, draws and seed.
4. G-1 restricted to pairs whose Y row carries an absolute framing term above 0.05 runs (the
   rows CORE changes most), with its n.

### 4.4 The decision

- **THE GUARD HOLDS when G-1 and G-2 are both NON-INFERIOR.** The flip is then cleared and runs
  at the epoch run of part 8.
- **Otherwise the flip does not happen.** Nothing moves; the owner is asked EWLE-Q2 (part 10)
  with the numbers, and no default is taken.
- **Before the look:** the whole reporting path is dry-run on fixtures with nulls, including a
  planted series whose gap is known (an identity series must read gap 0 and NON-INFERIOR; a
  series of pure noise must read not NON-INFERIOR), in `test_ewar_core_label_guard.py`. The
  look's stdout and stderr are teed to the task's output directory before anything else runs.
  On any exception after scoring began: STOP, no re-run, `OWNER_QUESTION.md`.
- **The record.** `docs/efv-2026-10-22/ewar_core_label_guard.json` (tracked, not served),
  produced by `python tools/ewar_core_label_guard.py --look`, pinned by a result test.

## 5. The label-only blast radius (descriptive, before any fit)

Measured once after the vintage is frozen, on labels alone: no grade, no consensus FV, no
model output and no FV cell is read. Rows: the list-vintage frame's development vintages 2011 to
2019 (`efv_vintage_frame.DEV_VINTAGES`), both sides, with labels from `efv_labels.labels_for_frame`
on the stored fWAR table and on that table re-expressed on the label (and on the realized core).
Per side and label (W3, L6): resolved rows, Pearson r between the two labels, mean and standard
deviation of the change, rows moving 0.5 WAR or more and 1 WAR or more, and W3 contributor flags
that change at the development threshold w* 1.19. The reserved vintages 2020 and 2021 and the
2025 and later debut cohorts are never read (the labels module's guards stand). Recorded in part
11 beside the guard.

## 6. The reads re-run on the new label (at the epoch run, after step F)

Each is run on the core label (primary), on the realized-core sensitivity, and on the incumbent
fWAR label (the cross-label disclosure part 0 requires), with each tool's own registered
statistic, frames, B and seeds unchanged. Development rows adjudicate NOTHING: the development
frames are spent and no row is a claim.

| Read | Tool | What it writes |
| --- | --- | --- |
| R1 eFV v2 development reads (H0 and the DS-16 assembled read) | `tools/efv_v2_dev_read.py` and `--ds16` | `data/efv_v2_dev_eval.json`, a block per label |
| R2 eFV v5 combined, development read | the `efv5_combined` development read as registered in `docs/efv-v2/EFV_V5_COMBINED.md` | its eval block, a block per label |
| R3 the progress record | `efv_progress` development rows | `data/efv_progress.json`, rows stamped with the label's fingerprint term |
| R4 the 2026 holdout | `efv_2026_holdout` | CORROBORATION ONLY: the frame is spent (`EFV_2026_HOLDOUT_RESULTS.md`); the read on the core label is recorded and adjudicates nothing |
| R5 every in-flight eFV read | its own tool | a registered eFV read whose look has not run on this commit's date reads the label in force on its look date and records the label's fingerprint term; one that froze its label in a frame file keeps it |

## 7. The clauses carried from the fWAR label epoch

Clauses (a) to (l) of `FWAR_LABEL_EPOCH_GATE.md` parts 4.2 and 5 bind this epoch, read through one
substitution: "the incumbent label" is published fWAR from the frozen vintage
2026-10-02-a020cf64844a and "the new label" is the core eWAR label of part 3. In particular:
(a) same-label margins only, floors first, both sides; (b) the cross-label matrix; (d) the TOST
at 0.02 on the swap's effect, E_cond primary; (f) the blast radius against the step A snapshot,
measured and published; (h) the stop clauses; (j) no dark betting column is related to any
outcome or price, and betting reads no WAR; (k) the driver re-test is its own registration; and
**(l) copy may never claim an accuracy gain from a basis change**, absolute: no string anywhere
may say the core eWAR label makes eFV, the projections, WAG, the arbitration model, a farm grade,
a surplus dollar figure or a board rank more accurate. Movement is not accuracy.

**The one factor.** The basis is the only factor of this epoch (clause (i) has one arm, the
swap itself). `RESOLVED_THROUGH` stays 2026. No label-definition arm, no feature arm, no blend
lambda move, no correction family and no eWAR part rides it.

**The added disclosure.** Wherever copy names eFV's label after the flip, it says the label is
the site's own era-consistent eWAR, published fWAR less the rest of baserunning and framing,
and that eFV is also read on published fWAR beside it.

## 8. The epoch run: where it runs, and the rebuild

**It runs in the main tree, with every lane stopped, as task EWAR_CORE_EPOCH_RUN.** The lane
worktrees share the main tree's `.cache` through a junction, and the rebuild deletes and rewrites
label-dependent caches there (`fa_corpus.pkl`, `fa_fits_*`, `proj_ml_frame_*`); `prospects.db` in
a worktree is a copy. The fWAR epoch's 17:43 stop (its part 9) is the measured cost of running a
rebuild beside another writer. This task builds, guards and measures; it does not flip.

The steps are the fWAR epoch's part 7 with these specifics (the letters name artifacts, and the
execution order of the last block is X, T, V, W):

| Step | What | Specifics |
| --- | --- | --- |
| A | snapshot | destination `../_pre_epoch_ewar_core_2026-10/`, refused if it exists; also the frozen fWAR vintage, `data/ewar_core_label.json` and the guard record |
| C | rebase `career_war` | `tools/rebase_career_war.py --provider ewar_core`, dry run first, then apply; the stored fWAR series stays reconstructible (`seasons_fwar`) |
| D + U | ONE commit | `LABEL_EWAR_CORE = True`; `storage.BOARD_RANK_BASIS_EPOCH` bumped; the label term `fwar@<id>` to `ewar_core@<id>` and `BOARD_BASIS_FINGERPRINT` restamped; every code site that names `"fwar"` as the training label moved or deliberately kept (the census below); the corpus `war_provider` follows |
| E | caches | delete `fa_corpus.pkl`, `fa_fits_*`, `proj_ml_frame_*`; keep `.cache/war_daily` |
| F | `efv_dataset.py` and `efv_model.py`, both sides | matrices on the core label; E0 and E star arm matrices |
| G | floors | `efv_mde_lab.py mde 2000`, `efv_power_lab.py all 2000` THEN `partb` |
| H | the epoch lab | a copy of `tools/efv_fwar_label_epoch_lab.py` with the substitution of part 7; the cross-label matrix and the TOST |
| I, J | the pooled outcome curve; `value_framework.py --fit`, then re-apply the sub-45 knots, capture `prospx_current`, sync `FV_WAR_ANCHORS` | the epoch's own rebuild of the anchors, as at the fWAR epoch's steps I and J |
| K, N | the draft slot curve; star odds | on the label |
| M | `tools/train_proj_models.py --final` | corpus on the label; the four pins move together |
| O to S | rebuild passes, `efv_export.py --all --eval`, `source_backtest.py`, `export_trade_values.py`, the step S exporters | the arbitration spine keeps its provider (part 9) |
| X, T, V, W | copy sweep and `copy_lint --check`; `build_site.py`; the eFV golden; registry rows and `tools/gen_audit_docs.py` | the `fwar` row demoted to the incumbent comparison label |
| Z | the reads of part 6, then the step Z entry in part 11 | |

**The D + U code-site census (read 2026-10-22, before any number).** These modules compare a
provider or a stored row's source to the literal `"fwar"` and must each be moved to the label or
kept on fWAR deliberately in the D + U commit, named in its message: `awards_export.py`,
`baserunning_export.py`, `efv_x3_pooled.py`, `fwar_vintage.py`, `source_backtest.py`, `storage.py`,
`war_source.py`, and under `tools/`: `ba_grade_consensus_lab.py`, `ba_stale_vote_lab.py`,
`dpw_path_gate.py`, `efv_beat_pooled_power.py`, `efv_beat_tilted_labels.py`,
`efv_pitch_rate_admission.py`, `efv_screen_lab.py`, `efv_tool_admission.py`, `efv_v2_dev_read.py`,
`efv_v2_driver_diag.py`, `efv_vm3_frame_read.py`, `fit_draft_slot_curve.py`,
`proj_component_stack.py`, `proj_shape_gate.py`, `prospect_anchor_gate.py`, `rebase_career_war.py`
and `swar_lab.py`. A registered gate tool whose own document names fWAR as its label (for
example `prospect_anchor_gate.py`, `proj_shape_gate.py`, `swar_lab.py`) keeps fWAR: its registration
froze it.

## 9. The fitted consumers, and the re-read each one moves through

| Consumer | What moves at the epoch run | Its re-read |
| --- | --- | --- |
| eFV labels, `xfv_war_6yr`, `realized_war_6yr` | the training label and the resolved label | steps F, G and H; the reads of part 6 |
| WAG (PROSPX boom and bust, farm roll-up, Talent Translation) | observed WAR and the fitted expectations it is read against | steps I and J; the WAG baseline refit (the fWAR epoch's Z2) reads the label in force |
| Surplus, trade values, debuted value | the anchors and the $ per WAR read through them | step J, then `export_trade_values.py`; the eWAR v3 valuation input test (`docs/ewar-v3/EWAR_V3_VALUATION_GATE.md`, look 2027-11-03) is a different question (eWAR v3 as the WAR input of FA Hard Gate 2 and the Trade Machine) and is untouched |
| MLB Projections, Team Outlook, FA projections, Franchise and F-SCORE outlook | the training corpus and everything priced off it | step M, then the rebuild passes and step S |
| Arbitration | nothing at this epoch | its WAR spine keeps its provider until the arbitration model's own registered re-read admits the label; recorded, not moved |
| Star odds, the draft slot curve | the star label and the slot curve's WAR | steps N and K |
| HoF | nothing | stays on bWAR (its careers reach before 2000) |
| Awards, season recaps, every display door | nothing | they show the displayed eWAR and eWAR realized, not the label |

## 10. Owner questions

**EWLE-Q1 (recorded, not blocking; the default is applied).** Which eWAR is eFV's label?
- (a) CORE, era-consistent from 2000 (the default, the specification's): published fWAR less the
  rest of baserunning and framing; changes hitters only.
- (b) The headline eWAR in the label's own seasons: published fWAR plus the ABS part from 2026;
  keeps framing and baserunning, and is era-consistent across the label seasons 2011 to 2026
  except for ABS, which did not exist before 2026.
- (c) Keep published fWAR until a part enters eWAR through the skill look; eWAR and fWAR are then
  the same label in every season but 2026.

**EWLE-Q2 (asked only if the guard of part 4 does not hold; blocking, no default).** The core
label failed the circularity guard. Options: (a) keep the fWAR label (no flip); (b) switch to the
headline eWAR of EWLE-Q1 (b) after its own guard read; (c) switch to CORE anyway as an owner basis
decision, with the failed guard disclosed in the label's copy.

## 11. Results

**EMPTY AT REGISTRATION.**

No label value, guard statistic, twin, secondary leg, blast-radius number or eFV read on the core
label has been computed at this commit. The first entry here is dated, names the commit that
produced it, and states what was met when it ran. Clause (l) binds this part.

### 2026-10-22: the circularity guard does NOT hold; the label stays published fWAR

This entry records the one read of part 4 and the label-only blast radius of part 5. Clause (l)
binds it: it reports what was measured and draws no conclusion about eFV's accuracy.

**What ran, and on what.** `python -u tools/ewar_core_label_guard.py --look`, once, at HEAD
`bcd329c3` (2026-10-22 04:58 to 04:59 UTC), rc 0, after the fixture dry run passed
(`test_ewar_core_label_guard.py`, 7 passed: the identity series held with gap 0 and a planted
noise series did not hold). Inputs: the frozen label vintage
`ewar-core-2026-10-02-a020cf64844a-9f947d8f87ac` (frozen at `07c0709c`, file sha256
`295fb428fa5e4d90a3af42b7c06b6e0531e008331ea5840ef935779b7350eb57`) on the frozen fWAR vintage
`2026-10-02-a020cf64844a`; the Baseball-Reference stint caches (bat sha256 `e9571c42...`, pit
`3279bfbd...`); StatsAPI standings of 2012 to 2019 and 2022 to 2025, 30 clubs each. The record is
`docs/efv-2026-10-22/ewar_core_label_guard.json` (sha256
`2ed7b427aafe945b646c79e1c9c55ff002573249f8bfc80c9aab6d766d8cb6e6`; as written by the look it was
`17c54efcaca5c24d9b39bbc497a9b57075b9f716fbb7d5b354e78ea55f1f4750`, and the one change since is a
top-level `generated_at` equal to its own `run.finished_at`, 2026-10-22T04:59:19+00:00, which the
registry's freshness test requires; no measured field changed); stdout and stderr were teed to the
task's output directory before anything else ran.

**G-1, the player leg: not NON-INFERIOR.** 2,416 hitter pairs (713 players, 12 predictor seasons,
every pair carrying a departure). Pair-weighted within-season Spearman with next-season published
fWAR: core label 0.4504, published fWAR 0.4788. Gap -0.0285, 5th percentile -0.0386, 95th
percentile -0.0188, sd 0.0059, MDE95 0.0097 (B 2,000, seed 20261022). The rule needs the 5th
percentile above -0.02; it is below it, and the whole one-sided interval sits under zero.

**The permuted twin.** The same departures permuted within season read gap -0.0055 (5th
percentile -0.0099), NON-INFERIOR. So a random change of the same size costs about a fifth of
what the core's change costs: the parts CORE removes carry next-season signal that a change of
their size does not. (The look's last log line printed the part 4.1 twin disclosure because the
twin was NON-INFERIOR; that sentence is written for the case where G-1 itself passes, and it does
not apply here. The record's fields are as above; the tool's wording is corrected in the commit
that carries this entry.)

**G-2, the club leg (11.2.4 verbatim): not NON-INFERIOR.** 360 club-seasons, 30 franchises, B
2,000 each, seed 20261024; no leg underpowered (every half-width at or under 0.02).

| Outcome (Y + 1) | r fWAR | r core | dT | lower, players | lower, franchises | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| runs scored (hitting sum) | 0.4524 | 0.4545 | +0.0021 | -0.0124 | -0.0128 | NON-INFERIOR |
| runs allowed (hitting sum, reversed) | 0.5250 | 0.4929 | -0.0321 | -0.0450 | -0.0441 | not |
| run differential (total) | 0.7312 | 0.7167 | -0.0144 | -0.0239 | -0.0210 | not |
| wins (total) | 0.7146 | 0.6981 | -0.0165 | -0.0260 | -0.0230 | not |

bWAR's r, reported beside: 0.4395, 0.4540, 0.6774 and 0.6592.

**THE GUARD DOES NOT HOLD (part 4.4).** The flip does not happen: `war_source.LABEL_EWAR_CORE`
stays False, `DEFAULT_PROVIDER` stays `"fwar"`, no epoch run is armed, and nothing served moves.
EWLE-Q2 (part 10) goes to the owner with these numbers; no default is taken.

**Secondary legs (part 4.3; each decides nothing).**

| Leg | n | S label | S fWAR | gap | 5th pct |
| --- | --- | --- | --- | --- | --- |
| G-1 on the rate (per 600 PA) | 2,416 | 0.4104 | 0.4460 | -0.0356 | -0.0481 |
| G-1 at a 200 PA floor | 3,217 | 0.4395 | 0.4650 | -0.0255 | -0.0340 |
| realized-core sensitivity, pitchers 50+ IP (Y 2016 to 2018, 2021 to 2024) | 1,536 | 0.3430 | 0.4505 | -0.1075 | -0.1311 |
| G-1 on pairs with a framing term above 0.05 runs | 254 | 0.3192 | 0.4853 | -0.1661 | -0.2467 |

The pitcher leg's target is published fWAR, whose pitching is FIP-based, so a runs-allowed
departure is measured against a FIP-built target there; it is reported, not read.

**The label-only blast radius (part 5).** `python tools/ewar_core_label_blast.py --write`, once,
record `docs/efv-2026-10-22/ewar_core_label_blast.json` (sha256
`e3adb3837d5c9c1a48307d1c247d0f7bdc3e5fa4142c8a843f193267976f5686`). Development vintages 2011 to
2019, labels only.

| Side, label | rows | r with fWAR label | mean change | sd change | move 0.5+ | move 1.0+ | W3 contributor flags changed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hitters W3 | 3,053 | 0.9895 | -0.030 | 0.321 | 199 | 60 | 56 |
| hitters L6 | 2,963 | 0.9932 | -0.054 | 0.560 | 391 | 170 | |
| pitchers W3 | 2,909 | 1.0000 | +0.001 | 0.008 | 0 | 0 | 0 |
| pitchers L6 | 2,829 | 1.0000 | +0.002 | 0.017 | 1 | 0 | |

The realized-core sensitivity moves pitchers (W3: r 0.9442, sd 0.551, 232 rows move 1 WAR or
more; L6: r 0.9677, sd 0.903, 454 rows) and leaves hitters as the core label does. Pitchers'
core values move at all only through their own batting lines, which carry departures before
2022. The fWAR label's sd is 2.19 (hitters W3) and 4.75 (hitters L6). Movement is not
accuracy.

**Not run, because the flip did not happen:** the reads of part 6 (R1 to R5), the epoch run of
part 8 and every consumer move of part 9. The circularity guard is the condition in front of
them, and part 4.4 stops there.
