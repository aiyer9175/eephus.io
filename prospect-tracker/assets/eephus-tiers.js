/* =============================================================================
   eephus.io - the value ruler
   -----------------------------------------------------------------------------
   Seven colour steps that rank a number against its OWN metric: elite, great,
   good, above, avg, below, and poor, which is reserved for values under zero.
   The colours are shared site-wide; the CUTS belong to the metric, and this file
   is the only place in the repo they are allowed to exist.

   What the ruler promises, precisely: one vocabulary of seven steps, each metric
   ranked against itself, and a cell of a given colour is always at least as good
   as a cell of a dimmer colour IN ITS OWN COLUMN, wherever that column is drawn
   by ONE ladder on the number it prints. It does NOT promise that the same word
   means the same rarity across families - measured 2026-09-16, `great` is 1.6%
   of pooled projection season cells and 8.3% of qualified WAR/PA+.

   ONE RECORDED EXCEPTION to the in-column reading: the /projections/ 5y total is
   ranked on the per-season AVERAGE of the seasons it paints (owner decision A2,
   section 3.2 of the spec), while the cell prints the SUM. A row with a short
   in-window span can therefore print a smaller total in a brighter step than a
   row with five seasons, and the column is not monotone in its own printed
   number. That is the decision, not a defect: the total is a rate read on a
   window that differs row to row, and banding the sum instead would rank a
   2029-ETA prospect's two seasons against a veteran's five. It is disclosed in
   the cell's own tooltip and in the glossary entry.

   HOUSE RULES BAKED IN
     - Locked cuts keep their boundary AND the tier name they carry today:
       93 / 107 / 120 on the 100+10z family, 88 / 112 / 130 on HEM+,
       85 / 120 / 145 on published wRC+. Each of today's bands SPLITS in two; no
       value crosses a current boundary. One recorded exception: the `run` family
       adds 140 ABOVE today's top cut, so a REM+ of 125 reads `great` rather than
       `elite` (both bold teal, 120 still a boundary, and the reliever board runs
       to REM+ 200 so it needs the extra step).
     - Red (`poor`) means BELOW ZERO and nothing else. A family declares
       `neg: true` only when its value can genuinely go negative, and its last
       positive cut then sits at or above zero. Index families run six tiers and
       can never reach `poor`.
     - A cell is tiered on the number it PRINTS. Every ladder carries the `round`
       function its display formatter uses, and `tier()` rounds before it
       compares, so a cell reading "4.0" is never painted below the 4 cut.
       Measured: 37 of the 500 default-view /projections/ season cells, 219 of
       the 7,709 pooled, disagree between raw and printed on the war ladder.

   CUT TABLE PROVENANCE (all shares measured 2026-09-16 on the served artifacts,
   tiering the DISPLAYED value; pools named per row)
     war        6/4/3/2.5/1.5   default view (500 cells) 2.8/24.2/38.6/21.6/11.8/1.0/0.0
                                #src=prospect (492)      0/0/1.0/6.7/69.5/22.8
                                whole pool (7,709)       0.2/1.6/3.1/2.8/12.3/80.0/0.1
     rosterWar  40/35/32/29/26  30 clubs 10.0/3.3/36.7/16.7/23.3/10.0
     z          120/113/107/100/93   war_pa_plus qualified (351) 1.1/8.3/23.1/34.5/23.9/9.1
     run        140/120/107/100/93   rem_plus qualified (261) 1.9/8.0/14.2/22.2/25.7/28.0
     ratio      130/120/112/100/88   hem_plus qualified (351) 4.3/6.6/8.3/27.9/28.2/24.8
     wrc        145/130/120/100/85   wrc_plus qualified (351) 2.6/8.5/9.7/30.8/25.6/22.8
     woba       .400/.370/.340/.320/.300   projections default view (325) 1.2/4.0/18.8/26.8/34.2/15.1
     fip        3.00/3.50/3.90/4.30/4.80   projections default view (85) 17.6/44.7/31.8/5.9/0/0
     surplus    100/50/20/5/1   default view (99) 23.2/31.3/6.1/3.0/35.4/1.0/0
     trade      100/40/15/8/3   trade_values.json (6,426) 0.4/1.2/3.0/2.7/5.0/83.1/4.7

   SERVED CONSTANTS THIS FILE MUST STAY A SUPERSET OF (pinned by
   test_value_ruler.py::test_the_served_constants_are_a_subset)
     hitter_export.WRC_PLUS_BANDS        85 / 120 / 145   -> `wrc`
     dem_plus.DEM_ELITE/ABOVE/AVG        120 / 107 / 93   -> `z`
     bayes_trade_value._trade_value_grade cuts            -> `trade`

   No served number moves because of this file: it colours, it never computes.
   ========================================================================== */
