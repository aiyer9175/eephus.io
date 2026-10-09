# The prospect-surplus calibration at the live $/WAR level (CAL_KNOTS_REFIT_17M)

Owner answer VAL1-Q2 (2026-09-30, recorded in DECISIONS_FOR_OWNER.md under "VAL_1
landing (410cccce) and the ETA blend look"): one knots-only refit of the v6 isotonic
prospect-surplus correction map at the live $/WAR level, through
`backtest.fit_calibration_knots`, computing no consensus-FV cell and no held-out
statistic. This note records how that answer was closed and what the closure measured.

## What VAL_1 served (the bridge)

VAL_1 (410cccce) moved prospect surplus to the free-agent winter level of the one
written series (`data/fa_dpw_series.json` `pricing.level_usd`) and applied the v6 map,
fit at the FanGraphs $11.74M, by unit conversion in
`value_framework.calibration_level_scale`: `s * f(x / s)`, `s = level / fit_dpw_flat_usd`
(1.4603 at VAL_1's $17.14M). The bridge is inexact: the league-minimum and anchor legs of
the raw surplus do not scale with the level, so the map was being read off a unit its
knots were not fit in.

## The refit

The refit landed in 70a50b24 (M11_PROSPECT_ARB_VIA_MODEL, 2026-10-09), in the same
change that moved prospect arbitration seasons to the award model on both sides of the
calibration pool:

- entry point `backtest.fit_calibration_knots` (VAL_5 built it; `test_backtest_knots_entry.py`
  proves it returns the knots and a fit stamp only, never calls `backtest.run_backtest`,
  and carries no key naming an FV cell or a tier), run through
  `tools/fit_surplus_calibration.py --target today_flat`;
- training frame and rows: `surplus_backtest_real.build_cohorts`, the pre-debut listings
  of `LISTING_YEARS` 2017-2019 on the normalized consensus frame, filtered by
  `_resolved_only` (washed-out busts, and debuts whose six control seasons end by 2025),
  n = 2,235. No reserved frame can enter: the R-LV list vintages 2020-2021 are outside
  `LISTING_YEARS` and an R-VM 2025+ debut cohort is never resolved by 2025. Nothing is
  stratified by an FV cell;
- surplus expressed at the live level: `calibration.fit_dpw_flat_usd` is 16,856,777 (the
  series moved off VAL_1's $17,143,641 at the fWAR epoch's step T, 94ec6875), so
  `calibration_level_scale()` is 1.0 and the served map IS the refit knots
  (`isotonic-real-v3-todaypriced-2026-10-09`). The function stays so a future level
  change bridges again until its own refit;
- the calibration block carries the refit's stamp: `fit_date`, `fit_entry_point`,
  `fit_rows` (this task), beside `version`, `fit_dpw_flat_usd` and `fit_provenance`.

The held-out bias and slope in the registry are NOT re-measured: that needs the backtest
`docs/PROSPECT_ANCHOR_GATE.md` bans before its look. The registry row (`prospect_surplus`,
its `remeasure_pending` and `notes`) carries the label "measured at $11.74M before the
refit; not re-measured until docs/PROSPECT_ANCHOR_GATE.md's look"; the row's served
summary and the glossary entries `value_framework`, `surplus_value` and `dpw_tier` carry
its served form, "measured at $11.74M before the refit; not re-measured until the Prospect
Anchor look", because the served copy rules (docs/COPY_STYLE.md L8) keep file paths out
of served text. The Anchor gate's `m_C` clause (section 5.4)
concerns the step J anchor table (FV to WAR), which the dollar map does not touch, so no
amendment is triggered.

## Bridge against refit on the same inputs (the map alone)

Measured on the served board of 2026-10-09 with the arbitration swap held fixed: the raw
input of every row was recovered by inverting the served map (strictly increasing knots;
3,698 rows served at the floor are bridged at the floor's bound) and the v6 bridge was
re-applied at s = 16,856,777 / 11,740,000 = 1.4358.

| raw $M | bridge $M | refit $M | refit minus bridge |
|---|---|---|---|
| 1 | 0.96 | 1.45 | +0.49 |
| 5 | 7.95 | 12.47 | +4.52 |
| 10 | 17.45 | 22.83 | +5.39 |
| 30 | 54.07 | 61.35 | +7.28 |
| 50 | 79.71 | 80.99 | +1.28 |
| 100 | 143.80 | 130.07 | -13.73 |
| 150 | 207.89 | 179.14 | -28.74 |

- eFV surplus, active rows (4,691): 16,665.6 -> 17,061.2 $M (+395.6, +2.4 percent); hitters
  10,067.4 -> 10,562.1, pitchers 6,598.2 -> 6,499.1. Max abs move 17.75, mean abs move 0.79,
  mean move +0.08; 1,736 rows up, 2,552 down, 403 flat within 0.05.
- Top movers up: Joseph Dzierwa and Travis Sykora 52.7 -> 60.3, Vahn Lackey 53.0 -> 60.5,
  Parks Harber 52.6 -> 60.1 (FV 50-55 regulars, about +7.5 each). Top movers down: Caden
  Bodine 160.9 -> 143.2, Franklin Arias 131.4 -> 120.6, Seth Hernandez 119.2 -> 111.2,
  Demetrio Crisantes 114.3 -> 107.5, Ryan Sloan 111.7 -> 105.5.
- Debuted rows: hitters 37,182.9 -> 38,496.5, pitchers 21,618.7 -> 24,123.5 (the remaining
  path prices through the same map).
- Org active net surplus (the Club Ledger farm leg's input): 14,649.1 -> 15,044.8. Largest
  org moves BAL +69.5, MIA +55.2, SFG +43.2, LAD +38.0, MIL +37.8, SDP -38.8, CHC -15.8,
  SEA -11.1. By net surplus alone 15 orgs change order (BAL 2 -> 1, TBR 1 -> 2, ATH 12 -> 15,
  COL 23 -> 21, among them).
- Farm letters: the letters that moved in the change the refit shipped in (BAL and MIL
  A -> A+, ATL C+ -> B-, ATH B- -> C+, SDP D- -> F; farm rank moves on 8 orgs) are the
  arbitration swap and the refit together, as 70a50b24 measured them. The map alone was
  not re-run through the farm composite (a rank-based letter on a 30-org composite), so a
  map-only letter split is not claimed.
- Trade Machine prospect total, /projections/ prospect surNpv and the Club Ledger
  controlled surplus moved in 70a50b24 (15,515.2 -> 17,068.6; 8,171.7 -> 8,831.3;
  26,006.6 -> 27,560.0) for the two changes together; this task moves no served number.

## Pins

`test_calibration_refit_live_level.py`: the knots are fit at the live level (the series,
the engine flat and `fit_dpw_flat_usd` agree, scale 1.0, stamp level); the served map
equals interpolation on the refit knots and differs from the bridge; the stamp carries the
date, the entry point and the rows; the training years are disjoint from the reserved
frames; the tool stamps the entry point and rows; the registry and the three glossary
entries carry the remeasure label. `test_backtest_knots_entry.py` (the no-FV-tier proof)
stays green.
