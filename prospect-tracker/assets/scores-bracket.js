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
   ("TBR leads 2-0") and every count come from the block.

   THE ART (SCORES_7b, owner SC7-2). Above the full view's rounds, a pixel
   bracket: each series a box of two clubs with logo chips and series-win pips
   (wins needed to take the series, the won ones lit), stepped connector lines
   from the series that fed it, and a pixel trophy over the World Series. A
   series finds its feeder by the club that won it, by MLB's placeholder
   ("Winner of CLE and CWS"), then by order inside its league; when any series
   finds no place the art is left out and the rounds below stand alone. The
   art is aria-hidden: the rounds below say the same in words. */
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

  // ---- the art
  var TROPHY = ["#############", "#.#########.#", "#.#########.#", ".#.#######.#.", "..##.###.##..", "....#####....",
    ".....###.....", "......#......", "......#......", "....#####....", "...#######..."];
  function runs(rows, x, y) {
    var d = "";
    rows.forEach(function (row, r) {
      row.replace(/#+/g, function (m, c) { d += "M" + (x + c) + " " + (y + r) + "h" + m.length + "v1h-" + m.length + "z"; return m; });
    });
    return d;
  }
  function codeOf(x) {
    var H = window.EEPHUS_HUB, c = H && H.club ? H.club(x) : null;
    return c ? c.code : String(x || "").toUpperCase();
  }
  function fed(S, T) {
    var ids = S.clubs.map(function (c) { return c.team_id; });
    if (T.over && T.winner_id != null && ids.indexOf(T.winner_id) >= 0) return true;
    var tc = T.clubs.map(function (c) { return codeOf(c.code); }).sort().join();
    return S.clubs.some(function (c) {
      var m = !c.code && /Winner of (\w+) and (\w+)/.exec(c.name || "");
      return m && [codeOf(m[1]), codeOf(m[2])].sort().join() === tc;
    });
  }
  // kids[k][i]: the series of round k-1 that fed series i of round k; null when the rounds do not make a tree
  function tree(R) {
    var kids = R.map(function (ss) { return ss.map(function () { return []; }); });
    for (var k = R.length - 1; k > 0; k--) {
      var prev = R[k - 1], used = prev.map(function () { return false; }), groups = {};
      R[k].forEach(function (S, i) { (groups[S.lg || "*"] = groups[S.lg || "*"] || []).push(i); });
      for (var key in groups) {
        var cand = [];
        prev.forEach(function (T, j) { if (key === "*" || T.lg === key) cand.push(j); });
        var per = cand.length / groups[key].length;
        if (per < 1 || per !== Math.floor(per)) return null;
        for (var pass = 0; pass < 2; pass++) {
          groups[key].forEach(function (i) {
            cand.forEach(function (j) {
              if (!used[j] && kids[k][i].length < per && (pass || fed(R[k][i], prev[j]))) { used[j] = true; kids[k][i].push(j); }
            });
          });
        }
      }
      if (used.indexOf(false) >= 0) return null;
    }
    return kids;
  }
  function pips(s, c) {
    var need = Math.ceil((s.best_of || 1) / 2), w = isNum(c.wins) ? c.wins : 0, o = "";
    for (var i = 0; i < need; i++) o += '<i class="scba-pip' + (i < w ? " is-on" : "") + '"></i>';
    return o;
  }
  function boxHTML(s, k, y) {
    var rows = s.clubs.map(function (c) {
      var won = s.over && s.winner_id != null && c.team_id === s.winner_id;
      return '<span class="scba-c' + (won ? " is-won" : s.over ? " is-out" : "") + '">' + chip(c) +
        '<b class="scba-code">' + esc(c.code || "TBD") + "</b>" + pips(s, c) + "</span>";
    }).join("");
    return '<div class="scba-box" style="--k:' + k + ";--y:" + y + 'px">' + rows + "</div>";
  }
  function line(cls, k, y, h) {
    return '<i class="' + cls + '" style="--k:' + k + ";--y:" + y + "px" + (h != null ? ";--h:" + h + "px" : "") + '"></i>';
  }
  function art(rounds) {
    var R = rounds.map(function (r) { return r.series || []; }), K = R.length;
    if (K < 2 || !R[K - 1].length) return "";
    var kids = tree(R);
    if (!kids) return "";
    var SLOT = 56, BOX = 48, slot = 0, pos = R.map(function (ss) { return ss.map(function () { return null; }); });
    function place(k, i) {
      var ch = kids[k][i], sum = 0;
      if (!ch.length) return (pos[k][i] = slot++ * SLOT);
      ch.forEach(function (j) { sum += place(k - 1, j); });
      return (pos[k][i] = Math.round(sum / ch.length));
    }
    R[K - 1].forEach(function (s, i) { place(K - 1, i); });
    var cup = rounds[K - 1].type === "W" && R[K - 1].length === 1;
    var off = cup ? Math.max(0, 30 - pos[K - 1][0]) : 0, o = "";
    for (var k = 0; k < K; k++) {
      for (var i = 0; i < R[k].length; i++) {
        var y = pos[k][i] + off, mid = y + BOX / 2;
        o += boxHTML(R[k][i], k, y);
        if (kids[k][i].length) {
          var ys = kids[k][i].map(function (j) { return pos[k - 1][j] + off + BOX / 2; }).concat([mid]);
          var lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
          kids[k][i].forEach(function (j) { o += line("scba-h1", k, pos[k - 1][j] + off + BOX / 2); });
          if (hi > lo) o += line("scba-v", k, lo - 1, hi - lo + 2);
          o += line("scba-h2", k, mid);
        }
      }
    }
    if (cup) {
      o += '<svg class="scba-cup" style="--k:' + (K - 1) + ";--y:" + (pos[K - 1][0] + off - 26) + 'px" viewBox="0 0 13 11" width="26" height="22" shape-rendering="crispEdges">' +
        '<path class="scba-gold" d="' + runs(TROPHY, 0, 0) + '"/><path class="scba-shine" d="' + runs(["#", "#"], 3, 1) + '"/></svg>';
    }
    var heads = rounds.map(function (r) { return "<span>" + esc(r.name) + "</span>"; }).join("");
    return '<div class="scb-art" aria-hidden="true" style="--n:' + K + '"><div class="scba-heads">' + heads + "</div>" +
      '<div class="scba-tree" style="height:' + (slot * SLOT - SLOT + BOX + off) + 'px">' + o + "</div></div>";
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
    el.innerHTML = '<div class="scb' + (o.compact ? " scb-compact" : "") + '">' + (o.compact ? "" : art(rounds)) + '<div class="scb-rounds">' + html + "</div>" +
      (o.compact ? "" : '<p class="scb-src">Series and results as MLB lists them.</p>') + "</div>";
    return true;
  }

  window.EephusScoresBracket = { mount: mount };
})();
