# Gate: does the SHAPE of a glove predict how it transfers?

Pre-registered 2026-08-07, lane K6 of docs/master-plan-2026-08-07-omnibus3.md.
Written and committed to disk BEFORE the harness was written, before any
challenger coefficient was fitted, and before any held-out number was computed.
Standard: docs/EFV_GATE_STANDARD.md.

## The owner ask

"Can we make the defensive adjustments more accurate, maybe by using better
defensive statistics (or developing our own)?" Lane K5 answered the LADDER half
by re-gating it onto a rolling window. This is the FIELDER half.

## The one genuinely new signal on disk

`data/savant_oaa.json` (2016-2026, 1,537 players, 13,001 player-position-seasons)
already carries, per row, more than the two scalars the model reads:

| field  | meaning                       |
|--------|-------------------------------|
| `oaa`  | outs above average            |
| `frp`  | fielding runs prevented       |
| `in`   | outs on balls in front        |
| `bk`   | outs on balls behind          |
| `l3`   | outs lateral toward the 3B line |
| `l1`   | outs lateral toward the 1B line |
| `rhh`  | outs vs RHH                   |
| `lhh`  | outs vs LHH                   |
| `sr_act` / `sr_exp` | actual and adjusted expected success rate |

`positional_fit.Feeds.rates` reads `oaa` and `frp` and nothing else
(positional_fit.py:153). The directional and platoon splits have never been
opened by any model in this tree.

Measured before pre-registration, on the raw feed:

- `in + bk + l3 + l1` equals `oaa` exactly in 9,357 of 13,001 rows, and the
  worst disagreement anywhere is 2.0 outs with a mean of -0.32. The split is
  additive and the residual is Savant's own per-component integer rounding.
- `rhh + lhh` equals `oaa` exactly in 10,664 of 13,001 rows, same reason.
- No component is ever null in any row.
- All 169 rows of the conversion harness have complete directional components on
  every one of their 195 source reads. Coverage is 100 percent, so no arm has to
  abstain and no row is dropped for the challenger's benefit.

Catchers have zero Savant OAA rows in every season, so `OAA_POSITIONS` already
excludes them and both arms abstain on catchers identically. Nothing here
imputes a catcher.

## The hypothesis

A scalar shrunk-z summary throws away the SHAPE of a fielder's skill, and shape
is what should govern transfer to a DIFFERENT position. A lateral-range
specialist and an in/back specialist with identical total OAA should not project
identically at shortstop versus first base. If that is true, a per-destination
shape coefficient will be non-zero and will differ across the ladder.

If it is false, the shape term is noise and the challenger degenerates to the
champion. The challenger below is built so that the null is EXACT degeneracy,
not a drift: with every shape coefficient at zero the challenger's prediction is
bit-identical to the champion's.

## What ships if the gate passes

A shape term inside `positional_fit`'s prediction of the destination rate.
`positional_fit.fit_ladder` is untouched, so the one-owner rule holds and no
second ladder is fitted. `data/def_home.json` is checked for byte-identity the
way the K5 recency gate checked it, and the identification tests in
`test_positional_fit.py` must stay green.

## What ships if the gate fails

The null, as an artifact, plus the measured component reliabilities and the
per-destination coefficients so the next attempt does not re-measure them.
`positional_fit.py` is NOT edited. No served grade, rank or dollar moves.

## Champion (incumbent, shipped)

`conversion_accuracy`'s `model` arm, unchanged (positional_fit.py:961):

    pred(b) = D_t[b] + s_b * Zhat

`Zhat = _shrunk_z(src, D_t, sig)`. `D_t` is refit on seasons <= t inside the
harness. `sig` is the all-seasons `fit_signal` result. Reproduced live today at
MAE **5.682** on n=169 against carry-over 6.733, d-shift 6.654, league-average
6.284, permuted 6.244. Those five numbers match `data/positional_fit.json`
exactly, so the harness is reproducing, not drifting.

## Challenger S (the only arm; strictly nested)

    pred(b) = D_t[b] + s_b * Zhat + g_b * Uhat

`Zhat`, `D_t`, `s_b` are the champion's, unmodified. Two new objects:

### Uhat, the shrunk shape score

Per read (player i, season y, position p, innings n):

    u_raw   = ((l3 + l1) - (in + bk)) * 1000 / n

