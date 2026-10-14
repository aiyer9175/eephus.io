# FA destination gate: FA_DESTINATION_GATE (registered 2026-10-08)

Registration status: REGISTERED

Protocol hash: `cab64290169c7577c74db3181fae35ffffd505389010113d836749818155bda8` (sha256, defined in section 17)

**Registered, not read.** Model id `fa_destination`. This document was written
before any code, feature builder, coefficient, probability, artifact, registry
row or glossary entry for the destination model exists, and before any number of
the model has been computed: no fit, no ranking, no log loss, no floor, no join
of an industry pick to a signing. The feature builder `fa_destination.py`, the
producer `tools/fa_destination_lab.py`, the eval artifact
`data/fa_destination_eval.json`, the registry row `fa_destination` and the serve
flag `FA_DESTINATION_SERVE` are names reserved here (to be built, task Q9_04a);
the one gate read is task Q9_04b. Plan: Part 8 P8.5 'The financial module into
Free Agency and Arbitration', item FAA-0 (task Q9_02), from the lane design
`finance_to_fa_arb.md` sections 2.3 and 4.4 (Part 8 bundle). Code citations are
HEAD `0f9fb164` unless a commit is written beside them; the anchor in brackets
wins over a line number.

## 0. Read to write this

**No destination model exists, so no read below was joined to a destination
model's output.** Every read of this gate's frame (the Gate 3 forward chain,
winters 2018-2026) that shaped the design is listed. Each number is quoted from a
committed artifact or from the Part 8 lane's read-only pass of 2026-09-30, and
none was recomputed for this document.

- `data/fa_gate3_eval.json` (generated 2026-08-04, last changed at `4db4e9cd`),
  block `results`, the six registered arms quoted in section 4.1. Among them the
  **payroll_only against random comparison**: MRR 0.1350 against 0.1332, a gap of
  0.0018 inside the frame's 0.0139 floor. It is why payroll space stays the named
  baseline (`payroll_space`) and why payroll level is added beside it.
- The same artifact, `fitted_transfer_coefs_final_winter`: **the final-winter
  logistic without incumbency** signs need +0.513, window -0.168, afford -0.068,
  park +0.010, behavior +0.337. Its negative space term (clubs with LESS room
  under the tax signed more on this chain) was read as payroll carrying its level,
  not its room. It motivated the feature L2 `payroll_level` and the
  `payroll_level` baseline.
- The same artifact, **`fitted_full` and its incumbency result**: the logistic
  with the incumbency indicator scored MRR 0.2679, top-1 0.1787 and top-5 0.3065
  on its 1,080 signings, against the served analog's 0.1669 and 0.0520. It is why
  section 1 states, before any number, that C1 and C2 are expected to pass from
  re-signing alone, and why C3 alone answers the owner's ask.
- The same artifact, **the refits of the Fit's own features**: the per-winter
  refit (`fitted_transfer`) scored MRR 0.1479 on its 1,080, and the final-winter
  fitted vector (`weight_mix_comparison.fitted_logistic`: need 0.596, window 0,
  afford 0, park 0.012, behavior 0.392) scored 0.1660 against the shipped
  weights' 0.1669 on the identical 1,173-signing chain. They are why the model
  keeps the Fit's five weights fixed and fits one temperature on them.
- The same artifact, block `teamfit_conditional_gate`: MDE95 0.0139 (cluster
  bootstrap, signing as the unit, B 2,000, seed 7), chain_n 1,173, and the banded
  chain (the `behavior_cond` term the Fit ships since 2026-08-19) at MRR 0.1628,
  top-1 0.0546, top-5 0.2097. Read by this writer on 2026-10-08 to define F as
  the twin of what ships (section 5) and to add the banded twin to step 0.
- **The served 2027 class's first-fit counts** (`data/fa_class.json`, generated
  2026-09-25, read by the lane): CHW 50, WSN 46, NYY 41, NYM 34, PHI 19, LAD 11,
  SFG 11, CHC 6 of 232 priced members; 14 distinct first clubs; max share 0.2155;
  the 96 CHW and WSN firsts all priced under $20M (median projected guarantee
  $2.6M and $3.2M); the 9 members priced at $50M or more first-fit NYY 4, NYM 3,
  LAD 1, PHI 1; the mean Fit components on the CHW rows (need 0.071, window 0.223,
  afford 1.000, park 0.508, behavior 0.825) and the WSN rows (0.191, 0.053, 1.000,
  0.451, 0.783).
- **The 2024-2026 league dollar shares** (the Ledger's `fa.winters`,
  `data/ledger_board.json` generated 2026-09-25, read by the lane): LAD 19.1%,
  NYM 14.1%, SFG 6.3%, TOR 5.7%, NYY 5.1% at the top; MIA 0.3%, MIN 0.4%, COL 0.5%,
  CLE 0.6%, WSN 0.7% at the bottom; CHW 1.4% ($129.3M) and WSN 0.7% ($69.5M) of
  $9.45B; CHW's free-agent signings by winter 2021-2026 of 2, 6, 4, 7, 9 and 8.
  These are nominal shares over the three winters before the 2027 class, so the L1
  inputs of the serving class are partly seen; no L1 value of any scored winter was
  computed.
