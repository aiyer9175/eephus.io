# Rest-of-season talent basis: the de-aged basis SHIPS

**Date:** 2026-08-05
**Decision:** OWNER, overriding the executing agent's recommendation.
**Scope:** the rest-of-season (rental) leg of veteran surplus in
`data/mlb_projections.json` (`surRos`, `rosWar`, and therefore `surTotal` and
every trade-board price that reads it).
**Revert:** one line. `proj_export.ROS_TALENT_BASIS = "first_season"`.

---

## 1. The question

`proj_export`'s rest-of-season leg prices the balance of the IN-PROGRESS season
(2026). It priced it on `war[0]`, which is the FIRST_SEASON (**2027**)
projection: one full aging year PAST the season actually being sold. For an
aging veteran that is a real, signed bias downward. For a 21-year-old it is a
bias upward.

The pre-existing comment defended `war[0]` on the grounds that the leg
"deliberately does not read 2026 results to date, which measure what the SELLING
club already banked." That reasoning is sound about BANKED PRODUCTION and silent
about TALENT TIMING. The only question here is which season's talent estimate
the remainder is priced on. Nothing about re-banking April changed.

## 2. What shipped

The remainder is now priced on `war[0]` scaled by the exact **one-year inverse
of the platform's own aging operator**.

`fa_market._decay_path` is the only WAR aging operator in the tree. Moving INTO
age `a` it ADDS `curve_delta(side, role, "war_rate", a)` to the per-600-PA /
per-250-BF WAR rate and `curve_delta(side, role, "pt", a)` to the projected
exposure, then re-multiplies. Both deltas are additive, so the step is exactly
invertible:

```
rate       = war1 / expo * per                       per = 600 PA (hit) / 250 BF (pit)
rate_back  = rate - curve_delta(war_rate, age)       SUBTRACT: the forward step adds
expo_back  = max(0, expo - curve_delta(pt, age))
war_back   = max(0, rate_back) * expo_back / per
ratio      = war_back / war1_champ                   summed over sides for two-way
```

The RATIO (not the absolute de-aged WAR) is applied to the shipped `war[0]`, so
the ML quantile head's information survives and only the aging timing moves.
Both sides of a two-way player are summed before the ratio is taken, matching
the way the served `war` path sums them. The per-side universe gate
(`MIN_PA=100` / `MIN_IP=30`) is applied inside the operator, so it can never
de-age a side the served row does not contain.

Implementation: `proj_export.deaged_year1` (the operator),
`proj_export.ros_talent_basis` (the switch and the fallback policy),
`proj_export.ROS_TALENT_BASIS` (the constant). `tools/ros_talent_basis_probe.py`
now IMPORTS the same function rather than carrying its own copy, so the probe
and production cannot drift apart.

Published, per served row:

| field | meaning |
| --- | --- |
| `rosWar` | `basis_war * rosFrac`, the WAR the acquiring club receives, on the SAME talent the dollars were priced off |
| `rosBasis` | `de_aged`, `first_season`, or `first_season_unresolved` |
| `ros_talent_basis` (payload root) | the constant the export ran under |

`rosWar` moved with the price on purpose. A display WAR that describes different
talent than the dollars beside it is exactly the class of quiet inconsistency
this file keeps paying to remove.

## 3. The unresolved-row policy

The ratio is undefined where the champion year-1 is at or near zero, and where
that year-1 is NEGATIVE a ratio would flip the sign of the priced talent.

Measured on the 2026-08-05 artifact: **134 of the 954** rest-of-season rows are
unresolved. **All 134 for that reason** (champion year-1 at or below
`DEAGE_MIN_CHAMP_WAR = 0.05`); **none** because a side was missing or failed the
gate. Every one of them has `|war[0]| <= 0.46`, i.e. the population this policy
governs is replacement-level and its dollars are small.

**Policy: fall back to the first_season basis, and SAY SO** in the payload
(`rosBasis = "first_season_unresolved"`). Rejected alternatives:

