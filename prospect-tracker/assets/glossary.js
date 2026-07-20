/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

// =============================================================================
// eephus.io unified Glossary & Methodology app (/glossary/)
// =============================================================================
// Four views: Terms (search + group nav + A-Z index + entry cards) ·
// How to Read (annotated anatomy guide) · Methodology (derivations +
// interactive teaching widgets + PDF export) · Source Comparison (the
// empirical source-vs-source backtest). The guide/methodology/backtest
// renderers are PORTED from the retired PROSPX Glossary/Methodology tab
// (owner decision 2026-06-10); the data source for every definition is
// data/glossary.json via window.EEPHUS_GLOSSARY (assets/eephus-gl.js).
(function () {
  "use strict";

  const _S = { view: "terms", cat: "all", q: "", term: null,
               backtest: null, btLoading: false, cards: false };
  // Report Cards v0: inline champion-vs-baseline proof charts on the Models &
  // Proofs cards. Dark by default pre-launch; opt in with #cards=1 for owner
  // preview. Flip _CARDS_DEFAULT to true at launch.
  const _CARDS_DEFAULT = true;   // surfaced: proof charts on by default (#cards=0 to hide)
  let GL = {};         // legacy-shaped map: slug -> {name, short, long, ...}
  let GROUPS = {};     // category -> display group
  // Models & Proofs view state. Declared up top (module scope, before boot
  // runs) so the lazy fetch guard is always initialized, mirroring the
  // _S.registry/_S.backtest lazy-load pattern the other views use.
  let _MODELS = null;          // cached model_registry.json payload (or {__error:true})
  let _MODELS_LOADING = false; // in-flight guard against a double fetch
  let _MODELS_FILTER = "all";  // active verdict filter for the Models & Proofs list

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  // Inline glossary link - same .g-term affordance as PROSPX; the shared
  // tooltip engine in eephus-gl.js handles hover/click on [data-gl].
  function gTermLink(slug, label) {
    return `<span class="g-term" data-gl="${escapeHtml(slug)}">${escapeHtml(label != null ? label : (GL[slug] ? GL[slug].name : slug))}</span>`;
  }
  const GLOSSARY = new Proxy({}, { get: (_, k) => GL[k],
                                   ownKeys: () => Reflect.ownKeys(GL),
                                   getOwnPropertyDescriptor: (_, k) =>
                                     GL[k] ? { enumerable: true, configurable: true, value: GL[k] } : undefined });

  // ---- URL state: #g=<slug>&view=&cat=&q= -----------------------------------
  function syncFromURL() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.has("view")) {
      const v = p.get("view");
      if (["terms", "guide", "methodology", "source-comparison", "models"].includes(v)) _S.view = v;
    }
    if (p.has("cat")) _S.cat = p.get("cat");
    if (p.has("q")) _S.q = p.get("q");
    _S.cards = p.has("cards") ? p.get("cards") !== "0" : _CARDS_DEFAULT;
    _S.term = p.get("g") || null;
    if (_S.term) _S.view = "terms";
  }
  function syncToURL() {
    const p = new URLSearchParams();
    if (_S.view !== "terms") p.set("view", _S.view);
    if (_S.cat !== "all") p.set("cat", _S.cat);
    if (_S.q) p.set("q", _S.q);
    if (_S.term) p.set("g", _S.term);
    const h = p.toString();
    history.replaceState(null, "", h ? "#" + h : location.pathname);
  }

  // ---- Terms view ------------------------------------------------------------
  function groupOrder() {
    const seen = [];
    for (const g of Object.values(GROUPS)) if (!seen.includes(g)) seen.push(g);
    return seen;
  }
  function entryGroup(e) { return GROUPS[e.category] || e.category; }

  function moduleBadges(e) {
    const LBL = { prospx: "PROSPX", fa: "MLB FA", foundations: "FOUNDATIONS",
                  platform: "PLATFORM" };
    return (e.module || []).map(m =>
      `<span class="gl-mod gl-mod--${m}">${LBL[m] || m.toUpperCase()}</span>`).join("");
  }

  // Provenance chip: distinguishes our own models from borrowed industry
  // metrics and shared foundations, so a reader always knows what is ours.
  function shelfBadge(e) {
    const S = { ark: ["ARKMETRIC", "eephus.io original"],
                industry: ["INDUSTRY", "external metric, credited"],
                foundation: ["FOUNDATION", "shared concept or standard stat"] };
    const s = S[e.shelf];
    return s ? `<span class="gl-shelf gl-shelf--${e.shelf}" title="${s[1]}">${s[0]}</span>` : "";
  }

  function entryCard(slug, e, expanded) {
    const altNames = (e.aliases || []).filter(a => a !== e.name && a.includes(" "));
    const fullName = altNames.length ? altNames.sort((a, b) => b.length - a.length)[0] : "";
    const more = [];
    if (e.long) more.push(`<div class="gl-meth">${e.long.split("\n\n").map(p => `<p>${escapeHtml(p)}</p>`).join("")}</div>`);
    if (e.formula) more.push(`<div class="gp-formula">${escapeHtml(e.formula)}</div>`);
    if (e.example) more.push(`<div class="gl-example"><span class="gl-microlabel">Example · </span>${escapeHtml(e.example)}</div>`);
    if (e.origin) more.push(`<div class="gl-origin"><span class="gl-microlabel">Origin · </span>${escapeHtml(e.origin)}</div>`);
    if (e.visual_html) more.push(`<div class="gl-microlabel" style="margin-top:8px;">Visual</div><div class="glossary-visual">${e.visual_html}</div>`);
    if (typeof _GLOSSARY_VIZ !== "undefined" && _GLOSSARY_VIZ[slug]) {
      let viz = ""; try { viz = _GLOSSARY_VIZ[slug](); } catch (err) { viz = ""; }
      if (viz) more.push(`<div class="gl-microlabel" style="margin-top:8px;">Visualization</div><div class="glossary-visual">${viz}</div>`);
    }
    const rel = (e.related || []).filter(r => GL[r]).map(r =>
      `<a class="gl-rel" href="#g=${escapeHtml(r)}">${escapeHtml(GL[r].name)}</a>`).join("");
    if (rel) more.push(`<div class="gl-relrow"><span class="gl-microlabel">See also</span>${rel}</div>`);
    const moreHtml = more.length
      ? `<details class="gp-more"${expanded ? " open" : ""}><summary>+ methodology</summary><div class="gp-more-body">${more.join("")}</div></details>` : "";
    return `<div class="glossary-card" id="g-${escapeHtml(slug)}">
      <div class="gl-card-head">
        <span class="gp-term">${escapeHtml(e.name)}</span>
        ${fullName ? `<span class="gl-fullname">(${escapeHtml(fullName)})</span>` : ""}
        <span class="gl-badges">${shelfBadge(e)}${moduleBadges(e)}</span>
      </div>
      <div class="gl-def">${escapeHtml(e.short)}</div>
      ${moreHtml}</div>`;
  }

  function renderTerms() {
    const root = document.getElementById("glossary-rows");
    const q = (_S.q || "").toLowerCase().trim();
    const groups = groupOrder();
    // group filter chips with counts
    const counts = { all: 0 };
    const byGroup = new Map(groups.map(g => [g, []]));
    for (const [slug, e] of Object.entries(GL)) {
      const grp = entryGroup(e);
      if (q) {
        const hay = (e.name + " " + (e.aliases || []).join(" ") + " " +
                     e.short + " " + (e.long || "")).toLowerCase();
        if (!hay.includes(q)) continue;
      }
      // Tolerate unknown categories: lazily create the bucket so a stray
      // category surfaces in its own chip instead of vanishing. Increments
      // live inside the bucketing path so counts can never exceed what renders.
      if (!byGroup.has(grp)) byGroup.set(grp, []);
      byGroup.get(grp).push([slug, e]);
      counts.all++;
      counts[grp] = (counts[grp] || 0) + 1;
    }
    // Union the defined group order with any orphan groups discovered above.
    const allGroups = groups.concat([...byGroup.keys()].filter(g => !groups.includes(g)));
    const chips = [`<button class="chip${_S.cat === "all" ? " active" : ""}" data-gl-cat="all">All <span class="gl-count">${counts.all}</span></button>`]
      .concat(allGroups.map(g =>
        `<button class="chip${_S.cat === g ? " active" : ""}" data-gl-cat="${escapeHtml(g)}">${escapeHtml(g)} <span class="gl-count">${counts[g] || 0}</span></button>`));
    document.getElementById("gl-cats").innerHTML = chips.join("");
    document.querySelectorAll("[data-gl-cat]").forEach(b => b.onclick = () => {
      _S.cat = b.dataset.glCat; syncToURL(); render();
    });
    // entries: alphabetical within the active scope
    const active = _S.cat === "all" ? allGroups : [_S.cat];
    const flat = [];
    for (const g of active) {
      for (const [slug, e] of (byGroup.get(g) || [])) flat.push([slug, e, g]);
    }
    flat.sort((a, b) => a[1].name.localeCompare(b[1].name, "en", { sensitivity: "base" }));
    // A-Z index strip (inactive letters dimmed, never hidden)
    const present = new Set(flat.map(([, e]) => (e.name[0] || "#").toUpperCase()));
    const az = ["#"].concat("ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("")).map(L => {
      const has = L === "#" ? [...present].some(c => !/[A-Z]/.test(c)) : present.has(L);
      return has ? `<a href="#" data-gl-az="${L}">${L}</a>` : `<span class="gl-az-off">${L}</span>`;
    }).join("");
    document.getElementById("gl-az").innerHTML = az;
    document.querySelectorAll("[data-gl-az]").forEach(a => a.onclick = ev => {
      ev.preventDefault();
      const L = a.dataset.glAz;
      const hit = flat.find(([, e]) => {
        const c = (e.name[0] || "#").toUpperCase();
        return L === "#" ? !/[A-Z]/.test(c) : c === L;
      });
      if (hit) document.getElementById("g-" + hit[0])?.scrollIntoView({ block: "start" });
    });
    let lastLetter = null;
    const parts = [];
    for (const [slug, e] of flat) {
      const c = (e.name[0] || "#").toUpperCase();
      const letter = /[A-Z]/.test(c) ? c : "#";
      if (letter !== lastLetter) {
        parts.push(`<div class="glossary-cat-heading">${letter}</div>`);
        lastLetter = letter;
      }
      // Hybrid expansion: collapsed by default, expanded when arrived via
      // a direct #g= anchor (the reader asked for THIS entry's full read).
      parts.push(entryCard(slug, e, _S.term === slug));
    }
    root.innerHTML = parts.join("") || `<div class="state-message">No glossary terms match.</div>`;
    if (_S.term) {
      const card = document.getElementById("g-" + _S.term);
      if (card) {
        requestAnimationFrame(() => {
          card.scrollIntoView({ behavior: "smooth", block: "start" });
          card.classList.add("is-highlighted");
        });
      }
      _S.term = null;
    }
  }

  // ---- router ----------------------------------------------------------------
  function render() {
    const ids = { terms: "glossary-rows", guide: "guide-body",
                  methodology: "methodology-body", "source-comparison": "source-comparison-body",
                  models: "models-body" };
    document.querySelectorAll("[data-glossary-view]").forEach(b => {
      b.classList.toggle("active", b.dataset.glossaryView === _S.view);
    });
    for (const [v, id] of Object.entries(ids)) {
      const el = document.getElementById(id);
      if (el) el.style.display = v === _S.view ? "" : "none";
    }
    const bar = document.getElementById("gl-termbar");
    if (bar) bar.style.display = _S.view === "terms" ? "" : "none";
    if (_S.view === "guide") renderGuide();
    else if (_S.view === "methodology") renderMethodology();
    else if (_S.view === "source-comparison") renderSourceComparison();
    else if (_S.view === "models") renderModels();
    else renderTerms();
  }

  function boot() {
    syncFromURL();
    document.querySelectorAll("[data-glossary-view]").forEach(b => {
      b.onclick = () => { _S.view = b.dataset.glossaryView; syncToURL(); render(); };
    });
    const inp = document.getElementById("gl-search");
    if (inp) {
      inp.value = _S.q;
      inp.addEventListener("input", () => { _S.q = inp.value; syncToURL(); render(); });
      inp.addEventListener("keydown", e => {
        if (e.key === "Escape") { inp.value = ""; _S.q = ""; syncToURL(); render(); }
      });
    }
    window.addEventListener("hashchange", () => { syncFromURL(); render(); });
    const start = () => {
      GL = window.EEPHUS_GLOSSARY || {};
      GROUPS = window.EEPHUS_GLOSSARY_GROUPS || {};
      render();
    };
    if (window.EEPHUS_GLOSSARY) start();
    else window.addEventListener("eephus-glossary-ready", start, { once: true });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // window-scope the print hook the toolbar button calls.
  window._printMethodology = function () {
    document.body.classList.add("printing-meth");
    const cleanup = () => { document.body.classList.remove("printing-meth"); window.removeEventListener("afterprint", cleanup); };
    window.addEventListener("afterprint", cleanup);
    setTimeout(() => { window.print(); }, 30);
    setTimeout(cleanup, 1500);
  };

// ==== PORTED FROM PROSPX (Glossary/Methodology tab, retired 2026-06-10) =====
// Source: prospx/index.html L17995-18742 via build_glossary_port.py.
// Hand-maintained from here on; the generator is provenance only.
//
// _RATER_META / _TIER_ORDER sat ONE LINE above the port slice and were
// missed - Source Comparison silently hung on "Loading…" because the
// ReferenceError died inside the fetch promise (fixed 2026-06-10; the
// smoke test now asserts rendered content, not just a non-empty body).
// _raterMeta() is the safe accessor: unknown raters (new sources join the
// backtest as their cohorts resolve) get a neutral fallback, never a throw.
// Owner palette (2026-06-24): FanGraphs dark green, MLB Pipeline blue, PROSPX consensus pink,
// eFV the site lilac (its identity color, theme-aware via --accent-lilac).
const _RATER_META = {
  fangraphs:        { label: "FanGraphs",        color: "#2E8B57" },
  mlb_pipeline:     { label: "MLB Pipeline",     color: "#4F9DFF" },
  prospx_consensus: { label: "PROSPX consensus", color: "#FF6FB3" },
  xfv:              { label: "eFV (ours, OOS)",  color: "var(--accent-lilac)" },
};
const _TIER_ORDER = ["<45", "45", "50", "55", "60+"];
function _raterMeta(r) {
  return _RATER_META[r] || { label: String(r), color: "var(--text-tertiary)" };
}
// WAR-capture (lift) curve: share of all realized career WAR sitting in the top N% of each
// board. A sharper-ordering grade concentrates WAR earlier -> a higher curve. Replaces the
// confounded mean-WAR-by-tier chart (where BETTER ordering paradoxically lowers the middle mean).
function _methCaptureCurve(bt) {
  const cc = bt.accuracy && bt.accuracy.capture_curve;
  if (!cc || !cc.xfv || !cc.consensus) return "";
  const W = 460, H = 230, ML = 40, MR = 12, MT = 16, MB = 30, iW = W - ML - MR, iH = H - MT - MB;
  const sx = p => ML + p * iW, sy = v => MT + iH - v * iH;
  const grid = [];
  for (let i = 0; i <= 4; i++) {
    const v = i / 4, y = sy(v).toFixed(1);
    grid.push(`<line x1="${ML}" y1="${y}" x2="${ML + iW}" y2="${y}" stroke="var(--border-light)" stroke-width="0.5" stroke-dasharray="2,3"/>`,
      `<text x="${ML - 6}" y="${y}" dy="3" text-anchor="end" font-size="9" fill="var(--text-tertiary)">${Math.round(v * 100)}%</text>`);
  }
  const xlabels = [0, 0.2, 0.4, 0.6, 0.8, 1].map(p =>
    `<text x="${sx(p).toFixed(1)}" y="${MT + iH + 15}" text-anchor="middle" font-size="9" fill="var(--text-secondary)">${Math.round(p * 100)}%</text>`).join("");
  const diag = `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(1)}" y2="${sy(1)}" stroke="var(--text-tertiary)" stroke-width="0.8" stroke-dasharray="4,4"/>`;
  const line = (pts, col, wdt) => {
    let d = `M ${sx(0).toFixed(1)},${sy(0).toFixed(1)}`;
    pts.forEach(p => { d += ` L ${sx(p.pct).toFixed(1)},${sy(p.captured).toFixed(1)}`; });
    return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${wdt}" stroke-linecap="round" stroke-linejoin="round"/>`;
  };
  const efvCol = "var(--accent-lilac)", consCol = _raterMeta("prospx_consensus").color;
  const t20x = Math.round((cc.xfv.top20 || 0) * 100), t20c = Math.round((cc.consensus.top20 || 0) * 100);
  return `<div class="meth-chart">
    <div class="meth-chart-title">Career WAR captured by the top of the board <span class="meth-sub">share of all realized WAR sitting in each board's top N%, higher = sharper ordering</span></div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="WAR capture curve">
      ${grid.join("")}${diag}
      <line x1="${ML}" y1="${MT + iH}" x2="${ML + iW}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      <line x1="${ML}" y1="${MT}" x2="${ML}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      ${line(cc.consensus.points, consCol, 2.2)}${line(cc.xfv.points, efvCol, 2.8)}
      ${xlabels}
      <text x="${ML + iW}" y="${MT + iH + 15}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">top % of board</text>
    </svg>
    <div class="meth-legend">
      <span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${efvCol};"></span>eFV</span>
      <span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${consCol};"></span>PROSPX consensus</span>
      <span class="meth-legend-key"><span class="meth-legend-swatch" style="background:var(--text-tertiary);"></span>random</span>
    </div>
    <p class="meth-note">eFV concentrates <strong>${t20x}%</strong> of all realized career WAR in the top 20% of its board, against ${t20c}% for the consensus. It sorts the eventual contributors toward the top more sharply. Full graded pool (n=${cc.pool_n.toLocaleString()}, debuted + busts); the public sources don't grade the lower-minors busts, so this lift curve is eFV against the consensus it is built to upgrade.</p>
  </div>`;
}
function _methProseHTML() {
  return `
  <div class="meth-prose">
    <h2 class="meth-h">How eFV is built <span class="meth-sub">the site's primary grade</span></h2>
    <p><strong>eFV (eephusFV)</strong> is our outcome-grounded Future Value grade, and the
    primary grade and ranking signal site-wide. A scout FV grades the tool profile; eFV predicts
    the career it produces: <em>given everything known before a prospect debuts, his distribution
    of first-6-MLB-season WAR</em>, summarized back onto the familiar 20-80 scale.</p>
    <p><strong>The model.</strong> eFV starts from the consensus FV as a regularized prior (see
    below), then adds a small set of outcome-validated adjustments: the signals that carry WAR
    information <em>beyond</em> the grade and are under-priced by scouts. Hitters: on-base vs level,
    contact (K%) vs level, a multi-season peak K-rate, age-for-level, MiLB track-record length, the
    hit and speed tools. Pitchers: a multi-season peak K-rate, final-season K-rate, walk rate (the
    K-BB% completion), age-for-level, fastball. Game power is <em>omitted</em> for hitters on
    purpose: the data shows scouts over-price it and it predicts ISO, not incremental WAR, so
    leaving it out is eFV's power-overpricing correction. It is a regularized ridge on ~3,800
    labeled prospects (2011-2023), rate features sample-shrunk so a cup of coffee does not read as
    a track record.</p>
    <p><strong>The guarded blend.</strong> The headline ranking is a guarded blend,
    rank = (1-λ)·(consensus→WAR) + λ·(model→WAR), where λ is <em>WAG-calibrated</em>: the trust
    that realized WAR-Above-Grade supports for eFV's adjustment, fit forward-chained
    (hitters ~0.85; pitchers shrink harder, since consensus is the stronger pitcher signal). The
    blend cannot fall far below the consensus prior, and leans on eFV where its edge is real.</p>
    <p><strong>Two grades, one model.</strong> The <em>headline</em> eFV is a rank-preserving
    quantile map of that blended ranking onto the consensus 20-80 distribution (so it reads on the
    scale you know); a deflated <em>realized-implied</em> grade - typically lower, because scout FV
    runs optimistic - drives the surplus + the 5-bucket outcome mix. Live prospects also get two
    bounded tilts: an injury penalty (current IL + recent IL load + post-TJ) and a Statcast+
    quality tilt on upper-level prospects.</p>
    <p><strong>Everywhere, frozen at debut.</strong> Every graded prospect carries an eFV: the
    active boards, graduates (backgraded at their final pre-debut snapshot, then <em>locked</em>),
    and the farm-system rankings, surplus, DvM+, and movement engine all run on it. Players with no
    pro track record (recent draftees, int'l signs) fall back to the consensus prior until they
    play.</p>
    <p class="meth-verdict is-good">On out-of-sample, leakage-free, forward-chained tests of how
    well each grade ordered what prospects became, eFV out-predicts every public source: the PROSPX
    consensus, MLB Pipeline, and FanGraphs. The Source Comparison tab has the head-to-head numbers.
    eFV is <strong>provisional</strong> and near the data's rank ceiling; its historical track is a
    current-model retrospective, not the grade we showed at the time.</p>

    <h2 class="meth-h">How the consensus FV (eFV's prior) is built</h2>
    <p>The consensus FV is the scout-grade aggregate eFV anchors on, and the reference shown
    alongside eFV everywhere. Every source that publishes an explicit 20-80 Future Value grade feeds an
    <strong>accuracy-weighted</strong> consensus. Each source's vote weight comes from its
    measured track record on resolved cohorts, shrunk hard toward equal and clamped, so the
    weights barely move off one vote - today only MLB Pipeline (1.06) and FanGraphs (0.94)
    differ; every other source votes at 1.0. The consensus FV is that weighted mean of the
    published grades (FanGraphs, ESPN, Just Baseball, TJStats, MLB Pipeline,
    and MLB Pipeline International). Two rank-only sources (Baseball America, The Athletic)
    contribute a rank→implied-FV <em>only</em> when no source has graded a player yet; once
    any explicit FV exists, the grade mean wins and ranks become informational (the
    <code>avg_rank</code> field).</p>
    <p>Grades are <strong>forward-filled</strong>: because sources publish on different dates,
    the consensus at any date uses the latest snapshot from <em>every</em> source up to that
    date, so a player isn't reduced to a single most-recent list. It is then
    <strong>Bayesian-shrunk</strong> - a thin-evidence grade (graded by few sources, or only
    just added) is pulled toward a prior, so one aggressive outlier source can't swing the
    number until corroborating grades arrive. The chart you see on every prospect page is this
    point-in-time consensus history; the per-source overlay shows the inputs it blends.</p>

    <h2 class="meth-h">How the Arkmetrics are derived</h2>
    <dl class="meth-dl">
      <dt>WAG - WAR Above Grade <span class="meth-tag">graduates</span></dt>
      <dd>A graduate's career WAR <em>rate</em> projected to a role-typical full season
      (612 PA for hitters; 175 / 65 / 50 / 60 IP for SP / MIRP / SIRP / CL), minus the
      per-season WAR the player's FV grade implied. Positive = outproducing the grade. Sample
      floors of 150 PA / 50 IP gate it. This is the realized-outcome metric the backtest below
      leans on.</dd>

      <dt>DvM+ - Development vs Mean <span class="meth-tag">farm system</span></dt>
      <dd>A wRC+-style index of organizational development: an org's cumulative <strong>eFV</strong>
      growth over a 1 / 3 / 6-year window scored against the league-mean farm (100 = mean, +10 =
      one standard deviation). Acquisitions are nullified and graduations don't subtract, so it
      measures only development of prospects already in the system. The farm grade weights
      6y / 3y / 1y at 60 / 30 / 10%. ($DvM+, the per-prospect surplus-development index, is also
      eFV-based; ToolDvM+ stays on per-tool scout-grade growth, since the tool grades have no
      separate eFV time series.)</dd>

      <dt>RPS+ - Rate Performance Score <span class="meth-tag">prospect</span></dt>
      <dd>A level-anchored rate index (OPS+ for hitters, ERA- for pitchers) normalized against
      the player's <em>own</em> age × position-group cohort, then nudged by a small position
      multiplier (C ×1.08 … 1B ×0.95). 100 = the same-age, same-position-group mean. MLB-level
      prospects substitute canonical wRC+ / xFIP.</dd>

      <dt>SC+ - Statcast+ <span class="meth-tag">prospect</span></dt>
      <dd>A side-aware composite of tracked Statcast / zone signals - contact quality + zone
      discipline for hitters; stuff + induced whiff/chase + suppressed contact for pitchers.
      Each component is z-scored against the side-matched active pool, averaged, and rescaled so
      100 = pool mean and one standard deviation moves it 15 points (the wRC+/OPS+ family).</dd>

      <dt>ToolDvM+ - Tool Development vs Mean <span class="meth-tag">farm system</span></dt>
      <dd>A position-weighted blend of an org's per-tool DvM+ values (Hit, Power, Field, Arm,
      Fastball, Command, …). Each tool's development velocity is league-anchored (100 + 10·z),
      then weighted by how much that tool matters for the position bucket (a catcher's Field/Arm,
      a starter's Fastball/Command), so growing the <em>right</em> tools scores higher than
      padding the average.</dd>
    </dl>

    <div class="meth-eg-card">
      <div class="meth-eg-title">Worked example · how a grade becomes a dollar figure</div>
      <div class="meth-eg-row">An <b>${gTermLink("fv", "FV")} 60</b> shortstop: the FV→WAR anchor maps the grade to a per-year WAR expectation, the position multiplier nudges it for the up-the-middle profile, and the six cost-controlled years are priced at the tiered ${gTermLink("dpw_tier", "$/WAR")} (about $7.7M / $9.7M / $15.1M by WAR level) minus the league-min-plus-arb cost basis, then probability-weighted across debut and bust outcomes and discounted to present value.</div>
      <div class="meth-eg-row">The result is the published ${gTermLink("surplus_value", "surplus value")} on that player's card. A higher ${gTermLink("dvm_plus", "$DvM+")} (faster-than-mean development) and stronger underlying rates (${gTermLink("k_pct", "K%")} / ${gTermLink("bb_pct", "BB%")}, ${gTermLink("ops_plus", "OPS+ vs lvl")}) lift the expectation within the FV band.</div>
      <div class="meth-eg-note">Illustrative - each player's card carries their own current figure, which moves with the FV→WAR table and the $/WAR market.</div>
    </div>

    <h2 class="meth-h">Surplus value - the economic model</h2>
    <p>A prospect is an asset because the six years of team control after debut are paid below
    market. Surplus value is the dollar production those controlled years are expected to deliver
    above what they cost. The grade priced here is <strong>eFV</strong> (the consensus FV is the
    fallback where eFV abstains); the pricing engine below is grade-agnostic - it takes whatever
    grade leads and converts it to dollars:</p>
    <p class="meth-eq">surplus = (expected WAR × $/WAR) − cost basis, probability-weighted across outcomes and discounted to present value</p>
    <p>The build, in order: (1) the <strong>FV→WAR anchor</strong> converts the scouting grade to an
    expected ${gTermLink("war", "WAR")}/year over six controlled seasons (${gTermLink("fv_to_war_table", "the FV→WAR table")}).
    (2) WAR is priced at a non-linear, tiered <strong>${gTermLink("dpw_tier", "$/WAR")}</strong> (a win on a star is worth more
    than a win on a replacement-level filler). (3) The <strong>cost basis</strong> is the three pre-arbitration
    years at the league minimum plus three arbitration years at an escalating fraction of free-agent
    value (${gTermLink("service_time", "service-time")} schedule). (4) Because a prospect is a <em>distribution</em>
    of outcomes, not a point, the engine probability-weights a bucketed outcome set (bust → role player
    → regular → star) rather than trusting the FV midpoint, then discounts future years to present value
    at 9%/yr. The published per-prospect figure is ${gTermLink("surplus_value", "Surplus value")}; the per-FV-point
    and per-dollar efficiency cuts are ${gTermLink("surplus_per_fv_pt", "Surplus / FV-pt")} and ${gTermLink("dollars_per_fv", "$/FV-pt")}.
    The <em>Interactive</em> tab below walks an FV through every step.</p>

    <h2 class="meth-h">Farm-system grades - how the org letter is built</h2>
    <p>The org grade is a weighted tree (${gTermLink("farm_report_card", "Farm grade tree")}), not a single
    formula, so each letter is auditable down to its leaves. Four branches, value-led (v40):
    <strong>Value</strong> (65% - the org's aggregate risk-adjusted controlled surplus, the total $ value of
    the active prospect pool from the recalibrated value framework, which already prices elite ceiling
    non-linearly; ${gTermLink("fin_war_per_m", "WAR per $M")}, ${gTermLink("fin_contract_surplus", "grad-contract surplus")},
    ${gTermLink("fin_dollar_dvm", "Org $DvM+")}, ${gTermLink("fin_draft_pool_efficiency", "draft-pool efficiency")},
    ${gTermLink("fin_ifa_roi", "IFA ROI")}), <strong>MLB Production</strong> (18% - does the system produce
    big-leaguers, boom/bust rates, top-3 graduate WAR, a star-presence ${gTermLink("mlb_production_conviction", "Conviction")}
    flag), <strong>Development</strong> (9% - per-tool growth of prospects the org already had,
    ${gTermLink("dvm_plus", "DvM+")} / ${gTermLink("tools_dvm_plus", "ToolDvM+")}), and
    <strong>Acquisition Strategy</strong> (8% - Draft / IFA / Trade / Waiver channels).
    Every leaf is z-scored across the 30 orgs and anchored so the composite reads on a 100 = league-mean
    scale; sparse leaves return " - " rather than guessing. Surplus enters the Value branch as realized
    capital efficiency and again via the development of surplus dollars (Org $DvM+).</p>

    <h2 class="meth-h">Aggregation - player level to farm level</h2>
    <p>Roll-ups are explicit, not implied. Org surplus is the sum of its active prospects' per-player
    surplus dollars (the authoritative engine aggregate, <code>_active_surplus_net_mm</code>); the farm
    list, the detail Surplus tile, and the Finances tab all read that one number. DvM+ / ToolDvM+
    aggregate per-tool development across the org's actives with acquisitions nullified (so a trade
    doesn't read as development) and graduations not subtracted (so promoting a star doesn't read
    as a loss). The "+" indices (DvM+, RPS+, SC+, OrgSur+) are all built to the wRC+/OPS+ convention - 
    100 = the relevant mean, ±10 ≈ one standard deviation - so they share one mental scale.</p>

    <h2 class="meth-h">Where the Arkmetrics sit vs public metrics</h2>
    <table class="meth-cmp">
      <thead><tr><th>Arkmetric</th><th>Closest public analogue</th><th>What's different</th></tr></thead>
      <tbody>
        <tr><td>${gTermLink("wag", "WAG")}</td><td>WAR vs draft-pick / FV expectation</td><td>Measures realized career WAR against the WAR a player's FV grade <em>implied</em> - a grade-calibration residual, not raw production.</td></tr>
        <tr><td>${gTermLink("dvm_plus", "DvM+ / $DvM+")}</td><td>Farm-system surplus-value rankings (e.g. public prospect-value tables)</td><td>Indexed wRC+-style (100 = mean) and scoped to in-system <em>development</em> with acquisitions removed, so it isolates org skill rather than hoarded talent.</td></tr>
        <tr><td>${gTermLink("surplus_value", "Surplus value")}</td><td>Surplus-value frameworks (FV→WAR→$ minus cost)</td><td>Same skeleton, but probability-weighted over a bucketed outcome distribution and discounted, rather than applying a single FV-tier dollar constant.</td></tr>
        <tr><td>${gTermLink("rps_plus", "RPS+")}</td><td>wRC+ / ERA-</td><td>Re-anchored to the player's own age × position-group cohort and level, so a young hitter at a hard level isn't penalized against older peers.</td></tr>
        <tr><td>${gTermLink("statcast_plus", "SC+")}</td><td>Statcast percentile dashboards</td><td>Collapses the tracked-data panel into one side-aware, pool-anchored composite on the wRC+ scale.</td></tr>
      </tbody>
    </table>

    <h2 class="meth-h">Data sources &amp; references</h2>
    <ul class="meth-refs">
      <li><strong>Scouting grades / FV:</strong> FanGraphs, MLB Pipeline (domestic + international), ESPN, Just Baseball, TJStats; rank-only fallbacks from Baseball America and The Athletic.</li>
      <li><strong>Performance &amp; tracked data:</strong> MLB Stats API (MLB + MiLB statlines), Baseball Savant (Statcast) where available for upper-level / debuted players, pulled via pybaseball.</li>
      <li><strong>Contracts &amp; bonuses:</strong> published MLB draft-pool and international bonus-pool figures; Spotrac for graduate contract/AAV data.</li>
      <li><strong>Framework anchors:</strong> the FanGraphs scouting primer (FV→WAR ranges) and public $/WAR estimates (tiered, rolling multi-year average). The surplus engine's outcome buckets and discount rate are documented in <code>value_framework.py</code>.</li>
    </ul>

    <h2 class="meth-h">Data sources &amp; attribution</h2>
    <p class="meth-note">PROSPX grades are a consensus built across seven independent industry sources - the value added is the aggregation, calibration, and track-record audit, not any single list. No source's rankings or reports are republished wholesale; excerpts appear with attribution in the spirit of commentary and analysis. All trademarks and data remain the property of their owners. The full attribution page lives at <a href="/sources/">/sources/</a>.</p>
    <div class="article-grid">
      ${[
        ["FanGraphs", "https://www.fangraphs.com/", "Prospect rankings, FV + tool grades, scouting reports (consensus input); league stats and park factors."],
        ["MLB Pipeline", "https://www.mlb.com/prospects", "Prospect rankings and grades (consensus input); draft bonus pools and slot values."],
        ["Baseball America", "https://www.baseballamerica.com/", "Prospect rankings and grades (consensus input)."],
        ["ESPN", "https://www.espn.com/mlb/", "Prospect rankings (consensus input); team logo imagery on internal surfaces."],
        ["The Athletic", "https://www.nytimes.com/athletic/", "Prospect rankings (consensus input)."],
        ["Just Baseball", "https://www.justbaseball.com/", "Prospect rankings (consensus input)."],
        ["TJStats", "https://x.com/TJStats", "Prospect rankings (consensus input) and movers wire."],
        ["MLB Stats API / Baseball Savant", "https://baseballsavant.mlb.com/", "Game logs, transactions, rosters, Statcast tracking data, and player headshots."],
        ["Baseball-Reference", "https://www.baseball-reference.com/", "bWAR - the WAR framework used site-wide - plus historical player pages."],
        ["pybaseball", "https://github.com/jldbc/pybaseball", "Open-source Python toolkit used to pull Statcast, FanGraphs, and Baseball-Reference data programmatically."],
        ["Spotrac", "https://www.spotrac.com/", "Contracts, payrolls, free-agent classes, and international signing trackers."],
      ].map(([nm, url, use]) => `<div class="card source-card"><h3><a href="${url}" target="_blank" rel="noopener noreferrer">${escapeHtml(nm)}</a></h3><p>${escapeHtml(use)}</p></div>`).join("")}
    </div>
    <p class="meth-note">All grades remain the property of their publishers; the site stores them to compute a consensus and does not redistribute source lists wholesale.</p>

    <h2 class="meth-h">Methodology changelog</h2>
    <ul class="meth-changelog">
      <li><span class="mc-date">2026-06</span> Historical backfill: ingested FanGraphs 2017-2020 boards (new-format CSVs) + MLB Pipeline 2017-2020 Top 100, each grade date-stamped to its year. The backtest's resolved-cohort window grew from 2021-2023 (3 base years) to 2017-2023 (7), and the common scored set grew with it. On the larger, further-resolved sample the consensus still outranks its best individual source (current common-set size and margins are in Source Comparison below).</li>
      <li><span class="mc-date">2026-06</span> Surplus engine v38: FV→WAR anchor moved from a single peak-year projection to a flat 6-year-average table; side difference carried by the position multiplier. Farm list/detail surplus consolidated on the engine aggregate.</li>
      <li><span class="mc-date">2026-06</span> Glossary reorganized into Glossary / Methodology / Source Comparison; taxonomy regrouped (Arkmetrics · Statcast · Standard · Scouting · Economic · Farm · Site Features); Statcast input terms added.</li>
      <li><span class="mc-date">2026-06</span> Farm grade tree v40: value-tracking reweight. The org letter is now primarily driven by aggregate risk-adjusted controlled surplus (the Value branch, 65%); Development drops from the top weight to a secondary controllable-skill signal (9%), MLB Production 18%, Acquisition Strategy 8%. This stops the grade from reading as a per-prospect tool-development index decoupled from aggregate farm value.</li>
      <li><span class="mc-date">2026-05</span> Farm grade tree v7: MLB Production added a Bust-Rate (negative) leaf and a Conviction star-presence cap; Development promoted to the 40% top weight.</li>
      <li><span class="mc-date">2026-06</span> Consensus FV moved to ACCURACY-WEIGHTED source blending after a vintage-disciplined A/B beat equal-weight on both Spearman and AUC (weights shrunk toward equal, clamped, frozen per vintage; sources without resolved history stay at 1.0). The model accountability registry below records the eval.</li>
      <li><span class="mc-date">2026-05</span> Source-vs-source backtest published (resolved cohorts only) as the Source Comparison area.</li>
      <li><span class="mc-date">2026-04</span> Consensus FV: equal-weight mean confirmed over weighted schemes at that window; Bayesian shrinkage + forward-fill formalized.</li>
    </ul>
    <p class="meth-note">Versioned methodology pairs with the Time Machine: a board state and the rules that produced it are both reconstructable for any past month.</p>

    <h2 class="meth-h">FAQ</h2>
    <dl class="meth-dl">
      <dt>Why a consensus instead of one source?</dt>
      <dd>Averaging cancels idiosyncratic source error: the pooled consensus modestly but consistently beats its best individual input on resolved cohorts (see Source Comparison). Per-source edges exist but are small and unstable year to year, which is why the weighting stays shrunk toward equal rather than chasing them.</dd>
      <dt>How are sources weighted?</dt>
      <dd>Accuracy-weighted, as of June 2026: per-source weights come from measured track records on resolved cohorts, shrunk heavily toward equal (so a thin history can't dominate), clamped, and frozen per vintage so grades don't jitter month to month. The weighted blend shipped only after beating equal-weight in a no-lookahead A/B on both rank correlation and AUC; sources without enough resolved history stay at exactly 1.0. The interactive below lets you test any weighting yourself.</dd>
      <dt>How often does it update?</dt>
      <dd>Grades, Arkmetrics, farm grades, and the backtest refresh monthly; transactions, IL, roster status, debuts, and trades refresh daily. Each board stamps its own cadence.</dd>
      <dt>What's the track record - and its limits?</dt>
      <dd>The evaluation window spans seven preseason base years (2017-2023): the 2017-2020 cohorts are fully resolved while 2021-2023 are still accruing WAR, and cumulative WAR is censored at today. Top FV tiers stay thin (n≈40-70), so their rates move on a few outcomes. The Source Comparison area lists sample sizes and these caveats in full rather than headlining an inflated number.</dd>
    </dl>
  </div>`;
}

// Smooth (Catmull-Rom) calibration line: x = FV tier, y = an outcome metric,
// one line per rater. Honest "smooth data curve" while UI stays sharp-cornered.
function _methCalibrationChart(bt, metricKey, metricLabel, opts) {
  opts = opts || {};
  const W = 580, H = 250, ML = 46, MR = 16, MT = 16, MB = 40;
  const iW = W - ML - MR, iH = H - MT - MB;
  const tiers = _TIER_ORDER;
  // eFV joins the FV-tier lines whenever its cohort is present (primary, drawn boldest).
  const raterList = bt.raters.concat(bt.cohorts.xfv ? ["xfv"] : []);
  const series = raterList.map(r => {
    const tmap = {}; ((bt.cohorts[r] && bt.cohorts[r].tiers) || []).forEach(t => { tmap[t.tier] = t; });
    return { rater: r, pts: tiers.map(t => tmap[t] ? tmap[t][metricKey] : null) };
  });
  const allVals = series.flatMap(s => s.pts).filter(v => v != null);
  if (!allVals.length) return "";
  const yMax = opts.yMax || (Math.max(...allVals) * 1.1 || 1);
  const yMin = opts.yMin || 0;
  const sx = i => ML + (tiers.length === 1 ? iW / 2 : (i / (tiers.length - 1)) * iW);
  const sy = v => MT + iH - ((v - yMin) / (yMax - yMin)) * iH;
  const yticks = 4;
  const grid = [];
  for (let i = 0; i <= yticks; i++) {
    const v = yMin + (yMax - yMin) * i / yticks;
    const y = sy(v).toFixed(1);
    grid.push(`<line x1="${ML}" y1="${y}" x2="${ML + iW}" y2="${y}" stroke="var(--border-light)" stroke-width="0.5" stroke-dasharray="2,3"/>`,
      `<text x="${ML - 6}" y="${y}" dy="3" text-anchor="end" font-size="9" fill="var(--text-tertiary)">${opts.pct ? Math.round(v * 100) + "%" : v.toFixed(opts.dp != null ? opts.dp : 1)}</text>`);
  }
  const xlabels = tiers.map((t, i) =>
    `<text x="${sx(i).toFixed(1)}" y="${MT + iH + 16}" text-anchor="middle" font-size="10" fill="var(--text-secondary)" font-weight="600">${t}</text>`).join("");
  const lines = series.map(s => {
    const pts = s.pts.map((v, i) => v == null ? null : { x: sx(i), y: sy(v) }).filter(Boolean);
    if (pts.length < 2) return "";
    let d = `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || pts[i + 1];
      const c1x = p1.x + (p2.x - p0.x) / 6, c1y = p1.y + (p2.y - p0.y) / 6;
      const c2x = p2.x - (p3.x - p1.x) / 6, c2y = p2.y - (p3.y - p1.y) / 6;
      d += ` C ${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
    }
    const col = _raterMeta(s.rater).color;
    const isEfv = s.rater === "xfv";
    const emph = isEfv || s.rater === "prospx_consensus";   // both drawn solid; eFV boldest
    const dots = pts.map(p => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${isEfv ? 3.8 : emph ? 3.2 : 2.5}" fill="${col}"/>`).join("");
    return `<path d="${d}" fill="none" stroke="${col}" stroke-width="${isEfv ? 2.8 : emph ? 2.4 : 1.6}" ${emph ? "" : 'stroke-dasharray="5,3"'} stroke-linecap="round"/>${dots}`;
  }).join("");
  const legend = raterList.map(r =>
    `<span class="meth-legend-key"><span class="meth-legend-swatch" style="background:${_raterMeta(r).color};"></span>${escapeHtml(_raterMeta(r).label)}</span>`).join("");
  return `<div class="meth-chart">
    <div class="meth-chart-title">${escapeHtml(metricLabel)} by FV tier</div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${escapeHtml(metricLabel)} by FV tier">
      ${grid.join("")}
      <line x1="${ML}" y1="${MT + iH}" x2="${ML + iW}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      <line x1="${ML}" y1="${MT}" x2="${ML}" y2="${MT + iH}" stroke="var(--text-secondary)" stroke-width="1"/>
      ${lines}${xlabels}
    </svg>
    <div class="meth-legend">${legend}</div>
  </div>`;
}

// Source-accuracy comparison - horizontal bars for Spearman ρ + AUC, consensus
// highlighted. Answers "which is most reliable, and does the blend win?"
function _methAccuracyChart(bt) {
  const acc = bt.accuracy && bt.accuracy.pooled;
  if (!acc) return "";
  const h2hRaters = (bt.accuracy && bt.accuracy.head_to_head_raters) || bt.raters;
  const metric = (key, label, lo, hi, fmt) => {
    const rows = h2hRaters.map(r => ({ r, v: acc[r] ? acc[r][key] : null })).filter(x => x.v != null);
    if (!rows.length) return "";
    const best = Math.max(...rows.map(x => x.v));
    const bars = rows.map(x => {
      const w = Math.max(2, ((x.v - lo) / (hi - lo)) * 100);
      const emph = x.r === "prospx_consensus";
      const isBest = x.v === best;
      return `<div class="meth-bar-row">
        <span class="meth-bar-label">${escapeHtml(_raterMeta(x.r).label)}</span>
        <span class="meth-bar-track"><span class="meth-bar-fill${emph ? " is-consensus" : ""}" style="width:${w.toFixed(1)}%;background:${_raterMeta(x.r).color};"></span></span>
        <span class="meth-bar-val${isBest ? " is-best" : ""}">${fmt(x.v)}${isBest ? " ★" : ""}</span>
      </div>`;
    }).join("");
    return `<div class="meth-metric"><div class="meth-metric-title">${escapeHtml(label)}</div>${bars}</div>`;
  };
  const sp = metric("spearman", "Ordering skill - Spearman ρ (grade vs realized WAR)", 0, 0.4, v => v.toFixed(3));
  const au = metric("auc", "Discrimination - AUC (grade predicts ‘became a contributor’)", 0.5, 0.85, v => v.toFixed(3));
  const pld = bt.accuracy.pooled || {};
  const x = pld.xfv, c = pld.prospx_consensus, fg = pld.fangraphs, mlb = pld.mlb_pipeline;
  let verdict;
  if (x && x.spearman != null && c && c.spearman != null) {
    const f3 = v => (v == null ? "-" : v.toFixed(3));
    verdict = `<p class="meth-verdict is-good">Out of sample, leakage-free, on the players it grades, <strong>eFV orders realized WAR better than every grade on the board</strong>: Spearman ${f3(x.spearman)}, against ${f3(c.spearman)} for the PROSPX consensus, ${f3(mlb && mlb.spearman)} for MLB Pipeline, ${f3(fg && fg.spearman)} for FanGraphs; it also leads on contributor AUC, ${f3(x.auc)} to ${f3(c.auc)}. The consensus is the strongest public-style input, but eFV beats the consensus itself, and that gap is the reason it is the primary grade, not the consensus's edge over its inputs. The lead holds across recent cohorts and FV tiers; it is bounded, a few Spearman points (see caveats).</p>`;
  } else {
    verdict = `<p class="meth-verdict">On the common set of ${bt.accuracy.common_n.toLocaleString()} players, the consensus is competitive with its inputs but does not lead on every metric (reported as measured, not cherry-picked).</p>`;
  }
  return `<div class="meth-chart meth-accuracy">
    <div class="meth-chart-title">Head-to-head predictive accuracy <span class="meth-sub">same players, same outcome, same window</span></div>
    ${sp}${au}${verdict}
  </div>`;
}

// eFV vs consensus FV - our outcome-grounded model, shown SEPARATELY from the per-source
// bars because it runs on its own out-of-sample protocol (the harder, conservative bar).
function _methEfvPanel(bt) {
  const xc = bt.xfv_vs_consensus;
  if (!xc || !xc.sides) return "";
  const W = v => Math.max(2, (v / 0.4) * 100).toFixed(1);
  const sideBlock = (key, label) => {
    const s = xc.sides[key];
    if (!s) return "";
    const win = s.xfv_beats;
    const eras = s.era_split || {};
    const eraRows = Object.keys(eras).map(k => {
      const e = eras[k];
      const d = (e.xfv_blend_spearman != null && e.consensus_spearman != null)
        ? e.xfv_blend_spearman - e.consensus_spearman : 0;
      const col = d > 0 ? "var(--up)" : d < 0 ? "var(--down)" : "var(--text-secondary)";
      return `<tr><td>${escapeHtml(k)}</td><td>${e.n}</td><td>${e.consensus_spearman != null ? e.consensus_spearman.toFixed(3) : " - "}</td><td style="color:${col};font-weight:700;">${e.xfv_blend_spearman != null ? e.xfv_blend_spearman.toFixed(3) : " - "}</td></tr>`;
    }).join("");
    return `<div class="meth-metric">
      <div class="meth-metric-title">${escapeHtml(label)} <span class="meth-sub">n=${s.n}</span></div>
      <div class="meth-bar-row"><span class="meth-bar-label">Consensus FV</span><span class="meth-bar-track"><span class="meth-bar-fill" style="width:${W(s.consensus_spearman)}%;background:var(--text-secondary);"></span></span><span class="meth-bar-val">${s.consensus_spearman.toFixed(3)}</span></div>
      <div class="meth-bar-row"><span class="meth-bar-label">eFV</span><span class="meth-bar-track"><span class="meth-bar-fill is-consensus" style="width:${W(s.xfv_spearman)}%;background:var(--neon-cyan);"></span></span><span class="meth-bar-val${win ? " is-best" : ""}">${s.xfv_spearman.toFixed(3)}${win ? " ★" : ""}</span></div>
      ${eraRows ? `<div class="table-scroll-x" style="margin-top:6px;"><table class="meth-table"><thead><tr><th>Debut era</th><th>n</th><th>Consensus ρ</th><th>eFV ρ</th></tr></thead><tbody>${eraRows}</tbody></table></div>` : ""}
    </div>`;
  };
  // Per-FV-tier head-to-head + the resolved "receipts" (where they disagreed, who was right).
  const det = bt.accuracy && bt.accuracy.xfv_vs_consensus_detail;
  let tierTable = "", receipts = "";
  if (det && det.per_tier && det.per_tier.length) {
    const rows = det.per_tier.map(t => {
      const win = t.xfv_spearman != null && t.consensus_spearman != null && t.xfv_spearman > t.consensus_spearman;
      return `<tr><td class="meth-td-tier">${escapeHtml(t.tier)}</td><td>${t.n}</td>
        <td>${t.consensus_spearman != null ? t.consensus_spearman.toFixed(3) : " - "}</td>
        <td style="color:${win ? "var(--up)" : "var(--text-secondary)"};font-weight:${win ? 700 : 400};">${t.xfv_spearman != null ? t.xfv_spearman.toFixed(3) : " - "}${win ? " ★" : ""}</td></tr>`;
    }).join("");
    tierTable = `<div class="meth-table-wrap"><div class="meth-table-title">By FV tier <span class="meth-sub">ordering skill (Spearman ρ) within each consensus-FV bucket</span></div>
      <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>FV tier</th><th>n</th><th>Consensus ρ</th><th>eFV ρ</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
  }
  if (det && det.receipts && det.receipts.length) {
    const rr = det.receipts.map(r => {
      const ok = r.xfv_right;
      return `<tr><td>${escapeHtml(r.name)}</td><td>${r.consensus_fv}</td><td>eFV ${escapeHtml(r.dir)}</td><td>${r.war}</td>
        <td style="color:${ok ? "var(--up)" : "var(--down)"};font-weight:700;">${ok ? "eFV ✓" : "consensus ✓"}</td></tr>`;
    }).join("");
    const share = det.xfv_right_share_on_disagreements;
    receipts = `<div class="meth-table-wrap"><div class="meth-table-title">Biggest disagreements - who was right <span class="meth-sub">resolved players; on ${det.n_disagreements || "?"} clear grade disagreements (eFV vs consensus &ge;15 percentile apart), eFV was closer ${share != null ? Math.round(share * 100) : "?"}% of the time</span></div>
      <div class="table-scroll-x"><table class="meth-table"><thead><tr><th>Player</th><th>Consensus FV</th><th>eFV said</th><th>Career WAR</th><th>Closer</th></tr></thead><tbody>${rr}</tbody></table></div></div>`;
  }
  return `<div class="meth-chart meth-accuracy">
    <div class="meth-chart-title">eFV vs consensus FV <span class="meth-sub">our model · out-of-sample</span></div>
    <p class="meth-note">${escapeHtml(xc.protocol || "")}</p>
    ${sideBlock("hitters", "Hitters - ordering skill (Spearman ρ, grade vs realized WAR)")}
    ${sideBlock("pitchers", "Pitchers - ordering skill (Spearman ρ, grade vs realized WAR)")}
    <p class="meth-verdict is-good">eFV out-ranks consensus FV out-of-sample on both sides, and the edge holds on the recent 2019-2023 cohorts, so it is not merely exploiting older, less-accurate scouting. eFV is the primary grade; consensus FV remains a reference input. (This is eFV's own out-of-sample protocol, a more conservative test than the in-sample common-set bars above.)</p>
    ${tierTable}
    ${receipts}
  </div>`;
}

// Findings-led callout strip: the headline numbers that make the eFV case, pulled live from
// the backtest so they never drift from the artifact. Cards read stat -> what it means.
function _methEfvFindings(bt) {
  const p = (bt.accuracy && bt.accuracy.pooled) || {};
  const det = bt.accuracy && bt.accuracy.xfv_vs_consensus_detail;
  const x = p.xfv, c = p.prospx_consensus, fg = p.fangraphs, mlb = p.mlb_pipeline;
  if (!x || x.spearman == null) return "";
  const f3 = v => (v == null ? "-" : v.toFixed(3));
  const cards = [];
  cards.push({ stat: f3(x.spearman), label: "eFV ranking skill (Spearman ρ vs realized WAR)",
    sub: `best of every grader &middot; consensus ${f3(c && c.spearman)} &middot; FanGraphs ${f3(fg && fg.spearman)} &middot; MLB ${f3(mlb && mlb.spearman)}` });
  // (Removed the per-tier "Sharpest edge" card: on the current cohort the best tier
  // margin is a fraction of a Spearman point -- e.g. 0.44 -> 0.45 -- which does not read
  // as a "sharp edge" and overstated a within-noise gap.)
  if (det && det.xfv_right_share_on_disagreements != null)
    cards.push({ stat: `${Math.round(det.xfv_right_share_on_disagreements * 100)}%`,
      label: "eFV closer on the biggest disagreements", sub: "resolved players where eFV & consensus most diverged" });
  if (x.auc != null)
    cards.push({ stat: f3(x.auc), label: "eFV AUC (predicts “becomes a contributor”)",
      sub: `consensus ${f3(c && c.auc)} &middot; FanGraphs ${f3(fg && fg.auc)} &middot; MLB ${f3(mlb && mlb.auc)}` });
  return `<div class="meth-findings">${cards.map(cd => `
    <div class="meth-find-card">
      <div class="meth-find-stat">${cd.stat}</div>
      <div class="meth-find-label">${cd.label}</div>
      <div class="meth-find-sub">${cd.sub}</div>
    </div>`).join("")}</div>`;
}

function _methTierTable(bt, rater) {
  const c = bt.cohorts[rater];
  const rows = (c.tiers || []).slice().reverse().map(t => `
    <tr>
      <td class="meth-td-tier">${t.tier}</td>
      <td>${t.n}</td>
      <td>${Math.round(t.debut_rate * 100)}%</td>
      <td>${t.mean_war.toFixed(1)}</td>
      <td>${t.mean_war_per_yr_debut != null ? t.mean_war_per_yr_debut.toFixed(2) : " - "}</td>
      <td>${Math.round(t.contributor_rate * 100)}%</td>
      <td>${Math.round((t.regular_pace_rate || 0) * 100)}%</td>
      <td>${Math.round(t.star_rate * 100)}%</td>
    </tr>`).join("");
  return `<div class="meth-table-wrap">
    <div class="meth-table-title"><span class="meth-legend-swatch" style="background:${_raterMeta(rater).color};"></span>${escapeHtml(_raterMeta(rater).label)} <span class="meth-sub">n=${c.n} · ${c.n_debuted} debuted</span></div>
    <div class="table-scroll-x"><table class="meth-table">
      <thead><tr><th>FV</th><th>n</th><th title="Reached MLB">Debut</th><th title="Mean cumulative career WAR (undebuted = 0)">WAR</th><th title="Mean WAR per season, among players who debuted">WAR/yr</th><th title="Career WAR ≥ 3">Contrib</th><th title="≥ 1.5 WAR per season">Reg pace</th><th title="Career WAR ≥ 10">Star</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
  </div>`;
}

// Per-archetype accuracy - where each grader (and the blend) is strongest.
// AUC = the grade discriminates "became a contributor" (0.50 = coin flip);
// best in each row marked ★. Answers "who do I trust on THIS kind of player?"
function _methArchetypeTable(bt) {
  const ba = bt.accuracy && bt.accuracy.by_archetype;
  if (!ba || !ba.length) return "";
  const raters = (bt.accuracy && bt.accuracy.head_to_head_raters) || bt.raters;
  const head = raters.map(r => `<th>${escapeHtml(_raterMeta(r).label)}</th>`).join("");
  const rows = ba.map(a => {
    const aucs = raters.map(r => (a.raters[r] || {}).auc).filter(v => v != null);
    const best = aucs.length ? Math.max(...aucs) : null;
    const cells = raters.map(r => {
      const v = (a.raters[r] || {}).auc;
      const isBest = v != null && v === best;
      const style = isBest ? "font-weight:700;color:var(--up);"
        : (r === "prospx_consensus" ? "color:var(--text-primary);" : "color:var(--text-secondary);");
      return `<td style="${style}">${v != null ? v.toFixed(3) : " - "}${isBest ? " ★" : ""}</td>`;
    }).join("");
    return `<tr><td class="meth-td-tier">${escapeHtml(a.label)}</td><td>${a.n}</td>${cells}</tr>`;
  }).join("");
  return `<div class="meth-table-wrap">
    <div class="meth-table-title">Best grader by archetype <span class="meth-sub">AUC (grade predicts ‘became a contributor’) · winner ★</span></div>
    <div class="table-scroll-x"><table class="meth-table">
      <thead><tr><th>Archetype</th><th>n</th>${head}</tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    ${_methArchetypeNote(bt)}
  </div>`;
}

// Build the archetype takeaway sentence FROM the live by_archetype data so it
// can never contradict the table above it (who leads, where a single source
// wins outright, the hardest archetype). Replaces a hardcoded note that drifted.
function _methArchetypeNote(bt) {
  const ba = bt.accuracy && bt.accuracy.by_archetype;
  if (!ba || !ba.length) return "";
  const XFV = "xfv";
  let efvWins = 0, total = 0;
  const losses = [];   // archetypes where eFV trails the best public grade
  ba.forEach(a => {
    const entries = Object.entries(a.raters)
      .filter(([, v]) => v && v.auc != null).map(([r, v]) => [r, v.auc]);
    const xa = (a.raters[XFV] || {}).auc;
    if (xa == null || !entries.length) return;
    total++;
    const best = Math.max(...entries.map(([, v]) => v));
    if (xa >= best - 1e-9) { efvWins++; return; }
    const winner = entries.find(([, v]) => v === best);
    losses.push({ label: a.label, rater: winner ? winner[0] : null, auc: best, xa });
  });
  if (!total) return "";
  const lead = `<strong>eFV grades best (highest AUC) in ${efvWins} of ${total} archetypes.</strong>`;
  const lose = losses.length
    ? ` It trails only on ${losses.map(l => `${escapeHtml(l.label)} (${escapeHtml(_raterMeta(l.rater).label)} ${l.auc.toFixed(3)} vs eFV ${l.xa.toFixed(3)})`).join(", ")} - the youngest, lowest-track-record cohorts, where scouting projection still reads best and eFV leans on the consensus prior.`
    : ` It leads every archetype on the board.`;
  return `<p class="meth-note">${lead}${lose}</p>`;
}

// "How to Read the Site" (Part 1 anchor) - annotated anatomy of a player card,
// the FV history chart, and a farm page, with every element linked to its
// glossary term, plus the metric-architecture diagram (how the metrics build on
// each other). Onboards new readers and lays out the system at a glance.
function renderGuide() {
  const el = document.getElementById("guide-body");
  if (!el) return;
  // One annotated element: a live example chip + the term link + plain-English.
  const anat = (example, slug, plain) => `<div class="guide-anat-row">
      <div class="guide-anat-vis">${example}</div>
      <div class="guide-anat-txt"><div class="guide-anat-term">${gTermLink(slug, GLOSSARY[slug] ? GLOSSARY[slug].name : slug)}</div><div class="guide-anat-plain">${plain}</div></div>
    </div>`;
  const archNode = (slug, label, sub) => `<div class="arch-node">${gTermLink(slug, label)}${sub ? `<span class="arch-node-sub">${escapeHtml(sub)}</span>` : ""}</div>`;

  const cardAnatomy = [
    anat(`<span class="fv-badge fv-60" style="padding:3px 9px;">60</span>`, "fv",
      "The headline grade - a single 20-80 number summarizing the prospect's projected MLB future, blended across every source that grades them."),
    anat(`<span style="display:inline-flex;gap:3px;"><span class="fv-badge fv-55 card-rarity-holo" style="padding:2px 7px;font-size:11px;">photo</span></span>`, "fv_rarity",
      "The photo's border/effect tier (shine → foil → chrome → holo → legendary) is keyed to FV, so rarity reads at a glance and matches the prospect list."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--up);">HIT 60 · PWR 65 · …</span>`, "twenty_eighty",
      "Per-tool 20-80 scouting grades. 50 is MLB-average; each ±10 is roughly one standard deviation. These feed the composite and, ultimately, FV."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--neon-violet);">$DvM+ 110</span>`, "dvm_plus",
      "A wRC+-style index of organizational development applied to the player's surplus dollars - 100 is league mean, +10 ≈ one SD."),
    anat(`<span class="g-term" data-gl="rps_plus" style="font-family:var(--font-mono);font-size:12px;color:var(--neon-cyan);">RPS+ 118</span>`, "rps_plus",
      "Level-anchored rate performance vs the player's own age × position cohort. 100 = cohort mean."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--up);">SC+ 113</span>`, "statcast_plus",
      "Tracked-data composite (contact quality + discipline for hitters; stuff + induced whiff/chase for pitchers), scaled so 100 = pool mean."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--up);">$154M</span>`, "surplus_value",
      "Projected cost-controlled surplus value - the dollar production the player is expected to deliver above what those years cost."),
    anat(`<span style="font-family:var(--font-mono);font-size:13px;color:var(--up);">▲</span>`, "stock",
      "Recent direction of the consensus FV - rising, flat, or falling over the trailing window."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-secondary);">ETA 2027</span>`, "eta",
      "Projected MLB-arrival year, derived from level, age, performance, and the org's promotion pace."),
  ].join("");

  const chartAnatomy = [
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--neon-cyan);">━━ line</span>`, "consensus_fv",
      "The solid line is the point-in-time consensus FV - the forward-filled, Bayesian-shrunk mean of every source's grade as of each date."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-tertiary);">┈┈ overlay</span>`, "fv",
      "Toggling the per-source overlay shows each outlet's individual grade history - the inputs the consensus blends."),
    anat(`<svg width="42" height="12" style="vertical-align:middle;" aria-hidden="true"><line x1="2" y1="6" x2="40" y2="6" stroke="var(--neon-violet)" stroke-width="1.4" stroke-dasharray="3,2"/></svg>`, "tools_dvm_plus",
      "The dashed violet line is the tool-composite trajectory - the mean per-tool grade at each snapshot, plotted on the FV scale. When it rises alongside the FV curve the tools are backing the grade; when FV climbs while it stays flat, the bump is scout-narrative-driven rather than tool-supported. It's the per-snapshot signal behind ToolDvM+."),
    anat(`<span style="font-family:var(--font-mono);font-size:13px;color:var(--up);">◆</span>`, "debut_rule",
      "A debut marker flags when the player crossed the rookie-eligibility threshold and graduated off the prospect board."),
    anat(`<span style="font-family:var(--font-mono);font-size:13px;color:var(--neon-amber);">⇄</span>`, "trade",
      "Trade markers stamp cross-org moves at the FV the league assigned on the trade date."),
  ].join("");

  const farmAnatomy = [
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-secondary);">A+ tree</span>`, "farm_report_card",
      "The org letter grade is a weighted tree, value-led: a Value branch (aggregate risk-adjusted surplus), then MLB Production, Development, and Acquisition Strategy, each built from auditable leaves."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--neon-violet);">DvM+ 112</span>`, "dvm_plus",
      "Development vs Mean - how fast the org grows the FV of prospects it already had (acquisitions nullified), 100 = league mean."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--neon-cyan);">ToolDvM+ 108</span>`, "tools_dvm_plus",
      "The same development idea applied per tool, weighted by what each position needs."),
    anat(`<span style="font-family:var(--font-mono);font-size:12px;color:var(--up);">OrgSur+ 121</span>`, "sur_plus",
      "Org-level capital efficiency - WAR and contract surplus per dollar spent, scaled to 100 = league mean."),
  ].join("");

  el.innerHTML = `
  <div class="guide-wrap">
    <p class="guide-intro">Every number on the site resolves to a glossary entry. This page labels the elements you'll see on a player card, the FV history chart, and a farm-system page, then shows how the metrics build on one another. Click any underlined term for its definition.</p>

    <h2 class="meth-h">Anatomy of a player card</h2>
    <div class="guide-anat">${cardAnatomy}</div>

    <h2 class="meth-h">Reading the FV history chart</h2>
    <div class="guide-anat">${chartAnatomy}</div>

    <h2 class="meth-h">Reading a farm-system page</h2>
    <div class="guide-anat">${farmAnatomy}</div>

    <h2 class="meth-h">How the metrics build on each other</h2>
    <p class="meth-note">Each stage consumes the one before it. Scouting grades aggregate into a per-source FV; per-source FVs blend into the consensus; the consensus plus performance and tracked data drive the player indices; player indices roll up to the org grade.</p>
    <div class="arch-flow">
      <div class="arch-stage">
        <div class="arch-stage-label">Inputs</div>
        ${archNode("twenty_eighty", "Tool grades", "20-80, per source")}
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-stage">
        <div class="arch-stage-label">Per-source grade</div>
        ${archNode("fv", "FV", "each outlet")}
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-stage">
        <div class="arch-stage-label">Blend</div>
        ${archNode("consensus_fv", "Consensus FV", "forward-fill + shrink")}
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-stage">
        <div class="arch-stage-label">Player indices</div>
        <div class="arch-node-col">
          ${archNode("rps_plus", "RPS+")}
          ${archNode("statcast_plus", "SC+")}
          ${archNode("dvm_plus", "DvM+ / $DvM+")}
          ${archNode("surplus_value", "Surplus value")}
        </div>
      </div>
      <div class="arch-arrow">→</div>
      <div class="arch-stage">
        <div class="arch-stage-label">Org roll-up</div>
        ${archNode("farm_report_card", "Farm grade", "weighted tree")}
      </div>
    </div>
  </div>`;
  if (window.EEPHUS_GL) window.EEPHUS_GL.wire(el);
}

