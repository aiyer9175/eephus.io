// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026
//
// The DFS sub-module of /fantasy/. Today's slate, priced per game, plus a
// lineup optimizer. It was the whole of /dfs/ between 2026-08-05 and
// 2026-08-07 and that dir is a redirect stub now.
//
// WHERE THE NUMBERS COME FROM. data/dfs.json (dfs_export.py) carries the slate,
// a per-game projected line for every probable starter and every hitter whose
// club plays today, and the scoring weight tables. The skill half of those
// lines rides the same rest-of-season engine the Redraft board runs on; the
// per-game playing time, matchup multiplier and park leg are display-layer
// estimates and the payload labels each one. This file re-scores and solves.
// It fits nothing.
//
// WHERE THE SALARIES COME FROM. You. We do not scrape or republish any
// contest site's salary feed. Paste the CSV your site exports, or type prices
// in by hand. Salaries live in this browser's localStorage and are sent
// nowhere, because there is nowhere to send them: this page has no server.
//
// THE OPTIMIZER is a greedy build plus a local-search improvement pass (single
// swaps to a local optimum, then pairwise swaps to escape the obvious traps).
// At MLB slate sizes that lands on or next to the true optimum in well under a
// frame, and it degrades honestly: if the constraint set has no feasible
// lineup, it says so instead of returning a broken one.
(function () {
  "use strict";
  var DATA_URL = "/data/dfs.json";
  var LS_SAL = "eephus.dfs.salaries";
  var LS_SET = "eephus.dfs.settings";
  var S = {
    data: null, error: null, section: "slate", system: "dk", template: null,
    cap: null, maxPerTeam: null, minStart: 0.5, avoidOpp: false,
    salaries: {}, salaryMeta: null, lineup: null, importReport: null,
    player: null,
    q: "", pos: null, team: null, hitShown: 100,
    sort: { pitchers: { key: "pts", asc: false }, hitters: { key: "pts", asc: false } }
  };
  // One page of the hitter board. 508 rows in one <table> is a scroll nobody
  // finishes; the board opens at 100 and extends on demand (2026-08-16).
  var HIT_PAGE = 100;
  var LINKS = null;
  // The SEASON corpus, borrowed from the coordinator for the player card only.
  // This module's own payload is the slate; see the card block near the router.
  var CORPUS = null;
  var CORPUS_PENDING = false;

  // ---- shell binding --------------------------------------------------------
  function el(id) { return document.getElementById(id); }
  function pick() {
    for (var i = 0; i < arguments.length; i++) {
      var n = el(arguments[i]);
      if (n) return n;
    }
    return null;
  }
  function root() { return pick("dfs-app-root", "fantasy-app-root"); }
  function bannerEl() { return pick("dfs-banner", "fantasy-banner"); }
  function scoringBar() { return pick("dfs-scoring", "fantasy-scoring"); }
  function tabs() {
    var t = document.querySelectorAll(".mlbstats-sectionbtn[data-dfssection]");
    if (t && t.length) return t;
    return document.querySelectorAll(".mlbstats-sectionbtn[data-fantasysection]");
  }
  function tabKey(b) {
    return b.getAttribute("data-dfssection") || b.getAttribute("data-fantasysection");
  }

  // ---- host binding (the combined /fantasy/ page, 2026-08-07) ---------------
  // assets/fantasy-hub.js owns the address bar on /fantasy/ and hands this
  // module its own half of the hash, because Redraft and Dynasty are in the
  // same document with their own "#section=" vocabularies.
  //
  // THE HOST ALSO HOLDS THE SEASON CORPUS, and that is what finally makes the
  // player card reachable from a DFS row. The card is a lookup into
  // data/fantasy.json, which this module does not read and must not start
  // reading: its own sidecar is the slate. So it asks the host for the corpus
  // the OTHER two modules already load, and only when a reader opens a card.
  // Off /fantasy/ there is no host, no corpus and no card, and every name falls
  // back to the outbound link it had before.
  var MODULE = "dfs";
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
  // Content stamp lookup for the standalone read. build_site emits
  // window.EEPHUS_DATA_VERS on pages whose payloads are build-time artifacts;
  // with a stamp the fetch rides a versioned URL under DEFAULT caching, and
  // without one (hand-served page, missing emission) the no-cache
  // revalidation below stays exactly as it was. The betting payloads never
  // enter the map: the close job mutates them intra-day with no rebuild.
  function stampedURL(url) {
    try {
      var vers = (typeof window !== "undefined" && window.EEPHUS_DATA_VERS) || null;
      var v = vers && vers[url.split("/").pop()];
      return v ? url + "?v=" + encodeURIComponent(v) : null;
    } catch (e) { return null; }
  }
  function load(url) {
    var H = host();
    if (H) return H.json(url);
    var stamped = stampedURL(url);
    var opts = stamped ? undefined : { cache: "no-cache" };
    if (stamped) url = stamped;
    return fetch(url, opts).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  // ---- Diamond gate (wired, OFF) -------------------------------------------
  // Routed through window.EephusDiamond (assets/eephus-diamond.js) since
  // 2026-08-16; the private dcfg()/isMember() copy that lived here read config
  // keys that never exist, so a flipped flag would have capped paying members.
  // Absent helper means the gate is open.
  function gate() { return window.EephusDiamond || null; }
  function gated() {
    var D = gate();
    try { return !!(D && D.gated()); } catch (e) { return false; }
  }
  function capRows(rows) {
    if (!gated()) return rows;
    return (rows || []).slice(0, gate().previewRows("dfs"));
  }
  // The conversion line is a LINK. It was plain text on every Diamond page, so
  // the only route to the pricing page was the last item of a nav dropdown.
  function gateNote(total, shown) {
    if (!gated() || shown >= total) return "";
    return '<div class="dfs-note">Diamond preview: showing the top ' + shown + " of " + total +
      ' rows. <a class="dfs-name-link" href="/diamond/">Diamond funds the free site</a>.</div>';
  }

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  // The pixel state box (assets/eephus-state.js, final-pass plan 5.7 PX-12):
  // loading, empty, unmeasured or failed, around a message this file escapes.
  // The bare box is the fallback for a test harness that loads this file alone.
  function pxState(kind, msg, opts) {
    var S = typeof window !== "undefined" && window.EephusState;
    if (S) return S.html(kind, msg, opts);
    var cls = typeof opts === "string" ? opts : (opts && opts.cls) || "";
    return '<div class="px-state is-' + kind + (cls ? " " + cls : "") + '"' +
      (kind === "failed" ? ' role="alert"' : "") + '><div class="px-state-msg">' + msg + "</div></div>";
  }
  function num(v, d) { return (v == null || isNaN(v)) ? "-" : Number(v).toFixed(d == null ? 1 : d); }
  function money(v) { return (v == null || isNaN(v)) ? "-" : ("$" + Math.round(v).toLocaleString()); }
  function hrefFor(mlbam) {
    var e = LINKS && LINKS.byMlbam && LINKS.byMlbam[String(mlbam)];
    return (e && e.key) ? ("/projections/#player=" + e.key) : null;
  }
  // On the combined page a name opens the in-page card, which resolves for
  // every row on the slate. The outbound /projections/ link is the fallback,
  // and it only ever resolved for the players player_links covers.
  function nameLink(mlbam, name) {
    if (cardable()) {
      return '<a class="dfs-name-link" href="' + esc(cardHash(mlbam)) + '">' + esc(name) + "</a>";
    }
    var h = hrefFor(mlbam);
    if (h) return '<a class="dfs-name-link" href="' + esc(h) + '">' + esc(name) + "</a>";
    return esc(name);
  }
  function teamLogo(team) {
    return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo && team) ? EEPHUS_HUB.teamLogo(team) : "";
  }
  // Glossary term span, on the betting.js contract: the span carries NO
  // .g-term of its own. eephus-gl's wire() adds that class only when the slug
  // resolves against the loaded glossary, so a slug the artifact does not
  // carry yet (the DFS vocabulary: points per $1k, start rate, team total,
  // matchup multiplier) degrades to plain text instead of a clickable term
  // that defines nothing, and lights up the day the entry lands.
  function gl(label, slug) {
    return '<span data-gl="' + esc(slug) + '">' + esc(label) + "</span>";
  }
  // Name key for joining a salary sheet to our pool. Lowercase, accents folded,
  // punctuation and generational suffixes dropped, so "Ronald Acuna Jr." and
  // "Ronald Acuña Jr" land on the same key.
  function nameKey(s) {
    var t = String(s || "");
    if (t.normalize) t = t.normalize("NFD").replace(/[̀-ͯ]/g, "");
    return t.toLowerCase()
      .replace(/[^a-z ]/g, " ")
      .replace(/\b(jr|sr|ii|iii|iv)\b/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  // ---- persisted settings ---------------------------------------------------
  function templates() { return (S.data && S.data.roster_templates) || []; }
  function template() {
    var list = templates();
    var found = null;
    list.forEach(function (t) { if (t.id === S.template) found = t; });
    if (found) return found;
    list.forEach(function (t) { if (!found && t.default) found = t; });
    return found || list[0] || null;
  }
  function loadSettings() {
    var v = null;
    try { v = JSON.parse(window.localStorage.getItem(LS_SET) || "null"); } catch (e) { v = null; }
    if (!v) return;
    if (v.system) S.system = v.system;
    if (v.template) S.template = v.template;
    if (v.cap != null) S.cap = v.cap;
    if (v.maxPerTeam != null) S.maxPerTeam = v.maxPerTeam;
    if (v.minStart != null) S.minStart = v.minStart;
    if (v.avoidOpp != null) S.avoidOpp = !!v.avoidOpp;
  }
  function saveSettings() {
    try {
      window.localStorage.setItem(LS_SET, JSON.stringify({
        system: S.system, template: S.template, cap: S.cap,
        maxPerTeam: S.maxPerTeam, minStart: S.minStart, avoidOpp: S.avoidOpp
      }));
    } catch (e) { /* private mode */ }
  }
  function loadSalaries() {
    var v = null;
    try { v = JSON.parse(window.localStorage.getItem(LS_SAL) || "null"); } catch (e) { v = null; }
    if (!v || !v.rows) return;
    // Salaries belong to ONE slate. Yesterday's prices on today's board would
    // be worse than no prices, so a date mismatch drops them rather than
    // silently pricing the wrong day.
    if (S.data && v.slate_date && v.slate_date !== S.data.slate_date) return;
    S.salaries = v.rows;
    S.salaryMeta = { slate_date: v.slate_date, saved_at: v.saved_at, n: Object.keys(v.rows).length };
  }
  function saveSalaries() {
    try {
      window.localStorage.setItem(LS_SAL, JSON.stringify({
        slate_date: S.data ? S.data.slate_date : null,
        saved_at: new Date().toISOString(), rows: S.salaries
      }));
    } catch (e) { /* private mode */ }
  }

  // ---- salary CSV -----------------------------------------------------------
  // A tolerant reader, not a spec-complete CSV parser: it handles quoted fields
  // and embedded commas, which is all a contest-site export throws at it, and
  // it finds its columns by header NAME so a site adding a column upstream does
  // not shift the salary out from under us.
  function parseCsv(text) {
    var rows = [], row = [], cur = "", q = false;
    var t = String(text || "").replace(/\r\n?/g, "\n");
    for (var i = 0; i < t.length; i++) {
      var ch = t[i];
      if (q) {
        if (ch === '"') {
          if (t[i + 1] === '"') { cur += '"'; i++; }
          else q = false;
        } else cur += ch;
      } else if (ch === '"') q = true;
      else if (ch === ",") { row.push(cur); cur = ""; }
      else if (ch === "\n") { row.push(cur); rows.push(row); row = []; cur = ""; }
      else cur += ch;
    }
    row.push(cur);
    if (row.length > 1 || row[0] !== "") rows.push(row);
    return rows;
  }
  var COL_ALIASES = {
    name: ["name", "nickname", "player", "player name", "full name"],
    salary: ["salary", "cost", "price"],
    pos: ["position", "roster position", "pos"],
    team: ["teamabbrev", "team", "team abbrev", "tm"]
  };
  function headerIndex(header) {
    var idx = {};
    (header || []).forEach(function (h, i) {
      var k = String(h || "").trim().toLowerCase();
      Object.keys(COL_ALIASES).forEach(function (want) {
        if (idx[want] != null) return;
        if (COL_ALIASES[want].indexOf(k) >= 0) idx[want] = i;
      });
    });
    return idx;
  }
  function importSalaries(text) {
    var rows = parseCsv(text).filter(function (r) { return r && r.join("").trim() !== ""; });
    if (!rows.length) {
      S.importReport = { ok: false, msg: "That file had no rows in it." };
      return;
    }
    // Contest exports sometimes stack two tables in one file, so the header is
    // located by content rather than assumed to be line 1.
    var hIdx = -1, idx = null;
    for (var i = 0; i < Math.min(rows.length, 12); i++) {
      var cand = headerIndex(rows[i]);
      if (cand.name != null && cand.salary != null) { hIdx = i; idx = cand; break; }
    }
    if (hIdx < 0) {
      S.importReport = { ok: false,
        msg: "No Name and Salary columns found. Expected headers like Name, Position, " +
             "Salary, TeamAbbrev." };
      return;
    }
    var pool = {}, byName = {};
    ((S.data && S.data.players) || []).forEach(function (p) {
      pool[p.mlbam + "|" + p.side] = p;
      var k = nameKey(p.name);
      (byName[k] = byName[k] || []).push(p);
    });
    var matched = 0, unmatched = [], read = 0;
    var next = {};
    for (var r = hIdx + 1; r < rows.length; r++) {
      var cells = rows[r];
      var nm = cells[idx.name], sal = parseInt(String(cells[idx.salary] || "").replace(/[^0-9]/g, ""), 10);
      if (!nm || isNaN(sal) || sal <= 0) continue;
      read++;
      var cands = byName[nameKey(nm)] || [];
      if (idx.team != null && cands.length > 1) {
        var tm = String(cells[idx.team] || "").trim().toUpperCase();
        var narrowed = cands.filter(function (p) { return String(p.team || "").toUpperCase() === tm; });
        if (narrowed.length) cands = narrowed;
      }
      // A pitcher row and a hitter row can share a name (the two-way case), so
      // the CSV position column decides which record the price belongs to.
      var posRaw = idx.pos != null ? String(cells[idx.pos] || "").toUpperCase() : "";
      if (cands.length > 1 && posRaw) {
        var wantPit = posRaw.indexOf("P") >= 0 && posRaw.indexOf("1B") < 0;
        var byside = cands.filter(function (p) { return (p.side === "pit") === wantPit; });
        if (byside.length) cands = byside;
      }
      if (!cands.length) { unmatched.push(nm); continue; }
      var p0 = cands[0];
      var elig = posRaw ? posRaw.split(/[\/,]/).map(function (x) { return x.trim(); })
        .filter(Boolean) : null;
      next[p0.mlbam + "|" + p0.side] = { salary: sal, csv_pos: elig, csv_name: nm };
      matched++;
    }
    S.salaries = next;
    saveSalaries();
    S.salaryMeta = { slate_date: S.data ? S.data.slate_date : null,
                     saved_at: new Date().toISOString(), n: matched };
    S.importReport = { ok: true, read: read, matched: matched,
                       unmatched: unmatched.slice(0, 25), unmatched_n: unmatched.length };
    S.lineup = null;
  }

  // ---- pool -----------------------------------------------------------------
  function salaryOf(p) {
    var s = S.salaries[p.mlbam + "|" + p.side];
    return s ? s.salary : null;
  }
  function eligOf(p) {
    var s = S.salaries[p.mlbam + "|" + p.side];
    // The reader's own contest sheet is authoritative about what slot a player
    // fills there. Our fielding-games eligibility is the fallback.
    if (s && s.csv_pos && s.csv_pos.length) return s.csv_pos;
    return p.elig || ["UTIL"];
  }
  function ptsOf(p) { return ((p.pts || {})[S.system] != null) ? p.pts[S.system] : 0; }
  function valueOf(p) {
    var sal = salaryOf(p);
    return sal ? (ptsOf(p) / (sal / 1000)) : null;
  }
  function playersOf(side) {
    return ((S.data && S.data.players) || []).filter(function (p) { return p.side === side; });
  }

  // ---- filter bar (2026-08-16) ----------------------------------------------
  // A VIEW over the slate, and the ONE view the optimizer also honors: the
  // pool it solves over is the filtered pool, said out loud on that panel.
  // Name is a case-insensitive substring; position matches eligOf (so the
  // reader's own CSV positions win here exactly as they do in a lineup slot);
  // team matches the served code. Duplicated per client on purpose, the same
  // trade the sort machinery already made.
  function normQ(s) { return String(s == null ? "" : s).toLowerCase(); }
  function decodeQ(s) {
    try { return decodeURIComponent(s); } catch (e) { return ""; }
  }
  function filtersOn() { return !!(S.q || S.pos || S.team); }
  function passFilter(p) {
    if (!p) return false;
    if (S.q && normQ(p.name).indexOf(normQ(S.q)) < 0) return false;
    if (S.pos && eligOf(p).indexOf(S.pos) < 0) return false;
    if (S.team && String(p.team || "").toUpperCase() !== S.team) return false;
    return true;
  }
  function filterRows(list) {
    return filtersOn() ? (list || []).filter(passFilter) : (list || []);
  }
  // Every filter change is a pool change: the shown page resets and a solved
  // lineup goes stale, because it was solved over a pool that no longer
  // matches the screen.
  function filterChanged() {
    S.hitShown = HIT_PAGE;
    S.lineup = null;
    renderSection();
    writeHash();
  }
  function filterVocab() {
    var pos = {}, team = {};
    ((S.data && S.data.players) || []).forEach(function (p) {
      eligOf(p).forEach(function (e) { pos[e] = 1; });
      if (p.team) team[p.team] = 1;
    });
    return { pos: Object.keys(pos).sort(), team: Object.keys(team).sort() };
  }
  function filterBarHTML() {
    var v = filterVocab();
    var out = '<input type="search" id="dfs-f-q" class="dfs-f-q" placeholder="Filter by name"' +
      ' aria-label="Filter by player name" maxlength="40" value="' + esc(S.q) + '">';
    if (v.pos.length > 1) {
      out += v.pos.map(function (e) {
        var on = e === S.pos;
        return '<button type="button" class="dfs-f-pos' + (on ? " active" : "") +
          '" data-dfsfpos="' + esc(e) + '" aria-pressed="' + (on ? "true" : "false") + '">' +
          esc(e) + "</button>";
      }).join("");
    }
    if (v.team.length > 1) {
      out += '<select id="dfs-f-team" data-team-picker aria-label="Filter by team"><option value="">All teams</option>' +
        v.team.map(function (t) {
          return '<option value="' + esc(t) + '"' + (t === S.team ? " selected" : "") + ">" +
            esc(t) + "</option>";
        }).join("") + "</select>";
    }
    if (filtersOn()) {
      out += '<button type="button" class="dfs-f-pos" id="dfs-f-clear">Clear</button>';
    }
    return '<div class="dfs-filterbar">' + out + "</div>";
  }
  function wireFilterBar(r) {
    var q = r.querySelector ? r.querySelector("#dfs-f-q") : null;
    if (q) q.addEventListener("input", function () {
      S.q = String(q.value || "").slice(0, 40);
      filterChanged();
      var again = r.querySelector("#dfs-f-q");
      if (again && again.focus) {
        again.focus();
        try { again.setSelectionRange(again.value.length, again.value.length); } catch (e) { /* fine */ }
      }
    });
    r.querySelectorAll("[data-dfsfpos]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-dfsfpos");
        S.pos = (S.pos === v) ? null : v;
        filterChanged();
      });
    });
    var t = r.querySelector ? r.querySelector("#dfs-f-team") : null;
    if (t) t.addEventListener("change", function () {
      S.team = t.value ? String(t.value).toUpperCase() : null;
      filterChanged();
    });
    var c = r.querySelector ? r.querySelector("#dfs-f-clear") : null;
    if (c) c.addEventListener("click", function () {
      S.q = ""; S.pos = null; S.team = null;
      filterChanged();
    });
  }

  // ---- honesty signals ------------------------------------------------------
  // dfs_export publishes four things about how much this payload can be
  // trusted, and the client rendered NONE of them: the page looked identical
  // whether today's build succeeded, was refused and replaced by yesterday's,
  // or came out with a whole side of the slate missing. Each renderer below
  // reads one of those keys and prints what it says. Nothing here recomputes a
  // judgement the exporter already made.

  // 1. stale_slate. refresh() refuses to overwrite a good payload with one it
  //    cannot verify (dead schedule feed) or one that is structurally
  //    impossible (games but no hitters). It restamps YESTERDAY's board with
  //    stale_slate + the reason and files a RED ledger row. That was invisible
  //    here: the reader got a full, confident board carrying another day's
  //    date in a corner of the banner.
  //
  //    AND THE STAMP IS NOT ENOUGH ON ITS OWN. stale_slate is written by the
  //    publish decision, so it only exists on the paths that REACHED that
  //    decision. A daily job that never ran, or one that died before it, leaves
  //    the old payload on disk carrying no flag at all: on 2026-08-07 this page
  //    served the 2026-08-05 slate at full confidence for exactly that reason.
  //    A slate date in the past is enough to know, and the reader's own clock is
  //    the only clock that matters here, so the client checks it itself rather
  //    than trusting a stamp only the healthy paths write.
  function todayLocal() {
    // The VIEWER's calendar day. A bare ISO string through new Date() is parsed
    // as UTC and reads as the previous day anywhere west of Greenwich, which
    // would fire this banner a day early every North American evening, so both
    // sides of the comparison are built from local date parts.
    var t = new Date();
    return t.getFullYear() + "-" + ("0" + (t.getMonth() + 1)).slice(-2) +
      "-" + ("0" + t.getDate()).slice(-2);
  }
  function staleInfo() {
    var d = S.data || {};
    // The season is over: no later slate is due, so a past slate date is not
    // a missed run and the season-over panel is the whole story (audit QREC12).
    if (d.empty_reason_kind === "season_over") return null;
    if (d.stale_slate) {
      return { date: d.slate_date,
               reason: d.stale_reason ||
                 "Today's build could not be verified, so it was not published.",
               kept: true, checked: d.stale_checked_at || null };
    }
    if (d.slate_date && String(d.slate_date) < todayLocal()) {
      return { date: d.slate_date,
               reason: "Today's slate has not published; this is the last board on disk. " +
                 "It carries no staleness stamp, so the daily run stopped before writing one.",
               kept: false, checked: null };
    }
    return null;
  }
  function staleBanner() {
    var st = staleInfo();
    if (!st) return "";
    var when = st.date ? esc(st.date) : "an earlier";
    return '<div class="dfs-stale" role="alert">' +
      "<strong>This is the " + when + " slate, not today's.</strong>" +
      "<span>" + esc(st.reason) + "</span>" +
      "<span>" + (st.kept ? "We kept the last board we could verify. " : "") +
      "Projections below are for " + when + "; salaries imported for another date " +
      "are dropped.</span>" +
      (st.checked
        ? '<span class="dfs-stale-when">Checked ' + esc(st.checked) + ".</span>"
        : "") +
      "</div>";
  }

  // 2. integrity. The counts every join resolved, so a THIN board can be told
  //    from a BROKEN one. On 2026-08-05 this page served 15 games, 29 players
  //    and zero hitters and looked tidy; the counts are what would have said so
  //    out loud. Rendered on the slate tab, where the boards they describe are.
  function integrityPanel() {
    var g = (S.data || {}).integrity;
    if (!g) return "";
    var m = g.matchup_orgs_resolved || {};
    var exp = m.expected == null ? null : m.expected;
    var off = m.offense_plus, pen = m.bullpen_plus;
    var missing = g.orgs_without_hitters || [];
    // A partial join is not a failure worth blocking a board over, but it is a
    // fact a reader is entitled to: "23 of 30 clubs" is the number nobody would
    // ever have seen otherwise.
    var thin = (exp != null && ((off != null && off < exp) || (pen != null && pen < exp))) ||
               missing.length > 0;
    var nGames = ((S.data || {}).games || []).length;
    var sides = g.lineup_sides_possible;
    // TWO POPULATIONS (2026-09-11). n_hitters / n_pitchers are what the board
    // serves; n_*_priced is everything that priced before the active-roster
    // filter. The chip used to say "Hitters priced 128" above a board of 109.
    // A payload from before the split carries no n_*_priced and its n_hitters
    // IS the priced count, so it keeps the old label rather than being
    // relabelled as a board count it never was.
    var split = g.n_hitters_priced != null;
    var offH = split ? (g.n_hitters_removed_off_roster || 0) : 0;
    var offP = split ? (g.n_pitchers_removed_off_roster || 0) : 0;
    var cells =
      kvChip(split ? "Hitters on the board" : "Hitters priced", g.n_hitters) +
      kvChip(split ? "Starters on the board" : "Starters priced", g.n_pitchers) +
      (offH + offP > 0 ? kvChip("Left off, not on an active roster", offH + offP) : "") +
      kvChip("Probables announced", g.n_probables_announced) +
      (exp == null ? "" : kvChip("Clubs with Offense+", off == null ? "-" : off + " of " + exp)) +
      (exp == null ? "" : kvChip("Clubs with Bullpen+", pen == null ? "-" : pen + " of " + exp)) +
      // The three joins added on 2026-08-07, counted the same way as the rest:
      // what resolved over what this slate needed, never over the league's 30.
      (g.park_sources == null ? "" : kvChip("Games with a park factor",
        ((g.park_sources.savant_mlb || 0) + (g.park_sources.milb_park_factors || 0)) +
        " of " + nGames)) +
      (g.vegas_games == null ? "" : kvChip("Games with a Vegas total", g.vegas_games + " of " + nGames)) +
      (sides == null ? "" : kvChip("Lineups posted", (g.lineup_sides_posted || 0) + " of " + sides));
    return '<div class="dfs-integrity' + (thin ? " is-thin" : "") + '">' +
      '<div class="dfs-integrity-h">What this build resolved</div>' +
      '<div class="dfs-integrity-row">' + cells + "</div>" +
      (missing.length
        ? '<div class="dfs-integrity-note">No hitter matched ' + missing.length +
          " club" + (missing.length === 1 ? "" : "s") + " on the slate: " +
          esc(missing.join(", ")) + ". Those are missed joins.</div>"
        : "") +
      (thin && !missing.length
        ? '<div class="dfs-integrity-note">Some clubs have no measured team context; ' +
          "their matchup multiplier falls back to neutral (rows marked no matchup).</div>"
        : "") +
      (offH + offP > 0
        ? '<div class="dfs-integrity-note">We priced ' + esc(g.n_hitters_priced) + " " +
          plural(g.n_hitters_priced, "hitter", "hitters") + " and " + esc(g.n_pitchers_priced) + " " +
          plural(g.n_pitchers_priced, "starter", "starters") + ". " + esc(offH) + " " +
          plural(offH, "hitter", "hitters") + " and " + esc(offP) + " " +
          plural(offP, "starter", "starters") + " are not on a current active roster, so they " +
          "are left off the board.</div>"
        : "") +
      "</div>";
  }
  function plural(n, one, many) { return Number(n) === 1 ? one : many; }
  function kvChip(label, value) {
    if (value == null) return "";
    return '<span class="dfs-kv"><span class="dfs-kv-l">' + esc(label) + "</span>" +
      '<span class="dfs-kv-v">' + esc(value) + "</span></span>";
  }

  // 3. matchup_resolved, per row. Both team-context lookups fall back to a
  //    neutral 100 when they miss, exactly as before - the PRICE does not move.
  //    What the payload added is the ability to tell a MEASURED 100 from a
  //    lookup that found nothing, and unmarked those two read identically.
  function matchupMark(ctx) {
    if (!ctx || ctx.matchup_resolved !== false) return "";
    return ' <span class="dfs-unres" title="The opponent Offense+ / Bullpen+ lookup missed; ' +
      'the matchup multiplier uses a neutral 100. A missing measurement, not an average ' +
      'opponent.">no matchup</span>';
  }

  // 4. empty_reason_kind. Six empties reach this page and they are not the same
  //    claim: "the league scheduled no games" is a fact about baseball, "the
  //    schedule feed did not answer" is a fact about our pipeline, and only one
  //    of them means nothing is broken. The reason SENTENCE always comes from
  //    the payload; this table only chooses the headline and the closing line
  //    around it, and whether the box reads as an outage.
  var EMPTY_KINDS = {
    no_games_scheduled: { head: "No games today", bad: false,
      tail: "Nothing is broken. The page rebuilds daily." },
    // No tail: the payload's own sentence already says when slates return.
    season_over: { head: "The season is over", bad: false, tail: "" },
    schedule_unavailable: { head: "We could not verify today's slate", bad: true,
      tail: "Pipeline outage: the schedule feed did not answer, so nothing is published " +
            "for today." },
    no_corpus: { head: "The projection corpus is missing", bad: true,
      tail: "Pipeline outage: nothing on the slate can be priced without it." },
    no_projections: { head: "The slate is here, the projections are not", bad: false,
      tail: "No player on today's games has a rest-of-season projection yet. The next " +
            "build fills it in." },
    collapsed_slate: { head: "This board did not assemble", bad: true,
      tail: "A broken join in the build. No partial slate is published." },
    build_failed: { head: "Today's build did not finish", bad: true,
      tail: "Pipeline outage: the run failed before pricing anything. No older board is " +
            "substituted." },
    // Every game on the slate had started (or finished, or was postponed)
    // when the board was built or when this page checked: a fact about the
    // day, so it reassures.
    slate_closed: { head: "Today's games have all started", bad: false,
      tail: "Nothing is broken. The next slate publishes on the next build." }
  };
  function emptyPanel(d) {
    var k = EMPTY_KINDS[d.empty_reason_kind] || null;
    // An outage draws the failed board; a quiet day draws the empty one. The
    // box keeps role=status either way: the reason sentence is not an alert.
    return pxState(k && k.bad ? "failed" : "empty",
      "<strong>" + esc(k ? k.head : "No slate to price") + "</strong> " +
      esc(d.empty_reason || "") + " " +
      esc(k ? k.tail : "This page rebuilds every day."),
      { cls: "dfs-empty" + (k && k.bad ? " is-broken" : ""), role: "status" });
  }

  // ---- the draftable slate, on the viewer's clock (owner decision 5) --------
  // The exporter leaves off every game that had started when the board was
  // BUILT, but the board is built once a day and most games start hours after
  // that. A contest locks each game at its scheduled first pitch, so the page
  // applies the same rule on the viewer's clock, every time it renders or
  // solves: a game whose first pitch is at or before now leaves the slate
  // cards, both boards, the value and stack tabs and the optimizer pool, and is
  // listed beside the games the exporter left off. An unreadable time, or a
  // start time StatsAPI marks TBD, is never locked (the exporter's rule).
  var OFF_STATE = { started: "under way", final: "final", postponed: "postponed",
                    suspended: "suspended", cancelled: "cancelled" };
  function firstPitchMs(g) {
    if (!g || g.start_time_tbd) return null;
    var t = Date.parse(String(g.datetime || ""));
    return isNaN(t) ? null : t;
  }
  function lockStarted(d, nowMs) {
    if (!d || !d.games || !d.games.length) return d;
    var keep = [], gone = {}, locked = [];
    d.games.forEach(function (g) {
      var t = firstPitchMs(g);
      if (t !== null && t <= nowMs) {
        gone[g.game_pk] = true;
        locked.push({ game_pk: g.game_pk, datetime: g.datetime,
                      away: (g.away || {}).org, home: (g.home || {}).org,
                      state: "started", basis: "viewer_clock" });
      } else keep.push(g);
    });
    if (!locked.length) return d;
    d.games = keep;
    d.players = (d.players || []).filter(function (p) { return !gone[p.game_pk]; });
    d.n_games = keep.length;
    d.n_players = d.players.length;
    d.locked_on_page = (d.locked_on_page || []).concat(locked);
    if (!keep.length && !d.empty_reason) {
      d.empty_reason = "Every game on the " + (d.slate_date || "") + " slate has started, " +
        "so nothing is left to draft.";
      d.empty_reason_kind = "slate_closed";
    }
    return d;
  }
  function liveData() {
    return lockStarted(S.data, Date.now());
  }
  // The games that are not on the board and why, from the exporter's list and
  // the page's own clock. Nothing renders when every game is still open.
  function offBoardNote() {
    var d = S.data || {};
    var rows = (d.excluded_games || []).concat(d.locked_on_page || []);
    if (!rows.length) return "";
    return '<div class="dfs-note">Off the board, because nobody can still draft them: ' +
      rows.map(function (x) {
        return esc((x.away || "") + " at " + (x.home || "")) + " (" +
          esc(OFF_STATE[x.state] || "under way") + (x.reason ? ", " + esc(x.reason) : "") + ")";
      }).join(", ") + ".</div>";
  }

  // ---- boards ---------------------------------------------------------------
  var PIT_COLS = [
    { key: "rank", label: "#" },
    { key: "name", label: "Pitcher", text: true },
    { key: "pts", label: "Proj", num: true },
    { key: "salary", label: "Salary", num: true },
    { key: "value", label: "Pts/$1k", num: true, term: "dfs_points_per_1k" },
    { key: "opp", label: "Opponent", text: true },
    // The runs the market expects the club he is facing to score. It is the
    // single most-read number on a DFS pitcher card and it is pure market: no
    // projection on this page is priced off it.
    { key: "opp_itt", label: "Opp total", num: true, term: "implied_team_total" },
    { key: "ip", label: "IP", num: true },
    { key: "k", label: "K", num: true },
    { key: "sem_plus", label: "SEM+", num: true, term: "sem_plus" }
  ];
  var HIT_COLS = [
    { key: "rank", label: "#" },
    { key: "name", label: "Hitter", text: true },
    { key: "pts", label: "Proj", num: true },
    { key: "salary", label: "Salary", num: true },
    { key: "value", label: "Pts/$1k", num: true, term: "dfs_points_per_1k" },
    { key: "start_rate", label: "Start", num: true, term: "dfs_start_rate" },
    // Sorts on the spot itself, so a click gives the reader the confirmed
    // top-of-the-order bats. Rows with no posted card sort last, which is the
    // honest place for "we do not know" on a column about what is known.
    { key: "lineup", label: "Spot", num: true },
    { key: "opp", label: "Opponent", text: true },
    { key: "itt", label: "Team total", num: true, term: "implied_team_total" },
    { key: "opp_sp", label: "Opp SP", text: true },
    { key: "hem_plus", label: "HEM+", num: true, term: "hem_plus" }
  ];
  function cellOf(p, key) {
    var line = p.line || {}, ctx = p.ctx || {};
    switch (key) {
      case "name": return p.name;
      case "pts": return ptsOf(p);
      case "salary": return salaryOf(p);
      case "value": return valueOf(p);
      case "start_rate": return p.start_rate;
      // The SORT value, which is the confirmed spot or nothing. A scratched bat
      // and an unposted card both sort last, because neither is a batting order
      // and putting "out" at the top of an ascending Spot sort would bury the
      // nine rows the column exists to surface. The CELL still tells them
      // apart; see lineupCell.
      case "lineup": return p.lineup_spot || null;
      case "opp": return (p.is_home ? "vs " : "@ ") + (p.opp || "");
      case "itt": return ctx.vegas_itt;
      case "opp_itt": return ctx.vegas_opp_itt;
      case "opp_sp": return ctx.opp_sp || null;
      case "ip": return line.ip;
      case "k": return line.k;
      case "sem_plus": return p.sem_plus;
      case "hem_plus": return p.hem_plus;
      default: return null;
    }
  }
  function fmtCell(p, key) {
    var v = cellOf(p, key);
    if (key === "name") return teamLogo(p.team) + " " + nameLink(p.mlbam, p.name) +
      ' <span class="dfs-elig">' + esc(eligOf(p).join("/")) + "</span>";
    // Ahead of the null guard on purpose: this column's null covers TWO states
    // and only one of them is "-".
    if (key === "lineup") return lineupCell(p);
    if (v == null || v === "") return "-";
    // The opponent cell is where the matchup multiplier is legible, so it is
    // where an unresolved lookup gets said out loud.
    if (key === "opp") return esc(v) + matchupMark(p.ctx);
    if (key === "salary") return money(v);
    if (key === "value") return num(v, 2);
    // A confirmed start is a FACT and a projected one is a guess, and 100% next
    // to 79% reads as the same kind of number unless the row says otherwise.
    //
    // ONLY ON THE CONFIRMED SIDE. A scratched bat is also sourced from a posted
    // card, so the first cut chipped him too, and a green "posted" mark beside
    // a 0% start rate reads as reassurance about a player who is not playing.
    // His Spot cell already carries the red "out", which is the same fact in
    // the column that is about it.
    if (key === "start_rate") {
      return Math.round(v * 100) + "%" +
        (p.lineup_status === "confirmed"
          ? ' <span class="dfs-conf" title="Lineup posted. Projected start rate was ' +
            Math.round((p.start_rate_projected || 0) * 100) + '%.">posted</span>'
          : "");
    }
    if (key === "itt" || key === "opp_itt") return num(v, 2);
    if (key === "pts") return num(v, 1);
    if (key === "ip" || key === "k") return num(v, 1);
    if (key === "sem_plus" || key === "hem_plus") return num(v, 0);
    return esc(v);
  }
  var SPOT_SUFFIX = ["th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th"];
  function lineupCell(p) {
    if (p.lineup_status === "not_in_lineup") {
      return '<span class="dfs-out" title="Lineup posted without him.">out</span>';
    }
    var s = p.lineup_spot;
    if (!s) return "-";
    return s + (SPOT_SUFFIX[s % 10] || "th");
  }
  function sortPlayers(list, cols, st) {
    var col = null;
    cols.forEach(function (c) { if (c.key === st.key) col = c; });
    if (!col) return list.slice();
    var out = list.slice();
    out.sort(function (a, b) {
      var va = cellOf(a, st.key), vb = cellOf(b, st.key);
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
  function renderBoard(side) {
    var cols = side === "pit" ? PIT_COLS : HIT_COLS;
    var st = S.sort[side === "pit" ? "pitchers" : "hitters"];
    var list = filterRows(playersOf(side));
    if (!list.length) {
      return '<div class="dfs-note">' +
        (filtersOn()
          ? "No " + (side === "pit" ? "starter" : "hitter") + " matches the current filter."
          : "No projected " + (side === "pit" ? "starters" : "hitters") + " on this slate.") +
        "</div>";
    }
    var sorted = sortPlayers(list, cols, st);
    var total = sorted.length;
    sorted = capRows(sorted);
    var gateShown = sorted.length;
    // The hitter board pages: first 100, then 100 more per click. The pitcher
    // board is ~30 rows and never pages. A filter change resets the page (see
    // filterChanged), so a narrowed board never opens mid-scroll.
    var pager = "";
    if (side === "hit" && sorted.length > S.hitShown) {
      pager = '<div class="dfs-form"><button type="button" class="dfs-btn" id="dfs-more-hit">' +
        "Show 100 more</button>" +
        '<span class="dfs-page-note">Showing the top ' + S.hitShown + " of " + sorted.length +
        " hitters under the current sort.</span></div>";
      sorted = sorted.slice(0, S.hitShown);
    }
    // Both boards render on the Slate tab, so every sort control names the
    // board it belongs to. Without that they share one sort state and a click
    // on a hitter column re-sorts the pitchers by a column they do not have.
    var board = side === "pit" ? "pitchers" : "hitters";
    var head = cols.map(function (c) {
      var on = st.key === c.key;
      // .mlbstats-col-rank on BOTH the header and the cell. site.css keys the
      // frozen-column rules off it: these boards lead with a rank digit rather
      // than the player, so the shared "freeze :first-child" would pin the
      // number and scroll the name away, which is the orphaning the freeze
      // exists to prevent. With the class on both, the rank pins narrow at the
      // left edge and the NAME pins beside it.
      var cls = c.key === "rank" ? "mlbstats-col-rank" : (c.text ? "dfs-l" : "");
      // aria-sort on the th (a columnheader), not the span: on a role=button
      // it is not read (census X06-06).
      return "<th" + (cls ? ' class="' + cls + '"' : "") + ' scope="col" aria-sort="' +
        (on ? (st.asc ? "ascending" : "descending") : "none") +
        '"><span role="button" tabindex="0" data-dfssort="' +
        esc(c.key) + '" data-dfsboard="' + board + '">' +
        (c.term ? gl(c.label, c.term) : esc(c.label)) +
        (on ? (st.asc ? " ▴" : " ▾") : "") + "</span></th>";
    }).join("");
    var body = sorted.map(function (p, i) {
      return "<tr>" + cols.map(function (c) {
        if (c.key === "rank") return '<td class="mlbstats-col-rank">' + (i + 1) + "</td>";
        return '<td' + (c.text ? ' class="dfs-l"' : "") + ">" + fmtCell(p, c.key) + "</td>";
      }).join("") + "</tr>";
    }).join("");
    return methodNote(side) +
      '<div class="dfs-scroll mlbstats-scroll"><table class="dfs-table mlbstats-table"><thead><tr>' + head +
      "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      pager + gateNote(total, gateShown);
  }
  // THE PARK SENTENCE IS DERIVED, NOT TYPED (2026-08-07). It used to read
  // "park factor neutral (no MLB park table on the site yet)" as a string
  // literal, which was true right up until the exporter started resolving MLB
  // parks off the Savant index and then became the most confident wrong line on
  // the page. A disclosure that outlives the thing it describes is worse than
  // none, so this one counts what the payload actually did.
  function parkPhrase() {
    var src = ((S.data || {}).integrity || {}).park_sources || {};
    var applied = (src.savant_mlb || 0) + (src.milb_park_factors || 0);
    var n = 0, k;
    for (k in src) { if (Object.prototype.hasOwnProperty.call(src, k)) n += src[k]; }
    if (!n) return "a park factor";
    if (!applied) return "a park factor that is neutral on every game today";
    if (applied === n) return "the park's run index";
    return "the park's run index on " + applied + " of " + n +
      " games and a neutral park on the rest";
  }
  function methodNote(side) {
    var d = S.data || {};
    var park = parkPhrase();
    var sal = Object.keys(S.salaries).length
      ? (Object.keys(S.salaries).length + " salaries loaded from your import")
      : "No salaries loaded; Pts/$1k is blank until you import them";
    if (side === "pit") {
      return '<div class="dfs-note">Announced probables, one start each. Skill line: the ' +
        "rest-of-season engine; hits, earned runs and home runs allowed carry an opponent-offense " +
        "multiplier and " + esc(park) + ". No relievers: save and hold chances are unknowable " +
        "before first pitch. " + esc(sal) + ".</div>";
    }
    // The anchor prints to two decimals, because the page is prose and the
    // exporter's fourth decimal is not a sentence. The provenance clause
    // follows the payload's OWN receipt: a board built before the anchor was
    // measured carries no `pa_per_start_basis`, and the page must not tell a
    // reader that board was priced off a count it was not priced off.
    var anch = (d.anchors && d.anchors.pa_per_start != null)
      ? Number(d.anchors.pa_per_start).toFixed(2) : "4.02";
    var anchNote = (d.anchors && d.anchors.pa_per_start_basis)
      ? anch + " PA-per-start league anchor, counted off this season's box scores"
      : anch + " PA-per-start anchor";
    return '<div class="dfs-note">Every hitter on a slate club, projected for a game he starts. ' +
      gl("Start", "dfs_start_rate") + ": projected lineup rate (playing time against a " +
      anchNote + "), replaced by the " +
      "posted card. " + gl("Matchup multiplier", "dfs_matchup_multiplier") + ": inverse of " +
      "the innings-weighted opponent pitching index (starter " + gl("SEM+", "sem_plus") +
      " plus " + gl("Bullpen+", "bullpen_plus") + "), times " + esc(park) + ". " +
      esc(sal) + ".</div>";
  }

  // ---- value board ----------------------------------------------------------
  // Points per thousand dollars over everyone the reader has a price for. It is
  // the one board that is meaningless without an import, so the import form
  // lives on it rather than on a tab of its own.
  function renderValue() {
    var priced = ((S.data && S.data.players) || []).filter(function (p) {
      return salaryOf(p) && ptsOf(p) > 0;
    });
    if (!priced.length) {
      return renderSalaries() +
        '<div class="dfs-warn">No salaries loaded, so there is nothing to value. Import them ' +
        "above.</div>";
    }
    priced = filterRows(priced);
    if (!priced.length) {
      return renderSalaries() + filterBarHTML() +
        '<div class="dfs-note">No priced player matches the current filter.</div>';
    }
    priced.sort(function (a, b) { return (valueOf(b) || 0) - (valueOf(a) || 0); });
    var total = priced.length;
    var shown = capRows(priced);
    var rows = shown.map(function (p, i) {
      return '<tr><td class="mlbstats-col-rank">' + (i + 1) + '</td><td class="dfs-l">' +
        teamLogo(p.team) + " " + nameLink(p.mlbam, p.name) +
        ' <span class="dfs-elig">' + esc(eligOf(p).join("/")) + "</span></td><td>" +
        esc((p.is_home ? "vs " : "@ ") + (p.opp || "")) + matchupMark(p.ctx) + "</td><td>" + num(ptsOf(p), 1) +
        "</td><td>" + money(salaryOf(p)) + "</td><td>" + num(valueOf(p), 2) + "</td><td>" +
        (p.side === "hit" && p.start_rate != null ? Math.round(p.start_rate * 100) + "%" : "-") +
        "</td></tr>";
    }).join("");
    return renderSalaries() + filterBarHTML() +
      '<div class="dfs-note">' + gl("Pts/$1k", "dfs_points_per_1k") + ": projected points " +
      "per $1,000 of salary, for every player you priced. Projections are ours; salaries are " +
      "yours. Read it with Start: a high value on a low start rate is a cheap bench bat.</div>" +
      '<div class="dfs-scroll mlbstats-scroll"><table class="dfs-table mlbstats-table">' +
      '<thead><tr><th class="mlbstats-col-rank">#</th>' +
      '<th class="dfs-l">Player</th><th>Game</th><th>Proj</th>' +
      "<th>Salary</th><th>Pts/$1k</th><th>Start</th></tr></thead><tbody>" + rows +
      "</tbody></table></div>" + gateNote(total, shown.length);
  }

  // ---- stacks ---------------------------------------------------------------
  // A stack is the whole club's bats against one arm. Correlation is the reason
  // DFS players build them, and correlation is exactly what our per-player
  // projections do NOT model, so this board ranks the raw sum and says so
  // rather than dressing an independent sum up as a correlated one.
  function renderStacks() {
    var byTeam = {};
    playersOf("hit").forEach(function (p) {
      if (!p.team) return;
      (byTeam[p.team] = byTeam[p.team] || []).push(p);
    });
    var teams = Object.keys(byTeam);
    if (!teams.length) return '<div class="dfs-note">No hitters on this slate.</div>';
    var rows = teams.map(function (tm) {
      var lst = byTeam[tm].slice().sort(function (a, b) { return ptsOf(b) - ptsOf(a); });
      var top4 = lst.slice(0, 4), top5 = lst.slice(0, 5);
      function sum(l, fn) { var t = 0; l.forEach(function (p) { t += fn(p) || 0; }); return t; }
      var sal4 = sum(top4, salaryOf);
      var p0 = lst[0] || {};
      return {
        team: tm, opp: p0.opp, is_home: p0.is_home,
        // The whole stack shares one opponent, so it shares one matchup
        // resolution: carrying p0's ctx through is what lets the Opp index cell
        // say whether that index was measured or fell back to a neutral 100.
        ctx: p0.ctx || null,
        opp_sp: (p0.ctx || {}).opp_sp, opp_pitch: (p0.ctx || {}).opp_pitch,
        // The market's runs for the whole club, which is the number stacking
        // exists to chase. It is a lineup-wide fact, so it belongs on the
        // lineup-wide board rather than only on nine individual rows.
        itt: (p0.ctx || {}).vegas_itt,
        pts4: sum(top4, ptsOf), pts5: sum(top5, ptsOf),
        sal4: sal4, names: top4.map(function (p) { return p.name; })
      };
    }).sort(function (a, b) { return b.pts4 - a.pts4; });
    var shown = capRows(rows);
    var body = shown.map(function (r, i) {
      return '<tr><td class="mlbstats-col-rank">' + (i + 1) + '</td><td class="dfs-l">' + teamLogo(r.team) + " " +
        esc(r.team) + "</td><td>" + esc((r.is_home ? "vs " : "@ ") + (r.opp || "")) + "</td><td>" +
        esc(r.opp_sp || "TBD") + "</td><td>" + num(r.opp_pitch, 0) + matchupMark(r.ctx) +
        "</td><td>" + (r.itt == null ? "-" : num(r.itt, 2)) + "</td><td>" + num(r.pts4, 1) +
        "</td><td>" + num(r.pts5, 1) + "</td><td>" + (r.sal4 ? money(r.sal4) : "-") +
        '</td><td class="dfs-l">' + esc(r.names.join(", ")) + "</td></tr>";
    }).join("");
    return '<div class="dfs-note">Clubs ranked by the summed projection of their four best bats, with ' +
      "the arm they face, that opponent's innings-weighted pitching index (lower is easier) and the " +
      gl("team total", "implied_team_total") + " from a cached odds snapshot. Our points are not " +
      "priced off it. Points are a sum of independent projections: stack correlation is real and " +
      "we do not model it.</div>" +
      '<div class="dfs-scroll mlbstats-scroll"><table class="dfs-table mlbstats-table">' +
      '<thead><tr><th class="mlbstats-col-rank">#</th>' +
      '<th class="dfs-l">Club</th><th>Game</th><th>Opp SP</th>' +
      "<th>Opp index</th><th>Team total</th><th>Top 4</th><th>Top 5</th><th>Top 4 salary</th>" +
      '<th class="dfs-l">Bats</th></tr></thead><tbody>' + body + "</tbody></table></div>" +
      gateNote(rows.length, shown.length);
  }

  // ---- salaries surface -----------------------------------------------------
  function renderSalaries() {
    var meta = S.salaryMeta, rep = S.importReport;
    var have = Object.keys(S.salaries).length;
    var block =
      '<div class="dfs-note">Salaries come from you and stay in this browser; no salary feed is ' +
      "scraped or republished. Drop your contest site's player export below or paste it. Required " +
      "columns: Name, Salary. Optional: Position (wins over ours), TeamAbbrev.</div>" +
      '<div class="dfs-form">' +
      '<label class="dfs-field"><span>CSV file</span><input type="file" id="dfs-csv-file" accept=".csv,text/csv,text/plain"></label>' +
      '<button type="button" class="dfs-btn" id="dfs-sal-clear">Clear salaries</button>' +
      "</div>" +
      '<textarea id="dfs-csv-text" class="dfs-textarea" rows="6" placeholder="Name,Position,Salary,TeamAbbrev"></textarea>' +
      '<div class="dfs-form"><button type="button" class="dfs-btn dfs-btn-go" id="dfs-csv-go">Import pasted text</button></div>';
    return block + salaryStatus();
  }
  // Split out of renderSalaries so the OPTIMIZER can show it too. Importing
  // from the optimizer tab used to make the form and the result vanish
  // together the moment the import succeeded: the reader pressed Import and
  // got no confirmation that anything had happened at all.
  function salaryStatus() {
    var meta = S.salaryMeta, rep = S.importReport;
    var have = Object.keys(S.salaries).length;
    if (rep && !rep.ok) return '<div class="dfs-warn">' + esc(rep.msg) + "</div>";
    if (rep && rep.ok) {
      return '<div class="dfs-ok">Read ' + rep.read + " priced rows, matched " + rep.matched +
        " to the slate." + (rep.unmatched_n ? " " + rep.unmatched_n + " did not match: " +
          esc(rep.unmatched.join(", ")) + (rep.unmatched_n > rep.unmatched.length ? ", and more." : "") : "") +
        "</div>";
    }
    if (have) {
      return '<div class="dfs-ok">' + have + " salaries stored for " +
        esc((meta && meta.slate_date) || "this slate") + ".</div>";
    }
    return "";
  }

  // ---- optimizer ------------------------------------------------------------
  function slotAccepts(slot, elig) {
    var accepts = slot.accepts || [slot.slot];
    for (var i = 0; i < accepts.length; i++) {
      if (elig.indexOf(accepts[i]) >= 0) return true;
      // UTIL takes any position player. A pitcher never fills a hitter slot.
      if (accepts[i] === "UTIL" && elig.indexOf("P") < 0) return true;
    }
    return false;
  }
  function candidatesFor(slot, pool) {
    return pool.filter(function (p) { return slotAccepts(slot, eligOf(p)); });
  }
  function optimizerPool(tpl) {
    var out = [];
    ((S.data && S.data.players) || []).forEach(function (p) {
      var sal = salaryOf(p);
      if (!sal || sal <= 0) return;
      if (ptsOf(p) <= 0) return;
      if (p.side === "hit" && (p.start_rate || 0) < S.minStart) return;
      // The board filter narrows the pool too (2026-08-16): a reader who has
      // filtered the slate down to one club is asking the solver about that
      // club, and a lineup drawn from rows he deliberately hid would be a
      // lineup the boards cannot explain. The panel says so out loud.
      if (!passFilter(p)) return;
      out.push(p);
    });
    return out;
  }
  function teamCounts(roster) {
    var c = {};
    roster.forEach(function (p) { if (p) c[p.team] = (c[p.team] || 0) + 1; });
    return c;
  }
  function feasible(roster, tpl) {
    var filled = roster.filter(Boolean);
    var total = 0, seen = {}, games = {};
    for (var i = 0; i < filled.length; i++) {
      var key = filled[i].mlbam + "|" + filled[i].side;
      if (seen[key]) return false;
      seen[key] = 1;
      total += salaryOf(filled[i]) || 0;
      games[filled[i].game_pk] = 1;
    }
    if (total > capOf(tpl)) return false;
    var counts = teamCounts(filled);
    var lim = maxPerTeamOf(tpl);
    for (var t in counts) if (counts[t] > lim) return false;
    if (S.avoidOpp) {
      var pitOpp = {};
      filled.forEach(function (p) { if (p.side === "pit") pitOpp[p.opp] = 1; });
      for (var j = 0; j < filled.length; j++) {
        if (filled[j].side === "hit" && pitOpp[filled[j].team]) return false;
      }
    }
    if (roster.every(Boolean) && Object.keys(games).length < (tpl.min_games || 1)) return false;
    return true;
  }
  function capOf(tpl) { return S.cap != null ? S.cap : (tpl.cap || 50000); }
  function maxPerTeamOf(tpl) { return S.maxPerTeam != null ? S.maxPerTeam : (tpl.max_per_team || 5); }
  function total(roster, fn) {
    var t = 0;
    roster.forEach(function (p) { if (p) t += fn(p) || 0; });
    return t;
  }
  // WHAT THE UNFILLED SLOTS WILL COST, AT LEAST. Two lower bounds, and the
  // larger of the two is still a lower bound, so reserving it can never rule
  // out a lineup that exists:
  //
  //   per slot   - every remaining slot costs at least the cheapest unused
  //                player who can fill it,
  //   distinct   - the remaining slots get DISTINCT players drawn from the
  //                union of their pools, so together they cost at least the
  //                sum of the n cheapest players in that union.
  //
  // The second bound is the one that matters and the one the first pass of
  // this solver was missing. Three outfield slots share one pool, so summing
  // the per-slot minimum reserved the cheapest outfielder three times over.
  // The build then walked into a budget it could not finish, and the page told
  // the reader no lineup satisfied his constraints while a lineup costing 68%
  // of his cap sat in the pool.
  function reserveFor(rest, cands, used) {
    var perSlot = 0, union = {}, i, j, key, sal;
    for (i = 0; i < rest.length; i++) {
      var list = cands[rest[i]], lo = Infinity;
      for (j = 0; j < list.length; j++) {
        key = list[j].mlbam + "|" + list[j].side;
        if (used[key]) continue;
        sal = salaryOf(list[j]) || 0;
        if (sal < lo) lo = sal;
        union[key] = sal;
      }
      if (lo === Infinity) return Infinity;   // nothing left that can fill it
      perSlot += lo;
    }
    var vals = Object.keys(union).map(function (k) { return union[k]; })
      .sort(function (a, b) { return a - b; });
    if (vals.length < rest.length) return Infinity;
    var distinct = 0;
    for (i = 0; i < rest.length; i++) distinct += vals[i];
    return Math.max(perSlot, distinct);
  }
  // GREEDY BUILD. Slots are filled scarcest first (a catcher pool of eight is
  // where a lineup gets stuck, not the outfield), and each pick has to leave
  // enough money on the table for the cheapest legal filling of what is left.
  // That reservation is the difference between a solver that fills nine slots
  // and one that spends the cap on eight and reports failure.
  //
  // `byCost` runs the same build cheapest-first instead of best-first. It is
  // the feasibility pass: a lower bound is a bound, not a plan, so a points
  // ordering can still dead-end, and "no lineup exists" is a claim this page
  // should only make after trying to build the cheapest one there is.
  function greedy(tpl, pool, byCost) {
    var slots = tpl.slots.map(function (s, i) { return { s: s, i: i }; });
    var cands = slots.map(function (x) {
      var list = candidatesFor(x.s, pool);
      return byCost
        ? list.sort(function (a, b) { return (salaryOf(a) || 0) - (salaryOf(b) || 0); })
        : list.sort(function (a, b) { return ptsOf(b) - ptsOf(a); });
    });
    var order = slots.map(function (x, i) { return i; })
      .sort(function (a, b) { return cands[a].length - cands[b].length; });
    var roster = slots.map(function () { return null; });
    var used = {};
    for (var oi = 0; oi < order.length; oi++) {
      var si = order[oi];
      var reserve = reserveFor(order.slice(oi + 1), cands, used);
      if (!isFinite(reserve)) return null;
      var spent = total(roster, salaryOf);
      var budget = capOf(tpl) - spent - reserve;
      var best = null;
      for (var c = 0; c < cands[si].length; c++) {
        var p = cands[si][c];
        var key = p.mlbam + "|" + p.side;
        if (used[key]) continue;
        if ((salaryOf(p) || 0) > budget) continue;
        var trial = roster.slice();
        trial[si] = p;
        if (!feasible(trial, tpl)) continue;
        best = p;
        break;                       // candidates are already in pick order
      }
      if (!best) return null;
      roster[si] = best;
      used[best.mlbam + "|" + best.side] = 1;
    }
    return roster;
  }
  // LOCAL SEARCH. Single swaps to a local optimum, then pairwise swaps, then
  // back to single swaps if the pair pass moved anything. Candidate lists are
  // truncated by points so the pair pass stays inside a frame.
  function improve(roster, tpl, pool) {
    var slots = tpl.slots;
    var cands = slots.map(function (s) {
      return candidatesFor(s, pool).sort(function (a, b) { return ptsOf(b) - ptsOf(a); }).slice(0, 120);
    });
    function score(r) { return total(r, ptsOf); }
    var guard = 0;
    for (var pass = 0; pass < 8 && guard < 40; pass++) {
      guard++;
      var moved = false;
      for (var i = 0; i < slots.length; i++) {
        var bestGain = 0, bestP = null;
        var base = score(roster);
        for (var c = 0; c < cands[i].length; c++) {
          var p = cands[i][c];
          if (roster[i] && p.mlbam === roster[i].mlbam && p.side === roster[i].side) continue;
          var trial = roster.slice();
          trial[i] = p;
          if (!feasible(trial, tpl)) continue;
          var gain = score(trial) - base;
          if (gain > bestGain) { bestGain = gain; bestP = p; }
        }
        if (bestP) { roster[i] = bestP; moved = true; }
      }
      if (!moved) {
        var pairMoved = false;
        for (var a = 0; a < slots.length && !pairMoved; a++) {
          for (var b = a + 1; b < slots.length && !pairMoved; b++) {
            var base2 = score(roster);
            var la = cands[a].slice(0, 30), lb = cands[b].slice(0, 30);
            var bg = 0, pa = null, pb = null;
            for (var x = 0; x < la.length; x++) {
              for (var y = 0; y < lb.length; y++) {
                var t2 = roster.slice();
                t2[a] = la[x]; t2[b] = lb[y];
                if (!feasible(t2, tpl)) continue;
                var g2 = score(t2) - base2;
                if (g2 > bg) { bg = g2; pa = la[x]; pb = lb[y]; }
              }
            }
            if (pa && pb) { roster[a] = pa; roster[b] = pb; pairMoved = true; }
          }
        }
        if (!pairMoved) break;
      }
    }
    return roster;
  }
  function optimize() {
    liveData();
    var tpl = template();
    if (!tpl) return { ok: false, msg: "No roster template is available in the payload." };
    var pool = optimizerPool(tpl);
    if (!pool.length) {
      // The Salaries tab this used to name was folded into Value; the import
      // form also renders on this tab, so the line points at neither.
      return { ok: false, msg: "No player in the pool has both a salary and a projection. " +
                              "Import salaries first." };
    }
    var roster = greedy(tpl, pool, false);
    if (!roster) roster = greedy(tpl, pool, true);   // cheapest-first feasibility pass
    if (!roster) {
      return { ok: false, msg: "No lineup satisfies these constraints (best-first and " +
                              "cheapest-first builds both failed). Raise the cap or the per-team " +
                              "limit, lower the minimum start rate, or import more salaries." };
    }
    roster = improve(roster, tpl, pool);
    return { ok: true, tpl: tpl, roster: roster,
             pts: total(roster, ptsOf), salary: total(roster, salaryOf),
             pool: pool.length };
  }
  function renderOptimizer() {
    var tpl = template();
    if (!tpl) return '<div class="dfs-note">The payload carries no roster templates.</div>';
    var haveSal = Object.keys(S.salaries).length;
    var controls =
      '<div class="dfs-form">' +
      '<label class="dfs-field"><span>Roster</span><select id="dfs-tpl">' +
      templates().map(function (t) {
        return '<option value="' + esc(t.id) + '"' + (t.id === tpl.id ? " selected" : "") + ">" +
          esc(t.label) + "</option>";
      }).join("") + "</select></label>" +
      '<label class="dfs-field"><span>Salary cap</span><input type="number" id="dfs-cap" value="' +
        capOf(tpl) + '" min="1000" step="500"></label>' +
      '<label class="dfs-field"><span>Max per team</span><input type="number" id="dfs-maxteam" value="' +
        maxPerTeamOf(tpl) + '" min="1" max="10"></label>' +
      '<label class="dfs-field"><span>Min start rate %</span><input type="number" id="dfs-minstart" value="' +
        Math.round(S.minStart * 100) + '" min="0" max="100" step="5"></label>' +
      '<label class="dfs-check"><input type="checkbox" id="dfs-avoidopp"' + (S.avoidOpp ? " checked" : "") +
        "> No hitters facing my starter</label>" +
      '<button type="button" class="dfs-btn dfs-btn-go" id="dfs-run">Optimize</button>' +
      "</div>";
    var intro = '<div class="dfs-note">Maximizes projected points under your constraints: a greedy ' +
      "build plus local search over our projections and your salaries. The pool honors the Slate " +
      "and Value filter bar: filtering shrinks the pool.</div>" +
      (filtersOn()
        ? '<div class="dfs-warn">The slate filter is active, so the solver sees only the ' +
          "filtered pool.</div>"
        : "");
    if (!haveSal) {
      // The importer comes with the message. Telling a reader what is missing
      // and then making him hunt for the control that fixes it is half a
      // feature.
      return intro + controls + '<div class="dfs-warn">No salaries loaded. Import your contest ' +
        "site's prices below.</div>" + renderSalaries();
    }
    var res = S.lineup;
    var head = intro + controls + salaryStatus();
    if (!res) return head;
    if (!res.ok) return head + '<div class="dfs-warn">' + esc(res.msg) + "</div>";
    var rows = res.roster.map(function (p, i) {
      var slot = res.tpl.slots[i];
      return "<tr><td>" + esc(slot.slot) + '</td><td class="dfs-l">' + teamLogo(p.team) + " " +
        nameLink(p.mlbam, p.name) + "</td><td>" + esc((p.is_home ? "vs " : "@ ") + (p.opp || "")) +
        "</td><td>" + num(ptsOf(p), 1) + "</td><td>" + money(salaryOf(p)) + "</td><td>" +
        num(valueOf(p), 2) + "</td></tr>";
    }).join("");
    var cap = capOf(res.tpl);
    var summary = '<div class="dfs-summary"><span><b>' + num(res.pts, 1) + "</b> projected points</span>" +
      "<span><b>" + money(res.salary) + "</b> of " + money(cap) + " used</span>" +
      "<span><b>" + money(cap - res.salary) + "</b> left</span>" +
      "<span>" + res.pool + " players in the pool</span></div>";
    return head + summary +
      '<div class="dfs-scroll mlbstats-scroll"><table class="dfs-table mlbstats-table"><thead><tr><th>Slot</th>' +
      '<th class="dfs-l">Player</th><th>Game</th>' +
      "<th>Proj</th><th>Salary</th><th>Pts/$1k</th></tr></thead><tbody>" + rows +
      "</tbody></table></div>";
  }

  // ---- slate header ---------------------------------------------------------
  function renderSlate() {
    var d = S.data || {};
    var games = d.games || [];
    if (!games.length) return offBoardNote();
    var cards = games.map(function (g) {
      function sideLine(s) {
        var pp = (s || {}).probable;
        return '<div class="dfs-slate-row"><span class="dfs-slate-team">' + teamLogo((s || {}).org) + " " +
          esc((s || {}).org || "") +
          ((s || {}).lineup_posted ? ' <span class="dfs-conf">card</span>' : "") +
          ((s || {}).vegas_itt != null
            ? ' <span class="dfs-itt">' + num(s.vegas_itt, 2) + "</span>" : "") +
          '</span><span class="dfs-slate-sp">' +
          (pp ? esc(pp.name) : "no probable posted") + "</span></div>";
      }
      var v = g.vegas;
      // A refused market is not a missing one. The exporter found odds for
      // this game and threw them out because they were read after first
      // pitch, and the card says so rather than looking like a quiet miss.
      var refused = !v && g.vegas_refused === "in_game"
        ? " · no total: the odds we hold were taken after first pitch" : "";
      return '<div class="dfs-slate-card">' + sideLine(g.away) + sideLine(g.home) +
        '<div class="dfs-slate-meta">' + esc(g.venue || "") + parkMark(g) +
        (v ? " · total " + num(v.total, 1) : "") + refused + "</div></div>";
    }).join("");
    return '<div class="dfs-slate">' + cards + "</div>" + offBoardNote() + vegasNote();
  }
  // Every park source is a different claim and the card says which one it is.
  // "neutral" alone used to cover all of them, which meant an average park, a
  // neutral-site game and a lookup that found nothing read identically.
  var PARK_MARK = {
    none: " · park neutral (no factor)",
    neutral_site: " · neutral site, park factor not applied",
    no_factor_for_park: " · park neutral (this park has no factor yet)"
  };
  function parkMark(g) {
    var src = String(g.park_source || "");
    if (PARK_MARK[src]) return PARK_MARK[src];
    // A factor outside the plausible range was clamped by the exporter and the
    // source carries the suffix. It is still applied, so the number is shown,
    // but a clamped value must never pass for a measured one.
    if (src.indexOf("_out_of_range") > 0) {
      return " · park " + num(g.park_run_pf, 2) + " (out of range, clamped)";
    }
    if (src === "savant_mlb" || src === "milb_park_factors") {
      return " · park " + num(g.park_run_pf, 2);
    }
    return " · park neutral";
  }
  // The market legs are read from odds snapshots the betting module already
  // pays for. When there is no snapshot the totals are simply absent, and the
  // page says why rather than leaving a column of dashes unexplained.
  //
  // THE COPY HERE AVOIDS BETTING VOCABULARY ON PURPOSE, and the guard in
  // test_fantasy_split enforces it. A DFS board showing a market-implied team
  // total is standard fantasy context; a DFS board that has started talking
  // like a betting slip is a fantasy page somebody has begun treating as a
  // betting product. The number is the same either way, so the plain-English
  // description is strictly better: "each side's price, with the house margin
  // taken out" is what a de-vigged two-way market IS.
  function vegasNote() {
    var d = S.data || {}, src = d.vegas_source || {}, integ = d.integrity || {};
    // Interpolated from the payload's own refusal count, never typed.
    var nLive = Number(src.n_rejected_in_game || 0);
    var liveLine = nLive > 0
      ? " " + nLive + " " + plural(nLive, "game", "games") + " on this slate had already started when " +
        "that snapshot was taken; " + plural(nLive, "its", "their") + " in-game odds are not shown."
      : "";
    if (integ.vegas_games) {
      return '<div class="dfs-note">' + gl("Team totals", "implied_team_total") + " are the " +
        "market's: the posted game total split by each side's price with the house margin removed, " +
        "from an odds snapshot taken " + esc(src.captured_at || "earlier") +
        ". Nothing on this page is priced off them." + liveLine + "</div>";
    }
    if (!src.reason) return "";
    return '<div class="dfs-note">No Vegas team totals on this slate: ' + esc(src.reason) +
      ". We read cached odds snapshots and never fetch our own, so no total is estimated.</div>";
  }

  // ---- render ---------------------------------------------------------------
  function renderSection() {
    var r = root();
    if (!r) return;
    if (!S.error) liveData();
    var d = S.data || {};
    var html;
    if (S.error) {
      // The payload never arrived. The tabs are still wired, so the reader gets
      // a control that responds instead of four buttons that do nothing, and
      // the same honest message under every one of them.
      html = pxState("failed", "<strong>Slate failed to load.</strong> " +
        esc(S.error) + ". The daily build may be mid-run. Every tab, the optimizer included, " +
        'needs the slate. <button type="button" id="dfs-retry" ' +
        'class="dfs-btn">Retry</button>', "dfs-error");
    } else if (d.empty_reason) {
      html = emptyPanel(d) + (d.empty_reason_kind === "slate_closed" ? offBoardNote() : "");
    } else if (S.section === "value") html = renderValue();
    else if (S.section === "stacks") html = renderStacks();
    else if (S.section === "optimizer") html = renderOptimizer();
    else {
      // ONE filter bar above BOTH boards: the two tables share a slate, so a
      // filter that only narrowed one of them would leave the page disagreeing
      // with itself about who is on it.
      html = renderSlate() + integrityPanel() + filterBarHTML() +
        '<h3 class="dfs-h">Probable starters</h3>' + renderBoard("pit") +
        '<h3 class="dfs-h">Hitters</h3>' + renderBoard("hit");
    }
    // The shell gives /redraft/ a bar for its scoring selector and gives this
    // page none, so the contest-format selector rides at the top of the
    // section when there is nowhere else to put it.
    if (!scoringBar() && !d.empty_reason && !S.error) html = selectorHTML() + html;
    // The stale banner rides ABOVE everything, on every tab including the
    // optimizer and the empty states. A kept slate is a fact about every number
    // under it, not a footnote on one board.
    if (!S.error) html = staleBanner() + html;
    r.innerHTML = html;
    var rb = r.querySelector("#dfs-retry");
    if (rb) rb.addEventListener("click", boot);
    wireSection(r);
    if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(r);
  }
  function wireSection(r) {
    wireSelector(r);
    wireFilterBar(r);
    var more = r.querySelector ? r.querySelector("#dfs-more-hit") : null;
    if (more) more.addEventListener("click", function () {
      S.hitShown += HIT_PAGE;
      renderSection();
    });
    r.querySelectorAll("[data-dfssort]").forEach(function (h) {
      function fire() {
        var st = S.sort[h.getAttribute("data-dfsboard") || "pitchers"];
        if (!st) return;
        var k = h.getAttribute("data-dfssort");
        if (st.key === k) st.asc = !st.asc;
        // Ascending on first click for the columns where small is the answer a
        // reader wants first: the names, and the batting order (1st, not 9th).
        else { st.key = k; st.asc = (k === "name" || k === "opp" || k === "opp_sp" || k === "lineup"); }
        renderSection();
        writeHash();
      }
      h.addEventListener("click", fire);
      h.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        fire();
      });
    });
    var go = r.querySelector("#dfs-csv-go");
    if (go) go.addEventListener("click", function () {
      var ta = r.querySelector("#dfs-csv-text");
      importSalaries(ta ? ta.value : "");
      renderSection();
    });
    var file = r.querySelector("#dfs-csv-file");
    if (file) file.addEventListener("change", function () {
      var f = file.files && file.files[0];
      if (!f || typeof FileReader === "undefined") return;
      var fr = new FileReader();
      fr.onload = function () { importSalaries(String(fr.result || "")); renderSection(); };
      fr.readAsText(f);
    });
    var clr = r.querySelector("#dfs-sal-clear");
    if (clr) clr.addEventListener("click", function () {
      S.salaries = {}; S.salaryMeta = null; S.importReport = null; S.lineup = null;
      saveSalaries();
      renderSection();
    });
    var tplSel = r.querySelector("#dfs-tpl");
    if (tplSel) tplSel.addEventListener("change", function () {
      S.template = tplSel.value;
      var t = template();
      // A template switch resets the numbers it owns; keeping a 50,000 cap on a
      // 35,000 roster is the sort of stale state that produces a lineup nobody
      // can enter.
      S.cap = null; S.maxPerTeam = null;
      if (t && t.scoring) S.system = t.scoring;
      S.lineup = null;
      saveSettings();
      renderSelector();
      renderSection();
    });
    bindNum(r, "#dfs-cap", function (v) { S.cap = Math.max(1000, v); });
    bindNum(r, "#dfs-maxteam", function (v) { S.maxPerTeam = Math.max(1, Math.min(10, v)); });
    bindNum(r, "#dfs-minstart", function (v) { S.minStart = Math.max(0, Math.min(100, v)) / 100; });
    var av = r.querySelector("#dfs-avoidopp");
    if (av) av.addEventListener("change", function () {
      S.avoidOpp = !!av.checked; S.lineup = null; saveSettings(); renderSection();
    });
    var run = r.querySelector("#dfs-run");
    if (run) run.addEventListener("click", function () {
      S.lineup = optimize();
      renderSection();
    });
  }
  function bindNum(r, sel, set) {
    var n = r.querySelector(sel);
    if (!n) return;
    n.addEventListener("change", function () {
      var v = parseInt(n.value, 10);
      if (isNaN(v)) return;
      set(v);
      S.lineup = null;
      saveSettings();
      renderSection();
      var again = root() && root().querySelector(sel);
      if (again && again.focus) again.focus();
    });
  }
  function selectorHTML() {
    var cat = (S.data && S.data.scoring_catalog) || [];
    if (!cat.length) return "";
    return '<div class="dfs-scorebar"><span class="dfs-score-lbl">Contest scoring</span>' +
      cat.map(function (c) {
        return '<button type="button" class="dfs-scorebtn' + (c.id === S.system ? " active" : "") +
          '" data-dfssystem="' + esc(c.id) + '">' + esc(c.label) + "</button>";
      }).join("") +
      '<span class="dfs-score-note">' + esc((S.data && S.data.scoring_note) || "") + "</span></div>";
  }
  function wireSelector(scope) {
    scope.querySelectorAll("[data-dfssystem]").forEach(function (b) {
      b.addEventListener("click", function () {
        S.system = b.getAttribute("data-dfssystem");
        S.lineup = null;
        saveSettings();
        renderSelector();
        renderSection();
        writeHash();
      });
    });
  }
  function renderSelector() {
    var bar = scoringBar();
    if (!bar) return;                  // the inline copy in renderSection covers it
    bar.innerHTML = selectorHTML();
    wireSelector(bar);
  }
  function syncTabs() {
    tabs().forEach(function (b) {
      var on = tabKey(b) === S.section;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }
  // Idempotent: a Retry after a failed load runs the boot path a second time,
  // and a second listener on the same button would render the section twice
  // per click.
  function wireTabs() {
    tabs().forEach(function (b) {
      if (b.getAttribute("data-dfswired")) return;
      b.setAttribute("data-dfswired", "1");
      b.addEventListener("click", function () {
        S.section = tabKey(b);
        syncTabs();
        renderSection();
        writeHash();
      });
    });
  }

  // ---- hash router ----------------------------------------------------------
  //   #section=slate|value|stacks|optimizer
  //   #sys=<scoring id from the served catalog>
  //   #q= #pos= #team=   the filter bar (2026-08-16); pos and team validate
  //                      against the served pool (pos through eligOf, so the
  //                      reader's own CSV positions count), q is a decoded
  //                      substring
  // The canonical names are the shell nav's own attribute values, because
  // syncTabs compares the two directly. The pre-split names are accepted as
  // aliases so a link written against an earlier build still lands somewhere
  // real.
  var SECTIONS = ["slate", "value", "stacks", "optimizer", "pitchers", "hitters", "salaries"];
  var SECTION_ALIAS = { pitchers: "slate", hitters: "slate", salaries: "value" };
  var LAST_HASH = null;
  function hashParam(h, key, pat) {
    var m = new RegExp("(?:^#|[#&])" + key + "=(" + pat + ")(?:&|$)").exec(h || "");
    return m ? m[1] : null;
  }
  // EVERY CALLER REWRITES THE ADDRESS BAR AFTERWARDS. An invalid #section was
  // already refused by the alternation, so the page rendered the default - but
  // the address bar kept the bad value until the reader clicked a tab, so a
  // shared link named a section that does not exist. An ALIASED section is not
  // canonical either ("#section=pitchers" resolves to slate and should say so),
  // and since the card joined the hash there are more ways to be off canonical
  // than one return flag could name. So normalize unconditionally, the way
  // redraft.js and dynasty.js do.
  function readHash() {
    var h = hostHash();
    var s = hashParam(h, "section", SECTIONS.join("|"));
    if (s) S.section = SECTION_ALIAS[s] || s;
    var sys = hashParam(h, "sys", "[A-Za-z0-9_]+");
    var known = ((S.data && S.data.scoring_catalog) || []).filter(function (c) { return c.id === sys; });
    if (sys && known.length) S.system = sys;
    // The filter half, validated against the served pool. Read unconditionally
    // so a hash WITHOUT the key clears the filter (Back button undoes one),
    // and reset the hitter page whenever the filter state moves.
    var vocab = filterVocab();
    var q = hashParam(h, "q", "[^&]+");
    var nq = q ? decodeQ(q).slice(0, 40) : "";
    var pos = hashParam(h, "pos", "[A-Za-z0-9]{1,4}");
    var npos = (pos && vocab.pos.indexOf(pos.toUpperCase()) >= 0) ? pos.toUpperCase() : null;
    var team = hashParam(h, "team", "[A-Za-z]{2,3}");
    var nteam = (team && vocab.team.indexOf(team.toUpperCase()) >= 0) ? team.toUpperCase() : null;
    if (nq !== S.q || npos !== S.pos || nteam !== S.team) {
      // A pool change through the address bar is still a pool change: the
      // page resets and a solved lineup goes stale, same as filterChanged.
      S.hitShown = HIT_PAGE;
      S.lineup = null;
    }
    S.q = nq; S.pos = npos; S.team = nteam;
    S.player = hashParam(h, "player", "\\d+");
  }
  // The BOARD half, card left out, so onHashChange can tell a card open from a
  // real board change and not repaint the slate underneath it.
  function boardHash() {
    var parts = ["section=" + S.section];
    var def = ((S.data && S.data.scoring_catalog) || []).filter(function (c) { return c.default; })[0];
    if (S.system && S.system !== (def ? def.id : "dk")) parts.push("sys=" + S.system);
    if (S.q) parts.push("q=" + encodeURIComponent(S.q));
    if (S.pos) parts.push("pos=" + S.pos);
    if (S.team) parts.push("team=" + S.team);
    return "#" + parts.join("&");
  }
  function cardHash(mlbam) { return hostLink(boardHash() + "&player=" + mlbam); }
  function writeHash() {
    LAST_HASH = S.player ? (boardHash() + "&player=" + S.player) : boardHash();
    hostWrite(LAST_HASH);
  }
  function onHashChange() {
    if (!S.data && !S.error) return;
    if (hostHash() === LAST_HASH) return;
    var before = boardHash();
    readHash();
    if (boardHash() !== before) { renderSelector(); syncTabs(); renderSection(); }
    syncCard();
    writeHash();
  }
  hostRoute(onHashChange);

  // ---- player card ----------------------------------------------------------
  // The card is a lookup into the SEASON corpus (data/fantasy.json), which this
  // module does not read for its own boards and must not start reading: its
  // sidecar is the slate. On /fantasy/ the coordinator already holds that
  // corpus for Redraft and Dynasty, so the card costs this page one shared
  // load, taken on the first card a reader opens and never on a reader who
  // opens none.
  //
  // NO SCORE LINE HERE. The four-format league score is the Redraft port, which
  // test_fantasy_split drives against the frozen assets/fantasy.js; a copy in
  // this file would be a third implementation nobody is comparing, and the
  // season points total is not what a DFS reader came for anyway. The card
  // renders every other block and simply omits that one.
  function card() { return window.EEPHUS_FANTASY_CARD || null; }
  function cardable() { return !!(host() && card()); }
  // THE LINKS SIDECAR IS READ ON A CARD, NOT AT BOOT (audit QREP15).
  // player_links (about 1.9 MB) feeds only the card's outbound "Full MLB card"
  // link, so it is asked for the first time a card opens; until it lands the
  // card says nothing about that link rather than "No MLB card yet".
  var LINKS_ASKED = false, LINKS_DONE = false;
  function wantLinks() {
    if (LINKS || LINKS_ASKED || !S.player || !(window.EEPHUS_HUB && EEPHUS_HUB.links)) return;
    LINKS_ASKED = true;
    EEPHUS_HUB.links().then(function (L) { LINKS = L || null; LINKS_DONE = true; syncCard(); },
                            function () { LINKS_DONE = true; syncCard(); });
  }
  function syncCard() {
    var C = card();
    if (!C) return;
    if (S.player) { ensureCorpus(); wantLinks(); }
    C.sync(S.player);
  }
  function attachCard() {
    var C = card();
    if (!C) return;
    C.attach({
      payload: function () { return CORPUS; },
      links: function () { return LINKS; },
      linksPending: function () { return LINKS_ASKED && !LINKS_DONE; },
      onClose: function () { S.player = null; writeHash(); }
    });
  }
  // Lazy and once. A failed corpus load leaves the card closed rather than
  // opening an overlay with nothing in it, and the name still carries the
  // reader somewhere: the hash keeps the id, so a retry is a reload.
  function ensureCorpus() {
    if (CORPUS || CORPUS_PENDING || !host()) return;
    CORPUS_PENDING = true;
    host().corpus().then(function (d) {
      CORPUS = d || null;
      syncCard();
    }).catch(function () { CORPUS_PENDING = false; });
  }

  // ---- boot -----------------------------------------------------------------
  // A failed load used to paint one red box and stop, leaving the shell's four
  // section tabs on screen with nothing bound to them: every click was a dead
  // control. The tabs get wired either way now, and renderSection carries the
  // message.
  function errorState(msg) {
    S.error = String(msg || "the payload did not load");
    S.data = null;
    readHash(); writeHash();
    wireTabs(); syncTabs(); renderSection();
  }
  function onData(d) {
    S.error = null;
    S.data = lockStarted(d || {}, Date.now());
    loadSettings();
    loadSalaries();
    var t = template();
    if (t && !S.template) S.template = t.id;
    if (!S.data.scoring_catalog) S.data.scoring_catalog = [];
    var def = S.data.scoring_catalog.filter(function (c) { return c.default; })[0];
    if (!S.system && def) S.system = def.id;
    var b = bannerEl();
    if (b) {
      // The stage phrase is the page's only conversion route, so it is a link.
      b.innerHTML = '<div class="dfs-asof">' + esc(S.data.slate_date || "") + " · " +
        // n_players is the SERVED count since the 2026-09-11 priced/served
        // split, so the label says players, not players priced.
        (S.data.n_games || 0) + " games · " + (S.data.n_players || 0) +
        ' players · <a class="dfs-name-link" href="/diamond/">Diamond preview</a>' +
        ", free while we build" +
        // Same predicate as the banner, so the header chip and the banner can
        // never disagree about whether the board is today's.
        (staleInfo() ? ' · <span class="dfs-stale-chip">old slate</span>' : "") +
        "</div>";
    }
    readHash();
    attachCard();
    renderSelector(); wireTabs(); syncTabs(); renderSection();
    writeHash();
    syncCard();
    if (!LINKS && !cardable() && window.EEPHUS_HUB && EEPHUS_HUB.links) {
      // Off /fantasy/ (no card host) the boards' names fall back to the
      // /projections/ link, which needs the sidecar at boot. On /fantasy/ every
      // name opens the card, which asks for it on open (wantLinks).
      EEPHUS_HUB.links().then(function (L) { LINKS = L || null; renderSection(); });
    }
  }
  // The lamp loader goes up before the payload is asked for, so a held or slow
  // load shows the loading kind rather than an empty root.
  function boot() {
    var r = root();
    if (r) r.innerHTML = pxState("loading", "Loading the DFS slate.");
    load(DATA_URL).then(onData).catch(function (e) { errorState(String(e && e.message || e)); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  // Membership resolves after first paint; re-render when the answer changes
  // (2026-08-16). Guarded on S.data: nothing to cap before the payload.
  (function () {
    var D = gate();
    if (D && D.onEntitlement) D.onEntitlement(function () { if (S.data) renderSection(); });
  })();

  // ---- module styles (theme tokens only) ------------------------------------
  var css = document.createElement("style");
  css.textContent = [
    // Wide boards scroll inside their own box. The nine-column slate and stacks
    // tables were pushing the whole document sideways at phone widths.
    // THE SHARED DIALECT. Every board also carries .mlbstats-scroll /
    // .mlbstats-table so it inherits the site-wide sticky header and the frozen
    // identity column out of assets/site.css. These tables sit on the page
    // background, which is the fill those rules already use, so nothing needs
    // correcting here beyond the rank-class rename noted further down.
    ".dfs-scroll{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}",
    ".dfs-table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}",
    ".dfs-table th{text-align:right;font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em;padding:6px 8px;border-bottom:1px solid var(--border)}",
    ".dfs-table td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--border-light);color:var(--text-primary)}",
    ".dfs-table th.dfs-l,.dfs-table td.dfs-l{text-align:left}",
    // THE RANK CELL'S CLASS CHANGED. It used to be .dfs-rk; it is now the
    // shared .mlbstats-col-rank, because site.css carries a rule that UNDOES
    // the frozen first column on any .dfs-table whose first cell is .dfs-rk
    // (freezing a rank digit pins the number and scrolls the name away).
    // Stamping the shared rank class on the header AND the cell is the
    // module-side fix that rule's comment asks for: the rank-rail rules take
    // over, the digit pins narrow at the left edge and the NAME pins beside it.
    // The muted colour is re-declared here so the rename costs nothing.
    ".dfs-table td.mlbstats-col-rank{color:var(--text-tertiary)}",
    ".dfs-table th [role=button]{cursor:pointer}",
    ".dfs-filterbar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:8px 0 2px}",
    ".dfs-f-q{padding:6px 8px;border:1px solid var(--border);background:var(--bg-primary);color:var(--text-primary);font:600 12px/1 var(--font-retro,monospace);min-width:170px}",
    ".dfs-f-pos{font:600 11px/1 var(--font-retro,monospace);padding:6px 9px;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer}",
    ".dfs-f-pos.active{background:var(--accent-cyan);color:var(--text-on-accent);border-color:transparent}",
    ".dfs-filterbar select{padding:6px 8px;border:1px solid var(--border);background:var(--bg-primary);color:var(--text-primary);font:600 12px/1 var(--font-retro,monospace)}",
    ".dfs-page-note{font-size:11.5px;color:var(--text-tertiary)}",
    ".dfs-elig{font:600 10px/1 var(--font-retro,monospace);color:var(--text-tertiary);border:1px solid var(--border);padding:1px 4px;margin-left:4px}",
    ".dfs-note{font-size:12.5px;color:var(--text-secondary);background:var(--bg-secondary);border:1px solid var(--border);padding:9px 12px;margin:8px 0}",
    ".dfs-warn{font-size:12.5px;color:var(--text-primary);background:var(--bg-secondary);border:1px solid var(--accent-red);padding:9px 12px;margin:8px 0}",
    ".dfs-ok{font-size:12.5px;color:var(--text-primary);background:var(--bg-secondary);border:1px solid var(--accent-green);padding:9px 12px;margin:8px 0}",
    ".dfs-empty{display:flex;flex-direction:column;gap:6px;font-size:14px;color:var(--text-primary);background:var(--bg-secondary);border:1px solid var(--border);padding:20px;margin:12px 0}",
    ".dfs-empty span{font-size:12.5px;color:var(--text-secondary)}",
    // An empty that is OUR fault reads as an outage; an empty that is baseball
    // (no games, season over) keeps the plain border. Same box, two states,
    // chosen off empty_reason_kind rather than off the sentence.
    ".dfs-empty.is-broken{border-color:var(--accent-red)}",
    // The kept-slate banner is the loudest thing on the page when it fires,
    // because every number below it belongs to a different day.
    ".dfs-stale{display:flex;flex-direction:column;gap:5px;border:2px solid var(--accent-gold);background:var(--bg-secondary);padding:12px 14px;margin:10px 0;color:var(--text-primary);font-size:13px}",
    ".dfs-stale span{font-size:12.5px;color:var(--text-secondary)}",
    ".dfs-stale-when{font-size:11px;color:var(--text-tertiary)}",
    ".dfs-stale-chip{font:700 10px/1 var(--font-retro,monospace);border:1.5px solid var(--accent-gold);padding:2px 5px;text-transform:uppercase;letter-spacing:.03em;color:var(--text-primary)}",
    ".dfs-integrity{border:1px solid var(--border);background:var(--bg-secondary);padding:9px 12px;margin:8px 0}",
    ".dfs-integrity.is-thin{border-left:3px solid var(--accent-gold)}",
    ".dfs-integrity-h{font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px}",
    ".dfs-integrity-row{display:flex;flex-wrap:wrap;gap:6px 14px}",
    ".dfs-integrity-note{font-size:12px;color:var(--text-secondary);margin-top:6px}",
    ".dfs-kv{display:inline-flex;flex-direction:column;gap:2px}",
    ".dfs-kv-l{font:600 9px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em}",
    ".dfs-kv-v{font:700 13px/1 var(--font-retro,monospace);color:var(--text-primary)}",
    // The unresolved-matchup mark rides in a table cell, so it has to stay
    // small and must never wrap the column wider than the value beside it.
    ".dfs-unres{font:600 9px/1 var(--font-retro,monospace);color:var(--text-primary);border:1px solid var(--accent-gold);padding:1px 4px;white-space:nowrap;cursor:help}",
    // A CONFIRMED start and a SCRATCH are the two facts on this page, so they
    // get the two colours that mean settled: green for the posted card, red for
    // the bat that is not on it. Everything projected keeps the plain type.
    ".dfs-conf{font:600 9px/1 var(--font-retro,monospace);color:var(--text-primary);border:1px solid var(--accent-green);padding:1px 4px;white-space:nowrap;cursor:help}",
    ".dfs-out{font:600 9px/1 var(--font-retro,monospace);color:var(--text-primary);border:1px solid var(--accent-red);padding:1px 4px;white-space:nowrap;cursor:help;text-transform:uppercase}",
    // The market number rides beside a club code on the slate card, so it has
    // to read as an annotation and never compete with the club's own weight.
    ".dfs-itt{font:600 10px/1 var(--font-retro,monospace);color:var(--text-tertiary);margin-left:2px}",
    ".dfs-error{border:1px solid var(--accent-red);padding:12px;color:var(--text-primary);background:var(--bg-secondary)}",
    ".dfs-asof{font-size:12px;color:var(--text-tertiary);margin:4px 0}",
    ".dfs-name-link{color:var(--accent-cyan);text-decoration:none}.dfs-name-link:hover{text-decoration:underline}",
    ".dfs-form{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin:10px 0}",
    ".dfs-field{display:flex;flex-direction:column;gap:3px;font:600 11px/1.3 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em}",
    ".dfs-field input,.dfs-field select{min-width:150px;padding:6px 8px;border:1px solid var(--border);background:var(--bg-primary);color:var(--text-primary);font:600 13px/1 var(--font-retro,monospace)}",
    ".dfs-check{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-secondary)}",
    ".dfs-btn,.dfs-scorebtn{font:600 12px/1 var(--font-retro,monospace);padding:7px 12px;border:1px solid var(--border);background:var(--bg-secondary);color:var(--text-secondary);cursor:pointer}",
    ".dfs-scorebar{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:10px 0}",
    ".dfs-h{font:700 13px/1.2 var(--font-retro,monospace);color:var(--text-primary);text-transform:uppercase;letter-spacing:.04em;margin:16px 0 2px}",
    ".dfs-btn-go{background:var(--accent-cyan);color:var(--text-on-accent);border-color:transparent}",
    ".dfs-scorebtn.active{background:var(--accent-cyan);color:var(--text-on-accent);border-color:transparent}",
    ".dfs-score-lbl{font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.04em;margin-right:4px}",
    ".dfs-score-note{flex:1 1 240px;font-size:11.5px;color:var(--text-tertiary)}",
    ".dfs-textarea{width:100%;min-height:110px;padding:8px;border:1px solid var(--border);background:var(--bg-primary);color:var(--text-primary);font:12px/1.4 var(--font-retro-mono,monospace)}",
    ".dfs-summary{display:flex;flex-wrap:wrap;gap:16px;margin:10px 0;font-size:13px;color:var(--text-secondary)}",
    ".dfs-slate{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px;margin:8px 0}",
    ".dfs-slate-card{border:1px solid var(--border);background:var(--bg-secondary);padding:7px 9px}",
    ".dfs-slate-row{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;padding:1px 0}",
    ".dfs-slate-team{font-weight:700;color:var(--text-primary)}",
    ".dfs-slate-sp{color:var(--text-secondary);text-align:right}",
    ".dfs-slate-meta{margin-top:4px;font-size:11px;color:var(--text-tertiary)}"
  ].join("");
  document.head.appendChild(css);
})();
