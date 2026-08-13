# Serve-chain verification: what actually moves if xfv_war is corrected at source

Verified 2026-08-13 against the tree, at the owner's instruction, as the
prerequisite for the C-1 grade-basis epoch. Read-only; nothing changed.

This CORRECTS my own earlier description twice, in both directions.

## The chain, as it actually is

| consumer | reads | monotone in `xfv_war`? |
| --- | --- | --- |
| board grade AND board order | `xfv_grade = vf.outcome_implied_fv(xfv_war)`, `efv_score.py:1473` | YES |
| within-tie tiebreak | `board_sort_key = round(_war_unclamped, 6)`, `:2157` | YES |
| surplus dollars | `xfv_grade_display`, a quantile map ordered by **`rank_war`**, `:2189-2191` | **NO** |
| `rank_war` | `(1 - lam) * cons_war + lam * xfv_war`, `:1923` | **NO** |

`storage.py:4866` fixes `BOARD_GRADE_FIELD = "xfv_grade"` and the surrounding
note records the 2026-07-25 owner decision that the raw grade is "the single
number, everywhere", for ordering and display alike. Three orderings coexisting
is the exact bug that constant was created to prevent, and the owner hit it twice.

## What this means for the epoch

**GOOD NEWS, and it corrects my earlier claim.** Board ORDER does not move. The
grade is a strictly increasing function of `xfv_war` and the tiebreak is another,
so composing them with a strictly increasing affine correction leaves the entire
ordering identical. I previously told the owner that applying at source "moves
every displayed grade" and implied the board re-ranks. The VALUES move; the ORDER
does not. That is a materially smaller change than I described.

**BAD NEWS, and it is the part that needs the gate.** Dollars are NOT safe, and
this corrects the other direction of my earlier claim. Surplus prices off
`xfv_grade_display`, which is built by ordering the pool on `rank_war`, and
`rank_war` is the BLEND. Substituting `a_c + b_c * xfv_war` gives

    rank_war' = (1 - lam) * cons_war + lam * a_c + lam * b_c * xfv_war

so the model leg now carries `lam * b_c` against the consensus leg's `1 - lam`.
Two consequences, both real:

1. **The blend is re-weighted.** At `b_c` near 0.63 that is roughly a 37% cut to
   the effective lambda. **Blend-lambda shifts are a banned lane** (TOST RULED
   OUT at 0.65 / 0.60 / 0.51). The epoch therefore cannot ship without an
   EXPLICIT lambda re-gate; taking it as a side effect is precisely what the ban
   exists to stop.
2. **`rank_war` can reorder**, because a re-weighted blend is not a monotone
   transform of the old one: two players with different consensus-to-model mixes
   can swap. Every swap moves a quantile position, and quantile position is what
   prices the dollars. So the dollar effect is NOT zero and must be measured, not
   inherited from the 2026-07-29 note, which was written about a correction
   applied somewhere else.

## The narrower option this verification opens

Because board order and grade both hang off `xfv_war` while dollars hang off
`rank_war`, the two can be separated:

- correct `xfv_war` for the GRADE and the EXPORTED WAR, and
- leave the BLEND leg reading the uncorrected value.

That yields calibrated grades and a calibrated published WAR, with lambda
untouched, `rank_war` untouched, quantile positions untouched and therefore
**dollars provably unmoved**, while board order stays identical for the reason
above. It still needs an epoch bump, a fingerprint term and a golden restamp,
because the displayed grade VALUES move, but it needs no lambda re-gate and no
dollar measurement.

The cost is that the grade and the blend would read two different versions of the
same quantity, which is a coherence claim someone will have to defend. It is the
narrower path the owner was offered and declined in favour of the full epoch;
recorded here because the verification is what makes its cost concrete, and the
owner's choice was made before this evidence existed.

## The lambda re-gate, quantified 2026-08-13, and it does not pass on the pitcher side

The epoch's implicit lambda change is computable exactly. Substituting
`a_c + b_c * xfv_war` leaves the consensus leg at `1 - lam` and puts the model leg
at `lam * b_c`, so the equivalent pure lambda is

    lam_eff = lam * b_c / ((1 - lam) + lam * b_c)

Using the leave-one-fold-out coefficients this lane already fitted:

| side | lam shipped | b_c per fold | mean b_c | **lam_eff** | shift | clamp floor |
| --- | --- | --- | --- | --- | --- | --- |
| hit | 0.70 | 0.637 0.640 0.609 0.577 0.644 | 0.6212 | **0.5917** | -0.108 | +0.242 clear |
| pit | 0.57 | 0.308 0.651 0.350 0.417 0.380 | 0.4213 | **0.3583** | -0.212 | **+0.008 clear** |

`_BLEND_LAMBDA_CLAMP` is `(0.35, 0.90)`.

**HITTERS: acceptable.** 0.5917 lands beside 0.60, which the TOST battery already
tested and RULED OUT as a difference. The hitter side's implicit shift is
therefore inside territory that has been measured and found to change nothing.

**PITCHERS: this is a stop.** 0.3583 sits **0.0083 above the clamp floor the
model imposes on itself**. The clamp exists precisely to stop lambda going that
low, and nothing near 0.36 has ever been tested; the TOST work covered 0.65,
0.60 and 0.51. The full epoch would therefore drive the pitcher blend to the edge
of its own admissible range as an UNMEASURED SIDE EFFECT of a calibration fix.

It is also the least trustworthy number in the lane. Pitcher `b_c` ranges 0.308
to 0.651 across folds, better than a factor of two, which is the same instability
already visible in the pitcher slope CI [0.0677, 1.1341]. So the side whose
correction is least precise is the side whose implied lambda lands on the floor.

**Conclusion: the full epoch cannot ship on the pitcher side as specified.** Not
because the calibration is wrong, but because routing it through the blend spends
the correction as a lambda cut into untested territory. The options that remain
are the narrow path above, which touches no lambda at all, or a hitter-only
epoch, or an explicit and separately gated pitcher lambda decision taken on its
own evidence rather than inherited from a dispersion fit.

## What the full epoch now has to include

1. An explicit blend-lambda re-gate, or an argument that `lam * b_c` against
   `1 - lam` is the intended weighting. Without one the epoch re-opens a banned
   lane.
2. A measured dollar blast radius: rows whose `rank_war` order changes, and the
   resulting surplus movement. The "exactly $0.00" figure does not apply here.
3. Epoch bump, a fingerprint term naming the correction, `prospx_current`
   re-capture inside `vf.valuation_set`, golden restamp.
4. A re-read of every margin measured on the old basis.
5. Board ORDER should be asserted unchanged as a regression test, since that is
   now a provable property rather than a hope.
