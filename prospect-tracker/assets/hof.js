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
// SIX SECTIONS ARE LIVE AND TWO ARE DARK. The dark ones render a card that
// names their blocker and says nothing else. They are dark for data reasons,
// not modelling reasons:
//   deserved    a Hall-SIZED line needs the count of PLAYER inductions, and no
//               field in the source says what a plaque says
//   predictor   no merit model has passed its ship rule
//
// FRANCHISES WENT LIVE 2026-09-25 on the owner's frozen rule: every inductee
// credited to ONE franchise, the one with the most bWAR summed over his
// stints, through a franchise map carried back to 1871 with a defunct-club
// bucket. The rule, its date, what it rejected and every count are payload
// keys; the induction column keeps its three states there too.
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
  // THE BAND SWITCHER IS A REAL TABLIST (audit QCLA14). It carried
  // role=tablist over three plain buttons, so a screen reader met a tablist
  // with no tabs and the active band was a class only. Each button is a tab
  // with aria-selected and aria-controls on the one panel below, and the
  // arrow keys move between them.
  function renderBands() {
    var out = [], k;
    for (k in BANDS) {
      if (!Object.prototype.hasOwnProperty.call(BANDS, k)) continue;
      var n = (DATA[k] || []).length;
      var on = state.band === k;
      out.push('<button type="button" role="tab" id="hof-band-' + k + '" aria-controls="hof-band-panel"' +
        ' aria-selected="' + (on ? "true" : "false") + '" class="hof-bandbtn' +
        (on ? " active" : "") + '" data-band="' + k + '">' +
        esc(BANDS[k].label) + ' <span class="hof-bandn">' + n + "</span></button>");
    }
    return '<div class="hof-bands" role="tablist" aria-label="Bands">' + out.join("") + "</div>";
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

  function renderTable(rows) {
    var head = COLS.map(function (c) {
      var arrow = state.sort.key === c.key ? (state.sort.asc ? " ▲" : " ▼") : "";
      // scope=col and aria-sort, not role=button: the header had no sort
      // state for a screen reader at all (census X06-06).
      var aria = state.sort.key === c.key ? (state.sort.asc ? "ascending" : "descending") : "none";
      return '<th class="' + c.cls + '" data-sort="' + c.key + '" scope="col" tabindex="0" aria-sort="' + aria + '">' +
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
      (body || '<tr><td colspan="14">' + pxState("empty", "No players match.") + "</td></tr>") +
      "</tbody></table></div>" + more;
  }

  function countText(rows) {
    return rows.length + " players shown of " +
      (DATA[state.band] || []).length + " in this band.";
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

  // ---- franchises -------------------------------------------------------------
  // One row per current franchise plus the defunct bucket, then a closed list
  // per franchise. The clubs carry inductee ids; the rows live once, in
  // sections.franchises.inductees.
  function renderFranchises() {
    var f = DATA.sections.franchises;
    if (!f || !f.live) return renderDark("franchises", "Franchises");
    var byId = {};
    (f.inductees || []).forEach(function (r) { byId[r.id] = r; });
    var c = f.counts, dfn = f.defunct, gl = dfn.group_labels || {};
    var groups = Object.keys(dfn.by_group || {}).map(function (g) {
      return esc(dfn.by_group[g]) + " " + esc(gl[g] || g);
    }).join(", ");
    var units = f.clubs.slice();
    units.push({ code: dfn.key, name: dfn.label, n: dfn.n, n_player_bbwaa: dfn.n_player_bbwaa,
      n_route_unverified: dfn.n_route_unverified, n_played_for: null,
      inductees: dfn.inductees, defunct: true });
    units.sort(function (a, b) { return (b.n - a.n) || String(a.name).localeCompare(String(b.name)); });
    function topNames(u) {
      return u.inductees.slice(0, 3).map(function (id) {
        var r = byId[id];
        return r ? esc(r.name) + " " + num(r.primary_war) : "";
      }).join(", ");
    }
    var rows = units.map(function (u) {
      return "<tr" + (u.defunct ? ' class="hof-fr-defunct"' : "") + '><td class="hof-c-name">' + esc(u.name) + "</td>" +
        '<td class="hof-c-n">' + esc(u.n) + "</td>" +
        '<td class="hof-c-n">' + esc(u.n_player_bbwaa) + "</td>" +
        '<td class="hof-c-n">' + esc(u.n_route_unverified) + "</td>" +
        '<td class="hof-c-n">' + (u.n_played_for === null ? "" : esc(u.n_played_for)) + "</td>" +
        '<td class="hof-c-pos">' + topNames(u) + "</td></tr>";
    }).join("");
    var lists = units.filter(function (u) { return u.n > 0; }).map(function (u) {
      var body = u.inductees.map(function (id) {
        var r = byId[id];
        if (!r) return "";
        return '<tr><td class="hof-c-name">' + esc(r.name) + "</td>" +
          (u.defunct ? '<td class="hof-c-pos">' + esc(r.primary_label) + "</td>" : "") +
          '<td class="hof-c-n">' + num(r.primary_war) + "</td>" +
          '<td class="hof-c-n">' + esc(r.primary_seasons) + "</td>" +
          '<td class="hof-c-n">' + num(r.career_war) + "</td>" +
          '<td class="hof-c-ind">' + inductionCell(r) + "</td></tr>";
      }).join("");
      return '<details class="hof-fr"><summary>' + esc(u.name) + ' <span class="hof-bandn">' + esc(u.n) + "</span></summary>" +
        '<div class="hof-tablewrap mlbstats-scroll"><table class="hof-table hof-fr-table"><thead><tr>' +
        '<th class="hof-c-name">Inductee</th>' + (u.defunct ? '<th class="hof-c-pos">Club</th>' : "") +
        '<th class="hof-c-n">WAR with</th><th class="hof-c-n">Seasons with</th>' +
        '<th class="hof-c-n">Career WAR</th><th class="hof-c-ind">Induction</th>' +
        "</tr></thead><tbody>" + body + "</tbody></table></div></details>";
    }).join("");
    return '<section class="hof-block"><h2>Franchises</h2>' +
      '<p class="hof-note"><strong>' + esc(f.rule) + "</strong> Frozen " + esc(f.rule_frozen) +
      " (" + esc(f.doc) + ").</p>" +
      '<p class="hof-note">' + esc(c.n_credited) + " of " + esc(c.n_inductees) +
      " inductees with a playing record are credited: " + esc(c.n_to_a_current_franchise) +
      " to a current franchise and " + esc(c.n_to_a_defunct_club) + " to a defunct club (" + groups + "). " +
      esc(f.credit_basis) + "</p>" +
      '<div class="hof-tablewrap mlbstats-scroll"><table class="hof-table hof-fr-table"><thead><tr>' +
      '<th class="hof-c-name">Franchise</th><th class="hof-c-n">Credited</th>' +
      '<th class="hof-c-n">Writers, as players</th><th class="hof-c-n">Route unverified</th>' +
      '<th class="hof-c-n">Inductees who played for it</th><th class="hof-c-pos">Most WAR with the franchise</th>' +
      "</tr></thead><tbody>" + rows + "</tbody></table></div>" +
      "<h3>Inductees by franchise</h3>" + lists +
      '<p class="hof-note">' + esc(f.rejected) + "</p>" +
      '<p class="hof-count">The map: ' + esc(f.map_basis) + " " + esc(c.n_defunct_clubs_in_map) +
      " defunct clubs from " + esc(c.map_first_season) + "; " + esc(c.n_decided_by_tiebreak) +
      " credits decided by the tie-break.</p></section>";
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
      root.innerHTML = pxState("failed", esc(LOAD_ERROR));
      return;
    }
    if (!DATA) { root.innerHTML = pxState("loading", "Loading."); return; }
    if (state.section === "method") { root.innerHTML = renderMethod(); return; }
    if (state.section === "franchises") { root.innerHTML = renderFranchises(); return; }
    if (state.section === "blocked") {
      var fr = DATA.sections.franchises;
      root.innerHTML = renderBakeoff() +
        renderDark("deserved", "Deserved vs Inducted") +
        renderDark("predictor", "Induction predictor") +
        (fr && fr.live ? "" : renderDark("franchises", "Franchises"));
      return;
    }
    // THE BOARD PAINTS IN TWO LAYERS. The bands, the controls and the count
    // line are drawn once per band; a search, a filter, a sort or Show more
    // repaints only the table slot. So the search box keeps its focus without
    // a re-focus trick, and the count line is one persistent role=status node
    // whose text changes, which is what a screen reader announces (a live
    // region rebuilt on every keystroke is never read).
    root.innerHTML = renderBands() +
      '<div id="hof-band-panel" role="tabpanel" aria-labelledby="hof-band-' + state.band + '">' +
      renderBandNote() + renderControls() + '<div id="hof-table-slot"></div>' +
      '<p class="hof-count" id="hof-count" role="status"></p>' +
      renderLadder() + "</div>";
    wire();
    renderRows();
  }

  // Repaint the table slot and the count. `refocus` is a selector inside the
  // slot that takes focus afterwards: the header just sorted, or Show more.
  // Without it a keyboard sort dropped focus on <body> (audit QCLA14).
  function renderRows(refocus) {
    var slot = el("hof-table-slot");
    if (!slot) return;
    var rows = sorted(filtered());
    slot.innerHTML = renderTable(rows);
    var c = el("hof-count");
    if (c) c.textContent = countText(rows);
    wireTable();
    if (refocus) {
      var t = slot.querySelector(refocus) ||
        slot.querySelector('th[data-sort="' + state.sort.key + '"]');
      if (t) t.focus();
    }
  }

  function setBand(k) {
    state.band = k; state.shown = PAGE; state.pos = "ALL"; render();
    var b = el("hof-band-" + k);
    if (b) b.focus();
  }

  function wire() {
    var q = el("hof-q");
    if (q) q.addEventListener("input", function () {
      state.query = this.value; state.shown = PAGE; renderRows();
    });
    var p = el("hof-pos");
    if (p) p.addEventListener("change", function () { state.pos = this.value; state.shown = PAGE; renderRows(); });
    var i = el("hof-ind");
    if (i) i.addEventListener("change", function () { state.induction = this.value; state.shown = PAGE; renderRows(); });
    var keys = Object.keys(BANDS);
    Array.prototype.forEach.call(document.querySelectorAll(".hof-bandbtn"), function (b) {
      b.addEventListener("click", function () { setBand(this.getAttribute("data-band")); });
      b.addEventListener("keydown", function (e) {
        var at = keys.indexOf(this.getAttribute("data-band")), to = -1;
        if (e.key === "ArrowRight") to = (at + 1) % keys.length;
        else if (e.key === "ArrowLeft") to = (at + keys.length - 1) % keys.length;
        else if (e.key === "Home") to = 0;
        else if (e.key === "End") to = keys.length - 1;
        if (to < 0) return;
        e.preventDefault();
        setBand(keys[to]);
      });
    });
  }

  function wireTable() {
    var m = el("hof-more");
    if (m) m.addEventListener("click", function () { state.shown += PAGE; renderRows("#hof-more"); });
    Array.prototype.forEach.call(document.querySelectorAll("#hof-table-slot th[data-sort]"), function (th) {
      function go() {
        var k = th.getAttribute("data-sort");
        if (state.sort.key === k) state.sort.asc = !state.sort.asc;
        else state.sort = { key: k, asc: k === "name" || k === "pos" };
        renderRows('th[data-sort="' + k + '"]');
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
    // The lamp loader goes up before the fetch: with DATA still null, render()
    // paints its loading kind and the board replaces it when the fetch settles.
    render();
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
