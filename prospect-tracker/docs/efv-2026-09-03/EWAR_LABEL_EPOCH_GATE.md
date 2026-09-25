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
| A1 | service-aligned label window: the debut season is season 1 only if the debut is on or before the 04-15 convention (roughly opening day plus 14, the 172-of-186-day service rule), else the window shifts to dy+1..dy+6 and the debut-season stub WAR is added (audit F03) | `efv_dataset._label_6yr` plus a rebuild of `fv_outcome_curves_pooled.json` on the same label | see the CORRECTED expectation below | see below | YES, the moved rows are identifiable by debut date |
| A2 | neutral imputation for `milb_unavailable` rows: `level_rank`, `n_milb_seasons` and the rate keys imputed at the has-MiLB pool mean (or the two-stage fit), so raw 0 stops being a -0.99 sd input on 39 to 46 percent of the pool (audit F04) | `efv_model._vec` plus the docstring correction | ordering: the `level_rank` raw-scale slope moves 0.154 to 0.209-0.253 WAR per rung, so the AAA-versus-A gap widens from 0.46 to 0.63-0.76 WAR before calibration | same direction, larger block (46.4 percent of the pool is imputed) | YES, the moved rows carry `milb_unavailable` |

### A1 expectation, CORRECTED 2026-09-04 BEFORE any measurement

The cells above originally read "+1.0 WAR on the 55 resolved rows debuting on or after
1 August". That was the expected effect of a DIFFERENT rule: the audit's F03 evidence was
computed on the 1-August tail, while the rule frozen here cuts at the service-year boundary
and therefore moves far more rows. The implementing lane caught the mismatch. The
expectation is corrected here rather than quietly, because a pre-registered expectation
exists to be compared against the result, and a wrong one is worse than none. No arm has
been built and no margin has been read.

Measured read-only 2026-09-04 on the current matrices joined to `career_war`, applying the
shipped censoring treatment to both windows (scratchpad w0/a1_cut_sweep.py):

| cut | hit rows shifted | hit resolved n / mean dLabel | hit resolved -> censored | pit rows shifted | pit resolved n / mean dLabel | pit resolved -> censored |
| --- | --- | --- | --- | --- | --- | --- |
| 04-15 (FROZEN) | 504 of 845 (59.6%) | 129 / +1.047 WAR | 57 | 613 of 983 (62.4%) | 136 / +0.496 WAR | 101 |
| 06-15 | 356 (42.1%) | 79 / +1.048 | 57 | 431 (43.8%) | 89 / +0.539 | 101 |
| 08-01 | 204 (24.1%) | 51 / +1.093 | 38 | 249 (25.3%) | 52 / +0.528 | 59 |
| 09-01 | 90 (10.7%) | 26 / +1.019 | 14 | 113 (11.5%) | 18 / +0.723 | 21 |

**The per-row effect is the same at every cut** (about +1.05 WAR for hitters, +0.5 to +0.7
for pitchers, which is the seventh year of value the shift admits). Only the number of rows
treated and the censoring cost move. So the cut is a question about WHICH ROWS deserve the
treatment, not about effect size, and it must be answered on the estimand.

**Why the 04-15 cut stays.** Clemens's quantity is total team-control WAR and control is
roster-day based, spanning six to seven-plus calendar years precisely because a partial
debut season does not accrue a service year (framework 7.4, 1648-1655). A June debut does
not start service year 1 any more than a September debut does; the 1-August tail is where
the defect is most VISIBLE, not where it begins. Choosing a later cut because it moves fewer
rows would be tuning the estimand to its blast radius.

**An exposure-based cut was considered and rejected on data, not on principle.** Shifting
only when the debut season fell short of the repo's own rookie-eligibility thresholds
(`stats.ROOKIE_AB_THRESHOLD` 130, `ROOKIE_IP_THRESHOLD` 50) is the better question, but
`career_stats` carries no debut-season row for 464 of 845 hitter and 482 of 983 pitcher
debuted rows (55% and 49%), concentrated in exactly the older cohorts whose windows are
resolved. The rule would fall back to "no shift" on the majority of the rows that carry the
evidence, which is worse than a date convention applied uniformly.

**Pre-registered clauses that ride with A1, added with this correction:**

