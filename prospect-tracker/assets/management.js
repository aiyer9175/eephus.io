/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - In-Game Management (/management/)
// =============================================================================
// Renders data/management_board.json (mgmt_export.py) and, on demand, one
// per club-season decision shard from data/mgmt_decisions/ (mgmt_shards.py).
//
// THERE IS NO PLUS METRIC ON THIS PAGE AND THAT IS THE POINT. The gate battery
// was frozen before it ran, it came back a bounded null, and its verdict set
// this page's scope: a club's decision value in the running game does not
// repeat between halves of its own season, so no club may be ranked by it.
//
// THE DECISION LEDGER (2026-09-23) adds nine families the play corpus can name
// and prices each as REALIZED VALUE: the win probability that actually moved
// from the decision to the last play it governed, credited to the club that
// made it. It is a record of what happened after a manager acted, not a
// measure of how well he chose, and the payload's own sentence says so on
// every leaderboard and club page. Per-family sums only, never a cross-family
// total (the windows overlap); the agent is the club-season until the manager
// ledger lands; value above state (DVS) lives on the drill-down and the League
// census only. The style figures are signed z-scores in neutral chips: no
// ladder, no plus sign, and this file makes no tier call of any kind.
//
// NOT ONE FIGURE IN THIS FILE IS TYPED. Every number and every sentence comes
// out of the payload. The one thing this file decides for itself is COLOUR, and
// only on the sign of a published realized number.
(function () {
  "use strict";

  var DATA_URL = "/data/management_board.json";
  var DATA = null;
  var LOAD_ERROR = "";
  var SECTIONS = ["league", "running", "bunt", "decisions", "clubs", "managers",
                  "challenges", "lineups", "reference", "gate"];
  var state = { section: "league", season: "ALL", sort: { key: "attempts", asc: false },
                team: "", cseason: "", family: "", game: 0, ab: -1, mgr: 0,
                boardSeason: "ALL", boardSort: { key: "n_all", asc: false },
                dsort: { key: "", asc: true }, spark: "pitching_change", open: "" };
  // One-entry shard cache: the drill-down and the club page share the club-season.
  var SHARD = { key: "", data: null, error: "", loading: "" };

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
  // COLOUR ON THE SIGN OF A PUBLISHED REALIZED NUMBER, nothing else.
  function signCls(v) {
    if (v === null || v === undefined || v !== v || v === 0) return "";
    return v > 0 ? "mgmt-pos" : "mgmt-neg";
  }
  function signedCell(v, nd) {
    if (v === null || v === undefined || v !== v) return "<td></td>";
    return '<td class="' + signCls(v) + '">' + signed(v, nd === undefined ? 3 : nd) + "</td>";
  }
  function hasTab(name) {
    try { return !!document.querySelector('[data-mgmtsection="' + name + '"]'); }
    catch (e) { return false; }
  }
  function sel(id, opts, label) {
    return '<label>' + esc(label) + ' <select id="' + esc(id) + '" class="eephus-select" aria-label="' +
      esc(label) + '">' + opts + "</select></label>";
  }
  function opt(v, label, cur) {
    return '<option value="' + esc(v) + '"' + (String(v) === String(cur) ? " selected" : "") + ">" +
      esc(label) + "</option>";
  }
  var BASE_LABEL = { 0: "empty", 1: "1B", 2: "2B", 3: "1B 2B", 4: "3B", 5: "1B 3B", 6: "2B 3B", 7: "loaded" };
  function famLabel(f) {
    var fam = ((DATA.decisions || {}).families || {})[f];
    return fam && fam.label ? fam.label : String(f || "").replace(/_/g, " ");
  }
  function families() { return Object.keys(((DATA || {}).decisions || {}).families || {}); }
  function summedFamilies() {
    var fam = ((DATA || {}).decisions || {}).families || {};
    return Object.keys(fam).filter(function (f) { return fam[f].summed; });
  }
  function halfLetter(h) { return String(h || "").indexOf("bot") === 0 ? "B" : "T"; }
  // The situation string is DERIVED from fields, never typed: half, inning,
  // outs, bases and the deciding club's lead before the play.
  function situation(r) {
    var lead = r.score_diff === 0 ? "tied" : (r.score_diff > 0 ? "up " + r.score_diff : "down " + (-r.score_diff));
    return halfLetter(r.half) + r.inning + ", " + r.outs + " out, " + BASE_LABEL[r.base] + ", " + lead;
  }
  function decisionId(r) { return r.game_pk + ":" + r.ab + ":" + r.idx; }

  // ---- hash router (mlbstats idiom: every key anchored to a separator) -----
  var SECTION_HASH_RE = /(?:^#|[#&])section=(league|running|bunt|decisions|clubs|managers|challenges|lineups|reference|gate)\b/;
  var TEAM_HASH_RE = /(?:^#|[#&])team=([A-Z]{2,3})\b/;
  var SEASON_HASH_RE = /(?:^#|[#&])season=(\d{4})\b/;
  var FAMILY_HASH_RE = /(?:^#|[#&])family=([a-z_]+)\b/;
  var GAME_HASH_RE = /(?:^#|[#&])game=(\d+)\b/;
  var AB_HASH_RE = /(?:^#|[#&])ab=(\d+)\b/;
  var MGR_HASH_RE = /(?:^#|[#&])mgr=(\d+)\b/;
  function hashNow() {
    try { return (typeof location !== "undefined" && location.hash) || ""; } catch (e) { return ""; }
  }
  function readHash() {
    var h = hashNow();
    var s = SECTION_HASH_RE.exec(h);
    if (s) state.section = s[1];
    var t = TEAM_HASH_RE.exec(h);
    if (t) state.team = t[1];
    var y = SEASON_HASH_RE.exec(h);
    if (y) { state.cseason = y[1]; state.boardSeason = y[1]; }
    var f = FAMILY_HASH_RE.exec(h);
    // Validated against the payload's family list, so a hash can never resolve
    // off Object.prototype or select a family the ledger does not carry.
    if (f && families().indexOf(f[1]) >= 0) state.family = f[1];
    var g = GAME_HASH_RE.exec(h);
    if (g) state.game = parseInt(g[1], 10);
    var a = AB_HASH_RE.exec(h);
    if (a) state.ab = parseInt(a[1], 10);
    var m = MGR_HASH_RE.exec(h);
    if (m) state.mgr = parseInt(m[1], 10);
  }
  function writeHash() {
    var parts = ["section=" + state.section];
    if (state.section === "clubs" || state.section === "decisions" || state.section === "challenges") {
      if (state.team) parts.push("team=" + state.team);
    }
    if ((state.section === "clubs" || state.section === "decisions") && state.cseason) parts.push("season=" + state.cseason);
    if (state.section === "managers" && state.boardSeason !== "ALL") parts.push("season=" + state.boardSeason);
    if (state.section === "decisions" && state.family) parts.push("family=" + state.family);
    if (state.section === "decisions" && state.game) { parts.push("game=" + state.game); if (state.ab >= 0) parts.push("ab=" + state.ab); }
    if (state.section === "managers" && state.mgr) parts.push("mgr=" + state.mgr);
    try { if (typeof history !== "undefined" && history.replaceState) history.replaceState(null, "", "#" + parts.join("&")); }
    catch (e) { /* hash optional */ }
  }
  function syncTabs() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-mgmtsection]"), function (b) {
      var on = b.getAttribute("data-mgmtsection") === state.section;
      if (on) b.classList.add("active"); else b.classList.remove("active");
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  // ---- shard schema 2 (mgmt_shards.py): the one reader ---------------------
  // A shard is array rows under a per-family key legend, with a game table
  // (date, opponent, home), a name table keyed by player id, and code tables
  // for events, kinds and flags. A window play is [event, wp_after], with
  // wp_before written only where the feed's chain breaks (the first play
  // always carries it), and its plate appearance is the row's ab plus its
  // offset unless a fourth element says otherwise. This rebuilds the row
  // objects every renderer below reads, in the shard's order (date, game_pk,
  // ab, idx; ties in family order), so nothing downstream knows the shape on
  // disk. mgmt_shards.expand is the Python twin the tests hold it to.
  var NAME_OF = { in_id: "in_name", out_id: "out_name", pitcher_id: "pitcher_name", due_id: "due_name", ondeck_id: "ondeck_name" };
  function expandShard(d) {
    if (!d || !d.families || !d.games) return null;
    var games = d.games || {}, names = d.names || {}, events = d.events || [], kinds = d.kinds || [], flagsL = d.flags || [];
    var half = (d.legend && d.legend.half) || ["top", "bottom"];
    var rows = [];
    Object.keys(d.families).forEach(function (fam) {
      var blk = d.families[fam] || {}, keys = blk.keys || [];
      (blk.rows || []).forEach(function (arr) {
        var r = {}, i, k, v;
        for (i = 0; i < keys.length; i++) {
          k = keys[i]; v = i < arr.length ? arr[i] : null;
          if (v === null || v === undefined) continue;
          if (k === "half") r.half = half[v];
          else if (k === "kind") r.kind = kinds[v];
          else if (k === "flags") r.flags = v.map(function (f) { return flagsL[f]; });
          else r[k] = v;
          if (NAME_OF[k] && names[String(v)] != null) r[NAME_OF[k]] = names[String(v)];
        }
        var g = games[String(r.game_pk)];
        r.home = !!(g && g[2]);
        if (g && g[0] != null) r.date = g[0];
        if (g && g[1] != null) r.opp = g[1];
        r.family = fam;
        if (r.window) {
          var prev = null;
          r.window = r.window.map(function (p, j) {
            var wpb = p.length > 2 ? p[2] : prev;
            var ab = p.length > 3 ? p[3] : r.ab + j;
            prev = p[1];
            return [ab, events[p[0]], wpb, p[1]];
          });
        }
        r.win_len = r.window ? r.window.length : 0;
        rows.push(r);
      });
    });
    rows.sort(function (a, b) {
      var x = a.date || "", y = b.date || "";
      if (x !== y) return x < y ? -1 : 1;
      return (a.game_pk - b.game_pk) || (a.ab - b.ab) || (a.idx - b.idx);
    });
    return { season: d.season, club: d.club, n: d.n, generated_at: d.generated_at, schema_version: d.schema_version, rows: rows };
  }

  // ---- shard fetch, one-entry cache ----------------------------------------
  function shardKey() { return state.cseason + "-" + state.team; }
  function shardUrl(season, club) {
    var tpl = ((DATA.shards || {}).path_template) || "/data/mgmt_decisions/{season}-{club}.json";
    return tpl.replace("{season}", season).replace("{club}", club);
  }
  function shardInIndex(season, club) {
    var idx = (DATA.shards || {}).index || [];
    for (var i = 0; i < idx.length; i++) if (String(idx[i].season) === String(season) && idx[i].club === club) return true;
    return false;
  }
  function loadShard() {
    var key = shardKey();
    if (!state.team || !state.cseason) return null;
    if (SHARD.key === key && SHARD.data) return SHARD.data;
    if (SHARD.key === key && (SHARD.error || SHARD.loading)) return null;
    SHARD.key = key; SHARD.data = null; SHARD.error = ""; SHARD.loading = key;
    if (!shardInIndex(state.cseason, state.team)) {
      SHARD.loading = ""; SHARD.error = "No decisions shard for " + state.team + " " + state.cseason + ".";
      return null;
    }
    try {
      fetch(shardUrl(state.cseason, state.team), { cache: "no-cache" })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (d) {
          if (SHARD.key !== key) return;
          SHARD.loading = "";
          var expanded = expandShard(d);
          if (!expanded) { SHARD.error = "No decisions shard for " + state.team + " " + state.cseason + "."; }
          else SHARD.data = expanded;
          render();
        })
        .catch(function () {
          if (SHARD.key !== key) return;
          SHARD.loading = ""; SHARD.error = "No decisions shard for " + state.team + " " + state.cseason + ".";
          render();
        });
    } catch (e) {
      SHARD.loading = ""; SHARD.error = "No decisions shard for " + state.team + " " + state.cseason + ".";
    }
    // A synchronous fetch (the render harness) has already filled the cache.
    return (SHARD.key === key && SHARD.data) ? SHARD.data : null;
  }
  function shardNote() {
    if (SHARD.error) return '<p class="mgmt-note">' + esc(SHARD.error) + "</p>";
    if (SHARD.loading) return '<p class="mgmt-note">Loading the decisions of ' + esc(state.team) + " " + esc(state.cseason) + ".</p>";
    return "";
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
      "</p></section>" + (hasTab("bunt") ? "" : renderBunt()) + renderTeams();
  }

  // ---- the sacrifice bunt --------------------------------------------------
  // The second decision family (mgmt_bunt.py), live in the payload since
  // 2026-09-07. It rides under the running game until the page shell carries a
  // tab of its own for it.
  function renderBunt() {
    var b = (DATA.sections || {}).sacrifice_bunt;
    if (!b || !b.live) return "";
    var rows = (b.cells || []).map(function (c) {
      return "<tr><td>" + esc(c.bases) + "</td><td>" + esc(c.outs) + "</td><td>" +
        esc(c.n_bunt) + '</td><td class="' + (c.dv_per_bunt > 0 ? "mgmt-pos" : "mgmt-neg") + '">' +
        signed(c.dv_per_bunt, 4) + "</td><td>" + signed(c.dv_total, 1) + "</td></tr>";
    }).join("");
    var ic = b.independent_control || {};
    var fam = (((DATA.decisions || {}).families) || {}).bunt;
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
      // The bunt ATTEMPT ledger (pitch codes) rides beside the priced result.
      (fam && fam.kinds ? '<p class="mgmt-note"><b>Attempts in the ledger</b>: ' +
        Object.keys(fam.kinds).map(function (k) { return esc(k.replace(/_/g, " ")) + " " + esc(fam.kinds[k]); }).join(", ") +
        ". " + esc(fam.sign_note || "") + " " + esc(fam.counterfactual_sentence || "") + "</p>" : "") +
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

  // ---- the club style board (running game) ---------------------------------
  function renderTeams() {
    var t = DATA.teams;
    if (!t || t.status !== "built") {
      return '<section class="mgmt-block"><h2>Club style</h2>' +
        '<p class="mgmt-note">Not built on this run (' + esc((t || {}).status) + ").</p></section>";
    }
    var seasons = [];
    t.rows.forEach(function (r) { if (seasons.indexOf(r.season) < 0) seasons.push(r.season); });
    seasons.sort(function (a, b) { return b - a; });
    var opts = [opt("ALL", "Every season", state.season)].concat(seasons.map(function (y) {
      return opt(y, y, state.season);
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

    return '<section class="mgmt-block"><h2>Club style: the running game</h2>' +
      '<p class="mgmt-note"><b>Columns</b>: ' + esc(t.columns_are_style_not_skill) + "</p>" +
      '<p class="mgmt-note"><b>No plus metric</b>: ' +
      esc(DATA.sections.team_style.why_no_plus_metric) + "</p>" +
      '<div class="mgmt-controls">' + sel("mgmt-season", opts, "Season") + "</div>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr>' + head +
      "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      '<p class="mgmt-count">' + rows.length + " club-seasons" +
      (rows.length > 200 ? ", first 200 shown" : "") + ".</p></section>";
  }

  // ---- the League tab: the family census -----------------------------------
  function ledgerDark(title) {
    var d = DATA.decisions || {};
    return '<section class="mgmt-block mgmt-dark"><h2>' + esc(title) +
      ' <span class="mgmt-darktag">not built</span></h2>' +
      '<p class="mgmt-dark-why">' + esc(d.status || "the decision ledger is not on this build") + "</p>" +
      (d.why ? '<p class="mgmt-note">' + esc(d.why) + "</p>" : "") + "</section>";
  }
  function censusSeasons() {
    var d = DATA.decisions || {};
    return (d.seasons || []).map(String).sort().reverse();
  }
  function renderLeague() {
    var d = DATA.decisions;
    if (!d || !d.live) return ledgerDark("League census");
    var seasons = censusSeasons();
    if (!seasons.length) return ledgerDark("League census");
    var season = (state.boardSeason !== "ALL" && seasons.indexOf(String(state.boardSeason)) >= 0)
      ? String(state.boardSeason) : seasons[0];
    var opts = seasons.map(function (y) { return opt(y, y, season); }).join("");
    var fams = d.families || {};
    var rows = Object.keys(fams).map(function (f) {
      var b = fams[f];
      var n = (b.n_by_season || {})[season];
      var s = (b.league_sum_mwpa_by_season || {})[season];
      var thin = b.thin_cells || {};
      // A counted family with no event in the feed for that season (mound visits
      // enter the feed in 2023) reads "not in the feed", never a zero.
      var notInFeed = b.counted_only && (b.seasons_without_events || []).map(String).indexOf(String(season)) >= 0;
      // A family read against its corpus rows (ejections) prints the rows it could
      // not place: "171 attributed of 173", never a count that disagrees with the
      // Managers tab's fixture on the same page.
      var nc = (b.n_corpus_rows_by_season || {})[season];
      var nCell = notInFeed ? "not in the feed"
        : (n == null ? "" : (nc != null && nc !== n ? esc(n) + " attributed of " + esc(nc) : esc(n)));
      // A summed family prints its league sum. A family whose window is stored and
      // never summed (defensive subs, spec 3.4) prints that, never a total.
      var realized = !b.has_window ? "<td>counted</td>" : (b.summed ? signedCell(s, 1) : "<td>stored, not summed</td>");
      return "<tr><td>" + esc(b.label || f) + "</td><td>" + nCell + "</td><td>" +
        num(b.mean_li, 2) + "</td>" + realized +
        "<td>" + esc(b.within_family_windows) + "</td>" +
        "<td>" + (b.dvs_identity_max_abs == null ? "" : esc(b.dvs_identity_max_abs)) + "</td>" +
        "<td>" + (thin.decisions_in_thin_cells == null ? "" :
          esc(thin.decisions_in_thin_cells) + " of " + esc(b.n) + " in " + esc(thin.cells_thin) + " of " + esc(thin.cells_total) + " cells") + "</td>" +
        "<td>" + esc(b.gate_status) + "</td></tr>";
    }).join("");
    var cb = d.chain_break || {};
    var cbs = (cb.by_season || {})[season] || {};
    var rp = d.removed_pitcher || {};
    var sw = d.switch_classification || {};
    var base = d.baseline || {};
    return '<section class="mgmt-block">' +
      '<p class="mgmt-lede">' + esc(d.realized_sentence) + "</p>" +
      '<p class="mgmt-agent">' + esc(d.agent_sentence) + "</p>" +
      '<div class="mgmt-controls">' + sel("mgmt-cseason", opts, "Season") +
      '<span class="mgmt-count">through ' + esc((d.through_by_season || {})[season] || "") +
      "; corpus built " + esc(String(d.corpus_built_at || "").slice(0, 10)) + "</span></div>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table mgmt-table--census"><thead><tr>' +
      "<th>Family</th><th>Decisions</th><th>Mean LI</th><th>" + gl("Realized", "realized_mwpa") +
      ' <span class="mgmt-th-tag">wins, realized</span></th><th>Windows within the family</th>' +
      "<th>" + gl("DVS", "dvs") + " identity</th><th>Thin cells</th><th>Gate</th></tr></thead><tbody>" +
      rows + "</tbody></table></div>" +
      '<p class="mgmt-note"><b>Sums</b>: ' + esc(d.overlap_note) + "</p>" +
      '<p class="mgmt-note"><b>Value above state</b>: ' + esc(d.dvs_note) + "</p>" +
      '<p class="mgmt-note"><b>Single plate appearance</b>: ' + esc(d.single_pa_caveat) + "</p>" +
      '<p class="mgmt-note"><b>Leverage</b>: ' + esc(d.li_note) + "</p>" +
      "<h3>The window is an endpoint difference</h3>" +
      '<p class="mgmt-note">' + esc(cb.note) + " On " + esc(season) + ": " +
      pct(cbs.share_of_plays_not_chained, 2) + " of plays do not chain at a tolerance of " +
      esc(cb.tolerance) + "; the largest gap is " + num(cbs.max_gap_points, 1) +
      " points; a row sum misses a median " + num(cbs.row_sum_misses_median_points, 1) +
      " points of a game's journey (p90 " + num(cbs.row_sum_misses_p90_points, 1) +
      ", p99 " + num(cbs.row_sum_misses_p99_points, 1) + ").</p>" +
      "<h3>Derivations</h3>" +
      '<p class="mgmt-note"><b>Removed pitcher</b>: ' + esc(rp.derivation) + " Agreement with the description: " +
      esc(rp.description_agree) + " of " + esc(rp.description_checked) + "; with the field where it names a pitcher: " +
      esc(rp.replacing_pitcher_clause_agree) + " of " + esc(rp.replacing_pitcher_clause_rows) + ".</p>" +
      '<p class="mgmt-note"><b>Inherited runners</b>: ' + esc(((fams.pitching_change || {}).inherited_runners || {}).derivation) + "</p>" +
      '<p class="mgmt-note"><b>Defensive switches</b>: ' + esc(sw.n) + " rows: " + esc(sw.dh_retained) +
      " designated hitter retained, " + esc(sw.position_move) + " position moves, " + esc(sw.stayed_in_field) +
      " stayed in the field, " + esc(sw.unclassified) + " unclassified.</p>" +
      (base.min_cell != null ? '<p class="mgmt-note"><b>Baseline</b>: cells need ' + esc(base.min_cell) +
        " league windows; " + esc(base.identity) + " " + esc(base.where_dvs_lives) + "</p>" : "") +
      "</section>";
  }

  // ---- the club-season board (Managers tab until the manager ledger lands) --
  function boardCols() {
    var cols = [
      { key: "club", label: "Club", kind: "club" }, { key: "season", label: "Season" },
      { key: "games", label: "G" }, { key: "n_all", label: "Ledger rows" },
      { key: "n_pitching_change", label: "PC" }, { key: "n_pinch_hit", label: "PH" },
      { key: "n_pinch_run", label: "PR" }, { key: "n_intentional_walk", label: "IBB" },
      { key: "n_bunt", label: "Bunt" }, { key: "n_steal", label: "SB" },
      { key: "n_defensive_sub", label: "DS" }, { key: "mean_li", label: "LI at decision", nd: 2 }
    ];
    summedFamilies().forEach(function (f) {
      cols.push({ key: "mwpa_" + f, label: famLabel(f), kind: "realized", fam: f });
    });
    [["z_hook", "Hook z (negative = earlier)"], ["z_pen", "Pen z"], ["z_bench", "Bench z"],
     ["z_ibb", "IBB z"], ["z_visit", "Visit z"]].forEach(function (p) {
      cols.push({ key: p[0], label: p[1], kind: "z" });
    });
    cols.push({ key: "best", label: "Best decision", kind: "link", sortless: true });
    cols.push({ key: "worst", label: "Worst decision", kind: "link", sortless: true });
    return cols;
  }
  function decisionLink(row, d) {
    if (!d) return "<td></td>";
    var href = "#section=decisions&team=" + esc(row.club) + "&season=" + esc(row.season) +
      "&family=" + esc(d.family) + "&game=" + esc(d.game_pk) + "&ab=" + esc(d.ab);
    return '<td class="' + signCls(d.mwpa) + '"><a href="' + href + '" data-mlink="1">' + signed(d.mwpa, 3) +
      " " + esc(famLabel(d.family).toLowerCase()) + "</a></td>";
  }
  function renderBoard() {
    var c = DATA.clubs;
    if (!c || !c.rows || !c.rows.length) return ledgerDark("Club-season leaderboard");
    var floors = c.floors || {};
    var seasons = [];
    c.rows.forEach(function (r) { if (seasons.indexOf(r.season) < 0) seasons.push(r.season); });
    seasons.sort(function (a, b) { return b - a; });
    var opts = [opt("ALL", "Every season", state.boardSeason)].concat(seasons.map(function (y) {
      return opt(y, y, state.boardSeason);
    })).join("");
    var rows = c.rows.filter(function (r) {
      return state.boardSeason === "ALL" || String(r.season) === String(state.boardSeason);
    });
    var k = state.boardSort.key, asc = state.boardSort.asc;
    rows = rows.slice().sort(function (a, b) {
      var x = a[k], y = b[k];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      if (typeof x === "string") return asc ? x.localeCompare(y) : y.localeCompare(x);
      return asc ? x - y : y - x;
    });
    var cols = boardCols();
    var head = cols.map(function (col) {
      var arrow = k === col.key ? (asc ? " ▲" : " ▼") : "";
      var tag = col.kind === "realized" ? ' <span class="mgmt-th-tag">' + esc(c.realized_header_tag || "realized") + "</span>"
        : col.kind === "z" ? ' <span class="mgmt-th-tag">style</span>' : "";
      if (col.sortless) return "<th>" + esc(col.label) + "</th>";
      return '<th data-bsort="' + col.key + '" tabindex="0" role="button">' + esc(col.label) + tag + arrow + "</th>";
    }).join("");
    var body = rows.slice(0, 300).map(function (r) {
      return "<tr>" + cols.map(function (col) {
        var v = r[col.key];
        if (col.kind === "club") {
          return '<td><a href="#section=clubs&team=' + esc(r.club) + "&season=" + esc(r.season) +
            '" data-mlink="1">' + esc(r.club) + "</a>" + (r.partial ? '<span class="mgmt-flag">partial</span>' : "") + "</td>";
        }
        if (col.kind === "realized") {
          var n = r["n_" + col.fam];
          if (v == null) return '<td title="' + esc(n) + " below the floor of " + esc(floors[col.fam]) + '"> - </td>';
          return '<td class="' + signCls(v) + '">' + signed(v, 2) + "</td>";
        }
        if (col.kind === "z") return "<td>" + (v == null ? "" : esc(signed(v, 1))) + "</td>";
        if (col.kind === "link") return decisionLink(r, v);
        if (col.nd != null) return "<td>" + num(v, col.nd) + "</td>";
        return "<td>" + (v == null ? "" : esc(v)) + "</td>";
      }).join("") + "</tr>";
    }).join("");
    return '<section class="mgmt-block"><h2>Club-season leaderboard</h2>' +
      '<p class="mgmt-lede">' + esc(c.columns_are_realized_not_skill) + "</p>" +
      '<p class="mgmt-agent">' + esc(c.agent_sentence) + "</p>" +
      '<p class="mgmt-note"><b>Sorting a realized column</b>: ' + esc(c.sort_by_realized_is_a_rank_by_what_happened) + "</p>" +
      '<p class="mgmt-note"><b>Style columns</b>: ' + esc(c.style_sentence) + "</p>" +
      '<div class="mgmt-controls">' + sel("mgmt-bseason", opts, "Season") + "</div>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr>' + head +
      "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      '<p class="mgmt-count">' + rows.length + " club-seasons" + (rows.length > 300 ? ", first 300 shown" : "") +
      ". Realized figures are shown at or above the family floor (" +
      Object.keys(floors).map(function (f) { return esc(famLabel(f).toLowerCase()) + " " + esc(floors[f]); }).join(", ") +
      "); a dash carries the count in its tooltip. Defensive subs are counted and their window value is never summed.</p>" +
      "</section>";
  }
  function renderManagers() {
    var m = DATA.managers || {};
    var out = "";
    if (!m.live) {
      out += '<section class="mgmt-block mgmt-dark"><h2>Managers <span class="mgmt-darktag">not published</span></h2>' +
        '<p class="mgmt-dark-why">Blocked on: ' + esc(m.blocked_on) + ".</p>" +
        '<p class="mgmt-note">' + esc(m.why) + "</p>" +
        (m.fixture && m.fixture.ejection_named_managers != null
          ? '<p class="mgmt-count">Fixture: ' + esc(m.fixture.ejection_named_managers) + " of " +
            esc(m.fixture.ejections) + " ejection rows name a manager with an id; " + esc(m.fixture.note) + "</p>" : "") +
        "</section>";
    }
    return out + renderBoard();
  }

  // ---- club pages ----------------------------------------------------------
  function clubRow() {
    var rows = ((DATA.clubs || {}).rows) || [];
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].club === state.team && String(rows[i].season) === String(state.cseason)) return rows[i];
    }
    return null;
  }
  function clubList() {
    var rows = ((DATA.clubs || {}).rows) || [], out = [];
    rows.forEach(function (r) { if (out.indexOf(r.club) < 0) out.push(r.club); });
    return out.sort();
  }
  function seasonsOf(club) {
    var rows = ((DATA.clubs || {}).rows) || [], out = [];
    rows.forEach(function (r) { if (r.club === club && out.indexOf(r.season) < 0) out.push(r.season); });
    return out.sort(function (a, b) { return b - a; });
  }
  function ensureClubSeason() {
    var clubs = clubList();
    if (!clubs.length) return false;
    if (clubs.indexOf(state.team) < 0) state.team = clubs[0];
    var ys = seasonsOf(state.team);
    if (ys.map(String).indexOf(String(state.cseason)) < 0) state.cseason = String(ys[0]);
    return true;
  }
  function controls(withFamily) {
    var clubs = clubList().map(function (c) { return opt(c, c, state.team); }).join("");
    var ys = seasonsOf(state.team).map(function (y) { return opt(y, y, state.cseason); }).join("");
    var out = '<div class="mgmt-controls">' + sel("mgmt-club", clubs, "Club") + sel("mgmt-cseason", ys, "Season");
    if (withFamily) {
      var fo = [opt("", "Every family", state.family)].concat(families().map(function (f) {
        return opt(f, famLabel(f), state.family);
      })).join("");
      out += sel("mgmt-family", fo, "Family");
    }
    return out + "</div>";
  }
  function hist(clubCounts, leagueCounts, bins) {
    var cs = clubCounts.reduce(function (a, b) { return a + b; }, 0) || 1;
    var ls = leagueCounts.reduce(function (a, b) { return a + b; }, 0) || 1;
    var mx = 0;
    bins.forEach(function (_, i) { mx = Math.max(mx, clubCounts[i] / cs, leagueCounts[i] / ls); });
    mx = mx || 1;
    var bars = bins.map(function (_, i) {
      return '<div class="mgmt-bin"><span class="mgmt-b-club" style="height:' + (100 * clubCounts[i] / cs / mx).toFixed(1) +
        '%" title="club ' + esc(clubCounts[i]) + '"></span><span class="mgmt-b-league" style="height:' +
        (100 * leagueCounts[i] / ls / mx).toFixed(1) + '%" title="league ' + esc(leagueCounts[i]) + '"></span></div>';
    }).join("");
    var axis = bins.map(function (b) { return "<span>" + esc(b) + "</span>"; }).join("");
    return '<div class="mgmt-hist" style="grid-template-columns:repeat(' + bins.length + ',1fr)">' + bars + "</div>" +
      '<div class="mgmt-hist-axis" style="grid-template-columns:repeat(' + bins.length + ',1fr)">' + axis + "</div>" +
      '<div class="mgmt-hist-legend"><i class="mgmt-i-club"></i>club <i class="mgmt-i-league"></i>league; share of hooks per pitch-count bin</div>';
  }
  // Sparkline: inline SVG, one polyline, currentColor, no library.
  function spark(values) {
    if (!values.length) return "";
    var w = 720, h = 90, pad = 4;
    var mn = Math.min(0, Math.min.apply(null, values)), mx = Math.max(0, Math.max.apply(null, values));
    var span = (mx - mn) || 1;
    var pts = values.map(function (v, i) {
      var x = pad + (w - 2 * pad) * (values.length === 1 ? 0 : i / (values.length - 1));
      var y = pad + (h - 2 * pad) * (1 - (v - mn) / span);
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    var zy = pad + (h - 2 * pad) * (1 - (0 - mn) / span);
    return '<div class="mgmt-spark"><svg viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" role="img" aria-label="cumulative realized value by game">' +
      '<line class="mgmt-spark-zero" x1="0" x2="' + w + '" y1="' + zy.toFixed(1) + '" y2="' + zy.toFixed(1) + '"></line>' +
      '<polyline class="mgmt-spark-line" points="' + pts + '"></polyline></svg></div>';
  }
  function mean(xs) { return xs.length ? xs.reduce(function (a, b) { return a + b; }, 0) / xs.length : null; }
  function sum(xs) { return xs.reduce(function (a, b) { return a + b; }, 0); }
  function countBy(rows, keyFn) {
    var out = {};
    rows.forEach(function (r) { var k = keyFn(r); out[k] = (out[k] || 0) + 1; });
    return out;
  }
  function inningBucket(i) { return i <= 6 ? "1-6" : i === 7 ? "7" : i === 8 ? "8" : "9+"; }
  function leadState(r) { return r.score_diff > 0 ? "ahead" : r.score_diff < 0 ? "behind" : "tied"; }
  function drill(family) {
    return "#section=decisions&team=" + esc(state.team) + "&season=" + esc(state.cseason) + (family ? "&family=" + esc(family) : "");
  }
  function miniTable(pairs) {
    return '<table class="mgmt-mini">' + pairs.map(function (p) {
      return "<tr><td>" + p[0] + "</td><td>" + p[1] + "</td></tr>";
    }).join("") + "</table>";
  }
  function renderClubs() {
    var d = DATA.decisions;
    if (!d || !d.live || !ensureClubSeason()) return ledgerDark("Club pages");
    var row = clubRow();
    var c = DATA.clubs;
    var floors = c.floors || {};
    var fams = d.families || {};
    var out = '<section class="mgmt-block">' + controls(false);
    if (!row) return out + '<p class="mgmt-note">No club-season row for ' + esc(state.team) + " " + esc(state.cseason) + ".</p></section>";
    var sapi = ((c.statsapi_codes || {})[row.club]) || "";
    var famLine = summedFamilies().map(function (f) {
      var v = row["mwpa_" + f];
      return '<span class="mgmt-fam">' + esc(famLabel(f)) + " <b class=\"" + signCls(v) + '">' +
        (v == null ? " - " : signed(v, 2)) + "</b></span>";
    }).join("");
    out += '<div class="mgmt-club-head"><h2>' + esc(row.club) + " " + esc(row.season) +
      (row.partial ? ' <span class="mgmt-flag">partial</span>' : "") + "</h2>" +
      '<div class="mgmt-club-meta">' + esc(row.agent) + "; " + esc(row.games) + " games; " + esc(row.n_all) +
      " ledger rows; mean " + gl("LI at decision", "li_at_decision") + " " + num(row.mean_li, 2) +
      "; share at LI 1.5 or more " + pct(row.share_li_high) + "</div>" +
      '<div class="mgmt-club-fams">' + famLine + "</div>" +
      '<p class="mgmt-note">' + esc(c.columns_are_realized_not_skill) + "</p>" +
      '<p class="mgmt-agent">' + esc(c.agent_sentence) + "</p></div>";
    // family cards
    out += '<div class="mgmt-cards">' + families().map(function (f) {
      var n = row["n_" + f] || 0, b = fams[f] || {};
      var v = row["mwpa_" + f];
      var absent = b.counted_only && (b.seasons_without_events || []).map(String).indexOf(String(row.season)) >= 0;
      var status = absent ? "not in the feed for this season"
        : !b.summed ? (b.counted_only ? "counted, never valued" : "stored, never summed")
        : (n >= (floors[f] || 0) ? "at or above the floor of " + floors[f] : "below the floor of " + floors[f]);
      return '<div class="mgmt-card"><div class="mgmt-card-title">' + esc(famLabel(f)) + "</div>" +
        '<div class="mgmt-card-big">' + esc(n) + "</div>" +
        '<div class="mgmt-card-sub">' + num(row.games ? n / row.games : null, 2) + " per game; " + esc(status) + "</div>" +
        (b.summed ? '<div class="' + signCls(v) + '">' + (v == null ? " - " : signed(v, 2) + " wins, realized") + "</div>" : "") +
        '<div class="mgmt-links"><a href="' + drill(f) + '" data-mlink="1">decisions</a></div></div>';
    }).join("") + "</div>";
    // /franchise/ (D3) and /ledger/ (D1) are drawn only when the export found
    // the route built; until then an anchor to either is a 404.
    var routes = DATA.routes || {};
    out += '<div class="mgmt-links">' +
      (sapi ? '<a href="/mlbstats/#section=bullpen&view=teams&team=' + esc(sapi) + '">bullpen board (' + esc(sapi) + ")</a>" +
        '<a href="/mlbstats/#section=leverage&team=' + esc(sapi) + '">leverage board</a>' : "") +
      '<a href="/projections/#team=' + esc(row.club) + '">projections</a>' +
      '<a href="/prospx/#farm-org=' + esc(row.club) + '">farm</a>' +
      (routes.franchise ? '<a href="/franchise/#team=' + esc(row.club) + '">franchise</a>' : "") +
      (routes.ledger ? '<a href="/ledger/#team=' + esc(row.club) + '">ledger</a>' : "") +
      '<a href="' + drill("") + '" data-mlink="1">every decision</a></div>';
    // style z strip: NEUTRAL chips
    out += "<h3>Style</h3><p class=\"mgmt-note\">" + esc(c.style_sentence) + "</p>" +
      '<div class="mgmt-zstrip">' + [["z_hook", "Hook z", "hook_z"], ["z_pen", "Pen z", "pen_z"], ["z_bench", "Bench z", "bench_z"],
        ["z_ibb", "IBB z", "ibb_z"], ["z_visit", "Visit z", "visit_z"]].map(function (p) {
        return '<div class="mgmt-zchip"><b>' + (row[p[0]] == null ? "" : esc(signed(row[p[0]], 1))) + "</b>" +
          '<span class="mgmt-zlbl">' + gl(p[1], p[2]) + (p[0] === "z_hook" ? " (negative = earlier)" : "") + "</span></div>";
      }).join("") +
      '<div class="mgmt-zchip"><b>' + num(row.mean_li, 2) + '</b><span class="mgmt-zlbl">' + gl("LI at decision", "li_at_decision") + "</span></div></div>";
    // the shard-backed sections
    var sh = loadShard();
    if (!sh) return out + shardNote() + "</section>";
    var rows = sh.rows || [];
    var pc = rows.filter(function (r) { return r.family === "pitching_change"; });
    var hooks = pc.filter(function (r) { return r.kind === "starter_hook" && r.pitch_count != null; });
    var hh = d.hook_hist || { bins: [], by_season: {} };
    var bins = hh.bins || [];
    var lg = (hh.by_season || {})[String(state.cseason)] || bins.map(function () { return 0; });
    var clubCounts = bins.map(function () { return 0; });
    hooks.forEach(function (r) {
      var i = Math.min(bins.length - 1, Math.floor(r.pitch_count / 10));
      if (i >= 0) clubCounts[i]++;
    });
    var hookInn = countBy(hooks, function (r) { return r.inning; });
    var tto = countBy(hooks.filter(function (r) { return r.tto != null; }), function (r) { return r.tto; });
    out += "<h3>Hook profile</h3>" +
      '<p class="mgmt-note">' + esc(hooks.length) + " starter hooks; median pitch count at removal " +
      num(row.hook_median_pitches, 0) + " (league median " + num(((fams.pitching_change || {}).hook_pitch_count || {}).median, 0) + ").</p>" +
      (bins.length ? hist(clubCounts, lg, bins) : "") +
      miniTable([["Inning of the hook",
        Object.keys(hookInn).sort(function (a, b) { return a - b; }).map(function (k) { return esc(k) + ": " + esc(hookInn[k]); }).join(", ")],
        ["Times through the order at the hook",
          Object.keys(tto).sort(function (a, b) { return a - b; }).map(function (k) { return esc(k) + ": " + esc(tto[k]); }).join(", ")]]);
    // bullpen deployment
    var LI_BINS = [[0, 0.5, "under 0.5"], [0.5, 1, "0.5 to 1"], [1, 1.5, "1 to 1.5"], [1.5, 2, "1.5 to 2"], [2, 3, "2 to 3"], [3, 1e9, "3 and up"]];
    var entries = pc.filter(function (r) { return r.li != null; });
    var liRows = LI_BINS.map(function (b) {
      var g = entries.filter(function (r) { return r.li >= b[0] && r.li < b[1]; });
      var fp = g.filter(function (r) { return r.first_pa_mwpa != null; }).map(function (r) { return r.first_pa_mwpa; });
      var st = g.filter(function (r) { return r.mwpa != null; }).map(function (r) { return r.mwpa; });
      return "<tr><td>" + esc(b[2]) + "</td><td>" + esc(g.length) + "</td>" + signedCell(mean(fp), 4) + signedCell(st.length ? sum(st) : null, 3) + "</tr>";
    }).join("");
    var inh = sum(pc.map(function (r) { return r.inherited || 0; }));
    var inhS = sum(pc.map(function (r) { return r.inherited_scored || 0; }));
    // data-csv-primary: the club page's export is this table, not the two-row
    // hook-profile mini table painted above it.
    out += "<h3>Bullpen deployment</h3>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table" data-csv-primary><thead><tr><th>LI at entry</th><th>Entries</th>' +
      '<th>Mean first-PA ' + gl("mWPA", "realized_mwpa") + '</th><th>Stint mWPA, summed <span class="mgmt-th-tag">realized</span></th></tr></thead><tbody>' +
      liRows + "</tbody></table></div>" +
      '<p class="mgmt-note">Inherited runners: ' + esc(inhS) + " scored of " + esc(inh) + " inherited" +
      (inh ? " (" + pct(inhS / inh, 1) + ")" : "") + "; " + esc(((fams.pitching_change || {}).inherited_runners || {}).derivation) + "</p>";
    // bench
    var ph = rows.filter(function (r) { return r.family === "pinch_hit"; });
    var pr = rows.filter(function (r) { return r.family === "pinch_run"; });
    var ds = rows.filter(function (r) { return r.family === "defensive_sub"; });
    var phInn = countBy(ph, function (r) { return inningBucket(r.inning); });
    var phSpot = countBy(ph, function (r) { return (r.flags || []).indexOf("pitcher_spot") >= 0 ? "pitcher's spot" : "position player"; });
    var phStay = ph.filter(function (r) { return (r.flags || []).indexOf("stayed_in") >= 0; }).length;
    var prBase = countBy(pr, function (r) { return r.kind || "pinch_run"; });
    var prFate = countBy(pr, function (r) { var f = r.flags || []; return f.indexOf("scored") >= 0 ? "scored" : f.indexOf("out_on_bases") >= 0 ? "out on the bases" : "left on"; });
    var dsLead = countBy(ds, function (r) { return leadState(r) + ", inning " + inningBucket(r.inning); });
    function kv(o) { return Object.keys(o).sort().map(function (k) { return esc(k) + ": " + esc(o[k]); }).join(", "); }
    out += "<h3>Bench</h3>" + miniTable([
      ["Pinch hitters by inning", kv(phInn)], ["Pinch hitters by spot", kv(phSpot) + "; stayed in " + esc(phStay)],
      ["Pinch runners by base", kv(prBase)], ["Pinch runners, outcome", kv(prFate)],
      ["Defensive subs by lead state", kv(dsLead)]]);
    // tactics
    var ibb = rows.filter(function (r) { return r.family === "intentional_walk"; });
    var ibbState = {};
    ibb.forEach(function (r) {
      var k = r.outs + " out, " + BASE_LABEL[r.base] + ", " + (r.batter_side || "?") + "HB";
      var s = ibbState[k] = ibbState[k] || { n: 0, v: [] };
      s.n++; if (r.mwpa != null) s.v.push(r.mwpa);
    });
    var ibbRows = Object.keys(ibbState).sort().map(function (k) {
      return "<tr><td>" + esc(k) + "</td><td>" + esc(ibbState[k].n) + "</td>" + signedCell(mean(ibbState[k].v), 4) + "</tr>";
    }).join("");
    var bunts = rows.filter(function (r) { return r.family === "bunt"; });
    var bState = {};
    bunts.forEach(function (r) {
      var k = r.outs + " out, " + BASE_LABEL[r.base];
      var s = bState[k] = bState[k] || { n: 0, v: [], dv: null, kinds: {} };
      s.n++; if (r.mwpa != null) s.v.push(r.mwpa);
      if (r.dv_cell != null) s.dv = r.dv_cell;
      var kk = r.kind || "bunt"; s.kinds[kk] = (s.kinds[kk] || 0) + 1;
    });
    var bRows = Object.keys(bState).sort().map(function (k) {
      var s = bState[k];
      return "<tr><td>" + esc(k) + "</td><td>" + esc(s.n) + "</td><td>" + kv(s.kinds) + "</td>" +
        signedCell(mean(s.v), 4) + (s.dv == null ? "<td></td>" : '<td class="' + signCls(s.dv) + '">' + signed(s.dv, 4) + "</td>") + "</tr>";
    }).join("");
    var steal = ((DATA.teams || {}).rows || []).filter(function (r) { return r.team === row.club && String(r.season) === String(row.season); })[0];
    out += "<h3>Tactics</h3>" +
      "<h4>Intentional walks by state</h4>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr><th>State</th><th>Walks</th><th>Mean mWPA <span class="mgmt-th-tag">realized</span></th></tr></thead><tbody>' +
      (ibbRows || "<tr><td>none</td><td></td><td></td></tr>") + "</tbody></table></div>" +
      '<p class="mgmt-note">' + esc((fams.intentional_walk || {}).counterfactual_sentence) + "</p>" +
      "<h4>Bunts by state</h4>" +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr><th>State</th><th>Bunts</th><th>Kinds</th>' +
      '<th>Mean mWPA <span class="mgmt-th-tag">realized</span></th><th>League ' + gl("DV", "decision_value") + " per bunt</th></tr></thead><tbody>" +
      (bRows || "<tr><td>none</td><td></td><td></td><td></td><td></td></tr>") + "</tbody></table></div>" +
      "<h4>Steals</h4>" +
      (steal ? miniTable([["Attempts (priced)", esc(steal.attempts)], ["Success", pct(steal.success_rate)],
        ["Share to 2B / 3B", pct(steal.share_2B) + " / " + pct(steal.share_3B)],
        ["Mean break-even faced", pct(steal.mean_breakeven_faced)],
        ["Realized mWPA, summed", row.mwpa_steal == null ? " - " : '<span class="' + signCls(row.mwpa_steal) + '">' + signed(row.mwpa_steal, 2) + "</span>"]])
        : '<p class="mgmt-note">No priced steal row for this club-season.</p>');
    // timeline: one family, one line
    var sf = state.spark && fams[state.spark] && fams[state.spark].summed ? state.spark : "pitching_change";
    var tl = rows.filter(function (r) { return r.family === sf && r.mwpa != null; });
    var byGame = {};
    var order = [];
    tl.forEach(function (r) {
      var k = (r.date || "") + "|" + r.game_pk;
      // hasOwnProperty, not a truthiness test: a game whose running total sits
      // at exactly zero would otherwise be pushed a second time.
      if (!Object.prototype.hasOwnProperty.call(byGame, k)) { byGame[k] = 0; order.push(k); }
      byGame[k] += r.mwpa;
    });
    order.sort();
    var cum = 0, series = order.map(function (k) { cum += byGame[k]; return cum; });
    var fo = summedFamilies().map(function (f) { return opt(f, famLabel(f), sf); }).join("");
    out += "<h3>Season timeline</h3>" +
      '<div class="mgmt-controls">' + sel("mgmt-spark", fo, "Family") +
      '<span class="mgmt-count">cumulative realized mWPA by game, one family; never a cross-family line</span></div>' +
      spark(series) +
      '<p class="mgmt-count">' + esc(order.length) + " games with a " + esc(famLabel(sf).toLowerCase()) + " decision; ends at " +
      (series.length ? signed(series[series.length - 1], 2) : "") + " wins, realized.</p>";
    // 2026 feeds: dark
    var ch = DATA.challenges || {}, lu = DATA.lineups || {};
    if (!ch.live || !lu.live) {
      out += '<div class="mgmt-dark"><h3>Challenges, mound-visit budgets, lineups <span class="mgmt-darktag">not published</span></h3>' +
        '<p class="mgmt-note">Blocked on: ' + esc(ch.blocked_on) + "; " + esc(lu.blocked_on) + ".</p></div>";
    }
    return out + "</section>";
  }

  // ---- the per-decision drill-down -----------------------------------------
  function detailCard(r) {
    var who = r.in_name ? esc(r.in_name) + (r.out_name ? " for " + esc(r.out_name) : "") : (r.pitcher_name ? esc(r.pitcher_name) : (r.ejected_name ? esc(r.ejected_name) : ""));
    var pairs = [
      ["Situation", esc(situation(r)) + (r.li == null ? "" : ", LI " + num(r.li, 2))],
      ["Game", esc(r.date || "") + ", " + (r.home ? "vs " : "at ") + esc(r.opp || "")],
      ["Realized " + gl("mWPA", "realized_mwpa"), r.mwpa == null ? "not valued" : '<span class="' + signCls(r.mwpa) + '">' + signed(r.mwpa, 4) + "</span> wins, realized"],
      [gl("DVS", "dvs"), r.dvs == null ? (r.mwpa == null ? "" : "thin cell") : '<span class="' + signCls(r.dvs) + '">' + signed(r.dvs, 4) + "</span> wins above state"],
      ["Window", esc(r.win_len || 0) + " plays"],
      ["Flags", (r.flags || []).map(function (f) { return '<span class="mgmt-flag">' + esc(f.replace(/_/g, " ")) + "</span>"; }).join(" ") || "none"]
    ];
    if (r.family === "pitching_change") pairs.push(["Removed pitcher", esc(r.out_name || "") + (r.pitch_count == null ? "" : ", " + esc(r.pitch_count) + " pitches, time through the order " + esc(r.tto))],
      ["Inherited runners", esc(r.inherited || 0) + ", scored " + esc(r.inherited_scored || 0)],
      ["First plate appearance", r.first_pa_mwpa == null ? "" : '<span class="' + signCls(r.first_pa_mwpa) + '">' + signed(r.first_pa_mwpa, 4) + "</span>"]);
    if (r.family === "intentional_walk") pairs.push(["On deck", esc(r.ondeck_name || "")], ["Walk alone", r.walk_only_mwpa == null ? "" : '<span class="' + signCls(r.walk_only_mwpa) + '">' + signed(r.walk_only_mwpa, 4) + "</span>"]);
    if (r.family === "steal") pairs.push(["Model " + gl("DV", "decision_value") + " / " + gl("ER", "execution_residual") + " / realized (model)", signed(r.dv, 4) + " / " + signed(r.er, 4) + " / " + signed(r.realized_delta, 4)],
      [gl("Break-even", "steal_break_even"), pct(r.breakeven_p)]);
    if (r.family === "bunt" && r.dv_cell != null) pairs.push(["League " + gl("DV", "decision_value") + " for the state", signed(r.dv_cell, 4)]);
    if (r.pitcher_name && r.family !== "pitching_change") pairs.push(["Pitcher", esc(r.pitcher_name) + (r.pitcher_hand ? " (" + esc(r.pitcher_hand) + ")" : "")]);
    var win = (r.window || []).map(function (p) {
      return "<tr><td>" + esc(p[0]) + "</td><td>" + esc(p[1]) + "</td><td>" + num(p[2], 1) + "</td><td>" + num(p[3], 1) + "</td></tr>";
    }).join("");
    return '<div class="mgmt-detail" id="mgmt-detail"><button type="button" class="mgmt-detail-close" id="mgmt-close">close</button>' +
      "<h3>" + esc(famLabel(r.family)) + (r.kind && r.kind !== r.family ? ", " + esc(String(r.kind).replace(/_/g, " ")) : "") + (who ? ": " + who : "") + "</h3>" +
      '<div class="mgmt-detail-sub">' + esc(decisionId(r)) + "</div>" + miniTable(pairs) +
      (win ? "<h4>The plays governed</h4>" +
        '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table"><thead><tr><th>PA</th><th>Event</th>' +
        "<th>Home win probability before (feed, %)</th><th>After (%)</th></tr></thead><tbody>" + win + "</tbody></table></div>" : "") +
      "</div>";
  }
  var DCOLS = [
    { key: "date", label: "Date" }, { key: "opp", label: "Game", kind: "game" }, { key: "score_diff", label: "Lead" },
    { key: "inning", label: "Inn", kind: "inn" }, { key: "outs", label: "Outs" }, { key: "base", label: "Bases", kind: "base" },
    { key: "li", label: "LI", nd: 2 }, { key: "family", label: "Family", kind: "fam" }, { key: "kind", label: "Kind", kind: "kind" },
    { key: "in_name", label: "In" }, { key: "out_name", label: "Out" },
    { key: "mwpa", label: "Realized mWPA", kind: "signed", nd: 4 }, { key: "dvs", label: "DVS", kind: "signed", nd: 4 },
    { key: "win_len", label: "Plays" }, { key: "flags", label: "Flags", kind: "flags" }
  ];
  function renderDecisions() {
    var d = DATA.decisions;
    if (!d || !d.live || !ensureClubSeason()) return ledgerDark("Decisions");
    var out = '<section class="mgmt-block">' +
      '<p class="mgmt-lede">' + esc(d.realized_sentence) + "</p>" +
      '<p class="mgmt-agent">' + esc(d.agent_sentence) + "</p>" + controls(true);
    var sh = loadShard();
    if (!sh) return out + shardNote() + "</section>";
    var rows = (sh.rows || []).filter(function (r) { return !state.family || r.family === state.family; });
    var opened = null, openIds = {};
    if (state.game) {
      rows.forEach(function (r) {
        if (r.game_pk === state.game && (state.ab < 0 || r.ab === state.ab)) { openIds[decisionId(r)] = true; if (!opened) opened = r; }
      });
      if (state.open) { rows.forEach(function (r) { if (decisionId(r) === state.open) opened = r; }); }
    }
    var k = state.dsort.key, asc = state.dsort.asc;
    if (k) {
      rows = rows.slice().sort(function (a, b) {
        var x = a[k], y = b[k];
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        if (typeof x === "string") return asc ? x.localeCompare(y) : y.localeCompare(x);
        return asc ? x - y : y - x;
      });
    }
    var head = DCOLS.map(function (c) {
      var arrow = k === c.key ? (asc ? " ▲" : " ▼") : "";
      var tag = c.key === "mwpa" ? ' <span class="mgmt-th-tag">realized</span>' : c.key === "dvs" ? ' <span class="mgmt-th-tag">above state</span>' : "";
      if (c.kind === "flags") return "<th>" + esc(c.label) + "</th>";
      return '<th data-dsort="' + c.key + '" tabindex="0" role="button">' + esc(c.label) + tag + arrow + "</th>";
    }).join("");
    var shown = rows.slice(0, 500);
    var body = shown.map(function (r) {
      var id = decisionId(r);
      return '<tr data-mrow="' + esc(id) + '"' + (openIds[id] || (opened && decisionId(opened) === id) ? ' class="mgmt-row--open"' : "") + ">" +
        DCOLS.map(function (c) {
          var v = r[c.key];
          if (c.kind === "game") return "<td>" + (r.home ? "vs " : "at ") + esc(r.opp || "") + "</td>";
          if (c.kind === "inn") return "<td>" + halfLetter(r.half) + esc(r.inning) + "</td>";
          if (c.kind === "base") return "<td>" + esc(BASE_LABEL[r.base]) + "</td>";
          if (c.kind === "fam") return "<td>" + esc(famLabel(r.family)) + "</td>";
          if (c.kind === "kind") return "<td>" + esc(String(r.kind || "").replace(/_/g, " ")) + "</td>";
          if (c.kind === "signed") return signedCell(v, c.nd);
          if (c.kind === "flags") return "<td>" + (r.flags || []).map(function (f) { return '<span class="mgmt-flag">' + esc(f.replace(/_/g, " ")) + "</span>"; }).join("") + "</td>";
          if (c.nd != null) return "<td>" + num(v, c.nd) + "</td>";
          return "<td>" + (v == null ? "" : esc(v)) + "</td>";
        }).join("") + "</tr>";
    }).join("");
    // data-csv-primary: the CSV control on the mount exports this listing, never
    // an open card's situation or plays table, which are painted above it.
    return out + (opened ? detailCard(opened) : "") +
      '<div class="mgmt-tablewrap mlbstats-scroll"><table class="mgmt-table" data-csv-primary><thead><tr>' + head + "</tr></thead><tbody>" +
      body + "</tbody></table></div>" +
      '<p class="mgmt-count">' + rows.length + " decisions" + (rows.length > 500 ? ", first 500 shown" : "") +
      "; a row opens the plays it governed. " + esc(sh.schema_note ? "" : "") + "</p>" +
      '<p class="mgmt-note">' + esc(((d.families || {})[state.family] || {}).counterfactual_sentence || d.dvs_note) + "</p>" +
      "</section>";
  }

  // ---- dark tabs (Wave B) --------------------------------------------------
  function renderDarkTab(title, blk, extraKeys) {
    blk = blk || {};
    return '<section class="mgmt-block mgmt-dark"><h2>' + esc(title) + ' <span class="mgmt-darktag">not published</span></h2>' +
      '<p class="mgmt-dark-why">Blocked on: ' + esc(blk.blocked_on) + ".</p>" +
      '<p class="mgmt-note">' + esc(blk.why) + "</p>" +
      (extraKeys || []).map(function (k) { return blk[k] ? '<p class="mgmt-note">' + esc(blk[k]) + "</p>" : ""; }).join("") +
      "</section>";
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

  var CSV_SECTIONS = ["gate", "reference", "teams", "bunt", "league", "decisions", "clubs", "managers", "challenges", "lineups"];
  function render() {
    var root = el("mgmt-app-root");
    if (!root) return;
    if (LOAD_ERROR) { root.innerHTML = '<p class="mgmt-note">' + esc(LOAD_ERROR) + "</p>"; return; }
    if (!DATA) { root.innerHTML = '<p class="mgmt-note">Loading.</p>'; return; }
    var s = state.section;
    if (s === "gate") root.innerHTML = renderGate() + renderBlocked();
    else if (s === "reference") root.innerHTML = renderReference();
    else if (s === "teams") root.innerHTML = renderTeams();
    else if (s === "bunt") root.innerHTML = renderBunt();
    else if (s === "league") root.innerHTML = renderLeague();
    else if (s === "decisions") root.innerHTML = renderDecisions();
    else if (s === "clubs") root.innerHTML = renderClubs();
    else if (s === "managers") root.innerHTML = renderManagers();
    else if (s === "challenges") root.innerHTML = renderDarkTab("Challenges", DATA.challenges, ["regime_note", "value_not_observable"]);
    else if (s === "lineups") root.innerHTML = renderDarkTab("Lineups", DATA.lineups, ["value_not_measured"]);
    else root.innerHTML = renderRunning();
    // The CSV control on the mount (build_site's data-csv-export opt-in)
    // exports the table marked data-csv-primary where a section paints more
    // than one (the decision listing, the club page's bullpen deployment),
    // else the first visible table. The file name says which section, and
    // for those two which club-season, it holds.
    try {
      var csvName = "in-game-management-" + (CSV_SECTIONS.indexOf(s) >= 0 ? s : "running");
      if ((s === "decisions" || s === "clubs") && state.team) csvName += "-" + String(state.team).toLowerCase() + "-" + state.cseason;
      root.setAttribute("data-csv-export", csvName);
    } catch (e) { /* the host attribute is a courtesy */ }
    syncTabs();
    wire();
    try { if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(root); } catch (e) { /* glossary optional */ }
  }

  function onSel(id, fn) {
    var s = el(id);
    if (s && s.addEventListener) s.addEventListener("change", function () { fn(this.value); writeHash(); render(); });
  }
  function wire() {
    onSel("mgmt-season", function (v) { state.season = v; });
    onSel("mgmt-bseason", function (v) { state.boardSeason = v; });
    onSel("mgmt-club", function (v) { state.team = v; state.game = 0; state.ab = -1; state.open = ""; ensureClubSeason(); });
    onSel("mgmt-cseason", function (v) { state.cseason = v; state.boardSeason = v; state.game = 0; state.ab = -1; state.open = ""; });
    onSel("mgmt-family", function (v) { state.family = v; state.game = 0; state.ab = -1; state.open = ""; });
    onSel("mgmt-spark", function (v) { state.spark = v; });
    function sortable(attr, sortState, defaultAscKeys) {
      Array.prototype.forEach.call(document.querySelectorAll("th[" + attr + "]"), function (th) {
        function go() {
          var k = th.getAttribute(attr);
          if (sortState.key === k) sortState.asc = !sortState.asc;
          else { sortState.key = k; sortState.asc = defaultAscKeys.indexOf(k) >= 0; }
          render();
        }
        th.addEventListener("click", go);
        th.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
        });
      });
    }
    sortable("data-msort", state.sort, ["team"]);
    sortable("data-bsort", state.boardSort, ["club"]);
    sortable("data-dsort", state.dsort, ["date", "in_name", "out_name", "family", "kind", "opp"]);
    Array.prototype.forEach.call(document.querySelectorAll("tr[data-mrow]"), function (tr) {
      tr.addEventListener("click", function () {
        var id = tr.getAttribute("data-mrow").split(":");
        state.game = parseInt(id[0], 10); state.ab = parseInt(id[1], 10); state.open = tr.getAttribute("data-mrow");
        writeHash(); render();
        try { var dcard = el("mgmt-detail"); if (dcard && dcard.scrollIntoView) dcard.scrollIntoView({ block: "nearest" }); } catch (e) { /* optional */ }
      });
    });
    var close = el("mgmt-close");
    if (close && close.addEventListener) close.addEventListener("click", function () { state.game = 0; state.ab = -1; state.open = ""; writeHash(); render(); });
    // In-page deep links: read the hash and re-render without a reload.
    Array.prototype.forEach.call(document.querySelectorAll("a[data-mlink]"), function (a) {
      a.addEventListener("click", function (e) {
        var href = a.getAttribute("href") || "";
        if (href.indexOf("#") !== 0) return;
        e.preventDefault();
        try { if (typeof history !== "undefined" && history.replaceState) history.replaceState(null, "", href); } catch (err) { /* optional */ }
        state.game = 0; state.ab = -1; state.open = ""; state.family = "";
        readHash();
        render();
        try { if (typeof window !== "undefined" && window.scrollTo) window.scrollTo(0, 0); } catch (err) { /* optional */ }
      });
    });
  }

  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-mgmtsection]"), function (b) {
      b.addEventListener("click", function () {
        state.section = this.getAttribute("data-mgmtsection");
        writeHash();
        render();
      });
    });
    try {
      if (typeof window !== "undefined" && window.addEventListener) {
        window.addEventListener("hashchange", function () { readHash(); render(); });
      }
    } catch (e) { /* optional */ }
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { DATA = d; readHash(); render(); })
      .catch(function () {
        LOAD_ERROR = "The In-Game Management board could not be loaded.";
        render();
      });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
