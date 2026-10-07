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

  // ---- shared club table: code, ESPN logo slug, name, MLBAM id ----------------
  // THE one club resolver for the served pages. Keyed on the FanGraphs codes the
  // prospect side treats as canonical (trades.canonical_org), with every alias a
  // source spells differently folded in: the MLB StatsAPI codes the MLB modules
  // use (AZ, CWS, KC, SD, SF, TB, WSH), the pre-2025 Athletics code OAK and the
  // pre-2012 Marlins code FLA (both map to the club that franchise is today, as
  // canonical_org does). A join that misses an alias fails silently, so every
  // alias resolves here or it resolves nowhere. Logos are the ESPN CDN images
  // PROSPX already serves.
  var _CLUB_ROWS = [
    // [code, ESPN slug, full name, MLBAM id, aliases...]
    ["ARI", "ari", "Arizona Diamondbacks", 109, "AZ"],
    ["ATH", "ath", "Athletics", 133, "OAK"],
    ["ATL", "atl", "Atlanta Braves", 144],
    ["BAL", "bal", "Baltimore Orioles", 110],
    ["BOS", "bos", "Boston Red Sox", 111],
    ["CHC", "chc", "Chicago Cubs", 112],
    ["CHW", "chw", "Chicago White Sox", 145, "CWS"],
    ["CIN", "cin", "Cincinnati Reds", 113],
    ["CLE", "cle", "Cleveland Guardians", 114],
    ["COL", "col", "Colorado Rockies", 115],
    ["DET", "det", "Detroit Tigers", 116],
    ["HOU", "hou", "Houston Astros", 117],
    ["KCR", "kc", "Kansas City Royals", 118, "KC"],
    ["LAA", "laa", "Los Angeles Angels", 108],
    ["LAD", "lad", "Los Angeles Dodgers", 119],
    ["MIA", "mia", "Miami Marlins", 146, "FLA"],
    ["MIL", "mil", "Milwaukee Brewers", 158],
    ["MIN", "min", "Minnesota Twins", 142],
    ["NYM", "nym", "New York Mets", 121],
    ["NYY", "nyy", "New York Yankees", 147],
    ["PHI", "phi", "Philadelphia Phillies", 143],
    ["PIT", "pit", "Pittsburgh Pirates", 134],
    ["SDP", "sd", "San Diego Padres", 135, "SD"],
    ["SEA", "sea", "Seattle Mariners", 136],
    ["SFG", "sf", "San Francisco Giants", 137, "SF"],
    ["STL", "stl", "St. Louis Cardinals", 138],
    ["TBR", "tb", "Tampa Bay Rays", 139, "TB"],
    ["TEX", "tex", "Texas Rangers", 140],
    ["TOR", "tor", "Toronto Blue Jays", 141],
    ["WSN", "wsh", "Washington Nationals", 120, "WSH"],
  ];
  // Former full names a payload can still carry for the same franchise.
  var _CLUB_OLD_NAMES = {
    "oakland athletics": "ATH", "florida marlins": "MIA", "cleveland indians": "CLE",
    "tampa bay devil rays": "TBR", "anaheim angels": "LAA", "los angeles angels of anaheim": "LAA",
  };
  // LOGO SIZE (QCLP05, 2026-10-02). The 500 x 500 master PNG is 19 to 80 KB
  // and these marks are drawn at 16 to 17 px: /arbitration/ pulled 27 of them,
  // 1.06 MB, half its wire. ESPN's combiner serves the same image resized, so
  // a logo is asked for at twice the drawn size (34 px for the 17 px row mark,
  // about 1.7 KB). A caller drawing a bigger mark passes its own size.
  var LOGO_PX = 34;
  function _logoSrc(slug, px) {
    var n = Math.max(16, Math.round(+px || LOGO_PX));
    return "https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/" + slug + ".png&h=" + n + "&w=" + n;
  }
  // Null-prototype maps read through _own(): a plain object answered
  // club("constructor") with Object off the prototype, and a hash-fed input
  // can reach this function.
  var _CLUB_BY = Object.create(null), _CLUB_BY_ID = Object.create(null), _CLUB_BY_NAME = Object.create(null);
  function _own(m, k) { return Object.prototype.hasOwnProperty.call(m, k) ? m[k] : null; }
  _CLUB_ROWS.forEach(function (r) {
    var c = { code: r[0], slug: r[1], name: r[2], id: r[3], aliases: r.slice(4),
              logo: _logoSrc(r[1]) };
    _CLUB_BY[r[0]] = c;
    c.aliases.forEach(function (a) { _CLUB_BY[a] = c; });
    _CLUB_BY_ID[r[3]] = c;
    _CLUB_BY_NAME[r[2].toLowerCase()] = c;
  });
  Object.keys(_CLUB_OLD_NAMES).forEach(function (n) { _CLUB_BY_NAME[n] = _CLUB_BY[_CLUB_OLD_NAMES[n]]; });
  // club(x): a club code in either family, an MLBAM team id (number or digit
  // string) or a full club name -> {code, slug, name, id, aliases, logo}, or
  // null when x is not one of the thirty (a college, an overseas club, "all").
  // Exact keys only: no nickname, substring or suffix matching, so "Texas",
  // "Worcester Red Sox" and "ACL D-backs" resolve to nothing, never a guess.
  function club(x) {
    if (x == null || x === "") return null;
    if (typeof x === "number") return _own(_CLUB_BY_ID, x);
    var s = String(x).trim();
    if (!s) return null;
    if (/^\d+$/.test(s)) return _own(_CLUB_BY_ID, +s);
    return _own(_CLUB_BY, s.toUpperCase()) || _own(_CLUB_BY_NAME, s.toLowerCase());
  }
  function clubs() { return _CLUB_ROWS.map(function (r) { return _CLUB_BY[r[0]]; }); }
  // ---- club links (owner ask 9): the one href builder for a club mention -----
  // clubHref(x, ctx): "" when club(x) is null; ctx "farm" -> the PROSPX farm
  // system page, anything else -> the Franchises club page. The href always
  // carries the canonical code, so an alias (CWS, OAK) lands on its club.
  // build_site._club_href is the server mirror and reads this same table.
  function clubHref(x, ctx) {
    var c = club(x);
    if (!c) return "";
    return (ctx === "farm" ? "/prospx/#farm-org=" : "/franchise/#team=") + c.code;
  }
  // clubLinkHTML(x, opts): an <a class="club-link"> for a club mention.
  //   opts.ctx   "franchise" (default) | "farm"
  //   opts.text  "code" (default) | "name" | the string the surface prints today;
  //              "" with opts.logo makes a logo-only link (the logo's alt is the
  //              full club name; beside text the logo's alt is empty)
  //   opts.logo  true only where the surface already shows a logo
  //   opts.stop  true inside a clickable row (the click stays on the link)
  // Unresolved input keeps its escaped text in a span marked
  // data-club-nolink="unresolved"; it is never linked to a guessed club.
  function clubLinkHTML(x, opts) {
    var o = opts || {};
    var c = club(x);
    var t = o.text == null ? "code" : String(o.text);
    if (!c) {
      var raw = t === "code" || t === "name" ? (x == null ? "" : String(x)) : t;
      return raw ? '<span data-club-nolink="unresolved">' + esc(raw) + "</span>" : "";
    }
    var label = t === "code" ? c.code : t === "name" ? c.name : t;
    if (!label && !o.logo) label = c.code;
    var farm = o.ctx === "farm";
    var title = c.name + (farm ? ": farm system" : ": franchise overview");
    var logoOnly = !!o.logo && !label;
    // A logo-only link that loses its image falls back to the code, so it
    // never becomes an empty link.
    var img = o.logo
      ? '<img class="club-link-logo" src="' + esc(c.logo) + '" alt="' + (logoOnly ? esc(c.name) : "")
        + '" loading="lazy" onerror="' + (logoOnly ? "this.outerHTML='<span>" + c.code + "</span>'" : "this.remove()") + '">'
      : "";
    return '<a class="club-link' + (logoOnly ? " club-link--logo-only" : "") + '" href="'
      + clubHref(c.code, farm ? "farm" : "franchise") + '" data-club="' + c.code + '" title="' + esc(title) + '"'
      + (o.stop ? ' onclick="event.stopPropagation()"' : "") + ">"
      + img + (label ? "<span>" + esc(label) + "</span>" : "") + "</a>";
  }
  // teamLogoURL(team, px): the logo at px pixels square (default 34).
  function teamLogoURL(team, px) {
    var c = club(team);
    return c ? _logoSrc(c.slug, px) : "";
  }
  // teamLogo(team, cls, opts): opts.size is the requested pixel size (twice
  // the drawn size; default 34). opts.decorative gives alt="" for a caller
  // that prints the club code right after the mark, so a screen reader does
  // not hear the code twice (QCLA16); every other caller keeps alt = code.
  function teamLogo(team, cls, opts) {
    if (!team) return "";
    opts = opts || {};
    var c = club(team);
    var slug = c ? c.slug : String(team).toLowerCase();
    return '<img class="' + (cls || "eephus-teamlogo") + '" src="' + esc(_logoSrc(slug, opts.size))
      + '" alt="' + (opts.decorative ? "" : esc(team)) + '" loading="lazy" onerror="this.remove()">';
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
    return `<div class="player-hub-strip" title="This player on every eephus.io module">${chips.join("")}</div>`;
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
      sub:  _tok("--text-tertiary", dark ? "#868A95" : "#6B6657"),
      line: _tok("--border",        dark ? "#2B2B31" : "#C9C1AE"),
      accent: _tok(accentTok || "--accent-cyan", dark ? "#00D9FF" : "#0E7C86"),
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
        sections.push({ title: `Projected WAR ${d.firstSeason}-${d.lastSeason} (fWAR basis)`,
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
  // Canvas text never waits for a webfont: an unloaded face falls silently
  // through to the next family in MONO, so a cold first card rasterises in a
  // different letterform than every card after it. Since 2026-08-07 that is a
  // Windows risk too, not just an Apple one - PixelMplus12 leads --font-logo, so
  // every platform now downloads it instead of matching a system face.
  // Deliberately awaited in drawCard rather than in shareCard: the GFX modal and
  // the legacy direct-download path both land here, and only one of them used to
  // wait. Resolves on failure - a missing webfont should degrade, not block.
  // Two specs cover the surface: fonts.load matches family and weight, never the
  // size its shorthand syntax forces you to supply.
  let _fontsReady = null;
  function awaitFonts() {
    if (_fontsReady) return _fontsReady;
    if (!document.fonts || !document.fonts.load) return (_fontsReady = Promise.resolve());
    const jobs = ["700 26px PixelMplus12", "400 26px PixelMplus12"].map(s => {
      try { return document.fonts.load(s).catch(() => {}); }
      catch (e) { return Promise.resolve(); }
    });
    if (document.fonts.ready) jobs.push(document.fonts.ready.catch(() => {}));
    // Never let a hung font request hold an export hostage.
    const timeout = new Promise(r => setTimeout(r, 4000));
    _fontsReady = Promise.race([Promise.all(jobs), timeout]);
    return _fontsReady;
  }

  async function drawCard(opts) {
    await awaitFonts();
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
      // CONTRACT (2026-08-04d): `opts.headshotURL` MUST already be a SQUARE
      // crop. Canvas drawImage has no object-fit, so this call stretches
      // whatever it is handed into SxS - and MLB source headshots are 480x720
      // (2:3), which came out as a vertically squashed face on every card.
      // The fix lives at the callers, which now ask the CDN for the exact box
      // via `c_fill,g_face,w_264,h_264` (Cloudinary crops around the detected
      // face and returns exactly that size). Do NOT "fix" it here with cover
      // math: that would re-crop an already-correct crop.
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

  window.EEPHUS_HUB = { links, stripHTML, shareCard, drawCard, exportCanvas, openCard, templates, esc, teamLogo, teamLogoURL, club, clubs, clubHref, clubLinkHTML, histogram, scatter, fvCeil, money, dash, DASH };
})();
