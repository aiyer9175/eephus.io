# Master plan 2026-09-11: the fWAR label epoch, the driver re-test, two bust categories, and the betting program

Branch `efv-conviction-2026-08-08`. PLAN ONLY. It is written to the standard of
`docs/master-plan-2026-09-09-fangraphs-ewar-betting.md` and `docs/EFV_GATE_STANDARD.md`.
Every number comes from one of five read-only planning lanes run on 2026-09-11. Each lane's
record, scripts and outputs sit in the planning scratchpad under `plan3/<lane>/`, and each
number below is tagged with its lane:

- [R1] `R1_war_consumers`: the WAR-dependency census and the rebuild order.
- [R2] `R2_driver_ledger`: the eFV driver ledger and the re-test protocol.
- [R3] `R3_bust_pool`: the bust pool and the two bust categories.
- [R4] `R4_posted_lineups`: posted lineups for the betting model.
- [R5] `R5_betting_holistic`: the rest of the betting backlog.

No lane fitted a model, ran a gate, or related a betting feature to a game outcome. The only
numbers are label-only descriptives, counts, coverage and served-artifact reads. This plan
inherits the do-not-reopen checklist (`docs/master-plan-2026-08-19-holistic-audit.md`
section 2), the 2026-09-03 locked decisions, the 2026-09-09 FanGraphs-primary decision, and
the owner's 24 answers of 2026-09-11 (`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, section
ANSWERED). Where a lane default contradicts an owner answer, the answer wins, and section 0.2
says so.

**Status at commit (2026-09-11).** The 24 owner decisions O1 to O24 in section 6 are OPEN and
will be put to the owner in batches. Betting repair 2 (section 4.2) is half done: `26e9a177`
redirects `betting_ingest.STATUS_PATH` in the test fixture and makes the session guard restore
any locally-modified file a test overwrites. The golden-hash check for every other betting
sidecar is still owed.

---

## 0. The ask and the answer

### 0.1 What the owner asked (2026-09-11, verbatim)

> "we need to create a plan to audit all models & re-derive/re-test all drivers (eFV drivers,
> both active ones and previously NULL ones, but also any metric or driver across the site)
> based on our new WAR system (using eWAR/fWAR instead of bWAR for WAG, eFV, projections,
> surplus value, etc) - also, we should consider tweaking the eFV bust pool threshold to make
> it more accurate, maybe by including players who recorded negative MLB WAR? (even if they
> made it to the MLB, this doesnt mean they were a bust - maybe have 2 bust categories, one
> for prospects who never reached the MLB and one for prospects who recorded
> negative/mediocre WAR/were out of the MLB in a few years?) By doing all of this, we should
> be able to improve all of our models and metrics significantly and make the PROSPX module
> as pristine as possible. additionally, for the sports betting module, can we pull real
> lineups when they are posted before each game and have the model calculate based on this
> rather than on expected lineups? what else can we do to further improve the sports betting
> model holistically, including all models and metrics?"

### 0.2 The answer, in one paragraph

Yes to every part, with four corrections to the premise. (1) **The label.** Train every fitted
consumer on PUBLISHED FanGraphs WAR, taken from MLB's StatsAPI sabermetrics feed and frozen
per season. Rebuild everything once, at the close of the 2026 regular season, bundled with
the `RESOLVED_THROUGH` 2025 to 2026 advance. For hitters this label is genuinely new for the
first time: the change sd is 1.785 WAR, against 0.049 at the 2026-09-04 epoch [R1], and
almost all of it is fielding (correlation 0.802 with the fielding-part change [R2]). For
pitchers it moves less than the change already measured as a null (sd 0.831 against 1.435)
[R1]. (2) **The drivers.** The new label is the one legitimate reopen condition the record
names (2026-09-03 locked decision 6, do-not-reopen items 1 and 17). So every closed eFV
driver gets exactly ONE re-read, in one frozen registration, on the final label. The honest
prior is zero survivors: 0 of 48 arms and 0 of 177 in the 2026-09-04 families so far [R2].
The payoff is coherence and a permanent close, not a promised accuracy gain. The last basis
epoch measured a null, and no copy may claim otherwise. (3) **The bust pool.** The served
P(bust) ALREADY counts MLB players with negative or low WAR as busts (six-season sum under
3.0). The real defect is elsewhere: 203 hitter and 192 pitcher never-MLB rows are labelled a
resolved 0.0 at full weight while still playing affiliated ball [R3]. Fix that inside the
epoch. Put the owner's two categories in the ODDS layer, where they sum to the served
number, and leave the E[WAR] regression target alone. (4) **Betting.** Posted lineups can be
pulled for free today [R4]. But the served prices do not use a lineup at all (they use a
season roster rollup), and the board is built at 03:10 ET, before any card posts [R4]. So
lineups need a dark intraday capture now, a disclosure rebuild, and a pre-registered gate
whose first honest look is 2027. The largest betting lever is not a feature. The pricer
that serves is not the pricer the honest gate grades: 25.3% of served games sit outside 0.4
to 0.6, against 2.7% for the graded pricer [R5]. That comes first, then the close job that
has never run, the third of nightly vintages that are missing, and a coefficient fit on 610
rows at r2 0.003. Eight seasons of pre-2026 play-by-play can fix that last one without
touching a 2026 clock [R5].

### 0.3 Disagreements between the lanes, resolved

