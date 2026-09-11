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
        "<tr><td>Break-even needed</td><td>" + pct(t.swing_weighted_breakeven_p) + "</td></tr>" +
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

    return '<section class="mgmt-block">' +
      '<p class="mgmt-lede">' + esc(h.sentence) + "</p>" +
      '<div class="mgmt-cards">' + cards + "</div>" +
      '<p class="mgmt-note">Across ' + esc(h.games) + " games the whole running game is worth " +
      signed(h.net_dv_all_seasons_wins) + " wins to the league that plays it. That is not the " +
      "same as saying nothing happens: the pool that moves between clubs is " +
      num(h.redistributable_pool_abs_dv_wins) + " wins in absolute value. It nets out.</p>" +
      "<h3>By season</h3>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr>' +
      "<th>Season</th><th>Attempts</th><th>Success</th><th>Decision value</th>" +
      "</tr></thead><tbody>" + srows + "</tbody></table></div>" +
      "<h3>What a decision value is</h3>" +
      '<p class="mgmt-note">' + esc(r.decomposition.dv) + " " + esc(r.decomposition.er) +
      " " + esc(r.decomposition.identity) + "</p>" +
      '<p class="mgmt-note">' + esc(r.why_the_league_average_runner) + "</p>" +
      '<p class="mgmt-note">' + esc(r.which_breakeven_predicts_the_sign) + "</p>" +
      "<h3>What is excluded, and why</h3>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><tbody>' + exrows +
      "</tbody></table></div>" +
      // The census sentence says the table closes against the corpus (audit
      // F02-01). It is derived in mgmt_export._census_sentence; absent on a
      // payload that predates the census, and then nothing is drawn.
      (r.attempt_census_sentence
        ? '<p class="mgmt-note">' + esc(r.attempt_census_sentence) + "</p>" : "") +
      '<p class="mgmt-note">' + esc(r.why_two_out_attempts_are_excluded) + "</p>" +
      '<p class="mgmt-note">' + esc(r.third_out_handling) + "</p></section>";
  }

  // ---- the gate ------------------------------------------------------------
  function renderGate() {
    var g = DATA.gate;
    return '<section class="mgmt-block"><h2>Is any club better at this?</h2>' +
      '<p class="mgmt-lede">No, and the test that says so is bounded rather than a shrug.</p>' +
      '<table class="mgmt-mini mgmt-mini--wide">' +
      "<tr><td>Split-half correlation, season-controlled</td><td>" + num(g.split_half_r, 4) + "</td></tr>" +
      "<tr><td>Permutation null band</td><td>" + num(g.null_band[0], 4) + " to " + num(g.null_band[1], 4) + "</td></tr>" +
      "<tr><td>Clears the null</td><td>" + (g.clears_null ? "yes" : "no") + "</td></tr>" +
      "<tr><td>Club-seasons in the split</td><td>" + esc(g.n_agent_seasons_in_the_split) + "</td></tr>" +
      "<tr><td>Smallest effect this would have seen</td><td>" +
      esc(g.smallest_detectable_per_attempt_sd) + " wins per attempt</td></tr>" +
      "<tr><td>Variance explained by season</td><td>" + pct(g.variance_explained_by_season) + "</td></tr>" +
      "<tr><td>Variance explained by the club</td><td>" + pct(g.variance_explained_by_team) + "</td></tr>" +
      "</table>" +
      '<h3>The number that looks like a finding and is not</h3>' +
      '<p class="mgmt-note">' + esc(g.why_the_raw_number_is_not_the_finding) + "</p>" +
      "<h3>How the null was built</h3>" +
      '<p class="mgmt-note">' + esc(g.null_construction) + "</p>" +
      "<h3>What a bounded null decides</h3>" +
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
    return '<section class="mgmt-block"><h2>Run expectancy</h2>' +
      '<p class="mgmt-note">Expected runs scored from here to the end of the half-inning, ' +
      'over ' + esc(ref.model.n_plays_fit) + ' plays across ' +
      esc((ref.model.seasons || []).length) + ' seasons. This is the table every ' +
      'break-even on this page is built from.</p>' +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table mgmt-table--re"><thead>' +
      head + "</thead><tbody>" + body + "</tbody></table></div>" +
      "<h2>Coming to bat in a tied game</h2>" +
      '<p class="mgmt-note">' + esc(ref.half_inning_start.note) + "</p>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr>' +
      "<th>Inning</th><th>Half</th><th>Win probability</th><th>Games</th>" +
      "</tr></thead><tbody>" +
      his + "</tbody></table></div>" +
      "<h2>What the win model is and is not</h2>" +
      '<p class="mgmt-note">' + esc(ref.why_a_model_not_a_table) + "</p>" +
      '<p class="mgmt-note">' + esc(ref.monotone_by_construction) + "</p>" +
      '<p class="mgmt-note">' + esc(ref.smoothing_costs_the_tails) + "</p>" +
      '<p class="mgmt-note">' + esc(ref.state_excludes) + "</p>" +
      (cal.brier ? '<p class="mgmt-count">Brier ' + num(cal.brier, 4) +
        " against " + num(cal.brier_base_rate_only, 4) + " for the base rate alone.</p>" : "");
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
      '<p class="mgmt-lede">What a club CHOSE to do, not how well it chose.</p>' +
      '<p class="mgmt-note">' + esc(DATA.sections.team_style.why_no_plus_metric) + "</p>" +
      '<p class="mgmt-note">' + esc(t.columns_are_style_not_skill) + "</p>" +
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
        '<p class="mgmt-dark-why">Blocked on ' + esc(s.blocked_on) + ".</p>" +
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
    else root.innerHTML = renderRunning();
    wire();
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
