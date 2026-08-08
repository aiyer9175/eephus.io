# SURPLUS DECOMPOSITION ON THE v6 EV FRAME, AND THE GATE CURRENCY

Lane C4, program 2026-08-07b. **This section is written BEFORE the lab runs.**
Everything below the `## RESULT` marker is appended after the run and nothing above
that marker is edited afterwards.

Owns: `tools/surplus_decomposition_lab.py`, `data/surplus_decomposition_v6.json`,
this file. READ-ONLY on `value_framework.py` and `surplus_backtest_real.py`.

## 0. What is stale and what is being asked

`docs/EFV_FRONTIER_AUDIT.md` section 4 published

    incumbent board                                 MAE $13.473M
    perfect ranking, same served FV multiset        MAE  $5.677M
    perfect 6yr-WAR foresight, grade unconstrained  MAE  $3.558M

read as **58% ranking / 16% level / 26% pricing floor**, n=2,236 resolved listings.
Those stages ran under seed 20260724, i.e. BEFORE two frame changes:

1. **2026-07-25** the listing consensus moved from the RAW per-source FV median to the
   NORMALIZED one (`surplus_backtest_real.FV_SCALE`, default now `normalized`), because
   production prices on the normalized consensus.
2. **2026-07-31** the dollar calibration moved from `linearmap-v5` (floored linear,
   `corrected = max(0, 1.382491*raw - 2.318551)`, zero-cross raw $1.677M) to
   `isotonic-real-v6-evframe-2026-07-31`, whose bottom knot is `y=0.67`, **removing the
   $0 floor**. Owner ruling `docs/efv-2026-07-30/SURPLUS_EV_OBJECTIVE.md`: surplus is an
   EXPECTED VALUE, so the map targets the conditional MEAN and knowingly loses v5's MAE.

The lane's question: the 26% "pricing floor" term should be GONE. Re-run and say where
it went.

The second and higher-value ask: `docs/EFV_GATE_STANDARD.md` section 4 quotes

> **+0.01 pooled eFV Spearman = -$0.0704M surplus MAE per prospect**
> CI95 [-0.0878, -0.0550], P(improves) = 1.000, n = 2,236

That conversion is quoted across this program to price rank claims in dollars. Re-derive
it on v6.

## 1. Known non-reproducibility, declared up front

A third change landed **2026-08-04**: the FA-implied $/WAR re-anchor (2026 winter
$14.92M -> $17.29M, trailing-3 mean $14.89M -> $16.61M). Every dollar in the engine moved
with it and it is NOT revertible from this lane (it lives in
`value_framework_config.yaml` / `data/fa_dpw_series.json`, neither of which this lane
owns or may write).

Therefore: **my "old frame" is a RECONSTRUCTION under today's win cost, not a replay of
the 2026-07-24 run.** My old-frame numbers are not expected to equal 13.473 / 5.677 /
3.558. The comparison that carries weight is OLD-vs-V6 **under identical code, identical
pool and identical win cost**, which is a clean 2x2. Any claim of the form "the published
number was X and is now Y" is reported as a reproduction check, not as a measurement.

## 2. The 2x2 frame grid

| factor | old level | v6 level |
|---|---|---|
| listing FV scale | `raw` (pre-2026-07-25 median) | `normalized` (production) |
| dollar calibration | `linearmap-v5` floored linear | `isotonic-real-v6-evframe` |

Four cells: `raw_v5` (= OLD), `norm_v5`, `raw_v6`, `norm_v6` (= **V6, production**).
The off-diagonal cells exist so "where did the floor term go" gets a mechanism, not a
before/after.

Held fixed in all four: the pool (`GATE_SCALE=raw`, so membership is the registered
3,368 listings / 2,236 resolved and only the FV *values* move), the active valuation set
(production default `clemens_2026`), the win cost, the discount rate, the realized-side
construction, and the code.

