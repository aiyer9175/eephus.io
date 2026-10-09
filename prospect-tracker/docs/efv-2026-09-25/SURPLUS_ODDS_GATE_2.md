# Pre-registration 2: price the eFV surplus fan from the served odds, on a new frame

REGISTERED 2026-10-08, BEFORE any number on the frame below exists. This document is
committed alone. The scorer, its tests and the dry run land in later commits, and the one
read runs after them, on the look date of section 7. Where this document and the later
read disagree, the read is what this gate uses, and the disagreement is recorded in
section 10 rather than edited away.

Why a second registration. The one read of `SURPLUS_ODDS_GATE.md` (read `27ee25f9`, FAIL
on G2) is VOID: owner answer VAL3-Q3 (b), 2026-09-30, "Void and re-register on another
frame: the read is declared VOID in the gate doc and registry; a new registration names a
different admissible frame or reports that none exists". The reason is a frame
substitution (that document's section 10). This document names a different frame and
keeps everything else of the first gate that the frame does not force to change.

## 0. Honesty clause and what was read to write this

Nothing was scored to write this document. No row of the new frame was opened, counted,
priced or scored, no realized surplus was computed, no PIT was taken and no model was
fit. Exactly these were read:

- Code, for what it does: `surplus_odds_gate.py` (the void read's scorer, whole);
  `efv_score.py` (`run` from line 1837, `run_backgrade` from line 3127, `scored_path`,
  `_grade_map_age`, the flag at line 1501); `efv_dataset.py` (`RESOLVED_THROUGH`,
  `DEBUT_YEARS`, `MILB_FLOOR_DEFAULT`, `_milb_features`, the bust and rerouted-bust row
  builders); `efv_model.py` (`SCORED_YEARS`, `_decision_year`); `efv_reliability.py`
  (`CHAIN_YEARS`, `MIN_TRAIN`, `MIN_TEST`, `_oof_rows`); `efv_odds_calibration.py` (module
  docstring, `_PLATT`); `efv_vintage_frame.py` (module docstring, `RESERVED_LV`,
  `R_VM_FIRST_DEBUT_YEAR`, `DEV_VINTAGES`, the two guards); `surplus_backtest_real.py`
  (docstring and constants); `war_source.DEFAULT_PROVIDER`; `model_registry.py`.
- Documents: `SURPLUS_ODDS_GATE.md` (whole); the VAL_3 writer's report; the owner's
  answers in `DECISIONS_FOR_OWNER.md`; `FWAR_LABEL_EPOCH_GATE.md` part 3 (the look
  scheduling note) and the part 9 headings (step Z recorded 2026-10-03);
  `PROSPECT_ANCHOR_GATE.md` section 4.4; a date search over every `docs/**/*GATE*.md`.
- Data: the `surplus_odds_gate` block of `data/surplus_backtest_real.json` (the VOID
  read's own published frame accounting: fold counts, accounting classes, n, scope and
  decision; no row), and `data/model_registry.json` rows.
- NOT opened: `data/xfv_hitter_matrix.json`, `data/xfv_pitcher_matrix.json`,
  `data/xfv_scored.json`, `data/xfv_scored_pitcher.json`, `data/xfv.json`,
  `data/xfv_backgrade.json`, and the `career_war` and `career_stats` tables of
  `prospects.db`.

The only figures below that touch the new frame's universe are the void read's
published `n_train` counts of its 2016 folds (rows with a decision year before 2016, at
that read's matrix build), quoted as an estimate of size, never as a result.

## 1. The question, unchanged

On the three efv_score seams that read the odds at the realized-implied ODDS grade while
the dollars are priced at the DISPLAY grade (`run`, `run_live`, `run_backgrade`), should
the eFV surplus mean, band and fan be drawn from the row's served odds vector (candidate)
instead of from the curve at the display grade (incumbent)? The incumbent and the
candidate are exactly those of `SURPLUS_ODDS_GATE.md` section 2: same display grade G_d,
timing, per-bucket dollar values and served dollar map (`vf.apply_calibration`); the
candidate's weights are the served odds vector, the mixture mean is not re-pinned, and its
fan puts exactly the served P(bust) on the bust atom. The code for both arms exists
(`value_framework.sv_distribution(..., bucket_probs=...)`, `mixture_surplus_usd`,
`efv_score._reprice_surplus_on_display(..., odds=...)`, commit `79a637e3`) and is not
changed by this gate. `efv_score.SURPLUS_FROM_SERVED_ODDS_DEFAULT` stays False until a
pass and the owner's flip.

## 2. The candidate frames, evaluated on paper

The new frame must (i) carry eFV odds (keys with a served odds vector) and resolved
outcomes, (ii) not be reserved, (iii) not be the void read's frame, and (iv) not have been
read to write this document (section 0).

**What exists.** The eFV resolved matrix assigns each row a decision year
(`efv_model._decision_year`): the debut year for a debuted row (`DEBUT_YEARS` = 2011
through 2025, since `RESOLVED_THROUGH` moved to 2026 at the fWAR label epoch), and the
year of the last as-of snapshot plus one for a bust. Busts whose last snapshot is 2024 or
later are `bust_recent` and are dropped from every fit and score pool, so pooled decision
years run from the earliest list year plus one through 2025. `efv_score.run` scores every
pool row in sample and writes its `p_bucket` (the served odds vector of the resolved seam)
to `data/xfv_scored.json` and `data/xfv_scored_pitcher.json`, and `run_backgrade` writes
one for every graduate and bust (`data/xfv_backgrade.json`, the debuted and bust rows of
`data/xfv.json`), so every matrix key carries a served odds vector (criterion (i))
whatever its year.

| decision years | status | admissible |
|---|---|---|
| 2016 to 2019 | the VOID read's frame (forward-chained test years, 1,185 rows scored); spent for this candidate | no, (iii) |
| 2020, 2021 | reach the R-LV list vintages (`efv_vintage_frame.RESERVED_LV`); the void scorer's guard refuses any decision year from 2020 on, because a row's as-of snapshot can be a 2020 or 2021 list read. (The eFV v3 reserved read of 2026-10-08, `1c73c420`, read R-LV once; it stays reserved here.) | no, (ii) |
| 2022 to 2024 | refused by the same guard convention; also, under surplus_backtest_real's rule (`debut + CONTROL_YEARS - 1 <= LAST_FULL_SEASON`, 6 and 2025) no debut after 2020 resolves, so only washed-out busts could be scored, a frame selected by its outcome | no, (ii) and (i) |
| 2025 | the R-VM debut cohorts (`R_VM_FIRST_DEBUT_YEAR`); unresolved | no, (ii) and (i) |
| 2015 and earlier | never read by any surplus-odds read. 2014 and 2015 are test folds of every eFV forward-chained accuracy gate (`efv_model.SCORED_YEARS` starts at 2014) and lie inside the Platt fit frame (decision years 2014 to 2020, `efv_odds_calibration`); earlier years enter those chains as training rows only (`SCORED_YEARS` from 2014, `efv_reliability.CHAIN_YEARS` from 2016). None is reserved. Resolved: every debut is 2015 or earlier | **yes** |

**A join of surplus_backtest_real's realized side to eFV odds through the identity set.**
Mechanically possible: surplus_backtest_real's listings are keyed by `players.player_key`,
the namespace the matrix rows carry, and `efv_identity` resolves the outcome-blind person
id. But a joined player's served odds vector is his matrix row's, at his decision year.
A listing row is pre-debut in a listing year of 2017 to 2019, so a debuted player's
decision year is 2017 or later and a bust's is 2018 or later: every resolved joined row
lands in 2017 to 2019 (the void frame) or in 2020 and later (the reserved convention).
Pricing those players at the listing year instead needs an eFV prediction dated at the
listing, which no seam serves: the v1 seams score at the decision year, the
list-vintage frame (`efv_vintage_frame`, development vintages 2011 to 2019) carries
features and grades only and no odds, and the served V2 rows hand no odds to the
re-price, so on a V2 row the candidate equals the incumbent (the first gate's section
2). Inadmissible.

**A within-vintage split of 2016 to 2019.** Admissible only if the void read's scoring
provably never touched the rows. It priced every test row of its 8 folds (`n_priced`
equals `n_test` in each) and classified every priced row (438 debuted, 747 washed out,
29 censored-active: 1,214). The rows of those years it did not score are the 29
censored-active rows, unresolved by the frame's own rules (any of them that has resolved
since would enter by its outcome), and any pool row `_prep` drops before the folds,
which no frame rule can score either. (The `bust_recent` rows are not in those years:
their last snapshot is 2024 or later, so their decision year is 2025 or later.)
Every other split shares the void read's fold models, players and realized values. No
untouched split exists. Inadmissible.

**Decision.** An admissible frame exists: the eFV resolved matrix, forward-chained, over
the decision years before 2016. No blocker.

## 3. The frame

**Rows.** The eFV resolved matrix pool exactly as `efv_score.run` builds it (both sides;
`bust_recent` rows dropped; `_prep(pool, "target_censored", side)`), scored
FORWARD-CHAINED. Test decision years: every decision year Y in the pool with Y <= 2015,
ascending, per side. A fold runs only where the registered chain floors hold for that
side (`MIN_TRAIN` 60 training rows with `decision_year < Y`, `MIN_TEST` 10 test rows), and
a fold below a floor is recorded with its counts and skipped. Each fold fits the ridge,
its linear output calibration and the consensus OLS anchor on its training rows only.
Each test row is priced as the void scorer's `_side_rows` prices it (that function with
its year list replaced, nothing else): `G_odds = vf.realized_implied_fv(
apply_dispersion_correction(model_war), ...)` at `_grade_map_age(age, 0.0)`, age at
`debut_year or 2020`; odds per the first gate's section 2 with `run`'s provisional guard
(`provisional=not src.get("milb")`); `rank_war = (1 - lam) * cons_war + lam * model_war`
at the pinned `blend_lambda(side)`; G_d the rank-preserving quantile map of `rank_war`
onto the consensus FV distribution of the same (side, test year) fold; dollars at
`eta = 1.0`. No training row of any fold has a decision year of 2016 or later, so no row
or label of the void frame enters this read.

**Realized surplus.** The void scorer's `realized_surplus`, unchanged: surplus_backtest_real's
construction and classes (resolved when `debut + 5 <= 2025`; MLB time without WAR rows
excluded, never zeroed; no MLB time and pro activity in 2024 or later censored and
excluded; no MLB time and none since washed out, realized 0; an MLB season before the
decision year excluded), valued at the live flat $/WAR and discounted at the config rate
to the decision year.

**Guards the scorer asserts.** Every frame row has `decision_year <= 2015` (so none is in
the void frame or reaches 2020); every resolved debut is before 2025 (R-VM);
`efv_vintage_frame.guard_score_request` is called for every test year.

**Size, on paper.** The void read's 2016 folds trained on 268 hitter and 278 pitcher rows
with a decision year before 2016 (its published `n_train`, at that read's matrix build;
the current build, rebuilt at the fWAR label epoch, was not counted). The test rows are
those rows minus the early years that only train, and minus unpriced, unresolved and
excluded rows. The registrant does not know the per-year spread. The UNPOWERED rule of
section 5 stays.

**Properties stated before the read.**

1. MiLB inputs are absent from most of the frame. `_milb_features` walks back from
   `decision_year - 1` to `MILB_FLOOR_DEFAULT` (2014), so no row with a decision year of
   2014 or earlier has MiLB features, a 2015 row has at most its 2014 season, and the
   matrix builders mark such rows `milb_unavailable` (`dec_year <= 2015`). Two
   consequences: the forward-chained models fit on these rows read grades and priors
   without production; and `run`'s provisional guard withholds the Platt map on every
   row without a MiLB line, so on most of this frame the served odds vector is the raw
   curve at the ODDS grade, not the Platt-calibrated curve. The candidate still differs
   from the incumbent there (G_odds is not G_d), and that is the path the served
   `run_backgrade` rows without a MiLB line take, but the Platt-mapped path is exercised
   only on 2015 rows with a 2014 line. This frame therefore tests the mechanism mostly
   on the provisional-guard odds (owner question, section 9).
2. In sample. The Platt constants were fit on decision years 2014 to 2020, so where the
   map applies (2015 rows with a MiLB line) the candidate's bust weight is partly in
   sample on the bust event, which favours the candidate. The v6 dollar map was fit on
   surplus_backtest_real's 2017 to 2019 listing cohorts; a player whose decision year is
   2015 or earlier debuted by 2015 or carries no snapshot after 2014, so he cannot be a
   pre-debut listing of 2017 to 2019, and this frame is out of sample for the dollar map
   (both arms go through it in any case).
3. Label. Since the fWAR label epoch (step Z recorded 2026-10-03) the matrix target and
   `career_war`'s `seasons` are fWAR (`war_source.DEFAULT_PROVIDER = "fwar"`); the v6
   dollar map was fit on the earlier label. Both arms share the realized side and the
   map.
4. The chain's as-of point is the eFV frame's own (debut year for a debuted row, last
   snapshot year plus one for a bust), outcome-dependent by construction; both arms share
   it. The F-SIDE-FIX top-band re-anchor that `efv_score.run` applies is not in the
   frame, as in the void read (its crosswalk is built from the pool's realized WAR).

**PROSPECT_ANCHOR guard and bans.** Every statistic is POOLED over the whole frame.
Nothing is computed, stored or printed by consensus-FV cell or by any FV band, tier or
stratum, and there is no per-side verdict. `backtest.run_backtest`, `_by_tier_metrics`,
`by_fv_tier` and `tools/fit_surplus_calibration.py` are never called. No reserved frame is
read: no decision year from 2020 on (R-LV convention), no debut cohort from 2025 on
(R-VM). No row with a decision year of 2016 to 2019 is read.

## 4. The statistics, unchanged

Per arm, pooled, in served $M, exactly the first gate's section 4: `pred_mm` (the arm's
calibrated mixture mean), bias = mean(realized - pred_mm), OLS slope and intercept of
realized on pred_mm, randomized PIT over N = 4,000 calibrated draws per row (the bust
atom at the served floor f = `vf.apply_calibration(0.0)`: PIT = U * F(f) at or below f,
else F(y-) + U * (F(y) - F(y-))), one U per row shared by both arms, coverage = share of
PIT in [0.10, 0.90] (0.80 nominal), PIT KS statistic (descriptive only). Paired bootstrap,
B = 2,000, resampling PLAYERS, percentile CI95, on `D_cov = |cov_inc - 0.80| - |cov_cand -
0.80|`, `H_bias = |bias_cand| - |bias_inc|` and `H_slope = |slope_cand - 1| - |slope_inc -
1|`. The scorer functions are the void scorer's (`calibration_metrics`,
`randomized_pit`, `paired_bootstrap`, `verdict`, `price_arms`), imported unchanged.

