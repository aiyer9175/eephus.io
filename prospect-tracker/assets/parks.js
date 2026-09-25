/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - MiLB Park Factors (/parks/)
// =============================================================================
// Renders data/milb_park_factors.json (tools/park_line_lab.py) as a sortable
// venue board. 202 venues, sports 11/12/13/14/16, seasons 2021 through the
// live one.
//
// The artifact carries, per venue:
//   seasons[year]        = {run_pf, hr_pf, g_home}   single-season factor
//   window_run_pf[year]  = the 3-season factor as of that year (seasons in
//                          [year-2, year] only, home-game weighted; the lab
//                          builds it vintage-safe so it never peeks forward)
//   window_hr_pf[year]   = same, for home runs
// and, separately, team_seasons[] - one row per club-season, which is where
// the level / league / affiliate labels and the home-game counts come from.
// This file joins the two by venue_id.
//
// The board ranks on the WINDOW only. Single-season factors are in the artifact
// and in each venue's drilldown, but they are not a sortable basis: measured
// here (see stability(), which computes it in the browser off the same numbers
// the page draws) their year-over-year Spearman runs 0.35 to 0.48 on runs,
// under the 0.50 bar the park registration set, while the multi-season
// aggregate clears it. Ranking 200 venues on a number that misses its own
// stability bar would be the page lying quietly, so it does not offer it.
//
// DISPLAY ONLY. No model reads these numbers. The park-line experiment that
// produced them (efv_park_line.py) is flag-gated OFF under a registered fail
// verdict, so nothing on this page moves an eFV, a projection, or a dollar.
// The Method section says so on the page, in the reader's own words.
(function () {
  "use strict";

  var DATA_URL = "/data/milb_park_factors.json";
  var LEVEL_ORDER = ["AAA", "AA", "A+", "A", "CPX", "DSL"];
  var LEVEL_RANK = { AAA: 0, AA: 1, "A+": 2, A: 3, CPX: 4, DSL: 5 };
  var SECTIONS = { board: 1, leagues: 1, method: 1 };

  var DATA = null;
  var LOAD_ERROR = false;
  var VENUE_TS = {};      // venue_id -> {season -> [team_season, ...]}
  var SEASONS = [];       // every season present, descending

  var section = "board";
  var state = {
    season: null,         // selected window vintage (number)
    level: "ALL",
    query: "",
    sort: { key: "run", asc: false },
    open: {}              // venue_id -> drilldown open
  };

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function num(v) { return (v === null || v === undefined || isNaN(v)) ? null : Number(v); }
  // Three decimals, ties AWAY from zero. toFixed() alone inherits the binary
  // representation, so the stored 1.2085 prints as 1.208 (the double sits a
  // hair under the decimal) and the page would disagree with the artifact.
  // The epsilon is ~1e-10 relative at these magnitudes, far under the data's
  // own 4-decimal precision.
  function f2(v) { var n = num(v); return n === null ? "-" : n.toFixed(2); }
  function f3(v) {
    var n = num(v);
    if (n === null) return "-";
    var e = n < 0 ? -1e-7 : 1e-7;
    return (Math.round(n * 1000 + e) / 1000).toFixed(3);
  }
  function fInt(v) { var n = num(v); return n === null ? "-" : String(Math.round(n)); }
  function fPct(v) { var n = num(v); return n === null ? "-" : (n * 100).toFixed(1) + "%"; }
  function chart(fn, arg, opts) {
    try { return (window.EEPHUS_HUB && EEPHUS_HUB[fn]) ? EEPHUS_HUB[fn](arg, opts) : ""; }
    catch (e) { return ""; }
  }
  function uniq(arr) {
    var seen = {}, out = [];
    (arr || []).forEach(function (v) {
      if (v === null || v === undefined || v === "") return;
      if (seen[v]) return;
      seen[v] = 1; out.push(v);
    });
    return out;
  }
  function median(sorted) {
    if (!sorted.length) return null;
    var m = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2;
  }
  function sdev(vals) {
    if (vals.length < 2) return null;
    var mu = 0, i;
    for (i = 0; i < vals.length; i++) mu += vals[i];
    mu /= vals.length;
    var ss = 0;
    for (i = 0; i < vals.length; i++) ss += (vals[i] - mu) * (vals[i] - mu);
    return Math.sqrt(ss / vals.length);
  }

  // ---- index ----------------------------------------------------------------
  function indexData() {
    VENUE_TS = {};
    var years = {};
    ((DATA && DATA.team_seasons) || []).forEach(function (t) {
      var by = VENUE_TS[t.venue_id] || (VENUE_TS[t.venue_id] = {});
      (by[t.season] || (by[t.season] = [])).push(t);
    });
    ((DATA && DATA.venues) || []).forEach(function (v) {
      Object.keys(v.window_run_pf || {}).forEach(function (y) { years[Number(y)] = 1; });
      Object.keys(v.seasons || {}).forEach(function (y) { years[Number(y)] = 1; });
    });
    SEASONS = Object.keys(years).map(Number).sort(function (a, b) { return b - a; });
    if (state.season === null || years[state.season] !== 1) state.season = SEASONS[0] || null;
  }

  // A board row for one venue on the 3-season window ending at `year`, or null
  // when the venue has no games in that window (the artifact simply omits the
  // key, which is the honest answer: a park with no recent games has no recent
  // factor, and we never carry a stale one forward).
  function rowFor(v, year) {
    var span = [year - 2, year];
    var run = num((v.window_run_pf || {})[String(year)]);
    var hr = num((v.window_hr_pf || {})[String(year)]);
    if (run === null) return null;

    var games = 0, nSeasons = 0, y;
    for (y = span[0]; y <= span[1]; y++) {
      var sy = (v.seasons || {})[String(y)];
      if (sy) { games += (sy.g_home || 0); nSeasons++; }
    }
    if (!nSeasons) return null;

    // Labels come from the club-seasons that actually played there, newest
    // season inside the window first.
    var clubs = [], levels = [], leagues = [], latest = null;
    for (y = span[1]; y >= span[0]; y--) {
      var ts = (VENUE_TS[v.venue_id] || {})[y] || [];
      if (ts.length && latest === null) latest = y;
      ts.forEach(function (t) {
        clubs.push(t.team_name); levels.push(t.level); leagues.push(t.league);
      });
    }
    clubs = uniq(clubs); levels = uniq(levels); leagues = uniq(leagues);
    levels.sort(function (a, b) { return (LEVEL_RANK[a] || 9) - (LEVEL_RANK[b] || 9); });

    var latestClubs = uniq(((VENUE_TS[v.venue_id] || {})[latest] || [])
      .map(function (t) { return t.team_name; }));

    return {
      id: v.venue_id,
      venue: v.venue_name || "-",
      clubs: clubs,
      club: latestClubs.length === 1 ? latestClubs[0]
        : (latestClubs.length ? latestClubs.length + " clubs" : "-"),
      shared: clubs.length > 1,
      unnamed: isPooled(v),
      level: levels[0] || "-",
      levels: levels,
      league: leagues.length === 1 ? leagues[0] : (leagues.length ? "mixed" : "-"),
      run: run,
      hr: hr,
      g: games,
      n: nSeasons,
      latest: latest,
      stale: latest !== null && latest < year
    };
  }

  function allRows() {
    var year = state.season, out = [];
    ((DATA && DATA.venues) || []).forEach(function (v) {
      var r = rowFor(v, year);
      if (r) out.push(r);
    });
    return out;
  }

  function filterRows(rows) {
    var q = state.query.trim().toLowerCase();
    return rows.filter(function (r) {
      if (state.level !== "ALL" && r.levels.indexOf(state.level) < 0) return false;
      if (!q) return true;
      if (r.venue.toLowerCase().indexOf(q) >= 0) return true;
      if (r.league.toLowerCase().indexOf(q) >= 0) return true;
      var i;
      for (i = 0; i < r.clubs.length; i++) {
        if (String(r.clubs[i]).toLowerCase().indexOf(q) >= 0) return true;
      }
      return false;
    });
  }

  var COLS = [
    { key: "venue", label: "Venue / affiliate", kind: "venue", text: true },
    { key: "level", label: "Lvl", kind: "level" },
    { key: "league", label: "League", text: true },
    { key: "run", label: "Run PF", num: true,
      title: "Runs scored and allowed at this park vs the same clubs on the road, centered on the league-season and shrunk toward 1.00. Bar reaches full width at 0.75 / 1.25" },
    { key: "hr", label: "HR PF", num: true,
      title: "Home runs at this park (hit plus allowed) vs the same clubs on the road, same centering and shrink. Bar reaches full width at 0.50 / 1.50" },
    { key: "g", label: "Home G", num: true, title: "Home games behind the factor" },
    { key: "n", label: "Sn", num: true, title: "Seasons of home games inside the window" }
  ];

  function sortRows(rows) {
    var key = state.sort.key, asc = state.sort.asc;
    var col = null;
    COLS.forEach(function (c) { if (c.key === key) col = c; });
    var out = rows.slice();
    out.sort(function (a, b) {
      var va, vb;
      if (key === "level") {
        va = (LEVEL_RANK[a.level] === undefined) ? 9 : LEVEL_RANK[a.level];
        vb = (LEVEL_RANK[b.level] === undefined) ? 9 : LEVEL_RANK[b.level];
        return asc ? va - vb : vb - va;
      }
      if (col && col.text) {
        va = String(a[key] || ""); vb = String(b[key] || "");
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      va = num(a[key]); vb = num(b[key]);
      // missing values always sort last, in both directions
      if (va === null && vb === null) return 0;
      if (va === null) return 1;
      if (vb === null) return -1;
      return asc ? va - vb : vb - va;
    });
    return out;
  }

  // ---- cells ----------------------------------------------------------------
  // The bar diverges from a center tick. Each column gets the span that fits
  // its own observed range (run factors live inside +/- 25%, home run factors
  // run roughly twice as wide), so neither column saturates and hides its
  // extremes. The spans are disclosed in the column tooltips, and the number
  // beside the bar is always the real value.
  var RUN_SPAN = 0.25, HR_SPAN = 0.50;

  function facCell(v, span) {
    var n = num(v);
    if (n === null) return '<td class="pk-fac-cell">-</td>';
    var cls = n >= 1.03 ? "pk-hot" : (n <= 0.97 ? "pk-cold" : "pk-flat");
    var fill = n >= 1 ? "pk-fill-hot" : "pk-fill-cold";
    var d = Math.max(-1, Math.min(1, (n - 1) / (span || 0.25)));
    var half = 50 * Math.abs(d);
    var style = n >= 1
      ? "left:50%;width:" + half.toFixed(1) + "%"
      : "right:50%;width:" + half.toFixed(1) + "%";
    return '<td class="pk-fac-cell" data-export-text="' + f3(n) + '">'
      + '<span class="pk-fac">'
      + '<span class="pk-fac-n ' + cls + '">' + f3(n) + "</span>"
      + '<span class="pk-fac-bar" aria-hidden="true">'
      + '<span class="pk-fac-fill ' + fill + '" style="' + style + '"></span>'
      + "</span></span></td>";
  }

  function venueCell(r) {
    var caret = '<span class="pk-caret" aria-hidden="true">'
      + (state.open[r.id] ? "▾" : "▸") + "</span>";
    var flags = "";
    if (r.shared) {
      flags += '<span class="pk-flag" title="' + esc(r.clubs.join(", "))
        + ' share this venue inside the window, so the factor describes the site, not one club">shared</span>';
    }
    if (r.unnamed) {
      flags += '<span class="pk-flag" title="the feed reports no venue for these club-seasons, so this row pools them">pooled</span>';
    }
    if (r.stale) {
      flags += '<span class="pk-flag" title="last home games here were ' + esc(String(r.latest))
        + '; the window still reaches back to them">' + esc(String(r.latest)) + "</span>";
    }
    return '<td class="pk-venue">' + caret
      + '<span class="pk-venue-name">' + esc(r.venue) + "</span>" + flags
      + '<span class="pk-affil">' + esc(r.club) + "</span></td>";
  }

  function detailRow(r, cols) {
    var v = null;
    ((DATA && DATA.venues) || []).forEach(function (x) { if (x.venue_id === r.id) v = x; });
    if (!v) return "";
    var years = Object.keys(v.seasons || {}).map(Number).sort(function (a, b) { return b - a; });
    var body = years.map(function (y) {
      var s = v.seasons[String(y)] || {};
      var ts = (VENUE_TS[r.id] || {})[y] || [];
      var clubs = uniq(ts.map(function (t) { return t.team_name; }));
      var lvl = uniq(ts.map(function (t) { return t.level; })).join(" / ");
      var w = num((v.window_run_pf || {})[String(y)]);
      var wh = num((v.window_hr_pf || {})[String(y)]);
      return "<tr><td>" + y + '</td><td class="pk-mini-club">'
        + esc(clubs.length > 2 ? clubs.length + " clubs" : clubs.join(", ") || "-")
        + "</td><td>" + esc(lvl || "-") + "</td><td>" + fInt(s.g_home) + "</td><td>"
        + f3(s.run_pf) + "</td><td>" + f3(s.hr_pf) + "</td><td>" + f3(w) + "</td><td>"
        + f3(wh) + "</td></tr>";
    }).join("");
    return '<tr class="pk-detail"><td colspan="' + cols + '"><div class="pk-detail-wrap">'
      + '<div class="pk-detail-h">' + esc(r.venue) + " - season by season</div>"
      + '<div class="mlbstats-note">Single seasons are the inputs, shown for audit. They miss the '
      + "stability bar (see Method), so the board sorts on the 3yr columns.</div>"
      + '<table class="pk-mini"><thead><tr><th>Season</th><th>Club</th><th>Lvl</th>'
      + "<th>Home G</th><th>Run PF</th><th>HR PF</th><th>3yr Run</th><th>3yr HR</th>"
      + "</tr></thead><tbody>" + body + "</tbody></table></div></td></tr>";
  }

  // ---- board ----------------------------------------------------------------
  function tiles(rows) {
    if (!rows.length) return "";
    var byRun = rows.slice().sort(function (a, b) { return b.run - a.run; });
    var hot = byRun[0], cold = byRun[byRun.length - 1];
    var hrRows = rows.filter(function (r) { return r.hr !== null; });
    var hrTop = hrRows.slice().sort(function (a, b) { return b.hr - a.hr; })[0];
    var spread = sdev(rows.map(function (r) { return r.run; }));
    function tile(label, val, sub, cls) {
      return '<div class="pk-tile"><div class="pk-tile-label">' + esc(label) + "</div>"
        + '<div class="pk-tile-val ' + (cls || "") + '">' + val + "</div>"
        + '<div class="pk-tile-sub">' + esc(sub) + "</div></div>";
    }
    return '<div class="pk-tiles">'
      + tile("Venues rated", String(rows.length), "3-season window, as of " + state.season)
      + tile("Most offense", f3(hot.run), hot.venue + " (" + hot.level + ")", "pk-hot")
      + tile("Least offense", f3(cold.run), cold.venue + " (" + cold.level + ")", "pk-cold")
      + (hrTop ? tile("Most home runs", f3(hrTop.hr), hrTop.venue + " (" + hrTop.level + ")", "pk-hot") : "")
      + tile("Spread (SD)", spread === null ? "-" : f3(spread), "across the filtered set")
      + "</div>";
  }

  function controls(nShown, nTotal) {
    var seasonOpts = SEASONS.map(function (y) {
      return '<option value="' + y + '"' + (y === state.season ? " selected" : "") + ">" + y + "</option>";
    }).join("");
    var levelBtns = ["ALL"].concat(LEVEL_ORDER).map(function (l) {
      return '<button type="button" class="chip' + (state.level === l ? " active" : "")
        + '" data-pklevel="' + esc(l) + '">' + (l === "ALL" ? "All levels" : esc(l)) + "</button>";
    }).join("");
    return '<div class="mlbstats-bar">'
      + '<label class="filter-label" for="pk-season">Window ending</label>'
      + '<select id="pk-season" aria-label="Window ending season">' + seasonOpts + "</select>"
      + '<span class="pk-count filter-label">' + nShown + " of " + nTotal + " venues</span>"
      + '<input id="pk-search" class="mlbstats-search" type="search" placeholder="venue, club or league"'
      + ' value="' + esc(state.query) + '" aria-label="Search venues">'
      + "</div>"
      + '<div class="filter-bar" role="group" aria-label="Level filter">' + levelBtns + "</div>";
  }

  function viz(rows) {
    if (rows.length < 8) return "";
    var runs = rows.map(function (r) { return r.run; });
    var hist = chart("histogram", runs, {
      height: 120, min: 0.78, max: 1.32, bins: 24,
      refs: [{ at: 1, label: "neutral" }],
      aria: "distribution of run park factors"
    });
    var pts = rows.filter(function (r) { return r.hr !== null; }).map(function (r) {
      return {
        x: r.run, y: r.hr,
        label: r.venue + "  run " + f3(r.run) + "  HR " + f3(r.hr),
        color: (r.run >= 1.05 || r.run <= 0.95) ? null : "var(--text-tertiary)"
      };
    });
    var sc = chart("scatter", pts, {
      height: 250, xLabel: "run factor →", yLabel: "↑ HR factor",
      xRef: 1, yRef: 1, aria: "run factor against home run factor"
    });
    if (!hist && !sc) return "";
    return '<div class="mlbstats-collapse is-collapsed" data-pkcollapse>'
      + '<button type="button" class="mlbstats-collapse-head" aria-expanded="false">'
      + '<span class="mlbstats-collapse-caret" aria-hidden="true"></span>Distribution</button>'
      + '<div class="mlbstats-collapse-body"><div class="mlbstats-viz">'
      + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Run factor, filtered set</div>' + hist + "</div>"
      + '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Runs against home runs</div>' + sc + "</div>"
      + "</div></div></div>";
  }

  function boardTable(rows) {
    var head = "<thead><tr>";
    COLS.forEach(function (c) {
      var sorted = (c.key === state.sort.key) ? " is-sorted" : "";
      var title = c.title ? ' title="' + esc(c.title) + '"' : "";
      var aria = (c.key === state.sort.key) ? (state.sort.asc ? "ascending" : "descending") : "none";
      head += '<th class="pk-col-' + c.key + sorted + '"' + title
        + ' scope="col" tabindex="0" aria-sort="' + aria + '" data-pkcol="' + c.key + '">'
        + esc(c.label) + "</th>";
    });
    head += "</tr></thead>";
    var body = "<tbody>";
    rows.forEach(function (r) {
      body += '<tr class="pk-row' + (state.open[r.id] ? " is-open" : "") + '" data-pkvenue="' + r.id
        + '" tabindex="0" role="button" aria-expanded="' + (state.open[r.id] ? "true" : "false") + '">';
      body += venueCell(r);
      body += "<td><span class=\"pk-lvl\">" + esc(r.level) + "</span></td>";
      body += "<td>" + esc(r.league) + "</td>";
      body += facCell(r.run, RUN_SPAN);
      body += facCell(r.hr, HR_SPAN);
      body += "<td>" + fInt(r.g) + "</td>";
      body += "<td>" + fInt(r.n) + "</td>";
      body += "</tr>";
      if (state.open[r.id]) body += detailRow(r, COLS.length);
    });
    body += "</tbody>";
    return '<table class="mlbstats-table">' + head + body + "</table>";
  }

  function renderBoard() {
    var all = allRows();
    var rows = sortRows(filterRows(all));
    if (!all.length) {
      return controls(0, 0)
        + '<div class="mlbstats-empty">No venue carries a factor for ' + esc(String(state.season))
        + " as a window end.</div>";
    }
    var note = "Three-season factor, " + (state.season - 2) + " to " + state.season
      + ", weighted by home games; venues with no games in that span are omitted. Ranked on "
      + "the window only: single seasons miss the stability bar (see Method).";
    return tiles(rows)
      + controls(rows.length, all.length)
      + '<div class="mlbstats-note">' + esc(note)
      + " Click a row for each season.</div>"
      + viz(rows)
      + (rows.length
          ? '<div class="mlbstats-scroll">' + boardTable(rows) + "</div>"
          : '<div class="mlbstats-empty">No venue matches that filter.</div>');
  }

  // ---- league spread --------------------------------------------------------
  // League MEANS carry no information: the lab centers every league-season on
  // its own mean, so they all sit at 1.00 by construction. What varies, and
  // what a reader can actually use, is the SPREAD - how far apart the parks
  // inside one league are.
  function renderLeagues() {
    var all = allRows();
    var rows = filterRows(all);
    var by = {};
    rows.forEach(function (r) {
      if (r.league === "mixed" || r.league === "-") return;
      var k = r.level + "|" + r.league;
      (by[k] || (by[k] = [])).push(r);
    });
    var groups = Object.keys(by).map(function (k) {
      var g = by[k];
      var runs = g.map(function (r) { return r.run; }).sort(function (a, b) { return a - b; });
      var sorted = g.slice().sort(function (a, b) { return b.run - a.run; });
      return {
        level: k.split("|")[0], league: k.split("|")[1], n: g.length,
        lo: runs[0], hi: runs[runs.length - 1], med: median(runs), sd: sdev(runs),
        hot: sorted[0], cold: sorted[sorted.length - 1]
      };
    }).filter(function (g) { return g.n >= 3; });
    if (!groups.length) {
      return '<div class="mlbstats-empty">Not enough rated venues in any one league for '
        + esc(String(state.season)) + ".</div>";
    }
    groups.sort(function (a, b) { return (b.sd || 0) - (a.sd || 0); });
    var body = groups.map(function (g) {
      return "<tr><td>" + '<span class="pk-lvl">' + esc(g.level) + "</span> " + esc(g.league)
        + "</td><td>" + g.n + "</td>"
        + '<td class="pk-cold">' + f3(g.lo) + "</td><td>" + f3(g.med) + "</td>"
        + '<td class="pk-hot">' + f3(g.hi) + "</td><td>" + f3(g.sd) + "</td>"
        + '<td class="pk-venue">' + esc(g.hot.venue) + "</td>"
        + '<td class="pk-venue">' + esc(g.cold.venue) + "</td></tr>";
    }).join("");
    return controls(rows.length, all.length)
      + '<div class="mlbstats-note">League means are 1.00 by construction (each league-season is '
      + "centered), so the spread is the signal: how much park context varies inside a league. "
      + "Leagues with under three rated venues are dropped.</div>"
      + '<div class="mlbstats-scroll"><table class="mlbstats-table"><thead><tr>'
      + "<th>League</th><th>Venues</th><th>Low</th><th>Median</th><th>High</th><th>SD</th>"
      + "<th>Most offense</th><th>Least offense</th></tr></thead><tbody>"
      + body + "</tbody></table></div>";
  }

  // ---- stability ------------------------------------------------------------
  // Computed IN THE BROWSER off the same artifact the board draws, so the
  // reliability claim on the page can never drift from the numbers on it.
  // Ranks with ties averaged, then Pearson on the ranks (that is Spearman).
  function ranks(xs) {
    var idx = xs.map(function (_v, i) { return i; });
    idx.sort(function (a, b) { return xs[a] - xs[b]; });
    var r = new Array(xs.length), i = 0;
    while (i < idx.length) {
      var j = i;
      while (j + 1 < idx.length && xs[idx[j + 1]] === xs[idx[i]]) j++;
      var avg = (i + j) / 2 + 1;
      for (var k = i; k <= j; k++) r[idx[k]] = avg;
      i = j + 1;
    }
    return r;
  }
  function pearson(a, b) {
    var n = a.length, i, ma = 0, mb = 0;
    if (n < 3) return null;
    for (i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
    ma /= n; mb /= n;
    var num = 0, da = 0, db = 0;
    for (i = 0; i < n; i++) {
      var x = a[i] - ma, y = b[i] - mb;
      num += x * y; da += x * x; db += y * y;
    }
    if (!da || !db) return null;
    return num / Math.sqrt(da * db);
  }
  function spearman(a, b) { return pearson(ranks(a), ranks(b)); }

  // The feed's no-venue bucket (StatsAPI 401 "TBD") is a row, not a park.
  function isPooled(v) { return !v.venue_name || v.venue_name === "TBD"; }

  function stability() {
    // A park's repeatability, so the pooled no-venue row stays out of it.
    var vs = ((DATA && DATA.venues) || []).filter(function (v) { return !isPooled(v); });
    var out = { yoy: [], splitRun: null, splitHr: null, runLo: null, runHi: null };
    SEASONS.slice().sort(function (a, b) { return a - b; }).forEach(function (y) {
      var xs = [], ys = [];
      vs.forEach(function (v) {
        var a = ((v.seasons || {})[String(y)] || {}).run_pf;
        var b = ((v.seasons || {})[String(y + 1)] || {}).run_pf;
        if (a !== undefined && b !== undefined && a !== null && b !== null) { xs.push(a); ys.push(b); }
      });
      if (xs.length >= 20) {
        var rho = spearman(xs, ys);
        out.yoy.push({ pair: y + " to " + (y + 1), n: xs.length, rho: rho });
        if (rho !== null) {
          if (out.runLo === null || rho < out.runLo) out.runLo = rho;
          if (out.runHi === null || rho > out.runHi) out.runHi = rho;
        }
      }
    });
    // Split half: odd seasons against even seasons, each side a home-game
    // weighted mean of that venue's single-season factors. Two independent
    // multi-season aggregates for the same park.
    function half(key) {
      var xs = [], ys = [];
      vs.forEach(function (v) {
        var s = v.seasons || {}, k, aN = 0, aD = 0, bN = 0, bD = 0;
        for (k in s) {
          var e = s[k], val = e[key];
          if (val === undefined || val === null) continue;
          var g = e.g_home || 0;
          if (Number(k) % 2) { aN += val * g; aD += g; } else { bN += val * g; bD += g; }
        }
        if (aD && bD) { xs.push(aN / aD); ys.push(bN / bD); }
      });
      return { n: xs.length, rho: spearman(xs, ys) };
    }
    out.splitRun = half("run_pf");
    out.splitHr = half("hr_pf");
    return out;
  }

  // ---- method ---------------------------------------------------------------
  function observedRanges() {
    var o = { runLo: null, runHi: null, hrLo: null, hrHi: null, sRunLo: null, sRunHi: null };
    function span(v, lo, hi) {
      if (v === null) return [lo, hi];
      return [(lo === null || v < lo) ? v : lo, (hi === null || v > hi) ? v : hi];
    }
    ((DATA && DATA.venues) || []).forEach(function (v) {
      var k;
      for (k in (v.window_run_pf || {})) {
        var a = span(num(v.window_run_pf[k]), o.runLo, o.runHi); o.runLo = a[0]; o.runHi = a[1];
      }
      for (k in (v.window_hr_pf || {})) {
        var b = span(num(v.window_hr_pf[k]), o.hrLo, o.hrHi); o.hrLo = b[0]; o.hrHi = b[1];
      }
      for (k in (v.seasons || {})) {
        var c = span(num(v.seasons[k].run_pf), o.sRunLo, o.sRunHi); o.sRunLo = c[0]; o.sRunHi = c[1];
      }
    });
    return o;
  }

  function renderMethod() {
    var m = (DATA && DATA.method) || {};
    var stop = (DATA && DATA.stop_d) || {};
    var sp = (m.seasons || []);
    var clamps = m.application_clamps || {};
    // Count the pooled no-venue row apart, the glossary's policy.
    var allV = (DATA && DATA.venues) || [];
    var pooledV = allV.filter(isPooled).length;
    var venues = allV.length - pooledV;
    var ts = ((DATA && DATA.team_seasons) || []).length;
    var h = '<div class="pk-prose">';
    // The shrink constant is read out of the artifact's own method string
    // (K_G=<n>) so the formula on the page cannot drift from the one the lab ran.
    var kMatch = /K_G\s*=\s*(\d+)/.exec(String(m.run_pf || ""));
    var kG = kMatch ? kMatch[1] : null;
    h += "<h3>What the number is</h3>";
    h += "<p>Runs per game, scored plus allowed, at the venue by its clubs, divided by the same "
      + "clubs' road rate over the same span, then league-centered and shrunk. Above 1.00 the park "
      + 'adds offense. <a class="g-term" href="/glossary/#g=milb_park_factor" '
      + 'data-gl="milb_park_factor">Glossary entry</a>.</p>';
    h += "<h3>How it is built</h3><ul>"
      + "<li>StatsAPI schedule, regular season, final scores. Sports "
      + esc((m.sports || []).join(", ")) + " (Triple-A through the DSL), seasons "
      + esc(sp.length === 2 ? sp[0] + " through " + sp[1] : sp.join(", ")) + ".</li>"
      + "<li>Each club-season is centered on its league-season mean ratio (pooled sport-season "
      + "when a league is unlabeled or has under four rated clubs).</li>"
      + "<li>Shrunk toward 1.00 by home games"
      + (kG ? ": it keeps G / (G + " + esc(kG) + ") of its raw gap" : "") + ".</li>"
      + "<li>The three-season window is the home-game-weighted mean of the shrunk seasons at or "
      + "before the selected year. It never reads forward.</li>"
      + "<li>Venue = a club's modal home venue. Shared sites are home-game weighted and flagged.</li>"
      + "<li>Home run factors: the league-wide team split fetch (home runs hit plus allowed), same "
      + "centering, shrink and window.</li>"
      + "</ul>";
    // Observed ranges are READ OFF the artifact, never typed into the prose,
    // so a rebuild can never leave this paragraph claiming a stale number.
    var rng = observedRanges();
    h += "<h3>What backs it</h3><ul>"
      + "<li>" + esc(String(venues)) + " venues"
      + (pooledV ? " plus " + esc(String(pooledV)) + " pooled row" + (pooledV === 1 ? "" : "s")
          + " for club-seasons with no reported venue" : "")
      + ", " + esc(String(ts)) + " club-seasons.</li>"
      + "<li>Three-season range: run " + f3(rng.runLo) + " to " + f3(rng.runHi)
      + ", home run " + f3(rng.hrLo) + " to " + f3(rng.hrHi) + ". Single seasons: run "
      + f3(rng.sRunLo) + " to " + f3(rng.sRunHi) + ".</li>"
      + "<li>Run factor coverage " + esc(fInt(stop.covered_run_pf)) + " of "
      + esc(fInt(stop.observed_team_seasons)) + " club-seasons ("
      + esc(fPct(stop.coverage_run_pf)) + ").</li>"
      + "<li>Home run factor coverage " + esc(fInt(stop.covered_hr_pf)) + " of "
      + esc(fInt(stop.observed_team_seasons)) + " club-seasons ("
      + esc(fPct(stop.covered_hr_pf && stop.observed_team_seasons
            ? stop.covered_hr_pf / stop.observed_team_seasons : null))
      + "); an empty split fetch shows a dash.</li>"
      + "<li>Home G on the board is the sample behind each row.</li>"
      + "</ul>";
    // ---- stability, measured on the page ----
    var st = stability();
    var yoyRows = st.yoy.map(function (p) {
      return "<tr><td>" + esc(p.pair) + "</td><td>" + p.n + "</td><td>" + f2(p.rho) + "</td></tr>";
    }).join("");
    h += "<h3>How much of it repeats</h3>";
    h += "<p>Computed in the browser from the table on this page.</p>";
    if (yoyRows) {
      h += '<table class="pk-mini"><thead><tr><th>Consecutive seasons</th><th>Venues</th>'
        + "<th>Run factor Spearman</th></tr></thead><tbody>" + yoyRows + "</tbody></table>";
    }
    h += "<p>Single seasons repeat at " + f2(st.runLo) + " to " + f2(st.runHi)
      + ", under the 0.50 bar in the park registration. Odd against even seasons, each a "
      + "home-game-weighted aggregate, repeat at " + f2(st.splitRun.rho) + " on runs ("
      + st.splitRun.n + " venues) and " + f2(st.splitHr.rho) + " on home runs ("
      + st.splitHr.n + "). <strong>So the board ranks on the three-season window and offers no "
      + "single-season sort.</strong> Per-season inputs stay in each venue's row.</p>";
    h += "<h3>What it is not</h3><ul>"
      + "<li>Not a regression: no control for weather, altitude, roster or schedule beyond the "
      + "home and road split.</li>"
      + "<li>Not a component factor: one run factor and one home run factor.</li>"
      + "<li>Not park-adjusted stats: no player line is rewritten.</li>"
      + "<li>CPX and DSL rows describe shared sites, and one row pools the club-seasons with no "
      + "reported venue. Read them as league context.</li>"
      + "<li>The live season is partial; its window leans on the two seasons behind it.</li>"
      + "</ul>";
    h += '<div class="pk-warn"><strong>Display only.</strong> No model reads these factors. '
      + "Park-neutralizing MiLB lines did not improve eFV, and the lane is a registered fail: "
      + '<code>xfv_park_line</code> in <a href="/glossary/#view=models">Models &amp; Proofs</a>, '
      + 'eval at <a href="/data/xfv_park_line_eval.json">data/xfv_park_line_eval.json</a>. '
      + "The artifact's clamps (run " + esc(f3((clamps.run_pf || [])[0])) + " to "
      + esc(f3((clamps.run_pf || [])[1])) + ", home run " + esc(f3((clamps.hr_pf || [])[0]))
      + " to " + esc(f3((clamps.hr_pf || [])[1]))
      + ") belong to that disabled path; the board shows unclamped values.</div>";
    h += "<h3>The artifact, in its own words</h3>";
    h += '<div class="pk-verbatim">' + esc(String(m.run_pf || "")) + "</div>";
    h += '<div class="pk-verbatim">' + esc(String(m.hr_pf || "")) + "</div>";
    h += '<p class="mlbstats-note">Built by <code>' + esc(String(DATA && DATA.tool || "")) + "</code>"
      + (DATA && DATA.generated_at ? ", generated " + esc(String(DATA.generated_at)) : "") + ".</p>";
    h += "</div>";
    return h;
  }

  // ---- render ---------------------------------------------------------------
  function render() {
    var root = document.getElementById("parks-app-root");
    if (!root) return;
    if (LOAD_ERROR) {
      root.innerHTML = '<div class="state-message is-error">'
        + '<div class="state-message-title">Park factors did not load</div>'
        + '<div class="state-message-body">The venue table lives at <code>/data/milb_park_factors.json</code>. '
        + '<button type="button" class="chip" id="pk-retry">Retry</button></div></div>';
      var rb = document.getElementById("pk-retry");
      if (rb) rb.addEventListener("click", load);
      return;
    }
    if (!DATA) {
      root.innerHTML = '<div class="mlbstats-empty">Loading venues...</div>';
      return;
    }
    root.innerHTML = section === "method" ? renderMethod()
      : (section === "leagues" ? renderLeagues() : renderBoard());
    bind(root);
  }

  function bind(root) {
    var sel = root.querySelector("#pk-season");
    if (sel) sel.addEventListener("change", function () {
      state.season = Number(sel.value); state.open = {}; render();
    });
    var q = root.querySelector("#pk-search");
    if (q) q.addEventListener("input", function () {
      state.query = q.value;
      render();
      // keep typing where the reader left off (the re-render replaces the input)
      var again = document.getElementById("pk-search");
      if (again) { again.focus(); again.setSelectionRange(again.value.length, again.value.length); }
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-pklevel]"), function (b) {
      b.addEventListener("click", function () {
        state.level = b.getAttribute("data-pklevel"); render();
      });
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-pkcol]"), function (th) {
      var key = th.getAttribute("data-pkcol");
      var activate = function () {
        var col = null;
        COLS.forEach(function (c) { if (c.key === key) col = c; });
        if (state.sort.key === key) state.sort.asc = !state.sort.asc;
        else state.sort = { key: key, asc: !!(col && col.text) || key === "level" };
        render();
      };
      th.addEventListener("click", activate);
      th.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        activate();
        // restore keyboard focus to the same header after the re-render
        var again = document.querySelector('.mlbstats-table th[data-pkcol="' + key + '"]');
        if (again) again.focus();
      });
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-pkvenue]"), function (tr) {
      var id = tr.getAttribute("data-pkvenue");
      var toggle = function () {
        if (state.open[id]) delete state.open[id]; else state.open[id] = 1;
        render();
        var again = document.querySelector('[data-pkvenue="' + id + '"]');
        if (again) again.focus();
      };
      tr.addEventListener("click", toggle);
      tr.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        toggle();
      });
    });
    var col = root.querySelector("[data-pkcollapse]");
    if (col) {
      var head = col.querySelector(".mlbstats-collapse-head");
      if (head) head.addEventListener("click", function () {
        var closed = col.classList.toggle("is-collapsed");
        head.setAttribute("aria-expanded", closed ? "false" : "true");
      });
    }
  }

  // ---- section nav / boot ---------------------------------------------------
  function setSection(s) {
    if (!SECTIONS[s]) return;
    section = s;
    Array.prototype.forEach.call(document.querySelectorAll("[data-parksection]"), function (x) {
      var on = x.getAttribute("data-parksection") === s;
      x.classList.toggle("active", on);
      x.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function bindSectionNav() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-parksection]"), function (b) {
      b.addEventListener("click", function () {
        setSection(b.getAttribute("data-parksection"));
        try { history.replaceState(null, "", "#" + section); } catch (e) { /* file:// */ }
        render();
      });
    });
  }

  function readHash() {
    var m = /^#(board|leagues|method)/.exec(location.hash || "");
    if (m) setSection(m[1]);
  }

  function load() {
    LOAD_ERROR = false;
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { DATA = j; indexData(); render(); })
      .catch(function () { DATA = null; LOAD_ERROR = true; render(); });
  }

  function init() {
    bindSectionNav();
    readHash();
    render();
    load();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
