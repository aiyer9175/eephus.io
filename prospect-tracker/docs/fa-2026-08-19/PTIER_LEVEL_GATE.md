# PTIER LEVEL GATE - guarantee bias by predicted tier (2026-08-19)

Owner program 2026-08-19, FA market model lane. Files: fa_market.py,
data/fa_gate2_eval.json, test_fa_ptier_gate.py, this doc. Lab runner:
scratchpad lab_gate2.py (persist=False, persist_dpw=False on every
diagnostic run; data/fa_dpw_series.json is never rewritten in this lane).

Discipline: section 2 was frozen BEFORE the arm or its control ran.
Results are filled with verbatim lab output only. A failed clause is a
loss-record, not a re-frame.

## 1. DIAGNOSIS (no fitting)

The committed Gate-2 artifact carries guarantee bias by PREDICTED tier
(bias_model, $M): lt10 -2.618 / 10to20 -9.115 / 20to50 -16.888 /
ge50 -24.169, mean|bias| 13.198. The E5 frozen record (2026-07-30,
RECAL_MODE "shift" ship) read -2.11 / -6.27 / -15.04 / -3.70, mean|bias|
6.78. Every tier under-priced, worst where the dollars are.

### 1a. Commit-level isolation (artifact archaeology, verbatim extraction)

    commit    date        guar MAE   mega     ptier bias lt10/10to20/20to50/ge50      mean|bias|
    89112f54  2026-07-30  9.6778     77.55    -1.978 / -6.825 / -11.894 / -14.155     8.713
    b21c027a  2026-07-30  9.6778     77.55    (byte-identical to 89112f54)            8.713
    a60678e7  2026-08-03  10.2067    86.065   -2.618 / -9.115 / -16.888 / -24.169     13.198
    cfcba76b  2026-08-04  10.2067    86.065   (numbers byte-identical to a60678e7)    13.198
    HEAD      committed   10.2067    86.065   (unchanged since cfcba76b)              13.198

- The 2026-08-03 gate refresh (a60678e7) carries the ENTIRE committed
  degradation: mean|bias| 8.713 -> 13.198, ge50 -14.155 -> -24.169. That
  commit changed NO code (4 data artifacts only); the movement is the
  drift the refresh measured, not anything the refresh did.
- The 2026-08-04 R7 dpw re-anchor (cfcba76b) contributed ZERO to the tier
  vector. Its fa_gate2_eval.json diff only drops the stale fa_mkt_lgbm_v1
  challenger block (a persist without challenger=True); every pooled,
  per-winter and tier number is byte-identical. R7 rewrote
  data/fa_dpw_series.json, which Gate 2 NEVER reads: run_market_gate
  derives its own train-only series in-run (fa_backtest.py:505), so the
  committed series cannot move the gate by construction. R7's own commit
  message records the same for served prices (clemens_2026 never reads
  the series).

### 1b. What moved under the 08-03 refresh

Between the 07-30 re-persist and 08-03, 4853e683 (2026-07-31) shipped
F-DEF into the WAR map, the kernel comps anchor and the no-vet-drop
repair, and the DB corpus moved under nightly regen. R7's own record
quantifies the result: the signings-implied $/WAR series rose up to
+15.9% per winter (2026: 14.92M -> 17.29M). DESTALE_MODE "series" derives
the comps de-staling rate from exactly that train-only series, and
de-staling and RECAL_MODE "shift" are documented SUBSTITUTES for one
level mechanism (fa_market.py, the E5 block). The single pooled intercept
re-fits to the corpus mean level each fold, so it absorbed the pooled
move; the tier-shaped residual it cannot express landed on the top tiers
(ge50 -14.2 -> -24.2). An intercept-only pooled shift is structurally
unable to hold four tiers at zero when the level basis moves non-uniformly
across the price scale.

### 1c. Reproduce run (current code, 2026-08-19)

