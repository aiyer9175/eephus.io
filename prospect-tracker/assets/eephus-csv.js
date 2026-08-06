// eephus.io - per-board CSV download (shared component).
// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
//
// WHAT THIS ADDS THAT eephus-export.js DOES NOT
// ---------------------------------------------
// eephus-export.js puts a quiet chip on every table with CSV in its COPY menu.
// That is a share affordance: it hands you a clipboard buffer. /diamond/
// advertised "data exports", which is a different verb - a file on disk that
// opens in a spreadsheet. This module is that file, and nothing else.
//
// It deliberately does NOT re-implement the serializer. EephusExport already
// owns scrape() and formats.csv, both pure and already correct about quoting,
// grouped headers, data-export-skip and data-export-text. A second CSV writer
// on the same page is a second answer to "what does this table contain", and
// the two would drift. This module borrows those two functions and adds the
// download, with a small local fallback for the case where the shared runtime
// is absent (a hand-authored page that carries its own script tags).
//
// OPT-IN IS ONE ATTRIBUTE, ON THE SERVER
// --------------------------------------
//   <div id="dynasty-app-root" data-csv-export="dynasty-board"></div>
// build_site.py stamps that attribute on the mount point each board already
// renders into. The board's own JS is untouched: the table appears inside the
// host whenever the app paints it, a debounced observer notices, and the
// control appears. That is why the opt-in is one line per board and why no
// module app had to be edited to get an export.
//
// WHAT THE FILE CONTAINS IS WHAT IS ON SCREEN
// -------------------------------------------
// The rows are scraped from the rendered DOM, so the download carries the
// user's current sort and filter, and every cell in the exact format the page
// displays (decimals, percent signs, plus-stat conventions). It is not a slice
// of the underlying artifact and does not claim to be; the row count rides the
// button so there is no ambiguity about how much came out. Anyone who wants
// the full, unfiltered payload gets it from the documented artifacts, which
// the button's own title text points at.
(function () {
  "use strict";
  if (window.EephusCSV) return;

  var HOST_SEL = "[data-csv-export]";
  var TABLE_SEL = "table";
  // A control on a table with no data rows is a promise of an empty file, so
  // the button only appears once the board has painted at least one row.
  var MIN_DATA_ROWS = 1;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // ---- the table this host exports ----------------------------------------
  // Boards render several sections into one mount and hide the inactive ones,
  // so "the table" is the VISIBLE one. offsetParent is null for a display:none
  // subtree, which is exactly the test we want and costs one layout read.
  function targetTable(host) {
    var tables = host.querySelectorAll ? host.querySelectorAll(TABLE_SEL) : [];
    var first = null;
    for (var i = 0; i < tables.length; i++) {
      var t = tables[i];
      if (!dataRowCount(t)) continue;
      if (!first) first = t;
      if (t.offsetParent !== null) return t;
    }
    return first;
  }

  function dataRowCount(table) {
    if (!table) return 0;
    var body = table.tBodies && table.tBodies.length ? table.tBodies[0] : null;
    if (body) return body.rows.length;
    // No <tbody>: fall back to total rows minus the header row.
    return Math.max(0, (table.rows ? table.rows.length : 0) - 1);
  }

  // ---- CSV text ------------------------------------------------------------
  // Shared runtime first. The fallback exists so a page without
  // eephus-export.js still downloads something correct rather than nothing;
  // it handles the common case (one header row, plain cells) and is not a
  // second full implementation.
  function toCSV(table) {
    var X = window.EephusExport;
    if (X && X.scrape && X.formats && X.formats.csv) {
      return X.formats.csv(X.scrape(table));
    }
    var rows = [];
    for (var i = 0; i < table.rows.length; i++) {
      var cells = table.rows[i].cells, line = [];
      for (var j = 0; j < cells.length; j++) {
        line.push(csvCell((cells[j].innerText || cells[j].textContent || "")
          .replace(/\s+/g, " ").trim()));
      }
      rows.push(line.join(","));
    }
    return rows.join("\n");
  }

  function csvCell(s) {
    s = String(s == null ? "" : s);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function fileName(host) {
    var base = (host.getAttribute("data-csv-export") || "table")
      .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    var d = new Date();
    var iso = d.getFullYear() + "-"
      + String(d.getMonth() + 1).padStart(2, "0") + "-"
      + String(d.getDate()).padStart(2, "0");
    return "eephus-" + (base || "table") + "-" + iso + ".csv";
  }

  // ---- download ------------------------------------------------------------
  function download(host) {
    var table = targetTable(host);
    if (!table) return false;
    var text = toCSV(table);
    // Leading BOM: without it Excel opens a UTF-8 CSV in the local ANSI
    // codepage and mangles every accented player name. Sheets, Numbers and
    // pandas all skip it, so the cost is zero and the failure it prevents is
    // the one a reader would blame on our data.
    var blob = new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = fileName(host);
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    if (window.EephusExport && window.EephusExport.toast) {
      window.EephusExport.toast("CSV downloaded");
    }
    return true;
  }

  // ---- the control ---------------------------------------------------------
  function ensureControl(host) {
    var table = targetTable(host);
    var n = dataRowCount(table);
    var bar = host.querySelector(":scope > .eph-csv-bar");
    if (n < MIN_DATA_ROWS) {
      if (bar && bar.parentNode) bar.parentNode.removeChild(bar);
      return;
    }
    if (!bar) {
      bar = el("div", "eph-csv-bar");
      var btn = el("button", "eph-csv-btn");
      btn.type = "button";
      btn.appendChild(el("span", "eph-csv-label", "Download CSV"));
      btn.appendChild(el("span", "eph-csv-n", ""));
      btn.title = "Downloads the rows currently on screen, in the order and "
        + "format shown. The full artifacts are documented on the data page.";
      btn.addEventListener("click", function () {
        try { download(host); } catch (e) { /* never break the board */ }
      });
      bar.appendChild(btn);
      host.insertBefore(bar, host.firstChild);
    }
    var count = bar.querySelector(".eph-csv-n");
    var label = n === 1 ? "1 row" : n + " rows";
    if (count && count.textContent !== label) count.textContent = label;
    var button = bar.querySelector(".eph-csv-btn");
    if (button) button.setAttribute("aria-label", "Download CSV, " + label);
  }

  function scan(root) {
    root = root || document;
    try {
      var hosts = root.querySelectorAll(HOST_SEL);
      for (var i = 0; i < hosts.length; i++) ensureControl(hosts[i]);
      // A host may sit ABOVE the mutated node, so a scan rooted at the mutation
      // would miss it; document-rooted scans keep this correct and the selector
      // is cheap enough to run on a debounce.
    } catch (e) { /* never break the page */ }
  }

  var _timer = null;
  function schedule() {
    clearTimeout(_timer);
    _timer = setTimeout(function () { scan(document); }, 250);
  }

  function injectCSS() {
    if (document.getElementById("eephus-csv-css")) return;
    var css = document.createElement("style");
    css.id = "eephus-csv-css";
    // Theme tokens with literal fallbacks, same contract as eephus-export.js:
    // the fallback only applies on a surface that never loaded site.css.
    css.textContent = [
      ".eph-csv-bar{display:flex;justify-content:flex-end;margin:0 0 8px;}",
      ".eph-csv-btn{display:inline-flex;align-items:baseline;gap:7px;cursor:pointer;",
      "padding:5px 10px;border:1px solid var(--border,#ccc);background:var(--bg-secondary,#fff);",
      "color:var(--text-secondary,#555);font-family:var(--font-retro,monospace);font-size:11px;",
      "letter-spacing:.06em;text-transform:uppercase;border-radius:0;}",
      ".eph-csv-btn:hover{color:var(--accent-lilac,#6E56CF);border-color:var(--accent-lilac,#6E56CF);}",
      ".eph-csv-btn:focus-visible{outline:2px solid var(--accent-lilac,#6E56CF);outline-offset:2px;}",
      ".eph-csv-n{color:var(--text-tertiary,#777);font-size:10px;letter-spacing:.04em;text-transform:none;}",
    ].join("");
    document.head.appendChild(css);
  }

  function boot() {
    injectCSS();
    scan(document);
    try {
      new MutationObserver(schedule).observe(document.body,
        { childList: true, subtree: true });
    } catch (e) { /* observer unavailable: the first scan still stands */ }
  }

  window.EephusCSV = {
    scan: scan,
    download: download,
    toCSV: toCSV,
    targetTable: targetTable,
  };

  if (document.body) boot();
  else document.addEventListener("DOMContentLoaded", boot);
})();
