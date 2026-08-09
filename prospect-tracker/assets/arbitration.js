/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026
 *
 * /arbitration/ - the Arbitration Predictor client.
 *
 * Three sections here; the fourth (Model) is server-rendered so the
 * accountability surface is complete with JavaScript off.
 *
 * The scoped stylesheet follows the accountability.js pattern: tokens only,
 * zero literal colours, and a comment justifying each token choice. site.css
 * belongs to another lane.
 */
(function () {
  "use strict";

  var BOARD_URL = "/data/arbitration.json";
  var HIST_URL = "/data/arb_history.json";
  var DASH = " - ";

  /* Flag bits, mirrored from arb_export.py. */
  var F_SERVICE_EST = 1, F_CLASS_EST = 2, F_NO_SALARY = 4,
      F_CARRY_FWD = 8, F_PRORATED = 16;

  var board = null, hist = null;
  var boardErr = false, histErr = false;
  var filters = { cls: "all", team: "all", flag: null };
  var sort = { key: "tot", dir: -1 };

  /* ---------------------------------------------------------------- css */

  var css = document.createElement("style");
  css.textContent = [
    /* NO BORDER-RADIUS ANYWHERE. site.css sets a global
       `*,*::before,*::after{border-radius:0!important}` and this sheet is
       injected after it, so a radius written here would be dead code that
       still reads like intent. */

    /* The caveat bar is a caution rail, not a card, so it borrows the
       .card::before navy spine recoloured to --accent-orange: the token this
       site already spends on "early", never on "defective". */
    ".arb-app .arb-caveatbar{border:1px solid var(--border);border-left:5px solid var(--accent-orange);background:var(--bg-secondary);padding:9px 12px;margin:10px 0 14px}",
    ".arb-app .arb-caveatbar h3{font:700 10px/1.4 var(--font-retro-mono);letter-spacing:.12em;text-transform:uppercase;color:var(--accent-orange);margin:0 0 6px}",
    ".arb-app .arb-caveatbar ul{margin:0;padding-left:16px}",
    ".arb-app .arb-caveatbar li{font-size:12px;line-height:1.6;color:var(--text-secondary);margin:0 0 3px}",
    ".arb-app .arb-caveatn{font-family:var(--font-retro-mono);font-size:10px;color:var(--text-tertiary);margin-left:4px}",

    /* THE LADDER STRIP. Fixed 62px steps rather than content width, so the
       strips column-align down the whole board and a reader can scan "who has
       three years left" without reading a single number. That vertical
       alignment is the entire point of the component; content-width cells
       would destroy it. */
    ".arb-app .arb-ladder{display:grid;grid-auto-flow:column;gap:2px;justify-content:start}",
    ".arb-app .arb-step{display:block;width:62px;padding:2px 4px;text-align:center;border:1px solid var(--border-light)}",
    ".arb-app .arb-step i{display:block;font:700 8px/1.4 var(--font-retro-mono);letter-spacing:.06em;text-transform:uppercase;color:var(--text-tertiary);font-style:normal}",
    ".arb-app .arb-step b{display:block;font:700 11px/1.3 var(--font-retro-mono);color:var(--text-primary)}",
    /* SHAPE, NOT COLOUR, carries every distinction on this strip, so it
       survives a greyscale print. */
    ".arb-app .arb-step--min{border-style:dotted}",
    ".arb-app .arb-step--min b{color:var(--text-tertiary);font-weight:400}",
    ".arb-app .arb-step--est{border-color:var(--accent-orange)}",
    ".arb-app .arb-step--carry{border-top:2px solid var(--accent-orange)}",
    /* The free-agency bookend is what turns three numbers into a story with an
       end. Gold is the terminal accent and it is used exactly once here. */
    ".arb-app .arb-step--fa{border-color:var(--accent-gold);background:var(--bg-tertiary)}",
    ".arb-app .arb-step--fa i{color:var(--text-gold)}",

    /* The two residuals. A 3px rule is a newspaper column rule: whitespace
       reads as layout, a rule reads as a boundary. --accent-navy is the
       institutional hue (it is the header band) and the market residual is a
       claim about the SYSTEM; --accent-cyan is the computed hue and the value
       residual is the computed one. The SIGN rides --up/--down on the number
       itself, a separate channel, so hue answers "which question" and sign
       answers "which direction" without either overwriting the other. */
    ".arb-app .arb-gs{border-left:3px solid var(--border)}",
    ".arb-app th.arb-gs{border-left-color:var(--accent-navy)}",
    ".arb-app .arb-ou{font-family:var(--font-retro-mono);font-weight:700}",
    ".arb-app .arb-oubar{display:block;height:7px;margin-top:2px;background:var(--accent-cyan)}",
    ".arb-app .arb-pos{color:var(--up)}",
    ".arb-app .arb-neg{color:var(--down)}",
    ".arb-app th small{display:block;font:400 8px/1.3 var(--font-retro);letter-spacing:0;text-transform:none;color:var(--text-tertiary)}",

    ".arb-app .arb-flag{display:inline-block;font:700 8px/1.4 var(--font-retro-mono);letter-spacing:.08em;text-transform:uppercase;padding:1px 4px;border:1px solid var(--border);color:var(--text-tertiary);white-space:nowrap}",
    ".arb-app .arb-flag--est{color:var(--accent-orange);border-color:var(--accent-orange)}",
    ".arb-app .arb-scorecard{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:0 0 16px}",
    ".arb-app .arb-tile{border:1px solid var(--border);border-top-width:3px;background:var(--bg-secondary);padding:12px 14px}",
    ".arb-app .arb-tile--green{border-top-color:var(--accent-green)}",
    ".arb-app .arb-tile--orange{border-top-color:var(--accent-orange)}",
    ".arb-app .arb-tile--red{border-top-color:var(--accent-red)}",
    ".arb-app .arb-tile--navy{border-top-color:var(--accent-navy)}",
    ".arb-app .arb-tilen{font:700 26px/1 var(--font-retro-mono);color:var(--text-primary)}",
    ".arb-app .arb-tilelab{font:700 10px/1.4 var(--font-retro-mono);letter-spacing:.1em;text-transform:uppercase;color:var(--text-tertiary);margin:8px 0 0}",
    ".arb-app .arb-tiledef{font-size:11px;line-height:1.5;color:var(--text-secondary);margin:5px 0 0}",
    ".arb-app .arb-note{margin:10px 0}",
    ".arb-app .arb-note p,.arb-app .arb-note li{font-size:12px;line-height:1.6;color:var(--text-secondary)}",
    ".arb-app .arb-row{border:1px solid var(--border);background:var(--bg-secondary);margin:0 0 6px;padding:8px 12px}",
    ".arb-app .arb-sum{cursor:pointer;font:700 12px/1.5 var(--font-retro-mono)}",
    ".arb-app .arb-vd{display:inline-block;font:700 9px/1.4 var(--font-retro-mono);letter-spacing:.1em;padding:1px 5px;border:1px solid var(--border);margin-right:6px}",
    ".arb-app .arb-vd--pass{color:var(--accent-green);border-color:var(--accent-green)}",
    ".arb-app .arb-vd--null{color:var(--accent-orange);border-color:var(--accent-orange)}",
    ".arb-app .arb-row dt{font:700 10px/1.5 var(--font-retro-mono);text-transform:uppercase;letter-spacing:.08em;color:var(--text-tertiary);margin-top:6px}",
    ".arb-app .arb-row dd{margin:0;font-size:12px;color:var(--text-primary)}",
    ".arb-app .arb-losses li{font-size:12px;line-height:1.6;color:var(--text-secondary);margin:0 0 8px}",

    /* On a phone the question is "how many years, how much total". The
       per-year dollar is deferred into title=, not deleted. */
    "@media (max-width:640px){.arb-app .arb-step{width:44px}.arb-app .arb-step b{display:none}.arb-app .arb-ladder{gap:1px}.arb-app th small{display:none}}"
  ].join("");
  document.head.appendChild(css);

  /* ------------------------------------------------------------- helpers */

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* Two-magnitude money, sign BEFORE the $. Missing data is DASH, never a
     dash glyph. */
  function money(usd, dp) {
    var n = Number(usd);
    if (usd == null || !isFinite(n)) return DASH;
    var neg = n < 0, a = Math.abs(n);
    if (a >= 1e9) return (neg ? "-" : "") + "$" + (a / 1e9).toFixed(2) + "B";
    var m = a / 1e6;
    var d = dp == null ? (m >= 100 ? 0 : 1) : dp;
    if (m < 1) return (neg ? "-" : "") + "$" + Math.round(a / 1e3) + "K";
    return (neg ? "-" : "") + "$" + m.toFixed(d) + "M";
  }

  function signed(usd) {
    if (usd == null || !isFinite(Number(usd))) return DASH;
    return (Number(usd) > 0 ? "+" : "") + money(usd);
  }

  function el(id) { return document.getElementById(id); }

  /* --------------------------------------------------------- caveat bar */

  /* Five caveats, each on FOUR surfaces: an inline marker, a filter chip with
     a live count, this bar, and the Model tab. The bar is OPEN by default -
     the inverse of the chart fold - because a chart the reader has not asked
     for should be closed and a caveat they have not asked for is exactly the
     one that has to be visible. */
  function caveats() {
    if (!board) return "";
    var rows = board.rows || [];
    var n = function (bit) {
      var c = 0;
      for (var i = 0; i < rows.length; i++) if ((rows[i].e || 0) & bit) c++;
      return c;
    };
    var items = [];
    var est = n(F_SERVICE_EST);
    if (est) items.push("Arbitration year is reconstructed, not read from published service time, on <b>" + est + "</b> players. Those rows are marked with a tilde." );
    var cls = n(F_CLASS_EST);
    if (cls) items.push("Of those, <b>" + cls + "</b> come from the weakest source, a debut-year and salary-shape heuristic measured at 0.70 agreement against ground truth.");
    var carry = n(F_CARRY_FWD);
    var rules = board.rules || {};
    if (carry) items.push("The collective bargaining agreement expires <b>" + esc(rules.expires || "2026-12-01") + "</b>. Every season from " + esc(String(rules.carry_forward_from || 2027)) + " assumes its arbitration structure survives unchanged. That is not estimated from data and no interval here covers it.");
    items.push("Second-and-later arbitration years are a <b>population multiplier</b>, not a per-player model: the model did not beat one, so the simpler estimator is what ships. Only the first trip is model-driven.");
    items.push("Non-tendered players are absent by construction, so summing a club total <b>overstates</b> what it actually owes.");
    return '<div class="arb-caveatbar"><h3>Read this first</h3><ul><li>' +
           items.join("</li><li>") + "</li></ul></div>";
  }

  /* ------------------------------------------------------------- ladder */

  function ladder(r) {
    var steps = r.l || [];
    var out = [], aria = [];
    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      var yr = s[0], usd = s[1], tok = s[4] || "";
      var pre = tok === "PRE-ARB";
      var cls = "arb-step";
      if (pre) cls += " arb-step--min";
      if ((r.e || 0) & F_SERVICE_EST) cls += " arb-step--est";
      if (yr > 2026) cls += " arb-step--carry";
      var lab = pre ? "MIN" : tok.replace("ARB ", "A").replace(/\s*\(S2\)/, "*");
      var tick = "'" + String(yr).slice(2);
      out.push('<span class="' + cls + '"><i>' + esc(lab) + " " + tick +
               "</i><b>" + money(usd) + "</b></span>");
      aria.push(esc(tok) + ", " + yr + ", " + money(usd));
    }
    /* The free-agency bookend: three dollar figures are data, three ending in
       FA is a story with an end. */
    var last = steps.length ? steps[steps.length - 1][0] : null;
    if (last) {
      out.push('<span class="arb-step arb-step--fa"><i>FA</i><b>&rsquo;' +
               String(last + 1).slice(2) + "</b></span>");
      aria.push("free agent after " + last);
    }
    return '<div class="arb-ladder" role="img" aria-label="' +
           esc(aria.join(". ")) + '">' + out.join("") + "</div>";
  }

  /* ------------------------------------------------- projections board */

  function classLabel(r) {
    var c = r.c;
    if (c == null) return DASH;
    if (c === 0) return "Pre-Arb";
    var s = "Arb " + c;
    if ((r.e || 0) & F_SERVICE_EST) s = "~" + s;
    return s;
  }

  function filtered() {
    var rows = (board && board.rows) || [];
    return rows.filter(function (r) {
      if (filters.team !== "all" && r.t !== filters.team) return false;
      if (filters.cls !== "all" && String(r.c) !== filters.cls) return false;
      if (filters.flag && !((r.e || 0) & filters.flag)) return false;
      return true;
    });
  }

  function renderBoard() {
    var root = el("arb-app-root");
    if (!root) return;
    if (boardErr) {
      root.innerHTML = '<div class="state-message is-error" role="alert">' +
        "Data failed to load. The nightly build may be mid-run." +
        ' <button type="button" id="arb-retry">Retry</button></div>';
      var b = el("arb-retry");
      if (b) b.onclick = function () { boardErr = false; load(); };
      return;
    }
    if (!board) {
      root.innerHTML = '<div class="state-message is-loading">Loading the arbitration board</div>';
      return;
    }
    if (!board.rows || !board.rows.length) {
      root.innerHTML = '<div class="mlbstats-empty">The arbitration board is being computed. ' +
        "It builds off service time, the salary ledger and the projection engine. Check back shortly.</div>";
      return;
    }
    var rows = filtered().slice();
    rows.sort(function (a, b) {
      var x = a[sort.key], y = b[sort.key];
      if (x == null) return 1;
      if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
    });

    var teams = {};
    (board.rows || []).forEach(function (r) { if (r.t) teams[r.t] = 1; });
    var chips = [["all", "All"], ["1", "Arb 1"], ["2", "Arb 2"], ["3", "Arb 3"], ["0", "Pre-Arb"]]
      .map(function (c) {
        return '<button type="button" class="chip' + (filters.cls === c[0] ? " active" : "") +
               '" data-cls="' + c[0] + '">' + c[1] + "</button>";
      }).join("");
    var estN = (board.rows || []).filter(function (r) { return (r.e || 0) & F_SERVICE_EST; }).length;
    chips += '<button type="button" class="chip' + (filters.flag ? " active" : "") +
             '" data-flag="1">Arb year estimated <span class="arb-caveatn">(' + estN + ")</span></button>";
    var opts = ['<option value="all">All clubs</option>'].concat(
      Object.keys(teams).sort().map(function (t) {
        return '<option value="' + esc(t) + '"' + (filters.team === t ? " selected" : "") + ">" + esc(t) + "</option>";
      })).join("");

    var head =
      '<tr><th class="mlbstats-col-rank">#</th><th>Player</th><th>Club</th>' +
      '<th>Class</th><th>Yrs</th><th>Remaining arbitration ladder</th>' +
      '<th data-col="tot">Total remaining<small>sorted</small></th></tr>';
    var body = rows.map(function (r, i) {
      return '<tr><td class="mlbstats-col-rank">' + (i + 1) + "</td>" +
        "<td>" + esc(r.n) + "</td><td>" + esc(r.t || DASH) + "</td>" +
        "<td>" + esc(classLabel(r)) + "</td><td>" + (r.yl == null ? DASH : r.yl) + "</td>" +
        '<td class="arb-laddercell">' + ladder(r) + "</td>" +
        "<td>" + money(r.tot) + "</td></tr>";
    }).join("");

    root.innerHTML = caveats() +
      '<div class="filter-bar">' + chips + ' <select id="arb-team">' + opts + "</select></div>" +
      (rows.length
        ? '<div class="mlbstats-scroll"><table class="mlbstats-table arb-table"><thead>' +
          head + "</thead><tbody>" + body + "</tbody></table></div>"
        : '<div class="mlbstats-empty">No player matches these filters. ' +
          '<button type="button" id="arb-clear">Clear filters</button></div>');

    root.querySelectorAll("[data-cls]").forEach(function (b) {
      b.onclick = function () { filters.cls = b.getAttribute("data-cls"); renderBoard(); };
    });
    root.querySelectorAll("[data-flag]").forEach(function (b) {
      b.onclick = function () { filters.flag = filters.flag ? null : F_SERVICE_EST; renderBoard(); };
    });
    var sel = el("arb-team");
    if (sel) sel.onchange = function () { filters.team = sel.value; renderBoard(); };
    var clr = el("arb-clear");
    if (clr) clr.onclick = function () {
      filters = { cls: "all", team: "all", flag: null }; renderBoard();
    };
  }

  /* ------------------------------------------------------------ history */

  function renderHistory() {
    var root = el("arb-panel-history");
    if (!root) return;
    if (histErr) {
      root.innerHTML = '<div class="state-message is-error" role="alert">' +
        "The history data failed to load.</div>";
      return;
    }
    if (!hist) {
      root.innerHTML = '<div class="state-message is-loading">Loading arbitration history</div>';
      return;
    }
    var rows = hist.rows || [];
    if (!rows.length) {
      root.innerHTML = '<div class="mlbstats-empty">The history is being computed.</div>';
      return;
    }
    var note =
      '<div class="card arb-note"><p><strong>Two different questions, kept apart.</strong> ' +
      "<b>vs Market</b> asks whether the arbitration system paid him more or less than players " +
      "with his case. It is this model&rsquo;s own residual and it sums to roughly zero across the " +
      "league by construction. <b>vs Value</b> asks whether his salary beat his on-field " +
      "production, priced at that winter&rsquo;s dollars per win. It does not sum to zero, because " +
      "arbitration systematically pays less than the open market. Averaging a number centred on " +
      "zero with one that is not gives you neither, so there is no combined column here and none " +
      "may be added.</p>" +
      "<p>A negative residual means this model expected a higher salary than the player received. " +
      "It is a statement about the model, not a statement that the player is underpaid.</p></div>";

    var head = '<tr><th class="mlbstats-col-rank">#</th><th>Season</th><th>Player</th>' +
      "<th>Club</th><th>Arb</th><th>Actual</th><th>Ours</th><th>MLBTR</th>" +
      '<th class="arb-gs">vs Market<small>the system vs comparable players</small></th>' +
      '<th>vs Value<small>salary minus WAR at that winter&rsquo;s price</small></th></tr>';

    var maxOu = 1;
    rows.forEach(function (r) { if (r[9] != null) maxOu = Math.max(maxOu, Math.abs(r[9])); });

    var body = rows.slice(0, 400).map(function (r, i) {
      var ouM = r[8], ouW = r[9];
      var bar = ouW == null ? "" :
        '<span class="arb-oubar" style="width:' +
        Math.round(40 * Math.abs(ouW) / maxOu) + 'px"></span>';
      return "<tr>" +
        '<td class="mlbstats-col-rank">' + (i + 1) + "</td>" +
        "<td>" + r[0] + ((r[11] || 0) & F_PRORATED ? " &dagger;" : "") + "</td>" +
        "<td>" + esc(r[2]) + "</td><td>" + esc(r[3] || DASH) + "</td>" +
        "<td>" + ((r[11] || 0) & F_SERVICE_EST ? "~" : "") + "A" + r[4] + "</td>" +
        "<td>" + money(r[5]) + "</td><td>" + money(r[6]) + "</td><td>" + money(r[7]) + "</td>" +
        '<td class="arb-gs arb-ou ' + (ouM > 0 ? "arb-pos" : "arb-neg") + '">' + signed(ouM) + "</td>" +
        '<td class="arb-ou">' + signed(ouW) + bar + "</td>" +
        "</tr>";
    }).join("");

    root.innerHTML = note +
      '<div class="mlbstats-scroll"><table class="mlbstats-table arb-table"><thead>' +
      head + "</thead><tbody>" + body + "</tbody></table></div>";
  }

  /* ---------------------------------------------------------- team view */

  function renderTeams() {
    var root = el("arb-panel-teams");
    if (!root) return;
    if (!board || !board.rows) {
      root.innerHTML = '<div class="state-message is-loading">Loading</div>';
      return;
    }
    var by = {};
    board.rows.forEach(function (r) {
      if (!r.t) return;
      var t = by[r.t] || (by[r.t] = { t: r.t, n: 0, tot: 0, next: 0 });
      t.n++;
      t.tot += r.tot || 0;
      if (r.l && r.l.length && r.l[0][1]) t.next += r.l[0][1];
    });
    var rows = Object.keys(by).map(function (k) { return by[k]; });
    rows.sort(function (a, b) { return b.tot - a.tot; });
    var body = rows.map(function (t, i) {
      return '<tr><td class="mlbstats-col-rank">' + (i + 1) + "</td><td>" + esc(t.t) +
        "</td><td>" + t.n + "</td><td>" + money(t.next) + "</td><td>" + money(t.tot) + "</td></tr>";
    }).join("");
    root.innerHTML =
      '<div class="card arb-note"><p>What each club still owes the players it controls through ' +
      "arbitration. Non-tendered players are absent by construction, so these totals are an " +
      "<strong>upper bound</strong> on the obligation, not a payroll forecast.</p></div>" +
      '<div class="mlbstats-scroll"><table class="mlbstats-table arb-table"><thead><tr>' +
      '<th class="mlbstats-col-rank">#</th><th>Club</th><th>Arb-eligible</th>' +
      "<th>Next season</th><th>Total remaining</th></tr></thead><tbody>" + body +
      "</tbody></table></div>";
  }

  /* -------------------------------------------------------------- boot */

  function show(which) {
    ["projections", "history", "teams", "model"].forEach(function (k) {
      var panel = el("arb-panel-" + k);
      if (panel) panel.hidden = k !== which;
    });
    document.querySelectorAll("[data-arbsection]").forEach(function (b) {
      var on = b.getAttribute("data-arbsection") === which;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (which === "history" && !hist && !histErr) loadHistory();
    if (which === "history") renderHistory();
    if (which === "teams") renderTeams();
    try { location.hash = "#" + which; } catch (e) { /* hash is optional */ }
  }

  function loadHistory() {
    /* Lazily fetched on first open: it is the bigger payload and most visits
       never open it. Its own error state, so a history failure cannot read as
       a board failure. */
    fetch(HIST_URL, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    }).then(function (d) { hist = d; renderHistory(); })
      .catch(function () { histErr = true; renderHistory(); });
  }

  function load() {
    renderBoard();
    fetch(BOARD_URL, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    }).then(function (d) { board = d; renderBoard(); })
      .catch(function () { boardErr = true; renderBoard(); });
  }

  function init() {
    document.querySelectorAll("[data-arbsection]").forEach(function (b) {
      b.onclick = function () { show(b.getAttribute("data-arbsection")); };
    });
    var h = (location.hash || "").replace("#", "");
    load();
    if (h === "history" || h === "teams" || h === "model") show(h);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
