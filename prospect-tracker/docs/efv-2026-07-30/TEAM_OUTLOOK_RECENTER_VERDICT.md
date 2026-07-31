# Verdict: the team-outlook recenter remainder, both candidates measured

Owner decision was "measure both, ship the winner, and do NOT widen the bound", scored on
the `proj_backtest.py` holdout. Both were measured. **Neither ships.** The bound is not
widened and `test_recenter_remainder_near_zero` stays red.

## What was already known going in

The guard went red on 2026-07-30 at remainder 4.48 wins/team (bound: 3). The cause was
already isolated to the FA E3 playing-time refit shipped in 89112f5, not to this file:
vet year-1 champion WAR fell 927.2 -> 866.6 and depth year-1 WAR 90.8 -> 43.4, together
taking the model league total from 1018.0 to 910.0 against a 1000-WAR benchmark. The
docstring named the two honest repairs. This document measures both.

## Candidate B: re-fit the cohort intercepts on the new paths

The committed intercepts were fit **2026-06-12**, seven weeks before the E3 ship, so they
are stale by exactly the change that caused the problem. Re-fitting is the obvious move
and it does what you would expect to the coefficients - every hitter band lifts, absorbing
the level drop:

| band | committed (06-12) | refit (07-31) |
|---|---|---|
| hit:0-25 | +0.172 | **+0.324** |
| hit:26-29 | +0.018 | **+0.146** |
| hit:30-33 | -0.138 | **+0.022** |
| hit:34-99 | -0.201 | **-0.007** |
| pit:0-25 | +0.216 | -0.082 |
| pit:34-99 | -0.199 | +0.031 |

Player-level accuracy improves outright: pooled MAE **0.593 -> 0.550**, r **0.581 ->
0.628**, n=8,866.

**But it loses its own pre-registered ship rule.** That rule is
`cohort_recentered < recentered` on the 2025 holdout:

| holdout team-wins MAE | committed fit | refit on new paths |
|---|---|---|
| raw | 7.73 | 8.56 |
| recentered | 7.76 | **7.19** |
| cohort_recentered | **7.71** | 7.29 |
| baseline_prior_wins | 7.24 | 7.24 |
| **challenger wins?** | **yes** | **NO** |

On the post-E3 paths the cohort intercepts are not merely useless, they are *harmful*:
7.29 against 7.19 for doing nothing. **NO SHIP.** The artifact was restored to the
committed 2026-06-12 fit, verified byte-identical.

### A real bug found while measuring this

`proj_export._cohort_intercepts()` read the intercepts **unconditionally**, ignoring the
artifact's own `ship_decision.challenger_wins`. So simply *running* `proj_backtest.py`
would have served the losing intercepts, with no gate and no announcement. Fixed: the
reader now returns `{}` unless the challenger won. `challenger_wins` is True on the
committed fit, so this is a **no-op today and moves no served number** - it exists so the
next refit cannot ship itself.

## Candidate A: re-anchor the playing-time refit

Not shipped, and the measurement explains why it should not be attempted as stated.

The E3 refit is uniformly below the shipped hand-set Marcel across the entire input range
- not at a floor, not at a ceiling, everywhere:

| e1 / e2 / e3 | fitted PT | shipped PT |
|---|---|---|
| 0 / 0 / 0 | 90.5 | 200.0 |
| 200 / 150 / 100 | 230.7 | 315.0 |
| 450 / 400 / 400 | 405.3 | 465.0 |
| 700 / 700 / 700 | 579.1 | 620.0 |

So there is one mechanism here, not two. WAR is proportional to exposure, so a uniformly
lower PT curve shrinks every player's WAR toward zero; marginal depth players shrink *to*
zero and are then dropped outright by `if not any(champ): continue` in `_depth_pool`. The
"118 players now project an all-zero path" symptom and the "vet WAR fell 60.6" symptom are
the same fact seen twice, and neither is a floor bug.

**The problem with re-anchoring is that it would re-introduce an error the gate panel says
is wrong.** On its own gate panel the refit's exposure level is *better*, not worse:
projected PA mean 364.0 -> 299.1 against 312.7 actual, i.e. the level error fell from
**+51.3 to -13.6**. Anchoring the curve upward so the roster universe sums to ~1000 would
push projected PA back above actual on the only population where exposure has been scored.
That is a level convention traded against a measured quantity, and it is an owner call,
not a repair.

## The finding that reframes the guard

**The E3 ship improved holdout team accuracy, and by enough to cross the baseline for the
first time.** Plain-recentered holdout MAE went 7.76 -> 7.19 against a prior-wins baseline
of 7.24. Before the ship the engine LOST to "just use last year's wins"; after it, it
wins.

Recentering forces the league to 2,430 regardless, so a uniform level error cannot reach
recentered MAE - the 7.19 is bought by better per-player accuracy, not by the level. But
it does mean the thing the guard is flagging has no measured accuracy cost at year 1. What
it costs is *interpretability*: 4.48 of every team's wins come from a constant rather than
from its roster, and that grows to 27.9 by 2031 as the roster empties.

## One more disagreement worth recording

The test asserts `900 <= roster_war_sum <= 1100`. `_depth_pool`'s own docstring says the
`>=1-input-season` population "sums to ~870-930" on real rosters. The current 886.3 is
inside the module's documented expectation and below the test's floor. Those two were
never reconciled; whichever is right, they should not both stand.

## Status

Guard stays RED at 4.48 with the bound at 3, which is the instruction and the right
outcome: it is the only instrument that noticed, both candidate repairs are measured
losses, and the remaining option is a level-convention decision that belongs to the owner.