v5 is re-expressed exactly inside `apply_calibration`'s isotonic branch as knots
`x=[0.0, 1.677, 400.0]`, `y=[0.0, 0.0, 550.677849]`, which reproduces
`max(0, 1.382491*raw - 2.318551)` on `[0, 400]` to interpolation precision. That
reconstruction is itself checked (clause C0) and the check is reported whatever it says.
The config block is patched IN MEMORY on the cached dict and restored; no file is written.

## 3. Ladder definitions (exact, so a verifier can re-derive them)

Per resolved listing i: `t_i` = realized surplus PV = `backtest.realized_sv_pv`
(historical $/WAR per season, imputed salaries, discounted to the listing year).
`p_i` = the SERVED price = `apply_calibration(expected_surplus_usd(fv_i, ...)/1e6)`,
i.e. what the board shows, calibration included.

* **L2 INCUMBENT**: `p_i` as served.
* **L1 PERFECT RANK, SAME SERVED MULTISET**: the multiset `{p_i}` is unchanged; it is
  re-assigned so that its ascending order matches the ascending order of `t_i`.
  This is a permutation, so `mean(p)` is invariant by construction; that invariance is
  asserted in the artifact. (Note: the published ladder's L1 has a different `pred_mean`
  than its L2 in `tools/_frontier_out/_surplus_stageC.json`, which a permutation cannot
  do. The published ladder rung and the published headline label therefore do not
  describe the same object. Recorded as an observation about the prior record; my L1 is
  the label, not the stage-C rung.)
* **L0 PERFECT FORESIGHT, GRADE UNCONSTRAINED**: invert the engine's own FV->WAR map:
  find continuous `fv*_i` in [20, 80] with
  `expected_six_year_avg_war(fv*_i, side) * control_years == W_i`, where `W_i` is the
  realized control-window WAR (`backtest._realized_control_war`), then price `fv*_i` with
  the player's own age/eta through the same pricing path as L2. Clamps at both ends are
  counted in the artifact. This is "the model given perfect WAR foresight", so its
  residual error is the PRICING layer alone: win-cost curve, discount, salary model, and
  the calibration map.

`control_years` is 7 under `clemens_2026` while the realized window in
`surplus_backtest_real` is capped at 6 seasons. That mismatch is INHERITED from the
shipped harness (`backtest.decomposition` compares the same two quantities) and is held
identical across all four cells, so it cannot move the old-vs-v6 contrast. Flagged, not
fixed, because the harness is read-only to this lane.

## 4. The partition, and the residual clause (MANDATORY)

    S_rank  = (MAE_L2 - MAE_L1) / MAE_L2
    S_level = (MAE_L1 - MAE_L0) / MAE_L2
    S_floor =  MAE_L0            / MAE_L2

**This telescopes to exactly 1 by construction.** Saying "the shares sum to 1" is
therefore NOT evidence of anything; a wave-3 lane published 1.0267 and 1.0551 and the
fix is not to congratulate myself on 1.0000. The artifact asserts
`|sum - 1| < 1e-9` (clause C2) as an arithmetic tripwire only, and the honest residual
statement is the one below.

**The real residual is PATH DEPENDENCE.** The ladder fixes ranking first and level
second; the shares are order-dependent. I also run the reverse order:

* `L1B` = each player priced at their own `fv*_i` (perfect level) but the resulting price
  vector re-scrambled back into the INCUMBENT price order.
* Order B: `S_level_B = (MAE_L2 - MAE_L1B)/MAE_L2`, `S_rank_B = (MAE_L1B - MAE_L0)/MAE_L2`,
  same `S_floor`.

Reported: order A, order B, and their average (the two-player Shapley value), plus the
**interaction** `|S_rank_A - S_rank_B|`. If that interaction is large, the 58/16/26
framing is unstable regardless of which frame it is measured on, and I say so.

## 5. EV objective vs MAE arbiter

