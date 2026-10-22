/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* The Scores / Standings slot at the top of the homepage MLB band (SCORES_7d,
   then HOME_6): a pure reader of the files /scores/ reads under /data/scores/,
   the job's latest file, the date files it names, the season index and the
   standings file. It computes no number of its own. One state at a time:
     games       live games, then today's games still to start (first pitch in
                 the reader's own time), then the latest day's finals;
     postseason  while the season index carries a bracket that is not over (or
                 ended within MAX_FINAL_AGE_DAYS): the current round's series
                 with their wins, then any live or still-to-start game;
     off season  nothing live, to come or recently final: the six division
                 leaders from the standings file, with its as-of date;
     unmeasured  the job's file is missing, not the job's, or older than
                 MAX_FINAL_AGE_DAYS: the pixel unmeasured box, with the date
                 of the last update when there is one.
   The MLB band's count line reads the same state. It polls every 60 s while a
   game is live and every 300 s while a game is still to start, and never while
   the tab is hidden. The season index is read only from September through
   November (or when the window holds no final) and the standings file only in
   the off-season state. Club marks come from the hub (EEPHUS_HUB.teamLogo),
   loaded only once the strip will show. */
(function () {
  "use strict";

  var BASE = "/data/scores/";
  var POLL_LIVE_MS = 60000, POLL_UPCOMING_MS = 300000;
  var MAX_FINAL_AGE_DAYS = 7, DAY_MS = 86400000;
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isNum(x) { return typeof x === "number" && isFinite(x); }
  function validDate(s) { return /^\d{4}-\d{2}-\d{2}$/.test(s || ""); }
  function noon(ds) { return Date.parse(ds + "T12:00:00Z"); }
  // The reader's own calendar date for an instant, as YYYY-MM-DD.
  function localDate(t) {
    var d = new Date(t), m = d.getMonth() + 1, dd = d.getDate();
    return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (dd < 10 ? "0" : "") + dd;
  }
  function daysBetween(a, b) { return Math.round((noon(b) - noon(a)) / DAY_MS); }
  function valid(L) {
    return !!(L && typeof L === "object" && L.schema === 1 && validDate(L.today) &&
      L.window && typeof L.window === "object");
  }

  // ---- card states (the same split /scores/ draws)
  function isLive(c) {
    return !!c && (c.state === "live" || (c.state === "delayed" && !!(c.sit && c.sit.inning)));
  }
  function isUpcoming(c) {
    return !!c && (c.state === "scheduled" || c.state === "pregame" ||
      (c.state === "delayed" && !(c.sit && c.sit.inning)));
  }
  function startMs(c) { var t = Date.parse((c && c.start) || ""); return isNaN(t) ? null : t; }
  function byStart(a, b) {
    var ta = a.tbd ? null : startMs(a), tb = b.tbd ? null : startMs(b);
    if (ta == null && tb == null) return (a.pk || 0) - (b.pk || 0);
    if (ta == null) return 1;
    if (tb == null) return -1;
    return ta - tb || (a.pk || 0) - (b.pk || 0);
  }

  // The latest date in the job's window, on or before its today, that holds a final.
  function windowFinalDate(L) {
    var best = null;
    Object.keys(L.window || {}).forEach(function (d) {
      var w = L.window[d];
      if (validDate(d) && d <= L.today && w && w.final > 0 && (!best || d > best)) best = d;
    });
    return best;
  }
  // The latest date before `before` that the season index lists with games.
  function indexDateBefore(seasonDoc, before) {
    var best = null;
    ((seasonDoc && seasonDoc.dates) || []).forEach(function (r) {
      if (r && validDate(r.d) && r.d < before && r.n > 0 && (!best || r.d > best.d)) best = r;
    });
    return best;
  }
  // The dates the strip reads, each with the rev that names its file.
  function datesToRead(L) {
    var out = {}, w = L.window || {};
    function add(d) { if (validDate(d) && w[d] && w[d].rev && w[d].n > 0) out[d] = w[d].rev; }
    add(L.today);
    (L.live || []).forEach(function (x) { if (x) add(x.date); });
    var fd = windowFinalDate(L);
    if (fd) add(fd);
    return out;
  }

  // plan(latest, docs, nowMs): what the strip shows. docs maps a date to its
  // date file. finalsDate names the day of the finals group; show is false
  // when there is nothing to draw, and the strip then stays hidden.
  function plan(L, docs, nowMs) {
    var out = { show: false, live: [], upcoming: [], finals: [], finalsDate: null, stale: false, asOf: null };
    if (!valid(L)) return out;
    docs = docs || {};
    var gen = Date.parse(L.generated_at || "");
    var downMs = (L.job && isNum(L.job.down_after_s) ? L.job.down_after_s : 1800) * 1000;
    out.asOf = isNaN(gen) ? null : gen;
    out.stale = isNaN(gen) || nowMs - gen > downMs;
    // A slate whose day is more than a day behind the reader's is a past day:
    // its live and upcoming rows are not shown.
    var current = daysBetween(L.today, localDate(nowMs)) <= 1;
    var seen = {};
    function cards(d) { var doc = docs[d]; return (doc && doc.games) || []; }
    if (current) {
      var liveDates = [L.today];
      (L.live || []).forEach(function (x) { if (x && validDate(x.date) && liveDates.indexOf(x.date) < 0) liveDates.push(x.date); });
      liveDates.forEach(function (d) {
        cards(d).forEach(function (c) { if (isLive(c) && !seen[c.pk]) { seen[c.pk] = 1; out.live.push(c); } });
      });
      cards(L.today).forEach(function (c) { if (isUpcoming(c) && !seen[c.pk]) { seen[c.pk] = 1; out.upcoming.push(c); } });
    }
    // The latest finals: the most recent date read that holds a final.
    var fds = Object.keys(docs).filter(function (d) {
      return validDate(d) && d <= L.today && cards(d).some(function (c) { return c && c.state === "final"; });
    }).sort();
    var fd = fds.length ? fds[fds.length - 1] : null;
    if (fd && daysBetween(fd, localDate(nowMs)) <= MAX_FINAL_AGE_DAYS) {
      out.finalsDate = fd;
      cards(fd).forEach(function (c) { if (c && c.state === "final" && !seen[c.pk]) { seen[c.pk] = 1; out.finals.push(c); } });
    }
    out.live.sort(byStart); out.upcoming.sort(byStart); out.finals.sort(byStart);
    out.show = out.live.length + out.upcoming.length + out.finals.length > 0;
    return out;
  }
  function pollMs(p) {
    if (!p || !p.show) return 0;
    if (p.live.length) return POLL_LIVE_MS;
    if (p.upcoming.length) return POLL_UPCOMING_MS;
    return 0;
  }

  // ---- the slot's state (games, postseason, off season, unmeasured)
  var DIV_NAME = { ALE: "AL East", ALC: "AL Central", ALW: "AL West", NLE: "NL East", NLC: "NL Central", NLW: "NL West" };
  var DIV_ORDER = ["ALE", "ALC", "ALW", "NLE", "NLC", "NLW"];

  function fresh(L, nowMs) {
    var g = Date.parse(L.generated_at || "");
    return !isNaN(g) && nowMs - g <= MAX_FINAL_AGE_DAYS * DAY_MS;
  }
  function dataDate(L) {
    var g = Date.parse(L.generated_at || "");
    return isNaN(g) ? L.today : localDate(g);
  }
  // The round the series row shows: the first with an undecided series, else the last.
  function currentRound(bracket) {
    var rounds = (bracket && bracket.rounds) || [];
    for (var i = 0; i < rounds.length; i++) {
      if ((rounds[i].series || []).some(function (s) { return s && !s.over; })) return rounds[i];
    }
    return rounds.length ? rounds[rounds.length - 1] : null;
  }
  function bracketLive(bracket, nowMs) {
    if (!currentRound(bracket)) return false;
    if (validDate(bracket.last) && daysBetween(bracket.last, localDate(nowMs)) > MAX_FINAL_AGE_DAYS) return false;
    return true;
  }
  // Does the reader's date call for the season index (bracket) read?
  function wantsIndex(L, nowMs) {
    var m = localDate(nowMs).slice(5, 7);
    return m === "09" || m === "10" || m === "11" || !windowFinalDate(L);
  }
  // The six division leaders, in league then division order, from the standings file.
  function leaders(st) {
    var by = {};
    ((st && st.rows) || []).forEach(function (r) {
      if (r && r.ranks && r.ranks.div === 1 && DIV_NAME[r.div] && !by[r.div]) by[r.div] = r;
    });
    return DIV_ORDER.filter(function (d) { return by[d]; }).map(function (d) { return by[d]; });
  }
  // ctx: { docs, index, standings }. kind is one of games, postseason, offseason, unmeasured.
  function slotState(L, ctx, nowMs) {
    ctx = ctx || {};
    if (!valid(L)) return { kind: "unmeasured", date: null, plan: null };
    if (!fresh(L, nowMs)) return { kind: "unmeasured", date: dataDate(L), plan: null };
    var p = plan(L, ctx.docs, nowMs);
    var br = ctx.index && ctx.index.bracket;
    if (bracketLive(br, nowMs)) {
      return { kind: "postseason", plan: p, round: currentRound(br), season: (ctx.index && ctx.index.season) || L.today.slice(0, 4) };
    }
    if (p.show) return { kind: "games", plan: p };
    var lead = leaders(ctx.standings);
    if (lead.length) return { kind: "offseason", plan: p, leaders: lead, asOf: ctx.standings.as_of, final: !!ctx.standings.final };
    return { kind: "unmeasured", date: dataDate(L), plan: null };
  }
  // Is the standings file needed to settle the state?
  function needsStandings(L, ctx, nowMs) {
    if (!valid(L) || !fresh(L, nowMs)) return false;
    ctx = ctx || {};
    if (bracketLive(ctx.index && ctx.index.bracket, nowMs)) return false;
    return !plan(L, ctx.docs, nowMs).show;
  }
  // The text after the clubs in the MLB band's count line.
  function countSuffix(S, L, nowMs) {
    if (!S) return "";
    if (S.kind === "postseason") return S.round ? String(S.round.name || "") : "";
    if (S.kind === "offseason") return S.final ? "final standings" : "standings";
    if (S.kind === "games" && valid(L) && daysBetween(L.today, localDate(nowMs)) <= 1) {
      var w = L.window && L.window[L.today], n = w && isNum(w.n) ? w.n : 0;
      return n > 0 ? n + (n === 1 ? " game today" : " games today") : "";
    }
    return "";
  }

  // ---- text
  function clock(t) {
    var d = new Date(t), h = d.getHours(), m = d.getMinutes();
    return ((h % 12) || 12) + ":" + (m < 10 ? "0" : "") + m + (h < 12 ? " AM" : " PM");
  }
  function firstPitch(c) {
    if (c.tbd || !c.start) return "Time TBA";
    var t = startMs(c);
    if (t == null) return "";
    // An engine without the en-US time format falls back to the plain clock.
    try {
      var s = new Date(t).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
      return /[AP]M/.test(s) ? s : clock(t);
    } catch (e) { return clock(t); }
  }
  function basesShort(b) {
    var names = ["1st", "2nd", "3rd"], on = [];
    for (var i = 0; i < 3; i++) if (b && b[i]) on.push(names[i]);
    if (!on.length) return "";
    return on.length === 3 ? "loaded" : on.join(" ");
  }
  function kicker(c, p) {
    if (isLive(c)) {
      var s = c.sit || {};
      var inn = s.inning ? (s.half === "bottom" ? "Bot " : "Top ") + s.inning : "Live";
      if (c.state === "delayed") return "Delayed, " + inn;
      return inn + (p && p.stale && p.asOf != null ? ", as of " + clock(p.asOf) : "");
    }
    if (c.state === "delayed") return "Delayed start";
    if (isUpcoming(c)) return firstPitch(c);
    if (c.state === "final") {
      var n = (c.line || []).length;
      return (c.flags && (c.flags.extra_innings || c.flags.shortened) && n) ? "Final/" + n : "Final";
    }
    return "";
  }
  function situation(c) {
    if (!isLive(c) || !c.sit || c.state === "delayed") return "";
    var o = isNum(c.sit.outs) ? c.sit.outs + " out" : "";
    var b = basesShort(c.sit.bases);
    return o + (o && b ? ", " : "") + b;
  }
  function dayLabel(ds) {
    var d = new Date(noon(ds));
    return [DAYS[d.getUTCDay()], MONTHS[d.getUTCMonth()] + " " + d.getUTCDate()];
  }

  // ---- markup
  function mark(side, hub) {
    var c = hub && hub.club ? hub.club(side.team_id) || hub.club(side.code) : null;
    // inside the game's own link (owner answer Q-L1): the chip stays unlinked and says why
    return c && hub.teamLogo ? hub.teamLogo(c.code, "sp-logo", { size: 40, decorative: true })
      .replace("<img ", '<img data-club-nolink="row-anchor" ') : "";
  }
  function teamCells(c, side, hub, scored) {
    var t = c[side] || {}, o = c[side === "away" ? "home" : "away"] || {};
    var won = c.state === "final" && isNum(t.r) && isNum(o.r) && t.r > o.r;
    var lost = c.state === "final" && isNum(t.r) && isNum(o.r) && t.r < o.r;
    var right = scored ? (isNum(t.r) ? String(t.r) : "")
      : (t.wl && isNum(t.wl.w) && isNum(t.wl.l) ? t.wl.w + "-" + t.wl.l : "");
    var cls = won ? " is-w" : lost ? " is-l" : "";
    return '<span class="sp-strip-tm' + cls + '">' + mark(t, hub) + esc(t.code || t.short || "") + "</span>" +
      '<span class="sp-strip-r' + cls + (scored ? "" : " is-rec") + '">' + esc(right) + "</span>";
  }
  function gameHTML(c, p, hub) {
    var live = isLive(c), scored = live || c.state === "final";
    var sit = situation(c);
    return '<li class="sp-strip-g' + (live ? " is-live" : c.state === "final" ? " is-final" : " is-pre") + '">' +
      '<a href="/scores/#game=' + encodeURIComponent(String(c.pk)) + '">' +
      '<span class="sp-kicker sp-strip-k' + (live ? " is-live" : "") + '">' + esc(kicker(c, p)) + "</span>" +
      '<span class="sp-strip-sit">' + esc(sit) + "</span>" +
      teamCells(c, "away", hub, scored) + teamCells(c, "home", hub, scored) + "</a></li>";
  }
  function trackHTML(p, hub) {
    var h = "";
    p.live.forEach(function (c) { h += gameHTML(c, p, hub); });
    p.upcoming.forEach(function (c) { h += gameHTML(c, p, hub); });
    if (p.finals.length) {
      var lab = dayLabel(p.finalsDate);
      h += '<li class="sp-strip-day"><span>' + esc(lab[0]) + "</span><span>" + esc(lab[1]) + "</span></li>";
      p.finals.forEach(function (c) { h += gameHTML(c, p, hub); });
    }
    return h;
  }

  function shortRound(r, ser) {
    var n = String((r && r.name) || "");
    if (!/^World/.test(n)) n = n.replace(/ Series$/, "");
    return (ser.lg ? ser.lg + " " : "") + n;
  }
  function seriesRow(ser, c, hub) {
    var won = ser.over && ser.winner_id != null && c.team_id === ser.winner_id;
    var lost = ser.over && ser.winner_id != null && c.team_id !== ser.winner_id;
    var cls = won ? " is-w" : lost ? " is-l" : "";
    var name = c.code ? mark(c, hub) + esc(c.code) : "TBD";
    return '<span class="sp-strip-tm' + cls + '">' + name + "</span>" +
      '<span class="sp-strip-r' + cls + '">' + (c.code && isNum(c.wins) ? c.wins : "") + "</span>";
  }
  function seriesHTML(r, ser, season, hub) {
    var cl = ser.clubs || [], a = cl[0] || {}, b = cl[1] || {};
    return '<li class="sp-strip-g is-series ' + (ser.over ? "is-final" : "is-pre") + '">' +
      '<a href="/scores/#bracket=' + encodeURIComponent(String(season)) + '"' + (ser.text ? ' title="' + esc(ser.text) + '"' : "") + ">" +
      '<span class="sp-kicker sp-strip-k">' + esc(shortRound(r, ser)) + "</span>" +
      '<span class="sp-strip-sit">' + (ser.over ? "Final" : (isNum(ser.best_of) ? "Best of " + ser.best_of : "")) + "</span>" +
      seriesRow(ser, a, hub) + seriesRow(ser, b, hub) + "</a></li>";
  }
  function monthDay(ds) {
    var d = new Date(noon(ds));
    return MONTHS[d.getUTCMonth()] + " " + d.getUTCDate();
  }
  function leaderHTML(r, final, hub) {
    return '<li class="sp-strip-g is-final is-lead"><a href="/standings/">' +
      '<span class="sp-kicker sp-strip-k">' + esc(DIV_NAME[r.div]) + "</span>" +
      '<span class="sp-strip-sit">' + (r.qualified === "division" || final ? "Winner" : "Leads") + "</span>" +
      '<span class="sp-strip-tm">' + mark(r, hub) + esc(r.code) + "</span>" +
      '<span class="sp-strip-r">' + esc(r.w + "-" + r.l) + "</span></a></li>";
  }
  // The list the strip draws for a state (unmeasured draws no list).
  function stateTrackHTML(S, hub) {
    var h = "";
    if (S.kind === "games") return trackHTML(S.plan, hub);
    if (S.kind === "postseason") {
      (S.round.series || []).forEach(function (ser) { h += seriesHTML(S.round, ser, S.season, hub); });
      // a game still to start is already in its series card: only live games add a card
      var open = S.plan ? S.plan.live : [];
      open.forEach(function (c) { h += gameHTML(c, S.plan, hub); });
      return h;
    }
    if (S.kind === "offseason") {
      h += '<li class="sp-strip-day"><span>' + (S.final ? "Final" : "As of") + "</span><span>" +
        esc(validDate(S.asOf) ? monthDay(S.asOf) : "") + "</span></li>";
      S.leaders.forEach(function (r) { h += leaderHTML(r, S.final, hub); });
    }
    return h;
  }
  // The pixel unmeasured box: the module's name from the page, the date of the last update.
  function unmeasuredHTML(S, name) {
    var nm = esc(name || "Scores");
    var msg = nm + " has no current data" + (S && validDate(S.date) ? " (last updated " + esc(monthDay(S.date)) + ")" : "") +
      '. <a href="/scores/">Open ' + nm + "</a>";
    var ST = window.EephusState;
    if (ST && ST.html) return ST.html("unmeasured", msg, "home-scores-unmeasured");
    return '<div class="px-state is-unmeasured home-scores-unmeasured"><div class="px-state-msg">' + msg + "</div></div>";
  }

  // ---- loading
  function loadHub(src) {
    if (window.EEPHUS_HUB) return Promise.resolve(window.EEPHUS_HUB);
    if (!src || !document.createElement) return Promise.resolve(null);
    return new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = src; s.async = true;
      s.onload = function () { resolve(window.EEPHUS_HUB || null); };
      s.onerror = function () { resolve(null); };
      document.head.appendChild(s);
    });
  }
  function getJSON(path) {
    return fetch(BASE + path, { cache: "no-cache" }).then(function (r) {
      if (!r || !r.ok) throw new Error("HTTP " + (r ? r.status : 0));
      return r.json();
    });
  }

  function mount(root) {
    var track = root.querySelector(".sp-strip-track");
    if (!track) return;
    var stateEl = document.getElementById("home-scores-state");
    var countEl = document.getElementById("home-mlb-count");
    var name = root.getAttribute("data-name") || "";
    var docs = {}, hubP = null, timer = null, dueAt = 0, busy = false, drawn = false;
    var idx = { rev: null, p: null }, stn = { rev: null, p: null };

    function memo(slot, rev, path) {
      if (slot.p && slot.rev === rev) return slot.p;
      slot.rev = rev;
      slot.p = getJSON(path + (rev ? "?v=" + encodeURIComponent(rev) : "")).catch(function () { slot.p = null; return null; });
      return slot.p;
    }
    function readDates(L) {
      var want = datesToRead(L), jobs = [];
      Object.keys(want).forEach(function (d) {
        if (docs[d] && docs[d].rev === want[d]) return;
        jobs.push(getJSON(d + ".json?v=" + encodeURIComponent(want[d])).then(function (doc) {
          docs[d] = { rev: want[d], doc: doc };
        }, function () { /* a missing date file leaves the date out */ }));
      });
      // No final in the job's window (a break in the schedule): the season
      // index names the latest earlier date with games.
      if (!windowFinalDate(L)) {
        var first = Object.keys(L.window).sort()[0] || L.today;
        jobs.push(memo(idx, L.index_rev, "index-" + L.today.slice(0, 4) + ".json").then(function (sd) {
          var r = indexDateBefore(sd, first);
          if (!r || !r.rev || daysBetween(r.d, localDate(Date.now())) > MAX_FINAL_AGE_DAYS) return null;
          if (docs[r.d] && docs[r.d].rev === r.rev) return null;
          return getJSON(r.d + ".json?v=" + encodeURIComponent(r.rev)).then(function (doc) {
            docs[r.d] = { rev: r.rev, doc: doc };
          });
        }).catch(function () { return null; }));
      }
      return Promise.all(jobs).then(function () {
        var keep = {};
        Object.keys(docs).forEach(function (d) { keep[d] = docs[d].doc; });
        return keep;
      });
    }
    // Everything the state needs, read once per tick: the date files, the
    // season index in the bracket months, the standings file off season.
    function resolve(L) {
      var now = Date.now();
      return readDates(L).then(function (docsNow) {
        var ctx = { docs: docsNow, index: null, standings: null };
        var idxP = wantsIndex(L, now) ? memo(idx, L.index_rev, "index-" + L.today.slice(0, 4) + ".json") : Promise.resolve(null);
        return idxP.then(function (ix) {
          ctx.index = ix;
          if (!needsStandings(L, ctx, now) || !L.standings || !L.standings.season) return ctx;
          return memo(stn, L.standings.rev, "standings/" + encodeURIComponent(L.standings.season) + ".json").then(function (st) {
            ctx.standings = st;
            return ctx;
          });
        });
      }).then(function (ctx) { return { L: L, S: slotState(L, ctx, now) }; });
    }
    function setCount(S, L) {
      if (!countEl) return;
      var base = countEl.getAttribute("data-base");
      if (base == null) { base = countEl.textContent; countEl.setAttribute("data-base", base); }
      var suf = countSuffix(S, L, Date.now());
      countEl.textContent = base + (suf ? " \u00b7 " + suf : "");
    }
    function draw(r, hub) {
      var S = r.S;
      setCount(S, r.L);
      if (S.kind === "unmeasured") {
        root.hidden = true;
        if (stateEl) { stateEl.innerHTML = unmeasuredHTML(S, name); stateEl.hidden = false; }
        return;
      }
      if (stateEl) { stateEl.hidden = true; stateEl.innerHTML = ""; }
      var act = document.activeElement, href = act && root.contains(act) ? act.getAttribute("href") : null;
      var x = track.scrollLeft;
      track.innerHTML = stateTrackHTML(S, hub);
      root.hidden = false;
      track.scrollLeft = x;
      drawn = true;
      if (href) {
        var again = track.querySelector('a[href="' + href + '"]');
        if (again) again.focus({ preventScroll: true });
      }
    }
    function schedule(ms) {
      clearTimeout(timer); timer = null;
      dueAt = ms ? Date.now() + ms : 0;
      if (ms && !document.hidden) timer = setTimeout(tick, ms);
    }
    function tick() {
      if (busy) return;
      busy = true;
      getJSON("latest.json").then(function (L) {
        if (!valid(L)) throw new Error("schema");
        // The hub loads beside the date files when the window names a date to
        // read, else only once the state says the strip will show.
        var hubSrc = root.getAttribute("data-hub");
        if (!hubP && Object.keys(datesToRead(L)).length) hubP = loadHub(hubSrc);
        return resolve(L).then(function (r) {
          if (r.S.kind === "unmeasured") { draw(r, null); return r.S; }
          if (!hubP) hubP = loadHub(hubSrc);
          return hubP.then(function (hub) { draw(r, hub); return r.S; });
        }).then(function (S) { schedule(pollMs(S.plan)); });
      }).catch(function () {
        // Missing files or a fetch error: a strip already drawn keeps its last
        // rows and tries again on its own cadence; none yet draws the
        // unmeasured box without a date.
        if (!drawn) draw({ L: null, S: { kind: "unmeasured", date: null, plan: null } }, null);
        schedule(drawn ? (dueAt ? POLL_LIVE_MS : 0) : 0);
      }).then(function () { busy = false; });
    }
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { clearTimeout(timer); timer = null; return; }
      if (dueAt && !timer) timer = setTimeout(tick, Math.max(0, dueAt - Date.now()));
    });
    tick();
  }

  window.EephusHomeScores = { plan: plan, pollMs: pollMs, datesToRead: datesToRead, kicker: kicker,
    situation: situation, trackHTML: trackHTML, indexDateBefore: indexDateBefore, windowFinalDate: windowFinalDate,
    slotState: slotState, needsStandings: needsStandings, wantsIndex: wantsIndex, countSuffix: countSuffix,
    stateTrackHTML: stateTrackHTML, unmeasuredHTML: unmeasuredHTML, leaders: leaders, currentRound: currentRound };

  function init() {
    var root = document.getElementById("home-scoreboard");
    if (root && window.fetch) mount(root);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