1. **Censoring cost is REPORTED, per side, before the level clause is read**: the count of
   rows moving from resolved to censored (expected 57 hit / 101 pit), the change in the
   pooled extrapolated-label share, and the weight distribution before and after. This is a
   real cost of the fix and it must not surface as a surprise in the margin.
2. **STOP if the extrapolated share moves more than 10 points** on either side. At that
   point the arm is changing the censoring regime more than the estimand, and the honest
   report is that the fix cannot be measured on this frame.
3. The level clause reads the RESOLVED rows (129 hit / 136 pit), because only there is the
   seventh year observed rather than projected. The full-pool number is reported beside it
   and is expected to be smaller, since a shifted recent row gains projection, not WAR.
4. Percentage-of-label figures are NOT a clause: the denominator is near zero on late-debut
   rows and the mean percentage is unstable across cuts (+2.3% to +180% on the same effect).

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
| Healthy-counterfactual routing bug | NOW, display field only | audit F12. `xfv_grade_healthy` is computed through the flagship map while the served grade for a routed row comes from the provisional map, so it renders BELOW the served grade on 192 of 580 rows that carry it. The fix routes the counterfactual on the served grade's own basis. It is outside clause (f)'s blast-radius set (grades, dollars, ranks, WAG, star labels, arb, projections) and the current value is wrong, so it rides now; the 192 displayed numbers move at the next regen |
| Odds key exported | NOW, adds a field, moves nothing | audit F09 step 1, owner decision S-3 of 2026-08-13 |


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
  **PREMISE FALSIFIED 2026-09-04, recorded BEFORE the margins were read.** The hitter
  label is NOT byte-identical. 107 of 1,899 hitter rows move, and the trace is complete:
  every one of the 187 moved player-seasons carries pitching innings, 183 of them under
  10 IP. These are position players mopping up in blowouts. eWAR re-prices those innings
  on FIP, which strips the balls in play that are most of the damage, so the swap credits
  back the run-based penalty: leo_rivas +0.68 WAR for 1.0 IP, matt_mervis +0.60 for 0.7 IP.
  The censored-tail projection then multiplies it, so the label moves up to +1.71 WAR.
  The identity `eWAR = bWAR + delta_pitch/RPW` is doing exactly what it says; the premise
  that "hitters have no pitching" is what was wrong. The abort condition is therefore
  RESTATED: abort if the hitter margin moves past its floor for any reason OTHER than
  position-player pitching, and the lab's `nopp` basis is what separates the two.
  The model's own conservation argument does not cover these rows: the centring is
  IP-weighted per (season, role), so a 1-IP position player contributes nothing to the
  constant and still receives the redistribution.
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

## 7.1 Execution record: what the nightly did before the rebuild wave started

Recorded 2026-09-04, before any margin was read.

The facade default flip (runbook step D) was committed in wave 1 on 2026-09-03. The
nightly `run_monthly` then ran 2026-09-04 13:46 to 15:21 local, BEFORE the rebase (step C).
Its own refetch goes through `war_source.career_war_bulk` on the default provider, so it
wrote 1,817 rows on the eWAR basis and left the other 849 on bWAR, then rebuilt the served
artifacts on that MIXED basis: `xfv.json` 15:08, `timeseries.json` 15:21,
`xfv_hitter_matrix.json` 15:01, `trade_values.json` 15:11, `debuts.json` 15:00,
`source_backtest.json` 14:52. This is the ordering hazard step C names in its own text,
arriving from the other direction than the one it warned about.

Consequences, stated plainly:

- The clause (f) pre-epoch snapshot could no longer be taken from the working tree. It was
  taken anyway at 15:30 (`../_pre_epoch_2026-09/`, database plus 16 artifacts) so the rest
  of the epoch is measurable, and the honest baseline for the board diff is the last
  COMMITTED board (af01ece7, generated 2026-08-14), which also carries three weeks of
  unrelated data change. The blast-radius numbers are reported against that baseline with
  this caveat attached; they are an upper bound on the epoch's own effect, not a clean read.
- The bWAR label survives regardless, which is what clause (b) required: `seasons_bwar`
  is written beside `seasons` on every rebased row, and the lab reads the bWAR label from
  the table itself. Clause (b) is unaffected.