Owner ruling 2026-07-31: surplus is an EXPECTED VALUE. MAE is minimised by the
conditional MEDIAN, so an MAE decomposition is not the objective's decomposition.
Accordingly:

* **Arbiter (EV):** per-rung calibration slope, intercept, mean bias, 8-bin binned
  calibration, and the same three-way partition computed in **MSE** (whose minimiser is
  the conditional mean).
* **Diagnostic (comparability only):** the MAE partition, because that is the currency
  the published 58/16/26 and the published -$0.0704M are denominated in.

If the MAE and MSE partitions disagree about where the error lives, that disagreement is
the finding and is reported before either number.

## 6. The currency re-derivation

Reconstruction of the stage-H instrument. For a mixing weight `w`:

    u_inc   = rankdata(p, 'average') / n          # incumbent board order
    u_truth = rankdata(t, 'average') / n          # realized surplus order
    score   = (1 - w) * u_inc + w * u_truth
    board_w = the served price multiset re-assigned in ascending `score` order

then `rho_w` = Spearman(board_w, realized control WAR) and `mae_w` = MAE(board_w, t).
Currency over a segment [0, w]:

    currency(w) = (mae_w - mae_0) / ((rho_w - rho_0) / 0.01)      $M per +0.01 rho

The published figure is the `[0, 0.10]` segment. That is the segment I quote as THE
currency, so it is like-for-like.

Bands: player-clustered bootstrap, B=2000 for the ladder and B=2000 for the currency,
resampling PLAYER KEYS (a player contributes up to three listing-years and those are not
independent). Fixed literal integer seed 20260808; no RNG seeded from a string hash, no
iteration order taken from a set.

**Floor for the currency comparison (rule H: derive it on my own statistic).** The
old-vs-v6 currency difference is tested PAIRED on the same resampled clusters, and its
own CI95 is the floor. I do not borrow the published `[-0.0878, -0.0550]` band as a
significance floor for a paired difference; that band is a one-sample band on a single
frame and is used only for the reproduction clause C1.

## 7. Pre-registered clauses

Every clause states what result would FAIL it (rule G).

* **C0 v5 reconstruction.** max abs deviation of my knot-form v5 from
  `max(0, 1.382491*x - 2.318551)` over the realised raw-price support < $0.01M.
  FAILS if any point deviates by more than that; then all `_v5` cells are reported as
  approximate and the old-frame comparison is downgraded.
* **C1 reproduction (this clause is EXPECTED to be informative in either direction).**
  My `raw_v5` currency point estimate falls inside the published CI95
  `[-0.0878, -0.0550]`. FAILS if outside. A failure does NOT invalidate the lane; it
  means the published currency does not reproduce under today's win cost and every
  old-vs-new statement in this doc is mine-vs-mine. Either outcome is reported in the
  headline.
* **C2 partition integrity.** `|S_rank + S_level + S_floor - 1| < 1e-9` in both orders
  and all four cells. FAILS on any arithmetic slip. (Weak by construction; declared weak.)
* **C3 did the floor term go away.** Operationalised: **"GONE" = the `norm_v6` floor
  share's bootstrap CI95 upper bound is below 0.05.** FAILS (i.e. the term is NOT gone)
  if that upper bound is >= 0.05. **This 0.05 is a threshold I am adding and it decides
  the verdict, so it goes in the headline** (rule B). It is set at 5% of total MAE
  because the term being replaced was 26% and a term under a twentieth of the total is
  not something a program should be reasoning about.
* **C4 did the currency move materially.** The paired `raw_v5 - norm_v6` currency
  difference, player-clustered, CI95 excluding 0. FAILS (no material move) if the CI95
  contains 0. Separately and secondarily: whether the `norm_v6` point estimate sits
  outside the published `[-0.0878, -0.0550]`, which is the practical question for
  everyone quoting that band.
