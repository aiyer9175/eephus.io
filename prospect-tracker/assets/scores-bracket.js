/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* The October bracket (SCORES_4b, plan 1.6), a lazy chunk. The scores page
   loads it only on its bracket route, or in October for the day view's rail at
   1400 px and wider; /standings/ mounts it unchanged in its Playoffs view.

   ONE EXPORT. EephusScoresBracket.mount(el, block, opts) draws the season
   index's bracket block into el and returns true when it drew one. It makes
   no route, hash or page assumption and no fetch of its own: the host passes
   the block. opts.compact draws one line per series (the rail); opts.gameHref
   maps a game pk to its link (default /scores/#game=<pk>).

   WHAT IT PRINTS. Series state and results as the job copied them from MLB's
   postseason schedule: rounds as columns, each series with its clubs, wins and
   games. No probability of any kind, no odds and no link to the Futures tab
   (Part 8 8.D row 8). A slot MLB has not decided carries code null and prints
   MLB's placeholder ("Winner of HOU and CWS") unlinked, with
   data-club-nolink="unresolved". The chunk computes nothing: the series line
   ("TBR leads 2-0") and every count come from the block. */
(function () {
  "use strict";

  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"];
  var STATE = { postponed: "Postponed", suspended: "Suspended", cancelled: "Cancelled", live: "Live", delayed: "Delayed" };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function isNum(x) { return typeof x === "number" && isFinite(x); }
  function monthDay(ds) {
    var d = new Date(String(ds || "") + "T12:00:00Z");
    return isNaN(d.getTime()) ? "" : MONTHS[d.getUTCMonth()] + " " + d.getUTCDate();
  }

  // A club MLB has decided links to its Franchises page; a placeholder never links.
  function club(c) {
    if (!c || !c.code) {
      return '<span class="scb-club" data-club-nolink="unresolved">' + esc(c && c.name) + "</span>";
    }
    return '<a class="scb-club" href="/franchise/#team=' + encodeURIComponent(c.code) + '" title="' + esc(c.name) + '">' +
      esc(c.code) + "</a>";
  }
  // SC7-1: the pixel logo chip beside a decided club, from the page's hub when it has one (the code prints
  // beside it, so its alt is empty; it removes itself on error). Without the hub the chunk draws codes only.
  function chip(c) {
    var H = window.EEPHUS_HUB;
    return c && c.code && H && H.club && H.club(c.code) ? H.teamLogo(c.code, "sp-logo", { size: 16, decorative: true }) : "";
  }
  function short(s, id) {
    for (var i = 0; i < s.clubs.length; i++) {
      var c = s.clubs[i];
      if (c.team_id === id) return c.code || c.name;
    }
    return "";
  }

  function gameRow(s, g, href) {
    var head = "Game " + (g.n || "") + ", " + monthDay(g.date), res = "";
    if (g.state === "final" && isNum(g.away_r) && isNum(g.home_r)) {
      res = short(s, g.away_id) + " " + g.away_r + ", " + short(s, g.home_id) + " " + g.home_r;
    } else if (STATE[g.state]) {
      res = STATE[g.state];
    } else if (g.if_necessary) {
      res = "If necessary";
    }
    return '<li><a href="' + esc(href(g.pk)) + '">' + esc(head) + "</a>" + (res ? ": " + esc(res) : "") + "</li>";
  }

  function clubRow(s, c) {
    var won = s.over && s.winner_id != null && c.team_id === s.winner_id;
    var inner = chip(c) + club(c) + ' <span class="scb-w">' + (isNum(c.wins) ? c.wins : 0) + "</span>";
    return '<li class="scb-c' + (won ? " is-won" : s.over ? " is-out" : "") + '">' + (won ? "<strong>" + inner + '</strong><span class="sr-only"> winner</span>' : inner) + "</li>";
  }

  function seriesHTML(r, s, o, href) {
    var lab = (s.lg ? s.lg + " " : "") + r.name;
    if (o.compact) {
      // a placeholder already names its league ("AL Lower Seed"), so the label waits for two clubs
      var lg = s.lg && s.clubs.every(function (c) { return c.code; }) ? '<span class="scb-lab">' + esc(s.lg) + "</span> " : "";
      return '<li class="scb-s scb-line">' + lg + chip(s.clubs[0]) + club(s.clubs[0]) + " vs " +
        chip(s.clubs[1]) + club(s.clubs[1]) + (s.text ? ': <span class="scb-text">' + esc(s.text) + "</span>" : "") + "</li>";
    }
    var games = (s.games || []).map(function (g) { return gameRow(s, g, href); }).join("");
    return '<li class="scb-s' + (s.over ? " is-over" : "") + '"><p class="scb-lab">' + esc(lab) +
      (s.best_of ? ", best of " + s.best_of : "") + '</p><ul class="scb-clubs">' +
      s.clubs.map(function (c) { return clubRow(s, c); }).join("") + "</ul>" +
      (s.text ? '<p class="scb-text sp-kicker">' + esc(s.text) + "</p>" : "") +
      (games ? '<ol class="scb-games">' + games + "</ol>" : "") + "</li>";
  }

  function mount(el, block, opts) {
    var o = opts || {};
    var href = typeof o.gameHref === "function" ? o.gameHref : function (pk) { return "/scores/#game=" + pk; };
    var rounds = (block && block.rounds) || [];
    if (!el) return false;
    if (!rounds.length) {
      el.innerHTML = o.compact ? "" : '<p class="scb-none">No bracket for this season in these files.</p>';
      return false;
    }
    var html = rounds.map(function (r) {
      var list = (r.series || []).map(function (s) { return seriesHTML(r, s, o, href); }).join("");
      return '<section class="scb-round"><h3>' + esc(r.name) + '</h3><ol class="scb-series">' + list + "</ol></section>";
    }).join("");
    el.innerHTML = '<div class="scb' + (o.compact ? " scb-compact" : "") + '"><div class="scb-rounds">' + html + "</div>" +
      (o.compact ? "" : '<p class="scb-src">Series and results as MLB lists them.</p>') + "</div>";
    return true;
  }

  window.EephusScoresBracket = { mount: mount };
})();