- Code and rule files only, no data value: `fa_fit_backtest.py` (`build_rows`,
  `_rank_metrics`, `_fit_logit`, `teamfit_conditional_gate`, `run_fit_gate`),
  `fa_backtest.py` (the `GATE2_COLLECT` hook, `run_market_gate`),
  `tools/arb_fa_gate_d.py` (`_gate2_rows()`), `docs/ARBITRATION_GATE.md` section 7
  (GATE D), `docs/fa-2026-08-19/TEAMFIT_CONDITIONAL_GATE.md`, `ledger_export.py`
  (`computed_cbt_bill`, `PAYOR_NEXT`, the `qo_tier_key` rule), `fa_cba.py`,
  `data/cba_rules.json` (regimes, thresholds and its single encoded rate
  schedule), `fa_market.py` (`enriched_signings`, `_npv_of`, `npv_guarantee_usd`),
  `fa_config.yaml` (the fit weights), and the method and keys of
  `data/fa_meta.json` `qo_tax_by_payor_tier` (to exclude it, section 5).
- `data/_labs/fa_predictions/mlbtr_retro_2015_2025.json` (commit `6e42d75b`): its
  top-level and row keys, class_year per offseason (2016 to 2026), 50 rows each,
  the unresolved counts by offseason (3, 1, 0, 3, 4, 1, 1, 2, 5, 3, 4), and that
  offseasons 2015-16 to 2020-21 print one predicted team per row while 2021-22 on
  print each writer's pick. No predicted team, contract figure or name was read,
  and nothing in the file was joined to a signing.
- The registry row `club_fa_spend_profile` (Leg A, flipped 2026-10-03): its notes
  only.

