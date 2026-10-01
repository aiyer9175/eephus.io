/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io shared "Generate GFX" modal - boards + cards, every module
// =============================================================================
// A PROSPX-style Generate GFX experience for the surfaces that don't host the
// PROSPX app (Free Agency, MLB Projections): a chip opens a modal with a live
// preview, Format / Theme / Accent / Show controls, and Copy / Download / Share.
//
// Canvas-native by the EEPHUS_HUB precedent (html2canvas can't resolve CSS
// var(); hand-drawn cards are deterministic in both themes). Two render paths:
//   kind:"board" -> a column-driven leaderboard, drawn here, format-aware
//                   (Wide fits every column; tall formats drop wide-only
//                   columns and show more rows).
//   kind:"card"  -> one subject, delegated to EEPHUS_HUB.drawCard (the unified
//                   player card already shipping on these surfaces).
//   kind:"newsday" -> the /news/ per-date digest (2026-07-23): EVERY item from
//                   one date at a fixed 1200px width - rows auto-fit (height/
//                   font step-down, then two columns, then a TALLER canvas in
//                   steps; items are never dropped), each row carrying a
//                   headshot (fallback: initials disc) + team logo chip
//                   (fallback: omitted) + colored event text.
//   kind:"sourcecomp" -> the glossary Source Comparison share card
//                   (2026-07-23): fixed 1200x675 (the Twitter card) - key-stat
//                   tiles + ranked horizontal accuracy bar panels, the eFV bar
//                   accented. Pure text/vector, no remote images, so the
//                   export canvas is taint-free by construction.
//
//   EEPHUS_GFX.open(spec)   spec = {
//     kind:"board"|"card"|"newsday"|"sourcecomp", module, accentToken?, title,
//     subtitle?, url, filenameBase, caption?,
//     board?: { columns:[{label, frac, narrowFrac?, align?, wideOnly?}],
//               rows:[{ cells:[{ t, sub?, c? }] }], counts?:[10,25,50] },
//     card?:  <EEPHUS_HUB.drawCard opts>,
//     items?: [{name, sub?, type?, val?, c?, shot?, logo?}] (newsday),
//     dateLabel?: "Jul 23, 2026" (newsday),
//     comp?:  { tiles:[{stat, label, sub?}],
//               panels:[{title, lo, hi, star?, rows:[{label, v, isEfv?, c?}]}],
//               note? } (sourcecomp) }
//   EEPHUS_GFX.chipHTML(id, label?)   a ready "Generate GFX" chip button
(function () {
  "use strict";

  var FORMATS = {
    wide:     { w: 1600, h: 900,  label: "Wide 16:9" },
    twitter:  { w: 1200, h: 675,  label: "Twitter 1200x675" },
    portrait: { w: 1080, h: 1350, label: "Portrait 4:5" },
    tall:     { w: 1080, h: 1620, label: "Tall 2:3" },
    square:   { w: 1080, h: 1080, label: "Square 1:1" },
    story:    { w: 1080, h: 1920, label: "Story 9:16" },
  };
  // Accent swatches -> safe, theme-aware tokens (defined in site.css :root).
  var ACCENTS = {
    lilac: "--accent-lilac",   // signature brand color (default)
    cyan:  "--accent-cyan", green: "--accent-green", gold: "--accent-gold",
    navy:  "--accent-navy", red:   "--accent-red",
  };
  var COLOR_KEYS = { pos: "green", neg: "red", accent: "accent", muted: "sub" };

  var _spec = null;
  var _opts = { format: "wide", theme: "auto", accent: null, count: 25 };
  var _origTheme = null;
  var _canvas = null;
  var _busy = false;
  var _renderPending = false;
  var _lastFocus = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function tok(name, fb) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fb;
  }
  function accentToken() {
    if (_opts.accent && ACCENTS[_opts.accent]) return ACCENTS[_opts.accent];
    return (_spec && _spec.accentToken) || "--accent-lilac";
  }

  // ---- shared canvas primitives (single owner) -------------------------------
  // DE-DUP 2026-07-23: this module owns FORMATS/ACCENTS, the CSS-token resolver
  // (tok), the resolved canvas palette (canvas can't read var()), the iridescent
  // ramp stops, and theme forcing. EEPHUS_HUB.drawCard consumes these via the
  // EEPHUS_GFX namespace (with a thin local fallback for pages - prospx - that
  // load the hub without this module).
  // Export supersample factor: canvases draw at SCALE x backing pixels via
  // ctx.scale (all geometry stays W-relative), so the PNG ships at 2x while the
  // modal preview CSS size is unchanged (.egfx-canvas max-width caps it).
  var SCALE = 2;
  function palette(accentTok) {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    return {
      dark: dark,
      bg:   tok("--bg-primary",    dark ? "#101014" : "#F6F1E4"),
      bg2:  tok("--bg-secondary",  dark ? "#16161B" : "#EFE9D8"),
      fg:   tok("--text-primary",  dark ? "#ECEEF2" : "#0F1B2D"),
      sub:  tok("--text-tertiary", dark ? "#868A95" : "#6B6657"),
      line: tok("--border",        dark ? "#2B2B31" : "#C9C1AE"),
      accent: tok(accentTok || "--accent-lilac", dark ? "#00D9FF" : "#0E7C86"),
      pos: dark ? "#4FFF9E" : "#1F7A3A",
      neg: dark ? "#FF6B6B" : "#B91C1C",
      // A canvas 2d context cannot resolve var(--font-logo), so the logo stack is
      // repeated here as a literal and MUST be kept in step with the
      // --font-logo token in assets/site.css.
      // test_board_card_typography.py fails the build if it drifts.
      MONO: '"PixelMplus12","MS Gothic","MS UI Gothic","Osaka-Mono",monospace',
      ramp: dark
        ? [[0, "#00D9FF"], [0.3, "#B47CFF"], [0.55, "#FF4FD8"], [0.78, "#FFD700"], [1, "#4FFF9E"]]
        : [[0, "#B91C1C"], [0.35, "#C9A227"], [0.65, "#1F7A3A"], [1, "#0E2B4D"]],
    };
  }
  // Force (or restore) the document theme. theme "light"|"dark" forces it; any
  // other value restores `orig` (null/undefined = remove the attribute).
  function forceTheme(theme, orig) {
    var root = document.documentElement;
    if (theme === "light" || theme === "dark") root.setAttribute("data-theme", theme);
    else if (orig != null) root.setAttribute("data-theme", orig);
    else root.removeAttribute("data-theme");
  }

  // ---- canvas board renderer -------------------------------------------------
  // Right edge of column i's track: the next column's origin less an 8px gutter,
  // or in the last column the PANEL edge. The panel edge is not the canvas edge:
  // in the two-panel layout the left panel ends mid-canvas, and clamping its last
  // column to the canvas let it paint through the gutter and over the right panel.
  function trackEnd(xs, panelRight, i) {
    return i + 1 < xs.length ? xs[i + 1] - 8 : panelRight;
  }
  function renderBoard(spec, fmt) {
    var W = fmt.w, H = fmt.h;
    var PAD = Math.round(W * 0.033);
    var c = document.createElement("canvas");
    c.width = W * SCALE; c.height = H * SCALE;
    var g = c.getContext("2d");
    g.scale(SCALE, SCALE);
    var P = palette(accentToken());
    var bg = P.bg, fg = P.fg, sub = P.sub, line = P.line,
        accent = P.accent, pos = P.pos, neg = P.neg, MONO = P.MONO;
    var colorOf = function (k) {
      var key = COLOR_KEYS[k] || k;
      return key === "green" ? pos : key === "red" ? neg : key === "accent" ? accent
        : key === "sub" ? sub : fg;
    };
    g.fillStyle = bg; g.fillRect(0, 0, W, H);

    // header: brand + module eyebrow + date, iridescent rule
    g.textBaseline = "alphabetic";
    g.fillStyle = fg; g.font = "700 26px " + MONO;
    g.fillText("EEPHUS.IO", PAD, 50);
    g.fillStyle = accent; g.font = "700 22px " + MONO;
    g.fillText(String(spec.module || "").toUpperCase(), PAD + 196, 50);
    var today = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    g.fillStyle = sub; g.font = "15px " + MONO;
    g.fillText(today, W - PAD - g.measureText(today).width, 50);
    var ramp = g.createLinearGradient(PAD, 0, W - PAD, 0);
    P.ramp.forEach(function (s) { ramp.addColorStop(s[0], s[1]); });
    g.fillStyle = ramp; g.fillRect(PAD, 66, W - 2 * PAD, 3);

    // title + subtitle
    g.fillStyle = fg; g.font = "700 34px " + MONO;
    g.fillText(spec.title || "", PAD, 108);
    if (spec.subtitle) {
      g.fillStyle = sub; g.font = "15px " + MONO;
      g.fillText(spec.subtitle, PAD, 134);
    }

    // columns: drop wide-only columns on narrow canvases. AUDIT 2026-07-18 (A4):
    // record each surviving column's ORIGINAL index so row cells (built by callers
    // to match the FULL column list) are read by original position -- a non-trailing
    // wideOnly column previously shifted every later cell one column left (FA board
    // printed Deal WAR under the Surplus header on all narrow formats).
    var board = spec.board || {};
    var allCols = board.columns || [];
    var origIdx = [];
    var cols = allCols.filter(function (col, j) {
      var keep = !(col.wideOnly && W < 1300);
      if (keep) origIdx.push(j);
      return keep;
    });
    var usableW = W - 2 * PAD;
    // A column may declare a SECOND width for the narrow column list, and the
    // reason is arithmetic rather than taste. When wide-only columns drop out,
    // the survivors keep their RATIO to each other and simply re-normalize, so
    // one frac vector has to serve two very different column sets. Measured
    // 2026-08-07 on the PAL RP->SP board: the vector that makes the 8-column
    // 723px panel fit exactly (Tier needs 33% of the non-wide budget there)
    // starves the same columns in the 5-column 488px panel (Tier can only have
    // 22% before # and FIT start clipping), and tuning for the narrow list puts
    // the 25-row flagship export back to a fully truncated Tier column. There
    // is no single vector: 168px of Tier in a 108px track is not a rounding
    // problem. narrowFrac is optional and falls back to frac, so every existing
    // caller keeps its exact current geometry.
    var narrowed = cols.length !== allCols.length;
    function fracOf(col) {
      return (narrowed && col.narrowFrac != null) ? col.narrowFrac : (col.frac || 0);
    }
    var totFrac = cols.reduce(function (a, col) { return a + fracOf(col); }, 0) || 1;

    // rows: fit by height, capped by the Show count. PARITY 2026-07-23 (the
    // prospx approach, implemented fresh): when the requested count outgrows a
    // single column's fit, the row block splits into TWO balanced side-by-side
    // panels (each with its own header rule), and the whole block is vertically
    // centered in the band between the subtitle and the footer.
    var rowsAll = board.rows || [];
    var rowH = 40;
    var bandTop = 148;           // just under the title/subtitle block
    var footH = 96;
    var availH = H - footH - bandTop;
    // 58 = header baseline offset (20) + header-to-first-row gap (38)
    var fit1 = Math.max(1, Math.floor((availH - 58) / rowH));
    var cap = (_opts.count === "all") ? rowsAll.length : Math.min(rowsAll.length, _opts.count);
    var nPanels = cap > fit1 ? 2 : 1;
    var n = Math.min(cap, fit1 * nPanels);
    var perCol = Math.ceil(n / nPanels);
    var yOff = Math.max(0, Math.floor((availH - (58 + perCol * rowH)) / 2));
    var headY = bandTop + 20 + yOff;
    var topY = headY + 38;
    var GUT = Math.round(W * 0.03);
    var panelW = (usableW - GUT * (nPanels - 1)) / nPanels;
    // per-panel column x origins (fracs are panel-relative, so both panels share
    // one geometry; a wide panel simply spaces the same fractions further apart)
    var panelX = [], colX = [];
    for (var p = 0; p < nPanels; p++) {
      var px = PAD + p * (panelW + GUT);
      panelX.push(px);
      var xs = [], acc = 0;
      cols.forEach(function (col) { xs.push(px + (acc / totFrac) * panelW); acc += fracOf(col); });
      colX.push(xs);
      g.font = "700 14px " + MONO;
      cols.forEach(function (col, i) {
        g.fillStyle = sub;
        g.fillText(fitTxt(g, String(col.label || "").toUpperCase(),
                          trackEnd(xs, px + panelW, i) - xs[i]), xs[i], headY);
      });
      g.strokeStyle = line; g.lineWidth = 1;
      g.beginPath(); g.moveTo(px, headY + 10); g.lineTo(px + panelW, headY + 10); g.stroke();
    }
    for (var r = 0; r < n; r++) {
      var row = rowsAll[r] || {};
      var cells = row.cells || [];
      var pi = Math.floor(r / perCol);
      var x0 = colX[pi];
      var y = topY + (r % perCol) * rowH + 18;
      for (var i = 0; i < cols.length; i++) {
        var cell = cells[origIdx[i]] || {};
        var t = cell.t == null ? "" : String(cell.t);
        var colEnd = trackEnd(x0, panelX[pi] + panelW, i);
        if (cell.sub) {
          g.fillStyle = fg; g.font = "700 17px " + MONO;
          var name = fitTxt(g, t, colEnd - x0[i]);
          g.fillText(name, x0[i], y);
          var subX = x0[i] + g.measureText(name).width + 9;
          g.fillStyle = sub; g.font = "12px " + MONO;
          // The sub is decoration, so it yields the whole remainder of the track
          // to the name and is dropped outright when nothing is left. The name
          // is data and is only ever shortened.
          if (colEnd - subX > 0) {
            var st = fitTxt(g, String(cell.sub), colEnd - subX);
            if (st) g.fillText(st, subX, y);
          }
        } else {
          g.fillStyle = cell.c ? colorOf(cell.c) : fg;
          g.font = (cell.c === "accent" || cell.bold ? "700 " : "") + "16px " + MONO;
          g.fillText(fitTxt(g, t, colEnd - x0[i]), x0[i], y);
        }
      }
      if (r % perCol < perCol - 1 && r < n - 1) {
        g.strokeStyle = line; g.globalAlpha = 0.5;
        g.beginPath(); g.moveTo(panelX[pi], y + 13); g.lineTo(panelX[pi] + panelW, y + 13); g.stroke();
        g.globalAlpha = 1;
      }
    }

    // footer: optional legend, caption + url left, watermark right
    if (board.legend) {
      g.fillStyle = sub; g.font = "13px " + MONO;
      g.fillText(String(board.legend), PAD, H - 74);
    }
    if (spec.caption) {
      g.fillStyle = sub; g.font = "13px " + MONO;
      g.fillText(spec.caption, PAD, H - 52);
    }
    if (rowsAll.length > n) {
      g.fillStyle = sub; g.font = "13px " + MONO;
      var more = "+ " + (rowsAll.length - n) + " more on " + (spec.url || "eephus.io");
      g.fillText(more, W - PAD - g.measureText(more).width, H - 52);
    }
    g.fillStyle = fg; g.font = "700 16px " + MONO;
    g.fillText(spec.url || "eephus.io", PAD, H - 26);
    g.fillStyle = sub; g.font = "700 13px " + MONO;
    var wm = "eephus.io";
    g.fillText(wm, W - PAD - g.measureText(wm).width, H - 26);
    return c;
  }

  // ---- canvas per-date news renderer (kind:"newsday", 2026-07-23) ------------
  // The /news/ per-date digest card. Contract: EVERY item from the chosen date
  // renders - nothing is silently dropped. Fixed 1200px width (the Twitter-card
  // width); the fit ladder steps row height/fonts down and splits into two
  // columns as the day grows, and when even the two-column legibility floor
  // cannot hold the day inside 675px the canvas grows TALLER in 120px steps.
  // Every remote image loads crossOrigin anonymous and a failure resolves null
  // (headshot -> initials disc, logo -> omitted), so toBlob/toDataURL never
  // throws on a tainted canvas. Promise-cached so theme/accent re-renders
  // don't refetch.
  var _IMG_CACHE = {};
  function loadImg(url) {
    if (!url) return Promise.resolve(null);
    if (!_IMG_CACHE[url]) {
      _IMG_CACHE[url] = new Promise(function (resolve) {
        var img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = function () { resolve(img); };
        img.onerror = function () { resolve(null); };
        img.src = url;
      });
    }
    return _IMG_CACHE[url];
  }
  function initialsOf(name) {
    var parts = String(name || "").trim().split(/\s+/);
    var a = (parts[0] || "").charAt(0);
    var b = (parts.length > 1 ? parts[parts.length - 1] : "").charAt(0);
    return ((a + b) || "?").toUpperCase();
  }
  // Contract: the result NEVER measures wider than max. Callers rely on that to
  // guarantee containment, so the ellipsis floor cannot be one character: on a
  // track too narrow for even "X..." the marker itself overhung, which is how an
  // already-clamped board sub still crossed its column by 8px.
  function fitTxt(g, t, max) {
    t = String(t == null ? "" : t);
    if (g.measureText(t).width <= max) return t;
    while (t.length > 1 && g.measureText(t + "...").width > max) t = t.slice(0, -1);
    if (g.measureText(t + "...").width <= max) return t + "...";
    while (t.length && g.measureText(t).width > max) t = t.slice(0, -1);
    return t;
  }
  async function renderNewsDay(spec) {
    var W = 1200, PAD = Math.round(W * 0.033);
    var items = spec.items || [];
    var n = Math.max(1, items.length);
    // Fit ladder: single column at comfortable row heights first, then two
    // columns stepping down to the 40px legibility floor - first rung that
    // holds the whole day inside the base 675px height wins.
    var LADDER = [[1, 58], [1, 52], [1, 46], [2, 56], [2, 50], [2, 44], [2, 40]];
    var bandTop = 148, footH = 84, H = 675, nCols = 2, rowH = 44, fitOK = false;
    for (var li = 0; li < LADDER.length; li++) {
      if (Math.ceil(n / LADDER[li][0]) * LADDER[li][1] <= H - bandTop - footH) {
        nCols = LADDER[li][0]; rowH = LADDER[li][1]; fitOK = true; break;
      }
    }
    if (!fitOK) { // grow the canvas instead of dropping items (width stays 1200)
      var need = bandTop + footH + Math.ceil(n / nCols) * rowH;
      H += Math.ceil((need - H) / 120) * 120;
    }
    var perCol = Math.ceil(n / nCols);
    // preload every row image up front; failures resolve null (fallback path)
    var shots = await Promise.all(items.map(function (it) { return loadImg(it.shot); }));
    var logos = await Promise.all(items.map(function (it) { return loadImg(it.logo); }));

    var c = document.createElement("canvas");
    c.width = W * SCALE; c.height = H * SCALE;
    var g = c.getContext("2d");
    g.scale(SCALE, SCALE);
    var P = palette(accentToken());
    var bg = P.bg, bg2 = P.bg2, fg = P.fg, sub = P.sub, line = P.line,
        accent = P.accent, MONO = P.MONO;
    var colorOf = function (k) {
      var key = COLOR_KEYS[k] || k;
      return key === "green" ? P.pos : key === "red" ? P.neg : key === "accent" ? accent
        : key === "sub" ? sub : fg;
    };
    g.fillStyle = bg; g.fillRect(0, 0, W, H);

    // header: brand + module eyebrow + generated-on date, iridescent rule
    g.textBaseline = "alphabetic";
    g.fillStyle = fg; g.font = "700 26px " + MONO;
    g.fillText("EEPHUS.IO", PAD, 50);
    g.fillStyle = accent; g.font = "700 22px " + MONO;
    g.fillText(String(spec.module || "").toUpperCase(), PAD + 196, 50);
    var today = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    g.fillStyle = sub; g.font = "15px " + MONO;
    g.fillText(today, W - PAD - g.measureText(today).width, 50);
    var ramp = g.createLinearGradient(PAD, 0, W - PAD, 0);
    P.ramp.forEach(function (s) { ramp.addColorStop(s[0], s[1]); });
    g.fillStyle = ramp; g.fillRect(PAD, 66, W - 2 * PAD, 3);

    // title (carries the date prominently) + subtitle
    g.fillStyle = fg; g.font = "700 34px " + MONO;
    g.fillText(spec.title || "", PAD, 108);
    if (spec.subtitle) {
      g.fillStyle = sub; g.font = "15px " + MONO;
      g.fillText(spec.subtitle, PAD, 134);
    }

    // rows: [headshot | name over type+sub | logo chip + colored value]
    var GUT = Math.round(W * 0.03);
    var usableW = W - 2 * PAD;
    var colW = (usableW - GUT * (nCols - 1)) / nCols;
    var topY = bandTop + Math.max(0, Math.floor((H - footH - bandTop - perCol * rowH) / 2));
    var nameF = rowH >= 52 ? 17 : rowH >= 46 ? 15 : 13;
    var subF = rowH >= 52 ? 12 : 11;
    var valF = rowH >= 52 ? 15 : rowH >= 46 ? 14 : 12;
    if (nCols === 2 && n > perCol) {
      g.strokeStyle = line; g.globalAlpha = 0.5;
      var dx = PAD + colW + GUT / 2;
      g.beginPath(); g.moveTo(dx, topY); g.lineTo(dx, topY + perCol * rowH); g.stroke();
      g.globalAlpha = 1;
    }
    for (var r = 0; r < items.length; r++) {
      var it = items[r] || {};
      var pi = Math.floor(r / perCol);
      var x0 = PAD + pi * (colW + GUT);
      var yTop = topY + (r % perCol) * rowH;
      var cy = yTop + rowH / 2;
      var S = rowH - 12;
      // headshot square (house card treatment) or the initials disc fallback
      var shot = shots[r];
      if (shot) {
        g.fillStyle = bg2; g.fillRect(x0, cy - S / 2, S, S);
        // CONTRACT (2026-08-04d): `it.shot` MUST already be a SQUARE crop.
        // drawImage has no object-fit, so this stretches whatever it is handed
        // into SxS, and MLB source headshots are 480x720 (2:3) - i.e. every
        // face here is currently squashed vertically. The fix belongs at the
        // caller: ask the CDN for `c_fill,g_face,w_{2S},h_{2S}` (Cloudinary
        // crops around the detected face and returns exactly that box), which
        // needs no change to this file. STILL OUTSTANDING for the one supplier
        // that feeds this path, build_site.py shotURL (the news module); the FA
        // and PROSPX callers were converted on 2026-08-04d. Do NOT "fix" it
        // here with cover math once the callers are square: that would re-crop
        // an already-correct crop.
        g.drawImage(shot, x0, cy - S / 2, S, S);
        g.strokeStyle = line; g.lineWidth = 1;
        g.strokeRect(x0, cy - S / 2, S, S);
      } else {
        g.fillStyle = bg2;
        g.beginPath(); g.arc(x0 + S / 2, cy, S / 2, 0, Math.PI * 2); g.fill();
        g.strokeStyle = line; g.lineWidth = 1;
        g.beginPath(); g.arc(x0 + S / 2, cy, S / 2, 0, Math.PI * 2); g.stroke();
        var ini = initialsOf(it.name);
        g.fillStyle = sub; g.font = "700 " + Math.max(10, Math.round(S * 0.38)) + "px " + MONO;
        g.fillText(ini, x0 + S / 2 - g.measureText(ini).width / 2, cy + S * 0.14);
      }
      // colored event value, right-aligned; team logo chip just left of it
      g.font = "700 " + valF + "px " + MONO;
      var vt = String(it.val || "");
      var vx = x0 + colW - g.measureText(vt).width;
      g.fillStyle = colorOf(it.c);
      g.fillText(vt, vx, cy + valF * 0.35);
      var valLeft = vx;
      var lg = logos[r];
      if (lg) {
        var L = Math.min(22, S);
        var lx = vx - 8 - L;
        g.drawImage(lg, lx, cy - L / 2, L, L);
        valLeft = lx;
      }
      // name + "Type - pos - org" line, ellipsized to the space that's left
      var tx = x0 + S + 10;
      var tMax = Math.max(20, valLeft - 10 - tx);
      g.fillStyle = fg; g.font = "700 " + nameF + "px " + MONO;
      g.fillText(fitTxt(g, it.name || "", tMax), tx, cy - 3);
      var st = String(it.type || "") + (it.sub ? " - " + it.sub : "");
      if (st) {
        g.fillStyle = sub; g.font = subF + "px " + MONO;
        g.fillText(fitTxt(g, st, tMax), tx, cy + subF + 3);
      }
      if ((r % perCol) < perCol - 1 && r < items.length - 1) {
        g.strokeStyle = line; g.globalAlpha = 0.5;
        g.beginPath(); g.moveTo(x0, yTop + rowH - 0.5); g.lineTo(x0 + colW, yTop + rowH - 0.5); g.stroke();
        g.globalAlpha = 1;
      }
    }

    // footer: caption + url left, watermark right (never a "+N more" - the
    // per-date card always holds the whole day)
    if (spec.caption) {
      g.fillStyle = sub; g.font = "13px " + MONO;
      g.fillText(spec.caption, PAD, H - 52);
    }
    g.fillStyle = fg; g.font = "700 16px " + MONO;
    g.fillText(spec.url || "eephus.io", PAD, H - 26);
    g.fillStyle = sub; g.font = "700 13px " + MONO;
    var wm = "eephus.io";
    g.fillText(wm, W - PAD - g.measureText(wm).width, H - 26);
    return c;
  }

  // ---- canvas source-comparison renderer (kind:"sourcecomp", 2026-07-23) ----
  // The glossary Source Comparison share card: the head-to-head key stats as
  // tiles plus ranked horizontal accuracy bars per source, eFV accented.
  // Fixed 1200x675 (the Twitter card). All numbers arrive in spec.comp, built
  // by the caller from the same artifacts the page renders - the engine draws,
  // it never fetches. No remote images anywhere on this card, so toBlob /
  // toDataURL can never hit a tainted canvas.
  // Two-line greedy word wrap for tile labels; each emitted line is still
  // ellipsized to the box (the fitTxt treatment).
  function wrap2(g, t, max) {
    t = String(t == null ? "" : t);
    if (g.measureText(t).width <= max) return [t];
    var words = t.split(" ");
    var l1 = "", i = 0;
    while (i < words.length) {
      var cand = l1 ? l1 + " " + words[i] : words[i];
      if (l1 && g.measureText(cand).width > max) break;
      l1 = cand; i++;
    }
    return [fitTxt(g, l1, max), fitTxt(g, words.slice(i).join(" "), max)];
  }
  function renderSourceComp(spec) {
    var W = 1200, H = 675, PAD = Math.round(W * 0.033);
    var comp = spec.comp || {};
    var tiles = comp.tiles || [];
    var panels = comp.panels || [];
    var c = document.createElement("canvas");
    c.width = W * SCALE; c.height = H * SCALE;
    var g = c.getContext("2d");
    g.scale(SCALE, SCALE);
    var P = palette(accentToken());
    var bg = P.bg, bg2 = P.bg2, fg = P.fg, sub = P.sub, line = P.line,
        accent = P.accent, MONO = P.MONO;
    g.fillStyle = bg; g.fillRect(0, 0, W, H);

    // header: brand + module eyebrow + date, iridescent rule (house)
    g.textBaseline = "alphabetic";
    g.fillStyle = fg; g.font = "700 26px " + MONO;
    g.fillText("EEPHUS.IO", PAD, 50);
    g.fillStyle = accent; g.font = "700 22px " + MONO;
    g.fillText(String(spec.module || "").toUpperCase(), PAD + 196, 50);
    var today = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    g.fillStyle = sub; g.font = "15px " + MONO;
    g.fillText(today, W - PAD - g.measureText(today).width, 50);
    var ramp = g.createLinearGradient(PAD, 0, W - PAD, 0);
    P.ramp.forEach(function (s) { ramp.addColorStop(s[0], s[1]); });
    g.fillStyle = ramp; g.fillRect(PAD, 66, W - 2 * PAD, 3);

    // title (shrinks to fit, the CS-card hero-name treatment) + subtitle
    var usableW = W - 2 * PAD;
    var tSize = 34;
    g.font = "700 " + tSize + "px " + MONO;
    while (tSize > 22 && g.measureText(String(spec.title || "")).width > usableW) {
      tSize -= 2; g.font = "700 " + tSize + "px " + MONO;
    }
    g.fillStyle = fg;
    g.fillText(String(spec.title || ""), PAD, 108);
    if (spec.subtitle) {
      g.fillStyle = sub; g.font = "15px " + MONO;
      g.fillText(fitTxt(g, spec.subtitle, usableW), PAD, 134);
    }

    // key-stat tiles: one row of bordered squares (the house headshot frame)
    var nT = tiles.length;
    var TGAP = 16, tileTop = 152, tileH = 122;
    var tileW = nT ? (usableW - TGAP * (nT - 1)) / nT : usableW;
    tiles.forEach(function (t, i) {
      var x = PAD + i * (tileW + TGAP);
      g.fillStyle = bg2; g.fillRect(x, tileTop, tileW, tileH);
      g.strokeStyle = line; g.lineWidth = 1;
      g.strokeRect(x, tileTop, tileW, tileH);
      var sSize = 32;
      g.font = "700 " + sSize + "px " + MONO;
      while (sSize > 18 && g.measureText(String(t.stat || "")).width > tileW - 28) {
        sSize -= 2; g.font = "700 " + sSize + "px " + MONO;
      }
      g.fillStyle = accent;
      g.fillText(String(t.stat || ""), x + 14, tileTop + 44);
      g.fillStyle = fg; g.font = "700 12px " + MONO;
      var lines = wrap2(g, t.label, tileW - 28);
      g.fillText(lines[0], x + 14, tileTop + 68);
      if (lines[1]) g.fillText(lines[1], x + 14, tileTop + 84);
      if (t.sub) {
        g.fillStyle = sub; g.font = "11px " + MONO;
        g.fillText(fitTxt(g, String(t.sub), tileW - 28), x + 14, tileTop + (lines[1] ? 104 : 88));
      }
    });

    // ranked accuracy bar panels, side by side (values labeled, best starred)
    var GUT = Math.round(W * 0.03);
    var chartTop = tileTop + tileH + 34;
    var nP = panels.length;
    var panelW = nP ? (usableW - GUT * (nP - 1)) / nP : usableW;
    panels.forEach(function (pn, pi) {
      var x0 = PAD + pi * (panelW + GUT);
      g.fillStyle = fg; g.font = "700 15px " + MONO;
      g.fillText(fitTxt(g, String(pn.title || ""), panelW), x0, chartTop + 14);
      g.strokeStyle = line; g.lineWidth = 1;
      g.beginPath(); g.moveTo(x0, chartTop + 24); g.lineTo(x0 + panelW, chartTop + 24); g.stroke();
      var rows = pn.rows || [];
      var lo = pn.lo || 0;
      var hi = (pn.hi != null && pn.hi !== lo) ? pn.hi : 1;
      // star:false = the caller has no floor that licenses a "best" mark.
      var best = pn.star === false ? null : rows.reduce(function (m, r) {
        return (r.v != null && (m == null || r.v > m)) ? r.v : m;
      }, null);
      var labelW = Math.round(panelW * 0.34), valW = 82;
      var trackX = x0 + labelW, trackW = panelW - labelW - valW;
      var rowH = 46, barH = 16;
      rows.forEach(function (r, ri) {
        var yMid = chartTop + 46 + ri * rowH + barH / 2;
        var col = r.isEfv ? accent : (r.c || sub);
        g.fillStyle = r.isEfv ? fg : sub;
        g.font = (r.isEfv ? "700 " : "") + "13px " + MONO;
        g.fillText(fitTxt(g, String(r.label || ""), labelW - 12), x0, yMid + 4);
        g.globalAlpha = 0.22;
        g.fillStyle = line;
        g.fillRect(trackX, yMid - barH / 2, trackW, barH);
        g.globalAlpha = 1;
        var frac = Math.max(0.02, Math.min(1, ((r.v || 0) - lo) / (hi - lo)));
        g.fillStyle = col;
        g.fillRect(trackX, yMid - barH / 2, trackW * frac, barH);
        var isBest = best != null && r.v === best;
        var vt = (r.v == null ? "-" : Number(r.v).toFixed(3)) + (isBest ? " ★" : "");
        g.fillStyle = isBest ? fg : sub;
        g.font = "700 14px " + MONO;
        g.fillText(vt, x0 + panelW - g.measureText(vt).width, yMid + 4);
      });
    });
    if (comp.note) {
      g.fillStyle = sub; g.font = "12px " + MONO;
      g.fillText(fitTxt(g, String(comp.note), usableW), PAD, H - 76);
    }

    // footer: caption + url left, watermark right (house)
    if (spec.caption) {
      g.fillStyle = sub; g.font = "13px " + MONO;
      g.fillText(spec.caption, PAD, H - 52);
    }
    g.fillStyle = fg; g.font = "700 16px " + MONO;
    g.fillText(spec.url || "eephus.io", PAD, H - 26);
    g.fillStyle = sub; g.font = "700 13px " + MONO;
    var wm = "eephus.io";
    g.fillText(wm, W - PAD - g.measureText(wm).width, H - 26);
    return c;
  }

  // ---- render dispatch -------------------------------------------------------
  // Canvas text does NOT wait for a webfont. `g.font = "700 26px PixelMplus12"`
  // silently falls back to the next family in the stack if the face has not
  // loaded, and every face here is declared font-display:swap - so the FIRST
  // graphic generated in a session could rasterise in a different face than
  // every later one, with nothing in the console to say so. The DOM engine in
  // prospx awaits document.fonts before capture; this one never did.
  //
  // Since 2026-08-07 this matters on Windows too: PixelMplus12 leads
  // --font-logo, so a Windows visitor downloads it rather than matching a
  // system face, and a cold first export is the likeliest moment to miss it.
  //
  // Two specs, not one per size: document.fonts.load matches on family and
  // weight, never on the size the shorthand syntax forces you to supply.
  //
  // Resolves rather than rejects on failure: a missing webfont should degrade
  // to the fallback face, not block the export.
  var _fontsReady = null;
  function awaitFonts() {
    if (_fontsReady) return _fontsReady;
    if (!document.fonts || !document.fonts.load) {
      _fontsReady = Promise.resolve();
      return _fontsReady;
    }
    var specs = ["700 26px PixelMplus12", "400 26px PixelMplus12"];
    var jobs = specs.map(function (s) {
      try { return document.fonts.load(s).catch(function () {}); }
      catch (e) { return Promise.resolve(); }
    });
    if (document.fonts.ready) jobs.push(document.fonts.ready.catch(function () {}));
    // Never let a hung font request hold an export hostage.
    var timeout = new Promise(function (r) { setTimeout(r, 4000); });
    _fontsReady = Promise.race([Promise.all(jobs), timeout]);
    return _fontsReady;
  }

  async function renderCanvas() {
    await awaitFonts();
    var fmt = FORMATS[_opts.format] || FORMATS.wide;
    if (_spec.kind === "card") {
      // The unified card has its own 16:9-ish geometry; format control is hidden.
      var copts = Object.assign({}, _spec.card, { accentToken: accentToken() });
      return await window.EEPHUS_HUB.drawCard(copts);
    }
    if (_spec.kind === "newsday") {
      // Fixed-width, auto-height per-date digest; format control is hidden.
      return await renderNewsDay(_spec);
    }
    if (_spec.kind === "sourcecomp") {
      // Fixed Twitter-card geometry; format control is hidden.
      return renderSourceComp(_spec);
    }
    return renderBoard(_spec, fmt);
  }

  // ---- modal -----------------------------------------------------------------
  function ensureModal() {
    var ov = document.getElementById("egfx-overlay");
    if (ov) return ov;
    ov = document.createElement("div");
    ov.id = "egfx-overlay"; ov.className = "egfx-overlay";
    var fmtOpts = Object.keys(FORMATS).map(function (k) {
      return '<option value="' + k + '">' + esc(FORMATS[k].label) + "</option>";
    }).join("");
    var accSwatches = Object.keys(ACCENTS).map(function (k) {
      return '<button type="button" class="egfx-accent" data-egfx-accent="' + k +
        '" style="background:var(' + ACCENTS[k] + ')" title="' + k + ' accent"></button>';
    }).join("");
    ov.innerHTML =
      '<div class="egfx-modal" role="dialog" aria-modal="true" aria-label="Generate graphic">' +
        '<div class="egfx-head"><span class="egfx-title">Generate graphic</span>' +
          '<button class="egfx-x" type="button" aria-label="Close">&times;</button></div>' +
        '<div class="egfx-controls">' +
          '<label class="egfx-ctrl egfx-ctrl-format">Format<select id="egfx-format" class="egfx-select">' + fmtOpts + "</select></label>" +
          '<label class="egfx-ctrl">Theme<select id="egfx-theme" class="egfx-select">' +
            '<option value="auto">Auto (site)</option><option value="dark">Dark</option><option value="light">Light</option></select></label>' +
          '<label class="egfx-ctrl egfx-ctrl-count">Show<select id="egfx-count" class="egfx-select"></select></label>' +
          '<span class="egfx-ctrl egfx-ctrl-accent">Accent<span class="egfx-accents">' + accSwatches + "</span></span>" +
        "</div>" +
        '<div class="egfx-preview" id="egfx-preview"></div>' +
        '<div class="egfx-actions">' +
          '<button class="egfx-btn" id="egfx-share" type="button" hidden>Share</button>' +
          '<button class="egfx-btn egfx-btn-primary" id="egfx-download" type="button">Download PNG</button>' +
          '<button class="egfx-btn" id="egfx-copy" type="button">Copy</button>' +
        "</div>" +
      "</div>";
    document.body.appendChild(ov);
    ov.addEventListener("click", function (e) { if (e.target === ov) close(); });
    ov.querySelector(".egfx-x").onclick = close;
    ov.querySelector("#egfx-format").onchange = function (e) { _opts.format = e.target.value; refresh(); };
    ov.querySelector("#egfx-theme").onchange = function (e) { _opts.theme = e.target.value; applyTheme(); refresh(); };
    ov.querySelector("#egfx-count").onchange = function (e) {
      var v = e.target.value; _opts.count = (v === "all") ? "all" : Number(v); refresh();
    };
    ov.querySelectorAll("[data-egfx-accent]").forEach(function (b) {
      b.onclick = function () { _opts.accent = b.dataset.egfxAccent; syncControls(); refresh(); };
    });
    ov.querySelector("#egfx-download").onclick = function () { exportNow("download"); };
    ov.querySelector("#egfx-copy").onclick = function () { exportNow("copy"); };
    ov.querySelector("#egfx-share").onclick = function () { exportNow("share"); };
    document.addEventListener("keydown", function (e) {
      if (!ov.classList.contains("is-open")) return;
      if (e.key === "Escape") { close(); return; }
      if (e.key === "Tab") {
        var modal = ov.querySelector(".egfx-modal");
        if (!modal) return;
        var focusable = Array.prototype.filter.call(
          modal.querySelectorAll('button, [href], select, input, textarea, [tabindex]:not([tabindex="-1"])'),
          function (el) { return !el.disabled && !el.hidden && el.offsetParent !== null; }
        );
        if (!focusable.length) return;
        var first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
    return ov;
  }

  function applyTheme() { forceTheme(_opts.theme, _origTheme); }

  function syncControls() {
    var ov = document.getElementById("egfx-overlay");
    if (!ov) return;
    // card, newsday AND sourcecomp own their geometry (newsday: fixed 1200w,
    // auto height, every item always drawn; sourcecomp: fixed Twitter card) -
    // Format + Show only apply to boards. Theme + Accent stay live for all.
    var noBoard = _spec.kind === "card" || _spec.kind === "newsday" || _spec.kind === "sourcecomp";
    ov.querySelector(".egfx-ctrl-format").style.display = noBoard ? "none" : "";
    ov.querySelector(".egfx-ctrl-count").style.display = noBoard ? "none" : "";
    ov.querySelector("#egfx-format").value = _opts.format;
    ov.querySelector("#egfx-theme").value = _opts.theme;
    var counts = (_spec.board && _spec.board.counts) || [10, 25, 50];
    var csel = ov.querySelector("#egfx-count");
    csel.innerHTML = counts.map(function (n) { return '<option value="' + n + '">Top ' + n + "</option>"; }).join("") +
      '<option value="all">All</option>';
    csel.value = String(_opts.count);
    ov.querySelectorAll("[data-egfx-accent]").forEach(function (b) {
      var on = b.dataset.egfxAccent === (_opts.accent || _specAccentKey());
      b.classList.toggle("is-active", on);
    });
    var sh = ov.querySelector("#egfx-share");
    sh.hidden = !(typeof navigator !== "undefined" && typeof navigator.canShare === "function");
  }
  function _specAccentKey() {
    var t = (_spec && _spec.accentToken) || "";
    for (var k in ACCENTS) { if (ACCENTS[k] === t) return k; }
    return "lilac";
  }

  async function refresh() {
    var prev = document.getElementById("egfx-preview");
    if (!prev) return;
    // AUDIT 2026-07-18 (A12): coalesce instead of dropping. A control change made
    // while a render is in flight used to be discarded (early return on _busy),
    // leaving _canvas -- what export/copy/share uses -- stale vs the selected
    // options. Now the in-flight render re-runs with the latest _opts before it
    // paints, so the preview and the exported PNG always match the controls.
    if (_busy) { _renderPending = true; return; }
    _busy = true;
    prev.classList.add("is-busy");
    try {
      do {
        _renderPending = false;
        _canvas = await renderCanvas();
      } while (_renderPending);
      prev.innerHTML = "";
      var img = _canvas; // a canvas element scales fine inside the preview
      img.className = "egfx-canvas";
      prev.appendChild(img);
    } catch (e) {
      prev.innerHTML = '<div class="egfx-err">Could not render this graphic.</div>';
    } finally {
      prev.classList.remove("is-busy");
      _busy = false;
      if (_renderPending) refresh();
    }
  }

  async function exportNow(action) {
    if (!_canvas || !window.EEPHUS_HUB) return;
    var base = (_spec.filenameBase || "eephus-graphic");
    var fname = base + (_spec.kind === "board" ? "-" + _opts.format : "") + ".png";
    var res = await window.EEPHUS_HUB.exportCanvas(_canvas, {
      action: action, filename: fname, shareTitle: _spec.title || "eephus.io",
    });
    if (action === "copy") flash(res === "copied" ? "Copied to clipboard" : "Downloaded (copy unsupported)");
    else if (action === "share") flash(res === "shared" ? "Shared" : "Downloaded (share unsupported)");
    else flash("Downloaded");
  }
  var _flashTimer = null;
  function flash(msg) {
    var ov = document.getElementById("egfx-overlay");
    if (!ov) return;
    var t = ov.querySelector(".egfx-flash") || (function () {
      var d = document.createElement("div"); d.className = "egfx-flash";
      ov.querySelector(".egfx-modal").appendChild(d);
      // one style flush at opacity 0 so the first flash eases in too
      void d.offsetWidth;
      return d;
    })();
    t.textContent = msg; t.classList.add("is-show");
    // Keep the handle: a second flash inside 1.6 s restarts the hide timer
    // instead of being hidden early by the first one (audit A15).
    clearTimeout(_flashTimer);
    _flashTimer = setTimeout(function () { t.classList.remove("is-show"); }, 1600);
  }

  function open(spec) {
    if (!spec || !window.EEPHUS_HUB) return;
    _lastFocus = document.activeElement;
    _spec = spec;
    // A spec may name its own starting format (e.g. the /news/ digest defaults
    // to the Twitter card); unknown names fall back to wide as before.
    _opts.format = (spec.format && FORMATS[spec.format]) ? spec.format : "wide";
    _opts.accent = null;            // default to the module's own accent
    var _cs = (spec.board && spec.board.counts) || [10, 25, 50];
    var _dc = (spec.board && spec.board.defaultCount);
    _opts.count = (_cs.indexOf(_dc) >= 0) ? _dc : (_cs.length ? _cs[0] : 25);
    _origTheme = document.documentElement.getAttribute("data-theme");
    var ov = ensureModal();
    ov.classList.add("is-open");
    applyTheme();
    syncControls();
    refresh();
    var x = ov.querySelector(".egfx-x");
    if (x) x.focus();
  }
  function close() {
    var ov = document.getElementById("egfx-overlay");
    if (ov) ov.classList.remove("is-open");
    forceTheme(null, _origTheme);
    _canvas = null;
    if (_lastFocus && _lastFocus.focus) _lastFocus.focus();
    _lastFocus = null;
  }

  function chipHTML(id, label) {
    return '<button class="chip egfx-chip" id="' + esc(id) + '" type="button" ' +
      'title="Generate a shareable graphic (theme-aware, multiple formats)">' +
      '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>' + esc(label || "Generate GFX") + "</button>";
  }

  window.EEPHUS_GFX = { open: open, close: close, chipHTML: chipHTML, FORMATS: FORMATS,
    ACCENTS: ACCENTS, tok: tok, palette: palette, forceTheme: forceTheme, SCALE: SCALE };
})();
