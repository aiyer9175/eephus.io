/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io player hub - cross-module identity + the unified share card
// =============================================================================
// One player exists on up to three card surfaces (PROSPX prospect card,
// FA market card, MLB player page). This tiny shared lib gives every
// surface the same two affordances:
//
//   EEPHUS_HUB.links()                  -> promise of data/player_links.json
//   EEPHUS_HUB.stripHTML(row, active)   -> the module hub strip (chips that
//                                          link the SAME player across
//                                          modules; active chip filled)
//   EEPHUS_HUB.shareCard(opts)          -> canvas-native PNG share card with
//                                          one visual language for every
//                                          module (module eyebrow + accent
//                                          carries the distinction)
//
// Canvas-native by the FA board precedent: html2canvas can't resolve CSS
// var(), hand-drawn cards are deterministic in both themes. Tokens are
// read from the live computed style at draw time.
(function () {
  "use strict";

  let _linksPromise = null;
  function links() {
    if (!_linksPromise) {
      _linksPromise = fetch("/data/player_links.json", { cache: "no-cache" })
        .then(r => (r.ok ? r.json() : null))
        .catch(() => null);
    }
    return _linksPromise;
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ---- shared team logo (ESPN slugs) ----------------------------------------
  // Keyed on the MLB StatsAPI abbreviations the MLB modules use (SD/SF/TB/CWS/AZ
  // differ from the FanGraphs codes fa.js/projections.js use), with the ESPN
  // slug aliases folded in so either family resolves.
  var _ESPN = {
    ARI: "ari", AZ: "ari", ATH: "ath", ATL: "atl", BAL: "bal", BOS: "bos",
    CHC: "chc", CWS: "chw", CHW: "chw", CIN: "cin", CLE: "cle", COL: "col",
    DET: "det", HOU: "hou", KC: "kc", KCR: "kc", LAA: "laa", LAD: "lad",
    MIA: "mia", MIL: "mil", MIN: "min", NYM: "nym", NYY: "nyy", PHI: "phi",
    PIT: "pit", SD: "sd", SDP: "sd", SEA: "sea", SF: "sf", SFG: "sf",
    STL: "stl", TB: "tb", TBR: "tb", TEX: "tex", TOR: "tor", WSH: "wsh", WSN: "wsh",
  };
  function teamLogo(team, cls) {
    if (!team) return "";
    var slug = _ESPN[team] || String(team).toLowerCase();
    return '<img class="' + (cls || "eephus-teamlogo") + '" src="https://a.espncdn.com/i/teamlogos/mlb/500/'
      + slug + '.png" alt="' + esc(team) + '" loading="lazy" onerror="this.remove()">';
  }

  // ---- lightweight inline charts (SVG, theme-tokened) -----------------------
  // Emit live CSS variable references (the fa.js precedent), not resolved hexes:
  // SVG fill/stroke resolve var() at paint time, so an open chart re-themes the
  // moment data-theme flips instead of keeping the old theme's baked colors.
  // The canvas share card keeps resolved values via _tok (canvas can't do var()).
  function _chartTokens() {
    return { grid: "var(--border, #2b2b31)", axis: "var(--text-tertiary, #7c808a)",
             bar: "var(--accent-gold, #c9a227)", hi: "var(--accent-cyan, #00d9ff)",
             lo: "var(--accent-red, #b91c1c)", text: "var(--text-secondary, #aaa)" };
  }
  function _fmtN(v) {
    if (Math.abs(v) >= 10) return String(Math.round(v));
    return (Math.round(v * 100) / 100).toString();
  }

  // histogram(values, {width,height,bins,min,max,highlightAbove,refs:[{at,label}],aria})
  function histogram(values, o) {
    o = o || {};
    var vals = (values || []).map(Number).filter(function (v) { return !isNaN(v); });
    if (vals.length < 4) return "";
    var W = o.width || 640, H = o.height || 120, pad = 22;
    var lo = o.min != null ? o.min : Math.min.apply(null, vals);
    var hi = o.max != null ? o.max : Math.max.apply(null, vals);
    if (hi <= lo) hi = lo + 1;
    var nb = o.bins || 26, bw = (hi - lo) / nb;
    var counts = new Array(nb).fill(0);
    vals.forEach(function (v) { var i = Math.floor((v - lo) / bw); if (i < 0) i = 0; if (i >= nb) i = nb - 1; counts[i]++; });
    var maxc = Math.max.apply(null, counts) || 1, t = _chartTokens();
    var iw = W - pad * 2, ih = H - pad - 8;
    var bars = counts.map(function (c, i) {
      var x = pad + i / nb * iw, w = Math.max(1, iw / nb - 1), h = c / maxc * ih, y = H - pad - h;
      var mid = lo + (i + 0.5) * bw;
      var col = (o.highlightAbove != null && mid >= o.highlightAbove) ? t.hi : t.bar;
      return '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + h.toFixed(1) + '" fill="' + col + '" opacity="0.82"/>';
    }).join("");
    var refs = (o.refs || []).map(function (r) {
      var x = pad + (r.at - lo) / (hi - lo) * iw;
      return '<line x1="' + x.toFixed(1) + '" y1="' + (H - pad) + '" x2="' + x.toFixed(1) + '" y2="4" stroke="' + t.axis + '" stroke-dasharray="3 3"/>'
        + '<text x="' + (x + 3).toFixed(1) + '" y="12" fill="' + t.axis + '" font-size="9" font-family="monospace">' + esc(r.label) + '</text>';
    }).join("");
    var ax = '<line x1="' + pad + '" y1="' + (H - pad) + '" x2="' + (W - pad) + '" y2="' + (H - pad) + '" stroke="' + t.grid + '"/>'
      + '<text x="' + pad + '" y="' + (H - 5) + '" fill="' + t.axis + '" font-size="9" font-family="monospace">' + esc(_fmtN(lo)) + '</text>'
      + '<text x="' + (W - pad) + '" y="' + (H - 5) + '" fill="' + t.axis + '" font-size="9" font-family="monospace" text-anchor="end">' + esc(_fmtN(hi)) + '</text>';
    return '<svg class="eephus-chart" viewBox="0 0 ' + W + ' ' + H + '" width="100%" preserveAspectRatio="none" role="img" aria-label="' + esc(o.aria || "distribution") + '">' + bars + refs + ax + "</svg>";
  }

  // scatter(points [{x,y,label,color}], {width,height,xLabel,yLabel,xRef,yRef,
  //   xRefLabel,yRefLabel,diag,aria}). Axes carry numeric tick values and the
  //   xRef/yRef reference lines are labeled with their values; diag:true draws
  //   the y = x identity line (only meaningful when both axes share units).
  function scatter(points, o) {
    o = o || {};
    var pts = (points || []).filter(function (p) { return p && !isNaN(p.x) && !isNaN(p.y); });
    if (pts.length < 3) return "";
    var W = o.width || 640, H = o.height || 300, padL = 34, padB = 34, padT = 16, padR = 10;
    var xs = pts.map(function (p) { return p.x; }), ys = pts.map(function (p) { return p.y; });
    var x0 = o.xMin != null ? o.xMin : Math.min.apply(null, xs), x1 = o.xMax != null ? o.xMax : Math.max.apply(null, xs);
    var y0 = o.yMin != null ? o.yMin : Math.min.apply(null, ys), y1 = o.yMax != null ? o.yMax : Math.max.apply(null, ys);
    if (x1 <= x0) x1 = x0 + 1; if (y1 <= y0) y1 = y0 + 1;
    var t = _chartTokens(), iw = W - padL - padR, ih = H - padB - padT;
    var sx = function (x) { return padL + (x - x0) / (x1 - x0) * iw; };
    var sy = function (y) { return padT + (1 - (y - y0) / (y1 - y0)) * ih; };
    var refs = "";
    if (o.xRef != null) {
      refs += '<line x1="' + sx(o.xRef).toFixed(1) + '" y1="' + padT + '" x2="' + sx(o.xRef).toFixed(1) + '" y2="' + (H - padB) + '" stroke="' + t.grid + '" stroke-dasharray="3 3"/>'
        + '<text x="' + (sx(o.xRef) + 3).toFixed(1) + '" y="' + (padT + 9) + '" fill="' + t.axis + '" font-size="9" font-family="monospace">'
        + esc(o.xRefLabel != null ? o.xRefLabel : _fmtN(o.xRef)) + "</text>";
    }
    if (o.yRef != null) {
      refs += '<line x1="' + padL + '" y1="' + sy(o.yRef).toFixed(1) + '" x2="' + (W - padR) + '" y2="' + sy(o.yRef).toFixed(1) + '" stroke="' + t.grid + '" stroke-dasharray="3 3"/>'
        + '<text x="' + (W - padR) + '" y="' + (sy(o.yRef) - 3).toFixed(1) + '" fill="' + t.axis + '" font-size="9" font-family="monospace" text-anchor="end">'
        + esc(o.yRefLabel != null ? o.yRefLabel : _fmtN(o.yRef)) + "</text>";
    }
    if (o.diag) {
      // y = x identity, clipped to the shared domain (fa.js fair-value treatment)
      var d0 = Math.max(x0, y0), d1 = Math.min(x1, y1);
      if (d1 > d0) {
        refs += '<line x1="' + sx(d0).toFixed(1) + '" y1="' + sy(d0).toFixed(1) + '" x2="' + sx(d1).toFixed(1) + '" y2="' + sy(d1).toFixed(1) + '" stroke="' + t.axis + '" stroke-dasharray="5 4"/>'
          + '<text x="' + (sx(d1) - 4).toFixed(1) + '" y="' + (sy(d1) + 12).toFixed(1) + '" fill="' + t.axis + '" font-size="9" font-style="italic" font-family="monospace" text-anchor="end">y = x</text>';
      }
    }
    var dots = pts.map(function (p) {
      return '<circle cx="' + sx(p.x).toFixed(1) + '" cy="' + sy(p.y).toFixed(1) + '" r="' + (p.r || 3) + '" fill="' + (p.color || t.hi) + '" opacity="0.7"><title>' + esc(p.label || "") + "</title></circle>";
    }).join("");
    // numeric tick values (4 per axis) so magnitudes read without hovering dots
    var ticks = "";
    for (var i = 0; i <= 3; i++) {
      var vx = x0 + (x1 - x0) * i / 3, vy = y0 + (y1 - y0) * i / 3;
      var anch = i === 0 ? "start" : (i === 3 ? "end" : "middle");
      ticks += '<text x="' + sx(vx).toFixed(1) + '" y="' + (H - padB + 12) + '" fill="' + t.axis + '" font-size="9" font-family="monospace" text-anchor="' + anch + '">' + esc(_fmtN(vx)) + "</text>"
        + '<text x="' + (padL - 5) + '" y="' + (sy(vy) + 3).toFixed(1) + '" fill="' + t.axis + '" font-size="9" font-family="monospace" text-anchor="end">' + esc(_fmtN(vy)) + "</text>";
    }
    var ax = '<line x1="' + padL + '" y1="' + (H - padB) + '" x2="' + (W - padR) + '" y2="' + (H - padB) + '" stroke="' + t.grid + '"/>'
      + '<line x1="' + padL + '" y1="' + padT + '" x2="' + padL + '" y2="' + (H - padB) + '" stroke="' + t.grid + '"/>'
      + ticks
      + (o.xLabel ? '<text x="' + (W - padR) + '" y="' + (H - 6) + '" fill="' + t.axis + '" font-size="10" font-family="monospace" text-anchor="end">' + esc(o.xLabel) + "</text>" : "")
      + (o.yLabel ? '<text x="4" y="10" fill="' + t.axis + '" font-size="10" font-family="monospace">' + esc(o.yLabel) + "</text>" : "");
    return '<svg class="eephus-chart" viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="' + esc(o.aria || "scatter") + '">' + refs + dots + ax + "</svg>";
  }

  // The module registry for the strip: id -> {label, glyph, href(row)}.
  // Module accents mirror the homepage sidebar glyph identity.
  const MODULES = [
    { id: "prospx", label: "PROSPX", glyph: "●", note: "prospect card",
      href: r => r.prospx ? `/prospx/#player=${encodeURIComponent(r.prospx)}` : null },
    { id: "fa", label: "FREE AGENCY", glyph: "$", note: "market card",
      href: r => r.fa ? `/fa/#player=${encodeURIComponent(r.key)}` : null },
    { id: "mlb", label: "MLB PROJECTIONS", glyph: "Δ", note: "player page",
      // AUDIT 2026-07-18 (A6): only offer the projections chip to players who have a
      // projections page. player_links now tags projection-universe players proj:true;
      // never-debuted prospects get proj:false. Older payloads without the flag
      // (proj===undefined) fall back to the prior key-presence behavior until regen.
      href: r => {
        const has = (r.proj === undefined) ? r.key : r.proj;
        return (has && r.key) ? `/projections/#player=${encodeURIComponent(r.key)}` : null;
      } },
  ];

  // row: {key, mlbam, fa, prospx} (a player_links entry). active: module id.
  function stripHTML(row, active) {
    if (!row) return "";
    const chips = MODULES.map(m => {
      const href = m.href(row);
      if (!href && m.id !== active) return "";
      const cls = m.id === active ? "hub-chip is-active" : "hub-chip";
      const inner = `<span class="hub-glyph">${m.glyph}</span>${m.label}<span class="hub-note">${m.note}</span>`;
      return m.id === active
        ? `<span class="${cls}" title="You are on this player's ${m.note}">${inner}</span>`
        : `<a class="${cls}" href="${href}" title="Open this player's ${m.note}">${inner}</a>`;
    }).filter(Boolean);
    if (chips.length <= 1) return "";
    return `<div class="player-hub-strip" title="One player, every module - the same player across eephus.io surfaces">${chips.join("")}</div>`;
  }

  // ---- unified share card ---------------------------------------------------
  // DE-DUP 2026-07-23: EEPHUS_GFX is the single owner of the token resolver,
  // resolved palette, ramp stops, and theme forcing. These are thin back-compat
  // aliases: they delegate when the GFX module is loaded and keep a minimal
  // local fallback for pages (prospx) that load the hub alone.
  function _tok(name, fallback) {
    if (window.EEPHUS_GFX && window.EEPHUS_GFX.tok) return window.EEPHUS_GFX.tok(name, fallback);
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }
  function _palette(accentTok) {
    if (window.EEPHUS_GFX && window.EEPHUS_GFX.palette) return window.EEPHUS_GFX.palette(accentTok);
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    return {
      dark,
      bg:   _tok("--bg-primary",    dark ? "#101014" : "#F6F1E4"),
      bg2:  _tok("--bg-secondary",  dark ? "#16161B" : "#EFE9D8"),
      fg:   _tok("--text-primary",  dark ? "#ECEEF2" : "#0F1B2D"),
      sub:  _tok("--text-tertiary", dark ? "#7C808A" : "#706B5C"),
      line: _tok("--border",        dark ? "#2B2B31" : "#C9C1AE"),
      accent: _tok(accentTok || "--accent-cyan", dark ? "#00D9FF" : "#0E7C86"),
      pos: dark ? "#4FFF9E" : "#1F7A3A",
      neg: dark ? "#FF6B6B" : "#B91C1C",
      MONO: '"DotGothic16","MS Gothic","MS UI Gothic","Osaka-Mono",monospace',
      ramp: dark
        ? [[0, "#00D9FF"], [0.3, "#B47CFF"], [0.55, "#FF4FD8"], [0.78, "#FFD700"], [1, "#4FFF9E"]]
        : [[0, "#B91C1C"], [0.35, "#C9A227"], [0.65, "#1F7A3A"], [1, "#0E2B4D"]],
    };
  }
  // Canvas fillStyle can't parse CSS var() references; callers historically pass
  // both literal colors and "var(--x, fb)" strings, so resolve the latter here.
  function _color(v, fallback) {
    if (v == null) return fallback;
    const m = /^var\((--[^,)]+)(?:,\s*([^)]+))?\)$/.exec(String(v).trim());
    if (m) return _tok(m[1], (m[2] || fallback || "").trim() || fallback);
    return v;
  }
  function _loadImage(url) {
    return new Promise(resolve => {
      if (!url) return resolve(null);
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = url;
    });
  }

  // ---- card template registry (GFX slice 4, 2026-07-23) ---------------------
  // One declarative layout per card family. Module spec-builders pass
  //   openCard({ template: "<name>", data: {...}, module, accentToken, name,
  //              meta, sub?, headshotURL?, url, filename, caption? })
  // and this registry owns the tile/section assembly each module used to
  // hand-roll. Contract: data LEAVES arrive display-formatted by the module
  // (money/WAR formatting rules genuinely differ per module and must stay
  // there); a template owns STRUCTURE - which tiles exist, their order and
  // labels, section titles, row composition, caps, and color rules. A template
  // returns {tiles, sections} (it may also return hero/sub/caption); whatever
  // it returns wins over the same key on the spec. Layouts are frozen copies
  // of the 2026-07-23 per-module builders - pixel parity is the contract, so
  // treat any composition change here as a visible redesign of every caller.
  const templates = {
    // FA market card (fa.js sharePlayerCard): the predicted market as tiles;
    // rational-vs-price rows + top team fits, then nearest real comps.
    // data: {projYears?, projGuar?, projAav?, dealPlus?, dealWar?, rational?,
    //        surplus?, priorAav?, fits: [{org, blocked, fit}],
    //        comps: [{name, yr, years, guar, to}]}
    "player-market": (d) => {
      const tiles = [];
      if (d.projGuar != null) tiles.push({ label: "projected", value: `${d.projYears != null ? d.projYears + "y/" : ""}${d.projGuar}` });
      if (d.projAav != null) tiles.push({ label: "proj AAV", value: d.projAav });
      if (d.dealPlus != null) tiles.push({ label: "Deal+", value: d.dealPlus });
      if (d.dealWar != null) tiles.push({ label: "deal WAR", value: d.dealWar });
      const fitRows = (d.fits || []).slice(0, 3).map(f =>
        [`fit · ${f.org}${f.blocked ? " (blocked)" : ""}`, String(f.fit)]);
      const sections = [{
        title: "Rational value vs price",
        rows: [
          ["rational value", d.rational != null ? d.rational : DASH],
          ["contract surplus", d.surplus != null ? d.surplus : DASH],
          d.priorAav != null ? ["prior AAV", d.priorAav] : null,
        ].filter(Boolean).concat(fitRows),
      }];
      const comps = (d.comps || []).slice(0, 5);
      if (comps.length) {
        sections.push({ title: "Nearest real comps",
          rows: comps.map(c => [`${c.name || "?"}${c.yr ? ` '${String(c.yr).slice(2)}` : ""}`,
            `${c.years != null ? c.years + "y / " : ""}${c.guar != null ? c.guar : "-"}${c.to ? `  ${c.to}` : ""}`]) });
      }
      return { tiles, sections };
    },
    // MLB projection card (projections.js shareMlbCard): projection band +
    // surplus + skill "+" stats as tiles; the season WAR path, then the
    // pitcher arsenal OR (hitters / no arsenal) Statcast percentiles.
    // data: {warYears, warTotal?, surplus?: {value, neg}, swingPlus?,
    //        aaaStuffPlus?, projAav?, firstSeason, lastSeason,
    //        warRows: [{season, war, band?}],
    //        arsenal: [{pitch, usageWhiff}], statcast?: {season, metrics}}
    "player-projection": (d) => {
      const tiles = [];
      if (d.warTotal != null) tiles.push({ label: `${d.warYears}y WAR`, value: d.warTotal });
      if (d.surplus) tiles.push({ label: "Surplus", value: d.surplus.value,
                                  color: d.surplus.neg ? "var(--down)" : undefined });
      if (d.swingPlus != null) tiles.push({ label: "Swing+", value: d.swingPlus });
      if (d.aaaStuffPlus != null) tiles.push({ label: "aStuff+", value: d.aaaStuffPlus });
      if (d.projAav != null) tiles.push({ label: "proj AAV", value: d.projAav });
      const sections = [];
      if ((d.warRows || []).length) {
        sections.push({ title: `Projected bWAR ${d.firstSeason}-${d.lastSeason}`,
          rows: d.warRows.map(r => [r.season, `${r.war}${r.band ? `  (${r.band})` : ""}`]) });
      }
      if ((d.arsenal || []).length) {
        sections.push({ title: "Pitch arsenal · usage / whiff",
          rows: d.arsenal.slice(0, 6).map(a => [a.pitch, a.usageWhiff]) });
      } else if (d.statcast && (d.statcast.metrics || []).length) {
        sections.push({ title: `Statcast percentiles · ${d.statcast.season}`,
          rows: d.statcast.metrics.map(m => [m.label, `${m.value}  (${m.pct})`]) });
      }
      return { tiles, sections };
    },
    // Two-subject compare card (projections.js head-to-head): no tile rail,
    // one column per subject. data: {columns: [{title, rows}, {title, rows}]}
    "compare": (d) => ({
      tiles: [],
      sections: (d.columns || []).slice(0, 2).map(c => ({ title: c.title, rows: c.rows })),
    }),
    // Trade Machine deal card: totals/gap/verdict tiles, one section per side,
    // each asset row "name  [grade]" -> value (negative values in the down
    // color). data: {sideA: {total, assets: [{name, grade, value, neg}]},
    //                sideB: {...}, gap, verdict}
    "deal": (d) => {
      const a = d.sideA || {}, b = d.sideB || {};
      const asset = x => [`${String(x.name || "?")}${x.grade ? `  [${x.grade}]` : ""}`,
        x.value, x.neg ? "var(--down)" : undefined];
      return {
        tiles: [
          { label: "Side A", value: a.total },
          { label: "Side B", value: b.total },
          { label: "Gap", value: d.gap },
          { label: "Verdict", value: d.verdict },
        ],
        sections: [
          { title: "Side A receives", rows: (a.assets || []).map(asset) },
          { title: "Side B receives", rows: (b.assets || []).map(asset) },
        ],
      };
    },
    // Leaderboard-subject card (CollegeSavant hitter + pitcher profiles):
    // headline stat tiles pass through; one percentile section vs the
    // qualified pool. data: {stats: [{label, value}], poolSize, poolNoun,
    //                        percentiles: [{label, value, pct}]}
    "leaderboard-subject": (d) => ({
      tiles: (d.stats || []).slice(0, 6),
      sections: [{
        title: `Percentiles · vs ${d.poolSize} qualified ${d.poolNoun}`,
        rows: (d.percentiles || []).slice(0, 8).map(p => [p.label, `${p.value}  (${p.pct})`]),
      }],
    }),
  };
  // Resolve {template, data} specs into plain drawCard opts; pass-through for
  // specs that already carry tiles/sections (prospx's own builder, callers
  // predating slice 4). Unknown template names fall through unchanged so a
  // stale page at worst draws an empty card body, never throws.
  function resolveTemplate(opts) {
    if (!opts || !opts.template || typeof templates[opts.template] !== "function") return opts;
    const out = Object.assign({}, opts, templates[opts.template](opts.data || {}));
    delete out.template;
    delete out.data;
    return out;
  }

  // opts: {module, accentToken?, name, meta, sub?, headshotURL?, url,
  //        filename, tiles: [{label, value, color?}] (<=6),
  //        sections: [{title, rows: [[label, value, color?], ...]}] (<=2),
  //        caption?}
  //        - or the declarative {template, data} form (see templates above).
  async function drawCard(opts) {
    opts = resolveTemplate(opts);
    const W = 1200, H = 675, PAD = 48;
    // 2x supersample (the EEPHUS_GFX board treatment): backing store at 2x,
    // all geometry in logical W x H coordinates via ctx.scale.
    const SCALE = (window.EEPHUS_GFX && window.EEPHUS_GFX.SCALE) || 2;
    const c = document.createElement("canvas");
    c.width = W * SCALE; c.height = H * SCALE;
    const g = c.getContext("2d");
    g.scale(SCALE, SCALE);
    const P = _palette(opts.accentToken || "--accent-cyan");
    const bg = P.bg, bg2 = P.bg2, fg = P.fg, sub = P.sub, line = P.line,
          accent = P.accent, MONO = P.MONO;
    g.fillStyle = bg; g.fillRect(0, 0, W, H);

    // header: brand + module eyebrow + date, iridescent rule under
    g.fillStyle = fg; g.font = `700 26px ${MONO}`;
    g.fillText("EEPHUS.IO", PAD, 52);
    g.fillStyle = accent; g.font = `700 22px ${MONO}`;
    g.fillText(String(opts.module || "").toUpperCase(), PAD + 190, 52);
    const today = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    g.fillStyle = sub; g.font = `15px ${MONO}`;
    g.fillText(today, W - PAD - g.measureText(today).width, 52);
    const ramp = g.createLinearGradient(PAD, 0, W - PAD, 0);
    P.ramp.forEach(([s, col]) => ramp.addColorStop(s, col));
    g.fillStyle = ramp; g.fillRect(PAD, 70, W - 2 * PAD, 3);

    // hero: headshot (when CORS lets us) + name + meta
    const img = await _loadImage(opts.headshotURL);
    let heroX = PAD;
    if (img) {
      const S = 132;
      g.save();
      g.fillStyle = bg2; g.fillRect(PAD, 100, S, S);
      g.drawImage(img, PAD, 100, S, S);
      g.strokeStyle = accent; g.lineWidth = 3;
      g.strokeRect(PAD, 100, S, S);
      g.restore();
      heroX = PAD + S + 26;
    }
    // tile rail (right-aligned over the hero band); caps at 6 tiles - beyond 4
    // the rail switches to a compact scale so it stays clear of the hero name
    const tiles = (opts.tiles || []).slice(0, 6);
    const compact = tiles.length > 4;
    const tvFont = compact ? 20 : 24, tvMin = compact ? 64 : 86,
          tvPad = compact ? 20 : 28, tGap = compact ? 8 : 10;
    let tx = W - PAD;
    for (let i = tiles.length - 1; i >= 0; i--) {
      const t = tiles[i];
      g.font = `700 ${tvFont}px ${MONO}`;
      const vw = Math.max(g.measureText(String(t.value)).width, tvMin) + tvPad;
      tx -= vw;
      g.fillStyle = bg2; g.fillRect(tx, 96, vw, 64);
      g.strokeStyle = line; g.lineWidth = 1; g.strokeRect(tx, 96, vw, 64);
      g.fillStyle = sub; g.font = `700 11px ${MONO}`;
      g.fillText(String(t.label).toUpperCase(), tx + 10, 116);
      g.fillStyle = _color(t.color, fg) || fg; g.font = `700 ${tvFont}px ${MONO}`;
      g.fillText(String(t.value), tx + 10, 146);
      tx -= tGap;
    }

    // hero name shrinks to fit the space left of the tile rail (long names used
    // to run under the tiles); meta/sub sit below the rail band, so only the
    // name needs the clamp
    const nameMax = (tiles.length ? tx : W - PAD) - 18 - heroX;
    let nameSize = 40;
    g.font = `700 ${nameSize}px ${MONO}`;
    while (nameSize > 24 && g.measureText(opts.name || "").width > nameMax) {
      nameSize -= 2;
      g.font = `700 ${nameSize}px ${MONO}`;
    }
    g.fillStyle = fg;
    g.fillText(opts.name || "", heroX, 142);
    g.fillStyle = sub; g.font = `17px ${MONO}`;
    g.fillText(opts.meta || "", heroX, 174);
    if (opts.sub) {
      g.fillStyle = accent; g.font = `700 15px ${MONO}`;
      g.fillText(opts.sub, heroX, 202);
    }

    // sections: up to two columns of label/value rows
    const secs = (opts.sections || []).slice(0, 2);
    const colW = (W - 2 * PAD - 36) / Math.max(1, secs.length);
    secs.forEach((s, si) => {
      const x = PAD + si * (colW + 36);
      let y = 268;
      g.fillStyle = sub; g.font = `700 14px ${MONO}`;
      g.fillText(String(s.title).toUpperCase(), x, y);
      g.strokeStyle = line; g.beginPath();
      g.moveTo(x, y + 10); g.lineTo(x + colW, y + 10); g.stroke();
      y += 44;
      (s.rows || []).slice(0, 8).forEach(([label, value, color]) => {
        g.fillStyle = sub; g.font = `15px ${MONO}`;
        g.fillText(String(label), x, y);
        g.fillStyle = _color(color, fg) || fg; g.font = `700 17px ${MONO}`;
        const v = String(value);
        g.fillText(v, x + colW - g.measureText(v).width, y);
        y += 36;
      });
    });

    // footer: caption + url left, watermark right
    if (opts.caption) {
      g.fillStyle = sub; g.font = `13px ${MONO}`;
      g.fillText(opts.caption, PAD, H - 56);
    }
    g.fillStyle = fg; g.font = `700 16px ${MONO}`;
    g.fillText(opts.url || "eephus.io", PAD, H - 28);
    g.fillStyle = sub; g.font = `700 13px ${MONO}`;
    const wm = "eephus.io";
    g.fillText(wm, W - PAD - g.measureText(wm).width, H - 28);

    return c;
  }

  // Export any canvas (board or card) as a PNG. action 'copy' -> clipboard,
  // 'share' -> Web Share (mobile), else download. Shared by shareCard and the
  // GFX modal so all three surfaces export through one code path.
  function exportCanvas(c, opts) {
    opts = opts || {};
    return new Promise(resolve => {
      c.toBlob(async blob => {
        if (opts.action === "copy" && navigator.clipboard
            && typeof ClipboardItem !== "undefined") {
          try {
            await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
            resolve("copied");
            return;
          } catch (e) { /* fall through to download */ }
        }
        if (opts.action === "share" && navigator.canShare && blob) {
          try {
            const file = new File([blob], opts.filename || "eephus-card.png", { type: "image/png" });
            if (navigator.canShare({ files: [file] })) {
              await navigator.share({ files: [file], title: opts.shareTitle || "eephus.io" });
              resolve("shared");
              return;
            }
          } catch (e) { /* fall through to download */ }
        }
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = opts.filename || "eephus-player-card.png";
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 5000);
        resolve(true);
      }, "image/png");
    });
  }

  async function shareCard(opts) {
    return exportCanvas(await drawCard(opts), opts);
  }

  // One shared "open the card modal" helper (DE-DUP 2026-07-23): fa.js,
  // projections.js, trademachine.js, and the CollegeSavant apps all carried a
  // verbatim copy of this wrapper. Opens the shared Generate GFX modal when the
  // module is loaded; falls back to the legacy direct shareCard download when
  // it isn't (prospx keeps its own builder - untouched).
  function openCard(opts) {
    opts = resolveTemplate(opts);   // {template, data} -> plain drawCard opts
    if (window.EEPHUS_GFX) {
      window.EEPHUS_GFX.open({ kind: "card", module: opts.module, accentToken: opts.accentToken,
        title: opts.name, filenameBase: (opts.filename || "eephus-card").replace(/\.png$/, ""), card: opts });
    } else {
      shareCard(opts);
    }
  }

  // Shared display helpers so every surface formats the site's headline values
  // the same way (FV rounding, money, and the missing-data glyph had each drifted
  // into per-module copies that disagreed).
  var DASH = " - ";
  function dash(v, fn) {  // the missing-data glyph, or fn(v) when v is present
    return (v === null || v === undefined || v === "" ||
            (typeof v === "number" && !isFinite(v))) ? DASH : (fn ? fn(v) : v);
  }
  function fvCeil(v) {    // FV / 20-80 grades DISPLAY rounded up (never nearest)
    if (v === null || v === undefined || !isFinite(v)) return null;
    return Math.ceil(v - 1e-9);  // epsilon guards float noise (45.0000001 stays 45)
  }
  function money(mm, decimals) {  // $ millions with the sign BEFORE the $ (-$4.2M)
    if (mm === null || mm === undefined || !isFinite(mm)) return DASH;
    var d = (decimals == null) ? 1 : decimals;
    return (mm < 0 ? "-" : "") + "$" + Math.abs(mm).toFixed(d) + "M";
  }

  window.EEPHUS_HUB = { links, stripHTML, shareCard, drawCard, exportCanvas, openCard, templates, esc, teamLogo, histogram, scatter, fvCeil, money, dash, DASH };
})();