**Named plainly: every Gate 3 figure above is a read of winters 2018-2026, the
winters this gate scores.** They are published metrics of other rankers (the
Fit's analog, its refits, a logistic with incumbency) on the realized-price frame,
and they shaped three choices: keep payroll space as the named baseline and add
payroll level; fix the Fit's weights and fit one temperature; state the
incumbency expectation before any number. No ranking, probability, coefficient or
metric of P, N or L_perm, no value of L1 to L4 on any scored winter, and no metric
of any baseline on the primary frame was computed. None of these reads was joined
to a destination model's output, because none exists.

## 1. The question and what this gate can answer

**The owner's ask 3 (2026-09-30, verbatim):** "Can we wire the financial module
into the Free Agency / arbitration modules to make them more accurate? Ex. to make
team fit projections more accurate based on which teams actually spend money in
free agency."

**Owner answers on file** (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, Part 8
batches 2 and 3): FA-DEST-1 (a) yes, with re-signing (merged with FA-DEST-2: the
Fit score itself stays byte-identical and the spending signal lives in this
model); FA-DEST-3 (b) also a retro comparator; FA-DEST-4 (a) no market-size arm;
OUTLOOK (a) as of signings, with the Fit kept on the pre-free-agency frame.

**Stated before any number, under FA-DEST-1 (a).** Clauses C1 and C2 are expected
to pass from re-signing alone: on these winters Gate 3's logistic with incumbency
already scored MRR 0.2679 and top-1 0.1787 against the served analog's 0.1669 and
0.0520. A serve therefore says nothing about the Ledger block. Only C3 (P against
N, with the L_perm twin) answers the owner's ask.

## 2. Estimand, registry row and reserved names

- **Estimand.** P(club signs player | the player signs a major-league deal this
  winter): for each free agent, a 30-vector over the 30 clubs
  (`fa_fit_backtest.ORGS`) whose entries lie in (0, 1) and sum to 1.
- **Registry row** `fa_destination`, written by the look task with the verdict
  the look returns, `eval_artifact` `data/fa_destination_eval.json`, gate document
  this file. This commit writes no registry row.
- **Reserved names** (to be built): `fa_destination.py` (the one feature builder
  that the lab and the export both import), `tools/fa_destination_lab.py`,
  `data/fa_destination_eval.json`, `FA_DESTINATION_SERVE` (default False),
  `data/fa_destinations.json`, `.cache/fa_destination/preview/`.

## 3. What never moves

- **The Fit** (`fa_fit.fit_scores`, `fa_config.yaml` `fit.weights`) stays
  byte-identical, and so do the served `teamFits`.
- **Gate 2.** `data/fa_class.json`, `data/fa_meta.json`, `data/fa_gate2_eval.json`
  and `data/fa_dpw_series.json` stay byte-identical. The lab reads predicted prices
  only through the `GATE2_COLLECT` hook with `persist=False, persist_dpw=False` and
  never triggers the auto re-export that follows a gate save (M14-1).
- **Gate 3.** The lab imports `fa_fit_backtest.build_rows`, `_rank_metrics` and
  `_fit_logit` and never calls `run_fit_gate`, whose `persist=True` default
  regenerates the frozen blocks; `data/fa_gate3_eval.json` stays byte-identical.
- The lab never calls `fa_export`. P(enter) is never multiplied into P(signs), so
  the frozen P(enter) eval (clock 2026-10-01 to 2027-01-31,
  `docs/fa-2026-08-19/PENTER_DECISION_EVAL_PREREG.md`) is untouched.
- Nothing here reads a betting column, a PROSPECT_ANCHOR cell or a reserved eFV
  frame, and nothing scores GATE C2.

## 4. The frame

### 4.1 Step 0: the realized-price frame, reproduced bit-exact

The lab calls `fa_fit_backtest.build_rows()` with no override and scores the
registered arms the way `run_fit_gate` does (the same `_rank_metrics`, the same
`_fit_logit` forward chain, the analytic random arm), without calling
`run_fit_gate`. The registered numbers (`data/fa_gate3_eval.json`, 2026-08-04):

| arm | n | top-1 | top-5 | MRR |
|---|---|---|---|---|
| random | 1,173 | 0.0333 | 0.1667 | 0.1332 |
| payroll_only | 1,173 | 0.0384 | 0.1722 | 0.1350 |
| behavior_only | 1,173 | 0.0418 | 0.2080 | 0.1515 |
| live_analog | 1,173 | 0.0520 | 0.2293 | 0.1669 |
| fitted_full | 1,080 | 0.1787 | 0.3065 | 0.2679 |
| banded twin (`teamfit_conditional_gate.chain_candidate`) | 1,173 | 0.0546 | 0.2097 | 0.1628 |

Bit-exact means the same n and the same four-decimal top-1, top-3, top-5 and MRR
for every row. **Drift rule (the TEAMFIT gate's):** a difference in any of them is
disclosed in the artifact, registered value beside today's, and the run proceeds
on the current frame; no floor, clause or definition moves because of a drift.

### 4.2 The primary frame: as served

The served model prices a free agent before he signs, so the primary frame
replaces the price input of every row with Gate 2's forward-chained prediction for
that signing.

- **Collection.** `fa_backtest.GATE2_COLLECT = []`, then
  `fa_backtest.run_market_gate(persist=False, persist_dpw=False)`, then
  `GATE2_COLLECT = None` in a `finally` (the Gate D precedent,
  `tools/arb_fa_gate_d.py@64bf1bb3:123-130` (in `_gate2_rows()`); the hook at
  `fa_backtest.py@410cccce:486-491`, appended at `:603-607` (in
  `run_market_gate()`)). Each collected tuple is (winter, player key, predicted
  guarantee $M, actual guarantee $M, predicted AAV $M, actual AAV $M, predicted
  years, actual years).
- **Join.** On (winter, player_key) against the Gate 3 signings. A Gate 3 signing
  with no collected tuple is dropped and counted; a key with more than one tuple in
  a winter is dropped and counted; a matched signing whose collected actual
  guarantee times 1e6 differs from `fa_market._npv_of` of the signing by more than
  $1 is dropped and counted (both sides price NPV). Counts by winter: Gate 3
  signings, matched, unmatched, duplicate, integrity drops, and collected tuples
  with no Gate 3 signing.
- **The override.** `build_rows` gains one keyword argument, `price_override`,
  default None. Given a mapping {(winter, player_key): (guarantee_usd, aav_usd)},
  it replaces only the signing's OWN price: the guarantee in the band terms, reach
  and behavior, and the AAV in afford and L3. The clubs' behavior priors keep their
  realized prior guarantees, which are facts at the winter start. A signing absent
  from the mapping yields no rows. With the default, `build_rows()` returns rows
  byte-identical to today's, pinned by a row-hash test in the build task.
- Every arm and every baseline in a frame reads that frame's price.

### 4.3 Scored rows

One set for every arm and baseline: the matched signings of each winter Y whose
earlier matched winters hold at least 30 training positives (one positive per
signing; the `_fit_logit` rule, `fa_fit_backtest.py` (in `_fit_logit()`)). Winter
2018 has no earlier winter in the chain, so it trains only; the scored winters are
expected to be 2019-2026. The realized-price frame, reported in section 12, applies
the same rule to its own rows.

## 5. Features, all as of the winter start

| id | feature | exact definition, winter Y in the lab | 2027 class in serving |
|---|---|---|---|
| F | fit_analog | 0.40 need + 0.05 window + 0.05 afford + 0.05 park + 0.45 behavior_cond, the `build_rows` fields verbatim (need: the club had an outgoing free agent of his position group; window: playoff leverage at the club's Y-1 wins; afford: min(1, max(0, (threshold(Y-1) - Y-1 tax payroll) / (2 x AAV))), 0.5 when unknown; park: Y-1 Savant factors; behavior_cond: the banded will-spend term). The weights are read from `fa_config.yaml` `fit.weights` at run time and the lab stops if they differ from these. | the same definitions on 2026 inputs and `projGuar` / `projAav` (not the served Fit's components; lane findings F-1, F-2) |
| L1 | fa_share_3 | the club's sum of NPV guarantees over the league's sum, over every `storage.load_fa_signings(y)` row with y in Y-3..Y-1, `mlb_deal` true, years and guarantee above 0 and `to_team` among the 30 clubs, each valued at `fa_market.npv_guarantee_usd(player_key, y, guarantee_usd)`. No WAR-history filter, so international signings count. | the same over 2024-2026 |
| L2 | payroll_level | the z-score across the 30 clubs (mean and population SD over clubs with a value) of the club's season Y-1 tax payroll from `fa_fit_backtest.team_payroll_state(Y-1)` (Spotrac tax pages, cached for 2016-2025); a club with no value takes 0 and is counted | season 2026 |
| L3 | tax_multiplier | 1 + (bill(T + a) - bill(T)) / a, with T the club's Y-1 tax payroll (as L2), a his AAV in the frame, and bill(x) = `ledger_export.computed_cbt_bill(x, fa_cba.cbt_threshold(Y).threshold_usd, tier_Y, fa_cba.cbt_tax_rates(), fa_cba.cbt_surcharge_tiers())` bill_usd (`ledger_export.py@64bf1bb3:305-341` (in `computed_cbt_bill()`)); tier_Y = `ledger_export.PAYOR_NEXT` of the club's Y-1 Spotrac payor token when T exceeds threshold(Y-1), else Non-Tax (the Ledger's derived-payor rule). T unknown or a not above 0 gives 1, counted. | T = 2026 tax payroll, threshold(2027), a = `projAav` |
| L4 | qo_cost | q x 1[club is not his club] x k, with q = 1 when the signing carries a qualifying offer (`qo`), and k the number of draft picks in `fa_cba.pick_forfeiture(tier, date(Y-1, 12, 1))` picks for tier `cbt_payor` when the club's Y-1 Spotrac payor token is not Non-Tax, else `other` (the Ledger's `qo_tier_key` rule): k is 2 or 1 | the class member's qualifying offer; the club's 2026 token |
| I1 | incumbent | 1 when the club is his club (`from_team`), else 0 (the `build_rows` field) | the class `from` |

**Definitions resolved at registration (defaults, each disclosed).**

- F is the twin of what ships, so it uses `behavior_cond`, the banded term the Fit
  has served since the TEAMFIT conditional gate passed; the registered unbanded
  analog (0.1669) stays in step 0 and is reported beside the primary frame.
- L4 counts forfeited picks instead of the Ledger's `qo_pick_tax` dollars, which
  are priced from realized slot WAR (`method` `realized_slot_war_service_priced_v2`)
  and exist only for the current class: the Ledger block stays WAR-free and the
  same definition runs in the lab and in serving. Revenue-sharing status has no
  in-tree source by season, so it maps to `other`, as the Ledger maps it.
- L3 for winters 2018-2021 (thresholds of the 2017 agreement): `cba_rules.json`
  encodes one rate schedule, the 2022 one, and the lab applies it to every winter.
  The 2022 agreement added the third surcharge tier (the 60% rate from $60M over),
  so the lab counts the rows of those winters where T + a exceeds threshold(Y) +
  $60M and reports the count; no rate is hand-entered.

**Excluded, with reasons.** Forward commitments and forward space (Spotrac's
class-year page, scraped after the fact for past winters, includes the
signings being predicted); projected arbitration (no ex-ante projection exists
for 2018-2021; Swartz starts 2022); market size (FA-DEST-4 (a); no in-tree source;
attendance is a key the Ledger refuses; payroll level already carries the club
effect); ownership signals (no source); the Ledger's QO dollars (WAR-borne, above);
the served Fit's AFFORD and WINDOW inputs (not reconstructable for past winters,
lane findings F-1 and F-2); any club fixed effect (it would fit the club main
effect directly, the monopoly the Gate 3 notes describe).

## 6. The model

A conditional logit over the 30 clubs for each signing i:

```
u_ij = tau x F_ij + beta . L_ij + gamma x I1_ij
P_ij = exp(u_ij) / sum over the 30 clubs k of exp(u_ik)
```

- Only tau, beta (four terms) and gamma are fitted, on the scored frame's winters
  before Y, and scored on Y (forward chain). The Fit's five weights inside F are
  never refitted.
- Inside each training fold, L1, L3 and L4 are standardized by the mean and
  population SD over all 30 x n training rows of the fold, and the test winter's
  rows use the fold's mean and SD; L2 enters as defined; F and I1 enter raw. A
  feature with SD 0 in a fold enters as 0 there, counted.
- **Penalty, fixed now:** minimize the summed negative log likelihood over the
  fold's signings plus 0.5 x lambda x (the sum of squared beta), lambda = 1.0 (the
  `_fit_logit` setting, C = 1.0). tau and gamma are not penalized.
