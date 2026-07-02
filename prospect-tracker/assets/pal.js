/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io - Pitcher Alchemy Lab (PAL)
// =============================================================================
// Renders data/pal.json (pal_export.py) into three sections:
//   rp2sp   - relievers who profile as starters (RP->SP FIT, arsenal depth,
//             command, platoon-neutrality, role-adjusted velocity)
//   sp2rp   - starters whose stuff would play up in relief (SP->RP FIT, putaway
//             pitch, projected relief velo + REM+)
//   history - a validated archive of past SP<->RP switches (the model's backtest
//             set) with a scorecard, plus a pitch-mix before/after view
// The FIT scores are a candidate SCREEN, not a success probability - the score
// is anchored on the role-structural arsenal-depth signal; the backtest is a
// directional sign-check on a small, selection-biased sample.
(function () {
  "use strict";

  var DATA_URL = "/data/pal.json";
  var DATA = null;
  var LOAD_ERROR = false;    // fetch failed / non-OK (distinct from "not exported yet")
  var section = "rp2sp";     // rp2sp | sp2rp | history
  var historyView = "table"; // table | mix
  var sortKey = "fit";
  var sortAsc = false;
  var openRow = null;

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
  function f1(v) { var n = num(v); return n == null ? "-" : n.toFixed(1); }
  function f2(v) { var n = num(v); return n == null ? "-" : n.toFixed(2); }
  function fPct(v) { var n = num(v); return n == null ? "-" : (n * 100).toFixed(1) + "%"; }
  function f3(v) { var n = num(v); return n == null ? "-" : n.toFixed(3); }
  function gloss(label, term) { return '<span class="g-term" data-gl="' + esc(term) + '">' + esc(label) + "</span>"; }
  function wireGlossary(el) { try { if (window.EEPHUS_GL && EEPHUS_GL.wire) EEPHUS_GL.wire(el); } catch (e) { } }
  function logo(team) { try { return (window.EEPHUS_HUB && EEPHUS_HUB.teamLogo) ? EEPHUS_HUB.teamLogo(team) : ""; } catch (e) { return ""; } }
  function chart(fn, arg, opts) { try { return (window.EEPHUS_HUB && EEPHUS_HUB[fn]) ? EEPHUS_HUB[fn](arg, opts) : ""; } catch (e) { return ""; } }
  function vizWrap(title, svg) {
    return svg ? '<div class="mlbstats-viz"><div class="mlbstats-viz-cell"><div class="mlbstats-viz-h">' + title + "</div>" + svg + "</div></div>" : "";
  }
  function rp2spViz() {
    var rows = (DATA && DATA.rp2sp) || [];
    if (rows.length < 12) return "";
    var hist = chart("histogram", rows.map(function (r) { return r.fit; }),
      { height: 100, min: 0, max: 100, highlightAbove: 70, refs: [{ at: 60, label: "starter shape" }], aria: "RP-SP FIT distribution" });
    return vizWrap(gloss("RP→SP FIT", "rp_sp_fit") + ' distribution <span class="proj-dim">(cyan = 70+, a real starter profile)</span>', hist);
  }
  function sp2rpViz() {
    var rows = (DATA && DATA.sp2rp) || [];
    var pts = rows.filter(function (r) { return r.relief_upside != null && r.components && r.components.conversion_need != null; })
      .map(function (r) {
        return { x: r.relief_upside, y: r.components.conversion_need,
                 label: r.name + "  upside " + r.relief_upside + "  need " + r.components.conversion_need + "  FIT " + r.fit,
                 color: r.fit >= 55 ? null : "#6a6f7a" };
      });
    if (pts.length < 8) return "";
    var sc = chart("scatter", pts, { height: 270, xMin: 0, xMax: 100, yMin: 0, yMax: 100,
      xLabel: "relief upside →", yLabel: "↑ conversion need", xRef: 50, yRef: 50, aria: "upside vs need" });
    return vizWrap('The conversion sweet spot <span class="proj-dim">(top-right = good stuff AND struggling as a starter)</span>', sc);
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
      var sorted = c.key === sortKey ? " is-sorted" : "";
      var lbl = c.term ? gloss(c.label, c.term) : esc(c.label);
      head += '<th class="mlbstats-col-' + c.key + sorted + '" data-col="' + c.key + '">' + lbl + "</th>";
    });
    head += "</tr></thead>";
    var body = "<tbody>";
    rows.forEach(function (r, i) {
      var open = (openRow === r.mlbam);
      body += "<tr" + (open ? " class=\"is-open\"" : "") + " data-open=\"" + r.mlbam + "\">";
      cols.forEach(function (c) {
        if (c.kind === "rank") { body += "<td>" + (i + 1) + "</td>"; return; }
        if (c.kind === "name") {
          body += '<td class="mlbstats-name pal-expand">' + logo(r.team) + esc(r.name || "-")
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
    { key: "fit", label: "RP→SP FIT", term: "rp_sp_fit", desc: true, cell: function (r) { return fitCell(r.fit, "rp_sp_fit"); } },
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
    { key: "fit", label: "SP→RP FIT", term: "sp_rp_fit", desc: true, cell: function (r) { return fitCell(r.fit, "sp_rp_fit"); } },
    { key: "starter_era", label: "SP ERA", cell: function (r) { return f2(r.starter_era); }, asc: true },
    { key: "relief_upside", label: "Relief upside", cell: function (r) { return f1(r.relief_upside); } },
    { key: "best_whiff", label: "Putaway", term: "putaway_pitch", cell: function (r) { return fPct(r.best_whiff); } },
    { key: "proj_velo", label: "velo→RP", term: "role_velo_delta", cell: function (r) { return veloCell(r); } },
    { key: "proj_relief_rem_plus", label: "proj REM+", term: "rem_plus", cell: function (r) { return r.proj_relief_rem_plus == null ? "-" : '<span class="rem-plus ' + remClass(r.proj_relief_rem_plus) + '">' + fInt(r.proj_relief_rem_plus) + "</span>"; } },
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
      va = (va == null || isNaN(va)) ? -Infinity : Number(va);
      vb = (vb == null || isNaN(vb)) ? -Infinity : Number(vb);
      return sortAsc ? va - vb : vb - va;
    });
    return out;
  }

  // ---- sections -------------------------------------------------------------
  function renderRP2SP() {
    var rows = (DATA && DATA.rp2sp) || [];
    if (!rows.length) return empty("No RP→SP candidates yet.");
    var note = '<div class="mlbstats-note">Relievers who profile as starters. ' + gloss("RP→SP FIT", "rp_sp_fit")
      + " leads on arsenal depth (a starter needs a third pitch to survive a lineup three times), then command, "
      + "platoon-neutrality, and contact quality. Click a row for the component breakdown.</div>";
    return rp2spViz() + note + candTable(sortRows(rows, RP_COLS), RP_COLS);
  }
  function renderSP2RP() {
    var rows = (DATA && DATA.sp2rp) || [];
    if (!rows.length) return empty("No SP→RP candidates yet.");
    var note = '<div class="mlbstats-note">Starters who are <b>struggling in the rotation</b> and whose stuff would play up in relief. '
      + gloss("SP→RP FIT", "sp_rp_fit") + " is relief upside GATED by conversion need: a starter succeeding in the rotation "
      + "scores low no matter how nasty his stuff is, because a good starter is worth more than a good reliever. SP ERA is "
      + "the need signal; proj REM+ is a display-only relief projection.</div>";
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
  function scorecard() {
    var b = (DATA && DATA.backtest) || {};
    return '<div class="pal-scorecard">'
      + '<span class="pal-sc-stat"><b>' + esc(DATA.n_conversions) + "</b> conversions</span>"
      + '<span class="pal-sc-stat">' + gloss("pre-FIT vs held", "pal_conversion") + " <b>&rho; "
      + (b.spearman_prefit_vs_held == null ? "-" : b.spearman_prefit_vs_held) + "</b><span class=\"proj-dim\"> (n=" + esc(b.n_labeled) + ")</span></span>"
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
    // labeled conversions (the model's evidence) lead; then the newest pending ones
    rows = rows.slice().sort(function (a, b) {
      var la = a.success == null ? 1 : 0, lb = b.success == null ? 1 : 0;
      return la - lb || b.year - a.year || (b.pre_fit || 0) - (a.pre_fit || 0);
    });
    var head = "<thead><tr><th>Pitcher</th><th>Conversion</th><th>Year</th><th>Before</th><th>After</th>"
      + "<th>Held role</th><th>pre-FIT</th><th>Result</th></tr></thead>";
    var body = "<tbody>" + rows.map(function (h) {
      return "<tr><td class=\"mlbstats-name\">" + logo(h.team) + esc(h.name || "-") + "</td>"
        + '<td><span class="pal-dir">' + esc((h.direction || "").replace("->", "→")) + "</span></td>"
        + "<td>" + esc(h.year) + "</td>"
        + "<td>" + roleLine(h.pre) + "</td><td>" + roleLine(h.post) + "</td>"
        + "<td>" + heldCell(h) + "</td>"
        + '<td>' + (h.pre_fit == null ? "-" : '<span class="pal-fit ' + fitClass(h.pre_fit) + '">' + f1(h.pre_fit) + "</span>") + "</td>"
        + "<td>" + successCell(h) + "</td></tr>";
    }).join("") + "</tbody>";
    return scorecard() + historyToggle()
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
      return '<div class="pal-mix-card"><h4><span>' + logo(m.team) + esc(m.name) + '</span><span class="pal-dir">'
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
      return '<div class="pal-mix-card"><h4><span>' + logo(r.team) + esc(r.name) + '<span class="proj-dim"> ' + esc(r.team)
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
      return '<tr><td class="mlbstats-name">' + logo(r.team) + esc(r.name) + "</td>"
        + "<td>" + esc(r.p_throws) + "HP</td><td>" + esc(r.role) + "</td>"
        + "<td>" + f3(r.own_ops) + "</td><td>" + f3(r.opp_ops) + "</td>"
        + "<td>" + f3(r.split) + "</td><td>" + read + "</td></tr>";
    }).join("") + "</tbody>";
    return note + '<div class="mlbstats-scroll"><table class="mlbstats-table">' + head + body + "</table></div>";
  }

  function renderProspects() {
    var rows = (DATA && DATA.prospect_watch) || [];
    if (!rows.length) return empty("No prospect role-mismatches yet.");
    var note = '<div class="mlbstats-note">Prospect pitchers whose SCOUTED role may not fit their arsenal shape ('
      + gloss("arsenal depth", "arsenal_depth") + " + command, from 20-80 scout grades). A scouted starter with a thin "
      + "arsenal profiles as a reliever; a reliever with a deep arsenal could start. Shape-only: there is no pitch tracking "
      + "at the minors, so this reads role fit from tool grades, not stuff. " + esc(DATA.n_prospects || "")
      + " prospect pitchers scanned. A descriptive shape screen, not a separately backtested model.</div>";
    function toolBars(tools) {
      tools = tools || {};
      return ["fb", "sl", "cb", "ch", "ct", "cmd"].filter(function (k) { return tools[k] != null; }).map(function (k) {
        return '<div class="pal-ars-row"><span class="pal-ars-pitch">' + k.toUpperCase() + "</span>"
          + bar((tools[k] - 20) / 60 * 100) + '<span class="pal-ars-meta">' + fInt(tools[k]) + "</span></div>";
      }).join("");
    }
    var cards = rows.map(function (p) {
      var arrow = p.role === "SP" ? "SP &rarr; RP" : "RP &rarr; SP";
      var msg = p.role === "SP" ? "Scouted a starter, but the arsenal profiles as a reliever."
        : "Scouted a reliever, but has the arsenal to start.";
      return '<div class="pal-mix-card"><h4><span>' + logo(p.org) + esc(p.name)
        + '<span class="proj-dim"> ' + esc(p.org || "") + "</span></span>"
        + '<span class="pal-dir">' + arrow + "</span></h4>"
        + '<div class="mlbstats-note" style="margin:2px 0">Scouted ' + esc(p.position) + " &middot; FV " + fInt(p.fv)
        + " &middot; shape " + f1(p.starter_shape) + " &middot; " + esc(p.arsenal_depth) + " plus pitches</div>"
        + '<div style="margin:6px 0;font-size:11px;color:var(--text-secondary)">' + esc(msg) + "</div>"
        + toolBars(p.tools) + "</div>";
    }).join("");
    return note + '<div class="pal-mix-grid">' + cards + "</div>";
  }

  // ---- shell ----------------------------------------------------------------
  function render() {
    var root = document.getElementById("pal-app-root");
    if (!root) return;
    if (!DATA) {
      root.innerHTML = LOAD_ERROR
        ? '<div class="mlbstats-empty pal-load-error" role="alert">Data failed to load. Refresh to retry; '
          + 'if it persists the nightly build is mid-run. '
          + '<button type="button" class="chip" id="pal-retry">Retry</button></div>'
        : empty("The Pitcher Alchemy Lab conversion models are being computed from Statcast. Check back shortly.");
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
        + esc((DATA.verdict && DATA.verdict !== "validated") ? "[" + DATA.verdict + "]" : "") + "</div>" : "";
    bindTable(root);
    wireGlossary(root);
  }

  function bindTable(root) {
    root.querySelectorAll("[data-open]").forEach(function (tr) {
      tr.addEventListener("click", function (e) {
        if (e.target.closest("th")) return;
        var id = Number(tr.getAttribute("data-open"));
        openRow = (openRow === id) ? null : id;
        render();
      });
    });
    root.querySelectorAll(".mlbstats-table th[data-col]").forEach(function (th) {
      th.addEventListener("click", function (e) {
        e.stopPropagation();
        var key = th.getAttribute("data-col");
        var cols = (section === "sp2rp") ? SP_COLS : RP_COLS;
        var col = null; cols.forEach(function (c) { if (c.key === key) col = c; });
        if (!col || col.kind === "rank" || col.kind === "name") return;
        if (sortKey === key) sortAsc = !sortAsc;
        else { sortKey = key; sortAsc = !!col.asc; }
        render();
      });
    });
    root.querySelectorAll("[data-histview]").forEach(function (b) {
      b.addEventListener("click", function () { historyView = b.getAttribute("data-histview"); render(); });
    });
  }

  function setSection(s) {
    section = s;
    openRow = null;
    sortKey = "fit"; sortAsc = false;
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
    var m = /^#(rp2sp|sp2rp|history|pitchadd|platoon|prospects)/.exec(location.hash || "");
    if (m) setSection(m[1]);
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
    load();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
