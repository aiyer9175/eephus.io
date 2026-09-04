# eWAR label epoch: pre-registration (2026-09-03)

STATUS: REGISTERED, RESULTS EMPTY. Written in wave 1 (code and tooling only) before
any matrix, floor, curve, anchor or served number was rebuilt on the new label. The
rebuild is a later wave, gated on the design audit that was running when this file was
committed. Git timestamps the registration; part 9 is filled in afterwards and nothing
above it may be edited once results exist (the EPOCH_2026_PREREGISTRATION.md pattern).

Companion: `docs/efv-2026-09-03/WAR_BASIS_RUNBOOK.md` (the ordered commands).
Standard: `docs/EFV_GATE_STANDARD.md` (floors, controls, estimators, the 0.02 margin).
Last epoch of this class: `docs/efv-2026-08-13/GRADE_BASIS_EPOCH_GATE.md`.

## 0. What kind of decision this is

**The WAR basis flip is an OWNER BASIS DECISION. It ships regardless of margin.**

That sentence is the whole frame. The 2026-08-04 measurements (part 2) did not support
a swap on accuracy grounds and nothing since has changed that. The owner is not
claiming eWAR makes eFV more accurate; the owner is choosing which quantity the site
means by "WAR", and every model that is labelled, anchored or priced in WAR follows
the definition. So this gate has no SHIP / NO_SHIP verdict on the flip itself.

What IS pre-committed is what gets MEASURED, how it is reported, and what the epoch
may and may not carry. A basis decision that skips measurement is how a re-rank gets
published as player movement (2026-07-29) and how a margin gets read against a stale
floor (2026-08-13b). Both are on the record and both are what parts 3 to 5 exist to
prevent.

## 1. Decision record (owner, 2026-09-03, locked)

1. **eWAR v2 everywhere, one epoch.** Served display WAR, eFV labels, WAG, the FV
   outcome curve and survivor anchors, surplus, arbitration, farm grades and the MLB
   projections all move from bWAR to eWAR v2 together. No surface stays on bWAR.
2. **One combined label epoch.** The eWAR label and the design audit's label-definition
   fixes land in the same epoch. Floors are derived ONCE, on the final frame. The
   post-shift driver sweep runs on that frame, not before it.
3. **bWAR remains an INPUT.** eWAR v2 is built on the Baseball-Reference war_daily
   frame (pybaseball, cached at `.cache/war_daily/{bat,pit}.parquet`). What changes is
   the SERVED and LABEL series, not the ingest.
4. **fWAR is not obtainable here** (FanGraphs Cloudflare 403; `ewar.py` header,
   `docs/efv-2026-07-30/DEFENSIVE_SOURCE_PROBE.md`). It is not a fallback and not a
   pending option.

### What eWAR v2 is, stated so the copy cannot overclaim

`ewar.py`: the B-Ref run frame with exactly ONE component replaced. Pitching is
re-priced on FIP (the pitcher's own K / BB / HBP / HR over his own innings, FIP
constant from `fa_projection.build_corpus`), carried to the RA9 scale, park-adjusted
by the row's PPF, and RE-CENTRED per (season, role) so the SP total and the RP total
match B-Ref's. Replacement level is re-derived per season so league eWAR sums to the
platform's replacement-wins target. The fielding blend weight is 0.0 (measured and
removed 2026-08-04). Offense, baserunning, double plays, the positional adjustment and
reliever leverage are B-Ref's, untouched.

Consequences that every comment and every line of copy must state plainly:

- **Position players: eWAR equals bWAR exactly** until the SDR defense drop lands
  (`test_ewar_fielding_blend.py::test_w_zero_reproduces_bwar_exactly` pins w = 0.0 to
  B-Ref fielding). The hitter label does not move in this epoch. A hitter-side margin
  change is therefore a REGEN effect or an audit-fix effect, never an eWAR effect.
