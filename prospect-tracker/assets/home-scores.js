/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* The homepage scoreboard strip (SCORES_7d; owner SC7-6 and SC7-7): a pure
   reader of the files /scores/ reads under /data/scores/, the job's latest
   file and the date files it names. It computes no number of its own.
   Order: live games, then today's games still to start (first pitch in the
   reader's own time), then the latest day's finals. With nothing live or to
   come it shows the latest finals; it stays hidden (no space held) when the
   files are missing or the latest final is more than MAX_FINAL_AGE_DAYS old.
   It polls every 60 s while a game is live and every 300 s while a game is
   still to start today, and never while the tab is hidden. Club marks come
   from the hub (EEPHUS_HUB.teamLogo), loaded only once the strip will show. */
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
    var docs = {}, hubP = null, timer = null, dueAt = 0, busy = false;

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
        jobs.push(getJSON("index-" + L.today.slice(0, 4) + ".json").then(function (sd) {
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
    function draw(p, hub) {
      if (!p.show) { root.hidden = true; return; }
      var act = document.activeElement, href = act && root.contains(act) ? act.getAttribute("href") : null;
      var x = track.scrollLeft;
      track.innerHTML = trackHTML(p, hub);
      root.hidden = false;
      track.scrollLeft = x;
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
        // read, else only once the plan says the strip will show.
        var hubSrc = root.getAttribute("data-hub");
        if (!hubP && Object.keys(datesToRead(L)).length) hubP = loadHub(hubSrc);
        return readDates(L).then(function (docsNow) {
          var p = plan(L, docsNow, Date.now());
          if (!p.show) return draw(p, null);
          if (!hubP) hubP = loadHub(hubSrc);
          return hubP.then(function (hub) { draw(p, hub); return p; });
        }).then(function (p) { schedule(pollMs(p)); });
      }).catch(function () {
        // Missing files or a fetch error: a strip never drawn stays hidden; a
        // drawn one keeps its last rows and tries again on its own cadence.
        schedule(root.hidden ? 0 : (dueAt ? POLL_LIVE_MS : 0));
      }).then(function () { busy = false; });
    }
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { clearTimeout(timer); timer = null; return; }
      if (dueAt && !timer) timer = setTimeout(tick, Math.max(0, dueAt - Date.now()));
    });
    tick();
  }

  window.EephusHomeScores = { plan: plan, pollMs: pollMs, datesToRead: datesToRead, kicker: kicker,
    situation: situation, trackHTML: trackHTML, indexDateBefore: indexDateBefore, windowFinalDate: windowFinalDate };

  function init() {
    var root = document.getElementById("home-scoreboard");
    if (root && window.fetch) mount(root);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