(function () {
  "use strict";

  // Best first. The class names, the token names and the glossary entry all use
  // these seven words and nothing else.
  var TIERS = ["elite", "great", "good", "above", "avg", "below", "poor"];

  // Display rounding, one per ladder, matching the formatter that prints the
  // cell. `war` mirrors fmtWar (one decimal), the index families mirror fInt
  // (Math.round), money mirrors the one-decimal $M strings.
  function r1(v) { return Number(v.toFixed(1)); }
  function r2(v) { return Number(v.toFixed(2)); }
  function r3(v) { return Number(v.toFixed(3)); }

  // dir "hi": bigger is better, cuts strictly DECREASING.
  // dir "lo": smaller is better, cuts strictly INCREASING.
  // neg true: values under zero take `poor`; the ladder's last cut is >= 0.
  var LADDERS = {
    war:       { cuts: [6, 4, 3, 2.5, 1.5],            dir: "hi", neg: true,  round: r1 },
    rosterWar: { cuts: [40, 35, 32, 29, 26],           dir: "hi", neg: false, round: r1 },
    z:         { cuts: [120, 113, 107, 100, 93],       dir: "hi", neg: false, round: Math.round },
    run:       { cuts: [140, 120, 107, 100, 93],       dir: "hi", neg: false, round: Math.round },
    ratio:     { cuts: [130, 120, 112, 100, 88],       dir: "hi", neg: false, round: Math.round },
    wrc:       { cuts: [145, 130, 120, 100, 85],       dir: "hi", neg: false, round: Math.round },
    woba:      { cuts: [0.400, 0.370, 0.340, 0.320, 0.300], dir: "hi", neg: false, round: r3 },
    fip:       { cuts: [3.00, 3.50, 3.90, 4.30, 4.80], dir: "lo", neg: false, round: r2 },
    surplus:   { cuts: [100, 50, 20, 5, 1],            dir: "hi", neg: true,  round: r1 },
    trade:     { cuts: [100, 40, 15, 8, 3],            dir: "hi", neg: true,  round: r1 }
  };

  // "good" | "" - the empty string for a missing or non-finite value, so a call
  // site can concatenate it without emitting a stray class.
  function tier(v, fam) {
    var L = LADDERS[fam];
    if (!L) return "";
    if (v == null || v === "") return "";
    var n = Number(v);
    if (!isFinite(n)) return "";
    n = L.round(n);
    if (L.neg && n < 0) return "poor";
    for (var i = 0; i < L.cuts.length; i++) {
      if (L.dir === "lo" ? n <= L.cuts[i] : n >= L.cuts[i]) return TIERS[i];
    }
    return "below";
  }

  // Colour AND weight. The `vt` base class is the weight channel's opt-in, so
  // only call sites whose element does not own its own weight use this one.
  function cls(v, fam) {
    var t = tier(v, fam);
    return t ? "vt vt-fam-" + fam + " vt-" + t : "";
  }

  // Colour only. Display type that already sets a weight (the card tiles at 800,
  // the lens at 800, the Upside strip at 700, the dot-ruler value at 700) takes
  // this one, so the ruler never fights the rule that was there first. The 5y
  // total takes clsAvgInk below, which is this function on the average.
  function clsInk(v, fam) {
    var t = tier(v, fam);
    return t ? "vt-fam-" + fam + " vt-" + t : "";
  }

  // A multi-season total is tiered on its PAINTED per-season average, not on
  // total / horizon: `warShown` gives a prospect the in-window sum only, and 69
  // of 183 prospects have fewer than five in-window seasons.
  function clsAvg(total, n, fam) {
    if (total == null || !(n >= 1)) return "";
    return cls(Number(total) / n, fam);
  }

  // The same average, colour only. The 5y total sits under
  // `.proj-app .proj-board-table .proj-tot`, which owns its 700 weight at
  // specificity 0,3,0; emitting the `vt` base class there would put a 400 rule
  // one specificity step away from flattening it. The weight channel is opt-in,
  // so the total opts out, exactly as the card tiles and the Upside strip do.
  function clsAvgInk(total, n, fam) {
    if (total == null || !(n >= 1)) return "";
    return clsInk(Number(total) / n, fam);
  }

  // For the handful of call sites that colour through an inline style= (the
  // Trade Machine board and evaluator).
  function varOf(v, fam) {
    var t = tier(v, fam);
    return t ? "var(--vt-" + t + ")" : "";
  }

  var API = { TIERS: TIERS, LADDERS: LADDERS, tier: tier, cls: cls,
              clsInk: clsInk, clsAvg: clsAvg, clsAvgInk: clsAvgInk,
              varOf: varOf };
  if (typeof window !== "undefined") window.EephusTiers = API;
  if (typeof globalThis !== "undefined") globalThis.EephusTiers = API;
})();