- **Pitchers: a within-role redistribution of runs.** The SP pool total and the RP pool
  total are B-Ref's by construction; individual pitchers move.
- **League total preserved per season.** `data/ewar_eval.json` accounting_league_sum:
  2016 target 997.77, bWAR sum 998.06, eWAR sum 997.77 (replacement_scale 0.99969);
  2017 target 999.00, bWAR sum 997.54, eWAR sum 999.00 (scale 1.0017).

## 2. Prior measurements (the record the flip is taken against)

### 2.1 Validity gates, `data/ewar_eval.json` (model ewar_v2, window 2016-2025)

| gate | eWAR | bWAR | reading |
| --- | --- | --- | --- |
| 1: team wins, r, 300 team-seasons | 0.8595 | 0.8803 | LOSS, by construction for any FIP WAR |
| 1: team wins, zero-parameter MAE | 4.306 | 3.787 | LOSS |
| 2: pitcher persistence, RAA/9 self-r, 1,677 pairs, min 50 IP | 0.3617 | 0.1768 | WIN, 2.0x |
| 2: forecast of next-year ACTUAL runs above average | 0.2573 | 0.1768 | WIN |
| 2: season WAR self-r | 0.4722 | 0.3176 | WIN |

Gate 1 rewards DESCRIBING the season that happened; B-Ref prices pitchers on the runs
they allowed, which is most of what decided the games, so a runs-allowed WAR is nearly
fitted to team wins. FIP throws away sequencing and balls in play and must fit worse.
The owner's decision re-registers the team-wins gate FORWARD-ONLY (next-season wins),
where the persistence result says eWAR should lead. That re-registration is a later
wave's document, not this one.

### 2.2 R3a and R3b, verbatim from the `ewar.py` header

> R3a, eFV first-6yr label swap (2026-08-04). Decision quantity is the
> model-versus-consensus MARGIN with BOTH scored on the SAME labels, because
> swapping the label changes what "right" means and absolute rho is therefore
> uninterpretable. DELTA = -0.0011 (hit) and -0.0115 (pit), both NEGATIVE,
> against MDE floors of 0.017 and 0.016. Coverage was not the obstacle: 98.6%
> of hit and 99.1% of pit test-fold rows carry an eWAR label, because the
> scored folds are debut years 2020-2023 and eWAR starts in 2016.
> IMPORTANT, and the reason this is a NO-SHIP rather than a CLOSED question:
> the null is NOT tight enough to exclude a floor-sized effect on the pitching
> side. The lane's own bootstrap held both fitted models FIXED, but the eWAR
> arm refits ridge and OLS on the new label, so model-estimation variance
> belongs in the sampling distribution. Adding it moves pit sd 0.0164 ->
> 0.0210 and the CI90 upper bound to +0.0206, which is ABOVE the 0.016 floor;
> the original single-seed CI90 upper of +0.0147 also sits within Monte Carlo
> error of the floor, and 10 of 40 reseeds put it at or above. So: no evidence
> of benefit, do NOT flip, and do not write down that the hypothesis is
> closed. It is unsupported, which is a weaker and more honest claim.
>
> HIGHER-POWERED RE-TEST, pitching only, owner-authorised and run 2026-08-04.
> It did NOT close the question, and it weakened the headline rather than the
> reverse. Pre-registered design: add the 2019 fold (test n=71, train n=80),
> taking the scored population from 434 to 505 rows, and raise the full-refit
> paired bootstrap from B=400 to B=2000. 2024 was deliberately NOT added
> despite being the larger fold, because a 2024 debut has only 2 of its 6
> label seasons resolved against 6 for 2019.
>   * The base 4-fold arm REPRODUCES exactly, DELTA -0.0115.
>   * On 5 folds DELTA is -0.0001. The "moved the wrong way on pitchers"
>     reading is FOLD-DEPENDENT and should not be quoted as though it were
>     stable.
>   * sd went 0.0210 -> 0.02393, WIDER. The pre-registered prediction was
>     that +16% n would shrink it about 7%; that was wrong because it treated
>     all rows as equally informative. The 2019 fold trains on 80 rows
>     against 151+ for the folds it joins, so it carries more noise than
>     information and the pooled margin over consensus falls from +0.0286 to
>     +0.0104 on the bWAR label too.
>   * CI90 [-0.0469, +0.0311]. The upper bound is still well above the 0.016
>     floor, so a floor-sized effect remains UNEXCLUDED.
> CONSEQUENCE FOR ANY FUTURE ATTEMPT: this cohort cannot be re-sliced into
> enough power. The only fold that would add clean information is one whose
> six label seasons are fully resolved, which means WAITING for debut years to
> mature, not re-partitioning what is already here.
>
> R3b, fa_backtest Gate 1 (2026-08-04). Margin over the Marcel carry-forward
> baseline, both scored on the same labels: -0.0387 WAR on pitchers against a
> pre-registered floor of +0.020, CI95 [-0.0472, -0.0309], negative in all six
> scored targets. THE MECHANISM IS THE INTERESTING PART and it generalises:
> the eWAR pitching label really IS more forecastable (label r 0.5033 ->
> 0.5779, persistence 0.4528 -> 0.5823), but a 5/4/3 carry-forward IS a
> persistence bet, so a more persistent label helps the NAIVE BASELINE more
> than it helps the model. A cleaner label raises the floor before it raises
> the ceiling. Expect this anywhere a model is scored as margin-over-carry.

