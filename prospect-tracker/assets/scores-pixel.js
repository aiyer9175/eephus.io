/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* The scores page's pixel art (SCORES_7b, owner SC7-2), eager beside
   assets/scores.js. Every sprite is an SVG drawn on a whole-number grid with
   shape-rendering: crispEdges and scaled by a whole number (k CSS px per
   cell), so it stays sharp at 1x and 2x; every colour is a site token set in
   assets/scores-pixel.css. It reads only what the job's files carry and
   computes no number of its own.

   EXPORTS (window.EephusScoresPixel):
   diamond(s, mode, k)  the base/outs diamond. mode "live" reads a card's sit
                        (bases, outs, balls, strikes: B S O lamps); "end" reads
                        a final card's end (bases and outs the last play left),
                        compact. k is the CSS px per cell (default 2).
                        role="img" with the state in words.
   chart(g, W, live, pts, h)  the Win Prob chart as a stepped pixel line, the
                        numbered marks of the biggest plays, and a marker and
                        label on the biggest swing. Returns {svg, pts, x, y, W, H}.
   key(g, h)            the chart's legend, one sprite per mark. */
(function () {
  "use strict";

  // 5 x 5 bases, 3 x 5 letters; "#" is a lit cell.
  var BASE_ON = ["..#..", ".###.", "#####", ".###.", "..#.."];
  var BASE_OFF = ["..#..", ".#.#.", "#...#", ".#.#.", "..#.."];
  var GLYPH = {
    B: ["##.", "#.#", "##.", "#.#", "##."],
    S: [".##", "#..", ".#.", "..#", "##."],
    O: [".#.", "#.#", "#.#", "#.#", ".#."]
  };
  var PIP_ON = ["###", "###", "###"], PIP_OFF = ["###", "#.#", "###"];
  var BASE_NAMES = ["first", "second", "third"];

  function isNum(x) { return typeof x === "number" && isFinite(x); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  // A bitmap at (x, y) as path runs, one "M x y h w v 1 h -w z" per lit run.
  function runs(rows, x, y) {
    var d = "";
    for (var r = 0; r < rows.length; r++) {
      var row = rows[r], c = 0;
      while (c < row.length) {
        if (row.charAt(c) !== "#") { c++; continue; }
        var s = c;
        while (c < row.length && row.charAt(c) === "#") c++;
        d += "M" + (x + s) + " " + (y + r) + "h" + (c - s) + "v1h-" + (c - s) + "z";
      }
    }
    return d;
  }
  function path(cls, d) { return d ? '<path class="' + cls + '" d="' + d + '"/>' : ""; }
  function ordinal(n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }
  function basesWords(b) {
    var on = [];
    for (var i = 0; i < 3; i++) if (b && b[i]) on.push(BASE_NAMES[i]);
    if (!on.length) return "bases empty";
    if (on.length === 3) return "bases loaded";
    return (on.length === 1 ? "runner on " : "runners on ") + on.join(" and ");
  }
  function outsWords(n) { return n + (n === 1 ? " out" : " outs"); }
  function clamp(n, hi) { n = isNum(n) ? Math.floor(n) : 0; return n < 0 ? 0 : n > hi ? hi : n; }

  // ---- the diamond: second base on top, third left, first right; lamps to the right.
  // Live: home plate and base paths too, and B S O lamps (34 px tall at k 2). End: a compact
  // diamond and the O lamps only (18 px tall at k 2), small enough for a card's head row.
  function diamond(s, mode, k) {
    s = s || {};
    k = k || 2;
    var b = s.bases || [], live = mode !== "end";
    var on = "", off = "", dim = "", ink = "";
    // live centres (8,3) second, (2,9) third, (14,9) first; end centres (6,2), (2,6), (10,6)
    var at = live ? [[12, 7], [6, 1], [0, 7]] : [[8, 4], [4, 0], [0, 4]];
    for (var i = 0; i < 3; i++) {
      if (b[i]) on += runs(BASE_ON, at[i][0], at[i][1]);
      else off += runs(BASE_OFF, at[i][0], at[i][1]);
    }
    if (live) {
      dim += runs(["###", ".#."], 7, 14);
      // the base paths, dotted
      [[10, 5], [12, 7], [6, 5], [4, 7], [10, 13], [12, 11], [6, 13], [4, 11]].forEach(function (p) { dim += runs(["#"], p[0], p[1]); });
    }
    var rows = live ? [["B", s.balls, 3], ["S", s.strikes, 2], ["O", s.outs, 3]] : [["O", s.outs, 3]];
    var lx = live ? 20 : 16, y0 = live ? 0 : 2;
    rows.forEach(function (r, j) {
      var y = y0 + j * 6, n = clamp(r[1], r[2]);
      ink += runs(GLYPH[r[0]], lx, y);
      for (var p = 0; p < r[2]; p++) {
        if (p < n) on += runs(PIP_ON, lx + 4 + p * 4, y + 1);
        else off += runs(PIP_OFF, lx + 4 + p * 4, y + 1);
      }
    });
    var W = live ? 36 : 32, H = live ? 17 : 9;
    var label = live
      ? basesWords(b).replace(/^./, function (c) { return c.toUpperCase(); }) + ", " + outsWords(clamp(s.outs, 3)) +
        ", " + clamp(s.balls, 3) + (s.balls === 1 ? " ball, " : " balls, ") + clamp(s.strikes, 2) + (s.strikes === 1 ? " strike" : " strikes")
      : "Last play, " + (s.half === "bottom" ? "bottom" : "top") + " of the " + ordinal(s.inning || 9) + ": " +
        outsWords(clamp(s.outs, 3)) + ", " + basesWords(b);
    return '<svg class="sc-bases px-sprite" viewBox="0 0 ' + W + " " + H + '" width="' + W * k + '" height="' + H * k +
      '" role="img" aria-label="' + esc(label) + '" shape-rendering="crispEdges"><title>' + esc(label) + "</title>" +
      path("px-dim", dim) + path("px-off", off) + path("px-ink", ink) + path("px-on", on) + "</svg>";
  }

  // ---- the Win Prob chart: a stepped line on whole pixels
  function chart(g, W, live, pts, h) {
    var c = g.card, n = pts.length;
    var H = W < 600 ? 180 : 240, AX = 24, PADL = 12, PADR = live ? 58 : 12, PADT = 10;
    var iw = Math.max(40, W - PADL - PADR), ih = H - PADT;
    var x = function (i) { return Math.round(PADL + (n <= 1 ? iw / 2 : i / (n - 1) * iw)); };
    var y = function (th) { return Math.round(PADT + (1 - th / 1000) * ih); };
    var o = '<svg class="sc-wp-svg" width="' + W + '" height="' + (H + AX) + '" viewBox="0 0 ' + W + " " + (H + AX) +
      '" aria-hidden="true" focusable="false" shape-rendering="crispEdges">';
    [0, 250, 500, 750, 1000].forEach(function (v) {
      o += '<line class="sc-gl' + (v === 500 ? " is-mid" : "") + '" x1="' + PADL + '" x2="' + (PADL + iw) + '" y1="' + (y(v) + 0.5) + '" y2="' + (y(v) + 0.5) + '"/>';
    });
    o += '<text class="sc-ax" x="' + (PADL + 2) + '" y="' + (y(1000) + 12) + '">' + esc((c.home.code || c.home.short) + " 100%") + "</text>";
    o += '<text class="sc-ax" x="' + (PADL + 2) + '" y="' + (y(0) - 4) + '">' + esc((c.away.code || c.away.short) + " 100%") + "</text>";
    o += '<text class="sc-ax" x="' + (PADL + iw - 2) + '" y="' + (y(500) - 4) + '" text-anchor="end">50%</text>';
    // each plate appearance holds its value until the next one: across, then down or up
    var d = "", pen = false, lastInn = null, px = 0, py = 0;
    for (var i = 0; i < n; i++) {
      var p = pts[i];
      if (p.half === "top" && p.inning !== lastInn) {
        o += '<text class="sc-ax" x="' + x(i) + '" y="' + (H + 16) + '" text-anchor="middle">' + p.inning + "</text>";
        lastInn = p.inning;
      }
      if (!isNum(p.wp)) { pen = false; continue; }
      var X = x(i), Y = y(p.wp);
      if (!pen) d += "M" + X + " " + Y;
      else { if (X !== px) d += "H" + X; if (Y !== py) d += "V" + Y; }
      px = X; py = Y; pen = true;
    }
    o += '<path class="sc-wp-line" d="' + d + '"/>';
    var top = null;
    for (i = 0; i < n; i++) {
      if (!pts[i].rank || !isNum(pts[i].wp)) continue;
      var mx = x(i), my = y(pts[i].wp);
      if (pts[i].rank === 1) top = { X: mx, Y: my, ab: pts[i].ab };
      o += '<g class="sc-mark' + (pts[i].rank === 1 ? " is-top" : "") + '"><rect x="' + (mx - 8) + '" y="' + (my - 8) + '" width="16" height="16"/>' +
        '<text x="' + mx + '" y="' + (my + 4) + '" text-anchor="middle">' + pts[i].rank + "</text></g>";
    }
    // the biggest swing: a pixel flag on a leader and its label, above the mark where it fits, else below
    var big = (g.plays_big || [])[0];
    if (top && big && big.ab === top.ab) {
      var lab = "Biggest swing: " + (big.bat_team || "") + " " + h.signed(big.swing);
      var lw = Math.ceil(lab.length * 6.2) + 10, up = top.Y - 8 - 30 >= 0;
      var ly = up ? top.Y - 8 - 30 : top.Y + 8 + 12;
      var lx = Math.max(PADL, Math.min(top.X - 4, PADL + iw - lw));
      o += '<g class="sc-swing"><rect class="sc-lead" x="' + (top.X - 1) + '" y="' + (up ? ly + 18 : top.Y + 8) + '" width="2" height="12"/>' +
        '<rect class="sc-plate" x="' + lx + '" y="' + ly + '" width="' + lw + '" height="18"/>' +
        '<text x="' + (lx + 5) + '" y="' + (ly + 13) + '">' + esc(lab) + "</text></g>";
    }
    if (live && n && isNum(pts[n - 1].wp)) {
      var lead = h.lead(c, pts[n - 1].wp), ex = x(n - 1), ey = y(pts[n - 1].wp);
      o += '<rect class="sc-end px-blink" x="' + (ex - 3) + '" y="' + (ey - 3) + '" width="6" height="6"/>' +
        '<text class="sc-ax sc-endlbl" x="' + (ex + 8) + '" y="' + (ey + 4) + '">' + esc(lead.code + " " + lead.pct + "%") + "</text>";
    }
    o += '<line class="sc-cross" x1="0" x2="0" y1="' + PADT + '" y2="' + (PADT + ih) + '" visibility="hidden"/></svg>';
    return { svg: o, pts: pts, x: x, y: y, W: W, H: H };
  }

  // ---- the legend over the chart: the line, a numbered mark, the biggest swing's flag
  function sprite(inner, w) {
    return '<svg class="px-key" viewBox="0 0 ' + w + ' 8" width="' + w * 2 + '" height="16" aria-hidden="true" shape-rendering="crispEdges">' + inner + "</svg>";
  }
  function key(g) {
    var home = g.card.home.code || g.card.home.short;
    var line = sprite(path("px-line", runs(["....####", "....#...", "....#...", "#####..."], 0, 2)), 8);
    var mark = sprite('<rect class="px-mark" x="0" y="0" width="8" height="8"/>', 8);
    var top = sprite('<rect class="px-top" x="1" y="1" width="6" height="6"/>', 8);
    return '<p class="sc-wp-key">' + line + " " + esc(home) + " win probability after each plate appearance " +
      mark + " the biggest plays, numbered " + top + " the biggest swing</p>";
  }

  window.EephusScoresPixel = { diamond: diamond, chart: chart, key: key, runs: runs };
})();