- Optimizer: `scipy.optimize.minimize`, method L-BFGS-B, start at zeros, analytic
  gradient, gtol 1e-8, maxiter 2000. A fold that does not converge is recorded and
  scored with the returned coefficients. No other setting is tried.
- Every fold's coefficients are written to the artifact, with a `coef_hash`.

## 7. Arms and baselines

All arms carry I1 (owner answer FA-DEST-1 (a)).

- **P** (primary): F + L1-L4 + I1.
- **N** (ablation): F + I1.
- **L_perm** (control): P with L1-L4 permuted across clubs within each winter: for
  winter Y one permutation pi_Y of the 30 clubs, drawn by
  `numpy.random.default_rng(7 + Y).permutation(30)` over the clubs in `ORGS`
  order; in every signing of winter Y, club j's L1-L4 values are replaced by club
  pi_Y(j)'s values for the same signing, in training and test winters alike. One
  draw per winter, no other.
- **Baselines** on the same rows: `random` (analytic: top-k k/30, MRR 0.1332);
  `payroll_space` (Gate 3's `payroll_only`, ranks by afford); `payroll_level`
  (ranks by L2, richest first); `behavior_only` (ranks by `behavior_cond`, as
  shipped); `live_analog` (ranks by F, the twin of the served Fit); and
  `incumbency_only` (his club first, then uniform: a signing that re-signs ranks 1;
  any other takes the analytic expectation over a uniform order of the other 29
  clubs; a signing with no club among the 30 takes the random expectation). Its
  probabilities: his club at the training fold's re-sign share among signings whose
  `from_team` is one of the 30, the other 29 sharing the rest equally; 1/30 each
  when he has no club among the 30.
- Rank ties break alphabetically by club code, Gate 3's sort.

## 8. Metrics

- Top-1, top-3, top-5 and MRR as `_rank_metrics` computes them (four decimals),
  for every arm and baseline.
- Multinomial log loss: the mean over scored signings of -ln P(signed club), out of
  fold (forward chain), natural log; uniform = ln 30 = 3.4012. For P, N, L_perm,
  `random` and `incumbency_only`.
- Reliability: the OLS slope of the realized indicator on the predicted P, with an
  intercept, over all 30 x n (signing, club) rows; and ECE in ten bins (rows sorted
  by P, ties by club code then winter and player key, split into ten equal-count
  bins by `numpy.array_split`; ECE = the sum over bins of (bin rows / all rows) x
  |mean realized - mean predicted|). For P, N and L_perm.

## 9. Floors and the bootstrap

- **One set of resamples.** The scored signings are ordered by (winter,
  player_key); `rng = numpy.random.default_rng(7)`; 2,000 draws of
  `rng.integers(0, n, n)`, the unit one signing with its 30 rows. The same 2,000
  index draws serve every bootstrap quantity in this gate.
- **MRR floor: the paired MDE95 0.0139** on this frame
  (`teamfit_conditional_gate.mde95`), fixed; the same-frame paired MDE95 of P
  against each comparator (1.96 x the SD of the resampled paired difference) is
  reported, never gated.
- **Log-loss floor:** 1.96 x the SD (ddof 1) over the 2,000 draws of P's resampled
  mean log loss. The lab writes the floors block (this SD and floor, and the
  resample seed and count) to the artifact BEFORE it computes any arm's mean
  metric, any difference or any clause, and the build task's test asserts that
  order.
- **C3's test:** for MRR the paired difference P minus N, for log loss N minus P,
  each with a one-sided p = (1 + the number of draws whose difference is at most 0)
  / 2,001. Holm at family alpha 0.05 over the two: the smaller p rejects at or below
  0.025, and then the other at or below 0.05.

## 10. Clauses (frozen at registration)

Verbatim from the lane design (`finance_to_fa_arb.md` section 2.3):

- C1 vs payroll: P beats `payroll_space` and `payroll_level` on MRR by more than MDE95, and on top-5.
- C2 vs the Fit: P beats `live_analog` on MRR by more than MDE95.
- C3 the Ledger block (the ask's own test; Holm over MRR and log loss): P beats N on at least one after Holm, and L_perm reproduces less than 60% of the P minus N lift (the Gate D control rule, `docs/ARBITRATION_GATE.md:358-401`).
- C4 calibration: out-of-fold log loss below ln 30 by more than its floor; reliability slope within 0.8 to 1.2.
- C5 stability: P at or above `payroll_space` MRR in at least 7 of the scored winters (the Gate 3 "7 of 9" reading).

The C3 citation's line numbers are at `64bf1bb3`; at HEAD its anchor is the
heading '## 7. GATE D - the free-agent increment'. Operationally:

- **C1** passes when MRR(P) - MRR(payroll_space) > 0.0139 and MRR(P) -
  MRR(payroll_level) > 0.0139, and top-5(P) is above both baselines' top-5.
- **C2** passes when MRR(P) - MRR(live_analog) > 0.0139.
- **C3** passes when Holm rejects for at least one of MRR and log loss with the
  point difference favouring P, and, for every metric Holm rejects, (M(L_perm) -
  M(N)) / (M(P) - M(N)) < 0.60, with M the MRR or minus the log loss.
- **C4** passes when ln 30 - log loss(P) is above the log-loss floor and the
  reliability slope of P lies in [0.8, 1.2].
- **C5** passes when MRR(P) is at or above MRR(payroll_space) in at least 7 of the
  scored winters; fewer than 7 scored winters fails C5.

## 11. Ship rule

- C1, C2, C3, C4 and C5 all pass: serve P.
- C1, C2, C4 and C5 pass and C3 does not: serve N and record the Ledger block as a
  NULL in the artifact's loss ledger ("the Club Ledger's spending history did not
  make destinations more predictable than the Fit's will-spend term already
  does"). N is served only if C1, C2, C4 and C5 also pass with N in P's place;
  otherwise nothing serves.
- C1 or C2 fails: serve nothing and record the loss. C4 or C5 fails: serve nothing
  and record the loss.
- Any serve is a separate flag flip the owner can veto (the TEAMFIT precedent),
  under `FA_DESTINATION_SERVE`.

## 12. Reported, never gated

The realized-price frame with every arm and baseline; the per-winter table;
N against live_analog (the incumbency lift alone); the registered unbanded
`live_analog` and `behavior_only` on the primary frame; an accepted-QO-excluded
sensitivity (signings in `fa_cba.qo_acceptances` removed); the same-frame paired
MDE95s; every fold's coefficients; the 2017-agreement third-tier count (section
5); expected major-league deals per club (the sum of P over each winter's scored
signings) beside each club's realized count per winter, 2019-2026; first-club
concentration on the served class once the serving builder exists; the industry
comparators (section 13).

## 13. Industry comparators (FA-DEST-3 (b))

Both are reported, never gated, and join an industry pick to a signing only inside
the look (section 15) or, for the forward capture, after the class closes.

**Scoring rule, both comparators.** MLB Trade Rumors' pick is the club its post
names; where the post prints each writer's pick instead, the pick is the club the
most writers name, and a tie among k clubs credits 1/k to each tied club. A
player's MLBTR hit is that credit for the club he signed with (0 or 1, or 1/k on a
tie). The model's hit is 1 when its top club (the highest P) is the club he signed
with. Reported: the hit rate of each on identical players, the paired difference
with a player-cluster bootstrap 95% interval (`numpy.random.default_rng(7)`,
2,000 draws over the matched players), and the model's top-3 hit rate and MRR on
the same players for context.

