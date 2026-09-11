/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - In-Game Management (/management/)
// =============================================================================
// Renders data/management_board.json (mgmt_export.py).
//
// THERE IS NO PLUS METRIC ON THIS PAGE AND THAT IS THE POINT. The gate battery
// was frozen before it ran, it came back a bounded null, and its verdict set
// this page's scope: a club's decision value in the running game does not
// repeat between halves of its own season, so no club may be ranked by it.
//
// What ships instead is the thing the null makes sayable:
//   the league steals second at almost exactly its own break-even
//   steals of third pay, steals of home do not
//   the entire running game is worth a fraction of a win to the league
//   and no club is repeatably better at deciding
// The sacrifice bunt, the second family, renders from sections.sacrifice_bunt.
//
// NOT ONE FIGURE IN THIS FILE IS TYPED. Every number and every sentence comes
// out of the payload. The one thing this file decides for itself is COLOUR, and
// only on the sign of a published number.
(function () {
  "use strict";

  var DATA_URL = "/data/management_board.json";
  var DATA = null;
  var LOAD_ERROR = "";
  var state = { section: "running", season: "ALL", sort: { key: "attempts", asc: false } };

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function num(v, nd) {
    if (v === null || v === undefined || v !== v) return "";
    return Number(v).toFixed(nd === undefined ? 2 : nd);
  }
  function pct(v, nd) {
    if (v === null || v === undefined || v !== v) return "";
    return (Number(v) * 100).toFixed(nd === undefined ? 1 : nd) + "%";
  }
  function signed(v, nd) {
    if (v === null || v === undefined || v !== v) return "";
    return (v > 0 ? "+" : "") + Number(v).toFixed(nd === undefined ? 2 : nd);
  }
  function el(id) { return document.getElementById(id); }
  // A glossary hook. Ids the glossary does not carry yet resolve to nothing,
  // so an unmatched hook is inert rather than broken.
  function gl(label, id) {
    return '<span class="g-term" data-gl="' + esc(id) + '">' + esc(label) + "</span>";
  }

  // ---- the running game ----------------------------------------------------
  function renderRunning() {
    var h = DATA.headline, r = DATA.running_game, bt = r.by_target;
    var order = ["2B", "3B", "HOME"];
    var label = { "2B": "Stealing second", "3B": "Stealing third", HOME: "Stealing home" };
    var cards = order.map(function (k) {
      var t = bt[k];
      if (!t) return "";
      var good = t.sum_dv_wins > 0;
      return '<div class="mgmt-card">' +
        '<div class="mgmt-card-title">' + esc(label[k]) + "</div>" +
        '<div class="mgmt-card-big ' + (good ? "mgmt-pos" : "mgmt-neg") + '">' +
        signed(t.sum_dv_wins) + " wins</div>" +
        '<div class="mgmt-card-sub">' + esc(t.n) + " attempts</div>" +
        '<table class="mgmt-mini">' +
        "<tr><td>Success rate</td><td>" + pct(t.success_rate) + "</td></tr>" +
        "<tr><td>" + gl("Break-even", "steal_break_even") + " (swing-weighted)</td><td>" +
        pct(t.swing_weighted_breakeven_p) + "</td></tr>" +
        "<tr><td>Below their own break-even</td><td>" +
        pct(t.share_of_attempts_below_their_own_breakeven) + "</td></tr>" +
        "</table></div>";
    }).join("");

    var seasons = Object.keys(r.by_season).sort();
    var srows = seasons.map(function (y) {
      var s = r.by_season[y];
      return "<tr><td>" + esc(y) + "</td><td>" + esc(s.n) + "</td><td>" +
        pct(s.success_rate) + "</td><td>" + signed(s.sum_dv_wins) + "</td></tr>";
    }).join("");

    var ex = r.excluded, exrows = Object.keys(ex).map(function (k) {
      return "<tr><td>" + esc(k.replace(/_/g, " ")) + "</td><td>" + esc(ex[k]) + "</td></tr>";
    }).join("");

    // Copy is labels plus the payload's own sentences (owner copy rule,
    // 2026-09-11). The swing-weighted break-even explainer and the third-out
    // note are not drawn: the first belongs to the steal_break_even glossary
    // entry, and the second describes two-out attempts, which are excluded.
    return '<section class="mgmt-block">' +
      '<p class="mgmt-lede">' + esc(h.sentence) + "</p>" +
      '<div class="mgmt-cards">' + cards + "</div>" +
      '<p class="mgmt-note">' + esc(h.games) + " games: net " +
      signed(h.net_dv_all_seasons_wins) + " wins to the league; " +
      num(h.redistributable_pool_abs_dv_wins) + " wins move between clubs in absolute value.</p>" +
      "<h3>By season</h3>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr>' +
      "<th>Season</th><th>Attempts</th><th>Success</th><th>Decision value</th>" +
      "</tr></thead><tbody>" + srows + "</tbody></table></div>" +
      "<h3>" + gl("Decision value", "decision_value") + "</h3>" +
      '<p class="mgmt-note"><b>DV</b>: ' + esc(r.decomposition.dv) + " <b>ER</b>: " +
      esc(r.decomposition.er) + " " + esc(r.decomposition.identity) + ".</p>" +
      '<p class="mgmt-note"><b>League-average runner</b>: ' + esc(r.why_the_league_average_runner) + "</p>" +
      "<h3>Excluded</h3>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><tbody>' + exrows +
      "</tbody></table></div>" +
      // The census sentence says the table closes against the corpus (audit
      // F02-01). It is derived in mgmt_export._census_sentence; absent on a
      // payload that predates the census, and then nothing is drawn.
      (r.attempt_census_sentence
        ? '<p class="mgmt-note">' + esc(r.attempt_census_sentence) + "</p>" : "") +
      '<p class="mgmt-note"><b>Two-out attempts</b>: ' + esc(r.why_two_out_attempts_are_excluded) +
      "</p></section>" + (hasTab("bunt") ? "" : renderBunt());
  }

  // ---- the sacrifice bunt --------------------------------------------------
  // The second decision family (mgmt_bunt.py), live in the payload since
  // 2026-09-07 and never drawn until now. It rides under the running game
  // until the page shell carries a tab of its own for it.
  function hasTab(name) {
    try { return !!document.querySelector('[data-mgmtsection="' + name + '"]'); }
    catch (e) { return false; }
  }
  function renderBunt() {
    var b = (DATA.sections || {}).sacrifice_bunt;
    if (!b || !b.live) return "";
    var rows = (b.cells || []).map(function (c) {
      return "<tr><td>" + esc(c.bases) + "</td><td>" + esc(c.outs) + "</td><td>" +
        esc(c.n_bunt) + '</td><td class="' + (c.dv_per_bunt > 0 ? "mgmt-pos" : "mgmt-neg") + '">' +
        signed(c.dv_per_bunt, 4) + "</td><td>" + signed(c.dv_total, 1) + "</td></tr>";
    }).join("");
    var ic = b.independent_control || {};
    return '<section class="mgmt-block"><h2>The sacrifice bunt</h2>' +
      '<p class="mgmt-lede">' + esc(b.sentence) + "</p>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr>' +
      "<th>Bases</th><th>Outs</th><th>Bunts</th><th>" + gl("DV", "decision_value") +
      " per bunt</th><th>DV total</th></tr></thead><tbody>" + rows + "</tbody></table></div>" +
      (ic.total_wins != null
        ? '<p class="mgmt-note"><b>Control</b> (StatsAPI realized WPA, same bunts): ' +
          signed(ic.total_wins, 1) + " wins; " + esc(ic.why_it_is_not_the_metric) + "</p>" : "") +
      (b.the_selection_problem
        ? '<p class="mgmt-note"><b>Selection</b>: ' + esc(b.the_selection_problem) + "</p>" : "") +
      (b.two_outs_excluded ? '<p class="mgmt-note">' + esc(b.two_outs_excluded) + "</p>" : "") +
      "</section>";
  }

  // ---- the gate ------------------------------------------------------------
  // THE RAW SPLIT-HALF, FROM THE NUMBERS. The payload's
  // why_the_raw_number_is_not_the_finding quotes its figures inside the
  // sentence, and on the 2026-09-11 build they are the pre-repair ones, which
  // disagree with the gate block printed in the table directly above it. So
  // the line is built from the gate block's own fields plus the payload's
  // why_season_controlled, and that sentence is drawn only by a payload that
  // predates raw_split_half_r_for_comparison.
  function rawSplitHalf(g) {
    if (g.raw_split_half_r_for_comparison == null || !g.why_season_controlled) {
      return '<p class="mgmt-note">' + esc(g.why_the_raw_number_is_not_the_finding) + "</p>";
    }
    return '<p class="mgmt-note">Raw ' + num(g.raw_split_half_r_for_comparison, 4) +
      " against " + num(g.split_half_r, 4) + " season-controlled: " +
      esc(g.why_season_controlled) + "</p>";
  }
  function renderGate() {
    var g = DATA.gate;
    // The lede is read off clears_null, never typed: it used to assert "No"
    // as a literal, which could not follow the gate if a rebuild flipped it.
    return '<section class="mgmt-block"><h2>Club decision value: split-half gate</h2>' +
      '<p class="mgmt-lede">' + (g.clears_null ? "Clears its permutation null."
        : "Inside its permutation null band, so no club is ranked.") + "</p>" +
      '<table class="mgmt-mini mgmt-mini--wide">' +
      "<tr><td>Split-half correlation, season-controlled</td><td>" + num(g.split_half_r, 4) + "</td></tr>" +
      "<tr><td>Permutation null band</td><td>" + num(g.null_band[0], 4) + " to " + num(g.null_band[1], 4) + "</td></tr>" +
      "<tr><td>Clears the null</td><td>" + (g.clears_null ? "yes" : "no") + "</td></tr>" +
      "<tr><td>Club-seasons in the split</td><td>" + esc(g.n_agent_seasons_in_the_split) + "</td></tr>" +
      "<tr><td>Smallest detectable effect</td><td>" +
      esc(g.smallest_detectable_per_attempt_sd) + " wins per attempt</td></tr>" +
      "<tr><td>Variance explained by season</td><td>" + pct(g.variance_explained_by_season) + "</td></tr>" +
      "<tr><td>Variance explained by the club</td><td>" + pct(g.variance_explained_by_team) + "</td></tr>" +
      "</table>" +
      "<h3>Raw split-half</h3>" + rawSplitHalf(g) +
      "<h3>Null</h3>" +
      '<p class="mgmt-note">' + esc(g.null_construction) + "</p>" +
      "<h3>Detection floor and scope</h3>" +
      '<p class="mgmt-note">' + esc(g.detection_floor_reading) + "</p>" +
      '<p class="mgmt-note">' + esc(g.what_a_null_decides) + "</p>" +
      '<p class="mgmt-count">Clauses frozen in ' + esc(DATA.gate_doc) + ", " +
      esc(DATA.gate_frozen_at) + "</p></section>";
  }

  // ---- the reference tables ------------------------------------------------
  function renderReference() {
    var ref = DATA.reference;
    var re = ref.run_expectancy;
    var bases = [];
    re.forEach(function (r) { if (bases.indexOf(r.bases) < 0) bases.push(r.bases); });
    var head = "<tr><th>Bases</th><th>0 out</th><th>1 out</th><th>2 out</th></tr>";
    var body = bases.map(function (b) {
      var cells = [0, 1, 2].map(function (o) {
        var hit = re.filter(function (r) { return r.bases === b && r.outs === o; })[0];
        return "<td>" + (hit ? num(hit.runs, 3) : "") + "</td>";
      }).join("");
      return "<tr><td>" + esc(b) + "</td>" + cells + "</tr>";
    }).join("");

    // The cell carries p, n and thin. It used to be read as a bare number and
    // every row drew blank (audit F07-01); the sample size now ships beside the
    // probability, the way it does on the run-expectancy matrix.
    var his = ref.half_inning_start.tied_game.map(function (r) {
      return "<tr><td>" + esc(r.inning) + "</td><td>" + esc(r.half) + "</td><td>" +
        pct(r.batting_team_win_prob) + "</td><td>" +
        (r.n === null || r.n === undefined ? "" : esc(r.n)) + "</td></tr>";
    }).join("");

    var cal = ref.model.calibration || {};
    // The win model's method (why a model rather than a cell table, and why it
    // is monotone) belongs to the win_expectancy glossary entry; the page keeps
    // the two caveats a reader of these numbers needs. The MLB feed's own
    // Brier prints beside the model's whenever the payload carries it, so the
    // comparison is the reader's to make and never typed here.
    return '<section class="mgmt-block"><h2>' + gl("Run expectancy", "run_expectancy") + "</h2>" +
      '<p class="mgmt-note">Expected runs to the end of the half-inning; ' +
      esc(ref.model.n_plays_fit) + " plays, " + esc((ref.model.seasons || []).length) +
      " seasons. Every break-even on this page is priced from it.</p>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table mgmt-table--re"><thead>' +
      head + "</thead><tbody>" + body + "</tbody></table></div>" +
      "<h2>Coming to bat in a tied game</h2>" +
      '<p class="mgmt-note">' + esc(ref.half_inning_start.note) + "</p>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr>' +
      "<th>Inning</th><th>Half</th><th>Win probability</th><th>Games</th>" +
      "</tr></thead><tbody>" +
      his + "</tbody></table></div>" +
      "<h2>" + gl("Win model", "win_expectancy") + "</h2>" +
      '<p class="mgmt-note"><b>Tails</b>: ' + esc(ref.smoothing_costs_the_tails) + "</p>" +
      '<p class="mgmt-note"><b>Not in the state</b>: ' + esc(ref.state_excludes) + "</p>" +
      (cal.brier ? '<p class="mgmt-count">Brier ' + num(cal.brier, 4) +
        "; base rate alone " + num(cal.brier_base_rate_only, 4) +
        (cal.feed_brier ? "; MLB feed " + num(cal.feed_brier, 4) : "") + ".</p>" : "") +
      "</section>";
  }

  // ---- the club style board ------------------------------------------------
  function renderTeams() {
    var t = DATA.teams;
    if (!t || t.status !== "built") {
      return '<section class="mgmt-block"><h2>Club style</h2>' +
        '<p class="mgmt-note">Not built on this run (' + esc((t || {}).status) + ").</p></section>";
    }
    var seasons = [];
    t.rows.forEach(function (r) { if (seasons.indexOf(r.season) < 0) seasons.push(r.season); });
    seasons.sort(function (a, b) { return b - a; });
    var opts = ['<option value="ALL">Every season</option>'].concat(seasons.map(function (y) {
      return '<option value="' + y + '"' + (String(state.season) === String(y) ? " selected" : "") +
        ">" + y + "</option>";
    })).join("");

    var rows = t.rows.filter(function (r) {
      return state.season === "ALL" || String(r.season) === String(state.season);
    });
    var k = state.sort.key, asc = state.sort.asc;
    rows = rows.slice().sort(function (a, b) {
      var x = a[k], y = b[k];
      if (typeof x === "string") return asc ? x.localeCompare(y) : y.localeCompare(x);
      return asc ? x - y : y - x;
    });
    var COLS = [
      { key: "team", label: "Club" }, { key: "season", label: "Season" },
      { key: "attempts", label: "Attempts" }, { key: "success_rate", label: "Success" },
      { key: "share_2B", label: "Share to 2B" }, { key: "share_3B", label: "Share to 3B" },
      { key: "mean_breakeven_faced", label: "Mean break-even faced" }
    ];
    var head = COLS.map(function (c) {
      var arrow = k === c.key ? (asc ? " ▲" : " ▼") : "";
      return '<th data-msort="' + c.key + '" tabindex="0" role="button">' +
        esc(c.label) + arrow + "</th>";
    }).join("");
    var body = rows.slice(0, 200).map(function (r) {
      return "<tr><td>" + esc(r.team) + "</td><td>" + esc(r.season) + "</td><td>" +
        esc(r.attempts) + "</td><td>" + pct(r.success_rate) + "</td><td>" +
        pct(r.share_2B) + "</td><td>" + pct(r.share_3B) + "</td><td>" +
        pct(r.mean_breakeven_faced) + "</td></tr>";
    }).join("");

    return '<section class="mgmt-block"><h2>Club style</h2>' +
      '<p class="mgmt-note"><b>Columns</b>: ' + esc(t.columns_are_style_not_skill) + "</p>" +
      '<p class="mgmt-note"><b>No plus metric</b>: ' +
      esc(DATA.sections.team_style.why_no_plus_metric) + "</p>" +
      '<div class="mgmt-controls"><select id="mgmt-season" aria-label="Season">' +
      opts + "</select></div>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr>' + head +
      "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      '<p class="mgmt-count">' + rows.length + " club-seasons" +
      (rows.length > 200 ? ", first 200 shown" : "") + ".</p></section>";
  }

  function renderBlocked() {
    var out = "";
    ["manager_attribution", "bullpen_and_lineup"].forEach(function (k) {
      var s = DATA.sections[k];
      if (!s || s.live) return;
      out += '<section class="mgmt-block mgmt-dark"><h2>' +
        esc(k.replace(/_/g, " ")) + ' <span class="mgmt-darktag">not published</span></h2>' +
        '<p class="mgmt-dark-why">Blocked on: ' + esc(s.blocked_on) + ".</p>" +
        '<p class="mgmt-note">' + esc(s.why) + "</p></section>";
    });
    out += '<section class="mgmt-block"><h2>What this page does not claim</h2>' +
      '<p class="mgmt-note">' + esc(DATA.what_this_page_does_not_claim) + "</p></section>";
    return out;
  }

  function render() {
    var root = el("mgmt-app-root");
    if (!root) return;
    if (LOAD_ERROR) { root.innerHTML = '<p class="mgmt-note">' + esc(LOAD_ERROR) + "</p>"; return; }
    if (!DATA) { root.innerHTML = '<p class="mgmt-note">Loading.</p>'; return; }
    if (state.section === "gate") root.innerHTML = renderGate() + renderBlocked();
    else if (state.section === "reference") root.innerHTML = renderReference();
    else if (state.section === "teams") root.innerHTML = renderTeams();
    else if (state.section === "bunt") root.innerHTML = renderBunt();
    else root.innerHTML = renderRunning();
    wire();
    try { if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(root); } catch (e) { /* glossary optional */ }
  }

  function wire() {
    var s = el("mgmt-season");
    if (s) s.addEventListener("change", function () { state.season = this.value; render(); });
    Array.prototype.forEach.call(document.querySelectorAll("th[data-msort]"), function (th) {
      function go() {
        var k = th.getAttribute("data-msort");
        if (state.sort.key === k) state.sort.asc = !state.sort.asc;
        else state.sort = { key: k, asc: k === "team" };
        render();
      }
      th.addEventListener("click", go);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
      });
    });
  }

  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-mgmtsection]"), function (b) {
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(document.querySelectorAll("[data-mgmtsection]"), function (o) {
          o.classList.remove("active"); o.setAttribute("aria-selected", "false");
        });
        this.classList.add("active"); this.setAttribute("aria-selected", "true");
        state.section = this.getAttribute("data-mgmtsection");
        render();
      });
    });
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { DATA = d; render(); })
      .catch(function () {
        LOAD_ERROR = "The In-Game Management board could not be loaded.";
        render();
      });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
