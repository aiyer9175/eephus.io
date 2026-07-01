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
  function fInt(v) { var n = num(v); return n == null ? "-" : String(Math.round(n)); }
  function f1(v) { var n = num(v); return n == null ? "-" : n.toFixed(1); }
  function f2(v) { var n = num(v); return n == null ? "-" : n.toFixed(2); }
  function fPct(v) { var n = num(v); return n == null ? "-" : (n * 100).toFixed(1) + "%"; }
  function fSigned(v) { var n = num(v); if (n == null) return "-"; return (n > 0 ? "+" : "") + n.toFixed(1); }
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
      return { x: r.rem_plus, y: r.gmli, label: r.name + "  REM+ " + r.rem_plus + "  gmLI " + r.gmli,
               color: r.rem_plus >= 115 ? null : "#6a6f7a" };
    });
    var sc = chart("scatter", pts, { height: 250, xLabel: "REM+ (skill) →", yLabel: "↑ gmLI (leverage)",
      xRef: 100, yRef: 1, aria: "skill vs leverage" });
    if (!hist && !sc) return "";
    return '<div class="mlbstats-viz">'
      + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">' + gloss("REM+", "rem_plus")
      + ' distribution <span class="proj-dim">(qualified relievers; cyan = elite)</span></div>' + hist + "</div>"
      + (sc ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Skill vs leverage'
        + ' <span class="proj-dim">(top-right = elite arms in high leverage)</span></div>' + sc + "</div>" : "")
      + "</div>";
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
  function gloss(label, term) {
    return '<span class="g-term" data-gl="' + esc(term) + '">' + esc(label) + "</span>";
  }
  function wireGlossary(el) {
    try { if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(el); } catch (e) { /* glossary optional */ }
  }

  // ---- column definitions (Relievers) --------------------------------------
  // Skill core first, then the Impact/leverage columns (kept distinct from the
  // REM+ talent number by design).
  var REL_COLS = [
    { key: "name", label: "Reliever", term: null, sortable: true, kind: "name" },
    { key: "rem_plus", label: "REM+", term: "rem_plus", fmt: remCell, num: true, desc: true, isRem: true },
    { key: "ip", label: "IP", fmt: f1, num: true },
    { key: "g", label: "G", fmt: fInt, num: true },
    { key: "k_pct", label: "K%", fmt: fPct, num: true },
    { key: "bb_pct", label: "BB%", fmt: fPct, num: true },
    { key: "k_bb_pct", label: "K-BB%", fmt: fPct, num: true },
    { key: "fip", label: "FIP", fmt: f2, num: true, asc: true },
    { key: "swstr_pct", label: "SwStr%", fmt: fPct, num: true },
    { key: "era", label: "ERA", fmt: f2, num: true, asc: true },
    { key: "gmli", label: "gmLI", term: "gmli", fmt: f2, num: true },
    { key: "wpa", label: "WPA", term: "wpa", fmt: fSigned, num: true },
    { key: "wpa_li", label: "WPA/LI", term: "wpa_li", fmt: fSigned, num: true },
    { key: "sd_md", label: "SD-MD", term: "shutdowns_meltdowns", fmt: fInt, num: true,
      get: function (r) { var sd = num(r.sd), md = num(r.md); return (sd == null && md == null) ? null : (sd || 0) - (md || 0); } },
  ];

  var TEAM_COLS = [
    { key: "team", label: "Team", sortable: true, kind: "team" },
    { key: "bullpen_plus", label: "Bullpen+", term: "bullpen_plus", fmt: remCell, num: true, desc: true, isRem: true },
    { key: "leverage_deploy_plus", label: "Lev Deploy+", term: "bullpen_plus", fmt: remCell, num: true },
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
  var view = "relievers";          // relievers | teams | depth
  var relSort = { key: "rem_plus", asc: false };
  var teamSort = { key: "bullpen_plus", asc: false };
  var query = "";
  var qualifiedOnly = true;

  function getVal(col, row) {
    if (col.get) return col.get(row);
    return row[col.key];
  }

  // ---- render: shared table -------------------------------------------------
  function renderTable(rows, cols, sort, onSort) {
    var head = "<thead><tr>";
    cols.forEach(function (c) {
      var sorted = (c.key === sort.key) ? " is-sorted" : "";
      var lbl = c.term ? gloss(c.label, c.term) : esc(c.label);
      head += '<th class="mlbstats-col-' + c.key + sorted + '" data-col="' + c.key + '">' + lbl + "</th>";
    });
    head += "</tr></thead>";

    var body = "<tbody>";
    rows.forEach(function (r) {
      var prov = (r.qualified === false) ? " is-provisional" : "";
      body += "<tr" + prov + ">";
      cols.forEach(function (c) {
        if (c.kind === "name") { body += nameCell(r); return; }
        if (c.kind === "team") { body += '<td class="mlbstats-name">' + logo(r.team) + esc(r.team || "-") + "</td>"; return; }
        if (c.cell) { body += "<td>" + c.cell(r) + "</td>"; return; }
        var v = getVal(c, r);
        var rendered = c.fmt ? c.fmt(v, c.term) : esc(v);
        body += "<td>" + rendered + "</td>";
      });
      body += "</tr>";
    });
    body += "</tbody>";
    return '<table class="mlbstats-table">' + head + body + "</table>";
  }

  function nameCell(r) {
    var role = r.role ? ' <span class="bp-role">' + esc(r.role) + "</span>" : "";
    var team = r.team ? '<span class="proj-dim"> ' + esc(r.team) + "</span>" : "";
    var prov = (r.qualified === false) ? '<span class="bp-prov" title="below the qualifying sample - shown but provisional">prov</span>' : "";
    return '<td class="mlbstats-name">' + logo(r.team) + esc(r.name || "-") + team + role + prov + "</td>";
  }

  function sortRows(rows, cols, sort) {
    var col = null;
    cols.forEach(function (c) { if (c.key === sort.key) col = c; });
    if (!col) return rows.slice();
    var out = rows.slice();
    out.sort(function (a, b) {
      var va = getVal(col, a), vb = getVal(col, b);
      va = (va == null || isNaN(va)) ? -Infinity : Number(va);
      vb = (vb == null || isNaN(vb)) ? -Infinity : Number(vb);
      return sort.asc ? va - vb : vb - va;
    });
    return out;
  }

  // ---- views ----------------------------------------------------------------
  function filteredRelievers() {
    var rows = (DATA && DATA.relievers) || [];
    var q = query.trim().toLowerCase();
    return rows.filter(function (r) {
      if (qualifiedOnly && r.qualified === false) return false;
      if (!q) return true;
      return (String(r.name || "").toLowerCase().indexOf(q) >= 0
        || String(r.team || "").toLowerCase().indexOf(q) >= 0);
    });
  }

  function renderRelievers() {
    var rows = sortRows(filteredRelievers(), REL_COLS, relSort);
    if (!rows.length) return '<div class="mlbstats-empty">No relievers match the current filters.</div>';
    var note = '<div class="mlbstats-note">' + rows.length + " relievers. "
      + gloss("REM+", "rem_plus") + " is pure run-prevention skill (100 = average reliever); "
      + "gmLI / WPA / WPA-LI / SD-MD are the leverage context, kept separate.</div>";
    return scorecard() + relieverViz() + note + '<div class="mlbstats-scroll">' + renderTable(rows, REL_COLS, relSort) + "</div>";
  }

  function renderTeams() {
    var rows = (DATA && DATA.teams) || [];
    rows = sortRows(rows, TEAM_COLS, teamSort);
    if (!rows.length) return '<div class="mlbstats-empty">No team bullpens to show yet.</div>';
    var note = '<div class="mlbstats-note">' + gloss("Bullpen+", "bullpen_plus")
      + " weights each pen by the quality of the relief innings it throws (relief-IP-weighted REM+); "
      + "Lev Deploy+ adds how much leverage those innings carry.</div>";
    return note + '<div class="mlbstats-scroll">' + renderTable(rows, TEAM_COLS, teamSort) + "</div>";
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
    if (!teams.length) return '<div class="mlbstats-empty">No bullpen depth charts to show yet.</div>';
    var sorted = teams.slice().sort(function (a, b) { return (num(b.bullpen_plus) || 0) - (num(a.bullpen_plus) || 0); });
    var cards = sorted.map(function (t) {
      var slots = teamDepth(t).map(function (r) {
        return '<div class="bp-slot">'
          + '<span class="bp-slot-role">' + esc(r.role || "-") + "</span>"
          + '<span class="bp-slot-name">' + esc(r.name || "-")
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
  function banner() {
    if (!DATA) return "";
    var bits = [];
    if (DATA.season) bits.push("Season " + esc(DATA.season));
    if (DATA.as_of) bits.push("through " + esc(DATA.as_of));
    if (DATA.coverage && DATA.coverage.games != null) {
      var cov = DATA.coverage;
      bits.push(esc(cov.games) + (cov.expected ? " / " + esc(cov.expected) : "") + " games of play-by-play");
    }
    if (DATA.verdict === "validated") {
      bits.push('<span class="bp-validated" title="Backtested out of sample - see the REM+ scorecard below">backtested</span>');
    } else if (DATA.verdict) {
      bits.push('<span class="bp-prov" style="margin-left:0">' + esc(DATA.verdict) + "</span>");
    }
    if (!bits.length) return "";
    return '<div class="mlbstats-note">' + bits.join(" &middot; ") + "</div>";
  }

  // REM+ accountability scorecard - mirrors PAL's pattern so a validated model
  // surfaces its out-of-sample backtest to users, not just a status word.
  function scorecard() {
    var b = (DATA && DATA.backtest) || {};
    if (b.rho_rem_plus == null) return "";
    return '<div class="mlbstats-scorecard">'
      + '<span class="pal-sc-stat">' + gloss("REM+", "rem_plus") + ' forward &rho; <b>'
      + b.rho_rem_plus + '</b><span class="proj-dim"> vs FIP ' + (b.rho_fip == null ? "-" : b.rho_fip)
      + ", ERA " + (b.rho_era == null ? "-" : b.rho_era) + "</span></span>"
      + '<span class="pal-sc-stat"><b>' + esc(b.n_pairs) + "</b> out-of-sample year pairs"
      + (b.seasons ? '<span class="proj-dim"> (' + esc(b.seasons) + " seasons)</span>" : "") + "</span>"
      + (b.market_rho == null ? "" : '<span class="pal-sc-stat">market fit &rho; <b>' + b.market_rho + '</b><span class="proj-dim"> vs AAV</span></span>')
      + '<span class="pal-sc-note">' + esc(b.disclaimer || "") + "</span>"
      + "</div>";
  }

  function tabBar() {
    var tabs = [["relievers", "Relievers"], ["teams", "Team Bullpens"], ["depth", "Depth Charts"]];
    return '<div class="mlbstats-tabs" role="tablist">' + tabs.map(function (t) {
      var active = (t[0] === view) ? " active" : "";
      return '<button type="button" class="mlbstats-tab' + active + '" data-mlbview="' + t[0] + '" role="tab" aria-selected="' + (t[0] === view) + '">' + t[1] + "</button>";
    }).join("") + "</div>";
  }

  function controls() {
    if (view !== "relievers") return "";
    return '<div class="mlbstats-bar">'
      + '<label style="font-size:11px;color:var(--text-tertiary);display:inline-flex;gap:5px;align-items:center;">'
      + '<input type="checkbox" id="mlbstats-qual"' + (qualifiedOnly ? " checked" : "") + "> qualified only</label>"
      + '<input class="mlbstats-search" type="search" id="mlbstats-q" placeholder="Search reliever or team" value="' + esc(query) + '">'
      + "</div>";
  }

  function render() {
    var root = document.getElementById("mlbstats-app-root");
    if (!root) return;
    if (!DATA) {
      root.innerHTML = '<div class="mlbstats-empty">Bullpen Leaderboards are being computed from MLB play-by-play. '
        + "Check back shortly.</div>";
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
    root.querySelectorAll("[data-mlbview]").forEach(function (b) {
      b.addEventListener("click", function () {
        view = b.getAttribute("data-mlbview");
        try { history.replaceState(null, "", "#view=" + view); } catch (e) { /* hash optional */ }
        render();
      });
    });
    var q = root.querySelector("#mlbstats-q");
    if (q) q.addEventListener("input", function () { query = q.value; renderInPlace(); });
    var qual = root.querySelector("#mlbstats-qual");
    if (qual) qual.addEventListener("change", function () { qualifiedOnly = qual.checked; renderInPlace(); });
    root.querySelectorAll(".mlbstats-table th[data-col]").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-col");
        var cols = (view === "teams") ? TEAM_COLS : REL_COLS;
        var col = null; cols.forEach(function (c) { if (c.key === key) col = c; });
        if (!col || (!col.num && col.kind !== "name" && col.kind !== "team")) return;
        var sort = (view === "teams") ? teamSort : relSort;
        if (sort.key === key) sort.asc = !sort.asc;
        else { sort.key = key; sort.asc = !!col.asc; }
        render();
      });
    });
  }

  // Re-render only the table region (keeps search-box focus on input).
  function renderInPlace() {
    var root = document.getElementById("mlbstats-app-root");
    if (!root) return;
    var inner = (view === "teams") ? renderTeams() : (view === "depth") ? renderDepth() : renderRelievers();
    // Replace everything after the controls bar.
    var tabsHtml = tabBar();
    var ctrlHtml = controls();
    root.innerHTML = tabsHtml + ctrlHtml + inner;
    // restore focus + caret to the search field
    var q = root.querySelector("#mlbstats-q");
    if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
    bindEvents(root);
    wireGlossary(root);
  }

  function readHash() {
    var m = /view=(relievers|teams|depth)/.exec(location.hash || "");
    if (m) view = m[1];
  }

  function init() {
    readHash();
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { DATA = j; render(); })
      .catch(function () { DATA = null; render(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