**Retro, offseasons 2015-16 to 2025-26.** Input
`data/_labs/fa_predictions/mlbtr_retro_2015_2025.json` (FA_PRED_CAPTURE, commit
`6e42d75b`, parser `mlbtr-top50-1`; this task fetches nothing). Frame: rows with a
resolved `mlbam_id` whose player is a scored signing of the primary frame in that
row's class_year (the join is (class_year, mlbam_id) to the signing's winter and
`mlbam_id`). The model's vector is its out-of-fold forward-chain vector, so the
head-to-head covers class years 2019-2026; class years 2016-2018 have no
out-of-fold vector and are reported for MLBTR alone. Counts by offseason: rows,
unresolved (27 at capture), not a scored signing, matched. Scored for P and for N,
and for the arm the ship rule names. Context, disclosed: MLBTR's lists appear in
November with information past the winter start, such as reported interest, that
the model's winter-start inputs do not carry.

**Forward, the 2026-27 class.** FA_PRED_CAPTURE's November capture keeps MLBTR's
predicted team (`data/_labs/fa_predictions/2026_27_mlbtr_<capture date>.json`).
Frame: captured players with a resolved id who are members of the frozen vector
list (section 14) and sign a major-league deal with one of the 30 clubs by the
class close. Scored against the frozen served vector, after the class closes, by
the rule above; about 50 players a winter resolves only a large gap. If no vector
froze for 2026-27, the forward comparator moves to the 2027-28 class with the
forward read.

