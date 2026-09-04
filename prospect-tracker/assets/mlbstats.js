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
(function () {
  "use strict";

  var DATA_URL = "/data/bullpen_leaderboards.json";
  var ROLE_ORDER = ["Closer", "High-leverage", "Setup", "Middle", "Long", "Mop-up"];

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
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
    switch (type) {
      case "int":      return String(Math.round(z));
      case "war":      return z.toFixed(1);
      case "rate":     return sign + abs.toFixed(2);
      case "surplusM": return sign + "$" + abs.toFixed(1) + "M";
      // MINUS but never PLUS. Dropping the sign entirely was harmless for the
      // guarantees and AAVs this surface passes it (all positive) but rendered
      // a NEGATIVE dollar figure as a positive one, and /projections/ prices
      // surplus through this same type, where negatives are now common
      // (rest-of-season control pricing, 2026-08-03). A liability shown as an
      // asset is the worst possible rounding of that number. The leading "+"
      // that `sign` would add belongs to surplusM, where the direction is the
      // point; on a contract guarantee it is noise.
      case "moneyM":   return (z < 0 ? "-" : "") + "$"
                            + (abs >= 100 ? abs.toFixed(0) : abs.toFixed(1)) + "M";
      case "pct":      return z.toFixed(1) + "%";
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
  function logo(team) {
    try { return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo) ? EEPHUS_HUB.teamLogo(team) : ""; }
    catch (e) { return ""; }
  }
  function chart(fn, arg, opts) {
    try { return (window.EEPHUS_HUB && EEPHUS_HUB[fn]) ? EEPHUS_HUB[fn](arg, opts) : ""; }
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
    var body = '<div class="mlbstats-viz">'
      + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">' + gloss("REM+", "rem_plus")
      + ' distribution <span class="proj-dim">(qualified relievers; cyan = elite)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Skill vs leverage'
        + ' <span class="proj-dim">(top-right = elite arms in high leverage)</span></div>' + sc + "</div>" : "")
      + (xsc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Earned vs deserved: REM+ × ' + gloss("xREM+", "xrem_plus")
        + ' <span class="proj-dim">(below the diagonal = results ahead of contact quality)</span></div>' + xsc + "</div>" : "")
      + "</div>";
    return collapsible("relievers-viz", 'Charts <span class="proj-dim">(REM+ distribution, skill vs leverage, earned vs deserved)</span>', body);
  }

  // REM+/Bullpen+ index coloring (100 = average).
  function remClass(v) {
    var n = num(v);
    if (n == null) return "rem-avg";
    if (n >= 120) return "rem-elite";
    if (n >= 107) return "rem-good";
    if (n >= 93) return "rem-avg";
    return "rem-low";
  }
  function remCell(v, glossaryTerm) {
    var g = glossaryTerm ? ' data-gl="' + glossaryTerm + '"' : "";
    return '<span class="rem-plus ' + remClass(v) + '"' + g + '>' + fInt(v) + "</span>";
  }
  // HEM+ / xHEM+ / Offense+ ride a WIDER (wRC+-width) scale than the FIP-based
  // REM+/SEM+, so they get their own color bands (widening the shared remClass
  // would recolor the reliever/starter metrics). Same rem-* CSS classes, wider
  // thresholds (mean 100, SD ~16).
  function hemClass(v) {
    var n = num(v);
    if (n == null) return "rem-avg";
    if (n >= 130) return "rem-elite";
    if (n >= 112) return "rem-good";
    if (n >= 88) return "rem-avg";
    return "rem-low";
  }
  function hemCell(v, glossaryTerm) {
    var g = glossaryTerm ? ' data-gl="' + glossaryTerm + '"' : "";
    return '<span class="rem-plus ' + hemClass(v) + '"' + g + '>' + fInt(v) + "</span>";
  }
  // PUBLISHED wRC+ gets a THIRD band set, and that is deliberate. It is the
  // industry's number, not one of ours, and it is unshrunk, so it runs wider
  // than the HEM+ family beside it: measured over the pooled 2021-2026
  // qualified pools (n = 2,069), published wRC+ has SD 25.3 against HEM+ 17.7.
  // Painting it with hemClass 88/112/130 would call 12.4% of qualified hitters
  // elite where HEM+ calls 4.9%. The breaks below are the round-5 triple that
  // best reproduces the HEM+ band shares on the wRC+ distribution (85/120/145:
  // shares 26.0 / 52.1 / 17.9 / 4.1 vs the HEM+ reference 26.5 / 50.9 / 17.6 /
  // 4.9). SINGLE SOURCE OF TRUTH: hitter_export.WRC_PLUS_BANDS. These three
  // numbers mirror it and test_hitter_wrc_plus.py fails if they drift apart.
  function wrcClass(v) {
    var n = num(v);
    if (n == null) return "rem-avg";
    if (n >= 145) return "rem-elite";
    if (n >= 120) return "rem-good";
    if (n >= 85) return "rem-avg";
    return "rem-low";
  }
  function wrcCell(v) {
    return '<span class="rem-plus ' + wrcClass(v) + '" data-gl="wrc_plus">' + fInt(v) + "</span>";
  }
  function gloss(label, term) {
    return '<span class="g-term" data-gl="' + esc(term) + '">' + esc(label) + "</span>";
  }
  function wireGlossary(el) {
    try { if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(el); } catch (e) { /* glossary optional */ }
  }

  // ---- shared filter controls -----------------------------------------------
  // Every board on this surface shipped with exactly two filters: a search box
  // and a "qualified only" checkbox. The rows already carry team, role, innings
  // and plate appearances, so these narrow client-side off what is on screen
  // and never refetch. Markup rides the existing .mlbstats-bar input/select
  // rule and the .mlbstats-season pill, so there is no second control language.
  //
  // The option list is built from the ROWS, not a static club map, so it can
  // never offer a team the active board (or the active season) has nobody on.
  function teamSelect(id, rows, sel) {
    var seen = {}, out = [];
    (rows || []).forEach(function (r) { if (r.team && !seen[r.team]) { seen[r.team] = 1; out.push(r.team); } });
    out.sort();
    var opts = '<option value="">All teams</option>' + out.map(function (t) {
      return '<option value="' + esc(t) + '"' + (t === sel ? " selected" : "") + ">" + esc(t) + "</option>";
    }).join("");
    return '<label class="mlbstats-ctl">team <select id="' + id + '" aria-label="Filter by team">'
      + opts + "</select></label>";
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
  // Omitted means collapsed, which is what every chart panel wants; the
  // methodology folds below pass a viewport-dependent default instead. A
  // user's own choice is written to localStorage by setCollapse and outranks
  // whatever default the caller asked for, on every board and every visit.
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
  // None of it is deleted. It rides one collapsible per board, and the default
  // is viewport-aware rather than fixed: OPEN on a desktop, where it costs a
  // reader nothing and the methodology should be in his face, CLOSED on a
  // phone, where it costs him the board. The fold head keeps the row count
  // visible in both states, so the one number that is data rather than
  // methodology never hides.
  function isNarrowViewport() {
    // No matchMedia in the py_mini_racer smoke harness (and none in very old
    // browsers): fall back to "not a phone", i.e. the fold opens, which is the
    // state that shows the most.
    try {
      return !!(window.matchMedia && window.matchMedia("(max-width: 640px)").matches);
    } catch (e) { return false; }
  }
  // `lead` is HTML, like collapsible()'s title: escape anything dynamic at the
  // call site (every caller today passes a number or an already-esc()'d value).
  function proseFold(id, lead, body) {
    if (!body) return "";
    return collapsible(id,
      '<span class="mlbstats-fold-lead">' + lead + "</span>"
      + '<span class="mlbstats-fold-hint">how to read this board</span>',
      body, { collapsed: isNarrowViewport(), cls: "mlbstats-fold" });
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
  var REL_COLS = [
    { key: "name", label: "Reliever", term: null, sortable: true, kind: "name", asc: true },
    { key: "rem_plus", label: "REM+", term: "rem_plus", fmt: remCell, num: true, desc: true, isRem: true },
    { key: "rem_plus_3yr", label: "REM+ 3yr", term: "rem_plus_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear",
      get: function (r) { return r.rem_plus_3yr; },
      cell: function (r) {
        if (r.rem_plus_3yr == null) return "";
        var s = remCell(r.rem_plus_3yr);
        if (r.rem_plus_3yr_pct != null) s += '<span class="proj-dim"> p' + fInt(r.rem_plus_3yr_pct) + "</span>";
        if (r.rem_plus_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 40 IP in the trailing window">*</span>';
        return s;
      } },
    { key: "xrem_plus", label: "xREM+", term: "xrem_plus", num: true, desc: true, isRem: true,
      title: "Deserved run prevention: the REM+ scale on Savant expected wOBA allowed (lower allowed = higher). A companion to REM+, which stays FIP-based (xwOBA-allowed did not beat FIP predictively); this is a deserved read, not a replacement. Tracked relievers only.",
      get: function (r) { return r.xrem_plus; },
      cell: function (r) { return r.xrem_plus == null ? "" : remCell(r.xrem_plus); } },
    { key: "luck", label: "Luck", num: true, desc: true,
      title: "Actual minus expected wOBA allowed. Positive = allowed more than his contact deserved (unlucky, room to improve); negative = allowed less (over-performing, due to regress).",
      get: function (r) { return r.luck; },
      cell: function (r) {
        if (r.luck == null) return "";
        var v = r.luck;
        var col = v >= 0.02 ? "var(--up)" : v <= -0.02 ? "var(--down)" : "var(--text-tertiary)";
        return '<span style="color:' + col + ';font-variant-numeric:tabular-nums;">' + (v > 0 ? "+" : "") + v.toFixed(3) + "</span>";
      } },
    // Reliever-anchored WAR/IP+. Separate metric from the starter board's
    // WAR/IP+ (same field name, different payload, different anchor pool): a
    // reliever banks more WAR per inning than a starter of equal talent, so the
    // two are never pooled. remCell, not hemCell: 100 + 10z has SD exactly 10.
    { key: "war_ip_plus", label: "WAR/IP+", term: "war_ip_plus_rp", num: true, desc: true, isRem: true,
      title: "Pitching eWAR (FIP re-priced within role) per inning, indexed over RELIEVERS with 20+ IP: 100 is the average reliever and every 10 points is one standard deviation of that pool. Anchored on relievers only, so it is not comparable with the starter board's WAR/IP+. Needs 30 IP to show. The p-number is this value's percentile on the board, because on a 10-points-per-sigma scale a modest-looking number can still be rare.",
      get: function (r) { return r.war_ip_plus; },
      cell: function (r) {
        if (r.war_ip_plus == null) return "";
        var s = remCell(r.war_ip_plus);
        if (r.war_ip_plus_pct != null) s += '<span class="proj-dim"> p' + fInt(r.war_ip_plus_pct) + "</span>";
        return s;
      } },
    { key: "war_ip_plus_adj", label: "WAR/IP+ adj", term: "war_ip_plus_rp_adj", num: true, desc: true, isRem: true,
      title: "WAR/IP+ regressed for sample size: the rate is pulled toward the pool rate by innings before indexing, so a short hot stretch does not outrank a full season. Re-standardised on the regressed pool, so 10 points is still one standard deviation. A readability aid for thin samples, not a forecast: neither WAR rate predicts next season better than plain season WAR does.",
      get: function (r) { return r.war_ip_plus_adj; },
      cell: function (r) { return r.war_ip_plus_adj == null ? "" : remCell(r.war_ip_plus_adj); } },
    { key: "war_ip_plus_3yr", label: "WAR/IP+ 3yr", term: "war_ip_plus_rp_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear_war_rate",
      get: function (r) { return r.war_ip_plus_3yr; },
      cell: function (r) {
        if (r.war_ip_plus_3yr == null) return "";
        var s = remCell(r.war_ip_plus_3yr);
        if (r.war_ip_plus_3yr_pct != null) s += '<span class="proj-dim"> p' + fInt(r.war_ip_plus_3yr_pct) + "</span>";
        if (r.war_ip_plus_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 40 IP in the trailing window">*</span>';
        return s;
      } },
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true,
      title: "Pitching eWAR this season, the numerator of WAR/IP+ (shown so the rate is checkable against the IP column). eWAR (eephus WAR): Baseball-Reference run frame with pitching re-priced on FIP; fielding unchanged pending SDR; position players match bWAR except in seasons they also pitched." },
    { key: "ip", label: "IP", fmt: f1, num: true },
    { key: "g", label: "G", fmt: fInt, num: true },
    { key: "k_pct", label: "K%", fmt: fPct, num: true },
    { key: "bb_pct", label: "BB%", fmt: fPct, num: true, asc: true },
    { key: "k_bb_pct", label: "K-BB%", fmt: fPct, num: true },
    { key: "fip", label: "FIP", fmt: f2, num: true, asc: true },
    { key: "swstr_pct", label: "SwStr%", fmt: fPct, num: true },
    { key: "era", label: "ERA", fmt: f2, num: true, asc: true },
    { key: "gmli", label: "gmLI", term: "gmli", fmt: f2, num: true },
    // Frozen the same way as REM+ 3yr (leverage_consistency_eval.json), but its
    // join stamps no vintage block on the payload, so there is no date to show
    // and none is invented. Stamping one is an exporter change, not a frontend
    // one: see _join_leverage_consistency in bullpen_export.py, which returns a
    // row count where its sibling _join_rem_plus_3yr returns a vintage dict.
    { key: "gmli_3yr", label: "gmLI 3yr", term: "gmli_3yr", fmt: f2, num: true,
      title: "Trailing 3-year game-entry Leverage Index, read verbatim from the frozen leverage-consistency artifact rather than recomputed with this board. Deployment context only, never an input to REM+. This artifact ships no vintage stamp, so unlike the other 3-year columns it cannot state its own date.",
      cell: function (r) {
        if (r.gmli_3yr == null) return "";
        var s = f2(r.gmli_3yr);
        if (r.gmli_3yr_pct != null) s += '<span class="proj-dim"> p' + fInt(r.gmli_3yr_pct) + "</span>";
        if (r.gmli_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 60 relief entries in the trailing window">*</span>';
        return s;
      } },
    { key: "riv_plus", label: "RIV+", term: "riv_plus", fmt: remCell, num: true, desc: true },
    { key: "wpa", label: "WPA", term: "wpa", fmt: fSigned, num: true },
    { key: "wpa_li", label: "WPA/LI", term: "wpa_li", fmt: fSigned, num: true },
    { key: "sd_md", label: "SD-MD", term: "shutdowns_meltdowns", fmt: fInt, num: true,
      get: function (r) { var sd = num(r.sd), md = num(r.md); return (sd == null && md == null) ? null : (sd || 0) - (md || 0); } },
  ];

  // Past-season history rows (bullpen_history.json) carry only the season-level
  // fields, not the trailing-window ones. Reuse the same column objects so the
  // history board renders and sorts identically, dropping the columns whose data
  // (rem_plus_3yr, gmli_3yr, wpa_li) does not exist in a history row.
  // This one is an ALLOW-list (the starter/hitter boards use drop-lists), so a
  // new current-only column such as WAR/IP+ or WAR/IP+ 3yr is excluded from the
  // history board by simply not being listed here.
  var REL_HISTORY_KEYS = { name: 1, rem_plus: 1, riv_plus: 1, ip: 1, g: 1, k_pct: 1,
    bb_pct: 1, k_bb_pct: 1, fip: 1, swstr_pct: 1, era: 1, gmli: 1, wpa: 1, sd_md: 1 };
  var REL_HISTORY_COLS = REL_COLS.filter(function (c) { return REL_HISTORY_KEYS[c.key]; });

  var TEAM_COLS = [
    { key: "team", label: "Team", sortable: true, kind: "team", asc: true },
    { key: "bullpen_plus", label: "Bullpen+", term: "bullpen_plus", fmt: remCell, num: true, desc: true, isRem: true },
    // GLOSSARY PROXY, deliberate. There is no leverage_deploy_plus entry: the
    // glossary defines bullpen_plus, and Lev Deploy+ is the same index computed
    // on leverage-weighted rather than IP-weighted innings, so the tooltip
    // explains the scale a reader needs even though the id is not this column's
    // own. Point it at a real leverage_deploy_plus entry the day one exists;
    // until then a near-miss definition beats no tooltip at all.
    { key: "leverage_deploy_plus", label: "Lev Deploy+", term: "bullpen_plus", fmt: remCell, num: true,
      title: "Bullpen+ recomputed on leverage-weighted innings: how good the arms are in the spots that actually decide games, rather than across all relief innings equally. Same 100-average scale." },
    { key: "n_above_avg", label: "Above-avg arms", fmt: fInt, num: true,
      get: function (t) { var a = num(t.n_above_avg), n = num(t.n_relievers); return a; },
      cell: function (t) { return fInt(t.n_above_avg) + (t.n_relievers != null ? '<span class="proj-dim"> / ' + fInt(t.n_relievers) + "</span>" : ""); } },
    { key: "high_lev_core_rem", label: "Hi-Lev Core", fmt: remCell, num: true },
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
  //   <payload>.multiyear            -> REM+ 3yr / SEM+ 3yr / HEM+ 3yr
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
    return "FROZEN LAB COLUMN: read verbatim from " + (b.source || "a lab artifact")
      + ", generated " + b.generated_at + (w ? " over the " + w + " window" : "")
      + ". These values are as of that date, NOT as of this board's date, so the column can"
      + " trail the season columns beside it and anyone who entered the pool since then is blank.";
  }
  // Compact board note. `cols` is [[payload key, column label], ...]; a block
  // that is absent or unavailable simply contributes nothing.
  function vintageNote(meta, cols, extra) {
    var bits = [];
    (cols || []).forEach(function (p) {
      var b = vintageOf(meta, p[0]);
      if (!b) return;
      var w = vintageWindow(b);
      bits.push(esc(p[1]) + " as of " + esc(b.generated_at) + (w ? " (" + esc(w) + ")" : ""));
    });
    if (!bits.length) return "";
    return '<div class="mlbstats-note mlbstats-vintage"><b>Frozen columns:</b> ' + bits.join(", ")
      + ". The trailing-window columns are read verbatim from lab artifacts rather than recomputed"
      + " with this board, so they carry their own date and stay blank for anyone who joined the"
      + " pool after it." + (extra || "") + "</div>";
  }

  // ---- render: shared table -------------------------------------------------
  // `meta` is the section payload, passed only so a column flagged
  // `vintage: "<payload key>"` can date itself in its own tooltip.
  function renderTable(rows, cols, sort, meta) {
    var head = "<thead><tr>";
    cols.forEach(function (c) {
      var sortable = !!c.num || c.kind === "name" || c.kind === "team";
      var sorted = (c.key === sort.key) ? " is-sorted" : "";
      var lbl = c.term ? gloss(c.label, c.term) : esc(c.label);
      var vint = c.vintage ? vintageTitle(vintageOf(meta, c.vintage)) : "";
      var titleTxt = c.title ? (vint ? c.title + " " + vint : c.title) : vint;
      var title = titleTxt ? ' title="' + esc(titleTxt) + '"' : "";
      // keyboard-operable sort headers (the trademachine _tbTh pattern):
      // tabbable, announced as sorted, activated by Enter/Space via bindSortKeys
      var a11y = sortable
        ? ' tabindex="0" role="button" aria-sort="' + ((c.key === sort.key) ? (sort.asc ? "ascending" : "descending") : "none") + '"'
        : "";
      head += '<th class="mlbstats-col-' + c.key + sorted + '"' + title + a11y + ' data-col="' + c.key + '">' + lbl + "</th>";
    });
    head += "</tr></thead>";

    var body = "<tbody>";
    rows.forEach(function (r) {
      var prov = (r.qualified === false) ? " is-provisional" : "";
      body += "<tr" + prov + ">";
      cols.forEach(function (c) {
        if (c.kind === "name") { body += nameCell(r); return; }
        if (c.kind === "team") { body += '<td class="mlbstats-name">' + logo(r.team) + esc(r.team || EM_DASH) + "</td>"; return; }
        if (c.cell) { body += "<td>" + c.cell(r) + "</td>"; return; }
        var v = getVal(c, r);
        // An absent value reads as the site-wide null marker rather than a
        // blank cell. Columns with their own formatter keep it: those
        // formatters all route through the shared number-format contract now,
        // so they render the same token. A non-numeric value (none ship today)
        // falls through to escaped text rather than the contract, which would
        // read it as absent.
        var rendered = c.fmt ? c.fmt(v, c.term)
                     : (v == null || v === "" ? EM_DASH : esc(v));
        body += "<td>" + rendered + "</td>";
      });
      body += "</tr>";
    });
    body += "</tbody>";
    return '<table class="mlbstats-table">' + head + body + "</table>";
  }

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

  // The identity cell is capped at 260px and ellipsized (site.css), so a long
  // name-plus-team-plus-role runs off the end: measured at 390px, "Antonio
  // Senzatela COL High-leverage" needs 263px and loses its tail. The full
  // string therefore rides `title` on the CELL - and, because a title on the
  // anchor would win over the cell's for a pointer over the name itself, on
  // the LINK too. The link keeps its affordance hint after the name rather
  // than instead of it.
  function nameCell(r) {
    var role = r.role ? ' <span class="bp-role">' + esc(r.role) + "</span>" : "";
    var team = r.team ? '<span class="proj-dim"> ' + esc(r.team) + "</span>" : "";
    var prov = (r.qualified === false) ? '<span class="bp-prov" title="below the qualifying sample - shown but provisional">prov</span>' : "";
    var nm = esc(r.name || EM_DASH);
    // A row with no name at all gets no title rather than a title of null
    // markers: an empty tooltip is worse than none.
    var full = [r.name, r.team, r.role].filter(Boolean).join(" - ");
    if (full && r.qualified === false) full += " (provisional)";
    var href = playerHref(r);
    var name = href
      ? '<a class="mlbstats-name-link" href="' + href + '" title="'
        + (full ? esc(full) + " - " : "") + 'open the MLB player card">' + nm + "</a>"
      : nm;
    return '<td class="mlbstats-name"' + (full ? ' title="' + esc(full) + '"' : "") + ">"
      + logo(r.team) + name + team + role + prov + "</td>";
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
  function seasonPills() {
    var pills = [["current", "Current"]];
    historySeasons().slice().sort(function (a, b) { return b - a; }).forEach(function (y) {
      pills.push([String(y), String(y)]);
    });
    return '<div class="mlbstats-seasons" role="tablist" aria-label="Season">' + pills.map(function (p) {
      var sel = (p[0] === relSeason);
      return '<button type="button" class="mlbstats-season' + (sel ? " active" : "")
        + '" data-mlbseason="' + esc(p[0]) + '" role="tab" aria-selected="' + sel + '">' + esc(p[1]) + "</button>";
    }).join("") + "</div>";
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

  // On-page explainers for the headline metrics (F-08): 1-2 plain sentences,
  // wired to the shared glossary tooltip (data-gl via gloss()) plus a deep link
  // into the unified glossary entry.
  function explainer(term, html) {
    return '<div class="mlbstats-note mlbstats-explainer">' + html
      + ' <a href="/glossary/#g=' + encodeURIComponent(term) + '">Full definition in the glossary.</a></div>';
  }
  function remExplainer() {
    return explainer("rem_plus", gloss("REM+", "rem_plus")
      + " measures a reliever's run-prevention skill on a league-relative scale: 100 is an average reliever, 110 is 10 percent"
      + " better. It is FIP-based and regressed for small samples, so role and ball-in-play luck do not move it;"
      + " the leverage columns carry the usage context separately.");
  }
  function bullpenExplainer() {
    return explainer("bullpen_plus", gloss("Bullpen+", "bullpen_plus")
      + " rates a whole pen on the same 100-average scale, weighting each reliever's "
      + gloss("REM+", "rem_plus")
      + " by the relief innings he actually throws. It reads the talent of the innings a bullpen really uses.");
  }

  function renderRelievers() {
    if (relSeason !== "current") return renderRelieverHistory();
    var rows = sortRows(filteredRelievers(), REL_COLS, relSort);
    var body = rows.length
      ? (function () {
          var note = '<div class="mlbstats-note">'
            + gloss("REM+", "rem_plus") + " is pure run-prevention skill (100 = average reliever); "
            + gloss("RIV+", "riv_plus") + " is realized leverage-weighted value, and "
            + "gmLI / WPA / WPA-LI / SD-MD are the leverage context, kept separate. "
            + gloss("WAR/IP+", "war_ip_plus_rp")
            + " is banked value per inning, anchored on RELIEVERS only, so it does not compare with the"
            + " starter board's column of the same name; 10 of its points is one standard deviation.</div>";
          return proseFold("rel-about", rows.length + " relievers",
              remExplainer() + scorecard() + note
              + vintageNote(DATA, [["multiyear", "REM+ 3yr"], ["multiyear_war_rate", "WAR/IP+ 3yr"]],
                  " gmLI 3yr is frozen the same way, from the leverage-consistency artifact, which ships no"
                  + " date for the board to quote."))
            + relieverViz()
            + '<div class="mlbstats-scroll">' + renderTable(rows, REL_COLS, relSort, DATA) + "</div>";
        })()
      : '<div class="mlbstats-empty">No relievers match the current filters.</div>';
    return seasonPills() + body;
  }

  // A past season's board: the same table and controls, restricted to the
  // columns a history row carries (no trailing-window or WPA/LI columns). It
  // lets a user eyeball how each season's REM+ (skill) and RIV+ (impact) aged.
  function renderRelieverHistory() {
    var pills = seasonPills();
    if (HISTORY_ERROR) {
      return pills + '<div class="mlbstats-empty mlbstats-load-error" role="alert">'
        + "Season history failed to load. Refresh to retry; if it persists the nightly build is mid-run. "
        + '<button type="button" class="chip" id="mlbstats-history-retry">Retry</button></div>';
    }
    if (!HISTORY) {
      loadHistory();
      return pills + '<div class="mlbstats-empty">Loading the ' + esc(relSeason) + " season leaderboard&hellip;</div>";
    }
    if (HISTORY_LOADING) {
      return pills + '<div class="mlbstats-empty">Loading the ' + esc(relSeason) + " season leaderboard&hellip;</div>";
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
      '<div class="mlbstats-note">' + gloss("REM+", "rem_plus") + " is the skill read and "
      + gloss("RIV+", "riv_plus") + " is realized leverage-weighted value; compare them against how "
      + "these arms actually played forward.</div>");
    var table = rows.length
      ? '<div class="mlbstats-scroll">' + renderTable(rows, REL_HISTORY_COLS, sort) + "</div>"
      : '<div class="mlbstats-empty">No relievers match the current filters.</div>';
    return pills + cap + table;
  }

  function renderTeams() {
    var rows = (DATA && DATA.teams) || [];
    rows = sortRows(rows, TEAM_COLS, teamSort);
    if (!rows.length) return '<div class="mlbstats-empty">No team bullpens to show yet.</div>';
    var note = '<div class="mlbstats-note">' + gloss("Bullpen+", "bullpen_plus")
      + " weights each pen by the quality of the relief innings it throws (relief-IP-weighted REM+); "
      + "Lev Deploy+ adds how much leverage those innings carry.</div>";
    return proseFold("relteam-about", rows.length + " bullpens", bullpenExplainer() + note)
      + '<div class="mlbstats-scroll">' + renderTable(rows, TEAM_COLS, teamSort) + "</div>";
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
          + '<span class="bp-slot-rem ' + remClass(r.rem_plus) + '">' + fInt(r.rem_plus) + "</span>"
          + "</div>";
      }).join("");
      return '<div class="bp-depth-card"><div class="bp-depth-head">'
        + '<span class="bp-depth-team">' + logo(t.team) + esc(t.team) + "</span>"
        + '<span class="rem-plus ' + remClass(t.bullpen_plus) + '" data-gl="bullpen_plus">Bullpen+ ' + fInt(t.bullpen_plus) + "</span>"
        + "</div>" + slots + "</div>";
    }).join("");
    return '<div class="mlbstats-note">Each pen as a leverage ladder: who actually pitches the high-leverage innings, and how good they are ('
      + gloss("REM+", "rem_plus") + " per slot).</div>" + '<div class="bp-depth-grid">' + cards + "</div>";
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
  function bannerHTML(d, opts) {
    if (!d) return "";
    var o = opts || {};
    var bits = [];
    if (d.season) bits.push("Season " + esc(d.season));
    if (d.as_of) bits.push("through " + esc(d.as_of));
    if (!o.noCoverage && d.coverage && d.coverage.games != null) {
      var cov = d.coverage;
      // bullpen stamps `expected`, leverage stamps `games_total`.
      var tot = (cov.expected != null) ? cov.expected : cov.games_total;
      bits.push(esc(cov.games) + (tot != null ? " / " + esc(tot) : "") + " games of play-by-play");
    }
    if (d.verdict === "validated") {
      bits.push('<span class="bp-validated" title="Backtested out of sample - see the scorecard below">backtested</span>');
    } else if (d.verdict) {
      bits.push('<span class="bp-prov" style="margin-left:0">' + esc(d.verdict) + "</span>");
    }
    if (!bits.length) return "";
    return '<div class="mlbstats-note mlbstats-freshness">' + bits.join(" &middot; ") + "</div>";
  }
  function banner() { return bannerHTML(DATA); }

  // REM+ accountability scorecard - mirrors PAL's pattern so a validated model
  // surfaces its out-of-sample backtest to users, not just a status word.
  function scorecard() {
    var b = (DATA && DATA.backtest) || {};
    if (b.rho_rem_plus == null) return "";
    return '<div class="mlbstats-scorecard">'
      + '<span class="pal-sc-stat">' + gloss("REM+", "rem_plus") + ' forward &rho; <b>'
      + b.rho_rem_plus + '</b><span class="proj-dim"> vs FIP ' + (b.rho_fip == null ? EM_DASH : b.rho_fip)
      + ", ERA " + (b.rho_era == null ? EM_DASH : b.rho_era) + "</span></span>"
      + '<span class="pal-sc-stat"><b>' + esc(b.n_pairs) + "</b> out-of-sample year pairs"
      + (b.seasons ? '<span class="proj-dim"> (' + esc(b.seasons) + " seasons)</span>" : "") + "</span>"
      + (b.market_rho == null ? "" : '<span class="pal-sc-stat">market fit &rho; <b>' + b.market_rho + '</b><span class="proj-dim"> vs AAV</span></span>')
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
    return '<div class="mlbstats-bar">'
      + '<label class="mlbstats-ctl">'
      + '<input type="checkbox" id="mlbstats-qual"' + (qualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-team", pool, relTeam)
      + minSelect("mlbstats-minip", "min IP", relMinIp,
          "Hide relievers under this many innings. Composes with qualified only, which is the coarser gate.")
      + gfxChip("mlbstats-rel-gfx")
      + '<input class="mlbstats-search" type="search" id="mlbstats-q" placeholder="Search reliever or team" value="' + esc(query) + '">'
      + "</div>"
      + roleChips(pool, relRoles, "mlbstats-role-");
  }

  function render() {
    var root = document.getElementById("mlbstats-app-root");
    if (!root) return;
    if (!DATA) {
      root.innerHTML = LOAD_ERROR
        ? '<div class="mlbstats-empty mlbstats-load-error" role="alert">Data failed to load. Refresh to retry; '
          + 'if it persists the nightly build is mid-run. '
          + '<button type="button" class="chip" id="mlbstats-retry">Retry</button></div>'
        : '<div class="mlbstats-empty">Bullpen Leaderboards are being computed from MLB play-by-play. '
          + "Check back shortly.</div>";
      var retry = document.getElementById("mlbstats-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = '<div class="mlbstats-empty">Loading&hellip;</div>';
        load();
      });
      return;
    }
    var inner = (view === "teams") ? renderTeams() : (view === "depth") ? renderDepth() : renderRelievers();
    root.innerHTML = tabBar() + controls() + inner;
    bindEvents(root);
    wireGlossary(root);
    var bann = document.getElementById("mlbstats-banner");
    if (bann) bann.innerHTML = banner();
  }

  function bindEvents(root) {
    bindCollapse(root);
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
      var rows = (relSeason === "current")
        ? sortRows(filteredRelievers(), REL_COLS, relSort)
        : sortRows(filteredHistory(), REL_HISTORY_COLS, historySort());
      EEPHUS_GFX.open(_mlbstatsBoardSpec("relievers", rows));
    });
    var teamGfx = root.querySelector("#mlbstats-teams-gfx");
    if (teamGfx) teamGfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      EEPHUS_GFX.open(_mlbstatsBoardSpec("bullpens", sortRows((DATA && DATA.teams) || [], TEAM_COLS, teamSort)));
    });
    root.querySelectorAll("[data-mlbseason]").forEach(function (b) {
      b.addEventListener("click", function () {
        relSeason = b.getAttribute("data-mlbseason");
        if (relSeason !== "current") loadHistory();
        writeHash();
        render();
      });
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
  };
  // A season key is "current" or a four-digit year; anything else is ignored
  // rather than trusted, because the value goes straight into a payload lookup.
  function readSeason(h, key, fallback) {
    var m = new RegExp("(?:^#|[#&])" + key + "=(current|\\d{4})\\b").exec(h);
    return m ? m[1] : fallback;
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
    // Top-level section deep-link (#section=bullpen|starters|hitters) + the
    // per-section view (#view= bullpen, #sview= starters). Each key is anchored
    // to a separator so e.g. "sview=teams" can never match the "view=" regex.
    var s = /(?:^#|[#&])section=(bullpen|starters|hitters|leverage)\b/.exec(h);
    if (s) section = s[1];
    var m = /(?:^#|[#&])view=(relievers|teams|depth)\b/.exec(h);
    if (m) view = m[1];
    var sv = /(?:^#|[#&])sview=(starters|teams|charts)\b/.exec(h);
    if (sv) starterView = sv[1];
    var hv = /(?:^#|[#&])hview=(hitters|teams|charts)\b/.exec(h);
    if (hv) hitterView = hv[1];
    var lv = /(?:^#|[#&])lview=(batters|starters)\b/.exec(h);
    if (lv) leverageView = lv[1];
    // Season pills. readHash runs from init(), after every one of these vars
    // and column arrays has been assigned, so the forward references are safe.
    relSeason = readSeason(h, "rseason", relSeason);
    starterSeason = readSeason(h, "sseason", starterSeason);
    hitterSeason = readSeason(h, "hseason", hitterSeason);
    leverageSeason = readSeason(h, "lseason", leverageSeason);
    // Sort per board.
    readSort(h, "rsort", REL_COLS, relSort);
    readSort(h, "rtsort", TEAM_COLS, teamSort);
    readSort(h, "ssort", STARTER_COLS, starterSort);
    readSort(h, "stsort", STARTER_TEAM_COLS, starterTeamSort);
    readSort(h, "hsort", HITTER_COLS, hitterSort);
    readSort(h, "htsort", HITTER_TEAM_COLS, hitterTeamSort);
    readSort(h, "lbsort", BAT_LEV_COLS, leverageBatSort);
    readSort(h, "lssort", STARTER_LEV_COLS, leverageStarterSort);
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
    if (relSeason && relSeason !== "current") parts.push("rseason=" + relSeason);
    if (starterSeason && starterSeason !== "current") parts.push("sseason=" + starterSeason);
    if (hitterSeason && hitterSeason !== "current") parts.push("hseason=" + hitterSeason);
    if (leverageSeason && leverageSeason !== "current") parts.push("lseason=" + leverageSeason);
    pushSort(parts, "rsort", relSort);
    pushSort(parts, "rtsort", teamSort);
    pushSort(parts, "ssort", starterSort);
    pushSort(parts, "stsort", starterTeamSort);
    pushSort(parts, "hsort", hitterSort);
    pushSort(parts, "htsort", hitterTeamSort);
    pushSort(parts, "lbsort", leverageBatSort);
    pushSort(parts, "lssort", leverageStarterSort);
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
  // skill (100 = average qualified starter), and durability (IP, GS, average
  // start length) rides context columns so workload never moves the skill
  // number. Renders into #mlbstats-starters-root; reuses every shared helper
  // (renderTable / sortRows / gloss / remCell / explainer / season pills).
  // ===========================================================================
  var section = "bullpen";                    // bullpen | starters
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
    { key: "sem_plus", label: "SEM+", term: "sem_plus", fmt: remCell, num: true, desc: true, isRem: true },
    { key: "sem_plus_3yr", label: "SEM+ 3yr", term: "sem_plus_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear",
      get: function (r) { return r.sem_plus_3yr; },
      cell: function (r) {
        if (r.sem_plus_3yr == null) return "";
        var s = remCell(r.sem_plus_3yr);
        if (r.sem_plus_3yr_pct != null) s += '<span class="proj-dim"> p' + fInt(r.sem_plus_3yr_pct) + "</span>";
        if (r.sem_plus_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 120 IP in the trailing window">*</span>';
        return s;
      } },
    { key: "xsem_plus", label: "xSEM+", term: "xsem_plus", num: true, desc: true, isRem: true,
      title: "Deserved run prevention: the SEM+ scale on Savant expected wOBA allowed (lower allowed = higher). A companion to SEM+, which stays FIP-based (xwOBA-allowed did not beat FIP predictively); a deserved read, not a replacement. Tracked starters only.",
      get: function (r) { return r.xsem_plus; },
      cell: function (r) { return r.xsem_plus == null ? "" : remCell(r.xsem_plus); } },
    { key: "luck", label: "Luck", num: true, desc: true,
      title: "Actual minus expected wOBA allowed. Positive = allowed more than his contact deserved (unlucky, room to improve); negative = allowed less (over-performing, due to regress).",
      get: function (r) { return r.luck; },
      cell: function (r) {
        if (r.luck == null) return "";
        var v = r.luck;
        var col = v >= 0.02 ? "var(--up)" : v <= -0.02 ? "var(--down)" : "var(--text-tertiary)";
        return '<span style="color:' + col + ';font-variant-numeric:tabular-nums;">' + (v > 0 ? "+" : "") + v.toFixed(3) + "</span>";
      } },
    // Starter-anchored WAR/IP+. The reliever board ships a reliever-anchored
    // WAR/IP+ under the same field name in its own payload; the two are separate
    // metrics on separate pools and are never pooled into one column (a reliever
    // banks more WAR per inning than a starter of equal talent). Both ride
    // remCell: 100 + 10z has SD exactly 10, which is what remClass bands for.
    { key: "war_ip_plus", label: "WAR/IP+", term: "war_ip_plus_sp", num: true, desc: true, isRem: true,
      title: "Pitching eWAR (FIP re-priced within role) per inning, indexed over STARTERS with 20+ IP: 100 is the average starter and every 10 points is one standard deviation of that pool. Anchored on starters only, so it is not comparable with the reliever board's WAR/IP+. Needs 40 IP to show. The p-number is this value's percentile on the board, because on a 10-points-per-sigma scale a modest-looking number can still be rare.",
      get: function (r) { return r.war_ip_plus; },
      cell: function (r) {
        if (r.war_ip_plus == null) return "";
        var s = remCell(r.war_ip_plus);
        if (r.war_ip_plus_pct != null) s += '<span class="proj-dim"> p' + fInt(r.war_ip_plus_pct) + "</span>";
        return s;
      } },
    { key: "war_ip_plus_adj", label: "WAR/IP+ adj", term: "war_ip_plus_sp_adj", num: true, desc: true, isRem: true,
      title: "WAR/IP+ regressed for sample size: the rate is pulled toward the pool rate by innings before indexing, so a short hot stretch does not outrank a full season. Re-standardised on the regressed pool, so 10 points is still one standard deviation. A readability aid for thin samples, not a forecast: neither WAR rate predicts next season better than plain season WAR does.",
      get: function (r) { return r.war_ip_plus_adj; },
      cell: function (r) { return r.war_ip_plus_adj == null ? "" : remCell(r.war_ip_plus_adj); } },
    { key: "war_ip_plus_3yr", label: "WAR/IP+ 3yr", term: "war_ip_plus_sp_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear_war_rate",
      get: function (r) { return r.war_ip_plus_3yr; },
      cell: function (r) {
        if (r.war_ip_plus_3yr == null) return "";
        var s = remCell(r.war_ip_plus_3yr);
        if (r.war_ip_plus_3yr_pct != null) s += '<span class="proj-dim"> p' + fInt(r.war_ip_plus_3yr_pct) + "</span>";
        if (r.war_ip_plus_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 120 IP in the trailing window">*</span>';
        return s;
      } },
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true,
      title: "Pitching eWAR this season, the numerator of WAR/IP+ (shown so the rate is checkable against the IP column). eWAR (eephus WAR): Baseball-Reference run frame with pitching re-priced on FIP; fielding unchanged pending SDR; position players match bWAR except in seasons they also pitched." },
    { key: "ip", label: "IP", fmt: f1, num: true },
    { key: "gs", label: "GS", fmt: fInt, num: true },
    { key: "ip_per_gs", label: "IP/GS", fmt: f1, num: true, title: "Average start length (innings per game started)" },
    { key: "k_pct", label: "K%", fmt: fPct, num: true },
    { key: "bb_pct", label: "BB%", fmt: fPct, num: true, asc: true },
    { key: "k_bb_pct", label: "K-BB%", fmt: fPct, num: true },
    { key: "gb_pct", label: "GB%", fmt: fPct, num: true },
    { key: "fip", label: "FIP", term: "fip", fmt: f2, num: true, asc: true },
    { key: "era", label: "ERA", term: "era", fmt: f2, num: true, asc: true },
    { key: "hr9", label: "HR/9", fmt: f2, num: true, asc: true },
  ];

  // Past-season history rows carry the season-level fields but not the
  // trailing-window SEM+ 3yr. Reuse the same column objects so the history board
  // renders and sorts identically, dropping the column its rows lack.
  var STARTER_HISTORY_DROP = { sem_plus_3yr: 1, xsem_plus: 1, luck: 1,
    war_ip_plus: 1, war_ip_plus_adj: 1, war_ip_plus_3yr: 1, war: 1 };
  var STARTER_HISTORY_COLS = STARTER_COLS.filter(function (c) { return !STARTER_HISTORY_DROP[c.key]; });

  var STARTER_TEAM_COLS = [
    { key: "team", label: "Team", sortable: true, kind: "team", asc: true },
    { key: "rotation_plus", label: "Rotation+", term: "rotation_plus", fmt: remCell, num: true, desc: true, isRem: true },
    { key: "front_sem", label: "Front 3", fmt: remCell, num: true },
    { key: "n_above_avg", label: "Above-avg", fmt: fInt, num: true,
      get: function (t) { return num(t.n_above_avg); },
      cell: function (t) { return fInt(t.n_above_avg) + (t.n_starters != null ? '<span class="proj-dim"> / ' + fInt(t.n_starters) + "</span>" : ""); } },
    { key: "starter_ip", label: "Starter IP", fmt: f1, num: true },
    { key: "total_gs", label: "GS", fmt: fInt, num: true },
  ];

  // SEM+ explainer - reuses the shared explainer() markup so it styles like the
  // reliever REM+ one, wired to the glossary tooltip (data-gl) + deep link.
  function semExplainer() {
    return explainer("sem_plus", gloss("SEM+", "sem_plus")
      + " measures a starting pitcher's pure run-prevention skill on a league-relative scale: 100 is an average"
      + " qualified starter, 110 is 10 percent better. It is FIP-based and regressed for small samples, so"
      + " durability (innings, games started, and average start length) rides the context columns instead of"
      + " moving the skill number.");
  }

  // SEM+ accountability scorecard - mirrors the reliever scorecard so a validated
  // model surfaces its out-of-sample backtest, not just a status word.
  function starterScorecard() {
    var b = (starterData && starterData.backtest) || {};
    if (b.rho_sem_plus == null) return "";
    return '<div class="mlbstats-scorecard">'
      + '<span class="pal-sc-stat">' + gloss("SEM+", "sem_plus") + ' forward &rho; <b>'
      + b.rho_sem_plus + '</b><span class="proj-dim"> vs FIP ' + (b.rho_fip == null ? EM_DASH : b.rho_fip)
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
  function starterSeasonPills() {
    var pills = [["current", "Current"]];
    starterHistorySeasons().slice().sort(function (a, b) { return b - a; }).forEach(function (y) {
      pills.push([String(y), String(y)]);
    });
    return '<div class="mlbstats-seasons" role="tablist" aria-label="Season">' + pills.map(function (p) {
      var sel = (p[0] === starterSeason);
      return '<button type="button" class="mlbstats-season' + (sel ? " active" : "")
        + '" data-starterseason="' + esc(p[0]) + '" role="tab" aria-selected="' + sel + '">' + esc(p[1]) + "</button>";
    }).join("") + "</div>";
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
    return '<div class="mlbstats-bar">'
      + '<label class="mlbstats-ctl">'
      + '<input type="checkbox" id="mlbstats-starter-qual"' + (starterQualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-starter-team", starterSourceRows(), starterTeam)
      + minSelect("mlbstats-starter-minip", "min IP", starterMinIp,
          "Hide starters under this many innings. Composes with qualified only, which is the coarser gate.")
      + gfxChip("mlbstats-starter-gfx")
      + '<input class="mlbstats-search" type="search" id="mlbstats-starter-q" placeholder="Search starter or team" value="' + esc(starterQuery) + '">'
      + "</div>";
  }

  function renderStarterBoard() {
    if (starterSeason !== "current") return renderStarterHistory();
    var rows = sortRows(filteredStarters(), STARTER_COLS, starterSort);
    var body = rows.length
      ? (function () {
          var note = '<div class="mlbstats-note">'
            + gloss("SEM+", "sem_plus") + " is pure run-prevention skill (100 = average qualified starter); "
            + "the durability columns (IP, GS, IP/GS) are context, kept separate from the skill number. "
            + gloss("WAR/IP+", "war_ip_plus_sp")
            + " is banked value per inning, anchored on STARTERS only, so it does not compare with the"
            + " reliever board's column of the same name; 10 of its points is one standard deviation.</div>";
          return proseFold("sp-about", rows.length + " starters",
              semExplainer() + starterScorecard() + note
              + vintageNote(starterData, [["multiyear", "SEM+ 3yr"], ["multiyear_war_rate", "WAR/IP+ 3yr"]]))
            + '<div class="mlbstats-scroll">' + renderTable(rows, STARTER_COLS, starterSort, starterData) + "</div>";
        })()
      : '<div class="mlbstats-empty">No starters match the current filters.</div>';
    return starterSeasonPills() + body;
  }

  // A past season's board: the same table and controls, restricted to the
  // columns a history row carries (no SEM+ 3yr trailing-window column). It lets a
  // user eyeball how each season's SEM+ (skill) aged forward.
  function renderStarterHistory() {
    var pills = starterSeasonPills();
    if (STARTER_HISTORY_ERROR) {
      return pills + '<div class="mlbstats-empty mlbstats-load-error" role="alert">'
        + "Season history failed to load. Refresh to retry; if it persists the nightly build is mid-run. "
        + '<button type="button" class="chip" id="mlbstats-starter-history-retry">Retry</button></div>';
    }
    if (!STARTER_HISTORY) {
      loadStarterHistory();
      return pills + '<div class="mlbstats-empty">Loading the ' + esc(starterSeason) + " season leaderboard&hellip;</div>";
    }
    if (STARTER_HISTORY_LOADING) {
      return pills + '<div class="mlbstats-empty">Loading the ' + esc(starterSeason) + " season leaderboard&hellip;</div>";
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
      '<div class="mlbstats-note">' + gloss("SEM+", "sem_plus") + " is the skill read; the durability columns"
      + " (IP, GS, IP/GS) are context. Compare against how these arms actually pitched forward.</div>");
    var table = rows.length
      ? '<div class="mlbstats-scroll">' + renderTable(rows, STARTER_HISTORY_COLS, sort) + "</div>"
      : '<div class="mlbstats-empty">No starters match the current filters.</div>';
    return pills + cap + table;
  }

  function renderStarterTeams() {
    var rows = (starterData && starterData.teams) || [];
    rows = sortRows(rows, STARTER_TEAM_COLS, starterTeamSort);
    if (!rows.length) return '<div class="mlbstats-empty">No team rotations to show yet.</div>';
    var note = '<div class="mlbstats-note">' + gloss("Rotation+", "rotation_plus") + ' weights each rotation by the '
      + gloss("SEM+", "sem_plus") + " of the starter innings it throws (starter-IP-weighted). Front 3 reads the"
      + " top of the rotation; the durability columns are context.</div>";
    return proseFold("spteam-about", rows.length + " rotations", note)
      + '<div class="mlbstats-scroll">' + renderTable(rows, STARTER_TEAM_COLS, starterTeamSort) + "</div>";
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
      + ' distribution <span class="proj-dim">(qualified starters; cyan = elite)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Skill vs durability'
        + ' <span class="proj-dim">(top-right = front-line workhorses)</span></div>' + sc + "</div>" : "")
      + (xsc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Earned vs deserved: SEM+ × ' + gloss("xSEM+", "xsem_plus")
        + ' <span class="proj-dim">(below the diagonal = results ahead of contact quality)</span></div>' + xsc + "</div>" : "")
      + "</div>";
    return collapsible("starters-viz", 'Distribution <span class="proj-dim">(SEM+ spread, durability, earned vs deserved)</span>', body);
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
          + '<span class="bp-slot-rem ' + remClass(r.sem_plus) + '">' + fInt(r.sem_plus) + "</span>"
          + "</div>";
      }).join("");
      return '<div class="bp-depth-card"><div class="bp-depth-head">'
        + '<span class="bp-depth-team">' + logo(t.team) + esc(t.team) + "</span>"
        + '<span class="rem-plus ' + remClass(t.rotation_plus) + '" data-gl="rotation_plus">Rotation+ ' + fInt(t.rotation_plus) + "</span>"
        + "</div>" + slots + "</div>";
    }).join("");
    return '<div class="mlbstats-note">Each rotation as a depth ladder: its starters ordered by workload, with '
      + gloss("SEM+", "sem_plus") + " per slot (skill) and average start length.</div>"
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
        ? '<div class="mlbstats-empty mlbstats-load-error" role="alert">Data failed to load. Refresh to retry; '
          + 'if it persists the nightly build is mid-run. '
          + '<button type="button" class="chip" id="mlbstats-starter-retry">Retry</button></div>'
        : '<div class="mlbstats-empty">Starter Leaderboards are being computed from MLB play-by-play. '
          + "Check back shortly.</div>";
      var retry = document.getElementById("mlbstats-starter-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = '<div class="mlbstats-empty">Loading&hellip;</div>';
        loadStarters();
      });
      return;
    }
    var inner = (starterView === "teams") ? renderStarterTeams()
      : (starterView === "charts") ? renderStarterCharts() : renderStarterBoard();
    // No #mlbstats-banner div exists for this section, so the freshness line
    // leads the section's own root.
    root.innerHTML = bannerHTML(starterData) + starterTabBar() + starterControls() + inner;
    bindStarterEvents(root);
    wireGlossary(root);
  }

  function bindStarterEvents(root) {
    bindCollapse(root);
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
      var rows = (starterSeason === "current")
        ? sortRows(filteredStarters(), STARTER_COLS, starterSort)
        : sortRows(filteredStarterHistory(), STARTER_HISTORY_COLS, starterHistorySort());
      EEPHUS_GFX.open(_mlbstatsBoardSpec("starters", rows));
    });
    root.querySelectorAll("[data-starterseason]").forEach(function (b) {
      b.addEventListener("click", function () {
        starterSeason = b.getAttribute("data-starterseason");
        if (starterSeason !== "current") loadStarterHistory();
        writeHash();
        renderStarters();
      });
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
    root.innerHTML = bannerHTML(starterData) + starterTabBar() + starterControls() + inner;
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
  // offensive-rate skill (100 = average qualified hitter), a sample-shrunk wOBA;
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
      title: "PUBLISHED, NOT COMPUTED HERE. MLB's own wRC+ for this season, read verbatim from the league's season-total feed and matched by player id. 100 is league average, park and league adjusted. It sits here as the industry benchmark next to HEM+, which is the offense-rate index this site does compute. Because it is unshrunk it runs wider than HEM+ (about 25 points per standard deviation of the qualified pool against about 18), so it is colored on its own thresholds. A traded hitter reads one season line, not a single stint.",
      get: function (r) { return r.wrc_plus; },
      cell: function (r) { return r.wrc_plus == null ? "" : wrcCell(r.wrc_plus); } },
    { key: "hem_plus_3yr", label: "HEM+ 3yr", term: "hem_plus_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear",
      get: function (r) { return r.hem_plus_3yr; },
      cell: function (r) {
        if (r.hem_plus_3yr == null) return "";
        var s = hemCell(r.hem_plus_3yr);
        if (r.hem_plus_3yr_pct != null) s += '<span class="proj-dim"> p' + fInt(r.hem_plus_3yr_pct) + "</span>";
        if (r.hem_plus_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 600 PA in the trailing window">*</span>';
        return s;
      } },
    { key: "xhem_plus", label: "xHEM+", term: "xhem_plus", num: true, desc: true, isRem: true,
      title: "Deserved offense: the HEM+ scale on Savant expected wOBA (xwOBA). Forward-predicts next-year offense better than actual. Tracked hitters only.",
      get: function (r) { return r.xhem_plus; },
      cell: function (r) { return r.xhem_plus == null ? "" : hemCell(r.xhem_plus); } },
    { key: "fwdhem_plus", label: "xHEM+ Blend", term: "fwdhem_plus", num: true, desc: true, isRem: true,
      title: "Forward blend: 70% expected wOBA + 30% HEM+ core, on the HEM+ scale. The best single-number read on NEXT-year offense (beats xwOBA alone out of sample). Tracked hitters only.",
      get: function (r) { return r.fwdhem_plus; },
      cell: function (r) { return r.fwdhem_plus == null ? "" : hemCell(r.fwdhem_plus); } },
    { key: "pwoba", label: "pWOBA", term: "pwoba", num: true, desc: true,
      title: "Projected NEXT-season wOBA from the site's FA-engine Marcel (the validated projection engine: forward rho 0.5189 vs next-year wOBA, best of five gated arms). Read like wOBA: ~.310 average, .400 elite. Tracked hitters with a recent MLB sample only.",
      get: function (r) { return r.pwoba; },
      cell: function (r) {
        if (r.pwoba == null) return "";
        // Color by pool percentile (the export stamps pwoba_pctile), same
        // rem-* bands as the HEM+ family so the board reads as one system.
        var p = num(r.pwoba_pctile);
        var cls = p == null ? "rem-avg" : p >= 90 ? "rem-elite" : p >= 70 ? "rem-good" : p >= 25 ? "rem-avg" : "rem-low";
        return '<span class="rem-plus ' + cls + '" data-gl="pwoba">' + f3(r.pwoba) + "</span>";
      } },
    { key: "luck_gap", label: "Luck", num: true, desc: true,
      title: "xHEM+ minus HEM+: positive = under-performing his contact quality (bad luck, room to bounce back); negative = over-performing (due to regress).",
      get: function (r) { return r.luck_gap; },
      cell: function (r) {
        if (r.luck_gap == null) return "";
        var v = r.luck_gap;
        var col = v >= 13 ? "var(--up)" : v <= -13 ? "var(--down)" : "var(--text-tertiary)";
        return '<span style="color:' + col + ';font-variant-numeric:tabular-nums;">' + (v > 0 ? "+" : "") + fInt(v) + "</span>";
      } },
    // WAR/PA+ rides remCell, NOT hemCell, and that is deliberate. The HEM+
    // family around it is a ratio index widened to wRC+ width (SD about 16), so
    // hemCell bands at 112/130. WAR/PA+ is 100 + 10z, so its SD is exactly 10 by
    // construction and the +-2-sigma read is 80/120, which is what remClass
    // bands at. Recoloring it with hemCell would call a 1.2-sigma hitter
    // average. Do not "fix" this to match the neighbouring columns.
    { key: "war_pa_plus", label: "WAR/PA+", term: "war_pa_plus", num: true, desc: true, isRem: true,
      title: "Batting eWAR (equal to bWAR on the batting side) per plate appearance, indexed over hitters with 50+ PA: 100 is average and every 10 points is one standard deviation of that pool (not the wRC+-width scale HEM+ uses). Whole-player batting value per trip, so it carries fielding, baserunning and the positional adjustment, which HEM+ deliberately leaves out. Needs 100 PA to show. The p-number is this value's percentile on the board, because on a 10-points-per-sigma scale a modest-looking number can still be rare.",
      get: function (r) { return r.war_pa_plus; },
      cell: function (r) {
        if (r.war_pa_plus == null) return "";
        var s = remCell(r.war_pa_plus);
        if (r.war_pa_plus_pct != null) s += '<span class="proj-dim"> p' + fInt(r.war_pa_plus_pct) + "</span>";
        return s;
      } },
    { key: "war_pa_plus_adj", label: "WAR/PA+ adj", term: "war_pa_plus_adj", num: true, desc: true, isRem: true,
      title: "WAR/PA+ regressed for sample size: the rate is pulled toward the league rate by playing time before indexing, so a hot 110-PA line does not outrank a full season. Re-standardised on the regressed pool, so 10 points is still one standard deviation. A readability aid for thin samples, not a forecast: neither WAR rate predicts next season better than plain season WAR does.",
      get: function (r) { return r.war_pa_plus_adj; },
      cell: function (r) { return r.war_pa_plus_adj == null ? "" : remCell(r.war_pa_plus_adj); } },
    { key: "war_pa_plus_3yr", label: "WAR/PA+ 3yr", term: "war_pa_plus_3yr", num: true, desc: true, isRem: true,
      vintage: "multiyear_war_rate",
      get: function (r) { return r.war_pa_plus_3yr; },
      cell: function (r) {
        if (r.war_pa_plus_3yr == null) return "";
        var s = remCell(r.war_pa_plus_3yr);
        if (r.war_pa_plus_3yr_pct != null) s += '<span class="proj-dim"> p' + fInt(r.war_pa_plus_3yr_pct) + "</span>";
        if (r.war_pa_plus_3yr_tag === "provisional") s += '<span class="proj-dim" title="Provisional: under 2 seasons or 600 PA in the trailing window">*</span>';
        return s;
      } },
    { key: "war", label: "eWAR", term: "ewar", fmt: f1, num: true,
      title: "Batting eWAR this season, the numerator of WAR/PA+ (shown so the rate is checkable against the PA column). eWAR (eephus WAR): Baseball-Reference run frame with pitching re-priced on FIP; fielding unchanged pending SDR; position players match bWAR except in seasons they also pitched." },
    { key: "pa", label: "PA", fmt: fInt, num: true },
    { key: "hr", label: "HR", fmt: fInt, num: true },
    { key: "sb", label: "SB", fmt: fInt, num: true },
    { key: "avg", label: "AVG", fmt: f3, num: true, title: "Batting average (context)" },
    { key: "obp", label: "OBP", fmt: f3, num: true },
    { key: "slg", label: "SLG", fmt: f3, num: true },
    { key: "ops", label: "OPS", fmt: f3, num: true },
    { key: "iso", label: "ISO", fmt: f3, num: true, title: "Isolated power (SLG - AVG)" },
    { key: "woba", label: "wOBA", term: "hem_plus", fmt: f3, num: true, title: "Shrunk wOBA (the HEM+ skill core)" },
    { key: "bb_pct", label: "BB%", fmt: fPct, num: true },
    { key: "k_pct", label: "K%", fmt: fPct, num: true, asc: true },
    { key: "babip", label: "BABIP", fmt: f3, num: true },
  ];

  // History rows carry the season fields but not the trailing-window HEM+ 3yr,
  // the current-season Savant xHEM+ / xHEM+ Blend / Luck joins, or the
  // current-projection-only pWOBA column (a past board has no "next season").
  // The WAR-rate columns are joined only on the live board (the history export
  // carries no WAR join), so they drop out of a past-season board rather than
  // rendering as a blank column. Published wRC+ drops for the same reason: the
  // league feed serves it for every history season, but hitter_export joins it
  // on the live board only, so a past board would render the column empty.
  var HITTER_HISTORY_DROP = { hem_plus_3yr: 1, xhem_plus: 1, fwdhem_plus: 1, luck_gap: 1, pwoba: 1,
    war_pa_plus: 1, war_pa_plus_adj: 1, war_pa_plus_3yr: 1, war: 1, wrc_plus: 1 };
  var HITTER_HISTORY_COLS = HITTER_COLS.filter(function (c) { return !HITTER_HISTORY_DROP[c.key]; });
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
    { key: "heart_hem", label: "Heart 3", fmt: hemCell, num: true, title: "Top-3 regulars by HEM+ (heart of the order)" },
    { key: "n_above_avg", label: "Above-avg", fmt: fInt, num: true,
      get: function (t) { return num(t.n_above_avg); },
      cell: function (t) { return fInt(t.n_above_avg) + (t.n_hitters != null ? '<span class="proj-dim"> / ' + fInt(t.n_hitters) + "</span>" : ""); } },
    { key: "team_pa", label: "PA", fmt: fInt, num: true },
  ];

  function hemExplainer() {
    return explainer("hem_plus", gloss("HEM+", "hem_plus")
      + " measures a hitter's pure offensive-rate skill on a league-relative scale (100 = an average"
      + " qualified hitter), scaled to the wRC+ convention so the league reads with real separation"
      + " (roughly 15 points per standard deviation). It is a sample-shrunk wOBA (the wRC+ family), so"
      + " volume (PA), baserunning (SB), and the slash line ride the context columns instead of moving"
      + " the skill number.");
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
  function hitterSeasonPills() {
    var pills = [["current", "Current"]];
    hitterHistorySeasons().slice().sort(function (a, b) { return b - a; }).forEach(function (y) {
      pills.push([String(y), String(y)]);
    });
    return '<div class="mlbstats-seasons" role="tablist" aria-label="Season">' + pills.map(function (p) {
      var sel = (p[0] === hitterSeason);
      return '<button type="button" class="mlbstats-season' + (sel ? " active" : "")
        + '" data-hitterseason="' + esc(p[0]) + '" role="tab" aria-selected="' + sel + '">' + esc(p[1]) + "</button>";
    }).join("") + "</div>";
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
    return '<div class="mlbstats-bar">'
      + '<label class="mlbstats-ctl">'
      + '<input type="checkbox" id="mlbstats-hitter-qual"' + (hitterQualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-hitter-team", hitterSourceRows(), hitterTeam)
      + minSelect("mlbstats-hitter-minpa", "min PA", hitterMinPa,
          "Hide hitters under this many plate appearances. Composes with qualified only, which is the coarser gate.")
      + gfxChip("mlbstats-hitter-gfx")
      + '<input class="mlbstats-search" type="search" id="mlbstats-hitter-q" placeholder="Search hitter or team" value="' + esc(hitterQuery) + '">'
      + "</div>";
  }

  function renderHitterBoard() {
    if (hitterSeason !== "current") return renderHitterHistory();
    var rows = sortRows(filteredHitters(), HITTER_COLS, hitterSort);
    var body = rows.length
      ? (function () {
          var note = '<div class="mlbstats-note">'
            + gloss("HEM+", "hem_plus") + " is pure offensive-rate skill (100 = average qualified hitter); "
            + "the volume (PA, HR, SB) and slash columns are context, kept separate from the skill number. "
            + gloss("wRC+", "wrc_plus")
            + " beside it is the industry's published number, not one of ours: it is read verbatim from"
            + " MLB's season-total feed and matched by player id, so this site still derives no wRC+ of"
            + " its own. It runs wider than HEM+ because it is unshrunk, which is why the two columns"
            + " color on different thresholds. "
            + gloss("WAR/PA+", "war_pa_plus")
            + " is a different question and a different ruler: total batting value per plate appearance,"
            + " fielding and baserunning included, and 10 of its points is one standard deviation rather"
            + " than the wider spread HEM+ reads on.</div>";
          return proseFold("hit-about", rows.length + " hitters",
              hemExplainer() + hitterScorecard() + note
              + vintageNote(hitterData, [["multiyear", "HEM+ 3yr"], ["multiyear_war_rate", "WAR/PA+ 3yr"]]))
            + '<div class="mlbstats-scroll">' + renderTable(rows, HITTER_COLS, hitterSort, hitterData) + "</div>";
        })()
      : '<div class="mlbstats-empty">No hitters match the current filters.</div>';
    return hitterSeasonPills() + body;
  }

  function renderHitterHistory() {
    var pills = hitterSeasonPills();
    if (HITTER_HISTORY_ERROR) {
      return pills + '<div class="mlbstats-empty mlbstats-load-error" role="alert">'
        + "Season history failed to load. Refresh to retry; if it persists the nightly build is mid-run. "
        + '<button type="button" class="chip" id="mlbstats-hitter-history-retry">Retry</button></div>';
    }
    if (!HITTER_HISTORY) {
      loadHitterHistory();
      return pills + '<div class="mlbstats-empty">Loading the ' + esc(hitterSeason) + " season leaderboard&hellip;</div>";
    }
    if (HITTER_HISTORY_LOADING) {
      return pills + '<div class="mlbstats-empty">Loading the ' + esc(hitterSeason) + " season leaderboard&hellip;</div>";
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
      '<div class="mlbstats-note">' + gloss("HEM+", "hem_plus") + " is the skill read; the slash + volume"
      + " columns are context. Compare against how these bats actually hit forward.</div>");
    var table = rows.length
      ? '<div class="mlbstats-scroll">' + renderTable(rows, HITTER_HISTORY_COLS, sort) + "</div>"
      : '<div class="mlbstats-empty">No hitters match the current filters.</div>';
    return pills + cap + table;
  }

  function renderHitterTeams() {
    var rows = (hitterData && hitterData.teams) || [];
    rows = sortRows(rows, HITTER_TEAM_COLS, hitterTeamSort);
    if (!rows.length) return '<div class="mlbstats-empty">No team lineups to show yet.</div>';
    var note = '<div class="mlbstats-note">' + gloss("Offense+", "offense_plus") + ' weights each lineup by the '
      + gloss("HEM+", "hem_plus") + " of the plate appearances it takes (PA-weighted). Heart 3 reads the"
      + " top of the order; the volume columns are context.</div>";
    return proseFold("hitteam-about", rows.length + " lineups", note)
      + '<div class="mlbstats-scroll">' + renderTable(rows, HITTER_TEAM_COLS, hitterTeamSort) + "</div>";
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
      + ' distribution <span class="proj-dim">(qualified hitters; cyan = elite)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Skill vs volume'
        + ' <span class="proj-dim">(top-right = elite bats with the PAs to prove it)</span></div>' + sc + "</div>" : "")
      + (psc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Now vs next: HEM+ × ' + gloss("pWOBA", "pwoba")
        + ' <span class="proj-dim">(above the pack = projection believes; below = season outrunning it)</span></div>' + psc + "</div>" : "")
      + "</div>";
    return collapsible("hitters-viz", 'Distribution <span class="proj-dim">(HEM+ spread, skill vs volume, now vs next)</span>', body);
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
  function _slotRow(h, slotNum) {
    var adv = h.platoon_adv
      ? '<span class="bp-slot-adv" title="Platoon advantage vs this hand">●</span>' : "";
    var hand = h.bats ? '<span class="proj-dim"> ' + esc(h.bats) + "HB</span>" : "";
    return '<div class="bp-slot">'
      + '<span class="bp-slot-role">' + slotNum + "</span>"
      + '<span class="bp-slot-name"' + (h.name ? ' title="' + esc(h.name) + '"' : "") + ">" + esc(h.name || EM_DASH) + hand + adv
      + (h.pa != null ? '<span class="proj-dim"> ' + fInt(h.pa) + " PA</span>" : "") + "</span>"
      + '<span class="bp-slot-rem ' + hemClass(h.hem_plus) + '">' + fInt(h.hem_plus) + "</span>"
      + "</div>";
  }
  function lineupLadders() {
    var teams = (hitterData && hitterData.teams) || [];
    if (!teams.length) return "";
    var sorted = teams.slice().sort(function (a, b) { return (num(b.offense_plus) || 0) - (num(a.offense_plus) || 0); });
    var cards = sorted.map(function (t) {
      // Constructed handedness-aware order for the selected hand; fall back to the
      // HEM+ depth ladder when the bat side wasn't available.
      var order = (t.orders && t.orders[hitterSplit]) || null;
      var slots;
      if (order && order.length) {
        slots = order.map(function (h) { return _slotRow(h, h.slot); }).join("");
      } else {
        slots = (t.lineup || []).slice(0, 9).map(function (h, i) { return _slotRow(h, i + 1); }).join("");
      }
      // Bench bats, clearly separated below the nine.
      var bench = (t.bench || []);
      var benchHtml = bench.length
        ? '<div class="bp-bench-head">Bench</div>'
          + bench.map(function (h) {
              var hand = h.bats ? '<span class="proj-dim"> ' + esc(h.bats) + "HB</span>" : "";
              return '<div class="bp-slot bp-slot--bench">'
                + '<span class="bp-slot-role">&mdash;</span>'
                + '<span class="bp-slot-name"' + (h.name ? ' title="' + esc(h.name) + '"' : "") + ">" + esc(h.name || EM_DASH) + hand
                + (h.pa != null ? '<span class="proj-dim"> ' + fInt(h.pa) + " PA</span>" : "") + "</span>"
                + '<span class="bp-slot-rem ' + hemClass(h.hem_plus) + '">' + fInt(h.hem_plus) + "</span>"
                + "</div>";
            }).join("")
        : "";
      return '<div class="bp-depth-card"><div class="bp-depth-head">'
        + '<span class="bp-depth-team">' + logo(t.team) + esc(t.team) + "</span>"
        + '<span class="rem-plus ' + hemClass(t.offense_plus) + '" data-gl="offense_plus">Offense+ ' + fInt(t.offense_plus) + "</span>"
        + "</div>" + slots + benchHtml + "</div>";
    }).join("");
    return '<div class="mlbstats-note">A sabermetric batting order, not a HEM+ sort: the two best bats hit '
      + "2nd and 4th, and left/right hitters are staggered so a reliever can't get a platoon matchup. Toggle "
      + "the opposing hand to re-lens platoon advantage (" + "● marks a platoon-advantaged bat). Bench bats "
      + "are listed below each nine.</div>"
      + lineupSplitToggle()
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
        ? '<div class="mlbstats-empty mlbstats-load-error" role="alert">Data failed to load. Refresh to retry; '
          + 'if it persists the nightly build is mid-run. '
          + '<button type="button" class="chip" id="mlbstats-hitter-retry">Retry</button></div>'
        : '<div class="mlbstats-empty">Hitter Leaderboards are being computed from the MLB season. '
          + "Check back shortly.</div>";
      var retry = document.getElementById("mlbstats-hitter-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = '<div class="mlbstats-empty">Loading&hellip;</div>';
        loadHitters();
      });
      return;
    }
    var inner = (hitterView === "teams") ? renderHitterTeams()
      : (hitterView === "charts") ? renderHitterCharts() : renderHitterBoard();
    // No #mlbstats-banner div for this section; the freshness line leads the
    // section's own root.
    root.innerHTML = bannerHTML(hitterData) + hitterTabBar() + hitterControls() + inner;
    bindHitterEvents(root);
    wireGlossary(root);
  }

  function bindHitterEvents(root) {
    bindCollapse(root);
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
      var rows = (hitterSeason === "current")
        ? sortRows(filteredHitters(), HITTER_COLS, hitterSort)
        : sortRows(filteredHitterHistory(), HITTER_HISTORY_COLS, hitterHistorySort());
      EEPHUS_GFX.open(_mlbstatsBoardSpec("hitters", rows));
    });
    root.querySelectorAll("[data-hitterseason]").forEach(function (b) {
      b.addEventListener("click", function () {
        hitterSeason = b.getAttribute("data-hitterseason");
        if (hitterSeason !== "current") loadHitterHistory();
        writeHash();
        renderHitters();
      });
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
    root.innerHTML = bannerHTML(hitterData) + hitterTabBar() + hitterControls() + inner;
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
      title: "Win Probability Added (batter): total win probability the hitter's plate appearances swung his team's way.",
      cell: function (r) { return levSignedCell(r.wpa, 2, 0); } },
    { key: "pli", label: "pLI", term: "pli", num: true, desc: true,
      title: "Average Leverage Index faced (1.0 = neutral). How high-stakes his plate appearances were on average.",
      cell: function (r) { return r.pli == null ? EM_DASH : f2(r.pli); } },
    { key: "clutch", label: "Clutch", term: "clutch", num: true, desc: true,
      title: "WPA/pLI minus WPA/LI: how much more (or less) win probability he added in high-leverage spots than his own rate predicts. A timing read, not a skill.",
      cell: function (r) { return levSignedCell(r.clutch, 2, 0.5); } },
    { key: "wpa_li", label: "WPA/LI", term: "wpa_li", num: true, desc: true,
      title: "Context-neutral WPA: his win-probability production stripped of the leverage of the spots he happened to be in.",
      cell: function (r) { return levSignedCell(r.wpa_li, 2, 0); } },
    { key: "pa", label: "PA", fmt: fInt, num: true, title: "Plate appearances (context)" },
  ];

  var STARTER_LEV_COLS = [
    { key: "name", label: "Starter", term: null, sortable: true, kind: "name", asc: true },
    { key: "wpa", label: "WPA", term: "wpa", num: true, desc: true,
      title: "Win Probability Added (starter): total win probability his starts swung his team's way.",
      cell: function (r) { return levSignedCell(r.wpa, 2, 0); } },
    { key: "wpa_per_start", label: "WPA/start", num: true, desc: true,
      title: "WPA per game started -- his average per-outing win-probability impact.",
      cell: function (r) { return levSignedCell(r.wpa_per_start, 3, 0); } },
    { key: "wpa_li", label: "WPA/LI", term: "wpa_li", num: true, desc: true,
      title: "Context-neutral WPA: his production with the leverage of his spots removed.",
      cell: function (r) { return levSignedCell(r.wpa_li, 2, 0); } },
    { key: "starts", label: "GS", fmt: fInt, num: true, title: "Games started (context)" },
  ];

  function levCols() { return leverageView === "starters" ? STARTER_LEV_COLS : BAT_LEV_COLS; }
  function levSort() { return leverageView === "starters" ? leverageStarterSort : leverageBatSort; }

  function levExplainer() {
    return explainer("wpa", gloss("WPA", "wpa")
      + " (Win Probability Added) is a realized, in-the-moment impact tally: every play shifts each team's"
      + " win probability, and a batter is credited with his team's swing (the pitcher gets the mirror image)."
      + " " + gloss("pLI", "pli") + " is the average leverage of the spots he was in (1.0 = neutral), and "
      + gloss("Clutch", "clutch") + " asks whether his value clustered when it mattered (WPA/pLI minus WPA/LI)."
      + " These are descriptive outcome measures, self-computed from the MLB win-probability feed -- not a"
      + " projection.");
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
  function leverageSeasonPills() {
    var pills = [["current", "Current"]];
    leverageHistorySeasons().slice().sort(function (a, b) { return b - a; }).forEach(function (y) {
      pills.push([String(y), String(y)]);
    });
    if (pills.length < 2) return "";
    return '<div class="mlbstats-seasons" role="tablist" aria-label="Season">' + pills.map(function (p) {
      var sel = (p[0] === leverageSeason);
      return '<button type="button" class="mlbstats-season' + (sel ? " active" : "")
        + '" data-leverageseason="' + esc(p[0]) + '" role="tab" aria-selected="' + sel + '">' + esc(p[1]) + "</button>";
    }).join("") + "</div>";
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
        + ' <span class="proj-dim">(qualified starters)</span></div>' + hist + "</div>"
        + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Skill vs timing'
          + ' <span class="proj-dim">(above the line = value added in higher-leverage spots)</span></div>' + sc + "</div>" : "")
        + "</div>";
      return collapsible("leverage-viz", 'Charts <span class="proj-dim">(WPA distribution, skill vs timing)</span>', body);
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
      + ' distribution <span class="proj-dim">(qualified batters; cyan = high impact)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Production vs leverage'
        + ' <span class="proj-dim">(top-right = productive bats in high-leverage spots; green = clutch-positive, red = clutch-negative)</span></div>' + sc + "</div>" : "")
      + "</div>";
    return collapsible("leverage-viz", 'Charts <span class="proj-dim">(WPA distribution, production vs leverage)</span>', body);
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
    return '<div class="mlbstats-bar">'
      + '<label class="mlbstats-ctl">'
      + '<input type="checkbox" id="mlbstats-leverage-qual"' + (leverageQualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + teamSelect("mlbstats-leverage-team", leverageSourceRows(), leverageTeam)
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
      + (cov.games_total != null ? " / " + esc(cov.games_total) : "") + " games walked</span>";
  }

  function renderLeverageBoard() {
    // A past-season pill reads from the lazy-loaded history file; the inline
    // loading / error states mirror the reliever board so a failed fetch never
    // blanks the board.
    if (leverageSeason !== "current") {
      if (leverageHistoryErr) {
        return '<div class="mlbstats-empty mlbstats-load-error" role="alert">'
          + "Season history failed to load. Refresh to retry; if it persists the nightly build is mid-run. "
          + '<button type="button" class="chip" id="mlbstats-leverage-history-retry">Retry</button></div>';
      }
      if (!leverageHistory || leverageHistoryLoading) {
        if (!leverageHistory) loadLeverageHistory();
        return '<div class="mlbstats-empty">Loading the ' + esc(leverageSeason) + " season leaderboard&hellip;</div>";
      }
      if (!leverageHistory.history || !leverageHistory.history[leverageSeason]) {
        return '<div class="mlbstats-empty">No leaderboard for the ' + esc(leverageSeason) + " season.</div>";
      }
    }
    var cols = levCols(), sort = levSort();
    var rows = sortRows(filteredLeverage(), cols, sort);
    if (!rows.length) return '<div class="mlbstats-empty">No players match the current filters.</div>';
    var isStart = (leverageView === "starters");
    var seasonLbl = (leverageSeason === "current") ? "" : (esc(leverageSeason) + " season, ");
    var note = '<div class="mlbstats-note">'
      + gloss("WPA", "wpa") + " is realized in-game impact; " + gloss("pLI", "pli")
      + " and " + gloss("Clutch", "clutch") + " read the leverage of the spots. Descriptive outcome value, "
      + "not a forecast.</div>";
    // The coverage count rides the fold HEAD, not the folded body: the shell
    // banner suppresses its own copy here (noCoverage) because only this board
    // knows which season the pill is on, so folding it away would leave a phone
    // reader with no games-walked count at all.
    return proseFold("lev-about",
        seasonLbl + rows.length + (isStart ? " starters" : " batters") + leverageCoverage(),
        levExplainer() + note)
      + leverageViz() + '<div class="mlbstats-scroll">' + renderTable(rows, cols, sort) + "</div>";
  }

  function renderLeverage() {
    var root = document.getElementById("mlbstats-leverage-root");
    if (!root) return;
    if (!leverageData) {
      root.innerHTML = leverageErr
        ? '<div class="mlbstats-empty mlbstats-load-error" role="alert">Data failed to load. Refresh to retry; '
          + 'if it persists the nightly build is mid-run. '
          + '<button type="button" class="chip" id="mlbstats-leverage-retry">Retry</button></div>'
        : '<div class="mlbstats-empty">Leverage Leaderboards are being computed from the MLB win-probability '
          + "feed. Check back shortly.</div>";
      var retry = document.getElementById("mlbstats-leverage-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = '<div class="mlbstats-empty">Loading&hellip;</div>';
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
    root.innerHTML = bannerHTML(leverageData, { noCoverage: true })
      + leverageTabBar() + leverageSeasonPills() + leverageControls() + renderLeverageBoard();
    bindLeverageEvents(root);
    wireGlossary(root);
  }

  function renderLeverageInPlace(focusId) {
    var root = document.getElementById("mlbstats-leverage-root");
    if (!root) return;
    root.innerHTML = bannerHTML(leverageData, { noCoverage: true })
      + leverageTabBar() + leverageSeasonPills() + leverageControls() + renderLeverageBoard();
    restoreFocus(root, focusId || "mlbstats-leverage-q");
    bindLeverageEvents(root);
    wireGlossary(root);
  }

  function bindLeverageEvents(root) {
    bindCollapse(root);
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
      renderLeverageInPlace("mlbstats-leverage-team");
    });
    var levGfx = root.querySelector("#mlbstats-leverage-gfx");
    if (levGfx) levGfx.addEventListener("click", function () {
      if (!window.EEPHUS_GFX) return;
      EEPHUS_GFX.open(_mlbstatsBoardSpec("leverage", sortRows(filteredLeverage(), levCols(), levSort())));
    });
    root.querySelectorAll("[data-leverageseason]").forEach(function (b) {
      b.addEventListener("click", function () {
        leverageSeason = b.getAttribute("data-leverageseason");
        if (leverageSeason !== "current") loadLeverageHistory();
        writeHash();
        renderLeverage();
      });
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
  // Generate GFX: shared EEPHUS_GFX board specs, one builder for every board.
  // ---------------------------------------------------------------------------
  // Each board's control row carries a "Generate GFX" chip; the click handler
  // passes the view id plus the SAME filtered+sorted rows the table renders, so
  // the graphic always matches what's on screen (season pill, qualified-only,
  // search, and sort are all baked into `rows`). The module accent is gold; the
  // columns mirror each board's headline metric, with the trailing-window /
  // secondary columns marked wideOnly so the narrow (1080-wide) formats stay
  // legible. Titles auto-derive from the board; the subtitle carries the active
  // season/window selection. Mirrors fa.js / projections.js.
  // ===========================================================================
  function gfxChip(id) {
    return (window.EEPHUS_GFX && EEPHUS_GFX.chipHTML) ? EEPHUS_GFX.chipHTML(id, "Generate GFX") : "";
  }

  function _mlbstatsBoardSpec(view, rows) {
    rows = rows || [];
    // Season/window label for the subtitle: the live board reports the season +
    // as-of date; a past-season pill reports "<year> season". Count noun varies.
    function seasonBits(seasonSel, data, noun) {
      var s;
      if (seasonSel && seasonSel !== "current") {
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
          { t: fInt(r.rem_plus_3yr) },
          { t: fPct(r.k_bb_pct) },
          { t: f2(r.gmli) },
          { t: f2(r.era) },
          { t: f1(r.ip) },
        ] };
      });
      return spec("MLB Stats · REM+ Leaders",
        seasonBits(relSeason, DATA, "relievers"),
        "mlbstats-rem-leaders",
        "REM+ = FIP-based, sample-shrunk run-prevention skill - leverage rides separate columns",
        { defaultCount: 25, counts: [10, 25, 50], legend: "REM+ 100 = average reliever", columns: [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.33 },
          { label: "REM+", frac: 0.11 },
          { label: "REM+ 3yr", frac: 0.11, wideOnly: true },
          { label: "K-BB%", frac: 0.11 },
          { label: "gmLI", frac: 0.11, wideOnly: true },
          { label: "ERA", frac: 0.09, wideOnly: true },
          { label: "IP", frac: 0.09, wideOnly: true },
        ], rows: relRows });
    }

    if (view === "bullpens") {
      var bpRows = rows.map(function (t, i) {
        return { cells: [
          { t: i + 1 },
          { t: t.team || EM_DASH },
          { t: fInt(t.bullpen_plus), c: "accent" },
          { t: fInt(t.high_lev_core_rem) },
          { t: f1(t.relief_ip) },
        ] };
      });
      return spec("MLB Stats · Bullpen+ Leaders",
        seasonBits("current", DATA, "bullpens"),
        "mlbstats-bullpen-rankings",
        "Bullpen+ = relief-IP-weighted REM+ - the talent of the innings a pen actually uses",
        { defaultCount: 30, counts: [10, 30], legend: "Bullpen+ 100 = average bullpen", columns: [
          { label: "#", frac: 0.08 },
          { label: "Team", frac: 0.34 },
          { label: "Bullpen+", frac: 0.20 },
          { label: "Hi-Lev Core", frac: 0.19, wideOnly: true },
          { label: "Relief IP", frac: 0.19 },
        ], rows: bpRows });
    }

    if (view === "starters") {
      var spRows = rows.map(function (r, i) {
        return { cells: [
          { t: i + 1 },
          { t: r.name || EM_DASH, sub: r.team || undefined },
          { t: fInt(r.sem_plus), c: "accent" },
          { t: fInt(r.sem_plus_3yr) },
          { t: fPct(r.k_bb_pct) },
          { t: f2(r.era) },
          { t: f1(r.ip) },
          { t: fInt(r.gs) },
        ] };
      });
      return spec("MLB Stats · SEM+ Leaders",
        seasonBits(starterSeason, starterData, "starters"),
        "mlbstats-sem-leaders",
        "SEM+ = FIP-based, sample-shrunk starter run-prevention skill - durability kept separate",
        { defaultCount: 25, counts: [10, 25, 50], legend: "SEM+ 100 = average starter", columns: [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.33 },
          { label: "SEM+", frac: 0.12 },
          { label: "SEM+ 3yr", frac: 0.12, wideOnly: true },
          { label: "K-BB%", frac: 0.12 },
          { label: "ERA", frac: 0.09, wideOnly: true },
          { label: "IP", frac: 0.09, wideOnly: true },
          { label: "GS", frac: 0.08, wideOnly: true },
        ], rows: spRows });
    }

    if (view === "hitters") {
      var hitRows = rows.map(function (r, i) {
        return { cells: [
          { t: i + 1 },
          { t: r.name || EM_DASH, sub: r.team || undefined },
          { t: fInt(r.hem_plus), c: "accent" },
          { t: fInt(r.hem_plus_3yr) },
          { t: f3(r.woba) },
          { t: fInt(r.pa) },
          { t: f3(r.ops) },
        ] };
      });
      return spec("MLB Stats · HEM+ Leaders",
        seasonBits(hitterSeason, hitterData, "hitters"),
        "mlbstats-hem-leaders",
        "HEM+ = sample-shrunk wOBA on a league-relative scale - volume + slash kept separate",
        { defaultCount: 25, counts: [10, 25, 50], legend: "HEM+ 100 = average hitter", columns: [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.35 },
          { label: "HEM+", frac: 0.12 },
          { label: "HEM+ 3yr", frac: 0.12, wideOnly: true },
          { label: "wOBA", frac: 0.12 },
          { label: "PA", frac: 0.08, wideOnly: true },
          { label: "OPS", frac: 0.10, wideOnly: true },
        ], rows: hitRows });
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
        seasonBits(leverageSeason, leverageData, isStart ? "starters" : "batters"),
        "mlbstats-wpa-leaders",
        "WPA = realized in-game win-probability impact · Clutch reads timing, not skill",
        { defaultCount: 25, counts: [10, 25, 50],
          legend: "WPA = win probability added · + adds wins, − costs them",
          columns: levCols2, rows: levRows });
    }

    return null;
  }

  // ---- top-level section switching ------------------------------------------
  function showSection(name) {
    section = name;
    document.querySelectorAll("[data-mlbsection]").forEach(function (b) {
      var on = b.getAttribute("data-mlbsection") === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    var sects = { bullpen: "mlbstats-section-bullpen", starters: "mlbstats-section-starters",
                  hitters: "mlbstats-section-hitters", leverage: "mlbstats-section-leverage" };
    Object.keys(sects).forEach(function (k) {
      var el = document.getElementById(sects[k]);
      if (el) { if (k === name) el.removeAttribute("hidden"); else el.setAttribute("hidden", "hidden"); }
    });
    if (name === "starters") initStarters();
    else if (name === "hitters") initHitters();
    else if (name === "leverage") initLeverage();
  }
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
    bindSectionNav();
    load();
    // Honor a deep-linked non-default section (#section=starters|hitters).
    if (section !== "bullpen") showSection(section);
    // Preload the player-links map, then re-render the active section so the
    // leaderboard names upgrade from plain text to merged-card links.
    if (window.EEPHUS_HUB && EEPHUS_HUB.links) {
      EEPHUS_HUB.links().then(function (L) {
        LINKS = L || null;
        if (section === "starters") { if (starterInit) renderStarters(); }
        else if (section === "hitters") { if (typeof hitterInit !== "undefined" && hitterInit) renderHitters(); }
        else if (section === "leverage") { if (typeof leverageInit !== "undefined" && leverageInit) renderLeverage(); }
        else render();
      });
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
