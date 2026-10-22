/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// xM$ (Expected Market $) and Fair $ on the site's surfaces (task
// XM_3_SURFACES_DARK; owner decisions XM-1 to XM-4 of 2026-10-19).
//
// This file is loaded by a page only when build_site's xm display flag is on
// (xm_export.XM_DISPLAY_ON), so with the flag off no page references it and no
// page changes. It reads the two exported files and decorates the page that
// loaded it: it never touches a module's own script, so a module keeps working
// if this file fails to load or the data is absent.
//
//   player cards      /projections/ player tiles, /prospx/ player overview tiles
//   boards            /prospx/ row chip and two sort options, /mlbstats/ sortable
//                     xM$ column, /fa/ xM$ column beside the predicted contract,
//                     /arbitration/ projected next-rung salary as a share of xM$
//   club roll-ups     /ledger/ roster xM$ and farm Fair $ only (payroll on file
//                     beside the roster sum, not a payroll projection);
//                     /franchise/ roster, market-rate surplus over control and farm
//   Trade Machine     each side's xM$ and Fair $ totals and its market-rate
//                     surplus over control
//
// xM$ is what the market would pay (AAV, years and the NPV guarantee, with a
// P10 to P90 band). Fair $ is what the projected production is worth over the
// same term. They are shown side by side and never subtracted. A player who is
// not a free agent is priced as if he were one this winter and is labelled so.
// A prospect shows Fair $ only, the NPV of his eFV WAR path; his xM$ is withheld
// as outside the market model's range (gate section 16, owner answer XM2B-Q1).
// The market-rate surplus is never drawn on the Ledger: a club surplus total is
// on the Club Ledger never-list (owner answer XM2-Q2).
(function () {
  "use strict";

  var PLAYERS_URL = "/data/xm_players.json";
  var CLUBS_URL = "/data/xm_clubs.json";
  var COUNTERFACTUAL = "Priced as if a free agent this winter. No such contract exists; this is a counterfactual price.";
  var XM_WITHHELD = "outside the market model's range";
  var WITHHELD_NOTE = "xM$ withheld: " + XM_WITHHELD + ". The market model is fit on free-agent signings, nearly all by players 29 or older, so it does not price a prospect.";
  var PROSPECT_FAIR = "Fair $ only: the NPV of his eFV WAR path at the winter's market $/WAR and a 7% discount. The path already carries the bust risk, so nothing else is taken off. A counterfactual value, not a contract.";
  var PAYROLL_NOTE = "not a payroll projection";
  var CLIP_NOTE ="Outside the model's training range: the production path was clipped to the range, so read the price as an approximation.";
  var FAIR_NOTE = "Fair $: what the projected production is worth over the same term, at the winter's market $/WAR and a 7% discount. Shown beside xM$, never subtracted from it.";

  var X = { doc: null, clubs: null, byId: {}, byKey: {}, byMlbam: {}, rows: [], cols: null };

  // ---- formatting ---------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function isNum(v) { return typeof v === "number" && isFinite(v); }
  function usd(v) {
    if (!isNum(v)) return "";
    var a = Math.abs(v), s = v < 0 ? "-$" : "$";
    if (a >= 1e9) return s + (a / 1e9).toFixed(2) + "B";
    if (a >= 1e8) return s + Math.round(a / 1e6) + "M";
    if (a >= 1e6) return s + (a / 1e6).toFixed(1) + "M";
    if (a >= 1e3) return s + Math.round(a / 1e3) + "k";
    return s + Math.round(a);
  }
  function yrs(n) { return n + (n === 1 ? " yr" : " yrs"); }

  // ---- the data -----------------------------------------------------------
  function index(doc) {
    var cols = doc.columns, ix = {};
    cols.forEach(function (c, i) { ix[c] = i; });
    X.cols = ix;
    Object.keys(doc.players || {}).forEach(function (id) {
      var a = doc.players[id], r = {};
      cols.forEach(function (c, i) { r[c] = a[i]; });
      r.id = id;
      X.byId[id] = r;
      if (r.key) X.byKey[r.key] = r;
      if (r.mlbam != null) X.byMlbam[String(r.mlbam)] = r;
      X.rows.push(r);
    });
  }
  function find(o) {
    if (!o) return null;
    if (o.key && X.byKey[o.key]) return X.byKey[o.key];
    if (o.mlbam != null && X.byMlbam[String(o.mlbam)]) return X.byMlbam[String(o.mlbam)];
    if (o.id && X.byId[o.id]) return X.byId[o.id];
    return null;
  }
  function hashParam(name) {
    try {
      var h = (location.hash || "").replace(/^#/, "");
      return new URLSearchParams(h).get(name);
    } catch (e) { return null; }
  }

  // ---- text builders ------------------------------------------------------
  function withheld(r) { return !!(r && r.xm_withheld); }
  function cfText(r) { return withheld(r) ? PROSPECT_FAIR : COUNTERFACTUAL; }
  function cfShort(r) { return withheld(r) ? "Fair $ only" : "as if FA"; }
  function xmTip(r) {
    if (withheld(r)) return WITHHELD_NOTE;
    var t = "xM$ (Expected Market $): what the free-agent market would pay. "
      + "AAV " + usd(r.aav) + " (P10 " + usd(r.aav_p10) + " to P90 " + usd(r.aav_p90) + ") for "
      + yrs(r.years) + " (P10 " + r.years_p10 + " to P90 " + r.years_p90 + "), total guarantee "
      + usd(r.total) + " (P10 " + usd(r.total_p10) + " to P90 " + usd(r.total_p90) + ").";
    if (r.cf) t += " " + cfText(r);
    if (r.clip) t += " " + CLIP_NOTE;
    return t;
  }
  function fairTip(r) {
    if (withheld(r)) return PROSPECT_FAIR + " Here " + usd(r.fair) + (r.arrive != null ? ", on a path from " + r.arrive : "") + ".";
    var t = FAIR_NOTE + " Here " + usd(r.fair) + " over " + yrs(r.years) + ".";
    if (r.cf) t += " " + cfText(r);
    return t;
  }
  // "$8.5M x 2 yrs = $17M"
  function xmLine(r) {
    return usd(r.aav) + " x " + yrs(r.years) + " = " + usd(r.total);
  }
  // The two card tiles: xM$ and Fair $, or for a prospect the withheld note and
  // Fair $ alone.
  function cardTiles(r, tile) {
    if (withheld(r)) {
      return tile("xM$", "Withheld", XM_WITHHELD, xmTip(r)) +
        tile("Fair $", usd(r.fair), "eFV WAR path, NPV", fairTip(r));
    }
    return tile("xM$", usd(r.aav) + " AAV", xmLine(r) + (r.cf ? " (" + cfShort(r) + ")" : ""), xmTip(r)) +
      tile("Fair $", usd(r.fair), "over " + yrs(r.years) + (r.cf ? " (" + cfShort(r) + ")" : ""), fairTip(r));
  }
  function cfTag(r) {
    return r.cf ? ' <span class="xm-cf" title="' + esc(cfText(r)) + '">' + esc(cfShort(r)) + "</span>" : "";
  }

  // ---- styles (tokens only, so the page's own themes apply) ----------------
  function addStyle() {
    if (document.getElementById("xm-style")) return;
    var s = document.createElement("style");
    s.id = "xm-style";
    s.textContent =
      ".xm-cf{display:inline-block;font-size:.72em;letter-spacing:.02em;text-transform:uppercase;color:var(--text-secondary,#4A5468);border:1px solid var(--border,#C9C1AE);padding:0 .3em;margin-left:.3em;vertical-align:middle;white-space:nowrap}" +
      ".xm-chip{display:inline-flex;flex-wrap:wrap;gap:.2em .6em;align-items:baseline;font-size:11px;color:var(--text-secondary,#4A5468);margin-top:2px}" +
      ".xm-chip b{color:var(--text-primary,#0F1B2D);font-weight:600}" +
      ".xm-chip a,.xm-help{color:inherit}" +
      ".xm-pair{display:inline-flex;gap:.3em .9em;flex-wrap:wrap;align-items:baseline}" +
      ".xm-block{margin-top:14px}" +
      ".xm-block h3,.xm-block h2{margin:0 0 6px}" +
      ".xm-table{border-collapse:collapse;width:100%;font-size:13px}" +
      ".xm-table th,.xm-table td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--border-light,#E2DCC9);vertical-align:top}" +
      ".xm-table td.xm-n,.xm-table th.xm-n{text-align:right;font-variant-numeric:tabular-nums}" +
      ".xm-note{font-size:12px;color:var(--text-secondary,#4A5468);margin:6px 0 0;max-width:70ch}" +
      ".xm-col{white-space:nowrap;font-variant-numeric:tabular-nums}" +
      "th.xm-col{cursor:pointer}" +
      ".xm-tm{display:flex;flex-wrap:wrap;gap:2px 12px;font-size:12px;color:var(--text-secondary,#4A5468);padding:2px 0 4px}" +
      ".xm-tm b{color:var(--text-primary,#0F1B2D);font-weight:600}" +
      ".xm-tile-sub{display:block}" +
      "@media (max-width:480px){.xm-chip{font-size:10px}.xm-table{font-size:12px}.xm-table th,.xm-table td{padding:3px 5px}}";
    document.head.appendChild(s);
  }

  // ---- surfaces: player cards ---------------------------------------------
  // /projections/ player page: two tiles after the existing ones.
  function projectionsCard() {
    var key = hashParam("player");
    var tiles = document.querySelector(".mlbp-tiles");
    if (!key || !tiles) return;
    if (tiles.getAttribute("data-xm") === key) return;
    var old = tiles.querySelectorAll("[data-xm-tile]");
    for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    tiles.setAttribute("data-xm", key);
    var r = X.byKey[key];
    if (!r) return;
    tiles.insertAdjacentHTML("beforeend", cardTiles(r, projTile));
  }
  function projTile(label, val, sub, tip) {
    return '<div class="mlbp-tile" data-xm-tile title="' + esc(tip) + '"><span class="mlbp-tile-label">' + esc(label) +
      '</span><span class="mlbp-tile-val">' + esc(val) + '</span><span class="mlbp-tile-sub">' + esc(sub) + "</span></div>";
  }
  // /prospx/ player page: two overview tiles.
  function prospxCard() {
    var key = hashParam("player");
    var grids = document.querySelectorAll(".overview-tile-grid");
    if (!key || !grids.length) return;
    for (var g = 0; g < grids.length; g++) {
      var grid = grids[g];
      if (grid.getAttribute("data-xm") === key) continue;
      var old = grid.querySelectorAll("[data-xm-tile]");
      for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
      grid.setAttribute("data-xm", key);
      var r = X.byKey[key] || X.byId[key];
      if (!r) continue;
      grid.insertAdjacentHTML("beforeend", cardTiles(r, pxTile));
    }
  }
  function pxTile(label, val, sub, tip) {
    return '<div class="overview-tile" data-xm-tile title="' + esc(tip) + '"><div class="ov-tile-label">' + esc(label) +
      '</div><div class="ov-tile-val" style="color:var(--text-primary);">' + esc(val) + '</div><div class="ov-tile-sub">' + esc(sub) + "</div></div>";
  }

  // ---- surfaces: /prospx/ board --------------------------------------------
  function prospxRows() {
    var rows = document.querySelectorAll("#rows .player-row[data-key]");
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i], k = row.getAttribute("data-key");
      if (row.getAttribute("data-xm") === k) continue;
      var old = row.querySelector(".xm-chip");
      if (old) old.parentNode.removeChild(old);
      row.setAttribute("data-xm", k);
      var r = X.byId[k] || X.byKey[k];
      var host = row.querySelector(".player-name-stack");
      if (!r || !host) continue;
      host.insertAdjacentHTML("beforeend",
        '<div class="xm-chip"><span title="' + esc(xmTip(r)) + '">' + (withheld(r) ? "xM$ withheld" : "xM$ <b>" + esc(usd(r.aav)) + "</b> x " + esc(r.years) + "y") + cfTag(r) + "</span>" +
        '<span title="' + esc(fairTip(r)) + '">Fair $ <b>' + esc(usd(r.fair)) + "</b></span></div>");
    }
  }
  var SORTS = { xm_aav: "aav", xm_total: "total", xm_fair: "fair" };
  function prospxSortOptions() {
    var sel = document.getElementById("sort-select");
    if (!sel || sel.querySelector("[data-xm-opt]")) return;
    var g = document.createElement("optgroup");
    g.label = "Market (xM$)";
    [["xm_aav", "xM$ AAV (highest)"], ["xm_total", "xM$ total guarantee (highest)"], ["xm_fair", "Fair $ (highest)"]].forEach(function (o) {
      var op = document.createElement("option");
      op.value = o[0]; op.textContent = o[1]; op.setAttribute("data-xm-opt", "1");
      g.appendChild(op);
    });
    sel.appendChild(g);
    try { if (typeof state !== "undefined" && SORTS[state.sort]) sel.value = state.sort; } catch (e) { /* no state */ }
  }
  // getFilteredActives() returns the filtered, sorted pool; for an xM$ sort it
  // is asked for the default order and then ordered here. No-data rows sink in
  // both directions, as the app's own money sorts do.
  function wrapProspxSort() {
    if (typeof window.getFilteredActives !== "function" || window.getFilteredActives.xmWrapped) return;
    var orig = window.getFilteredActives;
    var wrapped = function () {
      var st;
      try { st = state; } catch (e) { return orig.apply(this, arguments); }
      var field = SORTS[st.sort];
      if (!field) return orig.apply(this, arguments);
      var keep = st.sort, pool;
      st.sort = "xfv";
      try { pool = orig.apply(this, arguments); } finally { st.sort = keep; }
      var rev = !!(st.sortRev && st.sortRev.sort);
      var idx = new Map();
      pool.forEach(function (p, i) { idx.set(p, i); });
      function val(p) {
        var r = X.byId[p.player_key] || X.byKey[p.player_key];
        return r && isNum(r[field]) ? r[field] : null;
      }
      pool.sort(function (a, b) {
        var av = val(a), bv = val(b);
        if (av == null && bv == null) return idx.get(a) - idx.get(b);
        if (av == null) return 1;
        if (bv == null) return -1;
        return (rev ? av - bv : bv - av) || (idx.get(a) - idx.get(b));
      });
      return pool;
    };
    wrapped.xmWrapped = true;
    window.getFilteredActives = wrapped;
    // The app's own list of sorts that honour the reverse flag themselves.
    try { if (typeof _INTERNAL_DIR_MAIN_SORTS !== "undefined") Object.keys(SORTS).forEach(function (k) { _INTERNAL_DIR_MAIN_SORTS.add(k); }); } catch (e) { /* optional */ }
  }

  // ---- surfaces: /mlbstats/ boards ------------------------------------------
  function statsRowRecord(tr) {
    var b = tr.querySelector("[data-mlbexpand]");
    if (b) { var r = X.byMlbam[b.getAttribute("data-mlbexpand")]; if (r) return r; }
    var a = tr.querySelector('a[href*="#player="]');
    if (a) {
      var m = /#player=([^&]+)/.exec(a.getAttribute("href") || "");
      if (m) { var k = decodeURIComponent(m[1]); return X.byKey[k] || X.byMlbam[k] || null; }
    }
    return null;
  }
  function statsTables() {
    var tables = document.querySelectorAll("table.mlbstats-table[data-mlbpage]");
    for (var t = 0; t < tables.length; t++) decorateStats(tables[t]);
  }
  function decorateStats(tbl) {
    if (!tbl.tHead || !tbl.tBodies.length) return;
    var body = tbl.tBodies[0];
    if (tbl.querySelector("th[data-xm]") && body.querySelector("td[data-xm]")) return;
    var trs = body.querySelectorAll("tr[data-mlbi]");
    if (!trs.length) return;
    var hit = 0, probe = Math.min(trs.length, 25);
    for (var i = 0; i < probe; i++) if (statsRowRecord(trs[i])) hit++;
    if (hit < probe / 2) return;
    var hr = tbl.tHead.rows[tbl.tHead.rows.length - 1];
    if (!hr.querySelector("th[data-xm]")) {
      var th = document.createElement("th");
      th.className = "xm-col mlbstats-cv-grp";
      th.setAttribute("data-xm", "aav");
      th.setAttribute("scope", "col");
      th.setAttribute("tabindex", "0");
      th.setAttribute("aria-sort", "none");
      th.setAttribute("data-export-text", "xM$ AAV");
      th.title = "xM$ AAV: what the market would pay a free agent per year. Click to sort all rows; again to reverse. Priced as if a free agent this winter for a player under contract.";
      th.textContent = "xM$";
      hr.insertBefore(th, hr.cells[1] || null);
    }
    for (var j = 0; j < trs.length; j++) {
      var tr = trs[j];
      if (tr.querySelector("td[data-xm]")) continue;
      var rec = statsRowRecord(tr);
      var td = document.createElement("td");
      td.className = "xm-col mlbstats-cv-grp";
      td.setAttribute("data-xm", "1");
      if (rec && withheld(rec)) {
        td.title = xmTip(rec);
        td.textContent = "withheld";
      } else if (rec) {
        td.setAttribute("data-xm-v", rec.aav);
        td.title = xmTip(rec);
        td.textContent = usd(rec.aav);
      } else td.textContent = " - ";
      tr.insertBefore(td, tr.cells[1] || null);
    }
  }
  function statsSort(th) {
    var tbl = th.closest("table"), body = tbl.tBodies[0];
    var dir = th.getAttribute("aria-sort") === "descending" ? "ascending" : "descending";
    var trs = Array.prototype.slice.call(body.querySelectorAll("tr[data-mlbi]"));
    function v(tr) { var c = tr.querySelector("td[data-xm]"); var x = c ? c.getAttribute("data-xm-v") : null; return x == null || x === "" ? null : Number(x); }
    var keyed = trs.map(function (tr, i) { return { tr: tr, v: v(tr), i: i }; });
    keyed.sort(function (a, b) {
      if (a.v == null && b.v == null) return a.i - b.i;
      if (a.v == null) return 1;
      if (b.v == null) return -1;
      return (dir === "descending" ? b.v - a.v : a.v - b.v) || (a.i - b.i);
    });
    var cs = body.style.counterReset;
    keyed.forEach(function (o, n) {
      body.appendChild(o.tr);
      o.tr.setAttribute("data-mlbi", String(n));
    });
    body.style.counterReset = cs;
    var ths = tbl.tHead.rows[tbl.tHead.rows.length - 1].cells;
    for (var i = 0; i < ths.length; i++) {
      ths[i].classList.remove("is-sorted");
      if (ths[i].hasAttribute("aria-sort")) ths[i].setAttribute("aria-sort", "none");
    }
    th.classList.add("is-sorted");
    th.setAttribute("aria-sort", dir);
    // Back to the first page: the pager steps the page span and re-hides rows.
    var pager = tbl.parentNode && tbl.parentNode.parentNode ? tbl.parentNode.parentNode.querySelector(".mlbx-pager") : null;
    var prev = pager && pager.querySelector('[data-mlbpage-step="-1"]');
    var guard = 0;
    while (prev && !prev.disabled && guard++ < 400) prev.click();
    var sel = pager && pager.querySelector("[data-mlbpage-size]");
    if (sel) sel.dispatchEvent(new Event("change", { bubbles: true }));
  }
  document.addEventListener("click", function (e) {
    var th = e.target && e.target.closest ? e.target.closest("th.xm-col[data-xm]") : null;
    if (th) statsSort(th);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var th = e.target && e.target.closest ? e.target.closest("th.xm-col[data-xm]") : null;
    if (th) { e.preventDefault(); statsSort(th); }
  });

  // ---- surfaces: /fa/ board ---------------------------------------------------
  function faBoard() {
    var tbls = document.querySelectorAll("table.fa-board-table");
    for (var t = 0; t < tbls.length; t++) {
      var tbl = tbls[t];
      if (!tbl.tHead || !tbl.tBodies.length) continue;
      var hr = tbl.tHead.rows[tbl.tHead.rows.length - 1];
      var gTh = hr.querySelector("th.fc-guar");
      if (!gTh) continue;
      if (!hr.querySelector("th.fc-xm")) {
        var th = document.createElement("th");
        th.className = "fc-xm";
        th.setAttribute("scope", "col");
        th.title = "xM$: the market price the model predicts, as AAV x years. The same model as the predicted contract beside it, so a free agent's figures agree.";
        th.textContent = "xM$";
        gTh.parentNode.insertBefore(th, gTh.nextSibling);
      }
      var rows = tbl.tBodies[0].rows;
      for (var i = 0; i < rows.length; i++) {
        var tr = rows[i], k = tr.getAttribute("data-key");
        if (!k) {
          var c = tr.cells.length === 1 ? tr.cells[0] : null;
          if (c && c.hasAttribute("colspan") && !c.hasAttribute("data-xm-cs")) {
            c.setAttribute("colspan", String(Number(c.getAttribute("colspan")) + 1));
            c.setAttribute("data-xm-cs", "1");
          }
          // A detail row paints one pad per column past its colspan cell, so it
          // keeps exactly the header's cell count (fa.js faDetailRow); the xM$
          // column takes a pad of its own right after that cell.
          var dt = tr.querySelector("td.fa-dt-cell");
          if (dt && !tr.querySelector("td.fc-xm")) {
            var pad = document.createElement("td");
            pad.className = "fc-xm fa-dt-pad";
            pad.setAttribute("aria-hidden", "true");
            dt.parentNode.insertBefore(pad, dt.nextSibling);
          }
          continue;
        }
        if (tr.querySelector("td.fc-xm")) continue;
        var gTd = tr.querySelector("td.fc-guar");
        if (!gTd) continue;
        var r = X.byKey[k], td = document.createElement("td");
        td.className = "fc-xm";
        if (r && !withheld(r)) {
          td.title = xmTip(r);
          td.textContent = usd(r.aav) + " x " + r.years + "y";
        } else td.textContent = " - ";
        gTd.parentNode.insertBefore(td, gTd.nextSibling);
      }
    }
  }

  // ---- surfaces: /arbitration/ ---------------------------------------------------
  function parseUsd(s) {
    var m = /^\s*\$?([\d.,]+)\s*([kKmMbB]?)/.exec(String(s || ""));
    if (!m) return null;
    var n = Number(m[1].replace(/,/g, "")), u = m[2].toLowerCase();
    if (!isFinite(n)) return null;
    return n * (u === "k" ? 1e3 : u === "m" ? 1e6 : u === "b" ? 1e9 : 1);
  }
  function arbTables() {
    var tbls = document.querySelectorAll("table.arb-table");
    for (var t = 0; t < tbls.length; t++) {
      var tbl = tbls[t];
      if (!tbl.tHead || !tbl.tBodies.length) continue;
      var hr = tbl.tHead.rows[tbl.tHead.rows.length - 1];
      var rows = tbl.tBodies[0].rows;
      if (!rows.length || !rows[0].querySelector('a[href*="#player="]')) continue;
      if (!hr.querySelector("th[data-xm]")) {
        var th = document.createElement("th");
        th.setAttribute("data-xm", "1");
        th.setAttribute("scope", "col");
        th.className = "xm-col";
        th.title = "The next arbitration rung's projected salary as a share of xM$ AAV, the AAV the market would pay if he were a free agent this winter. A counterfactual price, not a forecast of a contract.";
        th.textContent = "Next rung / xM$";
        hr.appendChild(th);
      }
      for (var i = 0; i < rows.length; i++) {
        var tr = rows[i];
        if (tr.querySelector("td[data-xm]")) continue;
        var td = document.createElement("td");
        td.setAttribute("data-xm", "1");
        td.className = "xm-col";
        var a = tr.querySelector('a[href*="#player="]'), m = a ? /#player=([^&]+)/.exec(a.getAttribute("href")) : null;
        var r = m ? X.byKey[decodeURIComponent(m[1])] : null;
        var step = tr.querySelector(".arb-step b");
        var sal = step ? parseUsd(step.textContent) : null;
        if (r && sal != null && r.aav > 0) {
          td.textContent = Math.round(100 * sal / r.aav) + "%";
          td.title = "Next rung " + usd(sal) + " against xM$ AAV " + usd(r.aav) + ". " + xmTip(r);
        } else td.textContent = " - ";
        tr.appendChild(td);
      }
    }
  }

  // ---- surfaces: Trade Machine -----------------------------------------------------
  function tradeMachine() {
    var sides = document.querySelectorAll("#trade-machine .tm-side[data-tm-side]");
    for (var s = 0; s < sides.length; s++) {
      var side = sides[s], rows = side.querySelectorAll(".tm-row a.tm-name");
      var sig = Array.prototype.map.call(rows, function (a) { return a.getAttribute("href"); }).join("|");
      if (side.getAttribute("data-xm") === sig && side.querySelector(".xm-tm")) continue;
      var old = side.querySelector(".xm-tm");
      if (old) old.parentNode.removeChild(old);
      side.setAttribute("data-xm", sig);
      if (!rows.length) continue;
      var tot = 0, fair = 0, n = 0, nx = 0, cf = 0, wh = 0, miss = 0, clip = 0, ms = 0, mf = 0, nm = 0, ns = 0;
      for (var i = 0; i < rows.length; i++) {
        var m = /#player=([^&]+)/.exec(rows[i].getAttribute("href") || "");
        var r = m ? (X.byKey[decodeURIComponent(m[1])] || X.byId[decodeURIComponent(m[1])]) : null;
        if (!r) { miss++; continue; }
        n++; fair += r.fair; if (r.clip) clip++;
        if (withheld(r)) wh++;
        else { nx++; tot += r.total; if (r.cf) cf++; }
        // market-rate surplus over control: only rows with a priced control window
        if (isNum(r.msur_xm)) { nm++; ms += r.msur_xm; mf += isNum(r.msur_fair) ? r.msur_fair : 0; ns += r.ctrl || 0; }
      }
      if (!n) continue;
      var tip = "xM$ total: the summed market guarantee the free-agent market would pay these players (NPV basis). Fair $ total: the summed worth of their projected production over the same terms. Side by side, never subtracted."
        + (cf ? " " + cf + " of " + n + " priced as if a free agent this winter (counterfactual)." : "")
        + (wh ? " " + wh + " of " + n + " are prospects: Fair $ only (the NPV of the eFV WAR path), xM$ withheld as " + XM_WITHHELD + ", so the xM$ total covers " + nx + " of " + n + "." : "")
        + (clip ? " " + clip + " outside the model's training range." : "")
        + (miss ? " " + miss + " not priced." : "");
      var msTip = "Market-rate surplus over control: each controlled season priced at the xM$ market rate (and, beside it, at Fair $), less the salary on the books, discounted and summed over the "
        + nm + " of " + n + " players with a priced control window (" + ns + " seasons). The others are not summed.";
      var html = '<div class="xm-tm" title="' + esc(tip) + '"><span>xM$ <b>' + esc(nx ? usd(tot) : "withheld") + "</b>" + (wh && nx ? " (" + nx + " of " + n + ")" : "") + '</span><span>Fair $ <b>' + esc(usd(fair)) + "</b></span>" +
        (cf ? '<span class="xm-cf">' + cf + " as if FA</span>" : "") +
        (wh ? '<span class="xm-cf">' + wh + " Fair $ only</span>" : "") +
        (nm ? '<span data-xm-msur title="' + esc(msTip) + '">Market-rate surplus over control: xM$ <b>' + esc(usd(ms)) + "</b>, Fair $ <b>" + esc(usd(mf)) + "</b> (" + nm + " of " + n + ")</span>" : "") +
        "</div>";
      var head = side.querySelector(".tm-side-head");
      if (head) head.insertAdjacentHTML("afterend", html);
    }
  }

  // ---- surfaces: club roll-ups (Ledger, Franchise) ----------------------------------
  // surface "ledger": the roster and farm rows only. The market-rate surplus
  // over control is a club surplus total, on the Club Ledger never-list (owner
  // answer XM2-Q2), so it is drawn on Franchise alone.
  function clubBlockHtml(code, heading, surface) {
    var c = X.clubs && X.clubs.clubs && X.clubs.clubs[code];
    if (!c) return "";
    var withSurplus = surface === "franchise";
    var R = c.roster || {}, M = c.market_surplus || {}, F = c.farm || {}, P = R.payroll_spotrac || {};
    function row(label, a, b, tip) {
      return "<tr><th scope=\"row\"" + (tip ? ' title="' + esc(tip) + '"' : "") + ">" + label + '</th><td class="xm-n">' + (a == null ? "" : typeof a === "string" ? esc(a) : esc(usd(a))) +
        '</td><td class="xm-n">' + (b == null ? "" : esc(usd(b))) + "</td></tr>";
    }
    var out = '<div class="xm-block" data-xm-club="' + esc(code) + '" data-xm-surface="' + esc(surface) + '">' + heading +
      '<table class="xm-table"><thead><tr><th scope="col">Figure</th><th scope="col" class="xm-n">xM$</th><th scope="col" class="xm-n">Fair $</th></tr></thead><tbody>' +
      row("40-man roster, AAV sum (" + esc(R.n) + " players" + (R.n_free_agents_excluded ? ", " + esc(R.n_free_agents_excluded) + " free agents left out" : "") +
        (R.n_on40_prospects_in_farm ? ", " + esc(R.n_on40_prospects_in_farm) + (R.n_on40_prospects_in_farm === 1 ? " prospect" : " prospects") + " counted in the farm" : "") + ")", R.xm_aav_usd, R.fair_aav_usd,
        "Each player priced as if a free agent this winter. A prospect on the 40-man is counted in the farm row, at Fair $ only. The two sums are separate figures and are not subtracted.") +
      '<tr data-xm-payroll><td colspan="3" class="xm-note">Beside it, payroll on file (Spotrac): ' + esc(usd(P.total_2026_usd)) + " in 2026 and " + esc(usd(P.committed_2027_usd)) +
      " committed for 2027; " + PAYROLL_NOTE + ". The xM$ roster sum prices players as if free agents and is never netted against it.</td></tr>" +
      (withSurplus ? row("Market-rate surplus over control (" + esc(M.n) + " players, " + esc(M.seasons) + " seasons)", M.xm_usd, M.fair_usd,
        "Each controlled season priced at the market rate, less the salary on the books, summed over the listed players. A player with no salary path is not summed" +
        (M.n_not_summed && M.n_not_summed.no_salary_path ? " (" + M.n_not_summed.no_salary_path + " here)" : "") + ".") : "") +
      row("Farm, board prospects (" + esc(F.n) + ")", "withheld", F.fair_usd,
        "Fair $ only: the sum over every board prospect, on the 40-man or off it, of the NPV of his eFV WAR path at the winter's market $/WAR and a 7% discount. xM$ is withheld: " + XM_WITHHELD + ".") +
      "</tbody></table>" +
      '<p class="xm-note"><a href="/glossary/#g=xm_dollars">xM$</a> and <a href="/glossary/#g=fair_dollars">Fair $</a> are separate numbers. Provisional: on 306 held-out 2025-26 signings xM$ missed by 0.736 (log of total) against 0.899 for a WAR-times-price rule; MLB Trade Rumors missed by 0.452 against 0.712 on the 92 signings both priced.</p></div>';
    return out;
  }
  function ledgerBlock() {
    var root = document.getElementById("ledger-block-links");
    var host = document.querySelector(".ledger-grid");
    if (!host || !root) return;
    var m = /(?:^#|[#&])team=([A-Z]{2,3})\b/.exec(location.hash || "");
    var code = m ? m[1] : null;
    var cur = document.getElementById("ledger-block-xm");
    if (!code) { if (cur) cur.parentNode.removeChild(cur); return; }
    if (cur && cur.getAttribute("data-xm-club") === code) return;
    if (cur) cur.parentNode.removeChild(cur);
    var inner = clubBlockHtml(code, '<h3>Expected market $ (xM$) and Fair $</h3>', "ledger");
    if (!inner) return;
    var sec = document.createElement("section");
    sec.id = "ledger-block-xm";
    sec.className = "ledger-block ledger-span-12";
    sec.setAttribute("data-xm-club", code);
    sec.innerHTML = inner;
    root.parentNode.insertBefore(sec, root);
  }
  function franchiseBlock() {
    var fin = document.getElementById("fr-sec-fin");
    var sel = document.getElementById("fr-club");
    if (!fin || !sel) return;
    var sect = fin.closest("section") || fin.parentNode;
    var code = sel.value;
    var cur = sect.querySelector(":scope > .xm-block");
    if (cur && cur.getAttribute("data-xm-club") === code) return;
    if (cur) cur.parentNode.removeChild(cur);
    var inner = clubBlockHtml(code, '<h3>Expected market $ (xM$) and Fair $</h3>', "franchise");
    if (inner) sect.insertAdjacentHTML("beforeend", inner);
  }

  // ---- driver -------------------------------------------------------------------------
  function route() {
    var p = location.pathname.replace(/index\.html$/, "");
    if (/^\/projections\//.test(p)) projectionsCard();
    else if (/^\/prospx\//.test(p)) { prospxSortOptions(); wrapProspxSort(); prospxRows(); prospxCard(); }
    else if (/^\/mlbstats\//.test(p)) statsTables();
    else if (/^\/fa\//.test(p)) faBoard();
    else if (/^\/arbitration\//.test(p)) arbTables();
    else if (/^\/trademachine\//.test(p)) tradeMachine();
    else if (/^\/ledger\//.test(p)) ledgerBlock();
    else if (/^\/franchise\//.test(p)) franchiseBlock();
  }
  var obs = null, pending = false;
  function schedule() {
    if (pending) return;
    pending = true;
    setTimeout(function () {
      pending = false;
      if (obs) obs.disconnect();
      try { route(); } catch (e) { if (window.console) console.warn("xm-surfaces", e); }
      if (obs) obs.observe(document.body, { childList: true, subtree: true });
    }, 60);
  }
  function start() {
    addStyle();
    obs = new MutationObserver(schedule);
    obs.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("hashchange", schedule);
    schedule();
  }
  function get(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) { if (!r.ok) throw new Error(url + " " + r.status); return r.json(); });
  }
  function boot() {
    Promise.all([get(PLAYERS_URL), get(CLUBS_URL).catch(function () { return null; })]).then(function (res) {
      var doc = res[0];
      // A second lock: the exporter writes display_on from the same flag.
      if (!doc || !doc.display_on) return;
      X.doc = doc; X.clubs = res[1];
      index(doc);
      start();
    }).catch(function () { /* data absent: the page stays as it was */ });
  }
  window.EEPHUS_XM = { find: find, usd: usd };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