## 14. The forward read

If the model passed and is frozen before the 2026-27 qualifying-offer acceptance
deadline (about mid-November 2026, the date MLB announces), every class member's
vector and the Fit's `teamFits` are frozen that day and hash-pinned in this
document by a dated entry in section 18 (sha256 of each frozen file). The Fit stays
on the pre-free-agency frame, byte-identical under every OUTLOOK answer, so the
frozen `teamFits` are the pre-free-agency ones. Club features freeze at the freeze
date; members who sign leave the class; the served vector is never refreshed from
in-winter signings, which the lab never saw.

The read is scored after the class closes (the day before 2027 Opening Day) on
members who signed major-league deals with one of the 30 clubs: the section 8
metrics for the frozen vector, and the frozen `teamFits` ranks (MRR, top-1, top-5)
on the same members beside them. It is a report beside the gate verdict; it does
not reopen the clauses.

Otherwise the first forward read is the 2027-28 class, under the same rules. A
lockout after the 2026-12-01 CBA expiry delays the read until the class closes. A
new CBA that changes QO compensation or the CBT schedule puts a regime flag on L3
and L4, which are reported under the flag and not refit.

## 15. Order of the look, crash protocol and early looks

- **When.** Once, task Q9_04b, after the build task Q9_04a, after the fWAR label
  epoch's step Z entry and the M14-2 Gate 2 re-save, never on a registered look's
  date.
- **Order.** (1) A dry run of the whole reporting path on fixtures with nulls.
  (2) stdout and stderr teed to the task's output directory before anything else
  runs. (3) Step 0. (4) The Gate 2 collection, the join and its counts. (5) Every
  arm's per-winter fit, coefficients written. (6) The floors block written. (7) The
  metrics, the clauses and the ship verdict. (8) The reported blocks, the industry
  comparators last.
- **Crash protocol.** On any exception after step (3) begins: STOP, no rerun, and
  write OWNER_QUESTION.md in the task's output directory.
- **An EARLY LOOK** is any computation on the real 2018-2026 chain, before the
  look, of a ranking, probability, coefficient, floor or metric of P, N, L_perm,
  `payroll_level` or `incumbency_only`, of any arm on the primary frame, or of any
  join of an MLBTR pick to a signing. An early look VOIDS this registration. The
  build task may compute `build_rows()`'s row hash with no override and the join
  counts of section 4.2, which read no metric; its tests run on fixtures.

## 16. Served form (to be built, behind `FA_DESTINATION_SERVE = False`)

