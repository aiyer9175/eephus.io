/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* /scores/ - Scores / Standings, the scores page (SCORES_3, behind
   scores_core.SCORES_LIVE). A pure reader of the job's files under
   /data/scores/: it joins, sorts and formats what the job wrote and compares
   times for the stale rule; it computes no number of its own.

   FETCH RULES (plan 2.3): the polled file every job.poll_live_s while a game
   on the viewed date is live and the tab is visible, else job.poll_idle_s,
   none while hidden, backing off on errors; the index when index_rev moves;
   date, season and game files only when their rev moves, as <file>?v=<rev>;
   every request with cache: "no-cache"; the player links and the video chunk
   (assets/scores-video.js) only once a game view opens.

   LABELLING (plan 4): every model number sits in a data-model-id element whose
   chip reads the registry block's sentence ("MLB, provisional"); a number with
   no row there is not drawn. Tokens only, no team colours. */
(function () {
  "use strict";

  var BASE = "/data/scores/";
  var POLL_LIVE_S = 45, POLL_IDLE_S = 300, BACKOFF = [45, 90, 180, 300];
  var ANNOUNCE_GAP_MS = 15000;
  var MAX_CHART_POINTS = 130;
  // The AL's fifteen MLBAM team ids, for the AL / NL filter (a join on the id).
  var AL_IDS = [108, 110, 111, 114, 116, 117, 118, 133, 136, 139, 140, 141, 142, 145, 147];
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"];
  var DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  var STALE = {
    S0: "Updated {t}",
    S1L: "Live updates paused. Scores as of {t}.",
    S1: "Updates paused. Scores as of {t}.",
    S2: "Live scores are not updating. Showing the last update, from {t}.",
    S3: "Scores were last updated {d}. They may be out of date.",
    S4: "Scores are not available right now."
  };

  // ------------------------------------------------------------------ helpers
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isNum(x) { return typeof x === "number" && isFinite(x); }
  function ms(iso) { var t = Date.parse(iso || ""); return isNaN(t) ? null : t; }
  // Thousandths to a whole percent, half up (scores_core.round_half_up).
  function pct(th) { return isNum(th) ? Math.floor(th / 10 + 0.5) : null; }
  function signed(th) {
    if (!isNum(th)) return "";
    var p = Math.floor(th / 10 + 0.5);
    return (p > 0 ? "+" : p < 0 ? "-" : "") + Math.abs(p);
  }
  function signed3(th) {
    if (!isNum(th)) return "";
    return (th > 0 ? "+" : th < 0 ? "-" : "") + (Math.abs(th) / 1000).toFixed(3);
  }
  function clock(t) {
    var d = new Date(t), h = d.getHours(), m = d.getMinutes();
    return ((h % 12) || 12) + ":" + (m < 10 ? "0" : "") + m + (h < 12 ? " AM" : " PM");
  }
  function monthDay(t) { var d = new Date(t); return MONTHS[d.getMonth()] + " " + d.getDate(); }
  // A YYYY-MM-DD string read as a calendar date (UTC noon, so no zone moves it).
  function dayOf(ds) { return new Date(ds + "T12:00:00Z"); }
  function longDate(ds) {
    var d = dayOf(ds);
    return DAYS[d.getUTCDay()] + ", " + MONTHS[d.getUTCMonth()] + " " + d.getUTCDate();
  }
  function shortDay(ds) { var d = dayOf(ds); return DAYS[d.getUTCDay()].slice(0, 3) + " " + d.getUTCDate(); }
  function addDays(ds, n) {
    var d = dayOf(ds); d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  }
  function validDate(s) { return /^\d{4}-\d{2}-\d{2}$/.test(s || "") && !isNaN(dayOf(s).getTime()); }
  function startTime(card) {
    if (!card || card.tbd || !card.start) return "Time to be announced";
    var t = ms(card.start);
    if (t == null) return "";
    try {
      return new Date(t).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
    } catch (e) { return clock(t); }
  }
  function ordinal(n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }
  function half3(h) { return h === "bottom" ? "Bot" : "Top"; }
  function halfWord(h) { return h === "bottom" ? "bottom" : "top"; }
  function lastName(full) {
    var p = String(full || "").split(" ");
    return p.length > 1 ? p.slice(1).join(" ") : String(full || "");
  }
  function lower(s) { return s ? String(s).toLowerCase() : ""; }
  function mmss(sec) {
    if (!isNum(sec)) return "";
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }
  // A rate the job rounded (one or two decimals), printed with its digits.
  function f1(x) { return isNum(x) ? x.toFixed(1) : ""; }
  function f2(x) { return isNum(x) ? x.toFixed(2) : ""; }
  function comma(n) { return isNum(n) ? String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",") : ""; }
  function outsText(n) { return n + (n === 1 ? " out" : " outs"); }
  function basesText(b) {
    var names = ["1st", "2nd", "3rd"], on = [];
    for (var i = 0; i < 3; i++) if (b && b[i]) on.push(names[i]);
    if (!on.length) return "bases empty";
    if (on.length === 3) return "bases loaded";
    return (on.length === 1 ? "runner on " : "runners on ") + on.join(" and ");
  }
  function basesAria(b) {
    var names = ["first", "second", "third"], on = [];
    for (var i = 0; i < 3; i++) if (b && b[i]) on.push(names[i]);
    if (!on.length) return "Bases empty";
    if (on.length === 3) return "Bases loaded";
    return (on.length === 1 ? "Runner on " : "Runners on ") + on.join(" and ");
  }

  // ------------------------------------------------------------ stale rule
  function validLatest(L) {
    return !!(L && typeof L === "object" && L.schema === 1 && typeof L.generated_at === "string" &&
      L.job && typeof L.job === "object" && typeof L.today === "string" &&
      L.window && typeof L.window === "object");
  }
  function liveOnDate(L, date) {
    if (!L) return false;
    var live = L.live || [];
    for (var i = 0; i < live.length; i++) if (live[i] && live[i].date === date) return true;
    var w = (L.window || {})[date];
    return !!(w && w.live > 0);
  }
  // scoresStaleState(latest, serverNowMs, viewedDate): plan 2.4, evaluated in
  // the order S4, S3, S2, S0, S1 (S1 is the default row). serverNowMs is the
  // Date header of the latest response, else the client clock.
  function scoresStaleState(L, serverNowMs, viewedDate) {
    if (!validLatest(L)) return { code: "S4", sentence: STALE.S4, live: false };
    var now = isNum(serverNowMs) ? serverNowMs : Date.now();
    var gen = ms(L.generated_at), lastOk = ms(L.job.last_ok_at), nextBy = ms(L.job.next_by);
    var down = isNum(L.job.down_after_s) ? L.job.down_after_s : 1800;
    var live = liveOnDate(L, viewedDate);
    var asOf = lastOk != null ? lastOk : gen;
    if (gen == null) return { code: "S4", sentence: STALE.S4, live: false };
    if (now - gen > 36 * 3600 * 1000) {
      return { code: "S3", sentence: STALE.S3.replace("{d}", monthDay(gen)), live: live, at: gen };
    }
    if (lastOk != null && now - lastOk > down * 1000 && live) {
      return { code: "S2", sentence: STALE.S2.replace("{t}", clock(lastOk)), live: live, at: lastOk };
    }
    if (nextBy != null && now <= nextBy && (L.job.state === "ok" || L.job.state === "idle")) {
      return { code: "S0", sentence: STALE.S0.replace("{t}", clock(gen)), live: live, at: gen };
    }
    return { code: "S1", sentence: (live ? STALE.S1L : STALE.S1).replace("{t}", clock(asOf)), live: live, at: asOf };
  }

  // ---------------------------------------------------------------- routes
  function parseRoute(hash) {
    var h = String(hash || "").replace(/^#/, ""), q = {};
    h.split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      var k = i < 0 ? kv : kv.slice(0, i), v = i < 0 ? "" : kv.slice(i + 1);
      try { v = decodeURIComponent(v); } catch (e) { v = ""; }
      if (k) q[k] = v;
    });
    var r = { view: "day", date: null, f: "all", lg: null, mine: false, game: null, tab: null, play: null };
    if (validDate(q.date)) r.date = q.date;
    if (/^(live|upcoming|final)$/.test(q.f || "")) r.f = q.f;
    if (/^(AL|NL)$/.test(q.lg || "")) r.lg = q.lg;
    if (q.mine === "1") r.mine = true;
    if (/^\d{1,9}$/.test(q.game || "")) {
      r.view = "game"; r.game = +q.game;
      if (/^(summary|preview|box|plays|lineups|info)$/.test(q.tab || "")) r.tab = q.tab;
      if (/^\d{1,4}$/.test(q.play || "")) r.play = +q.play;
    } else if ("about" in q) {
      r.view = "about";
    }
    return r;
  }
  function dayHash(r, over) {
    var o = {}, k;
    for (k in r) o[k] = r[k];
    for (k in (over || {})) o[k] = over[k];
    var p = [];
    if (o.date) p.push("date=" + o.date);
    if (o.f && o.f !== "all") p.push("f=" + o.f);
    if (o.lg) p.push("lg=" + o.lg);
    if (o.mine) p.push("mine=1");
    return "#" + p.join("&");
  }

  // ---------------------------------------------------------------- loader
  // One loader per page; fetchFn(url, opts) resolves to a Response.
  function makeLoader(fetchFn, clientNow) {
    clientNow = clientNow || function () { return Date.now(); };
    var S = { latest: null, index: null, indexRev: null, seasons: {}, dates: {}, games: {},
      serverAt: null, clientAt: null };
    function get(path) {
      return fetchFn(BASE + path, { cache: "no-cache" }).then(function (r) {
        if (!r || !r.ok) throw new Error("HTTP " + (r ? r.status : 0));
        return r;
      });
    }
    function json(path) { return get(path).then(function (r) { return r.json(); }); }
    function latest() {
      return get("latest.json").then(function (r) {
        var hdr = null;
        try { hdr = r.headers && r.headers.get ? r.headers.get("Date") : null; } catch (e) { hdr = null; }
        var t = hdr ? Date.parse(hdr) : NaN;
        S.serverAt = isNaN(t) ? null : t;
        S.clientAt = clientNow();
        return r.json();
      }).then(function (L) {
        S.latest = L;
        if (!validLatest(L)) throw new Error("schema");
        if (S.index && L.index_rev === S.indexRev) return L;
        return json("index.json?v=" + encodeURIComponent(L.index_rev || "")).then(function (ix) {
          S.index = ix; S.indexRev = L.index_rev;
          return L;
        });
      });
    }
    function serverNow() {
      if (S.serverAt == null) return clientNow();
      return S.serverAt + (clientNow() - S.clientAt);
    }
    function seasonRev(y) {
      var ss = (S.index && S.index.seasons) || [];
      for (var i = 0; i < ss.length; i++) if (ss[i].season === y) return ss[i].rev;
      return null;
    }
    function season(y) {
      var rev = seasonRev(y), have = S.seasons[y];
      if (!rev) return Promise.resolve(null);
      if (have && have.rev === rev) return Promise.resolve(have.doc);
      return json("index-" + y + ".json?v=" + encodeURIComponent(rev)).then(function (doc) {
        S.seasons[y] = { rev: rev, doc: doc };
        return doc;
      });
    }
    function dateRev(d) {
      var w = S.latest && S.latest.window && S.latest.window[d];
      if (w && w.rev) return Promise.resolve(w.rev);
      return season(+d.slice(0, 4)).then(function (doc) {
        var ds = (doc && doc.dates) || [];
        for (var i = 0; i < ds.length; i++) if (ds[i].d === d) return ds[i].rev;
        return null;
      });
    }
    function date(d) {
      return dateRev(d).then(function (rev) {
        if (!rev) return null;
        var have = S.dates[d];
        if (have && have.rev === rev) return have.doc;
        return json(d + ".json?v=" + encodeURIComponent(rev)).then(function (doc) {
          S.dates[d] = { rev: rev, doc: doc };
          return doc;
        });
      });
    }
    function game(pk, rev) {
      var have = S.games[pk];
      if (have && (rev == null || have.rev === rev)) return Promise.resolve(have.doc);
      var path = "games/" + pk + ".json" + (rev ? "?v=" + encodeURIComponent(rev) : "");
      return json(path).then(function (doc) {
        S.games[pk] = { rev: rev || (doc && doc.rev), doc: doc };
        return doc;
      });
    }
    return { state: S, latest: latest, serverNow: serverNow, season: season, date: date, game: game,
      dateRev: dateRev };
  }

  // ------------------------------------------------------------ registry
  function regRow(ix, id) {
    var rows = (ix && ix.registry) || [];
    for (var i = 0; i < rows.length; i++) if (rows[i] && rows[i].model_id === id) return rows[i];
    return null;
  }
  // An element holding model numbers: data-model-id plus its visible chip.
  function labelled(ix, id, inner, tag, cls) {
    var row = regRow(ix, id);
    if (!row) return "";
    tag = tag || "div";
    return "<" + tag + ' class="sc-model' + (cls ? " " + cls : "") + '" data-model-id="' + esc(id) + '">' +
      inner + ' <span class="sc-src">' + esc(row.sentence) + "</span></" + tag + ">";
  }
  // The leading club's MLB win probability, from the home value.
  function wpLead(card, homeTh) {
    if (!isNum(homeTh) || !card) return null;
    if (homeTh >= 500) return { code: card.home.code || card.home.short, pct: pct(homeTh) };
    return { code: card.away.code || card.away.short, pct: pct(1000 - homeTh) };
  }

  // ---------------------------------------------------------------- links
  var LINKS = null;
  function clubLink(side) {
    var hub = window.EEPHUS_HUB, c = null;
    if (hub && typeof hub.clubHref === "function" && typeof hub.clubLinkHTML === "function") {
      try { var h = hub.clubLinkHTML(side.team_id, { cls: "sc-club" }); if (h) return h; } catch (e) { /* stopgap below */ }
    }
    if (hub && typeof hub.club === "function") c = hub.club(side.team_id);
    var code = c ? c.code : null;
    if (!code) return '<span class="sc-club" data-club-nolink="unresolved">' + esc(side.code || side.short || "") + "</span>";
    return '<a class="sc-club" href="/franchise/#team=' + encodeURIComponent(code) + '">' + esc(code) + "</a>";
  }
  function player(id, name) {
    if (LINKS && LINKS.byMlbam && LINKS.byMlbam[String(id)]) {
      return '<a class="sc-player" href="/player/#' + encodeURIComponent(String(id)) + '">' + esc(name) + "</a>";
    }
    return esc(name);
  }

  // ---------------------------------------------------------------- cards
  function reasonText(r) { return r ? lower(r) : ""; }
  function stateLine(c, stale) {
    var r = reasonText(c.reason), n = (c.line || []).length;
    switch (c.state) {
      case "scheduled": return startTime(c);
      case "pregame": return startTime(c);
      case "delayed":
        if (c.sit && c.sit.inning) return "Delayed" + (r ? ": " + r : "") + ", " + halfWord(c.sit.half) + " " + c.sit.inning;
        return "Delayed start" + (r ? ": " + r : "");
      case "live":
        if (!c.sit) return "Live";
        if (stale && stale.code === "S1") return "Live, as of " + clock(stale.at);
        return half3(c.sit.half) === "Bot" ? "Bottom " + c.sit.inning + ", " + outsText(c.sit.outs)
          : "Top " + c.sit.inning + ", " + outsText(c.sit.outs);
      case "final":
        if (c.flags && c.flags.shortened) return "Final, " + n + " innings" + (r ? ": " + r : "");
        if (c.flags && c.flags.extra_innings) return "Final, " + n + " innings";
        return "Final";
      case "postponed": return "Postponed" + (r ? ": " + r : "") + ".";
      case "suspended": return "Suspended" + (n ? " in the " + ordinal(n) : "") + (r ? ": " + r : "") + ".";
      case "cancelled": return "Cancelled" + (r ? ": " + r : "") + ".";
    }
    return "";
  }
  function teamRow(c, side, showScore) {
    var t = c[side], o = c[side === "away" ? "home" : "away"];
    var won = c.state === "final" && isNum(t.r) && isNum(o.r) && t.r > o.r;
    var rec = t.wl && isNum(t.wl.w) ? t.wl.w + "-" + t.wl.l : "";
    var cells = '<th scope="row" class="sc-tm">' + clubLink(t) + ' <span class="sc-short">' + esc(t.short || "") +
      "</span>" + (won ? ' <span class="sr-only">winner</span>' : "") +
      (rec ? ' <span class="sc-rec">' + esc(rec) + "</span>" : "") + "</th>";
    if (showScore) {
      var line = c.line || [], li = "";
      for (var i = 0; i < line.length; i++) {
        var v = line[i] ? line[i][side === "away" ? 0 : 1] : null;
        li += '<td class="sc-inn">' + (v == null ? (c.state === "final" && side === "home" ? "x" : "") : esc(v)) + "</td>";
      }
      cells += li + '<td class="sc-r">' + (isNum(t.r) ? t.r : "") + '</td><td class="sc-he">' + (isNum(t.h) ? t.h : "") +
        '</td><td class="sc-he">' + (isNum(t.e) ? t.e : "") + "</td>";
    }
    return '<tr class="' + (won ? "is-won" : "") + '">' + cells + "</tr>";
  }
  function teamsTable(c) {
    var score = c.state === "live" || c.state === "final" || (c.state === "delayed" && c.sit && c.sit.inning) ||
      c.state === "suspended";
    var head = "";
    if (score) {
      var line = c.line || [], h = "";
      for (var i = 0; i < line.length; i++) h += '<th scope="col" class="sc-inn">' + (i + 1) + "</th>";
      head = '<thead><tr><th scope="col" class="sc-tm"><span class="sr-only">Club</span></th>' + h +
        '<th scope="col" class="sc-r">R</th><th scope="col" class="sc-he">H</th><th scope="col" class="sc-he">E</th></tr></thead>';
    }
    return '<div class="sc-line"><table class="sc-teams' + (score ? " has-score" : "") + '">' + head + "<tbody>" +
      teamRow(c, "away", score) + teamRow(c, "home", score) + "</tbody></table></div>";
  }
  function probableText(p) {
    if (!p) return "Probable not announced";
    var bits = [lastName(p.name)];
    if (p.hand) bits.push(p.hand);
    if (isNum(p.w) && isNum(p.l)) bits.push(p.w + "-" + p.l);
    if (p.era != null && p.era !== "") bits.push(p.era + " ERA");
    return bits.join(", ");
  }
  function diamond(b) {
    var on = function (i) { return b && b[i] ? " is-on" : ""; };
    return '<svg class="sc-bases" viewBox="0 0 30 22" width="30" height="22" role="img" aria-label="' + esc(basesAria(b)) + '">' +
      '<rect class="sc-base' + on(1) + '" x="11" y="1" width="8" height="8" transform="rotate(45 15 5)"/>' +
      '<rect class="sc-base' + on(2) + '" x="2" y="10" width="8" height="8" transform="rotate(45 6 14)"/>' +
      '<rect class="sc-base' + on(0) + '" x="20" y="10" width="8" height="8" transform="rotate(45 24 14)"/></svg>';
  }
  function lastUpdate(c) {
    var s = c.sit || {};
    return "Last update: " + (s.inning ? half3(s.half) === "Bot" ? "Bottom " + s.inning : "Top " + s.inning : "Live") +
      ", " + esc(c.away.code || c.away.short) + " " + (isNum(c.away.r) ? c.away.r : 0) + ", " +
      esc(c.home.code || c.home.short) + " " + (isNum(c.home.r) ? c.home.r : 0);
  }
  function cardBody(c, ix, stale) {
    var out = [];
    if (c.state === "scheduled" || c.state === "pregame" || (c.state === "delayed" && !(c.sit && c.sit.inning))) {
      out.push('<p class="sc-row sc-venue">' + esc(c.venue && c.venue.name || "") + "</p>");
      out.push('<p class="sc-row">' + esc((c.away.code || c.away.short) + ": " + probableText(c.away.probable)) + "</p>");
      out.push('<p class="sc-row">' + esc((c.home.code || c.home.short) + ": " + probableText(c.home.probable)) + "</p>");
      if (c.state === "pregame") {
        out.push('<p class="sc-row">' + (c.away.lineup_posted && c.home.lineup_posted ? "Lineups posted" : "Lineups not posted yet") + "</p>");
      }
      var extra = [];
      if (c.tv && c.tv.length) extra.push("TV: " + c.tv.join(", "));
      if (c.state === "pregame" && c.weather) {
        extra.push([c.weather.condition, c.weather.temp ? c.weather.temp + " F" : ""].filter(Boolean).join(", "));
      }
      if (extra.length) out.push('<p class="sc-row sc-dim">' + esc(extra.join(". ")) + "</p>");
      return out.join("");
    }
    if (c.state === "live" || c.state === "delayed") {
      var s = c.sit || {};
      if (stale && stale.code === "S2") {
        out.push('<p class="sc-row">' + lastUpdate(c) + "</p>");
        return out.join("");
      }
      out.push('<div class="sc-sit">' + diamond(s.bases) +
        '<span class="sc-count">Count ' + (s.balls || 0) + "-" + (s.strikes || 0) +
        '<span class="sr-only">: ' + (s.balls || 0) + (s.balls === 1 ? " ball, " : " balls, ") +
        (s.strikes || 0) + (s.strikes === 1 ? " strike" : " strikes") + "</span></span></div>");
      if (s.batter || s.pitcher) {
        var pc = s.pitcher && isNum(s.pitcher.pitches) ? " (" + s.pitcher.pitches + " pitches)" : "";
        out.push('<p class="sc-row">At bat: ' + esc(s.batter ? lastName(s.batter.name) : "") + " vs " +
          esc(s.pitcher ? lastName(s.pitcher.name) : "") + esc(pc) + "</p>");
      }
      out.push('<p class="sc-row sc-last">' + esc(s.last_text || "") + "</p>");
      var lead = c.wp ? wpLead(c, c.wp.home) : null;
      if (lead) out.push(labelled(ix, "scores_mlb_wp", "MLB win probability: " + esc(lead.code) + " " + lead.pct + "%", "p", "sc-row"));
      if (c.flags && (c.flags.no_hitter || c.flags.perfect_game)) {
        out.push('<p class="sc-row sc-chips"><span class="sc-chip">' + (c.flags.perfect_game ? "Perfect game in progress" : "No-hitter in progress") + "</span></p>");
      }
      return out.join("");
    }
    if (c.state === "final") {
      var rec = c.of_record || {}, dec = [];
      if (rec.w) dec.push("W " + lastName(rec.w.name));
      if (rec.l) dec.push("L " + lastName(rec.l.name));
      if (rec.sv) dec.push("S " + lastName(rec.sv.name));
      if (dec.length) out.push('<p class="sc-row">' + esc(dec.join(", ")) + "</p>");
      if (c.star) {
        out.push(labelled(ix, "scores_stars_rule", "Star: " + esc(lastName(c.star.name)) + " (" + esc(c.star.team) + "). " +
          esc(c.star.why || ""), "p", "sc-row sc-star"));
      }
      if (c.top_play) {
        var tp = c.top_play;
        var chip = isNum(tp.clip_s) ? ' <a class="sc-chip sc-up" href="#game=' + c.pk + "&play=" + tp.ab + '">Video ' + mmss(tp.clip_s) + "</a>" : "";
        out.push(labelled(ix, "scores_mlb_wp", "Top play: " + esc(tp.text) + " " + esc(tp.bat_team) + " " + pct(tp.before) +
          "% to " + pct(tp.after) + "% (" + signed(tp.swing) + ")" + chip, "p", "sc-row sc-top"));
      }
      var chips = [];
      if (c.videos && isNum(c.videos.recap_s)) chips.push('<a class="sc-chip sc-up" href="#game=' + c.pk + '">Recap ' + mmss(c.videos.recap_s) + "</a>");
      if (c.flags && c.flags.perfect_game) chips.push('<span class="sc-chip">Perfect game</span>');
      else if (c.flags && c.flags.no_hitter) chips.push('<span class="sc-chip">No-hitter</span>');
      if (c.flags && c.flags.debut) chips.push('<span class="sc-chip">MLB debut</span>');
      if (chips.length) out.push('<p class="sc-row sc-chips">' + chips.join(" ") + "</p>");
      return out.join("");
    }
    var when = c.state === "postponed" ? c.makeup : c.state === "suspended" ? c.resume : null;
    if (when && ms(when) != null) {
      out.push('<p class="sc-row">' + (c.state === "postponed" ? "Makeup " : "Resumes ") + esc(monthDay(ms(when))) + ".</p>");
    }
    return out.join("");
  }
  function cardHTML(c, ix, stale, gone) {
    var st = stale && c.state === "live" ? stale : null;
    var asOf = c.stale_since && ms(c.stale_since) != null && c.state === "live" && !(st && st.code !== "S0")
      ? '<span class="sc-asof">as of ' + esc(clock(ms(c.stale_since))) + "</span>" : "";
    var series = c.series && c.series.text ? esc(c.series.text) : "";
    if (c.series && c.series.if_necessary) series += (series ? ". " : "") + (gone ? "Not needed" : "If necessary");
    return '<div class="sc-head"><h3 class="sc-match"><a class="sc-stretch" href="#game=' + c.pk + '">' +
      esc(c.away.code || c.away.short) + " at " + esc(c.home.code || c.home.short) + "</a></h3>" +
      '<span class="sc-state">' + esc(stateLine(c, st)) + "</span>" + asOf + "</div>" +
      '<p class="sc-series">' + series + "</p>" + teamsTable(c) +
      '<div class="sc-body">' + cardBody(c, ix, st) + "</div>";
  }
  function slotOf(state) {
    if (state === "live" || state === "final") return "lf";
    if (state === "delayed") return "lf";
    if (state === "scheduled" || state === "pregame") return "pre";
    return "off";
  }

  // ------------------------------------------------------------ the chart
  // One 2 px line of the home club's MLB win probability over plate
  // appearances, drawn at the container's pixel width (plan 1.5).
  function chartModel(g) {
    var ser = (g.wp && g.wp.series) || [], step = 1;
    if (ser.length > MAX_CHART_POINTS) step = Math.ceil(ser.length / MAX_CHART_POINTS);
    var keep = {}, big = g.plays_big || [], i;
    for (i = 0; i < big.length; i++) keep[big[i].ab] = big[i].rank;
    var pts = [];
    for (i = 0; i < ser.length; i++) {
      var r = ser[i];
      if (i % step === 0 || keep[r[0]] || i === ser.length - 1) {
        pts.push({ ab: r[0], inning: r[1], half: r[2], wp: r[3], swing: r[4], rank: keep[r[0]] || 0, prev: i ? ser[i - 1][3] : g.wp.pregame_home });
      }
    }
    return pts;
  }
  function chartSVG(g, W, live) {
    var c = g.card, pts = chartModel(g);
    var H = W < 600 ? 180 : 240, AX = 24, PADL = 12, PADR = live ? 58 : 12, PADT = 10;
    var iw = Math.max(40, W - PADL - PADR), ih = H - PADT;
    var n = pts.length;
    var x = function (i) { return PADL + (n <= 1 ? iw / 2 : i / (n - 1) * iw); };
    var y = function (th) { return PADT + (1 - th / 1000) * ih; };
    var o = '<svg class="sc-wp-svg" width="' + W + '" height="' + (H + AX) + '" viewBox="0 0 ' + W + " " + (H + AX) + '" aria-hidden="true" focusable="false">';
    [0, 250, 500, 750, 1000].forEach(function (g2) {
      o += '<line class="sc-gl' + (g2 === 500 ? " is-mid" : "") + '" x1="' + PADL + '" x2="' + (PADL + iw) + '" y1="' + y(g2).toFixed(1) + '" y2="' + y(g2).toFixed(1) + '"/>';
    });
    o += '<text class="sc-ax" x="' + (PADL + 2) + '" y="' + (y(1000) + 12) + '">' + esc((c.home.code || c.home.short) + " 100%") + "</text>";
    o += '<text class="sc-ax" x="' + (PADL + 2) + '" y="' + (y(0) - 4) + '">' + esc((c.away.code || c.away.short) + " 100%") + "</text>";
    o += '<text class="sc-ax" x="' + (PADL + iw - 2) + '" y="' + (y(500) - 4) + '" text-anchor="end">50%</text>';
    var d = "", pen = false, lastInn = null;
    for (var i = 0; i < n; i++) {
      var p = pts[i];
      if (p.half === "top" && p.inning !== lastInn) {
        o += '<text class="sc-ax" x="' + x(i).toFixed(1) + '" y="' + (H + 16) + '" text-anchor="middle">' + p.inning + "</text>";
        lastInn = p.inning;
      }
      if (!isNum(p.wp)) { pen = false; continue; }
      d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(p.wp).toFixed(1);
      pen = true;
    }
    o += '<path class="sc-wp-line" d="' + d + '"/>';
    for (i = 0; i < n; i++) {
      if (pts[i].rank && isNum(pts[i].wp)) {
        o += '<g class="sc-mark"><circle cx="' + x(i).toFixed(1) + '" cy="' + y(pts[i].wp).toFixed(1) + '" r="9"/>' +
          '<text x="' + x(i).toFixed(1) + '" y="' + (y(pts[i].wp) + 4).toFixed(1) + '" text-anchor="middle">' + pts[i].rank + "</text></g>";
      }
    }
    if (live && n && isNum(pts[n - 1].wp)) {
      var lead = wpLead(c, pts[n - 1].wp);
      o += '<circle class="sc-end" cx="' + x(n - 1).toFixed(1) + '" cy="' + y(pts[n - 1].wp).toFixed(1) + '" r="4"/>' +
        '<text class="sc-ax sc-endlbl" x="' + (x(n - 1) + 8).toFixed(1) + '" y="' + (y(pts[n - 1].wp) + 4).toFixed(1) + '">' + esc(lead.code + " " + lead.pct + "%") + "</text>";
    }
    o += '<line class="sc-cross" x1="0" x2="0" y1="' + PADT + '" y2="' + (PADT + ih) + '" visibility="hidden"/></svg>';
    return { svg: o, pts: pts, x: x, y: y, W: W, H: H };
  }
  function chartAria(g) {
    var c = g.card, ser = (g.wp && g.wp.series) || [], last = null;
    for (var i = ser.length - 1; i >= 0; i--) if (isNum(ser[i][3])) { last = ser[i][3]; break; }
    var s = "Win probability, " + (c.home.code || c.home.short) + " at home: from " + pct(g.wp.pregame_home) +
      " percent to " + pct(last) + " percent.";
    var b = (g.plays_big || [])[0];
    if (b) {
      s += " Largest swing: " + String(b.text || "").split(". ")[0] + ", " + halfWord(b.half) + " " + ordinal(b.inning) +
        ", " + pct(b.before) + " to " + pct(b.after) + " percent.";
    }
    return s;
  }
  function mountChart(host, g, live) {
    var frame = host.querySelector(".sc-wp-frame");
    if (!frame) return;
    var W = Math.max(200, Math.floor(frame.clientWidth || 358));
    var ch = chartSVG(g, W, live);
    frame.innerHTML = ch.svg + '<div class="sc-tip" hidden></div>';
    var svg = frame.querySelector("svg"), tip = frame.querySelector(".sc-tip"), cross = svg.querySelector(".sc-cross");
    var byAb = {};
    (g.plays || []).forEach(function (p) { byAb[p.ab] = p; });
    var idx = frame._pin != null ? frame._pin : null, pinned = frame._pin != null;
    function show(i) {
      if (i == null || !ch.pts[i]) { cross.setAttribute("visibility", "hidden"); tip.hidden = true; return; }
      var p = ch.pts[i], X = ch.x(i);
      cross.setAttribute("x1", X.toFixed(1)); cross.setAttribute("x2", X.toFixed(1));
      cross.setAttribute("visibility", "visible");
      var home = g.card.home.code || g.card.home.short, play = byAb[p.ab];
      tip.textContent = "";
      var l1 = document.createElement("b"); l1.textContent = half3(p.half) + " " + p.inning; tip.appendChild(l1);
      var l2 = document.createElement("span"); l2.textContent = play ? play.text : ""; tip.appendChild(l2);
      var l3 = document.createElement("span");
      l3.textContent = isNum(p.wp) ? home + " " + pct(p.prev) + "% to " + pct(p.wp) + "%, swing " + signed(p.swing) : "No MLB value";
      tip.appendChild(l3);
      tip.hidden = false;
      var left = Math.min(Math.max(0, X - 90), Math.max(0, ch.W - 184));
      tip.style.left = left + "px";
    }
    function nearest(ev) {
      var r = svg.getBoundingClientRect(), px = ev.clientX - r.left, best = 0, bd = 1e9;
      for (var i = 0; i < ch.pts.length; i++) { var dd = Math.abs(ch.x(i) - px); if (dd < bd) { bd = dd; best = i; } }
      return best;
    }
    svg.addEventListener("pointermove", function (ev) { if (!pinned) { idx = nearest(ev); show(idx); } });
    svg.addEventListener("pointerleave", function () { if (!pinned) { idx = null; show(null); } });
    svg.addEventListener("pointerup", function (ev) {
      if (pinned) { pinned = false; idx = null; frame._pin = null; show(null); return; }
      idx = nearest(ev); pinned = true; frame._pin = idx; show(idx);
    });
    frame.onkeydown = function (ev) {
      var k = ev.key, n = ch.pts.length;
      if (k === "Escape") { pinned = false; idx = null; frame._pin = null; show(null); return; }
      if (k !== "ArrowLeft" && k !== "ArrowRight" && k !== "Home" && k !== "End") return;
      ev.preventDefault();
      if (idx == null) idx = k === "ArrowLeft" || k === "End" ? n - 1 : 0;
      else if (k === "ArrowLeft") idx = Math.max(0, idx - 1);
      else if (k === "ArrowRight") idx = Math.min(n - 1, idx + 1);
      else idx = k === "Home" ? 0 : n - 1;
      pinned = true; frame._pin = idx; show(idx);
    };
    if (pinned) show(idx);
  }

  // ------------------------------------------------------------ game view
  function lineScore(c) {
    return '<div class="sc-line sc-line-wide">' + teamsTable(c).replace('<div class="sc-line">', "").replace(/<\/div>$/, "") + "</div>";
  }
  function bigRows(g, ix, live) {
    if (!g.plays_big || !g.plays_big.length) return '<p class="sc-dim">' + esc(g.plays_big_reason || "No plate appearance moved win probability 3 points or more yet.") + "</p>";
    var rows = g.plays_big.map(function (b) {
      var s = b.situation || {}, lead = s.lead === 0 ? "tied" : s.lead > 0 ? b.bat_team + " leads by " + s.lead : b.bat_team + " trails by " + (-s.lead);
      return '<li class="sc-big" data-ab="' + b.ab + '"><span class="sc-rank">' + b.rank + '</span><div>' +
        '<p class="sc-dim">' + esc(half3(b.half) + " " + b.inning + ", " + outsText(s.outs || 0) + ", " + basesText(s.bases) + ", " + lead) + "</p>" +
        "<p>" + esc(b.text) + "</p><p>" + esc(b.bat_team) + " " + pct(b.before) + "% to " + pct(b.after) + "% (" + signed(b.swing) + ")" +
        (isNum(b.li) ? ", LI " + b.li.toFixed(2) : "") + "</p>" + vslot("big", b.ab) + "</div></li>";
    }).join("");
    return labelled(ix, "scores_mlb_wp", '<ol class="sc-bigs">' + rows + "</ol>", "div", "sc-block-num");
  }
  function starsBlock(g, ix) {
    var head = '<h3>Stars of the Game</h3><p class="sc-dim"><a href="#about">A rule, not an award</a></p>';
    if (!g.stars || !g.stars.length) return head + '<p class="sc-dim">' + esc(g.stars_reason || "Stars post when the game is final.") + "</p>";
    var rows = g.stars.map(function (s) {
      return '<li><span class="sc-rank">' + s.rank + "</span><div><p><b>" + player(s.id, s.name) + "</b> " + esc(s.team) +
        ", " + esc(signed3(s.score)) + (s.basis === "runs" ? " (runs prevented)" : " (win probability added)") + "</p>" +
        '<p class="sc-dim">' + esc(s.why || "") + "</p>" + vslot("star", s.id) + "</div></li>";
    }).join("");
    var note = g.first_star_note ? '<p class="sc-note">First star: top player on the winning team.</p>' : "";
    return head + labelled(ix, "scores_stars_rule", '<ol class="sc-stars">' + rows + "</ol>" + note, "div", "sc-block-num");
  }
  function scoringBlock(g, ix) {
    var by = {};
    (g.plays || []).forEach(function (p) { by[p.ab] = p; });
    var c = g.card, rows = (g.scoring || []).map(function (ab) {
      var p = by[ab];
      if (!p) return "";
      return "<li><b>" + esc(half3(p.half) + " " + p.inning) + "</b> " + esc(p.text) + " " +
        esc((c.away.code || c.away.short) + " " + p.away + ", " + (c.home.code || c.home.short) + " " + p.home) +
        (isNum(p.swing) ? " (" + signed(p.swing) + ")" : "") + "</li>";
    }).join("");
    if (!rows) return "";
    return "<h3>Scoring</h3>" + labelled(ix, "scores_mlb_wp", '<ul class="sc-scoring">' + rows + "</ul>", "div", "sc-block-num");
  }
  function summaryTab(g, ix) {
    var live = g.card.state !== "final";
    var chart = regRow(ix, "scores_mlb_wp") && g.wp && g.wp.series && g.wp.series.length
      ? labelled(ix, "scores_mlb_wp",
        '<div class="sc-wp-frame" tabindex="0" role="img" aria-label="' + esc(chartAria(g)) + '"></div>' + chartTable(g), "figure", "sc-wp")
      : "";
    var o = "<h3>Win probability</h3><p class=\"sc-dim\">MLB's model, after each plate appearance" + (live ? ", so far" : "") + "</p>" + chart;
    o += "<h3>Biggest plays</h3><p class=\"sc-dim\">The five plate appearances that moved win probability most" + (live ? ", so far" : "") + "</p>";
    o += regRow(ix, "scores_biggest_plays_rule") ? labelled(ix, "scores_biggest_plays_rule", bigRows(g, ix, live), "div", "sc-rule") : bigRows(g, ix, live);
    if (g.card.state === "final") o += starsBlock(g, ix) + vslot("game", 0);
    o += scoringBlock(g, ix);
    return o;
  }
  function chartTable(g) {
    var by = {}, home = g.card.home.code || g.card.home.short;
    (g.plays || []).forEach(function (p) { by[p.ab] = p; });
    var rows = (g.wp.series || []).map(function (r) {
      var p = by[r[0]];
      return "<tr><td>" + esc(half3(r[2]) + " " + r[1]) + "</td><td>" + esc(p ? p.text : "") + "</td><td>" +
        (isNum(r[3]) ? pct(r[3]) + "%" : "") + "</td><td>" + esc(signed(r[4])) + "</td></tr>";
    }).join("");
    return '<details class="sc-twin"><summary>Table</summary><div class="sc-scroll"><table class="sc-tbl"><thead><tr>' +
      '<th scope="col">Inning</th><th scope="col">Plate appearance</th><th scope="col">' + esc(home) +
      ' win probability after</th><th scope="col">Swing</th></tr></thead><tbody>' + rows + "</tbody></table></div></details>";
  }
  function boxTab(g, ix) {
    if (!g.box) return '<p class="sc-dim">The box score posts after first pitch.</p>';
    var c = g.card, o = "";
    ["away", "home"].forEach(function (side) {
      var b = g.box[side] || {}, code = c[side].code || c[side].short;
      var bat = (b.batting || []).map(function (r) {
        return '<tr><th scope="row" class="sc-name">' + player(r.id, r.name) + (r.debut ? ' <span class="sc-chip">MLB debut</span>' : "") +
          ' <span class="sc-dim">' + esc(r.pos || "") + "</span></th><td>" + r.ab + "</td><td>" + r.r + "</td><td>" + r.h + "</td><td>" + r.rbi +
          "</td><td>" + r.bb + "</td><td>" + r.k + "</td><td>" + f1(r.p_pa) + "</td><td>" + esc(signed3(r.wpa)) + "</td><td>" + f2(r.pli) + "</td></tr>";
      }).join("");
      var pit = (b.pitching || []).map(function (r) {
        var d = r.dec || {}, mk = [];
        if (d.w) mk.push("W"); if (d.l) mk.push("L"); if (d.sv) mk.push("S"); if (d.hld) mk.push("H"); if (d.bs) mk.push("BS");
        return '<tr><th scope="row" class="sc-name">' + player(r.id, r.name) + (mk.length ? " (" + mk.join(", ") + ")" : "") +
          (r.position_player ? ' <span class="sc-dim">position player</span>' : "") + (r.debut ? ' <span class="sc-chip">MLB debut</span>' : "") +
          "</th><td>" + Math.floor(r.outs / 3) + "." + (r.outs % 3) + "</td><td>" + r.h + "</td><td>" + r.r + "</td><td>" + r.er + "</td><td>" + r.bb +
          "</td><td>" + r.k + "</td><td>" + r.hr + "</td><td>" + r.pc + "-" + r.strikes + "</td><td>" + f1(r.p_ip) + "</td><td>" + esc(signed3(r.wpa)) +
          "</td><td>" + f2(r.pli) + "</td></tr>";
      }).join("");
      o += "<h3>" + esc(code) + "</h3>" + labelled(ix, "scores_mlb_wp",
        '<div class="sc-scroll"><table class="sc-tbl sc-box"><caption class="sr-only">' + esc(code) + ' batting</caption><thead><tr><th scope="col" class="sc-name">Batting</th>' +
        '<th scope="col">AB</th><th scope="col">R</th><th scope="col">H</th><th scope="col">RBI</th><th scope="col">BB</th><th scope="col">K</th><th scope="col"><abbr title="Pitches per plate appearance">P/PA</abbr></th><th scope="col">WPA</th><th scope="col">pLI</th></tr></thead><tbody>' + bat + "</tbody></table></div>" +
        '<div class="sc-scroll"><table class="sc-tbl sc-box"><caption class="sr-only">' + esc(code) + ' pitching</caption><thead><tr><th scope="col" class="sc-name">Pitching</th>' +
        '<th scope="col">IP</th><th scope="col">H</th><th scope="col">R</th><th scope="col">ER</th><th scope="col">BB</th><th scope="col">K</th><th scope="col">HR</th><th scope="col">PC-ST</th><th scope="col"><abbr title="Pitches per inning pitched">P/IP</abbr></th><th scope="col">WPA</th><th scope="col">pLI</th></tr></thead><tbody>' + pit + "</tbody></table></div>",
        "div", "sc-block-num") + ((b.notes || []).length ? '<p class="sc-dim">' + esc(b.notes.join(" ")) + "</p>" : "");
    });
    return o;
  }
  function playsTab(g, ix, focusAb) {
    if (!g.plays || !g.plays.length) return '<p class="sc-dim">Plate appearances post after first pitch.</p>';
    var c = g.card, groups = [], cur = null;
    g.plays.forEach(function (p) {
      var key = p.inning + p.half;
      if (!cur || cur.key !== key) { cur = { key: key, inning: p.inning, half: p.half, rows: [] }; groups.push(cur); }
      cur.rows.push(p);
    });
    var home = c.home.code || c.home.short;
    var o = groups.map(function (gr) {
      var rows = gr.rows.map(function (p) {
        var rev = (p.reviews || []).map(function (r) {
          return (r.by ? r.by + " " : "") + (r.kind ? lower(r.kind) + " " : "") + "review, call " + (r.overturned ? "overturned" : "stands");
        }).join(". ");
        return '<li class="sc-pa" id="sc-pa-' + p.ab + '" tabindex="-1"' + (p.ab === focusAb ? ' data-focus="1"' : "") + "><p>" + esc(p.text) + "</p>" +
          '<p class="sc-dim">' + esc(outsText(p.outs) + ", " + basesText(p.bases) + ". " + (c.away.code || c.away.short) + " " + p.away + ", " +
          home + " " + p.home + ".") + (isNum(p.wp) ? " " + esc(home + " " + pct(p.wp) + "%") + (isNum(p.swing) ? " (" + esc(signed(p.swing)) + ")" : "") : "") +
          (isNum(p.li) ? ", LI " + p.li.toFixed(2) : "") + (rev ? ". " + esc(rev) + "." : "") + "</p>" + vslot("pa", p.ab) + "</li>";
      }).join("");
      var open = focusAb == null || gr.rows.some(function (p) { return p.ab === focusAb; });
      return "<details class=\"sc-half\"" + (open ? " open" : "") + "><summary>" + esc((gr.half === "bottom" ? "Bottom " : "Top ") + ordinal(gr.inning)) +
        "</summary><ol class=\"sc-pas\">" + rows + "</ol></details>";
    }).join("");
    return labelled(ix, "scores_mlb_wp", o, "div", "sc-block-num");
  }
  function vslot(m, k) { return '<div class="sc-v" data-m="' + m + '" data-k="' + k + '"></div>'; }
  function lineupsTab(g) {
    var c = g.card, L = g.lineups || {};
    return ["away", "home"].map(function (side) {
      var rows = (L[side] || []).map(function (p) { return "<li>" + player(p.id, p.name) + ' <span class="sc-dim">' + esc(p.pos || "") + "</span></li>"; }).join("");
      return "<h3>" + esc(c[side].code || c[side].short) + "</h3>" + (rows ? '<ol class="sc-lineup">' + rows + "</ol>" : '<p class="sc-dim">Lineups not posted yet</p>');
    }).join("");
  }
  function previewTab(c) {
    var o = "<h3>Before first pitch</h3><dl class=\"sc-dl\">";
    o += "<dt>First pitch</dt><dd>" + esc(startTime(c)) + "</dd>";
    o += "<dt>Venue</dt><dd>" + esc(c.venue && c.venue.name || "") + "</dd>";
    ["away", "home"].forEach(function (s) {
      o += "<dt>" + esc((c[s].code || c[s].short) + " probable") + "</dt><dd>" + (c[s].probable ? player(c[s].probable.id, c[s].probable.name) + (probableText(c[s].probable).indexOf(",") > 0 ? esc(probableText(c[s].probable).slice(probableText(c[s].probable).indexOf(","))) : "") : "Probable not announced") + "</dd>";
    });
    o += "<dt>Lineups</dt><dd>" + (c.away.lineup_posted && c.home.lineup_posted ? "Lineups posted" : "Lineups not posted yet") + "</dd>";
    if (c.series && c.series.text) o += "<dt>Series</dt><dd>" + esc(c.series.text) + "</dd>";
    if (c.tv && c.tv.length) o += "<dt>TV</dt><dd>" + esc(c.tv.join(", ")) + "</dd>";
    if (c.weather) o += "<dt>Weather</dt><dd>" + esc([c.weather.condition, c.weather.temp ? c.weather.temp + " F" : "", c.weather.wind ? "wind " + c.weather.wind : ""].filter(Boolean).join(", ")) + "</dd>";
    return o + "</dl>";
  }
  function ledger(map, fmt) {
    var out = [];
    for (var k in (map || {})) out.push(k + " " + fmt(map[k]));
    return out.join(". ") + (out.length ? "." : "");
  }
  function infoTab(g) {
    var I = g.info;
    if (!I) return '<p class="sc-dim">Game info posts when the game is final.</p>';
    var o = '<dl class="sc-dl">';
    if (I.umpires && I.umpires.length) o += "<dt>Umpires</dt><dd>" + I.umpires.map(function (u) { return esc(u.pos + ": " + u.name); }).join("<br>") + "</dd>";
    if (I.weather) o += "<dt>Weather</dt><dd>" + esc([I.weather.condition, I.weather.temp ? I.weather.temp + " F" : ""].filter(Boolean).join(", ")) + "</dd>";
    if (I.wind) o += "<dt>Wind</dt><dd>" + esc(I.wind) + "</dd>";
    if (I.first_pitch && ms(I.first_pitch) != null) o += "<dt>First pitch</dt><dd>" + esc(clock(ms(I.first_pitch))) + "</dd>";
    if (isNum(I.duration_min)) o += "<dt>Time of game</dt><dd>" + Math.floor(I.duration_min / 60) + ":" + (I.duration_min % 60 < 10 ? "0" : "") + (I.duration_min % 60) + "</dd>";
    if (isNum(I.delay_min) && I.delay_min > 0) o += "<dt>Delay</dt><dd>" + I.delay_min + " minutes</dd>";
    if (isNum(I.attendance)) o += "<dt>Attendance</dt><dd>" + comma(I.attendance) + "</dd>";
    var v = I.venue || {};
    if (v.name) o += "<dt>Venue</dt><dd>" + esc(v.name) + "</dd>";
    if (v.roof) o += "<dt>Roof</dt><dd>" + esc(v.roof) + "</dd>";
    if (v.surface) o += "<dt>Surface</dt><dd>" + esc(v.surface) + "</dd>";
    if (v.dims) {
      var dm = v.dims, parts = [["LF", dm.lf], ["LC", dm.lcf], ["CF", dm.cf], ["RC", dm.rcf], ["RF", dm.rf]].filter(function (p) { return isNum(p[1]); });
      if (parts.length) o += "<dt>Dimensions</dt><dd>" + esc(parts.map(function (p) { return p[0] + " " + p[1]; }).join(", ")) + "</dd>";
    }
    if (isNum(v.elevation_ft)) o += "<dt>Elevation</dt><dd>" + comma(v.elevation_ft) + " ft</dd>";
    if (I.abs) o += "<dt>ABS challenges</dt><dd>" + esc(ledger(I.abs, function (a) { return a.won + " won, " + a.lost + " lost"; })) + "</dd>";
    if (I.reviews) o += "<dt>Replay reviews</dt><dd>" + esc(ledger(I.reviews, function (a) { return a.used + " used, " + a.remaining + " left"; })) + "</dd>";
    if (I.mound_visits) o += "<dt>Mound visits</dt><dd>" + esc(ledger(I.mound_visits, function (a) { return a.used + " used, " + a.remaining + " left"; })) + "</dd>";
    o += "</dl>";
    if (g.links && g.links.gameday && /^https:\/\/www\.mlb\.com\/gameday\/\d+$/.test(g.links.gameday)) {
      o += '<p><a href="' + esc(g.links.gameday) + '" rel="noopener noreferrer" target="_blank">Gameday on MLB.com<span class="sr-only"> (opens MLB.com)</span></a></p>';
    }
    return o;
  }
  function tabsFor(c, hasGame) {
    var pre = c.state === "scheduled" || c.state === "pregame" || (c.state === "delayed" && !(c.sit && c.sit.inning));
    var t = pre ? [["preview", "Preview"]] : [["summary", "Summary"]];
    if (hasGame && !pre) t.push(["box", "Box score"], ["plays", "Plays"]);
    t.push(["lineups", "Lineups"]);
    if (c.state === "final" && hasGame) t.push(["info", "Game info"]);
    return t;
  }

  // ------------------------------------------------------------ the app
  function store(key, val) {
    try {
      if (val === undefined) return window.localStorage.getItem(key);
      window.localStorage.setItem(key, val);
    } catch (e) { /* storage unavailable: the page works without it */ }
    return null;
  }
  function mineSet() {
    var v = null;
    try { v = JSON.parse(store("eephus.scores.mine") || "[]"); } catch (e) { v = []; }
    return Array.isArray(v) ? v : [];
  }

  function boot(root) {
    var L = makeLoader(function (u, o) { return fetch(u, o); });
    var app = { route: parseRoute(location.hash), stale: null, date: null, dateDoc: null, shown: {}, pending: [],
      timer: null, errors: 0, lastFetch: 0, paused: store("eephus.scores.paused") === "1", announceAt: 0, queue: null,
      prev: {}, focusPk: null, game: null };
    var announcer = document.createElement("div");
    announcer.className = "sr-only"; announcer.setAttribute("aria-live", "polite");
    root.parentNode.insertBefore(announcer, root);
    var St = window.EephusState;
    function state(kind, msg) {
      if (St && St.render) St.render(root, kind, esc(msg));
      else root.innerHTML = '<p role="status">' + esc(msg) + "</p>";
    }
    state("loading", "Loading scores.");

    function announce(msg) {
      var now = Date.now();
      app.queue = msg;
      if (now - app.announceAt >= ANNOUNCE_GAP_MS) flush();
      else if (!app.qtimer) app.qtimer = setTimeout(flush, ANNOUNCE_GAP_MS - (now - app.announceAt));
    }
    function flush() {
      app.qtimer = null;
      if (!app.queue) return;
      announcer.textContent = app.queue; app.queue = null; app.announceAt = Date.now();
    }
    function watchEvents(doc) {
      var mine = mineSet();
      (doc.games || []).forEach(function (c) {
        var p = app.prev[c.pk];
        app.prev[c.pk] = c;
        if (!p) return;
        var open = app.route.view === "game" && app.route.game === c.pk;
        var follow = mine.indexOf(c.away.code) >= 0 || mine.indexOf(c.home.code) >= 0;
        if (!open && !follow) return;
        var A = c.away.code || c.away.short, H = c.home.code || c.home.short;
        if (p.state !== "final" && c.state === "final") announce("Final: " + A + " " + c.away.r + ", " + H + " " + c.home.r + ".");
        else if (p.state !== "live" && c.state === "live") announce("Game started: " + A + " at " + H + ".");
        else if (c.state === "live" && (c.away.r !== p.away.r || c.home.r !== p.home.r)) {
          var who = c.away.r !== p.away.r ? A : H;
          announce(who + " scores. " + A + " " + c.away.r + ", " + H + " " + c.home.r +
            (c.sit && c.sit.inning ? ", " + halfWord(c.sit.half) + " " + ordinal(c.sit.inning) : "") + ".");
        }
      });
    }

    // ---- polling
    function interval() {
      var L0 = L.state.latest, j = (L0 && L0.job) || {};
      if (app.errors) return BACKOFF[Math.min(app.errors - 1, BACKOFF.length - 1)];
      var live = liveOnDate(L0, app.date || (L0 && L0.today));
      return live ? (j.poll_live_s || POLL_LIVE_S) : (j.poll_idle_s || POLL_IDLE_S);
    }
    function schedule() {
      clearTimeout(app.timer);
      if (app.paused && !app.errors) return;
      if (document.visibilityState === "hidden") return;
      app.timer = setTimeout(poll, interval() * 1000);
    }
    function poll() {
      app.lastFetch = Date.now();
      return L.latest().then(function () {
        app.errors = 0;
        return refresh(false);
      }).catch(function () {
        app.errors++;
        if (!app.dateDoc) state("failed", STALE.S4);
        else stamp();
      }).then(schedule);
    }
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") { clearTimeout(app.timer); return; }
      if (Date.now() - app.lastFetch > (POLL_LIVE_S * 1000) && !app.paused) poll();
      else schedule();
    });

    // ---- rendering
    function refresh(nav) {
      var r = app.route, Lt = L.state.latest;
      app.stale = scoresStaleState(Lt, L.serverNow(), r.date || Lt.today);
      if (r.view === "about") { renderAbout(); return null; }
      var d = r.date || (r.view === "game" && app.gameDate) || Lt.today;
      if (d !== app.date) { app.date = d; app.dateDoc = null; app.shown = {}; nav = true; }
      return L.date(d).then(function (doc) {
        if (doc) watchEvents(doc);
        if (r.view === "game") return renderGame(doc, nav);
        renderDay(doc, nav);
        return null;
      });
    }
    function stampHTML() {
      var s = app.stale || {};
      return '<span class="sc-stamp-text">' + esc(s.sentence || "") + "</span>" +
        '<button type="button" class="sc-btn sc-pause" aria-pressed="' + (app.paused ? "true" : "false") + '">' +
        (app.paused ? "Resume live updates" : "Pause live updates") + "</button>";
    }
    function stamp() {
      var el = root.querySelector(".sc-stamp");
      if (el) el.innerHTML = stampHTML();
      var b = root.querySelector(".sc-banner");
      if (b) { b.hidden = !(app.stale && app.stale.code === "S3"); b.textContent = app.stale && app.stale.code === "S3" ? app.stale.sentence : ""; }
    }
    function strip(d) {
      var Lt = L.state.latest, win = Object.keys(Lt.window || {}).sort(), today = Lt.today;
      if (win.indexOf(d) < 0) { win.push(d); win.sort(); }
      var chips = win.map(function (ds) {
        var w = (Lt.window || {})[ds], rel = ds === today ? "Today" : ds === addDays(today, -1) ? "Yesterday" : ds === addDays(today, 1) ? "Tomorrow" : shortDay(ds);
        var n = w && isNum(w.n) ? '<span class="sc-chip-n">' + w.n + (w.n === 1 ? " game" : " games") + "</span>" : "";
        return '<li><a class="sc-day' + (ds === d ? " is-on" : "") + '" href="' + dayHash(app.route, { date: ds }) + '"' +
          (ds === d ? ' aria-current="date"' : "") + '><span class="sc-chip-d">' + esc(rel) + "</span>" + n + "</a></li>";
      }).join("");
      var seasons = ((L.state.index && L.state.index.seasons) || []).map(function (s) { return s.season; }).sort();
      var min = seasons.length ? seasons[0] + "-01-01" : "", max = win[win.length - 1];
      return '<nav class="sc-strip" aria-label="Dates"><a class="sc-arrow" href="' + dayHash(app.route, { date: addDays(d, -1) }) + '" aria-label="Previous day">&lsaquo;</a>' +
        '<ul class="sc-days">' + chips + '</ul><a class="sc-arrow" href="' + dayHash(app.route, { date: addDays(d, 1) }) + '" aria-label="Next day">&rsaquo;</a>' +
        '<label class="sc-pickdate"><span class="sr-only">Choose a date</span><input type="date" class="sc-dateinput" value="' + esc(d) + '"' +
        (min ? ' min="' + min + '"' : "") + (max ? ' max="' + esc(max) + '"' : "") + "></label></nav>";
    }
    function filters(d) {
      var w = (L.state.latest.window || {})[d], r = app.route;
      var cnt = function (k) { return w && isNum(w[k]) ? " " + w[k] : ""; };
      var f = [["all", "All", cnt("n")], ["live", "Live", cnt("live")], ["upcoming", "Upcoming", cnt("pre")], ["final", "Final", cnt("final")]];
      return '<div class="sc-filters" role="group" aria-label="Filters">' + f.map(function (x) {
        return '<button type="button" class="sc-btn" data-f="' + x[0] + '" aria-pressed="' + (r.f === x[0]) + '">' + x[1] + x[2] + "</button>";
      }).join("") + ["AL", "NL"].map(function (lg) {
        return '<button type="button" class="sc-btn" data-lg="' + lg + '" aria-pressed="' + (r.lg === lg) + '">' + lg + "</button>";
      }).join("") + '<button type="button" class="sc-btn" data-mine="1" aria-pressed="' + r.mine + '">My teams</button></div>';
    }
    function visible(c) {
      var r = app.route, s = c.state;
      if (r.f === "live" && !(s === "live" || (s === "delayed" && c.sit && c.sit.inning))) return false;
      if (r.f === "upcoming" && !(s === "scheduled" || s === "pregame" || (s === "delayed" && !(c.sit && c.sit.inning)))) return false;
      if (r.f === "final" && s !== "final") return false;
      if (r.lg) {
        var al = AL_IDS.indexOf(c.away.team_id) >= 0 || AL_IDS.indexOf(c.home.team_id) >= 0;
        var nl = AL_IDS.indexOf(c.away.team_id) < 0 || AL_IDS.indexOf(c.home.team_id) < 0;
        if (r.lg === "AL" ? !al : !nl) return false;
      }
      if (r.mine) { var m = mineSet(); if (m.indexOf(c.away.code) < 0 && m.indexOf(c.home.code) < 0) return false; }
      return true;
    }
    function article(c, gone) {
      return '<article class="sc-card is-' + c.state + " slot-" + slotOf(c.state) + '" data-pk="' + c.pk + '" data-state="' + c.state + '"' +
        (visible(c) ? "" : " hidden") + ">" + cardHTML(c, L.state.index, app.stale, gone) + "</article>";
    }
    function railHTML(doc) {
      var tops = (doc && doc.day_top_plays) || [];
      if (!tops.length || !regRow(L.state.index, "scores_mlb_wp")) return "";
      var rows = tops.map(function (t) {
        return '<li><a href="#game=' + t.pk + "&play=" + t.ab + '">' + esc(t.text) + "</a> " + esc(t.bat_team + " " + pct(t.before) + "% to " + pct(t.after) + "% (" + signed(t.swing) + ")") +
          (t.live ? ' <span class="sc-chip">so far</span>' : "") + "</li>";
      }).join("");
      return '<aside class="sc-rail" aria-label="Biggest plays today"><h2>Biggest plays today</h2>' +
        labelled(L.state.index, "scores_mlb_wp", '<ol class="sc-railplays">' + rows + "</ol>", "div", "sc-block-num") + "</aside>";
    }
    function emptyDay(d) {
      var Lt = L.state.latest, win = Object.keys(Lt.window || {}).sort();
      if (win.length && d > win[win.length - 1]) return "This page lists games up to seven days ahead.";
      var msg = "No MLB games on " + longDate(d) + ".";
      if (d >= Lt.today && Lt.next_game_date && validDate(Lt.next_game_date) && Lt.next_game_date > d) {
        msg += " Next scheduled game: " + MONTHS[dayOf(Lt.next_game_date).getUTCMonth()] + " " + dayOf(Lt.next_game_date).getUTCDate() + ".";
      }
      return msg;
    }
    function renderDay(doc, nav) {
      var d = app.date;
      if (nav || !root.querySelector(".sc-day-view")) {
        root.innerHTML = '<div class="sc-day-view"><p class="sc-banner" role="note" hidden></p>' + strip(d) + filters(d) +
          '<div class="sc-stamp" role="status" aria-live="off"></div><div class="sc-layout"><div class="sc-grid-wrap">' +
          '<div class="sc-grid"></div><div class="sc-empty"></div><div class="sc-late"></div></div><div class="sc-railslot"></div></div>' +
          '<p class="sc-about-link"><a href="#about">About these numbers</a></p></div>';
        app.shown = {};
      }
      stamp();
      var grid = root.querySelector(".sc-grid"), empty = root.querySelector(".sc-empty"), late = root.querySelector(".sc-late");
      var games = (doc && doc.games) || [];
      var known = Object.keys(app.shown).length > 0;
      var fresh = [];
      var byPk = {};
      games.forEach(function (c) { byPk[c.pk] = c; });
      if (!known) {
        grid.innerHTML = games.map(function (c) { app.shown[c.pk] = c; return article(c, false); }).join("");
      } else {
        games.forEach(function (c) {
          if (!app.shown[c.pk]) { fresh.push(c); return; }
          var el = grid.querySelector('article[data-pk="' + c.pk + '"]');
          if (!el) return;
          var html = cardHTML(c, L.state.index, app.stale, false);
          if (el._html !== html) {
            el.className = "sc-card is-" + c.state + " slot-" + slotOf(c.state);
            el.setAttribute("data-state", c.state);
            el.innerHTML = html; el._html = html;
          }
          app.shown[c.pk] = c;
          el.hidden = !visible(c);
        });
        Object.keys(app.shown).forEach(function (pk) {
          if (byPk[pk]) return;
          var el = grid.querySelector('article[data-pk="' + pk + '"]');
          if (el && !el._gone) { el._gone = true; el.innerHTML = cardHTML(app.shown[pk], L.state.index, app.stale, true); }
        });
      }
      Array.prototype.forEach.call(grid.querySelectorAll("article"), function (el) {
        if (!el._html) el._html = el.innerHTML;
      });
      app.pending = fresh;
      late.innerHTML = fresh.length ? '<button type="button" class="sc-btn sc-showlate">' + (fresh.length === 1 ? "1 more game on this date. Show it" : fresh.length + " more games on this date. Show them") + "</button>" : "";
      var anyVisible = games.some(visible);
      if (!games.length) {
        if (St && St.html) empty.innerHTML = St.html("empty", esc(emptyDay(d)));
        else empty.innerHTML = '<p role="status">' + esc(emptyDay(d)) + "</p>";
      } else if (!anyVisible) {
        empty.innerHTML = St && St.html ? St.html("empty", "No games match these filters.") : "<p>No games match these filters.</p>";
      } else empty.innerHTML = "";
      root.querySelector(".sc-railslot").innerHTML = railHTML(doc);
      if (nav && app.focusPk != null) {
        var back = grid.querySelector('article[data-pk="' + app.focusPk + '"] .sc-stretch');
        if (back) { back.focus(); if (app.scrollY != null) window.scrollTo(0, app.scrollY); }
        app.focusPk = null;
      }
      app.dateDoc = doc || { games: [] };
    }
    function findCard(doc, pk) {
      var gs = (doc && doc.games) || [];
      for (var i = 0; i < gs.length; i++) if (gs[i].pk === pk) return gs[i];
      return null;
    }
    function renderGame(doc, nav) {
      var r = app.route, card = findCard(doc, r.game);
      var p = card ? (card.rev ? L.game(r.game, card.rev) : Promise.resolve(null)) : L.game(r.game, null).catch(function () { return null; });
      return p.then(function (g) {
        if (!card && g && g.card) {
          card = g.card;
          var gd = String(card.start || "").slice(0, 10);
          if (validDate(gd) && gd !== app.date) { app.gameDate = gd; }
        }
        if (!card) {
          if (St && St.render) St.render(root, "empty", "No game with that id in these files.");
          else root.innerHTML = "<p>No game with that id in these files.</p>";
          return;
        }
        if (g && g.card) card = g.card.rev === card.rev ? g.card : card;
        app.game = g;
        if (!LINKS && window.EEPHUS_HUB && window.EEPHUS_HUB.links && !app.linksAsked) {
          app.linksAsked = true;
          window.EEPHUS_HUB.links().then(function (Lk) { LINKS = Lk || null; if (app.route.view === "game") paintGame(card, app.game, true); });
        }
        paintGame(card, g, nav);
      });
    }
    var V = null, VP = null;
    function video(g) {
      VP = VP || new Promise(function (ok, no) {
        var s = document.createElement("script");
        s.src = "/assets/scores-video.js?v=" + (root.getAttribute("data-vv") || "");
        s.onload = function () { ok(V = window.EephusScoresVideo); }; s.onerror = no;
        document.head.appendChild(s);
      });
      VP.then(function (v) { if (app.game === g) v.mount(root, g, L.state.index, app.route.play); }, function () {});
    }
    function paintGame(c, g, nav) {
      var ix = L.state.index, r = app.route;
      if (!nav && V && V.isOpen(root)) { V.held(root, g, function () { paintGame(c, g, false); }); stamp(); return; }
      var tabs = tabsFor(c, !!g), tab = r.tab;
      if (!tab || !tabs.some(function (t) { return t[0] === tab; })) tab = tabs[0][0];
      var A = c.away, H = c.home, mine = mineSet();
      var follow = [A, H].filter(function (s) { return s.code; }).map(function (s) {
        var on = mine.indexOf(s.code) >= 0;
        return '<button type="button" class="sc-btn sc-follow" data-code="' + esc(s.code) + '" aria-pressed="' + on + '">' + (on ? "Following " : "Follow ") + esc(s.code) + "</button>";
      }).join("");
      var head = '<div class="sc-game-view"><p class="sc-back"><a href="' + dayHash(app.route, { date: app.date }) + '">All games on ' + esc(longDate(app.date)) + "</a></p>" +
        '<div class="sc-stamp" role="status" aria-live="off"></div>' +
        '<h2 class="sc-game-h" tabindex="-1">' + clubLink(A) + " " + (isNum(A.r) ? A.r : "") + " at " + clubLink(H) + " " + (isNum(H.r) ? H.r : "") + "</h2>" +
        '<p class="sc-state-big">' + esc(stateLine(c, c.state === "live" ? app.stale : null)) + "</p>" +
        (c.series && c.series.text ? '<p class="sc-dim">' + esc(c.series.text) + "</p>" : "") +
        '<p class="sc-dim">' + esc((c.venue && c.venue.name ? c.venue.name + ", " : "") + startTime(c)) + "</p>" +
        lineScore(c) + '<div class="sc-follows">' + follow + "</div>" +
        '<div class="sc-tabs" role="tablist" aria-label="Game sections">' + tabs.map(function (t) {
          return '<button type="button" role="tab" class="sc-tab" id="sc-tab-' + t[0] + '" aria-controls="sc-panel" data-tab="' + t[0] + '" aria-selected="' + (t[0] === tab) + '" tabindex="' + (t[0] === tab ? "0" : "-1") + '">' + t[1] + "</button>";
        }).join("") + '</div><div class="sc-panel" id="sc-panel" role="tabpanel" aria-labelledby="sc-tab-' + tab + '">';
      var body = "";
      if (tab === "preview") body = previewTab(c) + lineupsTab(g || { card: c, lineups: {} });
      else if (!g) body = '<p class="sc-dim">The game file posts after first pitch.</p>';
      else if (tab === "summary") body = summaryTab(g, ix);
      else if (tab === "box") body = boxTab(g, ix);
      else if (tab === "plays") body = playsTab(g, ix, r.play);
      else if (tab === "lineups") body = lineupsTab(g);
      else if (tab === "info") body = infoTab(g);
      var keepScroll = !nav ? window.scrollY : null;
      var pin = root.querySelector(".sc-wp-frame");
      var pinned = pin ? pin._pin : null;
      root.innerHTML = head + body + "</div></div>";
      stamp();
      var fr = root.querySelector(".sc-wp-frame");
      if (fr && g) { fr._pin = pinned; mountChart(root, g, c.state !== "final"); }
      if (g) video(g);
      if (nav) {
        var f = r.play != null ? root.querySelector('[data-focus="1"]') : null;
        (f || root.querySelector(".sc-game-h")).focus();
        if (f && f.scrollIntoView) f.scrollIntoView({ block: "center" });
      } else if (keepScroll != null) window.scrollTo(0, keepScroll);
    }
    function renderAbout() {
      var ix = L.state.index || {}, acc = (ix.accuracy && ix.accuracy.mlb_wp) || {}, rules = ix.rules || {};
      var o = '<div class="sc-about"><p class="sc-back"><a href="' + dayHash(app.route, { date: app.date || L.state.latest.today }) + '">Back to scores</a></p>' +
        '<h2 tabindex="-1">About these numbers</h2>';
      var p1 = "Win probability is MLB's live model, read from its public feed after every plate appearance.";
      var pv = acc.pregame_values || {}, keys = Object.keys(pv);
      if (keys.length && keys.every(function (k) { return k === "500"; })) {
        p1 += " It starts every game at 50 percent, so it is not a pregame forecast.";
      }
      p1 += " Inside a game it moves with the situation and, by this site's own check, also carries some team strength; it can trail the score by one play.";
      if (isNum(acc.feed_brier) && isNum(acc.base_rate_brier) && isNum(acc.n_plays) && (acc.seasons || []).length) {
        p1 += " In this site's own check over " + comma(acc.n_plays) + " regular-season plays from the " +
          (acc.seasons.length > 1 ? acc.seasons.slice(0, -1).join(", ") + " and " + acc.seasons[acc.seasons.length - 1] + " seasons" : acc.seasons[0] + " season") +
          " (no postseason game is in the check), it scored a Brier of " + acc.feed_brier.toFixed(4) + ", against " + acc.base_rate_brier.toFixed(4) +
          " for a constant base rate (lower is better).";
      }
      p1 += " Where MLB's feed has no number for a plate appearance, the line has a gap.";
      o += labelled(ix, "scores_mlb_wp", esc(p1), "p") || "<p>" + esc(p1) + "</p>";
      var s = rules.stars || {};
      if (s.rule) {
        var p2 = "Stars of the Game is a rule, not an award. Each player is ranked by win probability added, from MLB's live model: hitters by their plate appearances, pitchers by the batters they faced.";
        if (isNum(s.min_outs)) p2 += " A pitcher who records " + s.min_outs + " or more outs without losing win probability is credited instead with his runs prevented against the league rate when that is larger, so a starter's work in a lopsided game still counts.";
        if (s.first_star_winner) p2 += " The first star comes from the winning team, so he can rank below the second star.";
        p2 += " Ties go to the player whose plate appearances carried more leverage. Fielding, and base running inside a plate appearance, are not credited to anyone.";
        o += "<h3>Stars of the Game</h3><p>" + esc(p2) + "</p>";
      }
      var pl = rules.plays || {};
      if (pl.rule) {
        var words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
        o += "<h3>Biggest plays</h3><p>" + esc("The " + (words[pl.n] || pl.n) + " plate appearances that moved MLB's win probability most.") + "</p>";
        var w = (L.state.latest.window || {})[L.state.latest.today];
        if (w && isNum(w.clips_of) && w.clips_of > 0 && isNum(w.clips_matched)) {
          o += "<p>" + esc("Clips matched today: " + w.clips_matched + " of " + w.clips_of + " biggest plays.") + "</p>";
        }
      }
      o += "<h3>Source</h3><p>Scores, box scores and play data come from MLB's public StatsAPI feed.</p>";
      if (ix.copyright) o += '<p class="sc-dim">' + esc(ix.copyright) + "</p>";
      root.innerHTML = o + "</div>";
      var h = root.querySelector("h2"); if (h) h.focus();
    }

    // ---- events
    root.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target.closest("button, a") : null;
      if (!t) return;
      var r = app.route;
      if (t.matches(".sc-pause")) {
        app.paused = !app.paused; store("eephus.scores.paused", app.paused ? "1" : "0"); stamp();
        if (app.paused) clearTimeout(app.timer); else poll();
      } else if (t.hasAttribute("data-f")) { location.hash = dayHash(r, { f: t.getAttribute("data-f") }); }
      else if (t.hasAttribute("data-lg")) { location.hash = dayHash(r, { lg: r.lg === t.getAttribute("data-lg") ? null : t.getAttribute("data-lg") }); }
      else if (t.hasAttribute("data-mine")) { location.hash = dayHash(r, { mine: !r.mine }); }
      else if (t.matches(".sc-showlate")) {
        var grid = root.querySelector(".sc-grid");
        app.pending.forEach(function (c) { app.shown[c.pk] = c; grid.insertAdjacentHTML("beforeend", article(c, false)); });
        app.pending = []; root.querySelector(".sc-late").innerHTML = "";
      } else if (t.matches(".sc-follow")) {
        var code = t.getAttribute("data-code"), m = mineSet(), i = m.indexOf(code);
        if (i >= 0) m.splice(i, 1); else m.push(code);
        store("eephus.scores.mine", JSON.stringify(m));
        t.setAttribute("aria-pressed", String(i < 0)); t.textContent = (i < 0 ? "Following " : "Follow ") + code;
      } else if (t.matches(".sc-tab")) {
        location.hash = "#game=" + r.game + "&tab=" + t.getAttribute("data-tab");
      } else if (t.matches(".sc-stretch") || t.matches(".sc-up")) {
        app.focusPk = +t.closest("article").getAttribute("data-pk"); app.scrollY = window.scrollY;
      }
    });
    root.addEventListener("keydown", function (ev) {
      var t = ev.target;
      if (!t.matches || !t.matches(".sc-tab")) return;
      var all = Array.prototype.slice.call(root.querySelectorAll(".sc-tab")), i = all.indexOf(t);
      var j = ev.key === "ArrowRight" ? i + 1 : ev.key === "ArrowLeft" ? i - 1 : ev.key === "Home" ? 0 : ev.key === "End" ? all.length - 1 : null;
      if (j == null) return;
      ev.preventDefault();
      j = (j + all.length) % all.length;
      all[j].focus(); all[j].click();
    });
    root.addEventListener("change", function (ev) {
      if (ev.target.matches && ev.target.matches(".sc-dateinput") && validDate(ev.target.value)) {
        location.hash = dayHash(app.route, { date: ev.target.value });
      }
    });
    window.addEventListener("hashchange", function () {
      var prevView = app.route.view, prevGame = app.route.game;
      app.route = parseRoute(location.hash);
      var nav = prevView !== app.route.view || prevGame !== app.route.game;
      if (app.route.view !== "game") app.gameDate = null;
      if (!L.state.latest) return;
      if (app.route.view === "day" && prevView === "day") {
        var d = app.route.date || L.state.latest.today;
        if (d === app.date && root.querySelector(".sc-day-view")) {
          root.querySelector(".sc-filters").outerHTML = filters(d);
          Array.prototype.forEach.call(root.querySelectorAll(".sc-grid article"), function (el) {
            var c = app.shown[el.getAttribute("data-pk")];
            if (c) el.hidden = !visible(c);
          });
          renderDay(app.dateDoc, false);
          return;
        }
      }
      refresh(true || nav);
    });
    var rt = null;
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(function () { if (app.game && root.querySelector(".sc-wp-frame")) mountChart(root, app.game, app.game.card.state !== "final"); }, 150);
    });
    poll();
  }

  window.EephusScores = {
    scoresStaleState: scoresStaleState, parseRoute: parseRoute, makeLoader: makeLoader,
    validLatest: validLatest, liveOnDate: liveOnDate, clock: clock, monthDay: monthDay, pct: pct, signed: signed,
    stateLine: stateLine, cardHTML: cardHTML, chartSVG: chartSVG, chartAria: chartAria, STALE: STALE
  };
  function start() {
    var root = document.getElementById("scores-app-root");
    if (root) boot(root);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
