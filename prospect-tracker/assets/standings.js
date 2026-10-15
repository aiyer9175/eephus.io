/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* /standings/ (STANDINGS_4, behind standings_core.STANDINGS_LIVE): a pure
   reader of the Scores job's standings files under /data/scores/standings/.

   SERVED NUMBERS ONLY. Every number prints as the job served it; the page
   joins, sorts and formats (rounding, signs, W-L joins, a served date written
   out) and makes the stale comparison, nothing else. STANDINGS_5: only when the
   mount root names the chart chunk (data-charts-src, standings_core.STANDINGS_CHARTS)
   the page adds the Charts view and a Race disclosure under each division table,
   and loads the chunk on the first of them. Seeds, how a club
   qualified, league records, RD/G, W - xW, games left and the projected record
   (two integers) are served by standings_core. A date written from a UTC
   stamp is Eastern and says so. Fetch: latest.json and index.json once per
   load and on becoming visible, then the season file; never the race or the
   odds history files (charts only), never a poll. The Playoffs view mounts
   the SCORES_4b bracket chunk unchanged with the season index's bracket.
   STANDINGS_6: Season and As of; ODDS only on the newest latest file.
   STANDINGS_7: the mount root's data-glmap names each header's glossary id
   (standings_core.HEADER_GLOSSARY) and each chart's (CHART_GLOSSARY); every
   header's abbr carries its id as data-gl and the chart chunk gets the map. */