Two things follow for this epoch. The R3a floors (0.017 / 0.016) were the RETIRED 4-fold
incremental-add row and adjudicate nothing now; the R3a deltas were read on the 2026-08-04
frame and adjudicate nothing now either. Both are history, quoted so the flip is taken with
its eyes open, and neither may be re-cited as a current cell. And R3b says the projection
stack's margin-over-carry gates (fa_backtest Gate 1, `data/fa_gate1_eval.json`) will read
WORSE on the new label for a reason that is not a model defect; the runbook re-reads them
and the registry rows say why.

### 2.3 The bWAR-frame floors this epoch retires for the label question

`EFV_GATE_STANDARD.md` 7.5, rebuilt basis 2026-08-08, E_cond MDE95 one-sided: hit
full_pool_km 0.0206, pit full_pool_km 0.0212, hit debuted_km 0.0209, pit debuted_km
0.0290 (E_refit 0.0296 / 0.0259 / 0.0437 / 0.0423). These belong to bWAR labels and
their frame. **They are not the floors of this gate.** Clause (a) derives new ones
FIRST; until it does, no delta on the new frame may be read at all.

## 3. Frozen clauses

A clause is a measurement obligation, not a ship condition, except where it says STOP.

### (a) Same-label margins only, floors first, both sides

The decision quantity is the eFV-minus-consensus margin with BOTH scored on eWAR
labels. Absolute rho on the new label is reported but adjudicates nothing.

Order of operations, blocking: (1) `efv_dataset` matrices both sides on the rebased
`career_war`; (2) `efv_model` evals both sides; (3) `python tools/efv_mde_lab.py mde 2000`
and `python tools/efv_power_lab.py all 2000` on THAT frame, writing
`data/xfv_mde_floor.json` and `data/xfv_power_eval.json`; (4) only then the deltas.
E_cond is primary, E_refit is reported beside it, same seed convention (20260807) as the
standard. Both sides, all four pre-registered cuts (full_pool_km and debuted_km, hit and
pit), plus the head-to-head common set with the player-clustered estimator.

Pre-committed mechanism (from the sdr-ewar plan W3.4 and the hitter identity above): the
hitter label does not move, so the hitter cells are the REGEN CONTROL for this epoch.
Any hitter margin change larger than its E_cond floor is evidence that something other
than the WAR basis moved and must be traced before the pitcher cells are read.

