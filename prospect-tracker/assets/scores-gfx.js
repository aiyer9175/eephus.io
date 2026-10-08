/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* The Scores share cards (SCORES_7c, owner SC7-3), a lazy chunk: scores.js loads
   it on the first Generate GFX press, and it loads assets/eephus-gfx.js (the
   mount root's data-gfx-js) and opens that shared modal with kind "draw" and a
   Card control. Four cards, canvas-native and set like the paper's baseball
   page (the eephus.io nameplate over a double rule, a dateline, a section
   banner on the newsprint halftone, agate tables with column rules):
     final  the final score, 1200 x 675: clean logos, the printed line score,
            W, L and S, the series in October, the star line;
     box    the full box score: both clubs' batting (P/AB) and pitching (P/IP),
            fit by layoutBox (type steps down, then two columns, then a taller
            canvas; no row is ever dropped);
     stars  the Stars of the Game rule's top three, headshots and stat lines;
     slate  every final on one date as a grid of mini scores (layoutSlate).
   It prints what the job's files carry and computes no number of its own.
   Colours are the modal's palette and site tokens only. Club marks come from
   EEPHUS_HUB.teamLogoURL and draw clean (smoothed, never pixelated); headshots
   are MLB's square face crop. Every image loads crossOrigin through
   EEPHUS_GFX.loadImg, and a failed load draws the club code or the initials,
   so the canvas is never tainted and toBlob always succeeds. */
(function () {
  "use strict";

  var W = 1200, H0 = 675, PAD = 40, UW = W - 2 * PAD, FOOT = 52, GUT = 32;
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"];
  var DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  function GF() { return window.EEPHUS_GFX; }

  // ---- words, as the page prints them
  function isNum(x) { return typeof x === "number" && isFinite(x); }
  function dateLong(ds) {
    var d = new Date(String(ds) + "T12:00:00Z");
    if (isNaN(d.getTime())) return "";
    return DAYS[d.getUTCDay()] + ", " + MONTHS[d.getUTCMonth()] + " " + d.getUTCDate() + ", " + d.getUTCFullYear();
  }
  function code(s) { return (s && (s.code || s.short)) || ""; }
  function lastName(full) {
    var p = String(full || "").split(" ");
    return p.length > 1 ? p.slice(1).join(" ") : String(full || "");
  }
  function n0(x) { return isNum(x) ? String(x) : "-"; }
  function f1(x) { return isNum(x) ? x.toFixed(1) : "-"; }
  function ipOf(outs) { return isNum(outs) ? Math.floor(outs / 3) + "." + (outs % 3) : "-"; }
  function signed3(th) { return isNum(th) ? (th > 0 ? "+" : th < 0 ? "-" : "") + (Math.abs(th) / 1000).toFixed(3) : ""; }
  function ordinal(n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }
  function finalWord(c) {
    var n = (c.line || []).length, f = c.flags || {};
    return f.extra_innings || f.shortened ? "Final, " + n + " innings" : "Final";
  }
  function scoreLine(c) { return code(c.away) + " " + n0(c.away.r) + ", " + code(c.home) + " " + n0(c.home.r); }
  function winner(c, side) {
    var o = c[side === "away" ? "home" : "away"];
    return isNum(c[side].r) && isNum(o.r) && c[side].r > o.r;
  }
  function decisions(c, full) {
    var r = c.of_record || {}, out = [];
    [["w", "W"], ["l", "L"], ["sv", "S"]].forEach(function (k) {
      if (r[k[0]]) out.push(k[1] + " " + (full ? r[k[0]].name : lastName(r[k[0]].name)));
    });
    return out;
  }
  // The series line prints in October and on every postseason card.
  function seriesText(c, ds) {
    return c.series && c.series.text && (c.type !== "R" || String(ds).slice(5, 7) === "10") ? c.series.text : "";
  }

  // Word wrap at a character count: the agate face is monospaced, so a count is
  // a width. layoutBox and the painter share it, so a planned line is a drawn line.
  function wrapChars(t, n) {
    var out = [], cur = "";
    String(t || "").split(/\s+/).forEach(function (w) {
      if (!w) return;
      while (w.length > n) { if (cur) { out.push(cur); cur = ""; } out.push(w.slice(0, n)); w = w.slice(n); }
      if (!cur) cur = w;
      else if ((cur + " " + w).length <= n) cur += " " + w;
      else { out.push(cur); cur = w; }
    });
    if (cur) out.push(cur);
    return out;
  }
  function charsFor(width, font) { return Math.max(8, Math.floor(width / (font * 0.62))); }

  // ---- the fit ladders (pure; test_scores_gfx.py drives them)
  // The box score: one column at three type sizes, then two columns (away
  // left, home right) stepping down to the 19 px agate floor; when even that
  // floor cannot hold both clubs inside 675 px the canvas grows in 120 px
  // steps. A side's height in rows: its head (1.6), the batting head and rows,
  // a 0.6 gap, the pitching head and rows, then its wrapped note lines.
  var BOX_LADDER = [[1, 26, 16], [1, 22, 14], [1, 19, 13], [2, 26, 16], [2, 22, 14], [2, 19, 13]];
  var BOX_TOP = 214;
  function boxColW(cols) { return cols === 1 ? UW : (UW - GUT) / 2; }
  function sideUnits(s, cols, font) {
    var nl = 0, ch = charsFor(boxColW(cols), font);
    (s.notes || []).forEach(function (t) { nl += wrapChars(t, ch).length; });
    return 1.6 + 1 + (s.bat || 0) + 0.6 + 1 + (s.pit || 0) + (nl ? 0.4 + nl : 0);
  }
  function layoutBox(a, h) {
    var band = H0 - BOX_TOP - FOOT, L = BOX_LADDER[0], u = 0;
    for (var i = 0; i < BOX_LADDER.length; i++) {
      L = BOX_LADDER[i];
      var ua = sideUnits(a, L[0], L[2]), uh = sideUnits(h, L[0], L[2]);
      u = L[0] === 1 ? ua + 1 + uh : Math.max(ua, uh);
      if (u * L[1] <= band) return { cols: L[0], rowH: L[1], font: L[2], H: H0, units: u };
    }
    var need = BOX_TOP + FOOT + u * L[1];
    return { cols: L[0], rowH: L[1], font: L[2], H: H0 + Math.ceil((need - H0) / 120) * 120, units: u };
  }
  // The day slate: [columns, cell height]; the first rung that holds every
  // final inside 675 px wins, else the last rung on a canvas grown in 120 px steps.
  var SLATE_LADDER = [[2, 150], [3, 140], [4, 124], [4, 108], [5, 108], [5, 96]];
  var SLATE_TOP = 116, SGAP = 14;
  function layoutSlate(n) {
    n = Math.max(1, n || 0);
    var band = H0 - SLATE_TOP - FOOT, L = SLATE_LADDER[0], rows = 1;
    for (var i = 0; i < SLATE_LADDER.length; i++) {
      L = SLATE_LADDER[i]; rows = Math.ceil(n / L[0]);
      // a short day takes taller cells (up to 1.4 times the rung's), so the type grows to fill the card
      if (rows * (L[1] + SGAP) - SGAP <= band) {
        return { cols: L[0], cellH: Math.max(L[1], Math.min(Math.round(L[1] * 1.4), Math.floor((band + SGAP) / rows) - SGAP)), rows: rows, H: H0 };
      }
    }
    var need = SLATE_TOP + FOOT + rows * (L[1] + SGAP) - SGAP;
    return { cols: L[0], cellH: L[1], rows: rows, H: H0 + Math.ceil((need - H0) / 120) * 120 };
  }

  // ---- canvas pieces
  function sheet(env, H) {
    var c = document.createElement("canvas"), s = env.scale || 2;
    c.width = W * s; c.height = H * s;
    var g = c.getContext("2d");
    g.scale(s, s);
    g.textBaseline = "alphabetic";
    return { c: c, g: g };
  }
  // text at x (al 0 left, .5 centre, 1 right), ellipsized to max; returns its width
  function tx(g, P, t, x, y, f, col, max, al, sp) {
    g.font = f + "px " + P.MONO; g.fillStyle = col || P.fg;
    if (sp && "letterSpacing" in g) g.letterSpacing = sp + "px";
    t = GF().fitTxt(g, t, max || UW);
    var w = g.measureText(t).width;
    g.fillText(t, x - w * (al || 0), y);
    if (sp && "letterSpacing" in g) g.letterSpacing = "0px";
    return w;
  }
  function rule(g, col, x, y, w, h) { g.fillStyle = col; g.fillRect(x, y, w, h); }
  // the newsprint halftone of .sp-banner (light only: --paper-dot is unset in dark)
  function halftone(g, x, y, w, h) {
    var dot = GF().tok("--paper-dot", "");
    if (!dot) return;
    g.fillStyle = dot;
    for (var yy = y + 2; yy < y + h; yy += 4) for (var xx = x + 2; xx < x + w; xx += 4) g.fillRect(xx, yy, 1.2, 1.2);
  }
  // The nameplate, the banner and the footer every card shares.
  function frame(g, P, H, o, head, right) {
    g.fillStyle = P.bg; g.fillRect(0, 0, W, H);
    GF().brandHead(g, P, PAD, 44);
    tx(g, P, "SCORES", PAD + 196, 44, "700 18", P.accent, 160, 0, 2);
    tx(g, P, dateLong(o.date).toUpperCase(), W - PAD, 44, "700 14", P.sub, 520, 1, 1);
    rule(g, P.fg, PAD, 56, UW, 3); rule(g, P.fg, PAD, 61, UW, 1);
    halftone(g, PAD, 64, UW, 34);
    var hw = tx(g, P, head, PAD + 2, 90, "700 24", P.fg, UW * 0.6, 0, 2);
    if (right) tx(g, P, right, W - PAD - 2, 89, "700 16", P.fg, UW - hw - 40, 1, 1);
    rule(g, P.fg, PAD, 99, UW, 1);
    rule(g, P.line, PAD, H - FOOT + 8, UW, 1);
    tx(g, P, o.url, PAD, H - 18, "700 15", P.fg, UW * 0.6);
    tx(g, P, "Data: MLB. eephus.io", W - PAD, H - 18, "13", P.sub, UW * 0.35, 1);
  }
  function logoURL(cd, px) {
    var h = window.EEPHUS_HUB;
    return h && h.teamLogoURL ? h.teamLogoURL(cd, px) : "";
  }
  // MLB's square face crop (the projections.js and /news/ supplier), ACAO *;
  // no generic silhouette, so a missing photo fails and draws the initials.
  function shotURL(id, px) {
    return id ? "https://img.mlbstatic.com/mlb-photos/image/upload/c_fill,g_face,w_" + px + ",h_" + px +
      ",q_auto:best/v1/people/" + id + "/headshot/67/current" : "";
  }
  function logos(codes, px) {
    var out = {};
    return Promise.all(codes.map(function (cd) {
      return GF().loadImg(logoURL(cd, px)).then(function (im) { out[cd] = im; });
    })).then(function () { return out; });
  }
  // A clean club mark (smoothed, never pixelated), on a plate when asked; the
  // club code stands in for a mark that did not load. Dark frames take the
  // page's thin --text-dim glow so a navy mark stays legible.
  function mark(g, P, img, cd, x, y, s, plate) {
    if (plate) {
      g.fillStyle = P.bg2; g.fillRect(x, y, s, s);
      g.strokeStyle = P.line; g.lineWidth = 1; g.strokeRect(x + 0.5, y + 0.5, s - 1, s - 1);
    }
    if (img) {
      var k = plate ? Math.round(s * 0.12) : 0;
      g.save();
      g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
      if (P.dark) { g.shadowColor = GF().tok("--text-dim", P.sub); g.shadowBlur = 2; }
      g.drawImage(img, x + k, y + k, s - 2 * k, s - 2 * k);
      g.restore();
      return;
    }
    if (!plate) { g.strokeStyle = P.line; g.lineWidth = 1; g.strokeRect(x + 0.5, y + 0.5, s - 1, s - 1); }
    var f = Math.max(8, Math.round(s * 0.32));
    tx(g, P, cd, x + s / 2, y + s / 2 + f * 0.36, "700 " + f, P.fg, s - 4, 0.5);
  }
  // A kicker in a hairline box (.sp-kicker); returns its width.
  function kicker(g, P, t, x, y, f, col) {
    g.font = "700 " + f + "px " + P.MONO;
    var w = g.measureText(t).width + 12;
    g.strokeStyle = col || P.fg; g.lineWidth = 1;
    g.strokeRect(x + 0.5, y - f - 3.5, w - 1, f + 9);
    tx(g, P, t, x + 6, y, "700 " + f, col || P.fg, w);
    return w;
  }

  // The printed line score: the clubs, the innings, then R H E behind a column
  // rule and a rule under the head row; an unplayed home ninth prints "x".
  function lineScore(g, P, c, imgs, x, y, w, rh, f) {
    var line = c.line || [], n = line.length, nameW = Math.min(300, Math.round(w * 0.3));
    var cw = Math.min(46, (w - nameW - 14) / (n + 3)), r0 = x + nameW + n * cw + 14;
    for (var i = 0; i < n; i++) tx(g, P, String(i + 1), x + nameW + (i + 0.5) * cw, y + rh * 0.7, "700 " + (f - 2), P.sub, cw, 0.5);
    ["R", "H", "E"].forEach(function (h, j) { tx(g, P, h, r0 + (j + 0.5) * cw, y + rh * 0.7, "700 " + (f - 2), P.sub, cw, 0.5); });
    rule(g, P.fg, x, y + rh - 1, nameW + n * cw + 14 + 3 * cw, 1);
    rule(g, P.line, r0 - 7, y + rh, 1, rh * 2);
    ["away", "home"].forEach(function (side, k) {
      var t = c[side], yy = y + rh * (k + 1), base = yy + rh * 0.7, won = winner(c, side);
      mark(g, P, imgs[code(t)], code(t), x, yy + 3, rh - 6, false);
      var cwid = tx(g, P, code(t), x + rh + 4, base, "700 " + f, P.fg, nameW - rh - 8);
      tx(g, P, t.short || "", x + rh + 14 + cwid, base, String(f - 2), P.sub, nameW - rh - 22 - cwid);
      for (var i = 0; i < n; i++) {
        var v = line[i] ? line[i][k] : null;
        tx(g, P, v == null ? (c.state === "final" && side === "home" ? "x" : "") : String(v),
          x + nameW + (i + 0.5) * cw, base, String(f), P.fg, cw, 0.5);
      }
      [t.r, t.h, t.e].forEach(function (v, j) {
        tx(g, P, n0(v), r0 + (j + 0.5) * cw, base, (j === 0 || won ? "700 " : "") + f, P.fg, cw, 0.5);
      });
    });
    return rh * 3;
  }

  // ---- card 1: the final score
  async function drawFinal(env, o) {
    var c = o.card, P = env.palette, cds = [code(c.away), code(c.home)];
    var big = await logos(cds, 176), small = await logos(cds, 64);
    var S = sheet(env, H0), g = S.g;
    frame(g, P, H0, o, finalWord(c).toUpperCase(), (c.venue && c.venue.name) || "");
    var top = 116, ser = seriesText(c, o.date);
    if (ser) { tx(g, P, ser, PAD, 132, "700 18", P.fg, UW); top = 146; }
    ["away", "home"].forEach(function (side, k) {
      var t = c[side], y = top + k * 104, won = winner(c, side), ink = won ? P.fg : P.sub;
      mark(g, P, big[code(t)], code(t), PAD, y + 8, 88, true);
      tx(g, P, t.name || t.short || code(t), PAD + 108, y + 52, "700 36", ink, UW - 300);
      var rec = t.wl && isNum(t.wl.w) ? t.wl.w + "-" + t.wl.l : "";
      tx(g, P, code(t) + (rec ? "  " + rec : ""), PAD + 108, y + 82, "16", P.sub, UW - 300);
      tx(g, P, n0(t.r), W - PAD, y + 84, "700 76", ink, 180, 1);
      if (!k) rule(g, P.line, PAD, y + 103, UW, 1);
    });
    var y = top + 2 * 104 + 18;
    y += lineScore(g, P, c, small, PAD, y, UW, 34, 18) + 36;
    var dec = decisions(c, true);
    if (dec.length) { tx(g, P, dec.join("    "), PAD, y, "700 18", P.fg, UW); y += 32; }
    if (c.star) {
      tx(g, P, "Star: " + c.star.name + " (" + c.star.team + "). " + (c.star.why || ""), PAD, y, "15", P.sub, UW);
    }
    return S.c;
  }

  // ---- card 2: the full box score
  var BAT = ["AB", "R", "H", "RBI", "BB", "K", "P/AB"], PIT = ["IP", "H", "R", "ER", "BB", "K", "HR", "P/IP"];
  function batCells(r) { return [n0(r.ab), n0(r.r), n0(r.h), n0(r.rbi), n0(r.bb), n0(r.k), f1(r.p_ab)]; }
  function pitCells(r) { return [ipOf(r.outs), n0(r.h), n0(r.r), n0(r.er), n0(r.bb), n0(r.k), n0(r.hr), f1(r.p_ip)]; }
  function decOf(r) {
    var d = r.dec || {}, m = [];
    if (d.w) m.push("W"); if (d.l) m.push("L"); if (d.sv) m.push("S"); if (d.hld) m.push("H"); if (d.bs) m.push("BS");
    return m.length ? "(" + m.join(", ") + ")" : "";
  }
  // One agate block: the head row over a rule, then a row per player, the name
  // left (a substitute indented, as the paper sets it) and every figure right.
  function agate(g, P, x, y, w, rh, f, head, cols, rows) {
    var nameW = Math.round(w * 0.4), cw = (w - nameW) / cols.length, b = rh * 0.72;
    tx(g, P, head, x, y + b, "700 " + f, P.fg, nameW - 6);
    cols.forEach(function (h, i) { tx(g, P, h, x + nameW + cw * (i + 1) - 3, y + b, "700 " + f, P.sub, cw - 4, 1); });
    rule(g, P.fg, x, y + rh - 2, w, 1);
    rows.forEach(function (r, j) {
      var yy = y + rh * (j + 1) + b, ind = r.sub ? 10 : 0;
      var nw = tx(g, P, r.name, x + ind, yy, String(f), P.fg, nameW - ind - 40);
      if (r.tag) tx(g, P, r.tag, x + ind + nw + 6, yy, String(f - 2), P.sub, nameW - ind - nw - 12);
      r.cells.forEach(function (v, i) { tx(g, P, v, x + nameW + cw * (i + 1) - 3, yy, String(f), P.fg, cw - 4, 1); });
    });
    return rh * (rows.length + 1);
  }
  function boxSide(g, P, c, side, b, imgs, x, y, w, L) {
    var t = c[side], rh = L.rowH, f = L.font, hh = rh * 1.6;
    mark(g, P, imgs[code(t)], code(t), x, y + hh - rh - 4, rh, false);
    tx(g, P, (code(t) + " " + (t.name || t.short || "")).toUpperCase(), x + rh + 8, y + hh - 9, "700 " + (f + 2), P.fg, w - rh - 8, 0, 1);
    rule(g, P.fg, x, y + hh - 3, w, 2);
    y += hh;
    y += agate(g, P, x, y, w, rh, f, "Batting", BAT, (b.batting || []).map(function (r) {
      return { name: r.name, tag: r.pos || "", sub: isNum(r.order) && r.order % 100 !== 0, cells: batCells(r) };
    }));
    y += rh * 0.6;
    y += agate(g, P, x, y, w, rh, f, "Pitching", PIT, (b.pitching || []).map(function (r) {
      return { name: r.name, tag: decOf(r), cells: pitCells(r) };
    }));
    var notes = b.notes || [];
    if (notes.length) {
      y += rh * 0.4;
      notes.forEach(function (t) {
        wrapChars(t, charsFor(w, f)).forEach(function (ln) { tx(g, P, ln, x, y + rh * 0.72, String(f - 1), P.sub, w); y += rh; });
      });
    }
    return y;
  }
  function boxShape(b) {
    b = b || {};
    return { bat: (b.batting || []).length, pit: (b.pitching || []).length, notes: b.notes || [] };
  }
  async function drawBox(env, o) {
    var c = o.card, bx = o.game.box || {}, P = env.palette;
    var L = layoutBox(boxShape(bx.away), boxShape(bx.home));
    var imgs = await logos([code(c.away), code(c.home)], 64);
    var S = sheet(env, L.H), g = S.g;
    frame(g, P, L.H, o, "BOX SCORE", scoreLine(c) + ". " + finalWord(c));
    lineScore(g, P, c, imgs, PAD, 108, UW, 26, 15);
    var dec = decisions(c, false);
    if (dec.length) tx(g, P, dec.join(", "), PAD, 204, "700 14", P.fg, UW);
    var cw = boxColW(L.cols);
    if (L.cols === 2) {
      rule(g, P.line, PAD + cw + GUT / 2, BOX_TOP, 1, L.H - FOOT - BOX_TOP - 4);
      boxSide(g, P, c, "away", bx.away || {}, imgs, PAD, BOX_TOP, cw, L);
      boxSide(g, P, c, "home", bx.home || {}, imgs, PAD + cw + GUT, BOX_TOP, cw, L);
    } else {
      var y = boxSide(g, P, c, "away", bx.away || {}, imgs, PAD, BOX_TOP, cw, L);
      boxSide(g, P, c, "home", bx.home || {}, imgs, PAD, y + L.rowH, cw, L);
    }
    return S.c;
  }

  // ---- card 3: the top performers (the Stars of the Game rule's top three)
  // The star's own box-score line, as the Box score card prints it: pitching
  // for a star on runs prevented, batting otherwise; null when the box lacks him.
  function statLine(gm, s) {
    var hit = null, pit = null;
    ["away", "home"].forEach(function (side) {
      var b = (gm.box || {})[side] || {};
      (b.batting || []).forEach(function (r) { if (r.id === s.id) hit = { head: BAT, cells: batCells(r) }; });
      (b.pitching || []).forEach(function (r) { if (r.id === s.id) pit = { head: PIT, cells: pitCells(r) }; });
    });
    return s.basis === "runs" ? pit || hit : hit || pit;
  }
  async function drawStars(env, o) {
    var c = o.card, P = env.palette, st = (o.game.stars || []).slice(0, 3), n = Math.max(1, st.length);
    var shots = await Promise.all(st.map(function (s) { return GF().loadImg(shotURL(s.id, 300)); }));
    var imgs = await logos(st.map(function (s) { return s.team; }), 64);
    var S = sheet(env, H0), g = S.g;
    frame(g, P, H0, o, "STARS OF THE GAME", scoreLine(c) + ". " + finalWord(c));
    var cw = (UW - GUT * (n - 1)) / n, top = 118;
    st.forEach(function (s, i) {
      var x = PAD + i * (cw + GUT), y = top + 28;
      if (i) rule(g, P.line, x - GUT / 2, top + 8, 1, H0 - FOOT - top - 64);
      kicker(g, P, ordinal(s.rank || i + 1).toUpperCase() + " STAR", x, y, 15, P.accent);
      var hs = 150, hy = y + 18;
      if (shots[i]) {
        g.fillStyle = P.bg2; g.fillRect(x, hy, hs, hs);
        g.drawImage(shots[i], x, hy, hs, hs);
        g.strokeStyle = P.line; g.lineWidth = 1; g.strokeRect(x + 0.5, hy + 0.5, hs - 1, hs - 1);
      } else {
        mark(g, P, null, GF().initialsOf(s.name), x, hy, hs, true);
      }
      var rx = x + hs + 16, rw = cw - hs - 16;
      mark(g, P, imgs[s.team], s.team, rx, hy, 40, false);
      tx(g, P, s.team, rx + 48, hy + 28, "700 18", P.fg, rw - 48);
      tx(g, P, signed3(s.score), rx, hy + 92, "700 36", P.fg, rw);
      var basis = s.basis === "runs" ? "runs prevented" : "win probability added";
      wrapChars(basis, charsFor(rw, 14)).slice(0, 2).forEach(function (ln, j) { tx(g, P, ln, rx, hy + 116 + 18 * j, "14", P.sub, rw); });
      var ny = hy + hs + 38, nl = wrapChars(s.name, charsFor(cw, 26)).slice(0, 2);
      nl.forEach(function (ln, j) { tx(g, P, ln, x, ny + 30 * j, "700 26", P.fg, cw); });
      var wy = ny + 30 * nl.length + 8;
      var wl = wrapChars(s.why || "", charsFor(cw, 16)).slice(0, 5);
      wl.forEach(function (ln, j) { tx(g, P, ln, x, wy + 22 * j, "16", P.fg, cw); });
      var sl = statLine(o.game, s), ay = wy + 22 * wl.length + 18, aw = cw / Math.max(1, sl ? sl.head.length : 1);
      if (sl) {
        sl.head.forEach(function (h, j) { tx(g, P, h, x + aw * (j + 1) - 4, ay, "700 13", P.sub, aw - 4, 1); });
        rule(g, P.fg, x, ay + 6, cw, 1);
        sl.cells.forEach(function (v, j) { tx(g, P, v, x + aw * (j + 1) - 4, ay + 28, "700 18", P.fg, aw - 4, 1); });
      }
    });
    var note = "Stars of the Game: a published rule, not an award." +
      (o.game.first_star_note ? " First star: top player on the winning team." : "");
    tx(g, P, note, PAD, H0 - FOOT - 14, "13", P.sub, UW);
    return S.c;
  }

  // ---- card 4: the day slate
  function cell(g, P, c, imgs, x, y, w, h, ds) {
    g.fillStyle = P.bg2; g.fillRect(x, y, w, h);
    g.strokeStyle = P.line; g.lineWidth = 1; g.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    rule(g, P.fg, x, y, w, 2);
    var p = 10, kf = Math.max(11, Math.round(h * 0.1)), ky = y + Math.round(h * 0.2);
    var kw = tx(g, P, finalWord(c).toUpperCase(), x + p, ky, "700 " + kf, P.fg, w * 0.5, 0, 1);
    var ser = seriesText(c, ds);
    if (ser) {
      // a narrow cell keeps the series state: the round's name goes first ("Game 3 of 5, CHW leads 2-1")
      var sf = Math.max(11, Math.round(kf * 0.8)), sw = w - kw - 3 * p;
      g.font = sf + "px " + P.MONO;
      if (g.measureText(ser).width > sw && ser.indexOf(", ") > 0) ser = ser.slice(ser.indexOf(", ") + 2);
      tx(g, P, ser, x + w - p, ky, String(sf), P.sub, sw, 1);
    }
    var ls = Math.round(h * 0.2), cf = Math.round(h * 0.15), rf = Math.round(h * 0.19);
    ["away", "home"].forEach(function (side, k) {
      var t = c[side], cy = y + h * (0.42 + 0.23 * k), won = winner(c, side), ink = won ? P.fg : P.sub;
      mark(g, P, imgs[code(t)], code(t), x + p, cy - ls / 2, ls, false);
      var nw = tx(g, P, code(t), x + p + ls + 8, cy + cf * 0.36, (won ? "700 " : "") + cf, ink, w * 0.4);
      if (w > 300) tx(g, P, t.short || "", x + p + ls + 16 + nw, cy + cf * 0.36, String(Math.round(cf * 0.8)), P.sub, w - ls - nw - 90);
      tx(g, P, n0(t.r), x + w - p, cy + rf * 0.36, "700 " + rf, ink, 80, 1);
    });
    var dec = decisions(c, false);
    if (dec.length) tx(g, P, dec.join(", "), x + p, y + h - Math.round(h * 0.08), String(Math.max(11, Math.round(h * 0.095))), P.sub, w - 2 * p);
  }
  async function drawSlate(env, o) {
    var P = env.palette, gs = o.finals, L = layoutSlate(gs.length), cds = [];
    gs.forEach(function (c) { cds.push(code(c.away), code(c.home)); });
    var imgs = await logos(cds, 64);
    var S = sheet(env, L.H), g = S.g;
    var right = gs.length + (gs.length === 1 ? " final" : " finals") + (o.others ? ", " + o.others + " not final" : "");
    frame(g, P, L.H, o, "FINAL SCORES", right);
    var cw = (UW - SGAP * (L.cols - 1)) / L.cols, x0 = gs.length < L.cols ? PAD + (UW - gs.length * (cw + SGAP) + SGAP) / 2 : PAD;
    gs.forEach(function (c, i) {
      cell(g, P, c, imgs, x0 + (i % L.cols) * (cw + SGAP), SLATE_TOP + Math.floor(i / L.cols) * (L.cellH + SGAP), cw, L.cellH, o.date);
    });
    return S.c;
  }

  // ---- the modal spec
  // o: {mode "game"|"day", date, day (the date file), game (the game file, or null)}
  function spec(o) {
    var all = (o.day && o.day.games) || [], gm = o.game, c = gm && gm.card;
    var fin = all.filter(function (x) { return x && x.state === "final"; });
    if (c) all.forEach(function (x) { if (x && x.pk === c.pk && x.state === "final") c = x; });
    var cards = [];
    if (o.mode === "game" && c && c.state === "final") {
      cards.push({ key: "final", label: "Final score" });
      if (gm.box) cards.push({ key: "box", label: "Box score" });
      if (gm.stars && gm.stars.length) cards.push({ key: "stars", label: "Top performers" });
    }
    if (fin.length) cards.push({ key: "slate", label: "Day slate" });
    if (!cards.length) return null;
    var game = cards[0].key !== "slate";
    var base = { date: o.date, card: c, game: gm, finals: fin, others: all.length - fin.length };
    function ctx(k) {
      var slate = k === "slate";
      return Object.assign({}, base, { url: "eephus.io/scores/#" + (slate ? "date=" + o.date : "game=" + c.pk) });
    }
    return {
      kind: "draw", module: "Scores", accentToken: "--accent-lilac", cards: cards, card: cards[0].key,
      title: game ? scoreLine(c) + ". " + finalWord(c) : "Final scores, " + dateLong(o.date),
      url: ctx(cards[0].key).url,
      filenameFor: function (k) {
        return k === "slate" || !c ? o.date + "-scores-slate"
          : o.date + "-" + code(c.away).toLowerCase() + "-at-" + code(c.home).toLowerCase() + "-" + k;
      },
      draw: function (env) { return draw(env.card || cards[0].key, env, ctx(env.card || cards[0].key)); }
    };
  }
  function draw(k, env, o) {
    return k === "box" ? drawBox(env, o) : k === "stars" ? drawStars(env, o) : k === "slate" ? drawSlate(env, o) : drawFinal(env, o);
  }
  var gfxP = null;
  function open(root, o) {
    gfxP = gfxP || (window.EEPHUS_GFX ? Promise.resolve() : new Promise(function (ok, no) {
      var s = document.createElement("script");
      s.src = root.getAttribute("data-gfx-js"); s.onload = ok; s.onerror = no;
      document.head.appendChild(s);
    }));
    return gfxP.then(function () {
      var sp = spec(o);
      if (sp) window.EEPHUS_GFX.open(sp);
      return sp;
    }, function () { gfxP = null; return null; });
  }

  window.EephusScoresGfx = { open: open, spec: spec, draw: draw, layoutBox: layoutBox, layoutSlate: layoutSlate,
    wrapChars: wrapChars };
})();
