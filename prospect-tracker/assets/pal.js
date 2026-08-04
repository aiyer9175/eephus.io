/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - Alchemy Lab (PAL)
// =============================================================================
// Renders data/pal.json (pal_export.py) into three sections:
//   rp2sp   - relievers who profile as starters (RP->SP FIT, arsenal depth,
//             command, platoon-neutrality, role-adjusted velocity)
//   sp2rp   - starters whose stuff would play up in relief (SP->RP FIT, putaway
//             pitch, projected relief velo + REM+)
//   history - an archive of past SP<->RP switches (the model's backtest set)
//             with a scorecard, plus a pitch-mix before/after view
// The FIT scores are a candidate SCREEN, not a success probability. Backtest
// evidence is PER DIRECTION (repaired harness, 2026-07): SP->RP FIT carries a
// validated directional signal vs realized WAR change; RP->SP FIT is a
// structural screen whose backtest does NOT validate ranking within the
// direction. The retired pooled rho is reporting-only and never cited here.
(function () {
  "use strict";

  var DATA_URL = "/data/pal.json";
  var DATA = null;
  var LOAD_ERROR = false;    // fetch failed / non-OK (distinct from "not exported yet")
  var section = "rp2sp";     // rp2sp | sp2rp | posfit | history | pitchadd | platoon | prospects
  var historyView = "table"; // table | mix
  var sortKey = "fit";
  var sortAsc = false;
  var openRow = null;

  // ---- Position Fit (hitters) ----------------------------------------------
  // The hitter half of the lab. Payload is the SLIM view of the positional-fit
  // model that build_site.py bakes (data/positional_fit_ui.json); the full
  // artifact carries per-player evidence logs and never ships. Loaded lazily
  // the first time the section is opened so the pitcher sections stay light.
  var POSFIT_URL = "/data/positional_fit_ui.json";
  var PF = null;
  var PF_ERROR = false;
  var PF_LOADING = false;
  var posfitView = "misplaced";  // misplaced | down | board | ladder

  var FASTBALLS = { FF: 1, SI: 1, FC: 1, FT: 1 };
  var COMP_LABELS = {
    arsenal_depth: "Arsenal depth", command: "Command",
    fb_reliance_inv: "Not fastball-reliant", stuff_quality: "Contact quality",
    platoon_neutrality: "Platoon-neutral", survivability: "Weak contact",
    stuff_upside: "Stuff upside", tto_leakage: "TTO leakage (relief tilt)",
    putaway: "Putaway pitch", velo_leverage: "Velo leverage",
    conversion_need: "Conversion need (struggling as SP)",
  };
  var WARN_FLAGS = { relief_only: 1, needs_third: 1, fb_heavy: 1, platoon_risk: 1, succeeding_sp: 1 };

  // ---- helpers --------------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function num(v) { return (v == null || isNaN(v)) ? null : Number(v); }
  function fInt(v) { var n = num(v); return n == null ? "-" : String(Math.round(n)); }
  // FV / 20-80 grades display rounded UP, never nearest (owner rule; mirrors
  // EEPHUS_HUB.fvCeil with the same float-noise epsilon guard).
  function fCeil(v) { var n = num(v); return n == null ? "-" : String(Math.ceil(n - 1e-9)); }
  function f1(v) { var n = num(v); return n == null ? "-" : n.toFixed(1); }
  function f2(v) { var n = num(v); return n == null ? "-" : n.toFixed(2); }
  function fPct(v) { var n = num(v); return n == null ? "-" : (n * 100).toFixed(1) + "%"; }
  function f3(v) { var n = num(v); return n == null ? "-" : n.toFixed(3); }
  function gloss(label, term) { return '<span class="g-term" data-gl="' + esc(term) + '">' + esc(label) + "</span>"; }
  function wireGlossary(el) { try { if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(el); } catch (e) { } }
  function logo(team) { try { return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo) ? EEPHUS_HUB.teamLogo(team) : ""; } catch (e) { return ""; } }
  function chart(fn, arg, opts) { try { return (window.EEPHUS_HUB && EEPHUS_HUB[fn]) ? EEPHUS_HUB[fn](arg, opts) : ""; } catch (e) { return ""; } }

  // player_links map (MLBAM -> merged-card key), preloaded once so candidate
  // names link to the MLB player card at /projections/#player=<key> - the same
  // resolution the /mlbstats/ and /trademachine/ boards use. Unresolved names
  // (or prospects, who have no MLBAM) stay plain text.
  var LINKS = null;
  function loadLinks() {
    fetch("/data/player_links.json", { cache: "no-cache" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { LINKS = j || {}; if (DATA || PF) render(); })
      .catch(function () { LINKS = {}; });
  }
  function playerHref(mlbam) {
    if (!LINKS || !LINKS.byMlbam || mlbam == null) return null;
    var hit = LINKS.byMlbam[String(mlbam)];
    return (hit && hit.key) ? ("/projections/#player=" + encodeURIComponent(hit.key)) : null;
  }
  function nameLink(name, mlbam) {
    var nm = esc(name || "-");
    var href = playerHref(mlbam);
    return href ? '<a class="mlbstats-name-link" href="' + href + '" title="Open the MLB player card">' + nm + "</a>" : nm;
  }

  // ---- collapsible chart panels (shared pattern with /mlbstats/) ------------
  // Charts default COLLAPSED; the header is the toggle and the open/closed state
  // persists in localStorage.
  var COLLAPSE = {};
  function collapseState(id) {
    if (COLLAPSE[id] != null) return COLLAPSE[id];
    var v = true; // default collapsed
    try {
      var s = window.localStorage.getItem("pal.collapse." + id);
      if (s === "0") v = false; else if (s === "1") v = true;
    } catch (e) { /* localStorage optional */ }
    COLLAPSE[id] = v;
    return v;
  }
  function setCollapse(id, collapsed) {
    COLLAPSE[id] = collapsed;
    try { window.localStorage.setItem("pal.collapse." + id, collapsed ? "1" : "0"); } catch (e) { /* optional */ }
  }
  function bindCollapse(root) {
    root.querySelectorAll("[data-collapse]").forEach(function (el) {
      var head = el.querySelector(".mlbstats-collapse-head");
      if (!head) return;
      head.addEventListener("click", function (e) {
        e.stopPropagation();
        var id = el.getAttribute("data-collapse");
        var next = !el.classList.contains("is-collapsed");
        el.classList.toggle("is-collapsed", next);
        head.setAttribute("aria-expanded", String(!next));
        setCollapse(id, next);
      });
    });
  }
  function vizWrap(id, title, svg) {
    if (!svg) return "";
    var collapsed = collapseState(id);
    var body = '<div class="mlbstats-viz"><div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">' + title + "</div>" + svg + "</div></div>";
    return '<div class="mlbstats-collapse' + (collapsed ? " is-collapsed" : "") + '" data-collapse="' + esc(id) + '">'
      + '<button type="button" class="mlbstats-collapse-head" aria-expanded="' + (!collapsed) + '">'
      + '<span class="mlbstats-collapse-caret" aria-hidden="true"></span>Charts</button>'
      + '<div class="mlbstats-collapse-body">' + body + "</div></div>";
  }
  function rp2spViz() {
    var rows = (DATA && DATA.rp2sp) || [];
    if (rows.length < 12) return "";
    var hist = chart("histogram", rows.map(function (r) { return r.fit; }),
      { height: 100, min: 0, max: 100, highlightAbove: 70, refs: [{ at: 60, label: "starter shape" }], aria: "RP-SP FIT distribution" });
    return vizWrap("rp2sp-viz", gloss("RP→SP FIT", "rp_sp_fit") + ' distribution <span class="proj-dim">(cyan = 70+, a real starter profile)</span>', hist);
  }
  function sp2rpViz() {
    var rows = (DATA && DATA.sp2rp) || [];
    var pts = rows.filter(function (r) { return r.relief_upside != null && r.components && r.components.conversion_need != null; })
      .map(function (r) {
        return { x: r.relief_upside, y: r.components.conversion_need,
                 label: r.name + "  upside " + r.relief_upside + "  need " + r.components.conversion_need + "  FIT " + r.fit,
                 color: r.fit >= 55 ? null : "var(--text-tertiary)" };
      });
    if (pts.length < 8) return "";
    var sc = chart("scatter", pts, { height: 270, xMin: 0, xMax: 100, yMin: 0, yMax: 100,
      xLabel: "relief upside →", yLabel: "↑ conversion need", xRef: 50, yRef: 50, aria: "upside vs need" });
    return vizWrap("sp2rp-viz", 'The conversion sweet spot <span class="proj-dim">(top-right = good stuff AND struggling as a starter)</span>', sc);
  }

  function fitClass(v) {
    var n = num(v);
    if (n == null) return "pal-mid";
    if (n >= 70) return "pal-hi";
    if (n >= 55) return "pal-good";
    if (n >= 42) return "pal-mid";
    return "pal-lo";
  }
  function fitCell(v, term) {
    return '<span class="pal-fit ' + fitClass(v) + '" data-gl="' + esc(term) + '">' + f1(v) + "</span>";
  }
  // Color the conversion-direction chip by direction. RP->SP is the value-additive
  // move (a starter is worth more than a reliever) so it gets the prominent color;
  // SP->RP is the more muted salvage direction. Accepts "RP->SP", "RP→SP", or the
  // spaced arrow form used on the prospect cards.
  function dirClass(direction) {
    var d = String(direction || "").replace(/\s/g, "");
    if (d.indexOf("RP->SP") >= 0 || d.indexOf("RP→SP") >= 0) return " pal-dir--rp2sp";
    if (d.indexOf("SP->RP") >= 0 || d.indexOf("SP→RP") >= 0) return " pal-dir--sp2rp";
    return "";
  }
  // Candidate TIER titles. The role-value logic: a starter is worth more than a
  // reliever, so the premium RP->SP case is a SUCCESSFUL reliever who profiles as
  // a starter; the premium SP->RP case is a starter STRUGGLING in the rotation
  // whose stuff would play up in relief. Titles are wired off the FIT breakpoints
  // (>=70 / >=55 / >=42) plus the server-computed `successful` flag.
  function tierTitle(row, dir) {
    var f = num(row.fit);
    if (f == null) return "";
    if (dir === "sp2rp") {
      if (f >= 70) return "Bullpen Upside";
      if (f >= 55) return "Relief Fit";
      if (f >= 42) return "Marginal Move";
      return "Keep Starting";
    }
    // rp2sp
    if (f >= 70) return row.successful ? "Prime Starter Convert" : "Starter Upside";
    if (f >= 55) return "Worth a Look";
    if (f >= 42) return "Fringe Fit";
    return "Reliever Profile";
  }
  function tierBadge(row, dir) {
    var t = tierTitle(row, dir);
    if (!t) return "";
    return '<div class="pal-tier pal-tier--' + dir + '">' + esc(t) + "</div>";
  }
  function tierLegend(dir) {
    if (dir === "sp2rp") {
      return '<div class="pal-tier-legend">Tiers frame salvaging a struggling starter whose stuff plays up in short bursts: '
        + '<b>Bullpen Upside</b> (70+), <b>Relief Fit</b> (55+), <b>Marginal Move</b> (42+), <b>Keep Starting</b> (below 42).</div>';
    }
    return '<div class="pal-tier-legend">Tiers read FIT with role value in mind (a starter is worth more than a reliever, so a '
      + 'successful reliever who profiles as a starter is the premium case): <b>Prime Starter Convert</b> (70+, already succeeding '
      + 'in relief), <b>Starter Upside</b> (70+), <b>Worth a Look</b> (55+), <b>Fringe Fit</b> (42+), <b>Reliever Profile</b> (below 42).</div>';
  }
  function fbPct(row) {
    if (row.fb_pct != null) return row.fb_pct;
    var s = 0;
    (row.arsenal || []).forEach(function (p) { if (FASTBALLS[p.pitch]) s += (p.usage || 0); });
    return s;
  }
  function flagChips(flags) {
    return (flags || []).map(function (f) {
      var cls = WARN_FLAGS[f.key] ? " pal-flag--warn" : " pal-flag--good";
      return '<span class="pal-flag' + cls + '">' + esc(f.label) + "</span>";
    }).join("");
  }
  function empty(m) { return '<div class="mlbstats-empty">' + esc(m) + "</div>"; }

  // ---- "why" panel (component bars + arsenal) -------------------------------
  function bar(v) {
    var n = Math.max(0, Math.min(100, num(v) || 0));
    return '<div class="pal-bar"><span style="width:' + n + '%"></span></div>';
  }
  function whyPanel(row) {
    var comps = row.components || {};
    var rows = Object.keys(comps).map(function (k) {
      if (comps[k] == null) return "";
      return '<div class="pal-comp"><span class="pal-comp-label">' + esc(COMP_LABELS[k] || k)
        + "</span>" + bar(comps[k]) + '<span class="pal-comp-val">' + fInt(comps[k]) + "</span></div>";
    }).join("");
    var ars = (row.arsenal || []).slice().sort(function (a, b) { return (b.usage || 0) - (a.usage || 0); })
      .map(function (p) {
        return '<div class="pal-ars-row"><span class="pal-ars-pitch">' + esc(p.pitch || "-") + "</span>"
          + bar((p.usage || 0) * 100) + '<span class="pal-ars-meta">' + fPct(p.usage)
          + (p.whiff != null ? " &middot; " + fPct(p.whiff) + " whiff" : "")
          + (p.est_woba != null ? " &middot; " + f2(p.est_woba) + " xwOBA" : "") + "</span></div>";
      }).join("");
    var rec = row.pitch_add
      ? ('<div class="pal-comp" style="grid-template-columns:1fr;margin-top:10px;border-top:1px solid var(--border);padding-top:8px">'
        + '<span class="pal-comp-label" style="color:var(--text-primary)"><b>Add ' + esc(row.pitch_add.add) + "</b>"
        + (row.pitch_add.target ? " vs " + esc(row.pitch_add.target) : "") + ". " + esc(row.pitch_add.reason) + "</span></div>")
      : "";
    return '<td colspan="20"><div class="pal-why"><div class="pal-why-grid">'
      + '<div><h4>Why this score</h4>' + rows + rec + "</div>"
      + '<div><h4>Arsenal</h4>' + (ars || '<div class="mlbstats-note">no pitch data</div>') + "</div>"
      + "</div></div></td>";
  }

  // ---- generic sortable candidate table -------------------------------------
  function candTable(rows, cols, term) {
    var head = "<thead><tr>";
    cols.forEach(function (c) {
      var sortable = c.kind !== "rank" && c.kind !== "name" && c.sortable !== false;
      var sorted = c.key === sortKey ? " is-sorted" : "";
      var lbl = c.term ? gloss(c.label, c.term) : esc(c.label);
      // keyboard-operable sort headers (the trademachine pattern): only the
      // genuinely sortable columns carry data-col + the button affordance
      var attrs = sortable
        ? ' data-col="' + c.key + '" tabindex="0" role="button" aria-sort="'
          + (c.key === sortKey ? (sortAsc ? "ascending" : "descending") : "none") + '"'
        : "";
      head += '<th class="mlbstats-col-' + c.key + sorted + '"' + attrs + '>' + lbl + "</th>";
    });
    head += "</tr></thead>";
    var body = "<tbody>";
    rows.forEach(function (r, i) {
      var open = (openRow === r.mlbam);
      // expandable rows are tabbable and announce their open state so the
      // component breakdown is reachable without a mouse
      body += "<tr" + (open ? " class=\"is-open\"" : "") + " data-open=\"" + r.mlbam
        + "\" tabindex=\"0\" aria-expanded=\"" + (open ? "true" : "false") + "\">";
      cols.forEach(function (c) {
        if (c.kind === "rank") { body += "<td>" + (i + 1) + "</td>"; return; }
        if (c.kind === "name") {
          body += '<td class="mlbstats-name pal-expand">' + logo(r.team) + nameLink(r.name, r.mlbam)
            + '<span class="proj-dim"> ' + esc(r.team || "") + "</span>" + flagChips(r.flags) + "</td>";
          return;
        }
        body += "<td>" + c.cell(r) + "</td>";
      });
      body += "</tr>";
      if (open) body += '<tr class="pal-why-tr">' + whyPanel(r) + "</tr>";
    });
    body += "</tbody>";
    return '<div class="mlbstats-scroll"><table class="mlbstats-table">' + head + body + "</table></div>";
  }

  var RP_COLS = [
    { key: "rank", label: "#", kind: "rank" },
    { key: "name", label: "Reliever", kind: "name", sortable: false },
    { key: "fit", label: "RP→SP FIT", term: "rp_sp_fit", desc: true, cell: function (r) { return fitCell(r.fit, "rp_sp_fit") + tierBadge(r, "rp2sp"); } },
    { key: "n_pitches", label: "Arsenal", term: "arsenal_depth", cell: function (r) { return fInt(r.n_pitches) + '<span class="proj-dim"> pitch</span>'; } },
    { key: "fb_pct", label: "FB%", cell: function (r) { return fPct(fbPct(r)); }, get: function (r) { return fbPct(r); } },
    { key: "k_pct", label: "K%", cell: function (r) { return fPct(r.k_pct); } },
    { key: "bb_pct", label: "BB%", cell: function (r) { return fPct(r.bb_pct); }, asc: true },
    { key: "platoon_split", label: "Platoon", term: "platoon_split", cell: function (r) { return r.platoon_split == null ? "-" : f2(r.platoon_split); }, asc: true },
    { key: "proj_velo", label: "velo→SP", term: "role_velo_delta", cell: function (r) { return veloCell(r); } },
  ];
  var SP_COLS = [
    { key: "rank", label: "#", kind: "rank" },
    { key: "name", label: "Starter", kind: "name", sortable: false },
    { key: "fit", label: "SP→RP FIT", term: "sp_rp_fit", desc: true, cell: function (r) { return fitCell(r.fit, "sp_rp_fit") + tierBadge(r, "sp2rp"); } },
    { key: "starter_era", label: "SP ERA", cell: function (r) { return f2(r.starter_era); }, asc: true },
    { key: "relief_upside", label: "Relief upside", cell: function (r) { return f1(r.relief_upside); } },
    { key: "best_whiff", label: "Putaway", term: "putaway_pitch", cell: function (r) { return fPct(r.best_whiff); } },
    { key: "proj_velo", label: "velo→RP", term: "role_velo_delta", cell: function (r) { return veloCell(r); } },
    { key: "proj_relief_rem_plus", label: "proj REM+", term: "rem_plus", cell: function (r) { return r.proj_relief_rem_plus == null ? "-" : '<span class="rem-plus ' + remClass(r.proj_relief_rem_plus) + '">' + fInt(r.proj_relief_rem_plus) + "</span>"; } },
  ];
  // Conversion-history columns: drives the sortable header + the sort accessors
  // (the row cells are still rendered by renderHistory's custom builders). Default
  // sort is year-desc so the newest (current-season, still-pending) conversions
  // lead. Non-numeric columns (Pitcher / Conversion / Before / After / Arsenal)
  // are non-sortable; sortRows is numeric-only.
  var HISTORY_COLS = [
    { key: "name", label: "Pitcher", kind: "name" },
    { key: "direction", label: "Conversion", sortable: false },
    { key: "year", label: "Year", desc: true },
    { key: "pre_ip", label: "Before", sortable: false },
    { key: "post_ip", label: "After", sortable: false },
    { key: "war_delta", label: "WAR before &rarr; after" },
    { key: "arsenal", label: "Arsenal shift", sortable: false },
    { key: "held", label: "Held role", get: function (h) { return h.held === true ? 1 : h.held === false ? 0 : null; } },
    { key: "pre_fit", label: "pre-FIT" },
    { key: "success", label: "Result", get: function (h) { return h.success === true ? 1 : h.success === false ? 0 : null; } },
  ];
  function veloCell(r) {
    if (r.fb_velo == null) return "-";
    var d = (r.proj_velo != null) ? (r.proj_velo - r.fb_velo) : null;
    var arrow = d == null ? "" : '<span class="proj-dim"> ' + (d > 0 ? "+" : "") + d.toFixed(1) + "</span>";
    return f1(r.fb_velo) + (r.proj_velo != null ? " &rarr; " + f1(r.proj_velo) : "") + arrow;
  }
  function remClass(v) { var n = num(v); if (n == null) return "rem-avg"; if (n >= 120) return "rem-elite"; if (n >= 107) return "rem-good"; if (n >= 93) return "rem-avg"; return "rem-low"; }

  function sortRows(rows, cols) {
    var col = null; cols.forEach(function (c) { if (c.key === sortKey) col = c; });
    var out = rows.slice();
    out.sort(function (a, b) {
      var va = col && col.get ? col.get(a) : a[sortKey];
      var vb = col && col.get ? col.get(b) : b[sortKey];
      // missing values always sort LAST regardless of direction (the
      // trademachine convention; matters for nullable columns like Platoon
      // and the pending Held role / Result history cells)
      va = (va == null || isNaN(va)) ? null : Number(va);
      vb = (vb == null || isNaN(vb)) ? null : Number(vb);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return sortAsc ? va - vb : vb - va;
    });
    return out;
  }

  // ---- Generate GFX board specs ---------------------------------------------
  // Each candidate section exports its OWN board (the fa.js/projections.js
  // pattern), rebuilt from the current sort at click time so the shared graphic
  // always matches the on-screen order. FIT is a candidate SCREEN, not a success
  // probability - the caption/legend keep that framing PER DIRECTION (RP->SP is a
  // structural screen, SP->RP is validated). Module accent = cyan (the RP->SP
  // primary direction + the "hi" FIT tier - the pal identity color).
  function gfxChip(id) {
    return window.EEPHUS_GFX ? " &middot; " + EEPHUS_GFX.chipHTML(id, "Generate GFX") : "";
  }
  // Plain-text (canvas-safe) velocity cell: current FB velo -> role-projected
  // velo with the delta. veloCell() emits HTML spans, so the board needs its own
  // text-only builder.
  function veloText(r) {
    if (r.fb_velo == null) return "-";
    var d = (r.proj_velo != null) ? (r.proj_velo - r.fb_velo) : null;
    return f1(r.fb_velo) + (r.proj_velo != null ? " → " + f1(r.proj_velo) : "")
      + (d != null ? "  " + (d > 0 ? "+" : "") + d.toFixed(1) : "");
  }
  function rp2spBoardSpec() {
    var rows = sortRows((DATA && DATA.rp2sp) || [], RP_COLS);
    var brows = rows.map(function (r, i) {
      return { cells: [
        { t: i + 1 },
        { t: r.name, sub: r.team || undefined },
        { t: f1(r.fit), c: "accent" },
        { t: tierTitle(r, "rp2sp") || "-" },
        { t: fInt(r.n_pitches) },
        { t: fPct(fbPct(r)) },
        { t: veloText(r) },
        { t: (r.components && r.components.command != null) ? fInt(r.components.command) : "-" },
      ] };
    });
    return {
      kind: "board", module: "Alchemy Lab", accentToken: "--accent-cyan",
      title: "Alchemy Lab · RP→SP Candidates",
      subtitle: (DATA && DATA.season ? "Season " + DATA.season + " · " : "")
        + rows.length + " relievers who profile as starters",
      url: "eephus.io/pal", filenameBase: "pal-rp2sp-candidates",
      caption: "a candidate screen, not a forecast · RP→SP ranking is a structural screen (not backtest-validated)",
      board: { defaultCount: 25, counts: [10, 25, 50],
        legend: "FIT 0-100 = RP→SP conversion screen · Command = component score 0-100", columns: [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.24 },
          { label: "FIT", frac: 0.09 },
          { label: "Tier", frac: 0.16 },
          { label: "Arsenal", frac: 0.09, wideOnly: true },
          { label: "FB%", frac: 0.09, wideOnly: true },
          { label: "velo→SP", frac: 0.18 },
          { label: "Command", frac: 0.10, wideOnly: true },
        ], rows: brows },
    };
  }
  function sp2rpBoardSpec() {
    var rows = sortRows((DATA && DATA.sp2rp) || [], SP_COLS);
    var brows = rows.map(function (r, i) {
      return { cells: [
        { t: i + 1 },
        { t: r.name, sub: r.team || undefined },
        { t: f1(r.fit), c: "accent" },
        { t: f2(r.starter_era) },
        { t: fPct(r.best_whiff) },
        { t: veloText(r) },
        { t: fInt(r.proj_relief_rem_plus) },
        { t: fPct(r.bb_pct) },
      ] };
    });
    return {
      kind: "board", module: "Alchemy Lab", accentToken: "--accent-cyan",
      title: "Alchemy Lab · SP→RP Candidates",
      subtitle: (DATA && DATA.season ? "Season " + DATA.season + " · " : "")
        + rows.length + " starters whose stuff would play up in relief",
      url: "eephus.io/pal", filenameBase: "pal-sp2rp-candidates",
      caption: "a candidate screen · SP→RP carries a validated directional signal vs realized WAR change",
      board: { defaultCount: 25, counts: [10, 25, 50],
        legend: "FIT 0-100 = SP→RP relief-upside screen (gated by conversion need)", columns: [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.26 },
          { label: "FIT", frac: 0.10 },
          { label: "SP ERA", frac: 0.11 },
          { label: "Putaway whiff", frac: 0.13, wideOnly: true },
          { label: "velo→RP", frac: 0.16, wideOnly: true },
          { label: "proj REM+", frac: 0.11 },
          { label: "BB%", frac: 0.08, wideOnly: true },
        ], rows: brows },
    };
  }

  // ---- sections -------------------------------------------------------------
  function renderRP2SP() {
    var rows = (DATA && DATA.rp2sp) || [];
    if (!rows.length) return empty("No RP→SP candidates yet.");
    var note = '<div class="mlbstats-note">Relievers who profile as starters. ' + gloss("RP→SP FIT", "rp_sp_fit")
      + " leads on arsenal depth (a starter needs a third pitch to survive a lineup three times), then command, "
      + "platoon-neutrality, and contact quality. This is a structural screen: the repaired backtest does not "
      + "validate the ranking of RP&rarr;SP candidates against realized WAR change, so treat the order as a "
      + "shortlist, not a forecast. Click a row for the component breakdown." + gfxChip("pal-rp2sp-gfx") + "</div>" + tierLegend("rp2sp");
    return rp2spViz() + note + candTable(sortRows(rows, RP_COLS), RP_COLS);
  }
  function renderSP2RP() {
    var rows = (DATA && DATA.sp2rp) || [];
    if (!rows.length) return empty("No SP→RP candidates yet.");
    var note = '<div class="mlbstats-note">Starters who are <b>struggling in the rotation</b> and whose stuff would play up in relief. '
      + gloss("SP→RP FIT", "sp_rp_fit") + " is relief upside GATED by conversion need: a starter succeeding in the rotation "
      + "scores low no matter how nasty his stuff is, because a good starter is worth more than a good reliever. SP ERA is "
      + "the need signal; proj REM+ is a display-only relief projection. This direction carries a validated "
      + "directional signal: in the repaired backtest, pre-conversion SP&rarr;RP FIT out-ranked every same-event "
      + "baseline against realized WAR change." + gfxChip("pal-sp2rp-gfx") + "</div>" + tierLegend("sp2rp");
    return sp2rpViz() + note + candTable(sortRows(rows, SP_COLS), SP_COLS);
  }

  function roleLine(x) {
    if (!x) return "-";
    return esc((x.gs || 0) + "GS/" + (x.g || 0) + "G")
      + '<span class="proj-dim"> ' + f1(x.ip) + "ip &middot; " + f2(x.era) + "era"
      + (x.k_pct != null ? " &middot; " + fPct(x.k_pct) + "k" : "") + "</span>";
  }
  function heldCell(h) {
    if (h.held === true) return '<span class="pal-hit">held</span>';
    if (h.held === false) return '<span class="pal-miss">reverted</span>';
    return '<span class="pal-pending">-</span>';
  }
  function successCell(h) {
    if (h.success === true) return '<span class="pal-hit">Hit</span>';
    if (h.success === false) return '<span class="pal-miss">Miss</span>';
    return '<span class="pal-pending">pending</span>';
  }
  // WAR produced by the conversion: realized bWAR before and after the switch,
  // with the delta colored (a gain reads as a hit, a drop as a miss).
  function warCell(h) {
    if (h.post_war == null && h.pre_war == null) return '<span class="pal-pending">-</span>';
    var pre = (h.pre_war == null) ? "-" : f1(h.pre_war);
    var post = (h.post_war == null) ? "-" : f1(h.post_war);
    var d = "";
    if (h.war_delta != null) {
      var cls = h.war_delta > 0 ? "pal-hit" : (h.war_delta < 0 ? "pal-miss" : "proj-dim");
      d = ' <span class="' + cls + '">' + (h.war_delta > 0 ? "+" : "") + f1(h.war_delta) + "</span>";
    }
    return '<span class="proj-dim">' + pre + " &rarr; </span>" + post + d;
  }
  // Compact arsenal shift: pitches meaningfully ADDED (leaned on) and DROPPED
  // across the conversion, from the inline before/after pitch mix. Signals the
  // "stretch out adds a third pitch / trim to two" pattern per row.
  function arsenalShiftCell(h) {
    var mix = h.pitch_mix;
    if (!mix || !mix.before || !mix.after) return '<span class="pal-pending">-</span>';
    function set(arr, thr) {
      var m = {};
      (arr || []).forEach(function (p) { if ((p.usage || 0) >= thr) m[p.pitch] = p.usage; });
      return m;
    }
    var before = set(mix.before, 0.05), after = set(mix.after, 0.10);
    var added = [], dropped = [];
    Object.keys(after).forEach(function (p) { if (before[p] == null) added.push(p); });
    Object.keys(set(mix.before, 0.10)).forEach(function (p) { if (set(mix.after, 0.05)[p] == null) dropped.push(p); });
    var out = added.map(function (p) { return '<span class="pal-hit">+' + esc(p) + "</span>"; })
      .concat(dropped.map(function (p) { return '<span class="pal-miss">-' + esc(p) + "</span>"; }));
    return out.length ? out.join(" ") : '<span class="proj-dim">same mix</span>';
  }
  function scorecard() {
    var b = (DATA && DATA.backtest) || {};
    var pd = b.per_direction || {};
    // Evidence is per direction (repaired harness): pre-FIT rank vs realized
    // WAR change within each direction. The old pooled held-role rho is a
    // retired reporting-only field and is not shown.
    function dirStat(key, label, tag) {
      var d = pd[key] || {};
      if (d.rho_prefit_vs_war_delta == null) return "";
      return '<span class="pal-sc-stat">' + label + " <b>&rho; "
        + esc(d.rho_prefit_vs_war_delta) + '</b><span class="proj-dim"> vs WAR change (n='
        + esc(d.n_war) + ") &middot; " + tag + "</span></span>";
    }
    return '<div class="pal-scorecard">'
      + '<span class="pal-sc-stat"><b>' + esc(DATA.n_conversions) + "</b> conversions</span>"
      + dirStat("SP->RP", gloss("SP→RP FIT", "sp_rp_fit"), "validated vs baselines")
      + dirStat("RP->SP", gloss("RP→SP FIT", "rp_sp_fit"), "does not validate ranking")
      + '<span class="pal-sc-stat">converters at <b>' + esc(b.converter_median_fit_pool_pctile) + "th</b> pct of the field</span>"
      + '<span class="pal-sc-note">' + esc(b.disclaimer || "") + "</span>"
      + "</div>";
  }
  function historyToggle() {
    return '<div class="mlbstats-tabs" role="tablist">'
      + '<button type="button" class="mlbstats-tab' + (historyView === "table" ? " active" : "") + '" data-histview="table">Conversions</button>'
      + '<button type="button" class="mlbstats-tab' + (historyView === "mix" ? " active" : "") + '" data-histview="mix">Pitch-mix changes</button>'
      + "</div>";
  }
  function renderHistory() {
    var rows = (DATA && DATA.history) || [];
    if (!rows.length) return empty("No conversion history yet.");
    if (historyView === "mix") return scorecard() + historyToggle() + renderMix();
    // Sortable, recency-first by default (year desc -> 2026 conversions lead).
    // Click any numeric column header to re-sort.
    rows = sortRows(rows, HISTORY_COLS);
    var head = "<thead><tr>" + HISTORY_COLS.map(function (c) {
      if (c.kind === "name" || c.sortable === false) return "<th>" + c.label + "</th>";
      return '<th data-col="' + c.key + '"' + (c.key === sortKey ? ' class="is-sorted"' : "")
        + ' tabindex="0" role="button" aria-sort="' + (c.key === sortKey ? (sortAsc ? "ascending" : "descending") : "none")
        + '">' + c.label + "</th>";
    }).join("") + "</tr></thead>";
    var body = "<tbody>" + rows.map(function (h) {
      return "<tr><td class=\"mlbstats-name\">" + logo(h.team) + nameLink(h.name, h.mlbam) + "</td>"
        + '<td><span class="pal-dir' + dirClass(h.direction) + '">' + esc((h.direction || "").replace("->", "→")) + "</span></td>"
        + "<td>" + esc(h.year) + "</td>"
        + "<td>" + roleLine(h.pre) + "</td><td>" + roleLine(h.post) + "</td>"
        + "<td>" + warCell(h) + "</td>"
        + "<td>" + arsenalShiftCell(h) + "</td>"
        + "<td>" + heldCell(h) + "</td>"
        + '<td>' + (h.pre_fit == null ? "-" : '<span class="pal-fit ' + fitClass(h.pre_fit) + '">' + f1(h.pre_fit) + "</span>") + "</td>"
        + "<td>" + successCell(h) + "</td></tr>";
    }).join("") + "</tbody>";
    var note = '<div class="mlbstats-note">Every detected SP&harr;RP switch since 2018, labeled by whether the pitcher '
      + "held the new role. WAR before and after is realized Baseball-Reference pitcher WAR in the pre-role and "
      + "post-role seasons (the value the conversion actually produced); Arsenal shift flags the pitches he added "
      + "or dropped in the move.</div>";
    return scorecard() + historyToggle() + note
      + '<div class="mlbstats-scroll"><table class="mlbstats-table">' + head + body + "</table></div>";
  }
  function renderMix() {
    var rows = (DATA && DATA.pitch_mix_changes) || [];
    if (!rows.length) return empty("No pitch-mix change data.");
    function usageBars(mix) {
      return (mix || []).map(function (p) {
        return '<div class="pal-ars-row"><span class="pal-ars-pitch">' + esc(p.pitch) + "</span>"
          + bar((p.usage || 0) * 100) + '<span class="pal-ars-meta">' + fPct(p.usage) + "</span></div>";
      }).join("");
    }
    var cards = rows.map(function (m) {
      return '<div class="pal-mix-card"><h4><span>' + logo(m.team) + nameLink(m.name, m.mlbam) + '</span><span class="pal-dir' + dirClass(m.direction) + '">'
        + esc((m.direction || "").replace("->", "→")) + " " + esc(m.year) + "</span></h4>"
        + '<div class="pal-mix-cols"><div><h4>Before</h4>' + usageBars(m.before) + "</div>"
        + '<div><h4>After</h4>' + usageBars(m.after) + "</div></div></div>";
    }).join("");
    return '<div class="mlbstats-note">What did converters change? Pitch usage before and after the switch. '
      + "A reliever stretching out often adds or leans on a third pitch; a starter moving to relief trims to his best two.</div>"
      + '<div class="pal-mix-grid">' + cards + "</div>";
  }

  function renderPitchAdd() {
    var rows = (DATA && DATA.pitch_add) || [];
    if (!rows.length) return empty("No pitch-add recommendations yet.");
    var note = '<div class="mlbstats-note">What weapon would help each conversion candidate most? The '
      + "recommendation comes from the arsenal hole (no breaking ball, no offspeed, or a thin third pitch) crossed "
      + "with the platoon weakness a starter has to survive. Sorted by " + gloss("RP→SP FIT", "rp_sp_fit") + ".</div>";
    var cards = rows.map(function (r) {
      var rec = r.rec || {};
      var arsenal = (r.arsenal || []).slice().sort(function (a, b) { return (b.usage || 0) - (a.usage || 0); })
        .map(function (p) { return esc(p.pitch) + " " + fPct(p.usage); }).join(" &middot; ");
      var pri = rec.priority === "high" ? " pal-flag--warn" : " pal-flag--good";
      return '<div class="pal-mix-card"><h4><span>' + logo(r.team) + nameLink(r.name, r.mlbam) + '<span class="proj-dim"> ' + esc(r.team)
        + '</span></span><span class="pal-fit ' + fitClass(r.fit) + '">' + f1(r.fit) + "</span></h4>"
        + '<div class="mlbstats-note" style="margin:4px 0">Current: ' + (arsenal || "-") + "</div>"
        + '<div style="margin:7px 0"><span class="pal-flag' + pri + '">ADD ' + esc(rec.add) + "</span>"
        + (rec.target ? ' <span class="proj-dim">vs ' + esc(rec.target) + "</span>" : "") + "</div>"
        + '<div style="font-size:11px;color:var(--text-secondary);line-height:1.4">' + esc(rec.reason) + "</div></div>";
    }).join("");
    return note + '<div class="pal-mix-grid">' + cards + "</div>";
  }

  function renderPlatoon() {
    var rows = (DATA && DATA.reverse_platoon) || [];
    // only meaningful splits (with a decent sample), most-reverse first
    var view = rows.filter(function (r) {
      return (r.reverse || r.extreme) && (r.min_tbf == null || r.min_tbf >= 100);
    });
    if (!view.length) return empty("No notable platoon splits yet.");
    var note = '<div class="mlbstats-note">Conventionally a pitcher is tougher on same-handed hitters. A '
      + gloss("reverse platoon split", "platoon_split") + " (tougher on the OPPOSITE hand) is a rare hidden strength that "
      + "helps him face a full lineup, a plus for RP&rarr;SP; an extreme normal split is a conversion blocker. OPS-against "
      + "by batter hand. A descriptive split, not a separately backtested model.</div>";
    var head = "<thead><tr><th>Pitcher</th><th>Throws</th><th>Role</th><th>vs own hand</th><th>vs opp hand</th>"
      + "<th>Split</th><th>Read</th></tr></thead>";
    var body = "<tbody>" + view.map(function (r) {
      var read = r.reverse ? '<span class="pal-hit">reverse (neutral+)</span>'
        : '<span class="pal-miss">extreme split</span>';
      return '<tr><td class="mlbstats-name">' + logo(r.team) + nameLink(r.name, r.mlbam) + "</td>"
        + "<td>" + esc(r.p_throws) + "HP</td><td>" + esc(r.role) + "</td>"
        + "<td>" + f3(r.own_ops) + "</td><td>" + f3(r.opp_ops) + "</td>"
        + "<td>" + f3(r.split) + "</td><td>" + read + "</td></tr>";
    }).join("") + "</tbody>";
    return note + '<div class="mlbstats-scroll"><table class="mlbstats-table">' + head + body + "</table></div>";
  }

  function renderProspects() {
    var rows = (DATA && DATA.prospect_watch) || [];
    if (!rows.length) return empty("No prospect role-mismatches yet.");
    // The bound is STATED, never silent: every number below comes from the payload's
    // own prospect_watch_rule, so the copy cannot claim a threshold the export is not
    // applying. Degrades to the old wording on a payload built before the rule shipped.
    var rule = (DATA && DATA.prospect_watch_rule) || null;
    var bound = "";
    if (rule) {
      bound = " Ranked by how far past the swing band the shape sits, and staged: only the "
        + esc(rule.n_qualified) + " of " + esc(rule.n_mismatches) + " mismatches at least "
        + f1(rule.margin_min) + " shape points past the boundary are listed"
        + (rule.cap_binding ? (", top " + esc(rule.cap) + " shown") : "")
        + ". The other " + esc(rule.n_below_margin) + " sit inside that margin"
        + (rule.best_margin_below_threshold != null
           ? " (the closest is " + f1(rule.best_margin_below_threshold) + " points past)" : "")
        + " and are kept in the payload rather than dropped.";
    }
    var note = '<div class="mlbstats-note">Prospect pitchers whose SCOUTED role may not fit their arsenal shape ('
      + gloss("arsenal depth", "arsenal_depth") + " + command, from 20-80 scout grades). A scouted starter with a thin "
      + "arsenal profiles as a reliever; a reliever with a deep arsenal could start. Shape-only: there is no pitch tracking "
      + "at the minors, so this reads role fit from tool grades, not stuff. " + esc(DATA.n_prospects || "")
      + " prospect pitchers scanned." + bound
      + " A descriptive shape screen, not a separately backtested model.</div>";
    function toolBars(tools) {
      tools = tools || {};
      return ["fb", "sl", "cb", "ch", "ct", "cmd"].filter(function (k) { return tools[k] != null; }).map(function (k) {
        return '<div class="pal-ars-row"><span class="pal-ars-pitch">' + k.toUpperCase() + "</span>"
          + bar((tools[k] - 20) / 60 * 100) + '<span class="pal-ars-meta">' + fInt(tools[k]) + "</span></div>";
      }).join("");
    }
    var cards = rows.map(function (p) {
      var pdir = p.role === "SP" ? "SP->RP" : "RP->SP";
      var arrow = p.role === "SP" ? "SP &rarr; RP" : "RP &rarr; SP";
      var msg = p.role === "SP" ? "Scouted a starter, but the arsenal profiles as a reliever."
        : "Scouted a reliever, but has the arsenal to start.";
      return '<div class="pal-mix-card"><h4><span>' + logo(p.org) + esc(p.name)
        + '<span class="proj-dim"> ' + esc(p.org || "") + "</span></span>"
        + '<span class="pal-dir' + dirClass(pdir) + '">' + arrow + "</span></h4>"
        + '<div class="mlbstats-note" style="margin:2px 0">Scouted ' + esc(p.position)
        + " &middot; FV " + (p.fvE != null ? Math.round(p.fvE) : fCeil(p.fv))
        + " &middot; shape " + f1(p.starter_shape) + " &middot; " + esc(p.arsenal_depth) + " plus pitches"
        + (p.mismatch_margin != null ? " &middot; " + f1(p.mismatch_margin) + " past the band" : "") + "</div>"
        + '<div style="margin:6px 0;font-size:11px;color:var(--text-secondary)">' + esc(msg) + "</div>"
        + toolBars(p.tools) + "</div>";
    }).join("");
    return note + '<div class="pal-mix-grid">' + cards + "</div>";
  }

  // ---- Position Fit: which hitters are worth more runs somewhere else -------
  // Value per 650 PA at position p = bat + fielding(p) + positional adjustment.
  // The bat is position-independent, so it cancels out of any comparison BETWEEN
  // positions: only fielding + the ladder decide where a hitter belongs. Every
  // number rendered here is copied off the model artifact; the section adds no
  // arithmetic of its own beyond formatting.
  var POS_ORDER = ["C", "SS", "2B", "CF", "3B", "LF", "RF", "1B", "DH"];

  // Thousands separator, so a four-digit COUNT never reads as a season year
  // ("2,023 player-seasons", not "2023 player-seasons").
  function fThou(v) {
    var n = num(v);
    return n == null ? "-" : Math.round(n).toLocaleString("en-US");
  }
  function pfSigned(v, dp) {
    var n = num(v);
    if (n == null) return "-";
    return (n > 0 ? "+" : "") + n.toFixed(dp == null ? 1 : dp);
  }
  // A gain is only worth reading against its own standard error. The model
  // reports gain_se per player; show it, never hide it.
  function pfGainCell(g, se) {
    var n = num(g);
    if (n == null) return "-";
    var cls = n >= 3 ? "pal-hit" : n <= -3 ? "pal-miss" : "";
    return '<span class="' + cls + '">' + pfSigned(n) + "</span>"
      + (se == null ? "" : '<span class="proj-dim"> &plusmn;' + f1(se) + "</span>");
  }
  // Rng+ (legs): sprint speed as a range read, on OUTFIELD destinations only.
  // The producer decides which positions qualify (payload rngMeta.shipPositions)
  // and bakes every number, including the per-destination percentile. Nothing is
  // computed here, and no position not on the whitelist ever shows a meter: at
  // shortstop the measured correlation between sprint and OAA is -0.020 and at
  // third base -0.004, so a speed meter there would be a picture of nothing.
  function pfRngShips(pos) {
    var m = (PF && PF.rngMeta) || null;
    return !!(m && m.shipPositions && m.shipPositions.indexOf(pos) >= 0);
  }
  function pfRng(r, pos) {
    if (!pfRngShips(pos)) return "";
    var g = r.rng;
    if (!g || g.plus == null) return "";
    var pct = g.pct && g.pct[pos] != null ? g.pct[pos] : null;
    var meta = (PF && PF.rngMeta) || {};
    var pool = (meta.pools && meta.pools[pos]) || null;
    var season = (meta.anchor && meta.anchor.season) || null;
    var stale = season && g.season && g.season !== season;
    var tip = "Rng+ " + g.plus + ": sprint speed " + g.fts + " ft/s on the 100 + 10z scale, "
      + "so ten points is one standard deviation of the league."
      + (pct != null && pool
          ? " That is the " + pct + ordSuffix(pct) + " percentile among "
            + pool.n + " " + pos + " incumbents (400+ innings, trailing three seasons)."
          : "")
      + " Measured against outfield range, not asserted: sprint speed tracks OAA per 1000 "
      + "innings at " + pos + " with r " + fmtR(meta.r && meta.r[pos]) + ". It reads the "
      + "outfield only. At third and short, speed and range come apart completely, so the "
      + "meter is not shown there."
      + (stale ? " Read from his " + g.season + " season; he has no " + season + " tracking yet." : "")
      + " Display only: sprint speed is not a model input, because OAA already contains the legs.";
    return ' <span class="pal-rng" title="' + esc(tip) + '">Rng+ ' + g.plus
      + (pct != null ? ' <span class="proj-dim">' + pct + ordSuffix(pct) + " pct</span>" : "")
      + (stale ? ' <span class="proj-dim">(' + g.season + ")</span>" : "") + "</span>";
  }
  function ordSuffix(n) {
    var t = n % 100;
    if (t >= 11 && t <= 13) return "th";
    return ["th", "st", "nd", "rd"][n % 10] || "th";
  }
  function fmtR(o) {
    if (!o || o.r == null) return "a measured positive value";
    return "+" + Number(o.r).toFixed(2)
      + (o.ci95 ? " (95% CI +" + Number(o.ci95[0]).toFixed(2) + " to +" + Number(o.ci95[1]).toFixed(2) + ")" : "");
  }
  function pfMoveCell(r) {
    if (!r.best || r.best === r.pos) return '<span class="proj-dim">stays at ' + esc(r.pos || "-") + "</span>";
    return esc(r.pos) + ' <span class="proj-dim">&rarr;</span> <strong>' + esc(r.best) + "</strong>";
  }
  // Per-player defensive value at every feasible position, as bars relative to
  // the best one. This is the whole model for one player on one screen.
  function pfWhyPanel(r) {
    var by = r.byPos || {};
    var keys = Object.keys(by).sort(function (a, b) { return (by[b] || 0) - (by[a] || 0); });
    if (!keys.length) return '<td colspan="20"><div class="pal-why"><div class="mlbstats-note">No per-position breakdown for this player.</div></div></td>';
    var hi = by[keys[0]], lo = by[keys[keys.length - 1]];
    var span = Math.max(1e-6, hi - lo);
    var bars = keys.map(function (k) {
      var v = by[k];
      var mark = k === r.pos ? " (current)" : k === r.best ? " (best)" : "";
      return '<div class="pal-ars-row"><span class="pal-ars-pitch">' + esc(k) + "</span>"
        + bar((v - lo) / span * 100)
        + '<span class="pal-ars-meta">' + pfSigned(v) + esc(mark) + pfRng(r, k) + "</span></div>";
    }).join("");
    var dem = (r.demPos && r.demGain != null)
      ? '<div class="mlbstats-note" style="margin:2px 0 8px">Moving DOWN the spectrum to ' + esc(r.demPos)
        + " is worth " + pfSigned(r.demGain) + " runs per 650 PA (&plusmn;" + f1(r.demSe) + "): "
        + pfSigned(r.demPlayer) + " of that is this player's own glove, " + pfSigned(r.demLeague)
        + " is the league-wide constant every hitter making that move gets. Read the player part when the total sits near the flag line.</div>"
      : "";
    return '<td colspan="20"><div class="pal-why"><div class="pal-why-grid">'
      + '<div><h4>Defensive value by position</h4>'
      + '<div class="mlbstats-note" style="margin:2px 0 8px">Runs per 650 PA, fielding plus the positional adjustment. The bat is the same everywhere and is left out.</div>'
      + bars + "</div>"
      + '<div><h4>The read</h4>' + dem
      + '<div class="mlbstats-note" style="margin:2px 0">Glove ' + pfSigned(r.gloveZ, 2)
      + " standard units (&plusmn;" + f2(r.gloveZSe) + " after shrink), worth " + pfSigned(r.gloveRuns)
      + " runs per 650 PA at " + esc(r.pos || "-") + ". Bat " + pfSigned(r.bat)
      + " runs per 650 PA versus an average hitter: it does not move the position choice, it decides whether the bottom of the spectrum is still a job.</div>"
      + "</div></div>" + pfHistory(r) + "</div></td>";
  }

  // Where he has actually PLAYED, and how much each reading is worth. The model
  // already used this evidence to fit the glove read above; showing it answers a
  // different question, which is "which spot has he been best at", and it is only
  // answerable alongside the trust column. Forty innings in right field and nine
  // hundred at first are not comparable readings even though both print an OAA,
  // and `rel` is what says so: innings/(innings + the position's own fitted
  // stabilization constant), which runs from 632 innings at centre field to 2,539
  // at first base. A high number is a settled read; a low one is a rumour.
  function pfHistory(r) {
    var h = r.hist || [];
    if (!h.length) return "";
    var rows = h.map(function (e) {
      var rel = e.rel == null ? "-" : Math.round(e.rel * 100) + "%";
      var relCls = e.rel == null ? "proj-dim" : e.rel >= 0.4 ? "" : "proj-dim";
      return "<tr><td>" + esc(String(e.season || "")) + "</td>"
        + "<td><strong>" + esc(e.pos || "-") + "</strong></td>"
        + "<td>" + fInt(e.inn) + "</td>"
        + "<td>" + (e.oaa == null ? "-" : pfSigned(e.oaa, 0)) + "</td>"
        + "<td>" + (e.frp == null ? "-" : pfSigned(e.frp, 0)) + "</td>"
        + "<td>" + (e.z == null ? "-" : pfSigned(e.z, 2)) + "</td>"
        + '<td class="' + relCls + '">' + rel + "</td></tr>";
    }).join("");
    return '<div style="margin-top:10px;"><h4>Where he has played</h4>'
      + '<div class="mlbstats-note" style="margin:2px 0 6px">Per season and position. '
      + "OAA and FRP are what the glove did; z is that rate against the position's own "
      + "difficulty, in standard units. Trust is innings against the position's fitted "
      + "stabilization constant, so the same OAA counts for more at centre field than at "
      + "first base. Read the z column next to the trust column, never alone.</div>"
      + '<div class="mlbstats-scroll"><table class="detail-table"><thead><tr>'
      + "<th>Season</th><th>Pos</th><th>Inn</th><th>OAA</th><th>FRP</th><th>z</th><th>Trust</th>"
      + "</tr></thead><tbody>" + rows + "</tbody></table></div></div>";
  }

  var POSFIT_COLS = [
    { key: "rank", label: "#", kind: "rank" },
    { key: "name", label: "Hitter", kind: "name", sortable: false },
    { key: "pos", label: "Now", cell: function (r) { return esc(r.pos || "-"); } },
    { key: "pa", label: "PA", cell: function (r) { return fInt(r.pa); } },
    { key: "move", label: "Best fit", sortable: false, cell: pfMoveCell },
    { key: "gain", label: "Gain (runs/650)", desc: true, cell: function (r) { return pfGainCell(r.gain, r.gainSe); } },
    { key: "demPos", label: "Move down to", sortable: false, cell: function (r) { return r.demPos ? esc(r.demPos) : '<span class="proj-dim">-</span>'; } },
    { key: "demGain", label: "Demotion gain", desc: true, cell: function (r) { return pfGainCell(r.demGain, r.demSe); } },
    { key: "gloveZ", label: "Glove z", desc: true, cell: function (r) { return pfSigned(r.gloveZ, 2); } },
    { key: "bat", label: "Bat (runs/650)", desc: true, cell: function (r) { return pfSigned(r.bat); } },
  ];

  function pfSortedRows(rows) {
    var col = null;
    POSFIT_COLS.forEach(function (c) { if (c.key === sortKey) col = c; });
    var key = (col && !col.kind) ? col.key : "gain";
    var out = rows.slice();
    out.sort(function (a, b) {
      var x = num(a[key]), y = num(b[key]);
      if (x == null && y == null) return 0;
      if (x == null) return 1;          // missing always sinks
      if (y == null) return -1;
      return sortAsc ? x - y : y - x;
    });
    return out;
  }

  function pfTable(rows) {
    var head = "<thead><tr>";
    POSFIT_COLS.forEach(function (c) {
      var sortable = c.kind !== "rank" && c.kind !== "name" && c.sortable !== false;
      var sorted = c.key === sortKey ? " is-sorted" : "";
      var attrs = sortable
        ? ' data-col="' + c.key + '" tabindex="0" role="button" aria-sort="'
          + (c.key === sortKey ? (sortAsc ? "ascending" : "descending") : "none") + '"'
        : "";
      head += '<th class="mlbstats-col-' + c.key + sorted + '"' + attrs + '>' + esc(c.label) + "</th>";
    });
    head += "</tr></thead>";
    var body = "<tbody>";
    rows.forEach(function (r, i) {
      var open = (openRow === r.mlbam);
      body += "<tr" + (open ? ' class="is-open"' : "") + ' data-open="' + r.mlbam
        + '" tabindex="0" aria-expanded="' + (open ? "true" : "false") + '">';
      POSFIT_COLS.forEach(function (c) {
        if (c.kind === "rank") { body += "<td>" + (i + 1) + "</td>"; return; }
        if (c.kind === "name") {
          body += '<td class="mlbstats-name pal-expand">' + logo(r.team) + nameLink(r.name, r.mlbam)
            + '<span class="proj-dim"> ' + esc(r.team || "") + "</span>"
            + (r.misplaced ? ' <span class="pal-flag pal-flag--good">MISPLACED</span>' : "")
            + (r.demoted ? ' <span class="pal-flag pal-flag--warn">MOVE DOWN</span>' : "") + "</td>";
          return;
        }
        body += "<td>" + c.cell(r) + "</td>";
      });
      body += "</tr>";
      if (open) body += '<tr class="pal-why-tr">' + pfWhyPanel(r) + "</tr>";
    });
    body += "</tbody>";
    return '<div class="mlbstats-scroll"><table class="mlbstats-table">' + head + body + "</table></div>";
  }

  // The fitted ladder against the folklore table it replaces. This is the piece
  // of the model with the tightest evidence (R2 0.9779 on 9,101 player-seasons)
  // and it is worth showing on its own.
  function pfLadder() {
    var L = (PF && PF.ladder) || {};
    var vals = L.values || {}, ci = L.ci95 || {}, folk = L.folklore || {};
    var rows = POS_ORDER.filter(function (p) { return vals[p] != null; }).map(function (p) {
      var d = (folk[p] != null) ? vals[p] - folk[p] : null;
      var c = ci[p];
      return "<tr><td><strong>" + esc(p) + "</strong></td>"
        + "<td>" + pfSigned(vals[p], 2) + "</td>"
        + "<td>" + (c ? '<span class="proj-dim">' + pfSigned(c[0], 2) + " to " + pfSigned(c[1], 2) + "</span>" : "-") + "</td>"
        + "<td>" + (folk[p] != null ? pfSigned(folk[p], 1) : "-") + "</td>"
        + "<td>" + (d == null ? "-" : '<span class="' + (Math.abs(d) >= 1.5 ? "pal-hit" : "") + '">' + pfSigned(d, 2) + "</span>") + "</td></tr>";
    }).join("");
    var note = '<div class="mlbstats-note">The positional adjustment, re-estimated from Baseball-Reference&rsquo;s own '
      + "construction rather than taken from the folklore table: least squares of positional runs per 650 PA on innings "
      + "shares, no intercept, " + fThou(L.nPlayerSeasons) + " player-seasons from " + esc((L.seasons || [])[0])
      + " to " + esc((L.seasons || [])[1]) + " at " + fInt(L.minPa) + "+ PA. R&sup2; " + (L.r2 == null ? "-" : f1(L.r2 * 100) + "%")
      + ", residual SD " + f2(L.residSd) + " runs. This is an INVERSION: it recovers the constants Baseball-Reference "
      + "themselves used, so a rung reads as what BRef prices that position at, not as an independent measure of how "
      + "hard it is to play. The folklore column is the table everyone quotes; the difference column is "
      + "where it is wrong.</div>";
    // WHICH SUM IS ZERO. The column does not sum to zero and is not supposed
    // to, which reads as an error every time someone checks - so the page now
    // says so instead of leaving it to be rediscovered. Only rendered when the
    // artifact carries the identification block (added 2026-07-31); older
    // artifacts get the table with no claim attached rather than a wrong one.
    var id = L.identification || null;
    var sums = "";
    if (id && id.sum_exposure_weighted != null) {
      var wDH = ((id.exposure_share || {}).DH != null)
        ? f1(100 * id.exposure_share.DH) + "%" : "about 7%";
      sums = '<div class="mlbstats-note"><strong>Why the column does not add to zero.</strong> '
        + "The identity is a weighted one: the adjustment is centred so that the league&rsquo;s "
        + "own deployment averages zero, and that sum is <strong>" + f2(id.sum_exposure_weighted)
        + "</strong> here, imposed by construction. Adding the nine rungs with EQUAL weight gives "
        + f2(id.sum_equal_weight_9) + ", which is not an error: it weights DH like a fielding "
        + "position when DH is " + wDH + " of league exposure, so the large negative DH rung gets "
        + "counted nine times too heavily. With the weighted sum pinned at zero, the eight fielding "
        + "rungs are then forced to " + f2(id.sum_equal_weight_fielders) + ". Only the weighted sum "
        + "is a constraint; the other two are consequences of it.</div>";
    }
    return note + '<div class="mlbstats-scroll"><table class="mlbstats-table">'
      + "<thead><tr><th>Pos</th><th>Fitted (runs/650)</th><th>95% CI</th><th>Folklore</th><th>Difference</th></tr></thead>"
      + "<tbody>" + rows + "</tbody></table></div>" + sums + pfMethod();
  }

  // Honest accounting. Two DIFFERENT questions were measured and they got two
  // different answers; both are printed, and the failing one is not softened.
  function pfMethod() {
    var A = (PF && PF.accuracy) || {}, D = (PF && PF.demotionNull) || {};
    var mae = A.mae || {}, adv = (A.advantage || {}).carry_over || {}, auc = D.auc || {};
    var ci = adv.ci95 || [];
    var pass = '<div class="pal-mix-card"><h4><span>What the model does predict</span>'
      + '<span class="pal-dir pal-dir--pass">VALIDATED</span></h4>'
      + '<div class="mlbstats-note" style="margin:4px 0">The SIZE of a move. Out of sample on '
      + fInt(A.nConversions) + " real position changes (" + fInt(A.minInningsEachSide)
      + "+ innings on each side), mean absolute error " + f2(mae.model) + " runs per 650 PA against "
      + f2(mae.carry_over) + " for carrying the old rate over, " + f2(mae.league_avg) + " for league average and "
      + f2(mae.permuted) + " for a row-permuted twin of the same column. The paired advantage over carry-over is "
      + f2(adv.mean) + " runs, 95% CI " + f2(ci[0]) + " to " + f2(ci[1]) + ", against a permutation null band of "
      + f2(A.permNull95) + ". Positive in " + esc(A.seasonAdvantagePositiveIn || "-") + " season splits.</div></div>";
    var fail = '<div class="pal-mix-card"><h4><span>What it does NOT predict</span>'
      + '<span class="pal-dir pal-dir--null">MEASURED NULL</span></h4>'
      + '<div class="mlbstats-note" style="margin:4px 0">WHICH players clubs actually demote. Scored on '
      + fThou(D.nScored) + " player-seasons (" + fPct(D.baseRate) + " of them moved down the next year), the model ranks "
      + "demotions at AUC " + f2(auc.model) + ". A coin flip is 0.50, the permutation band on AUC minus a half is "
      + f2(D.permNull95) + ", and RAW single-season OAA on its own ranks them at " + f2(auc.raw_oaa)
      + " - better than the model. Read this list as valuation, not as prediction: it says what a move would be WORTH, "
      + "not that anyone is about to make it.</div></div>";
    var up = D.promotionSide || {};
    var nuance = (up.auc_model_up != null)
      ? '<div class="pal-mix-card"><h4><span>The asymmetry</span></h4>'
        + '<div class="mlbstats-note" style="margin:4px 0">The same score ranks moves UP the spectrum at AUC '
        + f2(up.auc_model_up) + " over " + fInt(up.n_moved_up) + " promotions, against " + f2(up.auc_control_up)
        + " for its zero-information control. A promotion needs a good glove AND an open job, and the glove part is "
        + "clearly readable; a demotion is a club decision driven by things this model never sees.</div></div>"
      : "";
    var caveats = ((PF && PF.caveats) || []).map(function (c) {
      return "<li>" + esc(c) + "</li>";
    }).join("");
    var oos = ((PF && PF.outOfScope) || []).join(", ");
    return '<div class="pal-mix-grid" style="margin-top:14px">' + pass + fail + nuance + "</div>"
      + (caveats ? '<details class="fa-valmap" style="margin-top:12px"><summary>Limits the model states about itself</summary>'
        + '<ul class="mlbstats-note" style="margin:8px 0 0 18px;list-style:disc">' + caveats + "</ul>"
        + (oos ? '<div class="mlbstats-note" style="margin-top:8px">Out of scope: ' + esc(oos)
          + ". Savant publishes no OAA at catcher in any season, so catchers are carried in the payload "
          + "and never offered a move; pitchers are not scored at all.</div>" : "")
        + "</details>" : "");
  }

  function renderPosFit() {
    if (PF_ERROR) {
      return '<div class="mlbstats-empty pal-load-error" role="alert">The position-fit model failed to load. '
        + 'Refresh to retry. <button type="button" class="chip" id="pf-retry">Retry</button></div>';
    }
    if (!PF) return empty("Loading the position-fit model…");
    var all = PF.rows || [];
    if (!all.length) return empty("No qualified hitters in the position-fit model yet.");
    var tabs = [["misplaced", "Misplaced hitters"], ["down", "Move down the spectrum"],
                ["board", "Every qualified hitter"], ["ladder", "The positional ladder"]]
      .map(function (t) {
        return '<button type="button" class="mlbstats-tab' + (posfitView === t[0] ? " active" : "")
          + '" data-pfview="' + t[0] + '" role="tab" aria-selected="' + (posfitView === t[0]) + '">'
          + esc(t[1]) + "</button>";
      }).join("");
    var nav = '<div class="mlbstats-tabs" role="tablist" aria-label="Position Fit views">' + tabs + "</div>";
    if (posfitView === "ladder") return nav + pfLadder();

    var rows = posfitView === "misplaced" ? all.filter(function (r) { return r.misplaced; })
      : posfitView === "down" ? all.filter(function (r) { return r.demoted; })
      : all;
    var fr = PF.flagRule || {};
    var lead = posfitView === "misplaced"
      ? "Hitters whose best defensive home is not where they are playing. Flagged at " + f1(fr.min_gain_runs_per_650)
        + "+ runs per 650 PA of gain AND at least " + f1(fr.min_sigma)
        + " standard error of it, so a big number with a big error bar does not make the list. "
        + fInt(PF.nFlagged) + " of " + fInt(PF.nQualified) + " qualified hitters."
      : posfitView === "down"
      ? "The Arozarena question: hitters who would GAIN runs by moving down the defensive spectrum, "
        + "the corner outfielder who belongs at first base or designated hitter. " + fInt(PF.nFlaggedDemotion)
        + " qualified hitters clear the same bar on a downward move. Part of every corner-outfield-to-first-base "
        + "gain is a league-wide constant rather than anything about the player; the expanded row splits the two."
      : "Every qualified hitter the model scores, sorted by the gain at his best position. Click any row for the "
        + "per-position breakdown. Qualification is " + fInt(fr.headline_min_pa) + "+ PA and "
        + fInt(fr.headline_min_innings) + "+ defensive innings.";
    var note = '<div class="mlbstats-note">' + esc(lead)
      + " Runs per 650 PA, " + esc(PF.season || "") + " season. Value identity: " + esc(PF.valueIdentity || "")
      + ". The gain says what a move would be worth, NOT that a club is about to make it - the prediction side of "
      + "that question measured as a null and is written up under The positional ladder.</div>";
    if (!rows.length) return nav + note + empty("No hitters clear the flag in this view.");
    return nav + note + pfTable(pfSortedRows(rows));
  }

  function loadPosFit() {
    if (PF || PF_LOADING) return;
    PF_LOADING = true;
    PF_ERROR = false;
    fetch(POSFIT_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { PF = j; PF_LOADING = false; render(); })
      .catch(function () { PF = null; PF_LOADING = false; PF_ERROR = true; render(); });
  }

  // ---- shell ----------------------------------------------------------------
  function render() {
    var root = document.getElementById("pal-app-root");
    if (!root) return;
    // Position Fit rides its own payload, so it must not wait on pal.json (and
    // must still paint if the pitcher sidecar is missing).
    if (section === "posfit") {
      root.innerHTML = renderPosFit();
      var pfBanner = document.getElementById("pal-banner");
      if (pfBanner) pfBanner.innerHTML = PF
        ? '<div class="mlbstats-note">Season ' + esc(PF.season || "") + " &middot; " + esc(PF.model || "")
          + " &middot; a valuation, not a prediction: the conversion matrix is validated out of sample for the SIZE "
          + "of a move, and predicting which players get moved down measured as a null.</div>"
        : "";
      bindTable(root);
      wireGlossary(root);
      return;
    }
    if (!DATA) {
      root.innerHTML = LOAD_ERROR
        ? '<div class="mlbstats-empty pal-load-error" role="alert">Data failed to load. Refresh to retry; '
          + 'if it persists the nightly build is mid-run. '
          + '<button type="button" class="chip" id="pal-retry">Retry</button></div>'
        : empty("The Alchemy Lab conversion models are being computed from Statcast. Check back shortly.");
      var retry = document.getElementById("pal-retry");
      if (retry) retry.addEventListener("click", function () {
        root.innerHTML = empty("Loading…");
        load();
      });
      return;
    }
    root.innerHTML = (section === "sp2rp") ? renderSP2RP() : (section === "history") ? renderHistory()
      : (section === "pitchadd") ? renderPitchAdd() : (section === "platoon") ? renderPlatoon()
      : (section === "prospects") ? renderProspects() : renderRP2SP();
    var banner = document.getElementById("pal-banner");
    if (banner) banner.innerHTML = DATA.season
      ? '<div class="mlbstats-note">Season ' + esc(DATA.season) + ' &middot; a candidate screen, not a projection. '
        + 'Backtest evidence is per direction: SP&rarr;RP validated, RP&rarr;SP structural screen only. '
        + esc((DATA.verdict && DATA.verdict !== "validated") ? "[" + DATA.verdict + "]" : "") + "</div>" : "";
    bindTable(root);
    wireGlossary(root);
  }

  function bindTable(root) {
    bindCollapse(root);
    root.querySelectorAll("[data-open]").forEach(function (tr) {
      function toggleRow() {
        var id = Number(tr.getAttribute("data-open"));
        openRow = (openRow === id) ? null : id;
        render();
        // re-render replaces the rows: put keyboard focus back on this one
        var again = root.querySelector('tr[data-open="' + id + '"]');
        if (again) again.focus();
      }
      tr.addEventListener("click", function (e) {
        if (e.target.closest("th")) return;
        if (e.target.closest("a")) return;   // let name links navigate, don't toggle the row
        toggleRow();
      });
      tr.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        if (e.target.closest("a")) return;   // Enter on a focused name link should navigate
        e.preventDefault();
        toggleRow();
      });
    });
    root.querySelectorAll(".mlbstats-table th[data-col]").forEach(function (th) {
      function sortBy() {
        var key = th.getAttribute("data-col");
        var cols = (section === "sp2rp") ? SP_COLS : (section === "history") ? HISTORY_COLS
          : (section === "posfit") ? POSFIT_COLS : RP_COLS;
        var col = null; cols.forEach(function (c) { if (c.key === key) col = c; });
        if (!col || col.kind === "rank" || col.kind === "name" || col.sortable === false) return;
        if (sortKey === key) sortAsc = !sortAsc;
        else { sortKey = key; sortAsc = !!col.asc; }
        render();
        // restore focus to the same header after the table is rebuilt
        var again = root.querySelector('.mlbstats-table th[data-col="' + key + '"]');
        if (again) again.focus();
      }
      th.addEventListener("click", function (e) {
        e.stopPropagation();
        sortBy();
      });
      th.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();
        e.stopPropagation();
        sortBy();
      });
    });
    root.querySelectorAll("[data-histview]").forEach(function (b) {
      b.addEventListener("click", function () { historyView = b.getAttribute("data-histview"); render(); });
    });
    root.querySelectorAll("[data-pfview]").forEach(function (b) {
      b.addEventListener("click", function () {
        posfitView = b.getAttribute("data-pfview");
        openRow = null;
        try { history.replaceState(null, "", "#posfit=" + posfitView); } catch (e) { /* hash optional */ }
        render();
      });
    });
    var pfRetry = root.querySelector("#pf-retry");
    if (pfRetry) pfRetry.addEventListener("click", function () { PF_ERROR = false; render(); loadPosFit(); });
    // Generate GFX chips - build the spec from the CURRENT sort at click time so
    // the graphic matches the on-screen order (fa.js/projections.js pattern).
    var rpGfx = root.querySelector("#pal-rp2sp-gfx");
    if (rpGfx) rpGfx.addEventListener("click", function () {
      if (window.EEPHUS_GFX) EEPHUS_GFX.open(rp2spBoardSpec());
    });
    var spGfx = root.querySelector("#pal-sp2rp-gfx");
    if (spGfx) spGfx.addEventListener("click", function () {
      if (window.EEPHUS_GFX) EEPHUS_GFX.open(sp2rpBoardSpec());
    });
  }

  function setSection(s) {
    section = s;
    openRow = null;
    // History defaults to year-desc (recency); the candidate tables to FIT-desc;
    // Position Fit to the gain at the best position, biggest first.
    sortKey = (s === "history") ? "year" : (s === "posfit") ? "gain" : "fit";
    sortAsc = false;
    if (s === "posfit") loadPosFit();
    document.querySelectorAll("[data-palsection]").forEach(function (x) {
      var on = x.getAttribute("data-palsection") === s;
      x.classList.toggle("active", on);
      x.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function bindSectionNav() {
    document.querySelectorAll("[data-palsection]").forEach(function (b) {
      b.addEventListener("click", function () {
        setSection(b.getAttribute("data-palsection"));
        try { history.replaceState(null, "", "#" + section); } catch (e) { }
        render();
      });
    });
  }

  function readHash() {
    var h = location.hash || "";
    var m = /^#(rp2sp|sp2rp|posfit|history|pitchadd|platoon|prospects)/.exec(h);
    if (m) setSection(m[1]);
    var v = /^#posfit=(misplaced|down|board|ladder)/.exec(h);
    if (v) { setSection("posfit"); posfitView = v[1]; }
  }

  // Loader with a visible failure mode: a non-OK response or a network error
  // sets LOAD_ERROR so render() paints the error state (with a Retry button)
  // instead of a blank/"computing" page.
  function load() {
    LOAD_ERROR = false;
    fetch(DATA_URL, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (j) { DATA = j; render(); })
      .catch(function () { DATA = null; LOAD_ERROR = true; render(); });
  }

  function init() {
    bindSectionNav();
    readHash();
    loadLinks();
    load();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
