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
     war        6/4/3/2.5/1.5   default view (500 cells, 2026-09-18b)
                                                         0.6/8.0/19.6/16.4/41.8/13.6/0.0
                                vet 5y total / 5 (1,383) 0.1/0.4/1.0/1.4/5.9/91.3/0.0
                                (the 2026-09-16 reading of the default view,
                                2.8/24.2/38.6/21.6/11.8/1.0/0.0, was taken while the
                                board printed the IF-HEALTHY path and is superseded.
                                The CUTS did not move; the pool under them did.)
     warProspect 1.7/0.9/0.7/0.6/0.4
                                #src=prospect PAINTED season cells
                                (672, 2026-10-01) 0.4/8.0/16.2/18.5/37.6/19.2
                                the same rows' 5y totals / seasons painted
                                (178)              0.6/6.7/12.9/19.7/42.1/18.0
                                (was 1.5/0.9/0.7/0.6/0.4, fitted 2026-09-18b on 813
                                cells: 0.4/8.1/16.2/18.1/36.4/20.8)
       RECOMPUTED 2026-10-01 (owner answer M26-2) on that day's nightly
       projections file (first season 2027) by the SAME recipe below,
       no new method: only the elite cut moves, 1.5 to 1.7, which repaints 2 of
       672 prospect season cells (2 of 178 prospects) from elite to great and no
       5y total. On the drifted 2026-09-24 payload the old cuts had fallen out of
       test_value_ruler's 10-point band. THEY RECOMPUTE AGAIN, by the same
       recipe, on the first nightly projections file written after the fWAR
       label epoch's step Z (dated line in docs/efv-2026-09-03/WAR_BASIS_RUNBOOK.md).
       WHY A SECOND WAR LADDER, and why it is not a softer one. On 2026-09-18
       the projections board stopped showing the if-healthy path and went to the
       expected value, which is the path surplus has always priced. A prospect
       expected path is bucket-weighted by P(bucket|FV), so it already carries
       the bust probability: the whole prospect pool then lands between 0.07 and
       1.69 WAR a season, median 0.50, and 99.6 percent of it sits under the war
       ladder's bottom cut of 1.5. One colour is not a ruler.

       THE CUTS ARE FITTED, NOT CHOSEN. They are the 0.1-grid cut vector that
       minimizes the L1 distance between its CUMULATIVE tier shares and the war
       ladder's own cumulative shares on the default view, so a prospect cell and
       a veteran cell painted one colour occupy the same RANK in their own
       population, which is the only claim a colour on this board makes. The
       reference, re-measured 2026-10-01 on the SERVED board (500 default-view
       cells), is 0.4/8.2/19.0/15.8/44.8/11.8/0.0. The fit is bounded by tie mass
       -- 672 cells over 17 distinct printed values -- so `good` lands 2.8
       points light, `avg` 7.2 light and `below` 7.4 heavy; no 0.1-grid vector
       does better (cumulative L1 10.70, against 10.85 for an elite cut of 1.6
       and 11.00 for the old 1.5).

       WHY THE OLD CUTS (1.1/0.65/0.45/0.30/0.15) ARE RETIRED. They were pinned
       to the war ladder's shares as measured on 2026-09-16, 2.8/24.2/38.6/
       21.6/11.8/1.0, which was the IF-HEALTHY display, one commit before the
       revert. That distribution no longer exists, so the percentile match they
       claimed was to a pool that had already gone: under them the prospect pool
       ran 4.4/20.3/34.9/34.6/4.9/0.9, three times the war ladder's `elite` share
       and a third of its `below`. They also stated two-decimal boundaries under a
       one-decimal `round`, so 0.65 really cut at 0.7 and 0.15 really cut at 0.2:
       the printed cut table did not mean what it said. Every cut here is on the
       0.1 grid the war formatter prints.

       AND WHY THERE IS NO THIRD LADDER FOR THE PRIME PATH. A prospect row also
       publishes a prime-anchored total (talent, same bucket weights, higher
       anchor). It is printed as labelled TEXT under the expected value, never as
       a coloured cell, so it needs no cuts. A ladder nothing paints would be a
       set of numbers in this file with no column to answer for them.
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
    // Recomputed 2026-10-01; recompute again on the first nightly projections
    // file after the fWAR epoch's step Z (see CUT TABLE PROVENANCE above).
    warProspect: { cuts: [1.7, 0.9, 0.7, 0.6, 0.4],    dir: "hi", neg: true,  round: r1 },
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

  // ---- the percentile gradient (owner ask 2026-10-01) -----------------------
  // A Savant percentile is already a rank, so it takes no cut ladder and no
  // tier word: it walks the seven ruler colours CONTINUOUSLY. The stops are the
  // ruler tokens at these percentiles; between two stops the colour is a
  // color-mix in OKLAB of its two neighbours, returned as a CSS expression, so
  // it resolves through the tokens of whichever theme is active and needs no
  // JS colour math and no recompute on a theme toggle. OKLAB, not OKLCH: two
  // stops (avg, below) are near-neutral, and an OKLCH hue arc from a grey to a
  // colour detours through unrelated hues. Measured 2026-10-01 in Chromium,
  // OKLCH painted p = 50 light rgb(0,106,116), the teal of the p = 90 stop
  // rgb(12,110,120), and p = 30 dark a pink grey between two blue greys; OKLAB
  // gives rgb(59,104,85) and rgb(160,165,176), with the same lightness.
  // Red at the bottom is the Savant convention for a bottom percentile; it does
  // not break the "poor is below zero" rule above, which is about tier WORDS on
  // value ladders, and no tier class is emitted from here.
  var PCT_STOPS = [[0, "poor"], [20, "below"], [40, "avg"], [60, "above"],
                   [80, "good"], [90, "great"], [100, "elite"]];

  function pctNum(p) {
    if (p == null || p === "") return null;
    var n = Number(p);
    if (!isFinite(n)) return null;
    return Math.min(100, Math.max(0, n));
  }

  // Index of the segment [stop i, stop i+1] that p falls in. An exact stop
  // opens its own segment; 100 closes the last one. -1 for a missing value.
  function pctSeg(p) {
    var n = pctNum(p);
    if (n == null) return -1;
    for (var i = PCT_STOPS.length - 2; i > 0; i--) {
      if (n >= PCT_STOPS[i][0]) return i;
    }
    return 0;
  }

  // "var(--vt-avg)" at a stop, "color-mix(in oklab, var(--vt-avg) 50%,
  // var(--vt-above))" between two (the percentage is the LOWER stop's share,
  // to one decimal), "" for a missing value.
  function pctColor(p) {
    var n = pctNum(p);
    if (n == null) return "";
    var i = pctSeg(n), a = PCT_STOPS[i], b = PCT_STOPS[i + 1];
    var w = Math.round((b[0] - n) / (b[0] - a[0]) * 1000) / 10;
    if (w >= 100) return "var(--vt-" + a[1] + ")";
    if (w <= 0) return "var(--vt-" + b[1] + ")";
    return "color-mix(in oklab, var(--vt-" + a[1] + ") " + w + "%, var(--vt-" + b[1] + "))";
  }

  var API = { TIERS: TIERS, LADDERS: LADDERS, tier: tier, cls: cls,
              clsInk: clsInk, clsAvg: clsAvg, clsAvgInk: clsAvgInk,
              varOf: varOf, PCT_STOPS: PCT_STOPS, pctSeg: pctSeg,
              pctColor: pctColor };
  if (typeof window !== "undefined") window.EephusTiers = API;
  if (typeof globalThis !== "undefined") globalThis.EephusTiers = API;
})();
