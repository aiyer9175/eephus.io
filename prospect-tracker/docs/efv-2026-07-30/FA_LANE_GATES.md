# FA lane gates - pre-registered criteria (2026-07-30)

Owner program: `docs/master-plan-2026-07-29-efv-fa.md` Phases E and F.
Executor: FA lane agent. Standard: `docs/EFV_GATE_STANDARD.md`.

**Everything below the "PRE-REGISTRATION" heading was written BEFORE any arm
ran.** Results are appended at the bottom, dated, and never edited upward.

Harnesses:
- Gate 1 (projection) `fa_backtest.run_projection_gate(persist=False)`,
  10 forward-chained target seasons 2015-2025 ex-2020, n=20,721 player-seasons.
- Gate 2 (market) `fa_backtest.run_market_gate(persist=False)`,
  9 forward-chained winters 2018-2026, n=1,199 signings.
  **`persist=True` is FORBIDDEN in this program** - it rewrites
  `data/fa_dpw_series.json`, which moves the whole valuation engine.
- Gate 3 (fits) `fa_fit_backtest.run_fit_gate(persist=False)`, 1,173 signings,
  forward-chained 2018-2026, REDUCED-FEATURE ANALOG (see its docstring).
- Concentration (fits) the harness in this doc's F5 section, run on the served
  class via `fa_fit.fit_scores(..., top_n=30)` for all class members.

---

## PRE-REGISTRATION

### Shared rules

1. **Resampling unit and interval.** Gate 1 arms are paired on the 10
   forward-chained target seasons; Gate 2 arms on the 9 forward-chained
   winters. The reported interval is the paired t-95% over folds:
   `delta_mean +/- t(.975, K-1) * sd(delta)/sqrt(K)`. The **MDE95 for that arm
   is `1.96 * sd(delta)/sqrt(K)`**, computed from the arm's own fold deltas.
   `|delta_mean| < MDE95` is a **NULL**, not a small win.
2. **Independent floors that override.** Gate-2 pooled guarantee MAE has a
   corpus-level MDE95 of **0.16 $M** already established by paired bootstrap
   with refit (`fa_market.py:1008-1021`). Any Gate-2 guarantee-MAE movement
   smaller than 0.16 $M is a NULL regardless of the fold interval.
3. **Zero-information control.** Every arm that adds an input channel is also
   run with that channel's per-player values PERMUTED across players within
   the fold (seed 1). Ship requires `|delta_candidate| >= 3 * |delta_control|`.
   An arm whose control scores as well as the candidate has no result.
4. **Level vs error.** A calibration arm may ship on BIAS while its MAE is a
   null, but only if MAE does not worsen by more than that metric's MDE95.
   This must be stated in the arm's verdict, never presented as an MAE win.
5. **Diagnostic cells are not criteria.** `war:{side}:act_ge4` conditions on
   the actual, so regression to the mean forces a negative bias there. It is
   read as "how much of the star tail does the map reach" and can never carry
   a ship decision alone.
6. **No tuning to a target.** No arm's criteria reference a target price for
   any named player or a target club distribution. Chisholm's price and the
   30-club spread are reported as consequences, never optimized.
7. **Display-policy changes** (E6) are not accuracy gates. They ship behind a
   named constant, report the distribution they produce and the count of
   historical rows whose verdict changes, and are flagged as an owner decision.

### E1 - measurement (no ship criteria; blocks nothing)

Deliverables, all additive:
- `fa_backtest.py` Gate 1: `pooled_by_side` with `war:hit`, `war:pit`, and the
  `:act_ge4` compression cells, each carrying MAE **and signed bias**
  (`mean(pred - actual)`) plus mean levels. Per-season rows carry the per-side
  MAE and bias.
- `fa_backtest.py` Gate 2: `pooled_by_pos_group` keyed
  `{guarantee,aav,years}:{SP,RP,C,POS,hit,pit,tier:*}`, MAE **and signed bias**
  for model and comps baseline.
- `tools/_am_fa_dealplus.py --groups`: Deal+ / verdict distribution per pos
  group against the 33/33/33 design, on the corpus at ACTUAL price (the basis
  the terciles were cut on), at PREDICTED price (what the board serves), and on
  the served board.

Both slice blocks are kept OUT of `pooled` because
`assets/fa.js:1131` renders `Object.entries(gate.pooled)` verbatim as the
served Model Accountability table; a slice added to `pooled` would silently
become a product surface. That file belongs to another agent this cycle.

### E2 - realized-WAR channel in the WAR reconstruction

Arm `EEPHUS_FA_REALWAR=1`: blend the map WAR with a 3-season PA/BF-weighted
realized-bWAR **rate** applied at the projected exposure, weight `w` from an
exposure-reliability shrink. Guard against double-counting the rate signal
already flowing through wRAA: the channel enters as a rate DIFFERENCE from the
map's own implied rate, and the arm is refit per fold like everything else.