- One genuine piece of luck: `data/_labs/xfv_hitter_matrix__E0.json` was built at 13:48,
  seven minutes before the refetch, so a true pre-nightly hitter label exists on disk and
  is what the 107-row hitter trace above was measured against. (It was written to
  `data/xfv_hitter_matrix__E0.json` and moved, byte for byte, to `data/_labs/` on
  2026-09-24: at data/ depth one it shipped to the webroot, and it holds the label side
  of the fit.)

The rebase was then applied with `--reapply` (the flag step C names for exactly this case)
at 15:30, taking `prospects.db.bak-ewar-2026-09-04` first. Post-state: 2,666 rows, 2,531 on
`ewar_v2` and 135 left on `bbref`, no season carrying neither value, no `ewar_v2` row
missing its `seasons_bwar` frame, 10,893 of 10,983 receipted seasons served by eWAR (99.2
percent, 90 in-window fallbacks). The 135 are the identity floor: no mlbam by any route.

Two smaller findings, recorded so they are not rediscovered:

- **Three slugs are two humans each.** `jose_alvarez`, `kyle_mcpherson` and `tyler_wilson`
  resolve one way through `player_photos` and another through the override files.
  `war_source.mlbam_index` prefers the binding table on purpose and says so. Measured here:
  for all three, the photos identity has ZERO eWAR records across the row's season frame
  while the override identity covers every season, because the career_war row belongs to
  the older major-leaguer and photos points at a younger namesake. Cost is 14 seasons on
  the bWAR fallback, which is the conservative path. The remedy is an identity split of the
  kind `tools/repair_jesus_lopez_collision.py` performs, NOT a precedence flip, which would
  re-point a canonical binding to suit one consumer.
- **Two receipt shapes.** The rebase tool stamps `ewar_coverage` as
  `{n_ewar, n_fallback_pre, n_fallback_post, n_seasons, mlbam, model, artifact_generated_at}`
  on 2,524 rows; the nightly facade stamps `{covered, total, fallback_years}` on 7. Both
  shapes are pinned by their own tests and neither is served, so this is untidy rather than
  wrong. Anything that reads the field must handle both, or the two writers must be
  reconciled in a later pass.

## 8. Registry and artifacts this gate creates

- `data/xfv_ewar_label_epoch_eval.json`: the matrix (b), coverage (c), TOST (d),
  controls (e), blast radius (f). Producer named in the runbook.
- `data/model_registry.json`: the `ewar` row's `consumers` moves off "NONE"; the eFV
  rows carry `label_basis: ewar_v2`; `fa_war_paths_decay` carries the retrain hash.
  Then `python tools/gen_audit_docs.py` (MODEL_REGISTRY.md is generated, never edited).

## 9. Results

Measured 2026-09-04 by `tools/efv_ewar_label_epoch_lab.py`, artifact
`data/xfv_ewar_label_epoch_eval.json`, seed 20260807, B = 2,000 for every leg. Floors were
re-derived on the eWAR frame FIRST (clause a): `data/xfv_mde_floor.json` regenerated
2026-09-04, E_refit MDE95 hit 0.0532, pit 0.0507, block 0.0373.

### The headline, stated as the gate requires

**The WAR basis swap did not improve eFV.** On the hitter side the effect on the decision
quantity is nil; on the pitcher side the point estimate is a small LOSS that does not clear
its own null. The flip ships anyway, because part 0 registered it as an owner basis
decision and not an accuracy claim. What this section governs is the COPY.

### (b) The cross-label matrix, margins (blend rho minus consensus rho)

| side | fit / score | score bWAR | score eWAR |
| --- | --- | --- | --- |
| hit | fit bWAR | +0.01000 | +0.00983 |
| hit | fit eWAR | +0.01023 | **+0.01006** |
| pit | fit bWAR | **+0.00538** | -0.00996 |
| pit | fit eWAR | -0.00008 | **-0.01285** |

Diagonal difference (eWAR same-label minus bWAR same-label): hit **+0.00006**, pit
**-0.01823**. n = 755 hit, 892 pit, identical rows in every cell.

The pitcher off-diagonals are the informative part. Scoring on the eWAR label costs about
0.015 whichever label the model was fitted on, while fitting on eWAR costs about 0.005
whichever label it is scored against. The dominant term is therefore the SCORE label, and
the direction is that the eWAR pitcher label rewards the consensus FV relatively more than
it rewards the ridge. That is the honest cell and it leads.