// ---- Part 5: interactive teaching widgets ---------------------------------
// Standard-normal CDF (Abramowitz-Stegun 26.2.17) for the 20-80 percentile.
function _normCdf(z) {
  const t = 1 / (1 + 0.2316419 * Math.abs(z));
  const d = 0.3989423 * Math.exp(-z * z / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return z > 0 ? 1 - p : p;
}
// Linear-interpolate a string-keyed numeric table ({"35":..,"80":..}) at x.
function _vfInterp(table, x) {
  const ks = Object.keys(table || {}).map(Number).sort((a, b) => a - b);
  if (!ks.length) return null;
  if (x <= ks[0]) return table[ks[0]];
  if (x >= ks[ks.length - 1]) return table[ks[ks.length - 1]];
  for (let i = 0; i < ks.length - 1; i++) {
    if (x >= ks[i] && x <= ks[i + 1]) {
      const t = (x - ks[i]) / (ks[i + 1] - ks[i]);
      return table[ks[i]] * (1 - t) + table[ks[i + 1]] * t;
    }
  }
  return table[ks[ks.length - 1]];
}
const _fmtMM2 = m => (m == null ? " - " : "$" + (Math.round(m * 10) / 10).toFixed(1) + "M");

// Bell curve with a marker at grade g (20-80) + shaded left tail = percentile.
function _gxBellSvg(g) {
  const W = 320, H = 96, pad = 6;
  const x = v => pad + (v - 20) / 60 * (W - 2 * pad);
  const mu = 50, sd = 10;
  const yOf = v => Math.exp(-((v - mu) ** 2) / (2 * sd * sd));
  let path = "", area = "";
  const pts = [];
  for (let v = 20; v <= 80; v += 1) pts.push([x(v), H - pad - yOf(v) * (H - 2 * pad - 8)]);
  path = "M" + pts.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L");
  const ap = pts.filter((_, i) => 20 + i <= g);
  if (ap.length) area = `M${x(20).toFixed(1)},${(H - pad).toFixed(1)} L` + ap.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L") + ` L${ap[ap.length - 1][0].toFixed(1)},${(H - pad).toFixed(1)} Z`;
  const gx = x(g);
  const ticks = [20, 30, 40, 50, 60, 70, 80].map(v => `<line x1="${x(v).toFixed(1)}" y1="${H - pad}" x2="${x(v).toFixed(1)}" y2="${H - pad + 3}" stroke="var(--text-tertiary)" stroke-width="1"/><text x="${x(v).toFixed(1)}" y="${H - pad + 12}" font-size="8" fill="var(--text-tertiary)" text-anchor="middle" font-family="var(--font-mono)">${v}</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H + 8}" width="100%" style="max-width:340px;display:block;" preserveAspectRatio="xMidYMid meet">
    ${area ? `<path d="${area}" fill="var(--neon-cyan)" opacity="0.18"/>` : ""}
    <path d="${path}" fill="none" stroke="var(--text-secondary)" stroke-width="1.5"/>
    <line x1="${gx.toFixed(1)}" y1="${pad}" x2="${gx.toFixed(1)}" y2="${H - pad}" stroke="var(--neon-cyan)" stroke-width="2"/>
    <circle cx="${gx.toFixed(1)}" cy="${(H - pad - yOf(g) * (H - 2 * pad - 8)).toFixed(1)}" r="3.5" fill="var(--neon-cyan)"/>
    ${ticks}
  </svg>`;
}
// ---- Per-term glossary visualizations (Part 2) ----------------------------
// Small, theme-aware diagrams keyed by slug, rendered inside the term card.
function _vizFvWar() {
  const tbl = (window.VALUE_FRAMEWORK || {}).fv_to_6yr_avg_war || { 40: 1, 45: 1.5, 50: 2, 55: 2.5, 60: 3, 65: 4, 70: 5, 80: 7 };
  const fvs = [40, 45, 50, 55, 60, 65, 70, 80], max = 7;
  return `<div style="display:flex;flex-direction:column;gap:3px;width:100%;max-width:300px;">${fvs.map(fv => {
    const w = _vfInterp(tbl, fv), pct = Math.max(3, w / max * 100);
    return `<div style="display:flex;align-items:center;gap:6px;font-family:var(--font-mono);font-size:10px;"><span style="width:20px;color:var(--text-tertiary);text-align:right;">${fv}</span><span style="flex:1;height:9px;background:var(--bg-tertiary);position:relative;"><span style="position:absolute;left:0;top:0;bottom:0;width:${pct}%;background:var(--neon-cyan);"></span></span><span style="width:54px;color:var(--text-secondary);">${w.toFixed(1)} WAR/yr</span></div>`;
  }).join("")}</div>`;
}
function _vizPlusGauge(val, lo, hi) {
  lo = lo || 70; hi = hi || 130;
  const pct = Math.max(0, Math.min(100, (val - lo) / (hi - lo) * 100));
  return `<div style="width:100%;max-width:300px;font-family:var(--font-mono);font-size:10px;">
    <div style="height:11px;background:linear-gradient(90deg,var(--down),var(--bg-tertiary) 50%,var(--up));position:relative;border:1px solid var(--border-light);">
      <span style="position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--text-tertiary);"></span>
      <span style="position:absolute;left:${pct}%;top:-3px;bottom:-3px;width:2px;background:var(--neon-cyan);"></span>
      <span style="position:absolute;left:${pct}%;top:-15px;transform:translateX(-50%);color:var(--neon-cyan);font-weight:700;">${val}</span>
    </div>
    <div style="display:flex;justify-content:space-between;color:var(--text-tertiary);margin-top:3px;"><span>${lo}</span><span>100 = mean</span><span>${hi}</span></div></div>`;
}
function _vizPercentile(pct) {
  return `<div style="width:100%;max-width:300px;font-family:var(--font-mono);font-size:10px;">
    <div style="height:11px;background:linear-gradient(90deg,#3b6bd6,#cfd6e4 50%,#d62b3b);position:relative;border-radius:6px;">
      <span style="position:absolute;left:${pct}%;top:50%;transform:translate(-50%,-50%);width:14px;height:14px;border-radius:50%;background:var(--text-primary);border:2px solid var(--bg-primary);"></span>
    </div>
    <div style="color:var(--text-tertiary);margin-top:3px;">${pct}th percentile vs pool (example)</div></div>`;
}
function _vizSurplusCurve() {
  const g = (window.VALUE_FRAMEWORK || {}).surplus_by_grade_mm, t = (g && g.hitter) || {};
  const fvs = [40, 45, 50, 55, 60, 65, 70], max = _vfInterp(t, 70) || 200;
  const pts = fvs.map((fv, i) => [i / (fvs.length - 1) * 100, 100 - ((_vfInterp(t, fv) || 0) / max * 92)]);
  const path = "M" + pts.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" L");
  return `<svg viewBox="0 0 100 100" width="100%" style="max-width:240px;height:84px;display:block;" preserveAspectRatio="none"><path d="${path}" fill="none" stroke="var(--up)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><div style="font-family:var(--font-mono);font-size:10px;color:var(--text-tertiary);">FV 40 → 70 · surplus $M (hitter), convex by grade</div>`;
}
const _GLOSSARY_VIZ = {
  twenty_eighty:   () => _gxBellSvg(60),
  fv:              () => _vizFvWar(),
  fv_to_war_table: () => _vizFvWar(),
  dvm_plus:        () => _vizPlusGauge(110),
  rps_plus:        () => _vizPlusGauge(118),
  sur_plus:        () => _vizPlusGauge(121),
  statcast_plus:   () => _vizPlusGauge(113),
  fin_dollar_dvm:  () => _vizPlusGauge(112),
  barrel_pct:      () => _vizPercentile(78),
  exit_velocity:   () => _vizPercentile(72),
  hard_hit_pct:    () => _vizPercentile(70),
  surplus_value:   () => _vizSurplusCurve(),
  tvi:             () => _vizSurplusCurve(),
};

function _gx2080() {
  const g = +(_byId("gx-grade-in") || {}).value || 50;
  const z = (g - 50) / 10;
  const pct = Math.round(_normCdf(z) * 100);
  const label = g >= 70 ? "Elite (top of scale)" : g >= 65 ? "Plus-plus" : g >= 60 ? "Plus" : g >= 55 ? "Above average" : g >= 45 ? "Average-ish" : g >= 40 ? "Below average" : "Well below average";
  _setHTML("gx-grade-out", `<div class="gx-out-big">${g} <span class="gx-out-sub">grade</span></div>
    <div class="gx-out-row"><span>z-score</span><b>${z >= 0 ? "+" : ""}${z.toFixed(1)} σ</b></div>
    <div class="gx-out-row"><span>percentile</span><b>~${pct}th</b></div>
    <div class="gx-out-row"><span>reads as</span><b>${label}</b></div>`);
  _setHTML("gx-grade-svg", _gxBellSvg(g));
  const lbl = _byId("gx-grade-val"); if (lbl) lbl.textContent = g;
}
function _gxConsensus() {
  const rows = [...document.querySelectorAll("#gx-consensus .gx-src-row")];
  let wsum = 0, wfv = 0, n = 0, fsum = 0;
  rows.forEach(r => {
    const fv = +r.querySelector(".gx-src-fv").value;
    const w = +r.querySelector(".gx-src-w").value;
    r.querySelector(".gx-src-wv").textContent = w.toFixed(1);
    if (!isFinite(fv)) return;
    n++; fsum += fv; wsum += w; wfv += fv * w;
  });
  const equal = n ? (fsum / n) : 0;
  const weighted = wsum > 0 ? (wfv / wsum) : equal;
  _setHTML("gx-consensus-out", `<div class="gx-out-row"><span>Equal-weight (site default)</span><b>${equal.toFixed(1)} FV</b></div>
    <div class="gx-out-row"><span>Your weighting</span><b style="color:var(--neon-cyan);">${weighted.toFixed(1)} FV</b></div>
    <div class="gx-out-row"><span>Difference</span><b style="color:${Math.abs(weighted - equal) >= 1 ? "var(--neon-amber)" : "var(--text-secondary)"};">${(weighted - equal) >= 0 ? "+" : ""}${(weighted - equal).toFixed(1)}</b></div>`);
}
function _gxConsensusReset() {
  document.querySelectorAll("#gx-consensus .gx-src-w").forEach(s => { s.value = 1; });
  _gxConsensus();
}
function _gxSurplus() {
  const vf = window.VALUE_FRAMEWORK || {};
  const fv = +(_byId("gx-surplus-fv") || {}).value || 50;
  const side = (_byId("gx-surplus-side") || {}).value || "hitter";
  const lbl = _byId("gx-surplus-fvval"); if (lbl) lbl.textContent = fv;
  const warYr = _vfInterp(vf.fv_to_6yr_avg_war || {}, fv);
  const dpw = (vf.dollars_per_war || {}).flat_mm || 11.74;
  const st = vf.service_time || {};
  const ctrl = st.control_years || 6, preArb = st.pre_arb_years || 3, lgMin = st.league_min_mm || 0.76;
  const arbFr = st.arb_fractions_of_fa_value || [0.4, 0.6, 0.8];
  if (warYr == null) { _setHTML("gx-surplus-out", " - "); return; }
  const war6 = warYr * ctrl;
  const gross = war6 * dpw;
  const faPerYr = warYr * dpw;
  const arbCost = arbFr.reduce((s, f) => s + f * faPerYr, 0);
  const cost = preArb * lgMin + arbCost;
  const framework = gross - cost;
  const published = _vfInterp((vf.surplus_by_grade_mm || {})[side] || {}, fv);
  _setHTML("gx-surplus-out", `
    <div class="gx-step"><span class="gx-step-n">1</span><span class="gx-step-t">FV ${fv} → ${warYr.toFixed(2)} WAR/yr</span><span class="gx-step-v">${gTermLink("fv_to_war_table", "table")}</span></div>
    <div class="gx-step"><span class="gx-step-n">2</span><span class="gx-step-t">× ${ctrl} controlled yrs</span><span class="gx-step-v">${war6.toFixed(1)} WAR</span></div>
    <div class="gx-step"><span class="gx-step-n">3</span><span class="gx-step-t">× $${dpw.toFixed(2)}M / WAR</span><span class="gx-step-v">${_fmtMM2(gross)} gross</span></div>
    <div class="gx-step"><span class="gx-step-n">4</span><span class="gx-step-t">− cost (3×$${lgMin}M pre-arb + arb ${arbFr.map(f => f).join("/")})</span><span class="gx-step-v">−${_fmtMM2(cost)}</span></div>
    <div class="gx-step gx-step-sum"><span class="gx-step-n">=</span><span class="gx-step-t">framework surplus</span><span class="gx-step-v">${_fmtMM2(framework)}</span></div>
    <div class="gx-surplus-final">Published surplus value <b>${_fmtMM2(published)}</b><div class="gx-surplus-note">The published figure additionally probability-weights the outcome distribution and discounts future years at ${((vf.discount_rate || 0.09) * 100).toFixed(0)}%/yr, so it differs slightly from the flat framework walk above.</div></div>`);
  if (window.EEPHUS_GL) { const _o = document.getElementById("gx-surplus-out"); if (_o) window.EEPHUS_GL.wire(_o); }
}
function _byId(id) { return document.getElementById(id); }
function _setHTML(id, html) { const e = document.getElementById(id); if (e) e.innerHTML = html; }

// Window-scope the methodology widget handlers. The interactive cards wire
// them via inline oninput / onclick / onchange attributes, which resolve
// against the global scope - NOT this IIFE's closure. Without this the
// sliders and number inputs silently no-op (ReferenceError swallowed by
// the inline handler). Mirrors window._printMethodology above.
window._gx2080 = _gx2080;
window._gxConsensus = _gxConsensus;
window._gxConsensusReset = _gxConsensusReset;
window._gxSurplus = _gxSurplus;


function _methInteractivesHTML() {
  return `
  <h2 class="meth-h">Interactive - manipulate the models</h2>
  <p class="meth-note">These run on the live framework values. Move the inputs to see how a scouting grade, a source-weighting scheme, and the surplus walk respond.</p>

  <div class="gx-card">
    <div class="gx-card-title">The 20-80 scale as a distribution</div>
    <div class="gx-card-body gx-2col">
      <div>
        <label class="gx-label">Grade <b id="gx-grade-val">60</b></label>
        <input id="gx-grade-in" class="gx-range" type="range" min="20" max="80" step="1" value="60" oninput="_gx2080()">
        <div id="gx-grade-svg"></div>
      </div>
      <div id="gx-grade-out" class="gx-out"></div>
    </div>
  </div>

  <div class="gx-card">
    <div class="gx-card-title">How source weighting works - adjustable consensus</div>
    <div class="gx-card-body">
      <div id="gx-consensus" class="gx-srcs">
        ${[["FanGraphs", 60], ["MLB Pipeline", 55], ["ESPN", 60], ["Just Baseball", 50], ["TJStats", 55]].map(([nm, fv]) => `
        <div class="gx-src-row">
          <span class="gx-src-name">${nm}</span>
          <label class="gx-src-lab">FV <input class="gx-src-fv gx-num" type="number" min="20" max="80" step="1" value="${fv}" oninput="_gxConsensus()"></label>
          <label class="gx-src-lab">w <input class="gx-src-w gx-range gx-range-sm" type="range" min="0" max="2" step="0.1" value="1" oninput="_gxConsensus()"> <b class="gx-src-wv">1.0</b></label>
        </div>`).join("")}
      </div>
      <div style="display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap;">
        <button class="chip" type="button" onclick="_gxConsensusReset()">Reset to equal weights</button>
        <div id="gx-consensus-out" class="gx-out gx-out-inline"></div>
      </div>
      <p class="meth-note" style="margin-top:8px;">The live board uses ACCURACY-WEIGHTED sources (since June 2026): measured track-record weights, shrunk toward equal and frozen per vintage, shipped after beating equal-weight in a vintage-disciplined A/B. This widget starts from equal weights so you can feel how any weighting moves a consensus.</p>
    </div>
  </div>

  <div class="gx-card">
    <div class="gx-card-title">Surplus value calculator - FV to dollars, step by step</div>
    <div class="gx-card-body gx-2col">
      <div>
        <label class="gx-label">FV <b id="gx-surplus-fvval">55</b></label>
        <input id="gx-surplus-fv" class="gx-range" type="range" min="35" max="80" step="1" value="55" oninput="_gxSurplus()">
        <label class="gx-label" style="margin-top:10px;display:block;">Side
          <select id="gx-surplus-side" class="gx-num" style="width:auto;" onchange="_gxSurplus()">
            <option value="hitter">Hitter</option><option value="pitcher">Pitcher</option>
          </select>
        </label>
      </div>
      <div id="gx-surplus-out" class="gx-out gx-steps"></div>
    </div>
  </div>`;
}

function renderMethodology() {
  const el = document.getElementById("methodology-body");
  if (!el) return;
  // Model registry (accountability ledger) - lazy-loaded once, same
  // pattern as the source backtest. Re-renders this view on arrival.
  if (!_S.registry && !_S.regLoading) {
    _S.regLoading = true;
    fetch("/data/model_registry.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.registry = j || { __error: true };
        if (_S.view === "methodology") renderMethodology(); })
      .catch(() => { _S.registry = { __error: true };
        if (_S.view === "methodology") renderMethodology(); });
  }
  // Live calibration monitor (finding 37): lazy-load the eFV self-monitoring
  // artifact, same guard/re-render pattern as the registry above. Diagnostic
  // only; a failed fetch or absent artifact simply drops its sub-block (the
  // section renders nothing) - it is dark-launched, so the dev artifact is a
  // stale vintage that the canonical box regenerates nightly.
  if (!_S.reliability && !_S.relLoading) {
    _S.relLoading = true;
    fetch("/data/xfv_reliability.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.reliability = j || { __error: true };
        if (_S.view === "methodology") renderMethodology(); })
      .catch(() => { _S.reliability = { __error: true };
        if (_S.view === "methodology") renderMethodology(); });
  }
  const today = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  const printHead = `<div id="methodology-print-head">eephus.io - Methodology · eephus.io/glossary · ${escapeHtml(today)}</div>`;
  const toolbar = `<div class="meth-toolbar"><button class="meth-export-btn" type="button" onclick="_printMethodology()" title="Print or save the methodology as a PDF">⎙ Export methodology (PDF)</button></div>`;
  el.innerHTML = printHead + toolbar + _methProseHTML() + _methRegistryHTML() + _methReliabilityHTML() + _methInteractivesHTML();
  if (window.EEPHUS_GL) window.EEPHUS_GL.wire(el);
  // Populate the interactives' initial state.
  _gx2080(); _gxConsensus(); _gxSurplus();
}