* **C5 the currency is a currency.** Measured on segments `[0,0.05]`, `[0,0.10]`,
  `[0,0.20]`, `[0,0.50]` and `[0,1.0]`. FAILS if the point estimates span more than 2x
  between the smallest and largest magnitude, in which case the number is a
  segment-specific slope and must not be quoted as a conversion rate. **I expect this to
  fail** on the published curve's own numbers (the `[0,1.0]` slope implied by stage H is
  about -$0.057M against the quoted -$0.0704M), and I am pre-registering that expectation
  so nobody can claim I discovered it after the fact.

## 8. Controls that would embarrass me (rule D)

* **CTRL-1 zero-information board.** Every player given the pool's median served FV.
  Rank information exactly zero. If its MAE is close to the incumbent's, the incumbent
  board's ranking is worth little and a large `S_rank` is not evidence of a good board.
* **CTRL-2 permuted board.** The served price multiset shuffled across players
  (multiset preserved, ranking destroyed), 40 draws. This is the upper bound the ladder
  is implicitly measured against; the published run reported $17.106M.
* **CTRL-3 path dependence.** Order A vs order B vs Shapley (section 4).
* **CTRL-4 objective swap.** MSE partition vs MAE partition (section 5).
* **CTRL-5 segment sweep.** Clause C5.
* **CTRL-6 permuted truth.** Re-run the whole ladder against a permuted `t` vector.
  `S_rank` must collapse toward 0 and `MAE_L1` must rise to roughly `MAE_L2`. If the
  ladder still shows a big ranking share against permuted truth, the ladder is measuring
  the price DISTRIBUTION, not ranking, and the entire decomposition is void.

## 9. Multiplicity

The clause family is C0-C5 (6 clauses) plus 6 controls, evaluated on 4 frame cells for
the ladder and 2 cells for the currency. Any "k of n significant" statement quotes n as
the full grid actually run, and the grid is fixed here before the run. No cell is dropped
after the fact.

---

## RESULT (appended after the run)

Artifact: `data/surplus_decomposition_v6.json` (runtime 17.1s, seed 20260808,
B=2000 both). Deterministic: the artifact is byte-identical across a cold-cache re-run
and a warm-cache re-run (the cohort cache lives in the scratchpad, not in the repo).
Every number below is a field of that artifact.

### Headline

**The 26% "pricing floor" term did not go anywhere, because it was never a floor term.
On the v6 EV frame it is 0.385 of MAE, CI95 [0.349, 0.421], LARGER than the old frame's
0.352 under identical code. And the gate currency is wrong by about 1.7x: measured with
the published instrument on the v6 frame it is -$0.117M per +0.01 rho, CI95
[-0.139, -0.096], not -$0.0704M.**

Self-added threshold that decided a verdict, declared per rule B: **C3 operationalised
"GONE" as a floor-share CI95 upper bound below 0.05.** The measured upper bound is 0.421.
Any threshold below 0.35 gives the same verdict, so the choice is not load-bearing, but
it is mine and it is stated.

### Pool and reproduction of the frame

n = **2,229** resolved listings over 1,365 distinct players, not the registered 2,236.
The DB has drifted since the registration: `scored` 2,958 vs 2,964, `scored_busts` 1,375
vs 1,382, `censored_active` 292 vs 286, `listed` 3,368 unchanged. Seven rows moved from
scored-bust to censored-active. Pool membership is byte-identical between the raw and
normalized cells (`pool_membership_identical: true`), so the FV-scale contrast is a pure
value change as designed.

Served FV: raw mean 44.637 sd 4.491 (the published run reported 44.62 / 4.49, so the raw
cell IS the published board); normalized mean 42.362 sd 4.376, min 34.875.

Truth: mean $7.253M, sd $24.591M, **61.7% of rows are exactly $0** (1,375 never-debuted).

### C0 v5 reconstruction: PASS

Max abs deviation of my knot form from `max(0, 1.382491x - 2.318551)` is
**1.14e-13 $M** over the [0, 400] support. The `_v5` cells are exact, not approximate.

### The ladder, all four cells (MAE, order A)

