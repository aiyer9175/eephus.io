# Pre-registration: repairing the $0 floor at the bottom of the board

Commissioned by the owner 2026-07-30. Written BEFORE any fitting. Two candidate repairs
for this defect have already been measured and REFUTED, so this file starts by saying
what they were, because the fastest way to waste this lane is to rediscover them.

## 1. The defect

**6,390 of 9,331 served rows price at exactly $0 (68.5%).** Concentrated at the bottom:
88.3% of active rows, 72.2% of busts. The anchor branch owns 6,336 of the 6,384 zero
rows.

On the tier view the same defect reads:

| tier | live n | model surplus | raw pre-calibration |
|---|---|---|---|
| hitter 35+ | 1,725 | **$0.0M** | $1.3M |
| pitcher 35+ | 2,097 | **$0.0M** | $1.2M |

So the engine computes a non-zero figure for 3,822 players and then calibration maps it
to exactly zero.

**Mechanism.** `value_framework.expected_surplus_usd` uses a direct dollar anchor below
`cutover_fv` (config: `anchor_usd_40fv_position` $2.0M at FV 40, `decay_per_point` 0.16,
cutover 40.0, bridge to 45.0). That raw figure then passes through `apply_calibration`,
whose shipped map is `linear-real-v5-todaypriced-2026-07-24`: isotonic knots
x = [0.0, 1.677, 20.0, 60.0, 400.0], y = [0.0, 0.0, 25.33, 80.63, 550.68], encoded as
`max(0, 1.382491*raw - 2.318551)`. **The zero-cross is at raw $1.677M.** Every player
whose raw surplus is under $1.677M is clamped to zero, and the entire bottom tier sits
under it.

The floor is therefore not a modelling opinion about those players. It is a v5
calibration fitted on a different population meeting a fixed Edwards anchor, with the
crossing point landing inside the densest part of the board.

## 2. What has already been refuted. Do not re-run these.

- **The surplus map refit.** REFUTED, `docs/efv-2026-07-29/DEFECT_C_LOSS_LEDGER.md`.
- **C-prime, the ramped calibration exemption.** REFUTED and clearly: held-out MAE
  9.808 -> 10.514, **0 of 6 folds better**, worse than its own permutation null band.

Both attacked the calibration layer. That is the evidence this lane should read as
"the calibration is not the free parameter", and look at the anchor and the display
contract instead.

## 3. The awkward fact that shapes the design

The live median first-6yr WAR in that tier is **negative**: -1.05 for hitters, -0.45 for
pitchers. So "these players are worth about nothing" is defensible. What is not
defensible is the mechanism producing it, because:

1. A hard $0 is a false precision. It says "worth nothing", when what the model knows is
   "below the resolution at which this engine can price anything".
2. It is discontinuous. A player one dollar of raw surplus above the crossing prices at
   $0.00, another just below also prices at $0.00, and their ordering is destroyed. The
   board still ranks them, on grade, but the dollar column silently stops carrying
   information for two thirds of the site.
3. It collides with a known nearby defect. C6, the reliever Edwards-bridge inversion,
   lives in the SAME branch: surplus FALLS as grade RISES for RP/SIRP/MIRP/CL between
   FV40 and FV40.5, and is currently invisible ONLY because the v5 zero floor swallows
   it. Repairing the floor will EXPOSE C6. That is not a reason to avoid the repair, but
   the two must be sequenced, and `GATED_CANDIDATES.md` C6 says they must not be
   attempted jointly.

## 4. Two arms, deliberately ordered

**ARM 1, display (cheap, no model change, ships first).** Stop rendering a hard $0 where
the engine has no resolution. Below the calibration zero-cross, show a "below threshold"
treatment or the rank-based read instead of a dollar figure, and say why in the tooltip.
This is honest immediately, it costs nothing, and it is reversible. It does NOT fix the
pricing; it stops the pricing from making a claim it cannot support.

**ARM 2, the pricing repair itself.** The hypothesis the two refuted attempts point at:
the defect is the ANCHOR meeting the calibration, not the calibration alone. Candidates,
each measured separately:

- (a) Re-fit the low-tier anchor so the raw figure at the modal bottom grade lands ABOVE
  the calibration zero-cross, rather than under it by construction.
- (b) Move the crossing itself by re-fitting calibration on a population that INCLUDES
  the bottom tier, rather than one that priced it out.
- (c) Accept a floor but make it a small positive constant with a stated meaning
  ("option value of a live org player") rather than zero.

(c) is the weakest and is listed to be tested and dismissed on evidence rather than
taste, because it is the one someone will otherwise propose later.

## 5. Gates

**Primary:** held-out surplus MAE against the realized-value target, forward-chained,
with the four mandatory controls. C-prime is the calibrated bar: it lost at MAE 9.808 ->
10.514 with 0 of 6 folds better, so a candidate must beat the incumbent on MAE AND win a
majority of folds.