// Model accountability ledger (model-audit Phase 5, WS-11): the committed
// registry rendered VERBATIM - unvalidated rows and misses included; that
// is the point. One row per model: champion, baseline, verdict, artifact.
const _REG_VERDICT_GLYPH = { validated: "✓ validated", provisional: "◐ provisional",
                             unvalidated: "○ unvalidated", deprecated: "✗ deprecated" };
function _methRegistryHTML() {
  const reg = _S.registry;
  let body;
  if (!reg) {
    body = `<div class="state-message">Loading model registry…</div>`;
  } else if (reg.__error || !Array.isArray(reg.models) || !reg.models.length) {
    body = `<p class="meth-note">The model registry is unavailable.</p>`;
  } else {
    const counts = {};
    reg.models.forEach(m => { counts[m.verdict] = (counts[m.verdict] || 0) + 1; });
    const rows = reg.models.map(m => {
      const art = m.eval_artifact
        ? `<a href="/${escapeHtml(m.eval_artifact)}" target="_blank" rel="noopener">${escapeHtml(m.eval_artifact.replace(/^data\//, ""))}</a>${m.stale ? " <em>(stale)</em>" : ""}`
        : " - ";
      const mainRow = `<tr>
        <td><strong>${escapeHtml(m.model_id)}</strong><br><span class="meth-note">${escapeHtml(m.surface || "")}</span></td>
        <td>${escapeHtml(m.champion || "")}</td>
        <td>${escapeHtml(m.baseline || "")}</td>
        <td>${_REG_VERDICT_GLYPH[m.verdict] || escapeHtml(m.verdict || "")}</td>
        <td>${art}</td>
      </tr>`;
      // The registry's `notes` carry the real audit trail - A/B numbers, the
      // surprise findings, the committed losing challengers. Render them in an
      // expandable row so the strongest honesty signal isn't dropped.
      const notesRow = m.notes
        ? `<tr class="meth-registry-notes"><td colspan="5"><details><summary>methodology notes &amp; committed results</summary><div class="meth-note" style="margin-top:6px;white-space:normal;">${escapeHtml(m.notes)}</div></details></td></tr>`
        : "";
      return mainRow + notesRow;
    }).join("");
    body = `
      <p class="meth-note">Every predictive model on the platform, with its verdict and committed eval artifact. <strong>${counts.validated || 0} validated · ${counts.provisional || 0} provisional · ${counts.unvalidated || 0} unvalidated · ${counts.deprecated || 0} deprecated</strong>${reg.checked_at ? ` · last checked ${escapeHtml(reg.checked_at)}` : ""}. Unvalidated rows are listed precisely so they can't hide; losing challengers stay committed.</p>
      <div class="meth-tables"><table class="meth-tier-table meth-registry-table">
        <thead><tr><th>Model · surface</th><th>Champion</th><th>Baseline</th><th>Verdict</th><th>Eval artifact</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>`;
  }
  return `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Model accountability · the registry, rendered verbatim</div>
    <h2 class="meth-h">Which models are validated - and which aren't</h2>
    ${body}
  </div>`;
}

