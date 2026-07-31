# Pre-registration: arm strength and sprint speed in the position-conversion model

Lane A of `docs/master-plan-2026-07-30-nine-asks.md`, owner ask 1. Written BEFORE the new
indicators are wired. The ingests (`savant_arm_strength.py`, `savant_sprint.py`) are data
plumbing and ship on their own; this file governs what the MODEL is allowed to do with
them.

## 1. The structural gap, stated exactly

`positional_fit.estimate_players` scores a player at every feasible position as

```
field(p) = ( D[p] + signal_sd[p] * z ) * innings_per_650PA / 1000
value(p) = field(p) + ladder[p]
```

**`z` is ONE number per player.** It is the shrunk, recency-weighted, position-difficulty
adjusted read of his glove, and it transports uniformly: a player who is +1.2 z is +1.2 z
at every position the feasibility gate offers him.

That is why the owner's question cannot currently be answered. "Does he have the ARM for
third, or should he go to second?" asks the model to distinguish two components of
defensive value that it has deliberately collapsed into one scalar. Nothing in the
current inputs can separate them: OAA and FRP are outcome measures that already contain
whatever the arm contributed, so no rearrangement of the existing feeds recovers the
split. It needs a new measurement, which is what arm strength is.

Sprint speed plays the same role on the other axis: it is a direct read on range that is
independent of the outcome-based OAA, and it is the only measured athletic input
available for the outfield-projection half of the ask.

## 2. The owner's three rules, checked against the feasibility ladder

`fit_feasibility` restricts candidate moves to what the league actually does, precisely
to stop the model recommending that every corner outfielder play shortstop. A move
a -> b is offered only when b == a, b == DH, the player has real measured innings at b,
or b is at or below a on the positional-adjustment ladder AND at least 8 regulars made
that move in the window.

The canonical ladder (`prospect_def_value.POS_ADJ`, recovered empirically 2026-07-25,
R2 0.9821): C 10.91, SS 8.76, 2B 4.51, CF 3.53, 3B 3.36, LF -6.47, RF -6.41, 1B -8.53,
DH -14.04.

| owner's rule | direction on the ladder | verdict |
|---|---|---|
| **struggling SS -> 3B if the arm plays, else 2B / 1B** | SS 8.76 down to 3B 3.36, 2B 4.51, 1B -8.53. All DOWN-spectrum. | **Feasible today.** This is the core deliverable and the arm gate is exactly the missing discriminator: 3B is the arm-demanding option, 2B is not. |
| **who projects best to the OF** | infield down to LF/RF (-6.4) is down-spectrum; to CF 3.53 depends on origin. | **Feasible.** Range question, so sprint speed is the added indicator. |
| **struggling OF -> 2B** | LF/RF -6.4 UP to 2B +4.51. UP-spectrum by ~11 runs. | **Mostly blocked, and correctly so.** It is offered only where the player has real measured innings at 2B or where 8+ regulars made that exact move. Report honestly rather than forcing it: if the league does not make a move, the conversion matrix has no population to estimate it from, and the guard exists because unguarded it recommended shortstop for everyone. |

Stating this now so the lane is not later judged against a rule the data cannot support.

## 3. Design: arm gates the CANDIDATE SET, it does not add a runs term

Two ways to use arm strength, and the second is a trap:

**CHOSEN: gate the candidate set.** A player whose arm sits below what the position's
incumbents actually throw does not get that position offered. This matches how
`fit_feasibility` already works (restrict to what is real, measured not asserted), it
answers the owner's question directly, and it cannot silently re-rank anyone on an
unfitted coefficient.

**REJECTED: add an arm term to `field(p)`.** That requires a fitted runs-per-mph-per
position coefficient. We do not have one, the outcome already contains the arm (so
fitting it against OAA double-counts), and inventing a coefficient to satisfy an
intuition is exactly what the loss ledgers in this program exist to prevent.

**Thresholds are DERIVED, not asserted.** For each position, compute the distribution of
arm velocity among players with real measured innings there, and take a low percentile
(pre-registered at the 10th) as the floor. If 90% of actual third basemen throw harder
than X, a player under X is not being offered third base on this model's say-so. Publish
the fitted floors in the artifact next to the ladder and the reliability constants, the
way `fit.signal` already publishes `k_inn`.

**Sample size is already solved and must be reused, not reinvented.** `fit.signal`
carries per-position `signal_sd`, `k_inn` and `yoy_r`, measured: 1B (2.33, 2539 inn,
r .25), 2B (3.54, 1739, .31), 3B (4.20, 1164, .41), LF (3.84, 935, .43), SS (5.49, 874,
.51), RF (4.54, 724, .50), CF (5.10, 632, .54). Identical raw OAA means very different
things at 1B and CF, and the shrinkage already encodes that. The arm read gets the same
treatment: shrink toward the position mean by throw count, and report the weight.

## 4. Framing constraint, non-negotiable

`positional_fit` validation is split and the split is load-bearing:

- conversion accuracy (the rate at the NEW position, n=169 clean conversions) BEATS every
  baseline: MAE 5.682 against carry-over 6.733, league-average 6.284, permuted 6.244.
- the demotion backtest (WHO moves) is **AUC 0.4953, chance**, against raw OAA's 0.6183.

So the model transports value well and cannot predict who actually gets moved. Every
surface from this lane says **"value at position X"** or "the profile fits X", never
"should be moved" or "will move". The raw-OAA superiority on the who-moves label is a
separate unexplored question and is not claimed here.

## 5. Gates

This lane ships DISPLAY, not grades. Fences that bound it:

1. **Nothing from this lane enters eFV.** Defense into eFV is a twice-measured loss
   ledger (`prospect_def_value` eFV swap rejected; `xfv_defense_tools` deprecated, every
   arm regresses, binding constraint is the offense-dominated 6yr WAR target).
2. **The arm gate must not change the conversion-accuracy MAE** on the 169-conversion
   validation set, because it only removes candidates. Re-run it and confirm; a change
   means the gate is doing something other than gating.
3. **Report how many players lose a candidate position** and which, since that is the
   entire visible effect.
4. **Catchers stay out of the first cut.** Savant returns zero catcher rows for OAA in
   every season, so C has no rate to transport. Framing and pop time are separate feeds
   with their own stabilization behaviour.
5. **Prospects get no measured arm.** There is no public MiLB tracking. A prospect-side
   read rides scout `tool_throw` (2017-2020 coverage only, disclose it), the MiLB
   games-by-position census and the migration matrix, and must not be presented as the
   same kind of number as an MLB arm velocity.

## 6. What would make this a NO-SHIP

- The derived floors do not separate positions (if 3B and 2B incumbents throw the same,
  the gate encodes nothing and should not ship).
- Applying the gate changes conversion-accuracy MAE, meaning it is doing more than
  removing candidates.
- Arm coverage is too thin on the live population to gate without inventing a default for
  most players. A gate that fires on a minority and defaults everyone else is a display
  of the data's absence, not of the player's arm.