(function () {
  "use strict";

  var BASE = "/data/scores/";
  var MS_S3 = 36 * 3600 * 1000;           // the Scores S3 rule (scores.js scoresStaleState)
  var MINE_KEY = "eephus.scores.mine";     // My teams, shared with /scores/
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"];
  var VIEWS = [["division", "Division"], ["wildcard", "Wild Card"], ["league", "League"], ["mlb", "MLB"],
    ["playoffs", "Playoffs"]];
  var GROUPS = [["splits", "Splits"], ["runs", "Runs"], ["odds", "Odds"], ["sched", "Schedule"]];
  var GLAB = { record: "Record", splits: "Splits", runs: "Runs", odds: "ODDS", sched: "Schedule" };
  var DIVS = [["ALE", "American League East"], ["ALC", "American League Central"], ["ALW", "American League West"],
    ["NLE", "National League East"], ["NLC", "National League Central"], ["NLW", "National League West"]];
  var LEAGUE = { AL: "American League", NL: "National League" };
  var MARK = { x: "clinched a playoff spot", y: "clinched the division", z: "clinched the league's best record",
    w: "clinched a wild card spot", e: "eliminated" };
  var CUT = { division: "the division lead", bye: "the bye line", wild_card: "the last wild card spot" };
  var RANK = { division: "div", wildcard: "wc", league: "lg", mlb: "mlb", playoffs: "div", seeds: "wc" };

  // ---- helpers
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isNum(x) { return typeof x === "number" && isFinite(x); }
  function width() { return window.innerWidth || 1280; }
  function store(key, val) {
    try {
      if (val === undefined) return window.localStorage.getItem(key);
      window.localStorage.setItem(key, val);
    } catch (e) { /* storage unavailable: the page works without it */ }
    return null;
  }
  function mine() {
    var v;
    try { v = JSON.parse(store(MINE_KEY) || "[]"); } catch (e) { v = []; }
    return Array.isArray(v) ? v : [];
  }
  function pair(p) { return Array.isArray(p) && p.length >= 2 ? p[0] + "-" + p[1] : "-"; }
  function signed(v, d) {
    if (!isNum(v)) return "-";
    var s = d ? v.toFixed(d) : String(v);
    if (Number(s) === 0) return d ? (0).toFixed(d) : "0";
    return (v > 0 ? "+" : "") + s;
  }
  function dot3(v) {
    if (!isNum(v)) return "-";
    var s = v.toFixed(3);
    return s.charAt(0) === "0" ? s.slice(1) : s;
  }
  // a served calendar date ("YYYY-MM-DD") written out; no zone is involved
  function ymd(ds, year) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(ds || ""));
    if (!m) return "";
    return MONTHS[+m[2] - 1] + " " + (+m[3]) + (year ? ", " + m[1] : "");
  }
  // a UTC stamp written as an Eastern date (or time), labelled (plan 4.7)
  function eastern(iso, time) {
    var t = Date.parse(iso || "");
    if (isNaN(t)) return "";
    var o = time ? { hour: "numeric", minute: "2-digit" } : { month: "long", day: "numeric" };
    o.timeZone = "America/New_York";
    try { return new Intl.DateTimeFormat("en-US", o).format(new Date(t)) + " (Eastern)"; } catch (e) { return ""; }
  }
  function lowerFirst(s) { return s.charAt(0).toLowerCase() + s.slice(1); }

  function hub() { return window.EEPHUS_HUB || null; }
  function clubOf(code) { var H = hub(); return H && H.club ? H.club(code) : null; }
  // the club's name without its city ("Rays", "Red Sox"), for the wide cell and the sentences
  function nick(code) {
    var c = clubOf(code);
    if (!c) return code;
    var w = c.name.split(" "), last = w[w.length - 1];
    return (last === "Sox" || last === "Jays") && w.length > 2 ? w.slice(-2).join(" ") : last;
  }
  function clubLink(code) {
    var H = hub();
    if (H && H.clubLinkHTML) return H.clubLinkHTML(code);
    var c = clubOf(code);
    return c && c.code ? '<a class="club-link" href="/franchise/#team=' + esc(c.code) + '">' + esc(c.code) + "</a>"
      : '<span data-club-nolink="unresolved">' + esc(code) + "</span>";
  }
  var sprite = null;
  function ico(key, size, cls) {
    if (sprite == null) {
      var u = document.querySelector('use[href*="/assets/eephus-icons.svg"]');
      sprite = u ? String(u.getAttribute("href")).split("#")[0] : "/assets/eephus-icons.svg";
    }
    var href = esc(sprite + "#i-" + key), c = ' class="ico' + (cls ? " " + cls : "") + '"';
    return size === 12
      ? "<svg" + c + ' width="12" height="12" viewBox="2 2 12 12" aria-hidden="true" focusable="false"><use href="' + href + '" width="16" height="16"/></svg>'
      : "<svg" + c + ' width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><use href="' + href + '"/></svg>';
  }
  function sr(t) { return '<span class="st-sr">' + esc(t) + "</span>"; }
  function stateHTML(kind, msg, cls) {
    var S = window.EephusState;
    if (S) return S.html(kind, msg, cls);
    return '<div class="px-state is-' + kind + '"' + (kind === "failed" ? ' role="alert"' : "") +
      '><div class="px-state-msg">' + msg + "</div></div>";
  }

  // ---- odds cells: the Franchise tile's pct(v, 1) with no "%" (the header carries it)
  function tint(v) {
    var T = window.EephusTiers, c = T && T.pctColor ? T.pctColor(v * 100) : "";
    return c ? "color:" + c : "";
  }
  function oddsCell(v, r) {
    if (r.e || !isNum(v)) return { s: "-", cls: "st-dim" };
    var s = (v * 100).toFixed(1);
    if (s === "0.0" && v > 0) return { s: "<0.1", cls: "st-dim", n: v };
    if (s === "100.0" && v < 1 && !r.mark) return { s: ">99.9", n: v, style: tint(v) };
    return { s: s, n: v, style: tint(v) };
  }

  // ---- columns. k: key (CSV and sort), g: group, a: header, t: full name,
  // d: the first press (best first), w: [phone, 768+, 1024+] px, v: the cell.
  function strkN(s) {
    var m = /^([WL])(\d+)$/.exec(String(s || ""));
    return m ? (m[1] === "W" ? 1 : -1) * +m[2] : null;
  }
  function num(k, g, a, t, d, w, key) {
    return { k: k, g: g, a: a, t: t, d: d, w: w, v: function (r) { return isNum(r[key]) ? { s: String(r[key]), n: r[key] } : { s: "-", cls: "st-dim" }; } };
  }
  function splitCol(k, a, t, key) {
    return { k: k, g: "splits", a: a, t: t, d: "desc", w: [56, 56, 56], v: function (r) {
      var p = key.charAt(0) === "_" ? r[key.slice(1)] : (r.split || {})[key];
      return { s: pair(p), n: Array.isArray(p) && p[0] + p[1] > 0 ? p[0] / (p[0] + p[1]) : null };
    } };
  }
  function oddsCol(k, a, t, key) {
    return { k: k, g: "odds", a: a, t: t, d: "desc", w: [50, 52, 52], v: function (r, x) {
      var c = x.ours && x.ours.clubs ? x.ours.clubs[r.code] : null;
      return oddsCell(c ? c[key] : null, r);
    } };
  }
  var SEED = { k: "seed", g: "record", a: "SEED", t: "Postseason seed", d: "asc", w: [40, 44, 44],
    v: function (r) { return isNum(r.seed) ? { s: String(r.seed), n: r.seed } : { s: "-", cls: "st-dim" }; } };
  function gbCol(view) {
    var wc = view === "wildcard";
    return { k: "gb", g: "record", a: wc ? "WCGB" : "GB", t: wc ? "Games back of the last wild card spot" : "Games back",
      d: "asc", w: [36, 44, 44], v: function (r) {
        if (wc) {
          if (!isNum(r.wcgb)) return { s: "-", cls: "st-dim" };
          if (r.wcgb === 0) return { s: "-", n: 0 };
          return { s: (r.wc_ahead ? "+" : "") + r.wcgb.toFixed(1), n: r.wc_ahead ? -r.wcgb : r.wcgb };
        }
        var v = r[view === "league" ? "lgb" : view === "mlb" ? "mlbgb" : "gb"];
        if (!isNum(v)) return { s: "-", cls: "st-dim" };
        return { s: v === 0 ? "-" : v.toFixed(1), n: v };
      } };
  }
  function projCell(r, x) {
    var c = x.ours && x.ours.clubs ? x.ours.clubs[r.code] : null, wl = r.w + "-" + r.l;
    if (!c) return { s: "-", cls: "st-dim" };
    if (c.proj_basis_ok === false) {
      return { s: "-", cls: "st-dim", title: isNum(c.proj_basis_w) && isNum(c.proj_basis_l)
        ? "Projection built on a W-L of " + c.proj_basis_w + "-" + c.proj_basis_l + "; this row is " + wl + "."
        : "The projection on file names no W-L; this row is " + wl + "." };
    }
    if (!isNum(c.proj_w_int) || !isNum(c.proj_l)) return { s: "-", cls: "st-dim" };
    var asof = eastern(x.ours.proj_made_at);
    return { s: c.proj_w_int + "-" + c.proj_l, n: c.proj_w_int,
      title: "Projected final record from the season simulator" + (asof ? ", as of " + asof : "") + "." +
        (isNum(c.proj_w) ? " Projected wins: " + c.proj_w.toFixed(1) + "." : "") };
  }
  function lamps(r) {
    var q = String(r.l10_seq || "");
    if (!/^[WL]{1,10}$/.test(q)) return "";
    var o = "";
    for (var i = 0; i < q.length; i++) o += '<i class="' + (q.charAt(i) === "W" ? "on" : "off") + '"></i>';
    return '<span class="st-lamps" aria-hidden="true">' + o + "</span>";
  }
  function columns(view, x) {
    var cols = view === "wildcard" ? [SEED] : [];
    cols.push(num("w", "record", "W", "Wins", "desc", [28, 34, 34], "w"), num("l", "record", "L", "Losses", "asc", [28, 34, 34], "l"),
      { k: "pct", g: "record", a: "PCT", t: "Winning percentage", d: "desc", w: [40, 46, 46], v: function (r) { return { s: dot3(r.pct), n: r.pct }; } },
      gbCol(view),
      { k: "l10", g: "record", a: "L10", t: "Last 10 games", d: "desc", w: [36, 88, 88], v: function (r) {
        return { h: lamps(r) + esc(pair(r.l10)), s: pair(r.l10), n: Array.isArray(r.l10) ? r.l10[0] : null };
      } },
      { k: "strk", g: "record", a: "STRK", t: "Streak", d: "desc", w: [40, 52, 52], v: function (r) {
        var n = strkN(r.streak);
        if (n == null) return { s: "-", cls: "st-dim" };
        var up = n > 0;
        return { h: ico(up ? "ev-up" : "ev-down", 12, up ? "st-up" : "st-down") + esc(r.streak) +
          sr((up ? "won " : "lost ") + Math.abs(n) + " in a row"), s: r.streak, n: n };
      } },
      { k: "rd", g: "record", a: "RD", t: "Run differential", d: "desc", w: [44, 46, 46], v: function (r) { return { s: signed(r.rd), n: r.rd }; } });
    var on = x.cols;
    if (on.indexOf("splits") >= 0) cols.push(
      splitCol("home", "HOME", "Home record", "home"), splitCol("away", "AWAY", "Road record", "away"),
      splitCol("div", "DIV", "Record against the division", "_vs_div"),
      splitCol("lg", "LG", "Record against the league", "_vs_lg"), splitCol("intr", "INTR", "Interleague record", "_intr"),
      splitCol("one", "1-RUN", "Record in one-run games", "one_run"), splitCol("xtra", "XTRA", "Record in extra-inning games", "extra"),
      splitCol("win", ">.500", "Record against clubs over .500", "winners"),
      splitCol("vsl", "vs L", "Record against left-handed starters", "vs_l"),
      splitCol("vsr", "vs R", "Record against right-handed starters", "vs_r"));
    if (on.indexOf("runs") >= 0) cols.push(
      num("rs", "runs", "RS", "Runs scored", "desc", [40, 42, 42], "rs"), num("ra", "runs", "RA", "Runs allowed", "asc", [40, 42, 42], "ra"),
      { k: "rdg", g: "runs", a: "RD/G", t: "Run differential per game", d: "desc", w: [50, 52, 52], v: function (r) {
        var s = signed(r.rdg, 2), T = window.EephusTiers;
        return { s: s, n: r.rdg, cls: r.gp >= 20 && T ? T.clsInk(r.rdg, "rdg") : "",
          title: "Run differential per game: " + s + ". Colour starts at 20 games." };
      } },
      { k: "xwl", g: "runs", a: "xW-L", t: "Expected record", d: "desc", w: [56, 58, 58], v: function (r) {
        return { s: pair(r.x_wl), n: Array.isArray(r.x_wl) ? r.x_wl[0] : null,
          title: "MLB's expected record from runs scored and allowed" + (isNum(r.x_exp) ? ": Pythagorean, exponent " + r.x_exp + "." : ".") };
      } },
      { k: "wxw", g: "runs", a: "W - xW", t: "Wins minus expected wins", d: "desc", w: [52, 54, 54], v: function (r) { return { s: signed(r.w_xw), n: r.w_xw }; } });
    if (on.indexOf("sched") >= 0) cols.push(
      num("left", "sched", "LEFT", "Games left", "asc", [40, 44, 44], "left"), num("magic", "sched", "MAGIC", "Magic number", "asc", [48, 52, 52], "magic"),
      { k: "elim", g: "sched", a: "ELIM", t: "Elimination number", d: "asc", w: [44, 48, 48], v: function (r) {
        var v = view === "division" || view === "playoffs" ? r.elim_div : r.elim_wc;
        if (isNum(v)) return { s: String(v), n: v };
        return v === "E" ? { s: "E", n: -1 } : { s: "-", cls: "st-dim" };
      } });
    if (on.indexOf("odds") >= 0 && x.ours) {
      var mods = x.ours.models || {}, want = x.model;
      if (mods.proj === want) cols.push({ k: "proj", g: "odds", a: "PROJ", t: "Projected final record", d: "desc", w: [56, 60, 60],
        v: function (r) { return projCell(r, x); } });
      [["pdiv", "DIV%", "Chance to win the division", "p_div"], ["ppost", "POST%", "Chance to reach the postseason", "p_post"],
        ["ppen", "PEN%", "Chance to win the pennant", "p_pennant"], ["pws", "WS%", "Chance to win the World Series", "p_ws"]
      ].forEach(function (o) { if (mods[o[3]] === want) cols.push(oddsCol(o[0], o[1], o[2], o[3])); });
      if (mods.sos === want) cols.push({ k: "sos", g: "odds", a: "SOS", t: "Strength of remaining schedule", d: "asc", w: [46, 48, 48],
        v: function (r) {
          var c = x.ours.clubs ? x.ours.clubs[r.code] : null, v = c ? c.sos : null;
          return isNum(v) ? { s: dot3(v), n: v, title: "Average talent rating of the opponents left to play, as a win rate from the season simulator's roster ratings, not their records. Rank 1 is the hardest." } : { s: "-", cls: "st-dim" };
        } });
    }
    return cols;
  }
  function colW(c) { var w = width(); return c.w[w >= 1024 ? 2 : w >= 768 ? 1 : 0]; }
  function clubW() { var w = width(); return w >= 1024 ? 190 : w >= 768 ? 116 : 100; }

  // ---- the app
  function boot(root) {
    var CH = root.getAttribute("data-charts-src"), VW = CH ? VIEWS.concat([["charts", "Charts"]]) : VIEWS;
    var GLM = { h: {}, c: {} };
    try { GLM = JSON.parse(root.getAttribute("data-glmap") || "") || GLM; } catch (e) { /* headers keep their titles */ }
    // tabindex -1: the sort button stays the one tab stop
    function glAttr(a) { var id = (GLM.h || {})[a]; return id ? ' tabindex="-1" data-gl="' + esc(id) + '"' : ""; }
    function glWire(el) { if (window.EEPHUS_GL && window.EEPHUS_GL.wire) window.EEPHUS_GL.wire(el || root); }
    var app = { route: parse(location.hash), L: null, IX: null, S: null, serverAt: null, clientAt: null,
      open: null, focus: null, bk: null, bkDoc: null, meta: {}, races: {}, seq: 0, miss: null };
    var St = window.EephusState;
    if (St) St.render(root, "loading", "Loading standings.");

    function parse(hash) {
      var q = {}, r = {};
      String(hash || "").replace(/^#/, "").split("&").forEach(function (kv) {
        var i = kv.indexOf("=");
        if (i > 0) try { q[decodeURIComponent(kv.slice(0, i))] = decodeURIComponent(kv.slice(i + 1)); } catch (e) { /* dropped */ }
      });
      if (VW.some(function (v) { return v[0] === q.view; })) r.view = q.view;
      if (/^(race|wc|odds|runs|xwl)$/.test(q.chart || "")) r.chart = q.chart;
      if (/^[AN]L[ECW]$/.test(q.div || "")) r.div = q.div;
      if (/^\d{4}$/.test(q.season || "")) r.season = +q.season;
      if (/^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(q.date || "")) r.date = q.date;
      if (q.cols != null) r.cols = String(q.cols).split(",").filter(function (c) {
        return GROUPS.some(function (g) { return g[0] === c; });
      });
      var m = /^([a-z0-9]+)\.(asc|desc)$/.exec(q.sort || "");
      if (m) r.sort = { k: m[1], dir: m[2] };
      if (/^[A-Z]{2,3}$/.test(q.team || "")) r.team = q.team;
      return r;
    }
    function hashOf(r) {
      var p = [];
      if (r.view) p.push("view=" + r.view);
      if (r.season) p.push("season=" + r.season);
      if (r.date) p.push("date=" + r.date);
      if (r.cols) p.push("cols=" + r.cols.join(","));
      if (r.sort) p.push("sort=" + r.sort.k + "." + r.sort.dir);
      if (r.team) p.push("team=" + r.team);
      if (r.chart) p.push("chart=" + r.chart);
      if (r.div) p.push("div=" + r.div);
      return p.length ? "#" + p.join("&") : "";
    }
    function go(r, rep) {
      var h = hashOf(r);
      app.route = r;
      if (h !== location.hash) {
        try { history[rep ? "replaceState" : "pushState"](null, "", h || location.pathname + location.search); } catch (e) { /* the view still renders */ }
      }
      if (!rep) sync();
    }
    function sync() { app.miss = null; choose().catch(fail); }
    function get(path) {
      return fetch(BASE + path, { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r;
      });
    }
    function load() {
      return get("latest.json").then(function (r) {
        var t = Date.parse((r.headers && r.headers.get("Date")) || "");
        app.serverAt = isNaN(t) ? null : t;
        app.clientAt = Date.now();
        return r.json();
      }).then(function (L) {
        if (!L || L.schema !== 1 || !L.standings) throw new Error("schema");
        app.L = L;
        return get("index.json?v=" + encodeURIComponent(L.index_rev || "")).then(function (r) { return r.json(); });
      }).then(function (IX) { app.IX = IX; return choose(); });
    }
    // season and date checked against the index; unknown values dropped
    function choose() {
      var ss = app.IX.standings_seasons || [], r = app.route, y = app.L.standings.season, e = null, n = ++app.seq;
      if (r.season && ss.some(function (s) { return s.season === r.season; })) y = r.season;
      else delete r.season;
      ss.forEach(function (s) { if (s.season === y) e = s; });
      if (!e) return Promise.reject(new Error("season"));
      if (r.date && !(e.by_date && +r.date.slice(0, 4) === y)) delete r.date;
      if (hashOf(r) !== location.hash) go(r, 1);
      var d = r.date, key = y + "|" + (d || e.rev);
      if (app.S && app.key === key) { app.entry = e; render(); return Promise.resolve(); }
      return get("standings/" + y + (d ? "/" + d + ".json" : ".json?v=" + encodeURIComponent(e.rev))).then(function (q) { return q.json(); })
        .then(function (S) {
          if (!S || S.schema !== 1 || S.season !== y || !Array.isArray(S.rows) || !S.rows.length || d && S.as_of !== d) throw new Error("schema");
          return S;
        }).then(function (S) {
          if (n !== app.seq) return;
          app.key = key; app.entry = e; app.S = S; render();
        }, function (err) {
          if (n !== app.seq) return;
          if (!d) throw err;
          delete r.date; app.miss = d; return choose();
        });
    }
    function fail() {
      if (St) St.render(root, "failed", 'Standings could not load. <button type="button" class="st-btn st-retry">Retry</button>');
      else root.textContent = "Standings could not load.";
    }
    function start() {
      load().catch(function () { if (!app.S) fail(); });
    }

    // ---- defaults that read the payload
    function oddsWin() { return !app.route.date && app.S.season === app.L.standings.season; }
    function ours() { return oddsWin() ? app.S.ours || null : null; }
    function view() { var O = ours(); return app.route.view || (O && O.phase === "postseason" ? "playoffs" : "division"); }
    function cols() {
      var c = app.route.cols, narrow = width() < 768;
      if (!c) c = narrow ? [] : (ours() ? ["runs", "odds"] : ["runs"]);
      if (!oddsWin()) c = c.filter(function (g) { return g !== "odds"; });
      return narrow ? c.slice(0, 1) : c;
    }
    function serverNow() { return app.serverAt == null ? Date.now() : app.serverAt + (Date.now() - app.clientAt); }
    function regFor(model) {
      var reg = app.S.registry || [];
      for (var i = 0; i < reg.length; i++) if (reg[i].model_id === model) return reg[i];
      return null;
    }
    // the labelled group line: source and verdict from the season file's registry block
    function oddsLabel(model) {
      var g = regFor(model), O = app.S.ours, src = (O.regular || {}).model_id === model ? O.regular : O.postseason;
      var asof = eastern((src || {}).generated_at);
      return '<p class="st-oddslab st-odds">ODDS &middot; Eephus model &middot; implied, no market &middot; ' +
        '<a class="st-chip" href="/models/#' + esc(model) + '">' + esc(((g && g.label) || model) + ", " + ((g && g.verdict) || "unvalidated")) +
        "</a>" + (asof ? " &middot; as of " + esc(asof) : "") + "</p>";
    }
    function rowsBy(fn) { return app.S.rows.filter(fn); }
    function cmpRank(key) {
      return function (a, b) {
        if (key === "wc") {
          var sa = isNum(a.seed) ? a.seed : 99, sb = isNum(b.seed) ? b.seed : 99;
          if (sa !== sb) return sa - sb;
        }
        var x = (a.ranks || {})[key], y = (b.ranks || {})[key];
        x = isNum(x) ? x : 99; y = isNum(y) ? y : 99;
        return x !== y ? x - y : (a.code < b.code ? -1 : a.code > b.code ? 1 : 0);
      };
    }

    // ---- the one table component: a shared <colgroup>, table-layout fixed
    function tableHTML(rows, cs, x, cap, cut) {
      var base = cmpRank(RANK[x.view]), sort = x.sort;
      rows = rows.slice().sort(base);
      var col = sort ? cs.filter(function (c) { return c.k === sort.k; })[0] : null;
      if (col) {
        var vals = {};
        rows.forEach(function (r) { var c = col.v(r, x); vals[r.code] = isNum(c.n) ? c.n : null; });
        rows.sort(function (a, b) {
          var va = vals[a.code], vb = vals[b.code];
          if (va == null || vb == null) return va == null && vb == null ? base(a, b) : va == null ? 1 : -1;
          if (va !== vb) return sort.dir === "asc" ? va - vb : vb - va;
          return base(a, b);
        });
      }
      if (x.mineOnly) rows = rows.filter(function (r) { return x.mine.indexOf(r.code) >= 0; });
      if (!rows.length) return "";
      var total = clubW(), cg = '<col class="st-c-club" style="width:' + total + 'px">', gh = '<th scope="col" class="st-g0"></th>', run = null, span = 0;
      function flush() {
        if (run) gh += '<th scope="colgroup" colspan="' + span + '" class="st-gh' + (run === "odds" ? " st-odds" : "") + '">' + GLAB[run] + "</th>";
      }
      cs.forEach(function (c) {
        var w = colW(c);
        total += w;
        cg += '<col class="st-c-' + c.k + '" style="width:' + w + 'px">';
        app.meta[c.k] = c;
        if (c.g !== run) { flush(); run = c.g; span = 0; }
        span++;
      });
      flush();
      var hh = '<th scope="col" class="st-club-h">Club</th>' + cs.map(function (c) {
        var on = col === c, as = on ? (sort.dir === "asc" ? "ascending" : "descending") : "none";
        return '<th scope="col" aria-sort="' + as + '" class="' + (c.g === "odds" ? "st-odds" : "") + (on ? " st-sorted" : "") + '">' +
          '<button type="button" class="st-sort" data-k="' + c.k + '"><abbr title="' + esc(c.t) + '"' + glAttr(c.a) + ">" + esc(c.a) + "</abbr>" +
          sr(", " + c.t) + '<span class="st-sort-ind" aria-hidden="true">' + (on ? (sort.dir === "asc" ? "▲" : "▼") : "") + "</span></button></th>";
      }).join("");
      var body = rows.map(function (r) {
        var follow = x.mine.indexOf(r.code) >= 0, open = app.open === r.code;
        var cells = cs.map(function (c) {
          var v = c.v(r, x);
          return '<td class="' + (c.g === "odds" ? "st-odds " : "") + (v.cls || "") + '"' + (v.style ? ' style="' + esc(v.style) + '"' : "") +
            (v.title ? ' title="' + esc(v.title) + '"' : "") + ">" + (v.h != null ? v.h : esc(v.s)) + "</td>";
        }).join("");
        var tr = '<tr data-code="' + esc(r.code) + '" class="' + (follow ? "st-mine " : "") + (x.team === r.code ? "st-hl " : "") +
          (open ? "st-isopen " : "") + (cut === r.code ? "st-cut" : "") + '">' + clubCell(r, follow, open, cut === r.code) + cells + "</tr>";
        if (open) tr += '<tr class="st-detail" id="st-d-' + esc(r.code) + '"><td colspan="' + (cs.length + 1) + '">' + detailHTML(r, x) + "</td></tr>";
        return tr;
      }).join("");
      return '<div class="st-tw"><div class="table-scroll-x st-frame"><table class="sp-agate st-table" style="width:' + total + 'px">' +
        "<caption>" + esc(cap) + "</caption><colgroup>" + cg + '</colgroup><thead><tr class="st-ghr">' + gh + "</tr><tr>" + hh +
        "</tr></thead><tbody>" + body + '</tbody></table></div><div class="st-shadow" aria-hidden="true"></div></div>';
    }
    function clubCell(r, follow, open, cut) {
      var m = r.mark || (r.e ? "e" : ""), wide = width() >= 1024, H = hub();
      return '<th scope="row" class="st-club"><span class="st-mk">' +
        (m ? ico(r.e ? "st-elim" : "st-clinch", 12, r.e ? "st-mk-e" : "st-mk-c") : "") + "</span>" +
        (wide && H && H.teamLogo ? H.teamLogo(r.code, "sp-logo st-logo", { decorative: true, size: 16 }) : "") +
        '<span class="st-code">' + clubLink(r.code) + "</span>" +
        (m ? '<sup class="st-letter"><abbr title="' + esc(MARK[m]) + '">' + m + "</abbr></sup>" + sr(MARK[m]) : "") +
        (wide ? '<span class="st-nick">' + esc(nick(r.code)) + "</span>" : "") +
        (follow ? sr("followed") : "") + (cut ? sr("Last wild card spot") : "") +
        '<button type="button" class="st-more" aria-expanded="' + open + '" aria-controls="st-d-' + esc(r.code) + '" data-code="' +
        esc(r.code) + '"><svg width="10" height="10" viewBox="0 0 5 5" aria-hidden="true" shape-rendering="crispEdges"><path d="' +
        (open ? "M2 1h1v1h-1zM1 2h3v1h-3zM0 3h5v1h-5z" : "M0 1h5v1h-5zM1 2h3v1h-3zM2 3h1v1h-1z") + '"/></svg>' + sr("Details, " + r.code) + "</button></th>";
    }
    function detailHTML(r, x) {
      var sp = r.split || {}, dl = [["Home", sp.home], ["Road", sp.away], ["Division", r.vs_div], ["League", r.vs_lg],
        ["Interleague", r.intr], ["One-run games", sp.one_run], ["Extra innings", sp.extra], ["Against clubs over .500", sp.winners],
        ["Against left-handed starters", sp.vs_l], ["Against right-handed starters", sp.vs_r], ["Day", sp.day], ["Night", sp.night]];
      var o = '<div class="st-dgrid"><dl class="st-dl"><dt>Record</dt><dd>' + esc(r.w + "-" + r.l + (r.t ? "-" + r.t : "")) + "</dd>" +
        dl.map(function (d) { return "<dt>" + esc(d[0]) + "</dt><dd>" + esc(pair(d[1])) + "</dd>"; }).join("") + "</dl><div>" +
        '<p class="st-l10">Last 10: ' + lamps(r) + " " + esc(pair(r.l10)) + "</p>";
      var mates = rowsBy(function (q) { return q.div === r.div; });
      var lead = mates.filter(function (q) { return (q.ranks || {}).div === 1; })[0], second = mates.filter(function (q) { return (q.ranks || {}).div === 2; })[0];
      if (isNum(r.magic) && second) o += "<p>Magic number " + r.magic + ": any combination of " + r.magic + " " + esc(nick(r.code)) +
        " wins and " + esc(nick(second.code)) + " losses clinches the division.</p>";
      if (isNum(r.elim_div) && lead && lead.code !== r.code) o += "<p>Elimination number " + r.elim_div + ": any combination of " +
        r.elim_div + " " + esc(nick(r.code)) + " losses and " + esc(nick(lead.code)) + " wins ends their division chances.</p>";
      var c = x.ours && x.ours.clubs ? x.ours.clubs[r.code] : null;
      if (c) {
        [["proj", "Projected final record"], ["p_div", "Division"], ["p_post", "Postseason"], ["p_pennant", "Pennant"], ["p_ws", "World Series"]].forEach(function (k) {
          var mid = (x.ours.models || {})[k[0]], g = regFor(mid);
          if (!mid || !g) return;
          var v = k[0] === "proj" ? projCell(r, x) : oddsCell(c[k[0]], r);
          o += '<p class="st-odds" data-model-id="' + esc(mid) + '">' + esc(g.label + ", " + g.verdict) + ": " + k[1] + " " +
            esc(v.s) + (k[0] === "proj" || v.s === "-" ? "" : "%") + "</p>";
        });
      }
      var follow = x.mine.indexOf(r.code) >= 0, H = hub(), fh = H && H.clubHref ? H.clubHref(r.code) : "";
      return o + '<p class="st-links">' + (fh ? '<a href="' + esc(fh) + '">Franchise</a>' : "") +
        '<a href="/projections/#view=teams">Team Outlook</a><a href="/scores/">Scores</a>' +
        '<button type="button" class="st-btn st-follow" data-code="' + esc(r.code) + '" aria-pressed="' + follow + '">' +
        (follow ? "Following " : "Follow ") + esc(r.code) + "</button></p></div></div>";
    }

    function controls(v, cs) {
      var S = app.S;
      return '<div class="st-ctl"><div class="st-row st-views" role="group" aria-label="Views">' + VW.map(function (w) {
        return '<button type="button" class="st-chip-btn" data-view="' + w[0] + '" aria-pressed="' + (w[0] === v) + '">' + w[1] + "</button>";
      }).join("") + '</div><div class="st-row st-groups" role="group" aria-label="Column groups">' +
        '<button type="button" class="st-chip-btn" aria-pressed="true" disabled>Record</button>' + GROUPS.filter(function (g) {
          return g[0] !== "odds" || oddsWin();
        }).map(function (g) {
          return '<button type="button" class="st-chip-btn" data-group="' + g[0] + '" aria-pressed="' + (cs.indexOf(g[0]) >= 0) + '">' + g[1] + "</button>";
        }).join("") + '<button type="button" class="st-chip-btn st-mine-btn" aria-pressed="' + !!app.route.mine + '">My teams</button>' +
        (app.route.sort ? '<button type="button" class="st-btn st-reset">Standings order</button>' : "") + "</div>" + seasonRow() + "</div>" +
        (S.format && S.format.notes && S.format.notes.length ? '<p class="st-fmt">' + esc(S.format.notes.join(" ")) + "</p>" : "");
    }
    function seasonRow() {
      var S = app.S, y = S.season, d = app.route.date || "", L = app.L.standings;
      var ss = (app.IX.standings_seasons || []).map(function (s) { return s.season; }).sort(function (a, b) { return b - a; });
      var mx = y === L.season ? L.as_of : S.as_of;
      return '<div class="st-row st-season"><label for="st-season">Season</label><select id="st-season">' + ss.map(function (s) {
        return '<option value="' + s + '"' + (s === y ? " selected" : "") + ">" + s + "</option>";
      }).join("") + "</select>" + ((app.entry || {}).by_date ? '<label for="st-date">As of</label><input type="date" id="st-date" value="' +
        esc(d) + '"' + (S.opening_day ? ' min="' + esc(S.opening_day) + '"' : "") + (mx ? ' max="' + esc(mx) + '"' : "") + ">" +
        (d ? '<button type="button" class="st-btn st-latest">Latest</button>' : "") : "") + "</div>";
    }
    function stamp() {
      var S = app.S, o, stale = "";
      if (app.route.date) o = "Standings as of " + ymd(S.as_of, true) + ".";
      else if (S.final) o = "Final standings, " + S.season + " regular season.";
      else {
        var up = eastern(S.generated_at, true);
        o = "Standings through " + ymd(S.as_of) + "." + (up ? " Updated " + up + "." : "");
        var gen = Date.parse((app.L || {}).generated_at || "");
        if (!isNaN(gen) && serverNow() - gen > MS_S3) {
          stale = '<p class="st-stale">Standings were last updated ' + esc(eastern(app.L.generated_at)) + ". They may be out of date.</p>";
        }
      }
      return '<div class="sp-dateline st-stamp"><span>' + esc(S.season) + ' standings</span><em role="status">' + esc(o) + "</em></div>" + stale;
    }
    function legend() {
      return '<p class="st-legend">' + ico("st-clinch", 16, "st-mk-c") + " x clinched a playoff spot &middot; y clinched the division &middot; " +
        "z clinched the league's best record &middot; w clinched a wild card spot &middot; " + ico("st-elim", 16, "st-mk-e") + " e eliminated</p>" +
        "<p class=\"st-legend\">Letters are MLB's; e is set when MLB's wild card elimination number reaches E, or when the season is over.</p>";
    }
    function notes(cs) {
      var S = app.S, o = "";
      if (S.opening_day && S.rows.every(function (r) { return !r.gp; })) {
        o += stateHTML("unmeasured", esc("The race starts on Opening Day, " + ymd(S.opening_day) + "."), "st-note st-race-note");
      }
      if (cs.indexOf("odds") >= 0 && !S.ours) {
        var from = (app.entry || {}).phist_from;
        (app.IX.standings_seasons || []).forEach(function (s) { if (!from && s.phist_from) from = s.phist_from; });
        o += stateHTML("unmeasured", esc(from ? "The daily odds record starts " + ymd(from, true) + "."
          : "The odds group has no record for this season."), "st-note st-odds-note");
      }
      if (app.entry && !app.entry.race_rev) {
        o += stateHTML("unmeasured", esc("Game-by-game results for " + S.season + " are not on file."), "st-note st-race-note");
      }
      if (app.miss) o += stateHTML("unmeasured", esc("No standings file for " + ymd(app.miss, true) + "."), "st-note st-miss");
      return o;
    }
    function credit() {
      var c = String(app.S.copyright || ""), i = c.search(/https?:\/\//), url = i >= 0 ? c.slice(i).split(/\s/)[0] : "";
      var text = url ? esc(c.slice(0, i)) + '<a href="' + esc(url) + '" rel="noopener">' + esc(url) + "</a>" + esc(c.slice(i + url.length)) : esc(c);
      return '<footer class="st-credit"><p>Standings, records and splits come from MLB\'s public StatsAPI feed. <span class="st-copy">' + text +
        "</span></p>" + (ours() ? "<p>Odds: the site's season and bracket simulators, implied, no market.</p>" : "") + "</footer>";
    }
    function tiesHTML() {
      var tb = app.S.tiebreak;
      if (!tb) return "";
      return '<details class="st-tie"><summary>How ties are broken</summary><p>' + esc(tb.text) + "</p>" + (tb.cut_ties || []).map(function (t) {
        var h = (t.h2h || []).map(function (q) { return q[0] + " " + pair(q[2]) + " against " + q[1]; }).join("; ");
        return "<p>Tied at " + esc(CUT[t.cut] || t.cut) + " (" + esc(t.lg) + "): " + esc((t.clubs || []).join(", ")) + "." +
          (h ? " Head to head: " + esc(h) + "." : "") + "</p>";
      }).join("") + "</details>";
    }

    function viewHTML(v, x) {
      var y = app.S.season, thru = app.S.final ? "final" : "through " + ymd(app.S.as_of), cs = columns(v, x), o = "";
      if (v === "division" || v === "playoffs") {
        var lg = null;
        DIVS.forEach(function (d) {
          var l = d[0].slice(0, 2);
          if (l !== lg) { lg = l; o += '<h3 class="sp-boxhead">' + LEAGUE[l] + "</h3>"; }
          o += tableHTML(rowsBy(function (r) { return r.div === d[0]; }), cs, x, d[1] + ", " + y + ", " + thru);
          if (CH && v === "division") o += '<details class="st-race" data-div="' + d[0] + '"' + (app.races[d[0]] ? " open" : "") +
            '><summary>Race</summary><div class="st-cm"></div></details>';
        });
      } else if (v === "wildcard") {
        ["AL", "NL"].forEach(function (l) {
          var rows = rowsBy(function (r) { return r.lg === l; });
          var cut = rows.filter(function (r) { return r.qualified === "wild_card" && isNum(r.seed); }).sort(function (a, b) { return b.seed - a.seed; })[0];
          o += '<h3 class="sp-boxhead">' + LEAGUE[l] + "</h3>";
          [["division", "Division leaders"], ["division_second", "Division second place"], [null, "Wild card"]].forEach(function (g) {
            var part = rows.filter(function (r) { return g[0] ? r.qualified === g[0] : r.qualified !== "division" && r.qualified !== "division_second"; });
            if (part.length) o += '<h4 class="st-sub">' + g[1] + "</h4>" +
              tableHTML(part, cs, x, LEAGUE[l] + ", " + lowerFirst(g[1]) + ", " + y + ", " + thru, cut ? cut.code : null);
          });
        });
      } else if (v === "league") {
        ["AL", "NL"].forEach(function (l) {
          o += '<h3 class="sp-boxhead">' + LEAGUE[l] + "</h3>" + tableHTML(rowsBy(function (r) { return r.lg === l; }), cs, x, LEAGUE[l] + ", " + y + ", " + thru);
        });
      } else {
        o += tableHTML(app.S.rows, cs, x, "Major League Baseball, " + y + ", " + thru);
      }
      return o;
    }
    // the Playoffs seeds tables: the served seed and how-qualified text, and
    // the bracket simulator's Pennant and World Series chances in their own labelled group
    function seedsHTML(x) {
      var O = x.ours, model = O && O.models && O.models.p_pennant === O.models.p_ws ? O.models.p_pennant : null;
      var xs = { view: "seeds", cols: [], sort: x.sort, mine: x.mine, mineOnly: x.mineOnly, team: x.team, ours: O, model: model };
      var cs = [SEED, { k: "wl", g: "record", a: "W-L", t: "Record", d: "desc", w: [56, 60, 60], v: function (r) { return { s: r.w + "-" + r.l, n: r.w }; } },
        { k: "how", g: "record", a: "HOW", t: "How qualified", d: "asc", w: [150, 170, 190], v: function (r) { return { s: r.qualified_text || "-", n: r.seed }; } }];
      if (model) cs.push(oddsCol("ppen", "PEN%", "Chance to win the pennant", "p_pennant"), oddsCol("pws", "WS%", "Chance to win the World Series", "p_ws"));
      var t = ["AL", "NL"].map(function (l) {
        return '<h3 class="sp-boxhead">' + LEAGUE[l] + " seeds</h3>" +
          tableHTML(rowsBy(function (r) { return r.lg === l && isNum(r.seed); }), cs, xs, LEAGUE[l] + " postseason seeds, " + app.S.season);
      }).join("");
      return '<div class="st-seeds">' + (model ? '<section class="st-mw" data-model-id="' + esc(model) + '">' + oddsLabel(model) + t + "</section>" : t) + "</div>";
    }

    function render() {
      if (!app.S) return;
      var v = view(), cs = cols(), O = ours();
      var x = { view: v, cols: cs, sort: app.route.sort || null, mine: mine(), mineOnly: !!app.route.mine, team: app.route.team,
        ours: O, model: O && O.regular ? O.regular.model_id : null };
      app.meta = {};
      var body = v === "charts" ? '<div class="st-cm st-charts"></div>' : viewHTML(v, x);
      if (O && cs.indexOf("odds") >= 0 && /<table/.test(body)) body = '<section class="st-mw" data-model-id="' + esc(x.model) + '">' + oddsLabel(x.model) + body + "</section>";
      if (v === "playoffs") body = seedsHTML(x) + (app.route.date ? "" : '<div class="st-bracket" id="st-bracket"></div>') + '<h3 class="st-final-h">' +
        (app.S.final ? "Final regular-season standings" : "Standings") + "</h3>" + body;
      if (x.mineOnly && v !== "charts" && !/<table/.test(body)) body = stateHTML("empty", "No followed clubs in this view. Follow a club from its row's details.", "st-note");
      if (v === "wildcard") body += tiesHTML();
      root.innerHTML = '<div class="st-wrap">' + controls(v, cs) + stamp() + legend() + notes(cs) + '<div class="st-body">' + body + "</div>" + credit() +
        '<p class="st-sr" role="status" aria-live="polite" id="st-announce"></p></div>';
      if (v === "playoffs" && !app.route.date) mountBracket();
      mountCharts(root.querySelectorAll(".st-charts, .st-race[open] .st-cm"));
      glWire(root);
      shadows();
      var f = app.focus;
      app.focus = null;
      if (f) {
        var b = root.querySelectorAll(f.sel)[f.i || 0] || root.querySelector(f.sel);
        if (b) b.focus();
        if (f.say) root.querySelector("#st-announce").textContent = f.say;
      }
      if (app.route.team && !app.scrolled) {
        var tr = root.querySelector('tr[data-code="' + app.route.team + '"]');
        if (tr && tr.scrollIntoView) { tr.scrollIntoView({ block: "center" }); app.scrolled = true; }
      }
    }
    function shadows() {
      Array.prototype.forEach.call(root.querySelectorAll(".st-tw"), function (tw) {
        var f = tw.firstChild;
        tw.lastChild.hidden = !(f.scrollWidth - f.clientWidth - f.scrollLeft > 1);
      });
    }
    function mountBracket() {
      var y = app.S.season, rev = null;
      (app.IX.seasons || []).forEach(function (s) { if (s.season === y) rev = s.rev; });
      if (!rev) return;
      var src = root.getAttribute("data-bracket-src");
      app.bk = app.bk || new Promise(function (ok, no) {
        if (window.EephusScoresBracket) return ok(window.EephusScoresBracket);
        var s = document.createElement("script");
        s.src = src;
        s.onload = function () { ok(window.EephusScoresBracket); };
        s.onerror = no;
        document.head.appendChild(s);
      });
      var doc = app.bkDoc && app.bkDoc.rev === rev ? Promise.resolve(app.bkDoc.doc)
        : get("index-" + y + ".json?v=" + encodeURIComponent(rev)).then(function (r) { return r.json(); })
          .then(function (d) { app.bkDoc = { rev: rev, doc: d }; return d; });
      Promise.all([app.bk, doc]).then(function (a) {
        var el = root.querySelector("#st-bracket");
        if (el && a[0] && a[0].mount) a[0].mount(el, (a[1] || {}).bracket || null);
      }).catch(function () { /* the seeds stand without the bracket */ });
    }

    // the lazy chart chunk: loaded once, on the first Race disclosure or the Charts view
    function mountCharts(els) {
      if (!els.length) return;
      Array.prototype.forEach.call(els, function (el) { el.innerHTML = stateHTML("loading", "Loading the race."); });
      app.ch = app.ch || new Promise(function (ok, no) {
        var s = document.createElement("script");
        s.src = CH;
        s.onload = function () { ok(window.EephusStandingsCharts); };
        s.onerror = no;
        document.head.appendChild(s);
      });
      app.ch.then(function (C) {
        Array.prototype.forEach.call(els, function (el) {
          if (root.contains(el)) C.mount(el, { S: app.S, entry: app.entry, get: get, mine: mine(), route: app.route,
            gl: GLM, wire: function () { glWire(el); },
            div: el.parentNode.getAttribute("data-div"), setRoute: function (k, val) {
              app.route[k] = val;
              try { history.replaceState(null, "", hashOf(app.route)); } catch (e) { /* the chart still redraws */ }
            } });
        });
      }, function () {
        Array.prototype.forEach.call(els, function (el) { el.innerHTML = stateHTML("failed", "The charts could not load."); });
      });
    }
    root.addEventListener("toggle", function (ev) {
      var d = ev.target, div = d.getAttribute && d.getAttribute("data-div");
      if (!div || !d.classList.contains("st-race") || !!app.races[div] === d.open) return;
      app.races[div] = d.open;
      if (d.open) mountCharts([d.querySelector(".st-cm")]);
    }, true);

    // ---- events
    root.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target.closest("button") : null;
      if (!t || !root.contains(t) || !app.S && !t.classList.contains("st-retry")) return;
      var r = Object.assign({}, app.route);
      if (t.classList.contains("st-retry")) { if (St) St.render(root, "loading", "Loading standings."); start(); return; }
      if (t.hasAttribute("data-view")) { r.view = t.getAttribute("data-view"); delete r.sort; app.open = null; app.focus = { sel: '[data-view="' + r.view + '"]' }; go(r); return; }
      if (t.hasAttribute("data-group")) {
        var g = t.getAttribute("data-group"), cur = cols(), on = cur.indexOf(g) >= 0;
        r.cols = width() < 768 ? (on ? [] : [g]) : (on ? cur.filter(function (c) { return c !== g; }) : cur.concat([g]));
        app.focus = { sel: '[data-group="' + g + '"]' };
        go(r); return;
      }
      if (t.classList.contains("st-mine-btn")) { r.mine = !r.mine; app.route = r; app.focus = { sel: ".st-mine-btn" }; render(); return; }
      if (t.classList.contains("st-latest")) { delete r.date; app.focus = { sel: "#st-date" }; go(r); return; }
      if (t.classList.contains("st-reset")) {
        delete r.sort;
        app.focus = { sel: '.st-views [aria-pressed="true"]', say: "Standings order restored." };
        go(r); return;
      }
      if (t.classList.contains("st-sort")) {
        var k = t.getAttribute("data-k"), col = app.meta[k];
        ev.stopPropagation();   // the redraw detaches the term under the tap
        if (!col) return;
        var i = Array.prototype.indexOf.call(root.querySelectorAll('.st-sort[data-k="' + k + '"]'), t);
        var dir = r.sort && r.sort.k === k ? (r.sort.dir === "asc" ? "desc" : "asc") : col.d;
        r.sort = { k: k, dir: dir };
        app.focus = { sel: '.st-sort[data-k="' + k + '"]', i: i, say: "Sorted by " + lowerFirst(col.t) + ", " + (dir === "desc" ? "highest first." : "lowest first.") };
        go(r); return;
      }
      if (t.classList.contains("st-more")) {
        var code = t.getAttribute("data-code");
        app.open = app.open === code ? null : code;
        app.focus = { sel: '.st-more[data-code="' + code + '"]' };
        render(); return;
      }
      if (t.classList.contains("st-follow")) {
        var c2 = t.getAttribute("data-code"), m = mine(), j = m.indexOf(c2);
        if (j >= 0) m.splice(j, 1); else m.push(c2);
        store(MINE_KEY, JSON.stringify(m));
        app.focus = { sel: '.st-follow[data-code="' + c2 + '"]' };
        render();
      }
    });
    root.addEventListener("scroll", function (ev) {
      var f = ev.target;
      if (f && f.classList && f.classList.contains("st-frame")) f.parentNode.lastChild.hidden = !(f.scrollWidth - f.clientWidth - f.scrollLeft > 1);
    }, true);
    root.addEventListener("change", function (ev) {
      var t = ev.target, r = Object.assign({}, app.route);
      if (!app.S || (t.id !== "st-season" && t.id !== "st-date")) return;
      if (t.id === "st-season") { r.season = +t.value; delete r.date; delete r.team; app.open = null; }
      else if (t.value) r.date = t.value;
      else delete r.date;
      app.focus = { sel: "#" + t.id };
      go(r);
    });
    window.addEventListener("popstate", function () { app.route = parse(location.hash); if (app.IX) sync(); });
    window.addEventListener("hashchange", function () { app.route = parse(location.hash); app.scrolled = false; if (app.IX) sync(); });
    var band = null;
    window.addEventListener("resize", function () {
      var w = width(), b = w >= 1024 ? 2 : w >= 768 ? 1 : 0;
      if (band == null) band = b;
      if (b !== band) { band = b; render(); } else shadows();
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible" && app.S) load().catch(function () { /* keep what is shown */ });
    });
    start();
  }

  window.EephusStandings = { ymd: ymd, eastern: eastern, oddsCell: oddsCell, signed: signed, staleMs: MS_S3 };
  function init() {
    var root = document.getElementById("standings-app-root");
    if (root) boot(root);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
