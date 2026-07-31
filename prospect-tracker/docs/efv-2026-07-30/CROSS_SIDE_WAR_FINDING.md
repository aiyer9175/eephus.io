# The cross-side finding: consensus FV is not comparable across sides

Measured 2026-07-30, planning/execution session. This is the load-bearing measurement for
the owner's question "are we systemically underrating pitchers?" and for the Phase A board
basis decision (D1). It changes the answer.

## The measurement

Pool: `data/xfv_scored.json` (hitters) + `data/xfv_scored_pitcher.json` (pitchers),
uncensored resolved rows only (realized 6-year bWAR observed, censored rows excluded).
n = 1,500 hit / 1,537 pit.

`consensus_fv` is a model **INPUT**, not a fitted output, so this cut is NOT contaminated by
the in-sample calibration trap that `DEFECT_C_LOSS_LEDGER.md:176-181` warns about (that trap
is why the same artifacts show a hitter calibration slope of 1.0090, which is an artifact of
`efv_score.run()` fitting its output calibration on the rows it scores and must not be read
as evidence of anything).

**Mean realized first-6-year bWAR, by consensus FV bucket:**

| consensus FV | HIT n | HIT mean | PIT n | PIT mean | hit/pit |
|---|---|---|---|---|---|
| 35-40 | 659 | 0.095 | 746 | 0.124 | **0.76** |
| 40-45 | 525 | 0.531 | 527 | 0.626 | **0.85** |
| 45-50 | 171 | 3.037 | 149 | 2.104 | 1.44 |
| 50-55 | 70 | 6.656 | 62 | 5.317 | 1.25 |
| 55-60 | 46 | 10.087 | 42 | 4.276 | **2.36** |
| 60+ | 29 | 14.137 | 11 | 9.065 | 1.56 |

| aggregate | HIT | PIT | ratio |
|---|---|---|---|
| consensus >= 50 | n=145, 9.241 | n=115, 5.295 | **1.75** |
| consensus >= 55 | n=75, 11.653 | n=53, 5.270 | **2.21** |

## What it means

**One scouting FV number does not mean one expected outcome across sides.** At consensus
FV 55 and above a hitter has historically returned roughly 2.2x the first-6-year WAR of a
pitcher at the same grade. The gap widens with grade and **INVERTS below FV 45**, where
pitchers modestly outperform (ratio 0.76 / 0.85).

Three consequences, in order of importance:

1. **The consensus top 100 (28 pitchers) is the mis-scaled view, not the truth.** Ranking a
   joint board by consensus FV, or by any per-side quantile remap OF consensus, systematically
   over-places pitchers at the top because it treats an FV 55 arm as equal to an FV 55 bat.
   The served board's 8 pitchers per 100 is closer to WAR-truth than consensus's 28.
   **Therefore "restore the quantile basis" is NOT the fix** - the retired
   `xfv_grade_quantile` field is a per-side rank-quantile remap onto each side's own
   consensus distribution, so its joint top-N pitcher share is IDENTICALLY the consensus
   share by construction (independently confirmed: the per-side pre-fix display multiset
   equals that side's consensus multiset exactly, n=1,970 hit / 2,290 pit). Reverting the
   board to it would restore a known mis-scaling and would also re-break the single-basis
   coherence the owner deliberately bought on 2026-07-25.
2. **The model separating the sides at the top is pricing a real effect.** This is the
   measured basis for the position `efv_board_scale.py:159-164` records as the owner's own
   reasoning at enable time ("by the Clemens framework, hitter/pitcher FVs translate to
   different outcomes"). That reasoning is correct. What was missing was this measurement.
3. **But the model appears to over-separate modestly.** In-sample top-25 by prediction:
   hitters predicted 12.393 / realized 13.030; pitchers predicted 6.313 / realized 7.391.
   So the model's top-end hit:pit prediction ratio is 1.96 against a realized 1.76, i.e. it
   over-separates by roughly 10%, and BOTH sides under-predict their own top tail (hit top-5%
   under-predicts by 2.13 WAR). Direction of the needed correction: pitchers UP slightly
   relative to hitters, which is the same direction as the disabled `efv_board_scale` affine
   (hit intercept -2.603 vs pit -0.579).

## Why this still does not license re-enabling the affine

The 10% over-separation is measured IN-SAMPLE (see the contamination note above) on 25
pitcher rows. `efv_board_scale`'s own pre-registered gate on exactly this quantity is a
measured NULL and its per-split estimates are wildly unstable:
gap@55 point -1.87, boot CI90 [-5.15, +1.31], permutation p 0.259, zero-info control CI90
[-2.72, +2.69], time splits **[+1.34, -8.31, -2.47, +4.21, -8.82]**. A statistic whose five
time splits span +1.34 to -8.82 has not been measured.

**Conclusion: cross-side calibration AT THE TOP OF THE BOARD is not resolvable at current n**
(12 pitcher rows above raw 56 in the labelled pool). The board basis is therefore a
product/policy decision, not a measurable one, and it must be recorded as a judgment call.
Re-enabling the affine on the evidence above would repeat precisely the error the 2026-07-29
session corrected when it disabled the module.

## Recommendation to the owner (D1)

**Keep the board on raw `xfv_grade`. Do not revert to the quantile. Do not re-enable the
per-side affine.** Then fix what is genuinely broken, none of which requires the basis to
move:

- the **third-basis** defect (history and movement run on the retired quantile field while
  the board serves raw: Jesus Made 59.00 in history vs 64.24 served, Bradfield 46.60 vs
  50.97, Ryan Sloan 54.80 vs 56.52) - this is the defect behind a top-3% hitter appearing
  to "grade 49.1", and it is pure correctness;
- the **epoch guard**, so a future basis change cannot publish a re-rank as player movement
  (it already happened: the 2026-07-29 board-scale disable moved Seth Hernandez 22 -> 50 and
  his card reads "down 33, confidence high" for a change no player caused);
- the **composition tripwire**, so any future basis change that moves the top-100 side share
  outside a registered band fails the suite instead of shipping silently;
- the per-player defects that are real regardless of basis: the 7-day-IL injury factor
  (Seth Hernandez, 4 IL days costing 1.25 FV) and the bare backgrade factor path.

## What to tell the owner about the four named pitchers

They were not marked down. Most carry `xfv_minus_consensus` of ~0.0 (dzierwa +0.0,
hardin +0.0, scarborough -0.0). They were **displaced** by hitter raw grades that are higher
because the model predicts elite hitters will produce far more WAR, and the resolved cohorts
say that is broadly right. The honest headline is: the board is closer to correct than
consensus is, the model over-separates by perhaps 10% at the very top, and that 10% cannot
currently be measured well enough to correct responsibly.

The genuine per-player wins available: Seth Hernandez recovers roughly 18 board spots from
the injury-factor fix alone.
