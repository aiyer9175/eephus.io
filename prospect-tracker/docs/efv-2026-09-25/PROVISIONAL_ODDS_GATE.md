# Pre-registration: price the thin-sample provisional dollar range from its served odds

REGISTERED 2026-10-08, BEFORE any number on the frame below exists. This document is
committed alone (with its registry row). Nothing was read to write it, no number was
computed on any frame, and no served number moves. The capture (step 1), the flag, the
scorer and its tests land in later commits; the one read runs after them and only when
section 7 allows it. Where this document and the later read disagree, the read is what
this gate uses, and the disagreement is recorded in section 11 rather than edited away.

Owner answer (2026-09-30, VAL3-Q2 = (b), recorded in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md` under "Cot's terms, the ETA FanGraphs entry,
VAL_3 follow-ups"): register a separate gate on that lane's own frame, before any read.
Parent: `docs/efv-2026-09-25/SURPLUS_ODDS_GATE.md` (registration `fc90703d`, read
`27ee25f9`, FAIL on G2), whose section 8 named this lane out of scope. This gate copies
the parent's form; it does not reuse the parent's frame, and nothing here touches the
parent's read or its re-registration (task SURPLUS_ODDS_VOID_REREGISTER).

## 0. Honesty clause

Every number below is one of: a count over a served artifact that carries no outcome
(`data/xfv.json`, `data/xfv_ungraded.json`, both generated 2026-10-07, read in the
worktree on 2026-10-08); a size recorded in a committed artifact or manifest
(`data/xfv_thin_pbust_eval.json`, `data/provisional_freeze/*.manifest.json`); a figure in
a committed gate document or commit message (the parent's section 9); arithmetic on those
figures (section 6, stated step by step); or a line of code read for what it does. No
realized surplus was priced, no PIT was taken, no frame row was classified as resolved,
washed out or debuted, and no row of any cohort with outcomes was counted.

## 1. The lane, exactly

**The producer (one code path).** `efv_ungraded.build` (`efv_ungraded.py:683`) scores
every rostered non-MLB player the flagship board does not own (`flagship_owns`,
`efv_ungraded.py:632`: no scout grade, or a consensus point made only by the constant
anchor) and that has usable MiLB production. For each row it prices, at the provisional
grade G:

- the DOLLARS: `vf.expected_surplus_usd(G, ...)` and `vf.sv_distribution(G, ...)`
  (`efv_ungraded.py:735-738`), so the fan's bucket weights are the grade-only curve
  `vf.p_bucket_given_fv(G)`, with age, `eta_years = _LEVEL_ETA[roster level]` (4.0 when the
  level is off the ladder) and `eta_origin` = the build year;
- the ODDS: `thin_sample_p_bust(G, side, statline level)` (`efv_ungraded.py:289`, the
  thin-sample head fitted on cohort seasons 2015-2018) replaces P(bust), and
  `_apply_thin_pbust` (`efv_ungraded.py:314`) rescales the four non-bust buckets so
  `p_bucket` keeps the curve's relative shape and sums to 1.000
  (`efv_ungraded.py:741-754`); `p_bust_basis = "thin_sample_conditional"`.

So on every row of this producer, P(bust) and `p_bucket` are the thin-sample odds while
the fan, `surplus_mm` and the band are the grade-only mixture: two bases on one row. The
dollars are written RAW: the producer never passes them through `vf.apply_calibration`
(the flagship does, `efv_score._cal_mm`, `efv_score.py:1458`), so the raw bust atom is
$0 here (disclosure D3).

**Two served routes, one producer.**

- **R1, the board row.** `efv_score._serve_v2` (`efv_score.py:2488`) replaces a live row
  whose consensus is the last-resort constant (`anchor_constant_only`) by
  `_v2_provisional_entry` (`efv_score.py:2452`), which copies the producer's grade, odds,
  `surplus_mm`, `dist` and band from the PREVIOUS run's `data/xfv_ungraded.json`
  (`_provisional_rows`, `efv_score.py:2524`, one run behind) and stamps
  `grade_basis = "provisional_capped"` in `data/xfv.json`. These are the rows VAL_3 named
  ("routing efv_ungraded").
- **R2, the provisional card.** `data/xfv_ungraded.json` `by_player` rows, read directly
  by PROSPX (`ensureEfvUngraded`, `_buildProvPlayers`) for players with no consensus point
  at all.

**Count today** (served artifacts of 2026-10-07; no outcome in either):

| served rows | rows | with a fan | page rule trips (`efvFanBasisConflict`, `prospx/index.html:38990`) |
|---|---|---|---|
| R1, `data/xfv.json`, `grade_basis` `provisional_capped` (all `kind` active) | 2,686 | 2,686 | 2 (`braulio_cavero` P(bust) 0.679, `drew_brutcher` 0.559) |
| producer, `data/xfv_ungraded.json` `by_player`, all `p_bust_basis` `thin_sample_conditional` | 6,067 | 6,067 | 4 (the two R1 rows, plus `mlbam_835219` 0.642 and `mlbam_814522` 0.613) |

The page rule is the parent's (P(bust) >= .10 with P10, >= .25 with P25, >= .50 with P50
above $1.0M). Rendered 2026-10-08 (worktree, `python -m http.server 9141`, headless
Chromium, 1280 px): both R1 rows print the "Two bases" note; the two R2-only rows print
no dollar fan and no note, because an R2 card renders no eFV fan. So the VISIBLE
conflicts are the 2 that VAL_3 counted (2,684 R1 rows on 2026-09-30, 2 trips), and the
producer object behind them is all 6,067 rows.

**The lane this gate covers** is the producer: every row `efv_ungraded.build` writes, on
both routes. A pass changes the producer, so R1 and R2 move together.

## 2. The incumbent and the candidate

Both arms price the same row at the same provisional grade G, the same position, age,
`eta_years`, `eta_origin` and per-bucket dollar values. They differ in ONE thing, the
mixture weights.

- **Incumbent (served today).** weights = `vf.p_bucket_given_fv(G)`; bucket dollar values
  from `vf._mixture_bucket_values` rescaled so the curve's mixture mean equals
  `vf.expected_surplus_usd(G)`; draws per `vf._sv_draws_mm`; `surplus_mm`, the band and the
  fan are that mean and its percentiles.
- **Candidate (the parent's form, on this lane).** weights = the row's SERVED odds vector,
  the `p_bucket` the card's P(bust) is read from (the thin-sample vector, 3 dp as served,
  divided by its own sum). Per-bucket dollar values are the incumbent's, unchanged; the
  mean is `vf.mixture_surplus_usd(G, ..., bucket_probs=p_bucket)` (`value_framework.py:2331`)
  and the fan is `vf.sv_distribution(G, ..., bucket_probs=p_bucket)`
  (`value_framework.py:2440`); the mean is NOT re-pinned to `expected_surplus_usd`. The
  fan's bust share then equals the served P(bust), which is the point.

Code that already exists: `mixture_surplus_usd` and `sv_distribution(bucket_probs=)` were
built by the parent (`79a637e3`) and are byte-identical to the incumbent when no odds are
passed. Code built after this commit, behind a flag: `efv_ungraded.SURPLUS_FROM_THIN_ODDS_DEFAULT
= False`, env override `EEPHUS_SURPLUS_FROM_THIN_ODDS` ("1"/"0"), read only inside
`efv_ungraded.build`; flag off is byte-identical to today (a test pins it). The flag build
moves no served number.

**One thing this gate does NOT decide: the dollar unit.** Both arms are scored in the
unit the realized side is measured in (section 4: through `efv_score._cal_mm` at G,
pointwise on draws, as the flagship seam prices), because the raw unit is not the
realized unit. Whether the lane should SERVE calibrated dollars is a separate question
(disclosure D3, owner question in section 10). A pass ships the WEIGHTS on whatever unit
the lane serves on the ship day.

## 3. The frame

**What exists, and why none of it is the frame.**

| candidate frame | size, as recorded | status |
|---|---|---|
| thin cohort seasons 2015-2018 (`tools/pbust_thin/`, `data/xfv_thin_pbust_eval.json`) | 19,812 player-seasons (hit 9,762, pit 10,050) | SPENT. The served thin-sample head was fitted on these rows and its gates G1 to G5 read the bust event on every one (leave-one-cohort-year-out). The candidate's bust weight IS that head's output, so a read here is in sample by construction |
| cohort season 2019 | the artifact records only the grade-35-and-over counts (hit 154, pit 186) | SPENT as the same lab's sensitivity read of the bust rate (`sensitivity_2019_censored`), and censored: a 2019 row resolves only at debut + 5 <= H, and a late debut lands in a 2025+ debut cohort |
| cohort seasons 2014 and earlier | none | not buildable: the MiLB feature cache floors at 2014 and the artifact states the earliest usable cohort is 2015 |
| cohort season 2020 | none | no minor-league season |
| cohort season 2021 | not counted | RESERVED: "ungraded as of the season" is defined against the 2021 lists (R-LV, `efv_vintage_frame.RESERVED_LV`) |
| cohort seasons 2022-2025 | not counted | unresolvable (no first-six window can close before H = 2032 for a 2027 debut) and every debut falls in the 2025+ debut cohorts (R-VM) |
| the frozen served vintage `data/provisional_freeze/xfv_ungraded_2026-09-24.json` (`96ae3146`, pinned by `test_provisional_freeze_pin.py`) | 6,076 rows (graded_twin 253, routed 2,480, pure 3,343) | not spent on outcomes (`provisional_track` reads first source grades only, never WAR), 0 resolved rows; but it carries key, mlbam, side, org, level, age, grade, war6 and exposure only: no position, no served odds vector and no fan, so neither arm can be priced from it exactly. Not the frame; used as an identity cross-check |
| `data/xfv.json` as tracked (R1 rows) | 2,686 rows today | carries the served vector and fan for R1 only and no age or level; not the frame alone |

**The frame: F-THIN-2026, a prospective capture.** No resolved provisional frame exists
that is neither reserved nor spent. The frame is therefore the producer's served rows as
they stand on one capture day, frozen BEFORE any 2027 professional game:

- **Step 1, the capture (a later commit, alone).** A copy-only script writes
  `data/provisional_freeze/thin_odds_frame_<capture date>.json` from `data/xfv_ungraded.json`
  as served that day: per row `player_key`, `mlbam_id`, side, position, roster level,
  statline level, age, `eta_years` as priced, `eta_origin`, `xfv_grade`, `p_bucket`,
  `p_bust`, `p_bust_basis`, `surplus_mm`, `dist`, `band_p10_mm`, `band_p90_mm`, and whether
  the key is an R1 row in `data/xfv.json` that day; plus the producer's code commit and the
  artifact's sha256. It reads no outcome and computes nothing. It is pinned by a hash test
  in the same commit, and the capture commit is the frame's identity. **Deadline: committed
  on or before 2027-02-14.** If it is not, this registration lapses before any number and a
  new registration names a new capture.
- **Rows.** Every captured row, intention to treat: a row that a source grades later, or
  that leaves the lane, stays in the frame as captured. Expected size: the producer's row
  count on the capture day (6,067 on 2026-10-07).
- **Reproduction check G0 (structural, at the read).** The incumbent recomputed from the
  captured inputs, with the value framework and its config at the capture commit, must
  reproduce the captured `surplus_mm` and `dist` on every row to their served rounding. A
  miss is a bug and STOPS the read without a verdict.

**Realized surplus.** The parent's construction (from `surplus_backtest_real.py`), with
the decision year = the capture season (2026): `career_war` seasons -> `_impute_seasons`
(`surplus_backtest_real.py:230`) -> `backtest.realized_sv_pv` (`backtest.py:148`)
discounted at the config rate to 2026, production valued at the flat $/WAR
(`vf.dollars_per_war_flat()`), both read from the config at the capture commit, so nothing
changed after the capture moves either arm or the realized unit. The WAR rows are the
training label the database carries on the read day, named in the artifact.

**Resolution, with H = the last full MLB season loaded on the read day** (the parent's
rules from `surplus_backtest_real.build_cohorts`, `surplus_backtest_real.py:258`, with its
`LAST_FULL_SEASON` replaced by H and its `WASHED_BEFORE` by H - 1):

- WAR rows -> resolved when debut + 5 <= H (`CONTROL_YEARS` 6); otherwise UNRESOLVED.
- MLB time with no WAR rows -> excluded (UNRESOLVED), never zeroed.
- no MLB time and professional activity in H - 1 or H -> censored (UNRESOLVED).
- no MLB time and no professional activity in H - 1 or H -> washed out, realized 0,
  resolved.
- a row with an MLB season at or before the capture season is excluded at capture (the
  producer scores no MLB player, so this should be empty; counted if not).

**Reserved frames.** The frame reads no list, so no list vintage 2020 or 2021 (R-LV) is
touched. Every debut in the frame is 2027 or later, inside the "2025+ debut cohorts"
wording. The read refuses while any frame row's debut year sits in a debut cohort still
reserved on the read day (R-VM names the 2025, 2026 and 2027 cohorts and releases them at
its look 3 record, `docs/efv-v2/PROGRAM.md` section 2.4, the RT 2028 run; any later
reservation recorded before the read binds the same way). It refuses rather than drops: a
drop by debut year would condition on the outcome. The scorer asserts both.

**PROSPECT_ANCHOR guard.** Every statistic is POOLED over the whole frame. Nothing is
computed, stored or printed by consensus-FV cell (45, 50, 55, 60, 65+) or by any FV or
provisional-grade band, tier or stratum, and there is no per-side, per-route, per-level or
per-org verdict. `backtest.run_backtest` is NEVER called (it builds `by_fv_tier`,
`backtest.py:761`), nor `tools/fit_surplus_calibration.py`. No calibration is refitted;
both arms go through the capture commit's map unchanged. A test pins that no key of the
scorer's output or of the artifact contains "fv" or "tier" as a stratum.

**Known in-sample positions, stated before the read.** (i) The thin-sample head was fitted
on cohort seasons 2015-2018 and reads its odds out of sample here (a 2026 capture): unlike
the parent, the candidate has NO in-sample advantage. (ii) The dollar map and the flat
$/WAR were fitted on listed (graded) cohorts, a different population; both arms share it.
(iii) The washed-out rule makes most frame rows a $0 bust; most PITs are therefore
`U * F(f)`, so coverage on this lane mostly measures the bust weight, which is the
question asked.

## 4. The statistics (the parent's section 4, on this frame)

Per arm, pooled, in $M through `efv_score._cal_mm` at G (mean, and every draw pointwise):

- `pred_mm`: the arm's calibrated mixture mean, unrounded.
- **bias** = mean(realized - pred_mm). **slope**, intercept: OLS of realized on pred_mm.
- **PIT**, randomized, N = 4,000 draws per row (the arm's calibrated draws, seed per
  `vf._sv_draws_mm`). f = the calibrated bust atom, `efv_score._cal_mm(0.0, G, is_pit)` at
  the capture commit. Realized <= f is the bust event: PIT = U * F(f); otherwise
  PIT = F(y-) + U * (F(y) - F(y-)). U ~ Uniform(0,1), one per row, the SAME U for both arms,
  seed 20261008.
- **coverage** = share of PIT in [0.10, 0.90] (0.80 nominal). **KS** statistic of PIT
  against Uniform(0,1), descriptive only.

Scorer functions reused unchanged: `surplus_odds_gate.randomized_pit`,
`surplus_odds_gate.calibration_metrics` and `surplus_odds_gate.paired_bootstrap`
(`surplus_odds_gate.py:102`, `:126`, `:152`).

Paired bootstrap, B = 2,000, seed 20261008, resampling PLAYERS (one captured row per
player, so a cluster is a row; the code clusters by `player_key` anyway), percentile CI95:

- `D_cov  = |cov_inc - 0.80| - |cov_cand - 0.80|` (positive favours the candidate)
- `H_bias = |bias_cand| - |bias_inc|` (positive is harm)
- `H_slope = |slope_cand - 1| - |slope_inc - 1|` (positive is harm)

## 5. The pass rule

G0 (section 3) first, then all four, else FAIL:

1. **G1 one object (structural).** On every frame row the candidate's fan puts exactly the
   served P(bust) on the bust atom (normalized weight within 1e-6 of the captured
   `p_bust`; the 3-dp served vector sums to 1.000 by `_apply_thin_pbust`). A miss is a bug
   and STOPS the read without a verdict.
2. **G2 primary, coverage.** `D_cov > 0` and its CI95 lower bound `> 0`.
3. **G3 do no harm, bias.** The CI95 lower bound of `H_bias` is `<= 0`.
4. **G4 do no harm, slope.** The CI95 lower bound of `H_slope` is `<= 0`.

Stop without a verdict (UNPOWERED) if, on the read day, section 6's P1 or P2 fails.

## 6. The power precondition

Today the frame has **0 resolved rows**: it does not exist yet (step 1), and no captured
row can resolve before the 2027 season ends. A resolvable read needs both:

- **P1, size: at least 1,317 resolved rows.** From the parent's MDE arithmetic, on its
  published read (n 1,185; `D_cov` CI95 [-0.0295, +0.0000]): SE(D_cov) is about
  0.0295 / (2 x 1.95996) = 0.007526; at one-sided alpha 0.025 (the CI95 lower bound rule)
  and power 0.80 the minimum detectable `D_cov` is (1.95996 + 0.84162) x 0.007526 =
  0.02108 at n 1,185. Holding this gate to resolve a 0.02 coverage gain (two points of the
  80 percent band, the parent's own resolution rounded down) with SE scaling as
  1 / sqrt(n): n_min = 1,185 x (0.02108 / 0.02)^2 = 1,316.9, so **1,317**. A planning
  figure: this frame's PIT is dominated by $0 busts, so its variance will differ from the
  parent's; the rule stands as written.
- **P2, resolution: unresolved share at most 2.5 percent of frame rows** (the parent read's
  own excluded share, 29 of 1,214 = 2.4 percent, rounded up to the half point). Without it
  the resolved rows are mostly early washouts and the read is selected on the outcome.

With about 6,000 captured rows, P1 holds whenever P2 does; **P2 binds**.

**The earliest date the frame could reach it.** A captured row carries 2026 professional
activity (the production its grade read), so the washed-out rule first applies at
H = 2028; no precondition count can pass before the RT 2028 run (about 2028-10-15). A
debuted row resolves at debut + 5, so a 2027 debut resolves at H = 2032 at the earliest.
The thin-sample artifact records that 97.8 percent of eventual DSL and CPX debuts come
within 8 seasons of the cohort season, so the last material debuts from a 2026 capture
land by 2034 and resolve by H = 2039. The look is therefore expected between the RT 2028
count and the RT 2039 count; the count decides, not this forecast.

**The precondition count (not a look).** Once a year, after the RT run and never on a
registered look day, a counting step may write three integers and the H it used: frame
rows, resolved, unresolved. It reads debut status, MLB time and professional activity
only: never a WAR value, a dollar, either arm, or a split of the resolved rows into washed
out and debuted, nor any split by side, route, level, org or grade. Each count is
appended to section 11 as a dated line. A count that reports anything else is a look.

## 7. The one look, and its earliest date

One look, on the LATER of:

- (a) the fWAR label epoch's step Z plus 14 days: step Z is recorded 2026-10-03
  (`docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9), so not before **2026-10-17**;
- (b) the step 1 capture commit, and the flag, scorer and synthetic-row tests committed
  after it;
- (c) the first precondition count at which P1 and P2 both hold (not before the RT 2028
  run, about 2028-10-15);
- (d) the release of every debut cohort a frame row reaches (R-VM look 3 record for 2027).

Never on a registered look day (`docs/*GATE*.md`, `docs/*/*GATE*.md`,
`docs/diamond-betting.md`, checked on the day), never in a session that takes another
gate's look, never while a pipeline, nightly or pytest runs. **Looking early
disqualifies:** any arm statistic on frame rows before (a) to (d) hold spends the frame,
the gate is VOID, and a new registration needs a new capture. The scorer refuses before
its conditions and refuses a second scored look (it may re-print the stored result).

## 8. The crash protocol

Before the look, a full dry run of the scoring and reporting path on synthetic fixtures
with nulls. The look's stdout and stderr are teed to the task directory before anything
else runs. On any exception after scoring began: STOP, do not rerun, record the partial
stdout verbatim in section 11, and write the owner question. A rerun is admissible only on
an owner ruling for a one-line repair of a line that adjudicates nothing, committed alone,
and only if the rerun reproduces every printed clause line byte for byte; otherwise the
look is VOID (the ETA FanGraphs gate's 2026-09-30 precedent).

## 9. What a pass and a fail do

**Pass.** Flip `SURPLUS_FROM_THIN_ODDS_DEFAULT` to True under the landing rules in force on
the read day; regenerate `data/xfv_ungraded.json` first, then `efv_score.run_live` (R1
copies the producer's file as it stands) and every surplus-dependent artifact downstream;
publish the
blast radius (rows moved, before and after totals, named examples) in the commit. The
"Two bases" note then stops tripping on this lane. The grade and the odds never move under
this gate; the candidate reads the odds, it does not change them.

**Fail.** The flag stays False, nothing served moves, the failing clauses and their
numbers go into section 11, and the owner question list gets the result.

**Until the look:** the "Two bases" note stays on these rows, and nothing in this gate
changes the served lane.

## 10. Disclosures and owner questions recorded at registration

- **D1.** The frame is prospective and its read is years away (section 6). No admissible
  retrospective frame exists (section 3).
- **D2.** The candidate changes the dollars on all 6,067 producer rows, not only the 2
  visible conflicts; most rows are org filler whose fan sits on the floor under both arms.
- **D3, the dollar unit.** The producer serves RAW dollars (P10 $0.0 on all 6,067 rows),
  while the flagship V2 rows pass through the served calibration map; the
  `efvFanBasisConflict` threshold ($1.0M) was written for the calibrated unit. This gate
  scores both arms in the calibrated unit and decides only the weights.
  **Owner question (recorded, not answered here):** should the provisional lane serve
  calibrated dollars like the board? (a) DEFAULT: unchanged until a separate task measures
  and lands it; (b) a separate repair task that passes the producer's dollars through
  `efv_score._cal_mm` (moves `surplus_mm`, band and fan on every producer row, not the grade
  or the odds).

## 11. Results

(Filled in after the precondition counts and the one read. Nothing above this line may be
edited once a count or a result exists; an amendment filed before the look may change no
threshold, frame, arm, order or criterion.)

## 12. Read to write this

- the task specification `SURPLUS_ODDS_THIN_LANE_GATE_REG.spec.txt` (2026-10-08) and the
  owner answer VAL3-Q2 in `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`;
- VAL_3's FIX_REPORT (scratchpad `w7/VAL_3_dollar_range_from_odds_gate/FIX_REPORT.txt`),
  sections 1 to 5 and its owner questions;
- `docs/efv-2026-09-25/SURPLUS_ODDS_GATE.md`, whole;
- `efv_ungraded.py` (the thin-sample block above `_LEVEL_ETA`, `thin_sample_p_bust`,
  `_apply_thin_pbust`, `flagship_owns`, `build`);
- `efv_score.py` (`_cal_mm`, `_reprice_surplus_on_display` and its amended-invariant
  docstring, `_v2_entry`, `_v2_provisional_entry`, `_serve_v2`, `_provisional_rows`);
- `value_framework.py` (`_mixture_bucket_values`, `mixture_surplus_usd`, `sv_distribution`,
  `apply_calibration`);
- `surplus_backtest_real.py` (the outcome classes, `build_cohorts`, `_resolved_only`,
  `CONTROL_YEARS`, `LAST_FULL_SEASON`, `WASHED_BEFORE`), `surplus_odds_gate.py` (function
  list), `backtest.py` (`run_backtest`, `by_fv_tier`, `realized_sv_pv`);
- `data/xfv_thin_pbust_eval.json` (population, label, limits, protocol, the recorded 2019
  sensitivity counts) and `tools/pbust_thin/cohort.py` (header);
- `data/provisional_freeze/` (manifest, the 2026-09-24 frozen rows' schema and count),
  `provisional_track.py` (docstring), `test_provisional_freeze_pin.py` (what it pins);
- `docs/efv-v2/PROGRAM.md` section 2.4 (R-LV, R-VM), `efv_vintage_frame.py` (the guards),
  `docs/PROSPECT_ANCHOR_GATE.md` by reference, the step Z entry date in
  `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`;
- `prospx/index.html` (`efvFanBasisConflict`, `efvFanHidden`, the note, the ungraded loader);
- `data/model_registry.json`, `model_registry.py` and the registration rows
  `college_pitk_box_challenger` and `college_translation_career_refit` (row form);
- the crash-protocol wording of `docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md` and
  the ETA gate's 2026-09-30 crash record.

Counted to write this (served artifacts only, no outcome): R1 rows, fans and rule trips in
`data/xfv.json`; producer rows, `p_bust_basis` counts and rule trips in
`data/xfv_ungraded.json`; the 2026-09-24 freeze's row count and fields. Rendered: four
cards, 1280 px, for the note.