run_market_gate(persist=False, persist_dpw=False), verbatim:

    guar_mae 9.690171109257715   aav_mae 2.9089461174411357
    years_mae 0.43286071726438696   mega_mae 79.81375032   n 1199
    ptier_bias lt10 -2.1799 / 10to20 -7.5035 / 20to50 -12.8839 / ge50 -23.4605
    mean_abs_bias 11.50693244824901   gates all true   runtime 38.3s

The committed artifact does NOT reproduce, and the mismatch is itself
diagnostic: FA_PRICING_USE_DEF=False was pinned 2026-08-06 (owner
decision) AFTER the artifact was last persisted, and the artifact's AAV
3.1348 is exactly the F-DEF-ON reading the attribution doc records
(3.135 -> 2.909 when the pin drops F-DEF; the fresh run reads 2.9089).
So the committed numbers describe the 08-03/08-04 F-DEF-ON state; the
artifact refresh is owed regardless of the arm outcome. Under current
code the top-tier defect is REAL, not a staleness artifact: ge50 sits at
-23.46 while the other three tiers recovered most of the 08-03 move.

## 2. PRE-REGISTERED ARM P-1 (frozen before fitting)

Family: INTERCEPT/LEVEL ONLY. Slope forms ("fit", "fit_group") are
twice-refuted (2026-07-24 ledger, E5) and are not re-attempted.

ARM P-1, RECAL_MODE "shift_ptier": the E5 intercept-only shift, fit PER
PREDICTED-GUARANTEE TIER on the same inner forward chain _fit_recal
already runs. Tier of an inner row = ptier of its RAW (pre-recal) inner
prediction, bins lt10/10to20/20to50/ge50 at 10/20/50 $M (the Gate-2 ptier
bins, the decision-relevant conditioning per _fit_recal's docstring). A
tier gets its own intercept iff its inner sample holds >= 30 rows
(RECAL_TIER_MIN_ROWS), else the pooled shift. Slope pinned 1.0. At
predict time the tier is keyed on the raw pre-recal point, the same
conditioning the intercepts were fit under.

Baselines frozen from the section 1c champion run (same code, same folds,
paired by construction; the committed artifact figures ride along as the
secondary reference):

    champion (1c): guar 9.6902 / mega 79.8138 / mean|bias| 11.5069
    committed:     guar 10.2067 / mega 86.0652 / mean|bias| 13.1977

Clauses, ALL must pass:

- C1 pooled guarantee MAE: arm <= 9.6902 (same-run champion; secondary
  reference, must also be <= the committed 10.2067).
- C2 mega slice MAE: arm <= 79.8138 (same-run champion; secondary
  reference 86.0652).
- C3 ptier mean|bias|: arm < 11.5069.
- C4 E5a overshoot check: NO tier's bias_model may exceed +10.0 $M;
  top-tier overshoot beyond +$10M is an automatic fail.
- C5 zero-information control: the identical estimator with tier labels
  PERMUTED at fit time (RECAL_TIER_PERMUTE_SEED=7) must NOT improve
  mean|bias| below 11.5069; and if the control's improvement reaches half
  the arm's improvement, the arm fails regardless of C3.
- C6 fold stability (per-tier intercepts admissible iff): for each tier
  that receives its own intercept in >= 5 of the 9 outer folds,
  sign(a_tier - a_pooled) is identical in >= 80% of those folds. Any
  tier violating this makes the arm not fold-stable: loss-record, no
  partial ship.

Ship action if ALL clauses pass: RECAL_MODE default -> "shift_ptier" in
fa_market.py (+ _LAB_DEFAULTS), artifact re-persisted via
run_market_gate(persist=True, persist_dpw=False) with generated_at added.
If ANY clause fails: loss-record below, RECAL_MODE stays "shift", and the
artifact is re-persisted in the champion state (the refresh is owed per
1c either way).

## 3. RESULTS (verbatim lab output only)

### 3a. ARM P-1 (RECAL_MODE="shift_ptier")

    guar_mae 9.704424931609676   aav_mae 2.936938099870938
    years_mae 0.43286071726438696   mega_mae 78.73650298000001   n 1199
    ptier_bias lt10 -2.1394615709606986 / 10to20 -7.563996201550387 /
               20to50 -12.914115197674418 / ge50 -19.726743926470586
    mean_abs_bias 10.586079224164022   gates all true   runtime 36.8s

### 3b. Zero-information control (RECAL_TIER_PERMUTE_SEED=7)

    guar_mae 9.648955722268557   aav_mae 2.927879249662431
    years_mae 0.43286071726438696   mega_mae 79.42767502   n 1199
    ptier_bias lt10 -2.298491158008658 / 10to20 -8.168966307692306 /
               20to50 -11.584179454545454 / ge50 -23.790946897058827
    mean_abs_bias 11.460645954326312   gates all true   runtime 36.0s

### 3c. Fold-stability log (arm run, RECAL_FIT_LOG, 6 of 9 outer folds
fitted a recal; the first three test winters' inner chains fall under
_RECAL_MIN_ROWS and return None, exactly as "shift" does)

    fold  _pooled     lt10       10to20     20to50     ge50
    0     -0.18892    -0.19765   -0.12135   (thin)     (thin)
    1     -0.00628    -0.00329   +0.03769   (thin)     (thin)
    2     +0.11460    +0.10291   +0.16990   +0.05491   (thin)
    3     +0.15387    +0.15006   +0.16564   +0.08899   +0.26837
    4     +0.13608    +0.13460   +0.12635   +0.12618   +0.19188
    5     +0.12586    +0.11983   +0.15860   +0.07537   +0.21857

    deviations (a_tier - a_pooled), sign pattern:
    lt10   -/+/-/-/-/-  5 of 6 negative (83%)
    10to20 +/+/+/+/-/+  5 of 6 positive (83%)
    20to50 fitted in 4 folds only (all negative)   under the 5-fold bar
    ge50   fitted in 3 folds only (all positive)   under the 5-fold bar