### (b) The cross-label matrix

Four cells per side, all reported, none suppressed:

| model fitted on | scored on bWAR labels | scored on eWAR labels |
| --- | --- | --- |
| bWAR labels | the retired served frame (parity check) | cross cell |
| eWAR labels | cross cell | the new served frame |

Consensus is scored on each label beside the model in every cell, so every cell is a
MARGIN, not a rho. The diagonal difference (new same-label margin minus old same-label
margin) is the effect of the swap on the margin; the off-diagonal cells say how much of it
is "the model learned the new label" against "the label got easier for everyone". The
honest cell leads in any copy; the matrix is published whole in the eval artifact.

Requirement on the rebase: the bWAR label must remain RECONSTRUCTIBLE after
`career_war` is rebased. The L1 tool (`tools/rebase_career_war_to_ewar.py`) writes
`seasons_bwar` beside the served `seasons` on every rebased row, and `data/ewar.json`
carries `bw` beside `ew` per player-season, so the lab reads the bWAR label from the table
itself; the pre-rebase backup (`prospects.db.bak-ewar-<date>`, sqlite backup API) is the
cross-check, not the only source.

### (c) Coverage clause

Share of LABEL SEASONS (debut year through debut+5, capped at RESOLVED_THROUGH) served
by eWAR against bWAR fallback, by side and by debut cohort band (2011-2015, 2016-2019,
2020-2025), plus the count of debuted players with no mlbam id anywhere. **A pitcher
cohort below 90 percent eWAR coverage is REPORTED with its number, not hidden and not
pooled** (the pitcher-stuff 0.0-delta lesson). Coverage is reported per fold in the eval
artifact and the fold-level figures are what the matrix cells are read against.

Baseline census taken at registration (read-only, 2026-09-03, against the `data/ewar.json`
ON DISK, which is the 2026-08-04 build covering 2016-2026; the L1 rebuild to 2011 is what
lifts the first band):

| debut cohort | label seasons | join eWAR | share | no id | id, no eWAR row |
| --- | --- | --- | --- | --- | --- |
| 2011-2015 | 2,911 | 1,207 | 41.5% | 239 | 1,465 |
| 2016-2019 | 1,875 | 1,834 | 97.8% | 32 | 9 |
| 2020-2025 | 3,347 | 3,328 | 99.4% | 19 | 0 |

Method: `career_war` 2,666 rows; `debuts.json` 2,742 rows, 1,977 carrying `mlbam_id`;
ids completed from `data/sources/mlbam_id_overrides.json` and
`mlbam_id_overrides_busts.json`; 69 debuted players resolve to no id by any route. The
1,465 "id, no eWAR row" seasons in the first band are pre-2016 seasons, which the
`--first 2011` build supplies; the 290 no-id seasons are the identity floor no build
reaches. Pitching source inside the artifact today: 8,969 pitcher-seasons priced on FIP,
28 on B-Ref fallback (cells under `MIN_ROLE_CELL_ROWS` 20).

Second census, same method, same day, against L1's rebuilt artifact (`ewar.json`
generated 2026-09-03T12:35:09, seasons 2011-2026, 22,160 player-seasons, 5,136 players;
pitcher-seasons priced 12,457 on FIP, 35 on B-Ref fallback). `career_war` itself was still
all-bbref (2,666 rows) at this read; the rebase had not been applied:

| debut cohort | label seasons | join eWAR | share | no id | id, no eWAR row |
| --- | --- | --- | --- | --- | --- |
| 2011-2015 | 2,911 | 2,616 | 89.9% | 239 | 56 |
| 2016-2019 | 1,875 | 1,834 | 97.8% | 32 | 9 |
| 2020-2025 | 3,347 | 3,328 | 99.4% | 19 | 0 |
| all | 8,133 | 7,778 | 95.6% | 290 | 65 |

