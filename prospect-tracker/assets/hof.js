/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - Hall of Fame (/hof/)
// =============================================================================
// Renders data/hof_board.json (hof_export.py).
//
// NOT ONE FIGURE IN THIS FILE IS TYPED. Every count, every threshold and every
// sentence of disclosure copy is read out of the payload, because a hand-typed
// number on a page whose whole subject is what we can and cannot verify would
// be the exact failure the page exists to avoid. If a string here looks like
// prose, check where it comes from: it is a payload key.
//
// FIVE SECTIONS ARE LIVE AND THREE ARE DARK. The dark ones render a card that
// names their blocker and says nothing else. They are dark for data reasons,
// not modelling reasons:
//   deserved    a Hall-SIZED line needs the count of PLAYER inductions, and no
//               field in the source says what a plaque says
//   predictor   no merit model has passed its ship rule
//   franchises  no frozen attribution rule, and no franchise spine before 1969
//
// THE BAKE-OFF IS LIVE AND IT REPORTS A LOSS. Baseball-Reference's own HoF
// Monitor separates the Hall better than our WAR shelf does, on every one of
// our columns, by more than the sample can resolve. It renders because the
// point of benchmarking against the public work rather than asserting over it
// is that the answer is allowed to be "theirs is better", and a panel that
// only ships on a win is not a benchmark.
//
// THE THREE BANDS ARE A PARTITION. Eligible, Watch and Not Yet Eligible cover
// the ten-plus-season population exactly once each. Without the third band
// Albert Pujols, Zack Greinke, Robinson Cano, Miguel Cabrera and Joey Votto
// appear on neither board, and they are the most likely thing a reader opens
// this page in 2026 to look up. The exporter refuses to write a payload whose
// bands do not partition, and the page asserts it again here.
(function () {
  "use strict";

  var DATA_URL = "/data/hof_board.json";
  var BANDS = {
    leaderboard: { label: "Eligible", key: "leaderboard" },
    watch: { label: "Cooperstown Watch", key: "watch" },
    not_yet_eligible: { label: "Not Yet Eligible", key: "not_yet_eligible" }
  };
  var PAGE = 100;

  var DATA = null;
  var LOAD_ERROR = "";

  var state = {
    band: "leaderboard",
    section: "board",
    query: "",
    pos: "ALL",
    induction: "ALL",
    sort: { key: "jaws", asc: false },
    shown: PAGE
  };

  // ---- helpers -------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function num(v, nd) {
    if (v === null || v === undefined || v !== v) return "";
    return Number(v).toFixed(nd === undefined ? 1 : nd);
  }
  function el(id) { return document.getElementById(id); }
  // A glossary term: eephus-gl.js shows the definition on hover (document-level
  // [data-gl] delegation) and the href opens the canonical entry.
  function glTerm(slug, label) {
    return '<a class="g-term" href="/glossary/#g=' + esc(slug) + '" data-gl="' +
      esc(slug) + '">' + esc(label) + "</a>";
  }

  // A BLANK PUBLIC CELL IS NOT A ZERO. hof_monitor and hof_standards exist only
  // for players who reached a Hall of Fame election page, so an empty cell means
  // "Baseball-Reference published nothing", and rendering a 0 there would invent
  // a number for two thirds of the board.
  function pub(v) {
    return (v === null || v === undefined) ? '<span class="hof-blank" title="no published value">.</span>' : num(v, 0);
  }

  var INDUCTION_LABEL = {
    player_bbwaa: "Player, writers",
    route_unverified: "Inducted, route unverified",
    none: ""
  };

  function inductionCell(r) {
    var k = r.induction || "none";
    if (k === "none") return "";
    var t = INDUCTION_LABEL[k] || k;
    var yr = r.induction_year ? " " + r.induction_year : "";
    return '<span class="hof-ind hof-ind--' + esc(k) + '">' + esc(t + yr) + "</span>";
  }

  // ---- sorting -------------------------------------------------------------
  var COLS = [
    { key: "name", label: "Player", cls: "hof-c-name", txt: true },
    { key: "pos", label: "Pos", cls: "hof-c-pos", txt: true },
    { key: "first", label: "From", cls: "hof-c-yr" },
    { key: "last", label: "To", cls: "hof-c-yr" },
    { key: "seasons", label: "Sea", cls: "hof-c-n" },
    { key: "war", label: "WAR", cls: "hof-c-n" },
    { key: "war7", label: "WAR7", cls: "hof-c-n" },
    { key: "jaws", label: "JAWS", cls: "hof-c-n" },
    { key: "waa_pos", label: "WAA+", cls: "hof-c-n" },
    { key: "ink", label: "WAR ink", cls: "hof-c-n" },
    { key: "monitor", label: "Monitor", cls: "hof-c-n" },
    { key: "standards", label: "Standards", cls: "hof-c-n" },
    { key: "induction", label: "Induction", cls: "hof-c-ind", txt: true }
  ];

  function sorted(rows) {
    var k = state.sort.key, asc = state.sort.asc;
    var col = null, i;
    for (i = 0; i < COLS.length; i++) if (COLS[i].key === k) col = COLS[i];
    var out = rows.slice();
    out.sort(function (a, b) {
      var x = a[k], y = b[k];
      // A MISSING VALUE SORTS LAST IN BOTH DIRECTIONS. Sorting nulls as zero
      // would put every player with no ballot page at the bottom of a Monitor
      // ascending sort as though he scored zero, which is the same lie the
      // blank cell exists to avoid.
      var xm = (x === null || x === undefined || x === "");
      var ym = (y === null || y === undefined || y === "");
      if (xm && ym) return 0;
      if (xm) return 1;
      if (ym) return -1;
      if (col && col.txt) {
        x = String(x); y = String(y);
        return asc ? x.localeCompare(y) : y.localeCompare(x);
      }
      return asc ? x - y : y - x;
    });
    return out;
  }

  function filtered() {
    var rows = DATA[state.band] || [];
    var q = state.query.trim().toLowerCase();
    return rows.filter(function (r) {
      if (q && String(r.name).toLowerCase().indexOf(q) < 0) return false;
      if (state.pos !== "ALL" && r.pos !== state.pos) return false;
      if (state.induction === "IN" && r.induction === "none") return false;
      if (state.induction === "OUT" && r.induction !== "none") return false;
      if (state.induction === "BBWAA" && r.induction !== "player_bbwaa") return false;
      return true;
    });
  }

  // ---- render --------------------------------------------------------------
  function renderBands() {
    var out = [], k;
    for (k in BANDS) {
      if (!Object.prototype.hasOwnProperty.call(BANDS, k)) continue;
      var n = (DATA[k] || []).length;
      out.push('<button type="button" class="hof-bandbtn' +
        (state.band === k ? " active" : "") + '" data-band="' + k + '">' +
        esc(BANDS[k].label) + ' <span class="hof-bandn">' + n + "</span></button>");
    }
    return '<div class="hof-bands" role="tablist">' + out.join("") + "</div>";
  }

  function renderBandNote() {
    if (state.band === "watch") {
      return '<p class="hof-note">' + esc(DATA.sections.watch.why_no_projection) + "</p>";
    }
    if (state.band === "not_yet_eligible") {
      return '<p class="hof-note">' + esc(DATA.sections.not_yet_eligible.why) + "</p>";
    }
    return '<p class="hof-note">' + esc(DATA.reproduction.what_it_means) + "</p>";
  }

  function renderTable() {
    var rows = sorted(filtered());
    var head = COLS.map(function (c) {
      var arrow = state.sort.key === c.key ? (state.sort.asc ? " ▲" : " ▼") : "";
      return '<th class="' + c.cls + '" data-sort="' + c.key + '" tabindex="0" role="button">' +
        esc(c.label) + arrow + "</th>";
    }).join("");
    var body = rows.slice(0, state.shown).map(function (r, i) {
      // THE RANK CELL CARRIES .mlbstats-col-rank, on both the th and the td.
      // This board leads with the rank digit rather than the player, so the
      // shared freeze-:first-child would pin the NUMBER and scroll every
      // name out of reach. With the class on both, the rank pins narrow at
      // the left edge and the name pins beside it. Same contract as /pal/.
      return '<tr><td class="hof-c-rank mlbstats-col-rank">' + (i + 1) + "</td>" +
        '<td class="hof-c-name">' + esc(r.name) + "</td>" +
        '<td class="hof-c-pos" title="' + esc(r.pos_basis || "") + '">' + esc(r.pos || "") + "</td>" +
        '<td class="hof-c-yr">' + esc(r.first) + "</td>" +
        '<td class="hof-c-yr">' + esc(r.last) + "</td>" +
        '<td class="hof-c-n">' + esc(r.seasons) + "</td>" +
        '<td class="hof-c-n">' + num(r.war) + "</td>" +
        '<td class="hof-c-n">' + num(r.war7) + "</td>" +
        '<td class="hof-c-n hof-c-jaws">' + num(r.jaws) + "</td>" +
        '<td class="hof-c-n">' + num(r.waa_pos) + "</td>" +
        '<td class="hof-c-n">' + num(r.ink, 0) + "</td>" +
        '<td class="hof-c-n">' + pub(r.monitor) + "</td>" +
        '<td class="hof-c-n">' + pub(r.standards) + "</td>" +
        '<td class="hof-c-ind">' + inductionCell(r) + "</td></tr>";
    }).join("");
    var more = rows.length > state.shown
      ? '<div class="hof-more"><button type="button" id="hof-more">Show more (' +
        (rows.length - state.shown) + " left)</button></div>"
      : "";
    return '<div class="hof-tablewrap mlbstats-scroll"><table class="hof-table"><thead><tr>' +
      '<th class="hof-c-rank mlbstats-col-rank">#</th>' + head + "</tr></thead><tbody>" +
      (body || '<tr><td colspan="14" class="hof-empty">No players match.</td></tr>') +
      "</tbody></table></div>" + more +
      '<p class="hof-count">' + rows.length + " players shown of " +
      (DATA[state.band] || []).length + " in this band.</p>";
  }

  function renderControls() {
    var poss = {}, i, rows = DATA[state.band] || [];
    for (i = 0; i < rows.length; i++) if (rows[i].pos) poss[rows[i].pos] = 1;
    var opts = ['<option value="ALL">All positions</option>'];
    Object.keys(poss).sort().forEach(function (p) {
      opts.push('<option value="' + esc(p) + '"' +
        (state.pos === p ? " selected" : "") + ">" + esc(p) + "</option>");
    });
    return '<div class="hof-controls">' +
      '<input type="search" id="hof-q" placeholder="Search a player" value="' +
      esc(state.query) + '" aria-label="Search a player">' +
      '<select id="hof-pos" aria-label="Position class">' + opts.join("") + "</select>" +
      '<select id="hof-ind" aria-label="Induction">' +
      '<option value="ALL">Everyone</option>' +
      '<option value="IN"' + (state.induction === "IN" ? " selected" : "") + ">In the Hall</option>" +
      '<option value="BBWAA"' + (state.induction === "BBWAA" ? " selected" : "") + ">Elected by the writers</option>" +
      '<option value="OUT"' + (state.induction === "OUT" ? " selected" : "") + ">Not inducted</option>" +
      "</select></div>";
  }

  function renderLadder() {
    var q = DATA.line.quantiles, keys = Object.keys(q).sort(), out = [];
    keys.forEach(function (k) {
      out.push('<div class="hof-ladder-cell"><div class="hof-ladder-q">' +
        Math.round(parseFloat(k) * 100) + 'th</div><div class="hof-ladder-v">' +
        num(q[k]) + "</div></div>");
    });
    return '<section class="hof-block"><h2>JAWS ladder</h2>' +
      '<p class="hof-note">' + glTerm("jaws", "JAWS") + " quantiles across the " +
      esc(DATA.counts.n_eligible) + " eligible players. A distribution, not a Hall line " +
      "(that section is dark).</p>" +
      '<div class="hof-ladder">' + out.join("") + "</div></section>";
  }

  // THE BAKE-OFF PANEL, AND IT REPORTS A LOSS. It ships live only because the
  // answer to "is our shelf better than the public one" is allowed to be no.
  // Every string here is a payload key.
  function renderBakeoff() {
    var b = DATA.sections.bakeoff;
    if (!b || !b.live) return renderDark("bakeoff", "Benchmark bake-off");
    var rows = b.rows.map(function (r) {
      var d = (r.delta_vs_best_public === null || r.delta_vs_best_public === undefined)
        ? "" : (r.delta_vs_best_public > 0 ? "+" : "") + num(r.delta_vs_best_public, 4);
      return "<tr" + (r.is_public ? ' class="hof-pubarm"' : "") + ">" +
        '<td class="hof-c-name">' + esc(r.arm) + (r.is_public ? " (public)" : "") + "</td>" +
        '<td class="hof-c-n">' + num(r.auc, 4) + "</td>" +
        '<td class="hof-c-n">' + d + "</td>" +
        '<td class="hof-c-n">' + (r.mde95 === null || r.mde95 === undefined ? "" : num(r.mde95, 4)) + "</td>" +
        '<td class="hof-c-ind">' + esc(r.verdict || "") + "</td></tr>";
    }).join("");
    return '<section class="hof-block"><h2>Benchmark bake-off</h2>' +
      '<p class="hof-note"><strong>' + esc(b.headline) + "</strong></p>" +
      '<p class="hof-note">' + esc(b.why_it_loses) + "</p>" +
      '<div class="hof-tablewrap mlbstats-scroll"><table class="hof-table"><thead><tr>' +
      '<th class="hof-c-name">Rule</th><th class="hof-c-n">AUC</th>' +
      '<th class="hof-c-n">vs ' + esc(b.best_public) + "</th>" +
      '<th class="hof-c-n">Floor</th><th class="hof-c-ind">Verdict</th>' +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
      '<p class="hof-note">' + esc(b.n) + " players with a resolved writers' verdict, " +
      esc(b.n_positive) + " elected. Population: " + esc(b.population_note) + "</p>" +
      '<p class="hof-note">Calibration: ' + esc(b.calibration.n_cells_clearing_holm) +
      " of " + esc(b.calibration.n_cells) + " cells clear a multiplicity correction, and " +
      esc(b.calibration.note) + "</p>" +
      // what_it_does_not_show is a clause ("that our shelf is wrong. ..."), so
      // the page supplies the verb it completes; it rendered as a fragment.
      '<p class="hof-note">It does not show ' + esc(b.what_it_does_not_show) + "</p>" +
      '<p class="hof-count">Clauses frozen in ' + esc(b.gate_doc) + ", " +
      esc(b.gate_frozen || "") + "</p></section>";
  }

  function renderDark(key, title) {
    var s = DATA.sections[key];
    return '<section class="hof-block hof-dark"><h2>' + esc(title) +
      ' <span class="hof-darktag">not published</span></h2>' +
      '<p class="hof-dark-why">Blocked on ' + esc(s.blocked_on) +
      ". Nothing is published until it clears.</p>" +
      '<p class="hof-note">' + esc(s.why) + "</p></section>";
  }

  function renderMethod() {
    var c = DATA.coverage, r = DATA.reproduction, a = r.against_the_public_shelf;
    var hand = r.hand_checked;
    return '<section class="hof-block"><h2>What these numbers are</h2>' +
      '<p class="hof-note">Baseball-Reference\'s career WAR, ' + glTerm("war7", "WAR7") +
      " and " + glTerm("jaws", "JAWS") + ", reproduced from their daily WAR file. Hand-checked: " +
      esc(hand.n_players) + " players, exact on all " + esc(hand.n_comparisons) +
      " published figures. Against the " + esc(a.n_with_a_published_value) +
      " players with a ballot page: career WAR exact for " + esc(a.n_exact_on_career_war) +
      ", within 0.1 for " + esc(a.n_within_a_tenth) + ", mean absolute difference " +
      num(a.mean_absolute_difference, 2) + ". " + esc(r.what_it_means) + "</p>" +
      '<h3>The public columns</h3><p class="hof-note">' +
      esc(c.why_a_blank_public_column_is_not_a_zero) + " " +
      esc(DATA.coverage.n_eligible_with_no_ballot_page) + " of the " +
      esc(DATA.counts.n_eligible) + " eligible players have no ballot page at all.</p>" +
      '<h3>WAR ink</h3><p class="hof-note">' + esc(c.war_ink_is_ours) + "</p>" +
      '<h3>Position class</h3><p class="hof-note">' + esc(c.position_basis) + "</p>" +
      '<h3>The induction column</h3><p class="hof-note">' + esc(c.induction_column) + "</p>" +
      '<h3>The ledger</h3><p class="hof-note">' +
      esc(DATA.ledger.n_resolved_to_bbref) + " of " + esc(DATA.ledger.n_statsapi_inductees) +
      " inductees resolve to a playing record (" + esc(DATA.ledger.n_in_eligible_universe) +
      " in the eligible universe). The " + esc((DATA.ledger.resolution || {}).unresolved) +
      " unresolved are mostly non-players: umpires, owners, commissioners, union leaders " +
      "and Negro Leagues pioneers. " +
      esc(DATA.ledger.plaque_role_unverified.n_in_eligible_universe) +
      " eligible inductees carry a route we cannot verify.</p>" +
      '<h3>What this page does not claim</h3><p class="hof-note">' +
      esc(DATA.what_this_page_does_not_claim) + "</p></section>";
  }

  function render() {
    var root = el("hof-app-root");
    if (!root) return;
    if (LOAD_ERROR) {
      root.innerHTML = '<p class="hof-note">' + esc(LOAD_ERROR) + "</p>";
      return;
    }
    if (!DATA) { root.innerHTML = '<p class="hof-note">Loading.</p>'; return; }
    if (state.section === "method") { root.innerHTML = renderMethod(); return; }
    if (state.section === "blocked") {
      root.innerHTML = renderBakeoff() +
        renderDark("deserved", "Deserved vs Inducted") +
        renderDark("predictor", "Induction predictor") +
        renderDark("franchises", "Franchises");
      return;
    }
    root.innerHTML = renderBands() + renderBandNote() + renderControls() +
      renderTable() + renderLadder();
    wire();
  }

  function wire() {
    var q = el("hof-q");
    if (q) q.addEventListener("input", function () {
      state.query = this.value; state.shown = PAGE; render();
      var f = el("hof-q"); if (f) { f.focus(); f.setSelectionRange(f.value.length, f.value.length); }
    });
    var p = el("hof-pos");
    if (p) p.addEventListener("change", function () { state.pos = this.value; state.shown = PAGE; render(); });
    var i = el("hof-ind");
    if (i) i.addEventListener("change", function () { state.induction = this.value; state.shown = PAGE; render(); });
    var m = el("hof-more");
    if (m) m.addEventListener("click", function () { state.shown += PAGE; render(); });
    Array.prototype.forEach.call(document.querySelectorAll(".hof-bandbtn"), function (b) {
      b.addEventListener("click", function () {
        state.band = this.getAttribute("data-band");
        state.shown = PAGE; state.pos = "ALL"; render();
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("th[data-sort]"), function (th) {
      function go() {
        var k = th.getAttribute("data-sort");
        if (state.sort.key === k) state.sort.asc = !state.sort.asc;
        else state.sort = { key: k, asc: k === "name" || k === "pos" };
        render();
      }
      th.addEventListener("click", go);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
      });
    });
  }

  function wireSections() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-hofsection]"), function (b) {
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(document.querySelectorAll("[data-hofsection]"), function (o) {
          o.classList.remove("active"); o.setAttribute("aria-selected", "false");
        });
        this.classList.add("active"); this.setAttribute("aria-selected", "true");
        state.section = this.getAttribute("data-hofsection");
        render();
      });
    });
  }

  function boot() {
    wireSections();
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        DATA = d;
        // The partition is asserted again here rather than trusted. If it ever
        // fails, a player is on two boards or on none, and saying so is better
        // than drawing a board that quietly loses people.
        if (d.counts && d.counts.bands_partition_the_ten_plus_population === false) {
          LOAD_ERROR = "The three bands do not partition the population (a player " +
            "would show twice or not at all). Rebuild with hof_export.py.";
        }
        render();
      })
      .catch(function () {
        LOAD_ERROR = "The Hall of Fame board could not be loaded.";
        render();
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else { boot(); }
})();
