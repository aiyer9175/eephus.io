# xM$ downstream tests: XM_DOWNSTREAM (registered 2026-10-22)

Registration status: REGISTERED

**Registered, not read.** Task XM_4_DOWNSTREAM_TESTS, owner decisions XM-1 to
XM-4 (2026-10-19, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, section 'XM:
Expected Market $'). The owner asked where xM$ (Expected Market $) can improve
other metrics. This document registers five tests, A to E, before the lab
(`tools/xm_downstream_lab.py`), its test file, its artifact
(`data/_labs/xm_downstream/xm_downstream_eval.json`) or any number of any
test exists. Code citations are HEAD `91f4c551`; the anchor in brackets wins
over a line number.

What was looked at before writing this, all counts and never a price, error or
fit: the scored arbitration rows by season (`arb_dataset.scored_rows`, 1,069
rows, seasons 2022 to 2026); qualifying-offer acceptances by class year
(`data/qo_history.json`, 14 rows, 11 of them in class years 2017 to 2026) and
QO-flagged signings by class year (`storage.load_fa_signings`, 130 distinct names in
2015 to 2026); the count of contract entries on the cached Cot's club sheets
whose notes say 'signed extension' (249, by signing year); the FA destination
gate's primary frame size (1,080 scored signings, winters 2019 to 2026, from
its own published results); the column lists of `data/xm_players.json` and
`data/mlb_player_detail.json`.

## 1. What xM$ means here, and what never moves

xM$ is the market price model the XM_1 read left in place: its read stopped in
the holdout step (owner question XM1-Q1), its development selection was the
incumbent, and XM_2 serves `fa_market.MarketModel` dark as xM$
(`xm_export.py`, module docstring). Every test below therefore reads xM$ as
that model AS OF the winter of the row, refit exactly as Gate 2 refits it for a
test winter (section 2). Nothing here refits, re-weights or re-gates the
market model.

Nothing served moves under any verdict. No page, no served data file, no
glossary entry, no registry row, no flag. The only new data file is the lab
artifact under `data/_labs/` (which ships in neither deploy consumer).
`arb_model.py`, `arb_export.py`, `fa_destination.py`, `fa_market.py`,
`xm_export.py` and every served artifact are untouched. A passing test earns
an owner question (section 9), never a serve. `backtest.run_backtest` is never
run. Nothing is stratified by consensus FV level (docs/PROSPECT_ANCHOR_GATE.md);
no reserved eFV frame is read; no dark betting column is read.

## 2. The as-of xM$ engine (shared by A, B and C)

For winter W (class year W, contracts starting in season W):

* Training rows: `fa_market.enriched_signings(2015, 2026)` with class year
  below W. The model is built only when there are at least 100 of them (the
  Gate 2 fold rule [fa_backtest.py:830, in run_market_gate()]), so W runs from
  2017.
* Model: `fa_market.MarketModel(train, fa_market.dollars_per_war_by_winter(train))`
  with `supply_by_year[W] = fa_market._supply(class W signings, W)` (the class
  composition, known at the winter start, as Gate 2 sets it).
* WAR path: `fa_market.contract_war_path(hist, side, W, 10, age, curves,
  war_map, league, use_ml=False)` on `fa_projection.fitted_models(corpus, W - 1,
  use_def=fa_market.FA_PRICING_USE_DEF)`, hist the player's corpus rows for
  seasons W-1, W-2 and W-3, age anchored as `enriched_signings` anchors it.
  A player with no corpus row in those three seasons has no xM$ for W.
