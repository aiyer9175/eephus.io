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
// evidence is PER DIRECTION and every validity word on this page is DERIVED
// from data/pal.json, never written here: backtest.gate carries the
// pre-registered per-direction verdict (with the WAR series IT was measured on)
// and backtest.per_direction carries the live rho (on the series
// backtest.war_basis stamps). A payload without those blocks makes the page say
// the measurement is unavailable; it never asserts a verdict by default and it
// never promotes the sign of a rho to one. Fixed 2026-09-06: the scorecard used
// to print "validated vs baselines" and "does not validate ranking" as literal
// strings, so it kept reporting the bWAR-era gate after the WAR series under
// the live numbers changed to eWAR v2. The retired pooled rho is
// reporting-only and never cited here.
(function () {
  "use strict";

  // PAYLOAD FILES (QREP10, 2026-10-08). The core carries every rule, verdict
  // and backtest block and no rows; each pitcher tab's rows ride their own
  // file, fetched the first time the tab opens. The whole artifact is read
  // only when a split file cannot be had (a deploy that predates the split).
  var CORE_URL = "/data/pal_core.json";
  var FULL_URL = "/data/pal.json";
  var BLOCK_URL = {
    rp2sp: "/data/pal_rp2sp.json",
    sp2rp: "/data/pal_sp2rp.json",
    history: "/data/pal_history.json",
    pitchadd: "/data/pal_pitch_add.json",
    platoon: "/data/pal_reverse_platoon.json",
    prospects: "/data/pal_prospect_watch.json"
  };
  // the payload keys each section reads off its row file
  var BLOCK_KEYS = {
    rp2sp: ["rp2sp"], sp2rp: ["sp2rp"], history: ["history", "pitch_mix_changes"],
    pitchadd: ["pitch_add"], platoon: ["reverse_platoon"], prospects: ["prospect_watch"]
  };
  var BLOCK_LOADING = {};
  var BLOCK_ERROR = {};
  var DATA = null;
  var LOAD_ERROR = false;    // fetch failed / non-OK (distinct from "not exported yet")
  var LOADING = false;       // the payload is in flight: the lamp loader, not the computing note
  // DEFAULT TAB = the direction that passes its gate (owner default, 2026-09-06).
  // The lab opened on RP->SP, which is the direction whose ranking the gate does
  // NOT validate; the page led with its weakest claim. build_site.py paints the
  // server-rendered nav, so init() re-syncs the active button to whatever this
  // is (and to the hash when there is one).
  var section = "sp2rp";     // rp2sp | sp2rp | posfit | history | pitchadd | platoon | prospects
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
  // The pixel state box (assets/eephus-state.js, final-pass plan 5.7 PX-12):
  // loading, empty, unmeasured or failed, around a message this file escapes.
  // The bare box is the fallback for a test harness that loads this file alone.
  function pxState(kind, msg, opts) {
    var S = typeof window !== "undefined" && window.EephusState;
    if (S) return S.html(kind, msg, opts);
    var cls = typeof opts === "string" ? opts : (opts && opts.cls) || "";
    return '<div class="px-state is-' + kind + (cls ? " " + cls : "") + '"' +
      (kind === "failed" ? ' role="alert"' : "") + '><div class="px-state-msg">' + msg + "</div></div>";
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

  // ---- organization filter and sort (owner ask 2026-09-25) ------------------
  // One org filter for every player list on the page, through the shared team
  // picker (a native select marked data-team-picker whose values are the hub's
  // canonical club codes, with an All option). It holds across tabs and rides
  // the hash as &org=XXX. Rows carry their club in whatever code family the
  // source spelled (AZ or ARI, KC or KCR, OAK or ATH); EEPHUS_HUB.club folds
  // them to one code, so the filter and the Org sort agree with the picker.
  var orgFilter = "";
  var cardOrder = "rank";   // rank | org, the order of the card views
  function orgCode(t) {
    if (t == null || t === "") return "";
    try {
      var c = (window.EEPHUS_HUB && EEPHUS_HUB.club) ? EEPHUS_HUB.club(t) : null;
      if (c && c.code) return c.code;
    } catch (e) { /* hub optional */ }
    return String(t).toUpperCase();
  }
  function byOrg(rows, field) {
    if (!orgFilter) return rows;
    return rows.filter(function (r) { return orgCode(r[field]) === orgFilter; });
  }
  // Missing clubs sink in either direction; ties keep the order they came in.
  function sortByOrg(rows, field, asc) {
    var out = rows.slice();
    out.sort(function (a, b) {
      var x = orgCode(a[field]), y = orgCode(b[field]);
      if (!x && !y) return 0;
      if (!x) return 1;
      if (!y) return -1;
      var c = x < y ? -1 : x > y ? 1 : 0;
      return asc ? c : -c;
    });
    return out;
  }
  function orgCodes(rows, field) {
    var list = [];
    try {
      if (window.EEPHUS_HUB && EEPHUS_HUB.clubs) list = EEPHUS_HUB.clubs().map(function (c) { return c.code; });
    } catch (e) { list = []; }
    if (!list.length) {   // no hub (a test harness): the codes the rows carry
      var seen = {};
      rows.forEach(function (r) {
        var c = orgCode(r[field]);
        if (c && !seen[c]) { seen[c] = 1; list.push(c); }
      });
    }
    return list.slice().sort();
  }
  // The one control bar a list gets: the org filter, the count it leaves, the
  // card order where the list is cards, and any chip the section adds.
  function orgBar(all, field, noun, cards, extra) {
    var opts = '<option value="">All orgs</option>' + orgCodes(all, field).map(function (c) {
      return '<option value="' + esc(c) + '"' + (c === orgFilter ? " selected" : "") + ">" + esc(c) + "</option>";
    }).join("");
    var n = byOrg(all, field).length;
    return '<div class="mlbstats-bar pal-ctlbar">'
      + '<label class="mlbstats-ctl">org <select id="pal-org" data-team-picker aria-label="Filter by organization">'
      + opts + "</select></label>"
      + (cards
        ? '<label class="mlbstats-ctl">order <select id="pal-order" aria-label="Card order">'
          + '<option value="rank"' + (cardOrder === "rank" ? " selected" : "") + ">ranked</option>"
          + '<option value="org"' + (cardOrder === "org" ? " selected" : "") + ">org A to Z</option></select></label>"
        : "")
      + '<span class="proj-dim pal-count">' + (orgFilter ? esc(n) + " of " + esc(all.length) : esc(all.length))
      + " " + esc(noun) + "</span>" + (extra || "") + "</div>";
  }
  function orgEmpty() { return empty("No " + orgFilter + " rows match these filters."); }
  // The Org cell: the club's logo and code, linked to its club page (the farm
  // system page for a prospect).
  function orgCell(team, ctx) {
    try {
      if (window.EEPHUS_HUB && EEPHUS_HUB.clubLinkHTML) {
        return EEPHUS_HUB.clubLinkHTML(team, { logo: true, stop: true, ctx: ctx });
      }
    } catch (e) { /* hub optional */ }
    return esc(team || "-");
  }
  // A card's club: the code, linked, beside the name the card leads with.
  function orgTag(team, ctx) {
    var link = "";
    try {
      if (window.EEPHUS_HUB && EEPHUS_HUB.clubLinkHTML) link = EEPHUS_HUB.clubLinkHTML(team, { ctx: ctx });
    } catch (e) { link = ""; }
    return '<span class="proj-dim"> ' + (link || esc(team || "")) + "</span>";
  }
  function cardRows(rows, field) {
    var out = byOrg(rows, field);
    return cardOrder === "org" ? sortByOrg(out, field, true) : out;
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
    // The highlight is the direction's TOP TIER cut, read off the payload, so
    // the chart cannot mark a threshold the badges no longer use.
    var cut = topCut("rp2sp");
    var hist = chart("histogram", rows.map(function (r) { return r.fit; }),
      // REFERENCE LINE RELABELLED (plan item E6). It read "starter shape" at 60
      // while this same chart highlights the top cut and its caption calls that
      // band "a real starter profile". Two different starter thresholds on one
      // chart, so a reader could not tell which number meant what. 60 is the
      // PROSPECT BAND edge; the top cut is the starter threshold, and only one
      // of them gets that name.
      { height: 100, min: 0, max: 100, highlightAbove: cut,
        refs: [{ at: 60, label: "prospect band edge" }],
        aria: "RP-SP FIT distribution" });
    return vizWrap("rp2sp-viz", gloss("RP→SP FIT", "rp_sp_fit") + ' distribution <span class="proj-dim">(cyan = '
      + f1(cut) + '+, the top tier)</span>', hist);
  }
  function sp2rpViz() {
    var rows = (DATA && DATA.sp2rp) || [];
    var cut = topCut("sp2rp");
    var pts = rows.filter(function (r) { return r.relief_upside != null && r.components && r.components.conversion_need != null; })
      .map(function (r) {
        return { x: r.relief_upside, y: r.components.conversion_need,
                 label: r.name + "  upside " + r.relief_upside + "  need " + r.components.conversion_need + "  FIT " + r.fit,
                 // dimmed below this direction's own top cut, read off the payload
                 color: (cut == null || r.fit >= cut) ? null : "var(--text-tertiary)" };
      });
    if (pts.length < 8) return "";
    var sc = chart("scatter", pts, { height: 270, xMin: 0, xMax: 100, yMin: 0, yMax: 100,
      xLabel: "relief upside →", yLabel: "↑ conversion need", xRef: 50, yRef: 50, aria: "upside vs need" });
    return vizWrap("sp2rp-viz", 'Relief upside vs conversion need <span class="proj-dim">(dim = below the top tier)</span>', sc);
  }

  function fitClass(v) {
    var n = num(v);
    if (n == null) return "pal-mid";
    if (n >= 70) return "pal-hi";
    if (n >= 55) return "pal-good";
    if (n >= 42) return "pal-mid";
    return "pal-lo";
  }
  // tabindex -1 keeps the glossary hook (hover, aria-describedby) on every
  // cell but takes it out of the Tab order: the column header carries the
  // same term once, and a stop per row put 285 extra stops on RP->SP (QREA15).
  function fitCell(v, term) {
    return '<span class="pal-fit ' + fitClass(v) + '" data-gl="' + esc(term) + '" tabindex="-1">' + f1(v) + "</span>";
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
  // Candidate TIERS. The cuts, the labels and the member counts all come from
  // the payload (pal_export.tier_rule), never from constants here, so the badge,
  // the legend and the exported board cannot state a threshold the export is not
  // applying. The two directions are on DIFFERENT scales and carry different
  // cuts: sp_rp_fit multiplies relief upside by a conversion-need factor, so its
  // pool tops out near 60 and a shared 70 cut left the top tier permanently
  // empty. See the block comment in pal_export.py for the full argument.
  //
  // FALLBACK_TIERS is what a payload built before the rule shipped gets: the old
  // shared 70/55/42. A stale payload degrades to the previous rendering rather
  // than to a blank column, and it carries no counts, so the legend drops the
  // membership clause instead of printing zeros.
  var FALLBACK_TIERS = {
    rp2sp: { tiers: [
      { rank: 1, min_fit: 70, label: "Starter Upside",
        premium_label: "Prime Starter Convert", premium_flag: "successful" },
      { rank: 2, min_fit: 55, label: "Worth a Look" },
      { rank: 3, min_fit: 42, label: "Fringe Fit" },
      { rank: 4, min_fit: null, label: "Reliever Profile" }] },
    sp2rp: { tiers: [
      { rank: 1, min_fit: 70, label: "Bullpen Upside" },
      { rank: 2, min_fit: 55, label: "Relief Fit" },
      { rank: 3, min_fit: 42, label: "Marginal Move" },
      { rank: 4, min_fit: null, label: "Keep Starting" }] }
  };
  function tierRule(dir) {
    var r = DATA && DATA.tier_rule && DATA.tier_rule[dir];
    return (r && r.tiers && r.tiers.length) ? r : FALLBACK_TIERS[dir];
  }
  function tierOf(row, dir) {
    var f = num(row.fit);
    if (f == null) return null;
    var ts = tierRule(dir).tiers;
    for (var i = 0; i < ts.length; i++) {
      if (ts[i].min_fit == null || f >= ts[i].min_fit) return ts[i];
    }
    return ts[ts.length - 1];
  }
  // The top cut of a direction, for the chart annotations that mark it. Reading
  // it here keeps the highlight line and the tier badge on one number.
  function topCut(dir) {
    var t = tierRule(dir).tiers[0];
    return (t && t.min_fit != null) ? t.min_fit : null;
  }
  function tierTitle(row, dir) {
    var t = tierOf(row, dir);
    if (!t) return "";
    if (t.premium_label && t.premium_flag && row[t.premium_flag]) return t.premium_label;
    return t.label;
  }
  // Colour carries the TIER, not the direction. It used to be all-cyan on one
  // tab and all-orange on the other, which spent the whole colour channel
  // repeating which tab the reader had already clicked.
  function tierBadge(row, dir) {
    var t = tierOf(row, dir);
    if (!t) return "";
    return '<div><span class="pal-tier pal-tier--t' + (t.rank || 4) + '">'
      + esc(tierTitle(row, dir)) + "</span></div>";
  }
  function tierLegend(dir) {
    var r = tierRule(dir);
    var ts = r.tiers || [];
    var items = ts.map(function (t, i) {
      var prev = i ? ts[i - 1].min_fit : null;
      var band = (t.min_fit == null)
        ? ("below " + f1(prev))
        : (f1(t.min_fit) + "+");
      // The premium label is the same tier for a reliever who is already
      // succeeding (tier_rule.premium_flag), so the legend names the condition.
      var name = t.premium_label
        ? ('<b>' + esc(t.premium_label) + "</b> if " + esc(t.premium_flag || "flagged")
           + ", else <b>" + esc(t.label) + "</b>")
        : ('<b>' + esc(t.label) + "</b>");
      return name + " (" + band + (t.n == null ? "" : ", " + esc(t.n)) + ")";
    }).join(", ");
    // The SCALE is stated because the two directions do not share one: a 55 in
    // the SP->RP tab is near the top of its pool and mid-pack in the other.
    var scale = (r.fit_min != null && r.fit_max != null)
      ? (" This build's scale: " + f1(r.fit_min) + " to " + f1(r.fit_max) + ", median "
         + f1(r.fit_median) + ". Cuts are fixed, not per-build quantiles.")
      : "";
    return '<div class="pal-tier-legend">Tiers: ' + items + "." + scale + "</div>";
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
      // keyboard-operable sort headers: only the genuinely sortable columns
      // carry data-col, tabindex and aria-sort. No role=button: it replaced the
      // columnheader role, the only role aria-sort is read on (census X06-06).
      var attrs = sortable
        ? ' data-col="' + c.key + '" scope="col" tabindex="0" aria-sort="'
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
        // The rank CELL carries the same .mlbstats-col-rank class the header
        // already gets. site.css keys the frozen-column rules off it: /pal/
        // leads with the rank digit rather than the player, so the shared
        // "freeze :first-child" would pin the number and scroll the name away.
        // With the class on both cells the rank pins narrow at the left edge
        // and the NAME pins beside it. Do not drop it.
        if (c.kind === "rank") { body += '<td class="mlbstats-col-rank">' + (i + 1) + "</td>"; return; }
        if (c.kind === "name") {
          body += '<td class="mlbstats-name pal-expand">' + nameLink(r.name, r.mlbam) + flagChips(r.flags) + "</td>";
          return;
        }
        if (c.kind === "org") { body += '<td class="pal-org-cell">' + orgCell(r.team) + "</td>"; return; }
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
    { key: "org", label: "Org", kind: "org", asc: true },
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
    { key: "org", label: "Org", kind: "org", asc: true },
    { key: "fit", label: "SP→RP FIT", term: "sp_rp_fit", desc: true, cell: function (r) { return fitCell(r.fit, "sp_rp_fit") + tierBadge(r, "sp2rp"); } },
    { key: "starter_era", label: "SP ERA", cell: function (r) { return f2(r.starter_era); }, asc: true },
    { key: "relief_upside", label: "Relief upside", cell: function (r) { return f1(r.relief_upside); } },
    { key: "best_whiff", label: "Putaway", term: "putaway_pitch", cell: function (r) { return fPct(r.best_whiff); } },
    { key: "proj_velo", label: "velo→RP", term: "role_velo_delta", cell: function (r) { return veloCell(r); } },
    // The column is "proj REM+", so it takes the value ruler's `run` ladder, the
    // one /mlbstats/ paints the same number with. This used to be a PRIVATE COPY
    // of the board's banding function living in this file, which is how /pal/ and
    // /mlbstats/ were free to drift on one metric; the copy is deleted rather than
    // pinned by a test.
    { key: "proj_relief_rem_plus", label: "proj REM+", term: "rem_plus", cell: function (r) { return r.proj_relief_rem_plus == null ? "-" : '<span class="rem-plus ' + EephusTiers.cls(r.proj_relief_rem_plus, "run") + '">' + fInt(r.proj_relief_rem_plus) + "</span>"; } },
  ];
  // Conversion-history columns: drives the sortable header + the sort accessors
  // (the row cells are still rendered by renderHistory's custom builders). Default
  // sort is year-desc so the newest (current-season, still-pending) conversions
  // lead. Non-numeric columns (Pitcher / Conversion / Before / After / Arsenal)
  // are non-sortable; sortRows is numeric-only.
  var HISTORY_COLS = [
    { key: "name", label: "Pitcher", kind: "name" },
    { key: "org", label: "Org", kind: "org", asc: true },
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
  // Reverse-Platoon Radar columns: Org and the three OPS reads sort; the rest
  // are labels. The default order is the payload's (most reverse first).
  var PLATOON_COLS = [
    { key: "name", label: "Pitcher", kind: "name" },
    { key: "org", label: "Org", kind: "org", asc: true },
    { key: "p_throws", label: "Throws", sortable: false },
    { key: "role", label: "Role", sortable: false },
    { key: "own_ops", label: "vs own hand" },
    { key: "opp_ops", label: "vs opp hand", asc: true },
    { key: "split", label: "Split" },
    { key: "read", label: "Read", sortable: false },
  ];
  function veloCell(r) {
    if (r.fb_velo == null) return "-";
    var d = (r.proj_velo != null) ? (r.proj_velo - r.fb_velo) : null;
    var arrow = d == null ? "" : '<span class="proj-dim"> ' + (d > 0 ? "+" : "") + d.toFixed(1) + "</span>";
    return f1(r.fb_velo) + (r.proj_velo != null ? " &rarr; " + f1(r.proj_velo) : "") + arrow;
  }
  function sortRows(rows, cols) {
    var col = null; cols.forEach(function (c) { if (c.key === sortKey) col = c; });
    if (col && col.kind === "org") return sortByOrg(rows, col.field || "team", sortAsc);
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
    return window.EEPHUS_GFX ? EEPHUS_GFX.chipHTML(id, "Generate GFX") : "";
  }
  // HOW THIS WORKS (display pass 2026-10-08). The gate sentence, its caveat,
  // the tier cuts and the coverage counts are read once and checked rarely, so
  // they sit in one collapsed fold under a one-line lede; the table leads. They
  // are moved, never dropped: every disclosure a test pins is still in the page.
  function howBlock(html) {
    return html ? '<details class="fa-valmap pal-how"><summary>How this works</summary>'
      + '<div class="fa-valmap-wrap mlbstats-note">' + html + "</div></details>" : "";
  }
  // Plain-text (canvas-safe) velocity cell: current FB velo -> role-projected
  // velo. veloCell() emits HTML spans, so the board needs its own text-only
  // builder.
  // THE DELTA IS DELIBERATELY NOT HERE (dropped 2026-08-07). It used to trail
  // the pair, and it was the difference of the two numbers already printed on
  // either side of the arrow - so it carried no information the reader did not
  // already have, and it cost 48px of a 723px panel. Measured in the two-panel
  // Wide 16:9 export, which is what the split board produces at the default
  // Show=25: every one of the 25 velo cells overflowed its track and rendered
  // as "95.2 -> 94.2..." - the ellipsis had eaten the whole delta anyway, so
  // the column was paying full width for a run of dots. Without it the same
  // column needs 96px against 99px of track and no cell clips, in any format.
  function veloText(r) {
    if (r.fb_velo == null) return "-";
    return f1(r.fb_velo) + (r.proj_velo != null ? " → " + f1(r.proj_velo) : "");
  }
  function rp2spBoardSpec() {
    var rows = byOrg(sortRows((DATA && DATA.rp2sp) || [], RP_COLS), "team");
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
        + (orgFilter ? orgFilter + " · " : "") + rows.length + " relievers who profile as starters",
      url: "eephus.io/pal", filenameBase: "pal-rp2sp-candidates",
      // Caption reads the payload verdict (see verdictPhrase): a shareable
      // graphic that carries a frozen validity claim is the same defect as a
      // page that carries one.
      caption: "candidate screen, not a forecast · RP→SP: " + verdictPhrase("RP->SP"),
      board: { defaultCount: 25, counts: [10, 25, 50],
        legend: "FIT 0-100 = RP→SP conversion screen · Command = component score 0-100 · tiers cut at "
          + (tierRule("rp2sp").tiers || []).filter(function (t) { return t.min_fit != null; })
              .map(function (t) { return f1(t.min_fit); }).join(" / "),
        // Fracs budgeted against the TIGHTEST layout the board produces, the
        // 723px panel of the two-panel Wide 16:9 split (which is what the
        // default Show=25 renders). Measured 2026-08-07 at that width, the old
        // split cut ALL 25 Tier cells to "Prime Star..." / "Starter Up...", all
        // 25 velo cells, and 2 names: the Tier column was carrying 168px of
        // demand in a 108px track while FIT sat on a 65px track it filled to
        // 32px and Command on 72px it filled to 49px. Demand here is
        // max(header label, widest cell) + the renderer's 8px inter-track gap,
        // and the eight columns want 694.5px of the 723px available, so the
        // 28.5px of slack is spread in proportion to demand rather than parked
        // in one column. NOT a fixed pixel layout: the fracs still scale with
        // the panel, this only fixes their RATIO to what the content needs.
        // narrowFrac restores the ORIGINAL ratios for the five-column list the
        // 1080-wide formats render. Those panels are 488px against 532px of
        // demand, so something has to clip there no matter what; the original
        // split takes the hit in Tier (which is over budget by 68px on its own
        // and cannot be rescued) and keeps #, FIT and velo whole, which is the
        // least-bad of the vectors measured. Re-tuning that list for the 542px
        // Twitter panel would clear 31 more cells there and cost ~370 in the
        // 488px formats, so it was not taken.
        columns: [
          { label: "#", frac: 0.036, narrowFrac: 0.05 },
          { label: "Player", frac: 0.284, narrowFrac: 0.24 },
          { label: "FIT", frac: 0.057, narrowFrac: 0.09 },
          { label: "Tier", frac: 0.254, narrowFrac: 0.16 },
          { label: "Arsenal", frac: 0.082, wideOnly: true },
          { label: "FB%", frac: 0.069, wideOnly: true },
          { label: "velo→SP", frac: 0.148, narrowFrac: 0.18 },
          { label: "Command", frac: 0.070, wideOnly: true },
        ], rows: brows },
    };
  }
  function sp2rpBoardSpec() {
    var rows = byOrg(sortRows((DATA && DATA.sp2rp) || [], SP_COLS), "team");
    // TIER ships on this board too. rp2sp has carried one since it was built, so
    // without it the two shareable graphics disagreed about what a PAL board is.
    var brows = rows.map(function (r, i) {
      return { cells: [
        { t: i + 1 },
        { t: r.name, sub: r.team || undefined },
        { t: f1(r.fit), c: "accent" },
        { t: tierTitle(r, "sp2rp") || "-" },
        { t: f2(r.starter_era) },
        { t: fPct(r.best_whiff) },
        { t: veloText(r) },
        { t: fInt(r.proj_relief_rem_plus) },
      ] };
    });
    return {
      kind: "board", module: "Alchemy Lab", accentToken: "--accent-cyan",
      title: "Alchemy Lab · SP→RP Candidates",
      subtitle: (DATA && DATA.season ? "Season " + DATA.season + " · " : "")
        + (orgFilter ? orgFilter + " · " : "") + rows.length + " starters whose stuff would play up in relief",
      url: "eephus.io/pal", filenameBase: "pal-sp2rp-candidates",
      caption: "candidate screen, not a forecast · SP→RP: " + verdictPhrase("SP->RP"),
      board: { defaultCount: 25, counts: [10, 25, 50],
        legend: "FIT 0-100 = SP→RP relief-upside screen (gated by conversion need) · tiers cut at "
          + (tierRule("sp2rp").tiers || []).filter(function (t) { return t.min_fit != null; })
              .map(function (t) { return f1(t.min_fit); }).join(" / "),
        // Every column header must fit its own track, because the renderer now
        // clamps rather than overflows and a clipped header ("PUTAWAY ...")
        // destroys the column's meaning in a way a clipped cell does not.
        // Measured demand at the tightest layout the split board produces, a
        // 723px panel: Putaway whiff 99px and proj REM+ 71px were short, funded
        // here from FIT (65px track, 40px demand) and SP ERA (72/50).
        columns: [
          { label: "#", frac: 0.05 },
          { label: "Player", frac: 0.24 },
          { label: "FIT", frac: 0.075 },
          { label: "Tier", frac: 0.158 },
          { label: "SP ERA", frac: 0.09 },
          { label: "Putaway whiff", frac: 0.137, wideOnly: true },
          { label: "velo→RP", frac: 0.15, wideOnly: true },
          { label: "proj REM+", frac: 0.10 },
        ], rows: brows },
    };
  }

  // ---- sections -------------------------------------------------------------
  function renderRP2SP() {
    var rows = (DATA && DATA.rp2sp) || [];
    if (!rows.length) return empty("No RP→SP candidates yet.");
    var note = '<div class="mlbstats-note">' + gloss("RP→SP FIT", "rp_sp_fit")
      + " ranks arsenal depth first, then command, platoon-neutrality and contact quality."
      + " A candidate screen, not a forecast.</div>";
    var how = howBlock(esc(verdictSentence("RP->SP")) + tierLegend("rp2sp"));
    var shown = byOrg(sortRows(rows, RP_COLS), "team");
    return note + how + rp2spViz() + orgBar(rows, "team", "relievers", false, gfxChip("pal-rp2sp-gfx"))
      + (shown.length ? candTable(shown, RP_COLS) : orgEmpty());
  }
  function renderSP2RP() {
    var rows = (DATA && DATA.sp2rp) || [];
    if (!rows.length) return empty("No SP→RP candidates yet.");
    var note = '<div class="mlbstats-note">' + gloss("SP→RP FIT", "sp_rp_fit")
      + ": relief upside scaled by conversion need, so a starter succeeding in the rotation scores low."
      + " A candidate screen, not a forecast.</div>";
    var how = howBlock("SP ERA is the need signal; proj REM+ is display-only. "
      + esc(verdictSentence("SP->RP")) + tierLegend("sp2rp"));
    var shown = byOrg(sortRows(rows, SP_COLS), "team");
    return note + how + sp2rpViz() + orgBar(rows, "team", "starters", false, gfxChip("pal-sp2rp-gfx"))
      + (shown.length ? candTable(shown, SP_COLS) : orgEmpty());
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
  // WAR produced by the conversion: realized WAR before and after the switch on
  // whatever series backtest.war_basis stamps (eWAR v2 since the 2026-09-03
  // epoch), with the delta colored (a gain reads as a hit, a drop as a miss).
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
  // ---- backtest verdicts: DERIVED, never hard-coded --------------------------
  // Every validity claim on this page reads data/pal.json. Two different things
  // live in that payload and they are NOT the same measurement:
  //   backtest.per_direction  the LIVE rho of pre-conversion FIT against
  //                           realized WAR change, on whatever WAR series
  //                           backtest.war_basis names for this build.
  //   backtest.gate           the PRE-REGISTERED gate verdict carried out of
  //                           data/pal_eval.json, with the WAR series THAT was
  //                           measured on (gate.basis_series) and its own n.
  // A missing block yields "unavailable". The sign of a live rho is never
  // promoted to a verdict here: the gate is a bootstrap gap against same-event
  // baselines, and re-deciding it in a renderer would be inventing a gate.
  function btBlock() { return (DATA && DATA.backtest) || {}; }
  function btDir(key) { return (btBlock().per_direction || {})[key] || {}; }
  function btGate(key) {
    var g = btBlock().gate;
    var d = (g && g.per_direction) ? g.per_direction[key] : null;
    return (d && typeof d.pass === "boolean") ? d : null;
  }
  // Short series name off a stamp line ("eWAR v2: the Baseball-Reference ..."
  // -> "eWAR v2"). null when the build read no WAR at all.
  function seriesShort(s) {
    return s ? String(s).split(":")[0].split("(")[0].trim() : null;
  }
  // null in BOTH states where the series must not be named: no WAR read at all,
  // and WAR read by a substituted loader that never recorded which series it
  // was (pal_export._war_basis stamps those separately).
  function warSeriesShort() {
    var wb = btBlock().war_basis || {};
    if (wb.available === false || wb.provider_known === false) return null;
    return seriesShort(wb.series || wb.provider);
  }
  function gateSeriesShort() {
    var g = btBlock().gate;
    return g ? seriesShort(g.basis_series || g.basis_provider) : null;
  }
  // The regression-to-the-mean caveat on a PASSING gate (final pass M07-01).
  // Every registered baseline assumes a better pre-season means a bigger gain;
  // a WAR change pays out on a bad one. pal_export carries the reversed read
  // straight off the eval artifact (minus each baseline's rho). When that read
  // beats FIT the verdict word stays, and the caveat rides beside it. Null when
  // the payload predates the field or the direction does not pass.
  var REVERSED_LABEL = {
    neg_era_pre: "high pre-season ERA",
    kbb_pre: "low pre-season K-BB%",
    index_pre: "a low pre-season quality index"
  };
  function reversedCaveat(key) {
    var d = btGate(key);
    if (!d || !d.pass || d.reversed_beats_fit !== true || d.reversed_baseline_rho == null) return null;
    return {
      label: REVERSED_LABEL[d.reversed_baseline] || String(d.reversed_baseline),
      rho: d.reversed_baseline_rho
    };
  }
  // true / false / null(unknown) - the ONLY source of a validity word.
  function dirValidates(key) {
    var d = btGate(key);
    return d ? !!d.pass : null;
  }
  // Scorecard tail: the verdict word, the gate's own n, and the series the
  // gate ran on (which may not be the series the live rho ran on).
  function verdictTag(key) {
    var v = dirValidates(key);
    if (v === null) return '<span class="proj-dim">gate verdict not in this payload</span>';
    var d = btGate(key);
    var basis = gateSeriesShort();
    var cav = reversedCaveat(key);
    return '<span class="' + (v ? "pal-hit" : "pal-miss") + '">'
      + (v ? "validated vs baselines" : "does not validate ranking") + "</span>"
      + '<span class="proj-dim"> (gate' + (d.n_gate == null ? "" : " n=" + esc(d.n_gate))
      + (basis ? ", " + esc(basis) + " basis" : "") + ")"
      + (cav ? "; a sort on " + esc(cav.label) + " ranks the same events higher ("
          + esc(cav.rho) + ")" : "") + "</span>";
  }
  // PLAIN TEXT (callers esc() it for HTML; the GFX captions need it raw).
  // One short clause for the banner and the shareable-board captions.
  function verdictPhrase(key) {
    var v = dirValidates(key);
    if (v === null) return "backtest verdict unavailable";
    if (v && reversedCaveat(key)) {
      return "passed its backtest gate; a sort on " + reversedCaveat(key).label + " ranks higher";
    }
    return v ? "backtest-validated ranking" : "structural screen, ranking not backtest-validated";
  }
  // PLAIN TEXT. The long form for the section notes: the verdict, the gate's
  // own n and series, its rho and the baseline it had to beat.
  function verdictSentence(key) {
    var v = dirValidates(key);
    if (v === null) return "No gate verdict in this payload, so no validity claim either way.";
    var d = btGate(key);
    var basis = gateSeriesShort();
    var where = " (gate" + (d.n_gate == null ? "" : " n=" + d.n_gate)
      + (basis ? ", " + basis + " basis" : "")
      + (d.rho_fit_war_delta == null ? "" : ", rho " + d.rho_fit_war_delta)
      + (d.best_baseline ? " vs best same-event baseline " + d.best_baseline
          + (d.best_baseline_rho == null ? "" : " " + d.best_baseline_rho) : "")
      + ")";
    var cav = reversedCaveat(key);
    var caveat = cav
      ? " Caveat: every registered baseline assumes a better pre-season means a bigger gain, "
        + "while a WAR change pays out on a bad one (regression to the mean). A sort on "
        + cav.label + " ranks the same events at " + cav.rho + ", above FIT. The gate never "
        + "tested that reading, so the pass is owed a re-gate."
      : "";
    return v
      ? "Gate: validated; pre-conversion FIT out-ranked every registered same-event baseline on realized "
        + "WAR change" + where + "." + caveat
      : "Gate: structural screen; the ranking is not validated on realized WAR change" + where + ".";
  }

  function scorecard() {
    var b = btBlock();
    // Evidence is per direction (repaired harness): pre-FIT rank vs realized
    // WAR change within each direction. The old pooled held-role rho is a
    // retired reporting-only field and is not shown. The VERDICT is derived
    // (see verdictTag): this card used to hard-code one word per direction and
    // therefore could not report a measurement, only remember one.
    function dirStat(key, label) {
      var d = btDir(key);
      var g = btGate(key);
      var rho = d.rho_prefit_vs_war_delta;
      if (rho == null && !g) {
        return '<span class="pal-sc-stat">' + label
          + '<span class="proj-dim"> measurement unavailable</span></span>';
      }
      var series = warSeriesShort();
      var live = (rho == null)
        ? '<span class="proj-dim">no live &rho; in this build</span>'
        : "<b>&rho; " + esc(rho) + '</b><span class="proj-dim"> vs WAR change (n=' + esc(d.n_war)
          + (series ? ", " + esc(series) : "") + ")</span>";
      return '<span class="pal-sc-stat">' + label + " " + live
        + '<span class="proj-dim"> &middot; </span>' + verdictTag(key) + "</span>";
    }
    return '<div class="pal-scorecard">'
      + '<span class="pal-sc-stat"><b>' + esc(DATA.n_conversions) + "</b> conversions</span>"
      + dirStat("SP->RP", gloss("SP→RP FIT", "sp_rp_fit"))
      + dirStat("RP->SP", gloss("RP→SP FIT", "rp_sp_fit"))
      // NULL GUARD (plan item E6). rp2sp can be empty, and esc(null) renders
      // nothing, so this printed the literal "converters at th pct of the
      // field". A sentence with a hole in it reads as a rendering bug to a
      // reader and tells them nothing either way; say there is no sample.
      // The ordinal is computed: a typed "th" printed "72th".
      + (b.converter_median_fit_pool_pctile == null
          ? '<span class="pal-sc-stat">no converter sample yet</span>'
          : '<span class="pal-sc-stat">converter median FIT: <b>' + esc(b.converter_median_fit_pool_pctile)
            + esc(ordSuffix(Math.round(Number(b.converter_median_fit_pool_pctile)))) + "</b> pct of the field</span>")
      + "</div>";
  }
  // A sub-view strip: real tabs (role, selected state, the panel they control),
  // so the tablist is not an empty one around two plain buttons (QREA15).
  function viewTab(attr, key, label, on) {
    return '<button type="button" class="mlbstats-tab' + (on ? " active" : "") + '" ' + attr + '="' + key
      + '" role="tab" aria-selected="' + (on ? "true" : "false") + '" aria-controls="pal-view">'
      + esc(label) + "</button>";
  }
  function viewPanel(label, html) {
    return '<div id="pal-view" role="tabpanel" aria-label="' + esc(label) + '">' + html + "</div>";
  }
  function historyToggle() {
    return '<div class="mlbstats-tabs" role="tablist" aria-label="Conversion History views">'
      + viewTab("data-histview", "table", "Conversions", historyView === "table")
      + viewTab("data-histview", "mix", "Pitch-mix changes", historyView === "mix")
      + "</div>";
  }
  // Header row for a table built from a column list: sortable columns carry
  // data-col, scope, tabindex and aria-sort; the rest are plain labels.
  function headRow(cols) {
    return "<thead><tr>" + cols.map(function (c) {
      var cls = "mlbstats-col-" + c.key + (c.key === sortKey ? " is-sorted" : "");
      if (c.kind === "name" || c.sortable === false) return '<th class="' + cls + '">' + c.label + "</th>";
      return '<th class="' + cls + '" data-col="' + c.key + '" scope="col" tabindex="0" aria-sort="'
        + (c.key === sortKey ? (sortAsc ? "ascending" : "descending") : "none") + '">' + c.label + "</th>";
    }).join("") + "</tr></thead>";
  }
  function renderHistory() {
    var rows = (DATA && DATA.history) || [];
    if (!rows.length) return empty("No conversion history yet.");
    // the backtest's terms, under the card both views share
    var how = howBlock("Before and After: the pre-role and post-role seasons. Arsenal shift: pitches "
      + "added (+) or dropped (-). " + esc(btBlock().disclaimer || ""));
    if (historyView === "mix") return scorecard() + how + historyToggle() + viewPanel("Pitch-mix changes", renderMix());
    // Sortable, recency-first by default (year desc -> 2026 conversions lead).
    // Click any numeric column header to re-sort.
    var all = rows;
    rows = byOrg(sortRows(rows, HISTORY_COLS), "team");
    var head = headRow(HISTORY_COLS);
    var body = "<tbody>" + rows.map(function (h) {
      return "<tr><td class=\"mlbstats-name\">" + nameLink(h.name, h.mlbam) + "</td>"
        + '<td class="pal-org-cell">' + orgCell(h.team) + "</td>"
        + '<td><span class="pal-dir' + dirClass(h.direction) + '">' + esc((h.direction || "").replace("->", "→")) + "</span></td>"
        + "<td>" + esc(h.year) + "</td>"
        + "<td>" + roleLine(h.pre) + "</td><td>" + roleLine(h.post) + "</td>"
        + "<td>" + warCell(h) + "</td>"
        + "<td>" + arsenalShiftCell(h) + "</td>"
        + "<td>" + heldCell(h) + "</td>"
        + '<td>' + (h.pre_fit == null ? "-" : '<span class="pal-fit ' + fitClass(h.pre_fit) + '">' + f1(h.pre_fit) + "</span>") + "</td>"
        + "<td>" + successCell(h) + "</td></tr>";
    }).join("") + "</tbody>";
    var note = '<div class="mlbstats-note">Every detected ' + gloss("SP↔RP switch", "pal_conversion")
      + " since 2018, with realized pitcher WAR" + (warSeriesShort() ? " on " + esc(warSeriesShort()) : "")
      + " before and after.</div>";
    return scorecard() + how + historyToggle() + viewPanel("Conversions", note + orgBar(all, "team", "conversions")
      + (rows.length ? '<div class="mlbstats-scroll"><table class="mlbstats-table">' + head + body + "</table></div>"
        : orgEmpty()));
  }
  function renderMix() {
    var all = (DATA && DATA.pitch_mix_changes) || [];
    if (!all.length) return empty("No pitch-mix change data.");
    var rows = cardRows(all, "team");
    function usageBars(mix) {
      return (mix || []).map(function (p) {
        return '<div class="pal-ars-row"><span class="pal-ars-pitch">' + esc(p.pitch) + "</span>"
          + bar((p.usage || 0) * 100) + '<span class="pal-ars-meta">' + fPct(p.usage) + "</span></div>";
      }).join("");
    }
    var cards = rows.map(function (m) {
      return '<div class="pal-mix-card"><h4><span>' + logo(m.team) + nameLink(m.name, m.mlbam) + orgTag(m.team)
        + '</span><span class="pal-dir' + dirClass(m.direction) + '">'
        + esc((m.direction || "").replace("->", "→")) + " " + esc(m.year) + "</span></h4>"
        + '<div class="pal-mix-cols"><div><h4>Before</h4>' + usageBars(m.before) + "</div>"
        + '<div><h4>After</h4>' + usageBars(m.after) + "</div></div></div>";
    }).join("");
    return '<div class="mlbstats-note">Pitch usage before and after the switch.</div>'
      + orgBar(all, "team", "conversions", true)
      + (rows.length ? '<div class="pal-mix-grid">' + cards + "</div>" : orgEmpty());
  }

  function renderPitchAdd() {
    var all = (DATA && DATA.pitch_add) || [];
    if (!all.length) return empty("No pitch-add recommendations yet.");
    var rows = cardRows(all, "team");
    var note = '<div class="mlbstats-note">Pitch to add: the arsenal hole (no breaking ball, no offspeed, or a '
      + "thin third pitch) crossed with the platoon weakness. Sorted by " + gloss("RP→SP FIT", "rp_sp_fit") + ".</div>";
    var cards = rows.map(function (r) {
      var rec = r.rec || {};
      var arsenal = (r.arsenal || []).slice().sort(function (a, b) { return (b.usage || 0) - (a.usage || 0); })
        .map(function (p) { return esc(p.pitch) + " " + fPct(p.usage); }).join(" &middot; ");
      var pri = rec.priority === "high" ? " pal-flag--warn" : " pal-flag--good";
      return '<div class="pal-mix-card"><h4><span>' + logo(r.team) + nameLink(r.name, r.mlbam) + orgTag(r.team)
        + '</span><span class="pal-fit ' + fitClass(r.fit) + '">' + f1(r.fit) + "</span></h4>"
        + '<div class="mlbstats-note" style="margin:4px 0">Current: ' + (arsenal || "-") + "</div>"
        + '<div style="margin:7px 0"><span class="pal-flag' + pri + '">ADD ' + esc(rec.add) + "</span>"
        + (rec.target ? ' <span class="proj-dim">vs ' + esc(rec.target) + "</span>" : "") + "</div>"
        + '<div style="font-size:11px;color:var(--text-secondary);line-height:1.4">' + esc(rec.reason) + "</div></div>";
    }).join("");
    return note + orgBar(all, "team", "relievers", true)
      + (rows.length ? '<div class="pal-mix-grid">' + cards + "</div>" : orgEmpty());
  }

  function renderPlatoon() {
    var rows = (DATA && DATA.reverse_platoon) || [];
    // only meaningful splits (with a decent sample), most-reverse first
    var view = rows.filter(function (r) {
      return (r.reverse || r.extreme) && (r.min_tbf == null || r.min_tbf >= 100);
    });
    if (!view.length) return empty("No notable platoon splits yet.");
    var all = view;
    view = byOrg(sortRows(view, PLATOON_COLS), "team");
    var note = '<div class="mlbstats-note">' + gloss("Reverse split", "reverse_platoon")
      + ": tougher on opposite-handed hitters, a plus for RP&rarr;SP; " + gloss("extreme split", "platoon_split")
      + ": a conversion blocker. OPS-against by batter hand, 100+ TBF a hand; descriptive, not backtested.</div>";
    var head = headRow(PLATOON_COLS);
    var body = "<tbody>" + view.map(function (r) {
      // BOTH FLAGS, WHEN BOTH ARE SET. `reverse` is a DIRECTION (own-side OPS
      // higher by more than .030) and `extreme` is a MAGNITUDE (|split| >= .150),
      // so a row can carry both, and 22 of the 146 listed here do. The ternary
      // showed only the first, so those rows displayed the strength this note
      // describes and hid the blocker it describes in the same sentence. An
      // extreme split is still a one-sided profile whichever hand it faces.
      var read = (r.reverse && r.extreme)
        ? '<span class="pal-hit">reverse</span>, but <span class="pal-miss">extreme</span>'
        : r.reverse ? '<span class="pal-hit">reverse (neutral+)</span>'
        : '<span class="pal-miss">extreme split</span>';
      return '<tr><td class="mlbstats-name">' + nameLink(r.name, r.mlbam) + "</td>"
        + '<td class="pal-org-cell">' + orgCell(r.team) + "</td>"
        + "<td>" + esc(r.p_throws) + "HP</td><td>" + esc(r.role) + "</td>"
        + "<td>" + f3(r.own_ops) + "</td><td>" + f3(r.opp_ops) + "</td>"
        + "<td>" + f3(r.split) + "</td><td>" + read + "</td></tr>";
    }).join("") + "</tbody>";
    return note + orgBar(all, "team", "pitchers")
      + (view.length ? '<div class="mlbstats-scroll"><table class="mlbstats-table">' + head + body + "</table></div>"
        : orgEmpty());
  }

  function renderProspects() {
    var all = (DATA && DATA.prospect_watch) || [];
    if (!all.length) return empty("No prospect role-mismatches yet.");
    var rows = cardRows(all, "org");
    // The bound is STATED, never silent: every number below comes from the payload's
    // own prospect_watch_rule, so the copy cannot claim a threshold the export is not
    // applying. Degrades to the old wording on a payload built before the rule shipped.
    var rule = (DATA && DATA.prospect_watch_rule) || null;
    // Severity bands, read off the same rule block. They are QUARTERS OF THE
    // SWING BAND, not a fitted scale and not a probability: a full band past the
    // boundary is a different object from the half-band listing floor, and the
    // card printed both as the same sentence.
    var sevCuts = (rule && rule.severity_cuts) || null;
    function severityOf(margin) {
      var m = num(margin);
      if (!sevCuts || m == null) return null;
      for (var i = 0; i < sevCuts.length; i++) {
        if (m >= sevCuts[i].min_margin) return sevCuts[i];
      }
      return null;
    }
    function sevChip(p) {
      var c = severityOf(p.mismatch_margin);
      if (!c) {
        // stale payload: no bands to read, so state the raw margin rather than
        // invent a tier for it
        return p.mismatch_margin == null ? ""
          : ' <span class="pal-sev">' + f1(p.mismatch_margin) + " past the band</span>";
      }
      var tip = f1(p.mismatch_margin) + " shape points past the boundary, "
        + c.label + " (band " + f1(rule.swing_band) + " points wide).";
      return ' <span class="pal-sev pal-sev--' + esc(c.key) + '" title="' + esc(tip) + '">'
        + esc(c.key) + " " + f1(p.mismatch_margin) + "</span>";
    }
    var bound = "";
    if (rule) {
      bound = " Ranked by margin past the swing band. Listed: " + esc(rule.n_qualified) + " of "
        + esc(rule.n_mismatches) + " mismatches at " + f1(rule.margin_min) + "+ shape points past"
        + (rule.cap_binding ? (", top " + esc(rule.cap) + " shown") : "")
        + "; " + esc(rule.n_below_margin) + " below that margin"
        + (rule.best_margin_below_threshold != null
           ? " (closest " + f1(rule.best_margin_below_threshold) + ")" : "")
        + " stay in the payload.";
      if (sevCuts) {
        bound += " Severity, in quarters of the band: "
          + sevCuts.map(function (c) {
              return "<b>" + esc(c.key) + "</b> at " + f1(c.min_margin) + "+"
                + (c.n == null ? "" : " (" + esc(c.n) + ")");
            }).join(", ") + ".";
      }
    }
    var note = '<div class="mlbstats-note">Scouted role vs ' + gloss("starter shape", "starter_shape")
      + " (" + gloss("arsenal depth", "arsenal_depth") + " + command, from 20-80 tool grades; no minors pitch "
      + "tracking). Descriptive shape screen, not a backtested model.</div>";
    var how = howBlock(esc(DATA.n_prospects || "") + " prospect pitchers scanned"
      // COVERAGE, STATED. A mismatch needs a stated role for the shape to
      // disagree with, and a position of RHP, LHP or P states handedness and no
      // role. Those rows can never appear here, correctly, and the bare
      // "N scanned" read as a screen of the whole pool.
      + ((rule && rule.n_role_unstated)
         ? ("; " + esc(rule.n_role_unstated) + " list only RHP, LHP or P, no role to compare, so they "
            + "cannot appear"
            + (rule.n_role_unstated_above_fv
               ? " (" + esc(rule.n_role_unstated_above_fv) + " of those clear the FV floor)" : "")
            + ".")
         : ".") + bound);
    function toolBars(tools) {
      tools = tools || {};
      return ["fb", "sl", "cb", "ch", "ct", "cmd"].filter(function (k) { return tools[k] != null; }).map(function (k) {
        return '<div class="pal-ars-row"><span class="pal-ars-pitch">' + k.toUpperCase() + "</span>"
          + bar((tools[k] - 20) / 60 * 100) + '<span class="pal-ars-meta">' + fInt(tools[k]) + "</span></div>";
      }).join("");
    }
    // Two grades, two labels. "FV" is the consensus close, which the listing
    // floor reads and which displays as a ceiling; "eFV" is the model grade,
    // to nearest. Printing the eFV grade under "FV" put 38 and 39 on a list
    // gated at FV 40 and printed the scale floor as "FV 20". A floor row
    // (fvE_is_floor) is the outcome curve's lowest knot for every non-positive
    // projection, so it is named as the floor, never read as a level, and no
    // FV-vs-eFV difference is printed on any row.
    var FLOOR_TIP = "The outcome curve returns its lowest knot for every non-positive "
      + "projection, so this is the floor of the 20-80 scale rather than a resolved level.";
    function gradeText(p) {
      var s = "FV " + fCeil(p.fv);
      if (p.fvE == null) return s;
      s += " &middot; " + gloss("eFV", "xfv") + " " + Math.round(p.fvE);
      if (p.fvE_is_floor) s += ' <span class="proj-dim" title="' + esc(FLOOR_TIP) + '">scale floor</span>';
      return s;
    }
    var cards = rows.map(function (p) {
      // Read the LEAN, not the negation of "SP". Only SP and RP rows can be a
      // mismatch, so the else-branch is right today, but it asserted "scouted a
      // reliever" for anything that was not literally SP, which would have
      // mislabelled an UNSTATED row the moment one reached this list.
      var pdir = p.role === "SP" ? "SP->RP" : "RP->SP";
      var arrow = p.role === "SP" ? "SP &rarr; RP" : "RP &rarr; SP";
      var msg = p.role === "SP" ? "Scouted a starter, but the arsenal profiles as a reliever."
        : p.role === "RP" ? "Scouted a reliever, but has the arsenal to start."
        : "Scouted " + esc(p.position || "a pitcher") + ", and the arsenal shape leans "
          + esc(p.lean || "the other way") + ".";
      // the name opens the prospect's PROSPX card; the club opens its farm page
      var nm = p.player_key
        ? '<a class="mlbstats-name-link" href="/prospx/#player=' + encodeURIComponent(p.player_key)
          + '" title="Open the PROSPX card">' + esc(p.name) + "</a>"
        : esc(p.name);
      return '<div class="pal-mix-card"><h4><span>' + logo(p.org) + nm + orgTag(p.org, "farm") + "</span>"
        + '<span class="pal-dir' + dirClass(pdir) + '">' + arrow + "</span></h4>"
        + '<div class="mlbstats-note" style="margin:2px 0">Scouted ' + esc(p.position)
        + " &middot; " + gradeText(p)
        + " &middot; shape " + f1(p.starter_shape) + " &middot; " + esc(p.arsenal_depth) + " plus pitches"
        + sevChip(p) + "</div>"
        + '<div style="margin:6px 0;font-size:11px;color:var(--text-secondary)">' + esc(msg) + "</div>"
        + toolBars(p.tools) + "</div>";
    }).join("");
    return note + how + orgBar(all, "org", "prospects", true)
      + (rows.length ? '<div class="pal-mix-grid">' + cards + "</div>" : orgEmpty());
  }

  // ---- Position Fit: which hitters are worth more runs somewhere else -------
  // Value per 650 PA at position p = bat + fielding(p) + positional adjustment.
  // The bat is position-independent, so it cancels out of any comparison BETWEEN
  // positions: only fielding + the ladder decide where a hitter belongs. Every
  // number rendered here is copied off the model artifact; the section adds no
  // arithmetic of its own beyond formatting, with ONE exception, the ladder
  // table's subtotal row (pfLadder). That row adds the cells printed directly
  // above it, and it has to do its own arithmetic precisely because the check it
  // offers is only worth anything if it is computed from the same digits the
  // reader is adding, not from the payload behind them.
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
    var tip = "Rng+ " + g.plus + ": sprint speed " + g.fts + " ft/s, 100 + 10z (10 points = 1 SD)."
      + (pct != null && pool
          ? " " + pct + ordSuffix(pct) + " percentile of " + pool.n + " " + pos
            + " incumbents (400+ innings, trailing three seasons)."
          : "")
      + " Sprint vs OAA per 1000 innings at " + pos + ": r " + fmtR(meta.r && meta.r[pos])
      + ". Outfield only."
      + (stale ? " From his " + g.season + " season; no " + season + " tracking yet." : "")
      + " Display only, not a model input.";
    return ' <span class="pal-rng" data-gl="rng_plus" title="' + esc(tip) + '">Rng+ ' + g.plus
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
      ? '<div class="mlbstats-note" style="margin:2px 0 8px">Down to ' + esc(r.demPos) + ": "
        + pfSigned(r.demGain) + " runs per 650 PA (&plusmn;" + f1(r.demSe) + "); own glove "
        + pfSigned(r.demPlayer) + ", league-wide constant " + pfSigned(r.demLeague) + ".</div>"
      : "";
    return '<td colspan="20"><div class="pal-why"><div class="pal-why-grid">'
      + '<div><h4>Defensive value by position</h4>'
      + '<div class="mlbstats-note" style="margin:2px 0 8px">Runs per 650 PA: fielding + positional adjustment. The bat is the same at every position and is left out.</div>'
      + bars + "</div>"
      + '<div><h4>The read</h4>' + dem
      + '<div class="mlbstats-note" style="margin:2px 0">Glove ' + pfSigned(r.gloveZ, 2)
      + " SD (&plusmn;" + f2(r.gloveZSe) + " after shrink) = " + pfSigned(r.gloveRuns)
      + " runs per 650 PA at " + esc(r.pos || "-") + ". Bat " + pfSigned(r.bat)
      + " runs per 650 PA vs an average hitter; it does not move the position choice.</div>"
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
      + '<div class="mlbstats-note" style="margin:2px 0 6px">z: the glove rate against the '
      + "position's own difficulty, in SD. Trust: innings / (innings + the position's fitted "
      + "stabilization constant). Read z with Trust.</div>"
      + '<div class="mlbstats-scroll"><table class="detail-table"><thead><tr>'
      + "<th>Season</th><th>Pos</th><th>Inn</th><th>OAA</th><th>FRP</th><th>z</th><th>Trust</th>"
      + "</tr></thead><tbody>" + rows + "</tbody></table></div></div>";
  }

  var POSFIT_COLS = [
    { key: "rank", label: "#", kind: "rank" },
    { key: "name", label: "Hitter", kind: "name", sortable: false },
    { key: "org", label: "Org", kind: "org", asc: true },
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
    if (col && col.kind === "org") return sortByOrg(rows, "team", sortAsc);
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
        ? ' data-col="' + c.key + '" scope="col" tabindex="0" aria-sort="'
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
        // .mlbstats-col-rank: see the note in candTable - it is what lets the
        // frozen column pin the player name instead of the rank digit.
        if (c.kind === "rank") { body += '<td class="mlbstats-col-rank">' + (i + 1) + "</td>"; return; }
        if (c.kind === "org") { body += '<td class="pal-org-cell">' + orgCell(r.team) + "</td>"; return; }
        if (c.kind === "name") {
          body += '<td class="mlbstats-name pal-expand">' + nameLink(r.name, r.mlbam)
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
  // of the model with the tightest evidence, and it is worth showing on its own.
  // NO NUMBERS IN THIS COMMENT ON PURPOSE: it used to quote an R2 and a row
  // count that the payload had already moved past, and the note text below
  // prints the artifact's own n, window and R2, which is the only copy that
  // cannot go stale.
  // Why the fit sees a handful of recent seasons instead of everything on
  // record. Rendered only when the artifact on screen IS the short window: the
  // payload forwards `seasons` but not the window basis, so the span is the
  // only thing that can be checked here, and a long-window artifact must not be
  // handed an explanation of a decision it does not reflect.
  function pfWindowNote(L) {
    var s = L && L.seasons;
    if (!s || s.length !== 2 || num(s[0]) == null || num(s[1]) == null) return "";
    var span = Number(s[1]) - Number(s[0]) + 1;
    if (span > 8) return "";
    // READ, NOT TYPED (QREC13): the held-out comparison rides in the payload
    // (ladder.windowEval, from the recency gate's eval artifact) and is cited
    // by name. Without it the note states the reason and no figure.
    var W = L.windowEval || null;
    var head = " Window: rungs drift by more than their sampling intervals, so the short span was chosen "
      + "on held-out error";
    if (!W || W.dmae == null) return head + ", at the cost of wider intervals.";
    var ci = W.ci95 || [];
    return head + "; it beat the " + (W.poolFrom ? esc(W.poolFrom) + "-onward " : "longer ")
      + "pool by " + f2(W.dmae) + " runs per 650 PA (95% CI " + f2(ci[0]) + " to " + f2(ci[1])
      + ", better in " + esc(W.nSeasonsBetter) + " of " + esc(W.nSeasons) + " held-out seasons; "
      + esc(W.artifact || "") + (W.generatedAt ? ", " + esc(W.generatedAt) : "")
      + "), at the cost of wider intervals.";
  }
  // The two Difference columns, explained where they are read. This is a
  // basis mismatch, not a scoring dispute, and the page used to print only the
  // uncorrected one under the claim that it showed "where the folklore table is
  // wrong".
  function pfFolkloreNote(L) {
    var b = L.folkloreBasis;
    if (!b || !b.scale_to_our_basis) {
      return " Diff: this fit minus the folklore table.";
    }
    return " Folklore is quoted per 162 games (" + fThou(b.full_season_innings)
      + " innings); 650 PA is about " + fThou(b.pa_equivalent_innings)
      + " innings, so as quoted it runs about " + f1((1 / b.scale_to_our_basis - 1) * 100)
      + "% large. <strong>Diff, same basis</strong> rescales it by " + f2(b.scale_to_our_basis)
      + " first. Neither diff is the answer: some sources quote the folklore table per 600 to"
      + " 700 PA, and it is the FanGraphs ladder while this fit inverts Baseball-Reference.";
  }

  function pfLadder() {
    var L = (PF && PF.ladder) || {};
    // WHICH COLUMN IS PRINTED. build_positional_fit_payload selects it: the
    // fielder-centred ladder, in which the eight fielding rungs sum to exactly
    // zero. That is the convention the folklore table uses, so the Difference
    // column is finally comparing like with like. The model's own column
    // (exposure-weighted zero) rides along as L.values and is what every
    // valuation on the site runs on; the two differ by one constant, so every
    // gap between two positions is identical in both. Artifacts built before
    // 2026-07-31 carry no fielder-centred column and fall back to L.values,
    // with the note below saying which basis is on screen.
    var model = L.values || {};
    var vals = L.valuesDisplay || model;
    var fielderCentred = (L.valuesDisplayBasis === "fielder_centred");
    var ci = L.ci95 || {}, folk = L.folklore || {};
    // THE FOLKLORE COLUMN IS NOT ON OUR BASIS, and this table subtracted it
    // from ours anyway. Our rungs are runs per 650 PA of exposure; the folklore
    // table is quoted per full defensive season (162 games, 1,458 innings), and
    // 650 PA is only about 1,278 of those innings. So every Difference cell
    // overstated folklore by roughly 14 percent: first base read 4.1 runs wrong
    // where a like-for-like read is 2.6, and catcher read 1.6 where it is
    // within 0.1.
    //
    // Both readings now print, and NEITHER is called the answer. The scale is
    // derived from the fit's own inn_per_pa, but the convention it corrects for
    // is genuinely ambiguous (the folklore table is quoted per 162 games in
    // some sources and per 600-700 PA in others), and it is the FanGraphs/Tango
    // ladder while this fit inverts Baseball-Reference, so the comparison is
    // cross-system before it is cross-basis. Replacing a stated error with an
    // unstated assumption would not be an improvement.
    var fbasis = L.folkloreBasis || null;
    var folkRe = (fbasis && fbasis.folklore_rescaled) || null;
    // The interval is the model's own bootstrap band, carried onto the printed
    // line by the SAME constant that moved the point estimate, so it stays
    // centred on the printed number at its original width.
    function shift(p) {
      return (vals[p] != null && model[p] != null) ? vals[p] - model[p] : 0;
    }
    // WHY THIS TABLE IS SPLIT (owner report 2026-08-07: "the fitted runs/650
    // still is not summing to 0, which it should by definition").
    //
    // The fit was never the defect and is not touched. Re-derived from the live
    // feeds on the shipped 2021-2026 window, n=2023, the recentred ladder's
    // weighted sum is -1.1e-16, machine zero, and the eight fielding rungs in
    // the column printed here sum to -0.01, which is 2 dp rounding across eight
    // cells. THE DEFECT WAS ON SCREEN: the nine POS_ORDER rungs went into one
    // undivided column, and DH, which the printed column is NOT centred over,
    // sat in that column at -15.18 with nothing marking it. So the only sum a
    // reader could take off the page was -15.19, and the only thing saying
    // otherwise was prose below the table.
    //
    // The fix is arithmetic the reader can redo: the eight centred rungs, a
    // subtotal of THOSE PRINTED CELLS, then DH below the line and labelled out.
    // The subtotal parses the formatted cell rather than reading the payload, so
    // it can never disagree with the column it is a check on.
    var sum8 = 0, sum8Folk = 0, sum8Diff = 0, sum8Re = 0, nField8 = 0, nFolk8 = 0;
    // One row formatter for both groups. DH below the subtotal is the same five
    // cells as a rung above it and must stay that way, so it is built here too,
    // with `collect` false and a tag that says why it is standing apart.
    function ladderRow(p, collect, tag) {
      var d = (folk[p] != null) ? vals[p] - folk[p] : null;
      var c = ci[p], k = shift(p);
      var vCell = pfSigned(vals[p], 2);
      var fCell = (folk[p] != null) ? pfSigned(folk[p], 1) : "-";
      var dCell = (d == null) ? "-" : pfSigned(d, 2);
      // Parse back off the formatted cell, and take only what parsed. pfSigned
      // renders a bad payload value as "-", and Number("-") is NaN, which would
      // turn the whole subtotal into "NaN" and lose the eight good rungs with
      // it. A skipped cell makes the subtotal disagree with the column, which is
      // the one thing it must not do, so `nField8` counts what actually went in
      // and the row says so when that is not eight.
      if (collect) {
        if (isFinite(Number(vCell))) { sum8 += Number(vCell); nField8 += 1; }
        if (folk[p] != null && isFinite(Number(fCell)) && isFinite(Number(dCell))) {
          sum8Folk += Number(fCell);
          sum8Diff += Number(dCell);
          nFolk8 += 1;
        }
      }
      var dRe = (folkRe && folkRe[p] != null) ? vals[p] - folkRe[p] : null;
      var reCell = (dRe == null) ? "-" : pfSigned(dRe, 2);
      if (collect && dRe != null && isFinite(Number(reCell))) sum8Re += Number(reCell);
      return "<tr><td><strong>" + esc(p) + "</strong>" + (tag || "") + "</td>"
        + "<td>" + vCell + "</td>"
        + "<td>" + (c ? '<span class="proj-dim">' + pfSigned(c[0] + k, 2) + " to " + pfSigned(c[1] + k, 2) + "</span>" : "-") + "</td>"
        + "<td>" + fCell + "</td>"
        + "<td>" + (d == null ? "-" : '<span class="proj-dim">' + dCell + "</span>") + "</td>"
        + "<td>" + (dRe == null ? "-" : '<span class="' + (Math.abs(dRe) >= 1.5 ? "pal-hit" : "") + '">' + reCell + "</span>") + "</td></tr>";
    }
    // POS_ORDER is shared with the rest of this file and is NOT mutated: the
    // split below is a filter over a copy, so the display order of the rungs is
    // unchanged. Excluding DH mirrors positional_fit._FIELDERS, which is
    // LADDER_POSITIONS minus DH and is exactly the set the printed column is
    // centred over.
    var shown = POS_ORDER.filter(function (p) { return vals[p] != null; });
    var rows = shown.filter(function (p) { return p !== "DH"; })
      .map(function (p) { return ladderRow(p, true); }).join("");
    // Inline styles on EVERY cell of the subtotal, on purpose: site.css freezes
    // td:first-child with its own opaque fill at a specificity this file cannot
    // reach from a class, so an un-inlined band would leave the frozen Pos cell
    // untinted and let the columns underneath slide through it on a horizontal
    // scroll. Rules above AND below close the block, which is what puts DH
    // outside it.
    var subTd = ' style="border-top:2px solid var(--border);border-bottom:2px solid var(--border);background:var(--bg-secondary)"';
    // The claim attached to the subtotal branches with the basis, because on a
    // pre-2026-07-31 artifact this column is the model's own and its eight-rung
    // sum is a CONSEQUENCE of the weighted zero, not a constraint. Printing
    // "0 by construction" over +11.83 would be the same kind of wrong the split
    // exists to end.
    //
    // The residue band is arithmetic, not slack: each cell is printed to 2 dp,
    // so n of them can drift at most n x 0.005 from the exact zero the centring
    // imposes, which is 0.04 over the usual eight. The served column lands at
    // -0.01. ANYTHING OUTSIDE THAT BAND is a real mismatch between the column
    // and the basis it claims, and the row says so on the page rather than
    // explaining it away as rounding, which is the failure mode that let this
    // table read as broken while every number in it was right.
    var subNote = !fielderCentred ? "not the imposed zero"
      : (Math.abs(sum8) < 0.005 ? "0 by construction"
        : (Math.abs(sum8) <= nField8 * 0.005 + 1e-9 ? "0 by construction, 2 dp rounding"
          : "does not add up, off by " + pfSigned(sum8, 2)));
    rows += "<tr>"
      + "<td" + subTd + "><strong>Sum of the " + fInt(nField8) + "</strong></td>"
      + "<td" + subTd + "><strong>" + pfSigned(sum8, 2) + "</strong></td>"
      + "<td" + subTd + '><span class="proj-dim">' + subNote + "</span></td>"
      + "<td" + subTd + ">" + (nFolk8 ? "<strong>" + pfSigned(sum8Folk, 1) + "</strong>" : "-") + "</td>"
      + "<td" + subTd + ">" + (nFolk8 ? "<strong>" + pfSigned(sum8Diff, 2) + "</strong>" : "-") + "</td>"
      + "<td" + subTd + ">" + (nFolk8 && folkRe ? "<strong>" + pfSigned(sum8Re, 2) + "</strong>" : "-") + "</td>"
      + "</tr>";
    // DH stays on the page: the owner needs the number, and it is the rung that
    // decides whether a bat is worth carrying with no glove attached. It just
    // stops being an unmarked ninth term in a sum of eight.
    rows += shown.filter(function (p) { return p === "DH"; })
      .map(function (p) {
        return ladderRow(p, false, '<span class="proj-dim"> not in the sum</span>');
      }).join("");
    var note = '<div class="mlbstats-note">' + gloss("Positional ladder", "positional_ladder")
      + ", inverted from Baseball-Reference: " + fThou(L.nPlayerSeasons) + " player-seasons, "
      + esc((L.seasons || [])[0]) + " to " + esc((L.seasons || [])[1]) + ", " + fInt(L.minPa) + "+ PA; R&sup2; "
      + (L.r2 == null ? "-" : f1(L.r2 * 100) + "%") + ", residual SD " + f2(L.residSd) + " runs. A rung is "
      + "what BRef prices the position at, not an independent measure of difficulty.</div>"
      + howBlock("Least squares of positional runs per 650 PA on innings shares, no intercept."
        + pfFolkloreNote(L) + pfWindowNote(L));
    // WHICH SUM IS ZERO, stated on the page rather than left to be
    // rediscovered. Only rendered when the artifact carries the identification
    // block (added 2026-07-31); older artifacts get the table with no claim
    // attached rather than a wrong one, and their fallback text is the one that
    // describes the exposure-weighted column they are actually printing.
    var id = L.identification || null;
    var sums = "";
    if (id && id.sum_exposure_weighted != null) {
      var wDH = ((id.exposure_share || {}).DH != null)
        ? f1(100 * id.exposure_share.DH) + "%" : "about 7%";
      if (fielderCentred) {
        // Signed on purpose: the model column sits HIGHER only because the eight
        // fielding rungs happen to sum positive. State the direction, do not
        // assume it.
        var lvl = (id.sum_equal_weight_fielders != null)
          ? id.sum_equal_weight_fielders / 8 : null;
        sums = '<div class="mlbstats-note"><strong>Centring.</strong> '
          + "The eight fielding rungs sum to zero, the folklore table's convention; the subtotal row "
          + "adds the printed cells. DH"
          + (vals.DH != null ? " (" + pfSigned(vals.DH, 2) + ")" : "")
          + " is outside the sum: DH is " + wDH + " of league play, not a ninth. The model's own zero "
          + "is exposure-weighted (sum <strong>" + f2(id.sum_exposure_weighted) + "</strong> by construction"
          + (lvl == null ? ""
             : "; every rung sits " + f2(Math.abs(lvl)) + " runs " + (lvl >= 0 ? "higher" : "lower")
               + " on that basis")
          + "). Gaps between positions are identical on either basis. Site valuations use the weighted "
          + "basis; the 95% interval is the model&rsquo;s bootstrap band shifted by the same constant.</div>";
      } else {
        sums = '<div class="mlbstats-note"><strong>Centring.</strong> '
          + "This artifact predates the fielder-centred column, so the rungs are on the model&rsquo;s "
          + "exposure-weighted basis: that sum is <strong>" + f2(id.sum_exposure_weighted)
          + "</strong> by construction. The subtotal row (" + f2(id.sum_equal_weight_fielders)
          + ") and the equal-weight nine-rung sum (" + f2(id.sum_equal_weight_9)
          + ") follow from it, not errors: DH is " + wDH + " of league exposure, not a ninth.</div>";
      }
    }
    return note + '<div class="mlbstats-scroll"><table class="mlbstats-table">'
      + "<thead><tr><th>Pos</th><th>Fitted (runs/650)</th><th>95% CI</th><th>Folklore</th>"
      + "<th>Diff, as quoted</th><th>Diff, same basis</th></tr></thead>"
      + "<tbody>" + rows + "</tbody></table></div>" + sums + pfMethod();
  }

  // The OAA comparator, READ off the paired difference (model minus raw OAA)
  // and its interval rather than typed (QREC13): an interval wholly below
  // zero is "better than the model", wholly above is "worse", across zero
  // is "not separable from the model".
  function oaaVsModel(D) {
    var mm = ((D && D.modelMinus) || {}).raw_oaa || {};
    var c = mm.ci95 || [];
    if (mm.mean == null || num(c[0]) == null || num(c[1]) == null) return ".";
    var word = c[1] < 0 ? "better than the model" : c[0] > 0 ? "worse than the model"
      : "not separable from the model";
    return ", " + word + " (model minus OAA " + pfSigned(mm.mean, 2) + ", 95% CI "
      + pfSigned(c[0], 2) + " to " + pfSigned(c[1], 2) + ").";
  }
  // Two DIFFERENT questions were measured and they got two different
  // answers; both are printed, and the failing one is not softened.
  function pfMethod() {
    var A = (PF && PF.accuracy) || {}, D = (PF && PF.demotionNull) || {};
    var mae = A.mae || {}, adv = (A.advantage || {}).carry_over || {}, auc = D.auc || {};
    var ci = adv.ci95 || [];
    var pass = '<div class="pal-mix-card"><h4><span>Predicts: the size of a move</span>'
      + '<span class="pal-dir pal-dir--pass">VALIDATED</span></h4>'
      + '<div class="mlbstats-note" style="margin:4px 0">Out of sample, ' + fInt(A.nConversions)
      + " position changes (" + fInt(A.minInningsEachSide) + "+ innings each side). MAE " + f2(mae.model)
      + " runs per 650 PA; carry-over " + f2(mae.carry_over) + ", league average " + f2(mae.league_avg)
      + ", row-permuted twin " + f2(mae.permuted) + ". Advantage over carry-over " + f2(adv.mean)
      + " runs (95% CI " + f2(ci[0]) + " to " + f2(ci[1]) + "; permutation null " + f2(A.permNull95)
      + "). Positive in " + esc(A.seasonAdvantagePositiveIn || "-") + " season splits.</div></div>";
    var fail = '<div class="pal-mix-card"><h4><span>Does not predict: who gets demoted</span>'
      + '<span class="pal-dir pal-dir--null">MEASURED NULL</span></h4>'
      + '<div class="mlbstats-note" style="margin:4px 0">' + fThou(D.nScored) + " player-seasons ("
      + fPct(D.baseRate) + " moved down the next year): AUC " + f2(auc.model) + " (coin flip 0.50; "
      + "permutation band on AUC minus 0.5: " + f2(D.permNull95) + "). Raw single-season OAA alone: "
      + f2(auc.raw_oaa) + oaaVsModel(D) + " The list is a valuation, not a prediction.</div></div>";
    var up = D.promotionSide || {};
    var nuance = (up.auc_model_up != null)
      ? '<div class="pal-mix-card"><h4><span>Moves up</span></h4>'
        + '<div class="mlbstats-note" style="margin:4px 0">AUC ' + f2(up.auc_model_up) + " over "
        + fInt(up.n_moved_up) + " promotions; zero-information control " + f2(up.auc_control_up) + ".</div></div>"
      : "";
    var caveats = ((PF && PF.caveats) || []).map(function (c) {
      return "<li>" + esc(c) + "</li>";
    }).join("");
    var oos = ((PF && PF.outOfScope) || []).join(", ");
    return '<div class="pal-mix-grid" style="margin-top:14px">' + pass + fail + nuance + "</div>"
      + (caveats ? '<details class="fa-valmap" style="margin-top:12px"><summary>Stated limits</summary>'
        + '<ul class="mlbstats-note" style="margin:8px 0 0 18px;list-style:disc">' + caveats + "</ul>"
        + (oos ? '<div class="mlbstats-note" style="margin-top:8px">Out of scope: ' + esc(oos) + ".</div>" : "")
        + "</details>" : "");
  }

  function renderPosFit() {
    if (PF_ERROR) {
      return pxState("failed", "Position-fit model did not load. "
        + '<button type="button" class="chip" id="pf-retry">Retry</button>', "pal-load-error");
    }
    if (!PF) return pxState("loading", esc("Loading the position-fit model."));
    var all = PF.rows || [];
    if (!all.length) return empty("No qualified hitters in the position-fit model yet.");
    var views = [["misplaced", "Misplaced hitters"], ["down", "Move down the spectrum"],
                 ["board", "Every qualified hitter"], ["ladder", "The positional ladder"]];
    var tabs = views.map(function (t) { return viewTab("data-pfview", t[0], t[1], posfitView === t[0]); }).join("");
    var curLabel = "";
    views.forEach(function (t) { if (t[0] === posfitView) curLabel = t[1]; });
    var nav = '<div class="mlbstats-tabs" role="tablist" aria-label="Position Fit views">' + tabs + "</div>";
    if (posfitView === "ladder") return nav + viewPanel(curLabel, pfLadder());

    var rows = posfitView === "misplaced" ? all.filter(function (r) { return r.misplaced; })
      : posfitView === "down" ? all.filter(function (r) { return r.demoted; })
      : all;
    var fr = PF.flagRule || {};
    var lead = posfitView === "misplaced"
      ? "Best defensive position is not the current one. Flag: gain of " + f1(fr.min_gain_runs_per_650)
        + "+ runs per 650 PA and at least " + f1(fr.min_sigma) + " SE. "
        + fInt(PF.nFlagged) + " of " + fInt(PF.nQualified) + " qualified hitters."
      : posfitView === "down"
      ? "Hitters who gain runs moving down the defensive spectrum, on the same flag bar: "
        + fInt(PF.nFlaggedDemotion) + " qualified. Part of every corner-outfield-to-first-base gain is a league-wide "
        + "constant; the expanded row splits it out."
      : "Every qualified hitter (" + fInt(fr.headline_min_pa) + "+ PA, " + fInt(fr.headline_min_innings)
        + "+ defensive innings), by gain at his best position.";
    var note = '<div class="mlbstats-note">' + gloss("Position fit", "position_fit") + ". " + esc(lead)
      + " Runs per 650 PA, " + esc(PF.season || "") + " season; a valuation, not a prediction: who gets moved "
      + "measured null (see The positional ladder).</div>"
      + howBlock(PF.valueIdentity ? "Value identity: " + esc(PF.valueIdentity) + ". The bat is the same at "
        + "every position, so fielding and the positional adjustment decide the move." : "");
    if (!rows.length) return nav + viewPanel(curLabel, note + empty("No hitters clear the flag in this view."));
    var shown = byOrg(pfSortedRows(rows), "team");
    return nav + viewPanel(curLabel, note + orgBar(rows, "team", "hitters")
      + (shown.length ? pfTable(shown) : orgEmpty()));
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
      // The build date rides the banner: this payload is baked from a model
      // artifact that is not refit nightly, so its age is the reader's to see.
      if (pfBanner) pfBanner.innerHTML = PF
        ? '<div class="mlbstats-note">Season ' + esc(PF.season || "") + " &middot; " + esc(PF.model || "")
          + (PF.generated_at ? ", built " + esc(String(PF.generated_at).slice(0, 10)) : "") + "</div>"
        : "";
      bindTable(root);
      wireGlossary(root);
      return;
    }
    if (!DATA) {
      root.innerHTML = LOAD_ERROR
        ? pxState("failed", "Alchemy Lab did not load; the nightly build may be writing it. "
          + '<button type="button" class="chip" id="pal-retry">Retry</button>', "pal-load-error")
        : LOADING ? pxState("loading", esc("Loading the Alchemy Lab."))
        // Names the ACTUAL source mix. This read "from Statcast", which is only
        // the arsenal and velocity half: role, rates and platoon splits are
        // StatsAPI (through bullpen_export) and the conversion WAR column is
        // Baseball-Reference.
        : pxState("unmeasured", esc("Alchemy Lab not built yet on this deploy; the nightly build writes it "
                + "from Statcast arsenals, StatsAPI roles and platoon splits, and run-frame WAR."));
      var retry = document.getElementById("pal-retry");
      if (retry) retry.addEventListener("click", function () { load(); });
      return;
    }
    if (!hasBlock(section)) {
      ensureBlock(section);
      if (hasBlock(section)) return;   // answered at once: that render already painted
      root.innerHTML = BLOCK_ERROR[section]
        ? pxState("failed", "This tab's rows did not load. "
          + '<button type="button" class="chip" id="pal-block-retry">Retry</button>', "pal-load-error")
        : pxState("loading", esc("Loading this tab's rows."));
      var bretry = document.getElementById("pal-block-retry");
      if (bretry) bretry.addEventListener("click", function () {
        BLOCK_ERROR[section] = false; render();
      });
      return;
    }
    root.innerHTML = (section === "sp2rp") ? renderSP2RP() : (section === "history") ? renderHistory()
      : (section === "pitchadd") ? renderPitchAdd() : (section === "platoon") ? renderPlatoon()
      : (section === "prospects") ? renderProspects() : renderRP2SP();
    var banner = document.getElementById("pal-banner");
    if (banner) banner.innerHTML = DATA.season
      ? '<div class="mlbstats-note">Season ' + esc(DATA.season)
        // The build date is the reader's to see (census M07-25). The two
        // per-direction verdicts are not repeated here: the masthead derives
        // them from the same gate block, and the boards' folds carry them long.
        + (DATA.generated_at ? " &middot; built " + esc(String(DATA.generated_at).slice(0, 10)) : "")
        + " &middot; candidate screen, not a projection "
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
          : (section === "posfit") ? POSFIT_COLS : (section === "platoon") ? PLATOON_COLS : RP_COLS;
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
    var orgSel = root.querySelector("#pal-org");
    if (orgSel) orgSel.addEventListener("change", function () {
      orgFilter = orgSel.value || "";
      openRow = null;
      writeHash();
      render();
    });
    var ordSel = root.querySelector("#pal-order");
    if (ordSel) ordSel.addEventListener("change", function () {
      cardOrder = ordSel.value === "org" ? "org" : "rank";
      render();
    });
    root.querySelectorAll("[data-histview]").forEach(function (b) {
      b.addEventListener("click", function () { historyView = b.getAttribute("data-histview"); render(); });
    });
    root.querySelectorAll("[data-pfview]").forEach(function (b) {
      b.addEventListener("click", function () {
        posfitView = b.getAttribute("data-pfview");
        openRow = null;
        writeHash();
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
        writeHash();
        render();
      });
    });
  }

  // The hash: the section (or posfit=<view>), then &org=<code> when a club
  // is picked. The section regexes below are what test_page_index reads.
  function writeHash() {
    var base = (section === "posfit") ? "posfit=" + posfitView : section;
    try { history.replaceState(null, "", "#" + base + (orgFilter ? "&org=" + orgFilter : "")); } catch (e) { /* hash optional */ }
  }
  function readHash() {
    var h = location.hash || "";
    var m = /^#(rp2sp|sp2rp|posfit|history|pitchadd|platoon|prospects)/.exec(h);
    if (m) setSection(m[1]);
    var v = /^#posfit=(misplaced|down|board|ladder)/.exec(h);
    if (v) { setSection("posfit"); posfitView = v[1]; }
    var o = /[#&]org=([A-Za-z]{2,4})(?:&|$)/.exec(h);
    if (o) orgFilter = orgCode(o[1]);
  }

  // Loader with a visible failure mode: a non-OK response or a network error
  // sets LOAD_ERROR so render() paints the error state (with a Retry button)
  // instead of a blank/"computing" page. While the fetch is in flight render()
  // paints the lamp loader, so the first paint is the loading kind.
  function fetchJSON(url) {
    return fetch(url, { cache: "no-cache" })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }
  function load() {
    LOAD_ERROR = false;
    LOADING = true;
    render();
    fetchJSON(CORE_URL)
      .catch(function () { return fetchJSON(FULL_URL); })
      .then(function (j) { LOADING = false; DATA = j; render(); })
      .catch(function () { LOADING = false; DATA = null; LOAD_ERROR = true; render(); });
  }
  // true when every key the section reads is on hand (the whole artifact, or
  // the core plus this section's row file)
  function hasBlock(s) {
    var ks = BLOCK_KEYS[s];
    if (!ks) return true;
    if (!DATA) return false;
    for (var i = 0; i < ks.length; i++) if (!Array.isArray(DATA[ks[i]])) return false;
    return true;
  }
  function ensureBlock(s) {
    if (!DATA || hasBlock(s) || BLOCK_LOADING[s] || BLOCK_ERROR[s]) return;
    BLOCK_LOADING[s] = true;
    fetchJSON(BLOCK_URL[s])
      .catch(function () { return fetchJSON(FULL_URL); })
      .then(function (j) {
        BLOCK_LOADING[s] = false;
        BLOCK_KEYS[s].forEach(function (k) { DATA[k] = (j && Array.isArray(j[k])) ? j[k] : []; });
        render();
      })
      .catch(function () { BLOCK_LOADING[s] = false; BLOCK_ERROR[s] = true; render(); });
  }

  function init() {
    bindSectionNav();
    // a typed or back/forward hash (#history&org=LAD) re-reads the state
    window.addEventListener("hashchange", function () { openRow = null; orgFilter = ""; readHash(); render(); });
    // Sync the server-rendered nav to the default section BEFORE readHash, or a
    // no-hash load paints SP->RP content under an active RP->SP button.
    setSection(section);
    readHash();
    loadLinks();
    load();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