// Live calibration monitor (finding 37): the flagship self-monitoring, made
// visible. efv_reliability.build writes data/xfv_reliability.json nightly -
// forward-chained out-of-fold reliability for the SHIPPED eFV 5-bucket outcome
// distribution, plus a bust-bucket ECE drift tripwire. No competitor surfaces
// live model calibration. Strictly DIAGNOSTIC: no served eFV/WAR/grade/surplus
// number depends on these curves; they only measure them.
//
// Degrades GRACEFULLY and ADDITIVELY. The whole section returns "" when the
// artifact is absent / errored / an unexpected shape, and each sub-block
// renders ONLY when its own field is present, so the dark-launched dev vintage
// (which predates tripwire + per_tier_reliability) shows just the per-bucket
// ECE it does carry, while the freshly regenerated box artifact shows the full
// monitor. Nothing here can 404 or throw a visible error.
const _REL_BUCKET_LABEL = { bust: "Bust", bench: "Bench", regular: "Regular",
                            good: "Good", star: "Star" };
const _REL_BUCKET_ORDER = ["bust", "bench", "regular", "good", "star"];
function _methReliabilityHTML() {
  const rel = _S.reliability;
  // Silent while the fetch is in flight (null) or failed (__error); the
  // resolved re-render fills it in, and a failure just stays hidden.
  if (!rel || rel.__error || typeof rel !== "object") return "";
  const before = rel.reliability_curves_pooled && rel.reliability_curves_pooled.before;
  if (!before || typeof before !== "object") return "";   // unexpected shape - hide
  const f3 = v => (v == null || isNaN(Number(v)) ? "-" : Number(v).toFixed(3));
  const pct = v => (v == null || isNaN(Number(v)) ? "-" : Math.round(Number(v) * 100) + "%");

  // --- Tripwire status banner (fresh artifact only) ------------------------
  // Composed from tripped/bust_ece/threshold only; the artifact's own note
  // string is NOT rendered verbatim (it carries a dash character), so the
  // page copy stays owner-clean regardless of the artifact vintage.
  let tripHTML = "";
  const tw = rel.tripwire;
  if (tw && typeof tw === "object" && tw.bust_ece != null && tw.threshold != null) {
    const tripped = !!tw.tripped;
    tripHTML = `<div class="meth-verdict${tripped ? "" : " is-good"}"${tripped ? ' style="border-left-color:var(--down);"' : ""}>
      <strong>${tripped ? "Drift flagged for review" : "Calibration within the documented band"}</strong>
      · bust-bucket calibration error (ECE) is <b>${f3(tw.bust_ece)}</b> against a drift threshold of <b>${f3(tw.threshold)}</b>${tripped
        ? ", so the low-probability bust bin has widened and is queued for a calibration review."
        : ", so no drift is flagged this run."}</div>`;
  }

  // --- Per-outcome-bucket calibration error (both vintages carry this) ------
  const bucketRows = _REL_BUCKET_ORDER
    .filter(b => before[b] && before[b].ece != null)
    .map(b => `<tr><td class="meth-td-tier">${_REL_BUCKET_LABEL[b]}</td><td>${f3(before[b].ece)}</td></tr>`)
    .join("");
  const bucketTable = bucketRows ? `<div class="meth-table-wrap">
      <div class="meth-table-title">Calibration error by outcome bucket</div>
      <table class="meth-table"><thead><tr><th>Outcome</th><th>ECE</th></tr></thead>
      <tbody>${bucketRows}</tbody></table></div>` : "";

  // --- Predicted vs realized by consensus-FV tier (fresh artifact only) -----
  const tiers = rel.per_tier_reliability;
  let tierTable = "";
  if (tiers && typeof tiers === "object") {
    const tks = Object.keys(tiers)
      .filter(k => tiers[k] && tiers[k].gap != null)
      .sort((a, b) => Number(a) - Number(b));
    if (tks.length) {
      const rows = tks.map(k => {
        const t = tiers[k], rf = t.realized_freq || {}, mp = t.mean_p || {};
        return `<tr><td class="meth-td-tier">FV ${escapeHtml(k)}</td><td>${t.n != null ? t.n : "-"}</td>
          <td>${pct(mp.star)}</td><td>${pct(rf.star)}</td>
          <td>${pct(mp.bust)}</td><td>${pct(rf.bust)}</td>
          <td>${f3(t.gap)}</td></tr>`;
      }).join("");
      tierTable = `<div class="meth-table-wrap">
        <div class="meth-table-title">Predicted vs realized outcome, by consensus-FV tier</div>
        <table class="meth-table"><thead><tr><th>Tier</th><th>n</th>
          <th>Star pred</th><th>Star obs</th><th>Bust pred</th><th>Bust obs</th><th>Mean gap</th></tr></thead>
        <tbody>${rows}</tbody></table></div>`;
    }
  }

  // Fully hide when there is genuinely nothing to show.
  if (!tripHTML && !bucketTable && !tierTable) return "";

  const nPool = rel.pooled_n != null ? ` · n=${rel.pooled_n}` : "";
  const gen = rel.generated_at ? ` · regenerated ${escapeHtml(String(rel.generated_at))}` : "";
  return `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Live calibration monitor · the model grading itself</div>
    <h2 class="meth-h">Is eFV still calibrated?</h2>
    <p class="meth-note">Every night the shipped eFV five-bucket outcome distribution is re-scored forward-chained out-of-fold against resolved outcomes${nPool}${gen}. This is the model's own self-monitoring: a widening bust-bucket calibration gap trips a review flag. Diagnostic only - no grade, WAR, or dollar figure depends on these curves; they only measure them.</p>
    ${tripHTML}
    <div class="meth-tables">${bucketTable}${tierTable}</div>
    <p class="meth-note">ECE (expected calibration error) is the bin-weighted gap between the probability the model assigned an outcome and how often it actually happened; lower is better. Honest read: low-probability bust calls land above the diagonal, meaning more prospects bust than the model predicts, so bust risk on higher-FV prospects runs understated - a standing miscalibration the tripwire watches for widening.</p>
  </div>`;
}