* Row: position from the StatsAPI people file of season W-1
  (`.cache/mlb_people/people_<W-1>.json`, primary position; a pitcher code
  resolved to SP or RP by the path's role; TWP prices as a hitter), qualifying
  offer False except in test B, player key `mlbam_<id>`.
* Output: `proj_aav_usd`, `proj_guarantee_usd` (total), `proj_years`.

## 3. Test A: arbitration (xM$ share as a feature)

**Question.** Does arb-year share x xM$ AAV, added to the arbitration model,
lower its out-of-sample error against the model as served? (MLB Trade Rumors
beats the served estimator 2.66x on MdAPE today, docs/ARBITRATION_GATE.md
section 14.)

**Frame.** `arb_dataset.scored_rows(build_panel()["rows"])` on the platform
frame (`arb_model.attach_frame`, FRAME "platform"), forward-chained by season
exactly as `arb_model.forward_chain` (deflator fit on train seasons only;
train on seasons before the test season, score the test season). Scored rows:
the current model's `served` prediction exists and the actual salary exists.

**Feature.** For a row of award season S and arbitration step k:
`xm_arb = log(max(share(k) x AAV, league_min(S)) / 1e6)`, AAV the as-of xM$
AAV for winter W = S (section 2). share: a 3-step chain (super_two not true)
1: 0.40, 2: 0.60, 3: 0.80; a 4-step chain (super_two true) 1: 0.25, 2: 0.40,
3: 0.60, 4: 0.80; any other step 0.80. A row with no as-of xM$ takes AAV =
league_min(S) and is counted.

**Candidate (AUG).** The champion's two stages (`fit_stage1` for arb 1,
`fit_stage2` for arb 2 to 4) with `CHAMPION_KEYS` plus `xm_arb`, the same ridge,
floor transform and smearing, refit per fold. The lab carries its own copy of
the two fit functions with a feature hook; on the real folds with no extra
feature it must reproduce `arb_model.forward_chain`'s `champion` predictions to
1e-6 relative, written to the artifact before any score, or the test is VOID.

**Comparators.** CURRENT: the served estimator per row (`served`: the champion
for arb 1, the banded multiplier for arb 2 to 4). AUG_PERM (null): AUG with
`xm_arb` permuted across rows within each (season, step) cell,
`numpy.random.default_rng(20261019)`, one draw, train and test alike. Reported:
the unaugmented champion, and the MLB Trade Rumors (Swartz) figure where
`arb_dataset.swartz_by_mlbam(rows, pool="repaired")` carries one.