So the 2011 build closes 1,409 of the 1,465 build-limited seasons and the first band lands
at 89.9 percent POOLED across sides, one tenth of a point under the clause's line, with the
gap being the 239 no-id seasons (identity, not the build). Both censuses pool hitters and
pitchers; the per-side split is the lab's to compute (`debuts.json` rows carry no reliable
side flag; `efv_dataset._side_match` is the resolver to reuse).

Pre-committed expectation, restated on the second census: the 2016+ bands clear 90 percent
on any side split. The 2011-2015 band is expected to sit within a point of the line and
its pitcher half may fall under it; if it does, the clause REPORTS the number, the
affected folds (SCORED_YEARS 2014 and 2015) are read separately from the pooled headline,
and the remedy is identity work on the 69 no-id players, never pooling or silence.

### (d) TOST margin on the swap's effect

Delta = 0.02 Spearman (the owner's registered equivalence margin, `EFV_GATE_STANDARD.md`
part 8) applied to the DIFFERENCE between the same-label margin on eWAR labels and the
same-label margin on bWAR labels, per side, E_cond interval. Three dispositions:
interval entirely inside +/- 0.02 is RULED OUT (the swap does not change the accuracy
story); entirely above is a swap GAIN; entirely below is a swap LOSS; otherwise
UNDECIDED. Whatever it says, the flip ships (part 0); the disposition decides the COPY
(clause g), nothing else. Known limit, stated up front: nine of the thirteen standard
cells carry E_cond floors of 0.0203-0.0322, so at 0.02 most cells can only come back
UNDECIDED. That is a fact about the registration, not about eWAR.

### (e) Controls

1. **Zero-information twin.** Take each player-season's eWAR-minus-bWAR delta, permute
   the deltas ACROSS PLAYERS within (season, side), add them back to bWAR, and re-label.
   The twin has eWAR's marginal distribution and none of its information. If the twin's
   same-label margin matches the eWAR cell, there is no result to attribute to FIP.
2. **Permutation null band** for the same quantity (delta of margins), B >= 2,000.
3. **>= 4 independent time splits.** The delta of margins is averaged over the
   forward-chained folds of `efv_model.SCORED_YEARS` and the per-fold signs are
   published; a headline with fewer than 4 folds behind it is not a headline.
4. **Paired bootstrap** resampling both train and test with a refit per draw for the
   E_refit leg, scored rows only for E_cond (the standard, sections 2 and 7).

### (f) Blast radius, MEASURED and published

Captured against a pre-epoch snapshot taken BEFORE any rebuild step runs (runbook step
A). Nothing here is gated; a zero must be explained.

- Board re-rank: rows moved, max and median |rank delta|, p90; membership change at
  top 10 / 25 / 100 / 250 (the 2026-08-13 epoch measured 4,585 of 4,664 moved, top-10
  change 0; that is the scale to compare against).
- Top-100 side mix against `test_board_basis_coherence.PINNED_MIX`
  ({"top10": 0, "top25": 1, "top50": 2, "top100": 6}); re-record only if breached.
- Surplus dollar movement, BOTH channels named separately: the `_odds_grade` channel
  and the `rank_war` quantile channel (`GRADE_BASIS_EPOCH_GATE.md` condition 5).
- WAG label flips per org and per graduate (survivor anchors move with the curve).
- `star_label` flips in `data/star_label_view.json` (Clemens star: >= 2 team-control
  seasons of 4+ WAR; a pitcher whose FIP season crosses 4.0 in either direction flips).
- Arbitration: rows whose WAR spine changes, and the award-model re-read.
- Projections: the four pins (feature schema length, `meta.train_hash`, the ml_config
  gate, the `star_blend` pin) all move or the retrain did not happen.

### (g) Copy contract

