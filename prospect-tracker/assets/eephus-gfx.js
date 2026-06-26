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
//
//   EEPHUS_GFX.open(spec)   spec = {
//     kind:"board"|"card", module, accentToken?, title, subtitle?, url,
//     filenameBase, caption?,
//     board?: { columns:[{label, frac, align?, wideOnly?}],
//               rows:[{ cells:[{ t, sub?, c? }] }], counts?:[10,25,50] },
//     card?:  <EEPHUS_HUB.drawCard opts> }
//   EEPHUS_GFX.chipHTML(id, label?)   a ready "Generate GFX" chip button
(function () {
  "use strict";

  var FORMATS = {
    wide:     { w: 1600, h: 900,  label: "Wide 16:9" },
    portrait: { w: 1080, h: 1350, label: "Portrait 4:5" },
    square:   { w: 1080, h: 1080, label: "Square 1:1" },
    story:    { w: 1080, h: 1920, label: "Story 9:16" },
  };
  // Accent swatches -> safe, theme-aware tokens (defined in site.css :root).
  var ACCENTS = {
    cyan:  "--accent-cyan", green: "--accent-green", gold: "--accent-gold",
    navy:  "--accent-navy", red:   "--accent-red",
  };
  var COLOR_KEYS = { pos: "green", neg: "red", accent: "accent", muted: "sub" };

  var _spec = null;
  var _opts = { format: "wide", theme: "auto", accent: null, count: 25 };
  var _origTheme = null;
  var _canvas = null;
  var _busy = false;

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
    return (_spec && _spec.accentToken) || "--accent-cyan";
  }

  // ---- canvas board renderer -------------------------------------------------
  function renderBoard(spec, fmt) {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    var W = fmt.w, H = fmt.h;
    var PAD = Math.round(W * 0.033);
    var c = document.createElement("canvas");
    c.width = W; c.height = H;
    var g = c.getContext("2d");
    var bg = tok("--bg-primary", dark ? "#101014" : "#F6F1E4");
    var fg = tok("--text-primary", dark ? "#ECEEF2" : "#0F1B2D");
    var sub = tok("--text-tertiary", dark ? "#7C808A" : "#706B5C");
    var line = tok("--border", dark ? "#2B2B31" : "#C9C1AE");
    var accent = tok(accentToken(), dark ? "#00D9FF" : "#0E7C86");
    var pos = dark ? "#4FFF9E" : "#1F7A3A", neg = dark ? "#FF6B6B" : "#B91C1C";
    var MONO = '"DotGothic16","MS Gothic","MS UI Gothic","Osaka-Mono",monospace';
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
    (dark
      ? [[0, "#00D9FF"], [0.3, "#B47CFF"], [0.55, "#FF4FD8"], [0.78, "#FFD700"], [1, "#4FFF9E"]]
      : [[0, "#B91C1C"], [0.35, "#C9A227"], [0.65, "#1F7A3A"], [1, "#0E2B4D"]]
    ).forEach(function (s) { ramp.addColorStop(s[0], s[1]); });
    g.fillStyle = ramp; g.fillRect(PAD, 66, W - 2 * PAD, 3);

    // title + subtitle
    g.fillStyle = fg; g.font = "700 34px " + MONO;
    g.fillText(spec.title || "", PAD, 108);
    if (spec.subtitle) {
      g.fillStyle = sub; g.font = "15px " + MONO;
      g.fillText(spec.subtitle, PAD, 134);
    }

    // columns: drop wide-only columns on narrow canvases
    var board = spec.board || {};
    var cols = (board.columns || []).filter(function (col) { return !(col.wideOnly && W < 1300); });
    var usableW = W - 2 * PAD;
    var totFrac = cols.reduce(function (a, col) { return a + (col.frac || 0); }, 0) || 1;
    var x0 = [], acc = 0;
    cols.forEach(function (col) { x0.push(PAD + (acc / totFrac) * usableW); acc += (col.frac || 0); });

    var headY = 168;
    g.font = "700 14px " + MONO;
    cols.forEach(function (col, i) {
      g.fillStyle = sub;
      g.fillText(String(col.label || "").toUpperCase(), x0[i], headY);
    });
    g.strokeStyle = line; g.lineWidth = 1;
    g.beginPath(); g.moveTo(PAD, headY + 10); g.lineTo(W - PAD, headY + 10); g.stroke();

    // rows: fit by height, capped by the Show count
    var rowsAll = board.rows || [];
    var rowH = 40;
    var topY = headY + 38;
    var footH = 96;
    var fit = Math.max(1, Math.floor((H - topY - footH) / rowH));
    var cap = (_opts.count === "all") ? rowsAll.length : Math.min(rowsAll.length, _opts.count);
    var n = Math.min(cap, fit);
    for (var r = 0; r < n; r++) {
      var row = rowsAll[r] || {};
      var cells = row.cells || [];
      var y = topY + r * rowH + 18;
      for (var i = 0; i < cols.length; i++) {
        var cell = cells[i] || {};
        var t = cell.t == null ? "" : String(cell.t);
        if (cell.sub) {
          g.fillStyle = fg; g.font = "700 17px " + MONO;
          g.fillText(t, x0[i], y);
          var nameW = g.measureText(t).width;
          g.fillStyle = sub; g.font = "12px " + MONO;
          g.fillText(String(cell.sub), x0[i] + nameW + 9, y);
        } else {
          g.fillStyle = cell.c ? colorOf(cell.c) : fg;
          g.font = (cell.c === "accent" || cell.bold ? "700 " : "") + "16px " + MONO;
          g.fillText(t, x0[i], y);
        }
      }
      if (r < n - 1) {
        g.strokeStyle = line; g.globalAlpha = 0.5;
        g.beginPath(); g.moveTo(PAD, y + 13); g.lineTo(W - PAD, y + 13); g.stroke();
        g.globalAlpha = 1;
      }
    }

    // footer: caption + url left, watermark right
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

  // ---- render dispatch -------------------------------------------------------
  async function renderCanvas() {
    var fmt = FORMATS[_opts.format] || FORMATS.wide;
    if (_spec.kind === "card") {
      // The unified card has its own 16:9-ish geometry; format control is hidden.
      var copts = Object.assign({}, _spec.card, { accentToken: accentToken() });
      return await window.EEPHUS_HUB.drawCard(copts);
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
      '<div class="egfx-modal" role="dialog" aria-label="Generate graphic">' +
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
      if (e.key === "Escape" && ov.classList.contains("is-open")) close();
    });
    return ov;
  }

  function applyTheme() {
    var root = document.documentElement;
    if (_opts.theme === "light" || _opts.theme === "dark") root.setAttribute("data-theme", _opts.theme);
    else if (_origTheme != null) root.setAttribute("data-theme", _origTheme);
    else root.removeAttribute("data-theme");
  }

  function syncControls() {
    var ov = document.getElementById("egfx-overlay");
    if (!ov) return;
    var isCard = _spec.kind === "card";
    ov.querySelector(".egfx-ctrl-format").style.display = isCard ? "none" : "";
    ov.querySelector(".egfx-ctrl-count").style.display = isCard ? "none" : "";
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
    return "cyan";
  }

  async function refresh() {
    var prev = document.getElementById("egfx-preview");
    if (!prev || _busy) return;
    _busy = true;
    prev.classList.add("is-busy");
    try {
      _canvas = await renderCanvas();
      prev.innerHTML = "";
      var img = _canvas; // a canvas element scales fine inside the preview
      img.className = "egfx-canvas";
      prev.appendChild(img);
    } catch (e) {
      prev.innerHTML = '<div class="egfx-err">Could not render this graphic.</div>';
    } finally {
      prev.classList.remove("is-busy");
      _busy = false;
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
  }
  function flash(msg) {
    var ov = document.getElementById("egfx-overlay");
    if (!ov) return;
    var t = ov.querySelector(".egfx-flash") || (function () {
      var d = document.createElement("div"); d.className = "egfx-flash";
      ov.querySelector(".egfx-modal").appendChild(d); return d;
    })();
    t.textContent = msg; t.classList.add("is-show");
    setTimeout(function () { t.classList.remove("is-show"); }, 1600);
  }

  function open(spec) {
    if (!spec || !window.EEPHUS_HUB) return;
    _spec = spec;
    _opts.format = "wide";
    _opts.accent = null;            // default to the module's own accent
    _opts.count = (spec.board && spec.board.defaultCount) || 25;
    _origTheme = document.documentElement.getAttribute("data-theme");
    var ov = ensureModal();
    ov.classList.add("is-open");
    applyTheme();
    syncControls();
    refresh();
  }
  function close() {
    var ov = document.getElementById("egfx-overlay");
    if (ov) ov.classList.remove("is-open");
    if (_origTheme != null) document.documentElement.setAttribute("data-theme", _origTheme);
    else document.documentElement.removeAttribute("data-theme");
    _canvas = null;
  }

  function chipHTML(id, label) {
    return '<button class="chip egfx-chip" id="' + esc(id) + '" type="button" ' +
      'title="Generate a shareable graphic (theme-aware, multiple formats)">' +
      '<span class="egfx-chip-glyph" aria-hidden="true">&#9636;</span>' + esc(label || "Generate GFX") + "</button>";
  }

  window.EEPHUS_GFX = { open: open, close: close, chipHTML: chipHTML, FORMATS: FORMATS };
})();