| cell | L2 | L1 | L0 | rank | level | floor |
|---|---|---|---|---|---|---|
| `raw_v5` (OLD) | 11.930 | 7.584 | 4.197 | 0.364 | 0.284 | **0.352** |
| `normalized_v5` | 9.837 | 6.166 | 4.197 | 0.373 | 0.200 | 0.427 |
| `raw_v6` | 15.371 | 10.859 | 4.703 | 0.294 | 0.400 | 0.306 |
| `normalized_v6` (**V6, production**) | 12.202 | 7.537 | 4.703 | 0.382 | 0.232 | **0.385** |

Bootstrap CI95 on the production cell: rank [0.332, 0.427], level [0.182, 0.289],
floor [0.349, 0.421].

**Residual, stated explicitly as the brief requires.** The three shares telescope to
exactly 1 by construction and the artifact asserts `|sum - 1| < 1e-9` in every cell,
every loss and both orders (C2 PASS). That assertion is worth nothing on its own and is
declared weak. **The real residual is path dependence, and it is enormous.** On the
production cell, order A splits rank/level 0.382 / 0.232; order B splits them
0.712 / **-0.098**. The interaction is **0.330 in MAE and 1.110 in MSE**. The level share
is NEGATIVE in order B because `L1B` (perfect level, incumbent ordering, MAE 13.395) is
WORSE than the incumbent board itself (12.202): handing every player their true
WAR-implied price and then scrambling it into the board's order costs money, because the
truth-implied price distribution is far more dispersed than the board's and dispersion
without ordering is punished. **Rank and level are not separable on this data**, so any
"X% ranking / Y% level" statement, the published one included, is an artefact of which
term you remove first. Only the floor share is order-invariant.

### Where the "26% floor" actually went: nowhere, and it was misnamed

The L0 rung is the model given perfect WAR foresight, so its residual is the pricing
layer alone. Decomposing that residual by outcome bucket:

| bucket | n | `raw_v5` share of L0 abs err | `normalized_v6` share |
|---|---|---|---|
| never debuted | 1,375 | **0.000** | 0.088 |
| debuted, WAR q1 | 215 | 0.222 | 0.212 |
| debuted, WAR q2 | 213 | 0.058 | 0.055 |
| debuted, WAR q3 | 214 | 0.148 | 0.091 |
| debuted, WAR q4 | 212 | **0.571** | **0.554** |

1. Under v5 the busts contributed **exactly zero** to the perfect-foresight residual.
   That is not a measurement, it is **two conventions coinciding**: the harness assigns
   never-debuted players a realized surplus of exactly $0.000, and the v5 map floors
   every raw price under $1.677M at exactly $0.000. 61.7% of the pool was scored right
   by construction on both sides of the comparison.
2. The residual was therefore always dominated by the 854 players who DID debut, and
   **55 to 57% of it sits in the top realized-WAR quartile**, which perfect foresight
   still over-prices by a mean of **+$18.87M (v5) / +$25.33M (v6)** per player. That is
   the convex win-cost curve, the discount and the imputed-salary schedule, not a floor.
3. v6 made the term **bigger**, not smaller: L0 MAE 4.197 -> 4.703, +12.1%. Of that
   +$0.507M, **$0.413M is arithmetically the new bottom knot** (1,375 busts x $0.67M /
   2,229 rows) and the remaining $0.093M is the isotonic map repricing debuted rows.
   Removing the $0 floor was an EV decision and it is defensible under the owner ruling;
   its cost is that perfect foresight now misprices every bust by exactly $0.67M.

So the answer to "a term that large does not vanish without moving somewhere" is that it
never was a $0-floor term to begin with. It is the pricing layer's irreducible error on
players who reached the majors, and the v6 change added a small new term to it rather
than deleting a large old one.

### The MAE partition and the EV partition disagree (CTRL-4)

Same cell, same rows, MSE (whose minimiser is the conditional mean, i.e. the owner's
stated objective):

