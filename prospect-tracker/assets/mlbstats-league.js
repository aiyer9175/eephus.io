/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// /mlbstats/ League tab: League Averages and Over time (owner asks 13 and 14 of
// 2026-09-30; final-pass plan Part 8 item P8.2, task LT-08, the League half).
// =============================================================================
// Lazy: assets/mlbstats.js injects this file once, the first time the League
// tab opens (showSection), from data-league-src on the /mlbstats/ root. The
// landing section never asks for it, and the shell carries the tab only while
// league_averages.MLBSTATS_LEAGUE_TEAMS_LIVE is True (build_site.build_mlbstats).
//
// WHAT IT SHOWS. Averages: rows are statistics, columns the pooled League value
// of the players shown, "vs all" (only while a filter is on: this pool minus the
// same side with no filter, signed, in text ink, never coloured, because whether
// higher is better differs by statistic), and the player distribution (mean,
// median, sample SD, n) over the floor. Over time: one statistic 2000 to the
// live season, one comparison group, small multiples and a numbers table.
//
// ONE RECIPE. A pool that is one of the exporter's precomputed groups prints the
// payload's own numbers, which league_averages.py derived through the shipped
// derivations (mlbstats_rates over hem_plus and sem_plus). A combined filter is
// pooled here from the payload's player rows with the same rule, rounding
// included; test_mlbstats_league_page.py pins that this pooling reproduces every
// precomputed group of a real season, so the two paths cannot drift apart.
//
// DESCRIPTIVE ONLY. Nothing here is a forecast. No group is keyed by a grade,
// no matchup (vs-hand) split exists, and no club filter is offered; the payload
// carries the reason for each and the page prints it.
//
// HASH KEYS use the g prefix (Leverage owns lview and lseason): gview, gside,
// gseason, gpos, grole, ghand, gage, gqual, glg, gstat, gcmp. Only non-defaults
// are written, through mlbstats.js writeHash, which asks hashParts().
(function () {
  "use strict";

  var DATA_DIR = "/data/";
  var PANEL_STEM = "mlb_league_panel_";
  var SERIES_FILE = "mlb_league_series.json";
  var DASH = " - ";

  // ---- small helpers ---------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isN(v) { return v != null && v !== "" && typeof v !== "boolean" && isFinite(v); }
  function num(v) { return isN(v) ? Number(v) : null; }
  // Python's round(x, n): correctly rounded, an exact tie goes to the even
  // digit. toFixed is correctly rounded too except on an exact tie, where it
  // rounds away from zero, so a tie is detected on the exact decimal digits.
  function pyRound(x, n) {
    if (!isN(x)) return null;
    x = Number(x);
    var neg = x < 0, a = Math.abs(x);
    var s = a.toFixed(n + 20), dot = s.indexOf(".");
    var head = s.slice(0, dot + 1 + n), tail = s.slice(dot + 1 + n);
    var out;
    if (/^50*$/.test(tail)) {
      var last = n > 0 ? head.charAt(head.length - 1) : head.charAt(dot - 1);
      out = (Number(last) % 2 === 0) ? Number(head) : Number(a.toFixed(n));
    } else {
      out = Number(a.toFixed(n));
    }
    return neg ? -out : out;
  }
  // Neumaier summation, so a mean matches Python's statistics.fmean (math.fsum)
  // to the last place on the values a pool carries.
  function fsum(xs) {
    var s = 0, c = 0;
    for (var i = 0; i < xs.length; i++) {
      var x = xs[i], t = s + x;
      if (Math.abs(s) >= Math.abs(x)) c += (s - t) + x; else c += (x - t) + s;
      s = t;
    }
    return s + c;
  }
  function ratio(n, d) {
    n = num(n); d = num(d);
    return (n == null || d == null || d <= 0) ? null : n / d;
  }
  function safeDiv(a, b) {
    a = num(a); b = num(b);
    return (a == null || b == null || b === 0) ? null : a / b;
  }

  // ---- state and the hash ----------------------------------------------------
  var VIEWS = ["avg", "time"], SIDES = ["hit", "pit", "team"];
  var DEFAULT_STAT = { hit: "p_per_pa", pit: "p_per_ip", team: "p_per_pa" };
  var S = { view: "avg", side: "hit", season: null, pos: [], role: [], hand: [], age: "",
            qual: "", lg: "", stat: "", cmp: "" };
  var RE = {
    view: /(?:^#|[#&])gview=(avg|time)\b/, side: /(?:^#|[#&])gside=(hit|pit|team)\b/,
    season: /(?:^#|[#&])gseason=(\d{4})\b/, pos: /(?:^#|[#&])gpos=([A-Za-z0-9,]+)/,
    role: /(?:^#|[#&])grole=([A-Za-z,]+)/, hand: /(?:^#|[#&])ghand=([LRS,]+)/,
    age: /(?:^#|[#&])gage=(age_[a-z0-9_]+)\b/, qual: /(?:^#|[#&])gqual=(floor|board|title|\d{1,4})\b/,
    lg: /(?:^#|[#&])glg=(AL|NL)\b/, stat: /(?:^#|[#&])gstat=([a-z0-9_]+)\b/,
    cmp: /(?:^#|[#&])gcmp=([A-Za-z0-9_]+)\b/
  };
  var POS_OK = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH", "other", "P"];
  var ROLE_OK = ["SP", "RP", "SW", "POS"];
  function list(m, ok) {
    if (!m) return [];
    var out = [];
    m[1].split(",").forEach(function (x) { if (ok.indexOf(x) >= 0 && out.indexOf(x) < 0) out.push(x); });
    return out;
  }
  function readHash(h) {
    h = h || "";
    var m;
    if ((m = RE.view.exec(h))) S.view = m[1];
    if ((m = RE.side.exec(h))) S.side = m[1];
    if ((m = RE.season.exec(h))) S.season = Number(m[1]);
    S.pos = list(RE.pos.exec(h), POS_OK);
    S.role = list(RE.role.exec(h), ROLE_OK);
    S.hand = list(RE.hand.exec(h), ["L", "R", "S"]);
    if ((m = RE.age.exec(h))) S.age = m[1];
    if ((m = RE.qual.exec(h))) S.qual = m[1];
    if ((m = RE.lg.exec(h))) S.lg = m[1];
    if ((m = RE.stat.exec(h))) S.stat = m[1];
    if ((m = RE.cmp.exec(h))) S.cmp = m[1];
    if (S.side === "pit") S.hand = S.hand.filter(function (x) { return x !== "S"; });
  }
  function statOf(side) { return S.stat || DEFAULT_STAT[side]; }
  function hashParts() {
    var p = [];
    if (S.view !== "avg") p.push("gview=" + S.view);
    if (S.side !== "hit") p.push("gside=" + S.side);
    if (S.season) p.push("gseason=" + S.season);
    if (S.pos.length) p.push("gpos=" + S.pos.join(","));
    if (S.role.length) p.push("grole=" + S.role.join(","));
    if (S.hand.length) p.push("ghand=" + S.hand.join(","));
    if (S.age) p.push("gage=" + S.age);
    if (S.qual) p.push("gqual=" + S.qual);
    if (S.lg) p.push("glg=" + S.lg);
    if (S.stat && S.stat !== DEFAULT_STAT[S.side]) p.push("gstat=" + S.stat);
    if (S.cmp) p.push("gcmp=" + S.cmp);
    return p;
  }
  function setSide(side) {
    if (SIDES.indexOf(side) < 0 || side === S.side) return;
    S.side = side; S.pos = []; S.role = []; S.hand = []; S.age = ""; S.qual = ""; S.lg = "";
    S.stat = ""; S.cmp = "";
  }

  // ---- data ------------------------------------------------------------------
  var CTX = null, PANELS = {}, SERIES = null, SERIES_STATE = "", ROWS = {};
  function liveSeason() {
    var r = CTX && CTX.root, v = r && r.getAttribute ? Number(r.getAttribute("data-league-live")) : NaN;
    if (v > 1900) return v;
    try { return new Date().getFullYear(); } catch (e) { return null; }
  }
  function seasonOf() { return S.season || liveSeason(); }
  function getJSON(url, done) {
    try {
      fetch(url, { cache: "no-cache" })
        .then(function (r) { return (r && r.ok) ? r.json() : null; })
        .then(function (j) { done(j || null); }, function () { done(null); });
    } catch (e) { done(null); }
  }
  function loadPanel(y) {
    if (PANELS[y]) return;
    PANELS[y] = "loading";
    getJSON(DATA_DIR + PANEL_STEM + y + ".json", function (j) {
      PANELS[y] = (j && j.hit && j.pit) ? j : "error";
      if (CTX && CTX.active()) render();
    });
  }
  function loadSeries() {
    if (SERIES_STATE) return;
    SERIES_STATE = "loading";
    getJSON(DATA_DIR + SERIES_FILE, function (j) {
      SERIES = (j && j.seasons) ? j : null;
      SERIES_STATE = SERIES ? "ok" : "error";
      if (CTX && CTX.active()) render();
    });
  }
  function rowsOf(doc, side) {
    var key = doc.season + ":" + side;
    if (ROWS[key]) return ROWS[key];
    var blk = doc[side] || {}, cols = blk.cols || [];
    ROWS[key] = (blk.rows || []).map(function (a) {
      var o = {};
      for (var i = 0; i < cols.length; i++) o[cols[i]] = a[i];
      return o;
    });
    return ROWS[key];
  }

  // ---- pooling (league_averages.hit_stats / pit_stats, rounding included) -----
  var HIT_ACC = [["pa", "pa"], ["ab", "ab"], ["h", "h"], ["2b", "d"], ["3b", "t"], ["hr", "hr"],
                 ["bb", "bb"], ["ibb", "ibb"], ["hbp", "hbp"], ["sf", "sf"], ["so", "so"],
                 ["sb", "sb"], ["cs", "cs"]];
  var PIT_ACC = [["g", "g"], ["gs", "gs"], ["outs", "outs"], ["tbf", "bf"], ["er", "er"],
                 ["r", "r"], ["bb", "bb"], ["so", "so"], ["hr", "hr"], ["hbp", "hbp"],
                 ["pit", "pit"], ["strk", "strk"], ["cg", "cg"], ["go", "go"], ["ao", "ao"],
                 ["sv", "sv"], ["hld", "hld"]];
  // Absent is not zero: a count no row carries stays absent.
  function acc(rows, pairs) {
    var out = {};
    rows.forEach(function (r) {
      pairs.forEach(function (p) {
        var v = num(r[p[1]]);
        if (v == null) return;
        out[p[0]] = (out[p[0]] || 0) + v;
      });
    });
    return out;
  }
  function pitched(rows, numCol, denCol) {
    var n = 0, d = 0;
    rows.forEach(function (r) {
      var p = num(r[numCol]);
      if (p == null) return;
      n += p;
      d += num(r[denCol]) || 0;
    });
    return [n, d];
  }
  function weighted(rows, valCol, wCol) {
    var n = 0, d = 0;
    rows.forEach(function (r) {
      var v = num(r[valCol]), w = num(r[wCol]);
      if (v == null || !w || w <= 0) return;
      n += v * w; d += w;
    });
    return d ? n / d : null;
  }
  // hem_plus.derive_rates on summed counts, rounded as mlbstats_rates rounds.
  function hitterRates(a) {
    var pa = a.pa || 0, ab = a.ab || 0, h = a.h || 0, d2 = a["2b"] || 0, d3 = a["3b"] || 0,
        hr = a.hr || 0, bb = a.bb || 0, hbp = a.hbp || 0, sf = a.sf || 0, so = a.so || 0;
    var s1 = Math.max(0, h - d2 - d3 - hr);
    var tb = s1 + 2 * d2 + 3 * d3 + 4 * hr;
    var obp = safeDiv(h + bb + hbp, ab + bb + hbp + sf), slg = safeDiv(tb, ab);
    return {
      avg: pyRound(safeDiv(h, ab), 3), obp: pyRound(obp, 3), slg: pyRound(slg, 3),
      ops: (obp != null && slg != null) ? pyRound(obp + slg, 3) : null,
      iso: pyRound(safeDiv(tb - h, ab), 3),
      babip: pyRound(safeDiv(h - hr, ab - so - hr + sf), 3),
      bb_pct: pyRound(safeDiv(bb, pa), 4), k_pct: pyRound(safeDiv(so, pa), 4)
    };
  }
  // sem_plus.derive_rates on summed counts, the innings rebuilt the way
  // bullpen_export.ip_to_float reads "X.Y" notation.
  function pitcherRates(a) {
    var outs = Math.trunc(a.outs || 0);
    var ip = Math.floor(outs / 3) + (outs % 3) / 3;
    var tbf = a.tbf || 0, so = a.so || 0, bb = a.bb || 0, go = a.go || 0, ao = a.ao || 0;
    var k = safeDiv(so, tbf), b = safeDiv(bb, tbf);
    var hr9 = (outs / 3) ? pyRound((a.hr || 0) * 9 / (outs / 3), 2) : null;
    return {
      era: pyRound(safeDiv((a.er || 0) * 9, ip), 2), hr9: pyRound(hr9, 2),
      k_pct: pyRound(k, 4), bb_pct: pyRound(b, 4),
      k_bb_pct: (k == null || b == null) ? null : pyRound(k - b, 4),
      gb_pct: pyRound(safeDiv(go, go + ao), 4),
      ip_per_gs: pyRound(safeDiv(ip, a.gs || 0), 2),
      strike_pct: pyRound(safeDiv(a.strk || 0, a.pit || 0), 4)
    };
  }
  function hitStats(rows) {
    var a = acc(rows, HIT_ACC), out = {};
    if (a.pa) {
      var rt = hitterRates(a);
      ["avg", "obp", "slg", "ops", "iso", "babip", "k_pct", "bb_pct"].forEach(function (k) { out[k] = rt[k]; });
      out.hr_pct = ratio(a.hr, a.pa);
    }
    var pp = pitched(rows, "pit", "pa");
    out.p_per_pa = ratio(pp[0], pp[1]);
    var sb = a.sb || 0, cs = a.cs || 0;
    out.sb_pct = ratio(sb, sb + cs);
    out.hem = weighted(rows, "hem", "pa");
    out.dem = weighted(rows, "dem", "inn");
    var war = 0, wpa = 0;
    rows.forEach(function (r) { if (num(r.war) != null && (r.pa || 0) > 0) { war += num(r.war); wpa += r.pa; } });
    out.war_600 = wpa ? war / wpa * 600 : null;
    return out;
  }
  function pitStats(rows, fipC) {
    var a = acc(rows, PIT_ACC), out = {}, outs = a.outs || 0;
    if (outs > 0) {
      var rt = pitcherRates(a);
      ["era", "hr9", "k_pct", "bb_pct", "k_bb_pct", "gb_pct", "ip_per_gs", "strike_pct"].forEach(function (k) { out[k] = rt[k]; });
      var ip = outs / 3;
      var core = (13 * (a.hr || 0) + 3 * ((a.bb || 0) + (a.hbp || 0)) - 2 * (a.so || 0)) / ip;
      out.fip = fipC == null ? null : core + fipC;
      var h = 0;
      rows.forEach(function (r) { h += num(r.h) || 0; });
      out.whip = (h + (a.bb || 0)) / ip;
    }
    var po = pitched(rows, "pit", "outs");
    out.p_per_ip = (po[1] > 0) ? ratio(po[0], po[1] / 3) : null;
    var pb = pitched(rows, "pit", "bf");
    out.p_per_bf = ratio(pb[0], pb[1]);
    function ipRows(board) {
      return rows.filter(function (r) { return r.plus_board === board; })
        .map(function (r) { return { plus: r.plus, ip: (r.outs || 0) / 3 }; });
    }
    out.sem = weighted(ipRows("sem"), "plus", "ip");
    out.rem = weighted(ipRows("rem"), "plus", "ip");
    var war = 0, wouts = 0;
    rows.forEach(function (r) { if (num(r.war) != null && (r.outs || 0) > 0) { war += num(r.war); wouts += r.outs; } });
    out.war_200 = wouts ? war / (wouts / 3) * 200 : null;
    return out;
  }
  function playerHit(r) {
    var v = hitStats([r]);
    v.hem = num(r.hem);
    v.dem = num(r.inn) ? num(r.dem) : null;
    return v;
  }
  function playerPit(r, fipC) {
    var v = pitStats([r], fipC);
    v.sem = r.plus_board === "sem" ? num(r.plus) : null;
    v.rem = r.plus_board === "rem" ? num(r.plus) : null;
    return v;
  }
  function dist(values, nd) {
    var xs = values.filter(isN).map(Number);
    if (!xs.length) return null;
    var n = xs.length, mean = fsum(xs) / n;
    var srt = xs.slice().sort(function (p, q) { return p - q; });
    var med = n % 2 ? srt[(n - 1) / 2] : (srt[n / 2 - 1] + srt[n / 2]) / 2;
    var sd = null;
    if (n > 1) sd = Math.sqrt(fsum(xs.map(function (x) { return (x - mean) * (x - mean); })) / (n - 1));
    return { mean: pyRound(mean, nd), median: pyRound(med, nd), sd: pyRound(sd, nd), n: n };
  }
  function floorOf(doc) { return ((doc.qualify || {}).floor) || {}; }
  // league_averages._group_block for one pool of rows.
  function poolBlock(doc, side, rows) {
    var fipC = num((doc.constants || {}).fip_constant), fl = floorOf(doc);
    var pooled, floor, den;
    if (side === "hit") {
      pooled = hitStats(rows);
      floor = rows.filter(function (r) { return (r.pa || 0) >= num(fl.pa); });
      den = { pa: rows.reduce(function (s, r) { return s + (r.pa || 0); }, 0) };
    } else {
      pooled = pitStats(rows, fipC);
      floor = rows.filter(function (r) { return (r.outs || 0) >= num(fl.ip) * 3; });
      den = { ip: pyRound(rows.reduce(function (s, r) { return s + (r.outs || 0); }, 0) / 3, 1) };
    }
    var per = floor.map(function (r) { return side === "hit" ? playerHit(r) : playerPit(r, fipC); });
    var league = {}, dst = {};
    ((doc.stats || {})[side] || []).forEach(function (sd) {
      if (sd.key === "sp_ip_per_gs") return;
      league[sd.key] = pyRound(pooled[sd.key], sd.nd);
      var d = dist(per.map(function (v) { return v[sd.key]; }), sd.nd);
      if (d) dst[sd.key] = d;
    });
    var out = { n: rows.length, n_floor: floor.length, league: league, dist: dst };
    Object.keys(den).forEach(function (k) { out[k] = den[k]; });
    return out;
  }

  // ---- filters -----------------------------------------------------------------
  var AGE_EDGES = { age_24u: [null, 24], age_25_27: [25, 27], age_28_30: [28, 30],
                    age_31_33: [31, 33], age_34o: [34, null] };
  function ageBand(a) {
    a = num(a);
    if (a == null) return null;
    for (var k in AGE_EDGES) {
      var e = AGE_EDGES[k];
      if ((e[0] == null || a >= e[0]) && (e[1] == null || a <= e[1])) return k;
    }
    return null;
  }
  function positions(doc) {
    return ((((doc.filters || {}).hit || {}).pos || {}).values || []).filter(function (p) { return p !== "other"; });
  }
  // One row through the filter state `st` (the module state unless a caller
  // passes its own). Pitchers batting and position players pitching are each
  // one toggle (P in gpos, POS in grole), off by default, as the payload's
  // default groups are.
  function passes(doc, side, r, st) {
    var fl = floorOf(doc), q = st.qual;
    if (side === "hit") {
      var isP = (r.pos || "") === "P";
      if (isP) { if (st.pos.indexOf("P") < 0) return false; }
      else {
        var chips = st.pos.filter(function (x) { return x !== "P"; });
        if (chips.length) {
          var pk = positions(doc).indexOf(r.pos) >= 0 ? r.pos : "other";
          if (chips.indexOf(pk) < 0) return false;
        }
      }
      if (st.hand.length && st.hand.indexOf(r.bats) < 0) return false;
      if (q === "floor" && !((r.pa || 0) >= num(fl.pa))) return false;
      if (/^\d+$/.test(q || "") && !((r.pa || 0) >= Number(q))) return false;
    } else {
      var pitcher = (r.pos || "") === "P";
      if (!pitcher) { if (st.role.indexOf("POS") < 0) return false; }
      else {
        var roles = st.role.filter(function (x) { return x !== "POS"; });
        if (roles.length && roles.indexOf(r.role) < 0) return false;
      }
      if (st.hand.length && st.hand.indexOf(r.throws) < 0) return false;
      if (q === "floor" && !((r.outs || 0) >= num(fl.ip) * 3)) return false;
      if (/^\d+$/.test(q || "") && !((r.outs || 0) >= Number(q) * 3)) return false;
    }
    if (st.age && ageBand(r.age) !== st.age) return false;
    if (q === "board" && !r.bq) return false;
    if (q === "title" && !r.tq) return false;
    if (st.lg && r.lg !== st.lg) return false;
    return true;
  }
  function filtersOn(st) {
    return !!(st.pos.length || st.role.length || st.hand.length || st.age || st.qual || st.lg);
  }
  // The payload group a state is exactly, or null for a combination.
  function groupKey(side, st) {
    var n = (st.pos.length ? 1 : 0) + (st.role.length ? 1 : 0) + (st.hand.length ? 1 : 0)
      + (st.age ? 1 : 0) + (st.qual ? 1 : 0) + (st.lg ? 1 : 0);
    if (side === "hit") {
      if (!n) return "all";
      if (n > 1 || st.role.length) return null;
      if (st.pos.length === 1) return st.pos[0] === "P" ? "all_incl_p" : "pos_" + st.pos[0];
      if (st.pos.length) return null;
      if (st.hand.length === 1) return "bats_" + st.hand[0];
    } else {
      if (!n) return "pitchers_only";
      if (n > 1 || st.pos.length) return null;
      if (st.role.length === 1) return st.role[0] === "POS" ? "all" : "role_" + st.role[0];
      if (st.role.length) return null;
      if (st.hand.length === 1) return "throws_" + st.hand[0];
    }
    if (st.hand.length) return null;
    if (st.age) return st.age;
    if (st.qual === "floor" || st.qual === "board" || st.qual === "title") return "sample_" + st.qual;
    if (st.qual) return null;
    if (st.lg) return "lg_" + st.lg;
    return null;
  }
  function blockFor(doc, side, st) {
    var key = groupKey(side, st);
    var g = key && ((doc.groups || {})[side] || {})[key];
    if (g && g.league) return g;
    return poolBlock(doc, side, rowsOf(doc, side).filter(function (r) { return passes(doc, side, r, st); }));
  }
  function emptyState() { return { pos: [], role: [], hand: [], age: "", qual: "", lg: "" }; }

  // ---- formatting ------------------------------------------------------------
  var PCT = { k_pct: 1, bb_pct: 1, hr_pct: 1, k_bb_pct: 1, gb_pct: 1, strike_pct: 1,
              relief_ip_share: 1, sb_pct: 1 };
  var DOT = { avg: 1, obp: 1, slg: 1, ops: 1, iso: 1, babip: 1, w_pct: 1 };
  function defOf(doc, side, key) {
    var d = null;
    ((doc.stats || {})[side] || []).forEach(function (x) { if (x.key === key) d = x; });
    return d;
  }
  function fmt(key, v, sd) {
    if (!isN(v)) return DASH;
    v = Number(v);
    if (PCT[key]) return (v * 100).toFixed(1) + "%";
    if (sd && sd.index) return v.toFixed(1);
    var nd = sd && isN(sd.nd) ? sd.nd : 2;
    var s = v.toFixed(nd);
    return (DOT[key] && Math.abs(v) < 1) ? s.replace(/^(-?)0\./, "$1.") : s;
  }
  function fmtSpread(key, v, sd) {
    if (!isN(v)) return DASH;
    return PCT[key] ? (Number(v) * 100).toFixed(1) : fmt(key, v, sd);
  }
  // The signed difference of the two PRINTED values, in the statistic's own
  // unit (percentage points for a percentage). Text ink: no colour says better.
  function fmtDelta(key, a, b, sd) {
    if (!isN(a) || !isN(b)) return DASH;
    var nd = PCT[key] ? 1 : (sd && sd.index ? 1 : (isN(sd && sd.nd) ? sd.nd : 2));
    var d = PCT[key] ? Number(fmtSpread(key, a, sd)) - Number(fmtSpread(key, b, sd)) : Number(a) - Number(b);
    d = pyRound(d, nd);
    var s = Math.abs(d).toFixed(nd);
    if (d === 0) return (DOT[key] ? s.replace(/^0\./, ".") : s) + (PCT[key] ? " pts" : "");
    if (DOT[key]) s = s.replace(/^0\./, ".");
    return (d > 0 ? "+" : "-") + s + (PCT[key] ? " pts" : "");
  }
  var GL = { hem: "hem_plus", sem: "sem_plus", rem: "rem_plus", dem: "dem_plus", era: "era", fip: "fip",
             whip: "whip", babip: "babip", ops: "ops", iso: "iso", avg: "avg", obp: "obp", slg: "slg",
             k_bb_pct: "k_bb_pct", p_per_ip: "pitches_per_ip" };
  var GL_SIDE = { hit: { k_pct: "k_pct", bb_pct: "bb_pct" }, pit: { k_pct: "k_pct_pitcher", bb_pct: "bb_pct_pitcher" } };
  function label(side, sd) {
    var term = (GL_SIDE[side] || {})[sd.key] || GL[sd.key];
    var lab = esc(sd.label);
    return (term && CTX && CTX.gloss) ? CTX.gloss(sd.label, term) : lab;
  }
  var FAMILIES = {
    hit: [["Slash line", ["avg", "obp", "slg", "ops", "iso", "babip"]],
          ["Plate appearances", ["k_pct", "bb_pct", "hr_pct", "p_per_pa", "sb_pct"]],
          ["Indexes", ["hem", "dem"]], ["Value", ["war_600"]]],
    pit: [["Run prevention", ["era", "fip", "whip"]],
          ["Rates", ["k_pct", "bb_pct", "k_bb_pct", "hr9", "gb_pct", "strike_pct"]],
          ["Pitch counts and workload", ["p_per_ip", "p_per_bf", "ip_per_gs", "sp_ip_per_gs"]],
          ["Indexes", ["sem", "rem"]], ["Value", ["war_200"]]],
    team: [["Runs and record", ["rs_g", "ra_g", "w_pct"]],
           ["Pitch counts", ["p_per_pa", "p_per_ip", "sp_p_per_ip", "rp_p_per_ip"]],
           ["Workload", ["sp_ip_per_gs", "relief_ip_share"]]]
  };
  // The payload's statistic definitions in family order; a statistic the
  // families do not name still prints, under Other, so a new payload key is
  // never dropped.
  function grouped(doc, side) {
    var defs = (doc.stats || {})[side] || [], seen = {}, out = [];
    (FAMILIES[side] || []).forEach(function (f) {
      var ds = f[1].map(function (k) { return defs.filter(function (d) { return d.key === k; })[0]; })
        .filter(Boolean);
      ds.forEach(function (d) { seen[d.key] = 1; });
      if (ds.length) out.push([f[0], ds]);
    });
    var rest = defs.filter(function (d) { return !seen[d.key]; });
    if (rest.length) out.push(["Other", rest]);
    return out;
  }

  // ---- controls ----------------------------------------------------------------
  function sidePills(withTeam) {
    var opts = [["hit", "Hitters"], ["pit", "Pitchers"]];
    if (withTeam) opts.push(["team", "Teams"]);
    return '<div class="mlbstats-seasons mlbx-lgside" role="group" aria-label="Side">'
      + opts.map(function (o) {
          var on = S.side === o[0];
          return '<button type="button" class="mlbstats-season' + (on ? " active" : "") + '" data-gside="'
            + o[0] + '" aria-pressed="' + on + '">' + o[1] + "</button>";
        }).join("") + "</div>";
  }
  function selectCtl(id, lab, key, opts, cur, title) {
    return '<label class="mlbstats-ctl"' + (title ? ' title="' + esc(title) + '"' : "") + ">" + esc(lab)
      + ' <select id="' + id + '" data-gsel="' + key + '">'
      + opts.map(function (o) {
          return '<option value="' + esc(o[0]) + '"' + (String(cur) === String(o[0]) ? " selected" : "") + ">"
            + esc(o[1]) + "</option>";
        }).join("") + "</select></label>";
  }
  function chipGroup(lab, key, opts) {
    var cur = S[key];
    return '<div class="mlbstats-seasons" role="group" aria-label="' + esc(lab) + '">'
      + '<span class="mlbstats-roles-lbl">' + esc(lab) + "</span>"
      + '<button type="button" class="mlbstats-season' + (cur.filter(function (x) { return opts.some(function (o) { return o[0] === x; }); }).length ? "" : " active")
      + '" data-gchip="' + key + ':" aria-pressed="false">All</button>'
      + opts.map(function (o) {
          var on = cur.indexOf(o[0]) >= 0;
          return '<button type="button" class="mlbstats-season' + (on ? " active" : "") + '" data-gchip="' + key + ":"
            + esc(o[0]) + '" aria-pressed="' + on + '">' + esc(o[1]) + "</button>";
        }).join("") + "</div>";
  }
  function seasonOptions(doc) {
    var first = num((((doc || {}).filters || {}).season || {}).first) || seasonOf(), live = liveSeason();
    var out = [];
    for (var y = live; y >= first; y--) out.push([String(y), String(y) + (y === live ? " (live)" : "")]);
    return out;
  }
  function filterCount() {
    return S.pos.length + S.role.length + S.hand.length + (S.age ? 1 : 0) + (S.qual ? 1 : 0) + (S.lg ? 1 : 0);
  }
  function controls(doc) {
    var side = S.side, fl = floorOf(doc), f = ((doc.filters || {})[side]) || {};
    var unit = side === "hit" ? "PA" : "IP";
    var sample = [["", "Every player"],
                  ["floor", (side === "hit" ? num(fl.pa) + "+ PA" : num(fl.ip) + "+ IP")],
                  ["board", "Board qualified"], ["title", "Title qualified"], ["custom", "Custom minimum"]];
    var custom = /^\d+$/.test(S.qual || "");
    var ages = [["", "All ages"]].concat(((f.age || {}).values || []).map(function (a) { return [a.key, a.label]; }));
    var bar = '<div class="' + (CTX.filtCls ? CTX.filtCls() : "mlbstats-bar") + '">'
      + (CTX.filtBtn ? CTX.filtBtn(filterCount()) : "")
      + selectCtl("mlbx-lg-season", "season", "season", seasonOptions(doc), seasonOf())
      + (side === "team" ? "" :
          selectCtl("mlbx-lg-age", "age", "age", ages, S.age)
          + selectCtl("mlbx-lg-qual", "sample", "qual", sample, custom ? "custom" : S.qual,
              "Board qualified is each board's own rule; title qualified is the batting or ERA title rule on the player's last club's games.")
          + (custom ? '<label class="mlbstats-ctl">min ' + unit + ' <input class="mlbstats-minnum" type="number" min="0" step="1"'
              + ' inputmode="numeric" id="mlbx-lg-min" data-gmin="1" value="' + esc(S.qual) + '" aria-label="Minimum ' + unit + '"></label>' : "")
          + selectCtl("mlbx-lg-lg", "league", "lg", [["", "Both leagues"], ["AL", "AL"], ["NL", "NL"]], S.lg,
              "The league of the player's last club.")
          + (side === "hit"
              ? '<label class="mlbstats-ctl"><input type="checkbox" data-gtoggle="pos:P"' + (S.pos.indexOf("P") >= 0 ? " checked" : "")
                + "> pitchers batting</label>"
              : '<label class="mlbstats-ctl"><input type="checkbox" data-gtoggle="role:POS"' + (S.role.indexOf("POS") >= 0 ? " checked" : "")
                + "> position players pitching</label>"))
      + "</div>";
    if (side === "team") return bar;
    var chips = side === "hit"
      ? chipGroup("Position", "pos", positions(doc).map(function (p) { return [p, p]; }).concat([["other", "Other"]]))
        + chipGroup("Bats", "hand", [["L", "L"], ["R", "R"], ["S", "S"]])
      : chipGroup("Role", "role", [["SP", "SP"], ["RP", "RP"], ["SW", "Swing"]])
        + chipGroup("Throws", "hand", [["L", "L"], ["R", "R"]]);
    return bar + '<div class="mlbstats-roles mlbx-lgchips">' + chips + "</div>";
  }

  // ---- the Averages view -------------------------------------------------------
  function seasonNote(doc) {
    var d = doc.complete ? { season: doc.season } : { season: doc.season, as_of: doc.as_of };
    return CTX.bannerHTML ? CTX.bannerHTML(d) : "";
  }
  // Every figure in this sentence is read from the panel: the row counts, the
  // join counts and the games per club. Nothing here is typed.
  function coverageHTML(doc, side, blk) {
    var c = doc.coverage || {}, fl = floorOf(doc), bits = [];
    if (side === "team") {
      bits.push(esc(c.n_teams) + " clubs, pooled over their own season lines");
    } else {
      var dv = side === "hit" ? blk.pa : blk.ip;
      var den = (isN(dv) ? Number(dv).toLocaleString("en-US") : DASH) + (side === "hit" ? " PA" : " IP");
      bits.push(esc(blk.n) + " players in this pool, " + esc(den));
      bits.push(esc(blk.n_floor) + " at or above " + (side === "hit" ? esc(fl.pa) + " PA" : esc(fl.ip) + " IP"));
      var nh = (c.n_hand || {})[side], na = (c.n_age || {})[side];
      bits.push("MLB season lines: " + esc(c.n_hit) + " hitting and " + esc(c.n_pit) + " pitching"
        + "; " + (side === "hit" ? "bat side" : "throwing hand") + " known for " + esc(nh) + ", age for " + esc(na));
      var ni = c.n_index || {}, keys = side === "hit" ? ["hem", "dem"] : ["sem", "rem"];
      bits.push(keys.map(function (k) {
        var sd = defOf(doc, side, k);
        return esc(sd ? sd.label : k) + " for " + (isN(ni[k]) ? esc(ni[k]) : DASH);
      }).join(", "));
    }
    if (isN(doc.games_per_team)) bits.push(esc(doc.games_per_team) + " games per club");
    return '<div class="mlbstats-note mlbx-lgcov">' + bits.join(" &middot; ") + "</div>";
  }
  function indexNote(doc, side) {
    var src = (doc.sources || {}).index || {}, keys = side === "hit" ? ["hem", "dem"] : ["sem", "rem"];
    var parts = keys.filter(function (k) { return src[k]; }).map(function (k) {
      var sd = defOf(doc, side, k);
      return esc(sd ? sd.label : k) + ": " + esc(src[k]);
    });
    return parts.length ? parts.join("; ") : "";
  }
  // The fold: the lane's 3.5 copy, its floors read from the payload, then the
  // three filters left out and the one statistic deferred, each with the
  // payload's own reason.
  function foldHTML(doc) {
    var fl = floorOf(doc), n = doc.notes || {};
    var left = (n.left_out || []).map(function (x) {
      return "<li><b>" + esc(x.label) + ".</b> " + esc(x.reason) + "</li>";
    }).join("");
    var deferred = (n.deferred || []).map(function (x) {
      return "<li><b>" + esc(x.label) + ".</b> " + esc(x.reason) + "</li>";
    }).join("");
    return '<details class="mlbx-lgfold" data-gfold="about"' + (FOLD.about ? " open" : "") + ">"
      + "<summary>Every number here is what happened, pooled.</summary><div class=\"mlbx-lgfold-body\">"
      + "<p>League is pooled: each numerator summed over the players shown, over the denominator summed the same way."
      + " Player mean, median and SD are over players with " + esc(fl.pa) + " or more PA (" + esc(fl.ip)
      + " or more IP); the SD is the sample SD. Indexes are weighted by plate appearances or innings and read on"
      + " each board's own scale; 100 is the average qualified player of that board, not the league mean, which"
      + " is printed beside it. A traded player's season sits under his last club. Descriptive: not a forecast.</p>"
      + (left ? "<p>Left out on purpose:</p><ul>" + left + "</ul>" : "")
      + (deferred ? "<p>Not shown yet:</p><ul>" + deferred + "</ul>" : "")
      + "</div></details>";
  }
  function avgTable(doc) {
    var side = S.side, filtered = filtersOn(S);
    var blk = blockFor(doc, side, S);
    var base = filtered ? blockFor(doc, side, emptyState()) : null;
    var pitAll = side === "pit" ? ((doc.groups || {}).pit || {}).sp_innings : null;
    var nCols = filtered ? 7 : 6;
    var head = '<thead><tr><th scope="col">Statistic</th>'
      + '<th scope="col" class="mlbx-lgnum" title="Pooled: the numerator summed over the players shown, over the denominator summed the same way">League</th>'
      + (filtered ? '<th scope="col" class="mlbx-lgnum" title="This pool minus the same side with no filter, in the statistic\'s own unit (points for a percentage)">vs all</th>' : "")
      + '<th scope="col" class="mlbx-lgnum mlbstats-cv-wide" title="Mean of the players at or above the floor">Player mean</th>'
      + '<th scope="col" class="mlbx-lgnum mlbstats-cv-wide">Median</th>'
      + '<th scope="col" class="mlbx-lgnum mlbstats-cv-wide" title="Sample SD of the players at or above the floor">SD</th>'
      + '<th scope="col" class="mlbx-lgnum" title="Players at or above the floor with a value">Players</th></tr></thead>';
    var y = num(doc.season), idx = indexNote(doc, side);
    var body = grouped(doc, side).map(function (fam) {
      return '<tr class="mlbx-lggrp"><th scope="rowgroup" colspan="' + nCols + '">' + esc(fam[0]) + "</th></tr>"
        + fam[1].map(function (sd) {
          var k = sd.key, lg = blk.league[k], why = "";
          if (k === "sp_ip_per_gs") {
            lg = filtered ? null : ((pitAll || {}).league || {}).sp_ip_per_gs;
            why = filtered ? "League-wide only: the club starter splits carry no player filter." : "From the club starter splits: innings in starts over games started.";
          } else if (y != null && isN(sd.first) && y < sd.first) {
            why = "No source before " + sd.first + ".";
          }
          var d = (blk.dist || {})[k] || {};
          var tip = sd.formula + (sd.index && idx ? " (" + idx + ")" : "") + (why ? " " + why : "");
          var vs = filtered ? '<td class="mlbx-lgnum mlbx-lgvs">' + (k === "sp_ip_per_gs" ? DASH : fmtDelta(k, lg, base.league[k], sd)) + "</td>" : "";
          return '<tr><th scope="row" class="mlbx-lgstat" title="' + esc(tip) + '">' + label(side, sd) + "</th>"
            + '<td class="mlbx-lgnum mlbx-lgval"' + (why && !isN(lg) ? ' title="' + esc(why) + '"' : "") + ">" + fmt(k, lg, sd) + "</td>" + vs
            + '<td class="mlbx-lgnum mlbstats-cv-wide">' + fmt(k, d.mean, sd) + "</td>"
            + '<td class="mlbx-lgnum mlbstats-cv-wide">' + fmt(k, d.median, sd) + "</td>"
            + '<td class="mlbx-lgnum mlbstats-cv-wide">' + fmtSpread(k, d.sd, sd) + "</td>"
            + '<td class="mlbx-lgnum">' + (isN(d.n) ? esc(d.n) : DASH) + "</td></tr>";
        }).join("");
    }).join("");
    return coverageHTML(doc, side, blk)
      + '<div class="mlbstats-scroll"><table class="mlbstats-table mlbx-lgtable">' + head + "<tbody>" + body + "</tbody></table></div>"
      + playersFold(doc, blk);
  }
  // The players behind the averages: one dot per player at or above the floor,
  // the statistic against his PA or IP, the pooled League value as the
  // reference line. EEPHUS_HUB.scatter, drawn at the panel's real width.
  function playersFold(doc, blk) {
    var side = S.side, hub = window.EEPHUS_HUB;
    var defs = ((doc.stats || {})[side] || []).filter(function (d) { return d.key !== "sp_ip_per_gs"; });
    var key = statOf(side);
    if (!defs.some(function (d) { return d.key === key; })) key = defs.length ? defs[0].key : "";
    var sd = defOf(doc, side, key);
    if (!sd || !hub || !hub.scatter) return "";
    var fipC = num((doc.constants || {}).fip_constant), fl = floorOf(doc);
    var pts = [];
    rowsOf(doc, side).forEach(function (r) {
      if (!passes(doc, side, r, S)) return;
      var x = side === "hit" ? (r.pa || 0) : (r.outs || 0) / 3;
      if (x < (side === "hit" ? num(fl.pa) : num(fl.ip))) return;
      var v = (side === "hit" ? playerHit(r) : playerPit(r, fipC))[key];
      if (!isN(v)) return;
      pts.push({ x: x, y: Number(v), r: 2.5, color: "var(--viz-1)",
                 label: (r.name || r.mlbam) + (r.club ? ", " + r.club : "") + ": " + fmt(key, v, sd) });
    });
    var lg = blk.league[key];
    // The fold body is at most 760px (site.css .mlbx-lgfold-body) and the chart
    // box pads 13px a side, so 734 is the widest the dots are ever drawn.
    var SW = realWidth(734);
    var chart = pts.length >= 3 ? hub.scatter(pts, {
      width: SW, height: Math.round(Math.min(300, Math.max(220, SW * 0.42))),
      xLabel: side === "hit" ? "PA" : "IP", yLabel: sd.label,
      yRef: isN(lg) ? Number(lg) : null, yRefLabel: isN(lg) ? "League " + fmt(key, lg, sd) : null,
      aria: sd.label + " by player against " + (side === "hit" ? "plate appearances" : "innings")
        + ", " + pts.length + " players at or above the floor"
    }) : '<div class="mlbstats-note">Fewer than three players at or above the floor in this pool.</div>';
    var opts = defs.map(function (d) { return [d.key, d.label]; });
    return '<details class="mlbx-lgfold" data-gfold="players"' + (FOLD.players ? " open" : "") + ">"
      + "<summary>Players behind the averages</summary><div class=\"mlbx-lgfold-body\">"
      + '<div class="mlbstats-bar">' + selectCtl("mlbx-lg-stat", "statistic", "stat", opts, key) + "</div>"
      + '<div class="mlbx-lgchart">' + chart + "</div>"
      + '<div class="mlbstats-note">Each dot is one player at or above the floor; the dashed line is the pooled League value. Descriptive.</div>'
      + "</div></details>";
  }
  function teamTable(doc) {
    var st = ((((doc.groups || {}).team || {}).clubs || {}).stats) || {};
    var head = '<thead><tr><th scope="col">Statistic</th>'
      + '<th scope="col" class="mlbx-lgnum" title="Pooled over the clubs: summed numerators over summed denominators">League</th>'
      + '<th scope="col" class="mlbx-lgnum mlbstats-cv-wide">Club mean</th>'
      + '<th scope="col" class="mlbx-lgnum mlbstats-cv-wide">Median</th>'
      + '<th scope="col" class="mlbx-lgnum" title="Sample SD across the clubs">SD</th>'
      + '<th scope="col" class="mlbx-lgnum">Low</th><th scope="col" class="mlbx-lgnum">High</th></tr></thead>';
    var body = grouped(doc, "team").map(function (fam) {
      return '<tr class="mlbx-lggrp"><th scope="rowgroup" colspan="7">' + esc(fam[0]) + "</th></tr>"
        + fam[1].map(function (sd) {
          var c = st[sd.key] || {};
          function end(p) { return (p && p.length === 2) ? esc(p[0]) + " " + fmt(sd.key, p[1], sd) : DASH; }
          return '<tr><th scope="row" class="mlbx-lgstat" title="' + esc(sd.formula) + '">' + esc(sd.label) + "</th>"
            + '<td class="mlbx-lgnum mlbx-lgval">' + fmt(sd.key, c.league, sd) + "</td>"
            + '<td class="mlbx-lgnum mlbstats-cv-wide">' + fmt(sd.key, c.mean, sd) + "</td>"
            + '<td class="mlbx-lgnum mlbstats-cv-wide">' + fmt(sd.key, c.median, sd) + "</td>"
            + '<td class="mlbx-lgnum">' + fmtSpread(sd.key, c.sd, sd) + "</td>"
            + '<td class="mlbx-lgnum">' + end(c.low) + "</td><td class=\"mlbx-lgnum\">" + end(c.high) + "</td></tr>";
        }).join("");
    }).join("");
    return coverageHTML(doc, "team", {})
      + '<div class="mlbstats-scroll"><table class="mlbstats-table mlbx-lgtable">' + head + "<tbody>" + body + "</tbody></table></div>"
      + '<div class="mlbstats-note">The club statistics of the season, averaged across clubs. The Low and High columns name the club. Descriptive.</div>';
  }
  function avgView() {
    var y = seasonOf(), doc = PANELS[y];
    if (!doc) { loadPanel(y); doc = PANELS[y]; }
    if (doc === "loading") return sidePills(true) + CTX.pxState("loading", "Loading the " + esc(y) + " league panel.");
    if (doc === "error") {
      return sidePills(true) + CTX.pxState("failed", "The " + esc(y) + " league panel did not load. The nightly build may be writing it. "
        + '<button type="button" class="chip" data-gretry="panel">Retry</button>', "mlbstats-load-error");
    }
    return seasonNote(doc) + sidePills(true) + controls(doc)
      + (S.side === "team" ? teamTable(doc) : avgTable(doc)) + foldHTML(doc);
  }

  // ---- the Over time view ------------------------------------------------------
  function seasonsOf(sr) {
    return Object.keys(sr.seasons || {}).sort(function (a, b) { return a - b; });
  }
  function baseCell(side, stat) {
    if (side === "team") return "league";
    var dflt = side === "hit" ? "all" : "pitchers_only";
    if (stat === "sp_ip_per_gs") return "all";
    return dflt;
  }
  function cellLabel(sr, side, key) {
    if (side === "team") return key === "league" ? "League (pooled over clubs)" : "Club mean";
    var c = ((sr.cells || {})[side] || []).filter(function (x) { return x.key === key; })[0];
    if (c && key === "pos_other") return "Other positions";
    if (c && /^pos_/.test(key)) return "Position " + c.label;
    if (c) return c.label;
    return key === "pitchers_only" ? "Pitchers" : key;
  }
  function seriesPts(sr, side, cell, stat) {
    var ys = seasonsOf(sr), thin = num(sr.thin_cell_n), maxG = 0;
    ys.forEach(function (y) { maxG = Math.max(maxG, num(sr.seasons[y].games_per_team) || 0); });
    return ys.map(function (y) {
      var s = sr.seasons[y] || {}, blk = (s[side] || {})[cell] || null;
      var v = blk ? blk[stat] : null, hints = [];
      if (!s.complete) hints.push("season in progress" + (s.as_of ? ", through " + s.as_of : ""));
      var g = num(s.games_per_team);
      if (g != null && g < maxG) hints.push(g + " games per club");
      if (blk && isN(blk.n) && thin != null && side !== "team" && blk.n < thin) hints.push(blk.n + " players");
      return { y: y, v: isN(v) ? Number(v) : null, partial: hints.length > 0, hint: hints.length ? "(" + hints.join("; ") + ")" : "" };
    });
  }
  function realWidth(desk) {
    var host = CTX && CTX.host ? CTX.host() : null;
    var w = Number(host && host.clientWidth);
    if (!(w > 0)) return desk;
    return Math.max(280, Math.min(desk, Math.round(w - 24)));
  }
  function timeView() {
    if (!SERIES) {
      loadSeries();
      if (SERIES_STATE === "error") {
        return sidePills(true) + CTX.pxState("failed", "The over-time series did not load. The nightly build may be writing it. "
          + '<button type="button" class="chip" data-gretry="series">Retry</button>', "mlbstats-load-error");
      }
      if (!SERIES) return sidePills(true) + CTX.pxState("loading", "Loading the over-time series.");
    }
    var sr = SERIES, side = S.side, defs = ((sr.stats || {})[side] || []);
    var stat = statOf(side);
    if (!defs.some(function (d) { return d.key === stat; })) stat = defs.length ? defs[0].key : "";
    var sd = defs.filter(function (d) { return d.key === stat; })[0];
    if (!sd) return sidePills(true) + '<div class="mlbstats-empty">No statistic to chart for this side.</div>';
    var base = baseCell(side, stat);
    var cells = side === "team" ? [{ key: "club_mean", label: "Club mean" }]
      : ((sr.cells || {})[side] || []).filter(function (c) { return c.key !== base; });
    var cmp = S.cmp && cells.some(function (c) { return c.key === S.cmp; }) ? S.cmp : "";
    var f = function (v) { return fmt(stat, v, sd); };
    var series = [{ label: cellLabel(sr, side, base), color: "var(--viz-1)", pts: seriesPts(sr, side, base, stat) }];
    if (cmp) series.push({ label: cellLabel(sr, side, cmp), color: "var(--viz-2)", pts: seriesPts(sr, side, cmp, stat) });
    var ys = seasonsOf(sr), first = ys[0], last = ys[ys.length - 1];
    var hub = window.EEPHUS_HUB;
    // The real width of the chart box (up to the widest container), so a
    // 9-unit label prints near 9px at every width instead of scaling up.
    var W = realWidth(1320);
    var chart = (hub && hub.lineChart) ? hub.lineChart(series, {
      xs: ys, fmt: f, width: W, height: Math.round(Math.min(260, Math.max(200, W * 0.32))), every: 5,
      pl: 52, pr: 58, caption: "Numbers (" + ys.length + " seasons)",
      aria: sd.label + " by season, " + first + " to " + last + ", " + series.map(function (s) { return s.label; }).join(" and ")
    }) : "";
    if (!chart) chart = '<div class="mlbstats-empty">Fewer than two seasons carry this statistic.</div>';
    var legend = '<div class="mlbx-lglegend">' + series.map(function (s) {
      return '<span><i style="background:' + s.color + '"></i>' + esc(s.label) + "</span>";
    }).join("") + '<span><i class="is-hollow"></i>hollow: a short or unfinished season, or a thin group</span></div>';
    var smalls = defs.map(function (d) {
      var c = baseCell(side, d.key), pts = seriesPts(sr, side, c, d.key).filter(function (p) { return isN(p.v); });
      if (pts.length < 2 || !hub || !hub.spark) return "";
      var on = d.key === stat, lastP = pts[pts.length - 1];
      var sp = hub.spark(pts, { xs: ys, width: Math.max(150, Math.min(240, Math.round((realWidth(1320) - 30) / 6))), height: 46, last: true,
        aria: d.label + " by season, " + pts[0].y + " to " + lastP.y,
        tip: function (p) { return d.label + " " + p.y + ": " + fmt(d.key, p.v, d); } });
      return '<button type="button" class="mlbx-lgsmall' + (on ? " is-on" : "") + '" data-gpick="' + esc(d.key) + '" aria-pressed="' + on + '">'
        + '<span class="mlbx-lgsmall-h"><span>' + esc(d.label) + "</span><em>" + esc(fmt(d.key, lastP.v, d)) + "</em></span>" + sp + "</button>";
    }).join("");
    var cmpOpts = [["", "None"]].concat(cells.map(function (c) { return [c.key, cellLabel(sr, side, c.key)]; }));
    var thin = num(sr.thin_cell_n);
    return sidePills(true)
      + '<div class="mlbstats-bar">'
      + selectCtl("mlbx-lg-tstat", "statistic", "stat", defs.map(function (d) { return [d.key, d.label]; }), stat)
      + selectCtl("mlbx-lg-cmp", "compare", "cmp", cmpOpts, cmp)
      + "</div>"
      + '<div class="mlbx-lgchartwrap"><div class="mlbstats-viz-h">' + esc(sd.label) + " by season, league pooled</div>"
      + legend + chart + "</div>"
      + '<div class="mlbstats-viz-h">At a glance, ' + esc(first) + " to " + esc(last) + " (pick one to chart it)</div>"
      + '<div class="mlbx-lgsmalls">' + smalls + "</div>"
      + '<p class="mlbstats-note">Every season from the same MLB season lines, pooled the same way. Hollow points: a season'
      + " shorter than the longest in the span, the season in progress, and a group under " + esc(thin) + " players."
      + " " + esc(sd.label) + ": " + esc(sd.formula) + ". Descriptive: no trend line and no forecast.</p>";
  }

  // ---- render and events ---------------------------------------------------------
  var FOLD = { about: false, players: false };
  function subTabs() {
    return '<div class="mlbstats-tabs" role="tablist" aria-label="League views">'
      + [["avg", "Averages"], ["time", "Over time"]].map(function (t) {
          var on = S.view === t[0];
          return '<button type="button" class="mlbstats-tab' + (on ? " active" : "") + '" data-gview="' + t[0]
            + '" role="tab" aria-selected="' + on + '">' + t[1] + "</button>";
        }).join("") + "</div>";
  }
  function render() {
    if (!CTX) return;
    var host = CTX.host();
    if (!host) return;
    host.innerHTML = subTabs() + (S.view === "time" ? timeView() : avgView());
    if (CTX.wireGlossary) CTX.wireGlossary(host);
    if (CTX.markFit) CTX.markFit(host);
  }
  function changed() {
    if (CTX && CTX.writeHash) CTX.writeHash();
    render();
  }
  function onClick(e) {
    var t = e.target && e.target.closest ? e.target.closest("[data-gview],[data-gside],[data-gchip],[data-gpick],[data-gretry]") : null;
    if (!t) return;
    if (t.hasAttribute("data-gview")) { S.view = t.getAttribute("data-gview"); }
    else if (t.hasAttribute("data-gside")) { setSide(t.getAttribute("data-gside")); }
    else if (t.hasAttribute("data-gpick")) { S.stat = t.getAttribute("data-gpick"); }
    else if (t.hasAttribute("data-gretry")) {
      if (t.getAttribute("data-gretry") === "series") { SERIES_STATE = ""; SERIES = null; }
      else { delete PANELS[seasonOf()]; }
    } else {
      var p = String(t.getAttribute("data-gchip")).split(":"), arr = S[p[0]];
      if (!arr) return;
      if (!p[1]) S[p[0]] = arr.filter(function (x) { return x === "P" || x === "POS"; });
      else { var i = arr.indexOf(p[1]); if (i >= 0) arr.splice(i, 1); else arr.push(p[1]); }
    }
    changed();
  }
  function onChange(e) {
    var el = e.target;
    if (!el || !el.getAttribute) return;
    var k = el.getAttribute("data-gsel"), tg = el.getAttribute("data-gtoggle");
    if (k === "season") {
      var y = Number(el.value);
      S.season = (y && y !== liveSeason()) ? y : null;
    } else if (k === "qual") {
      S.qual = el.value === "custom" ? String(num(floorOf(PANELS[seasonOf()] || {})[S.side === "hit" ? "pa" : "ip"]) || 0) : el.value;
    } else if (k) {
      S[k] = el.value;
    } else if (tg) {
      var p = tg.split(":"), arr = S[p[0]], i = arr.indexOf(p[1]);
      if (el.checked && i < 0) arr.push(p[1]);
      if (!el.checked && i >= 0) arr.splice(i, 1);
    } else if (el.getAttribute("data-gmin")) {
      var v = String(el.value == null ? "" : el.value).trim();
      S.qual = /^\d{1,4}$/.test(v) ? v : "";
    } else return;
    changed();
  }
  function onToggle(e) {
    var d = e.target;
    if (!d || !d.getAttribute) return;
    var k = d.getAttribute("data-gfold");
    if (k) FOLD[k] = !!d.open;
  }
  var bound = null, started = false, resizeT = null, lastW = 0;
  function bind() {
    var host = CTX.host();
    if (!host || bound === host) return;
    bound = host;
    host.addEventListener("click", onClick);
    host.addEventListener("change", onChange);
    host.addEventListener("toggle", onToggle, true);
  }
  function show(ctx) {
    CTX = ctx;
    if (!started) {
      started = true;
      try { readHash(location.hash || ""); } catch (e) { /* no location */ }
      try {
        window.addEventListener("resize", function () {
          if (resizeT) clearTimeout(resizeT);
          resizeT = setTimeout(function () {
            var w = realWidth(1320);
            if (w !== lastW && CTX && CTX.active()) { lastW = w; render(); }
          }, 150);
        });
      } catch (e) { /* no window events */ }
    }
    bind();
    lastW = realWidth(1320);
    render();
  }

  // =============================================================================
  // The Teams tab (owner asks 15 and 20 of 2026-09-30; final-pass plan Part 8
  // P8.2, task LT-08, the Teams half; lane design league_team_stats section 5).
  // =============================================================================
  // One sortable table of the thirty clubs, read from the Team Stats payload
  // that team_stats_export.py writes (the same lazy script as League; the
  // landing board never asks for either). Views: Standard, EM+, Runs, Pitch
  // counts, Depth and Tendencies, each a column set in the COL_VIEWS manner.
  //
  // TWO CLUB BASES, both named (owner answer LTS-2): Earned is the default (each
  // player's season index weighted by what he did for each club), Club today is
  // the rollup the boards' team tabs serve, copied unchanged. A column that
  // exists on one basis only says so in its header. Past seasons are earned only.
  //
  // DESCRIPTIVE ONLY. Every number is copied, summed, re-weighted or MLB's own
  // expected record. RD, W - xW and every "vs lg" print signed in text ink and
  // never take a colour. The style z columns of the Tendencies view take no
  // value class at all (a frequency has no good direction). The two Runs
  // charts draw the identity line and a zero line, and no fitted line.
  //
  // HASH KEYS use the t prefix: tseason, tcols, tbasis, tsort. Only non-defaults
  // are written, through mlbstats.js writeHash, which asks teamHashParts().
  var TEAMS_FILE = "mlb_team_stats.json";
  var TVIEWS = [["standard", "Standard"], ["emplus", "EM+"], ["runs", "Runs"],
                ["pitch", "Pitch counts"], ["depth", "Depth"], ["tend", "Tendencies"]];
  var TBASES = [["earned", "Earned"], ["today", "Club today"]];
  var T_SORT0 = { key: "wl", asc: false };
  var T = { season: null, cols: "standard", basis: "earned", sort: null };
  var TRE = {
    season: /(?:^#|[#&])tseason=(\d{4})\b/, cols: /(?:^#|[#&])tcols=([a-z]+)\b/,
    basis: /(?:^#|[#&])tbasis=(earned|today)\b/, sort: /(?:^#|[#&])tsort=([a-z0-9_]+)\.(a|d)\b/
  };
  // The value ruler family of each EM+ column: the family the board that
  // serves it paints it with (mlbstats.js hemCell is ratio, remCell z, runCell
  // run), so a club reads the same colour here as on its board's team tab.
  // test_value_ruler.py pins the two files together. Nothing else on this
  // table takes a family: the deltas are signed text, team PAR has no better
  // direction, eWAR is a counting total, and a style z is a frequency.
  var TEAM_FAMILY = { offense_plus: "ratio", heart_hem: "ratio", rest_hem: "ratio",
                      rotation_plus: "z", front_sem: "run", bullpen_plus: "z",
                      high_lev_core_rem: "z", leverage_deploy_plus: "z", team_dem_plus: "z" };
  var MEAN_KEY = { offense_plus: "offense_plus_pa_weighted", rotation_plus: "rotation_plus_ip_weighted",
                   bullpen_plus: "bullpen_plus_ip_weighted", team_dem_plus: "team_dem_plus_inn_weighted" };

  // ---- columns ------------------------------------------------------------------
  // basis: "pick" follows the pill; "today" or "earned" is fixed (the header
  // names it when it differs from the pill); "" is a record, earned by nature.
  // live: the column exists only for the live season (past seasons carry the
  // earned basis and the records, nothing else).
  function bx(r, b) { return (b === "today" ? r.today : r.earned) || null; }
  function pct(a, b) { return (isN(a) && isN(b) && (a + b) > 0) ? a / (a + b) : null; }
  function pair(p) { return (p && p.length === 2) ? p : null; }
  var TCOL = {};
  function tdef(c) { TCOL[c.key] = c; }
  tdef({ key: "wl", label: "W-L", term: "season_record", kind: "rec", title: "Wins and losses, from the StatsAPI standings.",
         get: function (r) { return pct(r.w, r.l); }, show: function (r) { return isN(r.w) ? r.w + "-" + r.l : DASH; } });
  tdef({ key: "rd", label: "RD", kind: "signed", title: "Run differential: runs scored minus runs allowed.",
         get: function (r) { return r.rd; } });
  tdef({ key: "xwl", label: "xW-L", term: "xwl", kind: "rec", copy: "xwl",
         get: function (r) { return pct(r.xw, r.xl); }, show: function (r) { return isN(r.xw) ? r.xw + "-" + r.xl : DASH; } });
  tdef({ key: "wx", label: "W - xW", term: "w_minus_xw", kind: "signed", copy: "w_minus_xw", get: function (r) { return r.wx; } });
  tdef({ key: "rs", label: "RS", kind: "int", title: "Runs scored.", get: function (r) { return r.rs; } });
  tdef({ key: "ra", label: "RA", kind: "int", title: "Runs allowed.", get: function (r) { return r.ra; } });
  tdef({ key: "rs_g", label: "RS/G", kind: "d2", title: "Runs scored per game.", get: function (r) { return safeDiv(r.rs, r.g); } });
  tdef({ key: "ra_g", label: "RA/G", kind: "d2", title: "Runs allowed per game.", get: function (r) { return safeDiv(r.ra, r.g); } });
  tdef({ key: "one_run", label: "1-run", kind: "rec", live: true, title: "Record in games decided by one run (StatsAPI split records).",
         get: function (r) { var p = pair(r.one_run); return p ? pct(p[0], p[1]) : null; },
         show: function (r) { var p = pair(r.one_run); return p ? p[0] + "-" + p[1] : DASH; } });
  tdef({ key: "extra", label: "Extra inn", kind: "rec", live: true, title: "Record in extra-inning games (StatsAPI split records).",
         get: function (r) { var p = pair(r.extra); return p ? pct(p[0], p[1]) : null; },
         show: function (r) { var p = pair(r.extra); return p ? p[0] + "-" + p[1] : DASH; } });
  [["offense_plus", "Offense+"], ["rotation_plus", "Rotation+"], ["bullpen_plus", "Bullpen+"],
   ["team_dem_plus", "Team DEM+"]].forEach(function (p) {
    var k = p[0];
    tdef({ key: k, label: p[1], term: k, kind: "plus", basis: "pick",
           get: function (r, b) { var x = bx(r, b); return x ? x[k] : null; } });
    tdef({ key: k + "_vs", label: "vs lg", kind: "delta", basis: "pick", of: k,
           title: p[1] + " minus the league's own weighted mean of it on this basis, which the payload carries. Signed, not coloured.",
           get: function (r, b, M) {
             var x = bx(r, b), m = M ? M[MEAN_KEY[k]] : null;
             if (!x || !isN(m)) return null;
             var raw = isN(x[k + "_raw"]) ? x[k + "_raw"] : x[k];
             return isN(raw) ? Number(raw) - Number(m) : null;
           } });
  });
  [["heart_hem", "Heart 3", "Mean HEM+ of the club's top three qualified hitters by HEM+."],
   ["front_sem", "Front 3", "Mean SEM+ of the club's top three starters by SEM+."],
   ["high_lev_core_rem", "Hi-Lev Core", "Mean REM+ of the club's three relievers with the highest gmLI."],
   ["leverage_deploy_plus", "Lev Deploy+", "REM+ weighted by relief innings times gmLI, over the arms with a gmLI feed. Blank with no coverage."]
  ].forEach(function (p) {
    tdef({ key: p[0], label: p[1], term: p[0] === "leverage_deploy_plus" ? "leverage_deploy_plus" : "", kind: "plus",
           basis: "today", live: true, title: p[2],
           get: function (r) { return r.today ? r.today[p[0]] : null; } });
  });
  tdef({ key: "war_today", label: "eWAR today", term: "ewar", kind: "d1", live: true,
         title: "Team eWAR on the club-today basis, as the Overall board serves it: a traded player's season counts for the club that holds him now.",
         get: function (r) { return r.today ? r.today.war : null; } });
  tdef({ key: "war_earned", label: "eWAR earned", term: "ewar", kind: "d1", live: true,
         title: "eWAR produced for this club this season, by stint, as the Overall board serves it.",
         get: function (r) { return r.earned ? r.earned.war : null; } });
  // F-SCORE (owner ask B, 2026-09-30; plan 8.E, orchestrator ruling X13): ONE
  // column, the score, letter and rank team_stats_export copies verbatim from
  // the F-SCORE payload, on the live season only and only while the payload
  // carries that join (fscore.joined). The letter prints in neutral ink, the
  // score takes the z ladder, and the cell opens the club's F-SCORE section on
  // Franchises. No pillar and no per-season value joins the Teams tab.
  tdef({ key: "fscore", label: "F-SCORE", term: "franchise_score", kind: "fscore", live: true, fscore: true,
         title: "F-SCORE, copied from Franchises: 100 is the league average and 10 points one standard deviation. Descriptive, not a forecast.",
         get: function (r) { return r.fs ? r.fs.score : null; } });
  // Pitch counts: earned from MLB's club lines; the club-today columns read the
  // boards' own team keys when the boards serve them, and earned until then.
  [["p_pa", "Lineup P/PA", "p_per_pa", "lineup_p_pa", "d3", "Pitches seen per plate appearance, every plate appearance the club took."],
   ["lineup_par", "Lineup PAR", "lineup_par", "lineup_par", "int", "Team PAR of the lineup's P/PA: 100 is the mean of the thirty club rates."],
   ["p_ip", "Staff P/IP", "p_per_ip", "", "d2", "Pitches thrown per inning by the whole staff."],
   ["sp_p_ip", "Rotation P/IP", "sp_p_per_ip", "rot_p_ip", "d2", "Pitches per inning in starts, from MLB's starter split."],
   ["rotation_par", "Rotation PAR", "rotation_par", "rot_par", "int", "Team PAR of the rotation's P/IP: 100 is the mean of the thirty club rates."],
   ["rp_p_ip", "Bullpen P/IP", "rp_p_per_ip", "pen_p_ip", "d2", "Pitches per inning in relief, from MLB's reliever split."],
   ["bullpen_par", "Bullpen PAR", "bullpen_par", "pen_par", "int", "Team PAR of the bullpen's P/IP: 100 is the mean of the thirty club rates."],
   ["sp_ip_gs", "Rotation IP/GS", "sp_ip_per_gs", "", "d2", "Innings thrown in starts per start (the starter split), not the boards' IP/GS."],
   ["relief_share", "Relief IP %", "relief_ip_share", "", "pct", "The share of the club's innings thrown in relief."]
  ].forEach(function (p) {
    tdef({ key: p[0], label: p[1], kind: p[4], basis: "pitch", todayKey: p[3], title: p[5],
           term: p[0].indexOf("p_ip") >= 0 ? "pitches_per_ip" : (p[0] === "relief_share" ? "relief_ip_share" : ""),
           get: function (r, b) {
             if (b === "today" && p[3] && T_PIT_TODAY[p[3]]) return r.today ? r.today[p[3]] : null;
             return r.pit ? r.pit[p[2]] : null;
           } });
  });
  [["rest_hem", "Rest", "plus", "PA-weighted HEM+ of the club's hitters outside its top three."],
   ["gap", "Gap", "signed1", "Heart 3 minus Rest. Signed, not coloured."],
   ["pa100", "PA at 100+", "pct", "The share of the club's plate appearances taken by hitters at HEM+ 100 or better."]
  ].forEach(function (p) {
    var src = p[0] === "pa100" ? "pa_share_hem_100" : p[0];
    tdef({ key: p[0], label: p[1], term: "lineup_depth", kind: p[2], basis: "today", live: true, title: p[3],
           get: function (r) { return r.depth ? r.depth[src] : null; } });
  });
  // Depth's Heart 3 is the same served value as the EM+ view's; one column.
  tdef({ key: "hook", label: "Hook", kind: "d1", live: true, title: "Median pitch count at which the club pulled its starter.",
         get: function (r) { return r.tend && r.tend.style ? r.tend.style.hook_median_pitches : null; } });
  [["z_hook", "Hook z", "hook_z", " (negative = earlier)"], ["z_pen", "Pen z", "pen_z", ""],
   ["z_bench", "Bench z", "bench_z", ""], ["z_ibb", "IBB z", "ibb_z", ""], ["z_visit", "Visit z", "visit_z", ""]
  ].forEach(function (p) {
    tdef({ key: p[0], label: p[1], term: p[2], kind: "z", live: true,
           title: "Style, not skill: a signed z-score across the thirty clubs of the season" + p[3] + ". No colour: a frequency has no good direction.",
           get: function (r) { return r.tend && r.tend.style ? r.tend.style[p[0]] : null; } });
  });
  tdef({ key: "pen_g", label: "Pen/G", kind: "d2", live: true, title: "Pitching changes per game.",
         get: function (r) { return r.tend && r.tend.style ? r.tend.style.pen_per_game : null; } });
  tdef({ key: "sb_att", label: "SB att", kind: "int", live: true, title: "Stolen-base attempts: what the club chose to do.",
         get: function (r) { return r.tend && r.tend.running ? r.tend.running.attempts : null; } });
  tdef({ key: "sb_pct", label: "SB%", kind: "pct", live: true, title: "Share of stolen-base attempts that succeeded.",
         get: function (r) { return r.tend && r.tend.running ? r.tend.running.success_rate : null; } });
  tdef({ key: "to3b", label: "To 3B", kind: "pct", live: true, title: "Share of stolen-base attempts aimed at third base.",
         get: function (r) { return r.tend && r.tend.running ? r.tend.running.share_3B : null; } });

  // keys in view order ("|" opens a column group); phone: the club, W-L and
  // the view's two lead columns (lane design 5.1).
  var TVIEW_COLS = {
    standard: { keys: ["wl", "rd", "xwl", "wx", "|", "offense_plus", "rotation_plus", "bullpen_plus", "team_dem_plus",
                       "|", "war_today", "war_earned", "|", "fscore"], phone: ["wl", "rd", "xwl"] },
    emplus: { keys: ["wl", "|", "offense_plus", "offense_plus_vs", "heart_hem", "|", "rotation_plus", "rotation_plus_vs",
                     "front_sem", "|", "bullpen_plus", "bullpen_plus_vs", "high_lev_core_rem", "leverage_deploy_plus",
                     "|", "team_dem_plus", "team_dem_plus_vs"], phone: ["wl", "offense_plus", "offense_plus_vs"] },
    runs: { keys: ["wl", "|", "rs", "ra", "rd", "|", "rs_g", "ra_g", "|", "xwl", "wx", "|", "one_run", "extra"],
            phone: ["wl", "rs", "ra"] },
    pitch: { keys: ["wl", "|", "p_pa", "lineup_par", "|", "p_ip", "|", "sp_p_ip", "rotation_par", "sp_ip_gs", "|",
                    "rp_p_ip", "bullpen_par", "relief_share"], phone: ["wl", "p_pa", "lineup_par"] },
    depth: { keys: ["wl", "|", "heart_hem", "rest_hem", "gap", "pa100", "|", "front_sem", "|", "high_lev_core_rem"],
             phone: ["wl", "heart_hem", "rest_hem"] },
    tend: { keys: ["wl", "|", "hook", "z_hook", "z_pen", "pen_g", "|", "z_bench", "z_ibb", "z_visit", "|",
                   "sb_att", "sb_pct", "to3b"], phone: ["wl", "hook", "z_hook"] }
  };
  var T_PIT_TODAY = {};

  // ---- state and the hash ----------------------------------------------------------
  function viewOk(id) { return TVIEWS.some(function (v) { return v[0] === id; }); }
  function readTeamsHash(h) {
    h = h || "";
    var m;
    if ((m = TRE.season.exec(h))) T.season = Number(m[1]);
    if ((m = TRE.cols.exec(h)) && viewOk(m[1])) T.cols = m[1];
    if ((m = TRE.basis.exec(h))) T.basis = m[1];
    if ((m = TRE.sort.exec(h)) && (TCOL[m[1]] || m[1] === "club")) T.sort = { key: m[1], asc: m[2] === "a" };
  }
  function teamHashParts() {
    var p = [];
    if (T.season) p.push("tseason=" + T.season);
    if (T.cols !== "standard") p.push("tcols=" + T.cols);
    if (T.basis !== "earned") p.push("tbasis=" + T.basis);
    if (T.sort && !(T.sort.key === T_SORT0.key && !!T.sort.asc === !!T_SORT0.asc)) {
      p.push("tsort=" + T.sort.key + "." + (T.sort.asc ? "a" : "d"));
    }
    return p;
  }

  // ---- data ------------------------------------------------------------------------
  var TCTX = null, TDOC = null, TSTATE = "", TFOLD = { about: false, charts: false };
  function loadTeams() {
    if (TSTATE) return;
    TSTATE = "loading";
    getJSON(DATA_DIR + TEAMS_FILE, function (j) {
      TDOC = (j && j.teams && j.teams.length) ? j : null;
      TSTATE = TDOC ? "ok" : "error";
      if (TCTX && TCTX.active()) renderTeams();
    });
  }
  function tLive(doc) { return num(doc.season); }
  function tSeasons(doc) {
    var ys = [tLive(doc)];
    Object.keys(((doc.history || {}).seasons) || {}).forEach(function (y) { if (ys.indexOf(Number(y)) < 0) ys.push(Number(y)); });
    return ys.sort(function (a, b) { return b - a; });
  }
  function tSeason(doc) {
    var y = T.season;
    return (y && tSeasons(doc).indexOf(y) >= 0) ? y : tLive(doc);
  }
  // One row shape for the live season and for a history row, so every column
  // reads the same fields on either.
  function tRows(doc, y) {
    if (y === tLive(doc)) {
      return (doc.teams || []).map(function (t) {
        return { club: t.club, g: t.g, w: t.w, l: t.l, rs: t.rs, ra: t.ra, rd: t.rd, xw: t.xw, xl: t.xl,
                 wx: t.w_minus_xw, one_run: t.one_run, extra: t.extra_inning, today: t.roster || null,
                 earned: t.earned || null, pit: t.pitches || null, depth: t.depth || null, tend: t.tendencies || null,
                 fs: t.fscore || null };
      });
    }
    var h = doc.history || {}, s = ((h.seasons || {})[String(y)]) || null, cols = h.cols || [];
    if (!s) return [];
    return (s.rows || []).map(function (a) {
      var o = {};
      for (var i = 0; i < cols.length; i++) o[cols[i]] = a[i];
      var e = {};
      Object.keys(MEAN_KEY).forEach(function (k) { e[k] = o[k]; });
      return { club: o.club, g: o.g, w: o.w, l: o.l, rs: o.rs, ra: o.ra,
               rd: (isN(o.rs) && isN(o.ra)) ? o.rs - o.ra : null, xw: o.xw, xl: o.xl,
               wx: (isN(o.w) && isN(o.xw)) ? o.w - o.xw : null, one_run: null, extra: null, today: null,
               earned: e, pit: o, depth: null, tend: null, fs: null };
    });
  }
  function tMeans(doc, y, b) {
    if (y === tLive(doc)) {
      var lg = doc.league || {};
      return b === "today" ? ((lg.roster || {}).means || null) : ((lg.earned || {}).means || null);
    }
    var s = (((doc.history || {}).seasons || {})[String(y)]) || {};
    return (s.league || {}).earned || null;
  }
  function tFsOn() { return !!(TDOC && TDOC.fscore && TDOC.fscore.joined); }
  function tBasis(doc, y) { return (y === tLive(doc)) ? T.basis : "earned"; }
  function colBasis(c, b) {
    if (c.basis === "pick") return b;
    if (c.basis === "pitch") return (b === "today" && c.todayKey && T_PIT_TODAY[c.todayKey]) ? "today" : "earned";
    return c.basis || "";
  }
  function tPlan(live, id) {
    var v = TVIEW_COLS[id || T.cols] || TVIEW_COLS.standard, out = [], grp = false;
    v.keys.forEach(function (k) {
      if (k === "|") { grp = true; return; }
      var c = TCOL[k];
      if (!c || (c.live && !live) || (c.basis === "today" && !live) || (c.fscore && !tFsOn())) return;
      out.push({ c: c, grp: grp && out.length > 0, phone: v.phone.indexOf(k) >= 0 });
      grp = false;
    });
    return out;
  }

  // ---- cells --------------------------------------------------------------------------
  function fSign(v, nd) {
    if (!isN(v)) return DASH;
    var d = pyRound(Number(v), nd), s = Math.abs(d).toFixed(nd);
    return d > 0 ? "+" + s : d < 0 ? "-" + s : s;
  }
  function tShow(c, r, b, M) {
    if (c.show) return esc(c.show(r));
    var v = c.get(r, b, M);
    if (!isN(v)) return DASH;
    v = Number(v);
    switch (c.kind) {
      case "plus": {
        var fam = TEAM_FAMILY[c.key];
        var cls = (fam && window.EephusTiers) ? window.EephusTiers.cls(v, fam) : "";
        return '<span class="rem-plus' + (cls ? " " + cls : "") + '">' + Math.round(v) + "</span>";
      }
      case "fscore": {
        var fs = r.fs || {}, H = window.EEPHUS_HUB, href = "";
        try { href = H && H.clubHref ? H.clubHref(r.club) : ""; } catch (e) { href = ""; }
        var zc = window.EephusTiers ? window.EephusTiers.cls(v, "z") : "";
        var inner = '<span class="mlbx-fsletter">' + esc(fs.letter || DASH) + '</span> <span class="rem-plus' + (zc ? " " + zc : "") + '">'
          + v.toFixed(1) + "</span>";
        return href ? '<a class="club-link mlbx-fslink" href="' + esc(href + "&sec=fscore")
          + '" title="' + esc("F-SCORE rank " + (isN(fs.rank) ? fs.rank : DASH) + ": open the club's F-SCORE section") + '">' + inner + "</a>" : inner;
      }
      case "delta": case "signed1": case "z": return fSign(v, 1);
      case "signed": return fSign(v, 0);
      case "d1": return v.toFixed(1);
      case "d2": return v.toFixed(2);
      case "d3": return v.toFixed(3);
      case "pct": return (v * 100).toFixed(1) + "%";
      default: return String(Math.round(v));
    }
  }
  function clubCell(code) {
    var H = window.EEPHUS_HUB, c = null;
    try { c = H && H.club ? H.club(code) : null; } catch (e) { c = null; }
    if (!c) return '<td class="mlbstats-name"><span data-club-nolink="unresolved">' + esc(code) + "</span></td>";
    var mark = H.teamLogo ? H.teamLogo(c.code, null, { decorative: true }) : "";
    var href = H.clubHref ? H.clubHref(c.code) : "/franchise/#team=" + c.code;
    return '<td class="mlbstats-name"><a class="club-link mlbstats-name-link" href="' + esc(href)
      + '" data-club="' + esc(c.code) + '" title="' + esc(c.name + ": franchise overview") + '">'
      + mark + esc(c.code) + "</a></td>";
  }
  function tSortRows(rows, sort, b, M) {
    var c = sort.key === "club" ? null : TCOL[sort.key];
    return rows.slice().sort(function (x, y) {
      if (!c) return sort.asc ? String(x.club).localeCompare(y.club) : String(y.club).localeCompare(x.club);
      var a = c.get(x, b, M), d = c.get(y, b, M);
      var na = !isN(a), nd = !isN(d);
      if (na || nd) return (na && nd) ? String(x.club).localeCompare(y.club) : (na ? 1 : -1);
      if (a === d) return String(x.club).localeCompare(y.club);
      return sort.asc ? a - d : d - a;
    });
  }
  function tSort(plan) {
    var s = T.sort || T_SORT0;
    if (s.key === "club" || plan.some(function (p) { return p.c.key === s.key; })) return s;
    return T_SORT0;
  }
  function tTable(rows, plan, sort, b, M) {
    var head = '<thead><tr><th scope="col" class="mlbstats-col-club' + (sort.key === "club" ? " is-sorted" : "")
      + '" tabindex="0" aria-sort="' + (sort.key === "club" ? (sort.asc ? "ascending" : "descending") : "none")
      + '" data-col="club" data-tsort="club" data-export-text="Club">Club</th>';
    plan.forEach(function (p) {
      var c = p.c, cb = colBasis(c, b), on = c.key === sort.key;
      var tag = (cb && cb !== b) ? ' <span class="mlbx-tmtag">' + (cb === "today" ? "club today" : "earned") + "</span>" : "";
      var tip = c.copy ? ((TDOC.copy || {})[c.copy] || "") : (c.title || "");
      if (cb && cb !== b) tip += (tip ? " " : "") + (cb === "today" ? "Club-today basis on every pill." : "Earned basis on every pill.");
      var cls = "mlbstats-col-" + c.key + (on ? " is-sorted" : "") + (p.phone ? "" : " mlbstats-cv-wide") + (p.grp ? " mlbstats-cv-grp" : "");
      head += '<th scope="col" class="' + cls + '"' + (tip ? ' title="' + esc(tip) + '"' : "") + ' tabindex="0" aria-sort="'
        + (on ? (sort.asc ? "ascending" : "descending") : "none") + '" data-col="' + c.key + '" data-tsort="' + c.key
        + '" data-export-text="' + esc(c.label + (tag ? (cb === "today" ? " (club today)" : " (earned)") : "")) + '">'
        + (c.term ? '<span class="g-term" data-gl="' + esc(c.term) + '">' + esc(c.label) + "</span>" : esc(c.label))
        + tag + "</th>";
    });
    head += "</tr></thead>";
    var body = rows.map(function (r) {
      return "<tr>" + clubCell(r.club) + plan.map(function (p) {
        var cls = (p.phone ? "" : "mlbstats-cv-wide") + (p.grp ? (p.phone ? "" : " ") + "mlbstats-cv-grp" : "");
        var c = p.c, t = "";
        if (c.key === "leverage_deploy_plus" && r.today && isN(r.today.leverage_deploy_cov)) {
          t = ' title="' + esc("Covered share of relief innings: " + (Number(r.today.leverage_deploy_cov) * 100).toFixed(0) + "%") + '"';
        }
        return "<td" + (cls ? ' class="' + cls + '"' : "") + t + ">" + tShow(c, r, b, M) + "</td>";
      }).join("") + "</tr>";
    }).join("");
    return '<div class="mlbstats-scroll"><table class="mlbstats-table mlbx-tmtable">'
      + '<caption class="visually-hidden">Team stats, thirty clubs</caption>' + head + "<tbody>" + body + "</tbody></table></div>";
  }

  // ---- copy (every count, mean and date is read from the payload) ------------------
  function tFreshHTML(doc, y, n) {
    var bits = ["Season " + esc(y)];
    if (y === tLive(doc)) {
      var st = ((doc.as_of || {}).boards) || {}, last = "";
      Object.keys(st).forEach(function (k) { var a = (st[k] || {}).as_of; if (a && a > last) last = a; });
      if (last) bits.push("boards through " + esc(last));
    } else {
      bits.push("final");
    }
    bits.push(esc(n) + " clubs");
    return '<div class="mlbstats-note mlbstats-freshness">' + bits.join(" &middot; ") + "</div>";
  }
  function tMeansLine(doc, y, b) {
    var M = tMeans(doc, y, b);
    if (!M) return "";
    var names = { offense_plus: "Offense+", rotation_plus: "Rotation+", bullpen_plus: "Bullpen+", team_dem_plus: "Team DEM+" };
    var parts = Object.keys(MEAN_KEY).filter(function (k) { return isN(M[MEAN_KEY[k]]); }).map(function (k) {
      return names[k] + " " + fmtMean(M[MEAN_KEY[k]]);
    });
    return parts.length ? "League weighted means on this basis: " + parts.join(", ") + "." : "";
  }
  // One line under the controls: the club basis on the two views whose + columns
  // follow the pill, and the view's own reading on the other four (records,
  // pitch counts, depth and tendencies are not on the pill).
  function tBasisNote(doc, y, b) {
    var cp = doc.copy || {}, tc = cp.tendencies || {}, live = y === tLive(doc);
    var lead = "", s = "";
    if (T.cols === "emplus" || T.cols === "standard") {
      lead = "Basis:";
      s = (live ? (b === "today" ? cp.basis_roster : cp.basis_earned) : cp.past_seasons) + " " + tMeansLine(doc, y, b);
      var hs = (((doc.history || {}).seasons || {})[String(y)]) || null;
      if (hs && !hs.index_basis) s += " No EM+ index is built for this season, so its + columns are blank.";
    } else if (T.cols === "runs") {
      s = (cp.xwl || "") + " " + (cp.w_minus_xw || "");
    } else if (T.cols === "pitch") {
      s = cp.pitches || "";
    } else if (T.cols === "depth") {
      s = cp.depth || "";
    } else {
      s = tc.style_sentence || "";
    }
    return '<p class="mlbstats-note mlbx-tmbasis">' + (lead ? "<b>" + lead + "</b> " : "") + esc(s) + "</p>";
  }
  function tCoverageHTML(doc, y) {
    var cv = (doc.league || {}).coverage || {};
    if (y !== tLive(doc) || !isN(cv.offense_pa) || !isN(cv.league_pa)) return "";
    var line = "Scored exposure: Offense+ " + fmtCount(cv.offense_pa) + " of " + fmtCount(cv.league_pa)
      + " league PA; Rotation+ " + fmtCount(cv.rotation_ip) + " and Bullpen+ " + fmtCount(cv.bullpen_ip)
      + " of " + fmtCount(cv.league_ip) + " league IP. " + ((doc.copy || {}).coverage || "");
    return '<p class="mlbstats-note">' + esc(line) + "</p>";
  }
  function tFoldHTML(doc, y) {
    var cp = doc.copy || {}, tc = cp.tendencies || {};
    var keys = ["plus_scale", "basis_earned", "basis_roster", "past_seasons", "xwl", "w_minus_xw", "pitches", "depth"];
    var ps = keys.filter(function (k) { return cp[k]; }).map(function (k) { return "<p>" + esc(cp[k]) + "</p>"; }).join("");
    var tend = "";
    if (T.cols === "tend") {
      tend = [tc.style_sentence, tc.running_columns_are_style_not_skill, tc.agent_sentence]
        .filter(Boolean).map(function (s) { return "<p>" + esc(s) + "</p>"; }).join("")
        + (tc.why_no_plus_metric ? "<p>No plus metric for a club's decisions: " + esc(tc.why_no_plus_metric) + "</p>" : "")
        + '<p>Realized decision value, family by family, is on the <a href="/management/">In-Game Management</a> board.</p>';
    }
    return '<details class="mlbx-lgfold" data-tfold="about"' + (TFOLD.about ? " open" : "") + ">"
      + "<summary>" + esc(cp.lead || "") + "</summary><div class=\"mlbx-lgfold-body\">"
      + tend + ps + tCoverageHTML(doc, y) + "</div></details>";
  }
  function fmtMean(v) { return Number(v).toFixed(1); }
  function fmtCount(v) { return isN(v) ? String(Math.round(Number(v))).replace(/\B(?=(\d{3})+(?!\d))/g, ",") : DASH; }

  // ---- the Runs charts: earned basis, no fitted line -----------------------------------
  function tChartWidth() {
    var host = TCTX && TCTX.host ? TCTX.host() : null;
    var w = Number(host && host.clientWidth);
    if (!(w > 0)) return 600;
    var cell = w > 820 ? (w - 16) / 2 : w;
    return Math.max(260, Math.min(640, Math.round(cell - 26)));
  }
  function tCharts(rows, live) {
    var H = window.EEPHUS_HUB;
    if (!H || !H.scatter) return "";
    var W = tChartWidth(), Hh = Math.round(Math.min(280, Math.max(220, W * 0.6)));
    var a = rows.filter(function (r) { return isN(r.xw) && isN(r.w); }).map(function (r) {
      return { x: r.xw, y: r.w, r: 3, color: "var(--viz-1)", label: r.club + ": W " + r.w + ", xW " + r.xw };
    });
    var s1 = H.scatter(a, { width: W, height: Hh, xLabel: "expected wins (xW)", yLabel: "wins", diag: true,
      aria: "Wins against expected wins, " + a.length + " clubs, with the identity line" });
    var s2 = "";
    if (live) {
      var b2 = rows.filter(function (r) { return r.earned && isN(r.earned.war) && isN(r.rd); }).map(function (r) {
        return { x: r.earned.war, y: r.rd, r: 3, color: "var(--viz-1)",
                 label: r.club + ": eWAR earned " + Number(r.earned.war).toFixed(1) + ", RD " + fSign(r.rd, 0) };
      });
      s2 = H.scatter(b2, { width: W, height: Hh, xLabel: "eWAR earned", yLabel: "run differential", yRef: 0, yRefLabel: "0",
        aria: "Run differential against eWAR earned, " + b2.length + " clubs, with a zero line" });
    }
    if (!s1 && !s2) return "";
    return '<details class="mlbx-lgfold mlbx-tmcharts" data-tfold="charts"' + (TFOLD.charts ? " open" : "") + ">"
      + "<summary>Charts (earned basis)</summary><div class=\"mlbstats-viz\">"
      + (s1 ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Wins against expected wins</div>' + s1 + "</div>" : "")
      + (s2 ? '<div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">Run differential against eWAR earned</div>' + s2 + "</div>" : "")
      + "</div><p class=\"mlbstats-note\">One dot per club. The dashed lines are the identity line (wins equal to expected wins)"
      + " and zero run differential; no line is fitted. Every number is in the table above.</p></details>";
  }

  // ---- controls and render ---------------------------------------------------------------
  function tControls(doc, y) {
    var live = y === tLive(doc);
    var seasons = tSeasons(doc).map(function (s) {
      return '<option value="' + s + '"' + (s === y ? " selected" : "") + ">" + s + "</option>";
    }).join("");
    // inside the module's control bar, so the select takes the one control rule
    // (.mlbstats-bar select) every other board's select is drawn with
    var sel = '<div class="mlbstats-bar"><label class="mlbstats-ctl">season <select id="mlbx-tm-season" data-tsel="season">'
      + seasons + "</select></label></div>";
    var basis = '<div class="mlbstats-seasons mlbstats-roles" role="group" aria-label="Club basis"><span class="mlbstats-roles-lbl">Basis</span>'
      + TBASES.map(function (p) {
          var on = (live ? T.basis : "earned") === p[0], dis = !live && p[0] === "today";
          return '<button type="button" class="mlbstats-season' + (on ? " active" : "") + '" data-tbasis="' + p[0]
            + '" aria-pressed="' + on + '"' + (dis ? ' disabled aria-disabled="true" title="' + esc((doc.copy || {}).past_seasons || "") + '"' : "")
            + ">" + p[1] + "</button>";
        }).join("") + "</div>";
    var views = '<div class="mlbstats-seasons mlbstats-roles mlbstats-views" role="group" aria-label="Columns"><span class="mlbstats-roles-lbl">Columns</span>'
      // A view with nothing but W-L on this season (Depth and Tendencies on a
      // past season) offers no pill; a deep link to one prints the note.
      + TVIEWS.filter(function (v) { return v[0] === T.cols || tPlan(live, v[0]).length > 1; }).map(function (v) {
          var on = T.cols === v[0];
          return '<button type="button" class="mlbstats-season' + (on ? " active" : "") + '" data-colview="teams:' + v[0]
            + '" data-tcols="' + v[0] + '" aria-pressed="' + on + '">' + v[1] + "</button>";
        }).join("") + "</div>";
    var gfx = (window.EEPHUS_GFX && window.EEPHUS_GFX.chipHTML) ? window.EEPHUS_GFX.chipHTML("mlbx-teams-gfx", "Generate GFX") : "";
    return '<div class="mlbstats-toolrow">' + sel + basis + "</div>"
      + '<div class="mlbstats-toolrow">' + views + gfx + "</div>";
  }
  function tRulerKey(plan) {
    if (!plan.some(function (p) { return TEAM_FAMILY[p.c.key] && p.c.kind === "plus"; })) return "";
    var k = (window.EephusTiers && window.EephusTiers.keyHTML) ? window.EephusTiers.keyHTML({ neg: false }) : "";
    return '<div class="mlbx-tmkey"><span class="mlbstats-note"><span data-gl="value_ruler">Colour reads on the value ruler.</span></span>' + k + "</div>";
  }
  var T_LAST = { rows: [], basis: "earned", season: null, live: true };
  function teamsBody() {
    if (!TDOC) loadTeams();
    if (!TDOC) {
      if (TSTATE === "error") {
        return TCTX.pxState("failed", "The team stats did not load. The nightly build may be writing them. "
          + '<button type="button" class="chip" data-tretry="1">Retry</button>', "mlbstats-load-error");
      }
      return TCTX.pxState("loading", "Loading the team stats.");
    }
    var doc = TDOC, y = tSeason(doc), live = y === tLive(doc), b = tBasis(doc, y);
    T_PIT_TODAY = {};
    if (live) {
      (doc.teams || []).forEach(function (t) {
        var ro = t.roster || {};
        ["lineup_p_pa", "lineup_par", "rot_p_ip", "rot_par", "pen_p_ip", "pen_par"].forEach(function (k) {
          if (isN(ro[k])) T_PIT_TODAY[k] = true;
        });
      });
    }
    var rows = tRows(doc, y), M = tMeans(doc, y, b), plan = tPlan(live), sort = tSort(plan);
    rows = tSortRows(rows, sort, b, M);
    T_LAST = { rows: rows, basis: b, season: y, live: live };
    var table = plan.length > 1 ? tTable(rows, plan, sort, b, M)
      : '<div class="mlbstats-empty">This view is built for the live season only; pick ' + esc(tLive(doc)) + " to read it.</div>";
    return tFreshHTML(doc, y, rows.length) + tControls(doc, y) + tBasisNote(doc, y, b)
      + (plan.length > 1 ? tRulerKey(plan) : "") + table
      + (T.cols === "runs" && plan.length > 1 ? tCharts(rows, live) : "") + tFoldHTML(doc, y);
  }
  function renderTeams() {
    if (!TCTX) return;
    var host = TCTX.host();
    if (!host) return;
    host.innerHTML = teamsBody();
    if (TCTX.wireGlossary) TCTX.wireGlossary(host);
    if (TCTX.markFit) TCTX.markFit(host);
  }
  function teamsChanged() {
    if (TCTX && TCTX.writeHash) TCTX.writeHash();
    renderTeams();
  }
  function tGfxRows() {
    var b = T_LAST.basis;
    return T_LAST.rows.map(function (r) {
      var x = bx(r, b) || {};
      return { team: r.club, w: r.w, l: r.l, rd: r.rd, offense_plus: x.offense_plus, rotation_plus: x.rotation_plus,
               bullpen_plus: x.bullpen_plus, team_dem_plus: x.team_dem_plus };
    });
  }
  function onTeamsClick(e) {
    var t = e.target && e.target.closest ? e.target.closest("[data-tsort],[data-tcols],[data-tbasis],[data-tretry],#mlbx-teams-gfx") : null;
    if (t) teamsAct(t);
  }
  function teamsAct(t) {
    if (t.id === "mlbx-teams-gfx") {
      if (window.EEPHUS_GFX && TCTX && TCTX.gfxSpec) {
        var asOf = "", st = ((TDOC || {}).as_of || {}).boards || {};
        Object.keys(st).forEach(function (k) { var a = (st[k] || {}).as_of; if (a && a > asOf) asOf = a; });
        window.EEPHUS_GFX.open(TCTX.gfxSpec("teams", tGfxRows(), {
          season: T_LAST.season, as_of: T_LAST.live ? asOf : "",
          basis: T_LAST.basis === "today" ? "club today" : "earned" }));
      }
      return;
    }
    if (t.hasAttribute("data-tretry")) { TSTATE = ""; TDOC = null; }
    else if (t.hasAttribute("data-tcols")) { T.cols = t.getAttribute("data-tcols"); }
    else if (t.hasAttribute("data-tbasis")) { if (t.disabled) return; T.basis = t.getAttribute("data-tbasis"); }
    else {
      var k = t.getAttribute("data-tsort"), cur = T.sort || T_SORT0;
      T.sort = (cur.key === k) ? { key: k, asc: !cur.asc } : { key: k, asc: k === "club" };
    }
    teamsChanged();
  }
  function onTeamsKey(e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var t = e.target;
    if (!t || !t.getAttribute || !t.getAttribute("data-tsort")) return;
    if (e.preventDefault) e.preventDefault();
    var k = t.getAttribute("data-tsort");
    teamsAct(t);
    var host = TCTX && TCTX.host();
    var again = host && host.querySelector ? host.querySelector('th[data-tsort="' + k + '"]') : null;
    if (again && again.focus) again.focus();
  }
  function onTeamsChange(e) {
    var el = e.target;
    if (!el || !el.getAttribute || el.getAttribute("data-tsel") !== "season") return;
    var y = Number(el.value);
    T.season = (TDOC && y && y !== tLive(TDOC)) ? y : null;
    teamsChanged();
  }
  function onTeamsToggle(e) {
    var d = e.target;
    if (!d || !d.getAttribute) return;
    var k = d.getAttribute("data-tfold");
    if (k) TFOLD[k] = !!d.open;
  }
  var tBound = null, tStarted = false, tResize = null, tLastW = 0;
  function showTeams(ctx) {
    TCTX = ctx;
    if (!tStarted) {
      tStarted = true;
      try { readTeamsHash(location.hash || ""); } catch (e) { /* no location */ }
      try {
        window.addEventListener("resize", function () {
          if (tResize) clearTimeout(tResize);
          tResize = setTimeout(function () {
            var w = tChartWidth();
            if (w !== tLastW && TCTX && TCTX.active()) { tLastW = w; renderTeams(); }
          }, 150);
        });
      } catch (e) { /* no window events */ }
    }
    var host = TCTX.host();
    if (host && tBound !== host) {
      tBound = host;
      host.addEventListener("click", onTeamsClick);
      host.addEventListener("keydown", onTeamsKey);
      host.addEventListener("change", onTeamsChange);
      host.addEventListener("toggle", onTeamsToggle, true);
    }
    tLastW = tChartWidth();
    renderTeams();
  }

  window.MLBX_LEAGUE = {
    show: show, hashParts: hashParts, readHash: readHash, render: render,
    showTeams: showTeams, teamHashParts: teamHashParts, readTeamsHash: readTeamsHash,
    // test seams (test_mlbstats_league_page.py): the pooling and the group map
    _pool: function (doc, side, st) { return poolBlock(doc, side, rowsOf(doc, side).filter(function (r) { return passes(doc, side, r, st); })); },
    _groupKey: groupKey, _pyRound: pyRound, _state: function () { return JSON.parse(JSON.stringify(S)); },
    _writeHash: function () { if (CTX && CTX.writeHash) CTX.writeHash(); else if (TCTX && TCTX.writeHash) TCTX.writeHash(); },
    _reset: function () { S = { view: "avg", side: "hit", season: null, pos: [], role: [], hand: [], age: "", qual: "", lg: "", stat: "", cmp: "" }; },
    // the Teams seams: the rows in table order and a header or pill click
    _teamRows: function () { return T_LAST.rows.map(function (r) { return r.club; }); },
    _teamClick: function (attrs) {
      teamsAct({ id: "", disabled: false, hasAttribute: function (n) { return attrs[n] != null; },
                 getAttribute: function (n) { return attrs[n] != null ? attrs[n] : null; } });
    }
  };
  // A tab was opened before this file landed: mlbstats.js left its context.
  try {
    var want = window.MLBX_LEAGUE_CTX;
    if (typeof want === "function") {
      var c = want();
      if (c && c.active && c.active()) show(c);
    }
  } catch (e) { /* the next showSection calls show() */ }
  try {
    var wantT = window.MLBX_TEAMS_CTX;
    if (typeof wantT === "function") {
      var ct = wantT();
      if (ct && ct.active && ct.active()) showTeams(ct);
    }
  } catch (e) { /* the next showSection calls showTeams() */ }
})();