**Metric.** PRIMARY: MAE in deflated dollars (each fold's deflator), pooled
over steps, on the rows where CURRENT, AUG and AUG_PERM all predict. Reported:
per step, MdAPE, and on the Swartz rows each estimator's MdAPE beside Swartz's
(nominal against nominal).

**Pass rule.** PASS iff (i) MAE(CURRENT) - MAE(AUG) has a one-sided 95 percent
lower bound above 0, and (ii) MAE(AUG_PERM) - MAE(AUG) has a lower bound above
0 (the gain is the feature's information, not the model structure). Otherwise
FAIL, with the clause that failed.

**Planted recovery (before the real read).** P-A1 SIGNAL: on the real design,
each scored row's salary is replaced by actual x exp(0.25 x z), z the row's
`xm_arb` standardized over all rows (arb 2 to 4 kept at or above 0.81 x prior
salary); the pass rule must PASS. P-A2 NULL: `xm_arb` replaced by independent
standard normal noise (seed 20261019) on the real labels; the pass rule must
not PASS. Either failure makes test A VOID.

## 4. Test B: qualifying-offer acceptance

**Question.** Does xM$ total against the QO amount predict who accepts a
qualifying offer better than the base rate?

**Frame.** Class years W 2017 to 2026 (section 2). Rows: every signing with
`qo` true in `storage.load_fa_signings(W)` (any deal), plus every
`fa_cba.qo_acceptances(W)` row not already among them, each joined to an MLBAM
id (a signing's own id; an acceptance by unique full-name match in
`people_<W-1>.json`, unmatched counted and dropped). Label: 1 if the player's
name is in that winter's acceptances, else 0. Rows with no as-of xM$ are
dropped and counted.

**Feature.** `x = log(xM$ total / qo_value(W))`, xM$ priced with the
qualifying offer attached (`qo` True), `fa_cba.qo_value(W)`.

**Candidate.** Logistic regression of the label on x with an intercept, fitted
by maximum likelihood (Newton, no penalty, 100 iterations at most),
forward-chained by winter: train on winters before Y, score Y, from the first Y
whose training rows hold at least one acceptance and one decline.

**Null.** BASE: the training winters' acceptance rate, per fold.

**Metric.** PRIMARY: Brier score on the scored rows. Reported: log loss, AUC,
and a leave-one-winter-out twin over all winters (context only, it trains on
later winters).

**Pass rule.** PASS iff Brier(BASE) - Brier(LOGIT) has a one-sided 95 percent
lower bound above 0. Otherwise FAIL.

**Planted recovery.** P-B1 SIGNAL: labels drawn as Bernoulli(logistic(a0 - 2.0
x)), a0 set so the mean probability equals the frame's acceptance rate, seed
20261019; must PASS. P-B2 NULL: real labels permuted within winter (seed
20261019); must not PASS. A P-B1 failure makes B VOID with the reason
'underpowered at this frame'; a P-B2 pass makes B VOID.

## 5. Test C: extension price

**Question.** On historical pre-arbitration and arbitration extensions, does
xM$ AAV for the free-agent years bought, times a fitted risk-and-control
discount, price the bought years better than a WAR-only rule?

**Frame.** The newest cached Cot's club sheet per club
(`tools/ingest_cots.newest_files`, `parse_sheet`; private research input,
attribution "Cot's Contracts (Baseball Prospectus)"). A row is a multi-year
contract one of whose notes contains 'signed extension'. Each row needs:

* the player's MLBAM id by unique full-name match in the StatsAPI people files
  (executives and unmatched names dropped, counted);
* S0, the contract's first season, and the signing date from the note;
* service at the start of S0: the sheet's 'ML service: Y.DDD' (stated as of the
  end of the 2025 season; checked on 2026 call-ups, who read 0.000) as Y +
  DDD / 172, minus one year for each season from S0 to 2025 in which the player
  appears in `arb_dataset.career_appearance_seasons()`, floored at 0;
* the free-agent season F = S0 + ceil(6 - service at S0); the row is kept iff
  service at S0 is below 6 and at least one guaranteed season is at or after F;
* the guaranteed salary by season from the per-year note ('23 :$4M',
  '25-29 :$18M annually'); a segment naming an option is not guaranteed;
  seasons after the contract's last season are dropped. A contract with no
  per-year note spreads its total evenly over its years (counted);
* LABEL: bought FA AAV = the mean salary over guaranteed seasons at or after F;
* as-of xM$ AAV for W = S0 (section 2); rows with S0 before 2017 or no as-of
  xM$ are dropped and counted. A contract signed before the end of season S0-1
  reads that whole season (counted and disclosed; a sensitivity drops them).

**Features.** ctrl = F - S0 (control seasons left at S0); war3 and plat (the
corpus WAR of seasons S0-3 to S0-1, and of S0-1).

**Candidate (XM).** log(bought AAV) = log(xM$ AAV) + a + b x ctrl (xM$ an
offset, the discount exp(a + b x ctrl) fitted by least squares on the
residual).

**Null (WAR).** log(bought AAV) = a + b x ctrl + c x war3 + d x plat, least
squares. Reported: a constant-and-ctrl rule, and XM with a free coefficient on
log(xM$ AAV).

**Protocol.** Forward-chained by S0: train on rows with S0 before the test
season, score it, from the first test season with at least 20 training rows.

**Metric.** PRIMARY: MAE of log bought AAV. Reported: median absolute percent
error, the fitted discount per ctrl value, the in-season-signing sensitivity.

**Pass rule.** PASS iff MAE(WAR) - MAE(XM) has a one-sided 95 percent lower
bound above 0. Otherwise FAIL.

**Planted recovery.** P-C1 SIGNAL: labels replaced by xM$ AAV x exp(-0.3 -
0.1 x ctrl + e), e normal sd 0.30, seed 20261019; must PASS. P-C2 NULL: labels
replaced by the WAR null fitted on all rows plus the same e; must not PASS.
Either failure makes C VOID.

## 6. Test D: FA destination, club-level xM$ demand

**Question.** Does a club-level xM$ demand term add accuracy to the FA
destination model as it would serve (arm N of docs/fa-2026-10/
FA_DESTINATION_GATE.md, fit_analog plus incumbent)?

**Frame.** The destination gate's primary frame, rebuilt by its own lab's
functions (`tools/fa_destination_lab.py`: `real_inputs`, `join_gate2`,
`build_frame` on the Gate 2 collection), scored winters and rows as that gate
scores them. Nothing in that lab or in `fa_destination.py` is edited.

**Feature.** For winter Y and club j: need_j = the sum of xM$ AAV over the
class Y signings whose `from_team` maps (`fa_destination.canonical_club`) to
j, xM$ AAV being Gate 2's forward-chained predicted AAV for that signing
(the collected tuple; the same refit as section 2); room_j =
threshold(Y) - the club's season Y-1 tax payroll (the club state the gate
reads; unknown payroll gives room 0, counted). demand_j = min(max(room_j, 0),
need_j) / 1e6, z-scored across the 30 clubs within the winter (population SD;
SD 0 gives 0). Every signing of winter Y reads the same 30 values.