Lateral outs minus depth outs per 1000 defensive innings. Positive means his
outs come disproportionately from range across the field; negative means from
charging in and going back. This is the contrast that is ORTHOGONAL in
construction to the level the champion already uses, because
`(l3 + l1) + (in + bk)` is `oaa` itself.

Standardised within position on the TRAINING corpus (seasons <= t, innings >=
`MIN_PAIR_INN`):  `u_std = (u_raw - mu_p) / sd_p`.

Then residualised against the champion's own per-read level, so the shape score
cannot smuggle in level information the champion already has:

    zread   = (frp_rate - D_t[p]) / s_p          (the term inside _shrunk_z)
    u_res   = u_std - (a_p + rho_p * zread)

`a_p, rho_p` are the OLS intercept and slope of `u_std` on `zread` at p over the
training rows. The intercept is fitted so `u_res` has mean zero at p, and it is
then DISCARDED from the prediction: the challenger may not win on a level
recalibration.

Shrunk across the player's source reads by the same posterior as `_shrunk_z`,
prior N(0,1), precision `n / k_u_p`:

    Uhat = sum(prec * u_res) / (1 + sum(prec))

`k_u_p` comes from year-over-year persistence of `u_res` at the same position,
by exactly the `fit_signal` construction (`hm_inn * (1 - r) / r`, r clipped to
[0.05, 0.95], min 300 innings on both sides, minimum 30 pairs). If a position
has fewer than 30 usable pairs in the training window its `k_u_p` falls back to
1200 innings, the same fallback `fit_signal` already uses.

### g_b, the per-destination shape coefficient

Estimated on SAME-POSITION year-over-year pairs in the training window only
(seasons <= t), 300 innings on both sides. For each pair, the target is the
champion's own forward residual and the regressor is the shape score:

    target    = frp_rate(y+1) - (D_t[p] + s_p * Zhat(y))
    regressor = Uhat(y)
    g_p       = OLS slope, with an intercept that is fitted and DISCARDED

So `g_p` answers exactly one question: after the champion has had its say, does
knowing the lateral-versus-depth tilt of last year's glove move next year's rate
at p? Fitting it on same-position pairs and applying it at the DESTINATION is
the same transfer assumption the champion already makes about `Zhat`, and it is
stated here rather than hidden.

Fallback: fewer than 60 training pairs at p gives `g_p = 0`, which degenerates
that destination to the champion exactly.

Everything new is FORWARD-CHAINED on seasons <= t, matching `D_t`. `sig` is
shared identically by both arms. The challenger is therefore held to a stricter
information rule than the champion, which is the conservative direction.

## Zero-information control

Shape-permuted. Inside each scored season, `Uhat` is shuffled between the movers
while `Zhat`, `D_t`, `s_b` and `g_b` all stay exactly as fitted. Same machinery,
same coefficients, same rows, zero shape content. 300 permutations.

This is the correct control for this gate: permuting the TARGET would test
whether a fitted model can beat a fixed one on random labels, which it can by
construction, and that trap is already recorded in the K5 gate.

## Pre-registered decision rule

Primary statistic: **dMAE = MAE(champion) - MAE(Challenger S)** on the identical
169 conversion rows. Positive means the challenger is better.

Bootstrap: paired, 2,000 draws, CLUSTERED BY PLAYER. The 169 rows come from 150
distinct players and one player contributes 4, so treating rows as independent
would understate the interval.

SHIP requires ALL FOUR:

1. **dMAE cluster-bootstrap CI95 excludes zero and lies entirely above it.**
2. **Sign consistency: Challenger S has the lower MAE in at least 6 of the 8
   scored seasons** (2017, 2018, 2020, 2021, 2022, 2023, 2024, 2025; n per
   season 11 to 32). Six of eight is fixed here, before the run, and is the
   anti-marginal clause. The shipped champion's own comparable figure against
   carry-over is 7 of 8.
3. **Control: the challenger's dMAE exceeds the 95th percentile of the
   shape-permuted control's dMAE distribution.**
4. **No collateral damage.** The demotion AUC in `backtest` under the challenger
   is no more than 0.01 below the champion's measured 0.4809; the identification
   tests in `test_positional_fit.py` stay green; `data/def_home.json` is
   byte-identical.

