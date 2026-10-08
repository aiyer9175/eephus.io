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

  window.MLBX_LEAGUE = {
    show: show, hashParts: hashParts, readHash: readHash, render: render,
    // test seams (test_mlbstats_league_page.py): the pooling and the group map
    _pool: function (doc, side, st) { return poolBlock(doc, side, rowsOf(doc, side).filter(function (r) { return passes(doc, side, r, st); })); },
    _groupKey: groupKey, _pyRound: pyRound, _state: function () { return JSON.parse(JSON.stringify(S)); },
    _writeHash: function () { if (CTX && CTX.writeHash) CTX.writeHash(); },
    _reset: function () { S = { view: "avg", side: "hit", season: null, pos: [], role: [], hand: [], age: "", qual: "", lg: "", stat: "", cmp: "" }; }
  };
  // The tab was opened before this file landed: mlbstats.js left its context.
  try {
    var want = window.MLBX_LEAGUE_CTX;
    if (typeof want === "function") {
      var c = want();
      if (c && c.active && c.active()) show(c);
    }
  } catch (e) { /* the next showSection calls show() */ }
})();