Seed: **20261020** for U and for the bootstrap (new, so no draw repeats the void read's).

## 5. The pass rule: G1 to G4 kept

The frame forces no change to the clauses. All four, else FAIL:

1. **G1 one object (structural).** On every frame row the candidate's fan puts exactly
   the served P(bust) on the bust atom (to 1e-9). A miss is a bug and STOPS the read
   without a verdict.
2. **G2 primary, coverage.** `D_cov > 0` and its CI95 lower bound `> 0`.
3. **G3 do no harm, bias.** The CI95 lower bound of `H_bias` is `<= 0`.
4. **G4 do no harm, slope.** The CI95 lower bound of `H_slope` is `<= 0`.

Stop without a verdict (UNPOWERED) if the frame holds fewer than 200 rows.

## 6. One look, and the crash protocol

**One look.** The read runs once. A second run is refused by the scorer (it refuses when
its block exists). A FAIL, an UNPOWERED or a STOPPED read is final for this frame; the
frame is then spent for this candidate.

**Code, built after this commit and before the read** (each in its own commit): a scorer
module `surplus_odds_gate_2.py` that imports the void scorer's functions unchanged and
replaces only the year list and the guards of section 3; it writes one block,
`surplus_odds_gate_2`, inside `data/surplus_backtest_real.json` (a challenger's read lives
in its parent artifact), never touches the void `surplus_odds_gate` block, refuses a
second run, and refuses before the look date of section 7 or on a look day;
`surplus_backtest_real.CARRIED_BLOCKS` gains the new key; conftest.py mirrors the
new module's output path in the same commit; tests pin the pooled scorer (no `fv` or
`tier` key in its output or block), no `run_backtest`, every frame year `<= 2015`, and the
second-run refusal.