### 3d. Clause verdicts

    C1 FAIL  arm 9.7044 > champion 9.6902 (delta +0.0142; the secondary
             reference, committed 10.2067, is satisfied, but the frozen
             primary is the same-run champion and it is not)
    C2 pass  mega 78.7365 <= 79.8138
    C3 pass  mean|bias| 10.5861 < 11.5069 (delta -0.9209; ge50
             -23.4605 -> -19.7267)
    C4 pass  no tier positive, no overshoot
    C5 FAIL  the permuted control IMPROVES mean|bias| (11.4606 < 11.5069,
             by 0.0463); the frozen first condition is "must NOT improve".
             The second condition holds (0.0463 < half of 0.9209), so the
             arm's bias gain is mostly real signal, but the clause as
             registered fails.
    C6 pass  both tiers over the 5-fold bar are sign-stable at 83% >= 80%.
             CAVEAT on the record: ge50, the tier this arm exists for, got
             its own intercept in only 3 of 9 outer folds (2024-2026); the
             top-tier correction does not exist in the early half of the
             chain.

VERDICT: NO SHIP. Loss-record. RECAL_MODE stays "shift"; the shift_ptier
machinery and its lab knobs stay in fa_market.py for re-gating, default
off. Worth recording for the next cycle: the control's pooled guarantee
MAE (9.6490) beats BOTH the champion (9.6902) and the arm (9.7044), i.e.
shuffled tier labels outscore real ones on the headline metric on a
single fixed-dataset run, which is the 2026-07-24 lesson again: deltas of
|0.01-0.04| $M are under the ~0.16 $M corpus noise floor and sharp
single-run inequalities on them are coin flips. If P-1 is re-opened it
needs a paired-bootstrap gate (B>=200 corpus resamples) with C1 and C5
stated against the bootstrap null band, pre-registered fresh, and it
should confront the ge50 sparsity (3 fitted folds) directly. The bias
result itself is encouraging and unspent: C3's -0.92 improvement is 20x
the control's, concentrated in the exact tier the diagnosis names.