### (d) TOST at the registered 0.02 margin, E_cond primary

| side | point | E_cond CI95 | E_refit CI95 | disposition |
| --- | --- | --- | --- | --- |
| hit | +0.00006 | [-0.00148, +0.00182] | [-0.00263, +0.00351] | **RULED OUT** (equivalent) |
| pit | -0.01823 | [-0.04747, +0.00962] | [-0.05283, +0.02282] | **UNDECIDED** |

The hitter cell is the tightest result in the epoch: the interval is an order of magnitude
inside the margin. The pitcher cell is undecided exactly as part (d) predicted it would be
for most cells at a 0.02 margin against floors of this size.

### (e) Controls

| side | observed | zero-information twin | permutation band (B=2,000) | p |
| --- | --- | --- | --- | --- |
| hit | +0.00006 | +0.00346 | [-0.01006, +0.01131] | 0.9905 |
| pit | -0.01823 | +0.00253 | [-0.01921, +0.01843] | 0.0635 |

The twin does NOT reproduce the pitcher effect (+0.0025 against an observed -0.0182), so
what the swap does is not merely eWAR's marginal distribution. But the observed value sits
just inside the permutation band and p = 0.0635 does not clear 0.05. Both sides ran 11
forward-chained folds, over the 4-fold rule; the per-fold signs are split (hit 6 positive
to 5 negative, pit 5 to 6), which is what a null looks like and is recorded as such.

### (c) Coverage, label seasons served by eWAR

| side | 2011-2015 | 2016-2019 | 2020-2025 |
| --- | --- | --- | --- |
| hit | 949/957 = 99.2% | 900/912 = 98.7% | 1350/1360 = 99.3% |
| pit | 885/918 = 96.4% | 874/895 = 97.7% | 1580/1593 = 99.2% |

Every band on every side clears the clause's 90 percent line, pitchers included, so the
pre-committed remedy path (read 2014 and 2015 separately) is not needed. This is better
than the registration's second census predicted because that census pooled all debuts
including the no-id players, while these are the matrix rows the folds actually score.

### The position-player pitching artifact, measured

The falsified premise recorded in section 7 costs the decision quantity almost nothing:

| side | rows affected | mean label inflation | max | margin cost |
| --- | --- | --- | --- | --- |
| hit | 90 of 845 | +0.071 WAR | +1.71 WAR | +0.00020 |
| pit | 1 of 983 | +0.390 WAR | +0.39 WAR | -0.00099 |

Across the whole `career_war` table the rule catches 273 seasons on 179 players. So this is
a LABEL-VALUE defect, not a ranking defect: it is two orders of magnitude below any floor
here, and it does not block the epoch. It is still wrong, and it propagates to quantities
this table does not measure, namely the pooled FV outcome curve that prices grades, the WAG
survivor anchors and surplus dollars. Disposition: NOT fixed in this epoch, because
changing the eWAR transform is a model-definition change with its own gate record and would
require rebuilding `ewar.json` and re-rebasing. The `nopp` basis in the lab is the
ready-made measurement for whoever takes that decision.

### (a) The standard's own cells, re-derived on the eWAR frame

`data/xfv_power_eval.json` part B, regenerated 2026-09-04T21:01:59Z against the pre-epoch
build of 2026-08-09T22:12:01Z. E_cond is primary.

| cell | pre point | pre floor | pre verdict | post point | post floor | post verdict |
| --- | --- | --- | --- | --- | --- | --- |
| pooled_rho hit full_pool_km | -0.01859 | 0.0208 | NULL | -0.01639 | 0.0214 | NULL |
| pooled_rho pit full_pool_km | +0.01491 | 0.0207 | NULL | +0.01116 | 0.0197 | NULL |
| pooled_rho hit debuted_km | +0.01121 | 0.0204 | NULL | +0.01045 | 0.0206 | NULL |
| pooled_rho pit debuted_km | +0.00702 | 0.0295 | NULL | **-0.01290** | 0.0251 | NULL |
| headtohead_common | +0.03318 | 0.0322 | RESOLVABLE WIN | +0.03609 | 0.0308 | RESOLVABLE WIN |
| block_rho | +0.00912 | 0.0203 | NULL | +0.00294 | 0.0182 | NULL |