**Crash protocol.**

1. **Dry run first, on fixtures.** Before the look, the full code path runs once on
   synthetic null-bearing fixture rows with persistence off: a row with no birth date, no
   position, no consensus FV, no MiLB line, odds with a zero bust share, a player with no
   `career_war` and no `career_stats`, and a realized value exactly at the served floor.
   It reads no real row and writes nothing. It must finish without an exception.
2. **stdout teed first.** The read runs as `python surplus_odds_gate_2.py 2>&1 | tee
   <log>`, with the log opened before the scorer starts; the log is kept with the
   result.
3. **STOP on any exception after scoring begins.** Scoring begins at the first read of a
   realized outcome (the first `realized_surplus` call). An exception after that point
   ends the look: no fix-and-rerun, the log is the record, section 10 records STOPPED
   with the traceback, and the owner is asked. An exception before it (an import error, a
   guard refusal) is not a look; it is fixed, disclosed in section 10, and the read runs.

## 7. The look date

**2026-10-20** (a Tuesday), after the fWAR label epoch's step Z entry (2026-10-03) plus
14 days (2026-10-17, a Saturday). No `docs/**/*GATE*.md` names 2026-10-20, and it is
none of the orchestrator's look days (2026-10-23, 2026-11-06, 2026-11-13, 2026-11-20,
2026-12-01). If the build is not committed by then, or if a registered look is recorded
for that day by then, the read runs on the first later day that is no registered look
day, and section 10 records the date and why. Never earlier than 2026-10-20.