* a silent 1.0 multiplier, which is numerically the same thing and publishes a
  de-aged basis that was never computed;
* an ADDITIVE de-aging (`war[0] + (war_back - war1_champ)`), which for these rows
  asserts a talent change LARGER THAN THE PROJECTION ITSELF, off a denominator
  the model is telling us is noise. For young replacement-level players the
  additive term is negative, so it would push already-negative rentals further
  negative on the strength of the least reliable rows in the set.

A related edge, measured and left alone: 15 resolved rows have `war[0] <= 0`
(all but one are exactly 0.00 or -0.00; the exception is -0.03). The tier kernel
floors production value at $0 for `w <= 0`, so these rows price identically
under either basis. No special case was added for them.

## 4. What was measured

`python tools/ros_talent_basis_probe.py`, run against
`data/mlb_projections.json` as of 2026-08-05 12:29 (954 vet rows carrying a
rest-of-season leg, `ros_fraction = 0.301`, `dpw_usd = 17,971,003`).
**Wall clock: 0.6 s** end to end, including interpreter start, corpus load and
all 954 rows (the de-aging pass itself is ~0.1 s). A separate 4-player wiring
smoke ran the REAL `_veteran_rows` over a trimmed corpus in 3.6 s and reproduced
the shipped fields by hand.

The baseline is the first_season basis, re-derived from each served row rather
than assumed. The probe DETECTS whether the artifact predates the A2a proration
fix (`f*V(w)` vs `V(f*w)`) instead of hardcoding a correction; on this artifact
it does not (28 of 28 decisive expiring rows match the new convention), so the
deltas below are **pure talent-basis effects with no convexity term mixed in**.

### surTotal change, shipped basis vs the old one

Over ALL 954 rows carrying the leg, unresolved rows counted at their policy
value of exactly $0:

| statistic | USD |
| --- | ---: |
| n | 954 |
| moved up (> $0.50) | 683 |
| moved down (< -$0.50) | 122 |
| unchanged (unresolved policy) | 134 |
| min | -7,391,807 |
| p10 | -123,237 |
| median | **+236,573** |
| mean | **+476,411** |
| p90 | +1,587,991 |
| max | +8,875,436 |
| sum | **+454,496,094** |

Conditioning on the 820 rows where the de-aging is defined: median +$308,795,
mean +$554,263, p10 -$220,810, p90 +$1,876,767, same min/max.

**This is not a uniform uplift.** 683 rows up, 122 down. The down moves are the
young players, who are correctly de-aged DOWNWARD (a 22-year-old's 2026 talent
is below his 2027 projection). The largest single move in the whole set is a
veteran gaining $8.88M; the largest negative is a 21-year-old losing $7.39M.

For reference, the rate-only variant (un-age the WAR rate, hold the Marcel
playing-time projection fixed) is roughly two thirds as large: median +$243,044,
mean +$420,218, max +$5,995,617, sum +$344,579,101, 15 sign flips. It is not a
switchable production basis; it is the obvious step-down if the shipped
magnitude is ever gated back.

### Sign flips: 20

All twenty are **negative to positive**, i.e. rentals that read as
"owed more than he is worth" now read as small positive assets. None flip the
other way.

Trent Grisham (-157,983 to +1,626,217), Kevin Gausman (-501,060 to +1,712,923),
Tyler Mahle (-360,851 to +390,353), Clay Holmes (-450,835 to +1,170,189),
Yandy Diaz (-542,845 to +1,453,164), Ramon Laureano (-280,871 to +309,870),
Dennis Santana (-151,057 to +83,639), Kirby Yates (-159,907 to +168,572),
Justin Steele (-8,514 to +379,753), Tomoyuki Sugano (-504,094 to +342,779),
Mark Leiter Jr. (-63,176 to +254,653), Jesus Sanchez (-80,257 to +168,880),
Kyle Hart (-1,128 to +242,398), Jake Rogers (-69,946 to +176,875),
Enrique Hernandez (-924,308 to +52,725), Burch Smith (-211,857 to +2,282),
Carlos Santana (-151,003 to +196,683), Cal Quantrill (-7,610 to +4,074),
Randal Grichuk (-97,282 to +70,107), Jordan Romano (-807 to +248,821).

