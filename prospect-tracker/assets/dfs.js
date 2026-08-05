// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
// Unauthorized copying of this file, via any medium is strictly prohibited
// Proprietary and confidential
// Written by Noah J. Dengler (@ARKNDJL), 2026
//
// /dfs/ module app. Today's slate, priced per game, plus a lineup optimizer.
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
    sort: { pitchers: { key: "pts", asc: false }, hitters: { key: "pts", asc: false } }
  };
  var LINKS = null;

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
  function gateNote(total, shown) {
    if (!gated() || shown >= total) return "";
    return '<div class="dfs-note">Diamond preview: showing the top ' + shown + " of " + total +
      " rows. Diamond funds the free site.</div>";
  }

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function num(v, d) { return (v == null || isNaN(v)) ? "-" : Number(v).toFixed(d == null ? 1 : d); }
  function money(v) { return (v == null || isNaN(v)) ? "-" : ("$" + Math.round(v).toLocaleString()); }
  function hrefFor(mlbam) {
    var e = LINKS && LINKS.byMlbam && LINKS.byMlbam[String(mlbam)];
    return (e && e.key) ? ("/projections/#player=" + e.key) : null;
  }
  function nameLink(mlbam, name) {
    var h = hrefFor(mlbam);
    if (h) return '<a class="dfs-name-link" href="' + esc(h) + '">' + esc(name) + "</a>";
    return esc(name);
  }
  function teamLogo(team) {
    return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo && team) ? EEPHUS_HUB.teamLogo(team) : "";
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
        msg: "Could not find a Name column and a Salary column in that file. " +
             "Expected headers like Name, Position, Salary, TeamAbbrev." };
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

  // ---- boards ---------------------------------------------------------------
  var PIT_COLS = [
    { key: "rank", label: "#" },
    { key: "name", label: "Pitcher", text: true },
    { key: "pts", label: "Proj", num: true },
    { key: "salary", label: "Salary", num: true },
    { key: "value", label: "Pts/$1k", num: true },
    { key: "opp", label: "Opponent", text: true },
    { key: "ip", label: "IP", num: true },
    { key: "k", label: "K", num: true },
    { key: "sem_plus", label: "SEM+", num: true }
  ];
  var HIT_COLS = [
    { key: "rank", label: "#" },
    { key: "name", label: "Hitter", text: true },
    { key: "pts", label: "Proj", num: true },
    { key: "salary", label: "Salary", num: true },
    { key: "value", label: "Pts/$1k", num: true },
    { key: "start_rate", label: "Start", num: true },
    { key: "opp", label: "Opponent", text: true },
    { key: "opp_sp", label: "Opp SP", text: true },
    { key: "hem_plus", label: "HEM+", num: true }
  ];
  function cellOf(p, key) {
    var line = p.line || {}, ctx = p.ctx || {};
    switch (key) {
      case "name": return p.name;
      case "pts": return ptsOf(p);
      case "salary": return salaryOf(p);
      case "value": return valueOf(p);
      case "start_rate": return p.start_rate;
      case "opp": return (p.is_home ? "vs " : "@ ") + (p.opp || "");
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
    if (v == null || v === "") return "-";
    if (key === "salary") return money(v);
    if (key === "value") return num(v, 2);
    if (key === "start_rate") return Math.round(v * 100) + "%";
    if (key === "pts") return num(v, 1);
    if (key === "ip" || key === "k") return num(v, 1);
    if (key === "sem_plus" || key === "hem_plus") return num(v, 0);
    return esc(v);
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
    var list = playersOf(side);
    if (!list.length) return '<div class="dfs-note">No projected ' +
      (side === "pit" ? "starters" : "hitters") + " on this slate.</div>";
    var sorted = sortPlayers(list, cols, st);
    var total = sorted.length;
    sorted = capRows(sorted);
    // Both boards render on the Slate tab, so every sort control names the
    // board it belongs to. Without that they share one sort state and a click
    // on a hitter column re-sorts the pitchers by a column they do not have.
    var board = side === "pit" ? "pitchers" : "hitters";
    var head = cols.map(function (c) {
      var on = st.key === c.key;
      return '<th' + (c.text ? ' class="dfs-l"' : "") + '><span role="button" tabindex="0" data-dfssort="' +
        esc(c.key) + '" data-dfsboard="' + board + '" aria-sort="' +
        (on ? (st.asc ? "ascending" : "descending") : "none") + '">' +
        esc(c.label) + (on ? (st.asc ? " ▴" : " ▾") : "") + "</span></th>";
    }).join("");
    var body = sorted.map(function (p, i) {
      return "<tr>" + cols.map(function (c) {
        if (c.key === "rank") return '<td class="dfs-rk">' + (i + 1) + "</td>";
        return '<td' + (c.text ? ' class="dfs-l"' : "") + ">" + fmtCell(p, c.key) + "</td>";
      }).join("") + "</tr>";
    }).join("");
    return methodNote(side) +
      '<div class="dfs-scroll"><table class="dfs-table"><thead><tr>' + head +
      "</tr></thead><tbody>" + body + "</tbody></table></div>" +
      gateNote(total, sorted.length);
  }
  function methodNote(side) {
    var d = S.data || {};
    var park = "park factor neutral (no MLB park table on the site yet)";
    var sal = Object.keys(S.salaries).length
      ? (Object.keys(S.salaries).length + " salaries loaded from your import")
      : "no salaries loaded yet, so the value column is blank until you import them";
    if (side === "pit") {
      return '<div class="dfs-note">Announced probable starters only, projected for ONE start. The skill line ' +
        "comes from the rest-of-season engine; hits, earned runs and home runs allowed carry an opponent-offense " +
        "and " + park + " multiplier. Relievers are not listed: save and hold chances are not knowable before " +
        "first pitch. " + esc(sal) + ".</div>";
    }
    return '<div class="dfs-note">Every hitter whose club is on the slate, projected for a game he STARTS. Start ' +
      "is our estimate of how often he is in the lineup, from projected playing time against a " +
      (d.anchors ? d.anchors.pa_per_start : 4.15) + " plate appearance league anchor. The matchup multiplier is " +
      "the inverse of an innings-weighted opponent pitching index (announced starter SEM+ plus bullpen Bullpen+), " +
      park + ". " + esc(sal) + ".</div>";
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
        '<div class="dfs-warn">No salaries loaded yet, so there is nothing to value. Import them above ' +
        "and this board fills in.</div>";
    }
    priced.sort(function (a, b) { return (valueOf(b) || 0) - (valueOf(a) || 0); });
    var total = priced.length;
    var shown = capRows(priced);
    var rows = shown.map(function (p, i) {
      return '<tr><td class="dfs-rk">' + (i + 1) + '</td><td class="dfs-l">' +
        teamLogo(p.team) + " " + nameLink(p.mlbam, p.name) +
        ' <span class="dfs-elig">' + esc(eligOf(p).join("/")) + "</span></td><td>" +
        esc((p.is_home ? "vs " : "@ ") + (p.opp || "")) + "</td><td>" + num(ptsOf(p), 1) +
        "</td><td>" + money(salaryOf(p)) + "</td><td>" + num(valueOf(p), 2) + "</td><td>" +
        (p.side === "hit" && p.start_rate != null ? Math.round(p.start_rate * 100) + "%" : "-") +
        "</td></tr>";
    }).join("");
    return renderSalaries() +
      '<div class="dfs-note">Projected points per thousand dollars of salary, over every player you have a ' +
      "price for. Projections are ours; salaries are yours. A high value score on a low start rate is a bench " +
      "bat who happens to be cheap, not a play.</div>" +
      '<div class="dfs-scroll"><table class="dfs-table"><thead><tr><th>#</th>' +
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
        opp_sp: (p0.ctx || {}).opp_sp, opp_pitch: (p0.ctx || {}).opp_pitch,
        pts4: sum(top4, ptsOf), pts5: sum(top5, ptsOf),
        sal4: sal4, names: top4.map(function (p) { return p.name; })
      };
    }).sort(function (a, b) { return b.pts4 - a.pts4; });
    var shown = capRows(rows);
    var body = shown.map(function (r, i) {
      return '<tr><td class="dfs-rk">' + (i + 1) + '</td><td class="dfs-l">' + teamLogo(r.team) + " " +
        esc(r.team) + "</td><td>" + esc((r.is_home ? "vs " : "@ ") + (r.opp || "")) + "</td><td>" +
        esc(r.opp_sp || "TBD") + "</td><td>" + num(r.opp_pitch, 0) + "</td><td>" + num(r.pts4, 1) +
        "</td><td>" + num(r.pts5, 1) + "</td><td>" + (r.sal4 ? money(r.sal4) : "-") +
        '</td><td class="dfs-l">' + esc(r.names.join(", ")) + "</td></tr>";
    }).join("");
    return '<div class="dfs-note">Clubs ranked by the summed projection of their four best bats on the slate, ' +
      "with the arm they face and that opponent's innings-weighted pitching index (lower is easier). This is a " +
      "SUM of independent per-player projections. The correlation that makes a stack worth building is real and " +
      "we do not model it, so read this as a shortlist of good spots, not as a stack projection.</div>" +
      '<div class="dfs-scroll"><table class="dfs-table"><thead><tr><th>#</th>' +
      '<th class="dfs-l">Club</th><th>Game</th><th>Opp SP</th>' +
      "<th>Opp index</th><th>Top 4</th><th>Top 5</th><th>Top 4 salary</th>" +
      '<th class="dfs-l">Bats</th></tr></thead><tbody>' + body + "</tbody></table></div>" +
      gateNote(rows.length, shown.length);
  }

  // ---- salaries surface -----------------------------------------------------
  function renderSalaries() {
    var meta = S.salaryMeta, rep = S.importReport;
    var have = Object.keys(S.salaries).length;
    var block =
      '<div class="dfs-note">Salaries come from you. We do not scrape or republish any site\'s salary feed, and ' +
      "nothing you paste here leaves your browser. Export the player list your contest site gives you and drop the " +
      "file below, or paste the text. We look for a Name column and a Salary column; Position and TeamAbbrev help " +
      "us join the right player. Your site's Position column wins over ours.</div>" +
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
    var tpl = template();
    if (!tpl) return { ok: false, msg: "No roster template is available in the payload." };
    var pool = optimizerPool(tpl);
    if (!pool.length) {
      return { ok: false, msg: "No player on this slate has both a salary and a projection. " +
                              "Import a salary sheet on the Salaries tab first." };
    }
    var roster = greedy(tpl, pool, false);
    if (!roster) roster = greedy(tpl, pool, true);   // cheapest-first feasibility pass
    if (!roster) {
      return { ok: false, msg: "No lineup satisfies these constraints. The solver tried a best-first " +
                              "build and then a cheapest-first one, and neither filled every slot. Try " +
                              "raising the cap, raising the per-team limit, lowering the minimum start " +
                              "rate, or importing more salaries." };
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
    var intro = '<div class="dfs-note">A greedy build plus a local-search improvement pass over the projections ' +
      "on this page and the salaries you imported. Projections are ours and are labelled on the board tabs; " +
      "salaries are yours. This is a solver, not a prediction: it maximizes projected points under your " +
      "constraints, and it is only as good as the projection it is handed.</div>";
    if (!haveSal) {
      // The importer comes with the message. Telling a reader what is missing
      // and then making him hunt for the control that fixes it is half a
      // feature.
      return intro + controls + '<div class="dfs-warn">No salaries loaded. The optimizer needs prices and we ' +
        "do not have them, by choice: bring them from your own contest site below.</div>" + renderSalaries();
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
      '<div class="dfs-scroll"><table class="dfs-table"><thead><tr><th>Slot</th>' +
      '<th class="dfs-l">Player</th><th>Game</th>' +
      "<th>Proj</th><th>Salary</th><th>Pts/$1k</th></tr></thead><tbody>" + rows +
      "</tbody></table></div>";
  }

  // ---- slate header ---------------------------------------------------------
  function renderSlate() {
    var d = S.data || {};
    var games = d.games || [];
    if (!games.length) return "";
    var cards = games.map(function (g) {
      function sideLine(s) {
        var pp = (s || {}).probable;
        return '<div class="dfs-slate-row"><span class="dfs-slate-team">' + teamLogo((s || {}).org) + " " +
          esc((s || {}).org || "") + '</span><span class="dfs-slate-sp">' +
          (pp ? esc(pp.name) : "no probable posted") + "</span></div>";
      }
      return '<div class="dfs-slate-card">' + sideLine(g.away) + sideLine(g.home) +
        '<div class="dfs-slate-meta">' + esc(g.venue || "") +
        (g.park_source === "none" ? " · park neutral" : "") + "</div></div>";
    }).join("");
    return '<div class="dfs-slate">' + cards + "</div>";
  }

  // ---- render ---------------------------------------------------------------
  function renderSection() {
    var r = root();
    if (!r) return;
    var d = S.data || {};
    var html;
    if (S.error) {
      // The payload never arrived. The tabs are still wired, so the reader gets
      // a control that responds instead of four buttons that do nothing, and
      // the same honest message under every one of them.
      html = '<div class="dfs-error" role="alert"><strong>Slate failed to load.</strong> ' +
        esc(S.error) + " The daily build may be mid-run, or the slate for today has not been " +
        "built yet. Nothing on this page works without it, including the optimizer, which " +
        'needs the projected pool to solve over. <button type="button" id="dfs-retry" ' +
        'class="dfs-btn">Retry</button></div>';
    } else if (d.empty_reason) {
      html = '<div class="dfs-empty" role="status"><strong>No slate to price.</strong><span>' +
        esc(d.empty_reason) + "</span><span>This page rebuilds every day. Nothing is broken.</span></div>";
    } else if (S.section === "value") html = renderValue();
    else if (S.section === "stacks") html = renderStacks();
    else if (S.section === "optimizer") html = renderOptimizer();
    else {
      html = renderSlate() +
        '<h3 class="dfs-h">Probable starters</h3>' + renderBoard("pit") +
        '<h3 class="dfs-h">Hitters</h3>' + renderBoard("hit");
    }
    // The shell gives /redraft/ a bar for its scoring selector and gives this
    // page none, so the contest-format selector rides at the top of the
    // section when there is nowhere else to put it.
    if (!scoringBar() && !d.empty_reason && !S.error) html = selectorHTML() + html;
    r.innerHTML = html;
    var rb = r.querySelector("#dfs-retry");
    if (rb) rb.addEventListener("click", boot);
    wireSection(r);
    if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(r);
  }
  function wireSection(r) {
    wireSelector(r);
    r.querySelectorAll("[data-dfssort]").forEach(function (h) {
      function fire() {
        var st = S.sort[h.getAttribute("data-dfsboard") || "pitchers"];
        if (!st) return;
        var k = h.getAttribute("data-dfssort");
        if (st.key === k) st.asc = !st.asc;
        else { st.key = k; st.asc = (k === "name" || k === "opp" || k === "opp_sp"); }
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
  function readHash() {
    var h = location.hash || "";
    var s = hashParam(h, "section", SECTIONS.join("|"));
    if (s) S.section = SECTION_ALIAS[s] || s;
    var sys = hashParam(h, "sys", "[A-Za-z0-9_]+");
    var known = ((S.data && S.data.scoring_catalog) || []).filter(function (c) { return c.id === sys; });
    if (sys && known.length) S.system = sys;
  }
  function writeHash() {
    var parts = ["section=" + S.section];
    var def = ((S.data && S.data.scoring_catalog) || []).filter(function (c) { return c.default; })[0];
    if (S.system && S.system !== (def ? def.id : "dk")) parts.push("sys=" + S.system);
    LAST_HASH = "#" + parts.join("&");
    try { history.replaceState(null, "", LAST_HASH); } catch (e) { /* the hash is a nicety */ }
  }
  function onHashChange() {
    if (!S.data && !S.error) return;
    if ((location.hash || "") === LAST_HASH) return;
    readHash();
    renderSelector(); syncTabs(); renderSection();
  }
  window.addEventListener("hashchange", onHashChange);

  // ---- boot -----------------------------------------------------------------
  // A failed load used to paint one red box and stop, leaving the shell's four
  // section tabs on screen with nothing bound to them: every click was a dead
  // control. The tabs get wired either way now, and renderSection carries the
  // message.
  function errorState(msg) {
    S.error = String(msg || "the payload did not load");
    S.data = null;
    readHash(); wireTabs(); syncTabs(); renderSection();
  }
  function onData(d) {
    S.error = null;
    S.data = d || {};
    loadSettings();
    loadSalaries();
    var t = template();
    if (t && !S.template) S.template = t.id;
    if (!S.data.scoring_catalog) S.data.scoring_catalog = [];
    var def = S.data.scoring_catalog.filter(function (c) { return c.default; })[0];
    if (!S.system && def) S.system = def.id;
    var b = bannerEl();
    if (b) {
      b.innerHTML = '<div class="dfs-asof">' + esc(S.data.slate_date || "") + " · " +
        (S.data.n_games || 0) + " games · " + (S.data.n_players || 0) +
        " players priced · Diamond preview, free while we build</div>";
    }
    readHash();
    renderSelector(); wireTabs(); syncTabs(); renderSection();
    if (!LINKS && window.EEPHUS_HUB && EEPHUS_HUB.links) {
      EEPHUS_HUB.links().then(function (L) { LINKS = L || null; renderSection(); });
    }
  }
  function boot() {
    fetch(DATA_URL, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(onData).catch(function (e) { errorState(String(e && e.message || e)); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // ---- module styles (theme tokens only) ------------------------------------
  var css = document.createElement("style");
  css.textContent = [
    // Wide boards scroll inside their own box. The nine-column slate and stacks
    // tables were pushing the whole document sideways at phone widths.
    ".dfs-scroll{max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}",
    ".dfs-table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}",
    ".dfs-table th{text-align:right;font:600 11px/1 var(--font-retro,monospace);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.03em;padding:6px 8px;border-bottom:1px solid var(--border)}",
    ".dfs-table td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--border-light);color:var(--text-primary)}",
    ".dfs-table th.dfs-l,.dfs-table td.dfs-l{text-align:left}",
    ".dfs-table td.dfs-rk{color:var(--text-tertiary)}",
    ".dfs-table th [role=button]{cursor:pointer}",
    ".dfs-elig{font:600 10px/1 var(--font-retro,monospace);color:var(--text-tertiary);border:1px solid var(--border);padding:1px 4px;margin-left:4px}",
    ".dfs-note{font-size:12.5px;color:var(--text-secondary);background:var(--bg-secondary);border:1px solid var(--border);padding:9px 12px;margin:8px 0}",
    ".dfs-warn{font-size:12.5px;color:var(--text-primary);background:var(--bg-secondary);border:1px solid var(--accent-red);padding:9px 12px;margin:8px 0}",
    ".dfs-ok{font-size:12.5px;color:var(--text-primary);background:var(--bg-secondary);border:1px solid var(--accent-green);padding:9px 12px;margin:8px 0}",
    ".dfs-empty{display:flex;flex-direction:column;gap:6px;font-size:14px;color:var(--text-primary);background:var(--bg-secondary);border:1px solid var(--border);padding:20px;margin:12px 0}",
    ".dfs-empty span{font-size:12.5px;color:var(--text-secondary)}",
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
