/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// /mlbstats/ player drawer (owner ask 18 of 2026-09-30, "Show stat
// visualizations for each player when clicked on in the MLB Stats module";
// final-pass plan Part 8 item P8.2, task LT-09; the lane design's section 6).
// =============================================================================
// Lazy: assets/mlbstats.js injects this file once, on the first drawer open,
// from data-drawer-src on the /mlbstats/ root, which build_site writes only
// while mlbstats_trends_export.MLBSTATS_DRAWER_LIVE is on. mlbstats.js owns the
// caret, the drawer row and the deep link; this file fills the drawer's cell
// (fill(mount, ctx)) with up to three panels, which stack below 700 px:
//
//   Trend       the board's index by season with its 100 rule (WPA with its
//               zero rule on Leverage; eWAR bars on Overall), from the trends
//               file, fetched on the first open only.
//   Percentiles each value against the board's qualified pool for the season
//               on screen, computed here from the board rows already loaded:
//               no download. A lower-is-better stat is flipped so right reads
//               better, and the panel says which; a usage stat (gmLI, pLI,
//               P/PA) is drawn uncoloured. The /projections/ slider markup.
//   Rolling     the live season's last 15 games (5 starts, 10 relief
//               appearances), from the player's own small game file; a toggle
//               doubles the window with no refetch. A point is drawn only once
//               its window is full, so no line opens on a one-game rate.
//
// DESCRIPTIVE ONLY. Every number is a count, a pooled rate or a served index.
// No label calls a stretch good or bad, no arrow, nothing projected.
(function () {
  "use strict";

  var DATA_DIR = "/data/";
  var TRENDS_FILE = "mlbstats_trends.json";
  var SHARD_DIR = "mlbstats_player/";
  var DASH = " - ";

  // ---- small helpers ---------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isN(v) { return v != null && v !== "" && typeof v !== "boolean" && isFinite(v); }
  function num(v) { return isN(v) ? Number(v) : null; }
  // Plus stats print to the nearest whole number, halves up (house rule).
  function f0(v) { return isN(v) ? String(Math.floor(Number(v) + 0.5)) : DASH; }
  function f1(v) { return isN(v) ? Number(v).toFixed(1) : DASH; }
  function f2(v) { return isN(v) ? Number(v).toFixed(2) : DASH; }
  function pc(v) { return isN(v) ? (Number(v) * 100).toFixed(1) + "%" : DASH; }
  function md(d) { return d ? String(d).slice(5) : ""; }
  function hub() { return (typeof window !== "undefined" && window.EEPHUS_HUB) || null; }
  function getJSON(u) {
    return fetch(u, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  // ---- data (each fetched once a page view) ----------------------------------
  var TRENDS = null, trendsP = null, TRENDS_ERR = false;
  function loadTrends() {
    if (TRENDS || trendsP) return trendsP;
    TRENDS_ERR = false;
    trendsP = getJSON(DATA_DIR + TRENDS_FILE).then(function (j) {
      TRENDS = (j && j.players) ? j : null;
      if (!TRENDS) TRENDS_ERR = true;
    }, function () { TRENDS_ERR = true; trendsP = null; });
    return trendsP;
  }
  var SHARDS = {}, shardP = {}, SHARD_ERR = {};
  function loadShard(id) {
    if (SHARDS[id] || shardP[id]) return shardP[id];
    delete SHARD_ERR[id];
    shardP[id] = getJSON(DATA_DIR + SHARD_DIR + encodeURIComponent(id) + ".json").then(function (j) {
      SHARDS[id] = j || null;
      if (!j) SHARD_ERR[id] = true;
    }, function () { SHARD_ERR[id] = true; delete shardP[id]; });
    return shardP[id];
  }

  // ---- what each board's drawer draws (the lane design's 6.2 table) ----------
  // pct rows: [key, how]; how "low" flips (lower is better), "use" is usage
  // and stays uncoloured. A key the board does not carry is skipped, so P/PA
  // and P/IP appear only once the boards ship them.
  var BOARDS = {
    hit: { noun: "hitters", trend: { fam: "h", val: "hem", vol: "pa", label: "HEM+", ref: 100 }, roll: "hit",
           pct: [["hem_plus"], ["xhem_plus"], ["wrc_plus"], ["k_pct", "low"], ["bb_pct"], ["iso"],
                 ["chase_pct", "low"], ["whiff_pct", "low"], ["p_pa", "use"]] },
    sp: { noun: "starters", trend: { fam: "p", board: "sp", val: "plus", vol: "ip", label: "SEM+", ref: 100 }, roll: "sp",
          pct: [["sem_plus"], ["xsem_plus"], ["k_pct"], ["bb_pct", "low"], ["k_bb_pct"], ["gb_pct"],
                ["swstr_pct"], ["fb_velo"], ["p_ip", "low"]] },
    rel: { noun: "relievers", trend: { fam: "p", board: "rp", val: "plus", vol: "ip", label: "REM+", ref: 100 }, roll: "rel",
           pct: [["rem_plus"], ["xrem_plus"], ["k_pct"], ["bb_pct", "low"], ["swstr_pct"], ["gmli", "use"], ["p_ip", "low"]] },
    // DEM+ within position is a served column (Pos %ile): the drawer prints the
    // board's own number rather than a second percentile beside it.
    def: { noun: "fielders", within: "pos", trend: { fam: "d", val: "dem", vol: "inn", label: "DEM+", ref: 100 }, roll: null,
           pct: [["dem_plus", "", "dem_plus_pos_pct"]] },
    // Baserunning (mlbstats.js section 7) supplies its own four panels through
    // window.MLBX_BR_DRAWER (Speed, the steal map, advancement against the
    // league, eBR by season); the percentile rows below feed its Speed panel.
    br: { noun: "runners", custom: true, trend: null, roll: null,
          pct: [["sprint"], ["hp1", "low"], ["bolts"], ["ebr"], ["xbt_pct"], ["att_rate", "use"]] },
    levbat: { noun: "batters", trend: { fam: "l", val: "wpa", vol: "pa", label: "WPA", ref: 0, fmt: f2 }, roll: null,
              pct: [["wpa"], ["wpa_li"], ["pli", "use"]] },
    levsp: { noun: "starters", trend: { fam: "p", board: "sp", val: "plus", vol: "ip", label: "SEM+", ref: 100 }, roll: null,
             pct: [["wpa"], ["wpa_li"], ["wpa_per_start"]] },
    war: { noun: "players", trend: null, roll: null, pct: null }
  };
  // Rolling windows: the default and the doubled toggle, per side.
  var WINDOWS = { hit: [15, 30], sp: [5, 10], rel: [10, 20] };
  var WIN_NOUN = { hit: "games", sp: "starts", rel: "appearances" };
  var winPick = { hit: 15, sp: 5, rel: 10 };
  var MIN_POOL = 10;

  // ---- percentiles -------------------------------------------------------------
  // The share of the pool below the value, ties counted half, nearest whole
  // number; flipped for a lower-is-better stat. Pure, so the page test pins it.
  function pctRank(v, vals, low) {
    if (!isN(v) || !vals.length) return null;
    var below = 0, eq = 0;
    for (var i = 0; i < vals.length; i++) { if (vals[i] < v) below++; else if (vals[i] === v) eq++; }
    var p = Math.floor((below + eq / 2) / vals.length * 100 + 0.5);
    p = Math.max(0, Math.min(100, p));
    return low ? 100 - p : p;
  }
  function percentiles(ctx) {
    var cfg = BOARDS[ctx.board], pool = ctx.pool;
    if (!cfg || !cfg.pct || !pool || pool.window || !ctx.row) return null;
    var me = ctx.row;
    var rows = (pool.rows || []).filter(function (r) {
      return r.qualified !== false && (!cfg.within || r[cfg.within] === me[cfg.within]);
    });
    var out = [];
    cfg.pct.forEach(function (m) {
      var cell = ctx.cell(m[0], me);
      if (!cell || cell.v == null) return;
      var vals = [];
      rows.forEach(function (r) { var c = ctx.cell(m[0], r); if (c && c.v != null) vals.push(c.v); });
      var served = m[2] && isN(me[m[2]]) ? Math.max(0, Math.min(100, Math.floor(Number(me[m[2]]) + 0.5))) : null;
      if (served == null && vals.length < MIN_POOL) return;
      out.push({ key: m[0], label: cell.label, html: cell.html, v: cell.v, n: vals.length, served: served != null,
                 how: m[1] || "", pct: served != null ? served : pctRank(cell.v, vals, m[1] === "low") });
    });
    return { rows: out, n: rows.length, season: pool.season, live: !!pool.live,
             within: cfg.within ? me[cfg.within] : null };
  }
  function pctClass(p) {
    return p >= 80 ? "is-elite" : p >= 60 ? "is-good" : p >= 40 ? "is-avg" : p >= 20 ? "is-low" : "is-poor";
  }
  function slider(m) {
    var T = (typeof window !== "undefined" && window.EephusTiers) || null;
    var use = m.how === "use";
    var c = (!use && T && T.pctColor) ? T.pctColor(m.pct) : "";
    var v = c ? "--pct:" + c + ";" : "";
    var cls = use ? "is-avg" : pctClass(m.pct);
    var tip = m.label + ": percentile " + m.pct + (m.served ? ", the board's own figure" : " of " + m.n)
      + (m.how === "low" ? " (lower is better, so the bar is flipped)" : use ? " (usage, not quality, so uncoloured)" : "");
    return '<div class="mlbp-slider" title="' + esc(tip) + '">'
      + '<span class="mlbp-slider-label">' + esc(m.label) + "</span>"
      + '<div class="mlbp-slider-track"><div class="mlbp-slider-fill ' + cls + '" style="' + v + "width:" + m.pct + '%;"></div>'
      + '<span class="mlbp-slider-pct ' + cls + '" style="' + v + "left:" + Math.min(94, Math.max(2, m.pct)) + '%;">'
      + m.pct + "</span></div>"
      + '<span class="mlbp-slider-val">' + m.html + "</span></div>";
  }
  function listWords(a) {
    return a.length < 2 ? a.join("") : a.slice(0, -1).join(", ") + " and " + a[a.length - 1];
  }
  function pctPanel(ctx) {
    var cfg = BOARDS[ctx.board], pool = ctx.pool;
    if (pool && pool.window) {
      return '<p class="mlbx-dnote">Percentiles rank one season&#39;s board, and this one shows the '
        + esc(pool.window) + " window. Pick a single season to see them.</p>";
    }
    var P = percentiles(ctx);
    if (!P || !P.rows.length) {
      return '<p class="mlbx-dnote">Too few qualified ' + esc(cfg.noun) + " carry these values to rank against.</p>";
    }
    var low = P.rows.filter(function (m) { return m.how === "low"; }).map(function (m) { return m.label; });
    var use = P.rows.filter(function (m) { return m.how === "use"; }).map(function (m) { return m.label; });
    var own = P.rows.filter(function (m) { return m.served; }).map(function (m) { return m.label; });
    var who = own.length === P.rows.length
      ? listWords(own) + " is the board's own percentile within position (Pos %ile), " + (P.season || "") + "."
      : "Against the " + P.n + " qualified " + cfg.noun + (P.within ? " at " + P.within : "")
        + " of the " + (P.season || "") + " board" + (P.live ? "" : ", which ships qualified rows only") + ".";
    var notes = [who];
    if (ctx.row && ctx.row.qualified === false) notes.push("This row is under the qualifying sample and is placed against the qualified pool.");
    if (low.length) notes.push(listWords(low) + (low.length > 1 ? " are" : " is") + " flipped: a lower value is better, so it draws the longer bar.");
    if (use.length) notes.push(listWords(use) + (use.length > 1 ? " are" : " is") + " usage, not quality, so " + (use.length > 1 ? "their bars are" : "its bar is") + " uncoloured.");
    return P.rows.map(slider).join("") + '<p class="mlbx-dnote">' + esc(notes.join(" ")) + "</p>";
  }

  // ---- trend ---------------------------------------------------------------------
  function seasonIncomplete(y) {
    // The house rule (league_averages.season_complete): a season is complete
    // from November 1.
    if (!TRENDS || Number(y) !== Number(TRENDS.live_season)) return false;
    return String(TRENDS.as_of || "") < String(TRENDS.live_season) + "-11-01";
  }
  function trendRows(ctx) {
    var cfg = BOARDS[ctx.board].trend, p = TRENDS && TRENDS.players && TRENDS.players[String(ctx.id)];
    var F = TRENDS && TRENDS.fields && TRENDS.fields[cfg.fam];
    if (!p || !F || !p[cfg.fam]) return [];
    var iy = F.indexOf("season"), iv = F.indexOf(cfg.val), iw = F.indexOf(cfg.vol), ib = F.indexOf("board");
    return p[cfg.fam].filter(function (a) { return !cfg.board || a[ib] === cfg.board; })
      .map(function (a) { return { season: a[iy], v: num(a[iv]), vol: num(a[iw]) }; })
      .filter(function (r) { return r.v != null; });
  }
  function trendBasis(ctx, y) {
    var cfg = BOARDS[ctx.board].trend, s = TRENDS && TRENDS.sources && TRENDS.sources[cfg.fam];
    var b = s && s[String(y)];
    if (b && typeof b === "object") b = b[cfg.board];
    return String(b || "");
  }
  function trendChart(ctx, width) {
    var cfg = BOARDS[ctx.board].trend, H = hub();
    var rows = trendRows(ctx);
    if (!rows.length) return '<p class="mlbx-dnote">No season of ' + esc(cfg.label) + " on file for this player.</p>";
    var fmt = cfg.fmt || f0, volName = cfg.vol === "pa" ? "PA" : cfg.vol === "ip" ? "IP" : "Inn";
    var lo = rows[0].season, hi = rows[rows.length - 1].season, xs = [];
    for (var y = lo; y <= hi; y++) xs.push(String(y));
    var pts = rows.map(function (r) {
      var part = Number(r.season) === 2020 || seasonIncomplete(r.season);
      return { y: String(r.season), v: r.v, partial: part,
               hint: "(" + (cfg.vol === "pa" ? f0(r.vol) : f1(r.vol)) + " " + volName
                 + (seasonIncomplete(r.season) ? ", through " + TRENDS.as_of : Number(r.season) === 2020 ? ", a 60-game season" : "") + ")" };
    });
    // A season label every season where 34 px apart fit, else every other.
    var gap = (width - 68) / Math.max(1, xs.length - 1);
    var svg = (H && H.lineChart && rows.length > 1) ? H.lineChart([{ label: cfg.label, color: "var(--viz-1)", pts: pts }], {
      xs: xs, width: width, height: 170, fmt: fmt, pl: 34, pr: 34, every: gap >= 34 ? 1 : gap >= 17 ? 2 : 5,
      refs: [{ v: cfg.ref, label: String(cfg.ref) }], aria: cfg.label + " by season, " + lo + " to " + hi,
      caption: "Numbers", xName: "Season" }) : "";
    if (!svg) {
      svg = '<p class="mlbx-dnote">' + esc(cfg.label + " " + fmt(rows[0].v) + " in " + rows[0].season
        + ", the one season on file.") + "</p>";
    }
    var notes = [];
    var q = xs.filter(function (y) { return /^qualified/.test(trendBasis(ctx, y)); });
    if (q.length) notes.push((q.length > 1 ? q[0] + " to " + q[q.length - 1] : q[0])
      + ": qualified rows only, so a season under the qualifying sample is missing there.");
    if (rows.some(function (r) { return r.partial || Number(r.season) === 2020 || seasonIncomplete(r.season); })) {
      notes.push("A hollow point is a partial season.");
    }
    if (ctx.board === "levsp") notes.push("The trend file carries WPA by season for batters only, so a starter's trend is his SEM+.");
    if (ctx.board === "hit") {
      var ew = ctx.ewar && ctx.ewar();
      if (ew && ew.length) {
        notes.push("eWAR by season: " + ew.map(function (s) { return s.season + " " + f1(s.war); }).join(", ") + ".");
      }
    }
    return svg + (notes.length ? '<p class="mlbx-dnote">' + esc(notes.join(" ")) + "</p>" : "");
  }
  // Overall: eWAR by season as bars, batting and pitching stacked (the
  // /projections/ idiom and its classes): every season of the per-season
  // payload the Overall board already holds, else the row's own seasons.
  function warBars(ctx, width) {
    var all = ctx.ewar && ctx.ewar();
    var ss = ((all && all.length) ? all : ((ctx.row && ctx.row.seasons) || []))
      .filter(function (s) { return s.war_bat != null || s.war_pit != null; });
    if (!ss.length) return '<p class="mlbx-dnote">No season of eWAR on file for this player.</p>';
    var W = Math.max(240, width), Hh = 170, PL = 8, PR = 8, PT = 18, PB = 22;
    function pos(s) { return Math.max(0, s.war_bat || 0) + Math.max(0, s.war_pit || 0); }
    function neg(s) { return Math.min(0, s.war_bat || 0) + Math.min(0, s.war_pit || 0); }
    var mx = Math.max.apply(null, [1].concat(ss.map(pos))), mn = Math.min.apply(null, [0].concat(ss.map(neg)));
    var slot = (W - PL - PR) / ss.length, bw = Math.min(34, slot * 0.62);
    function y(v) { return PT + (mx - v) * (Hh - PT - PB) / ((mx - mn) || 1); }
    function cx(i) { return PL + slot * (i + 0.5); }
    var every = slot < 30 ? Math.ceil(30 / slot) : 1;
    var bars = ss.map(function (s, i) {
      var tot = (s.war_bat || 0) + (s.war_pit || 0), pb = 0, nb = 0, out = "";
      var title = s.season + ": " + f1(tot) + " eWAR"
        + (s.war_bat != null && s.war_pit != null ? " (bat " + f1(s.war_bat) + ", pitch " + f1(s.war_pit) + ")" : "");
      [["a", s.war_bat], ["b", s.war_pit]].forEach(function (kv) {
        var v = kv[1];
        if (v == null) return;
        var lo = v >= 0 ? pb : nb + v, hi = v >= 0 ? pb + v : nb;
        if (v >= 0) pb += v; else nb += v;
        out += '<rect x="' + (cx(i) - bw / 2).toFixed(1) + '" y="' + y(hi).toFixed(1) + '" width="' + bw.toFixed(1)
          + '" height="' + Math.max(0.5, y(lo) - y(hi)).toFixed(1) + '" class="mlbp-warbar' + (kv[0] === "b" ? " mlbp-warbar-b" : "")
          + '"><title>' + esc(title) + "</title></rect>";
      });
      var ly = tot >= 0 ? y(pb) - 4 : y(nb) + 11;
      if (slot >= 22) out += '<text x="' + cx(i).toFixed(1) + '" y="' + ly.toFixed(1) + '" text-anchor="middle" class="mlbp-warbar-val">' + f1(tot) + "</text>";
      if (i % every === 0 || i === ss.length - 1) {
        out += '<text x="' + cx(i).toFixed(1) + '" y="' + (Hh - 6) + '" text-anchor="middle" class="mlbp-fan-tick">' + esc(s.season) + "</text>";
      }
      return out;
    }).join("");
    var two = ss.some(function (s) { return s.war_bat != null; }) && ss.some(function (s) { return s.war_pit != null; });
    return '<svg class="mlbp-fan mlbp-warbars" viewBox="0 0 ' + W + " " + Hh + '" style="display:block;width:100%;height:auto;" role="img" aria-label="'
      + esc("eWAR by season, " + ss[0].season + " to " + ss[ss.length - 1].season) + '">'
      + '<line x1="' + PL + '" x2="' + (W - PR) + '" y1="' + y(0).toFixed(1) + '" y2="' + y(0).toFixed(1) + '" class="mlbp-warbar-zero"/>'
      + bars + "</svg>"
      + (two ? '<p class="mlbx-dlegend"><span><i class="mlbx-dkey-a"></i>Batting</span><span><i class="mlbx-dkey-b"></i>Pitching</span></p>' : "")
      + '<details class="eephus-chart-table"><summary>Numbers</summary><div style="overflow-x:auto"><table><thead><tr>'
      + '<th scope="col">Season</th><th scope="col" style="text-align:right">Batting</th>'
      + '<th scope="col" style="text-align:right">Pitching</th><th scope="col" style="text-align:right">eWAR</th></tr></thead><tbody>'
      + ss.slice().reverse().map(function (s) {
          return "<tr><td>" + esc(s.season) + '</td><td style="text-align:right">' + f1(s.war_bat)
            + '</td><td style="text-align:right">' + f1(s.war_pit) + '</td><td style="text-align:right">'
            + f1((s.war_bat || 0) + (s.war_pit || 0)) + "</td></tr>";
        }).join("") + "</tbody></table></div></details>";
  }

  // ---- rolling windows -------------------------------------------------------------
  // Pure: the side's game rows (the shard's cols and games), the window, and
  // the points, one per game from the first full window on.
  function rolling(side, blk, W) {
    if (!blk || !blk.cols || !blk.games) return { games: 0, pts: [] };
    var c = {};
    blk.cols.forEach(function (k, i) { c[k] = i; });
    var g = blk.games.filter(function (a) {
      return side === "hit" ? num(a[c.pa]) > 0 : side === "sp" ? num(a[c.gs]) === 1 : num(a[c.bf]) > 0 || num(a[c.outs]) > 0;
    });
    var pts = [];
    for (var i = W - 1; i < g.length; i++) {
      var s = { pa: 0, so: 0, bb: 0, pit: 0, pitd: 0, bf: 0, outs: 0, li: 0, lin: 0, pitn: 0 };
      for (var j = i - W + 1; j <= i; j++) {
        var a = g[j];
        if (side === "hit") {
          s.pa += num(a[c.pa]) || 0; s.so += num(a[c.so]) || 0; s.bb += num(a[c.bb]) || 0;
          if (num(a[c.pit]) != null) { s.pit += num(a[c.pit]); s.pitd += num(a[c.pa]) || 0; }
        } else {
          s.bf += num(a[c.bf]) || 0; s.so += num(a[c.so]) || 0; s.outs += num(a[c.outs]) || 0;
          if (num(a[c.pit]) != null) { s.pit += num(a[c.pit]); s.pitn++; }
          if (num(a[c.li]) != null) { s.li += num(a[c.li]); s.lin++; }
        }
      }
      var p = { n: i + 1, from: g[i - W + 1][c.date], to: g[i][c.date] };
      if (side === "hit") {
        p.k = s.pa ? s.so / s.pa : null; p.bb = s.pa ? s.bb / s.pa : null; p.ppa = s.pitd ? s.pit / s.pitd : null;
      } else if (side === "sp") {
        p.pps = s.pitn === W ? s.pit / W : null; p.ips = s.outs / 3 / W; p.k = s.bf ? s.so / s.bf : null;
      } else {
        p.li = s.lin ? s.li / s.lin : null; p.k = s.bf ? s.so / s.bf : null;
      }
      pts.push(p);
    }
    return { games: g.length, pts: pts };
  }
  function rollChart(R, key, label, fmt, width, h, opts) {
    var H = hub();
    if (!H || !H.lineChart) return "";
    var o = opts || {};
    var dates = {};
    R.pts.forEach(function (p) { dates[p.n] = p; });
    var series = [{ label: label, color: "var(--viz-1)", pts: R.pts.map(function (p) { return { y: p.n, v: p[key] }; }) }];
    if (o.second) series.push({ label: o.second[1], color: "var(--viz-2)", pts: R.pts.map(function (p) { return { y: p.n, v: p[o.second[0]] }; }) });
    return H.lineChart(series, {
      width: width, height: h, fmt: fmt, tickFmt: o.tickFmt || fmt, pl: 38, pr: 40, table: false, every: o.every || 0,
      refs: o.refs || [], xfmt: function (n) { return md((dates[n] || {}).to); },
      tip: function (s, p) {
        var d = dates[p.y] || {};
        return s.label + " " + fmt(Number(p.v)) + ", games " + (p.y - o.W + 1) + " to " + p.y + " (" + md(d.from) + " to " + md(d.to) + ")";
      },
      aria: o.aria || label });
  }
  function rollTable(R, cols) {
    var rows = R.pts.slice().reverse().map(function (p) {
      return "<tr><td>" + esc(md(p.to)) + "</td><td>" + p.n + "</td>" + cols.map(function (c) {
        return '<td style="text-align:right">' + esc(c[2](p[c[0]])) + "</td>";
      }).join("") + "</tr>";
    }).join("");
    return '<details class="eephus-chart-table"><summary>Numbers</summary><div style="overflow-x:auto"><table><thead><tr>'
      + '<th scope="col">Through</th><th scope="col">Game</th>'
      + cols.map(function (c) { return '<th scope="col" style="text-align:right">' + esc(c[1]) + "</th>"; }).join("")
      + "</tr></thead><tbody>" + rows + "</tbody></table></div></details>";
  }
  function leaguePpa(ctx) {
    var pit = 0, pa = 0;
    ((ctx.pool && ctx.pool.rows) || []).forEach(function (r) {
      if (isN(r.pit) && isN(r.pa)) { pit += Number(r.pit); pa += Number(r.pa); }
    });
    return pa ? pit / pa : null;
  }
  function rollPanel(ctx, width) {
    var cfg = BOARDS[ctx.board], side = cfg.roll;
    var sh = SHARDS[String(ctx.id)];
    var blk = sh && sh[side === "hit" ? "hit" : "pit"];
    var W = winPick[side], noun = WIN_NOUN[side];
    var tog = '<div class="mlbx-dtoggle" role="group" aria-label="Window">' + WINDOWS[side].map(function (n) {
      return '<button type="button" class="chip' + (n === W ? " active" : "") + '" data-mlbxd-win="' + side + ":" + n
        + '" aria-pressed="' + (n === W) + '">' + n + " " + noun + "</button>";
    }).join("") + "</div>";
    var R = rolling(side, blk, W);
    var thru = sh && sh.covers_through ? " Games through " + sh.covers_through + "." : "";
    if (!R.pts.length) {
      return tog + '<p class="mlbx-dnote">' + esc(R.games + " " + noun + " in the " + ((sh && sh.season) || "") + " game log; the window draws once "
        + W + " are in." + thru) + "</p>";
    }
    var every = side === "hit" ? 30 : side === "sp" ? 5 : 15;
    var common = { W: W, every: every };
    var out = tog, tcols;
    if (side === "hit") {
      out += '<p class="mlbx-dlegend"><span><i class="mlbx-dkey-1"></i>K%</span><span><i class="mlbx-dkey-2"></i>BB%</span></p>'
        + rollChart(R, "k", "K%", pc, width, 150, { W: W, every: every, second: ["bb", "BB%"], aria: "K% and BB%, rolling " + W + " " + noun });
      var lg = leaguePpa(ctx);
      if (R.pts.some(function (p) { return p.ppa != null; })) {
        out += '<div class="mlbx-dsub">P/PA</div>' + rollChart(R, "ppa", "P/PA", f2, width, 120,
          { W: W, every: every, refs: lg != null ? [{ v: lg, label: "league " + f2(lg) }] : [], aria: "P/PA, rolling " + W + " " + noun });
      }
      tcols = [["k", "K%", pc], ["bb", "BB%", pc], ["ppa", "P/PA", f2]];
    } else if (side === "sp") {
      out += '<div class="mlbx-dsub">Pitches per start</div>' + rollChart(R, "pps", "Pitches per start", f1, width, 110,
          { W: W, every: every, tickFmt: f0 })
        + '<div class="mlbx-dsub">Innings per start</div>' + rollChart(R, "ips", "Innings per start", f1, width, 110, common)
        + '<div class="mlbx-dsub">K%</div>' + rollChart(R, "k", "K%", pc, width, 110, common);
      tcols = [["pps", "P/start", f1], ["ips", "IP/start", f1], ["k", "K%", pc]];
    } else {
      out += '<div class="mlbx-dsub">gmLI</div>' + rollChart(R, "li", "gmLI", f2, width, 110,
          { W: W, every: every, refs: [{ v: 1, label: "1.00" }] })
        + '<div class="mlbx-dsub">K%</div>' + rollChart(R, "k", "K%", pc, width, 110, common);
      tcols = [["li", "gmLI", f2], ["k", "K%", pc]];
    }
    var lead = side === "hit" ? "game" : side === "sp" ? "start" : "appearance";
    var note = "Each point pools the " + W + " " + noun + " ending at that " + lead + "; the line starts once "
      + W + " are in." + (side === "sp" ? " Innings are decimals (5.5 is five and a half)." : "")
      + (side === "rel" ? " gmLI is the Leverage Index when he entered; 1.00 is average." : "") + thru;
    return out + rollTable(R, tcols) + '<p class="mlbx-dnote">' + esc(note) + "</p>";
  }

  // ---- the drawer ----------------------------------------------------------------
  var OPEN = null;     // {mount, ctx}: the one open drawer
  function state(kind, msg) {
    var S = (typeof window !== "undefined") && window.EephusState;
    return S ? S.html(kind, msg) : '<div class="px-state is-' + kind + '"' + (kind === "failed" ? ' role="alert"' : "")
      + '><div class="px-state-msg">' + msg + "</div></div>";
  }
  function panelWidth(el) {
    var w = el && el.clientWidth;
    return Math.max(240, Math.round(w || 320));
  }
  function panel(key, title, body) {
    return '<section class="mlbx-dpanel" aria-label="' + esc(title) + '"><div class="mlbx-dpanel-h">' + esc(title)
      + '</div><div class="mlbx-dbody" data-mlbxd="' + key + '">' + body + "</div></section>";
  }
  function slot(key) {
    return OPEN && OPEN.mount.querySelector ? OPEN.mount.querySelector('[data-mlbxd="' + key + '"]') : null;
  }
  function rollTitle(ctx) {
    var side = BOARDS[ctx.board].roll;
    return "Last " + winPick[side] + " " + WIN_NOUN[side];
  }
  function draw() {
    if (!OPEN) return;
    var ctx = OPEN.ctx, cfg = BOARDS[ctx.board];
    if (!cfg) return;
    var html = "", why = "";
    if (ctx.board === "war") {
      html = panel("war", "eWAR by season", "");
    } else if (cfg.custom && window.MLBX_BR_DRAWER) {
      html = window.MLBX_BR_DRAWER.panels(ctx, pctPanel, panel);
    } else {
      html = panel("trend", cfg.trend.label + " by season", state("loading", "Loading the seasons."))
        + panel("pct", "Percentile", pctPanel(ctx));
      if (cfg.roll) {
        html += panel("roll", "Rolling window", ctx.pool && ctx.pool.live
          ? state("loading", "Loading the game log.")
          : '<p class="mlbx-dnote">The rolling window reads the live season&#39;s game log. Open the Current board to see it.</p>');
      } else {
        why = ctx.board === "def" ? " Fielding runs are not counted game by game, so Defense draws no rolling window."
          : " Per-game WPA is not in the game logs this drawer reads, so Leverage draws no rolling window.";
      }
    }
    OPEN.mount.innerHTML = '<div class="mlbx-dgrid' + (ctx.board === "war" ? " is-one" : "") + '">' + html + "</div>"
      + '<div class="mlbx-dfoot"><span class="mlbx-dnote">Descriptive: every number here is what happened.' + why + "</span>"
      + '<span data-mlbxd="strip"></span></div>';
    if (ctx.board === "war") { var w = slot("war"); if (w) w.innerHTML = warBars(ctx, panelWidth(w)); }
    if (cfg.custom && window.MLBX_BR_DRAWER) window.MLBX_BR_DRAWER.after(OPEN.mount, ctx, panelWidth);
    drawTrend();
    drawRoll();
    drawStrip();
    if (ctx.wireGlossary) ctx.wireGlossary(OPEN.mount);
  }
  function drawTrend() {
    var el = slot("trend");
    if (!el || !OPEN) return;
    var ctx = OPEN.ctx;
    if (TRENDS) { el.innerHTML = trendChart(ctx, panelWidth(el)); return; }
    if (TRENDS_ERR) {
      el.innerHTML = state("failed", 'The seasons did not load. <button type="button" class="chip" data-mlbxd-retry="trend">Retry</button>');
      return;
    }
    var p = loadTrends();
    if (p) p.then(function () { if (OPEN && OPEN.ctx === ctx) drawTrend(); });
  }
  function drawRoll() {
    var el = slot("roll");
    if (!el || !OPEN) return;
    var ctx = OPEN.ctx, cfg = BOARDS[ctx.board], id = String(ctx.id);
    if (!cfg.roll || !(ctx.pool && ctx.pool.live)) return;
    var h = el.parentNode && el.parentNode.querySelector ? el.parentNode.querySelector(".mlbx-dpanel-h") : null;
    if (h) h.textContent = rollTitle(ctx);
    if (SHARDS[id]) { el.innerHTML = rollPanel(ctx, panelWidth(el)); return; }
    if (SHARD_ERR[id]) {
      el.innerHTML = '<p class="mlbx-dnote">The rolling window is not built for this player. '
        + '<button type="button" class="chip" data-mlbxd-retry="roll">Retry</button></p>';
      return;
    }
    var p = loadShard(id);
    if (p) p.then(function () { if (OPEN && OPEN.ctx === ctx) drawRoll(); });
  }
  function drawStrip() {
    var el = slot("strip"), H = hub();
    if (!el || !H || !H.links || !H.stripHTML) return;
    var ctx = OPEN.ctx;
    H.links().then(function (L) {
      var row = L && L.byMlbam && L.byMlbam[String(ctx.id)];
      if (!row || !OPEN || OPEN.ctx !== ctx) return;
      var s = slot("strip");
      if (s) s.innerHTML = H.stripHTML(row, "mlbstats");
    });
  }
  function fill(mount, ctx) {
    if (!mount) return;
    try { mount.setAttribute("data-mlbdrawer-done", "1"); } catch (e) { /* stub DOM */ }
    OPEN = { mount: mount, ctx: ctx };
    draw();
  }
  try {
    document.addEventListener("click", function (e) {
      var t = e.target && e.target.closest ? e.target : null;
      if (!t || !OPEN) return;
      var b = t.closest("[data-mlbxd-win]");
      if (b) {
        var p = String(b.getAttribute("data-mlbxd-win")).split(":"), n = Number(p[1]);
        if (WINDOWS[p[0]] && WINDOWS[p[0]].indexOf(n) >= 0) { winPick[p[0]] = n; drawRoll(); }
        return;
      }
      var r = t.closest("[data-mlbxd-retry]");
      if (r) { if (r.getAttribute("data-mlbxd-retry") === "trend") { TRENDS_ERR = false; drawTrend(); } else { delete SHARD_ERR[String(OPEN.ctx.id)]; drawRoll(); } }
    });
    // Charts draw at their cell's real width, so a new width redraws them.
    var timer = null, lastW = window.innerWidth;
    window.addEventListener("resize", function () {
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        if (!OPEN || window.innerWidth === lastW) return;
        lastW = window.innerWidth;
        if (document.body && document.body.contains && !document.body.contains(OPEN.mount)) { OPEN = null; return; }
        draw();
      }, 150);
    });
  } catch (e) { /* no document events */ }

  window.MLBX_DRAWER = { fill: fill, percentiles: percentiles, pctRank: pctRank, rolling: rolling,
                         pctPanel: pctPanel, boards: BOARDS, windows: WINDOWS };
  if (typeof window.MLBX_DRAWER_READY === "function") window.MLBX_DRAWER_READY();
})();