## 8. What a pass does, and what a fail does

**Pass.** Per the owner's answer of 2026-09-25 (a pass ships), in a task of its own after
the read: flip `SURPLUS_FROM_SERVED_ODDS_DEFAULT` to True, regenerate the eFV scorer
artifacts and every surplus-dependent artifact downstream of them, and publish the blast
radius (rows moved, before and after totals, named examples) in that commit. Scope
default: all three seams, as the first gate's section 6 said (owner question, section 9).
The served GRADE and the served odds never move under this gate.

**Fail, UNPOWERED or STOPPED.** The flag stays False, nothing served moves, the numbers
and the failing clauses go into section 10, the registry row
`efv_surplus_from_served_odds` takes the result, and the owner question list gets it.

## 9. Owner question recorded at registration

SURPLUS-ODDS-2-Q1. The one admissible frame exercises the candidate mostly on the
provisional-guard odds (the raw curve at the odds grade), because rows before 2016 carry
no MiLB line; the Platt-mapped odds appear only on 2015 rows with a 2014 MiLB season. What
should a PASS ship?

- (a) DEFAULT: the flag for all three seams, as the first gate registered; the mechanism
  (draw the fan from the served odds) is the same on both odds paths.
- (b) Only rows whose served odds come through the provisional guard (no MiLB line); the
  Platt-mapped rows keep the incumbent pricing and the "Two bases" note until a frame
  that exercises the map exists. Needs a scoped flag in the build.
- (c) Take no read: withdraw this registration and keep the incumbent pricing and the
  "Two bases" note (nothing moves, the frame stays unspent).

## 10. Results

(Filled in after the one read. Nothing above this line may be edited once results exist.)
