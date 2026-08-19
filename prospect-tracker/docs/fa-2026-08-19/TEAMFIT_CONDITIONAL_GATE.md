# TEAMFIT CONDITIONAL GATE (Gate 3 lever: player-conditional behavior)

Frozen 2026-08-19 BEFORE any fitting or measurement. Results sections carry
PENDING until the lab runs; they are then filled with verbatim lab output.
No post-hoc arm, frame, floor, band, or estimator changes after this freeze.

## Registered defect (artifact's own decomposition, data/fa_gate3_eval.json 2026-08-04)

behavior = 0.5*reach + 0.3*recent + 0.2*rich. Only reach takes a player
input. `recent` normalizes by the league-max 3-winter outlay, which is LAD,
so LAD reads exactly 1.0 for every member. `rich` clips at n_100m/5. Both are
club constants: LAD tops 228 of 228 behavior lists and the concentration
tripwire is RED (max_top1_share 0.5746 vs 0.25; distinct_top1 11 vs 12;
distinct_top3 19 vs 20).

## Standing prior, disclosed

fa_fit.py and fa_fit_backtest.py carry an R6.3 note (2026-08-04): six
WITHIN-CLUB conditional-rate rewrites of recent/rich failed both gate halves,
and with behavior deleted outright the composite still concentrated 0.3816.
Those numbers are in code comments only; the persisted artifact never carried
an R6.3 block, so the lever is registered un-gated. This gate re-measures,
including the behavior-deleted falsification, and records whatever comes out.
The candidate here differs from R6.3: it keeps CROSS-CLUB magnitude
comparison but restricts it to the player's price band, instead of collapsing
to within-club rates (which destroyed the signal along with the monopoly).

## Candidate C (FROZEN)

Band: band(g) = [g / 2.5, g * 2.5], g = the deal's NPV guarantee on the chain,
proj_guarantee_usd on the served class. Multiplicative, symmetric in log space.

- reach: UNCHANGED (already player-conditional since F4).
- recent_cond(club, g, Y) = club outlay on prior signings with class_year in
  [Y-3, Y-1] AND guarantee in band(g), divided by the league max of that same
  quantity across the 30 clubs for this player. League max 0 => 0.0 for all.
  Served class uses the live corpus recency window (y >= last_winter - 2),
  identical to fa_fit.behavior_priors.
- rich_cond(club, g) = min(1.0, n_band / 5), n_band = count of the club's
  prior career MLB-deal guarantees in band(g). The /5 clip is retained from
  the incumbent on purpose: one lever per gate.
- behavior_cond = 0.5*reach + 0.3*recent_cond + 0.2*rich_cond
  (fit.behavior_weights unchanged).
- Composite candidate = shipped fa_config fit.weights with behavior_cond
  substituted for behavior. No weight moves.

Known property, accepted at freeze: rich_cond can saturate for many clubs in
cheap bands (many clubs have 5+ small deals). The gate decides; no retune.

## Measurement frame

- Chain: fa_fit_backtest.build_rows() forward chain, winters 2018-2026,
  registered n=1173 signings x 30 clubs. If today's regenerated frame drifts
  from 1,173 the drift is disclosed and the run proceeds on the current frame;
  the accuracy floor stays anchored to the REGISTERED 0.1669, and the
  same-frame incumbent is reported beside it.
- Served class: data/fa_class.json members via class_component_matrix()
  (live component scores), behavior_cond recomputed from
  storage.load_fa_signings(), the identical corpus behavior_priors reads.
- Ranking ties break alphabetically (matches _conc_from_scores).

## Clauses (FROZEN)

1. ACCURACY FLOOR. Cluster bootstrap on the chain frame: unit = signing
   (its 30-row group), B = 2000, numpy seed 7, statistic = paired MRR delta
   (candidate - incumbent) per resample. MDE95 = 1.96 * SD(bootstrap deltas),
   stated in the results. PASS iff mrr_cond >= 0.1669 - MDE95 AND
   top3_cond >= 0.145 - MDE95 (same margin for both, per the task freeze).
2. CONCENTRATION, candidate composite on the served class:
   max_top1_share < 0.25 AND distinct_top1 >= 12 AND distinct_top3 >= 20.
   median_gap is reported, not gated (this gate's clause set does not
   include it; the shipped tripwire still does and stays untouched).
3. SANITY. LAD is behavior_cond top-1 for < 50% of served members.
   LAD composite top-1 share reported beside it.
4. ZERO-SLACK REFUSAL. If accuracy and concentration trade one-for-one again
   (clause 2 passes while clause 1 fails, or clause 1 passes while clause 2
   fails), record the refusal and STOP. No band retune, no clip retune, no
   weight moves, no second arm.