The derived three-branch accuracy copy (`assets/glossary.js:618`, `:1301`, `:2653`;
`assets/diamond.js:152`; branches win / tie / lose off the served eval artifacts) is
UNCHANGED IN MECHANISM. Its inputs regenerate; nothing is hand-written. Every "bWAR"
claim on a served surface is replaced by the eWAR frame disclosure: B-Ref run frame,
FIP pitching swap, fielding upgrade pending SDR, position players identical to bWAR
until then. Copy gates that literally assert "bWAR" (`test_claims_freshness.py`,
`test_methodology_freshness.py`, `test_board_basis_coherence.py`, `test_fa_def_pin.py`,
`test_efv_sff_crosswalk.py`, `test_war_rate_plus.py`, `test_projections_smoke.py`,
`test_fa_projection.py`) are updated in the SAME commit as the served string. No copy
may say eWAR is more accurate; the R3a/R3b record and clause (d)'s disposition are the
only accuracy statements available, and the tie frame stands until a cell says
otherwise under Holm.

### (h) Stop clauses

Inside this epoch: **no lambda move** (blend lambda shifts are a banned lane; the 0.70
pin's TOST is RULED OUT), **no correction family** (no affine, no dispersion, no band
fix fitted to make a cell pass), **no feature arm** (the driver re-sweep is a later
program on the finished frame, owner decision 6). The combined label epoch may carry
ONLY the design audit's label-definition fixes, and only those named in Appendix A
BEFORE the rebuild starts. A fix that is not in Appendix A when the first matrix is
built is out of the epoch, full stop. If a cell fails a control, the lane records a
loss ledger and does not proceed to a second specification.

## 4. Coordination obligations (same-commit, or the epoch is partial)

From `war_source.py:33-39` (the trap list), `GRADE_BASIS_EPOCH_GATE.md` conditions 7-9,
and `EPOCH_2026_PREREGISTRATION.md`'s same-commit checklist:

1. `storage.BOARD_RANK_BASIS_EPOCH` ("2026-08-13" today) bumps to the flip date, and
   `storage.BOARD_BASIS_FINGERPRINT` gains a `label=` term naming the served label
   basis and its build identity (a fingerprint only guards what it NAMES; the current
   string has no label term and would report "no change" through the whole epoch).
   The grademap term (`outcome_pooled@6dbe8353f3bb` today) moves when the curve refits.
2. `prospx_current` re-captured INSIDE `with vf.valuation_set("prospx_current")`.
3. Golden restamp (`test_efv_export._GOLDEN_XFV_SHA256`, today
   `687aab4b420f0b550848714deb6b565880b77622b0a9983b2bd40dfe97777c31`, rowcount 9,379)
   from the PRODUCTION `efv_export.py --all` output, never from a post-pytest tree.
4. Shadow constants: `tools/build_star_odds_artifacts.py:27` carries its own
   `_RESOLVED_THROUGH = 2025`; grep for any other shadow of a constant this epoch moves
   before the flip commit.
5. Every margin is re-read AFTER regeneration, against the artifacts the regen wrote.
   A delta read against a stored floor, or a floor read against a stored delta, is the
   2026-08-13b vacuous-re-read defect and is refused.
6. The `career_war` rebase runs on the BOX database too (the table is not tracked by
   git; lineage converges only if both writers apply the same transform). The nightly's
   own `career_war` refetch (`run_monthly.py` step 3d) now routes through
   `war_source.career_war_bulk` on the default provider (L1, pinned by
   `test_career_war_ewar_funnel.py`), so the flip in `war_source` is what keeps the
   nightly from re-bWARing the table. See the runbook.

## 5. Pre-committed interpretations

- Clause (d) RULED OUT on both sides: the accuracy story is unchanged by the basis; the
  tie frame stands; copy discloses the frame and says nothing about accuracy moving.
- Clause (d) UNDECIDED (the expected outcome at these floors): same as above; the cell
  is logged with its interval; no "directional" language anywhere.