While the flag is off the payload goes only to `.cache/fa_destination/preview/`.
On a flip, one commit carries the flag, `data/fa_destinations.json` (`{model_id,
generated_at, class_year, arm, coef_hash, members: {key: {top: [[org, p] x 8],
rest_p}}, clubs: {org: {expected_mlb_deals}}}`, counts only, no club dollar
figure), the registry row and the glossary entries. On /fa/: a "Likely
destination" column, a "Where he signs" card block (top 5 with P and the three
largest drivers) and a "P(signs)" column beside Fit with the head note "Fit asks
whether he helps them; P(signs) asks whether they sign him." Pending-option members
read "if he reaches the market". The served `coef_hash` equals the artifact's.

## 17. Protocol hash

The protocol hash is the sha256 hex digest of the UTF-8 text from the line
'## 0. Read to write this' up to, not including, the line '## 18. Amendments',
with every run of whitespace replaced by one space and the ends stripped. It is
printed at the head of this document, pinned by `test_fa_destination_gate.py`, and
copied into the eval artifact by the lab. Changing any rule above changes it; a
change after this commit goes in section 18 as a dated amendment, before the look.

## 18. Amendments

None.

## 19. Results

### 2026-10-14: the one look (task Q9_04b), verdict SERVE N; the Ledger block is a NULL

Run once, 2026-10-14 11:27 to 11:28 local, worktree lane 208 (branch
`wt-Q9_04b_FA_DESTINATION_LOOK`), `python -u tools/fa_destination_lab.py --look
--generated-at 2026-10-14`, stdout and stderr teed to the task's output directory
before anything else ran; exit 0, no exception, stderr empty. The reporting path
was first dry-run on the synthetic fixture with nulls (`--dry-run`, every step
written, exit 0). Artifact `data/fa_destination_eval.json`, sha256
`d9297e2f4076dec759f9b79d53828ec55f0f643693263b4820efc2d4219b147c`, its
`protocol_sha256` equal to this document's (`cab64290...`), steps written in the
registered order: step0, gate2_join, folds, floors, metrics_clauses_verdict,
reported, industry. `fa_class.json`, `fa_meta.json`, `fa_gate2_eval.json`,
`fa_dpw_series.json` and `fa_gate3_eval.json` hash the same before and after.

**When.** After Q9_04a (30fb5799, integrated 163553e0), after the epoch's step Z
entry (2026-10-03) and the M14-2 Gate 2 re-save (168edf30). This gate registers
no date of its own, so this is not an early read. The PJ-C look of
`PROJ_COMPONENTS_GATE.md` also ran on 2026-10-14; the rule that no look runs on
another registered look's day is waived by the owner (EW3-5, 2026-10-14: "Fuck
the registered look days and waiting, we don't have to wait for anything. Let's
do everything today"), and this read is recorded as run under that waiver.

**Step 0 (realized-price frame, 35,190 rows, 1,173 signings).** random,
payroll_only and behavior_only reproduce bit-exact. Drift, disclosed by the rule
of section 4.1 (the two Arizona lookup repairs of 218560e0, as the build task
measured): live_analog top-5 0.2327 against 0.2293 and MRR 0.1672 against 0.1669;
fitted_full top-3 0.2435 against 0.2370, top-5 0.3083 against 0.3065, MRR 0.2690
against 0.2679; the banded twin top-3 0.1364 against 0.1338 and MRR 0.1630
against 0.1628. No floor, clause or definition moved.

**Gate 2 join.** 1,199 collected tuples; 1,173 of 1,173 Gate 3 signings matched,
0 unmatched, 0 duplicate, 0 integrity drops; 26 tuples carry no Gate 3 signing.
Primary frame: 1,173 signings over winters 2018-2026, scored winters 2019-2026,
n 1,080; no member dropped; no tax-multiplier default and no missing payroll.
Every fold of P, N and L_perm converged; no feature had SD 0 in any fold.

**Floors (written before any mean metric).** MRR MDE95 0.0139 (fixed); log-loss
bootstrap SD 0.02209, floor 0.04330 (seed 7, 2,000 resamples, n 1,080).

**Metrics on the primary frame (n 1,080).**

| arm | top-1 | top-3 | top-5 | MRR | log loss | slope | ECE |
|---|---|---|---|---|---|---|---|
| P | 0.1796 | 0.2509 | 0.3120 | 0.2722 | 3.2242 | 1.0191 | 0.0029 |
| N | 0.1787 | 0.2509 | 0.3065 | 0.2717 | 3.2248 | 1.0148 | 0.0020 |
| L_perm | 0.1815 | 0.2361 | 0.3046 | 0.2692 | 3.2382 | 0.9435 | 0.0029 |
| incumbency_only | 0.1798 | 0.2363 | 0.2929 | 0.2645 | 3.2347 | | |
| random | 0.0333 | 0.1000 | 0.1667 | 0.1332 | 3.4012 | | |
| payroll_space | 0.0343 | 0.0963 | 0.1778 | 0.1331 | | | |
| payroll_level | 0.0528 | 0.1407 | 0.2157 | 0.1639 | | | |
| behavior_only | 0.0500 | 0.1296 | 0.1926 | 0.1533 | | | |
| live_analog | 0.0537 | 0.1324 | 0.1926 | 0.1602 | | | |