Artifact action taken (per section 2's else-branch): champion state
re-persisted via run_market_gate(persist=True, persist_dpw=False),
reproducing 1c exactly (guar 9.6902 / mega 79.8138 / mean|bias| 11.5069),
generated_at added. The stale F-DEF-ON figures (10.21/86.07/13.20) are
superseded in the artifact; the registry note carries the dated reading.

## 4. TERCILE RE-CUT (task B, owner default adopted 2026-08-19)

Not a gate arm; an owner-adopted recalibration of the POOLED verdict
tercile edges, recorded here for the flip count.

Design (fixed before measuring): corpus Deal+ on the tercile-cut basis A
(expected rational value / ACTUAL NPV price; forward-chained train-only
$/WAR series per winter, ex-ante winter_dpw + _destale_rate, predicted
term capped at 10, the _am_fa_dealplus convention). New pooled edges =
interpolated p33/p67 of that distribution, rounded to integers. Record:
old-edge (109/223) distribution, new-edge distribution, count of
historical corpus rows whose POOLED verdict flips.

PREMISE CORRECTION, on the record: the tasking (and the fa_rational_value
registry note it quotes) says the served split is 37/52/9 and that
VERDICT_BAND_MODE is pooled. Both are stale. VERDICT_BAND_MODE has been
"group" since b21c027a (2026-07-30, owner decision), and the served board
(data/fa_class.json generated 2026-08-19, n=226) verdicts reproduce the
GROUP edges exactly (0 mismatches) at a split of overpay 23% / market
54% / value 23%. The pooled edges re-cut here are the fallback constants
and the historical-corpus banding basis; ZERO served verdicts move unless
the owner also re-cuts VERDICT_GROUP_EDGES (followup, flagged). The mode
is left untouched.

### 4a. Measured re-cut (verbatim lab output, lab_tercile.py)

Run twice: once on the prior session (output persisted to
tercile_recut.pkl before that session died), once fresh on resume
2026-08-19. The two runs are byte-identical, so the corpus did not move
between them; the fresh output:

    n 1300   winters 2017-2026
    p33 88.799   p67 197.77
    old_edges [109, 223]  ->  new_edges [89, 198]
    old_counts overpay 548 / market 385 / value 367   (42.2/29.6/28.2)
    new_counts overpay 434 / market 433 / value 433   (33.4/33.3/33.3)
    verdict flips 180 of 1300 (13.8%)
    group own terciles (diagnostic for the group-edge followup):
      SP  n 297  own_p33  89.4  own_p67 179.9
      RP  n 450  own_p33  66.5  own_p67 143.8
      C   n 102  own_p33 120.4  own_p67 279.4
      POS n 451  own_p33 115.6  own_p67 256.3

Registry-note verification: the note's "~85/189 restores the pooled
design" was the 2026-07-30 reading of the same staleness on the
pre-08-06 (F-DEF-ON) pricing basis. On the CURRENT basis the restoring
edges are 89/198, not 85/189; direction and mechanism confirmed, the
constants superseded.

### 4b. Ship record (task B)

- fa_market.py: VERDICT_OVERPAY_MAX 109 -> 89, VERDICT_VALUE_MIN
  223 -> 198, with the re-cut dated in the adjacent comment.
- data/fa_gate2_eval.json: verdict_edges block records band_mode,
  pooled edges, shipped group edges, and the full recut_2026_08_19
  record (edges, counts, 180 flips, group own terciles).
- VERDICT_BAND_MODE stays "group" (untouched); ZERO served verdicts
  move (section 4 premise correction). FOLLOWUP owed: re-cut
  VERDICT_GROUP_EDGES on this same basis using the 4a own-tercile
  table; until then the shipped group edges (SP 86/182, RP 65/146,
  C 101/243, POS 103/237) band the served board on the pre-08-06 cut.
- test_fa_ptier_gate.py fences both tasks: RECAL_MODE stays "shift"
  (P-1 loss-record), no positive ptier bias beyond +10 $M in the
  artifact (E5a standing check), pooled edges consistent across
  fa_market.py and the artifact, generated_at present.