**Arms.** N (as served): fit_analog, incumbent. NX: fit_analog, xm_demand,
incumbent. NX_PERM (null): NX with xm_demand permuted across clubs within each
winter by `numpy.random.default_rng(20261019 + Y).permutation(30)`, train and
test alike. All fitted by `fa_destination.fit_clogit` in the gate's forward
chain (xm_demand is not one of the penalized L terms).

**Metrics and pass rule (the gate's C3 form).** MRR and multinomial log loss
on the scored rows; one-sided p = (1 + draws with difference at most 0) /
2,001 over the gate's own 2,000 resamples (`bootstrap_draws`, seed 7), for MRR
NX minus N and for log loss N minus NX; Holm at 0.05 (the smaller p at or below
0.025, then the other at or below 0.05). PASS iff Holm rejects at least one
with the point difference favouring NX AND, for every metric rejected,
(M(NX_PERM) - M(N)) / (M(NX) - M(N)) < 0.60 (M the MRR or minus the log loss).

**Planted recovery.** P-D1 SIGNAL: the signed club of every member redrawn
from the conditional logit with N's all-winter coefficients plus 0.5 on
xm_demand, seed 20261019; must PASS. P-D2 NULL: the same with 0 on
xm_demand; must not PASS. Either failure makes D VOID.

## 7. Test E: Trade Machine sign check (descriptive, no pass rule)

For every row of `data/xm_players.json` with a market-rate surplus (`msur_xm`,
xM$ AAV carried by the $/WAR index minus expected salary over the priced
control seasons, discounted), joined by MLBAM id to the Trade Machine's MLB
price (`data/mlb_player_detail.json` `proj.surNpv`, the NPV of the controlled
seasons from 2027, raw dollars): the count where the two are both nonzero and
of opposite sign, the share, and the 15 largest absolute disagreements among
those, with both figures. Context: the same against `msur_fair` (Fair $ leg).
Descriptive only, for the owner; no claim, no serve.

## 8. Shared protocol

* Bootstrap for A, B and C: player-clustered (cluster = MLBAM id), B = 4,000,
  `numpy.random.default_rng(20261019)`; the one-sided 95 percent lower bound is
  the 5th percentile of the resampled paired improvement on identical rows.
  D uses its gate's resamples (section 6).
* Order of the read: (1) dry run of the whole reporting path on a synthetic
  fixture with nulls (a row with no xM$, a winter with no acceptance, a Cot's
  row with no per-year note, an MLBAM id with no Trade Machine price), output
  under the task's scratch directory; (2) the as-of xM$ engine and every
  reproduction check; (3) planted recovery for A to D, written to the artifact;
  (4) the real reads A, B, C, D, each once, each verdict written as read; (5) E.
* stdout and stderr of the real run are teed to the task directory before
  anything else runs. An exception after scoring began stops the read with no
  rerun and an OWNER_QUESTION.md.

## 9. Verdicts and owner questions

PASS, FAIL or VOID per test, with the numbers. A PASS earns an owner question
in the results (serve or not, and in what form); a FAIL or VOID is recorded as
a loss with the sentence of what the test could not show. No verdict here may
be described on the site; nothing is served.

## 10. Amendments

None.

## 11. Results

### 2026-10-22: the one read; A FAIL, B VOID (underpowered), C FAIL, D FAIL, E reported

Run once, 2026-10-22 01:29 to 01:30 local, worktree lane 202 (branch
`wt-XM_4_DOWNSTREAM_TESTS`), `python -u tools/xm_downstream_lab.py --read
--generated-at 2026-10-22` after the lab commit `47d31baa`; stdout and stderr
written to the task directory; exit 0, stderr empty. Before it: the fixture dry
run (`--dry-run`, every step written) and a frames-only crash check on the real
inputs (`--frames-only`, counts only, no planted run and no read). Artifact
`data/_labs/xm_downstream/xm_downstream_eval.json`, sha256
`48bde2d2cb316a17be5ac23015255cc896715aa25c9d1953d727caf7d1ce8293`, steps in
the registered order: engine_and_frames, A_reproduction, planted, A, B, C, D,
E. The working tree carried no other change after the run.

**Engine and reproductions.** The as-of engine's winter models reproduce Gate
2's collected predictions on all 1,199 tuples (max relative difference 0.0).
The lab's hook-free arbitration fits reproduce `arb_model.forward_chain`'s
champion on all 812 rows (max relative difference 0.0). The destination arm N
refit on every matched winter reproduces that gate's serving fit (fit_analog
0.8567, incumbent 1.7681) and its primary-frame N row (MRR 0.2717, log loss
3.2248). Engine prices: 1,230 priced, 8 with no history on the player's side.