**Clauses for P.** C1 PASS (MRR +0.1391 over payroll_space and +0.1083 over
payroll_level; top-5 0.3120 above 0.1778 and 0.2157). C2 PASS (MRR +0.1120 over
live_analog). C3 FAIL: one-sided p for P minus N, MRR 0.4403, log loss 0.4233;
Holm rejects neither (the first needs 0.025 or less); the point differences favour
P (MRR +0.0005, log loss 0.0006 lower), and L_perm's share of that lift, reported
only, is -5.0 on MRR and -22.6 on log loss (L_perm sits below N on both). C4 PASS
(ln 30 minus log loss 0.1770 against the floor 0.0433; slope 1.0191). C5 PASS (8
of 8 scored winters at or above payroll_space).

**Clauses for N in P's place.** C1 PASS (MRR +0.1386 and +0.1078; top-5 0.3065),
C2 PASS (+0.1115), C4 PASS (0.1764 against 0.0433; slope 1.0148), C5 PASS (8 of
8).

**Verdict by the ship rule (section 11): serve N; nothing serves until the
owner's flip of `FA_DESTINATION_SERVE`.** The loss ledger records the NULL: "the
Club Ledger's spending history did not make destinations more predictable than
the Fit's will-spend term already does". The answer to the owner's ask 3, as this
gate can give it: on 1,080 forward-chained signings, the Club Ledger's four
spending terms (FA spend share, payroll level, tax multiplier, QO pick cost)
added no measurable accuracy to the Fit's reduced twin plus incumbency. As
section 1 stated before any number, C1 and C2 pass on re-signing: N is
incumbency_only plus the Fit's twin, and incumbency_only alone scores MRR 0.2645.
Serving fit (every matched winter, 2018-2026): N fit_analog 0.8567, incumbent
1.7681, coef_hash `1c0fbaa5c72e97c3673d1811a85f8db9542887c4b78a5c43feb958d3be060149`
(the artifact's `coef_hash`); P's serving coefficients and hash are in the
artifact for the record.

**Reported, never gated.**

- Per winter, MRR (P / N / payroll_space / live_analog / incumbency_only): 2019
  (n 101) 0.1857 / 0.1772 / 0.1297 / 0.1328 / 0.1761; 2020 (123) 0.3318 / 0.3268
  / 0.1498 / 0.1673 / 0.3239; 2021 (143) 0.3031 / 0.3015 / 0.1135 / 0.1678 /
  0.2931; 2022 (142) 0.2375 / 0.2408 / 0.1255 / 0.1669 / 0.2252; 2023 (134)
  0.2306 / 0.2384 / 0.1265 / 0.1611 / 0.2371; 2024 (131) 0.2594 / 0.2518 / 0.1364
  / 0.1421 / 0.2473; 2025 (161) 0.2976 / 0.2925 / 0.1560 / 0.1718 / 0.2817; 2026
  (145) 0.3074 / 0.3174 / 0.1256 / 0.1616 / 0.3076. P is above N in 5 of 8
  winters.
- N against live_analog (the incumbency lift with the twin): MRR +0.1115.
- The registered unbanded analog on the primary frame: live_analog MRR 0.1650,
  behavior_only 0.1507.
- Same-frame paired MDE95 of P against: N 0.0062, L_perm 0.0081, payroll_space
  0.0247, payroll_level 0.0225, behavior_only 0.0230, live_analog 0.0227,
  incumbency_only 0.0064, random 0.0215.
- The realized-price frame (n 1,080): P MRR 0.2746, log loss 3.2211; N 0.2745,
  3.2210; L_perm 0.2702, 3.2346; live_analog 0.1635; payroll_space 0.1356.
- Accepted QOs excluded (14 acceptances, 7 matched signings removed, n 1,073): P
  MRR 0.2688, log loss 3.2332; N 0.2678, 3.2329; L_perm 0.2654.
- 2017-agreement third-tier rows (section 5): primary frame 62 in winter 2018 and
  0 in 2019-2021; realized-price frame 53, 1, 7 and 1.
- Expected major-league deals per club beside realized, 2019-2026: in the
  artifact (`reported.expected_mlb_deals_by_club`).
- First-club concentration on the served class: not available in the artifact
  (no serving builder existed at the look).

**Industry comparators (section 13), reported last.** Retro, MLB Trade Rumors
2015-16 to 2025-26 (input sha256 in the artifact): matched 358 players over class
years 2019-2026 (offseason counts in the artifact; 27 unresolved rows, 1 row with
no parsed pick). Model top-1 hit rate 0.2123 against MLBTR's 0.1625, paired
difference +0.0498, player-cluster bootstrap 95% interval 0.0058 to 0.0950,
identical for P and N; the model's top-3 hit rate 0.3212 (P) and 0.3073 (N), MRR
0.3201 and 0.3162. MLBTR alone on the class years with no out-of-fold vector:
2016 0.1364 (n 44), 2017 0.2609 (n 46), 2018 0.1163 (n 43). Context, as
registered: MLBTR's lists are written in November with information past the
winter start that the model's inputs do not carry. The forward comparator is
pending (section 14).