- Clause (d) GAIN on pitchers: the copy may say the pitcher label is more persistent
  (gate 2) and that the margin moved by the stated amount with its interval; it may not
  say eWAR is "better" without the gate 1 loss beside it.
- Clause (d) LOSS on pitchers: the flip STILL SHIPS (part 0). The loss is disclosed in
  the eFV glossary entry with its interval, and the R3b mechanism (a cleaner label
  helps the naive baseline first) is the stated explanation only if the cross-label
  matrix supports it; otherwise it is logged as unexplained.
- A hitter cell moving past its floor: the epoch stops until the cause is traced to an
  Appendix A fix or a regen defect. The hitter label did not change; a hitter effect is
  never attributed to eWAR.
- Coverage below 90 percent on a pitcher band after the 2011 build: that band's folds
  are reported separately and excluded from the pooled headline, with the count.

## 6. Appendix A: audit label-definition fixes carried by this epoch

**FROZEN 2026-09-04 on the owner's answer to question 1 of `ARKMETRIC_DESIGN_AUDIT.md`
section 9: BOTH fixes, each as its own matrix arm.** Nothing may be added to this table
now; a fix that is not below is out of the epoch. Each entry: the fix, the file it lands in, the pre-registered
expected effect on each side, and whether it is separable from the eWAR flip in the
cross-label matrix (a fix that is not separable is measured jointly and the copy says so).

The recommendation is TWO entries, and the reason is attribution rather than economy. Every
other audit finding wants its own measurement, and a fix that lands inside this rebuild
without its own arm is a fix whose effect can never be separated from the WAR basis. These
two are separable because each touches a disjoint, identifiable row set: A1 moves only
late-debut rows, A2 moves only rows with no MiLB block. Both are built as their own matrix
arms in the same rebuild (four matrices per side instead of two), so the cross-label matrix
reads the WAR basis, each fix, and their interaction.

| # | fix | lands in | expected hit effect | expected pit effect | separable |
| --- | --- | --- | --- | --- | --- |
| A1 | service-aligned label window: the debut season is season 1 only if the debut is on or before roughly opening day plus 14 days, else the window shifts and the stub WAR is added (audit F03) | `efv_dataset._label_6yr` plus a rebuild of `fv_outcome_curves_pooled.json` on the same label | level only: +1.0 WAR on the 55 resolved rows debuting on or after 1 August, about 1.5 FV at the 50 level; rank equivalent (Spearman between labels 0.9992, rho vs consensus +0.0004) | same shape, smaller: +0.72 WAR on 23 rows debuting on or after 1 September | YES, the moved rows are identifiable by debut date |
| A2 | neutral imputation for `milb_unavailable` rows: `level_rank`, `n_milb_seasons` and the rate keys imputed at the has-MiLB pool mean (or the two-stage fit), so raw 0 stops being a -0.99 sd input on 39 to 46 percent of the pool (audit F04) | `efv_model._vec` plus the docstring correction | ordering: the `level_rank` raw-scale slope moves 0.154 to 0.209-0.253 WAR per rung, so the AAA-versus-A gap widens from 0.46 to 0.63-0.76 WAR before calibration | same direction, larger block (46.4 percent of the pool is imputed) | YES, the moved rows carry `milb_unavailable` |

Both entries inherit clause (a): floors are derived on the final frame AFTER all frozen
fixes are applied, and the hitter regen control in clause (a) is read against the eWAR-only
arm, never against the fixed arm, or the control loses its meaning.

### Arm plan (frozen with the table)

Four matrices per side, built from one code path with two flags, so every arm is the same
build with a named difference:

| arm | label window | milb_unavailable imputation | what it isolates |
| --- | --- | --- | --- |
| E0 | calendar (incumbent) | floor (incumbent) | the eWAR basis alone, and the hitter regen control |
| E1 | service-aligned (A1) | floor | A1 |
| E2 | calendar | neutral (A2) | A2 |
| E3 | service-aligned | neutral | the interaction |