| # | Question | Lanes | Resolution |
|---|---|---|---|
| X1 | Which label trains eFV | R1: published fWAR, frozen per season. R2 OD-1: the served eWAR v3 as frozen at W1.4, with fWAR as a zero-weight sensitivity | **Published fWAR.** R2's own reason is that eFV is E[served WAR], and under R1's display default the served WAR at the flip IS published fWAR with attribution (O5), so the two coincide. The eWAR v3 replica equals published fWAR for hitters in every component 2011-2025, because it consumes the feed's fielding, UBR and wGDP. For pitchers it fails RAR in all 16 seasons while the feed is exact [R1]. So the label no longer waits on IFFB, the FIP park factor or stints. R2's P0 preconditions (finish W1.1, W1.2 and W1.3 before the freeze) and OD-2 (split sides) dissolve. Any W1.3 departure reaches a label only at the next epoch |
| X2 | When `RESOLVED_THROUGH` advances | R1: bundle 2025 to 2026 into this epoch at the 2026 season close. R2 and the 09-09 plan: an early-2027 advance | **Bundle (O2 default).** It is the same event. Doing it in October rebuilds every fitted artifact once instead of twice in about three months, and one re-sweep answers both reopen conditions [R1]. Attribution survives only through the arms of section 1.4 |
| X3 | Does betting read WAR | R2 and R4: zero readers. R1 and R5: two readers | **Two readers.** `star_out` (5c, dark) ranks stars by `vets[].warY1Champ`, and the served Futures board prices win totals from projected team WAR (`proj_export.py:1506-1520`) [R1, R5]. `lineup_strength` reads `vets[].woba[0]`, which a projections retrain can also move [R1, R4]. The run model itself reads no WAR, so no closed betting lane reopens. R4's 5j text must drop its "ZERO WAR readers" sentence before it is committed |
| X4 | Model class (`xfv_model_class_readjudication`) | R2 OD-6: stays closed | **Its own registry text sets the reopen condition as "the LABEL POOL (RESOLVED_THROUGH 2026)".** If O2 bundles the advance, the class reopens by its own pre-commitment, once, as its own registration after Z1. The MAE-basis serving angle it pre-registered is the only new angle. If O2 is refused, it stays closed |
| X5 | Holm structure | R1: the deprecated arms as ONE Holm family. R2: four add families with a 0.05 budget plus a removal family | **R2's structure** (section 2.3). It is a finer partition of the same budget and puts alpha where a mechanism exists |
| X6 | Pitcher arms | R1: secondary, expected null. R2: an unpaid debt with a real mechanism | **Both.** Pitchers are in the re-sweep because decision 6 of 2026-09-03 was never executed for the closed pitcher arms [R2]. The mechanism is real: bWAR is runs-allowed, fWAR is FIP, and starter careers gain +0.771 WAR [R2]. The registration states the expected-null prior, because the fWAR-vs-eWAR-v2 move is smaller than the one already measured null [R1] |
| X7 | Bust categories and the training target | R2 OD-3: no change to the ridge target. R3: keep the target, but fix never-MLB resolution (Arm R) as a label change | **Compatible.** The target stays summed six-season WAR with negatives kept. Arm R changes which rows count as resolved, so it is a label-definition change. It rides the epoch as an arm, and Z1 runs on whichever label ships |
| X8 | Arm R's affiliation window | R3 wrote "no line in RESOLVED_THROUGH and RESOLVED_THROUGH+1" with RT at 2025 | At RT 2026 in October 2026, RT+1 is unobservable. **Restated:** no affiliated line in either of the two latest seasons with MiLB data on disk at the build (2025 and 2026 at this epoch). The age and last-list clauses key off RT as written |
| X9 | Section letters | R4 calls posted lineups 5j. R5 calls the run-environment family 5j | **Posted lineups = 5j** (the owner's ask). **Run environment = 5k.** The as-served replay = 7e-D (it joins the 7e Holm family). The joint score kernel = 7i |
| X10 | 5e and postseason | R5 default: exclude postseason | **Owner answered 2026-09-11 (item 8): COUNT POSTSEASON**, amended under 5e's correction rule before its look. R5's default is withdrawn |
| X11 | Runline tie split | R5 default: fold into N2, do not flip alone | **Owner answered (item 4): reprice now.** The flip lands as answered. N2 must then beat the repriced incumbent on the margin, runline and total |
| X12 | WAG unification timing | R1: Z2 after the epoch | **Owner answered (item 14b): flip `WAG_UNIFIED` NOW.** Z2 becomes the refit of the unified baseline E[WAR given FV, reached, exposure] on the final label, plus the realized-PIT gate. R3's split supplies the "reached" leg |
| X13 | eWAR cadence (D11) | R1 default: monthly read, completed seasons frozen | **Owner answered (item 10): NIGHTLY.** Under published fWAR the nightly re-solves nothing, since there is no per-role centring constant. The in-progress season's display cell refreshes nightly, completed seasons stay frozen at their vintage, and fitted consumers re-read only at a label epoch |
| X14 | Hitter rows below zero | R2: 323 hit / 303 pit. R3: 328 / 306 | Different denominators: R2 counts rows resolvable to an MLBAM id (842 / 982), R3 counts every debuted matrix row (851 / 991). Quote each with its n |
| X15 | "Bust band" population | R2: 522 of 842 hitters. R3: 277 of 468 | Different frames: R2 covers all debuted rows with censored labels, R3 only resolved debuted rows. BUST2 uses R3's resolved frame |
| X16 | B3 level blend in Z1 | R1: may ride in its C3-repowered shape. R2: its own reopen shape is unmet | **Not in Z1.** No C3-repowered null-resolution shape exists on disk |

---

## 1. The WAR epoch

### 1.1 The label source, per consumer

Sources: **S1** published fWAR from the StatsAPI sabermetrics feed, frozen per season.
**S2** the eWAR v3 replica (`fwar_frame.py`), used as the display builder once pitchers pass.
**S3** v3 plus the W1.3 arms, display only in this program. **KEEP** means no change. The
full census is in R1 sections 3.1 to 3.7: 99 seam files, 22 facade importers, 23
`FROM career_war` readers, and 128 of 310 registry rows naming WAR, 27 of them deprecated
[R1].

| Consumer family | Today | Source | Step |
|---|---|---|---|
| `war_source` seam (`PROVIDERS` has no `fwar`, `war_source.py:109,112`) | eWAR v2 with bWAR fallback | add provider `fwar` (servable, not default), then flip the default | E3, D |
| `career_war` (2,673 rows: 2,538 `ewar_v2`, 135 `bbref`) | mixed | S1 via the rebase tool with a provider parameter | C |
| eFV matrices, model, score, ungraded, reliability, backgrade | career_war | S1 (rides) | F, P |
| Pooled outcome curve (grade map) | eWAR label shrunk to a Clemens fWAR prior | S1: prior and label share one currency for the first time | I |
| Empirical anchors, `survivor_expected_war`, `expected_surplus_usd`, `FV_WAR_ANCHORS` mirror | 50/50 our label with the Edwards fWAR reference | S1. Re-apply the sub-45 knots every time `--fit` runs | J |
| `p_bucket_given_fv`, `fv_to_prime_war`, `published_star_odds` | Clemens tables (fWAR) | KEEP the tables. Measure and publish k(FV) and prime WAR (Z3) | J, Z3 |
| Clemens yaml ($/WAR kernel, star definition 4.0) | fWAR | KEEP. Add `war_basis: fwar` | J |
| Draft slot curve, QO pick tax | eWAR v2 (2005-2010 on bWAR, 4.3% of cohort WAR mass) | S1, plus the pre-2011 feed per O4 | K |
| WAR/PA+, WAR/IP+ vintages and the 3yr columns (eval still declares bWAR, F-C7-3) | eWAR v2 served | S1 | L |
| Projections corpus, `proj_ml`, aging curves, F-REALWAR, FA Gate 1 (`fa_corpus.pkl` is 40.0% hit / 35.6% pit bWAR under an `ewar_v2` stamp) | mixed | S1, plus the pre-2011 feed per O4. F-DEF on the feed's fielding and positional runs rides as an arm (owner answer 19) | M |
| Star label, `star_label_view`, `star_odds_model` | career_war | S1 | N |
| Arb spine (2008-2010 bWAR, 14.7% of player-seasons), `arb_model` | eWAR v2 | S1, plus O4 | S |
| FA market, rational value, class, trade values, trade lookup | projections and kernel | rides | R, S |
| WAG (unified per owner answer 14b), farm grades, `tbs_farm`, `org_sur_plus` | anchors plus realized WAR | S1. The Z2 baseline refit follows the epoch | J, O, Z2 |
| GRPO (reward = `career_war`) | eWAR v2 | S1, retrained only after its 2026-09-18 forward read | after N |
| Display: player export, hitter/starter/bullpen boards, PAL | eWAR v2 plus a bWAR tick | S1 with attribution, eWAR v2 as the comparison tick (O5). S2 once pitchers pass | S |
| HoF (`hof_data.WAR_PROVIDER = "bwar"`) | bWAR, pinned by design | KEEP bWAR: neither the feed nor fWAR reaches 1871 | none |
| DEM+, betting 5g `team_fld_runs` | already published fWAR components | KEEP | none |
| `eta_backtest`, `advancement_pace`, name and identity joins | debut year and identity only | KEEP (basis-invariant) | none |
| HEM+/SEM+/REM+ | forward wOBA and RA9 targets, not WAR | constants from `league_constants` only; no label re-test | none |
| Betting `star_out` (5c), Futures board | projected WAR | moves with step M; see section 1.5 | M |

**Why S1 and not the replica, stated once.** Published fWAR is exact. C6 matched it to the FG
leaderboard at 0.0000 on 2011 and 2025, it joins at 100.0% on MLBAM in every season
2011-2025, and it is cached for both sides 2011-2026 [R1]. It adopts every FanGraphs
convention wholesale: the 57/43 replacement split, the RPW closed form, FG's league pool and
ladder, and Statcast fielding with framing inside. So D4, D5, D6 and D8 are settled for the
LABEL by the choice of source and stay open only for the eWAR v3 display [R1]. It also makes
the five FanGraphs tables coherent with our label for the first time. Star-season
disagreement drops from 37.8% to 0, and $/WAR tier disagreement from 9.76% to 0, by
construction. That is coherence, not accuracy [R1].

### 1.2 What moves (label-only descriptives, no fit)

| Quantity | Hitters | Pitchers | Lane |
|---|---|---|---|
| Resolved rows, bWAR to eWAR v2 (the 09-04 epoch, NULL) | n 459, r 1.0000, sd(d) 0.049, 0 rows over 1 WAR | n 527, r 0.9534, sd(d) 1.435, 194 rows | R1 |
| Resolved rows, eWAR v2 to fWAR (proposed) | r 0.9716, mean -0.224, sd(d) 1.785, 164 rows over 1 WAR (label sd 7.47) | r 0.9850, mean +0.113, sd(d) 0.831, 81 rows | R1 |
| New label variance (1 - r^2) | 0.056 (was 0.000) | 0.030 (the null-measured move was 0.091) | R1 |
| All debuted rows, Spearman eWAR v2 vs fWAR | 0.9402, mean abs 1.117 WAR, 302 of 842 move 1+ WAR | 0.9404, mean abs 0.548; bWAR vs fWAR 0.7959 | R2 |
| Where the hitter move lives | fielding: cross-frame window r 0.624, change sd 1.319 WAR, corr with total change 0.802. Positional 0.971, baserunning 0.912 | starter careers (90+ IP per pitched season, n 131) gain +0.771 and carry 58% of the squared change; the other 839 move -0.024 | R2 |
| Clemens bucket-band crossings | 112 of 842 (13.3%) | 67 of 982 (6.8%) | R1 |
| Implied 5-grade through the shipped pooled curve | 288 change (34.2%), 119 move 2+ grades, almost all in FV 20-40 | 282 (28.7%), 117 move 2+ | R1 |
| Clemens star label (2+ window seasons of 4+ WAR) | 60 to 48: 21 lose, 9 gain | 20 to 24: 1 loses, 5 gain | R1, R2 |
| Label at or below 0 | 326 to 315 (45 leave, 34 enter) | 309 to 328 (45 leave, 64 enter) | R1 |
| Level shift per player-season 2011-2025 (the 57/43 split) | -0.021; batting sums about 589 vs 570 per season | +0.025; pitching about 410 vs 430 | R1 |
| Gap to fWAR by era | mean abs 0.21-0.28 through 2021, 0.34-0.36 in 2022-2025 | pitcher eWAR v2 already r 0.968 | R1 |

Busts (never reached MLB) carry label 0 on every basis. They are 1,052 of 1,903 hitter matrix
rows, so the never-debuted half of the pooled curve's pool does not depend on the basis [R1].

### 1.3 Preconditions (nothing served moves)

| # | Item | Why it must come first | Lane |
|---|---|---|---|
| E1 | Owner decisions O1 to O13 (section 6) | every later step reads them | R1 |
| E2 | **Identity repair.** 13 label players with 50 window seasons carry `career_war` WAR where the bound MLBAM id has no feed row. Example: `carlos_martinez` is bound to 830052 but carries 2013-2018 seasons worth 15.45 WAR. Also the 9 + 9 debuted rows with no id and the 135 `bbref` rows. Add a tripwire test: every nonzero window season has a feed row under its bound id | an MLBAM-keyed label would zero these rows, while today's label carries another man's WAR | R1 |
| E3 | Frozen per-season fWAR vintage artifact (with `fetched_at`), a pitching loader in `saber_feed`, provider `fwar` in `war_source` (servable, not default; stint apportionment reuses `_ewar_frame`'s PA and IPouts split), and a rebase tool with a provider parameter and one receipt schema. The pre-2011 cache per O4 (22 calls, no credits; the first call is also the pre-2011 pitching probe) | C, D, K, M and S all read it | R1 |
| E4 | Pre-register `docs/efv-2026-09-1X/FWAR_LABEL_EPOCH_GATE.md`, committed alone. Clauses (a)-(h) of `EWAR_LABEL_EPOCH_GATE.md` verbatim, plus: (i) the attribution arms of 1.4; (j) the `star_out` handling; (k) the Z1 registration pointer; (l) "copy may never claim an accuracy gain from the basis" | clause (f) attribution is otherwise lost | R1 |
| E5 | 5c's look recorded (~2026-09-17) and GRPO's first forward read taken (2026-09-18), or amendments filed under their own rules before those looks | step M changes `star_out`'s and `lineup_strength`'s inputs; retraining GRPO mid-gate changes the gated object | R1, R2, R5 |
| E6 | 2026 regular season ended (2026-09-27) and the D9 freeze fetch taken (O3) | a completed season freezes cleanly, and RT can advance in the same rebuild | R1 |
| E7 | An independent label rebuild that matches the new matrices on at least 99% of debuted rows. `label_shift_descriptive.py` reads 837/842 and 972/982 on v2 and is the template | the label must be verified before any read | R2 |
| E8 | The owner's 2026-09-11 answers that move served numbers have landed, each in its own epoch with its fingerprint term (WAG_UNIFIED, the F10-01 re-point, wOBA 2015-2020, Ohtani on the starter board, the A's park) | step A's snapshot must be taken after them, or clause (f) attributes their movement to the basis | this plan |

### 1.4 What rides the epoch, and the attribution design

The 2026-09-03 routing rule stands: any served-number change in the same rebuild must be a
pre-registered ARM the lab can attribute, or it waits [R1]. The matrices are the incumbent
**E0**, the full candidate **E\***, and one leave-one-out arm per factor (E\* with that
factor reverted). That is 2 + k matrices per side, not a full factorial.

| Factor | Kind | Ship rule |
|---|---|---|
| Basis: published fWAR | owner decision (O1) | ships by decision; measured, never claimed as accuracy |
| `RESOLVED_THROUGH` 2025 to 2026 (plus `build_star_odds_artifacts._RESOLVED_THROUGH`) | the standing clock (O2) | ships by decision; measured |
| Arm R, never-MLB resolution (section 3) | label-definition candidate | ships only if its own clauses pass on its own arm |
| A1 service-aligned window, A2 neutral MiLB imputation (flags off since 2026-09-04; no arm matrices on disk) | label-definition candidates owed by 09-04 locked decision 1 | same rule as Arm R, per O7 |
| F-DEF on the feed's fielding and positional runs | projections-only arm, inside step M | Gate 1 on the projections bundle (owner answer 19: "in the WAR epoch") |

**Not allowed to ride:** any W1.3 departure, any lambda or correction-family move, C-7's
grade-seam affine, the star-odds measured-rates switch (09-03 decision 7), BUST2 Arm S, and
any served-feature removal from Z1. Each gets its own later epoch [R1, R3].

### 1.5 The rebuild, each fitted artifact exactly once, in `WAR_BASIS_RUNBOOK.md` order

The runbook's rules are load-bearing and unchanged. Floors come before deltas, the curve
before the anchors, and the retrain before the rebuild passes. There are two rebuild passes
because of the one-run lag. Margins come LAST. One code commit carries the default flip, the
epoch bump and the `label=` fingerprint term. `prospects.db` is written only by step C and
the box's mirror of C [R1].

| Step | What | fWAR-epoch specifics |
|---|---|---|
| A | pre-epoch snapshot | also snapshot `data/ewar.json` and the frozen fWAR vintage |
| B | `build_ewar.py` | **SKIPPED.** eWAR v2 retires to a frozen comparison provider, like `bwar` |
| C | rebase `career_war` | to `fwar` through the E3 tool; dry-run receipt first; box mirror |
| D + U | flip `DEFAULT_PROVIDER` to `fwar`; bump `BOARD_RANK_BASIS_EPOCH`; fingerprint `label=fwar@<vintage id>` | ONE commit. Deploy so D never lands on the box without C (the 2026-09-04 nightly pre-empted the epoch and wrote a mixed basis) |
| E | delete `fa_corpus.pkl`, `fa_fits_*`, `proj_ml_frame_*` | keep `.cache/war_daily` |
| F | `efv_dataset.py` / `efv_model.py`, both sides | plus the arm matrices of 1.4 |
| G | `efv_mde_lab.py mde 2000`; `efv_power_lab.py all 2000` THEN `partb` | order is load-bearing: `all` erases `partb_floors` |
| H | the epoch lab (a copy of `tools/efv_ewar_label_epoch_lab.py`) | its twin permutes fWAR-minus-eWAR deltas within season x side; re-run after P |
| I | `tools/fv_outcome_curve_pooled.py` | prior and label in one currency |
| J | `value_framework.py --fit`, then RE-APPLY the sub-45 knots; capture `prospx_current`; sync `FV_WAR_ANCHORS`; publish k(FV) | `--fit` silently reverts the knots to one 0.19 constant |
| K | `tools/fit_draft_slot_curve.py` | on `fwar`; pre-2011 per O4 |
| L | `tools/war_rate_plus_lab.py` | fix `conventions.war_source` (F-C7-3) |
| M | `tools/train_proj_models.py --final` | corpus on `fwar`; the F-DEF arm; four pins move together (schema length, train_hash, ml_config gate, star_blend h2 = 0) |
| N | `python -m tools.build_star_odds_artifacts` | star label on fWAR; refit `star_odds_model` |
| O | `run_monthly.py --rebuild-only`, pass 1 | |
| P | `efv_export.py --all --eval` | production output for the golden |
| Q | `source_backtest.py` | the consensus vintage A/B re-scores here against its unchanged 0.0068 bar; the C1-C4 confirmatory read, if O2 bundles RT |
| R | `run_monthly.py --rebuild-only`, pass 2 (a third if any stamp is pre-epoch) | |
| S | FA, arb, hitter/starter/bullpen, player, PAL exports | arb spine via `provider=` |
| T | `build_site.py` | after X's copy is in |
| V | golden restamp from P, outside pytest | cause "fWAR label epoch" |
| W | registry rows (the 128 WAR rows) and `tools/gen_audit_docs.py` | the `ewar` row demoted to comparison |
| X | copy sweep and `copy_lint --check` | 51 artifacts carry 223 bWAR mentions; `fa_backtest.py:375`; the Clemens `war_basis` key; the census sentence "betting has zero WAR readers" |
| Y | `tools/run_suite.py --out suite.json`, chunked | never concurrent with a lab |
| Z | margins re-read, then gate part 9 | Holm across the registered cells |

**The box** pulls D + U, backs up its DB, runs C, deletes the E caches and receives the
committed artifacts (frozen vintage, pooled curve, slot curve, war_rate evals, fitted
framework, `prospx_current.yaml`, `proj_lgbm`). Its first nightly then does O through T [R1].

**Betting touch points of step M** [R1, R5]. Vintages are first-write-wins, so captured
`star_out` rows keep their values, but every post-epoch vintage ranks stars on a different
WAR. Stamp the projections build in `star_out`'s `basis` string. The Futures board moves
with the projected team WAR during the postseason; publish a one-line changelog (O12).

### 1.6 After the epoch (separate registrations; none changes a label)

- **Z1** the driver re-test (section 2).
- **Z1b** the model-class re-adjudication, only if O2 bundles RT (X4).
- **Z1c** the pitcher-stuff first fold, opened by its own RT clock (item 8), under its own
  registration.
- **Z2** the WAG baseline E[WAR given FV, reached, exposure] refit on the final label, plus
  the realized-PIT gate with its within-(FV tier, exposure decile) zero-information control.
- **Z3** the valuation-chain reconciliation: k(FV) measured (0.35-0.65 today, F07),
  `fv_to_prime_war` measured through `tools/efv_peak_war_lab.py`, and the `public_reference`
  blend weight now comparable in one currency.
- **Z4** the eWAR v3 W1.3 departures, display only. A passer reaches the label at the 2027
  epoch.
- Owed re-reads on the new label: the age-ramp serve-rule gate (09-03 decision 4), the two
  `INJURY_PENALTY_SIDES` cells (v2: pit rho -0.1664, hit +0.0651) re-read and not re-tuned,
  the role dial's blast radius, and the `pwoba` re-gate after 2026-11-15 on the new-label
  projections bundle [R2].
- Refits and re-reads of every non-eFV WAR consumer in R2 section 4 (`fa_projection`
  Marcel with the `def_rate` repair, aging curves, FA market Gate 2, ARBITRATION_GATE, slot
  curve, `team_win_projections` under the 57/43 convention, trade machine, farm grades,
  `prospect_path`, `ifa_step_prior`, `xfv_provisional_prior`, `xfv_stale_anchor`, source
  and claim instruments, draft source weights) [R2].
- **Cadence afterwards** (owner answer 10, reconciled in X13): nightly for the in-progress
  season's display cell, completed seasons frozen, re-freeze only at a label epoch. The next
  label epoch is the 2027 season close.

---

## 2. The driver re-test program (Z1)

### 2.1 Registration

One file, `docs/efv-<date>/LABEL_V3_DRIVER_RETEST_GATE.md`, committed ALONE with an empty
Results section before any new-label floor is read [R2]. Its first paragraph suspends
CONVICTION_PROGRAM stop clause 1 ("no re-run of any of the 39 in any costume") for this
registration only.

**Blocking preconditions** [R2]:
- **P1 label freeze.** A named build in the `label=` term, a per-side coverage receipt, and
  E7 passed.
- **P2 floors first.** `python tools/efv_driver_lab.py floor 2000` and `auc 2000` on the new
  matrices. The eWAR v2 floors (rho 0.0170 hit / 0.0121 pit) adjudicate nothing here.
- **P3 parity.** The driver lab reproduces the new `xfv_eval*.json` bit-exact (the A0 check).
- **P4 input pinning.** sha256 of both matrices, the floors files and `efv_model.py`,
  recorded at start and verified at end, with the nightly idle. A mismatch voids the run.
- **P5 a derived arm list.** Extend `tools/efv_arm_ledger.py` to emit every distinct add
  column from the loss-ledger artifacts, including the 4-fold era and the 09-04 families.
  Dedupe by column definition, apply the mechanism rule and the exclusions mechanically,
  and commit the list with the registration.

**Engineering first** (effort S to M) [R2]: the `retest` mode in `tools/efv_driver_lab.py`,
which ports the 4-fold-era arms with bit-parity; and an `alpha` argument for `holm_family`,
with a test (it hardcodes 0.05 today).

### 2.2 Mechanism rule (frozen before any read)

A component is re-priced if its window value correlates under 0.90 across frames AND its
change sd is at least 0.5 WAR [R2]. For hitters that is fielding only (0.624, 1.319 WAR).
The positional arms stay in the hitter mechanism family because item 17's refutation record
names them, and the registration says so. For pitchers it is strikeout/walk/home-run skill
(runs-allowed to FIP) and starter-vs-reliever career shape.

### 2.3 Families, alpha and Holm (O8)

| Family | Content | Alpha | Arms / reads |
|---|---|---|---|
| H-MECH | `tool_field`, `pos_prem`, the D-Tool proxy, `field x pos_prem`, `tool_throw` alone (never measured; 717 of 845 now covered), three mean-z tool composites, `prospect_def_value`, the Defense+ prior proxy, the p_hold base rate, bmi x mid-position. **This is the "one registered attempt" of item 17** | 0.025 | 12 |
| P-MECH | `tool_cmd`, `tool_sl`, `tool_ch`, `era_rel`, `starter_shape`, `arsenal_depth`, `sits_mid`, `tops`, `rpm_fb`, `relief_flag`, `pit_peak_bb_rel` | 0.015 | 11 |
| H-NOMECH | every other distinct add column gated on the flagship ridge on an old label and not killed for a label-independent reason, plus the 09-04 volume, age-interaction and health families in their original scopes (O8, R2 OD-7) | 0.005 | about 131 reads |
| P-NOMECH | the same, pitcher side | 0.005 | about 84 reads |
| ABL (removal) | drop tests on 21 served features. `fv` dropped per side as the LIVENESS control: if dropping `fv` does not resolve as harmful, the instrument is dead and the run is BLOCKED | 0.05, for removal only | 21 + 2 |

Holm is a one-sided normal approximation within each family, sized jointly: both legs of
every arm count in m. At alpha 0.025 over 24 legs the step-1 z is 3.08, about 1.9x the
one-sided floor, so the 2x repeat bar is the binding bar in H-MECH. In the no-mechanism
families Holm binds harder, at a step-1 z of about 4.1 [R2].

### 2.4 Identical rows, instrument, bars

- **Identical rows** [R2]. Each arm runs on the frame and scope it was registered on. That
  is the 11-fold pair-weighted basis (SCORED_YEARS 2014-2024) for D-1, the C program and the
  4-fold-era arms (the retired 4-fold basis is not reproduced, because it adjudicates
  nothing); the six-fold 2019-2024 frame for the D-2 `tools_json` arms; and the original
  full, readable and debuted scopes for the 09-04 families. Baseline and candidate are
  scored on identical rows in every draw. Column definitions and imputation postures are
  copied verbatim. The reserved 2025 base-year cohort stays out of the frame.
- **Instrument.** E_refit (the lab's only estimator, named on every claim), B = 2000 paired
  bootstrap with the ridge and consensus OLS refit on each draw, a 200-draw permutation null
  per arm, a row-permuted zero-information twin, and three N(0,1) noise arms for the floor.
  Seed 20260807 (permutation stream seed + 7), noise seeds 0/1/2.
- **An arm passes only if all of these hold:** rho delta at least 2x its own floor (every arm
  is a registered repeat); positive on block-rho; no contributor-AUC veto; survives Holm in
  its family; beats its twin by more than the noise band; wins at least 7 of 11 folds (4 of 6
  on the six-fold frame); and stays inside the D-1 live-robustness limits [R2].
- **Attribution control** for passers only: re-run on the same rows with the OLD label. The
  pass is attributed to the label only if the old-label delta stays inside its floor.
- **Serving a passer** (O9): provisional, in its own grade-basis epoch, with no accuracy
  copy. Its confirmation on the reserved 2025 fold at the 2028 run is pre-registered, and a
  failed confirmation removes it automatically.

### 2.5 Compute budget and process

Measured cost per arm: 45 to 66 s on the 11-fold frame at B = 2000 with 200 permutations (the
26-arm D-1 run took 1,456 s), 28 to 33 s on the six-fold frame (641 s for 13 arms), and 739 s
for `auc 2000` [R2]. The core program is about 84 reads and roughly 85 minutes plus floors.
The full program, including the 09-04 families, is about 260 reads and roughly 4.5 hours
[R2]. Run one lab process at a time and never alongside the suite: `conftest.py` reverts
dirtied tracked files, and the single-process suite crashes on memory. The chunked suite
runs before the registration commit and after the results commit. No network, no credits.

### 2.6 Kill rules [R2]

1. **Frozen list.** Nothing may be added after the registration commit.
2. **One read per arm.** No friendlier frame, estimator or seed, and no smoke number cited.
3. **No second family** over the same columns if everything nulls.
4. **Uninformative family.** If its twins score at least as well as its best candidate,
   nothing in it is promoted.
5. **Dead instrument.** If the `fv` drop control fails, the run is BLOCKED.
6. **Program close.** If nothing passes, record the frontier as RE-CLOSED on label build X,
   rewrite do-not-reopen items 1, 8 and 17 with the date, and allow no driver re-test until
   either the 2027 RT advance or an owner-registered label DEFINITION change that moves the
   debuted label more than this one did (Spearman under 0.99 against the frozen label on
   either side).
7. **Stale inputs** (P4) void the run.
8. **Denominator published.** The arm ledger is regenerated with this registration as a new
   lane.

**The pre-registered expectation.** Zero survivors. 5.6% new hitter label variance is small
against floors of about 0.016-0.019 [R1]. A null is a result: it closes item 17 permanently
on existing columns. MiLB SDR, if Will's data ever arrives, is a new data source under its
own registration, not a fourth look.

### 2.7 Reopen status of every closed item

| Closed item | Does the new label (or the bundled RT advance) reopen it? | Lane |
|---|---|---|
| 1. Feature frontier, 39 arms (reopen = new LABELS, RT 2026) | **YES, once**, inside Z1 only. Both conditions are met at once if O2 bundles RT | R1, R2 |
| 2. Serve basis (ridge vs blend; A4 read banned) | NO. Re-read from the regenerated artifacts; A-SERVE-1 runs as its own gate; the rank_war remedy stays unauthorized | R1, R2 |
| 3. AUC leg null; full-pool AUC inadmissible | NO. Floors re-derived, copy rule unchanged | R1, R2 |
| 4. Blend lambda pinned (0.70 / 0.57) | NO. The TOST is re-read as a receipt; clause (h) ban carried | R1, R2 |
| 5. Correction families exhausted (C-7 identity) | NO. A label change adds no family; the owner's path is A-SEAM-1 | R1, R2 |
| 6. Distribution lanes, label replacement NULL | NO. Arm R is a resolution rule, not the censored-tail shape | R1, R3 |
| 7. Consensus weighting FLAT | NOT reopened. The standing vintage A/B re-scores once in step Q against its unchanged 0.0068 bar on both legs; BA stays out of SCORED_SOURCES | R1, R2 |
| 8a. Pitcher stuff waits for the RT clock | opens BY ITS OWN CLOCK if O2 bundles RT; own registration (Z1c), not Z1 | R1, R2 |
| 8b. Pre-Statcast proxies (sits/tops/rpm) closed on a runs-allowed label | **YES, in P-MECH**: on a FIP label, velocity and spin act through strikeouts | R2 |
| 8c. K-prior | NO, permanently (the target is K%, not WAR) | R1, R2 |
| 9. Hardcoded accuracy claims | unchanged; extended to "no accuracy claim from the basis" | R1 |
| 10. FA (AAV_CONSISTENT, BAND_SCALE_GUAR, ML inputs, slope recal) | NO. The Gate 1 target moves; those closures are about dollars | R1, R2 |
| 11. Platt; SERVE_RUN_DISPERSION | NO. N2 (7i) is the named successor | R5 |
| 12. Market blend (revisit at 150+ ledger games) | its own clock is MET (179 distinct games), so the registered lab may re-run. Not a label reopen | R5 |
| 13. Market-gate constants | NO | R5 |
| 14. Dynasty weights | NO | R1 |
| 15. Closer share RED; card scraping | NO; only the saves-only re-registration on unscored windows | R5 |
| 16. "eWAR site-basis flip REFUSED, dollars bWAR-anchored" | **STALE TEXT**, superseded by the owner decisions of 2026-09-03 and 2026-09-09. Rewrite it. The OAA/rfield grid still reopens only through SDR gate G-B | R1, R2 |
| 17. Defense into eFV (reopen = the label change, one attempt) | **YES, and this is its registered condition.** eWAR v2 never re-priced hitter fielding; fWAR does. H-MECH is the one attempt | R1, R2 |
| 18. STALE_DAYS, star-blend h2, ML quantile sums, Statcast into projections, draft-anchor backfill, `eta_age_continuous`, B3 level blend, PAL | NO. The `pwoba` re-gate after 2026-11-15 runs on the new-label bundle; B3 stays out (X16) | R1, R2 |
| Model class (`xfv_model_class_readjudication`) | reopens by its own text ("the LABEL POOL (RESOLVED_THROUGH 2026)") only if O2 bundles RT; Z1b | X4 |
| 09-04 volume and age-interaction families | in the no-mechanism families (O8) | R2 |
| 09-04 level weights | descriptive order (AAA > AA > A > A+ > CPX > DSL); re-read as a receipt | R1 |
| 09-04 health family and `INJURY_PENALTY_SIDES = {'pit'}` | the gated arms go into the no-mechanism families; the rule's two cells are re-read, not re-tuned | R1, R2 |
| C3 threshold pairs, C1b observed positions, pace-from-entry, park line, frame/athl, coverage clocks (college backfill, ungraded_disc, tbs2), Statcast line/overlay, `il_stints_pre`, MiLB SDR driver, C4a elite lambda | NO. Each was killed for a label-independent reason, is banned, or has no data | R2 |
| BREAKOUT stacked P(star)/P(bust) | NO as a rank driver; it proceeds as the owner-decided DISPLAY program on the new label and uses BUST2's three-class target | R2, R3 |
| Scout-report text traits | NO. Rejected at the data layer | R2 |
| 09-09 plan 5.1 (library fielding pages, popup walker, multi-indicator range, own gmLI, pitching negative list, re-fitting conventions) | NO. These concern building WAR, not using it | R1, R2 |
| Deprecated calibration, map, lambda and odds rows (alpha_criterion, cohort_lambda, grade_recal 2/3/4, isotonic, joint map, lambda band/confirm/parity, odds recalibration ship, odds cohort, odds grade basis, bucket_age_head, side_correction, topquant, war_total_band) | NO. Re-read through regeneration | R1, R3 |
| Deprecated projections, FA, arb, betting, cards and HoF rows | NO. No WAR label, or they wait on their own clock | R1 |
| Betting 7e-B ridge (INDETERMINATE), 7e-C grown window | NO. 7e-D (the replay) joins their Holm family; N1 is new data | R5 |
| Betting 7f/7g/7h total repairs | NO refit. One 7h re-read under its own text ("more eval games under the same 7h criteria") | R5 |
| `k_strength_sweep`, `fantasy_startscore` | NO | R5 |

---

## 3. The bust redesign

### 3.1 What is true today [R3]

"Bust" carries seven definitions in the code:

1. The dataset's never-MLB kind at 0.0.
2. The Clemens per-season band under 0.5.
3. The served realized-bust event: a six-season sum under 3.0, never-MLB counted
   (`tools/_prem_odds.py:28-43`, `efv_ungraded.py:187`).
4. `_SF_BUST_WAR`: under 0.5.
5. Edwards: under 1.0.
6. Engine WAG: expectation percentile at or below 0.20.
7. Legacy WAG and the farm Bust Rate: WAG at or below -1.5.

The owner's idea of counting negative-WAR MLB players is already definition 3.
`efv_odds_calibration.py` records 162 of 162 negative rows inside the bust band.

Negative six-season WAR is KEPT NEGATIVE in the label. Only predictions are floored
(`efv_model.py:697-698, 912-913`). Resolved debuted rows under zero: 166 of 468 hitters and
168 of 537 pitchers. In the ridge target, 328 of 851 hitter and 306 of 991 pitcher debuted
rows sit strictly below every never-MLB bust.

**The defect.** 212 hitter and 209 pitcher never-MLB rows have an affiliated line in 2025 or
2026. 203 and 192 of them carry full weight 1.0. 82 hitters and 89 pitchers are at AAA.
Median ages are 23.8 and 25.5, and 141 hitters are 25 or younger. These are right-censored
rows labelled resolved, and most sit in the production fit and the 2021-2024 folds. The only
resolution rule is `bust_recent` (last list 2024 or later), and its 0.5 weight is dead
because every pool excludes those rows. There is no age rule. 475 hitter and 672 pitcher
bust rows have neither an MLBAM id nor a birth date. About 20 hitter and 36 pitcher "debuted"
rows (outright-derived) have no MLB stat line and sit in neither pool.

### 3.2 Definitions (RECORDED conventions, never fitted)

| Name | Definition | Default | Lane |
|---|---|---|---|
| REACHED | at least one MLB regular-season appearance (a sport-1 stat line or a `career_war` season); the outright-derived debut status does not count | O6 (D-B4) | R3 |
| BUST-MLB | REACHED and six-season label under **3.0** on the label source in force at the run: the engine's 0.5 WAR per season band and the exact event `tools/_prem_odds.bust_label` scores today | O6 (D-B1) | R3 |
| Reported sub-cuts, never selectable | T0 (sum under 0) and T5 (no MLB line after debut + 2, nested inside T3 on every hitter row and all but one pitcher row) | - | R3 |
| BUST-NEVER | not REACHED, and resolved by: no affiliated line in either of the two latest seasons with MiLB data on disk (id known), OR age 27 or older on July 1 of RESOLVED_THROUGH, OR, with neither id nor birth date, last list year at or before RESOLVED_THROUGH - 5 | O6 (D-B3), restated per X8 | R3 |
| CENSORED-NEVER | not REACHED and not resolved: kept in the matrix, excluded from every fit and score, like `bust_recent` | - | R3 |
| NON-BUST | REACHED and at least 3.0 | - | R3 |

**Why 3.0 and not 0.** Under the fWAR switch, T0 membership churns 26% (hitters) and 32%
(pitchers), because zero sits exactly where replacement level, the league adjustment and the
ladder decide the sign. T3 churns 8.6% and 4.3% [R3]. Catchers move most, because framing is
inside fWAR fielding: `austin_hedges` goes from 0.15 to 6.15 and crosses T3 [R3].

Under T3 on the resolved pool, the split is 1,022 never / 277 MLB-bust / 191 non-bust for
hitters (any-bust 87.2%) and 985 / 389 / 148 for pitchers (90.3%). The calibration frame
(decision years 2014-2020) holds 549 / 228 / 147 hitters and 558 / 328 / 116 pitchers. At FV
50+ the resolved debuted cells are 136 hitters and 97 pitchers, and the non-bust class is the
thin one [R3]. All counts are on eWAR v2; they are re-published on the final label before any
score (3.5).

### 3.3 Where each category enters

| Consumer | Change | Lane |
|---|---|---|
| E[WAR] ridge label `target_censored` | **no change to the target** (O6 D-B2: negatives kept; the design audit verified "busts at zero, negative seasons kept"). Only Arm R changes the POOL, by excluding CENSORED-NEVER rows | R2, R3 |
| Pooled outcome curve, anchors, fingerprint | move only through Arm R, inside the epoch (section 1.4) | R3 |
| Served P(bust) (`efv_score.py:2401-2445`: odds grade to `p_bucket_given_fv` to Platt) | **Arm S:** P(BUST-NEVER) = 1 - P(REACHED), and P(BUST-MLB) = P(REACHED) x P(BUST-MLB given REACHED). Heads read only the served odds grade and the side. They sum to the served event, and zero rows move grade, rank or dollars | R3 |
| Thin p_bust (`efv_ungraded`) | re-derived under the same split without regressing its gated win | R3 |
| Bucket model (bust bucket priced at $0) | no dollar change. A BUST-MLB salary cost below $0 is a separate gated question | R3 |
| BREAKOUT's P(bust) half (09-03 decision 3, not started) | uses the three-class target from day one | R3 |
| WAG (unified per owner answer 14b) | P(BUST-MLB given REACHED) feeds the Z2 baseline E[WAR given FV, reached, exposure]. That removes the audit-F24 comparison of a graduate against outcomes impossible for him. Engine WAG's percentile "bust" is renamed or disclosed | R3 |
| Display | two chips, "Never reaches MLB %" and "MLB bust %", summing to P(bust); graduates show the MLB leg only; glossary `bust_prob` rewritten (O6 D-B5) | R3 |

Flooring debuted negatives at 0 (arm L1) is NOT run by default. It changes the estimand,
refits every grade, and raises ties at exactly 0.0 from 54.6% to 72.2% of the hitter pool,
which moves Spearman against its own label mechanically. If the owner ever wants it, it is
a separate label arm scored against a FIXED evaluation label [R3].

### 3.4 The pre-registered gate (BUST2), to commit before any lab code exists

The text below is R3 section (e), with X8's affiliation restatement and the frame clause
made RT-relative. Commit it verbatim as `docs/efv-<date>/BUST2_GATE.md`.

> **BUST2 pre-registration.** Written before any fit, lab or look. Any change to a
> definition, threshold, frame, metric or margin after the first candidate score
> DISQUALIFIES the candidate.
>
> **Definitions** are the recorded conventions of section 3.2. The union BUST-NEVER plus
> BUST-MLB reproduces the served realized-bust event on every resolved row (an invariant
> test, asserted before the lab runs).
>
> **Two arms, Holm across the family.**
> **Arm R** (never-resolution) is a LABEL change. It rides the eFV label epoch as its own
> matrix arm, never alone. Report the resolved-to-censored count FIRST (395 full-weight
> still-affiliated rows today). STOP if the full-pool bust share moves more than 10 points.
> Rank clause: E_cond pooled Spearman non-inferior to E0 at the 0.02 TOST margin per side, on
> floors re-derived on the final frame (runbook step G), scored against BOTH the E0
> evaluation label and the Arm R label, with both published.
> **Arm S** (the split) is an ODDS change. Heads: P(REACHED) and P(BUST-MLB given REACHED),
> each a function of the served odds grade and the side only (no new covariates).
>
> **Frame:** forward-chained by decision year over 2014 through the last decision year
> whose six-season windows are all closed under the RESOLVED_THROUGH in force at the run
> (2020 at RT 2025, 2021 at RT 2026). Served-comparable rows only, each fold trained strictly
> on earlier years. Power is stated in advance and re-published on the final label.
>
> **Primary (Arm S):** three-class multinomial log loss, pooled over folds. Paired bootstrap
> B = 2000, resampling the TRAIN frame and REFITTING on every draw, seed 20260807. The
> candidate must beat ALL THREE comparators with the CI95 of the difference excluding zero:
> C0, the incumbent served p_bust split by the train-fold constant P(never given bust);
> C1, the train-fold three-class base rate; C2, the candidate with its conditioning column
> row-permuted within fold. It must also exceed the p95 of a label-permutation null band.
> **Secondary, all must hold:**
> (i) the implied binary P(any bust) is non-inferior to the served p_bust at 0.005 Brier and
> 0.02 log loss;
> (ii) Murphy resolution rises with a CI95 above zero, and reliability worsens by no more
> than 0.005;
> (iii) per-category reliability tables (8 equal-count bins, Wilson CIs) are published per
> side;
> (iv) P(BUST-MLB given REACHED) beats the train-fold constant conditional rate on log loss
> on resolved debuted rows alone;
> (v) a test asserts zero rows move `xfv_grade`, rank, `xfv_war_6yr` or `surplus_mm`.
> **Not a criterion:** pooled bust ECE (a zero-information constant reproduced 152.7% of a
> candidate's ECE gain in `xfv_dist_recalibration`).
> **On failure:** the split may ship only as a DISCLOSURE (the served p_bust with its
> base-rate decomposition, labelled as a base rate), never as a model.
> **Label-source clause:** results bind the label they were measured on. The category churn
> table on the final label is published before any score.

### 3.5 Order

1. **Now** (docs and constants, no served number moves): record the taxonomy in one module
   of named constants. Point every one of the seven definitions at it, or comment on why it
   differs (Edwards 1.0 stays a named published-prior exception). Rewrite glossary
   `bust_prob`, then run `copy_lint`.
2. **Now:** add descriptive matrix columns (`bust_category`, `reached`, `never_resolved_by`,
   `still_affiliated`), read by no model, plus the union invariant test.
3. **Before the epoch:** commit BUST2 alone.
4. **In the epoch:** Arm R as an arm (section 1.4).
5. **After the epoch:** publish the churn table on the final label, then Arm S in the lane
   with BREAKOUT's bust half, then the thin p_bust re-derivation, then the chips, then the
   WAG baseline (Z2).

---

## 4. The betting plan

### 4.1 Posted lineups (the owner's ask)

**Premise correction** [R4]. The served moneyline, runline and total never price an expected
lineup. `expected_runs` reads `z_off`, the standardized `offense_plus`: a season HEM+ rollup
over the whole roster (`betting_model.py:966, :2517`). The constructed nine reaches only the
props fair lines and the dark vintage columns. A median 16.6% of each club's Offense+ plate
appearances come from hitters not active tonight: 20 of 30 clubs exceed 0.15, and SF sits at
0.423 [R5]. So the real change is from "roster season aggregate" to "tonight's nine against
tonight's starter", and that is a new model input under 5c.

**Source** [R4]. `fantasy_schedule.fetch_lineups` calls StatsAPI
`/schedule?hydrate=lineups`, a 12-minute cache keyed by `game_pk`, at zero Odds API
credits. It is already in the tree, and `/dfs/` reads it. `homePlayers` and `awayPlayers`
arrive in batting order with `id` and `primaryPosition`, and carry no bat side. Bat side
joins from the hitter board, and pitcher hand from `pal_export.load_pitch_hand`.

**Timing** [R4]. The nightly builds the board once at 03:10 ET. Nines are posted on:

| Lead before first pitch | Nines posted |
|---|---|
| 0-60 min | 42 of 42 sides |
| 60-120 min | 46 of 48 |
| 120-180 min | 51 of 58 |
| 180-240 min | 54 of 106 |
| 240-360 min | 4 of 96 |
| 6 h or more | 0 of 84 |

A posted card equalled the nine that started on 177 of 180 sides (98.3%). Inside 6 hours,
the listed probable started on 469 of 470 announced sides.

**The trap** [R4]. The completed feed's `boxscore.teams[side].battingOrder` array holds the
CURRENT occupant of each slot. It differs from the true starting nine (players whose own code
is 100-900) on 3,464 of 4,394 sides (78.8%), including the docstring's "verified" game 824804.

**The job.** `tools/betting_lineup_job.py`, cron `*/15` under TZ=UTC. It is modelled on the
close job, with `--why`, `--selfcheck` and a heartbeat. It acts only when a game is 10 to 180
minutes from first pitch and makes one StatsAPI call (lineups plus probables) per invocation,
at zero credits. It appends immutable rows to `.cache/lineup_captures/<UTC date>-<HHMM>.json`
(`game_pk`, side, org, `posted_ids`, `probable_id`, `captured_at`, `first_pitch`,
`lead_minutes`, status) and refuses any capture after first pitch [R4]. This is also R5's
instrumentation item I4: the same store makes the backtest's starter the object the board
priced (the backtest reads the final feed's probable, which equals the first pitcher used on
4,385 of 4,392 sides) [R4, R5].

**Three phases** [R4]:

| Phase | What | Moves a served price? | Credits |
|---|---|---|---|
| 1 dark capture | the job only | no | 0 |
| 2 disclosure | intraday rebuild of `betting.json` and `dfs.json` when a capture lands. Rows get a `lineup` block, slots a `lineup_caveat`, and DFS applies its existing confirmed-card rule. Narrow intraday publish from the single-writer box | no team price; DFS start rates follow the shipped rule | 0 |
| 3 serve | posted sides priced on `z_off_lu` | yes, after a 5j PASS only, via `SERVE_POSTED_LINEUPS` and a `MODEL_VERSION` bump | L-1: about 93 a month from the 150 reserve |

**Pick-publication rule** (R4-1, the honest half, before any intraday build) [R4]:
- **Slot lock.** `.cache/betting/published_slots/<slate>.json` is first-write-wins. Later
  builds serve the Pick of the Day and the longshot verbatim from the lock; anything later
  (a posted card, a changed probable, a started game) rides beside them as
  `since_published`. `write=False` builds never create a lock.
- **Record guard.** `maybe_publish_record` accepts one row per `(slate_date, slot)`, tested
  with a two-build test. Today it is idempotent per bet identity only, which is a latent
  double-headline defect the day `RECORD_PUBLISH_ARMED` flips.
- **Ledgers.** Shadow `board_all` rows carry a `pricing_basis` and are never pooled across
  bases. Calibration rows from an intraday reprice go under `phase: "lineup"`.
- **Stale-price rule.** An edge is valid only against a price captured after every input
  change that moved the model. A repriced side whose price predates its latest input change
  is marked `price_predates_input` and cannot enter a slot, a badge or the record. An
  invariant test pins it. Phase 2 does not reprice at all.
- **Publication timing A:** slots are chosen at the nightly and locked, until 5j passes (O21).

**The pre-registered gate.** Commit R4 section D as `docs/diamond-betting.md` **5j** BEFORE
any code, and before the 5c look on 2026-09-17 so that B4's result cannot shape it [R4, R5].
Two edits are made at commit, per X3 and X9. First, delete the sentence that betting has zero
WAR readers, and state instead that `lineup_strength` and `star_out` read the projections
bundle. Second, number the section 5j and schema-stamp it with whatever number actually
lands (5 is current; 6 is assumed, and a correction records the truth, as 5d's did).
The gate text in summary (the full text is R4 section D):

> **Candidate:** z_off_lu = z_off_base + [ w_O x (P_h - C_h) + (1 - w_O) x (P_s - C_s) ] /
> off_sd. P is the `LINEUP_SLOT_PA`-weighted HEM+ of the nine that started (N00 codes), C
> the same over the constructed nine for hand h, with per-hand values falling back to
> season values identically on both sides. w_O is the starter share from `_starter_share`.
> No new free parameter. Computed by `game_offense_lineup_z`, which nothing served calls.
> **Columns** (the schema-6 record blocks): `hand_index`, `orders`, `bench_mean_hem`. The
> lineup itself is a pregame fact joined at pricing time.
> **Expectation, stated first: UNDERPOWERED on outcomes.** The expected t is about sqrt(n)
> x RMS(p shift). A resting regular moves an even game about 1.4 points and a resting star
> about 4.6; the leg needs an RMS of about 6.7 points at 600 games.
> **Leg O** (required, non-inferiority) at split quantiles 0.6/0.7/0.8: the lb95 of paired
> moneyline Brier is at least -0.001; log loss and total absolute error are not worse on the
> point estimate. Superiority is reported, and qualifies only if the power precondition says
> it can resolve.
> **Leg M** (required, superiority): on at least 100 eval games with a two-sided h2h price
> captured after both cards posted, the mean of (p_served - m)^2 - (p_candidate - m)^2 is
> above 0 at one-sided t of at least 1.645.
> **Control:** a 200-seed within-date permuted-delta twin; the Leg M improvement must exceed
> its p95.
> **Clock:** four weeks of schema-6 vintages, 600 eval-half regular-season games, and 100
> Leg M games. First look in 2027, once per season after the last regular-season game.
> **Disqualification:** any number relating this delta or a close variant to an outcome or
> a price before commit.

**Adjacent, each its own flag and section** [R4]: props on the confirmed slot and starter
(`SERVE_PROPS_POSTED`), strikeout props against the posted nine, the props per-event pull
moved after the chosen games' cards post (O24), and later posted-nine variants of 5i-B, 5f,
5g and 5d-D, each frozen on the constructed nine until its own section.

### 4.2 The holistic backlog, ranked

The model's standing today [R5]: n 548, Brier 0.24334 against the home constant 0.24792,
skill t 2.314. Elo sits at 0.2444. On the 299 open-capture games the market scores 0.22995
against the model's 0.24414. The moneyline ledger reads 0.243617 on 175 games (t -1.006 vs a
coin). The total has been LEDGER-CLOSED since 2026-09-03 (0.268081, t 2.19 worse than a coin,
171 games). The skill lives in the pitcher term (b2).

#### Repairs (served, behind flags or with invariant tests)

| Rank | Item | Evidence | Gate or test | Deadline |
|---|---|---|---|---|
| 1 | **7e-D as-served replay: grade the pricer that serves.** For each eval date D, fit `build_context` on every game before D using vintage V_D's leaderboards, price D, and grade on the same window and ladder. Criteria: RIDGE_FIT_GATE_CRITERIA at 0.6/0.7/0.8. Same Holm family as 7e-B and 7e-C. Then `SERVE_PRICER` with a tripwire so gate 2 always reads the pricer that serves (O14) | served b1 0.2510 / b2 -0.3126 / diff_shrink 0.80 / home +0.2149 against graded -0.0372 / -0.0965 / 1.28 / -0.0443. 25.3% vs 2.7% outside 0.4-0.6. Today's POTD is 0.755 vs fair 0.6261, where the graded pricer has no games above 0.7 [R5] | registered eval mode; the response to a fail is pre-registered (O14) | register now; run in the offseason or sooner |
| 2 | Test isolation for `data/betting_status.json` and every betting sidecar, with a golden-hash teardown test | the working tree holds fixture state (`ev9`/`ev10`, cap 6, 0 snapshots, props armed) [R5] | test | now; before any commit or publish |
| 3 | `min_edge_gate` pooled-sampler tripwire (L14-05), the n-1 variance and zero-variance refusal (L14-09), and per-market subledger caps | gate 1 opens at 548 of 600 at 10.71 games a day [R5] | tripwire test | before ~2026-09-16 |
| 4 | Record guard and slot lock (R4-1 a, b) | latent double-headline defect [R4] | two-build test | before any intraday build |
| 5 | `starting_nine(feed, side)` on N00 codes, the `fetch_lineups` docstring fix, and the eval disclosure that the backtest's starter is the final feed's probable | 78.8% trap; 4,385 of 4,392 [R4, R5] | tests | W0 |
| 6 | Slate and runline guards L14-04 (postponed counted as started), L14-06 (non-1.5 points, pushes), L14-12 (explicit-date board with the started filter skipped, live today), L14-08 (note contradicts policy) | [R5] | tests | W0 |
| 7 | DFS/fantasy constants: `_PA_PER_START` 4.15 to 4.0208, the PA identity (breaks on 14 of 109 rows), QS 0.2574 vs 0.3828, CS/SB 0.26 vs 0.3018, HBP/BF 0.008 vs 0.01072, one shared matchup clamp | 3.2% high on every hitter total [R5] | invariant tests (`9 x pa_per_start` under league PA per team-game) | W0 |
| 8 | Freeze `LINEUP_SLOT_PA` at its literal (a 5i amendment under 5c rule 1, replacing the equality pin at `test_betting_ballpark.py:216`), THEN repair `SLOT_PA` behind `SERVE_SLOT_PA_MEASURED` with B-PA-DIST's acceptance | slot 1 4.52 vs 4.65, slot 9 3.455 vs 3.85; sum 38.25 vs 37.85; Overs 0.5-1.8 points high on 30 of 30 rows [R5] | 5i amendment, then the flag | amendment before 5i-B's look (~2026-10-10) |
| 9 | Runline tie split: reprice (owner answer 4) | +1.5 home overstated 0.031-0.040 a game [R5] | as answered; N2 must beat it | in flight |
| 10 | Over lean: stays disclosed (owner answer 1). One 7h re-read under unchanged criteria on 2026-09-28, registered before 09-27 (O23). The next honest attempt is 7i (N2) | 323 Overs to 102 Unders; 7f FAIL, 7g FAIL, 7h 2 of 4 [R5] | 7h text | register before 2026-09-27 |
| 11 | Home-field level: not a flip; it is candidate N4 | graded home adj -0.0443; the level repair is worth at most 0.00077 Brier [R5] | N4 | offseason |

#### Dark candidates (each gets its own section before any number)

| Rank | Candidate | Size and evidence | Gate | Clock and conflicts |
|---|---|---|---|---|
| 1 | **N1: reconstructed history 2018-2025 and a multi-season coefficient fit.** `.cache/pbp_corpus` holds 1,448,967 plays over 17,008 pre-2026 games. Rebuild ONLY the five core inputs as of each game date | attacks the 610-row, r2 0.003 fit at its root [R5] | stage 1 pre-2026 (fit 2018-23, tune 2024, score 2025 once, season-block bootstrap); stage 2 on the 2026 eval half against the served-class pricer. `SERVE_HISTORY_FIT` | no 2026 clock touched. Never reconstruct a clocked dark column. Stage 1 reports per-season sign and scale (the ball, the pitch clock) |
| 2 | **5j posted lineups** (section 4.1) | the owner's ask; median 16.6% of Offense+ PA from unavailable hitters [R5] | 5j | first look 2027; register before 09-17 |
| 3 | **N2 (7i): one joint score distribution fitted on pre-2026 finals** | tie atom 0.1352 vs 0.0877; one-run band 0.2503 vs 0.2721; var/mean 2.35 [R5] | per market: 11a's four criteria for margin and runline, the 7g/7h grid for the total, moneyline non-inferiority. `SERVE_SCORE_KERNEL` | immediate after registration; must beat the repriced runline incumbent; not stacked on 7h |
| 4 | **N6: the z_prev family** (one Holm family). F05-07 run-scale SEM+/REM+ blend (4.8% apart per point); F08-01 HR point 1320 per BF as a betting estimand (moves SEM+ 3+ points on 98 of 229 starters); G4-02 velocity form; G4-10 expected outs | the pitcher term is where the skill lives [R5] | 5c protocol per arm, permuted-pitcher twin, Holm over four | archive-reconstructable (O22). G4-10 amended into 5d-E before 2026-10-07. Served SEM+/REM+ unchanged |
| 5 | **N3 (5k): run environment.** A trailing league runs-per-game term (14/30 days to D-1) plus a calendar-month EB offset fitted pre-2026 | 7h: Over 7.5 observed 0.615 after 2026-08-29 vs 0.560 [R5] | the 5d-C form, permuted-date twin; one Holm family with 5d-C and 5h | read on 2026-10-07, never earlier |
| 6 | **N5: results-and-starters rating with offseason carry** | Elo is 0.00106 behind on 548 games and ahead on the 299 market games [R5] | G4-01 two stages, permuted-club twin | stage 1 pre-2026 |
| 7 | **N4: home and tie priors from eight seasons** | corpus home rate 0.5210-0.5428 per season [R5] | pseudo-count grid 50/100/200/400 under Holm | fold into N2 if N2 ships first |
| 8 | **N10: selection side.** The market-blend lab re-run (its clock is met, 179 of 150 games), B-BAKEOFF R3, a consensus-fair denominator, a thin-line veto (28% of priced sides on 2-3 books), early line move (forward only), CLV as the tiebreak | G5 measured market 0.2388 vs model 0.2460 on 158 games [R5] | B-BAKEOFF's paired per-slate design, 40+ slates | the expected finding may be "the model adds nothing the open does not have", which is a finding |
| 9 | **N8: opponent-specific matchup term (log5 K/BB/HR)** | [R5] | its own section | the DFS multiplier prices it ungated; reconcile first |
| 10 | **N11: props and futures.** Dark-grade four next prop markets (G8-5), B-PA-DIST, start probability as a calibrated number, B-MODELID; the offseason Elo futures baseline | [R5] | harness rules | offseason |
| 11 | **N9: the 2027 protocol, registered before Opening Day.** The 2027 fit uses all 2026 vintage-graded games (about 1,100), so the eval clock starts on game one. A gated prior-season carry for the five core inputs, and every 2026-registered dark column landed before the season | the vintage store starts 2026-07-05, so the model has never been measured in April or May [R5] | own section | before Opening Day 2027 |
| 12 | **N12: screens.** Umpire effect on eight seasons (chase a source only if the between-umpire SD exceeds 0.15 runs and a pregame source exists); a market-residual feature screen | [R5] | screens only | may only disqualify or prioritize |

#### Instrumentation

| Rank | Item | Evidence | Owner action? |
|---|---|---|---|
| 1 | **I1: install the close job on the production box**, verified with `--selfcheck` | 0 of 27 snapshots are close; 0 of 2,214 calibration lines and 0 of 281 shadow rows carry a close price [R5]. Every slate without it is lost for good | yes (O16) |
| 2 | **I3: two 5c amendments before 2026-09-17**, on facts established without outcomes: (a) `lineup_strength` became roster-filtered at `7cd5f572` (2026-09-07), so the look reports pre/post counts; (b) how rule 2 counts missing vintage nights | [R5] | no |
| 3 | **I2 and I10: independent crons for vintage (06:17 UTC) and open capture (13:10 UTC), a missing-night sentinel, and one named writer** | 16 of 24 schema-3 nights exist (missing 08-22, 08-25, 08-26, 08-28, 08-29, 09-01, 09-02, 09-08); 25 of 36 game dates have an open; captures land a median 3.83 h before first pitch [R5] | yes (O16) |
| 4 | **I4 = the lineup capture job** (section 4.1) | [R4, R5] | arm (O17) |
| 5 | **I7: season-end scorers committed before 2026-09-27**: the futures win-total PMF with CRPS vs Pythagenpat (G8-7), the DFS archive grader (18 slates), the ROS weekly archive (G8-9), and the two-start grader audit (7 of 561 exact) | [R5] | no |
| 6 | **I9: carry the WAR epoch into the two betting readers.** Stamp `star_out`'s basis, sequence step M after 09-17, re-read Futures with a changelog | [R1, R5] | no |
| 7 | **I8: record honesty.** A digest chain over the calibration ledger, accessible-book ROI beside best-of-nine (115 of 281 shadow rows are priced at lowvig), a per-book hold table with a fair-book tripwire, machine fields on the member tracker | [R5] | no |

#### Things to stop [R5]

- X1: fitting a fourth one-parameter total repair on the 305-game fit half.
- X2: filling slots and badges from a ledger-closed market (`SLOT_MARKET_POLICY = "any"`,
  `betting_model.py:385`; O15).
- X3: quoting `out_of_sample_skill` as validation of the served board until 7e-D lands.
- X4: pinning a dark column's constant to a served constant.
- X5: serving an explicit-date manual rebuild with the started filter skipped.
- X6: letting tests write betting artifacts.
- X7: registering late-season dark columns as if a 2026 look exists.
- X8: reading the one-per-slate POTD record as accruing evidence.
- X9: changing a dark column's input membership without a same-day 5c amendment.
- X10: capturing the open inside the nightly pipeline.
- X11: the sentence "betting has zero WAR readers".

---

## 5. Waves, dependencies and hard dates

The 2026 regular season ends **2026-09-27**. A dark column landed now accrues at most about
16 regular-season days [R5]. Every new betting candidate is either archive-reconstructable,
fitted on pre-2026 data, or carries a 2027 first look, and its registration says which.

### 5.1 The clock calendar (every open clock)

| Date | Clock | What must precede it | Lane |
|---|---|---|---|
| by 2026-09-15 | deadline for the 5c amendments (I3), the 5e postseason amendment (owner answer 8), and the 5j and 5k registrations | the looks below | R4, R5 |
| ~2026-09-16 | gate 1 `vintage_sample` opens (548/600 at 10.71/day) | the L14-05 tripwire (repair 3) | R5 |
| ~2026-09-17 | 5c B3/B4 look (`xwoba_14/30`, `lineup_strength`, `star_out`), with twins | I3 amendments; no posted-lineup, active-roster or star variant computed on outcomes; no projections retrain | R5 |
| 2026-09-18 | GRPO first admissible forward read | no GRPO retrain before it | R2 |
| before 2026-09-27 | I7 scorers and the 7h re-read registration committed | season end | R5 |
| 2026-09-27 | regular season ends | | all |
| 2026-09-28 | 7h re-read (once); season-end reads of futures, ROS, two-start, DFS archive | | R5 |
| ~2026-10-05 | D9 freeze fetch of the 2026 fWAR vintage (O3); the epoch starts | E1 to E8 | R1 |
| 2026-10-07 | 5d A-E (schema 4) and 5k run environment, one Holm family with 5d-C and 5h | G4-10 amended into 5d-E first | R5 |
| ~2026-10-09 earliest | 5e handedness (restarted; four weeks after the first repaired vintage; postseason COUNTED per owner answer 8; subject to its floors) | its amendment | R5, owner |
| ~2026-10-10 earliest | 5i-B park by hand | the `LINEUP_SLOT_PA` freeze amendment | R5 |
| clock starts when armed | 5h forecast weather (owner armed it, with the Previous-Runs backfill) | | owner |
| after 2026-11-15 | the `pwoba` re-gate, on the new-label projections bundle | the epoch's step M | R2 |
| before Opening Day 2027 | N9 protocol; every 2027 dark column landed | | R5 |
| 2027 | 5e (if not read in October), 5g (first date with 4 weeks and 600/300 games), 5h live arm, 5j (after the last regular-season game), 5f (end of the 2027 season, with a power precondition) | | R4, R5 |
| 2027 season close | the next label epoch (RT 2027), bundling any passed W1.3 departures | | R1 |
| 2028 run | the reserved 2025-fold confirmation of any Z1 passer | | R2 |

### 5.2 Waves

**W0, now to 2026-09-16 (deadline-bound; no served eFV number moves).**
- Betting:
  - the I3 amendments, the 5e postseason amendment, and the 5j, 5k, 7e-D, 7i and 7h
    re-read registrations (docs only);
  - repairs 2, 3, 5, 6 and 7;
  - the lineup capture job armed (R4-2) if O17 says yes. It captures, and computes nothing.
- PROSPX:
  - the bust taxonomy module and descriptive columns (section 3.5 steps 1-2);
  - the BUST2 registration;
  - E2 identity repair;
  - E3 (the `fwar` provider, the pitching loader, the frozen vintage builder, the rebase
    provider parameter), plus the O4 pre-2011 cache;
  - rewrite do-not-reopen item 16's stale text.
- Context: the owner's 24 answers are in implementation (workflow `wf_02e3c0ae-178`). Each
  served move lands in its own epoch with its fingerprint term, before E8's snapshot.

**W1, 2026-09-17 to 2026-09-27.**
- Betting:
  - the 5c look on its date under its protocol;
  - then R4-1 (record guard, slot lock);
  - R4-3 (schema-6 `hand_index`, `orders` and `bench_mean_hem` blocks, byte-identical
    Offense+ verified);
  - the `LINEUP_SLOT_PA` freeze amendment, then repair 8;
  - the I7 scorers committed.
- PROSPX:
  - the Z1 engineering (arm ledger extension, `retest` mode with bit-parity, the `holm_family`
    alpha argument);
  - the `FWAR_LABEL_EPOCH_GATE.md` registration (E4), committed alone, after the O
    decisions;
  - the `LABEL_V3_DRIVER_RETEST_GATE.md` registration, committed alone with the derived arm
    list;
  - the Arm R / A1 / A2 matrix code behind flags.
- Dependencies: E4 needs O1, O2, O6 and O7. Z1's registration needs E4's final-label
  definition.

**W2, the epoch (from the ~2026-10-05 freeze).** No lane measured the rebuild's duration.
The 2026-09-04 epoch's rebuild ran inside one day on this box, plus the box mirror, so plan
for days, not weeks, with the gate's part 9 last.
- Runbook A to Z (section 1.5), on this box then the box, with the D-before-C deploy guard.
- Step M only after 5c and GRPO have read (E5).
- The Futures changelog (O12).
- Betting runs its October clocks in parallel, untouched by the epoch except for `star_out`
  and Futures.
- Phase 2 of posted lineups (the intraday disclosure rebuild, R4-4) may land here once R4-1
  is in and O17 says yes.

**W3, after the epoch (October to November).**
- PROSPX:
  - Z1, about 4.5 hours of lab time, one process at a time;
  - Z1b model class, if bundled;
  - Z1c pitcher stuff;
  - the C1-C4 confirmatory read (at step Q);
  - Z2 WAG baseline and the realized-PIT gate;
  - Z3 valuation reconciliation;
  - BUST2 Arm S, the thin p_bust, and the chips;
  - BREAKOUT's bust half on the three-class target;
  - the age-ramp gate and the injury-cell re-read;
  - GRPO retrain;
  - the non-eFV refits (R2 section 4);
  - the `pwoba` re-gate after 11-15.
- Any Z1 passer ships only in its own later grade-basis epoch.

**W4, the offseason.**
- Betting:
  - 7e-D replay (and the O14 response);
  - N1, N2, N4 and N5 stage 1 on pre-2026 data;
  - the N6 arms (archive-reconstructable if O22 allows);
  - the market-blend lab and B-BAKEOFF (N10);
  - N11;
  - N9 registered before Opening Day;
  - R4-5 post-lineup price captures if O18 funds them.
- PROSPX: Z4 (W1.3 departures, display only), and the eWAR v3 replica for pitchers once the
  owner's IFFB and FIP park factor pulls land (owner answer 14a).

**Dependency spine:** E2, E3, E4 feed the D9 freeze, which feeds the epoch (A to Z). Z1,
Z1b, Z1c, Z2, Z3 and Arm S follow the epoch. On the betting side: the I3 amendments feed the
5c look, which is followed by step M, R4-candidate computation and the schema-6 look in 2027.
The I1 close job is needed before L-1 captures, which are needed before 5j Leg M.

---

## 6. Owner decisions, with a recommended default for each

**PROSPX and the WAR epoch**

| # | Decision | Recommended default | Lane |
|---|---|---|---|
| O1 | Label source for every fitted consumer (the 09-09 plan's D7) | **Published fWAR, frozen per season.** The 09-11 ask answers D7; the E4 gate doc is the registration. The eWAR v3 replica and W1.3 arms are display-only this program | R1, X1 |
| O2 | Bundle the epoch with RESOLVED_THROUGH 2025 to 2026 at the 2026 season close, with the leave-one-out arms of 1.4 | **Bundle** (one rebuild; items 1, 8 and the model class then meet their own conditions). The alternative is the basis now and RT in early 2027: two rebuilds | R1, X2 |
| O3 | D9 freeze date for the 2026 season vintage | **A fetch on ~2026-10-05**, stamped with `fetched_at`. Completed seasons are not re-fetched until the 2027 epoch; a drift receipt is published then | R1 |
| O4 | D1b: cache the sabermetrics feed for 2000-2010, both groups (22 calls, no credits) for the FA corpus (38% of rows), the arb spine (14.7%) and the slot curve (4.3%) | **Cache.** If pre-2011 pitching is absent, keep bWAR there with a per-artifact `war_basis: mixed` disclosure, never an `fwar` stamp | R1 |
| O5 | Displayed WAR at the flip | **Published fWAR with attribution for both sides**; the player-card tick becomes the eWAR v2 comparison (links owner answer 20). The S2 replica replaces it as the builder once pitchers pass | R1 |
| O6 | Bust taxonomy (D-B1 to D-B6) | **BUST-MLB under 3.0 six-season; negatives kept in the regression; never-resolution rule as restated in 3.2; REACHED = a regular-season appearance; two chips summing to P(bust); a failed Arm S ships only as a base-rate disclosure** | R3 |
| O7 | Which label-definition arms ride the epoch | **Arm R yes. A1 and A2 yes** (owed by 09-04 locked decision 1; no arm matrices exist on disk). **L1 flooring no** | R1, R3 |
| O8 | Z1 scope and alpha | **Four add families at 0.025 / 0.015 / 0.005 / 0.005 plus ABL at 0.05 for removal; include the 09-04 families** (dropping them saves about 3 hours and changes no error control) | R2 |
| O9 | Serving a Z1 passer before its reserved-fold confirmation | **Provisional, in its own epoch, no accuracy copy, automatic removal on a failed 2028 confirmation** | R2 |
| O10 | Model-class re-adjudication | **Yes, once, as Z1b, if and only if O2 bundles RT** (its own reopen text) | X4 |
| O11 | Sequence the epoch's projections retrain against 5c and GRPO | **After the 2026-09-17 look and the 2026-09-18 read**, stamping `star_out`'s basis; never an amendment after a look | R1, R2, R5 |
| O12 | The Futures board during the postseason | **Disclose the epoch's move with a one-line changelog**; do not hold two projection bundles | R5 |
| O13 | Engine WAG's percentile "bust" (expectation percentile at or below 0.20), a meaning none of the other definitions share | **Rename it on every surface (for example "bottom-fifth outcome")**, so "bust" means only BUST-NEVER or BUST-MLB | R3 |
| - | F-DEF repair | ANSWERED 2026-09-11: in the WAR epoch (rides as a step-M arm) | owner |
| - | WAG_UNIFIED | ANSWERED: flip now; Z2 refits its baseline after the epoch | owner |
| - | eWAR cadence (D11) | ANSWERED: nightly; reconciled in X13 | owner |

**Betting**

| # | Decision | Recommended default | Lane |
|---|---|---|---|
| O14 | Which pricer serves | **Grade the served pricer with the 7e-D replay first.** If it fails the registered criteria, serve the graded vintage pricer and bump `MODEL_VERSION`. Pre-register the response: the POTD and badges may go empty until a pricer clears | R5 |
| O15 | `SLOT_MARKET_POLICY` for a ledger-closed market (revisits the 09-05 "any" decision) | **Publishable markets only**: the total leaves the slots and badges until its ledger leg reopens | R5 |
| O16 | Close job on the production box; two independent crons; the named single writer | **Install all three now** (the highest-value operational item) | R5 |
| O17 | Arm the dark lineup capture job; Phase 2 intraday disclosure rebuild and narrow publish | **Yes to capture now (zero credits); yes to Phase 2 after R4-1 lands** | R4 |
| O18 | Credits for a post-lineup price capture | **L-0 until the close job is verified running, then L-1** (about 93 a month from the 150 reserve). L-3 (about 279) breaks the 500 tier | R4 |
| O19 | Accept Leg M (market agreement) as the qualifying leg of 5j | **Yes.** The outcome leg is expected to be underpowered; without Leg M the candidate cannot pass | R4 |
| O20 | 5j backfill arm (season-only, git-committed boards, 17 dates, none 08-13 to 09-04); 5j and postseason | **Backfill no. Postseason not graded in 5j** (its Leg M needs post-lineup captures, and the first look is 2027 either way). The owner may align it with the 5e answer | R4, X10 |
| O21 | Publication timing | **A: slots chosen at the nightly and locked**, until 5j passes | R4 |
| O22 | Archive-reconstruct provenance (ruling 6.5) for 5k(a), N6 and the lineup backfill | **ALLOW, labelled per row** | R5 |
| O23 | One 7h re-read on 2026-09-28 under unchanged criteria (its own text allows it) | **Yes, once, registered before 09-27.** A pass still needs the owner's flip of `SERVE_TOTAL_CALIBRATION` | R5 |
| O24 | Move the props per-event pull to after the chosen games' cards post | **Yes, when props are armed** (same 120 allocation) | R4 |
| - | 5e postseason; runline reprice; DFS started games | ANSWERED 2026-09-11 (count postseason; reprice now; remove from the draftable board) | owner |

---

## 7. Do-not-reopen additions, and risks

### 7.1 Additions to the checklist

1. Rewrite item 16 to read: "eWAR basis flip superseded (owner, 2026-09-03 and 2026-09-09);
   the OAA/rfield grid reopens only through SDR gate G-B" [R1, R2].
2. After Z1: if it nulls, items 1, 8b and 17 are RE-CLOSED on label build X. No driver
   re-test until the 2027 RT advance or a registered label-definition change moving the
   debuted label below Spearman 0.99 against the frozen label [R2].
3. CONVICTION_PROGRAM stop clause 1 is suspended ONLY inside the Z1 registration [R2].
4. No W1.3 departure and no eWAR v3 replica output becomes a label inside this program; the
   next label epoch is the 2027 season close [R1].
5. Completed fWAR seasons are never re-fetched or re-frozen outside a label epoch [R1].
6. "Sports Betting has zero WAR readers" is retired (`star_out`, Futures) [R1, R5].
7. The completed feed's `battingOrder` array is never the starting nine; read the N00 codes
   [R4].
8. No edge against a price captured before the latest input change (the stale-price rule)
   [R4].
9. Flooring debuted negative WAR in the E[WAR] label is not an accuracy fix. It may run only
   as a separate label arm scored against a fixed evaluation label [R3].
10. No bust threshold is selected among T0 to T8 after any score. T0 and T5 are report-only
    [R3].
11. Pooled bust ECE is never a gate [R3].
12. No fourth one-parameter total repair on the 305-game fit half (X1). No dark constant
    pinned to a served constant (X4). No dark column's membership changes without a
    same-day amendment (X9) [R5].
13. `out_of_sample_skill` is not cited as validation of the served board until 7e-D lands
    [R5].
14. N1 never reconstructs a clocked dark column (off_vs_*, xwOBA pair, `lineup_strength`,
    `star_out`, schemas 4 to 6) [R5].

### 7.2 Risks

1. **Churn reads as player movement.** 34% of hitter rows change implied grade, 13% cross a
   Clemens band, and 119 hitters move 2+ grades in FV 20-40 [R1]. The epoch bump must land in
   the same commit as the flip.
2. **Accuracy expectations.** The last basis epoch measured a null. Z1 is expected to null
   (0 of 48 plus 0 of 177 so far) [R2]. Copy must frame the epoch as coherence.
3. **Identity.** Without E2, an MLBAM-keyed label zeroes 13 collision players, and 135
   unresolved rows cannot join [R1].
4. **A mixed basis under a new stamp.** Without O4 the corpus stays 38% bWAR under an `fwar`
   stamp, which is worse than today [R1]. `career_war` holds 682 of 11,575 bWAR seasons
   (5.89%) [R2].
5. **The nightly pre-empting step C** (the 2026-09-04 incident). D must never reach the box
   without C [R1].
6. **Stale inputs mid-lab.** The nightly regenerating matrices during Z1 voids the verdicts.
   Hence P4 [R2].
7. **Close-variant contamination in betting.** Posted-lineup, active-roster and projections
   work all touch `star_out` and `lineup_strength` before 09-17. Any outcome read before the
   look disqualifies [R4, R5].
8. **The 7e-D replay may remove the POTD.** That is the point, and the response is
   pre-registered (O14) [R5].
9. **5j cannot pass without price captures that do not exist.** There are zero close
   snapshots and no post-lineup kind today [R4].
10. **Slot churn and double headlines.** Intraday builds without the lock and the record
    guard [R4].
11. **Small samples behind the lineup design.** The posting curve and late-scratch rate rest
    on 27 lineup and 116 probable captures from one box [R4]. Re-read them off the capture
    store after a month.
12. **Everything betting was measured on this box's `.cache`.** The deploy box's vintage and
    odds stores are unmeasured [R5]; I10 names the store.
13. **`data/betting_status.json` holds fixture state now.** A commit or publish before repair
    2 ships wrong status [R5].
14. **Label-source dependence of the bust split.** Catcher (framing) and reliever (57/43)
    membership moves most. BUST2 results never transfer across labels [R3].
15. **Thin cells.** FV 50+ resolved debuted cells hold 136 hitters and 97 pitchers, and star
    positives are 48 hitters under fWAR. Per-tier claims are underpowered and must be labelled
    so [R2, R3].
16. **Attribution.** Bundling RT, the basis and three label-definition arms in one rebuild is
    honest only through the E4 leave-one-out arms. Without them, clause (f) cannot separate
    the causes [R1].
17. **Operational load on the single-writer box.** A 15-minute lineup job, intraday
    publishes, the close job and two independent crons [R4, R5]. Every job refuses loudly
    and never loops.
18. **Display licensing.** Serving FanGraphs' WAR verbatim from MLB's API is an attribution
    decision (O5), separate from using it as a label [R1].
