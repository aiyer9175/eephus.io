# xM$ gate: XM_GATE (registered 2026-10-22)

Registration status: REGISTERED

**Registered, not read.** Model id `xm`. This document is committed alone,
before `xm.py`, the producer `tools/xm_lab.py`, the eval artifact
`data/xm_eval.json`, the registry row `xm` or any fitted number of the xM$
model exists. No candidate has been fitted, scored or bootstrapped. Owner
decisions XM-1 to XM-4 (2026-10-19, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`,
section 'XM: Expected Market $'); task XM_1_MODEL. Code citations are HEAD
`b6276c31`; the anchor in brackets wins over a line number.

What was looked at before writing this: row COUNTS of the signing table by
class year and deal type (1,760 rows; 145 non-MLB deals), the field names of
the MLB Trade Rumors retro capture (`data/_labs/fa_predictions/
mlbtr_retro_2015_2025.json`, 50 rows per offseason 2015-16 to 2025-26), the
season coverage of the IL table (`.cache/mlb_transactions/il_table.json`,
seasons 2015 to 2026) and the per-winter row counts Gate 2 already publishes in
`data/fa_gate2_eval.json`. No price, residual or error of any candidate.

## 1. The question

xM$ (Expected Market $) is what the free-agent market would pay a player this
winter: AAV, years and total guarantee jointly, with a P10 to P90 band (XM-2).
It is a POSITIVE model fitted on real signings and keeps the market's own
biases (XM-1), so recency of the platform season is a feature, not an error.
Fair $ is the existing rational value, shown beside it and never subtracted
from it (no gap column, XM-1). Pre-FA players and prospects are priced as if
they were free agents this winter and labelled counterfactual (XM-3).

This gate answers one question: which model prices signed MLB free agents
best out of sample, and does it beat a naive price and the served /fa/ model
on the two most recent winters, held out and read once.

## 2. The machinery is generalized, not forked

`fa_market.py` already ships both numbers for the current FA class: RATIONAL
VALUE (`expected_rational_value_usd`) and PREDICTED MARKET PRICE
(`MarketModel`, two stages: log years, then log NPV guarantee given years; per
winter $/WAR carried forward ex ante; flat residual quantile bands; real comps).
`xm.py` imports these functions; it never copies them. The as-of WAR path of
every row is `fa_market.contract_war_path` on `fa_projection.fitted_models`
fitted on seasons strictly before the winter (the `enriched_signings`
convention [fa_market.py:2827, in enriched_signings()]).

## 3. Label

Rows: `storage.load_fa_signings()`, class years 2015 to 2026.

* MLB deals (`mlb_deal` true, `years` and `guarantee_usd` positive, an MLBAM
  id and an as-of WAR path): years = `years`; total = the deferral-adjusted NPV
  guarantee (`fa_market._npv_of`, the incumbent's basis since Phase 2);
  AAV = total / years. These are the SCORED rows.
* Minor-league and non-guaranteed deals (`mlb_deal` false, an MLBAM id and an
  as-of WAR path): a CENSORED FLOOR, not dropped. The latent AAV is known only
  to sit below the league minimum of the class year
  (`arb_dataset.league_min_by_year()`, 2026's value carried to later years).
  Candidate (b) fits them as left-censored observations; candidates (a) and
  (c) price the market conditional on an MLB deal and do not fit them
  (disclosed, section 6). They are never scored as prices.
* Rows without an as-of WAR path (no MLB season in the three before the
  winter: NPB and KBO postings, other international professionals) are not
  training rows. They are the posting anchor set (section 11).

An MLB deal whose AAV sits at or below the league minimum stays an observed
row at its own value.

## 4. Features (all as of the winter start)

For a row of class year W, from data dated before W:

| name | definition |
|---|---|
| age | season age in W (the `enriched_signings` anchor) |
| war_y1, war_3, war_tot | as-of projected WAR path: year 1, sum of years 1-3, sum of all 15 years |
| plat_war | realized WAR of season W-1 (the projection corpus label, fWAR basis) |
| war_3y | realized WAR summed over seasons W-3 to W-1 |
| pos dummies | SP, RP, C, premium (SS, 2B, 3B, CF); corner and DH are the base |
| gs_share | pitchers: share of batters faced in seasons W-3 to W-1 with role SP (the corpus role, the stand-in for a GS share); 0 for hitters |
| il_prior1, il_3y | IL days in season W-1 and in seasons W-3 to W-1, from the IL table (seasons before 2015 are absent and count 0; coverage is reported) |
| qo | qualifying offer attached |
| supply_z | the incumbent's class supply at the position group (`fa_market._supply`, z-scored on the training winters) |
| demand | count of clubs whose season W-1 tax payroll (`fa_fit_backtest.team_payroll_state(W-1)`) sits at least $20M below the CBT threshold of season W |
| log_index | log of the winter's market-clearing $/WAR index (below) |
| log_rational3 | log(max(discounted WAR of path years 1-3, 0.25) x index) |

Positional NEED is not available as of past winters (the Ledger's depth data
is current only), so the demand term is payroll room alone. Disclosed, not
imputed.

THE $/WAR INDEX. The per-winter implied series is
`fa_market.dollars_per_war_by_winter` on the TRAINING rows of the fold. The
index for winter W is a one-step random-walk-with-drift forecast in logs from
winters strictly before W: log d(W) = log d(W-1) + mean of the prior log
differences (no drift with one prior winter; `fa_class._flat_dpw_usd()` with
none). A winter never sees its own prices or a later winter's
(`xm.dpw_index`; a test perturbs later winters and checks the index does not
move).

## 5. Candidates

Selected on forward-chained DEVELOPMENT winters only.

* (a) INCUMBENT: `fa_market.MarketModel` refit on the training winters of each
  fold exactly as Gate 2 refits it (`fa_backtest.run_market_gate` fold body),
  including its class supply convention. Point: `proj_years`,
  `proj_guarantee_usd`. Band: its own flat residual quantiles.
* (b) HURDLE: (i) P(guaranteed MLB deal), logistic on the section 4 features
  over MLB and floor rows; (ii) years, an ordered logit over the categories 1,
  2, 3, 4, 5, 6 and 7 or more, MLB rows; (iii) log AAV given log years, a Tobit
  regression left-censored at the log league minimum (floor rows censored, MLB
  rows observed), fitted by maximum likelihood. Point given an MLB deal: years
  = the median category (the 7-or-more category takes the mean years of its
  training rows); log AAV = the median of the latent normal truncated below at
  the floor; total = AAV x years. All three parts carry a ridge of 1.0 on
  standardized features, intercept free.
* (c) GBM: `sklearn.ensemble.HistGradientBoostingRegressor` for log years and
  for log AAV given log years, MLB rows. Monotone constraints: +1 on war_y1,
  war_3, war_tot, plat_war, war_3y and log_rational3 in both stages (more
  projected or realized WAR never lowers the price or the term); -1 on age in
  the years stage (age raises the years penalty). Fixed settings, never tuned:
  max_iter 300, learning_rate 0.05, max_leaf_nodes 15, min_samples_leaf 20,
  l2_regularization 1.0, early_stopping off, random_state 20261019. Point:
  years_f = exp(predicted log years) clipped to [1, 15]; AAV at years_f;
  total = AAV x years_f.

Years are scored on the rounded point (at least 1).

BANDS. Every candidate's first band is the P10 and P90 of its own in-sample
log-total residuals on the training rows. If a candidate's pooled development
P10-P90 coverage falls outside [0.75, 0.85], its band switches, for the whole
development and holdout read, to the WINTER-BLOCKED CONFORMAL band: the P10
and P90 of the out-of-sample log-total residuals of an inner forward chain
over the fold's training winters (each inner winter predicted by the
candidate fitted on the winters before it, from the fifth training winter on).
The switch is decided on development winters only and recorded. P50 is the
point. Band ordering P10 <= P50 <= P90 is enforced and tested.

## 6. Frames

* Winters 2015 to 2017 train only (Gate 2's `GATE2_WARMUP_THROUGH`).
* DEVELOPMENT: test winters 2018 to 2024, each fitted on all winters before it.
* HOLDOUT: test winters 2025 and 2026, each fitted on all winters before it
  (the 2026 fold trains on 2025, the forward chain). Read ONCE, after the
  development selection is written to the artifact.
* Disclosure: the incumbent's Gate 2 errors on 2025 and 2026 are already
  published in `data/fa_gate2_eval.json`, and its design choices were made
  with those winters in view. The holdout is fresh for (b) and (c), not for
  (a). Hence the verdict ladder in section 9.

## 7. Scoring

On scored rows (MLB deals with an as-of path), per candidate and comparator:

* PRIMARY: log-total MAE = mean |log(predicted total) - log(actual NPV total)|.
* Band: pinball loss on log total at q = 0.10, 0.50, 0.90, and the CRPS proxy
  = their mean; P10-P90 coverage (target 0.80).
* Years: share exact and share within one.
* Reported, never gated: log-AAV MAE, guarantee MAE in $M, per-winter and
  per-position-group cells, the megadeal slice (actual total >= $100M), and
  for (b) the Brier score of P(MLB deal) on MLB and floor rows.

## 8. Comparators (all required)

* NULL 1, NAIVE PRICE: total = years_age x max(league minimum,
  max(plat_war, 0) x index), where years_age is the median years of training
  MLB rows in the row's age band (27 or less, 28-29, 30-31, 32-33, 34 or more)
  and index is the section 4 one-step index. Band: its own in-sample residual
  quantiles.
* NULL 2, THE INCUMBENT: candidate (a).
* INDUSTRY BAR: MLB Trade Rumors' Top 50 predictions (task FA_PRED_CAPTURE,
  parser `mlbtr-top50-1`), joined on MLBAM id and class year. MLBTR predicts
  the sticker guarantee, so this comparison scores both MLBTR and the selected
  model against the STICKER guarantee on rows with no deferral adjustment
  (`deferral_adjusted` false). Reported on development and holdout. A claim
  versus MLBTR needs at least 60 paired holdout rows and the section 9
  bootstrap; with fewer, it is reported without a pass claim.
* PLANTED RECOVERY (before any real read, section 10).
* Reported context: a constant comparator (the training median log total of
  the row's position group).

## 9. Selection, pass rule and verdicts

SELECTION (development only): the candidate with the lowest pooled
development log-total MAE. If that is (a), no challenger is read.

PASS RULE (holdout, read once): the selected challenger replaces the
incumbent only if its pooled holdout log-total MAE beats BOTH NULL 1 and
NULL 2 with the one-sided 95 percent lower bound of the paired improvement
above 0. Paired improvement = MAE(comparator) - MAE(challenger) on identical
rows; the bound is the 5th percentile of a PLAYER-CLUSTERED bootstrap
(clusters = player_key, B = 4000, `numpy.random.default_rng(20261019)`).

VERDICTS and what the site may say (XM_2 and XM_3 serve dark until the owner
flips; these are the words the flip may use):

* REPLACE: the challenger passes. Registry `validated`. The site may say: "xM$
  is a market price model fitted on real free-agent signings. On the two most
  recent winters, held out from fitting, it missed actual guarantees by a
  median of N percent and beat both a WAR-times-price rule and the previous
  /fa/ model."
* INCUMBENT: no challenger selected, or the challenger fails, and the
  incumbent beats NULL 1 with lower bound above 0. Registry `provisional`,
  `provisional_kind` `inherits_parent_gate` (the incumbent's holdout is not
  fresh, section 6). The site may say: "xM$ uses the /fa/ market model,
  generalized to every player. On the two most recent winters it beat a
  WAR-times-price rule." No other accuracy claim.
* TIE: the served model does not beat NULL 1 with lower bound above 0.
  Registry `provisional`, `provisional_kind` `measurement_only`. The site may
  say only: "xM$ is an estimate of a free-agent price; on held-out winters it
  was no more accurate than a simple WAR-times-price rule." Never `validated`
  on a tie.
* VOID: planted recovery fails (section 10) or the read crashes after scoring
  began. No verdict, no registry claim, OWNER_QUESTION.md.

Counterfactual rows (section 11) carry no accuracy claim under any verdict:
the site labels them "counterfactual: priced as if a free agent this winter".

## 10. Planted recovery (runs before the development read)

On the REAL design (the development feature matrix, its winters and floors):

* P1 CENSORING: simulate latent log AAV = X b + e (b fixed in the lab, e
  normal with sd 0.45, seed 20261019); rows whose latent value falls below the
  log floor become floor rows. Pass if the Tobit fit recovers the true linear
  predictor with RMSE <= 0.10 AND a least squares fit on the uncensored rows
  alone recovers it worse (the censoring is doing work).
* P2a SIGNAL: simulated years (ordered logit, fixed cutpoints) and totals
  replace the labels of every MLB row; each candidate is run through the same
  forward-chained development scoring. Pass if the selected candidate's
  log-total MAE is within 15 percent of the oracle's (the true conditional
  median).
* P2b NULL: real log totals permuted across MLB rows within winter. Pass if
  the selected candidate does NOT beat the constant comparator with lower
  bound above 0 (no false discovery).

Any failure makes the read VOID for the candidate it concerns; a VOID
selected candidate falls back to the incumbent with verdict at most
INCUMBENT.

## 11. Counterfactual extension (XM-3), anchors and Fair $

FEATURES FOR ANY PLAYER, this winter (class year 2027):

* MLB players (pre-arb and arbitration, `trade_values.json` service phase):
  the same as-of path and features as a free agent, seasons through 2026.
* Prospects (no MLB season): the WAR path from served eFV: the expected
  six-season WAR `xfv_war_6yr` (the eFV grade's expected value, which carries
  the reach probability) spread evenly over the six seasons from the ETA
  season (`timeseries.json` eta), zero before it, and the six-season level
  held until age 30 and walked down 0.5 WAR a season after it (floored at 0);
  plat_war, war_3y, il and gs_share 0; qo 0.
* EXTRAPOLATION: the training support box is [min, max] of age, war_y1 and
  war_tot over the final model's training rows. A row outside the box is
  CLIPPED to it (age clipped; the WAR path scaled down so war_y1 and war_tot
  fall inside) and FLAGGED. No tree is ever evaluated outside its support.
  Reported: the share outside support by population (prospect, pre-arb,
  arbitration), never by consensus FV level (docs/PROSPECT_ANCHOR_GATE.md).

ANCHOR CHECKS (descriptive, registered, never gated):

* EXTENSIONS: players in the pre-arb or arbitration phase on a multi-year
  extension (`trade_values.json` contract phase starting 'Ext.'), joined to
  the cached Spotrac salary by year. Free-agent season = 2027 + (6 - service
  years). Bought FA AAV = mean salary over contract seasons at or after it
  (rows with no bought FA season are dropped and counted). Ratio = bought FA
  AAV / xM$ AAV. Reported: median ratio and a player bootstrap 95 percent
  interval (B 4000, seed 20261019). Expected below 1 (a risk-and-control
  discount): 'consistent' if the upper bound is below 1, 'not consistent' if
  the lower bound is above 1, else 'inconclusive'.
* POSTINGS AND INTERNATIONAL PROFESSIONALS: the MLB deals with no MLB season
  in the three before the winter (section 3). xM$ needs an as-of WAR path;
  the store has no as-of translated MLB WAR path for these players (the
  overseas translation serves ERA and strikeout factors, not WAR), so the
  anchor is computed only for rows with such a path and otherwise reported as
  NOT MEASURABLE with the row count and the contracts' median AAV. Age-
  restricted bonus-pool signings are never in the signing table.

FAIR $: `fa_market.expected_rational_value_usd` on the same WAR path, at the
xM$ point term, the same $/WAR index and `value_framework`'s discount rate,
for everyone; prospects use the eFV path above. Reported descriptively by
population.

## 12. What never moves

Nothing served moves in XM_1: no page, no served data file other than the new
eval artifact `data/xm_eval.json`, no glossary entry, no flag. `fa_market.py`,
`fa_export.py` and `data/fa_gate2_eval.json` are untouched; Gate 2's served
model is the incumbent and stays the /fa/ price. `backtest.run_backtest` is
never run. The reserved eFV frames are never scored; no realized MLB statistic
is computed by consensus FV cell. XM_2 consumes the selected model.

## 13. Order of the read and crash protocol

1. Dry run of the whole reporting path on a fixture with nulls (a row with no
   path, a winter with no floor rows, an MLBTR row with no join, a player with
   no Spotrac row), output under the task's scratch directory.
2. Planted recovery (section 10), written to the artifact.
3. Development read, every candidate and comparator; the selection written to
   the artifact.
4. Holdout read, once; the pass rule and verdict written.
5. Counterfactual extension, anchors and Fair $ on the served model.

stdout and stderr of the real run are teed to the task directory before
anything else runs. An exception after scoring began stops the read with no
rerun and an OWNER_QUESTION.md.

## 14. Amendments

### 2026-10-22: the first read crashed in step 4; resumed once (owner answer XM1-Q1)

* WHAT HAPPENED. `python tools/xm_lab.py --read` started 2026-10-22 at
  00:34:53 EDT (04:34:53 UTC) in worktree wt/s200, code head `70864a33`, and
  ended at 00:35:57 EDT with exit 139; bash reported "Segmentation fault".
  Its stdout and stderr, teed to the task directory before the run, were
  empty: no Python traceback and no exception message. The artifact's
  `order` ended at `development`: steps 1 to 3 (fixture dry run, planted
  recovery, development read and selection) were written. No holdout
  prediction, metric, paired bound or verdict was written to any file or
  printed, and none was seen. Windows logged no application error for the
  process. The machine has recorded memory-access faults (bugchecks 0x7e and
  0x1e, code c0000005), and this interpreter has recorded native access
  violations in numpy fancy-index assignment inside long bootstrap loops in
  two other labs (`tools/efv_rank_objective_lab.py`,
  `tools/ba_tool_grade_lab.py`).
* THE RESUME RULE (owner answer XM1-Q1, "Resume once", 2026-10-22). Steps 4
  and 5 of section 13 run ONCE, by `python tools/xm_lab.py --resume-holdout`,
  in a fresh process, from the development block as persisted: the selection
  (a_incumbent) and the band methods are read from the artifact and never
  recomputed. Planted recovery, the development read and the selection are
  not rerun. The resume refuses if the artifact already holds a holdout
  block, if this document changed above this section, or if the rebuilt
  input counts differ from the persisted ones. Its stdout and stderr are
  teed to the task directory before it runs.
* THE CRASH FIX; no registered choice changes. The weight matrix of the
  section 9 player-clustered bootstrap is built by one bincount instead of an
  `np.add.at` fancy-index accumulation. The draws, B 4000 and seed 20261019
  are unchanged and the counts are exactly equal (pinned by a test; the
  fixture dry run is byte-identical before and after). faulthandler is on, so
  a native fault leaves a Python traceback.
* If the resume dies after scoring began, the read is VOID under section 9:
  no verdict, no registry claim, no further rerun, and an owner question.

## 15. Results

Read 2026-10-22: steps 1 to 3 by `--read`, steps 4 and 5 once by
`--resume-holdout` (section 14). Artifact `data/xm_eval.json`; plain-language
write-up `docs/xm/RESULTS.md`.

* Planted recovery: P1 censoring passed (Tobit RMSE 0.053 against least
  squares 0.059, 0.6 percent censored). P2a: incumbent 1.128 and hurdle 1.098
  times the oracle MAE, pass; GBM 1.179, FAIL against the 1.15 bar, so (c) is
  VOID. P2b permuted null: all three pass.
* Development 2018-2024 (n 893 MLB deals), log-total MAE: incumbent 0.742,
  hurdle 0.768, GBM 0.734 (VOID, not eligible), NULL 1 1.015, constant 1.141.
  Band methods: in-sample for (a) and (b); conformal for (c) (in-sample
  coverage 0.515). SELECTED: (a) the incumbent; no challenger is read.
* Holdout 2025 and 2026 (n 306 MLB deals, 260 players), read once:
  incumbent 0.736, NULL 1 0.899, constant 1.163. Incumbent against NULL 1:
  +0.163, one-sided 95 percent lower bound +0.092. P10-P90 coverage 0.853;
  years exact 0.765.
* VERDICT: INCUMBENT. Registry row `xm`: `provisional`,
  `provisional_kind` `inherits_parent_gate`. The site may use only the
  section 9 INCUMBENT words.
* MLB Trade Rumors, sticker basis: development 309 paired rows, MLBTR 0.453
  against the incumbent 0.832; holdout 92 paired rows, MLBTR 0.452 against
  0.712, MLBTR better with the lower bound of its improvement above 0. No
  claim against MLBTR is made.
* Counterfactual (2027 winter, descriptive): share outside the training
  support, prospects 0.614, pre-arbitration 0.060, arbitration 0.003.
  Extension anchor: median bought-FA AAV over xM$ AAV 1.034 (n 101, 95
  percent interval 0.813 to 1.352), inconclusive. Posting anchor: NOT
  MEASURABLE (48 rows, median AAV $3.112M).