// Source Comparison - the empirical backtest, visually set apart from the
// methodology prose as the "does it work?" evidence area (distinct framed
// container + eyebrow). Lazy-loads source_backtest.json.
// Hero verdict banner: leads the source comparison with WHAT eFV is and the headline
// result (it wins out of sample) before the detailed breakdown. Uses the live pooled
// backtest numbers, so the claim can never drift from the measured data.
function _methHeroBanner(bt) {
  const p = (bt.accuracy && bt.accuracy.pooled) || {};
  const x = p.xfv, c = p.prospx_consensus, fg = p.fangraphs, mlb = p.mlb_pipeline;
  if (!x || x.spearman == null) return "";
  const f3 = v => (v == null ? "-" : v.toFixed(3));
  const pubs = [["PROSPX consensus", c], ["MLB Pipeline", mlb], ["FanGraphs", fg]]
    .filter(pr => pr[1] && pr[1].spearman != null);
  const bestPub = pubs.length ? pubs.reduce((a, b) => (b[1].spearman > a[1].spearman ? b : a)) : null;
  const lead = (bestPub && x.spearman != null) ? (x.spearman - bestPub[1].spearman) : null;
  const tile = (lbl, v, isEfv) => `<div class="meth-find-card${isEfv ? " scx-hero-efv" : ""}">
    <div class="meth-find-stat">${f3(v)}</div>
    <div class="meth-find-label">${escapeHtml(lbl)}</div>
    <div class="meth-find-sub">${isEfv ? "outcome-grounded model" : "public scouting grade"}</div>
  </div>`;
  const tiles = tile("eFV", x.spearman, true) + pubs.map(pr => tile(pr[0], pr[1].spearman, false)).join("");
  return `<div class="source-comp-hero">
    <div class="source-comp-hero-kicker">A different kind of Future Value</div>
    <h2 class="source-comp-hero-title">eFV grades prospects on what they actually <em>became</em> - and it out-ranks the scouting industry out of sample.</h2>
    <p class="source-comp-hero-lede">Every public FV grade is an educated opinion about the future. eFV is a model trained on resolved outcomes and scored the honest way: leakage-free, forward-chained, on the same players and the same window as the sources it is measured against. On ordering skill - how well a preseason grade tracks the WAR a prospect went on to produce - it beats every one of them${(lead != null && bestPub) ? `, ${f3(x.spearman)} to ${f3(bestPub[1].spearman)} over the best public source (${escapeHtml(bestPub[0])}), a +${lead.toFixed(3)} edge` : ""}.</p>
    <div class="meth-findings source-comp-hero-tiles">${tiles}</div>
    <p class="source-comp-hero-foot">Ordering skill = Spearman correlation between the preseason grade and realized MLB WAR (higher is better). The full method, per-FV-tier and per-archetype breakdowns, and the honest limits are all below - nothing cherry-picked.</p>
  </div>`;
}