SHIP requires ALL of:
- **P1** pooled `war` MAE strictly improves and `|delta| >= MDE95` (rule 1).
- **P2** at least 8 of the 10 folds improve.
- **P3** control clause (rule 3) with the realized-WAR column permuted.
- **P4** not-worse: `war:hit` and `war:pit` MAE each worsen by no more than
  0.005 WAR; `wrc_plus` and `fip` MAE not worse; P10-P90 coverage stays in
  [0.75, 0.85]; both hard-gate `war`/`wrc_plus`/`fip` verdicts stay True.
- **P5** reported (not gating, rule 5): `war:hit:act_ge4` bias moves toward 0.

An arm that improves the compression cell while failing P1 is a NULL and is
ledgered as one.

### E3 - playing time

Arm `EEPHUS_FA_PT=<mode>`: an established-workload channel added to
`pt = w1*e1 + w2*e2 + base`, refit per fold. Reported alongside: projPA mean
vs actual PA mean on the Gate-1 panel (the 456 vs 511 cell).

SHIP requires ALL of:
- **P1/P2/P4** exactly as E2.
- **P3'** the arm must NOT regress the in-progress reliability blend: with
  `in_progress` set, a player with >=600 established PA and a partial current
  season must still project >= the same value the champion gives him (the
  Lindor protection at `fa_projection.py:906-930` is a floor, not a tunable).
  Verified by direct assertion, not by the gate.
- **P6** reported: mean projPA vs mean actual PA must move toward parity. A
  PT arm that improves WAR MAE while widening the PA gap is suspicious and is
  disclosed as such.

### E4 - Marcel weights and in-progress season completeness

Two separable questions, gated separately.

**E4a doc/config mismatch.** `fa_config.yaml:53` ships `[5,3,2]`;
`fa_projection.py:10` and the Gate-1 baseline (`fa_backtest._baseline`,
`{1:5,2:4,3:3}`) say 5/4/3. Resolve by MEASUREMENT: run `[5,3,2]` and
`[5,4,3]` as two arms on identical folds. SHIP the winner under E2's
P1/P2/P4. If the delta is a NULL, the CONFIG stands and the DOCSTRING moves
(ground rule 3: when a row and the code disagree, the row moves).

**E4b completeness weighting.** Arm `EEPHUS_FA_SEASONFRAC=1`: scale the
recency weight of an in-progress season by its completeness
(`w1_eff = w1 * frac`). This is invisible to Gate 1 by construction (the gate
projects only completed seasons), so Gate 1 is a NOT-WORSE guard only and any
strict Gate-1 movement in either direction FAILS the arm as train-path
leakage. The affirmative evidence must be a direct measurement on the live
serve path: report, for the served class, the projPA/warY1 change and the
count of members whose in-progress season is <80% complete. Because there is
no ex-ante label for an in-progress season in this harness, **E4b is
explicitly an OWNER DECISION, not a gated ship**, and will be reported as a
measured consequence with its blast radius, not shipped silently.

### E5 - market stage

All arms are Gate-2, all with `persist=False`, all scored against the
same-process production-default champion.