**Planted recovery.** A: P-A1 passed (clause i bound +$140,217, clause ii
+$52,589), P-A2 did not pass (clause ii bound -$11,075). B: P-B1 was NOT
detected (Brier gain 0.0274, bound -0.0094, 13 planted acceptances on 89 scored
rows), P-B2 did not pass; B is VOID. C: P-C1 passed (bound +0.420 log), P-C2 did
not (bound -0.589). D: P-D1 passed (Holm rejects both, p 0.0005 each), P-D2 did
not (p 0.154 and 0.689).

**A, arbitration: FAIL (clause ii).** Frame 1,069 rows, 2 with no as-of xM$
(league minimum); scored 812 rows, 485 players, seasons 2023 to 2026. MAE in
deflated dollars: CURRENT (served) $757,490, AUG $605,108, AUG_PERM $588,968,
the unaugmented champion $587,299. Clause i, CURRENT minus AUG, +$152,382,
bound +$106,170 (passes). Clause ii, AUG_PERM minus AUG, -$16,140, bound
-$32,619 (fails). AUG against the unaugmented champion: -$17,809, bound
-$31,919. By step (MAE served / AUG / AUG_PERM): arb 1 (421) $542,017 /
$571,678 / $540,775; arb 2 (237) $890,971 / $537,990 / $541,288; arb 3 (154)
$1,141,123 / $799,789 / $794,094. Clause i's gain is structural: it is the
stage-2 model's gain over the banded multiplier at arb 2 and 3, which GATE A
already measured (docs/ARBITRATION_GATE.md section 15f, arb-2+ PASS on the
platform frame; switching the board to it is its own measured change under
15d), and the permuted twin keeps all of it. Reported: pooled MdAPE served
0.178, AUG 0.146, AUG_PERM 0.141, champion 0.138; on the 808 rows with a
repaired-pool Swartz figure, Swartz 0.077, served 0.178, AUG 0.145. Loss:
"arb-year share x xM$ AAV carried no information the arbitration model's own
features lack; with it the model priced awards no better than with the same
values shuffled".

**B, qualifying offers: VOID (underpowered at this frame).** Frame 99 QO rows,
class years 2017 to 2026, 11 accepted (one acceptance joined by name, one row
with no id); scored 89 rows, winters 2018 to 2026, 9 accepted. Brier: base
rate 0.0948, logistic 0.0920 (gain 0.0027, bound -0.0157); log loss 0.343 and
0.303; AUC 0.80. The fold slopes are all negative (-0.26 to -1.38 per log
ratio: the further xM$ total sits above the QO value, the less likely an
accept). Leave-one-winter-out context: Brier 0.1016 against 0.1006, AUC 0.78.
Because a planted slope of -2.0 was not detected on the same rows, no verdict
is read from these numbers. Loss: "the QO history (99 offers, 11 accepts) is
too small for this test to tell an acceptance signal from noise".