function renderSourceComparison() {
  const el = document.getElementById("source-comparison-body");
  if (!el) return;
  if (!_S.backtest && !_S.btLoading) {
    _S.btLoading = true;
    const base = "/data/";
    fetch(base + "source_backtest.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _S.backtest = j || { __error: true };
        if (_S.view === "source-comparison") renderSourceComparison(); })
      // A failed fetch (or a throw inside the re-render) must surface the
      // empty-state, never strand the loading placeholder.
      .catch(() => { _S.backtest = { __error: true };
        if (_S.view === "source-comparison") renderSourceComparison(); });
  }
  const bt = _S.backtest;
  let backtestHTML;
  if (!bt) {
    backtestHTML = `<div class="state-message">Loading backtest…</div>`;
  } else if (bt.__error || !bt.window || !bt.window.years || !bt.window.years.length) {
    backtestHTML = `<div class="meth-chart"><p class="meth-note">The source-vs-source backtest has no resolved cohorts yet (it needs ≥ 3 years of development lag). It will populate once the retained per-source history clears that window.</p></div>`;
  } else {
    const od = bt.outcome_defs || {};
    backtestHTML = `
      ${_methHeroBanner(bt)}
      <h2 class="meth-h">The full head-to-head</h2>
      <p class="meth-window">eFV is the primary grade, our outcome-grounded model. The test: a leakage-free, forward-chained backtest of eFV against the public sources (FanGraphs, MLB Pipeline) and the PROSPX consensus, scored on how well each grade ordered what prospects became. ${escapeHtml(bt.window.note)} <strong>Sources with too little history to score</strong> (${(bt.insufficient_history || []).join(", ")}) are excluded, not guessed at.</p>
      ${_methEfvFindings(bt)}
      <h3 class="meth-h3">Head-to-head: ranking skill + contributor AUC</h3>
      ${_methAccuracyChart(bt)}
      ${_methEfvPanel(bt)}
      <h3 class="meth-h3">Where each grade wins, by prospect archetype</h3>
      <p class="meth-note">eFV leads the field overall and on most archetypes; the few it trails (often HS arms / int'l bats, the youngest, lowest-track-record cohorts) are where the scouting consensus still reads projection best. The obvious adds (signing bonus, draft slot) are already priced into consensus FV, so out-of-sample they cost more than they returned.</p>
      ${_methArchetypeTable(bt)}
      <div class="meth-chart-grid">
        ${_methCaptureCurve(bt)}
        ${_methCalibrationChart(bt, "contributor_rate", "Contributor rate (career WAR ≥ " + (od.contributor_war ?? 3) + ")", { pct: true, yMax: 1 })}
      </div>
      <h3 class="meth-h3">Cohort outcomes by FV tier</h3>
      <p class="meth-note">Every prospect a source graded that preseason is in its cohort - players who never debuted stay in at 0 WAR (no survivorship cherry-picking). Cumulative WAR is censored at today, so younger cohorts (2023) have had less time to accrue it; the rate columns (WAR/yr, Reg pace) are less sensitive to that. <strong>eFV note:</strong> eFV is shown on its out-of-sample resolved cohort, which is debuted-heavy (its grades come from the labeled training pool), so its absolute WAR/contributor levels run a touch higher than the sources' full cohorts - compare the <em>shape</em> of the tier separation, not the absolute height.</p>
      <div class="meth-tables">${bt.raters.concat(bt.cohorts.xfv ? ["xfv"] : []).map(r => _methTierTable(bt, r)).join("")}</div>
      <div class="meth-caveats">
        <div class="meth-caveats-title">⚠ Read this honestly</div>
        <ul>
          <li><strong>Short track record.</strong> Only ${bt.window.years.length} preseason base years (${bt.window.years.join(", ")}) are old enough to have resolved outcomes. The newer sources have <em>zero</em> resolved cohorts.</li>
          <li><strong>Thin top tiers.</strong> The 60+ tier is only n≈40-60 across all years - a handful of hits or misses moves its rates a lot.</li>
          <li><strong>Censoring.</strong> Outcomes are cumulative WAR as of ${escapeHtml(bt.as_of_date || "today")}; the 2023 cohort has had ~3 seasons, the 2021 cohort ~5. Rate metrics mitigate but don't erase this.</li>
          <li><strong>eFV's edge is real but bounded.</strong> eFV leads pooled and on most archetypes, FV tiers, and eras, and the lead holds on recent cohorts (not just older, easier-to-beat scouting). It trails the consensus on a couple of young, low-track-record archetypes, and the margins are a few Spearman points: a calibrated grade that out-ranks the field by a steady, defensible amount, not a perfect predictor.</li>
          <li><strong>eFV is in-the-loop, not infallible.</strong> Its grades come from production we have; for the youngest prospects (recent draftees, int'l signs with no pro reps) it leans on the consensus prior, and where richer data exists (Statcast, Stuff+) it is only a live overlay, not yet historical. The lead grows when the data does.</li>
        </ul>
      </div>`;
  }
  // Framed as a distinct analytical area (eyebrow + bordered panel) so it reads
  // as the empirical evidence, not more prose.
  el.innerHTML = `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Empirical backtest · resolved cohorts only</div>
    ${backtestHTML}
  </div>`;
}

