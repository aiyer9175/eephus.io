// eephus.io - universal copy + export for tables and charts (shared component).
// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
//
// One centralized affordance + utility, wired in once and applied everywhere: a
// quiet chip on every table and chart that opens a short menu of share formats.
// Text copy is instant (no server). Image export reuses EEPHUS_HUB.exportCanvas
// (ClipboardItem image-copy / Web Share / download) + the vendored html2canvas.
//
// The faithful-view trick: we SCRAPE the rendered DOM. The cells already carry
// the exact number formatting (decimals, %, plus-stat signs, ranges) AND reflect
// the user's current sorted + filtered view, so a scrape needs no per-table
// wiring and can never drift from what's on screen.
//
// Public API (window.EephusExport):
//   scan(root?)            attach the chip to exportable tables/charts under root
//   attach(el, opts?)      attach the chip to one element
//   copyTable(el, fmt)     copy a table element in a format (md|mono|csv|tsv|bbcode|rich)
//   formats                the text serializers (pure, testable)
(function () {
  "use strict";
  if (window.EephusExport) return;

  var SITE = "eephus.io";

  // ---- small DOM helpers ---------------------------------------------------
  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  function txt(node) {
    // Visible text of a cell, whitespace-collapsed. Honors data-export-skip
    // (drop the cell) and data-export-text (override the scraped text, e.g. a
    // cell whose visible glyph isn't copy-friendly).
    if (!node) return "";
    if (node.getAttribute && node.getAttribute("data-export-skip") != null) return null;
    if (node.getAttribute && node.getAttribute("data-export-text") != null)
      return node.getAttribute("data-export-text");
    var t = (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
    return t;
  }

  // ---- scrape a table / grid into {title, headers, rows, aligns} -----------
  function scrape(host) {
    var table = host.matches && host.matches("table") ? host
              : (host.querySelector ? host.querySelector("table") : null);
    if (table) return scrapeTable(table, host);
    return scrapeGrid(host);
  }

  function _headerCells(table) {
    var thead = table.querySelector("thead");
    if (thead) {
      var hr = thead.querySelectorAll("tr");
      // use the LAST header row (handles grouped headers)
      if (hr.length) return Array.prototype.slice.call(hr[hr.length - 1].children);
    }
    var first = table.querySelector("tr");
    if (first && first.querySelector("th")) return Array.prototype.slice.call(first.children);
    return [];
  }

  function scrapeTable(table, host) {
    var hcells = _headerCells(table);
    var headers = [], aligns = [];
    hcells.forEach(function (c) {
      var t = txt(c);
      if (t === null) return;            // skipped column header
      headers.push(t || "");
      aligns.push(_align(c));
    });
    var bodyRows = [];
    var tbody = table.querySelector("tbody");
    var trs = tbody ? tbody.querySelectorAll("tr")
                    : table.querySelectorAll("tr");
    Array.prototype.forEach.call(trs, function (tr) {
      if (tr.querySelector("th") && !tr.querySelector("td")) return;  // header-only row
      if (tr.getAttribute("data-export-skip") != null) return;
      var cells = [];
      Array.prototype.forEach.call(tr.children, function (c, i) {
        var t = txt(c);
        if (t === null) return;          // skipped cell/column
        cells.push(t);
      });
      if (cells.length && cells.some(function (x) { return x !== ""; })) bodyRows.push(cells);
    });
    return _finish(headers, aligns, bodyRows, host || table);
  }

  // Best-effort scrape of a prospx-style CSS-grid "table" (a header row of
  // .col-header cells + .player-row rows). Cells are direct children; complex
  // cells (headshot/badges) collapse to their text. Callers can mark cells with
  // data-export-skip / data-export-text to clean it up.
  function scrapeGrid(host) {
    var header = host.querySelector(".col-header, [data-export-header]");
    var headers = [], aligns = [];
    if (header) {
      Array.prototype.forEach.call(header.children, function (c) {
        var t = txt(c); if (t === null) return;
        headers.push(t || ""); aligns.push(_align(c));
      });
    }
    var rowSel = host.getAttribute("data-export-rows") || ".player-row, .debut-row, .spotlight-row, .farm-row";
    var rows = host.querySelectorAll(rowSel);
    var bodyRows = [];
    Array.prototype.forEach.call(rows, function (r) {
      if (r.getAttribute("data-export-skip") != null) return;
      var cells = [];
      Array.prototype.forEach.call(r.children, function (c) {
        var t = txt(c); if (t === null) return;
        cells.push(t);
      });
      if (cells.length && cells.some(function (x) { return x !== ""; })) bodyRows.push(cells);
    });
    return _finish(headers, aligns, bodyRows, host);
  }

  function _align(cell) {
    try {
      var ta = (getComputedStyle(cell).textAlign || "").toLowerCase();
      if (ta === "right" || ta === "end") return "right";
      if (ta === "center") return "center";
    } catch (e) {}
    return "left";
  }
  function _isNum(s) { return /^[+\-(]?\$?\d[\d,]*\.?\d*%?\)?$/.test(String(s).trim()); }

  function _finish(headers, aligns, rows, host) {
    // normalize row widths to the header width (or the widest row)
    var w = headers.length || rows.reduce(function (m, r) { return Math.max(m, r.length); }, 0);
    if (!headers.length) { headers = []; for (var i = 0; i < w; i++) headers.push(""); }
    rows = rows.map(function (r) {
      var c = r.slice(0, w);
      while (c.length < w) c.push("");
      return c;
    });
    // infer right-alignment for columns that look numeric if CSS didn't say
    if (aligns.length < w) { while (aligns.length < w) aligns.push("left"); }
    for (var col = 0; col < w; col++) {
      if (aligns[col] === "left") {
        var nums = 0, tot = 0;
        rows.forEach(function (r) { if (r[col] !== "") { tot++; if (_isNum(r[col])) nums++; } });
        if (tot && nums / tot >= 0.7) aligns[col] = "right";
      }
    }
    // Drop anonymous empty columns (logo/headshot/icon-only cells with no text)
    // so a scrape of a rich grid reads clean.
    var keep = [];
    for (var k = 0; k < w; k++) {
      var emptyHead = (headers[k] || "") === "";
      var emptyAll = rows.every(function (r) { return (r[k] || "") === ""; });
      if (!(emptyHead && emptyAll)) keep.push(k);
    }
    if (keep.length && keep.length < w) {
      headers = keep.map(function (i) { return headers[i]; });
      aligns = keep.map(function (i) { return aligns[i]; });
      rows = rows.map(function (r) { return keep.map(function (i) { return r[i]; }); });
    }
    return { title: _title(host), headers: headers, rows: rows, aligns: aligns };
  }

  function _title(host) {
    var t = host && host.getAttribute && host.getAttribute("data-export-title");
    if (t) return t;
    // walk up for a nearby heading / caption
    var node = host, hops = 0;
    while (node && hops++ < 4) {
      var cap = node.querySelector && node.querySelector("caption, .section-eyebrow, .newsprint-eyebrow, .tt-title, h1, h2, h3");
      if (cap && (cap.innerText || cap.textContent)) return (cap.innerText || cap.textContent).replace(/\s+/g, " ").trim();
      node = node.parentElement;
    }
    return "";
  }

  // ---- text serializers (pure) --------------------------------------------
  function _esc(s) { return String(s == null ? "" : s); }
  function _displayW(s) { return _esc(s).length; }

  var formats = {
    csv: function (m) { return _delim(m, ","); },
    tsv: function (m) { return _delim(m, "\t"); },

    markdown: function (m) {
      var lines = [];
      lines.push("| " + m.headers.map(_mdCell).join(" | ") + " |");
      lines.push("| " + m.aligns.map(function (a) {
        return a === "right" ? "---:" : a === "center" ? ":---:" : "---";
      }).join(" | ") + " |");
      m.rows.forEach(function (r) { lines.push("| " + r.map(_mdCell).join(" | ") + " |"); });
      return lines.join("\n");
    },

    monospace: function (m, opts) {
      opts = opts || {};
      var W = m.headers.map(function (h, i) {
        var w = _displayW(h);
        m.rows.forEach(function (r) { w = Math.max(w, _displayW(r[i])); });
        return w;
      });
      function pad(s, i) {
        s = _esc(s); var gap = W[i] - s.length; if (gap < 0) gap = 0;
        return m.aligns[i] === "right" ? (new Array(gap + 1).join(" ") + s)
             : m.aligns[i] === "center" ? (new Array(((gap / 2) | 0) + 1).join(" ") + s + new Array(gap - ((gap / 2) | 0) + 1).join(" "))
             : (s + new Array(gap + 1).join(" "));
      }
      var out = [];
      out.push(m.headers.map(pad).join("  "));
      out.push(W.map(function (w) { return new Array(w + 1).join("-"); }).join("  "));
      m.rows.forEach(function (r) { out.push(r.map(pad).join("  ")); });
      var body = out.join("\n");
      return opts.fence === false ? body : "```\n" + body + "\n```";
    },

    bbcode: function (m) {
      var out = ["[table]"];
      out.push("[tr]" + m.headers.map(function (h) { return "[th]" + _esc(h) + "[/th]"; }).join("") + "[/tr]");
      m.rows.forEach(function (r) {
        out.push("[tr]" + r.map(function (c) { return "[td]" + _esc(c) + "[/td]"; }).join("") + "[/tr]");
      });
      out.push("[/table]");
      return out.join("\n");
    },

    html: function (m) {
      function row(cells, tag) {
        return "<tr>" + cells.map(function (c, i) {
          var al = m.aligns[i] === "right" ? " align=\"right\"" : m.aligns[i] === "center" ? " align=\"center\"" : "";
          return "<" + tag + al + ">" + _htmlesc(c) + "</" + tag + ">";
        }).join("") + "</tr>";
      }
      return '<table border="1" cellspacing="0" cellpadding="4" style="border-collapse:collapse;font-family:monospace;">'
        + "<thead>" + row(m.headers, "th") + "</thead><tbody>"
        + m.rows.map(function (r) { return row(r, "td"); }).join("") + "</tbody></table>";
    },
  };
  function _mdCell(s) { return _esc(s).replace(/\|/g, "\\|").replace(/\n/g, " "); }
  function _htmlesc(s) { return _esc(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function _delim(m, sep) {
    function cell(s) {
      s = _esc(s);
      if (sep === ",") { return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
      return s.replace(/\t/g, " ").replace(/\n/g, " ");   // TSV: no embedded tabs/newlines
    }
    var out = [m.headers.map(cell).join(sep)];
    m.rows.forEach(function (r) { out.push(r.map(cell).join(sep)); });
    return out.join("\n");
  }

  // ---- clipboard -----------------------------------------------------------
  function copyText(text, html) {
    if (navigator.clipboard && window.ClipboardItem && html) {
      try {
        var item = new ClipboardItem({
          "text/plain": new Blob([text], { type: "text/plain" }),
          "text/html": new Blob([html], { type: "text/html" }),
        });
        return navigator.clipboard.write([item]).catch(function () { return _copyPlain(text); });
      } catch (e) { return _copyPlain(text); }
    }
    return _copyPlain(text);
  }
  function _copyPlain(text) {
    if (navigator.clipboard && navigator.clipboard.writeText)
      return navigator.clipboard.writeText(text).catch(_legacyCopy.bind(null, text));
    return _legacyCopy(text);
  }
  function _legacyCopy(text) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.left = "-9999px";
      document.body.appendChild(ta); ta.select(); document.execCommand("copy");
      document.body.removeChild(ta);
      return Promise.resolve();
    } catch (e) { return Promise.reject(e); }
  }

  // ---- toast feedback ------------------------------------------------------
  var _toastTimer = null;
  function toast(msg) {
    var t = document.getElementById("eephus-export-toast");
    if (!t) {
      t = el("div", "eephus-export-toast"); t.id = "eephus-export-toast"; document.body.appendChild(t);
      // A new toast needs one style flush at opacity 0 before is-on, or the
      // first toast of a page skips its .15 s ease in (audit A07).
      void t.offsetWidth;
    }
    t.textContent = msg;
    t.classList.add("is-on");
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(function () { t.classList.remove("is-on"); }, 1900);
  }

  // ---- the menu ------------------------------------------------------------
  var TEXT_ITEMS = [
    { fmt: "markdown",  label: "Markdown table",   note: "Reddit / GitHub" },
    { fmt: "monospace", label: "Monospace (code)", note: "Discord / universal" },
    { fmt: "csv",       label: "CSV",              note: "spreadsheets" },
    { fmt: "tsv",       label: "TSV",              note: "Excel / Sheets" },
    { fmt: "rich",      label: "Rich text",        note: "Docs / email" },
    { fmt: "bbcode",    label: "BBCode",           note: "legacy forums" },
  ];

  function buildText(model, fmt) {
    if (fmt === "rich") return { text: formats.monospace(model, { fence: false }), html: formats.html(model), label: "Rich text" };
    var item = TEXT_ITEMS.filter(function (x) { return x.fmt === fmt; })[0];
    var map = { markdown: "markdown", monospace: "monospace", csv: "csv", tsv: "tsv", bbcode: "bbcode" };
    return { text: formats[map[fmt]](model), html: null, label: item ? item.label : fmt };
  }

  function openMenu(chip, host, kind) {
    closeMenu();
    var menu = el("div", "eephus-export-menu");
    menu.setAttribute("role", "menu");
    var head = el("div", "ex-menu-head", kind === "chart" ? "Export chart" : "Copy table");
    menu.appendChild(head);

    if (kind !== "chart") {
      TEXT_ITEMS.forEach(function (it) {
        var b = el("button", "ex-menu-item", '<span>' + it.label + '</span><small>' + it.note + '</small>');
        b.type = "button";
        b.setAttribute("role", "menuitem");
        b.addEventListener("click", function () {
          var model = scrape(host);
          var built = buildText(model, it.fmt);
          copyText(built.text, built.html).then(function () { toast("Copied as " + built.label); })
            .catch(function () { toast("Copy failed"); });
          closeMenu();
        });
        menu.appendChild(b);
      });
    }

    // image / chart actions - always available (html2canvas lazy-loads on demand)
    {
      menu.appendChild(el("div", "ex-menu-sep"));
      var imgActions = [
        { action: "copy", label: "Copy image", note: "paste into X / Discord" },
        { action: "download", label: "Download image", note: "PNG" },
      ];
      if (navigator.canShare) imgActions.splice(1, 0, { action: "share", label: "Share…", note: "system share sheet" });
      if (kind === "chart") imgActions.push({ action: "svg", label: "Download SVG", note: "vector" });
      imgActions.forEach(function (a) {
        var b = el("button", "ex-menu-item", '<span>' + a.label + '</span><small>' + a.note + '</small>');
        b.type = "button";
        b.setAttribute("role", "menuitem");
        b.addEventListener("click", function () {
          closeMenu();
          if (a.action === "svg") return exportChartSVG(host);
          exportImage(host, a.action, kind).catch(function () { toast("Image export failed"); });
        });
        menu.appendChild(b);
      });
    }

    document.body.appendChild(menu);
    var r = chip.getBoundingClientRect();
    var mw = menu.offsetWidth, mh = menu.offsetHeight;
    var left = Math.min(r.right - mw, window.innerWidth - mw - 8);
    var top = r.bottom + 6;
    if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 6);
    menu.style.left = Math.max(8, left) + "px";
    menu.style.top = top + "px";
    setTimeout(function () { document.addEventListener("click", _onDocClick, true); }, 0);
    document.addEventListener("keydown", _onKey, true);
    window.addEventListener("scroll", closeMenu, true);
    window.addEventListener("resize", closeMenu);
    EephusExport._menu = menu;
  }
  function _onDocClick(e) {
    if (EephusExport._menu && !EephusExport._menu.contains(e.target) && !e.target.closest(".eephus-export-chip")) closeMenu();
  }
  function _onKey(e) {
    if (e.key === "Escape") closeMenu();
  }
  function closeMenu() {
    if (EephusExport._menu && EephusExport._menu.parentNode) EephusExport._menu.parentNode.removeChild(EephusExport._menu);
    EephusExport._menu = null;
    document.removeEventListener("click", _onDocClick, true);
    document.removeEventListener("keydown", _onKey, true);
    window.removeEventListener("scroll", closeMenu, true);
    window.removeEventListener("resize", closeMenu);
  }

  // ---- image export (branded frame, self-contained) ------------------------
  function _dark() { return document.documentElement.getAttribute("data-theme") === "dark"; }
  // ONE URL for the vendored html2canvas, the same string PROSPX's own loader
  // uses, so a reader who exports on two surfaces downloads it once. The stamp
  // is the file's content hash (md5 of its LF bytes, first 8 hex);
  // test_html2canvas_one_url.py pins both loaders to it.
  var H2C_URL = "/vendor/html2canvas.min.js?v=d7530aa0";
  function _ensureH2C() {
    if (window.html2canvas) return Promise.resolve(window.html2canvas);
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = H2C_URL;
      s.onload = function () { resolve(window.html2canvas); };
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  // canvas -> clipboard-image / Web Share / download (self-contained, mirrors
  // EEPHUS_HUB.exportCanvas so this works on every surface incl. prospx).
  function _dispatchCanvas(canvas, action, filename, shareTitle) {
    return new Promise(function (resolve) {
      canvas.toBlob(function (blob) {
        if (!blob) { toast("Image export failed"); resolve(); return; }
        (async function () {
          try {
            if (action === "copy" && navigator.clipboard && window.ClipboardItem) {
              await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
              toast("Image copied"); resolve(); return;
            }
            if (action === "share" && navigator.canShare) {
              var file = new File([blob], filename || "eephus.png", { type: "image/png" });
              if (navigator.canShare({ files: [file] })) {
                await navigator.share({ files: [file], title: shareTitle || SITE });
                resolve(); return;
              }
            }
          } catch (e) { /* fall through to download */ }
          var a = document.createElement("a");
          a.download = filename || "eephus.png";
          a.href = URL.createObjectURL(blob);
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
          setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
          toast("Image downloaded"); resolve();
        })();
      }, "image/png");
    });
  }
  var RAMP_L = ["#B91C1C", "#C9A227", "#1F7A3A", "#0E2B4D"];
  var RAMP_D = ["#00D9FF", "#B47CFF", "#FF4FD8", "#FFD700", "#4FFF9E"];
  function _rampRule(g, x, y, w, h, dark) {
    var stops = dark ? RAMP_D : RAMP_L;
    var grad = g.createLinearGradient(x, 0, x + w, 0);
    stops.forEach(function (c, i) { grad.addColorStop(i / (stops.length - 1), c); });
    g.fillStyle = grad; g.fillRect(x, y, w, h);
  }
  // A canvas 2d context cannot resolve var(--font-logo), so the logo stack is
  // repeated here as a literal and MUST be kept in step with the
  // --font-logo token in assets/site.css.
  // test_board_card_typography.py fails the build if it drifts. One constant
  // for all three draws below: they used to be three separate literals, which is
  // exactly how _GFX_SVG_MONO in prospx drifted out of step unnoticed.
  var _LOGO = '"PixelMplus12", "MS Gothic", monospace';

  // Canvas text never waits for a webfont, and neither does html2canvas: an
  // unloaded face falls silently through to the next family, so a cold first
  // export rasterises in a different letterform than every export after it.
  // Since 2026-08-07 that is a Windows risk too, not just an Apple one -
  // PixelMplus12 leads --font-logo, so every platform now downloads it instead
  // of matching a system face. This module ships site-wide while EEPHUS_HUB does
  // not, so it cannot borrow the hub's copy of this.
  // Resolves on failure - a missing webfont should degrade, not block an export.
  // Two specs cover the surface: fonts.load matches family and weight, never the
  // size its shorthand syntax forces you to supply.
  var _fontsReady = null;
  function _awaitFonts() {
    if (_fontsReady) return _fontsReady;
    if (!document.fonts || !document.fonts.load) {
      _fontsReady = Promise.resolve();
      return _fontsReady;
    }
    var jobs = ["700 26px PixelMplus12", "400 26px PixelMplus12"].map(function (s) {
      try { return document.fonts.load(s).catch(function () {}); }
      catch (e) { return Promise.resolve(); }
    });
    if (document.fonts.ready) jobs.push(document.fonts.ready.catch(function () {}));
    // Never let a hung font request hold an export hostage.
    var timeout = new Promise(function (r) { setTimeout(r, 4000); });
    _fontsReady = Promise.race([Promise.all(jobs), timeout]);
    return _fontsReady;
  }

  // Wrap a rasterized content canvas in the branded frame (wordmark + title +
  // ramp rule + url), the newspaper/share-card language.
  function _brandCompose(content, title, dark) {
    var S = 2;                                   // matches html2canvas scale
    var pad = 26 * S, headH = 56 * S, footH = 40 * S;
    var W = content.width + pad * 2;
    var H = content.height + pad + headH + footH;
    var c = document.createElement("canvas"); c.width = W; c.height = H;
    var g = c.getContext("2d");
    g.fillStyle = dark ? "#0C0C0E" : "#F4F0E6"; g.fillRect(0, 0, W, H);
    // wordmark: under PIXEL_BRAND the pixel lockup (letters 2 px per font pixel
    // in frame units, the s 4 strike at 1:1 on the 2x canvas), top at the pad,
    // with the title on its baseline; otherwise the text wordmark. The .io is
    // lilac in both themes under the flag (owner answer PB-Q3).
    var fs = 30 * S;
    var pb = pixelBrand();
    var lk = pb ? pxLockup(g, pad, pad, 2 * S, 1, dark) : null;
    var by = lk ? pad + lk.base : pad + fs;
    g.textBaseline = "alphabetic";
    g.font = "700 " + fs + "px " + _LOGO;
    if (!lk) {
      g.fillStyle = dark ? "#ECEEF2" : "#0F1B2D";
      g.fillText("eephus", pad, by);
      var ew = g.measureText("eephus").width;
      g.fillStyle = dark ? "#9B8CFF" : (pb ? "#6E56CF" : "#C9A227");
      g.fillText(".io", pad + ew, by);
    }
    // title (right-aligned), the module icon at 12 px left of it (PX-18)
    if (title) {
      g.font = "700 " + (15 * S) + "px " + _LOGO;
      var tc = dark ? "#A6ABB5" : "#4A5468";
      g.fillStyle = tc;
      var tt = _clip(title, 64);
      g.textAlign = "right";
      g.fillText(tt, W - pad, by - 3 * S);
      g.textAlign = "left";
      var ik = routeIcon();
      if (ik) pxIcon(g, ik, W - pad - Math.ceil(g.measureText(tt).width) - 20 * S, by - 15 * S, S, tc);
    }
    // content
    g.drawImage(content, pad, pad + headH);
    // ramp rule + footer url
    var ry = pad + headH + content.height + 12 * S;
    _rampRule(g, pad, ry, W - pad * 2, 4 * S, dark);
    g.font = (12 * S) + "px " + _LOGO;
    g.fillStyle = dark ? "#868A95" : "#6B6657";
    g.fillText(SITE, pad, ry + 22 * S);
    return c;
  }
  function _clip(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
  function _slug(s) { return (String(s || "eephus") .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")) || "eephus"; }

  // ---- pixel icon painter (final-pass plan 5.7, PX-18) ----------------------
  // A canvas cannot draw an external <use>, so the exports paint the icon set's
  // own bitmaps (the 12 x 12 core of each symbol, written by tools/pixel_icons.py
  // beside the sprite) with fillRect, one rect per horizontal run. The table is
  // fetched on the first export only, never on page load, and is stamped with the
  // sprite's own ?v= (one generator writes both). A failed fetch paints nothing:
  // the export falls back to its text-only frame.
  var _iconTable = null, _iconsReady = null;
  function _iconsURL() {
    var u = document.querySelector('use[href*="/assets/eephus-icons.svg"]');
    var m = u ? /\?v=([^#"']+)/.exec(u.getAttribute("href") || "") : null;
    return "/assets/eephus-icons.json" + (m ? "?v=" + m[1] : "");
  }
  function loadIcons() {
    if (_iconsReady) return _iconsReady;
    _iconsReady = Promise.resolve().then(function () {
      if (typeof fetch !== "function") return null;
      return fetch(_iconsURL()).then(function (r) { return r.ok ? r.json() : null; });
    }).catch(function () { return null; }).then(function (t) {
      _iconTable = (t && typeof t === "object") ? t : null;
      return _iconTable;
    });
    return _iconsReady;
  }
  function _iconRows(key) {
    var e = _iconTable && _iconTable[key];
    if (e && e.alias) e = _iconTable[e.alias];
    return (e && e.rows && e.rows.length) ? e.rows : null;
  }
  function hasIcon(key) { return !!_iconRows(key); }
  // Paint icon `key` with its top-left at (x, y) in the context's own units.
  // The scale is a whole number of pixels per bitmap cell and the origin is
  // snapped to whole units, so with the exports' integer supersample every cell
  // lands on whole device pixels: no blurred edge, at any format. Ink ("#") and
  // the accent group ("+") both take `hex` (an icon at rest has its accent in
  // its ink, plan 5.7.1 rule 4) unless `accentHex` is given. Returns the width
  // painted (12 x scale), or 0 when the table or the key is missing.
  function pxIcon(ctx, key, x, y, scale, hex, accentHex) {
    var rows = _iconRows(key);
    if (!rows || !ctx) return 0;
    var s = Math.max(1, Math.round(Number(scale) || 1));
    var x0 = Math.round(Number(x) || 0), y0 = Math.round(Number(y) || 0);
    var prev = ctx.fillStyle;
    for (var r = 0; r < rows.length; r++) {
      var row = String(rows[r]);
      var c = 0;
      while (c < row.length) {
        var ch = row.charAt(c);
        if (ch !== "#" && ch !== "+") { c++; continue; }
        var c1 = c;
        while (c1 < row.length && row.charAt(c1) === ch) c1++;
        ctx.fillStyle = (ch === "+" && accentHex) ? accentHex : hex;
        ctx.fillRect(x0 + c * s, y0 + r * s, (c1 - c) * s, s);
        c = c1;
      }
    }
    ctx.fillStyle = prev;
    return rows[0].length * s;
  }
  // The icon key of the module this page belongs to: the first path segment
  // (/fa/ is "fa", /mlbstats/ is "mlbstats"), which is the icon set's own key
  // for every module route. "" when the page has no icon (the homepage).
  function routeIcon() {
    var seg = String((location && location.pathname) || "/").split("/")[1] || "";
    seg = seg.replace(/\.html?$/, "");
    return hasIcon(seg) ? seg : "";
  }

  // ---- pixel lockup painter (owner ask 2, PB-08 / BR-08) -------------------
  // Under build_site.PIXEL_BRAND every page serves the pixel lockup, and the
  // exports paint the same lockup from its committed PNG strikes
  // (tools/pixel_brand.py writes them to assets/brand/ beside the DOM
  // fragments) instead of setting the words in a font. With the flag off no
  // page carries the lockup, nothing is fetched and every frame keeps its text
  // wordmark. A strike is drawn only at a whole number of device
  // pixels per strike pixel, from a whole device pixel, with smoothing off, so
  // every lockup pixel is a flat square (the _pxIcon idea). The strikes load at
  // export time, never on page load; a failed load leaves the text wordmark.
  // Strike geometry, pinned to the generator by test_pixel_lockup_painter.py:
  // scale -> [width, height] in strike pixels; the letters' baseline sits
  // LOCKUP_BASE_U font pixels under the strike's top edge.
  var LOCKUP_STRIKES = { 4: [220, 84], 2: [110, 42] };
  var LOCKUP_BASE_U = 19;
  var _lockupImg = {}, _lockupReady = {};
  // The flag is read off the page: only the pixel lockup carries its words as
  // the visually hidden .wm-txt span (build_site.pixel_wordmark). A read, never
  // a write: the lockup's motion stays CSS only.
  var PIXEL_BRAND_PROBE = ".nameplate > .wm-txt";
  function pixelBrand() {
    try { return !!document.querySelector(PIXEL_BRAND_PROBE); } catch (e) { return false; }
  }
  // The strike that paints letters u device pixels per font pixel: the largest
  // committed scale that divides u, at the whole factor u / scale (s 4 at 1 is
  // the strike drawn for that size, not s 2 doubled). null when none divides u.
  function lockupStrike(u) {
    u = Math.round(Number(u) || 0);
    var scales = [4, 2];
    for (var i = 0; i < scales.length; i++) {
      if (u >= scales[i] && u % scales[i] === 0) return { s: scales[i], k: u / scales[i] };
    }
    return null;
  }
  function _lockupKey(s, dark) { return "s" + s + "-" + (dark ? "dark" : "light"); }
  function loadLockup(u, dark) {
    var st = lockupStrike(u);
    if (!st) return Promise.resolve(null);
    var key = _lockupKey(st.s, dark);
    if (_lockupReady[key]) return _lockupReady[key];
    var url = "/assets/brand/wordmark-" + key + ".png";
    _lockupReady[key] = Promise.resolve().then(function () {
      if (typeof fetch !== "function" || typeof Image !== "function") return null;
      // no-cache revalidates: the strike carries no ?v= stamp of its own
      return fetch(url, { cache: "no-cache" }).then(function (r) { return r.ok ? r.blob() : null; });
    }).then(function (blob) {
      if (!blob) return null;
      return new Promise(function (resolve) {
        var img = new Image();
        var src = URL.createObjectURL(blob);
        img.onload = function () { URL.revokeObjectURL(src); resolve(img); };
        img.onerror = function () { URL.revokeObjectURL(src); resolve(null); };
        img.src = src;
      });
    }).catch(function () { return null; }).then(function (img) {
      var dim = LOCKUP_STRIKES[st.s];
      // a strike whose size is not the pinned geometry paints nothing
      _lockupImg[key] = (img && img.width === dim[0] && img.height === dim[1]) ? img : null;
      return _lockupImg[key];
    });
    return _lockupReady[key];
  }
  // The lockup box in the context's own units (unit = device pixels per unit):
  // { w, h, base } with base the letters' baseline under the top edge, or null.
  function lockupBox(u, unit) {
    var st = lockupStrike(u);
    if (!st) return null;
    var d = Math.max(1, Math.round(Number(unit) || 1));
    var dim = LOCKUP_STRIKES[st.s];
    return { w: dim[0] * st.k / d, h: dim[1] * st.k / d, base: LOCKUP_BASE_U * u / d };
  }
  // Paint the lockup with its top-left at (x, y) in the context's units, letters
  // u device pixels per font pixel. Returns the box painted, or null when the
  // strike is not loaded (the caller sets its text wordmark instead).
  function pxLockup(ctx, x, y, u, unit, dark) {
    var st = lockupStrike(u);
    var box = lockupBox(u, unit);
    var img = st ? _lockupImg[_lockupKey(st.s, dark)] : null;
    if (!ctx || !box || !img) return null;
    var d = Math.max(1, Math.round(Number(unit) || 1));
    var x0 = Math.round((Number(x) || 0) * d) / d, y0 = Math.round((Number(y) || 0) * d) / d;
    var smooth = ctx.imageSmoothingEnabled;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, x0, y0, box.w, box.h);
    ctx.imageSmoothingEnabled = smooth;
    return box;
  }

  function exportImage(host, action, kind) {
    toast("Rendering image…");
    var jobs = [_ensureH2C(), _awaitFonts(), loadIcons()];
    if (pixelBrand()) jobs.push(loadLockup(4, _dark()));   // the frame's lockup: u 4 device px
    return Promise.all(jobs).then(function (r) {
      var h2c = r[0];
      var target = kind === "chart" ? (host.querySelector("svg") || host)
                                    : (host.matches("table") ? host : (host.querySelector("table") || host));
      var dark = _dark();
      return h2c(target, { useCORS: true, backgroundColor: dark ? "#0C0C0E" : "#F4F0E6", scale: 2, logging: false })
        .then(function (content) {
          var title = (scrape(host) || {}).title || (kind === "chart" ? "Chart" : "Table");
          var framed = _brandCompose(content, title, dark);
          return _dispatchCanvas(framed, action, "eephus-" + _slug(title) + ".png", title + " · " + SITE);
        });
    });
  }

  // Vector SVG download: clone the chart svg and bake computed styles inline so
  // var()/class-based fills survive standalone serialization.
  function exportChartSVG(host) {
    var svg = host.matches && host.matches("svg") ? host : (host.querySelector ? host.querySelector("svg") : null);
    if (!svg) { toast("No vector chart here"); return; }
    var clone = svg.cloneNode(true);
    _inlineStyles(svg, clone);
    if (!clone.getAttribute("xmlns")) clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    var s = new XMLSerializer().serializeToString(clone);
    var blob = new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n' + s], { type: "image/svg+xml" });
    var a = document.createElement("a");
    a.download = "eephus-" + _slug((scrape(host) || {}).title || "chart") + ".svg";
    a.href = URL.createObjectURL(blob);
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    toast("SVG downloaded");
  }
  var _SVG_PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap",
    "opacity", "fill-opacity", "stroke-opacity", "font-family", "font-size", "font-weight", "text-anchor"];
  function _inlineStyles(src, dst) {
    try {
      var cs = getComputedStyle(src);
      var decl = "";
      _SVG_PROPS.forEach(function (p) {
        var v = cs.getPropertyValue(p);
        if (v && v !== "normal" && v !== "none" || p === "fill") decl += p + ":" + v + ";";
      });
      if (decl) dst.setAttribute("style", decl + (dst.getAttribute("style") || ""));
    } catch (e) {}
    var sk = src.children || [], dk = dst.children || [];
    for (var i = 0; i < sk.length; i++) if (dk[i]) _inlineStyles(sk[i], dk[i]);
  }

  // ---- the quiet chip + auto-wiring ---------------------------------------
  function _hasLiveChip(host) {
    for (var i = 0; i < host.children.length; i++) {
      var ch = host.children[i];
      if (ch.classList && ch.classList.contains("eephus-export-chip")) return true;
    }
    return false;
  }
  function makeChip(host, kind) {
    if (!host || _hasLiveChip(host)) return;   // live-chip check auto-heals after SPA re-renders
    var chip = el("button", "eephus-export-chip");
    chip.type = "button";
    chip.setAttribute("aria-label", kind === "chart" ? "Export chart" : "Copy or export table");
    chip.title = chip.getAttribute("aria-label");
    // The pixel export icon (PX_SYSTEM_SWEEP) replaces the vector copy glyph.
    chip.innerHTML = window.EephusIco ? window.EephusIco("export", 12) : "";
    chip.addEventListener("click", function (e) {
      e.preventDefault(); e.stopPropagation();
      if (EephusExport._menu) { closeMenu(); return; }
      openMenu(chip, host, kind);
    });
    // keep the host positioned so the chip can sit top-right
    try { if (getComputedStyle(host).position === "static") host.style.position = "relative"; } catch (e) {}
    host.appendChild(chip);
    host.classList.add("eephus-exportable");
  }

  // Selectors that are safe to auto-attach to. Real tables across the apps +
  // grids/charts explicitly opted in with data-export. mlbstats-table covers
  // every /mlbstats/ and /pal/ leaderboard (each sits in its own
  // .mlbstats-scroll wrapper); tm-board-table is the Trade Board (its own
  // .tm-board-tablewrap wrapper) - parity with the FA/projections boards.
  var TABLE_SEL = "table.tt-table, table.draft-table, table.detail-table, table.proj-table, table.compare-stat-table, table.mlbstats-table, table.tm-board-table, table[data-export]";
  var CHART_SEL = "[data-export-chart]";
  var GRID_SEL = "[data-export-grid]";

  function attach(host, opts) {
    opts = opts || {};
    makeChip(host, opts.kind || "table");
  }

  function scan(root) {
    root = root || document;
    try {
      Array.prototype.forEach.call(root.querySelectorAll(TABLE_SEL), function (t) {
        // skip tiny/structural tables (need a header + at least one data row)
        if (t.rows && t.rows.length < 2) return;
        // chip goes on the table's WRAPPER (a button can't be a valid <table>
        // child). scrape() finds the table inside the wrapper.
        makeChip(t.parentElement || t, "table");
      });
      Array.prototype.forEach.call(root.querySelectorAll(GRID_SEL), function (g) { makeChip(g, "table"); });
      Array.prototype.forEach.call(root.querySelectorAll(CHART_SEL), function (c) { makeChip(c, "chart"); });
    } catch (e) { /* never break the page */ }
  }

  // Debounced observer: re-scan after the SPA re-renders, without touching any
  // render function. Cheap - only queries the known selectors.
  var _scanTimer = null;
  function _scheduleScan() { clearTimeout(_scanTimer); _scanTimer = setTimeout(function () { scan(document); }, 250); }

  function boot() {
    _injectCSS();
    scan(document);
    try {
      new MutationObserver(_scheduleScan).observe(document.body, { childList: true, subtree: true });
    } catch (e) {}
  }

  function _injectCSS() {
    if (document.getElementById("eephus-export-css")) return;
    var css = document.createElement("style");
    css.id = "eephus-export-css";
    css.textContent = [
      ".eephus-exportable{ }",
      // quiet chip: low-opacity, top-right, brightens on host hover / focus
      ".eephus-export-chip{position:absolute;top:4px;right:4px;z-index:6;display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;padding:0;cursor:pointer;color:var(--text-tertiary,#777);background:var(--bg-secondary,#fff);border:1px solid var(--border,#ccc);border-radius:0;opacity:0;transition:opacity .12s steps(3,start),color .12s steps(3,start),border-color .12s steps(3,start);}",
      ".eephus-exportable:hover > .eephus-export-chip,.eephus-export-chip:focus-visible{opacity:.85;}",
      ".eephus-export-chip:hover{opacity:1;color:var(--accent-lilac,#6E56CF);border-color:var(--accent-lilac,#6E56CF);}",
      // the chip (22 px wide at right:4px) sits over the right end of the header
      // row, so the last header cell keeps 30 px clear and a right-aligned label
      // never runs under it. Keyed on the table selectors as well as the host
      // class: the class lands a scan after render, and a board that measures
      // its own fit (mlbstats markFit) must measure with the reserve in place.
      ".eephus-exportable > table > thead > tr > th:last-child,:is(" + TABLE_SEL + ") > thead > tr > th:last-child{padding-right:30px;}",
      ".eephus-export-menu{position:fixed;z-index:9999;min-width:208px;background:var(--bg-secondary,#fff);border:1px solid var(--border,#ccc);box-shadow:var(--shadow-card-hover,0 4px 16px rgba(0,0,0,.2));font-family:var(--font-retro,monospace);padding:4px;}",
      ".ex-menu-head{font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--text-tertiary,#777);padding:6px 8px 4px;}",
      ".ex-menu-item{display:flex;align-items:baseline;justify-content:space-between;gap:10px;width:100%;text-align:left;background:transparent;border:0;cursor:pointer;padding:6px 8px;color:var(--text-primary,#111);font-family:inherit;font-size:12.5px;}",
      ".ex-menu-item:hover{background:var(--bg-hover,rgba(0,0,0,.05));color:var(--accent-lilac,#6E56CF);}",
      ".ex-menu-item small{color:var(--text-tertiary,#777);font-size:10px;white-space:nowrap;}",
      ".ex-menu-sep{height:1px;background:var(--border-light,#eee);margin:4px 2px;}",
      ".eephus-export-toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(8px);z-index:10000;background:var(--bg-header,#0E2B4D);color:var(--text-on-accent,#fff);font-family:var(--font-retro,monospace);font-size:12.5px;padding:9px 16px;border:1px solid var(--accent-lilac,#6E56CF);opacity:0;pointer-events:none;transition:opacity .15s steps(4,start),transform .15s steps(4,start);}",
      ".eephus-export-toast.is-on{opacity:1;transform:translateX(-50%) translateY(0);}",
      /* the chip and toast step in whole frames (PX_SYSTEM_SWEEP, the lamp idiom: the toast rises 8 px in
         four 2 px steps, the first at once) and run under Reduce Motion too (owner, 2026-10-01) */
    ].join("\n");
    document.head.appendChild(css);
  }

  // ---- public API ----------------------------------------------------------
  window.EephusExport = {
    scan: scan,
    attach: attach,
    scrape: scrape,
    formats: formats,
    copyText: copyText,
    toast: toast,
    // the pixel icon painter (PX-18), shared with the Generate GFX engine
    loadIcons: loadIcons,
    hasIcon: hasIcon,
    pxIcon: pxIcon,
    routeIcon: routeIcon,
    // the pixel lockup painter (PB-08), shared with the Generate GFX engine
    pixelBrand: pixelBrand,
    lockupStrike: lockupStrike,
    lockupBox: lockupBox,
    loadLockup: loadLockup,
    pxLockup: pxLockup,
    copyTable: function (host, fmt) {
      var model = scrape(host);
      var built = buildText(model, fmt || "markdown");
      return copyText(built.text, built.html);
    },
    _menu: null,
  };

  if (document.body) boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