E0 is the arm the cross-label matrix and clause (a) read; E3 is the candidate served frame.
An arm ships only if E3 is non-inferior to E0 on the rank TOST at 0.02 per side AND each
fix's own level clause passes on its own arm. If A1 and A2 disagree in sign on the same
side, neither ships and both are recorded as a loss with the interaction cell published.

### Owner decisions taken 2026-09-04, and where each one lands

Recorded here because three of them touch served numbers and must NOT ride this epoch, or
clause (f)'s blast radius stops being attributable to the WAR basis.

| decision | disposition | lands |
| --- | --- | --- |
| Appendix A: both fixes, separate arms | IN this epoch | the table above |
| C-7: re-apply the level correction at the grade seam from a leave-one-fold-out affine | AFTER, own grade-basis epoch | audit F02; coefficients re-fitted on the finished eWAR frame, elite table to the owner first |
| Abstention grade: decide after the anchor fix | AFTER, sequenced behind audit F01 | audit F19 |
| Age ramp: run the serve-rule gate first | AFTER, measurement lane | audit F11 |
| Statcast lean: restore the 4 FV / 40 rank ceiling, size the coefficient from the interval lower bound | AFTER, own registered change | audit F30 |
| Fabricated FV 35: serve an explicit ungraded state | AFTER, consensus-basis change with its own two-pass rebuild | audit F32 |
| Star odds: measured rates where n >= 30, truncate the served scale at 70 | AFTER, sequenced behind audit F07 | audit F42 and F07 |
| Delta chip computed on displayed values | NOW, display only, no served number | audit F43 |


NOT carried by this epoch, and each for a stated reason: F01 (the `B(fv)` ridge feature) and
F02 (the out-of-fold affine) change the served grade mechanism rather than the label and are
grade-basis epochs of their own; F36 (tool-scale normalization into the matrix) is admissible
in principle but has no measured prior and would spend the rebuild's attribution budget on a
third arm; every consensus-side fix (F10, F14, F16, F32, F34, F35) changes `consensus_fv_raw`,
which is simultaneously eFV's dominant feature and its baseline, so each is its own
consensus-basis change with its own two-pass rebuild.

## 7. Abort conditions (for the rebuild, not the decision)

- ABORT the rebuild if the hitter same-label margin moves past its E_cond floor before
  any Appendix A fix is applied (the hitter label is byte-identical; a move is a defect).
- ABORT if the `career_war` rebase leaves any season of any player with NEITHER an eWAR
  nor a bWAR value (the merge-preserving upsert should make this impossible; assert it).
- ABORT if the post-rescale league eWAR sum for any season in 2011-2015 misses its
  replacement-wins target at all (the rescale makes it exact by construction: every
  2016-2025 season in the eval lands on target, replacement_scale 0.99661 to 1.00181),
  or if the PRE-rescale gap exceeds the 2016-2025 range of |bWAR sum - target|, which
  is 0.24 to 1.99 wins (max 2018). A larger gap means the FIP corpus is thin for that
  season, not that the frame changed.
- ABORT if top-10 board membership changes (the 2026-08-13 tripwire, kept). Not a gate on
  size, a tripwire on the flip doing something other than what part 1 describes.

## 8. Registry and artifacts this gate creates

- `data/xfv_ewar_label_epoch_eval.json`: the matrix (b), coverage (c), TOST (d),
  controls (e), blast radius (f). Producer named in the runbook.
- `data/model_registry.json`: the `ewar` row's `consumers` moves off "NONE"; the eFV
  rows carry `label_basis: ewar_v2`; `fa_war_paths_decay` carries the retrain hash.
  Then `python tools/gen_audit_docs.py` (MODEL_REGISTRY.md is generated, never edited).

## 9. Results

EMPTY. Filled by the rebuild wave, after every step of the runbook has run and after
the margins are re-read from the regenerated artifacts. Nothing above this line changes.