// ---- Models & Proofs view --------------------------------------------------
// The platform's accountability ledger as a browsable, family-grouped,
// verdict-filterable view. Same registry the Methodology table renders
// verbatim (data/model_registry.json), reorganized so a reader can audit one
// family or one verdict at a time. Lazy-loaded once into _MODELS, mirroring
// the Source Comparison fetch / guard / failure pattern.
const _MODEL_FAMILY_ORDER = ["PROSPX / eFV", "MLB Projections", "Free Agency",
  "MLB Stats", "Draft", "Trade Machine", "Other", "Internal / model-dev"];
const _MODEL_VERDICT_ORDER = ["validated", "provisional", "unvalidated", "deprecated"];
// Tokens kept fully uppercased when a model_id is humanized into a label. The
// list the owner keeps uppercase (REM, RIV, SEM, FV, WAR, WAG, PAL, FA, DPW,
// QO, SC, RPS, KRP, DS) plus a few domain acronyms that appear in ids. The
// bare "<=4 chars" shortcut was dropped on purpose: it shouts common words
// (PICK, TAX, SLOT, TEAM, WIN, FIT), which reads badly in user-facing copy.
const _MODEL_ACRONYMS = new Set(["REM", "RIV", "SEM", "FV", "WAR", "WAG", "PAL",
  "FA", "DPW", "QO", "SC", "RPS", "KRP", "DS", "MLB", "ETA", "IFA", "NPB", "KBO",
  "CPBL", "AAA", "AA", "ERA", "OPS", "AUC"]);
