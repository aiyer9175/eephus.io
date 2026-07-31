# Rng+ (legs): the surviving half of owner ask 1

Shipped 2026-07-31, display only, on the Alchemy Lab Position Fit panel. Gate and
verdict in one document because the measurement came first and the scope was narrowed by
it rather than after it.

## 1. Why there is a leg indicator and not an arm indicator

The arm half of ask 1 was measured and NO-SHIPPED
(`CONVERSION_ARM_GATE_VERDICT.md`). Cross-sectionally 3B throws 5.1 mph harder than 2B,
which looks like confirmation, but within the SAME player in the SAME season throwing
from two spots, outfield reads **+7.46 mph** over infield on 102 pairs with 98% same
direction agreement. So 3.69 of that 5.1 is throw CONTEXT. Context-adjusted the whole
infield spread is **1.94 mph** against a within-position sd of **3.80**, and 3B minus SS
is **+0.50**. Arm barely selects positions inside the infield.

Sprint speed is the instrument that survived, and unlike arm mph there is an OUTCOME to
validate it against.

## 2. The measurement, and it is a restriction

Against OAA per 1000 innings at the position played (>=400 innings, 2016-2026):

| position | r | 95% CI | ships |
|---|---|---|---|
| CF | **+0.428** | [+0.342, +0.507] | **yes** |
| LF | **+0.416** | [+0.323, +0.501] | **yes** |
| RF | +0.269 | [+0.167, +0.365] | **no, see below** |
| 2B | +0.205 | [+0.102, +0.303] | no |
| 1B | +0.081 | [-0.023, +0.182] | no |
| 3B | -0.004 | [-0.108, +0.100] | no |
| SS | -0.020 | [-0.122, +0.083] | no |

The restriction IS the finding. At shortstop and third base the correlation between
sprint speed and range is indistinguishable from zero, so a speed meter on an infield
destination row would show a reader a measured nothing dressed up as information.

## 3. Why RIGHT FIELD is excluded despite clearing the headline bar

RF's +0.269 has a CI comfortably clear of +0.15. But split it:

| RF subgroup | n | r | 95% CI |
|---|---|---|---|
| all RF regulars | 336 | +0.269 | [+0.167, +0.365] |
| **pure corner** (<100 career CF innings) | 113 | **+0.075** | **[-0.111, +0.256]** |

The RF signal is carried by displaced centre fielders. For a right fielder who has never
played centre, which is exactly the reader RF would be aimed at, the correlation cannot
clear zero. LF survives the identical test (**+0.359** [+0.163, +0.528], n=89) and is not
restriction of range: pure-corner LF sprint sd is 0.79 against 0.97 for all LF.

So the ship set is **LF and CF**. RF is readmitted only if its pure-corner CI clears zero
on a later regeneration.

## 4. Two errors caught before shipping, recorded so they are not repeated

**The population was wrong throughout the first measurement.** Every number originally
attributed to "the served board" was measured on `data/positional_fit.json` (464 rows),
which is excluded at `deploy/data_exclude.txt:50` and never reaches a browser. The served
file is `data/positional_fit_ui.json` (235 rows), fetched at `assets/pal.js:38`. Measured
on each:

| | full artifact (never served) | **served board** |
|---|---|---|
| rows | 464 | **235** |
| sprint coverage | 462 (99.6%) | **235 (100%)** |
| Rng+ min / p10 / p50 / p90 / max | 62 / 87 / 101 / 112 / 124 | **80 / 89 / 102 / 113 / 124** |
| below 80 | 2.4% | **0.0%** |
| catchers | 75 | **0** |

The consequences were not cosmetic. The justification offered for an uncapped scale was
"2.4% below 80", which is **0.0%** on the surface that renders. And a risk slot was spent
prescribing that the meter be suppressed for catchers, on a board that contains **zero**
catchers, while the actual display bottom (Naylor 24.6, Hoskins 24.8, France 24.8,
Horwitz 24.9, Alvarez 24.9 ft/s) went undiscussed.

**The whitelist rule was written inverted.** It read "show the indicator only where the
95% CI of r excludes +0.15". A CI lying entirely BELOW +0.15 also excludes it, so the
literal rule ADMITS 3B ([-0.108, +0.100]) and SS ([-0.122, +0.083]) while rejecting 1B
([-0.023, +0.182]), which contains it. The rule as shipped and as tested is **lower bound
above +0.15**. `test_pal_smoke.py` asserts the bound, not the exclusion, precisely because
the inverted form would have passed.

## 5. What shipped

- **Rng+**, Arkmetric convention 3 (100 + 10z), anchored on the current-season MLB
  position-player sprint pool (2026: n=513, mean 27.30 ft/s, sd 1.37). Ten points is one
  league standard deviation. Served range 80 to 124.
- **The per-destination percentile**, which is the number a reader acts on. "28.4 ft/s"
  means nothing until it is the median of centre fielders. Pools are built from the
  artifact's own evidence log, >=400 innings at the position over the trailing three
  seasons: LF n=60 (p10 26.0, p50 27.5, p90 28.7), CF n=67 (27.1 / 28.4 / 29.7).
- **Rendered on LF and CF destination bars only**, inside the per-player Position Fit
  panel. 203 of 235 served rows have such a destination, and all 203 carry a read.
- Every number is baked by the producer (`build_site.build_positional_fit_payload`).
  Zero model math in JS, per house rule.

## 6. What did NOT ship, deliberately

**Nothing enters the model.** `positional_fit.py` gets no sprint term and does not import
the feed, which `test_pal_smoke.py` asserts by source inspection. OAA already contains the
legs, so a sprint feature would double-count, which is the same argument that rejected the
arm feature.

**No runs-denominated quote.** The outfield slope is era-unstable: +3.141 OAA/1000inn per
ft/s trained on 2016-2021 against +2.331 on 2022-2026, a 26% swing. Publishing "worth N
runs" off a coefficient that moves that much would be a false precision. The percentile is
stable and is what ships.

**No prospect bridge in v1.** There is no MiLB tracking anywhere
(`DEFENSIVE_SOURCE_PROBE.md`; `timeseries.json` prospect_savant_count is 0), so a prospect
could only ever get a GRADE TRANSLATION, never a measurement. The translation is strong
(spearman 0.7711 between pre-debut Speed grade and career ft/s on 627 debuted hitters,
beating the published stolen-base anchor's 0.7477) and it is a separate ship with its own
coverage disclosure, because only 40.2% of active non-pitchers carry a Speed grade.

## 7. Standing conditions

1. Whitelist regenerates from measurement. A position that stops clearing a CI lower bound
   above +0.15 loses the display that build.
2. RF stays out until its pure-corner CI clears zero.
3. `positional_fit.json` and `conversion_accuracy` are unchanged by this lane. If they
   move, something entered the model that should not have.
4. Coverage floor 90% of served rows. Today 100%.