Any one failing is a NO-SHIP. A CI that touches zero is a fail, not a trend.
Marginal is FAIL. ONE attempt: this is not re-run with a different contrast, a
different innings floor, a different shrinkage, or a widened population.

## Committed loss on failure

`data/positional_shape_transfer_lab.json` is published with the full null,
including every fitted `g_p`, every component reliability, and the per-season
splits. `positional_fit.py` is not edited. The doc below the line records what
was measured so the next attempt starts from it. The artifact is deliberately
named OUTSIDE the `*_eval*.json` registry glob (`test_model_registry.py:72`)
because this lane does not own `data/model_registry.json` and an unregistered
eval file would break that test.

## What is NOT tested this session, and why

One arm, one test. These are logged as follow-ups, not run:

- The platoon split (`rhh` / `lhh`). It is a real second contrast and it earns
  its own gate, not a second bite at this one.
- The full 4-way directional decomposition (in / back / lateral-to-line /
  lateral-to-middle, canonicalised per position since `l3` means "toward the
  line" at 3B/SS/LF and "toward the middle" at 1B/2B/RF). Twenty-eight free
  parameters against 169 rows is not a test this population can settle.
- `sr_act` versus `sr_exp` as an opportunity-difficulty control.

Reporting the best of several arms as one test is the failure mode this section
exists to prevent.

## What this gate cannot say

It scores the destination FIELDING RATE of 169 real movers. A win would mean
shape improves the transfer prediction. It says nothing about whether clubs
should move anyone, and it does not touch the ladder, the bat, or the
positional adjustment.

## The standing finding this gate must keep in view

The demotion AUC is already a published null: the shipped model scores 0.4809
and the ZERO-INFORMATION control scores 0.4800, while the naive raw OAA rate
scores 0.6184. Raw OAA out-discriminates the model on the demotion label by a
wide margin. That is not this gate's target and is not fixed by it. It is
carried forward as an open finding.

---

# RESULT, appended after the run

Everything above this line was on disk before `tools/positional_shape_transfer_lab.py`
was written or run. One attempt, one arm, one run. Full numbers:
`data/positional_shape_transfer_lab.json`.

## VERDICT: NO-SHIP. Three of the four clauses failed.

`positional_fit.py` is not edited. No served grade, rank or dollar moves.

### Reproduction tripwire, checked first

The harness refuses to interpret anything unless it reproduces the shipped
champion on the shipped rows. It did: n = 169 conversions from 150 distinct
players, champion MAE 5.6823 (artifact 5.682), carry-over 6.7326 (artifact
6.733). The gate scored the real model.

### The four clauses

| clause | required | measured | verdict |
|--------|----------|----------|---------|
| 1. dMAE CI95 above zero | excludes zero, positive | +0.0334, CI95 [-0.0654, 0.1357] | **FAIL** |
| 2. sign consistency | 6 of 8 seasons | 3 of 8 | **FAIL** |
| 3. beats the shape-permuted control | dMAE > control p95 | 0.0334 against p95 0.0569 | **FAIL** |
| 4. no demotion-AUC damage | within 0.01 of 0.4809 | 0.4825 | PASS |

MAE on the 169 rows: champion 5.6823, Challenger S 5.6488, carry-over 6.7326.

Clause 3 is the one that settles it. Shuffling the shape score BETWEEN movers,
while keeping every fitted coefficient in place, beats the champion by more than
the real shape does about one run in five. The measured advantage sits inside
the noise band of a score with no shape content in it at all. The control's mean
is -0.0133, so the machinery is not broken; it just cannot tell the real
contrast from a shuffled one.

Clause 2 is worse than 3 of 8 looks. 2017 and 2018 are exact ties at dMAE 0.0000
because the training window held fewer than 60 same-position pairs and `g_p` took
its pre-registered zero fallback, which degenerates the challenger to the
champion. Of the SIX seasons where the challenger was actually live it won three
and lost three: +0.234 (2022), +0.189 (2023), +0.048 (2025) against -0.118
(2020), -0.037 (2021), -0.005 (2024).

## Why it failed, which is the part worth keeping

The shape does not persist. Year-over-year correlation of the residualised
lateral-minus-depth score at the same position, at the 2025 training cutoff:

| pos | shape yoy r | champion LEVEL yoy r | k_u (innings) |
|-----|-------------|----------------------|---------------|
| 1B  | 0.111 | 0.251 | 6,870 |
| 2B  | 0.117 | 0.312 | 5,970 |
| 3B  | 0.113 | 0.409 | 6,363 |
| SS  | 0.123 | 0.509 | 6,592 |
| LF  | 0.058 | 0.433 | 11,645 |
| CF  | 0.173 | 0.540 | 3,556 |
| RF  | 0.050 (at the clip floor) | 0.497 | 13,690 |

A full season at one position is roughly 1,200 defensive innings. Against a
shrinkage constant of 6,000 to 13,700 innings, one season of shape evidence
survives at about 0.09 to 0.15 of its face value. The posterior does the correct
thing and crushes it: the shrunk shape score has SD **0.116** on the scored rows
against a prior SD of 1, p05/p95 [-0.210, +0.186]. The median absolute change to
a prediction is **0.045 runs per 1000 innings** on a champion MAE of 5.68.

The coefficients confirm it independently. `g_p` is unstable across training
cutoffs and flips sign on four of seven positions between the 2021 and 2025
fits: 3B +5.81 to -4.05, SS +0.71 to -4.02, LF -24.26 to -2.97, 1B +3.96 to
+6.15. That is the signature of a slope fitting noise, and it is visible without
looking at the outcome statistic at all.

Per destination, the challenger is better at LF (5.465 to 5.292), RF (4.914 to
4.836), CF and SS, and worse at 1B, 2B and 3B. The hypothesis predicted the
opposite pattern if anything: lateral range should be priced most where it is
scarce, at shortstop and centre field, and those two carry only 27 of the 169
rows between them. There is no destination-level pattern here to rescue.

## What this rules out, and what it does not

RULED OUT, for this feed and this population: a shrunk residual shape contrast
built from the Savant directional splits, applied as a per-destination transfer
term. It does not improve the conversion prediction, and the reason is measured
rather than assumed.

NOT ruled out, but now priced: the platoon split (`rhh` / `lhh`), the
canonicalised 4-way decomposition, and `sr_act` versus `sr_exp`. Any of those is
a different contrast on the SAME per-season component counts, so the binding
constraint is likely the same one. The cheap screen for the next attempt, before
any harness is written, is the year-over-year correlation of the candidate
contrast at the same position. If it lands in the 0.05 to 0.17 band measured
above, the posterior will shrink it to nothing and the arm cannot move a
prediction by enough to clear a 169-row bootstrap. Measure that first and
abandon on it, rather than building a second full gate.

The deeper reason is structural and applies to every arm: Savant publishes these
components as INTEGER out counts. A full-season corner outfielder's depth
component is a handful of outs, so a one-out rounding step is a large fraction of
the signal. The rounding is visible in the feed itself, which is why
`in + bk + l3 + l1` misses `oaa` by up to 2.0 outs in 3,644 of 13,001 rows. That
is a ceiling on any decomposition of this source, not a modelling choice.

## Atomicity, verified

- `positional_fit.py`, `prospect_def_value.py`: not edited, `git status` clean.
- `data/def_home.json`: byte-identical, `git diff` empty. Structurally it could
  not move, since nothing in the served path was touched.
- `data/positional_fit.json` and `data/positional_fit_ui.json`: byte-identical.
- `test_positional_fit.py`: 26 passed, 0 failed, 1 skipped, driven function by
  function with a monkeypatch shim rather than under pytest (this program's
  conftest git-checkouts files dirtied during a run). The skipped one,
  `test_fetch_raw_never_raises_and_falls_back`, was driven separately and passes.
- The lab artifact is named outside the `*_eval*.json` registry glob on purpose.

## The standing finding, still open

Unchanged and untouched by this gate. On the demotion label, the shipped model
scores AUC 0.4809, its zero-information control scores 0.4800, and raw OAA
scores 0.6184. The naive answer out-discriminates the model by 0.137 AUC. The
challenger moved it to 0.4825, which is nothing. `test_positional_fit.py` pins
this null in `test_demotion_discrimination_is_recorded_as_the_null_it_is`, and
it deserves its own lane rather than a byproduct of this one.
</content>