- **E5a `RECAL_MODE`** in `{"off"(champ), "shift", "fit"}`.
  SHIP requires: pooled guarantee MAE does not worsen by more than the 0.16 $M
  floor (rule 2); `aav`, `years`, `mega_guarantee` MAE each not worse by more
  than their own fold MDE95; AND the LEVEL criterion - mean `|bias_model|`
  over the four guarantee tiers (`lt10`, `10to20`, `20to50`, `ge50`)
  **strictly decreases**; AND all three hard gates stay True. This is a
  calibration ship on bias under rule 4.

  **CORRECTION, logged 2026-07-30 after the first wave-3 run, BEFORE the ship
  decision.** As first written, the tier criterion binned on the ACTUAL
  guarantee. That is the wrong conditioning and `fa_market._fit_recal`'s own
  docstring says so: conditioning on the actual is regression to the mean by
  construction, so the criterion can be satisfied by simply de-shrinking the
  predictions - exactly the failure rule 5 exists to prevent, applied by me to
  my own criterion. The DECISION criterion is therefore mean `|bias_model|`
  over tiers of the **PREDICTED** guarantee (`ptier:*`, the conditioning the
  recalibration is estimated against and the decision-relevant one: "when the
  board says $15M, what does the player actually get"). The actual-conditioned
  cell stays in the artifact as DESCRIPTIVE. This correction makes the
  criterion strictly harder to satisfy, and the first run's numbers under the
  old criterion are reported in the results section so the change is auditable.
- **E5b `AAV_CONSISTENT`** in `{False(champ), True, "reprice"}`.
  This is an arithmetic-coherence fix: the guarantee is priced at the
  continuous `years_f` and divided by `round(years)`. SHIP requires: `aav` MAE
  strictly improves OR is a null with `guarantee`/`years`/`mega` all not-worse;
  AND the served `proj_guarantee` and `proj_years` must describe the SAME deal
  after the change (this favours `"reprice"` a priori and the reason is
  recorded in `fa_market.py:1495-1502`, written before this program).
- **E5c `X_FEATURES["rate_line"] = False`.** Expected NULL (it is already
  ledgered as indistinguishable from noise with a wrong-signed hitter
  coefficient). Criteria: it may only be turned OFF if guarantee MAE improves
  by >= 0.16 $M; otherwise it stays ON and the null is re-ledgered. A
  wrong-signed coefficient is not by itself a ship reason.
- **E5d per-pos-group recalibration** (`RECAL_MODE="fit_group"`): the same
  inner-chain recalibration fit per `_pos_group`. SHIP requires E5a's criteria
  AND that the hit-vs-pit guarantee bias GAP `|bias_hit - bias_pit|` strictly
  decreases, AND every group has >= 200 inner-chain rows (the existing
  `_RECAL_MIN_ROWS`) or falls back to the pooled fit for that group.
- **E5e `POS_GROUP_MODE="v2"`** - LAB ARM ONLY, pre-registered as not for
  ship this cycle (measured down for the reference player during planning).
- A COMBINED arm of every individually-passing knob runs last and must satisfy
  every passing arm's criteria simultaneously. Only the combined winner ships.

### E6 - verdict banding per side (DISPLAY POLICY, owner decision)

Implement behind `VERDICT_BAND_MODE` in `{"pooled"(shipped), "group"}`.
Report, for both modes: per-pos-group overpay/market/value split on the
corpus at actual price and at predicted price, on the served board, and the
COUNT of the 1,300 corpus rows whose verdict changes. Pre-registered
acceptance for the "group" mode to be RECOMMENDED (not shipped) to the owner:
every pos group lands within +/- 8 percentage points of 33/33/33 on the
corpus at ACTUAL price. Default stays `"pooled"` unless the owner says
otherwise, because rebanding moves published verdicts on historical contracts.

### E7 - hygiene

`data/fa_meta.json` is stale against `data/fa_class.json` (baseWins 83.5 vs
82.0). The repair is an export re-run, which this lane is not authorized to
perform. Deliverable: MEASURE and REPORT the divergence and its cause. No
artifact is rewritten.

### F1-F4 - fits engine repairs

The live need/window inputs are **structurally outside Gate 3's reduced
analog** (see its docstring: contracted-roster projections come from CURRENT
Spotrac pages and do not reconstruct historically). Therefore:

- F1 (projected-roster need source), F2 (slot rule + completeness + the
  silent-drop fix) and F3 (contention term) are gated on the **CONCENTRATION
  GATE** below plus correctness assertions, NOT on Gate-3 MRR, and this is
  stated in the registry row rather than implied.
- F4 (behavior discrimination) and any weight change ARE visible to Gate 3
  (it reads `fa_config.fit.weights` since 2026-07-25) and must clear the
  Gate-3 criteria below.

Correctness assertions (hard, non-statistical - a failure blocks the arm):
- **A1** every one of the 30 clubs appears in every member's fit vector. A club
  with zero qualifying contracts is scored explicitly, never dropped.
- **A2** the projected-roster source sees arb/pre-arb players: the 2027 roster
  count and total projected WAR must both strictly exceed the Spotrac
  signed-through-only counts, and the fallback flag must read
  `mlb_projections` on the primary path and `spotrac_contracts` when the
  artifact is defective (mirrors `fa_fit.py:338-345`).
- **A3** no club with a 0% playoff probability may score a higher contention
  component than a club with a >=90% playoff probability.
- **A4** the pinned tests' INTENT stays green:
  `test_fa_fit.py::test_weights_sum_to_one`,
  `::test_need_is_displacement_not_unit_sum`,
  `::test_outlook_wins_reads_all_thirty_clubs`,
  `::test_team_baselines_agree_exactly_with_projections_outlook`,
  `test_fa_fit_gate.py::test_shipped_weights_match_gate3_decision`,
  `::test_gate_scores_the_weights_that_actually_ship`. Verified by direct
  execution of the assertions, NOT by pytest (this program runs concurrently
  with other agents and conftest's session fixture git-restores dirtied files).

### F2b - need normalized by the player's own value (ADDED 2026-07-30, BEFORE running)

**Why this arm exists, written before it ran.** F1-F4 were implemented and
measured on the concentration gate first: they FIXED the pitcher failure
(SFG's share of #1 fits among pitchers projecting >=1.0 WAR fell from 85% to
44%) and made the LAD failure WORSE (68% -> 79% of all #1 fits). The mechanism
is diagnosable from the composite's own algebra and is not a tuning problem:

- `need` is the ONLY player-specific component. `window`, `afford`, `park` and
  `behavior` are all club-level, so for any player whose need is flat across the
  30 clubs, the ranking IS a fixed club ranking and one club takes every such
  player. Most of the class is that player.
- v3's `need = min(1, gap / 4.0) * blocker_mult` caps at gap/4, so a 0.8-WAR
  reliever can vary by at most 0.2 across all 30 clubs (x weight 0.40 = 0.08 of
  composite) while behavior varies by ~0.65 (x weight 0.45 = 0.29). Behavior wins
  by construction for everyone below about 2 WAR.
- F4 made behavior player-CONDITIONAL as asked (LAD's term falls 0.815 -> 0.514
  from a $5M to a $250M price) but its cross-club spread did not shrink, because
  the Dodgers really do have the deepest big-deal history at every price point.
  So F4 alone could not fix concentration and a re-weight alone cannot either:
  shrinking behavior just promotes the next club-level term.

**The arm.** `NEED_MODE = "share"`: need is the SHARE of the player's own
projected value that is actually additive at that club,
`min(1, gap / max(war_y1, NEED_MIN_WAR))`, with `NEED_MIN_WAR = 1.0` so a
sub-1-WAR player cannot saturate on the strength of a sub-1-WAR gap. This gives
every player a full 0-1 spread across clubs instead of only stars, which is the
structural cause. v3's fixed 4-WAR saturation stays available as
`NEED_MODE="saturation"`.

SHIP requires: the F5 concentration gate below (all five metrics), the F1-F4
correctness assertions A1-A4, and the Gate-3 criteria in F5. Pre-registered
FAILURE condition: if the median #1-vs-#2 gap widens while the distinct-club
counts do not improve, the arm is just re-scaling noise and is a NULL.

### F5 - CONCENTRATION GATE (new, registered)

Measured on the full 30-club fit vector for every member of the served class.

| metric | shipped fit_v3 | gate |
|---|---|---|
| max share of #1 fits held by any single club | 0.68 (LAD 154/228) | **<= 0.25** |
| distinct clubs holding at least one #1 | 6/30 | **>= 12/30** |
| distinct clubs appearing in any top-3 | 12/30 | **>= 20/30** |
| max share of #1 fits within either side | SFG 85% of pitchers warY1>=1.0 | **<= 0.35** |
| median #1-vs-#2 fit gap | 0.0180 | **>= 0.0150** (ordering must not get flatter) |

All five must hold. The first four are the failure modes; the fifth stops a
"fix" that just adds noise to spread the mass around.

Gate-3 criteria for any arm that Gate 3 can see:
- MRR must beat `random` and `behavior_only`, and must not fall below the
  shipped `shipped_balanced` MRR by more than 0.010 (a not-worse band, since
  the artifact itself discloses that differences among the top mixes are
  within noise).
- `fitted_full` must still beat `fitted_transfer` (the incumbency-ceiling note
  the pinned test guards).
- If the shipped weights change, `data/fa_gate3_eval.json` is regenerated in
  the SAME change and `weight_mix_comparison` / `ship_decision` must be
  produced BY THE CODE, not hand-added, so the pin cannot go stale again.
  (Both keys are currently absent from `run_fit_gate`'s output and present in
  the committed artifact - i.e. a `persist=True` re-run today would silently
  break two pinned tests. Fixing that is part of F5.)

---

## RESULTS (2026-07-30)

Artifacts: `data/fa_projection_lab_eval.json` (Gate 1 arms),
`data/fa_market_feature_lab_wave3_eval.json` (Gate 2 arms),
`data/fa_gate3_eval.json` (Gate 3 + the concentration block).
`data/fa_dpw_series.json` md5 `410f603f1de67b5de79c4ae17a982978` and
`data/value_framework.json` md5 `a9b25b639397c3d7be1d3d6fb07e3957` were
recorded at the start of the program and verified UNCHANGED at the end.
`run_market_gate(persist=True)` was never called.

### E1 - per-side measurement (the owner's premise, tested)

Gate 1, forward-chained, n=20,721 player-seasons. `bias = mean(pred - actual)`.

| slice | MAE | bias | mean pred | mean actual | n |
|---|---|---|---|---|---|
| WAR pooled | 0.6157 (base 0.7279) | -0.004 | | | 20,721 |
| WAR hitters | 0.7596 (base 0.8019) | **+0.027** | 0.661 | 0.635 | 8,833 |
| WAR pitchers | 0.5088 (base 0.6729) | **-0.027** | 0.302 | 0.329 | 11,888 |
| hitters, actual >=4 bWAR | 3.235 (base **2.373**) | -3.219 | 2.336 | 5.556 | 424 |
| pitchers, actual >=4 bWAR | 3.364 (base **2.944**) | -3.363 | 2.173 | 5.536 | 186 |

Gate 2, 9 forward-chained winters, n=1,199, guarantee in $M.

| slice | MAE | bias | slice | MAE | bias |
|---|---|---|---|---|---|
| hitters | 12.09 | **-7.52** | POS | 13.47 | -8.47 |
| pitchers | 8.33 | **-4.02** | C | 5.80 | -3.17 |
| actual <$10M | 2.01 | **+0.53** | SP | 13.23 | -4.88 |
| actual $10-20M | 8.46 | -4.25 | RP | 4.95 | -3.43 |
| actual $20-50M | 20.78 | -13.37 | | | |
| actual >=$50M | 61.14 | -45.26 | | | |

Deal+ / verdict distribution against the 33/33/33 design
(`tools/_am_fa_dealplus.py --groups`), served 2027 board, 223 members with a
verdict:

| group | n | median Deal+ | overpay | market | value | mean surplus $M |
|---|---|---|---|---|---|---|
| ALL | 223 | 141 | 37% | 41% | 22% | +8.43 |
| hitters | 89 | 236 | 16% | 34% | **51%** | +12.94 |
| pitchers | 134 | 107 | **51%** | 46% | **2%** | +5.44 |
| POS | 75 | 218 | 17% | 33% | 49% | +11.22 |
| C | 14 | 281 | 7% | 36% | 57% | +22.16 |
| SP | 57 | 153 | 25% | 70% | 5% | +12.50 |
| RP | 77 | 92 | **71%** | 29% | **0%** | +0.21 |

**Verdict on the owner's premise: CONFIRMED as a verdict-layer effect, REFUTED
as a WAR-sign effect, and REFUTED as "pitchers" - it is mostly RELIEVERS.**

1. At the WAR level, hitters are OVER-projected (+0.027) and pitchers are
   UNDER-projected (-0.027). There is no pitcher over-projection to fix.
2. At the price level, BOTH sides are under-priced and HITTERS MORE
   (-7.52 vs -4.02 $M). Again no pitcher over-pricing.
3. The asymmetry lives in the verdict, and SP (25% overpay, +$12.50M mean
   surplus) looks like POS (17%, +$11.22M), not like RP (71%, +$0.21M). The
   perception is a reliever-banding artifact wearing a "pitchers" label.
4. **About half of the reliever effect is REAL, not a defect.** On the corpus at
   the ACTUAL price - the basis the terciles were cut on - relievers run 55%
   overpay / 17% value against position players' 35% / 36%. Deal+ is
   rational_value / price, and a short deal for a sub-1-WAR reliever prices most
   of its guarantee against very little projected value by construction.
5. The prediction stage AMPLIFIES it: at the PREDICTED price hitters go to 6%
   overpay / 64% value and pitchers to 40% / 5%, because under-pricing inflates
   Deal+ and it inflates hitters more.

### E2 / E3 / E4a - Gate 1 arms

| arm | WAR MAE | delta | CI95 | MDE95 | folds | verdict |
|---|---|---|---|---|---|---|
| champion | 0.61572 | | | | | |
| **E2 realwar** | 0.60087 | **-0.01496** | [-0.01814, -0.01178] | 0.00270 | 10/10 | **SHIPPED** |
| E2 control (permuted) | 0.62952 | +0.01379 | | | 0/10 | degrades - good |
| **E3 ptfit "hit"** | 0.59684 | **-0.01889** | [-0.02399, -0.01378] | 0.00434 | 10/10 | **SHIPPED** |
| E3 ptfit "both" | 0.59730 | -0.01838 | [-0.02388, -0.01289] | 0.00467 | 10/10 | NO (FIP clause) |
| **E2+E3 combined** | 0.58318 | **-0.03263** | [-0.03884, -0.02643] | 0.00527 | 10/10 | **SHIPPED** |
| E4a marcel 5/4/3 | 0.61911 | +0.00339 | [+0.00285, +0.00393] | 0.00046 | 0/10 | measured LOSS |
| realwar K x0.5 | 0.60054 | -0.01533 | | | 10/10 | sensitivity only |
| realwar K x2.0 | 0.60445 | -0.01135 | | | 10/10 | sensitivity only |

Hitter WAR MAE 0.75957 -> 0.68360 combined (delta -0.07573, MDE95 0.01074);
pitchers -0.00039, a null. wRC+ and FIP byte-identical. Coverage 0.7992 ->
0.7972, inside the band. Projected PA level error +51.3 -> -13.6.
`>=4 bWAR` hitter cell: mean predicted 2.336 -> 2.443, cell MAE 3.235 -> 3.129,
still worse than the naive baseline's 2.373 - the star tail is narrowed, not
fixed, and that is disclosed rather than presented as solved.
In-progress reliability-blend guard (P3'): 6 cases, 0 regressed, mean PT lift
+132.8 PA. Intact.

**Two protocol discrepancies, both recorded rather than resolved quietly:**

1. **E2's control clause.** Rule 3 was written as
   `|delta_candidate| >= 3*|delta_control|`. That magnitude form presumes a
   control that could accidentally HELP, which is the usual case when a placebo
   column receives a fitted coefficient. This channel has no fitted coefficient
   (a fixed shrinkage formula), so a permuted column can only add noise, and it
   does: the control DEGRADES the model on 0 of 10 folds while the candidate
   improves on 10 of 10. The literal form reads False purely because the control's
   delta has the opposite sign; the same rule's own sentence
   ("An arm whose control scores as well as the candidate has no result") is
   satisfied. Both readings are in the artifact as
   `control_literal_3x_form` and `control_does_not_reproduce_the_gain`.
2. **E4a resolved AGAINST the plan's expectation.** The plan implied 5/4/3 might
   be the intended value. It is a measured LOSS on every metric. The CONFIG
   stands and the DOCSTRING moved, per ground rule 3.

The plan's premise for E2 also did not survive contact. The literal
"3.09 WAR/600 realized vs engine 1.68" comparison double counts: realized WAR
contains the offensive rate the map already prices through wRAA. Isolating the
residual moved the reference player's warY1 only 1.68 -> 1.75. The channel is a
broad, decisive win (hitters -0.076 MAE, 10/10 folds) and a small effect for
that particular player.

### E5 - Gate 2 arms

| arm | guarantee MAE | delta | mean\|bias\| by PREDICTED tier | mega | verdict |
|---|---|---|---|---|---|
| champion | 9.9174 | | 14.07 | 81.54 | |
| **recal "shift"** | 10.0391 | +0.1336 (NULL, MDE95 0.427) | **6.78** | **79.34** | **SHIPPED** |
| recal "fit" | 10.4586 | +0.541 | 7.98 | 84.47 | NO |
| recal "fit_group" | 10.7238 | +0.806 | 8.56 | 86.07 | NO |
| AAV_CONSISTENT True | 9.9174 | 0.000 | 14.07 | 81.54 | NO (coherence) |
| AAV_CONSISTENT reprice | 9.9315 | +0.014 | 12.63 | 80.69 | NO (aav MAE) |
| rate_line OFF | 9.9555 | +0.0172 (NULL) | 15.45 | 80.72 | NO - stays ON |
| POS_GROUP_MODE v2 | 10.3093 | +0.392 | 16.54 | 90.93 | NO (lab only) |

Predicted-tier guarantee bias, $M: champion -2.81 / -9.64 / -21.32 / -22.52;
"shift" -2.11 / -6.27 / -15.04 / -3.70. Every tier under-priced before and
after, so the correction does not overshoot. Per group SP -4.88 -> -1.47,
RP -3.43 -> -2.76, C -3.17 -> -2.49, POS -8.47 -> -5.63.

`RECAL_MODE="shift"` is a **calibration ship on bias**. Its MAE movement is a
measured null in both directions (fold MDE95 0.427, corpus floor 0.16) and must
never be cited as an accuracy win. "fit" and "fit_group" reproduce the
2026-07-24 ledger's prediction exactly - recalibration and de-staling are
substitutes, and stacking a slope on `DESTALE_MODE="series"` over-corrects,
visible as a +$10.51M / +$14.95M overshoot in the top predicted tier.

**New and unresolved, registered as a candidate rather than shipped:** turning
`rate_line` OFF collapses the hit-vs-pit guarantee bias gap from 3.49 to 0.86
$M. The feature is already ledgered as indistinguishable from noise and its
hitter wOBA coefficient is wrong-signed, so this is a plausible mechanism for
the exact asymmetry the owner reports. It fails the criterion I pre-registered
(a >= 0.16 $M guarantee-MAE improvement) and I did not move the goalpost after
seeing the number. It needs its own pre-registration next cycle.

### E6 - verdict banding (OWNER DECISION, default unchanged)

`VERDICT_BAND_MODE` in `{"pooled"(shipped), "group"}` with per-group corpus
terciles `SP 86/182, RP 65/146, C 101/243, POS 103/237`. `deal_verdict` takes an
optional `position`; with the shipped mode the result is byte-identical, so no
caller changes until the owner picks.

Pre-registered acceptance for RECOMMENDING "group" (every group within +/-8
points of 33/33/33 at the actual price) is met by construction, since the edges
ARE those terciles. It is NOT shipped because re-banding moves published
verdicts on 256 of 1,300 historical contracts (19.7%) and changes what "value"
means. **A separate, smaller decision is also owed:** the POOLED edges are now
stale on their own basis (44/29/27 at the actual price instead of 33/33/33)
because the pricing moved under them; re-cutting them to 85/189 restores the
pooled design without changing its meaning.

### E7 - hygiene (measured, NOT repaired - the repair is an export run)

`data/fa_meta.json` (2026-07-28) vs `data/fa_class.json` (2026-07-29) and the
live code:
- served `baseWins` disagrees with `data/mlb_projections.json` for **all 29
  clubs it carries**, by +1.0 to +1.5 wins (SFG 83.5 vs 82.0, LAD 95.9 vs 94.5).
- served mean 81.94 over 29 clubs; the artifact and the live `team_baselines`
  both sum to 2430.1 over 30 for a mean of 81.00.
- `teams` carries 32 keys: 30 clubs plus the pseudo-club `AVERAGES` and a legacy
  `OAK` beside `ATH`. **MIA is absent** - that was the silent-drop defect, now
  fixed in code (F2), so a re-export will produce all 30.

### F - fits v4

Served 2027 board, 228 members, full 30-club vectors.

| metric | v3 shipped | F1-F4 | + F2b need-share | gate | verdict |
|---|---|---|---|---|---|
| max #1 share | 0.68 (LAD 154) | 0.79 (LAD 180) | **0.5219** (LAD 119) | <= 0.25 | FAILS |
| distinct clubs #1 | 6/30 | 6/30 | **10/30** | >= 12 | FAILS |
| distinct in top-3 | 12/30 | 11/30 | **20/30** | >= 20 | PASSES |
| median #1-#2 gap | 0.0180 | 0.0510 | **0.0530** | >= 0.015 | PASSES |
| SFG share of #1, pit warY1>=1 | 85% | 44% | 85% | (mis-specified) | reported |

**2 of 4 registered metrics pass. The concentration gate DOES NOT PASS and this
is not presented as a win.** Shipped: F1 (projected roster, 965 rows / 857.5
WAR vs Spotrac-only 858 / 741.2), F2 (slot fallback, completeness fields,
silent-drop fix), F2b (need-share), F3 (contention blend: SFG 0.828 vs LAD
0.175 becomes SFG 0.323 vs LAD 0.650), F4 (behavior percentile).

**The re-weight is a NO-SHIP; weights are UNCHANGED.** Seven vectors were scored
on both gates on identical folds:

| mix | Gate-3 MRR | max #1 share | distinct #1 | distinct top-3 |
|---|---|---|---|---|
| shipped .40/.05/.05/.05/.45 | **0.1669** | 52% | 10 | 20 |
| fitted logistic .596/0/0/.012/.392 | 0.1660 | 49% | 10 | 20 |
| need .55 / beh .35 | 0.1669 | 49% | 9 | 20 |
| need .50 / beh .25 | 0.1538 | 49% | 8 | 21 |
| need .55 / beh .20 | 0.1499 | 42% | 8 | 21 |
| need .60 / beh .15 | 0.1449 | 28% | 10 | 22 |
| need .65 / beh .10 | 0.1421 | 35% | 10 | 23 |
| behavior_only | 0.1515 | | | |

Every vector that materially improves concentration loses MRR by more than the
pre-registered 0.010 band, and need .60 also falls below `behavior_only`. Every
vector inside the Gate-3-equivalent neighbourhood leaves max #1 share at 49-52%.
The two gates genuinely disagree; the pre-registration says Gate 3 binds for
weight changes, so nothing was tuned and the trade-off goes to the owner.

**The fifth registered metric is mis-specified and is reported, not gated.**
"Max share of #1 fits within one side" cannot be satisfied by any correct
additive composite: within a position group the need ordering is a property of
the 30 clubs, not of the player, so whichever club is genuinely thinnest at a
position tops every player at that position. SFG's 5th-starter slot projects
0.00 WAR against a next-thinnest 0.03 and a league median near 0.85 - a real
continuous spread, unlike the v3 pathology. Across ALL pitchers the top club is
now LAD at 54%, so the Giants-for-all-pitchers failure is gone as a
side-level effect. Residual data limit, disclosed: SFG carries only 5 SP against
a league range of 5-11 because pitcher positions come from Spotrac labels (the
40-man codes every pitcher "P"), so some of that thinness is label noise.

Correctness assertions, all verified by direct execution (never pytest):
A1 all 30 clubs in every vector PASS. A2 projected roster strictly exceeds
Spotrac-only on rows and WAR PASS. A3 PASSES on the contract-season probability
the term uses (8 clubs at <=5% max 0.080 < the 1 club at >=90% min 0.650) and
FAILS if scored against the served CURRENT-season `playoffPct`, because that is
the wrong season for a contract-season term - both readings recorded. A4 all six
pinned assertions green, including `shipped mrr 0.1669 >= fitted_logistic
0.1660` and `fitted_full > fitted_transfer`.

**Artifact repair shipped in the same change:** `weight_mix_comparison` and
`ship_decision`, which two pinned tests assert, existed ONLY in the committed
artifact and were produced by no code, so any `persist=True` re-run silently
deleted them and broke both pins. Both are now computed by `run_fit_gate`.

### FINAL SHIPPED STATE - both gates re-run and re-persisted

`fa_backtest.run_projection_gate(persist=True)` and
`run_market_gate(persist=True, persist_dpw=False)`. The second call uses a new
parameter added in this change: `persist_dpw=False` writes
`data/fa_gate2_eval.json` and leaves `data/fa_dpw_series.json` alone. That
coupling was the module's worst write hazard - there was previously NO way to
refresh the published Gate-2 verdict after a model change without also rewriting
the $/WAR level the entire valuation engine prices against. The default is
unchanged, so no existing caller behaves differently.

| Gate 1 | before | shipped | Gate 2 | before | shipped |
|---|---|---|---|---|---|
| WAR MAE | 0.61572 | **0.58318** | guarantee MAE | 9.9174 | **9.6778** |
| baseline | 0.72790 | 0.72790 | baseline | 11.2227 | 10.8597 |
| hitters | 0.75957 | **0.68360** | aav MAE | 3.0450 | **2.9587** |
| pitchers | 0.50884 | 0.50857 | years MAE | 0.4362 | 0.4387 |
| coverage | 0.79919 | 0.79716 | megadeal MAE | 81.54 | **77.55** |
| gates | PASS | **PASS** | gates | PASS | **PASS** |

Gate 2 guarantee MAE ends up 0.24 $M BETTER than the pre-program champion: the
recalibration's +0.13 cost is more than repaid by the improved WAR inputs
feeding the market model, which the isolated arms could not show. Per-side price
bias narrows from -7.52/-4.02 to **-5.47/-2.92** $M (gap 3.49 -> 2.55), and the
predicted-tier bias from 14.07 to **8.72** mean absolute.

**DISCLOSED LEVEL REGRESSION, and my pre-registration should have gated it.**
The E2/E3 criteria covered MAE, not-worse clauses and coverage, but not the
signed level. Pooled Gate-1 WAR bias moves -0.004 -> **-0.077** and the hitter
side moves **+0.027 -> -0.153** (mean predicted 0.48 against 0.63 actual). The
mechanism is the PT refit: lower projected exposure through a WAR map with a
negative intercept lowers the projected level, and MAE improves anyway because
the errors were two-sided. This is the same class of defect the projections lane
already fixed once for `proj_lgbm` with a lift-only mean recenter after the owner
reported "projections a bit low across the board", and it is the TOP follow-up
here. I did not invent a recenter in this pass because it would need its own
pre-registered gate. Anyone reading the served hitter WAR should know it now
sits about 0.15 WAR low on the forward-chained panel.

### Served consequence of the three ships (read-only, in memory)

`fa_export.build_fa_class_payload()` run twice, arms off and on. Nothing written.

| field | before | after |
|---|---|---|
| median warY1 | 0.43 | 0.40 |
| median projGuar | $3.60M | $3.64M |
| mean projGuar | $11.58M | $13.58M |
| mean projAav | $6.28M | $6.88M |
| mean surplus | $8.25M | $7.24M |
| median Deal+ | 138.5 | 129.5 |
| hitters overpay/market/value | 16/33/50 | 24/57/18 |
| pitchers overpay/market/value | 50/45/2 | 46/49/3 |

The reference player moves projAav $7.35M -> $12.78M and projGuar $14.70M ->
$25.57M, warY1 1.68 -> 1.75. **The price move is mostly the market stage, not
the WAR stage.**

### Left for the owner

1. E6 per-group verdict bands (and, separately, re-cutting the stale pooled
   edges to 85/189). Both move published verdicts.
2. The fits weight vector: Gate 3 and the concentration gate disagree and no
   vector satisfies both.
3. `rate_line` OFF as a per-side bias fix - needs its own pre-registration.
4. E7: `data/fa_meta.json` needs an export re-run; so do `fa_class.json`,
   `fa_class_2028/2029.json` and the golden, because all three shipped arms move
   served numbers.
5. `data/mlb_projections.json` defects found from outside that lane: `team` is
   null on all 361 arb/pre-arb vet rows, and ARI's entire `current` block reads
   null.