SHIP iff clauses 1 AND 2 AND 3 pass and clause 4 does not fire. Ship =
fa_config flip + artifact re-persisted. Anything else = loss-record here,
in the artifact block, and in the registry note. The incumbency ceiling
(fitted_full MRR 0.2679) stays excluded by product design.

## Pre-registered diagnostics (reported, never gated)

- behavior-deleted composite concentration on the current served class
  (checks the R6.3 falsification claim of 0.3816).
- behavior_cond term-level concentration (top-1 share, distinct counts).
- Same-frame incumbent chain metrics.

## Results (filled 2026-08-19 from lab output, scratchpad teamfit_cond_result.json)

### Chain frame

chain_n = 1173. Exactly the registered frame; no drift. Same-frame incumbent
reproduces the registered numbers bit-exact:
incumbent {top1 0.052, top3 0.1449, top5 0.2293, mrr 0.1669}.

### Clause 1: accuracy

candidate {top1 0.0546, top3 0.1338, top5 0.2097, mrr 0.1628}
mrr_delta -0.0041, MDE95 0.0139 (B=2000, seed 7, cluster bootstrap, ddof=1),
delta CI95 [-0.0184, +0.0091].
Floors: mrr 0.1628 >= 0.1669 - 0.0139 = 0.1530  PASS
        top3 0.1338 >= 0.145 - 0.0139 = 0.1311  PASS (margin 0.0027, slim)
The CI straddles zero: the candidate is statistically indistinguishable from
the incumbent on MRR. PASS.

### Clause 2: concentration (candidate composite, served class n=230)

max_top1_share 0.2174 (WSN) < 0.25  PASS
distinct_top1 16 >= 12              PASS
distinct_top3 25 >= 20              PASS
median_gap 0.0163 (reported, not gated; also clears the shipped tripwire's
0.015, so the FULL four-criterion tripwire would read GREEN on this measure)
top1_counts: WSN 50, NYM 43, NYY 40, CHW 37, PHI 19, SFG 14, COL 6, LAD 5.
PASS.

### Clause 3: sanity (LAD)

LAD behavior_cond top-1 share 0.3826 (88 of 230; was 1.0000, 228 of 228).
0.3826 < 0.50  PASS. LAD candidate-composite top-1 share 0.0217 (5 of 230).

### Clause 4: trade check

Clause 1 PASS and clause 2 PASS. The one-for-one trade did NOT repeat.
Refusal not fired.

### Diagnostics (reported, never gated)

- recompose_max_abs_dev_vs_matrix_behavior 0.0005: the corpus recomposition
  is faithful to the live matrix behavior scores.
- behavior-deleted composite on the CURRENT class: max_top1_share 0.2913
  (MIA), distinct_top1 8, distinct_top3 19 - still fails 0.25. The R6.3
  comment's 0.3816 does NOT reproduce on today's class (the class moved,
  n 228 -> 230, and the corpus grew). The candidate PASSES where deletion
  fails because behavior_cond carries interaction that redistributes top-1s
  against the residual need/park concentration; deletion carries none.
- incumbent recomposed on the CURRENT class: max_top1_share 0.3261 (LAD),
  distinct_top1 7, distinct_top3 14 - the live tripwire is still RED today,
  but far less red than the registered 0.5746 (class movement, not code).
- behavior_cond term alone: max_top1_share 0.3826 (LAD), distinct_top1 6.
  The term still concentrates; the composite de-concentrates because the
  constant league-max floor is gone.
- TOP5 DROPS 0.2293 -> 0.2097 (-0.0196). top5 is the artifact's stated
  headline metric but was NOT a frozen clause here. Disclosed for the owner;
  the ship verdict below follows the frozen clauses only, and the live flip
  is a separate wiring step where the owner can veto.

## Verdict

ALL FOUR CLAUSES PASS. SHIP per the frozen gate, with two disclosures:
top3 margin is slim (0.0027) and top5 degrades outside the clause set.

Ship mechanics executed in this session (file boundary honored):
- fa_fit_backtest.py: behavior_cond in build_rows + teamfit_conditional_gate
  wired into run_fit_gate; regenerates the artifact block on every run.
- fa_config.yaml: frozen parameters registered under fit
  (behavior_conditional flag + behavior_cond_band_factor 2.5). The flag ships
  FALSE: the live engine read in fa_fit.fit_scores is NOT in this lane's
  file set, so flipping it here would make config lie about what is live.
- data/fa_gate3_eval.json: teamfit_conditional_gate block persisted verbatim.
- NOT done here (followup, other lane's file): fa_fit.py wiring of the
  conditional terms behind the config flag, and retiring its now-superseded
  "do not re-attempt a behavior-only repair" comment (its 0.3816
  falsification number does not reproduce on the current class).

The incumbency ceiling (fitted_full MRR 0.2679) stays excluded by product
design. The live concentration tripwire stays RED until the fa_fit.py flip
lands; this gate measured the candidate GREEN at 0.2174/16/25 on n=230.