**Monotonicity, hard requirement:** surplus must be non-decreasing in grade within side
and role across the whole range. Any candidate that exposes C6 without fixing it FAILS
this, which is the mechanism that keeps the two lanes sequenced rather than tangled.

**The tripwire stays red until it should not be.** `test_value_framework::
test_calibration_layer_is_real_fit_and_monotone` is currently red BY DESIGN, documenting
this defect. It must go green because the defect is fixed, never because the assertion was
widened.

**Blast radius, reported:** how many of the 9,331 rows change price, the distribution of
the change, and confirmation that grade, rank and the board ORDER do not move. Surplus
prices off the rank quantile, so a pure pricing repair should leave ordering untouched;
if it does not, the change is bigger than advertised.

## 6. What would make this a NO-SHIP

- Fails to beat the incumbent MAE, or wins pooled but loses a majority of folds.
- Exposes the C6 reliever inversion without repairing it.
- Moves board ordering at all.
- Requires re-fitting the calibration on a population chosen to produce the answer, which
  is the trap the P0 in `EFV_GATE_STANDARD.md` section 4 already flags: the calibration
  was fit on RAW per-source median FV while production prices the NORMALIZED consensus,
  so surplus dollars are provisional until that is closed.

Arm 1 ships regardless of Arm 2's verdict, because a false-precision $0 is worth removing
even if the underlying price stays unresolvable.

---

# MEASUREMENT (added 2026-07-31, before any fit)

Ran the Arm 2 diagnostics the gate above called for. Three results.

## M1. The cause is the ANCHOR sitting under the cross, not the calibration alone

Raw (pre-calibration) surplus against the $1.677M clamp point:

| FV | hitter raw | hitter calibrated | RP raw | RP calibrated |
|---|---|---|---|---|
| 35.0 | 0.899 | **0.000** | 0.809 | **0.000** |
| 37.5 | 1.341 | **0.000** | 1.207 | **0.000** |
| 38.5 | 1.573 | **0.000** | 1.416 | **0.000** |
| 39.0 | 1.704 | 0.038 | 1.534 | **0.000** |
| 40.0 | 2.000 | 0.447 | 1.800 | 0.170 |

**The first grade that prices above zero is FV 39.0 for hitters and FV 40.0 for
relievers.** Everything below clamps. That is the 68.5%, and it is not a calibration bug
in isolation: the calibration is a fixed linear map, and the anchor simply does not reach
it until FV 39. Candidate (a) from the gate above (move the anchor) is therefore the arm
that actually addresses the mechanism, and candidate (b) (re-fit the calibration) is
attacking the wrong end.

Note the anchor at FV 40 is already ABOVE the cross ($2.000M against $1.677M). So the
repair is not "the anchor is too low" globally. It is that `decay_per_point` 0.16 pulls
the sub-40 range under the cross within two grade points.

## M2. C6 confirmed, and it is worse and wider than registered

`GATED_CANDIDATES.md` describes the reliever bridge inversion as sitting "between FV40
and FV40.5". Measured, it runs the whole bridge and does not stop:

| FV | RP raw | RP calibrated |
|---|---|---|
| 40.0 | 1.800 | 0.170 |
| 41.0 | 1.774 | 0.134 |
| 42.0 | 1.747 | 0.097 |
| 43.0 | 1.721 | 0.061 |
| 44.0 | 1.694 | 0.024 |
| 44.5 | 1.681 | **0.006** |

Raw surplus falls monotonically as grade RISES (about -0.003M per 0.1 FV), identically for
RP, SIRP and CL. After calibration subtracts its constant, the effect compounds: **a FV
44.5 reliever prices at 28 times LESS than a FV 40 reliever.** Hitters over the same range
behave correctly (2.000 rising to 8.444).

## M3. But the served board does not currently expose it

Checked before claiming a live defect: the 412 served active pitchers graded FV 39.5 to
45.0 price from 0.0 at the bottom of the band to 8.1 at the top, i.e. RISING. So the
served path is not routing them through the RP branch that carries the inversion, which
is consistent with C6 being registered as latent rather than visible.

**That is the sequencing risk the gate above already named, now quantified.** The
inversion is a live landmine in the pricing function rather than a live defect on the
board. If Arm 2 lifts the floor and anything later routes relievers onto the RP curve,
28x backwards pricing becomes visible in the same motion. The monotonicity gate stays a
hard requirement, and C6 should be repaired BEFORE or WITH the anchor, never after.

## Recommendation

Candidate (a), re-anchoring so the sub-40 range clears the cross, is the arm worth
building, and the measurement says exactly how far it has to move. Candidate (b) is
misdirected. Candidate (c), a small positive constant floor, remains the weakest and is
now clearly unnecessary given (a) has a mechanical target.

Do not start it without C6 in the same lane.