| cell | MSE rank | MSE level | MSE floor |
|---|---|---|---|
| `raw_v5` | 0.683 | 0.051 | 0.267 |
| `normalized_v6` | 0.686 | **0.032**, CI95 [-0.061, 0.132] | 0.283 |

Under the EV-consistent loss the level term is **indistinguishable from zero** while the
MAE partition puts 23% there. The two objectives disagree by roughly 7x on the level
term. The floor term is the one quantity that is stable across losses (0.25 to 0.43 in
every cell and both losses), which is a further reason to stop calling it a floor: it is
the pricing layer's residual, and it is the largest reliably-estimated piece of the chain.

### Calibration (the arbiter, per the owner ruling)

| cell | L2 bias $M | OLS slope | 8-bin slope |
|---|---|---|---|
| `raw_v5` | +1.649 | 0.821 | 0.770 |
| `normalized_v5` | **-2.025** | **0.992** | **0.959** |
| `raw_v6` | +6.935 | 0.708 | 0.626 |
| `normalized_v6` | +2.137 | 0.837 | 0.755 |

On the frame production actually serves, v6 is over-priced by **+$2.137M per prospect**
with a binned calibration slope of 0.755. Under the arbiter this lane is required to use,
the **v5 map on the normalized frame calibrates better than the shipped v6 map does**
(bias -2.025 vs +2.137, slope 0.959 vs 0.755). That contradicts the v6 fit provenance,
which reports held-out bias -0.028 and slope 1.059. The difference is that the v6 fit was
performed on the 2026-07-31 win cost and the **2026-08-04 dpw re-anchor lifted the
trailing-3 mean 11.6% after it**, which re-inflates every predicted price without moving
the historical-$/WAR realized side. **The v6 calibration is fit to a win cost that is no
longer in force.** This lane cannot fix that (it is read-only on the config) and does not
claim a re-fit would clear a gate; it reports the measurement and files it.

### CTRL-1, the control that should embarrass the whole chain

A **zero-information board** that gives every player the pool median FV (40.645):

| | constant board | incumbent board |
|---|---|---|
| v6 frame, MAE | **11.560** | 12.202 |
| v6 frame, MSE | 617.16 | **483.24** |
| v5 frame, MAE | 9.860 | 9.837 |
| v5 frame, MSE | 646.70 | **476.07** |

**On MAE, a constant beats the production board.** On MSE the board wins by 22 to 27%.
This is the single most important number in the lane: the entire published currency, and
the entire 58/16/26 framing, are denominated in a loss under which the board carries no
measurable value at all. It also independently vindicates the 2026-07-31 owner ruling.
CTRL-2 (permuted board, 40 draws) gives 15.605 +/- 0.131 (`raw_v5`) and 15.917 +/- 0.136
(`normalized_v6`), so the board does beat a shuffle by ~$3.7M; the ordering is worth
something, but the DISPERSION of the served price multiset costs more under MAE than the
ordering earns.

### CTRL-6, and a pre-registered expectation of mine that was wrong

I pre-registered that permuting the truth vector should collapse `S_rank` toward 0 and
push `MAE_L1` up toward `MAE_L2`. **That expectation was misconceived and I am recording
it rather than quietly dropping it.** `MAE_L1` is `mean|sort(p) - sort(t)|`, a function of
the two MARGINAL distributions only, so it is invariant to any permutation of truth: it
reads 7.584 on real truth and 7.584 on permuted truth in the `raw_v5` cell. What actually
happens is that `MAE_L2` rises (11.930 -> 15.439) and therefore `S_rank` **RISES**, 0.364
-> 0.509.

That is the substantive finding hiding in a failed control: **`S_rank` is not a measure of
the board's ranking skill. It is larger for a board with zero rank information than for
the real board.** It measures how much of a board's MAE would be removed by reordering its
own price multiset, which grows as the board gets worse. The published "58% ranking" was
read across this program as a statement about where the recoverable value is; it is not
one. (The L0 arm of CTRL-6 is degenerate by construction, since L0 prices off each real
player's WAR while truth is permuted; its 1.127 floor share is not interpretable and is
not interpreted.)

