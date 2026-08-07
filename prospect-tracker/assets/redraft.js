// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026
//
// The Redraft sub-module of /fantasy/: daily streamers, two-start starters,
// ROS SP / RP / hitter boards, buy-low and sell-high, and the closer depth
// grid, all scored in the reader's league format.
//
// It was the whole of /redraft/ between 2026-08-05 and 2026-08-07 and that dir
// is a redirect stub now. Nothing about this client is page-shaped: it binds to
// its own ids, its own section vocabulary and its own half of the hash, which
// is what lets three of these share one document.
//
// ONE EXPORTER, THREE CLIENTS. data/fantasy.json is still built by
// fantasy_export.py on one corpus. assets/dynasty.js reads the two prospect
// sections out of it; this file reads the rest-of-season sections;
// assets/dfs.js reads its own daily slate payload.
//
// THE SCORING IS A PORT, NOT A REWRITE. scorePoints and rotoValue below are
// carried over unchanged from assets/fantasy.js, which in turn mirrors
// fantasy_scoring.py (the server is the authority; the weight tables ride in
// the payload). test_fantasy_split.py drives both files in a JS engine on one
// fixture and asserts the rendered scores match in all four formats, so a drift
// here fails the suite instead of quietly re-ranking somebody's league.
(function () {
  "use strict";
  var DATA_URL = "/data/fantasy.json";
  // streamerDay0 is the first slate this load actually served. It is not user
  // state; it exists so writeHash can tell "the reader picked a day" from "the
  // day the board opened on" and keep the default out of the URL.
  var S = { data: null, system: "fgp", section: "streamers", byId: {},
            streamerDay: null, streamerDay0: null, player: null };
  var SORT = {
    ros_hitter: { key: "score", asc: false },
    ros_sp: { key: "score", asc: false },
    ros_rp: { key: "score", asc: false }
  };
  var SORT_DEFAULTS = {};
  Object.keys(SORT).forEach(function (k) { SORT_DEFAULTS[k] = { key: SORT[k].key, asc: SORT[k].asc }; });
  var LINKS = null;
  // THE SECTIONS S.system CAN ACTUALLY MOVE, and the only ones the format bar
  // renders on. Every other tab is scored by the server on one fixed basis:
  // Daily Streamers and Two-Start ride per_start_fgp / total_fgp, Buy / Sell
  // sorts on the expected-stat gap, and the Closer Grid ranks on gmLI. The bar
  // used to sit above all seven, including the DEFAULT LANDING TAB, so the
  // first thing a reader met was a control that visibly did nothing to the
  // board under it, which is how a working selector got reported as broken.
  var SCORED_SECTIONS = { ros_sp: 1, ros_rp: 1, ros_hitter: 1 };
  function scoresHere() { return !!SCORED_SECTIONS[S.section]; }

  // ---- shell binding --------------------------------------------------------
  // Ids resolve through a candidate list ending at the pre-split shared id, so
  // this file still mounts on an older shell and an absent node is an
  // unrendered surface rather than an exception.
  //
  // THE COMBINED SHELL MUST NEVER EXPOSE THAT LAST CANDIDATE. All three
  // clients end their list at the same fantasy-era id, so a /fantasy/ shell
  // carrying it would hand one node to three clients and the last to paint
  // would win. build_site emits per-module ids only, and test_fantasy_split
  // pins that absence.
  function el(id) { return document.getElementById(id); }
  function pick() {
    for (var i = 0; i < arguments.length; i++) {
      var n = el(arguments[i]);
      if (n) return n;
    }
    return null;
  }
  function root() { return pick("redraft-app-root", "fantasy-app-root"); }
  function bannerEl() { return pick("redraft-banner", "fantasy-banner"); }
  function scoringBar() { return pick("redraft-scoring", "fantasy-scoring"); }
  function tabs() {
    var t = document.querySelectorAll(".mlbstats-sectionbtn[data-redraftsection]");
    if (t && t.length) return t;
    return document.querySelectorAll(".mlbstats-sectionbtn[data-fantasysection]");
  }
  function tabKey(b) {
    return b.getAttribute("data-redraftsection") || b.getAttribute("data-fantasysection");
  }

  // ---- host binding (the combined /fantasy/ page, 2026-08-07) ---------------
  // On /fantasy/ this file is ONE OF THREE clients in one document, so it owns
  // neither the address bar nor the corpus. assets/fantasy-hub.js hands it its
  // own half of the hash (the "#m=redraft" prefix is stripped on read and put
  // back on write), one memoized load of the 576KB data/fantasy.json that
  // assets/dynasty.js shares, and the module's activation. Three clients each
  // writing location.hash from their own state is three writers over one
  // string, which is the collision the namespace exists to prevent.
  //
  // With no host on the page every call below falls through to the plain
  // browser one. That is not dead code: test_fantasy_split drives this file in
  // a JS engine with no shell around it and compares its scores cell for cell
  // against the frozen assets/fantasy.js.
  var MODULE = "redraft";
  function host() { return window.EEPHUS_FANTASY_HOST || null; }
  function hostHash() { var H = host(); return H ? H.hash(MODULE) : (location.hash || ""); }
  function hostWrite(h) {
    var H = host();
    if (H) { H.write(MODULE, h); return; }
    try { history.replaceState(null, "", h); } catch (e) { /* the hash is a nicety */ }
  }
  function hostLink(h) { var H = host(); return H ? H.link(MODULE, h) : h; }
  function hostRoute(fn) {
    var H = host();
    if (H) H.onChange(MODULE, fn);
    else window.addEventListener("hashchange", fn);
  }
  function load(url) {
    var H = host();
    if (H) return H.json(url);
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  // ---- Diamond gate (wired, OFF) -------------------------------------------
  function dcfg() { return window.EEPHUS_DIAMOND || {}; }
  function isMember() {
    var c = dcfg();
    if (typeof c.isMember === "function") { try { return !!c.isMember(); } catch (e) { return false; } }
    return !!c.isMember;
  }
  function gated() { return !!dcfg().gating && !isMember(); }
  function capRows(rows) {
    if (!gated()) return rows;
    return (rows || []).slice(0, dcfg().previewRows || 25);
  }
  // The conversion line is a LINK. It was plain text on every Diamond page, so
  // the only route to the pricing page was the last item of a nav dropdown.
  function gateNote(total, shown) {
    if (!gated() || shown >= total) return "";
    return '<div class="rd-note">Diamond preview: showing the top ' + shown + " of " + total +
      ' rows. <a class="rd-name-link" href="/diamond/">Diamond funds the free site</a>.</div>';
  }

  // ---- record lookup --------------------------------------------------------
  // Keyed by mlbam AND side. A two-way player has TWO records, and keying on
  // mlbam alone is last-write-wins: "pit" is appended second, so it silently
  // clobbers the hitter row and puts a pitcher's points on the hitter board.
  function rec(mlbam, side) { return S.byId[mlbam + "|" + side]; }
  function recOf(entry, fallbackSide) {
    if (entry && typeof entry === "object") return rec(entry.mlbam, entry.side);
    return rec(entry, fallbackSide) || rec(entry, fallbackSide === "hit" ? "pit" : "hit");
  }

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function num(v, d) { return (v == null || isNaN(v)) ? "-" : Number(v).toFixed(d == null ? 1 : d); }
  // EVERY NAME OPENS THE IN-PAGE CARD, not the merged MLB page. The card is
  // assembled out of the payload already in this browser, so it works for every
  // row on the board rather than only the ones player_links can resolve, and it
  // carries the outbound "Full MLB card" link itself. The href is the FULL hash
  // (section, format, day and sorts included) so a card link that is copied out
  // of the page restores the board it was opened from.
  function nameLink(mlbam, name) {
    return '<a class="rd-name-link" href="' + esc(hashFor(mlbam)) + '">' + esc(name) + "</a>";
  }
  function teamLogo(team) {
    return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo && team) ? EEPHUS_HUB.teamLogo(team) : "";
  }

  // ---- scoring (mirrors fantasy_scoring.py; recomputed client side) ---------
  function scorePoints(ros, side) {
    if (!ros) return null;
    var sc = S.data.scoring || {};
    var w = side === "hit" ? sc.hitter : ((sc.pitcher || {})[S.system] || {});
    var t = 0;
    for (var k in w) if (ros[k] != null) t += ros[k] * w[k];
    return Math.round(t * 10) / 10;
  }
  var ROTO = {
    "5x5": { hit: ["avg", "hr", "rbi", "sb", "r"], pit: ["w", "sv", "era", "whip", "k"] },
    "4x4": { hit: ["obp", "slg", "hr", "r"], pit: ["era", "whip", "hr9", "k"] }
  };
  var RATE = { avg: 1, obp: 1, slg: 1, era: 1, whip: 1, hr9: 1 };
  var LOWER = { era: 1, whip: 1, hr9: 1 };
  function rotoValue(pool, side) {
    var cats = ROTO[S.system][side], ptk = side === "hit" ? "pa" : "ip";
    // PT-weighted pool mean for each rate cat.
    var means = {};
    cats.forEach(function (c) {
      if (!RATE[c]) return;
      var n = 0, d = 0;
      pool.forEach(function (p) { var r = p.ros || {}; n += (r[c] || 0) * (r[ptk] || 0); d += (r[ptk] || 0); });
      means[c] = d ? n / d : 0;
    });
    var raw = {}; cats.forEach(function (c) { raw[c] = []; });
    pool.forEach(function (p) {
      var r = p.ros || {};
      cats.forEach(function (c) {
        var v;
        if (RATE[c]) { var dev = (r[c] || 0) - means[c]; if (LOWER[c]) dev = -dev; v = dev * (r[ptk] || 0); }
        else v = r[c] || 0;
        raw[c].push(v);
      });
    });
    var z = {}; cats.forEach(function (c) {
      var xs = raw[c], mu = xs.reduce(function (a, b) { return a + b; }, 0) / (xs.length || 1);
      var sd = Math.sqrt(xs.reduce(function (a, b) { return a + (b - mu) * (b - mu); }, 0) / (xs.length || 1));
      z[c] = xs.map(function (x) { return sd ? (x - mu) / sd : 0; });
    });
    // Keyed by mlbam AND side, the same composite S.byId uses.
    var out = {};
    pool.forEach(function (p, i) {
      var t = 0;
      cats.forEach(function (c) { t += z[c][i]; });
      out[p.mlbam + "|" + p.side] = t;
    });
    return out;
  }
  function isRoto() { return S.system === "5x5" || S.system === "4x4"; }
  function scored(ids, side) {
    var pool = (ids || []).map(function (m) { return rec(m, side); }).filter(Boolean);
    if (isRoto()) {
      var rv = rotoValue(pool, side);
      return pool.map(function (p) { return { p: p, score: rv[p.mlbam + "|" + p.side] }; })
                 .sort(function (a, b) { return b.score - a.score; });
    }
    return pool.map(function (p) { return { p: p, score: scorePoints(p.ros, side) }; })
               .sort(function (a, b) { return (b.score || -1e9) - (a.score || -1e9); });
  }
  function scoreLabel() { return isRoto() ? "Value" : (S.system === "sabr" ? "SABR pts" : "FG pts"); }

  // ---- column maps ----------------------------------------------------------
  // ONE array per board drives the card cells, the aligned sort header, the tape
  // sort bar AND the comparator, so those four can never drift apart.
  function _ros(o, k) { var r = o.p.ros || {}; return r[k] == null ? null : r[k]; }
  function _sk(o, k) { var s = o.p.skill || {}; return s[k] == null ? null : s[k]; }
  function f0(v) { return num(v, 0); }
  function f2(v) { return num(v, 2); }
  function f3(v) { return num(v, 3); }
  function scoreFmt(v) { return num(v, isRoto() ? 2 : 0); }
  function rosIdentity(o) {
    var p = o.p;
    var sub = (p.elig && p.elig.length) ? p.elig.join("/") : (p.pos || "");
    return '<div class="rd-id ff-id"><span class="mlb-name">' + teamLogo(p.team) + " " + nameLink(p.mlbam, p.name) +
      '</span><span class="mlb-sub">' + esc(sub) + (p.team ? " &middot; " + esc(p.team) : "") + "</span></div>";
  }
  var SCORE_TITLE = "Rest-of-season value in the league format picked above. Points formats are the dot product of the projection and that format's weight table; roto formats are pooled category z-scores.";
  var HIT_COLS = [
    { key: "rank", label: "#", where: "head", track: "38px", kind: "rank",
      title: "Board position under the current sort" },
    { key: "name", label: "Player", where: "head", track: "minmax(0,1.7fr)", kind: "name", text: true, asc: true,
      title: "Sort by name", get: function (o) { return o.p.name; }, cell: rosIdentity },
    { key: "score", label: scoreLabel, where: "head", track: "94px", title: SCORE_TITLE,
      get: function (o) { return o.score; }, fmt: scoreFmt, strong: true },
    { key: "hem_plus", label: "HEM+", term: "hem_plus", where: "head", track: "76px",
      get: function (o) { return _sk(o, "hem_plus"); }, fmt: f0 },
    { key: "hr", label: "HR", where: "tape", get: function (o) { return _ros(o, "hr"); }, fmt: f0 },
    { key: "r", label: "R", where: "tape", get: function (o) { return _ros(o, "r"); }, fmt: f0 },
    { key: "rbi", label: "RBI", where: "tape", get: function (o) { return _ros(o, "rbi"); }, fmt: f0 },
    { key: "sb", label: "SB", where: "tape", get: function (o) { return _ros(o, "sb"); }, fmt: f0 },
    { key: "avg", label: "AVG", where: "tape", get: function (o) { return _ros(o, "avg"); }, fmt: f3 },
    { key: "obp", label: "OBP", where: "tape", get: function (o) { return _ros(o, "obp"); }, fmt: f3 }
  ];
  // SP and RP share every column but the skill index and the role counter, so
  // one factory emits both rather than two near-copies that drift apart.
  function pitCols(isRp) {
    return [
      { key: "rank", label: "#", where: "head", track: "38px", kind: "rank",
        title: "Board position under the current sort" },
      { key: "name", label: "Pitcher", where: "head", track: "minmax(0,1.7fr)", kind: "name", text: true, asc: true,
        title: "Sort by name", get: function (o) { return o.p.name; }, cell: rosIdentity },
      { key: "score", label: scoreLabel, where: "head", track: "94px", title: SCORE_TITLE,
        get: function (o) { return o.score; }, fmt: scoreFmt, strong: true },
      isRp
        ? { key: "rem_plus", label: "REM+", term: "rem_plus", where: "head", track: "76px",
            get: function (o) { return _sk(o, "rem_plus"); }, fmt: f0 }
        : { key: "sem_plus", label: "SEM+", term: "sem_plus", where: "head", track: "76px",
            get: function (o) { return _sk(o, "sem_plus"); }, fmt: f0 },
      { key: "ip", label: "IP", where: "tape", get: function (o) { return _ros(o, "ip"); }, fmt: f0 },
      { key: "k", label: "K", where: "tape", get: function (o) { return _ros(o, "k"); }, fmt: f0 },
      { key: "era", label: "ERA", where: "tape", asc: true, get: function (o) { return _ros(o, "era"); }, fmt: f2 },
      { key: "whip", label: "WHIP", where: "tape", asc: true, get: function (o) { return _ros(o, "whip"); }, fmt: f2 },
      isRp
        ? { key: "sv", label: "SV", where: "tape", get: function (o) { return _ros(o, "sv"); }, fmt: f0 }
        : { key: "qs", label: "QS", where: "tape", get: function (o) { return _ros(o, "qs"); }, fmt: f0 }
    ];
  }

  // ---- shared card machinery ------------------------------------------------
  function colByKey(cols, k) {
    var out = null;
    (cols || []).forEach(function (c) { if (c.key === k) out = c; });
    return out;
  }
  function headCols(cols) { return cols.filter(function (c) { return c.where === "head"; }); }
  function tapeCols(cols) { return cols.filter(function (c) { return c.where === "tape"; }); }
  function labelOf(c) { return typeof c.label === "function" ? c.label() : c.label; }
  function glossLbl(c) {
    var l = esc(labelOf(c));
    return c.term ? gl(labelOf(c), c.term) : l;
  }
  // The same span outside a column definition, for the table boards that are
  // hand-built rather than driven by a column array. Slugs are checked against
  // data/glossary.json first: a [data-gl] carrying a slug the artifact does not
  // have renders a term that looks interactive and defines nothing.
  function gl(label, slug) {
    return '<span class="g-term" data-gl="' + esc(slug) + '">' + esc(label) + "</span>";
  }
  // Missing values sort LAST in BOTH directions so a blank never wins a board.
  function sortRowsBy(rows, cols, st) {
    var col = colByKey(cols, st.key);
    if (!col || !col.get) return rows.slice();
    var out = rows.slice();
    out.sort(function (a, b) {
      var va = col.get(a), vb = col.get(b);
      if (col.text) {
        var sa = va == null ? "" : String(va), sb = vb == null ? "" : String(vb);
        if (!sa && !sb) return 0;
        if (!sa) return 1;
        if (!sb) return -1;
        return st.asc ? sa.localeCompare(sb) : sb.localeCompare(sa);
      }
      var na = (va == null || isNaN(va)) ? null : Number(va);
      var nb = (vb == null || isNaN(vb)) ? null : Number(vb);
      if (na == null && nb == null) return 0;
      if (na == null) return 1;
      if (nb == null) return -1;
      return st.asc ? na - nb : nb - na;
    });
    return out;
  }
  // A column with no get() cannot be compared, so it is NOT dressed as a
  // button. The "#" column used to be: it borrowed the score comparator, so
  // clicking it re-sorted the board into the order it was already in and moved
  // the sort arrow off Score onto a heading that is a display position, not a
  // field. A control whose first click does nothing is worse than no control.
  function sortBtn(c, st) {
    if (!c.get) return "<span>" + glossLbl(c) + "</span>";
    var on = st.key === c.key;
    return '<span role="button" tabindex="0" data-rdsort="' + esc(c.key) + '" aria-sort="' +
      (on ? (st.asc ? "ascending" : "descending") : "none") + '"' +
      (c.title ? ' title="' + esc(c.title) + '"' : "") + ">" + glossLbl(c) +
      (on ? (st.asc ? " ▴" : " ▾") : "") + "</span>";
  }
  function cellValue(c, row) {
    if (c.cell) return c.cell(row);
    var v = c.get ? c.get(row) : null;
    if (v == null) return "-";
    return c.fmt ? c.fmt(v) : esc(v);
  }
  // THE CARD CLASSES ARE THE SHARED ff- ONES, NOT rd- COPIES. assets/site.css
  // carries the whole board-card block (fixed 104px height with a matching
  // contain-intrinsic-size, the rotated rank diamond, the hover shadow, the
  // phone-swipeable sort bar, the phone header collapse) under .ff-card /
  // .ff-rank / .ff-sortbar, written for exactly these boards when they lived
  // at /fantasy/. The split renamed them to rd-* and dyn-*, which silently
  // dropped every one of those rules. Emitting the shared names is the fix,
  // and it is the fix rather than a local re-declaration because the
  // stylesheet already says so: one implementation, not two that drift.
  function cardCell(c, row, rk) {
    if (c.kind === "rank") return '<span class="ff-rank"><span class="ff-rank-i">' + esc(rk) + "</span></span>";
    if (c.kind === "name") return cellValue(c, row);
    return '<span class="mlb-metric' + (c.strong ? " ff-strong" : "") + '"><span class="mlb-metric-label">' +
      glossLbl(c) + "</span>" + cellValue(c, row) + "</span>";
  }
  // The stripe rides --org-color, the same custom property the PROSPX row and
  // the MLB cards use. This module has no org-colour source on the client, so
  // the stripe carries the board's own tier signal, in var() tokens only.
  function stripeFor(rk) {
    if (rk <= 10) return "var(--accent-gold)";
    if (rk <= 50) return "var(--accent-cyan)";
    return "var(--border)";
  }
  function renderCards(rows, cols, st, opts) {
    opts = opts || {};
    var hcols = headCols(cols), tcols = tapeCols(cols);
    var tracks = hcols.map(function (c) { return c.track; }).join(" ");
    var sorted = sortRowsBy(rows || [], cols, st);
    var total = sorted.length;
    sorted = capRows(sorted);
    var body = sorted.map(function (row, i) {
      var rk = opts.rankOf ? opts.rankOf(row, i) : (i + 1);
      var href = opts.hrefOf ? opts.hrefOf(row) : null;
      var chips = tcols.map(function (c) {
        return '<div class="mlb-chip"><b>' + esc(labelOf(c)) + "</b>" + cellValue(c, row) + "</div>";
      }).join("");
      return '<div class="mlb-card ff-card rd-card" style="--org-color:' +
        (opts.stripeOf ? opts.stripeOf(row, rk) : stripeFor(rk)) + ";grid-template-columns:" + tracks + '"' +
        (href ? ' tabindex="0" role="button" data-rdhref="' + esc(href) + '"' : "") + ">" +
        hcols.map(function (c) { return cardCell(c, row, rk); }).join("") +
        '<div class="mlb-tape"><div class="mlb-tape-inner">' + chips + "</div></div></div>";
    }).join("");
    if (!body) return '<div class="rd-note">' + esc(opts.empty || "No rows to show yet.") + "</div>";
    var head = '<div class="mlb-card-head ff-card-head rd-card-head" style="grid-template-columns:' + tracks + '">' +
      hcols.map(function (c) { return sortBtn(c, st); }).join("") + "</div>";
    var bar = tcols.length
      ? '<div class="ff-sortbar rd-sortbar"><span class="ff-sortbar-lbl">Sort by</span>' +
        tcols.map(function (c) { return sortBtn(c, st); }).join("") + "</div>"
      : "";
    return bar + head + '<div class="mlb-card-list ff-card-list rd-card-list">' + body + "</div>" +
      gateNote(total, sorted.length);
  }

  // ---- section renderers ----------------------------------------------------
  // ONE HITTER TABLE FOR BOTH POINTS FORMATS, and that is Ottoneu's rule rather
  // than a gap in ours: FanGraphs Points and SABR Points differ only in how
  // PITCHERS are scored, so fantasy.json carries a single scoring.hitter dict
  // and switching between those two cannot move this board. Said out loud here
  // because a control that visibly does nothing reads as a broken control.
  var HIT_FORMAT_NOTE =
    '<div class="rd-note">FanGraphs Points and SABR Points share one hitter table. The two formats ' +
    "differ only in how pitchers are scored, which is how Ottoneu runs them, so switching between " +
    "those two leaves this board exactly where it is. The two category formats do re-rank it.</div>";
  function boardHitter(ids) {
    return HIT_FORMAT_NOTE + renderCards(scored(ids, "hit"), HIT_COLS, SORT.ros_hitter, {
      hrefOf: function (o) { return hashFor(o.p.mlbam); },
      empty: "Rest-of-season hitter projections populate on the nightly build."
    });
  }
  function boardPitcher(ids, isRp) {
    return renderCards(scored(ids, "pit"), pitCols(isRp), isRp ? SORT.ros_rp : SORT.ros_sp, {
      hrefOf: function (o) { return hashFor(o.p.mlbam); },
      empty: "Rest-of-season pitcher projections populate on the nightly build."
    });
  }
  function streamerDayLabel(d) {
    // "2026-07-23" -> "Thu 7/23". Parse the parts locally: a bare ISO string
    // through new Date() is treated as UTC and can shift a day.
    var p = String(d || "").split("-");
    if (p.length !== 3) return esc(d);
    var dt = new Date(+p[0], +p[1] - 1, +p[2]);
    var wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dt.getDay()];
    return wd + " " + (+p[1]) + "/" + (+p[2]);
  }
  // STAYS A TABLE: one day slate at a time, roughly 26 rows. A 27-row table is
  // scannable in one screen; the same rows as cards are three screens.
  function tableStreamers(list) {
    var byDay = {}, days = [];
    (list || []).forEach(function (st) {
      var d = st.date || "";
      if (!byDay[d]) { byDay[d] = []; days.push(d); }
      byDay[d].push(st);
    });
    days.sort();
    if (!days.length) {
      return '<div class="rd-note">Probables are not posted for the streamer window yet. ' +
        "Check back once lineups firm up.</div>";
    }
    // A deep-linked #day= outside the served window is not an error state: it
    // snaps to the first slate, exactly as an empty S.streamerDay does.
    S.streamerDay0 = days[0];
    if (!S.streamerDay || days.indexOf(S.streamerDay) < 0) S.streamerDay = days[0];
    var pills = days.map(function (d) {
      var on = d === S.streamerDay;
      return '<button type="button" class="rd-daypill' + (on ? " active" : "") + '" data-streamerday="' + esc(d) +
        '" role="tab" aria-selected="' + (on ? "true" : "false") + '">' + streamerDayLabel(d) + "</button>";
    }).join("");
    // NO DATE COLUMN. The table only ever shows ONE day - the pill above it is
    // the day selector and the active pill already names the date - so a Date
    // cell repeated the same six characters down all 26 rows and cost a column
    // on a table that was already scrolling sideways on a phone.
    var rows = (byDay[S.streamerDay] || []).slice(0, 40).map(function (st, i) {
      var p = rec(st.mlbam, "pit") || {}, s = p.skill || {};   // probables are pitchers
      return '<tr><td class="mlbstats-col-rank">' + (i + 1) + '</td><td class="rd-nm">' +
        nameLink(st.mlbam, st.name) + " " + teamLogo(st.team) + "</td><td>@ " + esc(st.opp_org) +
        " (Off+ " + num(st.opp_off, 0) + ')</td><td class="rd-sc">' + num(st.per_start_fgp, 1) + "</td><td>" +
        (s.sem_plus != null ? num(s.sem_plus, 0) : "-") + "</td><td>" + esc(st.venue || "") + "</td></tr>";
    }).join("");
    return '<div class="rd-note">Every announced probable start over the next 3 days, ranked by matchup-adjusted ' +
      "expected points (a weaker opposing offense ranks higher). Pick a day below. Always scored in " +
      "FanGraphs Points: the league-format selector lives on the three rest-of-season tabs, because those " +
      "are the boards it can move.</div>" +
      '<div class="rd-daypills" role="tablist" aria-label="Streamer day">' + pills + "</div>" +
      '<div class="mlbstats-scroll rd-tablewrap"><table class="rd-table mlbstats-table">' +
      '<thead><tr><th class="mlbstats-col-rank">#</th><th class="rd-nm">Pitcher</th>' +
      "<th>Opponent</th><th>Exp pts</th>" +
      "<th>" + gl("SEM+", "sem_plus") + "</th><th>Park</th></tr></thead><tbody>" +
      rows + "</tbody></table></div>";
  }
  // STAYS A TABLE: the Matchups column is a free-text leg list that would fight
  // a fixed-height card box.
  function tableTwoStart(list) {
    if (!list || !list.length) {
      return '<div class="rd-note">No two-start pitchers detected or projectable in the current window yet. ' +
        "Check back once probables post for the scoring week.</div>";
    }
    var rows = list.slice(0, 60).map(function (t, i) {
      var legs = (t.legs || []).map(function (l) {
        var leg = "@" + esc(l.opp_org) + " (" + num(l.exp_fgp, 0) + ")";
        return l.projected ? '<span class="rd-proj">' + leg + " (proj)</span>" : leg;
      }).join(" · ");
      return '<tr><td class="mlbstats-col-rank">' + (i + 1) + '</td><td class="rd-nm">' + nameLink(t.mlbam, t.name) + " " +
        teamLogo(t.team) + "</td><td>" + esc(t.n_starts) + '</td><td class="rd-sc">' + num(t.total_fgp, 1) +
        "</td><td>" + legs + "</td></tr>";
    }).join("");
    return '<div class="rd-note">Pitchers lined up for two starts this scoring week. MLB posts probables only ' +
      "about 5 days out, so the second start is projected from the team schedule on normal rest and marked (proj) " +
      "until it is announced.</div>" +
      '<div class="mlbstats-scroll rd-tablewrap"><table class="rd-table mlbstats-table">' +
      '<thead><tr><th class="mlbstats-col-rank">#</th><th class="rd-nm">Pitcher</th>' +
      "<th>Starts</th><th>Total pts</th>" +
      "<th>Matchups</th></tr></thead><tbody>" + rows + "</tbody></table></div>";
  }
  // STAYS A TABLE: 30 and 30 rows in a deliberate side-by-side pair. Cards would
  // break the left-right comparison, which is the entire point of the surface.
  function renderBuySell() {
    function col(ids, label, cls, kind) {
      var rows = (ids || []).slice(0, 30).map(function (e) {
        var p = recOf(e, "hit"); if (!p) return "";
        var s = p.skill || {}, isHit = p.side === "hit", gap = isHit ? s.luck_gap : s.luck;
        // Mechanics-trend chip: display context only, baked server side from
        // per-season Swing+ when the latest-vs-prior move is 5 points or more.
        // Never part of the buy/sell ranking; the sort is luck only.
        var mt = p.swing_trend, chip = "";
        if (mt && mt.delta != null) {
          var md = (mt.delta > 0 ? "+" : "") + num(mt.delta, 0);
          chip = ' <span class="rd-mech ' + (mt.delta > 0 ? "rd-mech-up" : "rd-mech-down") +
            '" title="Mechanics trend: per-season Swing+ (Will Cahoon) moved ' + md + " from " +
            esc(mt.from) + " to " + esc(mt.to) + '. Context only, never part of this ranking.">mech trend ' +
            md + "</span>";
        }
        // TWO SCALES, TWO COLUMNS. Hitter luck_gap is xHEM+ minus HEM+, a
        // plus-stat delta whose pool spread is roughly +/-50; pitcher luck is
        // wOBA minus xwOBA, in wOBA points, spread roughly +/-0.05. They sit
        // about 500x apart (fantasy_export._buy_sell scales each side by its
        // own std before the combined sort for exactly that reason), and
        // stacking them under one "Luck gap" heading produced a column that
        // read +18, +0.041, +14, +0.038 down the page: non-monotonic, and
        // inviting a reader to compare a number to one 500 times its size.
        // Each row now fills the column for ITS scale and dashes the other, so
        // every column is internally comparable and the heading names its unit.
        var val = '<span class="rd-sc ' + cls + '">' + (gap > 0 ? "+" : "") +
          num(gap, isHit ? 0 : 3) + "</span>";
        var blank = '<span class="rd-dim">-</span>';
        return '<tr><td class="rd-nm">' + teamLogo(p.team) + " " + nameLink(p.mlbam, p.name) + chip + "</td><td>" +
          esc(p.pos || "") + "</td><td>" + (isHit ? val : blank) + "</td><td>" +
          (isHit ? blank : val) + "</td></tr>";
      }).join("");
      // AN EMPTY SIDE IS A SENTENCE, NOT A HEADER ROW OVER NOTHING. This was
      // the one surface on the page that fell through to a bare <tbody></tbody>:
      // on an empty payload the reader got "Buy-Low (unlucky)" and three column
      // headings above a blank strip. It also fires when the list IS served but
      // no id in it resolves to a player record, which reads the same way.
      if (!rows) {
        return '<div class="rd-half"><h3>' + label + "</h3>" +
          '<div class="rd-note">No ' + esc(kind) + " candidates in this build. The list comes " +
          "from the expected-stat gaps on the nightly run.</div></div>";
      }
      return '<div class="rd-half"><h3>' + label + '</h3>' +
        '<div class="mlbstats-scroll rd-tablewrap"><table class="rd-table mlbstats-table">' +
        '<thead><tr><th class="rd-nm">Player</th><th>Pos</th>' +
        '<th title="Hitters only: xHEM+ minus HEM+, in plus-stat points. Positive means unlucky.">Luck gap<br>' +
        gl("xHEM+", "xhem_plus") + " pts</th>" +
        '<th title="Pitchers only: wOBA minus xwOBA, in wOBA points. Positive means unlucky.">Luck gap<br>' +
        gl("wOBA", "woba") + " pts</th>" +
        "</tr></thead><tbody>" + rows + "</tbody></table></div></div>";
    }
    var sec = S.data.sections || {};
    return '<div class="rd-note">Regression candidates from our expected-stat gaps (hitters: ' +
      gl("xHEM+", "xhem_plus") + " against " + gl("HEM+", "hem_plus") + ", in plus-stat points; " +
      "pitchers: " + gl("xwOBA", "xwoba") + " against actual " + gl("wOBA", "woba") + ", in wOBA " +
      "points). The two scales sit about 500x apart, so they get a column each rather than one " +
      "column that mixes them. A positive gap means the player has been UNLUCKY and is due to " +
      "improve (buy); negative means he has been overperforming (sell). A mech trend chip flags a 5 point move in " +
      "per-season " + gl("Swing+", "swing_plus") + " (Will Cahoon), swing-mechanics context only, " +
      "never part of the ranking.</div>" +
      '<div class="rd-cols">' + col(sec.buy_low, "Buy-Low (unlucky)", "rd-pos", "buy-low") +
      col(sec.sell_high, "Sell-High (overperforming)", "rd-neg", "sell-high") + "</div>";
  }
  // ALREADY A CARD GRID: 30 team cards of 5 arms each.
  function renderClosers() {
    var depth = (S.data.sections || {}).closer_depth || {};
    var teams = Object.keys(depth).sort();
    if (!teams.length) {
      return '<div class="rd-note">The closer grid populates from the bullpen leaderboard on the nightly build.</div>';
    }
    var cards = teams.map(function (tm) {
      var lst = (depth[tm] || []).map(function (m, i) {
        var p = rec(m, "pit"); if (!p) return "";   // bullpen depth is pitchers
        var s = p.skill || {};
        var role = i === 0 ? '<span class="rd-closer">CLOSER</span>'
          : '<span class="rd-hc">' + (i === 1 ? "next" : "depth") + "</span>";
        return '<div class="rd-relief">' + role + " " + nameLink(p.mlbam, p.name) +
          ' <span class="rd-dim">gmLI ' + num(s.gmli, 2) + " · " + num(s.saves, 0) +
          "sv · REM+ " + num(s.rem_plus, 0) + "</span></div>";
      }).join("");
      // A team whose depth ids all miss the player index would otherwise render
      // as a logo over nothing. Say so instead.
      return '<div class="rd-team-card"><div class="rd-team-hd">' + teamLogo(tm) + " " + esc(tm) + "</div>" +
        (lst || '<div class="rd-relief rd-dim">No projectable arms in this build.</div>') + "</div>";
    }).join("");
    return '<div class="rd-note">Bullpen pecking order by average leverage (gmLI). The top arm is the likely ' +
      "closer, the rest are save handcuffs. Grab the next in line before the save chance opens.</div>" +
      '<div class="rd-grid">' + cards + "</div>";
  }

  function colsFor(section) {
    if (section === "ros_hitter") return HIT_COLS;
    if (section === "ros_sp") return pitCols(false);
    if (section === "ros_rp") return pitCols(true);
    return null;
  }

  // ---- share card -----------------------------------------------------------
  // PARITY WITH /dynasty/. The split gave the prospect half a Generate GFX chip
  // and left the rest-of-season half without one, so the same reader on the
  // same board machinery could share one page and not the other.
  //
  // The exported board follows the SECTION ON SCREEN (the cards.js rule), so
  // the graphic can never be a different board than the one the chip sits on.
  // Five sections export; Buy/Sell is a deliberate side-by-side PAIR and the
  // closer grid is a 30-card grid, and neither is a single ranked list, so
  // they get no chip rather than a graphic that misrepresents them.
  var GFX_SECTIONS = { streamers: 1, two_start: 1, ros_sp: 1, ros_rp: 1, ros_hitter: 1 };
  function gfxCell(c, row) {
    var v = c.get ? c.get(row) : null;
    if (v == null) return "-";
    return c.fmt ? c.fmt(v) : String(v);
  }
  function shareWrap(title, file, subtitle, columns, rows) {
    return {
      kind: "board", module: "Redraft", accentToken: "--accent-cyan",
      title: title, subtitle: subtitle,
      url: "eephus.io/redraft", filenameBase: file,
      caption: "Rest-of-season projections. A display ranking over served numbers.",
      board: { columns: columns, rows: rows, counts: [10, 25, 50] }
    };
  }
  function shareSpec() {
    var sec = (S.data && S.data.sections) || {};
    if (S.section === "streamers") {
      var byDay = {};
      (sec.daily_streamers || []).forEach(function (x) {
        (byDay[x.date || ""] = byDay[x.date || ""] || []).push(x);
      });
      var list = byDay[S.streamerDay] || [];
      return shareWrap("Daily Streamers",
        "eephus-redraft-streamers-" + (S.streamerDay || "day"),
        streamerDayLabel(S.streamerDay) + " · " + list.length +
          " announced starts · FanGraphs Points",
        [{ label: "#", frac: 0.07, align: "right" }, { label: "Pitcher", frac: 0.36 },
         { label: "Opp", frac: 0.16 }, { label: "Exp pts", frac: 0.15, align: "right" },
         { label: "SEM+", frac: 0.13, align: "right" },
         { label: "Park", frac: 0.13, wideOnly: true }],
        list.map(function (x, i) {
          var p = rec(x.mlbam, "pit") || {}, s = p.skill || {};
          return { cells: [{ t: i + 1 }, { t: x.name || "-", sub: x.team || undefined },
                           { t: "@ " + (x.opp_org || "-") },
                           { t: num(x.per_start_fgp, 1), c: "accent" },
                           { t: s.sem_plus == null ? "-" : num(s.sem_plus, 0) },
                           { t: x.venue || "-" }] };
        }));
    }
    if (S.section === "two_start") {
      var ts = sec.two_start || [];
      return shareWrap("Two-Start Starters", "eephus-redraft-two-start",
        ts.length + " pitchers lined up for two starts · FanGraphs Points",
        [{ label: "#", frac: 0.08, align: "right" }, { label: "Pitcher", frac: 0.46 },
         { label: "Starts", frac: 0.2, align: "right" },
         { label: "Total pts", frac: 0.26, align: "right" }],
        ts.map(function (t, i) {
          return { cells: [{ t: i + 1 }, { t: t.name || "-", sub: t.team || undefined },
                           { t: t.n_starts }, { t: num(t.total_fgp, 1), c: "accent" }] };
        }));
    }
    var cols = colsFor(S.section);
    if (!cols) return null;
    var side = S.section === "ros_hitter" ? "hit" : "pit";
    var rows = sortRowsBy(scored(sec[S.section] || [], side), cols, SORT[S.section]);
    var pick = cols.filter(function (c) {
      return c.key !== "rank" && c.key !== "name";
    }).slice(0, 4);
    var w = 0.56 / (pick.length || 1);
    var columns = [{ label: "#", frac: 0.07, align: "right" },
                   { label: side === "hit" ? "Player" : "Pitcher", frac: 0.37 }];
    pick.forEach(function (c) { columns.push({ label: labelOf(c), frac: w, align: "right" }); });
    var titles = { ros_sp: "Rest-of-Season Starters", ros_rp: "Rest-of-Season Relievers",
                   ros_hitter: "Rest-of-Season Hitters" };
    return shareWrap(titles[S.section] || "Rest-of-Season Board",
      "eephus-redraft-" + S.section,
      rows.length + " players · " + scoreLabel(),
      columns,
      rows.map(function (row, i) {
        var cells = [{ t: i + 1 },
                     { t: row.p.name || "-", sub: row.p.team || undefined }];
        pick.forEach(function (c, j) {
          cells.push({ t: gfxCell(c, row), c: j === 0 ? "accent" : undefined });
        });
        return { cells: cells };
      }));
  }
  function renderSection() {
    var sec = (S.data && S.data.sections) || {}, r = root();
    if (!r) return;
    var html;
    switch (S.section) {
      case "two_start": html = tableTwoStart(sec.two_start); break;
      case "ros_sp": html = boardPitcher(sec.ros_sp, false); break;
      case "ros_rp": html = boardPitcher(sec.ros_rp, true); break;
      case "ros_hitter": html = boardHitter(sec.ros_hitter); break;
      case "buysell": html = renderBuySell(); break;
      case "closers": html = renderClosers(); break;
      default: html = tableStreamers(sec.daily_streamers);
    }
    if (GFX_SECTIONS[S.section] && window.EEPHUS_GFX && EEPHUS_GFX.chipHTML) {
      html = '<div class="rd-tools">' + EEPHUS_GFX.chipHTML("rd-gfx", "Generate GFX") + "</div>" + html;
    }
    r.innerHTML = html;
    var gfx = r.querySelector("#rd-gfx");
    if (gfx) gfx.addEventListener("click", function () {
      var spec = shareSpec();
      if (spec && window.EEPHUS_GFX) EEPHUS_GFX.open(spec);
    });
    r.querySelectorAll(".rd-daypill").forEach(function (b) {
      b.addEventListener("click", function () {
        S.streamerDay = b.getAttribute("data-streamerday");
        renderSection();
        writeHash();
      });
    });
    // Sort headers plus the tape sort bar. Click AND Enter/Space, with focus
    // restored to the same control after the re-render replaces it. A repeat
    // click flips direction; a fresh column opens in ITS preferred direction,
    // so ERA and WHIP go low-first.
    r.querySelectorAll("[data-rdsort]").forEach(function (h) {
      function fire(refocus) {
        var st = SORT[S.section];
        if (!st) return;
        var k = h.getAttribute("data-rdsort"), c = colByKey(colsFor(S.section), k);
        if (st.key === k) st.asc = !st.asc;
        else { st.key = k; st.asc = !!(c && c.asc); }
        renderSection();
        writeHash();
        if (!refocus) return;
        var again = r.querySelector('[data-rdsort="' + k + '"]');
        if (again && again.focus) again.focus();
      }
      h.addEventListener("click", function () { fire(false); });
      h.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        fire(true);
      });
    });
    // Whole-card activation. The guard must EXCLUDE THE CARD ITSELF: the card
    // carries role="button", and closest() starts at the element it is called
    // on, so a naive closest("a,button,[role=button]") matched the card on
    // every click and shipped card activation as dead.
    r.querySelectorAll("[data-rdhref]").forEach(function (c) {
      function onCard(e) {
        var t = e.target.closest("a,button,[role=button]");
        return !t || t === c;
      }
      function open() { location.href = c.getAttribute("data-rdhref"); }
      c.addEventListener("click", function (e) { if (onCard(e)) open(); });
      c.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        if (!onCard(e)) return;
        e.preventDefault();
        open();
      });
    });
    if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(r);
  }

  // ---- scoring selector + section tabs --------------------------------------
  function renderSelector() {
    var bar = scoringBar(); if (!bar) return;
    // Emptied rather than hidden with a flag, so the :empty rule below is the
    // single place that decides what an unused bar looks like.
    if (!scoresHere()) { bar.innerHTML = ""; return; }
    var cat = (S.data && S.data.scoring_catalog) || [{ id: "fgp", label: "FanGraphs Points" }];
    var pts = cat.filter(function (c) { return c.kind !== "roto"; });
    var roto = cat.filter(function (c) { return c.kind === "roto"; });
    function btns(list) {
      return list.map(function (c) {
        return '<button type="button" class="rd-scorebtn' + (c.id === S.system ? " active" : "") +
          '" data-system="' + c.id + '">' + esc(c.label) + "</button>";
      }).join("");
    }
    bar.innerHTML = '<span class="rd-score-lbl">League scoring</span>' + btns(pts) +
      (roto.length ? '<span class="rd-score-sep">categories</span>' + btns(roto) : "");
    bar.querySelectorAll(".rd-scorebtn").forEach(function (b) {
      b.addEventListener("click", function () {
        S.system = b.getAttribute("data-system");
        renderSelector(); renderSection(); writeHash();
      });
    });
  }
  function syncTabs() {
    tabs().forEach(function (b) {
      var on = tabKey(b) === S.section;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  function wireTabs() {
    tabs().forEach(function (b) {
      b.addEventListener("click", function () {
        S.section = tabKey(b);
        syncTabs();
        // The format bar belongs to three of the seven tabs, so a tab change is
        // a bar change. Without this the bar kept whatever the previous section
        // left behind.
        renderSelector();
        renderSection();
        writeHash();
      });
    });
  }

  // ---- hash router ----------------------------------------------------------
  //   #section=streamers|two_start|ros_sp|ros_rp|ros_hitter|buysell|closers
  //   #sys=<scoring id>    any id the SERVED scoring_catalog carries
  //   #day=YYYY-MM-DD      the Daily Streamers slate
  //   #hsort= #spsort= #rpsort=   <column>.<a|d>, one per card board
  //   #player=<mlbam>      the fantasy player card, over whatever board is under it
  // section is always written; everything else only when it is off its default,
  // which keeps a shared URL short.
  //
  // THE CARD IS A HASH STATE, not a click handler, for three reasons: a card is
  // shareable, the browser Back button closes it because opening one is a real
  // history entry, and the board underneath keeps its own section, format, day
  // and sort in the same URL.
  var SECTIONS = ["streamers", "two_start", "ros_sp", "ros_rp", "ros_hitter", "buysell", "closers"];
  var LAST_HASH = null;
  function hashParam(h, key, pat) {
    var m = new RegExp("(?:^#|[#&])" + key + "=(" + pat + ")(?:&|$)").exec(h || "");
    return m ? m[1] : null;
  }
  // A sort is only honoured if the named column EXISTS on that board and can be
  // compared there. sortRowsBy needs exactly one thing from a column, a get(),
  // so that is the test.
  function readSort(h, key, board) {
    var v = hashParam(h, key, "[A-Za-z0-9_]+\\.[ad]");
    if (!v) return;
    var i = v.lastIndexOf("."), k = v.slice(0, i), c = colByKey(colsFor(board), k);
    if (!c || !c.get) return;
    SORT[board].key = k;
    SORT[board].asc = (v.slice(i + 1) === "a");
  }
  // EVERY CALLER REWRITES THE ADDRESS BAR AFTERWARDS. An invalid #section was
  // already refused by the alternation, so the page rendered the default - but
  // the address bar used to keep the bad value until the reader happened to
  // click a tab, so a shared link named a section that does not exist and the
  // page disagreed with its own URL. This used to return a "was it canonical"
  // flag; now that the hash also carries a card, there are more ways to be off
  // canonical than that flag could name, so the callers normalize every time.
  function readHash() {
    var h = hostHash();
    var s = hashParam(h, "section", SECTIONS.join("|"));
    if (s) S.section = s;
    // Validated against the SERVED catalog rather than a literal list, so a
    // format added to or dropped from fantasy_scoring.SCORING_CATALOG needs no
    // change here and a retired id cannot leave the pool scored by a weight
    // table the payload no longer carries.
    var sys = hashParam(h, "sys", "[A-Za-z0-9_]+");
    var known = ((S.data && S.data.scoring_catalog) || []).filter(function (c) { return c.id === sys; });
    if (sys && known.length) S.system = sys;
    var day = hashParam(h, "day", "\\d{4}-\\d{2}-\\d{2}");
    if (day) S.streamerDay = day;
    readSort(h, "hsort", "ros_hitter");
    readSort(h, "spsort", "ros_sp");
    readSort(h, "rpsort", "ros_rp");
    S.player = hashParam(h, "player", "\\d+");
  }
  function pushSort(parts, key, board) {
    var st = SORT[board], d = SORT_DEFAULTS[board];
    if (!st || !st.key) return;
    if (d && st.key === d.key && !!st.asc === !!d.asc) return;
    parts.push(key + "=" + st.key + "." + (st.asc ? "a" : "d"));
  }
  // The BOARD half of the hash, with the card left out. Two callers need it
  // without a player: hashFor() builds a card link over the current board, and
  // onHashChange compares before and after to tell a card open from a real
  // board change, so opening a card does not re-render 350 rows underneath it.
  function boardHash() {
    var parts = ["section=" + S.section];
    var def = ((S.data && S.data.scoring_catalog) || []).filter(function (c) { return c.default; })[0];
    if (S.system && S.system !== (def ? def.id : "fgp")) parts.push("sys=" + S.system);
    // Only once the reader has moved off the slate the board opened on. Writing
    // the default day would stamp today's date into every shared URL, and that
    // date is wrong by tomorrow morning.
    if (S.streamerDay && S.streamerDay !== S.streamerDay0) parts.push("day=" + S.streamerDay);
    pushSort(parts, "hsort", "ros_hitter");
    pushSort(parts, "spsort", "ros_sp");
    pushSort(parts, "rpsort", "ros_rp");
    return "#" + parts.join("&");
  }
  // The module's OWN hash, which is what LAST_HASH holds and what the host
  // stores. hashFor() is the same string routed through the host, because an
  // href a reader copies out of the page has to carry the module prefix too.
  function localHash() {
    return S.player ? (boardHash() + "&player=" + S.player) : boardHash();
  }
  function hashFor(mlbam) { return hostLink(boardHash() + "&player=" + mlbam); }
  function writeHash() {
    LAST_HASH = localHash();
    hostWrite(LAST_HASH);
  }
  // replaceState does not fire hashchange, so this only ever sees a hash the
  // READER changed. LAST_HASH is compared anyway: a handler that re-renders on
  // an echo of its own write ejects the user mid-scroll.
  function onHashChange() {
    if (!S.data) return;
    if (hostHash() === LAST_HASH) return;
    var before = boardHash();
    readHash();
    if (boardHash() !== before) { renderSelector(); syncTabs(); renderSection(); }
    syncCard();
    writeHash();
  }
  hostRoute(onHashChange);

  // ---- player card ----------------------------------------------------------
  // THE CARD MODULE OWNS THE OVERLAY; this file owns the data. The one thing it
  // cannot get from the payload is the four-format score line, because the
  // scoring port lives HERE and test_fantasy_split drives this file against the
  // frozen assets/fantasy.js. A second copy in the card would be a third
  // implementation nobody is comparing.
  function cardScoreLine(p) {
    if (!p || !S.data) return [];
    var sec = S.data.sections || {};
    var ids = p.side === "hit" ? sec.ros_hitter
      : (((p.ros || {}).role === "RP") ? sec.ros_rp : sec.ros_sp);
    var pool = (ids || []).map(function (m) { return rec(m, p.side); }).filter(Boolean);
    var key = p.mlbam + "|" + p.side;
    var inPool = pool.some(function (q) { return (q.mlbam + "|" + q.side) === key; });
    // scorePoints and rotoValue read S.system, so the sweep borrows it and puts
    // it back. Nothing renders between the two assignments.
    var keep = S.system, out = [];
    (S.data.scoring_catalog || []).forEach(function (c) {
      S.system = c.id;
      if (c.kind === "roto") {
        // A category value is a POSITION IN A POOL. A player the board does not
        // carry has no pool, and a z-score against a pool of one is a number
        // that means nothing, so the row is left off instead of invented.
        if (!inPool) return;
        var v = rotoValue(pool, p.side)[key];
        out.push({ label: c.label, value: num(v, 2), active: c.id === keep });
      } else {
        out.push({ label: c.label, value: num(scorePoints(p.ros, p.side), 0),
                   active: c.id === keep });
      }
    });
    S.system = keep;
    return out;
  }
  function card() { return window.EEPHUS_FANTASY_CARD || null; }
  function syncCard() { var C = card(); if (C) C.sync(S.player); }
  function attachCard() {
    var C = card();
    if (!C) return;
    C.attach({
      payload: function () { return S.data; },
      links: function () { return LINKS; },
      scoreLine: cardScoreLine,
      onClose: function () { S.player = null; writeHash(); }
    });
  }

  // ---- boot / load states ---------------------------------------------------
  function errorState(msg) {
    var r = root();
    if (r) r.innerHTML = '<div class="rd-error" role="alert"><strong>Data failed to load.</strong> ' +
      esc(msg || "") + ' The nightly build may be mid-run. <button type="button" id="rd-retry" class="rd-scorebtn">Retry</button></div>';
    var rb = el("rd-retry"); if (rb) rb.addEventListener("click", boot);
  }
  function notReady() {
    var r = root();
    if (r) r.innerHTML = '<div class="rd-note">Rest-of-season projections are being computed. ' +
      "Check back after the next nightly build.</div>";
  }
  function onData(d) {
    if (!d || !d.players) { notReady(); return; }
    S.data = d;
    S.byId = {};
    d.players.forEach(function (p) { S.byId[p.mlbam + "|" + p.side] = p; });
    var def = (d.scoring_catalog || []).filter(function (c) { return c.default; })[0];
    S.system = def ? def.id : "fgp";
    var b = bannerEl();
    if (b) {
      b.innerHTML = '<div class="rd-asof">' + (d.n_players || 0) + " players · rest-of-season, " +
        Math.round((d.season_fraction || 0) * 100) + "% of " + esc(d.season) +
        " played · scored in your league format</div>";
    }
    // Deep-link restore between the defaults and the first paint, so a restored
    // section or format renders once rather than flashing the default first.
    readHash();
    attachCard();
    renderSelector(); wireTabs(); syncTabs(); renderSection();
    writeHash();
    syncCard();
    if (!LINKS && window.EEPHUS_HUB && EEPHUS_HUB.links) {
      // The BOARD no longer needs the links sidecar: every name opens the
      // in-page card, which is the only surface carrying the outbound link to
      // the merged MLB page. So its arrival repaints the card, not 350 rows.
      EEPHUS_HUB.links().then(function (L) { LINKS = L || null; syncCard(); });
    }
  }
  function boot() {
    load(DATA_URL).then(onData).catch(function (e) { errorState(String(e && e.message || e)); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // ---- module styles (theme tokens only) ------------------------------------
  // The CARD styles are NOT here: they live next to the shared .mlb-card block
  // in assets/site.css, because these are the same cards the Projections and
  // Free Agency boards run on and one copy is the point.
  var css = document.createElement("style");
  css.textContent = [
    ".rd-scoring-bar,.fantasy-scoring-bar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:10px 0}",
    // The shell reserves the bar for every tab; only three of them fill it. An
    // emptied flex box still collapses its own margins into a 10px band above
    // the section nav, so the unused slot is removed from layout outright.
    ".rd-scoring-bar:empty,.fantasy-scoring-bar:empty{display:none;margin:0}",
    ".rd-score-lbl,.rd-score-sep{font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin-right:4px}",
    ".rd-score-sep{margin-left:8px}",
    ".rd-scorebtn{font:600 12px/1 var(--font-retro,monospace);padding:6px 11px;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer}",
    ".rd-scorebtn.active{background:var(--accent-cyan);color:var(--text-on-accent);border-color:transparent}",
    ".rd-table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}",
    ".rd-table th{text-align:right;font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em;padding:6px 8px;border-bottom:1px solid var(--border)}",
    ".rd-table td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--border-light);color:var(--text-primary)}",
    // The name column is column 3 on Daily Streamers, 2 on Two-Start SP and 1
    // on Buy / Sell, so the old `th:nth-child(2)` left-aligned the WRONG
    // heading on two of the three: "Player" and "Pitcher" sat right-aligned
    // over left-aligned names while "Date" and "Pos" sat left-aligned over
    // right-aligned values. The heading now carries the same class its cells
    // do, which cannot drift when a column moves.
    ".rd-table th.rd-nm,.rd-table td.rd-nm{text-align:left}",
    // Wide tables scroll INSIDE this box. Without it the 7-column streamers
    // table measured 431px against a 390px phone and scrolled the PAGE
    // sideways, clipping the Park column off the right edge of the viewport.
    ".rd-tablewrap{max-width:100%}",
    ".rd-tools{display:flex;justify-content:flex-end;margin:6px 0}",
    // THE RANK CELL'S CLASS CHANGED, and this rule is why the colour survived.
    // The rank td used to be .rd-rk; it is now .mlbstats-col-rank, because
    // site.css carries a rule that UNDOES the frozen first column on any
    // .rd-table whose first cell is .rd-rk (freezing a rank digit pins the
    // number and scrolls the name away). Stamping the shared rank class on the
    // header AND the cell is the module-side fix that rule's own comment asks
    // for: the rank-rail rules take over, the digit pins narrow at the left
    // edge and the NAME pins beside it. The muted colour is re-declared here so
    // the rename costs nothing on screen.
    ".rd-table td.mlbstats-col-rank{color:var(--text-tertiary)}",
    "@media (max-width:640px){.rd-tablewrap{scrollbar-width:thin;scrollbar-color:var(--border) transparent;padding-bottom:4px}",
    ".rd-tablewrap::-webkit-scrollbar{height:4px;display:block}",
    ".rd-tablewrap::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}}",
    // .rd-sc is now a SPAN inside the cell on Buy/Sell (two scale columns, one
    // filled per row) and still a cell class on the two point tables, so the
    // rule is written unqualified rather than as `td.rd-sc`.
    ".rd-table .rd-sc{font-weight:700}",
    ".rd-pos{color:var(--accent-green)}.rd-neg{color:var(--accent-red)}",
    ".rd-daypills{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 2px}",
    ".rd-daypill{font:600 12px/1 var(--font-retro,monospace);padding:6px 11px;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer}",
    ".rd-daypill.active{background:var(--accent-cyan);color:var(--text-on-accent);border-color:transparent}",
    ".rd-proj{color:var(--text-tertiary);font-style:italic}",
    ".rd-note{font-size:12.5px;color:var(--text-secondary);background:var(--bg-secondary);border:1px solid var(--border);padding:9px 12px;margin:8px 0}",
    ".rd-cols{display:flex;gap:16px;flex-wrap:wrap}.rd-half{flex:1;min-width:280px}",
    ".rd-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}",
    ".rd-team-card{border:1px solid var(--border);padding:8px 10px;background:var(--bg-secondary)}",
    ".rd-team-hd{font-weight:700;font-size:13px;margin-bottom:5px}",
    ".rd-relief{font-size:12.5px;padding:2px 0}.rd-dim{color:var(--text-tertiary);font-size:11px}",
    ".rd-closer{font:700 9px/1 var(--font-retro,monospace);color:var(--text-on-accent);background:var(--accent-green);padding:2px 5px}",
    ".rd-hc{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary)}",
    ".rd-asof{font-size:12px;color:var(--text-tertiary);margin:4px 0}",
    ".rd-error{border:1px solid var(--accent-red);padding:12px;color:var(--text-primary);background:var(--bg-secondary)}",
    ".rd-name-link{color:var(--accent-cyan);text-decoration:none}.rd-name-link:hover{text-decoration:underline}",
    ".rd-mech{font:600 10px/1 var(--font-retro,monospace);border:1px solid var(--border);padding:2px 5px;white-space:nowrap;cursor:help}",
    ".rd-mech.rd-mech-up{color:var(--accent-green);border-color:var(--accent-green)}",
    ".rd-mech.rd-mech-down{color:var(--accent-red);border-color:var(--accent-red)}"
    // NOTHING FOR THE SORT BAR, THE RANK CHIP OR THE SCORE CELL LIVES HERE any
    // more. Those are .ff-sortbar / .ff-rank / .ff-strong in assets/site.css
    // and the markup above names them. The local copies that used to sit here
    // were at the same specificity but LATER in the cascade than the
    // stylesheet, so they quietly beat it: that is how the phone sort-bar
    // swipe strip and the rank diamond went missing on this page.
  ].join("");
  document.head.appendChild(css);
})();
