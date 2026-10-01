/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - Club Ledger (/ledger/)
// =============================================================================
// Renders data/ledger_board.json (ledger_export.py): what each club has on the
// books, what it owes, what it controls, and what the platform's own prices say
// each dollar buys. A LEDGER, not a forecast and not an income statement.
//
// THREE RULES THIS FILE KEEPS.
//   1. No single projected payroll. The commitments block draws three labelled
//      segments per season (contract dollars on file, projected arbitration
//      steps, pre-arbitration minimums by rule) beside the count of vets with
//      no price, and nothing here adds the three into one printed number.
//   2. Only an INDEX takes a colour. Cost+, OrgSur+ and the fin_* score_100
//      leaves are 100+10z indexes and take the `z` ladder from EephusTiers. A
//      salary cell, a club surplus total and a cap-space cell print plain; the
//      only colour a dollar figure carries is its sign. The contract ledger and
//      the commitments renderers make no ruler call at all.
//   3. ou_mkt and ou_war stay in separate columns with separate totals; the
//      artifact says never_combine and nothing here adds or averages them.
//
// NOT ONE FIGURE IN THIS FILE IS TYPED. Every number, label basis and sentence
// comes out of the payload's own `copy`, `field_key` and per-club blocks. The
// one thing this file decides for itself is which dollar cell gets a sign
// colour, and the answer is: the ones that can go negative.
//
// THE DEPTH PASS (D5, 2026-09-24). The board carries a preview of each row
// layer; the full rows live in /data/ledger_clubs/CODE.json and are fetched
// once per club after the club page paints (ensureShard). Since 2026-09-30 the
// club's snapshot series (trade currency, actives, per prospect) ride in the
// same file, so the sparklines draw once it is in. Every row array is
// indexed through the board's `columns` legend (colIdx / cv), never by a
// positional guess. Three more rules ride the new blocks:
//   4. A band (p10/p90, lo/hi) prints on its row and the footer under a band
//      column reads "not summed". Sums are sums of expected values, labelled
//      "shown rows" when a filter applies.
//   5. A per-prospect surplus cell, a rung, a trade value and a strip cell
//      print plain with a sign only; a grade letter prints in neutral ink.
//   6. The Swartz figure is a third quantity beside ou_mkt and ou_war, never a
//      residual; no award quantile sits beside an arbitration figure.
(function () {
  "use strict";

  var DATA_URL = "/data/ledger_board.json";
  var SHARD_URL = "/data/ledger_clubs/";
  var DATA = null;
  var SHARDS = {};          // code -> the club's row file once fetched (a revisit is free)
  var SHARD_STATE = {};     // code -> "loading" | "ready" | "failed"
  var SCROLLED = "";        // team:block already scrolled to from the hash
  var LOAD_ERROR = "";
  var SECTIONS = ["league", "club", "rules", "method"];
  var BLOCKS = ["payroll", "cbt", "commitments", "contracts", "arbitration", "surplus", "farm", "fa", "prospects", "graduates", "trade"];
  var state = { section: "league", team: "", season: "", block: "",
                sort: { key: "cbt_payroll_2026", asc: false }, open: {}, pfilter: "all" };

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isNum(v) { return v !== null && v !== undefined && v === v && v !== ""; }
  function num(v, nd) { return isNum(v) ? Number(v).toFixed(nd === undefined ? 1 : nd) : ""; }
  function pct(v, nd) { return isNum(v) ? (Number(v) * 100).toFixed(nd === undefined ? 1 : nd) + "%" : ""; }
  // usd -> "$12.3M" / "-$4.1M". One decimal, never re-based.
  function money(usd) {
    if (!isNum(usd)) return "";
    var v = Number(usd) / 1e6;
    return (v < 0 ? "-" : "") + "$" + Math.abs(v).toFixed(1) + "M";
  }
  function moneyMM(mm) { return isNum(mm) ? (mm < 0 ? "-" : "") + "$" + Math.abs(Number(mm)).toFixed(1) + "M" : ""; }
  function usdFull(usd) { return isNum(usd) ? "$" + Math.round(Number(usd)).toLocaleString("en-US") : ""; }
  function el(id) { return document.getElementById(id); }
  function gl(label, id) {
    return '<a class="g-term" href="/glossary/#g=' + esc(id) + '" data-gl="' + esc(id) + '">' + esc(label) + "</a>";
  }
  function copy(k) { return (DATA && DATA.copy && DATA.copy[k]) || ""; }
  // Sign colour on a dollar figure that can go negative. Never a ladder.
  function signCls(v) {
    if (!isNum(v) || Number(v) === 0) return "";
    return Number(v) > 0 ? "ledger-pos" : "ledger-neg";
  }
  function signedMoney(usd) { return '<span class="' + signCls(usd) + '">' + money(usd) + "</span>"; }
  // A distance past a line that costs money (the overage above the tax
  // threshold) takes the house sign for a COST: over is red, under is green,
  // the convention the League column's negative "vs threshold" cell already
  // uses. The magnitude prints unsigned; the word beside it says over or under.
  function costMoney(usd) {
    return '<span class="' + signCls(isNum(usd) ? -Number(usd) : null) + '">' + (isNum(usd) ? money(Math.abs(Number(usd))) : "") + "</span>";
  }
  function overUnder(usd) { return isNum(usd) && Number(usd) < 0 ? "Under by " : "Over by "; }
  // The ONE ruler call site. A 100+10z index on the `z` ladder, family named.
  function zCls(v) {
    try {
      if (typeof EephusTiers !== "undefined" && EephusTiers && EephusTiers.cls) return EephusTiers.cls(v, "z");
    } catch (e) { /* ruler optional */ }
    return "";
  }
  function zCell(v) {
    return '<span class="' + zCls(v) + '">' + (isNum(v) ? Math.round(Number(v)) : "") + "</span>";
  }
  function flag(txt) { return txt ? '<span class="ledger-flag">' + esc(txt) + "</span>" : ""; }
  function dark(title, why) {
    return '<div class="ledger-dark"><div><strong>' + esc(title) + '</strong><span class="ledger-darktag">dark</span></div>' +
      '<div class="ledger-dark-why">' + esc(why) + "</div></div>";
  }
  function banner() { return '<div class="ledger-banner" role="note">' + esc(copy("cba_banner")) + "</div>"; }
  // ---- the depth pass's row plumbing ------------------------------------------
  // Every row array is read through the board's `columns` legend: a legend edit
  // and a renderer edit cannot drift apart, and a nested form ("[[season, ...]]",
  // "war[5]") is one column holding an array, never a bracket parse of prose.
  function colIdx(key, name) {
    var cols = (DATA && DATA.columns && DATA.columns[key]) || [];
    return cols.indexOf(name);
  }
  function cv(key, row, name) {
    var i = colIdx(key, name);
    return (i < 0 || !row) ? undefined : row[i];
  }
  function shardOf(code) { return SHARDS[code] || null; }
  function shardFailed(code) { return SHARD_STATE[code] === "failed"; }
  // Fetch the club's row file once, after the club page has painted from the
  // board; a file whose club is not the one asked for is treated as failed, a
  // file from another board build is flagged and never refused.
  function ensureShard(code) {
    if (!code || SHARDS[code] || SHARD_STATE[code] === "loading" || SHARD_STATE[code] === "failed") return;
    SHARD_STATE[code] = "loading";
    try {
      fetch(SHARD_URL + code + ".json", { cache: "no-cache" })
        .then(function (r) { if (!r || !r.ok) return null; return r.json(); })
        .then(function (s) {
          if (s && s.club === code) {
            s.vintage_mismatch = !!(DATA && s.board_generated_at !== DATA.generated_at);
            SHARDS[code] = s;
            SHARD_STATE[code] = "ready";
          } else {
            SHARD_STATE[code] = "failed";
          }
          render();
        })
        .catch(function () { SHARD_STATE[code] = "failed"; render(); });
    } catch (e) { SHARD_STATE[code] = "failed"; }
  }
  // A grade letter or tier token copied from the artifact: neutral ink, never
  // a ruler class (R7).
  function letter(g) { return isNum(g) || g ? '<span class="ledger-letter">' + esc(g) + "</span>" : ""; }
  function yn(v, label) { return v ? '<span class="ledger-flag">' + esc(label) + "</span>" : ""; }
  function signedMM(mm) { return '<span class="' + signCls(mm) + '">' + moneyMM(mm) + "</span>"; }
  function bandMM(lo, hi, title) {
    if (!isNum(lo) && !isNum(hi)) return "";
    return '<span class="ledger-band" title="' + esc(title || "") + '">' + esc(moneyMM(lo)) + " to " + esc(moneyMM(hi)) + "</span>";
  }
  function notSummed() { return '<span class="ledger-notsum">' + esc(copy("not_summed")) + "</span>"; }
  function xpBtn(k) {
    var open = !!state.open[k];
    return '<td class="lc-xp"><button type="button" class="ledger-xp-btn" data-lxp="' + esc(k) + '" aria-expanded="' + (open ? "true" : "false") + '">' + (open ? "&minus;" : "+") + "</button></td>";
  }
  function dd(label, html) { return "<dt>" + esc(label) + "</dt><dd>" + (html || "") + "</dd>"; }
  function pctStr(rate) { return isNum(rate) ? (Number(rate) * 100).toFixed(0) + " pct" : ""; }
  // The line above every shard-fed block: the preview note before the rows
  // arrive, the dark line when the fetch failed, the vintage flag when the
  // file was written against another board build.
  function shardLine(code, previewNote) {
    var s = shardOf(code);
    if (s) return s.vintage_mismatch ? '<p class="ledger-count">' + flag(copy("shard_vintage")) + "</p>" : "";
    if (shardFailed(code)) return dark("Per-club rows", copy("shard_failed"));
    return '<p class="ledger-count">' + esc(previewNote || copy("preview_note")) + "</p>";
  }
  function clubOf(code) { return DATA && DATA.clubs ? DATA.clubs[code] : null; }
  function clubs() { return DATA ? Object.keys(DATA.clubs).sort() : []; }
  function opt(v, label, cur) {
    return '<option value="' + esc(v) + '"' + (String(v) === String(cur) ? " selected" : "") + ">" + esc(label) + "</option>";
  }
  function seasonNow() { return String(DATA.season_now); }
  function classYear() { return String(DATA.class_year); }
  function ensureTeam() {
    if (!state.team || !clubOf(state.team)) state.team = clubs()[0] || "";
    if (!state.season) state.season = seasonNow();
  }

  // ---- hash router (mlbstats idiom: every key anchored to a separator) ------
  var SECTION_RE = /(?:^#|[#&])section=(league|club|rules|method)\b/;
  var TEAM_RE = /(?:^#|[#&])team=([A-Z]{2,3})\b/;
  var SEASON_RE = /(?:^#|[#&])season=(20\d\d)\b/;
  var BLOCK_RE = /(?:^#|[#&])block=(payroll|cbt|commitments|contracts|arbitration|surplus|farm|fa|prospects|graduates|trade)\b/;
  function hashNow() {
    try { return (typeof location !== "undefined" && location.hash) || ""; } catch (e) { return ""; }
  }
  function readHash() {
    var h = hashNow();
    var s = SECTION_RE.exec(h);
    if (s) state.section = s[1];
    var t = TEAM_RE.exec(h);
    // Trusted only when it is a key of payload.clubs, so a hash can never
    // resolve a club off Object.prototype.
    if (t && DATA && Object.prototype.hasOwnProperty.call(DATA.clubs, t[1])) {
      state.team = t[1];
      if (!s) state.section = "club";
    }
    var y = SEASON_RE.exec(h);
    if (y && DATA && (y[1] === seasonNow() || y[1] === classYear())) state.season = y[1];
    var b = BLOCK_RE.exec(h);
    if (b) state.block = b[1];
  }
  function writeHash() {
    var parts = ["section=" + state.section];
    if (state.section === "club" && state.team) {
      parts.push("team=" + state.team);
      if (state.season && state.season !== seasonNow()) parts.push("season=" + state.season);
      if (state.block) parts.push("block=" + state.block);
    }
    try {
      if (typeof history !== "undefined" && history.replaceState) history.replaceState(null, "", "#" + parts.join("&"));
      else if (typeof location !== "undefined") location.hash = "#" + parts.join("&");
    } catch (e) { /* hash is optional */ }
  }

  // ---- League --------------------------------------------------------------
  // Short header labels: the board takes them under 1400px of block width (so
  // sixteen columns sit inside the block at desk) and under 560px.
  var SHORT = { cbt_payroll_2026: "2026 CBT", space_2027_spotrac: "Space 27", cost_plus: "Cost+", club: "Club",
                est_tax_2026: "Est. tax 26", committed_2027: "Committed 27", proj_wins_2027: "Proj wins 27",
                usd_per_win: "$ per win", usd_per_war: "$ per WAR", controlled_surplus_mm: "Ctrl surplus",
                arb_exposure_2027: "Arb exp 27" };
  var KEEP_NARROW = { club: 1, cbt_payroll_2026: 1, space_2027_spotrac: 1, cost_plus: 1 };
  var TEXT_COLS = { club: 1, payor_2026: 1 };

  // M09-03 / owner answer M13-1: a club whose Spotrac 2027 tax payroll sits
  // below its own guaranteed 2027 contract AAV takes the AAV as its 2027 basis,
  // and every cell built on it carries a flag naming the substitution.
  function taxFloorMark(r) {
    return r.tax_floor_below_2027 ? '<span class="ledger-flag" title="' + esc(copy("tax_floor_note")) + '">AAV</span>' : "";
  }
  function taxFloorLine(tf) {
    if (!tf || !tf.below) return "";
    return "<br>" + flag(copy("cbt_basis_aav_label")) + " Spotrac publishes " + esc(money(tf.spotrac_tax_payroll_usd)) + "; the guaranteed " +
      esc(classYear()) + " contract AAV on " + esc(tf.n_rows) + " rows is " + esc(money(tf.guaranteed_aav_usd)) + ". " + esc(copy("tax_floor_note"));
  }
  // The Cost+ denominator, three parts printed apart (owner answer M13-4):
  // never added into one payroll figure on this page.
  function costParts(I) {
    var P = I.cost_plus_parts || {}, L = copy("cost_plus_part_labels") || {}, F = I.locked_fa_2027 || {};
    if (!isNum(P.guaranteed_usd)) return "";
    return '<table class="ledger-mini ledger-cost-parts">' +
      "<tr><td>" + esc(copy("cost_plus_numerator_label")) + "</td><td>" + esc(num(I.proj_war_2027, 1)) + " less " + esc(num(F.war, 1)) +
        " (" + esc(F.n) + " locked free agents) = " + esc(num(I.proj_war_2027_ex_fa, 1)) + "</td></tr>" +
      "<tr><td>" + esc(L.guaranteed || "") + "</td><td>" + esc(money(P.guaranteed_usd)) + (P.guaranteed_source === "guaranteed_aav" ? " " + flag(copy("cbt_basis_aav_label")) : "") + "</td></tr>" +
      "<tr><td>" + esc(L.arb || "") + " (" + esc(P.n_arb) + ")</td><td>" + esc(money(P.arb_usd)) + "</td></tr>" +
      "<tr><td>" + esc(L.prearb || "") + " (" + esc(P.n_prearb) + ")</td><td>" + esc(money(P.prearb_usd)) + "</td></tr></table>" +
      '<p class="ledger-count">' + esc(copy("cost_plus_parts_note")) +
      (P.n_contract_dropped ? "; here " + esc(P.n_contract_dropped) + " rung (" + esc(money(P.contract_dropped_usd)) + ")" : "") + ".</p>";
  }
  function costTitle(r) {
    var p = r.cost_plus_parts || [], L = copy("cost_plus_part_labels") || {};
    if (!isNum(p[0])) return "";
    return (L.guaranteed || "") + " " + money(p[0]) + "; " + (L.arb || "") + " " + money(p[1]) + "; " + (L.prearb || "") + " " + money(p[2]) +
      "; WAR less locked free agents " + num(r.proj_war_2027_ex_fa, 1) + " (" + num(r.locked_fa_war_2027, 1) + " left out)";
  }
  function leagueCell(r, key) {
    var v = r[key];
    if (key === "club") {
      return '<a href="#section=club&team=' + esc(r.club) + '" data-llink="1" title="' + esc(r.name || "") + '">' + esc(r.club) + "</a>";
    }
    if (key === "payor_2026") return esc(v || "");
    if (key === "cost_plus") return '<span title="' + esc(costTitle(r)) + '">' + zCell(v) + "</span>" + taxFloorMark(r);
    if (key === "orgsur_plus") return zCell(v);
    if (key === "vs_threshold_2026") return signedMoney(v);
    if (key === "space_2027_spotrac") {
      return '<span class="' + signCls(v) + '" title="' + esc(copy("space_2027_platform_label")) + ": " + money(r.space_2027_platform) + '">' + money(v) + "</span>" + taxFloorMark(r);
    }
    if (key === "proj_wins_2027") return num(v, 1);
    if (key === "locked_pct") return pct(v, 0);
    if (key === "controlled_surplus_mm") return moneyMM(v);
    if (key === "farm_rank") return isNum(v) ? String(v) : "";
    if (key === "usd_per_win" || key === "usd_per_war") return money(v);
    return money(v);
  }
  function sortedRows() {
    var rows = DATA.league.rows.slice();
    var k = state.sort.key, asc = state.sort.asc;
    rows.sort(function (a, b) {
      var x = a[k], y = b[k];
      if (TEXT_COLS[k]) { x = String(x || ""); y = String(y || ""); return asc ? x.localeCompare(y) : y.localeCompare(x); }
      var nx = isNum(x) ? Number(x) : (asc ? Infinity : -Infinity);
      var ny = isNum(y) ? Number(y) : (asc ? Infinity : -Infinity);
      return asc ? nx - ny : ny - nx;
    });
    return rows;
  }
  function renderLeague() {
    var L = DATA.league;
    var cols = L.columns;
    var head = cols.map(function (c) {
      var key = c[0], label = c[1], slug = c[2], tip = c[3];
      var cls = KEEP_NARROW[key] ? "" : "lb-col-hide";
      var lab = slug ? gl(label, slug) : esc(label);
      var labShort = slug ? gl(SHORT[key] || label, slug) : esc(SHORT[key] || label);
      var arrow = state.sort.key === key ? (state.sort.asc ? " &#9650;" : " &#9660;") : "";
      // aria-sort so a screen reader hears the sort, not only the arrow glyph
      // (census X06-06)
      var aria = state.sort.key === key ? (state.sort.asc ? "ascending" : "descending") : "none";
      return '<th class="' + cls + '" data-lsort="' + esc(key) + '" scope="col" tabindex="0" aria-sort="' + aria + '" title="' + esc(tip) + '">' +
        '<span class="lb-lab-long">' + lab + '</span><span class="lb-lab-short">' + labShort + "</span>" + arrow + "</th>";
    }).join("") + '<th class="lb-xp"></th>';
    var body = sortedRows().map(function (r) {
      var tds = cols.map(function (c) {
        var cls = KEEP_NARROW[c[0]] ? "" : "lb-col-hide";
        return '<td class="' + cls + '">' + leagueCell(r, c[0]) + "</td>";
      }).join("");
      var open = !!state.open["L:" + r.club];
      var xp = '<td class="lb-xp"><button type="button" class="ledger-xp-btn" data-lxp="L:' + esc(r.club) + '" aria-expanded="' + (open ? "true" : "false") + '">' + (open ? "&minus;" : "+") + "</button></td>";
      var row = "<tr>" + tds + xp + "</tr>";
      if (open) {
        row += '<tr class="ledger-xp-row"><td colspan="' + (cols.length + 1) + '"><dl class="ledger-dl">' +
          cols.map(function (c) { return "<dt>" + esc(c[1]) + "</dt><dd>" + leagueCell(r, c[0]) + "</dd>"; }).join("") +
          "</dl></td></tr>";
      }
      return row;
    }).join("");
    var av = L.averages_row, mv = L.means.values;
    var foot = "<tr><td>" + esc(av.label) + "</td>" + cols.slice(1).map(function (c) {
      var k = c[0], cls = KEEP_NARROW[k] ? "" : "lb-col-hide";
      return '<td class="' + cls + '">' + (k === "committed_2027" ? money(av.committed_2027) : "") + "</td>";
    }).join("") + '<td class="lb-xp"></td></tr>';
    foot += "<tr><td>" + esc(L.means.label) + "</td>" + cols.slice(1).map(function (c) {
      var k = c[0], cls = KEEP_NARROW[k] ? "" : "lb-col-hide";
      var v = mv[k];
      var txt = "";
      if (!isNum(v)) txt = "";
      else if (k === "cost_plus" || k === "orgsur_plus" || k === "proj_wins_2027") txt = num(v, 1);
      else if (k === "locked_pct") txt = pct(v, 0);
      else if (k === "controlled_surplus_mm") txt = moneyMM(v);
      else txt = money(v);
      // A mean over fewer rows than the board carries says so (the Est. tax
      // pool is the payors alone: a non-payor is blank, never zero).
      var n = mv[k + "_n"];
      if (txt && isNum(n) && Number(n) < DATA.league.rows.length) txt += " (n " + esc(n) + ")";
      return '<td class="' + cls + '">' + txt + "</td>";
    }).join("") + '<td class="lb-xp"></td></tr>';
    var pool = L.pools.cost_plus;
    return '<p class="ledger-lede">' + esc(copy("league_lede")) + "</p>" + banner() +
      '<div class="ledger-board"><table class="ledger-table" data-csv-primary><thead><tr>' + head + "</tr></thead><tbody>" + body +
      "</tbody><tfoot>" + foot + "</tfoot></table>" +
      // Why the two footer means disagree: one sentence from the export,
      // pinned to the measured cause (the fetch stamps), never typed here.
      (copy("footer_means_note") ? '<p class="ledger-count ledger-foot-note">' + esc(copy("footer_means_note")) + "</p>" : "") +
      renderQuadrant() + "</div>" +
      '<p class="ledger-count">' + gl("Cost+", "cost_plus") + " pool: n " + esc(pool.n) + ", mean " + esc(num(pool.mean_index, 1)) +
      ", sd " + esc(num(pool.sd_index, 1)) + "; " + esc(copy("cost_plus_basis")) + ". " + esc(copy("cost_plus_registry")) + "</p>" +
      '<p class="ledger-note">' + esc(copy("surplus_ev")) + " " + esc(copy("surplus_no_tier")) + "</p>";
  }

  // The quadrant: one series (thirty clubs), x = CBT payroll 2026, y = controlled
  // surplus, both in $M. Direct identity labels (the club code), a surface ring
  // on every dot, a hit target wider than the dot, solid recessive gridlines,
  // text in text tokens. The table above carries the same numbers.
  function niceTicks(lo, hi, n) {
    if (!(hi > lo)) return [lo];
    var span = hi - lo, raw = span / n, mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var step = raw / mag;
    step = step < 1.5 ? 1 : step < 3.5 ? 2 : step < 7.5 ? 5 : 10;
    step *= mag;
    var out = [];
    for (var v = Math.floor(lo / step) * step; v <= hi + step * 0.5; v += step) out.push(Math.round(v * 1e6) / 1e6);
    return out;
  }
  function renderQuadrant() {
    var Q = DATA.league.quadrant;
    var pts = DATA.league.rows.filter(function (r) { return isNum(r[Q.x]) && isNum(r[Q.y]); })
      .map(function (r) { return { c: r.club, x: Number(r[Q.x]) / 1e6, y: Number(r[Q.y]) }; });
    if (!pts.length) return "";
    var W = 560, H = 360, padL = 52, padR = 16, padT = 16, padB = 42;
    var xs = pts.map(function (p) { return p.x; }), ys = pts.map(function (p) { return p.y; });
    var xt = niceTicks(Math.min.apply(null, xs), Math.max.apply(null, xs), 5);
    var yt = niceTicks(Math.min.apply(null, ys), Math.max.apply(null, ys), 5);
    var x0 = xt[0], x1 = xt[xt.length - 1], y0 = yt[0], y1 = yt[yt.length - 1];
    function X(v) { return padL + (v - x0) / (x1 - x0 || 1) * (W - padL - padR); }
    function Y(v) { return H - padB - (v - y0) / (y1 - y0 || 1) * (H - padT - padB); }
    var g = "";
    xt.forEach(function (v) {
      g += '<line class="lq-grid" x1="' + X(v) + '" x2="' + X(v) + '" y1="' + padT + '" y2="' + (H - padB) + '"/>' +
        '<text x="' + X(v) + '" y="' + (H - padB + 14) + '" text-anchor="middle">' + esc(v) + "</text>";
    });
    yt.forEach(function (v) {
      g += '<line class="lq-grid" x1="' + padL + '" x2="' + (W - padR) + '" y1="' + Y(v) + '" y2="' + Y(v) + '"/>' +
        '<text x="' + (padL - 6) + '" y="' + (Y(v) + 3) + '" text-anchor="end">' + esc(v) + "</text>";
    });
    g += '<line class="lq-axis" x1="' + padL + '" x2="' + (W - padR) + '" y1="' + (H - padB) + '" y2="' + (H - padB) + '"/>' +
      '<line class="lq-axis" x1="' + padL + '" x2="' + padL + '" y1="' + padT + '" y2="' + (H - padB) + '"/>';
    var xlab = "CBT payroll " + esc(seasonNow()) + " (" + esc(Q.unit) + ")";
    var ylab = "Controlled surplus (" + esc(Q.unit) + ")";
    g += '<text class="lq-title" x="' + (padL + (W - padL - padR) / 2) + '" y="' + (H - 6) + '" text-anchor="middle">' + xlab + "</text>";
    g += '<text class="lq-title" transform="translate(12 ' + (padT + (H - padT - padB) / 2) + ') rotate(-90)" text-anchor="middle">' + ylab + "</text>";
    pts.forEach(function (p) {
      var tip = p.c + ": " + xlab + " " + p.x.toFixed(1) + ", " + ylab + " " + p.y.toFixed(1);
      g += '<circle class="lq-hit" cx="' + X(p.x) + '" cy="' + Y(p.y) + '" r="12"><title>' + esc(tip) + "</title></circle>" +
        '<circle class="lq-dot" cx="' + X(p.x) + '" cy="' + Y(p.y) + '" r="5"><title>' + esc(tip) + "</title></circle>" +
        '<text x="' + (X(p.x) + 7) + '" y="' + (Y(p.y) - 5) + '">' + esc(p.c) + "</text>";
    });
    return '<figure class="ledger-quadrant"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(xlab + " against " + ylab + ", thirty clubs") + '">' + g + "</svg>" +
      '<figcaption class="ledger-count">' + esc(xlab) + " against " + esc(ylab) + "; descriptive, one point per club, the same numbers as the table.</figcaption></figure>";
  }

  // ---- Club --------------------------------------------------------------------
  function renderControls(d) {
    var sel = '<label>Club <select id="ledger-club" class="eephus-select" data-team-picker aria-label="Club">' +
      clubs().map(function (c) { return opt(c, c + (clubOf(c).name ? " " + clubOf(c).name : ""), state.team); }).join("") + "</select></label>";
    var seasons = [seasonNow(), classYear()].map(function (y) {
      return '<label class="ledger-chip"><input type="radio" name="ledger-season" value="' + esc(y) + '"' + (state.season === y ? " checked" : "") + "> " + esc(y) + "</label>";
    }).join("");
    return '<div class="ledger-controls">' + sel + '<span>Season</span>' + seasons + "</div>";
  }
  function tile(title, big, sub, cls) {
    return '<div class="ledger-tile"><div class="ledger-tile-title">' + title + '</div><div class="ledger-tile-big ' + (cls || "") + '">' + big + '</div><div class="ledger-tile-sub">' + (sub || "") + "</div></div>";
  }
  function renderPayroll(d) {
    var P = d.payroll, y = state.season, ps = P["s" + y] || {}, p27 = P.s2027 || {};
    // the 2027 tile prints the club's 2027 basis (owner answer M13-1): Spotrac's
    // figure, or the guaranteed AAV where that is larger, named by taxFloorLine
    var b27 = P.cbt_basis_2027 || {};
    var bigTax = y === classYear() && isNum(b27.usd) ? b27.usd : ps.tax_payroll_usd;
    var t1 = tile(gl("CBT payroll " + esc(y), "cbt_payroll"), money(bigTax),
      gl("Total payroll allocations " + esc(y), "payroll_allocations") + ": " + esc(money(ps.total_payroll_usd)) + " (Spotrac)" +
      (y === classYear() ? taxFloorLine(P.tax_floor_2027) : ""));
    // The 2027 tier names its basis (the Spotrac page, or derived) in both branches.
    var basis27 = y === classYear() ? " (" + esc(copy("payor_basis")[P.payor_2027.basis] || P.payor_2027.basis) + ")" : "";
    var payorTxt = gl("payor", "payor_tier") + " " + esc(y === classYear() ? P.payor_2027.value : ps.payor_status_raw) + basis27;
    var surOnly = y === classYear() && (d.cbt[y] || {}).spotrac_est_is_surcharges_only;
    var t2 = ps.est_tax_bill_usd ? tile("Est. tax " + esc(y), money(ps.est_tax_bill_usd), "Spotrac estimate" + (surOnly ? ", surcharges only (no base rate)" : "") + "; " + payorTxt)
      : tile("Est. tax " + esc(y), "not a payor", payorTxt);
    var t3 = tile(gl("Committed " + esc(classYear()), "payroll_allocations"), money(p27.total_payroll_usd), "Spotrac total payroll allocations");
    var sp = P.space_2027;
    var t4 = tile("Space " + esc(classYear()), signedMoney(sp.spotrac_usd),
      esc(copy("space_2027_spotrac_label")) + "<br>" + esc(copy("space_2027_platform_label")) + ": " + signedMoney(sp.platform_usd) +
      ((P.tax_floor_2027 || {}).below ? "<br>" + flag(copy("cbt_basis_aav_label")) : ""));
    var out = '<div class="ledger-tiles">' + t1 + t2 + t3 + t4 + "</div>" +
      '<p class="ledger-count">' + esc(copy("allocations_note")) + "</p>";
    if (p27.split_available && p27.split) {
      var names = ["active", "injured", "retained", "buried"];
      var tot = p27.split.reduce(function (a, v) { return a + (isNum(v) ? Number(v) : 0); }, 0);
      out += '<div class="ledger-split">' + p27.split.map(function (v, i) {
        return isNum(v) && tot > 0 ? '<span class="ledger-split-' + names[i] + '" style="width:' + (Number(v) / tot * 100).toFixed(2) + '%" title="' + esc(names[i]) + " " + esc(money(v)) + '"></span>' : "";
      }).join("") + "</div>" +
        '<div class="ledger-legend">' + p27.split.map(function (v, i) {
          return '<span><i class="ledger-split-' + names[i] + '"></i>' + esc(names[i]) + " " + esc(isNum(v) ? money(v) : "n/a") + "</span>";
        }).join("") + "<span>" + esc(copy("split_2027_label")) + (isNum(p27.avg_age) ? "; avg age " + esc(num(p27.avg_age, 1)) : "") + "</span></div>";
    }
    out += '<p class="ledger-count">' + esc(copy("split_2026_note")) + "</p>";
    out += dark("Payroll history", (DATA.sections.payroll_history || {}).blocked_on || "");
    return out;
  }
  function renderCbt(d) {
    var y = state.season, C = d.cbt[y] || {}, tiers = DATA.cba.surcharge_tiers_usd, T = C.threshold_usd;
    var rungs = [T].concat(tiers.map(function (t) { return T + t; }));
    var top = rungs[rungs.length - 1] + (tiers[0] || 0);
    var tax = C.tax_payroll_usd;
    function pos(v) { return Math.max(0, Math.min(100, (v - (T - (tiers[0] || 0))) / (top - (T - (tiers[0] || 0))) * 100)); }
    var ladder = '<div class="ledger-ladder">' + rungs.map(function (r, i) {
      return '<div class="ledger-rung" style="bottom:' + pos(r).toFixed(1) + '%">' + esc(i === 0 ? "threshold " + money(r) : "+" + money(tiers[i - 1]) + " " + money(r)) + "</div>";
    }).join("") + (isNum(tax) ? '<div class="ledger-marker" style="bottom:calc(' + pos(tax).toFixed(1) + '% - 6px)"></div><div class="ledger-marker-lab" style="bottom:calc(' + pos(tax).toFixed(1) + '% - 8px)">' + esc(money(tax)) + "</div>" : "") + "</div>";
    var list = '<ul class="ledger-rungs">' + rungs.map(function (r, i) {
      var here = isNum(tax) && tax >= r && (i === rungs.length - 1 || tax < rungs[i + 1]);
      return '<li class="' + (here ? "is-here" : "") + '"><span>' + esc(i === 0 ? "threshold" : "+" + money(tiers[i - 1])) + "</span><span>" + esc(money(r)) + "</span></li>";
    }).join("") + "</ul>";
    var bracket = (DATA.cba.brackets || {})[C.bracket] || "";
    var over = '<p class="ledger-note">' + gl("Bracket", "cbt_bracket") + ": " + esc(bracket) + ". " + overUnder(C.over_usd) + costMoney(C.over_usd) +
      " (platform " + esc(money(T)) + ", " + esc(C.threshold_verify) + ")" +
      (y === classYear() && isNum(C.over_spotrac_basis_usd) ? "; Spotrac " + esc(money(C.spotrac_basis_usd)) + " basis: " + overUnder(C.over_spotrac_basis_usd).toLowerCase() + costMoney(C.over_spotrac_basis_usd) : "") + "</p>";
    var comp = isNum(C.spotrac_est_bill_usd)
      ? "<tr><td>" + gl("Computed bill", "computed_cbt_bill") + "</td><td>" + esc(money(C.computed_bill_usd)) + "</td></tr>" +
        "<tr><td>Spotrac estimate</td><td>" + esc(money(C.spotrac_est_bill_usd)) + "</td></tr>" +
        "<tr><td>Difference</td><td>" + esc(money(C.diff_usd)) + "</td></tr>" +
        (C.spotrac_est_is_surcharges_only ? '<tr><td colspan="2" class="ledger-count">' + esc(copy("cbt_spotrac_surcharges_only")) + "</td></tr>" : "")
      : "<tr><td>" + gl("Computed bill", "computed_cbt_bill") + "</td><td>" + esc(money(C.computed_bill_usd)) + (C.bracket === "under" ? " (" + esc(copy("cbt_under")) + ")" : "") + "</td></tr>" +
        "<tr><td>Spotrac estimate</td><td></td></tr>";
    comp += "<tr><td>" + gl("Payor tier", "payor_tier") + "</td><td>" + esc(C.tier || "") + " (" + esc(copy("payor_basis")[C.tier_basis] || C.tier_basis) + ")</td></tr>";
    var clock = d.cbt.clock || {};
    var q = d.cbt.qo_pick_tax || {};
    return (y === classYear() ? banner() : "") + ladder + list + over +
      '<table class="ledger-mini">' + comp + "</table>" +
      '<p class="ledger-count">' + esc(copy("cbt_computed_label")) + ". " + esc(copy("cbt_verify_note")) + "</p>" +
      '<p class="ledger-note">Tax clock: ' + esc(clock.tier_2026 || "") + " for " + esc(seasonNow()) + " implies " + esc(clock.consecutive_payor_seasons_implied) + " consecutive payor season(s); " + esc(copy("cbt_clock_rule")) + "</p>" +
      '<p class="ledger-note">' + gl("QO pick tax", "qo_tax") + " at the club's tier (" + esc(q.club_tier) + "): " + esc(money(q.club_usd)) + ". " + esc(copy("qo_recipient_note")) + ". " + esc((DATA.sections.qo_pending || {}).note || "") + "</p>";
  }
  // NO RULER CALL IN THIS FUNCTION. Three labelled segments per season and the
  // unpriced count; the sum is never printed.
  function renderCommitments(d) {
    var K = d.commitments, rows = K.by_season, bases = copy("commitments_bases") || {};
    var maxTot = 0;
    rows.forEach(function (r) { maxTot = Math.max(maxTot, r[1] + r[3] + r[5]); });
    var T = K.threshold_2027_usd;
    var out = '<div class="ledger-legend"><span><i class="ledger-seg-contract"></i>' + esc(bases.contract) + "</span><span><i class=\"ledger-seg-arb\"></i>" + esc(bases.arb) + "</span><span><i class=\"ledger-seg-prearb\"></i>" + esc(bases.prearb) + "</span></div>";
    rows.forEach(function (r) {
      var season = r[0], a = r[1], b = r[3], c = r[5];
      function w(v) { return maxTot > 0 ? (v / maxTot * 100).toFixed(2) + "%" : "0%"; }
      var thr = "";
      if (season === DATA.class_year && isNum(T) && maxTot > 0 && T <= maxTot) {
        thr = '<div class="ledger-threshold" style="left:' + (T / maxTot * 100).toFixed(2) + '%" title="' + esc(copy("commitments_threshold_2027")) + '"></div>';
      }
      out += '<div class="ledger-season"><div class="ledger-season-head"><span>' + esc(season) + "</span><span>" +
        esc(r[2]) + " contract, " + esc(r[4]) + " arb, " + esc(r[6]) + " pre-arb, " + esc(K.n_unpriced) + " unpriced" + (r[7] ? ", " + esc(r[7]) + " cliff" : "") + "</span></div>" +
        '<div class="ledger-stack">' + thr +
        '<span class="ledger-seg-contract" style="width:' + w(a) + '"></span><span class="ledger-seg-arb" style="width:' + w(b) + '"></span><span class="ledger-seg-prearb" style="width:' + w(c) + '"></span></div>' +
        '<div class="ledger-segs"><div><b>' + esc(money(a)) + "</b><i>on file</i></div><div><b>" + esc(money(b)) + "</b><i>arb, projected</i></div><div><b>" + esc(money(c)) + "</b><i>pre-arb by rule</i></div></div>" +
        '<div class="ledger-threshold-lab">' + esc(season === DATA.class_year ? "threshold " + money(T) + ", " + copy("commitments_threshold_2027") : copy("commitments_threshold_later")) + "</div>" +
        arbSeasonBar(d, season, w) + "</div>";
    });
    if (d.arbitration && d.arbitration.by_season) {
      out += '<div class="ledger-legend"><span><i class="ledger-seg-arb2"></i>arb rungs (Arbitration Predictor board)</span><span><i class="ledger-seg-prearb2"></i>pre-arb rungs (board)</span></div>' +
        '<p class="ledger-count">' + esc(copy("arb_two_populations")) + "</p>";
    }
    var ex = K.expiring;
    out += '<p class="ledger-note">' + gl("Payroll horizon", "payroll_horizon") + ": " + esc(copy("horizon_label")) + " " + esc(K.horizon_season || copy("horizon_beyond")) + ". " +
      esc(K.n_priced) + " priced of " + esc(K.n_vets) + " vets; " + esc(K.n_unpriced) + " carry no price.</p>";
    out += '<table class="ledger-mini"><tr><td>Expiring after ' + esc(seasonNow()) + "</td><td>" + esc(ex["2027"][0]) + " players, prev AAV " + esc(money(ex["2027"][1])) + ", projected guarantees " + esc(money(ex["2027"][2])) + "</td></tr>" +
      "<tr><td>Expiring after " + esc(classYear()) + "</td><td>" + esc(ex["2028"][0]) + " players, prev AAV " + esc(money(ex["2028"][1])) + "</td></tr>" +
      "<tr><td>Expiring the winter after</td><td>" + esc(ex["2029"][0]) + " players</td></tr></table>" +
      '<p class="ledger-count">' + esc(copy("expiring_basis")) + "</p>";
    out += '<p class="ledger-note">' + esc(copy("commitments_not_summed")) + "</p>";
    out += "<details><summary>" + gl("Salary path", "salary_path") + ": the four disclosed holes</summary><ul>" +
      (copy("holes") || []).map(function (h) { return "<li>" + esc(h) + "</li>"; }).join("") + "</ul></details>";
    return out;
  }
  // The second exposure population, drawn APART from the stack (4.4): a thin
  // hatched bar of the Arbitration Predictor board's rungs for the season, two
  // parts of one number (the v1 ladder sum), its own legend and total, on the
  // stack's axis so widths compare but never inside the stack. No ruler call.
  function arbSeasonBar(d, season, w) {
    var A = d.arbitration || {};
    if (!A.by_season) return "";
    var row = null;
    A.by_season.forEach(function (b) { if (cv("arbitration.by_season", b, "season") === season) row = b; });
    if (!row) return "";
    var arb = cv("arbitration.by_season", row, "arb_rung_usd") || 0, pre = cv("arbitration.by_season", row, "prearb_rung_usd") || 0;
    var na = cv("arbitration.by_season", row, "n_arb_rungs") || 0, np = cv("arbitration.by_season", row, "n_prearb_rungs") || 0, nn = cv("arbitration.by_season", row, "n_null_rungs") || 0;
    return '<div class="ledger-bar2" role="group" aria-label="Arbitration Predictor board rungs ' + esc(season) + '">' +
      '<div class="ledger-bar2-track"><span class="ledger-seg-arb2" style="width:' + w(arb) + '"></span><span class="ledger-seg-prearb2" style="width:' + w(pre) + '"></span></div>' +
      '<div class="ledger-bar2-lab">Arbitration Predictor board, ' + esc(A.n) + " rows, " + esc(A.n_in_vets) + " in the projections vets: ladder sum " + esc(money(arb + pre)) +
      " = arb rungs " + esc(money(arb)) + " (" + esc(na) + ") + pre-arb rungs " + esc(money(pre)) + " (" + esc(np) + ")" + (nn ? "; " + esc(nn) + " null rung(s) outside every sum" : "") + "</div></div>";
  }
  // The basis words under a trade value range: a projection-priced MLB row's
  // range is the projection P10-P90 over every priced season, not the eFV
  // interval a prospect row carries. An older payload without the projection
  // key falls back to the one sentence it has.
  function bandCopy(isProjection) {
    return (isProjection && copy("band_row_projection")) || copy("band_row_only");
  }
  // The WAR strip beneath a salary cell: the season's expected WAR (a mean),
  // blank where the surplus strip has no salary so the two strips align; the
  // band rides the title, per season, never summed. No ruler call.
  function warStripCell(pr, i) {
    if (!pr) return "";
    var war = cv("contracts.paths", pr, "war") || [], lo = cv("contracts.paths", pr, "war_p10") || [], hi = cv("contracts.paths", pr, "war_p90") || [], sur = cv("contracts.paths", pr, "sur_mm") || [];
    if (!isNum(sur[i]) || !isNum(war[i])) return "";
    return '<span class="ledger-warcell" title="' + esc("WAR P10 " + num(lo[i], 1) + " to P90 " + num(hi[i], 1) + ", " + copy("war_band_cell")) + '">' + esc(num(war[i], 1)) + " WAR</span>";
  }
  // The contract expander's depth lines: the surplus strip, the two identities
  // (NPV of the strip against the served NPV; total = rest of season + NPV),
  // the trade board's value with its source and the re-anchored chip, control,
  // and the opt-out sentence when the row carries a player option.
  function contractDepth(pr, opts) {
    if (!pr) return "";
    function P(n) { return cv("contracts.paths", pr, n); }
    var sur = P("sur_mm") || [], first = DATA.horizon[0], rate = (DATA.accountability || {}).discount_rate;
    // The WHOLE strip, not only the horizon columns: a guarantee past the last
    // horizon season is priced through its last season (the contract tail), and
    // the NPV identity below discounts every cell of it.
    var strip = sur.map(function (v, i) { return isNum(v) ? esc(first + i) + " " + signedMM(v) : ""; }).filter(Boolean).join(", ");
    var out = dd("Surplus strip", strip + '<div class="ledger-count">' + esc(copy("sur_strip_basis")) + "</div>");
    out += dd("NPV identity", "NPV of the strip at " + esc(isNum(rate) ? pctStr(rate) : "the platform rate") + ": " + esc(money(P("npv_check_usd"))) + "; served " + esc(money(P("sur_npv_usd"))) +
      '<div class="ledger-count">' + esc(copy("npv_identity")) + "</div>");
    out += dd("Total to acquire", esc(money(P("sur_total_usd"))) + " = rest of season " + esc(moneyMM(P("sur_ros_mm"))) + " + NPV " + esc(money(P("sur_npv_usd"))) +
      '<div class="ledger-count">' + esc(copy("sur_total_identity")) + "</div>");
    if (isNum(P("tv_mm"))) {
      out += dd("Trade Machine", esc(moneyMM(P("tv_mm"))) + " (" + bandMM(P("tv_lo_mm"), P("tv_hi_mm"), bandCopy(P("band_basis") === "projection")) + ") " + letter(P("tv_grade")) + " " + esc(P("surplus_source") || "") +
        (P("reanchored") ? " " + flag("re-anchored") + " " + esc(copy("tv_reanchored")) : "") +
        (P("surplus_source") === "prearb_min" ? '<div class="ledger-count">' + esc(copy("prearb_min_floor")) + "</div>" : ""));
    }
    out += dd("Control", esc(P("control_thru") || "") + " " + esc(P("control_why") || "") + (isNum(P("remaining_control_years")) ? "; " + esc(P("remaining_control_years")) + " control years remaining" : ""));
    var po = P("player_opt_years") || [];
    if (po.length) out += dd("Player option " + po.join(", "), esc(copy("opt_out_two_engines")));
    // The club's right (owner answer VAL2-Q2): a club option the club would
    // decline is a $0 cell in the strip above, never a negative one.
    var co = P("club_opt_years") || [], cd = P("club_opt_declined") || [];
    if (co.length) out += dd("Club option " + co.join(", ") + (cd.length ? ", declined " + cd.join(", ") : ""), esc(copy("club_option_rule")));
    return out;
  }
  function cellState(tok, cliff) {
    if (cliff) return "is-cut";
    if (tok === "signed") return "is-signed";
    if (tok === "PRE-ARB") return "is-prearb";
    return "is-arb";
  }
  // NO RULER CALL IN THIS FUNCTION. A salary is a cost: state classes with a
  // border and a strike, never a tier colour; the NPV surplus column takes its
  // sign only.
  function renderContracts(d) {
    var K = d.contracts, seasons = DATA.horizon, bases = copy("cell_basis") || {};
    // the depth rows: the club's contract paths, keyed, once the shard is in
    var sh = shardOf(d.club), pathBy = {};
    if (sh && sh.contracts && sh.contracts.paths) sh.contracts.paths.forEach(function (p) { pathBy[cv("contracts.paths", p, "key")] = p; });
    var head = "<tr><th>Player</th><th class=\"lc-col-hide\">Src</th>" + seasons.map(function (s, i) {
      return '<th class="' + (i === 0 ? "" : "lc-col-hide") + '">' + esc(s) + "</th>";
    }).join("") + "<th>Thru</th><th class=\"lc-col-hide\">Ctrl</th><th class=\"lc-col-hide\">NPV surplus</th><th class=\"lc-xp\"></th></tr>";
    var body = K.rows.map(function (r) {
      var key = r[0], name = r[1], pos = r[2], src = r[4], thru = r[6], ctrl = r[7], why = r[8], npv = r[9], path = r[10] || [], opts = r[11] || [];
      var byS = {};
      path.forEach(function (c) { byS[c[0]] = c; });
      var pr = pathBy[key] || null;
      var cells = seasons.map(function (s, i) {
        var c = byS[s];
        if (!c) return '<td class="' + (i === 0 ? "" : "lc-col-hide") + '"></td>';
        return '<td class="' + (i === 0 ? "" : "lc-col-hide") + '"><span class="ledger-cell ' + cellState(c[4], c[6]) + '" title="' + esc(c[4]) + ", " + esc(bases[c[5]] || c[5]) + '">' + esc(money(c[1])) + "</span>" + warStripCell(pr, i) + "</td>";
      }).join("");
      var ok = "C:" + key, open = !!state.open[ok];
      var optChips = opts.map(function (o) { return '<span class="ledger-opt">' + esc((o[1] === "club" ? "CO " : "PO ") + o[0] + (isNum(o[2]) ? " " + money(o[2]) : "")) + "</span>"; }).join("");
      var row = "<tr><td><a href=\"/projections/#player=" + esc(key) + '">' + esc(name) + "</a> <span class=\"ledger-src\">" + esc(pos) + "</span>" + optChips + (pr && cv("contracts.paths", pr, "reanchored") ? flag("re-anchored") : "") + "</td>" +
        '<td class="lc-col-hide"><span class="ledger-src">' + esc(src) + "</span></td>" + cells +
        "<td>" + esc(thru || "") + "</td><td class=\"lc-col-hide\" title=\"" + esc(why || "") + '">' + esc(ctrl || "") + "</td>" +
        '<td class="lc-col-hide">' + signedMoney(npv) + "</td>" +
        '<td class="lc-xp"><button type="button" class="ledger-xp-btn" data-lxp="' + esc(ok) + '" aria-expanded="' + (open ? "true" : "false") + '">' + (open ? "&minus;" : "+") + "</button></td></tr>";
      if (open) {
        row += '<tr class="ledger-xp-row"><td colspan="' + (seasons.length + 6) + '"><dl class="ledger-dl">' +
          "<dt>Source</dt><dd>" + esc(src) + "</dd><dt>Control</dt><dd>" + esc(ctrl || "") + " " + esc(why || "") + "</dd><dt>NPV surplus</dt><dd>" + signedMoney(npv) + "</dd>" +
          path.map(function (c) {
            return "<dt>" + esc(c[0]) + " " + esc(c[4]) + "</dt><dd>" + esc(money(c[1])) + (isNum(c[2]) && isNum(c[3]) && (c[2] !== c[1] || c[3] !== c[1]) ? " (" + esc(money(c[2])) + " to " + esc(money(c[3])) + ", " + esc(copy("band_note")) + ")" : "") + "; " + esc(bases[c[5]] || c[5]) + (c[6] ? "; non-tender cliff" : "") + "</dd>";
          }).join("") + contractDepth(pr, opts) + "</dl></td></tr>";
      }
      return row;
    }).join("");
    var D = K.deferrals, PS = K.paths_summary;
    var out = banner() + '<p class="ledger-count">' + esc(K.n_priced) + " priced, " + esc(K.n_unpriced) + " unpriced. Season cells: " +
      Object.keys(bases).map(function (k) { return esc(k) + " = " + esc(bases[k]); }).join("; ") +
      (PS ? "; " + esc(PS.n_reanchored) + " of " + esc(PS.n_paths) + " re-anchored on the trade board, " + esc(PS.n_opt_out_rows) + " with a player option (" + esc(PS.n_opt_out_seasons) + " seasons)" : "") + "</p>" +
      (PS ? shardLine(d.club, copy("paths_preview_note")) : "") +
      '<div class="ledger-scroll"><table class="ledger-table ledger-contracts" data-csv-primary><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";
    out += "<details><summary>" + esc(K.n_unpriced) + " vets with no salary path</summary><div class=\"ledger-chips\">" +
      K.unpriced.map(function (u) { return '<span class="ledger-flag">' + esc(u[1]) + " " + esc(u[2]) + " " + esc(u[3]) + "</span>"; }).join("") + "</div></details>";
    out += '<p class="ledger-count">' + esc(copy("options_note")) + " " + esc(K.options.length) + " players carry options here.</p>";
    out += '<p class="ledger-note">' + gl("Deferred dollars", "deferral_npv") + " outstanding (covered deals only): sticker " + esc(money(D.sticker_usd)) + ", " + esc(copy("deferral_rate_label")) + " " + esc(money(D.npv_usd)) +
      (D.players.length ? " (" + D.players.map(function (p) { return esc(p[0]) + " " + esc(money(p[1])) + " / " + esc(money(p[2])); }).join("; ") + ")" : "") + ". " + esc(copy("deferral_coverage")) + ". " + esc(copy("deferral_rate_note")) + "</p>";
    // dark() escapes its title, so the glossary hook rides the paragraph beneath.
    out += dark("Dead money", (DATA.sections.dead_money || {}).blocked_on || "") +
      '<p class="ledger-count">Beside ' + gl("dead money", "dead_money") + ", never summed: Spotrac " + esc(classYear()) + " buried allocation " + esc(isNum(K.dead_money.buried_usd_2027) ? money(K.dead_money.buried_usd_2027) : "n/a") + ". " + esc(copy("dead_money_beside")) + "</p>";
    out += dark("Retained salary", (DATA.sections.retained || {}).blocked_on || "") +
      '<p class="ledger-count">Cross-check for ' + gl("retained salary", "retained_salary") + ": Spotrac " + esc(classYear()) + " retained allocation " + esc(isNum(K.retained.retained_usd_2027) ? money(K.retained.retained_usd_2027) : "n/a") + " (" + esc(copy("retained_cross_check")) + ").</p>";
    return out;
  }
  function flagChips(e) {
    var bits = [1, 2, 4, 8, 16], out = "";
    bits.forEach(function (b) { if (e & b) out += '<span class="ledger-flag" title="' + esc(copy("arb_flag_key")) + '">bit ' + b + "</span>"; });
    return out;
  }
  // The full ladder (shard): one cell per season carrying the rung with its
  // token and eWAR beneath and the band in the title, labelled a band, never an
  // interval; a null rung prints dark and enters no sum. Per-season cells are
  // the hidden set at phone width (Player, Class, Remaining kept).
  function renderLadder(rows) {
    var labels = copy("arb_class_labels") || {}, years = [];
    rows.forEach(function (r) { (cv("arbitration.ladders", r, "ladder") || []).forEach(function (t) { if (years.indexOf(t[0]) < 0) years.push(t[0]); }); });
    years.sort();
    var head = "<tr><th>Player</th><th>Class</th>" + '<th class="lc-col-hide">' + gl("Service", "service_time") + '</th><th class="lc-col-hide">Yrs left</th>' +
      years.map(function (y) { return '<th class="lc-col-hide">' + esc(y) + "</th>"; }).join("") + "<th>Remaining</th>" + '<th class="lc-col-hide">Flags</th><th class="lc-xp"></th></tr>';
    var body = rows.map(function (r) {
      var name = cv("arbitration.ladders", r, "name"), m = cv("arbitration.ladders", r, "mlbam"), cls = cv("arbitration.ladders", r, "class"), fl = cv("arbitration.ladders", r, "flags") || 0, sv = cv("arbitration.ladders", r, "sv"), svy = cv("arbitration.ladders", r, "svy"), yl = cv("arbitration.ladders", r, "years_left");
      var lad = cv("arbitration.ladders", r, "ladder") || [], war = cv("arbitration.ladders", r, "war") || [], tot = cv("arbitration.ladders", r, "tot_usd");
      var clsLab = ((fl & 1) ? "~" : "") + (labels[String(cls)] || String(cls));
      var byY = {};
      lad.forEach(function (t, i) { byY[t[0]] = { t: t, w: war[i] }; });
      var cells = years.map(function (y) {
        var e = byY[y];
        if (!e) return '<td class="lc-col-hide"></td>';
        var t = e.t;
        if (!isNum(t[1])) return '<td class="lc-col-hide"><span class="ledger-rung is-null" title="no salary on file; outside every sum">' + esc(t[4]) + "</span></td>";
        return '<td class="lc-col-hide"><span class="ledger-rung" title="' + esc(money(t[2]) + " to " + money(t[3]) + "; " + copy("band_note")) + '">' + esc(money(t[1])) + "</span>" +
          '<span class="ledger-rung-tok">' + esc(t[4]) + (isNum(e.w) ? " " + esc(num(e.w, 1)) + " eWAR" : "") + "</span></td>";
      }).join("");
      var k = "A:" + m, open = !!state.open[k];
      var svTxt = sv ? String(sv) + (svy ? " as of " + svy : "") : " - ";
      var row = '<tr><td><span title="mlbam ' + esc(m) + '">' + esc(name) + "</span>" + (cv("arbitration.ladders", r, "in_vets") ? flag("vets") : "") + (cv("arbitration.ladders", r, "has_salpath") ? flag("salary path") : "") + "</td><td>" + esc(clsLab) + "</td>" +
        '<td class="lc-col-hide">' + esc(svTxt) + "</td>" + '<td class="lc-col-hide">' + esc(yl) + "</td>" + cells + "<td>" + esc(money(tot)) + "</td>" + '<td class="lc-col-hide">' + flagChips(fl) + "</td>" + xpBtn(k) + "</tr>";
      if (open) {
        row += '<tr class="ledger-xp-row"><td colspan="' + (years.length + 7) + '"><dl class="ledger-dl">' +
          lad.map(function (t, i) {
            return dd(t[0] + " " + t[4], (isNum(t[1]) ? esc(money(t[1])) + " (" + esc(money(t[2])) + " to " + esc(money(t[3])) + ", " + esc(copy("band_note")) + ")" : "no salary on file, outside every sum") + (isNum(war[i]) ? "; eWAR " + esc(num(war[i], 2)) : ""));
          }).join("") +
          dd("Service", esc(svTxt)) + dd("Class", esc(clsLab) + " (" + esc(cls) + ")") + dd("Remaining", esc(money(tot))) +
          dd("Projections", (cv("arbitration.ladders", r, "in_vets") ? "in the projections vets" : "not in the projections vets") + (cv("arbitration.ladders", r, "has_salpath") ? ", salary path priced" : "")) +
          dd("Flags", flagChips(fl) + ((fl & 8) ? '<div class="ledger-count">' + esc(copy("cba_banner")) + "</div>" : "")) +
          "</dl></td></tr>";
      }
      return row;
    }).join("");
    return '<div class="ledger-scroll"><table class="ledger-table ledger-ladder-table"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";
  }
  // The realized rows per season (shard), grouped and collapsed under the v1
  // seasons row: Actual, Ours, MLBTR (Swartz) as a THIRD quantity that is never
  // a residual, then ou_mkt and ou_war in their own columns with their own
  // group totals; the Swartz footer stays blank (present on some rows only).
  function renderRealizedRows(rows) {
    var by = {};
    rows.forEach(function (r) { var s = cv("arbitration.realized.rows", r, "season"); (by[s] = by[s] || []).push(r); });
    return Object.keys(by).sort().reverse().map(function (s) {
      var rs = by[s], tot = { a: 0, o: 0, m: 0, w: 0, war: 0 };
      var body = rs.map(function (r) {
        var a = cv("arbitration.realized.rows", r, "actual_usd"), o = cv("arbitration.realized.rows", r, "ours_usd"), sw = cv("arbitration.realized.rows", r, "swartz_usd"), m = cv("arbitration.realized.rows", r, "ou_mkt_usd"), w = cv("arbitration.realized.rows", r, "ou_war_usd"), war = cv("arbitration.realized.rows", r, "war");
        tot.a += Number(a || 0); tot.o += Number(o || 0); tot.m += Number(m || 0); tot.w += Number(w || 0); tot.war += Number(war || 0);
        return "<tr><td>" + esc(cv("arbitration.realized.rows", r, "name")) + "</td><td>" + esc(cv("arbitration.realized.rows", r, "arb_year")) + "</td><td>" + esc(money(a)) + "</td><td>" + esc(money(o)) + "</td><td>" + (isNum(sw) ? esc(money(sw)) : "") + "</td><td>" + signedMoney(m) + "</td><td>" + signedMoney(w) + "</td><td>" + esc(num(war, 2)) + "</td></tr>";
      }).join("");
      return "<details" + (state.block === "arbitration" ? " open" : "") + "><summary>" + esc(s) + ": " + esc(rs.length) + " players</summary>" +
        '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Player</th><th>Arb yr</th><th>Actual</th><th>Ours</th><th title="' + esc(copy("swartz_label")) + '">MLBTR (Swartz)</th><th>' + gl("ou_mkt", "arb_market_residual") + "</th><th>ou_war</th><th>eWAR</th></tr></thead><tbody>" + body +
        "</tbody><tfoot><tr><td>" + esc(s) + "</td><td></td><td>" + esc(money(tot.a)) + "</td><td>" + esc(money(tot.o)) + "</td><td></td><td>" + signedMoney(tot.m) + "</td><td>" + signedMoney(tot.w) + "</td><td>" + esc(num(tot.war, 2)) + "</td></tr></tfoot></table></div></details>";
    }).join("");
  }
  function renderArbitration(d) {
    var A = d.arbitration, R = A.realized, sh = shardOf(d.club);
    var bs = {};
    (A.by_season || []).forEach(function (b) { bs[cv("arbitration.by_season", b, "season")] = b; });
    var s27 = bs[DATA.class_year];
    var splitSub = s27
      ? "arb rungs " + esc(money(cv("arbitration.by_season", s27, "arb_rung_usd"))) + " (" + esc(cv("arbitration.by_season", s27, "n_arb_rungs")) + "), pre-arb rungs " + esc(money(cv("arbitration.by_season", s27, "prearb_rung_usd"))) + " (" + esc(cv("arbitration.by_season", s27, "n_prearb_rungs")) + "); " + esc(copy("arb_prearb_rungs")) + ". "
      : "";
    var out = banner() + '<div class="ledger-tiles ledger-tiles--2">' +
      tile("Arb-eligible", esc(A.n), "class mix " + Object.keys(A.class_mix).map(function (k) { return k + ": " + A.class_mix[k]; }).join(", ") +
        (isNum(A.n_in_vets) ? "; " + esc(A.n_in_vets) + " in the projections vets, " + esc(A.n_with_salpath) + " with a salary path" : "")) +
      tile(gl("Ladder sum " + esc(classYear()) + " (arb and pre-arb rungs)", "arb_exposure"), money(A.s2027_usd), splitSub + esc(copy("arb_tender_note"))) +
      tile("Remaining, all seasons", money(A.remaining_usd), esc(copy("arb_provisional"))) +
      tile("Projected eWAR over the ladder", num(A.war, 1), "sum of the per-season projections") + "</div>";
    out += '<p class="ledger-count">Flag census: ' + Object.keys(A.flags).map(function (b) { return "bit " + b + ": " + A.flags[b]; }).join(", ") + ". " + esc(copy("arb_flag_key")) + "</p>";
    if (A.by_season) {
      out += '<table class="ledger-mini">' + A.by_season.map(function (b) {
        var nn = cv("arbitration.by_season", b, "n_null_rungs");
        return "<tr><td>" + esc(cv("arbitration.by_season", b, "season")) + " ladder sum</td><td>" + esc(money((cv("arbitration.by_season", b, "arb_rung_usd") || 0) + (cv("arbitration.by_season", b, "prearb_rung_usd") || 0))) + " = arb " + esc(money(cv("arbitration.by_season", b, "arb_rung_usd"))) + " (" + esc(cv("arbitration.by_season", b, "n_arb_rungs")) + ") + pre-arb " + esc(money(cv("arbitration.by_season", b, "prearb_rung_usd"))) + " (" + esc(cv("arbitration.by_season", b, "n_prearb_rungs")) + ")" + (nn ? "; " + esc(nn) + " null rung(s) outside every sum" : "") + "</td></tr>";
      }).join("") + "</table>";
    }
    out += shardLine(d.club, copy("arb_preview_note"));
    if (sh && sh.arbitration && sh.arbitration.ladders) {
      out += renderLadder(sh.arbitration.ladders);
    } else {
      out += '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Player</th><th>Token</th><th>' + esc(classYear()) + " proj</th><th>" + gl("Band", "arb_award_band") + "</th><th>Yrs left</th><th>eWAR</th></tr></thead><tbody>" +
        A.rows.map(function (r) {
          return "<tr><td>" + esc(r[0]) + "</td><td>" + esc(r[2] || "") + "</td><td>" + esc(money(r[3])) + "</td><td title=\"" + esc(copy("band_note")) + '">' + esc(isNum(r[4]) ? money(r[4]) + " to " + money(r[5]) : "") + "</td><td>" + esc(r[6]) + "</td><td>" + esc(num(r[7], 2)) + "</td></tr>";
        }).join("") + "</tbody></table></div>";
    }
    out += '<p class="ledger-count">' + gl("Band", "arb_award_band") + ": " + esc(copy("band_note")) + "</p>";
    out += dark("Award quantiles", copy("arb_quantiles_dark")) + dark("Comps", copy("arb_comps_dark")) + dark("Filing figures and hearings", copy("arb_filing_dark"));
    out += "<h3>" + esc(copy("arb_realized_title")) + "</h3>" +
      '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Season</th><th>n</th><th>Actual</th><th>Ours</th><th>' + gl("ou_mkt", "arb_market_residual") + "</th><th>ou_war</th><th>eWAR</th></tr></thead><tbody>" +
      R.seasons.map(function (s) {
        return "<tr><td>" + esc(s[0]) + "</td><td>" + esc(s[1]) + "</td><td>" + esc(money(s[2])) + "</td><td>" + esc(money(s[3])) + "</td><td>" + signedMoney(s[4]) + "</td><td>" + signedMoney(s[5]) + "</td><td>" + esc(num(s[6], 1)) + "</td></tr>";
      }).join("") + "</tbody><tfoot><tr><td>Total</td><td>" + esc(R.n) + "</td><td></td><td></td><td>" + signedMoney(R.ou_mkt_total_usd) + "</td><td>" + signedMoney(R.ou_war_total_usd) + "</td><td></td></tr></tfoot></table></div>";
    if (sh && sh.arbitration && sh.arbitration.realized_rows) out += renderRealizedRows(sh.arbitration.realized_rows);
    out += '<p class="ledger-count">ou_mkt: ' + esc(copy("ou_mkt")) + " ou_war: " + esc(copy("ou_war")) + " " + esc(copy("never_combine")) + "</p>";
    if (DATA.arbitration_eval && copy("swartz_a6")) {
      out += '<p class="ledger-count">' + esc(copy("swartz_label")) + ". " + esc(copy("swartz_a6_prefix")) + ", n " + esc(DATA.arbitration_eval.n) + ": " + esc(copy("swartz_a6")) + "</p>";
    }
    out += '<p class="ledger-note">' + esc(copy("arb_realized_copy")) + "</p>";
    return out;
  }
  function spark(series, valueIdx) {
    if (!series || series.length < 2) return "";
    var W = 520, H = 64, pad = 4;
    var vals = series.map(function (p) { return Number(p[valueIdx]); });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var pts = vals.map(function (v, i) {
      var x = pad + i / (vals.length - 1) * (W - 2 * pad);
      var y = hi === lo ? H / 2 : H - pad - (v - lo) / (hi - lo) * (H - 2 * pad);
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    return '<div class="ledger-spark"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(series[0][0]) + " to " + esc(series[series.length - 1][0]) + '"><polyline class="ledger-spark-line" points="' + pts + '"/></svg>' +
      '<div class="ledger-count">' + esc(series[0][0]) + " " + esc(num(vals[0], 1)) + " to " + esc(series[series.length - 1][0]) + " " + esc(num(vals[vals.length - 1], 1)) + "</div></div>";
  }
  function renderSurplus(d) {
    var S = d.surplus, I = d.indexes;
    var out = banner() + '<div class="ledger-tiles">' +
      tile("$ per projected win " + esc(classYear()), money(I.usd_per_win), esc(copy("ratio_bases"))) +
      tile("$ per projected WAR " + esc(classYear()), money(I.usd_per_war), "plain dollars, no ladder") +
      tile(gl("Cost+", "cost_plus"), zCell(I.cost_plus), esc(copy("cost_plus_basis"))) +
      tile("Locked", pct(I.locked_pct, 0), "share of " + esc(classYear()) + "-" + esc(DATA.horizon[DATA.horizon.length - 1]) + " core WAR under control") + "</div>" +
      costParts(I);
    out += "<h3>" + gl("Controlled surplus", "controlled_surplus") + " (" + esc(S.unit) + ", plain)</h3><table class=\"ledger-mini\">" +
      "<tr><td>MLB leg (surNpv)</td><td>" + esc(moneyMM(S.mlb_mm)) + "</td></tr>" +
      Object.keys(S.mlb_by_salsrc_mm).map(function (k) { return "<tr><td>&nbsp;&nbsp;" + esc(k) + "</td><td>" + esc(moneyMM(S.mlb_by_salsrc_mm[k])) + "</td></tr>"; }).join("") +
      "<tr><td>Farm leg (active surplus)</td><td>" + esc(moneyMM(S.farm_mm)) + "</td></tr>" +
      "<tr><td><strong>Total</strong></td><td>" + esc(moneyMM(S.total_mm)) + "</td></tr>" +
      "<tr><td>Trade Machine currency (not added)</td><td>" + esc(moneyMM(S.trade_currency_mm)) + "</td></tr></table>" +
      '<p class="ledger-count">' + esc(copy("surplus_basis")) + " " + esc(copy("surplus_ev")) + " " + esc(copy("surplus_no_tier")) + " " + esc(copy("trade_currency_basis")) + "</p>";
    if (S.reconciliation) {
      var Rc = S.reconciliation, bys = Rc.by_salsrc || {};
      out += "<h3>The legs against their rows</h3><table class=\"ledger-mini\">" +
        Object.keys(bys).map(function (k) { return "<tr><td>MLB leg, " + esc(k) + ": served / contract rows (n " + esc(bys[k][2]) + ")</td><td>" + esc(moneyMM(bys[k][0])) + " / " + esc(moneyMM(bys[k][1])) + "</td></tr>"; }).join("") +
        "<tr><td>MLB leg: served / rows</td><td>" + esc(moneyMM(Rc.mlb_served_mm)) + " / " + esc(moneyMM(Rc.mlb_rows_mm)) + "</td></tr>" +
        "<tr><td>Farm leg: served / PROSPX leaf</td><td>" + esc(moneyMM(Rc.farm_served_mm)) + " / " + esc(moneyMM(Rc.farm_leaf_mm)) + "</td></tr>" +
        "<tr><td>Trade currency: served / farm rows gross + debuted rows</td><td>" + esc(moneyMM(Rc.trade_currency_served_mm)) + " / " + esc(moneyMM(Rc.trade_rows_active_mm)) + " + " + esc(moneyMM(Rc.trade_rows_debuted_mm)) + "</td></tr>" +
        "<tr><td>Status</td><td>" + esc(Rc.status) + "</td></tr></table>" +
        '<p class="ledger-count">' + esc(copy("trade_currency_split")) + "</p>";
    }
    var c = S.crunch;
    out += '<p class="ledger-note">40-man crunch: ' + esc(c.on_40_man) + " on the 40-man, " + esc(c.rule5_exposed) + " Rule 5 exposed, " + esc(c.options_left_0) + " out of options; " + esc(c.n_active) + " active and " + esc(c.n_debuted) + " debuted assets on the trade board.</p>";
    var sh = shardOf(d.club);
    out += "<h3>Trade currency trajectory</h3>" + (sh ? spark(sh.surplus && sh.surplus.trajectory, 1) + '<p class="ledger-count">' + esc(copy("trajectory_note")) + "</p>" : seriesPending(d.club));
    return out;
  }
  // The snapshot series live in the club's row file (the board carries only a
  // receipt, shards.trajectories): a short loading line until the file is in,
  // the dark line if the fetch failed, never an empty chart.
  function seriesPending(code) {
    return shardFailed(code) ? shardLine(code) : '<p class="ledger-count">' + esc(copy("trajectory_loading")) + "</p>";
  }
  function renderFarm(d) {
    var F = d.farm, L = F.leaves, meta = copy("farm_leaves") || {};
    var out = '<div class="ledger-tiles ledger-tiles--2">' +
      tile(gl("OrgSur+", "sur_plus"), zCell(F.orgsur_plus.financial_score), esc(copy("orgsur_chip")) + "; tree fin_war_per_m score " + esc(num(F.orgsur_plus.tree_fin_war_per_m_score_100, 1))) +
      tile("Farm rank", esc(F.farm_rank), "farm score " + esc(num(F.farm_score, 1)) + ", financial letter " + esc(F.financial_letter || "")) + "</div>";
    out += '<ul class="ledger-leaves">' + Object.keys(L).map(function (k) {
      var l = L[k], m = meta[k] || {};
      return "<li><span>" + gl(k, k === "fin_active_surplus" ? "farm_grade_financial" : k) + " <span class=\"ledger-src\" title=\"" + esc(m.basis || "") + '">' + esc(isNum(m.weight) ? "w " + m.weight : "") + "</span></span>" +
        "<span>" + esc(isNum(l.value) ? num(l.value, 2) : "") + (isNum(l.n) ? " (n " + esc(l.n) + ")" : "") + " " + zCell(l.score_100) + ' <span class="ledger-letter">' + esc(l.letter) + "</span></span></li>";
    }).join("") + "</ul>" + '<p class="ledger-count">' + esc(copy("farm_letters_note")) + "</p>";
    var roi = F.financial_roi || {}, ms = F.method_surplus || {};
    out += '<p class="ledger-note">Financial ROI: ' + esc(num(roi.war_per_million, 2)) + " WAR per $M over " + esc(roi.grad_count_with_bonus) + " graduates with a bonus (" + esc(money(roi.total_bonus_usd)) + "). Surplus by method: " +
      Object.keys(ms).map(function (k) { return esc(k) + " " + esc(moneyMM(ms[k].net_mm)) + " on " + esc(ms[k].count); }).join("; ") + ".</p>";
    if (F.reconciliation) {
      var Rf = F.reconciliation, M = F.method || {};
      out += "<h3>" + gl("Farm dollar", "farm_dollar") + " leaf against the rows</h3>" +
        '<p class="ledger-note">Leaf ' + esc(moneyMM(Rf.leaf_mm)) + " (n " + esc(Rf.leaf_n) + "; " + esc(Rf.leaf_source) + ", " + esc(Rf.leaf_generated_at) + "). Rows: gross " + esc(moneyMM(Rf.rows_gross_mm)) +
        ", bonuses " + esc(moneyMM(Rf.rows_cost_mm)) + " (" + esc(Rf.n_with_bonus) + " of " + esc(Rf.n_rows) + " with a bonus on file; leaf cost basis " + esc(moneyMM(Rf.leaf_cost_mm)) + "), net " + esc(moneyMM(Rf.rows_net_mm)) +
        " (" + esc(Rf.rows_source) + ", " + esc(Rf.rows_generated_at) + "). Gap " + esc(moneyMM(Rf.gap_mm)) + " against a tolerance of " + esc(moneyMM(Rf.tolerance_mm)) + ": " + esc(String(Rf.status).replace("_", " ")) + ".</p>" +
        (Rf.status === "broken" ? '<p class="ledger-note">' + flag("does not reconcile") + " " + esc(copy("farm_gap_broken")) + "</p>" : "") +
        '<p class="ledger-count">' + esc(copy("farm_reconcile")) + (Rf.status === "vintage_drift" ? " " + esc(copy("farm_vintage_gap")) : "") + " " + esc(copy("farm_no_bonus")) + "</p>";
      out += '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Method</th><th>n (with bonus)</th><th>Gross</th><th>' + gl("Cost basis", "acquisition_cost_basis") + "</th><th>Net</th><th>Net per $ of cost</th><th>Served net / cost (org_summary, n)</th><th>" + gl("$ per FV pt", "surplus_per_fv_pt") + "</th></tr></thead><tbody>" +
        Object.keys(M).map(function (m) {
          var r = M[m], n = cv("farm.method", r, "n"), ratio = cv("farm.method", r, "net_per_cost_ratio");
          if (m === "trade") return "<tr><td>trade</td><td>" + esc(n) + '</td><td colspan="6" class="ledger-dark-cell">' + esc(copy("trade_cost_dark")) + "</td></tr>";
          return "<tr><td>" + esc(m) + "</td><td>" + esc(n) + " (" + esc(cv("farm.method", r, "n_with_bonus")) + ")</td><td>" + esc(moneyMM(cv("farm.method", r, "gross_mm"))) + "</td><td>" + esc(moneyMM(cv("farm.method", r, "cost_mm"))) + "</td><td>" + signedMM(cv("farm.method", r, "net_mm")) + "</td><td>" + esc(isNum(ratio) ? num(ratio, 1) + "x" : "") + "</td><td>" +
            esc(moneyMM(cv("farm.method", r, "served_net_mm"))) + " / " + esc(moneyMM(cv("farm.method", r, "served_cost_mm"))) + " (n " + esc(cv("farm.method", r, "served_count")) + ")</td><td>" + esc(num(cv("farm.method", r, "served_per_fv_pt_mm"), 3)) + "</td></tr>";
        }).join("") + "</tbody></table></div>" +
        '<p class="ledger-count">Net per dollar of cost basis is a ratio of two served numbers, plain, no ladder; the bonus coverage beside n says how much of the cost basis the pipeline captured.</p>';
    }
    out += "<h3>" + gl("Draft pools", "bonus_pool") + "</h3><div class=\"ledger-strip\">" + Object.keys(F.pools).map(function (y) {
      var p = F.pools[y];
      return "<div>" + esc(y) + "<b>" + esc(p[0] !== null ? money(p[0]) : p[1]) + "</b></div>";
    }).join("") + "</div>" + '<p class="ledger-count">' + esc(copy("pools_note")) + "</p>";
    out += '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Draft</th><th>Picks</th><th>Signed</th><th>Paid, all rounds</th><th>Paid (slotted)</th><th>Slot (slotted)</th><th>Over slot</th><th>Slot coverage</th><th>Pool used</th><th>Round 11+ over $150K</th></tr></thead><tbody>' +
      Object.keys(F.draft_paid).sort().reverse().map(function (y) {
        var r = F.draft_paid[y];
        // Round 11+ over $150K (owner answer M10-3): its own column, never in Pool used;
        // a draft before the 2022 CBA carries null and prints n/a.
        var r11 = isNum(r[11]) ? money(r[11]) + " (" + r[12] + ")" : (r.length > 11 ? "n/a" : "");
        return "<tr><td>" + esc(y) + "</td><td>" + esc(r[0]) + "</td><td>" + esc(r[1]) + "</td><td>" + esc(money(r[3])) + "</td><td>" + esc(money(r[6])) + "</td><td>" + esc(money(r[5])) + " (" + esc(r[4]) + ")</td><td>" + signedMoney(r[7]) + "</td><td>" + esc(isNum(r[8]) ? num(r[8], 0) + "%" : "") + "</td><td>" + esc(isNum(r[10]) ? pct(r[10], 0) : "") + "</td><td>" + esc(r11) + "</td></tr>";
      }).join("") + "</tbody></table></div>" + '<p class="ledger-count">Slot coverage: ' + esc(copy("slot_coverage_basis")) + ". Pool used: " + esc(copy("pool_used_basis")) + ". Round 11+ over $150K: " + esc(copy("r11_over_basis")) + ".</p>";
    var shp = shardOf(d.club);
    if (shp && shp.farm && shp.farm.picks) out += renderPicks(shp.farm.picks, F.picks_summary || {});
    var sc = F.slot_chips || {}, lg = copy("slot_league") || {};
    out += "<h3>Slot behaviour (" + esc(copy("slot_window")) + ")</h3><div class=\"ledger-chips\">" +
      ["overSlotShare", "r1UnderShare", "bonusHHI", "prepDollarShare"].map(function (k) {
        var m = lg[k] || {};
        return '<div class="ledger-zchip"><span class="ledger-zlbl">' + esc(k) + "</span><b>" + esc(num(sc[k], 3)) + "</b><span class=\"ledger-zlbl\">league " + esc(num(m.mean, 3)) + " sd " + esc(num(m.sd, 3)) + "</span></div>";
      }).join("") + "</div>" + '<p class="ledger-count">' + esc(sc.label || "") + "; " + esc(sc.spendLabel || "") + ". <a href=\"" + esc(d.links.org_tendencies) + '">Org tendencies</a></p>';
    var lot = F.lottery, pw = F.pick_war;
    out += "<h3>" + esc(classYear()) + " pick</h3>" + (lot ? '<p class="ledger-note">Projected pick ' + esc(lot[0]) + " (" + esc(lot[3]) + "-" + esc(lot[4]) + ", " + esc(lot[6]) + " " + esc(lot[5]) + ")" +
      (isNum(lot[1]) ? "; odds of pick 1 " + esc(num(lot[1], 1)) + "%, top-6 " + esc(num(lot[2], 1)) + "%" : "") + ". " + gl("Pick WAR", "pick_war") + ": " + esc(num(pw[0], 2)) + " (bucket to pick " + esc(pw[1]) + "). " + esc(copy("pick_war_label")) + ". " + esc(copy("pick_war_why")) + ". " + esc(copy("pick_dollars")) + "</p>" : dark("Lottery position", "no lottery snapshot for this club"));
    out += "<h3>International signings</h3>" + '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Class</th><th>Spend</th><th>Signings</th><th>Top bonus</th><th>Pool used</th><th>' + gl("Implied pool", "implied_ifa_pool") + "</th></tr></thead><tbody>" +
      Object.keys(F.ifa).sort().reverse().map(function (y) {
        var r = F.ifa[y];
        return "<tr><td>" + esc(y) + "</td><td>" + esc(money(r[0])) + "</td><td>" + esc(r[1]) + "</td><td>" + esc(money(r[2])) + " " + esc(r[3] || "") + "</td><td>" + esc(isNum(r[4]) ? num(r[4], 1) + "%" : "") + "</td><td>" + esc(money(r[5])) + (isNum(r[6]) ? " (n " + esc(r[6]) + ")" : "") + "</td></tr>";
      }).join("") + "</tbody></table></div>" + '<p class="ledger-count">' + esc(copy("ifa_implied_basis")) + "</p>" +
      dark("IFA history", (DATA.sections.ifa_history || {}).blocked_on || "");
    out += "<h3>Farm score trajectory</h3>" + spark(F.score_history, 1);
    var ta = shp && shp.farm && shp.farm.trajectory_active;
    if (!shp) {
      out += "<h3>Active eFV surplus trajectory (gross)</h3>" + seriesPending(d.club);
    } else if (ta && ta.length) {
      out += "<h3>Active eFV surplus trajectory (gross)</h3>" + spark(ta, 1) + '<p class="ledger-count">' + esc(copy("trajectory_active_basis")) + "</p>";
    }
    return out;
  }
  // Draft picks by year (shard): slot against bonus, the over-slot figure
  // sign-coloured, a pick that is still an active prospect of the club linked
  // to its farm ledger row. One collapsed group per year.
  function renderPicks(picks, summary) {
    ;
    return "<h3>" + gl("Draft picks", "slot_value") + "</h3>" + Object.keys(picks).sort().reverse().map(function (y) {
      var rows = picks[y] || [], sm = summary[y];
      if (!rows.length) return "";
      var body = rows.map(function (r) {
        var pk = cv("farm.picks", r, "prospect_key"), nm = esc(cv("farm.picks", r, "player_name"));
        return "<tr><td>" + esc(cv("farm.picks", r, "pick_overall")) + "</td><td>" + esc(cv("farm.picks", r, "round_label")) + "</td><td>" + (pk ? '<a href="' + esc("#section=club&team=" + state.team + "&block=prospects") + '" data-lprospect="' + esc(pk) + '">' + nm + "</a>" : nm) + "</td>" +
          "<td>" + esc(isNum(cv("farm.picks", r, "slot_usd")) ? money(cv("farm.picks", r, "slot_usd")) : "") + "</td><td>" + esc(isNum(cv("farm.picks", r, "bonus_usd")) ? money(cv("farm.picks", r, "bonus_usd")) : "") + "</td><td>" + signedMoney(cv("farm.picks", r, "over_slot_usd")) + "</td><td>" + esc(cv("farm.picks", r, "signed") ? "signed" : (cv("farm.picks", r, "signed") === 0 ? "unsigned" : "")) + "</td></tr>";
      }).join("");
      return "<details><summary>" + esc(y) + ": " + esc(rows.length) + " picks" + (sm ? ", " + esc(cv("farm.picks_summary", sm, "n_signed")) + " signed: " + esc(cv("farm.picks_summary", sm, "n_on_tracker")) + " on the prospect tracker, " + esc(cv("farm.picks_summary", sm, "n_graduated")) + " graduated, " + esc(cv("farm.picks_summary", sm, "n_not_tracked")) + " not tracked" : "") + "</summary>" +
        '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Pick</th><th>Round</th><th>Player</th><th>Slot</th><th>Bonus</th><th>Over slot</th><th>Signed</th></tr></thead><tbody>' + body + "</tbody></table></div></details>";
    }).join("") + '<p class="ledger-count">joined on draft year and overall pick, never on name; the tracker and graduated counts follow the player wherever he is now. The prospect tracker carries ranked and graded prospects, not every signed minor leaguer, so not tracked mixes released players with players it never carried.</p>';
  }
  function renderFa(d) {
    var A = d.fa, R = A.realized;
    var out = banner() + "<h3>Outgoing free agents</h3>" +
      '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Player</th><th>Status</th><th>Prev AAV</th><th>Yrs</th><th>Proj guar</th><th>P10 to P90</th><th>Deal+</th><th>Verdict</th></tr></thead><tbody>' +
      A.outgoing.map(function (m) {
        return "<tr><td><a href=\"/fa/#view=board\">" + esc(m[1]) + "</a> <span class=\"ledger-src\">" + esc(m[2]) + "</span></td><td>" + esc(m[4]) + " " + esc(m[5]) + "</td><td>" + esc(money(m[6])) + "</td><td>" + esc(m[7]) + "</td><td>" + esc(money(m[8])) + "</td><td>" + esc(money(m[9])) + " to " + esc(money(m[10])) + "</td><td>" + esc(isNum(m[13]) ? Math.round(m[13]) : "") + "</td><td>" + esc(m[14] || "") + "</td></tr>";
      }).join("") + "</tbody></table></div>" +
      '<p class="ledger-count">fa_market ' + esc(A.outgoing_verdicts ? "" : "") + esc((DATA.accountability.registry_verdicts.filter(function (r) { return r.model_id === "fa_market"; })[0] || {}).verdict) + ", fa_projection_marcel " + esc((DATA.accountability.registry_verdicts.filter(function (r) { return r.model_id === "fa_projection_marcel"; })[0] || {}).verdict) + ". Expiring after " + esc(classYear()) + ": " + esc(A.expiring_2028[0]) + " (prev AAV " + esc(money(A.expiring_2028[1])) + "); the winter after: " + esc(A.expiring_2029[0]) + ".</p>";
    out += "<h3>Top fits</h3><div class=\"ledger-chips\">" + A.fits.map(function (f) {
      return '<span class="ledger-flag" title="need ' + esc(num(f[4], 2)) + " window " + esc(num(f[5], 2)) + " afford " + esc(num(f[6], 2)) + '">' + esc(f[1]) + " " + esc(num(f[3], 2)) + "</span>";
    }).join("") + "</div>" + '<p class="ledger-count">' + esc(copy("fits_note")) + '. <a href="' + esc(d.links.fa_fits) + '">FA fits</a></p>';
    var pr = A.priors || [];
    out += '<div class="ledger-tiles ledger-tiles--2">' + tile("Largest guarantee", money(pr[0]), esc(copy("priors_basis"))) + tile("Deals of $100M+", esc(pr[1]), esc(copy("priors_basis"))) +
      tile("Three-winter outlay", money(pr[2]), esc(copy("priors_basis"))) + tile("Winters on file", esc(A.winters.length), "fa_archive") + "</div>";
    out += "<h3>Spend by winter</h3>" + '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Winter</th><th>Signed</th><th>Spend</th><th>Mean AAV</th><th>QO</th><th>Departed</th><th>Guar elsewhere</th><th>League ' + gl("$/WAR", "winter_dpw") + "</th></tr></thead><tbody>" +
      A.winters.slice().reverse().map(function (w) {
        return "<tr><td>" + esc(w[0]) + "</td><td>" + esc(w[1]) + "</td><td>" + esc(money(w[2])) + "</td><td>" + esc(money(w[3])) + "</td><td>" + esc(w[4]) + "</td><td>" + esc(w[5]) + "</td><td>" + esc(money(w[6])) + "</td><td>" + esc(money(w[7])) + "</td></tr>";
      }).join("") + "</tbody></table></div>" + '<p class="ledger-count">' + esc(copy("implied_dpw_note")) + "</p>";
    out += "<h3>" + gl(copy("realized_title"), "realized_contract_value") + "</h3>" +
      '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Winter</th><th>Covered</th><th>WAR to date</th><th>Paid to date</th><th>Value delivered</th><th>Surplus to date<span class="ledger-th-tag">realized</span></th></tr></thead><tbody>' +
      R.by_winter.slice().reverse().map(function (w) {
        return "<tr><td>" + esc(w[0]) + "</td><td>" + esc(w[2]) + " of " + esc(w[1]) + "</td><td>" + esc(num(w[3], 1)) + "</td><td>" + esc(money(w[4])) + "</td><td>" + esc(money(w[6])) + "</td><td>" + signedMoney(w[5]) + "</td></tr>";
      }).join("") + "</tbody></table></div>" +
      '<p class="ledger-count">Method ' + esc(copy("realized_method")) + ". " + esc(copy("realized_coverage")) + "</p>" +
      '<p class="ledger-note">' + esc(copy("realized_sentence")) + "</p>";
    return out;
  }
  // A generic dt/dd for every column of a row (the expander lists them all),
  // formatted by the column's suffix: _mm in $M, _usd in dollars, booleans as
  // words. Nothing is summed here.
  function rowDl(key, row) {
    var cols = (DATA.columns || {})[key] || [];
    return cols.map(function (n, i) {
      var v = row[i], txt;
      if (v === true) txt = "yes";
      else if (v === false) txt = "no";
      else if (/_mm$/.test(n)) txt = moneyMM(v);
      else if (/_usd$/.test(n)) txt = money(v);
      else if (Array.isArray(v)) txt = v.length ? v.join(", ") : "";
      else txt = isNum(v) || v ? String(v) : "";
      return dd(n, esc(txt));
    }).join("");
  }
  // ---- C7a Farm ledger: every active prospect on the eFV basis -------------
  // NO RULER CALL IN THIS FUNCTION. A surplus cell prints plain with a sign, a
  // grade letter in neutral ink, the band per row, and the footer sums means
  // over the rows SHOWN while the band column's footer reads "not summed".
  function renderProspects(d) {
    var F = d.farm, sh = shardOf(d.club), L = "farm.prospects";
    var full = !!(sh && sh.farm && sh.farm.prospects);
    var rows = full ? sh.farm.prospects : (F.preview || []);
    if (!F.preview && !full) return dark("Farm ledger", copy("shard_failed") || "no prospect rows on this board");
    var Rf = F.reconciliation || {}, traj = (sh && sh.farm && sh.farm.prospect_trajectory) || {};
    var out = banner() + '<p class="ledger-note">' + esc(F.n_prospects) + " active prospects, " + esc(Rf.n_with_bonus) + " with a bonus on file; eFV surplus is an expected value, bands per row.</p>";
    out += '<p class="ledger-count">' + esc(copy("farm_dollar_is")) + " " + esc(copy("farm_dollar_is_not")) + "</p>";
    out += shardLine(d.club, copy("preview_note"));
    var f = state.pfilter || "all";
    out += '<div class="ledger-chips" role="group" aria-label="Acquisition method">' + [["all", "all"], ["draft", "draft"], ["international_fa", "IFA"]].map(function (c) {
      return '<button type="button" class="ledger-chip' + (f === c[0] ? " is-on" : "") + '" data-lfilter="' + c[0] + '" aria-pressed="' + (f === c[0] ? "true" : "false") + '">' + esc(c[1]) + "</button>";
    }).join("") + "</div>";
    var shown = rows.filter(function (r) { return f === "all" || cv("farm.prospects", r, "acq_method") === f; });
    var head = "<tr><th>Player</th><th>" + gl("Expected surplus", "tvi") + "</th><th>" + gl("Band", "surplus_value") + '</th><th class="lc-col-hide">' + gl("eFV", "xfv") + '</th><th class="lc-col-hide">' + gl("Bonus", "signing_bonus") +
      '</th><th class="lc-col-hide">' + gl("Slot", "slot_value") + '</th><th class="lc-col-hide">' + gl("Net", "acquisition_cost_basis") + '</th><th class="lc-col-hide">Acquired</th><th class="lc-col-hide">' + gl("ETA", "eta") +
      ' / phase</th><th class="lc-col-hide">' + gl("Crunch", "roster_crunch") + '</th><th class="lc-col-hide">' + gl("$DvM+", "fin_dollar_dvm") + '</th><th class="lc-xp"></th></tr>';
    var sums = { s: 0, b: 0, n: 0 };
    var body = shown.map(function (r) {
      var key = cv("farm.prospects", r, "key"), s = cv("farm.prospects", r, "surplus_mm"), bonus = cv("farm.prospects", r, "bonus_usd"), slot = cv("farm.prospects", r, "slot_usd"), net = cv("farm.prospects", r, "net_mm"), method = cv("farm.prospects", r, "acq_method"), pick = cv("farm.prospects", r, "pick_overall"), dvm = cv("farm.prospects", r, "dollar_dvm_plus");
      sums.s += Number(s || 0); sums.b += Number(bonus || 0); sums.n += Number(net || 0);
      var k = "P:" + key, open = !!state.open[k];
      var crunch = yn(cv("farm.prospects", r, "on_40_man"), "40-man") + (isNum(cv("farm.prospects", r, "options_left")) ? '<span class="ledger-flag">' + esc(cv("farm.prospects", r, "options_left")) + " opt</span>" : "") + yn(cv("farm.prospects", r, "rule5_exposed"), "Rule 5");
      var row = '<tr id="ledger-prospect-' + esc(key) + '"><td><a href="/prospx/#player=' + esc(key) + '">' + esc(cv("farm.prospects", r, "name")) + '</a> <span class="ledger-src">' + esc(cv("farm.prospects", r, "pos")) + "</span> " + letter(cv("farm.prospects", r, "tv_grade")) + "</td>" +
        "<td>" + signedMM(s) + "</td><td>" + bandMM(cv("farm.prospects", r, "band_lo_mm"), cv("farm.prospects", r, "band_hi_mm"), copy("band_row_only")) + "</td>" +
        '<td class="lc-col-hide">' + esc(num(cv("farm.prospects", r, "efv"), 1)) + "</td>" +
        '<td class="lc-col-hide">' + esc(isNum(bonus) ? money(bonus) : "no bonus on file") + "</td>" +
        (isNum(slot) ? '<td class="lc-col-hide">' + esc(money(slot)) + "</td>"
          : (method === "international_fa" ? '<td class="lc-col-hide" title="' + esc(copy("ifa_slot_dark")) + '">' + esc(String(copy("ifa_slot_dark")).split(":")[0]) + "</td>" : '<td class="lc-col-hide"></td>')) +
        '<td class="lc-col-hide">' + signedMM(net) + "</td>" +
        '<td class="lc-col-hide">' + esc((method || "") + " " + (cv("farm.prospects", r, "acq_year") || "") + (isNum(pick) ? ", pick " + pick : "")) + "</td>" +
        '<td class="lc-col-hide">' + esc((cv("farm.prospects", r, "eta_year") || "") + " / " + (cv("farm.prospects", r, "service_phase") || "")) + "</td>" +
        '<td class="lc-col-hide">' + crunch + "</td>" +
        '<td class="lc-col-hide" title="' + esc(copy("dvm_within_tier")) + '">' + esc(isNum(dvm) ? Math.round(dvm) : "") + "</td>" + xpBtn(k) + "</tr>";
      if (open) {
        var cur = cv("farm.prospects", r, "cur_method"), cy = cv("farm.prospects", r, "cur_year");
        row += '<tr class="ledger-xp-row"><td colspan="12"><dl class="ledger-dl">' + rowDl(L, r) +
          dd("PROSPX consensus basis, not added", esc(moneyMM(cv("farm.prospects", r, "cons_surplus_mm"))) + " (" + bandMM(cv("farm.prospects", r, "cons_lo_mm"), cv("farm.prospects", r, "cons_hi_mm"), copy("band_row_only")) + ")") +
          dd("P(bust)", esc(num(cv("farm.prospects", r, "p_bust"), 2)) + '<div class="ledger-count">' + esc(copy("p_bust_basis")) + "</div>") +
          dd("Current acquisition", esc((cur || "") + (cy ? " " + cy : "")) + (cur === "trade" || cur === "free_agent" ? " (" + esc(cur) + " event; the original signing channel is the method column)" : "")) +
          dd("Years to free agency", esc(copy("years_to_fa_dark"))) +
          (traj[key] && traj[key].length > 1 ? dd("eFV surplus trajectory", spark(traj[key], 1)) : "") +
          "</dl></td></tr>";
      }
      return row;
    }).join("");
    var foot = "<tr><td>" + esc(copy("shown_rows")) + " (" + esc(shown.length) + ")</td><td>" + esc(moneyMM(sums.s)) + "</td><td>" + notSummed() + "</td>" +
      '<td class="lc-col-hide"></td><td class="lc-col-hide">' + esc(money(sums.b)) + '</td><td class="lc-col-hide"></td><td class="lc-col-hide">' + signedMM(sums.n) + '</td><td class="lc-col-hide" colspan="4"></td><td class="lc-xp"></td></tr>';
    out += '<div class="ledger-scroll"><table class="ledger-table ledger-prospects"><thead>' + head + "</thead><tbody>" + body + "</tbody><tfoot>" + foot + "</tfoot></table></div>";
    out += '<p class="ledger-count">' + esc(copy("dvm_within_tier")) + " " + esc(copy("years_to_fa_dark")) + (copy("service_time_source") ? " (" + esc(copy("service_time_source")) + ")" : "") + "</p>";
    return out;
  }
  // ---- C7b Graduates: two engines per row, each under its own name ---------
  function renderGraduates(d) {
    var F = d.farm, sh = shardOf(d.club), L = "farm.graduates";
    var rows = (sh && sh.farm && sh.farm.graduates) || null;
    var leaf = (F.leaves || {}).fin_contract_surplus || {};
    var out = banner() + '<p class="ledger-note">' + esc(F.n_graduates) + " graduates on the debuted rows. " + esc(copy("grad_two_engines")) + " " + esc(copy("grad_no_registry")) + "</p>";
    out += '<p class="ledger-count">' + gl("Grad-Contract Surplus", "fin_contract_surplus") + " org mean " + esc(money(leaf.value)) + " per year (n " + esc(leaf.n) + ")</p>" +
      dark("Grad-Contract Surplus per graduate", copy("grad_contract_dark"));
    if (!rows) return out + shardLine(d.club, copy("grad_preview_note"));
    out += shardLine(d.club, copy("grad_preview_note"));
    var head = "<tr><th>Player</th><th>" + gl("Debut", "mlb_debut") + "</th><th>" + gl("Debuted value", "debuted_value") + '</th><th class="lc-col-hide">' + gl("Trade board", "trade_machine") + '</th><th class="lc-col-hide">Acquired</th><th class="lc-col-hide">' + gl("Bonus", "signing_bonus") +
      '</th><th class="lc-col-hide">Realized<span class="ledger-th-tag">realized</span></th><th class="lc-col-hide">' + gl("Control", "club_control_window") + '</th><th class="lc-col-hide">Career WAR</th><th class="lc-col-hide">' + gl("WAG", "wag") + '</th><th class="lc-xp"></th></tr>';
    var body = rows.map(function (r) {
      var key = cv("farm.graduates", r, "key"), k = "G:" + key, open = !!state.open[k], inv = cv("farm.graduates", r, "in_vets");
      var href = inv ? "/projections/#player=" + esc(key) : "/prospx/#player=" + esc(key);
      var row = '<tr><td><a href="' + href + '">' + esc(cv("farm.graduates", r, "name")) + '</a> <span class="ledger-src">' + esc(cv("farm.graduates", r, "pos")) + "</span></td><td>" + esc(cv("farm.graduates", r, "debut_date") || "") + "</td>" +
        "<td>" + esc(moneyMM(cv("farm.graduates", r, "dv_trade_value_mm"))) + ' <span class="ledger-src">PROSPX debuted_player_value</span></td>' +
        '<td class="lc-col-hide">' + esc(moneyMM(cv("farm.graduates", r, "tv_trade_value_mm"))) + (cv("farm.graduates", r, "tv_surplus_source") ? ' <span class="ledger-src">' + esc(cv("farm.graduates", r, "tv_surplus_source")) + "</span>" : "") + "</td>" +
        '<td class="lc-col-hide">' + esc((cv("farm.graduates", r, "acq_method") || "") + " " + (cv("farm.graduates", r, "acq_year") || "")) + "</td>" +
        '<td class="lc-col-hide">' + esc(isNum(cv("farm.graduates", r, "bonus_usd")) ? money(cv("farm.graduates", r, "bonus_usd")) : "no bonus on file") + "</td>" +
        '<td class="lc-col-hide">' + esc(moneyMM(cv("farm.graduates", r, "dv_realized_mm"))) + "</td>" +
        '<td class="lc-col-hide">' + esc(isNum(cv("farm.graduates", r, "control_thru")) ? "thru " + cv("farm.graduates", r, "control_thru") : "") + (cv("farm.graduates", r, "control_why") ? ' <span class="ledger-src">' + esc(cv("farm.graduates", r, "control_why")) + "</span>" : "") + " " + esc(cv("farm.graduates", r, "service_phase") || "") + "</td>" +
        '<td class="lc-col-hide">' + esc(num(cv("farm.graduates", r, "career_war"), 1)) + "</td>" +
        '<td class="lc-col-hide">' + esc(cv("farm.graduates", r, "wag_label") || "") + "</td>" + xpBtn(k) + "</tr>";
      if (open) row += '<tr class="ledger-xp-row"><td colspan="11"><dl class="ledger-dl">' + rowDl(L, r) + dd("Engines", esc(copy("grad_two_engines"))) + "</dl></td></tr>";
      return row;
    }).join("");
    out += '<div class="ledger-scroll"><table class="ledger-table ledger-graduates"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>" +
      '<p class="ledger-count">' + esc(copy("realized_not_skill")) + " No total is printed for either engine.</p>";
    return out;
  }
  // ---- C6b Trade board, debuted rows ---------------------------------------
  // NO RULER CALL IN THIS FUNCTION. Trade value plain, band per row, tier and
  // grade in neutral ink, the footer a sum of expected values over shown rows.
  function renderTrade(d) {
    var S = d.surplus, sh = shardOf(d.club), L = "surplus.rows_debuted";
    var rows = (sh && sh.surplus && sh.surplus.rows_debuted) || null;
    var out = banner() + '<p class="ledger-note">' + esc(S.n_debuted_rows) + " debuted rows on the trade board; the active rows are the farm ledger's prospect rows and are not repeated. " + esc(copy("trade_currency_basis")) + "</p>";
    if (!rows) return out + shardLine(d.club, copy("trade_preview_note"));
    out += shardLine(d.club, copy("trade_preview_note"));
    var head = "<tr><th>Player</th><th>" + gl("Trade value", "trade_machine") + "</th><th>" + gl("Band", "surplus_value") + '</th><th class="lc-col-hide">Tier</th><th class="lc-col-hide">Grade</th><th class="lc-col-hide">Source</th><th class="lc-col-hide">' + gl("Salary basis", "salary_path") + '</th><th class="lc-col-hide">' + gl("Control", "club_control_window") + '</th><th class="lc-xp"></th></tr>';
    var sum = 0;
    var body = rows.map(function (r) {
      var key = cv("surplus.rows_debuted", r, "key"), k = "T:" + key, open = !!state.open[k], v = cv("surplus.rows_debuted", r, "tv_mm"), src = cv("surplus.rows_debuted", r, "surplus_source");
      sum += Number(v || 0);
      var href = cv("surplus.rows_debuted", r, "in_contract_rows") ? "/projections/#player=" + esc(key) : "/prospx/#player=" + esc(key);
      var row = '<tr><td><a href="' + href + '">' + esc(cv("surplus.rows_debuted", r, "name")) + '</a> <span class="ledger-src">' + esc(cv("surplus.rows_debuted", r, "pos")) + "</span></td><td>" + signedMM(v) + "</td><td>" + bandMM(cv("surplus.rows_debuted", r, "tv_lo_mm"), cv("surplus.rows_debuted", r, "tv_hi_mm"), bandCopy(src === "projection" || src === "prearb_min")) + "</td>" +
        '<td class="lc-col-hide">' + letter(cv("surplus.rows_debuted", r, "tv_tier")) + '</td><td class="lc-col-hide">' + letter(cv("surplus.rows_debuted", r, "tv_grade")) + '</td><td class="lc-col-hide"><span class="ledger-src">' + esc(src || "") + "</span></td>" +
        '<td class="lc-col-hide">' + esc(cv("surplus.rows_debuted", r, "salary_basis") || "") + '</td><td class="lc-col-hide">' + esc((cv("surplus.rows_debuted", r, "control_thru") || "") + " " + (cv("surplus.rows_debuted", r, "control_why") || "")) + "</td>" + xpBtn(k) + "</tr>";
      if (open) row += '<tr class="ledger-xp-row"><td colspan="9"><dl class="ledger-dl">' + rowDl(L, r) + (src === "prearb_min" ? dd("Floor", esc(copy("prearb_min_floor"))) : "") + "</dl></td></tr>";
      return row;
    }).join("");
    var foot = "<tr><td>" + esc(copy("shown_rows")) + " (" + esc(rows.length) + ")</td><td>" + esc(moneyMM(sum)) + "</td><td>" + notSummed() + '</td><td class="lc-col-hide" colspan="5"></td><td class="lc-xp"></td></tr>';
    out += '<div class="ledger-scroll"><table class="ledger-table ledger-trade"><thead>' + head + "</thead><tbody>" + body + "</tbody><tfoot>" + foot + "</tfoot></table></div>";
    return out;
  }
  function renderLinks(d) {
    var L = d.links, labels = {
      farm_tree: "Farm system tree", org_tendencies: "Org tendencies", farm_board: "Farm board", ifa_board: "IFA board", draft_board: "Draft board",
      roster_board: "Roster board", team_outlook: "Team Outlook", fa_fits: "FA fits", fa_archive: "FA archive", arbitration_teams: "Arbitration by club",
      trade_board: "Trade board", mlbstats_war: "MLB Stats: eWAR by club", mlbstats_bullpen: "MLB Stats: bullpen by club", betting_teams: "Betting teams",
      fantasy_dynasty: "Fantasy dynasty", management_club: "In-Game Management", franchise: "Franchise hub" };
    return '<div class="ledger-links">' + Object.keys(labels).map(function (k) {
      return L[k] ? '<a href="' + esc(L[k]) + '">' + esc(labels[k]) + "</a>" : "";
    }).join("") + "</div>";
  }
  function block(id, eyebrow, title, span, inner) {
    return '<section class="ledger-block ledger-span-' + span + '" id="ledger-block-' + id + '"><div class="ledger-eyebrow">' + esc(eyebrow) + "</div><h2>" + title + "</h2>" + inner + "</section>";
  }
  function renderClub() {
    ensureTeam();
    var d = clubOf(state.team);
    if (!d) return '<p class="ledger-note">' + esc(copy("load_error")) + "</p>";
    var out = renderControls(d) + "<h2>" + esc(d.club) + (d.name ? " " + esc(d.name) : "") + "</h2>" + banner() + '<div class="ledger-grid">';
    out += block("payroll", "C1", "Payroll now", 12, renderPayroll(d));
    out += block("commitments", "C4", gl("Commitments timeline", "contract_dollars_on_file"), 7, renderCommitments(d));
    out += block("cbt", "C3", gl("CBT position and tax", "cbt_payroll"), 5, renderCbt(d));
    out += block("contracts", "C5", "Contract ledger", 7, renderContracts(d));
    out += block("arbitration", "C5", gl("Arbitration exposure", "arb_exposure"), 5, renderArbitration(d));
    out += block("surplus", "C6", gl("Cost per projected WAR", "cost_plus"), 6, renderSurplus(d));
    out += block("farm", "C7", "Farm capital", 6, renderFarm(d));
    out += block("trade", "C6b", gl("Trade board, debuted", "trade_machine"), 12, renderTrade(d));
    out += block("prospects", "C7a", gl("Farm ledger", "farm_dollar"), 12, renderProspects(d));
    out += block("graduates", "C7b", gl("Graduates", "debuted_value"), 12, renderGraduates(d));
    out += block("fa", "C8", "Free agency ledger", 12, renderFa(d));
    out += block("links", "C9", "Into every module", 12, renderLinks(d));
    out += "</div>" + '<p class="ledger-foot">' + esc(copy("club_foot")) + " " + esc(copy("no_payroll_line")) + "</p>";
    return out;
  }

  // ---- Rules -----------------------------------------------------------------
  function renderRules() {
    var R = DATA.rules, rates = R.rates || {}, br = rates.base_rate_by_payor_year || {}, sr = rates.surcharge_rates || {};
    var out = banner();
    out += "<h3>" + gl("CBT thresholds", "cbt_payroll") + "</h3>" + '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Season</th><th>Threshold</th><th>Regime</th><th>Status</th></tr></thead><tbody>' +
      R.thresholds.map(function (t) { return "<tr><td>" + esc(t.season) + "</td><td>" + esc(money(t.threshold_usd)) + "</td><td>" + esc(t.regime) + "</td><td>" + esc(t.verify_status) + (t.carry_forward ? " (carry-forward)" : "") + "</td></tr>"; }).join("") + "</tbody></table></div>";
    out += "<h3>Tax rates (" + esc(rates.regime) + ")</h3>" + '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Payor year</th><th>Base</th><th>+' + esc(money(R.surcharge_tiers_usd[0])) + "</th><th>+" + esc(money(R.surcharge_tiers_usd[1])) + "</th><th>+" + esc(money(R.surcharge_tiers_usd[2])) + "</th></tr></thead><tbody>" +
      Object.keys(br).map(function (k) {
        var b = Number(br[k]);
        return "<tr><td>" + esc(k) + "</td><td>" + esc(pct(b, 0)) + "</td><td>" + esc(pct(b + Number(sr.tier1), 0)) + "</td><td>" + esc(pct(b + Number(k === "1" ? sr.tier2_first : sr.tier2_repeat), 1)) + "</td><td>" + esc(pct(b + Number(sr.tier3), 0)) + "</td></tr>";
      }).join("") + "</tbody></table></div>" + '<p class="ledger-count">' + esc(rates.verify_status) + ". Brackets: " + Object.keys(R.brackets).map(function (k) { return esc(R.brackets[k]); }).join("; ") + "</p>";
    out += "<h3>" + gl("Qualifying offer", "qo_tax") + " values</h3>" + '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Winter</th><th>Class</th><th>Value</th><th>Status</th></tr></thead><tbody>' +
      R.qo_values.map(function (q) { return "<tr><td>" + esc(q.winter) + "</td><td>" + esc(q.class_year) + "</td><td>" + esc(money(q.value_usd)) + "</td><td>" + esc(q.verify_status) + "</td></tr>"; }).join("") + "</tbody></table></div>";
    var qc = R.qo_compensation || {}, mat = qc.signing_team_forfeits || {};
    out += "<h3>QO compensation matrix" + (qc.carry_forward ? " (carry-forward)" : "") + "</h3><table class=\"ledger-mini\">" + Object.keys(mat).map(function (t) {
      var m = mat[t] || {};
      return "<tr><td>" + esc(t) + "</td><td>" + esc((m.picks || []).join(", ")) + (isNum(m.intl_pool_usd) ? "; IFA pool " + esc(money(m.intl_pool_usd)) : "") + "</td></tr>";
    }).join("") + "</table>";
    var qt = R.qo_tax_by_payor_tier || {};
    out += "<h3>QO pick tax by payor tier (platform)</h3><table class=\"ledger-mini\">" + Object.keys(qt).map(function (t) {
      return "<tr><td>" + esc(t) + "</td><td>" + esc(money((qt[t] || {}).total_usd)) + "</td></tr>";
    }).join("") + "</table>" + '<p class="ledger-count">' + esc(copy("qo_recipient_note")) + "</p>";
    out += "<h3>" + gl("League minimum", "pre_arbitration") + "</h3><table class=\"ledger-mini\">" + R.league_minimum.map(function (m) { return "<tr><td>" + esc(m.season) + "</td><td>" + esc(usdFull(m.usd)) + "</td></tr>"; }).join("") + "</table>" +
      '<p class="ledger-count">' + esc(copy("league_minimum_note")) + "</p>";
    out += "<h3>Dollars per WAR</h3>" + renderDpw(R.dpw) +
      '<p class="ledger-note">Arbitration discount ' + esc(seasonNow()) + ": " + esc(num(R.dpw.arbitration_discount_2026, 2)) + " (" + esc(copy("arb_dpw_basis")) + "). Projections rate " + esc(money(R.dpw.projections_dpw_usd)) + " (" + esc(copy("projections_dpw_basis")) + ").</p>";
    var wd = R.war_input_divergence || {};
    out += '<p class="ledger-note">Why two WARs for one player: ' + esc(wd.why || "") + " " + esc(wd.consequence || "") + "</p>";
    out += '<p class="ledger-count">' + esc(R.unverified_records.length) + " cba_rules records are curated-unverified. CBA expiry " + esc(R.cba_expiry) + ".</p>";
    return out;
  }
  function renderDpw(D) {
    var years = Object.keys(D.open_market_by_winter).sort();
    var arbYears = Object.keys(D.arbitration_by_season).sort();
    var all = years.concat(arbYears.filter(function (y) { return years.indexOf(y) < 0; })).sort();
    var vals = [];
    all.forEach(function (y) {
      if (isNum(D.open_market_by_winter[y])) vals.push(Number(D.open_market_by_winter[y]));
      if (isNum(D.arbitration_by_season[y])) vals.push(Number(D.arbitration_by_season[y]));
    });
    if (!vals.length) return "";
    var W = 560, H = 220, padL = 52, padR = 16, padT = 12, padB = 30;
    var lo = 0, hi = Math.max.apply(null, vals) / 1e6;
    var yt = niceTicks(lo, hi, 4);
    hi = yt[yt.length - 1];
    function X(i) { return padL + i / Math.max(1, all.length - 1) * (W - padL - padR); }
    function Y(v) { return H - padB - (v / 1e6 - lo) / (hi - lo || 1) * (H - padT - padB); }
    var g = "";
    yt.forEach(function (v) { g += '<line class="lq-grid" x1="' + padL + '" x2="' + (W - padR) + '" y1="' + Y(v * 1e6) + '" y2="' + Y(v * 1e6) + '"/><text x="' + (padL - 6) + '" y="' + (Y(v * 1e6) + 3) + '" text-anchor="end">' + esc(v) + "</text>"; });
    all.forEach(function (y, i) { if (i % 2 === 0) g += '<text x="' + X(i) + '" y="' + (H - padB + 14) + '" text-anchor="middle">' + esc(y) + "</text>"; });
    function line(map, cls) {
      var pts = [];
      all.forEach(function (y, i) { if (isNum(map[y])) pts.push(X(i).toFixed(1) + "," + Y(map[y]).toFixed(1)); });
      return pts.length ? '<polyline class="' + cls + '" points="' + pts.join(" ") + '"/>' : "";
    }
    g += line(D.open_market_by_winter, "ld-open") + line(D.arbitration_by_season, "ld-arb");
    var lastO = years[years.length - 1], lastA = arbYears[arbYears.length - 1];
    g += '<text x="' + (X(all.indexOf(lastO)) - 4) + '" y="' + (Y(D.open_market_by_winter[lastO]) - 6) + '" text-anchor="end">open market</text>';
    g += '<text x="' + (X(all.indexOf(lastA)) - 4) + '" y="' + (Y(D.arbitration_by_season[lastA]) + 12) + '" text-anchor="end">arbitration</text>';
    var table = '<table class="ledger-mini">' + all.map(function (y) {
      return "<tr><td>" + esc(y) + "</td><td>open " + esc(money(D.open_market_by_winter[y])) + (isNum(D.arbitration_by_season[y]) ? ", arb " + esc(money(D.arbitration_by_season[y])) : "") + "</td></tr>";
    }).join("") + "</table>";
    return '<div class="ledger-dpw"><svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="dollars per WAR, open market and arbitration, in $M">' + g + "</svg>" +
      '<div class="ledger-legend"><span><i class="ledger-seg-contract"></i>open market (' + esc(D.open_market_method) + ")</span><span><i class=\"ledger-seg-arb\"></i>arbitration (arbitration.json dpw)</span></div>" + table + "</div>";
  }

  // ---- Method -----------------------------------------------------------------
  function renderMethod() {
    var M = DATA.method, A = DATA.accountability;
    var out = "<h3>Sources and cadence</h3>" + '<div class="ledger-scroll"><table class="ledger-table"><thead><tr>' + M.source_key.map(function (k) { return "<th>" + esc(k) + "</th>"; }).join("") + "</tr></thead><tbody>" +
      M.sources.map(function (s) { return "<tr>" + s.map(function (v) { return "<td>" + esc(v) + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody></table></div>";
    out += "<h3>Registry verdicts quoted on this page</h3>" + '<div class="ledger-scroll"><table class="ledger-table"><thead><tr><th>Model</th><th>Verdict</th><th>Eval artifact</th><th>Last checked</th><th>Stale</th></tr></thead><tbody>' +
      A.registry_verdicts.map(function (r) { return "<tr><td>" + esc(r.model_id) + "</td><td>" + esc(r.verdict || "no row") + "</td><td>" + esc(r.eval_artifact || "none") + "</td><td>" + esc(r.last_checked || "") + "</td><td>" + esc(r.stale === null || r.stale === undefined ? "" : String(r.stale)) + "</td></tr>"; }).join("") + "</tbody></table></div>";
    out += banner();
    var sp = A.salary_path_census || {};
    out += "<h3>" + gl("Salary path", "salary_path") + " census</h3><table class=\"ledger-mini\">" + ["mode", "vintage", "priced_rows", "board_rows", "cliff_rows", "band_rows", "cba_floored_steps"].map(function (k) {
      return "<tr><td>" + esc(k) + "</td><td>" + esc(sp[k]) + "</td></tr>";
    }).join("") + "<tr><td>contract disagreements (S5 vs trade board)</td><td>" + esc(A.contract_disagreements) + "</td></tr></table>" +
      '<p class="ledger-count">' + esc(A.contract_disagreement_rule) + ". " + esc(A.contract_set_note) + "</p>";
    var oj = A.org_join || {};
    out += "<h3>Club join</h3><table class=\"ledger-mini\">" + Object.keys(oj).map(function (k) { return "<tr><td>" + esc(k) + "</td><td>" + esc(Array.isArray(oj[k]) ? oj[k].join(" to ") : oj[k]) + "</td></tr>"; }).join("") + "</table>";
    out += "<h3>What this page does not claim</h3><ul>" + DATA.what_this_page_does_not_claim.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ul>";
    out += "<h3>Sections</h3><table class=\"ledger-mini\">" + Object.keys(DATA.sections).map(function (k) {
      var s = DATA.sections[k];
      return "<tr><td>" + esc(k) + "</td><td>" + esc(s.live ? "live" : "dark: " + (s.blocked_on || s.note || "")) + "</td></tr>";
    }).join("") + "</table>";
    out += "<h3>Inputs</h3><table class=\"ledger-mini\">" + Object.keys(M.inputs_generated_at).map(function (k) { return "<tr><td>" + esc(k) + "</td><td>" + esc(M.inputs_generated_at[k] || "") + "</td></tr>"; }).join("") + "</table>" +
      '<p class="ledger-count">Board generated ' + esc(DATA.generated_at) + "</p>";
    var C = DATA.calibration;
    if (C && C.sources) {
      out += "<h3>Calibration stamps</h3><table class=\"ledger-mini\">" + Object.keys(C.sources).map(function (k) { return "<tr><td>" + esc(k) + " (" + esc(C.sources[k].generated_at || "") + ")</td><td>" + esc(C.sources[k].version || "unstamped") + "</td></tr>"; }).join("") +
        "<tr><td>agree</td><td>" + esc(C.agree ? "yes" : "no") + "</td></tr></table>" + '<p class="ledger-count">' + esc(M.sources_stamps || "") + "</p>";
    }
    var Sh = DATA.shards;
    if (Sh) {
      out += "<h3>Per-club row files</h3>" + '<p class="ledger-count">' + esc(Sh.n) + " files in data/" + esc(Sh.dir) + "/, preview " + esc(Sh.preview_n) + " rows per block on the board, cap " + esc(Sh.cap_bytes) + " bytes per file; the club page fetches one on demand and flags a file from another board build.</p>";
    }
    if (DATA.arbitration_eval && DATA.arbitration_eval.statement) {
      var E = DATA.arbitration_eval;
      out += "<h3>Arbitration a6 arm (MLBTR / Swartz)</h3>" + '<p class="ledger-count">n ' + esc(E.n) + ", ours MdAPE " + esc(num(E.ours_mdape, 4)) + ", Swartz MdAPE " + esc(num(E.swartz_mdape, 4)) + ", ratio " + esc(num(E.ratio_ours_over_swartz, 3)) + ", verdict " + esc(E.verdict) + ". " + esc(E.claim) + "</p>" +
        '<p class="ledger-note">' + esc(E.statement) + "</p>";
    }
    if (M.grad_contract_formula) out += '<p class="ledger-count">Grad-Contract Surplus, ' + esc(M.grad_contract_formula) + "</p>";
    return out;
  }

  // ---- render and wire ----------------------------------------------------------
  function syncTabs() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-ledgersection]"), function (b) {
      var on = b.getAttribute("data-ledgersection") === state.section;
      if (b.classList) b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  function render() {
    var root = el("ledger-app-root");
    if (!root) return;
    if (!DATA) {
      root.innerHTML = '<p class="ledger-note">' + esc(LOAD_ERROR || "Loading") + "</p>";
      return;
    }
    var m = el("ledger-masthead");
    if (m) m.textContent = copy("masthead");
    var s = state.section;
    if (SECTIONS.indexOf(s) < 0) s = "league";
    if (s === "club") root.innerHTML = renderClub();
    else if (s === "rules") root.innerHTML = renderRules();
    else if (s === "method") root.innerHTML = renderMethod();
    else root.innerHTML = renderLeague();
    if (s === "club" && state.team) {
      // the hash's block key: scroll to the named block once per team
      if (state.block && SCROLLED !== state.team + ":" + state.block) {
        SCROLLED = state.team + ":" + state.block;
        try { var blk = el("ledger-block-" + state.block); if (blk && blk.scrollIntoView) blk.scrollIntoView(); } catch (e) { /* optional */ }
      }
      // the per-club rows, fetched AFTER the preview has painted
      ensureShard(state.team);
    }
    // The CSV control on the mount (build_site's data-csv-export opt-in)
    // exports the table marked data-csv-primary: the League board, or the
    // club's contract ledger. The file name says which one it holds.
    try {
      root.setAttribute("data-csv-export", "club-ledger-" + (s === "club" ? String(state.team).toLowerCase() + "-contracts" : s));
    } catch (e) { /* the host attribute is a courtesy */ }
    syncTabs();
    wire();
    try { if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(root); } catch (e) { /* glossary optional */ }
  }
  function wire() {
    var sel = el("ledger-club");
    if (sel && sel.addEventListener) sel.addEventListener("change", function () { state.team = this.value; state.open = {}; writeHash(); render(); });
    Array.prototype.forEach.call(document.querySelectorAll('input[name="ledger-season"]'), function (r) {
      r.addEventListener("change", function () { if (this.checked) { state.season = this.value; writeHash(); render(); } });
    });
    Array.prototype.forEach.call(document.querySelectorAll("th[data-lsort]"), function (th) {
      function go() {
        var k = th.getAttribute("data-lsort");
        if (state.sort.key === k) state.sort.asc = !state.sort.asc;
        else { state.sort.key = k; state.sort.asc = !!TEXT_COLS[k]; }
        render();
      }
      th.addEventListener("click", go);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-lxp]"), function (b) {
      b.addEventListener("click", function () {
        var k = b.getAttribute("data-lxp");
        state.open[k] = !state.open[k];
        render();
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-lfilter]"), function (b) {
      b.addEventListener("click", function () { state.pfilter = b.getAttribute("data-lfilter") || "all"; render(); });
    });
    // a draft pick that is still an active prospect: open its farm ledger row
    Array.prototype.forEach.call(document.querySelectorAll("a[data-lprospect]"), function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        var k = a.getAttribute("data-lprospect");
        state.block = "prospects"; state.pfilter = "all"; state.open["P:" + k] = true; SCROLLED = "";
        writeHash(); render();
        try { var row = el("ledger-prospect-" + k); if (row && row.scrollIntoView) row.scrollIntoView(); } catch (err) { /* optional */ }
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("a[data-llink]"), function (a) {
      a.addEventListener("click", function (e) {
        var href = a.getAttribute("href") || "";
        if (href.indexOf("#") !== 0) return;
        e.preventDefault();
        try { if (typeof history !== "undefined" && history.replaceState) history.replaceState(null, "", href); } catch (err) { /* optional */ }
        readHash();
        render();
        try { if (typeof window !== "undefined" && window.scrollTo) window.scrollTo(0, 0); } catch (err) { /* optional */ }
      });
    });
  }
  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-ledgersection]"), function (b) {
      b.addEventListener("click", function () {
        state.section = this.getAttribute("data-ledgersection");
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
      .then(function (d) { DATA = d; readHash(); ensureTeam(); render(); })
      .catch(function () { LOAD_ERROR = "The Club Ledger could not be loaded."; render(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