### The currency

**C1 reproduction: FAIL as pre-registered.** My `raw_v5` currency is **-$0.155M** per
+0.01 rho, CI95 [-0.184, -0.123], far outside the published [-0.0878, -0.0550].

**Post-hoc diagnosis, run only after C1 failed and NOT a re-specification of C1.** The
published instrument ranks the incumbent board by **served FV**; my pre-registered one
ranks it by **served price**. Those differ enormously in tie structure: the raw served FV
takes **13 distinct values across 2,229 rows with a largest tie block of 678**, while the
served price takes 380 (v5) to 733 (v6) distinct values because age and eta enter it.
Re-running my curve ranked on served FV gives **-$0.0764M**, CI95 [-0.0913, -0.0608],
which **contains the published -$0.0704M**. The instrument is reproduced; the published
figure is confirmed to be the FV-tied variant.

Why that matters, entirely inside the published `[0, 0.10]` segment. On the FV-ranked
curve rho runs 0.1940 -> 0.3167 -> 0.3315 and MAE runs 12.0236 -> 11.3168 -> 10.9730 at
w = 0, 0.02, 0.10. So **89.2% of the segment's rho gain, but only 67.3% of its MAE gain,
happens in the first fifth of the segment**, where the only thing changing is the order
WITHIN the FV grid's tie blocks. Priced separately:

* w 0 -> 0.02 (tie-breaking): **-$0.0576M** per +0.01 rho
* w 0.02 -> 0.10 (moving players across grades): **-$0.2323M** per +0.01 rho

**A factor of four, inside the single segment the published number averages over.** The
same segment on the price-ranked board gains only 0.0612 rho against the FV-ranked
board's 0.1375, for essentially the same MAE gain (-0.950 vs -1.051): the extra rho is
tie resolution and it is nearly free.

The gate standard then quotes the resulting average to price a change in **pooled eFV
Spearman**, and eFV is a continuous score that does not tie in 678-row blocks. **The
published currency is the tied-grid conversion being applied to a tie-free statistic.**

**The number, both instruments, both frames** (`currency_bootstrap*` in the artifact):

| instrument | `raw_v5` (old) | `normalized_v6` (v6) | paired diff CI95 |
|---|---|---|---|
| ranked on served FV (published) | -0.0751 [-0.0913, -0.0608] | **-0.1167 [-0.1388, -0.0956]** | [+0.0279, +0.0558] |
| ranked on served price | -0.1522 [-0.1839, -0.1232] | -0.1295 [-0.1525, -0.1074] | [-0.0380, -0.0091] |

**C4: PASS (it moved, materially).** Both paired CI95s exclude zero, and they point in
OPPOSITE directions, which is itself a warning: under the published instrument the v6
frame makes a rank point worth 55% MORE, under the price instrument 15% LESS. What both
agree on is that the v6 value is **outside the published band**.

**Like-for-like replacement: on the v6 frame, with the published instrument,
+0.01 pooled rho = -$0.117M surplus MAE per prospect, CI95 [-0.139, -0.096].** Every
argument in this program that priced a rank gain at $0.0704M per 0.01 **understates the
dollars by about 1.66x**.

**C5: FAIL. The currency is not a currency.** On the production cell, price-ranked, the
segment estimates are -0.154 (w<=0.05), -0.134 (0.10), -0.110 (0.20), -0.069 (0.50),
-0.075 (1.0): a spread of **2.23x**, above the pre-registered 2.0x. FV-ranked on the old
frame the spread is 1.51x, on the v6 frame 1.69x. I pre-registered the expectation that
this would fail, from the published curve's own numbers, before running it. Combined with
the 2.0x instrument dependence, the honest statement of the conversion rate is a RANGE of
roughly **-$0.06M to -$0.17M per +0.01 rho**, and any decision that flips inside that
range is not decidable by this instrument.