**C, extensions: FAIL.** Frame: 249 'signed extension' contracts on the Cot's
sheets; dropped 32 with no service line (executives and others), 54 at six
years of service or more at S0, 57 that buy no free-agent season, 10 starting
before 2017, 6 with no as-of xM$, 3 ambiguous and 2 unmatched names, 1 with no
span; kept 84 (26 signed before the end of season S0-1), scored 57, S0 2023 to
2027. Log MAE: XM 0.775, WAR 0.432, constant-and-ctrl 0.510, free coefficient
0.464; MdAPE XM 0.778, WAR 0.346. WAR minus XM -0.343, bound -0.468. Without
the in-season signings (34 scored): XM 0.725, WAR 0.440. Fitted discount on all
rows, exp(a + b x ctrl): 0.79 at one control season to 0.95 at six. Loss:
"xM$ AAV times a control discount priced the bought free-agent years of
pre-free-agency extensions worse than a rule on realized WAR and control
seasons".

**D, FA destination: FAIL.** 1,080 scored signings, winters 2019 to 2026.
N: MRR 0.2717, log loss 3.2248; NX: 0.2701, 3.2254; NX_PERM: 0.2699, 3.2254.
One-sided p, MRR 0.802, log loss 0.700; Holm rejects neither; the point
differences favour N. The xm_demand coefficient by fold runs from -0.072 to
+0.004. Loss: "club-level xM$ demand (payroll room against the market value of
departing free agents) added nothing to the destination model's Fit twin plus
incumbency".

**E, Trade Machine sign check (descriptive).** 830 rows of `xm_players.json`
with a market-rate surplus joined to a Trade Machine MLB price (224 with a
market-rate surplus have no `surNpv`). Opposite signs: 106 (12.8 percent), 88
with xM$ surplus positive and the Trade Machine's negative, 18 the reverse; the
Fair $ leg disagrees in sign on 82 (9.9 percent). The 15 largest absolute
disagreements, $M (market-rate surplus over control, Trade Machine surplus,
Fair $ surplus):

| player | club | control seasons | xM$ surplus | TM surplus | Fair $ surplus |
|---|---|---|---|---|---|
| Konnor Griffin | PIT | 8 | -3.8 | 135.9 | 375.8 |
| Mookie Betts | LAD | 6 | 63.9 | -71.2 | -20.9 |
| Max Fried | NYY | 6 | 67.0 | -36.4 | 4.4 |
| Samuel Basallo | BAL | 8 | -34.0 | 58.2 | 213.1 |
| Garrett Crochet | BOS | 5 | 43.8 | -37.3 | -12.7 |
| Aaron Judge | NYY | 5 | 22.8 | -30.7 | -75.7 |
| Colt Emerson | SEA | 7 | -51.3 | 1.7 | 96.1 |
| Pete Alonso | BAL | 4 | -15.4 | 36.7 | 30.9 |
| Kyle Bradish | BAL | 5 | 4.9 | -44.8 | 20.5 |
| Roman Anthony | BOS | 8 | -15.1 | 28.1 | 139.1 |
| Jarren Duran | BOS | 2 | -4.6 | 31.2 | 19.9 |
| Will Smith | LAD | 7 | 23.2 | -7.3 | 33.4 |
| Luis Lara | MIL | 6 | -4.0 | 25.1 | 95.9 |
| Kazuma Okamoto | TOR | 3 | 24.7 | -0.7 | 56.5 |
| Francisco Lindor | NYM | 5 | -0.3 | 18.6 | -22.3 |

Two patterns, described and not claimed: young players on long control
(Griffin, Basallo, Emerson, Anthony) read low on xM$, because a market model
fitted on free agents prices a short MLB record as a short MLB record; veterans
on long contracts (Betts, Fried, Crochet, Judge) read higher on xM$ than on the
Trade Machine, because xM$ keeps the market's own price for their production
while the Trade Machine prices projected WAR. The Fair $ leg agrees with the
Trade Machine's sign more often than xM$ does.

**Owner questions.** No test passed, so no serve question is asked. Nothing
served moved; no registry row, glossary entry or flag was added.
