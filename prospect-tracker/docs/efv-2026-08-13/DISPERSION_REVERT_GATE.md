# C-7: revert the dispersion correction to identity, on the owner's decision

Pre-registered 2026-08-14 BEFORE the coefficients were changed. Results section
deliberately empty at commit so git timestamps this.

## Status: an OWNER DECISION, not a gated search for a pass

This is the option `TAIL_PRESERVING_REFIT_GATE.md` left open as (b), "revert to
identity and eat the sub-45 cost", after C-1b aborted. The owner has now taken it,
twice-stated, after being shown the measured trade. **This gate therefore does not
decide WHETHER to ship.** It exists to bound the damage: to state in advance what
must be re-derived, what is permitted to move, and what would make the revert unsafe
rather than merely costly.

That distinction is deliberate. A gate written to adjudicate a decision already made
would be theatre, and clause-shopping toward a foregone conclusion is the failure
this programme has recorded against itself twice.

## What is being reverted

`efv_score.apply_dispersion_correction`, shipped 2026-08-14 as a grade-basis epoch
under `GRADE_BASIS_EPOCH_GATE.md`:

    hit  a_c 0.470359  b_c 0.663929
    pit  a_c 0.493744  b_c 0.546915

goes to the identity `max(-2.0, war)`. One function, so all FOUR call sites move
together: `run`, `run_live` (twice, including the healthy counterfactual),
`score_history`, `run_backgrade` (twice). The four-site rule is the lesson from
2026-08-13b, where a new scoring seam was applied at three sites and put the FV
history series on a different basis for 1,882 players.

## The trade, as measured before the decision (C-1b, pre-epoch board)

| consensus band | affine (incumbent) | identity | n |
| --- | --- | --- | --- |
| 55+ | -4.95 | +0.14 | 14 |
| 50 to 55 | -2.90 | +0.02 | 35 |
| 45 to 50 | -0.78 | +0.84 | 139 |
| below 45 | -4.99 | **-10.97** | 4,470 |

And against realized WAR, out of fold (C-1c): the corrected arm is resolvably MORE
accurate on the full pool (hit paired -0.2787 CI95 [-0.334, -0.224]; pit -0.1415
[-0.173, -0.109]) and nominally better on all four pre-decision elite bands.

**So the revert is expected to cost measurable accuracy and to buy industry
agreement at the top.** That is the trade the owner accepted. It is recorded here
in advance so the Results cannot be read as a discovery that the revert was free.

C-6 changes how the sub-45 column should be read: 2,651 of those rows carry a
fabricated consensus and 525 sit on the abstention floor, so much of the -10.97 is
measured against comparisons that are not comparisons. It does NOT change the
accuracy column, which is measured against outcomes.

## What must be re-derived, and this list is the point of the gate

1. **Fingerprint.** `storage.BOARD_BASIS_FINGERPRINT` carries
   `disp=hit:0.470359/0.663929|pit:0.493744/0.546915`. It is DERIVED, so it moves on
   its own and the pinned copy must be restamped in the same commit.
2. **Epoch.** `BOARD_RANK_BASIS_EPOCH` bumps, so the movement engine does not
   difference ranks across the basis change.
3. **`prospx_current` re-capture** inside the valuation set.
4. **Golden restamp**, with the reason in the ledger.
5. **Every margin re-read FRESH**, never against a stored figure.
6. **The `Level calibration` chip self-retires**: it renders only when
   `abs(_corr_delta) >= 0.05`, and the identity map makes that delta exactly 0.0 for
   every row. Asserted, not assumed.

## HARD clauses. These bound the damage; they do not re-litigate the decision.

1. **Monotone and floored.** The served map is strictly increasing on a dense
   lattice and never emits below -2.0. Identity satisfies this trivially, which is
   why it is a check and not an argument.
2. **The four call sites move together.** No path may serve a corrected WAR after
   this commit. Asserted by searching the shipped source for a second correction
   seam, and by the history-basis pin that caught the three-site defect.
3. **Consequence-pinned, not constant-pinned.** The tests must assert that the
   SERVED WAR equals the model WAR, not that two coefficients equal 0.0 and 1.0. A
   pin on the constants goes green for any re-fit that happens to write those values
   while a second correction is applied elsewhere.
4. **The chip is gone from every row**, and no row publishes a `Level calibration`
   factor.
5. **C-6 survives.** The suppressed set must still be exactly the two declared
   cohorts, and `xfv_minus_consensus` must still be null on all of them. The floor
   cohort is EXPECTED to grow, because removing the `+0.47` lift pushes more rows
   below zero. Its new size is reported, not gated.

## Abort conditions

- ABORT if the served map is not strictly increasing.
- ABORT if any row's served WAR differs from its model WAR after the change.
- ABORT if the fingerprint does not change, which would mean the basis moved
  invisibly and is the exact failure `board_basis_fingerprint` exists to prevent.

## Reported, not gated

These are consequences the owner accepted and they are measured and published rather
than used as pass conditions: the per-band `eFV minus consensus` table on the current
board, the change in the FV20 floor population, the movement in `p_bust` and in
served dollars, and the fresh full-pool and elite-band accuracy deltas.

## Results

(empty at pre-registration)