### Clause and control ledger (multiplicity: 6 clauses, 6 controls, 4 cells)

| id | verdict |
|---|---|
| C0 v5 reconstruction | PASS (1.1e-13) |
| C1 reproduction of the published currency | **FAIL** as specified; explained post-hoc by the ranking variable |
| C2 partition integrity | PASS, declared weak (telescopes by construction) |
| C3 floor term gone | **FAIL** - it is 0.385, CI95 [0.349, 0.421], vs the 0.05 bar |
| C4 currency moved materially | PASS, both instruments, opposite signs |
| C5 currency is a currency | **FAIL** - 2.23x segment spread |
| CTRL-1 zero-information board | FIRED - constant beats the board on MAE |
| CTRL-2 permuted board | clean, board beats shuffle by ~$3.7M |
| CTRL-3 path dependence | FIRED - interaction 0.330 MAE / 1.110 MSE |
| CTRL-4 objective swap | FIRED - level share 0.232 (MAE) vs 0.032 (MSE) |
| CTRL-5 segment sweep | FIRED (= C5) |
| CTRL-6 permuted truth | my pre-registered criterion was wrong; the corrected reading reverses the meaning of `S_rank` |

Three of six clauses failed as written, and four of six controls fired. Nothing here is
narrowed to a passing family: the grid is the grid fixed in section 9.

### One deviation from the pre-registration, in the safe direction

Section 2 says the v5 calibration block would be "patched IN MEMORY on the cached dict
and restored". It is not patched at all. `_apply_cal` applies a calibration block as a
pure function to a vector of raw prices, so `value_framework`'s cached config is never
touched. That matters because agents run in parallel in this program and an in-memory
patch on a shared cache is a cross-lane hazard. `_apply_cal` reproduces
`vf.apply_calibration`'s isotonic branch exactly, including both end clamps; C0 checks it
against the closed-form v5 to 1.1e-13.

### Known limits, so nobody over-reads this

* The 2026-08-04 dpw re-anchor is not revertible from this lane, so the old-frame cell is
  a reconstruction under today's win cost and is NOT a replay of the 2026-07-24 run. All
  old-vs-v6 claims above are mine-vs-mine under identical code. The one cross-check that
  IS like-for-like is the currency instrument, which reproduces the published figure.
* `control_years` is 7 (`clemens_2026`) while the realized window is capped at 6 seasons
  in `surplus_backtest_real`. Inherited from the shipped harness, held identical across
  all four cells. It cannot move the contrasts; it does inflate `L0`'s over-pricing of the
  top quartile and so is a candidate cause of that +$18.87M to +$25.33M bias. Worth a
  lane; not this one.
* The engine's FV->WAR map is not exactly monotone on a 0.05 FV grid (30 decreasing steps
  per side between FV 20.2 and 34.75, worst step -0.0072 total WAR). Inversion needs
  monotonicity, so the lab takes a running maximum and records the violation
  (`fv_to_war_monotonicity_repair`). The distortion is far below one FV point.
* The published stage-C rung labelled "perfect ranking, same served FV multiset" has a
  different `pred_mean` (12.587) from its own L2 (8.883) in
  `tools/_frontier_out/_surplus_stageC.json`. A permutation cannot change a mean, so the
  published stage-C rung and the published headline label are not the same object. My L1
  is the label. Recorded as an observation about the prior record, not re-litigated here.
* The served eFV matrices are stale (they reproduce `consensus_fv_raw` on 74.8% of rows).
  This lane does not touch eFV at all: it prices the 2017-2019 vintage CONSENSUS listing
  FV against realized outcomes. The staleness bounds the lane only through the gate
  standard's wording ("pooled eFV Spearman"), which is why the currency is reported as a
  board-order-vs-outcome conversion and the instrument dependence is stated in full.