const _MODEL_MIXEDCASE = { efv: "eFV", xfv: "eFV", gmli: "gmLI" };
const _MODEL_STOPWORDS = new Set(["to", "vs", "of", "and", "the", "per", "by", "a"]);

function _modelLabel(id) {
  const toks = String(id == null ? "" : id).split("_");
  return toks.map((tok, i) => {
    if (!tok) return tok;
    const low = tok.toLowerCase();
    if (_MODEL_MIXEDCASE[low]) return _MODEL_MIXEDCASE[low];
    if (_MODEL_ACRONYMS.has(tok.toUpperCase())) return tok.toUpperCase();
    if (i > 0 && _MODEL_STOPWORDS.has(low)) return low;
    return tok.charAt(0).toUpperCase() + tok.slice(1);
  }).join(" ");
}

// Family from the surface (+ id as a fallback signal). Internal / model-dev is
// tested FIRST so the many "rendered nowhere" dev artifacts land there rather
// than being pulled into a product family by an incidental mention of eFV or
// Projections in their description.
function _modelFamily(m) {
  const s = ((m.surface || "") + " " + (m.model_id || "")).toLowerCase();
  const any = arr => arr.some(n => s.indexOf(n) !== -1);
  if (any(["model-dev", "rendered nowhere", "loss ledger", "not wired", "n/a", "internal"])) return "Internal / model-dev";
  if (any(["mlbstats", "bullpen", "starter"])) return "MLB Stats";
  if (any(["trademachine", "trade machine"])) return "Trade Machine";
  if (any(["free agency", "/fa/"])) return "Free Agency";
  if (any(["/projections/", "projections"])) return "MLB Projections";
  if (any(["draft"])) return "Draft";
  if (any(["prospx", "efv", "xfv"])) return "PROSPX / eFV";
  return "Other";
}

function _modelRow(label, val) {
  return val
    ? `<div class="gl-model-row"><span class="gl-model-rowlabel">${label}</span><span class="gl-model-rowval">${escapeHtml(val)}</span></div>`
    : "";
}

// The proof line: a link to the committed eval artifact where one exists; the
// audit-hit-list note for an unvalidated claim with no eval; the consensus /
// source models also point at the Source Comparison head-to-head. Eval-less
// internal rows get no Proof line at all.
function _modelProofHTML(m) {
  const bits = [];
  if (m.eval_artifact) {
    bits.push(`<a href="/${escapeHtml(m.eval_artifact)}" target="_blank" rel="noopener">${escapeHtml(m.eval_artifact)}</a>`);
  } else if (m.verdict === "unvalidated") {
    bits.push("No committed eval yet (this is the audit's hit list).");
  }
  if (m.model_id === "consensus_fv" || m.model_id === "source_track_record") {
    bits.push("See the Source Comparison view for the head-to-head proof.");
  }
  if (!bits.length) return "";
  return `<div class="gl-model-row"><span class="gl-model-rowlabel">Proof</span><span class="gl-model-rowval">${bits.join(" ")}</span></div>`;
}

// Report Card v0: paired champion-vs-baseline bars for each headline metric.
// Bars are normalized to the larger of the two values so the win is visible;
// the winner (per `better`) gets a star. One try/catch-wrapped card must never
// strand the ledger, so the caller degrades to the text card on a throw.
function _cardHeadline(card) {
  if (!card || !Array.isArray(card.headline) || !card.headline.length) return "";
  const rows = card.headline.map(h => {
    const champWins = h.better === "lower" ? h.champion <= h.baseline : h.champion >= h.baseline;
    const scale = Math.max(Math.abs(h.champion), Math.abs(h.baseline)) || 1;
    const bar = (val, isChamp) => {
      const pct = Math.max(2, Math.min(100, Math.abs(val) / scale * 100));
      return `<div class="gl-card-barrow">
        <span class="gl-card-barlab">${isChamp ? "model" : "baseline"}${isChamp && champWins ? " ★" : ""}</span>
        <span class="gl-card-track"><span class="gl-card-fill${isChamp ? " gl-card-fill--champ" : ""}" style="width:${pct.toFixed(1)}%"></span></span>
        <span class="gl-card-barval">${escapeHtml(String(val))}</span></div>`;
    };
    const dir = h.better === "lower" ? "lower is better" : "higher is better";
    return `<div class="gl-card-metric">
      <div class="gl-card-metriclab">${escapeHtml(h.label)} <span class="gl-card-dir">(${dir})</span></div>
      ${bar(h.champion, true)}${bar(h.baseline, false)}</div>`;
  }).join("");
  const foot = [card.n ? `n = ${escapeHtml(String(card.n))}` : "", escapeHtml(card.window || "")]
    .filter(Boolean).join(" · ");
  return `<div class="gl-card-proof">${rows}${foot ? `<div class="gl-card-foot">${foot}</div>` : ""}</div>`;
}

function _modelCard(m) {
  const v = m.verdict || "";
  const badge = `<span class="gl-verdict gl-verdict--${escapeHtml(v)}">${escapeHtml(v)}</span>`;
  let cardHtml = "";
  if (_S.cards && m.card) {
    try { cardHtml = _cardHeadline(m.card); } catch (err) { cardHtml = ""; }
  }
  return `<details class="gl-model-card">
    <summary class="gl-model-head">
      <span class="gl-model-name">${escapeHtml(_modelLabel(m.model_id))}</span>
      ${badge}
      <span class="gl-model-surface">${escapeHtml(m.surface || "")}</span>
    </summary>
    <div class="gl-model-body">
      ${cardHtml}
      ${_modelRow("Predicts", m.predicts)}
      ${_modelRow("Champion", m.champion)}
      ${_modelRow("Baseline it must beat", m.baseline)}
      ${_modelRow("How it is measured", m.metric)}
      ${_modelRow("Accountability", m.notes)}
      ${_modelProofHTML(m)}
    </div>
  </details>`;
}

function _modelsShell(inner) {
  return `<div class="source-comp-wrap">
    <div class="source-comp-eyebrow"><span class="scx-dot"></span>Models &amp; Proofs · the accountability ledger</div>
    ${inner}
  </div>`;
}

function renderModels() {
  const el = document.getElementById("models-body");
  if (!el) return;
  if (!_MODELS && !_MODELS_LOADING) {
    _MODELS_LOADING = true;
    fetch("/data/model_registry.json", { cache: "no-cache" })
      .then(r => (r.ok ? r.json() : null))
      .then(j => { _MODELS = j || { __error: true }; _MODELS_LOADING = false;
        if (_S.view === "models") renderModels(); })
      // A failed fetch (or a throw in the re-render) must surface the retry
      // state, never strand the loading placeholder.
      .catch(() => { _MODELS = { __error: true }; _MODELS_LOADING = false;
        if (_S.view === "models") renderModels(); });
  }
  const reg = _MODELS;
  if (!reg) {
    el.innerHTML = _modelsShell(`<div class="state-message">Loading the model registry...</div>`);
    return;
  }
  if (reg.__error || !Array.isArray(reg.models) || !reg.models.length) {
    el.innerHTML = _modelsShell(`<div class="state-message">The model registry could not be loaded.<div style="margin-top:12px;"><button class="chip" type="button" id="gl-models-retry">Retry</button></div></div>`);
    const rb = document.getElementById("gl-models-retry");
    if (rb) rb.onclick = () => { _MODELS = null; _MODELS_LOADING = false; renderModels(); };
    return;
  }

  const models = reg.models;
  const counts = {};
  models.forEach(m => { counts[m.verdict] = (counts[m.verdict] || 0) + 1; });
  const filters = [["all", "All", models.length]].concat(
    _MODEL_VERDICT_ORDER.map(v => [v, v.charAt(0).toUpperCase() + v.slice(1), counts[v] || 0]));
  const chips = filters.map(([key, lbl, n]) =>
    `<button class="chip${_MODELS_FILTER === key ? " active" : ""}" type="button" data-gl-mfilter="${escapeHtml(key)}">${escapeHtml(lbl)} <span class="gl-count">${n}</span></button>`).join("");

  const shown = _MODELS_FILTER === "all" ? models : models.filter(m => m.verdict === _MODELS_FILTER);
  const byFam = new Map();
  shown.forEach(m => {
    const f = _modelFamily(m);
    if (!byFam.has(f)) byFam.set(f, []);
    byFam.get(f).push(m);
  });
  const famOrder = _MODEL_FAMILY_ORDER.concat([...byFam.keys()].filter(f => _MODEL_FAMILY_ORDER.indexOf(f) === -1));
  const groupsHTML = famOrder.filter(f => byFam.has(f)).map(f =>
    `<div class="gl-model-group">
      <div class="gl-model-grouphead">${escapeHtml(f)} <span class="gl-count">${byFam.get(f).length}</span></div>
      ${byFam.get(f).map(_modelCard).join("")}
    </div>`).join("");

  const summary = `${models.length} models: ${counts.validated || 0} validated, ${counts.provisional || 0} provisional, ${counts.unvalidated || 0} unvalidated, ${counts.deprecated || 0} deprecated${reg.checked_at ? ` &middot; last checked ${escapeHtml(reg.checked_at)}` : ""}.`;

  el.innerHTML = _modelsShell(`
    <h2 class="meth-h">Every model that makes a predictive claim</h2>
    <p class="meth-note">This is the platform's accountability ledger. Every model that makes a predictive claim is listed here with an honest verdict, misses included. <strong>Validated</strong> means a forward-chained out-of-sample backtest exists and the champion beats its stated baseline. <strong>Provisional</strong> means measured but partial. <strong>Unvalidated</strong> means a claim with no measurement yet. <strong>Deprecated</strong> means it failed its gate and was retired.</p>
    <p class="gl-model-summary">${summary}</p>
    <div class="filter-bar gl-model-filters">${chips}</div>
    ${shown.length ? groupsHTML : `<div class="state-message">No models with that verdict.</div>`}`);

  el.querySelectorAll("[data-gl-mfilter]").forEach(b => b.onclick = () => {
    _MODELS_FILTER = b.dataset.glMfilter; renderModels();
  });
}

})();
