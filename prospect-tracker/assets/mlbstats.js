/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - MLB Stats module: Bullpen Leaderboards
// =============================================================================
// Renders data/bullpen_leaderboards.json (bullpen_export.py) into three views:
//   - Relievers:    individual REM+ leaderboard + the leverage/Impact columns
//   - Team Bullpens: team Bullpen+ (relief-IP-weighted) + a leverage-deploy read
//   - Depth Charts:  each pen's gmLI leverage ladder, REM+ per slot
//
// REM+ is a ratio-to-league rate index (100 = average reliever, 110 = 10%
// better). The headline number is pure-skill (FIP-based, sample-shrunk); the
// leverage context (gmLI / WPA / WPA-LI / SD-MD) rides separate Impact columns
// so role assignment never moves the talent number (the two-number design).
//
// Five sections share this file: Bullpen (above), Starters (section 2),
// Hitters (3), Leverage (4) and Defense (5, DEM+ from defense_export.py).
(function () {
  "use strict";

  var DATA_URL = "/data/bullpen_leaderboards.json";
  var ROLE_ORDER = ["Closer", "High-leverage", "Setup", "Middle", "Long", "Mop-up"];

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  // The pixel state box (assets/eephus-state.js, final-pass plan 5.7 PX-12):
  // loading, empty, unmeasured or failed, around a message this file escapes.
  // The bare box is the fallback for a test harness that loads this file alone.
  function pxState(kind, msg, opts) {
    var S = typeof window !== "undefined" && window.EephusState;
    if (S) return S.html(kind, msg, opts);
    var cls = typeof opts === "string" ? opts : (opts && opts.cls) || "";
    return '<div class="px-state is-' + kind + (cls ? " " + cls : "") + '"' +
      (kind === "failed" ? ' role="alert"' : "") + '><div class="px-state-msg">' + msg + "</div></div>";
  }
  function num(v, d) { return (v == null || isNaN(v)) ? null : Number(v); }
  // The site's null marker. fa.js and projections.js both render an absent
  // value as this; mlbstats rendered an EMPTY CELL, so a missing number and a
  // rendering bug looked identical on the only surface where whole columns
  // are legitimately absent for unqualified players. Named EM_DASH to match
  // fa.js, and like fa.js it is a spaced hyphen: real em-dashes are banned in
  // user-facing copy and tools/strip_emdashes.py lints assets/*.js.
  var EM_DASH = " - ";

  // Mirror of PROSPX's formatMetric for the types this surface renders -
  // same precision rules, same null token, same -0 collapse. Kept local so
  // the MLB Stats page never imports the 2.4MB PROSPX script.
  function formatMetric(value, type = "int") {
    const n = Number(value);
    if (value == null || value === "" || !Number.isFinite(n)) return EM_DASH;
    const z = n === 0 ? 0 : n;                       // collapse -0 -> 0
    const sign = z > 0 ? "+" : (z < 0 ? "-" : "");   // zero is unsigned
    const abs = Math.abs(z);
    // A value that ROUNDS to zero at the printed precision is zero and prints
    // unsigned. toFixed keeps the sign of a tiny negative, so -0.01 at one
    // decimal printed "-0.0" (218 board cells on /projections/, 2026-10-02), and
    // the signed types put a "+" or "-" on a printed 0.00. Both helpers read
    // the ROUNDED figure, never z itself.
    const fixed = (x, d) => (Number(x.toFixed(d)) === 0 ? (0).toFixed(d) : x.toFixed(d));
    const signAt = d => (Number(abs.toFixed(d)) === 0 ? "" : sign);
    switch (type) {
      case "int":      return String(Math.round(z));
      case "war":      return fixed(z, 1);
      case "rate":     return signAt(2) + abs.toFixed(2);
      case "surplusM": return signAt(1) + "$" + abs.toFixed(1) + "M";
      // MINUS but never PLUS. Dropping the sign entirely was harmless for the
      // guarantees and AAVs this surface passes it (all positive) but rendered
      // a NEGATIVE dollar figure as a positive one, and /projections/ prices
      // surplus through this same type, where negatives are now common
      // (rest-of-season control pricing, 2026-08-03). A liability shown as an
      // asset is the worst possible rounding of that number. The leading "+"
      // that `sign` would add belongs to surplusM, where the direction is the
      // point; on a contract guarantee it is noise.
      case "moneyM":   return (z < 0 && signAt(1) ? "-" : "") + "$"
                            + (abs >= 100 ? abs.toFixed(0) : abs.toFixed(1)) + "M";
      case "pct":      return fixed(z, 1) + "%";
      default:         return String(z);
    }
  }
  // ^ CHARACTER-IDENTICAL to the copies in assets/fa.js and
  // assets/projections.js, including the comments and the FA-specific docstring
  // above it: test_number_format_parity.py compares the extracted text, so a
  // "tidied" copy is a failing copy. This surface was outside that contract
  // entirely until 2026-08-03 - it carried its own EM_DASH and six one-off
  // formatters, two of which rendered an absent number as a bare "-" while
  // every other board on the site rendered " - ". Extending the test's MIRRORS
  // list to cover this file is a follow-up for the orchestrator; until then
  // this copy is pinned by review only.
  //
  // The board formatters below ROUTE through the mirror wherever the type
  // exists, and where it does not they at least share its null token. What
  // stays local is stated, not left to be rediscovered:
  //   f2  - ERA / FIP / gmLI want two decimals and NEVER a sign. The mirror's
  //         "rate" type is signed, which would print a 3.45 ERA as "+3.45".
  //   f3  - the baseball slash convention (.300, leading zero dropped) has no
  //         type in the contract; OPS over 1 keeps its leading digit.
  //   fSigned - one decimal, signed. "rate" is two decimals.
  function fInt(v) { return formatMetric(v, "int"); }
  function f1(v) { return formatMetric(v, "war"); }
  function f2(v) { var n = num(v); return n == null ? EM_DASH : n.toFixed(2); }
  // 3-decimal baseball slash formatter: .300 (drops the leading zero; OPS>1 keeps it).
  function f3(v) { var n = num(v); return n == null ? EM_DASH : n.toFixed(3).replace(/^0\./, "."); }
  // The payload carries rates as fractions and the contract's "pct" type
  // formats an already-scaled percentage, so scale first, then hand it over.
  function fPct(v) { var n = num(v); return n == null ? EM_DASH : formatMetric(n * 100, "pct"); }
  function fSigned(v) { var n = num(v); if (n == null) return EM_DASH; return (n > 0 ? "+" : "") + n.toFixed(1); }
  // Signed whole numbers: Savant serves blocking runs and blocks above average as integers.
  function fSignedInt(v) { var n = num(v); if (n == null) return EM_DASH; return (n > 0 ? "+" : "") + Math.round(n); }
  function logo(team) {
    try { return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo) ? EEPHUS_HUB.teamLogo(team) : ""; }
    catch (e) { return ""; }
  }
  // The hub charts draw on a viewBox (640 units wide unless told) that the SVG
  // scales to its cell, so a 9-unit label in the 306px cell of a 390px phone
  // drew 5px tall (9px at 1280). Every chart here gets a viewBox as wide as
  // its cell is in pixels, read off the .mlbx root when it renders: site.css
  // lays .mlbstats-viz out in one column at 820px and below and two with a
  // 16px gap above, inside a collapse body padded 12px a side and cells padded
  // 12px a side, each boxed by a 1px border. Capped at the old 640, so a wide
  // cell keeps the old box; no layout (the py_mini_racer smoke test) keeps the default.
  var VIZ_MAX_W = 640, VIZ_MIN_W = 200;
  function vizWidth() {
    try {
      var host = document.querySelector(".mlbx");
      var w = host ? host.clientWidth : 0;
      if (!w) return null;
      var one = window.matchMedia ? window.matchMedia("(max-width: 820px)").matches : w <= 772;
      var cell = one ? w - 52 : (w - 42) / 2 - 26;
      return Math.max(VIZ_MIN_W, Math.min(VIZ_MAX_W, Math.round(cell)));
    } catch (e) { return null; }
  }
  function chart(fn, arg, opts) {
    try {
      var o = opts || {};
      if (o.width == null) { var vw = vizWidth(); if (vw) o.width = vw; }
      return (window.EEPHUS_HUB && EEPHUS_HUB[fn]) ? EEPHUS_HUB[fn](arg, o) : "";
    }
    catch (e) { return ""; }
  }
  function relieverViz() {
    var qual = ((DATA && DATA.relievers) || []).filter(function (r) { return r.qualified !== false; });
    if (qual.length < 12) return "";
    var rems = qual.map(function (r) { return r.rem_plus; });
    var hist = chart("histogram", rems, { height: 108, min: 55, max: 175, highlightAbove: 120,
      refs: [{ at: 100, label: "avg" }], aria: "REM+ distribution" });
    var pts = qual.filter(function (r) { return r.gmli != null; }).map(function (r) {
      return { x: r.rem_plus, y: r.gmli, label: r.name + "  REM+ " + fInt(r.rem_plus) + "  gmLI " + f2(r.gmli),
               color: r.rem_plus >= 115 ? null : "var(--text-tertiary)" };
    });
    var sc = chart("scatter", pts, { height: 250, xLabel: "REM+ (skill) →", yLabel: "↑ gmLI (leverage)",
      xRef: 100, yRef: 1, aria: "skill vs leverage" });
    // Earned vs deserved: REM+ (FIP-based results) against xREM+ (xwOBA-
    // allowed). Below the diagonal = results ahead of contact quality
    // (regression candidates); above = deserving better. Mirrors the starter
    // SEM+ x xSEM+ chart; the read matters MORE for relievers, whose small
    // samples make FIP-vs-contact-quality gaps larger.
    var xpts = qual.filter(function (r) { return r.xrem_plus != null; }).map(function (r) {
      return { x: r.rem_plus, y: r.xrem_plus,
               label: r.name + "  REM+ " + fInt(r.rem_plus) + "  xREM+ " + fInt(r.xrem_plus),
               color: r.rem_plus >= 115 ? null : "var(--text-tertiary)" };
    });
    var xsc = xpts.length >= 12
      ? chart("scatter", xpts, { height: 250, xLabel: "REM+ (results) →",
          yLabel: "↑ xREM+ (deserved)", xRef: 100, yRef: 100, diag: true, aria: "earned vs deserved" })
      : "";
    if (!hist && !sc && !xsc) return "";
    // Captions are legends: the pool, the highlight cut and how to read the
    // diagonal, each read off the chart options above.
    var body = '<div class="mlbstats-viz">'
      + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">' + gloss("REM+", "rem_plus")
      + ' distribution <span class="proj-dim">(qualified; cyan = 120+)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">REM+ vs ' + gloss("gmLI", "gmli")
        + ' <span class="proj-dim">(bright = REM+ 115+)</span></div>' + sc + "</div>" : "")
      + (xsc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">REM+ vs ' + gloss("xREM+", "xrem_plus")
        + ' <span class="proj-dim">(below the diagonal = FIP results ahead of contact quality)</span></div>' + xsc + "</div>" : "")
      + "</div>";
    return collapsible("relievers-viz", 'Charts <span class="proj-dim">(REM+ distribution, vs gmLI, vs xREM+)</span>', body);
  }

  // ---- index colouring: the value ruler ------------------------------------
  // Every cut is in assets/eephus-tiers.js, and each of these columns names the
  // FAMILY it belongs to rather than carrying a threshold:
  //   z     100 + 10z          WAR/PA+, WAR/IP+, DEM+, Team DEM+, Bullpen+,
  //                            Rotation+, Lev Deploy+, Hi-Lev Core
  //   run   FIP-based run prevention, which runs much wider (REM+ to 200 on the
  //         served artifact, SEM+ to 164): REM+, SEM+, RIV+, xREM+, xSEM+, Front 3
  //   ratio HEM+ family at wRC+ width: HEM+, xHEM+, xHEM+ Blend, Offense+, Heart 3
  //   wrc   the industry's PUBLISHED wRC+, and nothing else
  // The raw eWAR columns on these boards carry NO family and stay uncoloured:
  // the eWAR section's Player and Team boards, the per-board eWAR column and
  // the team_war rollup. They are counting totals, and the only WAR ladders the
  // ruler owns were cut on /projections/ pools: `war` on PROJECTED seasons, which
  // are regressed and narrower than played ones, and `rosterWar` on the 30
  // projected club totals. Painting a season-to-date eWAR on either would borrow
  // a ladder from a pool it was never measured on, which is the one thing the
  // cut table forbids. They get a family when someone measures their own pool,
  // and test_value_ruler.py::test_raw_ewar_columns_carry_no_ladder holds that
  // line until then.
  // The locked cuts keep their boundary and their tier name: 93 / 107 / 120 on z,
  // 88 / 112 / 130 on ratio, 85 / 120 / 145 on wrc. Each band splits in two, so
  // no value crosses a boundary it was on the other side of yesterday. The one
  // recorded exception is `run`, which adds 140 above 120 so the reliever board
  // can separate a 200 from a 121; 120 is still a boundary and both are bold teal.
  function vtCell(v, fam, glossaryTerm) {
    var g = glossaryTerm ? ' data-gl="' + glossaryTerm + '"' : "";
    return '<span class="rem-plus ' + EephusTiers.cls(v, fam) + '"' + g + '>' + fInt(v) + "</span>";
  }
  function remCell(v, glossaryTerm) { return vtCell(v, "z", glossaryTerm); }
  function runCell(v, glossaryTerm) { return vtCell(v, "run", glossaryTerm); }
  function hemCell(v, glossaryTerm) { return vtCell(v, "ratio", glossaryTerm); }
  // PUBLISHED wRC+ gets its OWN ladder, and that is deliberate. It is the
  // industry's number, not one of ours, and it is unshrunk, so it runs wider
  // than the HEM+ family beside it: measured over the pooled 2021-2026
  // qualified pools (n = 2,069), published wRC+ has SD 25.3 against HEM+ 17.7.
  // Painting it on the ratio ladder 88/112/130 would call 12.4% of qualified
  // hitters elite where HEM+ calls 4.9%. The locked breaks are the round-5 triple
  // that best reproduces the HEM+ band shares on the wRC+ distribution
  // (85/120/145: shares 26.0 / 52.1 / 17.9 / 4.1 vs the HEM+ reference 26.5 /
  // 50.9 / 17.6 / 4.9). SINGLE SOURCE OF TRUTH: hitter_export.WRC_PLUS_BANDS,
  // of which the `wrc` ladder's cuts are a superset; test_value_ruler.py fails if
  // they drift apart.
  function wrcCell(v) { return vtCell(v, "wrc", "wrc_plus"); }
  function gloss(label, term) {
    return '<span class="g-term" data-gl="' + esc(term) + '">' + esc(label) + "</span>";
  }
  // Header tooltip for the served `fip` field on both pitcher boards. One
  // sentence builder so the reliever and starter wording cannot drift apart:
  // only the pool and the index it feeds differ. No served number is typed
  // here; the column's own cells carry the values.
  function skillFipTitle(pool, index) {
    return "The sample-shrunk FIP " + index + " is built on: K, BB, HBP and HR rates pulled toward"
      + " the " + pool + " pool by sample size, constant solved on " + pool + "s; not the standard FIP.";
  }
  // Header tooltip for the Savant custom-leaderboard display columns
  // (savant_leaderboards.py). Each sentence names its denominator; none of the
  // columns feeds a score.
  function savantTitle(sentence) {
    return sentence + " From the Baseball Savant custom leaderboard. Display only: no score on this board reads it.";
  }
  function wireGlossary(el) {
    try { if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(el); } catch (e) { /* glossary optional */ }
    mountPagers(el);
    // One measure per frame, after the write (QMLP05): markFit reads
    // offsetWidth, and reading it straight after an innerHTML swap forced a
    // synchronous style and layout of the whole board on every render.
    scheduleFit(el);
    linksSoon();
    // Every board render replaces its section root's innerHTML, and the
    // Download CSV bar is that root's FIRST CHILD, so a sort, a search, a
    // filter or a view click deleted it. eephus-csv.js puts it back off a
    // 250ms-debounced observer: measured, the control was gone for 0.5 to
    // 1.5s after every interaction, and on a phone, where the bar owns its
    // own row, the board jumped up and back with it. Re-scan here, where
    // every render path already lands. ensureControl is idempotent (an
    // existing bar is reused, never duplicated) and the pass also refreshes
    // the row count the bar prints, which used to trail the filter by the
    // same debounce.
    try { if (window.EephusCSV && EephusCSV.scan) EephusCSV.scan(document); } catch (e) { /* export control optional */ }
    csvTitles(el);
  }
  // A board whose table fits its scroller gets .is-fit, and site.css then clips
  // instead of scrolling: no scroll container, so the header sticks to the
  // viewport and the page is the only scroll. Measured, never assumed: a view
  // that does not fit (a tablet, the All view) keeps the scroller and the
  // frozen name column. No layout in the smoke harness, so it is a no-op there.
  function markFit(el) {
    try {
      (el || document).querySelectorAll(".mlbstats-scroll").forEach(function (sc) {
        var t = sc.querySelector(".mlbstats-table");
        if (!t || !sc.classList) return;
        sc.classList.toggle("is-fit", t.offsetWidth > 0 && t.offsetWidth <= sc.clientWidth);
      });
    } catch (e) { /* layout optional */ }
  }
  var fitQueue = [], fitFrame = 0;
  function scheduleFit(el) {
    var raf = (typeof window !== "undefined") && window.requestAnimationFrame;
    if (!raf) { markFit(el); return; }
    if (fitQueue.indexOf(el) < 0) fitQueue.push(el);
    if (fitFrame) return;
    fitFrame = raf.call(window, function () {
      fitFrame = 0;
      var q = fitQueue;
      fitQueue = [];
      q.forEach(function (x) { markFit(x); });
    });
  }
  var fitTimer = null;
  try { window.addEventListener("resize", function () {
    if (fitTimer) clearTimeout(fitTimer);
    fitTimer = setTimeout(function () { markFit(document.querySelector(".mlbx")); }, 120);
  }); } catch (e) { /* no window */ }
  // A webfont that lands after the first paint re-flows every table; re-measure
  // then, so a mark taken on the fallback face never clips the real one.
  try { if (document.fonts) {
    if (document.fonts.ready) document.fonts.ready.then(function () { markFit(document.querySelector(".mlbx")); });
    if (document.fonts.addEventListener) document.fonts.addEventListener("loadingdone", function () { markFit(document.querySelector(".mlbx")); });
  } } catch (e) { /* no font loading API */ }

  // ---- phone filter drawer ----------------------------------------------------
  // At 640px and below only the search box shows until Filters is pressed
  // (site.css, .mlbx-filters); the role and position chip row after the bar
  // hides with it. One flag for every section, flipped by one delegated
  // listener, so the drawer stays open across re-renders and section
  // switches. The button carries the count of non-default filters (team, a
  // min floor, pressed chips, and the qualified gate when a reader has
  // turned it OFF), so a narrowed board never reads as the whole league
  // while the drawer is closed. The qualified box is IN the drawer and
  // defaults to on, so unchecking it (261 relievers to the whole league)
  // is the largest change a closed drawer can hide; the search box, which
  // stays visible at every width, is the one filter the count leaves out.
  // Hidden on a desktop by site.css.
  // MEASURED 2026-09-11 at 390x844: the reliever bar is 27px closed against
  // 64px open, and the board moves to y 741 while a reader has it open.
  var filtersOpen = false;
  function filtCount(team, min, chips, qualOff) {
    return (team ? 1 : 0) + (min != null ? 1 : 0) + ((chips && chips.length) || 0)
      + (qualOff ? 1 : 0);
  }
  function filtBtn(n) {
    return '<button type="button" class="chip mlbx-filtbtn" aria-expanded="' + filtersOpen + '">Filters'
      + (n ? ' <span class="proj-dim">' + n + "</span>" : "") + "</button>";
  }
  function filtCls() { return "mlbstats-bar mlbx-filters" + (filtersOpen ? " is-open" : ""); }
  try { document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest(".mlbx-filtbtn") : null;
    if (!b) return;
    filtersOpen = !filtersOpen;
    document.querySelectorAll(".mlbx-filters").forEach(function (f) { f.classList.toggle("is-open", filtersOpen); });
    document.querySelectorAll(".mlbx-filtbtn").forEach(function (x) { x.setAttribute("aria-expanded", String(filtersOpen)); });
  }); } catch (e) { /* no document events */ }

  // ---- shared filter controls -----------------------------------------------
  // Every board on this surface shipped with exactly two filters: a search box
  // and a "qualified only" checkbox. The rows already carry team, role, innings
  // and plate appearances, so these narrow client-side off what is on screen
  // and never refetch. Markup rides the existing .mlbstats-bar input/select
  // rule and the .mlbstats-season pill, so there is no second control language.
  //
  // The option list is built from the ROWS, not a static club map, so it can
  // never offer a team the active board (or the active season) has nobody on.
  // `sec` is passed so the control can say which basis it is on: on Current the
  // club is the roster today, on a window it is every club of production inside
  // it (owner decision D9). A row that carries a clubs list contributes every
  // one of them, so a club a player produced for in 2024 and nobody is on today
  // is still selectable.
  function teamSelect(id, rows, sel, sec) {
    var seen = {}, out = [];
    (rows || []).forEach(function (r) {
      var cl = (r.clubs && r.clubs.length) ? r.clubs : (r.team ? [r.team] : []);
      cl.forEach(function (t) { if (t && !seen[t]) { seen[t] = 1; out.push(t); } });
    });
    out.sort();
    var win = !!(sec && isWindow(sec));
    var opts = '<option value="">All ' + (win ? "clubs" : "teams") + "</option>" + out.map(function (t) {
      return '<option value="' + esc(t) + '"' + (t === sel ? " selected" : "") + ">" + esc(t) + "</option>";
    }).join("");
    return '<label class="mlbstats-ctl"' + (win ? ' title="' + esc("Every player who produced for this"
        + " club in any season of the window, not the roster today.") + '"' : "")
      + ">" + (win ? "club (produced for)" : "team") + ' <select id="' + id + '" data-team-picker aria-label="'
      + (win ? "Filter by club of production" : "Filter by team") + '">'
      + opts + "</select></label>";
  }
  // The rows the club select is built from: the WINDOW's rows when one is open
  // and its payload has landed, the board's own rows otherwise.
  function winSelectRows(sec, cur) {
    var w = WIN[sec];
    if (!w) return cur;
    if (sec === "war") {
      return (SEASONS && SEASONS.players) ? foldSeasons(w.lo, w.hi).players : cur;
    }
    var lw = labWindowFor(LAB_BOARD[sec], w.lo, w.hi);
    var doc = lw && WINDOW_DOC[lw.key];
    return doc ? windowRows(sec, doc) : cur;
  }
  // The CSV a window exports is named for the window. The column headers already
  // carry the span (exportLabel), so only the FILE name was still single-season;
  // a reader who downloads 2024-2026 and files it under 2026 has been told the
  // wrong thing by the one string he keeps. The base name is the shell's, read
  // once, so this can never compound over re-renders.
  var CSV_BASE = {};
  function stampCsv(sec, host) {
    if (!host || !host.getAttribute) return;
    if (CSV_BASE[sec] == null) CSV_BASE[sec] = host.getAttribute("data-csv-export") || "";
    var base = CSV_BASE[sec];
    if (!base) return;
    var w = WIN[sec];
    host.setAttribute("data-csv-export", w ? base + "-" + winSpan(w) : base);
  }
  // A numeric floor (min IP / min PA). Empty means no floor, which is not the
  // same as zero: the qualified-only checkbox is a different, coarser gate and
  // the two compose.
  function minSelect(id, label, val, title) {
    return '<label class="mlbstats-ctl"' + (title ? ' title="' + esc(title) + '"' : "") + ">" + esc(label)
      + ' <input class="mlbstats-minnum" type="number" min="0" step="1" inputmode="numeric" id="'
      + id + '" value="' + (val == null ? "" : esc(val)) + '" aria-label="' + esc(label) + '"></label>';
  }
  // "" / non-numeric reads as "no floor" rather than 0, so clearing the box
  // restores the unfiltered board instead of pinning it at zero.
  function readMin(el) {
    if (!el) return null;
    var s = String(el.value == null ? "" : el.value).trim();
    if (!s) return null;
    var n = Number(s);
    return isNaN(n) ? null : n;
  }
  function passesMin(v, min) {
    if (min == null) return true;
    var n = num(v);
    return n != null && n >= min;
  }

  // ---- the shared team filter (#team=) ---------------------------------------
  // Section 7 of the overhaul: ONE team key for the whole page. Every section
  // already had its own team select and its own module var; what a reader
  // never had was a way to LINK the club he is looking at, or to carry it from
  // one board to the next. #team=NYY sets all six vars at once, and the ACTIVE
  // section writes its own back, so a copied URL opens the club the reader was
  // on and lands it on every board he clicks from there. The selects stay per
  // section: picking a club on Hitters narrows Hitters, not five boards the
  // reader has not opened. The value is validated as a club abbreviation
  // before it is trusted, because it goes straight into a row comparison.
  //
  // Seasons deliberately stay per section: a shared season key would change
  // what #section=starters&rseason=2024 means today, and a deep link that
  // silently shows a different season is the bug this overhaul closed.
  var TEAM_HASH_RE = /(?:^#|[#&])team=([A-Z]{2,3})\b/;
  // The filter bar already names the club in its select. What it lacked is the
  // one control that undoes it in a click, which is also the control the empty
  // board needs, so both render the same chip.
  function teamFilterChip(team) {
    return team ? '<button type="button" class="chip mlbx-teamclear" title="Clear the team filter">'
      + esc(team) + ' <span class="proj-dim">Clear</span></button>' : "";
  }
  // A board narrowed to a club with nobody on it says which club, and offers
  // the way out. Without the team filter it keeps the sentence it always had.
  function noRowsNote(team, fallback) {
    return '<div class="mlbstats-empty">' + (team
      ? "No " + esc(team) + " rows on this board. "
        + '<button type="button" class="chip mlbx-teamclear">Clear</button>'
      : fallback) + "</div>";
  }
  function activeTeam() {
    return section === "starters" ? starterTeam
      : section === "hitters" ? hitterTeam
      : section === "leverage" ? leverageTeam
      : section === "defense" ? defenseTeam
      : section === "war" ? warTeam : relTeam;
  }
  function clearActiveTeam() {
    if (section === "starters") { starterTeam = ""; writeHash(); renderStartersInPlace(); }
    else if (section === "hitters") { hitterTeam = ""; writeHash(); renderHittersInPlace(); }
    else if (section === "leverage") { leverageTeam = ""; writeHash(); renderLeverageInPlace(); }
    else if (section === "defense") { defenseTeam = ""; writeHash(); renderDefenseInPlace(); }
    else if (section === "war") { warTeam = ""; writeHash(); renderWar(); }
    else { relTeam = ""; writeHash(); renderInPlace(); }
  }
  // One delegated listener, the pattern the phone drawer and the Team note
  // already use: a Clear rendered by any bar or any empty board keeps working
  // after the re-render that replaced the button the reader pressed.
  try { document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest(".mlbx-teamclear") : null;
    if (!b) return;
    clearActiveTeam();
  }); } catch (e) { /* no document events */ }

  // Role chips reuse the season-pill markup wholesale: same active state, same
  // phone swipe strip, same 44px touch target, no new CSS. Multi-select (an OR
  // set) because "Closer + High-leverage" is the question people actually ask;
  // "All" clears rather than toggling a tenth pill.
  function roleSlug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "_"); }
  function roleChips(rows, active, idPrefix) {
    var counts = {}, n = 0;
    (rows || []).forEach(function (r) { if (r.role) { counts[r.role] = (counts[r.role] || 0) + 1; n++; } });
    if (!n) return "";
    var roles = ROLE_ORDER.filter(function (x) { return counts[x]; });
    Object.keys(counts).sort().forEach(function (x) { if (roles.indexOf(x) < 0) roles.push(x); });
    var all = !active.length;
    return '<div class="mlbstats-seasons mlbstats-roles" role="group" aria-label="Filter by bullpen role">'
      + '<span class="mlbstats-roles-lbl">Role</span>'
      + '<button type="button" class="mlbstats-season' + (all ? " active" : "") + '" id="' + idPrefix
      + 'all" data-mlbrole="" aria-pressed="' + all + '">All</button>'
      + roles.map(function (x) {
          var on = active.indexOf(x) >= 0;
          return '<button type="button" class="mlbstats-season' + (on ? " active" : "") + '" id="'
            + idPrefix + roleSlug(x) + '" data-mlbrole="' + esc(x) + '" aria-pressed="' + on + '">'
            + esc(x) + '<span class="proj-dim"> ' + counts[x] + "</span></button>";
        }).join("") + "</div>";
  }

  // ---- collapsible chart panels --------------------------------------------
  // Charts default to COLLAPSED (they are context, not the leaderboard). The
  // header is the click target; open/closed state persists in localStorage so a
  // user who opens the charts keeps them open across renders and visits.
  var COLLAPSE = {};
  // `dflt` is the panel's OPENING state when the user has never toggled it.
  // Omitted means collapsed, which is what every chart panel wants and what
  // the methodology folds below ask for explicitly. A user's own choice is
  // written to localStorage by setCollapse and outranks whatever default the
  // caller asked for, on every board and every visit.
  function collapseState(id, dflt) {
    if (COLLAPSE[id] != null) return COLLAPSE[id];
    var v = (dflt == null) ? true : !!dflt;
    try {
      var s = window.localStorage.getItem("mlbstats.collapse." + id);
      if (s === "0") v = false; else if (s === "1") v = true;
    } catch (e) { /* localStorage optional */ }
    COLLAPSE[id] = v;
    return v;
  }
  function setCollapse(id, collapsed) {
    COLLAPSE[id] = collapsed;
    try { window.localStorage.setItem("mlbstats.collapse." + id, collapsed ? "1" : "0"); } catch (e) { /* optional */ }
  }
  // opts: { collapsed: <default open/closed>, cls: <extra class on the panel> }.
  // Both optional; the three-argument call shape every chart panel uses is
  // unchanged.
  function collapsible(id, title, body, opts) {
    if (!body) return "";
    var o = opts || {};
    var collapsed = collapseState(id, o.collapsed);
    return '<div class="mlbstats-collapse' + (o.cls ? " " + o.cls : "")
      + (collapsed ? " is-collapsed" : "") + '" data-collapse="' + esc(id) + '">'
      + '<button type="button" class="mlbstats-collapse-head" aria-expanded="' + (!collapsed) + '">'
      + '<span class="mlbstats-collapse-caret" aria-hidden="true"></span>' + title + "</button>"
      + '<div class="mlbstats-collapse-body">' + body + "</div></div>";
  }

  // ---- the methodology fold -------------------------------------------------
  // MEASURED 2026-08-05 at 390x844, Bullpen Leaderboards: 1,108px of masthead,
  // controls and PROSE sat above the first data row, 484px of it explanatory
  // copy (the metric explainer, the backtest scorecard, the column key and the
  // frozen-column disclosure). That is more than a full phone screen a reader
  // has to scroll past EVERY visit to reach a board he came for, to re-read a
  // methodology he needs ONCE.
  //
  // None of it is deleted. It rides one collapsible per board, CLOSED by
  // default at every width (owner decision O2, 2026-09-11: the board is what
  // a reader came for, so the 2026-08-05 open-on-desktop default is
  // reversed; measured at 1440x900 the reliever table top moved from y 770
  // to 589). A reader who opens the fold keeps it open: collapseState reads
  // his stored choice before this default, on every board and every visit.
  // The fold head keeps the row count visible in both states, so the one
  // number that is data rather than methodology never hides.
  // `lead` is HTML, like collapsible()'s title: escape anything dynamic at the
  // call site (every caller today passes a number or an already-esc()'d value).
  function proseFold(id, lead, body) {
    if (!body) return "";
    return collapsible(id,
      '<span class="mlbstats-fold-lead">' + lead + "</span>"
      + '<span class="mlbstats-fold-hint">how to read this board</span>',
      body + VALUE_RULER_NOTE + rulerKey(), { collapsed: true, cls: "mlbstats-fold" });
  }
  // One sentence, once, on every board that carries a ladder. Terse on the page;
  // the cuts are behind the glossary hook, per house rule.
  var VALUE_RULER_NOTE = '<p class="mlbstats-note"><span data-gl="value_ruler">'
    + "Colour reads on the value ruler.</span></p>";
  // The ruler key under it (final-pass plan 5.7, PX-19): the step words with a
  // pixel meter each. Every family on these boards is an index family, which
  // never reaches the below-zero step, so the key stops at `below`.
  function rulerKey() {
    return (typeof EephusTiers !== "undefined" && EephusTiers.keyHTML) ? EephusTiers.keyHTML({ neg: false }) : "";
  }
  function bindCollapse(root) {
    root.querySelectorAll("[data-collapse]").forEach(function (el) {
      var head = el.querySelector(".mlbstats-collapse-head");
      if (!head) return;
      head.addEventListener("click", function () {
        var id = el.getAttribute("data-collapse");
        var next = !el.classList.contains("is-collapsed");
        el.classList.toggle("is-collapsed", next);
        head.setAttribute("aria-expanded", String(!next));
        setCollapse(id, next);
      });
    });
  }

  // ---- column definitions (Relievers) --------------------------------------
  // Skill core first, then the Impact/leverage columns (kept distinct from the
  // REM+ talent number by design).
  // RIV+ is a realized record. The 2026-09-18 re-gate (docs/HEM_RIV_REGATE_GATE.md)
  // forbids any forward reading of it, and says the column copy has to say so.
  var RIV_TITLE = "Realized value this season: 70% WPA and 30% shutdowns minus meltdowns, 100 + 10z"
    + " over the reliever pool. A record of what happened, not a forecast: this season's REM+ predicts"
    + " next season's RIV+ better than this season's RIV+ does. Not shown to track free-agent pay"
    + " better than REM+.";
  var REL_COLS = [
    { key: "name", label: "Reliever", term: null, sortable: true, kind: "name", asc: true },
    { key: "rem_plus", label: "REM+", term: "rem_plus", fmt: runCell, num: true, desc: true, isRem: true },
    { key: "rem_plus_3yr", label: "REM+ 3yr", term: "rem_plus_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear",
      get: function (r) { return r.rem_plus_3yr; },
      cell: function (r) {
        return r.rem_plus_3yr == null ? "" : win3yrCell(r, "rem_plus_3yr", "under 2 seasons or 40 IP");
      } },
    { key: "xrem_plus", label: "xREM+", term: "xrem_plus", num: true, desc: true, isRem: true,
      title: "REM+ scale on Savant xwOBA allowed. A deserved read beside REM+, not a replacement: xwOBA allowed did not beat FIP predictively. Tracked relievers only.",
      get: function (r) { return r.xrem_plus; },
      cell: function (r) { return r.xrem_plus == null ? "" : runCell(r.xrem_plus); } },
    { key: "luck", label: "Luck (wOBA)", num: true, desc: true,
      title: "wOBA allowed minus xwOBA allowed. Positive: allowed more than his contact deserved; negative: less.",
      get: function (r) { return r.luck; },
      cell: function (r) {
        if (r.luck == null) return "";
        var v = r.luck;
        var col = v >= 0.02 ? "var(--up)" : v <= -0.02 ? "var(--down)" : "var(--text-tertiary)";
        return '<span style="color:' + col + ';font-variant-numeric:tabular-nums;">' + (v > 0 ? "+" : "") + v.toFixed(3) + "</span>";
      } },
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true,
      title: "Pitching eWAR this season; the WAR/IP+ numerator." },
    // Reliever-anchored WAR/IP+. Separate metric from the starter board's
    // WAR/IP+ (same field name, different payload, different anchor pool): a
    // reliever banks more WAR per inning than a starter of equal talent, so the
    // two are never pooled. The z family, not the ratio family: 100 + 10z has SD
    // exactly 10.
    { key: "war_ip_plus", label: "WAR/IP+", term: "war_ip_plus_rp", num: true, desc: true, isRem: true,
      ewar: true,
      title: "Pitching eWAR per inning, 100 + 10z over relievers with 20+ IP; shown at 30+ IP. Not comparable with the starter board's WAR/IP+. p = percentile on this board.",
      get: function (r) { return r.war_ip_plus; },
      cell: function (r) {
        if (r.war_ip_plus == null) return "";
        var s = remCell(r.war_ip_plus);
        if (r.war_ip_plus_pct != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(r.war_ip_plus_pct) + "</span>";
        return s;
      } },
    { key: "war_ip_plus_adj", label: "WAR/IP+ adj", term: "war_ip_plus_rp_adj", num: true, desc: true, isRem: true,
      title: "WAR/IP+ with the rate shrunk toward the pool by innings, re-standardised (10 points = 1 SD). A thin-sample readability aid, not a forecast: neither WAR rate predicts next season better than season WAR.",
      get: function (r) { return r.war_ip_plus_adj; },
      cell: function (r) { return r.war_ip_plus_adj == null ? "" : remCell(r.war_ip_plus_adj); } },
    { key: "war_ip_plus_3yr", label: "WAR/IP+ 3yr", term: "war_ip_plus_rp_3yr", num: true, desc: true, isRem: true,
      title: "Trailing three seasons, innings-weighted, on the same eWAR series as WAR/IP+.",
      vintage: "multiyear_war_rate",
      get: function (r) { return r.war_ip_plus_3yr; },
      cell: function (r) {
        if (r.war_ip_plus_3yr == null) return "";
        var s = remCell(r.war_ip_plus_3yr);
        if (r.war_ip_plus_3yr_pct != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(r.war_ip_plus_3yr_pct) + "</span>";
        if (r.war_ip_plus_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 40 IP in the trailing window">*</span>';
        return s;
      } },
    { key: "ip", label: "IP", fmt: f1, num: true },
    { key: "g", label: "G", fmt: fInt, num: true },
    { key: "saves", label: "SV", fmt: fInt, num: true, title: "Saves. Context; does not move REM+." },
    { key: "holds", label: "HLD", fmt: fInt, num: true, title: "Holds. Context; does not move REM+." },
    { key: "k_pct", label: "K%", term: "k_pct", fmt: fPct, num: true },
    { key: "bb_pct", label: "BB%", term: "bb_pct", fmt: fPct, num: true, asc: true },
    { key: "k_bb_pct", label: "K-BB%", term: "k_bb_pct", fmt: fPct, num: true },
    // NOT the standard FIP. The payload key is `fip` for compatibility
    // (build_site's current-lines payload and assets/fa.js read it), but the
    // value is rem_plus.fip_skill: every component rate shrunk toward the
    // RELIEVER pool by sample size, plus a reliever-pool constant. It is the
    // number REM+ is a ratio of, so the header names it Skill FIP and links
    // the skill_fip glossary entry, never the standard `fip` one.
    { key: "fip", label: "Skill FIP", term: "skill_fip", fmt: f2, num: true, asc: true,
      title: skillFipTitle("reliever", "REM+") },
    { key: "swstr_pct", label: "SwStr%", term: "swstr_pct", fmt: fPct, num: true,
      title: "Whiffs per pitch, derived from the Baseball Savant custom leaderboard as whiff% x swing%, the one source both pitcher boards use. Display only: no score on this board reads it." },
    { key: "whiff_pct", label: "Whiff%", term: "whiff_pct", fmt: fPct, num: true,
      title: savantTitle("Misses per swing.") },
    { key: "chase_pct", label: "Chase%", term: "chase_pct", fmt: fPct, num: true,
      title: savantTitle("Swings per pitch outside Savant's strike zone.") },
    { key: "z_contact_pct", label: "Z-Contact%", term: "z_contact_pct", fmt: fPct, num: true, asc: true,
      title: savantTitle("Contact per swing at a pitch inside Savant's strike zone.") },
    { key: "f_strike_pct", label: "F-Strike%", term: "f_strike_pct", fmt: fPct, num: true,
      title: savantTitle("Share of plate appearances that start with a strike.") },
    { key: "fb_velo", label: "FB velo", term: "fb_velo", fmt: f1, num: true,
      title: "Average fastball speed in mph, from the Baseball Savant custom leaderboard. Display only: no score on this board reads it." },
    { key: "era", label: "ERA", term: "era", fmt: f2, num: true, asc: true },
    { key: "gmli", label: "gmLI", term: "gmli", fmt: f2, num: true },
    // Frozen the same way as REM+ 3yr (leverage_consistency_eval.json), but its
    // join stamps no vintage block on the payload, so there is no date to show
    // and none is invented. Stamping one is an exporter change, not a frontend
    // one: see _join_leverage_consistency in bullpen_export.py, which returns a
    // row count where its sibling _join_rem_plus_3yr returns a vintage dict.
    { key: "gmli_3yr", label: "gmLI 3yr", term: "gmli_3yr", fmt: f2, num: true,
      title: "Trailing 3-year game-entry LI, frozen from the leverage-consistency artifact, which ships no date. Deployment context; not an input to REM+.",
      cell: function (r) {
        if (r.gmli_3yr == null) return "";
        var s = f2(r.gmli_3yr);
        if (r.gmli_3yr_pct != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(r.gmli_3yr_pct) + "</span>";
        if (r.gmli_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 60 relief entries in the trailing window">*</span>';
        return s;
      } },
    { key: "riv_plus", label: "RIV+", term: "riv_plus", fmt: runCell, num: true, desc: true,
      title: RIV_TITLE },
    { key: "wpa", label: "WPA", term: "wpa", fmt: fSigned, num: true },
    { key: "wpa_li", label: "WPA/LI", term: "wpa_li", fmt: fSigned, num: true },
    { key: "sd_md", label: "SD-MD", term: "shutdowns_meltdowns", fmt: fInt, num: true,
      get: function (r) { var sd = num(r.sd), md = num(r.md); return (sd == null && md == null) ? null : (sd || 0) - (md || 0); } },
  ];

  // ---- history columns ------------------------------------------------------
  // A past board reuses the LIVE column objects, so it inherits their tooltips
  // too, and one of those sentences is only true on the live board: the eWAR
  // title dates itself ("this season") and names the WAR rate it feeds, a
  // column no history board carries. historyTitle swaps that one sentence and
  // copies every other property (term, formatter, the ewar flag, noteFrom)
  // through untouched.
  function historyTitle(cols, key, title) {
    return cols.map(function (c) {
      if (c.key !== key) return c;
      var out = {};
      for (var k in c) { if (Object.prototype.hasOwnProperty.call(c, k)) out[k] = c[k]; }
      out.title = title;
      return out;
    });
  }
  // The history exports join eWAR per (player, season) (spec E6) and the
  // recorded wOBA (E8). A season built before those joins carries neither, and
  // an empty column is exactly what the drop lists below exist to prevent, so a
  // joined key with no value anywhere in the rendered season drops out here and
  // comes back by itself once a rebuilt payload carries it. Nothing else is
  // filtered this way: the static lists still say what a history board can hold.
  var HISTORY_JOINED = { war: 1, woba_raw: 1 };
  function coveredCols(cols, rows) {
    return cols.filter(function (c) {
      if (!HISTORY_JOINED[c.key]) return true;
      for (var i = 0; i < rows.length; i++) {
        var v = rows[i][c.key];
        if (v !== null && v !== undefined && v !== "") return true;
      }
      return false;
    });
  }

  // Past-season history rows (bullpen_history.json) carry only the season-level
  // fields, not the trailing-window ones. Reuse the same column objects so the
  // history board renders and sorts identically, dropping the columns whose data
  // (rem_plus_3yr, gmli_3yr, wpa_li) does not exist in a history row.
  // This one is an ALLOW-list (the starter/hitter boards use drop-lists), so a
  // new current-only column such as WAR/IP+ or WAR/IP+ 3yr is excluded from the
  // history board by simply not being listed here. `war` IS listed: eWAR is a
  // season count, joined per (player, season) by the history export, while the
  // rates standardised on the live pool stay out.
  var REL_HISTORY_KEYS = { name: 1, rem_plus: 1, riv_plus: 1, ip: 1, g: 1, k_pct: 1,
    bb_pct: 1, k_bb_pct: 1, fip: 1, swstr_pct: 1, era: 1, gmli: 1, wpa: 1, sd_md: 1, saves: 1, holds: 1,
    war: 1 };
  var REL_HISTORY_COLS = historyTitle(REL_COLS.filter(function (c) { return REL_HISTORY_KEYS[c.key]; }),
    "war", "Pitching eWAR for the season shown.");

  var TEAM_COLS = [
    { key: "team", label: "Team", sortable: true, kind: "team", asc: true },
    { key: "bullpen_plus", label: "Bullpen+", term: "bullpen_plus", fmt: remCell, num: true, desc: true, isRem: true },
    { key: "team_war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true,
      title: "Relief eWAR of this pen's arms. Same club basis as the Team column." },
    // GLOSSARY PROXY, deliberate. There is no leverage_deploy_plus entry: the
    // glossary defines bullpen_plus, and Lev Deploy+ is the same index computed
    // on leverage-weighted rather than IP-weighted innings, so the tooltip
    // explains the scale a reader needs even though the id is not this column's
    // own. Point it at a real leverage_deploy_plus entry the day one exists;
    // until then a near-miss definition beats no tooltip at all.
    { key: "leverage_deploy_plus", label: "Lev Deploy+", term: "bullpen_plus", fmt: remCell, num: true,
      title: "Bullpen+ on leverage-weighted rather than IP-weighted relief innings. Same 100-average scale." },
    { key: "n_above_avg", label: "Above-avg arms", fmt: fInt, num: true,
      title: "Relievers at REM+ 100 or better / relievers on the pen.",
      get: function (t) { var a = num(t.n_above_avg), n = num(t.n_relievers); return a; },
      cell: function (t) { return fInt(t.n_above_avg) + (t.n_relievers != null ? '<span class="proj-dim"> / ' + fInt(t.n_relievers) + "</span>" : ""); } },
    { key: "high_lev_core_rem", label: "Hi-Lev Core", fmt: remCell, num: true,
      title: "Mean REM+ of the pen's top three arms by gmLI." },
    { key: "relief_ip", label: "Relief IP", fmt: f1, num: true },
    { key: "team_wpa", label: "WPA", term: "wpa", fmt: fSigned, num: true },
    { key: "sd_md", label: "SD-MD", term: "shutdowns_meltdowns", fmt: fInt, num: true,
      get: function (t) { var sd = num(t.sd), md = num(t.md); return (sd == null && md == null) ? null : (sd || 0) - (md || 0); } },
  ];

  // ---- state ----------------------------------------------------------------
  var DATA = null;
  var LOAD_ERROR = false;          // fetch failed / non-OK (distinct from "not exported yet")
  var view = "relievers";          // relievers | teams | depth
  var relSort = { key: "rem_plus", asc: false };
  var teamSort = { key: "bullpen_plus", asc: false };
  var query = "";
  var qualifiedOnly = true;
  // Filters added 2026-08-03. Until then the only reachable narrowing on a
  // 460-row reliever board was a free-text box and one binary checkbox, so
  // "the Padres' high-leverage arms with 30+ innings" was a question the page
  // could answer from data already on every row and offered no way to ask.
  // All three are client-side off fields the payload already carries
  // (team / role / ip); nothing here refetches.
  var relTeam = "";                // "" = all clubs
  var relRoles = [];               // empty = all roles; otherwise an OR set
  var relMinIp = null;             // null = no floor

  // Yearly history board (bullpen_history.json) is lazy-fetched the first time a
  // past season is picked. relSeason is "current" for the live board or a season
  // string like "2025". HISTORY caches the payload; the flags drive the inline
  // loading / error states so a failed fetch never leaves a blank board.
  var HISTORY_URL = "/data/bullpen_history.json";
  var relSeason = "current";
  var HISTORY = null;
  var HISTORY_LOADING = false;
  var HISTORY_ERROR = false;

  function getVal(col, row) {
    if (col.get) return col.get(row);
    return row[col.key];
  }


  // ---- column views -----------------------------------------------------------
  // ONE table per board, several named views of it. Every column still renders
  // into the markup (the CSV export, the glossary wiring and the smoke harness
  // all read the whole row); a column outside the active view carries
  // mlbstats-cv-off (and data-export-skip) and site.css hides it. A view is an
  // ordered key list; "|" starts a new column group (a hairline rule on its
  // first cell). `phone` is the subset that survives at 640px and below; every
  // other view column carries mlbstats-cv-wide. The column the board is SORTED
  // on is always shown, appended after the view's own columns if the view lacks
  // it, so an old link sorted on K% still shows K%. keys: null = every column.
  // History boards reuse the live views; a key a history array lacks is skipped.
  // The All pill says what it costs on a narrow screen. All carries EVERY
  // column, the Baseball Savant display columns included (owner answer M26-3,
  // 2026-09-25): it runs 1,249 to 1,431px, so up to a 1440 window it may scroll
  // sideways inside its own table frame, never the page, with the name column
  // held in place (test_mlbstats_fit.py).
  var ALL_TITLE = "Every column, the Baseball Savant columns included; when the board is wider than the screen it scrolls sideways inside the table.";
  var COL_VIEWS = {
    rel: [
      { id: "standard", label: "Standard", phone: ["rem_plus", "war", "ip", "saves", "era"],
        keys: ["rem_plus", "rem_plus_3yr", "|", "war", "war_ip_plus", "|", "ip", "saves", "holds", "|",
               "k_bb_pct", "era", "|", "gmli", "riv_plus"] },
      { id: "skill", label: "Skill", phone: ["rem_plus", "k_bb_pct", "fip", "era"],
        keys: ["rem_plus", "xrem_plus", "luck", "|", "k_pct", "bb_pct", "k_bb_pct", "swstr_pct", "|",
               "fip", "era", "|", "ip"] },
      { id: "value", label: "Value", phone: ["war", "war_ip_plus", "riv_plus", "ip"],
        keys: ["war", "war_ip_plus", "war_ip_plus_adj", "war_ip_plus_3yr", "|", "rem_plus", "riv_plus",
               "wpa", "|", "ip"] },
      { id: "leverage", label: "Leverage", phone: ["gmli", "saves", "riv_plus", "wpa"],
        keys: ["gmli", "gmli_3yr", "|", "saves", "holds", "sd_md", "|", "riv_plus", "wpa", "wpa_li", "|",
               "g", "ip"] },
      { id: "discipline", label: "Discipline", phone: ["rem_plus", "swstr_pct", "chase_pct", "fb_velo"],
        keys: ["rem_plus", "|", "k_pct", "swstr_pct", "whiff_pct", "|", "chase_pct", "z_contact_pct",
               "f_strike_pct", "|", "fb_velo", "|", "ip"] },
      { id: "all", label: "All", phone: null, keys: null, title: ALL_TITLE }
    ],
    sp: [
      { id: "standard", label: "Standard", phone: ["sem_plus", "war", "ip", "k_bb_pct", "era"],
        keys: ["sem_plus", "sem_plus_3yr", "|", "war", "war_ip_plus", "|", "ip", "gs", "ip_per_gs", "|",
               "k_bb_pct", "era"] },
      { id: "skill", label: "Skill", phone: ["sem_plus", "k_bb_pct", "fip", "era"],
        keys: ["sem_plus", "xsem_plus", "luck", "|", "k_pct", "bb_pct", "k_bb_pct", "gb_pct", "hr9", "|",
               "fip", "era"] },
      { id: "value", label: "Value", phone: ["war", "war_ip_plus", "ip", "gs"],
        keys: ["war", "war_ip_plus", "war_ip_plus_adj", "war_ip_plus_3yr", "|", "sem_plus", "|",
               "ip", "gs", "ip_per_gs"] },
      { id: "discipline", label: "Discipline", phone: ["sem_plus", "swstr_pct", "chase_pct", "fb_velo"],
        keys: ["sem_plus", "|", "k_pct", "swstr_pct", "whiff_pct", "|", "chase_pct", "z_contact_pct",
               "f_strike_pct", "|", "fb_velo", "|", "ip"] },
      { id: "all", label: "All", phone: null, keys: null, title: ALL_TITLE }
    ],
    hit: [
      { id: "standard", label: "Standard", phone: ["hem_plus", "wrc_plus", "war", "pa", "hr"],
        keys: ["hem_plus", "wrc_plus", "|", "war", "war_pa_plus", "|", "pa", "hr", "sb", "|",
               "avg", "obp", "slg"] },
      { id: "skill", label: "Skill", phone: ["hem_plus", "xhem_plus", "fwdhem_plus", "pwoba"],
        keys: ["hem_plus", "hem_plus_3yr", "xhem_plus", "fwdhem_plus", "luck_gap", "pwoba", "|",
               "woba_raw", "|", "bb_pct", "k_pct", "babip"] },
      { id: "value", label: "Value", phone: ["war", "war_pa_plus", "hem_plus", "pa"],
        keys: ["war", "war_pa_plus", "war_pa_plus_adj", "war_pa_plus_3yr", "|", "hem_plus", "wrc_plus",
               "|", "pa"] },
      { id: "batting", label: "Batting", phone: ["avg", "obp", "slg", "hr"],
        keys: ["pa", "hr", "sb", "|", "avg", "obp", "slg", "ops", "iso", "woba_raw", "|", "bb_pct", "k_pct"] },
      { id: "discipline", label: "Discipline", phone: ["hem_plus", "chase_pct", "whiff_pct", "sweet_spot_pct"],
        keys: ["hem_plus", "|", "bb_pct", "k_pct", "|", "chase_pct", "whiff_pct", "z_contact_pct", "|",
               "sweet_spot_pct", "pull_pct", "|", "pa"] },
      { id: "all", label: "All", phone: null, keys: null, title: ALL_TITLE }
    ],
    def: [
      { id: "standard", label: "Standard", phone: ["pos", "dem_plus", "fld_total", "inn"],
        keys: ["pos", "|", "dem_plus", "dem_plus_3yr", "dem_plus_pos_pct", "|", "fld_total", "def_runs",
               "|", "inn", "|", "hem_plus", "war"],
        // A catcher board needs its framing column: with the C chip alone
        // active, Frm joins Standard right after Fld.
        extra: function () {
          return (defensePos.length === 1 && defensePos[0] === "C") ? { after: "fld_total", key: "frm_runs" } : null;
        } },
      { id: "runs", label: "Runs", phone: ["pos", "fld_total", "def_runs", "inn"],
        keys: ["pos", "|", "fld_total", "fld_runs", "frm_runs", "|", "pos_runs", "pos_runs_fg", "def_runs", "|",
               "rate_1000_shrunk", "|", "inn"] },
      // Catchers' own work beyond framing, from Savant. Pick the C chip to read
      // it as a catcher board; other positions show the columns blank. ONE view
      // with every column, each sample count beside its rate (owner answer
      // M26-4, 2026-09-25): it runs about 826px, so below a 1024 window it may
      // scroll sideways inside its own table frame, never the page. The
      // Blocking and Throwing views it replaces still resolve here
      // (VIEW_ALIAS below), so an old dcols= link or a stored pick lands on it.
      { id: "catching", label: "Catching", phone: ["dem_plus", "frm_runs", "c_blk_runs", "c_cs_runs"],
        keys: ["pos", "|", "dem_plus", "frm_runs", "|", "c_blk_runs", "c_blk_aa", "c_blk_pitches", "|",
               "c_cs_runs", "c_cs_aa", "c_sb_att", "|", "c_pop", "c_exchange", "c_arm", "|", "inn"] },
      { id: "all", label: "All", phone: null, keys: null, title: ALL_TITLE }
    ],
    // Single-view boards: no view strip, only a phone subset.
    levbat: [{ id: "standard", label: "Standard", phone: ["wpa", "wpa_li", "war", "pa"], keys: null }],
    levsp: [{ id: "standard", label: "Standard", phone: ["wpa", "wpa_per_start", "war", "gs"], keys: null }],
    relteam: [{ id: "standard", label: "Standard", phone: ["bullpen_plus", "team_war", "high_lev_core_rem", "relief_ip"], keys: null }],
    spteam: [{ id: "standard", label: "Standard", phone: ["rotation_plus", "team_war", "front_sem", "starter_ip"], keys: null }],
    hitteam: [{ id: "standard", label: "Standard", phone: ["offense_plus", "team_war", "heart_hem", "team_pa"], keys: null }],
    defteam: [{ id: "standard", label: "Standard", phone: ["team_dem_plus", "n_above_avg", "team_fld_total", "team_inn"], keys: null }],
    // The Overall board carries 12 to 15 columns now, so it gets named views
    // like the other four: Standard is the season line, Rate is the two
    // per-playing-time divisions (each over ITS OWN denominator, which is why
    // there is no single eWAR/600), All is everything.
    war: [
      { id: "standard", label: "Standard", phone: ["war", "war_bat", "war_pit", "pa"],
        keys: ["pos", "age", "|", "war", "war_bat", "war_pit", "|", "pa", "ip", "g", "gs", "|",
               "yrs", "clubs"] },
      { id: "rate", label: "Rate", phone: ["war", "bat_600", "pitch_200", "pa"],
        keys: ["pos", "age", "|", "war", "bat_600", "pitch_200", "|", "pa", "ip"] },
      { id: "all", label: "All", phone: null, keys: null, title: ALL_TITLE }
    ],
    warteam: [{ id: "standard", label: "Standard", phone: ["war", "war_earned", "war_bat", "war_sp"], keys: null }]
  };
  // Which named view each multi-view board is on. The hash outranks the
  // stored preference, which outranks Standard.
  var COL_VIEW = { rel: "standard", sp: "standard", hit: "standard", def: "standard",
                   war: "standard" };
  var COL_VIEW_HASH = { rel: "rcols", sp: "scols", hit: "hcols", def: "dcols", war: "wcols" };
  // Retired view ids and the view that replaced each, so a deep link or a
  // stored pick naming one opens the replacement rather than Standard.
  var VIEW_ALIAS = { def: { blocking: "catching", throwing: "catching" } };
  function resolveView(board, id) {
    var a = VIEW_ALIAS[board];
    return (a && a[id]) || id;
  }
  (function () {
    Object.keys(COL_VIEW).forEach(function (b) {
      try {
        var s = resolveView(b, window.localStorage.getItem("mlbstats.cols." + b));
        if (s && viewById(b, s)) COL_VIEW[b] = s;
      } catch (e) { /* localStorage optional */ }
    });
  })();
  function viewById(board, id) {
    var vs = COL_VIEWS[board] || [];
    for (var i = 0; i < vs.length; i++) if (vs[i].id === id) return vs[i];
    return null;
  }
  function activeView(board) {
    var vs = COL_VIEWS[board];
    if (!vs) return null;
    return viewById(board, COL_VIEW[board] || "standard") || vs[0];
  }
  // A pinned sort column sits last, after the view's own columns, with a group
  // rule, so an old link sorted on K% still shows K%. One exception, a house
  // rule: wRC+ sits right after HEM+ wherever both show, so a wRC+ sort on a
  // view that lacks it (Skill) joins HEM+ instead of trailing the view.
  var PIN_BESIDE = { wrc_plus: "hem_plus" };
  // [{c: column, cls: " mlbstats-cv-off" | " mlbstats-cv-wide" | " mlbstats-cv-grp" | ""}],
  // identity column first, then the view's columns in view order, then the
  // pinned sort column, then everything else (hidden) in master order.
  function viewPlan(cols, sort, board) {
    var v = activeView(board);
    var byKey = {};
    cols.forEach(function (c) { byKey[c.key] = c; });
    var phone = {};
    ((v && v.phone) || []).forEach(function (k) { phone[k] = 1; });
    if (sort && sort.key) phone[sort.key] = 1;
    var on = [], grp = {}, nextGrp = false;
    if (!v || !v.keys) {
      // All: every column (see ALL_TITLE).
      cols.forEach(function (c) { on.push(c); });
    } else {
      on.push(cols[0]);
      var keys = v.keys.slice();
      var ex = v.extra ? v.extra() : null;
      if (ex) { var at = keys.indexOf(ex.after); if (at >= 0 && keys.indexOf(ex.key) < 0) keys.splice(at + 1, 0, ex.key); }
      keys.forEach(function (k) {
        if (k === "|") { nextGrp = true; return; }
        var c = byKey[k];
        if (!c || on.indexOf(c) >= 0) return;
        if (nextGrp && on.length > 1) grp[k] = 1;
        nextGrp = false;
        on.push(c);
      });
      if (sort && byKey[sort.key] && on.indexOf(byKey[sort.key]) < 0) {
        var beside = PIN_BESIDE[sort.key] ? on.indexOf(byKey[PIN_BESIDE[sort.key]]) : -1;
        if (beside >= 0) on.splice(beside + 1, 0, byKey[sort.key]);
        else { grp[sort.key] = 1; on.push(byKey[sort.key]); }
      }
    }
    var plan = on.map(function (c, i) {
      var cls = "";
      if (i > 0 && v && v.phone && !phone[c.key]) cls += " mlbstats-cv-wide";
      if (grp[c.key]) cls += " mlbstats-cv-grp";
      return { c: c, cls: cls };
    });
    cols.forEach(function (c) { if (on.indexOf(c) < 0) plan.push({ c: c, cls: " mlbstats-cv-off", off: true }); });
    return plan;
  }
  // The view strip. Rides the season-pill markup (same active state, same
  // phone swipe strip, same 44px target), so there is no new control language.
  function viewPills(board) {
    var vs = COL_VIEWS[board];
    if (!vs || vs.length < 2) return "";
    var cur = activeView(board).id;
    return '<div class="mlbstats-seasons mlbstats-roles mlbstats-views" role="group" aria-label="Columns">'
      + '<span class="mlbstats-roles-lbl">Columns</span>'
      + vs.map(function (v) {
          var on = v.id === cur;
          return '<button type="button" class="mlbstats-season' + (on ? " active" : "") + '" data-colview="'
            + esc(board) + ":" + esc(v.id) + '" aria-pressed="' + on + '"'
            + (v.title ? ' title="' + esc(v.title) + '"' : "") + ">" + esc(v.label) + "</button>";
        }).join("") + "</div>";
  }
  function toolRow(pills, board) {
    return '<div class="mlbstats-toolrow">' + pills + viewPills(board) + "</div>";
  }
  // The years control plus, when a deep link named a span this board does not
  // publish, the one line that says so. Every board emits this where its season
  // pills used to be.
  function yearsRow(sec) {
    return toolRow(rangeControl(sec), winColBoard(sec)) + winRefusedNote(sec);
  }
  function bindColViews(root, rerender) {
    root.querySelectorAll("[data-colview]").forEach(function (b) {
      b.addEventListener("click", function () {
        var p = String(b.getAttribute("data-colview") || "").split(":");
        if (!COL_VIEWS[p[0]] || !viewById(p[0], p[1])) return;
        COL_VIEW[p[0]] = p[1];
        try { window.localStorage.setItem("mlbstats.cols." + p[0], p[1]); } catch (e) { /* optional */ }
        writeHash();
        rerender(b.id || null);
      });
    });
  }

  // Sortable-header wiring shared by every leaderboard: click AND Enter/Space
  // both activate the sort, and keyboard focus is restored to the same header
  // after the re-render replaces the table (the root element persists).
  function bindSortKeys(th, root, activate) {
    th.addEventListener("click", activate);
    th.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      var key = th.getAttribute("data-col");
      activate();
      var again = root.querySelector('.mlbstats-table th[data-col="' + key + '"]');
      if (again) again.focus();
    });
  }

  // ---- year windows: presets, a from/to range, and what a column may say -----
  // A window is a span of seasons, and its three classes of column behave
  // differently because the data does:
  //   SUM   a count adds over the window (eWAR, PA, IP, HR, WPA, runs).
  //   POOL  a rate is recomputed once, numerator over denominator, never the
  //         average of the seasons.
  //   INDEX a "+" index is NOT foldable in a browser: 100 is the average of ONE
  //         season's pool, so a window is a different pool and a window index is
  //         a different statistic. tools/mlbstats_window_lab.py computes a FIXED
  //         set of windows offline, by the same recipe the shipped 3-year
  //         columns use, and those are the only windows an index appears on. On
  //         any other window the board says so in one line instead of printing a
  //         number on a scale nobody computed.
  // Two rules ride every window index here, both read from the artifact rather
  // than typed: the span is in the column LABEL, and no value ruler, tier or
  // band colour is carried onto it (data/mlbstats_windows.json `method` says
  // why, and `pool_stats` says what 100 and one standard deviation actually are
  // on that pool, which the column tooltip reports).
  var WINDOWS_URL = "/data/mlbstats_windows.json";
  var SEASONS_URL = "/data/war_seasons.json";
  var WINDOWS = null, WINDOWS_LOADING = false, WINDOWS_ERROR = false;
  var WINDOW_DOC = {}, WINDOW_LOADING = {}, WINDOW_ERROR = {};
  var SEASONS = null, SEASONS_LOADING = false, SEASONS_ERROR = false;
  // section -> the lab's own board name, and the Columns strip it rides.
  var LAB_BOARD = { war: "overall", hitters: "hitters", starters: "starters",
                    bullpen: "bullpen", leverage: "leverage", defense: "defense" };
  var WIN_COLBOARD = { war: "war", hitters: "hit", starters: "sp", bullpen: "rel",
                       leverage: null, defense: "def" };
  // THE WINDOW IS THE STATE. null = Current (the live board). {lo, hi} is a
  // window, and lo === hi is the single past season the *season= keys have
  // always opened, so there is one render path and one thing to validate.
  var WIN = { bullpen: null, starters: null, hitters: null, leverage: null,
              defense: null, war: null };
  // One line when a deep link named a span this board does not publish: the
  // reader gets a visible wrong answer to correct rather than a silent one.
  var WIN_REFUSED = {};
  // Established only, ON by default on a window INDEX board. Measured on the
  // served artifact: 233 of 587 rows (40%) of the Last 3 hitter board are
  // provisional, which is what a denominator-weighted mean of per-season values
  // does with a partial window. The count boards need no such filter.
  var winEstablished = true;
  var FOLD_CACHE = {};

  function winSpan(w) { return w ? (w.lo === w.hi ? String(w.lo) : (w.lo + "-" + w.hi)) : ""; }
  function isWindow(sec) { var w = WIN[sec]; return !!(w && w.lo !== w.hi); }
  function winColBoard(sec) {
    return sec === "leverage" ? (leverageView === "starters" ? "levsp" : "levbat")
                              : WIN_COLBOARD[sec];
  }
  function round1(v) { return Math.round(v * 10) / 10; }

  // ---- per-section accessors, so one window renderer serves six boards -------
  function sectionLiveSeason(sec) {
    var d = sec === "war" ? warData : sec === "starters" ? starterData
          : sec === "hitters" ? hitterData : sec === "leverage" ? leverageData
          : sec === "defense" ? defenseData : DATA;
    return num(d && d.season);
  }
  function sectionHistorySeasons(sec) {
    if (sec === "war") return ((SEASONS && SEASONS.seasons) || []).slice();
    if (sec === "starters") return starterHistorySeasons();
    if (sec === "hitters") return hitterHistorySeasons();
    if (sec === "leverage") return leverageHistorySeasons();
    if (sec === "defense") return defenseHistorySeasons();
    return historySeasons();
  }
  function sectionCols(sec) {
    if (sec === "war") return warCols();
    if (sec === "starters") return STARTER_COLS;
    if (sec === "hitters") return HITTER_COLS;
    if (sec === "leverage") return levCols();
    if (sec === "defense") return DEFENSE_COLS;
    return REL_COLS;
  }
  function sectionSort(sec) {
    if (sec === "war") return warSort;
    if (sec === "starters") return starterSort;
    if (sec === "hitters") return hitterSort;
    if (sec === "leverage") return levSort();
    if (sec === "defense") return defenseSort;
    return relSort;
  }
  function sectionTeam(sec) {
    return sec === "war" ? warTeam : sec === "starters" ? starterTeam
      : sec === "hitters" ? hitterTeam : sec === "leverage" ? leverageTeam
      : sec === "defense" ? defenseTeam : relTeam;
  }
  function sectionQual(sec) {
    return sec === "war" ? warQualifiedOnly : sec === "starters" ? starterQualifiedOnly
      : sec === "hitters" ? hitterQualifiedOnly : sec === "leverage" ? leverageQualifiedOnly
      : sec === "defense" ? defenseQualifiedOnly : qualifiedOnly;
  }
  function sectionQuery(sec) {
    return sec === "war" ? warQuery : sec === "starters" ? starterQuery
      : sec === "hitters" ? hitterQuery : sec === "leverage" ? leverageQuery
      : sec === "defense" ? defenseQuery : query;
  }
  // {key, val}: the min-floor control each board carries, over the field it
  // filters. The Overall board and Leverage have none.
  var MIN_LABEL = { ip: "IP", pa: "PA", inn: "Inn" };
  // A floor typed into the min box filters the window TOTAL, not a season: 50 IP
  // over three seasons is a different question from 50 IP in one, so the control
  // says which it is asking rather than keeping its one-season label.
  function minLabel(sec, label) { return isWindow(sec) ? label + " (window)" : label; }
  function sectionMin(sec) {
    if (sec === "starters") return { key: "ip", val: starterMinIp };
    if (sec === "hitters") return { key: "pa", val: hitterMinPa };
    if (sec === "defense") return { key: "inn", val: defenseMinInn };
    if (sec === "bullpen") return { key: "ip", val: relMinIp };
    return { key: null, val: null };
  }
  function renderSection(sec) {
    if (sec === "starters") renderStarters();
    else if (sec === "hitters") renderHitters();
    else if (sec === "leverage") renderLeverage();
    else if (sec === "defense") renderDefense();
    else if (sec === "war") renderWar();
    else render();
  }
  // The five single-season vars every history path still reads are DERIVED from
  // the window and written nowhere else: two copies of one piece of state is how
  // a season and a range end up disagreeing on the same page.
  function seasonVar(sec) { var w = WIN[sec]; return (w && w.lo === w.hi) ? String(w.lo) : "current"; }
  function syncSeasonVars() {
    relSeason = seasonVar("bullpen");
    starterSeason = seasonVar("starters");
    hitterSeason = seasonVar("hitters");
    leverageSeason = seasonVar("leverage");
    defenseSeason = seasonVar("defense");
  }

  // ---- the lab's windows -----------------------------------------------------
  function labWindows(board) {
    var out = [];
    ((WINDOWS && WINDOWS.windows) || []).forEach(function (w) {
      if (!w || !w.key || !w.seasons || w.seasons.length < 2) return;
      if (board !== "overall" && w.n_rows && !w.n_rows[board]) return;
      out.push(w);
    });
    return out;
  }
  function winEnds(w) { return { lo: w.seasons[0], hi: w.seasons[w.seasons.length - 1] }; }
  function winLabel(w) { var e = winEnds(w); return e.lo + "-" + e.hi; }
  function labWindowFor(board, lo, hi) {
    var hit = null;
    labWindows(board).forEach(function (w) {
      var e = winEnds(w);
      if (e.lo === lo && e.hi === hi) hit = w;
    });
    return hit;
  }
  function labWindowByKey(board, key) {
    var hit = null;
    labWindows(board).forEach(function (w) { if (w.key === key) hit = w; });
    return hit;
  }
  function overallSpan() {
    var s = (SEASONS && SEASONS.seasons) || [];
    return s.length > 1 ? { lo: s[0], hi: s[s.length - 1] } : null;
  }
  // Every season this section can be asked for: its own history list, its live
  // season, and every season inside a window the lab built for it.
  function sectionSeasons(sec) {
    var seen = {}, out = [];
    function add(y) { y = num(y); if (y != null && !seen[y]) { seen[y] = 1; out.push(y); } }
    (sectionHistorySeasons(sec) || []).forEach(add);
    add(sectionLiveSeason(sec));
    labWindows(LAB_BOARD[sec]).forEach(function (w) { (w.seasons || []).forEach(add); });
    out.sort(function (a, b) { return a - b; });
    return out;
  }
  // VALIDATE, NEVER TRUST. Both endpoints have to be seasons this section
  // publishes, and lo <= hi, or the key is refused. Before any payload has
  // landed there is nothing to validate against, so the decision waits rather
  // than rejecting a good link: winCheck re-runs on every render.
  function seasonsReady(sec) {
    if (sec === "war") return !!(SEASONS && SEASONS.players) || SEASONS_ERROR;
    if (sec === "starters") return !!STARTER_HISTORY || STARTER_HISTORY_ERROR;
    if (sec === "hitters") return !!HITTER_HISTORY || HITTER_HISTORY_ERROR;
    if (sec === "leverage") return !!leverageHistory || leverageHistoryErr;
    if (sec === "defense") return !!DEFENSE_HISTORY || DEFENSE_HISTORY_ERROR;
    return !!HISTORY || HISTORY_ERROR;
  }
  function spanAllowed(sec, lo, hi) {
    if (lo == null || hi == null || lo > hi) return false;
    if (labWindowFor(LAB_BOARD[sec], lo, hi)) return true;   // the lab built it
    if (!seasonsReady(sec)) return true;                     // decide when it lands
    var s = sectionSeasons(sec);
    if (!s.length) return true;
    return s.indexOf(lo) >= 0 && s.indexOf(hi) >= 0;
  }
  // The five history payloads, one per section, each already guarded against a
  // second fetch. winCheck needs one to JUDGE a span the lab did not build.
  function loadSectionHistory(sec) {
    if (sec === "war") loadSeasons(sec);
    else if (sec === "starters") loadStarterHistory();
    else if (sec === "hitters") loadHitterHistory();
    else if (sec === "leverage") loadLeverageHistory();
    else if (sec === "defense") loadDefenseHistory();
    else loadHistory();
  }
  function winCheck(sec) {
    var w = WIN[sec];
    if (!w) return;
    // A span the lab built is allowed without any history. Anything else has to
    // be checked against the seasons this section publishes, so the payload that
    // check reads is FETCHED rather than waited for forever: without this,
    // #hyears=2019-2025 sat on the generic refusal, seasonsReady stayed false
    // and the bad key was never cleaned out of the URL.
    if (!labWindowFor(LAB_BOARD[sec], w.lo, w.hi) && !seasonsReady(sec)) loadSectionHistory(sec);
    if (spanAllowed(sec, w.lo, w.hi)) return;
    WIN_REFUSED[sec] = winSpan(w) + (w.lo === w.hi ? " is not a season" : " is not a span")
      + " this board publishes, so it opened on Current.";
    WIN[sec] = null;
    syncSeasonVars();
    writeHash();
  }
  function winRefusedNote(sec) {
    return WIN_REFUSED[sec] ? '<div class="mlbstats-note mlbstats-winrefused">'
      + esc(WIN_REFUSED[sec]) + "</div>" : "";
  }
  function setWindow(sec, win) {
    WIN[sec] = win;
    WIN_REFUSED[sec] = "";
    syncSeasonVars();
    if (win) loadWindows(sec);
    if (win && sec === "war") loadSeasons(sec);
    writeHash();
    renderSection(sec);
  }

  // ---- loaders ---------------------------------------------------------------
  function loadWindows(sec) {
    if (WINDOWS || WINDOWS_LOADING) return;
    WINDOWS_LOADING = true;
    WINDOWS_ERROR = false;
    fetch(WINDOWS_URL, { cache: "no-cache" })
      .then(function (r) {
        if (r.status === 404) return null;         // the lab has never run here
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (j) {
        WINDOWS = (j && j.windows) ? j : { windows: [] };
        WINDOWS_LOADING = false;
        if (!patchRange(sec)) renderSection(sec);
      })
      .catch(function () { WINDOWS_LOADING = false; WINDOWS_ERROR = true; renderSection(sec); });
  }
  // On Current the window list feeds the Years control and nothing else, so
  // its arrival rewrites that control in place (QMLP05: it used to re-render
  // the 928-row board). A window board, or a section not yet painted, renders.
  function patchRange(sec) {
    if (WIN[sec]) return false;
    var host = document.getElementById("mlbstats-section-" + sec);
    var el = host && host.querySelector(".mlbstats-range");
    if (!el) return false;
    el.outerHTML = rangeControl(sec);
    return true;
  }
  function loadWindowDoc(w, sec) {
    var key = w.key;
    if (WINDOW_DOC[key] || WINDOW_LOADING[key]) return;
    var file = String(w.file || "").replace(/[^A-Za-z0-9_.-]/g, "");
    if (!file) { WINDOW_ERROR[key] = true; return; }
    WINDOW_LOADING[key] = true;
    WINDOW_ERROR[key] = false;
    fetch("/data/" + file, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) {
        WINDOW_DOC[key] = (j && j.boards) ? j : null;
        WINDOW_LOADING[key] = false;
        if (!WINDOW_DOC[key]) WINDOW_ERROR[key] = true;
        renderSection(sec);
      })
      .catch(function () { WINDOW_LOADING[key] = false; WINDOW_ERROR[key] = true; renderSection(sec); });
  }
  // The per-season substrate the Overall board folds. Fetched WITH the board
  // rather than on the first non-Current pick, because Overall is the landing
  // section now and its from/to control has to be complete on the first click:
  // a picker that grows a second after the reader opens it is worse than the
  // transfer, and the same fold is what the per-season expander reads.
  function loadSeasons(sec) {
    if (SEASONS || SEASONS_LOADING) return;
    SEASONS_LOADING = true;
    SEASONS_ERROR = false;
    fetch(SEASONS_URL, { cache: "no-cache" })
      .then(function (r) {
        if (r.status === 404) return null;
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (j) {
        SEASONS = (j && j.players) ? j : null;
        SEASONS_LOADING = false;
        if (!SEASONS) SEASONS_ERROR = true;
        renderSection(sec || "war");
      })
      .catch(function () { SEASONS_LOADING = false; SEASONS_ERROR = true; renderSection(sec || "war"); });
  }

  // ---- the control -----------------------------------------------------------
  // Presets plus a from/to, in the toolrow slot the season pills used to own.
  // The pills are REPLACED rather than joined: from/to reaches every year they
  // did, and a strip of years beside a range picker is two control languages for
  // one question (owner decision D7).
  function rangeControl(sec) {
    if (!WINDOWS && !WINDOWS_LOADING && !WINDOWS_ERROR) loadWindows(sec);
    var cur = WIN[sec], out = [];
    function btn(id, label, sub, on, title) {
      return '<button type="button" class="mlbstats-season' + (on ? " active" : "")
        + '" data-mlbrange="' + esc(sec) + ":" + esc(id) + '" aria-pressed="' + on + '"'
        + (title ? ' title="' + esc(title) + '"' : "") + ">" + esc(label)
        + (sub ? '<span class="proj-dim"> ' + esc(sub) + "</span>" : "") + "</button>";
    }
    out.push(btn("current", "Current", "", !cur, "The live season, as the board is served."));
    labWindows(LAB_BOARD[sec]).forEach(function (w) {
      var e = winEnds(w);
      out.push(btn(w.key, w.name || winLabel(w), w.label || winLabel(w),
        !!cur && cur.lo === e.lo && cur.hi === e.hi,
        "A window the lab computed, so this board keeps its + indexes on it."));
    });
    var all = (sec === "war") ? overallSpan() : null;
    if (all) {
      out.push(btn("all", "All", all.lo + "-" + all.hi,
        !!cur && cur.lo === all.lo && cur.hi === all.hi,
        "Every season the eWAR artifact covers, summed."));
    }
    var years = sectionSeasons(sec);
    var live = sectionLiveSeason(sec);
    var lo = cur ? cur.lo : (live != null ? live : years[years.length - 1]);
    var hi = cur ? cur.hi : lo;
    function sel(which, val) {
      // Shipped with no class, in a pill row the module's only control rule does
      // not reach, so it rendered in the browser default (owner report
      // 2026-09-18). `.eephus-select` is the shared themed-select class in
      // site.css; the element, its options, its keyboard and screen-reader
      // behaviour and every deep-link value are untouched.
      return '<select class="eephus-select" data-mlbrangesel="' + esc(sec) + ":" + which + '" aria-label="'
        + (which === "lo" ? "First season" : "Last season") + '">'
        + years.map(function (y) {
            return '<option value="' + y + '"' + (y === val ? " selected" : "") + ">" + y + "</option>";
          }).join("") + "</select>";
    }
    var picker = years.length > 1
      ? '<span class="mlbstats-range-fromto"><label class="mlbstats-ctl">from ' + sel("lo", lo)
        + '</label><label class="mlbstats-ctl">to ' + sel("hi", hi) + "</label></span>"
      : "";
    return '<div class="mlbstats-seasons mlbstats-roles mlbstats-range" role="group" aria-label="Years">'
      + '<span class="mlbstats-roles-lbl">Years</span>' + out.join("") + picker + "</div>";
  }
  function applyRange(spec) {
    var p = String(spec || "").split(":"), sec = p[0], id = p[1];
    if (!LAB_BOARD[sec]) return;
    if (id === "current") { setWindow(sec, null); return; }
    if (id === "all") { var a = overallSpan(); if (a) setWindow(sec, a); return; }
    var w = labWindowByKey(LAB_BOARD[sec], id);
    if (w) { var e = winEnds(w); setWindow(sec, { lo: e.lo, hi: e.hi }); }
  }
  // Picking a first season above the last pushes the other end with it, so an
  // inverted range is unreachable rather than validated after the fact. A window
  // of one season that IS the live season is Current, which keeps one state for
  // one board.
  function applyRangeSelect(spec, value) {
    var p = String(spec || "").split(":"), sec = p[0], which = p[1];
    var v = num(value);
    if (!LAB_BOARD[sec] || v == null) return;
    var live = sectionLiveSeason(sec);
    var cur = WIN[sec] || { lo: (live == null ? v : live), hi: (live == null ? v : live) };
    var lo = (which === "lo") ? v : cur.lo, hi = (which === "hi") ? v : cur.hi;
    if (lo > hi) { if (which === "lo") hi = lo; else lo = hi; }
    setWindow(sec, (lo === hi && live != null && lo === live) ? null : { lo: lo, hi: hi });
  }
  try { document.addEventListener("click", function (e) {
    var t = e.target && e.target.closest ? e.target : null;
    if (!t) return;
    var b = t.closest("[data-mlbrange]");
    if (b) { applyRange(b.getAttribute("data-mlbrange")); return; }
    var est = t.closest("[data-mlbest]");
    if (est) { winEstablished = !winEstablished; renderSection(est.getAttribute("data-mlbest")); return; }
    var x = t.closest("[data-mlbexpand]");
    if (x) { toggleSeasonRow(x.getAttribute("data-mlbexpand")); }
  }); } catch (e) { /* no document events */ }
  try { document.addEventListener("change", function (e) {
    var s = e.target && e.target.closest ? e.target.closest("[data-mlbrangesel]") : null;
    if (!s) return;
    applyRangeSelect(s.getAttribute("data-mlbrangesel"), s.value);
  }); } catch (e) { /* no document events */ }

  // ---- the window board ------------------------------------------------------
  function winLoading(txt) { return pxState("loading", esc(txt) + "&hellip;"); }
  function winFailed(sec, txt) {
    return pxState("failed", esc(txt)
      + " Refresh to retry; if it persists the nightly build is mid-run. "
      + '<button type="button" class="chip" data-mlbrange="' + esc(sec)
      + ':current">Back to Current</button>', "mlbstats-load-error");
  }
  // Returns "" when the window went away while this render was building it,
  // which is the caller's signal to render the season board instead. Nothing
  // downstream may assume WIN[sec] is still set: rangeControl starts the window
  // fetch, and the payload it waits for is what decides whether the span exists.
  function renderWindowBoard(sec) {
    var ctl = toolRow(rangeControl(sec), winColBoard(sec)) + winRefusedNote(sec);
    var win = WIN[sec];
    if (!win) return "";
    if (sec === "war") return ctl + renderOverallWindow(win);
    if (WINDOWS_ERROR) return ctl + winFailed(sec, "The year windows failed to load.");
    if (!WINDOWS) return ctl + winLoading("Loading the year windows");
    var w = labWindowFor(LAB_BOARD[sec], win.lo, win.hi);
    if (!w) return ctl + winRefusal(sec, win);
    if (WINDOW_ERROR[w.key]) return ctl + winFailed(sec, "The " + winSpan(win) + " board failed to load.");
    if (!WINDOW_DOC[w.key]) {
      loadWindowDoc(w, sec);
      return ctl + winLoading("Loading the " + winSpan(win) + " board");
    }
    return ctl + windowBoardBody(sec, w, WINDOW_DOC[w.key]);
  }
  // The one-line reason, and the two ways out. A board whose rates ship as
  // finished numbers with no counts behind them cannot pool an arbitrary window,
  // and an index on a window nobody computed would be a number on a scale that
  // does not exist. So the span is refused by name, the windows that DO exist are
  // offered as buttons, and the Overall board - every column of which is a count
  // - is offered for the exact span that was asked for.
  function winRefusal(sec, win) {
    var opts = labWindows(LAB_BOARD[sec]).map(function (w) {
      return '<button type="button" class="chip" data-mlbrange="' + esc(sec) + ":" + esc(w.key) + '">'
        + esc(w.name || "") + ' <span class="proj-dim">' + esc(winLabel(w)) + "</span></button>";
    }).join(" ");
    return '<div class="mlbstats-empty mlbstats-winrefusal">'
      + esc(winSpan(win)) + " is not a window this board can build. Its + indexes are standardised on"
      + " one season's pool, so a window index is a lab pass, and its season history ships finished"
      + " rates with no counts behind them, so nothing can be pooled over a span the lab did not build. "
      + (opts ? "Windows this board has: " + opts + " " : "")
      // A button, not an in-page link: readHash runs once, at init, so an
      // <a href="#section=..."> would change the URL and leave the reader on
      // the board that just refused him.
      + 'Every column on the Overall board is a count, so it sums over any span: '
      + '<button type="button" class="chip mlbx-goto" data-mlbgoto="war:'
      + esc(win.lo + "-" + win.hi) + '">Overall <span class="proj-dim">'
      + esc(win.lo + "-" + win.hi) + "</span></button> Or pick one season.</div>";
  }
  function windowRows(sec, doc) {
    var b = (doc.boards || {})[LAB_BOARD[sec]] || {};
    if (sec === "bullpen") return b.relievers || [];
    if (sec === "leverage") return (leverageView === "starters" ? b.starters : b.batters) || [];
    if (sec === "defense") return b.fielders || [];
    if (sec === "hitters") return b.hitters || [];
    if (sec === "starters") return b.starters || [];
    return [];
  }
  // The index the Established-only gate reads: the board's headline one, which
  // is the first index column the artifact declares.
  function primaryIndex(spec) {
    var keys = Object.keys((spec && spec.index) || {});
    return keys.length ? keys[0] : null;
  }
  // The clubs a row was produced for inside the window. A Current row carries one
  // club and no list; a window row carries every club it produced for, and the
  // filter, the search box, the select and the cell all read this one list
  // (owner decision D9: club of production on a window, not the club of the last
  // season). Filtering 2024-2026 by BOS used to lose a player who took 400 plate
  // appearances for BOS in 2024 and is filed under NYY.
  function rowClubs(r) {
    if (r.clubs && r.clubs.length) return r.clubs;
    return r.team ? [r.team] : [];
  }
  // The name a row shows. The substrate names the players on the CURRENT board
  // and leaves the rest blank; data/player_links.json closes part of the gap and
  // lands on its own schedule, so the fallback is resolved HERE, at render time,
  // rather than frozen into the fold cache by whichever fetch won the race. The
  // cell, the search box and the "no name" count all read this one function, so
  // the board cannot disclose a count it does not render.
  function rowName(r) {
    if (r.name) return r.name;
    return (r.mlbam != null) ? linkName(r.mlbam) : "";
  }
  function winMatch(sec, r, idxKey) {
    if (sectionQual(sec) && r.qualified === false) return false;
    var tm = sectionTeam(sec);
    if (tm && rowClubs(r).indexOf(tm) < 0) return false;
    if (winEstablished && idxKey && r[idxKey + "_tag"] === "provisional") return false;
    if (sec === "defense" && defensePos.length && defensePos.indexOf(r.pos) < 0) return false;
    var min = sectionMin(sec);
    if (min.key && !passesMin(r[min.key], min.val)) return false;
    var q = String(sectionQuery(sec) || "").trim().toLowerCase();
    if (!q) return true;
    // A row the substrate does not name is still addressable: the cell prints
    // its MLBAM id, so the search box matches that id too.
    var nm = rowName(r);
    return (nm.toLowerCase().indexOf(q) >= 0
      || rowClubs(r).join(" ").toLowerCase().indexOf(q) >= 0
      || (!nm && r.mlbam != null && String(r.mlbam).indexOf(q.replace(/^#/, "")) >= 0));
  }
  function cloneCol(c) {
    var out = {};
    for (var k in c) { if (Object.prototype.hasOwnProperty.call(c, k)) out[k] = c[k]; }
    return out;
  }
  // A count or a pooled rate keeps its cell and its formatter and states what was
  // done to it; the window rides its EXPORT label, so a range number cannot leave
  // the page under a single-season header.
  function windowCountCol(c, w, spec) {
    var out = cloneCol(c), lbl = winLabel(w);
    if (c.kind === "name") return out;          // a name is not a window number
    out.exportLabel = c.label + " " + lbl;
    out.vintage = null;
    var p = (spec.pool || {})[c.key], rc = (spec.recomposed || {})[c.key];
    out.title = p ? ("Pooled once over " + lbl + ": " + p.formula + ". Not the average of the seasons.")
      : rc ? ("Recomposed over " + lbl + ": " + rc + ".")
      : ("Summed over " + lbl + ".");
    if (p) {
      var base = c.cell || function (r) {
        return c.fmt ? c.fmt(getVal(c, r), c.term) : fInt(getVal(c, r));
      };
      // THE POOLED CELL CARRIES ITS OWN DENOMINATOR, and its own contributing
      // season count where the artifact ships one: a pitcher with three seasons
      // of innings but one season missing from a feed has his IP summed over
      // three and his ERA pooled over two, and one row-level Yrs cannot say
      // that. The numbers are the payload's, never inferred here.
      out.cell = function (r) {
        var body = base(r);
        var d = num((r.denoms || {})[p.denom]);
        if (d == null) return body;
        var ns = num(r[c.key + "_n"]), yrs = num(r.yrs);
        return '<span title="' + esc("Pooled over " + d + " " + p.denom + " in " + lbl
          + (ns != null ? ", from " + ns + (yrs != null ? " of " + yrs : "") + " seasons" : ""))
          + '">' + body + "</span>";
      };
    }
    return out;
  }
  // A window index: the span in the LABEL, the pool in the tooltip, and NO
  // ladder. It never routes through remCell / runCell / hemCell / vtCell, which
  // is the one move that would paint a cut measured on a one-season pool onto a
  // pool 12 to 18% narrower.
  // `how` is the lab's spec for this index: {formula, from, ...} on the served
  // window files, a bare sentence on older ones. The object used to be glued
  // into the sentence whole, so every served index header read
  // "2024-2026: [object Object], each season scored..." (census M06-06).
  // `built` is the window file's generated_at; `frozen` is true when the
  // Current board carries a frozen 3yr column over the same span, and `same`
  // when its 3yr column reads this window's own index (owner answer M17-2).
  function windowIndexCol(c, w, how, stats, built, frozen, same) {
    var out = cloneCol(c), lbl = winLabel(w);
    var howTxt = (how && typeof how === "object") ? (how.formula || "") : String(how || "");
    out.labelExtra = '<span class="mlbstats-winspan">' + esc(lbl) + "</span>";
    out.exportLabel = c.label + " " + lbl;
    out.vintage = null;
    out.isRem = false;
    out.title = lbl + ": " + (howTxt ? howTxt + ", " : "") + "each season scored against its own pool, so 100 is the average of"
      + " those pools and not of this window's"
      + (stats && stats.mean != null
          ? " - measured, this window's pool averages " + stats.mean
            + (stats.sd != null ? " with a standard deviation of " + stats.sd + " points" : "")
            + (stats.n != null ? " over " + stats.n + " rows" : "")
          : "")
      + ". No value ruler is carried onto a window, so the column is uncoloured."
      + " p = percentile inside this window's pool; * = provisional."
      + (built ? " Built " + built + " by the window lab." : "")
      + (frozen ? " The Current board's frozen 3yr column is a separate, dated build of the same"
        + " recipe, so the two can differ by a few points." : "")
      + (same ? " The Current board's 3yr column reads this index, so the two print one number." : "");
    out.cell = function (r) {
      var v = num(r[c.key]);
      if (v == null) return EM_DASH;
      // NOT .rem-plus: that class is cursor:help, and the explanation is on the
      // header, not on the cell. A help cursor over nothing is an affordance
      // that lies.
      var s = '<span class="mlbstats-winidx">' + fInt(v) + "</span>";
      var p = num(r[c.key + "_pct"]);
      if (p != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(p) + "</span>";
      if (r[c.key + "_tag"] === "provisional") {
        s += '<span class="proj-dim" title="Provisional: fewer contributing seasons or less denominator'
          + ' than this window asks for">*</span>';
      }
      return s;
    };
    return out;
  }
  // THE CURRENT BOARD'S 3yr COLUMNS ARE A WINDOW INDEX (owner answer M17-2,
  // census M06-06): the exporters read HEM+ / SEM+ / REM+ / DEM+ 3yr from the
  // Last 3 window file, so the cell prints the way windowIndexCol does: the
  // numeral with no band (the ruler was cut on a one-season pool), the window
  // pool's percentile, and the provisional star with the owning lab's floor.
  function win3yrCell(r, key, floor) {
    var v = num(r[key]);
    if (v == null) return "";
    var s = '<span class="mlbstats-winidx">' + fInt(v) + "</span>";
    var p = num(r[key + "_pct"]);
    if (p != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(p) + "</span>";
    if (r[key + "_tag"] === "provisional") {
      s += '<span class="proj-dim" title="Provisional: ' + floor + ' in the trailing window">*</span>';
    }
    return s;
  }
  // Every column key this window's payload can fill. The board's own column
  // array MINUS this set is exactly what the window drops, which is why the
  // note is built from it rather than from spec.hidden: a column the lab
  // classified nowhere disappeared silently under a sentence that claimed to
  // name everything that went.
  function winAllow(spec) {
    var allow = { name: 1, pos: 1 };
    (spec.sum || []).forEach(function (k) { allow[k] = 1; });
    Object.keys(spec.pool || {}).forEach(function (k) { allow[k] = 1; });
    Object.keys(spec.recomposed || {}).forEach(function (k) { allow[k] = 1; });
    Object.keys(spec.index || {}).forEach(function (k) { allow[k] = 1; });
    if (allow.sd && allow.md) allow.sd_md = 1;      // one column over two counts
    return allow;
  }
  function windowCols(sec, w, doc, spec) {
    var allow = winAllow(spec), idx = spec.index || {};
    var ends = winEnds(w), spans3 = ends.hi - ends.lo === 2, keys = {};
    sectionCols(sec).forEach(function (c) { keys[c.key] = 1; });
    var pool = ((doc.pool_stats || {})[LAB_BOARD[sec]]) || {};
    // Does the Current board's 3yr column read THIS window (a `multiyear` block
    // of kind "window", served since M17-2) or a frozen lab artifact?
    var lm = (sectionLive(sec) || {}).multiyear;
    var same = !!(lm && lm.kind === "window" && lm.window_key === (doc.window || {}).key);
    var out = [];
    sectionCols(sec).forEach(function (c) {
      if (!allow[c.key]) return;
      var has3 = spans3 && !!keys[c.key + "_3yr"];
      out.push(idx[c.key] ? windowIndexCol(c, w, idx[c.key], pool[c.key], doc.generated_at || null,
                                           has3 && !same, has3 && same)
                          : windowCountCol(c, w, spec));
    });
    return out;
  }
  // The live payload behind a section's Current board.
  function sectionLive(sec) {
    if (sec === "starters") return starterData;
    if (sec === "hitters") return hitterData;
    if (sec === "defense") return defenseData;
    if (sec === "bullpen") return DATA;
    return null;
  }
  // A sort key the window board does not carry falls back to the board's own
  // first numeric column, the rule readSort has always applied to a stale link.
  function windowSort(sec, cols) {
    var s = sectionSort(sec), ok = false, fall = null;
    cols.forEach(function (c) {
      if (c.key === s.key) ok = true;
      if (!fall && c.num) fall = c;
    });
    return ok ? s : { key: fall ? fall.key : "name", asc: false };
  }
  // A column the lab classified in no family at all. It is still NAMED: the
  // note's promise is that everything the board serves and this window does not
  // is listed, and "the lab has no opinion on it" is a reason a reader can act
  // on, where silence is not.
  var UNCLASSIFIED_COL = "The lab does not classify this column on a window, so it is off rather than"
    + " printed on a basis nobody chose.";
  // The dropped list is the board's OWN column array minus the keys this
  // window's payload can fill, so a column added to either side is named here
  // by existing. The reason is the artifact's where it has one.
  function droppedCols(sec, spec) {
    var allow = winAllow(spec), hidden = spec.hidden || {}, seen = {}, out = [];
    sectionCols(sec).forEach(function (c) {
      if (allow[c.key] || seen[c.key] || c.kind === "name") return;
      seen[c.key] = 1;
      out.push('<span title="' + esc(hidden[c.key] || UNCLASSIFIED_COL) + '">' + esc(c.label) + "</span>");
    });
    return out.join(", ");
  }
  // The label a column carries on the board, so a sentence can name one.
  function colLabel(sec, key) {
    var lbl = key;
    sectionCols(sec).forEach(function (c) { if (c.key === key) lbl = c.label; });
    return lbl;
  }
  // What this window's pool ACTUALLY is, from the payload's pool_stats. It goes
  // in the note and not only in a column tooltip: a phone has no hover, and this
  // is the one sentence that says what the scale under the numerals is.
  function poolStatsLine(sec, doc, idxKey) {
    var s = (((doc.pool_stats || {})[LAB_BOARD[sec]]) || {})[idxKey];
    if (!s || s.mean == null) return "";
    return "Measured on this window, the " + esc(colLabel(sec, idxKey)) + " pool averages " + s.mean
      + (s.sd != null ? " with a standard deviation of " + s.sd + " points" : "")
      + (s.n != null ? " over " + s.n + " rows" : "")
      + ", so ten points here is not one standard deviation of it.";
  }
  // The note is a DETAILS: one line of summary and the rest a tap away. Measured
  // at 390x844, the open note put the first row of every window board below the
  // fold (table top y 781 to 802 against an 844px screen), which is the board
  // itself off the first screen. The repo already closes the methodology fold
  // and the Team note the same way, so this is the page's own pattern and not a
  // new one. The Established-only control rides OUTSIDE it: a filter that
  // changes the rows cannot hide inside a collapsed note.
  function winNoteShell(head, bits, tail) {
    return '<div class="mlbstats-winhead">'
      + '<details class="mlbstats-note mlbstats-winnote"><summary>' + head
      + ' <span class="mlbx-more">What this window did</span></summary>'
      + '<div class="mlbx-notebody">' + bits.join(" ") + "</div></details>" + (tail || "") + "</div>";
  }
  // 2020 and the season still being played, one mechanism and no typed number:
  // season_share is that season's league eWAR over the mean of the last three
  // complete seasons, published by the exporter and read here.
  function shortSeasons(doc, seasons) {
    var share = (doc && doc.season_share) || (SEASONS && SEASONS.season_share) || null;
    if (!share) return [];
    var live = num(doc && doc.live_season);
    if (live == null) live = num(WINDOWS && WINDOWS.live_season);
    var out = [];
    (seasons || []).forEach(function (y) {
      var v = num(share[String(y)]);
      if (v == null || v >= 0.98) return;
      var pct = Math.round(v * 100);
      out.push(y === live
        ? y + " is still being played and has produced " + pct + "% of a normal season so far."
        : y + " is inside this window and produced " + pct + "% of a normal season.");
    });
    return out;
  }
  // What the page says on a window, every number of it off the payload.
  function windowNote(sec, w, doc, spec, shown, rows, idxKey) {
    var lbl = winLabel(w), n = (w.seasons || []).length;
    var bits = [];
    bits.push("Counts are summed over the window. Rates are pooled once, numerator over denominator,"
      + " never an average of the seasons.");
    if (idxKey) {
      bits.push("The " + gloss("+ indexes", "range") + " are the window the lab computed: each season"
        + " scored against its own pool, weighted by its own denominator. So 100 is the average of"
        + " those pools and not of this window's, and no colour ladder is carried onto them.");
      var ps = poolStatsLine(sec, doc, idxKey);
      if (ps) bits.push(ps);
    }
    bits.push("Club is every club of production inside the window; the cell shows the last one, the name"
      + " tooltip lists the rest, and the club filter and the search box match any of them.");
    var mn = sectionMin(sec);
    if (mn.key) {
      bits.push("The min " + esc(MIN_LABEL[mn.key] || mn.key) + " floor applies to the window total,"
        + " not to a season.");
    }
    var qr = ((doc.qualified_rule_window || {})[LAB_BOARD[sec]] || {}).rule;
    if (qr) bits.push("Qualified: " + esc(qr) + ".");
    shortSeasons(doc, w.seasons).forEach(function (s) { bits.push(esc(s)); });
    var ends = winEnds(w);
    var ex = (doc.excluded_seasons || []).filter(function (y) {
      return y >= ends.lo && y <= ends.hi && w.seasons.indexOf(y) < 0;
    });
    if (ex.length) {
      bits.push("The index labs exclude " + esc(ex.join(", ")) + ", so this window is " + n
        + " played seasons inside " + esc(lbl) + ".");
    }
    var dropped = droppedCols(sec, spec);
    if (dropped) bits.push("<b>Off on this window:</b> " + dropped + ".");
    var est = idxKey
      ? ' <button type="button" class="chip mlbx-est' + (winEstablished ? " active" : "")
        + '" data-mlbest="' + esc(sec) + '" aria-pressed="'
        + winEstablished + '" title="' + esc("A row tagged provisional has fewer contributing seasons"
          + " or less denominator than this window asks for. Measured on the served window, 40% of the"
          + " rows are provisional and they reach the top 25, which is what a denominator-weighted mean"
          + " does with a partial window.") + '">Established only '
        + (winEstablished ? "on" : "off") + "</button>"
      : "";
    var head = "<b>" + esc(lbl) + ", " + n + (n === 1 ? " season" : " seasons") + ".</b> Counts summed,"
      + " rates pooled once" + (idxKey ? ", + indexes uncoloured" : "") + "."
      + ' <span class="proj-dim">' + rows.length + " of " + shown.length + " rows shown.</span>";
    return winNoteShell(head, bits, est);
  }
  function windowBoardBody(sec, w, doc) {
    var spec = (doc.columns || {})[LAB_BOARD[sec]] || {};
    var cols = windowCols(sec, w, doc, spec);
    var idxKey = primaryIndex(spec);
    var all = windowRows(sec, doc);
    var rows = all.filter(function (r) { return winMatch(sec, r, idxKey); });
    var sort = windowSort(sec, cols);
    rows = sortRows(rows, cols, sort);
    var note = windowNote(sec, w, doc, spec, all, rows, idxKey);
    if (!rows.length) return note + noRowsNote(sectionTeam(sec), "No rows match the current filters.");
    return note + '<div class="mlbstats-scroll">'
      + renderTable(rows, cols, sort, doc, winColBoard(sec)) + "</div>";
  }

  // The rows a shareable card gets on a window board: the SAME fold, the same
  // matcher and the same sort as the table, so a card cannot carry a different
  // set of rows from the board it was generated off. An empty list when the
  // window payload has not landed, which the card module renders as no card
  // rather than as the live season's rows.
  function windowGfxRows(sec) {
    var win = WIN[sec];
    var w = win && labWindowFor(LAB_BOARD[sec], win.lo, win.hi);
    var doc = w && WINDOW_DOC[w.key];
    if (!doc) return [];
    var spec = (doc.columns || {})[LAB_BOARD[sec]] || {};
    var cols = windowCols(sec, w, doc, spec), idx = primaryIndex(spec);
    return sortRows(windowRows(sec, doc).filter(function (r) { return winMatch(sec, r, idx); }),
                    cols, windowSort(sec, cols));
  }
  // One clause on the card itself, because a card outlives the page it came
  // from: the subtitle says which window, this says what a window did to the
  // numbers under it.
  function winCardNote(sec) {
    return isWindow(sec)
      ? " \u00b7 " + winSpan(WIN[sec]) + ": counts summed, rates pooled once, and each + index"
        + " the denominator-weighted mean of the per-season index on its own pool"
      : "";
  }

  // ---- the Overall fold ------------------------------------------------------
  // One pass over data/war_seasons.json: counts add, the two eWAR sides sum
  // UNROUNDED and round once (the board's own rule over one season), and a
  // denominator a season does not carry contributes nothing rather than a zero.
  // The per-season lines come back WITH the total, so the expander under a row
  // cannot disagree with the number above it.
  function fieldIndex(fields) {
    var idx = {};
    (fields || []).forEach(function (f, i) { idx[f] = i; });
    return idx;
  }
  function foldSeasons(lo, hi) {
    var ck = lo + "-" + hi;
    if (FOLD_CACHE[ck]) return FOLD_CACHE[ck];
    var idx = fieldIndex(SEASONS.fields), tms = SEASONS.tm || [], poss = SEASONS.pos || [];
    var players = SEASONS.players || {}, out = [], nameless = 0;
    var lg = { war: 0, war_bat: 0, war_pit: 0 };
    var rule = SEASONS.qualified_rule_window || {};
    Object.keys(players).forEach(function (mid) {
      var ent = players[mid], lines = ent && ent[1];
      if (!lines || !lines.length) return;
      var bat = null, pit = null, pa = null, ip = null, g = null, gs = null;
      var yrs = 0, last = null, age = null, pos = null, team = null, clubs = [], seasons = [];
      lines.forEach(function (r) {
        var y = num(r[idx.season]);
        if (y == null || y < lo || y > hi) return;
        yrs++;
        var b = num(r[idx.war_bat]), p = num(r[idx.war_pit]);
        var rpa = num(r[idx.pa]), rip = num(r[idx.ip]);
        var rg = num(r[idx.g]), rgs = num(r[idx.gs]);
        if (b != null) bat = (bat || 0) + b;
        if (p != null) pit = (pit || 0) + p;
        if (rpa != null) pa = (pa || 0) + rpa;
        if (rip != null) ip = (ip || 0) + rip;
        if (rg != null) g = (g || 0) + rg;
        if (rgs != null) gs = (gs || 0) + rgs;
        var tm = tms[r[idx.tm]] || "";
        String(tm).split("/").forEach(function (c) { if (c && clubs.indexOf(c) < 0) clubs.push(c); });
        if (last == null || y >= last) {
          last = y;
          age = num(r[idx.age]);
          pos = poss[r[idx.pos]] || null;
          team = String(tm).split("/").pop() || null;
        }
        seasons.push({ season: y, team: tm, war: round1((b || 0) + (p || 0)),
                       war_bat: b == null ? null : round1(b),
                       war_pit: p == null ? null : round1(p),
                       pa: rpa, ip: rip, g: rg, gs: rgs });
      });
      if (!yrs) return;
      var nm = ent[0] || linkName(mid) || "";
      if (!nm) nameless++;
      seasons.sort(function (a, b2) { return b2.season - a.season; });
      var row = { mlbam: num(mid), name: nm, team: team, pos: pos, age: age,
        war: round1((bat || 0) + (pit || 0)),
        war_bat: bat == null ? null : round1(bat),
        war_pit: pit == null ? null : round1(pit),
        pa: pa, ip: ip, g: g, gs: gs, yrs: yrs, clubs: clubs, seasons: seasons,
        bat_600: (bat != null && pa) ? (bat / pa) * 600 : null,
        pitch_200: (pit != null && ip) ? (pit / ip) * 200 : null };
      row.qualified = !!((rule.min_pa != null && pa != null && pa >= rule.min_pa)
                      || (rule.min_ip != null && ip != null && ip >= rule.min_ip));
      lg.war += (bat || 0) + (pit || 0);
      lg.war_bat += (bat || 0);
      lg.war_pit += (pit || 0);
      out.push(row);
    });
    var fold = { players: out, nameless: nameless, seasons: [],
      league: { war: round1(lg.war), war_bat: round1(lg.war_bat),
                war_pit: round1(lg.war_pit), n: out.length } };
    for (var y2 = lo; y2 <= hi; y2++) {
      if ((SEASONS.seasons || []).indexOf(y2) >= 0) fold.seasons.push(y2);
    }
    FOLD_CACHE[ck] = fold;
    return fold;
  }
  // The substrate names the players the CURRENT board names and leaves the rest
  // blank, so a window reaching back past today's rosters loses names the fold
  // still has numbers for. The player-links map closes part of the gap; what it
  // does not close is stated ON the board rather than hidden, and the sentence
  // disappears by itself when the exporter fills the field.
  function linkName(mid) {
    try {
      var hit = LINKS && LINKS.byMlbam && LINKS.byMlbam[String(mid)];
      return (hit && hit.name) || "";
    } catch (e) { return ""; }
  }
  function renderOverallWindow(win) {
    if (SEASONS_ERROR) return winFailed("war", "The per-season eWAR substrate failed to load.");
    if (!SEASONS) { loadSeasons("war"); return winLoading("Loading every season"); }
    var fold = foldSeasons(win.lo, win.hi);
    var cols = warCols();
    var rows = fold.players.filter(function (r) { return winMatch("war", r, null); });
    var sort = windowSort("war", cols);
    rows = sortRows(rows, cols, sort);
    var note = overallWindowNote(win, fold, rows);
    if (!rows.length) return note + noRowsNote(warTeam, "No players match the current filters.");
    return note + '<div class="mlbstats-scroll">'
      + renderTable(rows, cols, sort, warData, "war", warTableOpts()) + "</div>";
  }
  // Why each Overall column goes on a window. `boards` is a fact about the five
  // boards served TODAY; Yrs and Clubs are facts about a span, so one season has
  // nothing for them to say.
  var WAR_WIN_DROP = {
    boards: "The five role boards this player is on TODAY. A window has no per-season answer on disk,"
      + " so the column is off rather than answered for the wrong date.",
    yrs: "One season is not a span, so there is nothing to count.",
    clubs: "One season is not a span; the club cell already names it."
  };
  // The same promise the lab boards make, kept by the same means: the board's own
  // column array minus what is on screen. "Nothing is hidden" was false the
  // moment a window opened, because Also on goes on every window and Yrs and
  // Clubs go on a single season.
  function overallDropped() {
    var keep = {}, out = [];
    warCols().forEach(function (c) { keep[c.key] = 1; });
    WAR_COLS.forEach(function (c) {
      if (keep[c.key]) return;
      out.push('<span title="' + esc(WAR_WIN_DROP[c.key] || UNCLASSIFIED_COL) + '">'
        + esc(c.label) + "</span>");
    });
    return out.join(", ");
  }
  function overallWindowNote(win, fold, rows) {
    var nameless = 0;
    rows.forEach(function (r) { if (!rowName(r)) nameless++; });
    var n = fold.seasons.length, lbl = winSpan(win);
    var bits = [];
    bits.push("Every column here is a count summed over the window, or one of those counts over its own"
      + " denominator. Nothing on this board is an index, so no ladder and no colour is carried onto"
      + " one.");
    bits.push("Club is every club of production inside the window; the cell shows the last one, the name"
      + " tooltip lists the rest, and the club filter and the search box match any of them.");
    var rule = SEASONS.qualified_rule_window || {};
    if (rule.min_pa != null || rule.min_ip != null) {
      var f = [];
      if (rule.min_pa != null) f.push(rule.min_pa + " plate appearances");
      if (rule.min_ip != null) f.push(rule.min_ip + " innings");
      bits.push("Qualified: " + f.join(" or ") + " over the whole window. On a long window this filter"
        + " removes very little, because a small sample makes a small total anyway.");
    }
    shortSeasons({ season_share: SEASONS.season_share, live_season: sectionLiveSeason("war") },
                 fold.seasons).forEach(function (s) { bits.push(esc(s)); });
    var dropped = overallDropped();
    if (dropped) bits.push("<b>Off on this window:</b> " + dropped + ".");
    if (nameless) {
      bits.push("<b>" + nameless + " of " + rows.length + " rows carry no name:</b> the per-season"
        + " substrate names the players on the current board and leaves the rest blank, so a window"
        + " reaching back past today's rosters loses names it still has numbers for. Those rows print"
        + " the player's MLBAM id instead, which the search box matches, and the names return by"
        + " themselves when the exporter fills the field.");
    }
    bits.push("League eWAR over this window: " + fold.league.war + " from " + fold.league.n
      + " players.");
    var head = "<b>" + esc(lbl) + ", " + n + (n === 1 ? " season" : " seasons") + ".</b> Every column is"
      + " a count summed over it, or a count over its own denominator."
      + ' <span class="proj-dim">' + rows.length + " of " + fold.players.length + " rows shown.</span>";
    return winNoteShell(head, bits, "");
  }

  // ---- the per-season expander ----------------------------------------------
  // The line behind the total, rendered FROM THE SAME FOLD, so the explanation
  // cannot disagree with the number above it. No hash key: an expanded row is a
  // glance, not a page state.
  var warOpen = {};
  // The board is rebuilt on every toggle, so a caret written in its new state
  // never runs its .12s turn (site.css). The toggled row's caret is written in
  // the state it had (aria-expanded already says the new one), the style is
  // flushed, and only then is it flipped, so that one caret turns on open and
  // on close and no other caret moves.
  var warCaretFrom = null;
  function toggleSeasonRow(id) {
    if (!id) return;
    var was = !!warOpen[id];
    if (was) delete warOpen[id]; else warOpen[id] = 1;
    warCaretFrom = { id: id, open: was };
    try { renderWar(); } finally { warCaretFrom = null; }
    var root = document.getElementById("mlbstats-war-root");
    var carets = root ? root.querySelectorAll(".mlbx-caret[data-mlbexpand]") : [];
    var back = null;
    for (var i = 0; i < carets.length; i++) {
      var c = carets[i];
      if (c.getAttribute("data-mlbexpand") !== id) continue;
      void c.offsetWidth;
      c.classList.toggle("is-open", !was);
      c.setAttribute("aria-expanded", String(!was));
      if (!back) back = c;
    }
    // The render replaced the button the reader pressed, so focus fell to
    // <body> and the next Tab went to Download CSV above the board (QMLA05).
    // Put it back on the same row's caret, as bindSortKeys does for a header.
    if (back) { try { back.focus({ preventScroll: true }); } catch (e) { back.focus(); } }
  }
  function warTableOpts() {
    return {
      nameExtra: function (r) {
        if (!r.seasons || !r.seasons.length) return "";
        var open = !!warOpen[String(r.mlbam)];
        var drawn = (warCaretFrom && warCaretFrom.id === String(r.mlbam)) ? warCaretFrom.open : open;
        return '<button type="button" class="mlbx-caret' + (drawn ? " is-open" : "")
          + '" data-mlbexpand="' + esc(String(r.mlbam)) + '" aria-expanded="' + open
          + '" aria-label="Season by season" title="Season by season" data-export-skip></button>';
      },
      child: function (r, n) {
        if (!r.seasons || !warOpen[String(r.mlbam)]) return "";
        // What the lines PRINT, added up. Each one rounds to a tenth and the
        // total rounds once over the whole window, so on a long window they
        // genuinely do not add up, and the cell says what they add to rather
        // than asserting a bound that only holds over three seasons.
        var printed = 0;
        r.seasons.forEach(function (s) { printed += (s.war == null ? 0 : s.war); });
        printed = round1(printed);
        var cells = r.seasons.map(function (s) {
          var side = [];
          if (s.war_bat != null) side.push("bat " + f1(s.war_bat));
          if (s.war_pit != null) side.push("pitch " + f1(s.war_pit));
          if (s.pa != null) side.push(fInt(s.pa) + " PA");
          if (s.ip != null) side.push(f1(s.ip) + " IP");
          if (s.g != null) side.push(fInt(s.g) + " G");
          return '<span class="mlbx-season"><b>' + s.season + '</b> <span class="proj-dim">'
            + esc(s.team || EM_DASH) + "</span> <b>" + f1(s.war) + '</b> <span class="proj-dim">'
            + esc(side.join(" · ")) + "</span></span>";
        }).join("");
        return '<tr class="mlbx-seasonrow" data-export-skip><td colspan="' + n
          + '" data-export-skip><span class="mlbx-seasons">' + cells
          + '<span class="mlbx-season mlbx-season-total" title="'
          + esc("Each season line rounds to a tenth; the total sums the two unrounded sides over the"
                + " whole window and rounds once, so the lines need not add to it exactly. These lines"
                + " add to " + f1(printed) + ".")
          + '"><b>Total</b> <b>' + f1(r.war) + "</b></span></span></td></tr>";
      }
    };
  }

  // ---- frozen-vintage disclosure --------------------------------------------
  // Several columns are NOT computed by the run that built the board: the
  // trailing-window ones are read verbatim from frozen lab artifacts, so their
  // numbers are as of the artifact's generated_at, not the board's as_of. The
  // exporters have always passed that divergence down deliberately (see the
  // docstring on bullpen_export._join_rem_plus_3yr, which says in as many words
  // that it "returns the artifact's vintage block ... for the payload to carry
  // and the frontend to disclose"), and the frontend has never once read it.
  // A 3-year column three weeks stale beside a same-day 1-year column, with no
  // date on either, is the whole reason those blocks exist.
  //
  // Payload key paths, confirmed against the served files:
  //   <payload>.multiyear            -> REM+ 3yr / SEM+ 3yr / HEM+ 3yr / DEM+ 3yr
  //                                     (kind "window" since M17-2: the Last 3
  //                                     window's index, not a frozen artifact)
  //   <payload>.multiyear_war_rate   -> WAR/IP+ 3yr / WAR/PA+ 3yr
  // Each block carries { available, source, generated_at, season, window,
  // n_stamped, n_in_artifact, note }. gmLI 3yr is frozen the same way (from
  // leverage_consistency_eval.json) but its join stamps NO vintage block, so
  // nothing here can date it and nothing here pretends to.
  function vintageOf(meta, key) {
    var b = meta && meta[key];
    return (b && b.available && b.generated_at) ? b : null;
  }
  function vintageWindow(b) {
    var w = b && b.window;
    return (w && w.length >= 2) ? (w[0] + "-" + w[w.length - 1]) : "";
  }
  // Column-tooltip sentence, appended after whatever `title` the column already
  // carries.
  function vintageTitle(b) {
    if (!b) return "";
    var w = vintageWindow(b);
    if (b.kind === "window") {
      return "LAST 3 WINDOW: read from " + (b.source || "the window lab") + ", built " + b.generated_at
        + (w ? ", " + w : "") + (b.panel_built_at && b.season != null
          ? ", " + b.season + " through " + b.panel_built_at : "")
        + "; the value the Last 3 view prints. Uncoloured: no value ruler travels onto a"
        + " window pool. p = percentile inside that pool. Blank for anyone the window does not publish.";
    }
    return "FROZEN: read from " + (b.source || "a lab artifact") + ", generated " + b.generated_at
      + (w ? ", " + w : "") + "; as of that date, not this board's. Blank for anyone who joined"
      + " the pool since.";
  }
  // THE eWAR BUILD STAMP (war_source.ewar_vintage, on all three pitching and
  // hitting payloads since 2026-09-10). The live season rebuilds nightly since
  // 2026-09-11; when a night is missed or refused this season's eWAR numerator
  // can trail the IP or PA beside it. The page reads `stale`, the build date and
  // `rebuilds_on_a_schedule`; it never types any of them.
  function ewarVintage(meta) {
    var v = meta && meta.ewar_vintage;
    return (v && v.stale === true && v.artifact_generated_at) ? v : null;
  }
  function ewarTitle(meta) {
    var v = ewarVintage(meta);
    return v ? "eWAR built " + String(v.artifact_generated_at).slice(0, 10)
      + (v.rebuilds_on_a_schedule === true ? " and behind its nightly rebuild"
         : " and not rebuilt nightly")
      + ", so this season's value can trail the line beside it." : "";
  }
  // Compact board note. `cols` is [[payload key, column label], ...]; a block
  // that is absent or unavailable simply contributes nothing.
  // A `multiyear` block of kind "window" (served since owner answer M17-2) is
  // the Last 3 window's index, not a frozen artifact, and says so; an older
  // payload without the kind keeps the frozen sentence it always had.
  function vintageNote(meta, cols, extra) {
    var bits = [], wins = [], frozen3 = false;
    (cols || []).forEach(function (p) {
      var b = vintageOf(meta, p[0]);
      if (!b) return;
      var w = vintageWindow(b);
      if (b.kind === "window") {
        wins.push(esc(p[1]) + " is the Last 3 index" + (w ? " (" + esc(w) + ")" : "")
          + ", built " + esc(b.generated_at)
          + (b.panel_built_at && b.season != null
            ? ", " + esc(b.season) + " through " + esc(b.panel_built_at) : ""));
        return;
      }
      if (p[0] === "multiyear") frozen3 = true;
      bits.push(esc(p[1]) + " as of " + esc(b.generated_at) + (w ? " (" + esc(w) + ")" : ""));
    });
    var ew = ewarTitle(meta);
    if (!bits.length && !wins.length && !ew) return "";
    var parts = [];
    if (wins.length) {
      parts.push("<b>Window columns</b>: " + wins.join(", ") + ". The same value the Last 3 view"
        + " prints, uncoloured because no value ruler travels onto a window pool; p is the"
        + " percentile inside that pool.");
    }
    if (bits.length) {
      parts.push("<b>Frozen columns</b> (lab artifacts, not recomputed; blank for anyone who"
        + " joined the pool later): " + bits.join(", ") + "." + (extra || "")
        + (frozen3 ? " The Last 3 window recomputes the same 3-year recipe on its own build, dated in that"
          + " view's stamp, so a player's 3yr value here and his Last 3 index can differ by a few points." : ""));
    }
    if (ew) parts.push(esc(ew));
    return '<div class="mlbstats-note mlbstats-vintage">' + parts.join(" ") + "</div>";
  }

  // ---- board paging (site pass, 2026-10-02) ----------------------------------
  // Overall printed all 928 rows on one page: 30,765 px tall at 1280 and 51,967
  // px at 390. A board of more than 50 rows now pages, 100 rows by default, with
  // a 50 / 100 / 250 / All select and a status line. Every row the filters match
  // is still IN the table and the off-page rows carry `hidden`, so the browser
  // lays out one page (the render cost that grew with the board, QMLP05, now
  // grows with the page), a page turn is an attribute flip rather than a
  // render, and Download CSV still writes every matching row: its count says
  // so, and its click shows the hidden rows for the one synchronous scrape.
  // A new row set (a sort, a filter, a view) opens on the first page; a render
  // of the same rows (a season line opened, a payload landing) keeps the page.
  var PAGE_SIZES = [50, 100, 250, 0];
  var PAGE_MIN = 50;
  var pageSize = 100;
  try {
    var savedSize = window.localStorage.getItem("mlbstats.pagesize");
    if (savedSize != null && PAGE_SIZES.indexOf(Number(savedSize)) >= 0) pageSize = Number(savedSize);
  } catch (e) { /* per-viewer convenience only */ }
  var PAGE_AT = {};
  function rowId(r) { return r ? (r.mlbam != null ? r.mlbam : (r.team || r.name || "")) : ""; }
  function pageState(key) { return PAGE_AT[key] || (PAGE_AT[key] = { sig: "", start: 0 }); }
  function pageSpan(key, total) {
    var start = pageSize ? Math.min(pageState(key).start, Math.max(0, total - 1)) : 0;
    return { start: start, end: pageSize ? Math.min(total, start + pageSize) : total, total: total };
  }
  function pagerText(s) { return "Rows " + (s.total ? s.start + 1 : 0) + " to " + s.end + " of " + s.total; }
  function pagerHTML(key, total) {
    var s = pageSpan(key, total);
    return '<div class="mlbx-pager" data-mlbpager="' + esc(key) + '">'
      + '<span class="mlbx-pager-n" role="status">' + pagerText(s) + "</span>"
      + '<button type="button" class="chip" data-mlbpage-step="-1" aria-label="Previous rows"'
      + (s.start <= 0 ? " disabled" : "") + ">Prev</button>"
      + '<button type="button" class="chip" data-mlbpage-step="1" aria-label="Next rows"'
      + (s.end >= total ? " disabled" : "") + ">Next</button>"
      + '<label class="mlbstats-ctl">Rows <select class="eephus-select" data-mlbpage-size'
      + ' aria-label="Rows per page">' + PAGE_SIZES.map(function (n) {
          return '<option value="' + n + '"' + (n === pageSize ? " selected" : "") + ">" + (n || "All") + "</option>";
        }).join("") + "</select></label></div>";
  }
  // The pager sits under the table's scroll box, outside it, so it never
  // scrolls sideways with a wide board. Every render path ends in
  // wireGlossary, which calls this.
  function mountPagers(el) {
    try {
      (el || document).querySelectorAll("table[data-mlbpage]").forEach(function (t) {
        var box = t.closest(".mlbstats-scroll") || t;
        var nx = box.nextElementSibling;
        if (nx && nx.classList.contains("mlbx-pager")) nx.parentNode.removeChild(nx);
        box.insertAdjacentHTML("afterend", pagerHTML(t.getAttribute("data-mlbpage"),
          Number(t.getAttribute("data-mlbpage-total"))));
      });
    } catch (e) { /* paging optional */ }
  }
  // The CSV button's own title says it downloads the rows on screen. On a paged
  // board it writes every row the filters match, so it says that instead.
  function csvTitles(el) {
    try {
      (el || document).querySelectorAll("table[data-mlbpage]").forEach(function (t) {
        var host = t.closest("[data-csv-export]");
        var csv = host && host.querySelector(":scope > .eph-csv-bar .eph-csv-btn");
        if (csv) csv.title = "Downloads every row the filters match, in the order shown, not only this page.";
      });
    } catch (e) { /* export control optional */ }
  }
  function pagerTable(pg) {
    var box = pg && pg.previousElementSibling;
    if (!box) return null;
    return box.matches("table[data-mlbpage]") ? box : box.querySelector("table[data-mlbpage]");
  }
  function applyPage(t, pg) {
    var key = t.getAttribute("data-mlbpage"), s = pageSpan(key, Number(t.getAttribute("data-mlbpage-total")));
    var trs = t.tBodies.length ? t.tBodies[0].rows : [];
    if (t.tBodies.length) t.tBodies[0].style.counterReset = s.start ? "mlbx-rank " + s.start : "";
    for (var i = 0; i < trs.length; i++) {
      var k = Number(trs[i].getAttribute("data-mlbi"));
      trs[i].hidden = !(k >= s.start && k < s.end);
    }
    if (pg) {
      var n = pg.querySelector(".mlbx-pager-n");
      if (n) n.textContent = pagerText(s);
      var prev = pg.querySelector('[data-mlbpage-step="-1"]'), next = pg.querySelector('[data-mlbpage-step="1"]');
      var had = document.activeElement;
      if (prev) prev.disabled = s.start <= 0;
      if (next) next.disabled = s.end >= s.total;
      // A button that just went disabled drops focus to <body>; hand it to
      // the other one so a keyboard reader stays in the pager.
      if (had === next && next.disabled && prev && !prev.disabled) prev.focus();
      else if (had === prev && prev.disabled && next && !next.disabled) next.focus();
    }
    scheduleFit(t.closest(".mlbstats-section") || t);
  }
  try { document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest("[data-mlbpage-step]") : null;
    if (!b || !pageSize) return;
    var pg = b.closest(".mlbx-pager"), t = pagerTable(pg);
    if (!t) return;
    var key = t.getAttribute("data-mlbpage"), total = Number(t.getAttribute("data-mlbpage-total"));
    var st = pageState(key);
    st.start = Math.max(0, Math.min(st.start + Number(b.getAttribute("data-mlbpage-step")) * pageSize,
      Math.floor((total - 1) / pageSize) * pageSize));
    applyPage(t, pg);
    var top = (t.closest(".mlbstats-scroll") || t).getBoundingClientRect().top;
    if (top < 0) (t.closest(".mlbstats-scroll") || t).scrollIntoView({ block: "start" });
  }); } catch (e) { /* no document events */ }
  try { document.addEventListener("change", function (e) {
    var sel = e.target && e.target.closest ? e.target.closest("[data-mlbpage-size]") : null;
    if (!sel) return;
    var v = Number(sel.value);
    if (PAGE_SIZES.indexOf(v) < 0) return;
    pageSize = v;
    try { window.localStorage.setItem("mlbstats.pagesize", String(v)); } catch (err) { /* optional */ }
    var pg = sel.closest(".mlbx-pager"), t = pagerTable(pg);
    if (!t) return;
    var st = pageState(t.getAttribute("data-mlbpage"));
    st.start = v ? Math.floor(st.start / v) * v : 0;
    applyPage(t, pg);
  }); } catch (e) { /* no document events */ }
  // Download CSV scrapes the DOM, so for the length of its click the off-page
  // rows are shown (capture phase, before the button's own handler) and hidden
  // again (bubble phase, after it). No frame paints in between.
  try {
    document.addEventListener("click", function (e) {
      var b = e.target && e.target.closest ? e.target.closest(".eph-csv-btn") : null;
      var host = b && b.closest("[data-csv-export]");
      if (!host) return;
      host.querySelectorAll("table[data-mlbpage] tbody tr[hidden]").forEach(function (tr) {
        tr.hidden = false; tr.setAttribute("data-mlbcsv", "");
      });
    }, true);
    document.addEventListener("click", function (e) {
      var b = e.target && e.target.closest ? e.target.closest(".eph-csv-btn") : null;
      var host = b && b.closest("[data-csv-export]");
      if (!host) return;
      host.querySelectorAll("tr[data-mlbcsv]").forEach(function (tr) {
        tr.removeAttribute("data-mlbcsv"); tr.hidden = true;
      });
    });
  } catch (e) { /* no document events */ }

  // ---- render: shared table -------------------------------------------------
  // `meta` is the section payload, passed only so a column flagged
  // `vintage: "<payload key>"` can date itself in its own tooltip.
  // `opts` is how a board adds something the shared table has no opinion
  // about: `nameExtra(row)` rides inside the identity cell (the Overall board's
  // expander caret) and `child(row, nCols)` emits one extra row under it (the
  // per-season line). Both are optional and every other board passes neither.
  function renderTable(rows, cols, sort, meta, board, opts) {
    var plan = viewPlan(cols, sort, board);
    var allv = !!(board && COL_VIEWS[board] && COL_VIEWS[board].length > 1 && !activeView(board).keys);
    var head = "<thead><tr>";
    plan.forEach(function (p) {
      var c = p.c;
      var sortable = !!c.num || c.kind === "name" || c.kind === "team";
      var sorted = (c.key === sort.key) ? " is-sorted" : "";
      // `labelExtra` is HTML after the label, on its own line: the window
      // boards put the SPAN there, because the span belongs in the label and a
      // one-line "HEM+ 2024-2026" header is 60px wider than the column under
      // it (measured at 390px: five window boards ran past their box).
      var lbl = (c.term ? gloss(c.label, c.term) : esc(c.label)) + (c.labelExtra || "");
      var vint = c.vintage ? vintageTitle(vintageOf(meta, c.vintage)) : "";
      if (c.ewar) { var ew = ewarTitle(meta); if (ew) vint = vint ? vint + " " + ew : ew; }
      var titleTxt = c.title ? (vint ? c.title + " " + vint : c.title) : vint;
      var fnote = (c.noteFrom && meta && meta.frame && meta.frame[c.noteFrom]) ? String(meta.frame[c.noteFrom]) : "";
      if (fnote) titleTxt = titleTxt ? titleTxt + " " + fnote : fnote;
      var title = titleTxt ? ' title="' + esc(titleTxt) + '"' : "";
      // keyboard-operable sort headers: tabbable, announced as sorted,
      // activated by Enter/Space via bindSortKeys. No role=button: aria-sort is
      // honoured only on a columnheader, and the button role replaced the th's
      // own, so no screen reader heard the sort (census X06-06).
      // Every header is a column header (QMLA17: Pos and Also on had none).
      var a11y = sortable
        ? ' scope="col" tabindex="0" aria-sort="' + ((c.key === sort.key) ? (sort.asc ? "ascending" : "descending") : "none") + '"'
        : ' scope="col"';
      var nw = (allv && String(c.label).indexOf(" ") < 0) ? " mlbstats-nw" : "";
      head += '<th class="mlbstats-col-' + c.key + sorted + p.cls + nw + '"' + title + a11y + ' data-col="' + c.key
        + '" data-export-text="' + esc(c.exportLabel || c.label) + '"' + (p.off ? " data-export-skip" : "") + '>' + lbl + "</th>";
    });
    head += "</tr></thead>";

    var key = board || "board", total = rows.length, paged = total > PAGE_MIN, span = null;
    if (paged) {
      var sig = total + "|" + sort.key + "|" + sort.asc + "|" + rowId(rows[0]) + "|" + rowId(rows[total - 1]);
      var st = pageState(key);
      if (st.sig !== sig) { st.sig = sig; st.start = 0; }
      span = pageSpan(key, total);
    }
    // The rank is a CSS counter over the shown rows (site.css mlbx-rank), so a
    // later page starts it at its first row: page 2 reads 101, not 1.
    var body = "<tbody" + (span && span.start ? ' style="counter-reset: mlbx-rank ' + span.start + '"' : "") + ">";
    rows.forEach(function (r, i) {
      var prov = (r.qualified === false) ? " is-provisional" : "";
      var pg = span ? ' data-mlbi="' + i + '"' + ((i < span.start || i >= span.end) ? " hidden" : "") : "";
      body += "<tr" + prov + pg + ">";
      plan.forEach(function (p) {
        var c = p.c, td = p.cls ? '<td class="' + p.cls.slice(1) + '"' + (p.off ? " data-export-skip" : "") + ">" : "<td>";
        if (c.kind === "name") {
          body += nameCell(r, opts && opts.nameExtra ? opts.nameExtra(r) : "");
          return;
        }
        if (c.kind === "team") { body += '<td class="mlbstats-name">' + logo(r.team) + esc(r.team || EM_DASH) + "</td>"; return; }
        if (c.cell) { body += td + c.cell(r) + "</td>"; return; }
        var v = getVal(c, r);
        // An absent value reads as the site-wide null marker rather than a
        // blank cell. Columns with their own formatter keep it: those
        // formatters all route through the shared number-format contract now,
        // so they render the same token. A non-numeric value (none ship today)
        // falls through to escaped text rather than the contract, which would
        // read it as absent.
        var rendered = c.fmt ? c.fmt(v, c.term)
                     : (v == null || v === "" ? EM_DASH : esc(v));
        body += td + rendered + "</td>";
      });
      body += "</tr>";
      if (opts && opts.child) {
        var kid = opts.child(r, plan.length);
        body += (kid && pg) ? kid.replace(/^<tr/, "<tr" + pg) : kid;
      }
    });
    body += "</tbody>";
    return '<table class="mlbstats-table' + (allv ? " mlbstats-cv-all" : "") + '"'
      + (span ? ' data-mlbpage="' + esc(key) + '" data-mlbpage-total="' + total + '"' : "") + ">"
      + '<caption class="visually-hidden">' + esc(TABLE_LABEL[board] || "MLB Stats leaderboard") + "</caption>"
      + head + body + "</table>";
  }
  // The accessible name of each board's table, a hidden caption (QMLA17): a
  // screen reader's table list read "table, table" with nothing to tell the
  // boards apart.
  var TABLE_LABEL = {
    war: "Overall eWAR leaderboard", warteam: "Team eWAR",
    hit: "Hitters leaderboard", hitteam: "Team offense",
    sp: "Starters leaderboard", spteam: "Team rotations",
    rel: "Relievers leaderboard", relteam: "Team bullpens",
    def: "Fielders leaderboard", defteam: "Team defense",
    levbat: "Leverage leaderboard, hitters", levsp: "Leverage leaderboard, pitchers",
  };

  // player_links map (mlbam -> merged-card key), preloaded once at init so
  // nameCell can link synchronously. Names resolve to the merged MLB player card
  // at /projections/#player=<key>; unmatched rows stay plain text.
  var LINKS = null;
  function playerHref(r) {
    // Resolve by MLBAM via player_links -- NOT r.key (which is str(mlbam) here).
    if (!LINKS || !LINKS.byMlbam || r.mlbam == null) return null;
    var hit = LINKS.byMlbam[String(r.mlbam)];
    return (hit && hit.key) ? ("/projections/#player=" + encodeURIComponent(hit.key)) : null;
  }
  // Before the map lands, a plain name carries its MLBAM so the map's arrival
  // can turn it into the link in place. That arrival used to re-render the
  // whole active board (QMLP05: 1.7 s of main thread on a slow phone).
  function pendingName(id, nm) {
    return '<span class="mlbstats-name-txt"' + ((!LINKS && id != null) ? ' data-mlbam="' + esc(String(id)) + '"' : "")
      + ">" + nm + "</span>";
  }
  function upgradeLinks(el) {
    try {
      (el || document).querySelectorAll("span.mlbstats-name-txt[data-mlbam]").forEach(function (s) {
        var href = playerHref({ mlbam: s.getAttribute("data-mlbam") });
        s.removeAttribute("data-mlbam");
        if (!href) return;
        var a = document.createElement("a");
        a.className = "mlbstats-name-link";
        a.setAttribute("href", href);
        var td = s.closest("td.mlbstats-name"), full = td && td.getAttribute("title");
        if (td) a.setAttribute("title", (full ? full + " - " : "") + "open the MLB player card");
        while (s.firstChild) a.appendChild(s.firstChild);
        s.parentNode.replaceChild(a, s);
      });
    } catch (e) { /* links optional */ }
  }

  // The identity cell is capped at 260px and ellipsized (site.css), so a long
  // name-plus-team-plus-role runs off the end: measured at 390px, "Antonio
  // Senzatela COL High-leverage" needs 263px and loses its tail. The full
  // string therefore rides `title` on the CELL - and, because a title on the
  // anchor would win over the cell's for a pointer over the name itself, on
  // the LINK too. The link keeps its affordance hint after the name rather
  // than instead of it.
  // `extra` is HTML the board puts at the head of the cell (the Overall
  // board's expander caret). `clubs`, which only a window row carries, adds the
  // +N of the other clubs the player produced for inside the window: the cell
  // shows the last one, and the title says who the rest were, so the club basis
  // is never silently one club when the window held three.
  function nameCell(r, extra) {
    var role = r.role ? ' <span class="bp-role">' + esc(r.role) + "</span>" : "";
    var more = (r.clubs && r.clubs.length > 1)
      ? '<span class="proj-dim" title="' + esc("Clubs of production: " + r.clubs.join(", "))
        + '">+' + (r.clubs.length - 1) + "</span>" : "";
    var team = r.team ? '<span class="proj-dim"> ' + esc(r.team) + "</span>" + more : "";
    var prov = (r.qualified === false) ? '<span class="bp-prov" title="Below the qualifying sample; provisional">prov</span>' : "";
    // A fold row whose substrate carries no name prints the player's MLBAM id
    // rather than a null marker: an id is a handle (the search box matches it,
    // and it is what a reader can look up), where an em-dash at rank 4 of a
    // ranked board is not.
    var named = rowName(r);
    var nm = named ? esc(named)
      : (r.mlbam != null
          ? '<span class="mlbx-noname" title="' + esc("The per-season substrate names the players on the"
              + " current board and leaves the rest blank. This is his MLBAM id; the search box matches"
              + " it.") + '">#' + esc(String(r.mlbam)) + "</span>"
          : EM_DASH);
    // A row with no name at all gets no title rather than a title of null
    // markers: an empty tooltip is worse than none.
    var full = [named, (r.clubs && r.clubs.length > 1) ? r.clubs.join("/") : r.team,
                r.role].filter(Boolean).join(" - ");
    if (full && r.qualified === false) full += " (provisional)";
    var href = playerHref(r);
    var name = href
      ? '<a class="mlbstats-name-link" href="' + href + '" title="'
        + (full ? esc(full) + " - " : "") + 'open the MLB player card">' + nm + "</a>"
      : pendingName(named ? r.mlbam : null, nm);
    return '<td class="mlbstats-name"' + (full ? ' title="' + esc(full) + '"' : "") + ">"
      + (extra || "") + logo(r.team) + name + team + role + prov + "</td>";
  }

  function sortRows(rows, cols, sort) {
    var col = null;
    cols.forEach(function (c) { if (c.key === sort.key) col = c; });
    if (!col) return rows.slice();
    var out = rows.slice();
    var text = (col.kind === "name" || col.kind === "team");
    out.sort(function (a, b) {
      var va = getVal(col, a), vb = getVal(col, b);
      if (text) {
        // text columns (player / team): locale order, missing values last
        var sa = (va == null) ? "" : String(va), sb = (vb == null) ? "" : String(vb);
        if (!sa && !sb) return 0;
        if (!sa) return 1;
        if (!sb) return -1;
        return sort.asc ? sa.localeCompare(sb) : sb.localeCompare(sa);
      }
      // numeric columns: missing values always sort LAST regardless of
      // direction (the trademachine _tbSortRows convention)
      var na = (va == null || isNaN(va)) ? null : Number(va);
      var nb = (vb == null || isNaN(vb)) ? null : Number(vb);
      if (na == null && nb == null) return 0;
      if (na == null) return 1;
      if (nb == null) return -1;
      return sort.asc ? na - nb : nb - na;
    });
    return out;
  }

  // ---- views ----------------------------------------------------------------
  // The unfiltered pool behind whichever season is selected. The controls read
  // it too, so the team options and role chips always describe the board the
  // user is looking at rather than the live season's roster.
  function relSourceRows() {
    if (relSeason !== "current") {
      var yr = historyYear();
      return (yr && yr.relievers) || [];
    }
    return (DATA && DATA.relievers) || [];
  }
  // ONE matcher for the live board and the history board: they took separate
  // (identical) copies before, which is how a filter gets added to one and not
  // the other. History rows carry team, role and ip, so every filter applies.
  function relMatch(r) {
    if (qualifiedOnly && r.qualified === false) return false;
    if (relTeam && r.team !== relTeam) return false;
    if (relRoles.length && relRoles.indexOf(r.role) < 0) return false;
    if (!passesMin(r.ip, relMinIp)) return false;
    var q = query.trim().toLowerCase();
    if (!q) return true;
    return (String(r.name || "").toLowerCase().indexOf(q) >= 0
      || String(r.team || "").toLowerCase().indexOf(q) >= 0);
  }
  function filteredRelievers() {
    return ((DATA && DATA.relievers) || []).filter(relMatch);
  }

  // ---- yearly history board -------------------------------------------------
  // The season list drives the pills. Before the history file loads we seed it
  // from the live season (the five completed seasons before it) so the pills
  // exist to trigger the fetch; once loaded the file's own list is authoritative.
  function historySeasons() {
    if (HISTORY && HISTORY.seasons && HISTORY.seasons.length) return HISTORY.seasons.slice();
    var cur = num(DATA && DATA.season);
    if (cur == null) return [];
    var out = [];
    for (var y = cur - 1; y >= cur - 5; y--) out.push(y);
    return out;
  }
  function loadHistory() {
    if (HISTORY || HISTORY_LOADING) return;
    HISTORY_LOADING = true;
    HISTORY_ERROR = false;
    fetch(HISTORY_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { HISTORY = j; HISTORY_LOADING = false; render(); })
      .catch(function () { HISTORY_LOADING = false; HISTORY_ERROR = true; render(); });
  }
  function historyYear() {
    return (HISTORY && HISTORY.history && HISTORY.history[relSeason]) || null;
  }
  function filteredHistory() {
    var yr = historyYear();
    return ((yr && yr.relievers) || []).filter(relMatch);
  }
  // A past board can only sort on columns it actually shows; if the shared sort
  // key belongs to a current-only column, fall back to the REM+ default.
  function historySort() {
    var ok = false;
    REL_HISTORY_COLS.forEach(function (c) { if (c.key === relSort.key) ok = true; });
    return ok ? relSort : { key: "rem_plus", asc: false };
  }

  // On-page explainers for the headline metrics (F-08): one line, wired to the
  // shared glossary tooltip (data-gl via gloss()) plus a deep link into the
  // unified glossary entry, which carries the method.
  function explainer(term, html) {
    return '<div class="mlbstats-note mlbstats-explainer">' + html
      + ' <a href="/glossary/#g=' + encodeURIComponent(term) + '">Library</a></div>';
  }
  function remExplainer() {
    return explainer("rem_plus", gloss("REM+", "rem_plus")
      + ": FIP-based run-prevention skill, sample-shrunk; 100 is an average reliever, 110 is 10% better."
      + " Role and leverage do not move it.");
  }
  function bullpenExplainer() {
    return explainer("bullpen_plus", gloss("Bullpen+", "bullpen_plus")
      + ": relief-IP-weighted " + gloss("REM+", "rem_plus") + " of a pen; 100 = average."
      + " Lev Deploy+: the same on leverage-weighted innings.");
  }

  function renderRelievers() {
    winCheck("bullpen");
    if (isWindow("bullpen")) {
      var wbbullpen = renderWindowBoard("bullpen");
      if (wbbullpen) return wbbullpen;
    }
    if (relSeason !== "current") return renderRelieverHistory();
    var rows = sortRows(filteredRelievers(), REL_COLS, relSort);
    var body = rows.length
      ? (function () {
          var note = '<div class="mlbstats-note">'
            + gloss("RIV+", "riv_plus") + ": realized leverage-weighted value, a record and not a forecast."
            + " gmLI, WPA, WPA/LI and SD-MD"
            + " are leverage context. " + gloss("WAR/IP+", "war_ip_plus_rp")
            + ": reliever-anchored, 10 points = 1 SD; not comparable with the starter board's.</div>";
          return proseFold("rel-about", rows.length + " relievers",
              remExplainer() + scorecard() + note
              + vintageNote(DATA, [["multiyear", "REM+ 3yr"], ["multiyear_war_rate", "WAR/IP+ 3yr"]],
                  " gmLI 3yr: frozen the same way, no date shipped."))
            + relieverViz()
            + '<div class="mlbstats-scroll">' + renderTable(rows, REL_COLS, relSort, DATA, "rel") + "</div>";
        })()
      : noRowsNote(relTeam, "No relievers match the current filters.");
    return yearsRow("bullpen") + body;
  }

  // A past season's board: the same table and controls, restricted to the
  // columns a history row carries (no trailing-window or WPA/LI columns). It
  // lets a user eyeball how each season's REM+ (skill) and RIV+ (impact) aged.
  function renderRelieverHistory() {
    var pills = yearsRow("bullpen");
    if (HISTORY_ERROR) {
      return pills + pxState("failed",
        "Season history failed to load. Refresh to retry; if it persists the nightly build is mid-run. "
        + '<button type="button" class="chip" id="mlbstats-history-retry">Retry</button>', "mlbstats-load-error");
    }
    if (!HISTORY) {
      loadHistory();
      return pills + pxState("loading", "Loading the " + esc(relSeason) + " season leaderboard&hellip;");
    }
    if (HISTORY_LOADING) {
      return pills + pxState("loading", "Loading the " + esc(relSeason) + " season leaderboard&hellip;");
    }
    var yr = historyYear();
    if (!yr || !yr.relievers || !yr.relievers.length) {
      return pills + '<div class="mlbstats-empty">No leaderboard for the ' + esc(relSeason) + " season.</div>";
    }
    var sort = historySort();
    var rows = sortRows(filteredHistory(), REL_HISTORY_COLS, sort);
    var nQual = (yr.n_qualified != null) ? yr.n_qualified : yr.relievers.length;
    var cap = proseFold("rel-history-about",
      esc(relSeason) + " season, " + esc(nQual) + " qualified relievers",
      '<div class="mlbstats-note">' + gloss("REM+", "rem_plus") + ": skill. "
      + gloss("RIV+", "riv_plus") + ": realized leverage-weighted value, a record and not a forecast.</div>");
    var relHistCols = coveredCols(REL_HISTORY_COLS, rows);
    var table = rows.length
      ? '<div class="mlbstats-scroll">' + renderTable(rows, relHistCols, sort, null, "rel") + "</div>"
      : noRowsNote(relTeam, "No relievers match the current filters.");
    return pills + cap + table;
  }

  function renderTeams() {
    var rows = (DATA && DATA.teams) || [];
    rows = sortRows(rows, TEAM_COLS, teamSort);
    if (!rows.length) return '<div class="mlbstats-empty">No team bullpens to show yet.</div>';
    return proseFold("relteam-about", rows.length + " bullpens", bullpenExplainer())
      + '<div class="mlbstats-scroll">' + renderTable(rows, TEAM_COLS, teamSort, DATA, "relteam") + "</div>";
  }

  function teamDepth(t) {
    if (t.depth && t.depth.length) return t.depth.slice();
    // fall back to grouping the reliever pool by team, ordered by gmLI
    var rel = ((DATA && DATA.relievers) || []).filter(function (r) { return r.team === t.team; });
    rel.sort(function (a, b) { return (num(b.gmli) || 0) - (num(a.gmli) || 0); });
    return rel;
  }

  function renderDepth() {
    var teams = (DATA && DATA.teams) || [];
    if (!teams.length) return '<div class="mlbstats-empty">No bullpen charts to show yet.</div>';
    var sorted = teams.slice().sort(function (a, b) { return (num(b.bullpen_plus) || 0) - (num(a.bullpen_plus) || 0); });
    var cards = sorted.map(function (t) {
      var slots = teamDepth(t).map(function (r) {
        return '<div class="bp-slot">'
          + '<span class="bp-slot-role">' + esc(r.role || EM_DASH) + "</span>"
          + '<span class="bp-slot-name"' + (r.name ? ' title="' + esc(r.name) + '"' : "") + ">" + esc(r.name || EM_DASH)
          + (r.gmli != null ? '<span class="proj-dim"> gmLI ' + f2(r.gmli) + "</span>" : "") + "</span>"
          + '<span class="bp-slot-rem ' + EephusTiers.clsInk(r.rem_plus, "run") + '">' + fInt(r.rem_plus) + "</span>"
          + "</div>";
      }).join("");
      return '<div class="bp-depth-card"><div class="bp-depth-head">'
        + '<span class="bp-depth-team">' + logo(t.team) + esc(t.team) + "</span>"
        + '<span class="rem-plus ' + EephusTiers.cls(t.bullpen_plus, "z") + '" data-gl="bullpen_plus">Bullpen+ ' + fInt(t.bullpen_plus) + "</span>"
        + "</div>" + slots + "</div>";
    }).join("");
    return '<div class="mlbstats-note">Each pen by role, then gmLI; number = '
      + gloss("REM+", "rem_plus") + ".</div>" + '<div class="bp-depth-grid">' + cards + "</div>";
  }

  // ---- shell ----------------------------------------------------------------
  // FRESHNESS BANNER, one implementation for all four sections. This read
  // season / as_of / coverage / verdict off the bullpen payload only, and wrote
  // into the #mlbstats-banner div the page shell provides for that section
  // alone - so Starters, Hitters and Leverage showed no date at all, even
  // though every one of those payloads carries as_of (and Leverage carries a
  // coverage block too). A stat board that will not say what day it is through
  // is the one thing a reader cannot check for himself.
  //
  // The other three sections have no banner div in the shell, so they prepend
  // the same markup inside their own root instead. `opts.noCoverage` is for
  // Leverage, whose board note already prints a SEASON-AWARE coverage line
  // (the live count is wrong for a past-season pill); one number, once.
  //
  // `opts.sec` names the section, so a past season or a window stamps ITSELF
  // rather than the live payload (census M06-03): the 2023 hitter board and
  // the 2024-2026 window both read "Season 2026 through <today>" while the
  // window's 2026 slice was built days earlier, and a past bullpen board
  // printed the live season's play-by-play coverage.
  function bannerHTML(d, opts) {
    if (!d) return "";
    var o = opts || {};
    var bits = [];
    var w = o.sec ? viewWin(o.sec) : null, liveY = num(d.season);
    if (w && w.lo === w.hi && (liveY == null || w.lo >= liveY)) w = null;
    if (w && w.lo === w.hi) {
      bits.push("Season " + esc(w.lo) + ", complete");
    } else if (w) {
      bits.push(esc(w.lo + "-" + w.hi));
      var thru = (liveY != null && w.hi >= liveY) ? liveSliceDate(o.sec, w, liveY) : null;
      if (thru) bits.push(esc(liveY) + " through " + esc(thru));
    }
    if (!w && d.season) bits.push("Season " + esc(d.season));
    if (!w && d.as_of) bits.push("through " + esc(d.as_of));
    if (!w && !o.noCoverage && d.coverage && d.coverage.games != null) {
      var cov = d.coverage;
      // bullpen stamps `expected`, leverage stamps `games_total`.
      var tot = (cov.expected != null) ? cov.expected : cov.games_total;
      bits.push(esc(cov.games) + (tot != null ? " / " + esc(tot) : "") + " games of play-by-play");
    }
    if (d.verdict === "validated") {
      bits.push('<span class="bp-validated" title="Backtested out of sample; scorecard in the board notes">backtested</span>');
    } else if (d.verdict) {
      bits.push('<span class="bp-prov" style="margin-left:0">' + esc(d.verdict) + "</span>");
    }
    if (!bits.length) return "";
    return '<div class="mlbstats-note mlbstats-freshness">' + bits.join(" &middot; ") + "</div>";
  }
  function banner() { return bannerHTML(DATA, { sec: "bullpen" }); }
  // The window or past season a section's PLAYER board is showing, or null for
  // Current. The team and chart views of the role boards always serve the live
  // payload, so they stamp it whatever the season control says. The Overall
  // board's Team eWAR tab refuses a window outright, so it keeps the stamp.
  function viewWin(sec) {
    var on = sec === "bullpen" ? view === "relievers"
      : sec === "starters" ? starterView === "starters"
      : sec === "hitters" ? hitterView === "hitters"
      : sec === "defense" ? defenseView === "fielders"
      : true;
    return on ? (WIN[sec] || null) : null;
  }
  // The date the live season's slice of a window was built: the Overall board
  // folds data/war_seasons.json, whose as_of it prints; the role boards read
  // the lab window file's panel_built_at. Null until that payload has landed.
  function liveSliceDate(sec, w, liveY) {
    if (sec === "war") return (SEASONS && SEASONS.as_of) || null;
    var lw = labWindowFor(LAB_BOARD[sec], w.lo, w.hi);
    var doc = lw && WINDOW_DOC[lw.key];
    return (doc && doc.panel_built_at && doc.panel_built_at[String(liveY)]) || null;
  }
  // The payload whose team_basis block describes the rows on screen: the live
  // one on Current, the section's history payload on a past season, and none on
  // a window, whose own note states that the club is every club of production.
  function sectionBasis(sec, live, hist) {
    var w = viewWin(sec), liveY = num(live && live.season);
    if (!w || (w.lo === w.hi && liveY != null && w.lo >= liveY)) return live;
    return w.lo === w.hi ? (hist || null) : null;
  }

  // WHAT THE TEAM COLUMN MEANS, and it is not what a reader assumes.
  //
  // The exporters point `team` at the club MLB's transaction feed says employs
  // the player TODAY, on the history boards as well as the current one. So a
  // past season carries the player's present club: Corbin Burnes' 2021 Cy Young
  // season shows under his current club rather than Milwaukee.
  //
  // The exporters have written a full `team_basis` block explaining this since
  // it was introduced. NOTHING ON THIS PAGE HAS EVER READ IT: a grep for
  // team_basis in this file returned zero. So the convention was applied
  // silently and a reader had no way to learn it existed.
  //
  // This renders the payload's own sentence. It does not change the basis,
  // which is a deliberate choice with a real argument behind it (you can filter
  // a club and see the arms it holds now); it just stops the page keeping that
  // choice to itself.
  //
  // AND IT HAS TO RUN ON EVERY BOARD. It was wired into one render site, the
  // bullpen view, which is the board where the convention moves the FEWEST rows
  // (39 of 790). The starter, hitter and Leverage views rendered nothing, and
  // the yearly-history boards, where the same rule points a 2021 season at a
  // 2026 club and moves 2,088 of 6,885 rows, had no team_basis block in their
  // payloads at all to render. Each view passes ITS OWN payload, because the
  // counts differ per board and a shared one would misreport three of them.
  // The closed summary is a CLAIM about the basis, so it is read from the
  // payload rather than typed. bullpen_export.TEAM_BASIS is a two-value
  // constant (current_roster | stats_earned) with a one-line revert, and the
  // meta block carries the scope beside it: under stats_earned, and on the
  // outage path where the authoritative org map comes back empty, a typed
  // "the club today" would say the opposite of the sentence in the body. The
  // history boards get their own noun because the rule costs a reader more
  // there: 2,088 of 6,885 served history rows sit under a club the player
  // joined after the season.
  function teamBasisLead(tb) {
    if (tb.basis === "current_roster") {
      return (tb.scope === "history") ? "the club today, not the club of that season"
                                      : "the club today";
    }
    if (tb.basis === "stats_earned") return "the club the line was earned with";
    return "see the note";        // a basis this page has never been told about
  }
  // A native <details> keeps no state of its own and every board rewrites its
  // root on a keystroke, so an opened note snapped shut under the reader, on
  // four boards but not the fifth. One module flag, flipped by one delegated
  // listener and emitted by every render: the pattern the methodology fold
  // (collapseState) and the phone drawer (filtersOpen) already use. The click
  // listener runs before the browser's own toggle, so the state it records is
  // !open.
  var teamNoteOpen = false;
  try { document.addEventListener("click", function (e) {
    var s = e.target && e.target.closest ? e.target.closest("details.mlbstats-teambasis > summary") : null;
    if (!s || !s.parentNode) return;
    teamNoteOpen = !s.parentNode.open;
  }); } catch (e) { /* no document events */ }
  function teamBasisNote(d) {
    var tb = (d || {}).team_basis;
    if (!tb || !tb.note) return "";
    var moved = (tb.n_moved_to_current_club != null && tb.n_rows)
      ? " " + esc(tb.n_moved_to_current_club) + " of " + esc(tb.n_rows) +
        " rows are credited to a club other than the one they earned the line for."
      : "";
    // One line closed (the vertical budget, O2); the payload's own sentence
    // and the moved-row count open under it. The closed line is the one
    // 100% of readers see, so it is DERIVED like the body, and the count is
    // dropped when nothing moved rather than printing "(0 rows moved)".
    var n = tb.n_moved_to_current_club;
    return '<details class="mlbstats-note mlbstats-teambasis"' + (teamNoteOpen ? " open" : "")
      + '><summary><b>Team column:</b> ' + teamBasisLead(tb)
      + (n ? '<span class="proj-dim"> (' + esc(n) + (n === 1 ? " row" : " rows")
          + " moved)</span>" : "")
      + "</summary>" + esc(tb.note) + moved + "</details>";
  }

  // The market line prints only with its signing count. A payload that carries
  // a bare market_rho is the old one, whose number was a leverage-weighted lab
  // variant on a name-matched pair set rather than REM+, so it prints nothing.
  function marketLine(b) {
    if (b.market_rho == null || b.market_n == null) return "";
    return '<span class="pal-sc-stat" title="' + esc("Descriptive, not a gate: the rank correlation between"
        + " REM+ in a reliever's walk year and the AAV of the free-agent deal he signed that winter, on "
        + b.market_n + " matched signings" + (b.market_as_of ? " (re-gate of " + b.market_as_of + ")" : "")
        + ".") + '">REM+ vs next-winter AAV &rho; <b>' + esc(b.market_rho) + '</b><span class="proj-dim"> ('
      + esc(b.market_n) + " signings, descriptive)</span></span>";
  }
  // REM+ accountability scorecard - mirrors PAL's pattern so a validated model
  // surfaces its out-of-sample backtest to users, not just a status word.
  function scorecard() {
    var b = (DATA && DATA.backtest) || {};
    if (b.rho_rem_plus == null) return "";
    return '<div class="mlbstats-scorecard">'
      + '<span class="pal-sc-stat">' + gloss("REM+", "rem_plus") + ' forward &rho; <b>'
      + b.rho_rem_plus + '</b><span class="proj-dim"> vs raw FIP ' + (b.rho_fip == null ? EM_DASH : b.rho_fip)
      + ", ERA " + (b.rho_era == null ? EM_DASH : b.rho_era) + "</span></span>"
      + '<span class="pal-sc-stat"><b>' + esc(b.n_pairs) + "</b> out-of-sample year pairs"
      + (b.seasons ? '<span class="proj-dim"> (' + esc(b.seasons) + " seasons)</span>" : "") + "</span>"
      + marketLine(b)
      + '<span class="pal-sc-note">' + esc(b.disclaimer || "") + "</span>"
      + "</div>";
  }

  function tabBar() {
    // routing key stays "depth" so existing URLs/hashes keep working; the label
    // reads "Bullpen Charts" now.
    var tabs = [["relievers", "Relievers"], ["teams", "Team Bullpens"], ["depth", "Bullpen Charts"]];
    return '<div class="mlbstats-tabs" role="tablist">' + tabs.map(function (t) {
      var active = (t[0] === view) ? " active" : "";
      return '<button type="button" class="mlbstats-tab' + active + '" data-mlbview="' + t[0] + '" role="tab" aria-selected="' + (t[0] === view) + '">' + t[1] + "</button>";
    }).join("") + "</div>";
  }

  function controls() {
    // Team Bullpens has no filter controls of its own; give it a bar that just
    // carries the Generate GFX chip (only when the shared module is loaded).
    if (view === "teams") {
      var teamChip = gfxChip("mlbstats-teams-gfx");
      return teamChip ? '<div class="mlbstats-bar">' + teamChip + "</div>" : "";
    }
    if (view !== "relievers") return "";
    var pool = relSourceRows();
    // Role is a SEASON fact: the window payload carries no role field, so the
    // chips cannot be applied on one. They go with the filter rather than
    // sitting pressed over a board that ignores them, and the Filters badge
    // stops counting them (a badge that counts a filter which is off is the
    // same lie in one digit).
    var relWin = isWindow("bullpen");
    return '<div class="' + filtCls() + '">'
      + filtBtn(filtCount(relTeam, relMinIp, relWin ? null : relRoles, !qualifiedOnly))
      + teamFilterChip(relTeam)
      + '<label class="mlbstats-ctl">'
      + '<input type="checkbox" id="mlbstats-qual"' + (qualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-team", winSelectRows("bullpen", pool), relTeam, "bullpen")
      + minSelect("mlbstats-minip", minLabel("bullpen", "min IP"), relMinIp,
          "Minimum innings. Stacks with qualified only.")
      + gfxChip("mlbstats-rel-gfx")
      + '<input class="mlbstats-search" type="search" id="mlbstats-q" placeholder="Search reliever or team" value="' + esc(query) + '">'
      + "</div>"
      + (relWin ? "" : roleChips(pool, relRoles, "mlbstats-role-"));
  }

  function render() {
    var root = document.getElementById("mlbstats-app-root");
    if (!root) return;
    if (!DATA) {
      root.innerHTML = LOAD_ERROR
        ? pxState("failed", "Data failed to load. Refresh to retry; "
          + "if it persists the nightly build is mid-run. "
          + '<button type="button" class="chip" id="mlbstats-retry">Retry</button>', "mlbstats-load-error")
        : pxState("unmeasured", 'Bullpen Leaderboards are being computed from MLB play-by-play. '
          + "Check back shortly.");
      var retry = document.getElementById("mlbstats-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = pxState("loading", "Loading&hellip;");
        load();
      });
      return;
    }
    var inner = (view === "teams") ? renderTeams() : (view === "depth") ? renderDepth() : renderRelievers();
    root.innerHTML = tabBar() + controls() + inner;
    bindEvents(root);
    wireGlossary(root);
    var bann = document.getElementById("mlbstats-banner");
    if (bann) bann.innerHTML = banner() + teamBasisNote(sectionBasis("bullpen", DATA, HISTORY));
  }

  function bindEvents(root) {
    bindCollapse(root);
    stampCsv("bullpen", root);
    bindColViews(root, function () { renderInPlace(); });
    root.querySelectorAll("[data-mlbview]").forEach(function (b) {
      b.addEventListener("click", function () {
        view = b.getAttribute("data-mlbview");
        writeHash();
        render();
      });
    });
    var q = root.querySelector("#mlbstats-q");
    if (q) q.addEventListener("input", function () { query = q.value; renderInPlace(); });
    var qual = root.querySelector("#mlbstats-qual");
    if (qual) qual.addEventListener("change", function () { qualifiedOnly = qual.checked; renderInPlace(); });
    // Each control re-renders in place and hands focus back to ITSELF, so a
    // keyboard user is not thrown to the search box every time he narrows.
    var relTeamSel = root.querySelector("#mlbstats-team");
    if (relTeamSel) relTeamSel.addEventListener("change", function () {
      relTeam = relTeamSel.value || "";
      writeHash();
      renderInPlace("mlbstats-team");
    });
    var relMin = root.querySelector("#mlbstats-minip");
    if (relMin) relMin.addEventListener("input", function () {
      relMinIp = readMin(relMin);
      renderInPlace("mlbstats-minip");
    });
    root.querySelectorAll("[data-mlbrole]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-mlbrole");
        if (!v) relRoles = [];
        else {
          var i = relRoles.indexOf(v);
          if (i >= 0) relRoles.splice(i, 1); else relRoles.push(v);
        }
        renderInPlace(b.id || null);
      });
    });
    var relGfx = root.querySelector("#mlbstats-rel-gfx");
    if (relGfx) relGfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      var rows = isWindow("bullpen") ? windowGfxRows("bullpen")
        : (relSeason === "current") ? sortRows(filteredRelievers(), REL_COLS, relSort)
        : sortRows(filteredHistory(), REL_HISTORY_COLS, historySort());
      EEPHUS_GFX.open(_mlbstatsBoardSpec("relievers", rows));
    });
    var teamGfx = root.querySelector("#mlbstats-teams-gfx");
    if (teamGfx) teamGfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      EEPHUS_GFX.open(_mlbstatsBoardSpec("bullpens", sortRows((DATA && DATA.teams) || [], TEAM_COLS, teamSort)));
    });
    var hretry = root.querySelector("#mlbstats-history-retry");
    if (hretry) hretry.addEventListener("click", function () {
      HISTORY_ERROR = false;
      loadHistory();
      render();
    });
    root.querySelectorAll(".mlbstats-table th[data-col]").forEach(function (th) {
      bindSortKeys(th, root, function () {
        var key = th.getAttribute("data-col");
        var cols = (view === "teams") ? TEAM_COLS
          : (view === "relievers" && relSeason !== "current") ? REL_HISTORY_COLS : REL_COLS;
        var col = null; cols.forEach(function (c) { if (c.key === key) col = c; });
        if (!col || (!col.num && col.kind !== "name" && col.kind !== "team")) return;
        var sort = (view === "teams") ? teamSort : relSort;
        if (sort.key === key) sort.asc = !sort.asc;
        else { sort.key = key; sort.asc = !!col.asc; }
        writeHash();
        render();
      });
    });
  }

  // Focus restore after an in-place re-render. The innerHTML swap destroys the
  // control the user was operating, so whichever one triggered the render gets
  // put back under the caret. setSelectionRange throws on input[type=number] in
  // Chromium, hence the guard - the focus still lands.
  function restoreFocus(root, id) {
    var el = root.querySelector("#" + (id || "mlbstats-q"));
    if (!el) return;
    el.focus();
    try { el.setSelectionRange(el.value.length, el.value.length); } catch (e) { /* not a text field */ }
  }

  // Re-render only the table region (keeps focus on the control being used).
  function renderInPlace(focusId) {
    var root = document.getElementById("mlbstats-app-root");
    if (!root) return;
    var inner = (view === "teams") ? renderTeams() : (view === "depth") ? renderDepth() : renderRelievers();
    // Replace everything after the controls bar.
    var tabsHtml = tabBar();
    var ctrlHtml = controls();
    root.innerHTML = tabsHtml + ctrlHtml + inner;
    restoreFocus(root, focusId);
    bindEvents(root);
    wireGlossary(root);
  }

  // ---- deep-linkable page state ---------------------------------------------
  // Section + view have been in the hash for a while; SEASON and SORT were not,
  // so a URL copied off "2024 relievers sorted by K-BB%" reopened on the
  // current season sorted by REM+ - a link that silently shows something else
  // is worse than no link. Both are in the hash now.
  //
  // Sort encodes as "<column key>.<a|d>" (ascending / descending). Only the
  // per-board DEFAULT is omitted, so a fresh board still produces the short URL
  // it always did and an old URL, which carries none of these keys, restores
  // exactly what it used to.
  var SORT_DEFAULTS = {
    rsort:  { key: "rem_plus", asc: false },        // Relievers
    rtsort: { key: "bullpen_plus", asc: false },    // Team Bullpens
    ssort:  { key: "sem_plus", asc: false },        // Starters
    stsort: { key: "rotation_plus", asc: false },   // Team Rotations
    hsort:  { key: "hem_plus", asc: false },        // Hitters
    htsort: { key: "offense_plus", asc: false },    // Team Lineups
    lbsort: { key: "wpa", asc: false },             // Leverage: batters
    lssort: { key: "wpa", asc: false },             // Leverage: starters
    dsort:  { key: "dem_plus", asc: false },        // Defense: fielders
    dtsort: { key: "team_dem_plus", asc: false },   // Team Defense
    wsort:  { key: "war", asc: false },             // eWAR: players
    wtsort: { key: "war", asc: false },             // eWAR: teams
  };
  // A season key is "current" or a four-digit year; anything else is ignored
  // rather than trusted, because the value goes straight into a payload lookup.
  function readSeason(h, key, fallback) {
    var m = new RegExp("(?:^#|[#&])" + key + "=(current|\\d{4})\\b").exec(h);
    return m ? m[1] : fallback;
  }
  // A WINDOW rides its own key, never a widened season key. readSeason's \b
  // matches between 2023 and the hyphen, so a browser holding a cached copy of
  // yesterday's script and reading #hseason=2023-2025 would silently render
  // 2023; a key it has never heard of is ignored outright, which opens Current -
  // a visible wrong answer instead of an invisible one. The (?:^#|[#&]) anchor
  // is the same one that stops sview= matching view=.
  function readRange(h, key) {
    var m = new RegExp("(?:^#|[#&])" + key + "=(\\d{4})-(\\d{4})\\b").exec(h);
    return m ? { lo: Number(m[1]), hi: Number(m[2]) } : null;
  }
  // The season key first, then the window key, because a span is the more
  // specific statement. Neither is TRUSTED: winCheck validates both against the
  // seasons that section publishes once its payload has landed.
  function readWindow(h, sec, seasonKey, yearsKey) {
    var y = readSeason(h, seasonKey, "current");
    if (y !== "current") WIN[sec] = { lo: Number(y), hi: Number(y) };
    var r = readRange(h, yearsKey);
    if (r && r.lo <= r.hi) WIN[sec] = r;
  }
  function pushWindow(parts, sec, seasonKey, yearsKey) {
    var w = WIN[sec];
    if (!w) return;                       // Current is the default: no key at all
    if (w.lo === w.hi) parts.push(seasonKey + "=" + w.lo);
    else parts.push(yearsKey + "=" + w.lo + "-" + w.hi);
  }
  // A sort key is only honoured if the named column EXISTS on that board and is
  // actually sortable; a stale or hand-edited URL falls back to the default
  // instead of leaving the board sorted by a column it does not have.
  function readSort(h, key, cols, sort) {
    var m = new RegExp("(?:^#|[#&])" + key + "=([A-Za-z0-9_]+)\\.([ad])\\b").exec(h);
    if (!m) return;
    var ok = false;
    (cols || []).forEach(function (c) {
      if (c.key === m[1] && (c.num || c.kind === "name" || c.kind === "team")) ok = true;
    });
    if (!ok) return;
    sort.key = m[1];
    sort.asc = (m[2] === "a");
  }
  function readHash() {
    var h = location.hash || "";
    // Top-level section deep-link (#section=bullpen|starters|hitters|leverage|
    // defense) + the per-section view (#view= bullpen, #sview= starters,
    // #dview= defense). Each key is anchored to a separator so e.g.
    // "sview=teams" or "dview=teams" can never match the "view=" regex.
    var s = /(?:^#|[#&])section=(bullpen|starters|hitters|leverage|defense|war)\b/.exec(h);
    if (s) section = s[1];
    var m = /(?:^#|[#&])view=(relievers|teams|depth)\b/.exec(h);
    if (m) view = m[1];
    var sv = /(?:^#|[#&])sview=(starters|teams|charts)\b/.exec(h);
    if (sv) starterView = sv[1];
    var hv = /(?:^#|[#&])hview=(hitters|teams|charts)\b/.exec(h);
    if (hv) hitterView = hv[1];
    var lv = /(?:^#|[#&])lview=(batters|starters)\b/.exec(h);
    if (lv) leverageView = lv[1];
    var dv = /(?:^#|[#&])dview=(fielders|teams|charts)\b/.exec(h);
    if (dv) defenseView = dv[1];
    var wv = /(?:^#|[#&])wview=(players|teams)\b/.exec(h);
    if (wv) warView = wv[1];
    // One team for every section (section 7). Set before the boards render, so
    // a deep-linked club is the first thing each one is narrowed to.
    var tm = TEAM_HASH_RE.exec(h);
    if (tm) {
      relTeam = starterTeam = hitterTeam = leverageTeam = defenseTeam = warTeam = tm[1];
    }
    // Season pills. readHash runs from init(), after every one of these vars
    // and column arrays has been assigned, so the forward references are safe.
    readWindow(h, "bullpen", "rseason", "ryears");
    readWindow(h, "starters", "sseason", "syears");
    readWindow(h, "hitters", "hseason", "hyears");
    readWindow(h, "leverage", "lseason", "lyears");
    readWindow(h, "defense", "dseason", "dyears");
    readWindow(h, "war", "wseason", "wyears");
    syncSeasonVars();
    // Column view per board (rcols / scols / hcols / dcols). A retired id
    // resolves to its replacement (VIEW_ALIAS); an unknown one is ignored, so
    // the board opens on the stored view or Standard.
    Object.keys(COL_VIEW_HASH).forEach(function (b) {
      var m2 = new RegExp("(?:^#|[#&])" + COL_VIEW_HASH[b] + "=([a-z]+)\\b").exec(h);
      var id = m2 ? resolveView(b, m2[1]) : null;
      if (id && viewById(b, id)) COL_VIEW[b] = id;
    });
    // Sort per board.
    readSort(h, "rsort", REL_COLS, relSort);
    readSort(h, "rtsort", TEAM_COLS, teamSort);
    readSort(h, "ssort", STARTER_COLS, starterSort);
    readSort(h, "stsort", STARTER_TEAM_COLS, starterTeamSort);
    readSort(h, "hsort", HITTER_COLS, hitterSort);
    readSort(h, "htsort", HITTER_TEAM_COLS, hitterTeamSort);
    readSort(h, "lbsort", BAT_LEV_COLS, leverageBatSort);
    readSort(h, "lssort", STARTER_LEV_COLS, leverageStarterSort);
    readSort(h, "dsort", DEFENSE_COLS, defenseSort);
    readSort(h, "dtsort", DEFENSE_TEAM_COLS, defenseTeamSort);
    readSort(h, "wsort", WAR_COLS, warSort);
    readSort(h, "wtsort", WAR_TEAM_COLS, warTeamSort);
  }

  // Compose the FULL page state into the hash on every section/tab/season/sort
  // change so a copied URL restores what the user sees. The section is always
  // written; everything else only when off its default (keeps URLs short), and
  // the single replaceState never clobbers a deep-linked #section= the way the
  // old bullpen-only "#view=" write did.
  function pushSort(parts, key, sort) {
    var d = SORT_DEFAULTS[key];
    if (!sort || !sort.key) return;
    if (d && sort.key === d.key && !!sort.asc === !!d.asc) return;
    parts.push(key + "=" + sort.key + "." + (sort.asc ? "a" : "d"));
  }
  function writeHash() {
    var parts = ["section=" + section];
    if (view !== "relievers") parts.push("view=" + view);
    if (starterView !== "starters") parts.push("sview=" + starterView);
    if (hitterView !== "hitters") parts.push("hview=" + hitterView);
    if (leverageView !== "batters") parts.push("lview=" + leverageView);
    if (defenseView !== "fielders") parts.push("dview=" + defenseView);
    if (warView !== "players") parts.push("wview=" + warView);
    pushWindow(parts, "bullpen", "rseason", "ryears");
    pushWindow(parts, "starters", "sseason", "syears");
    pushWindow(parts, "hitters", "hseason", "hyears");
    pushWindow(parts, "leverage", "lseason", "lyears");
    pushWindow(parts, "defense", "dseason", "dyears");
    pushWindow(parts, "war", "wseason", "wyears");
    Object.keys(COL_VIEW_HASH).forEach(function (b) {
      if (COL_VIEW[b] && COL_VIEW[b] !== "standard") parts.push(COL_VIEW_HASH[b] + "=" + COL_VIEW[b]);
    });
    pushSort(parts, "rsort", relSort);
    pushSort(parts, "rtsort", teamSort);
    pushSort(parts, "ssort", starterSort);
    pushSort(parts, "stsort", starterTeamSort);
    pushSort(parts, "hsort", hitterSort);
    pushSort(parts, "htsort", hitterTeamSort);
    pushSort(parts, "lbsort", leverageBatSort);
    pushSort(parts, "lssort", leverageStarterSort);
    pushSort(parts, "dsort", defenseSort);
    pushSort(parts, "dtsort", defenseTeamSort);
    pushSort(parts, "wsort", warSort);
    pushSort(parts, "wtsort", warTeamSort);
    // The ACTIVE section's team, so the URL describes the board on screen
    // rather than a club the reader left behind on another one.
    var tm = activeTeam();
    if (tm) parts.push("team=" + tm);
    try { history.replaceState(null, "", "#" + parts.join("&")); } catch (e) { /* hash optional */ }
  }

  // Loader with a visible failure mode: a non-OK response or a network error
  // sets LOAD_ERROR so render() paints the error state (with a Retry button)
  // instead of a blank/"computing" page. A successful fetch of a null payload
  // still reads as "not exported yet".
  function load() {
    LOAD_ERROR = false;
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { DATA = j; render(); })
      .catch(function () { DATA = null; LOAD_ERROR = true; render(); });
  }

  // ===========================================================================
  // Section 2: Starter Leaderboards (SEM+ starter run-prevention skill).
  // ---------------------------------------------------------------------------
  // A parallel of the reliever section: SEM+ is a starter's pure run-prevention
  // skill (100 = the IP-weighted average of starters with 20+ IP), and durability (IP, GS, average
  // start length) rides context columns so workload never moves the skill
  // number. Renders into #mlbstats-starters-root; reuses every shared helper
  // (renderTable / sortRows / gloss / remCell / explainer / season pills).
  // ===========================================================================
  // THE LANDING SECTION, owner decision 2026-09-17: Overall (hash value `war`,
  // unchanged, so every link ever copied off this page still opens what it
  // named). The section nav in build_site.build_mlbstats is ordered and marked
  // active to match; the two have to move together or a deep link paints the
  // wrong tab.
  var section = "war";                        // war | hitters | starters | bullpen | defense | leverage
  var STARTER_URL = "/data/starter_leaderboards.json";
  var STARTER_HISTORY_URL = "/data/starter_history.json";

  var starterData = null;
  var starterErr = false;                     // fetch failed / non-OK
  var starterInit = false;                    // lazy-fetch guard (first activation)
  var starterView = "starters";               // starters | teams
  var starterSort = { key: "sem_plus", asc: false };
  var starterTeamSort = { key: "rotation_plus", asc: false };
  var starterQuery = "";
  var starterQualifiedOnly = true;
  var starterTeam = "";                       // "" = all clubs
  var starterMinIp = null;                    // null = no floor

  // Yearly history board (starter_history.json), lazy-fetched the first time a
  // past season pill is picked. Mirrors the reliever history state machine.
  var starterSeason = "current";
  var STARTER_HISTORY = null;
  var STARTER_HISTORY_LOADING = false;
  var STARTER_HISTORY_ERROR = false;

  // Skill core first (SEM+ and the trailing-window SEM+ 3yr), then the durability
  // and rate columns that ride as context.
  var STARTER_COLS = [
    { key: "name", label: "Starter", term: null, sortable: true, kind: "name", asc: true },
    { key: "sem_plus", label: "SEM+", term: "sem_plus", fmt: runCell, num: true, desc: true, isRem: true },
    { key: "sem_plus_3yr", label: "SEM+ 3yr", term: "sem_plus_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear",
      get: function (r) { return r.sem_plus_3yr; },
      cell: function (r) {
        return r.sem_plus_3yr == null ? "" : win3yrCell(r, "sem_plus_3yr", "under 2 seasons or 120 IP");
      } },
    { key: "xsem_plus", label: "xSEM+", term: "xsem_plus", num: true, desc: true, isRem: true,
      title: "SEM+ scale on Savant xwOBA allowed. A deserved read beside SEM+, not a replacement: xwOBA allowed did not beat FIP predictively. Tracked starters only.",
      get: function (r) { return r.xsem_plus; },
      cell: function (r) { return r.xsem_plus == null ? "" : runCell(r.xsem_plus); } },
    { key: "luck", label: "Luck (wOBA)", num: true, desc: true,
      title: "wOBA allowed minus xwOBA allowed. Positive: allowed more than his contact deserved; negative: less.",
      get: function (r) { return r.luck; },
      cell: function (r) {
        if (r.luck == null) return "";
        var v = r.luck;
        var col = v >= 0.02 ? "var(--up)" : v <= -0.02 ? "var(--down)" : "var(--text-tertiary)";
        return '<span style="color:' + col + ';font-variant-numeric:tabular-nums;">' + (v > 0 ? "+" : "") + v.toFixed(3) + "</span>";
      } },
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true,
      title: "Pitching eWAR this season; the WAR/IP+ numerator." },
    // Starter-anchored WAR/IP+. The reliever board ships a reliever-anchored
    // WAR/IP+ under the same field name in its own payload; the two are separate
    // metrics on separate pools and are never pooled into one column (a reliever
    // banks more WAR per inning than a starter of equal talent). Both ride the
    // z family: 100 + 10z has SD exactly 10, which is what that ladder bands for.
    { key: "war_ip_plus", label: "WAR/IP+", term: "war_ip_plus_sp", num: true, desc: true, isRem: true,
      ewar: true,
      title: "Pitching eWAR per inning, 100 + 10z over starters with 20+ IP; shown at 40+ IP. Not comparable with the reliever board's WAR/IP+. p = percentile on this board.",
      get: function (r) { return r.war_ip_plus; },
      cell: function (r) {
        if (r.war_ip_plus == null) return "";
        var s = remCell(r.war_ip_plus);
        if (r.war_ip_plus_pct != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(r.war_ip_plus_pct) + "</span>";
        return s;
      } },
    { key: "war_ip_plus_adj", label: "WAR/IP+ adj", term: "war_ip_plus_sp_adj", num: true, desc: true, isRem: true,
      title: "WAR/IP+ with the rate shrunk toward the pool by innings, re-standardised (10 points = 1 SD). A thin-sample readability aid, not a forecast: neither WAR rate predicts next season better than season WAR.",
      get: function (r) { return r.war_ip_plus_adj; },
      cell: function (r) { return r.war_ip_plus_adj == null ? "" : remCell(r.war_ip_plus_adj); } },
    { key: "war_ip_plus_3yr", label: "WAR/IP+ 3yr", term: "war_ip_plus_sp_3yr", num: true, desc: true, isRem: true,
      title: "Trailing three seasons, innings-weighted, on the same eWAR series as WAR/IP+.",
      vintage: "multiyear_war_rate",
      get: function (r) { return r.war_ip_plus_3yr; },
      cell: function (r) {
        if (r.war_ip_plus_3yr == null) return "";
        var s = remCell(r.war_ip_plus_3yr);
        if (r.war_ip_plus_3yr_pct != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(r.war_ip_plus_3yr_pct) + "</span>";
        if (r.war_ip_plus_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 120 IP in the trailing window">*</span>';
        return s;
      } },
    { key: "ip", label: "IP", fmt: f1, num: true },
    { key: "gs", label: "GS", fmt: fInt, num: true },
    { key: "ip_per_gs", label: "IP/GS", fmt: f1, num: true, title: "Average start length (innings per game started)" },
    { key: "k_pct", label: "K%", term: "k_pct", fmt: fPct, num: true },
    { key: "bb_pct", label: "BB%", term: "bb_pct", fmt: fPct, num: true, asc: true },
    { key: "k_bb_pct", label: "K-BB%", term: "k_bb_pct", fmt: fPct, num: true },
    { key: "gb_pct", label: "GB%", fmt: fPct, num: true },
    // Same field, same caveat as the reliever board: sem_plus.fip_skill, shrunk
    // toward the STARTER pool, not the standard FIP the `fip` glossary entry
    // defines. That entry used to be wired here.
    { key: "fip", label: "Skill FIP", term: "skill_fip", fmt: f2, num: true, asc: true,
      title: skillFipTitle("starter", "SEM+") },
    { key: "era", label: "ERA", term: "era", fmt: f2, num: true, asc: true },
    { key: "hr9", label: "HR/9", fmt: f2, num: true, asc: true },
    // Savant custom leaderboard (savant_leaderboards.py), display only. SwStr%
    // is the one derived column: Savant whiff% x swing% (whiffs per pitch).
    { key: "swstr_pct", label: "SwStr%", term: "swstr_pct", fmt: fPct, num: true,
      title: "Whiffs per pitch, derived from the Baseball Savant custom leaderboard as whiff% x swing%, the one source both pitcher boards use. Display only: no score on this board reads it." },
    { key: "whiff_pct", label: "Whiff%", term: "whiff_pct", fmt: fPct, num: true,
      title: savantTitle("Misses per swing.") },
    { key: "chase_pct", label: "Chase%", term: "chase_pct", fmt: fPct, num: true,
      title: savantTitle("Swings per pitch outside Savant's strike zone.") },
    { key: "z_contact_pct", label: "Z-Contact%", term: "z_contact_pct", fmt: fPct, num: true, asc: true,
      title: savantTitle("Contact per swing at a pitch inside Savant's strike zone.") },
    { key: "f_strike_pct", label: "F-Strike%", term: "f_strike_pct", fmt: fPct, num: true,
      title: savantTitle("Share of plate appearances that start with a strike.") },
    { key: "fb_velo", label: "FB velo", term: "fb_velo", fmt: f1, num: true,
      title: "Average fastball speed in mph, from the Baseball Savant custom leaderboard. Display only: no score on this board reads it." },
  ];

  // Past-season history rows carry the season-level fields but not the
  // trailing-window SEM+ 3yr. Reuse the same column objects so the history board
  // renders and sorts identically, dropping the column its rows lack. The WAR
  // RATES stay dropped (they are standardised on the live pool); eWAR itself is
  // a season count the history export joins per (player, season), so it is not
  // in the list, and coveredCols holds it back until a season carries it.
  var STARTER_HISTORY_DROP = { sem_plus_3yr: 1, xsem_plus: 1, luck: 1,
    war_ip_plus: 1, war_ip_plus_adj: 1, war_ip_plus_3yr: 1,
    swstr_pct: 1, whiff_pct: 1, chase_pct: 1, z_contact_pct: 1, f_strike_pct: 1, fb_velo: 1 };
  var STARTER_HISTORY_COLS = historyTitle(
    STARTER_COLS.filter(function (c) { return !STARTER_HISTORY_DROP[c.key]; }),
    "war", "Pitching eWAR for the season shown.");

  var STARTER_TEAM_COLS = [
    { key: "team", label: "Team", sortable: true, kind: "team", asc: true },
    { key: "rotation_plus", label: "Rotation+", term: "rotation_plus", fmt: remCell, num: true, desc: true, isRem: true },
    { key: "team_war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true,
      title: "Starter eWAR of this rotation's arms. Same club basis as the Team column." },
    { key: "front_sem", label: "Front 3", fmt: runCell, num: true,
      title: "Mean SEM+ of the top three starters by SEM+." },
    { key: "n_above_avg", label: "Above-avg", fmt: fInt, num: true,
      title: "Starters at SEM+ 100 or better / starters in the rotation.",
      get: function (t) { return num(t.n_above_avg); },
      cell: function (t) { return fInt(t.n_above_avg) + (t.n_starters != null ? '<span class="proj-dim"> / ' + fInt(t.n_starters) + "</span>" : ""); } },
    { key: "starter_ip", label: "Starter IP", fmt: f1, num: true },
    { key: "total_gs", label: "GS", fmt: fInt, num: true },
  ];

  // SEM+ explainer - reuses the shared explainer() markup so it styles like the
  // reliever REM+ one, wired to the glossary tooltip (data-gl) + deep link.
  function semExplainer() {
    return explainer("sem_plus", gloss("SEM+", "sem_plus")
      + ": FIP-based run-prevention skill, sample-shrunk; 100 is the IP-weighted average of starters with 20+ IP, 110 is"
      + " 10% better. IP, GS and IP/GS are context and do not move it.");
  }

  // SEM+ accountability scorecard - mirrors the reliever scorecard so a validated
  // model surfaces its out-of-sample backtest, not just a status word.
  function starterScorecard() {
    var b = (starterData && starterData.backtest) || {};
    if (b.rho_sem_plus == null) return "";
    return '<div class="mlbstats-scorecard">'
      + '<span class="pal-sc-stat">' + gloss("SEM+", "sem_plus") + ' forward &rho; <b>'
      + b.rho_sem_plus + '</b><span class="proj-dim"> vs raw FIP ' + (b.rho_fip == null ? EM_DASH : b.rho_fip)
      + ", ERA " + (b.rho_era == null ? EM_DASH : b.rho_era) + "</span></span>"
      + '<span class="pal-sc-stat"><b>' + esc(b.n_pairs) + "</b> out-of-sample year pairs"
      + (b.seasons ? '<span class="proj-dim"> (' + esc(b.seasons) + " seasons)</span>" : "") + "</span>"
      + '<span class="pal-sc-note">' + esc(b.disclaimer || "") + "</span>"
      + "</div>";
  }

  // ---- starters: yearly history board ---------------------------------------
  function starterHistorySeasons() {
    if (STARTER_HISTORY && STARTER_HISTORY.seasons && STARTER_HISTORY.seasons.length) return STARTER_HISTORY.seasons.slice();
    var cur = num(starterData && starterData.season);
    if (cur == null) return [];
    var out = [];
    for (var y = cur - 1; y >= cur - 5; y--) out.push(y);
    return out;
  }
  function loadStarterHistory() {
    if (STARTER_HISTORY || STARTER_HISTORY_LOADING) return;
    STARTER_HISTORY_LOADING = true;
    STARTER_HISTORY_ERROR = false;
    fetch(STARTER_HISTORY_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { STARTER_HISTORY = j; STARTER_HISTORY_LOADING = false; renderStarters(); })
      .catch(function () { STARTER_HISTORY_LOADING = false; STARTER_HISTORY_ERROR = true; renderStarters(); });
  }
  function starterHistoryYear() {
    return (STARTER_HISTORY && STARTER_HISTORY.history && STARTER_HISTORY.history[starterSeason]) || null;
  }
  // The unfiltered pool behind the active season pill, so the team options
  // describe the board on screen.
  function starterSourceRows() {
    if (starterSeason !== "current") {
      var yr = starterHistoryYear();
      return (yr && yr.starters) || [];
    }
    return (starterData && starterData.starters) || [];
  }
  // One matcher for the live and history boards (see relMatch).
  function starterMatch(r) {
    if (starterQualifiedOnly && r.qualified === false) return false;
    if (starterTeam && r.team !== starterTeam) return false;
    if (!passesMin(r.ip, starterMinIp)) return false;
    var q = starterQuery.trim().toLowerCase();
    if (!q) return true;
    return (String(r.name || "").toLowerCase().indexOf(q) >= 0
      || String(r.team || "").toLowerCase().indexOf(q) >= 0);
  }
  function filteredStarters() {
    return ((starterData && starterData.starters) || []).filter(starterMatch);
  }
  function filteredStarterHistory() {
    var yr = starterHistoryYear();
    return ((yr && yr.starters) || []).filter(starterMatch);
  }
  // A past board can only sort on columns it shows; if the shared sort key is a
  // current-only column (SEM+ 3yr), fall back to the SEM+ default.
  function starterHistorySort() {
    var ok = false;
    STARTER_HISTORY_COLS.forEach(function (c) { if (c.key === starterSort.key) ok = true; });
    return ok ? starterSort : { key: "sem_plus", asc: false };
  }

  // ---- starters: views ------------------------------------------------------
  function starterTabBar() {
    var tabs = [["starters", "Starters"], ["teams", "Team Rotations"], ["charts", "Rotation Charts"]];
    return '<div class="mlbstats-tabs" role="tablist">' + tabs.map(function (t) {
      var active = (t[0] === starterView) ? " active" : "";
      return '<button type="button" class="mlbstats-tab' + active + '" data-starterview="' + t[0] + '" role="tab" aria-selected="' + (t[0] === starterView) + '">' + t[1] + "</button>";
    }).join("") + "</div>";
  }
  function starterControls() {
    if (starterView !== "starters") return "";
    return '<div class="' + filtCls() + '">' + filtBtn(filtCount(starterTeam, starterMinIp, null, !starterQualifiedOnly))
      + teamFilterChip(starterTeam)
      + '<label class="mlbstats-ctl">'
      + '<input type="checkbox" id="mlbstats-starter-qual"' + (starterQualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-starter-team", winSelectRows("starters", starterSourceRows()),
          starterTeam, "starters")
      + minSelect("mlbstats-starter-minip", minLabel("starters", "min IP"), starterMinIp,
          "Minimum innings. Stacks with qualified only.")
      + gfxChip("mlbstats-starter-gfx")
      + '<input class="mlbstats-search" type="search" id="mlbstats-starter-q" placeholder="Search starter or team" value="' + esc(starterQuery) + '">'
      + "</div>";
  }

  function renderStarterBoard() {
    winCheck("starters");
    if (isWindow("starters")) {
      var wbstarters = renderWindowBoard("starters");
      if (wbstarters) return wbstarters;
    }
    if (starterSeason !== "current") return renderStarterHistory();
    var rows = sortRows(filteredStarters(), STARTER_COLS, starterSort);
    var body = rows.length
      ? (function () {
          var note = '<div class="mlbstats-note">' + gloss("WAR/IP+", "war_ip_plus_sp")
            + ": starter-anchored, 10 points = 1 SD; not comparable with the reliever board's.</div>";
          return proseFold("sp-about", rows.length + " starters",
              semExplainer() + starterScorecard() + note
              + vintageNote(starterData, [["multiyear", "SEM+ 3yr"], ["multiyear_war_rate", "WAR/IP+ 3yr"]]))
            + '<div class="mlbstats-scroll">' + renderTable(rows, STARTER_COLS, starterSort, starterData, "sp") + "</div>";
        })()
      : noRowsNote(starterTeam, "No starters match the current filters.");
    return yearsRow("starters") + body;
  }

  // A past season's board: the same table and controls, restricted to the
  // columns a history row carries (no SEM+ 3yr trailing-window column). It lets a
  // user eyeball how each season's SEM+ (skill) aged forward.
  function renderStarterHistory() {
    var pills = yearsRow("starters");
    if (STARTER_HISTORY_ERROR) {
      return pills + pxState("failed",
        "Season history failed to load. Refresh to retry; if it persists the nightly build is mid-run. "
        + '<button type="button" class="chip" id="mlbstats-starter-history-retry">Retry</button>', "mlbstats-load-error");
    }
    if (!STARTER_HISTORY) {
      loadStarterHistory();
      return pills + pxState("loading", "Loading the " + esc(starterSeason) + " season leaderboard&hellip;");
    }
    if (STARTER_HISTORY_LOADING) {
      return pills + pxState("loading", "Loading the " + esc(starterSeason) + " season leaderboard&hellip;");
    }
    var yr = starterHistoryYear();
    if (!yr || !yr.starters || !yr.starters.length) {
      return pills + '<div class="mlbstats-empty">No leaderboard for the ' + esc(starterSeason) + " season.</div>";
    }
    var sort = starterHistorySort();
    var rows = sortRows(filteredStarterHistory(), STARTER_HISTORY_COLS, sort);
    var nQual = (yr.n_qualified != null) ? yr.n_qualified : yr.starters.length;
    var cap = proseFold("sp-history-about",
      esc(starterSeason) + " season, " + esc(nQual) + " qualified starters",
      '<div class="mlbstats-note">' + gloss("SEM+", "sem_plus") + ": skill. IP, GS and IP/GS: context.</div>");
    var spHistCols = coveredCols(STARTER_HISTORY_COLS, rows);
    var table = rows.length
      ? '<div class="mlbstats-scroll">' + renderTable(rows, spHistCols, sort, null, "sp") + "</div>"
      : noRowsNote(starterTeam, "No starters match the current filters.");
    return pills + cap + table;
  }

  function renderStarterTeams() {
    var rows = (starterData && starterData.teams) || [];
    rows = sortRows(rows, STARTER_TEAM_COLS, starterTeamSort);
    if (!rows.length) return '<div class="mlbstats-empty">No team rotations to show yet.</div>';
    var note = '<div class="mlbstats-note">' + gloss("Rotation+", "rotation_plus") + ": starter-IP-weighted "
      + gloss("SEM+", "sem_plus") + " of a rotation; 100 = average.</div>";
    return proseFold("spteam-about", rows.length + " rotations", note)
      + '<div class="mlbstats-scroll">' + renderTable(rows, STARTER_TEAM_COLS, starterTeamSort, starterData, "spteam") + "</div>";
  }

  // ---- starters: Rotation Charts (mirrors the reliever viz + bullpen depth) --
  // SVG SEM+ distribution + skill-vs-durability scatter (clone of relieverViz),
  // then per-team rotation depth ladders (clone of renderDepth): each rotation as
  // its workload-ordered starters with SEM+ per slot.
  function starterViz() {
    var qual = ((starterData && starterData.starters) || []).filter(function (r) { return r.qualified !== false; });
    if (qual.length < 12) return "";
    var sems = qual.map(function (r) { return r.sem_plus; });
    var hist = chart("histogram", sems, { height: 108, min: 55, max: 175, highlightAbove: 120,
      refs: [{ at: 100, label: "avg" }], aria: "SEM+ distribution" });
    var pts = qual.filter(function (r) { return r.ip_per_gs != null; }).map(function (r) {
      return { x: r.sem_plus, y: r.ip_per_gs, label: r.name + "  SEM+ " + fInt(r.sem_plus) + "  IP/GS " + f1(r.ip_per_gs),
               color: r.sem_plus >= 115 ? null : "var(--text-tertiary)" };
    });
    var sc = chart("scatter", pts, { height: 250, xLabel: "SEM+ (skill) →", yLabel: "↑ IP/GS (durability)",
      xRef: 100, aria: "skill vs durability" });
    // Earned vs deserved: SEM+ (FIP-based results) against xSEM+ (xwOBA-
    // allowed). Below the diagonal band = results ahead of contact quality
    // (regression candidates); above = deserving better.
    var xpts = qual.filter(function (r) { return r.xsem_plus != null; }).map(function (r) {
      return { x: r.sem_plus, y: r.xsem_plus,
               label: r.name + "  SEM+ " + fInt(r.sem_plus) + "  xSEM+ " + fInt(r.xsem_plus),
               color: r.sem_plus >= 115 ? null : "var(--text-tertiary)" };
    });
    var xsc = xpts.length >= 12
      ? chart("scatter", xpts, { height: 250, xLabel: "SEM+ (results) →",
          yLabel: "↑ xSEM+ (deserved)", xRef: 100, yRef: 100, diag: true, aria: "earned vs deserved" })
      : "";
    if (!hist && !sc && !xsc) return "";
    var body = '<div class="mlbstats-viz">'
      + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">' + gloss("SEM+", "sem_plus")
      + ' distribution <span class="proj-dim">(qualified; cyan = 120+)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">SEM+ vs IP/GS'
        + ' <span class="proj-dim">(bright = SEM+ 115+)</span></div>' + sc + "</div>" : "")
      + (xsc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">SEM+ vs ' + gloss("xSEM+", "xsem_plus")
        + ' <span class="proj-dim">(below the diagonal = FIP results ahead of contact quality)</span></div>' + xsc + "</div>" : "")
      + "</div>";
    return collapsible("starters-viz", 'Charts <span class="proj-dim">(SEM+ distribution, vs IP/GS, vs xSEM+)</span>', body);
  }

  function rotationLadders() {
    var teams = (starterData && starterData.teams) || [];
    var starters = (starterData && starterData.starters) || [];
    if (!teams.length || !starters.length) return "";
    var byTeam = {};
    starters.forEach(function (r) {
      if (!r.team) return;
      (byTeam[r.team] = byTeam[r.team] || []).push(r);
    });
    Object.keys(byTeam).forEach(function (t) {
      byTeam[t].sort(function (a, b) { return (num(b.ip) || 0) - (num(a.ip) || 0); });
    });
    var sorted = teams.slice().sort(function (a, b) { return (num(b.rotation_plus) || 0) - (num(a.rotation_plus) || 0); });
    var cards = sorted.map(function (t) {
      var rot = (byTeam[t.team] || []).slice(0, 5);
      var slots = rot.map(function (r, i) {
        return '<div class="bp-slot">'
          + '<span class="bp-slot-role">SP' + (i + 1) + "</span>"
          + '<span class="bp-slot-name"' + (r.name ? ' title="' + esc(r.name) + '"' : "") + ">" + esc(r.name || EM_DASH)
          + (r.ip_per_gs != null ? '<span class="proj-dim"> ' + f1(r.ip_per_gs) + " IP/GS</span>" : "") + "</span>"
          + '<span class="bp-slot-rem ' + EephusTiers.clsInk(r.sem_plus, "run") + '">' + fInt(r.sem_plus) + "</span>"
          + "</div>";
      }).join("");
      return '<div class="bp-depth-card"><div class="bp-depth-head">'
        + '<span class="bp-depth-team">' + logo(t.team) + esc(t.team) + "</span>"
        + '<span class="rem-plus ' + EephusTiers.cls(t.rotation_plus, "z") + '" data-gl="rotation_plus">Rotation+ ' + fInt(t.rotation_plus) + "</span>"
        + "</div>" + slots + "</div>";
    }).join("");
    return '<div class="mlbstats-note">Top five starters by IP; number = ' + gloss("SEM+", "sem_plus") + ".</div>"
      + '<div class="bp-depth-grid">' + cards + "</div>";
  }

  function renderStarterCharts() {
    if (!starterData || !((starterData.starters) || []).length) {
      return '<div class="mlbstats-empty">No rotation charts to show yet.</div>';
    }
    return starterViz() + rotationLadders();
  }

  // ---- starters: shell ------------------------------------------------------
  function renderStarters() {
    var root = document.getElementById("mlbstats-starters-root");
    if (!root) return;
    if (!starterData) {
      root.innerHTML = starterErr
        ? pxState("failed", "Data failed to load. Refresh to retry; "
          + "if it persists the nightly build is mid-run. "
          + '<button type="button" class="chip" id="mlbstats-starter-retry">Retry</button>', "mlbstats-load-error")
        : pxState("unmeasured", 'Starter Leaderboards are being computed from MLB play-by-play. '
          + "Check back shortly.");
      var retry = document.getElementById("mlbstats-starter-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = pxState("loading", "Loading&hellip;");
        loadStarters();
      });
      return;
    }
    var inner = (starterView === "teams") ? renderStarterTeams()
      : (starterView === "charts") ? renderStarterCharts() : renderStarterBoard();
    // No #mlbstats-banner div exists for this section, so the freshness line
    // leads the section's own root.
    root.innerHTML = bannerHTML(starterData, { sec: "starters" }) + teamBasisNote(sectionBasis("starters", starterData, STARTER_HISTORY))
      + starterTabBar() + starterControls() + inner;
    bindStarterEvents(root);
    wireGlossary(root);
  }

  function bindStarterEvents(root) {
    bindCollapse(root);
    stampCsv("starters", root);
    bindColViews(root, function () { renderStartersInPlace(); });
    root.querySelectorAll("[data-starterview]").forEach(function (b) {
      b.addEventListener("click", function () {
        starterView = b.getAttribute("data-starterview");
        writeHash();
        renderStarters();
      });
    });
    var q = root.querySelector("#mlbstats-starter-q");
    if (q) q.addEventListener("input", function () { starterQuery = q.value; renderStartersInPlace(); });
    var qual = root.querySelector("#mlbstats-starter-qual");
    if (qual) qual.addEventListener("change", function () { starterQualifiedOnly = qual.checked; renderStartersInPlace(); });
    var spTeam = root.querySelector("#mlbstats-starter-team");
    if (spTeam) spTeam.addEventListener("change", function () {
      starterTeam = spTeam.value || "";
      writeHash();
      renderStartersInPlace("mlbstats-starter-team");
    });
    var spMin = root.querySelector("#mlbstats-starter-minip");
    if (spMin) spMin.addEventListener("input", function () {
      starterMinIp = readMin(spMin);
      renderStartersInPlace("mlbstats-starter-minip");
    });
    var starterGfx = root.querySelector("#mlbstats-starter-gfx");
    if (starterGfx) starterGfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      var rows = isWindow("starters") ? windowGfxRows("starters")
        : (starterSeason === "current") ? sortRows(filteredStarters(), STARTER_COLS, starterSort)
        : sortRows(filteredStarterHistory(), STARTER_HISTORY_COLS, starterHistorySort());
      EEPHUS_GFX.open(_mlbstatsBoardSpec("starters", rows));
    });
    var hretry = root.querySelector("#mlbstats-starter-history-retry");
    if (hretry) hretry.addEventListener("click", function () {
      STARTER_HISTORY_ERROR = false;
      loadStarterHistory();
      renderStarters();
    });
    root.querySelectorAll(".mlbstats-table th[data-col]").forEach(function (th) {
      bindSortKeys(th, root, function () {
        var key = th.getAttribute("data-col");
        var cols = (starterView === "teams") ? STARTER_TEAM_COLS
          : (starterView === "starters" && starterSeason !== "current") ? STARTER_HISTORY_COLS : STARTER_COLS;
        var col = null; cols.forEach(function (c) { if (c.key === key) col = c; });
        if (!col || (!col.num && col.kind !== "name" && col.kind !== "team")) return;
        var sort = (starterView === "teams") ? starterTeamSort : starterSort;
        if (sort.key === key) sort.asc = !sort.asc;
        else { sort.key = key; sort.asc = !!col.asc; }
        writeHash();
        renderStarters();
      });
    });
  }

  // Re-render only the starters root (keeps focus on the control being used).
  function renderStartersInPlace(focusId) {
    var root = document.getElementById("mlbstats-starters-root");
    if (!root) return;
    var inner = (starterView === "teams") ? renderStarterTeams()
      : (starterView === "charts") ? renderStarterCharts() : renderStarterBoard();
    root.innerHTML = bannerHTML(starterData, { sec: "starters" }) + teamBasisNote(sectionBasis("starters", starterData, STARTER_HISTORY))
      + starterTabBar() + starterControls() + inner;
    restoreFocus(root, focusId || "mlbstats-starter-q");
    bindStarterEvents(root);
    wireGlossary(root);
  }

  // Loader with a visible failure mode, matching the bullpen loader: a non-OK
  // response or network error sets starterErr so renderStarters paints the error
  // state (with Retry) instead of a blank board.
  function loadStarters() {
    starterErr = false;
    fetch(STARTER_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { starterData = j; renderStarters(); })
      .catch(function () { starterData = null; starterErr = true; renderStarters(); });
  }

  // First activation lazy-fetches the payload; later activations just re-render.
  function initStarters() {
    if (starterInit) { renderStarters(); return; }
    starterInit = true;
    renderStarters();          // paint the loading/computing state up front
    loadStarters();
  }

  // ===========================================================================
  // Section 3: Hitter Leaderboards (HEM+ offensive-rate skill).
  // ---------------------------------------------------------------------------
  // The hitter analog of the reliever/starter sections: HEM+ is a hitter's pure
  // offensive-rate skill (100 = the PA-weighted average of hitters with 50+ PA), a sample-shrunk wOBA;
  // volume (PA), baserunning (SB), and the slash line ride context columns so
  // they never move the skill number. Renders into #mlbstats-hitters-root; reuses
  // every shared helper. Tabs mirror the pitching sections: Hitters / Team
  // Lineups / Lineup Charts.
  // ===========================================================================
  var HITTER_URL = "/data/hitter_leaderboards.json";
  var HITTER_HISTORY_URL = "/data/hitter_history.json";

  var hitterData = null;
  var hitterErr = false;
  var hitterInit = false;
  var hitterView = "hitters";                 // hitters | teams | charts
  var hitterSplit = "vr";                      // vr (vs RHP) | vl (vs LHP) for lineup charts
  var hitterSort = { key: "hem_plus", asc: false };
  var hitterTeamSort = { key: "offense_plus", asc: false };
  var hitterQuery = "";
  var hitterQualifiedOnly = true;
  var hitterTeam = "";                        // "" = all clubs
  var hitterMinPa = null;                     // null = no floor
  // NO POSITION FILTER. The hitter payload carries no position field at all
  // (hitter_export ships name / team / bats / the rate and volume columns and
  // nothing else), so a position dropdown would either be empty or invented.
  // It is an exporter change, not a frontend one.

  var hitterSeason = "current";
  var HITTER_HISTORY = null;
  var HITTER_HISTORY_LOADING = false;
  var HITTER_HISTORY_ERROR = false;

  // Skill core first (HEM+), then the volume + slash-line context columns.
  var HITTER_COLS = [
    { key: "name", label: "Hitter", term: null, sortable: true, kind: "name", asc: true },
    { key: "hem_plus", label: "HEM+", term: "hem_plus", fmt: hemCell, num: true, desc: true, isRem: true },
    // INDUSTRY COLUMN, deliberately placed beside HEM+ so the site's own index
    // can be read against the number the industry publishes. No isRem flag:
    // that marks the site's own index family and this is not one of them.
    { key: "wrc_plus", label: "wRC+", term: "wrc_plus", num: true, desc: true,
      title: "PUBLISHED, NOT COMPUTED HERE. MLB's season-total wRC+, read verbatim by player id; a traded hitter reads one line. 100 = league average, park and league adjusted. Unshrunk, so it runs wider than HEM+ and bands on its own thresholds.",
      get: function (r) { return r.wrc_plus; },
      cell: function (r) { return r.wrc_plus == null ? "" : wrcCell(r.wrc_plus); } },
    { key: "hem_plus_3yr", label: "HEM+ 3yr", term: "hem_plus_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear",
      get: function (r) { return r.hem_plus_3yr; },
      cell: function (r) {
        return r.hem_plus_3yr == null ? "" : win3yrCell(r, "hem_plus_3yr", "under 2 seasons or 600 PA");
      } },
    { key: "xhem_plus", label: "xHEM+", term: "xhem_plus", num: true, desc: true, isRem: true,
      title: "HEM+ scale on Savant xwOBA. Predicts next-year offense better than actual wOBA. Tracked hitters only.",
      get: function (r) { return r.xhem_plus; },
      cell: function (r) { return r.xhem_plus == null ? "" : hemCell(r.xhem_plus); } },
    { key: "fwdhem_plus", label: "xHEM+ Blend", term: "fwdhem_plus", num: true, desc: true, isRem: true,
      title: "70% xwOBA + 30% HEM+ core, HEM+ scale. Provisional: as served, not separable from xwOBA alone on next-year offense at this sample (2026-09-18 re-gate). Tracked hitters only.",
      get: function (r) { return r.fwdhem_plus; },
      cell: function (r) { return r.fwdhem_plus == null ? "" : hemCell(r.fwdhem_plus); } },
    { key: "pwoba", label: "pWOBA", term: "pwoba", num: true, desc: true,
      title: "Next-season wOBA from the FA-engine Marcel projection; read like wOBA (about .310 average). Tracked hitters with a recent MLB sample.",
      get: function (r) { return r.pwoba; },
      cell: function (r) {
        if (r.pwoba == null) return "";
        // Color by pool PERCENTILE (the export stamps pwoba_pctile). This is not
        // a value ladder and it has no family among the ten on the value ruler:
        // a percentile is ALREADY a rank, so it is banded here and exempted by
        // name in test_value_ruler.py. It borrows the ruler's colour vocabulary
        // so the board still reads as one system, and never reaches the red
        // step. It carries `vt-fam-pctile` rather than no family at all, so the
        // markup still says which ruler drew the cell and a test can read it:
        // this is the ONE call site whose family is not a ladder.
        var p = num(r.pwoba_pctile);
        var cls = "vt vt-fam-pctile " + (p == null ? "vt-avg" : p >= 90 ? "vt-elite" : p >= 70 ? "vt-good" : p >= 25 ? "vt-avg" : "vt-below");
        return '<span class="rem-plus ' + cls + '" data-gl="pwoba">' + f3(r.pwoba) + "</span>";
      } },
    // Savant xwOBA minus Savant wOBA, in wOBA points (hitter_export). It was
    // xHEM+ minus HEM+ until 2026-09-24, which subtracted a SHRUNK index from
    // an unshrunk one and so mostly measured the shrinkage: it disagreed in
    // sign with xwOBA minus wOBA on 126 of 460 hitters. Same unit, precision
    // and colour steps as the pitcher boards' Luck (wOBA) column.
    { key: "luck_gap", label: "Luck (wOBA)", num: true, desc: true,
      title: "xwOBA minus wOBA (Savant). Positive: results below his contact quality; negative: above it.",
      get: function (r) { return r.luck_gap; },
      cell: function (r) {
        if (r.luck_gap == null) return "";
        var v = r.luck_gap;
        var col = v >= 0.02 ? "var(--up)" : v <= -0.02 ? "var(--down)" : "var(--text-tertiary)";
        return '<span style="color:' + col + ';font-variant-numeric:tabular-nums;">' + (v > 0 ? "+" : "") + v.toFixed(3) + "</span>";
      } },
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true,
      title: "Position-player eWAR this season; the WAR/PA+ numerator." },
    // WAR/PA+ rides the z family, NOT the ratio family, and that is deliberate.
    // The HEM+ family around it is a ratio index widened to wRC+ width (SD about
    // 16), so it bands at 112 / 130. WAR/PA+ is 100 + 10z, so its SD is exactly
    // 10 by construction, and the z ladder bands it at 93 / 107 / 120 (0.7 and 2
    // sigma), the one colour ruler the MLB player page shares for the whole
    // 100 + 10z family (owner decision 25, 2026-09-11). Recolouring it on the
    // ratio ladder would call a 1.2-sigma hitter average. Do not "fix" this to
    // match the neighbouring columns.
    { key: "war_pa_plus", label: "WAR/PA+", term: "war_pa_plus", num: true, desc: true, isRem: true,
      ewar: true,
      title: "Position-player eWAR (equal to bWAR on this side) per PA, 100 + 10z over hitters with 50+ PA; shown at 100+ PA. Carries fielding, baserunning and the positional adjustment, which HEM+ leaves out. p = percentile on this board.",
      get: function (r) { return r.war_pa_plus; },
      cell: function (r) {
        if (r.war_pa_plus == null) return "";
        var s = remCell(r.war_pa_plus);
        if (r.war_pa_plus_pct != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(r.war_pa_plus_pct) + "</span>";
        return s;
      } },
    { key: "war_pa_plus_adj", label: "WAR/PA+ adj", term: "war_pa_plus_adj", num: true, desc: true, isRem: true,
      title: "WAR/PA+ with the rate shrunk toward the league by PA, re-standardised (10 points = 1 SD). A thin-sample readability aid, not a forecast: neither WAR rate predicts next season better than season WAR.",
      get: function (r) { return r.war_pa_plus_adj; },
      cell: function (r) { return r.war_pa_plus_adj == null ? "" : remCell(r.war_pa_plus_adj); } },
    { key: "war_pa_plus_3yr", label: "WAR/PA+ 3yr", term: "war_pa_plus_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear_war_rate",
      get: function (r) { return r.war_pa_plus_3yr; },
      cell: function (r) {
        if (r.war_pa_plus_3yr == null) return "";
        var s = remCell(r.war_pa_plus_3yr);
        if (r.war_pa_plus_3yr_pct != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(r.war_pa_plus_3yr_pct) + "</span>";
        if (r.war_pa_plus_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 600 PA in the trailing window">*</span>';
        return s;
      } },
    { key: "pa", label: "PA", fmt: fInt, num: true },
    { key: "hr", label: "HR", fmt: fInt, num: true },
    { key: "sb", label: "SB", fmt: fInt, num: true },
    { key: "avg", label: "AVG", term: "avg", fmt: f3, num: true, title: "Batting average (context)" },
    { key: "obp", label: "OBP", term: "obp", fmt: f3, num: true },
    { key: "slg", label: "SLG", term: "slg", fmt: f3, num: true },
    { key: "ops", label: "OPS", term: "ops", fmt: f3, num: true },
    { key: "iso", label: "ISO", term: "iso", fmt: f3, num: true, title: "Isolated power (SLG - AVG)" },
    { key: "woba_raw", label: "wOBA", term: "woba", fmt: f3, num: true, title: "Season wOBA as recorded, unshrunk." },
    { key: "woba", label: "Shrunk wOBA", term: "hem_plus", fmt: f3, num: true,
      title: "wOBA shrunk toward the pool by PA: the number HEM+ is scaled from." },
    { key: "bb_pct", label: "BB%", fmt: fPct, num: true },
    { key: "k_pct", label: "K%", fmt: fPct, num: true, asc: true },
    { key: "babip", label: "BABIP", term: "babip", fmt: f3, num: true },
    // Savant custom leaderboard (savant_leaderboards.py), display only.
    { key: "chase_pct", label: "Chase%", term: "chase_pct", fmt: fPct, num: true, asc: true,
      title: savantTitle("Swings per pitch outside Savant's strike zone.") },
    { key: "whiff_pct", label: "Whiff%", term: "whiff_pct", fmt: fPct, num: true, asc: true,
      title: savantTitle("Misses per swing.") },
    { key: "z_contact_pct", label: "Z-Contact%", term: "z_contact_pct", fmt: fPct, num: true,
      title: savantTitle("Contact per swing at a pitch inside Savant's strike zone.") },
    { key: "sweet_spot_pct", label: "Sweet spot%", term: "sweet_spot_pct", fmt: fPct, num: true,
      title: savantTitle("Share of batted balls hit at a launch angle of 8 to 32 degrees.") },
    { key: "pull_pct", label: "Pull%", term: "pull_pct", fmt: fPct, num: true,
      title: savantTitle("Share of batted balls hit to the pull side.") },
  ];

  // History rows carry the season fields but not the trailing-window HEM+ 3yr,
  // the current-season Savant xHEM+ / xHEM+ Blend / Luck joins, or the
  // current-projection-only pWOBA column (a past board has no "next season").
  // The WAR-RATE columns are standardised on the live pool, so they drop out of
  // a past-season board rather than rendering as a blank column; eWAR itself is
  // a season count, and recorded wOBA is a season field, so both are out of this
  // list and coveredCols holds each back until a season carries it. Published
  // wRC+ still drops outright: the league feed serves it for every history
  // season, but hitter_export joins it on the live board only.
  var HITTER_HISTORY_DROP = { hem_plus_3yr: 1, xhem_plus: 1, fwdhem_plus: 1, luck_gap: 1, pwoba: 1,
    war_pa_plus: 1, war_pa_plus_adj: 1, war_pa_plus_3yr: 1, wrc_plus: 1,
    chase_pct: 1, whiff_pct: 1, z_contact_pct: 1, sweet_spot_pct: 1, pull_pct: 1 };
  var HITTER_HISTORY_COLS = historyTitle(
    HITTER_COLS.filter(function (c) { return !HITTER_HISTORY_DROP[c.key]; }),
    "war", "Position-player eWAR for the season shown.");
  // A past board can only sort on columns it shows; if the shared key is a
  // current-only column (HEM+ 3yr), fall back to the HEM+ default.
  function hitterHistorySort() {
    var ok = false;
    HITTER_HISTORY_COLS.forEach(function (c) { if (c.key === hitterSort.key) ok = true; });
    return ok ? hitterSort : { key: "hem_plus", asc: false };
  }

  var HITTER_TEAM_COLS = [
    { key: "team", label: "Team", sortable: true, kind: "team", asc: true },
    { key: "offense_plus", label: "Offense+", term: "offense_plus", fmt: hemCell, num: true, desc: true, isRem: true },
    { key: "team_war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true,
      title: "Position-player eWAR of this club's hitters. Same club basis as the Team column." },
    { key: "heart_hem", label: "Heart 3", fmt: hemCell, num: true, title: "Mean HEM+ of the top three qualified regulars by HEM+." },
    { key: "n_above_avg", label: "Above-avg", fmt: fInt, num: true,
      title: "Hitters at HEM+ 100 or better / hitters in the rollup.",
      get: function (t) { return num(t.n_above_avg); },
      cell: function (t) { return fInt(t.n_above_avg) + (t.n_hitters != null ? '<span class="proj-dim"> / ' + fInt(t.n_hitters) + "</span>" : ""); } },
    { key: "team_pa", label: "PA", fmt: fInt, num: true },
  ];

  function hemExplainer() {
    return explainer("hem_plus", gloss("HEM+", "hem_plus")
      + ": sample-shrunk wOBA on the wRC+ scale; 100 = the PA-weighted average of hitters with 50+ PA. PA, SB and the"
      + " slash line are context and do not move it.");
  }

  function hitterScorecard() {
    var b = (hitterData && hitterData.backtest) || {};
    if (b.rho_hem_plus == null) return "";
    return '<div class="mlbstats-scorecard">'
      + '<span class="pal-sc-stat">' + gloss("HEM+", "hem_plus") + ' forward &rho; <b>'
      + b.rho_hem_plus + '</b><span class="proj-dim"> vs raw wOBA ' + (b.rho_woba == null ? EM_DASH : b.rho_woba)
      + ", OPS " + (b.rho_ops == null ? EM_DASH : b.rho_ops) + ", AVG " + (b.rho_avg == null ? EM_DASH : b.rho_avg)
      + "</span></span>"
      + '<span class="pal-sc-stat"><b>' + esc(b.n_pairs) + "</b> out-of-sample year pairs"
      + (b.seasons ? '<span class="proj-dim"> (' + esc(b.seasons) + " seasons)</span>" : "") + "</span>"
      + '<span class="pal-sc-note">' + esc(b.disclaimer || "") + "</span>"
      + "</div>";
  }

  function hitterHistorySeasons() {
    if (HITTER_HISTORY && HITTER_HISTORY.seasons && HITTER_HISTORY.seasons.length) return HITTER_HISTORY.seasons.slice();
    var cur = num(hitterData && hitterData.season);
    if (cur == null) return [];
    var out = [];
    for (var y = cur - 1; y >= cur - 5; y--) out.push(y);
    return out;
  }
  function loadHitterHistory() {
    if (HITTER_HISTORY || HITTER_HISTORY_LOADING) return;
    HITTER_HISTORY_LOADING = true;
    HITTER_HISTORY_ERROR = false;
    fetch(HITTER_HISTORY_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { HITTER_HISTORY = j; HITTER_HISTORY_LOADING = false; renderHitters(); })
      .catch(function () { HITTER_HISTORY_LOADING = false; HITTER_HISTORY_ERROR = true; renderHitters(); });
  }
  function hitterHistoryYear() {
    return (HITTER_HISTORY && HITTER_HISTORY.history && HITTER_HISTORY.history[hitterSeason]) || null;
  }
  // The unfiltered pool behind the active season pill (see relSourceRows).
  function hitterSourceRows() {
    if (hitterSeason !== "current") {
      var yr = hitterHistoryYear();
      return (yr && yr.hitters) || [];
    }
    return (hitterData && hitterData.hitters) || [];
  }
  function hitterMatch(r) {
    if (hitterQualifiedOnly && r.qualified === false) return false;
    if (hitterTeam && r.team !== hitterTeam) return false;
    if (!passesMin(r.pa, hitterMinPa)) return false;
    var q = hitterQuery.trim().toLowerCase();
    if (!q) return true;
    return (String(r.name || "").toLowerCase().indexOf(q) >= 0
      || String(r.team || "").toLowerCase().indexOf(q) >= 0);
  }
  function filteredHitters() {
    return ((hitterData && hitterData.hitters) || []).filter(hitterMatch);
  }
  function filteredHitterHistory() {
    var yr = hitterHistoryYear();
    return ((yr && yr.hitters) || []).filter(hitterMatch);
  }

  function hitterTabBar() {
    var tabs = [["hitters", "Hitters"], ["teams", "Team Lineups"], ["charts", "Lineup Charts"]];
    return '<div class="mlbstats-tabs" role="tablist">' + tabs.map(function (t) {
      var active = (t[0] === hitterView) ? " active" : "";
      return '<button type="button" class="mlbstats-tab' + active + '" data-hitterview="' + t[0] + '" role="tab" aria-selected="' + (t[0] === hitterView) + '">' + t[1] + "</button>";
    }).join("") + "</div>";
  }
  function hitterControls() {
    if (hitterView !== "hitters") return "";
    return '<div class="' + filtCls() + '">' + filtBtn(filtCount(hitterTeam, hitterMinPa, null, !hitterQualifiedOnly))
      + teamFilterChip(hitterTeam)
      + '<label class="mlbstats-ctl">'
      + '<input type="checkbox" id="mlbstats-hitter-qual"' + (hitterQualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-hitter-team", winSelectRows("hitters", hitterSourceRows()),
          hitterTeam, "hitters")
      + minSelect("mlbstats-hitter-minpa", minLabel("hitters", "min PA"), hitterMinPa,
          "Minimum plate appearances. Stacks with qualified only.")
      + gfxChip("mlbstats-hitter-gfx")
      + '<input class="mlbstats-search" type="search" id="mlbstats-hitter-q" placeholder="Search hitter or team" value="' + esc(hitterQuery) + '">'
      + "</div>";
  }

  function renderHitterBoard() {
    winCheck("hitters");
    if (isWindow("hitters")) {
      var wbhitters = renderWindowBoard("hitters");
      if (wbhitters) return wbhitters;
    }
    if (hitterSeason !== "current") return renderHitterHistory();
    var rows = sortRows(filteredHitters(), HITTER_COLS, hitterSort);
    var body = rows.length
      ? (function () {
          var note = '<div class="mlbstats-note">' + gloss("wRC+", "wrc_plus")
            + ": the industry's published number, not one of ours; read verbatim from MLB's feed, so this"
            + " site derives no wRC+. Unshrunk, so it bands wider than HEM+. " + gloss("WAR/PA+", "war_pa_plus")
            + ": value per PA with fielding and baserunning, 10 points = 1 SD.</div>";
          return proseFold("hit-about", rows.length + " hitters",
              hemExplainer() + hitterScorecard() + note
              + vintageNote(hitterData, [["multiyear", "HEM+ 3yr"], ["multiyear_war_rate", "WAR/PA+ 3yr"]]))
            + '<div class="mlbstats-scroll">' + renderTable(rows, HITTER_COLS, hitterSort, hitterData, "hit") + "</div>";
        })()
      : noRowsNote(hitterTeam, "No hitters match the current filters.");
    return yearsRow("hitters") + body;
  }

  function renderHitterHistory() {
    var pills = yearsRow("hitters");
    if (HITTER_HISTORY_ERROR) {
      return pills + pxState("failed",
        "Season history failed to load. Refresh to retry; if it persists the nightly build is mid-run. "
        + '<button type="button" class="chip" id="mlbstats-hitter-history-retry">Retry</button>', "mlbstats-load-error");
    }
    if (!HITTER_HISTORY) {
      loadHitterHistory();
      return pills + pxState("loading", "Loading the " + esc(hitterSeason) + " season leaderboard&hellip;");
    }
    if (HITTER_HISTORY_LOADING) {
      return pills + pxState("loading", "Loading the " + esc(hitterSeason) + " season leaderboard&hellip;");
    }
    var yr = hitterHistoryYear();
    if (!yr || !yr.hitters || !yr.hitters.length) {
      return pills + '<div class="mlbstats-empty">No leaderboard for the ' + esc(hitterSeason) + " season.</div>";
    }
    var sort = hitterHistorySort();
    var rows = sortRows(filteredHitterHistory(), HITTER_HISTORY_COLS, sort);
    var nQual = (yr.n_qualified != null) ? yr.n_qualified : yr.hitters.length;
    var cap = proseFold("hit-history-about",
      esc(hitterSeason) + " season, " + esc(nQual) + " qualified hitters",
      '<div class="mlbstats-note">' + gloss("HEM+", "hem_plus") + ": skill. Slash and volume: context.</div>");
    var hitHistCols = coveredCols(HITTER_HISTORY_COLS, rows);
    var table = rows.length
      ? '<div class="mlbstats-scroll">' + renderTable(rows, hitHistCols, sort, null, "hit") + "</div>"
      : noRowsNote(hitterTeam, "No hitters match the current filters.");
    return pills + cap + table;
  }

  function renderHitterTeams() {
    var rows = (hitterData && hitterData.teams) || [];
    rows = sortRows(rows, HITTER_TEAM_COLS, hitterTeamSort);
    if (!rows.length) return '<div class="mlbstats-empty">No team lineups to show yet.</div>';
    var note = '<div class="mlbstats-note">' + gloss("Offense+", "offense_plus") + ": PA-weighted "
      + gloss("HEM+", "hem_plus") + " of a lineup; 100 = average.</div>";
    return proseFold("hitteam-about", rows.length + " lineups", note)
      + '<div class="mlbstats-scroll">' + renderTable(rows, HITTER_TEAM_COLS, hitterTeamSort, hitterData, "hitteam") + "</div>";
  }

  // Lineup Charts: HEM+ distribution + skill-vs-volume scatter (clone of the
  // reliever viz), then per-team lineup ladders (clone of the bullpen depth).
  function hitterViz() {
    var qual = ((hitterData && hitterData.hitters) || []).filter(function (r) { return r.qualified !== false; });
    if (qual.length < 12) return "";
    var hems = qual.map(function (r) { return r.hem_plus; });
    var hist = chart("histogram", hems, { height: 108, min: 55, max: 175, highlightAbove: 130,
      refs: [{ at: 100, label: "avg" }], aria: "HEM+ distribution" });
    var pts = qual.filter(function (r) { return r.pa != null; }).map(function (r) {
      return { x: r.hem_plus, y: r.pa, label: r.name + "  HEM+ " + fInt(r.hem_plus) + "  PA " + fInt(r.pa),
               color: r.hem_plus >= 130 ? null : "var(--text-tertiary)" };
    });
    var sc = chart("scatter", pts, { height: 250, xLabel: "HEM+ (skill) →", yLabel: "↑ PA (volume)",
      xRef: 100, aria: "skill vs volume" });
    // Now vs next: this season's skill (HEM+) against the FORWARD projection
    // (pWOBA). Off-diagonal names are the interesting ones - above the pack =
    // the model believes more than the season shows (buy-lows), below = the
    // season is outrunning the projection (sell-highs / luck candidates).
    var ppts = qual.filter(function (r) { return r.pwoba != null; }).map(function (r) {
      return { x: r.hem_plus, y: r.pwoba,
               label: r.name + "  HEM+ " + fInt(r.hem_plus) + "  pWOBA " + f3(r.pwoba),
               color: r.hem_plus >= 130 ? null : "var(--text-tertiary)" };
    });
    var psc = ppts.length >= 12
      ? chart("scatter", ppts, { height: 250, xLabel: "HEM+ (this season) →",
          yLabel: "↑ pWOBA (projected next)", xRef: 100, aria: "skill now vs projected next" })
      : "";
    if (!hist && !sc && !psc) return "";
    var body = '<div class="mlbstats-viz">'
      + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">' + gloss("HEM+", "hem_plus")
      + ' distribution <span class="proj-dim">(qualified; cyan = 130+)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">HEM+ vs PA'
        + ' <span class="proj-dim">(bright = HEM+ 130+)</span></div>' + sc + "</div>" : "")
      + (psc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">HEM+ vs ' + gloss("pWOBA", "pwoba")
        + ' <span class="proj-dim">(this season against the next-season projection)</span></div>' + psc + "</div>" : "")
      + "</div>";
    return collapsible("hitters-viz", 'Charts <span class="proj-dim">(HEM+ distribution, vs PA, vs pWOBA)</span>', body);
  }

  // vs-RHP / vs-LHP segmented toggle for the constructed lineups.
  function lineupSplitToggle() {
    function b(val, label) {
      return '<button type="button" class="mlbstats-tab' + (hitterSplit === val ? " active" : "")
        + '" data-hittersplit="' + val + '" role="tab" aria-selected="' + (hitterSplit === val) + '">' + label + "</button>";
    }
    return '<div class="mlbstats-seasons" role="tablist" aria-label="Opposing pitcher hand">'
      + b("vr", "vs RHP") + b("vl", "vs LHP") + "</div>";
  }
  // ---- lineup cards: the nine, the bench, platoon options, regulars out ----
  // Every hand-specific number is SERVED (slot hem_plus_split / split_pa, the
  // bench row's per-hand dicts, teams[].platoon_options, teams[].regulars_out).
  // The page computes no marker and types no threshold: the thin floor is read
  // from lineup_cards.constants, and an older payload without it dims nothing.
  var EDGE_DOT = '<span class="bp-slot-adv" title="Platoon edge vs this hand">●</span>';
  // The shared .bp-slot grid reserves 92px for a bullpen role label; a lineup
  // row needs a slot number and a position, so the name gets the difference.
  var LC_GRID = ' style="grid-template-columns:64px 1fr auto"';
  function lcConst(key) {
    var c = (hitterData && hitterData.lineup_cards && hitterData.lineup_cards.constants) || {};
    return num(c[key]);
  }
  function splitHand() { return hitterSplit === "vl" ? "L" : "R"; }
  function handLabel() { return hitterSplit === "vl" ? "vs LHP" : "vs RHP"; }
  function hasEdge(bats, hand) {
    var b = String(bats || "").toUpperCase().charAt(0);
    return b === "S" || (b === "L" && hand === "R") || (b === "R" && hand === "L");
  }
  function posText(pos) { return (pos && pos.length) ? pos.slice(0, 3).join("/") : ""; }
  // Card names link to the merged player card when the mlbam maps (nameCell's
  // rule); plain text otherwise. Hitter keys are str(mlbam) by construction.
  function cardName(h) {
    var nm = esc(h.name || EM_DASH);
    var id = h.mlbam != null ? h.mlbam : (/^\d+$/.test(String(h.key || "")) ? h.key : null);
    var href = id != null ? playerHref({ mlbam: id }) : null;
    return href ? '<a class="mlbstats-name-link" href="' + href + '">' + nm + "</a>"
      : (!LINKS && id != null ? pendingName(id, nm) : nm);
  }
  function batsTxt(bats) { return bats ? '<span class="proj-dim"> ' + esc(bats) + "HB</span>" : ""; }
  function paTxt(pa) { return pa != null ? '<span class="proj-dim"> ' + fInt(pa) + " PA</span>" : ""; }
  // The number column. hand null = the neutral lineup (season HEM+ only).
  // Otherwise the per-hand HEM+ leads and the season number trails, dim;
  // data-kind names the state (split | thin | fallback) so each is countable.
  function lcValue(hand, v, pa, season) {
    if (!hand) return '<span class="bp-slot-rem ' + EephusTiers.clsInk(season, "ratio") + '">' + fInt(season) + "</span>";
    var lbl = handLabel();
    if (v == null) {
      // STATE, not a rank: there is no split line for this hand, so the cell
      // reads the neutral step whatever the season number is, exactly as it did
      // on the old neutral index class before the ruler. It carries no
      // vt-fam-* because no ladder drew it; test_value_ruler.py exempts it by
      // its data-kind.
      return '<span class="bp-slot-rem"><span class="vt-avg" data-kind="fallback" style="opacity:.6" title="No '
        + lbl + ' line; season HEM+ shown">' + fInt(season) + "<sup>s</sup></span></span>";
    }
    var floor = lcConst("min_split_pa");
    var thin = floor != null && (num(pa) || 0) < floor;
    var cell = thin
      ? '<span class="' + EephusTiers.cls(v, "ratio") + '" data-kind="thin" style="opacity:.6;text-decoration:underline dotted" title="'
        + fInt(pa) + " PA " + lbl + ", under " + fInt(floor) + '">'
      : '<span class="' + EephusTiers.cls(v, "ratio") + '" data-kind="split" title="' + lbl + " HEM+ on " + fInt(pa) + ' PA">';
    return '<span class="bp-slot-rem">' + cell + fInt(v) + '</span><span class="proj-dim" title="Season HEM+"> '
      + fInt(season) + "</span></span>";
  }
  function _slotRow(h, slotNum, meta, hand) {
    var pos = posText((meta || {}).pos);
    var adv = (hand && h.platoon_adv) ? EDGE_DOT : "";
    var v = hand ? h.hem_plus_split : null;
    return '<div class="bp-slot" data-slot="order"' + LC_GRID + ">"
      + '<span class="bp-slot-role">' + slotNum + (pos ? " " + esc(pos) : "") + "</span>"
      + '<span class="bp-slot-name"' + (h.name ? ' title="' + esc(h.name) + '"' : "") + ">" + cardName(h)
      + batsTxt(h.bats) + adv + paTxt(hand && v != null ? h.split_pa : h.pa) + "</span>"
      + lcValue(hand, v, h.split_pa, h.hem_plus)
      + "</div>";
  }
  function _optRow(o, b) {
    b = b || { key: o.bench_key, name: "" };
    return '<div class="bp-slot bp-slot--opt" data-opt="1" data-spa="' + esc(o.starter_split_pa)
      + '" data-bpa="' + esc(o.bench_split_pa) + '"' + LC_GRID + ">"
      + '<span class="bp-slot-role"></span>'
      + '<span class="bp-slot-name"' + (b.name ? ' title="' + esc(b.name) + '"' : "") + ">"
      + '<span class="bp-role" data-gl="platoon_option">PLT</span> ' + cardName(b)
      + batsTxt(o.bench_bats) + paTxt(o.bench_split_pa) + "</span>"
      + '<span class="bp-slot-rem"><span class="' + EephusTiers.cls(o.bench_split, "ratio") + '">' + fInt(o.bench_split)
      + '</span><span class="proj-dim"> +' + fInt(o.delta) + "</span></span>"
      + "</div>";
  }
  function _benchRow(b, hand, opts, names) {
    var v = hand ? (b.hem_plus_split || {})[hand] : null;
    var pa = hand ? (b.split_pa || {})[hand] : null;
    var chips = (opts || []).map(function (o) {
      return '<span class="bp-role" data-optb="1" data-gl="platoon_option" title="For '
        + esc(names[o.starter_key] || "") + " (" + esc(o.pos) + "), +" + fInt(o.delta) + '">PLT</span> ';
    }).join("");
    return '<div class="bp-slot bp-slot--bench" data-slot="bench"' + LC_GRID + ">"
      + '<span class="bp-slot-role">' + esc(posText(b.pos)) + "</span>"
      + '<span class="bp-slot-name"' + (b.name ? ' title="' + esc(b.name) + '"' : "") + ">" + cardName(b) + (chips ? " " + chips : "")
      + batsTxt(b.bats) + ((hand && hasEdge(b.bats, hand)) ? EDGE_DOT : "")
      + paTxt(hand && v != null ? pa : b.pa) + "</span>"
      + lcValue(hand, v, pa, b.hem_plus)
      + "</div>";
  }
  // Bench order for the toggled hand: split lines at or over the floor first,
  // then thin and fallback rows, each by value. Neutral: the served order.
  function _benchSorted(bench, hand) {
    if (!hand) return bench.slice();
    var floor = lcConst("min_split_pa");
    function val(b) {
      var v = (b.hem_plus_split || {})[hand];
      return v != null ? num(v) : num(b.hem_plus);
    }
    function full(b) {
      var v = (b.hem_plus_split || {})[hand], pa = num((b.split_pa || {})[hand]) || 0;
      return v != null && (floor == null || pa >= floor);
    }
    return bench.slice().sort(function (a, b) {
      var fa = full(a), fb = full(b);
      if (fa !== fb) return fa ? -1 : 1;
      return (val(b) || 0) - (val(a) || 0);
    });
  }
  function _outRow(r) {
    return '<div class="bp-slot bp-slot--bench" data-slot="out"' + LC_GRID + ">"
      + '<span class="bp-slot-role">Out</span>'
      + '<span class="bp-slot-name"' + (r.name ? ' title="' + esc(r.name) + '"' : "") + ">" + cardName(r)
      + batsTxt(r.bats) + paTxt(r.pa)
      + ' <span class="bp-prov">' + esc(r.status_label || "Not active") + "</span></span>"
      + '<span class="bp-slot-rem"><span class="proj-dim" title="Season HEM+">' + fInt(r.hem_plus) + "</span></span>"
      + "</div>";
  }
  // The constructed nine's PA-weighted mean HEM+ against one hand, computed
  // EXACTLY as leaderboard_vintages._pa_weighted_hem computes off_vs_lhp and
  // off_vs_rhp (owner decision 21, 2026-09-11: shown on the card): each slot's
  // per-hand value (hem_plus_split), its season hem_plus when that is absent,
  // weighted by the slot's season PA; a slot missing a value or a positive PA is
  // skipped, never counted as zero. Display only: nothing here reaches betting.
  function orderHandMean(order) {
    var totPa = 0, acc = 0;
    (order || []).forEach(function (s) {
      if (!s || typeof s !== "object") return;
      var hem = s.hem_plus_split;
      if (hem == null) hem = s.hem_plus;
      var pa = s.pa;
      if (hem == null || pa == null) return;
      hem = Number(hem); pa = Number(pa);
      if (!isFinite(hem) || !isFinite(pa) || pa <= 0) return;
      totPa += pa;
      acc += hem * pa;
    });
    return totPa > 0 ? Math.round(acc / totPa * 1000) / 1000 : null;
  }
  function handMeans(t) {
    if (t.platoon_applied === false || !t.orders) return "";
    var vl = orderHandMean(t.orders.vl), vr = orderHandMean(t.orders.vr);
    if (vl == null && vr == null) return "";
    function one(hand, v) {
      return '<span class="' + EephusTiers.cls(v, "ratio") + '" data-hand-mean="' + hand + '" data-raw="' + esc(v) + '">'
        + "vs " + hand + "HP " + fInt(v) + "</span>";
    }
    return '<span class="proj-dim" data-gl="hem_plus_vs_hand" title="PA-weighted vs-hand HEM+ of the nine">'
      + one("L", vl) + " &middot; " + one("R", vr) + "</span>";
  }
  function lineupLadders() {
    var teams = (hitterData && hitterData.teams) || [];
    if (!teams.length) return "";
    // platoon_applied=false on every club: one lineup, no toggle, no hand
    // column (the _ORDER_KEY_CONTRACT "flag" rule). Absent = an older payload.
    var splitOn = teams.some(function (t) { return t.platoon_applied !== false; });
    var sorted = teams.slice().sort(function (a, b) { return (num(b.offense_plus) || 0) - (num(a.offense_plus) || 0); });
    var cards = sorted.map(function (t) {
      var hand = (splitOn && t.platoon_applied !== false) ? splitHand() : null;
      // The hand's constructed order, or the one neutral nine; the HEM+ depth
      // ladder when neither was served.
      var order = hand ? ((t.orders && t.orders[hitterSplit]) || null)
        : (t.order_no_platoon || (t.orders && (t.orders.vr || t.orders.vl)) || null);
      var meta = t.slot_meta || {};
      var opts = hand ? ((t.platoon_options || {})[hitterSplit] || []) : [];
      var byStarter = {}, byBench = {}, benchByKey = {}, names = {};
      opts.forEach(function (o) {
        (byStarter[o.starter_key] = byStarter[o.starter_key] || []).push(o);
        (byBench[o.bench_key] = byBench[o.bench_key] || []).push(o);
      });
      (t.bench || []).forEach(function (b) { benchByKey[b.key] = b; });
      var slots;
      if (order && order.length) {
        order.forEach(function (h) { names[h.key] = h.name; });
        slots = order.map(function (h) {
          return _slotRow(h, h.slot, meta[h.key], hand)
            + (byStarter[h.key] || []).map(function (o) { return _optRow(o, benchByKey[o.bench_key]); }).join("");
        }).join("");
      } else {
        slots = (t.lineup || []).slice(0, 9).map(function (h, i) { return _slotRow(h, i + 1, null, null); }).join("");
      }
      var head = hand
        ? '<div class="bp-slot"' + LC_GRID + '><span class="bp-slot-role">#</span><span class="bp-slot-name proj-dim">Hitter</span>'
          + '<span class="bp-slot-rem proj-dim">' + gloss(handLabel(), "hem_plus_vs_hand") + "</span></div>"
        : "";
      var bench = _benchSorted(t.bench || [], hand);
      var benchHtml = bench.length
        ? '<div class="bp-bench-head">Bench</div>'
          + bench.map(function (b) { return _benchRow(b, hand, byBench[b.key], names); }).join("")
        : "";
      var out = t.regulars_out || [];
      var outHtml = out.length
        ? '<div class="bp-bench-head" title="Regulars not on the active roster">Out</div>' + out.map(_outRow).join("")
        : "";
      return '<div class="bp-depth-card"><div class="bp-depth-head">'
        + '<span class="bp-depth-team">' + logo(t.team) + esc(t.team) + "</span>"
        + '<span class="rem-plus ' + EephusTiers.cls(t.offense_plus, "ratio") + '" data-gl="offense_plus">Offense+ ' + fInt(t.offense_plus) + "</span>"
        + handMeans(t)
        + "</div>" + head + slots + benchHtml + outHtml + "</div>";
    }).join("");
    var lc = (hitterData && hitterData.lineup_cards) || {};
    var floor = lcConst("min_split_pa");
    var note = splitOn
      ? "Order built on season " + gloss("HEM+", "hem_plus") + ". Number: " + gloss("vs-hand HEM+", "hem_plus_vs_hand")
        + ", season dim" + (floor != null ? "; dotted under " + fInt(floor) + " PA" : "") + "; <sup>s</sup> season fallback. "
        + "● platoon edge. " + gloss("PLT", "platoon_option") + " platoon option."
        + (lc.reason ? ' <span class="proj-dim">' + esc(lc.reason) + "</span>" : "")
      : "Handedness split unavailable this build; one lineup shown, season " + gloss("HEM+", "hem_plus") + ".";
    return '<div class="mlbstats-note">' + note + "</div>"
      + (splitOn ? lineupSplitToggle() : "")
      + '<div class="bp-depth-grid">' + cards + "</div>";
  }

  function renderHitterCharts() {
    if (!hitterData || !((hitterData.hitters) || []).length) {
      return '<div class="mlbstats-empty">No lineup charts to show yet.</div>';
    }
    return hitterViz() + lineupLadders();
  }

  function renderHitters() {
    var root = document.getElementById("mlbstats-hitters-root");
    if (!root) return;
    if (!hitterData) {
      root.innerHTML = hitterErr
        ? pxState("failed", "Data failed to load. Refresh to retry; "
          + "if it persists the nightly build is mid-run. "
          + '<button type="button" class="chip" id="mlbstats-hitter-retry">Retry</button>', "mlbstats-load-error")
        : pxState("unmeasured", 'Hitter Leaderboards are being computed from the MLB season. '
          + "Check back shortly.");
      var retry = document.getElementById("mlbstats-hitter-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = pxState("loading", "Loading&hellip;");
        loadHitters();
      });
      return;
    }
    var inner = (hitterView === "teams") ? renderHitterTeams()
      : (hitterView === "charts") ? renderHitterCharts() : renderHitterBoard();
    // No #mlbstats-banner div for this section; the freshness line leads the
    // section's own root.
    root.innerHTML = bannerHTML(hitterData, { sec: "hitters" }) + teamBasisNote(sectionBasis("hitters", hitterData, HITTER_HISTORY))
      + hitterTabBar() + hitterControls() + inner;
    bindHitterEvents(root);
    wireGlossary(root);
  }

  function bindHitterEvents(root) {
    bindCollapse(root);
    stampCsv("hitters", root);
    bindColViews(root, function () { renderHittersInPlace(); });
    root.querySelectorAll("[data-hitterview]").forEach(function (b) {
      b.addEventListener("click", function () {
        hitterView = b.getAttribute("data-hitterview");
        writeHash();
        renderHitters();
      });
    });
    root.querySelectorAll("[data-hittersplit]").forEach(function (b) {
      b.addEventListener("click", function () {
        hitterSplit = b.getAttribute("data-hittersplit");
        renderHitters();
      });
    });
    var q = root.querySelector("#mlbstats-hitter-q");
    if (q) q.addEventListener("input", function () { hitterQuery = q.value; renderHittersInPlace(); });
    var qual = root.querySelector("#mlbstats-hitter-qual");
    if (qual) qual.addEventListener("change", function () { hitterQualifiedOnly = qual.checked; renderHittersInPlace(); });
    var hTeam = root.querySelector("#mlbstats-hitter-team");
    if (hTeam) hTeam.addEventListener("change", function () {
      hitterTeam = hTeam.value || "";
      writeHash();
      renderHittersInPlace("mlbstats-hitter-team");
    });
    var hMin = root.querySelector("#mlbstats-hitter-minpa");
    if (hMin) hMin.addEventListener("input", function () {
      hitterMinPa = readMin(hMin);
      renderHittersInPlace("mlbstats-hitter-minpa");
    });
    var hitterGfx = root.querySelector("#mlbstats-hitter-gfx");
    if (hitterGfx) hitterGfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      var rows = isWindow("hitters") ? windowGfxRows("hitters")
        : (hitterSeason === "current") ? sortRows(filteredHitters(), HITTER_COLS, hitterSort)
        : sortRows(filteredHitterHistory(), HITTER_HISTORY_COLS, hitterHistorySort());
      EEPHUS_GFX.open(_mlbstatsBoardSpec("hitters", rows));
    });
    var hretry = root.querySelector("#mlbstats-hitter-history-retry");
    if (hretry) hretry.addEventListener("click", function () {
      HITTER_HISTORY_ERROR = false;
      loadHitterHistory();
      renderHitters();
    });
    root.querySelectorAll(".mlbstats-table th[data-col]").forEach(function (th) {
      bindSortKeys(th, root, function () {
        var key = th.getAttribute("data-col");
        var cols = (hitterView === "teams") ? HITTER_TEAM_COLS
          : (hitterSeason !== "current") ? HITTER_HISTORY_COLS : HITTER_COLS;
        var col = null; cols.forEach(function (c) { if (c.key === key) col = c; });
        if (!col || (!col.num && col.kind !== "name" && col.kind !== "team")) return;
        var sort = (hitterView === "teams") ? hitterTeamSort : hitterSort;
        if (sort.key === key) sort.asc = !sort.asc;
        else { sort.key = key; sort.asc = !!col.asc; }
        writeHash();
        renderHitters();
      });
    });
  }

  function renderHittersInPlace(focusId) {
    var root = document.getElementById("mlbstats-hitters-root");
    if (!root) return;
    var inner = (hitterView === "teams") ? renderHitterTeams()
      : (hitterView === "charts") ? renderHitterCharts() : renderHitterBoard();
    root.innerHTML = bannerHTML(hitterData, { sec: "hitters" }) + teamBasisNote(sectionBasis("hitters", hitterData, HITTER_HISTORY))
      + hitterTabBar() + hitterControls() + inner;
    restoreFocus(root, focusId || "mlbstats-hitter-q");
    bindHitterEvents(root);
    wireGlossary(root);
  }

  function loadHitters() {
    hitterErr = false;
    fetch(HITTER_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { hitterData = j; renderHitters(); })
      .catch(function () { hitterData = null; hitterErr = true; renderHitters(); });
  }

  function initHitters() {
    if (hitterInit) { renderHitters(); return; }
    hitterInit = true;
    renderHitters();
    loadHitters();
  }

  // ===========================================================================
  // Section 4: Leverage Leaderboards (S-1) -- realized in-game leverage IMPACT.
  // ---------------------------------------------------------------------------
  // Self-computed from the MLB StatsAPI winProbability feed (mlb_leverage), the
  // two sides the reliever board doesn't cover: BATTERS (WPA, average leverage
  // faced pLI, Clutch, context-neutral WPA/LI) and STARTERS (per-start WPA,
  // WPA/LI). A DESCRIPTIVE realized-value board (the RIV+ / xREM+ precedent), not
  // a predictive model -- so no forward scorecard. Renders into
  // #mlbstats-leverage-root; reuses every shared helper.
  // ===========================================================================
  var LEVERAGE_URL = "/data/leverage_leaderboards.json";
  var leverageData = null;
  var leverageErr = false;
  var leverageInit = false;
  var leverageView = "batters";                 // batters | starters
  var leverageBatSort = { key: "wpa", asc: false };
  var leverageStarterSort = { key: "wpa", asc: false };
  var leverageQuery = "";
  var leverageQualifiedOnly = true;
  var leverageTeam = "";                        // "" = all clubs

  // Yearly leverage history (leverage_history.json) is lazy-fetched the first
  // time a past-season pill is picked. leverageSeason is "current" for the live
  // board or a season string like "2025"; it applies to whichever view (batters
  // or starters) is active. The history payload carries only qualified rows.
  var LEV_HISTORY_URL = "/data/leverage_history.json";
  var leverageSeason = "current";
  var leverageHistory = null;
  var leverageHistoryLoading = false;
  var leverageHistoryErr = false;

  // Signed, tabular WPA-family cell: positive (added win probability) reads up,
  // negative reads down, a neutral band stays quiet.
  function levSignedCell(v, digits, band) {
    var n = num(v);
    if (n == null) return EM_DASH;
    var d = (digits == null) ? 2 : digits;
    var b = band || 0;
    var col = n > b ? "var(--up)" : n < -b ? "var(--down)" : "var(--text-tertiary)";
    return '<span style="color:' + col + ';font-variant-numeric:tabular-nums;">'
      + (n > 0 ? "+" : "") + n.toFixed(d) + "</span>";
  }

  // Skill/impact core first (WPA), then the leverage context (pLI, Clutch,
  // context-neutral WPA/LI) and the volume column.
  var BAT_LEV_COLS = [
    { key: "name", label: "Batter", term: null, sortable: true, kind: "name", asc: true },
    { key: "wpa", label: "WPA", term: "wpa", num: true, desc: true,
      title: "Win probability his plate appearances added.",
      cell: function (r) { return levSignedCell(r.wpa, 2, 0); } },
    { key: "pli", label: "pLI", term: "pli", num: true, desc: true,
      title: "Average Leverage Index faced; 1.0 = neutral.",
      cell: function (r) { return r.pli == null ? EM_DASH : f2(r.pli); } },
    { key: "clutch", label: "Clutch", term: "clutch", num: true, desc: true,
      title: "WPA/pLI minus WPA/LI. Timing, not skill.",
      cell: function (r) { return levSignedCell(r.clutch, 2, 0.5); } },
    { key: "wpa_li", label: "WPA/LI", term: "wpa_li", num: true, desc: true,
      title: "WPA with the leverage of his spots removed.",
      cell: function (r) { return levSignedCell(r.wpa_li, 2, 0); } },
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true,
      title: "Position-player eWAR this season." },
    { key: "pa", label: "PA", fmt: fInt, num: true, title: "Plate appearances (context)" },
  ];

  var STARTER_LEV_COLS = [
    { key: "name", label: "Starter", term: null, sortable: true, kind: "name", asc: true },
    { key: "wpa", label: "WPA", term: "wpa", num: true, desc: true,
      title: "Win probability his starts added.",
      cell: function (r) { return levSignedCell(r.wpa, 2, 0); } },
    { key: "wpa_per_start", label: "WPA/start", num: true, desc: true,
      title: "WPA per game started.",
      cell: function (r) { return levSignedCell(r.wpa_per_start, 3, 0); } },
    { key: "wpa_li", label: "WPA/LI", term: "wpa_li", num: true, desc: true,
      title: "WPA with the leverage of his spots removed.",
      cell: function (r) { return levSignedCell(r.wpa_li, 2, 0); } },
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true,
      title: "Pitching eWAR this season. Swingmen included." },
    { key: "gs", label: "GS", fmt: fInt, num: true, title: "Official games started." },
    { key: "starts", label: "Starts", fmt: fInt, num: true,
      title: "Starts in the win-probability feed: the WPA/start denominator. Can differ from GS." },
  ];

  function levCols() { return leverageView === "starters" ? STARTER_LEV_COLS : BAT_LEV_COLS; }
  function levSort() { return leverageView === "starters" ? leverageStarterSort : leverageBatSort; }

  function levExplainer() {
    return explainer("wpa", gloss("WPA", "wpa")
      + ": realized win probability added, computed here from the MLB win-probability feed. "
      + gloss("pLI", "pli") + ": average leverage faced (1.0 = neutral). " + gloss("Clutch", "clutch")
      + ": WPA/pLI minus WPA/LI. Descriptive, not a projection.");
  }

  // The row source for the active view honors the season pill: the live board
  // for "current", else the matching batters/starters list from the history
  // payload (which carries only that season's qualified players).
  function leverageSourceRows() {
    if (leverageSeason !== "current") {
      var yr = (leverageHistory && leverageHistory.history && leverageHistory.history[leverageSeason]) || null;
      return (yr && (leverageView === "starters" ? yr.starters : yr.batters)) || [];
    }
    return (leverageData && (leverageView === "starters" ? leverageData.starters : leverageData.batters)) || [];
  }
  function filteredLeverage() {
    var rows = leverageSourceRows();
    var q = leverageQuery.trim().toLowerCase();
    return rows.filter(function (r) {
      if (leverageQualifiedOnly && r.qualified === false) return false;
      if (leverageTeam && r.team !== leverageTeam) return false;
      if (!q) return true;
      return (String(r.name || "").toLowerCase().indexOf(q) >= 0
        || String(r.team || "").toLowerCase().indexOf(q) >= 0);
    });
  }

  // ---- yearly history pills (leverage_history.json) -------------------------
  // Seed the pill list from the live season before the history file loads (the
  // five completed seasons before it), then the file's own list is authoritative.
  function leverageHistorySeasons() {
    if (leverageHistory && leverageHistory.seasons && leverageHistory.seasons.length) return leverageHistory.seasons.slice();
    var cur = num(leverageData && leverageData.season);
    if (cur == null) return [];
    var out = [];
    for (var y = cur - 1; y >= cur - 5; y--) out.push(y);
    return out;
  }
  function loadLeverageHistory() {
    if (leverageHistory || leverageHistoryLoading) return;
    leverageHistoryLoading = true;
    leverageHistoryErr = false;
    fetch(LEV_HISTORY_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { leverageHistory = j; leverageHistoryLoading = false; renderLeverage(); })
      .catch(function () { leverageHistoryLoading = false; leverageHistoryErr = true; renderLeverage(); });
  }

  // ---- charts (WPA distribution + production-vs-leverage scatter) ------------
  // Descriptive read of the qualified pool for the active view + season. Batters
  // get the leverage story the memo asked for: WPA distribution + a WPA/LI
  // (context-neutral production) vs pLI (leverage faced) scatter, dots tinted by
  // Clutch. Starters have no pLI, so their scatter is context-neutral skill
  // (WPA/LI) vs the leverage/timing delta (WPA minus WPA/LI); above the zero line
  // = more value realized in higher-leverage spots than context-neutral rate.
  function leverageViz() {
    var isStart = (leverageView === "starters");
    // Read the raw season pool (NOT filteredLeverage) so the search box never
    // reshapes or hides the distribution -- the sibling viz functions do the same.
    var qual = leverageSourceRows().filter(function (r) { return r.qualified !== false; });
    if (qual.length < 10) return "";
    var hist, pts, sc, body;
    if (isStart) {
      hist = chart("histogram", qual.map(function (r) { return r.wpa_per_start; }),
        { height: 108, highlightAbove: 0.04, refs: [{ at: 0, label: "0" }], aria: "WPA per start distribution" });
      pts = qual.filter(function (r) { return r.wpa_li != null && r.wpa != null; }).map(function (r) {
        var timing = r.wpa - r.wpa_li;      // realized minus context-neutral = leverage/timing
        return { x: r.wpa_li, y: timing, color: timing >= 0 ? null : "var(--text-tertiary)",
                 label: r.name + "  WPA " + fSigned(r.wpa) + "  WPA/LI " + fSigned(r.wpa_li)
                   + "  timing " + fSigned(timing) };
      });
      sc = chart("scatter", pts, { height: 250, xLabel: "WPA/LI (context-neutral) →", yLabel: "↑ WPA over context (timing)",
        xRef: 0, yRef: 0, aria: "context-neutral skill vs leverage timing" });
      if (!hist && !sc) return "";
      body = '<div class="mlbstats-viz">'
        + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">WPA per start'
        + ' <span class="proj-dim">(qualified; cyan = 0.04+)</span></div>' + hist + "</div>"
        + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">WPA/LI vs timing'
          + ' <span class="proj-dim">(timing = WPA minus WPA/LI; above 0 = more value in higher-leverage spots)</span></div>' + sc + "</div>" : "")
        + "</div>";
      return collapsible("leverage-viz", 'Charts <span class="proj-dim">(WPA per start, WPA/LI vs timing)</span>', body);
    }
    hist = chart("histogram", qual.map(function (r) { return r.wpa; }),
      { height: 108, highlightAbove: 2, refs: [{ at: 0, label: "0" }], aria: "WPA distribution" });
    pts = qual.filter(function (r) { return r.wpa_li != null && r.pli != null; }).map(function (r) {
      var c = r.clutch;
      var col = (c == null) ? "var(--text-tertiary)" : (c >= 0.5 ? "var(--up)" : (c <= -0.5 ? "var(--down)" : "var(--text-tertiary)"));
      return { x: r.wpa_li, y: r.pli, color: col,
               label: r.name + "  WPA/LI " + fSigned(r.wpa_li) + "  pLI " + f2(r.pli)
                 + "  Clutch " + (c == null ? EM_DASH : fSigned(c)) };
    });
    sc = chart("scatter", pts, { height: 250, xLabel: "WPA/LI (context-neutral) →", yLabel: "↑ pLI (leverage faced)",
      xRef: 0, yRef: 1, aria: "production vs leverage faced" });
    if (!hist && !sc) return "";
    body = '<div class="mlbstats-viz">'
      + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">' + gloss("WPA", "wpa")
      + ' distribution <span class="proj-dim">(qualified; cyan = 2+)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">WPA/LI vs ' + gloss("pLI", "pli")
        + ' <span class="proj-dim">(green = Clutch +0.5 or more, red = -0.5 or less)</span></div>' + sc + "</div>" : "")
      + "</div>";
    return collapsible("leverage-viz", 'Charts <span class="proj-dim">(WPA distribution, WPA/LI vs pLI)</span>', body);
  }

  function leverageTabBar() {
    var tabs = [["batters", "Batters"], ["starters", "Starters"]];
    return '<div class="mlbstats-tabs" role="tablist">' + tabs.map(function (t) {
      var active = (t[0] === leverageView) ? " active" : "";
      return '<button type="button" class="mlbstats-tab' + active + '" data-leverageview="' + t[0]
        + '" role="tab" aria-selected="' + (t[0] === leverageView) + '">' + t[1] + "</button>";
    }).join("") + "</div>";
  }
  function leverageControls() {
    // No min-PA / min-GS control here: this board is already gated to qualified
    // players by the export and the volume column is context, not a filter the
    // memo asked for. Team is, and it is the one narrowing a 400-row WPA board
    // actually needs.
    return '<div class="' + filtCls() + '">' + filtBtn(filtCount(leverageTeam, null, null, !leverageQualifiedOnly))
      + teamFilterChip(leverageTeam)
      + '<label class="mlbstats-ctl">'
      + '<input type="checkbox" id="mlbstats-leverage-qual"' + (leverageQualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-leverage-team", winSelectRows("leverage", leverageSourceRows()),
          leverageTeam, "leverage")
      + gfxChip("mlbstats-leverage-gfx")
      + '<input class="mlbstats-search" type="search" id="mlbstats-leverage-q" placeholder="Search player or team" value="' + esc(leverageQuery) + '">'
      + "</div>";
  }
  function leverageCoverage() {
    var cov;
    if (leverageSeason !== "current") {
      var yr = (leverageHistory && leverageHistory.history && leverageHistory.history[leverageSeason]) || null;
      cov = (yr && yr.coverage) || null;
    } else {
      cov = (leverageData && leverageData.coverage) || null;
    }
    if (!cov || cov.games == null) return "";
    return '<span class="proj-dim"> &middot; ' + esc(cov.games)
      + (cov.games_total != null ? " / " + esc(cov.games_total) : "") + " games of play-by-play</span>";
  }

  function renderLeverageBoard() {
    winCheck("leverage");
    if (isWindow("leverage")) {
      var wbleverage = renderWindowBoard("leverage");
      if (wbleverage) return wbleverage;
    }
    // A past season reads from the lazy-loaded history file; the inline
    // loading / error states mirror the reliever board so a failed fetch never
    // blanks the board.
    if (leverageSeason !== "current") {
      if (leverageHistoryErr) {
        return yearsRow("leverage") + pxState("failed",
          "Season history failed to load. Refresh to retry; if it persists the nightly build is mid-run. "
          + '<button type="button" class="chip" id="mlbstats-leverage-history-retry">Retry</button>', "mlbstats-load-error");
      }
      if (!leverageHistory || leverageHistoryLoading) {
        if (!leverageHistory) loadLeverageHistory();
        return yearsRow("leverage") + pxState("loading", "Loading the "
          + esc(leverageSeason) + " season leaderboard&hellip;");
      }
      if (!leverageHistory.history || !leverageHistory.history[leverageSeason]) {
        return yearsRow("leverage") + '<div class="mlbstats-empty">No leaderboard for the '
          + esc(leverageSeason) + " season.</div>";
      }
    }
    var cols = levCols(), sort = levSort();
    var rows = sortRows(filteredLeverage(), cols, sort);
    if (!rows.length) {
      return yearsRow("leverage") + noRowsNote(leverageTeam, "No players match the current filters.");
    }
    var isStart = (leverageView === "starters");
    var seasonLbl = (leverageSeason === "current") ? "" : (esc(leverageSeason) + " season, ");
    // The coverage count rides the fold HEAD, not the folded body: the shell
    // banner suppresses its own copy here (noCoverage) because only this board
    // knows which season the pill is on, so folding it away would leave a phone
    // reader with no games-walked count at all.
    return yearsRow("leverage") + proseFold("lev-about",
        seasonLbl + rows.length + (isStart ? " starters" : " batters") + leverageCoverage(),
        levExplainer())
      + leverageViz() + '<div class="mlbstats-scroll">' + renderTable(rows, cols, sort, leverageData, leverageView === "starters" ? "levsp" : "levbat") + "</div>";
  }

  function renderLeverage() {
    var root = document.getElementById("mlbstats-leverage-root");
    if (!root) return;
    if (!leverageData) {
      root.innerHTML = leverageErr
        ? pxState("failed", "Data failed to load. Refresh to retry; "
          + "if it persists the nightly build is mid-run. "
          + '<button type="button" class="chip" id="mlbstats-leverage-retry">Retry</button>', "mlbstats-load-error")
        : pxState("unmeasured", 'Leverage Leaderboards are being computed from the MLB win-probability '
          + "feed. Check back shortly.");
      var retry = document.getElementById("mlbstats-leverage-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = pxState("loading", "Loading&hellip;");
        loadLeverage();
      });
      return;
    }
    // noCoverage: the board note below already prints a SEASON-AWARE coverage
    // count (leverageCoverage), and the live figure is wrong for a past-season
    // pill. One number, in the place that knows which season it belongs to.
    // levExplainer() is no longer prepended here: it rides the board's own
    // methodology fold (renderLeverageBoard), so it does not stand above a
    // load error or a "no rows" state either.
    root.innerHTML = bannerHTML(leverageData, { noCoverage: true, sec: "leverage" })
      + teamBasisNote(sectionBasis("leverage", leverageData, leverageHistory))
      + leverageTabBar() + leverageControls() + renderLeverageBoard();
    bindLeverageEvents(root);
    wireGlossary(root);
  }

  function renderLeverageInPlace(focusId) {
    var root = document.getElementById("mlbstats-leverage-root");
    if (!root) return;
    root.innerHTML = bannerHTML(leverageData, { noCoverage: true, sec: "leverage" })
      + teamBasisNote(sectionBasis("leverage", leverageData, leverageHistory))
      + leverageTabBar() + leverageControls() + renderLeverageBoard();
    restoreFocus(root, focusId || "mlbstats-leverage-q");
    bindLeverageEvents(root);
    wireGlossary(root);
  }

  function bindLeverageEvents(root) {
    bindCollapse(root);
    stampCsv("leverage", root);
    root.querySelectorAll("[data-leverageview]").forEach(function (b) {
      b.addEventListener("click", function () {
        leverageView = b.getAttribute("data-leverageview");
        writeHash();
        renderLeverage();
      });
    });
    var q = root.querySelector("#mlbstats-leverage-q");
    if (q) q.addEventListener("input", function () { leverageQuery = q.value; renderLeverageInPlace(); });
    var qual = root.querySelector("#mlbstats-leverage-qual");
    if (qual) qual.addEventListener("change", function () { leverageQualifiedOnly = qual.checked; renderLeverageInPlace(); });
    var levTeam = root.querySelector("#mlbstats-leverage-team");
    if (levTeam) levTeam.addEventListener("change", function () {
      leverageTeam = levTeam.value || "";
      writeHash();
      renderLeverageInPlace("mlbstats-leverage-team");
    });
    var levGfx = root.querySelector("#mlbstats-leverage-gfx");
    if (levGfx) levGfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      EEPHUS_GFX.open(_mlbstatsBoardSpec("leverage", isWindow("leverage")
        ? windowGfxRows("leverage")
        : sortRows(filteredLeverage(), levCols(), levSort())));
    });
    var lhretry = root.querySelector("#mlbstats-leverage-history-retry");
    if (lhretry) lhretry.addEventListener("click", function () {
      leverageHistoryErr = false;
      loadLeverageHistory();
      renderLeverage();
    });
    root.querySelectorAll(".mlbstats-table th[data-col]").forEach(function (th) {
      bindSortKeys(th, root, function () {
        var key = th.getAttribute("data-col");
        var cols = levCols();
        var col = null; cols.forEach(function (c) { if (c.key === key) col = c; });
        if (!col || (!col.num && col.kind !== "name")) return;
        var sort = levSort();
        if (sort.key === key) sort.asc = !sort.asc;
        else { sort.key = key; sort.asc = !!col.asc; }
        writeHash();
        renderLeverage();
      });
    });
  }

  function loadLeverage() {
    leverageErr = false;
    fetch(LEVERAGE_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { leverageData = j; renderLeverage(); })
      .catch(function () { leverageData = null; leverageErr = true; renderLeverage(); });
  }

  function initLeverage() {
    if (leverageInit) { renderLeverage(); return; }
    leverageInit = true;
    renderLeverage();
    loadLeverage();
  }

  // ===========================================================================
  // Section 5: Defense Leaderboards (DEM+ fielding-rate skill).
  // ---------------------------------------------------------------------------
  // Renders data/defense_leaderboards.json (defense_export.py) into Fielders /
  // Team Defense / Defense Charts, a clone of the Hitter section. DEM+ is the
  // sample-shrunk published fielding rate on 100 + 10z, so its SD is exactly 10
  // and it bands on the z ladder (93 / 107 / 120), NEVER the ratio one: it is not
  // on the HEM+ ruler. Fld and Frm are FanGraphs' published values read from
  // MLB's feed; the positional term inside Def is OUR ladder (Position Fit,
  // owner decision 18, 2026-09-11), with FanGraphs' own beside it as Pos (FG).
  // This page computes none of them. Copy is column titles plus
  // glossary links (owner copy rule, 2026-09-11), and every accuracy number is
  // read from the payload's backtest block, never typed here.
  // ===========================================================================
  var DEFENSE_URL = "/data/defense_leaderboards.json";
  var DEFENSE_HISTORY_URL = "/data/defense_history.json";
  var POS_ORDER = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"];

  var defenseData = null;
  var defenseErr = false;
  var defenseInit = false;
  var defenseView = "fielders";               // fielders | teams | charts
  var defenseSort = { key: "dem_plus", asc: false };
  var defenseTeamSort = { key: "team_dem_plus", asc: false };
  var defenseQuery = "";
  var defenseQualifiedOnly = true;
  var defenseTeam = "";                       // "" = all clubs
  var defenseMinInn = null;                   // null = no floor
  var defensePos = [];                        // empty = all positions; else an OR set

  var defenseSeason = "current";
  var DEFENSE_HISTORY = null;
  var DEFENSE_HISTORY_LOADING = false;
  var DEFENSE_HISTORY_ERROR = false;

  // Primary position, with the innings split in the tooltip for a fielder who
  // played more than one. Not sortable (text, and not a name/team column).
  function posCell(r) {
    if (!r.pos) return EM_DASH;
    var pi = r.pos_inn || {};
    var keys = POS_ORDER.filter(function (p) { return pi[p] != null; });
    var split = keys.length > 1
      ? keys.map(function (p) { return p + " " + f1(pi[p]); }).join(", ") : "";
    return "<span" + (split ? ' title="Innings: ' + esc(split) + '"' : "") + ">" + esc(r.pos)
      + (split ? '<span class="proj-dim"> +' + (keys.length - 1) + "</span>" : "") + "</span>";
  }

  // Skill core first (DEM+), then the published run columns and the volume
  // context. DEM+ rides the z family for the reason WAR/PA+ does on the hitter
  // board: 100 + 10z has SD exactly 10, and 93 / 107 / 120 is the one colour
  // ruler the player page shares for that family.
  var DEFENSE_COLS = [
    { key: "name", label: "Fielder", term: null, sortable: true, kind: "name", asc: true },
    { key: "pos", label: "Pos", title: "Primary position (most defensive innings).", cell: posCell },
    { key: "dem_plus", label: "DEM+", term: "dem_plus", num: true, desc: true, isRem: true,
      title: "100 = pool average; 10 points = 1 SD. Not the HEM+ scale. p = percentile on this board.",
      get: function (r) { return r.dem_plus; },
      cell: function (r) {
        if (r.dem_plus == null) return EM_DASH;
        var s = remCell(r.dem_plus);
        if (r.dem_plus_pct != null) s += '<span class="proj-dim mlbstats-pct"> p' + fInt(r.dem_plus_pct) + "</span>";
        return s;
      } },
    { key: "dem_plus_3yr", label: "DEM+ 3yr", term: "dem_plus_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear",
      get: function (r) { return r.dem_plus_3yr; },
      cell: function (r) {
        return r.dem_plus_3yr == null ? EM_DASH : win3yrCell(r, "dem_plus_3yr", "under 2 seasons or 1,000 innings");
      } },
    { key: "dem_plus_pos_pct", label: "Pos %ile", fmt: fInt, num: true, desc: true,
      title: "DEM+ percentile among fielders at the same primary position." },
    { key: "fld_total", label: "Fld", term: "fielding_runs", fmt: fSigned, num: true,
      title: "PUBLISHED, NOT COMPUTED HERE. FanGraphs fielding runs; framing included for catchers." },
    { key: "fld_runs", label: "Fld ex-Frm", term: "fielding_runs", fmt: fSigned, num: true,
      title: "PUBLISHED, NOT COMPUTED HERE. Fielding runs without framing; equals Fld for non-catchers." },
    { key: "frm_runs", label: "Frm", term: "framing_runs", fmt: fSigned, num: true,
      title: "PUBLISHED, NOT COMPUTED HERE. Catcher framing runs; catchers only." },
    { key: "pos_runs", label: "Pos (ours)", term: "positional_adjustment", fmt: fSigned, num: true,
      title: "OUR LADDER. Position Fit's positional ladder (Baseball-Reference scale), pro-rated by innings at each fielding position; DH time excluded. The term in Def. Context; does not move DEM+." },
    { key: "pos_runs_fg", label: "Pos (FG)", term: "positional_adjustment", fmt: fSigned, num: true,
      title: "PUBLISHED, NOT COMPUTED HERE. FanGraphs' positional adjustment, DH time included. For comparison; not in Def." },
    { key: "def_runs", label: "Def", term: "def_runs", fmt: fSigned, num: true,
      title: "Fld + Pos (ours): FanGraphs fielding and framing plus our positional ladder. Not FanGraphs Def." },
    { key: "rate_1000", label: "Fld/1000", fmt: fSigned, num: true,
      title: "Fld per 1,000 defensive innings, unshrunk." },
    { key: "rate_1000_shrunk", label: "Shrunk/1000", fmt: fSigned, num: true,
      title: "Fld/1000 pulled toward the position mean by innings. DEM+ is scored on this rate." },
    { key: "inn", label: "Inn", fmt: f1, num: true, title: "Defensive innings, C through RF." },
    { key: "fld_pct", label: "Fld%", fmt: f3, num: true, title: "Fielding percentage (context)." },
    // Savant catcher blocking and throwing (savant_catcher.py), display only,
    // on rows whose primary position is C. No club total is built from them.
    { key: "c_blk_runs", label: "Blk runs", term: "catcher_blocking", fmt: fSignedInt, num: true,
      title: "Runs saved by blocking pitches in the dirt, Savant's run value. From Baseball Savant's catcher leaderboards; catchers only. Display only: DEM+, eWAR and the team totals do not read it." },
    { key: "c_blk_aa", label: "Blocks AA", term: "catcher_blocking", fmt: fSignedInt, num: true,
      title: "Blocks above average on the pitches in the next column. From Baseball Savant's catcher leaderboards; catchers only. Display only: DEM+, eWAR and the team totals do not read it." },
    { key: "c_blk_pitches", label: "Blk pitches", term: "catcher_blocking", fmt: fInt, num: true,
      title: "Pitches received that the blocking model scores. From Baseball Savant's catcher leaderboards; catchers only. Display only: DEM+, eWAR and the team totals do not read it." },
    { key: "c_cs_runs", label: "CS runs", term: "catcher_throwing", fmt: fSigned, num: true,
      title: "Runs saved on stolen-base attempts, Savant's run value. From Baseball Savant's catcher leaderboards; catchers only. Display only: DEM+, eWAR and the team totals do not read it." },
    { key: "c_cs_aa", label: "CS AA", term: "catcher_throwing", fmt: fSigned, num: true,
      title: "Caught stealing above the expected count on the attempts in the next column. From Baseball Savant's catcher leaderboards; catchers only. Display only: DEM+, eWAR and the team totals do not read it." },
    { key: "c_sb_att", label: "SB att", term: "catcher_throwing", fmt: fInt, num: true,
      title: "Stolen-base attempts with him catching. From Baseball Savant's catcher leaderboards; catchers only. Display only: DEM+, eWAR and the team totals do not read it." },
    { key: "c_pop", label: "Pop 2B", term: "pop_time", fmt: f2, num: true, asc: true,
      title: "Average pop time on throws to second base, in seconds. From Baseball Savant's catcher leaderboards; catchers only. Display only: DEM+, eWAR and the team totals do not read it." },
    { key: "c_exchange", label: "Exchange", term: "pop_time", fmt: f2, num: true, asc: true,
      title: "Average time from catch to release, in seconds. From Baseball Savant's catcher leaderboards; catchers only. Display only: DEM+, eWAR and the team totals do not read it." },
    { key: "c_arm", label: "C arm", term: "pop_time", fmt: f1, num: true,
      title: "Average arm strength on throws, in mph. From Baseball Savant's catcher leaderboards; catchers only. Display only: DEM+, eWAR and the team totals do not read it." },
    { key: "hem_plus", label: "HEM+", term: "hem_plus", fmt: hemCell, num: true, desc: true,
      title: "HEM+ from the Hitter board (ratio scale), for the glove vs bat read." },
    // Whole-player eWAR on a fielding board: its fielding term comes from a
    // different frame than Fld and DEM+, and the payload NAMES that frame in
    // frame.ewar_note, which renderTable appends to this title. Never type a
    // frame here: the eWAR v3 switch rewrites the sentence with no JS change.
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true, noteFrom: "ewar_note",
      title: "Whole-player eWAR this season." },
  ];

  // History rows (defense_history.json) carry the season line but not the
  // 3-year window join, the per-position percentile, the shrunk rate or the
  // HEM+ join, so those columns drop rather than render blank. eWAR is NOT in
  // the list: it is a season count the history export joins per (player,
  // season), and coveredCols holds it back until a season carries it.
  var DEFENSE_HISTORY_DROP = { dem_plus_3yr: 1, dem_plus_pos_pct: 1, rate_1000_shrunk: 1, hem_plus: 1,
    c_blk_runs: 1, c_blk_aa: 1, c_blk_pitches: 1, c_cs_runs: 1, c_cs_aa: 1, c_sb_att: 1,
    c_pop: 1, c_exchange: 1, c_arm: 1 };
  var DEFENSE_HISTORY_COLS = historyTitle(
    DEFENSE_COLS.filter(function (c) { return !DEFENSE_HISTORY_DROP[c.key]; }),
    "war", "Whole-player eWAR for the season shown.");
  function defenseHistorySort() {
    var ok = false;
    DEFENSE_HISTORY_COLS.forEach(function (c) { if (c.key === defenseSort.key) ok = true; });
    return ok ? defenseSort : { key: "dem_plus", asc: false };
  }

  var DEFENSE_TEAM_COLS = [
    { key: "team", label: "Team", sortable: true, kind: "team", asc: true },
    { key: "team_dem_plus", label: "Team DEM+", term: "team_dem_plus", fmt: remCell, num: true, desc: true, isRem: true,
      title: "Innings-weighted DEM+ of the club's fielders. 100 + 10z scale." },
    { key: "n_above_avg", label: "Above-avg", fmt: fInt, num: true,
      title: "Fielders at DEM+ 100 or better / fielders in the rollup.",
      get: function (t) { return num(t.n_above_avg); },
      cell: function (t) { return fInt(t.n_above_avg) + (t.n_fielders != null ? '<span class="proj-dim"> / ' + fInt(t.n_fielders) + "</span>" : ""); } },
    { key: "team_fld_total", label: "Fld", term: "fielding_runs", fmt: fSigned, num: true,
      title: "PUBLISHED, NOT COMPUTED HERE. Sum of FanGraphs fielding runs, catcher framing included when the rollup includes catchers." },
    { key: "team_frm_runs", label: "Frm", term: "framing_runs", fmt: fSigned, num: true,
      title: "PUBLISHED, NOT COMPUTED HERE. Sum of the club's catcher framing runs; already inside Fld." },
    { key: "team_pos_runs", label: "Pos (ours)", term: "positional_adjustment", fmt: fSigned, num: true,
      title: "OUR LADDER. Sum of the fielders' Pos (ours): Position Fit's ladder pro-rated by innings, DH time excluded." },
    { key: "team_pos_runs_fg", label: "Pos (FG)", term: "positional_adjustment", fmt: fSigned, num: true,
      title: "PUBLISHED, NOT COMPUTED HERE. Sum of FanGraphs' positional adjustments, for comparison." },
    { key: "team_inn", label: "Inn", fmt: fInt, num: true, title: "Defensive innings in the rollup." },
  ];

  function defenseExplainer() {
    return explainer("dem_plus", gloss("DEM+", "dem_plus") + " is computed here. "
      + gloss("Fld", "fielding_runs") + " and " + gloss("Frm", "framing_runs")
      + " are FanGraphs' published values; " + gloss("Pos (ours)", "positional_adjustment")
      + ", the term in Def, is our positional ladder, with FanGraphs' own beside it as Pos (FG).");
  }

  function defenseScorecard() {
    var b = (defenseData && defenseData.backtest) || {};
    if (b.rho_dem_plus == null) return "";
    function v(x) { return x == null ? EM_DASH : esc(x); }
    return '<div class="mlbstats-scorecard">'
      + '<span class="pal-sc-stat">' + gloss("DEM+", "dem_plus") + " forward &rho; <b>"
      + v(b.rho_dem_plus) + '</b><span class="proj-dim"> vs raw rate ' + v(b.rho_raw_rate)
      + ", Fld% " + v(b.rho_fld_pct) + ", Inn " + v(b.rho_innings) + "</span></span>"
      + '<span class="pal-sc-stat"><b>' + v(b.n_pairs) + "</b> out-of-sample year pairs"
      + (b.seasons ? '<span class="proj-dim"> (' + esc(b.seasons) + " seasons)</span>" : "") + "</span>"
      + '<span class="pal-sc-note">' + esc(b.disclaimer || "") + "</span>"
      + "</div>";
  }

  function defenseHistorySeasons() {
    if (DEFENSE_HISTORY && DEFENSE_HISTORY.seasons && DEFENSE_HISTORY.seasons.length) return DEFENSE_HISTORY.seasons.slice();
    var cur = num(defenseData && defenseData.season);
    if (cur == null) return [];
    var out = [];
    for (var y = cur - 1; y >= cur - 5; y--) out.push(y);
    return out;
  }
  function loadDefenseHistory() {
    if (DEFENSE_HISTORY || DEFENSE_HISTORY_LOADING) return;
    DEFENSE_HISTORY_LOADING = true;
    DEFENSE_HISTORY_ERROR = false;
    fetch(DEFENSE_HISTORY_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { DEFENSE_HISTORY = j; DEFENSE_HISTORY_LOADING = false; renderDefense(); })
      .catch(function () { DEFENSE_HISTORY_LOADING = false; DEFENSE_HISTORY_ERROR = true; renderDefense(); });
  }
  function defenseHistoryYear() {
    return (DEFENSE_HISTORY && DEFENSE_HISTORY.history && DEFENSE_HISTORY.history[defenseSeason]) || null;
  }
  // The unfiltered pool behind the active season pill (see relSourceRows).
  function defenseSourceRows() {
    if (defenseSeason !== "current") {
      var yr = defenseHistoryYear();
      return (yr && yr.fielders) || [];
    }
    return (defenseData && defenseData.fielders) || [];
  }
  function defenseMatch(r) {
    if (defenseQualifiedOnly && r.qualified === false) return false;
    if (defenseTeam && r.team !== defenseTeam) return false;
    if (defensePos.length && defensePos.indexOf(r.pos) < 0) return false;
    if (!passesMin(r.inn, defenseMinInn)) return false;
    var q = defenseQuery.trim().toLowerCase();
    if (!q) return true;
    return (String(r.name || "").toLowerCase().indexOf(q) >= 0
      || String(r.team || "").toLowerCase().indexOf(q) >= 0);
  }
  function filteredDefense() {
    return ((defenseData && defenseData.fielders) || []).filter(defenseMatch);
  }
  function filteredDefenseHistory() {
    var yr = defenseHistoryYear();
    return ((yr && yr.fielders) || []).filter(defenseMatch);
  }
  // A past-season pill shows a CLOSED season, and the history file carries its
  // own team_basis sentence for that case (a 2021 line under a 2026 club); the
  // live board's sentence describes an in-season trade. Each board discloses
  // its own. Team Defense and Defense Charts are always the live season.

  // Position chips: the roleChips markup (season-pill buttons, OR set, "All"
  // clears), keyed on the primary position in diamond order.
  function posChips(rows, active, idPrefix) {
    var counts = {}, n = 0;
    (rows || []).forEach(function (r) { if (r.pos) { counts[r.pos] = (counts[r.pos] || 0) + 1; n++; } });
    if (!n) return "";
    var list = POS_ORDER.filter(function (p) { return counts[p]; });
    Object.keys(counts).sort().forEach(function (p) { if (list.indexOf(p) < 0) list.push(p); });
    var all = !active.length;
    return '<div class="mlbstats-seasons mlbstats-roles" role="group" aria-label="Filter by position">'
      + '<span class="mlbstats-roles-lbl">Pos</span>'
      + '<button type="button" class="mlbstats-season' + (all ? " active" : "") + '" id="' + idPrefix
      + 'all" data-mlbpos="" aria-pressed="' + all + '">All</button>'
      + list.map(function (p) {
          var on = active.indexOf(p) >= 0;
          return '<button type="button" class="mlbstats-season' + (on ? " active" : "") + '" id="'
            + idPrefix + roleSlug(p) + '" data-mlbpos="' + esc(p) + '" aria-pressed="' + on + '">'
            + esc(p) + '<span class="proj-dim"> ' + counts[p] + "</span></button>";
        }).join("") + "</div>";
  }

  function defenseTabBar() {
    var tabs = [["fielders", "Fielders"], ["teams", "Team Defense"], ["charts", "Defense Charts"]];
    return '<div class="mlbstats-tabs" role="tablist">' + tabs.map(function (t) {
      var active = (t[0] === defenseView) ? " active" : "";
      return '<button type="button" class="mlbstats-tab' + active + '" data-defenseview="' + t[0] + '" role="tab" aria-selected="' + (t[0] === defenseView) + '">' + t[1] + "</button>";
    }).join("") + "</div>";
  }
  function defenseControls() {
    if (defenseView === "teams") {
      var teamChip = gfxChip("mlbstats-defense-teams-gfx");
      return teamChip ? '<div class="mlbstats-bar">' + teamChip + "</div>" : "";
    }
    if (defenseView !== "fielders") return "";
    var pool = defenseSourceRows();
    return '<div class="' + filtCls() + '">' + filtBtn(filtCount(defenseTeam, defenseMinInn, defensePos, !defenseQualifiedOnly))
      + teamFilterChip(defenseTeam)
      + '<label class="mlbstats-ctl">'
      + '<input type="checkbox" id="mlbstats-defense-qual"' + (defenseQualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-defense-team", winSelectRows("defense", pool), defenseTeam, "defense")
      + minSelect("mlbstats-defense-mininn", minLabel("defense", "min Inn"), defenseMinInn,
          "Minimum defensive innings. Stacks with qualified only.")
      + gfxChip("mlbstats-defense-gfx")
      + '<input class="mlbstats-search" type="search" id="mlbstats-defense-q" placeholder="Search fielder or team" value="' + esc(defenseQuery) + '">'
      + "</div>"
      + posChips(pool, defensePos, "mlbstats-defense-pos-");
  }

  function renderDefenseBoard() {
    winCheck("defense");
    if (isWindow("defense")) {
      var wbdefense = renderWindowBoard("defense");
      if (wbdefense) return wbdefense;
    }
    if (defenseSeason !== "current") return renderDefenseHistory();
    var rows = sortRows(filteredDefense(), DEFENSE_COLS, defenseSort);
    var body = rows.length
      ? proseFold("def-about", rows.length + " fielders",
          defenseExplainer() + defenseScorecard()
          + vintageNote(defenseData, [["multiyear", "DEM+ 3yr"]]))
        + '<div class="mlbstats-scroll">' + renderTable(rows, DEFENSE_COLS, defenseSort, defenseData, "def") + "</div>"
      : noRowsNote(defenseTeam, "No fielders match the current filters.");
    return yearsRow("defense") + body;
  }

  function renderDefenseHistory() {
    // Start the fetch BEFORE reading the state, so a fetch that settles at
    // once (a warm cache, the smoke harness) paints the board rather than
    // leaving a stale "Loading" over it.
    if (!DEFENSE_HISTORY && !DEFENSE_HISTORY_LOADING && !DEFENSE_HISTORY_ERROR) loadDefenseHistory();
    var pills = yearsRow("defense");
    if (DEFENSE_HISTORY_ERROR) {
      return pills + pxState("failed",
        "Season history failed to load. Refresh to retry; if it persists the nightly build is mid-run. "
        + '<button type="button" class="chip" id="mlbstats-defense-history-retry">Retry</button>', "mlbstats-load-error");
    }
    if (!DEFENSE_HISTORY || DEFENSE_HISTORY_LOADING) {
      return pills + pxState("loading", "Loading the " + esc(defenseSeason) + " season leaderboard&hellip;");
    }
    var yr = defenseHistoryYear();
    if (!yr || !yr.fielders || !yr.fielders.length) {
      return pills + '<div class="mlbstats-empty">No leaderboard for the ' + esc(defenseSeason) + " season.</div>";
    }
    var sort = defenseHistorySort();
    var rows = sortRows(filteredDefenseHistory(), DEFENSE_HISTORY_COLS, sort);
    var nQual = (yr.n_qualified != null) ? yr.n_qualified : yr.fielders.length;
    var cap = proseFold("def-history-about",
      esc(defenseSeason) + " season, " + esc(nQual) + " qualified fielders", defenseExplainer());
    var defHistCols = coveredCols(DEFENSE_HISTORY_COLS, rows);
    var defHistMeta = { frame: (defenseData && defenseData.frame) || null };
    var table = rows.length
      ? '<div class="mlbstats-scroll">' + renderTable(rows, defHistCols, sort, defHistMeta, "def") + "</div>"
      : noRowsNote(defenseTeam, "No fielders match the current filters.");
    return pills + cap + table;
  }

  function renderDefenseTeams() {
    var rows = sortRows((defenseData && defenseData.teams) || [], DEFENSE_TEAM_COLS, defenseTeamSort);
    if (!rows.length) return '<div class="mlbstats-empty">No team defenses to show yet.</div>';
    var tf = (defenseData && defenseData.team_rollup_framing) || {};
    var note = explainer("team_dem_plus", gloss("Team DEM+", "team_dem_plus") + ": innings-weighted DEM+"
      + (tf.included === false ? "; catchers are excluded from it and from the team run totals."
        : tf.included === true ? "; catchers are included, framing too." : "."));
    return proseFold("defteam-about", rows.length + " clubs", note)
      + '<div class="mlbstats-scroll">' + renderTable(rows, DEFENSE_TEAM_COLS, defenseTeamSort, defenseData, "defteam") + "</div>";
  }

  // Defense Charts: DEM+ distribution, DEM+ by innings and DEM+ by HEM+ over the
  // qualified live pool, then one alignment card per club.
  function defenseViz() {
    var qual = ((defenseData && defenseData.fielders) || []).filter(function (r) {
      return r.qualified !== false && r.dem_plus != null;
    });
    if (qual.length < 12) return "";
    var hist = chart("histogram", qual.map(function (r) { return r.dem_plus; }), { height: 108, min: 60, max: 140,
      highlightAbove: 120, refs: [{ at: 100, label: "avg" }], aria: "DEM+ distribution" });
    var pts = qual.filter(function (r) { return r.inn != null; }).map(function (r) {
      return { x: r.dem_plus, y: r.inn,
               label: r.name + "  " + (r.pos || "") + "  DEM+ " + fInt(r.dem_plus) + "  Inn " + f1(r.inn),
               color: r.dem_plus >= 120 ? null : "var(--text-tertiary)" };
    });
    var sc = chart("scatter", pts, { height: 250, xLabel: "DEM+ →", yLabel: "↑ Inn",
      xRef: 100, aria: "DEM+ by innings" });
    var hpts = qual.filter(function (r) { return r.hem_plus != null; }).map(function (r) {
      return { x: r.dem_plus, y: r.hem_plus,
               label: r.name + "  " + (r.pos || "") + "  DEM+ " + fInt(r.dem_plus) + "  HEM+ " + fInt(r.hem_plus),
               color: r.dem_plus >= 120 ? null : "var(--text-tertiary)" };
    });
    var hsc = hpts.length >= 12
      ? chart("scatter", hpts, { height: 250, xLabel: "DEM+ →", yLabel: "↑ HEM+",
          xRef: 100, yRef: 100, aria: "DEM+ by HEM+" })
      : "";
    if (!hist && !sc && !hsc) return "";
    var body = '<div class="mlbstats-viz">'
      + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">' + gloss("DEM+", "dem_plus")
      + ' distribution <span class="proj-dim">(qualified fielders)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">DEM+ by innings</div>' + sc + "</div>" : "")
      + (hsc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">DEM+ by ' + gloss("HEM+", "hem_plus")
        + "</div>" + hsc + "</div>" : "")
      + "</div>";
    return collapsible("defense-viz", 'Charts <span class="proj-dim">(DEM+ distribution, by innings, by HEM+)</span>', body);
  }

  // One card per club, a slot per position (the bullpen depth-card markup, so
  // site.css needs nothing new). With the club framing rollup on, the catcher
  // slot carries his own frm_runs; a payload built with it off does not, and
  // the slot then looks his up on the fielder board by MLBAM id.
  function alignmentCards() {
    var teams = (defenseData && defenseData.teams) || [];
    if (!teams.length) return "";
    var frm = {};
    ((defenseData && defenseData.fielders) || []).forEach(function (r) {
      if (r.mlbam != null && r.frm_runs != null) frm[String(r.mlbam)] = r.frm_runs;
    });
    function rung(p) { var i = POS_ORDER.indexOf(p); return i < 0 ? POS_ORDER.length : i; }
    var sorted = teams.slice().sort(function (a, b) { return (num(b.team_dem_plus) || 0) - (num(a.team_dem_plus) || 0); });
    var cards = sorted.map(function (t) {
      var slots = (t.alignment || []).filter(function (a) { return a && a.pos; })
        .sort(function (a, b) { return rung(a.pos) - rung(b.pos); })
        .map(function (a) {
          var f = a.pos !== "C" ? null
            : (a.frm_runs != null ? a.frm_runs : (a.mlbam != null ? frm[String(a.mlbam)] : null));
          return '<div class="bp-slot">'
            + '<span class="bp-slot-role">' + esc(a.pos) + "</span>"
            + '<span class="bp-slot-name"' + (a.name ? ' title="' + esc(a.name) + '"' : "") + ">" + esc(a.name || EM_DASH)
            + (a.inn_at_pos != null ? '<span class="proj-dim"> ' + f1(a.inn_at_pos) + " inn</span>" : "")
            + (f != null ? '<span class="proj-dim"> Frm ' + fSigned(f) + "</span>" : "") + "</span>"
            + '<span class="bp-slot-rem ' + EephusTiers.clsInk(a.dem_plus, "z") + '">' + fInt(a.dem_plus) + "</span>"
            + "</div>";
        }).join("");
      return '<div class="bp-depth-card"><div class="bp-depth-head">'
        + '<span class="bp-depth-team">' + logo(t.team) + esc(t.team) + "</span>"
        + '<span class="rem-plus ' + EephusTiers.cls(t.team_dem_plus, "z") + '" data-gl="team_dem_plus">Team DEM+ ' + fInt(t.team_dem_plus) + "</span>"
        + "</div>" + slots + "</div>";
    }).join("");
    return '<div class="mlbstats-note">Alignment: the active-roster fielder with the most innings at each position.</div>'
      + '<div class="bp-depth-grid">' + cards + "</div>";
  }

  function renderDefenseCharts() {
    if (!defenseData || !((defenseData.fielders) || []).length) {
      return '<div class="mlbstats-empty">No defense charts to show yet.</div>';
    }
    return defenseViz() + alignmentCards();
  }

  function defenseInner() {
    return (defenseView === "teams") ? renderDefenseTeams()
      : (defenseView === "charts") ? renderDefenseCharts() : renderDefenseBoard();
  }

  function renderDefense() {
    var root = document.getElementById("mlbstats-defense-root");
    if (!root) return;
    if (!defenseData) {
      root.innerHTML = defenseErr
        ? pxState("failed", "Data failed to load. Refresh to retry; "
          + "if it persists the nightly build is mid-run. "
          + '<button type="button" class="chip" id="mlbstats-defense-retry">Retry</button>', "mlbstats-load-error")
        : pxState("unmeasured", "Defense Leaderboards are being computed. Check back shortly.");
      var retry = document.getElementById("mlbstats-defense-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = pxState("loading", "Loading&hellip;");
        loadDefense();
      });
      return;
    }
    // Build the body first: a past-season render can start the history fetch,
    // and the team-basis note should read whichever payload the board shows.
    var inner = defenseInner();
    root.innerHTML = bannerHTML(defenseData, { sec: "defense" }) + teamBasisNote(sectionBasis("defense", defenseData, DEFENSE_HISTORY))
      + defenseTabBar() + defenseControls() + inner;
    bindDefenseEvents(root);
    wireGlossary(root);
  }

  function bindDefenseEvents(root) {
    bindCollapse(root);
    stampCsv("defense", root);
    bindColViews(root, function () { renderDefenseInPlace(); });
    root.querySelectorAll("[data-defenseview]").forEach(function (b) {
      b.addEventListener("click", function () {
        defenseView = b.getAttribute("data-defenseview");
        writeHash();
        renderDefense();
      });
    });
    var q = root.querySelector("#mlbstats-defense-q");
    if (q) q.addEventListener("input", function () { defenseQuery = q.value; renderDefenseInPlace(); });
    var qual = root.querySelector("#mlbstats-defense-qual");
    if (qual) qual.addEventListener("change", function () { defenseQualifiedOnly = qual.checked; renderDefenseInPlace(); });
    var dTeam = root.querySelector("#mlbstats-defense-team");
    if (dTeam) dTeam.addEventListener("change", function () {
      defenseTeam = dTeam.value || "";
      writeHash();
      renderDefenseInPlace("mlbstats-defense-team");
    });
    var dMin = root.querySelector("#mlbstats-defense-mininn");
    if (dMin) dMin.addEventListener("input", function () {
      defenseMinInn = readMin(dMin);
      renderDefenseInPlace("mlbstats-defense-mininn");
    });
    root.querySelectorAll("[data-mlbpos]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-mlbpos");
        if (!v) defensePos = [];
        else {
          var i = defensePos.indexOf(v);
          if (i >= 0) defensePos.splice(i, 1); else defensePos.push(v);
        }
        renderDefenseInPlace(b.id || null);
      });
    });
    var dGfx = root.querySelector("#mlbstats-defense-gfx");
    if (dGfx) dGfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      var rows = isWindow("defense") ? windowGfxRows("defense")
        : (defenseSeason === "current") ? sortRows(filteredDefense(), DEFENSE_COLS, defenseSort)
        : sortRows(filteredDefenseHistory(), DEFENSE_HISTORY_COLS, defenseHistorySort());
      EEPHUS_GFX.open(_mlbstatsBoardSpec("defense", rows));
    });
    var dTeamGfx = root.querySelector("#mlbstats-defense-teams-gfx");
    if (dTeamGfx) dTeamGfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      EEPHUS_GFX.open(_mlbstatsBoardSpec("teamdefense",
        sortRows((defenseData && defenseData.teams) || [], DEFENSE_TEAM_COLS, defenseTeamSort)));
    });
    var dhretry = root.querySelector("#mlbstats-defense-history-retry");
    if (dhretry) dhretry.addEventListener("click", function () {
      DEFENSE_HISTORY_ERROR = false;
      loadDefenseHistory();
      renderDefense();
    });
    root.querySelectorAll(".mlbstats-table th[data-col]").forEach(function (th) {
      bindSortKeys(th, root, function () {
        var key = th.getAttribute("data-col");
        var cols = (defenseView === "teams") ? DEFENSE_TEAM_COLS
          : (defenseSeason !== "current") ? DEFENSE_HISTORY_COLS : DEFENSE_COLS;
        var col = null; cols.forEach(function (c) { if (c.key === key) col = c; });
        if (!col || (!col.num && col.kind !== "name" && col.kind !== "team")) return;
        var sort = (defenseView === "teams") ? defenseTeamSort : defenseSort;
        if (sort.key === key) sort.asc = !sort.asc;
        else { sort.key = key; sort.asc = !!col.asc; }
        writeHash();
        renderDefense();
      });
    });
  }

  function renderDefenseInPlace(focusId) {
    var root = document.getElementById("mlbstats-defense-root");
    if (!root) return;
    var inner = defenseInner();
    root.innerHTML = bannerHTML(defenseData, { sec: "defense" }) + teamBasisNote(sectionBasis("defense", defenseData, DEFENSE_HISTORY))
      + defenseTabBar() + defenseControls() + inner;
    restoreFocus(root, focusId || "mlbstats-defense-q");
    bindDefenseEvents(root);
    wireGlossary(root);
  }

  function loadDefense() {
    defenseErr = false;
    fetch(DEFENSE_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { defenseData = j; renderDefense(); })
      .catch(function () { defenseData = null; defenseErr = true; renderDefense(); });
  }

  function initDefense() {
    if (defenseInit) { renderDefense(); return; }
    defenseInit = true;
    renderDefense();
    loadDefense();
  }

  // ===========================================================================
  // Generate GFX: shared EEPHUS_GFX board specs, one builder for every board.
  // ---------------------------------------------------------------------------
  // Each board's control row carries a "Generate GFX" chip; the click handler
  // passes the view id plus the SAME filtered+sorted rows the table renders, so
  // the graphic always matches what's on screen (season pill, qualified-only,
  // search, and sort are all baked into `rows`). The module accent is gold; the
  // columns mirror each board's headline metric and then its eWAR (the value
  // column the boards themselves lead with since the 2026-09-11 overhaul), with
  // the secondary columns marked wideOnly so the narrow (1080-wide) formats stay
  // legible. Team Defense carries no eWAR: a fielding rollup would repeat the
  // lineup total on another frame. A card whose board has no eWAR to print on a
  // past season (hitters) swaps in the columns that season does carry.
  // HAND-OFF, spec section 8 item 10: the eWAR SECTION's own card
  // (# | Player | eWAR | Bat | Pitch | Role) belongs to the wave-5 step that
  // adds that section, because its rows, its payload and its season label do
  // not exist until war_leaderboards.json does.
  // Titles auto-derive from the board; the subtitle carries the active
  // season/window selection. Mirrors fa.js / projections.js.
  // ===========================================================================
  function gfxChip(id) {
    return (window.EEPHUS_GFX && EEPHUS_GFX.chipHTML) ? EEPHUS_GFX.chipHTML(id, "Generate GFX") : "";
  }

  function _mlbstatsBoardSpec(view, rows) {
    rows = rows || [];
    // Season/window label for the subtitle: the live board reports the season +
    // as-of date; a past-season pill reports "<year> season". Count noun varies.
    // The window rides the subtitle, so a range board's graphic cannot leave the
    // page looking like one season.
    function seasonBits(seasonSel, data, noun) {
      var s;
      if (seasonSel && seasonSel.lo != null) {
        s = (seasonSel.lo === seasonSel.hi)
          ? (seasonSel.lo + " season")
          : (seasonSel.lo + "-" + seasonSel.hi + ", " + (seasonSel.hi - seasonSel.lo + 1) + " seasons");
      } else if (seasonSel && seasonSel !== "current") {
        s = seasonSel + " season";
      } else {
        s = (data && data.season != null) ? ("Season " + data.season) : "";
        if (data && data.as_of) s += (s ? " · " : "") + "through " + data.as_of;
      }
      return (s ? s + " · " : "") + rows.length + " " + noun;
    }
    function spec(title, subtitle, filenameBase, caption, board) {
      return { kind: "board", module: "MLB Stats", accentToken: "--accent-gold",
        title: title, subtitle: subtitle, url: "eephus.io/mlbstats",
        filenameBase: filenameBase, caption: caption, board: board };
    }

    if (view === "relievers") {
      var relRows = rows.map(function (r, i) {
        return { cells: [
          { t: i + 1 },
          { t: r.name || EM_DASH, sub: r.team || undefined },
          { t: fInt(r.rem_plus), c: "accent" },
          { t: f1(r.war) },
          { t: fPct(r.k_bb_pct) },
          { t: f2(r.era) },
          { t: f1(r.ip) },
          { t: f2(r.gmli) },
        ] };
      });
      return spec("MLB Stats · REM+ Leaders",
        seasonBits(WIN["bullpen"] || "current", DATA, "relievers"),
        "mlbstats-rem-leaders",
        "REM+ = FIP-based, sample-shrunk run-prevention skill" + winCardNote("bullpen"),
        { defaultCount: 25, counts: [10, 25, 50], legend: "REM+ 100 = average reliever", columns: [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.33 },
          { label: "REM+", frac: 0.11 },
          { label: "eWAR", frac: 0.11 },
          { label: "K-BB%", frac: 0.11 },
          { label: "ERA", frac: 0.10, wideOnly: true },
          { label: "IP", frac: 0.09, wideOnly: true },
          { label: "gmLI", frac: 0.10, wideOnly: true },
        ], rows: relRows });
    }

    if (view === "bullpens") {
      var bpRows = rows.map(function (t, i) {
        return { cells: [
          { t: i + 1 },
          { t: t.team || EM_DASH },
          { t: fInt(t.bullpen_plus), c: "accent" },
          { t: f1(t.team_war) },
          { t: fInt(t.high_lev_core_rem) },
          { t: f1(t.relief_ip) },
        ] };
      });
      return spec("MLB Stats · Bullpen+ Leaders",
        seasonBits("current", DATA, "bullpens"),
        "mlbstats-bullpen-rankings",
        "Bullpen+ = relief-IP-weighted REM+",
        { defaultCount: 30, counts: [10, 30], legend: "Bullpen+ 100 = average bullpen", columns: [
          { label: "#", frac: 0.08 },
          { label: "Team", frac: 0.30 },
          { label: "Bullpen+", frac: 0.17 },
          { label: "eWAR", frac: 0.13 },
          { label: "Hi-Lev Core", frac: 0.16, wideOnly: true },
          { label: "Relief IP", frac: 0.16 },
        ], rows: bpRows });
    }

    if (view === "starters") {
      var spRows = rows.map(function (r, i) {
        return { cells: [
          { t: i + 1 },
          { t: r.name || EM_DASH, sub: r.team || undefined },
          { t: fInt(r.sem_plus), c: "accent" },
          { t: f1(r.war) },
          { t: fPct(r.k_bb_pct) },
          { t: f2(r.era) },
          { t: f1(r.ip) },
          { t: fInt(r.gs) },
        ] };
      });
      return spec("MLB Stats · SEM+ Leaders",
        seasonBits(WIN["starters"] || "current", starterData, "starters"),
        "mlbstats-sem-leaders",
        "SEM+ = FIP-based, sample-shrunk starter run-prevention skill" + winCardNote("starters"),
        { defaultCount: 25, counts: [10, 25, 50], legend: "SEM+ 100 = average starter", columns: [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.33 },
          { label: "SEM+", frac: 0.12 },
          { label: "eWAR", frac: 0.12 },
          { label: "K-BB%", frac: 0.12 },
          { label: "ERA", frac: 0.09, wideOnly: true },
          { label: "IP", frac: 0.09, wideOnly: true },
          { label: "GS", frac: 0.08, wideOnly: true },
        ], rows: spRows });
    }

    if (view === "hitters") {
      var hitPast = (hitterSeason !== "current");
      var hitRows = rows.map(function (r, i) {
        return { cells: hitPast ? [
          { t: i + 1 },
          { t: r.name || EM_DASH, sub: r.team || undefined },
          { t: fInt(r.hem_plus), c: "accent" },
          { t: f3(r.woba) },
          { t: f3(r.ops) },
          { t: fInt(r.pa) },
        ] : [
          { t: i + 1 },
          { t: r.name || EM_DASH, sub: r.team || undefined },
          { t: fInt(r.hem_plus), c: "accent" },
          { t: fInt(r.wrc_plus) },
          { t: f1(r.war) },
          { t: fInt(r.pa) },
          { t: f3(r.ops) },
        ] };
      });
      var hitCols = hitPast ? [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.37 },
          { label: "HEM+", frac: 0.12 },
          { label: "Shrunk wOBA", frac: 0.15 },
          { label: "OPS", frac: 0.13 },
          { label: "PA", frac: 0.10, wideOnly: true },
        ] : [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.35 },
          { label: "HEM+", frac: 0.12 },
          { label: "wRC+", frac: 0.12 },
          { label: "eWAR", frac: 0.12 },
          { label: "PA", frac: 0.08, wideOnly: true },
          { label: "OPS", frac: 0.10, wideOnly: true },
        ];
      return spec("MLB Stats · HEM+ Leaders",
        seasonBits(WIN["hitters"] || "current", hitterData, "hitters"),
        "mlbstats-hem-leaders",
        (hitPast
          ? "HEM+ = sample-shrunk wOBA on the wRC+ scale · Shrunk wOBA = the number it is scaled from"
          : "HEM+ = sample-shrunk wOBA on the wRC+ scale · wRC+ = FanGraphs, published")
        + winCardNote("hitters"),
        { defaultCount: 25, counts: [10, 25, 50], legend: "HEM+ 100 = average hitter",
          columns: hitCols, rows: hitRows });
    }

    if (view === "leverage") {
      var isStart = (leverageView === "starters");
      var levRows = rows.map(function (r, i) {
        var cells = [
          { t: i + 1 },
          { t: r.name || EM_DASH, sub: r.team || undefined },
          { t: fSigned(r.wpa), c: "accent" },
        ];
        if (isStart) {
          cells.push({ t: r.wpa_per_start == null ? EM_DASH
            : (r.wpa_per_start > 0 ? "+" : "") + Number(r.wpa_per_start).toFixed(2) });
          cells.push({ t: fSigned(r.wpa_li) });
        } else {
          cells.push({ t: fSigned(r.wpa_li) });
          cells.push({ t: fSigned(r.clutch) });
        }
        return { cells: cells };
      });
      var levCols2 = isStart
        ? [ { label: "#", frac: 0.06 }, { label: "Player", frac: 0.44 },
            { label: "WPA", frac: 0.17 }, { label: "WPA/start", frac: 0.17 },
            { label: "WPA/LI", frac: 0.16, wideOnly: true } ]
        : [ { label: "#", frac: 0.06 }, { label: "Player", frac: 0.44 },
            { label: "WPA", frac: 0.17 }, { label: "WPA/LI", frac: 0.16 },
            { label: "Clutch", frac: 0.17, wideOnly: true } ];
      return spec("MLB Stats · WPA Leaders" + (isStart ? " (Starters)" : " (Batters)"),
        seasonBits(WIN["leverage"] || "current", leverageData, isStart ? "starters" : "batters"),
        "mlbstats-wpa-leaders",
        "WPA = realized in-game win-probability impact · Clutch reads timing, not skill"
        + winCardNote("leverage"),
        { defaultCount: 25, counts: [10, 25, 50],
          legend: "WPA = win probability added · + adds wins, − costs them",
          columns: levCols2, rows: levRows });
    }

    if (view === "defense") {
      var defRows = rows.map(function (r, i) {
        return { cells: [
          { t: i + 1 },
          { t: r.name || EM_DASH, sub: r.team || undefined },
          { t: r.pos || EM_DASH },
          { t: fInt(r.dem_plus), c: "accent" },
          { t: fInt(r.dem_plus_3yr) },
          { t: fSigned(r.fld_total) },
          { t: f1(r.inn) },
        ] };
      });
      return spec("MLB Stats · DEM+ Leaders",
        seasonBits(WIN["defense"] || "current", defenseData, "fielders"),
        "mlbstats-dem-leaders",
        "DEM+ = sample-shrunk fielding runs per inning · Fld = FanGraphs, published"
        + winCardNote("defense"),
        { defaultCount: 25, counts: [10, 25, 50], legend: "DEM+ 100 = average fielder · 10 points = 1 SD", columns: [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.35 },
          { label: "Pos", frac: 0.08 },
          { label: "DEM+", frac: 0.12 },
          { label: "DEM+ 3yr", frac: 0.12, wideOnly: true },
          { label: "Fld", frac: 0.14 },
          { label: "Inn", frac: 0.14, wideOnly: true },
        ], rows: defRows });
    }

    if (view === "teamdefense") {
      var tdRows = rows.map(function (t, i) {
        return { cells: [
          { t: i + 1 },
          { t: t.team || EM_DASH },
          { t: fInt(t.team_dem_plus), c: "accent" },
          { t: fSigned(t.team_fld_total) },
          { t: fInt(t.team_inn) },
        ] };
      });
      return spec("MLB Stats · Team DEM+ Leaders",
        seasonBits("current", defenseData, "clubs"),
        "mlbstats-team-dem-rankings",
        "Team DEM+ = innings-weighted DEM+ · Fld = FanGraphs, published",
        { defaultCount: 30, counts: [10, 30], legend: "Team DEM+ 100 = average · 10 points = 1 SD", columns: [
          { label: "#", frac: 0.08 },
          { label: "Team", frac: 0.34 },
          { label: "Team DEM+", frac: 0.20 },
          { label: "Fld", frac: 0.19 },
          { label: "Inn", frac: 0.19, wideOnly: true },
        ], rows: tdRows });
    }

    // The sixth board's card: the only shareable graphic on this page that
    // reads a whole season rather than one side of it, so it leads with the
    // total and keeps both sides under it. Role is the column that says why a
    // name a reader cannot place is on the list (a swingman on neither pitcher
    // board, a two-way player on both).
    if (view === "ewar") {
      var ewarRows = rows.map(function (r, i) {
        return { cells: [
          { t: i + 1 },
          { t: r.name || EM_DASH, sub: r.team || undefined },
          { t: f1(r.war), c: "accent" },
          { t: f1(r.war_bat) },
          { t: f1(r.war_pit) },
          { t: r.role ? (WAR_ROLE_LBL[r.role] || r.role) : EM_DASH },
        ] };
      });
      return spec("MLB Stats · eWAR Leaders",
        seasonBits(WIN.war || "current", warData, "players"),
        "mlbstats-ewar-leaders",
        "eWAR = batting plus pitching, summed before rounding" + winCardNote("war"),
        { defaultCount: 25, counts: [10, 25, 50],
          legend: "Hitters, starters, relievers and swingmen on one list", columns: [
          { label: "#", frac: 0.06 },
          { label: "Player", frac: 0.32 },
          { label: "eWAR", frac: 0.13 },
          { label: "Bat", frac: 0.13 },
          { label: "Pitch", frac: 0.13 },
          { label: "Role", frac: 0.20 },
        ], rows: ewarRows });
    }

    return null;
  }


  // ===========================================================================
  // Section 6: eWAR Leaderboards. Every player with a season eWAR block,
  // hitters and pitchers on ONE list: the exporter sums the two sides
  // UNROUNDED (war = round(war_bat + war_pit, 1)), so a two-way player reads
  // his whole season rather than his bigger half, and a swingman on neither
  // pitcher board still appears. The five existing boards cannot show that
  // list: Ohtani reads his batting side on Hitters and his pitching side on
  // Starters, and 118 swingmen worth 15.85 eWAR are on no board at all.
  //
  // Fetches data/war_leaderboards.json ONLY, and treats any payload without a
  // players array as "not exported yet" rather than an error: the exporter
  // (war_board_export.py) refuses to write under its coverage floor, and the
  // smoke harness answers every URL with the bullpen sample.
  //
  // Team eWAR carries BOTH club bases, named (owner decision O8): `war` is the
  // roster today, the basis every other team board on this page uses, and
  // `war_earned` is what was produced for the club by stint. They differ by 3.2
  // per club on average and by 8.0 at most, so showing one silently would be a
  // claim about the other.
  // ---------------------------------------------------------------------------
  var WAR_URL = "/data/war_leaderboards.json";
  var warData = null, warErr = false, warInit = false;
  var warLoading = false;                          // the board payload is in flight
  var warView = "players";                         // players | teams
  var warSort = { key: "war", asc: false };
  var warTeamSort = { key: "war", asc: false };
  var warQuery = "", warTeam = "", warRoles = [], warQualifiedOnly = true;
  var WAR_ROLE_LBL = { H: "Hitter", SP: "Starter", RP: "Reliever", SW: "Swingman", TWP: "Two-way" };
  // Counting eWAR, uncoloured on purpose: see the family table beside vtCell.
  // No ladder here was measured on a played-season pool.
  // The five role boards a player is also on, as chips that switch section.
  // An in-page <a href="#section=..."> would change the hash and nothing else:
  // readHash runs once, at init.
  var WAR_BOARD_LBL = { hitters: "Hitters", starters: "Starters", bullpen: "Bullpen",
                        leverage: "Leverage", defense: "Defense" };
  function boardsCell(r) {
    var b = r.boards;
    if (!b) return EM_DASH;
    if (!b.length) {
      return '<span class="proj-dim" title="On none of the five role boards: a swingman, a two-way'
        + ' player split across two of them, or a sample under their floors. That is the claim this'
        + ' board exists to make.">none</span>';
    }
    return b.filter(function (k) { return WAR_BOARD_LBL[k]; }).map(function (k) {
      return '<button type="button" class="chip mlbx-goto" data-mlbgoto="' + esc(k) + '">'
        + esc(WAR_BOARD_LBL[k]) + "</button>";
    }).join(" ");
  }
  var WAR_COLS = [
    { key: "name", label: "Player", kind: "name", asc: true },
    { key: "pos", label: "Pos", title: "Primary position; P for pitchers.",
      cell: function (r) { return esc(r.pos || EM_DASH); } },
    { key: "age", label: "Age", fmt: fInt, num: true, asc: true,
      title: "Age in the season shown; on a window, in the last season with a line." },
    { key: "war", label: "eWAR", term: "ewar", num: true, ewar: true,
      title: "Batting plus pitching eWAR this season, summed before rounding.",
      cell: function (r) { return r.war == null ? EM_DASH : "<b>" + f1(r.war) + "</b>"; } },
    { key: "war_bat", label: "Bat", fmt: f1, num: true,
      title: "Position-player side: batting, baserunning, fielding, position." },
    { key: "war_pit", label: "Pitch", fmt: f1, num: true, title: "Pitching side." },
    // EACH SIDE OVER ITS OWN DENOMINATOR. One eWAR/600 on the total would charge
    // a two-way player's pitching to his plate appearances; _side_war_by_season
    // keeps the two sides apart for the same reason. A division, not an index:
    // there is no pool behind it, so there is no colour on it and no ladder.
    { key: "bat_600", label: "Bat/600", term: "bat_600", num: true,
      title: "Batting eWAR per 600 plate appearances, a full season for a regular. A division, not an"
        + " index: no pool behind it, so no colour on it.",
      cell: function (r) { return r.bat_600 == null ? EM_DASH : f1(r.bat_600); } },
    { key: "pitch_200", label: "Pitch/200", term: "pitch_200", num: true,
      title: "Pitching eWAR per 200 innings. A reliever's 70 innings and a starter's 200 sit on the"
        + " same ruler, which is why IP is beside it.",
      cell: function (r) { return r.pitch_200 == null ? EM_DASH : f1(r.pitch_200); } },
    { key: "pa", label: "PA", fmt: fInt, num: true },
    { key: "ip", label: "IP", fmt: f1, num: true },
    { key: "g", label: "G", fmt: fInt, num: true,
      title: "Games played, the larger of the two feeds per season and then summed: a two-way player's"
        + " hitting games and pitching games are the same games." },
    { key: "gs", label: "GS", fmt: fInt, num: true, title: "Official games started." },
    { key: "yrs", label: "Yrs", fmt: fInt, num: true,
      title: "Seasons with a line inside the window." },
    { key: "clubs", label: "Clubs", num: true,
      title: "Clubs of production inside the window; the cell names the first two.",
      get: function (r) { return (r.clubs && r.clubs.length) || null; },
      cell: function (r) {
        var c = r.clubs || [];
        if (!c.length) return EM_DASH;
        return c.length + '<span class="proj-dim" title="' + esc(c.join(", ")) + '"> '
          + esc(c.slice(0, 2).join(" ")) + (c.length > 2 ? "+" : "") + "</span>";
      } },
    { key: "boards", label: "Also on", cell: boardsCell,
      title: "The five role boards this player is on today, built from those five artifacts. A window"
        + " has no per-season answer on disk, so the column drops on one." },
  ];
  // Which of those the board is serving right now. `yrs` and `clubs` are window
  // facts; `boards` is a fact about today; `age` and `g` reach the CURRENT board
  // only through the per-season substrate, because the served payload's `g` is
  // the pitching feed's alone (800 of 1,457 rows) and it carries no age at all.
  // A column with no data is dropped rather than served empty, which is the rule
  // coveredCols already applies to a history board.
  var WAR_POOLED = { bat_600: "batting eWAR / PA x 600",
                     pitch_200: "pitching eWAR / IP x 200" };
  var WAR_LAST_SEASON = { pos: 1, age: 1 };
  function warCols() {
    var win = !!WIN.war, span = isWindow("war"), enriched = !!(SEASONS && SEASONS.players);
    var lbl = win ? winSpan(WIN.war) : "";
    return WAR_COLS.filter(function (c) {
      if (c.key === "boards") return !win;
      if (c.key === "yrs" || c.key === "clubs") return span;
      if (c.key === "g" || c.key === "age") return win || enriched;
      return true;
    }).map(function (c) {
      if (!win || c.kind === "name") return c;
      var out = cloneCol(c);
      out.exportLabel = c.label + " " + lbl;
      out.title = WAR_LAST_SEASON[c.key]
        ? ("The last season with a line inside " + lbl + ".")
        : WAR_POOLED[c.key]
          ? ("Pooled once over " + lbl + ": " + WAR_POOLED[c.key] + ". A division, not an index: no"
             + " pool behind it, so no colour on it.")
          : (c.key === "yrs" || c.key === "clubs") ? c.title
          : ("Summed over " + lbl + (c.key === "war" ? ", the two sides added unrounded and rounded"
             + " once, exactly as one season is." : "."));
      return out;
    });
  }
  var WAR_TEAM_COLS = [
    { key: "team", label: "Team", kind: "team", asc: true },
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true, ewar: true,
      title: "eWAR of the players on the club today, the basis of every team board here." },
    { key: "war_earned", label: "Earned", fmt: f1, num: true,
      title: "eWAR produced for this club this season, by stint. Blank when a club cannot be mapped." },
    { key: "war_bat", label: "Hitters", fmt: f1, num: true },
    { key: "war_sp", label: "Starters", fmt: f1, num: true },
    { key: "war_rp", label: "Relievers", fmt: f1, num: true },
    { key: "war_sw", label: "Swing", fmt: f1, num: true, title: "Pitchers on neither pitcher board." },
    { key: "n_players", label: "Players", fmt: fInt, num: true },
  ];
  // The served board, plus the three columns it cannot carry by itself. Age and
  // G come from data/war_seasons.json folded at the LIVE season - the same file
  // war_board_export writes in the same process from the same read, so the join
  // cannot disagree with the row it lands on - and the two rates are a division
  // of the row's own served numbers, so they agree with the Bat and Pitch cells
  // beside them to the tenth those cells print. Cached on identity, because this
  // runs again on every keystroke in the search box.
  var WAR_ROWS_CACHE = { src: null, fold: null, out: [] };
  function warRows() {
    var d = warData, rows = (d && d.players && d.players.length) ? d.players : [];
    if (!rows.length) return rows;
    var live = num(d.season);
    var fold = (SEASONS && SEASONS.players && live != null) ? foldSeasons(live, live) : null;
    if (WAR_ROWS_CACHE.src === rows && WAR_ROWS_CACHE.fold === fold) return WAR_ROWS_CACHE.out;
    var by = {};
    if (fold) fold.players.forEach(function (p) { by[p.mlbam] = p; });
    var out = rows.map(function (r) {
      var o = cloneCol(r), f = by[r.mlbam];
      o.bat_600 = (r.war_bat != null && r.pa) ? (r.war_bat / r.pa) * 600 : null;
      o.pitch_200 = (r.war_pit != null && r.ip) ? (r.war_pit / r.ip) * 200 : null;
      if (f) {
        o.age = f.age;
        o.g = f.g;
        o.seasons = f.seasons;
      }
      return o;
    });
    WAR_ROWS_CACHE = { src: rows, fold: fold, out: out };
    return out;
  }
  function warMatch(r) {
    if (warQualifiedOnly && r.qualified === false) return false;
    if (warTeam && r.team !== warTeam) return false;
    if (warRoles.length && warRoles.indexOf(r.role) < 0) return false;
    var q = warQuery.trim().toLowerCase();
    return !q || String(r.name || "").toLowerCase().indexOf(q) >= 0 || String(r.team || "").toLowerCase().indexOf(q) >= 0;
  }
  // The qualifying rule is the EXPORTER's (war_board_export writes
  // qualified_rule from the same WAR_RATE_DISPLAY_MIN_PA / _MIN_RP_IP the rate
  // columns are gated on), so the page reports it instead of typing it and a
  // payload that ships a different floor says so by itself.
  function warQualTitle() {
    var win = !!WIN.war;
    var q = (win ? (SEASONS && SEASONS.qualified_rule_window) : null)
         || (warData && warData.qualified_rule) || null;
    if (!q || (q.min_pa == null && q.min_ip == null)) return "";
    var bits = [];
    if (q.min_pa != null) bits.push(q.min_pa + " plate appearances");
    if (q.min_ip != null) bits.push(q.min_ip + " innings");
    return ' title="' + esc("Qualified: " + bits.join(" or ")
      + (win ? " over the whole window, the rule published beside the substrate. On a long window it"
             + " removes very little, because a small sample makes a small total anyway."
             : ", the rule this board is served with.")) + '"';
  }
  function warRoleChips() {
    var counts = {};
    warRows().forEach(function (r) { if (r.role) counts[r.role] = (counts[r.role] || 0) + 1; });
    var all = !warRoles.length;
    return '<div class="mlbstats-seasons mlbstats-roles" role="group" aria-label="Filter by role">'
      + '<span class="mlbstats-roles-lbl">Role</span>'
      + '<button type="button" class="mlbstats-season' + (all ? " active" : "") + '" id="mlbstats-warrole-all"'
      + ' data-warrole="" aria-pressed="' + all + '">All</button>'
      + ["H", "SP", "RP", "SW", "TWP"].filter(function (k) { return counts[k]; }).map(function (k) {
          var on = warRoles.indexOf(k) >= 0;
          return '<button type="button" class="mlbstats-season' + (on ? " active" : "") + '" id="mlbstats-warrole-'
            + k.toLowerCase() + '" data-warrole="' + k + '" aria-pressed="' + on + '">' + WAR_ROLE_LBL[k]
            + '<span class="proj-dim"> ' + counts[k] + "</span></button>";
        }).join("") + "</div>";
  }
  function warExplainer() {
    return explainer("ewar", gloss("eWAR", "ewar") + ": batting plus pitching, summed before rounding.");
  }
  function renderWarInner() {
    winCheck("war");
    var win = !!WIN.war;
    if (warView === "teams") {
      // A club total over a window is the one thing this substrate cannot say:
      // a season's line carries every club the player produced for and not the
      // split between them, so summing it by club would credit a traded man's
      // whole season to both. Refused by name rather than served on the live
      // season under a window's heading.
      if (win) {
        return yearsRow("war") + warExplainer()
          + '<div class="mlbstats-empty mlbstats-winrefusal">Team eWAR is a single-season board. A'
          + " season's line names every club the player produced for but not the split between them,"
          + " so a club total over " + esc(winSpan(WIN.war)) + " would credit a traded player's whole"
          + ' season to each of his clubs. <button type="button" class="chip"'
          + ' data-mlbrange="war:current">Back to Current</button></div>';
      }
      var t = sortRows((warData && warData.teams) || [], WAR_TEAM_COLS, warTeamSort);
      if (!t.length) return warExplainer() + '<div class="mlbstats-empty">No team eWAR to show yet.</div>';
      return warExplainer()
        + '<div class="mlbstats-scroll">' + renderTable(t, WAR_TEAM_COLS, warTeamSort, warData, "warteam") + "</div>";
    }
    // The role chips go on a window (a fold row has no role), so the Filters
    // badge stops counting them there as well.
    var bar = '<div class="' + filtCls() + '">'
      + filtBtn(filtCount(warTeam, null, win ? null : warRoles, !warQualifiedOnly))
      + teamFilterChip(warTeam)
      + '<label class="mlbstats-ctl"' + warQualTitle() + '>'
      + '<input type="checkbox" id="mlbstats-war-qual"' + (warQualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-war-team", winSelectRows("war", warRows()), warTeam, "war")
      + gfxChip("mlbstats-war-gfx")
      + '<input class="mlbstats-search" type="search" id="mlbstats-war-q" placeholder="Search player or team" value="' + esc(warQuery) + '">'
      + "</div>"
      // Role is a season fact by construction, so the chips go on a window and
      // the filter goes with them rather than silently emptying the board.
      + (win ? "" : warRoleChips());
    if (win) {
      var wbody = renderWindowBoard("war");
      // Still a window: serve it. Otherwise the span was refused while this
      // render ran, and Current below is the right answer.
      if (wbody) return bar + warExplainer() + wbody;
    }
    var cols = warCols();
    var rows = sortRows(warRows().filter(warMatch), cols, warSort);
    if (!rows.length) {
      return bar + warExplainer() + yearsRow("war")
        + noRowsNote(warTeam, "No players match the current filters.");
    }
    return bar + warExplainer() + yearsRow("war")
      + '<div class="mlbstats-scroll">'
      + renderTable(rows, cols, warSort, warData, "war", warTableOpts()) + "</div>";
  }
  function renderWar(focusId) {
    var root = document.getElementById("mlbstats-war-root");
    if (!root) return;
    if (!warRows().length) {
      // In flight: the lamp loader. The computing note is for a load that
      // settled with no rows, and the failed kind for one that errored.
      root.innerHTML = warLoading
        ? pxState("loading", "Loading&hellip;")
        : warErr
        ? pxState("failed", "Data failed to load. Refresh to retry; "
          + "if it persists the nightly build is mid-run. "
          + '<button type="button" class="chip" id="mlbstats-war-retry">Retry</button>', "mlbstats-load-error")
        : pxState("unmeasured", "The eWAR board is being computed. Check back shortly.");
      var retry = document.getElementById("mlbstats-war-retry");
      if (retry) retry.addEventListener("click", function () { loadWar(); });
      return;
    }
    var tabs = [["players", "Players"], ["teams", "Team eWAR"]];
    // The club basis note is the CURRENT board's, and on a window the window
    // note states the basis instead: the served block says "the club today",
    // which is not what a window row's club is.
    root.innerHTML = bannerHTML(warData, { noCoverage: true, sec: "war" }) + teamBasisNote(sectionBasis("war", warData, null))
      + '<div class="mlbstats-tabs" role="tablist">' + tabs.map(function (t) {
          return '<button type="button" class="mlbstats-tab' + (t[0] === warView ? " active" : "") + '" data-warview="' + t[0]
            + '" role="tab" aria-selected="' + (t[0] === warView) + '">' + t[1] + "</button>"; }).join("") + "</div>"
      + renderWarInner();
    stampCsv("war", root);
    root.querySelectorAll("[data-warview]").forEach(function (b) { b.addEventListener("click", function () {
      warView = b.getAttribute("data-warview"); writeHash(); renderWar(); }); });
    root.querySelectorAll("[data-warrole]").forEach(function (b) { b.addEventListener("click", function () {
      var v = b.getAttribute("data-warrole");
      if (!v) warRoles = []; else { var i = warRoles.indexOf(v); if (i >= 0) warRoles.splice(i, 1); else warRoles.push(v); }
      renderWar(b.id || null); }); });
    var q = root.querySelector("#mlbstats-war-q");
    if (q) q.addEventListener("input", function () { warQuery = q.value; renderWar("mlbstats-war-q"); });
    var qual = root.querySelector("#mlbstats-war-qual");
    if (qual) qual.addEventListener("change", function () { warQualifiedOnly = qual.checked; renderWar("mlbstats-war-qual"); });
    var ts = root.querySelector("#mlbstats-war-team");
    if (ts) ts.addEventListener("change", function () {
      warTeam = ts.value || "";
      writeHash();
      renderWar("mlbstats-war-team");
    });
    var wgfx = root.querySelector("#mlbstats-war-gfx");
    if (wgfx) wgfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      EEPHUS_GFX.open(_mlbstatsBoardSpec("ewar", WIN.war
        ? sortRows(foldSeasons(WIN.war.lo, WIN.war.hi).players.filter(function (r) {
            return winMatch("war", r, null); }), warCols(), warSort)
        : sortRows(warRows().filter(warMatch), warCols(), warSort)));
    });
    root.querySelectorAll(".mlbstats-table th[data-col]").forEach(function (th) {
      bindSortKeys(th, root, function () {
        var key = th.getAttribute("data-col"), cols = (warView === "teams") ? WAR_TEAM_COLS : warCols();
        var col = null; cols.forEach(function (c) { if (c.key === key) col = c; });
        if (!col || (!col.num && col.kind !== "name" && col.kind !== "team")) return;
        var s = (warView === "teams") ? warTeamSort : warSort;
        if (s.key === key) s.asc = !s.asc; else { s.key = key; s.asc = !!col.asc; }
        writeHash(); renderWar();
      });
    });
    if (focusId) restoreFocus(root, focusId);
    wireGlossary(root);
  }
  // A payload that was never WRITTEN is "not exported yet", not a failure:
  // this board is new, war_board_export.py refuses to write under its coverage
  // floor, and until its first nightly run the file is a 404. So 404 reads as
  // the computing note, while a 5xx or a network error is the error state the
  // other five boards carry, with the same Retry bound to the same loader.
  // The guard is on init, not on the fetch, so Retry can run the fetch again.
  function loadWar() {
    warErr = false;
    warLoading = true;
    renderWar();
    fetch(WAR_URL, { cache: "no-cache" })
      .then(function (r) {
        if (r.status === 404) return null;
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (j) { warLoading = false; warData = (j && Array.isArray(j.players)) ? j : null; renderWar(); })
      .catch(function () { warLoading = false; warData = null; warErr = true; renderWar(); });
    // THE PER-SEASON SUBSTRATE RIDES WITH THE BOARD, second in the queue so the
    // board's own payload paints first. Measured on the served artifacts: the
    // landing section fetches war_leaderboards.json (40.8 KB gzip) plus
    // war_seasons.json (279.5 KB) and mlbstats_windows.json (5.2 KB) where it
    // used to fetch bullpen_leaderboards.json (62.5 KB), so the landing costs
    // 263 KB more than it did. What that buys, and why it is not lazy: the
    // from/to control is complete on the first click rather than growing a
    // second later under the reader's hand, and Age, G and the per-season
    // expander exist on the CURRENT board at all - the served payload carries
    // no age and its `g` is the pitching feed's alone. Deferring it to the
    // first non-Current pick is a one-line change (move this call into
    // setWindow) that costs those three.
    loadSeasons("war");
  }
  function initWar() {
    if (warInit) { renderWar(); return; }
    warInit = true;
    loadWar();
  }

  // ---- top-level section switching ------------------------------------------
  function showSection(name) {
    section = name;
    document.querySelectorAll("[data-mlbsection]").forEach(function (b) {
      var on = b.getAttribute("data-mlbsection") === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    var sects = { war: "mlbstats-section-war", bullpen: "mlbstats-section-bullpen",
                  starters: "mlbstats-section-starters",
                  hitters: "mlbstats-section-hitters", leverage: "mlbstats-section-leverage",
                  defense: "mlbstats-section-defense" };
    Object.keys(sects).forEach(function (k) {
      var el = document.getElementById(sects[k]);
      if (el) { if (k === name) el.removeAttribute("hidden"); else el.setAttribute("hidden", "hidden"); }
    });
    markFit(document.getElementById(sects[name]));
    if (name === "starters") initStarters();
    else if (name === "hitters") initHitters();
    else if (name === "leverage") initLeverage();
    else if (name === "defense") initDefense();
    else if (name === "war") initWar();
    else if (name === "bullpen") initBullpen();
  }
  // The bullpen board is lazy like the other five now, because it is no longer
  // the one a bare URL opens: measured on the served payloads, the landing
  // section fetches war_leaderboards.json (389 KB) instead of
  // bullpen_leaderboards.json (452 KB).
  var relInit = false;
  function initBullpen() {
    if (relInit) { render(); return; }
    relInit = true;
    render();
    load();
  }
  // A chip that switches section, optionally with a window: the Also on column
  // and the refusal note both use it, because an in-page hash link would change
  // the URL and nothing else.
  try { document.addEventListener("click", function (e) {
    var b = e.target && e.target.closest ? e.target.closest("[data-mlbgoto]") : null;
    if (!b) return;
    var p = String(b.getAttribute("data-mlbgoto") || "").split(":");
    if (!LAB_BOARD[p[0]]) return;
    if (p[1]) {
      var yy = String(p[1]).split("-");
      WIN[p[0]] = { lo: Number(yy[0]), hi: Number(yy[1]) };
      syncSeasonVars();
    }
    showSection(p[0]);
    writeHash();
  }); } catch (e) { /* no document events */ }
  function bindSectionNav() {
    document.querySelectorAll("[data-mlbsection]").forEach(function (b) {
      b.addEventListener("click", function () {
        showSection(b.getAttribute("data-mlbsection"));
        writeHash();
      });
    });
  }

  function init() {
    readHash();
    syncSeasonVars();
    // A remembered non-Standard view (localStorage) reopens on that view: say
    // so in the URL at once, so a link copied before any click carries it. A
    // bare URL with nothing remembered stays bare.
    if (Object.keys(COL_VIEW).some(function (b) { return COL_VIEW[b] !== "standard"; })) writeHash();
    bindSectionNav();
    // Every section is lazy, including the one the page opens on, so the shell's
    // active tab and this call are the only two places the landing board is
    // named.
    showSection(section);
    // The player-links map loads after the first board paints (linksSoon), or
    // after four seconds if no board ever does.
    try { setTimeout(loadLinks, 4000); } catch (e) { /* no timers */ }
  }
  // The map is 1.88 MB. Fetched at boot, it raced the board's own payload for
  // the wire, and its arrival re-rendered the whole active board (QMLP05). It
  // now waits for the first painted board and an idle moment, and its arrival
  // turns the plain names into links in place. A board that prints names out
  // of the map itself (a window's unnamed rows) still re-renders.
  var linksAsked = false, linksQueued = false;
  function linksSoon() {
    if (linksAsked || linksQueued) return;
    linksQueued = true;
    var idle = (typeof window !== "undefined") && window.requestIdleCallback;
    if (idle) idle.call(window, loadLinks, { timeout: 1500 });
    else {
      try { setTimeout(loadLinks, 0); }
      catch (e) { try { Promise.resolve().then(loadLinks); } catch (e2) { loadLinks(); } }
    }
  }
  function loadLinks() {
    if (linksAsked) return;
    linksAsked = true;
    if (!(window.EEPHUS_HUB && EEPHUS_HUB.links)) return;
    EEPHUS_HUB.links().then(function (L) {
      LINKS = L || null;
      upgradeLinks(document.querySelector(".mlbx"));
      var host = document.getElementById("mlbstats-section-" + section);
      if (!WIN[section] && !(host && host.querySelector(".mlbx-noname"))) return;
      if (section === "starters") { if (starterInit) renderStarters(); }
      else if (section === "hitters") { if (typeof hitterInit !== "undefined" && hitterInit) renderHitters(); }
      else if (section === "leverage") { if (typeof leverageInit !== "undefined" && leverageInit) renderLeverage(); }
      else if (section === "defense") { if (defenseInit) renderDefense(); }
      else if (section === "war") { if (warInit) renderWar(); }
      else if (relInit) render();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