Expect trade-board reordering at the bottom of the veteran list.

### Top 15 movers by absolute dollars

| player | pos | age | war[0] | de-aged | delta USD | surTotal before | surTotal after |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Zack Wheeler | SP | 37 | 3.48 | 4.893 | +8,875,436 | +39,765,017 | +48,640,454 |
| Jacob deGrom | SP | 39 | 1.48 | 2.301 | +7,941,477 | -48,412,694 | -40,471,216 |
| Shohei Ohtani | TWP | 32 | 9.14 | 10.394 | +7,875,380 | +480,174,432 | +488,049,812 |
| Konnor Griffin | SS | 21 | 2.33 | 1.643 | -7,391,807 | +172,253,553 | +164,861,746 |
| Freddie Freeman | 1B | 37 | 1.91 | 2.645 | +7,328,644 | +5,161,406 | +12,490,051 |
| A.J. Ewing | CF | 22 | 2.34 | 1.707 | -7,018,350 | +106,763,270 | +99,744,920 |
| Chris Sale | SP | 38 | 2.90 | 3.947 | +6,574,466 | +64,305,504 | +70,879,971 |
| Paul Goldschmidt | 1B | 39 | 0.48 | 1.772 | +6,328,866 | +385,218 | +6,714,085 |
| Roman Anthony | LF | 23 | 2.25 | 1.673 | -6,290,766 | +90,109,863 | +83,819,097 |
| Willson Contreras | 1B | 35 | 1.89 | 2.446 | +6,253,041 | +28,893,037 | +35,146,078 |
| Aaron Judge | RF | 35 | 4.39 | 5.344 | +5,989,702 | +66,558,322 | +72,548,025 |
| Kevin McGonigle | 3B | 22 | 4.17 | 3.378 | -4,971,360 | +355,455,950 | +350,484,590 |
| Logan Gilbert | SP | 30 | 1.98 | 2.408 | +4,909,836 | +40,119,873 | +45,029,709 |
| Bryce Harper | 1B | 34 | 1.95 | 2.359 | +4,795,602 | -48,989,939 | -44,194,337 |
| Max Muncy | 1B | 36 | 2.51 | 3.228 | +4,510,154 | +67,734,475 | +72,244,629 |

### The multiplier by age (the shape the whole argument turns on)

Median de-aging multiplier, resolved rows, re-measured 2026-08-05. Published in
full in `data/ros_talent_basis_probe.json` under `deaging_multiplier_by_age`.

| age | 21 | 22 | 24 | 26 | 28 | 30 | 32 | 34 | 36 | 37 | 39 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| median x | 0.67 | 0.77 | 0.90 | 1.01 | 1.17 | 1.22 | 1.31 | 1.40 | 1.57 | 1.64 | 1.54 |

Monotone in age up to the thin top cells. Over the whole resolved set: min
0.000, median 1.210, max 3.917, and **124 of 820 rows move more than 1.5x**.

## 5. Recorded dissent

Carried here verbatim in substance, and repeated in the code at
`proj_export.ROS_TALENT_BASIS`, so it is not lost in a commit message.

> The de-aging DIRECTION is right: the multiplier is monotone in age, which is
> what a genuine aging correction should look like, and the operator is the
> platform's own fitted curve rather than a new constant. The MAGNITUDE is not
> obviously credible as a ONE-STEP operator. A one-year de-aging worth +40% of
> talent at age 34 is the FORWARD decay path's own steepness read backwards, and
> those curves are fitted on SURVIVORS. Inverting a survivor-fitted population
> decay for an INDIVIDUAL is an assumption, not a measurement. 124 of 820
> resolved rows move more than 1.5x.

Two specific reasons the inverse is not automatically as trustworthy as the
forward step, even though it is algebraically exact:

1. **Survivorship.** The forward curves are corrected for survivorship in the
   direction they were fitted (players who fall out of the sample). Running them
   backwards asks a different question: what this player's talent WAS, given he
   is still here. The correction that makes the forward step honest is not
   guaranteed to make the backward step honest.
2. **The playing-time leg does most of the work.** The exposure delta is the
   aggressive half. For a 34-year-old starter the fitted `pt` delta is large, and
   the full inverse adds it back. The rate-only variant, which does not, is about
   two thirds the size. That the two defensible readings of "the same operator"
   differ by a third is itself evidence that the magnitude is under-determined by
   what has actually been measured.

The owner has decided to ship it. It is implemented as asked, with the switch,
the tag, and the tests, so the decision is reversible and legible rather than
buried.

## 6. Revert

```python
# proj_export.py
ROS_TALENT_BASIS = "first_season"
```

Nothing else changes. The operator is never called under that value (the
callable is lazy), served rows then ship `rosBasis="first_season"`, the payload
root stamps `ros_talent_basis: "first_season"`, and the export note rewrites
itself. `test_the_shipped_basis_is_the_owner_decision` will fail on purpose and
points back at this document, so an accidental flip is loud and a deliberate one
is a two-file edit.

Re-export required to serve it: `python proj_export.py`, then the trade board.

## 7. What is still NOT validated

**Nothing in this tree validates a one-step de-aging operator against observed
same-player year-over-year WAR.** That is the honest state, and it did not change
by shipping.

What a real gate would need, in rough order of cheapness:

1. **Same-player year-over-year WAR pairs**, split by age, comparing the
   observed year-N to year-N+1 change against what `curve_delta` predicts for
   that player's own (side, profile role, exposure) cell. The corpus already has
   the pairs; what is missing is a pre-registered gate on the RESIDUAL of the
   inverse step, not the forward fit that produced the curves.
2. **A held-out check of the exposure leg specifically**, because it is where the
   full and rate-only variants disagree by a third.
3. Beyond that: whether clubs actually PAY the de-aged number for a deadline
   rental is a separate and still-blocked claim. The backtest is blocked for the
   same reasons recorded at the R5.2 concentration premium: historical per-player
   salary and in-season WAR splits do not exist in this tree, and
   `xfv_history` is 0% covered before 2021 and survivor-selected after, leaving
   about 8 usable deadline trades against a pre-registered floor of 40. Do not
   ship a further premium constant before one of those lands.

Until item 1 exists, the correct description of the shipped leg is: *the platform
prices a rental on its own aging curve, run backwards one year, and it has not
tested that this is right for an individual player.*

## 8. Files

| file | change |
| --- | --- |
| `proj_export.py` | `ROS_TALENT_BASIS` + `ROS_TALENT_BASES` + `DEAGE_MIN_CHAMP_WAR`, `recent_history`, `_side_in_universe`, `deaged_year1`, `ros_talent_basis`; `_veteran_rows` memoizes per player; `_apply_contract` prices and publishes on the basis; payload stamps `ros_talent_basis` and a note |
| `tools/ros_talent_basis_probe.py` | imports the SHIPPED operator instead of its own copy; baseline re-derived from the served row; detects the A2a convention instead of assuming it; adds `shipped_effect_all_rows` and `deaging_multiplier_by_age` |
| `test_rest_of_season_control.py` | de-aged arithmetic pinned with hand literals and stubbed curves; an exact-inverse round trip against `fa_market._decay_path`; the universe gate; the unresolved policy; the switch, the lazy revert, and a typo'd constant; the served-artifact proration test is now basis-agnostic with a derived tolerance |
| `data/ros_talent_basis_probe.json` | regenerated (measurement output) |

Re-measure at any time with `python tools/ros_talent_basis_probe.py`. After the
next export the probe's baseline reconstruction handles the shipped basis
automatically: it backs the priced talent out of `rosWar / rosFrac` and
re-prices on `war[0]`, so the reported deltas stay "shipped vs the old basis"
rather than drifting to zero.