NO VERDICT MOVED. Five cells stay NULL and the head-to-head common set stays a resolvable
win on both estimators, so the epoch changes no published claim. The one material movement
is the pitcher debuted cell flipping sign, +0.00702 to -0.01290, which is the same story the
cross-label matrix tells from the other direction and is still comfortably inside its floor.

A procedural note, recorded because it cost a re-run. Runbook step G said
`python tools/efv_power_lab.py all 2000`, and `all` calls `run_all`, which writes the WHOLE
artifact in one shot and therefore ERASED the part-B blocks including `partb_floors`. That
is precisely the incident the lab's own `merge_artifact` docstring pre-registers against.
The floors above come from a follow-up `partb` run and the runbook has been corrected to
require both commands, in that order.

### A caveat on the pitcher cell, found 2026-09-04 after the measurement

`war_source` reports that 461 of 12,507 covered pitcher-seasons (3.7 percent) now have a
bWAR sum that no longer matches the eWAR artifact built 2026-09-03T12:35:09. The cause is
ordinary: B-Ref revises WAR as park and league adjustments update, the nightly refreshed
`war_daily` at 15:11 today, and the artifact is a fixed snapshot taken the day before. The
facade handles it explicitly, serves the artifact's eWAR and writes a receipt.

It matters here because of WHERE the two label arms come from. The eWAR arm reads the
artifact; the bWAR arm reads `seasons_bwar`, which the rebase preserved from the frame the
row already carried. For those 3.7 percent of pitcher-seasons the two arms are therefore on
slightly different VINTAGES of bWAR, so a sliver of the pitcher diagonal difference is
vintage drift rather than the FIP swap. This does not rescue the pitcher cell, it degrades
it further, and the cell was already UNDECIDED with a negative point estimate. The hitter
cell is untouched: hitter bWAR is not re-priced and its diagonal difference is +0.00006.

NOT remedied by rebuilding `ewar.json`, and the reason is structural rather than lazy: the
frame moves every day, so a rebuild would be stale again tomorrow and would restart the
whole measurement chain for a permanent condition. The fingerprint's `label=` term pins the
artifact's build timestamp, so the served basis names its own vintage. Anyone who wants the
pitcher cell measured without this term must rebuild the artifact and the bWAR frame in the
same pass and re-run the lab immediately after.

### (f) Blast radius, measured

`data/xfv_ewar_label_epoch_blast.json`, the final served artifacts against
`../_pre_epoch_2026-09/`. Read the caveat in section 7.1 first: the nightly rebuilt on a
mixed basis before the snapshot could be taken, so the board baseline here is the last
committed board and carries three weeks of unrelated change. These are an upper bound on
the epoch's own effect.

| quantity | value |
| --- | --- |
| rows compared | 9,502 |
| rows whose rank moved | 8,819 |
| median, p90, max absolute rank delta | 6, 38, 709 |
| rows whose grade moved | 5,573 |
| mean absolute grade delta | 0.19 FV |
| membership change, top 10 / 25 / 100 | **0 / 0 / 0** |
| membership change, top 250 | 2 |
| star-label flag flips | 6 of 2,592 |

The top-10 tripwire in section 7 is SATISFIED: zero change, and zero at top 25 and top 100
as well. So the epoch is a broad, shallow re-rank with a still top of board, which is the
shape a label-basis change should have and the same shape the 2026-08-13 epoch had. The six
star-label flips are pitchers whose FIP-priced seasons cross the 4.0 WAR line in one
direction or the other, which clause (f) named in advance as the mechanism to expect.

One defect in the measurement itself, found and fixed before this table was written: the
first blast run read `star_label_view.json`'s `players` as a dict when it is a LIST, so it
compared the eight top-level metadata keys and reported "2 changed". That looked like a
star-label result and was not one. The lab now keys the list by `player_key` and reports the
star flag flips separately from any-field changes.

### What the copy may and may not say (clause g)

MAY: eWAR v2 is the site WAR by owner basis decision; the eFV label is built on it; the
frame is B-Ref with pitching re-priced on FIP and fielding unchanged pending SDR.
MUST NOT: any claim that the swap made eFV more accurate. On the hitter side the effect is
ruled out as equivalent, and on the pitcher side the point estimate is negative and
undecided. The served three-branch accuracy copy is unchanged in mechanism and re-derives
from the regenerated eval artifacts.
